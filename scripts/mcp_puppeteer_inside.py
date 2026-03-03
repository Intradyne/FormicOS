"""Run inside formicos-colony container to test UI via MCP puppeteer."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")


async def main():
    from src.mcp_client import MCPGatewayClient
    from src.models import MCPGatewayConfig

    mcp_config = MCPGatewayConfig(
        docker_fallback_endpoint="http://mcp-gateway:8811"
    )

    client = MCPGatewayClient(mcp_config)
    await client.connect()

    print(f"Connected: {client.connected}")
    tool_names = [
        t.get("id") if isinstance(t, dict) else getattr(t, "name", str(t))
        for t in client._tools
    ]
    print(f"Tools ({len(tool_names)}): {tool_names}")

    # Step 1: Add puppeteer server
    print("\n=== Step 1: Adding puppeteer ===")
    try:
        result = await client.call_tool("mcp-add", {"name": "puppeteer", "activate": True})
        print(f"mcp-add result: {result}")
    except Exception as e:
        print(f"mcp-add error: {e}")

    # Wait for puppeteer container to spin up
    print("\nWaiting 8s for puppeteer container...")
    await asyncio.sleep(8)

    # Refresh tool list
    print("\n=== Step 2: Refreshing tools ===")
    try:
        await client.refresh_tools()
        tool_names = [
            t.get("id") if isinstance(t, dict) else getattr(t, "name", str(t))
            for t in client._tools
        ]
        print(f"Tools after refresh ({len(tool_names)}): {tool_names}")
    except Exception as e:
        print(f"refresh error: {e}")

    # Step 3: Navigate to FormicOS dashboard
    # From inside Docker, the formicos service is at localhost:8000
    # or host.docker.internal:8080
    print("\n=== Step 3: puppeteer_navigate ===")
    try:
        result = await client.call_tool("puppeteer_navigate", {
            "url": "http://formicos-colony:8000",
        })
        print(f"Navigate result: {json.dumps(result, indent=2)[:2000]}")
    except Exception as e:
        print(f"Navigate error: {e}")
        # Try alternate URL
        print("Trying host.docker.internal:8080...")
        try:
            result = await client.call_tool("puppeteer_navigate", {
                "url": "http://host.docker.internal:8080",
            })
            print(f"Navigate result: {json.dumps(result, indent=2)[:2000]}")
        except Exception as e2:
            print(f"Navigate error (alt): {e2}")

    # Step 4: Take screenshot
    print("\n=== Step 4: puppeteer_screenshot ===")
    try:
        result = await client.call_tool("puppeteer_screenshot", {})
        if isinstance(result, dict):
            # Truncate base64 image data for display
            for k, v in result.items():
                if isinstance(v, str) and len(v) > 200:
                    result[k] = v[:200] + f"... ({len(v)} chars total)"
            print(f"Screenshot result: {json.dumps(result, indent=2)[:2000]}")
        elif isinstance(result, str):
            print(f"Screenshot result (string, {len(result)} chars): {result[:500]}")
        else:
            print(f"Screenshot result type: {type(result)}, value: {str(result)[:500]}")
    except Exception as e:
        print(f"Screenshot error: {e}")

    # Step 5: Evaluate page content
    print("\n=== Step 5: puppeteer_evaluate ===")
    try:
        result = await client.call_tool("puppeteer_evaluate", {
            "script": "JSON.stringify({title: document.title, bodyLen: document.body.innerText.length, hasCanvas: !!document.querySelector('canvas'), buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(Boolean).slice(0, 10), tabs: Array.from(document.querySelectorAll('nav a, .tab, button.tab-btn, [role=tab]')).map(t => t.textContent.trim()).filter(Boolean)})",
        })
        print(f"Evaluate result: {json.dumps(result, indent=2)[:2000]}")
    except Exception as e:
        print(f"Evaluate error: {e}")

    # Cleanup
    try:
        await client.disconnect()
    except Exception:
        pass

    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
