"""Queen deterministic intent fallback parser (Wave 13).

When the primary tool-call path fails (local model produces prose instead of
structured tool calls), this parser extracts directives from the Queen's
natural language output.

Two-pass architecture:

1. **Regex** — pattern matching for the 4 core directives (SPAWN, KILL,
   REDIRECT, APOPTOSIS).  Cheap, deterministic, zero-latency.
2. **Gemini Flash classification** — only runs when regex finds nothing.
   500ms timeout, same ``gemini/gemini-2.5-flash`` endpoint as Queen naming
   (Wave 11).  Returns ``None`` on timeout or parse failure.

Emits identical action dicts to the tool-call path so the downstream
``_execute_tool`` flow works unchanged.

Lives in adapters/ — imports only core/.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns — built from real Qwen3-30B-A3B failure outputs
# ---------------------------------------------------------------------------

_SPAWN_RE = re.compile(
    r"(?i)(?:"
    # "Let's spawn / I'll create / We should launch ..."
    r"(?:let(?:['\u2019]s|\s+us)?|I(?:['\u2019]ll|\s+will)?|we\s+should|going\s+to|I\s+(?:want|need)\s+to|I\s+recommend)\s+"
    r"(?:spawn|create|start|launch|kick\s+off|set\s+up|initiate|begin|deploy)"
    # "Spawning / Creating ..."  (gerund form)
    r"|(?:spawning|creating|starting|launching|setting\s+up|initiating|deploying)"
    r")\s+"
    r"(?:a\s+)?(?:new\s+)?(?:colony|team|task|worker|group)\s+"
    r"(?:for|to|targeting|focused\s+on|that\s+(?:will|can|should))\s+"
    r"(.+?)(?:\.\s|\.$|$)",
    re.DOTALL,
)
_SPAWN_TOOL_TASK_RE = re.compile(
    r"(?is)\bspawn_colony\b.*?\btask\s*[:=]\s*(?:\"([^\"]+)\"|'([^']+)'|([^,\n.]+))"
)
_SPAWN_TOOL_PROSE_RE = re.compile(
    r"(?is)\bspawn_colony\b.*?(?:"
    r"(?:create|spawn|start|launch|kick\s+off|set\s+up|initiate|begin)\s+"
    r"(?:a\s+)?(?:new\s+)?(?:colony|team|task|worker|group)\s+"
    r")?"
    r"(?:for|to)\s+(.+?)(?:\.\s|\.$|$)",
    re.DOTALL,
)
_PREVIEW_TASK_LINE_RE = re.compile(r"(?im)^\s*Task:\s*(.+)$")
_PREVIEW_TEAM_LINE_RE = re.compile(r"(?im)^\s*Team:\s*(.+)$")
_PREVIEW_STRATEGY_LINE_RE = re.compile(r"(?im)^\s*Strategy:\s*(stigmergic|sequential)\s*$")
_PREVIEW_ROUNDS_LINE_RE = re.compile(r"(?im)^\s*Rounds:\s*(\d+)\s*$")
_PREVIEW_BUDGET_LINE_RE = re.compile(
    r"(?im)^\s*Budget:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*$"
)
_PREVIEW_ROUNDS_BUDGET_LINE_RE = re.compile(
    r"(?im)^\s*Rounds:\s*(\d+)\s*,\s*Budget:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*$"
)
_PREVIEW_TEAM_SLOT_RE = re.compile(
    r"(?i)\b(coder|reviewer|researcher|archivist)\b"
    r"(?:\s*\(\s*(light|standard|heavy|flash)?"
    r"(?:\s*,\s*(\d+)\s*agent(?:s)?)?[^)]*\))?"
    r"(?:x(\d+))?"
)

_KILL_RE = re.compile(
    r"(?i)(?:"
    r"(?:let(?:['\u2019]s|\s+us)?|I(?:['\u2019]ll|\s+will)?|we\s+should|going\s+to)?\s*"
    r"(?:kill|terminate|stop|abort|shut(?:\s+)?down|cancel)"
    r")\s+"
    r"(?:the\s+)?(?:colony\s+)?([a-zA-Z0-9_-]+)",
)

_REDIRECT_RE = re.compile(
    r"(?i)(?:redirect|refocus|pivot|change|repoint)\s+"
    r"(?:the\s+)?(?:colony\s+)?([a-zA-Z0-9_-]+)\s+"
    r"(?:to(?:ward|wards)?|on(?:to)?)\s+"
    r"(.+?)(?:\.\s|\.$|$)",
    re.DOTALL,
)

_APOPTOSIS_RE = re.compile(
    r"(?i)(?:colony\s+)?([a-zA-Z0-9_-]+)\s+"
    r"(?:should|can|is\s+ready\s+to|has\s+finished|appears?\s+to\s+be\s+(?:done|complete))\s*"
    r"(?:self[- ]?terminate|complete|finish|wrap\s+up"
    r"|shut\s+down|be\s+(?:killed|terminated|stopped))",
)

_DELIBERATION_RE = re.compile(
    r"(?i)(?:"
    r"(?:I\s+think|we\s+could|here\s+are\s+(?:some|a\s+few)|"
    r"you\s+might|let\s+me\s+suggest|options?\s+(?:include|are)|"
    r"what\s+(?:about|if)|consider|some\s+ideas|my\s+recommendation)"
    r")",
)

_ACTION_MARKERS_RE = re.compile(
    r"(?i)(?:spawning\s+now|I['\u2019]ll\s+(?:go\s+ahead|dispatch|create\s+a\s+colony))"
)


INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # APOPTOSIS before KILL — "self-terminate" must not match KILL's "terminate"
    ("APOPTOSIS", _APOPTOSIS_RE),
    ("SPAWN", _SPAWN_RE),
    ("REDIRECT", _REDIRECT_RE),
    ("KILL", _KILL_RE),
]


# ---------------------------------------------------------------------------
# Regex-based intent extraction
# ---------------------------------------------------------------------------


def parse_intent_regex(text: str) -> dict[str, Any] | None:
    """Extract a directive from Queen prose via regex.

    Returns ``None`` if no intent detected.  Returns a dict with
    ``action`` and action-specific fields if found.
    """
    if not text or not text.strip():
        return None

    # Wave 60.5: deliberation guard — exploratory prose should not trigger SPAWN
    if _DELIBERATION_RE.search(text) and not _ACTION_MARKERS_RE.search(text):
        return {"action": "DELIBERATE"}

    # Explicit tool-name prose from weaker local models:
    # "I'll use spawn_colony to create a colony with task='...'"
    task_match = _SPAWN_TOOL_TASK_RE.search(text)
    if task_match:
        objective = next(
            (group.strip() for group in task_match.groups() if group and group.strip()),
            "",
        ).rstrip(".")
        if len(objective) >= 3:
            return {"action": "SPAWN", "objective": objective}

    tool_prose_match = _SPAWN_TOOL_PROSE_RE.search(text)
    if tool_prose_match:
        objective = tool_prose_match.group(1).strip().rstrip(".")
        if len(objective) >= 3:
            return {"action": "SPAWN", "objective": objective}

    preview_task = _PREVIEW_TASK_LINE_RE.search(text)
    preview_team = _PREVIEW_TEAM_LINE_RE.search(text)
    if preview_task and preview_team:
        rounds_budget_match = _PREVIEW_ROUNDS_BUDGET_LINE_RE.search(text)
        rounds_match = _PREVIEW_ROUNDS_LINE_RE.search(text)
        budget_match = _PREVIEW_BUDGET_LINE_RE.search(text)
        looks_like_preview = any(
            token in text.lower()
            for token in ("preview complete", "ready to spawn", "confirm to proceed")
        )
        if rounds_budget_match or rounds_match or budget_match or looks_like_preview:
            objective = preview_task.group(1).strip().rstrip(".")
            castes: list[dict[str, Any]] = []
            for team_match in _PREVIEW_TEAM_SLOT_RE.finditer(preview_team.group(1)):
                caste = team_match.group(1).lower()
                tier = (team_match.group(2) or "standard").lower()
                count_raw = team_match.group(3) or team_match.group(4)
                slot: dict[str, Any] = {"caste": caste, "tier": tier}
                if count_raw:
                    slot["count"] = max(1, int(count_raw))
                castes.append(slot)
            intent: dict[str, Any] = {
                "action": "PREVIEW_SPAWN",
                "objective": objective,
                "castes": castes or [{"caste": "coder", "tier": "standard"}],
            }
            strategy_match = _PREVIEW_STRATEGY_LINE_RE.search(text)
            if strategy_match:
                intent["strategy"] = strategy_match.group(1).lower()
            if rounds_budget_match:
                intent["max_rounds"] = int(rounds_budget_match.group(1))
                intent["budget_limit"] = float(rounds_budget_match.group(2))
            else:
                if rounds_match:
                    intent["max_rounds"] = int(rounds_match.group(1))
                if budget_match:
                    intent["budget_limit"] = float(budget_match.group(1))
            if "fast_path" in text.lower():
                intent["fast_path"] = True
            return intent

    for action, pattern in INTENT_PATTERNS:
        match = pattern.search(text)
        if match:
            if action == "SPAWN":
                objective = match.group(1).strip().rstrip(".")
                if len(objective) < 3:
                    continue  # too short to be a real objective
                return {"action": "SPAWN", "objective": objective}
            if action == "KILL":
                return {"action": "KILL", "colony_id": match.group(1).strip()}
            if action == "REDIRECT":
                return {
                    "action": "REDIRECT",
                    "colony_id": match.group(1).strip(),
                    "new_objective": match.group(2).strip().rstrip("."),
                }
            if action == "APOPTOSIS":
                return {"action": "APOPTOSIS", "colony_id": match.group(1).strip()}
    return None


# ---------------------------------------------------------------------------
# Gemini Flash classification fallback
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """\
Classify the following Queen agent output into one of these actions:
- SPAWN: The Queen wants to create a new colony for a task
- KILL: The Queen wants to terminate a colony
- REDIRECT: The Queen wants to change a colony's focus
- APOPTOSIS: The Queen says a colony should self-terminate
- DELIBERATE: The Queen is exploring options, suggesting ideas, or discussing — not directing action
- NONE: No clear directive

Output ONLY a JSON object: {{"action": "SPAWN|KILL|REDIRECT|APOPTOSIS|NONE", "details": "..."}}

Queen output:
{text}"""


async def classify_intent_gemini(
    text: str,
    runtime: Any,  # noqa: ANN401
) -> dict[str, Any] | None:
    """Classify Queen prose via Gemini Flash.  500ms timeout.

    Returns ``None`` on timeout, parse failure, or ``NONE`` classification.
    """
    prompt = _CLASSIFY_PROMPT.format(text=text[:500])
    try:
        response = await asyncio.wait_for(
            runtime.llm_router.complete(
                model="gemini/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],  # type: ignore[list-item]
                temperature=0.0,
                max_tokens=100,
            ),
            timeout=0.5,
        )
        content = response.content.strip()
        # Try to parse JSON from the response
        obj: Any = json.loads(content)
        if isinstance(obj, dict) and obj.get("action") not in (None, "NONE"):  # pyright: ignore[reportUnknownMemberType]
            action = str(obj["action"]).upper()  # pyright: ignore[reportUnknownArgumentType]
            details = str(obj.get("details", ""))  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

            if action == "DELIBERATE":
                return {"action": "DELIBERATE"}
            if action == "SPAWN" and details:
                return {"action": "SPAWN", "objective": details}
            if action == "KILL" and details:
                return {"action": "KILL", "colony_id": details}
            if action == "REDIRECT" and details:
                parts = details.split(" to ", 1)
                if len(parts) == 2:
                    return {
                        "action": "REDIRECT",
                        "colony_id": parts[0].strip(),
                        "new_objective": parts[1].strip(),
                    }
            if action == "APOPTOSIS" and details:
                return {"action": "APOPTOSIS", "colony_id": details}

    except (TimeoutError, json.JSONDecodeError, Exception):
        logger.debug("queen_intent.gemini_fallback_failed", text_preview=text[:80])

    return None


# ---------------------------------------------------------------------------
# Unified two-pass entry point
# ---------------------------------------------------------------------------


async def parse_queen_intent(
    text: str,
    runtime: Any | None = None,  # noqa: ANN401
) -> tuple[dict[str, Any] | None, str]:
    """Two-pass intent extraction from Queen prose.

    Returns ``(intent_dict, via)`` where ``via`` is ``"regex"`` or
    ``"gemini_flash"``.  Returns ``(None, "")`` when nothing detected.
    """
    # Pass 1: Regex
    result = parse_intent_regex(text)
    if result is not None:
        logger.info(
            "queen_intent_parsed",
            action=result["action"],
            via="regex",
            text_preview=text[:100],
        )
        return result, "regex"

    # Pass 2: Gemini Flash (only if runtime available)
    if runtime is not None:
        result = await classify_intent_gemini(text, runtime)
        if result is not None:
            logger.info(
                "queen_intent_parsed",
                action=result["action"],
                via="gemini_flash",
                text_preview=text[:100],
            )
            return result, "gemini_flash"

    return None, ""


def intent_to_tool_call(intent: dict[str, Any]) -> dict[str, Any]:
    """Convert an intent dict to a tool-call dict matching _execute_tool format.

    The returned dict has ``name`` and ``input`` keys — same shape as
    tool calls from the primary LLM path, so ``_execute_tool`` handles
    them identically.
    """
    action = intent["action"]
    if action == "DELIBERATE":
        return {}  # no tool call — pass through as chat
    if action == "PREVIEW_SPAWN":
        tool_input: dict[str, Any] = {
            "task": intent["objective"],
            "castes": intent.get("castes") or [{"caste": "coder", "tier": "standard"}],
            "preview": True,
        }
        if "max_rounds" in intent:
            tool_input["max_rounds"] = intent["max_rounds"]
        if "budget_limit" in intent:
            tool_input["budget_limit"] = intent["budget_limit"]
        if "strategy" in intent:
            tool_input["strategy"] = intent["strategy"]
        if "fast_path" in intent:
            tool_input["fast_path"] = intent["fast_path"]
        return {
            "name": "spawn_colony",
            "input": tool_input,
        }
    if action == "SPAWN":
        return {
            "name": "spawn_colony",
            "input": {
                "task": intent["objective"],
                "castes": ["coder", "reviewer"],  # sensible default
            },
        }
    if action == "KILL":
        return {
            "name": "kill_colony",
            "input": {"colony_id": intent["colony_id"]},
        }
    # REDIRECT and APOPTOSIS don't have dedicated tools yet —
    # log and return a kill for APOPTOSIS, skip for REDIRECT
    if action == "APOPTOSIS":
        return {
            "name": "kill_colony",
            "input": {"colony_id": intent["colony_id"]},
        }
    # REDIRECT — no tool exists yet; return empty (no-op, logged)
    logger.info(
        "queen_intent.no_tool_for_action",
        action=action,
        intent=intent,
    )
    return {}


__all__ = [
    "parse_intent_regex",
    "parse_queen_intent",
    "intent_to_tool_call",
]
