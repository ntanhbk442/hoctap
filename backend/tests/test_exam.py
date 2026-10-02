"""Story 8.1: exam mode -- the I/O matrix rows. Exam mode mirrors Quiz mode's play
mechanics (no feedback until submit, one grading pass) but is a STRICT SUBSET of its
reward effects: zero Stars, zero Retry Queue rows, zero Streak contribution (see this
story's spec Design Notes -- an earlier framing of "matches quiz exactly" was wrong).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from test_sessions import (
    API,
    BOOK,
    LESSON,
    SETUP,
    UNIT,
    Pub,
    _attempt,
    _post,
    make_doc,
)

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.review.models import content_review_concepts, content_review_problem_concepts
from hoctap.learning.models import progress_retry_items, progress_stars
from hoctap.learning.summary import compute_streak
from hoctap.parent import service as parent_service
from hoctap.parent.models import parent_profiles

# Orchestrator's Independent Audit (2026-10-03): `app.state.clock` is pinned (mirrors
# `test_assignments.py`'s established pattern) so `assigned_date` validation's "not in the
# past" check doesn't depend on the real wall clock -- two tests below hardcode
# `assigned_date: "2026-10-02"`, which genuinely broke the moment real time crossed into
# 2026-10-03 (`DATE_IN_PAST`), the exact same class of flaky-hardcoded-date bug already
# found and fixed in this project's Epic 3 audit.
NOW = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)
AT = "2026-10-02T10:00:00+00:00"
RIGHT_A = [{"key": "s1", "value": "5"}]
RIGHT_B = [{"key": "s1", "value": "3"}]
WRONG = [{"key": "s1", "value": "0"}]
ASSIGN_API = "/api/v1/parent/assignments"


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        app.state.clock = lambda: NOW
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def profile_id(client: TestClient) -> str:
    return client.post("/api/v1/setup", json=SETUP).json()["id"]


def _enable_exams(engine: Engine, profile_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(parent_profiles)
            .where(parent_profiles.c.id == profile_id)
            .values(exams_enabled=True)
        )


def _grade_scope_ref(count: int = 100, time_limit_s: int = 600) -> dict[str, Any]:
    return {
        "kind": "exam",
        "scope": {"kind": "grade"},
        "count": count,
        "time_limit_s": time_limit_s,
    }


def _book_unit_ref(
    unit_keys: list[str] | None = None, count: int = 100, time_limit_s: int = 600
) -> dict[str, Any]:
    return {
        "kind": "exam",
        "scope": {"kind": "book_unit", "book_id": BOOK, "unit_keys": unit_keys},
        "count": count,
        "time_limit_s": time_limit_s,
    }


def _start(client: TestClient, profile_id: str, ref: dict[str, Any]):
    return client.post(API, json={"profile_id": profile_id, "ref": ref})


def _event(kind: str, problem_id: str | None = None, payload: dict[str, Any] | None = None):
    return {
        "id": str(uuid.uuid7()),
        "kind": kind,
        "problem_id": problem_id,
        "payload": payload or {},
        "occurred_at": AT,
    }


def _stars(engine: Engine, sid: str | None = None) -> list[Any]:
    with engine.connect() as conn:
        q = select(progress_stars)
        if sid is not None:
            q = q.where(progress_stars.c.session_id == sid)
        return list(conn.execute(q))


def _retry_rows(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(select(progress_retry_items)))


# --- EXAMS_DISABLED gate --------------------------------------------------------------


def test_start_exam_disabled_by_default_returns_403(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    resp = _start(client, profile_id, _grade_scope_ref())
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "EXAMS_DISABLED"


def test_start_exam_enabled_succeeds(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)(make_doc("bai-1"))
    _enable_exams(engine, profile_id)
    resp = _start(client, profile_id, _grade_scope_ref(count=5, time_limit_s=900))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "exam"
    assert body["time_limit_s"] == 900
    assert len(body["problem_ids"]) == 1


# --- Scope kinds ------------------------------------------------------------------------


def test_start_exam_book_unit_bounded_only_draws_from_that_unit(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    from hoctap.content.catalog.service import (
        BookRow,
        LessonRow,
        ProblemInput,
        UnitRow,
        publish_problems,
        upsert_books,
    )
    from hoctap.content.review import service as review

    other_unit_doc = make_doc("other")
    other_unit_doc.update(unit_key="tuan-6", problem_id=f"{BOOK}.tuan-6.{LESSON}.other")
    Pub(engine)(make_doc("bai-1"), make_doc("bai-2"))
    with engine.begin() as conn:
        upsert_books(
            conn, [BookRow(BOOK, "2020", 1, 1, "Toán 1 – 2020", f"{BOOK}.pdf", 10, 1, "f")]
        )
        publish_problems(
            conn,
            BOOK,
            units=[UnitRow(BOOK, "tuan-6", "TUẦN 6", "", 600)],
            lessons=[LessonRow(BOOK, "tuan-6", LESSON, "Tiết 2", "", 601)],
            problems=[
                ProblemInput(
                    doc=other_unit_doc, position=1, needs_review=False, verify_status="agree",
                    duplicate=False,
                )
            ],
        )
        review.record_concept_proposals(conn, 1, {other_unit_doc["problem_id"]: []})
    _enable_exams(engine, profile_id)
    resp = _start(client, profile_id, _book_unit_ref(unit_keys=[UNIT], count=100))
    assert resp.status_code == 201, resp.text
    assert other_unit_doc["problem_id"] not in resp.json()["problem_ids"]
    assert len(resp.json()["problem_ids"]) == 2


def test_start_exam_count_greater_than_pool_gets_whole_pool_no_error(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(*(make_doc(f"bai-{i}") for i in range(3)))
    _enable_exams(engine, profile_id)
    resp = _start(client, profile_id, _grade_scope_ref(count=50))
    assert resp.status_code == 201
    assert len(resp.json()["problem_ids"]) == 3


def test_start_exam_zero_eligible_problems_is_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    _enable_exams(engine, profile_id)
    resp = _start(client, profile_id, _grade_scope_ref())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_PROBLEM_SET"


def test_start_exam_concept_scope(client: TestClient, engine: Engine, profile_id: str) -> None:
    docs = [make_doc(f"bai-{i}") for i in range(3)]
    Pub(engine)(*docs)
    concept_id = "g1.so-sanh-so"
    with engine.begin() as conn:
        conn.execute(
            content_review_concepts.insert().values(
                concept_id=concept_id, grade=1, name_vi="So sánh", created_at="2026-10-02"
            )
        )
        conn.execute(
            content_review_problem_concepts.insert(),
            [{"problem_id": docs[0]["problem_id"], "concept_id": concept_id}],
        )
    _enable_exams(engine, profile_id)
    ref = {
        "kind": "exam",
        "scope": {"kind": "concept", "concept_ids": [concept_id]},
        "count": 100,
        "time_limit_s": 600,
    }
    resp = _start(client, profile_id, ref)
    assert resp.status_code == 201
    assert resp.json()["problem_ids"] == [docs[0]["problem_id"]]


# --- Play: no feedback until submit -----------------------------------------------------


def test_exam_attempt_response_exposes_nothing_and_queues_nothing(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    resp = _post(client, sid, profile_id, _attempt(doc["problem_id"], "a", WRONG, AT))
    assert resp.status_code == 201
    out = resp.json()[0]
    assert out["correct"] is None
    assert out["wrong_keys"] is None
    assert out["hint"] is None
    assert out["solution"] is None
    assert _retry_rows(engine) == []
    assert _stars(engine, sid) == []


@pytest.mark.parametrize(
    "kind", ["hint_requested", "solution_shown", "fallback_revealed", "self_marked"]
)
def test_help_events_rejected_in_exam(
    client: TestClient, engine: Engine, profile_id: str, kind: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    resp = _post(client, sid, profile_id, _event(kind, doc["problem_id"], {"correct": True}))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NOT_ALLOWED_IN_QUIZ"


def test_exam_submitted_rejected_on_non_exam_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    lesson_ref = {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON}
    sid = client.post(API, json={"profile_id": profile_id, "ref": lesson_ref}).json()["id"]
    resp = _post(client, sid, profile_id, _event("exam_submitted"))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NOT_AN_EXAM_SESSION"


def test_quiz_submitted_rejected_on_exam_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    resp = _post(client, sid, profile_id, _event("quiz_submitted"))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NOT_A_QUIZ_SESSION"


# --- Submit: grading happens, nothing is rewarded ---------------------------------------


def test_submit_grades_correctly_but_awards_zero_stars_zero_retry_zero_streak(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, bad = make_doc("bai-1"), make_doc("bai-2")
    Pub(engine)(good, bad)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]

    _post(
        client, sid, profile_id,
        _attempt(good["problem_id"], "a", RIGHT_A, AT),
        _attempt(good["problem_id"], "b", RIGHT_B, AT),
        _attempt(bad["problem_id"], "a", WRONG, AT),
        _attempt(bad["problem_id"], "b", RIGHT_B, AT),
    )  # fmt: skip

    resp = _post(client, sid, profile_id, _event("exam_submitted"))
    assert resp.status_code == 201, resp.text
    out = resp.json()[0]
    assert "quiz_stars_awarded" not in out or out["quiz_stars_awarded"] is None
    by_id = {r["problem_id"]: r for r in out["exam_results"]}
    assert by_id[good["problem_id"]]["correct"] is True
    assert by_id[good["problem_id"]]["solutions"] == []
    assert by_id[bad["problem_id"]]["correct"] is False
    assert [s["part_key"] for s in by_id[bad["problem_id"]]["solutions"]] == ["a"]

    # The whole point of this story: zero Stars, zero Retry Queue rows, zero Streak.
    assert _stars(engine) == []
    assert _retry_rows(engine) == []

    _post(client, sid, profile_id, _event("session_completed"))
    with engine.connect() as conn:
        streak = compute_streak(conn, profile_id, datetime(2026, 10, 2, tzinfo=UTC).date())
    assert streak == 0

    summary = client.get(f"{API}/{sid}/summary", params={"profile_id": profile_id}).json()
    assert summary["stars_earned"] == 0
    assert summary["streak"] == 0


def test_unanswered_problem_grades_wrong_at_submit(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    resp = _post(client, sid, profile_id, _event("exam_submitted"))
    out = resp.json()[0]
    assert out["exam_results"][0]["correct"] is False


def test_resend_and_second_submit_return_stored_result_without_double_effects(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, bad = make_doc("bai-1"), make_doc("bai-2")
    Pub(engine)(good, bad)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    _post(
        client, sid, profile_id,
        _attempt(good["problem_id"], "a", RIGHT_A, AT),
        _attempt(good["problem_id"], "b", RIGHT_B, AT),
    )  # fmt: skip
    submit = _event("exam_submitted")
    first = _post(client, sid, profile_id, submit).json()[0]
    again = _post(client, sid, profile_id, submit).json()[0]
    other = _post(client, sid, profile_id, _event("exam_submitted")).json()[0]
    assert first["exam_results"] == again["exam_results"] == other["exam_results"]
    assert _stars(engine) == []
    assert _retry_rows(engine) == []


def test_session_completed_before_submit_rejected(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _enable_exams(engine, profile_id)
    sid = _start(client, profile_id, _grade_scope_ref()).json()["id"]
    resp = _post(client, sid, profile_id, _event("session_completed"))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EXAM_NOT_SUBMITTED"


# --- Assignments (Story 8.1's parent-assign path) ---------------------------------------


def _login_parent(client: TestClient) -> None:
    resp = client.post("/api/v1/parent/login", json={"pin": SETUP["pin"]})
    assert resp.status_code == 204, resp.text


def test_parent_assigns_exam_and_child_starts_a_fresh_draw_each_time(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(*(make_doc(f"bai-{i}") for i in range(5)))
    _enable_exams(engine, profile_id)
    _login_parent(client)
    resp = client.post(
        ASSIGN_API,
        json={
            "profile_id": profile_id,
            "exam": {"scope": {"kind": "grade"}, "count": 2, "time_limit_s": 600},
            "assigned_date": "2026-10-02",
        },
    )
    assert resp.status_code == 201, resp.text
    assignment = resp.json()
    assert assignment["ref_kind"] == "exam"
    assert assignment["exam_count"] == 2
    assert assignment["exam_time_limit_s"] == 600
    assert assignment["exam_scope"] == {"kind": "grade"}

    client.cookies.clear()  # child-facing POST /sessions needs no parent cookie
    ref = {
        "kind": "exam",
        "scope": assignment["exam_scope"],
        "count": assignment["exam_count"],
        "time_limit_s": assignment["exam_time_limit_s"],
    }
    first = client.post(
        API, json={"profile_id": profile_id, "ref": ref, "assignment_id": assignment["id"]}
    )
    assert first.status_code == 201, first.text
    assert len(first.json()["problem_ids"]) == 2
    sid = first.json()["id"]
    client.post(
        f"{API}/{sid}/events",
        json={"profile_id": profile_id, "events": [_event("exam_submitted")]},
    )
    client.post(
        f"{API}/{sid}/events",
        json={"profile_id": profile_id, "events": [_event("session_completed")]},
    )
    # The Assignment itself is now DONE (same one-shot semantics a Lesson Assignment
    # already has) -- a RETAKE of the same scope/count/time_limit_s is an on-demand exam
    # (no `assignment_id`), which re-resolves its OWN fresh random draw every time (AD-9:
    # an Assignment -- and, by the same resolve()-at-start rule, every exam start -- is
    # never a frozen Problem list).
    second = client.post(API, json={"profile_id": profile_id, "ref": ref})
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]
    assert len(second.json()["problem_ids"]) == 2


def test_assignment_ref_mismatch_rejected(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(*(make_doc(f"bai-{i}") for i in range(5)))
    _enable_exams(engine, profile_id)
    _login_parent(client)
    resp = client.post(
        ASSIGN_API,
        json={
            "profile_id": profile_id,
            "exam": {"scope": {"kind": "grade"}, "count": 2, "time_limit_s": 600},
            "assigned_date": "2026-10-02",
        },
    )
    assignment = resp.json()
    client.cookies.clear()
    mismatched_ref = {
        "kind": "exam",
        "scope": {"kind": "grade"},
        "count": 999,  # doesn't match the assignment's stored count
        "time_limit_s": 600,
    }
    resp = client.post(
        API,
        json={
            "profile_id": profile_id,
            "ref": mismatched_ref,
            "assignment_id": assignment["id"],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ASSIGNMENT_REF_MISMATCH"
