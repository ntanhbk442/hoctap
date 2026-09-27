"""`PageExtraction`: the model's structured output for one scanned page.

It reuses the ProblemDoc Part union (answer, hint and solution included), so extraction
and runtime share one contract (AD-1). The structural keys (`unit_key`, `lesson_key`,
`problem_id`) are not extracted: `builder.stages.validate` assigns them deterministically.

Drafts are validated one by one in the validate stage, so one bad draft never loses the
rest of the page; `PageEnvelope` is the loose shape checked when a result is collected.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hoctap.content.schema import BBox, Key, NonEmptyText, Part, Text, Unit


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Heading(_Model):
    label: NonEmptyText = Field(
        description='the heading label as printed, e.g. "TUẦN 3", "Tiết 2", '
        '"Phiếu tự luyện cuối tuần", "Chương 1", "Chủ đề 2"'
    )
    title: Text = Field(description="the heading's title text after the label; may be empty")
    y: Unit = Field(
        description="the top edge of the heading, normalised 0-1 on the page (0 = page top)"
    )


class DraftImage(_Model):
    image_key: Key = Field(description="a short lowercase key, e.g. hinh-1, tranh-ga")
    on_next_page: bool = Field(
        description="true only when the image is on the NEXT page (a continued problem)"
    )
    bbox: BBox = Field(description="[x0, y0, x1, y1] normalised 0-1 on the page the image is on")


class ProblemDraft(_Model):
    problem_label: Key = Field(
        description='the printed number as a key: "Bài 3" -> "bai3", "Bài 12" -> "bai12"'
    )
    display_label: NonEmptyText = Field(description='as printed, e.g. "Bài 3"')
    instruction: Text = Field(description="the problem's instruction, Vietnamese NFC")
    layout: Literal["sequence", "together"] = Field(
        description="sequence: Parts shown one at a time; together: all Parts on one screen"
    )
    bbox: BBox = Field(
        description="[x0, y0, x1, y1] normalised 0-1: the whole problem on THIS page"
    )
    images: list[DraftImage]
    parts: list[Part] = Field(min_length=1)
    concept_proposals: list[NonEmptyText] = Field(
        description="1-3 short Vietnamese names of the maths concepts practised"
    )
    continues_on_next_page: bool = Field(
        description="true when the problem starts on this page and continues on the next"
    )
    next_page_bbox: BBox | None = Field(
        description="the continued part on the NEXT page, normalised 0-1; "
        "null unless continues_on_next_page"
    )

    @model_validator(mode="after")
    def _continuation(self) -> ProblemDraft:
        if self.continues_on_next_page and self.next_page_bbox is None:
            raise ValueError("continues_on_next_page needs next_page_bbox")
        if not self.continues_on_next_page:
            if self.next_page_bbox is not None:
                raise ValueError("next_page_bbox is set but continues_on_next_page is false")
            on_next = [i.image_key for i in self.images if i.on_next_page]
            if on_next:
                raise ValueError(
                    f"images {on_next} are on the next page but continues_on_next_page is false"
                )
        return self


class WorkedExample(_Model):
    title: Text = Field(description='e.g. "Ví dụ 1" or the theory box title; may be empty')
    text: NonEmptyText = Field(description="the full text, Vietnamese NFC, inline LaTeX subset")


class PageExtraction(_Model):
    """Everything extracted from one page. Only problems that START on this page."""

    unit_heading: Heading | None = Field(
        description='the week or chapter heading ("TUẦN 3", "Chương 1") if printed on this page'
    )
    lesson_heading: Heading | None = Field(
        description='the lesson heading ("Tiết 2", "Phiếu tự luyện cuối tuần") if printed'
    )
    problems: list[ProblemDraft]
    worked_examples: list[WorkedExample] = Field(
        description="theory boxes and Ví dụ blocks; never problems"
    )
    page_notes: Text = Field(description='short notes, e.g. "blank page", "cover"; may be empty')


class PageEnvelope(BaseModel):
    """The loose page shape: the headings are checked later, drafts one at a time."""

    model_config = ConfigDict(extra="ignore")

    unit_heading: dict[str, Any] | None = None
    lesson_heading: dict[str, Any] | None = None
    problems: list[Any]
    worked_examples: list[Any] = []
    page_notes: str = ""


def drop_titles(node: Any, in_properties: bool = False) -> Any:
    """Removes the cosmetic `title` annotations (not properties named "title")."""
    if isinstance(node, dict):
        return {
            key: drop_titles(value, key in ("properties", "$defs"))
            for key, value in node.items()
            if in_properties or not (key == "title" and isinstance(value, str))
        }
    if isinstance(node, list):
        return [drop_titles(value) for value in node]
    return node


EXTRACTION_SCHEMA_PATH = Path(__file__).resolve().parent / "page_extraction.schema.json"


def build_extraction_schema() -> dict[str, Any]:
    """`anthropic.transform_schema(PageExtraction)` without the cosmetic titles (the schema
    travels on the command line). Regenerate the committed copy with
    `hoctap export-extraction-schema` whenever the models change; a test checks it."""
    import anthropic  # slow to import (tens of seconds on /mnt/c), so only here

    return drop_titles(anthropic.transform_schema(PageExtraction))


@cache
def extraction_schema() -> dict[str, Any]:
    """The `--json-schema` for one page, from the committed `page_extraction.schema.json`."""
    return json.loads(EXTRACTION_SCHEMA_PATH.read_text(encoding="utf-8"))
