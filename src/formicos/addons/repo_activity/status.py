"""Repo Activity addon handler — local git + optional remote enrichment.

Returns declarative kpi_card payloads for the workspace-mounted panel.
Local git data is always live (cheap subprocess calls). Remote data
(PRs, CI) comes through the governed MCP gateway and is cached by
Team C's refresh helper.

Read-only. No mutation actions.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger()


async def get_dashboard(
    inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return repo activity dashboard as a kpi_card payload."""
    ctx = runtime_context or {}
    ws_id = inputs.get("workspace_id", "") or workspace_id or "default"
    workspace_root_fn = ctx.get("workspace_root_fn")
    ws_path = workspace_root_fn(ws_id) if workspace_root_fn else None

    kpi_items: list[dict[str, Any]] = []
    status_items: list[dict[str, str]] = []

    # -- Local git layer (always available) --
    local = await _local_git_status(ws_path)
    kpi_items.extend(local["kpis"])
    status_items.extend(local["statuses"])

    # -- Optional remote enrichment --
    remote = await _remote_enrichment(ctx, ws_id, local.get("repo_meta", {}))
    kpi_items.extend(remote["kpis"])
    status_items.extend(remote["statuses"])

    # -- Meta --
    status_items.append({
        "label": "Last Refresh",
        "value": datetime.now(UTC).strftime("%H:%M:%S UTC"),
    })

    return {
        "display_type": "kpi_card",
        "refresh_interval_s": 30,
        "items": kpi_items,
        "_status_rows": status_items,
    }


# ---------------------------------------------------------------------------
# Local git layer
# ---------------------------------------------------------------------------


async def _local_git_status(
    ws_path: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Gather local git state via subprocess calls."""
    kpis: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []

    repo_meta: dict[str, Any] = {}
    if not ws_path or not ws_path.is_dir():
        statuses.append({"label": "Repo", "value": "no workspace bound"})
        return {"kpis": kpis, "statuses": statuses, "repo_meta": repo_meta}

    cwd = str(ws_path)

    # Branch
    branch = await _git_cmd(["git", "branch", "--show-current"], cwd)
    if branch is None:
        statuses.append({"label": "Repo", "value": "git unavailable"})
        return {"kpis": kpis, "statuses": statuses, "repo_meta": repo_meta}

    statuses.append({"label": "Branch", "value": branch or "detached HEAD"})

    # Modified files
    porcelain = await _git_cmd(["git", "status", "--porcelain"], cwd)
    modified_lines = [
        ln for ln in (porcelain or "").splitlines() if ln.strip()
    ]
    modified_count = len(modified_lines)
    mod_status = (
        "ok" if modified_count == 0
        else "warn" if modified_count <= 5
        else "error"
    )
    kpis.append({
        "label": "Modified Files",
        "value": modified_count,
        "status": mod_status,
    })

    # Recent commits
    log_output = await _git_cmd(
        ["git", "log", "--oneline", "-n", "5", "--no-decorate"], cwd,
    )
    commits = [ln.strip() for ln in (log_output or "").splitlines() if ln.strip()]

    if commits:
        kpis.append({
            "label": "Recent Commits",
            "value": len(commits),
        })
        # Last commit as status row
        statuses.append({"label": "Last Commit", "value": commits[0][:60]})

    # Diff stat
    diff_stat = await _git_cmd(["git", "diff", "--stat", "--shortstat"], cwd)
    if diff_stat and diff_stat.strip():
        last_line = diff_stat.strip().splitlines()[-1].strip()
        statuses.append({"label": "Diff Summary", "value": last_line[:80]})

    # Clean/dirty indicator
    clean = modified_count == 0
    kpis.append({
        "label": "Working Tree",
        "value": "Clean" if clean else "Dirty",
        "status": "ok" if clean else "warn",
    })

    origin_url = await _git_cmd(["git", "remote", "get-url", "origin"], cwd)
    if origin_url:
        parsed_remote = _parse_remote_origin(origin_url)
        if parsed_remote:
            repo_meta.update(parsed_remote)
            statuses.append({
                "label": "Remote Repo",
                "value": f"{parsed_remote['repo_owner']}/{parsed_remote['repo_name']}",
            })

    return {"kpis": kpis, "statuses": statuses, "repo_meta": repo_meta}


async def _git_cmd(cmd: list[str], cwd: str) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    def _run() -> str | None:
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except Exception:  # noqa: BLE001
            return None
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Remote enrichment (optional, degradable)
# ---------------------------------------------------------------------------


async def _remote_enrichment(
    ctx: dict[str, Any],
    workspace_id: str,
    repo_meta: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Enrich with remote data via governed MCP gateway.

    Degrades gracefully to empty when:
    - no MCP gateway is configured
    - auth is unavailable
    - the provider is down
    - the governed gateway denies a tool
    """
    kpis: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    repo_meta = repo_meta or {}

    # Check for governed MCP gateway
    gateway = ctx.get("mcp_gateway")
    if gateway is None:
        statuses.append({"label": "Remote", "value": "not configured"})
        return {"kpis": kpis, "statuses": statuses}

    # Check for Team C's cache helper
    cache_helper = ctx.get("addon_cache")
    remote_cfg = _build_remote_config(ctx, workspace_id, repo_meta)

    if not remote_cfg["server"]:
        statuses.append({"label": "Remote", "value": "not configured"})
        return {"kpis": kpis, "statuses": statuses}

    try:
        remote_data = await _fetch_remote_data(
            gateway, workspace_id, cache_helper, remote_cfg,
        )
        if remote_data:
            if remote_data.get("error"):
                statuses.append({"label": "Remote", "value": "unavailable"})
                if remote_data.get("cache_age_s") is not None:
                    statuses.append({
                        "label": "Cache Age",
                        "value": f"{remote_data['cache_age_s']}s",
                    })
                return {"kpis": kpis, "statuses": statuses}

            # Open PRs / MRs
            pr_count = remote_data.get("open_prs", 0)
            kpis.append({
                "label": "Open PRs",
                "value": pr_count,
                "status": "ok" if pr_count < 5 else "warn",
            })

            # CI health
            ci_status = remote_data.get("ci_status", "")
            if ci_status:
                ci_health = (
                    "ok" if ci_status in ("passing", "success")
                    else "error" if ci_status in ("failing", "failed")
                    else "warn"
                )
                kpis.append({
                    "label": "CI",
                    "value": ci_status.title(),
                    "status": ci_health,
                })

            statuses.append({"label": "Remote", "value": "connected"})

            # Cache freshness
            cache_age = remote_data.get("cache_age_s")
            if cache_age is not None:
                statuses.append({
                    "label": "Cache Age",
                    "value": f"{cache_age}s",
                })
        else:
            statuses.append({"label": "Remote", "value": "no data"})
    except Exception:  # noqa: BLE001
        log.debug(
            "repo_activity.remote_enrichment_failed",
            workspace_id=workspace_id,
        )
        statuses.append({"label": "Remote", "value": "unavailable"})

    return {"kpis": kpis, "statuses": statuses}


async def _fetch_remote_data(
    gateway: Any,
    workspace_id: str,
    cache_helper: Any,
    remote_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch remote repo data through governed gateway with optional caching.

    Returns None when the gateway or cache returns no usable data.
    """
    route = "/dashboard"
    remote_target = (
        f"{remote_cfg['server']}:{remote_cfg.get('repo_owner', '')}/"
        f"{remote_cfg.get('repo_name', '')}"
    ).strip(":/")

    # Use Team C's cache helper if available
    if cache_helper is not None:
        try:
            cached = cache_helper.get(workspace_id, remote_target, route)
            if cached is not None and not cached.expired:
                payload = dict(cached.data)
                freshness = cached.freshness
                payload["cache_age_s"] = freshness["age_s"]
                if cached.is_error:
                    payload["error"] = cached.error_message or "remote unavailable"
                return payload
        except Exception:  # noqa: BLE001
            pass

    # Direct gateway call (governed)
    if gateway is None:
        return None

    try:
        pr_args = _build_remote_args(remote_cfg)
        pr_result = await gateway.call_tool(
            remote_cfg["server"],
            remote_cfg["pr_tool"],
            pr_args,
        )
        pr_items = _extract_items_from_gateway_result(pr_result)
        ci_status = ""
        ci_tool = remote_cfg.get("ci_tool") or ""
        if ci_tool:
            ci_args = _build_ci_args(remote_cfg, pr_items or [])
            if ci_args is not None:
                ci_result = await gateway.call_tool(
                    remote_cfg["server"],
                    ci_tool,
                    ci_args,
                )
                ci_status = _extract_ci_status(ci_result)
        if pr_items is not None or ci_status:
            data = {
                "open_prs": len(pr_items or []),
                "ci_status": ci_status,
                "cache_age_s": 0,
            }
            # Cache the result via Team C's helper
            if cache_helper is not None:
                import contextlib  # noqa: PLC0415

                with contextlib.suppress(Exception):
                    cache_helper.put(
                        workspace_id,
                        remote_target,
                        route,
                        {k: v for k, v in data.items() if k != "cache_age_s"},
                    )
            return data
    except Exception:  # noqa: BLE001
        log.debug("repo_activity.remote_fetch_failed", exc_info=True)

    if cache_helper is not None:
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            cache_helper.put_error(
                workspace_id,
                remote_target,
                route,
                "remote unavailable",
            )

    return {"error": "remote unavailable"}


def _build_remote_config(
    ctx: dict[str, Any],
    workspace_id: str,
    repo_meta: dict[str, Any],
) -> dict[str, Any]:
    """Resolve remote enrichment config from workspace config and repo meta."""
    server = _get_addon_config_value(ctx, workspace_id, "remote_server", "")
    repo_owner = _get_addon_config_value(ctx, workspace_id, "repo_owner", "")
    repo_name = _get_addon_config_value(ctx, workspace_id, "repo_name", "")
    inferred_server = repo_meta.get("remote_server", "")

    if not server:
        server = inferred_server
    if not repo_owner:
        repo_owner = repo_meta.get("repo_owner", "")
    if not repo_name:
        repo_name = repo_meta.get("repo_name", "")

    default_pr_tools = {
        "github": "list_pull_requests",
        "gitlab": "list_merge_requests",
    }
    default_ci_tools = {
        "github": "get_pull_request_status",
        "gitlab": "list_pipelines",
    }
    pr_tool = _get_addon_config_value(ctx, workspace_id, "pr_tool", "")
    ci_tool = _get_addon_config_value(ctx, workspace_id, "ci_tool", "")

    if not pr_tool:
        pr_tool = default_pr_tools.get(server, "list_pull_requests")
    if not ci_tool:
        ci_tool = default_ci_tools.get(server, "")

    return {
        "server": server,
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "pr_tool": pr_tool,
        "ci_tool": ci_tool,
    }


def _get_addon_config_value(
    ctx: dict[str, Any],
    workspace_id: str,
    key: str,
    default: Any,
) -> Any:
    """Read repo-activity addon config from the workspace projection."""
    try:
        projections = ctx.get("projections")
        ws_proj = getattr(projections, "workspaces", {}).get(workspace_id)
        ws_config = getattr(ws_proj, "config", {}) if ws_proj is not None else {}
        raw_value = ws_config.get(f"addon.repo-activity.{key}")
        if raw_value is None:
            return default
        if isinstance(raw_value, str):
            try:
                return json.loads(raw_value)
            except (TypeError, ValueError):
                return raw_value
        return raw_value
    except Exception:  # noqa: BLE001
        return default


def _build_remote_args(remote_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build provider-friendly call arguments for read-only repo tools."""
    owner = remote_cfg.get("repo_owner", "")
    repo = remote_cfg.get("repo_name", "")
    project = f"{owner}/{repo}".strip("/")
    args = {
        "owner": owner,
        "repo": repo,
        "project": project,
        "state": "open",
        "limit": 10,
        "per_page": 10,
    }
    return {k: v for k, v in args.items() if v not in ("", None)}


def _build_ci_args(
    remote_cfg: dict[str, Any],
    pr_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build provider-specific CI/status lookup args."""
    ci_tool = remote_cfg.get("ci_tool", "")
    base_args = _build_remote_args(remote_cfg)

    if ci_tool == "get_pull_request_status":
        pr_number = _extract_pull_number(pr_items)
        if pr_number is None:
            return None
        return {
            "owner": remote_cfg.get("repo_owner", ""),
            "repo": remote_cfg.get("repo_name", ""),
            "pull_number": pr_number,
        }

    return base_args


def _extract_pull_number(pr_items: list[dict[str, Any]]) -> int | None:
    """Extract a PR number from a list response."""
    for item in pr_items:
        if not isinstance(item, dict):
            continue
        for key in ("number", "pull_number", "iid"):
            value = item.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _extract_items_from_gateway_result(result: Any) -> list[dict[str, Any]] | None:
    """Parse the governed gateway result into a list of dict items."""
    payload = _unwrap_gateway_result(result)
    if payload is None:
        return None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "pull_requests", "merge_requests", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return None


def _extract_ci_status(result: Any) -> str:
    """Parse a CI/pipeline status string from a gateway result."""
    payload = _unwrap_gateway_result(result)
    if payload is None:
        return ""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            for key in ("status", "conclusion", "state", "result"):
                value = first.get(key)
                if isinstance(value, str) and value:
                    return value.lower()
    if isinstance(payload, dict):
        for key in ("status", "conclusion", "state", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value.lower()
    if isinstance(payload, str):
        lowered = payload.lower()
        for token in ("passing", "success", "failing", "failed", "running"):
            if token in lowered:
                return token
    return ""


def _unwrap_gateway_result(result: Any) -> Any:
    """Normalize gateway results from dict/text/test-double forms."""
    if result is None:
        return None
    if isinstance(result, dict) and "ok" in result:
        if not result.get("ok"):
            return None
        result = result.get("result")
    if isinstance(result, (list, dict)):
        return result
    if isinstance(result, str):
        text = result.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fall back to counting line-oriented textual items
            lines = [ln.strip("- ").strip() for ln in text.splitlines() if ln.strip()]
            if len(lines) > 1:
                return [{"text": line} for line in lines]
            return text
    return None


_HTTPS_REMOTE_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
)
_SSH_REMOTE_RE = re.compile(
    r"^(?:git@|ssh://git@)(?P<host>[^:/]+)[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
)


def _parse_remote_origin(origin_url: str) -> dict[str, str] | None:
    """Parse a git remote URL into provider and repo identity."""
    text = origin_url.strip()
    match = _HTTPS_REMOTE_RE.match(text) or _SSH_REMOTE_RE.match(text)
    if match is None:
        return None
    host = match.group("host").lower()
    remote_server = ""
    if "github" in host:
        remote_server = "github"
    elif "gitlab" in host:
        remote_server = "gitlab"
    return {
        "remote_host": host,
        "remote_server": remote_server,
        "repo_owner": match.group("owner"),
        "repo_name": match.group("repo"),
    }
