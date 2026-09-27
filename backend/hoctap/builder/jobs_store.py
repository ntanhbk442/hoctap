"""Idempotent job records in `build_jobs`, keyed by (`page_ref`, `stage`, `input_hash`).

The caller owns the transaction: pass a connection from `engine.begin()`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, insert, select, update

from hoctap.builder.models import build_jobs
from hoctap.ids import new_id, to_iso, utc_now


def page_ref(book_id: str, page: int) -> str:
    """`{book_id}#p{page:03d}`, 1-based page."""
    return f"{book_id}#p{page:03d}"


@dataclass(frozen=True)
class Job:
    page_ref: str
    stage: str
    input_hash: str
    status: str
    output: Any
    error: str | None
    updated_at: str


def _job(row: Any) -> Job:
    output = json.loads(row.output_json) if row.output_json is not None else None
    return Job(
        row.page_ref,
        row.stage,
        row.input_hash,
        row.status,
        output,
        row.error,
        row.updated_at,
    )


def get_job(conn: Connection, ref: str, stage: str, input_hash: str) -> Job | None:
    t = build_jobs
    row = conn.execute(
        select(t).where(t.c.page_ref == ref, t.c.stage == stage, t.c.input_hash == input_hash)
    ).first()
    return _job(row) if row is not None else None


def find_done(conn: Connection, ref: str, stage: str, input_hash: str) -> Job | None:
    job = get_job(conn, ref, stage, input_hash)
    return job if job is not None and job.status == "done" else None


def record(
    conn: Connection,
    ref: str,
    stage: str,
    input_hash: str,
    status: str,
    *,
    output: Any = None,
    error: str | None = None,
    run_kind: str = "pilot",
) -> None:
    """Inserts or updates the job row for this key. `run_kind` (pilot | full) is set on
    insert only; the full run (Story 6.2) passes `full`."""
    t = build_jobs
    stamp = to_iso(utc_now())
    values = {
        "status": status,
        "output_json": None if output is None else json.dumps(output, ensure_ascii=False),
        "error": error,
        "updated_at": stamp,
    }
    where = (t.c.page_ref == ref, t.c.stage == stage, t.c.input_hash == input_hash)
    if conn.execute(select(t.c.id).where(*where)).first() is None:
        conn.execute(
            insert(t).values(
                id=new_id(),
                page_ref=ref,
                stage=stage,
                input_hash=input_hash,
                run_kind=run_kind,
                created_at=stamp,
                **values,
            )
        )
    else:
        conn.execute(update(t).where(*where).values(**values))


def latest_done(conn: Connection, stage: str, ref_prefix: str) -> dict[str, Job]:
    """The most recently finished `done` job of `stage` per page_ref starting with the prefix."""
    t = build_jobs
    prefix = t.c.page_ref.startswith(ref_prefix, autoescape=True)
    rows = conn.execute(
        select(t).where(t.c.stage == stage, t.c.status == "done", prefix).order_by(t.c.updated_at)
    ).all()
    return {row.page_ref: _job(row) for row in rows}
