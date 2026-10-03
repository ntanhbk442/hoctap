# Epic 9 Context: Child experience polish

<!-- New epic, added 2026-10-03 directly by Anh (not in the original PRD/epics planning
docs) -- see spec-9-1's own Intent for the full diagnosis trail. -->

## Goal

Anh reported the child-facing screens feel "hard to use" (visual design + navigation).
Investigation found the root cause is NOT that the design system is missing or wrong --
`DESIGN.md`'s tokens are correctly generated into `tokens.css`, and leaf components built
from them (`HomeCard`, `Badge`, `AnswerSlot`, `NumberPad`) are correctly styled. The gap is
that the PAGE SHELLS around those components were never wired up to the design system or to
`EXPERIENCE.md`'s own navigation model: every child screen uses a bottom-of-page text link
("Về trang chủ" / "Về Sách") instead of the spec's persistent top-left ⬅ back button, the
base page font/background falls back to generic `system-ui`/white instead of Nunito/warm
cream, and Library's lesson rows are plain thin-bordered boxes instead of `HomeCard`-style
chunky cards.

## Stories

- Story 9.1: Child screen navigation and visual polish

## Requirements & Constraints

- **A single shared `ChildTopBar` component** (⬅ back, progress dots when in a Session, 🔊
  where relevant) replaces every bottom-of-page "Về trang chủ"/"Về Sách" text link across
  Home, Library, LessonDetail, Badges, and SessionPlayer/the Problem screen -- matching
  `EXPERIENCE.md`'s explicit "every child surface has one big ⬅ back button in the top-left
  corner and nothing else in the chrome" rule.
- **Base page styles** (`frontend/src/index.css`'s `:root`/`body`) switch from the generic
  `system-ui` font and white background to the design tokens (`--font-body-family` /
  `--color-surface-base`) every child page should already be inheriting.
- **Library's book/unit/lesson rows and the Badges layout** are restyled to match
  `HomeCard`'s established chunky-card look (icons, `rounded.lg`/`rounded.md`, the 4px
  "physical button" bottom-edge shadow) instead of today's thin bordered list rows.
- Pure frontend change: CSS plus one new shared component and its wiring into 5 existing
  pages. No backend/API changes, no new Problem Type, no new Session mode.
- This is explicitly scoped to the CHILD-facing experience only -- the Parent Area's own
  navigation/visual design (a separate, larger piece of work Anh named but did not ask to
  start yet) is out of scope for this story.
