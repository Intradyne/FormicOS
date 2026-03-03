"""FormicOS service modules -- webhook, worker, audit, ingestion.

v0.7.9 scaffolding: Re-exports from existing src/ flat layout.
v0.8.0: Added ingestion (AsyncDocumentIngestor).
"""
from src.webhook import WebhookDispatcher
from src.worker import WorkerManager
from src.services.ingestion import AsyncDocumentIngestor

__all__ = ["WebhookDispatcher", "WorkerManager", "AsyncDocumentIngestor"]
