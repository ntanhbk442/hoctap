# Epic 3 Context: Bin keeps coming back

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic gives Bin (and any child) reasons to return daily: rewards for practice (Stars and a Streak flame), recognition for milestones (badges), a mechanism that resurfaces missed problems until they're mastered (the Retry Queue), and a lower-pressure quiz format for the weekly practice sheet. All of it must feel encouraging, never punitive — no lives to lose, no leaderboards, no shaming language for wrong answers or missed days.

## Stories

- Story 3.1: Stars and the Streak
- Story 3.2: Badges
- Story 3.3: Retry Queue
- Story 3.4: Quiz mode for "Phiếu tự luyện cuối tuần"

## Requirements & Constraints

- **Stars per Problem:** 3 if every Part was right on the first try; 1 if any Part needed a Hint, a second try, or was a `fallback` self-marked "đúng"; 0 if the Solution was shown for any Part.
- **Streak:** count of consecutive calendar days (Asia/Ho_Chi_Minh, derived from each event's `occurred_at`) with at least one completed Session. `replay` Sessions never count toward Stars or Streak.
- **Scoring is keyed by Session mode**, fixed at Session start:
  - `practice`, `retry`, `concept`: normal Stars, count toward leaving the Retry Queue, count toward Streak.
  - `quiz`: no Hints during play; graded only at submission (see quiz rules below); still counts toward Retry Queue and Streak.
  - `replay` ("Luyện lại bài sai"): earns no Stars, does not count toward leaving the Retry Queue, does not count toward Streak — it's extra practice only.
- **Badges/milestones:** "Hoàn thành Tuần 1" (finished week 1), "7 ngày liên tiếp" (7-day streak), and first 100 Stars. Earning a badge pops a fanfare + spoken (🔊) announcement on the Session summary. Home shows the latest 3 badges; "Huy hiệu của em" shows all badges, with unearned ones greyed out and 🔊 explaining how to earn them.
- **Retry Queue entry:** a Problem enters when any Part gets a wrong Attempt (including during a quiz) or a `fallback` Problem is self-marked "chưa đúng". It becomes due starting the next calendar day after the last wrong Attempt.
- **Retry Queue exit:** a Problem leaves after every Part is answered correctly on the first try across 2 separate Sessions of any kind (not necessarily consecutive), excluding `replay` Sessions. A `fallback` Problem leaves after being self-marked "Em làm đúng" twice.
- **Quiz mode (weekly sheet):** during play there's no 💡 button, no Hints, and no right/wrong feedback — only "Đã lưu" (saved) confirmation and progress dots that only fill in (never show correct/wrong per problem). Grading happens entirely at submission (`quiz_submitted`): every Problem is shown as ✔ or ↻, wrong ones show their Solution and go to the Retry Queue, Problems with every Part right earn 3 Stars, everything else earns 0.
- **Counter-metric constraint:** don't optimize for raw Stars/Problems-per-day volume — this is a known failure mode (racing through easy content). First-try accuracy on assigned work matters more.
- **Tone constraint:** rewards stay positive — no red/✗/"Sai!" on child screens, no lives/hearts that can be lost, no leaderboards, no "don't lose your streak" loss-framing language.

## Technical Decisions

- **Server-authoritative, event-sourced state (AD-6):** `progress_events` is the append-only source of truth (kinds: `attempt`, `hint_requested`, `solution_shown`, `fallback_revealed`, `self_marked`, `quiz_submitted`, `session_started`, `session_completed`). Every event carries a client-generated UUIDv7 (idempotent resend) and the device's `occurred_at`, which determines the calendar day for Streak/Retry.
- Only the `learning` module grades, derives Stars/Retry/Streak/badges/first-try-accuracy, and materialises results into `progress_*` tables, **in the same transaction as the event**. The client never grades; Stars/results only ever come from the server's response. Dashboards (Epic 4) read materialisations and never recompute.
- Relevant backend module layout: `learning/` contains `problem_sets` (resolve), `sessions`, `events`, `graders/<type>.py`, `scoring`, `retry`, `streaks`, `badges`, `assignments`.
- Data model touchpoints (names/relationships only): `parent_profiles` → `progress_sessions` → `progress_events` (about `content_catalog_problems`); `parent_profiles` → `progress_retry_items`; `parent_profiles` → `progress_badges`.
- A Session **freezes** its ordered `problem_id` list and chunking (max 10 problems, "Phần i/n") at start (AD-9); later content changes don't affect an in-progress Session.
- Dates/times are stored and transmitted as UTC ISO-8601; the calendar day used for Streak/Retry/Assignment logic is derived from `occurred_at` converted to `Asia/Ho_Chi_Minh`.
- Client side: the event outbox (IndexedDB) sends events in order; Help/grades/Stars only render from server responses (AD-10).
- UI phrase catalogue for audio (badge names, praise lines, Home labels, states) lives at `frontend/src/audio/phrases.vi.json`; any new copy for Stars/Streak/badges/quiz needs entries there so `speak-missing` can synthesize audio.

## UX & Interaction Patterns

- **Home screen** shows: today's Assignment (if any), the "Luyện lại" card (only when at least one queued Problem is due — i.e., last wrong Attempt was on an earlier calendar day), the current Streak flame, total Stars, and the latest 3 badges.
- **Star burst:** gold stars visually fly from a correctly-answered Problem up into a running counter at the top of the screen; disabled under Reduce Motion (static count update + sound only, no flying stars/confetti).
- **Session summary** shows Stars earned, count correct on first try, Streak status/flame growth, any newly earned badge (with fanfare + 🔊 name), and a "Luyện lại bài sai" button that starts a `replay` Session of that Session's wrong Problems.
- **Badge component:** 96px round medal, gold ring, icon, short label; pops onto the Session summary on first earn.
- **Quiz Session UI:** Library/Lesson card shows a 📝 "Kiểm tra" indicator for quiz-eligible lessons. During play: no 💡, no Hint bubble, no correct/wrong banner — checking just shows "Đã lưu" and advances; progress dots only fill (no green/wrong distinction). Quiz results screen (after last Problem submits `quiz_submitted`) shows every Problem marked ✔ or ↻, Solutions for wrong ones, then the Stars earned.
- **Feedback banner (non-quiz modes):** correct → soft green, "Đúng rồi!", stars fly; wrong → soft orange, "Chưa đúng, thử lại nhé!", banner closes itself after Hint audio finishes and preserves the child's answer for editing.
- Copy examples for tone reference: Session end — "Em đã hoàn thành bài! Em được 22 ngôi sao." Streak — "4 ngày liên tiếp! 🔥" (never "don't lose your streak"). Empty Retry Queue — the "Luyện lại" card simply doesn't render (no empty-state message needed).

## Cross-Story Dependencies

- Story 3.1 (Stars/Streak) establishes the scoring transaction and materialisation pattern that Story 3.2 (badges) and Story 3.3 (Retry Queue) both build on — badges and Retry entries are derived from the same `progress_events` stream in the same transaction.
- Story 3.3's Retry Queue is populated by wrong Attempts happening in stories from Epic 2 (practice/hint/solution flow) and by Story 3.4's quiz submissions — quiz wrong-Problem handling must feed the same Retry Queue rules.
- Story 3.4 (quiz mode) reuses the Story 3.1 scoring rules (3 Stars / 0 Stars only, no Hint-adjusted 1-Star tier) and the Story 3.3 Retry Queue entry rule, but defers all grading to `quiz_submitted` instead of per-Part like other modes.
- Epic 4's parent dashboard (Story 4.2) reads Stars, Streak, accuracy and Retry Queue data materialised by this epic — it must not recompute any of this itself.
- The "Luyện lại bài sai" replay flow (Session summary, Story 3.1) intentionally does not affect Streak or Retry Queue exit counts, per AD-6's mode table — this is an explicit product decision, not an oversight, and should not change without updating AD-6.
