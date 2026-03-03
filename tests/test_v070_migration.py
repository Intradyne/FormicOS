"""
FormicOS v0.7.0 — Migration Script Tests

Tests the v0.6.x -> v0.7.0 migration functions.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.migrate_v06_to_v07 import (
    migrate_config,
    migrate_sessions,
    migrate_skills,
    materialize_results,
    _normalize_skill,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _write_config(tmp_path: Path) -> Path:
    """Write a minimal v0.6.x config YAML."""
    config_path = tmp_path / "formicos.yaml"
    config = {
        "schema_version": "0.6.0",
        "identity": {"name": "FormicOS", "version": "0.6.2"},
        "persistence": {"session_dir": str(tmp_path / "sessions")},
        "skill_bank": {"storage_file": str(tmp_path / "skills.json")},
    }
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path


def _write_session(tmp_path: Path, colony_id: str, status: str = "completed") -> Path:
    """Write a mock session context.json."""
    session_dir = tmp_path / "sessions" / colony_id
    session_dir.mkdir(parents=True, exist_ok=True)
    context = {
        "colony": {
            "colony_id": colony_id,
            "session_id": f"session-{colony_id}",
            "status": status,
            "task": "test task",
            "round": 3,
            "final_answer": "test answer" if status == "completed" else None,
            "topology_history": [{"round": 0}, {"round": 1}],
        },
        "_episodes": [{"round": 0, "summary": "did stuff"}],
        "_tkg": [{"subject": "X", "predicate": "uses", "object": "Y"}],
    }
    context_file = session_dir / "context.json"
    with open(context_file, "w") as f:
        json.dump(context, f)
    return session_dir


def _write_skills(tmp_path: Path) -> Path:
    """Write a mock skills.json."""
    skills_file = tmp_path / "skills.json"
    skills = {
        "general": [
            {"skill_id": "gen_001", "content": "Use pytest", "retrieval_count": 5},
            {"skill_id": "gen_002", "content": "Split modules"},
        ],
        "task_specific": [
            {"skill_id": "ts_001", "content": "FastAPI routing", "category": "web"},
        ],
    }
    with open(skills_file, "w") as f:
        json.dump(skills, f)
    return skills_file


# ── Config Migration ─────────────────────────────────────────────────────


def test_config_migration(tmp_path):
    config_path = _write_config(tmp_path)
    output = migrate_config(config_path, dry_run=False, verbose=True)

    assert output is not None
    assert output.exists()

    with open(output) as f:
        data = yaml.safe_load(f)

    assert data["schema_version"] == "1.0"
    assert data["identity"]["version"] == "0.7.0"


def test_config_migration_dry_run(tmp_path):
    config_path = _write_config(tmp_path)
    output = migrate_config(config_path, dry_run=True, verbose=False)

    assert output is not None
    # File should NOT be written in dry-run
    assert not output.exists()


def test_config_migration_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    output = migrate_config(missing, dry_run=False, verbose=False)
    assert output is None


# ── Session Migration ────────────────────────────────────────────────────


def test_session_migration(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "colony-alpha")
    _write_session(tmp_path, "colony-beta", status="running")

    count = migrate_sessions(config_path, dry_run=False, verbose=True)
    assert count == 2

    # Check v1 file was written
    v1_file = tmp_path / "sessions" / "colony-alpha" / "context_v1.json"
    assert v1_file.exists()

    with open(v1_file) as f:
        data = json.load(f)

    assert data["session_id"] == "session-colony-alpha"
    assert data["colony_id"] == "colony-alpha"
    assert data["metadata"]["schema_version"] == "1.0"
    assert data["metadata"]["save_reason"] == "migration"
    assert len(data["topology_history"]) == 2
    assert len(data["episodes"]) == 1
    assert len(data["tkg"]) == 1


def test_session_migration_preserves_state(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "test-col")

    migrate_sessions(config_path, dry_run=False, verbose=False)

    v1_file = tmp_path / "sessions" / "test-col" / "context_v1.json"
    with open(v1_file) as f:
        data = json.load(f)

    # State should contain the original context data
    assert "colony" in data["state"]
    assert data["state"]["colony"]["task"] == "test task"


def test_session_migration_dry_run(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "colony-dry")

    count = migrate_sessions(config_path, dry_run=True, verbose=False)
    assert count == 1

    v1_file = tmp_path / "sessions" / "colony-dry" / "context_v1.json"
    assert not v1_file.exists()


# ── Skill Migration ──────────────────────────────────────────────────────


def test_skill_migration(tmp_path):
    config_path = _write_config(tmp_path)
    _write_skills(tmp_path)

    count = migrate_skills(config_path, dry_run=False, verbose=True)
    assert count == 3

    v1_file = tmp_path / "skills.v1.json"
    assert v1_file.exists()

    with open(v1_file) as f:
        skills = json.load(f)

    assert len(skills) == 3
    assert all("skill_id" in s for s in skills)
    assert all("content" in s for s in skills)
    assert all("tier" in s for s in skills)
    assert all("metadata" in s for s in skills)


def test_skill_normalize_dict():
    skill = {"skill_id": "s1", "content": "test", "category": "web"}
    result = _normalize_skill(skill, "general")
    assert result["skill_id"] == "s1"
    assert result["content"] == "test"
    assert result["tier"] == "general"
    assert result["category"] == "web"


def test_skill_normalize_old_shape():
    """Old skills may use 'description' instead of 'content'."""
    skill = {"id": "old1", "description": "old skill text"}
    result = _normalize_skill(skill, "task_specific")
    assert result["skill_id"] == "old1"
    assert result["content"] == "old skill text"
    assert result["tier"] == "task_specific"


def test_skill_migration_dry_run(tmp_path):
    config_path = _write_config(tmp_path)
    _write_skills(tmp_path)

    count = migrate_skills(config_path, dry_run=True, verbose=False)
    assert count == 3

    v1_file = tmp_path / "skills.v1.json"
    assert not v1_file.exists()


# ── Result Materialization ───────────────────────────────────────────────


def test_result_materialization(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "completed-col", status="completed")

    # Create workspace with some files
    _ws = tmp_path.parent / "workspace" / "completed-col"
    # Can't easily create workspace relative to cwd, so just test the session part
    count = materialize_results(config_path, dry_run=False, verbose=True)
    assert count == 1

    result_file = tmp_path / "sessions" / "completed-col" / "result_v1.json"
    assert result_file.exists()

    with open(result_file) as f:
        data = json.load(f)

    assert data["colony_id"] == "completed-col"
    assert data["status"] == "completed"
    assert data["final_answer"] == "test answer"


def test_result_skips_non_completed(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "running-col", status="running")

    count = materialize_results(config_path, dry_run=False, verbose=False)
    assert count == 0


def test_result_materialization_dry_run(tmp_path):
    config_path = _write_config(tmp_path)
    _write_session(tmp_path, "dry-col", status="completed")

    count = materialize_results(config_path, dry_run=True, verbose=False)
    assert count == 1

    result_file = tmp_path / "sessions" / "dry-col" / "result_v1.json"
    assert not result_file.exists()
