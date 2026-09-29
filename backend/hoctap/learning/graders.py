"""Grading: one function per non-`fallback` Part type (Story 2.5, AD-6).

Every Part type validates a rich, type-specific `answer` shape (`content.schema`), so
grading is not one generic string compare -- this module holds one grading function per
type plus a `grade_part()` dispatcher, matching the spec's Code Map.

Numeric tolerance (`number_input`/`number_tree`/`grid_fill`/`count_image`/`dot_draw`, all
`NumericEntry`/`CountEntry`-keyed) is via `_lenient_number()` below, NOT
`content.schema.parse_number()` directly: FR-12/FR-13 require a SUBMITTED value like
`"07"` (a leading zero) or `"3.5"` (a `.` decimal) to compare correct against a
canonically-stored answer -- but `parse_number()`'s own `NUMERIC_PATTERN` (enforced on
stored answers for canonical-storage reasons, see `content/schema.py`) rejects both of
those shapes outright (`parse_number("07") is None`, `parse_number("3.5") is None`; see
this story's Spec Change Log for the direct verification). `_lenient_number()` is a
strictly MORE PERMISSIVE parse for untrusted, free-typed child input -- a different
concern from the schema's own canonical-storage validation, so it lives here, not in
`content/schema.py` (the Never-list rule against touching `content.schema` still
stands). The Part's own stored `answer` value is ALSO run through `_lenient_number()`
(not `parse_number()`) so both sides compare as the same Decimal regardless of which
one is used -- the stored answer is always canonical already, so lenient parsing of it
is a no-op in practice, just a uniform code path.

A submitted value that doesn't even parse into the expected shape (wrong JSON shape,
unknown key, wrong Python type) grades wrong for that slot (or the whole Part, for
all-or-nothing types) -- never an exception. A malformed payload is a normal, expected
input from an untrusted client, not a bug: never trust the payload's shape.

Submitted-value JSON shape per type (implementer's call per the frozen spec; documented
here and in the story's Implementation Notes):

- `number_input` / `number_tree` / `grid_fill` / `count_image` / `dot_draw` (multi-slot,
  keyed, numeric): `list[{"key": str, "value": str}]` -- one entry per slot, mirroring
  `NumericEntry`/`CountEntry`'s own shape exactly, so no shape translation is needed
  before grading.
- `compare` (multi-slot, keyed, non-numeric): `list[{"key": str, "value": "<"|">"|"="}]`
  -- the same list-of-entries shape, mirroring `CompareEntry`.
- `multiple_choice` / `image_select` (all-or-nothing): `{"selected": list[str]}`.
- `order` (all-or-nothing): `{"order": list[str]}`.
- `match` (all-or-nothing): `{"pairs": list[[left_key, right_key]]}`.
- `connect_dots` (all-or-nothing): `{"sequence": list[int]}`.
- `spot_difference` (all-or-nothing): `{"region_keys": list[str]}` -- only the
  `region_key` set matters for grading (region-key set equality, not exact bbox match,
  per the frozen intent), so the submitted shape carries just the keys, not full `Region`
  objects with bboxes the child never drew.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from hoctap.content.schema import (
    ComparePart,
    ConnectDotsPart,
    CountImagePart,
    DotDrawPart,
    FallbackPart,
    GridFillPart,
    ImageSelectPart,
    MatchPart,
    MultipleChoicePart,
    NumberInputPart,
    NumberTreePart,
    OrderPart,
    Part,
    SpotDifferencePart,
    answer_map,
)

# A leading zero is allowed here (unlike `content.schema.NUMERIC_PATTERN`, which forbids
# one on stored answers); either `,` or `.` is accepted as the decimal separator.
_LENIENT_NUMBER_RE = re.compile(r"^-?[0-9]+([.,][0-9]+)?$")


def _lenient_number(value: str) -> Decimal | None:
    """A submitted numeric value, tolerant of a leading zero (`"07"`) and either decimal
    separator (`","` or `"."`) -- FR-12/FR-13's exact tolerance for a child's free-typed
    answer. None if `value` isn't a number at all (graded wrong for that slot, not an
    error)."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _LENIENT_NUMBER_RE.fullmatch(text):
        return None
    try:
        number = Decimal(text.replace(",", "."))
    except InvalidOperation:  # pragma: no cover - the regex above already guards this
        return None
    return Decimal(0) if number == 0 else number  # "-0"/"-0,0" compare equal to "0"


@dataclass(frozen=True)
class GradeResult:
    correct: bool
    wrong_keys: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- multi-slot


def _keyed_submitted_map(submitted: Any) -> dict[str, str] | None:
    """`list[{"key": str, "value": str}]` loosely parsed to `{key: value}`; None if the
    shape is unusable at all (not a list, or an entry isn't a `{key: str, value: str}`
    object) -- the caller then grades every known key wrong, not crashes."""
    if not isinstance(submitted, list):
        return None
    out: dict[str, str] = {}
    for entry in submitted:
        if not isinstance(entry, dict):
            return None
        key, value = entry.get("key"), entry.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        out[key] = value
    return out


def _grade_keyed(answer: dict[str, str], submitted: Any, *, numeric: bool) -> GradeResult:
    """Every keyed slot graded independently (FR-12): a slot present on one side only
    (submitted but not in the Part's own answer, or vice versa) counts as wrong for that
    key, not silently ignored."""
    submitted_map = _keyed_submitted_map(submitted)
    if submitted_map is None:
        return GradeResult(False, sorted(answer))
    wrong: list[str] = []
    for key in sorted(set(answer) | set(submitted_map)):
        if key not in answer or key not in submitted_map:
            wrong.append(key)
            continue
        want, got = answer[key], submitted_map[key]
        if numeric:
            want_n, got_n = _lenient_number(want), _lenient_number(got)
            if want_n is None or got_n is None or want_n != got_n:
                wrong.append(key)
        elif want != got:
            wrong.append(key)
    return GradeResult(not wrong, wrong)


def grade_number_input(part: NumberInputPart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=True)


def grade_number_tree(part: NumberTreePart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=True)


def grade_grid_fill(part: GridFillPart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=True)


def grade_count_image(part: CountImagePart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=True)


def grade_dot_draw(part: DotDrawPart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=True)


def grade_compare(part: ComparePart, submitted: Any) -> GradeResult:
    return _grade_keyed(answer_map(part), submitted, numeric=False)


# --------------------------------------------------------------------------- all-or-nothing


def _grade_set(answer: list[str], submitted: Any, field_name: str) -> GradeResult:
    """Set equality for `{field_name: list[str]}` -- correct or wrong as a whole, no
    partial-credit key list (these types have no independent keyed slots to report)."""
    if not isinstance(submitted, dict):
        return GradeResult(False)
    got = submitted.get(field_name)
    if not isinstance(got, list) or not all(isinstance(v, str) for v in got):
        return GradeResult(False)
    return GradeResult(set(got) == set(answer))


def grade_multiple_choice(part: MultipleChoicePart, submitted: Any) -> GradeResult:
    return _grade_set(part.answer.selected, submitted, "selected")


def grade_image_select(part: ImageSelectPart, submitted: Any) -> GradeResult:
    return _grade_set(part.answer.selected, submitted, "selected")


def grade_order(part: OrderPart, submitted: Any) -> GradeResult:
    if not isinstance(submitted, dict):
        return GradeResult(False)
    order = submitted.get("order")
    if not isinstance(order, list) or not all(isinstance(v, str) for v in order):
        return GradeResult(False)
    return GradeResult(order == part.answer.order)


def grade_match(part: MatchPart, submitted: Any) -> GradeResult:
    if not isinstance(submitted, dict):
        return GradeResult(False)
    pairs = submitted.get("pairs")
    if not isinstance(pairs, list):
        return GradeResult(False)
    got: set[tuple[str, str]] = set()
    for pair in pairs:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(v, str) for v in pair)
        ):
            return GradeResult(False)
        got.add((pair[0], pair[1]))
    want = {(left, right) for left, right in part.answer.pairs}
    return GradeResult(got == want)


def grade_connect_dots(part: ConnectDotsPart, submitted: Any) -> GradeResult:
    if not isinstance(submitted, dict):
        return GradeResult(False)
    sequence = submitted.get("sequence")
    if not isinstance(sequence, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in sequence
    ):
        return GradeResult(False)
    return GradeResult(sequence == part.answer.sequence)


def grade_spot_difference(part: SpotDifferencePart, submitted: Any) -> GradeResult:
    if not isinstance(submitted, dict):
        return GradeResult(False)
    region_keys = submitted.get("region_keys")
    if not isinstance(region_keys, list) or not all(isinstance(v, str) for v in region_keys):
        return GradeResult(False)
    want = {r.region_key for r in part.answer.regions}
    return GradeResult(set(region_keys) == want)


# --------------------------------------------------------------------------- dispatch

_GRADERS: dict[type, Any] = {
    NumberInputPart: grade_number_input,
    ComparePart: grade_compare,
    MultipleChoicePart: grade_multiple_choice,
    ImageSelectPart: grade_image_select,
    OrderPart: grade_order,
    NumberTreePart: grade_number_tree,
    GridFillPart: grade_grid_fill,
    MatchPart: grade_match,
    CountImagePart: grade_count_image,
    DotDrawPart: grade_dot_draw,
    ConnectDotsPart: grade_connect_dots,
    SpotDifferencePart: grade_spot_difference,
}


def grade_part(part: Part, submitted: Any) -> GradeResult:
    """Dispatches to the Part type's own grading function.

    `FallbackPart` is never graded (`answer` is always None, solution-only) -- raises
    `TypeError`, a programmer error: the caller (`learning.sessions.post_event()`) must
    reject an attempt on a `fallback` Part with a 422 before ever calling this.
    """
    if isinstance(part, FallbackPart):
        raise TypeError("FallbackPart has no answer to grade against")
    grader = _GRADERS.get(type(part))
    if grader is None:  # pragma: no cover - defensive; every non-fallback type is registered
        raise TypeError(f"no grader registered for {type(part).__name__}")
    return grader(part, submitted)
