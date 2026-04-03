"""Reviewed-plan normalization and validation (Wave 83 Track A).

Pure helpers that transform a UI-edited plan preview into the
``spawn_parallel`` input shape, then validate it against the real
execution contract. Used by both ``validate_reviewed_plan`` (dry-run)
and ``confirm_reviewed_plan`` (dispatch).
"""

from __future__ import annotations

from typing import Any

_DEFAULT_MAX_ROUNDS = 8
_DEFAULT_BUDGET_LIMIT = 2.0


def normalize_preview(preview: dict[str, Any]) -> dict[str, Any]:
    """Convert a UI preview payload into ``spawn_parallel`` input shape.

    Preserves operator edits. Fills defaults only when absent.
    Does NOT hardcode ``input_from = depends_on`` — they are kept
    semantically separate.
    """
    task_previews: list[dict[str, Any]] = preview.get("taskPreviews", [])
    groups: list[dict[str, Any]] = preview.get("groups", [])

    tasks: list[dict[str, Any]] = []
    for i, tp in enumerate(task_previews):
        depends_on = tp.get("depends_on", [])
        input_from = tp.get("input_from", tp.get("inputFrom", []))

        tasks.append({
            "task_id": tp.get("task_id", f"task-{i}"),
            "task": tp.get("task", ""),
            "caste": tp.get("caste", "coder"),
            "strategy": tp.get("strategy", "sequential"),
            "max_rounds": tp.get("max_rounds", tp.get("maxRounds", _DEFAULT_MAX_ROUNDS)),
            "budget_limit": tp.get(
                "budget_limit", tp.get("budgetLimit", _DEFAULT_BUDGET_LIMIT),
            ),
            "target_files": tp.get("target_files", tp.get("targetFiles", [])),
            "expected_outputs": tp.get(
                "expected_outputs", tp.get("expectedOutputs", []),
            ),
            "depends_on": depends_on,
            "input_from": input_from if input_from else depends_on,
        })

    return {
        "reasoning": preview.get("reasoning", "Operator-reviewed plan"),
        "tasks": tasks,
        "parallel_groups": [g.get("taskIds", g.get("task_ids", [])) for g in groups],
        "estimated_total_cost": preview.get("estimatedCost", 0.0),
        "knowledge_gaps": preview.get("knowledgeGaps", []),
    }


def validate_plan(
    normalized: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Validate a normalized plan against the execution contract.

    Returns ``(errors, warnings)`` where errors are blocking and
    warnings are informational.
    """
    errors: list[str] = []
    warnings: list[str] = []

    tasks: list[dict[str, Any]] = normalized.get("tasks", [])
    groups: list[list[str]] = normalized.get("parallel_groups", [])

    if not tasks:
        errors.append("Plan has no tasks.")
        return errors, warnings

    if not groups:
        errors.append("Plan has no parallel groups.")
        return errors, warnings

    # --- Task ID validation ---
    task_ids = [t.get("task_id", "") for t in tasks]
    task_id_set = set(task_ids)

    if "" in task_id_set:
        errors.append("One or more tasks have empty task_id.")

    if len(task_ids) != len(task_id_set):
        dupes = [tid for tid in task_ids if task_ids.count(tid) > 1]
        errors.append(f"Duplicate task IDs: {sorted(set(dupes))}")

    # --- Group structure validation ---
    all_group_ids: set[str] = set()
    for gi, group in enumerate(groups):
        if not group:
            errors.append(f"Group {gi} is empty.")
        for tid in group:
            if tid in all_group_ids:
                errors.append(f"Task '{tid}' appears in multiple groups.")
            all_group_ids.add(tid)

    # Tasks not in any group
    orphaned = task_id_set - all_group_ids
    if orphaned:
        errors.append(f"Tasks not in any group: {sorted(orphaned)}")

    # Group references to nonexistent tasks
    phantom = all_group_ids - task_id_set
    if phantom:
        errors.append(f"Groups reference nonexistent tasks: {sorted(phantom)}")

    # --- Dependency validation ---
    # Build group index: task_id -> group_index
    group_index: dict[str, int] = {}
    for gi, group in enumerate(groups):
        for tid in group:
            group_index[tid] = gi

    for task in tasks:
        tid = task.get("task_id", "")
        deps = task.get("depends_on", [])
        for dep in deps:
            if dep not in task_id_set:
                errors.append(f"Task '{tid}' depends on nonexistent '{dep}'.")
            elif dep == tid:
                errors.append(f"Task '{tid}' depends on itself.")
            elif tid in group_index and dep in group_index:
                dep_group = group_index[dep]
                task_group = group_index[tid]
                if dep_group >= task_group:
                    errors.append(
                        f"Task '{tid}' (group {task_group}) depends on "
                        f"'{dep}' (group {dep_group}), violating group order.",
                    )

    # Cycle detection via topological sort
    if not errors:
        adj: dict[str, list[str]] = {t.get("task_id", ""): [] for t in tasks}
        in_degree: dict[str, int] = {t.get("task_id", ""): 0 for t in tasks}
        for task in tasks:
            tid = task.get("task_id", "")
            for dep in task.get("depends_on", []):
                if dep in adj:
                    adj[dep].append(tid)
                    in_degree[tid] = in_degree.get(tid, 0) + 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(tasks):
            errors.append("Dependency cycle detected in the plan.")

    # --- File ownership warnings ---
    file_owners: dict[str, list[str]] = {}
    for task in tasks:
        tid = task.get("task_id", "")
        for f in task.get("target_files", []):
            file_owners.setdefault(f, []).append(tid)
    for f, owners in file_owners.items():
        if len(owners) > 1:
            warnings.append(
                f"File '{f}' targeted by multiple tasks: {owners}",
            )

    # --- input_from vs depends_on coherence ---
    for task in tasks:
        tid = task.get("task_id", "")
        deps = set(task.get("depends_on", []))
        inputs = set(task.get("input_from", []))
        if deps and not inputs:
            warnings.append(
                f"Task '{tid}' has depends_on but no input_from. "
                f"Data provenance may be implicit.",
            )

    # --- Empty task text ---
    for task in tasks:
        if not task.get("task", "").strip():
            warnings.append(f"Task '{task.get('task_id', '?')}' has empty text.")

    return errors, warnings
