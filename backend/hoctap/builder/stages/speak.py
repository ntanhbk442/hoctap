"""`speak`: the mp3 of every currently-referenced `speech_key` (AD-8).

Unlike the page-addressed stages (`crop`, `publish`, ...), this stage is content-addressed:
one `build_jobs` row per `speech_key` (`page_ref` `speech#{speech_key}`, `input_hash` the
key itself), not per page. The key already commits to the spoken text and the voice
(`content.speech.speech_key()`), so editing a Problem's text or switching voice produces a
new key automatically; only that new key is missing, so only it gets synthesised, and the
old key's file is simply left in place (orphaned — cleanup is deferred, see
`deferred-work.md`).

The file on disk is the only source of truth for "already done": a key whose file exists is
skipped without a TTS call, even if it has no job row (e.g. a fresh checkout of
`data/assets/audio`); a key whose file is missing is re-synthesised even if its job row
says `done` (e.g. the file was deleted). The `build_jobs` row is written only as an audit
trail after a successful synthesis.

Every currently-published (not retired) Problem's referenced text
(`content.speech.problem_speech_refs`) and every phrase of the UI phrase catalogue
(`frontend/src/audio/phrases.vi.json`) are scanned. Concept Guides have no speakable text
fields in `content.schema` yet, so they are not covered (deferred, see `deferred-work.md`).

A single engine failure is recorded in `Report.failed` and does not stop the rest.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, Engine

from hoctap.builder import jobs_store
from hoctap.builder.tts_client import TtsEngine, TtsError
from hoctap.content import effective
from hoctap.content.speech import problem_speech_refs, speech_key, speech_path, speech_text

STAGE = "speak"
PHRASES_REL_PATH = Path("frontend") / "src" / "audio" / "phrases.vi.json"

# Bilingual, matching `cli.py`'s `_SPEND_REFUSED` style: printed for a key skipped because
# this run's spend cap was reached (only the cloud engine has a non-zero cost per char).
BUDGET_REACHED = "hết ngân sách cho lượt chạy này / this run's spend cap was reached"


def _job_ref(key: str) -> str:
    return f"speech#{key}"


def load_phrases(repo_root: Path) -> dict[str, str]:
    """The flat `{key: text}` UI-phrase catalogue; `{}` if the file does not exist yet."""
    path = repo_root / PHRASES_REL_PATH
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def _add_ref(refs: dict[str, str], key: str, text: str) -> None:
    """Sets `refs[key] = text`, warning if the key was already mapped to a *different*
    text. Two different keys always meaning different text is the whole point of a
    content-addressed hash; seeing this warning means `speech_key()`/`speech_text()` have a
    bug (a real sha256 collision here is astronomically unlikely), not that anything is
    actually wrong with the two texts themselves."""
    existing = refs.get(key)
    if existing is not None and existing != text:
        warnings.warn(
            f"speech_key collision: {key!r} maps to two different texts "
            f"({existing!r} vs {text!r}); this points at a speech_text()/speech_key() bug",
            RuntimeWarning,
            stacklevel=2,
        )
    refs[key] = text


def collect_refs(conn: Connection, repo_root: Path, voice_id: str) -> dict[str, str]:
    """Every currently-referenced `speech_key -> NORMALISED text` (see
    `content.speech.SpeechRef`), across published (not retired) Problems and the phrase
    catalogue — this is the text actually sent to the TTS engine, not the raw field."""
    refs: dict[str, str] = {}
    for state in effective.load_effective(conn, include_retired=False):
        if state.doc is None:
            continue
        for ref in problem_speech_refs(state.doc, voice_id):
            _add_ref(refs, ref.speech_key, ref.text)
    for raw in load_phrases(repo_root).values():
        if not raw:
            continue
        _add_ref(refs, speech_key(raw, voice_id), speech_text(raw))
    return refs


@dataclass
class Report:
    synthesized: int = 0  # files written now
    skipped: int = 0  # file already on disk
    planned: list[str] = field(default_factory=list)  # dry-run: keys that would be synthesised
    failed: dict[str, str] = field(default_factory=dict)  # speech_key -> why


def pending_keys(data_dir: Path, refs: dict[str, str]) -> list[str]:
    """The referenced keys whose file is missing, in a stable order."""
    return sorted(key for key in refs if not speech_path(data_dir, key).is_file())


def run_speak(
    engine: Engine,
    data_dir: Path,
    repo_root: Path,
    tts: TtsEngine | None,
    voice_id: str,
    *,
    dry_run: bool = False,
    max_total_usd: float | None = None,
    cost_per_char_usd: float = 0.0,
) -> Report:
    """Synthesises the mp3 of every referenced key whose file is missing.

    `tts` is only used for a key that is actually missing; pass `None` for `dry_run` (or
    when nothing is missing). `max_total_usd` stops starting new calls once this run's
    estimated spend (at `cost_per_char_usd`, 0 for edge-tts) would exceed it; the key is
    then recorded in `failed` so the run is visibly incomplete."""
    report = Report()
    with engine.connect() as conn:
        refs = collect_refs(conn, repo_root, voice_id)
    spent = 0.0
    for key in sorted(refs):
        text = refs[key]
        path = speech_path(data_dir, key)
        if path.is_file():
            report.skipped += 1
            continue
        if dry_run:
            report.planned.append(key)
            continue
        cost = cost_per_char_usd * len(text)
        if max_total_usd is not None and spent + cost > max_total_usd:
            report.failed[key] = BUDGET_REACHED
            continue
        if tts is None:
            report.failed[key] = "không có bộ máy TTS / no TTS engine available"
            continue
        try:
            audio = tts.synthesize(text, voice_id)
        except TtsError as exc:
            report.failed[key] = str(exc)
            continue
        if not audio:
            # Never write a zero-byte mp3: a later run would treat the file as done.
            report.failed[key] = "âm thanh rỗng / the engine returned empty audio"
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".mp3.tmp")
        tmp.write_bytes(audio)
        os.replace(tmp, path)
        spent += cost
        report.synthesized += 1
        with engine.begin() as write_conn:
            jobs_store.record(
                write_conn,
                _job_ref(key),
                STAGE,
                key,
                "done",
                output={"path": str(path.relative_to(data_dir))},
            )
    return report


def describe(report: Report) -> list[str]:
    """The report lines printed by the CLI."""
    lines = [
        f"speak: {report.synthesized} synthesised, {report.skipped} unchanged, "
        f"{len(report.failed)} failed"
    ]
    if report.planned:
        lines.append(f"would synthesise {len(report.planned)} key(s) (--dry-run)")
    return lines


def describe_failures(report: Report) -> list[str]:
    if not report.failed:
        return []
    lines = [
        f"Cảnh báo / Warning: {len(report.failed)} âm thanh không tạo được / audio "
        "clip(s) failed:"
    ]
    lines += [f"  - {key}: {why}" for key, why in sorted(report.failed.items())]
    return lines
