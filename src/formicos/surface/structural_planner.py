"""Wave 82 Track B: Structural planner — project-structure-to-planning signals.

Turns real project structure (imports, reverse deps, test companions) into
planning-grade hints for the Queen's delegation decisions. Built on top of
``code_analysis.py`` (workspace structure) and ``knowledge_graph.py``
(MODULE / DEPENDS_ON entities).

Not a new repo-map subsystem. A thin deterministic layer that answers:
- which files are structurally coupled?
- which files likely belong in the same colony?
- when is the evidence weak enough that the hint should be omitted?
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Files that match these terms in the operator message are candidates
_FILE_INDICATORS = re.compile(
    r"\.py\b|\.ts\b|\.js\b|\.go\b|\.rs\b|src/|tests/|import |module |file ",
    re.IGNORECASE,
)


def get_structural_hints(
    runtime: Any,
    workspace_id: str,
    operator_message: str,
    *,
    max_groups: int = 3,
) -> dict[str, Any]:
    """Return planning-grade structural hints from real project structure.

    Returns a dict with:
    - ``matched_files``: files mentioned or referenced in the message
    - ``coupling_pairs``: proven dependency pairs between matched files
    - ``suggested_groups``: file groupings for colony assignment
    - ``confidence``: overall confidence in the structural signal
    - ``rationale``: human-readable explanation

    Returns empty hints when evidence is too weak to be useful.
    """
    def _empty(reason: str) -> dict[str, Any]:
        return {
            "matched_files": [],
            "coupling_pairs": [],
            "suggested_groups": [],
            "confidence": 0.0,
            "rationale": "no structural signal",
            "suppression_reason": reason,
        }

    # Only analyze when message references files or modules
    if not _FILE_INDICATORS.search(operator_message):
        return _empty("no_file_indicators")

    try:
        structure = _get_workspace_structure(runtime, workspace_id)
    except Exception:
        log.debug("structural_planner.analysis_failed", workspace_id=workspace_id)
        return _empty("analysis_failed")

    if structure is None or not structure.files:
        return _empty("no_workspace_files")

    # Phase 1: Find files mentioned in the operator message
    matched = _find_mentioned_files(structure, operator_message)
    if not matched:
        return _empty("no_file_matches")

    # Phase 2: Find structural coupling between matched files
    coupling_pairs = _find_coupling_pairs(structure, matched)

    # Phase 3: Expand to neighbors for grouping
    all_relevant = set(matched)
    for f in matched:
        neighbors = structure.neighbors(f, max_hops=1)
        all_relevant.update(neighbors)

    # Phase 4: Group files by coupling clusters
    groups = _suggest_groups(structure, list(all_relevant), matched, max_groups)

    # Phase 5: Compute confidence
    confidence = _compute_confidence(matched, coupling_pairs, groups, structure)

    # Suppress weak signals
    if confidence < 0.3:
        log.debug(
            "structural_planner.low_confidence_suppressed",
            workspace_id=workspace_id,
            matched_files=len(matched),
            coupling_pairs=len(coupling_pairs),
            suggested_groups=len(groups),
            confidence=round(confidence, 2),
        )
        return _empty("low_confidence")

    rationale = _build_rationale(matched, coupling_pairs, groups, confidence)

    return {
        "matched_files": matched,
        "coupling_pairs": coupling_pairs,
        "suggested_groups": groups,
        "confidence": round(confidence, 2),
        "rationale": rationale,
        "suppression_reason": None,
    }


def _get_workspace_structure(runtime: Any, workspace_id: str) -> Any:
    """Load workspace structure from project root or library root."""
    from formicos.adapters.code_analysis import analyze_workspace  # noqa: PLC0415
    from formicos.surface.workspace_roots import (  # noqa: PLC0415
        workspace_project_root,
        workspace_runtime_root,
    )

    # Prefer bound project root over library root
    project_root = workspace_project_root(workspace_id)
    if project_root is not None and project_root.is_dir():
        ws_dir = str(project_root)
    else:
        data_dir = runtime.settings.system.data_dir
        ws_dir = str(workspace_runtime_root(data_dir, workspace_id))

    if not Path(ws_dir).is_dir():
        return None

    return analyze_workspace(ws_dir, max_files=200)


def _normalize_for_matching(text: str) -> str:
    """Normalize text for phrase-to-filename matching.

    Treats ``_``, ``-``, ``.``, ``/``, and whitespace as equivalent.
    """
    return re.sub(r"[_\-./\\\s]+", " ", text.lower()).strip()


def _find_mentioned_files(
    structure: Any,
    operator_message: str,
) -> list[str]:
    """Find workspace files referenced in the operator message.

    Supports:
    - direct path mention (``workspace_roots.py``)
    - stem mention (``runner`` -> ``runner.py``)
    - module-style mention (``formicos.engine.runner``)
    - phrase-style mention (``workspace roots`` -> ``workspace_roots.py``,
      ``plan patterns`` -> ``plan_patterns.py``)
    """
    lower = operator_message.lower()
    norm_msg = _normalize_for_matching(operator_message)
    matched: list[str] = []

    for finfo in structure.files.values():
        path = finfo.path
        path_lower = path.lower()
        stem = Path(path).stem.lower()

        # Direct path mention
        if path_lower in lower:
            matched.append(path)
            continue

        # Stem mention (e.g. "runner" matches "runner.py")
        if len(stem) >= 3 and stem in lower:
            matched.append(path)
            continue

        # Module-style mention (e.g. "formicos.engine.runner")
        module = path.replace("/", ".").replace("\\", ".")
        if module.endswith(".py"):
            module = module[:-3]
        if module.lower() in lower:
            matched.append(path)
            continue

        # Phrase-style mention (e.g. "workspace roots" -> workspace_roots.py)
        norm_stem = _normalize_for_matching(stem)
        if len(norm_stem) >= 5 and norm_stem in norm_msg:
            matched.append(path)

    return matched[:20]  # cap to avoid explosion


def _find_coupling_pairs(
    structure: Any,
    matched_files: list[str],
) -> list[dict[str, str]]:
    """Find proven dependency pairs between matched files."""
    pairs: list[dict[str, str]] = []
    matched_set = set(matched_files)

    for f in matched_files:
        # Forward deps: f imports what?
        forward = structure.dependency_graph.get(f, set())
        for dep in forward:
            if dep in matched_set and dep != f:
                pair = {"from": f, "to": dep, "type": "imports"}
                if pair not in pairs:
                    pairs.append(pair)

        # Reverse deps: what imports f?
        reverse = structure.reverse_deps.get(f, set())
        for rdep in reverse:
            if rdep in matched_set and rdep != f:
                pair = {"from": rdep, "to": f, "type": "imports"}
                if pair not in pairs:
                    pairs.append(pair)

        # Test companions
        for test_file, source_file in structure.test_companions.items():
            if source_file == f and test_file in matched_set:
                pair = {"from": test_file, "to": f, "type": "test_companion"}
                if pair not in pairs:
                    pairs.append(pair)

    return pairs[:10]  # cap


def _suggest_groups(
    structure: Any,
    all_relevant: list[str],
    primary_files: list[str],
    max_groups: int,
) -> list[dict[str, Any]]:
    """Cluster relevant files into suggested colony groupings.

    Uses a simple connected-components approach over the dependency graph.
    Each component becomes a suggested group.
    """
    if len(all_relevant) <= 1:
        if all_relevant:
            return [{"files": all_relevant, "reason": "single file"}]
        return []

    # Build adjacency for relevant files only
    adj: dict[str, set[str]] = {f: set() for f in all_relevant}
    relevant_set = set(all_relevant)

    for f in all_relevant:
        for dep in structure.dependency_graph.get(f, set()):
            if dep in relevant_set:
                adj[f].add(dep)
                adj.setdefault(dep, set()).add(f)

        for rdep in structure.reverse_deps.get(f, set()):
            if rdep in relevant_set:
                adj[f].add(rdep)
                adj.setdefault(rdep, set()).add(f)

        # Include test companions
        for test_file, source_file in structure.test_companions.items():
            if source_file == f and test_file in relevant_set:
                adj[f].add(test_file)
                adj.setdefault(test_file, set()).add(f)

    # Connected components via BFS
    visited: set[str] = set()
    components: list[list[str]] = []

    for start in all_relevant:
        if start in visited:
            continue
        component: list[str] = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        if component:
            components.append(component)

    # Sort: primary files' components first, largest first within that
    primary_set = set(primary_files)

    def _sort_key(comp: list[str]) -> tuple[int, int]:
        has_primary = any(f in primary_set for f in comp)
        return (0 if has_primary else 1, -len(comp))

    components.sort(key=_sort_key)

    groups: list[dict[str, Any]] = []
    for comp in components[:max_groups]:
        has_test = any(
            f in structure.test_companions for f in comp
        )
        reason = (
            "coupled files"
            + (" + tests" if has_test else "")
            + f" ({len(comp)} files)"
        )
        groups.append({"files": sorted(comp), "reason": reason})

    return groups


def _compute_confidence(
    matched: list[str],
    coupling_pairs: list[dict[str, str]],
    groups: list[dict[str, Any]],
    structure: Any,
) -> float:
    """Compute confidence in the structural signal.

    Higher when:
    - more matched files have proven coupling
    - groups are non-trivial (> 1 file)
    - test companions detected
    """
    if not matched:
        return 0.0

    # Base: matched-file count signal
    base = min(len(matched) / 5.0, 0.4)

    # Coupling bonus
    if coupling_pairs:
        base += min(len(coupling_pairs) / 5.0, 0.3)

    # Multi-file group bonus
    multi_file_groups = sum(1 for g in groups if len(g.get("files", [])) > 1)
    if multi_file_groups > 0:
        base += 0.2

    # Test companion bonus
    has_test = any(
        p.get("type") == "test_companion" for p in coupling_pairs
    )
    if has_test:
        base += 0.1

    return min(base, 1.0)


def _build_rationale(
    matched: list[str],
    coupling_pairs: list[dict[str, str]],
    groups: list[dict[str, Any]],
    confidence: float,
) -> str:
    """Build a concise human-readable rationale string."""
    parts: list[str] = []
    parts.append(f"{len(matched)} files matched")

    if coupling_pairs:
        import_count = sum(1 for p in coupling_pairs if p["type"] == "imports")
        test_count = sum(1 for p in coupling_pairs if p["type"] == "test_companion")
        if import_count:
            parts.append(f"{import_count} import deps")
        if test_count:
            parts.append(f"{test_count} test companions")

    parts.append(f"{len(groups)} groups suggested")
    parts.append(f"conf={confidence:.2f}")

    return "; ".join(parts)


async def reflect_structure_to_graph(
    runtime: Any,
    workspace_id: str,
) -> int:
    """Reflect project structure into the knowledge graph as MODULE entities.

    Incremental and additive: creates MODULE entities and DEPENDS_ON edges
    from real import analysis. Returns the number of edges added.
    """
    kg = getattr(runtime, "knowledge_graph", None)
    if kg is None:
        return 0

    try:
        structure = _get_workspace_structure(runtime, workspace_id)
    except Exception:
        return 0

    if structure is None or not structure.files:
        return 0

    edges_added = 0

    # Create MODULE entities for source files
    entity_ids: dict[str, str] = {}
    for finfo in structure.files.values():
        if finfo.role not in ("source", "test"):
            continue
        try:
            eid = await kg.resolve_entity(
                name=finfo.path,
                entity_type="MODULE",
                workspace_id=workspace_id,
            )
            entity_ids[finfo.path] = eid
        except Exception:
            continue

    # Create DEPENDS_ON edges from the dependency graph
    for source_file, deps in structure.dependency_graph.items():
        from_eid = entity_ids.get(source_file)
        if not from_eid:
            continue
        for dep_file in deps:
            to_eid = entity_ids.get(dep_file)
            if not to_eid:
                continue
            try:
                await kg.add_edge(
                    from_node=from_eid,
                    to_node=to_eid,
                    predicate="DEPENDS_ON",
                    workspace_id=workspace_id,
                    confidence=0.9,
                )
                edges_added += 1
            except Exception:
                continue

    log.info(
        "structural_planner.graph_reflected",
        workspace_id=workspace_id,
        modules=len(entity_ids),
        edges=edges_added,
    )
    return edges_added


__all__ = [
    "get_structural_hints",
    "reflect_structure_to_graph",
]
