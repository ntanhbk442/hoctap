# ruff: noqa: F401, F811  (fixtures imported from test_sessions)
"""Story 5.2: the child Concept read, the `concept` ProblemSetRef and `concept` Sessions."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from test_sessions import (  # noqa: F401
    API,
    Pub,
    _envelope,
    client,
    data_dir,
    engine,
    fast_bcrypt,
    make_doc,
    profile_id,
)

from hoctap.content.catalog.models import content_catalog_concept_guides
from hoctap.content.effective import value_hash
from hoctap.content.review.models import (
    content_review_concepts,
    content_review_guide_status,
    content_review_problem_concepts,
)
from hoctap.learning.models import progress_sessions

CONCEPT = "g1.so-sanh-so"
LIB = "/api/v1/library"
GUIDE = {
    "explanation": "Số nào có nhiều chục hơn thì lớn hơn.",
    "example": {"question": "So sánh 35 và 28", "steps": ["3 chục > 2 chục"], "answer": "35 > 28"},
}


def seed(engine: Engine, count: int, *, link: bool = True) -> list[str]:
    docs = [make_doc(f"bai-{i:02d}") for i in range(1, count + 1)]
    Pub(engine)(*docs)
    with engine.begin() as conn:
        conn.execute(
            content_review_concepts.insert().values(
                concept_id=CONCEPT, grade=1, name_vi="So sánh số", created_at="2026-09-30"
            )
        )
        if link:
            conn.execute(
                content_review_problem_concepts.insert(),
                [{"problem_id": d["problem_id"], "concept_id": CONCEPT} for d in docs],
            )
    return [d["problem_id"] for d in docs]


def add_guide(engine: Engine, *, approved: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            content_catalog_concept_guides.insert().values(
                concept_id=CONCEPT,
                body_json=json.dumps(GUIDE),
                source="book",
                input_hash="h",
                model="m",
                generated_at="2026-09-30",
            )
        )
        if approved:
            conn.execute(
                content_review_guide_status.insert().values(
                    concept_id=CONCEPT, approved_hash=value_hash(GUIDE), updated_at="2026-09-30"
                )
            )


def start(client: TestClient, profile_id: str, **extra: Any):
    return client.post(
        API,
        json={"profile_id": profile_id, "ref": {"kind": "concept", "concept_id": CONCEPT}, **extra},
    )


def answer(
    client: TestClient,
    session_id: str,
    profile_id: str,
    problem_id: str,
    value: str,
    part: str = "a",
):
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": problem_id,
        "payload": {"part_key": part, "value": [{"key": "s1", "value": value}]},
        "occurred_at": "2026-09-30T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session_id}/events", json={"profile_id": profile_id, "events": [event]}
    )
    assert resp.status_code == 201, resp.text


def test_start_concept_ten_problems_book_order(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    ids = seed(engine, 14)
    resp = start(client, profile_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "concept" and body["ref_kind"] == "concept"
    assert body["problem_ids"] == ids[:10]
    with engine.connect() as conn:
        row = conn.execute(select(progress_sessions.c.ref_key, progress_sessions.c.mode)).one()
    assert tuple(row) == (f"concept:{CONCEPT}", "concept")


def test_unsolved_first_then_book_order(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    ids = seed(engine, 14)
    first = start(client, profile_id).json()
    # bai-01 right first try, bai-02 wrong first try (then never solved)
    answer(client, first["id"], profile_id, ids[0], "5")
    answer(client, first["id"], profile_id, ids[1], "9")
    second = start(client, profile_id).json()
    assert second["problem_ids"] == ids[1:11]


def test_all_solved_still_up_to_ten_in_book_order(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    ids = seed(engine, 3)
    first = start(client, profile_id).json()
    for pid in ids:
        answer(client, first["id"], profile_id, pid, "5")
    assert start(client, profile_id).json()["problem_ids"] == ids


def test_unknown_concept_404(client: TestClient, engine: Engine, profile_id: str) -> None:
    seed(engine, 1)
    resp = client.post(
        API,
        json={"profile_id": profile_id, "ref": {"kind": "concept", "concept_id": "g1.khong-co"}},
    )
    _envelope(resp, 404, "CONCEPT_NOT_FOUND")


def test_concept_without_visible_problems_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    seed(engine, 2, link=False)
    _envelope(start(client, profile_id), 422, "EMPTY_PROBLEM_SET")


def test_mode_mismatch_422(client: TestClient, engine: Engine, profile_id: str) -> None:
    seed(engine, 2)
    _envelope(start(client, profile_id, mode="practice"), 422, "MODE_REF_MISMATCH")
    assert start(client, profile_id, mode="concept").status_code == 201


def test_concept_with_assignment_id_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    seed(engine, 2)
    _envelope(start(client, profile_id, assignment_id="x"), 422, "ASSIGNMENT_REF_MISMATCH")


def test_concept_session_awards_stars_like_practice(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    ids = seed(engine, 2)
    session = start(client, profile_id).json()
    answer(client, session["id"], profile_id, ids[0], "5")
    answer(client, session["id"], profile_id, ids[0], "3", part="b")
    with engine.connect() as conn:
        stars = conn.exec_driver_sql("SELECT COALESCE(SUM(stars), 0) FROM progress_stars").scalar()
    assert stars == 3


def test_library_concept_list_counts(client: TestClient, engine: Engine) -> None:
    seed(engine, 3)
    resp = client.get(f"{LIB}/concepts", params={"grade": 1})
    assert resp.json() == [
        {"concept_id": CONCEPT, "name_vi": "So sánh số", "grade": 1, "problem_count": 3}
    ]
    assert client.get(f"{LIB}/concepts", params={"grade": 2}).json() == []


def test_library_concept_approved_guide(client: TestClient, engine: Engine) -> None:
    seed(engine, 3)
    add_guide(engine, approved=True)
    body = client.get(f"{LIB}/concepts/{CONCEPT}").json()
    assert body["guide"] == GUIDE and body["problem_count"] == 3


def test_library_concept_unapproved_or_missing_guide_is_null(
    client: TestClient, engine: Engine
) -> None:
    seed(engine, 1)
    assert client.get(f"{LIB}/concepts/{CONCEPT}").json()["guide"] is None
    add_guide(engine, approved=False)
    body = client.get(f"{LIB}/concepts/{CONCEPT}").json()
    assert body["guide"] is None
    assert set(body) == {"concept_id", "name_vi", "grade", "problem_count", "guide"}


def test_library_unknown_concept_404(client: TestClient) -> None:
    _envelope(client.get(f"{LIB}/concepts/g1.nope"), 404, "CONCEPT_NOT_FOUND")
