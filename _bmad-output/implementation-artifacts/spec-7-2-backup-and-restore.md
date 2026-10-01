---
title: 'Story 7.2: Backup and restore'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: 'a11f301db3d6a268d2ef5376de987f8e2b04d9b1'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The only copy of Bin's progress is `data/hoctap.db` (WAL, plus `-wal`/`-shm`) on the home PC. There is no backup, no restore, no `db_epoch`, no maintenance mode; Settings only has profiles and PIN (NFR-7, AD-14).

**Approach:** Add a consistent single-file `.db` backup made with the SQLite online backup API while the app runs (Parent Area "Sao lưu" download, plus `hoctap backup`), and a restore that validates the file, refuses during a build, takes an automatic safety backup, swaps the database in maintenance mode, migrates, rotates the cookie key and bumps `db_epoch` so tablets drop stale outbox events.

## Boundaries & Constraints

**Always:** Backup = `sqlite3.Connection.backup()` into a temp file, then `PRAGMA integrity_check` on the copy; never copy the live `.db`/`-wal` by file. The backup contains the whole database only (progress, profiles, parent_settings incl. PIN hash, curated overrides, concepts, guides, error reports, catalogue, build tables). Restore order: validate upload (SQLite header, `integrity_check`, has `alembic_version`) -> refuse if its revision is newer than the app's head (name both) -> refuse if a build run is active (`RunManager._busy` and `build_runs` active rows, since the CLI builder is a separate process) -> require typed confirmation `KHÔI PHỤC` and a correct PIN cookie -> safety backup of the current DB to `<data_dir>/backups/pre-restore-<utc>.db` -> maintenance (503 `maintenance` envelope for all routes except health) -> dispose engine, replace file, delete stale `-wal`/`-shm` -> `run_migrations` (older backups upgrade) -> rotate `secret.key` and `app.state.secret_key` -> new random `db_epoch` -> reopen engine -> leave maintenance. On any failure after the swap starts, put the safety backup back and leave the app working. Restored PIN/sessions: the restored PIN applies; all cookies are invalid after key rotation.


**Human decisions (Anh, 2026-09-30):** (1) A backup contains the database only (progress, profiles, PIN, curated overrides, Concepts, Guides, error reports); assets, `build/`, `logs/` and source PDFs are regenerable and not included. (2) A backup is a browser download of an unencrypted file the parent keeps wherever they choose; the app keeps no other copy except the automatic safety backup taken before a restore (in `data/backups/`). (3) Restore is available from the Parent Area web page, behind the PIN session, a typed confirmation and the automatic safety backup, with the server briefly in maintenance mode, exactly as the acceptance criteria describe. (4) No scheduled or automatic backups: manual only. (5) Restoring onto another machine carries the database only; that machine keeps its own `secret.key`, certificates and assets. The story stays one story.

**Never:** Touch the real `data/` in tests (temp dirs only). Restore over an unverified file. Restore while a build is running. Copy the live DB with `shutil`. Put default backups inside a directory the restore replaces. Log the PIN hash or backup contents. Include `secret.key`, `assets/`, `build/`, `logs/` or `source_dir` (regenerable via the builder; Architecture "Deferred").

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Backup while a child answers | App serving writes | Consistent `.db` download named `hoctap-backup-<YYYYMMDD-HHMMSS>.db`; server keeps serving | Copy fails integrity: 500 envelope, temp deleted |
| Backup, no PIN cookie | Any request | 401 envelope; nothing written | N/A |
| CLI backup | `hoctap backup --to <dir>` | Verified file written outside `data_dir` by default check (warn if inside) | Missing dir: created; unwritable: exit 1 |
| Valid restore | Same-head backup, no build, typed phrase | Safety backup, swap, migrate, key rotated, `db_epoch` changed, 200 | N/A |
| Older backup | Head < app head | Migrated to head after swap; succeeds | Migration error: rolled back to safety backup, 500 |
| Newer backup | Head > app head | Refused before anything changes | 409 `backup_newer` |
| Not a database / corrupt | Random or truncated file | Refused | 422 `backup_invalid` |
| Build running | Active run | Refused, nothing changed | 409 `build_running` |
| Wrong/missing phrase | Confirm text differs | Refused | 422 |
| Stale tablet events | Outbox event stamped with old `db_epoch` | Server 409 `stale_epoch`; client discards it and shows a notice | Unstamped legacy event: accepted once |
| Requests during restore | Any non-health call | 503 `maintenance` with retry hint | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/db/engine.py` -- `create_db_engine`, `run_migrations`; add backup/verify helpers in new `backend/hoctap/parent/backup.py` (architecture names `parent/backup`).
- `backend/hoctap/app.py` -- lifespan owns `app.state.engine`/`secret_key`; add maintenance middleware and swap-in-place under a lock.
- `backend/hoctap/parent/auth.py` (`load_or_create_secret`, `secret.key`), `parent/service.py` (`session_version`, `reset_pin`), `parent/models.py` -- key rotation; new `db_epoch` column via Alembic `0020_db_epoch.py` (head is `0019_full_run`).
- `backend/hoctap/builder/jobs.py` -- `ACTIVE_STATUSES`, `RunManager._busy`; expose a public `is_busy()`.
- `backend/hoctap/api/parent.py`, `api/sessions.py` (`post_events`), `api/deps.py` -- backup/restore routes; epoch check on events.
- `backend/hoctap/cli.py` -- `backup`, `restore` subcommands (model on `_reset_pin`, `_open_db`).
- `frontend/src/pages/Settings.tsx` -- "Sao lưu" / "Khôi phục" section (confirm dialog pattern from profile delete).
- `frontend/src/offline/outbox.ts`, `outboxStore.ts`, `api/client.ts` -- stamp events with `db_epoch`, drop stale ones.

## Tasks & Acceptance

**Execution:**
- [x] `parent/backup.py` -- `make_backup(engine, dest)`, `verify_backup(path)` (header, integrity, revision compare against Alembic head), `restore(app, upload)` with safety backup and rollback
- [x] `0020_db_epoch.py` -- `parent_settings.db_epoch` (random token); `app.py` maintenance middleware; `RunManager.is_busy()`
- [x] `api/parent.py` -- `POST /api/v1/parent/backup` (file response), `POST /api/v1/parent/restore` (multipart + `confirm`); regenerate `schema.d.ts`
- [x] `api/sessions.py` + outbox -- `db_epoch` on session/event responses, stale-event 409 and client discard
- [x] `cli.py` -- `hoctap backup [--to DIR]`, `hoctap restore FILE` (offline; refuses if the port is listening or a build is active)
- [x] `Settings.tsx` -- backup button, restore file picker, typed confirmation, maintenance/relogin message
- [x] Tests in `backend/tests/test_backup.py`, `frontend/src/pages/Settings.test.tsx`, outbox tests -- every matrix row; concurrent-writer backup; rollback on injected migration failure; all on temp dirs

**Acceptance Criteria:**
- Given the PIN session, when I tap "Sao lưu", then a verified single `.db` downloads and the app keeps serving.
- Given a valid backup and no build, when I type the phrase and confirm "Khôi phục", then a safety backup exists, data equals the backup, I must sign in again, and old tablet events are discarded.
- Given a newer, corrupt or build-blocked case, when I restore, then nothing on disk changes.

## Design Notes

`db_epoch` lives in the DB but is regenerated (random token, not a counter) after every restore so an old backup never reuses a value. Backups hold the PIN hash: files should be treated as private.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_backup.py -q && uv run ruff check .` -- run pytest in the background
- `cd frontend && npx vitest run --pool=vmThreads && npm run build`

## Orchestrator's Independent Audit

(2026-10-01) 3 parallel reviewers (Blind Hunter, Verification Gap, Edge Case Hunter) audited this story given its stakes: this is the family's only backup mechanism, with real, irreversible data-loss and theoretical auth-bypass exposure. Findings, highest priority first:

1. **[HIGH — correctness/concurrency] Cross-process race between a restore and the CLI builder.** `is_busy()` is checked once, early in `restore()`, before `make_backup()` (can take real time) and before `maintenance.begin()` (up to a 15s drain) — there is no re-check immediately before `_swap()`. Worse, `MaintenanceMiddleware`/`Maintenance.begin()` only throttle this web app's own HTTP requests; the CLI builder is a separate OS process with its own SQLite connection and is never blocked or even detected. Concrete scenario: a restore passes the early `is_busy()` check, then a `hoctap build` starts and begins writing; `_swap()` later calls `engine.dispose()` + `os.replace()` out from under the builder's open fd, silently losing its writes and/or corrupting state. Separately, the CLI's own `hoctap restore` only guards against the server via a TCP port-listening probe (`_port_listening()`), a check-then-act race with no OS-level lock (e.g. `flock` on a pidfile) preventing two concurrent `hoctap restore` invocations, or a `hoctap serve` started in the gap, from both touching `db_path` at once. **Fix:** re-check `is_busy()` immediately before `_swap()` inside the maintenance window, and have the builder process honor a shared filesystem lock that both the web app and CLI respect.
2. **[HIGH — data integrity + theoretical auth bypass] No crash-recovery for a restore interrupted by a real process kill.** The failure-handling is a Python `try/except BaseException` around swap→migrate→rotate-key→bump-epoch→integrity-check — this only catches in-process exceptions, not a SIGKILL/OOM-kill/power-loss between `_swap()`'s `os.replace()` and the end of that block. On restart, `lifespan()` just opens whatever file is at `db_path` and migrates it; there is no marker file recording "a restore was interrupted" and no automatic rollback-replay on boot. If the crash lands after the file swap but before `_write_secret`/`bump_db_epoch`, the restored database goes live with the **old**, un-rotated `secret.key` — a parent's pre-restore cookie remains cryptographically valid (`cookie_valid()` only checks the HMAC signature plus `session_version`) and could authenticate against the newly-restored (possibly different) family's data without ever re-entering the PIN, if `session_version` happens to coincide. Narrow window, but zero mitigation. **Fix:** write a small `restore.inprogress` marker (containing the safety-backup path) before `_swap()`, and have `lifespan()` check for it on every startup, replaying the rollback if found.
3. **[MEDIUM] `verify_backup()` doesn't assert expected tables exist.** It checks the SQLite header, `PRAGMA integrity_check`, and that `alembic_version` holds a known revision — but never checks that real tables (e.g. `parent_settings`) exist. A crafted file with a valid header + a correctly-stamped `alembic_version` but no other tables would pass validation and get swapped in; the subsequent `bump_db_epoch()` UPDATE would then throw on the missing table, triggering the existing rollback path — so the end state self-heals, but only incidentally, via a pointless maintenance-mode round-trip. **Fix:** have `verify_backup()` also assert a known table exists.
4. **[LOW] Rollback failures are logged, not surfaced.** `_rollback()`'s own exception path only logs ("restore rollback failed; the safety backup is at %s"); an operator not watching logs could be left with a dead `hoctap.db` with no visible error beyond the original 500. Consider a sentinel file given the stakes.
5. **[LOW, confirmed non-issue, no action needed]** Safety-backup failure (`make_backup()` raising on any `sqlite3.Error`/`OSError`) happens before `maintenance.begin()`/`_swap()`, so a disk-full/permission failure here correctly aborts with nothing on disk changed — confirmed sound by code reading, but per the established pattern (see point 6) this needs a test, since it was previously unverified.
6. **6th occurrence of the recurring missing-migration-upgrade-test pattern**, now for `0020_db_epoch.py` — add `test_migration_0020_up_and_down` to `backend/tests/test_app.py` per the established template.
7. **[Note, no action]** Cookie-key rotation correctly invalidates all sessions in a single-process deployment (the model this app uses); would need a shared-cache fix only if ever deployed multi-worker.

Priority for fix dispatch: items 1 and 2 are the ones that would block merge regardless of how clean the rest of the suite looks, given this is the family's only backup/restore path with real data-loss and (narrow-window) auth-bypass stakes. Items 3, 6 next. Items 4, 5, 7 are polish/test-coverage, not design defects.

## Implementation Notes

- (2026-09-30) Migration `0020_db_epoch` adds `parent_settings.db_epoch` (a random 32-hex token). **Backup:** `POST /api/v1/parent/backup` (PIN session) downloads a single verified `.db` made with the SQLite online backup API into a temp file and checked with `PRAGMA integrity_check`; the live database keeps serving and is never file-copied. **Restore:** `POST /api/v1/parent/restore` (multipart file plus the typed phrase `KHÔI PHỤC`) validates the upload, refuses a backup from a newer app version or a running build, takes a safety backup to `data/backups/pre-restore-<utc>.db`, puts the server in maintenance mode (503), swaps the file, migrates, rotates `secret.key`, sets a new `db_epoch`, and rolls back to the safety backup on any failure after the swap starts. CLI: `hoctap backup [--to DIR]` and `hoctap restore FILE [--yes]` (refuses if the port is listening, a build is active, or the phrase is wrong). Database only, unencrypted download, web restore, no scheduled backups, database-only onto another machine: Anh's decisions.
- Stale tablet answers: session start, bundle and event responses carry `db_epoch`; an event stamped with an old epoch gets 409 `STALE_EPOCH` before anything is written (unstamped legacy events are accepted); the frontend outbox stamps each event with its Session's epoch, drops stale ones on flush and shows a notice. Settings gets a "Sao lưu và khôi phục" section with a confirm dialog. New dependency: `python-multipart==0.0.20`.
- Added in review: the restore upload had no size limit; it is now copied in chunks with a 256 MB cap (`backup.MAX_UPLOAD_BYTES`, 413 `BACKUP_TOO_LARGE`, the partial file removed) and `test_restore_refuses_an_oversized_upload`. The web framework's own temporary multipart copy is still uncapped.
- Gaps: never run on a real machine or under real WAL load, and the restore flow was not tried in a browser; assets, `build/`, `logs/` and source PDFs are not in a backup (decision); the CLI port check assumes the configured `port`/`tls_port`; a crashed CLI build that left a `running` row blocks restore until the row settles; a request that never finishes makes restore give up with 409 `RESTORE_BUSY` instead of forcing the swap; error codes are UPPER_SNAKE (`BACKUP_NEWER`, `BACKUP_INVALID`, `BUILD_RUNNING`, `MAINTENANCE`, `STALE_EPOCH`, `CONFIRM_REQUIRED`); a foreign SQLite file with an `alembic_version` table is reported as `BACKUP_NEWER`; the per-session epoch is remembered in localStorage (50 entries) or memory.

### 2026-09-30: independent re-verification

- Safety: the real `data/` directory was untouched by the work (database file unchanged since Sept 27 and at its original migration, no `data/backups`, no `secret.key`). My own adversarial script on a throwaway temp dir passed 28 of 28 checks: garbage, empty, truncated, fake-header, newer-version, wrong and empty confirmation, and no-PIN uploads were all refused with the live data unchanged and the server healthy; a legitimate restore reverted the data, rotated the key and epoch, created the safety backup and invalidated the old login.
- `ruff check .` clean. `pytest tests/test_backup.py tests/test_app.py tests/test_parent.py tests/test_profiles.py tests/test_sessions.py tests/test_runs.py tests/test_full_run.py tests/test_worksheets.py` — 299 passed; after the size-cap change `tests/test_backup.py tests/test_app.py` — 90 passed. The implementing agent reported the full backend suite at 1114 passed. Regenerated OpenAPI file and types are unchanged.
- Frontend `tsc -b` and `eslint .` clean; `src/pages` + `src/offline` + `src/print` with `--pool=vmThreads`: 341 passed, 4 failed — the three known pre-existing `ExtractionPage` failures and `ProblemPlayer.speaker.test.tsx`, which needs `--pool=threads`; run alone with `--pool=threads`, `speech.test.ts` and `ProblemPlayer.speaker.test.tsx` pass (31 tests).

### 2026-10-01: fixes for the orchestrator's audit (points 1-6)

- **Cross-process lock** (point 1): new `hoctap.parent.backup.db_lock(data_dir, blocking)`, an exclusive OS-level lock on `<data_dir>/hoctap.lock` (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows — this app installs as a Windows service, so both had to work). `restore()` now re-checks `run_manager.is_busy()` AND takes this lock (`blocking=False`) inside the maintenance window, immediately before `_swap()` — a failed acquire or a busy manager at that exact point raises 409 `DB_LOCKED` instead of racing a build. The CLI builder (`_open_db`, `_run_build`, and `hoctap build catalogue`'s own inline open, all in `cli.py`) now holds the same lock (`blocking=True`, waits) for as long as it has the database open. `hoctap serve`'s `lifespan()` also takes it (blocking) around its own startup engine-open/migrate, so a server started mid offline-restore waits instead of racing it; the lock is released before the server starts actually serving, so the builder and a running server can still work side by side as designed. `hoctap restore`'s old TOCTOU (`_port_listening()` alone) is closed the same way, since it goes through the shared `restore()`.
- **Crash recovery** (point 2): `restore()` now writes `<data_dir>/restore.inprogress` (JSON: the safety-backup path and the pre-rotation `secret.key`, hex-encoded) right after taking the lock, before `_swap()`, and removes it once the restore (or its rollback) finishes. New `hoctap.parent.backup.replay_interrupted_restore(settings)` is called from `app.py`'s `lifespan()`, inside the same startup lock, before the database is opened: if the marker is present, it copies the safety backup back over the live db and restores the old `secret.key` — the exact rollback a real process kill between `_swap()` and key rotation would otherwise skip, including the narrow stale-cookie window the audit flagged. If the replay itself cannot complete (e.g. the safety backup is missing), it leaves the marker in place, writes the point-4 sentinel, and raises — the app refuses to boot on an unknown-state database rather than serving one.
- **`verify_backup()` table check** (point 3): now also asserts a `parent_settings` row-having table exists via `sqlite_master`, alongside the header/integrity_check/`alembic_version` checks, so a crafted file with a valid header and a correctly-stamped `alembic_version` but no real tables is rejected directly (422 `BACKUP_INVALID`) instead of only self-healing via the `bump_db_epoch()` crash + rollback round-trip.
- **Rollback-failure sentinel** (point 4): both `_rollback()` (in-process) and `replay_interrupted_restore()` (startup) now write `<data_dir>/restore.rollback_failed` on failure, in addition to the existing `log.exception`.
- `_rollback()`'s file-copy-plus-key-restore logic was factored into `_restore_file_and_key()`, shared with `replay_interrupted_restore()`, so both paths do byte-for-byte the same recovery.
- Added `test_migration_0020_up_and_down` to `test_app.py` (point 6 pattern) and 17 new tests to `test_backup.py` covering: the table check, the safety-backup-failure-aborts-before-touching-anything path (byte-compared live db file, proved `maintenance.begin()` was never even called), the pre-swap re-check (both a held lock and a build starting in the make_backup/drain window), the rollback sentinel, marker-replay (success, no-op, end-to-end via `lifespan()`, and the unrecoverable-raises-and-leaves-the-marker case), the lock's own exclusivity, and that `hoctap build` and `hoctap restore` now mutually exclude each other through it.
- Not done: did not add a lock around `hoctap backup`/the backup HTTP route (read-only via SQLite's own backup API, already safe to run concurrently with anything) or around `reset_pin`/other CLI commands that write outside a build context (out of the audit's scope, and PIN reset's own window is far shorter and not restore-adjacent). Did not change the already-existing `is_busy()`/`build_runs`-row check itself, since it is still the main signal for "a build is active" cross-process via the shared table; the lock only closes the race *around* that check, not the check itself. Did not add retry/backoff tuning for the lock (CLI builder waits indefinitely at `blocking=True`, matching how `is_busy()` already made restore wait on a build via the drain/retry UI already in place) — a bounded wait felt like scope creep for a bug-fix pass. Verified: `ruff check .` clean; `pytest tests/test_backup.py tests/test_app.py` — 108 passed; full backend suite `pytest -q` — 1147 passed, 0 failed.
