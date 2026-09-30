"""Progress dashboard metrics (Story 4.2): the single owner of every dashboard figure's
definition. Read-only over `progress_*` and the `content` views; writes nothing.

Definitions (frozen in the story spec):

- Only completed, non-`replay` Sessions count (AD-6). `quiz` Sessions count like practice.
- First-try accuracy = first-try-correct Problems / Problems in completed Sessions, from
  `summary.session_wrong_problem_ids()`. `fallback` Problems (self-check) are counted
  beside it, never in the ratio.
- A calendar day is a `LOCAL_TZ` date of a Session's `completed_at`; event `occurred_at`
  (never `received_at`) drives time.
- Time per Session = sum of gaps between consecutive event `occurred_at`, each capped at
  `IDLE_CAP`.
- A Problem-in-a-Session outcome is one Attempt for every effective Concept of the Problem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, text

from hoctap.content import effective, library
from hoctap.content.review.models import content_review_concepts
from hoctap.ids import from_iso
from hoctap.learning import assignments as learning_assignments
from hoctap.learning import badges as learning_badges
from hoctap.learning import progress as learning_progress
from hoctap.learning import retry as learning_retry
from hoctap.learning import scoring as learning_scoring
from hoctap.learning.models import progress_events, progress_retry_items, progress_sessions
from hoctap.learning.summary import (
    _local_date,
    compute_streak,
    session_wrong_problem_ids,
)
from hoctap.parent.models import parent_profiles

IDLE_CAP = timedelta(minutes=5)
WEAK_CONCEPT_WINDOW_DAYS = 28  # four calendar weeks ending today
WEAK_CONCEPT_MIN_ATTEMPTS = 5
WEAK_CONCEPT_LIMIT = 5
RECENT_MISTAKES_LIMIT = 10


class ProfileNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DayMetrics:
    date: str  # ISO local date
    future: bool
    sessions: int
    minutes: int
    first_try_correct: int
    problems: int  # graded Problems (fallback excluded) -- the accuracy denominator
    self_check: int  # fallback Problems ("tự kiểm tra"), outside the ratio
    accuracy: float | None  # None when nothing graded


@dataclass(frozen=True)
class WeekTotals:
    sessions: int
    minutes: int
    first_try_correct: int
    problems: int
    self_check: int
    accuracy: float | None


@dataclass(frozen=True)
class UnitProgress:
    unit_key: str
    label: str
    title: str
    attempted: int
    total: int


@dataclass(frozen=True)
class BookProgress:
    book_id: str
    title_vi: str
    attempted: int
    total: int
    units: list[UnitProgress]


@dataclass(frozen=True)
class WeakConcept:
    concept_id: str
    name_vi: str
    attempts: int
    first_try_correct: int
    accuracy: float


@dataclass(frozen=True)
class MistakePart:
    part_key: str
    child_answer: str
    correct_answer: str


@dataclass(frozen=True)
class RecentMistake:
    problem_id: str
    display_label: str
    completed_at: str
    parts: list[MistakePart]


@dataclass(frozen=True)
class BadgeMetric:
    badge_key: str
    earned: bool
    earned_at: str | None


@dataclass(frozen=True)
class Dashboard:
    profile_id: str
    name: str
    grade: int
    week_start: str
    week_end: str
    stars: int
    streak: int
    badges: list[BadgeMetric]
    retry_due_count: int
    retry_open_count: int
    days: list[DayMetrics]
    week: WeekTotals
    books: list[BookProgress]
    weak_concepts: list[WeakConcept]
    recent_mistakes: list[RecentMistake]
    assignments: list[learning_assignments.AssignmentInfo]


@dataclass
class _SessionFacts:
    id: str
    completed_at: str
    day: date
    problem_ids: list[str]
    wrong: set[str]
    seconds: float = 0.0
    fallback: set[str] = field(default_factory=set)


def _ratio(correct: int, total: int) -> float | None:
    return None if total == 0 else correct / total


def session_seconds(conn: Any, session_id: str) -> float:
    """Sum of gaps between consecutive events' `occurred_at`, each capped at `IDLE_CAP`."""
    rows = conn.execute(
        select(progress_events.c.occurred_at).where(progress_events.c.session_id == session_id)
    )
    stamps = sorted(from_iso(r.occurred_at) for r in rows)
    total = timedelta()
    for earlier, later in zip(stamps, stamps[1:], strict=False):
        total += min(later - earlier, IDLE_CAP)
    return total.total_seconds()


def _completed_sessions(conn: Any, profile_id: str) -> list[_SessionFacts]:
    rows = conn.execute(
        select(
            progress_sessions.c.id,
            progress_sessions.c.completed_at,
            progress_sessions.c.problem_ids_json,
        )
        .where(
            progress_sessions.c.profile_id == profile_id,
            progress_sessions.c.mode != "replay",
            progress_sessions.c.completed_at.isnot(None),
        )
        .order_by(progress_sessions.c.completed_at)
    ).all()
    return [
        _SessionFacts(
            id=r.id,
            completed_at=r.completed_at,
            day=_local_date(r.completed_at),
            problem_ids=json.loads(r.problem_ids_json),
            wrong=set(session_wrong_problem_ids(conn, r.id)),
        )
        for r in rows
    ]


def _week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def _day_rows(sessions: list[_SessionFacts], today: date) -> list[DayMetrics]:
    start, _ = _week_bounds(today)
    out: list[DayMetrics] = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        of_day = [s for s in sessions if s.day == day]
        graded = correct = self_check = 0
        for s in of_day:
            for pid in s.problem_ids:
                if pid in s.fallback:
                    self_check += 1
                    continue
                graded += 1
                correct += pid not in s.wrong
        out.append(
            DayMetrics(
                date=day.isoformat(),
                future=day > today,
                sessions=len(of_day),
                minutes=round(sum(s.seconds for s in of_day) / 60),
                first_try_correct=correct,
                problems=graded,
                self_check=self_check,
                accuracy=_ratio(correct, graded),
            )
        )
    return out


def _week_totals(days: list[DayMetrics], sessions: list[_SessionFacts], today: date) -> WeekTotals:
    start, end = _week_bounds(today)
    seconds = sum(s.seconds for s in sessions if start <= s.day <= end)
    graded = sum(d.problems for d in days)
    correct = sum(d.first_try_correct for d in days)
    return WeekTotals(
        sessions=sum(d.sessions for d in days),
        minutes=round(seconds / 60),
        first_try_correct=correct,
        problems=graded,
        self_check=sum(d.self_check for d in days),
        accuracy=_ratio(correct, graded),
    )


def _fmt(value: Any) -> str:
    """A short human text for a stored answer / Answer Key value of any Part shape."""
    if value is None:
        return ""
    if isinstance(value, list):
        if value and all(isinstance(v, dict) and "key" in v and "value" in v for v in value):
            if len(value) == 1:
                return str(value[0]["value"])
            return "; ".join(f"{v['key']} = {v['value']}" for v in value)
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, dict):
        for name in ("selected", "order", "pairs", "sequence", "regions"):
            if name in value:
                return _fmt(value[name])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _wrong_parts(
    conn: Any, session_id: str, problem_id: str, state: effective.EffectiveProblem
) -> list[MistakePart]:
    """Parts whose EARLIEST `attempt` in this Session was wrong: the child's submitted
    `value` beside the effective Answer Key."""
    assert state.doc is not None
    parts = {p.part_key: p for p in state.doc.parts}
    seen: set[str] = set()
    out: list[MistakePart] = []
    rows = conn.execute(
        select(progress_events.c.payload_json)
        .where(
            progress_events.c.session_id == session_id,
            progress_events.c.problem_id == problem_id,
            progress_events.c.kind == "attempt",
        )
        .order_by(text("progress_events.rowid ASC"))
    )
    for row in rows:
        payload = json.loads(row.payload_json)
        key = payload.get("part_key")
        if key is None or key in seen:
            continue
        seen.add(key)
        if payload.get("correct") is True:
            continue
        part = parts.get(key)
        answer = getattr(part, "answer", None)
        if hasattr(answer, "model_dump"):
            answer = answer.model_dump(mode="json")
        elif isinstance(answer, list):
            answer = [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in answer]
        out.append(
            MistakePart(
                part_key=key,
                child_answer=_fmt(payload.get("value")),
                correct_answer=_fmt(answer),
            )
        )
    return out


def _is_fallback(state: effective.EffectiveProblem | None) -> bool:
    return (
        state is not None
        and state.doc is not None
        and all(p.type == "fallback" for p in state.doc.parts)
    )


def _book_progress(conn: Any, grade: int, profile_id: str) -> list[BookProgress]:
    out: list[BookProgress] = []
    for book in library.grade_books(conn, grade):
        attempted = learning_progress.attempted_lesson_counts(conn, book.book_id, profile_id)
        units: list[UnitProgress] = []
        for unit in book.units:
            total = sum(lesson.problem_count for lesson in unit.lessons)
            done = sum(
                attempted.get((unit.unit_key, lesson.lesson_key), 0) for lesson in unit.lessons
            )
            if total:
                units.append(UnitProgress(unit.unit_key, unit.label, unit.title, done, total))
        if units:
            out.append(
                BookProgress(
                    book_id=book.book_id,
                    title_vi=book.title_vi,
                    attempted=sum(u.attempted for u in units),
                    total=sum(u.total for u in units),
                    units=units,
                )
            )
    return out


def dashboard(conn: Any, profile_id: str, today: date) -> Dashboard:
    profile = conn.execute(
        select(parent_profiles.c.name, parent_profiles.c.grade).where(
            parent_profiles.c.id == profile_id
        )
    ).one_or_none()
    if profile is None:
        raise ProfileNotFound(profile_id)

    sessions = _completed_sessions(conn, profile_id)
    states = {
        s.problem_id: s
        for s in effective.load_effective(
            conn, {pid for sess in sessions for pid in sess.problem_ids}, include_retired=True
        )
    }
    week_start, week_end = _week_bounds(today)
    window_start = today - timedelta(days=WEAK_CONCEPT_WINDOW_DAYS - 1)
    for s in sessions:
        s.fallback = {pid for pid in s.problem_ids if _is_fallback(states.get(pid))}
        if s.day >= min(week_start, window_start):
            s.seconds = session_seconds(conn, s.id)

    days = _day_rows(sessions, today)

    # Weak Concepts: last 4 calendar weeks; visible, graded Problems only.
    tallies: dict[str, list[int]] = {}
    for s in sessions:
        if not (window_start <= s.day <= today):
            continue
        for pid in s.problem_ids:
            state = states.get(pid)
            if pid in s.fallback or state is None or not state.visible or state.doc is None:
                continue
            for concept_id in state.doc.concept_ids:
                tally = tallies.setdefault(concept_id, [0, 0])
                tally[0] += 1
                tally[1] += pid not in s.wrong
    ranked = sorted(
        ((cid, n, ok) for cid, (n, ok) in tallies.items() if n >= WEAK_CONCEPT_MIN_ATTEMPTS),
        key=lambda t: (t[2] / t[1], -t[1], t[0]),
    )[:WEAK_CONCEPT_LIMIT]
    names = {
        r.concept_id: r.name_vi
        for r in conn.execute(
            select(content_review_concepts.c.concept_id, content_review_concepts.c.name_vi).where(
                content_review_concepts.c.concept_id.in_([c[0] for c in ranked])
            )
        )
    }
    weak = [WeakConcept(cid, names.get(cid, cid), n, ok, ok / n) for cid, n, ok in ranked]

    # Recent mistakes: newest completed Session first, Session order within it.
    mistakes: list[RecentMistake] = []
    for s in sorted(sessions, key=lambda x: x.completed_at, reverse=True):
        if len(mistakes) >= RECENT_MISTAKES_LIMIT:
            break
        for pid in s.problem_ids:
            state = states.get(pid)
            if pid not in s.wrong or pid in s.fallback or state is None:
                continue
            if not state.visible or state.doc is None:
                continue
            parts = _wrong_parts(conn, s.id, pid, state)
            if not parts:
                continue
            mistakes.append(RecentMistake(pid, state.doc.display_label, s.completed_at, parts))
            if len(mistakes) >= RECENT_MISTAKES_LIMIT:
                break

    open_count = conn.execute(
        select(func.count())
        .select_from(progress_retry_items)
        .where(
            progress_retry_items.c.profile_id == profile_id,
            progress_retry_items.c.resolved_at.is_(None),
        )
    ).scalar_one()

    return Dashboard(
        profile_id=profile_id,
        name=profile.name,
        grade=profile.grade,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        stars=learning_scoring.total_stars(conn, profile_id),
        streak=compute_streak(conn, profile_id, today),
        badges=[
            BadgeMetric(b.badge_key, b.earned, b.earned_at)
            for b in learning_badges.profile_badges(conn, profile_id)
        ],
        retry_due_count=len(learning_retry.due_problem_ids(conn, profile_id, today)),
        retry_open_count=int(open_count),
        days=days,
        week=_week_totals(days, sessions, today),
        books=_book_progress(conn, profile.grade, profile_id),
        weak_concepts=weak,
        recent_mistakes=mistakes,
        assignments=learning_assignments.list_for_profile(conn, profile_id, today),
    )
