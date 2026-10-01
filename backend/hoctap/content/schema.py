"""ProblemDoc v1: the one contract for a Problem (AD-1).

The extractor, graders, widgets, print renderer, review overrides and Attempts all use
this shape, and address content by (`problem_id`, `part_key`, `slot_key`), never by
array position.

Each Problem Type has two classes:

- a child-visible *view* (`NumberInputView`, ...): the common Part fields plus the
  type's structure, with the structural validators;
- the full *Part* (`NumberInputPart`, ...): the view plus the answer-bearing fields
  `answer`, `hint` and `solution`, with the answer-coverage validators.

`hoctap.content.views.child_view()` projects a ProblemDoc onto the views, so Answer
Keys, Hints and Solutions never reach the child (AD-5). Only the Part's `answer`,
`hint` and `solution` fields carry answer content.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)

from hoctap.content.arith import evaluate

SCHEMA_VERSION = "v1"

KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,15}$"
BOOK_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,31}$"
CONCEPT_ID_PATTERN = r"^g[1-5]\.[a-z0-9][a-z0-9-]{0,47}$"
# Canonical numbers: decimal comma (Vietnamese "." groups thousands), no leading zeros,
# no negative zero. Counts are non-negative integers.
NUMERIC_PATTERN = r"^-?(0|[1-9][0-9]*)(,[0-9]+)?$"
COUNT_PATTERN = r"^(0|[1-9][0-9]*)$"
_NUMERIC_RE = re.compile(NUMERIC_PATTERN)
SLOT_MARKER = re.compile(r"\[\[([^\[\]]*)\]\]")


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


# Vietnamese text with the inline LaTeX subset; always stored NFC.
Text = Annotated[str, AfterValidator(_nfc)]
NonEmptyText = Annotated[str, AfterValidator(_nfc), AfterValidator(_non_blank)]
Key = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]


def parse_number(value: str) -> Decimal | None:
    """A canonical numeric string as a Decimal, or None if it is not one."""
    if not _NUMERIC_RE.fullmatch(value):
        return None
    number = Decimal(value.replace(",", "."))
    return None if value.startswith("-") and number == 0 else number


def _no_negative_zero(value: str) -> str:
    if value.startswith("-") and parse_number(value) is None:
        raise ValueError(f"{value!r} is negative zero; write it without the sign")
    return value


NumericString = Annotated[
    str, StringConstraints(pattern=NUMERIC_PATTERN), AfterValidator(_no_negative_zero)
]
CountString = Annotated[str, StringConstraints(pattern=COUNT_PATTERN)]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]


def _check_bbox(bbox: list[float]) -> list[float]:
    x0, y0, x1, y1 = bbox
    if not (x0 < x1 and y0 < y1):
        raise ValueError(f"bbox must have x0 < x1 and y0 < y1, got {list(bbox)}")
    return bbox


# [x0, y0, x1, y1] normalised 0-1, x0 < x1, y0 < y1; the frame (page or image) is stated
# on each field. A list rather than a tuple, so the
# extraction schema keeps `items` (transform_schema has no `prefixItems`).
BBox = Annotated[list[Unit], Field(min_length=4, max_length=4), AfterValidator(_check_bbox)]
# [left item_key, right item_key]
KeyPair = Annotated[list[Key], Field(min_length=2, max_length=2)]


def _const_as_enum(schema: dict[str, Any]) -> None:
    """Emit a one-value Literal as `enum`: `anthropic.transform_schema()` drops `const`."""
    if "const" in schema:
        schema["enum"] = [schema.pop("const")]


def _tag(name: str) -> Any:
    return Field(json_schema_extra=_const_as_enum, description=f"Problem Type: {name}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(keys: Iterable[str], what: str, where: str) -> None:
    dupes = sorted(k for k, n in Counter(keys).items() if n > 1)
    if dupes:
        raise ValueError(f"{where}: duplicate {what} {', '.join(repr(k) for k in dupes)}")


def _covers(answer_keys: Iterable[str], expected: Iterable[str], what: str, part_key: str) -> None:
    got, want = set(answer_keys), set(expected)
    missing, extra = sorted(want - got), sorted(got - want)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {', '.join(repr(k) for k in missing)}")
        if extra:
            details.append(f"unknown {', '.join(repr(k) for k in extra)}")
        raise ValueError(
            f"part {part_key!r}: answer must cover exactly its {what} ({'; '.join(details)})"
        )


def _check_selected(selected: list[str], known: list[str], multi: bool, part_key: str) -> None:
    _unique(selected, "selection", f"part {part_key!r}")
    unknown = sorted(set(selected) - set(known))
    if unknown:
        raise ValueError(
            f"part {part_key!r}: answer selects unknown key {', '.join(repr(k) for k in unknown)}"
        )
    if not selected:
        raise ValueError(f"part {part_key!r}: answer must select at least one key")
    if not multi and len(selected) != 1:
        raise ValueError(f"part {part_key!r}: multi is false, so exactly one key must be selected")


# --------------------------------------------------------------------------- shared


class SourcePage(_Model):
    page: int = Field(ge=1, description="1-based page number in the book PDF")
    bbox: BBox = Field(description="[x0, y0, x1, y1] normalised 0-1 on the page")


class ImageRef(_Model):
    image_key: Key
    page: int = Field(ge=1, description="1-based page; must be one of the source_pages")
    bbox: BBox = Field(description="[x0, y0, x1, y1] normalised 0-1 on the page")


class Solution(_Model):
    steps: list[NonEmptyText] = Field(min_length=1)
    final: NonEmptyText


class Slot(_Model):
    slot_key: Key


class LabeledSlot(_Model):
    slot_key: Key
    label: Text


class CompareRow(_Model):
    slot_key: Key
    left: NonEmptyText
    right: NonEmptyText


class ChoiceOption(_Model):
    option_key: Key
    text: NonEmptyText | None = None
    image_key: Key | None = None

    @model_validator(mode="after")
    def _has_content(self) -> ChoiceOption:
        if self.text is None and self.image_key is None:
            raise ValueError(f"option {self.option_key!r} needs text or image_key")
        return self


class Region(_Model):
    region_key: Key
    bbox: BBox = Field(description="[x0, y0, x1, y1] normalised 0-1 on the image (not the page)")


class OrderItem(_Model):
    item_key: Key
    text: NonEmptyText


class TreeNode(_Model):
    node_key: Key
    parent_key: Key | None = None
    given: NonEmptyText | None = Field(
        default=None, description="the printed value; a node without `given` is an Answer Slot"
    )


class GridCell(_Model):
    given: NonEmptyText | None = Field(
        default=None,
        description="the printed value; an empty cell is an Answer Slot keyed r{i}c{j} "
        "(0-based row i, column j)",
    )


class MatchItem(_Model):
    item_key: Key
    text: NonEmptyText | None = None
    image_key: Key | None = None

    @model_validator(mode="after")
    def _has_content(self) -> MatchItem:
        if self.text is None and self.image_key is None:
            raise ValueError(f"match item {self.item_key!r} needs text or image_key")
        return self


class Dot(_Model):
    n: StrictInt = Field(ge=1, description="the printed number; the dots are exactly 1..N")
    x: Unit = Field(description="normalised 0-1 on the image (not the page)")
    y: Unit = Field(description="normalised 0-1 on the image (not the page)")


class DotBox(_Model):
    slot_key: Key
    label: NonEmptyText = Field(description="the printed number or text under the box")
    given: int = Field(
        default=0, ge=0, description="dots already printed in the box (for 'draw more')"
    )


# --------------------------------------------------------------------------- views


class PartViewBase(_Model):
    """Common child-visible Part fields."""

    part_key: Key = Field(
        description="the book's own label (a, b, c) or p1, p2... in reading order"
    )
    type: str  # narrowed to a Literal tag by each Problem Type
    prompt: Text = Field(description="the Part's own text; may be empty")
    image_keys: list[Key]

    @model_validator(mode="after")
    def _image_keys_unique(self) -> PartViewBase:
        _unique(self.image_keys, "image_key", f"part {self.part_key!r}")
        return self

    def referenced_image_keys(self) -> list[str]:
        """Every image_key this Part points at (checked against the Problem's images)."""
        return list(self.image_keys)


class NumberInputView(PartViewBase):
    type: Literal["number_input"] = _tag("number_input")
    template: NonEmptyText = Field(description="text with [[slot_key]] markers")
    slots: list[Slot] = Field(min_length=1)

    @model_validator(mode="after")
    def _markers(self) -> NumberInputView:
        where = f"part {self.part_key!r}"
        keys = [s.slot_key for s in self.slots]
        _unique(keys, "slot_key", where)
        markers = SLOT_MARKER.findall(self.template)
        _unique(markers, "[[slot]] marker", where)
        if set(markers) != set(keys):
            raise ValueError(
                f"{where}: template markers {sorted(markers)} must match slots {sorted(keys)}"
            )
        return self


class ExpressionInputView(PartViewBase):
    type: Literal["expression_input"] = _tag("expression_input")
    template: NonEmptyText = Field(description="text with [[slot_key]] markers")
    slots: list[Slot] = Field(min_length=1)
    mode: Literal["value", "exact"] = Field(
        default="value",
        description="value: any expression with the key's exact value is correct; "
        "exact: only when the book demands a specific form (the same expression as the key)",
    )

    @model_validator(mode="after")
    def _markers(self) -> ExpressionInputView:
        where = f"part {self.part_key!r}"
        keys = [s.slot_key for s in self.slots]
        _unique(keys, "slot_key", where)
        markers = SLOT_MARKER.findall(self.template)
        _unique(markers, "[[slot]] marker", where)
        if set(markers) != set(keys):
            raise ValueError(
                f"{where}: template markers {sorted(markers)} must match slots {sorted(keys)}"
            )
        return self


class CompareView(PartViewBase):
    type: Literal["compare"] = _tag("compare")
    rows: list[CompareRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys(self) -> CompareView:
        _unique([r.slot_key for r in self.rows], "slot_key", f"part {self.part_key!r}")
        return self


class MultipleChoiceView(PartViewBase):
    type: Literal["multiple_choice"] = _tag("multiple_choice")
    options: list[ChoiceOption] = Field(min_length=2)
    multi: bool

    @model_validator(mode="after")
    def _keys(self) -> MultipleChoiceView:
        _unique([o.option_key for o in self.options], "option_key", f"part {self.part_key!r}")
        return self

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, *(o.image_key for o in self.options if o.image_key)]


class ImageSelectView(PartViewBase):
    type: Literal["image_select"] = _tag("image_select")
    image_key: Key
    regions: list[Region] = Field(min_length=1)
    multi: bool

    @model_validator(mode="after")
    def _keys(self) -> ImageSelectView:
        _unique([r.region_key for r in self.regions], "region_key", f"part {self.part_key!r}")
        return self

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, self.image_key]


class OrderView(PartViewBase):
    type: Literal["order"] = _tag("order")
    items: list[OrderItem] = Field(min_length=2)
    direction: Literal["asc", "desc", "custom"]

    @model_validator(mode="after")
    def _keys(self) -> OrderView:
        _unique([i.item_key for i in self.items], "item_key", f"part {self.part_key!r}")
        return self


class NumberTreeView(PartViewBase):
    type: Literal["number_tree"] = _tag("number_tree")
    nodes: list[TreeNode] = Field(min_length=2)

    @model_validator(mode="after")
    def _tree(self) -> NumberTreeView:
        where = f"part {self.part_key!r}"
        keys = [n.node_key for n in self.nodes]
        _unique(keys, "node_key", where)
        parents = {n.node_key: n.parent_key for n in self.nodes}
        for node in self.nodes:
            if node.parent_key is not None and node.parent_key not in parents:
                raise ValueError(
                    f"{where}: node {node.node_key!r} has unknown parent_key {node.parent_key!r}"
                )
        for start in keys:  # no cycles: every chain reaches a root
            seen: set[str] = set()
            key: str | None = start
            while key is not None:
                if key in seen:
                    raise ValueError(f"{where}: node {start!r} is in a parent_key cycle")
                seen.add(key)
                key = parents[key]
        roots = [n.node_key for n in self.nodes if n.parent_key is None]
        if len(roots) != 1:
            raise ValueError(f"{where}: the tree needs exactly one root, found {roots}")
        if not self.slot_keys():
            raise ValueError(f"{where}: at least one node must be an Answer Slot (no `given`)")
        return self

    def slot_keys(self) -> list[str]:
        return [n.node_key for n in self.nodes if n.given is None]


class GridFillView(PartViewBase):
    type: Literal["grid_fill"] = _tag("grid_fill")
    rows: int = Field(ge=1, le=20)
    cols: int = Field(ge=1, le=20)
    cells: list[list[GridCell]] = Field(min_length=1)

    @model_validator(mode="after")
    def _shape(self) -> GridFillView:
        where = f"part {self.part_key!r}"
        if len(self.cells) != self.rows or any(len(row) != self.cols for row in self.cells):
            raise ValueError(f"{where}: cells must be {self.rows} rows x {self.cols} cols")
        if not self.slot_keys():
            raise ValueError(f"{where}: at least one cell must be empty (an Answer Slot)")
        return self

    def slot_keys(self) -> list[str]:
        return [
            f"r{i}c{j}"
            for i, row in enumerate(self.cells)
            for j, cell in enumerate(row)
            if cell.given is None
        ]


class MatchView(PartViewBase):
    type: Literal["match"] = _tag("match")
    left: list[MatchItem] = Field(min_length=1)
    right: list[MatchItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys(self) -> MatchView:
        _unique([i.item_key for i in self.left], "left item_key", f"part {self.part_key!r}")
        _unique([i.item_key for i in self.right], "right item_key", f"part {self.part_key!r}")
        return self

    def referenced_image_keys(self) -> list[str]:
        items = [*self.left, *self.right]
        return [*self.image_keys, *(i.image_key for i in items if i.image_key)]


class CountImageView(PartViewBase):
    type: Literal["count_image"] = _tag("count_image")
    image_key: Key
    slots: list[LabeledSlot] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys(self) -> CountImageView:
        _unique([s.slot_key for s in self.slots], "slot_key", f"part {self.part_key!r}")
        return self

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, self.image_key]


class DotDrawView(PartViewBase):
    type: Literal["dot_draw"] = _tag("dot_draw")
    boxes: list[DotBox] = Field(min_length=1)

    @model_validator(mode="after")
    def _keys(self) -> DotDrawView:
        _unique([b.slot_key for b in self.boxes], "slot_key", f"part {self.part_key!r}")
        return self


class ConnectDotsView(PartViewBase):
    type: Literal["connect_dots"] = _tag("connect_dots")
    image_key: Key
    dots: list[Dot] = Field(min_length=2)

    @model_validator(mode="after")
    def _numbers(self) -> ConnectDotsView:
        where = f"part {self.part_key!r}"
        _unique([str(d.n) for d in self.dots], "dot number", where)
        if sorted(d.n for d in self.dots) != list(range(1, len(self.dots) + 1)):
            raise ValueError(f"{where}: dot numbers must be exactly 1..{len(self.dots)}")
        return self

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, self.image_key]


class SpotDifferenceView(PartViewBase):
    type: Literal["spot_difference"] = _tag("spot_difference")
    image_left: Key
    image_right: Key
    count: int = Field(ge=1, le=20, description="how many differences the child must find")

    @model_validator(mode="after")
    def _two_images(self) -> SpotDifferenceView:
        if self.image_left == self.image_right:
            raise ValueError(f"part {self.part_key!r}: image_left and image_right must differ")
        return self

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, self.image_left, self.image_right]


class FallbackView(PartViewBase):
    type: Literal["fallback"] = _tag("fallback")
    image_key: Key = Field(description="the cropped Problem, shown as it is printed")

    def referenced_image_keys(self) -> list[str]:
        return [*self.image_keys, self.image_key]


# --------------------------------------------------------------------------- parts


class AnswerBearing(_Model):
    """The fields a child must never see: the Answer Key lives in each Part's `answer`."""

    hint: NonEmptyText = Field(description="one hint for the child; never contains the answer")
    solution: Solution


class NumericEntry(_Model):
    """One keyed answer value: `key` is a slot_key, empty node_key or empty cell `r{i}c{j}`."""

    key: Key
    value: NumericString


class CountEntry(_Model):
    """A count: a non-negative integer (count_image, dot_draw)."""

    key: Key = Field(description="a slot_key")
    value: CountString


EXPRESSION_MAX = 100


class ExpressionEntry(_Model):
    """One expression answer: `key` is a slot_key, `value` an arithmetic expression
    ("36", "(4 × 3) × 3", "3,5", "1/2")."""

    key: Key
    value: Annotated[
        str, AfterValidator(_nfc), StringConstraints(min_length=1, max_length=EXPRESSION_MAX)
    ]

    @model_validator(mode="after")
    def _evaluable(self) -> ExpressionEntry:
        if evaluate(self.value) is None:
            raise ValueError(f"{self.value!r} is not an arithmetic expression")
        return self


class CompareEntry(_Model):
    key: Key = Field(description="a row's slot_key")
    value: Literal["<", ">", "="]


def _entry_keys(
    entries: list[NumericEntry] | list[CountEntry] | list[CompareEntry] | list[ExpressionEntry],
    part_key: str,
) -> list[str]:
    keys = [e.key for e in entries]
    _unique(keys, "answer key", f"part {part_key!r}")
    return keys


class SelectedAnswer(_Model):
    selected: list[Key]


class OrderAnswer(_Model):
    order: list[Key]


class MatchAnswer(_Model):
    pairs: list[KeyPair] = Field(min_length=1, description="[left item_key, right item_key]")


class SequenceAnswer(_Model):
    sequence: list[StrictInt] = Field(description="the dot numbers in drawing order: 1..N")


class SpotDifferenceAnswer(_Model):
    regions: list[Region] = Field(description="the differences, on the right image")


class NumberInputPart(AnswerBearing, NumberInputView):
    answer: list[NumericEntry] = Field(description="[{key, value}], one per slot_key")

    @model_validator(mode="after")
    def _answer(self) -> NumberInputPart:
        _covers(
            _entry_keys(self.answer, self.part_key),
            [s.slot_key for s in self.slots],
            "slots",
            self.part_key,
        )
        return self


class ExpressionInputPart(AnswerBearing, ExpressionInputView):
    answer: list[ExpressionEntry] = Field(
        description="[{key, value}], one per slot_key; value is an arithmetic expression"
    )

    @model_validator(mode="after")
    def _answer(self) -> ExpressionInputPart:
        _covers(
            _entry_keys(self.answer, self.part_key),
            [s.slot_key for s in self.slots],
            "slots",
            self.part_key,
        )
        return self


class ComparePart(AnswerBearing, CompareView):
    answer: list[CompareEntry] = Field(description="[{key, value}], one per row slot_key")

    @model_validator(mode="after")
    def _answer(self) -> ComparePart:
        _covers(
            _entry_keys(self.answer, self.part_key),
            [r.slot_key for r in self.rows],
            "rows",
            self.part_key,
        )
        return self


class MultipleChoicePart(AnswerBearing, MultipleChoiceView):
    answer: SelectedAnswer

    @model_validator(mode="after")
    def _answer(self) -> MultipleChoicePart:
        known = [o.option_key for o in self.options]
        _check_selected(self.answer.selected, known, self.multi, self.part_key)
        return self


class ImageSelectPart(AnswerBearing, ImageSelectView):
    answer: SelectedAnswer

    @model_validator(mode="after")
    def _answer(self) -> ImageSelectPart:
        known = [r.region_key for r in self.regions]
        _check_selected(self.answer.selected, known, self.multi, self.part_key)
        return self


class OrderPart(AnswerBearing, OrderView):
    answer: OrderAnswer

    @model_validator(mode="after")
    def _answer(self) -> OrderPart:
        order = self.answer.order
        _unique(order, "item_key in answer", f"part {self.part_key!r}")
        _covers(order, [i.item_key for i in self.items], "items", self.part_key)
        texts = {i.item_key: i.text for i in self.items}
        numbers = [parse_number(texts[key]) for key in order]
        if self.direction != "custom" and all(n is not None for n in numbers):
            want = sorted(numbers, reverse=self.direction == "desc")  # type: ignore[type-var]
            if numbers != want:
                raise ValueError(
                    f"part {self.part_key!r}: answer order is not {self.direction} by number"
                )
        return self


class NumberTreePart(AnswerBearing, NumberTreeView):
    answer: list[NumericEntry] = Field(description="[{key, value}], one per empty node_key")

    @model_validator(mode="after")
    def _answer(self) -> NumberTreePart:
        _covers(
            _entry_keys(self.answer, self.part_key), self.slot_keys(), "empty nodes", self.part_key
        )
        return self


class GridFillPart(AnswerBearing, GridFillView):
    answer: list[NumericEntry] = Field(description="[{key, value}], one per empty cell r{i}c{j}")

    @model_validator(mode="after")
    def _answer(self) -> GridFillPart:
        _covers(
            _entry_keys(self.answer, self.part_key), self.slot_keys(), "empty cells", self.part_key
        )
        return self


class MatchPart(AnswerBearing, MatchView):
    answer: MatchAnswer

    @model_validator(mode="after")
    def _answer(self) -> MatchPart:
        where = f"part {self.part_key!r}"
        lefts = [left for left, _ in self.answer.pairs]
        _unique(lefts, "left item_key in answer", where)
        _covers(lefts, [i.item_key for i in self.left], "left items", self.part_key)
        right_keys = {i.item_key for i in self.right}
        unknown = sorted({right for _, right in self.answer.pairs} - right_keys)
        if unknown:
            raise ValueError(
                f"{where}: answer pairs use unknown right item_key "
                f"{', '.join(repr(k) for k in unknown)}"
            )
        return self


class CountImagePart(AnswerBearing, CountImageView):
    answer: list[CountEntry] = Field(description="[{key, value}], one per slot_key")

    @model_validator(mode="after")
    def _answer(self) -> CountImagePart:
        _covers(
            _entry_keys(self.answer, self.part_key),
            [s.slot_key for s in self.slots],
            "slots",
            self.part_key,
        )
        return self


class DotDrawPart(AnswerBearing, DotDrawView):
    answer: list[CountEntry] = Field(
        description="[{key, value}], one per slot_key; value = total dots, given included"
    )

    @model_validator(mode="after")
    def _answer(self) -> DotDrawPart:
        _covers(
            _entry_keys(self.answer, self.part_key),
            [b.slot_key for b in self.boxes],
            "boxes",
            self.part_key,
        )
        values = {e.key: int(e.value) for e in self.answer}
        for box in self.boxes:
            if values[box.slot_key] < box.given:
                raise ValueError(
                    f"part {self.part_key!r}: box {box.slot_key!r} answer {values[box.slot_key]} "
                    f"is less than the {box.given} dots already given"
                )
        return self


class ConnectDotsPart(AnswerBearing, ConnectDotsView):
    answer: SequenceAnswer

    @model_validator(mode="after")
    def _answer(self) -> ConnectDotsPart:
        if self.answer.sequence != list(range(1, len(self.dots) + 1)):
            raise ValueError(
                f"part {self.part_key!r}: answer sequence must be 1..{len(self.dots)} in order"
            )
        return self


class SpotDifferencePart(AnswerBearing, SpotDifferenceView):
    answer: SpotDifferenceAnswer

    @model_validator(mode="after")
    def _answer(self) -> SpotDifferencePart:
        where = f"part {self.part_key!r}"
        _unique([r.region_key for r in self.answer.regions], "region_key in answer", where)
        if len(self.answer.regions) != self.count:
            raise ValueError(f"{where}: answer must have exactly count={self.count} regions")
        return self


class FallbackPart(AnswerBearing, FallbackView):
    answer: None = Field(default=None, description="always null: the solution only")


Part = Annotated[
    NumberInputPart
    | ExpressionInputPart
    | ComparePart
    | MultipleChoicePart
    | ImageSelectPart
    | OrderPart
    | NumberTreePart
    | GridFillPart
    | MatchPart
    | CountImagePart
    | DotDrawPart
    | ConnectDotsPart
    | SpotDifferencePart
    | FallbackPart,
    Field(discriminator="type"),
]

PROBLEM_TYPES: tuple[str, ...] = (
    "number_input",
    "expression_input",
    "compare",
    "multiple_choice",
    "image_select",
    "order",
    "number_tree",
    "grid_fill",
    "match",
    "count_image",
    "dot_draw",
    "connect_dots",
    "spot_difference",
    "fallback",
)

ANSWER_FIELDS: frozenset[str] = frozenset({"answer", "hint", "solution"})


# --------------------------------------------------------------------------- problem


class ProblemHeader(_Model):
    """The top-level ProblemDoc fields; shared by `ProblemDoc` and `ChildProblemView`."""

    schema_version: Literal["v1"] = Field(json_schema_extra=_const_as_enum)
    problem_id: str = Field(description="{book_id}.{unit_key}.{lesson_key}.{problem_label}")
    book_id: Annotated[str, StringConstraints(pattern=BOOK_ID_PATTERN)]
    unit_key: Key
    lesson_key: Key
    problem_label: Key
    display_label: NonEmptyText = Field(description='as printed, e.g. "Bài 3"')
    instruction: Text
    layout: Literal["sequence", "together"] = Field(
        description="sequence: the Parts are shown one at a time, in order; "
        "together: all Parts are shown at once on one screen"
    )
    source_pages: list[SourcePage] = Field(min_length=1)
    images: list[ImageRef]
    concept_ids: list[Annotated[str, StringConstraints(pattern=CONCEPT_ID_PATTERN)]] = Field(
        description="existing curated Concept ids, e.g. g1.so-sanh-so; may be empty"
    )
    concept_proposals: list[NonEmptyText] = Field(
        description="names of new Concepts proposed for review (not existing concept_ids); "
        "may be empty, and both lists may be empty while tags are pending"
    )

    def _check_header(self, parts: list[PartViewBase]) -> None:
        composed = f"{self.book_id}.{self.unit_key}.{self.lesson_key}.{self.problem_label}"
        if self.problem_id != composed:
            raise ValueError(f"problem_id {self.problem_id!r} must equal {composed!r}")
        _unique([i.image_key for i in self.images], "image_key", "images")
        _unique(self.concept_ids, "concept_id", "concept_ids")
        _unique(self.concept_proposals, "concept proposal", "concept_proposals")
        pages = {p.page for p in self.source_pages}
        for image in self.images:
            if image.page not in pages:
                raise ValueError(
                    f"image {image.image_key!r} is on page {image.page}, "
                    f"which is not in source_pages {sorted(pages)}"
                )
        _unique([p.part_key for p in parts], "part_key", "parts")
        known = {i.image_key for i in self.images}
        for part in parts:
            for key in part.referenced_image_keys():
                if key not in known:
                    raise ValueError(
                        f"part {part.part_key!r}: image_key {key!r} is not in the Problem's images"
                    )


class ProblemDoc(ProblemHeader):
    """ProblemDoc v1. Answers live only in each Part's `answer`, `hint` and `solution`."""

    parts: list[Part] = Field(min_length=1)

    @model_validator(mode="after")
    def _cross_refs(self) -> ProblemDoc:
        self._check_header(list(self.parts))
        self._check_fallback_not_mixed()
        return self

    def _check_fallback_not_mixed(self) -> None:
        """Review Triage Log #3 (spec-3-1, 2026-10-01, low): `learning/scoring.py`'s
        `compute_problem_stars()` routes a WHOLE Problem through fallback-only scoring the
        moment ANY Part is a `FallbackPart` (`any(isinstance(p, FallbackPart) for p in
        parts)`) -- so a Problem mixing a `FallbackPart` with graded Parts would silently
        discard the graded Parts' `attempt` events for Star purposes, with no error
        anywhere. Rejected here, at content-authoring/validation time, so that ambiguous
        shape can never exist in the first place; cheaper and more robust than a defensive
        runtime check in `scoring.py`, since every path that can create a `ProblemDoc`
        (content pipeline ingestion, hand-authored fixtures, future editor UI) already goes
        through this same Pydantic validation."""
        has_fallback = any(isinstance(p, FallbackPart) for p in self.parts)
        has_graded = any(not isinstance(p, FallbackPart) for p in self.parts)
        if has_fallback and has_graded:
            raise ValueError(
                "a Problem cannot mix a fallback Part with graded Parts -- scoring routes "
                "the whole Problem through fallback-only scoring the moment any Part is a "
                "FallbackPart, which would silently discard the graded Parts' attempts"
            )


# --------------------------------------------------------------------------- concept guide

GUIDE_EXPLANATION_MAX = 300  # the prompt asks for about 280 characters
GUIDE_QUESTION_MAX = 200
GUIDE_STEP_MAX = 160
GUIDE_STEPS_MAX = 5
GUIDE_ANSWER_MAX = 100


class GuideExample(_Model):
    """The one worked example of a Concept Guide."""

    question: Annotated[NonEmptyText, StringConstraints(max_length=GUIDE_QUESTION_MAX)]
    steps: list[Annotated[NonEmptyText, StringConstraints(max_length=GUIDE_STEP_MAX)]] = Field(
        min_length=1, max_length=GUIDE_STEPS_MAX
    )
    answer: Annotated[NonEmptyText, StringConstraints(max_length=GUIDE_ANSWER_MAX)]


class ConceptGuideDoc(_Model):
    """A Concept Guide: a short explanation plus one worked example (Story 5.1). The one
    validator of generated and edited Guide text; it fits one tablet screen."""

    explanation: Annotated[NonEmptyText, StringConstraints(max_length=GUIDE_EXPLANATION_MAX)]
    example: GuideExample


def problemdoc_json_schema() -> dict[str, Any]:
    """The ProblemDoc v1 JSON Schema, as committed in `problemdoc.schema.json`."""
    return ProblemDoc.model_json_schema()


KEYED_ANSWER_TYPES = (
    NumberInputPart,
    ExpressionInputPart,
    ComparePart,
    NumberTreePart,
    GridFillPart,
    CountImagePart,
    DotDrawPart,
)


def answer_map(part: Any) -> dict[str, str]:
    """The keyed answer of a Part as `{key: value}`, for graders."""
    if not isinstance(part, KEYED_ANSWER_TYPES):
        raise TypeError(f"{type(part).__name__} has no keyed answer")
    return {entry.key: entry.value for entry in part.answer}
