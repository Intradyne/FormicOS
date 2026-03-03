"""
FormicOS UI Smoke Test via MCP Gateway + Puppeteer.

Connects to the Docker MCP Gateway SSE endpoint, activates the puppeteer
server, then calls puppeteer_navigate to check the FormicOS dashboard.
"""
import asyncio
import json
import uuid
import httpx

GATEWAY = "http://localhost:8811"


async def mcp_call(client: httpx.AsyncClient, session_id: str, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC request to the MCP gateway."""
    req_id = str(uuid.uuid4())[:8]
    body = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params:
        body["params"] = params

    resp = await client.post(
        f"{GATEWAY}/sse?sessionid={session_id}",
        json=body,
        timeout=30.0,
    )
    return {"status": resp.status_code, "text": resp.text}


async def mcp_tool_call(client: httpx.AsyncClient, session_id: str, tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool via tools/call."""
    return await mcp_call(client, session_id, "tools/call", {
        "name": tool_name,
        "arguments": arguments,
    })


async def read_sse_events(client: httpx.AsyncClient, session_id: str, timeout: float = 10.0) -> list[dict]:
    """Read SSE events until timeout."""
    events = []
    try:
        async with client.stream("GET", f"{GATEWAY}/sse?sessionid={session_id}", timeout=timeout) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        events.append(data)
                    except json.JSONDecodeError:
                        pass
    except (httpx.ReadTimeout, httpx.RemoteProtocolError):
        pass
    return events


async def main():
    print("=" * 60)
    print("  FormicOS UI Smoke Test — MCP Puppeteer")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Step 1: Connect to MCP Gateway and get session
        print("\n[1] Connecting to MCP Gateway SSE...")
        session_id = None
        try:
            async with client.stream("GET", f"{GATEWAY}/sse", timeout=5.0) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            # The gateway sends a session ID on connect
                            if isinstance(data, dict) and "sessionid" in str(data).lower():
                                print(f"  Event: {json.dumps(data)[:200]}")
                            events_text = line[6:]
                        except json.JSONDecodeError:
                            pass
                    elif "sessionid=" in line:
                        # Parse session ID from event
                        print(f"  Raw: {line[:200]}")
                    # Break after first few events
                    if session_id or len(line) > 0:
                        break
        except (httpx.ReadTimeout, httpx.RemoteProtocolError):
            pass

        # Try getting session from the endpoint URL pattern
        print("\n[2] Getting fresh SSE session...")
        try:
            # The Docker MCP gateway sends the session ID in the first SSE message
            collected_lines = []
            async with client.stream("GET", f"{GATEWAY}/sse", timeout=5.0) as resp:
                async for line in resp.aiter_lines():
                    collected_lines.append(line)
                    if len(collected_lines) >= 5:
                        break
            for line in collected_lines:
                print(f"  SSE: {line[:300]}")
                if "sessionid" in line.lower() or "endpoint" in line.lower():
                    # Extract session ID
                    try:
                        data = json.loads(line.replace("data: ", ""))
                        if "sessionId" in data:
                            session_id = data["sessionId"]
                        elif "endpoint" in str(data):
                            # Parse from endpoint URL
                            import re
                            m = re.search(r"sessionid=([A-Z0-9]+)", str(data), re.IGNORECASE)
                            if m:
                                session_id = m.group(1)
                    except (json.JSONDecodeError, TypeError):
                        import re
                        m = re.search(r"sessionid=([A-Z0-9]+)", line, re.IGNORECASE)
                        if m:
                            session_id = m.group(1)
        except (httpx.ReadTimeout, httpx.RemoteProtocolError):
            pass

        if session_id:
            print(f"  Session ID: {session_id}")
        else:
            print("  No session ID found, trying direct approach...")
            # Just send messages and see what happens
            session_id = "test-session"

        # Step 3: Add puppeteer server
        print("\n[3] Adding puppeteer MCP server...")
        result = await mcp_tool_call(client, session_id, "mcp-add", {
            "name": "puppeteer",
            "activate": True,
        })
        print(f"  Result: {result}")

        # Wait for puppeteer to spin up
        print("  Waiting 5s for puppeteer container to start...")
        await asyncio.sleep(5)

        # Step 4: List available tools (should now include puppeteer)
        print("\n[4] Listing tools...")
        result = await mcp_call(client, session_id, "tools/list")
        print(f"  Tools response: {result['text'][:500]}")

        # Step 5: Call puppeteer_navigate
        print("\n[5] Navigating to FormicOS dashboard...")
        result = await mcp_tool_call(client, session_id, "puppeteer_navigate", {
            "url": "http://host.docker.internal:8080",
        })
        print(f"  Navigate result: {result}")

        # Step 6: Take screenshot
        print("\n[6] Taking screenshot...")
        result = await mcp_tool_call(client, session_id, "puppeteer_screenshot", {})
        print(f"  Screenshot result status: {result['status']}")
        if result.get("text"):
            print(f"  Response: {result['text'][:500]}")

    print("\n" + "=" * 60)
    print("  Test complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
