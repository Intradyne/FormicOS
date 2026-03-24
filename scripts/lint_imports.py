#!/usr/bin/env python3
"""Boundary enforcer for FormicOS.

Walks all .py files in src/formicos/ and verifies that no module imports
from a layer farther from Core than itself.

Also validates that the frontend event manifest stays in sync with the
backend event manifest so new drift cannot silently grow.

Layer rules (Constitution Article 2):
  core/     -> imports NOTHING from formicos
  engine/   -> imports only from core/
  adapters/ -> imports only from core/
  surface/  -> imports from all layers

Exit 0 if all boundary checks are valid. Exit 1 with details on violations.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Define which layers each layer is allowed to import from
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "core": set(),  # core imports nothing from formicos
    "engine": {"core"},
    "adapters": {"core"},
    "surface": {"core", "engine", "adapters", "surface"},
}

LAYER_NAMES = set(ALLOWED_IMPORTS.keys())
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "formicos"
BACKEND_EVENTS_PATH = SRC_DIR / "core" / "events.py"
FRONTEND_TYPES_PATH = REPO_ROOT / "frontend" / "src" / "types.ts"


def get_layer(filepath: Path) -> str | None:
    """Extract the layer name from a file path like src/formicos/engine/foo.py."""
    parts = filepath.parts
    try:
        formicos_idx = parts.index("formicos")
        if formicos_idx + 1 < len(parts):
            candidate = parts[formicos_idx + 1]
            if candidate in LAYER_NAMES:
                return candidate
    except ValueError:
        pass
    return None


def extract_formicos_imports(filepath: Path) -> list[tuple[int, str, str]]:
    """Parse a Python file and return formicos imports as (line, layer, import)."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
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
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("formicos.")
        ):
            parts = node.module.split(".")
            if len(parts) >= 2 and parts[1] in LAYER_NAMES:
                imports.append((node.lineno, parts[1], node.module))
    return imports


def check_file(filepath: Path) -> list[str]:
    """Check a single file for layer violations. Returns list of error messages."""
    source_layer = get_layer(filepath)
    if source_layer is None:
        return []

    allowed = ALLOWED_IMPORTS[source_layer]
    violations = []

    for lineno, target_layer, full_import in extract_formicos_imports(filepath):
        if target_layer == source_layer:
            continue  # same-layer imports are always fine
        if target_layer not in allowed:
            violations.append(
                f"  {filepath}:{lineno} - {source_layer}/ imports from "
                f"{target_layer}/ ({full_import})"
            )
    return violations


def _extract_python_event_names(filepath: Path) -> list[str]:
    """Parse EVENT_TYPE_NAMES from the backend event manifest."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))

    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "EVENT_TYPE_NAMES"
                for target in node.targets
            ):
                value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "EVENT_TYPE_NAMES"
        ):
            value = node.value

        if value is None:
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            raise ValueError("EVENT_TYPE_NAMES must be a list literal")

        names: list[str] = []
        for elt in value.elts:
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                raise ValueError(
                    "EVENT_TYPE_NAMES must contain only string literals"
                )
            names.append(elt.value)
        return names

    raise ValueError("EVENT_TYPE_NAMES not found in core/events.py")


def _extract_typescript_event_names(filepath: Path) -> list[str]:
    """Parse EVENT_NAMES from frontend/src/types.ts."""
    text = filepath.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+EVENT_NAMES\s*=\s*\[(.*?)\]\s*as\s+const",
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("EVENT_NAMES not found in frontend/src/types.ts")
    return re.findall(r"'([^']+)'", match.group(1))


def check_event_manifest_parity(
    backend_events_path: Path = BACKEND_EVENTS_PATH,
    frontend_types_path: Path = FRONTEND_TYPES_PATH,
) -> list[str]:
    """Validate frontend EVENT_NAMES against backend EVENT_TYPE_NAMES."""
    violations: list[str] = []

    try:
        python_names = _extract_python_event_names(backend_events_path)
    except Exception as exc:  # noqa: BLE001
        return [f"  Could not parse backend event manifest: {exc}"]

    try:
        ts_names = _extract_typescript_event_names(frontend_types_path)
    except Exception as exc:  # noqa: BLE001
        return [f"  Could not parse frontend event manifest: {exc}"]

    if len(python_names) != len(set(python_names)):
        violations.append("  Backend EVENT_TYPE_NAMES contains duplicates.")
    if len(ts_names) != len(set(ts_names)):
        violations.append("  Frontend EVENT_NAMES contains duplicates.")

    if python_names != ts_names:
        python_only = sorted(set(python_names) - set(ts_names))
        ts_only = sorted(set(ts_names) - set(python_names))
        violations.append(
            "  Event manifest drift: frontend/src/types.ts EVENT_NAMES must match "
            "src/formicos/core/events.py EVENT_TYPE_NAMES."
        )
        if python_only:
            violations.append(f"    Python only: {python_only}")
        if ts_only:
            violations.append(f"    Frontend only: {ts_only}")
        if not python_only and not ts_only:
            violations.append("    Same members, different order.")

    return violations


def main() -> int:
    if not SRC_DIR.exists():
        print(f"Directory {SRC_DIR} not found. Run from repo root.")
        return 1

    all_violations: list[str] = []
    file_count = 0

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        file_count += 1
        all_violations.extend(check_file(py_file))

    all_violations.extend(check_event_manifest_parity())

    if all_violations:
        print(f"BOUNDARY VIOLATIONS ({len(all_violations)}):\n")
        for violation in all_violations:
            print(violation)
        print(f"\nScanned {file_count} files. {len(all_violations)} violations found.")
        return 1

    print(
        f"OK - {file_count} files scanned, no layer or event-manifest violations."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
