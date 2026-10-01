"""Story 5.1: Concept Guides generated, edited, approved and spoken.

Every Claude call goes to `FakeClaudeClient` and every TTS call to a fake, so nothing
spawns the CLI or the network.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_review import API, BOOK, SETUP, Pub, err, make_doc

from hoctap import cli
from hoctap.builder import jobs_store
from hoctap.builder.claude_client import CallResult, FakeClaudeClient, PageRequest
from hoctap.builder.stages import guides, speak
from hoctap.config import Settings
from hoctap.content.effective import effective_concept_guide
from hoctap.content.speech import guide_speech_refs
from hoctap.parent import service as parent_service

CONCEPT = "g1.so-sanh-so"
GUIDE = {
    "explanation": "Số nào có nhiều chục hơn thì lớn hơn.",
    "example": {
        "question": "So sánh 35 và 28",
        "steps": ["3 chục lớn hơn 2 chục"],
        "answer": "35 > 28",
    },
}
EDITED = "Nhìn hàng chục trước, số nào nhiều chục hơn thì lớn hơn."
DOC_PAGE = 12  # the page of the fixture Problems


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path, tmp_path: Path):
    from hoctap.app import create_app

    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir)


@pytest.fixture
def concept(client: TestClient, engine: Engine) -> str:
    """Three Problems on page 12 linked to the accepted Concept `g1.so-sanh-so`."""
    Pub(engine)(*(make_doc(f"bai-{i}", ["So sánh số"]) for i in (1, 2, 3)))
    [prop] = client.get(f"{API}/concepts").json()["proposals"]
    resp = client.post(
        f"{API}/concepts/accept", json={"grade": 1, "proposal_key": prop["proposal_key"]}
    )
    assert resp.status_code == 200, resp.text
    return CONCEPT


def add_examples(engine: Engine, examples: list[dict[str, str]]) -> None:
    with engine.begin() as conn:
        jobs_store.record(
            conn,
            jobs_store.page_ref(BOOK, DOC_PAGE),
            "extract",
            "h-extract",
            "done",
            output={"problems": [], "worked_examples": examples},
        )


def ok(body: dict[str, Any] | None = None) -> CallResult:
    return CallResult(ok=True, output=body or GUIDE, cost_usd=0.1)


def fake(body: dict[str, Any] | CallResult | None = None) -> FakeClaudeClient:
    def respond(request: PageRequest) -> CallResult:
        return body if isinstance(body, CallResult) else ok(body)

    return FakeClaudeClient(respond)


def generate(
    engine: Engine, settings: Settings, client: FakeClaudeClient | None, **kw: Any
) -> guides.GuideReport:
    with engine.connect() as conn:
        tasks = guides.load_tasks(conn)
    return guides.run_guides(engine, client, settings, tasks, **kw)


def guide_url(cid: str = CONCEPT) -> str:
    return f"{API}/concepts/{cid}/guide"


def concept_row(client: TestClient) -> dict[str, Any]:
    [row] = client.get(f"{API}/concepts").json()["concepts"]
    return row


# --------------------------------------------------------------------------- generation


def test_generate_from_book(engine: Engine, settings: Settings, concept: str) -> None:
    add_examples(engine, [{"title": "Ví dụ 1", "text": "So sánh 35 và 28: 3 chục > 2 chục"}])
    claude = fake()
    report = generate(engine, settings, claude)
    assert report.generated == [CONCEPT] and not report.failed
    assert report.drafted_from_problems == []
    [request] = claude.calls
    assert "So sánh 35 và 28" in request.prompt and request.page_ref == f"guide:{CONCEPT}"
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT body_json, source, input_hash, model FROM content_catalog_concept_guides"
        ).one()
        job = conn.exec_driver_sql("SELECT run_kind, status FROM build_jobs WHERE stage='guide'")
        assert job.one() == ("full", "done")
        cost = conn.exec_driver_sql("SELECT stage FROM build_costs").all()
    assert json.loads(row[0]) == GUIDE and row[1] == "book" and row[3] == settings.extraction_model
    assert cost == [("guide",)]


def test_generate_from_problems_when_no_book_material(
    engine: Engine, settings: Settings, concept: str
) -> None:
    claude = fake()
    report = generate(engine, settings, claude)
    assert report.drafted_from_problems == [CONCEPT]
    assert "Sách không có ví dụ" in claude.calls[0].prompt
    with engine.connect() as conn:
        assert effective_concept_guide(conn, CONCEPT).source == "problems"  # type: ignore[union-attr]


def test_rerun_same_input_makes_no_call(engine: Engine, settings: Settings, concept: str) -> None:
    generate(engine, settings, fake())
    again = fake()
    report = generate(engine, settings, again)
    assert again.calls == [] and report.skipped == [CONCEPT] and report.generated == []
    # New book material changes the input hash: regenerated.
    add_examples(engine, [{"title": "", "text": "Khung lý thuyết mới"}])
    third = fake()
    assert generate(engine, settings, third).generated == [CONCEPT] and len(third.calls) == 1


def test_bad_output_fails_the_job_and_retries_next_run(
    engine: Engine, settings: Settings, concept: str
) -> None:
    long = {**GUIDE, "explanation": "x" * 400}
    report = generate(engine, settings, fake(long))
    assert CONCEPT in report.failed and report.generated == []
    with engine.connect() as conn:
        assert effective_concept_guide(conn, CONCEPT) is None
        status = conn.exec_driver_sql("SELECT status FROM build_jobs WHERE stage='guide'").one()
    assert status == ("failed",)
    good = fake()
    assert generate(engine, settings, good).generated == [CONCEPT] and len(good.calls) == 1


def test_dry_run_writes_requests_only(engine: Engine, settings: Settings, concept: str) -> None:
    report = generate(engine, settings, None, dry_run=True)
    [path] = report.requests_written
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["page_ref"] == f"guide:{CONCEPT}" and saved["argv"][:2] == ["claude", "-p"]
    with engine.connect() as conn:
        assert effective_concept_guide(conn, CONCEPT) is None
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM build_jobs").scalar() == 0


# --------------------------------------------------------------------------- CLI


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, data_dir: Path, concept: str, engine: Engine) -> Path:
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(data_dir))
    monkeypatch.delenv("HOCTAP_CONFIG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    return data_dir


def test_cli_refuses_without_yes_spend(
    monkeypatch: pytest.MonkeyPatch, cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claude = fake()
    monkeypatch.setattr(cli, "_claude_client", lambda settings: claude)
    assert cli.main(["build", "guides"]) == 2
    assert "--yes-spend" in capsys.readouterr().err and claude.calls == []


def test_cli_dry_run_and_spend(
    monkeypatch: pytest.MonkeyPatch, cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_client(settings):  # noqa: ANN001, ANN202
        raise AssertionError("dry run must not create a client")

    monkeypatch.setattr(cli, "_claude_client", no_client)
    assert cli.main(["build", "guides", "--dry-run"]) == 0
    assert (cli_env / "build" / "requests" / "guides" / f"{CONCEPT}.json").is_file()
    claude = fake()
    monkeypatch.setattr(cli, "_claude_client", lambda settings: claude)
    assert cli.main(["build", "guides", "--yes-spend", "--concept", CONCEPT]) == 0
    out = capsys.readouterr().out
    assert "1 generated" in out and CONCEPT in out and len(claude.calls) == 1
    con = sqlite3.connect(cli_env / "hoctap.db")
    try:
        assert con.execute("SELECT COUNT(*) FROM content_catalog_concept_guides").fetchone() == (1,)
    finally:
        con.close()
    assert cli.main(["build", "guides", "--yes-spend"]) == 0  # unchanged: no new call
    assert len(claude.calls) == 1


# --------------------------------------------------------------------------- review


def stored(client: TestClient, engine: Engine, settings: Settings) -> None:
    generate(engine, settings, fake())


def test_new_guide_is_unapproved_and_listed(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    assert concept_row(client)["has_guide"] is False
    assert client.get(guide_url()).status_code == 404
    stored(client, engine, settings)
    row = concept_row(client)
    assert (row["has_guide"], row["guide_source"], row["guide_approved"]) == (
        True,
        "problems",
        False,
    )
    body = client.get(guide_url()).json()
    assert body["effective"] == GUIDE and body["approved"] is False and body["overrides"] == []
    with engine.connect() as conn:
        assert effective_concept_guide(conn, CONCEPT).approved is False  # type: ignore[union-attr]


def test_approve_edit_reset(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    stored(client, engine, settings)
    h = client.get(guide_url()).json()["content_hash"]
    resp = client.post(f"{guide_url()}/approve", json={"content_hash": h})
    assert resp.status_code == 200 and resp.json()["approved"] is True
    assert concept_row(client)["guide_approved"] is True
    # An edit after approval hides it again.
    resp = client.put(guide_url(), json={"edits": [{"field": "explanation", "value": EDITED}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["effective"]["explanation"] == EDITED and body["approved"] is False
    assert body["generated"] == GUIDE and [o["field"] for o in body["overrides"]] == ["explanation"]
    # Stale approval is refused; the current hash works.
    assert client.post(f"{guide_url()}/approve", json={"content_hash": h}).status_code == 409
    resp = client.post(f"{guide_url()}/approve", json={"content_hash": body["content_hash"]})
    assert resp.json()["approved"] is True
    # Reset returns to the generated text (unapproved again: a different hash).
    reset = client.delete(guide_url()).json()
    assert reset["effective"] == GUIDE and reset["overrides"] == [] and reset["approved"] is False


def test_edit_validation_and_errors(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    stored(client, engine, settings)
    for value in ("", "x" * 400):
        resp = client.put(guide_url(), json={"edits": [{"field": "explanation", "value": value}]})
        assert resp.status_code == 422 and err(resp) == "INVALID_OVERRIDE"
    bad = {"question": "q", "steps": ["s"] * 6, "answer": "a"}
    resp = client.put(guide_url(), json={"edits": [{"field": "example", "value": bad}]})
    assert resp.status_code == 422
    assert client.get(guide_url()).json()["overrides"] == []
    missing = client.put(
        guide_url("g1.khong-co"), json={"edits": [{"field": "explanation", "value": EDITED}]}
    )
    assert missing.status_code == 404 and err(missing) == "CONCEPT_NOT_FOUND"
    unknown = client.post(f"{guide_url('g1.khong-co')}/approve", json={"content_hash": "x"})
    assert unknown.status_code == 404
    # Saving the generated value again is not an override.
    resp = client.put(
        guide_url(), json={"edits": [{"field": "explanation", "value": GUIDE["explanation"]}]}
    )
    assert resp.json()["overrides"] == []


def test_regeneration_keeps_the_edit_and_flags_the_conflict(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    stored(client, engine, settings)
    client.put(guide_url(), json={"edits": [{"field": "explanation", "value": EDITED}]})
    h = client.get(guide_url()).json()["content_hash"]
    client.post(f"{guide_url()}/approve", json={"content_hash": h})
    add_examples(engine, [{"title": "", "text": "Ví dụ mới"}])
    newer = {**GUIDE, "explanation": "Lời giải thích mới."}
    assert generate(engine, settings, fake(newer)).generated == [CONCEPT]
    body = client.get(guide_url()).json()
    assert body["effective"]["explanation"] == EDITED  # the override still wins
    assert body["conflict"] is True and body["overrides"][0]["conflict"] is True
    assert body["generated"]["explanation"] == "Lời giải thích mới."
    assert concept_row(client)["guide_conflict"] is True
    approved = client.post(f"{guide_url()}/approve", json={"content_hash": body["content_hash"]})
    assert approved.json()["conflict"] is False  # approving re-bases the override


def test_regeneration_with_new_text_unapproves(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    stored(client, engine, settings)
    h = client.get(guide_url()).json()["content_hash"]
    client.post(f"{guide_url()}/approve", json={"content_hash": h})
    add_examples(engine, [{"title": "", "text": "Ví dụ mới"}])
    generate(engine, settings, fake({**GUIDE, "explanation": "Khác."}))
    assert client.get(guide_url()).json()["approved"] is False


def test_problems_drafts_listed_first(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    other = make_doc("bai-9", ["Phép cộng"])
    other["source_pages"][0]["page"] = 13  # no worked example on this page
    # A re-publish replaces the Lesson's Problems, so publish all of them again.
    Pub(engine)(*(make_doc(f"bai-{i}", ["So sánh số"]) for i in (1, 2, 3)), other)
    [prop] = [
        p for p in client.get(f"{API}/concepts").json()["proposals"] if p["status"] == "proposed"
    ]
    client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": prop["proposal_key"]})
    add_examples(engine, [{"title": "", "text": "Ví dụ sách"}])  # page 12 only
    report = generate(engine, settings, fake())
    assert report.drafted_from_problems == ["g1.phep-cong"]
    rows = client.get(f"{API}/concepts").json()["concepts"]
    assert [(c["concept_id"], c["guide_source"]) for c in rows] == [
        ("g1.phep-cong", "problems"),
        (CONCEPT, "book"),
    ]


def test_guide_routes_need_parent(client: TestClient, concept: str) -> None:
    client.cookies.clear()
    for method, suffix in [("GET", ""), ("PUT", ""), ("DELETE", ""), ("POST", "/approve")]:
        assert client.request(method, guide_url() + suffix).status_code == 401


# --------------------------------------------------------------------------- speech


def test_edit_after_approval_voids_it_on_the_child_endpoint(
    client: TestClient, engine: Engine, settings: Settings, concept: str
) -> None:
    """Chains both halves of the content-safety claim through the real child-facing read
    (Story 5.2's `GET /library/concepts/{id}`): approve, edit, then confirm the child
    endpoint -- not just `effective_concept_guide()` -- now returns `guide: null` again."""
    stored(client, engine, settings)
    h = client.get(guide_url()).json()["content_hash"]
    assert client.post(f"{guide_url()}/approve", json={"content_hash": h}).status_code == 200
    child_url = f"/api/v1/library/concepts/{CONCEPT}"
    approved = client.get(child_url)
    assert approved.status_code == 200
    assert approved.json()["guide"] == {
        "explanation": GUIDE["explanation"],
        "example": GUIDE["example"],
    }
    resp = client.put(guide_url(), json={"edits": [{"field": "explanation", "value": EDITED}]})
    assert resp.status_code == 200, resp.text
    voided = client.get(child_url)
    assert voided.status_code == 200
    assert voided.json()["guide"] is None


def test_guide_text_is_spoken_and_edits_change_the_keys(
    client: TestClient, engine: Engine, settings: Settings, concept: str, tmp_path: Path
) -> None:
    from hoctap.content.schema import ConceptGuideDoc

    stored(client, engine, settings)
    voice = settings.tts_voice_id
    doc = ConceptGuideDoc.model_validate(GUIDE)
    want = {r.speech_key: r.text for r in guide_speech_refs(doc, voice)}
    assert len(want) == 4  # explanation, question, one step, answer
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, tmp_path, voice)
    assert want.items() <= refs.items()
    client.put(guide_url(), json={"edits": [{"field": "explanation", "value": EDITED}]})
    with engine.connect() as conn:
        after = speak.collect_refs(conn, tmp_path, voice)
    new = set(after) - set(refs)
    assert [after[k] for k in new] == [EDITED]
    assert guide_speech_refs(doc, voice)[0].speech_key not in after  # old text: orphaned
