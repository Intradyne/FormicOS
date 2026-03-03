"""Full UI smoke test via MCP puppeteer — runs inside formicos-colony."""
import asyncio
import base64
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

    # Ensure puppeteer is available
    tool_names = [
        t.get("id") if isinstance(t, dict) else getattr(t, "name", str(t))
        for t in client._tools
    ]
    if "puppeteer_navigate" not in tool_names:
        print("Adding puppeteer...")
        await client.call_tool("mcp-add", {"name": "puppeteer", "activate": True})
        await asyncio.sleep(8)
        await client.refresh_tools()

    results = []

    # ── Test 1: Navigate to dashboard ───────────────────────
    print("\n[Test 1] Navigate to FormicOS dashboard...")
    try:
        nav_result = await client.call_tool("puppeteer_navigate", {
            "url": "http://formicos-colony:8000",
        })
        passed = "Navigated" in str(nav_result)
        results.append(("Navigate to dashboard", passed, str(nav_result)[:200]))
        print(f"  {'PASS' if passed else 'FAIL'}: {nav_result}")
    except Exception as e:
        results.append(("Navigate to dashboard", False, str(e)))
        print(f"  FAIL: {e}")

    # Wait for JS to hydrate
    await asyncio.sleep(2)

    # ── Test 2: Check page has loaded (title, body) ─────────
    print("\n[Test 2] Check page content...")
    try:
        result = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    // Wait for content to appear
                    await new Promise(r => setTimeout(r, 2000));
                    return JSON.stringify({
                        title: document.title,
                        url: window.location.href,
                        bodyLength: document.body.innerHTML.length,
                        bodyText: document.body.innerText.substring(0, 500),
                        h1: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.textContent.trim()).slice(0, 5),
                        links: Array.from(document.querySelectorAll('a')).map(a => a.textContent.trim()).filter(Boolean).slice(0, 10),
                        buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(Boolean).slice(0, 10),
                        inputs: Array.from(document.querySelectorAll('input, textarea')).map(i => ({type: i.type, id: i.id, placeholder: i.placeholder})).slice(0, 5),
                        scripts: document.querySelectorAll('script').length,
                        stylesheets: document.querySelectorAll('link[rel=stylesheet], style').length,
                    });
                })()
            """,
        })
        # Parse the result
        print(f"  Raw: {str(result)[:1000]}")
        data = {}
        try:
            # The result may be wrapped in "Execution result:\n..."
            if isinstance(result, str):
                # Extract JSON from the result string
                lines = result.split("\n")
                for line in lines:
                    line = line.strip().strip('"')
                    if line.startswith("{"):
                        data = json.loads(line)
                        break
                    # Handle escaped JSON
                    try:
                        unescaped = json.loads(f'"{line}"') if line.startswith("\\") else line
                        if isinstance(unescaped, str) and unescaped.startswith("{"):
                            data = json.loads(unescaped)
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass
        except (json.JSONDecodeError, TypeError) as e:
            print(f"  Parse error: {e}")

        has_content = data.get("bodyLength", 0) > 100
        results.append(("Page has content", has_content, f"bodyLength={data.get('bodyLength', 0)}, title={data.get('title', '')}"))
        print(f"  {'PASS' if has_content else 'FAIL'}: bodyLength={data.get('bodyLength', 0)}")

        if data.get("bodyText"):
            print(f"  Body text: {data['bodyText'][:300]}")
        if data.get("buttons"):
            print(f"  Buttons: {data['buttons']}")
        if data.get("inputs"):
            print(f"  Inputs: {data['inputs']}")
        if data.get("h1"):
            print(f"  Headings: {data['h1']}")
    except Exception as e:
        results.append(("Page has content", False, str(e)))
        print(f"  FAIL: {e}")

    # ── Test 3: Screenshot dashboard ────────────────────────
    print("\n[Test 3] Take dashboard screenshot...")
    try:
        result = await client.call_tool("puppeteer_screenshot", {
            "name": "dashboard",
            "width": 1920,
            "height": 1080,
        })
        # Save the screenshot
        if isinstance(result, str) and "data=" in result:
            # Extract base64 data after "data='"
            import re
            m = re.search(r"data='([A-Za-z0-9+/=]+)", result)
            if m:
                img_data = base64.b64decode(m.group(1))
                with open("/app/workspace/dashboard_screenshot.png", "wb") as f:
                    f.write(img_data)
                results.append(("Dashboard screenshot", True, f"Saved ({len(img_data)} bytes)"))
                print(f"  PASS: Saved to workspace/dashboard_screenshot.png ({len(img_data)} bytes)")
            else:
                results.append(("Dashboard screenshot", True, f"Captured ({len(result)} chars)"))
                print(f"  PASS: Captured ({len(result)} chars)")
        else:
            results.append(("Dashboard screenshot", True, str(type(result))))
            print(f"  PASS: Got result type {type(result)}")
    except Exception as e:
        results.append(("Dashboard screenshot", False, str(e)))
        print(f"  FAIL: {e}")

    # ── Test 4: Check API connectivity from browser ─────────
    print("\n[Test 4] Test API fetch from browser context...")
    try:
        result = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    try {
                        const resp = await fetch('/api/colony');
                        const data = await resp.json();
                        return JSON.stringify({
                            ok: resp.ok,
                            status: resp.status,
                            keys: Object.keys(data),
                            task: data.task,
                            colony_status: data.status,
                        });
                    } catch(e) {
                        return JSON.stringify({ok: false, error: e.message});
                    }
                })()
            """,
        })
        print(f"  Raw: {str(result)[:500]}")
        api_ok = "ok" in str(result) and "true" in str(result).lower()
        results.append(("API fetch from browser", api_ok, str(result)[:200]))
        print(f"  {'PASS' if api_ok else 'FAIL'}")
    except Exception as e:
        results.append(("API fetch from browser", False, str(e)))
        print(f"  FAIL: {e}")

    # ── Test 5: Check WebSocket from browser ────────────────
    print("\n[Test 5] Test WebSocket from browser...")
    try:
        result = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    return new Promise((resolve) => {
                        const timeout = setTimeout(() => resolve(JSON.stringify({connected: false, error: 'timeout'})), 5000);
                        const ws = new WebSocket('ws://' + location.host + '/ws');
                        ws.onopen = () => {
                            clearTimeout(timeout);
                            ws.close();
                            resolve(JSON.stringify({connected: true}));
                        };
                        ws.onerror = () => {
                            clearTimeout(timeout);
                            resolve(JSON.stringify({connected: false, error: 'connection error'}));
                        };
                    });
                })()
            """,
        })
        ws_ok = "connected" in str(result) and "true" in str(result).lower()
        results.append(("WebSocket connection", ws_ok, str(result)[:200]))
        print(f"  {'PASS' if ws_ok else 'FAIL'}: {str(result)[:200]}")
    except Exception as e:
        results.append(("WebSocket connection", False, str(e)))
        print(f"  FAIL: {e}")

    # ── Test 6: Check V1 health endpoint from browser ───────
    print("\n[Test 6] V1 health endpoint from browser...")
    try:
        result = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    const resp = await fetch('/api/v1/system/health');
                    const data = await resp.json();
                    return JSON.stringify(data);
                })()
            """,
        })
        health_ok = "healthy" in str(result).lower()
        results.append(("V1 health endpoint", health_ok, str(result)[:200]))
        print(f"  {'PASS' if health_ok else 'FAIL'}: {str(result)[:200]}")
    except Exception as e:
        results.append(("V1 health endpoint", False, str(e)))
        print(f"  FAIL: {e}")

    # ── Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  UI SMOKE TEST RESULTS (via MCP Puppeteer)")
    print("=" * 60)
    passed = 0
    failed = 0
    for name, ok, detail in results:
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}: {detail[:80]}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)}")
    print("=" * 60)

    try:
        await client.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
