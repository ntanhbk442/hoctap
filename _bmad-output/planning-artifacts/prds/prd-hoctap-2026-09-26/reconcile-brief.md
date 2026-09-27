---
title: "Reconciliation: brief -> PRD (Học Tập)"
created: 2026-09-26
inputs:
  - planning-artifacts/briefs/brief-hoctap-2026-09-26/brief.md
  - planning-artifacts/briefs/brief-hoctap-2026-09-26/addendum.md
  - planning-artifacts/briefs/brief-hoctap-2026-09-26/.memlog.md
target:
  - planning-artifacts/prds/prd-hoctap-2026-09-26/prd.md
  - planning-artifacts/prds/prd-hoctap-2026-09-26/addendum.md
---

# Reconciliation: product brief vs PRD

Severity: **High** = the PRD contradicts or loses a settled brief decision/criterion; **Medium** = weakened or only implicit; **Low** = detail dropped that downstream steps may need.

## A. Gaps, contradictions and weakenings

| # | Sev | Brief says (source) | PRD state (location) | Gap |
|---|---|---|---|---|
| 1 | High | Success criterion **Outcome**: "a better score on the child's next school tests", observed by the parent (brief > Success Criteria). Goal = high marks at school (memlog decision). | §1 Vision names school marks as the central bet, but §8 Success Metrics has no school-score metric. SM-4 substitutes in-app first-try accuracy. | Dropped. The top-level outcome metric is gone; only a proxy remains. Add an SM for parent-observed school test results (qualitative, out-of-app). |
| 2 | High | Assumption: "At least 95% of problems can be made interactive. The rest are shown as page images" (brief > Assumptions to Validate). | §8 SM-3 counts `fallback` as "playable"; §9 Q2 only acts if grade-1 fallback exceeds **15%**. | Weakened. Brief implies <=5% fallback; PRD tolerates up to 15% before new types are built, and SM-3 can be met with heavy fallback. (Brief's own Success Criteria bullet is ambiguous too, but the Assumption is explicit.) Separate "interactive %" from "playable %". |
| 3 | High | Grade-1 type mapping (brief addendum): draw dots matching a number -> **dot counter / tap-to-add**; connect dots 1-10 -> **ordered tap**; fill in a sequence of shapes -> number inputs in a sequence; spot the difference -> **image hotspot**. | §4.3 FR-9 type table has `count_image` (count only, not produce), `image_select`, `order` (drag-sort numbers). No tap-to-add/produce-a-quantity type, no ordered-tap/connect-the-dots type. | Dropped. These grade-1 page types (the child's own grade, and the brief's #1 risk) have no matching widget, so they fall to `fallback`, feeding gap #2. PRD addendum only points to the brief addendum rather than mapping them. |
| 4 | High | Scope v1 = **both editions**; assumption: overlapping topics "kept as separate problem sets rather than merged" (brief > Scope, Assumptions; memlog). | §9 Q4 reopens whether the child should see only the edition the school currently uses. FR-4 merges Concepts across editions (fine), FR-1 lists all 30 books. | Contradiction risk. Q4 reopens a settled brief decision; if answered "one edition only", it contradicts brief scope. Reframe Q4 as a display/default question, not a scope question. |
| 5 | Medium | Brief has a **Key Risks** section: picture-heavy grade-1 pages; wrong answer keys teach mistakes; extraction cost/time (brief > Key Risks). | PRD has no Risks section. Mitigations are scattered (FR-3, FR-21, FR-5, §9 Q1/Q2). | Weakened. The risk framing (esp. "wrong keys teach the child mistakes" as the reason for the safeguards) is not carried; downstream steps lose the rationale. |
| 6 | Medium | Decision: "AI-generated answers/solutions are **trusted (no mandatory parent review)**; keep a report-error path" (memlog). Brief risk mitigation: "flag any disagreement". | FR-3 hides `needs_review` Problems from the child `[ASSUMPTION]`; FR-21 hides parent-flagged Problems until resolved in Content Review; UJ-4 has Anh check pilot problems in Content Review. | Tension. Hiding until resolved makes parent review mandatory for every disagreement, which the brief/memlog said is not required. At minimum flag this against the memlog decision in §10; consider "show with self-check" instead of hide. |
| 7 | Medium | Primary learner success: "practising on their own for **15–20 minutes** and coming away with **more right answers than yesterday**" (brief > Who This Serves). | FR-14 summary shows Stars/correct/Streak only; no session-length target anywhere; SM-1 only covers a 10-problem set. | Dropped. No target session length (sizing of Problem Sets/Sessions) and no day-over-day "better than yesterday" feedback to the child. |
| 8 | Medium | "The weekly self-practice sheet ('Phiếu tự luyện cuối tuần') **works as a short quiz**" (brief > Solution #4). | §3 Glossary treats it as an ordinary Lesson/Problem Set; no quiz mode behaviour (e.g. help deferred, score at end) in FR-7/FR-13/FR-14. | Dropped. Quiz behaviour distinct from practice is not specified. |
| 9 | Medium | Pilot purpose: "prove extraction quality and measure cost **before** the whole corpus is run" (brief > Exec Summary, Risks). | FR-5 shows a cost estimate after the pilot; §7 step 1 = pilot. No quality go/no-go gate (e.g. apply SM-3 thresholds to pilot). Content Review (FR-6) is needed in the pilot (UJ-4) but §7 places Parent Area in step 3. | Weakened. No explicit pilot exit criteria; build order puts the review tool after the full run it is meant to gate. |
| 10 | Low | Engagement: "practice on at least **5 days a week** for the first month (streak data)". | §8 SM-2: "a Streak of at least 5 days per week". §3 defines Streak as consecutive days. | Wording drift. "Streak of 5 days per week" is not the same as 5 practice days/week (a 5-day streak requires consecutive days). Restate as practice days per week. |
| 11 | Low | Duplicates: "for each pair, use the **higher-quality file** for page rendering"; "embedded text layers are bad OCR and should be **ignored**" (brief addendum > Source corpus). | FR-1 excludes duplicates but doesn't say which copy is kept; FR-2 ignores watermarks/QR/headers but not embedded text layers. | Dropped detail (only indirectly referenced via PRD addendum pointer). |
| 12 | Low | Environment facts: no `ANTHROPIC_API_KEY` present; 8 cores / 9 GB RAM / WSL2, no GPU (brief addendum > Technical notes). | PRD addendum points to brief addendum for corpus/OCR/type mapping but not these constraints. | Not carried forward to architecture handoff explicitly. |
| 13 | Low | Vision: other Archimedes parents could run it with **their own copies** of the books (brief > Vision). | §6 Non-Goals "No ... sharing"; vision not mentioned. | Dropped long-term vision (acceptable for v1, but it affects packaging/config choices; worth one line in §1 or §7 Out). |
| 14 | Low | Vision: "practice **adapts to weak topics automatically**". | §7 Out (phase 2): adaptive practice. | Consistent (deferred). No action; listed for completeness. |

## B. Carried through correctly (no action)

- One-time Claude vision extraction, no runtime AI, offline after build (§5 Offline, §6, addendum Rejected).
- Tesseract rejection and reasons (PRD addendum).
- Source link per problem: file, page, bounding box (FR-2).
- Answer generated twice + arithmetic checked by code + flag disagreement (FR-3).
- Pre-generated Vietnamese audio for problems, hints, solutions, guides; works without browser vi voice (FR-10, addendum).
- Hint on first mistake, worked solution on second (FR-13); concept links (FR-15).
- Browse by grade/book/week-chapter/lesson and by topic (FR-7).
- Parent dashboard: progress per book/topic, weak topics, time, recent mistakes, assign, report error (FR-19–21).
- Stars, streaks, badges, retry queue, printable worksheets with separate answer page (FR-16, FR-17, FR-22).
- Tablet layout, large touch targets, LAN/home PC, child profiles (§5, FR-18).
- Out of scope: Tiếng Việt (phase 2), speech input, cloud/multi-school, live AI tutor, public distribution (§6, §7).
- Grade-1 types built first; pilot first (§7).
- 95% coverage and 98% answer-key accuracy on 100-problem spot check (SM-3; see gap #2 on the interactive vs playable split).
- Independent 10-problem set with audio (SM-1, tightened to "first week").

## C. Suggested PRD edits (for the PRD owner; PRD not modified)

1. §8: add SM for parent-observed school test results; split SM-3 into interactive % (>=95% target per brief) and playable %.
2. FR-9: add `tap_to_add` (produce N dots/objects), `ordered_tap` (connect-the-dots), and an image-hotspot variant for spot-the-difference; or record that they are deliberately `fallback` and adjust §9 Q2.
3. §9 Q4: reframe as default/visibility, keeping both editions in v1 scope.
4. Add a short Risks section mirroring the brief's three risks.
5. FR-3/FR-21 + §10: note the tension with the "trusted, no mandatory review" decision.
6. FR-14/§5 or a new NFR: target session length 15–20 minutes; "better than yesterday" feedback.
7. Specify quiz behaviour for "Phiếu tự luyện cuối tuần".
8. §7: move Content Review (FR-6) into step 1 and add pilot exit criteria.
9. SM-2: reword to "practice on at least 5 days per week".
