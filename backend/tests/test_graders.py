"""Story 2.5: `learning.graders` -- one grading function per non-`fallback` Part type,
`grade_part()`'s dispatch, numeric tolerance, multi-slot wrong-key reporting, and
all-or-nothing whole-Part grading. Parts are loaded from the same fixtures
`test_sessions.py`/`test_effective.py` already use, via `ProblemDoc.model_validate()`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hoctap.content.arith import evaluate
from hoctap.content.schema import FallbackPart, Part, ProblemDoc
from hoctap.learning.graders import GradeResult, _lenient_number, grade_part

FIXTURES = Path(__file__).parent / "fixtures" / "problemdocs"


def load_part(filename: str, part_key: str | None = None) -> Any:
    doc = ProblemDoc.model_validate(json.loads((FIXTURES / filename).read_text("utf-8")))
    if part_key is None:
        return doc.parts[0]
    return next(p for p in doc.parts if p.part_key == part_key)


# --- number_input / number_tree / grid_fill / count_image / dot_draw (numeric, keyed) --


def test_number_input_correct_exact() -> None:
    part = load_part("number_input.json", "a")  # answer s1 = "5"
    result = grade_part(part, [{"key": "s1", "value": "5"}])
    assert result == GradeResult(True, [])


def test_number_input_leading_zero_tolerance() -> None:
    """FR-12: a submitted leading zero ("07") must compare correct against an answer of
    "7" -- `content.schema.parse_number()` itself rejects this (its `NUMERIC_PATTERN`
    forbids a leading zero on stored answers), so grading uses the more lenient
    `learning.graders._lenient_number()` instead, for untrusted child-submitted input."""
    part = load_part("number_input.json", "a")  # answer s1 = "5"
    assert grade_part(part, [{"key": "s1", "value": "05"}]).correct is True
    part_b = load_part("number_input.json", "b")  # answer s1 = "3"
    assert grade_part(part_b, [{"key": "s1", "value": "03"}]).correct is True


def test_number_input_dot_decimal_tolerance() -> None:
    """FR-13: a submitted `.` decimal ("3.5") must compare correct against a canonically
    comma-stored answer ("3,5")."""
    doc = json.loads((FIXTURES / "number_input.json").read_text("utf-8"))
    doc["parts"][0]["answer"] = [{"key": "s1", "value": "3,5"}]
    part = ProblemDoc.model_validate(doc).parts[0]
    assert grade_part(part, [{"key": "s1", "value": "3.5"}]).correct is True


def test_number_input_decimal_value_tolerance_trailing_zero() -> None:
    """Comparing by Decimal VALUE, not by exact string: a differently-written comma
    decimal (a trailing zero) still equals the stored answer."""
    doc = json.loads((FIXTURES / "number_input.json").read_text("utf-8"))
    doc["parts"][0]["answer"] = [{"key": "s1", "value": "3,5"}]
    part = ProblemDoc.model_validate(doc).parts[0]
    assert grade_part(part, [{"key": "s1", "value": "3,50"}]).correct is True


def test_number_input_actually_malformed_value_still_wrong() -> None:
    """A value that isn't a number at all (not just non-canonically-formatted) stays
    wrong, never crashes."""
    part = load_part("number_input.json", "a")  # answer s1 = "5"
    assert grade_part(part, [{"key": "s1", "value": "abc"}]).correct is False


def test_number_tree_correct() -> None:
    part = load_part("number_tree.json", "a")  # node "r" answer "3"
    assert grade_part(part, [{"key": "r", "value": "3"}]).correct is True


def test_multi_slot_one_of_three_wrong() -> None:
    part = load_part("compare.json")  # r1 "<", r2 ">", r3 "="
    result = grade_part(
        part,
        [
            {"key": "r1", "value": "<"},
            {"key": "r2", "value": "<"},  # wrong
            {"key": "r3", "value": "="},
        ],
    )
    assert result.correct is False
    assert result.wrong_keys == ["r2"]


def test_compare_all_correct() -> None:
    part = load_part("compare.json")
    result = grade_part(
        part,
        [
            {"key": "r1", "value": "<"},
            {"key": "r2", "value": ">"},
            {"key": "r3", "value": "="},
        ],
    )
    assert result == GradeResult(True, [])


def test_count_image_multi_slot() -> None:
    part = load_part("count_image.json")  # ga=7, vit=3
    result = grade_part(part, [{"key": "ga", "value": "7"}, {"key": "vit", "value": "4"}])
    assert result.correct is False
    assert result.wrong_keys == ["vit"]


def test_dot_draw_correct() -> None:
    part = load_part("dot_draw.json")  # b1=4, b2=6
    result = grade_part(part, [{"key": "b1", "value": "4"}, {"key": "b2", "value": "6"}])
    assert result == GradeResult(True, [])


def test_keyed_missing_slot_in_submission_is_wrong() -> None:
    part = load_part("count_image.json")  # ga, vit
    result = grade_part(part, [{"key": "ga", "value": "7"}])  # "vit" missing entirely
    assert result.correct is False
    assert result.wrong_keys == ["vit"]


def test_keyed_extra_unknown_slot_in_submission_is_wrong() -> None:
    part = load_part("count_image.json")
    result = grade_part(
        part,
        [
            {"key": "ga", "value": "7"},
            {"key": "vit", "value": "3"},
            {"key": "not-a-real-slot", "value": "1"},
        ],
    )
    assert result.correct is False
    assert result.wrong_keys == ["not-a-real-slot"]


@pytest.mark.parametrize(
    "submitted",
    [
        "not-a-list",
        123,
        None,
        [{"key": "ga"}],  # missing value
        [{"key": "ga", "value": 7}],  # value not a string
        ["not-a-dict"],
    ],
)
def test_keyed_malformed_submission_graded_wrong_never_raises(submitted: Any) -> None:
    part = load_part("count_image.json")
    result = grade_part(part, submitted)
    assert result.correct is False
    assert set(result.wrong_keys) == {"ga", "vit"}


# --- multiple_choice / image_select / order / match / connect_dots / spot_difference ---


def test_multiple_choice_correct() -> None:
    part = load_part("multiple_choice.json")  # selected = ["b"]
    assert grade_part(part, {"selected": ["b"]}) == GradeResult(True, [])


def test_multiple_choice_wrong_is_whole_part_no_partial_keys() -> None:
    part = load_part("multiple_choice.json")
    result = grade_part(part, {"selected": ["a"]})
    assert result.correct is False
    assert result.wrong_keys == []


def test_image_select_multi_correct_regardless_of_order() -> None:
    part = load_part("image_select.json")  # selected = ["t1", "t3"]
    assert grade_part(part, {"selected": ["t3", "t1"]}) == GradeResult(True, [])


def test_order_correct() -> None:
    part = load_part("order.json")
    assert grade_part(part, {"order": ["n2", "n4", "n6", "n9"]}) == GradeResult(True, [])


def test_order_wrong_sequence() -> None:
    part = load_part("order.json")
    result = grade_part(part, {"order": ["n9", "n6", "n4", "n2"]})
    assert result.correct is False
    assert result.wrong_keys == []


def test_match_correct_pairs_any_order() -> None:
    part = load_part("match.json")
    result = grade_part(
        part, {"pairs": [["l2", "r4"], ["l1", "r5"], ["l3", "r5"]]}
    )
    assert result == GradeResult(True, [])


def test_match_wrong_pairing() -> None:
    part = load_part("match.json")
    result = grade_part(part, {"pairs": [["l1", "r4"], ["l2", "r5"], ["l3", "r5"]]})
    assert result.correct is False
    assert result.wrong_keys == []


def test_connect_dots_correct_sequence() -> None:
    part = load_part("connect_dots.json")
    assert grade_part(part, {"sequence": [1, 2, 3, 4, 5, 6]}) == GradeResult(True, [])


def test_connect_dots_wrong_order() -> None:
    part = load_part("connect_dots.json")
    assert grade_part(part, {"sequence": [1, 2, 3, 4, 6, 5]}).correct is False


def test_spot_difference_region_key_set_not_exact_bbox() -> None:
    part = load_part("spot_difference.json")  # region_keys d1, d2, d3
    assert grade_part(part, {"region_keys": ["d3", "d1", "d2"]}) == GradeResult(True, [])


def test_spot_difference_wrong_region_keys() -> None:
    part = load_part("spot_difference.json")
    assert grade_part(part, {"region_keys": ["d1", "d2"]}).correct is False


@pytest.mark.parametrize(
    "submitted",
    ["not-a-dict", None, {"selected": "b"}, {"selected": [1, 2]}, {}],
)
def test_all_or_nothing_malformed_submission_graded_wrong_never_raises(submitted: Any) -> None:
    part = load_part("multiple_choice.json")
    result = grade_part(part, submitted)
    assert result.correct is False


def test_multiple_choice_multi_false_two_selections_wrong() -> None:
    """`multiple_choice.json`'s Part has `multi: false` and a single-key answer
    (`["b"]`) -- submitting 2 keys (even including the right one) does not match the
    answer SET and is graded wrong as a whole."""
    part = load_part("multiple_choice.json")
    result = grade_part(part, {"selected": ["a", "b"]})
    assert result.correct is False
    assert result.wrong_keys == []


def test_match_duplicate_left_key_in_submission_graded_wrong() -> None:
    part = load_part("match.json")
    result = grade_part(
        part, {"pairs": [["l1", "r5"], ["l1", "r4"], ["l3", "r5"]]}  # "l1" duplicated
    )
    assert result.correct is False


def test_match_unknown_right_key_in_submission_graded_wrong() -> None:
    part = load_part("match.json")
    result = grade_part(
        part, {"pairs": [["l1", "not-a-real-right-key"], ["l2", "r4"], ["l3", "r5"]]}
    )
    assert result.correct is False


def test_spot_difference_extra_region_key_graded_wrong() -> None:
    part = load_part("spot_difference.json")  # answer region_keys: d1, d2, d3
    result = grade_part(part, {"region_keys": ["d1", "d2", "d3", "d4"]})
    assert result.correct is False


def test_spot_difference_missing_region_key_graded_wrong() -> None:
    part = load_part("spot_difference.json")
    result = grade_part(part, {"region_keys": ["d1", "d2"]})
    assert result.correct is False


def test_number_input_negative_number() -> None:
    doc = json.loads((FIXTURES / "number_input.json").read_text("utf-8"))
    doc["parts"][0]["answer"] = [{"key": "s1", "value": "-4"}]
    part = ProblemDoc.model_validate(doc).parts[0]
    assert grade_part(part, [{"key": "s1", "value": "-4"}]).correct is True
    assert grade_part(part, [{"key": "s1", "value": "4"}]).correct is False


def test_number_input_bare_zero() -> None:
    doc = json.loads((FIXTURES / "number_input.json").read_text("utf-8"))
    doc["parts"][0]["answer"] = [{"key": "s1", "value": "0"}]
    part = ProblemDoc.model_validate(doc).parts[0]
    assert grade_part(part, [{"key": "s1", "value": "0"}]).correct is True
    assert grade_part(part, [{"key": "s1", "value": "-0"}]).correct is True


# --- dispatch -----------------------------------------------------------------------


def test_grade_part_raises_for_fallback() -> None:
    doc = ProblemDoc.model_validate(
        json.loads((FIXTURES / "fallback.json").read_text("utf-8"))
    )
    part = doc.parts[0]
    assert isinstance(part, FallbackPart)
    with pytest.raises(TypeError):
        grade_part(part, {"anything": "goes"})


def test_grade_part_dispatches_every_non_fallback_type_without_error() -> None:
    """Every Part type in `content.schema`'s union (except fallback) has a registered
    grader -- exercised once per fixture file, correct submission, no exception."""
    cases: list[tuple[str, Any]] = [
        ("number_input.json", [{"key": "s1", "value": "5"}]),
        ("expression_input.json", [{"key": "s1", "value": "36"}]),
        ("compare.json", None),  # filled below from the fixture's own answer
        ("multiple_choice.json", {"selected": ["b"]}),
        ("image_select.json", {"selected": ["t1", "t3"]}),
        ("order.json", {"order": ["n2", "n4", "n6", "n9"]}),
        ("number_tree.json", [{"key": "r", "value": "3"}]),
        (
            "grid_fill.json",
            [
                {"key": "r0c1", "value": "2"},
                {"key": "r0c3", "value": "4"},
                {"key": "r1c2", "value": "7"},
            ],
        ),
        ("match.json", {"pairs": [["l1", "r5"], ["l2", "r4"], ["l3", "r5"]]}),
        ("count_image.json", [{"key": "ga", "value": "7"}, {"key": "vit", "value": "3"}]),
        ("dot_draw.json", [{"key": "b1", "value": "4"}, {"key": "b2", "value": "6"}]),
        ("connect_dots.json", {"sequence": [1, 2, 3, 4, 5, 6]}),
        ("spot_difference.json", {"region_keys": ["d1", "d2", "d3"]}),
    ]
    for filename, submitted in cases:
        part: Part = load_part(filename)
        if submitted is None:
            submitted = [{"key": e.key, "value": e.value} for e in part.answer]  # type: ignore[union-attr]
        result = grade_part(part, submitted)
        assert result.correct is True, f"{filename}: expected correct, got {result}"


# --- expression_input ------------------------------------------------------------------


def _expr(mode: str, key: str) -> Any:
    part = load_part("expression_input.json", "a").model_copy(deep=True)
    object.__setattr__(part, "mode", mode)
    part.answer[0].value = key
    return part


def _got(value: str) -> list[dict[str, str]]:
    return [{"key": "s1", "value": value}]


@pytest.mark.parametrize("child", ["36", "(4×3)×3", "12 x 3", "3 * 12", "036", "72 : 2", "40 - 4"])
def test_expression_value_mode_accepts_any_equivalent_form(child: str) -> None:
    assert grade_part(_expr("value", "12 × 3"), _got(child)) == GradeResult(True, [])


def test_expression_value_mode_accepts_sum_for_number() -> None:
    assert grade_part(_expr("value", "7"), _got("3+4")).correct


@pytest.mark.parametrize("child", ["3.5", "3,5", "03,50", "7/2", "14:4"])
def test_expression_decimal_comma_and_dot(child: str) -> None:
    assert grade_part(_expr("value", "3,5"), _got(child)).correct


def test_expression_full_width_unicode_operators_are_recognised() -> None:
    """Review Triage Log finding #3 (2026-10-01): an IME can emit full-width Unicode
    operators/parens/digits (e.g. "＋", "（", "０"); `content.arith.evaluate()` now
    NFKC-normalises its input before tokenising, so these fold to their ASCII/canonical
    equivalents instead of a clean (but wrong) "unparsable" grade."""
    assert evaluate("１２　＋　３") == evaluate("12 + 3")
    assert grade_part(_expr("value", "12 × 3"), _got("（４×３）×３")).correct


def test_expression_wrong_value() -> None:
    assert grade_part(_expr("value", "36"), _got("35")) == GradeResult(False, ["s1"])


def test_expression_exact_mode_requires_the_same_form() -> None:
    part = _expr("exact", "2 × 3 + 4")
    assert not grade_part(part, _got("10")).correct
    assert not grade_part(part, _got("4+2×3")).correct
    assert grade_part(part, _got("2 × 3 + 4")).correct


def test_expression_exact_mode_normalises_whitespace_and_aliases() -> None:
    part = _expr("exact", "2×3")
    assert grade_part(part, _got(" 2 x 3 ")).correct
    assert grade_part(part, _got("2*3")).correct
    assert not grade_part(_expr("exact", "6 : 2"), _got("6 × 2")).correct
    assert grade_part(_expr("exact", "6 : 2"), _got("6/2")).correct


@pytest.mark.parametrize(
    "child", ["3+", "abc", "", "   ", "5:0", "(", "2 3", "7" * 5000, "1+" * 300]
)
def test_expression_not_an_expression_is_wrong_without_raising(child: str) -> None:
    for mode in ("value", "exact"):
        assert grade_part(_expr(mode, "7"), _got(child)) == GradeResult(False, ["s1"])


@pytest.mark.parametrize(
    "submitted",
    [None, "7", {"s1": "7"}, [1], [{"key": "s1"}], [{"key": "s1", "value": 7}]],
)
def test_expression_malformed_submission_is_wrong(submitted: Any) -> None:
    assert grade_part(_expr("value", "7"), submitted) == GradeResult(False, ["s1"])


def test_expression_multi_slot_reports_the_wrong_slot() -> None:
    raw = json.loads((FIXTURES / "expression_input.json").read_text("utf-8"))
    part = raw["parts"][0]
    part["template"] = "[[s1]] và [[s2]]"
    part["slots"] = [{"slot_key": "s1"}, {"slot_key": "s2"}]
    part["answer"] = [{"key": "s1", "value": "6"}, {"key": "s2", "value": "8"}]
    doc = ProblemDoc.model_validate(raw)
    got = [{"key": "s1", "value": "2×3"}, {"key": "s2", "value": "9"}]
    assert grade_part(doc.parts[0], got) == GradeResult(False, ["s2"])
    assert grade_part(doc.parts[0], got[:1]) == GradeResult(False, ["s2"])


def test_number_input_grade_4_5_comma_equals_dot() -> None:
    part = load_part("number_input.json", "a").model_copy(deep=True)
    part.answer[0].value = "3,5"
    assert grade_part(part, [{"key": "s1", "value": "3.5"}]).correct
    assert grade_part(part, [{"key": "s1", "value": "3,5"}]).correct


# --- parity: _lenient_number() vs. the expression evaluator's own number token ----------
#
# Review Triage Log finding #1 (2026-10-01): `_lenient_number()` (used for
# `number_input`/`number_tree`/`grid_fill`/`count_image`/`dot_draw`) and
# `content.arith.evaluate()`'s number token (used for `expression_input`, where a plain
# number is just a one-term expression) are a deliberate, separate implementation per this
# story's own Design Notes -- not a hidden duplication to unify -- but nothing cross-checked
# that the two regexes still agree on the same free-typed input. This pins parity for the
# inputs the audit named, so a future change to either one that silently breaks agreement
# gets caught by a test instead of drifting unnoticed.


@pytest.mark.parametrize("value", ["07", "3,5", "-0", "3,50"])
def test_lenient_number_and_arith_evaluator_agree_on_shared_number_inputs(value: str) -> None:
    lenient = _lenient_number(value)
    fraction = evaluate(value, dot_decimal=True)
    assert lenient is not None, f"{value!r}: _lenient_number() rejected it"
    assert fraction is not None, f"{value!r}: the evaluator rejected it"
    assert lenient == Decimal(fraction.numerator) / Decimal(fraction.denominator)
