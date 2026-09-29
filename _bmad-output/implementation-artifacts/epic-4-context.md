# Epic 4 Context: Anh sees progress and steers practice

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic gives Anh (the parent) control and visibility: manage up to 4 Child Profiles and their settings, see each child's progress at a glance, assign a day's work, and handle Error Reports (from the parent and from the child's 🚩). It turns the app from something Bin uses alone into something Anh steers. Dashboards only read what earlier epics already materialised.

## Stories

- Story 4.1: Profiles and settings
- Story 4.2: Progress dashboard
- Story 4.3: Assignments
- Story 4.4: Error Reports from the parent and the child

## Requirements & Constraints

- Up to 4 Child Profiles (name, avatar, Grade); v1 is built for one child. The parent can also change the PIN and switch audio auto-play on or off per child. The child app shows a profile picker only when more than one Profile exists.
- The Parent Area is entered from a 🔒 on Home by a 2-second long-press then a 4-digit PIN, so a child cannot open it by accident.
- Dashboard per child: Sessions and time per day and week, first-try accuracy (self-checked results are shown but not counted), progress per Book and Unit, weakest Concepts (only Concepts with at least 5 Attempts, ranked by first-try accuracy), and recent mistakes with the child's answer beside the correct one.
- Assignment: any Problem Set or Concept practice set assigned to a date; shows first on Home that day; done when all its Sessions are complete; unfinished ones carry over (a "Hôm qua" ribbon, no guilt copy). Dashboard statuses: Chưa làm, Đang làm ("Phần i/n"), Đã xong.
- Error Reports: a parent report hides the Problem from the child until resolved in Content Review; a child's 🚩 (after a "Có" confirm) creates a report under Cần duyệt, keeps the Problem visible, and tells Bin "Đã báo cho bố mẹ".
- Child-facing copy stays positive: no red, ✗ or "Sai!". New spoken copy needs entries in the phrase catalogue for audio.

## Technical Decisions

- Parent routes sit behind a signed httpOnly PIN cookie (30-minute idle expiry, slid on each request). Child routes take a `profile_id` and need no PIN; they reach only the child view, that Profile's own progress, and the child-flag service.
- `parent/` owns `parent_settings` (PIN, lockout) and `parent_profiles`; only it writes them. Dashboards and Assignment status read the `learning` materialisations and never recompute grading, Stars or accuracy (AD-6).
- An Assignment stores a `ProblemSetRef`; Sessions freeze their ordered problem list and chunking (max 10 per Session) at start (AD-9). Resolution goes through the single `learning.problem_sets` resolver.
- Error Reports are created through the `content.review` service, which is the only writer of review state.
- Calendar days for carry-over and per-day figures are derived in Asia/Ho_Chi_Minh from event timestamps; times are stored as UTC ISO-8601.
- Runtime ids are UUIDv7 strings; the frontend API client is generated from the OpenAPI schema.

## UX & Interaction Patterns

- Child navigation is flat: one big back button, no menus. The Parent Area has its own menu (Dashboard, Duyệt nội dung, Settings, extraction); on a PC the dashboard is two-column.
- Settings lists Child Profiles, PIN and per-child auto-play; backup and restore rows are also planned there (not part of these stories).
- Assign is reachable from the Dashboard and from any Lesson or Concept in the Parent Library; parent 🚩 "Báo lỗi" appears in the Library preview and in recent mistakes, with an optional note.

## Cross-Story Dependencies

- Story 4.1's profile management and Parent Area menu are the entry point for 4.2 to 4.4; the dashboard (4.2) is per child and needs the profile list.
- Story 4.3 adds the Assignment card to Home and its status to the dashboard from 4.2; Story 4.4's parent flag is also reachable from 4.2's recent mistakes.
- Depends on Epic 3's materialised Stars, Streak, accuracy and Retry data, and on Epic 1's Content Review for Error Reports.
