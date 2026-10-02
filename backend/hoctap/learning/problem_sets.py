"""`ProblemSetRef`: what "the Problems of a set" means (Story 2.4, AD-9).

`resolve()` is the ONLY function that turns a `ProblemSetRef` into an ordered
`list[problem_id]` -- a Session freezes exactly this list at start. For `kind: "lesson"`
it delegates straight to `content.library.lesson_problems()` (itself a thin wrapper over
`content.effective.visible_to_child()`), so Library/Lesson-detail and Sessions always agree
on what "the Problems of this Lesson" means -- no ordering is reimplemented here.

`kind: "replay"` (Story 2.10, AD-9/AD-6) resolves directly to a source Session's own
wrong-Problem ids -- see this module's `resolve()` docstring.

`kind: "concept"` (Story 5.2): up to `CONCEPT_SET_SIZE` visible Problems linked to a Concept,
those the Profile has not yet solved correctly on the first try first, then Book order.

`kind: "exam"` (Story 8.1): a RANDOM sample of up to `count` visible Problems from a chosen
`ExamScope` (one or more Concepts, a Book optionally bounded to Unit(s), or the Profile's
whole Grade) -- see `resolve_exam_scope()`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import Connection, select

from hoctap.api.errors import AppError
from hoctap.content import library as content_library
from hoctap.learning.summary import LOCAL_TZ

# Problems per Session chunk ("Phần i/n"); shared by sessions and assignments.
CHUNK_SIZE = 10

RefKind = Literal["lesson", "concept", "retry", "replay", "exam"]


@dataclass(frozen=True)
class LessonRef:
    """`kind: "lesson"`: every visible Problem of one Book/Unit/Lesson, in the order
    `content.library.lesson_problems()` returns them."""

    book_id: str
    unit_key: str
    lesson_key: str
    kind: Literal["lesson"] = "lesson"


@dataclass(frozen=True)
class ReplayRef:
    """`kind: "replay"` (Story 2.10): a NEW Session made of exactly one earlier Session's
    wrong Problem ids ("Luyện lại bài sai"), in their original order. `source_session_id`
    is the earlier ("source") Session -- `resolve()` computes its wrong-Problem ids via
    `learning.summary.session_wrong_problem_ids()` (first-try-per-Session, by the earliest
    `attempt`/`self_marked` event ordered by rowid), so the Session summary screen and the
    replay Session it starts always agree on what "the wrong Problems" means."""

    source_session_id: str
    kind: Literal["replay"] = "replay"


@dataclass(frozen=True)
class RetryRef:
    """`kind: "retry"` (Story 3.3): the Profile's DUE Retry Queue Problems (last wrong
    Attempt on an earlier local calendar day), ordered by `last_wrong_at` ascending."""

    kind: Literal["retry"] = "retry"


@dataclass(frozen=True)
class ConceptRef:
    """`kind: "concept"` (Story 5.2): practice of one Concept (`g1.so-sanh-so`)."""

    concept_id: str
    kind: Literal["concept"] = "concept"


# Max Problems of a Concept practice Session.
CONCEPT_SET_SIZE = 10


@dataclass(frozen=True)
class ExamConceptScope:
    """`kind: "concept"`: the pool is every visible Problem linked to ANY of `concept_ids`
    (one or more -- unlike `ConceptRef`, which practises exactly one)."""

    concept_ids: list[str]
    kind: Literal["concept"] = "concept"


@dataclass(frozen=True)
class ExamBookUnitScope:
    """`kind: "book_unit"`: the pool is every visible Problem of `book_id`, optionally
    bounded to `unit_keys` (`None` -- not an empty list -- means the whole Book)."""

    book_id: str
    unit_keys: list[str] | None
    kind: Literal["book_unit"] = "book_unit"


@dataclass(frozen=True)
class ExamGradeScope:
    """`kind: "grade"`: the pool is every visible Problem anywhere in the Profile's own
    Grade (every Book of that Grade) -- no further input needed from whoever configures
    the exam."""

    kind: Literal["grade"] = "grade"


ExamScope = ExamConceptScope | ExamBookUnitScope | ExamGradeScope


@dataclass(frozen=True)
class ExamRef:
    """`kind: "exam"` (Story 8.1): a timed practice exam -- `count` Problems drawn at
    random from `scope`, `time_limit_s` seconds to answer them. Both are required,
    positive integers set by whoever configures the exam (parent or child); neither has a
    default here since `api/sessions.py`'s request schema is the one place that actually
    validates "positive" (this dataclass just carries whatever it's given)."""

    scope: ExamScope
    count: int
    time_limit_s: int
    kind: Literal["exam"] = "exam"


ProblemSetRef = LessonRef | ReplayRef | RetryRef | ConceptRef | ExamRef


def exam_scope_to_dict(scope: ExamScope) -> dict[str, object]:
    """`ExamScope` -> plain JSON data. Shared by `ref_key()` (write-only) and
    `learning.assignments` (which DOES need to parse `exam_scope_json` back, unlike
    `ref_key` -- an assigned exam re-resolves a fresh random draw at every Session start,
    so its scope must survive a round trip through storage)."""
    if scope.kind == "concept":
        return {"kind": "concept", "concept_ids": list(scope.concept_ids)}
    if scope.kind == "book_unit":
        return {
            "kind": "book_unit",
            "book_id": scope.book_id,
            "unit_keys": None if scope.unit_keys is None else list(scope.unit_keys),
        }
    return {"kind": "grade"}


def exam_scope_from_dict(data: dict[str, object]) -> ExamScope:
    """The inverse of `exam_scope_to_dict()`."""
    kind = data["kind"]
    if kind == "concept":
        return ExamConceptScope(concept_ids=list(data["concept_ids"]))  # type: ignore[arg-type]
    if kind == "book_unit":
        unit_keys = data.get("unit_keys")
        return ExamBookUnitScope(
            book_id=data["book_id"],  # type: ignore[arg-type]
            unit_keys=None if unit_keys is None else list(unit_keys),  # type: ignore[arg-type]
        )
    if kind == "grade":
        return ExamGradeScope()
    raise ValueError(f"ExamScope kind={kind!r} không được hỗ trợ. / not supported.")


class UnsupportedProblemSetRef(NotImplementedError):
    """Raised for an unknown `kind` -- not implemented, not silently wrong."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            f"ProblemSetRef kind={kind!r} chưa được hỗ trợ. / not supported."
        )


def ref_key(ref: ProblemSetRef) -> str:
    """The compact string a `progress_sessions` row stores as `ref_key`.

    Naive `:`-joined concatenation -- assumes `book_id`/`unit_key`/`lesson_key` never
    contain a literal `:` themselves (true of every id this codebase currently generates).
    Dormant today since `ref_key` is write-only (nothing parses it back this story); a
    future reader that DOES parse it should validate that assumption or switch to an
    unambiguous encoding first.
    """
    if ref.kind == "lesson":
        return f"lesson:{ref.book_id}:{ref.unit_key}:{ref.lesson_key}"
    if ref.kind == "replay":
        return f"replay:{ref.source_session_id}"
    if ref.kind == "retry":
        return "retry"
    if ref.kind == "concept":
        return f"concept:{ref.concept_id}"
    if ref.kind == "exam":
        # Story 8.1: `scope` is a richer structure than any existing ref kind's own fields,
        # so (implementer's call, per this story's spec Design Notes) this uses a short,
        # deterministic JSON string instead of extending the naive `:`-join scheme above --
        # `sort_keys` makes it reproducible for equal input, `separators` drops incidental
        # whitespace. `ref_key` ITSELF is still write-only/dormant, same as every other ref
        # kind (this module's own docstring) -- but `exam_scope_to_dict()` is reused by
        # `learning.assignments`, which DOES need to parse the scope back.
        return "exam:" + json.dumps(exam_scope_payload(ref), sort_keys=True, separators=(",", ":"))
    raise UnsupportedProblemSetRef(ref.kind)


def exam_scope_payload(ref: ExamRef) -> dict[str, object]:
    """The JSON-able `{scope, count, time_limit_s}` shape stored both in `ref_key()` and in
    `progress_assignments.exam_scope_json` (the latter is parsed back by
    `learning.assignments`; see `exam_scope_to_dict()`'s own docstring for why the two have
    different parse-ability expectations despite sharing this exact shape)."""
    return {
        "scope": exam_scope_to_dict(ref.scope),
        "count": ref.count,
        "time_limit_s": ref.time_limit_s,
    }


def exam_ref_from_payload(data: dict[str, object]) -> ExamRef:
    """The inverse of `exam_scope_payload()` -- used only by `learning.assignments` to
    reconstruct the `ExamRef` an exam Assignment recorded, so starting it can re-resolve a
    FRESH random draw (AD-9: an Assignment is a recipe, not a frozen Problem list)."""
    return ExamRef(
        scope=exam_scope_from_dict(data["scope"]),  # type: ignore[arg-type]
        count=data["count"],  # type: ignore[arg-type]
        time_limit_s=data["time_limit_s"],  # type: ignore[arg-type]
    )


def resolve_exam_scope(conn: Connection, scope: ExamScope, profile_id: str) -> list[str]:
    """The pool of visible `problem_id`s `scope` draws from (NOT yet sampled/truncated to
    `count` -- that happens in `resolve()`), always through `content.effective.
    load_effective()`/`visible_to_child()`, the exact same eligibility gate every other
    child-facing selection uses: hidden, retired, `needs_review`-unapproved and conflicted
    Problems are never in the pool.

    `kind: "concept"` silently ignores a `concept_id` that doesn't exist (rather than
    raising, unlike `ConceptRef.resolve()`'s single-Concept 404): a multi-Concept scope with
    one bad id among several good ones should still draw from the good ones, matching this
    story's own "fewer eligible Problems than requested is not an error" philosophy rather
    than failing the whole exam over one typo'd id (implementer's call, documented here and
    in the story's Implementation Notes)."""
    from hoctap.content import effective
    from hoctap.content.catalog import service as catalog_service
    from hoctap.content.review.models import content_review_problem_concepts
    from hoctap.parent.models import parent_profiles

    if scope.kind == "concept":
        if not scope.concept_ids:
            return []
        linked = list(
            dict.fromkeys(
                conn.execute(
                    select(content_review_problem_concepts.c.problem_id).where(
                        content_review_problem_concepts.c.concept_id.in_(scope.concept_ids)
                    )
                ).scalars()
            )
        )
        if not linked:
            return []
        return [v.problem_id for v in effective.visible_to_child(conn, linked)]
    if scope.kind == "book_unit":
        if scope.unit_keys is None:
            return [v.problem_id for v in effective.visible_to_child(conn, book_id=scope.book_id)]
        pool: list[str] = []
        for unit_key in scope.unit_keys:
            pool += [
                v.problem_id
                for v in effective.visible_to_child(
                    conn, book_id=scope.book_id, unit_key=unit_key
                )
            ]
        return pool
    # kind == "grade": the Profile's own Grade, every Book of it.
    grade = conn.execute(
        select(parent_profiles.c.grade).where(parent_profiles.c.id == profile_id)
    ).scalar_one_or_none()
    if grade is None:
        raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
    pool = []
    for book in catalog_service.list_books(conn):
        if book.grade != grade:
            continue
        pool += [v.problem_id for v in effective.visible_to_child(conn, book_id=book.book_id)]
    return pool


def resolve(
    conn: Connection, ref: ProblemSetRef, profile_id: str, now: datetime | None = None
) -> list[str]:
    """The ordered `problem_id`s of `ref`, for `profile_id`.

    `profile_id` is unused for `kind: "lesson"` (a Lesson's Problems aren't personalised);
    for `kind: "replay"` it is the ownership check: the source Session must belong to this
    same Profile, else a client could replay another child's wrong Problems by guessing a
    `session_id`. The source Session must also already be completed (`completed_at is not
    None`, Review Triage Log #2, 2026-09-29) -- otherwise a still-in-progress Session's
    "no attempt yet" Problems would look indistinguishable from genuinely wrong ones and a
    replay could be started before the original was ever finished.

    Replaying a replay (a `kind: "replay"` ref whose `source_session_id` itself points at
    a `mode="replay"` Session) is intentionally ALLOWED and untouched by any extra check
    (Review Triage Log #5, 2026-09-29): a replay Session that itself still has wrong
    Problems is a legitimate, if unusual, thing to want to practise again, and blocking it
    would need an arbitrary chained-replay-depth rule the frozen spec never asked for. The
    only two intentional guards on a replay source remain "belongs to this profile" and
    "already completed"; nothing here inspects the source's own `mode`/`ref_kind`.
    """
    if ref.kind == "lesson":
        views = content_library.lesson_problems(conn, ref.book_id, ref.unit_key, ref.lesson_key)
        return [v.problem_id for v in views]
    if ref.kind == "replay":
        # Imported here, not at module top -- `learning.summary` never needs anything from
        # `learning.problem_sets`, but keeping the import local avoids the reader having to
        # wonder whether a future cycle exists between the two sibling modules.
        from hoctap.learning.models import progress_sessions
        from hoctap.learning.summary import session_wrong_problem_ids

        source = conn.execute(
            select(progress_sessions).where(progress_sessions.c.id == ref.source_session_id)
        ).one_or_none()
        if source is None or source.profile_id != profile_id:
            raise AppError(
                422,
                "REPLAY_SOURCE_NOT_FOUND",
                "Không tìm thấy lượt học để luyện lại.",
            )
        # Review Triage Log #2 (2026-09-29, medium): a still-in-progress source Session
        # (`completed_at is None`) must not be replayed -- `session_wrong_problem_ids()`
        # treats "no attempt yet" the same as "wrong" (absence-of-evidence rule), so an
        # in-progress Session would otherwise look like a valid, non-empty replay target
        # and spawn a near-duplicate Session before the child ever finished the original.
        if source.completed_at is None:
            raise AppError(
                422,
                "REPLAY_SOURCE_NOT_COMPLETED",
                "Lượt học này chưa hoàn thành, chưa thể luyện lại. / "
                "This session isn't finished yet, so it can't be replayed.",
            )
        wrong_ids = session_wrong_problem_ids(conn, ref.source_session_id)
        if not wrong_ids:
            raise AppError(
                422,
                "REPLAY_NO_WRONG_PROBLEMS",
                "Lượt học này không có bài nào làm sai để luyện lại.",
            )
        return wrong_ids
    if ref.kind == "concept":
        from hoctap.content import effective
        from hoctap.content.review.models import (
            content_review_concepts,
            content_review_problem_concepts,
        )
        from hoctap.learning.summary import first_try_solved_problem_ids

        found = conn.execute(
            select(content_review_concepts.c.concept_id).where(
                content_review_concepts.c.concept_id == ref.concept_id
            )
        ).scalar_one_or_none()
        if found is None:
            raise AppError(404, "CONCEPT_NOT_FOUND", "Không tìm thấy khái niệm này.")
        linked = list(
            conn.execute(
                select(content_review_problem_concepts.c.problem_id).where(
                    content_review_problem_concepts.c.concept_id == ref.concept_id
                )
            ).scalars()
        )
        # Book order (book, position) comes from `visible_to_child()`.
        visible = [v.problem_id for v in effective.visible_to_child(conn, linked)]
        solved = first_try_solved_problem_ids(conn, profile_id, visible)
        ordered = [p for p in visible if p not in solved] + [p for p in visible if p in solved]
        return ordered[:CONCEPT_SET_SIZE]
    if ref.kind == "retry":
        from hoctap.learning.retry import due_problem_ids

        if now is None:
            raise ValueError("resolve() needs `now` for a retry ref (no wall-clock fallback)")
        today = now.astimezone(LOCAL_TZ).date()
        due = due_problem_ids(conn, profile_id, today)
        if not due:
            raise AppError(
                422,
                "RETRY_QUEUE_EMPTY",
                "Chưa có bài nào cần luyện lại hôm nay.",
            )
        return due
    if ref.kind == "exam":
        # Story 8.1: random sample, truncated to `count` -- a scope with fewer eligible
        # Problems than requested is NOT an error (this story's frozen Boundaries): the
        # exam simply gets a smaller set, never padded with ineligible Problems. An empty
        # pool returns `[]` here (not raised), same as `start_session()`'s generic
        # `EMPTY_PROBLEM_SET` 422 every other ref kind already falls back to for an empty
        # result -- unlike `retry`/`replay` above, exam mode has no bespoke empty-scope
        # error code of its own (the I/O matrix reuses the generic one).
        pool = resolve_exam_scope(conn, ref.scope, profile_id)
        if not pool:
            return []
        # `random.sample` without replacement is exactly "shuffled, then truncated to
        # count" in one call -- no separate `random.shuffle()` + slice needed.
        return random.sample(pool, min(ref.count, len(pool)))
    raise UnsupportedProblemSetRef(ref.kind)
