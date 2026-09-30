"""Story 3.2: Badges (`progress_badges`, `maybe_award_badges()`) and the Session-summary/
Home/"Huy hiệu của em" surfacing of them. One test (or group) per row of the I/O matrix.

Direct-engine tests (no HTTP client) follow the same pattern Story 2.10's own streak
tests use (`test_sessions.py::test_streak_consecutive_days_and_a_gap_day` et al.) --
building `progress_sessions`/`progress_stars` rows straight into an in-memory engine and
calling `learning.badges` functions directly, since setting up a real 7-day streak or a
98-Stars total through the real grading pipeline would need dozens of Problems/attempts
for no additional coverage. API-level tests cover the endpoints themselves
(`GET /sessions/{id}/summary`, `GET /library/home/{profile_id}`,
`GET /profiles/{id}/badges`).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.engine import URL

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
from hoctap.db.engine import run_migrations
from hoctap.learning import badges as badges_service
from hoctap.learning.models import progress_badges, progress_sessions, progress_stars
from hoctap.parent import service as parent_service

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK = "toan1-2020-q1"
UNIT, LESSON = "tuan-5", "tiet-2"
SESSIONS_API = "/api/v1/sessions"
LIBRARY_API = "/api/v1/library"
PROFILES_API = "/api/v1/profiles"
SETUP = {
    "pin": "1234",
    "pin_confirm": "1234",
    "profile": {"name": "Bin", "avatar": "cat", "grade": 1},
}


# --- Direct-engine helpers ---------------------------------------------------------------


def _bare_engine() -> Engine:
    eng = create_engine(URL.create("sqlite", database=":memory:"))
    run_migrations(eng)
    return eng


def _session_row(
    session_id: str, profile_id: str, day: str, mode: str = "practice"
) -> dict[str, Any]:
    return dict(
        id=session_id,
        profile_id=profile_id,
        ref_kind="lesson",
        ref_key="lesson:x:y:z",
        mode=mode,
        problem_ids_json="[]",
        chunk_size=10,
        started_at=f"{day}T03:00:00+00:00",
        completed_at=f"{day}T03:00:00+00:00",
    )


def _stars_row(session_id: str, profile_id: str, problem_id: str, stars: int) -> dict[str, Any]:
    return dict(
        id=str(uuid.uuid7()),
        session_id=session_id,
        profile_id=profile_id,
        problem_id=problem_id,
        stars=stars,
        awarded_at="2026-09-29T03:00:00+00:00",
    )


def _badge_keys(conn: Any) -> set[str]:
    return {row.badge_key for row in conn.execute(select(progress_badges.c.badge_key))}


# --- streak7 -------------------------------------------------------------------------------


def test_streak7_awarded_on_crossing_from_6_to_7() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        for i, day in enumerate(f"2026-09-0{d}" for d in range(1, 8)):
            conn.execute(
                progress_sessions.insert().values(**_session_row(f"s{i}", profile_id, day))
            )
    with eng.begin() as conn:
        newly = badges_service.maybe_award_badges(
            conn, "2026-09-07T03:00:00+00:00", "s6", profile_id, "practice"
        )
    assert newly == ["week1", "streak7"]
    with eng.connect() as conn:
        assert _badge_keys(conn) == {"week1", "streak7"}


def test_streak7_already_earned_no_duplicate_on_later_session() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        for i, day in enumerate(f"2026-09-0{d}" for d in range(1, 8)):
            conn.execute(
                progress_sessions.insert().values(**_session_row(f"s{i}", profile_id, day))
            )
        conn.execute(
            progress_sessions.insert().values(**_session_row("s8", profile_id, "2026-09-08"))
        )
    with eng.begin() as conn:
        first = badges_service.maybe_award_badges(
            conn, "2026-09-07T03:00:00+00:00", "s6", profile_id, "practice"
        )
    assert first == ["week1", "streak7"]
    with eng.begin() as conn:
        second = badges_service.maybe_award_badges(
            conn, "2026-09-08T03:00:00+00:00", "s8", profile_id, "practice"
        )
    assert second == []
    with eng.connect() as conn:
        rows = list(
            conn.execute(select(progress_badges).where(progress_badges.c.badge_key == "streak7"))
        )
    assert len(rows) == 1


# --- stars100 ------------------------------------------------------------------------------


def test_stars100_awarded_on_crossing_from_98_to_101() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(**_session_row("s0", profile_id, "2026-09-01"))
        )
        # 32*3 + 2*1 = 98 Stars.
        for i in range(32):
            conn.execute(
                progress_stars.insert().values(**_stars_row("s0", profile_id, f"pr-{i}", 3))
            )
        for i in range(2):
            conn.execute(
                progress_stars.insert().values(**_stars_row("s0", profile_id, f"pr-hint-{i}", 1))
            )
    with eng.begin() as conn:
        from hoctap.learning.scoring import total_stars

        assert total_stars(conn, profile_id) == 98
        # The 1 Problem (3 Stars) whose award crosses 98 -> 101.
        conn.execute(
            progress_stars.insert().values(**_stars_row("s0", profile_id, "pr-crossing", 3))
        )
        newly = badges_service.maybe_award_badges(
            conn, "2026-09-01T04:00:00+00:00", "s0", profile_id, "practice"
        )
    assert newly == ["week1", "stars100"]
    with eng.connect() as conn:
        assert _badge_keys(conn) == {"week1", "stars100"}


def test_stars100_already_earned_no_duplicate() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(**_session_row("s0", profile_id, "2026-09-01"))
        )
        for i in range(40):
            conn.execute(
                progress_stars.insert().values(**_stars_row("s0", profile_id, f"pr-{i}", 3))
            )
    with eng.begin() as conn:
        first = badges_service.maybe_award_badges(
            conn, "2026-09-01T04:00:00+00:00", "s0", profile_id, "practice"
        )
    assert first == ["week1", "stars100"]
    with eng.begin() as conn:
        second = badges_service.maybe_award_badges(
            conn, "2026-09-01T05:00:00+00:00", "s0", profile_id, "practice"
        )
    assert second == []
    with eng.connect() as conn:
        rows = list(
            conn.execute(select(progress_badges).where(progress_badges.c.badge_key == "stars100"))
        )
    assert len(rows) == 1


# --- week1 ---------------------------------------------------------------------------------


def test_week1_awarded_on_first_ever_completed_session() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(**_session_row("s0", profile_id, "2026-09-01"))
        )
    with eng.begin() as conn:
        newly = badges_service.maybe_award_badges(
            conn, "2026-09-01T04:00:00+00:00", "s0", profile_id, "practice"
        )
    assert newly == ["week1"]
    with eng.connect() as conn:
        assert _badge_keys(conn) == {"week1"}


def test_week1_second_completed_session_no_duplicate() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(**_session_row("s0", profile_id, "2026-09-01"))
        )
        conn.execute(
            progress_sessions.insert().values(**_session_row("s1", profile_id, "2026-09-02"))
        )
    with eng.begin() as conn:
        first = badges_service.maybe_award_badges(
            conn, "2026-09-01T04:00:00+00:00", "s0", profile_id, "practice"
        )
    assert first == ["week1"]
    with eng.begin() as conn:
        second = badges_service.maybe_award_badges(
            conn, "2026-09-02T04:00:00+00:00", "s1", profile_id, "practice"
        )
    assert second == []
    with eng.connect() as conn:
        rows = list(
            conn.execute(select(progress_badges).where(progress_badges.c.badge_key == "week1"))
        )
    assert len(rows) == 1


# --- replay mode gate ------------------------------------------------------------------------


def test_replay_mode_session_runs_no_badge_check() -> None:
    """All 3 conditions are already true (a completed Session exists, the Streak is >= 7,
    total Stars >= 100), yet calling with `mode="replay"` must write NOTHING -- matching
    `maybe_award_stars()`'s own `STAR_AWARDING_MODES` gate posture (AD-6: `replay` never
    counts toward Streak/Stars, so it must never trigger a badge check either)."""
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        for i, day in enumerate(f"2026-09-0{d}" for d in range(1, 8)):
            conn.execute(
                progress_sessions.insert().values(**_session_row(f"s{i}", profile_id, day))
            )
        for i in range(40):
            conn.execute(
                progress_stars.insert().values(**_stars_row("s0", profile_id, f"pr-{i}", 3))
            )
    with eng.begin() as conn:
        newly = badges_service.maybe_award_badges(
            conn, "2026-09-07T03:00:00+00:00", "s6", profile_id, "replay"
        )
    assert newly == []
    with eng.connect() as conn:
        assert _badge_keys(conn) == set()


# --- "Huy hiệu của em" full read --------------------------------------------------------


def test_profile_badges_read_all_three_states() -> None:
    eng = _bare_engine()
    profile_id = "p1"
    with eng.begin() as conn:
        conn.execute(
            progress_sessions.insert().values(**_session_row("s0", profile_id, "2026-09-01"))
        )
    with eng.begin() as conn:
        badges_service.maybe_award_badges(
            conn, "2026-09-01T04:00:00+00:00", "s0", profile_id, "practice"
        )
    with eng.connect() as conn:
        states = {s.badge_key: s for s in badges_service.profile_badges(conn, profile_id)}
    assert set(states) == {"week1", "streak7", "stars100"}
    assert states["week1"].earned is True
    assert states["week1"].earned_at is not None
    assert states["streak7"].earned is False
    assert states["streak7"].earned_at is None
    assert states["stars100"].earned is False
    assert states["stars100"].earned_at is None


# --- API-level: real content pipeline + endpoints ------------------------------------------


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


def _completed(occurred_at: str = "2026-09-29T10:00:00+00:00") -> dict[str, Any]:
    return {
        "id": str(uuid.uuid7()),
        "kind": "session_completed",
        "problem_id": None,
        "payload": {},
        "occurred_at": occurred_at,
    }


def test_first_completed_session_summary_carries_week1_in_new_badges(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    _post(client, session["id"], profile_id, _completed())

    resp = client.get(f"{SESSIONS_API}/{session['id']}/summary", params={"profile_id": profile_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_badges"] == ["week1"]


def test_resent_session_completed_event_does_not_duplicate_badge(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session = _start(client, profile_id)
    completed = _completed()
    resp1 = _post(client, session["id"], profile_id, completed)
    assert resp1.status_code == 201, resp1.text

    resp2 = _post(client, session["id"], profile_id, completed)
    assert resp2.status_code == 201, resp2.text

    with engine.connect() as conn:
        rows = list(
            conn.execute(select(progress_badges).where(progress_badges.c.profile_id == profile_id))
        )
    assert len(rows) == 1
    assert rows[0].badge_key == "week1"


def test_home_zero_badges_and_profile_badges_all_unearned(
    client: TestClient, profile_id: str
) -> None:
    home = client.get(f"{LIBRARY_API}/home/{profile_id}").json()
    assert home["recent_badges"] == []

    resp = client.get(f"{PROFILES_API}/{profile_id}/badges")
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert {s["badge_key"] for s in states} == {"week1", "streak7", "stars100"}
    assert all(s["earned"] is False and s["earned_at"] is None for s in states)


def test_home_recent_badges_and_huy_hieu_screen_with_two_earned(
    client: TestClient, engine: Engine, profile_id: str
) -> None:
    doc = make_doc("bai-1")
    Pub(engine)(doc)
    session1 = _start(client, profile_id)
    _post(client, session1["id"], profile_id, _completed("2026-09-01T10:00:00+00:00"))

    # Seed 98 Stars directly (bypassing the graded pipeline for test speed), then earn a
    # real 3-Star Problem via the API to cross 100 -- and check `stars100` in that
    # Session's own `new_badges`.
    with engine.begin() as conn:
        for i in range(32):
            conn.execute(
                progress_stars.insert().values(
                    **_stars_row(session1["id"], profile_id, f"pr-{i}", 3)
                )
            )
        for i in range(2):
            conn.execute(
                progress_stars.insert().values(
                    **_stars_row(session1["id"], profile_id, f"pr-hint-{i}", 1)
                )
            )

    session2 = _start(client, profile_id)
    _post(
        client,
        session2["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "a", [{"key": "s1", "value": "5"}], "2026-09-02T10:00:00+00:00"
        ),
    )
    resp = _post(
        client,
        session2["id"],
        profile_id,
        _attempt(
            doc["problem_id"], "b", [{"key": "s1", "value": "3"}], "2026-09-02T10:00:01+00:00"
        ),
    )
    assert resp.status_code == 201, resp.text
    _post(client, session2["id"], profile_id, _completed("2026-09-02T10:00:02+00:00"))

    summary2 = client.get(
        f"{SESSIONS_API}/{session2['id']}/summary", params={"profile_id": profile_id}
    ).json()
    assert summary2["new_badges"] == ["stars100"]

    home = client.get(f"{LIBRARY_API}/home/{profile_id}").json()
    # Most-recently-earned first: `stars100` (session2) before `week1` (session1).
    assert home["recent_badges"] == ["stars100", "week1"]

    states = {
        s["badge_key"]: s
        for s in client.get(f"{PROFILES_API}/{profile_id}/badges").json()
    }
    assert states["week1"]["earned"] is True
    assert states["stars100"]["earned"] is True
    assert states["streak7"]["earned"] is False
    assert states["streak7"]["earned_at"] is None


def test_recent_badges_orders_ties_by_id_desc() -> None:
    eng = _bare_engine()
    at = "2026-09-29T03:00:00+00:00"
    with eng.begin() as conn:
        for key in ("streak7", "week1", "stars100"):  # ids ascend in this insertion order
            conn.execute(
                progress_badges.insert().values(
                    id=str(uuid.uuid7()), profile_id="p1", badge_key=key, earned_at=at
                )
            )
    with eng.connect() as conn:
        assert badges_service.recent_badges(conn, "p1") == ["stars100", "week1", "streak7"]
