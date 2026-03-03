/**
 * FormicOS UI Smoke Test — Puppeteer
 * Navigates to the dashboard, captures screenshots, and checks key elements.
 */
import puppeteer from "puppeteer";

const BASE = "http://localhost:8080";
const SCREENSHOT_DIR = "./screenshots";

async function main() {
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  const results = [];

  // ── Test 1: Dashboard loads ──────────────────────────────
  console.log("\n[Test 1] Loading dashboard...");
  try {
    const resp = await page.goto(BASE, { waitUntil: "networkidle2", timeout: 15000 });
    const status = resp.status();
    results.push({ test: "Dashboard loads", pass: status === 200, detail: `HTTP ${status}` });
    console.log(`  HTTP ${status}`);
  } catch (err) {
    results.push({ test: "Dashboard loads", pass: false, detail: err.message });
    console.error(`  FAIL: ${err.message}`);
  }

  // ── Test 2: Title check ──────────────────────────────────
  console.log("[Test 2] Checking page title...");
  const title = await page.title();
  results.push({ test: "Page title", pass: title.length > 0, detail: title });
  console.log(`  Title: "${title}"`);

  // ── Test 3: Key UI elements present ──────────────────────
  console.log("[Test 3] Checking key UI elements...");
  const checks = [
    { name: "Header/Logo", selector: "header, .header, h1, .logo, #logo, .brand" },
    { name: "Task input", selector: "textarea, input[type='text'], #task, .task-input, #taskInput" },
    { name: "Run/Start button", selector: "button" },
    { name: "Navigation tabs", selector: "nav, .tabs, .tab, [role='tablist'], .nav-tabs" },
  ];

  for (const check of checks) {
    const el = await page.$(check.selector);
    const found = el !== null;
    results.push({ test: `UI element: ${check.name}`, pass: found, detail: found ? "Found" : "Not found" });
    console.log(`  ${check.name}: ${found ? "FOUND" : "NOT FOUND"}`);
  }

  // ── Test 4: Screenshot of main dashboard ─────────────────
  console.log("[Test 4] Taking screenshot...");
  try {
    await page.screenshot({ path: `${SCREENSHOT_DIR}/01_dashboard.png`, fullPage: true });
    results.push({ test: "Screenshot: dashboard", pass: true, detail: "01_dashboard.png" });
    console.log("  Saved: 01_dashboard.png");
  } catch (err) {
    results.push({ test: "Screenshot: dashboard", pass: false, detail: err.message });
  }

  // ── Test 5: Check colony status panel ────────────────────
  console.log("[Test 5] Checking colony status...");
  const bodyText = await page.evaluate(() => document.body.innerText);
  const hasStatusText = /colony|status|idle|running|task/i.test(bodyText);
  results.push({ test: "Colony status text present", pass: hasStatusText, detail: hasStatusText ? "Status text found" : "No status text" });
  console.log(`  Status text: ${hasStatusText ? "FOUND" : "NOT FOUND"}`);

  // ── Test 6: API health via fetch from browser ────────────
  console.log("[Test 6] Fetching /api/colony from browser context...");
  const apiResult = await page.evaluate(async () => {
    try {
      const resp = await fetch("/api/colony");
      const data = await resp.json();
      return { ok: resp.ok, status: resp.status, keys: Object.keys(data) };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  });
  results.push({
    test: "API fetch from browser",
    pass: apiResult.ok,
    detail: apiResult.ok ? `Keys: ${apiResult.keys.join(", ")}` : apiResult.error,
  });
  console.log(`  API: ${apiResult.ok ? "OK" : "FAIL"} — ${JSON.stringify(apiResult)}`);

  // ── Test 7: WebSocket connection ─────────────────────────
  console.log("[Test 7] Testing WebSocket connection...");
  const wsResult = await page.evaluate(async () => {
    return new Promise((resolve) => {
      const timeout = setTimeout(() => resolve({ connected: false, error: "timeout" }), 5000);
      try {
        const ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close();
          resolve({ connected: true });
        };
        ws.onerror = (e) => {
          clearTimeout(timeout);
          resolve({ connected: false, error: "connection error" });
        };
      } catch (err) {
        clearTimeout(timeout);
        resolve({ connected: false, error: err.message });
      }
    });
  });
  results.push({
    test: "WebSocket connection",
    pass: wsResult.connected,
    detail: wsResult.connected ? "Connected" : wsResult.error,
  });
  console.log(`  WebSocket: ${wsResult.connected ? "CONNECTED" : "FAILED"} — ${JSON.stringify(wsResult)}`);

  // ── Test 8: Navigate tabs ────────────────────────────────
  console.log("[Test 8] Checking tab navigation...");
  const tabNames = await page.evaluate(() => {
    const tabs = document.querySelectorAll("nav a, .tab, [role='tab'], .nav-link, button.tab-btn");
    return Array.from(tabs).map((t) => t.textContent.trim()).filter(Boolean);
  });
  results.push({
    test: "Tab names found",
    pass: tabNames.length > 0,
    detail: tabNames.length > 0 ? tabNames.join(", ") : "No tabs",
  });
  console.log(`  Tabs: ${tabNames.length > 0 ? tabNames.join(", ") : "NONE FOUND"}`);

  // Click through each tab and take screenshots
  if (tabNames.length > 0) {
    const tabEls = await page.$$("nav a, .tab, [role='tab'], .nav-link, button.tab-btn");
    for (let i = 0; i < Math.min(tabEls.length, 6); i++) {
      try {
        const tabText = await tabEls[i].evaluate((el) => el.textContent.trim());
        if (!tabText) continue;
        await tabEls[i].click();
        await new Promise((r) => setTimeout(r, 500));
        const safeName = tabText.replace(/[^a-zA-Z0-9]/g, "_").toLowerCase();
        await page.screenshot({ path: `${SCREENSHOT_DIR}/tab_${safeName}.png`, fullPage: true });
        console.log(`  Clicked tab "${tabText}" — screenshot saved`);
      } catch (err) {
        console.log(`  Tab ${i} click failed: ${err.message}`);
      }
    }
  }

  // ── Test 9: Console errors ───────────────────────────────
  console.log("[Test 9] Checking for JS console errors...");
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  // Reload to capture fresh errors
  await page.reload({ waitUntil: "networkidle2", timeout: 10000 });
  await new Promise((r) => setTimeout(r, 2000));
  results.push({
    test: "No JS console errors on load",
    pass: consoleErrors.length === 0,
    detail: consoleErrors.length === 0 ? "Clean" : `${consoleErrors.length} error(s): ${consoleErrors[0]}`,
  });
  console.log(`  Console errors: ${consoleErrors.length}`);
  if (consoleErrors.length > 0) {
    consoleErrors.forEach((e) => console.log(`    - ${e}`));
  }

  // ── Summary ──────────────────────────────────────────────
  console.log("\n════════════════════════════════════════");
  console.log("  UI SMOKE TEST RESULTS");
  console.log("════════════════════════════════════════");
  let passed = 0;
  let failed = 0;
  for (const r of results) {
    const icon = r.pass ? "PASS" : "FAIL";
    console.log(`  [${icon}] ${r.test}: ${r.detail}`);
    if (r.pass) passed++;
    else failed++;
  }
  console.log(`\n  Total: ${passed} passed, ${failed} failed out of ${results.length}`);
  console.log("════════════════════════════════════════\n");

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(2);
});
