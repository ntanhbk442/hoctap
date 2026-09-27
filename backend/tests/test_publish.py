"""Story 1.7: crop, Concept proposals and publish (`hoctap build publish`, pilot publish).

One test per row of the I/O matrix, plus the acceptance run, the current-hash rule and
the service-level rules. Every Claude call goes to the fake model of `test_verify`.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from alembic import command
from sqlalchemy import text
from test_extraction import (  # noqa: F401 - `env` is a fixture
    BOOK_ID,
    PAGE_DATA,
    continued_draft,
    draft,
    env,
    fixture_parts,
    page_data,
    rows,
    use,
    write_pdf,
)
from test_verify import (  # noqa: F401 - `model` is a fixture
    P5_BAI1,
    P5_BAI2,
    P6_BAI3,
    P7_BAI1,
    Model,
    model,
    run,
)

import hoctap.cli as cli
from hoctap.builder.catalogue import build_catalogue
from hoctap.builder.claude_client import CallResult, FakeClaudeClient
from hoctap.builder.stages import validate
from hoctap.builder.stages.crop import PADDING, crop_specs, cut, pixel_rect, run_crop
from hoctap.content.catalog.books import BOOKS
from hoctap.content.catalog.service import (
    LessonRow,
    ProblemInput,
    UnitRow,
    canonical_doc_json,
    content_hash,
    publish_problems,
)
from hoctap.content.review.service import proposal_key, record_concept_proposals
from hoctap.content.schema import ImageRef, ProblemDoc
from hoctap.db.engine import alembic_config, create_db_engine, run_migrations

ALL = (P5_BAI1, P5_BAI2, P6_BAI3, P7_BAI1)

# --------------------------------------------------------------------------- helpers


def problems(data: Path) -> dict[str, dict[str, Any]]:
    con = sqlite3.connect(data / "hoctap.db")
    con.row_factory = sqlite3.Row
    try:
        return {
            r["problem_id"]: dict(r)
            for r in con.execute("SELECT * FROM content_catalog_problems ORDER BY problem_id")
        }
    finally:
        con.close()


def crop_dir(data: Path, problem_id: str) -> Path:
    return data / "assets" / "crops" / BOOK_ID / problem_id


def crops(data: Path) -> dict[str, float]:
    """Every crop file (relative path) with its modification time."""
    folder = data / "assets" / "crops" / BOOK_ID
    if not folder.is_dir():
        return {}
    return {str(p.relative_to(folder)): p.stat().st_mtime_ns for p in sorted(folder.rglob("*.jpg"))}


def publish(pages: str = "5-7") -> int:
    return run("publish", pages=pages)


_generation = 0


def re_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new extraction model: the next pilot re-extracts (and re-verifies) every page."""
    global _generation
    _generation += 1
    monkeypatch.setenv("HOCTAP_EXTRACTION_MODEL", f"claude-test-{_generation}")


def invalid_draft() -> dict[str, Any]:
    bad = draft("bai9")
    bad["parts"] = []  # at least one Part is required
    return bad


def number_input(template: str, value: str) -> list[dict[str, Any]]:
    parts = fixture_parts("number_input")
    parts[0].update(template=template, answer=[{"key": "s1", "value": value}])
    return parts


# --------------------------------------------------------------------------- matrix


def test_first_publish(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """3 pages, 5 valid and 1 invalid draft: 5 Problems, their units/lessons and crops."""
    monkeypatch.setitem(PAGE_DATA, 6, page_data([draft("bai3"), draft("bai4"), invalid_draft()]))
    assert run("pilot", "--yes-spend") == 0
    out = capsys.readouterr().out
    assert "publish: 5 published (5 new" in out and "1 invalid draft(s) not published" in out
    bai4 = f"{BOOK_ID}.tuan03.tiet2.bai4"
    got = problems(env)
    assert set(got) == {*ALL, bai4}
    assert {p["verify_status"] for p in got.values()} == {"agree"}
    assert {p["needs_review"] for p in got.values()} == {0}
    assert {p["retired_at"] for p in got.values()} == {None}
    # Position: page, then draft order.
    order = sorted(got, key=lambda pid: got[pid]["position"])
    assert order == [P5_BAI1, P5_BAI2, P6_BAI3, bai4, P7_BAI1]
    assert got[P5_BAI1]["source_page_first"] == 5 and got[P7_BAI1]["source_page_first"] == 7
    stored = rows(env, f"SELECT doc_json FROM build_page_results WHERE problem_id = '{P5_BAI2}'")
    doc = json.loads(stored[0][0])
    assert got[P5_BAI2]["doc_json"] == canonical_doc_json(doc)
    assert got[P5_BAI2]["content_hash"] == content_hash(doc)

    assert rows(env, "SELECT unit_key, label, title FROM content_catalog_units") == [
        ("tuan03", "TUẦN 3", "")
    ]
    lessons = rows(
        env,
        "SELECT unit_key, lesson_key, label, is_quiz_sheet FROM content_catalog_lessons "
        "ORDER BY position",
    )
    assert lessons == [
        ("tuan03", "tiet2", "Tiết 2", 0),
        ("tuan03", "phieu", "Phiếu tự luyện cuối tuần", 1),
    ]
    for pid in (*ALL, bai4):
        assert (crop_dir(env, pid) / "_problem.jpg").is_file()
    assert sorted(p.name for p in crop_dir(env, P5_BAI1).iterdir()) == [
        "_problem.jpg",
        "_problem_p5.jpg",
        "_problem_p6.jpg",
        "con-vat.jpg",
    ]


def test_acceptance_second_run_changes_nothing(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Re-publish unchanged: 0 rows changed, 0 crops re-cut (pilot and `build publish`)."""
    _, client = model
    assert run("pilot", "--yes-spend") == 0
    before, files = problems(env), crops(env)
    assert set(before) == set(ALL) and files
    proposals = rows(env, "SELECT * FROM content_review_concept_proposals")
    links = rows(env, "SELECT * FROM content_review_problem_proposals ORDER BY problem_id")
    n = len(client.calls)
    capsys.readouterr()
    assert run("pilot") == 0
    out = capsys.readouterr().out
    assert "crop: 0 cut" in out and "(0 new, 0 updated, 0 restored, 4 unchanged), 0 retired" in out
    assert publish() == 0
    assert "crop: 0 cut" in capsys.readouterr().out
    assert len(client.calls) == n
    assert problems(env) == before  # updated_at included
    assert crops(env) == files  # not re-cut
    assert rows(env, "SELECT * FROM content_review_concept_proposals") == proposals
    assert rows(env, "SELECT * FROM content_review_problem_proposals ORDER BY problem_id") == links


def test_content_changed_updates_only_that_row(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run("pilot", "--yes-spend") == 0
    before = problems(env)
    changed = draft("bai2", parts=number_input("3 + 4 = [[s1]]", "7"))
    monkeypatch.setitem(PAGE_DATA, 5, page_data([continued_draft(), changed], "TUẦN 3", "Tiết 2"))
    re_extract(monkeypatch)
    assert run("pilot", "--yes-spend") == 0
    after = problems(env)
    assert after[P5_BAI2]["content_hash"] != before[P5_BAI2]["content_hash"]
    assert '"value":"7"' in after[P5_BAI2]["doc_json"]
    assert after[P5_BAI2]["updated_at"] > before[P5_BAI2]["updated_at"]
    assert after[P5_BAI2]["created_at"] == before[P5_BAI2]["created_at"]
    for pid in (P5_BAI1, P6_BAI3, P7_BAI1):
        assert after[pid] == before[pid]


def test_problem_vanishes_then_returns(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("pilot", "--yes-spend") == 0
    before = problems(env)
    monkeypatch.setitem(PAGE_DATA, 6, page_data([]))
    re_extract(monkeypatch)
    capsys.readouterr()
    assert run("pilot", "--yes-spend") == 0
    assert f"retired (vanished from their lesson): {P6_BAI3}" in capsys.readouterr().out
    mid = problems(env)
    assert set(mid) == set(ALL)  # nothing deleted
    assert mid[P6_BAI3]["retired_at"] is not None
    assert mid[P6_BAI3]["doc_json"] == before[P6_BAI3]["doc_json"]
    for pid in (P5_BAI1, P5_BAI2, P7_BAI1):
        assert mid[pid]["retired_at"] is None
    # The retired Problem loses its proposal links; the count follows.
    assert rows(
        env, f"SELECT COUNT(*) FROM content_review_problem_proposals WHERE problem_id = '{P6_BAI3}'"
    ) == [(0,)]
    assert rows(env, "SELECT problem_count FROM content_review_concept_proposals") == [(3,)]

    # Returns: bai3 appears again (same content): retired_at is cleared.
    monkeypatch.setitem(PAGE_DATA, 6, page_data([draft("bai3")]))
    re_extract(monkeypatch)
    capsys.readouterr()
    assert run("pilot", "--yes-spend") == 0
    assert f"restored: {P6_BAI3}" in capsys.readouterr().out
    after = problems(env)
    assert after[P6_BAI3]["retired_at"] is None
    assert after[P6_BAI3]["content_hash"] == before[P6_BAI3]["content_hash"]


def test_untouched_lesson_keeps_its_state(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run("pilot", "--yes-spend") == 0
    # bai2 vanishes from page 5 (lesson tiet2); only page 7 (lesson phieu) is published.
    monkeypatch.setitem(PAGE_DATA, 5, page_data([continued_draft()], "TUẦN 3", "Tiết 2"))
    re_extract(monkeypatch)
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    before = problems(env)
    assert publish("7-7") == 0
    assert problems(env) == before  # tiet2 untouched: bai2 keeps its state
    assert publish("5-5") == 0
    assert problems(env)[P5_BAI2]["retired_at"] is not None


def test_needs_review_is_published_flagged(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    m, _ = model

    def wrong(second: dict[str, Any]) -> dict[str, Any]:
        second["parts"][1]["answer"] = [{"key": "s1", "value": "4"}]
        return second

    m.edits[P6_BAI3] = wrong  # the verify model disagrees on part b
    assert run("pilot", "--yes-spend") == 0
    assert "1 need review" in capsys.readouterr().out
    got = problems(env)
    assert set(got) == set(ALL)
    assert (got[P6_BAI3]["needs_review"], got[P6_BAI3]["verify_status"]) == (1, "disagree")
    assert (got[P5_BAI2]["needs_review"], got[P5_BAI2]["verify_status"]) == (0, "agree")


def test_multi_page_problem_gets_a_crop_per_page(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
) -> None:
    assert run("pilot", "--yes-spend") == 0
    folder = crop_dir(env, P5_BAI1)
    p5 = pymupdf.Pixmap(str(folder / "_problem_p5.jpg"))
    p6 = pymupdf.Pixmap(str(folder / "_problem_p6.jpg"))
    first = pymupdf.Pixmap(str(folder / "_problem.jpg"))
    page = pymupdf.Pixmap(str(env / "assets" / "pages" / BOOK_ID / "p005.jpg"))
    assert (first.width, first.height) == (p5.width, p5.height)
    # p5 bbox [0.05, 0.5, 0.95, 0.95], p6 bbox [0.05, 0.05, 0.95, 0.3], both padded 2%.
    assert p5.height > p6.height
    assert first.width == pixel_rect([0.05, 0.5, 0.95, 0.95], page.width, page.height).width
    # The image on the next page is cut from page 6.
    assert (folder / "con-vat.jpg").is_file()
    assert rows(
        env,
        "SELECT COUNT(*) FROM build_jobs WHERE stage = 'crop' "
        f"AND page_ref = '{BOOK_ID}#p006/{P5_BAI1}/con-vat'",
    ) == [(1,)]


def test_bbox_at_page_edge_is_clamped() -> None:
    page = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 300), False)
    page.clear_with(255)
    rect = pixel_rect([0.5, 0.9, 1.0, 1.0], 200, 300)
    assert (rect.x0, rect.y0, rect.x1, rect.y1) == (
        int((0.5 - PADDING) * 200),
        int((0.9 - PADDING) * 300),
        200,
        300,
    )
    assert tuple(pixel_rect([0.0, 0.0, 1.0, 1.0], 200, 300)) == (0, 0, 200, 300)
    jpeg = pymupdf.Pixmap(cut(page, [0.5, 0.9, 1.0, 1.0]))
    assert (jpeg.width, jpeg.height) == (rect.width, rect.height)
    # A sliver still gives at least one pixel.
    assert pixel_rect([0.999, 0.999, 1.0, 1.0], 10, 10).width >= 1


def test_bbox_at_page_edge_in_the_pipeline(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edge = draft("bai3")
    edge["bbox"] = [0.0, 0.6, 1.0, 1.0]
    monkeypatch.setitem(PAGE_DATA, 6, page_data([edge]))
    assert run("pilot", "--yes-spend") == 0
    page = pymupdf.Pixmap(str(env / "assets" / "pages" / BOOK_ID / "p006.jpg"))
    crop = pymupdf.Pixmap(str(crop_dir(env, P6_BAI3) / "_problem.jpg"))
    assert crop.width == page.width
    assert crop.height == page.height - int((0.6 - PADDING) * page.height)


def test_missing_page_image_fails_only_its_problems(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    assert problems(env) == {}
    (env / "assets" / "pages" / BOOK_ID / "p006.jpg").unlink()
    capsys.readouterr()
    assert publish() == 1
    captured = capsys.readouterr()
    assert "2 bài không xuất bản được / problem(s) not published" in captured.err
    assert f"{P5_BAI1}: thiếu ảnh trang / page image missing: " in captured.err
    assert f"assets/pages/{BOOK_ID}/p006.jpg" in captured.err
    assert set(problems(env)) == {P5_BAI2, P7_BAI1}
    assert not crop_dir(env, P6_BAI3).exists()


def test_proposals_share_one_key(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b = draft("bai3"), draft("bai4")
    a["concept_proposals"] = ["So sánh số"]
    b["concept_proposals"] = ["so sánh  số", "Phép cộng trong phạm vi 10"]
    monkeypatch.setitem(PAGE_DATA, 6, page_data([a, b]))
    assert run("pilot", "--yes-spend") == 0
    got = rows(
        env,
        "SELECT proposal_key, grade, text, problem_count, status "
        "FROM content_review_concept_proposals ORDER BY proposal_key",
    )
    assert got == [
        ("phép cộng trong phạm vi 10", 1, "Phép cộng trong phạm vi 10", 4, "proposed"),
        ("so sánh số", 1, "So sánh số", 2, "proposed"),
    ]
    bai4 = f"{BOOK_ID}.tuan03.tiet2.bai4"
    assert rows(
        env,
        "SELECT problem_id FROM content_review_problem_proposals "
        "WHERE proposal_key = 'so sánh số' ORDER BY problem_id",
    ) == [(P6_BAI3,), (bai4,)]

    # Links are replaced on each publish; counts follow; the proposal row stays.
    b2 = copy.deepcopy(b)
    b2["concept_proposals"] = ["Phép cộng trong phạm vi 10"]
    monkeypatch.setitem(PAGE_DATA, 6, page_data([a, b2]))
    re_extract(monkeypatch)
    first_seen = rows(env, "SELECT first_seen FROM content_review_concept_proposals")
    assert run("pilot", "--yes-spend") == 0
    assert rows(
        env,
        "SELECT proposal_key, problem_count FROM content_review_concept_proposals "
        "ORDER BY proposal_key",
    ) == [("phép cộng trong phạm vi 10", 4), ("so sánh số", 1)]
    assert rows(env, "SELECT first_seen FROM content_review_concept_proposals") == first_seen


def test_quiz_lesson(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
) -> None:
    assert run("pilot", "--yes-spend") == 0
    assert rows(
        env, "SELECT lesson_key, is_quiz_sheet FROM content_catalog_lessons ORDER BY lesson_key"
    ) == [("phieu", 1), ("tiet2", 0)]
    assert problems(env)[P7_BAI1]["lesson_key"] == "phieu"


# --------------------------------------------------------------------------- more


def test_duplicates_are_published_flagged(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(PAGE_DATA, 6, page_data([draft("bai3"), draft("bai3")]))
    assert run("pilot", "--yes-spend") == 0
    got = problems(env)
    assert got[P6_BAI3]["duplicate"] == 0
    assert got[f"{P6_BAI3}-2"]["duplicate"] == 1


def test_stale_rows_are_not_published(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A new extraction model makes every extraction (and so every row) stale until the
    pilot runs again: `build publish` publishes nothing and says why."""
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    re_extract(monkeypatch)
    capsys.readouterr()
    assert publish() == 1
    captured = capsys.readouterr()
    assert (
        "stale pages (not published; run `hoctap build pilot` for them first): 5, 6, 7"
        in captured.out
    )
    assert "every requested page is stale" in captured.err
    assert problems(env) == {}


def test_failed_re_extraction_retires_nothing(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page 6 loses its rows when its re-extraction fails: bai3 is unknown, not vanished."""
    m, _ = model
    assert run("pilot", "--yes-spend") == 0
    refusal = CallResult(ok=False, error="no structured_output (refusal)")

    def responder(request):  # noqa: ANN001, ANN202
        if request.stage == "extract" and request.page_ref.endswith("#p006"):
            return refusal
        return m(request)

    use(monkeypatch, FakeClaudeClient(responder))
    re_extract(monkeypatch)
    assert run("pilot", "--yes-spend") == 0
    assert rows(env, "SELECT DISTINCT page FROM build_page_results ORDER BY page") == [(5,), (7,)]
    assert {pid: p["retired_at"] for pid, p in problems(env).items()} == dict.fromkeys(ALL)


def test_publish_unknown_book_and_bad_range(
    env: Path,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("publish", pages="5-7") == 1  # nothing extracted yet: all pages stale
    assert "stale pages" in capsys.readouterr().out
    assert run("publish", pages="0-3") == 2
    assert run("publish", pages="7-5") == 2
    assert cli.main(["build", "publish", "--book", "nope", "--pages", "1-2"]) == 2


def test_no_publish_flag(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
) -> None:
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    assert problems(env) == {} and crops(env) == {}


def test_proposal_key() -> None:
    assert proposal_key("  So sánh  số ") == proposal_key("so sánh số") == "so sánh số"
    decomposed = "So sánh số"  # NFD
    assert proposal_key(decomposed) == "so sánh số"
    assert proposal_key("   ") == ""


def _engine_with_book(tmp_path: Path):  # noqa: ANN202
    source = tmp_path / "src"
    write_pdf(source / BOOKS[0].source_path, 3)
    engine = create_db_engine(tmp_path / "s.db")
    run_migrations(engine)
    build_catalogue(engine, source, books=(BOOKS[0],))
    return engine


def _doc(label: str, lesson: str = "tiet1", page: int = 1) -> dict[str, Any]:
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "problemdocs" / "number_input.json").read_text(
            encoding="utf-8"
        )
    )
    raw.update(
        problem_id=f"{BOOK_ID}.tuan01.{lesson}.{label}",
        unit_key="tuan01",
        lesson_key=lesson,
        problem_label=label,
        source_pages=[{"page": page, "bbox": [0.1, 0.1, 0.9, 0.5]}],
        concept_ids=[],
    )
    return raw


def _input(doc: dict[str, Any]) -> ProblemInput:
    return ProblemInput(doc, doc["source_pages"][0]["page"] * 1000, False, "agree", False)


def test_service_upsert_retire_and_idempotence(tmp_path: Path) -> None:
    engine = _engine_with_book(tmp_path)
    units = [UnitRow(BOOK_ID, "tuan01", "TUẦN 1", "", 100)]
    lessons = [
        LessonRow(BOOK_ID, "tuan01", "tiet1", "Tiết 1", "", 101),
        LessonRow(BOOK_ID, "tuan01", "phieu", "Phiếu", "", 102),
    ]
    a, b, q = _doc("bai1"), _doc("bai2"), _doc("bai1", "phieu", 2)
    try:
        with engine.begin() as conn:
            r = publish_problems(
                conn, BOOK_ID, units=units, lessons=lessons, problems=[_input(d) for d in (a, b, q)]
            )
            assert len(r.inserted) == 3 and r.units_written == ["tuan01"]
        with engine.begin() as conn:
            r = publish_problems(
                conn, BOOK_ID, units=units, lessons=lessons, problems=[_input(d) for d in (a, b, q)]
            )
            assert r.changed == 0 and r.units_written == [] and r.lessons_written == []
        with engine.begin() as conn:
            # b vanished from tiet1; phieu is not touched.
            r = publish_problems(conn, BOOK_ID, units=units, lessons=lessons, problems=[_input(a)])
            assert r.retired == [b["problem_id"]]
            # b stays retired; a Problem outside the known-current pages is never retired.
            r = publish_problems(
                conn,
                BOOK_ID,
                units=[],
                lessons=[],
                problems=[],
                touch_pages=[2],
                current_pages=[1],
            )
            assert r.retired == []
            r = publish_problems(
                conn, BOOK_ID, units=[], lessons=[], problems=[], touch_pages=[2], present=[]
            )
            assert r.retired == [q["problem_id"]]
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM content_catalog_problems")).scalar() == 3
            with pytest.raises(ValueError):
                publish_problems(
                    conn,
                    "toan2-2020-q1",
                    units=[],
                    lessons=[],
                    problems=[_input(a)],
                )
    finally:
        engine.dispose()


def test_service_proposals_idempotent(tmp_path: Path) -> None:
    engine = _engine_with_book(tmp_path)
    try:
        with engine.begin() as conn:
            r = record_concept_proposals(conn, 1, {"p1": ["So sánh số"], "p2": ["so sánh  số"]})
            assert r.new_keys == ["so sánh số"] and r.counts == {"so sánh số": 2}
            r = record_concept_proposals(conn, 1, {"p1": ["So sánh số"], "p2": ["so sánh  số"]})
            assert r.new_keys == [] and r.counts == {"so sánh số": 2}
            # Another Grade is a separate proposal.
            r = record_concept_proposals(conn, 2, {"p9": ["So sánh số"]})
            assert r.new_keys == ["so sánh số"]
            r = record_concept_proposals(conn, 1, {"p2": []})
            assert r.counts == {"so sánh số": 1}
    finally:
        engine.dispose()


def test_migration_0006_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "m.db")
    cfg = alembic_config(engine)
    try:
        tables = {
            "content_catalog_units",
            "content_catalog_lessons",
            "content_catalog_problems",
            "content_review_concept_proposals",
            "content_review_problem_proposals",
        }
        indexes = {
            "ix_content_catalog_problems_lesson",
            "ix_content_review_problem_proposals_key",
        }

        def names(conn, kind: str) -> set[str]:  # noqa: ANN001
            sql = f"SELECT name FROM sqlite_master WHERE type = '{kind}'"
            return {r[0] for r in conn.execute(text(sql))}

        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            assert tables <= names(conn, "table") and indexes <= names(conn, "index")
            command.downgrade(cfg, "0005_verify_columns")
            assert not tables & names(conn, "table") and not indexes & names(conn, "index")
            command.upgrade(cfg, "head")
            assert tables <= names(conn, "table") and indexes <= names(conn, "index")
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- review fixes


def test_corrupt_stored_doc_fails_only_that_problem(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    con = sqlite3.connect(env / "hoctap.db")
    with con:
        con.execute(
            "UPDATE build_page_results SET doc_json = '{}' WHERE problem_id = ?", (P6_BAI3,)
        )
    con.close()
    capsys.readouterr()
    assert publish() == 1
    err = capsys.readouterr().err
    assert f"{P6_BAI3}: stored doc no longer validates" in err
    assert set(problems(env)) == {P5_BAI1, P5_BAI2, P7_BAI1}


def test_invalid_re_extracted_draft_does_not_retire(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run("pilot", "--yes-spend") == 0
    bad = draft("bai3")
    bad["parts"] = []  # invalid this time, but its id is still known
    monkeypatch.setitem(PAGE_DATA, 6, page_data([bad]))
    re_extract(monkeypatch)
    assert run("pilot", "--yes-spend") == 0
    assert rows(env, f"SELECT status FROM build_page_results WHERE problem_id = '{P6_BAI3}'") == [
        ("invalid",)
    ]
    assert problems(env)[P6_BAI3]["retired_at"] is None


def test_deleted_page_image_after_publish_retires_nothing(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("pilot", "--yes-spend") == 0
    before = problems(env)
    (env / "assets" / "pages" / BOOK_ID / "p006.jpg").unlink()
    capsys.readouterr()
    assert publish() == 1
    captured = capsys.readouterr()
    assert "stale pages" not in captured.out  # neighbours are not made stale
    assert {pid: p["retired_at"] for pid, p in problems(env).items()} == dict.fromkeys(ALL)
    assert problems(env) == before


def test_publish_transaction_failure_publishes_nothing_and_keeps_crops(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import hoctap.builder.stages.publish as publish_stage

    assert run("pilot", "--yes-spend", "--no-publish") == 0

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("proposals failed")

    with monkeypatch.context() as patch:
        patch.setattr(publish_stage, "record_concept_proposals", boom)
        assert publish() == 1
    assert "proposals failed" in capsys.readouterr().err
    assert problems(env) == {}
    assert rows(env, "SELECT COUNT(*) FROM content_catalog_units") == [(0,)]
    files = crops(env)
    assert files
    capsys.readouterr()
    assert publish() == 0
    assert "crop: 0 cut" in capsys.readouterr().out
    assert crops(env) == files
    assert set(problems(env)) == set(ALL)


def test_changed_bbox_re_cuts_and_deleted_crop_is_re_created(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run("pilot", "--yes-spend") == 0
    target = crop_dir(env, P6_BAI3) / "_problem.jpg"
    old = pymupdf.Pixmap(str(target)).height
    moved = draft("bai3")
    moved["bbox"] = [0.05, 0.1, 0.95, 0.8]
    monkeypatch.setitem(PAGE_DATA, 6, page_data([moved]))
    re_extract(monkeypatch)
    assert run("pilot", "--yes-spend") == 0
    assert pymupdf.Pixmap(str(target)).height > old

    target.unlink()
    assert publish() == 0
    assert target.is_file()


def test_stale_crop_files_are_removed(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert run("pilot", "--yes-spend") == 0
    folder = crop_dir(env, P5_BAI1)
    (folder / "leftover.jpg").write_bytes(b"x")
    assert publish() == 0
    assert sorted(p.name for p in folder.iterdir()) == [
        "_problem.jpg",
        "_problem_p5.jpg",
        "_problem_p6.jpg",
        "con-vat.jpg",
    ]


def test_unreadable_page_image_fails_only_its_problems(
    env: Path,  # noqa: F811
    model: tuple[Model, FakeClaudeClient],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PyMuPDF cannot open page 7's image (a changed file would make the page stale, so
    the open fails instead)."""
    assert run("pilot", "--yes-spend", "--no-publish") == 0
    import hoctap.builder.stages.crop as crop_stage

    original = crop_stage.load_page

    def load_page(path: Path) -> Any:
        if path.name == "p007.jpg":
            raise pymupdf.FileDataError("cannot open broken document")
        return original(path)

    capsys.readouterr()
    with monkeypatch.context() as patch:
        patch.setattr(crop_stage, "load_page", load_page)
        assert publish() == 1
    assert f"{P7_BAI1}: crop failed" in capsys.readouterr().err
    assert set(problems(env)) == {P5_BAI1, P5_BAI2, P6_BAI3}


def test_unsafe_image_keys_fail_the_problem(tmp_path: Path) -> None:
    doc = ProblemDoc.model_validate(_doc("bai1"))
    for key in ("", "_problem", "../x", "a/b", ".hidden"):
        image = ImageRef.model_construct(image_key=key, page=1, bbox=[0.1, 0.1, 0.5, 0.5])
        bad = doc.model_copy(update={"images": [image]})
        with pytest.raises(ValueError):
            crop_specs(bad)
        engine = create_db_engine(tmp_path / "c.db")
        try:
            run_migrations(engine)
            report = run_crop(engine, tmp_path, BOOK_ID, [bad])
        finally:
            engine.dispose()
        assert list(report.failed) == [doc.problem_id] and report.ok == []


def test_crop_specs_use_the_lowest_source_page() -> None:
    raw = _doc("bai1")
    raw["source_pages"] = [
        {"page": 4, "bbox": [0.1, 0.1, 0.9, 0.3]},
        {"page": 3, "bbox": [0.1, 0.5, 0.9, 0.9]},
    ]
    specs = crop_specs(ProblemDoc.model_validate(raw))
    first = next(s for s in specs if s.name == "_problem")
    assert (first.page, first.bbox) == (3, (0.1, 0.5, 0.9, 0.9))
    assert [s.name for s in specs] == ["_problem", "_problem_p3", "_problem_p4"]


def test_book_structure_takes_each_heading_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every heading event carries its own text. PageExtraction has one lesson heading
    per page, so two lesson headings on one page are fed through `_page_events`."""
    events = [
        validate._Event(0.1, "lesson", "tiet1", "Tiết 1", "Số 1"),
        validate._Event(0.5, "lesson", "tiet2", "Tiết 2", "Số 2"),
    ]
    monkeypatch.setattr(validate, "_page_events", lambda data, warnings: events)
    data = page_data([draft("bai1"), draft("bai2")])
    data["problems"][1]["bbox"] = [0.05, 0.6, 0.95, 0.9]
    structure = validate.book_structure([validate.PageInput(5, "h", data)])
    one, two = structure.lessons[("u00", "tiet1")], structure.lessons[("u00", "tiet2")]
    assert (one.label, one.title, two.label, two.title) == ("Tiết 1", "Số 1", "Tiết 2", "Số 2")
    assert structure.units["u00"].position < one.position < two.position
    assert two.position < validate.position(6, 0)


def test_heading_text_on_one_page_is_not_shared() -> None:
    data = page_data([draft("bai1")], unit="TUẦN 3", lesson="Tiết 2")
    data["unit_heading"]["title"] = "Ôn tập"
    structure = validate.book_structure([validate.PageInput(5, "h", data)])
    unit, lesson = structure.units["tuan03"], structure.lessons[("tuan03", "tiet2")]
    assert (unit.label, unit.title) == ("TUẦN 3", "Ôn tập")
    assert (lesson.label, lesson.title) == ("Tiết 2", "")


def test_positions_share_one_scale() -> None:
    assert validate.position(5, 0) == 50_000
    assert validate.position(5, 9_999) < validate.position(6, 0)
    with pytest.raises(ValueError):
        validate.position(5, validate.POSITION_SCALE)
    with pytest.raises(ValueError):
        validate.position(5, -1)


def test_missing_structure_never_overwrites(tmp_path: Path) -> None:
    engine = _engine_with_book(tmp_path)
    try:
        with engine.begin() as conn:
            publish_problems(
                conn,
                BOOK_ID,
                units=[UnitRow(BOOK_ID, "tuan01", "TUẦN 1", "", 10_001)],
                lessons=[LessonRow(BOOK_ID, "tuan01", "tiet1", "Tiết 1", "", 10_002)],
                problems=[],
            )
            r = publish_problems(
                conn,
                BOOK_ID,
                units=[
                    UnitRow(BOOK_ID, "tuan01", "", "", 0, insert_only=True),
                    UnitRow(BOOK_ID, "tuan02", "", "", 0, insert_only=True),
                ],
                lessons=[LessonRow(BOOK_ID, "tuan01", "tiet1", "", "", 0, insert_only=True)],
                problems=[],
            )
            assert r.units_written == ["tuan02"] and r.lessons_written == []
            got = conn.execute(
                text("SELECT unit_key, label, position FROM content_catalog_units ORDER BY 1")
            ).all()
            assert [tuple(g) for g in got] == [("tuan01", "TUẦN 1", 10_001), ("tuan02", "", 0)]
    finally:
        engine.dispose()
