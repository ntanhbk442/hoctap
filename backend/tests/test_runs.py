"""Story 1.10: extraction control from the Parent Area (`builder.jobs.RunManager` and the
`/build/runs*` API). One test per row of the I/O matrix, using `FakeClaudeClient` and a
short page range so the pipeline runs fast; a small polling loop with a timeout awaits the
background thread's progress instead of fixed sleeps.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_extraction import BOOK, BOOK_ID, PAGES, page_of, write_pdf
from test_verify import Model

from hoctap.app import create_app
from hoctap.builder.catalogue import build_catalogue
from hoctap.builder.claude_client import CallResult, FakeClaudeClient
from hoctap.config import Settings
from hoctap.db.engine import alembic_config, create_db_engine
from hoctap.parent import service as parent_service

RUNS = "/api/v1/build/runs"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def factory(tmp_path: Path):
    """`make(responder=None, delay=0.0)` builds a real (small, fast) book environment and
    a TestClient whose `RunManager` calls a `FakeClaudeClient`; returns `(client, fake,
    model)`. Every produced client is torn down at the end of the test."""
    clients: list[TestClient] = []

    def make(
        *, responder: Any = None, delay: float = 0.0, book: Any = BOOK, pages: int = PAGES
    ) -> tuple[TestClient, FakeClaudeClient, Model]:
        source = tmp_path / f"src{len(clients)}" / "Sach_Arch"
        write_pdf(source / book.source_path, pages)
        settings = Settings(
            data_dir=tmp_path / f"data{len(clients)}",
            frontend_dist=tmp_path / "no-dist",
            source_dir=source,
            render_long_edge=300,
        )
        model = Model(settings.data_dir)

        def default_responder(request: Any) -> CallResult:
            if delay:
                time.sleep(delay)
            return model(request)

        fake = FakeClaudeClient(responder or default_responder)
        app = create_app(settings, run_client_factory=lambda _s: fake)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        assert client.post("/api/v1/setup", json=SETUP).status_code == 201
        build_catalogue(client.app.state.engine, source, books=(book,))
        return client, fake, model

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def start(client: TestClient, pages: str = "6-6", yes_spend: bool = True, book_id: str = BOOK_ID):
    return client.post(RUNS, json={"book_id": book_id, "pages": pages, "yes_spend": yes_spend})


def get(client: TestClient, run_id: str):
    return client.get(f"{RUNS}/{run_id}")


def wait_for(client: TestClient, run_id: str, statuses: tuple[str, ...], timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        resp = get(client, run_id)
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["status"] in statuses:
            return last
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {statuses}; last seen: {last}")


def code(resp: Any) -> str:
    return resp.json()["error"]["code"]


def calls_for(fake: FakeClaudeClient, stage: str, page: int) -> int:
    return sum(1 for r in fake.calls if r.stage == stage and page_of(r) == page)


# --------------------------------------------------------------------------- matrix


def test_start_ok(factory) -> None:  # noqa: ANN001
    client, fake, _model = factory()
    resp = start(client, pages="6-6")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert (body["book_id"], body["first_page"], body["last_page"]) == (BOOK_ID, 6, 6)
    final = wait_for(client, body["id"], ("done", "failed"))
    assert final["status"] == "done", final
    assert final["pages_done"] == 1 and final["pages_total"] == 1
    assert final["failed_pages"] == []
    assert final["activity"] == "Đã xong"
    assert calls_for(fake, "extract", 6) == 1


def test_start_needs_confirm(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    resp = start(client, pages="6-6", yes_spend=False)
    assert resp.status_code == 422 and code(resp) == "SPEND_NOT_CONFIRMED"
    message = resp.json()["error"]["message"]
    assert "Ước tính" in message or "Estimate" in message
    assert client.get(f"{RUNS}/current").json() is None


def test_start_invalid_range(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    resp = start(client, pages="6-6", book_id="unknown-book")
    assert resp.status_code == 422 and code(resp) == "VALIDATION_ERROR"
    resp = start(client, pages="99-100")
    assert resp.status_code == 422 and code(resp) == "VALIDATION_ERROR"


def test_start_while_running(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory(delay=0.05)
    first = start(client, pages="6-7")
    assert first.status_code == 202, first.text
    resp = start(client, pages="6-6")
    assert resp.status_code == 409 and code(resp) == "RUN_IN_PROGRESS"
    wait_for(client, first.json()["id"], ("done", "failed"))


def test_poll_during_run(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory(delay=0.05)
    run_id = start(client, pages="6-7").json()["id"]
    first = get(client, run_id).json()["pages_done"]
    time.sleep(0.15)
    second = get(client, run_id).json()["pages_done"]
    assert second >= first
    final = wait_for(client, run_id, ("done", "failed"))
    assert final["pages_done"] == 2


def test_page_fails(factory) -> None:  # noqa: ANN001
    fail_page = 6

    def responder(model: Model):
        def _respond(request: Any) -> CallResult:
            if request.stage == "extract" and page_of(request) == fail_page:
                return CallResult(ok=False, error="refusal: cannot read the page")
            return model(request)

        return _respond

    # Build with a placeholder responder first so we can close over `model` after creation.
    client, fake, model = factory()
    fake.responder = responder(model)
    resp = start(client, pages="6-7")
    assert resp.status_code == 202, resp.text
    final = wait_for(client, resp.json()["id"], ("done", "failed"))
    assert final["status"] == "done"
    assert final["pages_done"] == 2  # the run proceeds past the failed page
    assert [f["page"] for f in final["failed_pages"]] == [6]
    assert final["failed_pages"][0]["stage"] == "extract"
    assert "refusal" in final["failed_pages"][0]["reason"]


def test_pause(factory) -> None:  # noqa: ANN001
    client, fake, _model = factory(delay=0.1)
    run_id = start(client, pages="6-7").json()["id"]
    time.sleep(0.05)  # let the first page start
    pause_resp = client.post(f"{RUNS}/{run_id}/pause")
    assert pause_resp.status_code == 200, pause_resp.text
    assert pause_resp.json()["status"] in ("pausing", "paused")
    final = wait_for(client, run_id, ("paused",))
    assert final["pages_done"] < final["pages_total"]
    assert final["activity"] == "Đã tạm dừng"
    calls_at_pause = len(fake.calls)
    time.sleep(0.2)  # no further Claude calls once paused
    assert len(fake.calls) == calls_at_pause


def test_resume(factory) -> None:  # noqa: ANN001
    client, fake, _model = factory(delay=0.1)
    run_id = start(client, pages="6-7").json()["id"]
    time.sleep(0.05)
    client.post(f"{RUNS}/{run_id}/pause")
    paused = wait_for(client, run_id, ("paused",))
    assert paused["pages_done"] == 1  # page 6 finished before the pause took effect
    calls_for_page6_before = calls_for(fake, "extract", 6)

    resume_resp = client.post(f"{RUNS}/{run_id}/resume")
    assert resume_resp.status_code == 200, resume_resp.text
    new_run = resume_resp.json()
    assert new_run["id"] != run_id and new_run["resumed_from"] == run_id
    final = wait_for(client, new_run["id"], ("done", "failed"))
    assert final["status"] == "done" and final["pages_done"] == 2
    assert final["activity"] == "Đã xong"
    assert calls_for(fake, "extract", 6) == calls_for_page6_before  # page 6 was not repeated
    assert calls_for(fake, "extract", 7) == 1


def test_cancel(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory(delay=0.1)
    run_id = start(client, pages="6-7").json()["id"]
    time.sleep(0.05)
    resp = client.post(f"{RUNS}/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    final = wait_for(client, run_id, ("cancelled",))
    assert final["status"] == "cancelled"
    # Resuming a cancelled run is allowed, the same way as a paused one.
    resume_resp = client.post(f"{RUNS}/{run_id}/resume")
    assert resume_resp.status_code == 200, resume_resp.text


def test_poll_unknown_id(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    resp = get(client, "not-a-real-id")
    assert resp.status_code == 404 and code(resp) == "RUN_NOT_FOUND"


def test_auth(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    client.cookies.clear()
    for method, path in (
        ("POST", RUNS),
        ("GET", f"{RUNS}/current"),
        ("GET", f"{RUNS}/x"),
        ("GET", RUNS),
        ("POST", f"{RUNS}/x/pause"),
        ("POST", f"{RUNS}/x/resume"),
        ("POST", f"{RUNS}/x/cancel"),
    ):
        resp = client.request(method, path, json={})
        assert resp.status_code == 401, (method, path)


def test_stale_running_row(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    old = "2020-01-01T00:00:00.000000+00:00"
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO build_runs (id, book_id, first_page, last_page, status, stage, "
                "pages_total, pages_done, cost_usd, cost_unknown_count, failed_pages_json, "
                "error, resumed_from, started_at, updated_at, finished_at) VALUES "
                "('r1', :book, 6, 7, 'running', 'extract', 2, 0, 0, 0, '[]', NULL, NULL, "
                ":ts, :ts, NULL)"
            ),
            {"book": BOOK_ID, "ts": old},
        )
    resp = get(client, "r1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running" and body["stale"] is True
    assert client.get(f"{RUNS}/current").json()["stale"] is True


def test_resume_on_a_stale_running_row(factory) -> None:  # noqa: ANN001
    """Tiếp tục on a stale `running` row (a crashed server's leftover) works in one step:
    the dead row is closed out as `cancelled` and a fresh run starts over the same range."""
    client, _fake, _model = factory()
    old = "2020-01-01T00:00:00.000000+00:00"
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO build_runs (id, book_id, first_page, last_page, status, stage, "
                "pages_total, pages_done, cost_usd, cost_unknown_count, failed_pages_json, "
                "error, resumed_from, started_at, updated_at, finished_at) VALUES "
                "('r1', :book, 6, 6, 'running', 'extract', 1, 0, 0, 0, '[]', NULL, NULL, "
                ":ts, :ts, NULL)"
            ),
            {"book": BOOK_ID, "ts": old},
        )
    resp = client.post(f"{RUNS}/r1/resume")
    assert resp.status_code == 200, resp.text
    new_run = resp.json()
    assert new_run["id"] != "r1" and new_run["resumed_from"] == "r1"
    final = wait_for(client, new_run["id"], ("done", "failed"))
    assert final["status"] == "done"
    assert get(client, "r1").json()["status"] == "cancelled"


def test_current_reflects_the_active_run_after_reload(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory(delay=0.05)
    run_id = start(client, pages="6-7").json()["id"]
    current = client.get(f"{RUNS}/current").json()
    assert current is not None and current["id"] == run_id
    wait_for(client, run_id, ("done", "failed"))


def test_current_ignores_an_old_settled_run(factory) -> None:  # noqa: ANN001
    """A `done` run older than a day no longer hides the picker on page load."""
    client, _fake, _model = factory()
    old = "2020-01-01T00:00:00.000000+00:00"
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO build_runs (id, book_id, first_page, last_page, status, stage, "
                "pages_total, pages_done, cost_usd, cost_unknown_count, failed_pages_json, "
                "error, resumed_from, started_at, updated_at, finished_at) VALUES "
                "('r1', :book, 6, 6, 'done', NULL, 1, 1, 0, 0, '[]', NULL, NULL, "
                ":ts, :ts, :ts)"
            ),
            {"book": BOOK_ID, "ts": old},
        )
    assert client.get(f"{RUNS}/current").json() is None
    assert get(client, "r1").json()["status"] == "done"  # still reachable by id


def test_stage_transitions_through_more_than_extract(factory) -> None:  # noqa: ANN001
    """Over one page, `stage` visits more than just `extract` (render/validate/verify/crop
    are also reported, though a fast in-memory step may be missed by polling)."""
    client, _fake, _model = factory(delay=0.15)
    run_id = start(client, pages="6-6").json()["id"]
    seen: list[str | None] = []
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        body = get(client, run_id).json()
        if not seen or seen[-1] != body["stage"]:
            seen.append(body["stage"])
        if body["status"] not in ("running", "pausing"):
            break
        time.sleep(0.01)
    distinct = {s for s in seen if s is not None}
    assert len(distinct) > 1, seen


def test_list_catalogue_books(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    resp = client.get("/api/v1/build/books")
    assert resp.status_code == 200, resp.text
    match = next(b for b in resp.json() if b["book_id"] == BOOK_ID)
    assert match["title_vi"] == BOOK.title_vi
    assert match["page_count"] == PAGES


def test_list_runs(factory) -> None:  # noqa: ANN001
    client, _fake, _model = factory()
    run_id = start(client, pages="6-6").json()["id"]
    wait_for(client, run_id, ("done", "failed"))
    resp = client.get(RUNS)
    assert resp.status_code == 200, resp.text
    assert any(r["id"] == run_id for r in resp.json()["runs"])


def test_migration_0010_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "m.db")
    cfg = alembic_config(engine)
    try:
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn

            def names(kind: str) -> set[str]:
                sql = f"SELECT name FROM sqlite_master WHERE type = '{kind}'"
                return {r[0] for r in conn.execute(text(sql))}

            command.upgrade(cfg, "head")
            assert "build_runs" in names("table")
            command.downgrade(cfg, "0009_build_jobs_run_kind")
            assert "build_runs" not in names("table")
            command.upgrade(cfg, "head")
            assert "build_runs" in names("table")
    finally:
        engine.dispose()
