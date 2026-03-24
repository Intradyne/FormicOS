"""Lightweight structural analysis for workspace code trees (Wave 42 Pillar 1).

Extracts import/dependency relationships, top-level function/class inventory,
and rough file-role classification from workspace files.  Deliberately
lightweight: Python uses stdlib ``ast``, JS/TS/Go use regex.

Known gaps (accepted for v1):
- Dynamic imports (``importlib``, ``require()`` with variables)
- Conditional imports behind ``if TYPE_CHECKING``
- Macro-based or template-literal includes
- Go ``import .`` (dot imports)
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

FileRole = str  # "source" | "test" | "config" | "docs" | "unknown"

_CONFIG_EXTS: frozenset[str] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
})
_DOC_EXTS: frozenset[str] = frozenset({
    ".md", ".rst", ".txt", ".adoc",
})
_SOURCE_EXTS: frozenset[str] = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp",
})

# Max file size to parse (256 KB) — skip huge generated files.
_MAX_FILE_BYTES = 256 * 1024


@dataclass(frozen=True)
class FileInfo:
    """Structural facts about a single source file."""

    path: str
    role: FileRole
    imports: tuple[str, ...]  # resolved import targets (module or file paths)
    definitions: tuple[str, ...]  # top-level function/class names
    language: str  # "python" | "javascript" | "typescript" | "go" | "unknown"


@dataclass
class WorkspaceStructure:
    """Workspace-scoped structural index (not stored in knowledge substrate)."""

    files: dict[str, FileInfo] = field(default_factory=dict)
    # Forward dependency graph: file_path → set of imported file_paths
    dependency_graph: dict[str, set[str]] = field(default_factory=dict)
    # Reverse dependency graph: file_path → set of files that import it
    reverse_deps: dict[str, set[str]] = field(default_factory=dict)
    # Test companion mapping: test_file → likely source file
    test_companions: dict[str, str] = field(default_factory=dict)

    def neighbors(self, path: str, max_hops: int = 1) -> set[str]:
        """Return files within ``max_hops`` dependency distance of *path*."""
        visited: set[str] = set()
        frontier = {path}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for p in frontier:
                if p in visited:
                    continue
                visited.add(p)
                next_frontier.update(self.dependency_graph.get(p, set()))
                next_frontier.update(self.reverse_deps.get(p, set()))
            frontier = next_frontier - visited
        visited.update(frontier)
        visited.discard(path)
        return visited

    def relevant_context(
        self,
        target_files: list[str],
        *,
        max_tokens: int = 1500,
    ) -> str:
        """Budget-aware structural context string for agent injection.

        Ranks facts by dependency distance from *target_files*, then
        truncates to approximately *max_tokens* (assuming ~4 chars/token).
        """
        if not target_files or not self.files:
            return ""

        char_budget = max_tokens * 4
        lines: list[str] = []

        # Tier 1: target files themselves
        for tf in target_files:
            info = self.files.get(tf)
            if info:
                lines.append(_format_file_info(info))

        # Tier 2: direct dependency neighbors (1-hop)
        neighbor_set: set[str] = set()
        for tf in target_files:
            neighbor_set.update(self.neighbors(tf, max_hops=1))
        neighbor_set -= set(target_files)
        for nb in sorted(neighbor_set):
            info = self.files.get(nb)
            if info:
                lines.append(_format_file_info(info))

        # Tier 3: test companions
        for tf in target_files:
            companion = self.test_companions.get(tf)
            if companion and companion not in neighbor_set and companion not in target_files:
                info = self.files.get(companion)
                if info:
                    lines.append(f"  test: {_format_file_info(info)}")

        # Truncate to budget
        result_parts: list[str] = []
        used = 0
        for line in lines:
            if used + len(line) > char_budget:
                break
            result_parts.append(line)
            used += len(line) + 1  # +1 for newline

        return "\n".join(result_parts)

    def to_dict(self) -> dict[str, Any]:
        """Serializable summary for debugging / eval."""
        return {
            "file_count": len(self.files),
            "dependency_edges": sum(len(v) for v in self.dependency_graph.values()),
            "test_companions": len(self.test_companions),
        }


def _format_file_info(info: FileInfo) -> str:
    """One-line summary of a file's structure."""
    defs = ", ".join(info.definitions[:8])
    imports_str = ", ".join(info.imports[:6])
    parts = [f"{info.path} ({info.role})"]
    if defs:
        parts.append(f"defs=[{defs}]")
    if imports_str:
        parts.append(f"imports=[{imports_str}]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_workspace(
    workspace_dir: str,
    *,
    max_files: int = 500,
) -> WorkspaceStructure:
    """Analyze workspace tree and return structural index.

    Walks *workspace_dir*, parses source files, and builds dependency/test
    companion graphs.  Stays under *max_files* to bound cost.
    """
    structure = WorkspaceStructure()
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return structure

    file_list = _collect_files(workspace_dir, max_files=max_files)
    py_modules: dict[str, str] = {}  # dotted module name → file path

    # First pass: parse all files
    for rel_path, abs_path in file_list:
        info = _analyze_file(rel_path, abs_path)
        if info:
            structure.files[rel_path] = info
            if info.language == "python":
                mod = _path_to_module(rel_path)
                if mod:
                    py_modules[mod] = rel_path

    # Second pass: resolve imports to file paths and build dependency graph
    for rel_path, info in structure.files.items():
        resolved: set[str] = set()
        for imp in info.imports:
            target = _resolve_import(imp, rel_path, info.language, structure.files, py_modules)
            if target and target != rel_path:
                resolved.add(target)
        structure.dependency_graph[rel_path] = resolved
        for dep in resolved:
            structure.reverse_deps.setdefault(dep, set()).add(rel_path)

    # Third pass: test companion detection
    for rel_path, info in structure.files.items():
        if info.role == "test":
            companion = _find_test_companion(rel_path, info, structure.files)
            if companion:
                structure.test_companions[rel_path] = companion

    log.debug(
        "code_analysis.done",
        files=len(structure.files),
        edges=sum(len(v) for v in structure.dependency_graph.values()),
        companions=len(structure.test_companions),
    )
    return structure


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", "vendor",
})


def _collect_files(
    root: str,
    max_files: int,
) -> list[tuple[str, str]]:
    """Collect (relative_path, absolute_path) pairs up to *max_files*."""
    result: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if len(result) >= max_files:
                return result
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
            result.append((rel_path, abs_path))
    return result


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


def _analyze_file(rel_path: str, abs_path: str) -> FileInfo | None:
    """Parse a single file and extract structural facts."""
    ext = os.path.splitext(rel_path)[1].lower()
    role = _classify_role(rel_path, ext)
    language = _detect_language(ext)

    if language == "unknown":
        if role in ("config", "docs"):
            return FileInfo(
                path=rel_path, role=role, imports=(), definitions=(),
                language=language,
            )
        return None

    try:
        size = os.path.getsize(abs_path)
        if size > _MAX_FILE_BYTES:
            return FileInfo(
                path=rel_path, role=role, imports=(), definitions=(),
                language=language,
            )
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        return None

    if language == "python":
        imports, defs = _parse_python(source)
    elif language in ("javascript", "typescript"):
        imports, defs = _parse_js_ts(source)
    elif language == "go":
        imports, defs = _parse_go(source)
    else:
        imports, defs = [], []

    return FileInfo(
        path=rel_path,
        role=role,
        imports=tuple(imports),
        definitions=tuple(defs),
        language=language,
    )


def _classify_role(rel_path: str, ext: str) -> FileRole:
    """Classify file role from path and extension."""
    basename = os.path.basename(rel_path).lower()
    parts = rel_path.lower().replace("\\", "/").split("/")

    # Test detection
    if ext in _SOURCE_EXTS:
        if basename.startswith("test_") or basename.endswith("_test" + ext):
            return "test"
        if any(p in ("tests", "test", "__tests__", "spec") for p in parts):
            return "test"
        if basename.endswith(".test" + ext) or basename.endswith(".spec" + ext):
            return "test"

    if ext in _CONFIG_EXTS:
        return "config"
    if ext in _DOC_EXTS:
        return "docs"
    if ext in _SOURCE_EXTS:
        return "source"
    return "unknown"


def _detect_language(ext: str) -> str:
    """Map file extension to language identifier."""
    lang_map: dict[str, str] = {
        ".py": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".go": "go",
    }
    return lang_map.get(ext, "unknown")


# ---------------------------------------------------------------------------
# Python analysis (stdlib ast)
# ---------------------------------------------------------------------------


def _parse_python(source: str) -> tuple[list[str], list[str]]:
    """Extract imports and top-level definitions from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []

    imports: list[str] = []
    definitions: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            definitions.append(f"class {node.name}")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            definitions.append(f"def {node.name}")

    return imports, definitions


# ---------------------------------------------------------------------------
# JS/TS analysis (regex)
# ---------------------------------------------------------------------------

# import ... from "module"
_JS_IMPORT_FROM = re.compile(
    r"""(?:^|\n)\s*import\s+.*?\s+from\s+['"]([^'"]+)['"]""",
    re.DOTALL,
)
# import "module" (side-effect)
_JS_IMPORT_BARE = re.compile(
    r"""(?:^|\n)\s*import\s+['"]([^'"]+)['"]""",
)
# const X = require("module")
_JS_REQUIRE = re.compile(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)
# export ... from "module"
_JS_EXPORT_FROM = re.compile(
    r"""(?:^|\n)\s*export\s+.*?\s+from\s+['"]([^'"]+)['"]""",
    re.DOTALL,
)
# function/class/const declarations
_JS_FUNC = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)""",
)
_JS_CLASS = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?class\s+(\w+)""",
)
_JS_CONST_ARROW = re.compile(
    r"""(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(""",
)


def _parse_js_ts(source: str) -> tuple[list[str], list[str]]:
    """Extract imports and definitions from JS/TS source via regex."""
    imports: list[str] = []
    for pat in (_JS_IMPORT_FROM, _JS_IMPORT_BARE, _JS_REQUIRE, _JS_EXPORT_FROM):
        imports.extend(pat.findall(source))

    definitions: list[str] = []
    for m in _JS_FUNC.finditer(source):
        definitions.append(f"function {m.group(1)}")
    for m in _JS_CLASS.finditer(source):
        definitions.append(f"class {m.group(1)}")
    for m in _JS_CONST_ARROW.finditer(source):
        definitions.append(f"const {m.group(1)}")

    return imports, definitions


# ---------------------------------------------------------------------------
# Go analysis (regex)
# ---------------------------------------------------------------------------

_GO_IMPORT_SINGLE = re.compile(
    r"""(?:^|\n)\s*import\s+['"]([^'"]+)['"]""",
)
_GO_IMPORT_BLOCK = re.compile(
    r"""import\s*\((.*?)\)""",
    re.DOTALL,
)
_GO_IMPORT_LINE = re.compile(
    r"""['"]([^'"]+)['"]""",
)
_GO_FUNC = re.compile(
    r"""(?:^|\n)\s*func\s+(?:\([^)]*\)\s+)?(\w+)""",
)
_GO_TYPE = re.compile(
    r"""(?:^|\n)\s*type\s+(\w+)\s+(?:struct|interface)""",
)


def _parse_go(source: str) -> tuple[list[str], list[str]]:
    """Extract imports and definitions from Go source via regex."""
    imports: list[str] = []
    imports.extend(_GO_IMPORT_SINGLE.findall(source))
    for block_match in _GO_IMPORT_BLOCK.finditer(source):
        block = block_match.group(1)
        imports.extend(_GO_IMPORT_LINE.findall(block))

    definitions: list[str] = []
    for m in _GO_FUNC.finditer(source):
        definitions.append(f"func {m.group(1)}")
    for m in _GO_TYPE.finditer(source):
        definitions.append(f"type {m.group(1)}")

    return imports, definitions


# ---------------------------------------------------------------------------
# Import resolution
# ---------------------------------------------------------------------------


def _path_to_module(rel_path: str) -> str:
    """Convert ``src/formicos/core/types.py`` → ``formicos.core.types``."""
    path = rel_path.replace("\\", "/")
    if path.endswith("/__init__.py"):
        path = path[:-12]
    elif path.endswith(".py"):
        path = path[:-3]
    else:
        return ""
    # Strip common src/ prefix
    if path.startswith("src/"):
        path = path[4:]
    return path.replace("/", ".")


def _resolve_import(
    imp: str,
    source_file: str,
    language: str,
    all_files: dict[str, FileInfo],
    py_modules: dict[str, str],
) -> str | None:
    """Try to resolve an import string to a workspace file path."""
    if language == "python":
        # Exact module match
        if imp in py_modules:
            return py_modules[imp]
        # Try parent package (from foo.bar import X → foo.bar)
        parts = imp.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in py_modules:
                return py_modules[candidate]
        return None

    if language in ("javascript", "typescript"):
        if not imp.startswith("."):
            return None  # external package
        source_dir = os.path.dirname(source_file)
        candidate = os.path.normpath(os.path.join(source_dir, imp)).replace("\\", "/")
        # Try common extensions
        for ext in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
            full = candidate + ext
            if full in all_files:
                return full
        return None

    if language == "go":
        # Go imports are package paths — match last segment to directory names
        pkg = imp.rsplit("/", 1)[-1] if "/" in imp else imp
        for fpath in all_files:
            if fpath.endswith(".go"):
                parts = fpath.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[-2] == pkg:
                    return fpath
        return None

    return None


def _find_test_companion(
    test_path: str,
    test_info: FileInfo,
    all_files: dict[str, FileInfo],
) -> str | None:
    """Find likely source companion for a test file.

    Uses naming heuristic + import verification.
    """
    basename = os.path.basename(test_path)
    ext = os.path.splitext(basename)[1]

    # Naming heuristic: test_foo.py → foo.py, foo_test.go → foo.go
    candidates: list[str] = []
    if basename.startswith("test_"):
        source_name = basename[5:]
        candidates.append(source_name)
    if basename.endswith("_test" + ext):
        source_name = basename[: -len("_test" + ext)] + ext
        candidates.append(source_name)
    if basename.endswith(".test" + ext):
        source_name = basename[: -len(".test" + ext)] + ext
        candidates.append(source_name)
    if basename.endswith(".spec" + ext):
        source_name = basename[: -len(".spec" + ext)] + ext
        candidates.append(source_name)

    # Search workspace files for matching source names
    best: str | None = None
    for fpath, finfo in all_files.items():
        if finfo.role != "source":
            continue
        fname = os.path.basename(fpath)
        if fname in candidates:
            # Verify via imports if possible
            if _imports_overlap(test_info, fpath):
                return fpath
            if best is None:
                best = fpath

    return best


def _imports_overlap(test_info: FileInfo, source_path: str) -> bool:
    """Check if the test file imports the candidate source."""
    source_mod = _path_to_module(source_path)
    if not source_mod:
        return False
    return any(source_mod in imp or imp in source_mod for imp in test_info.imports)
