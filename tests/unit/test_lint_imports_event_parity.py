from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "lint_imports.py"
_SPEC = importlib.util.spec_from_file_location("lint_imports_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _temp_manifest_dir() -> Path:
    temp_dir = _REPO_ROOT / f".lint-imports-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    return temp_dir


def test_event_manifest_parity_passes_for_matching_files() -> None:
    temp_dir = _temp_manifest_dir()
    backend = temp_dir / "events.py"
    backend.write_text(
        'EVENT_TYPE_NAMES: list[str] = ["Alpha", "Beta"]\n',
        encoding="utf-8",
    )
    frontend = temp_dir / "types.ts"
    frontend.write_text(
        "export const EVENT_NAMES = ['Alpha', 'Beta'] as const;\n",
        encoding="utf-8",
    )

    try:
        violations = _MODULE.check_event_manifest_parity(backend, frontend)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert violations == []


def test_event_manifest_parity_detects_drift() -> None:
    temp_dir = _temp_manifest_dir()
    backend = temp_dir / "events.py"
    backend.write_text(
        'EVENT_TYPE_NAMES: list[str] = ["Alpha", "Beta"]\n',
        encoding="utf-8",
    )
    frontend = temp_dir / "types.ts"
    frontend.write_text(
        "export const EVENT_NAMES = ['Alpha', 'Gamma'] as const;\n",
        encoding="utf-8",
    )

    try:
        violations = _MODULE.check_event_manifest_parity(backend, frontend)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert violations
    assert any("Event manifest drift" in msg for msg in violations)
    assert any("Python only: ['Beta']" in msg for msg in violations)
    assert any("Frontend only: ['Gamma']" in msg for msg in violations)
