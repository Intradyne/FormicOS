"""Colony template management (ADR-016).

Loads, saves, and lists colony templates from YAML files in ``config/templates/``.
Templates are immutable: edits create new versions with the same ``template_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
import yaml
from pydantic import BaseModel, ConfigDict

from formicos.core.events import ColonyTemplateCreated
from formicos.core.types import CasteSlot

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger(__name__)

TEMPLATE_DIR = Path("config/templates")


class ColonyTemplate(BaseModel):
    """Immutable colony configuration template (ADR-016)."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    name: str
    description: str
    version: int = 1
    castes: list[CasteSlot]
    strategy: str = "stigmergic"
    budget_limit: float = 1.0
    max_rounds: int = 25
    tags: list[str] = []
    source_colony_id: str | None = None
    created_at: str = ""
    use_count: int = 0
    # Task contract fields (Wave 25)
    input_description: str = ""
    output_description: str = ""
    expected_output_types: list[str] = []
    completion_hint: str = ""
    # Wave 50: learned template fields
    learned: bool = False
    task_category: str = ""
    fast_path: bool = False
    target_files_pattern: str = ""
    success_count: int = 0
    failure_count: int = 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def load_templates(
    template_dir: Path | None = None,
) -> list[ColonyTemplate]:
    """Read all YAML files from the templates directory.

    Returns the latest version per ``template_id``.
    """
    d = template_dir or TEMPLATE_DIR
    if not d.exists():
        return []

    templates: dict[str, ColonyTemplate] = {}
    for path in sorted(d.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data: dict[str, Any] = yaml.safe_load(fh) or {}
            tmpl = ColonyTemplate(**data)
            existing = templates.get(tmpl.template_id)
            if existing is None or tmpl.version > existing.version:
                templates[tmpl.template_id] = tmpl
        except Exception as exc:  # noqa: BLE001
            log.warning("template.load_failed", path=str(path), error=str(exc))
    return list(templates.values())


async def get_template(
    template_id: str,
    template_dir: Path | None = None,
) -> ColonyTemplate | None:
    """Load a single template by ID (latest version)."""
    templates = await load_templates(template_dir)
    for tmpl in templates:
        if tmpl.template_id == template_id:
            return tmpl
    return None


async def save_template(
    tmpl: ColonyTemplate,
    runtime: Runtime,
    template_dir: Path | None = None,
) -> ColonyTemplate:
    """Write template YAML and emit ``ColonyTemplateCreated``."""
    d = template_dir or TEMPLATE_DIR
    d.mkdir(parents=True, exist_ok=True)

    # Fill in created_at if empty
    if not tmpl.created_at:
        tmpl = tmpl.model_copy(update={"created_at": _now_iso()})

    filename = f"{tmpl.template_id}-v{tmpl.version}.yaml"
    path = d / filename
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(
            tmpl.model_dump(mode="json"),
            fh,
            default_flow_style=False,
            sort_keys=False,
        )

    await runtime.emit_and_broadcast(ColonyTemplateCreated(
        seq=0,
        timestamp=datetime.now(UTC),
        address="system",
        template_id=tmpl.template_id,
        name=tmpl.name,
        description=tmpl.description,
        castes=list(tmpl.castes),
        strategy=tmpl.strategy,  # type: ignore[arg-type]
        source_colony_id=tmpl.source_colony_id,
    ))

    log.info(
        "template.saved",
        template_id=tmpl.template_id,
        version=tmpl.version,
        path=str(path),
    )
    return tmpl


async def list_templates(
    template_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Return template summaries suitable for JSON serialization."""
    templates = await load_templates(template_dir)
    return [tmpl.model_dump() for tmpl in templates]


def new_template_id() -> str:
    """Generate a new template ID."""
    return f"tmpl-{uuid4().hex[:8]}"


def learned_templates_from_projection(
    templates: dict[str, Any],
) -> list[ColonyTemplate]:
    """Convert TemplateProjection dicts to ColonyTemplate instances (Wave 50).

    Only includes learned templates (learned=True). Disk-backed operator
    templates are loaded separately via load_templates().
    """
    result: list[ColonyTemplate] = []
    for tmpl in templates.values():
        if not getattr(tmpl, "learned", False):
            continue
        try:
            result.append(ColonyTemplate(
                template_id=tmpl.id,
                name=tmpl.name,
                description=tmpl.description,
                castes=list(tmpl.castes),
                strategy=tmpl.strategy,
                budget_limit=tmpl.budget_limit,
                max_rounds=tmpl.max_rounds,
                source_colony_id=tmpl.source_colony_id,
                use_count=tmpl.use_count,
                learned=True,
                task_category=tmpl.task_category,
                fast_path=tmpl.fast_path,
                target_files_pattern=tmpl.target_files_pattern,
                success_count=tmpl.success_count,
                failure_count=tmpl.failure_count,
            ))
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "template.projection_convert_failed",
                template_id=getattr(tmpl, "id", "?"),
                error=str(exc),
            )
    return result


async def load_all_templates(
    template_dir: Path | None = None,
    projection_templates: dict[str, Any] | None = None,
) -> list[ColonyTemplate]:
    """Load disk templates and merge with projection-derived learned templates.

    Disk templates take precedence if IDs collide (operator > learned).
    """
    disk = await load_templates(template_dir)
    if not projection_templates:
        return disk
    learned = learned_templates_from_projection(projection_templates)
    # Merge: disk templates win on ID collision
    disk_ids = {t.template_id for t in disk}
    merged = list(disk)
    for lt in learned:
        if lt.template_id not in disk_ids:
            merged.append(lt)
    return merged


__all__ = [
    "ColonyTemplate",
    "get_template",
    "learned_templates_from_projection",
    "list_templates",
    "load_all_templates",
    "load_templates",
    "new_template_id",
    "save_template",
]
