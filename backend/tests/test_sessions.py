"""Story 2.4: Sessions (`POST /sessions`), the bundle (`GET /sessions/{id}/bundle`) and the
event API (`POST /sessions/{id}/events`). One test (or group) per row of the I/O matrix.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from hoctap.api.sessions import _is_uuid7
from hoctap.app import create_app
from hoctap.config import Settings
from hoctap.content.catalog.models import (
    content_catalog_books,
    content_catalog_lessons,
    content_catalog_problems,
    content_catalog_units,
)
from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    UnitRow,
    publish_problems,
    upsert_books,
)
from hoctap.content.review import service as review
from hoctap.learning.models import progress_events, progress_sessions
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-5", "tiet-2"
API = "/api/v1/sessions"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


def make_doc(label: str) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=f"{BOOK}.{UNIT}.{LESSON}.{label}",
        book_id=BOOK,
        unit_key=UNIT,
        lesson_key=LESSON,
        problem_label=label,
        display_label=f"Bài {label}",
        concept_ids=[],
        concept_proposals=[],
    )
    return doc


class Pub:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        with engine.begin() as conn:
            upsert_books(
                conn, [BookRow(BOOK, "2020", 1, 1, "Toán 1 – 2020", f"{BOOK}.pdf", 10, 1, "f")]
            )

    def __call__(self, *docs: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            publish_problems(
                conn,
                BOOK,
                units=[UnitRow(BOOK, UNIT, "TUẦN 5", "", 500)],
                lessons=[LessonRow(BOOK, UNIT, LESSON, "Tiết 2", "", 501)],
                problems=[
                    ProblemInput(
                        doc=d,
                        position=12000 + i,
                        needs_review=False,
                        verify_status="agree",
                        duplicate=False,
                    )
                    for i, d in enumerate(docs)
                ],
            )
            review.record_concept_proposals(conn, 1, {d["problem_id"]: [] for d in docs})


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
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def profile_id(client: TestClient) -> str:
    return client.post("/api/v1/setup", json=SETUP).json()["id"]


def _envelope(resp, status: int, code: str) -> str:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]["message"]


def _lesson_ref() -> dict[str, str]:
    return {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON}


def _start(client: TestClient, profile_id: str) -> dict[str, Any]:
    resp = client.post(API, json={"profile_id": profile_id, "ref": _lesson_ref()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _bundle(client: TestClient, session_id: str, profile_id: str, **params: Any):
    return client.get(f"{API}/{session_id}/bundle", params={"profile_id": profile_id, **params})


# --- Start ---------------------------------------------------------------------------


def test_start_lesson_leq_10_problems_one_chunk(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(*(make_doc(f"bai-{i}") for i in range(3)))
    session = _start(client, profile_id)
    assert len(session["problem_ids"]) == 3
    assert session["chunk_size"] == 10
    assert session["mode"] == "practice"

    bundle = _bundle(client, session["id"], profile_id).json()
    assert bundle["chunk"] == 1
    assert bundle["chunk_count"] == 1
    assert len(bundle["problems"]) == 3


def test_start_lesson_more_than_10_problems_two_chunks(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(*(make_doc(f"bai-{i:02d}") for i in range(14)))
    session = _start(client, profile_id)
    assert len(session["problem_ids"]) == 14

    b1 = _bundle(client, session["id"], profile_id, chunk=1).json()
    assert b1["chunk_count"] == 2
    assert len(b1["problems"]) == 10
    assert b1["chunk_label"] == "Phần 1/2"

    b2 = _bundle(client, session["id"], profile_id, chunk=2).json()
    assert len(b2["problems"]) == 4
    assert b1["problems"][0]["problem"]["problem_id"] != b2["problems"][0]["problem"]["problem_id"]


def test_start_zero_visible_problems_422_no_session_created(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)  # book exists, nothing published
    resp = client.post(API, json={"profile_id": profile_id, "ref": _lesson_ref()})
    _envelope(resp, 422, "EMPTY_PROBLEM_SET")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_sessions).where(progress_sessions.c.profile_id == profile_id)
        ).all()
    assert rows == []


def test_start_unknown_profile_404(client: TestClient, engine: Engine) -> None:
    Pub(engine)(make_doc("bai-1"))
    resp = client.post(API, json={"profile_id": "no-such-profile", "ref": _lesson_ref()})
    _envelope(resp, 404, "PROFILE_NOT_FOUND")


# --- Bundle --------------------------------------------------------------------------


def test_bundle_shape_has_view_urls_and_attempted(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    session = _start(client, profile_id)
    bundle = _bundle(client, session["id"], profile_id).json()
    p = bundle["problems"][0]
    assert "answer" not in json.dumps(p["problem"])  # AD-5: no Answer Key to the child
    assert p["crop_urls"]
    assert p["page_urls"]
    assert isinstance(p["audio"], dict) and p["audio"]
    assert p["attempted"] is False


def test_bundle_chunk_out_of_range_422(client: TestClient, engine: Engine, profile_id: str) -> None:
    Pub(engine)(make_doc("bai-1"))
    session = _start(client, profile_id)
    resp = _bundle(client, session["id"], profile_id, chunk=3)
    _envelope(resp, 422, "CHUNK_OUT_OF_RANGE")


def test_bundle_after_hide_still_shows_frozen_problem(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """AD-9: a Problem hidden after the Session started must still render for it."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    with engine.begin() as conn:
        review.set_hidden(conn, doc["problem_id"], True)

    bundle = _bundle(client, session["id"], profile_id).json()
    assert len(bundle["problems"]) == 1
    assert bundle["problems"][0]["problem"]["problem_id"] == doc["problem_id"]


def test_bundle_unknown_session_404(client: TestClient, profile_id: str) -> None:
    resp = _bundle(client, "no-such-session", profile_id)
    _envelope(resp, 404, "SESSION_NOT_FOUND")


def test_bundle_wrong_profile_for_session_403(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Story 2.4 review follow-up (#10): the bundle endpoint now has the same
    `profile_id`/ownership check `POST /events` already had -- a `session_id` alone
    (e.g. guessed or observed) must not be enough to read another child's bundle."""
    Pub(engine)(make_doc("bai-1"))
    session = _start(client, profile_id)
    resp = _bundle(client, session["id"], "some-other-profile-id")
    _envelope(resp, 403, "FORBIDDEN")


def test_bundle_attempted_true_after_attempt_event(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    assert resp.status_code == 201, resp.text

    bundle = _bundle(client, session["id"], profile_id).json()
    assert bundle["problems"][0]["attempted"] is True


# --- Events ----------------------------------------------------------------------------


def test_event_first_post_stored_once(client: TestClient, engine: Engine, profile_id: str) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1


def test_event_resent_is_idempotent_no_duplicate(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    body = {"profile_id": profile_id, "events": [event]}
    first = client.post(f"{API}/{session['id']}/events", json=body)
    second = client.post(f"{API}/{session['id']}/events", json=body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1


def test_event_wrong_profile_for_session_403(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    # Any id that isn't this Session's own `profile_id` reproduces "wrong owner" -- Story
    # 2.4 has no need for a 2nd real Profile to prove the ownership check.
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events",
        json={"profile_id": str(uuid.uuid7()), "events": [event]},
    )
    _envelope(resp, 403, "FORBIDDEN")


def test_event_unknown_session_id_404(client: TestClient, profile_id: str) -> None:
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": None,
        "payload": {},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/no-such-session/events", json={"profile_id": profile_id, "events": [event]}
    )
    _envelope(resp, 404, "SESSION_NOT_FOUND")


def test_event_invalid_kind_422(client: TestClient, engine: Engine, profile_id: str) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "not_a_real_kind",
        "problem_id": None,
        "payload": {},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    _envelope(resp, 422, "INVALID_EVENT_KIND")


def test_event_invalid_id_not_uuid7_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid4()),  # a UUIDv4, not v7
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    _envelope(resp, 422, "INVALID_EVENT_ID")


def test_session_started_event_written_on_start(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    Pub(engine)(make_doc("bai-1"))
    session = _start(client, profile_id)
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(
                progress_events.c.session_id == session["id"],
                progress_events.c.kind == "session_started",
            )
        ).all()
    assert len(rows) == 1


# --- Batch semantics (review follow-up) -----------------------------------------------


def test_event_batch_two_distinct_events_both_stored(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A batch of 2+ distinct, valid events is stored in one call -- the actual
    batch-looping behaviour (every prior test posted a single-element list)."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    events = [
        {
            "id": str(uuid.uuid7()),
            "kind": "hint_requested",
            "problem_id": doc["problem_id"],
            "payload": {"part_key": "a"},
            "occurred_at": "2026-09-28T10:00:00+00:00",
        },
        {
            "id": str(uuid.uuid7()),
            "kind": "attempt",
            "problem_id": doc["problem_id"],
            "payload": {"part_key": "a", "value": "5"},
            "occurred_at": "2026-09-28T10:00:01+00:00",
        },
    ]
    resp = client.post(
        f"{API}/{session['id']}/events", json={"profile_id": profile_id, "events": events}
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert [e["id"] for e in out] == [e["id"] for e in events]
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id.in_([e["id"] for e in events]))
        ).all()
    assert len(rows) == 2


def test_event_batch_same_id_twice_within_batch_is_idempotent(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """The same event id appearing twice WITHIN one batch hits the idempotent-return path
    for its second occurrence, not a crash."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events",
        json={"profile_id": profile_id, "events": [event, dict(event)]},
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert len(out) == 2
    assert out[0] == out[1]
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1


def test_event_no_partial_insert_when_a_later_event_in_the_batch_is_invalid(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A batch is fully attempted or rejected outright: a bad event anywhere in the batch
    must not leave an earlier, individually-valid sibling event inserted."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    good_event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    bad_event = {
        "id": str(uuid.uuid7()),
        "kind": "not_a_real_kind",
        "problem_id": None,
        "payload": {},
        "occurred_at": "2026-09-28T10:00:01+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events",
        json={"profile_id": profile_id, "events": [good_event, bad_event]},
    )
    _envelope(resp, 422, "INVALID_EVENT_KIND")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == good_event["id"])
        ).all()
    assert rows == []  # the earlier, individually-valid event was NOT silently kept


def test_event_problem_id_must_belong_to_the_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """An `attempt` (or any Problem-scoped) event whose `problem_id` isn't in the Session's
    own frozen list is rejected -- otherwise a client could pollute an unrelated Lesson's
    `attempted` numerator via any Session it owns, and `progress_events` is append-only."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    foreign_event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": "some-other-book.some-unit.some-lesson.bai-9",
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    resp = client.post(
        f"{API}/{session['id']}/events",
        json={"profile_id": profile_id, "events": [foreign_event]},
    )
    _envelope(resp, 422, "PROBLEM_NOT_IN_SESSION")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == foreign_event["id"])
        ).all()
    assert rows == []


def test_event_concurrent_same_id_exactly_one_row_both_same_result(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Two real threads racing `POST .../events` with the SAME event id: exactly one row
    ends up in `progress_events`, and both callers get the same (idempotent) result --
    proving the "even concurrently" claim, not just a sequential resend."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a", "value": "5"},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    body = {"profile_id": profile_id, "events": [event]}

    def post() -> Any:
        return client.post(f"{API}/{session['id']}/events", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [f.result() for f in [pool.submit(post), pool.submit(post)]]

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json() == second.json()
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1


def test_event_id_collision_across_sessions_is_rejected_not_returned_as_success(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """#9 (review follow-up): the idempotent IntegrityError re-fetch must not hand back
    a DIFFERENT Session's event as if it were the caller's own. Two distinct Sessions,
    the SAME (colliding) event id posted to each -- the first stores it; the second, on
    a different `session_id`, must be rejected outright (409), never silently return the
    first Session's event content."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session_a = _start(client, profile_id)
    session_b = _start(client, profile_id)
    assert session_a["id"] != session_b["id"]

    colliding_id = str(uuid.uuid7())
    event = {
        "id": colliding_id,
        "kind": "session_completed",  # problem_id-less kind: valid for either Session
        "problem_id": None,
        "payload": {},
        "occurred_at": "2026-09-28T10:00:00+00:00",
    }
    first = client.post(
        f"{API}/{session_a['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{API}/{session_b['id']}/events", json={"profile_id": profile_id, "events": [event]}
    )
    _envelope(second, 409, "EVENT_ID_COLLISION")

    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == colliding_id)
        ).all()
    assert len(rows) == 1
    assert rows[0].session_id == session_a["id"]


# --- Chunking boundary -----------------------------------------------------------------


def test_chunk_boundary_exact_multiple_of_chunk_size(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Exactly 20 Problems (2x the chunk size): 2 full chunks of 10, not 3 with a trailing
    empty one."""
    Pub(engine)(*(make_doc(f"bai-{i:02d}") for i in range(20)))
    session = _start(client, profile_id)
    assert len(session["problem_ids"]) == 20

    b1 = _bundle(client, session["id"], profile_id, chunk=1).json()
    assert b1["chunk_count"] == 2
    assert len(b1["problems"]) == 10
    # #15 (review follow-up): every entry of a FULL 10-Problem chunk carries the complete
    # bundle shape -- not just the first, as narrower shape/length tests elsewhere checked.
    for p in b1["problems"]:
        assert "answer" not in json.dumps(p["problem"])
        assert p["crop_urls"]
        assert p["page_urls"]
        assert isinstance(p["audio"], dict) and p["audio"]
        assert p["attempted"] is False

    b2 = _bundle(client, session["id"], profile_id, chunk=2).json()
    assert len(b2["problems"]) == 10

    resp = _bundle(client, session["id"], profile_id, chunk=3)
    _envelope(resp, 422, "CHUNK_OUT_OF_RANGE")


@pytest.mark.parametrize("chunk", [0, -1])
def test_bundle_chunk_zero_or_negative_422_validation_error(
    client: TestClient, engine: Engine, profile_id: str, chunk: int
) -> None:
    """#13 (review follow-up): `chunk < 1` never reaches `learning.sessions.get_bundle()`
    at all -- the router's own `Query(ge=1)` rejects it first, as a generic 422
    `VALIDATION_ERROR` (not the service's `CHUNK_OUT_OF_RANGE`/former dead `INVALID_CHUNK`
    branch, which was removed since it was unreachable through the API)."""
    Pub(engine)(make_doc("bai-1"))
    session = _start(client, profile_id)
    resp = _bundle(client, session["id"], profile_id, chunk=chunk)
    _envelope(resp, 422, "VALIDATION_ERROR")


# --- Hard-deleted Problem in a frozen list ----------------------------------------------


def test_bundle_skips_a_hard_deleted_problem_without_crashing(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A Problem that vanished entirely (hard-deleted from `content_catalog_problems`, not
    merely retired/hidden) after the Session froze its list: the bundle silently omits it
    rather than 500ing (AD-9 freezes the id list, not the row's existence)."""
    doc1 = make_doc("bai-1")
    doc2 = make_doc("bai-2")
    Pub(engine)(doc1, doc2)
    session = _start(client, profile_id)
    with engine.begin() as conn:
        conn.execute(
            content_catalog_problems.delete().where(
                content_catalog_problems.c.problem_id == doc1["problem_id"]
            )
        )

    bundle = _bundle(client, session["id"], profile_id).json()
    assert len(bundle["problems"]) == 1
    assert bundle["problems"][0]["problem"]["problem_id"] == doc2["problem_id"]


def test_bundle_degrades_gracefully_after_whole_unit_and_book_deleted(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """#16 (review follow-up): not just a single Problem vanishing, but its whole parent
    Unit AND Book rows disappearing entirely after the Session froze its list -- the
    bundle must still degrade gracefully (empty `problems`, no 500), the same
    `ProblemNotFound`-skip path #6/the test above already covers for one Problem."""
    doc1 = make_doc("bai-1")
    doc2 = make_doc("bai-2")
    Pub(engine)(doc1, doc2)
    session = _start(client, profile_id)
    with engine.begin() as conn:
        conn.execute(
            content_catalog_problems.delete().where(content_catalog_problems.c.book_id == BOOK)
        )
        conn.execute(
            content_catalog_lessons.delete().where(content_catalog_lessons.c.book_id == BOOK)
        )
        conn.execute(content_catalog_units.delete().where(content_catalog_units.c.book_id == BOOK))
        conn.execute(content_catalog_books.delete().where(content_catalog_books.c.book_id == BOOK))

    resp = _bundle(client, session["id"], profile_id)
    assert resp.status_code == 200, resp.text
    bundle = resp.json()
    assert bundle["problems"] == []
    assert bundle["chunk_count"] == 1  # still derived from the frozen (2-item) id list


# --- _is_uuid7() -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", False),
        ("not-a-uuid-at-all", False),
        (str(uuid.uuid4()), False),  # valid UUID, wrong version
        (str(uuid.uuid7()), True),
        (str(uuid.uuid7()).upper(), True),  # uuid.UUID normalises case
    ],
)
def test_is_uuid7(value: str, expected: bool) -> None:
    assert _is_uuid7(value) is expected
