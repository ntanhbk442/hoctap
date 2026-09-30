# Epic 6 Context: All 30 Toán Books, every Problem Type

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

After this epic every Toán Book for grades 1-5, in both Editions (30 Books), is extracted and playable, including the Problem Types that grades 2-5 need. Until now only the grade-1 pilot subset is built and only grade-1 Problem Types exist, so Bin in a higher grade has nothing to practise. The epic adds the grade 3-5 calculation type and its grading rules, then runs the whole corpus through the resumable builder once the pilot gate has passed.

## Stories

- Story 6.1: `expression_input` and the grade 3-5 grading rules
- Story 6.2: Full-corpus run

## Requirements & Constraints

- `expression_input` is the calculation type for grades 3-5. The child enters it on an on-screen keypad (no system keyboard) offering + − × : ( ) and =.
- Grading accepts any expression that evaluates to the correct value, unless the Problem requires a specific form. Numbers match however formatted: `07` = `7`, and for grades 4-5 `3,5` = `3.5`.
- A wrong slot in a multi-slot Part is highlighted; a Part is wrong if any slot is wrong.
- A new Problem Type ships in one change: schema variant, grader, widget and print renderer together.
- The full run happens only after the approved build gate. It reports cost and progress, lists failures, and must leave at least 95% of Problems interactive (not `fallback`) with at least 98% of Answer Keys correct on a random check of 100.
- Answer Keys are verified by a second Claude pass plus code arithmetic; disagreements are flagged for review.
- Child screens are Vietnamese with correct diacritics; every instruction, Part and Solution has a 🔊 button; touch targets are at least 64 px; child copy stays positive.

## Technical Decisions

- One `ProblemDoc` (schema `v1`, Pydantic) is the single contract for extractor, grader, widgets and overrides. Parts are a union discriminated by `type`; every Part has a `part_key` and every Answer Slot a `slot_key`; everything is addressed by (`problem_id`, `part_key`, `slot_key`), never array position.
- The extraction request sends the transformed ProblemDoc schema; the validate stage re-validates every result. Frontend types are generated from OpenAPI, never hand-written.
- `child_view()` is the only projection that reaches the child and strips `answer`, `hint`, `solution`.
- Numbers are canonical decimal-comma strings in stored answers; free-typed child input is parsed more leniently by the grader.
- Speech is content-addressed through one normaliser; answer keys are never read aloud.
- The extraction stages are resumable and cost-metered; spending on Claude always needs an explicit opt-in.

## UX & Interaction Patterns

- Keypads are per type. Grades 1-3 show no comma key; grades 4-5 do. The expression keypad is the number pad plus operator keys, in the same 80 px key size and bottom action bar.

## Cross-Story Dependencies

- Story 6.2 depends on 6.1: extraction of grades 3-5 needs `expression_input` in the schema, extractor prompt and verify pass.
- Story 6.2 depends on the Epic 1 gate (approved `build_gate`) and the resumable stages, verify, publish and speech-missing tooling.
- Epic 7's worksheet printing must cover every Problem Type, including `expression_input`.
