#!/usr/bin/env python3
"""
Migrate FormicOS v0.6.x data to v0.7.0 format.

Usage:
    python scripts/migrate_v06_to_v07.py --config formicos.yaml [--dry-run] [--verbose]

This script:
1. Config transform: reads formicos.yaml, sets schema_version to "1.0",
   writes formicos.v1.yaml
2. Session transform: walks sessions dir, wraps each in SessionSnapshotV1
   envelope, writes with _v1 suffix
3. Skill transform: reads skills.json, normalizes each skill to SkillV1
   shape, writes skills.v1.json
4. Result materialization: for completed colonies, builds ColonyResultV1
   from workspace + final state
5. Verification: validates all outputs against Pydantic models, emits report

Source files are NEVER modified. The script creates new _v1 suffixed files.
Use --dry-run to preview all changes.
"""

from __future__ import annotations

import argparse
import json
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
# Config migration
# ---------------------------------------------------------------------------

def migrate_config(config_path: Path, dry_run: bool, verbose: bool) -> Path | None:
    """Migrate config to v1.0 schema_version.

    Reads the existing YAML, updates schema_version to "1.0",
    and writes to a .v1.yaml file alongside the original.

    Returns the output path, or None on failure.
    """
    if not config_path.exists():
        print(f"  Config not found: {config_path}")
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print(f"  Config is not a dict: {config_path}")
        return None

    old_version = config.get("schema_version", "unknown")
    config["schema_version"] = "1.0"

    # Update identity version if present
    if "identity" in config and isinstance(config["identity"], dict):
        config["identity"]["version"] = "0.7.0"

    output_path = config_path.with_suffix(".v1.yaml")

    if verbose:
        print(f"  schema_version: {old_version} -> 1.0")

    if dry_run:
        print(f"  [DRY RUN] Would write: {output_path}")
        return output_path

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"  Written: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Session migration
# ---------------------------------------------------------------------------

def migrate_sessions(config_path: Path, dry_run: bool, verbose: bool) -> int:
    """Wrap existing session files in SessionSnapshotV1 envelope.

    Returns the number of sessions migrated.
    """
    # Determine sessions dir from config
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    session_dir_str = "."
    if isinstance(config, dict):
        persistence = config.get("persistence", {})
        if isinstance(persistence, dict):
            session_dir_str = persistence.get("session_dir", ".formicos/sessions")

    sessions_dir = Path(session_dir_str)
    if not sessions_dir.exists():
        print(f"  Sessions directory not found: {sessions_dir}")
        return 0

    count = 0
    for session_path in sorted(sessions_dir.iterdir()):
        if not session_path.is_dir():
            continue

        context_file = session_path / "context.json"
        if not context_file.exists():
            if verbose:
                print(f"  Skip (no context.json): {session_path.name}")
            continue

        try:
            with open(context_file, "r", encoding="utf-8") as f:
                context_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  Error reading {context_file}: {exc}")
            continue

        # Extract fields for SessionSnapshotV1
        colony_data = context_data.get("colony", {})
        colony_id = colony_data.get("colony_id", session_path.name)
        session_id = colony_data.get("session_id", session_path.name)

        snapshot = {
            "session_id": session_id,
            "colony_id": colony_id,
            "state": context_data,
            "topology_history": colony_data.get("topology_history", []),
            "episodes": context_data.get("_episodes", []),
            "tkg": context_data.get("_tkg", []),
            "metadata": {
                "schema_version": "1.0",
                "saved_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "save_reason": "migration",
            },
        }

        output_file = session_path / "context_v1.json"

        if verbose:
            print(f"  Migrate session: {session_path.name} (colony={colony_id})")

        if dry_run:
            print(f"  [DRY RUN] Would write: {output_file}")
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)
            print(f"  Written: {output_file}")

        count += 1

    return count


# ---------------------------------------------------------------------------
# Skill migration
# ---------------------------------------------------------------------------

def migrate_skills(config_path: Path, dry_run: bool, verbose: bool) -> int:
    """Normalize skills to SkillV1 shape.

    Returns the number of skills migrated.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    skills_file_str = "skills.json"
    if isinstance(config, dict):
        sb = config.get("skill_bank", {})
        if isinstance(sb, dict):
            skills_file_str = sb.get("storage_file", "skills.json")

    skills_file = Path(skills_file_str)
    if not skills_file.exists():
        print(f"  Skills file not found: {skills_file}")
        return 0

    try:
        with open(skills_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Error reading skills: {exc}")
        return 0

    # Normalize to flat SkillV1 list
    v1_skills = []

    if isinstance(raw, dict):
        # Grouped by tier: {"general": [...], "task_specific": [...]}
        for tier, skills in raw.items():
            if not isinstance(skills, list):
                continue
            for skill in skills:
                v1_skills.append(_normalize_skill(skill, tier))
    elif isinstance(raw, list):
        for skill in raw:
            v1_skills.append(_normalize_skill(skill, "general"))

    output_file = skills_file.with_suffix(".v1.json")

    if verbose:
        print(f"  Normalized {len(v1_skills)} skills")

    if dry_run:
        print(f"  [DRY RUN] Would write: {output_file}")
    else:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(v1_skills, f, indent=2, default=str)
        print(f"  Written: {output_file}")

    return len(v1_skills)


def _normalize_skill(skill: Any, default_tier: str) -> dict:
    """Normalize a single skill entry to SkillV1 shape."""
    if isinstance(skill, dict):
        return {
            "skill_id": skill.get("skill_id", skill.get("id", f"migrated_{id(skill)}")),
            "content": skill.get("content", skill.get("description", "")),
            "tier": skill.get("tier", default_tier),
            "category": skill.get("category"),
            "metadata": {
                "source_colony": skill.get("source_colony"),
                "retrieval_count": skill.get("retrieval_count", 0),
                "success_correlation": skill.get("success_correlation", 0.0),
                "created_ts": skill.get("created_ts"),
                "updated_ts": skill.get("updated_ts"),
            },
        }
    return {
        "skill_id": f"migrated_{id(skill)}",
        "content": str(skill),
        "tier": default_tier,
        "category": None,
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Result materialization
# ---------------------------------------------------------------------------

def materialize_results(config_path: Path, dry_run: bool, verbose: bool) -> int:
    """For completed colonies, build ColonyResultV1 from workspace + state.

    Returns the number of results materialized.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    session_dir_str = ".formicos/sessions"
    if isinstance(config, dict):
        persistence = config.get("persistence", {})
        if isinstance(persistence, dict):
            session_dir_str = persistence.get("session_dir", ".formicos/sessions")

    sessions_dir = Path(session_dir_str)
    workspace_base = Path("./workspace")
    count = 0

    if not sessions_dir.exists():
        return 0

    for session_path in sorted(sessions_dir.iterdir()):
        if not session_path.is_dir():
            continue

        context_file = session_path / "context.json"
        if not context_file.exists():
            continue

        try:
            with open(context_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        colony_data = data.get("colony", {})
        status = colony_data.get("status", "")

        if status not in ("completed", "COMPLETED"):
            continue

        colony_id = colony_data.get("colony_id", session_path.name)

        # Scan workspace for files
        ws_path = workspace_base / colony_id
        files = []
        if ws_path.exists():
            files = sorted(
                str(p.relative_to(ws_path)).replace("\\", "/")
                for p in ws_path.rglob("*") if p.is_file()
            )

        result = {
            "colony_id": colony_id,
            "status": "completed",
            "final_answer": colony_data.get("final_answer"),
            "summary": None,
            "files": files,
            "session_ref": str(context_file),
            "completed_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "failure": {"code": None, "detail": None},
        }

        output_file = session_path / "result_v1.json"

        if verbose:
            print(f"  Result for colony '{colony_id}': {len(files)} files")

        if dry_run:
            print(f"  [DRY RUN] Would write: {output_file}")
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Written: {output_file}")

        count += 1

    return count


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_outputs(config_path: Path, verbose: bool) -> list[str]:
    """Validate migrated files against Pydantic models.

    Returns a list of warnings/errors.
    """
    warnings = []

    try:
        from src.models import (
            SessionSnapshotV1,
            ColonyResultV1,
            SkillV1,
        )
    except ImportError:
        warnings.append("Cannot import v0.7.0 models — skip Pydantic validation")
        return warnings

    # Verify config
    v1_config = config_path.with_suffix(".v1.yaml")
    if v1_config.exists():
        with open(v1_config, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data.get("schema_version") != "1.0":
            warnings.append(f"Config schema_version != 1.0 in {v1_config}")
    else:
        warnings.append(f"Config v1 file not found: {v1_config}")

    # Verify skills
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    skills_file_str = "skills.json"
    if isinstance(config, dict):
        sb = config.get("skill_bank", {})
        if isinstance(sb, dict):
            skills_file_str = sb.get("storage_file", "skills.json")

    v1_skills = Path(skills_file_str).with_suffix(".v1.json")
    if v1_skills.exists():
        with open(v1_skills, "r", encoding="utf-8") as f:
            skills = json.load(f)
        for i, s in enumerate(skills):
            try:
                SkillV1(**s)
            except Exception as exc:
                warnings.append(f"Skill #{i} validation failed: {exc}")
    else:
        warnings.append(f"Skills v1 file not found: {v1_skills}")

    # Verify sessions
    session_dir_str = ".formicos/sessions"
    if isinstance(config, dict):
        persistence = config.get("persistence", {})
        if isinstance(persistence, dict):
            session_dir_str = persistence.get("session_dir", ".formicos/sessions")

    sessions_dir = Path(session_dir_str)
    if sessions_dir.exists():
        for session_path in sessions_dir.iterdir():
            v1_ctx = session_path / "context_v1.json"
            if v1_ctx.exists():
                with open(v1_ctx, "r", encoding="utf-8") as f:
                    data = json.load(f)
                try:
                    SessionSnapshotV1(**data)
                except Exception as exc:
                    warnings.append(f"Session {session_path.name} validation: {exc}")

            v1_result = session_path / "result_v1.json"
            if v1_result.exists():
                with open(v1_result, "r", encoding="utf-8") as f:
                    data = json.load(f)
                try:
                    ColonyResultV1(**data)
                except Exception as exc:
                    warnings.append(f"Result {session_path.name} validation: {exc}")

    return warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate FormicOS v0.6.x to v0.7.0",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config/formicos.yaml"),
        help="Path to formicos.yaml config file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing files",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("FormicOS v0.6.x -> v0.7.0 Migration")
    print("=" * 60)

    if args.dry_run:
        print("[DRY RUN MODE — no files will be written]\n")

    # 1. Config
    print("\n1. Config Migration")
    print("-" * 40)
    migrate_config(args.config, args.dry_run, args.verbose)

    # 2. Sessions
    print("\n2. Session Migration")
    print("-" * 40)
    session_count = migrate_sessions(args.config, args.dry_run, args.verbose)
    print(f"  Sessions migrated: {session_count}")

    # 3. Skills
    print("\n3. Skill Migration")
    print("-" * 40)
    skill_count = migrate_skills(args.config, args.dry_run, args.verbose)
    print(f"  Skills migrated: {skill_count}")

    # 4. Results
    print("\n4. Result Materialization")
    print("-" * 40)
    result_count = materialize_results(args.config, args.dry_run, args.verbose)
    print(f"  Results materialized: {result_count}")

    # 5. Verification
    if not args.dry_run:
        print("\n5. Verification")
        print("-" * 40)
        warnings = verify_outputs(args.config, args.verbose)
        if warnings:
            for w in warnings:
                print(f"  WARNING: {w}")
            print(f"  {len(warnings)} warning(s)")
        else:
            print("  All outputs validated successfully.")

    print("\n" + "=" * 60)
    print("Migration complete.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
