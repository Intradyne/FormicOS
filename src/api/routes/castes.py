"""
FormicOS v0.7.9 -- V1 Caste & Skill Routes

Routes:
  Castes: GET/POST/PUT/DELETE /castes
  Skills: GET/POST /skills, GET/PUT/DELETE /skills/{skill_id}
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request

from src.api.helpers import api_error_v1, safe_serialize
from src.auth import ClientAPIKey, get_current_client
from src.models import (
    CasteConfig,
    CasteCreateRequest,
    CasteUpdateRequest,
    FormicOSConfig,
    SkillCreateRequest,
    SkillUpdateRequest,
    SubcasteMapEntry,
)
from src.skill_bank import SkillBank

router = APIRouter()


# -- Castes --

@router.get("/castes")
async def v1_list_castes(request: Request):
    config_obj: FormicOSConfig = request.app.state.config
    result = {}
    for name, cc in config_obj.castes.items():
        prompt_content = ""
        prompt_path = Path("config/prompts") / cc.system_prompt_file
        if prompt_path.exists():
            prompt_content = prompt_path.read_text(encoding="utf-8")
        result[name] = {
            "name": name,
            "system_prompt": prompt_content,
            "tools": cc.tools,
            "mcp_tools": cc.mcp_tools,
            "model_override": cc.model_override,
            "subcaste_overrides": {
                k: v.model_dump() if hasattr(v, "model_dump") else v
                for k, v in cc.subcaste_overrides.items()
            },
            "description": cc.description,
        }
    return result


@router.post("/castes")
async def v1_create_caste(body: CasteCreateRequest, request: Request):
    config_obj: FormicOSConfig = request.app.state.config
    name = body.name.strip().lower()
    if not name:
        return api_error_v1(400, "INVALID_NAME", "Caste name cannot be empty")
    if name in config_obj.castes:
        return api_error_v1(409, "CASTE_EXISTS", f"Caste '{name}' already exists")

    prompt_file = f"{name}.md"
    prompt_path = Path("config/prompts") / prompt_file
    prompt_path.write_text(
        body.system_prompt or f"# {name.title()} Agent\n\nYou are a {name} agent.\n",
        encoding="utf-8",
    )

    sub_overrides = {}
    for tier_key, entry_data in body.subcaste_overrides.items():
        if isinstance(entry_data, dict):
            sub_overrides[tier_key] = SubcasteMapEntry(**entry_data)
        else:
            sub_overrides[tier_key] = SubcasteMapEntry(primary=str(entry_data))

    config_obj.castes[name] = CasteConfig(
        system_prompt_file=prompt_file,
        tools=body.tools,
        mcp_tools=body.mcp_tools,
        model_override=body.model_override,
        subcaste_overrides=sub_overrides,
        description=body.description,
    )
    return {"name": name, "status": "created"}


@router.put("/castes/{name}")
async def v1_update_caste(name: str, body: CasteUpdateRequest, request: Request):
    config_obj: FormicOSConfig = request.app.state.config
    name = name.strip().lower()
    if name not in config_obj.castes:
        return api_error_v1(404, "CASTE_NOT_FOUND", f"Caste '{name}' not found")

    cc = config_obj.castes[name]
    if body.system_prompt is not None:
        prompt_path = Path("config/prompts") / cc.system_prompt_file
        prompt_path.write_text(body.system_prompt, encoding="utf-8")
    if body.tools is not None:
        cc.tools = body.tools
    if body.mcp_tools is not None:
        cc.mcp_tools = body.mcp_tools
    if body.model_override is not None:
        cc.model_override = body.model_override if body.model_override else None
    if body.description is not None:
        cc.description = body.description
    if body.subcaste_overrides is not None:
        sub_overrides = {}
        for tier_key, entry_data in body.subcaste_overrides.items():
            if isinstance(entry_data, dict):
                sub_overrides[tier_key] = SubcasteMapEntry(**entry_data)
            else:
                sub_overrides[tier_key] = SubcasteMapEntry(primary=str(entry_data))
        cc.subcaste_overrides = sub_overrides

    return {"name": name, "status": "updated"}


@router.delete("/castes/{name}")
async def v1_delete_caste(name: str, request: Request):
    config_obj: FormicOSConfig = request.app.state.config
    name = name.strip().lower()
    if name == "manager":
        return api_error_v1(403, "PROTECTED_CASTE", "Cannot delete the manager caste")
    if name not in config_obj.castes:
        return api_error_v1(404, "CASTE_NOT_FOUND", f"Caste '{name}' not found")

    cc = config_obj.castes.pop(name)
    prompt_path = Path("config/prompts") / cc.system_prompt_file
    if prompt_path.exists():
        prompt_path.unlink()
    return {"name": name, "status": "deleted"}


# -- Skills --

@router.get("/skills")
async def v1_list_skills(request: Request):
    sb: SkillBank = request.app.state.skill_bank
    grouped = sb.get_all()
    result = []
    for tier, skills in grouped.items():
        for s in skills:
            sd = safe_serialize(s)
            sd["tier"] = tier
            result.append(sd)
    return result


@router.post("/skills")
async def v1_create_skill(
    body: SkillCreateRequest,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    sb: SkillBank = request.app.state.skill_bank
    # Resolve author_client_id from API key if not explicitly set (v0.7.7)
    author = body.author_client_id
    if not author and client:
        author = client.client_id
    try:
        skill_id = sb.store_single(
            content=body.content, tier=body.tier, category=body.category,
        )
        # Set author_client_id on the stored skill (v0.7.7)
        if author or body.colony_id:
            try:
                skill = sb._find_skill(skill_id)
                if author:
                    skill.author_client_id = author
                if body.colony_id:
                    skill.source_colony = body.colony_id
                sb.save()
            except (KeyError, AttributeError):
                pass
        return {
            "skill_id": skill_id,
            "status": "created",
            "author_client_id": author,
        }
    except ValueError as exc:
        return api_error_v1(409, "SKILL_DUPLICATE", str(exc))
    except Exception as exc:
        return api_error_v1(500, "SKILL_CREATE_FAILED", str(exc))


@router.get("/skills/{skill_id}")
async def v1_get_skill(skill_id: str, request: Request):
    sb: SkillBank = request.app.state.skill_bank
    try:
        skill = sb._find_skill(skill_id)
        return safe_serialize(skill)
    except KeyError:
        return api_error_v1(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")


@router.put("/skills/{skill_id}")
async def v1_update_skill(skill_id: str, body: SkillUpdateRequest, request: Request):
    sb: SkillBank = request.app.state.skill_bank
    try:
        sb.update(skill_id, body.content)
        return {"skill_id": skill_id, "status": "updated"}
    except KeyError:
        return api_error_v1(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")
    except Exception as exc:
        return api_error_v1(500, "SKILL_UPDATE_FAILED", str(exc))


@router.delete("/skills/{skill_id}")
async def v1_delete_skill(skill_id: str, request: Request):
    sb: SkillBank = request.app.state.skill_bank
    try:
        sb.delete(skill_id)
        return {"skill_id": skill_id, "status": "deleted"}
    except KeyError:
        return api_error_v1(404, "SKILL_NOT_FOUND", f"Skill '{skill_id}' not found")
    except Exception as exc:
        return api_error_v1(500, "SKILL_DELETE_FAILED", str(exc))
