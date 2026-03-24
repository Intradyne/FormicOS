"""Layer boundary tests — verify no backward imports across architecture layers.

Reimplements the logic from scripts/lint_imports.py as a pytest test so it
runs as part of the standard test suite (Wave 07).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src" / "formicos"

ALLOWED_IMPORTS: dict[str, set[str]] = {
    "core": set(),
    "engine": {"core"},
    "adapters": {"core"},
    "surface": {"core", "engine", "adapters", "surface"},
}

LAYER_NAMES = set(ALLOWED_IMPORTS.keys())


def _get_layer(filepath: Path) -> str | None:
    parts = filepath.parts
    try:
        idx = parts.index("formicos")
        if idx + 1 < len(parts) and parts[idx + 1] in LAYER_NAMES:
            return parts[idx + 1]
    except ValueError:
        pass
    return None


def _extract_formicos_imports(filepath: Path) -> list[tuple[int, str, str]]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("formicos."):
                    parts = alias.name.split(".")
                    if len(parts) >= 2 and parts[1] in LAYER_NAMES:
                        imports.append((node.lineno, parts[1], alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("formicos."):
                parts = node.module.split(".")
                if len(parts) >= 2 and parts[1] in LAYER_NAMES:
                    imports.append((node.lineno, parts[1], node.module))
    return imports


def _find_violations() -> list[str]:
    violations: list[str] = []
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        source_layer = _get_layer(py_file)
        if source_layer is None:
            continue
        allowed = ALLOWED_IMPORTS[source_layer]
        for lineno, target_layer, full_import in _extract_formicos_imports(py_file):
            if target_layer != source_layer and target_layer not in allowed:
                violations.append(
                    f"{py_file}:{lineno} — {source_layer}/ imports from "
                    f"{target_layer}/ ({full_import})"
                )
    return violations


class TestLayerBoundaries:
    def test_no_backward_imports(self) -> None:
        violations = _find_violations()
        assert violations == [], (
            f"Layer boundary violations found:\n" + "\n".join(violations)
        )

    def test_core_imports_nothing_from_formicos(self) -> None:
        core_dir = SRC_DIR / "core"
        for py_file in sorted(core_dir.rglob("*.py")):
            imports = _extract_formicos_imports(py_file)
            for lineno, target_layer, full_import in imports:
                if target_layer != "core":
                    raise AssertionError(
                        f"core/ must not import from {target_layer}/: "
                        f"{py_file}:{lineno} ({full_import})"
                    )

    def test_engine_imports_only_core(self) -> None:
        engine_dir = SRC_DIR / "engine"
        if not engine_dir.exists():
            return
        for py_file in sorted(engine_dir.rglob("*.py")):
            imports = _extract_formicos_imports(py_file)
            for lineno, target_layer, full_import in imports:
                if target_layer not in ("core", "engine"):
                    raise AssertionError(
                        f"engine/ must only import from core/: "
                        f"{py_file}:{lineno} ({full_import})"
                    )

    def test_adapters_imports_only_core(self) -> None:
        adapters_dir = SRC_DIR / "adapters"
        if not adapters_dir.exists():
            return
        for py_file in sorted(adapters_dir.rglob("*.py")):
            imports = _extract_formicos_imports(py_file)
            for lineno, target_layer, full_import in imports:
                if target_layer not in ("core", "adapters"):
                    raise AssertionError(
                        f"adapters/ must only import from core/: "
                        f"{py_file}:{lineno} ({full_import})"
                    )
