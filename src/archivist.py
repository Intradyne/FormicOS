"""
FormicOS v0.6.0 -- Archivist

Compression and knowledge extraction engine. Transforms verbose round outputs
into compact summaries, structured facts, and transferable skills.

Responsibilities:
  1. Round Summarization (Phase 5)
     - Compresses agent outputs from a round into a concise Episode.
  2. Epoch Compression
     - Groups N episodes into an EpochSummary for long-term context.
  3. TKG Extraction
     - Extracts (subject, predicate, object) triples from agent outputs.
  4. Skill Distillation (Post-Colony)
     - Extracts transferable skills from a completed colony run.
  5. Repository Scanning
     - Walks directory tree, caches by content hash, produces per-dir summaries.
  6. Knowledge Harvesting
     - High-level post-colony extraction combining skills + repo scan.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from json_repair import repair_json
from src.llm_client import LLMClient
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import (
    Episode,
    EpochSummary,
    FormicOSConfig,
    Skill,
    SkillTier,
    TKGTuple,
)

if TYPE_CHECKING:
    from src.context import AsyncContextTree

logger = logging.getLogger("formicos.archivist")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(raw: str, fallback: Any = None) -> Any:
    """Parse LLM JSON response with repair fallback.

    Strategy:
      1. Try ``json.loads()`` directly.
      2. Try ``repair_json()`` then ``json.loads()``.
      3. Return *fallback* (caller decides what "safe empty" looks like).
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        repaired = repair_json(raw)
        return json.loads(repaired)
    except Exception:
        pass

    return fallback


# ---------------------------------------------------------------------------
# Archivist
# ---------------------------------------------------------------------------


class Archivist:
    """The colony's librarian -- compresses context, extracts knowledge."""

    def __init__(
        self,
        model_client: LLMClient,
        model_name: str,
        config: FormicOSConfig,
    ) -> None:
        self.client = model_client
        self.model = model_name
        self.config = config

        # Summarization settings
        self.epoch_window: int = config.summarization.epoch_window
        self.max_epoch_tokens: int = config.summarization.max_epoch_tokens
        self.max_agent_summary_tokens: int = (
            config.summarization.max_agent_summary_tokens
        )

        # Repository scan content-hash cache: hash -> dir summary string
        self._repo_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # LLM call with retry (stop_after_attempt=2, exponential backoff)
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _llm_call(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
    ) -> str:
        """Single LLM chat completion with retry."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return (response.choices[0].message.content or "").strip()

    # ------------------------------------------------------------------
    # Round Summarization
    # ------------------------------------------------------------------

    async def summarize_round(
        self,
        round_num: int,
        goal: str,
        agent_outputs: dict[str, str],
    ) -> Episode:
        """Compress a round's agent outputs into an Episode.

        On LLM failure, returns an Episode with an error-note summary
        so the round is never lost.
        """
        outputs_text = "\n".join(
            f"[{aid}]: {str(out)[:500]}"
            for aid, out in agent_outputs.items()
        )

        system = (
            "You are a concise summarizer for a multi-agent AI colony. "
            "Output ONLY the summary text, no formatting or preamble."
        )
        user = (
            f"Summarize this colony round in ~{self.max_agent_summary_tokens} "
            f"tokens. Focus on: what was attempted, what succeeded, "
            f"what failed, and what should happen next.\n\n"
            f"Round {round_num} Goal: {goal}\n\n"
            f"Agent Outputs:\n{outputs_text}"
        )

        try:
            summary = await self._llm_call(
                system, user, max_tokens=self.max_agent_summary_tokens
            )
        except Exception as exc:
            logger.warning(
                "LLM call failed during summarize_round (round %d): %s",
                round_num,
                exc,
            )
            summary = (
                f"[Summarization failed: {exc}] "
                f"Round {round_num} goal: {goal}. "
                f"Agents: {', '.join(agent_outputs.keys())}."
            )

        return Episode(
            round_num=round_num,
            summary=summary,
            goal=goal,
            agent_outputs=agent_outputs,
        )

    # ------------------------------------------------------------------
    # Epoch Compression
    # ------------------------------------------------------------------

    async def compress_epoch(
        self,
        episodes: list[Episode],
        epoch_id: int,
    ) -> EpochSummary:
        """Compress N episodes into one EpochSummary.

        On LLM failure, produces a mechanical concatenation summary.
        """
        if not episodes:
            return EpochSummary(
                epoch_id=epoch_id,
                summary="[Empty epoch -- no episodes to compress]",
                round_range=(0, 0),
            )

        episode_text = "\n".join(
            f"Round {ep.round_num}: {ep.summary}" for ep in episodes
        )

        system = (
            "You are a concise summarizer. Output ONLY the epoch "
            "summary text."
        )
        user = (
            f"Compress these {len(episodes)} colony rounds into a "
            f"single epoch summary of ~{self.max_epoch_tokens} tokens. "
            f"Preserve: key decisions, what worked, what failed, and "
            f"current trajectory.\n\n"
            f"Rounds:\n{episode_text}"
        )

        try:
            summary_text = await self._llm_call(
                system, user, max_tokens=self.max_epoch_tokens
            )
        except Exception as exc:
            logger.warning("LLM call failed during compress_epoch: %s", exc)
            summary_text = (
                f"[Compression failed: {exc}] "
                f"Rounds {episodes[0].round_num}-{episodes[-1].round_num}."
            )

        start = episodes[0].round_num
        end = episodes[-1].round_num

        return EpochSummary(
            epoch_id=epoch_id,
            summary=summary_text,
            round_range=(start, end),
        )

    # ------------------------------------------------------------------
    # Conditional Epoch Compression
    # ------------------------------------------------------------------

    async def maybe_compress_epochs(
        self,
        context_tree: AsyncContextTree,
    ) -> bool:
        """Check if enough episodes have accumulated to form an epoch.

        If episodes >= epoch_window, compress the oldest batch, record
        the EpochSummary to the context tree, and return True.
        """
        episodes = context_tree.get_episodes()
        existing_epochs = context_tree.get_epoch_summaries()

        # Determine which episodes have not yet been compressed
        if existing_epochs:
            last_end = existing_epochs[-1].round_range[1]
            uncompressed = [
                ep for ep in episodes if ep.round_num > last_end
            ]
        else:
            uncompressed = list(episodes)

        if len(uncompressed) < self.epoch_window:
            return False

        to_compress = uncompressed[: self.epoch_window]
        epoch_id = len(existing_epochs) + 1

        epoch_summary = await self.compress_epoch(to_compress, epoch_id)
        await context_tree.record_epoch_summary(epoch_summary)
        return True

    # ------------------------------------------------------------------
    # TKG Tuple Extraction
    # ------------------------------------------------------------------

    async def extract_tkg_tuples(
        self,
        round_num: int,
        agent_outputs: dict[str, str],
    ) -> list[TKGTuple]:
        """Extract (subject, predicate, object) triples from agent outputs.

        Returns an empty list on complete failure (never crashes the round).
        """
        outputs_text = "\n".join(
            f"[{aid}]: {str(out)[:400]}"
            for aid, out in agent_outputs.items()
        )

        system = (
            "You extract structured facts from agent outputs. "
            "Output ONLY a JSON array."
        )
        user = (
            "Extract structured facts from these agent outputs as a "
            "JSON array of {\"subject\", \"predicate\", \"object\"} tuples.\n\n"
            "Focus on: actions taken, files modified, tests run, "
            "errors encountered, decisions made.\n\n"
            "Examples:\n"
            '  {"subject": "coder_01", "predicate": "Modified_File", '
            '"object": "src/auth.py"}\n'
            '  {"subject": "reviewer_01", "predicate": "Failed_Test", '
            '"object": "test_login.py"}\n\n'
            f"Agent Outputs:\n{outputs_text}\n\n"
            "Respond with ONLY a JSON array of tuples."
        )

        try:
            raw = await self._llm_call(system, user, max_tokens=512)
        except Exception as exc:
            logger.warning(
                "LLM call failed during extract_tkg_tuples (round %d): %s",
                round_num,
                exc,
            )
            return []

        parsed = _parse_json_response(raw, fallback=[])
        if not isinstance(parsed, list):
            parsed = []

        tuples: list[TKGTuple] = []
        for item in parsed:
            if isinstance(item, dict) and all(
                k in item for k in ("subject", "predicate", "object")
            ):
                tuples.append(
                    TKGTuple(
                        subject=str(item["subject"]),
                        predicate=str(item["predicate"]),
                        object_=str(item["object"]),
                        round_num=round_num,
                    )
                )

        return tuples

    # ------------------------------------------------------------------
    # Skill Distillation
    # ------------------------------------------------------------------

    async def distill_skills(
        self,
        task: str,
        outcome: str,
        round_summaries: str,
    ) -> list[Skill]:
        """Extract transferable skills from a completed colony run.

        Returns a list of Skill objects across all tiers.
        """
        system = (
            "You extract reusable strategic patterns from AI colony "
            "runs. Output ONLY JSON."
        )
        user = (
            "Analyze this completed colony run and extract reusable skills.\n\n"
            f"TASK: {task}\n"
            f"OUTCOME: {outcome}\n\n"
            f"ROUND-BY-ROUND SUMMARY:\n{round_summaries}\n\n"
            "Respond ONLY as JSON:\n"
            "{\n"
            '  "general": ["<cross-task pattern>"],\n'
            '  "task_specific": [\n'
            '    {"category": "<task category>", "skill": "<pattern>"}\n'
            "  ],\n"
            '  "lessons": ["<what went wrong and how to avoid it>"]\n'
            "}\n\n"
            "Rules:\n"
            "- Extract 1-3 general skills, 1-3 task-specific, 0-2 lessons.\n"
            "- Each skill: 1-2 sentences, concise enough for agent context.\n"
            "- For failed colonies, prioritize lessons over general skills."
        )

        try:
            raw = await self._llm_call(system, user, max_tokens=800)
        except Exception as exc:
            logger.warning("LLM call failed during distill_skills: %s", exc)
            return []

        parsed = _parse_json_response(raw, fallback={})
        if not isinstance(parsed, dict):
            parsed = {}

        skills: list[Skill] = []

        # General skills
        for text in parsed.get("general", []):
            if isinstance(text, str) and text.strip():
                skills.append(
                    Skill(
                        skill_id=f"gen_{uuid.uuid4().hex[:8]}",
                        content=text.strip(),
                        tier=SkillTier.GENERAL,
                    )
                )

        # Task-specific skills
        for item in parsed.get("task_specific", []):
            if isinstance(item, dict):
                content = item.get("skill", "")
                category = item.get("category", "")
                if isinstance(content, str) and content.strip():
                    skills.append(
                        Skill(
                            skill_id=f"ts_{uuid.uuid4().hex[:8]}",
                            content=content.strip(),
                            tier=SkillTier.TASK_SPECIFIC,
                            category=category or None,
                        )
                    )

        # Lessons
        for text in parsed.get("lessons", []):
            if isinstance(text, str) and text.strip():
                skills.append(
                    Skill(
                        skill_id=f"les_{uuid.uuid4().hex[:8]}",
                        content=text.strip(),
                        tier=SkillTier.LESSON,
                    )
                )

        return skills

    # ------------------------------------------------------------------
    # Repository Scanning
    # ------------------------------------------------------------------

    async def scan_repository(
        self,
        repo_path: Path,
        extensions: list[str] | None = None,
    ) -> dict[str, str]:
        """Walk a directory tree and produce per-directory summaries.

        Uses content-hash caching: only re-summarizes files whose hash
        has changed since last scan. Skips unreadable files gracefully.

        Returns:
            dict mapping directory path (str) to summary string.
        """
        exts = extensions or [".py", ".js", ".ts"]
        skip_dirs = {
            ".git", "__pycache__", "node_modules",
            ".formicos", "venv", ".venv", ".tox",
        }

        # Collect source files grouped by directory
        dir_files: dict[Path, list[Path]] = {}
        for ext in exts:
            try:
                for f in repo_path.rglob(f"*{ext}"):
                    if any(skip in f.parts for skip in skip_dirs):
                        continue
                    dir_files.setdefault(f.parent, []).append(f)
            except OSError as exc:
                logger.warning("Error scanning for %s files: %s", ext, exc)

        dir_summaries: dict[str, str] = {}

        for dir_path, files in dir_files.items():
            file_summaries: list[str] = []

            for f in files:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    logger.warning("Skipping unreadable file %s: %s", f, exc)
                    continue

                content_hash = hashlib.sha256(
                    content.encode()
                ).hexdigest()[:16]

                # Check cache
                if content_hash in self._repo_cache:
                    file_summaries.append(self._repo_cache[content_hash])
                    continue

                # Generate summary via LLM
                truncated = content[:3000]
                system = "You summarize code files concisely."
                user = (
                    f"Summarize this source file in 1-2 sentences. "
                    f"Focus on: what it does and key classes/functions.\n\n"
                    f"File: {f.name}\n\n"
                    f"```\n{truncated}\n```"
                )

                try:
                    summary = await self._llm_call(
                        system, user, max_tokens=200
                    )
                except Exception as exc:
                    logger.warning("Failed to summarize %s: %s", f, exc)
                    summary = f"{f.name}: [summarization failed]"

                self._repo_cache[content_hash] = summary
                file_summaries.append(summary)

            if file_summaries:
                dir_summaries[str(dir_path)] = "\n".join(file_summaries)

        return dir_summaries

    # ------------------------------------------------------------------
    # Knowledge Harvesting (high-level post-colony)
    # ------------------------------------------------------------------

    async def harvest_knowledge(
        self,
        session_id: str,
        task: str,
        outcome: str,
    ) -> dict:
        """Post-colony knowledge extraction.

        Combines skill distillation with repository scanning metadata
        into a single harvest result.

        Returns:
            dict with keys: session_id, skills, repo_summaries, timestamp
        """
        # Distill skills from the colony run
        round_summaries = f"Task: {task}\nOutcome: {outcome}"
        skills = await self.distill_skills(task, outcome, round_summaries)

        # Scan repo if workspace path is available (best-effort)
        repo_summaries: dict[str, str] = {}

        result = {
            "session_id": session_id,
            "skills": [s.model_dump() for s in skills],
            "repo_summaries": repo_summaries,
            "timestamp": time.time(),
        }

        return result
