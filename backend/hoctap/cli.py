"""`hoctap` command line: `serve`, `export-*` schemas and
`build catalogue|pilot|verify|publish|guides|speak-missing|gate|full`."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import shutil
import socket
import sys
import threading
from dataclasses import replace
from pathlib import Path

from hoctap.config import REPO_ROOT, ConfigError, load_settings, validate_port

try:  # PyMuPDF's own error classes, for the pilot's error handler
    import pymupdf as _pymupdf

    _PYMUPDF_ERRORS: tuple[type[BaseException], ...] = tuple(
        e
        for e in (
            getattr(_pymupdf, "FileDataError", None),
            getattr(getattr(_pymupdf, "mupdf", None), "FzErrorBase", None),
        )
        if isinstance(e, type)
    )
except ImportError:  # pragma: no cover
    _PYMUPDF_ERRORS = ()

DEFAULT_OPENAPI_OUT = REPO_ROOT / "frontend" / "openapi.json"
DEFAULT_SCHEMA_OUT = Path(__file__).resolve().parent / "content" / "problemdoc.schema.json"
DEFAULT_EXTRACTION_SCHEMA_OUT = (
    Path(__file__).resolve().parent / "builder" / "extraction" / "page_extraction.schema.json"
)
DEFAULT_VERIFY_SCHEMA_OUT = (
    Path(__file__).resolve().parent / "builder" / "verify" / "verify_page.schema.json"
)


class ServeError(Exception):
    """A `hoctap serve` startup failure (e.g. a port already in use). `code` is the CLI
    exit code; `message` is already bilingual."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _bind_socket(host: str, port: int) -> socket.socket:
    """Binds `host:port` ourselves (instead of letting uvicorn do it) so a conflict
    surfaces as a typed `ServeError` instead of uvicorn's raw `sys.exit`/traceback."""
    try:
        return socket.create_server((host, port))
    except OSError as exc:
        raise ServeError(
            f"Cổng {port} đã được dùng bởi chương trình khác (có thể là một `hoctap serve` "
            f"khác đang chạy) / port {port} is already in use (perhaps by another running "
            f"`hoctap serve`, or another program): {exc}. Đóng chương trình đó, hoặc chọn "
            f"cổng khác bằng --port / close that program, or choose a different port with "
            "--port.",
            code=4,
        ) from exc


def _run_servers(servers: list, sockets: list[socket.socket]) -> int:  # noqa: ANN001
    """Runs each already-configured uvicorn `Server` concurrently, one per thread, each on its
    own pre-bound socket.

    Each `Server` runs in its own OS thread (its own `asyncio` loop via `Server.run()`), not
    together via `asyncio.gather` in one loop: uvicorn's `Server.serve()` installs its own
    Ctrl-C/SIGTERM handler per call (`capture_signals()`), and a second concurrent call's
    `with` block would clobber the first's handler, breaking a single Ctrl-C's ability to stop
    both. `signal.signal()` only has an effect from the main thread, so uvicorn's per-server
    handler install becomes a no-op in a background thread; instead we install exactly one
    handler here, in the main thread, that flips `should_exit` on every server together.
    """
    import signal

    threads = [
        threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        for server, sock in zip(servers, sockets, strict=True)
    ]

    def _handle_exit(signum: int, frame: object) -> None:  # noqa: ARG001
        for server in servers:
            server.should_exit = True

    # `signal.signal()` only works from the interpreter's main thread (Python itself
    # enforces this); when `_serve` is driven from elsewhere (e.g. test harnesses running it
    # in a worker thread), skip installing a handler here, same as uvicorn's own
    # `Server.capture_signals()` does -- the caller is then responsible for stopping the
    # servers (e.g. by setting `.should_exit` on them directly).
    previous: dict[int, object] = {}
    if threading.current_thread() is threading.main_thread():
        previous = {
            sig: signal.signal(sig, _handle_exit) for sig in (signal.SIGINT, signal.SIGTERM)
        }
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        for sock in sockets:
            with contextlib.suppress(OSError):
                sock.close()
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from hoctap.app import create_app

    settings = load_settings()
    if args.host:
        settings = replace(settings, host=args.host)
    if args.port is not None:
        settings = replace(settings, port=validate_port(args.port, "--port"))

    cert_file, key_file = settings.tls_cert_file, settings.tls_key_file
    log_level = settings.log_level.lower()
    # A separate `create_app(settings)` per bound port, not one app shared across servers:
    # FastAPI's lifespan (DB engine, RunManager) lives on `app.state`, which two concurrently
    # running `Server`s would stomp on (double startup, one's shutdown disposing the engine
    # the other is still using). Two engines onto the same SQLite file is the supported case
    # already (WAL mode + `db_lock`), exactly like two separate `hoctap serve` processes.
    configs: list[uvicorn.Config] = []

    if cert_file.is_file() and key_file.is_file():
        tls_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}
        if args.port is not None:
            # An explicit --port asks for one specific bind: TLS only, on that port.
            print(f"HTTPS bật / HTTPS is on (cert: {cert_file}); binding port {settings.port}.")
            configs.append(
                uvicorn.Config(
                    create_app(settings),
                    host=settings.host,
                    port=settings.port,
                    log_level=log_level,
                    **tls_kwargs,
                )
            )
        else:
            # The documented default: HTTPS on tls_port, plus the plain-HTTP fallback on
            # port (spec-1-11's no-install-needed fallback for a tablet without the CA yet).
            print(
                f"HTTPS bật / HTTPS is on (cert: {cert_file}); binding port {settings.tls_port} "
                f"(HTTPS) and port {settings.port} (HTTP dự phòng / HTTP fallback)."
            )
            configs.append(
                uvicorn.Config(
                    create_app(settings),
                    host=settings.host,
                    port=settings.tls_port,
                    log_level=log_level,
                    **tls_kwargs,
                )
            )
            configs.append(
                uvicorn.Config(
                    create_app(settings),
                    host=settings.host,
                    port=settings.port,
                    log_level=log_level,
                )
            )
    else:
        if cert_file.exists() != key_file.exists():
            missing = key_file if cert_file.exists() else cert_file
            print(
                f"Cảnh báo / Warning: thiếu {missing}, coi như chưa có chứng chỉ / missing "
                f"{missing}, treating the certificate as absent.",
                file=sys.stderr,
            )
        print(
            "HTTPS tắt / HTTPS is off: serving plain HTTP. Chạy `hoctap certs --ip <ip>` "
            "để bật / run `hoctap certs --ip <ip>` to enable it."
        )
        configs.append(
            uvicorn.Config(
                create_app(settings), host=settings.host, port=settings.port, log_level=log_level
            )
        )

    sockets: list[socket.socket] = []
    try:
        for config in configs:
            sockets.append(_bind_socket(config.host, config.port))
    except ServeError as exc:
        for sock in sockets:
            with contextlib.suppress(OSError):
                sock.close()
        print(exc.message, file=sys.stderr)
        return exc.code

    servers = [uvicorn.Server(config) for config in configs]
    return _run_servers(servers, sockets)


def _certs_cmd(args: argparse.Namespace) -> int:
    from hoctap.builder.certs import CertsError, generate

    settings = load_settings()
    try:
        paths = generate(args.ip, args.hostname, settings.tls_cert_dir, args.force)
    except CertsError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    print(f"Đã ghi {paths.cert_file} / wrote {paths.cert_file}")
    print(f"Đã ghi {paths.key_file} / wrote {paths.key_file}")
    return 0


def _install_windows_cmd(_args: argparse.Namespace) -> int:
    from hoctap.builder.winfw import FirewallError, install

    settings = load_settings()
    try:
        result = install(settings.tls_port)
    except FirewallError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(result.message)
    return 0


def _export_openapi(args: argparse.Namespace) -> int:
    from hoctap.app import create_app

    # The lifespan (data dir, DB, migrations) never runs here: schema only.
    schema = create_app(load_settings()).openapi()
    return _write_json(Path(args.out), schema)


def _write_json(out: Path, data: object) -> int:
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"cannot write {out}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out}")
    return 0


def _export_schema(args: argparse.Namespace) -> int:
    from hoctap.content.schema import problemdoc_json_schema

    return _write_json(Path(args.out), problemdoc_json_schema())


def _build_catalogue(_args: argparse.Namespace) -> int:
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.builder.catalogue import CatalogueError, collect_rows, write_catalogue
    from hoctap.db.engine import create_db_engine, run_migrations
    from hoctap.parent.backup import db_lock

    nothing_written = "Không ghi gì vào cơ sở dữ liệu / Nothing was written."
    settings = load_settings()
    # Validate every file before the database is opened, so a failed run leaves no trace.
    try:
        rows = collect_rows(settings.source_dir)
    except CatalogueError as exc:
        print(exc, file=sys.stderr)
        print(nothing_written, file=sys.stderr)
        return 1

    try:
        with db_lock(settings.data_dir, blocking=True):
            engine = create_db_engine(settings.db_path)
            try:
                run_migrations(engine)
                report = write_catalogue(engine, rows)
            finally:
                engine.dispose()
    except (SQLAlchemyError, OSError) as exc:
        print(
            f"Lỗi cơ sở dữ liệu {settings.db_path} / Database error at {settings.db_path}: {exc}",
            file=sys.stderr,
        )
        print(nothing_written, file=sys.stderr)
        return 1

    result = report.result
    status = {book_id: "new" for book_id in result.inserted}
    status |= {book_id: "changed" for book_id in result.changed}
    for row in report.rows:
        mark = status.get(row.book_id, "")
        print(f"{row.book_id:<15} {row.page_count:>5} pages  {row.title_vi}  {mark}".rstrip())
    if result.orphaned:
        print(f"orphaned (in the database, not in the catalogue): {', '.join(result.orphaned)}")
    print(
        f"{len(report.rows)} books, {report.total_pages} pages: "
        f"{len(result.inserted)} new, {len(result.changed)} changed, "
        f"{len(result.unchanged)} unchanged, {len(result.orphaned)} orphaned"
    )
    return 0


def _export_extraction_schema(args: argparse.Namespace) -> int:
    from hoctap.builder.extraction.models import build_extraction_schema

    return _write_json(Path(args.out), build_extraction_schema())


def _export_verify_schema(args: argparse.Namespace) -> int:
    from hoctap.builder.verify.models import build_verify_schema

    return _write_json(Path(args.out), build_verify_schema())


def _positive_usd(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive finite amount: {value!r}")
    return number


def _claude_client(settings):  # noqa: ANN001, ANN202 - replaced in tests
    from hoctap.builder.claude_client import ClaudeCliClient

    return ClaudeCliClient(settings.claude_executable)


_SPEND_REFUSED = (
    "Lệnh này sẽ gọi Claude và tốn tiền. Thêm --yes-spend để chạy, hoặc "
    "--dry-run để chỉ tạo yêu cầu. / This calls Claude and costs money: add "
    "--yes-spend to run it, or --dry-run to only write the requests. "
    "Nothing was sent."
)


class _Refused(Exception):
    """The spending guard refused the run (exit code 2); the message is already printed."""


def _spend_client(args: argparse.Namespace, settings, needs_calls: bool):  # noqa: ANN001, ANN202
    """The client for a run that may call Claude, or None when no call is needed (or it is a
    dry run). Raises `_Refused` when the spending guard refuses."""
    if args.dry_run or not needs_calls:
        return None
    if not args.yes_spend:
        print(_SPEND_REFUSED, file=sys.stderr)
        raise _Refused
    if shutil.which(settings.claude_executable) is None:
        print(
            f"Không tìm thấy lệnh `{settings.claude_executable}` (Claude Code CLI) "
            f"trong PATH / `{settings.claude_executable}` (the Claude Code CLI) is not "
            "on PATH; install it or set claude_executable. Nothing was sent.",
            file=sys.stderr,
        )
        raise _Refused
    return _claude_client(settings)


def _run_build(args: argparse.Namespace, body) -> int:  # noqa: ANN001
    """Opens the database, runs `body(engine, settings, first, last)` and maps the errors
    to exit codes (2: usage or input, 1: failure, 130: interrupted).

    Holds the cross-process db lock (`hoctap.parent.backup.db_lock`) for as long as the
    database is open here, so a restore running concurrently (web or `hoctap restore`)
    cannot swap the file out from under this process -- it will fail its own non-blocking
    acquire and refuse instead.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.builder.pilot import PilotError, parse_pages
    from hoctap.db.engine import create_db_engine, run_migrations
    from hoctap.parent.backup import db_lock

    settings = load_settings()
    try:
        first, last = parse_pages(args.pages)
    except PilotError as exc:
        print(exc, file=sys.stderr)
        return 2
    with db_lock(settings.data_dir, blocking=True):
        try:
            engine = create_db_engine(settings.db_path)
        except OSError as exc:
            print(
                f"Lỗi cơ sở dữ liệu / Database error at {settings.db_path}: {exc}",
                file=sys.stderr,
            )
            return 1
        try:
            run_migrations(engine)
            return body(engine, settings, first, last)
        except _Refused:
            return 2
        except PilotError as exc:
            print(exc, file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print(
                "Đã dừng; các trang đã xong được giữ lại / Interrupted; finished pages are "
                "kept, re-run to continue.",
                file=sys.stderr,
            )
            return 130
        except (SQLAlchemyError, OSError, RuntimeError, ValueError, *_PYMUPDF_ERRORS) as exc:
            print(f"Lỗi / Error: {exc}", file=sys.stderr)
            return 1
        finally:
            engine.dispose()


def _print_calls(stage: str, calls) -> None:  # noqa: ANN001
    print(
        f"{stage}: {len(calls.done)} done, {len(calls.failed)} failed, {calls.calls} call(s), "
        f"${calls.cost_usd:.4f} this run"
    )
    if calls.unknown_cost_calls:
        print(f"{calls.unknown_cost_calls} call(s) reported no cost (counted at the per-call cap)")
    if calls.budget_skipped:
        print(
            f"Cảnh báo / Warning: hết ngân sách / run budget reached; "
            f"{len(calls.budget_skipped)} page(s) not started ({stage}): "
            f"{', '.join(calls.budget_skipped)}",
            file=sys.stderr,
        )


def _print_failed(stage: str, failed: dict[str, str]) -> None:
    if failed:
        print(
            f"Cảnh báo / Warning: {len(failed)} trang lỗi / page(s) failed ({stage}; "
            "re-run to retry):",
            file=sys.stderr,
        )
        for ref, error in sorted(failed.items()):
            print(f"  - {ref}: {error}", file=sys.stderr)


def _where(reason) -> str:  # noqa: ANN001
    if reason.part_key is None:
        return ""
    return f"{reason.part_key}/{reason.slot_key}:" if reason.slot_key else f"{reason.part_key}:"


def _print_verify(report) -> None:  # noqa: ANN001
    if report is None or report.verdicts is None:
        return
    _print_calls("verify", report.calls)
    verdicts = report.verdicts
    counts = verdicts.counts
    print(
        f"verdicts: {counts['agree']} agree, {counts['disagree']} disagree, "
        f"{counts['unverified']} unverified; {len(verdicts.needs_review)} need review"
    )
    for problem_id, reasons in sorted(verdicts.needs_review.items()):
        why = ", ".join(_where(r) + r.kind for r in reasons)
        print(f"  needs_review {problem_id}: {why}")
    if verdicts.invalid_docs:
        print(
            f"stored docs that no longer validate (unverified): {', '.join(verdicts.invalid_docs)}"
        )
    if verdicts.not_run_pages:
        pages = ", ".join(str(p) for p in verdicts.not_run_pages)
        print(f"pages not verified yet (re-run to verify): {pages}")
    if verdicts.unrendered_pages:
        pages = ", ".join(str(p) for p in verdicts.unrendered_pages)
        print(f"pages not rendered (not verified; run `hoctap build pilot`): {pages}")


def _print_publish(report) -> bool:  # noqa: ANN001
    """Prints the crop and publish report; returns whether any Problem failed."""
    if report is None:
        return False
    from hoctap.builder.stages.publish import describe, describe_failures

    for line in describe(report):
        print(line)
    for line in describe_failures(report):
        print(line, file=sys.stderr)
    return bool(report.failed)


def _build_publish(args: argparse.Namespace) -> int:
    from hoctap.builder.pilot import plan_publish, run_publish
    from hoctap.builder.stages.publish import nothing_current

    def body(engine, settings, first: int, last: int) -> int:  # noqa: ANN001
        plan = plan_publish(engine, args.book, first, last)
        print(f"{plan.book.book_id}: publish pages {first}-{last} ({len(plan.pages)} page(s))")
        report = run_publish(engine, settings, plan)
        failed = _print_publish(report)
        if nothing_current(report):
            print(
                "Không xuất bản được gì: mọi trang đều cũ / Nothing was published: every "
                "requested page is stale (no current extraction and validation); run "
                "`hoctap build pilot` for these pages first.",
                file=sys.stderr,
            )
            return 1
        return 1 if failed else 0

    return _run_build(args, body)


def _build_pilot(args: argparse.Namespace) -> int:
    from hoctap.builder import costs, gate
    from hoctap.builder.jobs_store import page_ref
    from hoctap.builder.pilot import (
        pending_pages,
        pending_verify_pages,
        plan_pilot,
        run_pilot,
    )

    verify = not args.no_verify

    def body(engine, settings, first: int, last: int) -> int:  # noqa: ANN001
        plan = plan_pilot(engine, settings, args.book, first, last)
        todo = pending_pages(engine, settings, plan)
        print(f"{plan.book.book_id}: pages {first}-{last} ({len(plan.pages)} page(s))")
        print(costs.estimate(len(todo), settings).describe(settings.extraction_model))
        verify_todo: set[int] = set()
        if verify:
            # Pages re-extracted now are verified too, as are validated pages not yet verified.
            verify_todo = set(todo) | set(pending_verify_pages(engine, settings, plan))
            print(
                "verify: "
                + costs.estimate(len(verify_todo), settings).describe(settings.verify_model)
            )
        # With verify on, validate may create pages to verify that are not known yet, so
        # --yes-spend always gets a client.
        needs_calls = bool(todo or verify_todo) or (verify and args.yes_spend)
        client = _spend_client(args, settings, needs_calls)
        if not args.dry_run and gate.new_pages_would_invalidate(
            engine, settings, [page_ref(plan.book.book_id, p) for p in todo]
        ):
            print(
                "Cảnh báo / Warning: đã duyệt chạy toàn bộ; các trang chạy thử mới này sẽ "
                "làm mất hiệu lực lần duyệt / the full run is approved; these new pilot "
                "pages will invalidate that approval.",
                file=sys.stderr,
            )
        report = run_pilot(
            engine,
            settings,
            plan,
            client,
            dry_run=args.dry_run,
            max_total_usd=args.max_total_usd,
            verify=verify,
            publish_pages=not args.no_publish,
        )
        if args.dry_run:
            return 0
        ext, val = report.extract, report.validate
        _print_calls("extract", ext)
        if val is not None:
            state = "unchanged" if val.unchanged else "rebuilt"
            print(
                f"validate: {state}, {val.pages} page(s); "
                f"{val.valid} valid, {val.invalid} invalid draft(s)"
            )
            if val.duplicates:
                print(f"duplicate problem ids (suffixed): {', '.join(val.duplicates)}")
            if val.stale_pages:
                pages = ", ".join(str(p) for p in val.stale_pages)
                print(f"stale pages (results removed, no current extraction): {pages}")
            for page, warnings in sorted(val.warnings.items()):
                for warning in warnings:
                    print(f"  page {page}: {warning}")
        _print_verify(report.verify)
        if report.verify_needed_pages:
            pages = ", ".join(str(p) for p in report.verify_needed_pages)
            print(
                f"pages whose results were rebuilt and still need verification "
                f"(run `hoctap build verify`): {pages}"
            )
        failed = _print_publish(report.publish_report)
        print(f"cost so far for {plan.book.book_id}: ${report.book_cost_usd:.4f}")
        _print_failed("extract", ext.failed)
        if report.verify is not None:
            _print_failed("verify", report.verify.calls.failed)
        return 1 if failed else 0

    return _run_build(args, body)


def _build_verify(args: argparse.Namespace) -> int:
    from hoctap.builder import costs
    from hoctap.builder.pilot import pending_verify_pages, plan_pilot, run_verify

    def body(engine, settings, first: int, last: int) -> int:  # noqa: ANN001
        plan = plan_pilot(engine, settings, args.book, first, last)
        todo = pending_verify_pages(engine, settings, plan)
        print(f"{plan.book.book_id}: verify pages {first}-{last} ({len(plan.pages)} page(s))")
        print(costs.estimate(len(todo), settings).describe(settings.verify_model))
        client = _spend_client(args, settings, bool(todo))
        report = run_verify(
            engine,
            settings,
            plan,
            client,
            dry_run=args.dry_run,
            max_total_usd=args.max_total_usd,
        )
        if args.dry_run:
            return 0
        _print_verify(report)
        with engine.connect() as conn:
            total = costs.total_cost(conn, f"{plan.book.book_id}#p")
        print(f"cost so far for {plan.book.book_id}: ${total:.4f}")
        _print_failed("verify", report.calls.failed)
        return 0

    return _run_build(args, body)


def _build_guides(args: argparse.Namespace) -> int:
    from hoctap.builder import costs
    from hoctap.builder.stages import guides

    def body(engine, settings) -> int:  # noqa: ANN001
        with engine.connect() as conn:
            tasks = guides.load_tasks(conn, args.concept)
        if not tasks:
            what = f" cho {args.concept} / for {args.concept}" if args.concept else ""
            print(f"Không có khái niệm nào có bài{what} / No Concept with Problems{what}.")
            return 1 if args.concept else 0
        todo, current, restore = guides.pending(engine, tasks, settings)
        print(
            f"guides: {len(tasks)} Concept(s), {len(todo)} to generate, {len(current)} up to "
            f"date, {len(restore)} to restore from a finished job"
        )
        if todo:
            print(costs.estimate(len(todo), settings).describe(settings.extraction_model))
        try:
            client = _spend_client(args, settings, bool(todo))
        except _Refused:
            return 2
        try:
            report = guides.run_guides(
                engine,
                client,
                settings,
                tasks,
                dry_run=args.dry_run,
                max_total_usd=args.max_total_usd,
                on_page=lambda ref, status: print(f"  {ref}: {status}"),
            )
        except KeyboardInterrupt:
            print(
                "Đã dừng; các khái niệm đã xong được giữ lại / Interrupted; finished Concepts "
                "are kept, re-run to continue.",
                file=sys.stderr,
            )
            return 130
        if args.dry_run:
            print(
                f"dry run: {len(report.requests_written)} guide request(s) written to "
                f"{guides.request_dir(settings)}; nothing was sent"
            )
            return 0
        if report.calls is not None:
            _print_calls("guides", report.calls)
        print(
            f"guides: {len(report.generated)} generated, {len(report.skipped)} skipped "
            f"(unchanged), {len(report.failed)} failed"
        )
        if report.drafted_from_problems:
            print(
                "drafted from sample Problems (no book material; review these first): "
                + ", ".join(report.drafted_from_problems)
            )
        _print_failed("guides", report.failed)
        return 1 if report.failed else 0

    return _open_db(body)


def _tts_client(settings):  # noqa: ANN001, ANN202 - replaced in tests
    from hoctap.builder.tts_client import make_engine

    return make_engine(settings.tts_engine)


def _spend_tts_client(args: argparse.Namespace, settings, needs_calls: bool):  # noqa: ANN001, ANN202
    """Like `_spend_client`, but edge-tts (free) never needs `--yes-spend`: only the cloud
    engine is gated behind it."""
    from hoctap.builder.tts_client import EDGE_ENGINE

    if args.dry_run or not needs_calls:
        return None
    if settings.tts_engine != EDGE_ENGINE and not args.yes_spend:
        print(_SPEND_REFUSED, file=sys.stderr)
        raise _Refused
    return _tts_client(settings)


def _build_speak_missing(args: argparse.Namespace) -> int:
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.builder.stages import speak
    from hoctap.builder.tts_client import PRICE_PER_CHAR_USD
    from hoctap.config import REPO_ROOT
    from hoctap.db.engine import create_db_engine, run_migrations

    settings = load_settings()
    try:
        engine = create_db_engine(settings.db_path)
    except OSError as exc:
        print(f"Lỗi cơ sở dữ liệu / Database error at {settings.db_path}: {exc}", file=sys.stderr)
        return 1
    try:
        run_migrations(engine)
        with engine.connect() as conn:
            refs = speak.collect_refs(conn, REPO_ROOT, settings.tts_voice_id)
        todo = speak.pending_keys(settings.data_dir, refs)
        print(f"speak-missing: {len(refs)} referenced key(s), {len(todo)} missing")
        client = _spend_tts_client(args, settings, bool(todo))
        max_total = settings.tts_max_total_usd if args.max_total_usd is None else args.max_total_usd
        cost_per_char = PRICE_PER_CHAR_USD.get(settings.tts_engine, 0.0)
        report = speak.run_speak(
            engine,
            settings.data_dir,
            REPO_ROOT,
            client,
            settings.tts_voice_id,
            dry_run=args.dry_run,
            max_total_usd=max_total,
            cost_per_char_usd=cost_per_char,
        )
        for line in speak.describe(report):
            print(line)
        for line in speak.describe_failures(report):
            print(line, file=sys.stderr)
        return 1 if report.failed else 0
    except _Refused:
        return 2
    except (SQLAlchemyError, OSError) as exc:
        print(f"Lỗi / Error: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def _open_db(body) -> int:  # noqa: ANN001
    """Opens the database (migrated) and runs `body(engine, settings)`; database errors
    exit 1.

    Holds the cross-process db lock for as long as the database is open here (see
    `_run_build`), so this and a concurrent restore can never both touch `db_path`.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.db.engine import create_db_engine, run_migrations
    from hoctap.parent.backup import db_lock

    settings = load_settings()
    with db_lock(settings.data_dir, blocking=True):
        try:
            engine = create_db_engine(settings.db_path)
        except OSError as exc:
            print(
                f"Lỗi cơ sở dữ liệu / Database error at {settings.db_path}: {exc}",
                file=sys.stderr,
            )
            return 1
        try:
            run_migrations(engine)
            return body(engine, settings)
        except (SQLAlchemyError, OSError) as exc:
            print(f"Lỗi / Error: {exc}", file=sys.stderr)
            return 1
        finally:
            engine.dispose()


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _print_gate(report) -> None:  # noqa: ANN001
    from hoctap.builder import gate

    if not report.has_pilot:
        print("Chưa chạy thử / No pilot yet: run `hoctap build pilot` first.")
        return
    books = ", ".join(f"{b.book_id}: {b.pilot_pages}" for b in report.books)
    print(
        f"Chạy thử / Pilot: {report.pilot_pages} trang / page(s) ({books}), "
        f"{report.pilot_problems} bài / Problem(s)"
    )
    mark = {True: "ĐẠT / PASS", False: "KHÔNG ĐẠT / FAIL"}
    fb = report.fallback
    print(
        f"[{mark[fb.passed]}] fallback_share {_pct(fb.value)} "
        f"({fb.with_fallback}/{fb.problems}; ≤ {_pct(fb.threshold)})"
    )
    acc = report.accuracy
    counted = acc.correct + acc.wrong
    extra = ""
    if not acc.enough_sample:
        extra = f"; chưa đủ mẫu / not enough samples ({counted} < {acc.min_sample})"
    print(
        f"[{mark[acc.passed]}] key_accuracy {_pct(acc.value)} "
        f"({acc.correct}/{counted}; ≥ {_pct(acc.threshold)}{extra})"
    )
    if acc.stale:
        print(f"  {acc.stale} kết quả cần kiểm tra lại / verdict(s) need re-checking")
    if acc.sample_outdated:
        print(f"  {gate.MSG_SAMPLE_OUTDATED} / the sample predates new pilot pages: draw again")
    if not acc.enough_problems:
        print(
            f"  {gate.MSG_NOT_ENOUGH_PROBLEMS} / not enough Problems to evaluate "
            f"({acc.eligible_problems} < {acc.min_sample}): pilot more pages"
        )
    if acc.sample_id is None:
        print("  Chưa rút mẫu kiểm tra / no spot-check sample drawn yet")
    cost = report.cost
    est = "—" if cost.est_cost is None else f"${cost.est_cost:.2f}"
    print(
        f"Chi phí / Cost: pilot ${cost.pilot_cost:.4f} over {cost.pilot_pages} page(s); "
        f"est {est} for {cost.remaining_pages} of {cost.total_pages} page(s)"
    )
    if cost.unknown_cost_calls:
        print(
            f"  {cost.unknown_cost_calls} call(s) of unknown cost, counted at "
            f"${cost.unknown_cost_cap_usd:.2f} each"
        )
    approval = report.approval
    if report.approved and approval is not None:
        print(f"Đã duyệt / Approved at {approval.approved_at} (est ${approval.est_cost:.2f})")
    elif approval is not None:
        print(
            "Lần duyệt không còn hiệu lực / Approval no longer valid: "
            + " ".join(approval.invalid_reasons)
        )
    else:
        print("Chưa duyệt / Not approved")


def _build_gate(_args: argparse.Namespace) -> int:
    from hoctap.builder import gate

    def body(engine, settings) -> int:  # noqa: ANN001
        with engine.connect() as conn:
            _print_gate(gate.report(conn, settings))
        return 0

    return _open_db(body)


# `hoctap build full` exits 3 when the go/no-go gate is not approved (GATE_NOT_APPROVED).
EXIT_GATE_NOT_APPROVED = 3


def _build_full(args: argparse.Namespace) -> int:
    """The full-corpus run (Story 6.2; `builder/full.py`). Exit codes: 0 done or stopped at a
    checkpoint, 1 failed pages or an error, 2 usage or spend not confirmed, 3 the go/no-go
    approval is missing or void (GATE_NOT_APPROVED), 4 the overall cap was reached (resumable),
    130 interrupted."""

    from hoctap.builder import full, gate
    from hoctap.builder.jobs import STALE_AFTER
    from hoctap.builder.pilot import PilotError
    from hoctap.ids import to_iso, utc_now

    def body(engine, settings) -> int:  # noqa: ANN001
        try:
            gate.require_approval(engine, settings)
        except gate.GateNotApproved as exc:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            return EXIT_GATE_NOT_APPROVED
        try:
            plan = full.plan_full(
                engine,
                settings,
                grade=args.grade,
                books=tuple(b.strip() for b in (args.books or "").split(",") if b.strip()),
            )
        except PilotError as exc:
            print(exc, file=sys.stderr)
            return 2
        for line in full.describe_plan(plan, settings):
            print(line)
        if args.dry_run:
            report = full.run_full(
                engine, settings, plan, None, max_total_usd=0.0, dry_run=True, out=print
            )
            print(
                f"dry run: {report.requests_written} request(s) written under "
                f"{settings.build_dir / 'requests'}; nothing was sent"
            )
            return 0
        if not args.yes_spend:
            print(f"SPEND_NOT_CONFIRMED: {_SPEND_REFUSED}", file=sys.stderr)
            return 2
        if args.max_total_usd is None:
            print(
                "cần đặt --max-total-usd: mỗi lượt chạy toàn bộ phải có mức chi tối đa do bạn "
                "chọn / --max-total-usd is required on every full run (no default). "
                "Nothing was sent.",
                file=sys.stderr,
            )
            return 2
        now = utc_now()
        full.close_stale_rows(engine, to_iso(now), to_iso(now - STALE_AFTER))
        if full.active_run(engine) is not None:
            print(
                "RUN_IN_PROGRESS: Đang có một lượt chạy khác / another build run is in "
                "progress. Nothing was sent.",
                file=sys.stderr,
            )
            return 2
        client = _spend_client(args, settings, True)
        report = full.run_full(
            engine, settings, plan, client, max_total_usd=args.max_total_usd, out=print
        )
        for line in full.describe(report):
            print(line)
        if report.failed_pages:
            print(
                f"Cảnh báo / Warning: {len(report.failed_pages)} trang lỗi / failed page(s) "
                "(re-run `hoctap build full` to retry):",
                file=sys.stderr,
            )
            for line in full.describe_failures(report):
                print(line, file=sys.stderr)
        return full.exit_code(report)

    try:
        return _open_db(body)
    except KeyboardInterrupt:
        print(
            "Đã dừng; các trang đã xong được giữ lại / Interrupted; finished pages are kept, "
            "re-run to continue.",
            file=sys.stderr,
        )
        return 130
    except PilotError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (RuntimeError, ValueError) as exc:
        print(f"Lỗi / Error: {exc}", file=sys.stderr)
        return 1


def _spend_flags(command: argparse.ArgumentParser) -> None:
    command.add_argument("--book", required=True, help="book_id, e.g. toan1-2020-q1")
    command.add_argument("--pages", required=True, help="1-based page range a-b, e.g. 5-7")
    mode = command.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="write the requests; send nothing")
    mode.add_argument(
        "--yes-spend", action="store_true", help="allow calls to Claude (costs money)"
    )
    command.add_argument(
        "--max-total-usd",
        type=_positive_usd,
        help="stop starting new pages once this run has spent this much "
        "(default from config: extraction_max_total_usd)",
    )


def _speak_flags(command: argparse.ArgumentParser) -> None:
    """Like `_spend_flags`, but `speak-missing` has no `--book`/`--pages`: it scans every
    currently-referenced key across all published content."""
    mode = command.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report what would be synthesised")
    mode.add_argument(
        "--yes-spend",
        action="store_true",
        help="allow calls to the cloud TTS engine (costs money; not needed for edge-tts)",
    )
    command.add_argument(
        "--max-total-usd",
        type=_positive_usd,
        help="stop starting new syntheses once this run has spent this much "
        "(default from config: tts_max_total_usd)",
    )


def _reset_pin(_args: argparse.Namespace) -> int:
    """Forgotten PIN: sets a new one on the host, no old PIN and no running server needed."""
    import getpass

    from pydantic import TypeAdapter, ValidationError
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.api.errors import AppError
    from hoctap.db.engine import create_db_engine, run_migrations
    from hoctap.ids import utc_now
    from hoctap.parent import service
    from hoctap.parent.schemas import Pin

    settings = load_settings()
    pin = getpass.getpass("Mã PIN mới (4 chữ số) / New PIN (4 digits): ")
    try:
        TypeAdapter(Pin).validate_python(pin)
    except ValidationError:
        print("Mã PIN phải gồm đúng 4 chữ số / The PIN must be exactly 4 digits.", file=sys.stderr)
        return 2
    if getpass.getpass("Nhập lại mã PIN / Repeat the PIN: ") != pin:
        print("Hai mã PIN không khớp / The PINs do not match.", file=sys.stderr)
        return 2
    try:
        engine = create_db_engine(settings.db_path)
        try:
            run_migrations(engine)
            service.reset_pin(engine, pin, utc_now())
        finally:
            engine.dispose()
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except (SQLAlchemyError, OSError) as exc:
        print(f"Lỗi / Error at {settings.db_path}: {exc}", file=sys.stderr)
        return 1
    print("Đã đặt lại mã PIN; mọi phiên phụ huynh đang mở đã bị đăng xuất / PIN reset.")
    return 0


def _port_listening(host: str, port: int) -> bool:
    import socket

    probe = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with socket.create_connection((probe, port), timeout=1):
            return True
    except OSError:
        return False


def _backup(args: argparse.Namespace) -> int:
    """Writes a verified single-file backup while the app may keep running."""
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.api.errors import AppError
    from hoctap.db.engine import create_db_engine
    from hoctap.parent.backup import backup_filename, make_backup

    settings = load_settings()
    if not settings.db_path.is_file():
        print(f"Không có cơ sở dữ liệu / No database at {settings.db_path}.", file=sys.stderr)
        return 1
    target = (
        Path(args.to).expanduser() if args.to else settings.data_dir.parent / "hoctap-backups"
    ).resolve()
    inside = target == settings.data_dir.resolve() or settings.data_dir.resolve() in target.parents
    if inside:
        print(
            "Cảnh báo / Warning: thư mục này nằm trong thư mục dữ liệu; hãy giữ một bản ở nơi "
            "khác / this folder is inside the data folder; keep a copy somewhere else too.",
            file=sys.stderr,
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(settings.db_path)
        try:
            path = make_backup(engine, target / backup_filename())
        finally:
            engine.dispose()
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except (SQLAlchemyError, OSError) as exc:
        print(f"Lỗi / Error: {exc}", file=sys.stderr)
        return 1
    print(f"Đã sao lưu / Backup written: {path}")
    print("Tệp chứa mã PIN đã băm, hãy giữ riêng tư / It holds the PIN hash; keep it private.")
    return 0


def _restore(args: argparse.Namespace) -> int:
    """Offline restore: refuses while the server runs or a build is active."""
    from types import SimpleNamespace

    from hoctap.api.errors import AppError
    from hoctap.builder import jobs
    from hoctap.db.engine import create_db_engine, run_migrations
    from hoctap.parent.auth import load_or_create_secret
    from hoctap.parent.backup import CONFIRM_PHRASE, Maintenance, restore

    settings = load_settings()
    source = Path(args.file).expanduser()
    if not source.is_file():
        print(f"Không thấy tệp / File not found: {source}", file=sys.stderr)
        return 1
    for port in {settings.port, settings.tls_port}:
        if _port_listening(settings.host, port):
            print(
                f"Máy chủ đang chạy trên cổng {port}; hãy dừng nó trước khi khôi phục / the "
                "server is running; stop it before restoring. Nothing was changed.",
                file=sys.stderr,
            )
            return 1
    if args.yes:
        typed = CONFIRM_PHRASE
    else:
        typed = input(f"Gõ {CONFIRM_PHRASE} để ghi đè dữ liệu hiện tại / type it to overwrite: ")
    if typed.strip().upper() != CONFIRM_PHRASE:
        print("Chưa xác nhận, không đổi gì / Not confirmed; nothing changed.", file=sys.stderr)
        return 2
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(settings.db_path)
        try:
            run_migrations(engine)
            app = SimpleNamespace()
            app.state = SimpleNamespace(
                settings=settings,
                engine=engine,
                maintenance=Maintenance(),
                restore_lock=threading.Lock(),
                secret_key=load_or_create_secret(settings.data_dir),
                run_manager=jobs.RunManager(engine, settings, jobs.default_client_factory),
            )
            result = restore(app, source, own_requests=0)  # type: ignore[arg-type]
        finally:
            engine.dispose()
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    print(f"Đã khôi phục / Restored (revision {result.revision}).")
    print(f"Bản sao lưu an toàn / Safety backup: {result.safety_backup}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hoctap", description="Học Tập server")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web server")
    serve.add_argument("--host", help="bind address (default from config: 127.0.0.1)")
    serve.add_argument("--port", type=int, help="port (default from config: 8000)")
    serve.set_defaults(func=_serve)

    certs = sub.add_parser(
        "certs", help="generate an mkcert-signed certificate for the PC's LAN IP"
    )
    certs.add_argument("--ip", required=True, help="the PC's LAN IPv4 address")
    certs.add_argument("--hostname", help="an extra hostname to include in the certificate")
    certs.add_argument(
        "--force", action="store_true", help="overwrite an existing cert.pem/key.pem"
    )
    certs.set_defaults(func=_certs_cmd)

    install_windows = sub.add_parser(
        "install-windows",
        help="add a Windows Firewall rule for the TLS port (prints it and does nothing elsewhere)",
    )
    install_windows.set_defaults(func=_install_windows_cmd)

    reset_pin = sub.add_parser(
        "reset-pin", help="forgotten PIN: set a new one on this machine (prompts for it)"
    )
    reset_pin.set_defaults(func=_reset_pin)

    backup_cmd = sub.add_parser("backup", help="write a verified single-file database backup")
    backup_cmd.add_argument(
        "--to", help="folder for the backup (default: 'hoctap-backups' next to the data folder)"
    )
    backup_cmd.set_defaults(func=_backup)

    restore_cmd = sub.add_parser(
        "restore", help="replace the database with a backup (server must be stopped)"
    )
    restore_cmd.add_argument("file", help="the .db backup file")
    restore_cmd.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    restore_cmd.set_defaults(func=_restore)

    export = sub.add_parser("export-openapi", help="write the OpenAPI schema for gen:api")
    export.add_argument("--out", default=str(DEFAULT_OPENAPI_OUT), help="output file")
    export.set_defaults(func=_export_openapi)

    schema = sub.add_parser("export-schema", help="write the ProblemDoc v1 JSON Schema")
    schema.add_argument("--out", default=str(DEFAULT_SCHEMA_OUT), help="output file")
    schema.set_defaults(func=_export_schema)

    extraction = sub.add_parser(
        "export-extraction-schema", help="write the page extraction schema sent to Claude"
    )
    extraction.add_argument("--out", default=str(DEFAULT_EXTRACTION_SCHEMA_OUT), help="output file")
    extraction.set_defaults(func=_export_extraction_schema)

    verify_schema = sub.add_parser(
        "export-verify-schema", help="write the verify page schema sent to Claude"
    )
    verify_schema.add_argument("--out", default=str(DEFAULT_VERIFY_SCHEMA_OUT), help="output file")
    verify_schema.set_defaults(func=_export_verify_schema)

    build = sub.add_parser("build", help="content build pipeline")
    build_sub = build.add_subparsers(dest="build_command", required=True)
    catalogue = build_sub.add_parser(
        "catalogue", help="check the source PDFs and upsert the book catalogue"
    )
    catalogue.set_defaults(func=_build_catalogue)
    pilot = build_sub.add_parser(
        "pilot",
        help="render, extract (Claude), validate, verify (Claude), crop and publish a page range "
        "of one book",
    )
    _spend_flags(pilot)
    pilot.add_argument(
        "--no-verify", action="store_true", help="stop after validate (no verify calls)"
    )
    pilot.add_argument("--no-publish", action="store_true", help="stop before crop and publish")
    pilot.set_defaults(func=_build_pilot)
    verify = build_sub.add_parser(
        "verify",
        help="verify the Answer Keys of validated pages with an independent second answer",
    )
    _spend_flags(verify)
    verify.set_defaults(func=_build_verify)
    publish = build_sub.add_parser(
        "publish",
        help="crop and publish the validated problems of a page range (no Claude call)",
    )
    publish.add_argument("--book", required=True, help="book_id, e.g. toan1-2020-q1")
    publish.add_argument("--pages", required=True, help="1-based page range a-b, e.g. 5-7")
    publish.set_defaults(func=_build_publish)
    guides_cmd = build_sub.add_parser(
        "guides",
        help="generate the Concept Guide of every curated Concept with Claude (costs money)",
    )
    guides_cmd.add_argument("--concept", help="only this concept_id, e.g. g1.so-sanh-so")
    guides_mode = guides_cmd.add_mutually_exclusive_group()
    guides_mode.add_argument("--dry-run", action="store_true", help="write the requests only")
    guides_mode.add_argument(
        "--yes-spend", action="store_true", help="allow calls to Claude (costs money)"
    )
    guides_cmd.add_argument(
        "--max-total-usd",
        type=_positive_usd,
        help="stop starting new Concepts once this run has spent this much "
        "(default from config: extraction_max_total_usd)",
    )
    guides_cmd.set_defaults(func=_build_guides)
    speak_missing = build_sub.add_parser(
        "speak-missing",
        help="synthesise the Vietnamese audio of every currently-referenced speech key that "
        "is missing (Problems, Concept Guides once they have text, and the UI phrase catalogue)",
    )
    _speak_flags(speak_missing)
    speak_missing.set_defaults(func=_build_speak_missing)
    gate_cmd = build_sub.add_parser(
        "gate", help="the go/no-go report: pilot quality and cost against the thresholds"
    )
    gate_cmd.set_defaults(func=_build_gate)
    full = build_sub.add_parser(
        "full",
        help="the full-corpus run, Book by Book (needs the approved go/no-go gate: exit 3 "
        "without it; costs money: needs --yes-spend and --max-total-usd; exit 4 when the cap "
        "stops it)",
    )
    full_mode = full.add_mutually_exclusive_group()
    full_mode.add_argument(
        "--dry-run", action="store_true", help="write the requests; send nothing"
    )
    full_mode.add_argument(
        "--yes-spend", action="store_true", help="allow calls to Claude (costs money)"
    )
    full.add_argument(
        "--max-total-usd",
        type=_positive_usd,
        help="REQUIRED with --yes-spend: the overall cap over all Books (no default)",
    )
    full.add_argument("--grade", type=int, choices=range(1, 6), help="only this grade (1-5)")
    full.add_argument("--books", help="only these book_ids (comma-separated)")
    full.set_defaults(func=_build_full)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
