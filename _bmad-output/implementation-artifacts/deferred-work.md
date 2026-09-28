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
