---
title: 'Story 7.1: Printable worksheets'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: '42592fe07b6da8e97e8219bd8da87aafdfa65805'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Anh cannot put Bin's practice on paper. Only a one-Part text stub exists (`content/printing.py`, `render_expression_input`, Story 6.1); there is no route, page, print CSS or PDF dependency, and no "In phiếu" action in the Parent Area.

**Approach:** Add a parent-only worksheet endpoint that resolves a Lesson or Concept Problem Set (an Assignment is a Lesson ref) via `learning.problem_sets.resolve()` and returns effective Problems with Answer Keys, plus a `/parent/print` page that renders an A4 black-and-white worksheet and a separate answer page, printed with the browser's print or "Save as PDF" (PRD FR-22).

## Boundaries & Constraints

**Always:** Use `resolve()` for the set and effective docs for content, so hidden, retired or unapproved-`needs_review` Problems are excluded exactly as for the child. Answers appear only on the answer page after a page break, and the endpoint needs the parent PIN cookie. Render all 14 Part types, with `match` as dots, answer slots as empty boxes, `fallback` as the crop image, and crops via `crop_url`. Print CSS is A4, no colour-only meaning, Vietnamese diacritics intact, and it must work offline (no CDN, self-hosted fonts). Print chrome (buttons, nav) is hidden by `@media print`.

**Human decision (Anh, 2026-09-30):** a Concept worksheet is the same set a child would practise: up to 10 visible Problems from `resolve()`, unsolved-first for the chosen child profile, in Book order after those; the parent picks the child for a Concept sheet.

**Never:** Server-side PDF generation or a new Python dependency. No Answer Key, Hint or Solution in the problem pages or in any child-facing route. No hand-picked/custom Problem selection, worksheet persistence, or new DB tables. No changes to `resolve()` semantics. Do not delete the Story 6.1 text stub.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Lesson worksheet | Lesson with 12 visible Problems | Problems in Book order, numbered; answer page after a page break | N/A |
| Assignment | Assignment for a Lesson | Same as its Lesson | N/A |
| Concept worksheet | Concept id + child profile | The `resolve()` set for that profile | Unknown profile: 404 error envelope |
| Hidden Problem | One Problem hidden or under parent report | Omitted from both pages | N/A |
| Match / fallback | `match` Part; `fallback` Problem | Dots to connect; crop image with a blank writing area | Missing crop: Problem text, no broken image |
| Empty set | No visible Problems | Page says the set is empty; print button disabled | N/A |
| No parent cookie | Any request | 401 error envelope | Redirect to `/parent/login` |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/problem_sets.py` -- `resolve()`, `LessonRef`, `ConceptRef`; the only set definition.
- `backend/hoctap/content/effective.py` -- `load_effective`/`effective_problem`: docs with answers, `visible`.
- `backend/hoctap/content/printing.py` -- 6.1 text stub; reference for slot-blank rendering.
- `backend/hoctap/content/assets.py` -- `crop_url`.
- `backend/hoctap/api/review.py`, `api/deps.py` -- parent router pattern, `require_parent`.
- `backend/hoctap/app.py` -- router registration.
- `frontend/src/pages/ProblemPreview.tsx`, `pages/Assignments.tsx`, `pages/ParentHome.tsx` -- parent Problem rendering; entry points for "In phiếu".
- `frontend/src/App.tsx`, `frontend/src/api/schema.d.ts` -- routes; generated client types.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/api/worksheets.py` -- parent-only `GET /api/parent/worksheet` (lesson keys or `concept_id`+`profile_id`) returning ordered Problems with Parts, Answer Keys and crop URLs -- one resolver, no answer leaks
- [x] `backend/hoctap/app.py` -- register the router; regenerate `schema.d.ts`
- [x] `frontend/src/print/` -- per-type print renderers for the 14 Part types, `WorksheetPage`, answer page, `print.css`
- [x] `frontend/src/App.tsx`, `pages/Assignments.tsx`, `pages/ParentHome.tsx` -- `/parent/print` route; "In phiếu" links for a Lesson, Concept and Assignment
- [x] `backend/tests/test_worksheets.py`, `frontend/src/print/*.test.tsx` -- test each I/O row, and that every Problem Type has a renderer

**Acceptance Criteria:**
- Given a Lesson, when I tap "In phiếu", then a preview shows A4 problem pages with no answers, then an answer page after a page break.
- Given the printed output in greyscale, when I read it, then every slot is an empty box or line, and `match` shows dots.
- Given no network, when I open the preview, then it renders with local fonts and assets.
- Given a wrong or missing PIN cookie, when the endpoint is called, then no Problem content is returned.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Print renderers live in the frontend (`frontend/print`, per the architecture) because the browser does the printing; the backend stub stays as a plain-text reference. An Assignment is stored as a Lesson ref, so it needs no separate kind. Alembic head stays `0019_full_run`; no migration.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_worksheets.py tests/test_printing.py && uv run ruff check .` -- expected: pass
- `cd frontend && npm test -- print && npm run build` -- expected: pass

**Manual checks (if no CLI):**
- Chrome print preview (A4, greyscale, "Save as PDF") of a Lesson with `match` and `fallback`: no clipped boxes, answers only on the last page(s).

## Implementation Notes

- (2026-09-30) `GET /api/v1/parent/worksheet` (`backend/hoctap/api/worksheets.py`) sits behind `require_parent` for the whole router. It takes a Lesson (`book_id`+`unit_key`+`lesson_key`) or a Concept (`concept_id`+`profile_id`), builds the set with the same `learning.problem_sets.resolve()` a Session would freeze (a Concept sheet is therefore the up-to-10 set for the chosen child, unsolved first — Anh's decision), and returns each effective doc with its Answer Keys, `crop_url` and `image_urls` (only for crops that exist on disk). Hidden, retired, reported and unapproved Problems are skipped. An Assignment prints as its Lesson. No migration and no new dependency; the Story 6.1 text stub in `content/printing.py` is untouched.
- Frontend `frontend/src/print/`: one renderer for each of the 14 Part types (the compiler rejects a missing one), `WorksheetPage` with the question pages and, after a forced page break, the answer page; `print.css` sets A4, black on white and greyscale images, hides buttons and the PWA badge, and uses the self-hosted Nunito fonts. A `/parent/print` route, "In phiếu" links on each Assignment, and a `PrintPicker` on the Parent Area home for a Lesson or a Concept plus a child.
- Answer-leak guard: besides the agent's renderer tests, `frontend/src/print/leak.test.tsx` (added in review) replaces every answer, hint and solution value of every backend fixture Problem with a unique sentinel and fails if any appears in the rendered question section, text or attributes; it passes for all 14 Problem Types.
- Gaps: not viewed in a real browser or printer (A4 layout, greyscale, page-break placement and "Save as PDF" are unchecked); the Lesson picker lists Books by the chosen child's grade; `image_select` regions and `connect_dots` dots are drawn as numbered overlays on the crop, which the spec did not describe.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_worksheets.py tests/test_printing.py tests/test_problem_sets.py tests/test_library.py tests/test_app.py tests/test_sessions.py tests/test_assignments.py tests/test_review.py tests/test_guides.py` — 247 passed (the implementing agent reported 1080 passed on the full backend suite). Regenerated OpenAPI file and types are unchanged.
- Frontend `tsc -b` and `eslint .` clean; `src/pages` + `src/print` with `--pool=vmThreads`: 291 passed, 4 failed — the three known pre-existing `ExtractionPage` failures and `ProblemPlayer.speaker.test.tsx`, which needs `--pool=threads`; with `--pool=threads`, `speech.test.ts` and `ProblemPlayer.speaker.test.tsx` pass (31 tests).
