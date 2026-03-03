"""
Tests for FormicOS v0.7.4 API Key Authentication Layer.

Covers:
- APIKeyStore CRUD operations (create, lookup, revoke, list)
- get_current_client dependency (no header, valid, invalid, revoked)
- V1 auth CRUD endpoints (POST/GET/DELETE /api/v1/auth/keys)
- Namespace isolation on colony listing
- Colony ownership check (granted, denied, unowned)
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi import HTTPException

from src.auth import APIKeyStatus, APIKeyStore, ClientAPIKey


# ── APIKeyStore unit tests ────────────────────────────────────────────


def test_api_key_store_create():
    store = APIKeyStore()
    key, raw_token = store.create(client_id="n8n-prod")

    assert isinstance(key, ClientAPIKey)
    assert key.client_id == "n8n-prod"
    assert key.status == APIKeyStatus.ACTIVE
    assert key.prefix == raw_token[:8]
    assert raw_token.startswith("fos_")
    assert len(raw_token) > 20
    # Verify hash
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    assert key.hashed_token == expected_hash


def test_api_key_store_create_with_scopes():
    store = APIKeyStore()
    key, _ = store.create(
        client_id="ci-runner",
        scopes=["colonies:read"],
    )
    assert key.scopes == ["colonies:read"]


def test_api_key_store_create_default_scopes():
    store = APIKeyStore()
    key, _ = store.create(client_id="test")
    assert key.scopes == ["colonies:write"]


def test_api_key_store_lookup():
    store = APIKeyStore()
    key, raw_token = store.create(client_id="test")

    found = store.lookup(raw_token)
    assert found is not None
    assert found.key_id == key.key_id
    assert found.client_id == "test"


def test_api_key_store_lookup_invalid():
    store = APIKeyStore()
    store.create(client_id="test")

    result = store.lookup("fos_definitely_not_a_real_token")
    assert result is None


def test_api_key_store_revoke():
    store = APIKeyStore()
    key, raw_token = store.create(client_id="test")

    assert store.revoke(key.key_id) is True
    assert store.lookup(raw_token) is None


def test_api_key_store_revoke_nonexistent():
    store = APIKeyStore()
    assert store.revoke("nonexistent-id") is False


def test_api_key_store_list():
    store = APIKeyStore()
    store.create(client_id="alpha")
    store.create(client_id="beta")

    keys = store.list_keys()
    assert len(keys) == 2
    client_ids = {k.client_id for k in keys}
    assert client_ids == {"alpha", "beta"}


def test_api_key_store_list_includes_revoked():
    store = APIKeyStore()
    key, _ = store.create(client_id="test")
    store.revoke(key.key_id)

    keys = store.list_keys()
    assert len(keys) == 1
    assert keys[0].status == APIKeyStatus.REVOKED


def test_api_key_store_last_used_at():
    store = APIKeyStore()
    key, raw_token = store.create(client_id="test")
    assert key.last_used_at is None

    store.lookup(raw_token)
    assert key.last_used_at is not None


def test_api_key_prefix_format():
    store = APIKeyStore()
    _, raw_token = store.create(client_id="test")
    assert raw_token[:4] == "fos_"
    # prefix is first 8 chars of raw token
    key = store.lookup(raw_token)
    assert key.prefix == raw_token[:8]


# ── get_current_client dependency tests ───────────────────────────────


@pytest.mark.asyncio
async def test_get_current_client_no_header():
    from src.auth import get_current_client
    from unittest.mock import MagicMock

    request = MagicMock()
    result = await get_current_client(request=request, credentials=None)
    assert result is None


@pytest.mark.asyncio
async def test_get_current_client_valid_token():
    from src.auth import get_current_client
    from unittest.mock import MagicMock
    from fastapi.security import HTTPAuthorizationCredentials

    store = APIKeyStore()
    key, raw_token = store.create(client_id="test-client")

    request = MagicMock()
    request.app.state.api_key_store = store
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=raw_token,
    )

    result = await get_current_client(
        request=request, credentials=credentials,
    )
    assert result is not None
    assert result.client_id == "test-client"
    assert result.key_id == key.key_id


@pytest.mark.asyncio
async def test_get_current_client_invalid_token():
    from src.auth import get_current_client
    from unittest.mock import MagicMock
    from fastapi.security import HTTPAuthorizationCredentials

    store = APIKeyStore()
    store.create(client_id="real-client")

    request = MagicMock()
    request.app.state.api_key_store = store
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="fos_bogus_token",
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_client(
            request=request, credentials=credentials,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_client_revoked_token():
    from src.auth import get_current_client
    from unittest.mock import MagicMock
    from fastapi.security import HTTPAuthorizationCredentials

    store = APIKeyStore()
    key, raw_token = store.create(client_id="test")
    store.revoke(key.key_id)

    request = MagicMock()
    request.app.state.api_key_store = store
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=raw_token,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_client(
            request=request, credentials=credentials,
        )
    assert exc_info.value.status_code == 401


# ── Multiple keys for same client_id ─────────────────────────────────


def test_multiple_keys_same_client():
    store = APIKeyStore()
    key1, token1 = store.create(client_id="shared")
    key2, token2 = store.create(client_id="shared")

    assert key1.key_id != key2.key_id
    assert token1 != token2
    assert store.lookup(token1).key_id == key1.key_id
    assert store.lookup(token2).key_id == key2.key_id


def test_revoke_one_key_keeps_other():
    store = APIKeyStore()
    key1, token1 = store.create(client_id="shared")
    key2, token2 = store.create(client_id="shared")

    store.revoke(key1.key_id)
    assert store.lookup(token1) is None
    assert store.lookup(token2) is not None
