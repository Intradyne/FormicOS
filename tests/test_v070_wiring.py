"""
FormicOS v0.7.0 — Runtime Wiring Tests

Verifies that ColonyManager.start() and .resume() correctly wire
archivist, governance, skill_bank, and audit_logger into the Orchestrator.
Also tests RuntimeWiringContract validation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.colony_manager import ColonyManager
from src.models import (
    ColonyConfig,
    ColonyStatus,
    AgentConfig,
    RuntimeWiringContract,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_config():
    """Return a minimal FormicOSConfig-like object."""
    config = MagicMock()
    config.inference.model = "test-model"
    config.inference.model_alias = None
    config.inference.timeout_seconds = 60
    config.model_registry = {}
    config.governance.max_rounds = 10
    config.governance.convergence_threshold = 0.92
    config.governance.stall_window = 3
    return config


def _make_model_registry():
    """Return a mock ModelRegistry whose get_client returns (client, model)."""
    registry = MagicMock()
    mock_client = MagicMock()  # AsyncOpenAI mock
    registry.get_client.return_value = (mock_client, "test-model-string")
    return registry


def _make_colony_manager(
    config=None,
    model_registry=None,
    skill_bank=None,
    audit_logger=None,
    approval_gate=None,
    embedder=None,
):
    """Build a ColonyManager with mocked dependencies."""
    cfg = config or _make_config()
    mr = model_registry or _make_model_registry()

    with patch.object(ColonyManager, "_load_registry_sync"):
        cm = ColonyManager(
            config=cfg,
            model_registry=mr,
            session_manager=MagicMock(),
            rag_engine=None,
            mcp_client=None,
            embedder=embedder,
            skill_bank=skill_bank,
            audit_logger=audit_logger,
            approval_gate=approval_gate,
        )
    return cm


def _make_colony_config(colony_id: str = "test-colony") -> ColonyConfig:
    """Minimal ColonyConfig."""
    return ColonyConfig(
        colony_id=colony_id,
        task="test task",
        max_rounds=3,
        agents=[
            AgentConfig(agent_id="a1", caste="analyst"),
        ],
    )


# ── Constructor Tests ─────────────────────────────────────────────────────


def test_constructor_stores_skill_bank():
    sb = MagicMock()
    cm = _make_colony_manager(skill_bank=sb)
    assert cm._skill_bank is sb


def test_constructor_stores_audit_logger():
    al = MagicMock()
    cm = _make_colony_manager(audit_logger=al)
    assert cm._audit_logger is al


def test_constructor_stores_approval_gate():
    ag = MagicMock()
    cm = _make_colony_manager(approval_gate=ag)
    assert cm._approval_gate is ag


def test_constructor_defaults_none():
    cm = _make_colony_manager()
    assert cm._skill_bank is None
    assert cm._audit_logger is None
    assert cm._approval_gate is None


# ── Start Wiring Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_colony_start_wires_archivist():
    """Orchestrator receives an Archivist when ColonyManager.start() runs."""
    cm = _make_colony_manager(skill_bank=MagicMock(), audit_logger=MagicMock())
    colony_cfg = _make_colony_config()
    await cm.create(colony_cfg)

    with (
        patch("src.orchestrator.Orchestrator") as MockOrch,
        patch("src.agents.AgentFactory") as MockAF,
        patch("src.archivist.Archivist") as MockArch,
        patch("src.governance.GovernanceEngine") as _MockGov,
    ):
        mock_factory = MagicMock()
        mock_factory.create.return_value = MagicMock()
        MockAF.return_value = mock_factory

        mock_orch = AsyncMock()
        mock_orch.run = AsyncMock()
        MockOrch.return_value = mock_orch

        mock_archivist = MagicMock()
        MockArch.return_value = mock_archivist

        # Patch _run_colony to avoid actual execution
        with patch.object(cm, "_run_colony", new_callable=AsyncMock):
            await cm.start("test-colony")

        # Verify Archivist was passed to Orchestrator
        MockOrch.assert_called_once()
        call_kwargs = MockOrch.call_args
        assert call_kwargs.kwargs.get("archivist") is mock_archivist


@pytest.mark.asyncio
async def test_colony_start_wires_governance():
    """Orchestrator receives a GovernanceEngine."""
    cm = _make_colony_manager(skill_bank=MagicMock(), audit_logger=MagicMock())
    colony_cfg = _make_colony_config()
    await cm.create(colony_cfg)

    with (
        patch("src.orchestrator.Orchestrator") as MockOrch,
        patch("src.agents.AgentFactory") as MockAF,
        patch("src.archivist.Archivist"),
        patch("src.governance.GovernanceEngine") as MockGov,
    ):
        mock_factory = MagicMock()
        mock_factory.create.return_value = MagicMock()
        MockAF.return_value = mock_factory
        MockOrch.return_value = AsyncMock()

        mock_governance = MagicMock()
        MockGov.return_value = mock_governance

        with patch.object(cm, "_run_colony", new_callable=AsyncMock):
            await cm.start("test-colony")

        call_kwargs = MockOrch.call_args
        assert call_kwargs.kwargs.get("governance") is mock_governance


@pytest.mark.asyncio
async def test_colony_start_wires_skill_bank():
    """Orchestrator receives the shared skill_bank."""
    mock_sb = MagicMock()
    cm = _make_colony_manager(skill_bank=mock_sb, audit_logger=MagicMock())
    colony_cfg = _make_colony_config()
    await cm.create(colony_cfg)

    with (
        patch("src.orchestrator.Orchestrator") as MockOrch,
        patch("src.agents.AgentFactory") as MockAF,
        patch("src.archivist.Archivist"),
        patch("src.governance.GovernanceEngine"),
    ):
        mock_factory = MagicMock()
        mock_factory.create.return_value = MagicMock()
        MockAF.return_value = mock_factory
        MockOrch.return_value = AsyncMock()

        with patch.object(cm, "_run_colony", new_callable=AsyncMock):
            await cm.start("test-colony")

        call_kwargs = MockOrch.call_args
        assert call_kwargs.kwargs.get("skill_bank") is mock_sb


@pytest.mark.asyncio
async def test_colony_start_wires_audit_logger():
    """Orchestrator receives the audit_logger."""
    mock_al = MagicMock()
    cm = _make_colony_manager(skill_bank=MagicMock(), audit_logger=mock_al)
    colony_cfg = _make_colony_config()
    await cm.create(colony_cfg)

    with (
        patch("src.orchestrator.Orchestrator") as MockOrch,
        patch("src.agents.AgentFactory") as MockAF,
        patch("src.archivist.Archivist"),
        patch("src.governance.GovernanceEngine"),
    ):
        mock_factory = MagicMock()
        mock_factory.create.return_value = MagicMock()
        MockAF.return_value = mock_factory
        MockOrch.return_value = AsyncMock()

        with patch.object(cm, "_run_colony", new_callable=AsyncMock):
            await cm.start("test-colony")

        call_kwargs = MockOrch.call_args
        assert call_kwargs.kwargs.get("audit_logger") is mock_al


# ── Resume Wiring Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_colony_resume_wires_all_deps():
    """resume() wires archivist, governance, skill_bank, audit_logger."""
    mock_sb = MagicMock()
    mock_al = MagicMock()
    cm = _make_colony_manager(skill_bank=mock_sb, audit_logger=mock_al)
    colony_cfg = _make_colony_config()
    await cm.create(colony_cfg)

    # Manually set state to PAUSED so resume is valid
    state = cm._colonies["test-colony"]
    state.info.status = ColonyStatus.PAUSED

    with (
        patch("src.orchestrator.Orchestrator") as MockOrch,
        patch("src.agents.AgentFactory") as MockAF,
        patch("src.archivist.Archivist") as MockArch,
        patch("src.governance.GovernanceEngine") as MockGov,
    ):
        mock_factory = MagicMock()
        mock_factory.create.return_value = MagicMock()
        MockAF.return_value = mock_factory
        MockOrch.return_value = AsyncMock()

        mock_archivist = MagicMock()
        MockArch.return_value = mock_archivist
        mock_governance = MagicMock()
        MockGov.return_value = mock_governance

        with patch.object(cm, "_run_colony", new_callable=AsyncMock):
            await cm.resume("test-colony")

        call_kwargs = MockOrch.call_args
        assert call_kwargs.kwargs.get("archivist") is mock_archivist
        assert call_kwargs.kwargs.get("governance") is mock_governance
        assert call_kwargs.kwargs.get("skill_bank") is mock_sb
        assert call_kwargs.kwargs.get("audit_logger") is mock_al


# ── Wiring Contract Validation ────────────────────────────────────────────


def test_wiring_contract_all_present():
    wc = RuntimeWiringContract(
        model_registry=True,
        archivist=True,
        governance=True,
        skill_bank=True,
        audit_logger=True,
        approval_gate=True,
        rag_engine=True,
    )
    assert wc.validate_mandatory() == []


def test_wiring_contract_missing_archivist():
    wc = RuntimeWiringContract(
        model_registry=True,
        archivist=False,
        governance=True,
        skill_bank=True,
        audit_logger=True,
        approval_gate=True,
    )
    assert "archivist" in wc.validate_mandatory()


def test_wiring_contract_missing_multiple():
    wc = RuntimeWiringContract(
        model_registry=True,
        archivist=False,
        governance=False,
        skill_bank=True,
        audit_logger=False,
        approval_gate=True,
    )
    missing = wc.validate_mandatory()
    assert "archivist" in missing
    assert "governance" in missing
    assert "audit_logger" in missing
    assert len(missing) == 3


def test_wiring_contract_rag_optional():
    """RAG engine is NOT mandatory — omitting it should not appear in missing."""
    wc = RuntimeWiringContract(
        model_registry=True,
        archivist=True,
        governance=True,
        skill_bank=True,
        audit_logger=True,
        approval_gate=True,
        rag_engine=False,
    )
    assert wc.validate_mandatory() == []


def test_wiring_contract_defaults_all_false():
    wc = RuntimeWiringContract()
    missing = wc.validate_mandatory()
    assert len(missing) == 6  # all mandatory fields
