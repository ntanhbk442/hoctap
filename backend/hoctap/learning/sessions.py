"""Session-start, bundle-assembly and event-ingestion services (Story 2.4, AD-9/AD-10/AD-6).

Router (`api/sessions.py`) stays thin; this module owns the DB work, matching this
codebase's existing `api/*` (thin) + `content/*`/`learning/*` (service) split.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from hoctap.api.errors import AppError
from hoctap.content import assets
from hoctap.content.effective import ProblemNotFound, load_one
from hoctap.content.schema import FallbackPart, Part
from hoctap.content.speech import problem_speech_refs, speech_url
from hoctap.content.views import ChildProblemView, child_view
from hoctap.ids import new_id, to_iso
from hoctap.learning.graders import grade_part
from hoctap.learning.models import progress_events, progress_retry_items, progress_sessions
from hoctap.learning.problem_sets import ProblemSetRef, ref_key, resolve
from hoctap.parent.models import parent_profiles

CHUNK_SIZE = 10
EVENT_KINDS = frozenset(
    {
        "attempt",
        "hint_requested",
        "solution_shown",
        "fallback_revealed",
        "self_marked",
        "quiz_submitted",
        "session_started",
        "session_completed",
    }
)

# Voice id used to resolve a Problem's speech refs to URLs (matches `content.speech`'s
# content-addressed key; see `config.Settings.tts_voice_id`, duplicated here the same way
# Story 2.3's frontend already had to -- see deferred-work.md).
DEFAULT_VOICE_ID = "vi-VN-HoaiMyNeural"


@dataclass(frozen=True)
class SessionOut:
    id: str
    profile_id: str
    ref_kind: str
    problem_ids: list[str]
    chunk_size: int
    mode: str
    started_at: str


def start_session(conn: Any, now: datetime, profile_id: str, ref: ProblemSetRef) -> SessionOut:
    """Resolves `ref`, refuses an empty set (422), creates the Session, writes its
    `session_started` event (server-generated id -- the Session doesn't exist yet for the
    client to have already minted one), returns the frozen Session."""
    profile_exists = conn.execute(
        select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
    ).scalar_one_or_none()
    if profile_exists is None:
        raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")

    problem_ids = resolve(conn, ref, profile_id)
    if not problem_ids:
        raise AppError(
            422,
            "EMPTY_PROBLEM_SET",
            "Bài học này chưa có bài tập nào để bắt đầu.",
        )

    session_id = new_id()
    started_at = to_iso(now)
    conn.execute(
        progress_sessions.insert().values(
            id=session_id,
            profile_id=profile_id,
            ref_kind=ref.kind,
            ref_key=ref_key(ref),
            mode="practice",
            problem_ids_json=json.dumps(problem_ids),
            chunk_size=CHUNK_SIZE,
            started_at=started_at,
            completed_at=None,
        )
    )
    conn.execute(
        progress_events.insert().values(
            id=new_id(),
            session_id=session_id,
            profile_id=profile_id,
            kind="session_started",
            problem_id=None,
            payload_json="{}",
            occurred_at=started_at,
            received_at=started_at,
        )
    )
    return SessionOut(
        id=session_id,
        profile_id=profile_id,
        ref_kind=ref.kind,
        problem_ids=problem_ids,
        chunk_size=CHUNK_SIZE,
        mode="practice",
        started_at=started_at,
    )


def _load_session(conn: Any, session_id: str) -> Any:
    row = conn.execute(
        select(progress_sessions).where(progress_sessions.c.id == session_id)
    ).one_or_none()
    if row is None:
        raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy lượt học.")
    return row


@dataclass(frozen=True)
class BundleProblem:
    view: ChildProblemView
    crop_urls: list[str]
    page_urls: list[str]
    audio: dict[str, str]  # speech_key -> URL
    attempted: bool


@dataclass(frozen=True)
class BundleOut:
    session_id: str
    chunk: int
    chunk_count: int
    chunk_label: str
    problems: list[BundleProblem] = field(default_factory=list)


def get_bundle(conn: Any, session_id: str, profile_id: str, chunk: int) -> BundleOut:
    """The chunk's slice of the Session's frozen `problem_ids_json` (AD-9: never
    re-filtered), assembled with each Problem's child_view/crop/page/audio URLs and honest
    `attempted` progress state (AD-10).

    `chunk < 1` is unreachable through the API (the router's `Query(ge=1)` already 422s
    it before this function is ever called -- see finding #13 of the orchestrator's
    independent review round), so no `INVALID_CHUNK` guard is duplicated here.

    Validates `profile_id` matches the Session's own owner (403 `FORBIDDEN`) -- the same
    ownership check `post_event()`/`validate_events_batch()` already apply, closing the
    gap where anyone who knew/guessed a `session_id` could read another child's Problem
    content, URLs and progress state with no Profile check at all.
    """
    session = _load_session(conn, session_id)
    if session.profile_id != profile_id:
        raise AppError(403, "FORBIDDEN", "Lượt học này không thuộc về hồ sơ này.")
    problem_ids: list[str] = json.loads(session.problem_ids_json)
    chunk_count = max(1, math.ceil(len(problem_ids) / CHUNK_SIZE))
    if chunk > chunk_count:
        raise AppError(422, "CHUNK_OUT_OF_RANGE", "Phần này không tồn tại trong lượt học.")

    slice_ids = problem_ids[(chunk - 1) * CHUNK_SIZE : chunk * CHUNK_SIZE]

    attempted_ids: set[str] = set()
    if slice_ids:
        rows = conn.execute(
            select(progress_events.c.problem_id)
            .where(
                progress_events.c.profile_id == session.profile_id,
                progress_events.c.kind == "attempt",
                progress_events.c.problem_id.in_(slice_ids),
            )
            .distinct()
        )
        attempted_ids = {r.problem_id for r in rows}

    problems: list[BundleProblem] = []
    for problem_id in slice_ids:
        try:
            state = load_one(conn, problem_id)
        except ProblemNotFound:
            # Frozen list referencing a Problem that vanished entirely (not merely hidden)
            # -- skip it rather than 500; AD-9 freezes the id list, not the row's existence.
            continue
        if state.doc is None:
            continue
        view = child_view(state.doc)
        refs = problem_speech_refs(state.doc, DEFAULT_VOICE_ID)
        problems.append(
            BundleProblem(
                view=view,
                crop_urls=assets.problem_crop_urls(state.doc),
                page_urls=assets.problem_page_urls(state.doc),
                audio={r.speech_key: speech_url(r.speech_key) for r in refs},
                attempted=problem_id in attempted_ids,
            )
        )

    return BundleOut(
        session_id=session_id,
        chunk=chunk,
        chunk_count=chunk_count,
        chunk_label=f"Phần {chunk}/{chunk_count}",
        problems=problems,
    )


@dataclass(frozen=True)
class EventIn:
    id: str
    kind: str
    problem_id: str | None
    payload: dict[str, Any]
    occurred_at: str


@dataclass(frozen=True)
class EventOut:
    id: str
    session_id: str
    kind: str
    problem_id: str | None
    occurred_at: str
    received_at: str
    # Grading fields (Story 2.5): present only for `attempt` events, read back from the
    # stored `payload_json` -- so a freshly-graded insert and a resent (already-stored)
    # event return identically, without recomputing anything.
    correct: bool | None = None
    wrong_keys: list[str] | None = None
    hint: str | None = None
    solution: dict[str, Any] | None = None


def _row_to_event_out(row: Any) -> EventOut:
    correct = wrong_keys = hint = solution = None
    if row.kind == "attempt":
        payload = json.loads(row.payload_json)
        correct = payload.get("correct")
        wrong_keys = payload.get("wrong_keys")
        hint = payload.get("hint")
        solution = payload.get("solution")
    return EventOut(
        id=row.id,
        session_id=row.session_id,
        kind=row.kind,
        problem_id=row.problem_id,
        occurred_at=row.occurred_at,
        received_at=row.received_at,
        correct=correct,
        wrong_keys=wrong_keys,
        hint=hint,
        solution=solution,
    )


def _validate_event_against_session(session_row: Any, event: EventIn) -> None:
    """`event.kind` is one of AD-6's exact kinds, and, if `event.problem_id` is set, it is
    a member of the Session's own frozen `problem_ids_json` -- otherwise a client could
    pollute an unrelated Lesson's `attempted` numerator (`learning.progress`) via any
    Session it owns, and `progress_events` is append-only so that could never be cleaned
    up afterward."""
    if event.kind not in EVENT_KINDS:
        raise AppError(422, "INVALID_EVENT_KIND", "Loại sự kiện không hợp lệ.")
    if event.problem_id is not None:
        problem_ids = json.loads(session_row.problem_ids_json)
        if event.problem_id not in problem_ids:
            raise AppError(
                422,
                "PROBLEM_NOT_IN_SESSION",
                "Bài tập này không thuộc lượt học này.",
            )


def validate_events_batch(
    conn: Any, session_id: str, profile_id: str, events: list[EventIn]
) -> None:
    """Validates the WHOLE batch upfront -- the Session exists and belongs to
    `profile_id` (403/404), and every event's `kind`/`problem_id` membership -- before any
    insert is attempted. A batch is either fully attempted or rejected outright: without
    this upfront pass, a later invalid event in the same `engine.begin()` transaction would
    raise and roll back sibling events already inserted (in their own SAVEPOINT) moments
    before, silently discarding them (AD-6 requires durable, not-silently-lost events).
    """
    session = _load_session(conn, session_id)
    if session.profile_id != profile_id:
        raise AppError(403, "FORBIDDEN", "Lượt học này không thuộc về hồ sơ này.")
    for event in events:
        _validate_event_against_session(session, event)


def _find_part(parts: list[Part], part_key: Any) -> Part:
    """The named Part of the resolved Problem, or an AppError (422) -- never a 500 for a
    bad `part_key`, and `FallbackPart` (solution-only, `answer` always None) is never
    gradeable, so it is rejected the same way as a genuinely unknown `part_key`."""
    if isinstance(part_key, str):
        for part in parts:
            if part.part_key == part_key and not isinstance(part, FallbackPart):
                return part
    raise AppError(
        422, "PART_NOT_FOUND", "Không tìm thấy phần bài tập này để chấm điểm."
    )


def _count_prior_wrong(conn: Any, profile_id: str, problem_id: str, part_key: str) -> int:
    """Prior wrong `attempt` events for this Part, across ALL Sessions (Profile-wide, per
    AD-6/this story's frozen intent) -- staged help is derived by counting the append-only
    log, not a separate mutable counter."""
    rows = conn.execute(
        select(progress_events.c.payload_json).where(
            progress_events.c.profile_id == profile_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "attempt",
        )
    )
    count = 0
    for row in rows:
        data = json.loads(row.payload_json)
        if data.get("part_key") == part_key and data.get("correct") is False:
            count += 1
    return count


def _part_currently_correct(conn: Any, profile_id: str, problem_id: str, part_key: str) -> bool:
    """Whether this Part has at least one stored `attempt` AND its most recent one was
    graded correct -- used only to decide Retry Queue resolution. A Part NEVER attempted
    BLOCKS resolution (it has not been "answered correctly" at all); a Part that went
    wrong and was since corrected does not block.

    "Most recent" is ordered by SQLite's own implicit `rowid` (true insertion order),
    not `received_at`/`id`: every event of one batch shares the SAME `received_at`
    (resolved once per request via `get_now()`), and `id` (a client-supplied UUIDv7) is
    only millisecond-monotonic and client-controlled, so two attempts on the same Part
    minted in the same millisecond within one batch could otherwise sort in the wrong
    order and read a stale verdict.
    """
    rows = conn.execute(
        select(progress_events.c.payload_json)
        .where(
            progress_events.c.profile_id == profile_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "attempt",
        )
        .order_by(text("progress_events.rowid ASC"))
    )
    latest_correct: bool | None = None
    for row in rows:
        data = json.loads(row.payload_json)
        if data.get("part_key") != part_key:
            continue
        latest_correct = bool(data.get("correct"))
    if latest_correct is None:
        return False  # never attempted -- blocks resolution
    return latest_correct


def _add_retry_item(conn: Any, profile_id: str, problem_id: str, added_at: str) -> None:
    """Adds the Problem to the Retry Queue, skipping the insert if an unresolved row for
    this `profile_id`+`problem_id` already exists (a 2nd Part going wrong, or a resend
    replayed through the same transaction, must not duplicate the row)."""
    existing = conn.execute(
        select(progress_retry_items.c.id).where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.problem_id == problem_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).first()
    if existing is not None:
        return
    conn.execute(
        progress_retry_items.insert().values(
            id=new_id(),
            profile_id=profile_id,
            problem_id=problem_id,
            added_at=added_at,
            resolved_at=None,
        )
    )


def _maybe_resolve_retry_item(
    conn: Any,
    profile_id: str,
    problem_id: str,
    parts: list[Part],
    graded_part_key: str,
    now_iso: str,
) -> None:
    """Resolves this Problem's open Retry Queue row once every OTHER Part (the
    just-graded Part is correct by construction, since this is only called on a correct
    attempt) is also currently correct -- see `_part_currently_correct()`."""
    others = [
        p.part_key
        for p in parts
        if not isinstance(p, FallbackPart) and p.part_key != graded_part_key
    ]
    if any(not _part_currently_correct(conn, profile_id, problem_id, key) for key in others):
        return
    # A cheap existence check first: the common case (no open Retry Queue row at all,
    # e.g. this Part/Problem was never gotten wrong) then needs no write statement --
    # keeping a correct-and-already-fine attempt from ever requesting SQLite's exclusive
    # write lock at all.
    existing = conn.execute(
        select(progress_retry_items.c.id).where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.problem_id == problem_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).first()
    if existing is None:
        return
    conn.execute(
        progress_retry_items.update()
        .where(progress_retry_items.c.id == existing.id)
        .values(resolved_at=now_iso)
    )


def _grade_and_stage(
    conn: Any, profile_id: str, problem_id: str | None, payload: dict[str, Any], received_at: str
) -> dict[str, Any]:
    """The `attempt`-kind core: loads the effective Problem the same defensive way the
    bundle does (never 500s on a Problem whose override became invalid), grades the named
    Part, augments and returns `payload` with the verdict, and stages Hint/Solution
    release + the Retry Queue transition (AD-6's staged-help rule, this story's Boundaries
    & Constraints step 4)."""
    if problem_id is None:
        raise AppError(422, "PART_NOT_FOUND", "Không tìm thấy phần bài tập này để chấm điểm.")
    try:
        state = load_one(conn, problem_id)
    except ProblemNotFound:
        raise AppError(
            422, "PART_NOT_FOUND", "Không tìm thấy phần bài tập này để chấm điểm."
        ) from None
    if state.doc is None:
        raise AppError(422, "PART_NOT_FOUND", "Không tìm thấy phần bài tập này để chấm điểm.")

    part = _find_part(list(state.doc.parts), payload.get("part_key"))
    result = grade_part(part, payload.get("value"))

    payload = dict(payload)
    payload["correct"] = result.correct
    payload["wrong_keys"] = result.wrong_keys
    hint: str | None = None
    solution: dict[str, Any] | None = None
    if result.correct:
        _maybe_resolve_retry_item(
            conn, profile_id, problem_id, list(state.doc.parts), part.part_key, received_at
        )
    else:
        prior_wrong = _count_prior_wrong(conn, profile_id, problem_id, part.part_key)
        hint = part.hint  # released on the 1st wrong attempt, and stays shown afterward
        if prior_wrong == 0:
            _add_retry_item(conn, profile_id, problem_id, received_at)
        else:
            solution = part.solution.model_dump(mode="json")
    payload["hint"] = hint
    payload["solution"] = solution
    return payload


def post_event(
    conn: Any, now: datetime, session_id: str, profile_id: str, event: EventIn
) -> EventOut:
    """Race-safe idempotent insert (AD-6): the client's UUIDv7 is the primary key.

    An `attempt` event is graded synchronously, in the SAME transaction as its insert
    (AD-6's literal rule) -- `_grade_and_stage()` augments the event's own `payload_json`
    with the verdict and stages the Hint/Solution/Retry-Queue transition before the row is
    ever written. A genuinely already-stored event (same id, same session -- a sequential
    resend, or the 2nd occurrence of one id within a batch) is detected up front and
    returned as-is: it is NOT re-graded and cannot double-count into the Retry Queue.
    A CONCURRENT resend instead races the insert itself; that still hits an IntegrityError,
    which is caught and turned into a re-fetch of the already-stored row -- and because the
    grading + staging above runs inside the same SAVEPOINT as the insert, the loser of that
    race has its own (redundant) grading/Retry-Queue side effects rolled back with it, never
    left half-applied. Either way, the re-fetched row is only treated as a legitimate resend
    if it belongs to THIS `session_id`; a genuine cross-session UUID collision is rejected
    (409), never silently returned as if it were the caller's own event.

    Validates the Session exists and belongs to `profile_id` (403), and that the event is
    valid for it (`_validate_event_against_session()`).
    """
    session = _load_session(conn, session_id)
    if session.profile_id != profile_id:
        raise AppError(403, "FORBIDDEN", "Lượt học này không thuộc về hồ sơ này.")
    _validate_event_against_session(session, event)

    already_stored = conn.execute(
        select(progress_events).where(progress_events.c.id == event.id)
    ).one_or_none()
    if already_stored is not None:
        if already_stored.session_id != session_id:
            raise AppError(
                409,
                "EVENT_ID_COLLISION",
                "Mã sự kiện này đã được dùng cho một lượt học khác.",
            )
        return _row_to_event_out(already_stored)

    received_at = to_iso(now)
    try:
        with conn.begin_nested():
            payload = event.payload
            if event.kind == "attempt":
                payload = _grade_and_stage(
                    conn, profile_id, event.problem_id, payload, received_at
                )
            conn.execute(
                progress_events.insert().values(
                    id=event.id,
                    session_id=session_id,
                    profile_id=profile_id,
                    kind=event.kind,
                    problem_id=event.problem_id,
                    payload_json=json.dumps(payload),
                    occurred_at=event.occurred_at,
                    received_at=received_at,
                )
            )
    except IntegrityError:
        existing = conn.execute(
            select(progress_events).where(progress_events.c.id == event.id)
        ).one()
        if existing.session_id != session_id:
            # Not a legitimate resend -- the client's UUIDv7 happens to collide with a
            # DIFFERENT Session's event id (that Session was already confirmed, above, to
            # belong to a Profile at least as different as `session_id != existing.session_id`
            # implies). Returning `existing` here would hand the caller another Session's
            # event content as if it were their own 201 result.
            raise AppError(
                409,
                "EVENT_ID_COLLISION",
                "Mã sự kiện này đã được dùng cho một lượt học khác.",
            ) from None
        return _row_to_event_out(existing)

    row = conn.execute(select(progress_events).where(progress_events.c.id == event.id)).one()
    return _row_to_event_out(row)
