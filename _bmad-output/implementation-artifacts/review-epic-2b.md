# Code review: Epic 2, second half (Stories 2.7-2.11), 2026-09-30

Range `ed8fca3..600ba9b`, backend and frontend **source only** (tests, lockfiles, generated files left out of the diff; the Verification Gap layer read tests from the repo). Four independent layers reviewed against the five story specs. Claims that mattered were checked against the code; reviewer severities were disregarded.

## Decision needed

- [ ] [Review][Decision] **A fallback Problem the child self-marked "đúng" still counts as wrong in the Session summary and replay set** [medium] `summary.py:session_wrong_problem_ids` reads only `attempt` events, and Story 2.10's frozen text says self-marks must not count. Result: a Session containing any fallback Problem can never show n/n first-try, "Luyện lại bài sai" always offers those Problems and the replay never reaches zero, while Stories 3.1/3.3 already award a Star and Retry credit for the same self-mark. Found by all four layers. Options: count a fallback Problem's `self_marked` verdict as its first-try result / keep as specified.
- [ ] [Review][Decision] **The Streak day comes from server time, not the device time of the last event** [medium] `compute_streak` reads `progress_sessions.completed_at`, which `post_event` sets from the server's `received_at`. With the offline outbox (Story 2.11) a Session finished at 23:50 offline and synced the next day counts toward the wrong calendar day. The epic says `occurred_at` decides the day. You chose device time for the Retry Queue in the Epic 3 review. Options: use the `session_completed` event's device time for the Streak / keep server time.

## Patch

- [ ] [Review][Patch] **`tzdata` is not a dependency** [high] `learning/summary.py:27` builds `ZoneInfo("Asia/Ho_Chi_Minh")` at import. Nothing in `pyproject.toml` or `uv.lock` provides the time-zone database, and Windows (a supported runtime, Story 1.11) has none of its own, so the API would fail to start there. Add `tzdata` to the dependencies.
- [ ] [Review][Patch] **"Tiếp tục" resumes a practice Session from Problem 1** [medium] `SessionPlayer.tsx` starts at chunk 1, Problem 0; only quiz Sessions jump to the first unanswered Problem, and the bundle's `attempted` flag is profile-wide for non-quiz modes. Story 2.11 requires resuming at the current Problem. Make the resume point Session-scoped for every mode and skip Problems already completed in this Session.
- [ ] [Review][Patch] **A new event can overtake older queued ones, and flushes can run concurrently** [medium] `outbox.ts:postEventsOrQueue` posts directly even when the queue is non-empty, and `flushOutbox` has no single-flight guard (mount, `online`, manual retry, StrictMode). First-try grading depends on insertion order, and the spec says strictly FIFO, one at a time. Flush first when the queue is non-empty, queue behind it if that fails, and serialise flushes.
- [ ] [Review][Patch] **A failed `session_completed` post leaves the summary on "Đang tải…" forever** [medium] `SessionPlayer.tsx:~L138` shows a non-offline error only for quiz Sessions. Show the error with a retry for every mode. Also show an error when "Luyện lại bài sai" fails to start (currently silent).
- [ ] [Review][Patch] **`match` image items render their raw key** [medium] `MatchWidget.tsx` shows `item.text ?? item.item_key` and never uses `imageUrl`, so an image-based match item is unusable. Render the image.
- [ ] [Review][Patch] **Audio player** [low-medium] `audio/player.ts` marks a clip missing on a network error (code 2), permanently greying its 🔊 until reload; a rejected `play()` leaves the state stuck at "playing"; and leaving a Problem while `speak()` is still hashing the key lets the old clip start after the cleanup. Mark missing only on a not-supported/404 error, reset state when `play()` rejects, and cancel a pending `speak()` on unmount.
- [ ] [Review][Patch] **Auto-play speaks the Problem instruction once, not each Part's prompt** [low-medium] Story 2.9 says each new Part's instruction/prompt plays once when it renders; the effect in `ProblemPlayer` has empty dependencies. Play the Part prompt when the Part changes.
- [ ] [Review][Patch] **`connect_dots` dots are 32 px** [low-medium] `widgets.css` sets 32 px, against Story 2.7's ≥64 px touch-target rule. Keep the drawn size but give the dot a 64 px hit area. Same check for `dot_draw`'s removable dots.
- [ ] [Review][Patch] **Widget polish** [low] `DotDrawWidget` calls the parent's `onSetValue` inside a `setDotsByBox` updater (double-invoked under StrictMode); `MatchWidget` recomputes its lines only when pairs change, so a tablet rotation leaves them misplaced (add a `ResizeObserver`); the `connect_dots` wiggle timer is not cleared on unmount.
- [ ] [Review][Patch] **Test gaps** [medium] (a) `GET /sessions/{id}/summary` 403 for a foreign Profile and 404 for an unknown Session are untested; (b) no `SessionPlayer` test that a Profile with `auto_play:false` suppresses auto-play.

## Deferred

- [x] [Review][Defer] **`spot_difference` cannot be passed** [medium, known] Any tap counts as a difference, and the submitted region keys are client-side buckets that never match the server's `region_key`s, so a real Part always grades wrong. Disclosed in Story 2.7's Spec Change Log as a content-schema gap. — deferred: needs region coordinates in the content schema and grader.
- [x] [Review][Defer] **An abandoned unfinished Session stays on "Tiếp tục" forever** [low-medium] `find_unfinished_session` has no staleness cutoff and no tie-break on equal `started_at`. — deferred: needs a product rule for when a Session counts as abandoned.
- [x] [Review][Defer] **A permanently failing queued event jams the queue and traps the child on the offline screen** [medium, known] Already logged from Story 2.11 (`deferred-work.md`); the offline screen also waits for a manual "Thử lại" after the background flush drains. — deferred: needs a stuck-queue recovery UI.
- [x] [Review][Defer] **No test that `App` mounts `useOutboxAutoFlush`** [low] One line of wiring; a minimal `App` render test would cover it. — deferred: low value.

## Rejected

- `mode` independent of `ref.kind` (4 layers): fixed in the Epic 3 review (server derives mode, mismatch rejected).
- Story 2.8's correct self-mark calls the Retry Queue resolver against its own "Never" rule: superseded by Story 3.3, whose exit rule is built on self-marks.
- `find_unfinished_session` added to `learning/sessions.py` against 2.11's "Never": placement only; nothing else fits.
- Outbox `DB_VERSION` not bumped after the `seq` schema change: the change landed inside Story 2.11 before its commit; no v1 store exists in the wild.
- Replay set does not filter hidden Problems; `find_unfinished_session` ordering ties: hidden Problems in frozen Sessions are served by design (AD-9, decided in the Epic 4 review).
- Repeated self-marks inflate Stars; a mixed fallback and graded Problem can be self-marked; an empty last chunk posts `session_completed`: Stars are one row per Session and Problem since 3.1; the other two need content that does not exist.
- `session_completed` is accepted before any Problem is attempted; `fallback_revealed` returns any fallback Problem's Solution: needs a hand-made client; the child cannot gain much.
- Multi-Part Problem with an unattempted Part counts as first-try correct: a Session cannot complete without visiting every Part.
- Client `AbortError` wrapped as `NetworkError`; `store.add` failing inside the offline handler; rejected `dbPromise` cached; auto-flush unhandled rejection; offline screen not dismissed by the background flush: low.
- Widget accessibility and edge cases (keyboard on `DotDraw`, `ZoomableImage` NaN and off-centre reset, `OrderWidget` foreign drops, non-contiguous dot numbers, zero-dot `dot_draw`): tablet-first UI; content edge cases that do not exist.
- Missing-clip grey-out only on the instruction 🔊; queued attempt loses Part state after a flush; `match` line tap target: disclosed limitations in the story notes.
- Per-layer nits: bilingual error copy, `auto_play` migration downgrade, chunk-boundary message removed, `ProgressDots` unused: cosmetic.
- "Commit message claims Workbox and fake-indexeddb but the diff lacks them": those files are outside this diff range by construction.

## Decisions resolved (2026-09-30, by Anh) -> now patches

1. Fallback result: count a fallback Problem's `self_marked` verdict as its first-try result in the Session summary and the replay set (reverses Story 2.10's frozen "self-marks must not count").
2. Streak day: use the device time (`occurred_at`) of the `session_completed` event instead of the server time.

Patch handling chosen: apply every patch (together with the Epic 2 first-half patches).
