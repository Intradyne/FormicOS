from __future__ import annotations

import asyncio

import pytest

from formicos.engine.service_router import ServiceRouter


@pytest.mark.asyncio
async def test_query_uses_default_inject_fn() -> None:
    injected: list[tuple[str, str]] = []
    router = ServiceRouter(
        inject_fn=lambda colony_id, message: _record_injected(injected, colony_id, message)
    )
    router.register("research", "col-abc")

    async def _resolve_later() -> None:
        await asyncio.sleep(0)
        assert injected
        message = injected[0][1]
        request_id = message.split("\n", 1)[0].split(":", 1)[1].strip(" ]")
        router.resolve_response(request_id, "done")

    task = asyncio.create_task(router.query("research", "find docs"))
    await _resolve_later()
    assert await task == "done"
    assert injected[0][0] == "col-abc"
    assert injected[0][1].startswith("[Service Query:")


@pytest.mark.asyncio
async def test_query_without_inject_fn_raises_runtime_error() -> None:
    router = ServiceRouter()
    router.register("research", "col-abc")

    with pytest.raises(RuntimeError, match="injection function"):
        await router.query("research", "find docs")


async def _record_injected(
    injected: list[tuple[str, str]],
    colony_id: str,
    message: str,
) -> None:
    injected.append((colony_id, message))
