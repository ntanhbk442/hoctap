"""Story 2.4: `learning.problem_sets.resolve()` -- the only definition of "the Problems in
a set". For `kind: lesson` it must delegate to the same ordering
`content.library.lesson_problems()`/`content.effective.visible_to_child()` already produce.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    UnitRow,
    publish_problems,
    upsert_books,
)
from hoctap.content.review import service as review
from hoctap.db.engine import run_migrations
from hoctap.learning.problem_sets import LessonRef, UnsupportedProblemSetRef, resolve

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-5", "tiet-2"


def make_doc(label: str) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=f"{BOOK}.{UNIT}.{LESSON}.{label}",
        book_id=BOOK,
        unit_key=UNIT,
        lesson_key=LESSON,
        problem_label=label,
        display_label=f"Bài {label}",
        concept_ids=[],
        concept_proposals=[],
    )
    return doc


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = create_engine(URL.create("sqlite", database=str(tmp_path / "t.db")))
    run_migrations(eng)
    return eng


def _publish(engine: Engine, *docs: dict[str, Any], hidden: set[str] = frozenset()) -> None:
    with engine.begin() as conn:
        upsert_books(
            conn,
            [BookRow(BOOK, "2020", 1, 1, "Toán 1 – 2020", f"{BOOK}.pdf", 10, 1, "f")],
        )
        publish_problems(
            conn,
            BOOK,
            units=[UnitRow(BOOK, UNIT, "TUẦN 5", "", 500)],
            lessons=[LessonRow(BOOK, UNIT, LESSON, "Tiết 2", "", 501)],
            problems=[
                ProblemInput(
                    doc=d,
                    position=12000 + i,
                    needs_review=False,
                    verify_status="agree",
                    duplicate=False,
                )
                for i, d in enumerate(docs)
            ],
        )
        review.record_concept_proposals(conn, 1, {d["problem_id"]: [] for d in docs})
        for problem_id in hidden:
            review.set_hidden(conn, problem_id, True)


def test_resolve_lesson_returns_ordered_visible_problem_ids(engine: Engine) -> None:
    docs = [make_doc("bai-1"), make_doc("bai-2"), make_doc("bai-3")]
    _publish(engine, *docs)
    ref = LessonRef(book_id=BOOK, unit_key=UNIT, lesson_key=LESSON)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id="whoever")
    assert ids == [d["problem_id"] for d in docs]


def test_resolve_lesson_excludes_hidden(engine: Engine) -> None:
    docs = [make_doc("bai-1"), make_doc("bai-2")]
    _publish(engine, *docs, hidden={docs[1]["problem_id"]})
    ref = LessonRef(book_id=BOOK, unit_key=UNIT, lesson_key=LESSON)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id="whoever")
    assert ids == [docs[0]["problem_id"]]


def test_resolve_unknown_lesson_is_empty(engine: Engine) -> None:
    _publish(engine, make_doc("bai-1"))
    ref = LessonRef(book_id=BOOK, unit_key="no-such-unit", lesson_key="no-such-lesson")
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id="whoever")
    assert ids == []


def test_resolve_unknown_kind_raises_clear_not_supported() -> None:
    ref = LessonRef.__new__(LessonRef)
    object.__setattr__(ref, "book_id", "")
    object.__setattr__(ref, "unit_key", "")
    object.__setattr__(ref, "lesson_key", "")
    object.__setattr__(ref, "kind", "bogus")
    with pytest.raises(UnsupportedProblemSetRef, match="bogus"):
        resolve(None, ref, profile_id="whoever")  # type: ignore[arg-type]
