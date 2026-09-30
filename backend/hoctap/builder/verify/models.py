"""`VerifyPage`: the model's independent second answer for the Problems of one page.

`{problems: [{problem_id, parts: [{part_key, type, answer, unsure?}]}]}`. Each Part is a
union discriminated by `type`, and `answer` reuses the Story 1.4 answer models of that
Part type, so the second answer has exactly the shape of the extracted one (AD-1).
`unsure: true` marks a Part the model could not solve with confidence.

`VerifyEnvelope` is the loose page shape checked when a result is collected; each
Problem is validated on its own when it is compared, so one malformed Problem never
loses the rest of the page.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hoctap.builder.extraction.models import drop_titles
from hoctap.content.schema import (
    CompareEntry,
    CountEntry,
    ExpressionEntry,
    Key,
    MatchAnswer,
    NumericEntry,
    OrderAnswer,
    SelectedAnswer,
    SequenceAnswer,
    SpotDifferenceAnswer,
)


def _const_as_enum(schema: dict[str, Any]) -> None:
    """A one-value Literal as `enum`: `anthropic.transform_schema()` drops `const`."""
    if "const" in schema:
        schema["enum"] = [schema.pop("const")]


def _tag(name: str) -> Any:
    return Field(json_schema_extra=_const_as_enum, description=f"the Part's type: {name}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _VerifyPart(_Model):
    part_key: Key = Field(description="the Part's part_key, exactly as given")
    unsure: bool = Field(
        default=False,
        description="true when you cannot solve the Part with confidence (instead of guessing)",
    )


class NumberInputSecond(_VerifyPart):
    type: Literal["number_input"] = _tag("number_input")
    answer: list[NumericEntry] = Field(description="[{key, value}], one per slot_key")


class ExpressionInputSecond(_VerifyPart):
    type: Literal["expression_input"] = _tag("expression_input")
    answer: list[ExpressionEntry] = Field(
        description="[{key, value}], one per slot_key; value is an arithmetic expression"
    )


class CompareSecond(_VerifyPart):
    type: Literal["compare"] = _tag("compare")
    answer: list[CompareEntry] = Field(description="[{key, value}], one per row slot_key")


class MultipleChoiceSecond(_VerifyPart):
    type: Literal["multiple_choice"] = _tag("multiple_choice")
    answer: SelectedAnswer


class ImageSelectSecond(_VerifyPart):
    type: Literal["image_select"] = _tag("image_select")
    answer: SelectedAnswer


class OrderSecond(_VerifyPart):
    type: Literal["order"] = _tag("order")
    answer: OrderAnswer


class NumberTreeSecond(_VerifyPart):
    type: Literal["number_tree"] = _tag("number_tree")
    answer: list[NumericEntry] = Field(description="[{key, value}], one per empty node_key")


class GridFillSecond(_VerifyPart):
    type: Literal["grid_fill"] = _tag("grid_fill")
    answer: list[NumericEntry] = Field(description="[{key, value}], one per empty cell r{i}c{j}")


class MatchSecond(_VerifyPart):
    type: Literal["match"] = _tag("match")
    answer: MatchAnswer


class CountImageSecond(_VerifyPart):
    type: Literal["count_image"] = _tag("count_image")
    answer: list[CountEntry] = Field(description="[{key, value}], one per slot_key")


class DotDrawSecond(_VerifyPart):
    type: Literal["dot_draw"] = _tag("dot_draw")
    answer: list[CountEntry] = Field(
        description="[{key, value}], one per slot_key; value = total dots, given included"
    )


class ConnectDotsSecond(_VerifyPart):
    type: Literal["connect_dots"] = _tag("connect_dots")
    answer: SequenceAnswer


class SpotDifferenceSecond(_VerifyPart):
    type: Literal["spot_difference"] = _tag("spot_difference")
    answer: SpotDifferenceAnswer


class FallbackSecond(_VerifyPart):
    type: Literal["fallback"] = _tag("fallback")
    answer: None = Field(description="always null")


SecondPart = Annotated[
    NumberInputSecond
    | ExpressionInputSecond
    | CompareSecond
    | MultipleChoiceSecond
    | ImageSelectSecond
    | OrderSecond
    | NumberTreeSecond
    | GridFillSecond
    | MatchSecond
    | CountImageSecond
    | DotDrawSecond
    | ConnectDotsSecond
    | SpotDifferenceSecond
    | FallbackSecond,
    Field(discriminator="type"),
]


class VerifyProblem(_Model):
    problem_id: str = Field(description="the Problem's problem_id, exactly as given")
    parts: list[SecondPart] = Field(description="one entry per Part of the Problem")


class VerifyPage(_Model):
    """The second answers for every Problem given for one page."""

    problems: list[VerifyProblem]


class VerifyEnvelope(BaseModel):
    """The loose page shape: each Problem is checked when it is compared."""

    model_config = ConfigDict(extra="ignore")

    problems: list[Any]


VERIFY_SCHEMA_PATH = Path(__file__).resolve().parent / "verify_page.schema.json"


def build_verify_schema() -> dict[str, Any]:
    """`anthropic.transform_schema(VerifyPage)` without the cosmetic titles. Regenerate the
    committed copy with `hoctap export-verify-schema` whenever the models change; a test
    checks it."""
    import anthropic  # slow to import, so only here

    return drop_titles(anthropic.transform_schema(VerifyPage))


@cache
def verify_schema() -> dict[str, Any]:
    """The `--json-schema` for one verify call, from the committed `verify_page.schema.json`."""
    return json.loads(VERIFY_SCHEMA_PATH.read_text(encoding="utf-8"))
