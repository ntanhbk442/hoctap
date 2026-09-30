# ruff: noqa: F401, F811  (fixtures imported from test_sessions)
"""Story 7.1: the parent-only worksheet endpoint, one test per I/O row."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_concept_practice import CONCEPT, answer, seed, start
from test_sessions import (  # noqa: F401
    BOOK,
    LESSON,
    UNIT,
    Pub,
    _envelope,
    client,
    data_dir,
    engine,
    fast_bcrypt,
    make_doc,
    profile_id,
)

from hoctap.content.review import service as review
from hoctap.ids import utc_now

URL = "/api/v1/parent/worksheet"
LESSON_Q = {"book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON}


def get_ids(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [p["problem_id"] for p in resp.json()["problems"]]


def test_lesson_worksheet_in_book_order_with_answer_keys(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    pub = Pub(engine)
    docs = [make_doc(f"bai-{i:02d}") for i in range(1, 13)]
    pub(*docs)
    resp = client.get(URL, params=LESSON_Q)
    assert get_ids(resp) == [d["problem_id"] for d in docs]
    body = resp.json()
    assert body["kind"] == "lesson" and body["title"] and body["subtitle"]
    assert body["problems"][0]["doc"]["parts"][0]["answer"] == [{"key": "s1", "value": "5"}]


def test_hidden_and_reported_problems_are_omitted(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    docs = [make_doc(f"bai-{i}") for i in range(1, 4)]
    Pub(engine)(*docs)
    with engine.begin() as conn:
        review.set_hidden(conn, docs[0]["problem_id"], True, utc_now())
        review.add_error_report(conn, docs[1]["problem_id"], "parent", "sai", utc_now())
    assert get_ids(client.get(URL, params=LESSON_Q)) == [docs[2]["problem_id"]]


def test_unapproved_needs_review_problem_is_omitted(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    from hoctap.content.catalog.models import content_catalog_problems

    docs = [make_doc("bai-1"), make_doc("bai-2")]
    Pub(engine)(*docs)
    with engine.begin() as conn:
        conn.execute(
            content_catalog_problems.update()
            .where(content_catalog_problems.c.problem_id == docs[0]["problem_id"])
            .values(needs_review=1)
        )
    assert get_ids(client.get(URL, params=LESSON_Q)) == [docs[1]["problem_id"]]


def test_empty_lesson_is_an_empty_list(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)
    assert get_ids(client.get(URL, params=LESSON_Q)) == []


def test_concept_worksheet_is_the_child_practice_set(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    ids = seed(engine, 14)
    first = start(client, profile_id).json()
    answer(client, first["id"], profile_id, ids[0], "5")  # solved first try
    answer(client, first["id"], profile_id, ids[1], "9")  # wrong
    second = start(client, profile_id).json()
    resp = client.get(URL, params={"concept_id": CONCEPT, "profile_id": profile_id})
    assert get_ids(resp) == second["problem_ids"] == ids[1:11]
    assert resp.json()["kind"] == "concept" and resp.json()["title"] == "So sánh số"


def test_concept_errors(client: TestClient, engine: Engine, profile_id: str) -> None:
    seed(engine, 2)
    _envelope(
        client.get(URL, params={"concept_id": CONCEPT, "profile_id": "nope"}),
        404,
        "PROFILE_NOT_FOUND",
    )
    _envelope(
        client.get(URL, params={"concept_id": "g1.khong-co", "profile_id": profile_id}),
        404,
        "CONCEPT_NOT_FOUND",
    )
    _envelope(client.get(URL, params={"concept_id": CONCEPT}), 422, "WORKSHEET_REF_INVALID")
    _envelope(client.get(URL), 422, "WORKSHEET_REF_INVALID")
    _envelope(
        client.get(URL, params={"book_id": BOOK, "concept_id": CONCEPT, "profile_id": profile_id}),
        422,
        "WORKSHEET_REF_INVALID",
    )


def test_crop_urls_only_for_existing_files(
    client: TestClient, engine: Engine, data_dir: Path, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    page = doc["source_pages"][0]["page"]
    doc["images"] = [{"image_key": "img1", "page": page, "bbox": [0, 0, 1, 1]}]
    Pub(engine)(doc, make_doc("bai-2"))
    pid = doc["problem_id"]
    folder = data_dir / "assets" / "crops" / BOOK / pid
    folder.mkdir(parents=True)
    (folder / "_problem.jpg").write_bytes(b"\xff\xd8")
    problems = client.get(URL, params=LESSON_Q).json()["problems"]
    assert problems[0]["crop_url"] == f"/assets-data/crops/{BOOK}/{pid}/_problem.jpg"
    assert problems[0]["image_urls"] == {}
    assert problems[1]["crop_url"] is None


def test_no_cookie_returns_no_content(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)(make_doc("bai-1"))
    client.cookies.clear()
    for params in (LESSON_Q, {"concept_id": CONCEPT, "profile_id": profile_id}):
        resp = client.get(URL, params=params)
        _envelope(resp, 401, "UNAUTHORIZED")
        assert "bai-1" not in resp.text


def test_child_routes_never_carry_the_answer_key(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    client.cookies.clear()
    resp = client.get("/api/v1/library/books")
    assert '"answer"' not in resp.text and '"solution"' not in resp.text
