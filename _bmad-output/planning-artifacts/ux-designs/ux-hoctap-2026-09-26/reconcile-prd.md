# Input reconciliation: PRD vs UX spines

- **PRD (source of truth):** `../../prds/prd-hoctap-2026-09-26/prd.md`
- **Spines checked:** `DESIGN.md`, `EXPERIENCE.md` (both in this folder)
- **Date:** 2026-09-26
- **Scope:** (1) surface closure, (2) contradictions with PRD rules, (3) Glossary drift, (4) token references, (5) palette contrast.
- **Severity:** **H** blocks a PRD requirement or a WCAG AA failure on a core control · **M** the behaviour is under-specified and dev will have to guess · **L** wording or polish.

---

## 1. Surface closure

### 1a. FR/NFR → EXPERIENCE coverage

| PRD item | Implied surface / behaviour | EXPERIENCE coverage | Gap | Sev |
|---|---|---|---|---|
| FR-1 | Book catalogue listing | Extraction surface (implicit) | Nothing shows the catalogue or the excluded duplicates. Acceptable as a backend-only item. | L |
| FR-2 | Run extraction on all Books, one Book, or chosen pages | Extraction: "Pilot and full run" | No range picker (one Book, or a page range). | M |
| FR-3 | `needs_review` Problems are hidden | State "Problem hidden" + Content Review list | Covered. | — |
| FR-4 | Anh edits the per-Grade Concept list in Content Review | — | **Missing.** Content Review has no Concept-list editor and no view for re-tagging a Problem's Concepts. | M |
| FR-5 | Per-page status, failures, pages/min, API cost; pilot gate | States "Extraction running", "Pilot finished"; Flow 4 | Pages/min is not shown. The gate needs "≥98% of pilot Answer Keys correct **when Anh checks them**", but there is no way to mark a key as checked or correct, so the % has no source. | M |
| FR-6 | Browse **all** extracted Problems beside the page image; edit text, Answer Key, Hint, Solution, Problem Type, Parts display mode; approve or hide; audio regenerates | IA Content Review = "review list (`needs_review` + Error Reports)" | Only the review list is specified. Missing: browsing all Problems (by Book/Unit/Lesson), the edit form, the approve/hide controls, a "regenerating audio" state, and editing the Parts sequence/together setting (FR-9). | **H** |
| FR-7 | Grade → Book → Unit → Lesson, Concept → Problems; Lesson progress "5/8 ✓"; own Grade by default, other Grades reachable; both Editions listed | IA Library + Concept tab | Lesson progress badge, the default Grade, and how to reach other Grades are not described. A **parent Library** is used by Assign (IA), Flow 2 and Flow 3, but it is not an IA row. | M |
| FR-8 | Home: Assignment, Luyện lại, Streak, total Stars, **latest badges**, Tiếp tục; 🔊 on every card; **split Lessons > 10 Problems into Sessions ≤ 10** | IA Home: "Assignment, Luyện lại, Tiếp tục, Streak and Stars" | **Badges are missing from Home.** Splitting into Sessions is not covered anywhere: no chunk indicator ("Phần 1/2"), no rule for what the Library progress, the progress dots, the Assignment card and the "Tiếp tục" card show for a split Lesson. | **H** |
| FR-9 | 14 Problem Types; multi-Part shown in sequence or together | Problem Type interactions table | All 14 types covered. The multi-Part layout (sequence vs together, and how ✔ and the progress dots behave per Part) is not described. | M |
| FR-10 | 🔊 everywhere; auto-play toggle per Child Profile | Audio Behaviour; Settings | Covered. | — |
| FR-11 | Fallback self-check; 1 Star; Retry on "chưa đúng"; excluded from first-try accuracy | `fallback` row | Covered in the player. The dashboard does not say that self-checked results are shown separately (see FR-19). | L |
| FR-12 | Formatting-tolerant grading; each wrong slot highlighted in multi-slot Parts | Answer slot, ✔ Kiểm tra | Per-slot highlighting for `grid_fill`/multi-slot is implied but not stated. On a second try, should correct slots stay locked or stay editable? Not stated. | L |
| FR-13 | Hint on 1st wrong + Retry Queue; Solution on 2nd wrong; Hint on demand | Hint bubble, Solution panel, states | Covered. The 💡 (Hint on demand), 📖 and 🚩 buttons have no placement in DESIGN's Problem top bar ("back, progress dots, 🔊"). | L |
| FR-14 | Summary with Stars, first-try count, Streak, "Luyện lại bài sai" | IA Session summary; Flow 1 step 7 | The button is listed, but what it does is not defined (see §2, Retry timing). | M |
| **FR-23** | **Quiz mode for "Phiếu tự luyện cuối tuần": no Hints and no marking during play, graded at the end, Solutions available, 3 or 0 Stars** | **—** | **Entirely missing.** There is no way to enter quiz mode, no player variant that suppresses feedback, Hints, 💡 and the second try, no end-of-quiz results and review screen with Solutions, and no Star rule in the summary. | **H** |
| FR-15 | Concept Guide from the Problem or the Library; one screen; "Luyện tập" starts a Concept practice set | IA Concept Guide; 📖 overlay | Covered as a surface. How a Concept practice set is built (which Problems, how many, which Edition, max 10) is not defined. | M |
| FR-16 | Stars, Streak, **milestone badges** recorded and shown on Home | Stars/Streak everywhere | **No badge surface, earned-badge moment, or badge list** on any child screen. | **H** |
| FR-17 | Retry Queue: due the next calendar day or later; exits after first-try correct in 2 separate Sessions | Home "Luyện lại" card; state "Second wrong" | The due-date rule is not reflected: EXPERIENCE shows the card when the queue is non-empty, but Problems added today are not due yet. There is no "N/2 mastered" state and no rule for how many Problems a Luyện lại Session contains (≤10?). | M |
| FR-18 | Create Child Profiles (name, avatar, Grade); set the PIN; up to 4 | Profile picker, PIN gate, Settings | **No first-run setup:** creating the first profile and setting the PIN before any PIN gate exists. "First launch, no content" covers content only. | M |
| FR-19 | Sessions and time per day/week; first-try accuracy; progress per Book and Unit; weakest Concepts (≥5 Attempts); recent mistakes with the child's answer vs the correct one | Dashboard: "This week, weakest Concepts, recent mistakes, Assignment status" | Missing: time spent, per-day breakdown, progress per Book and Unit, the ≥5-Attempts threshold (and its empty state), and a separate line for self-checked results. There is no child switcher for 2–4 profiles. | M |
| FR-20 | Assign any Problem Set or Concept practice set to a date; done when all Sessions complete; carry-over; status on the dashboard | Assign surface; states "No Assignment", "carried over"; Flow 2 | Only "Chưa làm" is named. The full status set is undefined (for example: not started / in progress x/y Sessions / done / carried over). Several Assignments on the same day, and editing or deleting an Assignment, are not covered. | M |
| FR-21 | Parent flags; child 🚩 sends a report but **doesn't hide**; resolve in Content Review | 🚩 flag; Flow 2 edge; state "Problem hidden (… or flagged)" | "Flagged" is ambiguous. It must say **parent-flagged only** (see §2). The PRD requires resolving a report ("fixes or confirms"), but no resolve or dismiss action is specified. | M |
| FR-22 | Print any Problem Set; `match` printed as dots | Print surface; Responsive/Print | The `match` dot rendering and the per-type print layouts are not described (only "empty boxes"). | L |
| NFR-1 | Offline child features, including audio | Server-unreachable state | This is consistent with the LAN model. PWA asset/audio caching is not described. | L |
| NFR-3 | ≥64px targets; one text instruction; audio | Accessibility Floor | The icon-only chrome (⬅, 🔒, 💡, 📖, 🚩) contradicts DESIGN Do's & Don'ts: "no icon-only buttons without a label and 🔊". | L |
| NFR-4 | Problem < 1 s, audio < 0.5 s | — | No loading or skeleton state for the Problem or for audio. | L |
| NFR-7 | Save after every Attempt; **backup/restore = single-file export** | Settings lists "backup and restore"; "Tiếp tục" state | No flow or state for export (file name, success) or restore (choose file, confirm overwrite, failure). | M |

### 1b. IA surface → trace

Every IA row traces to an FR. Surfaces that are used but not traced or listed:

| Item | Where | Issue |
|---|---|---|
| Parent Library | IA "Assign" row, Flow 2 step 4, Flow 3 step 1 | Used but not an IA row. It needs its own row with "Giao bài" and "In phiếu" actions. |
| Parent menu | IA "Extraction", "Settings" | Not defined (a nav pattern for the Parent Area is missing). |
| "Học tiếp" card | State Patterns, "No Assignment today" | New behaviour (opens the next unfinished Lesson "in order") that is not in the PRD. It overlaps with "Tiếp tục" (FR-8), and "in order" is undefined across two Editions. Tag it `[ASSUMPTION]` or trace it. |
| Local progress buffering + sync | State "Server unreachable" | New behaviour, already tagged `[ASSUMPTION]`. It is compatible with NFR-7 but has architecture impact. |

---

## 2. Contradictions and risky readings of PRD rules

| Rule | PRD | EXPERIENCE / DESIGN | Issue | Sev |
|---|---|---|---|---|
| Stars | FR-16: Stars **per Problem** (3/1/0) | DESIGN Feedback banner "Correct: … and stars"; Flow 1 step 4 "3 Stars fly up" after ✔ | For multi-Part Problems, the banner fires per Part, but Stars are decided per Problem. State that Stars are awarded only when the Problem's last Part is finished. | M |
| Stars | FR-13/16 | Hint bubble "Stars then capped" | Consistent. Opening a Concept Guide (📖) mid-Problem: does it cap Stars? Neither document says. | L |
| Stars | FR-23: quiz = 3 or 0 | — | Not represented (see FR-23 gap). | H |
| Retry Queue timing | FR-17: back "on the next calendar day or later" | FR-14 summary button "Luyện lại bài sai" appears straight after the Session | There is tension (partly inherited from the PRD): does the immediate "Luyện lại bài sai" Session count as one of the 2 exit Sessions? Is it allowed the same day? EXPERIENCE must define this. | M |
| Retry Queue card | FR-8: card if the queue "isn't empty" | "Empty Retry Queue → card not shown" | Clarify: show the card only when a queued Problem is **due**, otherwise the card leads to an empty Session. | M |
| Sessions ≤ 10 | FR-8 | Flow 1 uses 8 Problems; nothing else | See FR-8. The Assignment is "done when all Sessions complete", so the Home card must show chunk progress. | H |
| Hidden Problems | FR-6/21: only `needs_review`, **parent**-flagged, or Anh-hidden Problems are hidden. A child's 🚩 doesn't hide. | State "Problem hidden (`needs_review` or flagged)" | Read literally, a child's flag would hide the Problem. Say "flagged by the parent". Also, if a Problem becomes hidden during an active Session, or while in the Retry Queue or an Assignment, the Session and Assignment counts must adjust. Not covered. | M |
| Quiz mode | FR-23 | Hint bubble, 💡, the Solution panel and the feedback banner are always on | These universal Problem patterns contradict quiz mode unless a quiz variant is specified. | H |
| Concept practice set | Glossary: a system-built Problem Set | Flow 2 step 4: "Giao bài on 'So sánh số', picks the **2024–25 Book's** set" | This mixes a Concept practice set (cross-Edition by FR-4) with a Book's Lesson. Decide whether a Concept practice set can be filtered by Edition. The PRD UJ-2 has the same ambiguity. | M |
| Assignment lifecycle | FR-20: carries over to the next day if unfinished | "Hôm qua" ribbon | This is wrong after 2+ days of carry-over. It should use the date or "Chưa xong" (not finished), with no guilt copy. There is also no status for a partially done multi-Session Assignment. | L |
| Badges | FR-16 | DESIGN Components and EXPERIENCE: none | Not designed at all. | H |
| Backup/restore | NFR-7 | Settings row only | See 1a. There is no destructive-restore confirmation. | M |
| PIN | FR-18 (no length) | "4-digit PIN" | This is an unstated assumption; tag it `[ASSUMPTION]`. | L |

---

## 3. Glossary drift

| Term in the spines | PRD Glossary | Note |
|---|---|---|
| "Học tiếp" (keep learning) card | not defined | A new concept that is easy to confuse with "Tiếp tục". Define it or drop it. |
| "parent Library", "parent menu" | not defined | Structural terms that are used but not in IA. |
| "answers ≥ 98%" (State Patterns, Pilot finished) | "Answer Keys … correct" | Use "Answer Keys ≥ 98% correct". |
| "slot" / "number slots" | **Answer Slot** | Casual shortening. Use "Answer Slot" at least on first use in Component Patterns. |
| "Lỗi gần đây" (recent mistakes) | "recent mistakes" (FR-19) | Fine, but these are Attempts, not Error Reports ("Báo lỗi"). Both use "lỗi", so watch the Vietnamese labels. Consider "Câu làm sai gần đây" (problems answered wrong recently). |
| "2024–25 Book" (en dash) | Edition `2024-25` | Cosmetic. Keep the Edition ID spelling in data labels. |
| "Luyện lại" Session | Retry Queue Session (Glossary: Problem Set) | Consistent. |
| "Streak", "Stars", "Session", "Problem Set" | ✓ | Used consistently. |
| **Practice days** | Glossary (SM-2) | Not surfaced on the dashboard. The PRD defines it, but no FR requires showing it, so this is optional. |

---

## 4. Token references (EXPERIENCE → DESIGN frontmatter)

| Reference in EXPERIENCE | Exists in DESIGN? |
|---|---|
| `{spacing.touch-min}` (Accessibility Floor) | ✓ 64px |
| `{spacing.key}` (Accessibility Floor) | ✓ 80px |
| "visual specs in DESIGN.md Components" | ✓ section exists |
| "Colour contrast is covered in DESIGN.md" | ✗ **DESIGN.md has no contrast section or ratios.** It is a dangling reference. |

Components that EXPERIENCE relies on but that have **no DESIGN token or component**:
- Solution panel
- Concept Guide overlay
- 💡, 📖 and 🚩 buttons
- Profile avatar tile
- Session summary
- Badge
- Quiz results
- `expression_input` keypad (DESIGN's number pad is 0–9, ⌫ and comma only; EXPERIENCE adds + − × : ( ) =)
- Locked `grid_fill` cell ("grey", no token)
- `match` line, `spot_difference` ring, `dot_draw` counter
- Offline screen
- Parent Area components (table, chart, form, review split view)

Other token issues:
- `button-check` has no `typography`.
- `feedback-correct` and `feedback-retry` have no text colour.
- `retry` is not given a text pairing.

---

## 5. Palette accessibility (WCAG 2.1 contrast ratios)

Label text is 18px/700. That is **below** the large-text threshold (18.66px bold / 24px regular), so it needs **4.5:1**. Non-text UI needs 3:1.

| Pair | Ratio | Use | Result |
|---|---|---|---|
| `ink-on-color` #FFFFFF on `primary` #1C7ED6 | **4.20** | button-primary label (18px/700) | **Fails AA** (4.5). Passes only for large text. |
| `ink-on-color` on `primary-pressed` #1864AB | 6.09 | pressed | Pass |
| `ink-on-color` on `success` #2F9E44 | **3.45** | ✔ Kiểm tra label | **Fails AA** for normal text. Passes large only if the label is ≥ 24px or ≥ 18.66px bold (typography not set). |
| `ink-on-color` on `success-pressed` #2B8A3E | 4.37 | pressed | Fails AA normal (just) |
| `ink-on-color` on `retry` #E8590C | **3.58** | any white-on-orange | **Fails AA** normal |
| `ink-secondary` #5C6178 on `surface-base` #FFF8EC | 5.79 | secondary text | Pass AA |
| `ink-secondary` on `surface-raised` #FFFFFF | 6.11 | | Pass |
| `ink-primary` #2B2D42 on `surface-base` | 12.78 | | Pass AAA |
| `slot-border` #A5B4C8 on `surface-raised` #FFFFFF | **2.11** | answer-slot / choice-chip border (the only cue for "write here") | **Fails 1.4.11** non-text (3:1) |
| `primary` icon on `primary-soft` #D0EBFF | 3.40 | 🔊 speaker icon | Pass 3:1 (thin margin) |
| `success` on `success-soft` | 3.00 | feedback accent | Borderline 3:1. Fails if used as text. |
| `retry` on `retry-soft` | 3.01 | feedback accent | Borderline 3:1. Fails if used as text. |
| `hint` #7048E8 on `hint-soft` #EDE7FF | 4.62 | Hint accent/text | Pass AA |
| `star` #FAB005 on `surface-base` | **1.76** | star counter/icon | Fails 3:1. Needs an outline or dark numerals. |
| `streak` #FF6B2C on `surface-base` | **2.69** | flame | Fails 3:1 |
| `surface-sunken` #F3EBDD on `surface-base` | **1.12** | progress-dot "todo" | **Effectively invisible.** The dots will not read. |
| `primary` on `surface-base` | 3.97 | any blue text | Fails AA for text |
| `ink-secondary` on `parent-surface` #F8F9FA | 5.80 | parent text | Pass |

**Suggested fixes (for the DESIGN owner):**
- Darken `primary` to about #1971C2 (≈4.9:1 with white).
- Darken `success` to about #2B8A3E, or use `ink-primary` text on `success`, or make the ✔ label ≥ 24px.
- Do not put white text on `retry`, or darken it to about #C2410C.
- Darken `slot-border` to about #7B8BA3 (≥3:1).
- Give the todo progress dots a `slot-border` outline.
- Outline the star and flame icons, and keep the counters in `ink-primary`.
- Add the ratios table to DESIGN.md so EXPERIENCE's reference resolves.

---

## Top gaps (priority order)

1. **FR-23 quiz mode is absent**, and the always-on Hint and feedback patterns contradict it. (EXPERIENCE Component Patterns, State Patterns, IA)
2. **FR-16 badges are not designed**, and Home omits "latest badges" (FR-8). (EXPERIENCE IA Home; DESIGN Components)
3. **FR-8 split into Sessions ≤ 10 is not handled**: chunk progress, Assignment completion, the Tiếp tục card. (EXPERIENCE State Patterns / Home)
4. **FR-6 Content Review is reduced to a review list**: no browse-all, edit form, approve/hide, Concept-list edit (FR-4), or Answer Key check marking for the FR-5 gate. (EXPERIENCE IA Content Review; Flow 4)
5. **White-on-colour contrast fails AA**: primary 4.20, success 3.45, retry 3.58. `slot-border` is 2.11 and the todo dots are 1.12. DESIGN has no contrast section, although EXPERIENCE points to one. (DESIGN colors / components)
6. **Retry Queue timing is undefined**: "due next day" vs the non-empty card, and the immediate "Luyện lại bài sai" button (FR-14 vs FR-17). The "Problem hidden … or flagged" state wrongly implies a child's 🚩 hides the Problem. (EXPERIENCE State Patterns)
