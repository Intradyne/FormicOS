"""
Tests for FormicOS CFO Caste — Ed25519 Signing + Expense Audit.

Covers:
1. CFOToolkit creation and properties
2. Expense review (within budget, over budget)
3. Approve and sign (signature, ledger, spend tracking)
4. Reject (reason recording)
5. End-to-end: Coder $5 expense → CFO signs → EgressProxy accepts
6. Tamper detection post-signing
7. Budget exhaustion across multiple approvals
8. Stripe dry-run mode
9. Tool schema registration
10. Tool implementations (expense_request, approve, reject file I/O)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.core.cfo import CFOToolkit
from src.core.network.egress_proxy import (
    ExpenseRequest,
    KeyVault,
    ProxyRouter,
    generate_keypair,
)


# ── Helpers ─────────────────────────────────────────────────────────────


class FakeResponse:
    """Mock httpx.Response for ProxyRouter tests."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data
        self.text = json.dumps(json_data) if json_data else "ok"

    def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("No JSON")


class FakeClient:
    """Mock httpx.AsyncClient."""

    def __init__(self):
        self.last_url: str | None = None
        self.last_json: dict | None = None

    async def post(self, url: str, **kwargs):
        self.last_url = url
        self.last_json = kwargs.get("json")
        return FakeResponse(200, {"id": "ch_test_123", "status": "succeeded"})

    async def aclose(self):
        pass


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for each test."""
    return generate_keypair()


@pytest.fixture
def toolkit(keypair):
    """CFOToolkit with $50 budget."""
    signing_key, _ = keypair
    return CFOToolkit(
        signing_key=signing_key,
        colony_id="test-colony",
        budget_limit_usd=50.0,
    )


@pytest.fixture
def sample_request():
    """A $5 expense request dict."""
    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="API access for code generation subtask",
    )
    return req.model_dump()


# ── 1. Toolkit Creation ─────────────────────────────────────────────────


def test_cfo_toolkit_creation(keypair):
    """CFOToolkit initializes with correct defaults."""
    signing_key, verify_key = keypair
    tk = CFOToolkit(
        signing_key=signing_key,
        colony_id="colony-42",
        budget_limit_usd=200.0,
    )
    assert tk.total_approved == 0.0
    assert tk.remaining_budget == 200.0
    assert tk.ledger == []
    assert tk.verify_key.encode() == verify_key.encode()


# ── 2. Review ────────────────────────────────────────────────────────────


def test_review_within_budget(toolkit, sample_request):
    """Review returns approved=True for request within budget."""
    result = toolkit.review_expense(sample_request, "Build a web scraper")
    assert result["approved"] is True
    assert result["amount"] == 5.00
    assert result["remaining_budget"] == 45.0
    assert result["request_nonce"] == sample_request["nonce"]


def test_review_over_budget(keypair):
    """Review returns approved=False when amount exceeds budget."""
    signing_key, _ = keypair
    tk = CFOToolkit(signing_key=signing_key, budget_limit_usd=3.0)
    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/embeddings",
        justification="Embedding generation",
    )
    result = tk.review_expense(req.model_dump(), "")
    assert result["approved"] is False
    assert "Over budget" in result["reason"]
    assert result["remaining_budget"] == 3.0


def test_review_invalid_request(toolkit):
    """Review handles malformed request gracefully."""
    result = toolkit.review_expense({"amount": -1}, "")
    assert result["approved"] is False
    assert "Invalid expense request" in result["reason"]


# ── 3. Approve & Sign ────────────────────────────────────────────────────


def test_approve_and_sign(toolkit, sample_request):
    """approve_and_sign produces a valid 128-char hex signature."""
    result = toolkit.approve_and_sign(sample_request)
    assert result["signed"] is True
    assert len(result["signature"]) == 128  # 64 bytes as hex
    assert result["amount"] == 5.00
    assert result["nonce"] == sample_request["nonce"]


def test_approve_updates_ledger(toolkit, sample_request):
    """Ledger contains approval entry after signing."""
    toolkit.approve_and_sign(sample_request)
    assert len(toolkit.ledger) == 1
    entry = toolkit.ledger[0]
    assert entry["action"] == "approved"
    assert entry["amount"] == 5.00
    assert entry["colony_id"] == "test-colony"
    assert len(entry["signature"]) == 128


def test_approve_increments_spent(toolkit, sample_request):
    """total_approved increases by the request amount."""
    assert toolkit.total_approved == 0.0
    toolkit.approve_and_sign(sample_request)
    assert toolkit.total_approved == 5.0
    assert toolkit.remaining_budget == 45.0


# ── 4. Reject ────────────────────────────────────────────────────────────


def test_reject_records_reason(toolkit, sample_request):
    """Rejection recorded in ledger with reason."""
    result = toolkit.reject_expense(sample_request, "Speculative spending")
    assert result["rejected"] is True
    assert result["reason"] == "Speculative spending"
    assert len(toolkit.ledger) == 1
    assert toolkit.ledger[0]["action"] == "rejected"
    assert toolkit.ledger[0]["reason"] == "Speculative spending"
    # Rejection does NOT increment spend
    assert toolkit.total_approved == 0.0


# ── 5. End-to-End: Coder → CFO → Proxy ──────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_coder_cfo_proxy(keypair):
    """Full chain: Coder requests $5 → CFO approves + signs → Proxy accepts."""
    signing_key, verify_key = keypair
    toolkit = CFOToolkit(signing_key=signing_key, budget_limit_usd=50.0)

    # Step 1: Coder creates expense request
    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="API access for code generation subtask",
    )

    # Step 2: CFO reviews — should approve
    review = toolkit.review_expense(req.model_dump(), "Build a web scraper")
    assert review["approved"] is True

    # Step 3: CFO signs
    result = toolkit.approve_and_sign(req.model_dump())
    assert result["signed"] is True
    assert len(result["signature"]) == 128

    # Step 4: Reconstruct signed request (as it would be read from file)
    signed_req = ExpenseRequest(
        amount=req.amount,
        target_api=req.target_api,
        justification=req.justification,
        nonce=req.nonce,
        timestamp=req.timestamp,
        signature=result["signature"],
    )

    # Step 5: EgressProxy verifies and forwards
    vault = KeyVault(verify_key)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    response = await proxy.forward(signed_req)
    assert response.forwarded is True
    assert response.status_code == 200
    assert response.request_nonce == req.nonce


# ── 6. Tamper Detection ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsigned_rejected_by_proxy(keypair):
    """ProxyRouter rejects an unsigned request with 403."""
    _, verify_key = keypair
    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="Unsigned request",
    )
    vault = KeyVault(verify_key)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    response = await proxy.forward(req)
    assert response.forwarded is False
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tampered_signed_rejected(keypair):
    """Modifying amount after signing → proxy rejects."""
    signing_key, verify_key = keypair
    toolkit = CFOToolkit(signing_key=signing_key, budget_limit_usd=50.0)

    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="Legit request",
    )
    result = toolkit.approve_and_sign(req.model_dump())

    # Tamper: change amount from $5 to $500
    tampered_req = ExpenseRequest(
        amount=500.00,  # TAMPERED
        target_api=req.target_api,
        justification=req.justification,
        nonce=req.nonce,
        timestamp=req.timestamp,
        signature=result["signature"],
    )

    vault = KeyVault(verify_key)
    proxy = ProxyRouter(vault)
    proxy._client = FakeClient()

    response = await proxy.forward(tampered_req)
    assert response.forwarded is False
    assert response.status_code == 403


# ── 7. Budget Exhaustion ─────────────────────────────────────────────────


def test_budget_exhaustion(keypair):
    """Multiple approvals exhaust budget; next review returns False."""
    signing_key, _ = keypair
    tk = CFOToolkit(signing_key=signing_key, budget_limit_usd=10.0)

    # Approve $4
    req1 = ExpenseRequest(
        amount=4.00,
        target_api="https://api.openai.com/v1/embeddings",
        justification="Embedding generation",
    )
    tk.approve_and_sign(req1.model_dump())
    assert tk.total_approved == 4.0

    # Approve $4 more ($8 total)
    req2 = ExpenseRequest(
        amount=4.00,
        target_api="https://api.openai.com/v1/embeddings",
        justification="More embeddings",
    )
    tk.approve_and_sign(req2.model_dump())
    assert tk.total_approved == 8.0
    assert tk.remaining_budget == 2.0

    # Try $5 — over budget
    req3 = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/embeddings",
        justification="Even more embeddings",
    )
    review = tk.review_expense(req3.model_dump(), "")
    assert review["approved"] is False
    assert "Over budget" in review["reason"]


# ── 8. Stripe Dry-Run ───────────────────────────────────────────────────


def test_stripe_dry_run(toolkit):
    """record_stripe_charge without API key returns dry_run."""
    result = toolkit.record_stripe_charge(
        amount=5.00,
        description="Test charge",
        metadata={"colony": "test-colony"},
    )
    assert result["mode"] == "dry_run"
    assert result["status"] == "succeeded"
    assert result["amount"] == 5.00
    assert result["charge_id"].startswith("dry_run_")


# ── 9. Tool Schema Registration ─────────────────────────────────────────


def test_tool_schemas_registered():
    """All 4 CFO/expense tools exist in _BUILTIN_TOOL_SCHEMAS."""
    from src.agents import _BUILTIN_TOOL_SCHEMAS

    expected = {"expense_request", "expense_review", "expense_approve", "expense_reject"}
    assert expected.issubset(set(_BUILTIN_TOOL_SCHEMAS.keys()))

    # Verify schemas have required fields
    for tool_name in expected:
        schema = _BUILTIN_TOOL_SCHEMAS[tool_name]
        assert "description" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"


# ── 10. Tool File I/O ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expense_request_creates_file(tmp_path):
    """_tool_expense_request writes valid JSON to expenses/pending/."""
    from src.agents import Agent

    agent = MagicMock(spec=Agent)
    agent.workspace_root = str(tmp_path)
    agent.config = {}

    # Call the method directly
    result = await Agent._tool_expense_request(
        agent, tmp_path,
        {
            "amount": 5.00,
            "target_api": "https://api.openai.com/v1/chat/completions",
            "justification": "Code generation",
        },
    )

    assert "Expense request created:" in result
    assert "$5.00" in result

    # Verify file exists and is valid JSON
    pending_dir = tmp_path / "expenses" / "pending"
    assert pending_dir.exists()
    files = list(pending_dir.glob("*.json"))
    assert len(files) == 1

    data = json.loads(files[0].read_text())
    assert data["amount"] == 5.0
    assert data["target_api"] == "https://api.openai.com/v1/chat/completions"
    assert data["signature"] == ""  # Unsigned


@pytest.mark.asyncio
async def test_approve_moves_file(tmp_path, keypair):
    """_tool_cfo_action("expense_approve") moves file from pending → approved."""
    from src.agents import Agent

    signing_key, _ = keypair
    toolkit = CFOToolkit(signing_key=signing_key, budget_limit_usd=50.0)

    # Create pending expense file
    req = ExpenseRequest(
        amount=5.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="Code generation",
    )
    pending_dir = tmp_path / "expenses" / "pending"
    pending_dir.mkdir(parents=True)
    pending_path = pending_dir / f"{req.nonce}.json"
    pending_path.write_text(req.model_dump_json(indent=2))

    agent = MagicMock(spec=Agent)
    agent.workspace_root = str(tmp_path)
    agent.config = {"cfo_toolkit": toolkit, "colony_objective": "Build web app"}

    result = await Agent._tool_cfo_action(
        agent, "expense_approve", tmp_path, {"request_id": req.nonce},
    )

    assert "APPROVED" in result
    assert "signed" in result.lower() or "Signature" in result

    # Pending file removed, approved file exists
    assert not pending_path.exists()
    approved_path = tmp_path / "expenses" / "approved" / f"{req.nonce}.json"
    assert approved_path.exists()

    data = json.loads(approved_path.read_text())
    assert data["signed"] is True
    assert len(data["signature"]) == 128


@pytest.mark.asyncio
async def test_reject_moves_file(tmp_path, keypair):
    """_tool_cfo_action("expense_reject") moves file from pending → rejected."""
    from src.agents import Agent

    signing_key, _ = keypair
    toolkit = CFOToolkit(signing_key=signing_key, budget_limit_usd=50.0)

    req = ExpenseRequest(
        amount=99.00,
        target_api="https://api.openai.com/v1/chat/completions",
        justification="Expensive request",
    )
    pending_dir = tmp_path / "expenses" / "pending"
    pending_dir.mkdir(parents=True)
    pending_path = pending_dir / f"{req.nonce}.json"
    pending_path.write_text(req.model_dump_json(indent=2))

    agent = MagicMock(spec=Agent)
    agent.workspace_root = str(tmp_path)
    agent.config = {"cfo_toolkit": toolkit}

    result = await Agent._tool_cfo_action(
        agent, "expense_reject", tmp_path,
        {"request_id": req.nonce, "reason": "Too expensive"},
    )

    assert "REJECTED" in result
    assert "Too expensive" in result

    assert not pending_path.exists()
    rejected_path = tmp_path / "expenses" / "rejected" / f"{req.nonce}.json"
    assert rejected_path.exists()

    data = json.loads(rejected_path.read_text())
    assert data["rejected"] is True
    assert data["reason"] == "Too expensive"


# ── 11. Verify Key Match ─────────────────────────────────────────────────


def test_verify_key_matches(keypair):
    """toolkit.verify_key matches the signing key's derived public key."""
    signing_key, verify_key = keypair
    toolkit = CFOToolkit(signing_key=signing_key)
    assert toolkit.verify_key.encode() == verify_key.encode()
    assert toolkit.verify_key.encode() == signing_key.verify_key.encode()
