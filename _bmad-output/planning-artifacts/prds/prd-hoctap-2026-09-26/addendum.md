---
title: "Addendum: Học Tập PRD"
created: 2026-09-26
---

# Addendum: technical direction for the architecture

- **Corpus facts, the OCR test and the grade-1 type mapping:** see `planning-artifacts/briefs/brief-hoctap-2026-09-26/addendum.md`.
- **Extraction:** Claude vision via the Anthropic API, one page image per call (render at about 200 dpi with `pdftoppm` or PyMuPDF). The output is JSON that follows a Problem schema. A second independent call checks the Answer Key; arithmetic is checked with a small evaluator. Use the Batch API if it lowers the cost.
- **Audio:** pre-generate Vietnamese speech for every instruction, Part, option, Hint, Solution and Concept Guide during the build, and cache it as static files. Candidate engines are to be compared in architecture (a cloud neural vi-VN voice versus a local model).
- **Runtime:** a local web server on the home PC serves the web app (a PWA suits tablets) and a local database (SQLite is likely enough for one family).
- **Images:** crops of each Problem's bounding box are stored as files; the page image is kept for Content Review and `fallback`.
- **Rejected:** Tesseract-only extraction (it loses overlines, tables, rule boxes and picture problems); speech in the browser at runtime (Vietnamese voices are unreliable on tablets); runtime AI (cost, needs internet, and not needed for a 6-year-old).
