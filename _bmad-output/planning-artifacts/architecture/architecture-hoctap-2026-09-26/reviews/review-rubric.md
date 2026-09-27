# Rubric Walker Review — Học Tập Architecture Spine

- **Target:** `../ARCHITECTURE-SPINE.md` (status: draft, altitude: initiative, Fast path)
- **Lens:** Good-spine checklist (`bmad-architecture/references/reviewer-gate.md`)
- **Also read:** `.memlog.md`, PRD `prd.md` §4 (FR-1..FR-23), NFR-1..NFR-7, PRD addendum
- **Date:** 2026-09-26

## Verdict

A strong, well-shaped spine (clear paradigm, real divergence points, operational envelope present), but the ownership rules around the `review_*` seam contradict each other — as written, `content.effective_problem()`, `content.visible_to_child()`, the child's 🚩 report and the audio re-speak for review edits each cannot be built without breaking AD-2, AD-4, AD-10 or the dependency diagram. Fix that seam before handoff; the rest is medium/low polish.

## Checklist walk

| Checklist item | Result | Notes |
| --- | --- | --- |
| Fixes the real divergence points, misses none | Mostly | Content contract, identity, table ownership, grading authority, speech keys, visibility gate are exactly the right calls. Missed: Part identity (F4), `needs_review` vs approve precedence (F5), content-version pinning of Attempts (F4). |
| Every AD's Rule enforceable and actually prevents its divergence | **No, for AD-2/AD-4/AD-5/AD-10 together** | Rules contradict each other at the review seam (F1, F2, F3). |
| Nothing under Deferred could let two units diverge | Yes, mostly | TTS engine, model, prompt wording are safely behind adapters/single model. "ProblemDoc field details" is deferred but single-sourced by AD-1, so acceptable. |
| Named tech verified-current | Mostly | Memlog records a 2026-09-26 PyPI/npm check for pinned versions. Unpinned: `anthropic` ("latest 0.x"), KaTeX ("latest"), mkcert ("latest"); OpenAPI→TS generator unnamed. Model id `claude-opus-5` and `output_config.format`/adaptive thinking on Batches were not captured as a `version` memlog entry (F7). Not re-verified by this reviewer. |
| Ratifies brownfield | N/A | Greenfield (only `Sach_Arch/` PDFs exist). |
| Covers the driving spec's capabilities | Mostly | Capability map covers FR-1..FR-23 and NFRs. Gaps: FR-4 Concept list editing in Content Review (content_concepts is builder-only, overrides cover Problems only) (F6); FR-21 child flag (F2); NFR-7 "restore" half (F6). |
| Inherited parent spine not weakened | N/A | No parent spine. |
| Every owned dimension decided / deferred / open — incl. operational envelope | Mostly | Deployment, environments, networking, TLS, config, logging, backup are present. Silent: WSL2 lifecycle (idle shutdown) and how the builder is triggered/scheduled vs the running app; LAN IP stability for the mkcert cert and `hoctap.local` name resolution; restore procedure vs Alembic revision (F6). |

## Findings

### F1 — HIGH — AD-2 / AD-4 / AD-5 vs dependency diagram: `content` must read `review_*` but has no legal path

- AD-4: effective content = extracted ⊕ `review_overrides`, computed **only** by `content.effective_problem()`.
- AD-5: `content.visible_to_child()` must know "hidden in review" and "open parent Error Report" — both live in `review_*`.
- AD-2: `review_*` has one writer, `parent.review`; "other modules read through the owning module's service functions, not with raw SQL."
- Dependency diagram: `parent → content` is allowed; `content → parent` is forbidden (content may only import `db`).

So `content` can neither call `parent.review` (layer violation) nor read `review_*` with raw SQL (AD-2 violation). Independent builders will resolve this differently (raw SQL in content, moving review tables under content, or putting the gate in `parent`) — exactly the divergence the spine exists to prevent.

**Fix options (discuss):** (a) move review ownership down: `review_*` owned and written by a `content.review` submodule, with `parent` only calling its services; or (b) keep `parent.review` as writer but carve an explicit AD-2 exception: `content` may read `review_*` directly (read-only) for `effective_problem`/`visible_to_child`. Option (a) is cleaner and also solves F2/F3.

### F2 — HIGH — AD-2 / AD-10 vs FR-21: the child's 🚩 has nowhere to be written

FR-21 lets the child flag a Problem, sending a report to the parent. Error Reports are `review_error_reports` (ER diagram), writable only by `parent.review` (AD-2), and AD-10 says child routes "cannot touch `review_*`". The PIN-gated parent module cannot be the path for an un-PINned child action without a rule saying so. Builders will either break AD-10 or invent a separate child-flag table.

**Fix (autofix once F1 is decided):** state that child flags are written via one named service (e.g. `content.review.report_error(source="child")` or a `progress_flags` table owned by `learning` that the review list reads), and that a child report never affects visibility (already in AD-5).

### F3 — HIGH — AD-4 / AD-8: audio for review-edited text cannot be produced under the rules

AD-8: "Editing text in review creates a new key, and the `speak` stage fills it." But AD-4: "The builder never reads or writes `review_*`", and the builder's stages operate on extracted pages. To speak edited text the builder must read effective content (i.e. `review_overrides`), directly or via `content.effective_problem()` — the latter just relocates the F1 problem. Also unstated: what triggers this (Content Review is in the runtime app, which is offline-first and has no builder in-process — yet `api/` has a `build` router, see F5), and what the player does while the new `speech_key` has no file yet (NFR-1/NFR-3: every string has audio).

**Fix (discuss):** add a rule: the `speak` stage enumerates missing `speech_key`s from `content.effective_problem()` over all problems (builder reads effective content, never writes `review_*`); name the trigger (review save enqueues a `build_jobs` speak record; builder run picks it up); define the missing-audio fallback (hide 🔊 / play previous key until regenerated).

### F4 — MEDIUM — AD-3 / AD-6: Part identity and content version are not pinned

AD-3 stabilises `problem_id`, but Attempts, grading (FR-12 per Part), staged help (FR-13 per Part) and Retry exit ("every Part correct on first try", FR-17) are per **Part**. A re-extraction or a Content Review edit can reorder, add or drop Parts or change an Answer Key. Nothing says how a Part is identified (index? label?) or which content version an Attempt was graded against. Two units (grader vs dashboard "recent mistakes with correct answer", FR-19) will disagree after an edit, and a Session bundle cached in the client (AD-9) may submit answers against stale Parts.

**Fix (autofix):** add to AD-3: `part_key` stable within a Problem (from printed label, else ordinal fixed at first publish); Attempts store `problem_id`, `part_key` and `content_hash` of the effective ProblemDoc used; the server grades against current effective content and rejects/flags a mismatched hash.

### F5 — MEDIUM — AD-5 / AD-4: `needs_review` vs parent "approve" precedence undefined; dependency diagram omits `api → builder`

- FR-6: "Approving a hidden Problem makes it visible" — including `needs_review` ones. AD-5 requires "not `needs_review`" (a builder-owned `content_*` flag) AND "not hidden in review". Nothing says a review approval overrides `needs_review`, or whether a re-extraction that again disagrees re-hides an approved Problem. Builders of the gate and of Content Review will choose differently.
- The Structural Seed lists an `api/` router `build`, and the Design Paradigm diagram labels builder "CLI / background job", but the dependency diagram has no `api → builder` edge (so "anything not drawn is forbidden" forbids the router). Decide: is the builder launchable from the Parent Area (FR-5 progress report, audio regeneration) or CLI-only?

**Fix (autofix + one decision):** AD-5: "a review approval (keyed to the `content_hash` it approved) overrides `needs_review`; a changed hash on re-extraction re-applies `needs_review`". Add or remove `api → builder` explicitly.

### F6 — MEDIUM — Coverage and operational gaps

- **FR-4 Concept list editable in Content Review:** `content_concepts` / `content_concept_guides` are builder-only and AD-4's override layer is Problem-keyed only. Concept edits (and Problem→Concept tag edits) have no owner and would be wiped by a re-run.
- **NFR-7 restore:** backup is decided (SQLite online backup), restore is not — especially restoring a DB at an older Alembic revision, and assets not in the backup (Deferred acknowledges cost but not the restore behaviour when audio/crop files are missing).
- **WSL2 lifecycle:** WSL2 VMs stop when idle / on Windows restart; "autostart if wanted" is too soft for the child's daily use — state the supported start mechanism (Task Scheduler `wsl -e hoctap serve` or systemd in WSL) as seed or open question.
- **LAN addressing:** the mkcert cert is issued for the PC's LAN IP; a DHCP change breaks TLS and the installed PWA origin. Needs "DHCP reservation for the PC" as an assumption; `hoctap.local` resolution from the tablet (mDNS from Windows vs WSL) is unstated.
- **Single-writer concurrency:** builder publish and live app writes share one WAL SQLite; state `busy_timeout` / publish-in-short-transactions so a build run does not stall the child's Attempts (NFR-7).

### F7 — LOW — Stack pinning, tagging and small rule gaps

- Unpinned: `anthropic` SDK, KaTeX, mkcert; the OpenAPI→TS generator behind `npm run gen:api` is unnamed (AD-1 depends on it). Lint would flag these.
- `claude-opus-5`, adaptive thinking and `output_config.format` on the Batches API with image input are not recorded as a verified `version` memlog entry; confirm before binding.
- AD-6 "client never holds Answer Keys" needs an explicit carve-out for parent routes (FR-22 print answer page, FR-6 review) and for FR-23 quiz end-of-play reveal and FR-11 fallback "Xem đáp án", otherwise a strict reader blocks them.
- AD-11: plain-HTTP fallback implies a second listener; the port/scheme pair is not stated (deployment diagram shows only :8443 TLS).
- AD-10 cookie signing secret source not named (Config row lists only API/TTS keys).
- Spine is `status: draft` with three `[ASSUMPTION]` tags (AD-7 model, AD-8 engine, AD-11 CA install) plus one in Deployment — all appropriately deferred to the pilot; triage at Finalize step 4.

## What is good (keep)

- Named two-part paradigm with diagrams; clean `content → learning → parent` layering.
- AD-1 single generated contract with the "type = schema + grader + widget + print renderer" rule — the best divergence-killer in the doc.
- AD-3 retire-never-delete, AD-6 server-authoritative append-only log with idempotent client UUIDs, AD-8 content-addressed speech — all enforceable and well targeted.
- AD-11 catches the secure-context trap for PWAs on LAN that domain-focused drafts usually miss.
- Deferred list is explicit and each item is safely isolated behind an adapter or config.
