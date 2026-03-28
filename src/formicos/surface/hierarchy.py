"""Knowledge hierarchy utilities — branch confidence aggregation.

Wave 67: materialized-path hierarchy on knowledge entry projections.
See ADR-049 for design rationale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore


def compute_branch_confidence(
    store: ProjectionStore,
    path_prefix: str,
    workspace_id: str = "",
) -> dict[str, Any]:
    """Aggregate Beta confidence for entries under a hierarchy branch.

    Returns ``{"alpha": float, "beta": float, "count": int, "mean": float}``.
    Sums children's evidence (subtracting the Beta(5,5) prior from each),
    re-adds a single prior, and caps effective sample size at 150.

    ESS 150 is mathematically equivalent to exponential decay with
    gamma ≈ 0.993.  Balances stability with responsiveness per production
    Thompson Sampling literature.
    """
    total_alpha = 0.0
    total_beta = 0.0
    count = 0
    for entry in store.memory_entries.values():
        if entry.get("entry_type") == "topic":
            continue  # don't count synthetic nodes
        if workspace_id and entry.get("workspace_id") != workspace_id:
            continue
        hp = entry.get("hierarchy_path", "/")
        if hp.startswith(path_prefix):
            total_alpha += entry.get("conf_alpha", 5.0) - 5.0
            total_beta += entry.get("conf_beta", 5.0) - 5.0
            count += 1
    agg_alpha = max(5.0 + total_alpha, 1.0)
    agg_beta = max(5.0 + total_beta, 1.0)
    ess = agg_alpha + agg_beta
    if ess > 150:
        scale = 150.0 / ess
        agg_alpha *= scale
        agg_beta *= scale
    mean = (
        agg_alpha / (agg_alpha + agg_beta)
        if (agg_alpha + agg_beta) > 0
        else 0.5
    )
    return {"alpha": agg_alpha, "beta": agg_beta, "count": count, "mean": mean}


def build_knowledge_tree(
    store: ProjectionStore,
    workspace_id: str,
) -> list[dict[str, Any]]:
    """Build a tree structure from memory_entries hierarchy paths.

    Returns a list of root branch dicts, each with nested ``children``.
    Each branch includes path, label, entryCount, and confidence.
    """
    # Collect all hierarchy paths for workspace entries
    path_counts: dict[str, int] = {}
    for entry in store.memory_entries.values():
        if entry.get("workspace_id") != workspace_id:
            continue
        if entry.get("entry_type") == "topic":
            continue
        hp = entry.get("hierarchy_path", "/")
        if hp and hp != "/":
            # Extract the root segment: /foo/ from /foo/ or /foo/bar/
            segments = [s for s in hp.split("/") if s]
            if segments:
                root_path = f"/{segments[0]}/"
                path_counts[root_path] = path_counts.get(root_path, 0) + 1
                # If deeper, also count the subtopic
                if len(segments) >= 2:
                    sub_path = f"/{segments[0]}/{segments[1]}/"
                    # Don't double-count in root — root counts all descendants
                    path_counts[sub_path] = path_counts.get(sub_path, 0) + 1

    # Build root branches sorted by label
    root_paths = sorted(
        {p for p in path_counts if p.count("/") == 2},
    )  # /foo/ has exactly 2 slashes

    branches: list[dict[str, Any]] = []
    for rp in root_paths:
        label = rp.strip("/")
        conf = compute_branch_confidence(store, rp, workspace_id)
        # Find children (subtopic paths under this root)
        children: list[dict[str, Any]] = []
        child_paths = sorted(
            p for p in path_counts
            if p.startswith(rp) and p != rp and p.count("/") == 3
        )
        for cp in child_paths:
            child_label = cp[len(rp):].strip("/")
            child_conf = compute_branch_confidence(store, cp, workspace_id)
            children.append({
                "path": cp,
                "label": child_label,
                "entryCount": child_conf["count"],
                "confidence": {
                    "alpha": round(child_conf["alpha"], 1),
                    "beta": round(child_conf["beta"], 1),
                    "mean": round(child_conf["mean"], 2),
                },
                "children": [],
            })

        branches.append({
            "path": rp,
            "label": label,
            "entryCount": conf["count"],
            "confidence": {
                "alpha": round(conf["alpha"], 1),
                "beta": round(conf["beta"], 1),
                "mean": round(conf["mean"], 2),
            },
            "children": children,
        })

    return branches
