---
title: 'Story 1.2: First-run setup with PIN and first Child Profile'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_commit: 'tree:cfbaea27e2fab7af4af225fce15c858d37dd42d6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Parent Area and the build routes must be protected by a PIN before any other parent feature exists. The very first run must also create the PIN and Bin's profile.

**Approach:** Add `parent_settings` and `parent_profiles` tables. A first-run setup API and screen create the PIN (bcrypt) and the first Child Profile. A PIN login issues a signed httpOnly cookie with a 30-minute sliding idle expiry. A shared `require_parent` dependency guards `/api/v1/parent/*` and `/api/v1/build/*`.

## Boundaries & Constraints

**Always:**
- The PIN is exactly 4 digits and is stored only as a bcrypt hash in `parent_settings`.
- The cookie `hoctap_parent` is httpOnly, `SameSite=Strict`, and `Secure` when the request is HTTPS. It is signed with a random key stored in `data/secret.key`, created on first start and never kept in the DB or the repo.
- Idle expiry is 30 minutes. Every authenticated parent request re-issues the cookie, so the expiry slides.
- Only the `parent` module writes `parent_*` tables, through its service functions, in one transaction. Routers hold no logic.
- User-facing messages are in Vietnamese and use the error envelope.
- Brute-force guard: after 5 wrong PINs in a row, login returns 429 `PIN_LOCKED` for 5 minutes. The count is kept in `parent_settings`.

**Never:**
- No profile editing, no second profile, no PIN change (those are Story 4.1).
- No child Home or design tokens (Epic 2). Parent screens get plain, readable styling only.
- No user accounts or passwords beyond the single family PIN.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Status, fresh | `GET /api/v1/setup/status`, no PIN | `200 {"setup_required": true}` | N/A |
| Setup ok | `POST /api/v1/setup` `{pin:"1234", pin_confirm:"1234", profile:{name:"Bin", avatar:"cat", grade:1}}` | `201`, PIN hash + profile stored, parent cookie set | N/A |
| Setup mismatch | pin ≠ pin_confirm | `422 PIN_MISMATCH` "Hai mã PIN không khớp" | nothing stored |
| Setup bad input | pin `"12a4"`/`"123"`, grade 0/6, empty name, unknown avatar | `422 VALIDATION_ERROR` | nothing stored |
| Setup twice | PIN already exists | `409 SETUP_DONE` | existing data unchanged |
| Guard before setup | any `/api/v1/parent/*` or `/api/v1/build/*` (not setup) | `403 SETUP_REQUIRED` | N/A |
| Login ok | `POST /api/v1/parent/login {pin}` correct | `204` + cookie; failure counter reset | N/A |
| Login wrong | wrong PIN | `401 PIN_INCORRECT` "Mã PIN chưa đúng" | counter +1 |
| Lockout | 6th attempt after 5 consecutive wrong ones, within 5 minutes | `429 PIN_LOCKED` (even with the correct PIN) | lock clears after 5 minutes |
| Guarded, no/expired/tampered cookie | `GET /api/v1/parent/session` | `401 UNAUTHORIZED` | N/A |
| Guarded, valid cookie | `GET /api/v1/parent/session` | `200 {"authenticated": true}` + refreshed cookie | N/A |
| Logout | `POST /api/v1/parent/logout` | `204`, cookie cleared | N/A |
| Profiles | `GET /api/v1/profiles` | `200 [{id,name,avatar,grade}]` (no auth needed) | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/app.py` -- `build_api_router()` includes routers. Add the setup, parent and profiles routers here.
- `backend/hoctap/api/errors.py` -- `AppError(status, code, message)`. Raise it from services.
- `backend/hoctap/db/engine.py` / `db/alembic/versions/0001_baseline.py` -- add migration `0002_parent` after the baseline. `app.state.engine` holds the engine.
- `backend/hoctap/config.py` -- `Settings.data_dir` gives the location of `secret.key`.
- `backend/hoctap/parent/` -- currently empty. New: `models.py`, `service.py` (setup, login, lockout, profiles), `auth.py` (signing and the `require_parent` dependency).
- `frontend/src/App.tsx` -- routes: add `/setup`, `/parent/login` and `/parent`. `frontend/src/api/client.ts` provides `apiGet`. Add `apiPost` next to it, and regenerate `schema.d.ts` with `npm run gen:api`.
- `frontend/src/pages/Home.tsx` -- if `setup_required`, redirect to `/setup`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- add `bcrypt` and `itsdangerous` (the latest stable versions, pinned exactly) and a UUIDv7 helper (the stdlib `uuid.uuid7` exists on Python 3.14).
- [x] `backend/hoctap/db/alembic/versions/0002_parent.py` + `backend/hoctap/parent/models.py` -- `parent_settings` (a single row: `pin_hash`, `failed_attempts`, `locked_until`, timestamps) and `parent_profiles` (`id` as UUIDv7 text, `name`, `avatar`, `grade` 1–5, `created_at`).
- [x] `backend/hoctap/parent/service.py` -- `setup_status`, `complete_setup`, `verify_pin` (with lockout), `list_profiles`; the allowed avatar keys are `cat`, `dog`, `rabbit`, `bear`, `fox`, `panda`.
- [x] `backend/hoctap/parent/auth.py` -- secret-key load/create, sign and verify the cookie with a timestamp, `require_parent` (returns 403 `SETUP_REQUIRED` or 401, and refreshes the cookie).
- [x] `backend/hoctap/api/setup.py`, `api/parent.py`, `api/profiles.py` -- thin routers, and a stub `GET /api/v1/build/status` guarded by `require_parent` (it returns `{"state":"idle"}`), so the guard is exercised on the build prefix.
- [x] `backend/tests/test_parent.py` -- one test per I/O matrix row. Test the time-based expiry and the lockout expiry with an injectable clock.
- [x] `frontend/src/pages/Setup.tsx`, `ParentLogin.tsx`, `ParentHome.tsx` + `App.tsx` routes + `api/client.ts` `apiPost` -- the Setup screen collects the PIN twice, the name, one of the 6 avatars and the grade, then goes to `/parent`. The login screen shows a 4-digit input and the Vietnamese errors. ParentHome shows "Khu vực phụ huynh" (Parent Area) and a logout button. Home redirects to `/setup` when setup is required.
- [x] `frontend/src/pages/*.test.tsx` -- tests for: setup validation (mismatch message), the login error message, and the redirect to `/setup`.

**Acceptance Criteria:**
- Given a fresh database, when the app opens in a browser, then it redirects to `/setup`. After submitting a valid form, the Parent Area shows, and reloading the page stays authenticated.
- Given the parent cookie is older than 30 minutes of inactivity, when a guarded route is called, then it returns 401 and the UI redirects to `/parent/login`.

## Implementation Notes

- Extra files beyond the Code Map: `hoctap/ids.py` (UUIDv7 `new_id`, `utc_now`, ISO helpers, `Clock` type), `hoctap/parent/schemas.py` (request/response models), `hoctap/api/deps.py` (`get_engine`, `get_now`), `hoctap/api/build.py` (build stub), `frontend/src/api/errors.ts` (`authRedirect`, `errorMessage`), `frontend/src/pages/avatars.ts`, `frontend/src/test/render.tsx` (router + fetch test helpers).
- Injectable clock: `app.state.clock` (default `utc_now`). Cookie signing uses a `TimestampSigner` subclass whose `get_timestamp()` reads that clock, so idle expiry is testable; `unsign(max_age=1800)` also rejects future timestamps. The cookie also carries `Max-Age=1800`.
- `secret.key` is created in the lifespan (before the DB engine) via temp file + fsync + `os.replace`, mode 0600, 64 hex chars; an empty file is regenerated, unreadable/short content raises a clear `RuntimeError`.
- The cookie payload is `parent:<session_version>` (`parent_settings.session_version`). Logout with a valid cookie increments it, invalidating every issued cookie; logout without one only clears the cookie.
- Lockout writes are single atomic `UPDATE ... WHERE not locked ... RETURNING` statements (bcrypt runs outside any transaction), so parallel wrong attempts are each counted once and attempts during a lock change nothing.
- Lockout: the 5th consecutive wrong PIN still returns 401 and sets `locked_until = now + 5 min`; attempts before that time return 429 even with the right PIN. After expiry the counter restarts at 0. A correct PIN resets it.
- `/api/v1/parent/login` and `/logout` return 403 `SETUP_REQUIRED` before setup (they are parent routes); they are not otherwise guarded by the cookie.
- Setup checks `SETUP_DONE` before `PIN_MISMATCH`; the insert race is caught as `IntegrityError` → 409. Names are NFC-normalized, trimmed, 1–40 chars, reject any Unicode C* character and need at least one printable non-space character. PIN pattern is `[0-9]{4}` (no non-ASCII digits).
- Frontend: a `QueryCache.onError` in `App.tsx` redirects any query failing with 401 `UNAUTHORIZED` → `/parent/login` and 403 `SETUP_REQUIRED` → `/setup`; the session query refetches on window focus. The Setup form checks format and mismatch client-side before POSTing.
- `tests/test_app.py` fresh-DB test updated for revision `0002_parent` and the two new tables. Tests set `service.BCRYPT_ROUNDS = 4` for speed (production is 12).

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Lockout counter race: parallel wrong logins lose increments | medium | read-then-write in deferred txn → patch (BEGIN IMMEDIATE / atomic increment) |
| 2 | SQLITE_BUSY during verify returns 500 and attempt not counted | medium | same root as 1 → patch |
| 3 | Fixed 5-min lockout allows ~1,440 guesses/day on a 4-digit PIN | medium | policy is in frozen intent → defer (escalating lockout, revisit with PIN change in Story 4.1) |
| 4 | Logout / PIN change doesn't invalidate a copied cookie | medium | stateless constant payload → patch (session_version in parent_settings, bumped on logout) |
| 5 | test_logout only clears client jar | medium | passes regardless of server → patch with 4 |
| 6 | Crash between O_EXCL create and write leaves empty secret.key; non-ASCII key → unclear traceback | medium | startup bricked → patch (temp+fsync+replace, regenerate if empty, clear error) |
| 7 | Secure flag behind TLS-terminating proxy | false | AD-12: app terminates TLS itself; no proxy |
| 8 | Name of only invisible/control chars accepted | low | trivial validator → patch |
| 9 | Setup done + mismatched PINs → 422 not 409 | low | reorder check → patch |
| 10 | `GUARDED` mislabels login/logout; docstring overstates | low | future misuse locks out login → patch (rename, docstring) |
| 11 | No UI path to Parent Area; Home flashes before redirect; ignores status error | low | add link on placeholder Home, loading/error states → patch |
| 12 | ParentLogin doesn't redirect authenticated parent; errorMessage can show English statusText | low | patch |
| 13 | Logout navigates even when POST fails | medium | UI shows logged out while cookie valid → patch (onSuccess) |
| 14 | ParentHome non-auth error has no retry | low | patch (retry button) |
| 15 | Session not polled while idle on /parent | low | reject (next action redirects) |
| 16 | apiGet forces GET | false | intended API; no caller passes method |
| 17 | apiPost Content-Type untested; Setup redirect/409 and ParentLogin 403 untested; backend gaps (name length, extra fields, lock doesn't extend, ordering, logout w/o cookie) | medium | verification gaps → patch |
| 18 | Concurrent-setup IntegrityError path untested | low | defer per reviewer (button disabled while pending) |

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd frontend && npm run gen:api && npm run build && npm run test && npm run lint` -- expected: success
