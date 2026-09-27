---
title: 'Story 1.6: Verify answers and flag disagreements'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'tree:d374be53deb411461ef6942fdad84ff437151ac2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A wrong Answer Key teaches Bin a mistake. Every extracted Answer Key must be checked independently, and any doubt must hide the Problem until Anh reviews it (FR-3, AD-7).

**Approach:** Add a `verify` stage after `validate`:
- For each page with valid ProblemDocs, make one `claude -p` call. It gets the page image and the child view of each Problem (no answers), solves every Part independently, and returns answers in the same answer shapes.
- Compare the second answer with the extracted one Part by Part. Where arithmetic can be computed, check it in code with `builder.arith`.
- Also check that no Hint reveals its answer.
- Record a verdict per Problem. Any disagreement or failure sets `needs_review`.

## Boundaries & Constraints

**Always:**
- **Same client and guards as Story 1.5:** `ClaudeCliClient`, the isolation flags, a temp cwd, cost recording, the total budget cap, `--yes-spend`, and resume by `build_jobs` with `stage="verify"`. The verify input hash covers the page image hash, the child-view JSON, the verify prompt version, the model and the schema.
- **No answers in the prompt:** the verify prompt includes only `child_view()` data (AD-5). The extracted answers never appear in it.
- **Schema:** `VerifyPage = {problems: [{problem_id, parts: [{part_key, answer}]}]}`. `answer` reuses the Story 1.4 answer models, keyed by part type through a per-Part discriminated union (`type` + `answer`). It is passed through `transform_schema` with the same no-collapse guard test.
- **Comparison:** answers are normalised before comparing.
  - Keyed answers: map equality through `answer_map`.
  - `selected` / `regions`: set equality. For regions, count and IoU ≥ 0.5 on each matched bbox.
  - `order` / `sequence`: list equality.
  - `match`: set of pairs.
  - `fallback`: always agrees.
- **`builder.arith.evaluate(expr) -> Fraction | None`:** a safe parser, with no `eval`, for integers and decimal-comma numbers, `+ − × : ( )`, and `x`/`*`//` as aliases. Use:
  - For `number_input` templates of the form `<expr> = [[slot]]` or `[[slot]] = <expr>`, compute the slot.
  - For `compare` rows where both sides evaluate, compute `<`/`>`/`=`.
  - Where the code result exists and differs from the extracted answer, the verdict is disagree, whatever the model said.
- **Hint check:** for each Part whose answer is one number, a Hint containing that exact number as a standalone token counts as a leak. A leak is flagged as a reason; it does not change the answer verdict.
- **Verdict per Problem:** `agree` | `disagree` | `unverified` (the verify call failed or the Problem was missing from its output), plus a list of reasons (`part_key`, `kind`, `extracted`, `second`, `code`).
- **Storage:** the verdict is stored on the `build_page_results` row (`verify_status`, `verify_reasons_json`, `needs_review` 0/1). `needs_review` = 1 for `disagree`, for `unverified`, or for any hint leak. A validate rebuild (Story 1.5) marks affected rows as unverified again.
- **Command:** `hoctap build verify --book --pages` (same flags as pilot), and `build pilot` runs verify after validate unless `--no-verify` is given.

**Never:**
- No UI and no publishing (Stories 1.7 and 1.8). No regenerating Hints; flag only.
- No real CLI calls in tests (use `FakeClaudeClient`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Agree | second answer equals the extracted one | `agree`, needs_review 0 | N/A |
| Model disagrees | second answer differs on one slot | `disagree` with that slot's reason; needs_review 1 | N/A |
| Code overrides | `3 + 4 = [[s1]]`, extracted 8, model says 8 | `disagree` (code says 7) | N/A |
| Code confirms | `3 + 4 = [[s1]]`, extracted 7, model says 7 | `agree` | N/A |
| Compare by code | row `5 + 2` vs `8`, extracted `<` | `agree` | N/A |
| Unparsable expr | template with words, e.g. "Có [[s1]] bạn" | arith skipped; model verdict only | N/A |
| Hint leak | answer 7, Hint "Đáp án là 7" | reason `hint_leak`, needs_review 1 | N/A |
| Missing problem | verify output lacks one problem_id | that Problem `unverified`, needs_review 1 | N/A |
| Call fails | refusal or timeout | all the page's Problems `unverified` | cost recorded |
| No answers in prompt | any page | the verify prompt and schema input contain no extracted answer, hint or solution text | test asserts |
| Resume | re-run unchanged | 0 verify calls | N/A |
| Region IoU | spot_difference regions shifted slightly (IoU 0.7) | agree | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/stages/validate.py` -- it writes `build_page_results` (`doc_json`, `status`). Verify reads the rows with a valid status. A rebuild must reset the verify columns.
- `backend/hoctap/builder/stages/extract.py`, `claude_client.py`, `costs.py`, `jobs_store.py`, `pilot.py` -- reuse the call, retry, cost, budget and concurrency machinery. Factor shared pieces out rather than copying them.
- `backend/hoctap/content/schema.py` -- the answer models, `answer_map`, `parse_number`.
- `backend/hoctap/content/views.py` -- `child_view()` for the prompt.
- `backend/hoctap/builder/extraction/prompt.py` -- the pattern for prompt, version and schema. Add `builder/verify/` alongside it.
- Migrations: the latest is `0004_build_tables` (released locally). Add `0005_verify_columns`.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/builder/arith.py` -- a safe expression evaluator using Fraction, with tests.
- [x] `backend/hoctap/builder/verify/{models,prompt,compare}.py` -- the VerifyPage schema (plus its committed schema JSON and export command), the prompt, and the comparison and hint-leak logic.
- [x] `backend/hoctap/builder/stages/verify.py` -- the stage runner, reusing the 1.5 machinery.
- [x] `db/alembic/versions/0005_verify_columns.py` + models -- the verify columns on `build_page_results`.
- [x] `backend/hoctap/cli.py` -- `build verify`, and verify inside `build pilot` (`--no-verify`).
- [x] `backend/tests/test_verify.py` -- every matrix row, plus arith unit tests, with the fake client.

**Acceptance Criteria:**
- Given pilot pages already validated, when `hoctap build verify --book toan1-2020-q1 --pages 5-7 --dry-run` runs, then the verify requests are written containing no answers, and the estimate is printed with no call made.

## Implementation Notes

- The call/retry/cost/budget pool moved from `stages/extract.py` into `builder/calls.py` (`run_calls`, `CallJob`); extract and verify both use it. `PageRequest` gained `stage` (not sent to the CLI) so fakes can tell calls apart.
- `verify_model` (default = `extraction_model`) is used for the verify request, cost rows and hash. Verdicts are recomputed from the stored verify job on every run (no call), so an answer-only change is re-compared; after any validate rebuild the stored verdicts of every page of the book are re-applied, and pages still needing calls are reported. Verdicts are applied in a `finally`, so a crash or Ctrl-C still records them.
- Verdict precedence: `answer`/`arith` -> `disagree`; else `missing_problem`/`missing_part`/`type_mismatch`/`invalid_output`/`unsure`/`call_failed`/`not_run`/`invalid_doc` -> `unverified`; else `agree`. `code_confirms` and `hint_leak` are informational (a leak still sets `needs_review`). Code arithmetic still runs without a usable second answer. Divisions that do not give a whole number are left to the model.
- Reasons carry an extra `slot_key`. `unsure` is `bool` defaulting to false (not nullable) to keep the schema at 1 union.
- Every other source page of a page's Problems is sent and hashed. Embedded JSON escapes `</`.
- `build pilot` with `--yes-spend` always builds a client when verify is on; `--dry-run` also writes verify requests for already-validated pages not being re-extracted. Story 1.5 tests pass `--no-verify`.

## Spec Change Log

- 2026-09-27 — Trigger: review. Amended (orchestrator decision, non-user-visible): when `builder.arith` computes a result equal to the extracted answer and only the model's second answer differs, the verdict is `agree` with an informational `code_confirms` reason (exact arithmetic outranks a second model answer). Verify output gains optional `unsure: bool` per Part → `unverified`. New config `verify_model` (default = `extraction_model`). KEEP: all matrix rows as written.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Pilot: verify todo computed before validate; client None despite --yes-spend → PilotError after extract spent | high | money spent then failure → patch |
| 2 | Validate rebuild resets verdicts of pages outside the pilot range; nothing restores them | high | verified problems silently hidden → patch (re-apply stored verdicts for every page with rows, no calls) |
| 3 | run_calls raising skips apply_verdicts, leaving stale agree rows | medium | → patch (apply in finally) |
| 4 | Non-terminating (10:3) or remainder division (7:2 quotient) forces false ARITH disagree | medium | → patch (skip code check when ':' gives non-integer / non-terminating) |
| 5 | Code confirms extracted answer but model differs → disagree | medium | exact code beats model → patch (agree + info reason; Change Log) |
| 6 | No abstain: model must guess on unreadable content, recorded as disagree | medium | → patch (optional `unsure` → unverified) |
| 7 | Duplicate / unknown problem_id, part_key or keys in output silently handled | medium | → patch (INVALID_OUTPUT → unverified) |
| 8 | Hint leak: raw string match, only single-value parts, `-3` matches `3`, Unicode minus, dot decimal | medium | → patch (value-based matching incl. `.`/`,`, boundaries; extend to multi-slot numeric, compare symbol words, selected option text) |
| 9 | load_tasks crashes on a row whose doc no longer validates | medium | → patch (skip + unverified + report) |
| 10 | source_pages beyond page+1 never shown to verifier | low | → patch (attach all source pages' images, or flag) |
| 11 | Prompt block delimiters not escaped (`</problems>` in text) | low | → patch |
| 12 | No separate verify model/budget/timeout | medium | independence weakened → patch (`verify_model`, default = extraction_model) |
| 13 | pilot --dry-run prints verify estimate but writes no verify requests | low | → patch (write them for already-validated pages) |
| 14 | Misleading "run pilot first" inside pilot | low | → patch |
| 15 | Verify estimate labelled "at most" uses extract figures | low | → patch (label "estimate") |
| 16 | Tests: 0004→0005 migration with data; unrendered pages not called; negative decimals format; unary +; duplicate outputs; verify Ctrl-C/crash; default-verify pilot path; brittle hard-coded model | medium | → patch |
| 17 | PageRequest.stage only used by fake | low | reject |

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
