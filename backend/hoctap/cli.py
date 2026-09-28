"""`hoctap` command line: `serve`, `export-*` schemas and
`build catalogue|pilot|verify|publish|gate|full`."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
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


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from hoctap.app import create_app

    settings = load_settings()
    if args.host:
        settings = replace(settings, host=args.host)
    if args.port is not None:
        settings = replace(settings, port=validate_port(args.port, "--port"))

    cert_file, key_file = settings.tls_cert_file, settings.tls_key_file
    ssl_kwargs: dict[str, str] = {}
    port = settings.port
    if cert_file.is_file() and key_file.is_file():
        ssl_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}
        if args.port is None:
            port = settings.tls_port
        print(f"HTTPS bật / HTTPS is on (cert: {cert_file}); binding port {port}.")
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

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=port,
        log_level=settings.log_level.lower(),
        **ssl_kwargs,
    )
    return 0


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
    to exit codes (2: usage or input, 1: failure, 130: interrupted)."""
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.builder.pilot import PilotError, parse_pages
    from hoctap.db.engine import create_db_engine, run_migrations

    settings = load_settings()
    try:
        first, last = parse_pages(args.pages)
    except PilotError as exc:
        print(exc, file=sys.stderr)
        return 2
    try:
        engine = create_db_engine(settings.db_path)
    except OSError as exc:
        print(f"Lỗi cơ sở dữ liệu / Database error at {settings.db_path}: {exc}", file=sys.stderr)
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
            "Đã dừng; các trang đã xong được giữ lại / Interrupted; finished pages are kept, "
            "re-run to continue.",
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


def _open_db(body) -> int:  # noqa: ANN001
    """Opens the database (migrated) and runs `body(engine, settings)`; database errors
    exit 1."""
    from sqlalchemy.exc import SQLAlchemyError

    from hoctap.db.engine import create_db_engine, run_migrations

    settings = load_settings()
    try:
        engine = create_db_engine(settings.db_path)
    except OSError as exc:
        print(f"Lỗi cơ sở dữ liệu / Database error at {settings.db_path}: {exc}", file=sys.stderr)
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


def _build_full(_args: argparse.Namespace) -> int:
    """Checks the go/no-go approval (exit 3 without one), then stops: the full run itself
    is Story 6.2."""
    from hoctap.builder import gate

    def body(engine, settings) -> int:  # noqa: ANN001
        try:
            gate.require_approval(engine, settings)
        except gate.GateNotApproved as exc:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            return EXIT_GATE_NOT_APPROVED
        print("chưa triển khai (Story 6.2) / not implemented yet (Story 6.2)")
        return 0

    return _open_db(body)


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
        help="add a Windows Firewall rule for the TLS port (prints it and does nothing "
        "elsewhere)",
    )
    install_windows.set_defaults(func=_install_windows_cmd)

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
    gate_cmd = build_sub.add_parser(
        "gate", help="the go/no-go report: pilot quality and cost against the thresholds"
    )
    gate_cmd.set_defaults(func=_build_gate)
    full = build_sub.add_parser(
        "full",
        help="the full-corpus run (checks the go/no-go approval, exit 3 without it; Story 6.2)",
    )
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
