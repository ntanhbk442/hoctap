"""Print renderer stubs: a Part as plain printable text, for the future worksheet renderer
(Story 7.1 builds on this). No routes, no UI; the Answer Key is never printed."""

from __future__ import annotations

from hoctap.content.schema import SLOT_MARKER, ExpressionInputPart, ExpressionInputView

ANSWER_LINE = "........."


def render_expression_input(part: ExpressionInputPart | ExpressionInputView) -> str:
    """The Part's label and prompt, then its template with every `[[slot]]` replaced by a
    blank answer line."""
    lines = [f"{part.part_key})"]
    if part.prompt.strip():
        lines[0] += f" {part.prompt.strip()}"
    lines.append(SLOT_MARKER.sub(ANSWER_LINE, part.template))
    return "\n".join(lines)
