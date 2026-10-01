"""Content Review (`/api/v1/parent/review/*`), behind the parent session."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine

from hoctap.api.deps import get_engine, get_now, get_settings
from hoctap.api.errors import ErrorResponse
from hoctap.builder import gate
from hoctap.config import Settings
from hoctap.content.review import service, spotcheck
from hoctap.content.review.schemas import (
    AcceptIn,
    ApproveIn,
    ConceptsOut,
    GuideDetail,
    GuideOverridesIn,
    MergeIn,
    OverridesIn,
    ProblemDetail,
    ProblemPage,
    ProblemSummary,
    RenameIn,
    ReportIn,
    ReportOut,
    ReviewBook,
    SpotCheckOut,
    VerdictIn,
)
from hoctap.parent.auth import require_parent

router = APIRouter(
    prefix="/parent/review",
    tags=["review"],
    dependencies=[Depends(require_parent)],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in"},
        403: {"model": ErrorResponse, "description": "Setup required"},
    },
)

EngineDep = Annotated[Engine, Depends(get_engine)]
NowDep = Annotated[datetime, Depends(get_now)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/queue", response_model=list[ProblemSummary], operation_id="get_review_queue")
def get_queue(engine: EngineDep) -> list[ProblemSummary]:
    with engine.connect() as conn:
        return [service.summary(s) for s in service.review_queue(conn)]


@router.get("/books", response_model=list[ReviewBook], operation_id="list_review_books")
def list_books(engine: EngineDep) -> list[ReviewBook]:
    with engine.connect() as conn:
        return service.list_review_books(conn)


@router.get("/problems", response_model=ProblemPage, operation_id="list_review_problems")
def list_problems(
    engine: EngineDep,
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
    no_concepts: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
) -> ProblemPage:
    with engine.connect() as conn:
        return service.list_problems(
            conn,
            book_id=book_id,
            unit_key=unit_key,
            lesson_key=lesson_key,
            no_concepts=no_concepts,
            page=page,
        )


@router.get(
    "/problems/{problem_id}", response_model=ProblemDetail, operation_id="get_review_problem"
)
def get_problem(problem_id: str, engine: EngineDep) -> ProblemDetail:
    with engine.connect() as conn:
        return service.problem_detail(conn, problem_id)


@router.put(
    "/problems/{problem_id}/overrides",
    response_model=ProblemDetail,
    operation_id="save_review_overrides",
)
def save_overrides(
    problem_id: str, body: OverridesIn, engine: EngineDep, now: NowDep
) -> ProblemDetail:
    edits = [service.Edit(e.field, e.value, e.part_key) for e in body.edits]
    with engine.begin() as conn:
        service.save_overrides(conn, problem_id, edits, now, expected_hash=body.expected_hash)
        return service.problem_detail(conn, problem_id)


@router.delete(
    "/problems/{problem_id}/overrides",
    response_model=ProblemDetail,
    operation_id="delete_all_review_overrides",
)
def delete_all_overrides(problem_id: str, engine: EngineDep) -> ProblemDetail:
    with engine.begin() as conn:
        service.delete_all_overrides(conn, problem_id)
        return service.problem_detail(conn, problem_id)


@router.delete(
    "/problems/{problem_id}/overrides/{override_id}",
    response_model=ProblemDetail,
    operation_id="delete_review_override",
)
def delete_override(problem_id: str, override_id: str, engine: EngineDep) -> ProblemDetail:
    with engine.begin() as conn:
        service.delete_override(conn, problem_id, override_id)
        return service.problem_detail(conn, problem_id)


@router.post(
    "/problems/{problem_id}/approve",
    response_model=ProblemDetail,
    operation_id="approve_review_problem",
)
def approve(problem_id: str, body: ApproveIn, engine: EngineDep, now: NowDep) -> ProblemDetail:
    with engine.begin() as conn:
        service.approve(conn, problem_id, body.content_hash, now)
        return service.problem_detail(conn, problem_id)


@router.post(
    "/problems/{problem_id}/hide", response_model=ProblemDetail, operation_id="hide_review_problem"
)
def hide(problem_id: str, engine: EngineDep, now: NowDep) -> ProblemDetail:
    with engine.begin() as conn:
        service.set_hidden(conn, problem_id, True, now)
        return service.problem_detail(conn, problem_id)


@router.post(
    "/problems/{problem_id}/unhide",
    response_model=ProblemDetail,
    operation_id="unhide_review_problem",
)
def unhide(problem_id: str, engine: EngineDep, now: NowDep) -> ProblemDetail:
    with engine.begin() as conn:
        service.set_hidden(conn, problem_id, False, now)
        return service.problem_detail(conn, problem_id)


@router.post(
    "/problems/{problem_id}/reports",
    response_model=ReportOut,
    operation_id="report_review_problem",
    responses={404: {"model": ErrorResponse, "description": "PROBLEM_NOT_FOUND"}},
)
def report_problem(problem_id: str, body: ReportIn, engine: EngineDep, now: NowDep) -> ReportOut:
    """Báo lỗi (parent): an open `parent` report hides the Problem from the child."""
    with engine.begin() as conn:
        report_id = service.add_error_report(conn, problem_id, "parent", body.note, now)
        return service.report_out(conn, report_id)


@router.post(
    "/reports/{report_id}/resolve", response_model=ReportOut, operation_id="resolve_review_report"
)
def resolve_report(report_id: str, engine: EngineDep, now: NowDep) -> ReportOut:
    with engine.begin() as conn:
        service.resolve_report(conn, report_id, now)
        return service.report_out(conn, report_id)


@router.get("/concepts", response_model=ConceptsOut, operation_id="list_review_concepts")
def list_concepts(engine: EngineDep) -> ConceptsOut:
    with engine.connect() as conn:
        return service.concepts_out(conn)


@router.post("/concepts/accept", response_model=ConceptsOut, operation_id="accept_concept_proposal")
def accept(body: AcceptIn, engine: EngineDep, now: NowDep) -> ConceptsOut:
    with engine.begin() as conn:
        service.accept_proposal(conn, body.grade, body.proposal_key, now)
        return service.concepts_out(conn)


@router.post("/concepts/merge", response_model=ConceptsOut, operation_id="merge_concept_proposal")
def merge(body: MergeIn, engine: EngineDep) -> ConceptsOut:
    with engine.begin() as conn:
        service.merge_proposal(conn, body.grade, body.proposal_key, body.concept_id)
        return service.concepts_out(conn)


@router.post("/concepts/rename", response_model=ConceptsOut, operation_id="rename_concept")
def rename(body: RenameIn, engine: EngineDep) -> ConceptsOut:
    with engine.begin() as conn:
        service.rename_concept(conn, body.concept_id, body.name_vi)
        return service.concepts_out(conn)


_GUIDE_404 = {404: {"model": ErrorResponse, "description": "CONCEPT_NOT_FOUND or GUIDE_NOT_FOUND"}}


@router.get(
    "/concepts/{concept_id}/guide",
    response_model=GuideDetail,
    operation_id="get_concept_guide",
    responses=_GUIDE_404,
)
def get_guide(concept_id: str, engine: EngineDep) -> GuideDetail:
    with engine.connect() as conn:
        return service.guide_detail(conn, concept_id)


@router.put(
    "/concepts/{concept_id}/guide",
    response_model=GuideDetail,
    operation_id="save_concept_guide",
    responses=_GUIDE_404,
)
def save_guide(
    concept_id: str, body: GuideOverridesIn, engine: EngineDep, now: NowDep
) -> GuideDetail:
    edits = [service.Edit(e.field, e.value) for e in body.edits]
    with engine.begin() as conn:
        service.save_guide_overrides(conn, concept_id, edits, now)
        return service.guide_detail(conn, concept_id)


@router.delete(
    "/concepts/{concept_id}/guide",
    response_model=GuideDetail,
    operation_id="reset_concept_guide",
    responses=_GUIDE_404,
)
def reset_guide(
    concept_id: str, engine: EngineDep, field: Literal["explanation", "example"] | None = None
) -> GuideDetail:
    """Bỏ sửa: removes the override of one field (or all); back to the generated text."""
    with engine.begin() as conn:
        service.delete_guide_override(conn, concept_id, field)
        return service.guide_detail(conn, concept_id)


@router.post(
    "/concepts/{concept_id}/guide/approve",
    response_model=GuideDetail,
    operation_id="approve_concept_guide",
    responses=_GUIDE_404,
)
def approve_guide(concept_id: str, body: ApproveIn, engine: EngineDep, now: NowDep) -> GuideDetail:
    with engine.begin() as conn:
        service.approve_guide(conn, concept_id, body.content_hash, now)
        return service.guide_detail(conn, concept_id)


@router.get("/spot-check", response_model=SpotCheckOut, operation_id="get_spot_check")
def get_spot_check(engine: EngineDep) -> SpotCheckOut:
    with engine.connect() as conn:
        return spotcheck.spot_check_out(conn)


@router.post("/spot-check/draw", response_model=SpotCheckOut, operation_id="draw_spot_check")
def draw_spot_check(engine: EngineDep, settings: SettingsDep, now: NowDep) -> SpotCheckOut:
    """Rút mẫu mới: a new sample of the pilot Problems; the old one is kept."""
    with engine.begin() as conn:
        gate.draw_sample(conn, settings, now=now)
        return spotcheck.spot_check_out(conn)


@router.put(
    "/spot-check/{sample_id}/items/{problem_id}",
    response_model=SpotCheckOut,
    operation_id="set_spot_check_verdict",
)
def set_verdict(
    sample_id: str, problem_id: str, body: VerdictIn, engine: EngineDep, now: NowDep
) -> SpotCheckOut:
    with engine.begin() as conn:
        spotcheck.set_verdict(
            conn, sample_id, problem_id, body.verdict, body.content_hash, body.note, now
        )
        return spotcheck.spot_check_out(conn)
