"""`guides`: one Concept Guide per curated Concept (Story 5.1).

Per Concept, one Claude call gets the Concept's name and Grade, the worked examples and
theory boxes that page extraction stored for the pages of its Problems (`source='book'`),
and up to 3 of its Problems (child text only: instruction and prompts, never an answer
key). A Concept whose pages have no worked example is drafted from the sample Problems
alone (`source='problems'`). The output is a `ConceptGuideDoc` (explanation plus one worked
example, Vietnamese, length-capped), stored by `content.catalog.service.upsert_concept_guide`.

The calls, retries, cost records and the total budget cap are `builder.calls.run_calls`;
the job ref is `guide:{concept_id}` and the job is `run_kind='full'` (the pilot gate never
counts it). `input_hash` = sha256 of the model, prompt version, system prompt, output
schema and the Concept's inputs, so an unchanged input makes no call. Nothing here touches
Anh's overrides or approvals: a regenerated text only makes the Guide unapproved (its
approval is by effective hash) and flags a stale override as a conflict.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, select

from hoctap.builder import jobs_store
from hoctap.builder.calls import CallJob, CallReport, run_calls
from hoctap.builder.claude_client import ClaudeClient, PageRequest, cli_argv
from hoctap.builder.models import build_jobs
from hoctap.config import Settings
from hoctap.content import effective
from hoctap.content.catalog import service as catalog
from hoctap.content.review.models import content_review_concepts, content_review_problem_concepts
from hoctap.content.schema import (
    GUIDE_ANSWER_MAX,
    GUIDE_EXPLANATION_MAX,
    GUIDE_STEPS_MAX,
    ConceptGuideDoc,
)
from hoctap.ids import utc_now

STAGE = "guide"
PROMPT_VERSION = "guide-v1"
RUN_KIND = "full"

MAX_EXAMPLES = 6
MAX_EXAMPLE_CHARS = 1200
MAX_SAMPLE_PROBLEMS = 3
MAX_PROBLEM_CHARS = 400

SYSTEM_PROMPT = f"""Bạn viết "Hướng dẫn khái niệm" cho ứng dụng học Toán tiểu học bằng tiếng Việt.
Bạn nhận tên khái niệm, lớp, các ví dụ/khung lý thuyết trong sách (nếu có) và vài bài tập mẫu.
Hãy viết đúng MỘT hướng dẫn gồm:
- explanation: lời giải thích ngắn, dễ hiểu, đúng trình độ của lớp đó, tối đa khoảng 280 ký tự.
- example: một ví dụ có lời giải: question (đề), steps (tối đa {GUIDE_STEPS_MAX} bước, mỗi bước
  một câu ngắn), answer (kết quả ngắn, tối đa {GUIDE_ANSWER_MAX} ký tự).
Quy tắc: tiếng Việt có dấu, chuẩn NFC; giọng tích cực, thân thiện; nếu có ví dụ trong sách thì
bám theo ví dụ đó; không chép đáp án của các bài tập mẫu; chỉ dùng ký hiệu toán đơn giản
(+, -, ×, ÷, <, >, =, \\overline{{ab}}, \\frac{{a}}{{b}}); không dùng markdown; nội dung phải vừa
một màn hình máy tính bảng (giải thích không quá {GUIDE_EXPLANATION_MAX} ký tự)."""


def guide_schema() -> dict[str, Any]:
    """The `--json-schema` of one Guide (the length caps are in the prompt and checked
    after the call)."""
    text = {"type": "string"}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "explanation": text,
            "example": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": text,
                    "steps": {"type": "array", "items": text},
                    "answer": text,
                },
                "required": ["question", "steps", "answer"],
            },
        },
        "required": ["explanation", "example"],
    }


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class GuideTask:
    concept_id: str
    grade: int
    name_vi: str
    examples: tuple[tuple[str, str], ...]  # (title, text) of the book's worked examples
    problems: tuple[str, ...]  # child text of up to 3 sample Problems

    @property
    def ref(self) -> str:
        return f"guide:{self.concept_id}"

    @property
    def source(self) -> str:
        return "book" if self.examples else "problems"


def _problem_text(doc: Any) -> str:
    parts = [doc.instruction, *(p.prompt for p in doc.parts)]
    return " | ".join(p for p in parts if p)[:MAX_PROBLEM_CHARS]


def _stored_examples(conn: Connection, refs: list[str]) -> list[tuple[str, str]]:
    """The worked examples of the latest done extract job of each page, in page order."""
    t = build_jobs
    latest: dict[str, Any] = {}
    for row in conn.execute(
        select(t.c.page_ref, t.c.output_json)
        .where(t.c.stage == "extract", t.c.status == "done", t.c.page_ref.in_(refs))
        .order_by(t.c.updated_at)
    ):
        latest[row.page_ref] = row.output_json
    out: list[tuple[str, str]] = []
    for ref in sorted(latest):
        try:
            data = json.loads(latest[ref])
        except TypeError, ValueError:
            continue
        for item in data.get("worked_examples", []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and str(item.get("text", "")).strip():
                out.append((str(item.get("title", "")), str(item["text"])[:MAX_EXAMPLE_CHARS]))
    return list(dict.fromkeys(out))[:MAX_EXAMPLES]


def load_tasks(conn: Connection, concept_id: str | None = None) -> list[GuideTask]:
    """One task per curated Concept that has active Problems (or just `concept_id`)."""
    c, pc = content_review_concepts, content_review_problem_concepts
    query = select(c).order_by(c.c.grade, c.c.concept_id)
    if concept_id is not None:
        query = query.where(c.c.concept_id == concept_id)
    tasks: list[GuideTask] = []
    for concept in conn.execute(query).all():
        ids = [
            r[0]
            for r in conn.execute(
                select(pc.c.problem_id).where(pc.c.concept_id == concept.concept_id)
            )
        ]
        states = [
            s
            for s in effective.load_effective(conn, ids, include_retired=False)
            if s.doc is not None
        ]
        if not states:
            continue
        refs = sorted(
            {
                jobs_store.page_ref(s.book_id, min(p.page for p in s.doc.source_pages))
                for s in states
                if s.doc
            }
        )
        samples = tuple(_problem_text(s.doc) for s in states[:MAX_SAMPLE_PROBLEMS] if s.doc)
        tasks.append(
            GuideTask(
                concept.concept_id,
                concept.grade,
                concept.name_vi,
                tuple(_stored_examples(conn, refs)),
                samples,
            )
        )
    return tasks


def input_hash(task: GuideTask, settings: Settings) -> str:
    return _sha(
        {
            "model": settings.extraction_model,
            "prompt_version": PROMPT_VERSION,
            "system": _sha(SYSTEM_PROMPT),
            "schema": _sha(guide_schema()),
            "concept_id": task.concept_id,
            "grade": task.grade,
            "name": task.name_vi,
            "examples": task.examples,
            "problems": task.problems,
        }
    )


def guide_prompt(task: GuideTask) -> str:
    lines = [f"Khái niệm: {task.name_vi} (mã {task.concept_id}), Toán lớp {task.grade}.", ""]
    if task.examples:
        lines.append("Ví dụ và khung lý thuyết trong sách:")
        for title, text in task.examples:
            lines.append(f"- {title + ': ' if title else ''}{text}")
    else:
        lines.append("Sách không có ví dụ hay khung lý thuyết cho khái niệm này.")
    lines += ["", "Một vài bài tập mẫu (không chép đáp án):"]
    lines += [f"- {p}" for p in task.problems]
    lines += ["", "Hãy viết hướng dẫn cho khái niệm này."]
    return "\n".join(lines)


def build_request(task: GuideTask, settings: Settings, add_dir: Path) -> PageRequest:
    return PageRequest(
        page_ref=task.ref,
        prompt=guide_prompt(task),
        system_prompt=SYSTEM_PROMPT,
        schema=guide_schema(),
        model=settings.extraction_model,
        add_dir=add_dir,
        max_budget_usd=settings.extraction_max_budget_usd,
        timeout_seconds=settings.extraction_timeout_seconds,
        stage=STAGE,
    )


def check_output(output: dict[str, Any] | None) -> str | None:
    """Why the output is not a usable Guide (schema or length caps), or None."""
    try:
        ConceptGuideDoc.model_validate(output)
    except ValidationError as exc:
        return f"output is not a valid Guide: {exc.errors(include_url=False)[0]['msg']} " + (
            f"({exc.error_count()} error(s))"
        )
    return None


@dataclass
class GuideReport:
    generated: list[str] = field(default_factory=list)  # concept ids stored now
    skipped: list[str] = field(default_factory=list)  # same input: no call
    failed: dict[str, str] = field(default_factory=dict)
    drafted_from_problems: list[str] = field(default_factory=list)  # generated, no book material
    requests_written: list[Path] = field(default_factory=list)
    calls: CallReport | None = None


def request_dir(settings: Settings) -> Path:
    return settings.build_dir / "requests" / "guides"


def _write_request(
    folder: Path, task: GuideTask, digest: str, request: PageRequest, exe: str
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{task.concept_id}.json"
    path.write_text(
        json.dumps(
            {"page_ref": task.ref, "input_hash": digest, "argv": cli_argv(exe, request)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / f"{task.concept_id}.prompt.txt").write_text(request.prompt + "\n", encoding="utf-8")
    return path


def pending(
    engine: Engine, tasks: list[GuideTask], settings: Settings
) -> tuple[list[tuple[GuideTask, str]], list[GuideTask], list[tuple[GuideTask, str]]]:
    """(to call, up to date, to restore from a done job without a call)."""
    todo: list[tuple[GuideTask, str]] = []
    current: list[GuideTask] = []
    restore: list[tuple[GuideTask, str]] = []
    with engine.connect() as conn:
        stored = catalog.guide_input_hashes(conn)
        for task in tasks:
            digest = input_hash(task, settings)
            if stored.get(task.concept_id) == digest:
                current.append(task)
            elif jobs_store.find_done(conn, task.ref, STAGE, digest) is not None:
                restore.append((task, digest))
            else:
                todo.append((task, digest))
    return todo, current, restore


def _store(engine: Engine, task: GuideTask, digest: str, settings: Settings) -> bool:
    """Stores the Guide of a done job; False when there is none or it is invalid."""
    with engine.begin() as conn:
        job = jobs_store.find_done(conn, task.ref, STAGE, digest)
        if job is None or check_output(job.output) is not None:
            return False
        body = ConceptGuideDoc.model_validate(job.output).model_dump(mode="json")
        catalog.upsert_concept_guide(
            conn,
            task.concept_id,
            body,
            source=task.source,
            input_hash=digest,
            model=settings.extraction_model,
            now=utc_now(),
        )
    return True


def run_guides(
    engine: Engine,
    client: ClaudeClient | None,
    settings: Settings,
    tasks: list[GuideTask],
    *,
    dry_run: bool = False,
    max_total_usd: float | None = None,
    on_page: Callable[[str, str], None] = lambda ref, status: None,
) -> GuideReport:
    """Dry run: writes the requests, sends nothing, stores nothing. Otherwise calls Claude
    for the Concepts whose input changed and stores each valid Guide."""
    report = GuideReport()
    todo, current, restore = pending(engine, tasks, settings)
    report.skipped = [t.concept_id for t in current]
    with tempfile.TemporaryDirectory(prefix="hoctap-guides-") as tmp:
        add_dir = Path(tmp).resolve()  # text-only calls: an empty folder to read
        if dry_run:
            for task, digest in todo:
                report.requests_written.append(
                    _write_request(
                        request_dir(settings),
                        task,
                        digest,
                        build_request(task, settings, add_dir),
                        settings.claude_executable,
                    )
                )
            return report
        by_ref = {task.ref: (task, digest) for task, digest in [*todo, *restore]}
        for task, digest in restore:
            if _store(engine, task, digest, settings):
                report.generated.append(task.concept_id)
        if todo:
            if client is None:
                raise RuntimeError("Claude client missing: re-run with --yes-spend")
            jobs = [
                CallJob(
                    task.ref,
                    STAGE,
                    digest,
                    build_request(task, settings, add_dir),
                    check_output,
                    RUN_KIND,
                )
                for task, digest in todo
            ]
            report.calls = run_calls(engine, client, jobs, settings, on_page, max_total_usd)
            report.failed = {
                by_ref[ref][0].concept_id: error for ref, error in report.calls.failed.items()
            }
            for ref in report.calls.done:
                task, digest = by_ref[ref]
                if _store(engine, task, digest, settings):
                    report.generated.append(task.concept_id)
                else:
                    report.failed[task.concept_id] = "stored output is not a valid Guide"
    report.generated.sort()
    report.drafted_from_problems = sorted(
        task.concept_id
        for task in tasks
        if task.concept_id in report.generated and task.source == "problems"
    )
    return report
