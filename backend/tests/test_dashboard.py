"""Story 4.2: the parent progress dashboard (`GET /parent/dashboard/{profile_id}`)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_sessions import SETUP, Pub, make_doc, make_fallback_doc

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.review.models import (
    content_review_concepts,
    content_review_problem_concepts,
    content_review_status,
)
from hoctap.learning.models import progress_events, progress_sessions
from hoctap.parent import service as parent_service

API = "/api/v1/parent/dashboard"
# 2026-09-30 is a Wednesday; its week is Mon 09-28 .. Sun 10-04 (Asia/Ho_Chi_Minh).
NOW = datetime(2026, 9, 30, 5, 0, tzinfo=UTC)  # 12:00 local
CONCEPT = "g1.cong-trong-pham-vi-10"


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


def _dash(client: TestClient, profile_id: str) -> dict[str, Any]:
    resp = client.get(f"{API}/{profile_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _session(
    engine: Engine,
    profile_id: str,
    completed_at: str | None,
    problem_ids: list[str],
    *,
    mode: str = "practice",
    attempts: list[tuple[str, str, bool, Any]] = (),  # type: ignore[assignment]
    event_times: list[str] = (),  # type: ignore[assignment]
) -> str:
    sid = str(uuid.uuid7())
    started = completed_at or "2026-09-30T01:00:00+00:00"
    with engine.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(
                id=sid,
                profile_id=profile_id,
                ref_kind="lesson",
                ref_key="x",
                mode=mode,
                problem_ids_json=json.dumps(problem_ids),
                chunk_size=10,
                started_at=started,
                completed_at=completed_at,
            )
        )
        rows = [
            (pid, "attempt", {"part_key": part, "value": value, "correct": ok}, started)
            for pid, part, ok, value in attempts
        ] + [(None, "session_started", {}, t) for t in event_times]
        for pid, kind, payload, at in rows:
            conn.execute(
                progress_events.insert().values(
                    id=str(uuid.uuid7()),
                    session_id=sid,
                    profile_id=profile_id,
                    kind=kind,
                    problem_id=pid,
                    payload_json=json.dumps(payload),
                    occurred_at=at,
                    received_at="2026-10-05T00:00:00+00:00",
                )
            )
    return sid


def _link_concept(engine: Engine, problem_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            content_review_concepts.insert()
            .prefix_with("OR IGNORE")
            .values(concept_id=CONCEPT, grade=1, name_vi="Cộng trong phạm vi 10", created_at="x")
        )
        conn.execute(
            content_review_problem_concepts.insert().values(
                problem_id=problem_id, concept_id=CONCEPT
            )
        )


def test_no_cookie_is_401(client: TestClient, profile_id: str) -> None:
    client.cookies.clear()
    assert client.get(f"{API}/{profile_id}").status_code == 401


def test_unknown_profile_404(client: TestClient, profile_id: str) -> None:
    resp = client.get(f"{API}/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_new_child_all_zero(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)(make_doc("bai-1"))
    d = _dash(client, profile_id)
    assert (d["stars"], d["streak"], d["retry_due_count"]) == (0, 0, 0)
    assert len(d["days"]) == 7
    assert d["days"][0]["date"] == "2026-09-28"
    assert all(day["sessions"] == 0 and day["accuracy"] is None for day in d["days"])
    assert d["week"]["sessions"] == 0 and d["week"]["accuracy"] is None
    assert d["weak_concepts"] == [] and d["recent_mistakes"] == []
    assert [b["earned"] for b in d["badges"]] == [False, False, False]
    assert d["books"][0]["total"] == 1 and d["books"][0]["attempted"] == 0


def test_happy_path_week_rows_time_mistakes_and_progress(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc1, doc2 = make_doc("bai-1"), make_doc("bai-2")
    Pub(engine)(doc1, doc2)
    p1, p2 = doc1["problem_id"], doc2["problem_id"]
    # Tuesday 09-29: bai-1 right, bai-2 wrong first (a: child typed 9, key is 5).
    # Events 03:00, 03:02, then a 40-minute idle gap capped at 5 min -> 7 minutes.
    _session(
        engine,
        profile_id,
        "2026-09-29T03:42:00+00:00",
        [p1, p2],
        attempts=[
            (p1, "a", True, [{"key": "s1", "value": "5"}]),
            (p2, "a", False, [{"key": "s1", "value": "9"}]),
        ],
        event_times=[
            "2026-09-29T03:00:00+00:00",
            "2026-09-29T03:02:00+00:00",
            "2026-09-29T03:42:00+00:00",
        ],
    )
    d = _dash(client, profile_id)
    tue = d["days"][1]
    assert tue["sessions"] == 1
    assert tue["minutes"] == 7
    assert (tue["first_try_correct"], tue["problems"]) == (1, 2)
    assert tue["accuracy"] == 0.5
    assert d["days"][0]["sessions"] == 0
    assert [x["future"] for x in d["days"]] == [False, False, False] + [True] * 4
    assert d["week"]["sessions"] == 1 and d["week"]["accuracy"] == 0.5
    assert d["streak"] == 1
    (m,) = d["recent_mistakes"]
    assert m["problem_id"] == p2
    assert m["parts"] == [{"part_key": "a", "child_answer": "9", "correct_answer": "5"}]
    # progress: attempted-visible over visible (both had attempt events)
    assert d["books"][0]["attempted"] == 2 and d["books"][0]["total"] == 2
    assert d["books"][0]["units"][0]["total"] == 2


def test_fallback_problems_never_in_ratio(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc, fb = make_doc("bai-1"), make_fallback_doc("bai-2")
    Pub(engine)(doc, fb)
    _session(
        engine,
        profile_id,
        "2026-09-30T02:00:00+00:00",
        [doc["problem_id"], fb["problem_id"]],
        attempts=[(doc["problem_id"], "a", True, [{"key": "s1", "value": "5"}])],
    )
    day = _dash(client, profile_id)["days"][2]
    assert (day["first_try_correct"], day["problems"], day["self_check"]) == (1, 1, 1)
    assert day["accuracy"] == 1.0
    assert _dash(client, profile_id)["recent_mistakes"] == []


def test_concept_needs_five_attempts(client: TestClient, engine: Engine, profile_id: str) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _link_concept(engine, pid)
    for i in range(4):
        _session(
            engine, profile_id, f"2026-09-2{i + 1}T03:00:00+00:00", [pid],
            attempts=[(pid, "a", False, [{"key": "s1", "value": "1"}])],
        )  # fmt: skip
    assert _dash(client, profile_id)["weak_concepts"] == []
    _session(
        engine, profile_id, "2026-09-25T03:00:00+00:00", [pid],
        attempts=[(pid, "a", True, [{"key": "s1", "value": "5"}])],
    )  # fmt: skip
    (weak,) = _dash(client, profile_id)["weak_concepts"]
    assert weak["concept_id"] == CONCEPT
    assert (weak["attempts"], weak["first_try_correct"]) == (5, 1)
    assert weak["accuracy"] == 0.2


def test_old_attempts_excluded_from_weak_concepts(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _link_concept(engine, pid)
    for day in range(1, 6):  # five weeks+ ago: outside the 4-week window
        _session(
            engine, profile_id, f"2026-08-0{day}T03:00:00+00:00", [pid],
            attempts=[(pid, "a", False, [{"key": "s1", "value": "1"}])],
        )  # fmt: skip
    assert _dash(client, profile_id)["weak_concepts"] == []


def test_monday_morning_shows_seven_zero_rows(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _session(
        engine, profile_id, "2026-09-27T03:00:00+00:00", [doc["problem_id"]],  # last Sunday
        attempts=[(doc["problem_id"], "a", True, [{"key": "s1", "value": "5"}])],
    )  # fmt: skip
    client.app.state.clock = lambda: datetime(2026, 9, 28, 1, 0, tzinfo=UTC)  # type: ignore[attr-defined]
    assert client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204
    d = _dash(client, profile_id)
    assert d["days"][0]["date"] == "2026-09-28" and not d["days"][0]["future"]
    assert all(x["sessions"] == 0 for x in d["days"])
    assert d["week"]["sessions"] == 0


def test_quiz_counts_replay_and_unfinished_do_not(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    right = [(pid, "a", True, [{"key": "s1", "value": "5"}])]
    _session(engine, profile_id, "2026-09-30T02:00:00+00:00", [pid], mode="quiz", attempts=right)
    _session(engine, profile_id, "2026-09-30T02:30:00+00:00", [pid], mode="replay", attempts=right)
    _session(engine, profile_id, None, [pid], attempts=right)
    d = _dash(client, profile_id)
    assert d["days"][2]["sessions"] == 1
    assert d["week"]["sessions"] == 1
    assert d["week"]["problems"] == 1


def test_late_sync_counts_on_local_day(client: TestClient, engine: Engine, profile_id: str) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    # 23:55 local on Tuesday = 16:55 UTC; received_at (10-05) is irrelevant.
    _session(
        engine, profile_id, "2026-09-29T16:55:00+00:00", [pid],
        attempts=[(pid, "a", True, [{"key": "s1", "value": "5"}])],
        event_times=["2026-09-29T16:55:00+00:00"],
    )  # fmt: skip
    d = _dash(client, profile_id)
    assert d["days"][1]["sessions"] == 1 and d["days"][2]["sessions"] == 0


def test_hidden_problem_omitted_from_mistakes_and_concepts(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _link_concept(engine, pid)
    for i in range(5):
        _session(
            engine, profile_id, f"2026-09-2{i + 1}T03:00:00+00:00", [pid],
            attempts=[(pid, "a", False, [{"key": "s1", "value": "1"}])],
        )  # fmt: skip
    assert len(_dash(client, profile_id)["weak_concepts"]) == 1
    with engine.begin() as conn:
        conn.execute(
            content_review_status.insert().values(
                problem_id=pid, hidden=1, approved_hash=None, updated_at="x"
            )
        )
    d = _dash(client, profile_id)
    assert d["weak_concepts"] == [] and d["recent_mistakes"] == []


def test_switching_child_shows_only_that_child(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    other = client.post(
        "/api/v1/profiles", json={"name": "Na", "avatar": "cat", "grade": 1}
    ).json()["id"]
    _session(
        engine, profile_id, "2026-09-30T02:00:00+00:00", [doc["problem_id"]],
        attempts=[(doc["problem_id"], "a", True, [{"key": "s1", "value": "5"}])],
    )  # fmt: skip
    assert _dash(client, profile_id)["week"]["sessions"] == 1
    d = _dash(client, other)
    assert d["name"] == "Na" and d["week"]["sessions"] == 0


def test_recent_mistake_reported_flag(client: TestClient, engine: Engine, profile_id: str) -> None:
    from hoctap.content.review import service as review

    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _session(
        engine,
        profile_id,
        "2026-09-29T03:42:00+00:00",
        [pid],
        attempts=[(pid, "a", False, [{"key": "s1", "value": "9"}])],
    )
    (m,) = _dash(client, profile_id)["recent_mistakes"]
    assert m["reported"] is False
    with engine.begin() as conn:
        rid = review.add_error_report(conn, pid, "parent")
    (m,) = _dash(client, profile_id)["recent_mistakes"]
    assert m["reported"] is True
    with engine.begin() as conn:
        review.resolve_report(conn, rid)
    (m,) = _dash(client, profile_id)["recent_mistakes"]
    assert m["reported"] is False
