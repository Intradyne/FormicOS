"""Wave 64 Track 6a: Addon manifest loader and component registration.

Reads ``addons/*/addon.yaml`` manifests, validates required fields, and
registers addon components into existing registries (queen tools, service
handlers, colony templates).
"""
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

class AddonToolSpec(BaseModel):
    """A tool declared by an addon manifest."""

    name: str
    description: str = ""
    handler: str = Field(..., description="module.py::function_name")
    parameters: dict[str, Any] = Field(default_factory=dict)


class AddonHandlerSpec(BaseModel):
    """An event handler declared by an addon manifest."""

    event: str
    handler: str = Field(..., description="module.py::function_name")


class AddonTriggerSpec(BaseModel):
    """A trigger declared by an addon manifest."""

    type: str = Field(..., description="cron | event | webhook | manual")
    schedule: str = ""
    handler: str = Field(..., description="module.py::function_name")


class AddonConfigParam(BaseModel):
    """A configurable parameter declared by an addon."""

    key: str
    type: str = Field(default="string", description="boolean | string | integer | cron | select")
    default: Any = None
    label: str = ""
    options: list[str] = Field(default_factory=list)


class AddonManifest(BaseModel):
    """Parsed addon.yaml manifest."""

    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    tools: list[AddonToolSpec] = Field(default_factory=list)
    handlers: list[AddonHandlerSpec] = Field(default_factory=list)
    config: list[AddonConfigParam] = Field(default_factory=list)
    panels: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list)
    triggers: list[AddonTriggerSpec] = Field(default_factory=list)
    hidden: bool = False  # Hide from operator UI (dev scaffolds)
    # Wave 68 Track 5: capability metadata for Queen routing
    content_kinds: list[str] = Field(default_factory=list)
    path_globs: list[str] = Field(default_factory=list)
    search_tool: str = Field(default="")
    # Wave 88 Track A: per-addon MCP permissions
    mcp_permissions: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Handler resolution
# ---------------------------------------------------------------------------

def _resolve_handler(addon_name: str, handler_ref: str) -> Callable[..., Any]:
    """Resolve a ``module.py::function_name`` handler reference.

    Handler paths are resolved relative to ``formicos.addons.<addon_name>``.
    For example ``rules/__init__.py::handle_query_briefing`` in addon
    ``proactive-intelligence`` resolves to
    ``formicos.addons.proactive_intelligence.rules::handle_query_briefing``.
    """
    if "::" not in handler_ref:
        raise ValueError(
            f"Addon '{addon_name}' handler '{handler_ref}' must use "
            "'module.py::function_name' format"
        )
    module_path, func_name = handler_ref.rsplit("::", 1)
    # Strip .py suffix and convert slashes to dots
    module_path = module_path.removesuffix(".py").replace("/", ".").replace("\\", ".")
    # Build fully-qualified module name
    package_name = addon_name.replace("-", "_")
    fq_module = f"formicos.addons.{package_name}.{module_path}"
    module = importlib.import_module(fq_module)
    func = getattr(module, func_name, None)
    if func is None:
        raise AttributeError(
            f"Addon '{addon_name}' handler function '{func_name}' "
            f"not found in module '{fq_module}'"
        )
    if not inspect.iscoroutinefunction(func):
        log.warning(
            "addon_loader.sync_handler",
            addon=addon_name,
            handler=handler_ref,
            hint="Handler is not async — it will be wrapped automatically, "
                 "but addon handlers should be declared async.",
        )

        async def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return _sync_wrapper  # type: ignore[return-value]
    return func  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_addon_manifest(manifest_path: Path) -> AddonManifest:
    """Parse a single addon.yaml file into an ``AddonManifest``."""
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid addon manifest at {manifest_path}: expected mapping")
    return AddonManifest(**raw)  # pyright: ignore[reportUnknownArgumentType]


def discover_addons(addons_dir: Path) -> list[AddonManifest]:
    """Discover all addon manifests in ``addons/*/addon.yaml``."""
    manifests: list[AddonManifest] = []
    if not addons_dir.is_dir():
        return manifests
    for child in sorted(addons_dir.iterdir()):
        manifest_file = child / "addon.yaml"
        if child.is_dir() and manifest_file.is_file():
            try:
                manifest = load_addon_manifest(manifest_file)
                manifests.append(manifest)
                log.info(
                    "addon_loader.discovered",
                    addon=manifest.name,
                    version=manifest.version,
                )
            except Exception:  # noqa: BLE001
                log.warning(
                    "addon_loader.manifest_error",
                    path=str(manifest_file),
                    exc_info=True,
                )
    return manifests


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class AddonRegistration:
    """Result of registering an addon — tracks what was registered."""

    def __init__(self, manifest: AddonManifest) -> None:
        self.manifest = manifest
        self.registered_tools: list[str] = []
        self.registered_handlers: list[str] = []
        self.registered_routes: list[dict[str, Any]] = []
        self.registered_panels: list[dict[str, Any]] = []
        self.runtime_context: dict[str, Any] = {}
        # Wave 66 T1: health monitoring counters
        self.tool_call_counts: dict[str, int] = {}
        self.last_tool_call: str | None = None
        self.handler_error_count: int = 0
        self.last_handler_fire: str | None = None
        self.last_error: str | None = None
        self.trigger_fire_times: dict[str, str | None] = {}
        self.disabled: bool = False

    @property
    def health_status(self) -> str:
        """Derive health from error counts: 0=healthy, 1-2=degraded, 3+=error."""
        if self.handler_error_count >= 3:
            return "error"
        if self.handler_error_count >= 1:
            return "degraded"
        return "healthy"


def register_addon(
    manifest: AddonManifest,
    *,
    tool_registry: dict[str, Callable[..., Any]] | None = None,
    service_router: Any | None = None,
    runtime_context: dict[str, Any] | None = None,
) -> AddonRegistration:
    """Register an addon's components into existing registries.

    Parameters
    ----------
    manifest:
        Parsed addon manifest.
    tool_registry:
        The ``QueenToolDispatcher._handlers`` dict. If provided, addon tools
        are registered as handlers.
    service_router:
        The colony manager's ``ServiceRouter``. If provided, addon event
        handlers are registered.

    Returns
    -------
    AddonRegistration with the list of successfully registered components.
    """
    result = AddonRegistration(manifest)
    _ctx = runtime_context or {}
    result.runtime_context = _ctx

    # Register tools
    for tool_spec in manifest.tools:
        try:
            handler_fn = _resolve_handler(manifest.name, tool_spec.handler)
            if tool_registry is not None:
                # Wrap addon handler to match queen_tools signature.
                # If the handler accepts runtime_context, pass it through.
                _fn = handler_fn
                try:
                    _accepts_ctx = "runtime_context" in inspect.signature(_fn).parameters
                except (ValueError, TypeError):
                    _accepts_ctx = False

                async def _tool_wrapper(
                    inputs: dict[str, Any],
                    workspace_id: str,
                    thread_id: str,
                    *,
                    _bound_fn: Callable[..., Any] = _fn,
                    _pass_ctx: bool = _accepts_ctx,
                    _bound_ctx: dict[str, Any] = _ctx,
                    _tool_name: str = tool_spec.name,
                    _reg: AddonRegistration = result,
                ) -> Any:
                    if _reg.disabled:
                        return f"Addon '{_reg.manifest.name}' is currently disabled."
                    from datetime import UTC, datetime
                    _reg.tool_call_counts[_tool_name] = (
                        _reg.tool_call_counts.get(_tool_name, 0) + 1
                    )
                    _reg.last_tool_call = datetime.now(UTC).isoformat()
                    if _pass_ctx:
                        return await _bound_fn(
                            inputs, workspace_id, thread_id,
                            runtime_context=_bound_ctx,
                        )
                    return await _bound_fn(inputs, workspace_id, thread_id)

                tool_registry[tool_spec.name] = _tool_wrapper
                result.registered_tools.append(tool_spec.name)
                log.info(
                    "addon_loader.tool_registered",
                    addon=manifest.name,
                    tool=tool_spec.name,
                )
        except Exception:  # noqa: BLE001
            log.warning(
                "addon_loader.tool_registration_failed",
                addon=manifest.name,
                tool=tool_spec.name,
                exc_info=True,
            )

    # Register event handlers
    for handler_spec in manifest.handlers:
        try:
            handler_fn = _resolve_handler(manifest.name, handler_spec.handler)
            if service_router is not None:
                # Wrap event handler to inject runtime_context if accepted.
                _efn = handler_fn
                try:
                    _handler_accepts_ctx = "runtime_context" in inspect.signature(_efn).parameters
                except (ValueError, TypeError):
                    _handler_accepts_ctx = False

                if _handler_accepts_ctx:
                    async def _event_wrapper(
                        event: Any,
                        *,
                        _bound_efn: Callable[..., Any] = _efn,
                        _bound_ctx: dict[str, Any] = _ctx,
                        _reg: AddonRegistration = result,
                        _evt_name: str = handler_spec.event,
                        **kwargs: Any,
                    ) -> Any:
                        if _reg.disabled:
                            log.debug(
                                "addon_loader.handler_skipped_disabled",
                                addon=_reg.manifest.name,
                                event=_evt_name,
                            )
                            return None
                        from datetime import UTC, datetime
                        _reg.last_handler_fire = datetime.now(UTC).isoformat()
                        try:
                            return await _bound_efn(
                                event, runtime_context=_bound_ctx, **kwargs,
                            )
                        except Exception:
                            _reg.handler_error_count += 1
                            _reg.last_error = (
                                f"{_evt_name}: "
                                f"{datetime.now(UTC).isoformat()}"
                            )
                            raise

                    svc_name = f"addon:{manifest.name}:{handler_spec.event}"
                    service_router.register_handler(svc_name, _event_wrapper)
                else:
                    _plain_efn = handler_fn
                    _plain_reg = result

                    async def _plain_event_wrapper(
                        event: Any,
                        *,
                        _bound_efn: Callable[..., Any] = _plain_efn,
                        _reg: AddonRegistration = _plain_reg,
                        **kwargs: Any,
                    ) -> Any:
                        if _reg.disabled:
                            return None
                        return await _bound_efn(event, **kwargs)

                    svc_name = f"addon:{manifest.name}:{handler_spec.event}"
                    service_router.register_handler(svc_name, _plain_event_wrapper)

                result.registered_handlers.append(svc_name)
                log.info(
                    "addon_loader.handler_registered",
                    addon=manifest.name,
                    handler_event=handler_spec.event,
                    service=svc_name,
                )
        except Exception:  # noqa: BLE001
            log.warning(
                "addon_loader.handler_registration_failed",
                addon=manifest.name,
                handler_event=handler_spec.event,
                exc_info=True,
            )

    # Register routes
    for route_spec in manifest.routes:
        handler_ref = route_spec.get("handler", "")
        route_path = route_spec.get("path", "")
        if not handler_ref or not route_path:
            continue
        try:
            handler_fn = _resolve_handler(manifest.name, handler_ref)
            result.registered_routes.append({
                "path": route_path,
                "handler": handler_fn,
                "addon_name": manifest.name,
            })
            log.info(
                "addon_loader.route_registered",
                addon=manifest.name,
                path=route_path,
            )
        except Exception:  # noqa: BLE001
            log.warning(
                "addon_loader.route_registration_failed",
                addon=manifest.name,
                path=route_path,
                exc_info=True,
            )

    # Register panels
    for panel_spec in manifest.panels:
        panel_entry: dict[str, Any] = {
            "target": panel_spec.get("target", ""),
            "display_type": panel_spec.get("display_type", "status_card"),
            "path": panel_spec.get("path", ""),
            "addon_name": manifest.name,
        }
        # Wave 87: preserve refresh interval for frontend polling
        if "refresh_interval_s" in panel_spec:
            panel_entry["refresh_interval_s"] = int(
                panel_spec["refresh_interval_s"],
            )
        result.registered_panels.append(panel_entry)
        log.info(
            "addon_loader.panel_registered",
            addon=manifest.name,
            target=panel_spec.get("target", ""),
        )

    # Warn about templates (still unimplemented)
    if manifest.templates:
        log.warning(
            "addon_loader.unimplemented_field",
            addon=manifest.name,
            field="templates",
            count=len(manifest.templates),
            hint=f"Addon '{manifest.name}' declares templates but "
                 "templates registration is not yet implemented.",
        )

    return result


def _validate_tool_params(params: dict[str, Any], addon_name: str, tool_name: str) -> bool:
    """Check that tool parameters look like a valid JSON Schema object."""
    if not params:
        return True  # Empty is fine — tool takes no parameters
    if params.get("type") != "object":
        log.warning(
            "addon_loader.invalid_tool_params",
            addon=addon_name,
            tool=tool_name,
            hint="Tool parameters must have type 'object'.",
        )
        return False
    if "properties" not in params:
        log.warning(
            "addon_loader.invalid_tool_params",
            addon=addon_name,
            tool=tool_name,
            hint="Tool parameters must include 'properties'.",
        )
        return False
    return True


def validate_new_addon(
    manifest: AddonManifest,
    existing_registrations: list[AddonRegistration],
) -> list[str]:
    """Validate a new addon before loading. Returns a list of errors (empty = ok).

    Checks:
    - addon name uniqueness
    - handler module imports
    - handler reference resolution
    - panel/route path collisions
    """
    errors: list[str] = []

    # Name uniqueness
    existing_names = {r.manifest.name for r in existing_registrations}
    if manifest.name in existing_names:
        errors.append(f"Addon name '{manifest.name}' already exists")

    # Handler import validation
    for tool in manifest.tools:
        try:
            _resolve_handler(tool.handler, manifest.name)
        except Exception as exc:
            errors.append(f"Tool '{tool.name}' handler error: {exc}")

    for route in manifest.routes:
        handler_ref = route.get("handler", "")
        if handler_ref:
            try:
                _resolve_handler(handler_ref, manifest.name)
            except Exception as exc:
                errors.append(f"Route '{route.get('path', '')}' handler error: {exc}")

    for panel in manifest.panels:
        handler_ref = panel.get("handler", "")
        if handler_ref:
            try:
                _resolve_handler(handler_ref, manifest.name)
            except Exception as exc:
                errors.append(f"Panel handler error: {exc}")

    # Panel/route path collisions
    existing_paths: set[tuple[str, str]] = set()
    for reg in existing_registrations:
        for aroute in reg.registered_routes:
            existing_paths.add((aroute["addon_name"], aroute["path"]))

    for route in manifest.routes:
        path = route.get("path", "")
        for existing_addon, existing_path in existing_paths:
            if existing_addon != manifest.name and existing_path == path:
                errors.append(
                    f"Route '{path}' conflicts with addon '{existing_addon}'",
                )

    return errors


async def load_new_addon(
    manifest: AddonManifest,
    *,
    app_state: Any,
    runtime: Any,
    base_runtime_context: dict[str, Any],
    queen_dispatcher: Any | None = None,
    service_router: Any | None = None,
) -> tuple[AddonRegistration | None, list[str]]:
    """Load a brand-new addon into the running app with strict validation.

    Returns ``(registration, errors)``. On failure, ``registration`` is None
    and ``errors`` is non-empty. No partial registration on failure.

    Reuses the same wiring path as startup (governed gateway, register_addon,
    AddonLoaded event, app state update).
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    existing: list[AddonRegistration] = getattr(
        app_state, "addon_registrations", [],
    )

    # Strict validation
    errors = validate_new_addon(manifest, existing)
    if errors:
        return None, errors

    # Build per-addon context (same as startup)
    per_addon_ctx = dict(base_runtime_context)
    if getattr(manifest, "mcp_permissions", None):
        mcp_bridge = base_runtime_context.get("mcp_bridge")
        if mcp_bridge:
            try:
                from formicos.addons.mcp_bridge.gateway import (  # noqa: PLC0415
                    create_gateway_for_addon,
                )
                per_addon_ctx["mcp_gateway"] = create_gateway_for_addon(
                    mcp_bridge, manifest.name, manifest.mcp_permissions,
                )
            except Exception:  # noqa: BLE001
                pass

    # Register (same as startup)
    tool_registry = (
        queen_dispatcher._handlers  # pyright: ignore[reportAttributeAccessIssue]
        if queen_dispatcher is not None else None
    )
    reg = register_addon(
        manifest,
        tool_registry=tool_registry,
        service_router=service_router,
        runtime_context=per_addon_ctx,
    )

    # Update app state (same as startup)
    existing.append(reg)
    app_state.addon_registrations = existing  # type: ignore[attr-defined]

    # Update Queen tool specs
    if queen_dispatcher is not None:
        new_specs = build_addon_tool_specs([manifest])
        queen_dispatcher._addon_tool_specs.extend(new_specs)  # pyright: ignore[reportAttributeAccessIssue]

    # Emit AddonLoaded event
    try:
        from formicos.core.events import AddonLoaded  # noqa: PLC0415
        await runtime.emit_and_broadcast(AddonLoaded(
            seq=0,
            timestamp=datetime.now(UTC),
            address="system",
            addon_name=manifest.name,
            version=manifest.version,
            tools=reg.registered_tools,
            handlers=reg.registered_handlers,
            panels=[p.get("target", "") for p in manifest.panels],
        ))
    except Exception:  # noqa: BLE001
        log.warning("addon_loader.event_failed", addon=manifest.name)

    log.info(
        "addon_loader.new_addon_loaded",
        addon=manifest.name,
        tools=reg.registered_tools,
        panels=len(manifest.panels),
    )
    return reg, []


def build_addon_tool_specs(manifests: list[AddonManifest]) -> list[dict[str, Any]]:
    """Build Queen tool spec dicts from addon manifests.

    These specs are appended to the Queen's tool list so the LLM
    can discover and call addon-provided tools.
    """
    specs: list[dict[str, Any]] = []
    for m in manifests:
        for tool in m.tools:
            _validate_tool_params(tool.parameters, m.name, tool.name)
            spec: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or f"Tool from addon '{m.name}'",
                "parameters": tool.parameters or {
                    "type": "object",
                    "properties": {},
                },
            }
            specs.append(spec)
    return specs
