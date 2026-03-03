"""Full UI smoke test via MCP puppeteer — uses host.docker.internal."""
import asyncio
import base64
import json
import re
import sys

sys.path.insert(0, "/app")

# The puppeteer container can reach the host via this address
DASHBOARD_URL = "http://host.docker.internal:8080"


def parse_eval_result(result: str) -> dict:
    """Extract JSON from puppeteer_evaluate result string."""
    if not isinstance(result, str):
        return {}
    # Try to find JSON in the result
    for line in result.split("\n"):
        line = line.strip().strip('"')
        if not line:
            continue
        # Unescape JSON string
        try:
            maybe_json = json.loads(f'"{line}"') if line.startswith("\\") else line
            if isinstance(maybe_json, str) and maybe_json.startswith("{"):
                return json.loads(maybe_json)
        except (json.JSONDecodeError, TypeError):
            pass
        # Direct parse
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return {}


async def main():
    from src.mcp_client import MCPGatewayClient
    from src.models import MCPGatewayConfig

    mcp_config = MCPGatewayConfig(
        docker_fallback_endpoint="http://mcp-gateway:8811"
    )

    client = MCPGatewayClient(mcp_config)
    await client.connect()

    # Ensure puppeteer tools are loaded
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
    print(f"\n[Test 1] Navigate to {DASHBOARD_URL}...")
    try:
        nav = await client.call_tool("puppeteer_navigate", {"url": DASHBOARD_URL})
        ok = "Navigated" in str(nav)
        results.append(("Navigate to dashboard", ok, str(nav)[:200]))
        print(f"  {'PASS' if ok else 'FAIL'}: {nav}")
    except Exception as e:
        results.append(("Navigate to dashboard", False, str(e)))
        print(f"  FAIL: {e}")
        return

    # Wait for JS app to hydrate
    print("  Waiting 3s for app to render...")
    await asyncio.sleep(3)

    # ── Test 2: Page content check ──────────────────────────
    print("\n[Test 2] Evaluate page content...")
    try:
        raw = await client.call_tool("puppeteer_evaluate", {
            "script": """
                JSON.stringify({
                    title: document.title,
                    url: window.location.href,
                    bodyLength: document.body.innerHTML.length,
                    bodyText: document.body.innerText.substring(0, 800),
                    headings: Array.from(document.querySelectorAll('h1, h2, h3, h4')).map(h => h.textContent.trim()).slice(0, 10),
                    buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(Boolean).slice(0, 15),
                    inputs: Array.from(document.querySelectorAll('input, textarea, select')).map(i => ({tag: i.tagName, type: i.type || '', id: i.id || '', ph: i.placeholder || ''})).slice(0, 10),
                    navLinks: Array.from(document.querySelectorAll('nav a, .tab-btn, [role=tab]')).map(a => a.textContent.trim()).filter(Boolean),
                    images: document.querySelectorAll('img').length,
                    scripts: document.querySelectorAll('script').length,
                    styles: document.querySelectorAll('link[rel=stylesheet], style').length,
                    divCount: document.querySelectorAll('div').length,
                    spanCount: document.querySelectorAll('span').length,
                })
            """,
        })
        print(f"  Raw result: {str(raw)[:1500]}")
        data = parse_eval_result(str(raw))

        body_len = data.get("bodyLength", 0)
        has_content = body_len > 100
        results.append(("Page has HTML content", has_content, f"bodyLength={body_len}"))
        print(f"  {'PASS' if has_content else 'FAIL'}: bodyLength={body_len}")

        if data.get("title"):
            print(f"  Title: {data['title']}")
        if data.get("url"):
            print(f"  URL: {data['url']}")
        if data.get("bodyText"):
            print(f"  Body text (first 400 chars): {data['bodyText'][:400]}")
        if data.get("headings"):
            print(f"  Headings: {data['headings']}")
        if data.get("buttons"):
            results.append(("Has buttons", True, str(data["buttons"][:5])))
            print(f"  Buttons: {data['buttons']}")
        else:
            results.append(("Has buttons", False, "No buttons found"))
        if data.get("inputs"):
            print(f"  Inputs: {data['inputs']}")
        if data.get("navLinks"):
            results.append(("Has navigation tabs", True, str(data["navLinks"])))
            print(f"  Nav links/tabs: {data['navLinks']}")
        else:
            results.append(("Has navigation tabs", False, "No tabs found"))
        print(f"  Elements: divs={data.get('divCount', 0)}, spans={data.get('spanCount', 0)}, scripts={data.get('scripts', 0)}, styles={data.get('styles', 0)}")
    except Exception as e:
        results.append(("Page has HTML content", False, str(e)[:200]))
        print(f"  FAIL: {e}")

    # ── Test 3: API fetch from browser ──────────────────────
    print("\n[Test 3] Fetch /api/colony from browser...")
    try:
        raw = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    const resp = await fetch('/api/colony');
                    const data = await resp.json();
                    return JSON.stringify({
                        ok: resp.ok,
                        status: resp.status,
                        keys: Object.keys(data),
                        colonyStatus: data.status,
                        task: (data.task || '').substring(0, 100),
                        agents: (data.agents || []).length,
                    });
                })()
            """,
        })
        data = parse_eval_result(str(raw))
        api_ok = data.get("ok", False)
        results.append(("API /api/colony from browser", api_ok, f"status={data.get('status')}, keys={data.get('keys')}"))
        print(f"  {'PASS' if api_ok else 'FAIL'}: {data}")
    except Exception as e:
        results.append(("API /api/colony from browser", False, str(e)[:200]))
        print(f"  FAIL: {e}")

    # ── Test 4: V1 health from browser ──────────────────────
    print("\n[Test 4] Fetch /api/v1/system/health from browser...")
    try:
        raw = await client.call_tool("puppeteer_evaluate", {
            "script": """
                (async () => {
                    const resp = await fetch('/api/v1/system/health');
                    return JSON.stringify(await resp.json());
                })()
            """,
        })
        health_ok = "healthy" in str(raw).lower()
        results.append(("V1 health endpoint", health_ok, str(raw)[:200]))
        print(f"  {'PASS' if health_ok else 'FAIL'}: {str(raw)[:300]}")
    except Exception as e:
        results.append(("V1 health endpoint", False, str(e)[:200]))
        print(f"  FAIL: {e}")

    # ── Test 5: WebSocket from browser ──────────────────────
    print("\n[Test 5] WebSocket connection from browser...")
    try:
        raw = await client.call_tool("puppeteer_evaluate", {
            "script": """
                new Promise((resolve) => {
                    const timeout = setTimeout(() => resolve(JSON.stringify({connected: false, error: 'timeout'})), 5000);
                    const ws = new WebSocket('ws://' + location.host + '/ws');
                    ws.onopen = () => { clearTimeout(timeout); ws.close(); resolve(JSON.stringify({connected: true})); };
                    ws.onerror = () => { clearTimeout(timeout); resolve(JSON.stringify({connected: false, error: 'ws_error'})); };
                })
            """,
        })
        ws_ok = "true" in str(raw).lower() and "connected" in str(raw).lower()
        results.append(("WebSocket connection", ws_ok, str(raw)[:200]))
        print(f"  {'PASS' if ws_ok else 'FAIL'}: {str(raw)[:300]}")
    except Exception as e:
        results.append(("WebSocket connection", False, str(e)[:200]))
        print(f"  FAIL: {e}")

    # ── Test 6: Full-page screenshot at 1920x1080 ──────────
    print("\n[Test 6] Full-page screenshot (1920x1080)...")
    try:
        raw = await client.call_tool("puppeteer_screenshot", {
            "name": "dashboard_full",
            "width": 1920,
            "height": 1080,
        })
        # Try to extract and save base64 image
        saved = False
        if isinstance(raw, str):
            m = re.search(r"data='([A-Za-z0-9+/=]+)", raw)
            if m:
                img_data = base64.b64decode(m.group(1))
                with open("/app/workspace/dashboard_full.png", "wb") as f:
                    f.write(img_data)
                results.append(("Full screenshot", True, f"Saved ({len(img_data)} bytes)"))
                print(f"  PASS: Saved workspace/dashboard_full.png ({len(img_data)} bytes)")
                saved = True
        if not saved:
            results.append(("Full screenshot", len(str(raw)) > 100, f"Got data ({len(str(raw))} chars)"))
            print(f"  PASS: Got screenshot data ({len(str(raw))} chars)")
    except Exception as e:
        results.append(("Full screenshot", False, str(e)[:200]))
        print(f"  FAIL: {e}")

    # ── Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  FORMICOS UI SMOKE TEST — MCP PUPPETEER")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}")
        print(f"         {detail[:100]}")
    print(f"\n  Total: {passed} passed, {failed} failed out of {len(results)}")
    print("=" * 60)

    try:
        await client.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
