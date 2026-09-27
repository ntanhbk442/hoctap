---
title: "Addendum: Học Tập brief"
created: 2026-09-26
---

# Addendum: detail for the PRD and architecture

## Source corpus (Toán only, for v1)

| Set | Books | Pages | Structure |
|---|---|---|---|
| Old edition, 2020 (`Lớp 1`–`Lớp 5`) | 4 quyển per grade, 20 books | ≈1,060 | Tuần (week) → Tiết (lesson) → Bài (exercise), plus "Phiếu tự luyện cuối tuần" (end-of-week practice sheet) |
| New edition, 2024–25 (`Sach_moi`) | 2 tập per grade, 10 books | ≈1,080 | Chapter (topic) → theory box → Ví dụ + Hướng dẫn (worked example + guidance) → exercises |

- Duplicates to skip:
  - Toán 1 T1: the full and `-compressed` copies;
  - Toán 2 T1: the full and `-compressed` copies;
  - Toán 4 T1: the full and `-fromzip` copies.

  For each pair, use the higher-quality file for page rendering.
- **Every page is a scan.** The few embedded text layers are bad OCR and should be ignored.
- The new-edition pages carry a GomNhom.com QR watermark. The extractor should ignore it.

## Grade 1 problem types seen (first sample)

| Seen on the page | Suggested widget |
|---|---|
| Draw dots matching a number | Dot counter or tap-to-add |
| Fill in a sequence of shapes | Number inputs in a sequence |
| Connect dots 1–10 | Ordered tap |
| Place numbers in a grid so no row or column repeats | Grid input |
| Number trees and bonds (triangles, houses) | Tree widget |
| "Số liền trước / liền sau" (number before / after) | Short number input |
| Circle the odd one out | Image choice, using the cropped image |
| Spot the difference | Image hotspot, or page image with self-check |
| Word problems ("Trả lời: Có … bạn", answer: there are … children) | Number input inside a sentence |

## Test result: Tesseract vs Claude vision (2026-09-26)

- **Tiếng Việt 3 text page:** Tesseract was good, with correct diacritics, at about 5 s per page.
- **Toán 3 page:** Tesseract
  - missed the light-blue rule box;
  - lost the overlines (`2a4b`);
  - flattened the tables;
  - made diacritic and digit errors ("tống", "1004+600").

  Claude vision reproduced the page exactly.
- Surya and other local VLMs aren't practical here: there is no working GPU in WSL, and the model download is 1.67 GB.

## Technical notes for the architecture

- No API key was present in the environment. `ANTHROPIC_API_KEY` is needed for extraction.
- The machine has 8 CPU cores and 9 GB of RAM, and runs Windows with WSL2.
- The Python packages `anthropic`, `PyMuPDF` and `pdftoppm` are available.
- For each problem, keep a link back to its source (file, page and bounding box) so errors can be checked against the original scan.
- Tests for answer-key accuracy:
  - generate each answer twice;
  - compute arithmetic answers with code;
  - flag any disagreement for review.
