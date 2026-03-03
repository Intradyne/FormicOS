"""Allow ``python -m src.mcp`` to launch the inbound memory server."""

import asyncio

from src.mcp.inbound_memory_server import main

asyncio.run(main())
