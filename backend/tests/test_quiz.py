"""Story 3.4: quiz mode for the weekly "Phiếu tự luyện cuối tuần" (I/O matrix rows)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from test_sessions import (
    API,
    LESSON,
    SETUP,
    Pub,
    _attempt,
    _lesson_ref,
    _post,
    make_doc,
    make_fallback_doc,
)

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.catalog.models import content_catalog_lessons
from hoctap.learning.models import progress_retry_items, progress_stars
from hoctap.parent import service as parent_service

HOME = "/api/v1/library/home"
DAY1 = datetime(2026, 9, 29, 5, 0, tzinfo=UTC)
AT = "2026-09-29T10:00:00+00:00"
RIGHT_A = [{"key": "s1", "value": "5"}]
RIGHT_B = [{"key": "s1", "value": "3"}]
WRONG = [{"key": "s1", "value": "0"}]


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def profile_id(client: TestClient) -> str:
    return client.post("/api/v1/setup", json=SETUP).json()["id"]


def _publish_quiz(engine: Engine, *docs: dict[str, Any]) -> None:
    Pub(engine)(*docs)
    with engine.begin() as conn:
        conn.execute(update(content_catalog_lessons).values(is_quiz_sheet=1))


def _start(client: TestClient, profile_id: str, body_mode: str | None = None):
    body: dict[str, Any] = {"profile_id": profile_id, "ref": _lesson_ref()}
    if body_mode:
        body["mode"] = body_mode
    return client.post(API, json=body)


def _event(kind: str, problem_id: str | None = None, payload: dict[str, Any] | None = None):
    return {
        "id": str(uuid.uuid7()),
        "kind": kind,
        "problem_id": problem_id,
        "payload": payload or {},
        "occurred_at": AT,
    }


def _answer_all_right(client: TestClient, sid: str, pid: str, doc: dict[str, Any]) -> None:
    resp = _post(
        client,
        sid,
        pid,
        _attempt(doc["problem_id"], "a", RIGHT_A, AT),
        _attempt(doc["problem_id"], "b", RIGHT_B, AT),
    )
    assert resp.status_code == 201, resp.text


def _stars(engine: Engine, sid: str) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(select(progress_stars).where(progress_stars.c.session_id == sid)))


def _retry_rows(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(select(progress_retry_items)))


def test_quiz_lesson_starts_as_quiz_session_and_bundle_reports_it(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    _publish_quiz(engine, make_doc("bai-1"))
    session = _start(client, profile_id).json()
    assert session["mode"] == "quiz"
    bundle = client.get(f"{API}/{session['id']}/bundle", params={"profile_id": profile_id})
    assert bundle.json()["mode"] == "quiz"


def test_client_cannot_send_quiz_mode(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)(make_doc("bai-1"))
    assert _start(client, profile_id, "quiz").status_code == 422
    assert _start(client, profile_id).json()["mode"] == "practice"


def test_quiz_attempt_response_exposes_nothing_and_queues_nothing(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    _publish_quiz(engine, doc)
    sid = _start(client, profile_id).json()["id"]
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
def test_help_events_rejected_in_quiz(
    client: TestClient, engine: Engine, profile_id: str, kind: str
) -> None:
    doc = make_doc("bai-1")
    _publish_quiz(engine, doc)
    sid = _start(client, profile_id).json()["id"]
    resp = _post(client, sid, profile_id, _event(kind, doc["problem_id"], {"correct": True}))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NOT_ALLOWED_IN_QUIZ"


def test_quiz_submitted_rejected_in_non_quiz_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    sid = _start(client, profile_id).json()["id"]
    resp = _post(client, sid, profile_id, _event("quiz_submitted"))
    assert resp.status_code == 422


def test_submit_grades_3_or_0_queues_wrong_and_reveals_solutions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, bad, half, blank = (make_doc(f"bai-{i}") for i in range(4))
    _publish_quiz(engine, good, bad, half, blank)
    sid = _start(client, profile_id).json()["id"]
    _answer_all_right(client, sid, profile_id, good)
    _post(
        client,
        sid,
        profile_id,
        _attempt(bad["problem_id"], "a", WRONG, AT),
        _attempt(bad["problem_id"], "b", RIGHT_B, AT),
        _attempt(half["problem_id"], "a", RIGHT_A, AT),
    )
    # A second, corrective attempt never changes the verdict.
    _post(client, sid, profile_id, _attempt(bad["problem_id"], "a", RIGHT_A, AT))

    resp = _post(client, sid, profile_id, _event("quiz_submitted"))
    assert resp.status_code == 201, resp.text
    out = resp.json()[0]
    assert out["quiz_stars_awarded"] is True
    by_id = {r["problem_id"]: r for r in out["quiz_results"]}
    assert by_id[good["problem_id"]]["correct"] is True
    assert by_id[good["problem_id"]]["stars"] == 3
    assert by_id[good["problem_id"]]["solutions"] == []
    for wrong in (bad, half, blank):
        r = by_id[wrong["problem_id"]]
        assert r["correct"] is False
        assert r["stars"] == 0
        assert r["solutions"]
    assert [s["part_key"] for s in by_id[bad["problem_id"]]["solutions"]] == ["a"]
    assert [s["part_key"] for s in by_id[half["problem_id"]]["solutions"]] == ["b"]

    assert sum(s.stars for s in _stars(engine, sid)) == 3
    assert len(_stars(engine, sid)) == 4
    queued = {r.problem_id for r in _retry_rows(engine) if r.resolved_at is None}
    assert queued == {bad["problem_id"], half["problem_id"], blank["problem_id"]}

    _post(client, sid, profile_id, _event("session_completed"))
    summary = client.get(f"{API}/{sid}/summary", params={"profile_id": profile_id}).json()
    assert summary["stars_earned"] == 3


def test_resend_and_second_submit_return_stored_result_without_double_effects(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, bad = make_doc("bai-1"), make_doc("bai-2")
    _publish_quiz(engine, good, bad)
    sid = _start(client, profile_id).json()["id"]
    _answer_all_right(client, sid, profile_id, good)
    submit = _event("quiz_submitted")
    first = _post(client, sid, profile_id, submit).json()[0]
    again = _post(client, sid, profile_id, submit).json()[0]
    other = _post(client, sid, profile_id, _event("quiz_submitted")).json()[0]
    assert first["quiz_results"] == again["quiz_results"] == other["quiz_results"]
    assert len(_stars(engine, sid)) == 2
    assert len(_retry_rows(engine)) == 1


def test_fallback_problem_is_retry_with_solution_but_not_queued(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    fb = make_fallback_doc("bai-1")
    _publish_quiz(engine, fb)
    sid = _start(client, profile_id).json()["id"]
    out = _post(client, sid, profile_id, _event("quiz_submitted")).json()[0]
    result = out["quiz_results"][0]
    assert result["correct"] is False
    assert result["stars"] == 0
    assert result["solutions"]
    assert _retry_rows(engine) == []


def test_session_completed_requires_submit(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    _publish_quiz(engine, make_doc("bai-1"))
    sid = _start(client, profile_id).json()["id"]
    resp = _post(client, sid, profile_id, _event("session_completed"))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "QUIZ_NOT_SUBMITTED"


def test_retake_is_graded_and_queued_but_awards_no_stars(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, bad = make_doc("bai-1"), make_doc("bai-2")
    _publish_quiz(engine, good, bad)
    first = _start(client, profile_id).json()["id"]
    _answer_all_right(client, first, profile_id, good)
    _post(client, first, profile_id, _event("quiz_submitted"))
    assert sum(s.stars for s in _stars(engine, first)) == 3

    second = _start(client, profile_id).json()["id"]
    _answer_all_right(client, second, profile_id, good)
    _answer_all_right(client, second, profile_id, bad)
    out = _post(client, second, profile_id, _event("quiz_submitted")).json()[0]
    assert out["quiz_stars_awarded"] is False
    assert all(r["correct"] for r in out["quiz_results"])
    assert all(r["stars"] == 0 for r in out["quiz_results"])
    assert _stars(engine, second) == []


def test_retake_wrong_problem_feeds_retry_queue(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    _publish_quiz(engine, doc)
    first = _start(client, profile_id).json()["id"]
    _answer_all_right(client, first, profile_id, doc)
    _post(client, first, profile_id, _event("quiz_submitted"))
    second = _start(client, profile_id).json()["id"]
    _post(client, second, profile_id, _attempt(doc["problem_id"], "a", WRONG, AT))
    _post(client, second, profile_id, _event("quiz_submitted"))
    assert [r.problem_id for r in _retry_rows(engine)] == [doc["problem_id"]]


def test_open_quiz_resumes_from_home_and_bundle_is_session_scoped(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    good, other = make_doc("bai-1"), make_doc("bai-2")
    _publish_quiz(engine, good, other)
    sid = _start(client, profile_id).json()["id"]
    _answer_all_right(client, sid, profile_id, good)
    home = client.get(f"{HOME}/{profile_id}").json()
    assert home["continue_session"]["session_id"] == sid
    bundle = client.get(f"{API}/{sid}/bundle", params={"profile_id": profile_id}).json()
    assert [p["attempted"] for p in bundle["problems"]] == [True, False]
    assert _stars(engine, sid) == [] and _retry_rows(engine) == []


def test_quiz_session_counts_toward_retry_queue_exit(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)  # practice lesson
    client.app.state.clock = lambda: DAY1  # type: ignore[attr-defined]
    s1 = _start(client, profile_id).json()["id"]
    _post(client, s1, profile_id, _attempt(doc["problem_id"], "a", WRONG, AT))
    client.app.state.clock = lambda: DAY1 + timedelta(days=1)  # type: ignore[attr-defined]
    s2 = _start(client, profile_id).json()["id"]
    _answer_all_right(client, s2, profile_id, doc)
    assert _retry_rows(engine)[0].resolved_at is None
    with engine.begin() as conn:
        conn.execute(update(content_catalog_lessons).values(is_quiz_sheet=1))
    client.app.state.clock = lambda: DAY1 + timedelta(days=2)  # type: ignore[attr-defined]
    s3 = _start(client, profile_id).json()["id"]
    _answer_all_right(client, s3, profile_id, doc)
    _post(client, s3, profile_id, _event("quiz_submitted"))
    assert _retry_rows(engine)[0].resolved_at is not None
    assert [s.stars for s in _stars(engine, s3)] == [3]


def test_library_marks_quiz_sheet(client: TestClient, engine: Engine, profile_id: str) -> None:
    _publish_quiz(engine, make_doc("bai-1"))
    books = client.get("/api/v1/library/grades/1/books", params={"profile_id": profile_id}).json()
    lessons = [
        lesson
        for b in books
        for u in b["units"]
        for lesson in u["lessons"]
        if lesson["lesson_key"] == LESSON
    ]
    assert lessons and lessons[0]["is_quiz_sheet"] is True
