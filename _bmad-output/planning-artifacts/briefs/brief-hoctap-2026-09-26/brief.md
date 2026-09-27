---
title: "Product Brief: Học Tập (working name)"
status: final
created: 2026-09-26
updated: 2026-09-26
---

# Product Brief: Học Tập (working name)

## Executive Summary

Học Tập turns the Archimedes School "Hướng dẫn học Toán" workbooks into an interactive, spoken, Vietnamese-language practice app for one grade-1 child at home. It covers the scanned books in `Sach_Arch/` (grades 1–5, both the 2020 edition and the 2024–25 edition). Every exercise becomes a problem the child can tap, drag or type into. The app reads each problem aloud, grades the answer immediately, gives a hint and then a worked solution when the child gets it wrong, and links each problem to a short concept explanation.

The goal is high marks at school through practice on the same books the school uses. Today those books are only scanned PDFs, so a parent must read every problem aloud and mark every answer by hand.

All content (problem text, answers, solutions, hints, concept guides and audio) is produced **once**, up front, by a Claude vision pipeline over roughly 2,140 pages of Toán (math) books. After that the app runs on the home PC or a tablet on the home network with no internet connection and no per-use AI cost. **First step: a pilot on a few grade-1 lessons**, to prove extraction quality and measure cost before the whole corpus is run.

## The Problem

- **The child is a non-reader or early reader.** A grade-1 child can't read the instructions ("Điền số thích hợp vào ô trống") on their own. Without an adult reading aloud, practice stops.
- **Paper doesn't hold attention.** The child engages with interactive formats and loses interest in static worksheets.
- **There's no feedback loop.** The workbooks have no answer keys, so mistakes are found late or not at all, and nobody tracks which topics are weak.
- **The content is locked in scans.** Plain OCR (Tesseract) was tested and failed on exactly what matters here: numbers written with an overline where letters stand for unknown digits (`2a4b`), tables, highlighted rule boxes and picture-based exercises such as counting dots, number trees and spot-the-difference.

## The Solution

1. **Extraction pipeline (runs once).** Claude reads each page image and outputs structured problems (text, cropped images, answer, step-by-step solution, hint, concept tag), each linked to its book, lesson and page.
2. **Interactive problem player.** Each problem type gets a matching control (number boxes, `<` / `>` / `=`, multiple choice, drag-to-order, number trees and bonds, grids, matching lines, counting objects in a cropped image), all with large touch targets for a 6-year-old on a tablet.
3. **Vietnamese audio throughout.** A 🔊 button reads each problem, hint and solution aloud in natural Vietnamese. Audio is generated in advance, so it works offline and on devices whose browser has no Vietnamese voice.
4. **Problem sets that follow the books.** The child can browse by grade, book, week or chapter, and lesson ("Tuần 1 → Tiết 2"), or by topic ("So sánh số"). The weekly self-practice sheet ("Phiếu tự luyện cuối tuần") works as a short quiz.
5. **Grading and help.** Answers are marked instantly. A first mistake brings a spoken hint; a second brings the worked solution. Each problem links to its concept guide: a short spoken explanation with an example.
6. **Parent dashboard.** Shows progress per book and topic, weak topics, time spent and recent mistakes. The parent can assign today's problem set and report a wrong answer.
7. **Motivation and extras.** Stars, streaks and badges; a retry queue for problems answered wrong; printable worksheets with a separate answer sheet.

## Who This Serves

- **Primary: the learner.** A grade-1 child at Archimedes School who can't yet read fluently and who prefers tapping, dragging and listening. Success means practising on their own for 15–20 minutes and coming away with more right answers than yesterday.
- **Secondary: the parent (Anh).** Wants the child to score highly without sitting through every exercise. Needs to see at a glance what was practised, what is weak and what to assign next.
- **Later:** siblings or the same child in higher grades. The grades 2–5 books are included for this reason.

## Success Criteria

- **Extraction coverage:** at least 95% of problems in the Toán books are captured and playable. Problems that can't be made interactive are shown as page images, and the child checks the answer against a revealed solution.
- **Answer-key accuracy:** at least 98% on a spot-check of 100 random problems.
- **Independent use:** the child completes a 10-problem set without adult help, audio included.
- **Engagement:** practice on at least 5 days a week for the first month (streak data).
- **Outcome:** a better score on the child's next school tests. This is observed by the parent; the app doesn't measure it.

## Scope

**In (v1):** all Toán books for grades 1–5 in both editions (duplicates removed); everything in The Solution, items 1–7; grade-1 problem types built first; child profiles; offline use on the home PC and LAN; a tablet layout.

**Out (for now):**
- Tiếng Việt books. The same pipeline can add them in a second phase.
- Spoken answers (speech recognition).
- Cloud hosting, accounts outside the family, and multi-school use.
- Live AI chat tutoring at runtime.
- Public distribution of book content. The app is for family use of materials shared among parents.

## Key Risks

- **Picture-heavy grade-1 pages** are the hardest to make interactive, and they are the child's own grade. This is why the pilot comes first.
- **Wrong answer keys would teach the child mistakes.** Mitigation: generate each answer twice, check arithmetic answers with code, flag any disagreement, and keep the report-error button.
- **Cost and time of extraction** for about 2,140 Toán pages through the Claude API. Estimate this during the pilot.

## Assumptions to Validate

- All AI content (answers, solutions, hints, concept guides, audio) can be generated up front, so the app needs no AI at runtime.
- At least 95% of problems can be made interactive. The rest are shown as page images, and the child checks against a revealed solution.
- The content is for family use only and is never published.
- Where the two editions overlap on a topic, both are kept as separate problem sets rather than merged.

## Vision

A complete, spoken, interactive companion to the Archimedes curriculum. The child moves with it from grade 1 to grade 5, Tiếng Việt is added through the same pipeline, and practice adapts to weak topics automatically. If it works well, other Archimedes parents could run it for their own children using their own copies of the books.
