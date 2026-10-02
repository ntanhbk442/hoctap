"""Story 3.1: Stars (`progress_stars`, `compute_problem_stars()`/`maybe_award_stars()`)
and the Home/Session-summary surfacing of them. One test (or group) per row of the I/O
matrix.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

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
from hoctap.learning.models import progress_stars
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-5", "tiet-2"
SESSIONS_API = "/api/v1/sessions"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


def make_doc(label: str) -> dict[str, Any]:
    """A 2-Part `number_input` Problem (the fixture's own `a`/`b` Parts) -- the I/O
    matrix's "2-Part Problem, both correct first try" row."""
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


def _lesson_ref() -> dict[str, str]:
    return {"kind": "lesson", "book_id": BOOK, "unit_key": UNIT, "lesson_key": LESSON}


def _start(client: TestClient, profile_id: str, mode: str = "practice") -> dict[str, Any]:
    resp = client.post(
        SESSIONS_API, json={"profile_id": profile_id, "ref": _lesson_ref(), "mode": mode}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post(client: TestClient, session_id: str, profile_id: str, *events: dict[str, Any]):
    return client.post(
        f"{SESSIONS_API}/{session_id}/events",
        json={"profile_id": profile_id, "events": list(events)},
    )


def _attempt(problem_id: str, part_key: str, value: Any, occurred_at: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "attempt",
        "problem_id": problem_id,
        "payload": {"part_key": part_key, "value": value},
        "occurred_at": occurred_at,
    }


def _self_marked(problem_id: str, correct: bool, occurred_at: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "self_marked",
        "problem_id": problem_id,
        "payload": {"correct": correct},
        "occurred_at": occurred_at,
    }


def _completed(occurred_at: str = "2026-09-29T10:00:00+00:00") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "session_completed",
        "problem_id": None,
        "payload": {},
        "occurred_at": occurred_at,
    }


def _stars_rows(engine: Engine, session_id: str) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(select(progress_stars).where(progress_stars.c.session_id == session_id))
        )


# --- Per-Problem 3/1/0 computation ----------------------------------------------------


def test_both_parts_first_try_correct_3_stars(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
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
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].problem_id == doc["problem_id"]
    assert rows[0].stars == 3


def test_hint_needed_one_part_no_solution_shown_1_star(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    # Part "a": wrong then correct (1 wrong attempt -> Hint, never a Solution).
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    # Part "b": correct first try.
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:02+00:00"
        ),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 1


def test_solution_shown_any_part_0_stars(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    # Part "a": two wrong attempts (2nd wrong releases the Solution) then correct.
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "9"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "8"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:02+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:03+00:00"
        ),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 0


def test_fallback_self_marked_dung_1_star(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(
        client,
        session["id"],
        profile_id,
        _self_marked(doc["problem_id"], True, "2026-09-29T10:00:00+00:00"),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 1


def test_fallback_self_marked_chua_dung_0_stars_row_written(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """Implementer's call (documented, see `learning.scoring`'s module docstring): a
    `fallback` self-marked "chưa đúng" writes a `0`-Star row, it does not skip the row
    entirely."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(
        client,
        session["id"],
        profile_id,
        _self_marked(doc["problem_id"], False, "2026-09-29T10:00:00+00:00"),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 0


# --- Mode gate -------------------------------------------------------------------------


def test_replay_mode_session_awards_no_stars(
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

    replay_resp = client.post(
        SESSIONS_API,
        json={
            "profile_id": profile_id,
            "ref": {"kind": "replay", "source_session_id": source["id"]},
            "mode": "replay",
        },
    )
    assert replay_resp.status_code == 201, replay_resp.text
    replay = replay_resp.json()
    _post(
        client,
        replay["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T11:00:00+00:00"
        ),
    )
    _post(
        client,
        replay["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T11:00:01+00:00"
        ),
    )
    assert _stars_rows(engine, replay["id"]) == []


# --- Review Triage Log #4 (2026-10-01): corrected self_marked updates the Star row -----


def test_corrected_self_mark_updates_existing_star_row(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    """A second, later `self_marked` for the same fallback Problem+Session, with a
    DIFFERENT verdict, updates the existing `progress_stars` row in place (same row id,
    new `stars`) rather than permanently freezing the first verdict -- matching
    `_fallback_stars()`'s own docstring claim that it reads the LATEST `self_marked`
    event."""
    doc = make_fallback_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(
        client,
        session["id"],
        profile_id,
        _self_marked(doc["problem_id"], False, "2026-09-29T10:00:00+00:00"),
    )
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 0
    first_id = rows[0].id

    _post(
        client,
        session["id"],
        profile_id,
        _self_marked(doc["problem_id"], True, "2026-09-29T10:00:01+00:00"),
    )
    rows2 = _stars_rows(engine, session["id"])
    assert len(rows2) == 1
    assert rows2[0].id == first_id  # same row, updated, not a duplicate
    assert rows2[0].stars == 1


# --- Review Triage Log #2 (2026-10-01): undetermined Star outcome at session_completed --


def test_session_completed_logs_when_a_problem_has_no_determinable_star_outcome(
    client: TestClient, engine: Engine, profile_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A practice-mode Session completed while one Problem's Star outcome is still
    undeterminable (here: only one of its two graded Parts was ever attempted, simulating
    a lost/dropped `attempt` event) is still accepted (201) -- Story 2.10's own
    `wrong_problem_ids` semantics already treat a never-attempted Problem as a legitimate,
    expected state -- but a WARNING is logged naming the Session and the Problem, so the
    anomaly is detectable server-side."""
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    # Only Part "a" ever gets an attempt; Part "b" never does, so compute_problem_stars()
    # stays None for this Problem in this Session.
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    with caplog.at_level("WARNING"):
        resp = _post(client, session["id"], profile_id, _completed())
    assert resp.status_code == 201, resp.text
    assert _stars_rows(engine, session["id"]) == []
    assert any(
        doc["problem_id"] in r.getMessage() and "session_completed" in r.getMessage()
        for r in caplog.records
    )


def test_session_completed_no_warning_when_every_problem_is_resolved(
    client: TestClient, engine: Engine, profile_id: str, caplog: pytest.LogCaptureFixture
) -> None:
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
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    with caplog.at_level("WARNING"):
        resp = _post(client, session["id"], profile_id, _completed())
    assert resp.status_code == 201, resp.text
    assert not any("no determinable Star outcome" in r.getMessage() for r in caplog.records)


# --- Idempotency -------------------------------------------------------------------------


def test_resent_resolving_event_no_duplicate_row(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
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
    resolving = _attempt(
        doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
    )
    _post(client, session["id"], profile_id, resolving)
    rows = _stars_rows(engine, session["id"])
    assert len(rows) == 1
    assert rows[0].stars == 3

    # A literal resend of the same event id (already-stored fast path) never re-derives
    # or re-inserts.
    resp = _post(client, session["id"], profile_id, resolving)
    assert resp.status_code == 201, resp.text
    rows_after = _stars_rows(engine, session["id"])
    assert len(rows_after) == 1
    assert rows_after[0].id == rows[0].id
    assert rows_after[0].stars == 3


# --- Session summary (`stars_earned`) ---------------------------------------------------


def test_session_summary_stars_earned_matches_sum_of_own_rows(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    graded = make_doc("bai-1")
    fallback = make_fallback_doc("bai-2")
    Pub(engine)(graded, fallback)
    session = _start(client, profile_id)
    # graded Problem: 3 Stars (both Parts correct first try).
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            graded["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        session["id"],
        profile_id,
        _attempt(
            graded["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    # fallback Problem: self-marked "chưa đúng" -> 0 Stars.
    _post(
        client,
        session["id"],
        profile_id,
        _self_marked(fallback["problem_id"], False, "2026-09-29T10:00:02+00:00"),
    )
    _post(client, session["id"], profile_id, _completed())

    resp = client.get(f"{SESSIONS_API}/{session['id']}/summary", params={"profile_id": profile_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stars_earned"] == 3


# --- Home: total Stars + Streak ---------------------------------------------------------


def test_home_total_stars_sums_across_sessions(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    doc2 = make_doc("bai-2")
    Pub(engine)(doc, doc2)

    # Fixed clock matching the hardcoded `2026-09-29` `occurred_at` timestamps below, so
    # the Home endpoint's `compute_streak()` "today" lines up with the completed Sessions'
    # local day regardless of the real wall-clock date.
    client.app.state.clock = lambda: datetime(2026, 9, 29, 12, 0, tzinfo=UTC)  # type: ignore[attr-defined]

    session_a = _start(client, profile_id)
    _post(
        client,
        session_a["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T10:00:00+00:00"
        ),
    )
    _post(
        client,
        session_a["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T10:00:01+00:00"
        ),
    )
    _post(client, session_a["id"], profile_id, _completed("2026-09-29T10:00:02+00:00"))

    session_b = _start(client, profile_id)
    _post(
        client,
        session_b["id"],
        profile_id,
        _attempt(
            doc2["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-29T11:00:00+00:00"
        ),
    )
    _post(
        client,
        session_b["id"],
        profile_id,
        _attempt(
            doc2["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-29T11:00:01+00:00"
        ),
    )
    _post(client, session_b["id"], profile_id, _completed("2026-09-29T11:00:02+00:00"))

    home = client.get(f"/api/v1/library/home/{profile_id}").json()
    assert home["total_stars"] == 6
    assert home["streak"] >= 1


def test_home_streak_matches_compute_streak(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(client, session["id"], profile_id, _completed())

    summary_streak = client.get(
        f"{SESSIONS_API}/{session['id']}/summary", params={"profile_id": profile_id}
    ).json()["streak"]
    home_streak = client.get(f"/api/v1/library/home/{profile_id}").json()["streak"]
    assert summary_streak == home_streak


def test_star_awarding_modes_excludes_exam() -> None:
    """Story 8.1: `STAR_AWARDING_MODES` is an explicit allowlist (`practice`/`retry`/
    `concept`) -- `exam` is excluded simply by never being added to it, same as `quiz`
    (awarded separately, via `award_quiz_stars()`) and `replay` already are. This test pins
    that fact so a future edit can't accidentally add `exam` to the allowlist without a
    test noticing."""
    from hoctap.learning.scoring import STAR_AWARDING_MODES

    assert STAR_AWARDING_MODES == frozenset({"practice", "retry", "concept"})
    assert "exam" not in STAR_AWARDING_MODES
