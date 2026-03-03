"""
FormicOS v0.7.9 -- V1 Auth Routes

Routes: POST /auth/keys, GET /auth/keys, DELETE /auth/keys/{key_id}
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.helpers import api_error_v1
from src.auth import APIKeyStore
from src.models import APIKeyCreateRequest, APIKeyListItem, APIKeyResponse

router = APIRouter()


@router.post("/auth/keys")
async def v1_create_api_key(body: APIKeyCreateRequest, request: Request):
    store: APIKeyStore = request.app.state.api_key_store
    if not body.client_id.strip():
        return api_error_v1(
            400, "INVALID_CLIENT_ID", "client_id must not be empty",
        )
    key, raw_token = store.create(
        client_id=body.client_id.strip(),
        scopes=body.scopes,
    )
    return APIKeyResponse(
        key_id=key.key_id,
        client_id=key.client_id,
        prefix=key.prefix,
        raw_token=raw_token,
        scopes=key.scopes,
        created_at=key.created_at,
    ).model_dump()


@router.get("/auth/keys")
async def v1_list_api_keys(request: Request):
    store: APIKeyStore = request.app.state.api_key_store
    keys = store.list_keys()
    return {
        "items": [
            APIKeyListItem(
                key_id=k.key_id,
                client_id=k.client_id,
                prefix=k.prefix,
                status=k.status.value,
                scopes=k.scopes,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
            ).model_dump()
            for k in keys
        ],
        "total": len(keys),
    }


@router.delete("/auth/keys/{key_id}")
async def v1_revoke_api_key(key_id: str, request: Request):
    store: APIKeyStore = request.app.state.api_key_store
    revoked = store.revoke(key_id)
    if not revoked:
        return api_error_v1(
            404, "KEY_NOT_FOUND",
            f"API key '{key_id}' not found",
        )
    return {"status": "revoked", "key_id": key_id}
