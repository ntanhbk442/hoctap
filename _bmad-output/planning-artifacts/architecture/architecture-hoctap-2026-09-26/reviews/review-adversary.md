---
title: 'Adversarial review: Học Tập architecture spine'
reviews: ../ARCHITECTURE-SPINE.md
against: ../../../prds/prd-hoctap-2026-09-26/prd.md
lens: 'Build two units one level down that obey every AD word for word but still don't fit together'
date: 2026-09-26
---

# Adversarial review: Học Tập architecture spine

## Verdict

The spine gets the big splits right: builder vs app, table ownership by prefix, a server-authoritative Attempt log, and one visibility gate. It still leaves at least eleven seams where two teams could follow every AD exactly and ship parts that don't fit together. Two of them are critical: the override addressing and the audio for review edits. In both, the AD rules together make the behaviour the PRD requires impossible to build without breaking one of those rules.

Severity scale: **Critical** means the PRD behaviour can't be built without breaking an AD, or data gets corrupted silently. **High** means units will diverge and the mismatch surfaces as wrong child-facing behaviour or wrong metrics. **Medium** means an integration bug that is likely but can be recovered. **Low** means a missing convention.

---

## H1 — Critical: Override patches point at array positions that re-extraction reorders

**Units:** Content Review (`parent.review`) vs extraction pipeline (`builder` validate/publish), with Grading (`learning`) as a third party.

**How they diverge while obeying the ADs:**
- AD-4 says an override is "a JSON patch over ProblemDoc" keyed by `problem_id`. RFC 6902 JSON Patch addresses array elements by index (`/parts/1/answer_key`).
- The review unit does exactly that. Anh fixes Part b's Answer Key, which stores `replace /parts/1/answer_key`.
- The builder re-extracts the page (AD-3: upsert by `problem_id`, which is allowed). This time Claude emits the Parts in a different order, or splits Part a into two. Nothing in AD-1 or AD-3 makes Part identity stable. Only `problem_id` is stable.
- `content.effective_problem()` applies the patch as written. Anh's fix now lands on the wrong Part, or the patch fails. Either way the PRD's "edits are kept" (FR-6) is broken, and the child is graded against a wrong key.
- `learning` stores Attempts "per Part" (Glossary: an Attempt is an answer to a Part) under whatever Part reference it picked, such as an index or a label. After the re-extraction the Retry Queue exit rule ("every Part answered correctly on first try", FR-17) and the dashboard's "child's answer vs the correct one" (FR-19) join to the wrong Part.
- FR-6 also lets Anh change a Part's **Problem Type**. The widget unit and the grader unit then read Attempt payloads whose shape doesn't match the current type.

**Minimal fix (tighten AD-3 and AD-4):**
- Every `Part` has a stable `part_key`: the book's label (`a`, `b`, …), or `p1` when there is none. Every `AnswerSlot` has a stable `slot_key` within its Part. Attempts reference `(problem_id, part_key)`.
- An override is **field-level and keyed**: `(problem_id, part_key|null, field) → value`. Positional JSON Patch is not allowed.
- Every override records the `base_hash` of the extracted ProblemDoc it was written against. When a re-publish changes that hash, the Problem goes into the review list with "override conflict". Until Anh resolves it, the override still applies if its keys still resolve. If they don't resolve, the Problem is hidden through AD-5.
- Every Attempt stores the `problem_type` and `content_hash` in force when it was graded, so its history can still be read after the type is edited.

## H2 — Critical: No legal path from a review edit to new audio

**Units:** Content Review (`parent.review`) vs speech (`builder.speech`, `speak` stage) vs Session bundle (`learning.sessions` via `content`).

**How they diverge while obeying the ADs:**
- AD-8 says editing text in review "creates a new key, and the `speak` stage fills it". But:
  - AD-4: the builder "never reads or writes `review_*`". The `speak` stage therefore can't see the edited text.
  - AD-7 keys jobs by `(page_ref, stage, input_hash)`. An override isn't a page, so no job exists to rerun.
  - The dependency graph has no `parent → builder` or `content → builder` edge. `speech_text()` sits in `builder.speech`, so neither review nor `content.effective_problem()` may call it to compute the new `speech_key`.
- So one team puts a copy of the normaliser into `content` to compute keys for the bundle, and another reads keys stored by the builder in `content_*` rows. Both paths follow the ADs. They disagree on every edited string, and they will drift on unedited ones as soon as the normaliser changes (AD-8 was meant to prevent exactly that).
- The builder needs internet; the app may be offline (NFR-1). The spine doesn't say what the player does when an edited string's audio file doesn't exist yet. It could play nothing, play the stale key, or break NFR-4.

**Minimal fix (tighten AD-8, adjust dependency graph):**
- Move `speech_text()` and `speech_key()` to `content.speech`. This is pure code with no I/O, so both `builder` and `content` may use it.
- `content.effective_problem()` returns each spoken field together with its `speech_key`, computed on read. The bundle never takes keys from anywhere else.
- Add a `speak` input that is not page-based: the builder stage `speak-missing` scans `content.all_effective_speech_keys()` (a read of a `content` service, which the builder may already import) and synthesises any keys that are missing. It never touches `review_*` directly.
- Player rule: when an audio file is missing, it hides the 🔊 for that string and logs `audio_missing`. It never plays an older key.

## H3 — High: The visibility gate reads data that it may neither import nor query

**Units:** Content Review / Error Reports (`parent.review`) vs visibility gate (`content.visible_to_child`) vs child 🚩 (`api/child` + frontend player).

**How they diverge while obeying the ADs:**
- AD-5 bases `visible_to_child()` in `content` on "hidden in review" and "open parent Error Report". That state lives in `review_*` (AD-2).
- AD-2 says other modules read through the owning module's service functions, not with raw SQL. The graph forbids `content → parent`. So `content` can neither call `parent.review` nor query `review_*`. AD-4 has the same problem: `effective_problem()` must read `review_overrides`.
- Team A has `visible_to_child()` run raw SQL on `review_*`. Team B keeps a `hidden` column in `content_problems` and has review write it. Both break some rule, but each can quote one AD to justify itself, and each stores hidden state somewhere different.
- `needs_review` is set by the builder in `content_*` (AD-7). FR-6 says **approving** a Problem makes it visible, but review can't write `content_*`. One team stores approval as `review_overrides {needs_review:false}`; another adds `review_approvals`. After a re-verify, is the approval still valid? That isn't defined.
- AD-10 says child routes "cannot touch `review_*`", but FR-21 has the child's 🚩 send an Error Report to the parent. The child team stores the flag in `progress_flags`. The parent team's review list reads only `review_error_reports`, so the parent never sees child flags.

**Minimal fix (tighten AD-2, AD-5, AD-10):**
- State in AD-2 that `review_*` is a **content-layer overlay**. The table *writer* is `parent.review`. The only *readers* are `content.effective_problem()` and `content.visible_to_child()`, which use a read-only repository in `content/overlay.py`. This is the one allowed cross-prefix read.
- Define one review status per Problem in `review_problem_status(problem_id, state ∈ {auto, approved, hidden}, approved_content_hash)`. The gate rule: visible iff not retired AND no open parent report AND state≠hidden AND (not needs_review OR (state=approved AND approved_content_hash = current extracted hash)).
- The child 🚩 goes through `POST /api/v1/child/problems/{id}/flag`, which calls the service `parent.review.submit_child_report()`. It writes `review_error_reports(source='child')`, which never affects visibility. This is the one child-route exception, and AD-10 names it.

## H4 — High: Help requests, reveals and self-marks are not in the append-only log, yet Stars depend on them

**Units:** Problem player widgets and the fallback widget (frontend) vs grading/learning (`learning.stars`, `learning.retry`) vs quiz mode.

**How they diverge while obeying the ADs:**
- AD-6 says `progress_attempts` is the only source of truth and that Stars are derived from it. But the Stars rule (FR-16) depends on "needed a Hint" (which includes a Hint *requested before answering*, FR-13) and "Solution shown". Neither of those is an Attempt.
- The widget team calls `POST /hint`, which releases the Hint (AD-6 lets the server release it), and doesn't record it. The Stars team derives 3 Stars. Another team writes `progress_help_events`. Rebuilding from `progress_attempts` alone then gives a different Star total, which breaks AD-6's own "no drift" goal.
- Fallback (FR-11): the child taps "Xem đáp án" **before** any Attempt. AD-6 says Solutions are released only "after the staged-help trigger", and that trigger is defined only as wrong Attempts. So the fallback team either sends a fake wrong Attempt, which puts the Problem in the Retry Queue by mistake (FR-17), or ships the Solution in the bundle, which breaks AD-6.
- Quiz mode (FR-23): "no marking during play". AD-9 has help released by the server's grade response per Attempt. The quiz team holds answers on the client and submits them at the end; the learning team grades as they arrive and puts the first wrong one in the Retry Queue with a Hint. Stars differ (3/0 in a quiz vs 3/1/0 normally).

**Minimal fix (tighten AD-6):**
- Replace the Attempt-only log with an append-only `progress_events` log. Its event types are `attempt`, `hint_requested`, `solution_revealed`, `self_mark` and `session_completed`, each with a client UUIDv7 and a `session_id`.
- Every derivation (Stars, Retry Queue, Streak, badges, Assignment status) is a pure function of the ordered events for the Session.
- `Session.mode ∈ {practice, quiz, retry, concept}` is fixed when the Session starts. In quiz mode the grader records a grade but sends back only `accepted`, and there is no help release. Grades are released at `session_completed`.
- For a fallback Problem, `solution_revealed` is allowed with no Attempt before it.

## H5 — High: "Problem Set" has no identity or composition rule

**Units:** Assignments (`learning.assignments` + parent UI) vs Sessions/Library (`learning.sessions`) vs printing (`frontend/print`) vs Concept Guide "Luyện tập".

**How they diverge while obeying the ADs:**
- The Glossary defines a Problem Set as a Lesson, a parent-built set, a Retry Queue set or a Concept practice set. The ER diagram has **no problem-set entity**, and no AD says how a set is referenced or put together.
- The Assignments team stores `assignment.target = lesson_id`. The print team takes `problem_ids[]` from the page it's on. The Concept Guide "Luyện tập" button builds its set by picking 10 random visible Problems for the Concept. Assigning "a Concept practice set" (FR-20) then gives a different set each day, and the dashboard's Assignment status can't be reproduced.
- FR-8 splits Lessons of more than 10 Problems into Sessions. Chunks are computed from the *visible* Problems (AD-5). If Anh hides a Problem between chunk 1 and chunk 2, the chunk boundaries move. "Done when all Sessions of its Problem Set are completed" (FR-20) now counts different chunks, so the Assignment either never completes or completes too early.
- The Session summary's "Luyện lại bài sai" (FR-14) and the Home "Luyện lại" card (FR-8) are both "retry sets" with different membership rules. Nothing names which one is which.

**Minimal fix (new AD-13, Problem Set reference):**
- One tagged union `ProblemSetRef = lesson{lesson_id} | concept{concept_id, seed} | retry{profile_id, as_of_day} | custom{set_id}` in `learning/problem_sets.py`, plus one resolver `resolve(ref) → ordered problem_ids`. Assignments, sessions, print and summary all use this resolver.
- When a Session starts, its resolved `problem_ids` and chunk index are frozen in `progress_sessions`. An Assignment is complete when every chunk that was frozen at assignment start is completed. A Problem that is hidden later is skipped, but it doesn't reopen the chunk.

## H6 — High: Concepts have neither a stable ID nor a legal editor

**Units:** Extraction/tagging (builder, FR-4) vs Content Review concept editing (FR-4 "Anh can edit it in Content Review") vs parent dashboard weakest-Concept ranking.

**How they diverge while obeying the ADs:**
- `content_concepts` and `content_concept_guides` are `content_*`, so only the builder writes them (AD-2). AD-4's overrides are keyed by `problem_id`, so a Concept list edit, a Concept rename or a Concept Guide text fix has nowhere legal to live. One team adds `review_concepts` as a shadow list. Another re-runs the builder with an edited seed file.
- AD-3 gives stable IDs to Problems only. A pilot re-run re-proposes the Concept list (FR-4, FR-5 "re-run the pilot"). If Concept IDs are slugs made by the model, "So sánh số" becomes `so-sanh-so-pv10` and history splits. The FR-19 ranking and SM-4 (week 1 vs week 4 on the weakest Concept) break silently.
- FR-4 says Concepts are shared across Editions. The builder runs per Book, so two runs can mint two IDs for the same Concept.

**Minimal fix (extend AD-3 and AD-4):**
- The Concept list per Grade is a **curated input file** (`content/concepts/grade{n}.toml`) with stable `concept_id`s. The pilot proposes it, Anh approves it, and the builder loads it and never makes up a new one. Tagging must choose from that list, and an unknown tag counts as a validation failure.
- A Concept Guide's text follows the same rule as a Problem: it gets field-level overrides keyed by `(concept_id, field)` in `review_overrides`, and `content.effective_concept_guide()` is the only reader.

## H7 — Medium: The "ProblemDoc without keys" projection is never defined

**Units:** child Session bundle / widgets vs print renderer vs Content Review editor.

**How they diverge:**
- AD-1 has *one* ProblemDoc model, with TS types generated from OpenAPI. AD-6/AD-9 say the bundle carries "ProblemDocs without keys".
- One team makes `answer_key`, `hint` and `solution` Optional and sets them to null. Another uses `response_model_exclude`. A third defines `ProblemDocPublic`. The widget team codes against whatever generated type it sees, which may contain `answer_key?`. A later refactor that forgets to null one field leaks keys to the tablet.
- The print unit (FR-22 needs an answer page) and review both need the full doc. Nothing says which endpoint gives it or who is allowed to call it.

**Minimal fix (tighten AD-1):** Define exactly two projections in `content/schema.py`: `ChildProblemView` (structurally has no key, hint or solution fields) and `ParentProblemView` (full effective doc). Child routes may return only `ChildProblemView`. Hints and Solutions come only from `learning` release endpoints. Print and review use `ParentProblemView` under `/api/v1/parent/*`. Add a contract test that fails if a child OpenAPI schema contains `answer_key`, `hint` or `solution`.

## H8 — Medium: Calendar days for Attempts that are delivered late through the outbox

**Units:** PWA outbox (AD-9) vs Streak/Retry/Assignment day logic (`learning`) vs dashboard "time per day" (`parent`).

**How they diverge:** The spine fixes the time zone but not *which timestamp* sets the day. Suppose an Attempt is made at 23:55 and delivered at 00:10. If Streak uses server `received_at`, a day is lost. The dashboard uses the client `answered_at`, so the two disagree. The Retry "next calendar day" rule counts from yet another value.

**Minimal fix (Consistency Conventions):** Every event carries the client `occurred_at` and the server `received_at`. Day bucketing uses `occurred_at`, clamped to [session_start, received_at], in the home time zone, and goes only through `learning.calendar_day(event)`. The dashboard reads the days that `learning` derived and never recomputes them.

## H9 — Medium: Partial re-extraction and cross-page Problems against "retire if no longer found"

**Units:** extraction (`extract`, per page) vs publish/retire (`publish`).

**How they diverge:** FR-2 allows extraction on "chosen pages", and AD-7 keys jobs by `page_ref`. AD-3 retires "a Problem that is no longer found". If publish compares against the whole Book, re-extracting page 12 retires everything else. If it compares against page 12 only, a Problem merged from pages 12–13 (FR-2) is upserted with only the part on page 12.

**Minimal fix (tighten AD-3/AD-7):** The unit of extraction, merging and retiring is the **Lesson page-span** (all pages of a Lesson). Choosing any page means its whole Lesson is processed. A Problem is retired only when its Lesson was fully reprocessed and the Problem was absent from it.

## H10 — Medium: Backup/restore against single-writer ownership and a builder running at the same time

**Units:** backup/restore (`parent/backup`) vs builder (`content_*`, `build_*` writer) vs learning.

**How they diverge:** A restore replaces every table, so `parent` becomes a writer of `content_*`, `build_*` and `progress_*`, against AD-2. If the builder CLI is running in a separate process while a backup is taken or a restore is applied, the result is a mixed state. Restoring an older DB file can also bring back an older Alembic revision, or `content_*` rows whose speech keys and crops don't match the assets on disk. Assets are not backed up (see Deferred).

**Minimal fix (AD-2 addendum):** Backup and restore are a named **maintenance operation**, not a module write. They hold an exclusive app-wide lock and refuse to run while any `build_jobs` row is `running`. A restore checks the Alembic revision (migrate forward, never backward). Afterwards it runs `speak-missing` and a crop check, and lists any missing assets in the review list.

## H11 — Low: Missing owners and duplicated metric definitions

- **PIN hash, per-profile auto-play switch (FR-10) and other settings:** AD-2 has no prefix for them. One team adds `parent_settings`, another adds columns to `progress_profiles`. **Fix:** add `settings_*`, owned by `parent`, read by `learning` and `api` through `parent.settings` services, and allow the `learning → parent.settings` edge. The other option is to put profile settings in `progress_profiles`, owned by `learning`, with `parent` writing them through `learning.profiles`. Pick one.
- **First-try accuracy:** it could be counted per Part or per Problem, and it excludes fallback (FR-11) and possibly quiz. The parent dashboard and the Session summary (FR-14) will each compute it their own way. **Fix:** one function, `learning.metrics.first_try()`, whose unit (the Problem) and exclusions (fallback, self-mark) are stated in the AD.
- **Publishing while the app is serving:** a bundle fetched while a publish is in progress may mix Problem versions. **Fix:** the builder publishes each Lesson in one transaction, and a Session's bundle freezes the `content_hash` of each Problem (see H5).

---

## Summary table

| # | Severity | Units in conflict | AD fix |
| --- | --- | --- | --- |
| H1 | Critical | review vs builder vs learning | Stable `part_key`/`slot_key`; field-level keyed overrides with `base_hash` conflict detection |
| H2 | Critical | review vs builder.speech vs bundle | Move `speech_text/key` to `content.speech`; `speak-missing` stage; missing-audio rule |
| H3 | High | review vs content gate vs child 🚩 | `review_*` declared as content overlay readable only by `content`; single `review_problem_status`; child flag via `parent.review` service |
| H4 | High | widgets/fallback/quiz vs learning | `progress_events` log with hint/reveal/self-mark events; `Session.mode` |
| H5 | High | assignments vs sessions vs print | New AD-13: `ProblemSetRef` + one resolver; Session freezes its problem list and chunk |
| H6 | High | builder tagging vs review vs dashboard | Curated stable `concept_id` list; Concept Guide overrides |
| H7 | Medium | bundle vs print vs review | `ChildProblemView` / `ParentProblemView` + contract test |
| H8 | Medium | outbox vs streak vs dashboard | `occurred_at` + `received_at`; one `calendar_day()` |
| H9 | Medium | extract vs publish/retire | Lesson page-span as the unit of extraction, merge and retire |
| H10 | Medium | backup vs builder vs ownership | Backup/restore as locked maintenance op with revision check |
| H11 | Low | settings, metrics, publish timing | `settings_*` owner; `learning.metrics.first_try()`; per-Lesson publish transaction |
