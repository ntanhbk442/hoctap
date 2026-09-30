# Epic 5 Context: Concept Guides and Concept practice

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic lets Anh curate the per-Grade Concept list and its Concept Guides, and lets Bin open a spoken Concept Guide from any Problem and practise one Concept. A Guide is the short "why" behind the exercises: without it a grade-1 child who cannot read has only the hints and solutions of single Problems.

## Stories

- Story 5.1: Concept Guides generated and editable
- Story 5.2: Concept Guide screen and practice

## Requirements & Constraints

- Every Problem carries 1-3 Concepts from one curated list per Grade, shared by both Editions. Every Concept has a Guide.
- A Guide is a short explanation plus one worked example, built from the Book's theory boxes and "Ví dụ" blocks where the Book has them. It has audio and fits on one tablet screen without scrolling.
- The child or parent opens the Guide from the current Problem (📖) or from the Library's Concept tab. It has a "Luyện tập" button that starts a Concept practice Session.
- Concept practice: up to 10 visible Problems for the Concept, those not yet solved correctly on the first try first. Assignments may point at a Concept practice set (already shipped).
- Every Guide text needs a 🔊 button; child copy stays positive (no red, ✗ or "Sai!").
- Generation calls Claude and costs money; the builder never spends without an explicit opt-in.

## Technical Decisions

- Concepts have stable `concept_id`s (`g1.so-sanh-so`); the list is owned by `content.review`. Concept links are curated there, and the Concept name can be renamed without changing the id.
- Review is a field-level overlay with a base hash: Anh's edits are stored as overrides over the extracted or generated content, survive regeneration, and only `content.effective_concept_guide()` merges them. A regeneration that changes a field with an older `base_hash` raises a conflict flag; the override still wins.
- Speech is content-addressed through one normaliser; `speak-missing` synthesises every referenced key, including Guides, after publish and after any review edit. Answer keys are never read aloud.
- Session problem lists are frozen at start; all Problem Set resolution goes through the single `learning.problem_sets` resolver, including the `concept` kind.
- Only owners write their tables: `content.catalog` writes catalog rows, `content.review` writes review rows.

## UX & Interaction Patterns

- The Concept Guide screen is an overlay on the Problem; closing returns to the same Problem with the answer kept.
- Content Review has a "Khái niệm" tab for editing the Concept list per Grade; Guides are edited beside it.

## Cross-Story Dependencies

- Story 5.1 produces the Guide data, its overrides, effective view and audio; Story 5.2 only reads it (child screen, 📖 button, Library Concept tab, `concept` Session).
- Depends on Epic 1 (Concept curation, Content Review overlay, speak-missing, builder call and cost tracking), Epic 2 (audio player, Library) and Epic 4 (Assignments of Concept practice sets).
