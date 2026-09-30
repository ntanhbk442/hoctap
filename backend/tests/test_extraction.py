"""Story 1.5: render -> extract -> validate for pilot pages (`hoctap build pilot`).

One test per row of the I/O matrix, run on a small generated PDF in a temporary source
folder. Every Claude call goes to `FakeClaudeClient`; the real CLI is never spawned (the
`ClaudeCliClient` test stubs `subprocess.run`).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import pymupdf
import pytest
from test_problemdoc import _collapsed, _count

import hoctap.cli as cli
from hoctap.builder.catalogue import build_catalogue
from hoctap.builder.claude_client import (
    CallResult,
    ClaudeCliClient,
    FakeClaudeClient,
    FakeCrash,
    PageRequest,
    Usage,
    cli_argv,
    parse_cli_output,
)
from hoctap.builder.costs import cost_usd, estimate
from hoctap.builder.extraction.models import (
    PageExtraction,
    build_extraction_schema,
    extraction_schema,
)
from hoctap.builder.stages.render import (
    MAX_IMAGE_BYTES,
    RenderError,
    encode_jpeg,
    render_image,
    render_pixmap,
)
from hoctap.builder.stages.validate import PageInput, heading_key, validate_book
from hoctap.config import ConfigError, load_settings
from hoctap.content import PROBLEM_TYPES, ProblemDoc
from hoctap.content.catalog.books import BOOKS
from hoctap.db.engine import create_db_engine, run_migrations

BOOK = BOOKS[0]  # toan1-2020-q1
BOOK_ID = BOOK.book_id
PAGES = 10
FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"

# --------------------------------------------------------------------------- helpers


def fixture_parts(problem_type: str) -> list[dict[str, Any]]:
    raw = json.loads((FIXTURES / f"{problem_type}.json").read_text(encoding="utf-8"))
    return raw["parts"]


def draft(
    label: str,
    *,
    continues: bool = False,
    parts: list[dict[str, Any]] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "problem_label": label,
        "display_label": f"Bài {label.removeprefix('bai')}",
        "instruction": "Tính:",
        "layout": "sequence",
        "bbox": [0.05, 0.5, 0.95, 0.95] if continues else [0.05, 0.1, 0.95, 0.4],
        "images": images or [],
        "parts": parts if parts is not None else fixture_parts("number_input"),
        "concept_proposals": ["Phép cộng trong phạm vi 10"],
        "continues_on_next_page": continues,
        "next_page_bbox": [0.05, 0.05, 0.95, 0.3] if continues else None,
    }


def page_data(
    problems: list[dict[str, Any]],
    unit: str | None = None,
    lesson: str | None = None,
    *,
    unit_y: float = 0.02,
    lesson_y: float = 0.05,
) -> dict[str, Any]:
    return {
        "unit_heading": {"label": unit, "title": "", "y": unit_y} if unit else None,
        "lesson_heading": {"label": lesson, "title": "", "y": lesson_y} if lesson else None,
        "problems": problems,
        "worked_examples": [],
        "page_notes": "",
    }


def continued_draft() -> dict[str, Any]:
    parts = fixture_parts("count_image")
    return draft(
        "bai1",
        continues=True,
        parts=parts,
        images=[
            {"image_key": "con-vat", "on_next_page": True, "bbox": [0.1, 0.1, 0.5, 0.3]},
        ],
    )


# p5: TUẦN 3 / Tiết 2 with Bài 1 (continues onto p6) and Bài 2; p6: Bài 3;
# p7: "Phiếu tự luyện cuối tuần" with Bài 1.
PAGE_DATA = {
    5: page_data([continued_draft(), draft("bai2")], unit="TUẦN 3", lesson="Tiết 2"),
    6: page_data([draft("bai3")]),
    7: page_data([draft("bai1")], lesson="Phiếu tự luyện cuối tuần"),
}
USAGE = Usage(input_tokens=20000, output_tokens=6000, cache_read_input_tokens=1000)


def page_of(request: PageRequest) -> int:
    return int(request.page_ref.rsplit("#p", 1)[1])


def ok(data: dict[str, Any]) -> CallResult:
    return CallResult(ok=True, output=data, cost_usd=0.25, usage=USAGE)


def respond(overrides: dict[int, CallResult | dict[str, Any]] | None = None):
    overrides = overrides or {}

    def responder(request: PageRequest) -> CallResult:
        page = page_of(request)
        value = overrides.get(page, PAGE_DATA.get(page, page_data([])))
        return value if isinstance(value, CallResult) else ok(value)

    return responder


def write_pdf(path: Path, pages: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page(width=552, height=818).insert_text((72, 72), f"Trang {i + 1}")
    doc.save(path)
    doc.close()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A catalogue with one 10-page book; small renders; the fake as the Claude client."""
    source = tmp_path / "Sach_Arch"
    write_pdf(source / BOOK.source_path, PAGES)
    data = tmp_path / "data"
    config = tmp_path / "hoctap.toml"
    config.write_text("[build]\nrender_long_edge = 300\n", encoding="utf-8")
    monkeypatch.setenv("HOCTAP_CONFIG", str(config))
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(data))
    monkeypatch.setenv("HOCTAP_SOURCE_DIR", str(source))
    engine = create_db_engine(data / "hoctap.db")
    run_migrations(engine)
    build_catalogue(engine, source, books=(BOOK,))
    engine.dispose()
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    return data


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClaudeClient:
    client = FakeClaudeClient(respond())
    use(monkeypatch, client)
    return client


def use(monkeypatch: pytest.MonkeyPatch, client: FakeClaudeClient) -> None:
    monkeypatch.setattr(cli, "_claude_client", lambda settings: client)


def pilot(*extra: str, pages: str = "5-7") -> int:
    """`build pilot` without the verify stage (Story 1.6 has its own tests)."""
    argv = ["build", "pilot", "--book", BOOK_ID, "--pages", pages, "--no-verify", *extra]
    return cli.main(argv)


def rows(data: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(data / "hoctap.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def jobs(data: Path, stage: str) -> dict[str, str]:
    return dict(
        rows(
            data,
            "SELECT page_ref, status FROM build_jobs "
            f"WHERE stage = '{stage}' AND page_ref NOT LIKE '%#book'",
        )
    )


def docs(data: Path) -> dict[str, dict[str, Any]]:
    return {
        pid: json.loads(doc)
        for pid, doc in rows(
            data, "SELECT problem_id, doc_json FROM build_page_results WHERE status = 'valid'"
        )
    }


def images(data: Path) -> list[str]:
    folder = data / "assets" / "pages" / BOOK_ID
    return sorted(p.name for p in folder.glob("*.jpg")) if folder.is_dir() else []


# --------------------------------------------------------------------------- schema


def test_page_extraction_schema_keeps_every_answer_shape() -> None:
    schema = anthropic.transform_schema(PageExtraction)
    defs = schema["$defs"]
    part_defs = [d for d in defs.values() if "enum" in d.get("properties", {}).get("type", {})]
    assert {d["properties"]["type"]["enum"][0] for d in part_defs} == set(PROBLEM_TYPES)
    for part in part_defs:
        tag = part["properties"]["type"]["enum"][0]
        answer = part["properties"]["answer"]
        if tag == "fallback":
            assert answer["type"] == "null"
        else:
            assert not _collapsed(answer, defs), tag
    # Within the structured-output limits (24 optional, 16 unions): the ProblemDoc's
    # 10 optional / 8 unions, plus the two nullable headings and next_page_bbox.
    assert _count(schema) == (10, 11)


def test_committed_extraction_schema_is_current(tmp_path: Path) -> None:
    out = tmp_path / "page_extraction.schema.json"
    assert cli.main(["export-extraction-schema", "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == build_extraction_schema()
    # The runtime reads the committed copy: regenerate it whenever the models change.
    committed = json.loads(cli.DEFAULT_EXTRACTION_SCHEMA_OUT.read_text(encoding="utf-8"))
    assert committed == written == extraction_schema()


def test_cli_schema_drops_only_cosmetic_titles() -> None:
    schema = build_extraction_schema()
    text = json.dumps(schema)
    assert '"title": "' not in text.replace('"title": {', "")  # no string titles left
    assert set(schema["$defs"]["Heading"]["properties"]) == {"label", "title", "y"}
    assert schema["$defs"]["WorkedExample"]["required"] == ["title", "text"]
    with_titles = anthropic.transform_schema(PageExtraction)
    assert set(schema["$defs"]) == set(with_titles["$defs"])


# --------------------------------------------------------------------------- matrix


def test_dry_run_renders_and_writes_requests(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_client(settings):  # noqa: ANN001, ANN202
        raise AssertionError("dry run must not create a client")

    monkeypatch.setattr(cli, "_claude_client", no_client)
    assert pilot("--dry-run") == 0
    out = capsys.readouterr().out
    assert "Estimate: 3 trang" in out and "Worst case: $6.00" in out and "retry" in out
    # The 3 pilot pages, plus page 8 as the next-page context for page 7.
    assert images(env) == ["p005.jpg", "p006.jpg", "p007.jpg", "p008.jpg"]
    for name in images(env):
        pix = pymupdf.Pixmap(str(env / "assets" / "pages" / BOOK_ID / name))
        assert max(pix.width, pix.height) == 300
    folder = env / "build" / "requests" / BOOK_ID
    requests = sorted(p.name for p in folder.glob("*.json"))
    assert requests == ["p005.json", "p006.json", "p007.json"]
    saved = json.loads((folder / "p007.json").read_text(encoding="utf-8"))
    argv = saved["argv"]
    assert argv[:2] == ["claude", "-p"] and "p007.jpg" in argv[2] and "p008.jpg" in argv[2]
    assert json.loads(argv[argv.index("--json-schema") + 1]) == extraction_schema()
    assert (folder / "p007.prompt.txt").read_text(encoding="utf-8").strip() == argv[2]
    assert jobs(env, "extract") == {}
    assert rows(env, "SELECT COUNT(*) FROM build_costs") == [(0,)]


def test_guard_refuses_without_yes_spend(
    env: Path, fake: FakeClaudeClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pilot() == 2
    err = capsys.readouterr().err
    assert "--yes-spend" in err and "Nothing was sent" in err
    assert fake.calls == []
    assert images(env) == []


def test_happy_path(env: Path, fake: FakeClaudeClient, capsys: pytest.CaptureFixture[str]) -> None:
    assert pilot("--yes-spend") == 0
    out = capsys.readouterr().out
    assert "3 done, 0 failed" in out
    assert sorted(page_of(r) for r in fake.calls) == [5, 6, 7]
    assert jobs(env, "extract") == {f"{BOOK_ID}#p{p:03d}": "done" for p in (5, 6, 7)}
    assert jobs(env, "validate") == {f"{BOOK_ID}#p{p:03d}": "done" for p in (5, 6, 7)}

    stored = docs(env)
    assert sorted(stored) == [
        f"{BOOK_ID}.tuan03.phieu.bai1",
        f"{BOOK_ID}.tuan03.tiet2.bai1",
        f"{BOOK_ID}.tuan03.tiet2.bai2",
        f"{BOOK_ID}.tuan03.tiet2.bai3",  # page 6: headings carried forward from page 5
    ]
    for doc in stored.values():
        ProblemDoc.model_validate(doc)
    # One cost row per call, with tokens and the CLI's cost.
    costs = rows(
        env,
        "SELECT page_ref, input_tokens, output_tokens, cache_read_input_tokens, cost_usd "
        "FROM build_costs ORDER BY page_ref",
    )
    assert costs == [(f"{BOOK_ID}#p{p:03d}", 20000, 6000, 1000, 0.25) for p in (5, 6, 7)]
    assert "$0.7500" in out


def test_resume_does_nothing_again(
    env: Path, fake: FakeClaudeClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pilot("--yes-spend") == 0
    before = rows(env, "SELECT * FROM build_page_results ORDER BY page_ref, draft_index")
    capsys.readouterr()
    assert pilot("--yes-spend") == 0
    out = capsys.readouterr().out
    assert "render: 0 rendered" in out
    assert "nothing to do" in out and "validate: unchanged" in out
    assert len(fake.calls) == 3  # no new calls
    assert rows(env, "SELECT * FROM build_page_results ORDER BY page_ref, draft_index") == before
    # Without --yes-spend the re-run is allowed too: nothing would be sent.
    assert pilot() == 0
    assert len(fake.calls) == 3


def test_crash_mid_run_resumes_without_redoing_done_pages(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call that raises (the run dies) still lets the finished pages be recorded; the
    re-run calls Claude only for the page that never finished."""
    base = respond()

    def crash_on_6(request: PageRequest) -> CallResult:
        if page_of(request) == 6:
            raise FakeCrash(request.page_ref)
        return base(request)

    use(monkeypatch, FakeClaudeClient(crash_on_6))
    # The crash is re-raised after the other pages are recorded; the CLI reports it.
    assert pilot("--yes-spend") == 1
    # The pages that finished before the crash are kept.
    assert jobs(env, "extract") == {f"{BOOK_ID}#p005": "done", f"{BOOK_ID}#p007": "done"}

    again = FakeClaudeClient(respond())
    use(monkeypatch, again)
    assert pilot("--yes-spend") == 0
    assert [page_of(r) for r in again.calls] == [6]
    assert set(jobs(env, "extract").values()) == {"done"}
    assert len(docs(env)) == 4


def test_continuation_merges_the_next_page(env: Path, fake: FakeClaudeClient) -> None:
    assert pilot("--yes-spend") == 0
    doc = docs(env)[f"{BOOK_ID}.tuan03.tiet2.bai1"]
    assert [p["page"] for p in doc["source_pages"]] == [5, 6]
    assert doc["source_pages"][1]["bbox"] == [0.05, 0.05, 0.95, 0.3]
    assert doc["images"] == [{"image_key": "con-vat", "page": 6, "bbox": [0.1, 0.1, 0.5, 0.3]}]
    assert doc["parts"][0]["type"] == "count_image"


def test_refusal_fails_only_that_page(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    refusal = CallResult(
        ok=False, error="no structured_output (refusal or schema failure): ", cost_usd=0.01
    )
    client = FakeClaudeClient(respond({6: refusal}))
    use(monkeypatch, client)
    assert pilot("--yes-spend") == 0
    captured = capsys.readouterr()
    assert "Warning: 1" in captured.err and f"{BOOK_ID}#p006" in captured.err
    assert jobs(env, "extract") == {
        f"{BOOK_ID}#p005": "done",
        f"{BOOK_ID}#p006": "failed",
        f"{BOOK_ID}#p007": "done",
    }
    assert sorted(page_of(r) for r in client.calls) == [5, 6, 7]  # a refusal is not retried
    assert f"{BOOK_ID}.tuan03.tiet2.bai3" not in docs(env)
    assert len(docs(env)) == 3
    # The failed page's spend is still recorded.
    assert rows(env, f"SELECT cost_usd FROM build_costs WHERE page_ref = '{BOOK_ID}#p006'") == [
        (0.01,)
    ]


def test_transient_error_is_retried_once(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: dict[int, int] = {}
    flaky = CallResult(ok=False, error="exit 1, subtype 'error_during_execution'", transient=True)

    def responder(request: PageRequest) -> CallResult:
        page = page_of(request)
        attempts[page] = attempts.get(page, 0) + 1
        if page == 6 and attempts[page] == 1:
            return flaky
        if page == 7:
            return flaky  # fails twice: the page is failed after one retry
        return ok(PAGE_DATA[page])

    use(monkeypatch, FakeClaudeClient(responder))
    assert pilot("--yes-spend") == 0
    assert attempts == {5: 1, 6: 2, 7: 2}
    assert jobs(env, "extract")[f"{BOOK_ID}#p006"] == "done"
    assert jobs(env, "extract")[f"{BOOK_ID}#p007"] == "failed"
    assert rows(
        env, f"SELECT attempt FROM build_costs WHERE page_ref = '{BOOK_ID}#p006' ORDER BY attempt"
    ) == [(1,), (2,)]


def test_invalid_draft_is_stored_with_errors(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_parts = fixture_parts("number_input")
    bad_parts[0]["answer"] = []  # the slot has no Answer Key
    page5 = page_data(
        [draft("bai1"), draft("bai2", parts=bad_parts), {"problem_label": "Bài 9"}],
        unit="TUẦN 3",
        lesson="Tiết 2",
    )
    use(monkeypatch, FakeClaudeClient(respond({5: page5})))
    assert pilot("--yes-spend") == 0
    results = rows(
        env,
        "SELECT draft_index, status, problem_id, errors_json FROM build_page_results "
        f"WHERE page_ref = '{BOOK_ID}#p005' ORDER BY draft_index",
    )
    assert [(r[0], r[1]) for r in results] == [(0, "valid"), (1, "invalid"), (2, "invalid")]
    assert results[1][2] == f"{BOOK_ID}.tuan03.tiet2.bai2"  # an id, so review can find it
    assert "answer must cover exactly its slots" in results[1][3]
    assert results[2][2] is None and json.loads(results[2][3])
    assert jobs(env, "validate")[f"{BOOK_ID}#p005"] == "done"
    assert len(docs(env)) == 3  # p5 bai1, p6 bai3, p7 bai1


def test_missing_claude_cli_exits_before_rendering(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert pilot("--yes-spend") == 2
    assert "PATH" in capsys.readouterr().err
    assert images(env) == []


@pytest.mark.parametrize("pages", ["0-2", "5-11", "7-5", "abc", "3-x"])
def test_bad_range_exits_2(
    env: Path, fake: FakeClaudeClient, pages: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["build", "pilot", "--book", BOOK_ID, "--pages", pages, "--dry-run"]) == 2
    assert capsys.readouterr().err
    assert images(env) == []


def test_unknown_book_exits_2(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["build", "pilot", "--book", "toan9-2020-q1", "--pages", "1-2"]) == 2
    assert "toan9-2020-q1" in capsys.readouterr().err


def test_changed_source_file_exits_2(env: Path, tmp_path: Path) -> None:
    write_pdf(tmp_path / "Sach_Arch" / BOOK.source_path, PAGES + 1)
    assert pilot("--dry-run") == 2


# --------------------------------------------------------------------------- validate


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("TUẦN 3", "tuan03"),
        ("Tuần 12", "tuan12"),
        ("Tiết 2", "tiet2"),
        ("TIẾT 10", "tiet10"),
        ("Phiếu tự luyện cuối tuần", "phieu"),
        ("Chương I", "chuong1"),
        ("Chương IV", "chuong4"),
        ("Chủ đề 2", "chude2"),
        ("Ôn tập 3", "ontap3"),
        ("123", None),
    ],
)
def test_heading_key(label: str, key: str | None) -> None:
    assert heading_key(label) == key


def test_pages_before_the_first_heading_use_defaults_and_duplicates_are_suffixed() -> None:
    pages = [
        PageInput(3, "h3", page_data([draft("bai1")])),
        PageInput(4, "h4", page_data([draft("bai1"), draft("bai1")], unit="Tuần 1")),
        PageInput(5, "h5", page_data([draft("bai1")], lesson="Tiết 1")),
    ]
    outcomes = validate_book(BOOK_ID, pages, 50)
    ids = [[(d.problem_id, d.duplicate) for d in o.drafts] for o in outcomes]
    assert ids == [
        [(f"{BOOK_ID}.u00.l00.bai1", False)],
        [(f"{BOOK_ID}.tuan01.l00.bai1", False), (f"{BOOK_ID}.tuan01.l00.bai1-2", True)],
        [(f"{BOOK_ID}.tuan01.tiet1.bai1", False)],
    ]
    assert outcomes[1].drafts[1].doc["problem_label"] == "bai1-2"
    # The input hash of a page depends on the pages up to the next one.
    changed = validate_book(BOOK_ID, [*pages[:2], PageInput(5, "other", pages[2].data)], 50)
    assert changed[0].input_hash == outcomes[0].input_hash
    assert changed[1].input_hash != outcomes[1].input_hash


def test_continuation_on_the_last_page_is_invalid() -> None:
    [outcome] = validate_book(BOOK_ID, [PageInput(50, "h", page_data([continued_draft()]))], 50)
    assert outcome.drafts[0].status == "invalid"


# --------------------------------------------------------------------------- more pipeline


def test_changed_model_re_extracts_every_page(
    env: Path, fake: FakeClaudeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert pilot("--yes-spend") == 0
    monkeypatch.setenv("HOCTAP_EXTRACTION_MODEL", "claude-other")
    assert pilot("--yes-spend") == 0
    assert sorted(page_of(r) for r in fake.calls) == [5, 5, 6, 6, 7, 7]
    assert {r.model for r in fake.calls[3:]} == {"claude-other"}


def test_malformed_output_is_retried_once_then_fails(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeClaudeClient(respond({6: {"problems": "x"}}))
    use(monkeypatch, client)
    assert pilot("--yes-spend") == 0
    assert sorted(page_of(r) for r in client.calls) == [5, 6, 6, 7]
    assert jobs(env, "extract")[f"{BOOK_ID}#p006"] == "failed"
    err = capsys.readouterr().err
    assert f"{BOOK_ID}#p006" in err and "not a page extraction" in err


def test_headings_carry_across_runs(env: Path, fake: FakeClaudeClient) -> None:
    assert pilot("--yes-spend", pages="5-5") == 0
    assert pilot("--yes-spend", pages="6-6") == 0
    assert f"{BOOK_ID}.tuan03.tiet2.bai3" in docs(env)
    assert f"{BOOK_ID}.tuan03.tiet2.bai2" in docs(env)  # page 5 rows are rebuilt, not lost


def test_deleted_image_is_re_rendered_without_new_calls(
    env: Path, fake: FakeClaudeClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pilot("--yes-spend") == 0
    (env / "assets" / "pages" / BOOK_ID / "p006.jpg").unlink()
    capsys.readouterr()
    assert pilot("--yes-spend") == 0
    assert "render: 1 rendered" in capsys.readouterr().out
    assert len(fake.calls) == 3  # the same image content: the same extract hash


def test_unknown_cost_is_recorded(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = CallResult(ok=False, error="timed out", transient=True, cost_unknown=True)
    use(monkeypatch, FakeClaudeClient(respond({6: timeout})))
    assert pilot("--yes-spend") == 0
    assert rows(
        env, f"SELECT cost_usd, cost_unknown FROM build_costs WHERE page_ref = '{BOOK_ID}#p006'"
    ) == [(0.0, 1), (0.0, 1)]


def test_run_budget_stops_new_pages(
    env: Path,
    fake: FakeClaudeClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOCTAP_EXTRACTION_CONCURRENCY", "1")
    assert pilot("--yes-spend", "--max-total-usd", "0.3") == 0
    assert [page_of(r) for r in fake.calls] == [5, 6]  # 0.25 < 0.3, then 0.50 >= 0.3
    err = capsys.readouterr().err
    assert "budget" in err and f"{BOOK_ID}#p007" in err
    assert f"{BOOK_ID}#p007" not in jobs(env, "extract")


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "x"])
def test_bad_max_total_usd_is_rejected(env: Path, value: str) -> None:
    with pytest.raises(SystemExit):
        pilot("--yes-spend", "--max-total-usd", value)


def test_pilot_max_pages(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOCTAP_PILOT_MAX_PAGES", "2")
    assert pilot("--dry-run") == 2
    assert images(env) == []
    assert pilot("--dry-run", pages="5-6") == 0


def test_failed_re_extraction_removes_stale_rows(
    env: Path, fake: FakeClaudeClient, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    assert pilot("--yes-spend") == 0
    monkeypatch.setenv("HOCTAP_EXTRACTION_MODEL", "claude-other")
    refusal = CallResult(ok=False, error="no structured_output (refusal)")
    use(monkeypatch, FakeClaudeClient(respond({6: refusal})))
    capsys.readouterr()
    assert pilot("--yes-spend") == 0
    assert "stale pages" in capsys.readouterr().out
    assert rows(env, "SELECT DISTINCT page FROM build_page_results ORDER BY page") == [(5,), (7,)]


def test_render_error_exits_1(env: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise RenderError("page 5 has zero size")

    monkeypatch.setattr("hoctap.builder.stages.render.run_render", broken)
    assert pilot("--dry-run") == 1
    assert "zero size" in capsys.readouterr().err


# --------------------------------------------------------------------------- validate rules


def test_mid_page_heading_keeps_problems_above_it() -> None:
    top = draft("bai5")  # bbox top 0.1
    below = draft("bai1") | {"bbox": [0.05, 0.6, 0.95, 0.9]}
    pages = [
        PageInput(4, "h4", page_data([draft("bai4")], unit="Tuần 1", lesson="Tiết 1")),
        PageInput(5, "h5", page_data([top, below], lesson="Tiết 2", lesson_y=0.5)),
        PageInput(6, "h6", page_data([draft("bai2")])),
    ]
    ids = [d.problem_id for o in validate_book(BOOK_ID, pages, 50) for d in o.drafts]
    assert ids == [
        f"{BOOK_ID}.tuan01.tiet1.bai4",
        f"{BOOK_ID}.tuan01.tiet1.bai5",
        f"{BOOK_ID}.tuan01.tiet2.bai1",
        f"{BOOK_ID}.tuan01.tiet2.bai2",
    ]


def test_unparsable_heading_keeps_previous_keys_with_a_warning() -> None:
    pages = [
        PageInput(4, "h4", page_data([draft("bai1")], unit="Tuần 2", lesson="Tiết 3")),
        PageInput(5, "h5", page_data([draft("bai2")], unit="123")),
    ]
    outcomes = validate_book(BOOK_ID, pages, 50)
    assert outcomes[1].drafts[0].problem_id == f"{BOOK_ID}.tuan02.tiet3.bai2"
    assert outcomes[1].warnings and "123" in outcomes[1].warnings[0]


def test_duplicate_suffix_skips_taken_labels_fits_the_key_and_ignores_invalid() -> None:
    bad_parts = fixture_parts("number_input")
    bad_parts[0]["answer"] = []
    long = "abcdefghijklmnop"  # 16 characters, the key maximum
    page = page_data(
        [
            draft("bai1", parts=bad_parts),  # invalid: takes no id
            draft("bai1"),
            draft("bai1-2"),
            draft("bai1"),
            draft(long),
            draft(long),
        ]
    )
    [outcome] = validate_book(BOOK_ID, [PageInput(5, "h", page)], 50)
    got = [
        (d.status, d.problem_id and d.problem_id.rsplit(".", 1)[1], d.duplicate)
        for d in outcome.drafts
    ]
    assert got == [
        ("invalid", "bai1", False),
        ("valid", "bai1", False),
        ("valid", "bai1-2", False),
        ("valid", "bai1-3", True),
        ("valid", long, False),
        ("valid", "abcdefghijklmn-2", True),
    ]


@pytest.mark.parametrize(("label", "key"), [("Chương IIII", "chuong"), ("Chương IX", "chuong9")])
def test_only_canonical_roman_numerals(label: str, key: str) -> None:
    assert heading_key(label) == key


# --------------------------------------------------------------------------- render, costs


def test_render_long_edge_fits_the_limit(tmp_path: Path) -> None:
    path = tmp_path / "a.pdf"
    write_pdf(path, 1)
    with pymupdf.open(path) as doc:
        pix = pymupdf.Pixmap(render_image(doc, 1, 2576))
    assert max(pix.width, pix.height) == 2576
    assert abs(pix.width - 552 * 2576 / 818) <= 1


def test_noisy_page_jpeg_stays_under_the_limit(tmp_path: Path) -> None:
    width, height = 1100, 1600
    noise = pymupdf.Pixmap(pymupdf.csRGB, width, height, os.urandom(width * height * 3), 0)
    doc = pymupdf.open()
    page = doc.new_page(width=552, height=818)
    page.insert_image(page.rect, pixmap=noise)
    data = render_image(doc, 1, 2576)
    assert data[:2] == b"\xff\xd8"  # a JPEG
    assert len(data) <= MAX_IMAGE_BYTES
    with pytest.raises(RenderError):
        encode_jpeg(render_pixmap(doc, 1, 2576), 1, max_bytes=1000)


def test_zero_size_page_raises() -> None:
    doc = [SimpleNamespace(rect=pymupdf.Rect(0, 0, 0, 0))]
    with pytest.raises(RenderError, match="zero size"):
        render_pixmap(doc, 1, 2576)  # type: ignore[arg-type]


def test_costs(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "absent.toml", env={})
    assert cost_usd(Usage(input_tokens=1_000_000, output_tokens=1_000_000), settings) == 30.0
    assert cost_usd(Usage(cache_read_input_tokens=1_000_000), settings) == 0.5
    est = estimate(3, settings)
    assert est.input_tokens == 3 * settings.estimate_input_tokens_per_page
    assert est.usd == cost_usd(Usage(est.input_tokens, est.output_tokens), settings)
    assert est.worst_case_usd == 3 * settings.extraction_max_budget_usd * 2


@pytest.mark.parametrize(
    "line",
    [
        "render_long_edge = 0",
        "extraction_concurrency = true",
        "unknown_key = 1",
        "price_input_per_mtok = nan",
        "extraction_max_total_usd = inf",
        "extraction_model = 3",
    ],
)
def test_bad_build_config_is_rejected(tmp_path: Path, line: str) -> None:
    config = tmp_path / "hoctap.toml"
    config.write_text(f"[build]\n{line}\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(config, env={})


def test_environment_overrides_build_config(tmp_path: Path) -> None:
    config = tmp_path / "hoctap.toml"
    config.write_text('[build]\nextraction_model = "from-file"\n', encoding="utf-8")
    assert load_settings(config, env={}).extraction_model == "from-file"
    env = {"HOCTAP_EXTRACTION_MODEL": "from-env", "HOCTAP_EXTRACTION_MAX_TOTAL_USD": "2.5"}
    settings = load_settings(config, env=env)
    assert settings.extraction_model == "from-env"
    assert settings.extraction_max_total_usd == 2.5
    with pytest.raises(ConfigError):
        load_settings(config, env={"HOCTAP_EXTRACTION_MAX_BUDGET_USD": "nan"})


# --------------------------------------------------------------------------- the real CLI


def _request(tmp_path: Path) -> PageRequest:
    return PageRequest(
        page_ref=f"{BOOK_ID}#p005",
        prompt="PAGE (page 5 of the book): /x/p005.jpg",
        system_prompt="SYSTEM",
        schema={"type": "object"},
        model="claude-opus-5",
        add_dir=tmp_path,
        max_budget_usd=1.5,
        timeout_seconds=60,
    )


class StubPopen:
    """Stands in for `subprocess.Popen`: records the call and replays one output."""

    calls: list[tuple[list[str], dict[str, Any]]] = []

    def __init__(
        self, argv: list[str], output: str = "", returncode: int = 0, hang: bool = False, **kw: Any
    ) -> None:
        self.argv, self.kwargs = argv, kw
        self._stdout, self.returncode, self._hang = output, returncode, hang
        self.killed = self.terminated = False
        StubPopen.calls.append((argv, kw))

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self._hang and not self.killed:
            raise subprocess.TimeoutExpired(self.argv, timeout or 0)
        return self._stdout, ""

    def kill(self) -> None:
        self.killed = True

    def terminate(self) -> None:
        self.terminated = True


def stub(stdout: str, returncode: int = 0, hang: bool = False):
    def popen(argv: list[str], **kw: Any) -> StubPopen:
        return StubPopen(argv, stdout, returncode, hang, **kw)

    return popen


SUCCESS = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "structured_output": PAGE_DATA[6],
    "result": json.dumps(PAGE_DATA[6]),
    "total_cost_usd": 0.088,
    "usage": {
        "input_tokens": 1200,
        "output_tokens": 800,
        "cache_creation_input_tokens": 300,
        "cache_read_input_tokens": 9000,
    },
}


def test_cli_client_argv_and_success(tmp_path: Path) -> None:
    StubPopen.calls = []
    client = ClaudeCliClient("claude", popen=stub(json.dumps(SUCCESS)))
    result = client.extract(_request(tmp_path))
    [(argv, kwargs)] = StubPopen.calls
    assert argv == cli_argv("claude", _request(tmp_path))
    assert argv == [
        "claude",
        "-p",
        "PAGE (page 5 of the book): /x/p005.jpg",
        "--output-format",
        "json",
        "--json-schema",
        '{"type":"object"}',
        "--system-prompt",
        "SYSTEM",
        "--tools",
        "Read",
        "--add-dir",
        str(tmp_path),
        "--restricted",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--model",
        "claude-opus-5",
        "--max-budget-usd",
        "1.50",
    ]
    # Each call runs in its own empty temp directory, not the repo.
    assert Path(kwargs["cwd"]).name.startswith("hoctap-claude-")
    assert not Path(kwargs["cwd"]).exists()  # removed afterwards
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert result.ok and result.output == PAGE_DATA[6]
    assert result.cost_usd == 0.088 and not result.cost_unknown
    assert result.usage == Usage(1200, 800, 300, 9000)


def test_cli_client_reads_the_last_json_line(tmp_path: Path) -> None:
    stdout = "warning: something\n" + json.dumps(SUCCESS) + "\n"
    result = ClaudeCliClient("claude", popen=stub(stdout)).extract(_request(tmp_path))
    assert result.ok and result.output == PAGE_DATA[6]


NO_OUTPUT = {k: v for k, v in SUCCESS.items() if k != "structured_output"}


def _error(result: str, subtype: str = "error_during_execution") -> str:
    return json.dumps(SUCCESS | {"is_error": True, "subtype": subtype, "result": result})


@pytest.mark.parametrize(
    ("stdout", "returncode", "transient", "cost", "unknown"),
    [
        (_error("API Error: 529 Overloaded", "success"), 1, True, 0.088, False),
        (json.dumps(SUCCESS | {"subtype": "error_during_execution"}), 0, True, 0.088, False),
        (json.dumps(SUCCESS | {"subtype": "error_max_budget_usd"}), 0, False, 0.088, False),
        (
            json.dumps(SUCCESS | {"subtype": "error_max_structured_output_retries"}),
            0,
            False,
            0.088,
            False,
        ),
        (_error("Invalid API key · Please run /login"), 1, False, 0.088, False),
        (_error("Not logged in · Please run /login"), 1, False, 0.088, False),
        (_error("model: claude-nope not found (not_found_error)"), 1, False, 0.088, False),
        (json.dumps(SUCCESS | {"structured_output": None}), 0, False, 0.088, False),
        (json.dumps(NO_OUTPUT), 0, False, 0.088, False),
        (json.dumps(SUCCESS), 2, True, 0.088, False),
        (json.dumps(SUCCESS | {"total_cost_usd": None, "subtype": "x"}), 0, True, 0.0, True),
        ("not json {", 0, True, 0.0, True),
        ("[1, 2]", 0, True, 0.0, True),
        ("", 1, True, 0.0, True),
    ],
)
def test_cli_client_failures(
    tmp_path: Path, stdout: str, returncode: int, transient: bool, cost: float, unknown: bool
) -> None:
    result = ClaudeCliClient("claude", popen=stub(stdout, returncode)).extract(_request(tmp_path))
    assert not result.ok and result.output is None and result.error
    assert result.transient is transient
    assert result.cost_usd == cost
    assert result.cost_unknown is unknown


def test_cli_client_timeout_and_missing_executable(tmp_path: Path) -> None:
    result = ClaudeCliClient("claude", popen=stub("", hang=True)).extract(_request(tmp_path))
    assert not result.ok and result.transient and "timed out" in (result.error or "")
    assert result.cost_unknown

    def missing(argv: list[str], **kwargs: Any) -> StubPopen:
        raise FileNotFoundError(argv[0])

    result = ClaudeCliClient("claude", popen=missing).extract(_request(tmp_path))
    assert not result.ok and not result.transient


def test_cli_client_terminate_all_stops_running_children(tmp_path: Path) -> None:
    client = ClaudeCliClient("claude", popen=stub(json.dumps(SUCCESS)))
    proc = StubPopen(["claude"])
    client._running.add(proc)
    client.terminate_all()
    assert proc.terminated
    assert client.extract(_request(tmp_path)).error == "cancelled"


def test_parse_cli_output_success_matches_client() -> None:
    result = parse_cli_output(0, json.dumps(SUCCESS))
    assert result.ok and result.output == PAGE_DATA[6]
