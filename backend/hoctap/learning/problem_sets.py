"""`ProblemSetRef`: what "the Problems of a set" means (Story 2.4, AD-9).

`resolve()` is the ONLY function that turns a `ProblemSetRef` into an ordered
`list[problem_id]` -- a Session freezes exactly this list at start. For `kind: "lesson"`
it delegates straight to `content.library.lesson_problems()` (itself a thin wrapper over
`content.effective.visible_to_child()`), so Library/Lesson-detail and Sessions always agree
on what "the Problems of this Lesson" means -- no ordering is reimplemented here.

`kind: "concept" | "retry" | "replay"` (AD-9) are documented, not-yet-supported extension
points: Concepts, the Retry Queue and replay history don't exist yet, so resolving one of
these kinds raises `UnsupportedProblemSetRef` loudly rather than silently returning the
wrong list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection

from hoctap.content import library as content_library

RefKind = Literal["lesson", "concept", "retry", "replay"]


@dataclass(frozen=True)
class LessonRef:
    """`kind: "lesson"`: every visible Problem of one Book/Unit/Lesson, in the order
    `content.library.lesson_problems()` returns them."""

    book_id: str
    unit_key: str
    lesson_key: str
    kind: Literal["lesson"] = "lesson"


# Extension point (Story 2.5+): `ProblemSetRef = LessonRef | ConceptRef | RetryRef | ReplayRef`.
ProblemSetRef = LessonRef


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
    raise UnsupportedProblemSetRef(ref.kind)


def resolve(conn: Connection, ref: ProblemSetRef, profile_id: str) -> list[str]:
    """The ordered `problem_id`s of `ref`, for `profile_id`.

    `profile_id` is unused for `kind: "lesson"` (a Lesson's Problems aren't personalised);
    it is threaded through now because `concept`/`retry`/`replay` kinds will need it.
    """
    del profile_id  # not needed for kind: lesson; kept for the concept/retry/replay kinds
    if ref.kind != "lesson":
        raise UnsupportedProblemSetRef(ref.kind)
    views = content_library.lesson_problems(conn, ref.book_id, ref.unit_key, ref.lesson_key)
    return [v.problem_id for v in views]
