"""Printable worksheets (Story 7.1, FR-22): `GET /api/v1/parent/worksheet`.

Parent-only (PIN cookie): the response carries every Part's Answer Key, Hint and Solution,
so it must never be reachable from a child route. The set is whatever
`learning.problem_sets.resolve()` says (the same list a Session would freeze); the content is
the effective doc, so hidden, retired, reported or unapproved Problems are already excluded.
An Assignment is a Lesson ref, so it prints as its Lesson.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, Engine, select

from hoctap.api.deps import get_engine, get_settings
from hoctap.api.errors import AppError, ErrorResponse
from hoctap.config import Settings
from hoctap.content import effective
from hoctap.content.assets import crop_url
from hoctap.content.catalog.models import (
    content_catalog_books,
    content_catalog_lessons,
    content_catalog_units,
)
from hoctap.content.review.models import content_review_concepts
from hoctap.content.schema import ProblemDoc
from hoctap.learning.problem_sets import ConceptRef, LessonRef, ProblemSetRef, resolve
from hoctap.parent.auth import require_parent
from hoctap.parent.models import parent_profiles

router = APIRouter(
    prefix="/parent",
    tags=["worksheets"],
    dependencies=[Depends(require_parent)],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in"},
        403: {"model": ErrorResponse, "description": "Setup required"},
    },
)


class WorksheetProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: str
    doc: ProblemDoc  # the effective doc, with Answer Keys: for the parent's answer page only
    crop_url: str | None  # the whole-Problem crop; None when the file is missing
    image_urls: dict[str, str]  # image_key -> crop URL, only for crops that exist


class WorksheetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["lesson", "concept"]
    title: str
    subtitle: str
    problems: list[WorksheetProblem]


def _crop_exists(crops: Path, book_id: str, problem_id: str, name: str) -> bool:
    return (crops / book_id / problem_id / f"{name}.jpg").is_file()


def _title(conn: Connection, ref: ProblemSetRef) -> tuple[str, str]:
    if isinstance(ref, ConceptRef):
        name = conn.execute(
            select(content_review_concepts.c.name_vi).where(
                content_review_concepts.c.concept_id == ref.concept_id
            )
        ).scalar_one_or_none()
        return name or ref.concept_id, "Luyện theo khái niệm"
    assert isinstance(ref, LessonRef)
    book = conn.execute(
        select(content_catalog_books.c.title_vi).where(
            content_catalog_books.c.book_id == ref.book_id
        )
    ).scalar_one_or_none()
    unit = conn.execute(
        select(content_catalog_units.c.label, content_catalog_units.c.title).where(
            content_catalog_units.c.book_id == ref.book_id,
            content_catalog_units.c.unit_key == ref.unit_key,
        )
    ).one_or_none()
    lesson = conn.execute(
        select(content_catalog_lessons.c.label, content_catalog_lessons.c.title).where(
            content_catalog_lessons.c.book_id == ref.book_id,
            content_catalog_lessons.c.unit_key == ref.unit_key,
            content_catalog_lessons.c.lesson_key == ref.lesson_key,
        )
    ).one_or_none()
    parts = [f"{r.label} {r.title}".strip() for r in (unit, lesson) if r is not None]
    return " · ".join(p for p in parts if p) or ref.lesson_key, book or ref.book_id


@router.get(
    "/worksheet",
    response_model=WorksheetOut,
    operation_id="get_worksheet",
    responses={
        404: {"model": ErrorResponse, "description": "PROFILE_NOT_FOUND or CONCEPT_NOT_FOUND"},
        422: {"model": ErrorResponse, "description": "WORKSHEET_REF_INVALID"},
    },
)
def get_worksheet(
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings)],
    book_id: str | None = None,
    unit_key: str | None = None,
    lesson_key: str | None = None,
    concept_id: str | None = None,
    profile_id: str | None = None,
) -> WorksheetOut:
    """A Lesson (`book_id`+`unit_key`+`lesson_key`) or a Concept (`concept_id`+`profile_id`)
    Problem Set, in `resolve()` order, with Answer Keys."""
    ref: ProblemSetRef
    lesson_given = (book_id, unit_key, lesson_key)
    if concept_id is not None and not any(lesson_given):
        if not profile_id:
            raise AppError(422, "WORKSHEET_REF_INVALID", "Cần chọn bé để in phiếu theo khái niệm.")
        ref = ConceptRef(concept_id)
    elif concept_id is None and all(lesson_given):
        assert book_id and unit_key and lesson_key
        ref = LessonRef(book_id, unit_key, lesson_key)
    else:
        raise AppError(
            422, "WORKSHEET_REF_INVALID", "Chọn một tiết học hoặc một khái niệm để in phiếu."
        )
    crops = settings.data_dir / "assets" / "crops"
    with engine.connect() as conn:
        if profile_id is not None:
            found = conn.execute(
                select(parent_profiles.c.id).where(parent_profiles.c.id == profile_id)
            ).scalar_one_or_none()
            if found is None:
                raise AppError(404, "PROFILE_NOT_FOUND", "Không tìm thấy hồ sơ.")
        ids = resolve(conn, ref, profile_id or "")
        states = {s.problem_id: s for s in effective.load_effective(conn, ids)}
        problems: list[WorksheetProblem] = []
        for pid in ids:
            state = states.get(pid)
            if state is None or not state.visible or state.doc is None:
                continue
            doc = state.doc
            problems.append(
                WorksheetProblem(
                    problem_id=pid,
                    doc=doc,
                    crop_url=(
                        crop_url(doc.book_id, pid, "_problem")
                        if _crop_exists(crops, doc.book_id, pid, "_problem")
                        else None
                    ),
                    image_urls={
                        i.image_key: crop_url(doc.book_id, pid, i.image_key)
                        for i in doc.images
                        if _crop_exists(crops, doc.book_id, pid, i.image_key)
                    },
                )
            )
        title, subtitle = _title(conn, ref)
    return WorksheetOut(kind=ref.kind, title=title, subtitle=subtitle, problems=problems)
