"""Story 2.2: `builder.stages.speak` (`hoctap build speak-missing`).

One test per row of the I/O matrix, using `FakeTtsEngine` — the real engines are never
called (see `test_tts_client.py`). The database/publish setup mirrors `test_review.py`'s
`Pub` helper: `content.catalog.service.publish_problems()` is how the builder itself gets a
Problem into `content_catalog_problems`.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

import hoctap.cli as cli
from hoctap.builder.stages import speak
from hoctap.builder.tts_client import FakeTtsEngine, TtsError
from hoctap.config import ConfigError, load_settings
from hoctap.content.catalog.service import (
    BookRow,
    LessonRow,
    ProblemInput,
    UnitRow,
    publish_problems,
    upsert_books,
)
from hoctap.content.review.service import record_concept_proposals
from hoctap.content.speech import problem_speech_refs, speech_key
from hoctap.db.engine import create_db_engine, run_migrations

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"
BOOK, UNIT, LESSON = "toan1-2020-q1", "tuan-5", "tiet-2"
VOICE = "vi-VN-HoaiMyNeural"


def make_doc(label: str = "bai-1") -> dict[str, Any]:
    doc = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    doc.update(
        problem_id=f"{BOOK}.{UNIT}.{LESSON}.{label}",
        problem_label=label,
        concept_ids=[],
        concept_proposals=[],
    )
    return doc


def publish(engine: Engine, *docs: dict[str, Any]) -> None:
    with engine.begin() as conn:
        upsert_books(
            conn, [BookRow(BOOK, "2020", 1, 1, "Toán 1 – Quyển 1 (2020)", "x.pdf", 10, 1, "f")]
        )
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
        record_concept_proposals(conn, 1, {d["problem_id"]: [] for d in docs})


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def engine(data_dir: Path) -> Engine:
    eng = create_db_engine(data_dir / "hoctap.db")
    run_migrations(eng)
    return eng


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A fake repo root with its own phrase catalogue, isolated from the real one."""
    root = tmp_path / "repo"
    phrases_dir = root / "frontend" / "src" / "audio"
    phrases_dir.mkdir(parents=True)
    (phrases_dir / "phrases.vi.json").write_text(
        json.dumps({"home_continue": "Tiếp tục", "praise_1": "Giỏi quá!"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def problem_texts() -> set[str]:
    from hoctap.content.schema import ProblemDoc

    doc = ProblemDoc.model_validate(make_doc())
    return {r.text for r in problem_speech_refs(doc, VOICE)}


PHRASE_TEXTS = {"Tiếp tục", "Giỏi quá!"}


# --------------------------------------------------------------------------- collect_refs


def test_collect_refs_covers_problems_and_phrases(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    assert set(refs.values()) == problem_texts() | PHRASE_TEXTS
    for key, text in refs.items():
        assert key == speech_key(text, VOICE)


def test_phrase_with_no_problem_origin_still_gets_a_key(
    engine: Engine, repo_root: Path
) -> None:
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    assert "Tiếp tục" in refs.values()


def test_collect_refs_stores_normalised_not_raw_text(engine: Engine, repo_root: Path) -> None:
    """Regression test for the critical bug where the raw field (still containing
    `\\overline{...}`/`\\frac{...}`/literal operators) was stored and sent to the TTS
    engine, instead of `speech_text()`'s normalised Vietnamese. This fixture's part 'a'
    solution.final is the raw string "3 + 2 = 5"."""
    publish(engine, make_doc())
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    assert "3 cộng 2 bằng 5" in refs.values()
    assert "3 + 2 = 5" not in refs.values()


def test_collect_refs_warns_on_speech_key_collision(engine: Engine, repo_root: Path) -> None:
    with pytest.warns(RuntimeWarning, match="speech_key collision"):
        refs: dict[str, str] = {}
        speak._add_ref(refs, "samekey", "text one")
        speak._add_ref(refs, "samekey", "text two")
    # the same key with the same text again must never warn
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        speak._add_ref(refs, "samekey", "text two")


# --------------------------------------------------------------------------- run_speak


def test_nothing_missing_means_zero_calls(engine: Engine, repo_root: Path, data_dir: Path) -> None:
    publish(engine, make_doc())
    fake = FakeTtsEngine()
    first = speak.run_speak(engine, data_dir, repo_root, fake, VOICE)
    assert first.synthesized > 0
    fake2 = FakeTtsEngine()
    second = speak.run_speak(engine, data_dir, repo_root, fake2, VOICE)
    assert fake2.calls == []
    assert second.synthesized == 0
    assert second.skipped == first.synthesized
    assert second.failed == {}


def test_some_missing_synthesizes_exactly_those(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    expected = problem_texts() | PHRASE_TEXTS
    fake = FakeTtsEngine()
    report = speak.run_speak(engine, data_dir, repo_root, fake, VOICE)
    assert report.synthesized == len(expected)
    assert {text for text, _ in fake.calls} == expected
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    for key in refs:
        assert speak.speech_path(data_dir, key).is_file()


def test_build_jobs_row_written_as_audit_trail(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    """The module docstring's audit-trail claim: after a successful synthesis, a `done`
    `build_jobs` row exists for the key (even though resume/skip itself is file-existence
    based, not this row)."""
    from hoctap.builder import jobs_store

    publish(engine, make_doc())
    report = speak.run_speak(engine, data_dir, repo_root, FakeTtsEngine(), VOICE)
    assert report.synthesized > 0
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
        for key in refs:
            job = jobs_store.find_done(conn, speak._job_ref(key), speak.STAGE, key)
            assert job is not None
            assert job.status == "done"
            assert job.output is not None and "path" in job.output


def test_file_deleted_but_job_done_is_resynthesized(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    fake = FakeTtsEngine()
    speak.run_speak(engine, data_dir, repo_root, fake, VOICE)
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    one_key = next(iter(refs))
    path = speak.speech_path(data_dir, one_key)
    assert path.is_file()
    path.unlink()  # simulate the file having been deleted, job row still "done"
    fake2 = FakeTtsEngine()
    report = speak.run_speak(engine, data_dir, repo_root, fake2, VOICE)
    assert report.synthesized == 1
    assert path.is_file()


def test_edit_then_rerun_synthesizes_exactly_one_new_key(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    speak.run_speak(engine, data_dir, repo_root, FakeTtsEngine(), VOICE)
    with engine.connect() as conn:
        before = speak.collect_refs(conn, repo_root, VOICE)
    old_key = speech_key("Bắt đầu từ 3, đếm thêm 2: bốn, năm.", VOICE)
    old_path = speak.speech_path(data_dir, old_key)
    assert old_path.is_file()

    edited = make_doc()
    edited["parts"][0]["solution"]["steps"] = ["Đếm thêm: một, hai, xong rồi!"]
    publish(engine, edited)

    with engine.connect() as conn:
        after = speak.collect_refs(conn, repo_root, VOICE)
    new_keys = set(after) - set(before)
    assert len(new_keys) == 1

    fake = FakeTtsEngine()
    report = speak.run_speak(engine, data_dir, repo_root, fake, VOICE)
    assert report.synthesized == 1
    assert fake.calls == [("Đếm thêm: một, hai, xong rồi!", VOICE)]
    assert old_path.is_file()  # orphaned, not deleted


def test_dry_run_reports_without_synthesizing(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    expected = problem_texts() | PHRASE_TEXTS
    report = speak.run_speak(engine, data_dir, repo_root, None, VOICE, dry_run=True)
    assert report.synthesized == 0
    assert len(report.planned) == len(expected)
    with engine.connect() as conn:
        refs = speak.collect_refs(conn, repo_root, VOICE)
    for key in refs:
        assert not speak.speech_path(data_dir, key).is_file()


def test_engine_failure_recorded_and_run_continues(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    failing_text = next(iter(problem_texts()))

    def responder(text: str, voice_id: str) -> bytes:
        if text == failing_text:
            raise TtsError("lỗi giả lập / simulated failure")
        return b"FAKE"

    fake = FakeTtsEngine(responder=responder)
    report = speak.run_speak(engine, data_dir, repo_root, fake, VOICE)
    failed_key = speech_key(failing_text, VOICE)
    assert report.failed[failed_key] == "lỗi giả lập / simulated failure"
    # every other key still got synthesised
    assert report.synthesized == len(problem_texts() | PHRASE_TEXTS) - 1


def test_spend_cap_stops_starting_new_calls(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    fake = FakeTtsEngine()
    report = speak.run_speak(
        engine, data_dir, repo_root, fake, VOICE, max_total_usd=0.0, cost_per_char_usd=0.01
    )
    assert report.synthesized == 0
    assert len(report.failed) == len(problem_texts() | PHRASE_TEXTS)
    assert all(why == speak.BUDGET_REACHED for why in report.failed.values())


def test_free_engine_ignores_budget_cap_when_cost_per_char_is_zero(
    engine: Engine, repo_root: Path, data_dir: Path
) -> None:
    publish(engine, make_doc())
    fake = FakeTtsEngine()
    report = speak.run_speak(
        engine, data_dir, repo_root, fake, VOICE, max_total_usd=0.0, cost_per_char_usd=0.0
    )
    assert report.failed == {}
    assert report.synthesized == len(problem_texts() | PHRASE_TEXTS)


# --------------------------------------------------------------------------- config


def test_config_rejects_unknown_tts_engine(tmp_path: Path) -> None:
    config = tmp_path / "hoctap.toml"
    config.write_text('[build]\ntts_engine = "not-a-real-engine"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(config, env={})


def test_config_defaults() -> None:
    settings = load_settings(Path("/nonexistent-hoctap.toml"), env={})
    assert settings.tts_engine == "edge-tts"
    assert settings.tts_voice_id
    assert settings.tts_max_total_usd > 0


# --------------------------------------------------------------------------- CLI


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> Path:
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(data_dir))
    monkeypatch.delenv("HOCTAP_CONFIG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    eng = create_db_engine(data_dir / "hoctap.db")
    run_migrations(eng)
    publish(eng, make_doc())
    eng.dispose()
    return data_dir


def test_cli_dry_run_sends_nothing(monkeypatch: pytest.MonkeyPatch, cli_env: Path) -> None:
    calls: list[FakeTtsEngine] = []

    def never_called(settings):  # noqa: ANN001
        raise AssertionError("the real engine must never be constructed on --dry-run")

    monkeypatch.setattr(cli, "_tts_client", never_called)
    code = cli.main(["build", "speak-missing", "--dry-run"])
    assert code == 0
    assert calls == []


def test_cli_refuses_cloud_engine_without_yes_spend(
    monkeypatch: pytest.MonkeyPatch, cli_env: Path, tmp_path: Path
) -> None:
    config = tmp_path / "hoctap.toml"
    config.write_text('[build]\ntts_engine = "google-tts"\n', encoding="utf-8")
    monkeypatch.setenv("HOCTAP_CONFIG", str(config))

    def never_called(settings):  # noqa: ANN001
        raise AssertionError("must not construct the engine when spend is refused")

    monkeypatch.setattr(cli, "_tts_client", never_called)
    code = cli.main(["build", "speak-missing"])
    assert code == 2


def test_cli_edge_tts_proceeds_without_yes_spend(
    monkeypatch: pytest.MonkeyPatch, cli_env: Path
) -> None:
    fake = FakeTtsEngine()
    monkeypatch.setattr(cli, "_tts_client", lambda settings: fake)
    code = cli.main(["build", "speak-missing"])
    assert code == 0
    assert len(fake.calls) > 0
