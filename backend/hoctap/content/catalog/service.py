"""Catalogue services, the only writers of `content_catalog_*` (AD-2).

`upsert_books()` writes `content_catalog_books`; `publish_problems()` writes the units,
lessons and problems.

The caller owns the transaction: pass a connection from `engine.begin()`.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, insert, select, update

from hoctap.content.catalog.models import (
    content_catalog_books,
    content_catalog_lessons,
    content_catalog_problems,
    content_catalog_units,
)
from hoctap.ids import to_iso, utc_now


@dataclass(frozen=True)
class BookRow:
    """One catalogue row, without the timestamps."""

    book_id: str
    edition: str
    grade: int
    volume: int
    title_vi: str
    source_path: str
    page_count: int
    file_size: int
    fingerprint: str


_FIELDS = tuple(BookRow.__dataclass_fields__)


@dataclass
class UpsertResult:
    """The `book_id`s in each outcome.

    `orphaned`: ids in the database but not among `rows`. They are reported, never deleted.
    """

    inserted: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


def upsert_books(
    conn: Connection, rows: list[BookRow], now: datetime | None = None
) -> UpsertResult:
    """Inserts new rows and updates rows whose fields differ.

    Unchanged rows are not written, so their `updated_at` stays as it was.
    """
    stamp = to_iso(now or utc_now())
    t = content_catalog_books
    existing = {r.book_id: r for r in conn.execute(select(*(t.c[f] for f in _FIELDS))).all()}
    result = UpsertResult()
    for row in rows:
        values = asdict(row)
        old = existing.get(row.book_id)
        if old is None:
            conn.execute(insert(t).values(**values, created_at=stamp, updated_at=stamp))
            result.inserted.append(row.book_id)
        elif tuple(old) != tuple(values[f] for f in _FIELDS):
            conn.execute(
                update(t).where(t.c.book_id == row.book_id).values(**values, updated_at=stamp)
            )
            result.changed.append(row.book_id)
        else:
            result.unchanged.append(row.book_id)
    result.orphaned = sorted(set(existing) - {row.book_id for row in rows})
    return result


def list_books(conn: Connection) -> list[BookRow]:
    """All catalogue rows, ordered by edition, grade and volume."""
    t = content_catalog_books
    rows = conn.execute(
        select(*(t.c[f] for f in _FIELDS)).order_by(t.c.edition, t.c.grade, t.c.volume)
    ).all()
    return [BookRow(*r) for r in rows]


# --------------------------------------------------------------------------- problems

_QUIZ_LESSON = re.compile(r"^phieu[0-9]*$")


def is_quiz_sheet(lesson_key: str) -> bool:
    """A "Phiếu tự luyện" lesson (`phieu`, or a numbered `phieu2`)."""
    return bool(_QUIZ_LESSON.fullmatch(lesson_key))


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc(v) for v in value]
    if isinstance(value, dict):
        return {_nfc(k): _nfc(v) for k, v in value.items()}
    return value


def canonical_doc_json(doc: dict[str, Any]) -> str:
    """The stored form of a ProblemDoc: NFC, sorted keys, no insignificant whitespace."""
    return json.dumps(_nfc(doc), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_doc_json(doc).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UnitRow:
    book_id: str
    unit_key: str
    label: str
    title: str
    position: int
    insert_only: bool = False  # heading unknown: never overwrite an existing row


@dataclass(frozen=True)
class LessonRow:
    book_id: str
    unit_key: str
    lesson_key: str
    label: str
    title: str
    position: int
    insert_only: bool = False  # heading unknown: never overwrite an existing row

    @property
    def is_quiz_sheet(self) -> bool:
        return is_quiz_sheet(self.lesson_key)


@dataclass(frozen=True)
class ProblemInput:
    """One Problem to publish: the validated ProblemDoc (as JSON data) and its flags."""

    doc: dict[str, Any]
    position: int
    needs_review: bool
    verify_status: str
    duplicate: bool

    @property
    def problem_id(self) -> str:
        return self.doc["problem_id"]

    @property
    def lesson(self) -> tuple[str, str]:
        return self.doc["unit_key"], self.doc["lesson_key"]


@dataclass
class PublishResult:
    """The `problem_id`s in each outcome, and the unit/lesson keys written."""

    inserted: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)  # were retired; published again
    retired: list[str] = field(default_factory=list)
    units_written: list[str] = field(default_factory=list)
    lessons_written: list[str] = field(default_factory=list)  # "unit_key.lesson_key"

    @property
    def changed(self) -> int:
        """Problem rows written (units and lessons are counted separately)."""
        return len(self.inserted) + len(self.updated) + len(self.restored) + len(self.retired)


def _upsert(
    conn: Connection,
    table: Any,
    keys: dict[str, Any],
    values: dict[str, Any],
    insert_only: bool = False,
) -> bool:
    """Inserts, or updates when a value differs (unless `insert_only`). Returns whether a
    row was written."""
    where = [table.c[k] == v for k, v in keys.items()]
    old = conn.execute(select(*(table.c[k] for k in values)).where(*where)).first()
    if old is None:
        conn.execute(insert(table).values(**keys, **values))
        return True
    if not insert_only and tuple(old) != tuple(values.values()):
        conn.execute(update(table).where(*where).values(**values))
        return True
    return False


def publish_problems(
    conn: Connection,
    book_id: str,
    *,
    units: Iterable[UnitRow],
    lessons: Iterable[LessonRow],
    problems: Iterable[ProblemInput],
    touched_lessons: Iterable[tuple[str, str]] = (),
    touch_pages: Iterable[int] = (),
    current_pages: Iterable[int] | None = None,
    present: Iterable[str] = (),
    now: datetime | None = None,
) -> PublishResult:
    """Upserts the units, lessons and Problems of one book, then retires vanished Problems.

    - A Problem is upserted by `problem_id`. A row whose content hash, flags and position
      are unchanged (and that is not retired) is not written. Otherwise the row is updated
      and `retired_at` is cleared.
    - Retirement (AD-3) covers only the touched Lessons: the Lessons of `problems`, the
      given `touched_lessons`, and the Lessons of active Problems first found on one of
      `touch_pages`. An active Problem there that is neither published now nor in
      `present` (still extracted, but not published this time) gets `retired_at` = now,
      provided its first page is one of `current_pages` (pages whose extraction is known
      to be current; None: every page). Nothing is ever deleted.
    """
    stamp = to_iso(now or utc_now())
    result = PublishResult()
    for unit in units:
        values = {"label": unit.label, "title": unit.title, "position": unit.position}
        keys = {"book_id": book_id, "unit_key": unit.unit_key}
        if _upsert(conn, content_catalog_units, keys, values, unit.insert_only):
            result.units_written.append(unit.unit_key)
    for lesson in lessons:
        values = {
            "label": lesson.label,
            "title": lesson.title,
            "position": lesson.position,
            "is_quiz_sheet": int(lesson.is_quiz_sheet),
        }
        keys = {"book_id": book_id, "unit_key": lesson.unit_key, "lesson_key": lesson.lesson_key}
        if _upsert(conn, content_catalog_lessons, keys, values, lesson.insert_only):
            result.lessons_written.append(f"{lesson.unit_key}.{lesson.lesson_key}")

    t = content_catalog_problems
    published: set[str] = set()
    touched = set(touched_lessons)
    for problem in problems:
        if problem.doc.get("book_id") != book_id:
            raise ValueError(f"{problem.problem_id} is not a Problem of {book_id}")
        doc_json = canonical_doc_json(problem.doc)
        values = {
            "doc_json": doc_json,
            "content_hash": hashlib.sha256(doc_json.encode("utf-8")).hexdigest(),
            "needs_review": int(problem.needs_review),
            "verify_status": problem.verify_status,
            "duplicate": int(problem.duplicate),
            "position": problem.position,
            "source_page_first": min(p["page"] for p in problem.doc["source_pages"]),
        }
        compared = (
            "content_hash",
            "needs_review",
            "verify_status",
            "duplicate",
            "position",
            "source_page_first",
        )
        old = conn.execute(
            select(*(t.c[c] for c in compared), t.c.retired_at).where(
                t.c.problem_id == problem.problem_id
            )
        ).first()
        published.add(problem.problem_id)
        touched.add(problem.lesson)
        if old is None:
            conn.execute(
                insert(t).values(
                    problem_id=problem.problem_id,
                    book_id=book_id,
                    unit_key=problem.lesson[0],
                    lesson_key=problem.lesson[1],
                    retired_at=None,
                    created_at=stamp,
                    updated_at=stamp,
                    **values,
                )
            )
            result.inserted.append(problem.problem_id)
            continue
        same = tuple(old[: len(compared)]) == tuple(values[c] for c in compared)
        if same and old.retired_at is None:
            result.unchanged.append(problem.problem_id)
            continue
        conn.execute(
            update(t)
            .where(t.c.problem_id == problem.problem_id)
            .values(**values, retired_at=None, updated_at=stamp)
        )
        if old.retired_at is not None:
            result.restored.append(problem.problem_id)
        else:
            result.updated.append(problem.problem_id)

    pages = set(touch_pages)
    known = None if current_pages is None else set(current_pages)
    active = conn.execute(
        select(t.c.problem_id, t.c.unit_key, t.c.lesson_key, t.c.source_page_first).where(
            t.c.book_id == book_id, t.c.retired_at.is_(None)
        )
    ).all()
    touched |= {(r.unit_key, r.lesson_key) for r in active if r.source_page_first in pages}
    keep = published | set(present)
    for row in active:
        if known is not None and row.source_page_first not in known:
            continue
        if (row.unit_key, row.lesson_key) in touched and row.problem_id not in keep:
            conn.execute(
                update(t)
                .where(t.c.problem_id == row.problem_id)
                .values(retired_at=stamp, updated_at=stamp)
            )
            result.retired.append(row.problem_id)
    result.retired.sort()
    return result
