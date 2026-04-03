"""Wave 84.5 Track B: Eval harness fixtures."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live-LLM eval tests unless FORMICOS_LIVE_EVAL=1."""
    skip_live = pytest.mark.skip(reason="FORMICOS_LIVE_EVAL not set")
    for item in items:
        if "live_eval" in item.keywords and not os.environ.get("FORMICOS_LIVE_EVAL"):
            item.add_marker(skip_live)
