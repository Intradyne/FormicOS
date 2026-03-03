"""
FormicOS v0.8.0 — Inbound MCP Memory Server

Standalone MCP server (stdio transport) that exposes the colony's persistent
memory manifold to external IDEs (Cursor, Claude Desktop, etc.) via MCP.

Resources:
  formic://stigmergy/{colony_id}/state  — full topological graph history
  formic://qdrant/{collection}/latest   — most recent points from a collection

Tools:
  query_formic_memory      — semantic search over Qdrant swarm_memory
  get_colony_failure_history — extract failure records from session files

Launch:
  python -m src.mcp.inbound_memory_server
  python -m src.mcp

Configuration (env vars):
  FORMICOS_CONFIG       — path to formicos.yaml (default: config/formicos.yaml)
  FORMICOS_SESSION_DIR  — session storage root (default: .formicos/sessions)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

logger = logging.getLogger("formicos.mcp.inbound")

# ── Configuration ─────────────────────────────────────────────────────────


def _load_config() -> dict:
    """Load formicos.yaml and return the parsed dict."""
    path = os.environ.get("FORMICOS_CONFIG", "config/formicos.yaml")
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Config not found: %s — using defaults", path)
        return {}


def _session_dir() -> Path:
    """Return the session storage root."""
    return Path(
        os.environ.get("FORMICOS_SESSION_DIR", ".formicos/sessions")
    )


# ── Session Helpers ───────────────────────────────────────────────────────


def read_session_state(session_dir: Path, colony_id: str) -> dict | None:
    """Find and return the context.json for a given colony_id.

    Scans session directories looking for a matching colony_id in the
    colony scope of each context.json.
    """
    if not session_dir.is_dir():
        return None
    for d in sorted(session_dir.iterdir()):
        if not d.is_dir():
            continue
        ctx_path = d / "context.json"
        if not ctx_path.exists():
            continue
        try:
            data = json.loads(ctx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cid = data.get("colony", {}).get("colony_id")
        if cid == colony_id:
            return data
    return None


def extract_colony_scope(data: dict) -> dict:
    """Extract the colony scope fields suitable for MCP resource response."""
    colony = data.get("colony", {})
    return {
        "colony_id": colony.get("colony_id"),
        "task": colony.get("task"),
        "status": colony.get("status"),
        "round": colony.get("round"),
        "topology": colony.get("topology"),
        "topology_history": colony.get("topology_history", []),
        "round_history": (
            colony.get("checkpoint", {}).get("round_history", [])
        ),
        "agents": [
            n.get("id")
            for n in colony.get("topology", {}).get("nodes", [])
        ],
    }


def extract_failure_history(
    session_dir: Path,
    colony_id: str | None = None,
    max_records: int = 3,
) -> list[dict]:
    """Extract failure records from session context files.

    Looks at ``_decisions`` for force_halt / intervene / escalate actions,
    and ``_tkg`` tuples for Failed_Test / Error predicates.
    """
    if not session_dir.is_dir():
        return []

    failure_decision_types = {"force_halt", "intervene"}
    failure_rec_actions = {"force_halt", "escalate", "intervene"}
    failure_predicates = {"Failed_Test", "Error", "failed_test", "error"}

    failures: list[dict] = []

    for d in sorted(session_dir.iterdir()):
        if not d.is_dir():
            continue
        ctx_path = d / "context.json"
        if not ctx_path.exists():
            continue
        try:
            data = json.loads(ctx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        cid = data.get("colony", {}).get("colony_id")
        if colony_id and cid != colony_id:
            continue

        # Decisions with failure types or failure-related recommendations
        for dec in data.get("_decisions", []):
            is_failure = dec.get("decision_type") in failure_decision_types
            has_failure_rec = any(
                rec.get("action") in failure_rec_actions
                for rec in dec.get("enriched_recommendations", [])
            )
            if is_failure or has_failure_rec:
                failures.append({
                    "source": "decision",
                    "colony_id": cid,
                    "round_num": dec.get("round_num"),
                    "decision_type": dec.get("decision_type"),
                    "detail": dec.get("detail"),
                    "recommendations": dec.get("enriched_recommendations", []),
                    "timestamp": dec.get("timestamp"),
                })

        # TKG tuples with failure predicates
        for triple in data.get("_tkg", []):
            if triple.get("predicate") in failure_predicates:
                failures.append({
                    "source": "tkg",
                    "colony_id": cid,
                    "round_num": triple.get("round_num"),
                    "subject": triple.get("subject"),
                    "predicate": triple.get("predicate"),
                    "detail": triple.get("object_"),
                    "timestamp": triple.get("timestamp"),
                })

    # Sort by timestamp descending, return last N
    failures.sort(key=lambda f: f.get("timestamp") or 0, reverse=True)
    return failures[:max_records]


# ── MCP Server ────────────────────────────────────────────────────────────


async def main() -> None:
    """Run the inbound MCP memory server on stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    config = _load_config()
    qdrant_cfg = config.get("qdrant", {})
    qdrant_host = qdrant_cfg.get("host", "localhost")
    qdrant_port = qdrant_cfg.get("port", 6333)
    embedding_cfg = config.get("embedding", {})
    embedding_endpoint = embedding_cfg.get("endpoint", "http://localhost:8080/v1")
    sessions = _session_dir()

    server = Server("formicos-memory")

    # ── Resources ──────────────────────────────────────────

    @server.list_resources()
    async def handle_list_resources() -> list[Resource]:
        """List available MCP resources.

        Returns one resource per session colony (stigmergy state) plus
        one per known Qdrant collection.
        """
        resources: list[Resource] = []

        # Stigmergy resources from session files
        if sessions.is_dir():
            for d in sorted(sessions.iterdir()):
                if not d.is_dir():
                    continue
                ctx_path = d / "context.json"
                if not ctx_path.exists():
                    continue
                try:
                    data = json.loads(
                        ctx_path.read_text(encoding="utf-8")
                    )
                    cid = data.get("colony", {}).get("colony_id")
                    if cid:
                        resources.append(Resource(
                            uri=f"formic://stigmergy/{cid}/state",
                            name=f"Colony {cid} — Stigmergy State",
                            description=(
                                f"Topological graph history and round data "
                                f"for colony {cid}"
                            ),
                            mimeType="application/json",
                        ))
                except (json.JSONDecodeError, OSError):
                    continue

        # Qdrant collection resources
        for coll_name in qdrant_cfg.get("collections", {}):
            resources.append(Resource(
                uri=f"formic://qdrant/{coll_name}/latest",
                name=f"Qdrant {coll_name} — Latest Points",
                description=(
                    f"Most recent entries from the {coll_name} collection"
                ),
                mimeType="application/json",
            ))

        return resources

    @server.read_resource()
    async def handle_read_resource(uri: Any) -> str:
        """Read the content of a specific MCP resource."""
        uri_str = str(uri)

        # formic://stigmergy/{colony_id}/state
        if uri_str.startswith("formic://stigmergy/"):
            parts = uri_str.split("/")
            if len(parts) >= 5:
                colony_id = parts[3]
                data = read_session_state(sessions, colony_id)
                if data is None:
                    return json.dumps(
                        {"error": f"Colony '{colony_id}' not found"},
                        indent=2,
                    )
                return json.dumps(extract_colony_scope(data), indent=2)

        # formic://qdrant/{collection}/latest
        if uri_str.startswith("formic://qdrant/"):
            parts = uri_str.split("/")
            if len(parts) >= 5:
                collection = parts[3]
                return await _qdrant_scroll_latest(
                    qdrant_host, qdrant_port, collection,
                )

        return json.dumps({"error": f"Unknown resource URI: {uri_str}"})

    # ── Tools ──────────────────────────────────────────────

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name="query_formic_memory",
                description=(
                    "Semantic vector search over the FormicOS swarm memory. "
                    "Returns the top-k most relevant memory entries."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (default 5)",
                            "default": 5,
                        },
                        "collection": {
                            "type": "string",
                            "description": (
                                "Qdrant collection name "
                                "(default: swarm_memory)"
                            ),
                            "default": "swarm_memory",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_colony_failure_history",
                description=(
                    "Retrieve recent failure records from FormicOS colony "
                    "sessions. Extracts governance decisions (force_halt, "
                    "intervene) and TKG failure predicates."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": (
                                "Filter to a specific colony "
                                "(omit for all colonies)"
                            ),
                        },
                    },
                    "required": [],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None,
    ) -> list[TextContent]:
        args = arguments or {}

        if name == "query_formic_memory":
            query = args.get("query", "")
            top_k = int(args.get("top_k", 5))
            collection = args.get("collection", "swarm_memory")
            result = await _qdrant_search(
                qdrant_host, qdrant_port,
                embedding_endpoint, query,
                collection, top_k,
            )
            return [TextContent(type="text", text=result)]

        if name == "get_colony_failure_history":
            colony_id = args.get("colony_id")
            failures = extract_failure_history(sessions, colony_id)
            if not failures:
                return [TextContent(
                    type="text",
                    text="No failure records found.",
                )]
            return [TextContent(
                type="text",
                text=json.dumps(failures, indent=2),
            )]

        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}",
        )]

    # ── Run ────────────────────────────────────────────────

    logger.info("FormicOS Inbound MCP Memory Server starting (stdio)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# ── Qdrant Helpers ────────────────────────────────────────────────────────


async def _qdrant_scroll_latest(
    host: str, port: int, collection: str, limit: int = 20,
) -> str:
    """Scroll the latest points from a Qdrant collection via REST API."""
    url = f"http://{host}:{port}/collections/{collection}/points/scroll"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            })
            if resp.status_code == 200:
                data = resp.json()
                points = data.get("result", {}).get("points", [])
                entries = []
                for pt in points:
                    payload = pt.get("payload", {})
                    entries.append({
                        "id": pt.get("id"),
                        "content": payload.get("content", payload.get("text", "")),
                        "source": payload.get("source", ""),
                        "timestamp": payload.get("timestamp"),
                    })
                return json.dumps(entries, indent=2)
            return json.dumps({
                "error": f"Qdrant returned {resp.status_code}",
                "body": resp.text[:500],
            })
    except Exception as exc:
        return json.dumps({
            "error": f"Qdrant unreachable: {exc}",
        })


async def _qdrant_search(
    host: str,
    port: int,
    embedding_endpoint: str,
    query: str,
    collection: str,
    top_k: int,
) -> str:
    """Embed query and search Qdrant via REST API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: Embed the query
            embed_resp = await client.post(
                f"{embedding_endpoint}/embeddings",
                json={"input": query, "model": "bge-m3"},
            )
            if embed_resp.status_code != 200:
                return f"Embedding API error: {embed_resp.status_code}"
            vector = embed_resp.json()["data"][0]["embedding"]

            # Step 2: Search Qdrant
            search_url = (
                f"http://{host}:{port}"
                f"/collections/{collection}/points/query"
            )
            search_resp = await client.post(search_url, json={
                "query": vector,
                "limit": top_k,
                "with_payload": True,
            })
            if search_resp.status_code != 200:
                return f"Qdrant search error: {search_resp.status_code}"

            results = search_resp.json().get("result", {}).get("points", [])

            # Step 3: Format as Markdown
            if not results:
                return "No results found."

            lines = [f"## Search Results for: {query}\n"]
            for i, pt in enumerate(results, 1):
                payload = pt.get("payload", {})
                score = pt.get("score", 0)
                content = payload.get("content", payload.get("text", ""))
                source = payload.get("source", "unknown")
                lines.append(
                    f"### {i}. (score: {score:.3f}) — {source}\n"
                    f"{content}\n"
                )
            return "\n".join(lines)

    except Exception as exc:
        return f"Search failed: {exc}"


if __name__ == "__main__":
    asyncio.run(main())
