"""Story 4.1: Profile CRUD, PIN change, auto-play write, host-side PIN reset."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select

from hoctap import cli
from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.ids import to_iso
from hoctap.learning.models import (
    progress_assignments,
    progress_badges,
    progress_events,
    progress_retry_items,
    progress_sessions,
    progress_stars,
)
from hoctap.parent import service
from tests.test_parent import VALID_SETUP, FakeClock

API = "/api/v1"
NEW = {"name": "Na", "avatar": "dog", "grade": 2}


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(tmp_path: Path, clock: FakeClock):
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    app.state.clock = clock
    with TestClient(app) as c:
        assert c.post(f"{API}/setup", json=VALID_SETUP).status_code == 201
        yield c


def _ids(client: TestClient) -> list[str]:
    return [p["id"] for p in client.get(f"{API}/profiles").json()]


def test_add_profile(client: TestClient) -> None:
    resp = client.post(f"{API}/profiles", json=NEW)
    assert resp.status_code == 201
    body = resp.json()
    assert body["auto_play"] is True and body["name"] == "Na"
    assert _ids(client)[-1] == body["id"]


def test_fifth_profile_rejected(client: TestClient) -> None:
    for _ in range(3):
        assert client.post(f"{API}/profiles", json=NEW).status_code == 201
    resp = client.post(f"{API}/profiles", json=NEW)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "PROFILE_LIMIT"
    assert len(_ids(client)) == 4


def test_add_bad_body(client: TestClient) -> None:
    assert client.post(f"{API}/profiles", json={**NEW, "grade": 9}).status_code == 422


def test_patch_profile(client: TestClient) -> None:
    pid = _ids(client)[0]
    resp = client.patch(f"{API}/profiles/{pid}", json={"name": "  Bin B ", "auto_play": False})
    assert resp.status_code == 200
    assert resp.json() == {
        "id": pid, "name": "Bin B", "avatar": "cat", "grade": 1, "auto_play": False,
    }  # fmt: skip
    assert client.get(f"{API}/profiles").json()[0]["auto_play"] is False


def test_patch_errors(client: TestClient) -> None:
    pid = _ids(client)[0]
    assert client.patch(f"{API}/profiles/nope", json={"grade": 2}).status_code == 404
    assert client.patch(f"{API}/profiles/{pid}", json={"grade": 6}).status_code == 422
    assert client.patch(f"{API}/profiles/{pid}", json={"name": None}).status_code == 422


def _seed_progress(client: TestClient, pid: str) -> None:
    ts = to_iso(FakeClock().now)
    with client.app.state.engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            insert(progress_sessions).values(
                id=f"s-{pid}",
                profile_id=pid,
                ref_kind="lesson",
                ref_key="k",
                problem_ids_json="[]",
                started_at=ts,
            )  # fmt: skip
        )
        conn.execute(
            insert(progress_events).values(
                id=f"e-{pid}",
                session_id=f"s-{pid}",
                profile_id=pid,
                kind="attempt",
                problem_id="p",
                payload_json="{}",
                occurred_at=ts,
                received_at=ts,
            )  # fmt: skip
        )
        conn.execute(
            insert(progress_stars).values(
                id=f"st-{pid}",
                session_id=f"s-{pid}",
                profile_id=pid,
                problem_id="p",
                stars=1,
                awarded_at=ts,
            )  # fmt: skip
        )
        conn.execute(
            insert(progress_retry_items).values(
                id=f"r-{pid}", profile_id=pid, problem_id="p", added_at=ts
            )
        )
        conn.execute(
            insert(progress_badges).values(
                id=f"b-{pid}", profile_id=pid, badge_key="week1", earned_at=ts
            )
        )


def test_delete_purges_progress(client: TestClient) -> None:
    keep = _ids(client)[0]
    gone = client.post(f"{API}/profiles", json=NEW).json()["id"]
    _seed_progress(client, keep)
    _seed_progress(client, gone)
    with client.app.state.engine.begin() as conn:  # type: ignore[attr-defined]
        for pid in (keep, gone):
            conn.execute(
                insert(progress_assignments).values(
                    id=f"a-{pid}",
                    profile_id=pid,
                    ref_kind="lesson",
                    ref_key="k",
                    book_id="b",
                    unit_key="u",
                    lesson_key="l",
                    assigned_date="2026-09-30",
                    created_at=to_iso(FakeClock().now),
                )  # fmt: skip
            )
    assert client.delete(f"{API}/profiles/{gone}").status_code == 204
    assert _ids(client) == [keep]
    with client.app.state.engine.connect() as conn:  # type: ignore[attr-defined]
        for t in (progress_sessions, progress_events, progress_stars,
                  progress_retry_items, progress_badges, progress_assignments):  # fmt: skip
            assert (
                conn.execute(
                    select(func.count()).select_from(t).where(t.c.profile_id == gone)
                ).scalar_one()
                == 0
            )
            assert (
                conn.execute(
                    select(func.count()).select_from(t).where(t.c.profile_id == keep)
                ).scalar_one()
                == 1
            )
    assert client.get(f"{API}/profiles/{gone}/badges").status_code == 404


def test_delete_errors(client: TestClient) -> None:
    only = _ids(client)[0]
    resp = client.delete(f"{API}/profiles/{only}")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "LAST_PROFILE"
    assert client.delete(f"{API}/profiles/nope").status_code == 404
    assert _ids(client) == [only]


def test_writes_need_cookie(client: TestClient) -> None:
    pid = _ids(client)[0]
    client.cookies.clear()
    assert client.post(f"{API}/profiles", json=NEW).status_code == 401
    assert client.patch(f"{API}/profiles/{pid}", json={"grade": 2}).status_code == 401
    assert client.delete(f"{API}/profiles/{pid}").status_code == 401
    body = {"current_pin": "1234", "new_pin": "4321", "new_pin_confirm": "4321"}
    assert client.post(f"{API}/parent/pin", json=body).status_code == 401
    assert client.get(f"{API}/profiles").status_code == 200


def test_change_pin(client: TestClient, tmp_path: Path) -> None:
    other = TestClient(client.app)
    assert other.post(f"{API}/parent/login", json={"pin": "1234"}).status_code == 204
    body = {"current_pin": "1234", "new_pin": "4321", "new_pin_confirm": "4321"}
    assert client.post(f"{API}/parent/pin", json=body).status_code == 204
    assert client.get(f"{API}/parent/session").status_code == 200  # own cookie re-issued
    assert other.get(f"{API}/parent/session").status_code == 401
    fresh = TestClient(client.app)
    assert fresh.post(f"{API}/parent/login", json={"pin": "1234"}).status_code == 401
    assert fresh.post(f"{API}/parent/login", json={"pin": "4321"}).status_code == 204


def test_change_pin_wrong_current_locks(client: TestClient) -> None:
    body = {"current_pin": "0000", "new_pin": "4321", "new_pin_confirm": "4321"}
    # The 5th wrong attempt sets the lock but is itself still answered 401; 429 starts after.
    for _ in range(service.MAX_FAILED_ATTEMPTS):
        assert client.post(f"{API}/parent/pin", json=body).status_code == 401
    assert client.post(f"{API}/parent/pin", json=body).status_code == 429
    good = {**body, "current_pin": "1234"}
    assert client.post(f"{API}/parent/pin", json=good).status_code == 429


def test_change_pin_mismatch(client: TestClient) -> None:
    body = {"current_pin": "1234", "new_pin": "4321", "new_pin_confirm": "4322"}
    assert client.post(f"{API}/parent/pin", json=body).status_code == 422


def test_cli_reset_pin(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for _ in range(5):
        client.post(f"{API}/parent/login", json={"pin": "0000"})  # lock it
    assert client.get(f"{API}/parent/session").status_code == 200  # cookie still valid
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    answers = iter(["9876", "9876"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(answers))
    assert cli.main(["reset-pin"]) == 0
    assert client.get(f"{API}/parent/session").status_code == 401
    fresh = TestClient(client.app)
    assert fresh.post(f"{API}/parent/login", json={"pin": "1234"}).status_code == 401
    assert fresh.post(f"{API}/parent/login", json={"pin": "9876"}).status_code == 204


def test_cli_reset_pin_invalid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": "12ab")
    assert cli.main(["reset-pin"]) == 2
    fresh = TestClient(client.app)
    assert fresh.post(f"{API}/parent/login", json={"pin": "1234"}).status_code == 204
