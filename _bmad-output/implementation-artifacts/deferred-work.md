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
