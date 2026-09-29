"""Story 2.5: `learning.graders` -- one grading function per non-`fallback` Part type,
`grade_part()`'s dispatch, numeric tolerance, multi-slot wrong-key reporting, and
all-or-nothing whole-Part grading. Parts are loaded from the same fixtures
`test_sessions.py`/`test_effective.py` already use, via `ProblemDoc.model_validate()`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hoctap.content.schema import FallbackPart, Part, ProblemDoc
from hoctap.learning.graders import GradeResult, grade_part

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
