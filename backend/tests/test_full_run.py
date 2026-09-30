"""Story 6.2: the full-corpus run (`hoctap build full`, `builder/full.py`, `RunManager`).

One test per row of the I/O matrix on a small generated corpus. Every Claude call goes to
`FakeClaudeClient`; the real CLI is never spawned. The go/no-go approval is stubbed with a
switch (its own rules are tested in test_gate.py) except where the test is about the real
guard.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_extraction import page_of, write_pdf
from test_verify import Model

import hoctap.cli as cli
from hoctap.app import create_app
from hoctap.builder import full, gate
from hoctap.builder.catalogue import build_catalogue
from hoctap.builder.claude_client import CallResult, FakeClaudeClient, FakeCrash, PageRequest
from hoctap.config import Settings, load_settings
from hoctap.content.catalog.books import BOOKS, CatalogueBook
from hoctap.db.engine import create_db_engine, run_migrations
from hoctap.parent import service as parent_service

PAGES = 8


def book(book_id: str) -> CatalogueBook:
    return next(b for b in BOOKS if b.book_id == book_id)


G1Q1, G1Q2 = book("toan1-2020-q1"), book("toan1-2020-q2")
G2Q1 = book("toan2-2020-q1")
G3Q1, G3Q2 = book("toan3-2020-q1"), book("toan3-2020-q2")


class Approval:
    """A switch standing in for `gate.require_approval`."""

    def __init__(self) -> None:
        self.ok = True
        self.checks = 0
        self.after: int | None = None  # refuse from this check on (1-based)

    def __call__(self, engine: Any, settings: Any) -> None:
        self.checks += 1
        if not self.ok or (self.after is not None and self.checks >= self.after):
            raise gate.GateNotApproved("test")


@pytest.fixture
def approval(monkeypatch: pytest.MonkeyPatch) -> Approval:
    switch = Approval()
    monkeypatch.setattr(gate, "require_approval", switch)
    return switch


def make_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    books: tuple[CatalogueBook, ...],
    *,
    probe_pages: int = 30,
) -> Path:
    source = tmp_path / "Sach_Arch"
    for b in books:
        write_pdf(source / b.source_path, PAGES)
    data = tmp_path / "data"
    config = tmp_path / "hoctap.toml"
    config.write_text(
        f"[build]\nrender_long_edge = 300\nextraction_concurrency = 1\n"
        f"pilot_max_pages = {probe_pages}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOCTAP_CONFIG", str(config))
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(data))
    monkeypatch.setenv("HOCTAP_SOURCE_DIR", str(source))
    engine = create_db_engine(data / "hoctap.db")
    run_migrations(engine)
    build_catalogue(engine, source, books=books)
    engine.dispose()
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    return data


class Fake:
    """`FakeClaudeClient` around the extract/verify `Model`, with per-page failures and an
    optional crash after N extract calls."""

    def __init__(self, data: Path) -> None:
        self.model = Model(data)
        self.refuse: set[tuple[str, int]] = set()  # (book_id, page) whose extract is refused
        self.crash_after: int | None = None
        self.client = FakeClaudeClient(self.respond)

    def respond(self, request: PageRequest) -> CallResult:
        page = page_of(request)
        book_id = request.page_ref.rsplit("#p", 1)[0]
        if request.stage == "extract":
            if (book_id, page) in self.refuse:
                return CallResult(ok=False, error="refusal: test", transient=False, cost_usd=0.1)
            extracts = sum(1 for r in self.client.calls if r.stage == "extract")
            if self.crash_after is not None and extracts > self.crash_after:
                raise FakeCrash(request.page_ref)
        return self.model(request)

    def refs(self, stage: str = "extract") -> list[str]:
        return [r.page_ref for r in self.client.calls if r.stage == stage]


@pytest.fixture
def one_grade(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return make_env(monkeypatch, tmp_path, (G1Q1, G1Q2))


def fake_for(monkeypatch: pytest.MonkeyPatch, data: Path) -> Fake:
    fake = Fake(data)
    monkeypatch.setattr(cli, "_claude_client", lambda settings: fake.client)
    return fake


def rows(data: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(data / "hoctap.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def full_cmd(*extra: str) -> int:
    return cli.main(["build", "full", *extra])


SPEND = ("--yes-spend", "--max-total-usd", "50")


# --------------------------------------------------------------------------- matrix: guards


def test_no_approval_exits_3_and_sends_nothing(
    one_grade: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    assert full_cmd(*SPEND) == 3
    assert "GATE_NOT_APPROVED" in capsys.readouterr().err
    assert fake.client.calls == []
    assert rows(one_grade, "SELECT count(*) FROM build_runs") == [(0,)]


def test_no_spend_flag_prints_the_plan_and_exits_2(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    assert full_cmd() == 2
    captured = capsys.readouterr()
    assert "SPEND_NOT_CONFIRMED" in captured.err
    assert "toan1-2020-q1" in captured.out and "toan1-2020-q2" in captured.out
    assert f"{PAGES} trang gọi Claude" in captured.out
    assert "Ước tính" in captured.out
    assert fake.client.calls == []
    assert rows(one_grade, "SELECT count(*) FROM build_jobs") == [(0,)]


def test_no_cap_exits_2(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    assert full_cmd("--yes-spend") == 2
    assert "cần đặt --max-total-usd" in capsys.readouterr().err
    assert fake.client.calls == []


def test_dry_run_writes_requests_only(
    one_grade: Path, approval: Approval, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    assert full_cmd("--dry-run") == 0
    assert fake.client.calls == []
    settings = load_settings()
    requests = list((settings.build_dir / "requests").rglob("p*.json"))
    assert len(requests) == 2 * PAGES
    assert rows(one_grade, "SELECT count(*) FROM build_jobs WHERE stage='extract'") == [(0,)]


# --------------------------------------------------------------------------- happy path


def test_happy_path_two_books(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    assert full_cmd(*SPEND) == 0
    out = capsys.readouterr().out
    assert sorted(set(fake.refs())) == sorted(fake.refs())  # one call per page
    assert len(fake.refs()) == 2 * PAGES
    kinds = rows(
        one_grade, "SELECT DISTINCT run_kind FROM build_jobs WHERE stage IN ('extract', 'verify')"
    )
    assert kinds == [("full",)]
    runs = rows(
        one_grade,
        "SELECT book_id, run_kind, status, pages_done, pages_total, max_total_usd, "
        "cost_usd > 0 FROM build_runs ORDER BY id",
    )
    assert runs == [
        ("toan1-2020-q1", "full", "done", PAGES, PAGES, 50.0, 1),
        ("toan1-2020-q2", "full", "done", PAGES, PAGES, 50.0, 1),
    ]
    assert len({r[0] for r in rows(one_grade, "SELECT full_id FROM build_runs")}) == 1
    assert out.index("toan1-2020-q1: done") < out.index("toan1-2020-q2: done")
    assert "Interactive share" in out and "Kiểm tra ngẫu nhiên" in out
    assert "verify disagreement" in out
    assert rows(one_grade, "SELECT count(*) FROM content_catalog_problems")[0][0] > 0


def test_books_are_ordered_by_grade_edition_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = make_env(monkeypatch, tmp_path, (G2Q1, G1Q2, G1Q1))
    engine = create_db_engine(data / "hoctap.db")
    try:
        plan = full.plan_full(engine, load_settings())
        assert [p.book.book_id for p in plan.books] == [G1Q1.book_id, G1Q2.book_id, G2Q1.book_id]
        narrowed = full.plan_full(engine, load_settings(), grade=1)
        assert len(narrowed.books) == 2
        one = full.plan_full(engine, load_settings(), books=(G2Q1.book_id,))
        assert [p.book.book_id for p in one.books] == [G2Q1.book_id]
        with pytest.raises(full.PilotError):
            full.plan_full(engine, load_settings(), books=("nope",))
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- restart, cap, failures


def test_restart_does_not_call_completed_pages_again(
    one_grade: Path, approval: Approval, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    fake.crash_after = 3
    assert full_cmd(*SPEND) == 1  # the crash is an error, not a failed page
    done = {
        r[0]
        for r in rows(
            one_grade, "SELECT page_ref FROM build_jobs WHERE stage='extract' AND status='done'"
        )
    }
    assert len(done) == 3
    assert rows(one_grade, "SELECT status FROM build_runs") == [("failed",)]
    before = len(fake.client.calls)
    fake.crash_after = None
    assert full_cmd(*SPEND) == 0
    second = [r.page_ref for r in fake.client.calls[before:] if r.stage == "extract"]
    assert not done & set(second)
    assert len(done) + len(set(second)) == 2 * PAGES


def test_cap_hit_stops_resumable(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    # 0.25 per extract call: two pages reach the 0.3 cap.
    assert full_cmd("--yes-spend", "--max-total-usd", "0.3") == 4
    out = capsys.readouterr().out
    assert len(fake.refs()) == 2
    status = rows(one_grade, "SELECT status, stop_reason, unstarted_json FROM build_runs")
    assert status[0][:2] == ("stopped_budget", "budget")
    unstarted = json.loads(status[0][2])
    assert [u["book_id"] for u in unstarted] == ["toan1-2020-q1", "toan1-2020-q2"]
    assert unstarted[0]["pages"] == PAGES - 2
    assert "toan1-2020-q2" in out and "Not started" in out
    first = set(fake.refs())
    before = len(fake.client.calls)
    assert full_cmd(*SPEND) == 0
    again = {r.page_ref for r in fake.client.calls[before:] if r.stage == "extract"}
    assert not first & again
    assert len(first | again) == 2 * PAGES


def test_unknown_cost_counts_at_the_per_call_cap(
    one_grade: Path, approval: Approval, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    original = fake.respond

    def unknown(request: PageRequest) -> CallResult:
        result = original(request)
        if request.stage == "extract":
            return CallResult(ok=True, output=result.output, cost_usd=0.0, cost_unknown=True)
        return result

    fake.client.responder = unknown
    # The per-call cap (1.0) is charged for each unknown-cost call: a 1.5 cap allows two.
    assert full_cmd("--yes-spend", "--max-total-usd", "1.5") == 4
    assert len(fake.refs()) == 2


def test_failed_page_is_listed_and_retried(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    fake.refuse = {(G1Q1.book_id, 5)}
    assert full_cmd(*SPEND) == 1
    captured = capsys.readouterr()
    assert "toan1-2020-q1 p5 [extract]: refusal: test" in captured.err
    assert len(fake.refs()) == 2 * PAGES  # the refusal is not retried; the others continue
    assert rows(
        one_grade, "SELECT count(*) FROM build_jobs WHERE stage='extract' AND status='done'"
    ) == [(2 * PAGES - 1,)]
    stored = json.loads(
        rows(one_grade, "SELECT failed_pages_json FROM build_runs ORDER BY id")[0][0]
    )
    assert stored == [
        {"book_id": G1Q1.book_id, "page": 5, "stage": "extract", "reason": "refusal: test"}
    ]
    fake.refuse = set()
    before = len(fake.client.calls)
    assert full_cmd(*SPEND) == 0
    retried = [r.page_ref for r in fake.client.calls[before:] if r.stage == "extract"]
    assert retried == [f"{G1Q1.book_id}#p005"]


def test_approval_lost_between_books_stops_before_the_next_book(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    approval.after = 3  # the CLI's own check, then one per Book: refused before the 2nd Book
    assert full_cmd(*SPEND) == 3
    assert {r.rsplit("#p", 1)[0] for r in fake.refs()} == {G1Q1.book_id}
    assert rows(one_grade, "SELECT book_id, status FROM build_runs ORDER BY id") == [
        (G1Q1.book_id, "stopped_gate")
    ]
    assert "toan1-2020-q2" in capsys.readouterr().out
    approval.after = None
    assert full_cmd(*SPEND) == 0
    assert {r.rsplit("#p", 1)[0] for r in fake.refs()} == {G1Q1.book_id, G1Q2.book_id}


def test_source_changed_book_is_skipped_and_listed(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    settings = load_settings()
    write_pdf(settings.source_dir / G1Q2.source_path, PAGES + 2)
    assert full_cmd(*SPEND) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out and "hoctap build catalogue" in out
    assert {r.rsplit("#p", 1)[0] for r in fake.refs()} == {G1Q1.book_id}


def test_concurrent_run_is_refused(
    one_grade: Path,
    approval: Approval,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = fake_for(monkeypatch, one_grade)
    con = sqlite3.connect(one_grade / "hoctap.db")
    now = "2999-01-01T00:00:00.000Z"
    con.execute(
        "INSERT INTO build_runs (id, book_id, first_page, last_page, status, pages_total, "
        "started_at, updated_at) VALUES ('x', 'b', 1, 1, 'running', 1, ?, ?)",
        (now, now),
    )
    con.commit()
    con.close()
    assert full_cmd(*SPEND) == 2
    assert "RUN_IN_PROGRESS" in capsys.readouterr().err
    assert fake.client.calls == []


# --------------------------------------------------------------------------- checkpoints


def test_grade_1_and_2_pause_after_each_grade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    approval: Approval,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = make_env(monkeypatch, tmp_path, (G1Q1, G1Q2, G2Q1))
    fake = fake_for(monkeypatch, data)
    assert full_cmd(*SPEND) == 0
    assert {r.rsplit("#p", 1)[0] for r in fake.refs()} == {G1Q1.book_id, G1Q2.book_id}
    assert rows(data, "SELECT book_id, status FROM build_runs ORDER BY id") == [
        (G1Q1.book_id, "done"),
        (G1Q2.book_id, "stopped_checkpoint"),
    ]
    assert "Tiếp tục" in capsys.readouterr().out
    assert full_cmd(*SPEND) == 0  # Tiếp tục: grade 1 has nothing to do, grade 2 runs
    assert {r.rsplit("#p", 1)[0] for r in fake.refs()} == {G1Q1.book_id, G1Q2.book_id, G2Q1.book_id}


def test_grade_3_first_book_is_a_pilot_then_the_run_stops(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    approval: Approval,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = make_env(monkeypatch, tmp_path, (G3Q1, G3Q2), probe_pages=3)
    fake = fake_for(monkeypatch, data)
    assert full_cmd(*SPEND) == 0
    assert sorted(fake.refs()) == [f"{G3Q1.book_id}#p00{p}" for p in (1, 2, 3)]
    assert rows(
        data, "SELECT DISTINCT run_kind FROM build_jobs WHERE stage IN ('extract', 'verify')"
    ) == [("pilot",)]
    assert rows(data, "SELECT book_id, status, stop_reason FROM build_runs") == [
        (G3Q1.book_id, "stopped_checkpoint", "checkpoint")
    ]
    out = capsys.readouterr().out
    assert "Kiểm tra ngẫu nhiên" in out and "approve the gate again" in out
    # After the human re-approval (stubbed), the rest of the grade runs as `full` jobs.
    before = len(fake.client.calls)
    assert full_cmd(*SPEND) == 0
    later = [r.page_ref for r in fake.client.calls[before:] if r.stage == "extract"]
    assert len(later) == (PAGES - 3) + PAGES
    assert not {f"{G3Q1.book_id}#p00{p}" for p in (1, 2, 3)} & set(later)
    kinds = dict(
        rows(
            data,
            "SELECT substr(page_ref, 1, 13) || '#' || run_kind, count(*) FROM build_jobs "
            "WHERE stage='extract' GROUP BY 1",
        )
    )
    assert kinds == {
        f"{G3Q1.book_id}#pilot": 3,
        f"{G3Q1.book_id}#full": PAGES - 3,
        f"{G3Q2.book_id}#full": PAGES,
    }


def test_grade_3_probe_voids_the_approval_until_it_is_renewed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the real guard: pilot pages change the pilot scope, so the next invocation is
    refused (exit 3) until the gate is approved again."""
    data = make_env(monkeypatch, tmp_path, (G3Q1, G3Q2), probe_pages=3)
    fake = fake_for(monkeypatch, data)
    state = {"valid": True}

    def guard(engine: Any, settings: Any) -> None:
        with engine.connect() as conn:
            scope = len(gate.pilot_refs(conn))
        if not state["valid"] or scope != state.setdefault("scope", scope):
            raise gate.GateNotApproved("phạm vi thay đổi")

    monkeypatch.setattr(gate, "require_approval", guard)
    assert full_cmd(*SPEND) == 0
    assert len(fake.refs()) == 3
    capsys.readouterr()
    assert full_cmd(*SPEND) == 3
    assert "GATE_NOT_APPROVED" in capsys.readouterr().err
    assert len(fake.refs()) == 3


def test_grade_3_other_books_wait_for_the_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, approval: Approval
) -> None:
    data = make_env(monkeypatch, tmp_path, (G3Q1, G3Q2), probe_pages=3)
    engine = create_db_engine(data / "hoctap.db")
    try:
        plan = full.plan_full(engine, load_settings(), books=(G3Q2.book_id,))
        assert plan.books[0].skipped is not None and "chạy thử" in plan.books[0].skipped
        assert plan.calls_pages == 0
        both = full.plan_full(engine, load_settings())
        assert both.books[0].probe and both.books[0].kind == "pilot"
        assert len(both.books[0].scope) == 3 and both.books[1].skipped
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- the gate cost fix


def test_full_run_leaves_the_real_gate_estimate_alone(
    one_grade: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pilot page re-extracted by the full run (its hash changed) is a `full` job; the
    gate's cost and estimate do not move."""
    fake_for(monkeypatch, one_grade)
    settings = load_settings()
    engine = create_db_engine(settings.db_path)
    try:
        from hoctap.builder.pilot import plan_pilot, run_pilot

        plan = plan_pilot(engine, settings, G1Q1.book_id, 5, 7)
        run_pilot(
            engine,
            settings,
            plan,
            Fake(one_grade).client,
            dry_run=False,
            out=lambda _l: None,
            verify=False,
        )
        with engine.connect() as conn:
            before = gate.report(conn, settings).cost
        assert before.pilot_pages == 3 and before.pilot_cost > 0
        # The prompt changes: the same pages are extracted again by a full run.
        from hoctap.builder.stages import extract as extract_stage

        monkeypatch.setattr(extract_stage, "PROMPT_VERSION", "p-next")
        fresh = Fake(one_grade)
        run_pilot(
            engine,
            settings,
            plan,
            fresh.client,
            dry_run=False,
            out=lambda _l: None,
            verify=False,
            run_kind="full",
        )
        assert len(fresh.refs()) == 3
        with engine.connect() as conn:
            after = gate.report(conn, settings).cost
        assert after.pilot_cost == before.pilot_cost
        assert after.est_cost == before.est_cost and after.pilot_pages == 3
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- API


SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)
    clients: list[TestClient] = []

    def make(delay: float = 0.0) -> tuple[TestClient, Fake]:
        source = tmp_path / "src" / "Sach_Arch"
        for b in (G1Q1, G1Q2):
            write_pdf(source / b.source_path, PAGES)
        settings = Settings(
            data_dir=tmp_path / "data",
            frontend_dist=tmp_path / "no-dist",
            source_dir=source,
            render_long_edge=300,
            extraction_concurrency=1,
        )
        fake = Fake(settings.data_dir)
        if delay:
            inner = fake.respond

            def slow(request: PageRequest) -> CallResult:
                time.sleep(delay)
                return inner(request)

            fake.client.responder = slow
        app = create_app(settings, run_client_factory=lambda _s: fake.client)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        assert client.post("/api/v1/setup", json=SETUP).status_code == 201
        build_catalogue(client.app.state.engine, source, books=(G1Q1, G1Q2))
        return client, fake

    yield make
    for c in clients:
        c.__exit__(None, None, None)


BUILD = "/api/v1/build"


def wait_full(client: TestClient, statuses: tuple[str, ...], timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = client.get(f"{BUILD}/full/current").json()
        if last is not None and last["status"] in statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"timed out; last: {last}")


def code(resp: Any) -> str:
    return resp.json()["error"]["code"]


def start_full(client: TestClient, body: dict[str, Any]) -> Any:
    """POST /full, waiting out the instant between a run's last row and its thread ending."""
    for _ in range(200):
        resp = client.post(f"{BUILD}/full", json=body)
        if resp.status_code != 409 or code(resp) != "RUN_IN_PROGRESS":
            return resp
        time.sleep(0.05)
    return resp


def test_api_plan_and_start_guards(api: Callable[..., Any]) -> None:
    client, fake = api()
    plan = client.post(f"{BUILD}/full/plan", json={})
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert [b["book_id"] for b in body["books"]] == [G1Q1.book_id, G1Q2.book_id]
    assert body["pages_to_call"] == 2 * PAGES and body["approved"] is False
    assert body["estimate_usd"] > 0
    start = {"max_total_usd": 50, "yes_spend": True}
    resp = client.post(f"{BUILD}/full", json=start)
    assert resp.status_code == 409 and code(resp) == "GATE_NOT_APPROVED"
    assert client.post(f"{BUILD}/full", json={"yes_spend": True}).status_code == 422  # no cap
    assert fake.client.calls == []


def test_api_full_run_end_to_end(api: Callable[..., Any], approval: Approval) -> None:
    client, fake = api()
    no_spend = client.post(f"{BUILD}/full", json={"max_total_usd": 50})
    assert no_spend.status_code == 422 and code(no_spend) == "SPEND_NOT_CONFIRMED"
    assert fake.client.calls == []
    resp = client.post(f"{BUILD}/full", json={"max_total_usd": 50, "yes_spend": True})
    assert resp.status_code == 202, resp.text
    final = wait_full(client, ("done", "failed", "stopped_checkpoint"))
    assert final["status"] == "done", final
    assert [b["book_id"] for b in final["books"]] == [G1Q1.book_id, G1Q2.book_id]
    assert all(b["run_kind"] == "full" and b["pages_done"] == PAGES for b in final["books"])
    assert final["max_total_usd"] == 50 and final["spent_usd"] > 0
    assert len(fake.refs()) == 2 * PAGES
    current = client.get(f"{BUILD}/runs/current").json()
    assert current["run_kind"] == "full" and current["full_id"] == final["full_id"]


def test_api_cap_stop_and_concurrent_start(api: Callable[..., Any], approval: Approval) -> None:
    client, fake = api()
    resp = client.post(f"{BUILD}/full", json={"max_total_usd": 0.3, "yes_spend": True})
    assert resp.status_code == 202, resp.text
    final = wait_full(client, ("stopped_budget", "done"))
    assert final["status"] == "stopped_budget" and final["stop_reason"] == "budget"
    assert final["unstarted"] and len(fake.refs()) == 2
    again = start_full(client, {"max_total_usd": 50, "yes_spend": True})
    assert again.status_code == 202, again.text
    wait_full(client, ("done",))
    assert len(set(fake.refs())) == 2 * PAGES


def test_api_second_start_while_running_is_409(api: Callable[..., Any], approval: Approval) -> None:
    client, _fake = api(delay=0.15)
    body = {"max_total_usd": 50, "yes_spend": True}
    assert client.post(f"{BUILD}/full", json=body).status_code == 202
    resp = client.post(f"{BUILD}/full", json=body)
    assert resp.status_code == 409 and code(resp) == "RUN_IN_PROGRESS"
    pilot = client.post(
        f"{BUILD}/runs", json={"book_id": G1Q1.book_id, "pages": "1-1", "yes_spend": True}
    )
    assert pilot.status_code == 409 and code(pilot) == "RUN_IN_PROGRESS"
    current = client.get(f"{BUILD}/full/current").json()
    client.post(f"{BUILD}/runs/{current['current_run_id']}/cancel")
    wait_full(client, ("cancelled", "done"))


def test_api_pause_and_resume(api: Callable[..., Any], approval: Approval) -> None:
    client, fake = api(delay=0.1)
    body = {"max_total_usd": 50, "yes_spend": True}
    assert client.post(f"{BUILD}/full", json=body).status_code == 202
    for _ in range(200):
        if len(fake.refs()) >= 2:
            break
        time.sleep(0.05)
    current = client.get(f"{BUILD}/full/current").json()
    assert client.post(f"{BUILD}/runs/{current['current_run_id']}/pause").status_code == 200
    paused = wait_full(client, ("paused", "done"))
    assert paused["status"] == "paused"
    done_before = len(fake.refs())
    assert 0 < done_before < 2 * PAGES
    # The thread ends just after the row settles.
    for _ in range(100):
        resume = client.post(f"{BUILD}/runs/{paused['current_run_id']}/resume")
        if resume.status_code != 409:
            break
        time.sleep(0.05)
    assert resume.status_code == 200, resume.text
    final = wait_full(client, ("done",))
    assert final["full_id"] == paused["full_id"] and final["status"] == "done"
    assert len(fake.refs()) == 2 * PAGES  # no page called twice


def test_full_current_is_running_between_books(api: Callable[..., Any], approval: Approval) -> None:
    """Between two Books the latest row is the finished Book's `done` while the run's thread
    is still alive: the full run as a whole is still running, not done (a race the
    pause/resume test used to hit intermittently)."""
    client, _fake = api()
    body = {"max_total_usd": 50, "yes_spend": True}
    assert client.post(f"{BUILD}/full", json=body).status_code == 202
    assert wait_full(client, ("done",))["status"] == "done"
    manager = client.app.state.run_manager
    manager._full_running = True  # the thread is alive, its next Book's row not created yet
    try:
        assert client.get(f"{BUILD}/full/current").json()["status"] == "running"
    finally:
        manager._full_running = False
    assert client.get(f"{BUILD}/full/current").json()["status"] == "done"
