---
title: 'Story 5.1: Concept guides generated and editable'
type: 'feature'
created: '2026-09-30'
status: 'done'
baseline_commit: '25a83e2c1b58b23a9e947f3c7e0ff3a14462458a'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Concepts are curated (Story 1.7/1.8) but have no Guide anywhere: no table, no schema, no audio. Page extraction already returns `worked_examples` (theory boxes and "Ví dụ") but they stay unused inside the stored extract job output.

**Approach:** Add a builder stage that, per curated Concept, asks Claude for one Guide (short explanation plus one worked example) from those stored worked examples and a few of the Concept's Problems. Store it in the catalogue, let Anh edit it in Content Review as field overrides with a base hash, expose `effective_concept_guide()`, and include its text in `speak-missing`. A Guide stays hidden from the child until Anh approves it (an `approved_hash`, like Problems); editing an approved Guide needs approving again. The child screen is Story 5.2.

## Boundaries & Constraints

**Always:** Guides are generated per Concept (`concept_id`), never per Lesson. Only `content.catalog.service` writes the generated Guide; only `content.review.service` writes guide overrides (AD-2). Only `effective_concept_guide()` merges them (AD-4). Approval (human decision): a Guide is visible to a child only when its `approved_hash` equals the hash of the current effective Guide (generated text plus overrides); generation, regeneration that changes the text, and every edit therefore make it unapproved until Anh approves again. `effective_concept_guide()` returns the effective Guide with `approved: bool`, and Story 5.2 must show only approved Guides. A Concept with no book material is drafted from up to 3 sample Problems (`source='problems'`) and listed first in review, so every Concept gets a draft. Generation goes through `ClaudeClient` and `builder.calls.run_calls`, so costs land in `build_costs` and the per-run cap applies. It needs `--yes-spend` and honours `--dry-run`, like `pilot`/`verify`. Generation is idempotent by input hash: unchanged input makes no call. Guide text is Vietnamese, NFC, written for the Concept's Grade, at most about 280 characters of explanation and 5 example steps so it fits one tablet screen. Answer-like text in a Guide is fine to speak; no Problem answer key is quoted.

**Never:** No child-facing screen, 📖 button, route or `concept` Session (Story 5.2). No change to Problem overrides, approval or visibility rules. No deletion of a Guide when a Concept is renamed; `concept_id` never changes. No LaTeX beyond the existing inline subset in spoken fields. No automatic regeneration on review edits. No Guide is ever exposed to a child before approval.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Generate | Concept `g1.so-sanh-so` with Problems on pages that have worked examples; `--yes-spend` | One row: explanation, example (question, steps, answer), `source='book'`, `input_hash`, model | N/A |
| No book material | Concept whose pages have no worked examples | Guide drafted from up to 3 sample Problems, `source='problems'`, listed in the run report | N/A |
| Rerun, same input | Same `input_hash` | Skipped, no call | N/A |
| No spend flag | Missing `--yes-spend`, calls needed | Refused with the existing bilingual message, exit 2, nothing sent | Same guard as `_spend_client` |
| Dry run | `--dry-run` | Requests written, no call, no row | N/A |
| Bad output | Claude output fails schema or length caps | Job recorded `failed`; no Guide row; listed in the report; retried next run | Transient retry as in `run_calls` |
| Edit | Anh saves `explanation` for a Concept | Override row with `base_hash` of the generated field; effective Guide shows it | Empty or over-length: 422; unknown Concept: 404 `CONCEPT_NOT_FOUND` |
| Regenerate after edit | Generated `explanation` changed, override `base_hash` differs | Override still wins; Guide flagged `review_conflict` in the Khái niệm tab | N/A |
| Reset | Anh deletes the override | Effective Guide returns to the generated text | N/A |
| Approve | Anh approves an unapproved Guide | `approved_hash` stored; `effective_concept_guide().approved` true | Unknown Concept: 404 |
| Edit after approval | Anh edits an approved Guide | `approved` false until approved again | N/A |
| Not yet approved | Freshly generated Guide | `approved` false; the child-facing read (5.2) must not return it | N/A |
| Audio | New or edited Guide text | `speak-missing` lists and synthesises its keys; old audio orphaned, not deleted | TTS error per key as today |

</frozen-after-approval>

## Code Map

- `backend/hoctap/builder/extraction/models.py` -- `WorkedExample(title, text)` already in `PageExtraction`; source material, stored in `build_jobs.output_json` (stage `extract`, done).
- `backend/hoctap/builder/jobs_store.py` -- `page_ref()`, `find_done()` to read stored extract output per page.
- `backend/hoctap/builder/claude_client.py`, `calls.py`, `costs.py` -- `PageRequest`, `CallJob`, `run_calls`, `record_call`; `FakeClaudeClient(responder)` for tests. `PageRequest.add_dir` is required: use an empty temp dir for this text-only call.
- `backend/hoctap/builder/stages/extract.py` -- template for prompt building, `input_hash` and `_check_output`; new `backend/hoctap/builder/stages/guides.py` follows it (job ref `guide:{concept_id}`, `run_kind='full'` since `build_jobs` allows only `pilot|full`).
- `backend/hoctap/cli.py` -- `_spend_client`, `_SPEND_REFUSED`, `build` subparsers (`speak-missing` at ~L826); add `hoctap build guides`.
- `backend/hoctap/content/catalog/models.py`, `service.py` -- add `content_catalog_concept_guides` (`concept_id` PK, `body_json`, `source`, `input_hash`, `model`, `generated_at`) and an upsert writer.
- `backend/hoctap/content/review/models.py`, `service.py` -- add `content_review_guide_overrides` (unique `concept_id, field`, mirroring `content_review_overrides`) and `content_review_guide_status` (`concept_id` PK, `approved_hash`); `save_guide_overrides`, `delete_guide_override`, `approve_guide`; reuse `_concept()` and `value_hash`.
- `backend/hoctap/content/effective.py` -- add `effective_concept_guide(conn, concept_id)` beside `effective_problem`.
- `backend/hoctap/content/schema.py` -- add a small `ConceptGuideDoc` model (no `problemdoc.schema.json` change).
- `backend/hoctap/content/speech.py`, `builder/stages/speak.py` -- add `guide_speech_refs()`; `collect_refs` includes every effective Guide; resolves the deferred-work item on Guide speech.
- `backend/hoctap/api/review.py`, `content/review/schemas.py` -- `GET/PUT/DELETE /parent/review/concepts/{concept_id}/guide` and `POST .../guide/approve`, behind `require_parent`; `concepts_out` gains `has_guide`, `guide_conflict`, `guide_approved`.
- `backend/hoctap/db/alembic/versions/0018_concept_guides.py` -- new migration, `down_revision = '0017_assignments'` (current head, verified).
- `frontend/src/pages/review/ConceptsTab.tsx` -- per Concept "Hướng dẫn" expander: edit explanation and example, reset, conflict badge; regenerate `api/client.ts` and `schema.d.ts`.
- `backend/tests/test_review.py`, `test_speak.py`, `test_speech.py`, `test_extraction.py` -- existing patterns (fake Claude, fake TTS, review overlay).

## Tasks & Acceptance

**Execution:**
- [x] `backend/hoctap/db/alembic/versions/0018_concept_guides.py` + both `models.py` -- three tables (guides, guide overrides, guide approval status) -- generated vs override data kept separate (AD-4)
- [x] `backend/hoctap/content/schema.py` -- `ConceptGuideDoc` with length caps -- one shared validator for generated and edited text
- [x] `backend/hoctap/builder/stages/guides.py`, `cli.py` -- gather worked examples and sample Problems per Concept, call Claude, validate, upsert; `hoctap build guides [--concept ID] [--dry-run] [--yes-spend]` with a report of generated, skipped, failed and drafted-from-problems -- the generation path
- [x] `backend/hoctap/content/catalog/service.py`, `review/service.py`, `effective.py` -- writer, overrides with `base_hash` and conflict detection, `effective_concept_guide` -- edit survives regeneration
- [x] `backend/hoctap/content/speech.py`, `builder/stages/speak.py` -- Guide speech refs in `collect_refs` -- "has audio"
- [x] `backend/hoctap/api/review.py`, schemas -- guide endpoints and `concepts_out` flags -- editor data
- [x] `frontend/src/pages/review/ConceptsTab.tsx` (+ generated client) -- Guide editor -- "Anh can edit a Guide in Content Review"
- [x] `backend/tests/*`, `frontend/src/pages/review/ConceptsTab.test.tsx` -- cover every matrix row using `FakeClaudeClient` and the fake TTS; no test spawns the CLI

**Acceptance Criteria:**
- Given curated Concepts and a successful run, when `hoctap build guides` finishes, then every Concept has a Guide within the length caps, and `speak-missing --dry-run` lists its audio keys.
- Given an edited Guide, when the Guide is regenerated with different text, then the effective Guide still shows Anh's edit and the conflict is visible in Khái niệm.
- Given a freshly generated Guide, when the child-facing read is used, then it is not returned until Anh approves it, and editing it afterwards hides it again.
- Given the parent routes, when called without the PIN cookie, then they return 401.

## Design Notes

Split point if this proves too large (it spans migration, builder stage, review service, speech and UI): 5.1a = tables, generator, CLI, effective view and speech; 5.1b = review endpoints and the Khái niệm editor. 5.1a is testable alone through the service and CLI.

Example generated body: `{"explanation": "Số nào có nhiều chục hơn thì lớn hơn.", "example": {"question": "So sánh 35 và 28", "steps": ["3 chục lớn hơn 2 chục"], "answer": "35 > 28"}}`

## Verification

**Commands:**
- `cd backend && ruff check . && pytest tests/test_review.py tests/test_speak.py tests/test_speech.py tests/test_extraction.py tests/test_app.py` -- expected: pass
- `cd backend && alembic upgrade head` on a scratch DB -- expected: head is `0018_concept_guides`
- `cd frontend && npx tsc -b && npx eslint . && npx vitest run --pool=vmThreads src/pages/review` -- expected: pass
- Speech-related frontend tests need `--pool=threads` instead of `vmThreads`.

**Manual checks (if no CLI):**
- Run `hoctap build guides --dry-run`, then with `--yes-spend` for one `--concept`; open Khái niệm, edit, rerun, confirm the edit survives.

## Implementation Notes

- (2026-09-30) Migration `0018_concept_guides` adds three tables (generated Guides, guide overrides, guide approval status). `effective_concept_guide()` merges overrides and reports `approved` only when the stored `approved_hash` equals the hash of the merged body, so regeneration or any edit hides the Guide until Anh approves again. Story 5.2 must show a child only `approved` Guides.
- `hoctap build guides [--concept ID] [--dry-run] [--yes-spend] [--max-total-usd]` goes through `run_calls` with the existing spend guard (exit 2 without `--yes-spend`); `CallJob` gained an optional `run_kind` so Guide jobs count as `full`, not toward the pilot gate. Guide speech refs are included for every effective Guide, approved or not.
- Gaps: a Concept with no active Problems gets no Guide (nothing to draft from); approving a Guide also re-bases any override whose generated field changed, clearing its conflict flag; the real Claude CLI was never run, only `FakeClaudeClient`; the failed-TTS-key-per-key matrix row is untested; speech-related frontend tests need `--pool=threads`.

### 2026-09-30: independent re-verification

- `ruff check .` clean. `pytest tests/test_guides.py tests/test_review.py tests/test_app.py tests/test_speak.py tests/test_speech.py tests/test_extraction.py tests/test_parent.py tests/test_sessions.py` — 378 passed (including `test_parent.py::test_guarded_tampered_cookie`, which the implementing agent had seen fail once in a full run).
- Frontend `tsc -b` and `eslint .` clean; `vitest run src/pages/review src/pages/ParentHome.test.tsx --pool=vmThreads` — 43 passed. OpenAPI file and types regenerated and current.
- Not run: `alembic upgrade head` on a scratch DB (the migration runs in every backend test and `test_app.py` checks the head), the wider frontend suite, the real Claude CLI.
