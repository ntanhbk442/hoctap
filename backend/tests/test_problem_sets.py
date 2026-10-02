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
from hoctap.content.review.models import content_review_concepts, content_review_problem_concepts
from hoctap.db.engine import run_migrations
from hoctap.learning.problem_sets import (
    ExamBookUnitScope,
    ExamConceptScope,
    ExamGradeScope,
    ExamRef,
    LessonRef,
    UnsupportedProblemSetRef,
    ref_key,
    resolve,
)
from hoctap.parent.models import parent_profiles

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


CONCEPT_A = "g1.so-sanh-so"
CONCEPT_B = "g1.cong-tru"


def make_unit_doc(unit_key: str, lesson_key: str, label: str) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=f"{BOOK}.{unit_key}.{lesson_key}.{label}",
        book_id=BOOK,
        unit_key=unit_key,
        lesson_key=lesson_key,
        problem_label=label,
        display_label=f"Bài {label}",
        concept_ids=[],
        concept_proposals=[],
    )
    return doc


def _publish_unit(engine: Engine, unit_key: str, lesson_key: str, *docs: dict[str, Any]) -> None:
    with engine.begin() as conn:
        upsert_books(
            conn, [BookRow(BOOK, "2020", 1, 1, "Toán 1 – 2020", f"{BOOK}.pdf", 10, 1, "f")]
        )
        publish_problems(
            conn,
            BOOK,
            units=[UnitRow(BOOK, unit_key, unit_key, "", 500)],
            lessons=[LessonRow(BOOK, unit_key, lesson_key, lesson_key, "", 501)],
            problems=[
                ProblemInput(
                    doc=d, position=i, needs_review=False, verify_status="agree", duplicate=False
                )
                for i, d in enumerate(docs)
            ],
        )
        review.record_concept_proposals(conn, 1, {d["problem_id"]: [] for d in docs})


def _make_profile(engine: Engine, grade: int = 1) -> str:
    with engine.begin() as conn:
        conn.execute(
            parent_profiles.insert().values(
                id="p1", name="Bin", avatar="cat", grade=grade, created_at="2026-10-02"
            )
        )
    return "p1"


def _link_concept(engine: Engine, concept_id: str, problem_ids: list[str]) -> None:
    with engine.begin() as conn:
        exists = conn.execute(
            content_review_concepts.select().where(
                content_review_concepts.c.concept_id == concept_id
            )
        ).first()
        if exists is None:
            conn.execute(
                content_review_concepts.insert().values(
                    concept_id=concept_id, grade=1, name_vi=concept_id, created_at="2026-10-02"
                )
            )
        conn.execute(
            content_review_problem_concepts.insert(),
            [{"problem_id": pid, "concept_id": concept_id} for pid in problem_ids],
        )


# --- Story 8.1: `kind: "exam"` -----------------------------------------------------


def test_resolve_exam_book_unit_whole_book(engine: Engine) -> None:
    docs_a = [make_unit_doc("u1", "l1", f"a{i}") for i in range(3)]
    docs_b = [make_unit_doc("u2", "l1", f"b{i}") for i in range(3)]
    _publish_unit(engine, "u1", "l1", *docs_a)
    _publish_unit(engine, "u2", "l1", *docs_b)
    profile_id = _make_profile(engine)
    ref = ExamRef(
        scope=ExamBookUnitScope(book_id=BOOK, unit_keys=None), count=100, time_limit_s=600
    )
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    all_ids = {d["problem_id"] for d in docs_a + docs_b}
    assert set(ids) == all_ids  # count (100) > pool (6): the WHOLE eligible pool, no error
    assert len(ids) == len(all_ids)


def test_resolve_exam_book_unit_bounded(engine: Engine) -> None:
    docs_a = [make_unit_doc("u1", "l1", f"a{i}") for i in range(3)]
    docs_b = [make_unit_doc("u2", "l1", f"b{i}") for i in range(3)]
    _publish_unit(engine, "u1", "l1", *docs_a)
    _publish_unit(engine, "u2", "l1", *docs_b)
    profile_id = _make_profile(engine)
    ref = ExamRef(
        scope=ExamBookUnitScope(book_id=BOOK, unit_keys=["u1"]), count=100, time_limit_s=600
    )
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert set(ids) == {d["problem_id"] for d in docs_a}


def test_resolve_exam_concept_scope_multiple_concepts(engine: Engine) -> None:
    docs_a = [make_unit_doc("u1", "l1", f"a{i}") for i in range(2)]
    docs_b = [make_unit_doc("u2", "l1", f"b{i}") for i in range(2)]
    _publish_unit(engine, "u1", "l1", *docs_a)
    _publish_unit(engine, "u2", "l1", *docs_b)
    _link_concept(engine, CONCEPT_A, [d["problem_id"] for d in docs_a])
    _link_concept(engine, CONCEPT_B, [d["problem_id"] for d in docs_b])
    profile_id = _make_profile(engine)
    ref = ExamRef(
        scope=ExamConceptScope(concept_ids=[CONCEPT_A, CONCEPT_B]), count=100, time_limit_s=600
    )
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert set(ids) == {d["problem_id"] for d in docs_a + docs_b}


def test_resolve_exam_concept_scope_ignores_unknown_concept_id(engine: Engine) -> None:
    docs_a = [make_unit_doc("u1", "l1", "a0")]
    _publish_unit(engine, "u1", "l1", *docs_a)
    _link_concept(engine, CONCEPT_A, [d["problem_id"] for d in docs_a])
    profile_id = _make_profile(engine)
    ref = ExamRef(
        scope=ExamConceptScope(concept_ids=[CONCEPT_A, "no-such-concept"]),
        count=100,
        time_limit_s=600,
    )
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert ids == [docs_a[0]["problem_id"]]


def test_resolve_exam_grade_scope_spans_every_book_of_the_grade(engine: Engine) -> None:
    docs = [make_unit_doc("u1", "l1", f"a{i}") for i in range(4)]
    _publish_unit(engine, "u1", "l1", *docs)
    profile_id = _make_profile(engine, grade=1)
    ref = ExamRef(scope=ExamGradeScope(), count=100, time_limit_s=600)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert set(ids) == {d["problem_id"] for d in docs}


def test_resolve_exam_grade_scope_excludes_other_grades(engine: Engine) -> None:
    docs = [make_unit_doc("u1", "l1", "a0")]
    _publish_unit(engine, "u1", "l1", *docs)
    profile_id = _make_profile(engine, grade=2)  # Profile is grade 2; Book is grade 1
    ref = ExamRef(scope=ExamGradeScope(), count=100, time_limit_s=600)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert ids == []


def test_resolve_exam_truncates_to_count(engine: Engine) -> None:
    docs = [make_unit_doc("u1", "l1", f"a{i}") for i in range(10)]
    _publish_unit(engine, "u1", "l1", *docs)
    profile_id = _make_profile(engine)
    ref = ExamRef(scope=ExamBookUnitScope(book_id=BOOK, unit_keys=None), count=3, time_limit_s=600)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    all_ids = {d["problem_id"] for d in docs}
    assert len(ids) == 3
    assert set(ids) <= all_ids
    assert len(set(ids)) == 3  # no duplicates


def test_resolve_exam_excludes_hidden_problems(engine: Engine) -> None:
    docs = [make_unit_doc("u1", "l1", f"a{i}") for i in range(3)]
    _publish_unit(engine, "u1", "l1", *docs)
    with engine.begin() as conn:
        review.set_hidden(conn, docs[0]["problem_id"], True)
    profile_id = _make_profile(engine)
    ref = ExamRef(
        scope=ExamBookUnitScope(book_id=BOOK, unit_keys=None), count=100, time_limit_s=600
    )
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert docs[0]["problem_id"] not in ids
    assert set(ids) == {d["problem_id"] for d in docs[1:]}


def test_resolve_exam_empty_scope_returns_empty_not_error(engine: Engine) -> None:
    profile_id = _make_profile(engine)
    ref = ExamRef(scope=ExamGradeScope(), count=10, time_limit_s=600)
    with engine.connect() as conn:
        ids = resolve(conn, ref, profile_id=profile_id)
    assert ids == []


def test_exam_ref_key_is_deterministic_json() -> None:
    ref1 = ExamRef(
        scope=ExamConceptScope(concept_ids=["a", "b"]), count=10, time_limit_s=600
    )
    ref2 = ExamRef(
        scope=ExamConceptScope(concept_ids=["a", "b"]), count=10, time_limit_s=600
    )
    assert ref_key(ref1) == ref_key(ref2)
    assert ref_key(ref1).startswith("exam:")
    decoded = json.loads(ref_key(ref1)[len("exam:") :])
    assert decoded == {
        "scope": {"kind": "concept", "concept_ids": ["a", "b"]},
        "count": 10,
        "time_limit_s": 600,
    }


def test_resolve_unknown_kind_raises_clear_not_supported() -> None:
    ref = LessonRef.__new__(LessonRef)
    object.__setattr__(ref, "book_id", "")
    object.__setattr__(ref, "unit_key", "")
    object.__setattr__(ref, "lesson_key", "")
    object.__setattr__(ref, "kind", "bogus")
    with pytest.raises(UnsupportedProblemSetRef, match="bogus"):
        resolve(None, ref, profile_id="whoever")  # type: ignore[arg-type]
