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


class AddonManifest(BaseModel):
    """Parsed addon.yaml manifest."""

    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    tools: list[AddonToolSpec] = Field(default_factory=list)
    handlers: list[AddonHandlerSpec] = Field(default_factory=list)
    panels: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list)
    triggers: list[AddonTriggerSpec] = Field(default_factory=list)


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
        self.runtime_context: dict[str, Any] = {}


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
                ) -> Any:
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
                        **kwargs: Any,
                    ) -> Any:
                        return await _bound_efn(event, runtime_context=_bound_ctx, **kwargs)

                    svc_name = f"addon:{manifest.name}:{handler_spec.event}"
                    service_router.register_handler(svc_name, _event_wrapper)
                else:
                    svc_name = f"addon:{manifest.name}:{handler_spec.event}"
                    service_router.register_handler(svc_name, handler_fn)

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

    # Warn about declared-but-unimplemented manifest fields
    for field_name in ("panels", "templates", "routes"):
        field_val = getattr(manifest, field_name, [])
        if field_val:
            log.warning(
                "addon_loader.unimplemented_field",
                addon=manifest.name,
                field=field_name,
                count=len(field_val),
                hint=f"Addon '{manifest.name}' declares {field_name} but "
                     f"{field_name} registration is not yet implemented.",
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
