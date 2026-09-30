"""Print renderer stub for `expression_input` (Story 6.1)."""

from __future__ import annotations

import json
from pathlib import Path

from hoctap.content import ProblemDoc
from hoctap.content.printing import ANSWER_LINE, render_expression_input

FIXTURE = Path(__file__).parent / "fixtures" / "problemdocs" / "expression_input.json"


def test_renders_prompt_and_blank_answer_line_without_the_key() -> None:
    doc = ProblemDoc.model_validate(json.loads(FIXTURE.read_text("utf-8")))
    assert render_expression_input(doc.parts[0]) == f"a)\n(4 + 8) × 3 = {ANSWER_LINE}"
    text = render_expression_input(doc.parts[1])
    assert text == f"b) Viết biểu thức: lấy 12 nhân 3.\n{ANSWER_LINE}"
    assert "36" not in render_expression_input(doc.parts[0])
