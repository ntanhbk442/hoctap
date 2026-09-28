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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from hoctap.api.errors import AppError
from hoctap.content import assets
from hoctap.content.effective import ProblemNotFound, load_one
from hoctap.content.speech import problem_speech_refs, speech_url
from hoctap.content.views import ChildProblemView, child_view
from hoctap.ids import new_id, to_iso
from hoctap.learning.models import progress_events, progress_sessions
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


def _row_to_event_out(row: Any) -> EventOut:
    return EventOut(
        id=row.id,
        session_id=row.session_id,
        kind=row.kind,
        problem_id=row.problem_id,
        occurred_at=row.occurred_at,
        received_at=row.received_at,
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


def post_event(
    conn: Any, now: datetime, session_id: str, profile_id: str, event: EventIn
) -> EventOut:
    """Race-safe idempotent insert (AD-6): the client's UUIDv7 is the primary key, so a
    resend (even a concurrent one) hits an IntegrityError, which is caught and turned into
    a re-fetch of the already-stored row -- never a check-then-insert race window. The
    re-fetched row is only treated as a legitimate resend if it belongs to THIS
    `session_id`; a genuine cross-session UUID collision is rejected (409), never
    silently returned as if it were the caller's own event.

    Validates the Session exists and belongs to `profile_id` (403), and that the event is
    valid for it (`_validate_event_against_session()`). Does NOT grade -- an `attempt`
    event is stored inertly; Story 2.5 reacts to it.
    """
    session = _load_session(conn, session_id)
    if session.profile_id != profile_id:
        raise AppError(403, "FORBIDDEN", "Lượt học này không thuộc về hồ sơ này.")
    _validate_event_against_session(session, event)

    received_at = to_iso(now)
    try:
        with conn.begin_nested():
            conn.execute(
                progress_events.insert().values(
                    id=event.id,
                    session_id=session_id,
                    profile_id=profile_id,
                    kind=event.kind,
                    problem_id=event.problem_id,
                    payload_json=json.dumps(event.payload),
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
