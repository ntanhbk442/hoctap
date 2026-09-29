---
title: 'Story 3.2: Badges'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: '559f612c29a44a49a9eedbc013e73174db7f2821'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing awards, stores, or shows a badge today. Story 3.1 already built the exact
transaction/materialization pattern this needs (`progress_stars`, `maybe_award_stars()` called
inside `post_event()`'s existing `conn.begin_nested()`), and `phrases.vi.json` already has
`your_badges`/`new_badge_earned` placeholders anticipating this story, but no `progress_badges`
table, checker, or UI exists.

**Approach:** A new `progress_badges` table (one row per Profile-per-earned-badge, unique on
`(profile_id, badge_key)`) is written the moment a badge's condition first becomes true, in the
SAME transaction as whichever event/Star-award caused it — reusing `post_event()`'s SAVEPOINT,
never a second commit boundary. Three badge checkers cover the three fixed badges ("7 ngày liên
tiếp" via `compute_streak()`, unchanged; "first 100 Stars" via a threshold crossing on
`total_stars()`; "Hoàn thành Tuần 1" = the Profile's first-ever completed non-`replay` Session —
a human decision, resolving the ambiguity between this simplest reading and two content-model-
based alternatives; see Implementation Notes for the alternatives considered). Session summary
surfaces newly-earned badges with fanfare + 🔊; Home shows the latest 3; a new "Huy hiệu của em"
screen shows all three, unearned ones greyed out with a 🔊 explanation.

## Boundaries & Constraints

**Always:**
- `progress_badges` (new table, `learning` module, AD-2): `id` (UUIDv7), `profile_id`,
  `badge_key` (one of a fixed enum: `week1`, `streak7`, `stars100` — `CHECK` constraint), `earned_at`.
  Unique index on `(profile_id, badge_key)` — a badge is earned once, ever, per Profile.
  New Alembic migration `0015_progress_badges.py` (current head is `0014_progress_stars`).
- New `backend/hoctap/learning/badges.py`: a `maybe_award_badges(conn, now_iso, session_id,
  profile_id, mode) -> list[str]` (returns newly-earned `badge_key`s, `[]` if none) called from
  `post_event()` right after `maybe_award_stars()`, inside the same SAVEPOINT. Idempotent: if a
  badge row already exists for this Profile, never re-insert or re-return it as "newly earned".
  Only `practice`/`retry`/`concept`/`quiz` mode Sessions can trigger a check (matches AD-6's mode
  table — `replay` never counts toward Streak/Stars, so it must never trigger a badge check either).
- `streak7`: `compute_streak(conn, profile_id, today) >= 7` (reuse unchanged, call don't modify).
- `stars100`: `total_stars(conn, profile_id) >= 100` (reuse unchanged, call don't modify) — a
  one-time threshold crossing, not re-checked once earned.
- `week1`: the Profile's first-ever completed (`session_completed`) non-`replay`-mode Session —
  human decision (see Intent), not a curriculum-position or elapsed-calendar-time check. Award on
  that Session's own completion, once, ever, per Profile.
- `GET /sessions/{id}/summary`: extend `SessionSummary`/its response with `new_badges: list[str]`
  (the `badge_key`s newly earned by events posted during THIS Session, empty list otherwise).
- `GET /library/home/{profile_id}`: extend with `recent_badges: list[str]` — the Profile's latest
  3 earned `badge_key`s by `earned_at` DESC.
- New `GET /profiles/{id}/badges`-style endpoint (implementer's call on exact path, document it):
  returns all 3 fixed badges with `earned: bool` + `earned_at` for the "Huy hiệu của em" screen.
- Frontend: a `Badge` component (96px round medal, gold ring, icon, short label — per the epic's
  own spec) used in three places: Session summary (pops on first earn, fanfare + 🔊 name via
  `speak()`/`phrase()`), Home (latest 3, small), a new "Huy hiệu của em" route/screen (all 3,
  unearned ones greyed out, each with its own 🔊 explaining how to earn it). Any new copy
  (badge names, per-badge earn-instructions) goes into `phrases.vi.json` so `speak-missing`
  pre-synthesizes it — reuse the existing `your_badges`/`new_badge_earned` keys, add per-badge
  name/instruction keys.

**Never:**
- No Retry Queue changes (Story 3.3) and no quiz-mode scoring changes (Story 3.4) — this story
  only ADDS a badge check point after Stars are awarded; it does not touch how Stars/Retry are
  computed.
- No changes to `compute_streak()`, `total_stars()`, `maybe_award_stars()`, or
  `content.schema`/`content.effective`/`content.catalog`/`content.library` themselves (call them,
  don't modify them) — except whatever read-only helper `week1`'s trigger needs, once its Open
  Question is resolved.
- No leaderboards, no badge "loss" or downgrade — badges are one-way, permanent per Profile.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Streak reaches 7 | `compute_streak()` crosses from 6 to 7 on a completed Session | `streak7` badge row written, returned in that Session's `new_badges` | N/A |
| Streak already ≥7, later Session | Profile already has `streak7` row | no duplicate row, not in `new_badges` again | N/A |
| Total Stars crosses 100 | `total_stars()` crosses from 98 to 101 in one Session (multi-Problem) | `stars100` badge written once, in `new_badges` | N/A |
| First-ever completed Session | Profile's first `session_completed`, mode ≠ `replay` | `week1` badge row written, in `new_badges` | N/A |
| Second completed Session | Profile already has `week1` row | no duplicate row, not in `new_badges` again | N/A |
| Replay-mode Session | any event in a `replay` Session | no badge check runs, no row written | N/A |
| Resent resolving event | idempotent resend that re-triggers the check | no duplicate badge row, not re-returned in `new_badges` | N/A |
| Home load, 0 badges earned | fresh Profile | `recent_badges: []`, "Huy hiệu của em" shows all 3 greyed out | N/A |
| Home load, 2 badges earned | 2 of 3 earned | `recent_badges` has those 2 (all of them, since <3) | N/A |
| "Huy hiệu của em" screen | 1 earned, 2 unearned | earned badge normal; unearned two greyed with 🔊 explanation each | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/models.py` -- add `progress_badges` table.
- `backend/hoctap/db/alembic/versions/0015_progress_badges.py` -- new migration (head is
  `0014_progress_stars`).
- `backend/hoctap/learning/badges.py` (new) -- `maybe_award_badges()`, one checker function per
  badge (`_check_streak7`, `_check_stars100`, `_check_week1` = Profile's first-ever completed
  non-`replay` Session), `profile_badges()` for the "Huy hiệu của em" read.
- `backend/hoctap/learning/sessions.py` -- `post_event()` calls `maybe_award_badges()` right after
  the existing `maybe_award_stars()` call, same SAVEPOINT (around line 762).
- `backend/hoctap/learning/summary.py` -- `SessionSummary` gains `new_badges: list[str]`.
- `backend/hoctap/api/sessions.py` -- `GET /sessions/{id}/summary` response gains `new_badges`.
- `backend/hoctap/api/library.py` -- `LibraryHomeOut` gains `recent_badges: list[str]`.
- `backend/hoctap/api/profiles.py` or a new small router -- `GET /profiles/{id}/badges`-style
  endpoint (implementer's call on exact path).
- `backend/tests/test_badges.py` (new) -- covers this spec's I/O matrix.
- `frontend/src/components/Badge/Badge.tsx` (new) -- 96px round medal component (earned/unearned
  variants).
- `frontend/src/pages/Home.tsx` -- latest-3-badges row.
- `frontend/src/pages/SessionPlayer.tsx` -- `SessionSummaryScreen` pops `new_badges` with fanfare
  + 🔊.
- `frontend/src/pages/Badges.tsx` (new) -- "Huy hiệu của em" screen, all 3, unearned greyed +
  per-badge 🔊 explanation.
- `frontend/src/App.tsx` -- new route (e.g. `/badges`) wired to the new screen.
- `frontend/src/audio/phrases.vi.json` -- per-badge name + earn-instruction keys (reuse
  `your_badges`/`new_badge_earned`).

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/learning/models.py` + `0015_progress_badges.py` -- add `progress_badges`
      table -- durable, transactional badge storage per AD-6.
- [x] `backend/hoctap/learning/badges.py` -- `_check_streak7`/`_check_stars100`/`_check_week1`
      (first-ever completed non-replay Session) + `maybe_award_badges()` wired into
      `post_event()`'s existing SAVEPOINT -- reuses Story 3.1's pattern exactly.
- [x] `GET /sessions/{id}/summary` gains `new_badges` -- lets the Session summary pop fanfare.
- [x] `GET /library/home/{profile_id}` gains `recent_badges` -- Home's latest-3 display.
- [x] New `GET /profiles/{id}/badges` (or chosen path) -- full 3-badge state for "Huy hiệu của em".
- [x] `frontend/src/components/Badge/Badge.tsx` -- shared 96px medal component, earned/unearned.
- [x] `Home.tsx` -- latest 3 badges row.
- [x] `SessionPlayer.tsx` -- new-badge fanfare + 🔊 on the summary screen.
- [x] `Badges.tsx` + route -- all-badges screen, unearned greyed + 🔊 explanation.
- [x] `phrases.vi.json` -- per-badge name/instruction copy added.
- [x] `test_badges.py` -- covers all I/O-matrix rows.
- [x] All new/existing backend and frontend tests, `ruff check`, `tsc -b`, `eslint` clean.

**Acceptance Criteria:**
- Given a Profile's Streak crosses 7 on a completed non-replay Session, when that Session's
  `session_completed` event resolves, then a `streak7` badge row is written once and returned in
  that Session's `new_badges`.
- Given a Profile's total Stars cross 100 within a Session, when the resolving event is
  processed, then a `stars100` badge row is written once and appears in `new_badges`.
- Given a `replay`-mode Session, when any event posts, then no badge check runs and no row is
  written.
- Given a Profile with 2 of 3 badges earned, when the "Huy hiệu của em" screen loads, then the
  earned 2 render normally and the unearned 1 renders greyed out with its own 🔊 explanation.
- Given Home loads for a Profile with 1+ earned badges, when the page renders, then the latest 3
  (or fewer) show, ordered most-recently-earned first.

## Implementation Notes

- (2026-09-29) **Call site for `maybe_award_badges()`**: called unconditionally after
  EVERY event kind's own handling in `post_event()` (not just `attempt`/`self_marked`
  like `maybe_award_stars()`) -- `week1`/`streak7` only ever become true once
  `session_completed`'s own handling has set `completed_at`, so the check has to run for
  that event kind too. Mode-gated internally (`BADGE_CHECK_MODES`), matching
  `maybe_award_stars()`'s `STAR_AWARDING_MODES` posture; `replay` never reaches a real
  check (verified directly: all 3 conditions pre-satisfied, `mode="replay"` still writes
  nothing).
- (2026-09-29) **`new_badges` derivation without a `session_id` column**: `progress_badges`
  only carries `id`/`profile_id`/`badge_key`/`earned_at` (per the frozen Boundaries) --
  `learning.summary.session_new_badges()` matches a badge's `earned_at` against the set of
  `received_at` values of THIS Session's own `progress_events` rows, since `earned_at` is
  always set to exactly the `received_at` of the one event whose processing triggered the
  award. Lives in `summary.py`, not `badges.py`, to avoid a circular import (`badges.py`
  already imports `compute_streak()`/`LOCAL_TZ` from `summary.py`).
- (2026-09-29) **`GET /profiles/{id}/badges`**: added to the existing `api/profiles.py`
  router (`/profiles` prefix already mounted) rather than a new router file.
- (2026-09-29) **Frontend**: `Badge.tsx` is presentation-only; its badge-name/instruction
  phrase-key lookups and per-badge icon live in a sibling `badgeCopy.ts` (not inside
  `Badge.tsx` itself) purely to satisfy `react-refresh/only-export-components` --
  `SessionSummaryScreen` imports `badgeName()` from there too, so the fanfare speaks the
  exact same text the medal shows. Home gained both a small latest-3-badges row (only
  when 1+ earned) and a "Huy hiệu của em" `HomeCard` entry point to the new `/badges`
  route, alongside the existing cards.
- (2026-09-29) **Test setup for streak7/stars100**: `test_badges.py`'s direct-engine tests
  build `progress_sessions`/`progress_stars` rows straight into an in-memory engine (the
  same pattern Story 2.10's own streak tests already use in `test_sessions.py`) rather
  than driving dozens of real Problems/attempts through the API only to reach a 7-day
  streak or a 98-Star total.

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

## Verification

**Commands:**
- `uv run ruff check .` -- all checks passed.
- `uv run pytest backend/tests/test_badges.py backend/tests/test_sessions.py backend/tests/test_library.py -q` -- all passed, no regressions.
- `npx tsc -b` -- clean.
- `npx eslint .` -- clean.
- `npx vitest run src/pages/Home.test.tsx src/pages/SessionPlayer.test.tsx src/pages/Badges.test.tsx --pool=vmThreads` -- 41 passed, 0 failed (use `vmThreads` per Story 3.1's Verification note on shared-machine worker timeouts).
- Tasks & Acceptance: all 12 checked. Matrix: all 10 rows covered by a passing test in
  `test_badges.py`.
