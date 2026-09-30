---
title: 'Story 5.2: Concept guide screen and practice'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: 'd6ec6f20abb2e936f977190e01cac805133c2f23'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 5.1 stores and approves Concept Guides, but no child can see one: there is no child read, no 📖 on the Problem, no Library Concept tab, and the `concept` ProblemSetRef still raises `UnsupportedProblemSetRef` although `concept` is already allowed as a Session mode (DB CHECK, Star and badge gates).

**Approach:** Add a child read of a Concept and its approved Guide, a `concept` ProblemSetRef with server-derived mode `concept`, a Guide overlay (explanation, worked example, per-field 🔊, "Luyện tập"), a 📖 button on the Problem, and a "Khái niệm" tab in the Library.

## Boundaries & Constraints

**Always:** Only `effective_concept_guide()` supplies Guide text, and a child read returns a Guide only when `approved` is true (unapproved or missing both return `guide: null`, never a hint that a draft exists). All Problem selection goes through `learning.problem_sets.resolve()`. A Concept practice set is up to 10 `visible_to_child` Problems linked to the `concept_id` in `content_review_problem_concepts`, both Editions, Problems the Profile has not solved correctly on the first try first, then Book order (AD-9). `mode` is derived from `ref.kind`: `concept` ref means `mode='concept'`; a client `mode` that disagrees gives 422 `MODE_REF_MISMATCH`. Concept Sessions score like `practice` (Stars, Retry Queue, Streak, badges: AD-6 table, no new code). The overlay sits above the mounted `ProblemPlayer`, so closing it keeps the typed answer. Every Guide text field has its own 🔊 through `speak(text)` (client-side `speechKey`, the same normaliser as `guide_speech_refs()`); a missing clip greys the button and keeps the text. Child copy is positive: no red, no ✗, no "Sai!". Purple `hint` token. Human decisions: 📖 is always shown on a Problem that has Concepts (outside quiz Sessions); with no approved Guide the overlay says so and "Luyện tập" stays available; Concept practice may start for any Concept with visible Problems, including from the Library tab, whether or not its Guide is approved; opening a Guide never changes Stars or Hint rules (it is not staged help and adds no event kind).

**Never:** No new table or migration (head stays `0018_concept_guides`). No Guide edit, approval or generation change. No Assignment of a Concept set (Assignments are Lesson-only today; a `concept` ref with `assignment_id` keeps giving 422 `ASSIGNMENT_REF_MISMATCH`). No 📖 in `quiz` Sessions. No Guide auto-play. Opening a Guide does not change Hint or Star rules. No answer key in any new response.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Open Guide | Problem with an approved Guide, tap 📖 | Overlay shows explanation, example, 🔊 per field, "Luyện tập"; close returns to the same Problem, answer kept, audio stopped | N/A |
| No approved Guide | Concept with none or unapproved | Overlay shows "Chưa có hướng dẫn cho khái niệm này" and still offers "Luyện tập"  | N/A |
| Several Concepts | Problem with 2-3 `concept_ids` | Chips with each Concept name; first selected | N/A |
| Start practice | `{kind:'concept', concept_id}` with 14 visible Problems | Session `mode='concept'`, 10 Problems: unsolved first, then Book order | N/A |
| All solved | Every Problem solved first try | Still up to 10, Book order | N/A |
| Unknown Concept | bad `concept_id` | 404 `CONCEPT_NOT_FOUND` | Vietnamese message |
| Nothing visible | Concept with no visible Problems | 422 `EMPTY_PROBLEM_SET`; "Luyện tập" hidden when the count is 0 | Existing message |
| Mode mismatch | `ref.kind='concept'`, `mode='practice'` | 422 `MODE_REF_MISMATCH` | N/A |
| Guide offline | Fetch fails | Overlay says it cannot load, "Đóng" works, Problem untouched | Friendly retry line |
| Library tab | Child's Grade | "Khái niệm" tab lists Concepts with visible-Problem counts; tap opens the same Guide screen | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/learning/problem_sets.py` -- add `ConceptRef`, `ref_key` (`concept:{id}`), a `resolve()` branch; drop `concept` from `UnsupportedProblemSetRef` text.
- `backend/hoctap/api/sessions.py` -- `ConceptRefIn` in the `ref` union, `mode` literal gains `concept`, derivation branch.
- `backend/hoctap/learning/sessions.py` -- `start_session` takes any ref; no change expected beyond the ref type.
- `backend/hoctap/learning/summary.py` -- first-try-correct logic to reuse for "solved on the first try".
- `backend/hoctap/content/effective.py` -- `effective_concept_guide()`, `visible_to_child()`; `content/review/models.py` -- `content_review_concepts`, `content_review_problem_concepts`.
- `backend/hoctap/api/library.py` -- new child reads `GET /library/concepts?grade=` and `GET /library/concepts/{concept_id}` (name, grade, visible count, `guide` or null); then regenerate OpenAPI and `frontend/src/api/schema.d.ts`.
- `frontend/src/api/queries.ts` -- `useLibraryConcepts`, `useLibraryConcept` (the existing `useConceptGuide` is the parent one), `useStartSession` accepts the concept ref.
- `frontend/src/pages/SessionPlayer.tsx` -- 📖 beside `FlagButton` (hidden when `isQuiz` or no `concept_ids`), overlay state.
- `frontend/src/pages/Library.tsx` -- "Sách | Khái niệm" toggle.
- `frontend/src/components/SpeakerButton/`, `frontend/src/audio/speech.ts`, `audio/player.ts` -- reuse `speak`, `isMissing`.
- New `frontend/src/components/ConceptGuide/ConceptGuide.tsx` (+ css, test).
- `backend/tests/test_sessions.py`, `test_library.py`; `frontend/src/pages/SessionPlayer.test.tsx`, `Library.test.tsx`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/learning/problem_sets.py` -- `ConceptRef` and resolver (link table, `visible_to_child`, unsolved-first ordering, cap 10) -- single resolver (AD-9)
- [x] `backend/hoctap/api/sessions.py` -- concept ref and derived mode -- `MODE_REF_MISMATCH` stays server-decided
- [x] `backend/hoctap/api/library.py` -- child Concept list and detail reads, approved-only Guide -- Story 5.1 visibility rule
- [x] OpenAPI and `schema.d.ts` -- regenerate -- typed client
- [x] `frontend/src/components/ConceptGuide/` and `SessionPlayer.tsx` -- overlay, 📖, "Luyện tập" starts the Session and navigates -- FR-15
- [x] `frontend/src/pages/Library.tsx` -- Khái niệm tab -- second entry point
- [x] backend and frontend tests -- every matrix row; no test calls TTS or Claude

**Acceptance Criteria:**
- Given a `concept` Session, when the child answers, then Stars, Retry Queue, Streak and badges behave as in `practice`, and `replay` and `quiz` rules are unchanged.
- Given an Assignment or Home card flow, when nothing is changed, then existing Lesson, retry and replay Sessions start exactly as before.
- Given an unfinished Session, when "Luyện tập" starts a new one, then the old Session stays unfinished and resumable from Home.

## Design Notes

"Solved on the first try" default: the Problem was first-try-correct in some earlier Session of this Profile, reusing the `learning.summary` rule; `quiz` and `replay` Sessions do not count. One query over the Profile's `attempt` events, not one per Problem.

## Verification

**Commands:**
- `cd backend && ruff check . && pytest tests/test_sessions.py tests/test_library.py tests/test_scoring.py tests/test_app.py` -- expected: pass
- `cd frontend && npx tsc -b && npx eslint . && npx vitest run --pool=vmThreads src/pages src/components` -- expected: pass
- `cd frontend && npx vitest run --pool=threads src/audio src/pages/ProblemPlayer.speaker.test.tsx` -- expected: pass

**Manual checks (if no CLI):**
- With one approved Guide: tap 📖 mid-answer, hear a field, close, answer still typed; tap "Luyện tập" and finish a `concept` Session.

## Implementation Notes

- (2026-09-30) `ConceptRef` resolves up to 10 `visible_to_child` Problems linked to the Concept, unsolved-first (`summary.first_try_solved_problem_ids`, one query, ignoring quiz and replay Sessions) then Book order; an unknown Concept gives 404 `CONCEPT_NOT_FOUND`. `POST /sessions` derives `mode='concept'` from the ref kind; a concept ref with an `assignment_id` still gives 422 `ASSIGNMENT_REF_MISMATCH`. `GET /library/concepts?grade=` and `GET /library/concepts/{id}` return a Guide only when it is approved (otherwise `null`). No migration.
- Frontend: `ConceptGuide` overlay (explanation, worked example, a 🔊 per text field, chips for several Concepts, "Luyện tập", and a "Chưa có hướng dẫn" state), 📖 in `SessionPlayer` (hidden in quiz Sessions), a "Khái niệm" Library tab, and the session route keyed by session id so "Luyện tập" starts clean. The overlay sits above the mounted `ProblemPlayer`, so the typed answer survives closing it.
- Gaps: the concept set does not check the child's Grade (the UI only lists the child's Grade); assigning a Concept practice set is not possible (Assignments are Lesson-only), which needs a follow-up story; one fixture in `SessionPlayer.test.tsx` uses an `as never[]` cast; overlay layout and audio were not checked in a running browser; `src/components` tests and the `--pool=threads` audio run were not run by the implementing agent (I ran the audio tests in the threads pool).

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_concept_practice.py tests/test_problem_sets.py tests/test_sessions.py tests/test_library.py tests/test_app.py tests/test_guides.py tests/test_assignments.py tests/test_retry.py tests/test_quiz.py` — 241 passed (the agent reported the full backend suite at 1001 passed).
- Frontend `tsc -b` and `eslint .` clean. Whole `src/pages` suite with `--pool=vmThreads`: 238 passed, 4 failed — the three known pre-existing `ExtractionPage` failures and `ProblemPlayer.speaker.test.tsx`, which needs `--pool=threads` (`crypto.subtle` is undefined under vmThreads); with `--pool=threads`, `ProblemPlayer.speaker.test.tsx` and `speech.test.ts` pass (26 tests). The four directly affected files (SessionPlayer, Library, ConceptGuide, Home) pass 78 of 78.
