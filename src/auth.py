"""
FormicOS v0.7.4 -- API Key Authentication

In-memory API key store with SHA-256 hashing, optional Bearer token
validation via FastAPI dependency, and CRUD operations.

Integration:
  - APIKeyStore created in server.py lifespan, stored on app.state.api_key_store
  - get_current_client() used as Depends() on V1 endpoints (OPTIONAL auth)
  - CRUD endpoints at /api/v1/auth/keys
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


class APIKeyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ClientAPIKey(BaseModel):
    """A registered API client key."""

    key_id: str
    client_id: str
    hashed_token: str
    prefix: str
    status: APIKeyStatus = APIKeyStatus.ACTIVE
    scopes: list[str] = Field(default_factory=lambda: ["colonies:write"])
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_used_at: str | None = None


class APIKeyStore:
    """In-memory API key store.

    Thread-safe via GIL for single-key dict reads (same principle as
    AsyncContextTree's lockless dict operations).
    """

    def __init__(self) -> None:
        self._by_hash: dict[str, ClientAPIKey] = {}
        self._by_id: dict[str, ClientAPIKey] = {}

    def create(
        self,
        client_id: str,
        scopes: list[str] | None = None,
    ) -> tuple[ClientAPIKey, str]:
        """Create a new API key.

        Returns (model, raw_token). The raw_token is returned ONCE
        and never stored.
        """
        raw_token = f"fos_{secrets.token_urlsafe(32)}"
        hashed = hashlib.sha256(raw_token.encode()).hexdigest()
        key = ClientAPIKey(
            key_id=str(uuid.uuid4()),
            client_id=client_id,
            hashed_token=hashed,
            prefix=raw_token[:8],
            scopes=scopes or ["colonies:write"],
        )
        self._by_hash[hashed] = key
        self._by_id[key.key_id] = key
        return key, raw_token

    def lookup(self, raw_token: str) -> ClientAPIKey | None:
        """Look up by raw token.  Returns None if not found or revoked."""
        hashed = hashlib.sha256(raw_token.encode()).hexdigest()
        key = self._by_hash.get(hashed)
        if key is None or key.status == APIKeyStatus.REVOKED:
            return None
        key.last_used_at = datetime.now(timezone.utc).isoformat()
        return key

    def list_keys(self) -> list[ClientAPIKey]:
        """Return all keys (active and revoked).  Never exposes raw tokens."""
        return list(self._by_id.values())

    def revoke(self, key_id: str) -> bool:
        """Revoke a key by key_id.  Returns True if found and revoked."""
        key = self._by_id.get(key_id)
        if key is None:
            return False
        key.status = APIKeyStatus.REVOKED
        return True


# ── FastAPI dependency ────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_client(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> ClientAPIKey | None:
    """Extract and validate Bearer token.

    Returns None if no token provided (OPTIONAL auth for v0.7.4).
    Raises 401 if token is provided but invalid/revoked.
    """
    if credentials is None:
        return None

    store: APIKeyStore = request.app.state.api_key_store
    key = store.lookup(credentials.credentials)
    if key is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return key
