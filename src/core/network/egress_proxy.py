"""
FormicOS v0.8.0 -- Cryptographic Egress Proxy

Ed25519-signed expense request forwarding for air-gapped agent containers.
Only the CFO caste holds the private signing key.  The proxy holds the
public verification key and rejects any request with an invalid or
missing signature.

Key invariant:
  An agent without the CFO's Ed25519 private key CANNOT forge a valid
  ExpenseRequest.  Tampering with ANY field (amount, target_api,
  justification, nonce, timestamp) invalidates the signature.

Dependencies:
  - PyNaCl  (Ed25519 signing/verification via libsodium)
  - httpx   (async HTTP forwarding)
  - pydantic (request/response models)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx
import nacl.encoding
import nacl.exceptions
import nacl.signing
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("formicos.egress_proxy")

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# ── Exceptions ─────────────────────────────────────────────────────────


class EgressProxyError(Exception):
    """Base exception for egress proxy operations."""


class SignatureVerificationError(EgressProxyError):
    """Raised when Ed25519 signature verification fails."""


class ProxyReplayError(EgressProxyError):
    """Raised when a nonce has already been consumed (replay attack)."""


# ── Nonce Ledger ──────────────────────────────────────────────────────

# Default: evict nonces older than 1 hour, cap at 100k entries.
_DEFAULT_NONCE_TTL = 3600.0
_DEFAULT_NONCE_MAX = 100_000


class NonceLedger:
    """Thread-safe in-memory ledger of consumed nonces.

    Prevents replay attacks by rejecting any nonce that has already been
    used to forward a request.  Old entries are evicted by timestamp to
    bound memory usage.

    Concurrency: An ``asyncio.Lock`` serialises all mutations so that
    concurrent ``forward()`` calls on the same event loop cannot race
    past the nonce check.
    """

    def __init__(
        self,
        ttl: float = _DEFAULT_NONCE_TTL,
        max_entries: int = _DEFAULT_NONCE_MAX,
    ) -> None:
        self._used: dict[str, float] = {}  # nonce → timestamp consumed
        self._ttl = ttl
        self._max_entries = max_entries
        self._lock = asyncio.Lock()

    async def check_and_consume(self, nonce: str) -> None:
        """Atomically check uniqueness and mark nonce as consumed.

        Raises :class:`ProxyReplayError` if the nonce is already in the
        ledger (replay detected).
        """
        async with self._lock:
            self._evict_expired()
            if nonce in self._used:
                raise ProxyReplayError(
                    f"Nonce already consumed: {nonce}"
                )
            self._used[nonce] = time.time()

    def _evict_expired(self) -> None:
        """Remove entries older than TTL or exceeding max size."""
        now = time.time()
        cutoff = now - self._ttl
        # Time-based eviction
        self._used = {
            n: ts for n, ts in self._used.items() if ts > cutoff
        }
        # Size-based eviction (keep newest)
        if len(self._used) > self._max_entries:
            sorted_entries = sorted(
                self._used.items(), key=lambda x: x[1], reverse=True,
            )
            self._used = dict(sorted_entries[: self._max_entries])

    def __len__(self) -> int:
        return len(self._used)

    def __contains__(self, nonce: str) -> bool:
        return nonce in self._used


# ── Pydantic Models ────────────────────────────────────────────────────


class ExpenseRequest(BaseModel):
    """A signed financial request from the CFO caste.

    The ``signature`` field is hex-encoded Ed25519 signature over the
    canonical JSON of all other fields (sorted keys, compact separators).
    """

    amount: float = Field(..., gt=0, description="Expense amount in USD")
    target_api: str = Field(
        ..., min_length=1, description="Target API URL",
    )
    justification: str = Field(
        ..., min_length=1, description="Why this expense is needed",
    )
    nonce: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique request identifier to prevent replay",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of request creation",
    )
    signature: str = Field(
        default="", description="Hex-encoded Ed25519 signature",
    )

    @field_validator("target_api")
    @classmethod
    def target_api_is_url(cls, v: str) -> str:
        if not v.startswith(("https://", "http://")):
            raise ValueError(
                "target_api must be a valid URL starting with http(s)://"
            )
        return v

    def canonical_bytes(self) -> bytes:
        """Serialize the signable fields to deterministic JSON bytes.

        Excludes ``signature`` to produce the canonical message that
        was (or should have been) signed by the CFO's private key.
        """
        payload = self.model_dump(exclude={"signature"})
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")

    def sign(self, signing_key: nacl.signing.SigningKey) -> None:
        """Sign this request in-place using the CFO's private key."""
        signed = signing_key.sign(self.canonical_bytes())
        self.signature = signed.signature.hex()

    def verify(self, verify_key: nacl.signing.VerifyKey) -> bool:
        """Verify the signature against the proxy's public key.

        Returns True if valid, raises SignatureVerificationError if not.
        """
        if not self.signature:
            raise SignatureVerificationError("Missing signature")
        try:
            sig_bytes = bytes.fromhex(self.signature)
        except ValueError as exc:
            raise SignatureVerificationError(
                f"Invalid signature encoding: {exc}"
            ) from exc
        try:
            verify_key.verify(self.canonical_bytes(), sig_bytes)
            return True
        except nacl.exceptions.BadSignatureError:
            raise SignatureVerificationError(
                "Ed25519 signature verification failed"
            )


class ProxyResponse(BaseModel):
    """Response from the egress proxy after forwarding (or rejecting)."""

    status_code: int
    body: Any = None
    error: str | None = None
    forwarded: bool = False
    request_nonce: str = ""


# ── Key Vault ──────────────────────────────────────────────────────────


def generate_keypair() -> tuple[nacl.signing.SigningKey, nacl.signing.VerifyKey]:
    """Generate a new Ed25519 keypair for CFO signing.

    Returns (signing_key, verify_key).
    The signing_key goes to the CFO agent.
    The verify_key goes to the EgressProxy.
    """
    signing_key = nacl.signing.SigningKey.generate()
    return signing_key, signing_key.verify_key


class KeyVault:
    """Holds the proxy-side Ed25519 public key for signature verification.

    Supports loading from:
      - A VerifyKey object directly
      - Raw 32-byte public key bytes
      - Hex-encoded string
      - File path containing raw or hex bytes
    """

    def __init__(self, verify_key: nacl.signing.VerifyKey) -> None:
        self._verify_key = verify_key

    @property
    def verify_key(self) -> nacl.signing.VerifyKey:
        return self._verify_key

    @classmethod
    def from_hex(cls, hex_str: str) -> KeyVault:
        """Construct from a hex-encoded 32-byte public key."""
        key_bytes = bytes.fromhex(hex_str)
        return cls(nacl.signing.VerifyKey(key_bytes))

    @classmethod
    def from_bytes(cls, raw: bytes) -> KeyVault:
        """Construct from raw 32-byte public key bytes."""
        return cls(nacl.signing.VerifyKey(raw))

    @classmethod
    def from_file(cls, path: str) -> KeyVault:
        """Load from a file containing hex or raw key bytes."""
        with open(path, "rb") as f:
            data = f.read().strip()
        try:
            return cls.from_hex(data.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return cls.from_bytes(data)


# ── Proxy Router ───────────────────────────────────────────────────────


class ProxyRouter:
    """Air-gapped egress proxy with Ed25519 signature verification.

    Lifecycle follows the WebhookDispatcher pattern::

        proxy = ProxyRouter(vault)
        await proxy.start()
        response = await proxy.forward(request)
        await proxy.stop()
    """

    def __init__(
        self,
        vault: KeyVault,
        timeout: httpx.Timeout | None = None,
        allowed_targets: list[str] | None = None,
        nonce_ttl: float = _DEFAULT_NONCE_TTL,
        nonce_max: int = _DEFAULT_NONCE_MAX,
    ) -> None:
        self._vault = vault
        self._timeout = timeout or _DEFAULT_TIMEOUT
        self._client: httpx.AsyncClient | None = None
        self._allowed_targets: list[str] | None = allowed_targets
        self._nonce_ledger = NonceLedger(ttl=nonce_ttl, max_entries=nonce_max)
        self._audit_log: list[dict[str, Any]] = []
        self._max_log_entries = 500

    async def start(self) -> None:
        """Create the shared httpx client.  Call in lifespan startup."""
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def stop(self) -> None:
        """Close the shared httpx client.  Call in lifespan shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def forward(self, request: ExpenseRequest) -> ProxyResponse:
        """Verify signature, check nonce uniqueness, and forward if valid.

        Returns ProxyResponse with:
          - 403 + error if signature invalid, nonce replayed, or target
            not in allowlist
          - 502 + error if upstream unreachable
          - 503 + error if proxy not started
          - upstream status_code + body if forwarded successfully
        """
        # Step 1: Verify Ed25519 signature
        try:
            request.verify(self._vault.verify_key)
        except SignatureVerificationError as exc:
            logger.warning(
                "Signature verification failed for nonce=%s: %s",
                request.nonce, exc,
            )
            self._append_audit(request, 403, str(exc), forwarded=False)
            return ProxyResponse(
                status_code=403,
                error=str(exc),
                forwarded=False,
                request_nonce=request.nonce,
            )

        # Step 2: Nonce replay check (atomic check-and-consume)
        try:
            await self._nonce_ledger.check_and_consume(request.nonce)
        except ProxyReplayError as exc:
            logger.warning(
                "Replay attack blocked for nonce=%s", request.nonce,
            )
            self._append_audit(request, 403, str(exc), forwarded=False)
            return ProxyResponse(
                status_code=403,
                error=str(exc),
                forwarded=False,
                request_nonce=request.nonce,
            )

        # Step 3: Optional target allowlist check
        if self._allowed_targets is not None:
            if not any(
                request.target_api.startswith(t)
                for t in self._allowed_targets
            ):
                msg = f"Target API not in allowlist: {request.target_api}"
                logger.warning(msg)
                self._append_audit(request, 403, msg, forwarded=False)
                return ProxyResponse(
                    status_code=403,
                    error=msg,
                    forwarded=False,
                    request_nonce=request.nonce,
                )

        # Step 4: Forward to target API
        if self._client is None:
            logger.error("ProxyRouter not started -- call start() first")
            return ProxyResponse(
                status_code=503,
                error="Proxy not initialized",
                forwarded=False,
                request_nonce=request.nonce,
            )

        try:
            resp = await self._client.post(
                request.target_api,
                json={
                    "amount": request.amount,
                    "justification": request.justification,
                    "nonce": request.nonce,
                },
                headers={"Content-Type": "application/json"},
            )
            body: Any = resp.text
            try:
                body = resp.json()
            except Exception:
                pass

            self._append_audit(
                request, resp.status_code, None, forwarded=True,
            )
            return ProxyResponse(
                status_code=resp.status_code,
                body=body,
                forwarded=True,
                request_nonce=request.nonce,
            )
        except Exception as exc:
            logger.error("Upstream request failed: %s", exc)
            self._append_audit(request, 502, str(exc), forwarded=False)
            return ProxyResponse(
                status_code=502,
                error=f"Upstream error: {exc}",
                forwarded=False,
                request_nonce=request.nonce,
            )

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return a copy of the egress audit log."""
        return list(self._audit_log)

    def _append_audit(
        self,
        request: ExpenseRequest,
        status_code: int,
        error: str | None,
        forwarded: bool,
    ) -> None:
        record = {
            "nonce": request.nonce,
            "amount": request.amount,
            "target_api": request.target_api,
            "status_code": status_code,
            "error": error,
            "forwarded": forwarded,
            "timestamp": time.time(),
        }
        self._audit_log.append(record)
        if len(self._audit_log) > self._max_log_entries:
            self._audit_log = self._audit_log[-self._max_log_entries :]
