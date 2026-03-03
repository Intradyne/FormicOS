"""
FormicOS v0.8.0 -- CFO Toolkit

Colony Financial Officer: Ed25519 expense signing + Stripe ledger.

The CFO caste is the colony's sole holder of the Ed25519 private key.
It reviews expense requests from Coder agents, signs approved requests
so the EgressProxy will forward them, and records all transactions to
an append-only ledger.

Integration:
  - Injected into a standard Agent via ``config["cfo_toolkit"]``
  - Tools dispatched in ``Agent._execute_tool()`` for expense_review,
    expense_approve, expense_reject
  - Orchestrator Phase 4.5 instantiates an ephemeral CFO agent when
    pending expense requests are detected in the workspace

Thread safety:
  - CFOToolkit is used only from the single orchestrator task — no
    concurrent access.  All mutations (ledger, budget) are sequential.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import nacl.signing

from src.core.network.egress_proxy import ExpenseRequest

logger = logging.getLogger("formicos.cfo")


class CFOToolkit:
    """Colony Financial Officer — Ed25519 signing + Stripe ledger.

    Parameters
    ----------
    signing_key : nacl.signing.SigningKey
        The colony's Ed25519 private key for expense signing.
    colony_id : str
        Colony identifier for audit trail.
    budget_limit_usd : float
        Maximum cumulative spend allowed (default: $100).
    stripe_api_key : str | None
        Stripe secret key.  If None, Stripe operations run in dry-run
        mode (no network calls, logged locally).
    """

    def __init__(
        self,
        signing_key: nacl.signing.SigningKey,
        colony_id: str = "",
        budget_limit_usd: float = 100.0,
        stripe_api_key: str | None = None,
    ) -> None:
        self._signing_key = signing_key
        self._verify_key = signing_key.verify_key
        self._colony_id = colony_id
        self._budget_limit_usd = budget_limit_usd
        self._total_approved: float = 0.0
        self._ledger: list[dict[str, Any]] = []
        self._stripe_api_key = stripe_api_key

    # ── Properties ────────────────────────────────────────────────────

    @property
    def verify_key(self) -> nacl.signing.VerifyKey:
        """Public key for distribution to the EgressProxy / KeyVault."""
        return self._verify_key

    @property
    def ledger(self) -> list[dict[str, Any]]:
        """Copy of the full audit trail."""
        return list(self._ledger)

    @property
    def total_approved(self) -> float:
        """Cumulative approved spend in USD."""
        return self._total_approved

    @property
    def remaining_budget(self) -> float:
        """Remaining budget in USD."""
        return max(0.0, self._budget_limit_usd - self._total_approved)

    # ── Review ────────────────────────────────────────────────────────

    def review_expense(
        self,
        request_json: dict[str, Any],
        colony_objective: str = "",
    ) -> dict[str, Any]:
        """Review an expense request against budget constraints.

        This is advisory — it does NOT sign the request.  The CFO agent
        uses this to decide whether to call ``approve_and_sign`` or
        ``reject_expense``.

        Parameters
        ----------
        request_json : dict
            Serialized ExpenseRequest fields.
        colony_objective : str
            The colony's current goal (for alignment check).

        Returns
        -------
        dict
            ``{approved, reason, remaining_budget, request_nonce, amount}``
        """
        try:
            req = ExpenseRequest(**request_json)
        except Exception as exc:
            return {
                "approved": False,
                "reason": f"Invalid expense request: {exc}",
                "remaining_budget": self.remaining_budget,
                "request_nonce": request_json.get("nonce", ""),
                "amount": request_json.get("amount", 0),
            }

        remaining = self.remaining_budget
        if req.amount > remaining:
            return {
                "approved": False,
                "reason": (
                    f"Over budget: requested ${req.amount:.2f} but only "
                    f"${remaining:.2f} remains of ${self._budget_limit_usd:.2f} limit"
                ),
                "remaining_budget": remaining,
                "request_nonce": req.nonce,
                "amount": req.amount,
            }

        return {
            "approved": True,
            "reason": "Within budget and ready for signing",
            "remaining_budget": remaining - req.amount,
            "request_nonce": req.nonce,
            "amount": req.amount,
        }

    # ── Approve & Sign ────────────────────────────────────────────────

    def approve_and_sign(
        self,
        request_json: dict[str, Any],
    ) -> dict[str, Any]:
        """Sign an approved ExpenseRequest with the colony's Ed25519 key.

        Increments cumulative spend and records to the ledger.

        Parameters
        ----------
        request_json : dict
            Serialized ExpenseRequest fields (unsigned).

        Returns
        -------
        dict
            ``{signed, signature, nonce, amount, timestamp}``
        """
        req = ExpenseRequest(**request_json)
        req.sign(self._signing_key)

        self._total_approved += req.amount

        record = {
            "action": "approved",
            "nonce": req.nonce,
            "amount": req.amount,
            "target_api": req.target_api,
            "justification": req.justification,
            "signature": req.signature,
            "timestamp": time.time(),
            "colony_id": self._colony_id,
            "cumulative_spend": self._total_approved,
        }
        self._ledger.append(record)

        logger.info(
            "CFO approved: $%.2f → %s (nonce=%s, cumulative=$%.2f)",
            req.amount, req.target_api, req.nonce, self._total_approved,
        )

        return {
            "signed": True,
            "signature": req.signature,
            "nonce": req.nonce,
            "amount": req.amount,
            "timestamp": req.timestamp,
        }

    # ── Reject ────────────────────────────────────────────────────────

    def reject_expense(
        self,
        request_json: dict[str, Any],
        reason: str = "Rejected by CFO",
    ) -> dict[str, Any]:
        """Reject an expense request and record to the ledger.

        Parameters
        ----------
        request_json : dict
            Serialized ExpenseRequest fields.
        reason : str
            Human-readable rejection reason.

        Returns
        -------
        dict
            ``{rejected, reason, nonce, amount}``
        """
        nonce = request_json.get("nonce", "unknown")
        amount = request_json.get("amount", 0)

        record = {
            "action": "rejected",
            "nonce": nonce,
            "amount": amount,
            "target_api": request_json.get("target_api", ""),
            "reason": reason,
            "timestamp": time.time(),
            "colony_id": self._colony_id,
        }
        self._ledger.append(record)

        logger.info(
            "CFO rejected: $%.2f (nonce=%s): %s",
            amount, nonce, reason,
        )

        return {
            "rejected": True,
            "reason": reason,
            "nonce": nonce,
            "amount": amount,
        }

    # ── Stripe Ledger ─────────────────────────────────────────────────

    def record_stripe_charge(
        self,
        amount: float,
        description: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Record a charge via Stripe (or dry-run if no API key).

        Parameters
        ----------
        amount : float
            Amount in USD.
        description : str
            Charge description.
        metadata : dict | None
            Additional key-value metadata for the charge.

        Returns
        -------
        dict
            ``{charge_id, amount, status, mode}``
        """
        if self._stripe_api_key is None:
            charge_id = f"dry_run_{int(time.time())}"
            logger.info(
                "CFO Stripe dry-run: $%.2f — %s", amount, description,
            )
            return {
                "charge_id": charge_id,
                "amount": amount,
                "status": "succeeded",
                "mode": "dry_run",
            }

        try:
            import stripe
            stripe.api_key = self._stripe_api_key

            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Stripe uses cents
                currency="usd",
                description=description,
                metadata=metadata or {},
            )
            logger.info(
                "CFO Stripe charge: $%.2f — %s (id=%s)",
                amount, description, intent.id,
            )
            return {
                "charge_id": intent.id,
                "amount": amount,
                "status": intent.status,
                "mode": "live",
            }
        except Exception as exc:
            logger.error("Stripe charge failed: %s", exc)
            return {
                "charge_id": "",
                "amount": amount,
                "status": f"failed: {exc}",
                "mode": "live",
            }
