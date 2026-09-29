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
from hoctap.learning.models import progress_events, progress_retry_items, progress_sessions
from hoctap.parent import service as parent_service
from hoctap.parent.models import parent_profiles

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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
            "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
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


# --- Grading and staged help (Story 2.5) ----------------------------------------------


def make_multi_slot_doc(label: str) -> dict[str, Any]:
    """A single Part with two numeric slots, for multi-slot wrong-key tests."""
    doc = make_doc(label)
    doc["parts"] = [
        {
            "part_key": "a",
            "type": "number_input",
            "prompt": "",
            "image_keys": [],
            "template": "3 + 2 = [[s1]], 4 + 3 = [[s2]]",
            "slots": [{"slot_key": "s1"}, {"slot_key": "s2"}],
            "answer": [{"key": "s1", "value": "5"}, {"key": "s2", "value": "7"}],
            "hint": "Con đếm thêm từng số nhé.",
            "solution": {"steps": ["5, rồi 7."], "final": "5 và 7"},
        }
    ]
    return doc


def _attempt(problem_id: str, part_key: str, value: Any, occurred_at: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": problem_id,
        "payload": {"part_key": part_key, "value": value},
        "occurred_at": occurred_at,
    }


def _post(client: TestClient, session_id: str, profile_id: str, *events: dict[str, Any]):
    return client.post(
        f"{API}/{session_id}/events", json={"profile_id": profile_id, "events": list(events)}
    )


def test_grade_correct_single_slot_no_hint_no_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
    )
    resp = _post(client, session["id"], profile_id, event)
    assert resp.status_code == 201, resp.text
    out = resp.json()[0]
    assert out["correct"] is True
    assert out["wrong_keys"] == []
    assert out["hint"] is None
    assert out["solution"] is None
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert rows == []


def test_grade_wrong_multi_slot_returns_exactly_the_wrong_key(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_multi_slot_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"],
        "a",
        [{"key": "s1", "value": "5"}, {"key": "s2", "value": "9"}],  # s2 wrong (answer 7)
        "2026-09-29T10:00:00+00:00",
    )
    resp = _post(client, session["id"], profile_id, event)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["wrong_keys"] == ["s2"]


def test_grade_first_wrong_releases_hint_and_adds_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    resp = _post(client, session["id"], profile_id, event)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["hint"]
    assert out["solution"] is None
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None


def test_grade_second_wrong_releases_solution_retry_item_not_duplicated(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    first = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    second = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "8"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, first)
    resp = _post(client, session["id"], profile_id, second)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["hint"]  # still shown
    assert out["solution"] and out["solution"]["final"] == "3 + 2 = 5"
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1  # not duplicated


def test_grade_wrong_then_correct_resolves_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A single-Part Problem (`make_multi_slot_doc` has exactly one Part, "a") -- wrong
    then correct on its only Part must resolve, with no OTHER Part to ever block it."""
    doc = make_multi_slot_doc("bai-1")  # answer: s1=5, s2=7
    Pub(engine)(doc)
    session = _start(client, profile_id)
    wrong = _attempt(
        doc["problem_id"],
        "a",
        [{"key": "s1", "value": "9"}, {"key": "s2", "value": "9"}],
        "2026-09-29T10:00:00+00:00",
    )
    correct = _attempt(
        doc["problem_id"],
        "a",
        [{"key": "s1", "value": "5"}, {"key": "s2", "value": "7"}],
        "2026-09-29T10:00:01+00:00",
    )
    _post(client, session["id"], profile_id, wrong)
    resp = _post(client, session["id"], profile_id, correct)
    out = resp.json()[0]
    assert out["correct"] is True
    assert out["hint"] is None
    assert out["solution"] is None
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is not None


def test_grade_two_parts_one_ever_wrong_retry_queue_stays_open(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Part A wrong once (never corrected), Part B always correct -- Problem-level
    resolution needs every Part correct, so the Retry Queue row stays open."""
    doc = make_doc("bai-1")  # parts "a" (answer 5) and "b" (answer 3)
    Pub(engine)(doc)
    session = _start(client, profile_id)
    a_wrong = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    b_correct = _attempt(
        doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, a_wrong)
    resp = _post(client, session["id"], profile_id, b_correct)
    assert resp.json()[0]["correct"] is True
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None  # still open -- Part A is still wrong


def make_three_part_doc(label: str) -> dict[str, Any]:
    """Three independent single-slot `number_input` Parts ("a", "b", "c")."""
    doc = make_doc(label)
    doc["parts"] = [
        {
            "part_key": key,
            "type": "number_input",
            "prompt": "",
            "image_keys": [],
            "template": f"{value} = [[s1]]",
            "slots": [{"slot_key": "s1"}],
            "answer": [{"key": "s1", "value": value}],
            "hint": "Con thử lại nhé.",
            "solution": {"steps": [f"Kết quả là {value}."], "final": value},
        }
        for key, value in (("a", "5"), ("b", "3"), ("c", "8"))
    ]
    return doc


def test_grade_never_attempted_sibling_part_blocks_resolution(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """#2 (review follow-up): a 3-Part Problem where only Part A is ever touched (wrong,
    then corrected) must NOT resolve the Retry Queue row while Parts B and C were never
    attempted at all -- a never-attempted Part is not "answered correctly", so it blocks
    resolution the same as a currently-wrong one."""
    doc = make_three_part_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    a_wrong = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    a_correct = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, a_wrong)
    resp = _post(client, session["id"], profile_id, a_correct)
    assert resp.json()[0]["correct"] is True
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None  # Parts B and C were never attempted


def test_grade_same_part_wrong_then_correct_within_one_batch_resolves(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """#3 (review follow-up): two attempts on the SAME Part within ONE batch call (wrong,
    then correct) share the same `received_at` (resolved once per request) -- resolution
    must reflect the LATER (correct) one regardless of the two events' UUIDv7 ordering,
    via SQLite's own insertion-order `rowid`, not `(received_at, id)`."""
    doc = make_multi_slot_doc("bai-1")  # single Part "a", answer s1=5, s2=7
    Pub(engine)(doc)
    session = _start(client, profile_id)
    wrong = _attempt(
        doc["problem_id"],
        "a",
        [{"key": "s1", "value": "9"}, {"key": "s2", "value": "9"}],
        "2026-09-29T10:00:00+00:00",
    )
    correct = _attempt(
        doc["problem_id"],
        "a",
        [{"key": "s1", "value": "5"}, {"key": "s2", "value": "7"}],
        "2026-09-29T10:00:01+00:00",
    )
    resp = _post(client, session["id"], profile_id, wrong, correct)  # ONE batch call
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out[0]["correct"] is False
    assert out[1]["correct"] is True
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is not None  # the later (correct) attempt wins


def test_grade_order_wrong_has_no_partial_wrong_keys(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    doc["parts"] = [
        {
            "part_key": "p1",
            "type": "order",
            "prompt": "",
            "image_keys": [],
            "items": [
                {"item_key": "n2", "text": "2"},
                {"item_key": "n4", "text": "4"},
            ],
            "direction": "asc",
            "answer": {"order": ["n2", "n4"]},
            "hint": "Số bé trước.",
            "solution": {"steps": ["2 rồi 4."], "final": "2, 4"},
        }
    ]
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(doc["problem_id"], "p1", {"order": ["n4", "n2"]}, "2026-09-29T10:00:00+00:00")
    resp = _post(client, session["id"], profile_id, event)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["wrong_keys"] == []


def test_grade_resent_attempt_idempotent_no_regrade_no_double_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    first = _post(client, session["id"], profile_id, event)
    second = _post(client, session["id"], profile_id, event)
    assert first.json() == second.json()
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1  # resend did not add a 2nd row


def test_hint_requested_has_no_side_effect_no_pre_released_hint(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "hint_requested",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a"},
        "occurred_at": "2026-09-29T10:00:00+00:00",
    }
    resp = _post(client, session["id"], profile_id, event)
    out = resp.json()[0]
    assert out["correct"] is None  # not an attempt -- no grading fields at all
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert rows == []


def test_grade_bad_part_key_422_not_500(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(doc["problem_id"], "not-a-real-part", "5", "2026-09-29T10:00:00+00:00")
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "PART_NOT_FOUND")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
    assert rows == []  # never stored


def test_grade_malformed_submitted_value_graded_wrong_not_500(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"], "a", "not-the-expected-shape-at-all", "2026-09-29T10:00:00+00:00"
    )
    resp = _post(client, session["id"], profile_id, event)
    assert resp.status_code == 201, resp.text
    assert resp.json()[0]["correct"] is False


# --- #6 edge cases (review follow-up) --------------------------------------------------


def make_fallback_doc(label: str) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "fallback.json").read_text(encoding="utf-8"))
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


def test_grade_attempt_on_fallback_part_422_via_real_endpoint(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A real `attempt` event against a `fallback` Part's own `part_key`, through the
    actual `POST /events` endpoint (not just a direct `grade_part()` call) -- `fallback`
    is solution-only (`answer` always `None`) and must never be graded."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(doc["problem_id"], "p1", "anything", "2026-09-29T10:00:00+00:00")
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "PART_NOT_FOUND")


def test_grade_attempt_with_null_problem_id_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """An `attempt` event with `problem_id: null` reaches the grading code path (not
    just some earlier, unrelated short-circuit) and fails loudly, never a 500."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": None,
        "payload": {"part_key": "a", "value": [{"key": "s1", "value": "5"}]},
        "occurred_at": "2026-09-29T10:00:00+00:00",
    }
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "PART_NOT_FOUND")


def test_grade_third_wrong_attempt_still_shows_solution_single_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A 3rd (and not just a 2nd) wrong attempt on the same Part keeps showing the
    Solution, and the Retry Queue row is still exactly one (not re-added)."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    resp = None
    for i in range(3):
        event = _attempt(
            doc["problem_id"],
            "a",
            [{"key": "s1", "value": "9"}],
            f"2026-09-29T10:00:0{i}+00:00",
        )
        resp = _post(client, session["id"], profile_id, event)
    assert resp is not None
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["solution"] is not None
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1


def test_hint_requested_then_wrong_attempt_on_same_part_still_stages_normally(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """`hint_requested` right before a wrong `attempt` on the same Part doesn't change
    staging: the wrong attempt is still treated as the Part's FIRST wrong attempt (Hint
    released, Retry Queue row added) -- asking early doesn't unlock anything early, and
    doesn't interfere with the real staged-help count either."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    hint_event = {
        "id": str(uuid.uuid7()),
        "kind": "hint_requested",
        "problem_id": doc["problem_id"],
        "payload": {"part_key": "a"},
        "occurred_at": "2026-09-29T10:00:00+00:00",
    }
    wrong_event = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, hint_event)
    resp = _post(client, session["id"], profile_id, wrong_event)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["hint"]
    assert out["solution"] is None  # still the FIRST wrong attempt on this Part


# --- Fallback self-check (Story 2.8) --------------------------------------------------


def _fallback_event(kind: str, problem_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": kind,
        "problem_id": problem_id,
        "payload": payload,
        "occurred_at": "2026-09-29T10:00:00+00:00",
    }


def test_fallback_revealed_first_tap_stored_inert(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """`fallback_revealed` is stored with no MUTATING side effect (no Retry Queue row),
    exactly like `hint_requested` -- but its response DOES carry the fallback Part's own
    `solution`, since `child_view()`/the bundle never carries it (Spec Change Log)."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("fallback_revealed", doc["problem_id"], {"part_key": "p1"})
    resp = _post(client, session["id"], profile_id, event)
    assert resp.status_code == 201, resp.text
    out = resp.json()[0]
    assert out["correct"] is None
    assert out["solution"] == {
        "steps": ["Đi theo lối không bị chặn."],
        "final": "Chú thỏ đi theo lối bên phải về nhà.",
    }
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1
    assert rows[0].kind == "fallback_revealed"
    with engine.connect() as conn:
        retry_rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert retry_rows == []


def test_self_marked_dung_stored_no_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """`self_marked` with `correct: true` is stored (a Star is derivable by a future
    reader counting it) but adds nothing to the Retry Queue."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": True})
    resp = _post(client, session["id"], profile_id, event)
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1
    stored_payload = json.loads(rows[0].payload_json)
    assert stored_payload["correct"] is True
    with engine.connect() as conn:
        retry_rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert retry_rows == []


def test_self_marked_chua_dung_adds_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    resp = _post(client, session["id"], profile_id, event)
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None


def test_self_marked_chua_dung_twice_two_sessions_dedup_one_open_row(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Two Sessions, both `self_marked(correct: false)` on the same Problem -- the Retry
    Queue still has exactly one open row (`_add_retry_item()`'s existing skip-if-exists)."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session_a = _start(client, profile_id)
    session_b = _start(client, profile_id)
    event_a = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    event_b = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    _post(client, session_a["id"], profile_id, event_a)
    _post(client, session_b["id"], profile_id, event_b)
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None


def test_self_marked_missing_correct_field_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {})
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "SELF_MARKED_INVALID_PAYLOAD")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
    assert rows == []


def test_self_marked_malformed_correct_field_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": "yes"})
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "SELF_MARKED_INVALID_PAYLOAD")


def test_self_marked_wrong_profile_for_session_403(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    resp = client.post(
        f"{API}/{session['id']}/events",
        json={"profile_id": str(uuid.uuid7()), "events": [event]},
    )
    _envelope(resp, 403, "FORBIDDEN")


def test_self_marked_resent_idempotent_no_double_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    first = _post(client, session["id"], profile_id, event)
    second = _post(client, session["id"], profile_id, event)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json() == second.json()
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
        retry_rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert len(retry_rows) == 1


def test_fallback_revealed_resent_idempotent_same_solution(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("fallback_revealed", doc["problem_id"], {"part_key": "p1"})
    first = _post(client, session["id"], profile_id, event)
    second = _post(client, session["id"], profile_id, event)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json() == second.json()
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
    assert len(rows) == 1


def test_fallback_part_never_graded_via_self_marked_path(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A fallback Problem's `p1` Part is never passed through `grade_part()` for
    `self_marked`/`fallback_revealed` -- both kinds insert successfully with no 422/500,
    proving the fallback Part's `TypeError`-raising grader is never invoked for them."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    reveal = _fallback_event("fallback_revealed", doc["problem_id"], {"part_key": "p1"})
    mark = _fallback_event("self_marked", doc["problem_id"], {"correct": True})
    resp = _post(client, session["id"], profile_id, reveal, mark)
    assert resp.status_code == 201, resp.text


def test_self_marked_rejected_for_non_fallback_graded_problem(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #1 (critical): `self_marked` posted against a real GRADED
    Problem (not a `fallback` one) must be rejected -- otherwise a client could
    self-award a derived Star on `correct: true` with no grading at all, or push an
    arbitrary never-attempted graded Problem onto the Retry Queue on `correct: false`."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", doc["problem_id"], {"correct": True})
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "SELF_MARKED_NOT_FALLBACK")
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.id).where(progress_events.c.id == event["id"])
        ).all()
    assert rows == []


def test_self_marked_chua_dung_then_dung_resolves_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #2 (high): a Problem self-marked "chưa đúng" (opening a Retry
    Queue row), then LATER self-marked "đúng" on a retry, must resolve that row --
    `grade_part()`/`_grade_and_stage()` are never invoked for a fallback Part, so nothing
    else could ever resolve it."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    wrong = _fallback_event("self_marked", doc["problem_id"], {"correct": False})
    _post(client, session["id"], profile_id, wrong)
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is None

    right = _fallback_event("self_marked", doc["problem_id"], {"correct": True})
    resp = _post(client, session["id"], profile_id, right)
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is not None


def test_self_marked_null_problem_id_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #5: `self_marked` with `problem_id: null` -> 422, untested until
    now (`_validate_self_marked()` explicitly checks this)."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _fallback_event("self_marked", None, {"correct": True})
    resp = _post(client, session["id"], profile_id, event)
    _envelope(resp, 422, "SELF_MARKED_INVALID_PAYLOAD")


def test_self_marked_dung_star_is_derived_by_counting_events(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #4: demonstrates the "Star is derived by counting `self_marked`
    events with `correct: true`" claim as an actual counting mechanism -- posts 2 correct
    self-marks (on two distinct fallback Problems) and manually queries `progress_events`
    the way a future Star-derivation reader would, documenting the query shape."""
    doc_1 = make_fallback_doc("bai-1")
    doc_2 = make_fallback_doc("bai-2")
    Pub(engine)(doc_1, doc_2)
    session = _start(client, profile_id)
    event_1 = _fallback_event("self_marked", doc_1["problem_id"], {"correct": True})
    event_2 = _fallback_event("self_marked", doc_2["problem_id"], {"correct": True})
    _post(client, session["id"], profile_id, event_1)
    _post(client, session["id"], profile_id, event_2)

    # The derivation query shape a future reader (Story 2.10's Session summary) would
    # use: count `self_marked` rows for this Profile whose payload's `correct` is True.
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_events.c.payload_json).where(
                progress_events.c.profile_id == profile_id,
                progress_events.c.kind == "self_marked",
            )
        ).all()
    star_count = sum(1 for row in rows if json.loads(row.payload_json).get("correct") is True)
    assert star_count == 2


def test_retry_queue_counting_is_profile_wide_across_two_sessions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A 1st wrong attempt in one Session and a 2nd wrong attempt in a DIFFERENT Session
    (same Profile, same Problem/Part) still correctly escalates to the Solution -- staged
    help and the Retry Queue are Profile-wide, not Session-scoped (this story's frozen
    intent), with two REAL distinct `session_id`s, not just asserted by code inspection."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session_a = _start(client, profile_id)
    session_b = _start(client, profile_id)
    assert session_a["id"] != session_b["id"]
    first_wrong = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    second_wrong = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "8"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session_a["id"], profile_id, first_wrong)
    resp = _post(client, session_b["id"], profile_id, second_wrong)
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["solution"] is not None
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert len(rows) == 1  # one Retry Queue row, not one per Session


# --- Session summary, replay, streak (Story 2.10) -------------------------------------


def _completed(occurred_at: str = "2026-09-29T10:00:00+00:00") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "session_completed",
        "problem_id": None,
        "payload": {},
        "occurred_at": occurred_at,
    }


def _summary(client: TestClient, session_id: str, profile_id: str):
    return client.get(f"{API}/{session_id}/summary", params={"profile_id": profile_id})


def _replay_ref(source_session_id: str) -> dict[str, str]:
    return {"kind": "replay", "source_session_id": source_session_id}


def _start_replay(client: TestClient, profile_id: str, source_session_id: str):
    return client.post(
        API,
        json={
            "profile_id": profile_id,
            "ref": _replay_ref(source_session_id),
            "mode": "replay",
        },
    )


def test_summary_before_completion_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    resp = _summary(client, session["id"], profile_id)
    _envelope(resp, 422, "SESSION_NOT_COMPLETED")


def test_session_completed_sets_completed_at_and_is_idempotent(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    event = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
    )
    _post(client, session["id"], profile_id, event)
    completed = _completed()
    resp = _post(client, session["id"], profile_id, completed)
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        row = conn.execute(
            select(progress_sessions).where(progress_sessions.c.id == session["id"])
        ).one()
    assert row.completed_at is not None
    first_completed_at = row.completed_at

    # Resent (same event id): idempotent no-op, `completed_at` unchanged.
    resp2 = _post(client, session["id"], profile_id, completed)
    assert resp2.status_code == 201, resp2.text
    with engine.connect() as conn:
        row2 = conn.execute(
            select(progress_sessions).where(progress_sessions.c.id == session["id"])
        ).one()
    assert row2.completed_at == first_completed_at

    summary = _summary(client, session["id"], profile_id).json()
    assert summary["first_try_correct"] == 1
    assert summary["total"] == 1
    assert summary["wrong_problem_ids"] == []


def test_summary_first_try_wrong_then_correct_not_counted(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    wrong = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
    )
    correct = _attempt(
        doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, wrong)
    _post(client, session["id"], profile_id, correct)
    _post(client, session["id"], profile_id, _completed())
    summary = _summary(client, session["id"], profile_id).json()
    assert summary["first_try_correct"] == 0
    assert summary["total"] == 1
    assert summary["wrong_problem_ids"] == [doc["problem_id"]]


def test_summary_wrong_problem_ids_preserve_session_order(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    docs = [make_doc(f"bai-{i}") for i in range(3)]
    Pub(engine)(*docs)
    session = _start(client, profile_id)
    # bai-0: correct first try. bai-1: wrong. bai-2: never attempted at all.
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            docs[0]["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            docs[1]["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    _post(client, session["id"], profile_id, _completed())
    summary = _summary(client, session["id"], profile_id).json()
    assert summary["first_try_correct"] == 1
    assert summary["total"] == 3
    assert summary["wrong_problem_ids"] == [docs[1]["problem_id"], docs[2]["problem_id"]]


def test_summary_streak_is_one_right_after_first_completed_session(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(client, session["id"], profile_id, _completed())
    summary = _summary(client, session["id"], profile_id).json()
    assert summary["streak"] == 1


def test_replay_resolves_wrong_problems_in_original_order_only(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    docs = [make_doc(f"bai-{i}") for i in range(3)]
    Pub(engine)(*docs)
    source = _start(client, profile_id)
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            docs[0]["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            docs[1]["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    _post(client, source["id"], profile_id, _completed())

    resp = _start_replay(client, profile_id, source["id"])
    assert resp.status_code == 201, resp.text
    replay = resp.json()
    assert replay["mode"] == "replay"
    # bai-1 (wrong) and bai-2 (never attempted) -- never bai-0 (correct first try).
    assert replay["problem_ids"] == [docs[1]["problem_id"], docs[2]["problem_id"]]


def test_replay_zero_wrong_problems_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    source = _start(client, profile_id)
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(client, source["id"], profile_id, _completed())
    resp = _start_replay(client, profile_id, source["id"])
    _envelope(resp, 422, "REPLAY_NO_WRONG_PROBLEMS")


def test_replay_source_session_wrong_profile_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    source = _start(client, profile_id)
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(client, source["id"], profile_id, _completed())
    other_profile_id = str(uuid.uuid7())
    with engine.begin() as conn:
        conn.execute(
            parent_profiles.insert().values(
                id=other_profile_id,
                name="Su",
                avatar="dog",
                grade=1,
                created_at="2026-09-29T00:00:00+00:00",
            )
        )
    resp = _start_replay(client, other_profile_id, source["id"])
    _envelope(resp, 422, "REPLAY_SOURCE_NOT_FOUND")


def test_replay_wrong_attempt_does_not_add_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """AD-6: a `replay`-mode Session's wrong attempts never re-add to the Retry Queue --
    Hint/Solution staging (grading itself) is unaffected."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    source = _start(client, profile_id)
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(client, source["id"], profile_id, _completed())
    replay = _start_replay(client, profile_id, source["id"]).json()

    resp = _post(
        client,
        replay["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T11:00:00+00:00"
        ),
    )
    out = resp.json()[0]
    assert out["correct"] is False
    assert out["hint"]  # grading/Hint staging itself is unaffected

    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    # The ORIGINAL wrong attempt (in the source Session) already added one row; the
    # replay's wrong attempt on the SAME Problem/Part must not add a second one.
    assert len(rows) == 1


def test_replay_self_marked_false_does_not_add_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    source = _start(client, profile_id)
    _post(client, source["id"], profile_id, _completed())
    # `source` has zero wrong Problems recorded via `attempt`/`self_marked`, but its own
    # frozen `problem_ids` still includes the fallback Problem with no evidence at all --
    # per `session_wrong_problem_ids()`, "never attempted" counts as NOT first-try-correct,
    # so it IS a valid (non-empty) replay target.
    replay = _start_replay(client, profile_id, source["id"]).json()
    assert replay["problem_ids"] == [doc["problem_id"]]

    resp = _post(
        client,
        replay["id"],
        profile_id,
        _fallback_event("self_marked", doc["problem_id"], {"correct": False}),
    )
    assert resp.status_code == 201, resp.text
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.profile_id == profile_id,
                progress_retry_items.c.problem_id == doc["problem_id"],
            )
        ).all()
    assert rows == []


def test_replay_correct_attempt_still_resolves_existing_retry_item(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Documented implementer's decision: `_maybe_resolve_retry_item()` is NOT gated on
    `mode` -- resolving a pre-existing open Retry Queue item via a replay attempt is a
    reasonable side effect (AD-6's exclusion is about replay attempts never ADDING to
    Stars/Retry/Streak, not about blocking a legitimate resolution)."""
    # Single-Part doc (`make_multi_slot_doc` -- Part "a" only, slots s1/s2, answer 5/7):
    # a real 2nd Part with no attempt at all would otherwise block resolution
    # (`_maybe_resolve_retry_item()`'s "every OTHER Part" check), which isn't what this
    # test is about.
    doc = make_multi_slot_doc("bai-1")
    Pub(engine)(doc)
    practice = _start(client, profile_id)
    _post(
        client,
        practice["id"],
        profile_id,
        _attempt(
            doc["problem_id"],
            "a",
            [{"key": "s1", "value": "9"}, {"key": "s2", "value": "9"}],
            "2026-09-29T10:00:00+00:00",
        ),
    )
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert len(rows) == 1 and rows[0].resolved_at is None

    _post(client, practice["id"], profile_id, _completed())
    replay = _start_replay(client, profile_id, practice["id"]).json()
    _post(
        client,
        replay["id"],
        profile_id,
        _attempt(
            doc["problem_id"],
            "a",
            [{"key": "s1", "value": "5"}, {"key": "s2", "value": "7"}],
            "2026-09-29T11:00:00+00:00",
        ),
    )
    with engine.connect() as conn:
        rows = conn.execute(
            select(progress_retry_items).where(
                progress_retry_items.c.problem_id == doc["problem_id"]
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].resolved_at is not None


def test_streak_excludes_replay_mode_sessions() -> None:
    """`compute_streak()` directly (Story 2.10, AD-6): a day whose only completed Session
    was `mode="replay"` does not count towards the Streak."""
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    from hoctap.db.engine import run_migrations
    from hoctap.learning.summary import compute_streak

    eng = create_engine(URL.create("sqlite", database=":memory:"))
    run_migrations(eng)
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(
                id="s-practice",
                profile_id=profile_id,
                ref_kind="lesson",
                ref_key="lesson:x:y:z",
                mode="practice",
                problem_ids_json="[]",
                chunk_size=10,
                started_at="2026-09-28T03:00:00+00:00",
                completed_at="2026-09-28T03:00:00+00:00",
            )
        )
        conn.execute(
            progress_sessions.insert().values(
                id="s-replay",
                profile_id=profile_id,
                ref_kind="replay",
                ref_key="replay:s-practice",
                mode="replay",
                problem_ids_json="[]",
                chunk_size=10,
                started_at="2026-09-29T03:00:00+00:00",
                completed_at="2026-09-29T03:00:00+00:00",
            )
        )
    with eng.connect() as conn:
        streak = compute_streak(conn, profile_id, date(2026, 9, 29))
    # Only 2026-09-28 (practice) counts; 2026-09-29's only completed Session was replay,
    # so it does not extend the Streak -- and per the "still alive" boundary, since today
    # (09-29) itself has no completed non-replay Session, the walk starts at yesterday.
    assert streak == 1


def test_streak_consecutive_days_and_a_gap_day() -> None:
    """`compute_streak()` directly: 3 consecutive completed days reads 3; a gap day (day 1
    and day 3 completed, day 2 not) reads however the "still alive" boundary defines it --
    here, walking backward from day 3 (today), the gap on day 2 stops the count at 1."""
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    from hoctap.db.engine import run_migrations
    from hoctap.learning.summary import compute_streak

    eng = create_engine(URL.create("sqlite", database=":memory:"))
    run_migrations(eng)
    profile_id = "p1"

    def _row(session_id: str, day: str) -> dict[str, Any]:
        return dict(
            id=session_id,
            profile_id=profile_id,
            ref_kind="lesson",
            ref_key="lesson:x:y:z",
            mode="practice",
            problem_ids_json="[]",
            chunk_size=10,
            started_at=f"{day}T03:00:00+00:00",
            completed_at=f"{day}T03:00:00+00:00",
        )

    with eng.begin() as conn:
        conn.execute(progress_sessions.insert().values(**_row("s1", "2026-09-01")))
        conn.execute(progress_sessions.insert().values(**_row("s2", "2026-09-02")))
        conn.execute(progress_sessions.insert().values(**_row("s3", "2026-09-03")))

    with eng.connect() as conn:
        three_in_a_row = compute_streak(conn, profile_id, date(2026, 9, 3))
    assert three_in_a_row == 3

    with eng.begin() as conn:
        conn.execute(progress_sessions.insert().values(**_row("s5", "2026-09-05")))
    with eng.connect() as conn:
        gap_day_streak = compute_streak(conn, profile_id, date(2026, 9, 5))
    assert gap_day_streak == 1  # day 4 missing breaks the chain; only day 5 itself counts


def test_session_completed_second_distinct_event_does_not_overwrite_completed_at(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #1 (2026-09-29, high): the `already_stored` fast path in
    `post_event()` only catches a literal RESEND of the SAME event id. A second, DISTINCT
    `session_completed` event (a different UUIDv7 -- two open tabs, or a client retry
    after a false-timeout) must still be stored durably (it's a valid event), but must NOT
    overwrite `completed_at`, which the FIRST `session_completed` event to arrive already
    set."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )

    first_event = _completed("2026-09-29T10:00:01+00:00")
    resp1 = _post(client, session["id"], profile_id, first_event)
    assert resp1.status_code == 201, resp1.text
    with engine.connect() as conn:
        row1 = conn.execute(
            select(progress_sessions).where(progress_sessions.c.id == session["id"])
        ).one()
    assert row1.completed_at is not None
    first_completed_at = row1.completed_at

    # A DIFFERENT event id (not a resend) -- must be stored, but must be a no-op for
    # `completed_at`.
    second_event = _completed("2026-09-29T12:00:00+00:00")
    assert second_event["id"] != first_event["id"]
    resp2 = _post(client, session["id"], profile_id, second_event)
    assert resp2.status_code == 201, resp2.text

    with engine.connect() as conn:
        row2 = conn.execute(
            select(progress_sessions).where(progress_sessions.c.id == session["id"])
        ).one()
        stored_kinds = conn.execute(
            select(progress_events.c.id).where(
                progress_events.c.session_id == session["id"],
                progress_events.c.kind == "session_completed",
            )
        ).all()
    assert row2.completed_at == first_completed_at  # unchanged by the second, later event
    # Both distinct `session_completed` events are still durably stored -- a valid event
    # is never rejected, it's simply a no-op for `completed_at`.
    assert len(stored_kinds) == 2


def test_replay_source_session_not_completed_422(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #2 (2026-09-29, medium): a client must not be able to start a
    replay against a source Session that's still in progress (no `completed_at`) --
    `session_wrong_problem_ids()`'s "never attempted" rule would otherwise make an
    in-progress Session look like a valid, non-empty replay target."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    source = _start(client, profile_id)
    _post(
        client,
        source["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    # No `session_completed` posted -- `source` is still in progress.
    resp = _start_replay(client, profile_id, source["id"])
    _envelope(resp, 422, "REPLAY_SOURCE_NOT_COMPLETED")


def test_summary_wrong_problem_ids_empty_when_all_correct_first_try(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Review Triage Log #4 (2026-09-29, low): a targeted assertion that
    `wrong_problem_ids` is empty (the signal the frontend's "Luyện lại bài sai" button
    hiding reads) when every Problem was answered correctly on the first try -- previously
    only exercised incidentally as a byproduct of a different test's `first_try_correct`
    assertion."""
    docs = [make_doc(f"bai-{i}") for i in range(2)]
    Pub(engine)(*docs)
    session = _start(client, profile_id)
    for i, doc in enumerate(docs):
        _post(
            client,
            session["id"],
            profile_id,
            _attempt(
                doc["problem_id"],
                "a",
                [{"key": "s1", "value": "5"}],
                f"2026-09-29T10:00:0{i}+00:00",
            ),
        )
    _post(client, session["id"], profile_id, _completed())
    summary = _summary(client, session["id"], profile_id).json()
    assert summary["wrong_problem_ids"] == []
    assert summary["first_try_correct"] == summary["total"] == 2


def test_streak_crosses_utc_local_calendar_day_boundary() -> None:
    """Review Triage Log #3 (2026-09-29, low): every other streak test happens to use a
    timestamp that falls on the SAME calendar day in both UTC and Asia/Ho_Chi_Minh
    (UTC+7), so none of them actually exercise `_local_date()`'s `.astimezone(LOCAL_TZ)`
    conversion at a real boundary -- a regression that dropped the `.astimezone()` call
    entirely would still pass every existing streak test. `18:00:00+00:00` UTC is
    `01:00` the next day in +07:00, so a completed Session stored with that `completed_at`
    must count towards the LOCAL day after its UTC date, not the UTC date itself."""
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    from hoctap.db.engine import run_migrations
    from hoctap.learning.summary import compute_streak

    eng = create_engine(URL.create("sqlite", database=":memory:"))
    run_migrations(eng)
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(
                id="s-boundary",
                profile_id=profile_id,
                ref_kind="lesson",
                ref_key="lesson:x:y:z",
                mode="practice",
                problem_ids_json="[]",
                chunk_size=10,
                started_at="2026-09-28T18:00:00+00:00",
                # UTC calendar date: 2026-09-28. Local (Asia/Ho_Chi_Minh, +07:00)
                # calendar date: 2026-09-29 01:00 -> 2026-09-29.
                completed_at="2026-09-28T18:00:00+00:00",
            )
        )
    with eng.connect() as conn:
        # `today` is the LOCAL date (2026-09-29) the completed_at converts to -- if
        # `_local_date()` incorrectly used the UTC date (2026-09-28) instead, this Session
        # would not be found "today" and the streak would read 0.
        streak_today_local = compute_streak(conn, profile_id, date(2026, 9, 29))
        # And it must NOT count towards the UTC date (2026-09-28) as "today" either --
        # 2026-09-28 local has no completed Session (nor does 2026-09-27, its "yesterday"),
        # so the streak from that vantage point is 0.
        streak_utc_date_as_today = compute_streak(conn, profile_id, date(2026, 9, 28))
    assert streak_today_local == 1
    assert streak_utc_date_as_today == 0
