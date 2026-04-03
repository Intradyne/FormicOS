"""Wave 88 Track B: Repo Activity addon tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


# ── Manifest tests ──


class TestManifest:
    def test_manifest_parses(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3] / "addons" / "repo-activity" / "addon.yaml"
        )
        assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert data["name"] == "repo-activity"
        assert data["version"] == "1.0.0"

    def test_manifest_has_panel(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3] / "addons" / "repo-activity" / "addon.yaml"
        )
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        panels = data.get("panels", [])
        assert len(panels) >= 1
        assert panels[0]["target"] == "workspace"
        assert panels[0]["display_type"] == "kpi_card"
        assert panels[0]["refresh_interval_s"] == 30

    def test_manifest_has_route(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3] / "addons" / "repo-activity" / "addon.yaml"
        )
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        routes = data.get("routes", [])
        assert len(routes) >= 1
        assert routes[0]["path"] == "/dashboard"

    def test_manifest_has_governed_permissions_and_refresh_trigger(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3] / "addons" / "repo-activity" / "addon.yaml"
        )
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        permissions = data.get("mcp_permissions", [])
        github = next((entry for entry in permissions if entry.get("server") == "github"), None)
        assert github is not None
        assert "list_pull_requests" in github["tools"]
        assert "get_pull_request_status" in github["tools"]

        triggers = data.get("triggers", [])
        assert any(trigger.get("type") == "manual" for trigger in triggers)


# ── Local-only mode tests ──


class TestLocalOnly:
    @pytest.mark.asyncio
    async def test_returns_kpi_card_shape(self) -> None:
        """Handler returns valid kpi_card payload."""
        from formicos.addons.repo_activity.status import get_dashboard

        result = await get_dashboard(
            {}, "ws1", "th1", runtime_context={},
        )
        assert result["display_type"] == "kpi_card"
        assert isinstance(result["items"], list)
        assert result["refresh_interval_s"] == 30

    @pytest.mark.asyncio
    async def test_works_without_workspace(self) -> None:
        """Handler degrades when no workspace is bound."""
        from formicos.addons.repo_activity.status import get_dashboard

        result = await get_dashboard(
            {}, "ws1", "th1", runtime_context={},
        )
        assert result["display_type"] == "kpi_card"
        # Status rows should mention no workspace
        statuses = result.get("_status_rows", [])
        assert any("no workspace" in s.get("value", "") for s in statuses)

    @pytest.mark.asyncio
    async def test_local_git_data_when_repo_available(self) -> None:
        """Handler returns git data when workspace is a real git repo."""
        from formicos.addons.repo_activity.status import get_dashboard

        # Use the FormicOS repo itself as workspace
        repo_root = Path(__file__).resolve().parents[3]
        ws_fn = MagicMock(return_value=repo_root)

        result = await get_dashboard(
            {}, "ws1", "th1",
            runtime_context={"workspace_root_fn": ws_fn},
        )
        items = result["items"]
        # Should have KPI items for modified files, working tree, etc.
        labels = {i["label"] for i in items}
        assert "Modified Files" in labels
        assert "Working Tree" in labels

    @pytest.mark.asyncio
    async def test_no_remote_without_gateway(self) -> None:
        """Without MCP gateway, remote section shows 'not configured'."""
        from formicos.addons.repo_activity.status import get_dashboard

        result = await get_dashboard(
            {}, "ws1", "th1", runtime_context={},
        )
        statuses = result.get("_status_rows", [])
        remote_rows = [s for s in statuses if s.get("label") == "Remote"]
        assert any("not configured" in r["value"] for r in remote_rows)


# ── Remote enrichment tests ──


class TestRemoteEnrichment:
    @pytest.mark.asyncio
    async def test_remote_data_appears_when_gateway_configured(self) -> None:
        """When gateway returns data, remote KPIs should appear."""
        from formicos.addons.repo_activity.status import _remote_enrichment

        gateway = AsyncMock()
        gateway.call_tool = AsyncMock(side_effect=[
            {"ok": True, "result": json.dumps([
                {"title": "PR 1", "number": 17},
                {"title": "PR 2", "number": 21},
            ])},
            {"ok": True, "result": json.dumps({"state": "success"})},
        ])

        result = await _remote_enrichment(
            {"mcp_gateway": gateway},
            "ws1",
            {"remote_server": "github", "repo_owner": "formicos", "repo_name": "FormicOSa"},
        )
        kpis = result["kpis"]
        assert any(k["label"] == "Open PRs" for k in kpis)
        pr_kpi = next(k for k in kpis if k["label"] == "Open PRs")
        assert pr_kpi["value"] == 2
        assert any(k["label"] == "CI" and k["value"] == "Success" for k in kpis)

    @pytest.mark.asyncio
    async def test_remote_failure_degrades_gracefully(self) -> None:
        """Gateway failure should not break the panel."""
        from formicos.addons.repo_activity.status import _remote_enrichment

        gateway = AsyncMock()
        gateway.call_tool = AsyncMock(side_effect=RuntimeError("provider down"))

        result = await _remote_enrichment(
            {"mcp_gateway": gateway},
            "ws1",
            {"remote_server": "github", "repo_owner": "formicos", "repo_name": "FormicOSa"},
        )
        statuses = result["statuses"]
        # Should degrade to "no data" or "unavailable", not crash
        remote_vals = [s["value"] for s in statuses if s["label"] == "Remote"]
        assert any(v in ("no data", "unavailable") for v in remote_vals)
        # Should NOT have any KPIs (remote failed)
        assert result["kpis"] == []

    @pytest.mark.asyncio
    async def test_cache_helper_used_when_available(self) -> None:
        """Team C's cache helper should be consulted before gateway call."""
        from formicos.addons.repo_activity.cache import EnrichmentCache
        from formicos.addons.repo_activity.status import _remote_enrichment

        cache = EnrichmentCache(ttl_s=300)
        cache.put("ws1", "github:formicos/FormicOSa", "/dashboard", {
            "open_prs": 3,
            "ci_status": "success",
        })
        gateway = AsyncMock()

        result = await _remote_enrichment(
            {"mcp_gateway": gateway, "addon_cache": cache},
            "ws1",
            {"remote_server": "github", "repo_owner": "formicos", "repo_name": "FormicOSa"},
        )
        # Should use cached data, not call gateway
        gateway.call_tool.assert_not_called()
        kpis = result["kpis"]
        assert any(k["label"] == "Open PRs" and k["value"] == 3 for k in kpis)


# ── Git command helper tests ──


class TestGitCmd:
    @pytest.mark.asyncio
    async def test_git_cmd_returns_output(self) -> None:
        """_git_cmd should return stdout for successful commands."""
        from formicos.addons.repo_activity.status import _git_cmd

        repo_root = str(Path(__file__).resolve().parents[3])
        result = await _git_cmd(["git", "branch", "--show-current"], repo_root)
        assert result is not None
        assert len(result) > 0  # should have a branch name

    @pytest.mark.asyncio
    async def test_git_cmd_returns_none_on_failure(self) -> None:
        """_git_cmd should return None for failing commands."""
        from formicos.addons.repo_activity.status import _git_cmd

        result = await _git_cmd(
            ["git", "log", "--oneline", "-1"],
            "/nonexistent/path",
        )
        assert result is None
