"""Story 1.9: spot-check, pilot report and go/no-go gate.

One test per row of the I/O matrix, the acceptance run (a fake-client pilot through
`hoctap build full`), and the service-level rules (allocation, invalidation, revoke).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, text
from test_extraction import (  # noqa: F401 - `env` is a fixture
    BOOK_ID,
    PAGE_DATA,
    draft,
    env,
    fixture_parts,
    page_data,
    rows,
)
from test_verify import Model, model, run  # noqa: F401 - `model` is a fixture

import hoctap.cli as cli
from hoctap.app import create_app
from hoctap.builder import gate, jobs_store
from hoctap.builder.claude_client import FakeClaudeClient
from hoctap.builder.models import build_costs
from hoctap.config import ConfigError, Settings, load_settings
from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    UnitRow,
    publish_problems,
    upsert_books,
)
from hoctap.content.effective import load_effective
from hoctap.content.review import service as review
from hoctap.content.review import spotcheck
from hoctap.db.engine import create_db_engine
from hoctap.ids import new_id, to_iso, utc_now
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-1", "tiet-1"
REVIEW = "/api/v1/parent/review"
GATE = "/api/v1/build/gate"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}
TYPES = ("number_input", "compare", "order", "match", "grid_fill")


def make_doc(n: int, problem_type: str, page: int) -> dict[str, Any]:
    doc = json.loads((FIXTURES / f"{problem_type}.json").read_text(encoding="utf-8"))
    label = f"bai-{n}"
    doc.update(
        problem_id=f"{BOOK}.{UNIT}.{LESSON}.{label}",
        unit_key=UNIT,
        lesson_key=LESSON,
        problem_label=label,
        display_label=f"Bài {n}",
        concept_ids=[],
        concept_proposals=[],
        source_pages=[{"page": page, "bbox": [0.05, 0.1, 0.95, 0.4]}],
    )
    for image in doc["images"]:
        image["page"] = page
    return doc


class World:
    """A pilot as the builder leaves it: book, extract jobs, costs and published Problems."""

    def __init__(self, engine: Engine, total_pages: int = 2140) -> None:
        self.engine = engine
        self.docs: list[dict[str, Any]] = []
        with engine.begin() as conn:
            upsert_books(
                conn,
                [BookRow(BOOK, "2020", 1, 1, "Toán 1 – Quyển 1", "x.pdf", total_pages, 1, "f")],
            )

    def pages(self, *pages: int) -> None:
        """Marks pages as extracted (done extract jobs)."""
        with self.engine.begin() as conn:
            for page in pages:
                jobs_store.record(conn, jobs_store.page_ref(BOOK, page), "extract", "h", "done")

    def cost(self, page: int, usd: float, *, unknown: bool = False, stage: str = "extract") -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(build_costs).values(
                    id=new_id(),
                    page_ref=jobs_store.page_ref(BOOK, page),
                    stage=stage,
                    input_hash="h",
                    attempt=1,
                    model="m",
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                    cost_usd=usd,
                    cost_unknown=int(unknown),
                    created_at=to_iso(utc_now()),
                )
            )

    def problems(self, counts: dict[str, int], page: int = 5) -> list[str]:
        """Publishes Problems of the given types on one page (all in one Lesson)."""
        for problem_type, n in counts.items():
            for _ in range(n):
                self.docs.append(make_doc(len(self.docs) + 1, problem_type, page))
        with self.engine.begin() as conn:
            publish_problems(
                conn,
                BOOK,
                units=[UnitRow(BOOK, UNIT, "TUẦN 1", "", 100)],
                lessons=[LessonRow(BOOK, UNIT, LESSON, "Tiết 1", "", 101)],
                problems=[
                    ProblemInput(
                        doc=d,
                        position=d["source_pages"][0]["page"] * 1000 + i,
                        needs_review=False,
                        verify_status="agree",
                        duplicate=False,
                    )
                    for i, d in enumerate(self.docs)
                ],
            )
        return [d["problem_id"] for d in self.docs]


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def world(engine: Engine) -> World:
    return World(engine)


def gate_report(client: TestClient) -> dict[str, Any]:
    resp = client.get(GATE)
    assert resp.status_code == 200, resp.text
    return resp.json()


def draw(client: TestClient) -> dict[str, Any]:
    resp = client.post(f"{REVIEW}/spot-check/draw")
    assert resp.status_code == 200, resp.text
    return resp.json()


def mark(client: TestClient, sample: dict[str, Any], problem_id: str, verdict: str, note: str = ""):
    item = next(i for i in sample["items"] if i["problem_id"] == problem_id)
    return client.put(
        f"{REVIEW}/spot-check/{sample['sample_id']}/items/{problem_id}",
        json={"verdict": verdict, "note": note, "content_hash": item["content_hash"]},
    )


def mark_all(client: TestClient, sample: dict[str, Any], wrong: int = 0) -> dict[str, Any]:
    out = sample
    for n, item in enumerate(sample["items"]):
        resp = mark(client, sample, item["problem_id"], "wrong" if n < wrong else "correct")
        assert resp.status_code == 200, resp.text
        out = resp.json()
    return out


def approve(client: TestClient, est: float, accept: bool = True):
    return client.post(f"{GATE}/approve", json={"accept_cost": accept, "est_cost_seen": est})


def code(resp) -> str:  # noqa: ANN001
    return resp.json()["error"]["code"]


def passing_pilot(client: TestClient, world: World) -> dict[str, Any]:
    """40 Problems over 16 pages, $3.20 spent, a sample all Đúng: both checks pass."""
    world.pages(*range(1, 17))
    for page in range(1, 17):
        world.cost(page, 0.15)
        world.cost(page, 0.05, stage="verify")
    world.problems({"number_input": 20, "compare": 10, "order": 5, "match": 3, "grid_fill": 2})
    mark_all(client, draw(client))
    return gate_report(client)


# --------------------------------------------------------------------------- matrix


def test_no_pilot(client: TestClient, world: World) -> None:
    report = gate_report(client)
    assert report["has_pilot"] is False and report["pilot_pages"] == 0
    assert report["checks_passed"] is False and report["approved"] is False
    resp = approve(client, 0.0)
    assert resp.status_code == 409 and code(resp) == "NO_PILOT"
    assert client.post(f"{REVIEW}/spot-check/draw").status_code == 409


def test_draw_sample_stratified(client: TestClient, engine: Engine, world: World) -> None:
    world.pages(5)
    counts = {"number_input": 20, "compare": 10, "order": 5, "match": 3, "grid_fill": 2}
    world.problems(counts)
    sample = draw(client)
    assert sample["size"] == 30 and len(sample["items"]) == 30
    got: dict[str, int] = {}
    for item in sample["items"]:
        got[item["problem_type"]] = got.get(item["problem_type"], 0) + 1
    assert set(got) == set(counts) and min(got.values()) >= 1
    assert got == {"number_input": 15, "compare": 7, "order": 4, "match": 2, "grid_fill": 2}
    assert [i["position"] for i in sample["items"]] == list(range(1, 31))
    with engine.connect() as conn:
        seed = conn.execute(text("SELECT seed FROM content_review_spot_check_samples")).scalar()
    assert seed == sample["seed"] and seed is not None


def test_same_seed_same_sample(engine: Engine, world: World) -> None:
    world.pages(5)
    ids = world.problems({"number_input": 20, "compare": 20})
    with engine.begin() as conn:
        a = spotcheck.draw_sample(conn, ids, 10, seed=7)
        b = spotcheck.draw_sample(conn, ids, 10, seed=7)
        rows_ = conn.execute(
            text("SELECT sample_id, problem_id, position FROM content_review_spot_checks")
        ).all()
    first = [(p, pos) for s, p, pos in rows_ if s == a]
    second = [(p, pos) for s, p, pos in rows_ if s == b]
    assert sorted(first, key=lambda x: x[1]) == sorted(second, key=lambda x: x[1])


def test_few_problems(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 8, "compare": 4})
    sample = draw(client)
    assert sample["size"] == 12
    mark_all(client, sample)
    acc = gate_report(client)["accuracy"]
    assert acc["correct"] == 12 and acc["value"] == 1.0
    assert acc["enough_sample"] is False and acc["passed"] is False


def test_mark_verdicts_one_wrong(client: TestClient, engine: Engine, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 25, "compare": 15})
    sample = mark_all(client, draw(client), wrong=1)
    acc = gate_report(client)["accuracy"]
    assert (acc["correct"], acc["wrong"]) == (29, 1)
    assert round(acc["value"] * 100, 1) == 96.7 and acc["passed"] is False
    # The Sai verdict opened a parent note: the Problem is in Cần duyệt.
    wrong_id = next(i["problem_id"] for i in sample["items"] if i["verdict"] == "wrong")
    queue = [p["problem_id"] for p in client.get(f"{REVIEW}/queue").json()]
    assert queue == [wrong_id]
    with engine.connect() as conn:
        kinds = conn.execute(text("SELECT kind, status FROM content_review_error_reports")).all()
    assert kinds == [("parent", "open")]


def test_all_correct(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 25, "compare": 15})
    mark_all(client, draw(client))
    acc = gate_report(client)["accuracy"]
    assert acc["value"] == 1.0 and acc["enough_sample"] is True and acc["passed"] is True


def test_stale_verdict(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 25, "compare": 15})
    sample = mark_all(client, draw(client))
    target = next(i for i in sample["items"] if i["problem_type"] == "number_input")
    edit = {"part_key": "a", "field": "hint", "value": "Con đếm tiếp nhé."}
    resp = client.put(f"{REVIEW}/problems/{target['problem_id']}/overrides", json={"edits": [edit]})
    assert resp.status_code == 200, resp.text
    now = client.get(f"{REVIEW}/spot-check").json()
    item = next(i for i in now["items"] if i["problem_id"] == target["problem_id"])
    assert item["stale"] is True and item["verdict"] == "correct"
    assert (now["checked"], now["stale"]) == (29, 1)
    acc = gate_report(client)["accuracy"]
    assert (acc["correct"], acc["stale"]) == (29, 1) and acc["passed"] is False
    # A verdict for the old hash is refused; the new hash can be re-checked.
    old = mark(client, sample, target["problem_id"], "correct")
    assert old.status_code == 409 and code(old) == "STALE"
    resp = mark(client, now, target["problem_id"], "correct")
    assert resp.status_code == 200 and resp.json()["stale"] == 0


def test_fallback_share(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 33, "fallback": 7})
    fb = gate_report(client)["fallback"]
    assert (fb["with_fallback"], fb["problems"]) == (7, 40)
    assert fb["value"] == pytest.approx(0.175) and fb["passed"] is False


def test_fallback_at_threshold_passes(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 34, "fallback": 6})
    fb = gate_report(client)["fallback"]
    assert fb["value"] == pytest.approx(0.15) and fb["passed"] is True


def test_cost(client: TestClient, world: World) -> None:
    world.pages(*range(1, 17))
    for page in range(1, 17):
        world.cost(page, 0.15)
        world.cost(page, 0.05, stage="verify")
    world.cost(99, 5.0)  # not a pilot page: not counted
    cost = gate_report(client)["cost"]
    assert cost["pilot_cost"] == pytest.approx(3.20)
    assert (cost["pilot_pages"], cost["total_pages"], cost["remaining_pages"]) == (16, 2140, 2124)
    assert cost["est_cost"] == 424.80
    assert cost["unknown_cost_calls"] == 0


def test_unknown_cost_counts_at_the_cap(client: TestClient, world: World) -> None:
    world.pages(1, 2)
    world.cost(1, 0.5)
    world.cost(2, 0.0, unknown=True)
    report = gate_report(client)
    cost = report["cost"]
    assert cost["unknown_cost_calls"] == 1 and cost["unknown_cost_cap_usd"] == 1.0
    assert cost["reported_cost"] == 0.5 and cost["pilot_cost"] == 1.5
    assert report["books"] == [{"book_id": BOOK, "pilot_pages": 2}]


def test_approve(client: TestClient, engine: Engine, world: World) -> None:
    report = passing_pilot(client, world)
    assert report["checks_passed"] is True
    resp = approve(client, report["cost"]["est_cost"])
    assert resp.status_code == 200, resp.text
    after = resp.json()
    assert after["approved"] is True and after["approval"]["valid"] is True
    assert gate_report(client)["approved"] is True
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM build_gate")).mappings().one()
    assert row["est_cost"] == 424.80 and row["sample_id"] == report["accuracy"]["sample_id"]
    assert json.loads(row["thresholds_json"]) == {
        "max_fallback_share": 0.15,
        "min_key_accuracy": 0.98,
        "min_sample": 30,
    }
    assert json.loads(row["metrics_json"])["key_accuracy"] == 1.0
    assert row["approved_at"] and row["revoked_at"] is None


def test_approve_failing(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 25, "compare": 15})
    mark_all(client, draw(client), wrong=1)
    report = gate_report(client)
    resp = approve(client, report["cost"]["est_cost"])
    assert resp.status_code == 409 and code(resp) == "GATE_CHECKS_FAILED"


def test_approve_stale_estimate(client: TestClient, world: World) -> None:
    report = passing_pilot(client, world)
    resp = approve(client, report["cost"]["est_cost"] + 0.01)
    assert resp.status_code == 409 and code(resp) == "ESTIMATE_CHANGED"
    assert approve(client, 424.804).status_code == 200  # the same to the cent


def test_approve_needs_accepted_cost(client: TestClient, world: World) -> None:
    report = passing_pilot(client, world)
    resp = approve(client, report["cost"]["est_cost"], accept=False)
    assert resp.status_code == 422 and code(resp) == "COST_NOT_ACCEPTED"


def test_invalidation_by_new_pilot_page(client: TestClient, world: World) -> None:
    report = passing_pilot(client, world)
    assert approve(client, report["cost"]["est_cost"]).status_code == 200
    world.pages(17)
    after = gate_report(client)
    assert after["approved"] is False
    assert after["approval"]["valid"] is False and after["approval"]["invalid_reasons"]


def test_invalidation_by_new_sample_and_thresholds(
    client: TestClient, engine: Engine, world: World
) -> None:
    report = passing_pilot(client, world)
    assert approve(client, report["cost"]["est_cost"]).status_code == 200
    settings = client.app.state.settings  # type: ignore[attr-defined]
    changed = Settings(**{**settings.__dict__, "gate_min_sample": 20})
    with engine.connect() as conn:
        assert gate.report(conn, settings).approved is True
        assert gate.report(conn, changed).approved is False
    draw(client)
    assert gate_report(client)["approved"] is False


def test_revoke(client: TestClient, world: World) -> None:
    report = passing_pilot(client, world)
    assert approve(client, report["cost"]["est_cost"]).status_code == 200
    resp = client.post(f"{GATE}/revoke")
    assert resp.status_code == 200
    assert resp.json()["approved"] is False and resp.json()["approval"] is None
    assert client.post(f"{GATE}/revoke").status_code == 200  # nothing left: no error


def test_auth(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
        c.cookies.clear()
        for method, path in (
            ("GET", GATE),
            ("POST", f"{GATE}/approve"),
            ("POST", f"{GATE}/revoke"),
            ("GET", f"{REVIEW}/spot-check"),
            ("POST", f"{REVIEW}/spot-check/draw"),
            ("PUT", f"{REVIEW}/spot-check/x/items/y"),
        ):
            resp = c.request(method, path, json={})
            assert resp.status_code == 401, (method, path)


# --------------------------------------------------------------------------- spot-check rules


def test_old_sample_is_kept_and_refuses_verdicts(client: TestClient, world: World) -> None:
    world.pages(5)
    world.problems({"number_input": 25, "compare": 15})
    first = draw(client)
    second = draw(client)
    assert first["sample_id"] != second["sample_id"]
    resp = mark(client, first, first["items"][0]["problem_id"], "correct")
    assert resp.status_code == 409 and code(resp) == "SAMPLE_OUTDATED"
    assert client.get(f"{REVIEW}/spot-check").json()["sample_id"] == second["sample_id"]
    assert len(rows_of(client, "SELECT sample_id FROM content_review_spot_check_samples")) == 2


def rows_of(client: TestClient, sql: str) -> list[Any]:
    engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        return list(conn.execute(text(sql)).all())


def test_hidden_and_retired_are_not_sampled(
    client: TestClient, engine: Engine, world: World
) -> None:
    world.pages(5)
    ids = world.problems({"number_input": 5})
    with engine.begin() as conn:
        review.set_hidden(conn, ids[0], True)
        review.add_error_report(conn, ids[1], "parent", "x")  # still reviewable
        conn.execute(
            text("UPDATE content_catalog_problems SET needs_review = 1 WHERE problem_id = :p"),
            {"p": ids[2]},
        )
        conn.execute(
            text("UPDATE content_catalog_problems SET retired_at = 'x' WHERE problem_id = :p"),
            {"p": ids[3]},
        )
    sample = draw(client)
    assert {i["problem_id"] for i in sample["items"]} == {ids[1], ids[2], ids[4]}


def test_verdicts_never_change_content_or_approval(
    client: TestClient, engine: Engine, world: World
) -> None:
    world.pages(5)
    ids = world.problems({"number_input": 3})
    with engine.begin() as conn:
        review.approve(conn, ids[0])
        before = {s.problem_id: (s.content_hash, s.approved) for s in load_effective(conn)}
    sample = draw(client)
    for item in sample["items"]:
        assert mark(client, sample, item["problem_id"], "wrong", "sai số").status_code == 200
    with engine.connect() as conn:
        after = {s.problem_id: (s.content_hash, s.approved) for s in load_effective(conn)}
        notes = conn.execute(text("SELECT note FROM content_review_error_reports")).all()
    assert after == before
    assert len(notes) == 3 and all("sai số" in n[0] for n in notes)
    # Marking Sai again for the same content does not open a second note.
    now = client.get(f"{REVIEW}/spot-check").json()
    assert mark(client, now, ids[0], "wrong").status_code == 200
    assert len(rows_of(client, "SELECT id FROM content_review_error_reports")) == 3


@pytest.mark.parametrize(
    ("counts", "size", "expected"),
    [
        ({"a": 20, "b": 10, "c": 5, "d": 3, "e": 2}, 30, {"a": 15, "b": 7, "c": 4, "d": 2, "e": 2}),
        ({"a": 12}, 30, {"a": 12}),
        ({"a": 39, "b": 1}, 30, {"a": 29, "b": 1}),
        ({"a": 5, "b": 5, "c": 5}, 2, {"a": 1, "b": 1, "c": 1}),
        ({"a": 10, "b": 0}, 5, {"a": 5}),
    ],
)
def test_allocate(counts: dict[str, int], size: int, expected: dict[str, int]) -> None:
    assert spotcheck.allocate(counts, size) == expected


def test_gate_config_keys(tmp_path: Path) -> None:
    config = tmp_path / "hoctap.toml"
    config.write_text(
        "[build]\ngate_max_fallback_share = 0.2\ngate_min_key_accuracy = 0.95\n"
        "gate_min_sample = 40\n",
        encoding="utf-8",
    )
    s = load_settings(config, env={})
    assert (s.gate_max_fallback_share, s.gate_min_key_accuracy, s.gate_min_sample) == (
        0.2,
        0.95,
        40,
    )
    d = load_settings(tmp_path / "none.toml", env={})
    assert (d.gate_max_fallback_share, d.gate_min_key_accuracy, d.gate_min_sample) == (
        0.15,
        0.98,
        30,
    )
    for bad in ("gate_min_key_accuracy = 1.5", "gate_min_sample = 0"):
        config.write_text(f"[build]\n{bad}\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_settings(config, env={})


# --------------------------------------------------------------------------- CLI


def full() -> int:
    return cli.main(["build", "full"])


def test_full_guard_without_approval(env: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    assert full() == 2
    assert "GATE_NOT_APPROVED" in capsys.readouterr().err


def test_gate_cli_without_pilot(env: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    assert cli.main(["build", "gate"]) == 0
    assert "Chưa chạy thử" in capsys.readouterr().out


def many_drafts(start: int, n: int) -> list[dict[str, Any]]:
    out = []
    for k in range(start, start + n):
        parts = fixture_parts("compare" if k % 3 == 0 else "number_input")
        out.append(draft(f"bai{k}", parts=parts))
    return out


def test_acceptance_pilot_spot_check_approve_full(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fake-client pilot with 30+ published Problems, the sample all Đúng, the cost
    accepted: `build full` passes the guard; one more pilot page makes it refuse again."""
    monkeypatch.setitem(PAGE_DATA, 5, page_data(many_drafts(1, 12), "TUẦN 3", "Tiết 2"))
    monkeypatch.setitem(PAGE_DATA, 6, page_data(many_drafts(13, 12)))
    monkeypatch.setitem(PAGE_DATA, 7, page_data(many_drafts(25, 12)))
    monkeypatch.setitem(PAGE_DATA, 8, page_data(many_drafts(37, 2)))
    assert run("pilot", "--yes-spend") == 0
    published = rows(env, "SELECT count(*) FROM content_catalog_problems")[0][0]
    assert published == 36

    settings = load_settings()
    engine = create_db_engine(settings.db_path)
    try:
        with engine.begin() as conn:
            sample_id = gate.draw_sample(conn, settings)
            for item in spotcheck.spot_check_out(conn).items:
                assert item.content_hash is not None
                spotcheck.set_verdict(
                    conn, sample_id, item.problem_id, "correct", item.content_hash
                )
            report = gate.report(conn, settings)
            assert report.checks_passed, report
            assert report.pilot_pages == 3 and report.pilot_problems == 36
            assert report.cost.est_cost is not None
            gate.approve(conn, settings, True, report.cost.est_cost)
        assert rows(env, "SELECT count(*) FROM build_gate")[0][0] == 1
        capsys.readouterr()
        assert full() == 0
        assert "chưa triển khai (Story 6.2)" in capsys.readouterr().out

        assert cli.main(["build", "gate"]) == 0
        assert "Đã duyệt" in capsys.readouterr().out

        # One more pilot page: the pilot warns, and the guard refuses again.
        assert run("pilot", "--yes-spend", pages="8-8") == 0
        assert "invalidate" in capsys.readouterr().err
        assert full() == 2
        assert "GATE_NOT_APPROVED" in capsys.readouterr().err
    finally:
        engine.dispose()
