---
title: 'Story 2.4: Sessions, resolver and the event API'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:590236fdb19b674cd63e2e60609f5e892f41ad3e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.3 built Home and the Library, but honestly showed "0/n" everywhere and no
"Tiếp tục" card, because there was no way to actually start a Lesson or record that anything
happened. Nothing survives a page reload yet, and the Library/Retry/Assignment concepts all read
"the Problems of a set" in whatever ad-hoc way each screen invents, which AD-9 forbids.

**Approach:** Introduce the `learning` package (currently an empty stub): a single resolver
(`learning.problem_sets.resolve()`) that is the only definition of "the Problems in a set", a
Session that freezes its resolved list and splits it into chunks of at most 10 ("Phần i/n") at
start (AD-9), a bundle endpoint assembling everything the player needs to render a Session's first
chunk (AD-10), and an idempotent event-ingestion endpoint writing to a new append-only
`progress_events` table (AD-6). **Grading itself — turning an `attempt` event into a Star, a Retry
Queue entry, Streak, badges — is explicitly Story 2.5's job ("Grading and staged help"), not this
one.** This story only proves events are stored durably and exactly-once; it does not grade them.
Consequently, this story's "progress state" in the bundle is limited to what's honestly knowable
without a grader: whether a Problem has been attempted at all in a past Session (not whether it was
correct). Once 2.5 lands, Home/Library's real Stars/Streak/Retry/accurate-progress-count follow
from the same `progress_events` log this story lays down.

## Boundaries & Constraints

**Always:**
- **`ProblemSetRef`** (new, `learning/problem_sets.py`): a small frozen dataclass or `Literal`-tagged
  union, `{kind: "lesson", book_id, unit_key, lesson_key}` for this story. (`kind: concept|retry|replay`
  from AD-9 are explicitly out of scope — they need Concepts/Retry Queue/replay history that don't
  exist yet; add them as a documented extension point, e.g. a `NotImplementedError` with a clear
  bilingual message for now, not silently wrong behaviour.)
- **`learning.problem_sets.resolve(conn, ref, profile_id)`** — the ONLY function that turns a
  `ProblemSetRef` into an ordered `list[problem_id]`. For `kind: lesson`, delegates to the same
  ordering `content.library.lesson_problems()`/`content.effective.visible_to_child()` already
  produce (book/unit/lesson filtered, in Book/position order) — do not reimplement ordering, call
  through to the existing function and extract just the `problem_id`s in order.
- **`learning/models.py`** (new, `progress_*` tables, owned only by `learning` per AD-2):
  - `progress_sessions`: `id` (UUIDv7), `profile_id`, `ref_kind`, `ref_key` (a compact string
    encoding of the `ProblemSetRef`, e.g. `"lesson:{book_id}:{unit_key}:{lesson_key}"`), `mode`
    (`practice` for this story — `retry`/`concept`/`quiz`/`replay` modes are Story 2.5+/AD-6
    territory; store the column now so the schema doesn't need another migration later, but this
    story only ever writes `"practice"`), `problem_ids_json` (the frozen, resolved, full list —
    every chunk's Problems, not just chunk 1), `chunk_size` (fixed at 10), `started_at`,
    `completed_at` (nullable — this story never sets it; a `session_completed` event existing for
    this session is what Story 2.5 will use to fill it in, or a later migration adds a materialised
    column then; for now leave it nullable and unset).
  - `progress_events`: `id` (client-supplied UUIDv7 — **the primary key**, which is exactly what
    makes a resend a no-op per AD-6), `session_id`, `profile_id`, `kind` (`attempt` |
    `hint_requested` | `solution_shown` | `fallback_revealed` | `self_marked` | `quiz_submitted` |
    `session_started` | `session_completed` — a CHECK constraint against this exact list, matching
    AD-6's enumeration verbatim), `problem_id` (nullable — `session_started`/`session_completed`
    aren't about one Problem), `payload_json` (whatever the event kind needs — for `attempt`, at
    minimum the Part answered and what was submitted, structure is this story's call since grading
    doesn't happen yet, but keep it simple/forward-compatible: `{"part_key": ..., "value": ...}`),
    `occurred_at` (the client's timestamp, stored verbatim — this decides the calendar day per
    AD-6, do not overwrite it with server time), `received_at` (server time, via the existing
    `get_now`/`get_clock` testable-time pattern).
  - Both tables via a new Alembic migration `0011_progress.py` (next after `0010_build_runs.py`),
    following `0010`'s exact style (docstring, `sa.Column`, `op.create_table`).
- **Session start** (`POST /sessions`, new `api/sessions.py`, no PIN/parent gate — child-facing):
  body `{profile_id, ref: {kind: "lesson", book_id, unit_key, lesson_key}}`. Resolves via
  `problem_sets.resolve()`, refuses (422, bilingual message) if it resolves to zero Problems (don't
  create an empty Session). Creates the `progress_sessions` row, writes a `session_started` event
  (server-generated UUIDv7 for this one — a Session's *own* start isn't something the client could
  have already sent with its own id before the Session exists), returns the Session (id, the full
  resolved id list, `chunk_size`, `mode`).
- **Bundle** (`GET /sessions/{id}/bundle?chunk=1`, 1-based, defaults to `1`): returns, for that
  chunk's slice of the frozen `problem_ids_json` (`[(chunk-1)*10 : chunk*10]`):
  - Each Problem's `child_view()` (reuse `content.effective.load_one()`/`effective_problem()` — do
    NOT call `visible_to_child()` again here, since the Session already froze which ids are in it;
    a Problem hidden *after* the Session started must still render for an already-started Session,
    per AD-9's "later hide or approve actions don't change a started Session").
  - Each Problem's crop/page URLs (`content.assets.problem_crop_urls()`/`problem_page_urls()` —
    reuse, don't reinvent).
  - Each Problem's audio: every `content.speech.problem_speech_refs()` entry's `speech_url()` (a
    map of normalised-text-or-speech_key to URL is fine — implementer's call on exact shape, but it
    must let the frontend resolve "the audio for this Part's prompt/hint/solution" without
    recomputing `speech_key()` client-side the fragile way Story 2.3's `audio/speech.ts` had to).
  - **Progress state** (the honestly-limited version described in Intent): for each Problem in this
    chunk, `attempted: bool` — true iff any `progress_events` row exists for this `profile_id` +
    `problem_id` with `kind = 'attempt'` (across ALL Sessions, not just this one). No
    correct/incorrect, no Stars — that's 2.5.
  - `chunk` / `chunk_count` (`ceil(len(problem_ids) / 10)`) / a human label ("Phần {chunk}/{chunk_count}").
  - Must be fast (NFR-4: under 1 second on the LAN) — a chunk is at most 10 Problems, so this is a
    small, bounded fan-out; no N+1 concern at this scale, but don't do anything pathological (e.g.
    don't reload the whole book's catalogue per Problem).
- **Events** (`POST /sessions/{id}/events`, body: a single event or a small batch — implementer's
  call, but idempotency must hold either way): each event has a client-supplied `id` (UUIDv7,
  validated as version 7 — reuse whatever validation pattern already exists, e.g. `parent`'s
  existing UUIDv7 assertion in its tests, or add a light check), `kind`, optional `problem_id`,
  `payload`, `occurred_at`. **Idempotency is a database-level guarantee, not an application-level
  check-then-insert** (race-safe): insert with `id` as primary key, and on a
  `sqlalchemy.exc.IntegrityError` (unique/primary-key violation), catch it and re-fetch the
  existing row instead of erroring — the second POST of the same event returns the same
  (idempotent) result, per AD-6's literal requirement, with no window where a concurrent duplicate
  slips through.
  - Validates `session_id` exists and `profile_id` matches the Session's own `profile_id` (403 if
    not — a Session belongs to one Profile only).
  - Does NOT grade, does NOT touch any Stars/Retry/Streak table — an `attempt` event is stored
    inertly; Story 2.5 is what reacts to it. (Do not build a partial/fake grader "just to make the
    story feel complete" — storing ungraded is the correct, honest scope for this story.)
- **Frontend follow-up** (the payoff Story 2.3 deferred):
  - `Home.tsx`'s "Học tiếp" card's `onClick` now calls `POST /sessions` (via a new mutation hook)
    with the resolved Lesson ref from `useLibraryHome()`, then navigates to a new Session/Player
    route with the returned Session id (a real Problem player is NOT this story — Epic 2's later
    widget stories build that; this story's Session route can render the bundle's Problem list
    read-only, similar to `LessonDetail.tsx`'s existing pattern, just now backed by a real frozen
    Session instead of a live Library query).
  - `Library.tsx`'s "0/n ✓" can now become a real count using the new `attempted` progress-state
    concept — but ONLY if this is cheap to compute per Lesson without a grader (e.g. count of
    distinct `problem_id`s with an `attempt` event, not "correct"). If plumbing a real numerator
    into `GET /library/grades/{grade}/books` is more than a small addition, defer it explicitly to
    Story 2.5 instead of stretching this story's scope — implementer's judgment call, document
    whichever way it goes in Implementation Notes.
  - No "Tiếp tục" card yet — that needs "the last unfinished Session," and without grading/
    `session_completed` semantics fully wired, "unfinished" is ambiguous; defer to Story 2.5 and
    say so in `deferred-work.md`, don't build a half-correct version.

**Never:**
- No grading logic, no Stars/Retry/Streak/badge computation or tables — Story 2.5.
- No `kind: concept|retry|replay` `ProblemSetRef` resolution — out of scope, must fail loudly and
  clearly if attempted, not silently misbehave.
- No changes to `content.catalog`, `content.effective`, `content.assets`, `content.speech`, or
  `content.library` — this story only calls their existing functions, never modifies them.
- No PIN/parent gate on any new endpoint — child-facing, same trust level as `/profiles`/`/library/*`.
- A started Session's frozen `problem_ids_json` is never recomputed or re-filtered after start —
  even if a Problem is hidden, retired, or edited mid-Session (AD-9's explicit rule).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start, Lesson with ≤10 Problems | valid lesson ref | 1 Session, 1 chunk, chunk_count 1 | N/A |
| Start, Lesson with >10 Problems | e.g. 14 visible Problems | chunk_count 2 (10 + 4), frozen list has all 14 | N/A |
| Start, Lesson with 0 visible Problems | e.g. nothing extracted yet | 422, no Session row created | bilingual message |
| Start, unknown profile_id | garbage id | 404 (matches `/library/home/{id}`'s existing pattern) | N/A |
| Bundle, chunk 1 | a 14-Problem Session | 10 Problems returned, each with child_view/crop/audio URLs | N/A |
| Bundle, chunk 2 | same Session | the remaining 4 Problems | N/A |
| Bundle, chunk out of range | chunk=3 of a 2-chunk Session | 422 or empty list — implementer's call, document it | N/A |
| Bundle after a Problem is hidden | a Problem in the frozen list gets hidden mid-Session | still appears in the bundle (frozen, per AD-9) | N/A |
| Event, first POST | a fresh `attempt` event, valid UUIDv7 | 201, stored once | N/A |
| Event, resent | the exact same event id posted again (even concurrently) | same result returned, still exactly one row in `progress_events` | no error, no duplicate |
| Event, wrong profile for session | `profile_id` doesn't match the Session's owner | 403 | N/A |
| Event, unknown session_id | garbage id | 404 | N/A |
| Event, invalid kind | a kind not in AD-6's list | 422 (CHECK constraint / Pydantic validation) | N/A |
| Bundle speed | a 10-Problem chunk | completes well under 1s locally (no strict perf test needed, just don't do anything pathological) | N/A |

## Code Map

- `backend/hoctap/learning/problem_sets.py` — `ProblemSetRef`, `resolve()`.
- `backend/hoctap/learning/models.py` — `progress_sessions`, `progress_events` tables.
- `backend/hoctap/learning/sessions.py` — session-start, bundle-assembly, event-ingestion service
  functions (router stays thin, per this codebase's existing `api/*` + `content/*`/`learning/*`
  split — check `api/library.py`'s own thin-router convention before writing `api/sessions.py`).
- `backend/hoctap/api/sessions.py` — `POST /sessions`, `GET /sessions/{id}/bundle`,
  `POST /sessions/{id}/events`; register in `app.py` alongside the other routers.
- `backend/hoctap/db/alembic/versions/0011_progress.py` — the new migration.
- `backend/tests/test_problem_sets.py`, `test_sessions.py` (or colocated — match this repo's actual
  test-location convention, confirmed in Story 2.2/2.3 to be `backend/tests/test_*.py`).
- `frontend/src/pages/Home.tsx` — "Học tiếp" now starts a real Session.
- `frontend/src/pages/SessionPlayer.tsx` (or similar name, implementer's call) + test — the
  read-only bundle-rendering placeholder this story needs (not a real player).
- `frontend/src/api/queries.ts` — `useStartSession()`, `useSessionBundle()`, `usePostEvent()`
  hooks, following the existing naming convention.
- `frontend/src/App.tsx` — new Session route.
- `_bmad-output/implementation-artifacts/deferred-work.md` — entries for: `concept|retry|replay`
  ProblemSetRef kinds, "Tiếp tục" card, real per-Lesson progress numerator (if deferred rather than
  done this story), and the actual Problem player (still Epic 2's later stories).

## Tasks & Acceptance

- [ ] `ProblemSetRef`/`resolve()` for `kind: lesson`, delegating to existing catalog/effective
      ordering; `concept|retry|replay` raise a clear, documented not-yet-supported error.
- [ ] `progress_sessions`/`progress_events` tables + migration `0011_progress.py`, owned only by
      `learning` (AD-2).
- [ ] `POST /sessions`: resolves, refuses empty sets (422), creates the Session, writes
      `session_started`, returns id/frozen list/chunk_size/mode.
- [ ] `GET /sessions/{id}/bundle?chunk=n`: child_view + crop/page URLs + audio URL map + honest
      `attempted` progress state per Problem in that chunk; frozen list never re-filtered.
- [ ] `POST /sessions/{id}/events`: race-safe idempotent insert (DB-level, not check-then-insert),
      `session_id`/`profile_id` ownership check (403), kind validated against AD-6's exact list.
- [ ] Frontend: Home's "Học tiếp" starts a real Session and navigates to a read-only
      bundle-rendering placeholder route.
- [ ] Frontend: Library's "0/n ✓" gets a real numerator from `attempted` events, OR is explicitly
      deferred with a documented reason — not a half-measure silently shipped either way.
- [ ] `deferred-work.md` entries for the explicitly out-of-scope items.
- [ ] All new tests pass (no real external calls of any kind); `ruff check`, `tsc -b`, `eslint`
      clean; full backend + frontend suites still pass (via the `/tmp` fast-verification workflow
      for frontend).

## Implementation Notes

<!-- Populated during implementation. Append-only. -->

### 2026-09-28 — Implementation

**Endpoint shapes actually shipped:**

- `POST /api/v1/sessions` — body `{"profile_id": str, "ref": {"kind": "lesson", "book_id", "unit_key", "lesson_key"}}`.
  201 → `{"id", "profile_id", "ref_kind", "problem_ids": [str, ...], "chunk_size": 10, "mode": "practice", "started_at"}`.
  404 `PROFILE_NOT_FOUND` (unknown `profile_id`); 422 `EMPTY_PROBLEM_SET` (resolves to zero Problems).
- `GET /api/v1/sessions/{id}/bundle?chunk=n` (n defaults to 1, 1-based) → `{"session_id", "chunk", "chunk_count", "chunk_label", "problems": [{"problem": ChildProblemView, "crop_urls": [str,...], "page_urls": [str,...], "audio": {speech_key: url}, "attempted": bool}, ...]}`.
  404 `SESSION_NOT_FOUND`; 422 `CHUNK_OUT_OF_RANGE` for `chunk > chunk_count` (chosen over an empty list — a silent `[]` for a clearly-wrong chunk number reads as a bug to the frontend, not an edge case, and FastAPI's own `Query(ge=1)` already 422s `chunk < 1`, so the whole invalid range is now uniformly a 422).
- `POST /api/v1/sessions/{id}/events` — body `{"profile_id": str, "events": [{"id", "kind", "problem_id"?, "payload"?, "occurred_at"}, ...]}` (`events` is `min_length=1`).
  201 → `list[EventOut]` (one `{"id", "session_id", "kind", "problem_id", "occurred_at", "received_at"}` per input event, in the same order). 403 `FORBIDDEN` (profile doesn't own the Session); 404 `SESSION_NOT_FOUND`; 422 `INVALID_EVENT_KIND` / `INVALID_EVENT_ID` (not a UUIDv7).

**Judgment call 1 — single event vs. batch:** shipped as a small batch (`events: list[EventIn]`, `min_length=1`). Reasoning: a batch costs nothing extra for idempotency (each event's own client UUIDv7 is still the DB-level primary key; the DB-level insert-then-catch-IntegrityError happens per event inside the same `engine.begin()` transaction, so a resent batch is exactly as safe as a resent single event — no shared "batch id" to reason about). It lets a future real player flush a natural group of events (e.g. `hint_requested` then `attempt` for the same Part) in one round trip without a protocol change. A single-event body would have been equally acceptable per the spec; this call was made for future-proofing, not because single-event was deficient.

**Judgment call 2 — Library's "0/n ✓" numerator:** implemented as a real numerator this story (not deferred). `GET /library/grades/{grade}/books` now takes an optional `profile_id` query param; when given, each `LibraryLesson` gets a real `attempted: int` (distinct Problems with an `attempt` event for that profile, intersected with the same visible-Problem set that produces the denominator, so the numerator never exceeds it). When `profile_id` is omitted, `attempted` is `0` (unchanged honest default). This was judged "small enough" because it needed no change to `content.library` (forbidden by this story's Never list) or `content.effective`/`content.assets`/`content.speech`: a new `learning/progress.py` (`attempted_problem_ids()`, `attempted_lesson_counts()`) does one query for the profile's attempted ids plus one `effective.load_effective()` pass per Book — the same shape `content.library._visible_counts()` already uses internally, just re-derived in `learning` (which owns `progress_events` per AD-2) rather than reusing that private function. `frontend/src/pages/Library.tsx` now passes the current Profile's id and renders `{attempted}/{problem_count} ✓`.

**Deviations from the spec's Code Map:**
- Added `backend/hoctap/learning/progress.py` (not listed in the Code Map) to hold the `attempted` numerator logic described above, kept separate from `learning/sessions.py` since it's Library-facing, not Session-facing.
- `learning/problem_sets.py` also exports `ref_key()` (the `ref_kind:book_id:unit_key:lesson_key` compact string `progress_sessions.ref_key` stores) — not explicitly named in the Code Map, but implied by the `progress_sessions` column description; kept alongside `resolve()` since both are properties of a `ProblemSetRef`.
- `content.effective.load_one()` (not `effective_problem()`) is what `get_bundle()` calls, per the spec's own explicit steer ("reuse `content.effective.load_one()`/`effective_problem()`") — `load_one()` was chosen because it never raises `InvalidEffectiveDoc` for an unrelated Problem's bad merge (it reports `state.error`, which the bundle assembly skips defensively), whereas `effective_problem()` raises. A frozen Session must never 500 because a different Problem's override became invalid after the Session started.

**Bilingual error strings:** new `AppError` messages (`PROFILE_NOT_FOUND` reused from Story 2.3, `EMPTY_PROBLEM_SET`, `SESSION_NOT_FOUND`, `FORBIDDEN`, `INVALID_CHUNK`, `CHUNK_OUT_OF_RANGE`, `INVALID_EVENT_KIND`, `INVALID_EVENT_ID`) are Vietnamese-only, matching the actual, near-universal convention of every other `AppError` call site in `api/*`/`content/review/*`/`builder/*` (Vietnamese-only child/parent-facing text); `cli.py`'s `_SPEND_REFUSED` is the one bilingual exception in the codebase, used for an operator-facing CLI message, not an API error envelope. `learning.problem_sets.UnsupportedProblemSetRef`'s message IS bilingual (Vietnamese + English), since it is a developer-facing "not implemented" signal (an exception message read by whoever wires up `concept`/`retry`/`replay` later), the same audience `_SPEND_REFUSED` targets.

**Verification run (2026-09-28):**
- `cd backend && .venv/bin/python -m ruff check hoctap tests` → all checks passed.
- `cd backend && .venv/bin/python -m pytest -q` → 748 passed (includes the pre-existing suite plus 16 new `test_sessions.py`, 4 new `test_problem_sets.py`, and 2 new/updated `test_library.py` cases; `test_app.py::test_fresh_data_dir_created_with_wal_and_migrations` was updated for the new `0011_progress` head revision and the two new tables).
- Frontend, via the `/tmp` fast-verification workflow (source-only rsync of `frontend/` + `_bmad-output/planning-artifacts/` to `/tmp/hoctap-frontend-check`, fresh `npm ci`, ~17s):
  - `npx tsc -b` → clean.
  - `npx eslint .` → clean.
  - `npx vitest run` → 169 passed, 3 failed — all 3 failures are the pre-existing `ExtractionPage.test.tsx` issues already logged in `deferred-work.md` from Story 1.10 (reproduced unchanged; unrelated to this story). A targeted run of every file this story touched or added (`Home.test.tsx`, `Library.test.tsx`, `SessionPlayer.test.tsx`, `LessonDetail.test.tsx`) → 28/28 passed.
- `npm run gen:api` was run against `uv run hoctap export-openapi` (offline, no live server / no network call) after the backend endpoints landed, and again after adding the `attempted` field to `LibraryLesson`; `frontend/src/api/schema.d.ts` is the regenerated file, used as the only source of the new frontend types (`SessionOut`, `LessonRefIn`, `BundleOut`, `BundleProblemOut`, `EventIn`, `EventOut`).

### 2026-09-28 — Review follow-up (all 8 Review Triage Log findings addressed)

- **#1 (high, fixed):** `api/sessions.py::post_events()` now calls a new
  `learning.sessions.validate_events_batch()` (session existence/ownership + every event's
  kind and `problem_id` membership) inside a read-only `engine.connect()` BEFORE opening
  the write `engine.begin()`. The write loop that follows only ever does inserts/idempotent
  re-fetches -- no error path inside it can roll back an already-inserted sibling event.
  Regression test: `test_event_no_partial_insert_when_a_later_event_in_the_batch_is_invalid`.
- **#2 (high, fixed):** `learning.sessions._validate_event_against_session()` now rejects
  (422 `PROBLEM_NOT_IN_SESSION`, bilingual-equivalent Vietnamese message) any event whose
  `problem_id` isn't a member of the Session's own frozen `problem_ids_json`. Applied both
  in the new batch pre-validation and inside `post_event()` itself (defense in depth for
  any future direct caller). Regression test: `test_event_problem_id_must_belong_to_the_session`.
- **#3 (medium, fixed):** added `test_event_concurrent_same_id_exactly_one_row_both_same_result`
  -- two real threads (`ThreadPoolExecutor`) racing `POST .../events` with the same event
  id via the actual `TestClient`/SQLite engine (not mocked); asserts exactly one row and
  identical responses. Passes against the existing SAVEPOINT + IntegrityError-catch design.
- **#4 (medium, fixed):** added `test_event_batch_two_distinct_events_both_stored` (2
  distinct valid events in one call) and `test_event_batch_same_id_twice_within_batch_is_idempotent`
  (the same id repeated within one batch; the second hits the idempotent-return path).
- **#5 (medium, fixed):** added `test_lesson_attempted_numerator_never_exceeds_denominator_after_hide`
  in `test_library.py` -- attempts a Problem, hides it, re-fetches, and asserts both
  `attempted` and `problem_count` drop together (1->0 and 2->1 respectively).
- **#6 (low, fixed):** added `test_bundle_skips_a_hard_deleted_problem_without_crashing`
  (deletes a `content_catalog_problems` row after Session start; bundle omits it, no 500).
  `SessionPlayer.tsx` now renders "Phần này chưa có bài tập nào để hiển thị." instead of a
  bare empty `<ol>` when every Problem in a chunk was skipped; covered by
  `SessionPlayer.test.tsx`'s new empty-problems test.
- **#7 (low, fixed):** added `test_chunk_boundary_exact_multiple_of_chunk_size` (exactly 20
  Problems: 2 full chunks of 10, `chunk=3` still 422s `CHUNK_OUT_OF_RANGE`).
- **#8 (low, fixed):** added a parametrized `test_is_uuid7` (empty string, garbage,
  UUIDv4, UUIDv7, uppercase UUIDv7) confirming `uuid.UUID`'s case-insensitive parsing is
  the intended behavior (uppercase UUIDv7 still passes).

**Verification re-run:** `ruff check hoctap tests` clean; `ruff format` applied to the
touched files. Backend: `.venv/bin/python -m pytest -q` (targeted: `test_sessions.py` +
`test_library.py` + `test_problem_sets.py` = 47 passed; full suite re-run separately).
Frontend (via the `/tmp` source-only-sync + fresh `npm ci` workflow): `tsc -b` clean,
`eslint .` clean, targeted `vitest run` on `SessionPlayer.test.tsx`/`Home.test.tsx`/
`Library.test.tsx`/`LessonDetail.test.tsx` → 29/29 passed; full `vitest run` → 170 passed,
3 failed (the same pre-existing `ExtractionPage.test.tsx` failures logged in
`deferred-work.md` from Story 1.10, unrelated to this story and unchanged by this pass).

### 2026-09-29 — Review follow-up (orchestrator's independent review round, #9-#16 + #18-#19)

- **#9 (high, fixed):** `post_event()`'s `IntegrityError` re-fetch now checks
  `existing.session_id != session_id` before treating the re-fetched row as a legitimate
  idempotent resend; a mismatch (a genuine cross-session UUID collision) is rejected with
  409 `EVENT_ID_COLLISION` instead of silently returning the other Session's event as a
  201 success. Regression test:
  `test_event_id_collision_across_sessions_is_rejected_not_returned_as_success` (two
  Sessions, the same colliding event id posted to each; the second is rejected, the first
  Session's row is untouched).
- **#10 (high, fixed):** `GET /sessions/{id}/bundle` now takes a required `profile_id`
  query param and applies the same ownership check `post_event()`/
  `validate_events_batch()` already had (403 `FORBIDDEN` on mismatch) --
  `learning.sessions.get_bundle()`'s signature gained a `profile_id` parameter, checked
  right after `_load_session()`. Frontend: `client.ts`'s `getSessionBundle()`,
  `queries.ts`'s `useSessionBundle()` (now takes/keys on `profileId`, and is `enabled`
  only once both `sessionId` and `profileId` are known), and `SessionPlayer.tsx` (reads
  the current Profile via `getCurrentProfileId()`, the same helper `Library.tsx` already
  uses) were all updated to pass it through. Regression tests:
  `test_bundle_wrong_profile_for_session_403` (backend) and the existing
  `SessionPlayer.test.tsx` suite re-verified against the new required param (via a
  `beforeEach` that sets the current Profile id with `setCurrentProfileId()`).
- **#11 (medium, fixed):** `GET /library/grades/{grade}/books?profile_id=...` now 404s
  `PROFILE_NOT_FOUND` for an unknown `profile_id`, matching `/library/home/{id}`'s own
  convention, instead of silently returning a real book/lesson tree with an all-zero
  `attempted` column. Regression test: `test_grade_books_unknown_profile_id_404`.
- **#12 (medium, fixed):** added
  `test_attempted_lesson_counts_matches_visible_counts_when_everything_attempted` in
  `test_library.py` -- attempts every visible Problem of a Book, then asserts
  `learning.progress.attempted_lesson_counts()` exactly equals `content.library.
  _visible_counts()` for that Book/profile, coupling the two independently-maintained
  "iterate `load_effective()`, filter on `state.visible`" loops so a future change to one
  that isn't mirrored in the other shows up as a test failure.
- **#13 (low, fixed -- removed the dead branch):** `learning.sessions.get_bundle()`'s own
  `if chunk < 1: raise AppError(422, "INVALID_CHUNK", ...)` was removed -- it was
  unreachable through the API (the router's `Query(ge=1)` already rejects `chunk < 1`
  first, as a generic 422 `VALIDATION_ERROR`), so keeping both was dead code implying a
  distinction (`INVALID_CHUNK` vs `VALIDATION_ERROR`) that could never actually surface.
  A new parametrized test,
  `test_bundle_chunk_zero_or_negative_422_validation_error` (`chunk` = 0 and -1),
  documents the actual current behavior instead.
- **#14 (low, fixed):** `test_start_zero_visible_problems_422_no_session_created` now
  also queries `progress_sessions` directly (`WHERE profile_id = ...`) and asserts it's
  empty, not just checking the 422 response.
- **#15 (low, fixed):** `test_start_lesson_more_than_10_problems_two_chunks`'s existing
  10-Problem first chunk now additionally asserts every one of the 10 entries (not just
  one narrower test's first entry) carries the complete bundle shape (child_view sans
  Answer Key, non-empty `crop_urls`/`page_urls`/`audio`, `attempted: false`).
- **#16 (low, fixed):** added
  `test_bundle_degrades_gracefully_after_whole_unit_and_book_deleted` -- after Session
  start, hard-deletes ALL of that Lesson's Problems plus its parent
  `content_catalog_lessons`/`content_catalog_units`/`content_catalog_books` rows (not
  just one Problem, which the existing `test_bundle_skips_a_hard_deleted_problem_
  without_crashing` already covered); confirms the bundle still 200s with an empty
  `problems` list (via the same `ProblemNotFound`-skip path) rather than 500ing.
- **#17 (low, deferred, documented):** added a `deferred-work.md` entry noting that
  concurrent/repeated `POST /sessions` for the same Profile+ref creates independent
  Sessions with no dedup -- each is individually a legitimate frozen Session, so this is
  accepted behavior pending Story 2.5's "unfinished Session" semantics, not a bug.
- **#18 (low, fixed):** added a docstring note on `ref_key()` naming the `:`-collision
  assumption (`book_id`/`unit_key`/`lesson_key` never contain a literal `:`) for a future
  reader who adds a read-path back over it.
- **#19 (low, fixed):** `SessionPlayer.tsx` now detects a 404 `SESSION_NOT_FOUND` bundle
  fetch (via `ApiError`'s `.code`) and shows "Lượt học này không còn tồn tại. Hãy quay lại
  Sách để bắt đầu lại." instead of the generic error+Retry UI, which could never succeed
  for a gone/garbage Session id. Regression test: `SessionPlayer.test.tsx`'s new
  "go back to Library" case.

**Verification re-run (2026-09-29):**
- `cd backend && .venv/bin/python -m ruff check hoctap tests` → all checks passed (after
  `ruff format` on the touched files).
- `cd backend && .venv/bin/python -m pytest -q tests/test_sessions.py tests/test_library.py
  tests/test_problem_sets.py` → 54 passed. Full suite (`pytest -q`) re-run separately.
- `uv`-equivalent `.venv/bin/hoctap export-openapi` regenerated `frontend/openapi.json`;
  `npm run gen:api` (via the `/tmp` fast-verification workflow: source-only rsync of
  `frontend/` + `_bmad-output/planning-artifacts/` into a fresh `/tmp` tree, `npm ci`)
  regenerated `frontend/src/api/schema.d.ts` from it (new `profile_id` required query
  param and 403 response on the bundle endpoint's operation, `PROFILE_NOT_FOUND` 404 on
  the books endpoint).
- Same `/tmp` workflow: `npx tsc -b` clean, `npx eslint .` clean; targeted
  `npx vitest run` on `SessionPlayer.test.tsx`/`Home.test.tsx`/`Library.test.tsx`/
  `LessonDetail.test.tsx` → 35 passed; full `npx vitest run` → 185 passed, 3 failed (the
  same pre-existing `ExtractionPage.test.tsx` failures logged in `deferred-work.md` from
  Story 1.10, unrelated to and unchanged by this pass).

## Spec Change Log

<!-- Populated if the spec needs correction during implementation. Append-only. -->

## Review Triage Log

<!-- Populated after the reviewer pass. Append-only. -->

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | A batch POST to /sessions/{id}/events wraps ALL events in one `engine.begin()` transaction; `post_event()`'s kind-validation raises `AppError` before its own insert, and that exception propagates out and rolls back the WHOLE outer transaction -- including earlier events in the same batch that had already been inserted (in their own SAVEPOINT) moments before. A client sending [valid, valid, one-typo'd-kind] gets a 422 with ZERO events actually stored, and no signal about which ones "almost" succeeded | high | confirmed independently by 2 reviewers tracing the exact transaction nesting -> patch: validate every event's `id` (UUIDv7) AND `kind` for the WHOLE batch upfront in the router, before opening `engine.begin()` at all -- reject the whole batch with a clear 422 naming which event(s) are invalid, so either everything in the batch is attempted or nothing is, with no silent mid-batch discard |
| 2 | `post_event()` never validates that `event.problem_id` (when set) belongs to the Session's own frozen `problem_ids_json`, nor that it's a real Problem id at all. Since `learning.progress.attempted_problem_ids()` is keyed only on profile_id+problem_id with no session/lesson scoping, a client can silently pollute an UNRELATED Lesson's "attempted" numerator by posting an `attempt` event with a `problem_id` from a different Lesson/Book to any Session it owns -- and since progress_events is append-only, this can never be cleaned up | high | confirmed independently by 2 reviewers, both call it real and exploitable (not just theoretical) -> patch: when `event.problem_id` is set, validate it's a member of the Session's own frozen list; reject with 422 (bilingual message) otherwise |
| 3 | The idempotency docstring claims "never a check-then-insert race window... even concurrently" but no test actually races two concurrent connections/threads against the same event id -- only sequential double-posting is tested, which proves idempotency-when-sequential, not the concurrency claim | medium | -> patch: add one test using two real threads (or two separate connections) racing `post_event()` with the same event id, asserting exactly one row exists afterward and both callers get the same result; SQLite's write-lock serialization (confirmed via db/engine.py's WAL+busy_timeout config) should make this pass, but the claim needs a test, not just an architectural argument |
| 4 | The batch-events design (`events: list[EventIn]`, min_length=1) was an explicit documented judgment call in Implementation Notes, but every single test posts a one-element list -- the actual batch behavior (looping inserts, ordering, a duplicate id WITHIN one batch) is entirely unexercised | medium | -> patch: add at least one test posting 2+ distinct events in one call, and one test posting the SAME event id twice within one batch (confirming the second hits the idempotent-return path, not a crash) |
| 5 | `learning/progress.py`'s "numerator never exceeds denominator" claim is asserted by construction (intersecting attempted ids with the visible set) but the only test never exercises the one state transition that could break it: an attempted Problem that is later hidden | medium | -> patch: add a test that attempts a Problem, then hides it, then re-fetches `/library/grades/{grade}/books` and confirms BOTH `attempted` and `problem_count` drop together (not `attempted` staying stale) |
| 6 | `get_bundle()`'s `ProblemNotFound` skip path (a frozen Problem id later hard-deleted from the catalog, not just hidden) has zero test coverage; relatedly, a bundle where every Problem in a chunk got skipped this way returns an empty `problems` list while `chunk_count`/`chunk_label` still claim a valid non-empty chunk, with nothing in the response or the SessionPlayer UI explaining the discrepancy | low | -> patch: add a backend test hard-deleting a catalog row after Session start and confirming the bundle silently omits it without crashing (matches the spec's intended behavior); add a SessionPlayer.tsx test for an empty `problems` array rendering a sane "not available" state instead of a bare empty list |
| 7 | Chunk-boundary math (`chunk_count = ceil(len/10)`, slicing) is only tested at 3 and 14 Problems -- exact multiples of the chunk size (10, 20, 30) are untested, where an off-by-one would most likely surface | low | -> patch: add a test at exactly 20 Problems asserting chunk_count == 2 and each chunk's slice has exactly 10, with no trailing empty chunk reachable |
| 8 | `_is_uuid7()` is only tested against a valid UUIDv4 as the negative case; empty string, non-UUID garbage, and an uppercase-hex UUIDv7 are all untested | low | -> patch: add 2-3 cheap parametrized cases; uppercase should still pass (Python's uuid.UUID normalizes case) -- confirm that's the intended behavior via the test |


### Orchestrator's independent review round (2026-09-29)

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 9 | `post_event()`'s idempotent re-fetch on an `IntegrityError` (event id collision) returns whatever row already has that primary key, with NO check that it belongs to the caller's own `session_id`/`profile_id`. A client posting an event id that happens to collide with a DIFFERENT session's event gets back that other event's full content (`session_id`, `kind`, `problem_id`, `occurred_at`, `received_at`) as if it were their own 201 result | high | confirmed independently -> patch: after the IntegrityError re-fetch, verify the existing row's `session_id` matches the caller's `session_id` (and by extension that session's `profile_id`); if it doesn't match, this is a genuine UUID collision across sessions (not a legitimate resend) and must be rejected (409 or 422 with a clear bilingual-equivalent message), never silently returned as a success |
| 10 | `GET /sessions/{id}/bundle` has no `profile_id`/ownership check at all, unlike `POST /sessions/{id}/events` which explicitly 403s on a profile/session mismatch. Anyone who knows (or can guess/observe) a `session_id` can read another child's Problem content, crop/audio URLs and progress state | high | confirmed independently, inconsistent with the events endpoint's own explicit gate -> patch: add a `profile_id` query param to the bundle endpoint and the same ownership check `post_event`/`validate_events_batch` already does (403 on mismatch), and update the frontend (`queries.ts`'s `useSessionBundle`, `SessionPlayer.tsx`) to pass the current profile id |
| 11 | `GET /library/grades/{grade}/books?profile_id=<garbage>` silently returns 0 everywhere instead of 404, inconsistent with the sibling `/library/home/{profile_id}` endpoint which does 404 on an unknown profile | medium | confirmed -> patch: validate `profile_id` the same way `/library/home/{id}` does when the query param is present, 404 `PROFILE_NOT_FOUND` for an unknown one |
| 12 | `learning/progress.py`'s `attempted_lesson_counts()` and `content/library.py`'s `_visible_counts()` are two independently-maintained copies of the same visibility-filtering loop (both iterate `effective.load_effective()` and check `state.visible`) with no shared helper and no test coupling them — the same drift pattern already known from Story 2.3's speech.ts/speech.py | medium | confirmed, currently byte-for-byte equivalent but no regression guard -> patch: add one test that compares `attempted_lesson_counts()`'s denominator against `_visible_counts()`'s count for the same Book/profile and asserts they match, so a future change to one that isn't mirrored in the other is caught |
| 13 | `chunk=0`/negative chunk numbers are rejected by FastAPI's own `Query(ge=1)` before ever reaching `learning/sessions.py`'s own `if chunk < 1: raise AppError(422, "INVALID_CHUNK", ...)` check, making that branch dead/unreachable code through the API; also untested (no test posts `chunk=0` or a negative chunk at all) | low | confirmed -> patch: either remove the now-dead `INVALID_CHUNK` branch (simplest, since `Query(ge=1)` already covers it) or add a test proving the actual current behavior (422 `VALIDATION_ERROR`, not `INVALID_CHUNK`) so the discrepancy is documented rather than silently dead |
| 14 | Matrix row "Start, 0 visible Problems → ... no Session row created" is only checked via the 422 response, never by querying `progress_sessions` directly to confirm zero rows were written | low | -> patch: extend `test_start_zero_visible_problems_422_no_session_created` to also query `progress_sessions` and assert it's empty for that profile |
| 15 | No single test proves all 10 Problems of a full chunk (not just 1) carry the complete bundle shape (child_view + crop/page/audio URLs + attempted) — length and shape are checked by two different, narrower tests | low | -> patch: extend or add a test on a 10+ Problem session asserting every entry in a full chunk has all expected keys, not just the first |
| 16 | A retired/deleted parent Unit or Book (not just a single hard-deleted Problem) after a Session starts is untested; the bundle's `ProblemNotFound` skip path presumably handles it the same way but this is inferred, not verified | low | -> patch: add one test retiring (or hard-deleting) an entire Unit/Book row after Session start and confirming the bundle still degrades gracefully |
| 17 | Concurrent/repeated `POST /sessions` for the same Lesson+profile creates independent duplicate Sessions with no dedup, and this is undocumented (no test, no Implementation Note, no deferred-work.md entry) | low | plausibly intentional (each is a legitimate frozen Session) but undocumented -> patch: add a `deferred-work.md` entry noting this is a known, accepted behavior pending Story 2.5's "unfinished Session" semantics, not a bug |
| 18 | `ref_key()`'s naive string concatenation (`f"lesson:{book_id}:{unit_key}:{lesson_key}"`) could theoretically collide if any component contains a literal `:`; currently dormant since `ref_key` is write-only (never read back this story) | low | -> patch: not urgent, just add a one-line comment on `ref_key()` noting the assumption (book/unit/lesson keys never contain `:`) so a future reader who adds a read-path knows to check it, or add a light validation if cheap |
| 19 | `SessionPlayer.tsx` has no special case for a 404 `SESSION_NOT_FOUND` bundle fetch (garbage/gone session id in the URL) — shows the same generic retry UI forever, which can never succeed | low | -> patch: optional UX nicety — detect `SESSION_NOT_FOUND` and show a message pointing back to the Library instead of an endless retry option; skip if time-constrained, this is not a correctness bug |

## Verification

<!-- Populated after independent re-verification. Append-only. -->

- 2026-09-29 (orchestrator, independent re-verification after fix round): confirmed both critical fixes directly in source (event-id collision now checks `existing.session_id != session_id` before returning it as a success; `get_bundle()` now requires `profile_id` and 403s on mismatch, mirroring the events endpoint). Ran `ruff check` (clean), the full backend suite (769/769 passing), and the full frontend suite via the `/tmp` fast-sync workflow: `tsc -b` clean, `eslint` clean, 185/188 passing (only the 3 pre-existing, already-logged ExtractionPage.test.tsx failures, unrelated to this story). Story marked done.
- Note: this story's own build and fix rounds were carried out with reduced orchestrator supervision (see the incident recorded in the conversation/session record around Story 2.3) — a full independent 3-reviewer pass was run retroactively on top of the story's own self-review before this sign-off, and found 2 high-severity issues (a cross-profile data leak via the event-idempotency re-fetch, and a missing ownership check on the bundle endpoint), both since fixed and verified above.

</frozen-after-approval>
