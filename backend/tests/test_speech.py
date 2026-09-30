"""Story 2.2: `content.speech`'s normaliser, key and Problem-text reference helper.

One test per row of the I/O matrix that concerns `speech_text`/`speech_key`, plus
`problem_speech_refs`'s field coverage (never `answer`).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from hoctap.content.schema import ProblemDoc
from hoctap.content.speech import (
    problem_speech_refs,
    speech_key,
    speech_path,
    speech_text,
    speech_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"


def test_comparison_operator() -> None:
    assert "bé hơn" in speech_text("3 < 5")


def test_all_operators() -> None:
    assert speech_text("1 + 2") == "1 cộng 2"
    assert speech_text("3 - 1") == "3 trừ 1"
    assert speech_text("2 × 3") == "2 nhân 3"
    assert speech_text("2 * 3") == "2 nhân 3"
    assert speech_text("6 ÷ 2") == "6 chia 2"
    assert speech_text("6 / 2") == "6 chia 2"
    assert speech_text("5 > 2") == "5 lớn hơn 2"
    assert speech_text("5 = 5") == "5 bằng 5"


def test_overline_two_digit_notation() -> None:
    assert speech_text(r"\overline{2a4b}") == "số hai a bốn b"


def test_fraction() -> None:
    assert speech_text(r"\frac{1}{2}") == "một phần hai"


def test_unknown_markup_is_literal_and_never_raises() -> None:
    text = r"\somethingweird{x}{y}"
    assert speech_text(text) == text  # left as literal text


def test_nested_notation_is_not_double_processed() -> None:
    # The inner \overline{2} is substituted first ("số hai"); the outer \frac{...} must
    # then NOT match that already-substituted, no-longer-alnum-only body (it would
    # otherwise get re-spelled character by character into something garbled like
    # "s ố h a i"). Left partially normalised (with the outer \frac{...}{...} literal),
    # never garbled, never raising — the documented v1 trade-off for nesting.
    result = speech_text(r"\frac{\overline{2}}{3}")
    assert result == r"\frac{số hai}{3}"
    assert "s ố" not in result  # the garbled character-by-character form


def test_overline_and_frac_with_empty_body_do_not_raise() -> None:
    # Degenerate input (empty braces): never raises, produces a plain, if odd, string.
    assert speech_text(r"\overline{}") == "số"
    assert speech_text(r"\frac{}{}") == "phần"


def test_frac_with_operator_inside_is_left_as_literal_wrapper() -> None:
    # `[^{}]*` used to let an operator through into a matched `\frac{...}` body (a body
    # would then be re-processed by both the frac substitution and the operator loop); the
    # body charclass is now digits/letters only, so `\frac{1+2}{3}` simply does not match
    # `_FRAC_RE` at all, and only the `+` is substituted by the operator loop.
    assert speech_text(r"\frac{1+2}{3}") == r"\frac{1 cộng 2}{3}"


def test_plain_digits_and_words_pass_through() -> None:
    assert speech_text("Con có 5 quả táo") == "Con có 5 quả táo"


def test_nfc_normalised() -> None:
    decomposed = unicodedata.normalize("NFD", "Đúng rồi")
    assert speech_text(decomposed) == unicodedata.normalize("NFC", "Đúng rồi")


def test_speech_key_stable() -> None:
    assert speech_key("3 < 5", "vi-VN-HoaiMyNeural") == speech_key("3 < 5", "vi-VN-HoaiMyNeural")


def test_speech_key_changes_on_text_edit() -> None:
    a = speech_key("3 < 5", "vi-VN-HoaiMyNeural")
    b = speech_key("3 > 5", "vi-VN-HoaiMyNeural")
    assert a != b


def test_speech_key_changes_on_voice_change() -> None:
    a = speech_key("3 < 5", "vi-VN-HoaiMyNeural")
    b = speech_key("3 < 5", "vi-VN-NamMinhNeural")
    assert a != b


def test_speech_key_is_16_hex_chars() -> None:
    key = speech_key("xin chào", "vi-VN-HoaiMyNeural")
    assert len(key) == 16
    int(key, 16)  # raises ValueError if not hex


def test_speech_url() -> None:
    assert speech_url("abc123") == "/assets-data/audio/abc123.mp3"


def test_speech_path(tmp_path: Path) -> None:
    assert speech_path(tmp_path, "abc123") == tmp_path / "assets" / "audio" / "abc123.mp3"


def _doc() -> ProblemDoc:
    data = json.loads((FIXTURES / "number_input.json").read_text(encoding="utf-8"))
    return ProblemDoc.model_validate(data)


def test_problem_speech_refs_covers_expected_fields_never_answer() -> None:
    doc = _doc()
    refs = problem_speech_refs(doc, "vi-VN-HoaiMyNeural")
    texts = {r.text for r in refs}
    # Each ref's `text` is the NORMALISED spoken text (this is what a TtsEngine actually
    # gets), not the raw field — a raw field with maths notation (e.g. "3 + 2 = 5") must not
    # appear verbatim; the CLAIM the refs cover it is checked against `speech_text(raw)`.
    assert speech_text(doc.instruction) in texts
    assert speech_text(doc.display_label) in texts
    for part in doc.parts:
        assert speech_text(part.hint) in texts
        assert speech_text(part.solution.final) in texts
        for step in part.solution.steps:
            assert speech_text(step) in texts
    # Never the answer (AD-5): no answer value string leaks in as a speech ref.
    for part in doc.parts:
        for entry in part.answer:
            assert entry.value not in texts
    # Every ref's key matches `speech_key(text, voice_id)` (normalising an already-
    # normalised text is idempotent, so this must still hold).
    for ref in refs:
        assert ref.speech_key == speech_key(ref.text, "vi-VN-HoaiMyNeural")


def test_problem_speech_refs_normalises_maths_notation() -> None:
    doc = _doc()
    refs = problem_speech_refs(doc, "vi-VN-HoaiMyNeural")
    texts = {r.text for r in refs}
    assert "3 cộng 2 bằng 5" in texts  # part a's raw final is "3 + 2 = 5"
    assert "4 cộng 3 bằng 7" in texts  # part b's raw final is "4 + 3 = 7"
    assert "3 + 2 = 5" not in texts
    assert "4 + 3 = 7" not in texts


def test_problem_speech_refs_deduplicates_and_skips_blank() -> None:
    doc = _doc()
    refs = problem_speech_refs(doc, "vi-VN-HoaiMyNeural")
    texts = [r.text for r in refs]
    assert len(texts) == len(set(texts))  # deduplicated
    assert "" not in texts  # both parts' `prompt` is blank in this fixture


def test_problem_speech_refs_handles_zero_parts() -> None:
    # ProblemDoc.parts has min_length=1 (a real ProblemDoc always has at least one Part),
    # so this uses a duck-typed stub, not a real ProblemDoc, to exercise the empty-parts
    # branch of the loop directly.
    class _Stub:
        instruction = "Nghe và trả lời."
        display_label = "Khởi động"
        parts: list = []

    refs = problem_speech_refs(_Stub(), "vi-VN-HoaiMyNeural")  # type: ignore[arg-type]
    texts = {r.text for r in refs}
    assert texts == {"Nghe và trả lời.", "Khởi động"}


def test_expression_symbols_are_read_in_a_maths_context() -> None:
    assert speech_text("12 : 3") == "12 chia 3"
    assert speech_text("(4 × 3) × 3 − 2") == "mở ngoặc 4 nhân 3 đóng ngoặc nhân 3 trừ 2"
    # Prose keeps its old spoken text.
    assert speech_text("Tính:") == "Tính:"
    assert speech_text("(1 điểm)") == "(1 điểm)"
