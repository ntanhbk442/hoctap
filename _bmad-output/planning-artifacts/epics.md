---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - planning-artifacts/prds/prd-hoctap-2026-09-26/prd.md
  - planning-artifacts/prds/prd-hoctap-2026-09-26/addendum.md
  - planning-artifacts/architecture/architecture-hoctap-2026-09-26/ARCHITECTURE-SPINE.md
  - planning-artifacts/ux-designs/ux-hoctap-2026-09-26/DESIGN.md
  - planning-artifacts/ux-designs/ux-hoctap-2026-09-26/EXPERIENCE.md
  - planning-artifacts/briefs/brief-hoctap-2026-09-26/brief.md
---

# Học Tập — Epic Breakdown

## Overview

This document breaks the PRD, the UX design contract (DESIGN.md and EXPERIENCE.md) and the architecture spine into epics and stories that can be implemented. Requirement IDs follow the source documents: FR-n and NFR-n (PRD), AD-n (architecture), UX-DRn (UX).

## Requirements Inventory

### Functional Requirements

- **FR-1** — Register the catalogue of 30 Toán Books, with duplicates skipped.
- **FR-2** — Extract Units, Lessons, Problems, Parts, Problem Types and crops from pages, keeping maths notation and a source link for each item.
- **FR-3** — Generate the Answer Key, Hint and Solution for every Part. Check each Answer Key twice, plus an arithmetic check; any disagreement sets `needs_review`.
- **FR-4** — Tag each Problem with 1–3 Concepts from a per-Grade Concept list shared by both Editions. Give every Concept a Guide. Anh can edit the list.
- **FR-5** — Extraction can be resumed. It reports status and cost, and the pilot's go/no-go gate must pass (fallback ≤ 15%, answer accuracy ≥ 98%, cost accepted) before the full run.
- **FR-6** — Content Review: browse Problems beside their source page, edit them, and approve or hide them. Edits survive re-extraction, and audio is regenerated after an edit.
- **FR-7** — Browse Grade → Book → Unit → Lesson and by Concept, with Lesson progress. Both Editions are listed as separate Books.
- **FR-8** — Child Home shows the Assignment, Retry, Continue, Streak, Stars and badges, and needs no reading. Sessions have at most 10 Problems.
- **FR-9** — Interactive Problem Types, with on-screen input and no system keyboard.
- **FR-10** — 🔊 read-aloud for every text. Auto-play of the instruction can be switched off per profile.
- **FR-11** — Fallback self-check: reveal the Solution, then the child marks it right or not yet (Stars and Retry rules apply).
- **FR-12** — Grading with answer equivalence and per-slot highlighting.
- **FR-13** — Staged help: a Hint after the first wrong answer, the Solution after the second, and the Hint available on request before answering.
- **FR-14** — Session summary with "Luyện lại bài sai" (practise the wrong ones).
- **FR-15** — Concept Guide screen, opened from a Problem or the Library, with "Luyện tập" (practise).
- **FR-16** — Stars per Problem (3/1/0, fallback 1), Streak and badges.
- **FR-17** — Retry Queue: entry, return on the next calendar day, and exit after two first-try correct answers.
- **FR-18** — Child Profiles (up to 4) and the Parent Area PIN.
- **FR-19** — Progress dashboard.
- **FR-20** — Assignments with a lifecycle and carry-over.
- **FR-21** — Error Reports: a parent flag hides the Problem, a child 🚩 doesn't.
- **FR-22** — Print a Problem Set as A4 with an answer page.
- **FR-23** — Quiz mode for "Phiếu tự luyện cuối tuần" (end-of-week practice sheet).

### NonFunctional Requirements

- **NFR-1** — Offline at runtime, including audio. Only extraction and audio regeneration need internet.
- **NFR-2** — Tablet (iPad or Android, both orientations) and PC Chrome or Edge, over the home LAN from one local server.
- **NFR-3** — Child-friendly: touch targets of at least 64px, one instruction plus audio, no ads, links or chat, and a natural child-friendly voice.
- **NFR-4** — A Problem shows in under 1 second, and audio starts in under 0.5 seconds on the LAN.
- **NFR-5** — All screens in Vietnamese, with correct diacritics.
- **NFR-6** — Data stays on the home PC. Only page images go to the extraction API.
- **NFR-7** — Progress is saved after every Attempt. Backup and restore works as a single file export.

### Additional Requirements (Architecture)

- **Starter (Epic 1, Story 1):** run `npm create @vite-pwa/pwa` (react-ts), then upgrade to Vite 8.3.1, @vitejs/plugin-react 6.1.1, TypeScript 6.0.3, React 19.3.0, vite-plugin-pwa 1.3.0, TanStack Query 5.104.0 and React Router 8.4.0. Add a minimal FastAPI 0.141.1 app on Python 3.14 (uv) with SQLAlchemy 2.1.1, Alembic 1.20.0, Pydantic 2.13.5, PyMuPDF 1.28.2 and anthropic >=1.8,<2. The frontend is served from the backend on one origin (AD-12).
- **AD-1:** a single ProblemDoc Pydantic contract with `part_key` and `slot_key`, a TS client generated with openapi-typescript, and `anthropic.transform_schema()` for extraction.
- **AD-2:** one SQLite database in WAL mode, with table-prefix ownership by module (`content_catalog_*`, `content_review_*`, `progress_*`, `parent_*`, `build_*`) and Alembic migrations.
- **AD-3:** stable `problem_id` and `concept_id`, upserted and retired (never deleted), with a curated Concept list and proposals.
- **AD-4:** a field-level review overlay with `base_hash`, a conflict flag, and approval tied to the content hash.
- **AD-5:** `visible_to_child()` and `child_view()` as the only child-facing selection and projection.
- **AD-6:** an append-only `progress_events` log, server-authoritative grading and scoring, and a scoring table by Session mode.
- **AD-7:** build stages keyed by input hash, the Message Batches API with `claude-opus-5`, `builder.jobs` control with Pause, and the `build_gate` formulas.
- **AD-8:** `content.speech.speech_text` and `speech_key`, the `speak-missing` stage, the `TtsEngine` adapter, and the UI phrase catalogue.
- **AD-9:** `ProblemSetRef` with one resolver, and Sessions frozen with ≤10-Problem chunks.
- **AD-10:** a client Session bundle, an IndexedDB event outbox, and no client-side grading.
- **AD-11:** LAN-only binding, PIN cookie (30-minute idle), first-run setup routes, and `parent_settings`.
- **AD-12:** TLS with an mkcert certificate for the reserved LAN IP, and a working plain-HTTP fallback.
- **AD-13:** native Windows runtime (uv, Python 3.14) and a firewall rule on Private networks.
- **AD-14:** backup through the SQLite backup API, and restore only while no build is running (maintenance mode, migration, key rotation, `db_epoch`).
- **Conventions:** UTF-8 NFC; UUIDv7; calendar day in Asia/Ho_Chi_Minh from `occurred_at`; error envelope `{error:{code,message}}`; JSON-lines logs; `build_costs`; pytest, Vitest and Playwright.

### UX Design Requirements

- **UX-DR1** — Implement the DESIGN.md colour, typography, rounded and spacing tokens as CSS variables, using the contrast-checked hex values exactly.
- **UX-DR2** — Self-host Nunito woff2 with the Vietnamese subset. Child text is at least 18px.
- **UX-DR3** — Chunky flat depth: a 4px solid bottom edge in a darker tone, and a press-down state that moves 4px. The Parent Area uses 1px borders.
- **UX-DR4** — Components: Speaker button (pulses while playing); Home card (double-width "Bài hôm nay" with a `primary-pressed` edge); Answer slot (grey → blue active → green ✔ / orange shake); Number pad (80px keys, comma only for grades 4–5); Choice chip; Feedback banner; Hint bubble (purple); Solution panel (steps with audio); Progress dots; Star burst; Streak flame; Badge (96px).
- **UX-DR5** — No red on child screens. Colour is never the only signal: ✔, ↻ and 💡 icons, plus a sound.
- **UX-DR6** — Child-mode navigation is flat: one ⬅ back button, no tabs or menus. The Parent Area is entered by long-pressing 🔒 for 2 seconds, or from the PC.
- **UX-DR7** — Audio behaviour: auto-play the instruction, one clip at a time, stop on leaving the screen, replay is free, the feedback sound plays before the Hint (with a 400ms gap), and a missing clip greys out 🔊.
- **UX-DR8** — Vietnamese microcopy from the EXPERIENCE Voice and Tone table, with the child addressed as "em". Six rotating praise lines. No loss framing.
- **UX-DR9** — Interactions for all 14 Problem Types, as in the EXPERIENCE table. Dragging always has a tap alternative, and there are no timers.
- **UX-DR10** — State patterns: first launch (no content or profile), no Assignment ("Học tiếp", keep learning), carried-over ribbon, server unreachable, interrupted Session, split Lesson "Phần i/n" (part i of n), quiz, Retry due, new badge, empty review list, Assignment statuses.
- **UX-DR11** — Accessibility: accessible names, the instruction text kept in the DOM, `prefers-reduced-motion` (no shake, stars or confetti), keyboard use in the Parent Area, and digit keys working in child mode.
- **UX-DR12** — Responsive layouts: tablet portrait (action bar at the bottom), tablet landscape (60/40 split), PC (max 1024px for the child view, two columns for the parent). The PWA runs full screen.
- **UX-DR13** — Print CSS: A4, black-and-white safe, empty boxes, the answer page after a page break, and dots for `match`.
- **UX-DR14** — Parent screens: Dashboard, Parent Library (Giao bài / In phiếu / Xem), Content Review tabs (Cần duyệt / Tất cả / Kiểm tra ngẫu nhiên / Khái niệm), Extraction with the go/no-go report, and Settings with backup and restore.

### FR Coverage Map

| FR | Epic | FR | Epic |
|---|---|---|---|
| FR-1 | E1 | FR-13 | E2 |
| FR-2 | E1 (grade-1 types), E6 (all types) | FR-14 | E2 |
| FR-3 | E1 | FR-15 | E5 |
| FR-4 | E1 (tagging and proposals), E5 (curation and guides) | FR-16 | E3 |
| FR-5 | E1 | FR-17 | E3 |
| FR-6 | E1 | FR-18 | E1 (PIN and first profile), E4 (up to 4 profiles and settings) |
| FR-7 | E2 | FR-19 | E4 |
| FR-8 | E2 (Home, Continue, chunks), E3 (Retry card, Streak, badges), E4 (Assignment card) | FR-20 | E4 |
| FR-9 | E2 (grade-1 types), E6 (remaining types) | FR-21 | E1 (review side), E4 (flags from parent and child) |
| FR-10 | E2 | FR-22 | E7 |
| FR-11 | E2 | FR-23 | E3 |
| FR-12 | E2 | | |

NFR-1, 2, 4 and 5 → E1 (serving and TLS) and E2 (PWA, outbox). NFR-3 → E2. NFR-6 → E1. NFR-7 → E2 (per-event save) and E7 (backup and restore).

## Epic List

### Epic 1: Anh loads and checks the first grade-1 lessons (pilot)
After this epic, Anh can install the app on the home PC, set a PIN, run the extraction pilot on about 3 grade-1 Lessons, review and fix the extracted Problems beside the scans, spot-check the answers, and see the go/no-go report with the real cost.
**FRs covered:** FR-1, FR-2 (grade-1), FR-3, FR-4 (tagging and proposals), FR-5, FR-6, FR-18 (PIN and first profile), FR-21 (review side)

### Epic 2: Bin practises a lesson alone, with voice
After this epic, Bin can open the app on the tablet, pick or continue a grade-1 Lesson, hear every problem, answer with touch controls, get instant grading, a Hint, then the Solution, and see a summary. This works even through brief Wi-Fi drops.
**FRs covered:** FR-7, FR-8 (Home, Continue, chunks), FR-9 (grade-1 types), FR-10, FR-11, FR-12, FR-13, FR-14

### Epic 3: Bin keeps coming back (Stars, Streaks, badges, Retry, quiz)
After this epic, Bin earns Stars and badges, builds a Streak, gets the Problems they missed back the next day, and can take the weekly practice sheet as a quiz.
**FRs covered:** FR-8 (Retry card, Streak, badges), FR-16, FR-17, FR-23

### Epic 4: Anh sees progress and steers practice
After this epic, Anh can manage up to 4 Child Profiles and settings, see the dashboard, assign today's work, and handle Error Reports from the dashboard or from Bin's 🚩.
**FRs covered:** FR-8 (Assignment card), FR-18, FR-19, FR-20, FR-21

### Epic 5: Concept Guides and Concept practice
After this epic, Anh can curate the Concept list and Guides, and Bin can open a spoken Concept Guide from any Problem and practise one Concept.
**FRs covered:** FR-4 (curation and guides), FR-15

### Epic 6: All 30 Toán Books, every Problem Type
After this epic, every Toán Book for grades 1–5 in both Editions is extracted and playable, including the Problem Types for grades 2–5.
**FRs covered:** FR-2 (all), FR-9 (remaining types)

### Epic 7: Paper worksheets and safe data
After this epic, Anh can print any Problem Set as a worksheet with an answer page, and back up and restore all progress.
**FRs covered:** FR-22; NFR-7 (backup and restore)

## Epic 1: Anh loads and checks the first grade-1 lessons (pilot)

Build the foundation and the extraction pipeline, and prove quality and cost on a small pilot before anything is spent on the full corpus.

### Story 1.1: Project scaffold served from one origin

As Anh,
I want to start Học Tập with one command on my PC,
So that the app runs locally and the other stories have a working base to build on.

**Acceptance Criteria:**

**Given** a fresh checkout
**When** I run `uv sync`, `npm ci`, `npm run build` and `hoctap serve`
**Then** FastAPI serves the built PWA at `/` and `GET /api/v1/health` returns `{"status":"ok"}` from one origin (AD-12)
**And** the frontend was scaffolded with `npm create @vite-pwa/pwa` (react-ts) and upgraded to the Stack versions, and the backend runs on Python 3.14 with the pinned versions.

**Given** the repo
**When** `pytest`, `npm run test` and `npm run lint` run
**Then** they all pass, and `npm run gen:api` generates `frontend/src/api` from OpenAPI with openapi-typescript.

**Given** the backend
**When** it starts
**Then** `data/hoctap.db` is created in WAL mode, and Alembic runs migrations at startup (AD-2)
**And** JSON-lines logs are written to `data/logs/`, and config comes from `hoctap.toml` and environment variables.

### Story 1.2: First-run setup with PIN and first Child Profile

As Anh,
I want to set a Parent PIN and create Bin's profile the first time the app opens,
So that the Parent Area is protected from the start.

**Acceptance Criteria:**

**Given** no PIN exists
**When** any client opens the app
**Then** only the first-run setup screen and routes are available (AD-11), and every other `/api/v1/parent/*` route returns 403 `SETUP_REQUIRED`.

**Given** the setup screen
**When** I enter a 4-digit PIN twice and create a profile (name, avatar, Grade)
**Then** the PIN is stored as a bcrypt hash in `parent_settings`, and the profile is stored in `parent_profiles`.

**Given** a PIN exists
**When** I enter the correct PIN
**Then** a signed httpOnly cookie is issued, and it expires after 30 minutes idle
**And** a wrong PIN returns 401 with the Vietnamese message "Mã PIN chưa đúng" (the PIN isn't right).

### Story 1.3: Book catalogue

As Anh,
I want the app to know all 30 Toán Books, with duplicates excluded,
So that extraction and the Library use one fixed list.

**Acceptance Criteria:**

**Given** `Sach_Arch/`
**When** `hoctap build catalogue` runs
**Then** `content_catalog_books` contains exactly 30 Toán Books, each with a fixed `book_id` (for example `toan1-2020-q1`, `toan3-2024-t1`), Edition, Grade, volume, source file and page count (FR-1)
**And** the duplicates named in the brief addendum are excluded, and the higher-quality file of each pair is chosen.

**Given** the catalogue has already been built
**When** it is run again
**Then** it makes no changes, and the `book_id`s stay the same (AD-3).

### Story 1.4: ProblemDoc contract and the grade-1 Problem Types

As the developer building extraction and the player,
I want one canonical ProblemDoc schema,
So that the extractor, graders and widgets all agree (AD-1).

**Acceptance Criteria:**

**Given** `hoctap/content/schema.py`
**When** it is imported
**Then** it defines ProblemDoc v1 with Parts discriminated by `type` for `number_input`, `compare`, `multiple_choice`, `order`, `number_tree`, `grid_fill`, `match`, `count_image`, `image_select`, `dot_draw`, `connect_dots`, `spot_difference` and `fallback`
**And** every Part has a `part_key`, every Answer Slot a `slot_key`, and the text uses the inline LaTeX subset.

**Given** the schema
**When** `anthropic.transform_schema(ProblemDoc)` runs
**Then** it produces a schema that the API accepts, and a unit test checks it against sample fixtures for each type.

**Given** a ProblemDoc
**When** `content.child_view()` projects it
**Then** the result contains no Answer Keys, Hints or Solutions (AD-5).

### Story 1.5: Render and extract pilot pages with Claude

As Anh,
I want to extract Problems from a chosen set of pages,
So that the scans become structured content.

**Acceptance Criteria:**

**Given** a page range and `ANTHROPIC_API_KEY`
**When** `hoctap build pilot --pages <ref>` runs
**Then** each page is rendered to PNG in `data/assets/pages/`, and Message Batches requests go out with model `claude-opus-5`, adaptive thinking and the transformed schema (AD-7)
**And** every result is validated with Pydantic, and gets stable `problem_id`s (AD-3) and a source page and bounding box (FR-2).

**Given** a Problem that runs onto the next page
**When** it is extracted
**Then** it is merged into one Problem. Watermarks, QR codes, headers and footers are ignored.

**Given** a stage completed earlier with the same input hash
**When** the build runs again
**Then** that stage is skipped, and `build_costs` records the cost of each batch (FR-5).

### Story 1.6: Verify answers and flag disagreements

As Anh,
I want every Answer Key double-checked,
So that Bin isn't taught a wrong answer (FR-3).

**Acceptance Criteria:**

**Given** extracted Problems
**When** the `verify` stage runs
**Then** a second, independent Claude answer is obtained for each Part, and arithmetic answers are also computed by `builder.arith.evaluate()`.

**Given** any disagreement between the two keys, or between the code result and either key
**When** verification finishes
**Then** the Problem is marked `needs_review`, and `visible_to_child()` excludes it (AD-5)
**And** Hints are checked so that they don't contain the answer.

### Story 1.7: Crop, Concept tagging and publish

As Anh,
I want the Problems stored with their cropped images and Concept tags,
So that they are ready to play and review.

**Acceptance Criteria:**

**Given** verified Problems
**When** `crop` and `publish` run
**Then** the crops are saved to `data/assets/crops/`, and the Problems are upserted into `content_catalog_*` through `content.catalog` only (AD-2)
**And** Problems of the re-extracted Lessons that weren't found again get `retired_at` set (AD-3).

**Given** a pilot with no Concept list yet
**When** tagging runs
**Then** the proposed Concepts are stored in `content_review_concept_proposals` (1–3 per Problem), and the Problems keep their proposal links until Anh accepts them (FR-4).

### Story 1.8: Content Review with overrides

As Anh,
I want to review and fix extracted Problems beside the scan,
So that the content is correct (FR-6).

**Acceptance Criteria:**

**Given** the PIN session
**When** I open Content Review
**Then** the tabs Cần duyệt (to review), Tất cả (all), Kiểm tra ngẫu nhiên (spot-check) and Khái niệm (Concepts) are shown (UX-DR14), and each Problem opens beside its source page crop.

**Given** a Problem
**When** I edit a field (text, Answer Key, Hint, Solution or Problem Type) and save
**Then** a field-level override is stored with its `base_hash` (AD-4), and `content.effective_problem()` returns the merged content.

**Given** a Problem whose extracted field changes in a re-extraction
**When** the override's `base_hash` no longer matches
**Then** the Problem gets `review_conflict` and appears under Cần duyệt, and the override still wins.

**Given** a `needs_review` Problem
**When** I tap Duyệt (approve) or Ẩn (hide)
**Then** `content_review_status` records the approval against the current content hash, or the hidden flag, and visibility follows AD-5.

**Given** the Khái niệm tab
**When** I accept, rename or merge Concept proposals
**Then** they become curated Concepts with stable `concept_id`s, and the tagged Problems link to them (AD-3).

### Story 1.9: Spot-check, pilot report and go/no-go gate

As Anh,
I want to see the pilot's quality and cost and approve or stop the full run,
So that money is only spent once quality is proven (FR-5).

**Acceptance Criteria:**

**Given** a finished pilot
**When** I open Kiểm tra ngẫu nhiên
**Then** a random sample of at least 30 Problems, spread across Problem Types, is shown, and I mark each Answer Key Đúng (right) or Sai (wrong).

**Given** the spot-check is done
**When** I open the Extraction screen
**Then** the report shows `fallback_share`, `key_accuracy` and `est_cost` against the thresholds (fallback ≤ 15%, accuracy ≥ 98%), with each check green or red
**And** "Chạy toàn bộ" (run everything) is enabled only when all checks pass and I confirm, which writes `build_gate` (AD-7).

**Given** no `build_gate` approval
**When** a full run is requested (UI or CLI)
**Then** it is refused with the code `GATE_NOT_APPROVED`.

### Story 1.10: Extraction control from the Parent Area

As Anh,
I want to start, pause and follow extraction from the PC browser,
So that I don't need the terminal.

**Acceptance Criteria:**

**Given** the PIN session
**When** I start a pilot or a run from the Extraction screen
**Then** `builder.jobs` starts the builder as a subprocess, and progress shows by Book and page, with the cost so far and the failed pages.

**Given** a running job
**When** I tap Tạm dừng (pause)
**Then** no new batches are submitted, results of batches already in flight are still collected when they arrive, and Tiếp tục (resume) continues without redoing finished pages.

### Story 1.11: HTTPS on the LAN and Windows runtime

As Anh,
I want the tablet to reach the app securely over home Wi-Fi,
So that the PWA features work (AD-12, AD-13).

**Acceptance Criteria:**

**Given** mkcert is installed
**When** I run `hoctap certs --ip <reserved LAN IP>`
**Then** a certificate is created in `data/certs/`, and `hoctap serve` serves TLS on port 8443 bound to the LAN interface.

**Given** Windows
**When** I run `hoctap install-windows`
**Then** a Private-network firewall rule for the port is added, and the docs explain how to install the CA on iPad and Android and how to reserve the IP on the router.

**Given** a device without the CA
**When** it opens the plain-HTTP URL
**Then** the app still loads and plays, without the service worker.

## Epic 2: Bin practises a lesson alone, with voice

The child-facing loop for grade-1 content: Home, Library, Problem player, audio, grading, help and summary.

### Story 2.1: Design tokens, Nunito and core components

As Bin,
I want big, friendly, colourful screens,
So that the app feels like a game.

**Acceptance Criteria:**

**Given** the frontend
**When** it is built
**Then** the DESIGN.md tokens exist as CSS variables with the exact hex values (UX-DR1), and Nunito is self-hosted with the Vietnamese subset and precached (UX-DR2).

**Given** the component library
**When** it is rendered in a Vitest or Storybook-style test page
**Then** Speaker button, Home card, Answer slot, Number pad, Choice chip, Feedback banner, Hint bubble, Solution panel, Progress dots and Star burst match UX-DR3 and UX-DR4, with touch targets of at least 64px (NFR-3)
**And** `useMotion()` honours `prefers-reduced-motion` (UX-DR11), and no child component uses red (UX-DR5).

### Story 2.2: Speech normaliser, TTS adapter and speak-missing

As Bin,
I want every problem read aloud in natural Vietnamese,
So that I can practise before I can read (FR-10).

**Acceptance Criteria:**

**Given** a text containing `<`, `>`, `=`, `\overline{2a4b}` or `\frac{1}{2}`
**When** `content.speech.speech_text()` normalises it
**Then** it returns correct Vietnamese read-aloud text (for example "bé hơn", less than), and unit tests cover each notation (AD-8).

**Given** Problems, Concept Guides and `frontend/src/audio/phrases.vi.json`
**When** `hoctap build speak-missing` runs
**Then** every referenced `speech_key` without a file is synthesised through the `TtsEngine` adapter to `data/assets/audio/<key>.mp3`
**And** at least two engines are implemented (one cloud, one local or edge-tts), selectable in config, for the pilot listening test.

**Given** an edited text in review
**When** `speak-missing` runs next
**Then** only the new key is synthesised.

### Story 2.3: Child Home and Library

As Bin,
I want to tap a big card to start today's lesson,
So that I can begin without reading.

**Acceptance Criteria:**

**Given** a Child Profile with Grade 1
**When** Bin opens the app
**Then** Home shows "Học tiếp" (keep learning: the next unfinished Lesson in Book order) and "Tiếp tục" (continue) when a Session is unfinished, each with an icon and 🔊, and a long press plays the label (FR-8, UX-DR6, UX-DR10).

**Given** the Library
**When** Bin opens 📚 Sách (books)
**Then** Grade → Book → Unit → Lesson is shown, with both Editions as separate Books and each Lesson's progress ("5/8 ✓") (FR-7)
**And** only Problems allowed by `visible_to_child()` are counted and listed.

**Given** only one profile
**When** the app opens
**Then** the profile picker is skipped.

### Story 2.4: Sessions, resolver and the event API

As Bin,
I want to start a Lesson and have every answer saved,
So that nothing is lost.

**Acceptance Criteria:**

**Given** a `ProblemSetRef{kind: lesson}`
**When** a Session starts
**Then** `learning.problem_sets.resolve()` returns the ordered visible Problems, and the Session freezes its list and its chunk of at most 10 ("Phần i/n") (AD-9).

**Given** a Session
**When** its bundle is requested
**Then** it contains the `child_view` of each Problem, the crop and audio URLs, and the progress state, and it loads in under 1 second on the LAN (NFR-4).

**Given** an event (`attempt`, `hint_requested`, etc.) with a client UUIDv7 and `occurred_at`
**When** it is posted twice
**Then** it is stored once in `progress_events`, and the second post returns the same result (AD-6).

### Story 2.5: Grading and staged help

As Bin,
I want to know right away if I'm right, and get help when I'm wrong,
So that I learn instead of guessing (FR-12, FR-13).

**Acceptance Criteria:**

**Given** an `attempt` for a Part
**When** the server grades it with the grader for that type
**Then** numbers match however they are formatted (`07` = `7`), `order` and `match` are all-or-nothing, and for multi-slot Parts every wrong `slot_key` is returned.

**Given** the first wrong Attempt on a Part
**When** the result comes back
**Then** the Hint is released and returned, and the Problem is added to the Retry Queue.

**Given** a second wrong Attempt
**When** the result comes back
**Then** the Solution is released. Asking for the Hint before answering records `hint_requested`.

### Story 2.6: Problem player with the basic grade-1 widgets

As Bin,
I want to answer by tapping big buttons and a number pad,
So that I never need the keyboard (FR-9).

**Acceptance Criteria:**

**Given** a Problem of type `number_input`, `compare`, `multiple_choice`, `number_tree` or `count_image`
**When** it opens
**Then** it renders with its UX-DR9 interaction and the on-screen number pad, and ✔ Kiểm tra (check) is enabled only when the current Part is complete
**And** the layout follows UX-DR12 for portrait, landscape and PC.

**Given** a correct answer
**When** it is graded
**Then** the slot turns green, a chime plays, the banner says "Đúng rồi!…" (correct!) with a rotating praise line. A wrong answer shakes the slot orange, plays "boop", then shows the Hint bubble with audio after 400ms (UX-DR7, UX-DR8).

**Given** a second wrong answer
**When** the Solution panel opens
**Then** the steps are revealed one at a time with audio, then "Tiếp ➜" (next).

### Story 2.7: The other grade-1 widgets

As Bin,
I want the picture exercises from my book to work in the app,
So that I can practise the whole lesson.

**Acceptance Criteria:**

**Given** a Problem of type `order`, `grid_fill`, `match`, `image_select`, `dot_draw`, `connect_dots` or `spot_difference`
**When** it opens
**Then** it follows the UX-DR9 interaction (dragging with a tap alternative, locked cells, drawn lines, hotspots on the right-hand image), and it is graded by its server grader.

**Given** `connect_dots`
**When** Bin taps the wrong next dot
**Then** the dot wiggles, and no Attempt is recorded until ✔.

### Story 2.8: Fallback self-check

As Bin,
I want to check my own work on exercises the app can't grade,
So that I can still finish the lesson (FR-11).

**Acceptance Criteria:**

**Given** a `fallback` Problem
**When** it opens
**Then** the page crop can be pinch-zoomed, and "Xem đáp án" (see answer) records `fallback_revealed` and shows the Solution.

**Given** the Solution is revealed
**When** Bin taps "Em làm đúng" or "Em chưa đúng" (I got it right / not yet)
**Then** `self_marked` is recorded, "đúng" earns 1 Star, and "chưa đúng" adds the Problem to the Retry Queue. Neither counts towards first-try accuracy.

### Story 2.9: Audio player and auto-play

As Bin,
I want the instruction to play when a problem opens, and 🔊 to replay it,
So that I always know what to do.

**Acceptance Criteria:**

**Given** a Problem opens and auto-play is on for the profile
**When** the first user tap has unlocked audio
**Then** the instruction plays through the shared `AudioPlayer`, and starting any other clip or leaving the screen stops it (UX-DR7)
**And** audio starts in under 0.5 seconds on the LAN (NFR-4).

**Given** a missing audio file
**When** 🔊 is shown
**Then** it is greyed out, and the text stays visible.

### Story 2.10: Session summary and "Luyện lại bài sai"

As Bin,
I want to see how I did and practise my mistakes,
So that I finish proud (FR-14).

**Acceptance Criteria:**

**Given** the last Problem of a Session
**When** it is completed
**Then** the summary shows the Problems correct on the first try, with a fanfare.

**Given** Problems answered wrong in the Session
**When** Bin taps "Luyện lại bài sai"
**Then** a `replay` Session starts with those Problems. It earns no Stars and doesn't count towards the Retry Queue or the Streak (AD-6).

### Story 2.11: PWA offline shell and event outbox

As Bin,
I want the lesson to keep working if the Wi-Fi drops for a moment,
So that my answers aren't lost (NFR-1, NFR-7).

**Acceptance Criteria:**

**Given** HTTPS with the CA installed
**When** the app loads
**Then** the service worker precaches the shell, fonts, KaTeX and phrase audio, and each Session bundle's assets are cached when the Session starts (AD-10).

**Given** the server can't be reached during a Session
**When** Bin answers
**Then** the event is queued in IndexedDB, the "Máy tính bảng chưa kết nối…" (the tablet isn't connected…) screen shows with 🔊 and a retry, and no local grading happens.

**Given** the connection returns
**When** the outbox flushes
**Then** events are sent in order and applied once. A closed tablet resumes at the same Problem through "Tiếp tục" (UX-DR10).

## Epic 3: Bin keeps coming back

### Story 3.1: Stars and the Streak

As Bin,
I want to earn Stars and keep my Streak flame,
So that I want to practise every day (FR-16).

**Acceptance Criteria:**

**Given** Problems finished in `practice`, `retry` or `concept` mode
**When** `learning.scoring` applies them
**Then** each Problem gets 3 Stars (every Part right first try), 1 (a Hint or second try was needed, or a fallback marked "đúng") or 0 (the Solution was shown), materialised in the same transaction as the event.

**Given** Sessions completed on consecutive calendar days (Asia/Ho_Chi_Minh, from `occurred_at`)
**When** Home loads
**Then** it shows the Streak and total Stars. `replay` Sessions don't count.
**And** Stars fly from a correct Problem to the counter (the Star burst), and the Session summary shows the Stars earned and the Streak flame.

### Story 3.2: Badges

As Bin,
I want badges for milestones,
So that I feel proud.

**Acceptance Criteria:**

**Given** a milestone ("Hoàn thành Tuần 1", finished week 1; "7 ngày liên tiếp", 7 days in a row; first 100 Stars)
**When** it is reached
**Then** a badge is stored in `progress_badges`, pops onto the Session summary with a fanfare and 🔊, the latest 3 badges show on Home, and all of them show in "Huy hiệu của em" (your badges), with locked ones in grey (UX-DR4).

### Story 3.3: Retry Queue

As Bin,
I want the problems I missed to come back the next day,
So that I really learn them (FR-17).

**Acceptance Criteria:**

**Given** a Problem with a wrong Attempt or a fallback marked "chưa đúng"
**When** the next calendar day comes
**Then** Home shows the "Luyện lại" (practise again) card, which starts a `retry` Session with the Problems that are due.

**Given** a queued Problem
**When** every Part is answered correctly on the first try in 2 separate non-replay Sessions
**Then** the Problem leaves the queue.

### Story 3.4: Quiz mode for "Phiếu tự luyện cuối tuần"

As Bin,
I want to take the weekly sheet as a quiz,
So that I can see what I know (FR-23).

**Acceptance Criteria:**

**Given** a Lesson that is a "Phiếu tự luyện cuối tuần"
**When** it starts
**Then** the Session mode is `quiz`: no 💡 button, no Hints and no right-or-wrong feedback, only "Đã lưu" (saved), and the progress dots only fill.

**Given** the last Problem
**When** `quiz_submitted` is recorded
**Then** Quiz results show every Problem as ✔ or ↻, with Solutions for the wrong ones. Problems with every Part right earn 3 Stars and the others 0, and the wrong ones go to the Retry Queue.

## Epic 4: Anh sees progress and steers practice

### Story 4.1: Profiles and settings

As Anh,
I want to manage up to 4 children and their settings,
So that siblings can use the app too (FR-18).

**Acceptance Criteria:**

**Given** the PIN session
**When** I open Settings
**Then** I can add, edit or remove profiles (at most 4), change the PIN, and turn auto-play on or off for each child.
**And** with more than 1 profile, the child app shows the profile picker.

**Given** the child Home
**When** 🔒 is long-pressed for 2 seconds
**Then** the PIN gate opens. A short tap does nothing (UX-DR6).

### Story 4.2: Progress dashboard

As Anh,
I want to see Bin's week at a glance,
So that I know what to work on (FR-19).

**Acceptance Criteria:**

**Given** the PIN session
**When** I open the Dashboard for a child
**Then** it shows Sessions and time per day and week, first-try accuracy, progress by Book and Unit, the weakest Concepts (only those with at least 5 Attempts, ranked by first-try accuracy) and recent mistakes with the child's answer beside the correct one. Every figure is read from the `learning` materialisations (AD-6).

### Story 4.3: Assignments

As Anh,
I want to assign tomorrow's lesson,
So that Bin practises what matters (FR-20).

**Acceptance Criteria:**

**Given** the Parent Library or a Concept
**When** I tap "Giao bài" (assign) and pick a date
**Then** an Assignment with a `ProblemSetRef` is stored, and on that day Bin's Home shows it first as "Bài hôm nay" (today's lesson).

**Given** an Assignment split into Sessions
**When** Bin completes all of its Sessions
**Then** its status becomes Đã xong (done). Unfinished Assignments carry over with the "Hôm qua" (yesterday) ribbon, and the Dashboard shows Chưa làm (not started), Đang làm (in progress, "Phần i/n") or Đã xong.

### Story 4.4: Error Reports from the parent and the child

As Anh,
I want to flag a wrong problem and see Bin's flags,
So that mistakes get fixed (FR-21).

**Acceptance Criteria:**

**Given** a Problem in the Parent Library preview or in recent mistakes
**When** I tap 🚩 "Báo lỗi" (report error) with an optional note
**Then** an Error Report of kind `parent` is created through `content.review`, and the Problem is hidden from the child until it is resolved.

**Given** Bin taps 🚩 and confirms "Có" (yes)
**When** the report is saved
**Then** a report of kind `child` appears under Cần duyệt, the Problem stays visible, and Bin sees "Đã báo cho bố mẹ" (your parents have been told).

## Epic 5: Concept Guides and Concept practice

### Story 5.1: Concept Guides generated and editable

As Anh,
I want a short spoken guide for every Concept,
So that Bin can learn the idea behind the exercises (FR-4).

**Acceptance Criteria:**

**Given** curated Concepts
**When** the builder generates the Guides from the Books' theory boxes and "Ví dụ" (worked examples)
**Then** every Concept has a Guide (explanation plus one worked example) that fits on one tablet screen and has audio.
**And** Anh can edit a Guide in Content Review. The edits are stored as overrides and survive regeneration (AD-4).

### Story 5.2: Concept Guide screen and practice

As Bin,
I want to open 📖 from a Problem and practise that Concept,
So that I understand it (FR-15).

**Acceptance Criteria:**

**Given** a Problem
**When** Bin taps 📖
**Then** the Guide opens as an overlay with 🔊, and closing it returns to the same Problem with the answer kept.

**Given** "Luyện tập" (practise) on a Guide, or the Library's Concept tab
**When** it is tapped
**Then** a `concept` Session starts with up to 10 visible Problems for that Concept, the ones not yet solved correctly on the first try first (AD-9).

## Epic 6: All 30 Toán Books, every Problem Type

### Story 6.1: `expression_input` and the grade 3–5 grading rules

As a child in a higher grade,
I want to enter calculations and decimals,
So that the grade 3–5 books work.

**Acceptance Criteria:**

**Given** the `expression_input` type
**When** a child enters an expression with the + − × : ( ) keypad
**Then** the server accepts any expression that evaluates to the correct value unless a specific form is required, and `3,5` = `3.5` for grades 4–5 (FR-12).
**And** the schema, grader, widget and print renderer all ship together (AD-1).

### Story 6.2: Full-corpus run

As Anh,
I want every Toán Book extracted after the gate passes,
So that all grades are available.

**Acceptance Criteria:**

**Given** an approved `build_gate`
**When** "Chạy toàn bộ" runs
**Then** all 30 Books are processed through the resumable stages, the cost and progress are reported, and failures are listed.
**And** after the run, at least 95% of Problems are interactive, and the SM-3 spot-check of 100 random Problems is available in Kiểm tra ngẫu nhiên.

## Epic 7: Paper worksheets and safe data

### Story 7.1: Printable worksheets

As Anh,
I want to print any Problem Set,
So that Bin can practise away from the tablet (FR-22).

**Acceptance Criteria:**

**Given** a Lesson, Concept or Assignment
**When** I tap "In phiếu" (print worksheet)
**Then** a print preview shows an A4, black-and-white-safe worksheet built from `learning.problem_sets.resolve()`, with empty boxes and dots for `match`, and an answer page after a page break (UX-DR13).

### Story 7.2: Backup and restore

As Anh,
I want to back up and restore all progress,
So that a PC problem doesn't lose Bin's work (NFR-7).

**Acceptance Criteria:**

**Given** the PIN session
**When** I tap "Sao lưu" (backup)
**Then** a single `.db` file is downloaded, created with the SQLite online backup API while the app keeps running.

**Given** a backup file and no running build
**When** I tap "Khôi phục" (restore) and confirm
**Then** the app enters maintenance (503), replaces the database, runs migrations, rotates the cookie key, bumps `db_epoch`, and returns (AD-14)
**And** restore is refused while a build job is running, and tablets discard outbox events stamped with the old `db_epoch`.
