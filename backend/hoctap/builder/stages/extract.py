"""`extract`: one Claude call per page, returning a `PageExtraction`.

The calls, retries, cost records and the total budget cap are `builder.calls.run_calls`;
an output that is not a page extraction is retried once.

`input_hash` = sha256 of the model, prompt version, system prompt, output schema and the
content hashes (sha256 of the image files) of the page and of the next page (the context
image). A library upgrade that renders identical images therefore re-bills nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine

from hoctap.builder import jobs_store
from hoctap.builder.calls import CallJob, CallReport, run_calls
from hoctap.builder.claude_client import ClaudeClient, PageRequest
from hoctap.builder.extraction.models import PageEnvelope, extraction_schema
from hoctap.builder.extraction.prompt import PROMPT_VERSION, SYSTEM_PROMPT, page_prompt
from hoctap.config import Settings

STAGE = "extract"


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class PageTask:
    book_id: str
    page: int
    image: Path
    image_sha: str | None  # None: not rendered yet
    next_image: Path | None
    next_image_sha: str | None

    @property
    def ref(self) -> str:
        return jobs_store.page_ref(self.book_id, self.page)


def extract_input_hash(task: PageTask, settings: Settings) -> str:
    return _sha(
        {
            "model": settings.extraction_model,
            "prompt_version": PROMPT_VERSION,
            "system": _sha(SYSTEM_PROMPT),
            "schema": _sha(extraction_schema()),
            "page": task.image_sha,
            "next_page": task.next_image_sha,
        }
    )


def build_request(task: PageTask, settings: Settings) -> PageRequest:
    return PageRequest(
        page_ref=task.ref,
        prompt=page_prompt(
            task.page, task.image.resolve(), task.next_image and task.next_image.resolve()
        ),
        system_prompt=SYSTEM_PROMPT,
        schema=extraction_schema(),
        model=settings.extraction_model,
        add_dir=task.image.parent.resolve(),
        max_budget_usd=settings.extraction_max_budget_usd,
        timeout_seconds=settings.extraction_timeout_seconds,
    )


def _check_output(output: dict[str, Any] | None) -> str | None:
    """Why the output is not a usable page, or None. Drafts are checked in validate."""
    try:
        PageEnvelope.model_validate(output)
    except ValidationError as exc:
        return f"output is not a page extraction: {exc}"
    return None


ExtractReport = CallReport


def run_extract(
    engine: Engine,
    client: ClaudeClient,
    tasks: list[tuple[PageTask, str]],
    settings: Settings,
    on_page: Callable[[str, str], None] = lambda ref, status: None,
    max_total_usd: float | None = None,
) -> ExtractReport:
    """Calls Claude for each (task, input_hash) and records the job and its costs
    (see `builder.calls.run_calls`)."""
    jobs = [
        CallJob(task.ref, STAGE, input_hash, build_request(task, settings), _check_output)
        for task, input_hash in tasks
    ]
    return run_calls(engine, client, jobs, settings, on_page, max_total_usd)
