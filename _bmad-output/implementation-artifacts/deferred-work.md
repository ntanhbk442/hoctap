- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-project-scaffold-served-from-one-origin.md`
  summary: Route uvicorn access/error logs into the JSON-lines log file.
  evidence: uvicorn loggers don't propagate to root; only console gets access logs (review finding 12).
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-first-run-setup-with-pin-and-first-child-profile.md`
  summary: Escalating PIN lockout (e.g. doubling lock duration) or daily cap for the 4-digit PIN.
  evidence: fixed 5-min lock allows ~1,440 guesses/day; frozen intent specifies 5 minutes — revisit with PIN change in Story 4.1.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-first-run-setup-with-pin-and-first-child-profile.md`
  summary: Test the concurrent-setup IntegrityError → 409 SETUP_DONE path.
  evidence: only reachable under a race; monkeypatch is_setup_done to force it.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-book-catalogue.md`
  summary: Test the fingerprint OSError → unreadable path in collect_rows.
  evidence: branch only reachable if a file becomes unreadable after opening; monkeypatch fingerprint.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-crop-concept-tagging-and-publish.md`
  summary: Test that build pilot exits 1 when publish fails.
  evidence: same _print_publish helper is tested via build publish; pilot only wires it.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-book-catalogue.md`
  summary: Fix flaky test_catalogue.py::test_fingerprint_change_detected_with_same_size.
  evidence: failed intermittently in two separate full runs (stories 1.6 and 1.8), passes alone.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-9-spot-check-pilot-report-and-go-no-go-gate.md`
  summary: Remove backend/hoctap/_py314_compat.py (and its conftest import) by pinning requires-python >= 3.14.1 / .python-version 3.14.7.
  evidence: shim added by the cloud run to work around CPython 3.14.0rc2 dropping prefer_fwd_module; it is a no-op on 3.14.7 but monkeypatches typing in production code.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-10-extraction-control-from-the-parent-area.md`
  summary: DB-level single-active-run constraint and multi-process/instance safety for RunManager.
  evidence: currently enforced only in-process; fine for the single-instance local-PC architecture (AD-13) but worth hardening later.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-11-https-on-the-lan-and-windows-runtime.md`
  summary: Optional --check/status and uninstall paths for hoctap certs / install-windows.
  evidence: reviewer suggestion, explicitly out of scope for this story per the frozen intent.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-10-extraction-control-from-the-parent-area.md`
  summary: Investigate and fix 3 failing tests in frontend/src/pages/ExtractionPage.test.tsx, discovered for the first time during Story 2.1 (this exact file could never run to completion on this machine before now, per Story 1.10's own Spec Change Log -- these may never have passed).
  evidence: |
    Run standalone from a native filesystem (npm ci + npx vitest run in /tmp, working
    around the /mnt/c WSL9P I/O latency issue): 3/8 tests in this file fail, reproducibly.
    (1) "shows the picker when there is no run, and starts one": uses synchronous
    `screen.getByRole(...)` immediately after `renderAt(...)`, but the component shows a
    "Đang tải..." loading state until its async GET queries resolve -- likely a test-authoring
    race (should be `findByRole`), not a component bug.
    (2) "asks to confirm the spend, then starts on confirm": after the mocked 422
    SPEND_NOT_CONFIRMED response, the DOM is byte-identical before and after the click --
    no estimate text, no confirmation UI, and the submit button ends up disabled. This does
    NOT look like a simple text-matcher issue (unlike #3) -- it looks like the mutation's
    onError never fires, or `start.isPending` never resolves, or the click/submit never
    reaches `start.mutate(false)` at all. Traced as far as: the onError handler in
    ExtractionPage.tsx (checks `error instanceof ApiError && error.code === 'SPEND_NOT_CONFIRMED'`)
    and mockApi's request matching (`src/test/render.tsx`) both look correct on inspection;
    root cause not yet found. THIS ONE MAY BE A REAL BUG in the spend-confirmation flow
    shipped in Story 1.10, not merely a test issue -- needs a debugger/console.log trace,
    not just static reading.
    (3) "cancels a run": `findByText('Đã hủy')` (exact match) fails because the actual
    rendered text is the longer `"Đã hủy (1/3 trang) · Chi phí: $0.2500"` -- testing-library's
    default exact-string matching doesn't substring-match; this is a test-authoring bug
    (needs a regex or `{exact: false}`), the component itself renders correctly.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-design-tokens-nunito-and-core-components.md`
  summary: Add a barrel export (src/components/index.ts) for the ten shared components once more consumers exist.
  evidence: reviewer suggestion, no current consumer needs it yet.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-speech-normaliser-tts-adapter-and-speak-missing.md`
  summary: Garbage-collect orphaned audio files under data/assets/audio/ (a key whose Problem/phrase text has since changed leaves its old mp3 behind forever).
  evidence: content-addressed by design (AD-8), so an orphan is safe (never served, never referenced) but wastes disk; frozen intent explicitly defers this cleanup to a later story.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-speech-normaliser-tts-adapter-and-speak-missing.md`
  summary: Extend `speak-missing` (and `content.speech`) to cover Concept Guide text once Concept Guides get speakable text fields.
  evidence: `content/schema.py` has no Concept Guide model yet (only Problems' `concept_ids`/`concept_proposals`); this story's Boundaries & Constraints explicitly allow deferring Concept Guide coverage until that schema exists, so `speak-missing` currently scans only Problems and `frontend/src/audio/phrases.vi.json`.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-speech-normaliser-tts-adapter-and-speak-missing.md`
  summary: Improve `content.speech`'s `\overline{...}`/`\frac{a}{b}` number reading from digit-by-digit spelling to proper Vietnamese number-to-words (e.g. "12" as "mười hai", not "một hai").
  evidence: v1 normaliser per the frozen intent ("not a full LaTeX parser"); digit-by-digit matches the spec's own worked example (`\overline{2a4b}` -> "số hai a bốn b") exactly, but is a rough approximation for a multi-digit `\frac` numerator/denominator.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-child-home-and-library.md`
  summary: A Grade switcher UI on the Library, to reach Books of a Grade other than the child's own.
  evidence: frozen intent explicitly defers this ("a Grade switcher UI is explicitly out of scope"); `GET /library/grades/{grade}/books` already accepts any grade, only the frontend has no picker for it yet.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-child-home-and-library.md`
  summary: "Tiếp tục" (continue), Retry Queue, and Streak/Stars/badges Home cards.
  evidence: blocked on Story 2.4 (Sessions/`progress_events`/`ProblemSetRef` do not exist yet); this story's Home deliberately renders neither a fake "0" nor these cards at all, per the frozen intent.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-child-home-and-library.md`
  summary: The actual Problem player/interaction in Lesson detail (tapping a Problem in the list is currently a no-op -- no click handler at all).
  evidence: frozen intent explicitly scopes Lesson detail here to a read-only list; the Problem player is a later Epic 2 widget story.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-child-home-and-library.md`
  summary: Replace `frontend/src/audio/speech.ts`'s hardcoded `DEFAULT_VOICE_ID` duplication of `Settings.tts_voice_id` with a real single source of truth (e.g. a `voice_id` field on an existing public endpoint, or generated from `config.py`).
  evidence: no endpoint currently exposes `tts_voice_id`; this story needed a `speech_key()`-matching frontend hash to resolve an already-synthesised UI phrase's audio URL (`content.speech.speech_url()`'s frontend counterpart) and settled for a documented, deliberate duplication rather than adding a new backend concept -- see this story's Implementation Notes.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-child-home-and-library.md`
  summary: Real progress numerators ("k/n ✓") once Story 2.4 ships Sessions/`progress_events`.
  evidence: this story's Library/Lesson lists always show "0/n" honestly (no child has ever done a Problem, because there is no way to start a Session yet), per the frozen intent.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: `ProblemSetRef` kinds `concept`/`retry`/`replay` (AD-9) -- resolving a personalised set for a Concept, the Retry Queue, or a replay of past Sessions.
  evidence: frozen intent explicitly scopes this story to `kind: "lesson"` only; the other kinds need Concepts/Retry Queue/replay history, none of which exist yet. `learning.problem_sets.resolve()` raises `UnsupportedProblemSetRef` (a clear, bilingual, documented `NotImplementedError`) for them rather than guessing.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: A "Tiếp tục" (continue) Home card for the last unfinished Session.
  evidence: needs "unfinished" to be well-defined, which needs `session_completed` semantics and/or grading (Story 2.5) to be meaningful; building a half-correct heuristic now (e.g. "has an incomplete problem_ids_json") was explicitly avoided per the frozen intent.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: The actual Problem player/interaction (answering a Part, submitting, seeing feedback).
  evidence: frozen intent explicitly scopes this story's Session route (`SessionPlayer.tsx`) to a read-only bundle-rendering placeholder, matching `LessonDetail.tsx`'s existing pattern; the real player is a later Epic 2 widget story. No grading exists yet either (Story 2.5), so a player couldn't give real feedback regardless.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: Garbage-collect `progress_sessions` rows whose frozen `problem_ids_json` references a Problem that was later fully deleted (not merely retired/hidden) from `content_catalog_problems`.
  evidence: `GET /sessions/{id}/bundle` already handles this defensively (skips an id `content.effective.load_one()` can no longer find, via `ProblemNotFound`, rather than 500ing), but Problems are in practice never hard-deleted (only `retired_at`-marked) by the current builder, so this path is untested by any real data flow; noted for completeness, not urgent.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: Fix `backend/hoctap/api/assets.py`'s `except OSError, ValueError:` (Python-2 tuple-exception syntax, pre-existing, not touched by Story 2.4) to `except (OSError, ValueError):`.
  evidence: |
    Discovered during Story 2.4 verification: this line only happens to parse on this
    machine's exact Python 3.14.7 build (its PEG parser accepts the old comma form as
    sugar for a tuple, confirmed via dis.dis showing a correct BUILD_TUPLE 2), but is
    invalid syntax on Python 3.11-3.13 and should not be relied upon going forward.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-sessions-resolver-and-the-event-api.md`
  summary: Dedup concurrent/repeated `POST /sessions` for the same Profile+`ProblemSetRef` -- currently each call creates an independent, fully-frozen `progress_sessions` row with no coalescing.
  evidence: |
    Finding #17 of the orchestrator's independent review round (2026-09-29): each
    Session is individually a legitimate, correctly-frozen Session, so this is not a
    correctness bug, but it is undocumented/untested behavior. Real dedup needs
    "the current unfinished Session for this ref", which needs `session_completed`
    semantics and/or grading (Story 2.5) to define "unfinished" -- the same blocker
    already noted above for the "Tiếp tục" card. Deferred to Story 2.5 rather than
    building a heuristic now.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-grading-and-staged-help.md`
  summary: Stars, Streak, and badge computation/tables.
  evidence: |
    Frozen intent explicitly defers these; AD-6 mentions `learning` eventually deriving
    them, but no story before 2.10 "Session summary" consumes them, and epics.md's own
    Story 2.5 acceptance criteria never mention them.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-grading-and-staged-help.md`
  summary: Assignment-status computation/tables.
  evidence: Frozen intent explicitly defers this; no consumer exists before a later story.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-grading-and-staged-help.md`
  summary: First-try-accuracy computation/tables.
  evidence: |
    Frozen intent explicitly defers this; grading's own `correct`/`wrong_keys` per
    attempt is stored (in `progress_events.payload_json`), so a later story can derive
    first-try accuracy from the existing log without a schema change, but no story
    before 2.10 consumes it yet.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-grading-and-staged-help.md`
  summary: |
    The actual Problem player/interaction that calls this story's grading (submitting an
    answer, seeing the Hint/Solution, the Retry Queue UI).
  evidence: |
    Frozen intent explicitly scopes this story to `POST /sessions/{id}/events` only --
    `SessionPlayer.tsx` (Story 2.4) stays read-only; the Problem Player widgets that
    would actually call this are Stories 2.6/2.7.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-5-grading-and-staged-help.md`
  summary: |
    A real Retry Queue endpoint/UI (a "Retry" Home card, a `ProblemSetRef` kind that
    resolves to the Retry Queue's own open Problems).
  evidence: |
    `progress_retry_items` rows are written and resolved correctly by this story, but
    nothing reads them yet -- `learning.problem_sets.resolve()`'s `retry` kind is still
    `UnsupportedProblemSetRef` (Story 2.4's own deferral, unchanged here).
- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-the-other-grade-1-widgets.md`
  summary: `expression_input` (EXPERIENCE.md's Problem Type interaction table lists it, but no Epic 2 story's acceptance criteria -- 2.6's basic 5 or this story's 7 -- ever names it).
  evidence: |
    This story's own Code Map explicitly asked to check this; confirmed not covered by
    any Epic 2 story, in scope or acceptance criteria, so it is out of scope for all of
    Epic 2 as it stands. No `expression_input` Part type even exists in
    `content/schema.py`'s `Part` union, so there is nothing to wire a widget to yet either.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-the-other-grade-1-widgets.md`
  summary: `spot_difference`'s child-facing View (`SpotDifferenceView`) needs to expose region/bbox hotspot data (mirroring `image_select`'s `Region` shape) -- or the grader needs a geometry-tolerant match -- before a real `spot_difference` Part can ever grade correct.
  evidence: |
    See this story's own Spec Change Log entry (2026-09-29) for the full analysis: the
    client can only ever produce a coordinate-derived region key, which cannot match
    `SpotDifferencePart.answer.regions`' author-assigned keys server-side. This story
    ships the full tap/ring/counter/✔-gating UX per spec regardless, but grading a real
    Part of this type will always come back incorrect until this is fixed.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-fallback-self-check.md`
  summary: |
    Whichever future story computes first-try accuracy (Story 2.5 deferred this; still not
    built by any story through 2.8) must exclude `fallback_revealed` and `self_marked`
    events by construction -- neither is a graded Attempt, so counting either into
    first-try accuracy would silently corrupt that metric.
  evidence: |
    Frozen intent explicitly calls this out: a `fallback` Problem's `self_marked` is a
    child self-report, never a `grade_part()` verdict, and `fallback_revealed` is a
    "the child asked to see the answer" telemetry marker -- neither belongs in a metric
    defined over graded Attempts. No code enforces this exclusion today because no story
    has built first-try accuracy yet (`progress_events.payload_json` already stores enough
    per-attempt `correct`/`wrong_keys` data for a future story to derive it directly); this
    entry exists so that future story's own design doesn't accidentally query `kind =
    'attempt'` loosely enough to also catch these two kinds, or forget they exist at all.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-fallback-self-check.md`
  summary: |
    A real Star display/count (Session summary, Home, a badge) that reads the
    `self_marked` events with `payload["correct"] is True` this story's events make
    derivable.
  evidence: |
    Frozen intent explicitly defers this to Story 2.10 "Session summary" -- this story only
    ensures the event log carries enough information (one `self_marked` event per
    self-check, its own `correct` field) for a future reader to derive the count; no
    Star-reading endpoint or UI exists yet, by design.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-9-audio-player-and-auto-play.md`
  summary: A Parent-Area UI control to toggle a Profile's `auto_play` setting.
  evidence: |
    Frozen intent explicitly scopes this story to the column + schema + `GET /profiles`
    exposure only (default `true` for every Profile, no toggle in acceptance criteria).
    `parent_profiles.auto_play` and `Profile.auto_play` are both ready for a future Parent
    Area story to add a switch that PATCHes it -- no new backend concept needed, just a
    write endpoint and a form control.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-10-session-summary-and-luyen-lai-bai-sai.md`
  summary: |
    A `fallback`-type Problem (Story 2.8's self-check) can never count as first-try-correct
    in `learning.summary.session_wrong_problem_ids()` -- even when the child self-marked
    "đúng" -- because that computation reads only `attempt` events, per this story's frozen
    spec text and the Story 2.8 `deferred-work.md` entry it echoes (`self_marked`/
    `fallback_revealed` must never be counted as a graded verdict). A fallback Problem
    therefore always appears in a completed Session's `wrong_problem_ids` and is always
    offered again via "Luyện lại bài sai", regardless of how the child actually self-marked
    it.
  evidence: |
    See this story's Implementation Notes (2026-09-29) for the full reasoning; a future
    story that wants first-try accuracy to treat a correct self-mark as "correct" needs to
    either extend `session_wrong_problem_ids()` to read `self_marked` for Problems with zero
    `attempt` events, or accept this as the permanent behaviour for fallback Problems and
    update the frozen spec text accordingly -- either way it should be a deliberate,
    reviewed change, not a silent one.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-10-session-summary-and-luyen-lai-bai-sai.md`
  summary: A real Streak-display UI (calendar view, flame animation/asset, badges tied to Streak length).
  evidence: |
    Frozen Boundaries & Constraints explicitly scope this story to the plain `streak` count
    `GET /sessions/{id}/summary` returns -- no calendar UI, no flame asset, no badges. The
    PRD's UJ-1 "4-day Streak flame growing" is flavor text, not a literal required asset.
- source_spec: `_bmad-output/implementation-artifacts/spec-2-10-session-summary-and-luyen-lai-bai-sai.md`
  summary: Badges (any kind) -- still not built by any Epic 2 story through 2.10.
  evidence: |
    Every prior Epic 2 story (2.5 through 2.9) has deferred badges in turn; this story's own
    frozen Boundaries repeat the deferral explicitly. No badge schema, computation, or UI
    exists yet.
