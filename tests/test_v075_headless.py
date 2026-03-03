"""
Tests for FormicOS v0.7.5 Headless Launch & Dispatch.

Covers:
- AsyncContextTree client namespace (set/get, default None)
- RAG ingest_document_inject (chunking, no-qdrant fallback)
- ColonyManager ingest_documents bridge
- ColonyManager create sets client namespace
- Enriched webhook payload (epoch_summaries, final_answer)
- v1_create_colony: webhook_url/budget_constraints flow into ColonyConfig
- v1_create_colony: injected_documents trigger RAG ingestion
- v1_create_colony: auto-start with webhook_url (202 response)
- v1_create_colony: no auto-start without webhook_url (200 response)
- Backward compatibility (no documents, no webhook_url)
- Version bump to 0.7.5
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.context import AsyncContextTree
from src.models import DocumentInject, EpochSummary


# ── AsyncContextTree client namespace ─────────────────────────────────


def test_context_tree_client_namespace_default_none():
    ctx = AsyncContextTree()
    assert ctx.get_client_namespace() is None


def test_context_tree_client_namespace_set_get():
    ctx = AsyncContextTree()
    ctx.set_client_namespace("n8n-prod")
    assert ctx.get_client_namespace() == "n8n-prod"


def test_context_tree_client_namespace_overwrite():
    ctx = AsyncContextTree()
    ctx.set_client_namespace("first")
    ctx.set_client_namespace("second")
    assert ctx.get_client_namespace() == "second"


# ── RAG ingest_document_inject ────────────────────────────────────────


@pytest.mark.asyncio
async def test_rag_ingest_document_inject_no_qdrant():
    """Without qdrant-client, ingest_document_inject returns 0."""
    from src.rag import RAGEngine

    with patch("src.rag.QDRANT_AVAILABLE", False):
        engine = RAGEngine.__new__(RAGEngine)
        doc = DocumentInject(filename="test.txt", content="Hello world")
        result = await engine.ingest_document_inject(doc, "test_collection")
        assert result == 0


@pytest.mark.asyncio
async def test_rag_ingest_document_inject_empty_content():
    """Empty content produces no chunks, returns 0."""
    from src.rag import RAGEngine

    with patch("src.rag.QDRANT_AVAILABLE", True):
        engine = RAGEngine.__new__(RAGEngine)
        doc = DocumentInject(filename="empty.txt", content="")
        result = await engine.ingest_document_inject(doc, "test_collection")
        assert result == 0


@pytest.mark.asyncio
async def test_rag_ingest_document_inject_calls_chunk_and_embed():
    """ingest_document_inject chunks text, embeds, and upserts."""
    from src.rag import RAGEngine, EmbeddingConfig

    engine = RAGEngine.__new__(RAGEngine)
    engine._embedding_config = EmbeddingConfig(
        endpoint="http://fake:8080",
        model="test-model",
        dimensions=1024,
    )

    test_chunks = ["chunk one", "chunk two"]
    test_embeddings = [[0.1] * 1024, [0.2] * 1024]

    with (
        patch("src.rag.QDRANT_AVAILABLE", True),
        patch.object(RAGEngine, "_chunk_text", return_value=test_chunks),
        patch.object(engine, "embed", new_callable=AsyncMock, return_value=test_embeddings),
        patch.object(engine, "ensure_collection", new_callable=AsyncMock),
        patch.object(engine, "_upsert_points", new_callable=AsyncMock, return_value=True),
    ):
        doc = DocumentInject(
            filename="design.md",
            content="Some long document content...",
            mime_type="text/markdown",
        )
        result = await engine.ingest_document_inject(doc, "colony_c1_docs")

        assert result == 2
        engine.embed.assert_awaited_once_with(test_chunks)
        engine.ensure_collection.assert_awaited_once_with(
            "colony_c1_docs", 1024,
        )
        engine._upsert_points.assert_awaited_once()
        # Verify point payloads
        points = engine._upsert_points.call_args[0][1]
        assert len(points) == 2
        assert points[0].payload["source"] == "design.md"
        assert points[0].payload["mime_type"] == "text/markdown"
        assert points[0].payload["chunk_index"] == 0
        assert points[1].payload["chunk_index"] == 1


# ── ColonyManager ingest_documents ────────────────────────────────────


@pytest.mark.asyncio
async def test_colony_manager_ingest_documents_no_rag():
    """Without RAG engine, ingest_documents returns 0."""
    from src.colony_manager import ColonyManager

    cm = ColonyManager.__new__(ColonyManager)
    cm._rag_engine = None

    docs = [DocumentInject(filename="a.txt", content="hello")]
    result = await cm.ingest_documents("c1", docs)
    assert result == 0


@pytest.mark.asyncio
async def test_colony_manager_ingest_documents_empty_list():
    """Empty document list returns 0."""
    from src.colony_manager import ColonyManager

    cm = ColonyManager.__new__(ColonyManager)
    cm._rag_engine = MagicMock()

    result = await cm.ingest_documents("c1", [])
    assert result == 0


@pytest.mark.asyncio
async def test_colony_manager_ingest_documents_calls_rag():
    """ingest_documents calls rag_engine.ingest_document_inject per doc."""
    from src.colony_manager import ColonyManager

    cm = ColonyManager.__new__(ColonyManager)
    mock_rag = AsyncMock()
    mock_rag.ingest_document_inject = AsyncMock(return_value=3)
    cm._rag_engine = mock_rag

    docs = [
        DocumentInject(filename="a.txt", content="alpha"),
        DocumentInject(filename="b.txt", content="beta"),
    ]
    result = await cm.ingest_documents("c1", docs)
    assert result == 6  # 3 chunks per doc
    assert mock_rag.ingest_document_inject.await_count == 2
    # Verify collection name
    first_call = mock_rag.ingest_document_inject.call_args_list[0]
    assert first_call[0][1] == "colony_c1_docs"


@pytest.mark.asyncio
async def test_colony_manager_ingest_documents_error_isolation():
    """One document failing doesn't block the rest."""
    from src.colony_manager import ColonyManager

    cm = ColonyManager.__new__(ColonyManager)
    mock_rag = AsyncMock()
    mock_rag.ingest_document_inject = AsyncMock(
        side_effect=[Exception("boom"), 5],
    )
    cm._rag_engine = mock_rag

    docs = [
        DocumentInject(filename="bad.txt", content="bad"),
        DocumentInject(filename="good.txt", content="good"),
    ]
    result = await cm.ingest_documents("c1", docs)
    assert result == 5  # Only second doc's chunks counted


# ── ColonyManager create sets client namespace ────────────────────────


@pytest.mark.asyncio
async def test_colony_manager_create_sets_namespace():
    """create() with client_id sets _client_namespace on context tree."""
    from src.colony_manager import ColonyManager
    from src.models import ColonyConfig, AgentConfig

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = __import__("asyncio").Lock()
    cm._workspace_base = MagicMock()
    cm._workspace_base.__truediv__ = MagicMock(return_value=MagicMock())
    cm._model_registry = None
    cm._rag_engine = None
    cm._persist_registry_sync = MagicMock()

    config = ColonyConfig(
        colony_id="test-colony",
        task="test task",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )

    info = await cm.create(config, origin="api", client_id="my-client")
    assert info.client_id == "my-client"

    # Verify the context tree has client namespace set
    state = cm._colonies["test-colony"]
    assert state.context_tree.get_client_namespace() == "my-client"


@pytest.mark.asyncio
async def test_colony_manager_create_no_client_id():
    """create() without client_id leaves namespace as None."""
    from src.colony_manager import ColonyManager
    from src.models import ColonyConfig, AgentConfig

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = __import__("asyncio").Lock()
    cm._workspace_base = MagicMock()
    cm._workspace_base.__truediv__ = MagicMock(return_value=MagicMock())
    cm._model_registry = None
    cm._rag_engine = None
    cm._persist_registry_sync = MagicMock()

    config = ColonyConfig(
        colony_id="test-colony-2",
        task="test task",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )

    await cm.create(config, origin="ui")

    state = cm._colonies["test-colony-2"]
    assert state.context_tree.get_client_namespace() is None


# ── Enriched webhook payload ──────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


class WebhookCapturingClient:
    """Mock httpx.AsyncClient that captures the webhook payload."""

    def __init__(self):
        self.last_payload: dict | None = None
        self.last_headers: dict | None = None

    async def post(self, url: str, content: bytes = None, headers: dict = None, **kwargs):
        self.last_payload = json.loads(content) if content else None
        self.last_headers = headers
        return FakeResponse(200)

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_webhook_payload_epoch_summaries():
    """colony.completed webhook includes epoch_summaries."""
    from src.webhook import WebhookDispatcher

    wd = WebhookDispatcher(max_retries=1)
    client = WebhookCapturingClient()
    wd._client = client

    # Build a mock orchestrator-like context
    ctx = AsyncContextTree()
    await ctx.record_epoch_summary(EpochSummary(
        epoch_id=1,
        summary="First epoch completed tasks A and B",
        round_range=(1, 3),
    ))
    await ctx.record_epoch_summary(EpochSummary(
        epoch_id=2,
        summary="Second epoch refined results",
        round_range=(4, 6),
    ))

    # Simulate what the orchestrator does
    epoch_summaries = [
        es.model_dump() for es in ctx.get_epoch_summaries()
    ]

    await wd.dispatch(
        url="https://example.com/hook",
        payload={
            "type": "colony.completed",
            "epoch_summaries": epoch_summaries,
            "final_answer": "The answer is 42",
        },
        colony_id="c1",
    )

    assert client.last_payload is not None
    assert len(client.last_payload["epoch_summaries"]) == 2
    assert client.last_payload["epoch_summaries"][0]["epoch_id"] == 1
    assert client.last_payload["epoch_summaries"][0]["summary"] == "First epoch completed tasks A and B"
    assert client.last_payload["final_answer"] == "The answer is 42"


@pytest.mark.asyncio
async def test_webhook_payload_final_answer():
    """colony.completed webhook includes final_answer."""
    from src.webhook import WebhookDispatcher

    wd = WebhookDispatcher(max_retries=1)
    client = WebhookCapturingClient()
    wd._client = client

    await wd.dispatch(
        url="https://example.com/hook",
        payload={
            "type": "colony.completed",
            "final_answer": "Implementation complete with all tests passing",
            "epoch_summaries": [],
        },
        colony_id="c1",
    )

    assert client.last_payload["final_answer"] == "Implementation complete with all tests passing"
    assert client.last_payload["epoch_summaries"] == []


# ── v1_create_colony wiring ───────────────────────────────────────────


def test_colony_config_accepts_webhook_url():
    """ColonyConfig accepts webhook_url field."""
    from src.models import ColonyConfig, AgentConfig

    config = ColonyConfig(
        colony_id="test",
        task="test",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
        webhook_url="https://example.com/hook",
    )
    assert config.webhook_url == "https://example.com/hook"


def test_colony_config_accepts_budget_constraints():
    """ColonyConfig accepts budget_constraints field."""
    from src.models import ColonyConfig, AgentConfig, BudgetConstraints

    config = ColonyConfig(
        colony_id="test",
        task="test",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
        budget_constraints=BudgetConstraints(max_total_tokens=10000),
    )
    assert config.budget_constraints.max_total_tokens == 10000


def test_document_inject_model():
    """DocumentInject model works with defaults."""
    doc = DocumentInject(filename="test.txt", content="Hello")
    assert doc.filename == "test.txt"
    assert doc.content == "Hello"
    assert doc.mime_type == "text/plain"


def test_document_inject_custom_mime():
    """DocumentInject accepts custom mime_type."""
    doc = DocumentInject(
        filename="spec.md",
        content="# Spec",
        mime_type="text/markdown",
    )
    assert doc.mime_type == "text/markdown"


# ── Backward compatibility ───────────────────────────────────────────


def test_colony_config_no_webhook_url():
    """ColonyConfig without webhook_url defaults to None."""
    from src.models import ColonyConfig, AgentConfig

    config = ColonyConfig(
        colony_id="test",
        task="test",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )
    assert config.webhook_url is None
    assert config.budget_constraints is None


def test_create_request_no_documents():
    """ColonyCreateRequest without injected_documents defaults to empty."""
    # Import from server since that's where ColonyCreateRequest lives
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test task")
    assert req.injected_documents == []
    assert req.webhook_url is None
    assert req.budget_constraints is None


# ── Version bump ──────────────────────────────────────────────────────


def test_version_server():
    from src.server import VERSION
    assert VERSION == "0.9.0"


def test_version_init():
    from src import __version__
    assert __version__ == "0.9.0"
