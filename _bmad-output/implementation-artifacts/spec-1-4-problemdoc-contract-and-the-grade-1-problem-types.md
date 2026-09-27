---
title: 'Story 1.4: ProblemDoc contract and the grade-1 Problem Types'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_commit: 'tree:a9496388b40e466d9fa1d90b0424b5ffe52f7919'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The extractor, graders, widgets, print renderer, overrides and Attempts must all agree on one shape for a Problem, and must address its Parts and Answer Slots by stable keys (AD-1). Answers must never leak to the child (AD-5).

**Approach:** Write one Pydantic ProblemDoc v1 model in `hoctap/content/schema.py`. Parts are a union discriminated by `type`, covering the 13 grade-1 types. Every type-specific answer lives only in the Part's `answer`, `hint` and `solution` fields. `content.child_view()` projects a ProblemDoc to a `ChildProblemView` that drops those fields. A fixture per type proves the model, the projection and `anthropic.transform_schema()`.

## Boundaries & Constraints

**Always:**
- Top-level fields:
  - `schema_version: "v1"`, `problem_id`, `book_id`, `unit_key`, `lesson_key`, `problem_label`, `display_label` ("Bài 3")
  - `instruction` (Vietnamese NFC text)
  - `layout: "sequence" | "together"`
  - `source_pages: [{page, bbox}]`
  - `images: [{image_key, page, bbox}]`
  - `concept_ids: []`, `concept_proposals: []`
  - `parts: [Part]` (at least 1)
- A `bbox` is `[x0, y0, x1, y1]`, normalised 0–1 on the page, with x0<x1 and y0<y1.
- Keys (`part_key`, `slot_key`, `option_key`, `item_key`, `node_key`, `region_key`, `image_key`) are unique within their parent and match `^[a-z0-9][a-z0-9_-]{0,15}$`. `part_key` is the book's own label (a, b, c) or `p1`, `p2`… in reading order.
- `problem_id` = `{book_id}.{unit_key}.{lesson_key}.{problem_label}`, and a validator enforces it.
- Every Part has:
  - common fields: `part_key`, `type`, `prompt` (may be empty), `image_keys`;
  - answer-bearing fields: `answer` (typed per type), `hint` (non-empty text), `solution: {steps: [text ≥1], final: text}`.
- Text fields use UTF-8 NFC and allow the inline LaTeX subset (`\overline{}`, `\frac{}{}`, `<`, `>`, `=`, `\times`, `:`). The validator NFC-normalises text.
- Per-type structure (child-visible) → `answer` (hidden):

| type | structure | answer |
|---|---|---|
| `number_input` | `template` with `[[slot_key]]` markers; `slots` | `[{key: slot_key, value: "12"}]`, where `value` is a numeric string |
| `compare` | `rows: [{slot_key, left, right}]` | `{slot_key: "<" \| ">" \| "="}` |
| `multiple_choice` | `options: [{option_key, text?, image_key?}]`, `multi: bool` | `{selected: [option_key]}` |
| `image_select` | `image_key`, `regions: [{region_key, bbox}]`, `multi` | `{selected: [region_key]}` |
| `order` | `items: [{item_key, text}]`, `direction: "asc" \| "desc" \| "custom"` | `{order: [item_key]}` |
| `number_tree` | `nodes: [{node_key, parent_key?, given?}]`, where a node without `given` is a slot | `{node_key: "5"}` |
| `grid_fill` | `rows`, `cols`, `cells: [[{given?}]]`; empty cells are keyed `r{i}c{j}` | `{"r0c1": "3"}` |
| `match` | `left`/`right: [{item_key, text?, image_key?}]` | `{pairs: [[l, r]]}` |
| `count_image` | `image_key`, `slots: [{slot_key, label}]` | `{slot_key: "7"}` |
| `dot_draw` | `boxes: [{slot_key, label}]` | `{slot_key: "4"}` |
| `connect_dots` | `image_key`, `dots: [{n, x, y}]` | `{sequence: [1, 2, …]}` |
| `spot_difference` | `image_left`, `image_right`, `count` | `{regions: [{region_key, bbox}]}`, on the right image |
| `fallback` | `image_key` | `null` (the solution only) |

- Cross-reference validators: every referenced key must exist (images, slots, options, items, nodes); answers must cover exactly the Part's slots, options, items or nodes; `connect_dots.sequence` must be a permutation of the dot numbers.
- `child_view(doc) -> ChildProblemView` drops `answer`, `hint` and `solution` from every Part, and also for `spot_difference` the answer regions (keeping `count`). A test serialises every fixture's child view and asserts that no answer value, hint text or solution text appears in it.
- Dump the JSON Schema to `backend/hoctap/content/problemdoc.schema.json` (with a CLI command `hoctap export-schema`), so later stories and prompts reuse it.

**Never:**
- No database table for Problems yet (Story 1.7). No graders (Story 2.5). No widgets (Stories 2.6/2.7). No `expression_input` (Story 6.1).
- No model call in tests. Extraction prompts come in Story 1.5.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid per type | 1 fixture per type (13) | parses; round-trips JSON losslessly | N/A |
| Unknown type | `type: "essay"` | ValidationError | names the discriminator |
| Answer/slot mismatch | answer key missing or extra | ValidationError | names the part_key |
| Dangling ref | `image_keys` or `image_key` not in `images` | ValidationError | names the key |
| Duplicate key | two parts `a` | ValidationError | N/A |
| Bad bbox | x0 ≥ x1 or a value outside 0–1 | ValidationError | N/A |
| Wrong problem_id | not equal to the composed id | ValidationError | N/A |
| NFD text | decomposed Vietnamese | stored as NFC | N/A |
| Child view | any fixture | no `answer`, `hint`, `solution`, or answer values anywhere | N/A |
| Extraction schema | `anthropic.transform_schema(ProblemDoc)` | returns a schema without error; its optional-field and union counts are recorded in Implementation Notes | if the SDK's limits are exceeded, record it and HALT |

</frozen-after-approval>

## Code Map

- `backend/hoctap/content/` -- `catalog/` exists (Story 1.3). Add `schema.py` (the models) and `views.py` (`child_view`), and export both from `hoctap/content/__init__.py`.
- `backend/hoctap/cli.py` -- add `export-schema`, following the existing `export-openapi` pattern.
- `backend/tests/fixtures/problemdocs/` -- new, one JSON file per type, in realistic Vietnamese grade-1 content (for example, a `number_tree` with 5 = 2 + [[?]]).
- `anthropic>=1.8,<2` is already a dependency. Confirm `transform_schema` exists in the installed SDK before using it. If it doesn't, write the finding into Implementation Notes and HALT.

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/content/schema.py` -- the ProblemDoc v1 models, the per-type Part variants and the validators above.
- [x] `backend/hoctap/content/views.py` -- `ChildProblemView` and `child_view()`.
- [x] `backend/tests/fixtures/problemdocs/*.json` -- 13 realistic fixtures.
- [x] `backend/tests/test_problemdoc.py` -- one test per matrix row, and one per type for round-tripping and leak-proof child view.
- [x] `backend/hoctap/cli.py export-schema` + committed `problemdoc.schema.json`.

**Acceptance Criteria:**
- Given the 13 fixtures, when the tests run, then each parses, round-trips, and its child view contains no answer, hint or solution content.

## Implementation Notes

- **SDK check:** `anthropic` 1.8.0 is installed and exports `transform_schema(json_schema: type[BaseModel] | dict)`. `transform_schema(ProblemDoc)` returns without error.
- **Counts** (on the transformed schema, each `$def` counted once; asserted in `test_transform_schema_accepts_problemdoc`):
  - optional fields: **9** — `ChoiceOption.text`, `ChoiceOption.image_key`, `MatchItem.text`, `MatchItem.image_key`, `TreeNode.parent_key`, `TreeNode.given`, `GridCell.given`, `FallbackPart.answer` and `DotBox.given` (added in review).
  - unions (`anyOf`): **8** — the 7 nullable fields above, plus the 13-way Part union.
  - Both are under the documented structured-output limits as I understand them (24 optional, 16 union parameters). No HALT.
- **Design choices:**
  - Every field the table marks without `?` is required, and has no default: `prompt` (may be `""`), `image_keys`, `images`, `concept_ids` and `concept_proposals`. This keeps the optional count low.
  - Each type has a child-visible `*View` class (common fields, structure and structural validators) and a `*Part` class (`AnswerBearing` + the view + a typed `answer`, with answer-coverage validators). `child_view()` dumps the doc, pops `answer`/`hint`/`solution`, and validates the result as `ChildProblemView`, whose Parts are the `*View` union.
  - `concept_proposals` is a list of proposed Concept names (non-blank text). `concept_ids` must match `CONCEPT_ID_PATTERN` = `^g[1-5]\.[a-z0-9][a-z0-9-]{0,47}$`. Neither list may contain duplicates. Both lists may be empty while tags are pending. Nothing enforces 1–3 tags yet.
  - Keys are also enforced on `unit_key`, `lesson_key` and `problem_label`, so `problem_id` can never contain extra dots.
  - `match` requires every left item exactly once. Right items may repeat or go unused, because several expressions can share one result. `multiple_choice` needs at least 2 options, `order` at least 2 items, `number_tree` at least 2 nodes and at least one slot, and `grid_fill` at least one empty cell. `number_input` markers must match its `slots` exactly once each. Numeric strings are canonical: `^-?(0|[1-9][0-9]*)(,[0-9]+)?$` (decimal comma, because "." groups thousands in Vietnamese), and `-0` is not allowed. `count_image` and `dot_draw` values are non-negative integers, `^(0|[1-9][0-9]*)$` (`CountEntry`).
  - One-value Literals (`type`, `schema_version`) are emitted as `enum`, not `const`, because `transform_schema` moves `const` into the description and would otherwise lose the discriminator. `bbox` and match pairs are fixed-length lists, not tuples, because `prefixItems` would likewise be dropped. The JSON shape is unchanged.
- **Keyed answers (resolved, see Spec Change Log):** `number_input`, `compare`, `number_tree`, `grid_fill`, `count_image` and `dot_draw` answers were free-keyed dicts, which `transform_schema` reduces to an object that allows no properties. Their answers are now lists of `{key, value}` entries: `NumericEntry` (a numeric string) and `CompareEntry` (`<`, `>` or `=`), both with `extra="forbid"`. Keys must be unique, and the set of keys must equal exactly the Part's slot_keys, empty node_keys or empty cells `r{i}c{j}`. `answer_map(part) -> dict[str, str]` gives graders the mapping. `test_transform_schema_keeps_every_answer_shape` fails if any Part's `answer` collapses to an empty object or an array without items. After the change, the counts were still 8 optional fields and 8 unions (now 9 optional after `DotBox.given`).
- **Review rules (added):**
  - `dot_draw` boxes are `DotBox {slot_key, label (non-empty), given: int = 0 (≥ 0)}`. The answer value is the total number of dots, and it must be ≥ `given`.
  - `connect_dots`: the dot numbers `n` are exactly 1..N, and the answer sequence is exactly 1..N in order. `StrictInt` is used, so booleans are rejected.
  - `number_tree` has exactly one root.
  - `order`: when `direction` is asc/desc and every item text is a canonical number, the answer order must be sorted that way.
  - An `ImageRef.page` must be one of the `source_pages`.
  - A Part's `image_keys` must be unique.
  - `concept_proposals` must be unique.
  - `spot_difference` `image_left` and `image_right` must differ.
  - Field descriptions state the coordinate frame: page-normalised for `source_pages`/`images` bboxes, image-normalised for `Region.bbox` and `Dot.x`/`y`. They also say that `r{i}c{j}` is 0-based and what `layout` sequence/together means.
- `hoctap export-schema [--out]` writes `ProblemDoc.model_json_schema()` (the Pydantic schema, not the transformed one) to `backend/hoctap/content/problemdoc.schema.json`. A test fails if the committed copy drifts from the model.

## Spec Change Log

- 2026-09-26 — Trigger: review found dot_draw cannot express 'draw more' problems and numeric answers were ambiguous. Amended (non-user-visible, orchestrator decision): dot_draw boxes gain optional `given` (pre-printed dots, default 0) with answer = total; numeric values use canonical Vietnamese form (decimal comma, no leading zeros); count answers are non-negative integers. KEEP: list-shaped keyed answers and all prior validators.

- 2026-09-26 — Trigger: implementation found `anthropic.transform_schema` turns free-keyed dict answers (`number_input`, `compare`, `number_tree`, `grid_fill`, `count_image`, `dot_draw`) into objects with no allowed properties, so strict structured output can only emit `{}`. Amended: those answers become lists `[{key, value}]` (key = slot_key / node_key / cell key) — a non-user-visible technical correction to the frozen answer table, decided by the orchestrator under the user's /loop autonomy to keep ONE contract for extraction and runtime (AD-1) instead of a parallel extraction shape. Known-bad state avoided: extraction silently producing empty answers. KEEP: every other model, validator, fixture, child_view and the enum-for-const/list-for-tuple schema adjustments.

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Committed schema JSON missing from diff | false | file exists; excluded from review diff on purpose |
| 2 | export-schema default path inside package | low | app runs from source checkout → reject |
| 3 | Leak-test sub-checks can never fail; spot check reads parts[0] | medium | false assurance on the key safety test → patch |
| 4 | dot_draw cannot express "draw more" (pre-printed dots) | medium | fixture instruction contradicts model → patch: optional `given` count per box, answer = total |
| 5 | dot_draw label equals answer in child view (claimed leak) | false | the label IS the task ("draw 4 dots"); not hidden info |
| 6 | Validators untested (tree with no slot, grid no empty cell, duplicate marker, match dup/unknown right, cycle, rows×cols, option without content, concept_ids, duplicate dot n / slot / item / region, image_select multi=false with 2) | medium | pre-verified gaps → patch |
| 7 | BBox frame (page vs image) undocumented for Region/Dot; grid keys 0-based undocumented; `layout` undocumented | medium | extractor ambiguity → patch (field descriptions) |
| 8 | Numeric values accept `.`/`,`, leading zeros, `-0` | medium | Vietnamese `.` = thousands; string graders diverge → patch (canonical form `-?(0|[1-9]\d*)(,\d+)?`) |
| 9 | count_image/dot_draw accept negative/decimal | medium | → patch (non-negative int) |
| 10 | connect_dots numbering not 1..n; sequence any permutation | low | → patch (contiguous 1..n, ascending answer) |
| 11 | number_tree allows forests/no root | medium | widget can't draw → patch (exactly one root) |
| 12 | order answer may contradict asc/desc for numeric items | medium | correct children marked wrong → patch |
| 13 | ImageRef.page not in source_pages; duplicate part image_keys / concept_proposals; image_left == image_right; bool coerced into dot ints; empty dot_draw label | low | trivial guards → patch |
| 14 | Magic (8,8) count assertion unexplained | low | → patch (comment) |
| 15 | Mutation tests mostly on parts[0]; fixtures reuse page 12 bbox; answer_map typed Any | low | reject |
| 16 | concept id pattern differs from Implementation Notes | low | → patch notes to match code |

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- `cd backend && uv run hoctap export-schema` -- expected: writes `hoctap/content/problemdoc.schema.json`
