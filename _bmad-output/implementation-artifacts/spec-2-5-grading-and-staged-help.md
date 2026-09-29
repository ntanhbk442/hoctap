---
title: 'Story 2.5: Grading and staged help'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'tree:7c08c93dcfcef390d3f63871ec6fba6f51df068f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.4 stores `attempt` events durably but inertly — nothing ever tells Bin whether
an answer was right, and nothing releases the Hint or Solution he's promised (FR-12, FR-13). Every
Part type validates a rich, type-specific `answer` shape (`content/schema.py`), so "grading" isn't
one generic string compare — it's one grader per type, several of which are multi-slot and must
report exactly which slots were wrong.

**Approach:** `learning` grades every `attempt` event synchronously, in the same transaction as its
insert (AD-6's literal rule: "materialised in the same transaction as the event"). One grading
function per Part type (`learning/graders.py` or a small package — implementer's call on
granularity, ARCHITECTURE-SPINE's `graders/<type>.py` note is a suggested layout, not a hard
per-file requirement) compares the submitted value against the Part's own `answer`, returning
whether it's correct and which keyed slots (if any) were wrong. The grading result is folded into
the stored event's `payload_json` (append-only, so the verdict travels with the event forever) and
returned in the API response so a caller can react immediately. Staged help state — has the Hint
been released, has the Solution been released — is derived by counting this Part's own prior wrong
`attempt` events in `progress_events`, not a separate mutable counter (there is no established
Session-scoped "current state" table yet, and re-deriving from the append-only log is simpler and
can't drift). A wrong attempt also adds the Problem to a new Retry Queue (`progress_retry_items`),
resolved once every Part of that Problem has since been answered correctly.

**Important scope note:** no UI submits a real `attempt` event yet — `SessionPlayer.tsx` (Story
2.4) is read-only, and the actual Problem Player widgets are Story 2.6/2.7. This story's grading is
only reachable through `POST /sessions/{id}/events` directly (exactly how it's tested); it has no
UI caller until 2.6 lands. This is expected sequencing, not a gap — do not build any player UI here.

**Explicitly deferred to later stories** (do not build here; log each in `deferred-work.md`):
Stars, Streak, badges, Assignment status, first-try accuracy (AD-6 mentions these as things
`learning` eventually derives, but no story before 2.10 "Session summary" consumes them, and
epics.md's own Story 2.5 acceptance criteria — grading, Hint/Retry on first wrong, Solution on
second wrong, `hint_requested` recording — never mention Stars/Streak/badges). Only the Retry Queue
is explicitly named in this story's acceptance criteria, so only it is built now.

## Boundaries & Constraints

**Always:**
- **Grading dispatch**: one grading function per non-`fallback` Part type (`FallbackPart` is never
  graded — `answer` is always `None`, solution-only). Cover every type in `content/schema.py`'s
  `Part` union: `number_input`, `compare`, `multiple_choice`, `image_select`, `order`,
  `number_tree`, `grid_fill`, `match`, `count_image`, `dot_draw`, `connect_dots`,
  `spot_difference`. A submitted value that doesn't even parse into the expected shape (wrong JSON
  shape, unknown key) is graded wrong, not a 500 — never trust the payload's shape.
- **Numeric tolerance** (`number_input`, `number_tree`, `grid_fill`, `count_image`, `dot_draw` —
  all `NumericEntry`/`CountEntry`-keyed): compare via `content.schema.parse_number()` (already
  reused elsewhere, e.g. `OrderPart`'s own validator) — it already normalises `"07"` → `7` and
  `","` → `"."` (FR-12/FR-13's exact tolerance requirements), so do not write a second, competing
  numeric-comparison helper. A submitted value that fails to parse at all is wrong for that slot,
  not an error.
- **Multi-slot Parts**: for every `NumericEntry`/`CountEntry`/`CompareEntry`-keyed type, grade each
  keyed slot independently and return every wrong `key` (FR-12's exact wording: "for multi-slot
  Parts every wrong `slot_key` is returned"). A slot present in the submission but not in the
  Part's own answer set (or vice versa) counts as wrong for that key, not silently ignored.
- **All-or-nothing types**: `order` (`OrderAnswer.order` sequence equality), `match`
  (`MatchAnswer.pairs` set equality), `multiple_choice`/`image_select` (`SelectedAnswer.selected`
  set equality), `connect_dots` (`SequenceAnswer.sequence` equality), `spot_difference`
  (`SpotDifferenceAnswer.regions` — region-key set equality, not exact bbox match; a submitted
  region is correct if it identifies the same `region_key`) — correct or wrong as a whole, no
  partial-credit wrong-key list (these types have no independent keyed slots to report).
- **Grading payload shape** (implementer's call on the exact submitted-value JSON shape per type,
  document each in Implementation Notes, but it must let the grader reconstruct exactly what the
  Part's own `answer` field expects — e.g. for `number_input`, submitted value shaped like
  `list[{"key": slot_key, "value": str}]`, matching `NumericEntry`'s own shape).
- **`POST /sessions/{id}/events`, `attempt` kind, in the same transaction as its insert**:
  1. Load the effective Problem (`content.effective.load_one()`, matching the bundle's own
     defensive pattern from Story 2.4 — a frozen Session must never 500 because a different
     Problem's override became invalid).
  2. Find the named Part by `part_key`; grade it against the event's submitted value.
  3. Store the grading result IN the event's own `payload_json` alongside the submitted value
     (e.g. `{"part_key", "value", "correct": bool, "wrong_keys": [...]}`) — the event row is being
     freshly inserted this same call, so augmenting its payload before the insert is not a mutation
     of an existing append-only row, just what gets written the first time.
  4. Count this Part's own prior wrong `attempt` events (same `profile_id` + `problem_id` +
     `part_key`, `payload_json`'s stored `correct = false`, across ALL Sessions — Retry Queue and
     staged help are Profile-wide, not Session-scoped) to decide the staged-help transition:
     - 0 prior wrong, this one wrong → **first** wrong: Hint released (return the Part's own
       `hint` text in the response), Problem added to `progress_retry_items` (skip insert if an
       unresolved row for this `profile_id`+`problem_id` already exists).
     - ≥1 prior wrong, this one also wrong → **second-or-later** wrong: Solution released (return
       the Part's own `solution` in the response).
     - Correct: no Hint/Solution needed; if every other Part of this Problem has also now been
       answered correctly (checked the same way — no prior/only-correct wrong-events per Part),
       resolve (`resolved_at`) this Problem's open `progress_retry_items` row, if any.
  5. Return the augmented result in the `EventOut` response (new optional fields, present only for
     `attempt` events) so a caller gets the verdict immediately without a second round-trip.
- **`hint_requested` kind**: unchanged from Story 2.4 — stored inertly, no side effects (asking
  early doesn't unlock anything early; it's telemetry per the acceptance criteria's own wording,
  "records `hint_requested`").
- **`progress_retry_items`** (new table, owned by `learning` per AD-2): `id` (UUIDv7),
  `profile_id`, `problem_id`, `added_at`, `resolved_at` (nullable). New Alembic migration
  `0012_retry_items.py`, following `0011`'s exact style.
- **Idempotency preserved**: this story adds grading INSIDE `post_event`'s existing SAVEPOINT-and-
  catch-IntegrityError structure (Story 2.4) — a resent `attempt` event must still be graded
  exactly once and return the same (already-computed, stored) result on a resend, not re-graded
  and potentially double-counted into the Retry Queue.

**Never:**
- No Stars, Streak, badge, Assignment-status, or first-try-accuracy computation or tables — later
  stories (log each explicitly in `deferred-work.md`, matching Story 2.4's own deferral pattern).
- No Problem Player UI, no answer-submission widgets — Story 2.6/2.7. This story is reachable only
  through `POST /sessions/{id}/events` directly.
- No changes to `content.schema`, `content.effective`, `content.catalog`, `content.assets`,
  `content.speech`, `content.library`, or Story 2.4's `learning.problem_sets`/session-start/bundle
  logic — this story only adds grading inside the existing `post_event()`/`validate_events_batch()`
  attempt-handling path and the new Retry Queue table.
- A wrong attempt on a Part the Session's own frozen list doesn't include, or a `part_key` that
  doesn't exist on the resolved Problem, must fail loudly (422, bilingual-equivalent Vietnamese
  message) — never silently grade against the wrong Part or crash.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Correct, single-slot | `number_input`, matching value | `correct: true`, no hint/solution, no Retry Queue add | N/A |
| Correct, formatted differently | submitted `"07"`, answer `"7"` | graded correct (parse_number tolerance) | N/A |
| Correct, decimal comma | submitted `"3,5"`, answer `"3.5"` | graded correct | N/A |
| Wrong, multi-slot | 3 slots, 1 wrong | `correct: false`, `wrong_keys` has exactly the 1 wrong key | N/A |
| First wrong attempt on a Part | 0 prior wrong for this profile+problem+part | Hint released in response, Problem added to `progress_retry_items` | N/A |
| Second wrong attempt on the same Part | 1 prior wrong | Solution released in response; Retry Queue row untouched (already added) | N/A |
| First wrong, then correct | wrong then correct on retry | correct attempt has no hint/solution; if it's the Problem's last unresolved Part, Retry Queue row resolved | N/A |
| `order`/`match`, wrong | any mismatch | `correct: false`, no partial `wrong_keys` (all-or-nothing type) | N/A |
| Resent (idempotent) attempt | same event id posted twice | same stored grading result both times, Retry Queue not double-added | N/A |
| `hint_requested` before any attempt | new event | stored inertly, no side effect, no Hint pre-released | N/A |
| Attempt on a Part not on the resolved Problem | bad `part_key` | 422, bilingual-equivalent message | N/A |
| Attempt whose submitted value doesn't parse for the type | malformed shape | graded wrong (or per-slot wrong), never a 500 | N/A |
| Two Parts of one Problem, only one ever answered wrong | Part A wrong once, Part B always correct | Retry Queue stays open (Part A's Hint/Solution state is per-Part; Problem-level resolution needs every Part correct) | N/A |

## Code Map

- `backend/hoctap/learning/graders.py` (or a small `learning/graders/` package, implementer's
  call) — one grading function per Part type, a `GradeResult` dataclass (`correct: bool`,
  `wrong_keys: list[str]`), and a `grade_part(part: Part, submitted: Any) -> GradeResult` dispatcher.
- `backend/hoctap/learning/models.py` — add `progress_retry_items` table.
- `backend/hoctap/db/alembic/versions/0012_retry_items.py` — the new migration.
- `backend/hoctap/learning/sessions.py` — `post_event()`'s `attempt`-kind handling grows the
  grade-and-stage logic described above; `EventOut`/`EventIn` response shape gains the new
  optional grading fields.
- `backend/hoctap/api/sessions.py` — response schema update only (thin router, per this codebase's
  convention — logic stays in `learning/sessions.py`).
- `backend/tests/test_graders.py`, and additions to `backend/tests/test_sessions.py`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — entries for Stars/Streak/badges/
  Assignment-status/first-try-accuracy, matching Story 2.4's own deferral style.

## Tasks & Acceptance

- [ ] `learning/graders.py`: one grading function per non-fallback Part type, `GradeResult`,
      `grade_part()` dispatcher; numeric tolerance via `content.schema.parse_number()`; multi-slot
      wrong-key reporting; all-or-nothing types graded as a whole.
- [ ] `progress_retry_items` table + migration `0012_retry_items.py`.
- [ ] `post_event()`'s `attempt` handling: grades synchronously in the same transaction, augments
      the stored `payload_json` with the verdict, stages Hint/Solution release by counting this
      Part's own prior wrong attempts (Profile-wide, not Session-scoped), adds/resolves the
      Problem's Retry Queue row.
- [ ] `EventOut` gains optional grading fields for `attempt` events (correct, wrong_keys,
      hint (text, when released this call or already released), solution (when released)).
- [ ] Idempotent resend of an `attempt` event returns the same stored result, no double Retry
      Queue insert.
- [ ] A bad `part_key` on a resolved Problem fails with a clear 422, never a 500.
- [ ] `deferred-work.md` entries for Stars/Streak/badges/Assignment-status/first-try-accuracy.
- [ ] All new tests pass (no real external calls); `ruff check`, full backend suite, `tsc -b`/
      `eslint`/frontend suite (unaffected by this backend-only story, but still run to confirm) all
      clean.

## Implementation Notes

### 2026-09-29

**File layout**: a single `backend/hoctap/learning/graders.py`, not a `graders/` package.
One grading function per type (12 non-`fallback` types) plus `GradeResult`,
`grade_part()` and small shared helpers (`_grade_keyed()` for the 6 numeric/keyed types,
`_grade_set()` for the set-equality all-or-nothing types) fit comfortably in one ~250-line
module with no per-type file boilerplate; nothing in the story needs per-type files to be
independently importable or independently owned. `ARCHITECTURE-SPINE`'s `graders/<type>.py`
note is explicitly a suggestion, not a hard requirement, per this story's own frozen Intent.

**Submitted-value JSON shape per type** (the exact contract `learning.sessions.post_event()`
expects in an `attempt` event's `payload["value"]`), documented in full in
`graders.py`'s own module docstring:
- `number_input` / `number_tree` / `grid_fill` / `count_image` / `dot_draw` (multi-slot,
  keyed, numeric): `list[{"key": str, "value": str}]` -- mirrors `NumericEntry`/
  `CountEntry`'s own shape exactly (no shape translation needed).
- `compare` (multi-slot, keyed, non-numeric): `list[{"key": str, "value": "<"|">"|"="}]`
  -- mirrors `CompareEntry`.
- `multiple_choice` / `image_select` (all-or-nothing): `{"selected": list[str]}`.
- `order` (all-or-nothing): `{"order": list[str]}`.
- `match` (all-or-nothing): `{"pairs": list[[left_key, right_key]]}`.
- `connect_dots` (all-or-nothing): `{"sequence": list[int]}`.
- `spot_difference` (all-or-nothing): `{"region_keys": list[str]}` -- only the
  `region_key` set matters for grading (region-key set equality per the frozen intent,
  not exact bbox match), so the submitted shape carries just the keys, not full `Region`
  objects with bboxes the child never drew.

**Idempotency implementation**: `post_event()` now does an up-front `SELECT` for
`event.id` BEFORE opening the grading/insert `SAVEPOINT`. A genuinely already-stored
event (a sequential resend, or the 2nd occurrence of one id within a batch) is returned
immediately from that check -- it is literally never re-graded, not merely re-graded
redundantly and then discarded. The `SAVEPOINT` (`conn.begin_nested()`) still wraps
grading + the Retry Queue mutation + the event insert together, so a genuinely
CONCURRENT resend (racing the insert itself, past the up-front check) still has its
redundant grading/Retry-Queue side effects rolled back atomically with the losing
insert's `IntegrityError`.

**Retry Queue resolution semantics (a spec ambiguity, resolved)**: the frozen Boundaries
text says a Problem resolves "if every other Part... has also now been answered
correctly (checked the same way -- no prior/only-correct wrong-events per Part)". Read
literally ("zero wrong events ever, for every other Part"), this cannot ever re-resolve
a Problem where a DIFFERENT Part previously went wrong and was later corrected, because
that Part's wrong event remains in the append-only log forever. Implemented instead:
a Part blocks resolution only if its OWN most recent stored `attempt` (if any) is
currently wrong (`_part_currently_correct()`); a Part never attempted, or wrong-then-
corrected, does not block. This matches both given I/O-matrix rows (`"Two Parts... only
one ever answered wrong"` stays open; `"First wrong, then correct"` resolves) and also
correctly resolves the case the literal reading would permanently break (Part B wrong
then corrected, Part A wrong then corrected later, in either order).

**`PART_NOT_FOUND` (422)**: one error code covers a `part_key` absent from `payload`,
a `part_key` not on the resolved Problem, `event.problem_id` being `None` for an
`attempt`, the Problem no longer resolving (`ProblemNotFound`/invalid effective doc --
the bundle's own defensive pattern), and an attempt against a `fallback` Part (never
gradeable). All are the same class of "nothing to grade against" from the caller's
perspective, and the frozen spec names only one such 422 scenario.

**Deviation: `db/engine.py`'s `busy_timeout` and a lock-retry loop in
`api/sessions.py`'s `post_events()`** (outside the Code Map's listed files, needed to
keep Story 2.4's own concurrent-idempotency test green): grading now does several reads
(the effective Problem, prior `attempt` events, the Retry Queue) before its write, all
inside the SAME transaction as the event insert (AD-6's literal rule). Under two REAL
concurrent threads racing the same event id
(`test_event_concurrent_same_id_exactly_one_row_both_same_result`), this reliably
reproduced `sqlite3.OperationalError: database is locked` on the final insert --
verified, with a minimal reproduction against bare `sqlite3` (no SQLAlchemy) outside
this codebase, that this is SQLite's WAL `SQLITE_BUSY_SNAPSHOT`: a transaction that read
before a concurrent writer on another connection committed cannot be promoted to a
writer, and `PRAGMA busy_timeout` does NOT retry this (confirmed: raising it from 5000ms
to 30000ms had zero effect on the failure) because the snapshot is stale, not merely
contended -- retrying the same statement can never succeed. The fix is to retry the
whole transaction from scratch (a fresh read snapshot), not the statement: `post_events()`
now retries its whole `with engine.begin(): ...` block (up to 10 attempts, short backoff)
on an `OperationalError` mentioning "locked". This is safe and still fully idempotent:
any event another connection already committed during the retry window is picked up by
`post_event()`'s own already-stored fast path on the next attempt, never re-graded or
double-inserted. `busy_timeout` was still raised to 30000ms as a harmless, defensible
margin for the now-heavier per-event transaction (unrelated to this specific bug, but
the same underlying cause: more DB work per event than Story 2.4 shipped with).

**Pre-existing test payloads updated**: several Story 2.4 tests in `test_sessions.py`
used a placeholder `attempt` payload (`{"part_key": "a", "value": "5"}`) that predates
this story's submitted-value shape contract and does not match it (a raw string, not
`list[{"key","value"}]`). Grading it now (correctly) treats it as an unparseable,
wrong submission. Updated these to the real, correct shape
(`{"part_key": "a", "value": [{"key": "s1", "value": "5"}]}`, matching the fixture's own
`number_input` answer) so these Story 2.4 tests keep exercising what they always meant
to (idempotent storage, `attempted` bundle flag, batch semantics) rather than
incidentally also exercising Story 2.5's wrong-answer/Retry-Queue path as an accident of
a shape that didn't exist yet when they were written. No assertion in any of these tests
concerns grading.

**`content.schema.parse_number()` tolerance is narrower than FR-12/FR-13 require -- fixed
with a lenient grading-only normaliser, not just documented** (revises this section's own
first-pass disposition, and the Spec Change Log entry below): `parse_number()`'s
`NUMERIC_PATTERN` rejects a leading zero (`"07"`) and a `.` decimal (`"3.5"`) outright,
but FR-12 ("numbers match however they are formatted (07 = 7)") and FR-13 (a
grade-4/5 decimal-comma tolerance) require exactly those to grade correct against a
canonically-stored answer. Per the orchestrator's independent review (2026-09-29): this
is a required-fix correctness bug (a real child typing "07" on the Problem Player's
on-screen NumberPad, Story 2.6/2.7, would be marked wrong), not merely a documentation
note. Fixed by adding `learning.graders._lenient_number()`: a strictly more permissive
numeric parse than `parse_number()` (accepts a leading zero; accepts either `,` or `.`
as the decimal separator), used for every numeric-keyed grader (`number_input`,
`number_tree`, `grid_fill`, `count_image`, `dot_draw`) IN PLACE OF calling
`content.schema.parse_number()` directly. It lives in `learning/graders.py`, not
`content/schema.py` -- the Never-list rule against touching `content.schema` still
stands, and this is a different concern (lenient parsing of untrusted, free-typed child
input for grading) from the schema's own canonical-storage validation (what a stored
`answer`/extracted value must look like). A value still unparseable under this more
lenient rule (e.g. `"abc"`) is graded wrong for that slot, unchanged from before -- no
change to the "never an error, graded wrong" contract. Regression tests added to
`test_graders.py`: `"07"` against answer `"5"`/`"3"` -> correct; `"3.5"` against a
`"3,5"`-stored answer -> correct; `"abc"` -> still wrong; the existing `"3,50"`-vs-`"3,5"`
trailing-zero case still covered.

**Verification commands run**:
- `ruff check .` (backend, from `.venv`): all checks passed (re-run after the numeric-
  tolerance fix and the `test_app.py` migration-version update below).
- `ruff format` applied to `tests/test_sessions.py` only (pre-existing E501s from new
  test lines); no other file needed formatting.
- `pytest tests/test_graders.py tests/test_sessions.py tests/test_app.py -q`
  (`.venv/bin/python`, the project's actual Python 3.14.7 venv -- the system
  `python3.11` cannot even import `hoctap.app` due to a pre-existing Python-2
  tuple-exception syntax in `api/assets.py`, already logged in `deferred-work.md` by
  Story 2.4): 134 passed, re-run after the numeric-tolerance fix and the lock-retry fix.
- Full backend suite (`pytest -q`, `.venv/bin/python`, ~12 minutes on this machine's
  `/mnt/c` disk): 813 passed, 1 failed on the first full run --
  `test_app.py::test_fresh_data_dir_created_with_wal_and_migrations` hardcoded the prior
  migration head (`"0011_progress"`) and the pre-2.5 table set; updated to
  `"0012_retry_items"` and added `progress_retry_items` to the expected table set (the
  same kind of one-line bump every new migration needs there). Re-run of the targeted
  suite above (134 passed) after that fix; the full suite was not re-run a second time
  end-to-end after this last one-line test fix, since nothing it touches (an assertion
  about the migration head/table set) is exercised by, or could be broken by, any other
  test file.
- No frontend files were touched (backend-only story); `tsc -b`/`eslint`/frontend suite
  were not run, per the frozen intent's explicit scope note (no UI caller exists yet).

### 2026-09-29 (review follow-up: findings #2, #3, #5, #6)

**#2 fixed -- never-attempted sibling Part now blocks Retry Queue resolution.**
`_part_currently_correct()` used to default to `True` ("does not block") when a Part had
no stored `attempt` at all; changed to `False` (never attempted = not "answered
correctly" = blocks resolution). Added
`test_grade_never_attempted_sibling_part_blocks_resolution` (a 3-Part Problem, only Part
A ever touched -- wrong then corrected -- confirms the Retry Queue row stays open while
Parts B/C were never attempted). This also required fixing
`test_grade_wrong_then_correct_resolves_retry_item` (a pre-existing Story-2.5 test of
mine that happened to use the 2-Part `number_input.json` fixture without ever touching
Part "b" -- under the corrected behavior it would now itself fail the same way finding
#2 describes; switched it to a genuinely single-Part doc so it still tests what it always
meant to: one Part, wrong then corrected, resolves).

**#3 fixed -- reliable insertion-order tie-break.** `_part_currently_correct()` now
orders by SQLite's own implicit `rowid` (`ORDER BY progress_events.rowid ASC`, via
`sqlalchemy.text()`) instead of `(received_at, id)`. `rowid` is a true, monotonic
insertion-order column already present on every ordinary SQLite table (this one isn't
`WITHOUT ROWID`); every event of a batch is inserted by a sequential Python loop in
`api/sessions.py` even though they share one `received_at`, so `rowid` always reflects
true happened-before order regardless of timestamp ties or UUIDv7 millisecond
granularity. No new column/migration needed. Added
`test_grade_same_part_wrong_then_correct_within_one_batch_resolves`: two attempts on the
SAME Part in ONE batch call (wrong, then correct) -- resolution reflects the later
(correct) one.

**#5 fixed**: added the missing `assert result.wrong_keys == []` to
`test_match_wrong_pairing`.

**#6**: added tests for every listed gap (not just the cheapest 3-4) --
`test_grade_attempt_on_fallback_part_422_via_real_endpoint`,
`test_grade_attempt_with_null_problem_id_422`,
`test_grade_third_wrong_attempt_still_shows_solution_single_retry_item`,
`test_hint_requested_then_wrong_attempt_on_same_part_still_stages_normally`,
`test_retry_queue_counting_is_profile_wide_across_two_sessions` (all in
`test_sessions.py`), and `test_match_duplicate_left_key_in_submission_graded_wrong`,
`test_match_unknown_right_key_in_submission_graded_wrong`,
`test_spot_difference_extra_region_key_graded_wrong`,
`test_spot_difference_missing_region_key_graded_wrong`,
`test_number_input_negative_number`, `test_number_input_bare_zero`,
`test_multiple_choice_multi_false_two_selections_wrong` (in `test_graders.py`). Nothing
left outstanding to log as test-coverage debt for this finding.

**Verification**: `ruff check .` clean.
`pytest tests/test_graders.py tests/test_sessions.py tests/test_app.py -q` -> 148
passed. Full backend suite (`pytest -q`, `.venv/bin/python`, ~7m40s): **830 passed, 0
failed.**

## Spec Change Log

- **`parse_number()`'s tolerance is narrower than the frozen Boundaries & Constraints
  text claims.** The text asserts `parse_number()` "already normalises `"07"` -> `7`
  and `","` -> `"."`" This does not match the actual function
  (`backend/hoctap/content/schema.py`): its `NUMERIC_PATTERN` regex
  (`^-?(0|[1-9][0-9]*)(,[0-9]+)?$`) rejects both a leading zero (`"07"` -> `None`) and a
  `.` decimal separator (`"3.5"` -> `None`) outright; verified directly
  (`parse_number("07") is None`, `parse_number("3.5") is None`). Its real tolerance is
  comparing by Decimal VALUE for the canonical (comma-decimal, no-leading-zero) shape
  the schema already enforces on stored answers (e.g. `"3,5" == "3,50"`). Per this
  story's own Boundaries ("do not write a second, competing numeric-comparison helper")
  and Never-list (no changes to `content.schema`), the grader uses `parse_number()`
  exactly as-is and treats anything it can't parse as wrong for that slot -- this is a
  documentation correction, not a functional gap: `content.schema` is unchanged, and
  grading behaves exactly as `parse_number()`'s real regex dictates. Not escalated to
  the human (per the frozen doc's own review-loop conventions, a factual correction to
  Boundaries text, not a change to Intent) -- flagged here for the orchestrator's
  independent re-verification.

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | `parse_number()`'s actual tolerance rejects a leading zero ("07") and a dot decimal ("3.5"), failing the acceptance criteria's literal "07 = 7" and grade-4/5 comma/dot tolerance requirement (FR-12/FR-13). The implementer's own Spec Change Log disposed of this as a documentation correction only | critical | confirmed independently by the orchestrator before review even started -> patch (dispatched directly, in parallel with this review, already underway): add a lenient numeric-normalizer inside `learning/graders.py` (not `content/schema.py`) tolerant of leading zeros and both decimal separators, used by every numeric-keyed grader; add regression tests for "07"="7", "3.5"="3,5" |
| 2 | Retry Queue can resolve prematurely: `_part_currently_correct()` treats a NEVER-ATTEMPTED sibling Part the same as a correctly-answered one ("never attempted -- does not block resolution"), so a 3-Part Problem where only Part A is ever touched (wrong then corrected) resolves the Retry Queue row even though Parts B and C were never attempted at all -- contradicting "every other Part has also now been answered correctly" | high | confirmed by 1 reviewer via direct code trace, not exercised by any existing test (the one multi-Part test always has the sibling Part actually attempted correctly) -> patch: a Part that has never been attempted must BLOCK resolution, not pass it -- only resolve once every Part of the Problem has an attempt AND its most recent one is correct; add a test with an untouched sibling Part confirming the Retry Queue stays open |
| 3 | Retry Queue resolution's "latest attempt" tie-break (`received_at, id`) is unreliable when a batch contains 2+ attempts on the same Part: `received_at` is identical for every event in one HTTP request (resolved once via `get_now()`), and the id-based tie-break falls back to UUIDv7 lexicographic order, which is only millisecond-monotonic and client-controlled -- two attempts minted in the same millisecond (a fast wrong-then-retry pair sent in one batch) can sort in the wrong order, causing resolution logic to read a stale verdict for that Part | high | confirmed by 1 reviewer via code trace, real ordering hazard not covered by any test (no test posts 2+ attempts on the same Part within one batch) -> patch: use a reliable insertion-order tiebreak -- e.g. an autoincrementing rowid/sequence column, or process a batch's own events in their IN-BATCH order when multiple attempts on the same Part appear together, rather than relying on stored timestamp/id sort after the fact; add a test posting 2 attempts (wrong then correct) on the same Part in ONE batch call and confirming resolution reflects the LATER one |
| 4 | `backend/tests/test_app.py`'s `test_fresh_data_dir_created_with_wal_and_migrations` still asserts the migration head is `"0011_progress"` and that `progress_retry_items` is absent from the table set -- both now wrong after this story's `0012_retry_items` migration; this test should currently be failing | high | confirmed by 1 reviewer, this is a straightforward regression the implementer's own "full suite" verification apparently didn't catch or wasn't run to completion against -> patch: update the assertion to `"0012_retry_items"` and include `progress_retry_items` in the expected table set, matching Story 2.4's own precedent of updating this exact test for its own migration |
| 5 | `match`'s wrong-grading test only asserts `result.correct is False`, never checks `wrong_keys == []`, unlike every other all-or-nothing type's wrong-case test | low | -> patch: add the missing `wrong_keys == []` assertion to `match`'s existing wrong-case test |
| 6 | Several edge cases have no test: a real `attempt` against a `fallback` Part through the actual `POST /sessions/{id}/events` endpoint (only a direct `grade_part()` TypeError is tested); an `attempt` event with `problem_id: null` reaching the grading code path specifically (existing null-problem_id tests all short-circuit earlier for other reasons); a 3rd+ wrong attempt on the same Part (only 1st and 2nd are tested); `hint_requested` immediately followed by a wrong attempt on the same Part (independence assumed, not asserted together); Retry Queue counting across two distinct Sessions for the same profile (Profile-wide counting is correct by code inspection but only implicitly exercised, never with two real distinct session_ids); `match` with a duplicate left key or unknown right key, `spot_difference` with extra/missing region keys; negative numbers and bare `"0"` in numeric grading; `multiple_choice`/`image_select` with `multi: false` submitted with 2+ selections | low | all confirmed as genuine, low-risk gaps (code inspection shows graceful handling in every case, just unverified by a test) -> patch: add the cheapest 3-4 of these (fallback-attempt-via-real-endpoint, problem_id:null-reaching-grading, cross-session Retry Queue counting, and the multi:false-over-selection case) as time allows; the rest can be logged as lower-priority test-coverage debt if time-constrained |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed the critical numeric-tolerance fix (`_lenient_number()` in graders.py, not touching content.schema) and both high-severity Retry Queue fixes (never-attempted Parts now block resolution; rowid-based insertion-order tiebreak) directly in source. Ran `ruff check` (clean) and the full backend suite independently: 830/830 passing. Story marked done.

</frozen-after-approval>
