"""Request and response models of the Content Review API (`/api/v1/parent/review/*`)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from hoctap.content.schema import ProblemDoc

OverrideField = Literal[
    "instruction", "display_label", "prompt", "answer", "hint", "solution", "part"
]


class ProblemSummary(BaseModel):
    problem_id: str
    book_id: str
    unit_key: str
    lesson_key: str
    position: int
    display_label: str
    instruction: str
    # Badges: cần duyệt, xung đột, báo lỗi, đã ẩn, trùng.
    awaiting_approval: bool = Field(
        description="needs_review and not approved for the current effective hash"
    )
    conflict: bool
    report: bool = Field(description="has an open Error Report")
    hidden: bool
    duplicate: bool
    approved: bool
    visible: bool = Field(description="visible to the child")
    retired: bool


class ProblemPage(BaseModel):
    items: list[ProblemSummary]
    total: int
    page: int
    page_size: int


class ReviewLesson(BaseModel):
    lesson_key: str
    label: str


class ReviewUnit(BaseModel):
    unit_key: str
    label: str
    lessons: list[ReviewLesson]


class ReviewBook(BaseModel):
    book_id: str
    title_vi: str
    problem_count: int
    units: list[ReviewUnit]


class OverrideOut(BaseModel):
    id: str
    part_key: str | None = Field(description="null for the top level")
    field: OverrideField
    value: JsonValue
    base_hash: str
    conflict: Literal["base_changed", "part_missing"] | None


class ConflictOut(BaseModel):
    override_id: str
    part_key: str | None
    field: OverrideField
    reason: Literal["base_changed", "part_missing"]


class ReportOut(BaseModel):
    id: str
    problem_id: str
    kind: Literal["parent", "child"]
    note: str
    status: Literal["open", "resolved"]
    created_at: str
    resolved_at: str | None


class ReviewStatusOut(BaseModel):
    needs_review: bool = Field(description="the extracted flag (answers disagreed)")
    verify_status: str
    approved_hash: str | None
    approved: bool = Field(description="approved for the current effective hash")
    hidden: bool
    duplicate: bool
    retired: bool
    visible: bool


class ProblemDetail(BaseModel):
    summary: ProblemSummary
    extracted: dict[str, Any]
    effective: ProblemDoc | None
    effective_error: list[str] = Field(
        description="validation messages when the merged doc is invalid; else empty"
    )
    content_hash: str | None
    overrides: list[OverrideOut]
    conflicts: list[ConflictOut]
    status: ReviewStatusOut
    reports: list[ReportOut]
    crop_urls: list[str]
    page_urls: list[str]


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_key: str | None = Field(default=None, description="null or omitted: the top level")
    field: OverrideField
    value: JsonValue


class OverridesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: list[EditIn] = Field(min_length=1)


class ProposalOut(BaseModel):
    proposal_key: str
    grade: int
    text: str
    problem_count: int
    status: Literal["proposed", "accepted", "merged"]
    target_concept_id: str | None


class ConceptOut(BaseModel):
    concept_id: str
    grade: int
    name_vi: str
    problem_count: int


class ConceptsOut(BaseModel):
    proposals: list[ProposalOut]
    concepts: list[ConceptOut]


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(description="the effective hash the parent reviewed")


class AcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: int = Field(ge=1, le=5)
    proposal_key: str


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: int = Field(ge=1, le=5)
    proposal_key: str
    concept_id: str


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    name_vi: str = Field(min_length=1, max_length=120)


class SpotCheckItem(BaseModel):
    problem_id: str
    position: int
    problem_type: str = Field(description="the type of the first Part")
    display_label: str
    verdict: Literal["correct", "wrong"] | None
    note: str
    checked_at: str | None
    verdict_hash: str | None = Field(description="the effective hash the verdict was given for")
    first_wrong_at: str | None = Field(
        description="set by the first Sai; the item then counts as wrong for good"
    )
    counted: Literal["correct", "wrong"] | None = Field(
        description="how the item counts toward key_accuracy; null: not counted"
    )
    content_hash: str | None = Field(description="the current effective hash")
    stale: bool = Field(
        description="a Đúng for an older hash (never judged wrong): cần kiểm tra lại"
    )
    retired: bool


class SpotCheckOut(BaseModel):
    sample_id: str | None = Field(description="null before the first sample is drawn")
    seed: int | None
    created_at: str | None
    size: int
    correct: int = Field(description="Đúng verdicts for the current hash, never judged wrong")
    wrong: int = Field(description="items ever judged Sai (counted wrong for good)")
    stale: int
    checked: int = Field(description="correct + wrong: the verdicts that count")
    items: list[SpotCheckItem]


class VerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["correct", "wrong"]
    note: str = Field(default="", max_length=500)
    content_hash: str = Field(description="the effective hash the parent checked")
