"""Token-to-cost conversion, the pre-flight estimate and the recorded cost totals.

Each call's real cost is the Claude CLI's own `total_cost_usd`; `cost_usd()` prices a
token count from config and is used for the estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, func, insert, select

from hoctap.builder.claude_client import CallResult, Usage
from hoctap.builder.models import build_costs
from hoctap.config import Settings
from hoctap.ids import new_id, to_iso, utc_now

MAX_ATTEMPTS = 2  # one retry on a transient failure

# Prompt-cache multipliers of the input price (5-minute writes, reads).
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


def cost_usd(usage: Usage, settings: Settings) -> float:
    """USD cost of a token count at the configured standard prices."""
    price_in = settings.price_input_per_mtok
    total = (
        usage.input_tokens * price_in
        + usage.cache_creation_input_tokens * price_in * CACHE_WRITE_MULTIPLIER
        + usage.cache_read_input_tokens * price_in * CACHE_READ_MULTIPLIER
        + usage.output_tokens * settings.price_output_per_mtok
    ) / 1_000_000
    return round(total, 6)


@dataclass(frozen=True)
class Estimate:
    pages: int
    input_tokens: int
    output_tokens: int
    usd: float
    worst_case_usd: float  # every call at its cap, every call retried once

    def describe(self, model: str) -> str:
        return (
            f"Ước tính / Estimate: {self.pages} trang / page(s) to {model}, "
            f"~{self.input_tokens:,} input + ~{self.output_tokens:,} output tokens, "
            f"~${self.usd:.2f} (fixed per-page estimate). Tối đa / Worst case: "
            f"${self.worst_case_usd:.2f} (per-call cap; a retry can double a page's cost)"
        )


def estimate(pages: int, settings: Settings) -> Estimate:
    """The fixed per-page pre-flight estimate (no call is made)."""
    usage = Usage(
        input_tokens=pages * settings.estimate_input_tokens_per_page,
        output_tokens=pages * settings.estimate_output_tokens_per_page,
    )
    worst = pages * settings.extraction_max_budget_usd * MAX_ATTEMPTS
    return Estimate(
        pages, usage.input_tokens, usage.output_tokens, cost_usd(usage, settings), round(worst, 2)
    )


def record_call(
    conn: Connection,
    *,
    page_ref: str,
    stage: str,
    input_hash: str,
    attempt: int,
    model: str,
    result: CallResult,
) -> None:
    u = result.usage
    conn.execute(
        insert(build_costs).values(
            id=new_id(),
            page_ref=page_ref,
            stage=stage,
            input_hash=input_hash,
            attempt=attempt,
            model=model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_creation_input_tokens=u.cache_creation_input_tokens,
            cache_read_input_tokens=u.cache_read_input_tokens,
            cost_usd=result.cost_usd,
            cost_unknown=int(result.cost_unknown),
            created_at=to_iso(utc_now()),
        )
    )


def total_cost(conn: Connection, ref_prefix: str = "") -> float:
    """The recorded USD cost of all calls whose page_ref starts with the prefix."""
    t = build_costs
    query = select(func.coalesce(func.sum(t.c.cost_usd), 0.0))
    if ref_prefix:
        query = query.where(t.c.page_ref.startswith(ref_prefix, autoescape=True))
    return float(conn.execute(query).scalar_one())
