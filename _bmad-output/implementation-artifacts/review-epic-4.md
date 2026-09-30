# Code review: Epic 4 (Stories 4.1-4.4), 2026-09-30

Range `a2c950d^..b544e9f`, backend and frontend source and tests (generated OpenAPI files excluded). Four independent layers reviewed against the four story specs. Every finding below was checked against the code where it mattered; reviewer severities were disregarded.

## Decision needed

- [x] [Review][Decision] **RESOLVED: keep the frozen list (AD-9); Story 4.4's matrix row corrected.** A parent-hidden or parent-reported Problem is still served inside an in-progress Session** [medium] `sessions.py:get_bundle` skips only Problems that vanished entirely (`ProblemNotFound`), by design: the Session freezes its Problem list (AD-9, "later content changes don't affect an in-progress Session"). New Sessions and the Library exclude hidden Problems (`visible_to_child`), but a Session already started (including one resumed through "Tiếp tục" days later, or an Assignment or Retry Session already frozen) keeps serving a Problem a parent reported for a wrong answer key, and grades the child against it. Story 4.4's I/O matrix ("Reported mid-Session: existing `get_bundle` skip applies; Problem no longer served") assumed the opposite and is not what the code does. Options: keep AD-9 and correct the spec's expectation / skip non-visible Problems in `get_bundle` so a parent report takes effect immediately.

## Patch

- [ ] [Review][Patch] **Deleting a Profile leaves its Assignments behind** [medium] `learning/progress.py:delete_profile_progress` purges events, stars, retry items, badges and sessions but not `progress_assignments` (added by 4.3). Violates 4.1's "no `progress_*` row references it". Add the table to the purge and extend `test_delete_purges_progress`. Found by all four layers.
- [ ] [Review][Patch] **Test gaps** [medium] (a) no `SessionPlayer` test that the child's `FlagButton` is mounted and posts the current Problem id and profile id; (b) `ASSIGNMENT_REF_MISMATCH` is untested (different lesson, and non-lesson refs); (c) `test_change_pin_wrong_current_locks` accepts 401 or 429 for the first attempts and does not pin the transition.
- [ ] [Review][Patch] **Home assignment card can start two Sessions and keeps a stale card** [low] Double-tapping "Bài hôm nay" while `startSession` is pending can create two linked Sessions; on `ASSIGNMENT_DONE` or 404 the stale card stays. Guard on `isPending` and refresh Home on error.
- [ ] [Review][Patch] **`CHUNK_SIZE` duplicated in `assignments.py`** [low] Redefined because `sessions.py` imports `assignments`; "Phần i/n" on the card drifts if the real chunk size changes. Move the constant somewhere both can import.

## Rejected

- Unauthenticated child flag route can be spammed or aimed at any Problem id: specified behaviour (no PIN, epic); reports dedupe per Problem, and the effect is review-queue noise only.
- No keyboard path to the lock: the 2-second hold is the specified child-proof gate; a parent can go to `/parent`.
- Replay- or retry-mode Session marking an Assignment done: no longer reachable; a lesson ref is required and mode is now derived from the ref (Epic 3 fix).
- Duplicate Assignments for the same Lesson and date; unbounded future dates; a done Assignment cannot be deleted; deleting one in progress gives no warning: low, recoverable, specified (done cannot be deleted, 409).
- Dashboard loads every completed Session for the Profile: unbounded but cheap on SQLite for one family; the "last 10 mistakes" list can legitimately reach outside the 28-day window, so narrowing the query changes behaviour.
- Accuracy counts unattempted Problems as first-try correct: same definition Story 2.10's Session summary already uses.
- Dashboard accuracy edge cases (non-dict payload, Problems missing from the effective set): server-written data; low.
- Weekly minutes rounding, recent-mistake ordering within a Session, note length checked before trimming, repeat parent report drops its new note: cosmetic or specified.
- Migration 0017 has no foreign keys or CHECKs: consistent with every other `progress_*` table (`profile_id` is plain text throughout).
- Layering (`learning` importing `api.errors`, private `_profile_exists`): existing pattern across the codebase.
- `change_pin` allows new PIN equal to old; concurrent change-PIN race; `reset-pin` tracebacks on Ctrl-C or piped input: low.
- Query caches not invalidated after profile delete or regrade: low.
- Concepts shown as raw ids, mistakes keep reported rows, 🚩 lives in `SessionPlayer`: disclosed in the 4.4 notes.
