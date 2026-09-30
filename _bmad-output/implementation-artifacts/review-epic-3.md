# Code review: Epic 3 (Stories 3.1-3.4), 2026-09-30

Range `600ba9b..d551415`, backend and frontend source and tests (generated OpenAPI files excluded). Four independent layers (Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor) reviewed against the four story specs. Every finding below was checked against the code; reviewer severities were disregarded.

## Decision needed

- [ ] [Review][Decision] **Session `mode` is a client-chosen field** [medium] `api/sessions.py:start_session` forces only `retry` and `quiz`. A replay ref sent with `mode:"practice"` earns Stars, Streak and Retry exit credit; a lesson ref sent with `mode:"retry"` is treated as a retry Session. The independence of `mode` from `ref.kind` was a Story 2.10 frozen decision, so fixing it changes that decision. Options: derive mode from `ref.kind` and reject a mismatch / leave as is.
- [ ] [Review][Decision] **Retry exit counts clean Sessions from before the latest wrong attempt** [medium] `retry.py:maybe_resolve_retry_item` counts since `added_at`, and a repeat wrong attempt only refreshes `last_wrong_at`. Wrong, clean, wrong again, clean resolves the item. This matches the 3.3 spec text exactly, which is why it needs your call. Options: count since `last_wrong_at` (a miss resets progress) / keep as specced.
- [ ] [Review][Decision] **A quiz retake can add to the Retry Queue but never clear it** [medium] Retakes write no `progress_stars` row (3.4 decision) and the exit rule counts only 3-star rows (3.3), so right answers in a retake never count toward exit while wrong ones still queue. Options: let a correct retake count toward exit without awarding Stars / keep as is and document it.
- [ ] [Review][Decision] **Retry and quiz "day" comes from server `received_at`, not the device `occurred_at`** [medium] Epic 3 says `occurred_at` decides the calendar day for Retry. `add_retry_item` is called with `received_at`, so events that sit in the offline outbox past midnight shift due dates. Streak already uses server `completed_at`, so this is a pattern across the epic. Options: switch Retry to `occurred_at` / keep server time.
- [ ] [Review][Decision] **Wrong quiz attempts feed the Profile-wide prior-wrong count** [medium] In a later practice Session, the first wrong attempt on a Part the child got wrong in a quiz releases the Solution immediately (0 Stars). This is stated in the 3.4 notes but conflicts with the epic's never-punitive tone. Options: exclude quiz attempts from the count / keep.

## Patch

- [ ] [Review][Patch] **Multi-Part quiz Problem counts as answered after one Part** [medium] `sessions.py:get_bundle` (~L249-281) sets `attempted` from any attempt event; on resume the Problem is skipped and its other Parts grade wrong. Require every graded Part to have an attempt.
- [ ] [Review][Patch] **Due Retry items ignore Problem visibility** [medium] `retry.py:due_problem_ids` and `library.py:retry_due_count` do not filter hidden or parent-reported Problems, so the "Luyện lại" card can offer a Problem the parent hid. Filter through `visible_to_child`.
- [ ] [Review][Patch] **Test gaps** [medium] No test plays a `retry`-mode Session (Stars, badges, exit are unprotected); the server-forces-`mode="retry"` rule is untested; the quiz fallback player and the retake "no Stars" line have no frontend test.
- [ ] [Review][Patch] **Error hidden after a successful quiz submit** [low] `SessionPlayer.tsx:215` shows `submitError` only while `!quizSubmitted`, so a failed `session_completed` shows nothing.
- [ ] [Review][Patch] **`recent_badges` has no tie-break** [low] `badges.py:125` orders by `earned_at` only; badges earned together are unordered. Add `id desc`.
- [ ] [Review][Patch] **Stale docstrings** [low] `total_stars` says quiz Sessions never write Star rows (they do); `_fallback_stars` says the latest self-mark wins (the first Star row wins).
- [ ] [Review][Patch] **Badge speech ignores `auto_play` and has no `.catch`** [low] `SessionSummaryScreen` always speaks the badge chain on mount.
- [ ] [Review][Patch] **`resolve(..., now=None)` falls back to the wall clock** [low] `problem_sets.py:~L160` bypasses the injected clock; make `now` required for `retry`.
- [ ] [Review][Patch] **Quiz "saved" timer not cleared on unmount** [low] `ProblemPlayer.tsx` (700 ms `onAdvance`) can fire on stale state.

## Deferred

- [x] [Review][Defer] **Quiz resume only computed for the first chunk** [medium, unverified] `SessionPlayer.tsx` sets `resumed` once on the first bundle. Settle by loading a multi-chunk quiz and reloading into chunk 2. — deferred: needs a quiz sheet with more than 10 Problems to confirm.
- [x] [Review][Defer] **A quiz sheet can be started silently via "Học tiếp"** [low-medium, unverified] The child gets a no-feedback quiz with no signal beforehand. — deferred: product question, needs a look at Home's flow.

## Rejected

- Fallback Problems in a quiz are unanswerable yet graded wrong, and never queue: matches the approved 3.4 spec row ("↻ with a Solution, 0 Stars, not queued"). Revisit if quiz sheets contain fallback Problems.
- `week1` badge name versus its rule: 3.2's Intent records your decision to award it on the first completed Session.
- Home Stars/Streak line has no audio: 3.1 says a plain number is enough.
- Badge fanfare is speech only, no sound effect: low, cosmetic.
- Self-mark count counts a Session whose last verdict flipped to wrong: low, needs a same-Session flip.
- `session_new_badges` matches by timestamp: needs identical millisecond timestamps across Sessions; fix needs a migration.
- Badge checks run on every event: low performance cost, fix adds gating logic.
- Late attempts after `quiz_submitted`, concurrent `quiz_submitted`, a vanished Problem dropped from quiz results: low and unlikely; fixes add guards or an index.
- Retry error shown in the wrong place on Home: low.
- Formatting noise in the diff: not a defect.
- `deferred-work.md` closing notes for 3.1 missing: false, they landed in `559f612`.
- 3.3 quiz-fed retry untested in 3.3: false, quiz did not exist yet; it is covered in `test_quiz.py`.

## Carried to the Epic 4 and Epic 2 reviews

- `get_bundle` skips only Problems that vanished entirely, not hidden or parent-reported ones (`sessions.py:~L266`), so a Session already in progress can still serve a Problem a parent reported. Story 4.4's spec assumed the bundle skips it. Check in the Epic 4 chunk.

## Decisions resolved (2026-09-30, by Anh) -> now patches

1. Mode: derive from `ref.kind` server-side and reject a mismatched `mode` (reverses Story 2.10's independent-mode choice).
2. Retry exit: count qualifying Sessions/self-marks only since the latest wrong attempt (`max(added_at, last_wrong_at)`).
3. Quiz retake: a correct retake counts toward Retry exit without awarding Stars or writing a `progress_stars` row.
4. Retry day: use the device `occurred_at` (not server `received_at`) for `last_wrong_at` and due-ness.
5. Staged help: wrong attempts made in `quiz` Sessions no longer count toward the Profile-wide prior-wrong tally.

Patch handling chosen: apply every patch.
