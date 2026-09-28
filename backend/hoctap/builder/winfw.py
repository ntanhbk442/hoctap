"""`hoctap install-windows`: one inbound Windows Firewall rule for the TLS port.

Only runs `netsh` on `platform.system() == "Windows"`; everywhere else it reports the
exact command it would run and does nothing (so this is buildable and testable on
Linux/WSL). `platform_name` and `run` are both injectable so both branches are testable
from Linux without touching a real OS or shelling out to `netsh`. Touches nothing besides
this one firewall rule: no service installation, no Task Scheduler autostart (AD-13).
"""

from __future__ import annotations

import platform
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

RULE_NAME = "Học Tập"

RunFunc = Callable[..., "subprocess.CompletedProcess[str]"]

_LOCAL_PORT_RE = re.compile(r"LocalPort:\s*(\d+)", re.IGNORECASE)


class FirewallError(Exception):
    """`netsh` reported a failure; `message` is already a clear, bilingual-ish hint."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class FirewallResult:
    executed: bool  # whether netsh was actually invoked (False off Windows)
    added: bool  # whether a rule was added or updated (False if already present as-is)
    message: str


def show_rule_command() -> list[str]:
    return ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}"]


def delete_rule_command() -> list[str]:
    return ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME}"]


def add_rule_command(port: int) -> list[str]:
    return [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={RULE_NAME}",
        "dir=in",
        "action=allow",
        "protocol=TCP",
        f"localport={port}",
        "profile=private",
        "remoteip=LocalSubnet",
    ]


def _existing_port(show_stdout: str) -> int | None:
    """The `LocalPort` netsh reports for the existing rule, or None if unparsable."""
    match = _LOCAL_PORT_RE.search(show_stdout or "")
    return int(match.group(1)) if match else None


def _run(command: list[str], run: RunFunc) -> subprocess.CompletedProcess[str]:
    try:
        return run(command, capture_output=True, text=True)
    except OSError as exc:
        raise FirewallError(
            f"Không chạy được netsh / could not run netsh ({' '.join(command)}): {exc}; "
            "hãy chạy với quyền quản trị viên / try running as Administrator."
        ) from exc


def _raise_on_failure(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        raise FirewallError(
            f"netsh {action} thất bại / netsh {action} failed ({detail}); hãy chạy với "
            "quyền quản trị viên / try running as Administrator."
        )


def install(
    port: int,
    *,
    platform_name: str | None = None,
    run: RunFunc = subprocess.run,
) -> FirewallResult:
    """Adds the firewall rule for `port` on Windows; reports what it would do elsewhere.

    Idempotent on Windows: checks for an existing rule with the same name (via `show
    rule`) before adding, and compares its `LocalPort` against the requested one. A rule
    already open on the right port is left alone; a rule found on a different (or
    unparsable) port is deleted and re-added on the requested port. Raises `FirewallError`
    when `netsh` reports a non-zero exit or cannot be run at all, with a message pointing
    at running as Administrator.
    """
    system = platform.system() if platform_name is None else platform_name
    add_command = add_rule_command(port)
    if system != "Windows":
        return FirewallResult(
            executed=False,
            added=False,
            message="Không phải Windows / not Windows; sẽ chạy lệnh sau trên Windows / "
            "would run this command on Windows: " + " ".join(add_command),
        )

    show = _run(show_rule_command(), run)
    if show.returncode == 0:
        if _existing_port(show.stdout) == port:
            return FirewallResult(
                executed=True,
                added=False,
                message=f'Đã có quy tắc tường lửa "{RULE_NAME}" cho cổng {port} / firewall '
                f'rule "{RULE_NAME}" already present for port {port}; skipped.',
            )
        # A rule with this name exists but for a different (or unreadable) port: replace it.
        _raise_on_failure(_run(delete_rule_command(), run), "delete")
        _raise_on_failure(_run(add_command, run), "add")
        return FirewallResult(
            executed=True,
            added=True,
            message=f'Đã cập nhật quy tắc tường lửa "{RULE_NAME}" sang cổng {port} / '
            f'updated firewall rule "{RULE_NAME}" to port {port}.',
        )

    added = _run(add_command, run)
    _raise_on_failure(added, "add")
    return FirewallResult(
        executed=True,
        added=True,
        message=f'Đã thêm quy tắc tường lửa "{RULE_NAME}" cho cổng {port} / added firewall '
        f'rule "{RULE_NAME}" for port {port}.',
    )
