"""Story 2.3: the child Library (`GET /library/*`).

One test (or group) per row of the I/O matrix: profile picker data comes from the
existing `/profiles`; these tests cover the new read-only Library/Home endpoints --
Book/Unit/Lesson listing with visible-Problem counts, the "Học tiếp" resolution and the
unknown-profile 404 -- plus the exclusion rules (hidden/needs_review/retired never
counted, matching `visible_to_child()`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

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
from hoctap.content.review import service as review
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK_2020 = "toan1-2020-q1"
BOOK_2024 = "toan1-2024-t1"
UNIT, LESSON = "tuan-5", "tiet-2"
API = "/api/v1/library"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


def make_doc(book_id: str, label: str, position_hint: int = 1) -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=f"{book_id}.{UNIT}.{LESSON}.{label}",
        book_id=book_id,
        unit_key=UNIT,
        lesson_key=LESSON,
        problem_label=label,
        display_label=f"Bài {label}",
        concept_ids=[],
        concept_proposals=[],
    )
    return doc


class Pub:
    """Publishes Problems the way the builder does (catalog upsert + publish)."""

    def __init__(self, engine: Engine, book_id: str, edition: str, grade: int) -> None:
        self.engine = engine
        self.book_id = book_id
        with engine.begin() as conn:
            upsert_books(
                conn,
                [
                    BookRow(
                        book_id,
                        edition,
                        grade,
                        1,
                        f"Toán {grade} – {edition}",
                        f"{book_id}.pdf",
                        10,
                        1,
                        "f",
                    )
                ],
            )

    def __call__(
        self,
        *docs: dict[str, Any],
        needs_review: set[str] = frozenset(),
        duplicate: set[str] = frozenset(),
    ) -> None:
        with self.engine.begin() as conn:
            result = publish_problems(
                conn,
                self.book_id,
                units=[UnitRow(self.book_id, UNIT, "TUẦN 5", "", 500)],
                lessons=[LessonRow(self.book_id, UNIT, LESSON, "Tiết 2", "", 501)],
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
            proposals |= {d["problem_id"]: [] for d in docs}
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
        yield c


@pytest.fixture
def engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined]


def _envelope(resp, status: int, code: str) -> str:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]["message"]


# --- No PIN / parent gate needed ---------------------------------------------------


def test_no_auth_required(client: TestClient) -> None:
    resp = client.get(f"{API}/grades/1/books")
    assert resp.status_code == 200


# --- Book list: both Editions of a Grade -------------------------------------------


def test_grade_books_both_editions(client: TestClient, engine: Engine) -> None:
    pub2020 = Pub(engine, BOOK_2020, "2020", 1)
    pub2024 = Pub(engine, BOOK_2024, "2024-25", 1)
    pub2020(make_doc(BOOK_2020, "bai-1"))
    pub2024(make_doc(BOOK_2024, "bai-1"))

    resp = client.get(f"{API}/grades/1/books")
    assert resp.status_code == 200
    books = resp.json()
    assert {b["book_id"] for b in books} == {BOOK_2020, BOOK_2024}
    assert {b["edition"] for b in books} == {"2020", "2024-25"}
    # Both listed as separate Books, each with its own Unit/Lesson tree.
    for b in books:
        assert b["units"][0]["unit_key"] == UNIT
        assert b["units"][0]["lessons"][0]["lesson_key"] == LESSON


def test_grade_books_other_grade_not_included(client: TestClient, engine: Engine) -> None:
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    resp = client.get(f"{API}/grades/2/books")
    assert resp.status_code == 200
    assert resp.json() == []


def test_grade_books_book_with_zero_units(client: TestClient, engine: Engine) -> None:
    """A Book in the catalogue with nothing published yet (no Unit/Lesson/Problem rows):
    `units` is an empty list, not an error or a missing entry."""
    Pub(engine, BOOK_2020, "2020", 1)  # upsert_books only, no publish_problems call

    resp = client.get(f"{API}/grades/1/books")
    assert resp.status_code == 200
    books = resp.json()
    assert len(books) == 1
    assert books[0]["book_id"] == BOOK_2020
    assert books[0]["units"] == []


def test_grade_books_unit_with_zero_lessons(client: TestClient, engine: Engine) -> None:
    """A published Unit with no Lessons under it yet: the Unit is still listed, with an
    empty `lessons` list."""
    with engine.begin() as conn:
        upsert_books(
            conn,
            [BookRow(BOOK_2020, "2020", 1, 1, "Toán 1 – 2020", f"{BOOK_2020}.pdf", 10, 1, "f")],
        )
        publish_problems(
            conn,
            BOOK_2020,
            units=[UnitRow(BOOK_2020, UNIT, "TUẦN 5", "", 500)],
            lessons=[],
            problems=[],
        )

    resp = client.get(f"{API}/grades/1/books")
    assert resp.status_code == 200
    units = resp.json()[0]["units"]
    assert len(units) == 1
    assert units[0]["unit_key"] == UNIT
    assert units[0]["lessons"] == []


# --- Lesson progress count: only visible_to_child()-eligible Problems --------------


def test_lesson_count_excludes_hidden_needs_review_retired(
    client: TestClient, engine: Engine
) -> None:
    pub = Pub(engine, BOOK_2020, "2020", 1)
    visible = make_doc(BOOK_2020, "bai-1")
    hidden = make_doc(BOOK_2020, "bai-2")
    needs_review = make_doc(BOOK_2020, "bai-3")
    # bai-3 flagged needs_review (awaiting_approval, so not visible).
    pub(visible, hidden, needs_review, needs_review={needs_review["problem_id"]})
    with engine.begin() as conn:
        review.set_hidden(conn, hidden["problem_id"], True)

    resp = client.get(f"{API}/grades/1/books")
    lesson = resp.json()[0]["units"][0]["lessons"][0]
    assert lesson["problem_count"] == 1  # only bai-1
    assert lesson["problem_count"] != 3


def test_lesson_count_no_profile_never_shows_a_nonzero_numerator(
    client: TestClient, engine: Engine
) -> None:
    """Without `profile_id`, `attempted` is honestly 0 -- Story 2.4 never fabricates a
    numerator when there is no Profile to count for."""
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    resp = client.get(f"{API}/grades/1/books")
    lesson = resp.json()[0]["units"][0]["lessons"][0]
    assert set(lesson) == {"lesson_key", "label", "title", "position", "problem_count", "attempted"}
    assert lesson["attempted"] == 0


def test_grade_books_unknown_profile_id_404(client: TestClient, engine: Engine) -> None:
    """#11 (orchestrator's independent review round): an unknown `profile_id` on
    `/library/grades/{grade}/books` must 404, matching the sibling `/library/home/{id}`
    convention -- not silently return a real book/lesson tree with an all-zero
    `attempted` column as if the id had simply never attempted anything."""
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    resp = client.get(f"{API}/grades/1/books", params={"profile_id": "no-such-profile"})
    _envelope(resp, 404, "PROFILE_NOT_FOUND")


def test_lesson_attempted_counts_real_progress_with_profile_id(
    client: TestClient, engine: Engine
) -> None:
    """Story 2.4: given `profile_id`, `attempted` is the real "done at least once" count --
    distinct Problems with an `attempt` event, capped by the visible denominator."""
    from hoctap.ids import new_id, utc_now
    from hoctap.learning.models import progress_events

    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    doc1 = make_doc(BOOK_2020, "bai-1")
    doc2 = make_doc(BOOK_2020, "bai-2")
    Pub(engine, BOOK_2020, "2020", 1)(doc1, doc2)

    session = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()
    with engine.begin() as conn:
        now = utc_now()
        conn.execute(
            progress_events.insert().values(
                id=new_id(),
                session_id=session["id"],
                profile_id=profile_id,
                kind="attempt",
                problem_id=doc1["problem_id"],
                payload_json="{}",
                occurred_at=now.isoformat(),
                received_at=now.isoformat(),
            )
        )

    resp = client.get(f"{API}/grades/1/books", params={"profile_id": profile_id})
    lesson = resp.json()[0]["units"][0]["lessons"][0]
    assert lesson["problem_count"] == 2
    assert lesson["attempted"] == 1


def test_lesson_attempted_numerator_never_exceeds_denominator_after_hide(
    client: TestClient, engine: Engine
) -> None:
    """Story 2.4: attempt a Problem, then hide it -- `attempted` must drop together with
    `problem_count` (both derived from the same visible-Problem set), never leaving a
    numerator bigger than the denominator."""
    from hoctap.ids import new_id, utc_now
    from hoctap.learning.models import progress_events

    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    doc1 = make_doc(BOOK_2020, "bai-1")
    doc2 = make_doc(BOOK_2020, "bai-2")
    Pub(engine, BOOK_2020, "2020", 1)(doc1, doc2)

    session = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()
    with engine.begin() as conn:
        now = utc_now()
        conn.execute(
            progress_events.insert().values(
                id=new_id(),
                session_id=session["id"],
                profile_id=profile_id,
                kind="attempt",
                problem_id=doc1["problem_id"],
                payload_json="{}",
                occurred_at=now.isoformat(),
                received_at=now.isoformat(),
            )
        )

    before = client.get(f"{API}/grades/1/books", params={"profile_id": profile_id}).json()
    lesson_before = before[0]["units"][0]["lessons"][0]
    assert lesson_before["problem_count"] == 2
    assert lesson_before["attempted"] == 1

    with engine.begin() as conn:
        review.set_hidden(conn, doc1["problem_id"], True)

    after = client.get(f"{API}/grades/1/books", params={"profile_id": profile_id}).json()
    lesson_after = after[0]["units"][0]["lessons"][0]
    assert lesson_after["problem_count"] == 1  # bai-1 no longer counted at all
    assert lesson_after["attempted"] == 0  # its attempt no longer counted either
    assert lesson_after["attempted"] <= lesson_after["problem_count"]


# --- Lesson detail: visible Problems, child_view() shape ---------------------------


def test_attempted_lesson_counts_matches_visible_counts_when_everything_attempted(
    client: TestClient, engine: Engine
) -> None:
    """#12 (orchestrator's independent review round): `learning.progress.
    attempted_lesson_counts()` and `content.library._visible_counts()` are two
    independently-maintained copies of the same "iterate `load_effective()`, filter on
    `state.visible`" loop, with nothing coupling them. When every visible Problem of a
    Book has been attempted, the two should agree exactly -- a future change to one that
    isn't mirrored in the other would show up here as a mismatch."""
    from hoctap.content.library import _visible_counts
    from hoctap.ids import new_id, utc_now
    from hoctap.learning import progress as learning_progress
    from hoctap.learning.models import progress_events

    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    doc1 = make_doc(BOOK_2020, "bai-1")
    doc2 = make_doc(BOOK_2020, "bai-2")
    Pub(engine, BOOK_2020, "2020", 1)(doc1, doc2)

    session = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()
    with engine.begin() as conn:
        now = utc_now()
        for doc in (doc1, doc2):
            conn.execute(
                progress_events.insert().values(
                    id=new_id(),
                    session_id=session["id"],
                    profile_id=profile_id,
                    kind="attempt",
                    problem_id=doc["problem_id"],
                    payload_json="{}",
                    occurred_at=now.isoformat(),
                    received_at=now.isoformat(),
                )
            )

    with engine.connect() as conn:
        attempted = learning_progress.attempted_lesson_counts(conn, BOOK_2020, profile_id)
        visible = _visible_counts(conn, BOOK_2020)
    assert attempted == visible


def test_lesson_problems_child_view_shape(client: TestClient, engine: Engine) -> None:
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    resp = client.get(f"{API}/lessons/{BOOK_2020}/{UNIT}/{LESSON}")
    assert resp.status_code == 200
    problems = resp.json()
    assert len(problems) == 1
    assert "answer" not in json.dumps(problems[0])  # AD-5: no Answer Key ever reaches this view


def test_lesson_problems_unknown_lesson_is_empty(client: TestClient, engine: Engine) -> None:
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    resp = client.get(f"{API}/lessons/{BOOK_2020}/no-such-unit/no-such-lesson")
    assert resp.status_code == 200
    assert resp.json() == []


# --- Home resolution ----------------------------------------------------------------


def test_home_resolves_first_visible_lesson(client: TestClient, engine: Engine) -> None:
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))

    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["grade"] == 1
    assert body["lesson"] == {
        "book_id": BOOK_2020,
        "book_title_vi": "Toán 1 – 2020",
        "unit_key": UNIT,
        "lesson_key": LESSON,
        "lesson_label": "Tiết 2",
        "lesson_title": "",
    }


def test_home_skips_an_earlier_book_with_nothing_visible(
    client: TestClient, engine: Engine
) -> None:
    """Two Books of the same Grade: the earlier one (by `list_books()` order -- "2020"
    sorts before "2024-25") has a Lesson but no visible Problem (all hidden); "Học tiếp"
    must skip straight to the later Book's visible Lesson, not stop at the empty one."""
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    hidden_only = make_doc(BOOK_2020, "bai-1")
    Pub(engine, BOOK_2020, "2020", 1)(hidden_only)
    with engine.begin() as conn:
        review.set_hidden(conn, hidden_only["problem_id"], True)
    Pub(engine, BOOK_2024, "2024-25", 1)(make_doc(BOOK_2024, "bai-1"))

    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    lesson = resp.json()["lesson"]
    assert lesson is not None
    assert lesson["book_id"] == BOOK_2024


def test_home_nothing_visible_yet_is_a_friendly_null_not_a_crash(client: TestClient) -> None:
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    assert resp.json() == {
        "profile_id": profile_id,
        "grade": 1,
        "lesson": None,
        "continue_session": None,
        "total_stars": 0,
        "streak": 0,
    }


def test_home_unknown_profile_404(client: TestClient) -> None:
    resp = client.get(f"{API}/home/no-such-profile")
    _envelope(resp, 404, "PROFILE_NOT_FOUND")


# --- "Tiếp tục" continue-session resolution (Story 2.11) ---------------------------


def test_home_no_continue_session_when_none_started(client: TestClient) -> None:
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["continue_session"] is None


def test_home_continue_session_for_an_unfinished_session(
    client: TestClient, engine: Engine
) -> None:
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    session = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()

    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["continue_session"] == {"session_id": session["id"]}


def test_home_no_continue_session_once_completed(client: TestClient, engine: Engine) -> None:
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    session = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()
    resp = client.post(
        f"/api/v1/sessions/{session['id']}/events",
        json={
            "profile_id": profile_id,
            "events": [
                {
                    "id": "018e6f1a-0000-7000-8000-000000000001",
                    "kind": "session_completed",
                    "problem_id": None,
                    "payload": {},
                    "occurred_at": "2026-09-29T10:00:00+00:00",
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["continue_session"] is None


def test_home_continue_session_excludes_replay_mode(client: TestClient, engine: Engine) -> None:
    """A `replay`-mode Session ("Luyện lại bài sai") left unfinished must NOT surface as
    "Tiếp tục" -- it is a practice loop over already-seen wrong Problems, not something to
    resume the way an interrupted regular Session is (this story's frozen Boundaries)."""
    profile_id = client.post("/api/v1/setup", json=SETUP).json()["id"]
    Pub(engine, BOOK_2020, "2020", 1)(make_doc(BOOK_2020, "bai-1"))
    source = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "lesson", "book_id": BOOK_2020, "unit_key": UNIT, "lesson_key": LESSON},
        },
    ).json()
    # Complete the source Session first, and give it one wrong attempt so `ReplayRef`
    # resolves to a non-empty Problem set.
    from hoctap.ids import new_id, utc_now
    from hoctap.learning.models import progress_events

    with engine.begin() as conn:
        now = utc_now()
        conn.execute(
            progress_events.insert().values(
                id=new_id(),
                session_id=source["id"],
                profile_id=profile_id,
                kind="attempt",
                problem_id=source["problem_ids"][0],
                payload_json='{"correct": false, "part_key": "a"}',
                occurred_at=now.isoformat(),
                received_at=now.isoformat(),
            )
        )
    client.post(
        f"/api/v1/sessions/{source['id']}/events",
        json={
            "profile_id": profile_id,
            "events": [
                {
                    "id": "018e6f1a-0000-7000-8000-000000000002",
                    "kind": "session_completed",
                    "problem_id": None,
                    "payload": {},
                    "occurred_at": "2026-09-29T10:00:00+00:00",
                }
            ],
        },
    )

    replay = client.post(
        "/api/v1/sessions",
        json={
            "profile_id": profile_id,
            "ref": {"kind": "replay", "source_session_id": source["id"]},
            "mode": "replay",
        },
    )
    assert replay.status_code == 201, replay.text

    resp = client.get(f"{API}/home/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["continue_session"] is None
