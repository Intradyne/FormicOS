"""
Tests for AsyncContextTree (context.py) -- FormicOS v0.6.0

Covers:
  - Concurrent read/write safety (asyncio.gather)
  - Scope isolation
  - TKG query by subject, by team_id
  - TKG performance (1000 tuples)
  - Serialization round-trip (to_dict -> from_dict)
  - Lock TTL expiration
  - Dirty tracking
  - Episode windowing
  - Decision recording and retrieval
  - batch_set atomicity
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from src.context import AsyncContextTree, SCHEMA_VERSION
from src.models import (
    Decision,
    DecisionType,
    Episode,
    EpochSummary,
    TKGTuple,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ctx() -> AsyncContextTree:
    """Fresh context tree for each test."""
    return AsyncContextTree(episode_window=2)


# ── Concurrent Read/Write Safety ────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_read_write_safety(ctx: AsyncContextTree) -> None:
    """
    Many concurrent writers and readers should not corrupt state.
    All 100 writes should land, and reads should never raise.
    """

    async def writer(i: int) -> None:
        await ctx.set("colony", f"key_{i}", f"val_{i}")

    async def reader(i: int) -> None:
        # Reads are lockless and must never raise
        ctx.get("colony", f"key_{i}")

    tasks = []
    for i in range(100):
        tasks.append(writer(i))
        tasks.append(reader(i))

    await asyncio.gather(*tasks)

    # All 100 writes should be present
    for i in range(100):
        assert ctx.get("colony", f"key_{i}") == f"val_{i}"


@pytest.mark.asyncio
async def test_concurrent_batch_set_and_reads(ctx: AsyncContextTree) -> None:
    """batch_set should apply atomically: a reader never sees partial state."""

    observed_states: list[tuple] = []

    async def batch_writer() -> None:
        for _ in range(20):
            await ctx.batch_set("colony", {"a": 1, "b": 2, "c": 3})
            await asyncio.sleep(0)
            await ctx.batch_set("colony", {"a": 10, "b": 20, "c": 30})
            await asyncio.sleep(0)

    async def reader() -> None:
        for _ in range(50):
            a = ctx.get("colony", "a")
            b = ctx.get("colony", "b")
            c = ctx.get("colony", "c")
            if a is not None:
                observed_states.append((a, b, c))
            await asyncio.sleep(0)

    await asyncio.gather(batch_writer(), reader())

    # Each observed state should be one of the two atomic batches or None
    for state in observed_states:
        assert state in [(1, 2, 3), (10, 20, 30)], (
            f"Observed inconsistent state: {state}"
        )


# ── Scope Isolation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scope_isolation(ctx: AsyncContextTree) -> None:
    """Writing to one scope must not affect another."""
    await ctx.set("colony", "key", "colony_val")
    await ctx.set("system", "key", "system_val")
    await ctx.set("mcp", "key", "mcp_val")

    assert ctx.get("colony", "key") == "colony_val"
    assert ctx.get("system", "key") == "system_val"
    assert ctx.get("mcp", "key") == "mcp_val"

    # Cross-scope: colony shouldn't see system's value
    assert ctx.get("colony", "nonexistent") is None
    assert ctx.get("project", "key") is None


@pytest.mark.asyncio
async def test_invalid_scope_raises(ctx: AsyncContextTree) -> None:
    """Accessing an invalid scope must raise ValueError."""
    with pytest.raises(ValueError, match="Invalid scope"):
        ctx.get("invalid_scope", "key")

    with pytest.raises(ValueError, match="Invalid scope"):
        await ctx.set("bogus", "key", "value")

    with pytest.raises(ValueError, match="Invalid scope"):
        await ctx.batch_set("nope", {"key": "value"})


@pytest.mark.asyncio
async def test_get_scope(ctx: AsyncContextTree) -> None:
    """get_scope returns a dict of all keys in that scope."""
    await ctx.set("system", "a", 1)
    await ctx.set("system", "b", 2)

    scope = ctx.get_scope("system")
    assert scope == {"a": 1, "b": 2}

    # Mutating the returned dict doesn't affect the tree
    scope["c"] = 3
    assert ctx.get("system", "c") is None


# ── TKG Query by Subject, by Team ───────────────────────────────────────


@pytest.mark.asyncio
async def test_tkg_query_by_subject(ctx: AsyncContextTree) -> None:
    """TKG subject-indexed lookup should return only matching tuples."""
    t1 = TKGTuple(subject="auth", predicate="uses", object_="JWT", round_num=1)
    t2 = TKGTuple(subject="auth", predicate="has", object_="bug", round_num=2)
    t3 = TKGTuple(subject="db", predicate="uses", object_="Postgres", round_num=1)

    await ctx.record_tkg_tuple(t1)
    await ctx.record_tkg_tuple(t2)
    await ctx.record_tkg_tuple(t3)

    auth_tuples = ctx.query_tkg(subject="auth")
    assert len(auth_tuples) == 2
    assert all(t.subject == "auth" for t in auth_tuples)

    db_tuples = ctx.query_tkg(subject="db")
    assert len(db_tuples) == 1
    assert db_tuples[0].object_ == "Postgres"


@pytest.mark.asyncio
async def test_tkg_query_by_team_id(ctx: AsyncContextTree) -> None:
    """TKG query with team_id filter."""
    t1 = TKGTuple(subject="api", predicate="owns", object_="endpoint",
                   round_num=1, team_id="team-a")
    t2 = TKGTuple(subject="api", predicate="owns", object_="schema",
                   round_num=2, team_id="team-b")
    t3 = TKGTuple(subject="api", predicate="has", object_="docs",
                   round_num=3, team_id="team-a")

    await ctx.record_tkg_tuple(t1)
    await ctx.record_tkg_tuple(t2)
    await ctx.record_tkg_tuple(t3)

    team_a = ctx.query_tkg(subject="api", team_id="team-a")
    assert len(team_a) == 2
    assert all(t.team_id == "team-a" for t in team_a)

    team_b = ctx.query_tkg(team_id="team-b")
    assert len(team_b) == 1
    assert team_b[0].object_ == "schema"


@pytest.mark.asyncio
async def test_tkg_query_all_filters(ctx: AsyncContextTree) -> None:
    """Query combining subject, predicate, object_, and team_id."""
    t = TKGTuple(subject="auth", predicate="uses", object_="JWT",
                 round_num=1, team_id="security")
    await ctx.record_tkg_tuple(t)
    await ctx.record_tkg_tuple(
        TKGTuple(subject="auth", predicate="uses", object_="cookies",
                 round_num=2, team_id="security")
    )

    results = ctx.query_tkg(
        subject="auth", predicate="uses", object_="JWT", team_id="security"
    )
    assert len(results) == 1
    assert results[0].object_ == "JWT"


# ── TKG Performance ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tkg_performance_1000_tuples(ctx: AsyncContextTree) -> None:
    """
    Insert 1000 TKG tuples across 50 subjects and query.
    Subject-indexed lookup should complete well under 1 second.
    """
    for i in range(1000):
        subject = f"subject_{i % 50}"
        t = TKGTuple(
            subject=subject,
            predicate=f"pred_{i}",
            object_=f"obj_{i}",
            round_num=i,
        )
        await ctx.record_tkg_tuple(t)

    start = time.perf_counter()
    results = ctx.query_tkg(subject="subject_0")
    elapsed = time.perf_counter() - start

    # 1000/50 = 20 tuples per subject
    assert len(results) == 20
    assert elapsed < 1.0, f"TKG query took {elapsed:.3f}s (too slow)"


@pytest.mark.asyncio
async def test_tkg_prune(ctx: AsyncContextTree) -> None:
    """prune_tkg should remove oldest tuples beyond the limit."""
    for i in range(10):
        t = TKGTuple(
            subject=f"s_{i % 3}",
            predicate="p",
            object_="o",
            round_num=i,
            timestamp=float(1000 + i),  # ascending timestamps
        )
        await ctx.record_tkg_tuple(t)

    removed = await ctx.prune_tkg(5)
    assert removed == 5

    remaining = ctx.query_tkg()
    assert len(remaining) == 5
    # The 5 newest (highest timestamp) should survive
    timestamps = sorted(t.timestamp for t in remaining)
    assert timestamps == [1005.0, 1006.0, 1007.0, 1008.0, 1009.0]


# ── Serialization Round-Trip ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serialization_round_trip(ctx: AsyncContextTree) -> None:
    """to_dict -> from_dict must preserve all state."""
    # Populate scopes
    await ctx.set("system", "llm_model", "Qwen3-30B")
    await ctx.set("colony", "task", "Build auth module")
    await ctx.set("mcp", "tools", ["fs", "fetch"])
    await ctx.set("supercolony", "active_colonies", 2)
    await ctx.set("project", "file_index", ["main.py", "utils.py"])
    await ctx.set("knowledge", "domain", "web-app")

    # Episode
    ep = Episode(round_num=1, summary="Implemented login", goal="Auth system")
    await ctx.record_episode(ep)

    # Epoch summary
    es = EpochSummary(epoch_id=0, summary="Phase 1 complete",
                      round_range=(0, 4))
    await ctx.record_epoch_summary(es)

    # TKG
    tkg = TKGTuple(subject="auth", predicate="uses", object_="JWT", round_num=1)
    await ctx.record_tkg_tuple(tkg)

    # Decision
    dec = Decision(
        round_num=1,
        decision_type=DecisionType.ROUTING,
        detail="Routed to architect",
    )
    await ctx.record_decision(dec)

    # Serialize
    data = await ctx.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION

    # Reconstruct
    restored = AsyncContextTree.from_dict(data)

    # Verify scopes
    assert restored.get("system", "llm_model") == "Qwen3-30B"
    assert restored.get("colony", "task") == "Build auth module"
    assert restored.get("mcp", "tools") == ["fs", "fetch"]
    assert restored.get("supercolony", "active_colonies") == 2
    assert restored.get("project", "file_index") == ["main.py", "utils.py"]
    assert restored.get("knowledge", "domain") == "web-app"

    # Episodes
    eps = restored.get_episodes()
    assert len(eps) == 1
    assert eps[0].summary == "Implemented login"

    # Epoch summaries
    sums = restored.get_epoch_summaries()
    assert len(sums) == 1
    assert sums[0].summary == "Phase 1 complete"

    # TKG
    tkg_results = restored.query_tkg(subject="auth")
    assert len(tkg_results) == 1
    assert tkg_results[0].predicate == "uses"

    # Decisions
    decs = restored.get_decisions()
    assert len(decs) == 1
    assert decs[0].detail == "Routed to architect"


@pytest.mark.asyncio
async def test_save_load_round_trip(ctx: AsyncContextTree, tmp_path) -> None:
    """save() and load() should produce identical state."""
    await ctx.set("colony", "round", 5)
    await ctx.record_episode(
        Episode(round_num=1, summary="Test ep", goal="Test goal")
    )

    path = tmp_path / "ctx.json"
    await ctx.save(path)
    assert path.exists()

    loaded = await AsyncContextTree.load(path)
    assert loaded.get("colony", "round") == 5
    assert len(loaded.get_episodes()) == 1
    assert loaded.get_episodes()[0].summary == "Test ep"


# ── Lock TTL Expiration ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_lock_ttl_expiration(ctx: AsyncContextTree) -> None:
    """An expired lock should be auto-released, letting another agent acquire."""
    # Agent A acquires with a very short TTL
    assert await ctx.acquire_lock("/workspace/file.py", "agent-a", ttl=0.01)

    # Wait for expiry
    await asyncio.sleep(0.05)

    # Agent B should be able to acquire the expired lock
    assert await ctx.acquire_lock("/workspace/file.py", "agent-b", ttl=30.0)

    # Agent A cannot re-acquire since B now holds it
    assert not await ctx.acquire_lock("/workspace/file.py", "agent-a", ttl=30.0)


@pytest.mark.asyncio
async def test_file_lock_basic(ctx: AsyncContextTree) -> None:
    """Basic lock acquire / release cycle."""
    assert await ctx.acquire_lock("/file.txt", "agent-1")

    # Same agent can re-acquire (refresh)
    assert await ctx.acquire_lock("/file.txt", "agent-1")

    # Different agent blocked
    assert not await ctx.acquire_lock("/file.txt", "agent-2")

    # Release and re-acquire by other
    await ctx.release_lock("/file.txt", "agent-1")
    assert await ctx.acquire_lock("/file.txt", "agent-2")


@pytest.mark.asyncio
async def test_file_lock_only_holder_can_release(ctx: AsyncContextTree) -> None:
    """A non-holder agent calling release should have no effect."""
    assert await ctx.acquire_lock("/f.txt", "agent-a")

    # Agent B tries to release A's lock (should be a no-op)
    await ctx.release_lock("/f.txt", "agent-b")

    # Agent A's lock should still be there — B can't acquire
    assert not await ctx.acquire_lock("/f.txt", "agent-b")


# ── Dirty Tracking ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dirty_tracking(ctx: AsyncContextTree) -> None:
    """set marks dirty; to_dict (snapshot) clears it."""
    assert not ctx.dirty

    await ctx.set("colony", "x", 1)
    assert ctx.dirty

    await ctx.to_dict()
    assert not ctx.dirty

    # batch_set also marks dirty
    await ctx.batch_set("colony", {"y": 2})
    assert ctx.dirty

    await ctx.to_dict()
    assert not ctx.dirty


@pytest.mark.asyncio
async def test_dirty_after_record_operations(ctx: AsyncContextTree) -> None:
    """All record_* methods should mark the tree dirty."""
    assert not ctx.dirty

    await ctx.record_episode(
        Episode(round_num=0, summary="s", goal="g")
    )
    assert ctx.dirty
    await ctx.to_dict()

    await ctx.record_epoch_summary(
        EpochSummary(epoch_id=0, summary="s", round_range=(0, 0))
    )
    assert ctx.dirty
    await ctx.to_dict()

    await ctx.record_tkg_tuple(
        TKGTuple(subject="s", predicate="p", object_="o", round_num=0)
    )
    assert ctx.dirty
    await ctx.to_dict()

    await ctx.record_decision(
        Decision(round_num=0, decision_type=DecisionType.ROUTING, detail="d")
    )
    assert ctx.dirty


# ── Episode Windowing ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_episode_windowing(ctx: AsyncContextTree) -> None:
    """get_working_memory respects the episode window."""
    for i in range(5):
        await ctx.record_episode(
            Episode(round_num=i, summary=f"ep_{i}", goal="g")
        )

    # Default window = 2
    wm = ctx.get_working_memory()
    assert len(wm) == 2
    assert wm[0].summary == "ep_3"
    assert wm[1].summary == "ep_4"


@pytest.mark.asyncio
async def test_episode_windowing_custom() -> None:
    """A tree with custom episode_window=4 should return 4 episodes."""
    ctx = AsyncContextTree(episode_window=4)
    for i in range(10):
        await ctx.record_episode(
            Episode(round_num=i, summary=f"ep_{i}", goal="g")
        )

    wm = ctx.get_working_memory()
    assert len(wm) == 4
    assert wm[0].summary == "ep_6"
    assert wm[-1].summary == "ep_9"


@pytest.mark.asyncio
async def test_get_episodes_with_window(ctx: AsyncContextTree) -> None:
    """get_episodes(window=N) returns last N episodes."""
    for i in range(5):
        await ctx.record_episode(
            Episode(round_num=i, summary=f"ep_{i}", goal="g")
        )

    last3 = ctx.get_episodes(window=3)
    assert len(last3) == 3
    assert last3[0].summary == "ep_2"

    all_eps = ctx.get_episodes()
    assert len(all_eps) == 5


# ── Decision Recording and Retrieval ────────────────────────────────────


@pytest.mark.asyncio
async def test_decision_recording(ctx: AsyncContextTree) -> None:
    """Decisions should be recorded and retrieved in order."""
    d1 = Decision(
        round_num=1,
        decision_type=DecisionType.ROUTING,
        detail="Route A->B",
    )
    d2 = Decision(
        round_num=2,
        decision_type=DecisionType.TERMINATION,
        detail="Colony converged",
        recommendations=["Save results"],
    )

    await ctx.record_decision(d1)
    await ctx.record_decision(d2)

    decisions = ctx.get_decisions()
    assert len(decisions) == 2
    assert decisions[0].detail == "Route A->B"
    assert decisions[1].decision_type == DecisionType.TERMINATION
    assert decisions[1].recommendations == ["Save results"]


# ── batch_set Atomicity ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_set_atomicity(ctx: AsyncContextTree) -> None:
    """batch_set should apply all keys at once."""
    await ctx.batch_set("colony", {
        "round": 3,
        "goal": "Build the API",
        "status": "running",
    })

    assert ctx.get("colony", "round") == 3
    assert ctx.get("colony", "goal") == "Build the API"
    assert ctx.get("colony", "status") == "running"


@pytest.mark.asyncio
async def test_batch_set_overwrite(ctx: AsyncContextTree) -> None:
    """batch_set should overwrite existing keys."""
    await ctx.set("colony", "round", 1)
    await ctx.batch_set("colony", {"round": 2, "new_key": "new_val"})

    assert ctx.get("colony", "round") == 2
    assert ctx.get("colony", "new_key") == "new_val"


# ── Clear Colony ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_colony(ctx: AsyncContextTree) -> None:
    """clear_colony wipes all colony-lifetime data."""
    await ctx.set("colony", "task", "do stuff")
    await ctx.set("system", "llm", "qwen")
    await ctx.record_episode(Episode(round_num=0, summary="s", goal="g"))
    await ctx.record_decision(
        Decision(round_num=0, decision_type=DecisionType.ROUTING, detail="d")
    )
    await ctx.record_tkg_tuple(
        TKGTuple(subject="s", predicate="p", object_="o", round_num=0)
    )

    await ctx.clear_colony()

    # Colony-lifetime state is gone
    assert ctx.get("colony", "task") is None
    assert len(ctx.get_episodes()) == 0
    assert len(ctx.get_decisions()) == 0
    assert len(ctx.query_tkg()) == 0

    # Process-lifetime state survives
    assert ctx.get("system", "llm") == "qwen"


# ── Context Assembly ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assemble_agent_context_basic(ctx: AsyncContextTree) -> None:
    """assemble_agent_context produces a non-empty string with key info."""
    await ctx.set("system", "llm_model", "Qwen3-30B")
    await ctx.set("system", "llm_endpoint", "http://localhost:8080")
    await ctx.set("colony", "task", "Build auth")
    await ctx.set("colony", "round", 2)

    await ctx.record_episode(
        Episode(round_num=1, summary="Started auth", goal="Auth module")
    )

    result = ctx.assemble_agent_context("agent-1", "coder")
    assert "Qwen3-30B" in result
    assert "Build auth" in result
    assert "Started auth" in result


@pytest.mark.asyncio
async def test_assemble_agent_context_token_budget(
    ctx: AsyncContextTree,
) -> None:
    """Token budget should truncate the output."""
    await ctx.set("system", "llm_model", "BigModel")
    await ctx.set("colony", "task", "A" * 1000)

    full = ctx.assemble_agent_context("a", "coder")
    truncated = ctx.assemble_agent_context("a", "coder", token_budget=10)

    assert len(truncated) <= 40  # 10 tokens * 4 chars
    assert len(full) > len(truncated)


@pytest.mark.asyncio
async def test_assemble_agent_context_team(ctx: AsyncContextTree) -> None:
    """Team context should appear when team_id is provided."""
    await ctx.set("colony", "teams", {"alpha": "Build the frontend"})

    result = ctx.assemble_agent_context("a", "coder", team_id="alpha")
    assert "Team alpha" in result
    assert "Build the frontend" in result


# ── Repr ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repr(ctx: AsyncContextTree) -> None:
    """__repr__ should not raise and should contain key stats."""
    r = repr(ctx)
    assert "AsyncContextTree" in r
    assert "dirty=" in r


# ── Schema Version Mismatch ─────────────────────────────────────────────


def test_from_dict_schema_mismatch() -> None:
    """Loading a dict with a different schema version should warn, not crash."""
    data = {
        "schema_version": "0.5.0",
        "system": {"llm": "test"},
        "_episodes": [],
        "_epoch_summaries": [],
        "_tkg": [],
        "_decisions": [],
        "_file_locks": {},
    }
    tree = AsyncContextTree.from_dict(data)
    assert tree.get("system", "llm") == "test"


# ── Default Value on Missing Key ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_default_value(ctx: AsyncContextTree) -> None:
    """get() should return the provided default for missing keys."""
    assert ctx.get("colony", "nonexistent") is None
    assert ctx.get("colony", "nonexistent", "fallback") == "fallback"
