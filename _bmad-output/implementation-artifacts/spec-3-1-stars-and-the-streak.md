---
title: 'Story 3.1: Stars and the Streak'
type: 'feature'
created: '2026-09-29'
status: 'blocked-on-2.11'
baseline_commit: 'tree:7af74abf5a32d1fcc4853be904c96db36e8c797f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing awards or stores a Star today. Story 2.8's "self_marked correct = a derived
Star" language and Story 2.10's `deferred-work.md` entries were explicit placeholders — "no
Star-reading endpoint or UI exists yet, by design." Story 2.10's Streak (`compute_streak()`) and
first-try-accuracy (`session_wrong_problem_ids()`) are already built and reactive/derived, but
Stars need something stronger: AD-6's literal rule is "materialised in the same transaction as the
event," which neither of those two functions does — they're computed on demand, not stored.

**Approach:** A new `progress_stars` table (one row per Problem-per-Session, written inside the
SAME transaction as the grading/self-mark event that resolves it — reusing the exact SAVEPOINT
structure `_grade_and_stage()`/`post_event()` already use) stores 3/2/1/0... **no — the AC is
literally 3/1/0** Stars per Problem: **3** if every Part of the Problem was first-try-correct within
this Session, **1** if a Hint (or a second try) was needed on any Part but no Part's Solution was
shown, OR the Problem is a `fallback` correctly self-marked "đúng", **0** if any Part's Solution was
shown (or a `fallback` marked "chưa đúng" — implementer's call whether "chưa đúng" is 0 or simply
never earns a row at all; document whichever is chosen). This is a genuinely NEW per-Problem
aggregation across Parts — Story 2.5's staged-help logic (`_count_prior_wrong()`) is per-Part, not
per-Problem, so this story adds the missing rollup. **Streak reuses `compute_streak()` unchanged**
(Story 2.10 already built exactly what this story's AC asks for) — this story's job for Streak is
purely surfacing it (Home display), not recomputing it. Total Stars is a new simple `SUM` over
`progress_stars` for the Profile.

**This story formally supersedes** Story 2.8's "Stars are derived reactively, no storage" language
and Story 2.10's "no Star-reading endpoint or UI exists yet" deferral — both `deferred-work.md`
entries should be marked resolved/superseded (not deleted — this codebase's convention is
append-only logs; add a closing note referencing this story). It does **not** touch or contradict
Story 2.10's first-try-accuracy metric (`session_wrong_problem_ids()`), which is a different,
narrower metric (only `attempt` events, used for the Session summary's "n/n correct" and "Luyện
lại bài sai") — Stars and first-try-accuracy are two separate, independently-computed things that
happen to share some of the same underlying `attempt`/`self_marked` events.

## Boundaries & Constraints

**Always:**
- **`progress_stars`** (new table, owned by `learning` per AD-2): `id` (UUIDv7), `session_id`,
  `profile_id`, `problem_id`, `stars` (0/1/3 — a `CHECK` constraint against exactly these 3 values,
  not an arbitrary int), `awarded_at`. One row per (session_id, problem_id) — written ONCE, when
  the Problem's outcome for that Session first becomes determinable (every Part has at least one
  attempt AND none is still "wrong-pending-a-later-attempt" — i.e., the same moment
  `_maybe_resolve_retry_item()`-style logic would consider the Problem "done" for this Session, OR
  a fallback Problem's `self_marked` event resolves it). New Alembic migration (next after whatever
  Story 2.11 lands with — check the actual head).
- **Per-Problem Star computation** (new function, e.g. `learning/scoring.py`'s
  `compute_problem_stars(conn, session_id, problem_id) -> int | None` — `None` if not yet
  determinable this Session): for a non-fallback Problem, inspect every Part's FIRST attempt within
  this Session (reuse the exact `session_id`-scoped, rowid-ordered pattern
  `session_wrong_problem_ids()` already established) — 3 if every Part's first attempt was correct;
  otherwise inspect whether any Part ever needed its Solution shown within this Session (0) vs. only
  ever needed a Hint/retry (1). For a `fallback` Problem, its single `self_marked` outcome maps
  directly: "đúng" → 1, "chưa đúng" → 0 or no row (implementer's call, document it).
- **Written inside the SAME transaction** as whichever event resolves the Problem — reuse
  `post_event()`'s existing SAVEPOINT (`conn.begin_nested()`), do not add a second commit boundary.
  Only `practice`, `retry`, and `concept` mode Sessions award Stars (per this story's own AC
  wording, matching AD-6's scoring-by-mode table from Story 2.10's research — `quiz` also scores
  per AD-6 but quiz Stars are Story 3.4's job, not this one; `replay` never awards Stars, matching
  the existing mode-gate pattern from Story 2.10).
- **Idempotency**: if a Problem's `progress_stars` row already exists for this Session (e.g. a
  resent event reaching the resolution point twice), do not insert a duplicate or overwrite a
  different value — same "already stored, no-op" posture as every other Story 2.5+ mutation.
- **`GET /sessions/{id}/summary`** (Story 2.10, extend it): add `stars_earned` (sum of this
  Session's `progress_stars` rows) alongside the existing `first_try_correct`/Streak fields.
- **A new Home-facing endpoint or extension** (implementer's call: extend `GET
  /library/home/{profile_id}` again, or a small new `GET /profiles/{id}/progress`-style endpoint)
  returning total Stars (all-time `SUM` for the Profile) and the current Streak (`compute_streak()`,
  unchanged, called from here).
- **Frontend**: Home shows a persistent Star total and Streak flame (a plain number is enough per
  Story 2.10's own deferred-work.md note — no calendar UI, no flame animation asset required, just
  a number with the 🔥/⭐ glyph and a phrase). The Session summary screen shows `stars_earned`
  (reusing `StarBurst`, already built and already used twice in `ProblemPlayer.tsx`'s correct-
  feedback path — wire a burst-to-Home-counter animation if cheap, but a static "Stars earned: n"
  on the summary screen satisfies the AC's literal wording even without the fly-animation if time-
  constrained; document whichever is delivered).

**Never:**
- No badges — Story 3.2.
- No Retry Queue exit-condition changes — Story 3.3 (the "2 separate Sessions" rule is a LATER
  story's job; this story's Retry Queue interaction is unchanged from Story 2.5/2.10).
- No quiz-mode scoring — Story 3.4.
- No changes to `content.schema`/`content.effective`/`content.catalog`/`content.library`/
  `content.speech`, and no changes to Story 2.10's `session_wrong_problem_ids()`/`compute_streak()`
  logic itself (call them, don't modify them).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Problem, all Parts first-try correct | 2-Part Problem, both correct first try | 3 Stars | N/A |
| Problem, a Hint needed on one Part, no Solution shown | 1 wrong then correct on one Part | 1 Star | N/A |
| Problem, a Solution shown on any Part | 2 wrong attempts on one Part | 0 Stars | N/A |
| Fallback, self-marked đúng | self_marked(true) | 1 Star | N/A |
| Fallback, self-marked chưa đúng | self_marked(false) | 0 Stars (or no row — document choice) | N/A |
| Replay-mode Session | any attempt in a replay Session | 0 Stars awarded, no progress_stars row | N/A |
| Resent resolving event | idempotent resend | no duplicate/changed progress_stars row | N/A |
| Total Stars, Home load | multiple Sessions with Stars | correct SUM across all non-replay Sessions | N/A |
| Streak display, Home load | consecutive completed days | matches compute_streak()'s existing value | N/A |
| Session summary | a completed Session with mixed outcomes | stars_earned matches the sum of that Session's own progress_stars rows | N/A |

## Code Map

- `backend/hoctap/learning/models.py`: `progress_stars` table.
- `backend/hoctap/db/alembic/versions/00XX_progress_stars.py`: new migration (check actual head).
- `backend/hoctap/learning/scoring.py` (new, per ARCHITECTURE-SPINE's own directory note) or a
  function added to `learning/sessions.py`/`summary.py` (implementer's call on file placement,
  document it): `compute_problem_stars()`, the write-on-resolution hook wired into
  `post_event()`'s existing `attempt`/`self_marked` handling.
- `backend/hoctap/api/sessions.py`: `GET /sessions/{id}/summary` gains `stars_earned`.
- `backend/hoctap/api/library.py` or a new small endpoint: total Stars + Streak for Home.
- `backend/tests/test_sessions.py`, a new `test_scoring.py` if scoring gets its own module.
- `frontend/src/pages/Home.tsx`: Star total + Streak display.
- `frontend/src/pages/SessionPlayer.tsx`: `stars_earned` shown on the summary screen.
- `_bmad-output/implementation-artifacts/deferred-work.md`: closing notes on the two superseded
  entries (Story 2.8's "Stars derived reactively" and Story 2.10's "no Star endpoint yet").

## Tasks & Acceptance

- [ ] `progress_stars` table + migration.
- [ ] Per-Problem 3/1/0 Star computation (Parts-aggregated for graded Problems, self_marked-mapped
      for fallback), written inside the same transaction as the resolving event.
- [ ] Mode-gated: only `practice`/`retry`/`concept` award Stars; `replay` never does.
- [ ] Idempotent: a resolving event's resend never duplicates/changes a Star row.
- [ ] `GET /sessions/{id}/summary` gains `stars_earned`.
- [ ] A Home-facing total-Stars + Streak endpoint/extension.
- [ ] Frontend: Home shows total Stars + Streak (plain number, no new animation assets required);
      Session summary shows Stars earned this Session.
- [ ] `deferred-work.md` closing notes on the two superseded entries.
- [ ] All new tests pass; `ruff check`/backend suite/`tsc -b`/`eslint`/frontend suite all clean.

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

## Verification

<!-- Populated after independent re-verification. Append-only. -->

</frozen-after-approval>
