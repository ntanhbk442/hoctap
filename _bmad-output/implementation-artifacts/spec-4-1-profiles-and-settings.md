---
title: 'Story 4.1: Profiles and settings'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'd551415c72f9e694aa151f0cd6b7d4f241ffbd86'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.2 creates the PIN and the first Child Profile, but afterwards Anh cannot add a sibling, edit or remove a child, change the PIN, or switch `auto_play` (column and `GET /profiles` exist, no write path). The child Home reaches the Parent Area through a plain "Khu vực phụ huynh" text link, not the intended 🔒 long-press, and the Parent Area has no Settings screen.

**Approach:** Add PIN-guarded profile CRUD (max 4), PIN change and per-child `auto_play` write endpoints, plus a `/parent/settings` screen linked from ParentHome. Replace the Home text link with a 🔒 that opens the PIN gate only after a 2-second long-press. The existing picker (shown at 2+ Profiles) and `auto_play` reads stay as they are.

## Boundaries & Constraints

**Always:**
- All new writes sit behind `require_parent`; `GET /profiles` stays open (child picks without a PIN).
- Max 4 Profiles, enforced server-side in the insert transaction. Profile fields reuse `ProfileIn` validation (name NFC, 40 chars, avatar set, Grade 1-5).
- PIN change requires the current PIN, reuses `Pin` (4 digits), bcrypt hashing, and the existing lockout counter on a wrong current PIN. A successful change bumps `session_version` and re-issues the caller's cookie, so other sessions are logged out.
- Deleting a Profile removes its `progress_*` rows (sessions, events, stars, badges, retry items) in one transaction; no FK cascades exist (`profile_id` is plain Text), so this is explicit code in `parent/service.py` reaching the `learning` tables through a `learning` function, not raw table writes.
- Deleting a Profile (human decision) permanently purges that child's progress after a confirm dialog that names the child and states progress will be lost; there is no undo and no block-if-progress-exists rule.
- Forgotten PIN (human decision): a `hoctap` CLI command run on the host machine resets the PIN without the old one, clears the lockout counter, and bumps `session_version` so every existing parent cookie is rejected. It prompts for the new 4-digit PIN (never a command-line argument), validates it with the same `Pin` rule, and needs no running server.
- New UI copy is Vietnamese; the child's Home keeps the positive tone (no red).

**Never:** Profile deletion of the last remaining Profile (Home would dead-end); a PIN reset without the current PIN through the web app or HTTP API (only the host-side CLI command may); backup/restore, dashboard, Assignments or the Parent Area menu redesign (Stories 4.2-4.4, NFR-7); moving the picker or `profile.ts` selection off `sessionStorage`; a new Alembic migration (`auto_play` already exists at head `0016_retry_queue_due`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Add profile | Parent cookie, 1 Profile, valid body | 201 Profile, `auto_play` true, listed last | N/A |
| Fifth profile | 4 Profiles exist | Rejected, nothing inserted | 409 `PROFILE_LIMIT` |
| Edit | `PATCH` name/avatar/grade/auto_play | Updated Profile returned | 404 `PROFILE_NOT_FOUND`; 422 on bad field |
| Delete | 2+ Profiles, confirmed | 204; that Profile's progress rows gone; others untouched | 404 unknown id |
| Delete last | Only 1 Profile | Rejected | 409 `LAST_PROFILE` |
| Change PIN | Correct current + new (+confirm) | 204; old PIN no longer logs in; other cookies rejected | 401 wrong current (counts toward lockout, 429 when locked); 422 mismatch |
| Forgotten PIN | Host runs the CLI reset with a valid new PIN | New PIN works, old PIN fails, lockout cleared, old cookies rejected | Invalid PIN rejected, nothing changed |
| No cookie | Any new write | Rejected | 401 / 403 `SETUP_REQUIRED` |
| Toggle auto-play | `auto_play=false` for Profile A | A's Session skips instruction auto-play; B unchanged | N/A |
| Long-press 🔒 | Held 2 s on Home | Navigates to `/parent/login` (or `/parent` if a valid cookie) | N/A |
| Short tap 🔒 | Released before 2 s | Nothing happens | N/A |
| Deleted current child | `sessionStorage` id no longer listed | Home shows picker (1 left: auto-select) | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/api/profiles.py` -- open `GET /profiles`, badges; add guarded `POST`, `PATCH /{id}`, `DELETE /{id}` here or in a new guarded router.
- `backend/hoctap/api/parent.py` -- `login`, `logout`, `session`; add `POST /parent/pin` (change PIN).
- `backend/hoctap/parent/service.py` -- `complete_setup`, `verify_pin`, `end_sessions`, `list_profiles`; add create/update/delete/change-PIN.
- `backend/hoctap/parent/schemas.py`, `models.py` -- `ProfileIn`, `Profile` (has `auto_play`), `Pin`; add `ProfilePatch`, `ChangePinRequest`.
- `backend/hoctap/cli.py` -- existing `hoctap` CLI (subparsers near line 732); add a `reset-pin` subcommand calling a `parent/service.py` reset function.
- `backend/hoctap/parent/auth.py` -- `require_parent`, `issue_cookie`; reuse for cookie re-issue after PIN change.
- `backend/hoctap/learning/` -- add a `delete_profile_progress(conn, profile_id)` helper over the `progress_*` tables (sessions, events, stars, badges, retry items).
- `frontend/src/pages/ParentHome.tsx`, `App.tsx` -- add "Cài đặt" link and `/parent/settings` route.
- `frontend/src/pages/Home.tsx`, `components/HomeCard/HomeCard.tsx` -- text link at Home.tsx:242 becomes 🔒; `HomeCard` long-press is 500 ms, so a separate 2000 ms press hook is needed. Same `parent-link` paragraph is repeated on Badges, Library, LessonDetail, SessionPlayer; leave those.
- `frontend/src/pages/Setup.tsx`, `avatars.ts`, `ProfilePicker.tsx`, `profile.ts` -- reuse the form fields, avatar list and picker.
- `frontend/src/api/queries.ts`, `client.ts`, `schema.d.ts` -- new mutations; run `npm run gen:api`.
- `backend/tests/test_parent.py` -- the existing profile and PIN tests; extend, or add `test_profiles.py`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/parent/service.py`, `schemas.py`, `api/profiles.py`, `api/parent.py` -- create/patch/delete Profile, change PIN, 4-Profile and last-Profile guards -- FR-18
- [x] `backend/hoctap/cli.py`, `parent/service.py` -- `reset-pin` command: prompt for new PIN, hash, clear lockout, bump `session_version`
- [x] `backend/hoctap/learning/` -- progress purge helper used by delete -- no orphan rows
- [x] `frontend/src/pages/Settings.tsx` (+ css, `App.tsx`, `ParentHome.tsx`) -- profile list with add/edit/remove, PIN form, auto-play switch per child -- the AC
- [x] `frontend/src/pages/Home.tsx` (+ long-press hook, `phrases.vi.json` if spoken) -- 🔒 with 2 s long-press, short tap inert -- UX-DR6
- [x] `backend/tests/`, `frontend/src/pages/*.test.tsx` -- cover every I/O Matrix row

**Acceptance Criteria:**
- Given the PIN session, when I open Settings, then I can add, edit or remove Profiles (at most 4), change the PIN, and toggle auto-play per child.
- Given more than 1 Profile, when the child opens the app, then the picker shows; given exactly 1, it does not.
- Given the child Home, when 🔒 is held 2 seconds, then the PIN gate opens; a short tap does nothing.
- Given a removed Profile, when its id is queried for badges or sessions, then it is not found and no `progress_*` row references it.
- Given auto-play off for a child, when a Problem opens, then its instruction does not auto-play (Story 2.9 gate already reads it).

## Verification

**Commands:**
- `cd backend && ruff check . && pytest tests/test_parent.py tests/test_sessions.py tests/test_badges.py` -- expected: pass
- `cd frontend && npm run gen:api && npx tsc -b && npx eslint . && npx vitest run --pool=vmThreads src/pages` -- expected: pass

**Manual checks (if no CLI):**
- Long-press 🔒 on a phone-width viewport: opens at 2 s, not at 1 s; the click after a completed press is suppressed.

## Implementation Notes

- (2026-09-29) 4-Profile cap is enforced inside the INSERT itself (`INSERT ... SELECT ... WHERE count < 4`), so concurrent adds cannot exceed it. Delete purges progress via `learning/progress.py: delete_profile_progress` in the same transaction; the last-Profile check is a count inside that transaction (two simultaneous deletes could theoretically race; accepted for a single-parent LAN app).
- PIN change validates the new-PIN confirmation, then the current PIN through the existing lockout counter, then bumps `session_version` and re-issues the caller's cookie. `hoctap reset-pin` (CLI only, no HTTP route) prompts twice with hidden input, validates with `Pin`, clears the lockout and bumps `session_version`.
- Home 🔒 uses a new `hooks/useLongPress.ts` (2000 ms); a short tap does nothing and the button has no click handler, so it is not keyboard-reachable (follows "short tap does nothing").
- Gaps: the 2-second hold was tested only with fake timers, not on a real phone-width viewport.

### 2026-09-29: independent re-verification

- `ruff check .` clean. `pytest tests/test_profiles.py tests/test_parent.py tests/test_sessions.py tests/test_badges.py tests/test_app.py tests/test_library.py` — 236 passed.
- Frontend `tsc -b` and `eslint .` clean. `vitest run` on Settings, Home, ParentHome and ParentLogin with `--pool=vmThreads` — 46 passed.
- The implementing agent also reported 4 failures in `ExtractionPage.test.tsx` and `ProblemPlayer.speaker.test.tsx` that it showed fail identically with its changes stashed; not re-verified by me. Not run: the full backend and frontend suites in one pass.
