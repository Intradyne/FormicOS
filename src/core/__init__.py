"""FormicOS core modules -- orchestrator, memory, routing.

v0.7.9 scaffolding: Re-exports from existing src/ flat layout.
Future versions will move source files into subdirectories.
"""
from src.orchestrator import Orchestrator
from src.context import AsyncContextTree
from src.stigmergy import SharedWorkspaceManager
from src.rag import RAGEngine

# v0.8.0: Cryptographic egress proxy
from src.core.network import EgressProxyError, ProxyRouter, KeyVault

# v0.8.0: REPL harness + sub-agent routing
from src.core.repl import REPLHarness, REPLHarnessError
from src.core.orchestrator.router import SubcallRouter

# v0.8.0: CFO toolkit (Ed25519 signing + Stripe ledger)
from src.core.cfo import CFOToolkit

__all__ = [
    "Orchestrator", "AsyncContextTree", "SharedWorkspaceManager", "RAGEngine",
    "EgressProxyError", "ProxyRouter", "KeyVault",
    "REPLHarness", "REPLHarnessError", "SubcallRouter",
    "CFOToolkit",
]
