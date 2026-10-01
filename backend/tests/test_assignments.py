"""Story 4.3: Assignments (`/parent/assignments`, Home card, Dashboard statuses)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_sessions import BOOK, LESSON, SETUP, UNIT, Pub, make_doc

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.review import service as review_service
from hoctap.ids import new_id
from hoctap.parent import service as parent_service

API = "/api/v1/parent/assignments"
NOW = datetime(2026, 9, 30, 5, 0, tzinfo=UTC)  # 12:00 local, Wed 2026-09-30
TODAY, YESTERDAY, TOMORROW = "2026-09-30", "2026-09-29", "2026-10-01"


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


def _assign(client: TestClient, profile_id: str, date: str) -> Any:
    return client.post(
        API,
        json={
            "profile_id": profile_id,
            "book_id": BOOK,
            "unit_key": UNIT,
            "lesson_key": LESSON,
            "assigned_date": date,
        },
    )


def _home(client: TestClient, profile_id: str) -> dict[str, Any]:
    return client.get(f"/api/v1/library/home/{profile_id}").json()


def _dash(client: TestClient, profile_id: str) -> list[dict[str, Any]]:
    return client.get(f"/api/v1/parent/dashboard/{profile_id}").json()["assignments"]


def _start(client: TestClient, profile_id: str, assignment_id: str | None) -> Any:
    return client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "assignment_id": assignment_id,
            "ref": {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON},
        },
    )


def _event(client: TestClient, sid: str, profile_id: str, kind: str, pid: str | None = None):
    payload = {"part_key": "a", "value": "1"} if kind == "attempt" else {}
    return client.post(
        f"/api/v1/sessions/{sid}/events",
        json={
            "profile_id": profile_id,
            "events": [
                {
                    "id": new_id(),
                    "kind": kind,
                    "problem_id": pid,
                    "payload": payload,
                    "occurred_at": NOW.isoformat(),
                }
            ],
        },
    )


def _publish(engine: Engine, n: int) -> list[str]:
    docs = [make_doc(f"b{i:02d}") for i in range(n)]
    Pub(engine)(*docs)
    return [d["problem_id"] for d in docs]


def test_requires_parent(client: TestClient, profile_id: str) -> None:
    client.cookies.clear()
    assert client.get(API, params={"profile_id": profile_id}).status_code == 401
    assert _assign(client, profile_id, TODAY).status_code == 401


def test_assign_and_list(client: TestClient, engine: Engine, profile_id: str) -> None:
    _publish(engine, 3)
    resp = _assign(client, profile_id, TOMORROW)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "todo"
    listed = client.get(API, params={"profile_id": profile_id}).json()
    assert [a["id"] for a in listed] == [resp.json()["id"]]


def test_assign_errors(client: TestClient, engine: Engine, profile_id: str) -> None:
    assert _assign(client, profile_id, TODAY).json()["error"]["code"] == "EMPTY_PROBLEM_SET"
    _publish(engine, 1)
    assert _assign(client, profile_id, YESTERDAY).status_code == 422
    assert _assign(client, "nope", TODAY).status_code == 404
    assert _assign(client, profile_id, TODAY).status_code == 201


def test_future_not_on_home_but_on_dashboard(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    _publish(engine, 2)
    _assign(client, profile_id, TOMORROW)
    assert _home(client, profile_id)["assignment"] is None
    assert _dash(client, profile_id)[0]["status"] == "todo"


def test_home_card_start_partial_complete(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    pids = _publish(engine, 12)
    aid = _assign(client, profile_id, TODAY).json()["id"]
    card = _home(client, profile_id)["assignment"]
    assert card["id"] == aid and card["status"] == "todo" and card["carried_over"] is False

    sid = _start(client, profile_id, aid).json()["id"]
    card = _home(client, profile_id)["assignment"]
    assert (card["status"], card["part"], card["part_count"], card["session_id"]) == (
        "doing",
        1,
        2,
        sid,
    )
    for pid in pids[:10]:
        assert _event(client, sid, profile_id, "attempt", pid).status_code in (200, 201)
    card = _home(client, profile_id)["assignment"]
    assert (card["part"], card["part_count"]) == (2, 2)
    dash = _dash(client, profile_id)[0]
    assert (dash["status"], dash["part"], dash["part_count"]) == ("doing", 2, 2)

    assert _event(client, sid, profile_id, "session_completed").status_code in (200, 201)
    assert _home(client, profile_id)["assignment"] is None
    assert _dash(client, profile_id)[0]["status"] == "done"
    assert _event(client, sid, profile_id, "session_completed").status_code in (200, 201)  # no-op
    assert _dash(client, profile_id)[0]["status"] == "done"
    assert _start(client, profile_id, aid).status_code == 409


def test_lesson_done_outside_card_stays_open(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    _publish(engine, 2)
    aid = _assign(client, profile_id, TODAY).json()["id"]
    sid = _start(client, profile_id, None).json()["id"]
    _event(client, sid, profile_id, "session_completed")
    assert _dash(client, profile_id)[0]["status"] == "todo"
    assert _home(client, profile_id)["assignment"]["id"] == aid


def test_carry_over_and_queue(client: TestClient, engine: Engine, profile_id: str) -> None:
    _publish(engine, 2)
    yesterday = _assign(client, profile_id, TODAY).json()["id"]
    # Backdate: the API refuses past dates, so move it directly.
    from hoctap.learning.models import progress_assignments

    with engine.begin() as conn:
        conn.execute(progress_assignments.update().values(assigned_date=YESTERDAY))
    today = _assign(client, profile_id, TODAY).json()["id"]
    card = _home(client, profile_id)["assignment"]
    assert card["id"] == yesterday and card["carried_over"] is True
    sid = _start(client, profile_id, yesterday).json()["id"]
    _event(client, sid, profile_id, "session_completed")
    assert _home(client, profile_id)["assignment"]["id"] == today


def test_delete(client: TestClient, engine: Engine, profile_id: str) -> None:
    _publish(engine, 2)
    aid = _assign(client, profile_id, TODAY).json()["id"]
    assert client.delete(f"{API}/{aid}").status_code == 204
    assert _home(client, profile_id)["assignment"] is None
    assert _dash(client, profile_id) == []
    assert client.delete(f"{API}/{aid}").status_code == 404

    aid = _assign(client, profile_id, TODAY).json()["id"]
    sid = _start(client, profile_id, aid).json()["id"]
    _event(client, sid, profile_id, "session_completed")
    assert client.delete(f"{API}/{aid}").status_code == 409


def test_home_skips_assignment_whose_lesson_has_no_visible_problems(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Orchestrator's Independent Audit (spec-4-3 #1, 2026-10-01): a Problem can be hidden
    (parent "Ẩn", or an open parent Error Report) AFTER its Lesson was assigned. Without
    this, `home_assignment()` would keep returning this same dead Assignment forever --
    jamming the queue and surfacing a raw `EMPTY_PROBLEM_SET` error to the child the moment
    they tap "Bài hôm nay". It must instead be skipped on Home (and anything queued behind
    it must still show up), while the Dashboard keeps listing it, flagged `resolvable:
    false`, so Anh can see it needs attention."""
    pids = _publish(engine, 1)
    aid = _assign(client, profile_id, TODAY).json()["id"]

    with engine.begin() as conn:
        review_service.set_hidden(conn, pids[0], True)

    assert _home(client, profile_id)["assignment"] is None

    dash = _dash(client, profile_id)
    assert dash[0]["id"] == aid
    assert dash[0]["status"] == "todo"
    assert dash[0]["resolvable"] is False

    # Directly starting the dead Assignment still legitimately fails (the real state is
    # genuinely empty) -- the fix is that the child is never handed this card at all.
    resp = _start(client, profile_id, aid)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_PROBLEM_SET"

    # Unhiding the Problem makes the Assignment resolvable (and servable) again.
    with engine.begin() as conn:
        review_service.set_hidden(conn, pids[0], False)
    assert _home(client, profile_id)["assignment"]["id"] == aid
    assert _dash(client, profile_id)[0]["resolvable"] is True


def test_start_validation(client: TestClient, engine: Engine, profile_id: str) -> None:
    _publish(engine, 2)
    assert _start(client, profile_id, "nope").status_code == 404
    other = client.post(
        "/api/v1/profiles", json={"name": "Mai", "avatar": "dog", "grade": 1}
    ).json()["id"]
    aid = _assign(client, profile_id, TODAY).json()["id"]
    assert _start(client, other, aid).status_code == 404

    # Different Lesson, and non-lesson refs, cannot carry an Assignment.
    other_lesson = {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": "tiet-9"}
    for ref in (other_lesson, {"kind": "retry"}, {"kind": "replay", "source_session_id": "x"}):
        resp = client.post(
            "/api/v1/sessions",
            json={"profile_id": profile_id, "assignment_id": aid, "ref": ref},
        )
        assert resp.status_code == 422, ref
        assert resp.json()["error"]["code"] == "ASSIGNMENT_REF_MISMATCH", ref
