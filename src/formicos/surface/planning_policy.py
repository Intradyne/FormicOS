"""Consolidated planning policy decision (Wave 84.5 Track A, Wave 87 Track C).

Wraps the scattered routing classifiers (``classify_complexity``,
``_looks_like_colony_work``, ``_prefer_single_colony_route``) and
playbook / capability signals into one decision object.

Wave 87 adds a capability-mode ladder above the colony-routing level:
``reply`` → ``inspect`` → ``edit`` → ``execute`` → ``host`` → ``operate``
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Capability mode: which class of instrument the Queen should reach for.
CapabilityMode = str  # "reply" | "inspect" | "edit" | "execute" | "host" | "operate"

# Keywords / patterns used to classify capability mode.
_INSPECT_KEYWORDS = frozenset({
    "status", "show", "list", "what", "how many", "check", "look",
    "describe", "explain", "where", "which", "display",
})
_EDIT_KEYWORDS = frozenset({
    "fix", "patch", "edit", "rename", "update", "change", "modify",
    "add a", "remove", "delete", "replace", "write",
})
_EXECUTE_KEYWORDS = frozenset({
    "implement", "build", "create", "refactor", "redesign", "test",
    "audit", "review", "analyze", "research", "benchmark", "migrate",
    "spawn", "colony", "parallel", "delegate",
})
_HOST_KEYWORDS = frozenset({
    "dashboard", "panel", "monitor", "daily", "addon", "hosted",
    "recurring", "living",
})
_OPERATE_KEYWORDS = frozenset({
    "integrate", "deploy", "persistent", "service", "webhook",
    "schedule", "watch", "continuous",
})


@dataclass(frozen=True)
class PlanningDecision:
    """Consolidated routing decision for a Queen turn."""

    task_class: str
    complexity: str  # "simple" | "complex"
    route: str  # "fast_path" | "single_colony" | "parallel_dag"
    capability_mode: CapabilityMode = "execute"
    playbook_hint: str | None = None
    behavior_flags: dict[str, bool] = field(default_factory=dict)
    confidence: float = 0.5


def decide_planning_route(
    message: str,
    *,
    model_addr: str = "",
    active_colonies: int = 0,
) -> PlanningDecision:
    """Resolve the planning route from all available classifiers.

    Calls ``classify_task``, ``classify_complexity``,
    ``_prefer_single_colony_route``, and ``get_decomposition_hints``
    internally and resolves disagreements with explicit precedence.
    """
    # Import existing classifiers
    from formicos.surface.queen_runtime import (  # noqa: PLC0415
        _looks_like_colony_work,
        _prefer_single_colony_route,
        classify_complexity,
    )

    # Task classification
    task_class = ""
    try:
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415
        task_class, _ = classify_task(message)
    except (ImportError, AttributeError):
        pass

    # Complexity
    complexity = classify_complexity(message)

    # Playbook hint
    playbook_hint: str | None = None
    try:
        from formicos.engine.playbook_loader import (  # noqa: PLC0415
            get_decomposition_hints,
        )
        playbook_hint = get_decomposition_hints(message) or None
    except (ImportError, AttributeError):
        pass

    # Behavior flags from capability profiles
    behavior_flags: dict[str, bool] = {}
    if model_addr:
        behavior_flags = _load_behavior_flags(model_addr)

    # Route decision with explicit precedence
    confidence = 0.5

    colony_work = _looks_like_colony_work(message)

    if not colony_work:
        # Not colony work → fast_path regardless of complexity
        route = "fast_path"
        confidence = 0.9
    elif _prefer_single_colony_route(message):
        route = "single_colony"
        confidence = 0.8
    elif complexity == "complex":
        route = "parallel_dag"
        confidence = 0.7
    else:
        route = "single_colony"
        confidence = 0.6

    # Playbook override: only upgrade single_colony → parallel_dag when
    # the playbook explicitly suggests 3+ colonies AND the route was NOT
    # determined by the high-confidence single-colony preference (which
    # means the task is simple + focused). Without this guard, every
    # playbook hint containing "colonies" would override fast-path tasks.
    _playbook_suggests_multi = (
        playbook_hint
        and any(f"{n}-" in playbook_hint or f"{n} col" in playbook_hint for n in "3456789")
    )
    if (
        _playbook_suggests_multi
        and route == "single_colony"
        and confidence < 0.8  # don't override high-confidence single preference
    ):
        route = "parallel_dag"
        confidence = min(confidence, 0.6)

    capability_mode = _classify_capability_mode(message, colony_work, complexity)

    return PlanningDecision(
        task_class=task_class,
        complexity=complexity,
        route=route,
        capability_mode=capability_mode,
        playbook_hint=playbook_hint,
        behavior_flags=behavior_flags,
        confidence=confidence,
    )


def _classify_capability_mode(
    message: str,
    colony_work: bool,
    complexity: str,
) -> CapabilityMode:
    """Classify the operator message into a capability mode on the durability ladder."""
    lower = message.lower()

    # Operate: persistent + integration-heavy
    if any(kw in lower for kw in _OPERATE_KEYWORDS):
        return "operate"

    # Host: durable operator-facing capability (dashboard, addon)
    if any(kw in lower for kw in _HOST_KEYWORDS):
        return "host"

    # Execute: colony work (already classified upstream)
    if colony_work and complexity == "complex":
        return "execute"

    # Edit: direct bounded workspace mutations
    if any(kw in lower for kw in _EDIT_KEYWORDS):
        if colony_work:
            return "execute"
        return "edit"

    # Inspect: status/search/read queries
    if any(kw in lower for kw in _INSPECT_KEYWORDS):
        return "inspect"

    # Execute: colony work at simple complexity
    if colony_work:
        return "execute"

    # Default: reply (conversational, no tool pressure)
    return "reply"


def _load_behavior_flags(model_addr: str) -> dict[str, bool]:
    """Load static behavior flags from capability profiles."""
    try:
        from formicos.surface.capability_profiles import (  # noqa: PLC0415
            _load_profiles,  # pyright: ignore[reportPrivateUsage]
        )
        profiles = _load_profiles()
        # Try full address match, then short alias
        short = model_addr.split("/")[-1] if "/" in model_addr else model_addr
        for key in (model_addr, short):
            profile = profiles.get(key, {})
            behavior = profile.get("behavior", {})
            if behavior:
                return {k: bool(v) for k, v in behavior.items()}
    except (ImportError, AttributeError):
        pass
    return {}
