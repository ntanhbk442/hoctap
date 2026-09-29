"""Story 1.2: first-run setup, PIN login with lockout, parent cookie guard, profiles.

One test (or parametrized group) per row of the I/O matrix, plus time-based expiry of
the cookie and of the lockout using an injectable clock.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.parent import service
from hoctap.parent.auth import COOKIE_NAME, load_or_create_secret

VALID_SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}
# Parent/build routes that answer 403 SETUP_REQUIRED before setup. Only session and
# build are behind the cookie guard; login and logout are setup-gated only.
SETUP_GATED = [
    ("GET", "/api/v1/parent/session"),
    ("POST", "/api/v1/parent/login"),
    ("POST", "/api/v1/parent/logout"),
    ("GET", "/api/v1/build/status"),
]


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(data_dir: Path, tmp_path: Path, clock: FakeClock):
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    app.state.clock = clock
    with TestClient(app) as c:
        yield c


@pytest.fixture
def setup_client(client: TestClient) -> TestClient:
    """A client after a successful setup, holding the parent cookie."""
    assert client.post("/api/v1/setup", json=VALID_SETUP).status_code == 201
    return client


def _envelope(resp, status: int, code: str) -> str:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]["message"]


def _db_rows(data_dir: Path, table: str) -> list[tuple]:
    con = sqlite3.connect(data_dir / "hoctap.db")
    try:
        return con.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
    finally:
        con.close()


def _set_cookie_header(resp) -> str:
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    assert len(headers) == 1, headers
    return headers[0]


# --- Status, fresh ---


def test_status_fresh(client: TestClient) -> None:
    resp = client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    assert resp.json() == {"setup_required": True}


# --- Setup ok ---


def test_setup_ok(client: TestClient, data_dir: Path) -> None:
    resp = client.post("/api/v1/setup", json=VALID_SETUP)
    assert resp.status_code == 201
    body = resp.json()
    assert {k: body[k] for k in ("name", "avatar", "grade")} == {
        "name": "Bin",
        "avatar": "cat",
        "grade": 1,
    }
    assert body["id"][14] == "7"  # UUIDv7

    cookie = _set_cookie_header(resp)
    assert cookie.startswith(f"{COOKIE_NAME}=")
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=strict" in lowered and "max-age=1800" in lowered
    assert "secure" not in lowered  # plain HTTP

    settings = _db_rows(data_dir, "parent_settings")
    assert len(settings) == 1
    pin_hash = settings[0][1]
    assert pin_hash.startswith("$2") and "1234" not in pin_hash
    assert [r[1:4] for r in _db_rows(data_dir, "parent_profiles")] == [("Bin", "cat", 1)]

    assert client.get("/api/v1/setup/status").json() == {"setup_required": False}
    # The setup cookie authenticates immediately.
    assert client.get("/api/v1/parent/session").json() == {"authenticated": True}


def test_cookie_secure_over_https(data_dir: Path, tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app, base_url="https://testserver") as c:
        resp = c.post("/api/v1/setup", json=VALID_SETUP)
        assert resp.status_code == 201
        assert "secure" in _set_cookie_header(resp).lower()


# --- Setup mismatch ---


def test_setup_mismatch(client: TestClient, data_dir: Path) -> None:
    resp = client.post("/api/v1/setup", json={**VALID_SETUP, "pin_confirm": "4321"})
    assert _envelope(resp, 422, "PIN_MISMATCH") == "Hai mã PIN không khớp"
    assert _db_rows(data_dir, "parent_settings") == []
    assert _db_rows(data_dir, "parent_profiles") == []
    assert "set-cookie" not in resp.headers


# --- Setup bad input ---


def _with_profile(**kw: object) -> dict:
    return {**VALID_SETUP, "profile": {**VALID_SETUP["profile"], **kw}}


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_SETUP, "pin": "12a4", "pin_confirm": "12a4"},
        {**VALID_SETUP, "pin": "123", "pin_confirm": "123"},
        {**VALID_SETUP, "pin": "12345", "pin_confirm": "12345"},
        {**VALID_SETUP, "pin": "١٢٣٤", "pin_confirm": "١٢٣٤"},  # non-ASCII digits
        _with_profile(grade=0),
        _with_profile(grade=6),
        _with_profile(name=""),
        _with_profile(name="   "),
        _with_profile(avatar="dragon"),
        {"pin": "1234", "pin_confirm": "1234"},
    ],
)
def test_setup_bad_input(client: TestClient, data_dir: Path, payload: dict) -> None:
    _envelope(client.post("/api/v1/setup", json=payload), 422, "VALIDATION_ERROR")
    assert _db_rows(data_dir, "parent_settings") == []
    assert _db_rows(data_dir, "parent_profiles") == []


def test_setup_name_too_long(client: TestClient) -> None:
    assert client.post("/api/v1/setup", json=_with_profile(name="a" * 41)).status_code == 422
    assert client.post("/api/v1/setup", json=_with_profile(name="a" * 40)).status_code == 201


@pytest.mark.parametrize(
    "name", ["\u200b", "\ufeff", "\u200b \ufeff", "Bin\u200b", "Bi\nn", "Bin\x07", "\n"]
)
def test_setup_name_invisible_or_control_rejected(
    client: TestClient, data_dir: Path, name: str
) -> None:
    resp = client.post("/api/v1/setup", json=_with_profile(name=name))
    _envelope(resp, 422, "VALIDATION_ERROR")
    assert _db_rows(data_dir, "parent_profiles") == []


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_SETUP, "extra": 1},
        _with_profile(nickname="B"),
    ],
)
def test_setup_unknown_field_rejected(client: TestClient, data_dir: Path, payload: dict) -> None:
    _envelope(client.post("/api/v1/setup", json=payload), 422, "VALIDATION_ERROR")
    assert _db_rows(data_dir, "parent_settings") == []


def test_setup_name_is_trimmed_and_nfc(client: TestClient) -> None:
    decomposed = "Bìn"  # "Bìn" with a combining grave accent
    resp = client.post("/api/v1/setup", json=_with_profile(name=f"  {decomposed} "))
    assert resp.status_code == 201
    assert resp.json()["name"] == "Bìn"


# --- Setup twice ---


def test_setup_twice(setup_client: TestClient, data_dir: Path) -> None:
    before = (_db_rows(data_dir, "parent_settings"), _db_rows(data_dir, "parent_profiles"))
    again = {
        "pin": "9999",
        "pin_confirm": "9999",
        "profile": {"name": "Na", "avatar": "dog", "grade": 3},
    }
    _envelope(setup_client.post("/api/v1/setup", json=again), 409, "SETUP_DONE")
    after = (_db_rows(data_dir, "parent_settings"), _db_rows(data_dir, "parent_profiles"))
    assert after == before


def test_setup_done_and_mismatch_is_409(setup_client: TestClient) -> None:
    body = {**VALID_SETUP, "pin_confirm": "4321"}
    _envelope(setup_client.post("/api/v1/setup", json=body), 409, "SETUP_DONE")


# --- Guard before setup ---


@pytest.mark.parametrize(("method", "path"), SETUP_GATED)
def test_guard_before_setup(client: TestClient, method: str, path: str) -> None:
    kwargs = {"json": {"pin": "1234"}} if path.endswith("/login") else {}
    _envelope(client.request(method, path, **kwargs), 403, "SETUP_REQUIRED")


def test_setup_routes_open_before_setup(client: TestClient) -> None:
    assert client.get("/api/v1/setup/status").status_code == 200
    assert client.get("/api/v1/profiles").status_code == 200


# --- Login ok / wrong ---


def test_login_ok(setup_client: TestClient, data_dir: Path) -> None:
    setup_client.cookies.clear()
    _envelope(setup_client.post("/api/v1/parent/login", json={"pin": "0000"}), 401, "PIN_INCORRECT")
    assert _db_rows(data_dir, "parent_settings")[0][2] == 1

    resp = setup_client.post("/api/v1/parent/login", json={"pin": "1234"})
    assert resp.status_code == 204
    assert _set_cookie_header(resp).startswith(f"{COOKIE_NAME}=")
    assert _db_rows(data_dir, "parent_settings")[0][2:4] == (0, None)  # counter reset
    assert setup_client.get("/api/v1/parent/session").status_code == 200


def test_login_wrong(setup_client: TestClient, data_dir: Path) -> None:
    setup_client.cookies.clear()
    resp = setup_client.post("/api/v1/parent/login", json={"pin": "9999"})
    assert _envelope(resp, 401, "PIN_INCORRECT") == "Mã PIN chưa đúng"
    assert "set-cookie" not in resp.headers
    assert _db_rows(data_dir, "parent_settings")[0][2] == 1
    setup_client.post("/api/v1/parent/login", json={"pin": "9998"})
    assert _db_rows(data_dir, "parent_settings")[0][2] == 2


def test_login_bad_format(setup_client: TestClient) -> None:
    _envelope(
        setup_client.post("/api/v1/parent/login", json={"pin": "12"}), 422, "VALIDATION_ERROR"
    )


# --- Lockout ---


def _fail(client: TestClient, times: int) -> None:
    for _ in range(times):
        _envelope(client.post("/api/v1/parent/login", json={"pin": "0000"}), 401, "PIN_INCORRECT")


def test_lockout(setup_client: TestClient, clock: FakeClock) -> None:
    setup_client.cookies.clear()
    _fail(setup_client, 5)
    # 6th attempt within 5 minutes: locked, even with the correct PIN.
    _envelope(setup_client.post("/api/v1/parent/login", json={"pin": "1234"}), 429, "PIN_LOCKED")
    clock.advance(minutes=4, seconds=59)
    _envelope(setup_client.post("/api/v1/parent/login", json={"pin": "1234"}), 429, "PIN_LOCKED")

    # The lock clears after 5 minutes.
    clock.advance(seconds=1)
    assert setup_client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204


def test_attempts_during_lock_change_nothing(
    setup_client: TestClient, data_dir: Path, clock: FakeClock
) -> None:
    setup_client.cookies.clear()
    _fail(setup_client, 5)
    locked = _db_rows(data_dir, "parent_settings")[0][2:4]
    assert locked[0] == 5 and locked[1] is not None
    clock.advance(minutes=2)
    for pin in ("0000", "1234", "0000"):
        resp = setup_client.post("/api/v1/parent/login", json={"pin": pin})
        _envelope(resp, 429, "PIN_LOCKED")
    assert _db_rows(data_dir, "parent_settings")[0][2:4] == locked


def test_lockout_expiry_restarts_count(setup_client: TestClient, clock: FakeClock) -> None:
    setup_client.cookies.clear()
    _fail(setup_client, 5)
    clock.advance(minutes=5)
    _fail(setup_client, 4)  # a fresh count: 4 wrong ones do not lock
    assert setup_client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204


def test_success_resets_consecutive_count(setup_client: TestClient) -> None:
    setup_client.cookies.clear()
    _fail(setup_client, 4)
    assert setup_client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204
    _fail(setup_client, 4)
    assert setup_client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204


# --- Guarded: no / expired / tampered cookie ---


def test_guarded_no_cookie(setup_client: TestClient) -> None:
    setup_client.cookies.clear()
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")
    _envelope(setup_client.get("/api/v1/build/status"), 401, "UNAUTHORIZED")


def test_guarded_expired_cookie(setup_client: TestClient, clock: FakeClock) -> None:
    clock.advance(minutes=30, seconds=1)
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")


def test_guarded_tampered_cookie(setup_client: TestClient) -> None:
    token = setup_client.cookies[COOKIE_NAME]
    setup_client.cookies.clear()
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    setup_client.cookies.set(COOKIE_NAME, tampered)
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")
    setup_client.cookies.set(COOKIE_NAME, "parent")
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")


def test_cookie_from_other_secret_rejected(
    setup_client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    other = create_app(Settings(data_dir=tmp_path / "other", frontend_dist=tmp_path / "no-dist"))
    with TestClient(other) as c:
        c.post("/api/v1/setup", json=VALID_SETUP)
        foreign = c.cookies[COOKIE_NAME]
    setup_client.cookies.clear()
    setup_client.cookies.set(COOKIE_NAME, foreign)
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")


# --- Guarded: valid cookie, sliding expiry ---


def test_guarded_valid_cookie_refreshes(setup_client: TestClient, clock: FakeClock) -> None:
    clock.advance(minutes=20)
    resp = setup_client.get("/api/v1/parent/session")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}
    assert _set_cookie_header(resp).startswith(f"{COOKIE_NAME}=")

    # 20 + 20 = 40 minutes after setup, but only 20 idle: still valid (sliding).
    clock.advance(minutes=20)
    assert setup_client.get("/api/v1/build/status").json() == {"state": "idle"}
    clock.advance(minutes=29)
    assert setup_client.get("/api/v1/parent/session").status_code == 200
    clock.advance(minutes=31)
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")


# --- Logout ---


def test_logout(setup_client: TestClient) -> None:
    old_token = setup_client.cookies[COOKIE_NAME]
    resp = setup_client.post("/api/v1/parent/logout")
    assert resp.status_code == 204
    cookie = _set_cookie_header(resp)
    assert cookie.startswith(f'{COOKIE_NAME}=""') or "max-age=0" in cookie.lower()
    assert COOKIE_NAME not in setup_client.cookies
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")

    # A copy of the old cookie no longer works after logout.
    setup_client.cookies.set(COOKIE_NAME, old_token)
    _envelope(setup_client.get("/api/v1/parent/session"), 401, "UNAUTHORIZED")

    # A new login works again.
    setup_client.cookies.clear()
    assert setup_client.post("/api/v1/parent/login", json={"pin": "1234"}).status_code == 204
    assert setup_client.get("/api/v1/parent/session").status_code == 200


def test_logout_without_cookie(setup_client: TestClient, data_dir: Path) -> None:
    token = setup_client.cookies[COOKIE_NAME]
    setup_client.cookies.clear()
    resp = setup_client.post("/api/v1/parent/logout")
    assert resp.status_code == 204
    assert _db_rows(data_dir, "parent_settings")[0][4] == 0  # session_version unchanged
    # Without a valid cookie, logout does not end other sessions.
    setup_client.cookies.set(COOKIE_NAME, token)
    assert setup_client.get("/api/v1/parent/session").status_code == 200


# --- Profiles ---


def test_profiles(client: TestClient) -> None:
    assert client.get("/api/v1/profiles").json() == []
    created = client.post("/api/v1/setup", json=VALID_SETUP).json()
    client.cookies.clear()
    resp = client.get("/api/v1/profiles")  # no auth needed
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": created["id"], "name": "Bin", "avatar": "cat", "grade": 1, "auto_play": True}
    ]


def test_list_profiles_order(client: TestClient) -> None:
    from sqlalchemy import insert

    from hoctap.parent.models import parent_profiles

    client.post("/api/v1/setup", json=VALID_SETUP)
    engine = client.app.state.engine  # type: ignore[attr-defined]
    with engine.begin() as conn:
        conn.execute(
            insert(parent_profiles),
            [
                {"id": "z", "name": "Cu", "avatar": "fox", "grade": 5,
                 "created_at": "2026-09-27T00:00:00.000000+00:00"},
                {"id": "a", "name": "Na", "avatar": "dog", "grade": 2,
                 "created_at": "2026-09-01T00:00:00.000000+00:00"},
                {"id": "b", "name": "Ti", "avatar": "bear", "grade": 3,
                 "created_at": "2026-09-01T00:00:00.000000+00:00"},
            ],
        )  # fmt: skip
    names = [p["name"] for p in client.get("/api/v1/profiles").json()]
    assert names == ["Na", "Ti", "Bin", "Cu"]  # by created_at, then id


# --- Secret key ---


def test_secret_key_created_once(data_dir: Path) -> None:
    key = load_or_create_secret(data_dir)
    path = data_dir / "secret.key"
    assert path.is_file() and len(key) == 64
    assert load_or_create_secret(data_dir) == key


def test_secret_key_empty_file_regenerated(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    (data_dir / "secret.key").write_bytes(b"")
    key = load_or_create_secret(data_dir)
    assert len(key) == 64
    assert (data_dir / "secret.key").read_bytes() == key
    assert not list(data_dir.glob("*.tmp"))


@pytest.mark.parametrize("content", [b"short", b"\xff" * 64])
def test_secret_key_bad_content_clear_error(data_dir: Path, content: bytes) -> None:
    data_dir.mkdir(parents=True)
    (data_dir / "secret.key").write_bytes(content)
    with pytest.raises(RuntimeError, match="secret key"):
        load_or_create_secret(data_dir)


def test_secret_key_survives_restart(
    setup_client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    token = setup_client.cookies[COOKIE_NAME]
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    app.state.clock = setup_client.app.state.clock  # type: ignore[attr-defined]
    with TestClient(app) as c:
        c.cookies.set(COOKIE_NAME, token)
        assert c.get("/api/v1/parent/session").status_code == 200
