"""FormicOS CLI entry point — ``python -m formicos``."""

from __future__ import annotations

import argparse

from formicos import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="formicos",
        description="FormicOS — Stigmergic Multi-Agent Colony Framework",
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
        _init_mcp(url=args.url)


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
- `addon_status` — Check installed addon health
- `toggle_addon` — Enable/disable addons
- `trigger_addon` — Run addon handlers (reindex, etc.)

## MCP Resources

- `formicos://plan` — Project plan (global)
- `formicos://procedures/{{workspace_id}}` — Operating procedures
- `formicos://journal/{{workspace_id}}` — Recent journal entries
- `formicos://knowledge/{{workspace}}` — Knowledge catalog
- `formicos://briefing/{{workspace_id}}` — Proactive intelligence briefing

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
    print("Restart Claude Code to connect. Then try:")
    print("  morning-status — get a complete briefing")
    print("  delegate-task — hand off work to FormicOS")
    print("  knowledge-for-context — search institutional memory")


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
