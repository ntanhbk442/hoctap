"""`hoctap build pilot`: render -> extract -> validate -> verify -> crop -> publish for a
page range of one book, `hoctap build verify` (verify only) and `hoctap build publish`
(crop and publish only; no Claude call).

`plan_pilot()` checks everything without writing (the book is in the catalogue, its file
is unchanged, the range is valid); `pending_pages()` says which pages would call Claude,
so the CLI can print the estimate and apply the spending guard before anything runs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from sqlalchemy import Engine

from hoctap.builder import costs, jobs_store
from hoctap.builder.calls import CallReport
from hoctap.builder.catalogue import fingerprint, resolve_source
from hoctap.builder.claude_client import ClaudeClient, PageRequest, cli_argv
from hoctap.builder.stages import extract, publish, render, validate
from hoctap.builder.stages import verify as verify_stage
from hoctap.config import Settings
from hoctap.content.catalog.service import BookRow, list_books

Out = Callable[[str], None]


class PilotError(Exception):
    """A usage or input problem: nothing was sent or written. Exit code 2."""


def parse_pages(spec: str) -> tuple[int, int]:
    """`"5-7"` -> (5, 7); `"5"` -> (5, 5)."""
    text = spec.strip()
    first, sep, last = text.partition("-")
    try:
        a = int(first)
        b = int(last) if sep else a
    except ValueError as exc:
        raise PilotError(
            f"--pages phải có dạng a-b, ví dụ 5-7 / --pages must look like a-b, e.g. 5-7 "
            f"(got {spec!r})"
        ) from exc
    if a > b:
        raise PilotError(f"--pages: {a} > {b}")
    return a, b


@dataclass(frozen=True)
class PilotPlan:
    book: BookRow
    pdf_path: Path
    pages: list[int]

    @property
    def context_page(self) -> int | None:
        """The page after the range, rendered only as context for continued problems."""
        nxt = self.pages[-1] + 1
        return nxt if nxt <= self.book.page_count else None


def plan_pilot(
    engine: Engine, settings: Settings, book_id: str, first: int, last: int
) -> PilotPlan:
    with engine.connect() as conn:
        books = {b.book_id: b for b in list_books(conn)}
    if not books:
        raise PilotError(
            "Danh mục sách trống; chạy `hoctap build catalogue` trước / "
            "The book catalogue is empty; run `hoctap build catalogue` first."
        )
    book = books.get(book_id)
    if book is None:
        raise PilotError(f"Không có sách / Unknown book: {book_id!r}")
    if first < 1 or last > book.page_count:
        raise PilotError(
            f"Trang ngoài phạm vi / Pages out of range: {first}-{last} "
            f"({book_id} has pages 1-{book.page_count})"
        )
    if last - first + 1 > settings.pilot_max_pages:
        raise PilotError(
            f"Quá nhiều trang / Too many pages: {last - first + 1} > pilot_max_pages "
            f"({settings.pilot_max_pages})"
        )
    res = resolve_source(settings.source_dir, book.source_path)
    if res.path is None or res.problem is not None:
        raise PilotError(
            f"Không tìm thấy tệp sách / Source file not found: {book.source_path} "
            f"under {settings.source_dir}"
        )
    _, digest = fingerprint(res.path)
    if digest != book.fingerprint:
        raise PilotError(
            f"Tệp sách đã thay đổi; chạy lại `hoctap build catalogue` / "
            f"{book.source_path} changed since the catalogue was built; "
            "run `hoctap build catalogue` again."
        )
    return PilotPlan(book, res.path, list(range(first, last + 1)))


def plan_publish(engine: Engine, book_id: str, first: int, last: int) -> PilotPlan:
    """Checks the book and the range for `build publish`; the source PDF is not needed."""
    with engine.connect() as conn:
        books = {b.book_id: b for b in list_books(conn)}
    book = books.get(book_id)
    if book is None:
        raise PilotError(f"Không có sách / Unknown book: {book_id!r}")
    if first > last:
        raise PilotError(f"--pages: {first} > {last}")
    if first < 1 or last > book.page_count:
        raise PilotError(
            f"Trang ngoài phạm vi / Pages out of range: {first}-{last} "
            f"({book_id} has pages 1-{book.page_count})"
        )
    return PilotPlan(book, Path(book.source_path), list(range(first, last + 1)))


def run_publish(engine: Engine, settings: Settings, plan: PilotPlan) -> publish.PublishReport:
    """Crops and publishes the current valid Problems of the plan's pages (no call)."""
    current = current_extract_hashes(engine, settings, plan.book)
    return publish.run_publish(engine, settings.data_dir, plan.book, plan.pages, current)


def _task(settings: Settings, book: BookRow, page: int) -> extract.PageTask:
    image = settings.data_dir / render.image_rel_path(book.book_id, page)
    nxt = page + 1 if page + 1 <= book.page_count else None
    next_image = (
        None if nxt is None else settings.data_dir / render.image_rel_path(book.book_id, nxt)
    )
    return extract.PageTask(
        book_id=book.book_id,
        page=page,
        image=image,
        image_sha=render.image_sha256(image),
        next_image=next_image,
        next_image_sha=None if next_image is None else render.image_sha256(next_image),
    )


def _tasks(plan: PilotPlan, settings: Settings) -> list[extract.PageTask]:
    return [_task(settings, plan.book, page) for page in plan.pages]


def _is_current(task: extract.PageTask) -> bool:
    """Whether the task's images are on disk (so its extract hash is exact)."""
    return task.image_sha is not None and (
        task.next_image is None or task.next_image_sha is not None
    )


def pending_pages(engine: Engine, settings: Settings, plan: PilotPlan) -> list[int]:
    """Pages whose extraction is not `done` for the current input hash (would call Claude).

    Before rendering, a page whose images are not on disk counts as pending."""
    pending = []
    with engine.connect() as conn:
        for task in _tasks(plan, settings):
            input_hash = extract.extract_input_hash(task, settings)
            done = jobs_store.find_done(conn, task.ref, extract.STAGE, input_hash)
            if not _is_current(task) or done is None:
                pending.append(task.page)
    return pending


def current_extract_hashes(engine: Engine, settings: Settings, book: BookRow) -> dict[int, str]:
    """The current extract hash of every page that was ever extracted or is rendered with
    its context page, computed from the images on disk."""
    prefix = f"{book.book_id}#p"
    with engine.connect() as conn:
        pages = {int(ref[len(prefix) :]) for ref in jobs_store.latest_done(conn, "extract", prefix)}
    folder = settings.data_dir / "assets" / "pages" / book.book_id
    if folder.is_dir():
        for path in folder.glob("p*.jpg"):
            if path.stem[1:].isdigit():
                pages.add(int(path.stem[1:]))
    current = {}
    for page in sorted(p for p in pages if 1 <= p <= book.page_count):
        task = _task(settings, book, page)
        if _is_current(task):
            current[page] = extract.extract_input_hash(task, settings)
    return current


@dataclass
class VerifyReport:
    pages: int = 0  # pages with valid Problems
    requests_written: list[Path] = field(default_factory=list)
    calls: CallReport = field(default_factory=CallReport)
    verdicts: verify_stage.VerdictReport | None = None


@dataclass
class PilotReport:
    rendered: int = 0
    requests_written: list[Path] = field(default_factory=list)
    extract: extract.ExtractReport = field(default_factory=extract.ExtractReport)
    validate: validate.ValidateReport | None = None
    verify: VerifyReport | None = None
    # Pages outside the verified range whose rows were reset by a validate rebuild and
    # that still need a verify call (`hoctap build verify`).
    verify_needed_pages: list[int] = field(default_factory=list)
    publish_report: publish.PublishReport | None = None
    book_cost_usd: float = 0.0


def request_dir(settings: Settings, book_id: str) -> Path:
    return settings.build_dir / "requests" / book_id


def verify_request_dir(settings: Settings, book_id: str) -> Path:
    return request_dir(settings, book_id) / "verify"


def _write_request(
    folder: Path, stem: str, ref: str, input_hash: str, request: PageRequest, settings: Settings
) -> Path:
    """Writes one request as it would be sent: the argv and the prompt text."""
    folder.mkdir(parents=True, exist_ok=True)
    argv = cli_argv(settings.claude_executable, request)
    path = folder / f"{stem}.json"
    path.write_text(
        json.dumps(
            {"page_ref": ref, "input_hash": input_hash, "argv": argv},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / f"{stem}.prompt.txt").write_text(request.prompt + "\n", encoding="utf-8")
    return path


def pending_verify_pages(engine: Engine, settings: Settings, plan: PilotPlan) -> list[int]:
    """Pages of the plan whose current valid Problems have no `done` verify job."""
    tasks = verify_stage.load_tasks(engine, settings, plan.book.book_id, plan.pages)
    return [task.page for task, _ in verify_stage.pending(engine, tasks, settings)]


NO_PROBLEMS_VERIFY = "verify: no valid problems on these pages (run `hoctap build pilot` first)"
NO_PROBLEMS_PILOT = "verify: these pages produced no valid problems; nothing to verify"


def run_verify(
    engine: Engine,
    settings: Settings,
    plan: PilotPlan,
    client: ClaudeClient | None,
    *,
    dry_run: bool,
    out: Out = print,
    max_total_usd: float | None = None,
    skip_pages: frozenset[int] = frozenset(),
    no_problems: str = NO_PROBLEMS_VERIFY,
) -> VerifyReport:
    """Verifies the valid Problems of the plan's pages: writes the requests (`dry_run`,
    except for `skip_pages`), or calls Claude for the pending pages and stores every
    Problem's verdict. The verdicts are stored even when the calls raise."""
    report = VerifyReport()
    book_id = plan.book.book_id
    tasks = verify_stage.load_tasks(engine, settings, book_id, plan.pages)
    report.pages = len(tasks)
    if not tasks:
        out(no_problems)
        return report
    todo = verify_stage.pending(engine, tasks, settings)
    if dry_run:
        folder = verify_request_dir(settings, book_id)
        written = [(task, h) for task, h in todo if task.page not in skip_pages]
        for task, input_hash in written:
            request = verify_stage.build_request(task, settings)
            path = _write_request(
                folder, f"p{task.page:03d}", task.ref, input_hash, request, settings
            )
            report.requests_written.append(path)
        out(f"dry run: {len(written)} verify request(s) written to {folder}; nothing was sent")
        return report
    if todo and client is None:
        raise PilotError(
            "Có trang cần kiểm tra đáp án bằng Claude; chạy lại với --yes-spend / "
            "Pages need answer verification; re-run with --yes-spend."
        )
    try:
        if todo:
            budget = settings.extraction_max_total_usd if max_total_usd is None else max_total_usd
            out(
                f"verify: {len(todo)} page(s), up to {settings.extraction_concurrency} at a "
                f"time, run budget ${budget:.2f}"
            )
            report.calls = verify_stage.run_verify(
                engine,
                client,  # type: ignore[arg-type]
                todo,
                settings,
                on_page=lambda ref, status: out(f"  {ref}: {status}"),
                max_total_usd=budget,
            )
        else:
            out("verify: nothing to call (every page already verified)")
    finally:
        # Also after a crash or Ctrl-C: the pages recorded so far get their verdicts.
        report.verdicts = verify_stage.apply_verdicts(engine, tasks, settings)
    return report


def reapply_book_verdicts(
    engine: Engine, settings: Settings, book_id: str, exclude: frozenset[int] = frozenset()
) -> list[int]:
    """After a validate rebuild: re-applies the stored verdicts of every page of the book
    with rows (no call), except `exclude`. Returns the pages that still need a verify call."""
    tasks = [t for t in verify_stage.load_tasks(engine, settings, book_id) if t.page not in exclude]
    verify_stage.apply_verdicts(engine, tasks, settings)
    return sorted(task.page for task, _ in verify_stage.pending(engine, tasks, settings))


def run_pilot(
    engine: Engine,
    settings: Settings,
    plan: PilotPlan,
    client: ClaudeClient | None,
    *,
    dry_run: bool,
    out: Out = print,
    max_total_usd: float | None = None,
    verify: bool = True,
    publish_pages: bool = True,
    on_stage: Callable[[str], None] = lambda stage: None,
) -> PilotReport:
    """Renders the range (plus the context page), then either writes the extract requests
    (`dry_run`) or extracts the pending pages, validates the range, (unless `verify` is
    false) verifies it and (unless `publish_pages` is false) crops and publishes it.
    Extract and verify share the run budget.

    `on_stage(stage)` is called just before each of render/extract/validate/verify/crop
    starts (a caller such as `builder.jobs.RunManager` uses it to report live progress);
    it defaults to a no-op, so the CLI's own behaviour is unchanged.
    """
    report = PilotReport()
    book = plan.book
    render_pages = plan.pages + ([plan.context_page] if plan.context_page else [])
    on_stage("render")
    previous = pymupdf.TOOLS.mupdf_display_errors()
    pymupdf.TOOLS.mupdf_display_errors(False)
    try:
        with pymupdf.open(plan.pdf_path, filetype="pdf") as doc:
            for page in render_pages:
                _, rendered = render.run_render(
                    engine,
                    doc,
                    settings.data_dir,
                    book.book_id,
                    book.fingerprint,
                    page,
                    settings.render_long_edge,
                )
                report.rendered += rendered
    finally:
        pymupdf.TOOLS.mupdf_display_errors(bool(previous))
    context = " (+1 context page)" if plan.context_page else ""
    out(f"render: {report.rendered} rendered, {len(render_pages)} pages{context}")

    todo_pages = set(pending_pages(engine, settings, plan))
    todo = [
        (task, extract.extract_input_hash(task, settings))
        for task in _tasks(plan, settings)
        if task.page in todo_pages and _is_current(task)
    ]
    if dry_run:
        folder = request_dir(settings, book.book_id)
        for task, input_hash in todo:
            request = extract.build_request(task, settings)
            path = _write_request(
                folder, f"p{task.page:03d}", task.ref, input_hash, request, settings
            )
            report.requests_written.append(path)
        out(f"dry run: {len(todo)} request(s) written to {folder}; nothing was sent")
        if verify:
            # Validated pages that need verification; pages about to be re-extracted are
            # verified after their extraction.
            report.verify = run_verify(
                engine,
                settings,
                plan,
                None,
                dry_run=True,
                out=out,
                skip_pages=frozenset(t.page for t, _ in todo),
                no_problems="verify: no validated problems on these pages yet",
            )
        return report

    if todo:
        if client is None:
            raise PilotError(
                "Có trang cần gọi Claude sau khi vẽ lại; chạy lại với --yes-spend / "
                "Pages need extraction after re-rendering; re-run with --yes-spend."
            )
        on_stage("extract")
        budget = settings.extraction_max_total_usd if max_total_usd is None else max_total_usd
        out(
            f"extract: {len(todo)} page(s), up to {settings.extraction_concurrency} at a time, "
            f"run budget ${budget:.2f}"
        )
        report.extract = extract.run_extract(
            engine,
            client,
            todo,
            settings,
            on_page=lambda ref, status: out(f"  {ref}: {status}"),
            max_total_usd=budget,
        )
    else:
        out("extract: nothing to do (every page already extracted)")

    on_stage("validate")
    current = current_extract_hashes(engine, settings, book)
    report.validate = validate.run_validate(engine, book.book_id, book.page_count, current)
    if not report.validate.unchanged:
        # The rebuild reset every row of the book: restore the stored verdicts (no call).
        verified_now = frozenset(plan.pages) if verify else frozenset()
        report.verify_needed_pages = reapply_book_verdicts(
            engine, settings, book.book_id, exclude=verified_now
        )
    if verify:
        on_stage("verify")
        budget = settings.extraction_max_total_usd if max_total_usd is None else max_total_usd
        report.verify = run_verify(
            engine,
            settings,
            plan,
            client,
            dry_run=False,
            out=out,
            max_total_usd=max(budget - report.extract.spent_usd, 0.0),
            no_problems=NO_PROBLEMS_PILOT,
        )
    if publish_pages:
        on_stage("crop")
        report.publish_report = run_publish(engine, settings, plan)
    with engine.connect() as conn:
        report.book_cost_usd = costs.total_cost(conn, f"{book.book_id}#p")
    return report
