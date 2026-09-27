---
title: 'Input reconciliation: ARCHITECTURE-SPINE vs PRD + UX'
spine: ../ARCHITECTURE-SPINE.md
inputs:
  - ../../../prds/prd-hoctap-2026-09-26/prd.md
  - ../../../prds/prd-hoctap-2026-09-26/addendum.md
  - ../../../ux-designs/ux-hoctap-2026-09-26/EXPERIENCE.md
  - ../../../ux-designs/ux-hoctap-2026-09-26/DESIGN.md
created: '2026-09-26'
---

# Input reconciliation — Học Tập architecture spine

Scope: requirements and quiet constraints from the PRD and UX that the spine **fails to place**, **contradicts**, or leaves **ambiguous** enough that two independently built units could diverge. The spine was not edited.

Severity: **H** = contradiction or missing rule that will cause divergence or a blocked story; **M** = ambiguity likely to cause divergence; **L** = placement or documentation gap.

## A. Contradictions inside the spine's own rules (exposed by input requirements)

### A1 (H) — Module dependency graph forbids what AD-4 and AD-5 require
- **Inputs:** FR-6 (edits, hide/approve), FR-21 (parent flag hides), UX hidden-Problem state.
- **Spine:** `content.effective_problem()` must apply `review_overrides`; `content.visible_to_child()` must read "hidden in review" and "open parent Error Report". Both live in `review_*`, owned by `parent.review` (AD-2). But the dependency graph has `parent → content`, never `content → parent`, and AD-2 bans raw SQL on another module's tables.
- **Divergence risk:** one implementer has `content` read `review_*` with raw SQL (violates AD-2); another moves the functions into `parent` (then `learning`, which may not import `parent`, can't call the visibility gate); a third duplicates the filter.
- **Resolve:** either move `review_*` ownership into `content` (a `content.review` submodule written only via parent-authorised API calls), or define a read-only port that `content` exposes and `parent` implements (dependency inversion), and draw it.

### A2 (H) — Builder must read review state, but AD-4 says it never reads `review_*`
- **Inputs:** FR-6 "editing any spoken text regenerates its audio"; FR-5 gate accuracy "≥98% of pilot Answer Keys correct when Anh checks them" (UX: spot-check tab marks Đáp án đúng/sai); FR-4 Concept list edited in Content Review.
- **Spine:** AD-8 says "editing text in review creates a new key, and the `speak` stage fills it" — the `speak` stage can only know the edited text by reading effective content (i.e. overrides). AD-7's gate needs the spot-check verdicts, which are review data. AD-4: "The builder never reads or writes `review_*`."
- **Resolve:** state that the builder reads *effective* content only via `content.effective_problem()` (never raw `review_*`), and that gate metrics come from a named service (e.g. `content.spot_check_summary()` / `parent.review` read API) — and fix A1 so that call path is legal. Also say who triggers the audio-regeneration run after an edit (automatic job vs Anh presses "regenerate") given it needs internet (NFR-1).

### A3 (H) — The Parent Area Extraction screen can't reach the builder
- **Inputs:** UX Extraction surface (pilot, full run, progress bar, cost so far, failed pages, Pause/Resume, "Chạy toàn bộ" enabled only after confirmation), FR-5 Anh's recorded approval.
- **Spine:** `api` may import `parent`, `learning`, `content` only; there is no `api → builder` edge, yet the Structural Seed lists an `api/` "build" router and AD-7 requires a `build_gate` record with Anh's approval while AD-2 says `build_*` is written by `builder` only. Diagram 1 shows the builder as "CLI / background job" — undefined which.
- **Divergence risk:** Extraction UI story writes `build_gate` from `parent`; builder story expects CLI-only; Pause/Resume implemented as process kill vs cooperative flag.
- **Resolve:** add `api → builder` (or `parent → builder` control-plane service), define the builder's process model (in-process background task vs separate `hoctap build` worker process sharing SQLite), and name the writer of `build_gate` (builder service called by the API with a parent session). Define Pause semantics with in-flight Message Batches (cancel vs let finish and don't submit more).

### A4 (H) — Child 🚩 Error Report has no legal write path
- **Inputs:** FR-21, UX 🚩 child flag ("Đã báo cho bố mẹ", does not hide).
- **Spine:** `review_error_reports` is written by `parent.review` only; AD-10 says child routes "cannot touch `review_*`"; `learning` cannot import `parent`.
- **Resolve:** allow a narrow `parent.review.report_from_child(problem_id, profile_id)` called by the child router, or give child reports their own table (`progress_flags` owned by learning) that the review list reads. Also distinguish parent vs child reports in the visibility gate (only parent reports hide — AD-5 says "open parent Error Report" but the table has no documented `source` field).

### A5 (H) — Concept list editing vs `content_*` single-writer
- **Inputs:** FR-4 "Anh can edit [the Concept list] in Content Review"; UX Content Review tab **Khái niệm**; FR-6 edit Problem (incl. Concept tags are part of reviewable content); FR-15 every Concept has a Concept Guide with audio.
- **Spine:** `content_concepts`, `content_concept_guides` and the problem↔concept join are `content_*`, builder-only. `review_overrides` is keyed by `problem_id` only, so it can't express renaming/merging/adding a Concept or editing a Concept Guide.
- **Divergence risk:** review story writes `content_concepts` directly; builder re-run overwrites Anh's Concept edits; a new Concept added by Anh has no Guide or audio and FR-4's "every Concept has a Concept Guide" breaks.
- **Resolve:** add a `review_concept_overrides` (or make the Concept list a parent-owned table the builder reads as input); state whether Concept tags live in ProblemDoc (so JSON-patch overrides cover them) or only in the join table; state how a new/edited Concept Guide gets text and audio (builder job).

### A6 (H) — Quiz mode vs "derived state materialised in the same transaction as the Attempt"
- **Inputs:** FR-23 (no marking during play, graded at end; any wrong Part → Retry; all correct → 3 Stars else 0), UX ✔ records "Đã lưu", Quiz results screen.
- **Spine:** AD-6 grades and materialises Stars/Retry per Attempt; AD-9 "a Problem's help is released only by the server's grade response". Nothing says quiz Attempts are stored-but-not-returned, when quiz scoring happens (on last Problem? on an explicit "finish" call?), whether the child may change a quiz answer (append-only log → last Attempt wins?), or how a quiz interrupted mid-way resumes.
- **Resolve:** add a Session `mode` (`practice` | `quiz`) and a `finish_session` endpoint that performs quiz grading/materialisation atomically; define "last Attempt per Part wins" for quiz; define that the grade response in quiz mode is `{"saved": true}` only.

### A7 (H) — Help/reveal events that are not Attempts
- **Inputs:** FR-13 "child can ask for the Hint before answering" (caps Stars at 1, FR-16); FR-11 fallback "Xem đáp án" reveals the Solution with no wrong Attempt; FR-16 Stars 0 if Solution shown.
- **Spine:** AD-6 says Stars are derived from the append-only **Attempt** log and help is released "after the staged-help trigger" (only wrong-Attempt triggers are implied). There's no event type or endpoint for "hint requested" or "solution revealed (fallback)", so Stars can't be derived and the client has no legal way to get Hint/Solution text early.
- **Resolve:** extend the log to `progress_events` (attempt | hint_requested | solution_revealed | self_mark) or add explicit help-request endpoints recorded in the log; fallback self-mark ("Em làm đúng/chưa đúng") is an Attempt whose grade is client-asserted — say so.

## B. Requirements the spine does not place

### B1 (H) — Session identity, splitting and kinds
- **Inputs:** FR-8 split >10 Problems into Sessions ≤10; UX "Phần 1/2", Assignment done only when every part done, progress dots per Session; FR-17 "2 separate Sessions of any kind"; UX "Luyện lại bài sai" replay earns no Stars and doesn't count toward leaving the Retry Queue; FR-15/FR-20 Concept practice sets; Retry Session; "Tiếp tục" resumes at the same Problem (NFR-7); UX "Học tiếp" = next unfinished Lesson in Book order.
- **Spine:** "Session split" is mapped to `learning/sessions` with no rule. Not defined: how chunks are computed (fixed at Lesson level from extraction order, or recomputed over *visible* Problems — hiding a Problem would renumber parts and break a half-done Assignment), what a Problem Set reference is (`lesson:{id}` / `concept:{id}` / `retry` / `replay:{session_id}`), how Concept practice sets are composed (which Problems, how many, order, seeded?), the Session kinds and which kinds earn Stars / count for Retry exit / count for Streak, and what "completed" means for an Assignment whose Problem Set is a Concept set.
- **Resolve:** add an AD for `ProblemSetRef` + deterministic chunking (snapshot the chunk membership when the Session is created) + a `session.kind` enum with a scoring/counting matrix.

### B2 (M) — UI speech (non-content audio) has no producer
- **Inputs:** FR-8 every Home card has a 🔊 label; UX praise lines (~6 variants), "Chưa đúng, em thử lại nhé!", "Mình cùng xem cách làm nhé", "Em đã hoàn thành bài! Em được 22 ngôi sao" (dynamic number), badge names and "how to earn" 🔊 for locked badges, empty-state and "not connected" screens with 🔊; feedback sounds (chime, boop, fanfare).
- **Spine:** AD-8 covers only content strings via the builder's `speak` stage. Dynamic phrases (numbers of stars, streak days, "Tuần 3 – Tiết 2" card titles) and UI phrases need a catalogue, a build step, and either composition from fragments or pre-generation. The "not connected" audio must be precached in the app shell (it plays exactly when the server is unreachable).
- **Resolve:** add a UI phrase catalogue (`frontend/src/audio/phrases` or `content/ui_phrases`) spoken through the same `speech_text()`/TTS path at build time, shipped in the precached app shell; decide how numbers are spoken (concatenated number clips vs per-value generation).

### B3 (M) — Backup/restore semantics
- **Inputs:** NFR-7 single-file export and restore; UX Settings "Sao lưu" (download) and "Khôi phục" (upload, confirm, replace).
- **Spine:** `parent/backup` uses the SQLite online backup API; restore is unspecified: replacing a live WAL DB under a running Uvicorn (close engine, swap file, reopen?), Alembic version mismatch in an older backup (auto-upgrade vs refuse), what happens to tablets' IndexedDB outboxes holding Attempts for a restored-over timeline (idempotent UUIDs would re-insert them), whether PIN hash and parent sessions are restored/invalidated, and a DB whose `speech_key`s/crops aren't on disk (assets not backed up — Deferred) → UX says greyed 🔊, OK, but crops for Problems would be missing too.
- **Resolve:** add a restore procedure rule (maintenance mode, migrate-on-restore, invalidate all cookies, bump a `data_epoch` that clients check before flushing their outbox).

### B4 (M) — Badge catalogue and rules
- **Inputs:** FR-16 milestone badges ("Hoàn thành Tuần 1", "7 ngày liên tiếp"); UX badges gallery with locked badges and 🔊 "how to earn", latest 3 on Home, pop-in on summary.
- **Spine:** `learning/badges`, `progress_badges` only. No badge definition source (code constant vs table), no trigger point (per Attempt vs Session end), no rule for content-derived badges across Editions ("Tuần 1" exists only in 2020 books; what's the 2024-25 equivalent?), hidden Problems' effect on "Hoàn thành", or revocation (never?).
- **Resolve:** a code-defined badge registry with ids, criteria and phrase keys (feeds B2); evaluate at Session completion; never revoked.

### B5 (M) — First-run setup and PIN bootstrap
- **Inputs:** UX First-run setup (no profiles → create PIN, then first Child Profile), 4-digit PIN, 🔒 long-press on tablet Home.
- **Spine:** AD-10 covers the cookie after the PIN but not the unauthenticated "set PIN when none exists" endpoint (must be one-shot and refuse once set), nor PIN reset if forgotten (CLI?), attempt throttling for a 4-digit PIN on a device the child holds, or ending the parent cookie when leaving the Parent Area on the shared tablet (30-min idle leaves it open for the child).
- **Resolve:** add bootstrap/lockout/logout-on-exit rules to AD-10; `hoctap reset-pin` CLI for recovery.

### B6 (M) — Offline/precache scope and NFR-4 thresholds
- **Inputs:** NFR-1 (no internet needed), NFR-4 (Problem <1 s, audio start <0.5 s on LAN), UX feedback sound then Hint speech after ~400 ms, UX "server unreachable" keeps current-Problem progress and syncs later.
- **Spine:** AD-9 precaches "crop and audio URLs" of the bundle but is silent on whether Hint/Solution audio is precached (their text is withheld until grade; the audio URL is a content hash so it leaks nothing readable, but the bundle would need to list it). If not precached, the Hint audio path is grade round-trip + fetch, which competes with the 0.5 s budget and fails when the LAN drops between grade and fetch. No perf budget/test is set for NFR-4 (tests row lists none).
- **Resolve:** state the precache set explicitly (instruction, Part, option, Hint, Solution audio + crops + app shell + fonts + KaTeX + UI phrases); add a Playwright timing check for NFR-4 on a LAN profile.

### B7 (M) — Maths rendering: KaTeX vs DESIGN typography
- **Inputs:** DESIGN "Maths overlines use CSS `text-decoration: overline` in the same font (Nunito)"; answer digits in Nunito 40/800; child text ≥18 px.
- **Spine:** "The frontend renders it with KaTeX." KaTeX uses its own fonts, so overlined numbers and `\frac` would render in KaTeX_Main, not Nunito, and widgets vs print renderer may pick differently. KaTeX fonts also need self-hosting/precaching for offline.
- **Resolve:** one `MathText` component used by widgets and print: Nunito + CSS overline for `\overline`, `<`, `>`, `=`, `\times`, `:`; KaTeX (self-hosted) only for `\frac` (or a CSS stacked fraction). Name it in conventions.

### B8 (L) — Nunito self-hosting
- **Inputs:** DESIGN "self-hosted, so it works offline", full Vietnamese diacritics.
- **Spine:** not mentioned; nothing stops a Google Fonts link (would break offline and NFR-6 "nothing sent outside").
- **Resolve:** convention row: fonts bundled in `frontend/` (Vietnamese + Latin subsets, weights 500/600/700/800), precached; no external requests from the frontend (CSP `default-src 'self'`).

### B9 (L) — Reduce motion
- **Inputs:** UX Accessibility Floor: no shake, no flying stars, no confetti; sounds remain.
- **Spine:** not placed. Ambiguous whether it's the OS `prefers-reduced-motion` only or also a per-profile setting (Settings lists only auto-play).
- **Resolve:** convention: honour `prefers-reduced-motion` via one shared motion utility; no per-profile toggle in v1 (or add it to profile settings if wanted).

### B10 (M) — Printing details
- **Inputs:** FR-22 any Problem Set, A4, answer page; `match` dots; UX Print CSS black-and-white-safe; UJ-3 "Tuần 4" (a whole Unit, not a Lesson — so Problem Set includes Unit?).
- **Spine:** `frontend/print` + AD-1 print renderer per type. Not stated: which endpoint provides keys (parent-only, since AD-6 keeps keys off child clients), whether hidden/`needs_review` Problems are excluded (visibility gate applies to child queries only), whether split Sessions matter (print whole Lesson), how `fallback` prints (page crop), and whether a Unit is a printable Problem Set (UJ-3/Flow 3 print from a Unit).
- **Resolve:** a parent `GET /api/v1/parent/print/{problem_set_ref}` returning effective content + keys, filtered by the visibility gate; extend `ProblemSetRef` to units if UJ-3 means it.

### B11 (M) — Cost reporting and the gate report
- **Inputs:** FR-5 per-page status, failures, pages/minute, API cost so far, full-run cost estimate; gate checks fallback ≤15%, ≥98% keys correct, cost accepted; UX: failing report lists "which layouts failed".
- **Spine:** `build_costs` per batch in Logging; `build_gate` approval. Not defined: how cost is computed (usage tokens × price table in config; batch discount), estimate formula (per-page mean × remaining pages, by grade?), where fallback share is measured (per pilot Problem, per Part?), what "layout" is recorded for the failure list, and pages/minute under Batches API (asynchronous, up to 24 h — pilot may want the synchronous API for turnaround).
- **Resolve:** a gate/report service with named metrics and formulas; allow `sync` vs `batch` transport per run (pilot sync, full run batch).

### B12 (M) — Spot-check sampling
- **Inputs:** UX Content Review "Kiểm tra ngẫu nhiên" for both FR-5 (pilot) and SM-3 (random 100 Problems).
- **Spine:** not placed. Sample population (pilot Problems vs all; include `needs_review`?), sample reproducibility (stored sample id/seed), and per-Part vs per-Problem verdicts are open; the gate reads this (A2).
- **Resolve:** `review_spot_checks(sample_id, problem_id, verdict)` with a stored sample; define accuracy = correct / checked over Problems.

### B13 (L) — Dashboard metrics definitions
- **Inputs:** FR-19 time per day/week, first-try accuracy (excludes fallback), weakest Concepts (≥5 Attempts), recent mistakes with child answer vs correct.
- **Spine:** not defined how "time" is measured (Session start→finish, sum of active intervals?), whether "first try" is per Part or per Problem, and whether ≥5 counts Attempts or first Attempts. Library "5/8 ✓" — "done" means attempted, correct, or completed-in-a-Session?
- **Resolve:** a short metric-definition table in `learning` owned by one module; dashboard only reads it.

### B14 (L) — Misc placement
- Auto-play-audio per profile (FR-10) — stored in `progress_profiles`? Profiles are learning-owned but edited by parent: say parent calls `learning.profiles` service.
- "Học tiếp" next unfinished Lesson "in Book order" — with two Editions per Grade, which Book comes first? (Config or catalogue order.)
- Multiple Assignments on the same date / carry-over stacking — one card or several?
- Grade 4–5 comma key and `3,5 = 3.5` normalisation (FR-12) — grader rule is a per-profile Grade or per-Book Grade?
- AD-11 plain-HTTP degraded mode has no service worker → no Session bundle precache; confirm the outbox still works (IndexedDB is fine on http) and the "not connected" screen still appears.
- Visibility changing mid-Session (Anh hides a Problem after the bundle was fetched): server rejects Attempts with a code, client skips?

## C. Items checked and found adequately placed
- Stable Problem identity and re-extraction upserts (AD-3); retire-not-delete.
- Server-only grading and key withholding (AD-6) for normal practice.
- Calendar-day time zone for Streak/Retry/Assignment (Conventions).
- Single shared AudioPlayer, stop on new clip/navigation, iOS unlock (Conventions) — matches UX "one voice at a time". The ~400 ms feedback-sound-then-Hint sequencing is not stated but is a single-component concern.
- Missing clip → greyed 🔊 (UX) is compatible with content-addressed audio (AD-8).
- LAN-only, PIN cookie (AD-10); HTTPS for PWA (AD-11); one origin (AD-12).
- `needs_review` hide rule and child 🚩 not hiding (AD-5).
