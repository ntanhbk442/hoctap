# Epic 8 Context: Timed exam practice

<!-- New epic, added 2026-10-02 directly by Anh (not in the original PRD/epics planning
docs) -- see spec-8-1's own Intent for the full brainstorming trail. -->

## Goal

A randomly-generated, timed practice exam: a parent (or, by explicit decision, the child
too) picks a scope (one or more Concepts, a Book+Unit range, or the whole Grade), a
problem count and a time limit, and the app draws a fresh random Problem Set under those
constraints. This is a deliberate, acknowledged departure from this app's "no timers, no
pressure" design philosophy for child screens (see `EXPERIENCE.md`'s "No timers on child
screens" rule) -- Anh explicitly chose a real, visible countdown for exam-realism practice,
gated per Child Profile so it only applies where a parent has turned it on.

## Stories

- Story 8.1: Exam generation with random problem sets

## Requirements & Constraints

- **Scope kinds:** `concept` (one or more Concept ids), `book_unit` (a Book id, optionally
  bounded to a Unit range), or `grade` (the Profile's whole Grade). Sampling always goes
  through the same `visible_to_child()` gate every other child-facing selection uses --
  hidden/retired/needs_review/conflicted Problems are never drawn.
- **Problem count:** the parent/child asks for N; fewer eligible Problems in the scope is
  not an error, the exam just gets a smaller set (never pads with ineligible Problems).
- **Time limit:** minutes, parent/child-set. The backend is the source of truth
  (`started_at` + `time_limit_s` on the Session row), so a closed-and-reopened tablet does
  not reset the clock, mirroring how Story 2.11 already makes "Tiếp tục" resume state
  entirely server-side.
- **No feedback until submitted** (same mechanic as Story 3.4's Quiz mode -- attempts are
  stored ungraded, a dedicated submit event grades the whole Session in one pass).
- **No Stars, no Retry Queue entry, no Streak effect** -- `exam` sits outside
  `STAR_AWARDING_MODES` alongside `quiz` and `replay`. Pure assessment.
- **Timeout:** auto-submits whatever is answered; unanswered Problems grade as wrong, same
  as Quiz mode's own "unanswered or fallback Problem" row.
- **Per-Profile gate:** `parent_profiles.exams_enabled` (default off) -- a parent must turn
  it on per child before that child can see any exam entry point, parent-assigned or
  on-demand.
- **Both launch paths:** a parent can configure and assign an exam ahead of time (reusing
  the existing Assignment machinery with a new exam-scope ref instead of a Lesson ref), and
  a child with `exams_enabled=true` can configure and start one on demand from the Library.
  Anh's explicit call: the child gets the SAME full scope/count/time picker a parent would
  use, not a simplified default -- a deliberate complexity trade-off, not an oversight.
