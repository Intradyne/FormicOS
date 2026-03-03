#!/usr/bin/env python3
"""
FormicOS CLI — programmatic control for autonomous Cloud Model operation.

Usage:
    python formicos-cli.py rebuild
    python formicos-cli.py diagnostics <colony_id>
    python formicos-cli.py status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

FORMICOS_API = "http://localhost:8000"


def cmd_rebuild(args: argparse.Namespace) -> None:
    """Rebuild FormicOS Docker containers."""
    compose_root = Path(__file__).resolve().parent
    print("Initiating FormicOS rebuild sequence...")
    print(f"  compose root: {compose_root}")
    try:
        subprocess.run(
            ["docker-compose", "down"],
            cwd=str(compose_root),
            check=True,
        )
        subprocess.run(
            ["docker-compose", "up", "--build", "-d"],
            cwd=str(compose_root),
            check=True,
        )
        print("Rebuild complete. API listening on :8000")
    except subprocess.CalledProcessError as exc:
        print(f"Rebuild failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("docker-compose not found. Is Docker installed?", file=sys.stderr)
        sys.exit(1)


def cmd_diagnostics(args: argparse.Namespace) -> None:
    """Fetch diagnostic payload for a colony."""
    try:
        import requests
    except ImportError:
        # Fall back to urllib if requests is not installed
        import urllib.request
        import urllib.error
        url = f"{FORMICOS_API}/api/v1/admin/diagnostics/{args.colony_id}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                print(json.dumps(data, indent=2))
        except urllib.error.URLError as exc:
            print(f"Failed to reach FormicOS API: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    url = f"{FORMICOS_API}/api/v1/admin/diagnostics/{args.colony_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        print(f"Diagnostics request failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args: argparse.Namespace) -> None:
    """Check FormicOS health status."""
    try:
        import requests
    except ImportError:
        import urllib.request
        import urllib.error
        url = f"{FORMICOS_API}/api/v1/system/health"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                print(json.dumps(data, indent=2))
        except urllib.error.URLError as exc:
            print(f"Failed to reach FormicOS API: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    url = f"{FORMICOS_API}/api/v1/system/health"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        print(f"Health check failed: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formicos-cli",
        description="FormicOS CLI — programmatic control for autonomous Cloud Model operation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # rebuild
    subparsers.add_parser("rebuild", help="Rebuild FormicOS Docker containers")

    # diagnostics
    diag = subparsers.add_parser("diagnostics", help="Fetch colony diagnostics")
    diag.add_argument("colony_id", help="Colony ID to diagnose")

    # status
    subparsers.add_parser("status", help="Check FormicOS health status")

    args = parser.parse_args()

    dispatch = {
        "rebuild": cmd_rebuild,
        "diagnostics": cmd_diagnostics,
        "status": cmd_status,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
