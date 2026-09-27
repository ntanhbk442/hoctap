---
title: "PRD: Học Tập"
status: final
created: 2026-09-26
updated: 2026-09-26
---

# PRD: Học Tập

## 0. Document Purpose

This PRD is written for Anh (the parent and owner) and for the BMad steps that come next: UX, architecture, and epics and stories. It builds on the final product brief (`planning-artifacts/briefs/brief-hoctap-2026-09-26/`) and does not repeat it. Each feature describes its behaviour first, followed by numbered functional requirements (FR-n) that can be tested. Words defined in §3 are used exactly as defined. FR IDs are stable, not sequential. Guesses I made are tagged `[ASSUMPTION]` and all listed in §11. How things will be built (models, storage, TTS engine) is in `addendum.md`, not here.

## 1. Vision

The central bet is simple: **the same books the school uses, made interactive and spoken, will get a young child practising on their own, and that practice will show up in school marks.** Everything else (extraction, audio, grading, the dashboard) exists to serve that one loop.

Học Tập turns the scanned Archimedes "Hướng dẫn học Toán" books (grades 1–5, the 2020 and 2024–25 editions) into a spoken, touch-first practice app in Vietnamese. It is for a grade-1 child who can't read the instructions yet. The child picks today's lesson and hears each problem read aloud. They answer by tapping, dragging or typing, and get instant feedback. When stuck, they get a spoken hint first and then a worked solution.

The parent can see what the child practised, which topics are weak, and which problem set comes next. The parent no longer has to read every problem aloud or mark every answer.

## 2. Target User

### 2.1 Jobs To Be Done
- **Child:** "Let me practise my school maths by myself, without waiting for someone to read it to me, and let me know right away if I got it right."
- **Child:** "When I'm stuck, help me a little. Don't just give me the answer."
- **Parent:** "Keep my child practising exactly what the school teaches, and tell me where they are weak, without me marking pages every evening."
- **Parent:** "Let me choose what my child should do today."

### 2.2 Non-Users (v1)
- Teachers, classes, or children outside the family.
- Tiếng Việt learners. The Tiếng Việt books come in phase 2.

### 2.3 Key User Journeys

**UJ-1. Bin practises tonight's lesson alone.** [ASSUMPTION: persona details]
Bin is 6, in grade 1 at Archimedes, and can recognise numbers but not read sentences. After dinner Bin opens Học Tập on the family tablet and taps their own avatar. Home shows one big card, "Bài hôm nay" (today's lesson): Toán 1 – Tuần 3 – Tiết 2, which Anh assigned. Bin taps it. The first problem appears and is read aloud automatically: *"Điền số thích hợp vào ô trống"* (fill in the missing number). Bin taps the empty box, types 4 on the big number pad, and taps ✔. Confetti, a "Đúng rồi!" (correct!) chime, and a star. The fourth problem is a number tree. Bin answers wrong, hears the hint *"Hai số ở dưới cộng lại bằng số ở trên"* (the two numbers below add up to the number on top), and gets it on the second try. After 8 problems (about 15 minutes) a summary screen shows 7 of 8 correct first try, 22 Stars earned, and the 4-day Streak flame growing. Bin shows the tablet to Anh.
**Edge case:** Bin gets the same Problem wrong twice. The worked Solution plays with audio. The Problem was already added to the Retry Queue at the first wrong Attempt, and it comes back tomorrow.

**UJ-2. Anh checks progress and assigns tomorrow's work.**
Anh opens the Parent Area on the PC and enters a PIN. The dashboard shows this week: 5 sessions, 42 problems, 81% correct first try. The weakest concept is "So sánh số" (comparing numbers) at 55%. Anh opens the list of recent mistakes, sees Bin keeps choosing `>` when the answer is `<`, and assigns the "So sánh số" problem set from the 2024–25 book for tomorrow. Anh notices one answer looks wrong and taps "Báo lỗi" (report error). The problem is hidden from Bin until Anh fixes or confirms it.

**UJ-3. Anh prints a worksheet for the weekend trip.**
Anh picks Tuần 4, taps "In phiếu" (print worksheet), and gets a clean A4 worksheet with an answer page at the end.

**UJ-4. Anh loads the books (once).**
Anh runs the extraction for a pilot of about 3 grade-1 Lessons and checks those Problems in the Content Review screen. The pilot report checks the go/no-go gate (FR-5). Anh confirms, and the rest of the Toán Books run. Progress can be resumed if it stops, and pages that failed are listed.

## 3. Glossary

- **Book** — one scanned PDF volume (for example "Toán 1 – Quyển 2" or "Toán 3 – Tập 1"). It belongs to one Edition, one Grade and one Subject.
- **Edition** — `2020` (weekly structure) or `2024-25` (topic structure).
- **Unit** — the top grouping inside a Book: a *Tuần* (week) in the 2020 edition, a *Chương/Chủ đề* (chapter or topic) in 2024-25.
- **Lesson** — a group of Problems inside a Unit, for example *Tiết 2* or *Phiếu tự luyện cuối tuần* (end-of-week practice sheet). Each Lesson is a Problem Set.
- **Problem Set** — an ordered list of Problems the child plays in one go. It is either a Lesson from a Book, or a set built by the parent or by the system (a Retry Queue Session or a Concept practice set).
- **Problem** — one numbered exercise ("Bài 3") with one or more **Parts** (a, b, c…). Each Part has one **Answer Slot** or more.
- **Problem Type** — the kind of interaction a Part uses (for example `number_input` or `compare`). The full list is in FR-9.
- **Fallback Problem** — a Problem that can't be made interactive (for example drawing or colouring). It is shown as the page image, and the child checks their work against the revealed Solution.
- **Answer Key** — the correct answer(s) for every Answer Slot of a Problem.
- **Hint** — a short, spoken nudge that doesn't reveal the answer.
- **Solution** — a step-by-step worked explanation with the answer.
- **Concept** — a named skill from a Grade's Concept list (for example "So sánh số trong phạm vi 10", comparing numbers up to 10); see FR-4.
- **Concept Guide** — a short, spoken explanation of a Concept with a worked example. Where the Book has one, it comes from the Book's theory box or "Ví dụ" (worked example).
- **Attempt** — one submitted answer to a Part.
- **Session** — one run through a Problem Set, or through one chunk of it when it is split (FR-8), from start to the summary screen.
- **Star** — a reward earned per Problem (scoring in FR-16).
- **Streak** — the number of days in a row with at least one completed Session. **Practice days** means the number of days with a completed Session in a given week.
- **Retry Queue** — the Problems a child got wrong, to be practised again (rules in FR-17).
- **Assignment** — a Problem Set the parent picks for a given day (lifecycle in FR-20).
- **Error Report** — a flag saying that a Problem's content or Answer Key is wrong.
- **Child Profile**, **Parent Area** — the child's identity and data; the PIN-protected area for the parent.

## 4. Features

### 4.1 Content Extraction
**Description:** A one-time, resumable pipeline turns each Book's scanned pages into structured Problems, Answer Keys, Hints, Solutions, Concepts and Concept Guides. It runs by page and supports a pilot first. Worked examples ("Ví dụ") and theory boxes become Concept Guide material, not Problems. Realizes UJ-4.

#### FR-1: Register the Book catalogue
The system lists every Toán Book in `Sach_Arch/` with its Edition, Grade and volume, and skips the known duplicate files.
- Each of the 30 Toán Books appears exactly once. The duplicates listed in the brief's addendum are excluded.

#### FR-2: Extract Problems from pages
Anh can run extraction on a chosen range: all Books, one Book, or chosen pages. It produces Units, Lessons, Problems, Parts, Problem Types and cropped images.
- Output for each Problem includes: Book, page(s), bounding box, Unit, Lesson, number, instruction text (Vietnamese with full diacritics), Parts, Problem Type, and the images it needs.
- Maths notation is preserved: overlines (for example $\overline{2a4b}$), fractions, `<`/`>`/`=`, and tables.
- A Problem that continues onto the next page is merged into one Problem.
- Every generated item keeps a link to its source page and bounding box, so any mistake can be checked against the scan.
- Watermarks, QR codes, page headers and page footers are ignored.

#### FR-3: Generate Answer Keys, Hints and Solutions
For every Part, the system generates an Answer Key, one Hint and a Solution in Vietnamese suitable for a grade-1 to grade-5 child.
- Each Answer Key is generated twice independently. Arithmetic answers are also computed by code. If the two generated keys disagree, or the code result disagrees with either of them, the Problem is marked `needs_review` and is not shown to the child. [ASSUMPTION: hide rather than show with a warning]
- A Hint never contains the answer.

#### FR-4: Tag Concepts and build Concept Guides
Every Problem is tagged with 1–3 Concepts from one Concept list per Grade, used by both Editions. Every Concept has a Concept Guide.
- No Problem has zero Concepts.
- Concepts are shared across Editions, so "So sánh số" from both Editions maps to one Concept.
- The Concept list for each Grade is proposed during the pilot, with each Concept about as broad as one Unit's topic, and Anh can edit it in Content Review.

#### FR-5: Resume, report, and the pilot go/no-go gate
Extraction can be stopped and resumed without redoing finished pages. It reports per-page status, failures, pages per minute and API cost so far.
- After the process is killed and restarted, no completed page is processed again.
- After the pilot, a report shows the cost estimate for the full run and checks the **go/no-go gate**:
  - `fallback` share of the pilot's Problems is at most 15%;
  - at least 98% of pilot Answer Keys are correct when Anh checks them;
  - Anh accepts the estimated cost. [ASSUMPTION: thresholds taken from the brief's targets]

  The full run starts only after Anh confirms. If the gate fails, the missing Problem Types are added or the prompts fixed, and the pilot is re-run before the full run.

#### FR-6: Content Review
In the Parent Area, Anh can browse extracted Problems next to their source page image, edit the text, Answer Key, Hint, Solution or Problem Type, and approve or hide a Problem.
- Edits are kept if extraction is run again on the same page. [ASSUMPTION]
- Editing any spoken text regenerates its audio.
- New Problems are visible to the child by default (AI content is trusted). Only `needs_review` Problems (FR-3), Problems flagged by the parent (FR-21) and Problems Anh hides here are hidden. Approving a hidden Problem makes it visible.
- `needs_review` Problems and Problems with an Error Report appear in a review list.

### 4.2 Library and Problem Sets
**Description:** The child and the parent browse content the way the books are organised: Grade → Book → Unit → Lesson. It can also be browsed by Concept. The child's Home screen puts today's Assignment first. Realizes UJ-1, UJ-2.

#### FR-7: Browse by book structure and by Concept
Users can browse Grade → Book → Unit → Lesson, or Concept → Problems, and start any Lesson as a Session.
- Every Lesson shows its progress (for example "5/8 ✓": 5 of 8 Problems done).
- The child's view defaults to their own Grade. Other Grades are reachable but not shown on Home. [ASSUMPTION]
- Both Editions of a Grade are listed as separate Books. Neither edition is hidden, and Problems are not merged across them.

#### FR-8: Child Home and session length
The child's Home screen shows: today's Assignment (if any), a "Luyện lại" (practise again) card if the Retry Queue isn't empty, the current Streak, total Stars and latest badges, and a "Tiếp tục" (continue) card for the last unfinished Session.
- Home needs no reading. Every card has an icon and a 🔊 label that plays its name aloud.
- A Lesson longer than 10 Problems is split into Sessions of at most 10, to fit a 15–20 minute sitting.

### 4.3 Problem Player
**Description:** Shows one Problem at a time with the control that matches its Problem Type. Designed for a 6-year-old's fingers and attention: big targets, one action at a time, audio first. Realizes UJ-1.

#### FR-9: Interactive Problem Types
The player supports these Problem Types:

| Type | Used for |
|---|---|
| `number_input` | Missing numbers, before and after, word-problem answers |
| `compare` | `<` `>` `=` |
| `multiple_choice` | Text or image options |
| `order` | Sort numbers by dragging |
| `number_tree` | Number bonds, number trees and number houses |
| `grid_fill` | Sudoku-like grids, tables |
| `match` | Draw lines between two columns |
| `count_image` | Count the objects in a cropped image |
| `image_select` | Tap the right picture or region |
| `dot_draw` | Tap to add dots or objects that match a number |
| `connect_dots` | Tap numbered dots in order (1 → 10) |
| `spot_difference` | Tap the differences (hotspots) between two images |
| `expression_input` | Calculations for grades 3–5 |
| `fallback` | Page image plus self-check |

- Each type has its own on-screen number pad or tap control, so no system keyboard is needed on a tablet.
- A Problem with several Parts shows them in sequence or together, as set for each Problem during extraction (FR-2) and editable in Content Review.

#### FR-10: Read aloud
Every instruction, Part, answer option, Hint, Solution and Concept Guide has a 🔊 button that plays Vietnamese speech. A Problem's instruction plays automatically when the Problem opens (the parent can switch this off per Child Profile).

#### FR-11: Fallback self-check
For a `fallback` Problem, the child sees the cropped page image. They do the work (on paper or aloud), tap "Xem đáp án" (see answer) to reveal the Solution, and mark "Em làm đúng / chưa đúng" (I got it right / not yet).
- "Em làm đúng" earns 1 Star (FR-16). "Em chưa đúng" adds the Problem to the Retry Queue (FR-17).
- Self-checked results are shown in the dashboard but are **not** counted in first-try accuracy (FR-19, SM-4).

### 4.4 Grading, Hints and Solutions
**Description:** Answers are marked instantly. Help comes step by step: first a Hint, then the Solution. Realizes UJ-1.

#### FR-12: Grade Attempts
The system grades each Part against its Answer Key.
- Numbers match however they are formatted (`07` = `7`; for grades 4–5, `3,5` = `3.5`).
- `order` and `match` Parts are right only if the whole answer is right. For `grid_fill` and other Parts with several Answer Slots, the Part is wrong if any slot is wrong, and each wrong slot is highlighted.
- `expression_input` accepts any expression that evaluates to the correct value, unless the Problem requires a specific form.

#### FR-13: Staged help
First wrong Attempt on a Part: the Hint plays, and the Problem is added to the Retry Queue (FR-17). Second wrong Attempt: the Solution is shown and read aloud. The child can also ask for the Hint before answering (Stars per FR-16).

#### FR-14: Session summary
At the end of a Session, the child sees Stars earned, number of Problems correct on the first try, Streak status, and a button for "Luyện lại bài sai" (practise the ones I got wrong).

#### FR-23: Quiz mode for "Phiếu tự luyện cuối tuần"
The end-of-week practice sheet can be played as a quiz: no Hints and no marking during play, then everything is graded at the end with the Solutions available. A Problem with any wrong Part is added to the Retry Queue (FR-17). A Problem with every Part correct earns 3 Stars and any other Problem earns 0, since no Hints or second tries are available.

### 4.5 Concept Guides
**Description:** Short spoken explanations that a child can reach from any Problem. Realizes UJ-1 (help when stuck).

#### FR-15: Open a Concept Guide from a Problem or from the library
The child or parent can open the Concept Guide for any Concept tagged on the current Problem, or from Concept browsing. A guide has a short explanation, one worked example and a "Luyện tập" (practise) button that starts a Concept practice set.
- Every guide has audio and fits on one tablet screen without scrolling. [ASSUMPTION]

### 4.6 Motivation
**Description:** Rewards that build a daily habit without rewarding speed over accuracy (see SM-C1). Realizes UJ-1.

#### FR-16: Stars, Streaks and badges
Stars, the Streak and milestone badges (for example "Hoàn thành Tuần 1", finished week 1; "7 ngày liên tiếp", 7 days in a row) are recorded per Child Profile and shown on Home.
- Stars per Problem: 0 if the Solution was shown for any Part; otherwise 1 if any Part needed a Hint or a second try; otherwise 3. A `fallback` Problem self-marked correct earns 1.
- Rewards stay inside the app. No real-world reward rules. [ASSUMPTION]

#### FR-17: Retry Queue
A Problem enters the Retry Queue when any of its Parts gets a wrong Attempt (including in quiz mode, FR-23), or when a `fallback` Problem is self-marked "chưa đúng" (FR-11). Problems in the Retry Queue come back on the next calendar day or later (counted from the last wrong Attempt), in a "Luyện lại" (practise again) Session. A Problem leaves the Retry Queue after every Part is answered correctly on the first try in 2 separate Sessions of any kind, not necessarily in a row. A `fallback` Problem leaves after being self-marked "Em làm đúng" in 2 separate Sessions.

### 4.7 Parent Area
**Description:** A PIN-protected area for oversight, Assignments, Content Review (FR-6) and worksheets (§4.8). Realizes UJ-2.

#### FR-18: Child Profiles and PIN
The parent can create Child Profiles (name, avatar, Grade) and set the Parent Area PIN. v1 is built for 1 child and supports up to 4. [ASSUMPTION: one child now; Anh's answer "1" read as one child]

#### FR-19: Progress dashboard
For each child, the dashboard shows: Sessions and time per day and week; accuracy on the first try; progress per Book and Unit; the weakest Concepts, ranked by first-try accuracy (only Concepts with at least 5 Attempts are ranked); and recent mistakes with the child's answer next to the correct one.

#### FR-20: Assignments
The parent can assign any Problem Set, or a Concept practice set, to a date. The Assignment shows on the child's Home that day. It is done when all Sessions of its Problem Set are completed; if unfinished, it carries over to the next day. The dashboard shows each Assignment's status.

#### FR-21: Error Reports
The parent can flag a Problem. The child can also flag one with a simple 🚩 button, which sends the report to the parent. A Problem flagged by the parent is hidden from the child until it is resolved in Content Review. A child's 🚩 doesn't hide the Problem.

### 4.8 Printable Worksheets
**Description:** Paper practice for times away from the tablet. Realizes UJ-3.

#### FR-22: Print a Problem Set
The parent can print any Problem Set as an A4 worksheet (problems plus an answer page) using the browser's print function or "Save as PDF".
- Interactive types print in a paper-friendly layout: empty boxes, and for `match`, dots to connect.

## 5. Cross-Cutting NFRs

- **NFR-1 Offline:** once the content is built, every child-facing feature works with no internet connection, including audio. Only extraction and audio regeneration need internet.
- **NFR-2 Devices:** a tablet (iPad or Android, in landscape and portrait) and a PC browser (Chrome or Edge), both reaching one local server on the home PC over the home LAN. Use away from home is not supported in v1. [ASSUMPTION]
- **NFR-3 Child-friendly:** touch targets at least 64 px; at most one text instruction on screen, always with audio; no ads, no external links, no chat. The voice must sound natural and friendly to a young child.
- **NFR-4 Speed:** a Problem shows in under 1 second and audio starts in under 0.5 seconds on the home LAN.
- **NFR-5 Language:** all child and parent screens are in Vietnamese, with correct diacritics.
- **NFR-6 Privacy:** all data stays on the home PC, and nothing is sent outside except the extraction API calls, which carry page images only.
- **NFR-7 Data safety:** progress is saved after every Attempt, so closing the tablet loses nothing. Backup and restore is a single file export.

## 6. Non-Goals
- Not a general maths app: content comes only from the Archimedes Books.
- No live AI tutor or chat at runtime.
- No speech recognition or spoken answers.
- No cloud accounts, sharing, or publishing of Book content.
- No ranking or competition between children.

## 7. MVP Scope

**In:** FR-1 to FR-23 for all 30 Toán Books. Built in this order:
1. Pilot extraction on about 3 grade-1 Lessons, with Content Review (FR-6) and the Problem Player for the Problem Types grade-1 pages need. Ends at the go/no-go gate (FR-5).
2. Full extraction, plus Library, Grading, audio and Motivation.
3. The rest of the Parent Area, Concept Guides, quiz mode and worksheets.

**Why all 30 Books for a grade-1 child:** the pipeline cost is paid once, the grade 2–5 Books serve the same child in later years (and any siblings), and the go/no-go gate stops the run early if quality or cost is poor.

**Out (phase 2):** the Tiếng Việt Books (the same pipeline with new Problem Types for reading and writing); adaptive practice that picks Problems automatically; more than 4 children.

## 8. Success Metrics

- **SM-1 (independence):** Bin finishes a 10-Problem Session with no adult help in the first week. Validates FR-8 to FR-13.
- **SM-2 (habit):** at least 5 practice days per week over the first month. Validates FR-16 and FR-20.
- **SM-3 (content quality):** at least 95% of Problems are **interactive** (not `fallback`), and at least 98% of Answer Keys are correct on a random check of 100 Problems. Validates FR-2 and FR-3.
- **SM-4 (learning):** first-try accuracy on the weakest Concept rises between week 1 and week 4. Validates FR-15, FR-17 and FR-19.
- **SM-5 (the real goal):** a better score on the child's school maths tests over the first term. Observed by Anh; the app does not measure this.
- **SM-C1 (counter-metric):** do **not** push up the number of Stars or Problems per day. Racing through easy sets to collect Stars is a failure mode, and first-try accuracy on assigned work matters more.

## 9. Key Risks
- **Picture-heavy grade-1 pages** may not fit the Problem Types. Mitigation: pilot first, plus the go/no-go gate (FR-5).
- **A wrong Answer Key teaches the child a mistake.** Mitigation: double generation and code checks (FR-3), the Error Report (FR-21), and the SM-3 spot-check.
- **Extraction cost and time for about 2,140 pages.** Mitigation: the pilot estimate and Anh's confirmation (FR-5).

## 10. Open Questions
1. What is the real extraction cost and time per page? Measured in the pilot.
2. Which grade-1 page layouts need Problem Types not listed in FR-9? The pilot will show this (see the gate in FR-5).
3. Product name: is "Học Tập" final?

## 11. Assumptions Index
- UJ-1: persona "Bin", 6 years old, a family tablet, practice after dinner.
- FR-3: Problems whose Answer Keys disagree are hidden, not shown with a warning.
- FR-5: the pilot gate thresholds (15% fallback, 98% accuracy) come from the brief's targets.
- FR-6: manual edits survive re-extraction.
- FR-7: the child's Home is limited to their own Grade.
- FR-15: a Concept Guide fits on one screen.
- FR-16: rewards stay inside the app.
- FR-18: "1" meant one child; the app supports up to 4.
- NFR-2: devices are a tablet plus a PC browser, served from a local PC; the tablet works only on the home network in v1.
