---
title: 'Story 2.2: Speech normaliser, TTS adapter and speak-missing'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:6ed9a57d34759019ea36053eb054213acfd03b61'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Bin can't read yet, so every Problem, Concept Guide and UI phrase needs natural
Vietnamese audio (FR-10). Nothing today normalises maths notation into speakable Vietnamese, and
there is no audio file, no TTS integration, and no build step that keeps audio in sync with edited
text (AD-8).

**Approach:** A single normaliser `content.speech.speech_text()` turns notation (`<`, `>`, `=`,
`\overline{...}`, `\frac{a}{b}`, etc.) into Vietnamese read-aloud text. Its output is hashed into a
content-addressed `speech_key` (`sha256(NFC(speech_text) + voice_id)[:16]`), which
`effective_problem()`-adjacent code computes so an edit produces a new key automatically. A new
`hoctap build speak-missing` stage (mirroring the existing `builder/stages/*` pattern: STAGE
constant, Report dataclass, resumable via `build_jobs`) walks every referenced key across Problems,
Concept Guides, and the new `frontend/src/audio/phrases.vi.json` UI-phrase catalogue, and
synthesises any file that's missing under `data/assets/audio/<speech_key>.mp3` through a
`TtsEngine` adapter. Two engines are implemented and selectable in config for Anh's pilot listening
test, guarded by the same `--dry-run`/`--yes-spend` spend pattern as extraction (TTS calls cost
money too).

## Boundaries & Constraints

**Always:**
- **`content/speech.py`** (new module, mirrors `content/assets.py`'s docstring/URL-helper style):
  - `speech_text(text: str) -> str`: the single Vietnamese maths read-aloud normaliser. Covers at
    minimum: `<` → "bé hơn", `>` → "lớn hơn", `=` → "bằng", `+` → "cộng", `-` → "trừ", `×`/`*` →
    "nhân", `÷`/`/` → "chia", `\overline{ab}` (two-digit overline notation, e.g. `\overline{2a4b}`)
    → "số " + digit-by-digit reading (e.g. "số hai a bốn b"), `\frac{a}{b}` → "a phần b". Plain
    digits/words pass through unchanged (NFC-normalised). Unrecognised LaTeX-like markup that isn't
    one of the covered notations is left as literal text (never raises) — this is a v1 normaliser,
    not a full LaTeX parser.
  - `speech_key(text: str, voice_id: str) -> str`: `sha256(unicodedata.normalize("NFC",
    speech_text(text)) + voice_id).hexdigest()[:16]`.
  - `speech_url(speech_key: str) -> str`: `f"{ASSETS_URL}/audio/{speech_key}.mp3"` (reuses
    `content.assets.ASSETS_URL`).
  - `speech_path(data_dir: Path, speech_key: str) -> Path`: `data_dir / "assets" / "audio" /
    f"{speech_key}.mp3"`.
  - A `SpeechRef` helper (or a plain function) that, given an `EffectiveProblem`/`ProblemDoc`,
    returns every `(text, speech_key)` pair referenced by its Parts (`instruction`,
    `display_label`, each Part's `prompt`/`hint`/`solution` — never `answer`, which is never read
    aloud to avoid giving it away) — used by both `speak-missing` and (in a later story) the child
    player to look up which key an audio button should fetch. A Concept Guide's equivalent
    text fields are keyed the same way (whatever text fields Concept Guides already define in
    `content/schema.py`; if none exist yet, only cover Problems and the phrase catalogue in this
    story and record that gap as deferred work — do not invent Concept Guide fields not already
    in the schema).
- **`frontend/src/audio/phrases.vi.json`** (new file): a flat `{key: string}` map of every
  non-Problem Vietnamese phrase the UI reads aloud (Home labels, praise lines, badge names,
  states) — populate it with the phrases already implied by DESIGN.md/EXPERIENCE.md and
  Story 2.1's components (e.g. "Học tiếp", "Tiếp tục", correct/retry lines already present as
  literal strings in `FeedbackBanner`/`HomeCard`, etc.); each entry's `speech_key` is computed the
  same way as Problem text.
- **`builder/stages/speak.py`** (new stage, same shape as `crop.py`/`publish.py`): `STAGE =
  "speak"`; a `Report` dataclass (synthesised count, skipped-already-present count, failed list);
  resumable via a `build_jobs` row per `(speech_key)` (not per page — this stage is
  content-addressed, not page-addressed); a key already `done` with its file present on disk is
  skipped without a TTS call; a key whose file is missing (even if its job row says `done` — e.g.
  the file was deleted) is re-synthesised.
- **`TtsEngine` adapter** (new, `builder/tts/` package or `builder/tts_client.py` — pick whichever
  matches `builder/claude_client.py`'s existing single-file-vs-package convention, check before
  writing): an abstract interface `synthesize(text: str, voice_id: str) -> bytes` (raw mp3 bytes)
  plus a `TtsError` exception. At least two concrete engines:
  1. A cloud engine (Azure Cognitive Services Speech or Google Cloud TTS — pick whichever has a
     lighter-weight Python SDK/dependency footprint; document the choice in Implementation Notes).
  2. `edge-tts` (local/free, no API key) as the second, always-available option.
  Both are real, working clients (not stubs) — but **exactly like `ClaudeCliClient`, no automated
  test ever calls a real engine.** All tests use a `FakeTtsEngine` returning deterministic fake mp3
  bytes and recording calls, following the exact `FakeClaudeClient` pattern already used
  throughout this codebase.
- **Config** (`config.py`, `_BUILD_KEYS`-style additions, `[build]` table in
  `hoctap.toml.example`): `tts_engine: str = "edge-tts"` (selectable: `"edge-tts"` or the cloud
  engine's name), `tts_voice_id: str = "vi-VN-..."` (a real default Vietnamese voice id for
  whichever engine is default), `tts_max_total_usd: float` (same spend-cap pattern as
  `extraction_max_total_usd`; `edge-tts` calls cost nothing so this only bounds the cloud engine).
  Secrets (cloud TTS API key) are read from the environment only, per `config.py`'s existing
  docstring rule — never stored in `hoctap.toml` or the database.
- **CLI** (`cli.py`): `hoctap build speak-missing` registered alongside the other `build`
  subcommands, using `_spend_flags`-equivalent guarding (`--dry-run`, `--yes-spend`,
  `--max-total-usd`) exactly like `_build_verify`/`_build_pilot` — a cloud-engine call needs
  `--yes-spend`; `edge-tts` (free) does not need to be gated behind spend confirmation the same
  way, but still respects `--dry-run` (report what would be synthesised, synthesize nothing).
  Unlike the page-ranged `_spend_flags`, `speak-missing` has no book/page-range arguments — it
  scans every currently-referenced key across all published Problems, Concept Guides and the
  phrase catalogue, so give it its own flag set (`--dry-run`, `--yes-spend`, `--max-total-usd`,
  no `--book`/`--pages`).
- **Only the new key is synthesised after an edit**: because `speech_key` is a function of the
  *current* effective text, running `speak-missing` again after any content edit naturally
  produces a different key for the edited text (old audio file is simply orphaned, not deleted —
  cleanup of orphaned audio is out of scope for this story) and only that new key's file is
  missing, so only it gets synthesised. Cover this with a test: build once, edit a Problem's text
  (or simulate an override), run `speak-missing` again, assert exactly one new TTS call happened.
- Bilingual (Vietnamese/English) status and error strings throughout, matching `cli.py`'s existing
  style (see `_SPEND_REFUSED`, `winfw.py`'s `FirewallError`).

**Never:**
- No real network/API calls to any TTS engine in tests — `FakeTtsEngine` only, exactly like the
  Claude CLI rule.
- No `--yes-spend` or real spend triggered by any automated build/test/review step.
- No change to `content/effective.py`'s existing merge/hash logic beyond adding the speech-key
  helper described above; `effective_hash`/`content_hash` computation is untouched (speech_key is
  derived from the effective text at read time, not stored as part of the doc's own hash).
- No frontend audio *playback* work — `SpeakerButton` (Story 2.1) already exists as a dumb
  play/pause control; wiring it to real `speech_url()`s is a later story. This story only produces
  the normaliser, the adapter, the build stage, and the phrase catalogue file.
- No deletion of orphaned audio files (content-addressed, so failing to garbage-collect is safe,
  just wastes disk — note it in Implementation Notes as a deferred cleanup, don't build it now).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normalise comparison | `"3 < 5"` | `speech_text` returns text containing "bé hơn" | N/A |
| Normalise overline | `\overline{2a4b}` | returns "số hai a bốn b" (digit-by-digit + letter placeholders) | N/A |
| Normalise fraction | `\frac{1}{2}` | returns "một phần hai" | N/A |
| Unknown notation | arbitrary unrecognised LaTeX-ish text | returned as literal text, no exception | N/A |
| speech_key stability | same text + voice_id twice | identical key both times | N/A |
| speech_key changes on edit | text changed | different key | N/A |
| speech_key changes on voice change | same text, different voice_id | different key | N/A |
| speak-missing, nothing missing | all referenced keys already have files | 0 TTS calls, report says so | N/A |
| speak-missing, some missing | N keys missing files | exactly N calls to the configured engine, N files written | a single engine failure is recorded in Report.failed and does not stop the rest |
| speak-missing, file deleted but job done | build_jobs row `done`, file missing on disk | re-synthesised (file existence wins over job-row cache) | N/A |
| speak-missing after edit | one Problem's text edited since last run | exactly 1 new key synthesised; old key's file left in place (orphaned) | N/A |
| speak-missing --dry-run | missing keys exist | reports what would be synthesised; 0 calls, 0 files written | N/A |
| speak-missing, cloud engine, no --yes-spend | cloud engine selected, keys missing | refused (same `_SPEND_REFUSED`-style message), nothing sent | exit code matches existing refusal convention |
| speak-missing, edge-tts (free), no --yes-spend | edge-tts selected, keys missing | proceeds without requiring --yes-spend (documented as free) | N/A — decide and document this exactly; if the reviewer disagrees at review time this can be tightened, but ship the documented choice |
| phrases.vi.json entry with no Problem/Concept origin | UI-only phrase | still gets a speech_key and is synthesised by speak-missing | N/A |
| Engine raises TtsError | fake engine configured to fail one key | that key appears in Report.failed with the reason; run continues to the next key | N/A |

## Code Map

- `backend/hoctap/content/speech.py` — new: `speech_text()`, `speech_key()`, `speech_url()`,
  `speech_path()`, the Problem-text-reference helper.
- `backend/hoctap/content/speech_test.py` (or wherever this repo's existing test-file convention
  puts it — check e.g. `content/effective_test.py`'s location before creating) — normaliser cases
  (comparison, overline, fraction, unknown-passthrough), key stability/change tests.
- `backend/hoctap/builder/stages/speak.py` — new: `STAGE`, `Report`, the content-addressed
  scan-and-synth logic (skip/resynthesise decided by file existence on disk; the `build_jobs`
  row per `speech_key` is an audit trail only, written after a successful synthesis — see
  Spec Change Log), `describe()`.
- `backend/hoctap/builder/stages/speak_test.py` — the I/O matrix above, using `FakeTtsEngine`.
- `backend/hoctap/builder/tts_client.py` (or `builder/tts/` package, matching whatever
  `claude_client.py`'s sibling convention is) — `TtsEngine` protocol/ABC, `TtsError`,
  `EdgeTtsEngine`, the cloud engine class, `FakeTtsEngine`.
- `backend/hoctap/builder/tts_client_test.py` — construction/config-selection tests (still no real
  network calls — assert the right engine class is chosen for a given config, not that synthesis
  works).
- `backend/hoctap/config.py` — add `tts_engine`, `tts_voice_id`, `tts_max_total_usd` to `Settings`
  and `_BUILD_KEYS`-equivalent validation.
- `backend/hoctap/cli.py` — register `speak-missing` subcommand, `_build_speak_missing()` function,
  its own flag group (no `--book`/`--pages`).
- `hoctap.toml.example` — document the new `[build]` keys, following the existing commented-out
  style.
- `frontend/src/audio/phrases.vi.json` — new UI-phrase catalogue.
- `pyproject.toml` — add the cloud TTS SDK and `edge-tts` as dependencies (via `uv add`).
- `_bmad-output/implementation-artifacts/deferred-work.md` — append an entry for orphaned-audio
  cleanup (content-addressed, safe to defer) and, if Concept Guides don't yet have text fields,
  an entry noting speak-missing only covers Problems + phrase catalogue until they do.

## Tasks & Acceptance

- [ ] `content/speech.py`: `speech_text()` covering `<`,`>`,`=`,`+`,`-`,`×`/`*`,`÷`/`/`,
      `\overline{...}`, `\frac{a}{b}`; `speech_key()`, `speech_url()`, `speech_path()`; unit tests
      for each notation plus stability/change cases (AD-8).
- [ ] `frontend/src/audio/phrases.vi.json` created with the UI phrases implied by
      DESIGN.md/EXPERIENCE.md/Story 2.1's components.
- [ ] `builder/tts_client.py` (or package): `TtsEngine` interface, `TtsError`, a real cloud engine
      class, a real `edge-tts` engine class, `FakeTtsEngine` for tests; both real engines added as
      dependencies in `pyproject.toml`.
- [ ] `builder/stages/speak.py`: resumable `speak-missing` scan over Problems + phrase catalogue
      (+ Concept Guides if their schema already has text fields), content-addressed via
      `build_jobs`, skips keys whose file already exists, re-synthesises a `done`-but-missing-file
      key, records failures without stopping the run.
- [ ] `config.py` + `hoctap.toml.example`: `tts_engine`, `tts_voice_id`, `tts_max_total_usd`.
- [ ] `cli.py`: `hoctap build speak-missing` with `--dry-run`/`--yes-spend`/`--max-total-usd`
      (cloud engine gated, edge-tts documented as ungated-by-spend since it's free).
- [ ] Edit-then-rerun test: exactly one new key synthesised after a text edit, old file untouched.
- [ ] `deferred-work.md` entries for orphaned-audio cleanup and (if applicable) the Concept Guide
      text-field gap.
- [ ] All new tests pass via `FakeClaudeClient`-equivalent `FakeTtsEngine`; no real TTS/network
      call anywhere in the test suite; `ruff`/`mypy` (or whatever this backend's lint/type
      commands are — check `Makefile`/`pyproject.toml` scripts) clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-28 — initial implementation

**Cloud TTS engine choice: Google Cloud Text-to-Speech (`google-cloud-texttospeech`), not
Azure Cognitive Services Speech.** Azure's Python SDK (`azure-cognitiveservices-speech`) is a
compiled native extension (a C/C++ core with Python bindings) with a much heavier
dependency footprint and a history of lagging new CPython releases; this project pins
`requires-python = ">=3.14,<3.15"`. `google-cloud-texttospeech` is a plain gRPC/REST client
(pure Python + `grpcio`/`protobuf`), installed cleanly on Python 3.14 via `uv add` with no
native build step, and has a documented Vietnamese neural voice. Both `google-cloud-texttospeech`
and `edge-tts` were added with `uv add google-cloud-texttospeech edge-tts` (see `pyproject.toml`).

**Deviations from the spec's Code Map:**
- Tests live at `backend/tests/test_speech.py`, `backend/tests/test_tts_client.py` and
  `backend/tests/test_speak.py` — this repo's actual convention (`backend/tests/test_*.py`,
  confirmed by `content/effective.py` having no sibling `_test.py` file at all; every
  existing test lives under `backend/tests/`), not the spec's suggested
  `content/speech_test.py` / colocated `_test.py` naming, which this codebase does not use
  anywhere.
- `builder/tts_client.py` is a single file (not a `builder/tts/` package), matching
  `builder/claude_client.py`'s own single-file convention exactly (checked before writing).
- Concept Guides: `content/schema.py` has no Concept Guide model at all yet (only Problems'
  `concept_ids`/`concept_proposals`). Per the frozen intent's explicit allowance, this story
  only covers Problems and `frontend/src/audio/phrases.vi.json`; recorded in
  `deferred-work.md`.
- `FeedbackBanner`/`HomeCard` (Story 2.1) turned out to be "dumb" components that take
  `children`/`title` props rather than containing literal Vietnamese praise/label strings
  themselves, so the phrase catalogue's content was sourced directly from
  `_bmad-output/planning-artifacts/ux-designs/ux-hoctap-2026-09-26/{DESIGN,EXPERIENCE}.md`
  (Home card labels, the ~6 praise-line variants, the two retry lines, session summary,
  badges) rather than by lifting literals out of those component files.
- `content.speech.speech_text()`'s `\overline{...}`/`\frac{a}{b}` number reading is
  digit-by-digit (e.g. `\overline{2a4b}` → "số hai a bốn b", matching the spec's own worked
  example exactly), not full Vietnamese number-to-words for multi-digit numerator/
  denominators (e.g. a hypothetical `\frac{12}{34}` reads as "một hai phần ba bốn", not
  "mười hai phần ba mươi tư"). Explicitly a v1 approximation ("not a full LaTeX parser");
  recorded as deferred work.
- `tts_max_total_usd`'s spend cap is enforced against an estimated cost
  (`PRICE_PER_CHAR_USD`: 0 for edge-tts, an approximate $4/1M-characters figure for
  `google-tts`, both in `builder/tts_client.py`), not an engine-reported actual cost —
  `TtsEngine.synthesize()` returns only bytes (per the spec), and neither engine's API
  returns a per-call price the way the Claude CLI's `total_cost_usd` does.
- `build_jobs` needed no new migration: its `stage` column has no CHECK constraint
  restricting allowed values (only `build_runs.stage` does), so the content-addressed
  `"speak"` stage stores rows the same way `"crop"`/`"publish"` do, keyed by
  `page_ref = "speech#{speech_key}"`, `input_hash = speech_key`. The job row is written only
  as an audit trail; the actual skip/resynthesise decision is file-existence only, per the
  spec's own edge-case rule ("file existence wins over job-row cache").

**Verification commands run (backend/, from the repo's own `/mnt/c` checkout — the
orchestrator will independently re-verify from a fast `/tmp` copy):**
- `uv run ruff check hoctap/content/speech.py hoctap/builder/tts_client.py hoctap/builder/stages/speak.py hoctap/config.py hoctap/cli.py tests/test_speech.py tests/test_tts_client.py tests/test_speak.py` → **all checks passed**.
- `uv run pytest tests/test_speech.py tests/test_tts_client.py -q` → **22 passed** in ~3s.
- `uv run pytest tests/test_speak.py -q` → **15 passed** in ~38s (build_jobs/migrations per
  test make this file slower than the pure-unit ones; not a hang).
- `uv run pytest -q` (the whole backend suite, all 705 tests including the new ones) →
  **705 passed** in 929.81s (0:15:29). A first attempt wrapped in a hard `timeout 590`
  was killed (exit 143) before finishing — that was this run legitimately needing more than
  590s on this machine's slow `/mnt/c` (WSL9P) disk, not a hang; the unwrapped re-run
  completed cleanly. No `mypy`/type-checker is configured anywhere in this backend
  (`pyproject.toml` has no `[tool.mypy]` section and no mypy dev dependency), so lint is
  `ruff check` only; there is nothing further to run for type-checking.
- No test in `test_speech.py`, `test_tts_client.py` or `test_speak.py` calls a real TTS
  engine: every `run_speak()`/CLI test uses `FakeTtsEngine`, and `test_tts_client.py`'s
  `make_engine("edge-tts"|"google-tts")` tests only assert the returned class, never call
  `.synthesize()` (both real engines build their network/credentialed client lazily, inside
  `synthesize()`, specifically so construction alone is always safe to exercise).

### 2026-09-28 — review-fix round

Fixed a critical bug and 8 smaller gaps found in review:

1. **Critical**: `content.speech.problem_speech_refs()`/`builder.stages.speak.collect_refs()`
   were storing and passing the RAW field to `TtsEngine.synthesize()` — `speech_key()`
   normalised internally just to compute the hash, but the normalised text itself was
   thrown away, so the mp3 would have contained literally-spoken LaTeX/operator markup.
   Fixed: `SpeechRef.text` (and every value `collect_refs()` puts in its `{key: text}` map,
   including phrase-catalogue entries) is now `speech_text(raw)`, the actual normalised
   Vietnamese; `speech_key` is unchanged (still the hash of that same normalised text +
   voice). Updated `test_speech.py`'s and `test_speak.py`'s assertions that had encoded the
   bug as correct (comparing against raw text) to expect normalised text instead, and added
   dedicated regression tests (`test_collect_refs_stores_normalised_not_raw_text`,
   `test_problem_speech_refs_normalises_maths_notation`) asserting e.g. `"3 cộng 2 bằng 5"`
   is present and `"3 + 2 = 5"` is not.
2. Fixed nested-notation garbling (`\frac{\overline{2}}{3}` mangled "số hai" into "s ố h a
   i"): `_OVERLINE_RE`/`_FRAC_RE`'s captured body is now restricted to `[0-9A-Za-z]*`
   (plain ASCII digits/letters only, no braces/spaces/non-ASCII), so a nested case's inner
   substitution result can never be re-matched and re-spelled by the outer regex; it is
   instead left partially normalised (e.g. `\frac{số hai}{3}`) — never garbled, never
   raises. Added `test_nested_notation_is_not_double_processed`.
3. The same `[0-9A-Za-z]*` restriction makes the module docstring's claim (operator
   characters never appear inside a matched `\overline{...}`/`\frac{...}{...}` body) true
   by construction, not just by convention; rewrote the comment/docstring to say so
   precisely, and documented that a `+`/`=`/etc. inside an otherwise-unmatched `\frac{...}`
   (e.g. `\frac{1+2}{3}`) now simply fails to match (left with a literal `\frac{...}`
   wrapper) rather than being consumed and reprocessed. Added
   `test_frac_with_operator_inside_is_left_as_literal_wrapper`.
4. Documented the operator-substitution's blind-`str.replace()` limitation (a literal `-`
   in ordinary prose reads as "trừ") explicitly in `speech.py`'s module docstring, and added
   a `deferred-work.md` entry; not fixed (would need digit-adjacency detection or NLP, out
   of scope for this pass per the coordinator's explicit instruction not to over-engineer
   it).
5. Added tests for degenerate empty bodies (`speech_text(r"\overline{}") == "số"`,
   `speech_text(r"\frac{}{}") == "phần"`, never raising) and for `problem_speech_refs()`
   given a duck-typed stub with zero Parts (a real `ProblemDoc` cannot have zero Parts,
   `parts: list[Part] = Field(min_length=1)`, so the zero-Parts branch is only reachable via
   a stub object, not a real `ProblemDoc`).
6. Added `builder.stages.speak._add_ref()`: warns (`RuntimeWarning`) if the same
   `speech_key` is ever mapped to two different texts within one `collect_refs()` call — a
   safety net for a future normaliser bug, not for a real sha256 collision. Covered by
   `test_collect_refs_warns_on_speech_key_collision`.
7. Added `test_edge_tts_package_actually_installs_and_imports` and
   `test_google_cloud_texttospeech_package_actually_installs_and_imports` to
   `test_tts_client.py`: bare `import edge_tts` / `import google.cloud.texttospeech`, no
   network, no API key — proves the two `uv add`ed dependencies actually install and import
   on Python 3.14, since nothing else in the suite ever imports them (both real engines
   defer their import to inside `synthesize()`, which no test calls).
8. Added `test_build_jobs_row_written_as_audit_trail`, confirming a `done` `build_jobs` row
   (via `jobs_store.find_done`) actually exists after a successful synthesis, backing the
   module docstring's "audit trail" claim with a test rather than just prose.
9. Corrected the Code Map's `builder/stages/speak.py` bullet wording ("the resumable
   scan-and-synth logic" → explicit file-existence-is-authoritative, `build_jobs` is an
   audit trail); see Spec Change Log. No code change was needed for this item — the
   implementation already matched the Boundaries & Constraints/I/O Matrix wording, only the
   Code Map's own phrasing was imprecise.

**Re-verification**, using an isolated `/tmp` copy (`rsync -a --exclude .venv --exclude
__pycache__ --exclude .pytest_cache backend/ /tmp/hoctap_verify/backend/`, then `uv sync`
there) so the check does not depend on anything left over in the working tree on `/mnt/c`:
- `uv run ruff check` on every touched/new file → all checks passed.
- `uv run pytest tests/test_speech.py tests/test_tts_client.py tests/test_speak.py -q` →
  **47 passed** in 13.51s (fast `/tmp` disk; compare ~24s+24s on `/mnt/c` for the same
  files pre-fix).
- `uv run pytest -q` (the whole backend suite, from the `/tmp` copy) → **715 passed** in
  223.17s (0:03:43) — confirms the review-round changes broke nothing else, and that the
  full suite genuinely completes in well under 10 minutes off the slow `/mnt/c` disk (the
  earlier `timeout 590` kill on `/mnt/c` was disk latency, not a hang, as already noted
  above).
- No test calls a real TTS engine at any point in this fix round either.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

### 2026-09-28 — Code Map wording correction (post-review)

The Code Map's `builder/stages/speak.py` bullet said "the resumable scan-and-synth logic",
which reads as if the `build_jobs` row itself decides skip/resynthesise. It does not: per
this same spec's own Boundaries & Constraints ("a key whose file is missing ... is
re-synthesised" / "file existence wins over job-row cache" in the I/O & Edge-Case Matrix),
the actual implementation's resume/skip decision is file-existence-based only; the
`build_jobs` row is written purely as an audit trail after a successful synthesis. The
Code Map bullet is corrected to say so explicitly (no code change — the implementation
already matched the Boundaries & Constraints wording, only the Code Map's own phrasing was
imprecise). Flagged during review.

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `problem_speech_refs()`/`collect_refs()` store the RAW field text (e.g. containing `\overline{2a4b}`, `\frac{1}{2}`, literal `<`/`=`), keyed by `speech_key()`'s normalized hash; `run_speak()` then sends that raw text to `tts.synthesize()`. The normaliser (`speech_text()`) is only ever used internally by `speech_key()` to compute the cache key — its output is discarded and never reaches the TTS engine. | critical | confirmed independently by reading speech.py:116-131, speak.py:60-73,111,127; `speech_text` is never imported in speak.py. The audio produced would literally read out LaTeX markup instead of Vietnamese words, defeating the entire point of the story -> patch: `SpeechRef`/`collect_refs` must carry the normalized (`speech_text()`) string, and `run_speak` must synthesize that, not the raw text |
| 2 | Nested `\overline{}` inside `\frac{}{}` (e.g. `\frac{\overline{2}}{3}`): overline substitution runs first, replacing it with "số hai" (now brace-free, Vietnamese words with spaces), then the frac regex matches and `_spell()` re-spells that phrase character-by-character (since `_spell` treats every non-digit char literally but joins with spaces), garbling already-correct Vietnamese into "s ố h a i" | medium | confirmed via code trace -> patch: either detect/skip already-substituted (non-original) content, or process `\frac{}{}` before `\overline{}` only when nested, or simplest: make `_spell` a no-op passthrough (return chars joined without the digit-only assumption breaking on already-Vietnamese text) — implementer's choice, but must not double-process |
| 3 | Docstring at speech.py:50-52 claims operator characters (`+`,`-`,`*`,`/` etc.) never appear inside `\overline{}`/`\frac{}{}` replacements, but the regexes use `[^{}]*` which happily captures them (e.g. `\frac{1+2}{3}`), and the surviving operator characters then get double-substituted by the later operator-word loop | low | real inaccuracy in the comment, low real-world likelihood (depends on what the extractor emits) -> patch: fix the comment to state the actual limitation, or add a guard/test for this shape if it's plausible extractor output |
| 4 | `_OPERATOR_WORDS` does an unconditional `str.replace` for `-`/`=`/etc. across the ENTIRE text, not just math-looking regions — a literal hyphen in ordinary Vietnamese prose (compound words, a dash in a sentence) gets turned into "trừ" (a wrong word) | medium | real design gap, no test covers operator chars mixed with normal prose -> given this is a v1 normaliser and full NLP disambiguation is out of scope, at minimum: note this as a known limitation in speech.py's docstring and deferred-work.md (do not attempt a full fix this story unless it's cheap — a plausible cheap mitigation: only substitute operators when they appear between digit-ish tokens, e.g. via a regex requiring adjacent digits/whitespace rather than a blind substring replace) |
| 5 | Empty `\frac{}{}` / `\overline{}` produce degenerate output ("phần" alone / "số" alone) with no test coverage; a doc with zero Parts has no test coverage for `problem_speech_refs` | low | -> patch: add the missing test cases (cheap, no behavior change needed unless the degenerate output is judged unacceptable — if so, treat as literal passthrough instead) |
| 6 | `collect_refs()` silently overwrites `refs[key]` on a hash collision between two different texts (16-hex-char sha256, astronomically unlikely, but a future bug in `speech_key`/`speech_text` producing an actual collision would silently drop one Problem's audio with no warning) | low | -> patch: not worth defending against real collisions, but add an assertion or log a warning if `collect_refs` ever sees the same key mapped to two different texts — cheap safety net for a future normaliser bug, not for a real hash collision |
| 7 | `cli.py`'s `speak-missing` exit code is `1` for both "one key of many failed" and "everything failed" — callers can't distinguish partial from total failure from the exit code alone | low | -> patch: optional — either leave as-is (matches `_build_verify`'s existing pattern of not distinguishing) or use `report.synthesized == 0 and report.failed` for a harder failure code; implementer's choice, document whichever is picked |
| 8 | The spec's Code Map says "resumable via `build_jobs`" but the actual resume/skip decision is 100% file-existence-based; the `build_jobs` row is (by the implementer's own admission) only an audit trail with no behavioral effect, and no test confirms the row is even written | low | spec-wording overstatement, self-disclosed by implementer -> patch: add one cheap test asserting `jobs_store` has a row after a successful synthesis (confirms the audit trail actually works as documented), and correct the spec's Code Map wording from "resumable via build_jobs" to "resumable via on-disk file existence, with an audit-trail build_jobs row" |
| 9 | No test ever imports/exercises the real `edge_tts` or `google-cloud-texttospeech` packages (both are lazily imported only inside `synthesize()`, which no test calls) — the "705 passed" run doesn't prove these dependencies actually install/import correctly on Python 3.14 | low | real verification gap -> patch: add one cheap smoke test (or a documented manual verification step) that does `import edge_tts` and `import google.cloud.texttospeech` (import only, no network call) to confirm the packages actually installed correctly |
| 10 | `_TTS_ENGINES` in config.py is a manually-duplicated copy of `builder.tts_client.ENGINE_NAMES`, by design (to avoid config.py depending on builder) — a future added/renamed engine could drift between the two | low | self-documented in a comment already -> reject, no action needed beyond what's already there; optionally add a cheap test asserting the two sets are equal (test-only import is fine, doesn't violate the config.py/builder layering) |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-28 (orchestrator, independent re-verification after fix round): confirmed the critical raw-text fix directly in source (`problem_speech_refs()` now returns `SpeechRef(speech_text(raw), key)`; `speak.collect_refs()` normalizes phrase-catalogue text via `_add_ref(refs, speech_key(raw, voice_id), speech_text(raw))`). Ran `ruff check` on all touched/new files (clean). Ran the 3 new/updated test files directly: 47/47 passed in 35.65s. Ran the full backend suite: 715/715 passed in 573.18s (~9.5 min, consistent with known `/mnt/c` WSL9P I/O slowness, not a hang). No test imports or calls a real TTS engine's `synthesize()`; the two new install-smoke tests only bare-import `edge_tts`/`google.cloud.texttospeech`. Story marked done.

</frozen-after-approval>
