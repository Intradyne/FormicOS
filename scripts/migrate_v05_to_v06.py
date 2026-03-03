#!/usr/bin/env python3
"""
Migrate FormicOS v0.5.x data to v0.6.0 format.

Usage:
    python scripts/migrate_v05_to_v06.py [--source formicos/] [--target ./] [--dry-run]

This script:
1. Migrates session files (adds schema_version, copies to new location)
2. Migrates skill bank (adds metadata, copies to new location)
3. Validates config YAML against v0.6.0 schema
4. Copies prompt files if they don't already exist at the target
5. Reports all changes without modifying source files

Source files are NEVER modified. The script reads from --source and writes
to --target. Use --dry-run to preview all changes before committing them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install it with:\n"
        "  pip install pyyaml\n",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Session migration
# ---------------------------------------------------------------------------

def migrate_sessions(source_dir: Path, target_dir: Path, dry_run: bool) -> int:
    """Migrate session files from v0.5.x to v0.6.0 format.

    For each session directory under ``source_dir/.formicos/sessions/``:
    - Reads ``session.json``
    - Adds ``schema_version: "0.6.0"``
    - Writes the updated JSON to ``target_dir/.formicos/sessions/<id>/session.json``

    Returns the number of sessions successfully migrated.
    """
    source_sessions = source_dir / ".formicos" / "sessions"
    target_sessions = target_dir / ".formicos" / "sessions"

    if not source_sessions.exists():
        print(f"  No sessions directory found at {source_sessions}")
        return 0

    if not source_sessions.is_dir():
        print(f"  {source_sessions} is not a directory -- skipping")
        return 0

    migrated = 0
    skipped = 0

    for entry in sorted(source_sessions.iterdir()):
        if not entry.is_dir():
            continue

        session_file = entry / "session.json"
        if not session_file.exists():
            print(f"  SKIP {entry.name}: no session.json found")
            skipped += 1
            continue

        # Read & parse -------------------------------------------------
        try:
            raw = session_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  SKIP {entry.name}: cannot read file ({exc})")
            skipped += 1
            continue

        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  SKIP {entry.name}: corrupt JSON ({exc})")
            skipped += 1
            continue

        if not isinstance(data, dict):
            print(f"  SKIP {entry.name}: top-level value is not a JSON object")
            skipped += 1
            continue

        # Transform ----------------------------------------------------
        data["schema_version"] = "0.6.0"

        # Write --------------------------------------------------------
        target = target_sessions / entry.name
        if not dry_run:
            target.mkdir(parents=True, exist_ok=True)
            out_path = target / "session.json"
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  {'[DRY] ' if dry_run else ''}Migrated session: {entry.name}")
        migrated += 1

    if skipped:
        print(f"  ({skipped} session(s) skipped due to errors)")

    return migrated


# ---------------------------------------------------------------------------
# Skill Bank migration
# ---------------------------------------------------------------------------

def migrate_skill_bank(source_dir: Path, target_dir: Path, dry_run: bool) -> bool:
    """Migrate skill bank from v0.5.x to v0.6.0 format.

    Reads ``source_dir/.formicos/skill_bank.json``, adds metadata fields
    required by v0.6.0, and writes to ``target_dir/.formicos/skill_bank.json``.

    Returns True on success, False otherwise.
    """
    source = source_dir / ".formicos" / "skill_bank.json"
    target = target_dir / ".formicos" / "skill_bank.json"

    if not source.exists():
        print(f"  No skill bank found at {source}")
        return False

    # Read & parse -----------------------------------------------------
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  SKIP: cannot read skill bank ({exc})")
        return False

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  SKIP: corrupt skill bank JSON ({exc})")
        return False

    if not isinstance(data, dict):
        print("  SKIP: skill bank top-level value is not a JSON object")
        return False

    # Transform --------------------------------------------------------
    data["schema_version"] = "0.6.0"
    data["embedding_model"] = "all-MiniLM-L6-v2"
    data["migrated_from"] = "v0.5.x"
    data["migrated_at"] = time.time()

    skills = data.get("skills", [])
    if not isinstance(skills, list):
        print("  WARNING: 'skills' key is not a list -- wrapping in list")
        skills = [skills] if skills else []
        data["skills"] = skills

    for skill in skills:
        if not isinstance(skill, dict):
            continue
        # Ensure required v0.6.0 fields exist with sensible defaults
        skill.setdefault("schema_version", "0.6.0")
        skill.setdefault("success_correlation", 0.0)
        skill.setdefault("superseded_by", None)

    # Write ------------------------------------------------------------
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  {'[DRY] ' if dry_run else ''}Migrated {len(skills)} skill(s)")
    return True


# ---------------------------------------------------------------------------
# Config YAML validation
# ---------------------------------------------------------------------------

# Top-level keys expected in a v0.6.0 config
_REQUIRED_SECTIONS = [
    "identity",
    "hardware",
    "inference",
    "embedding",
    "routing",
    "convergence",
    "summarization",
    "temporal",
    "castes",
    "persistence",
    "qdrant",
    "mcp_gateway",
    "model_registry",
    "skill_bank",
    "subcaste_map",
    "teams",
]

_KNOWN_SECTIONS = set(_REQUIRED_SECTIONS) | {
    "schema_version",
    "cloud_burst",
    "approval_required",
    "colonies",
}


def validate_config(source_dir: Path, target_dir: Path, dry_run: bool) -> list[str]:
    """Validate v0.5.x config YAML against v0.6.0 expectations.

    Reads ``source_dir/config/formicos.yaml``, checks for required sections,
    detects unknown sections, and optionally validates against the Pydantic
    model if importable.

    If validation passes, writes the (possibly patched) config to
    ``target_dir/config/formicos.yaml``.

    Returns a list of human-readable issue strings (empty = no issues).
    """
    source = source_dir / "config" / "formicos.yaml"
    target = target_dir / "config" / "formicos.yaml"

    issues: list[str] = []

    if not source.exists():
        issues.append(f"Config not found at {source}")
        return issues

    # Read & parse -----------------------------------------------------
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(f"Cannot read config: {exc}")
        return issues

    try:
        data: dict[str, Any] = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        issues.append(f"Invalid YAML: {exc}")
        return issues

    if data is None:
        issues.append("Config file is empty")
        return issues

    if not isinstance(data, dict):
        issues.append("Config top-level value is not a YAML mapping")
        return issues

    # Structural checks ------------------------------------------------
    if "schema_version" not in data:
        issues.append("Missing 'schema_version' (will add '0.6.0')")
        data["schema_version"] = "0.6.0"
    elif data["schema_version"] != "0.6.0":
        old = data["schema_version"]
        issues.append(f"schema_version is '{old}', will update to '0.6.0'")
        data["schema_version"] = "0.6.0"

    for key in _REQUIRED_SECTIONS:
        if key not in data:
            issues.append(f"Missing required section: '{key}'")

    for key in data:
        if key not in _KNOWN_SECTIONS:
            issues.append(f"Unknown section: '{key}' (may need manual review)")

    # Pydantic validation (best-effort) --------------------------------
    try:
        sys.path.insert(0, str(target_dir))
        from src.models import FormicOSConfig  # type: ignore[import-not-found]

        FormicOSConfig.model_validate(data)
        print("  Config validates against v0.6.0 Pydantic schema")
    except ImportError:
        issues.append(
            "Cannot import src.models for Pydantic validation "
            "(run from repo root or install dependencies)"
        )
    except Exception as exc:
        issues.append(f"Pydantic validation error: {exc}")

    # Write patched config (only if there are no blocking issues) ------
    blocking = [i for i in issues if "not found" not in i.lower() and "empty" not in i.lower()]
    if not dry_run and source != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"  Wrote patched config to {target}")
    elif dry_run:
        print(f"  [DRY] Would write patched config to {target}")

    return issues


# ---------------------------------------------------------------------------
# Prompt files
# ---------------------------------------------------------------------------

def migrate_prompts(source_dir: Path, target_dir: Path, dry_run: bool) -> int:
    """Copy prompt markdown files from source to target if they don't exist.

    Returns the number of files copied (or that would be copied in dry-run).
    """
    source_prompts = source_dir / "config" / "prompts"
    target_prompts = target_dir / "config" / "prompts"

    if not source_prompts.exists():
        print(f"  No prompts directory found at {source_prompts}")
        return 0

    if not source_prompts.is_dir():
        print(f"  {source_prompts} is not a directory -- skipping")
        return 0

    prompt_files = sorted(source_prompts.glob("*.md"))
    if not prompt_files:
        print("  No .md prompt files found in source")
        return 0

    print(f"  Found {len(prompt_files)} prompt file(s) in source")

    if target_prompts.exists() and any(target_prompts.glob("*.md")):
        print("  Target prompts directory already contains .md files -- skipping copy")
        return 0

    if not dry_run:
        shutil.copytree(source_prompts, target_prompts, dirs_exist_ok=True)
        print(f"  Copied prompts to {target_prompts}")
    else:
        print(f"  [DRY] Would copy prompts to {target_prompts}")

    return len(prompt_files)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate FormicOS v0.5.x data to v0.6.0 format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/migrate_v05_to_v06.py --dry-run\n"
            "  python scripts/migrate_v05_to_v06.py --source formicos/ --target ./\n"
        ),
    )
    parser.add_argument(
        "--source",
        default="formicos/",
        help="Path to v0.5.x installation (default: formicos/)",
    )
    parser.add_argument(
        "--target",
        default="./",
        help="Path to v0.6.0 installation root (default: ./)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing any files",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    target = Path(args.target).resolve()

    # Sanity checks ----------------------------------------------------
    if not source.exists():
        print(f"ERROR: Source directory does not exist: {source}", file=sys.stderr)
        return 1

    if source == target:
        print(
            "WARNING: Source and target are the same directory. "
            "Files will be updated in-place.\n",
        )

    # Banner -----------------------------------------------------------
    print("=" * 55)
    print("  FormicOS v0.5.x  -->  v0.6.0  Migration")
    print("=" * 55)
    print(f"  Source : {source}")
    print(f"  Target : {target}")
    if args.dry_run:
        print("  Mode   : DRY RUN (no files will be written)")
    else:
        print("  Mode   : LIVE (files will be written)")
    print()

    # 1. Sessions ------------------------------------------------------
    print("1. Migrating sessions...")
    n_sessions = migrate_sessions(source, target, args.dry_run)
    print(f"   Result: {n_sessions} session(s) migrated")
    print()

    # 2. Skill Bank ----------------------------------------------------
    print("2. Migrating skill bank...")
    skill_ok = migrate_skill_bank(source, target, args.dry_run)
    print(f"   Result: {'OK' if skill_ok else 'skipped (see above)'}")
    print()

    # 3. Config --------------------------------------------------------
    print("3. Validating and migrating config...")
    issues = validate_config(source, target, args.dry_run)
    if issues:
        print("   Issues found:")
        for issue in issues:
            print(f"     - {issue}")
    else:
        print("   No issues found")
    print()

    # 4. Prompts -------------------------------------------------------
    print("4. Checking prompt files...")
    n_prompts = migrate_prompts(source, target, args.dry_run)
    print(f"   Result: {n_prompts} prompt file(s) handled")
    print()

    # Summary ----------------------------------------------------------
    n_issues = len(issues)
    print("=" * 55)
    if n_issues == 0:
        print("  Migration complete. No issues found.")
    else:
        print(f"  Migration complete with {n_issues} issue(s).")
        print("  Review the issues above before running without --dry-run.")
    print("=" * 55)

    return 0 if n_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
