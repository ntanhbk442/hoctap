"""Story 3.3: Retry Queue due-ness, exit rules, and the `kind: "retry"` Session start."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from test_sessions import (
    API,
    BOOK,
    LESSON,
    SETUP,
    UNIT,
    Pub,
    _attempt,
    _post,
    _start,
    make_doc,
    make_fallback_doc,
)

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.review import service as review
from hoctap.learning.models import progress_retry_items, progress_stars
from hoctap.parent import service as parent_service

HOME = "/api/v1/library/home"
# 2026-09-29 12:00 Vietnam time = 05:00 UTC.
DAY1 = datetime(2026, 9, 29, 5, 0, tzinfo=UTC)
DAY2 = DAY1 + timedelta(days=1)

WRONG = [{"key": "s1", "value": "0"}]
RIGHT = [{"key": "s1", "value": "5"}]


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    _NOW[0] = DAY1
    with TestClient(app) as c:
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def profile_id(client: TestClient) -> str:
    return client.post("/api/v1/setup", json=SETUP).json()["id"]


_NOW = [DAY1]  # the test clock, also used as the events' device `occurred_at`


def _set_clock(client: TestClient, when: datetime) -> None:
    _NOW[0] = when
    client.app.state.clock = lambda: when  # type: ignore[attr-defined]


def _at() -> str:
    return _NOW[0].isoformat()


def _row(engine: Engine, problem_id: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            select(progress_retry_items).where(progress_retry_items.c.problem_id == problem_id)
        ).one()


def _attempt_at(problem_id: str, value: Any) -> dict[str, Any]:
    return _attempt(problem_id, "a", value, _at())


def _all_right(client: TestClient, session_id: str, profile_id: str, problem_id: str):
    """First-try-correct on both Parts of `make_doc` (a: 5, b: 3)."""
    return _post(
        client,
        session_id,
        profile_id,
        _attempt(problem_id, "a", RIGHT, _at()),
        _attempt(problem_id, "b", [{"key": "s1", "value": "3"}], _at()),
    )


def _selfmark(problem_id: str, correct: bool) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "self_marked",
        "problem_id": problem_id,
        "payload": {"correct": correct},
        "occurred_at": _at(),
    }


def _due_count(client: TestClient, profile_id: str) -> int:
    return client.get(f"{HOME}/{profile_id}").json()["retry_due_count"]


def _start_retry(client: TestClient, profile_id: str):
    return client.post(
        API, json={"profile_id": profile_id, "ref": {"kind": "retry"}, "mode": "retry"}
    )


def test_same_day_repeat_wrong_updates_last_wrong_at_and_is_not_due(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _set_clock(client, DAY1)
    session = _start(client, profile_id)
    _post(client, session["id"], profile_id, _attempt_at(doc["problem_id"], WRONG))
    first = _row(engine, doc["problem_id"])
    _set_clock(client, DAY1 + timedelta(hours=2))
    _post(client, session["id"], profile_id, _attempt_at(doc["problem_id"], WRONG))
    second = _row(engine, doc["problem_id"])
    assert second.added_at == first.added_at
    assert second.last_wrong_at > first.last_wrong_at
    assert _due_count(client, profile_id) == 0
    resp = _start_retry(client, profile_id)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RETRY_QUEUE_EMPTY"


def test_next_day_item_is_due_and_retry_session_freezes_it(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc, other = make_doc("bai-1"), make_doc("bai-2")
    Pub(engine)(doc, other)
    _set_clock(client, DAY1)
    session = _start(client, profile_id)
    _post(client, session["id"], profile_id, _attempt_at(doc["problem_id"], WRONG))
    _set_clock(client, DAY2)
    assert _due_count(client, profile_id) == 1
    resp = _start_retry(client, profile_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["problem_ids"] == [doc["problem_id"]]
    assert body["mode"] == "retry"
    assert body["ref_kind"] == "retry"


def _clean_session(client: TestClient, profile_id: str, problem_id: str):
    session = _start(client, profile_id)
    _all_right(client, session["id"], profile_id, problem_id)
    return session


def test_graded_problem_needs_two_qualifying_sessions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(pid, WRONG))
    # Correcting it in the SAME Session no longer resolves (not first-try).
    _all_right(client, s0["id"], profile_id, pid)
    assert _row(engine, pid).resolved_at is None

    _set_clock(client, DAY2)
    _clean_session(client, profile_id, pid)
    assert _row(engine, pid).resolved_at is None
    _set_clock(client, DAY2 + timedelta(hours=1))
    _clean_session(client, profile_id, pid)
    assert _row(engine, pid).resolved_at is not None


def test_replay_sessions_never_count(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(pid, WRONG))
    done = {
        "id": str(uuid.uuid7()),
        "kind": "session_completed",
        "problem_id": None,
        "payload": {},
        "occurred_at": _at(),
    }
    _post(client, s0["id"], profile_id, done)
    _set_clock(client, DAY2)
    for _ in range(2):
        resp = client.post(
            API,
            json={
                "profile_id": profile_id,
                "ref": {"kind": "replay", "source_session_id": s0["id"]},
                "mode": "replay",
            },
        )
        assert resp.status_code == 201, resp.text
        _all_right(client, resp.json()["id"], profile_id, pid)
    assert _row(engine, pid).resolved_at is None
    with engine.connect() as conn:  # replays award no Stars at all, so nothing to count
        assert conn.execute(select(progress_stars).where(progress_stars.c.stars == 3)).all() == []


def test_retry_session_with_completely_empty_queue_is_422(
    client: TestClient, profile_id: str
) -> None:
    resp = _start_retry(client, profile_id)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RETRY_QUEUE_EMPTY"


def test_replay_session_does_not_count_as_one_of_the_two_qualifying_sessions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(pid, WRONG))
    done = {
        "id": str(uuid.uuid7()),
        "kind": "session_completed",
        "problem_id": None,
        "payload": {},
        "occurred_at": _at(),
    }
    _post(client, s0["id"], profile_id, done)
    _set_clock(client, DAY2)
    replay = client.post(
        API,
        json={
            "profile_id": profile_id,
            "ref": {"kind": "replay", "source_session_id": s0["id"]},
            "mode": "replay",
        },
    )
    assert replay.status_code == 201, replay.text
    _all_right(client, replay.json()["id"], profile_id, pid)
    _clean_session(client, profile_id, pid)  # one real qualifying Session
    assert _row(engine, pid).resolved_at is None  # replay must not have been the second


def test_fallback_needs_two_self_marks_in_two_sessions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _selfmark(pid, False))
    assert _row(engine, pid).last_wrong_at is not None

    _set_clock(client, DAY2)
    s1 = _start(client, profile_id)
    # Two "đúng" inside one Session count once.
    _post(client, s1["id"], profile_id, _selfmark(pid, True))
    _post(client, s1["id"], profile_id, _selfmark(pid, True))
    assert _row(engine, pid).resolved_at is None

    s2 = _start(client, profile_id)
    _post(client, s2["id"], profile_id, _selfmark(pid, True))
    assert _row(engine, pid).resolved_at is not None


def test_retry_mode_session_is_played_and_counts_towards_exit(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(pid, WRONG))
    _set_clock(client, DAY2)
    retry = _start_retry(client, profile_id).json()
    assert retry["mode"] == "retry"
    _all_right(client, retry["id"], profile_id, pid)
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_stars).where(progress_stars.c.session_id == retry["id"])
        ).all()
    assert [r.stars for r in rows] == [3]
    assert _row(engine, pid).resolved_at is None
    _set_clock(client, DAY2 + timedelta(hours=1))
    _clean_session(client, profile_id, pid)  # second qualifying Session (practice)
    assert _row(engine, pid).resolved_at is not None


def test_retry_ref_without_mode_starts_a_retry_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(doc["problem_id"], WRONG))
    _set_clock(client, DAY2)
    resp = client.post(API, json={"profile_id": profile_id, "ref": {"kind": "retry"}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["mode"] == "retry"


def test_mode_that_disagrees_with_ref_kind_is_rejected(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    lesson = {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON}
    for ref, mode in ((lesson, "retry"), (lesson, "replay"), ({"kind": "retry"}, "practice")):
        resp = client.post(API, json={"profile_id": profile_id, "ref": ref, "mode": mode})
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "MODE_REF_MISMATCH"


def test_repeat_wrong_attempt_resets_exit_progress(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    pid = doc["problem_id"]
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(pid, WRONG))
    _set_clock(client, DAY2)
    _clean_session(client, profile_id, pid)
    _set_clock(client, DAY2 + timedelta(hours=1))
    s2 = _start(client, profile_id)
    _post(client, s2["id"], profile_id, _attempt_at(pid, WRONG))  # a miss: progress resets
    _set_clock(client, DAY2 + timedelta(hours=2))
    _clean_session(client, profile_id, pid)
    assert _row(engine, pid).resolved_at is None  # only one clean Session since the miss
    _set_clock(client, DAY2 + timedelta(hours=3))
    _clean_session(client, profile_id, pid)
    assert _row(engine, pid).resolved_at is not None


def test_hidden_problem_is_not_counted_or_served_as_due(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    _set_clock(client, DAY1)
    s0 = _start(client, profile_id)
    _post(client, s0["id"], profile_id, _attempt_at(doc["problem_id"], WRONG))
    _set_clock(client, DAY2)
    assert _due_count(client, profile_id) == 1
    with engine.begin() as conn:
        review.set_hidden(conn, doc["problem_id"], True)
    assert _due_count(client, profile_id) == 0
    assert _start_retry(client, profile_id).status_code == 422
