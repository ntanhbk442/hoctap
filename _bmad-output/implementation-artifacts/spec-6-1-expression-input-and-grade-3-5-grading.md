---
title: 'Story 6.1: expression_input and the grade 3-5 grading rules'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: '8cfeb5b99763163bcc97fde8a51194f040433387'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** ProblemDoc has 13 Part types, all grade 1; there is no `expression_input`, so grade 3-5 calculation problems can only become `fallback`. The keypad has no minus, operators or parentheses, and `ProblemPlayer` hard-codes `showComma={false}`, so a decimal answer cannot even be typed for `number_input` in grades 4-5.

**Approach:** Add `expression_input` across schema, child view, extractor and verify schemas, grader, widget and keypad, and speech. The grader compares by exact value (any equivalent expression passes) unless the Part requires an exact form, and grades 4-5 `3,5` = `3.5`.

## Boundaries & Constraints

**Always:**
- One change ships schema variant (`ExpressionInputView`/`Part`, answer per slot as an expression string), `child_view` stripping, extractor + verify models, both regenerated JSON schemas, grader, widget, OpenAPI types (`gen:api`) and speech (AD-1).
- The grader never uses `eval`. The safe evaluator `builder/arith.py` (exact `Fraction`, decimal comma, `+ - − × x * : / ÷`, parentheses, unary minus, size/depth caps) moves to a neutral module (`content/arith.py`) and `builder` re-imports it; `learning` must not import `builder`.
- Malformed, unparsable or empty input grades wrong for that slot, never raises; division by zero is wrong.
- A per-Part field selects the mode: `value` (default) or `exact` (child's text must equal the key after whitespace and operator-alias normalisation). The extractor sets `exact` only when the book demands a form.
- Keypad for `expression_input`: digits, comma, + − × : ( ), backspace, 80 px keys, in the existing bottom bar. `number_input` shows the comma key for grades 4-5 (grade from the Child Profile) and stays as is for grades 1-3.
- Speech reads `:` as "chia", "(" / ")" and U+2212 minus; the answer key is never spoken.

**Human decisions (Anh, 2026-09-30):** (1) `value` mode accepts ANY expression whose exact value equals the key (`3+4` passes for `7`), as the PRD says literally; `exact` mode still requires the same form. (2) Fractions are typed as `a/b` with a "/" key on the keypad; equal fractions are accepted unless the Part is `exact`; no fraction widget. (3) A minimal print-renderer stub ships with the type now (a small function in the content layer that renders an `expression_input` Part as printable text for the future worksheet renderer, e.g. its prompt plus a blank answer line, covered by a unit test); Story 7.1 builds on it. It must not add routes, endpoints or UI.

**Never:**
- No Alembic migration (content is JSON; head stays `0018_concept_guides`).
- No fraction widget, no `\frac` entry, no algebra (letters/variables), no CAS-style simplification checks.
- No full-corpus extraction or spend (Story 6.2); no changes to `_lenient_number`'s rules for existing types.
- Do not change grade-1 behaviour or existing golden schemas beyond adding the new variant.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Equivalent form | key `12 × 3`, mode `value`, child `36` or `(4×3)×3` | correct | N/A |
| Decimal comma | key `3,5`, child `3.5` or `03,50` | correct | N/A |
| Exact form required | key `2 × 3 + 4`, mode `exact`, child `10` | wrong | N/A |
| Whitespace/alias | mode `exact`, key `2×3`, child ` 2 x 3 ` | correct | N/A |
| Not an expression | child `3+`, `abc`, `` | wrong for that slot | no exception |
| Division by zero | child `5:0` | wrong | no exception |
| Multi-slot | 2 slots, one wrong | Part wrong, `wrong_keys=[that slot]` | N/A |
| Huge input | 5000-char string | wrong | evaluator size cap |

</frozen-after-approval>

## Code Map

- `backend/hoctap/content/schema.py` -- add `ExpressionInputView`/`Part`, answer entry type, `PROBLEM_TYPES`, `Part` union; regenerate `problemdoc.schema.json`
- `backend/hoctap/content/views.py` -- add the view to `ChildPart`
- `backend/hoctap/content/speech.py` -- operator words (`:`, parentheses, U+2212); problem speech refs
- `backend/hoctap/builder/arith.py` -- source of the evaluator; relocate to `content/arith.py`, re-export
- `backend/hoctap/builder/extraction/{prompt.py,models.py}` and `page_extraction.schema.json` -- teach the extractor the new type
- `backend/hoctap/builder/verify/{models.py,compare.py,prompt.py}` and `verify_page.schema.json` -- `ExpressionInputSecond`, code check for value equivalence
- `backend/hoctap/learning/graders.py` -- `grade_expression_input`, register in `_GRADERS`
- `frontend/src/pages/ProblemPlayer.tsx` -- widget dispatch, `SUPPORTED_TYPES`, keypad gating, `showComma`
- `frontend/src/components/NumberPad/` -- operator/parenthesis/minus keys (additive props)
- `frontend/src/components/widgets/` -- new `ExpressionInputWidget.tsx` (template with tappable slots, like `NumberInputWidget`)
- `frontend/src/api/schema.d.ts` -- regenerated
- `backend/tests/test_graders.py`, `test_problemdoc.py`, `test_verify.py`, `test_extraction.py`; frontend widget/pad tests

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/content/schema.py`, `views.py` -- new Part variant with mode field, covering-slot validation; regenerate schema JSON -- AD-1 single contract
- [x] `backend/hoctap/content/arith.py` (moved), `builder/arith.py` -- shared safe evaluator -- keeps `learning` free of `builder`
- [x] `backend/hoctap/learning/graders.py` -- value/exact grading, per-slot wrong keys, lenient decimal handling -- FR-12
- [x] `backend/hoctap/builder/extraction/*`, `builder/verify/*` -- prompt, models, JSON schemas, code check -- grade 3-5 pages can be extracted (run in 6.2)
- [x] `backend/hoctap/content/speech.py` -- read the new symbols -- audio for every expression Part
- [x] `frontend` NumberPad, widget, ProblemPlayer, generated types -- keypad and dispatch; comma for grades 4-5 on `number_input`
- [x] Tests for every I/O row, `child_view` stripping, schema round-trip, keypad keys, widget entry and submit shape

**Acceptance Criteria:**
- Given an `expression_input` Problem, when it is published and fetched as the child, then no `answer`, `hint`, `solution` is present and the widget renders.
- Given a wrong Attempt then a second wrong one, when submitted, then staged help behaves as for other types.
- Given a grade 4-5 Child Profile, when a `number_input` Part is open, then the comma key is shown and `3,5` grades correct against `3.5`.
- Given the grade-1 fixtures, when the full backend and frontend suites run, then nothing regresses.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Submitted shape mirrors the keyed convention: `list[{"key": slot_key, "value": "<typed text>"}]`. Grade 3-5 content is not extracted yet (the pilot was grade 1; all 30 Books are catalogued in `content/catalog/books.py`), so tests use hand-written fixtures. `_lenient_number` is not reused for expressions; a plain number is just a one-term expression, so `07` and `3.5` fall out of the evaluator (extend its number token to accept a leading zero and a `.` separator).

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: all pass
- `cd backend && uv run ruff check . && uv run hoctap export-schema` -- expected: clean, JSON schemas unchanged after regeneration
- `cd frontend && npm run gen:api && npm test -- --run && npm run lint && npm run build` -- expected: pass

**Manual checks (if no CLI):**
- Open a fixture `expression_input` Problem on the child player: type `(4×3)×3`, submit, see the correct banner; type `3+` and see a wrong Attempt, not an error.

## Implementation Notes

- (2026-09-30) `expression_input` Part: a template with `[[slot]]` markers, an answer expression per slot (max 100 characters) and `mode` (`value` by default, or `exact`). The evaluator (exact `Fraction`s, `+ - × : ( ) /`, decimal comma or dot, unary minus, capped at 500 characters and a fixed depth) moved to `content/arith.py`; `builder/arith.py` re-exports it. In `value` mode any expression with the same exact value passes (`3+4` for `7`, `3/6` for `1/2`); in `exact` mode the text must match the key after whitespace and operator-alias normalisation. Unparsable input, empty input and division by zero grade wrong for that slot. Extractor and verify prompts are bumped to p3/v3, and the child view carries no answer, hint or solution.
- Client: `NumberPad` gains an `expression` variant (operators, parentheses, `/`, comma, backspace), `ExpressionInputWidget` follows the `number_input` template pattern, and `ProblemPlayer` takes a `grade` prop (from the Child Profile) so grades 4-5 get the comma key on `number_input`. Print stub: `content/printing.py` renders the prompt plus a blank answer line; no routes or UI.
- Risks and gaps: the speech normaliser is duplicated in `frontend/src/audio/speech.ts` and must stay in step with the backend (hash-parity tests exist); `mode` is optional in the extraction schema (omitted means `value`), so the extractor is not forced to state it; a Part with an empty `prompt` gets no audio button; the child-player behaviour was not checked in a real browser; **no grade 2-5 content has been extracted yet** (Story 6.2), so all tests use hand-written fixtures.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_graders.py tests/test_problemdoc.py tests/test_speech.py tests/test_printing.py tests/test_extraction.py tests/test_verify.py tests/test_sessions.py tests/test_problem_sets.py tests/test_library.py tests/test_app.py tests/test_review.py tests/test_guides.py` — 685 passed (the implementing agent reported the full backend suite at 1046 passed). Regenerated OpenAPI file and types are unchanged; the three JSON schemas are checked by tests against the committed files.
- Frontend `tsc -b` and `eslint .` clean. `src/pages` + `src/components` with `--pool=vmThreads`: 297 passed, 4 failed — the three known pre-existing `ExtractionPage` failures and `ProblemPlayer.speaker.test.tsx`, which needs `--pool=threads` (`crypto.subtle` is undefined under vmThreads); with `--pool=threads`, `speech.test.ts` and `ProblemPlayer.speaker.test.tsx` pass (31 tests).
- Checked by hand: the evaluator rejects injection, deep nesting, division by zero, powers and 5,000-character input instantly; grading matches the decisions (`3+4`=`7` and `3/6`=`1/2` in value mode, rejected in exact mode; `3,5`=`3.5`).
