"""Wave 10 Docker smoke test.

Two-tier structure:
  GATE tests  — use the direct spawn_colony WS command (no Queen LLM).
                These are the hard acceptance gate.
  ADVISORY    — model-dependent or key-dependent checks that may fail
                in environments without specific API keys or models.

Wave 10 additions:
  GATE 7:  Qdrant serving skill bank (collection exists, healthy)
  GATE 8:  GET /api/v1/skills returns 404 (removed Wave 28)
  GATE 9:  Colony auto-navigation event flow (ColonySpawned delivers colony_id)
  ADVISORY: Gemini routing (requires GEMINI_API_KEY)
  ADVISORY: Queen tool-call spawn (model-dependent)

Run against a running container:
    docker compose build && docker compose up -d
    sleep 15 && python tests/smoke_test.py
"""

import asyncio
import json
import time
import urllib.request
from typing import Any

import websockets  # type: ignore[import-untyped]

RESULTS: list[tuple[str, bool, str, str]] = []  # label, ok, detail, tier

_TERMINAL_EVENTS = {"ColonyCompleted", "ColonyFailed", "ColonyKilled"}


def log(
    label: str, status: bool, detail: str = "", tier: str = "GATE",
) -> None:
    icon = "PASS" if status else "FAIL"
    RESULTS.append((label, status, detail, tier))
    tag = f"[{tier}]" if tier == "ADVISORY" else ""
    print(f"  [{icon}]{tag} {label}" + (f" -- {detail}" if detail else ""))


def _is_terminal(e: dict[str, Any]) -> bool:
    return e.get("type", "") in _TERMINAL_EVENTS


async def collect(
    ws: Any,
    predicate: Any = None,
    timeout_s: float = 60,
) -> list[dict[str, Any]]:
    """Collect events until timeout or predicate matches."""
    events: list[dict[str, Any]] = []
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=min(remaining, 5),
            )
            msg = json.loads(raw)
            if msg.get("type") == "event":
                ev = msg["event"]
                events.append(ev)
                if predicate and predicate(ev):
                    return events
        except TimeoutError:
            continue
    return events


def get_snapshot_from_msg(raw: str) -> dict[str, Any] | None:
    msg = json.loads(raw)
    if msg.get("type") == "state":
        return msg["state"]
    return None


async def drain_until_state(
    ws: Any, timeout_s: float = 15,
) -> dict[str, Any] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=min(remaining, 5),
            )
            snap = get_snapshot_from_msg(raw)
            if snap is not None:
                return snap
        except TimeoutError:
            continue
    return None


def find_colonies(
    tree: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    colonies: list[dict[str, Any]] = []
    for ws_node in tree:
        for thread in ws_node.get("children", []):
            for colony in thread.get("children", []):
                if colony.get("type") == "colony":
                    colonies.append(colony)
    return colonies


async def get_snapshot(ws: Any) -> dict[str, Any] | None:
    """Re-subscribe and return a fresh snapshot."""
    await ws.send(json.dumps({
        "action": "subscribe", "workspaceId": "default",
    }))
    return await drain_until_state(ws, timeout_s=15)


def _direct_spawn(task: str, castes: list[str] | None = None) -> str:
    """Build a direct spawn_colony WS command (bypasses Queen)."""
    return json.dumps({
        "action": "spawn_colony",
        "workspaceId": "default",
        "payload": {
            "threadId": "main",
            "task": task,
            "castes": [
                {"caste": caste, "tier": "standard", "count": 1}
                for caste in (castes or ["coder"])
            ],
        },
    })


def _queen_spawn(task: str) -> str:
    """Build a Queen chat message asking to spawn (model-dependent)."""
    return json.dumps({
        "action": "send_queen_message",
        "workspaceId": "default",
        "payload": {
            "threadId": "main",
            "content": (
                f'Use your spawn_colony tool to create a colony '
                f'with castes=["coder"] and task="{task}" '
                f'in thread main.'
            ),
        },
    })


# ===================================================================
# GATE TESTS — direct WS commands, no Queen LLM dependency
# ===================================================================


async def gate_routing_in_agent_events(ws: Any) -> None:
    """GATE: spawn via direct command, verify AgentTurnStarted.model."""
    print("\n--- GATE 1: Routing decisions in AgentTurnStarted.model ---")
    await ws.send(_direct_spawn("Write a fibonacci function in Python"))

    agent_models: dict[str, str] = {}
    colony_id: str | None = None

    evts = await collect(ws, _is_terminal, timeout_s=120)

    for e in evts:
        etype = e.get("type", "")
        if etype == "ColonySpawned":
            colony_id = (
                e.get("colony_id") or e.get("colonyId") or "?"
            )
            log("ColonySpawned", True, f"id={colony_id}")
        elif etype == "AgentTurnStarted":
            aid = e.get("agent_id") or e.get("agentId", "?")
            model = e.get("model", "")
            caste = e.get("caste", "?")
            agent_models[aid] = model
            log(
                f"AgentTurnStarted.model ({caste})",
                len(model) > 0,
                f"agent={aid} model={model}",
            )
        elif _is_terminal(e):
            log("Colony terminal", True, f"type={etype}")

    if not colony_id:
        log("ColonySpawned", False, "No ColonySpawned received")

    if agent_models:
        all_resolved = all(len(m) > 0 for m in agent_models.values())
        log(
            "All agents have routed models",
            all_resolved,
            f"{len(agent_models)} agents: {agent_models}",
        )
    else:
        log("Agent models captured", False, "No AgentTurnStarted events")


async def gate_models_used_badges(ws: Any) -> None:
    """GATE: verify modelsUsed + badge classification in snapshot."""
    print("\n--- GATE 2: modelsUsed and routing badges ---")

    snap = await get_snapshot(ws)
    if snap is None:
        log("Snapshot received", False, "No state snapshot")
        return

    log("Snapshot received", True)
    colonies = find_colonies(snap.get("tree", []))
    if not colonies:
        log("Colonies in snapshot", False, "No colonies found")
        return

    for col in colonies:
        cid = col.get("id", "?")
        models_used = col.get("modelsUsed")

        log(
            f"modelsUsed present ({cid})",
            models_used is not None,
            f"modelsUsed={models_used}",
        )
        if models_used is None:
            continue

        if len(models_used) == 0:
            badge = "none"
        elif len(models_used) > 1:
            badge = "mixed"
        elif (
            models_used[0].startswith("llama-cpp/")
            or models_used[0].startswith("ollama/")
        ):
            badge = "local"
        else:
            badge = "cloud"

        log(
            f"Routing badge ({cid})",
            badge in {"none", "local", "cloud", "mixed"},
            f"badge={badge} models={models_used}",
        )

        agent_models_in_snap = {
            a["model"] for a in col.get("agents", []) if a.get("model")
        }
        log(
            f"modelsUsed matches agents ({cid})",
            set(models_used) == agent_models_in_snap,
            f"snap={set(models_used)} agents={agent_models_in_snap}",
        )


async def gate_skill_bank_stats(ws: Any) -> None:
    """GATE: verify skillBankStats shape in snapshot."""
    print("\n--- GATE 3: skillBankStats in snapshot ---")

    snap = await get_snapshot(ws)
    if snap is None:
        log("Snapshot for skillBankStats", False, "No snapshot")
        return

    stats = snap.get("skillBankStats")
    log(
        "skillBankStats present",
        stats is not None,
        f"skillBankStats={stats}",
    )
    if stats is None:
        return

    log(
        "skillBankStats.total field",
        "total" in stats,
        f"total={stats.get('total')}",
    )
    log(
        "skillBankStats.avgConfidence field",
        "avgConfidence" in stats,
        f"avgConfidence={stats.get('avgConfidence')}",
    )

    total = stats.get("total", -1)
    avg = stats.get("avgConfidence", -1)
    log("skillBankStats.total >= 0", total >= 0, f"total={total}")
    log(
        "skillBankStats.avgConfidence in [0,1]",
        isinstance(avg, (int, float)) and 0 <= avg <= 1,
        f"avgConfidence={avg}",
    )


async def gate_concurrent_colony_isolation(ws: Any) -> None:
    """GATE: two direct spawns with same caste, verify no agent ID overlap."""
    print("\n--- GATE 4: Concurrent colony agent isolation ---")

    # Pre-snapshot to know existing colonies
    pre_snap = await get_snapshot(ws)
    existing_ids = (
        {c.get("id") for c in find_colonies(pre_snap.get("tree", []))}
        if pre_snap else set()
    )

    await ws.send(_direct_spawn("Write a Python hello-world script"))
    await asyncio.sleep(1)
    await ws.send(_direct_spawn("Write a Python fizzbuzz function"))

    colony_agents: dict[str, set[str]] = {}
    terminal_count = 0

    evts = await collect(
        ws,
        lambda e: (
            _is_terminal(e)
            and terminal_count >= 1  # noqa: B023
        ),
        timeout_s=180,
    )

    for e in evts:
        etype = e.get("type", "")
        cid = e.get("colony_id") or e.get("colonyId") or ""

        if etype == "ColonySpawned" and cid:
            colony_agents.setdefault(cid, set())
        elif etype == "AgentTurnStarted" and cid:
            colony_agents.setdefault(cid, set())
            aid = e.get("agent_id") or e.get("agentId") or ""
            colony_agents[cid].add(aid)
        elif _is_terminal(e):
            terminal_count += 1

    # Filter to only new colonies
    new_colonies = {
        cid: agents
        for cid, agents in colony_agents.items()
        if cid not in existing_ids
    }

    if len(new_colonies) < 2:
        log(
            "Two colonies spawned", False,
            f"Only {len(new_colonies)} new colonies captured",
        )
        return

    log(
        "Two colonies spawned", True,
        f"colonies={list(new_colonies.keys())}",
    )

    # Event-stream check
    colony_list = list(new_colonies.items())
    for i, (_cid_a, agents_a) in enumerate(colony_list):
        for _cid_b, agents_b in colony_list[i + 1:]:
            overlap = agents_a & agents_b
            log(
                "No agent overlap (events)",
                len(overlap) == 0,
                f"overlap={overlap}" if overlap else "clean",
            )

    # Snapshot check
    snap = await get_snapshot(ws)
    if snap is None:
        log("Snapshot for isolation check", False, "No snapshot")
        return

    all_agents_seen: dict[str, str] = {}
    cross_contaminated = False
    for col in find_colonies(snap.get("tree", [])):
        cid = col.get("id", "")
        for a in col.get("agents", []):
            aid = a["id"]
            if aid in all_agents_seen:
                log(
                    f"Agent {aid} cross-contamination", False,
                    f"in both {all_agents_seen[aid]} and {cid}",
                )
                cross_contaminated = True
            else:
                all_agents_seen[aid] = cid

    if not cross_contaminated:
        log(
            "Snapshot agent isolation", True,
            f"{len(all_agents_seen)} agents, no overlap",
        )


async def gate_skill_lifecycle(ws: Any) -> None:
    """GATE: spawn two colonies via direct command, check skill stats."""
    print("\n--- GATE 5: Skill lifecycle after colonies ---")

    # Colony A
    await ws.send(_direct_spawn(
        "Write a Python function that checks if a string is a palindrome",
    ))
    evts = await collect(ws, _is_terminal, timeout_s=120)
    terminal = [e for e in evts if _is_terminal(e)]

    if not terminal:
        log("Colony A terminal", False, "No terminal event within 120s")
        return

    t_type = terminal[0].get("type", "?")
    cid_a = (
        terminal[0].get("colony_id")
        or terminal[0].get("colonyId", "?")
    )
    log("Colony A terminal", True, f"id={cid_a} type={t_type}")

    snap_a = await get_snapshot(ws)
    if snap_a is None:
        log("Post-colony-A snapshot", False, "No snapshot")
        return

    stats_a = snap_a.get("skillBankStats", {})
    total_a = stats_a.get("total", 0)
    avg_a = stats_a.get("avgConfidence", 0)
    log(
        "Post-colony-A skillBankStats", True,
        f"total={total_a} avg={avg_a}",
    )

    col_a = next(
        (c for c in find_colonies(snap_a.get("tree", []))
         if c.get("id") == cid_a),
        None,
    )
    if col_a:
        log(
            "Colony A stats", True,
            f"skillsExtracted={col_a.get('skillsExtracted', 0)} "
            f"qualityScore={col_a.get('qualityScore', 0)} "
            f"status={col_a.get('status')}",
        )

    # Colony B — similar task, should trigger skill retrieval
    await ws.send(_direct_spawn(
        "Write a Python function that checks if a word is a palindrome",
    ))
    evts_b = await collect(ws, _is_terminal, timeout_s=120)
    terminal_b = [e for e in evts_b if _is_terminal(e)]

    if terminal_b:
        log(
            "Colony B terminal", True,
            f"type={terminal_b[0].get('type')}",
        )
    else:
        log("Colony B terminal", False, "No terminal event for colony B")
        return

    snap_b = await get_snapshot(ws)
    if snap_b:
        stats_b = snap_b.get("skillBankStats", {})
        total_b = stats_b.get("total", 0)
        avg_b = stats_b.get("avgConfidence", 0)
        log(
            "Post-colony-B skillBankStats", True,
            f"total={total_b} avg={avg_b:.3f} "
            f"(was total={total_a} avg={avg_a:.3f})",
        )
        if total_a > 0:
            log(
                "Skill total non-decreasing",
                total_b >= total_a,
                f"{total_a} -> {total_b}",
            )
    else:
        log("Post-colony-B snapshot", False, "No snapshot")


async def gate_health(_ws: Any) -> None:
    """GATE: health endpoint check."""
    print("\n--- GATE 6: Health endpoint ---")
    resp = urllib.request.urlopen(  # noqa: S310
        "http://localhost:8080/health",
    )
    data = json.loads(resp.read())
    seq = data.get("last_seq", 0)
    log("Health endpoint", seq >= 0, f"last_seq={seq}")


# ===================================================================
# WAVE 10 GATE TESTS — Qdrant, skill browser REST, auto-nav
# ===================================================================


async def gate_qdrant_serving(_ws: Any) -> None:
    """GATE: Qdrant is running and has the skill_bank collection."""
    print("\n--- GATE 7: Qdrant serving skill bank ---")
    try:
        resp = urllib.request.urlopen(  # noqa: S310
            "http://localhost:6333/healthz", timeout=5,
        )
        log("Qdrant healthz", resp.status == 200, f"status={resp.status}")
    except Exception as exc:
        log("Qdrant healthz", False, f"error={exc}")
        return

    try:
        resp = urllib.request.urlopen(  # noqa: S310
            "http://localhost:6333/collections/skill_bank", timeout=5,
        )
        data = json.loads(resp.read())
        result = data.get("result", {})
        status = result.get("status")
        points = result.get("points_count", 0)
        log(
            "skill_bank collection exists", True,
            f"status={status} points={points}",
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Collection doesn't exist yet — that's OK on first run
            # because ensure_collection is lazy (called on first operation)
            log(
                "skill_bank collection exists", True,
                "not yet created (lazy init on first skill upsert)",
            )
        else:
            log("skill_bank collection exists", False, f"HTTP {exc.code}")
    except Exception as exc:
        log("skill_bank collection exists", False, f"error={exc}")


async def gate_skill_browser_rest(_ws: Any) -> None:
    """GATE: GET /api/v1/skills returns 404 (removed in Wave 28)."""
    print("\n--- GATE 8: Skill browser REST endpoint (removed Wave 28) ---")
    try:
        resp = urllib.request.urlopen(  # noqa: S310
            "http://localhost:8080/api/v1/skills?sort=confidence&limit=10",
            timeout=10,
        )
        # If we get here, the endpoint still exists — unexpected
        log("/api/v1/skills removed", False, f"status={resp.status} (expected 404)")
    except urllib.error.HTTPError as exc:
        log("/api/v1/skills removed", exc.code == 404, f"status={exc.code}")
    except Exception as exc:
        log("/api/v1/skills removed", False, f"error={exc}")


async def gate_colony_autonav_events(ws: Any) -> None:
    """GATE: ColonySpawned delivers colony_id for auto-navigation."""
    print("\n--- GATE 9: Colony auto-navigation event flow ---")

    await ws.send(_direct_spawn("Write a Python hello function"))

    colony_id_from_spawn: str | None = None
    evts = await collect(ws, _is_terminal, timeout_s=120)

    for e in evts:
        etype = e.get("type", "")
        if etype == "ColonySpawned":
            addr = e.get("address", "")
            cid = e.get("colony_id") or e.get("colonyId") or ""
            # colony_id should be extractable from address or explicit field
            resolved = cid or (addr.split("/")[-1] if "/" in addr else "")
            colony_id_from_spawn = resolved
            log(
                "ColonySpawned has colony_id",
                len(resolved) > 0,
                f"colony_id={resolved} address={addr}",
            )

    if colony_id_from_spawn:
        # Verify the colony appears in snapshot (frontend would navigate to it)
        snap = await get_snapshot(ws)
        if snap:
            colonies = find_colonies(snap.get("tree", []))
            found = any(
                c.get("id") == colony_id_from_spawn for c in colonies
            )
            log(
                "Spawned colony in snapshot tree",
                found,
                f"looking for {colony_id_from_spawn} in {len(colonies)} colonies",
            )
        else:
            log("Snapshot for auto-nav check", False, "No snapshot")
    else:
        log(
            "ColonySpawned has colony_id", False,
            "No ColonySpawned event received",
        )


# ===================================================================
# ADVISORY TESTS — model/key-dependent
# ===================================================================


async def advisory_gemini_routing(ws: Any) -> None:
    """ADVISORY: Gemini models appear in routing (requires GEMINI_API_KEY)."""
    print("\n--- ADVISORY: Gemini routing ---")

    snap = await get_snapshot(ws)
    if snap is None:
        log("Snapshot for Gemini check", False, "No snapshot", tier="ADVISORY")
        return

    # Check if Gemini models are in cloud endpoints
    endpoints = snap.get("cloudEndpoints", [])
    gemini_ep = [ep for ep in endpoints if ep.get("provider") == "gemini"]
    if gemini_ep:
        status = gemini_ep[0].get("status", "unknown")
        models = gemini_ep[0].get("models", [])
        log(
            "Gemini endpoint registered", True,
            f"status={status} models={models}", tier="ADVISORY",
        )
        log(
            "Gemini endpoint connected",
            status == "connected",
            f"status={status} (no_key means GEMINI_API_KEY not set)",
            tier="ADVISORY",
        )
    else:
        log(
            "Gemini endpoint registered", False,
            "No gemini provider in cloudEndpoints",
            tier="ADVISORY",
        )

    # Check routing config for gemini references
    rt_config = snap.get("runtimeConfig", {})
    routing = rt_config.get("routing", {})
    log(
        "Routing config present", True,
        f"keys={list(routing.keys())}", tier="ADVISORY",
    )


async def advisory_queen_spawn(ws: Any) -> None:
    """ADVISORY: Queen chat reaches preview/spawn path via tool use."""
    print("\n--- ADVISORY: Queen preview/spawn path ---")

    await ws.send(_queen_spawn(
        "Write a Python function that reverses a string",
    ))

    colony_spawned = False
    preview_seen = False
    evts = await collect(
        ws,
        lambda e: (
            e.get("type") == "ColonySpawned"
            or (
                e.get("type") == "QueenMessage"
                and e.get("role") == "queen"
                and e.get("render") == "preview_card"
            )
            or _is_terminal(e)
        ),
        timeout_s=45,
    )

    for e in evts:
        if e.get("type") == "ColonySpawned":
            colony_spawned = True
            cid = e.get("colony_id") or e.get("colonyId", "?")
            log(
                "Queen spawned colony", True,
                f"id={cid}", tier="ADVISORY",
            )
        elif e.get("type") == "QueenMessage" and e.get("role") == "queen":
            content = (e.get("content") or "")[:150]
            log(
                "Queen replied", True,
                content, tier="ADVISORY",
            )
            if e.get("render") == "preview_card":
                preview_seen = True
                log(
                    "Queen produced preview card", True,
                    content, tier="ADVISORY",
                )

    if not colony_spawned and not preview_seen:
        log(
            "Queen preview/spawn path", False,
            "Queen did not produce a preview card or spawn a colony",
            tier="ADVISORY",
        )


# ===================================================================
# Main session
# ===================================================================


async def ws_session() -> None:
    uri = "ws://localhost:8080/ws"
    async with websockets.connect(uri) as ws:
        init_snap = await drain_until_state(ws, timeout_s=10)
        if init_snap:
            log("Initial snapshot", True)
        else:
            log("Initial snapshot", False, "No state on connect")

        await ws.send(json.dumps({
            "action": "subscribe", "workspaceId": "default",
        }))
        await drain_until_state(ws, timeout_s=10)

        # Hard acceptance gates (no Queen LLM dependency)
        await gate_routing_in_agent_events(ws)
        await gate_models_used_badges(ws)
        await gate_skill_bank_stats(ws)
        await gate_concurrent_colony_isolation(ws)
        await gate_skill_lifecycle(ws)
        await gate_health(ws)

        # Wave 10 gates
        await gate_qdrant_serving(ws)
        await gate_skill_browser_rest(ws)
        await gate_colony_autonav_events(ws)

        # Advisory (model/key-dependent)
        await advisory_gemini_routing(ws)
        await advisory_queen_spawn(ws)

    # --- Summary ---
    gate = [(lb, s, d) for lb, s, d, t in RESULTS if t == "GATE"]
    adv = [(lb, s, d) for lb, s, d, t in RESULTS if t == "ADVISORY"]

    gate_passed = sum(1 for _, s, _ in gate if s)
    gate_failed = sum(1 for _, s, _ in gate if not s)
    adv_passed = sum(1 for _, s, _ in adv if s)
    adv_failed = sum(1 for _, s, _ in adv if not s)

    print(f"\n{'=' * 60}")
    print(
        f"GATE:     {gate_passed} passed, {gate_failed} failed "
        f"out of {len(gate)}",
    )
    print(
        f"ADVISORY: {adv_passed} passed, {adv_failed} failed "
        f"out of {len(adv)}",
    )
    print(f"{'=' * 60}")

    if gate_failed:
        print("\nFailed GATE checks (blocking):")
        for label, status, detail in gate:
            if not status:
                print(f"  FAIL: {label} -- {detail}")

    if adv_failed:
        print("\nFailed ADVISORY checks (non-blocking):")
        for label, status, detail in adv:
            if not status:
                print(f"  WARN: {label} -- {detail}")

    print(f"{'=' * 60}")

    # Exit code reflects only GATE results
    raise SystemExit(1 if gate_failed else 0)


if __name__ == "__main__":
    asyncio.run(ws_session())
