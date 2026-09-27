# PRD Quality Review — Học Tập

- **PRD:** `_bmad-output/planning-artifacts/prds/prd-hoctap-2026-09-26/prd.md` (+ `addendum.md`)
- **Rubric:** `.claude/skills/bmad-prd/assets/prd-validation-checklist.md`
- **Stakes / shape:** family hobby project, chain-top (feeds UX → architecture → stories), consumer-style UX with a 6-year-old primary user.

## Overall verdict

This is a lean, honest PRD with a real thesis ("the same books the school uses, made interactive and spoken"), a well-built Glossary, concrete NFR bounds and user journeys that drive the design. It is fit for UX and architecture to start. The risk is in story-level done-ness. The rules for how the child's loop is scored and recycled (Retry Queue entry, Stars per Part vs per Problem, what a `fallback` self-check counts as) contradict each other or are missing. Several lifecycle behaviours (Assignments, hidden Problems, audio after edits) are left for story writers to invent. None of this needs a rethink, just a focused tightening pass on §3, §4.3–4.7 and §8.

## Decision-readiness — adequate

Most decisions are stated as decisions. Hiding `needs_review` Problems (FR-3), turning worked examples into Concept Guide material rather than Problems (§4.1), no runtime AI or speech recognition (§6), and the rejected alternatives in `addendum.md` ("Rejected: Tesseract-only extraction… speech in the browser… runtime AI") all say what was given up and why. The Open Questions in §9 are genuinely open, and two of them carry decision rules ("If it's above 15%, new Problem Types are needed before the full run").

The weak spot is the pilot → full-run gate and the breadth of MVP. §7 puts "FR-1 to FR-22 for all 30 Toán Books" (grades 1–5) in scope for a grade-1 child. The only guard on cost is OQ1, which has no threshold ("decides whether all 30 Books are run at once", but against what?). Extracting grades 2–5 now buys little for the thesis but adds API cost, audio generation for thousands of items, and a Content Review burden no single parent can clear. The PRD doesn't name that trade-off. OQ4 (which edition the child sees) is something Anh can answer today, and it shapes FR-7, FR-8 and FR-20.

### Findings
- **medium** No go/no-go criteria for the full extraction run (§7, §9 OQ1, FR-5) — FR-5 shows "a cost estimate… after the pilot, before the full run", but nothing says what estimate or quality level lets the run go ahead, or whether grades 2–5 can be deferred. *Fix:* add a budget ceiling (for example "≤ X USD total / ≤ Y USD per page") and a quality bar from the pilot (SM-3-style spot check) as explicit gate conditions. Name the option "grade 1 (+2) now, grades 3–5 later" and say whether it was chosen or rejected.
- **medium** OQ4 is answerable now and blocks design (§9 OQ4) — whether the child sees both editions or only the school's current one changes Home, Library defaults (FR-7) and which Problem Sets can be assigned (FR-20). *Fix:* resolve it with Anh (for example "default to the 2024-25 edition; 2020 reachable from Library") and record it as a decision or `[ASSUMPTION]`.
- **low** No `[NOTE FOR PM]` callouts at real tensions (whole doc) — tensions such as cost vs breadth and parent review load vs auto-publishing are handled implicitly. Acceptable at hobby stakes, but the two above deserve callouts.

## Substance over theater — strong

There's no persona theater. The two actors (Bin, Anh) each drive concrete decisions: no reading on Home (FR-8), 64 px targets (§5), the PIN-gated Parent Area (FR-18). The Vision is specific to this product and could not be dropped into another PRD. The NFRs have real thresholds ("a Problem shows in under 1 second and audio starts in under 0.5 seconds on the home LAN", "touch targets at least 64 px"). There is no invented differentiation section. The counter-metric SM-C1 shows real thinking about the failure mode.

### Findings
- **low** Leftover conversational text (title line 9, FR-18) — "*Working title. Please confirm.*" and "[ASSUMPTION: "1" in your answer meant one child]" read as chat, not document. *Fix:* confirm the title. Rephrase the tag as "[ASSUMPTION: one child in v1; the design allows up to 4]".

## Strategic coherence — adequate

The thesis is explicit and the features clearly serve the loop: extraction → spoken player → staged help → Retry Queue → parent dashboard/Assignment. The build order in §7 follows the thesis (pilot plus grade-1 player first). A counter-metric exists.

The metrics only half-validate the thesis. The bet ends with "that practice will show up in school marks", but no SM looks at school results, even qualitatively. SM-4 says accuracy on the weakest Concept "rises", with no magnitude and no baseline rule (the weakest Concept in week 1 may differ from week 4). SM-2 mixes two definitions: a Streak is defined as consecutive days (§3), yet the target is "a Streak of at least 5 days per week", which is days-per-week, not a streak. Scope breadth (grades 3–5, `expression_input`) serves a future child, not the current thesis. This is fine if it is stated, but it isn't.

### Findings
- **medium** Learning metric lacks magnitude and the thesis's school-marks claim is unmeasured (§8 SM-4, §1) — "first-try accuracy… rises" passes on a 1-point gain, and the weakest Concept is a moving target. *Fix:* fix the Concept at week 1 and set a target (for example "+15 points by week 4"). Add a light qualitative SM such as "Anh notes no regression / improvement on school worksheets for the practised Units", or drop "school marks" from the bet.
- **low** SM-2 conflicts with the Glossary's Streak definition (§8 SM-2 vs §3 Streak) — *Fix:* say "at least 5 practice days per week for 4 weeks", or state a Streak length.
- **low** Counter-metric not observable (§8 SM-C1) — "do not push up Stars" gives no signal to watch. *Fix:* name a check, for example "first-try accuracy on Assignments does not fall while Problems/day rises".

## Done-ness clarity — thin

Some FRs are excellent: FR-5 ("Killing the process and restarting it re-processes no page that was already completed"), FR-12 (`07` = `7`, `3,5` = `3.5`), FR-17 (the exit rule), FR-1 (30 Books, exactly once). But the rules of the core child loop are inconsistent or missing. Those are exactly the parts where story writers will guess, and where a 6-year-old will notice.

### Findings
- **high** Retry Queue entry rule contradicts itself, and the unit is unclear (FR-13, FR-17, §3 Retry Queue, UJ-1 edge case) — FR-13 adds a Problem only after the *second* wrong Attempt. FR-17 and the Glossary say "Problems the child got wrong come back", which a first-wrong-then-right Problem also matches. Grading is per Part (FR-12, §3 Attempt), but the queue holds Problems. With multi-Part Problems it's unclear whether one failed Part sends the whole Problem back. Also missing: what enters the queue from Hint-requested or `fallback` "chưa đúng" answers. *Fix:* write one rule, for example "A Problem enters the Retry Queue when any Part reaches the Solution stage (2 wrong Attempts) or the child marks a `fallback` 'chưa đúng'. It is retried as a whole Problem." Then align FR-17 and the Glossary.
- **high** `fallback` self-check has no scoring consequences (FR-11) — up to 15% of Problems (OQ2) are `fallback`, but FR-11 doesn't say whether "Em làm đúng" earns Stars, whether "chưa đúng" goes to the Retry Queue, or whether self-marks count toward first-try accuracy in FR-19 and SM-4. This feeds four other FRs (FR-14, FR-16, FR-17, FR-19). *Fix:* add bullets, for example "Self-marked correct earns 1 Star; 'chưa đúng' enters the Retry Queue; self-marked results are excluded from first-try accuracy."
- **medium** Star arithmetic doesn't match the journeys (§3 Star, UJ-1, FR-7) — Stars are per Part at 3/1/0, yet UJ-1 shows "7 of 8 stars" after 8 Problems and FR-7 shows Lesson progress as "5/8 ⭐". Neither matches 3-per-Part. *Fix:* choose one display model (Stars earned out of max, or Problems completed) and define Lesson progress and the Session summary against it.
- **medium** Vague or unbounded phrases that stories can't test (FR-3, FR-9, FR-19, FR-21, FR-22) — "suitable for a grade-1 to grade-5 child" (FR-3: by what check? sentence length, vocabulary?). "shows them in sequence or together, as the Problem's layout requires" (FR-9: who decides, and is it an extracted field?). "recent mistakes" (FR-19: how many, what time window?). FR-21 doesn't say what the child sees after tapping 🚩 (skip? continue?). FR-22 doesn't say whether the answer page has Answer Keys only or Solutions, or how `fallback` prints. *Fix:* add one testable bullet to each (for example "Hints ≤ 15 words", "layout is an extracted field `parts_layout: sequential|together`", "last 20 mistakes", "flagged Problem is skipped for this Session", "answer page lists Answer Keys only").
- **medium** Assignment lifecycle undefined (FR-20, FR-8) — no rules for more than one Assignment per day, an Assignment left unfinished (carry over? disappear at midnight?), or what counts as "done" for the Assignment and for SM-C1's "assigned work". *Fix:* add bullets: one per day or an ordered list; unfinished Assignments stay on Home until completed or replaced; done = Session reaches the summary.
- **medium** Visibility default for new content is unstated (FR-3, FR-6, FR-21, FR-7) — FR-6 lets Anh "approve or hide" a Problem, but it doesn't say whether extracted Problems are visible by default or only after approval. That choice decides whether the full run is usable without reviewing thousands of items. It's also unclear how hidden Problems affect Lesson counts ("5/8 ⭐") and Session length. *Fix:* state "Extracted Problems are visible unless `needs_review` or parent-flagged; hidden Problems are left out of Lesson totals."
- **low** FR-10 and FR-14 have no testable bullets (FR-10, FR-14) — FR-10 doesn't say where the per-profile auto-play toggle lives, and FR-14 doesn't say what "Luyện lại bài sai" includes (Parts with any wrong Attempt, or only Solution-stage ones). *Fix:* one bullet each.

## Scope honesty — adequate

§6 Non-Goals does real work (no runtime AI, no speech recognition, no cloud). §7 "Out (phase 2)" names what was deferred. The Assumptions Index round-trips cleanly: 8 inline tags, 8 index entries. Open-item density (4 OQs + 8 assumptions, 0 PM notes) is fine for hobby stakes.

Two cross-cutting tensions are left for the reader to infer. First, "Offline" (§5) actually means *no internet but home LAN required*: the tablet talks to "one local server" on the home PC. So the app likely doesn't work away from home, which UJ-3 hints at (print a worksheet for the trip) but never says. The addendum's PWA note suggests on-device caching might be expected. Second, audio is "pre-generated… during the build" (addendum) while FR-6 allows text edits in Content Review. Nothing says whether edited text gets new audio, and if the TTS engine is a cloud one, that step needs internet, which conflicts with "Only extraction needs internet".

### Findings
- **medium** "Offline" is ambiguous: LAN-bound vs truly on-device (§5 Offline/Devices, UJ-3, addendum Runtime) — this decides whether architecture must build a PWA offline cache and sync progress. *Fix:* state it explicitly, for example "[NON-GOAL for MVP] Using the tablet away from the home network; Offline means no internet, LAN required", or require PWA caching of assigned Problem Sets with sync-on-return.
- **medium** Audio after Content Review edits is unspecified (FR-6, FR-10, §5 Offline, addendum Audio) — edited Hints/Solutions would otherwise play stale audio or none. *Fix:* add an FR-6 bullet: "Saving an edit regenerates that item's audio; if regeneration is unavailable (offline TTS/internet), the item is marked and 🔊 is disabled until it succeeds."
- **medium** Concept list source and granularity undecided (FR-4, §3 Concept, UJ-2, SM-4) — "a shared Concept list for each Grade" doesn't say whether the list is predefined (curriculum-based) or generated during extraction, and the examples disagree on granularity ("So sánh số trong phạm vi 10" in §3 vs "So sánh số" in UJ-2). Cross-edition merging, the "weakest Concepts" dashboard and SM-4 all depend on it. *Fix:* decide who owns the list (for example "generated in the pilot, then frozen and edited by Anh in Content Review"), give the granularity rule, and tag it `[ASSUMPTION]` if not confirmed.

## Downstream usability — adequate

A strong Glossary (§3) is used consistently for its core nouns (Book, Unit, Lesson, Problem Set, Part, Answer Slot, Attempt, Session). IDs are contiguous and unique (UJ-1–4, FR-1–22, SM-1–4 + SM-C1), and the feature sections say which UJs they realize. The addendum is cleanly separated. Gaps: some set-type nouns drift and aren't defined, a few sections lack the Description/"Realizes" line, and FR-1 relies on another document for its duplicate list.

### Findings
- **low** Problem Set sub-types drift and aren't defined (§3 Problem Set, FR-15, FR-20, FR-14) — "Custom Set", "Concept practice", "Concept practice set", "auto-built set for a Concept" and "Luyện lại bài sai" set are all used, but only "Problem Set" is defined. `needs_review`, "badge" and "Home" are also used as terms without definitions. *Fix:* add Glossary entries (Custom Set with its sub-kinds: Retry set, Concept practice set, Wrong-answers set; Badge; Home; `needs_review` status).
- **low** FR-1 isn't self-contained (FR-1) — "The duplicates listed in the brief's addendum are excluded" means a story writer has to open another document. *Fix:* inline the duplicate file names or the rule (or copy them into this addendum).
- **low** §4.5, §4.6 and §4.8 lack a Description and "Realizes UJ-n" line (FR-15–17, FR-22) — FR-22 clearly realizes UJ-3, and FR-16/17 realize UJ-1. *Fix:* add one line each for traceability.

## Shape fit — strong

The shape matches a hobby, chain-top consumer-style product. There are four named-protagonist UJs (Bin, Anh) that carry context inline, a light capability spec underneath, and implementation pushed to the addendum. It isn't over-formalized: two actors, no persona matrix, a short NFR block. UJ-4 (the one-time operator job) is rightly kept brief.

### Findings
_None._

## Mechanical notes
- **Assumptions Index roundtrip:** clean. Inline tags at UJ-1, FR-3, FR-6, FR-7, FR-15, FR-16, FR-18 and §5 all appear in §10. Slight wording drift for FR-7: inline says Home shows only the child's own Grade and other Grades are reachable, while the index says "Home is limited to their own Grade". Harmless.
- **IDs:** UJ-1…4, FR-1…22, SM-1…4, SM-C1 are contiguous and unique. All FR references in §7/§8 resolve.
- **Glossary drift:** "Concept practice" (§3) / "Concept practice set" (FR-15) / "auto-built set for a Concept" (FR-20). "Tuần"/"Tiết" are used as Unit/Lesson instances, which is consistent. "badges" isn't in the Glossary.
- **SM traceability:** SM-1 claims to validate "FR-8 to FR-13", which includes FR-10 audio (good) but skips FR-15, which is arguably part of independence. Minor.
- **Required sections:** all present for hobby stakes (Vision, Users/JTBD, UJs, Glossary, FRs, NFRs, Non-Goals, Scope, SMs, OQs, Assumptions).
- **Frontmatter:** `status: draft` should change when the PRD is finalized.
