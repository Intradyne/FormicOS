#!/usr/bin/env python3
"""
FormicOS v0.8.0 — Cloud Handover Context Compiler

Concatenates the entire codebase into a single `cloud_context.txt` file
ready for upload to a frontier Cloud Model (Claude, GPT-4o, etc.).

The output is structured in sections:
  1. Prompt-Zero.txt        — The Cloud Model's operating directive
  2. AI-CONTRIBUTING.md     — Testing and debugging protocols
  3. Data-Migration-Strategy.md — Schema evolution rules
  4. Backend Master Spec    — Canonical architecture
  5. Source code (src/)     — All Python source files
  6. Test scaffolding       — conftest.py + latest version tests
  7. Configuration          — formicos.yaml, pyproject.toml, requirements.txt
  8. Infrastructure         — Dockerfile, docker-compose.yml, formicos-cli.py

Usage:
    python scripts/compile_context.py
    python scripts/compile_context.py --output handover.txt
    python scripts/compile_context.py --include-all-tests
    python scripts/compile_context.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ── File manifest ────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

# Section 1: The directive
PROMPT_ZERO = ["Prompt-Zero.txt"]

# Section 2: Governing documents (order matters)
GOVERNING_DOCS = [
    "docs/v0.8.0/AI-CONTRIBUTING.md",
    "docs/v0.8.0/Data-Migration-Strategy.md",
    "docs/v0.8.0/FormicOS-v0.8.0-Backend-Master-Spec.md",
]

# Section 3: Source code — models first (leaf dependency), then server, then rest
SOURCE_FILES_ORDERED = [
    # Core schemas (read first — universal type system)
    "src/models.py",
    # App factory and lifespan
    "src/server.py",
    # API layer (v0.7.9 extracted routes)
    "src/api/__init__.py",
    "src/api/ws.py",
    "src/api/helpers.py",
    "src/api/callbacks.py",
    "src/api/routes/__init__.py",
    "src/api/routes/system.py",
    "src/api/routes/auth.py",
    "src/api/routes/colonies.py",
    "src/api/routes/workspace.py",
    "src/api/routes/admin.py",
    "src/api/routes/sessions.py",
    "src/api/routes/castes.py",
    # Colony lifecycle
    "src/colony_manager.py",
    # Orchestration engine
    "src/orchestrator.py",
    # Agent abstraction
    "src/agents.py",
    # Memory and knowledge
    "src/context.py",
    "src/rag.py",
    "src/stigmergy.py",
    "src/router.py",
    # Services
    "src/mcp_client.py",
    "src/auth.py",
    "src/webhook.py",
    "src/worker.py",
    # Supporting modules
    "src/governance.py",
    "src/session.py",
    "src/skill_bank.py",
    "src/archivist.py",
    "src/audit.py",
    "src/approval.py",
    "src/model_registry.py",
    # Scaffolds
    "src/core/__init__.py",
    "src/services/__init__.py",
    # Package init
    "src/__init__.py",
    "src/__main__.py",
]

# Section 4: Test scaffolding (always included)
TEST_SCAFFOLDING = [
    "tests/conftest.py",
    "tests/test_v079_refactor.py",
    "tests/test_v078_harness.py",
]

# Section 5: All test files (optional, for --include-all-tests)
# Discovered dynamically from tests/ directory.

# Section 6: Configuration
CONFIG_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "config/caste_recipes.yaml",
]

# Section 7: Infrastructure
INFRA_FILES = [
    "Dockerfile",
    "docker-compose.yml",
    "formicos-cli.py",
]


# ── Helpers ──────────────────────────────────────────────────────────────


def _section_banner(title: str, section_num: int) -> str:
    """Create a visible section banner for the compiled context."""
    rule = "=" * 80
    return (
        f"\n\n{rule}\n"
        f"SECTION {section_num}: {title}\n"
        f"{rule}\n\n"
    )


def _file_banner(rel_path: str) -> str:
    """Create a file header banner."""
    dashes = "-" * 80
    return f"\n{dashes}\n FILE: {rel_path}\n{dashes}\n\n"


def _read_file(path: Path) -> str | None:
    """Read a file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"  WARNING: Could not read {path}: {exc}", file=sys.stderr)
        return None


def _discover_all_tests() -> list[str]:
    """Discover all test files in tests/ directory."""
    tests_dir = REPO_ROOT / "tests"
    if not tests_dir.exists():
        return []
    files = sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in tests_dir.glob("test_*.py")
    )
    return files


def _count_tokens_approx(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars for code)."""
    return len(text) // 4


# ── Main ─────────────────────────────────────────────────────────────────


def compile_context(
    output_path: Path,
    include_all_tests: bool = False,
    dry_run: bool = False,
) -> None:
    """Compile the full handover context into a single file."""

    sections: list[tuple[str, list[str]]] = [
        ("PROMPT ZERO — CLOUD MODEL DIRECTIVE", PROMPT_ZERO),
        ("GOVERNING DOCUMENTS", GOVERNING_DOCS),
        ("SOURCE CODE", SOURCE_FILES_ORDERED),
        ("TEST SCAFFOLDING", TEST_SCAFFOLDING),
    ]

    if include_all_tests:
        all_tests = _discover_all_tests()
        # Exclude files already in scaffolding
        scaffolding_set = {f.replace("\\", "/") for f in TEST_SCAFFOLDING}
        extra_tests = [t for t in all_tests if t not in scaffolding_set]
        if extra_tests:
            sections.append(("ALL TEST FILES", extra_tests))

    sections.append(("CONFIGURATION", CONFIG_FILES))
    sections.append(("INFRASTRUCTURE", INFRA_FILES))

    # Compile
    parts: list[str] = []
    total_files = 0
    missing_files: list[str] = []

    for section_idx, (title, file_list) in enumerate(sections, 1):
        parts.append(_section_banner(title, section_idx))

        for rel_path in file_list:
            full_path = REPO_ROOT / rel_path
            content = _read_file(full_path)

            if content is None:
                missing_files.append(rel_path)
                if not dry_run:
                    parts.append(_file_banner(rel_path))
                    parts.append(f"[FILE NOT FOUND: {rel_path}]\n")
                continue

            total_files += 1

            if dry_run:
                lines = content.count("\n") + 1
                print(f"  {rel_path:60s} {lines:>6} lines")
            else:
                parts.append(_file_banner(rel_path))
                parts.append(content)
                if not content.endswith("\n"):
                    parts.append("\n")

    compiled = "".join(parts)
    approx_tokens = _count_tokens_approx(compiled)

    # Summary
    print(f"\nFormicOS v0.8.0 Cloud Handover Context Compiler")
    print(f"{'=' * 50}")
    print(f"  Files included:  {total_files}")
    if missing_files:
        print(f"  Files missing:   {len(missing_files)}")
        for m in missing_files:
            print(f"    - {m}")
    print(f"  Output size:     {len(compiled):,} chars")
    print(f"  Approx tokens:   ~{approx_tokens:,}")
    print(f"  Output file:     {output_path}")

    if approx_tokens > 200_000:
        print(f"\n  WARNING: Output exceeds 200K tokens. Consider using")
        print(f"  --include-all-tests=false (default) to reduce size.")
        print(f"  The Cloud Model can request specific test files on demand.")

    if dry_run:
        print(f"\n  DRY RUN — no file written.")
        return

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(compiled, encoding="utf-8")
    print(f"\n  Context compiled successfully.")
    print(f"  Upload {output_path.name} to your Cloud Model interface.")


def main():
    parser = argparse.ArgumentParser(
        description="Compile FormicOS codebase into a single context file for Cloud Model handover.",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=REPO_ROOT / "cloud_context.txt",
        help="Output file path (default: cloud_context.txt in repo root)",
    )
    parser.add_argument(
        "--include-all-tests",
        action="store_true",
        default=False,
        help="Include ALL test files (default: only conftest + v0.7.8/v0.7.9 tests)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print file manifest and sizes without writing output",
    )
    args = parser.parse_args()

    compile_context(
        output_path=args.output,
        include_all_tests=args.include_all_tests,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
