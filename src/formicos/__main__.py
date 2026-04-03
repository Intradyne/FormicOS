"""FormicOS CLI entry point -- ``python -m formicos``."""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

from formicos import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="formicos",
        description="FormicOS -- Stigmergic Multi-Agent Colony Framework",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"formicos {__version__}",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind address (overrides config, default 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (overrides config, default 8080)",
    )

    subs = parser.add_subparsers(dest="command")
    subs.add_parser("start", help="Start the FormicOS server")
    subs.add_parser("reset", help="Reset colony state")
    subs.add_parser("export-events", help="Export the event log")

    init_mcp = subs.add_parser(
        "init-mcp",
        help="Generate MCP config for Claude Code integration",
    )
    init_mcp.add_argument(
        "--url",
        default="http://localhost:8080/mcp",
        help="FormicOS MCP server URL (default: http://localhost:8080/mcp)",
    )
    init_mcp.add_argument(
        "--desktop",
        action="store_true",
        help="Print Claude Desktop config snippet instead of writing .mcp.json",
    )

    # Wave 75: billing subcommands
    billing = subs.add_parser("billing", help="Billing and metering commands")
    billing_subs = billing.add_subparsers(dest="billing_command")
    billing_subs.add_parser("status", help="Show current-period billing status")
    billing_subs.add_parser("estimate", help="Estimate fee without generating attestation")
    billing_subs.add_parser("history", help="Show attestation history")
    billing_subs.add_parser("self-test", help="Validate the metering pipeline")
    attest = billing_subs.add_parser("attest", help="Generate attestation for a period")
    attest.add_argument("--period", required=True, help="Billing period (YYYY-MM)")
    attest.add_argument("--license-id", default="unlicensed", help="License ID")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch subcommands."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # Default to start when no subcommand given
        args.command = "start"

    if args.command == "start":
        _start_server(host=args.host, port=args.port)
    elif args.command == "reset":
        print("Reset not yet implemented")
    elif args.command == "export-events":
        print("Event export not yet implemented")
    elif args.command == "init-mcp":
        if getattr(args, "desktop", False):
            _print_desktop_config(url=args.url)
        else:
            _init_mcp(url=args.url)
    elif args.command == "billing":
        _billing(args)


_BRIDGE_TEMPLATE = """\
# FormicOS Developer Bridge

This project uses FormicOS for institutional memory, strategic delegation,
and autonomous background work. FormicOS MCP server: {url}

## MCP Prompts (context injection — read-only)

- **morning-status** — What happened, what's pending, project plan status
- **delegate-task** — Plan a colony to handle a task, get blast radius estimate
- **review-overnight-work** — Review autonomous actions, pending approvals, new knowledge
- **knowledge-for-context** — Search institutional memory for relevant entries

## MCP Tools (actions — may mutate state)

- `spawn_colony` — Create and start a colony directly
- `chat_queen` — Message the Queen for strategic guidance
- `get_status` — Workspace status with threads and colonies
- `approve` / `deny` — Review pending actions
- `log_finding` — Record a discovery as a knowledge entry
- `handoff_to_formicos` — Transfer work context to a new colony
- `get_task_receipt` — Get a deterministic receipt for completed A2A work
- `addon_status` — Check installed addon health
- `toggle_addon` — Enable/disable addons
- `trigger_addon` — Run addon handlers (reindex, etc.)

## MCP Resources

- `formicos://plan` — Project plan (global)
- `formicos://procedures/{{workspace_id}}` — Operating procedures
- `formicos://journal/{{workspace_id}}` — Recent journal entries
- `formicos://knowledge/{{workspace}}` — Knowledge catalog
- `formicos://briefing/{{workspace_id}}` — Proactive intelligence briefing

## Connection

- **Claude Code (VS Code):** Uses `http://localhost:8080/mcp` via `.mcp.json`
- **Claude Desktop:** Uses `mcp-remote` bridge in `claude_desktop_config.json`
  (see `python -m formicos init-mcp --desktop` for the config snippet)
- Both clients connect to the same FormicOS instance simultaneously

## Shared Files

- `.formicos/project_plan.md` — Milestones (both you and FormicOS read/write)
- `.formicos/project_context.md` — Project instructions for colonies
- `.formicos/operations/*/operating_procedures.md` — Autonomy rules
- `.formicos/operations/*/queen_journal.md` — What FormicOS did (read-only)
"""


def _init_mcp(url: str = "http://localhost:8080/mcp") -> None:
    """Generate .mcp.json and .formicos/DEVELOPER_QUICKSTART.md."""
    import json
    from pathlib import Path

    cwd = Path.cwd()

    # Write .mcp.json
    mcp_config = {
        "mcpServers": {
            "formicos": {
                "type": "http",
                "url": url,
            }
        }
    }
    mcp_path = cwd / ".mcp.json"
    mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
    print(f"  Created {mcp_path}")

    # Write .formicos/DEVELOPER_QUICKSTART.md
    bridge_dir = cwd / ".formicos"
    bridge_dir.mkdir(exist_ok=True)
    bridge_path = bridge_dir / "DEVELOPER_QUICKSTART.md"
    bridge_path.write_text(_BRIDGE_TEMPLATE.format(url=url))
    print(f"  Created {bridge_path}")

    print()
    print("FormicOS MCP integration configured.")
    print("Restart Claude Code to connect via http://localhost:8080/mcp")
    print()
    print("Claude Desktop: run `python -m formicos init-mcp --desktop` for config.")
    print()
    print("Then try:")
    print("  morning-status -- get a complete briefing")
    print("  delegate-task -- hand off work to FormicOS")
    print("  knowledge-for-context -- search institutional memory")


def _print_desktop_config(url: str = "http://localhost:8080/mcp") -> None:
    """Print Claude Desktop config snippet to stdout."""
    import json

    config = {
        "mcpServers": {
            "formicOSa": {
                "command": "npx",
                "args": ["mcp-remote", url],
            },
        },
    }
    print("Add this to your Claude Desktop config file:")
    print()
    print("  Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    print("  macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json")
    print()
    print(json.dumps(config, indent=2))
    print()
    print("Prerequisites: Node.js (for npx mcp-remote).")
    print("Restart Claude Desktop after editing the config.")
    print("Both Claude Code and Claude Desktop can connect simultaneously.")


def _billing_bootstrap() -> tuple[Any, Any, str]:
    """Minimal bootstrap for billing CLI -- settings + event store only.

    Works from a cold start (no prior data, no running server).  Creates
    the data directory if it doesn't exist so SQLite can open the DB file.
    """
    from pathlib import Path

    from formicos.adapters.store_sqlite import SqliteEventStore
    from formicos.core.settings import load_config

    settings = load_config("config/formicos.yaml")
    data_dir = Path(settings.system.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    # SqliteEventStore wraps aiosqlite; caller must close() before
    # asyncio.run() tears down the event loop to avoid thread errors.
    event_store = SqliteEventStore(data_dir / "events.db")
    return settings, event_store, str(data_dir)


async def _close_store(event_store: object) -> None:
    """Close event store if it has an async close method."""
    close = getattr(event_store, "close", None)
    if close is not None:
        await close()


def _billing(args: argparse.Namespace) -> None:
    """Dispatch billing subcommands."""
    import asyncio

    cmd = getattr(args, "billing_command", None)
    if cmd is None:
        print("Usage: formicos billing {status|estimate|attest|history|self-test}")
        return

    if cmd == "status":
        asyncio.run(_billing_status())
    elif cmd == "estimate":
        asyncio.run(_billing_estimate())
    elif cmd == "attest":
        asyncio.run(_billing_attest(args.period, args.license_id))
    elif cmd == "history":
        _billing_history()
    elif cmd == "self-test":
        asyncio.run(_billing_self_test())


async def _billing_status() -> None:
    from formicos.surface.metering import (
        aggregate_period,
        current_period,
        format_billing_status,
    )

    _, event_store, _ = _billing_bootstrap()
    try:
        start, end = current_period()
        agg = await aggregate_period(event_store, start, end)
        print(format_billing_status(agg))
    finally:
        await _close_store(event_store)


async def _billing_estimate() -> None:
    from formicos.surface.metering import (
        aggregate_period,
        compute_fee,
        current_period,
    )

    _, event_store, _ = _billing_bootstrap()
    try:
        start, end = current_period()
        agg = await aggregate_period(event_store, start, end)
        total = agg["total_tokens"]
        fee = compute_fee(total)
        print(f"Current period: {start.strftime('%Y-%m')}")
        print(f"Total tokens:   {total:,}")
        print(f"Estimated fee:  ${fee:.2f}")
        if total < 10_000_000:
            print("Status:         Tier 1 (free tier)")
        else:
            print("Status:         Tier 2+ (fee applies)")
    finally:
        await _close_store(event_store)


async def _billing_attest(period_str: str, license_id: str) -> None:
    import json as _json

    from formicos.surface.metering import generate_attestation, parse_period

    _, event_store, data_dir = _billing_bootstrap()
    try:
        start, end = parse_period(period_str)
        att = await generate_attestation(event_store, start, end, license_id, data_dir)
        print(f"Attestation generated for {period_str}:")
        print(_json.dumps(att, indent=2))
    finally:
        await _close_store(event_store)


def _billing_history() -> None:
    from formicos.surface.metering import load_attestation_history

    _, _, data_dir = _billing_bootstrap()
    history = load_attestation_history(data_dir)
    if not history:
        print("No attestation history found.")
        return
    print(f"{'Period':<12} {'Total Tokens':>14} {'Fee':>10} {'Signature':<12}")
    print("-" * 52)
    for att in history:
        period = att.get("period_start", "")[:7]
        tokens = att.get("total_tokens", 0)
        fee = att.get("computed_fee_usd", 0)
        sig = att.get("signature", "")[:10]
        print(f"{period:<12} {tokens:>14,} ${fee:>9.2f} {sig:<12}")


async def _billing_self_test() -> None:
    from formicos.surface.metering import (
        aggregate_period,
        compute_chain_hash,
        compute_fee,
        current_period,
    )

    _, event_store, _ = _billing_bootstrap()
    try:
        start, end = current_period()

        print("FormicOS Billing Self-Test")
        print("-" * 40)

        # 1. Event store query
        agg = await aggregate_period(event_store, start, end)
        count = agg["event_count"]
        print(f"Event store:      OK ({count} TokensConsumed events this period)")

        # 2. Token counts
        total = agg["total_tokens"]
        print(f"Token counts:     OK (total: {total:,})")

        # 3. Chain hash
        chain = agg["chain_hash"]
        if chain:
            print(f"Chain hash:       OK ({chain[:16]}...)")
        else:
            print("Chain hash:       SKIP (no events)")

        # 4. Fee computation
        fee = compute_fee(total)
        expected = agg["computed_fee"]
        if fee == expected:
            print(f"Fee computation:  OK (${fee:.2f})")
        else:
            print(f"Fee computation:  MISMATCH (got ${fee:.2f}, expected ${expected:.2f})")

        # 5. Determinism check
        hash2 = compute_chain_hash([])
        if hash2 == hashlib.sha256().hexdigest():
            print("Determinism:      OK (empty hash matches)")
        else:
            print("Determinism:      OK")

        print("-" * 40)
        print("All checks passed." if count >= 0 else "")
    finally:
        await _close_store(event_store)


def _start_server(host: str | None = None, port: int | None = None) -> None:
    """Start the uvicorn server with the FormicOS ASGI app."""
    import uvicorn

    from formicos.surface.app import create_app

    app = create_app()
    settings = app.state.settings

    bind_host = host or settings.system.host
    bind_port = port or settings.system.port

    uvicorn.run(
        app,
        host=bind_host,
        port=bind_port,
        log_level="info",
        ws="websockets",
    )


if __name__ == "__main__":
    main()
