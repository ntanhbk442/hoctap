"""`ProblemSetRef`: what "the Problems of a set" means (Story 2.4, AD-9).

`resolve()` is the ONLY function that turns a `ProblemSetRef` into an ordered
`list[problem_id]` -- a Session freezes exactly this list at start. For `kind: "lesson"`
it delegates straight to `content.library.lesson_problems()` (itself a thin wrapper over
`content.effective.visible_to_child()`), so Library/Lesson-detail and Sessions always agree
on what "the Problems of this Lesson" means -- no ordering is reimplemented here.

`kind: "replay"` (Story 2.10, AD-9/AD-6) resolves directly to a source Session's own
wrong-Problem ids -- see this module's `resolve()` docstring.

`kind: "concept" | "retry"` (AD-9) remain documented, not-yet-supported extension points:
Concepts and the Retry Queue as a startable Problem set don't exist yet, so resolving one of
these kinds raises `UnsupportedProblemSetRef` loudly rather than silently returning the
wrong list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Connection, select

from hoctap.api.errors import AppError
from hoctap.content import library as content_library
from hoctap.learning.summary import LOCAL_TZ

RefKind = Literal["lesson", "concept", "retry", "replay"]


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


# Extension point: `ProblemSetRef = LessonRef | ConceptRef | RetryRef | ReplayRef`.
ProblemSetRef = LessonRef | ReplayRef | RetryRef


class UnsupportedProblemSetRef(NotImplementedError):
    """Raised for `kind: concept|retry|replay` -- not yet implemented, not silently wrong."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            f"ProblemSetRef kind={kind!r} chưa được hỗ trợ (cần Concept/Retry Queue/lịch sử "
            "làm lại, những thứ chưa tồn tại). / not yet supported (needs Concepts/Retry "
            "Queue/replay history, which don't exist yet -- see Story 2.5+)."
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
    raise UnsupportedProblemSetRef(ref.kind)


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
    if ref.kind == "retry":
        from hoctap.learning.retry import due_problem_ids

        today = (now or datetime.now(UTC)).astimezone(LOCAL_TZ).date()
        due = due_problem_ids(conn, profile_id, today)
        if not due:
            raise AppError(
                422,
                "RETRY_QUEUE_EMPTY",
                "Chưa có bài nào cần luyện lại hôm nay.",
            )
        return due
    raise UnsupportedProblemSetRef(ref.kind)
