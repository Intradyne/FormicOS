"""
FormicOS v0.6.0 -- AsyncContextTree

Hierarchical, async-safe, scoped state store that serves as the shared memory
backbone for an entire colony.  All components read and write through it.

Concurrency model (see research doc Section 1.2):
  - Single asyncio.Lock on ALL mutations
  - Lockless single-key reads (GIL-safe: dict.get is one bytecode op)
  - Consistent multi-key snapshots acquire the lock

Design decisions:
  D1  Single lock, not per-scope (scopes aren't independent during snapshot)
  D2  Lockless reads (eventual consistency is acceptable for single keys)
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from src.models import (
    Decision,
    Episode,
    EpochSummary,
    TKGTuple,
)

logger = logging.getLogger("formicos.context")

SCHEMA_VERSION = "0.6.0"

VALID_SCOPES = frozenset({
    "supercolony",
    "system",
    "project",
    "colony",
    "knowledge",
    "mcp",
})


# ── Helpers ──────────────────────────────────────────────────────────────


def _validate_scope(scope: str) -> None:
    """Raise ValueError if *scope* is not one of the six canonical scopes."""
    if scope not in VALID_SCOPES:
        raise ValueError(
            f"Invalid scope '{scope}'. "
            f"Must be one of: {sorted(VALID_SCOPES)}"
        )


def _fsync_directory(dir_path: Path) -> None:
    """Sync directory metadata to disk (Linux only; no-op on Windows)."""
    if os.name == "nt":
        return
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_json(data: dict, target: Path) -> None:
    """Write-fsync-replace: crash-safe JSON persistence."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(target))
        _fsync_directory(target.parent)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── File Lock Entry ──────────────────────────────────────────────────────


class _FileLock:
    """Workspace file lock with TTL auto-release."""

    __slots__ = ("agent_id", "acquired_at", "ttl")

    def __init__(self, agent_id: str, ttl: float) -> None:
        self.agent_id = agent_id
        self.acquired_at = time.time()
        self.ttl = ttl

    @property
    def expired(self) -> bool:
        return (time.time() - self.acquired_at) >= self.ttl

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "acquired_at": self.acquired_at,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, d: dict) -> _FileLock:
        lock = cls(agent_id=d["agent_id"], ttl=d["ttl"])
        lock.acquired_at = d["acquired_at"]
        return lock


# ═════════════════════════════════════════════════════════════════════════
# AsyncContextTree
# ═════════════════════════════════════════════════════════════════════════


class AsyncContextTree:
    """
    Hierarchical, async-safe, scoped state store.

    Six scopes:
      supercolony  – model registry state, active colonies, global knowledge
      system       – GPU stats, LLM endpoint, model name
      project      – file index, repo structure, project docs
      colony       – task, agents, topology, round history, status
      knowledge    – epoch summaries, TKG, episodic memory
      mcp          – discovered tools, gateway status
    """

    VALID_SCOPES = VALID_SCOPES

    # ── Construction ─────────────────────────────────────────────────

    def __init__(self, *, episode_window: int = 2) -> None:
        # Scoped key-value store
        self._scopes: dict[str, dict[str, Any]] = {
            s: {} for s in self.VALID_SCOPES
        }

        # Episodic memory
        self._episodes: list[Episode] = []
        self._episode_window: int = episode_window

        # Epoch summaries
        self._epoch_summaries: list[EpochSummary] = []

        # TKG – indexed by subject for O(1) lookup
        self._tkg_index: dict[str, list[TKGTuple]] = {}

        # Decision log
        self._decisions: list[Decision] = []

        # File locks (path → _FileLock)
        self._file_locks: dict[str, _FileLock] = {}

        # Concurrency
        self._lock = asyncio.Lock()

        # Dirty tracking
        self._dirty: bool = False

        # Client namespace (v0.7.5)
        self._client_namespace: str | None = None

    # ── Lockless single-key reads (GIL-safe, Section 1.2) ───────────

    def get(self, scope: str, key: str, default: Any = None) -> Any:
        """
        Single-key read.  Safe WITHOUT the lock because dict.get() is a
        single bytecode operation in CPython and we accept eventual
        consistency for single reads.
        """
        _validate_scope(scope)
        return self._scopes[scope].get(key, default)

    def get_scope(self, scope: str) -> dict[str, Any]:
        """Return a shallow copy of every key in *scope*."""
        _validate_scope(scope)
        return dict(self._scopes[scope])

    # ── Protected writes (single asyncio.Lock on ALL mutations) ──────

    async def set(self, scope: str, key: str, value: Any) -> None:
        """Set a single key under the lock."""
        _validate_scope(scope)
        async with self._lock:
            self._set_unlocked(scope, key, value)
            self._dirty = True

    async def batch_set(self, scope: str, mapping: dict[str, Any]) -> None:
        """
        Atomic multi-key update within one scope.

        Uses a single lock acquisition so callers never see a partially
        applied batch.
        """
        _validate_scope(scope)
        async with self._lock:
            for key, value in mapping.items():
                self._set_unlocked(scope, key, value)
            self._dirty = True

    # ── Episodic memory ──────────────────────────────────────────────

    async def record_episode(self, episode: Episode) -> None:
        async with self._lock:
            self._episodes.append(episode)
            self._dirty = True

    def get_episodes(self, window: int | None = None) -> list[Episode]:
        """Return the last *window* episodes (lockless read)."""
        if window is None:
            return list(self._episodes)
        return list(self._episodes[-window:])

    def get_working_memory(self, window: int | None = None) -> list[Episode]:
        """Return the most recent episodes within the configured window."""
        w = window if window is not None else self._episode_window
        return list(self._episodes[-w:]) if self._episodes else []

    # ── Epoch summaries ──────────────────────────────────────────────

    async def record_epoch_summary(self, summary: EpochSummary) -> None:
        async with self._lock:
            self._epoch_summaries.append(summary)
            self._dirty = True

    def get_epoch_summaries(self) -> list[EpochSummary]:
        return list(self._epoch_summaries)

    # ── Client namespace (v0.7.5) ────────────────────────────────────

    def set_client_namespace(self, client_id: str) -> None:
        """Set the client namespace (called once at colony creation)."""
        self._client_namespace = client_id

    def get_client_namespace(self) -> str | None:
        """Return the client namespace (lockless read)."""
        return self._client_namespace

    # ── Temporal Knowledge Graph (indexed by subject) ────────────────

    async def record_tkg_tuple(self, t: TKGTuple) -> None:
        async with self._lock:
            self._tkg_index.setdefault(t.subject, []).append(t)
            self._dirty = True

    def query_tkg(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        team_id: str | None = None,
    ) -> list[TKGTuple]:
        """
        Query TKG tuples.  When *subject* is supplied the lookup is O(1)
        on the index; otherwise a full scan is performed.
        """
        if subject is not None:
            candidates = self._tkg_index.get(subject, [])
        else:
            candidates = [
                t for bucket in self._tkg_index.values() for t in bucket
            ]

        results: list[TKGTuple] = []
        for t in candidates:
            if predicate is not None and t.predicate != predicate:
                continue
            if object_ is not None and t.object_ != object_:
                continue
            if team_id is not None and t.team_id != team_id:
                continue
            results.append(t)
        return results

    async def prune_tkg(self, max_tuples: int) -> int:
        """
        Remove oldest tuples until count <= *max_tuples*.
        Returns the number of tuples removed.
        """
        async with self._lock:
            all_tuples: list[TKGTuple] = []
            for bucket in self._tkg_index.values():
                all_tuples.extend(bucket)

            if len(all_tuples) <= max_tuples:
                return 0

            # Sort ascending by timestamp – oldest first
            all_tuples.sort(key=lambda t: t.timestamp)
            keep = set(id(t) for t in all_tuples[-max_tuples:])
            removed = len(all_tuples) - max_tuples

            # Rebuild index keeping only the retained tuples
            new_index: dict[str, list[TKGTuple]] = {}
            for subject, bucket in self._tkg_index.items():
                filtered = [t for t in bucket if id(t) in keep]
                if filtered:
                    new_index[subject] = filtered
            self._tkg_index = new_index
            self._dirty = True
            return removed

    # ── Decision log ─────────────────────────────────────────────────

    async def record_decision(self, decision: Decision) -> None:
        async with self._lock:
            self._decisions.append(decision)
            self._dirty = True

    def get_decisions(self) -> list[Decision]:
        return list(self._decisions)

    # ── File locks with TTL ──────────────────────────────────────────

    async def acquire_lock(
        self, path: str, agent_id: str, ttl: float = 30.0
    ) -> bool:
        """
        Attempt to lock *path* for *agent_id*.

        Returns True if the lock was acquired, False if already held by
        another (non-expired) agent.  Expired locks are auto-released.
        """
        async with self._lock:
            existing = self._file_locks.get(path)
            if existing is not None:
                if existing.expired:
                    logger.warning(
                        "Auto-releasing expired lock on %s (held by %s)",
                        path,
                        existing.agent_id,
                    )
                elif existing.agent_id == agent_id:
                    # Same agent re-acquiring — refresh
                    existing.acquired_at = time.time()
                    existing.ttl = ttl
                    self._dirty = True
                    return True
                else:
                    return False  # Held by another agent, not expired
            self._file_locks[path] = _FileLock(agent_id=agent_id, ttl=ttl)
            self._dirty = True
            return True

    async def release_lock(self, path: str, agent_id: str) -> None:
        """Release a file lock.  Only the holder (or expiry) can release."""
        async with self._lock:
            existing = self._file_locks.get(path)
            if existing is not None and (
                existing.agent_id == agent_id or existing.expired
            ):
                del self._file_locks[path]
                self._dirty = True

    # ── Context assembly ─────────────────────────────────────────────

    def assemble_agent_context(
        self,
        agent_id: str,
        caste: str,
        *,
        team_id: str | None = None,
        token_budget: int | None = None,
    ) -> str:
        """
        Build a prioritised context string for an agent prompt.

        Priority (highest first):
          1. System info
          2. Project structure
          3. Colony state
          4. Team context (if team_id provided)
          5. Knowledge (episodes, epoch summaries)
          6. Skills (injected by Orchestrator – pulled from colony scope)
          7. Feedback

        If *token_budget* is given a rough char-based truncation is applied
        from the lowest-priority section upward (1 token ~ 4 chars).
        """
        sections: list[str] = []

        # 1. System info
        sys_scope = self._scopes.get("system", {})
        if sys_scope:
            lines = [f"[System] model={sys_scope.get('llm_model', 'N/A')}, "
                     f"endpoint={sys_scope.get('llm_endpoint', 'N/A')}"]
            gpu = sys_scope.get("gpu_stats")
            if gpu:
                lines.append(f"  GPU: {gpu}")
            sections.append("\n".join(lines))

        # 2. Project structure
        proj_scope = self._scopes.get("project", {})
        if proj_scope:
            parts: list[str] = []
            fi = proj_scope.get("file_index")
            if fi:
                parts.append(f"[Project] files: {fi}")
            rc = proj_scope.get("recent_changes")
            if rc:
                parts.append(f"  recent changes: {rc}")
            if parts:
                sections.append("\n".join(parts))

        # 3. Colony state
        col = self._scopes.get("colony", {})
        if col:
            parts = []
            task = col.get("task")
            if task:
                parts.append(f"[Colony] task: {task}")
            rnd = col.get("round")
            if rnd is not None:
                parts.append(f"  round: {rnd}")
            agents = col.get("agents")
            if agents:
                parts.append(f"  agents: {agents}")
            status = col.get("status")
            if status:
                parts.append(f"  status: {status}")
            if parts:
                sections.append("\n".join(parts))

        # 4. Team context
        if team_id:
            team_obj = col.get("teams", {})
            if isinstance(team_obj, dict):
                team = team_obj.get(team_id)
                if team:
                    sections.append(f"[Team {team_id}] {team}")

        # 5. Knowledge
        knowledge_parts: list[str] = []
        recent_eps = self.get_working_memory()
        if recent_eps:
            ep_strs = [f"  R{e.round_num}: {e.summary}" for e in recent_eps]
            knowledge_parts.append("[Recent Episodes]\n" + "\n".join(ep_strs))
        summaries = self.get_epoch_summaries()
        if summaries:
            s_strs = [f"  Epoch {s.epoch_id}: {s.summary}" for s in summaries[-3:]]
            knowledge_parts.append("[Epoch Summaries]\n" + "\n".join(s_strs))
        if knowledge_parts:
            sections.append("\n".join(knowledge_parts))

        # 6. Skills (stored in colony scope by Orchestrator)
        skill_ctx = col.get("skill_context")
        if skill_ctx:
            sections.append(f"[Skills]\n{skill_ctx}")

        # 7. Feedback
        feedback = col.get("agent_feedback", {})
        if isinstance(feedback, dict):
            agent_fb = feedback.get(agent_id)
            if agent_fb:
                sections.append(f"[Feedback]\n{agent_fb}")

        assembled = "\n\n".join(sections)

        # Rough token-budget truncation (1 token ~ 4 chars)
        if token_budget is not None:
            char_limit = token_budget * 4
            if len(assembled) > char_limit:
                assembled = assembled[:char_limit]

        return assembled

    # ── Serialization ────────────────────────────────────────────────

    async def to_dict(self) -> dict[str, Any]:
        """
        Produce a JSON-safe deep copy of the full tree under the lock.

        The returned dict is fully detached -- mutations to the live tree
        after this call do not affect the snapshot.  Clears the dirty flag.
        """
        async with self._lock:
            result: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
            }

            # Scopes
            for scope in sorted(self.VALID_SCOPES):
                result[scope] = copy.deepcopy(self._scopes[scope])

            # Episodes
            result["_episodes"] = [e.model_dump() for e in self._episodes]

            # Epoch summaries
            result["_epoch_summaries"] = [
                s.model_dump() for s in self._epoch_summaries
            ]

            # TKG
            tkg_list: list[dict] = []
            for bucket in self._tkg_index.values():
                for t in bucket:
                    tkg_list.append(t.model_dump())
            result["_tkg"] = tkg_list

            # Decisions
            result["_decisions"] = [d.model_dump() for d in self._decisions]

            # File locks
            result["_file_locks"] = {
                p: lk.to_dict() for p, lk in self._file_locks.items()
            }

            # Metadata
            result["_episode_window"] = self._episode_window
            result["_serialized_at"] = time.time()

            self._dirty = False
            return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AsyncContextTree:
        """
        Reconstruct an AsyncContextTree from a serialized dict.

        Applies schema migration if needed.
        """
        version = data.get("schema_version", "unknown")
        if version != SCHEMA_VERSION:
            logger.warning(
                "Schema version mismatch: got %s, expected %s. "
                "Attempting best-effort load.",
                version,
                SCHEMA_VERSION,
            )

        episode_window = data.get("_episode_window", 2)
        tree = cls(episode_window=episode_window)

        # Scopes
        for scope in VALID_SCOPES:
            scope_data = data.get(scope)
            if isinstance(scope_data, dict):
                tree._scopes[scope] = copy.deepcopy(scope_data)

        # Episodes
        for ep_data in data.get("_episodes", []):
            tree._episodes.append(Episode.model_validate(ep_data))

        # Epoch summaries
        for es_data in data.get("_epoch_summaries", []):
            tree._epoch_summaries.append(
                EpochSummary.model_validate(es_data)
            )

        # TKG
        for t_data in data.get("_tkg", []):
            t = TKGTuple.model_validate(t_data)
            tree._tkg_index.setdefault(t.subject, []).append(t)

        # Decisions
        for d_data in data.get("_decisions", []):
            tree._decisions.append(Decision.model_validate(d_data))

        # File locks
        for path, lk_data in data.get("_file_locks", {}).items():
            tree._file_locks[path] = _FileLock.from_dict(lk_data)

        tree._dirty = False
        return tree

    # ── Persistence shortcuts ────────────────────────────────────────

    async def save(self, path: str | Path) -> None:
        """
        Persist the full tree to *path* using atomic write-fsync-replace.

        Offloads the actual I/O to a thread so the event loop is never
        blocked by JSON serialization or disk writes.
        """
        data = await self.to_dict()
        await asyncio.to_thread(_atomic_write_json, data, Path(path))
        logger.info("Context tree saved to %s", path)

    @classmethod
    async def load(cls, path: str | Path) -> AsyncContextTree:
        """
        Load a context tree from *path*.

        Offloads the disk read and JSON parse to a thread.
        """
        raw = await asyncio.to_thread(_load_json, Path(path))
        return cls.from_dict(raw)

    # ── Dirty tracking ───────────────────────────────────────────────

    @property
    def dirty(self) -> bool:
        """Check if the tree has unsaved mutations (no lock needed)."""
        return self._dirty

    # ── Clear colony state ───────────────────────────────────────────

    async def clear_colony(self) -> None:
        """
        Clear ALL colony-lifetime state.  Called on session deletion or
        new colony start to avoid stale data from previous runs.
        """
        async with self._lock:
            self._scopes["colony"] = {}
            self._scopes["project"] = {}
            self._scopes["knowledge"] = {}
            self._episodes.clear()
            self._epoch_summaries.clear()
            self._tkg_index.clear()
            self._decisions.clear()
            self._file_locks.clear()
            self._dirty = True

    # ── Private helpers ──────────────────────────────────────────────

    def _set_unlocked(self, scope: str, key: str, value: Any) -> None:
        """
        Raw dict assignment.  MUST be called with self._lock held.
        No awaits inside (cannot yield to another coroutine).
        """
        self._scopes[scope][key] = value

    def __repr__(self) -> str:
        counts = {s: len(v) for s, v in self._scopes.items()}
        return (
            f"<AsyncContextTree scopes={counts} "
            f"episodes={len(self._episodes)} "
            f"tkg_subjects={len(self._tkg_index)} "
            f"decisions={len(self._decisions)} "
            f"dirty={self._dirty}>"
        )


# ── Module-level I/O helpers ─────────────────────────────────────────────


def _load_json(path: Path) -> dict:
    """Synchronous JSON load -- called via asyncio.to_thread()."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
