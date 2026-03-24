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
