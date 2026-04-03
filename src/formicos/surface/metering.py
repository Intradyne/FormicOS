"""Wave 75 Track 1: Metering — event-store-backed billing aggregate.

Single source of truth for token aggregation and fee computation.
Reads ``TokensConsumed`` events directly from the event store,
NOT from ``BudgetSnapshot`` projections (which exclude reasoning tokens).

See ``METERING.md`` for the normative specification.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.adapters.store_sqlite import SqliteEventStore

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Fee formula — single source of truth
# ---------------------------------------------------------------------------

_FEE_COEFFICIENT = 2.00
_FEE_DIVISOR = 1_000_000


def compute_fee(total_tokens: int) -> float:
    """Compute the commercial license fee from total tokens.

    Formula (from LICENSE):
        round(2.00 * sqrt(total_tokens / 1_000_000), 2)
    """
    if total_tokens <= 0:
        return 0.0
    return round(_FEE_COEFFICIENT * math.sqrt(total_tokens / _FEE_DIVISOR), 2)


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


def current_period() -> tuple[datetime, datetime]:
    """Return (start, end) for the current calendar month in UTC."""
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # End is first instant of next month
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


def parse_period(period_str: str) -> tuple[datetime, datetime]:
    """Parse 'YYYY-MM' into (start, end) datetimes."""
    parts = period_str.split("-")
    year, month = int(parts[0]), int(parts[1])
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


# ---------------------------------------------------------------------------
# Aggregation — reads event store, not projections
# ---------------------------------------------------------------------------


async def aggregate_period(
    event_store: SqliteEventStore,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, Any]:
    """Aggregate TokensConsumed events for a billing period.

    Pages through the event store and filters by timestamp in Python
    (the SQLite query seam does not support date filtering).

    Returns a dict with: input_tokens, output_tokens, reasoning_tokens,
    cache_read_tokens, total_tokens, event_count, first_event_seq,
    last_event_seq, by_model, total_cost, computed_fee.
    """
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    cache_read_tokens = 0
    total_cost = 0.0
    event_count = 0
    first_seq: int | None = None
    last_seq: int | None = None
    by_model: dict[str, dict[str, int | float]] = {}

    # Collect raw events for chain hash
    raw_events: list[dict[str, Any]] = []

    after_seq = 0
    while True:
        batch = await event_store.query(
            event_type="TokensConsumed",
            after_seq=after_seq,
            limit=1000,
        )
        if not batch:
            break

        for evt in batch:
            after_seq = evt.seq

            # Parse timestamp — events use ISO format
            ts = _parse_event_ts(evt.timestamp)
            if ts is None:
                continue
            if ts < period_start or ts >= period_end:
                continue

            inp = getattr(evt, "input_tokens", 0)
            out = getattr(evt, "output_tokens", 0)
            reas = getattr(evt, "reasoning_tokens", 0)
            cache = getattr(evt, "cache_read_tokens", 0)
            cost = getattr(evt, "cost", 0.0)
            model = getattr(evt, "model", "unknown")

            input_tokens += inp
            output_tokens += out
            reasoning_tokens += reas
            cache_read_tokens += cache
            total_cost += cost
            event_count += 1

            if first_seq is None:
                first_seq = evt.seq
            last_seq = evt.seq

            # By-model breakdown
            if model not in by_model:
                by_model[model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "cache_read_tokens": 0,
                    "cost": 0.0,
                }
            entry = by_model[model]
            entry["input_tokens"] = int(entry["input_tokens"]) + inp
            entry["output_tokens"] = int(entry["output_tokens"]) + out
            entry["reasoning_tokens"] = int(entry["reasoning_tokens"]) + reas
            entry["cache_read_tokens"] = int(entry["cache_read_tokens"]) + cache
            entry["cost"] = float(entry["cost"]) + cost

            # Collect for chain hash
            raw_events.append({
                "seq": evt.seq,
                "input_tokens": inp,
                "output_tokens": out,
                "reasoning_tokens": reas,
                "cache_read_tokens": cache,
                "cost": cost,
                "model": model,
                "agent_id": getattr(evt, "agent_id", ""),
            })

        if len(batch) < 1000:
            break

    total_tokens = input_tokens + output_tokens + reasoning_tokens
    chain_hash = compute_chain_hash(raw_events) if raw_events else ""

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cache_read_tokens": cache_read_tokens,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "event_count": event_count,
        "first_event_seq": first_seq,
        "last_event_seq": last_seq,
        "by_model": by_model,
        "chain_hash": chain_hash,
        "computed_fee": compute_fee(total_tokens),
    }


# ---------------------------------------------------------------------------
# Chain hash — deterministic integrity check
# ---------------------------------------------------------------------------


def compute_chain_hash(events: list[dict[str, Any]]) -> str:
    """Compute SHA-256 chain hash over event payloads in seq order.

    Matches the specification in METERING.md.
    """
    h = hashlib.sha256()
    for event in sorted(events, key=lambda e: e.get("seq", 0)):
        payload = json.dumps(
            event, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        h.update(payload)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Attestation generation
# ---------------------------------------------------------------------------

_ATTESTATION_DIR = "billing/attestations"


async def generate_attestation(
    event_store: SqliteEventStore,
    period_start: datetime,
    period_end: datetime,
    license_id: str,
    data_dir: str,
) -> dict[str, Any]:
    """Generate an unsigned v1 attestation for a billing period.

    Saves to ``.formicos/billing/attestations/YYYY-MM.json``.
    Returns the attestation dict.
    """
    agg = await aggregate_period(event_store, period_start, period_end)

    attestation: dict[str, Any] = {
        "version": 1,
        "license_id": license_id,
        "period_start": agg["period_start"],
        "period_end": agg["period_end"],
        "total_tokens": agg["total_tokens"],
        "breakdown": {
            "input_tokens": agg["input_tokens"],
            "output_tokens": agg["output_tokens"],
            "reasoning_tokens": agg["reasoning_tokens"],
            "cache_read_tokens": agg["cache_read_tokens"],
        },
        "by_model": agg["by_model"],
        "event_count": agg["event_count"],
        "first_event_seq": agg["first_event_seq"],
        "last_event_seq": agg["last_event_seq"],
        "chain_hash": agg["chain_hash"],
        "computed_fee_usd": agg["computed_fee"],
        "signature": "unsigned",
    }

    # Save to disk
    out_dir = Path(data_dir) / ".formicos" / _ATTESTATION_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    period_label = period_start.strftime("%Y-%m")
    out_path = out_dir / f"{period_label}.json"
    out_path.write_text(
        json.dumps(attestation, indent=2) + "\n", encoding="utf-8",
    )

    log.info(
        "metering.attestation_generated",
        period=period_label,
        total_tokens=agg["total_tokens"],
        fee=agg["computed_fee"],
        path=str(out_path),
    )

    return attestation


def load_attestation_history(data_dir: str) -> list[dict[str, Any]]:
    """Load all saved attestation files, sorted by period."""
    att_dir = Path(data_dir) / ".formicos" / _ATTESTATION_DIR
    if not att_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(att_dir.glob("*.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return results


# ---------------------------------------------------------------------------
# Formatting helpers (for CLI and MCP rendering)
# ---------------------------------------------------------------------------


def format_billing_status(agg: dict[str, Any]) -> str:
    """Render billing aggregate as readable CLI/MCP output."""
    lines = [
        "FormicOS Billing Status",
        "=" * 40,
        f"Period:            {agg['period_start'][:10]} to {agg['period_end'][:10]}",
        "",
        "Token Breakdown:",
        f"  Input tokens:    {agg['input_tokens']:>14,}",
        f"  Output tokens:   {agg['output_tokens']:>14,}",
        f"  Reasoning tokens:{agg['reasoning_tokens']:>14,}",
        f"  Cache-read:      {agg['cache_read_tokens']:>14,}  (informational, subset of input)",
        f"  {'-' * 32}",
        f"  Total tokens:    {agg['total_tokens']:>14,}",
        "",
        f"Events:            {agg['event_count']:>14,}",
        f"API cost (USD):    ${agg['total_cost']:>13,.4f}",
        f"Computed fee:      ${agg['computed_fee']:>13,.2f}",
        "",
    ]

    # By-model
    if agg.get("by_model"):
        lines.append("By Model:")
        for model, stats in sorted(agg["by_model"].items()):
            total = (
                int(stats.get("input_tokens", 0))
                + int(stats.get("output_tokens", 0))
                + int(stats.get("reasoning_tokens", 0))
            )
            lines.append(f"  {model:<30} {total:>12,} tokens  ${float(stats.get('cost', 0)):.4f}")
        lines.append("")

    # Free tier note
    lines.append("Note: Tier 1 (free) applies under 10M total tokens/month.")
    lines.append("      Tier status depends on revenue, not token count alone.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_event_ts(ts: Any) -> datetime | None:
    """Parse event timestamp to a timezone-aware datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return None
    return None
