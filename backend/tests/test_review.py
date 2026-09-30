"""Story 1.8: Content Review with overrides.

One test per row of the I/O matrix, the acceptance run, and the service-level rules
(merge order, Part replacement, link rebuild on re-publish, guards).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from hoctap.api.errors import AppError
from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    UnitRow,
    publish_problems,
    upsert_books,
)
from hoctap.content.effective import effective_problem, value_hash, visible_to_child
from hoctap.content.review import service as review
from hoctap.db.engine import alembic_config, create_db_engine
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-5", "tiet-2"
API = "/api/v1/parent/review"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


def pid(label: str) -> str:
    return f"{BOOK}.{UNIT}.{LESSON}.{label}"


def make_doc(label: str, proposals: list[str] | None = None) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=pid(label),
        problem_label=label,
        display_label=f"Bài {label.removeprefix('bai-')}",
        concept_ids=[],
        concept_proposals=proposals or [],
    )
    return doc


class Pub:
    """Publishes Problems the way the builder does (catalog upsert + proposals)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        with engine.begin() as conn:
            upsert_books(
                conn,
                [BookRow(BOOK, "2020", 1, 1, "Toán 1 – Quyển 1 (2020)", "x.pdf", 10, 1, "f")],
            )

    def __call__(
        self,
        *docs: dict[str, Any],
        needs_review: set[str] = frozenset(),
        duplicate: set[str] = frozenset(),
    ) -> None:  # noqa: E501
        with self.engine.begin() as conn:
            result = publish_problems(
                conn,
                BOOK,
                units=[UnitRow(BOOK, UNIT, "TUẦN 5", "", 500)],
                lessons=[LessonRow(BOOK, UNIT, LESSON, "Tiết 2", "", 501)],
                problems=[
                    ProblemInput(
                        doc=d,
                        position=12000 + i,
                        needs_review=d["problem_id"] in needs_review,
                        verify_status="disagree" if d["problem_id"] in needs_review else "agree",
                        duplicate=d["problem_id"] in duplicate,
                    )
                    for i, d in enumerate(docs)
                ],
            )
            proposals: dict[str, list[str]] = dict.fromkeys(result.retired, [])
            proposals |= {d["problem_id"]: d["concept_proposals"] for d in docs}
            review.record_concept_proposals(conn, 1, proposals)


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parent_service, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path, tmp_path: Path):
    app = create_app(Settings(data_dir=data_dir, frontend_dist=tmp_path / "no-dist"))
    with TestClient(app) as c:
        assert c.post("/api/v1/setup", json=SETUP).status_code == 201
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def pub(engine: Engine) -> Pub:
    return Pub(engine)


def detail(client: TestClient, problem_id: str) -> dict[str, Any]:
    resp = client.get(f"{API}/problems/{problem_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def put(client: TestClient, problem_id: str, *edits: dict[str, Any]):
    return client.put(f"{API}/problems/{problem_id}/overrides", json={"edits": list(edits)})


def answer_edit(value: str, part: str = "a") -> dict[str, Any]:
    return {"part_key": part, "field": "answer", "value": [{"key": "s1", "value": value}]}


def approve(client: TestClient, problem_id: str):
    """Duyệt with the hash the parent is looking at."""
    shown = detail(client, problem_id)["content_hash"]
    return client.post(f"{API}/problems/{problem_id}/approve", json={"content_hash": shown})


def visible_ids(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return [v.problem_id for v in visible_to_child(conn)]


def queue_ids(client: TestClient) -> list[str]:
    resp = client.get(f"{API}/queue")
    assert resp.status_code == 200, resp.text
    return [p["problem_id"] for p in resp.json()]


def overrides_rows(data_dir: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(data_dir / "hoctap.db")
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT * FROM content_review_overrides")]
    finally:
        con.close()


# --------------------------------------------------------------------------- matrix


def test_edit_answer(client: TestClient, engine: Engine, pub: Pub, data_dir: Path) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"), needs_review={p})
    assert visible_ids(engine) == []
    resp = put(client, p, answer_edit("6"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [row] = overrides_rows(data_dir)
    assert (row["part_key"], row["field"]) == ("a", "answer")
    assert row["base_hash"] == value_hash([{"key": "s1", "value": "5"}])
    assert body["effective"]["parts"][0]["answer"] == [{"key": "s1", "value": "6"}]
    assert body["extracted"]["parts"][0]["answer"] == [{"key": "s1", "value": "5"}]
    assert body["overrides"][0]["conflict"] is None
    with engine.connect() as conn:
        eff = effective_problem(conn, p)
    assert eff.doc.parts[0].answer[0].value == "6" and eff.conflicts == []
    assert visible_ids(engine) == []  # needs_review: visible only after approval
    assert approve(client, p).status_code == 200
    assert visible_ids(engine) == [p]


def test_invalid_edit(client: TestClient, pub: Pub, data_dir: Path) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    resp = put(client, p, {"part_key": "a", "field": "answer", "value": []})
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "INVALID_OVERRIDE"
    assert error["message"].startswith("Bản sửa không hợp lệ")
    assert any("Phần a" in d and "thiếu" in d for d in error["details"]), error
    assert overrides_rows(data_dir) == []
    # A valid edit in the same request does not rescue it: nothing is stored.
    resp = put(
        client,
        p,
        {"field": "instruction", "value": "Tính nhẩm:"},
        {"part_key": "a", "field": "hint", "value": " "},
    )
    assert resp.status_code == 422
    assert overrides_rows(data_dir) == []


def test_edit_equal_to_extracted_removes_override(
    client: TestClient, pub: Pub, data_dir: Path
) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    assert put(client, p, answer_edit("6")).status_code == 200
    assert len(overrides_rows(data_dir)) == 1
    body = put(client, p, answer_edit("5")).json()
    assert overrides_rows(data_dir) == [] and body["overrides"] == []


def test_reextract_same_field_unchanged(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    put(client, p, answer_edit("6"))
    changed = make_doc("bai-1")
    changed["parts"][0]["hint"] = "Con đếm tiếp nhé."  # another field changed
    pub(changed)
    body = detail(client, p)
    assert body["conflicts"] == []
    assert body["effective"]["parts"][0]["answer"][0]["value"] == "6"
    assert body["effective"]["parts"][0]["hint"] == "Con đếm tiếp nhé."
    assert visible_ids(engine) == [p]


def test_reextract_field_changed_conflict(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    put(client, p, answer_edit("6"))
    changed = make_doc("bai-1")
    changed["parts"][0]["answer"] = [{"key": "s1", "value": "7"}]
    pub(changed)
    body = detail(client, p)
    assert [c["reason"] for c in body["conflicts"]] == ["base_changed"]
    assert body["overrides"][0]["conflict"] == "base_changed"
    assert body["effective"]["parts"][0]["answer"][0]["value"] == "6"  # override still wins
    assert body["summary"]["conflict"] is True
    assert p in queue_ids(client)
    assert visible_ids(engine) == []
    # Duyệt accepts the edit over the new base: no conflict, visible again.
    approve(client, p)
    assert detail(client, p)["conflicts"] == []
    assert visible_ids(engine) == [p]


def test_part_removed_by_reextract(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    put(client, p, answer_edit("4", part="b"))
    fewer = make_doc("bai-1")
    fewer["parts"] = fewer["parts"][:1]
    pub(fewer)
    body = detail(client, p)
    assert body["conflicts"] == [
        {
            "override_id": body["overrides"][0]["id"],
            "part_key": "b",
            "field": "answer",
            "reason": "part_missing",
        }  # noqa: E501
    ]
    assert [x["part_key"] for x in body["effective"]["parts"]] == ["a"]  # skipped
    assert p in queue_ids(client) and visible_ids(engine) == []
    # Approving cannot clear a missing Part; reverting ("Bỏ sửa") does.
    approve(client, p)
    assert visible_ids(engine) == []
    resp = client.delete(f"{API}/problems/{p}/overrides/{body['overrides'][0]['id']}")
    assert resp.status_code == 200 and resp.json()["conflicts"] == []
    assert visible_ids(engine) == [p]


def test_approve(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"), needs_review={p})
    assert p in queue_ids(client)
    body = approve(client, p).json()
    assert body["status"]["approved_hash"] == body["content_hash"]
    assert body["status"]["approved"] is True and body["summary"]["awaiting_approval"] is False
    assert visible_ids(engine) == [p]
    assert p not in queue_ids(client)


def test_edit_after_approve_needs_approval_again(
    client: TestClient, engine: Engine, pub: Pub
) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"), needs_review={p})
    approve(client, p)
    assert visible_ids(engine) == [p]
    body = put(client, p, answer_edit("6")).json()
    assert body["content_hash"] != body["status"]["approved_hash"]
    assert body["summary"]["awaiting_approval"] is True
    assert visible_ids(engine) == [] and p in queue_ids(client)


def test_hide(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    assert visible_ids(engine) == [p]
    body = client.post(f"{API}/problems/{p}/hide").json()
    assert body["summary"]["hidden"] is True and body["status"]["visible"] is False
    assert visible_ids(engine) == []
    items = client.get(f"{API}/problems").json()["items"]
    assert items[0]["hidden"] is True
    client.post(f"{API}/problems/{p}/unhide")
    assert visible_ids(engine) == [p]


def test_open_parent_report(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    with engine.begin() as conn:
        report_id = review.add_error_report(conn, p, "parent", "Sai đáp án")
    assert visible_ids(engine) == []
    assert p in queue_ids(client)
    body = detail(client, p)
    assert body["summary"]["report"] is True
    assert body["reports"][0]["status"] == "open"
    resp = client.post(f"{API}/reports/{report_id}/resolve")
    assert resp.status_code == 200 and resp.json()["status"] == "resolved"
    assert resp.json()["resolved_at"]
    assert visible_ids(engine) == [p]
    assert p not in queue_ids(client)


def test_child_report(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    with engine.begin() as conn:
        review.add_error_report(conn, p, "child")
    assert p in queue_ids(client)
    assert visible_ids(engine) == [p]


def test_accept_proposal(client: TestClient, engine: Engine, pub: Pub) -> None:
    labels = ("bai-1", "bai-2", "bai-3")
    pub(*(make_doc(label, ["So sánh số"]) for label in labels))
    concepts = client.get(f"{API}/concepts").json()
    [prop] = concepts["proposals"]
    assert (prop["text"], prop["problem_count"], prop["status"]) == ("So sánh số", 3, "proposed")
    resp = client.post(
        f"{API}/concepts/accept", json={"grade": 1, "proposal_key": prop["proposal_key"]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["concepts"] == [
        {
            "concept_id": "g1.so-sanh-so",
            "grade": 1,
            "name_vi": "So sánh số",
            "problem_count": 3,
            "has_guide": False,
            "guide_source": None,
            "guide_conflict": False,
            "guide_approved": False,
        }
    ]
    assert body["proposals"][0]["status"] == "accepted"
    assert body["proposals"][0]["target_concept_id"] == "g1.so-sanh-so"
    for label in labels:
        assert detail(client, pid(label))["effective"]["concept_ids"] == ["g1.so-sanh-so"]
    # Accepting twice is refused.
    again = client.post(
        f"{API}/concepts/accept", json={"grade": 1, "proposal_key": prop["proposal_key"]}
    )
    assert again.status_code == 409


def test_accept_slug_collision(client: TestClient, pub: Pub) -> None:
    pub(make_doc("bai-1", ["So sánh số"]), make_doc("bai-2", ["So sánh số!"]))
    keys = [p["proposal_key"] for p in client.get(f"{API}/concepts").json()["proposals"]]
    for key in keys:
        assert (
            client.post(
                f"{API}/concepts/accept", json={"grade": 1, "proposal_key": key}
            ).status_code
            == 200
        )  # noqa: E501
    ids = sorted(c["concept_id"] for c in client.get(f"{API}/concepts").json()["concepts"])
    assert ids == ["g1.so-sanh-so", "g1.so-sanh-so-2"]


def test_merge(client: TestClient, pub: Pub) -> None:
    pub(make_doc("bai-1", ["So sánh số"]), make_doc("bai-2", ["So sánh các số"]))
    props = {
        p["text"]: p["proposal_key"] for p in client.get(f"{API}/concepts").json()["proposals"]
    }
    client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": props["So sánh số"]})
    resp = client.post(
        f"{API}/concepts/merge",
        json={"grade": 1, "proposal_key": props["So sánh các số"], "concept_id": "g1.so-sanh-so"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    merged = next(p for p in body["proposals"] if p["text"] == "So sánh các số")
    assert (merged["status"], merged["target_concept_id"]) == ("merged", "g1.so-sanh-so")
    assert body["concepts"][0]["problem_count"] == 2
    assert detail(client, pid("bai-2"))["effective"]["concept_ids"] == ["g1.so-sanh-so"]


def test_rename(client: TestClient, pub: Pub) -> None:
    pub(make_doc("bai-1", ["So sánh số"]))
    key = client.get(f"{API}/concepts").json()["proposals"][0]["proposal_key"]
    client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": key})
    resp = client.post(
        f"{API}/concepts/rename", json={"concept_id": "g1.so-sanh-so", "name_vi": "So sánh các số"}
    )
    assert resp.status_code == 200
    assert resp.json()["concepts"][0] == {
        "concept_id": "g1.so-sanh-so",
        "grade": 1,
        "name_vi": "So sánh các số",
        "problem_count": 1,
        "has_guide": False,
        "guide_source": None,
        "guide_conflict": False,
        "guide_approved": False,
    }
    assert detail(client, pid("bai-1"))["effective"]["concept_ids"] == ["g1.so-sanh-so"]


def test_pages_need_parent_cookie(client: TestClient, data_dir: Path) -> None:
    page = data_dir / "assets" / "pages" / BOOK / "p012.jpg"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"\xff\xd8page")
    assert client.get(f"/assets-data/pages/{BOOK}/p012.jpg").status_code == 200
    client.cookies.clear()
    resp = client.get(f"/assets-data/pages/{BOOK}/p012.jpg")
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_crops_public(client: TestClient, data_dir: Path) -> None:
    crop = data_dir / "assets" / "crops" / BOOK / pid("bai-1") / "_problem.jpg"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(b"\xff\xd8crop")
    client.cookies.clear()
    resp = client.get(f"/assets-data/crops/{BOOK}/{pid('bai-1')}/_problem.jpg")
    assert resp.status_code == 200 and resp.content == b"\xff\xd8crop"
    assert client.get(f"/assets-data/crops/{BOOK}/missing.jpg").status_code == 404
    assert client.get("/assets-data/crops/..%2F..%2Fhoctap.db").status_code == 404


# --------------------------------------------------------------------------- acceptance


def test_acceptance_edit_approve_survives_republish(
    client: TestClient, engine: Engine, pub: Pub
) -> None:
    p1, p2 = pid("bai-1"), pid("bai-2")
    docs = (make_doc("bai-1"), make_doc("bai-2"))
    pub(*docs, needs_review={p1})
    queue = client.get(f"{API}/queue").json()
    assert [q["problem_id"] for q in queue] == [p1] and queue[0]["awaiting_approval"] is True
    assert put(client, p1, answer_edit("6")).status_code == 200
    assert approve(client, p1).status_code == 200
    assert visible_ids(engine) == [p1, p2]
    with engine.connect() as conn:
        [view] = visible_to_child(conn, [p1])
    assert "answer" not in view.model_dump()["parts"][0]
    pub(*docs, needs_review={p1})  # a re-publish of the same extraction
    body = detail(client, p1)
    assert body["effective"]["parts"][0]["answer"][0]["value"] == "6"
    assert body["status"]["approved"] is True and body["conflicts"] == []
    assert visible_ids(engine) == [p1, p2]


# --------------------------------------------------------------------------- rules


def test_part_replacement_changes_type(client: TestClient, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    compare = json.loads((FIXTURES / "compare.json").read_text(encoding="utf-8"))["parts"][0]
    compare["part_key"] = "b"
    resp = put(client, p, {"part_key": "b", "field": "part", "value": compare})
    assert resp.status_code == 200, resp.text
    assert resp.json()["effective"]["parts"][1]["type"] == "compare"
    # The field overrides apply after the Part replacement.
    hint = {"part_key": "b", "field": "hint", "value": "So sánh từng cặp số."}
    body = put(client, p, hint).json()
    assert body["effective"]["parts"][1]["type"] == "compare"
    assert body["effective"]["parts"][1]["hint"] == "So sánh từng cặp số."
    # A replacement with another part_key is refused.
    bad = dict(compare, part_key="c")
    assert put(client, p, {"part_key": "b", "field": "part", "value": bad}).status_code == 422


def test_field_rules(client: TestClient, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    assert (
        put(client, p, {"field": "hint", "value": "x"}).json()["error"]["code"] == "INVALID_FIELD"
    )
    assert (
        put(client, p, {"part_key": "z", "field": "hint", "value": "x"}).json()["error"]["code"]
        == "PART_NOT_FOUND"
    )  # noqa: E501
    body = put(client, p, {"field": "instruction", "value": "Tính nhẩm:"}).json()
    assert body["effective"]["instruction"] == "Tính nhẩm:"
    assert body["overrides"][0]["part_key"] is None
    assert client.get(f"{API}/problems/nope").status_code == 404


def test_republish_rebuilds_concept_links(client: TestClient, pub: Pub) -> None:
    pub(make_doc("bai-1", ["So sánh số"]))
    key = client.get(f"{API}/concepts").json()["proposals"][0]["proposal_key"]
    client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": key})
    pub(make_doc("bai-1", ["So sánh số"]))  # unchanged proposals: links kept
    assert detail(client, pid("bai-1"))["effective"]["concept_ids"] == ["g1.so-sanh-so"]
    pub(make_doc("bai-1", ["Đếm số"]))  # changed: rebuilt from accepted/merged proposals
    assert detail(client, pid("bai-1"))["effective"]["concept_ids"] == []
    pub(make_doc("bai-1", ["So sánh số", "Đếm số"]))
    assert detail(client, pid("bai-1"))["effective"]["concept_ids"] == ["g1.so-sanh-so"]


def test_duplicate_in_queue_and_list_pagination(client: TestClient, pub: Pub) -> None:
    docs = [make_doc(f"bai-{i}") for i in range(1, 56)]
    pub(*docs, duplicate={pid("bai-3")})
    assert queue_ids(client) == [pid("bai-3")]
    first = client.get(f"{API}/problems", params={"book_id": BOOK}).json()
    assert (first["total"], len(first["items"]), first["page_size"]) == (55, 50, 50)
    second = client.get(f"{API}/problems", params={"book_id": BOOK, "page": 2}).json()
    assert len(second["items"]) == 5
    assert client.get(f"{API}/problems", params={"book_id": "other"}).json()["total"] == 0
    books = client.get(f"{API}/books").json()
    assert books == [
        {
            "book_id": BOOK,
            "title_vi": "Toán 1 – Quyển 1 (2020)",
            "problem_count": 55,
            "units": [
                {
                    "unit_key": UNIT,
                    "label": "TUẦN 5",
                    "lessons": [{"lesson_key": LESSON, "label": "Tiết 2"}],
                }
            ],
        }
    ]


def test_detail_urls(client: TestClient, pub: Pub) -> None:
    pub(make_doc("bai-1"))
    body = detail(client, pid("bai-1"))
    assert body["crop_urls"] == [f"/assets-data/crops/{BOOK}/{pid('bai-1')}/_problem.jpg"]
    assert body["page_urls"] == [f"/assets-data/pages/{BOOK}/p012.jpg"]


def test_review_routes_need_parent(client: TestClient) -> None:
    client.cookies.clear()
    for method, path in [
        ("GET", "/queue"),
        ("GET", "/problems"),
        ("GET", "/concepts"),
        ("POST", "/concepts/accept"),
    ]:
        assert client.request(method, API + path).status_code == 401


def test_publish_keeps_review_rows(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    put(client, p, answer_edit("6"))
    client.post(f"{API}/problems/{p}/hide")
    pub(make_doc("bai-9"))  # the Lesson re-published without bai-1: it is retired
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM content_review_overrides")).scalar_one()
        hidden = conn.execute(text("SELECT hidden FROM content_review_status")).scalar_one()
    assert (count, hidden) == (1, 1)
    assert visible_ids(engine) == [pid("bai-9")]


def test_migration_0007_up_and_down(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "m.db")
    cfg = alembic_config(engine)
    tables = {
        "content_review_overrides",
        "content_review_status",
        "content_review_error_reports",
        "content_review_concepts",
        "content_review_problem_concepts",
    }

    def names(conn) -> set[str]:  # noqa: ANN001
        return {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }  # noqa: E501

    def cols(conn) -> set[str]:  # noqa: ANN001
        sql = "PRAGMA table_info(content_review_concept_proposals)"
        return {r[1] for r in conn.execute(text(sql))}

    try:
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            assert tables <= names(conn) and "target_concept_id" in cols(conn)
            command.downgrade(cfg, "0006_catalog_problems")
            assert not tables & names(conn) and "target_concept_id" not in cols(conn)
            command.upgrade(cfg, "head")
            assert tables <= names(conn)
    finally:
        engine.dispose()


def test_slugify() -> None:
    assert review.slugify("So sánh số") == "so-sanh-so"
    assert review.slugify("Đếm đến 10") == "dem-den-10"
    assert review.slugify("!!!") == "khai-niem"
    assert review.slugify("a" * 80) == "a" * 48


# --------------------------------------------------------------------------- review fixes


def err(resp) -> str:  # noqa: ANN001
    return resp.json()["error"]["code"]


def test_retired_problem_absent_everywhere(client: TestClient, engine: Engine, pub: Pub) -> None:
    p1, p2 = pid("bai-1"), pid("bai-2")
    pub(make_doc("bai-1"), make_doc("bai-2"), needs_review={p1, p2})
    pub(make_doc("bai-2"), needs_review={p2})  # bai-1 vanished: retired, not hidden
    assert queue_ids(client) == [p2]
    assert client.get(f"{API}/problems").json()["total"] == 1
    assert client.get(f"{API}/books").json()[0]["problem_count"] == 1
    approve(client, p2)
    assert visible_ids(engine) == [p2]
    assert detail(client, p1)["status"]["retired"] is True


def test_approval_survives_concept_curation(client: TestClient, engine: Engine, pub: Pub) -> None:
    p1, p2 = pid("bai-1"), pid("bai-2")
    pub(make_doc("bai-1", ["So sánh số"]), make_doc("bai-2", ["Số bé hơn"]), needs_review={p1, p2})
    approve(client, p1)
    approve(client, p2)
    props = {
        x["text"]: x["proposal_key"] for x in client.get(f"{API}/concepts").json()["proposals"]
    }
    client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": props["So sánh số"]})
    client.post(
        f"{API}/concepts/merge",
        json={"grade": 1, "proposal_key": props["Số bé hơn"], "concept_id": "g1.so-sanh-so"},
    )
    for p in (p1, p2):
        body = detail(client, p)
        assert body["effective"]["concept_ids"] == ["g1.so-sanh-so"]
        assert body["status"]["approved"] is True
    assert visible_ids(engine) == [p1, p2]


def _reslot(doc: dict[str, Any]) -> dict[str, Any]:
    """Part a re-extracted with another slot key: an answer override for s1 no longer fits."""
    part = doc["parts"][0]
    part.update(template="3 + 2 = [[s2]]", slots=[{"slot_key": "s2"}])
    part["answer"] = [{"key": "s2", "value": "5"}]
    return doc


def test_republish_makes_override_invalid(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    put(client, p, answer_edit("6"), {"field": "instruction", "value": "Tính nhẩm:"})
    pub(_reslot(make_doc("bai-1")))
    resp = client.get(f"{API}/queue")
    assert resp.status_code == 200
    [item] = resp.json()
    assert item["problem_id"] == p and item["conflict"] is True
    body = detail(client, p)
    assert body["effective"] is None and body["content_hash"] is None
    assert any("Phần a" in m for m in body["effective_error"])
    resp = client.post(f"{API}/problems/{p}/approve", json={"content_hash": "x"})
    assert resp.status_code == 409 and err(resp) == "INVALID_EFFECTIVE"
    assert visible_ids(engine) == []
    # While invalid, any single revert is allowed, even one that leaves it invalid.
    instruction = next(o for o in body["overrides"] if o["field"] == "instruction")
    resp = client.delete(f"{API}/problems/{p}/overrides/{instruction['id']}")
    assert resp.status_code == 200 and resp.json()["effective"] is None
    # "Bỏ tất cả sửa đổi" goes back to the extracted doc.
    resp = client.delete(f"{API}/problems/{p}/overrides")
    assert resp.status_code == 200
    assert resp.json()["overrides"] == [] and resp.json()["effective"] is not None
    assert visible_ids(engine) == [p]


def test_delete_override_refused_only_when_it_breaks_a_valid_doc(
    client: TestClient, pub: Pub
) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    compare = json.loads((FIXTURES / "compare.json").read_text(encoding="utf-8"))["parts"][0]
    compare["part_key"] = "b"
    put(client, p, {"part_key": "b", "field": "part", "value": compare})
    answer = [{"key": "r1", "value": ">"}, {"key": "r2", "value": ">"}, {"key": "r3", "value": "="}]
    body = put(client, p, {"part_key": "b", "field": "answer", "value": answer}).json()
    ids = {o["field"]: o["id"] for o in body["overrides"]}
    # Without the Part replacement, the compare answer no longer fits a number_input Part.
    resp = client.delete(f"{API}/problems/{p}/overrides/{ids['part']}")
    assert resp.status_code == 422 and err(resp) == "INVALID_OVERRIDE"
    assert client.delete(f"{API}/problems/{p}/overrides/nope").status_code == 404
    assert client.delete(f"{API}/problems/{p}/overrides/{ids['answer']}").status_code == 200
    assert client.delete(f"{API}/problems/{p}/overrides/{ids['part']}").status_code == 200


def test_error_codes(client: TestClient, engine: Engine, pub: Pub) -> None:
    pub(make_doc("bai-1", ["So sánh số"]))
    with engine.begin() as conn:
        review.record_concept_proposals(conn, 2, {"toan2-x": ["Phép nhân"]})
    props = client.get(f"{API}/concepts").json()["proposals"]
    key1 = next(x["proposal_key"] for x in props if x["grade"] == 1)
    key2 = next(x["proposal_key"] for x in props if x["grade"] == 2)
    client.post(f"{API}/concepts/accept", json={"grade": 2, "proposal_key": key2})
    merge = {"grade": 1, "proposal_key": key1, "concept_id": "g2.phep-nhan"}
    assert err(client.post(f"{API}/concepts/merge", json=merge)) == "GRADE_MISMATCH"
    merge["concept_id"] = "g1.nope"
    assert err(client.post(f"{API}/concepts/merge", json=merge)) == "CONCEPT_NOT_FOUND"
    accept = {"grade": 1, "proposal_key": "nope"}
    assert err(client.post(f"{API}/concepts/accept", json=accept)) == "PROPOSAL_NOT_FOUND"
    rename = {"concept_id": "g1.nope", "name_vi": "X"}
    assert err(client.post(f"{API}/concepts/rename", json=rename)) == "CONCEPT_NOT_FOUND"
    blank = {"concept_id": "g2.phep-nhan", "name_vi": "   "}
    resp = client.post(f"{API}/concepts/rename", json=blank)
    assert resp.status_code == 422 and err(resp) == "INVALID_NAME"
    resp = client.post(f"{API}/reports/nope/resolve")
    assert resp.status_code == 404 and err(resp) == "REPORT_NOT_FOUND"


def test_approve_stale(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"), needs_review={p})
    shown = detail(client, p)["content_hash"]
    put(client, p, answer_edit("6"))  # changed elsewhere after it was shown
    resp = client.post(f"{API}/problems/{p}/approve", json={"content_hash": shown})
    assert resp.status_code == 409 and err(resp) == "STALE"
    assert "thay đổi" in resp.json()["error"]["message"]
    assert visible_ids(engine) == []


def test_mutating_routes_need_parent(client: TestClient, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    client.cookies.clear()
    routes = [
        ("PUT", f"/problems/{p}/overrides"),
        ("DELETE", f"/problems/{p}/overrides"),
        ("DELETE", f"/problems/{p}/overrides/x"),
        ("POST", f"/problems/{p}/approve"),
        ("POST", f"/problems/{p}/hide"),
        ("POST", f"/problems/{p}/unhide"),
        ("POST", "/reports/x/resolve"),
        ("POST", "/concepts/accept"),
        ("POST", "/concepts/merge"),
        ("POST", "/concepts/rename"),
        ("GET", f"/problems/{p}"),
        ("GET", "/books"),
    ]
    for method, path in routes:
        resp = client.request(method, API + path)
        assert resp.status_code == 401, (method, path)


def test_duplicate_leaves_queue_once_approved_or_hidden(client: TestClient, pub: Pub) -> None:
    p1, p2 = pid("bai-1"), pid("bai-2")
    pub(make_doc("bai-1"), make_doc("bai-2"), duplicate={p1, p2})
    assert queue_ids(client) == [p1, p2]
    approve(client, p1)
    client.post(f"{API}/problems/{p2}/hide")
    assert queue_ids(client) == []
    put(client, p1, answer_edit("6"))  # approval no longer current: queued again
    assert queue_ids(client) == [p1]


def test_concept_id_suffix_fits_and_blank_name(
    client: TestClient, engine: Engine, pub: Pub
) -> None:  # noqa: E501
    long = "Số " + "rất " * 20 + "dài"
    pub(make_doc("bai-1", [long]), make_doc("bai-2", [long + "!"]))
    for x in client.get(f"{API}/concepts").json()["proposals"]:
        resp = client.post(
            f"{API}/concepts/accept", json={"grade": 1, "proposal_key": x["proposal_key"]}
        )  # noqa: E501
        assert resp.status_code == 200, resp.text
    ids = sorted(c["concept_id"] for c in client.get(f"{API}/concepts").json()["concepts"])
    assert len(ids) == 2 and any(i.endswith("-2") for i in ids)
    assert all(len(i.split(".", 1)[1]) <= 48 for i in ids)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO content_review_concept_proposals "
                "(proposal_key, grade, text, problem_count, first_seen, status) "
                "VALUES ('blank', 1, '   ', 0, 'x', 'proposed')"
            )
        )
    resp = client.post(f"{API}/concepts/accept", json={"grade": 1, "proposal_key": "blank"})
    assert resp.status_code == 422 and err(resp) == "INVALID_NAME"


def test_retired_problem_actions(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    shown = detail(client, p)["content_hash"]
    pub(make_doc("bai-9"))  # the Lesson re-published without bai-1: retired
    assert detail(client, p)["status"]["retired"] is True
    resp = client.post(f"{API}/problems/{p}/approve", json={"content_hash": shown})
    assert resp.status_code == 409 and err(resp) == "PROBLEM_RETIRED"
    resp = client.post(f"{API}/problems/{p}/hide")
    assert resp.status_code == 409 and err(resp) == "PROBLEM_RETIRED"
    with engine.begin() as conn, pytest.raises(AppError) as exc:
        review.add_error_report(conn, pid("nope"), "parent")
    assert exc.value.status_code == 404


# --------------------------------------------------------------------- Story 4.4 reports


def test_parent_report_route_hides_dedupes_and_resolves(
    client: TestClient, engine: Engine, pub: Pub
) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    resp = client.post(f"{API}/problems/{p}/reports", json={"note": "  Sai đáp án  "})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["kind"], body["status"], body["note"]) == ("parent", "open", "Sai đáp án")
    assert visible_ids(engine) == []
    assert p in queue_ids(client)
    again = client.post(f"{API}/problems/{p}/reports", json={})
    assert again.json()["id"] == body["id"]
    assert len(detail(client, p)["reports"]) == 1
    client.post(f"{API}/reports/{body['id']}/resolve")
    assert visible_ids(engine) == [p]


def test_parent_report_errors(client: TestClient, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    resp = client.post(f"{API}/problems/{pid('nope')}/reports", json={})
    assert resp.status_code == 404 and err(resp) == "PROBLEM_NOT_FOUND"
    resp = client.post(f"{API}/problems/{p}/reports", json={"note": "x" * 501})
    assert resp.status_code == 422
    client.cookies.clear()
    assert client.post(f"{API}/problems/{p}/reports", json={}).status_code == 401


def test_child_flag_route_no_pin(client: TestClient, engine: Engine, pub: Pub) -> None:
    p = pid("bai-1")
    pub(make_doc("bai-1"))
    profile_id = client.get("/api/v1/profiles").json()[0]["id"]
    client.cookies.clear()  # no PIN cookie
    url = f"/api/v1/problems/{p}/flag"
    assert client.post(url, json={"profile_id": "nope"}).status_code == 404
    resp = client.post(url, json={"profile_id": "nope"})
    assert resp.json()["error"]["code"] == "PROFILE_NOT_FOUND"
    assert (
        client.post(f"/api/v1/problems/{pid('nope')}/flag", json={"profile_id": profile_id}).json()[
            "error"
        ]["code"]
        == "PROBLEM_NOT_FOUND"
    )
    assert client.post(url, json={"profile_id": profile_id}).status_code == 200
    assert client.post(url, json={"profile_id": profile_id}).status_code == 200  # twice
    assert visible_ids(engine) == [p]  # stays visible
    with engine.connect() as conn:
        (r,) = review.list_reports(conn, p)
    assert (r.kind, r.note, r.status) == ("child", "", "open")
