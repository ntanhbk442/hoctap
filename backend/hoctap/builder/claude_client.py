"""All Claude access goes through `ClaudeClient`: one call per page.

`ClaudeCliClient` is the real client. It runs the Claude Code CLI headless
(`claude -p ... --output-format json --json-schema ...`), which reads the page images with
its Read tool; no `ANTHROPIC_API_KEY` is needed. Each call runs in its own empty temp
directory with user/project/local settings, MCP servers and skills switched off, so only
the extraction prompt and the pages folder are in play. `FakeClaudeClient` drives every
test, so no test ever spawns the CLI.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class PageRequest:
    """Everything one call needs (an extract or a verify call)."""

    page_ref: str
    prompt: str
    system_prompt: str
    schema: dict[str, Any]
    model: str
    add_dir: Path  # the only folder the CLI may read (the page images)
    max_budget_usd: float
    timeout_seconds: float
    stage: str = "extract"  # the build stage the call is for (not sent to the CLI)


@dataclass(frozen=True)
class CallResult:
    """The outcome of one call.

    `output` is the structured output when `ok`. `transient` says whether one retry may
    help (a timeout, a crash, an API error); a refusal, a schema failure, the budget cap,
    an auth problem or an unknown model is not retried. `cost_usd` and `usage` are what the
    call spent, even when it failed; `cost_unknown` is set when the CLI reported nothing
    (a timeout, unparsable output), so the spend may be anything up to the per-call cap.
    """

    ok: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    transient: bool = False
    cost_usd: float = 0.0
    usage: Usage = field(default_factory=Usage)
    cost_unknown: bool = False


class ClaudeClient(Protocol):
    def extract(self, request: PageRequest) -> CallResult: ...


# CLI result subtypes that a retry would not fix (it would only spend again).
_PERMANENT_SUBTYPES = {"error_max_budget_usd", "error_max_structured_output_retries"}
# Error texts that a retry would not fix: not logged in, bad credentials, unknown model.
_PERMANENT_ERROR = re.compile(
    r"authenticat|not logged in|/login|log in|invalid api key|api key|oauth|unauthori[sz]ed|"
    r"permission_error|forbidden|not_found_error|model.{0,40}(not found|not exist|invalid|"
    r"unknown|not available)|(invalid|unknown) model",
    re.IGNORECASE,
)


def _budget(value: float) -> str:
    return f"{value:.2f}"


def cli_argv(executable: str, request: PageRequest) -> list[str]:
    """The `claude -p` command line for one page. The prompt comes right after `-p`,
    because `--tools` and `--add-dir` take several values."""
    return [
        executable,
        "-p",
        request.prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(request.schema, ensure_ascii=False, separators=(",", ":")),
        "--system-prompt",
        request.system_prompt,
        "--tools",
        "Read",
        "--add-dir",
        str(request.add_dir),
        "--restricted",  # ignore user, project and local settings files
        "--strict-mcp-config",  # no MCP servers (none are passed)
        "--disable-slash-commands",  # no skills
        "--no-session-persistence",
        "--model",
        request.model,
        "--max-budget-usd",
        _budget(request.max_budget_usd),
    ]


def _usage(data: Any) -> Usage:
    if not isinstance(data, dict):
        return Usage()

    def num(key: str) -> int:
        value = data.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    return Usage(
        input_tokens=num("input_tokens"),
        output_tokens=num("output_tokens"),
        cache_creation_input_tokens=num("cache_creation_input_tokens"),
        cache_read_input_tokens=num("cache_read_input_tokens"),
    )


def _result_object(stdout: str) -> dict[str, Any] | None:
    """The CLI's JSON result: the whole stdout, else the last line that is a JSON object
    (the CLI may print warnings around it)."""
    try:
        data = json.loads(stdout)
    except ValueError:
        data = None
    if isinstance(data, dict):
        return data
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_cli_output(returncode: int, stdout: str, stderr: str = "") -> CallResult:
    """Turns the CLI's `--output-format json` result into a `CallResult`.

    A failure is: a non-zero exit, no JSON result object, `is_error`, a `subtype` other
    than `success`, or a missing `structured_output`.
    """
    data = _result_object(stdout)
    if data is None:
        tail = (stderr or stdout).strip()[-500:]
        return CallResult(
            ok=False,
            error=f"exit {returncode}: output is not a JSON result: {tail!r}",
            transient=not _PERMANENT_ERROR.search(tail),
            cost_unknown=True,
        )
    cost = data.get("total_cost_usd")
    known = isinstance(cost, int | float) and not isinstance(cost, bool)
    cost = float(cost) if known else 0.0
    usage = _usage(data.get("usage"))
    subtype = data.get("subtype")
    if returncode != 0 or data.get("is_error") or subtype != "success":
        detail = str(data.get("result") or stderr or "").strip()[-500:]
        permanent = subtype in _PERMANENT_SUBTYPES or bool(_PERMANENT_ERROR.search(detail))
        return CallResult(
            ok=False,
            error=f"exit {returncode}, subtype {subtype!r}: {detail}",
            transient=not permanent,
            cost_usd=cost,
            usage=usage,
            cost_unknown=not known,
        )
    output = data.get("structured_output")
    if not isinstance(output, dict):
        detail = str(data.get("result") or "").strip()[-500:]
        return CallResult(
            ok=False,
            error=f"no structured_output (refusal or schema failure): {detail}",
            cost_usd=cost,
            usage=usage,
            cost_unknown=not known,
        )
    return CallResult(ok=True, output=output, cost_usd=cost, usage=usage, cost_unknown=not known)


Popen = Callable[..., Any]


class ClaudeCliClient:
    """The real client: one `claude -p` subprocess per page, in a fresh temp directory.

    `terminate_all()` stops every running child (used on Ctrl-C)."""

    def __init__(self, executable: str = "claude", popen: Popen = subprocess.Popen) -> None:
        self.executable = executable
        self._popen = popen
        self._lock = threading.Lock()
        self._running: set[Any] = set()
        self._stopped = False

    def extract(self, request: PageRequest) -> CallResult:
        argv = cli_argv(self.executable, request)
        with tempfile.TemporaryDirectory(prefix="hoctap-claude-") as cwd:
            with self._lock:
                if self._stopped:
                    return CallResult(ok=False, error="cancelled")
                try:
                    proc = self._popen(
                        argv,
                        cwd=cwd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError as exc:
                    return CallResult(ok=False, error=f"cannot run {self.executable}: {exc}")
                self._running.add(proc)
            try:
                stdout, stderr = proc.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return CallResult(
                    ok=False,
                    error=f"timed out after {request.timeout_seconds:g}s",
                    transient=True,
                    cost_unknown=True,
                )
            finally:
                with self._lock:
                    self._running.discard(proc)
        return parse_cli_output(proc.returncode, stdout or "", stderr or "")

    def terminate_all(self) -> None:
        with self._lock:
            self._stopped = True
            running = list(self._running)
        for proc in running:
            try:
                proc.terminate()
            except OSError:
                pass


Responder = Callable[[PageRequest], CallResult]


@dataclass
class FakeClaudeClient:
    """An in-memory client: `responder(request)` builds each call's result (a responder
    may raise `FakeCrash` to simulate a crash). Thread-safe: calls come from a worker pool.
    """

    responder: Responder
    calls: list[PageRequest] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def extract(self, request: PageRequest) -> CallResult:
        with self._lock:
            self.calls.append(request)
        return self.responder(request)


class FakeCrash(RuntimeError):
    """Raised by `FakeClaudeClient` to simulate the builder dying mid-run."""
