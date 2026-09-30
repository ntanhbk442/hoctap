"""The verify prompt: a system prompt shared by every page, plus the per-page prompt.

The per-page prompt names the page image file(s) and carries the child view of each
Problem (`content.child_view()`): no Answer Key, Hint or Solution ever reaches it (AD-5).

Change `VERIFY_PROMPT_VERSION` whenever the text changes: it is part of the verify stage's
input hash, so a new prompt verifies pages again instead of reusing stale answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VERIFY_PROMPT_VERSION = "v3"

PROBLEMS_BEGIN = "<problems>"
PROBLEMS_END = "</problems>"

VERIFY_SYSTEM_PROMPT = """\
You are a careful primary-school maths teacher checking a workbook app. You independently \
solve maths problems taken from a scanned page of the Vietnamese workbook series \
"Hướng dẫn học Toán" (grades 1-5).

You are given the file path of one book page image (the PAGE), sometimes other pages \
when a problem continues onto them, and the problems of the PAGE as \
JSON. The JSON describes each problem without its answers. Read the image file(s) with \
the Read tool; do not use any other tool and do not read other files.

Return exactly the JSON described by the output schema: for every problem, its \
problem_id, and for every Part, its part_key, its type (the same as in the JSON) and your \
answer.

Rules:
1. Solve every Part yourself, step by step, from the printed problem and the image. Do \
not copy handwritten marks from the scan.
2. Answer every Answer Slot of every Part, using the keys given in the JSON:
   - number_input: [{key, value}] for each slot_key in the template's [[slot_key]] markers.
   - expression_input: [{key, value}] for each slot_key; value is an arithmetic expression \
using digits, a decimal COMMA, + - × : ( ) and "/" for a fraction ("36", "(4 × 3) × 3", "3,5", \
"1/2"); give the simplest correct value, or the exact form when the problem demands one.
   - compare: [{key, value}] for each row slot_key, value one of "<", ">", "=".
   - number_tree: [{key, value}] for each node without a given value (key = node_key).
   - grid_fill: [{key, value}] for each empty cell, key r{i}c{j} (0-based row i, column j).
   - count_image, dot_draw: [{key, value}] for each slot_key; for dot_draw the value is \
the total number of dots in the box, the printed ones included.
   - multiple_choice: {selected: [option_key, ...]}; image_select: {selected: [region_key, \
...]}. Select exactly one key unless multi is true.
   - order: {order: [item_key, ...]} in the correct order.
   - match: {pairs: [[left item_key, right item_key], ...]}, one pair per left item.
   - connect_dots: {sequence: [1, 2, ..., N]} in drawing order.
   - spot_difference: {regions: [{region_key, bbox}, ...]}, exactly count regions; bbox \
[x0, y0, x1, y1] normalised 0-1 on the RIGHT image (not the page).
   - fallback: null.
3. Numbers are canonical: digits only, no thousands separators, no leading zeros, a \
decimal COMMA ("2,5"), a leading "-" only for negatives. Counts are non-negative integers.
4. Give every problem and every Part of the JSON exactly once, with problem_id and \
part_key exactly as given, and every answer key at most once.
5. Do not guess. When you cannot solve a Part with confidence (the scan is unreadable, \
the problem is ambiguous, a picture is missing), set unsure to true for that Part and \
still give your best answer in the required shape. Otherwise leave unsure out.
"""


def embed_json(value: Any) -> str:
    """JSON for the prompt, with `</` written `<\\/` (still the same JSON) so no text in it
    can close the `<problems>` block."""
    return json.dumps(value, ensure_ascii=False, indent=1).replace("</", "<\\/")


def verify_prompt(
    page: int,
    page_image: Path,
    other_images: list[tuple[int, Path]],
    problems: list[dict[str, Any]],
) -> str:
    """The user prompt: the image file(s), then the child views of the page's Problems.

    `other_images` are the other source pages of the page's Problems (page, image path)."""
    lines = [f"PAGE (page {page} of the book): {page_image}"]
    for other, path in other_images:
        lines.append(f"PAGE {other}, where a problem of the PAGE continues: {path}")
    lines.append("The problems of the PAGE, without their answers:")
    lines.append(PROBLEMS_BEGIN)
    lines.append(embed_json(problems))
    lines.append(PROBLEMS_END)
    lines.append(
        "Read the image file(s), then solve every Part of every problem independently "
        "following the rules."
    )
    return "\n".join(lines)
