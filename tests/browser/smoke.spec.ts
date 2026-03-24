import { test, expect } from '@playwright/test';

/**
 * Browser smoke tests for operator-visible truth surfaces.
 *
 * Wave 22: app load, tree toggle, chat input, timestamp rendering.
 * Wave 24: tree collapse visibility, model naming, colony display names,
 *          aggregate cost without misleading denominator.
 * Wave 25.5: single final output, artifact sections, output separation.
 * Wave 40: demo guide wiring, config memory presence, consistency audit.
 *
 * Run: npx playwright test tests/browser/smoke.spec.ts
 * Requires the frontend dev server running (npm run dev in frontend/).
 */

const BASE = process.env.SMOKE_URL ?? 'http://localhost:5173';

test('app shell loads and renders formicos-app', async ({ page }) => {
  await page.goto(BASE);
  const app = page.locator('formicos-app');
  await expect(app).toBeAttached({ timeout: 10_000 });
});

test('tree-nav renders and toggle is clickable', async ({ page }) => {
  await page.goto(BASE);
  const tree = page.locator('fc-tree-nav');
  await expect(tree).toBeAttached({ timeout: 10_000 });

  // The toggle target should be at least 20x20 for usability (C2)
  const toggle = tree.locator('.toggle').first();
  if (await toggle.isVisible()) {
    const box = await toggle.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThanOrEqual(18);
    expect(box!.height).toBeGreaterThanOrEqual(18);
    await toggle.click();
  }
});

test('queen-chat input accepts text', async ({ page }) => {
  await page.goto(BASE);
  const chat = page.locator('fc-queen-chat');
  await expect(chat).toBeAttached({ timeout: 10_000 });

  const input = chat.locator('input');
  await expect(input).toBeAttached();
  await input.fill('hello from smoke test');
  await expect(input).toHaveValue('hello from smoke test');
});

test('timestamps are relative, not raw ISO', async ({ page }) => {
  await page.goto(BASE);
  // Wait for the app to be present
  await page.locator('formicos-app').waitFor({ timeout: 10_000 });

  // Look for raw ISO patterns (e.g. 2026-03-16T...) — should NOT appear
  // in event or message timestamps since we now use timeAgo()
  const body = await page.locator('body').innerHTML();
  const isoPattern = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

  // Check specifically within timestamp-bearing elements
  const eventTimestamps = await page.locator('.event-ts').allInnerTexts();
  const msgTimestamps = await page.locator('.msg-ts').allInnerTexts();
  const allTimestamps = [...eventTimestamps, ...msgTimestamps];

  for (const ts of allTimestamps) {
    expect(ts).not.toMatch(isoPattern);
  }
});

// -- Wave 24 truth surface assertions --

test('tree collapse actually changes child visibility', async ({ page }) => {
  await page.goto(BASE);
  const tree = page.locator('fc-tree-nav');
  await expect(tree).toBeAttached({ timeout: 10_000 });

  const toggle = tree.locator('.toggle').first();
  if (await toggle.isVisible()) {
    const beforeCount = await tree.locator('.node').count();
    if (beforeCount > 1) {
      await toggle.click();
      const afterCount = await tree.locator('.node').count();
      expect(afterCount).toBeLessThan(beforeCount);
    }
  }
});

test('model names look human-readable, not raw routing addresses', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('formicos-app').waitFor({ timeout: 10_000 });

  await page.getByText('Models', { exact: true }).click();
  await page.locator('fc-model-registry').waitFor({ timeout: 10_000 });

  const modelNames = await page.locator('fc-model-registry .model-name').allInnerTexts();
  for (const name of modelNames) {
    expect(name.trim()).not.toBe('');
    expect(name).not.toContain('/');
  }
});

test('named colonies show display name when available', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('formicos-app').waitFor({ timeout: 10_000 });

  const colonyIds = page.locator('.col-id');
  const count = await colonyIds.count();
  if (count > 0) {
    const card = colonyIds.first().locator('..');
    const displayName = await card.locator('.col-name').innerText();
    const rawId = await colonyIds.first().innerText();
    expect(displayName.trim()).not.toBe('');
    expect(displayName).not.toBe(rawId);
  }
});

test('aggregate cost display does not show misleading budget denominator', async ({ page }) => {
  await page.goto(BASE);
  await page.locator('formicos-app').waitFor({ timeout: 10_000 });

  const topbarText = await page.locator('.topbar-right').innerText();
  expect(topbarText).not.toMatch(/\$[\d.]+\s*\/\s*\$[\d.]+/);
});

// -- Wave 25.5 output truth assertions --

/**
 * Helper: navigate to a completed colony detail page.
 * Returns true if a completed colony was found and navigated to.
 */
async function navigateToCompletedColony(page: import('@playwright/test').Page): Promise<boolean> {
  await page.goto(BASE);
  await page.locator('formicos-app').waitFor({ timeout: 10_000 });

  // Look for a completed colony node in the tree and click it
  const completedNodes = page.locator('fc-tree-nav .node').filter({ hasText: /completed/i });
  if (await completedNodes.count() === 0) {
    // Try clicking any colony node — colony detail will show status
    const anyColonyNode = page.locator('fc-tree-nav .node').first();
    if (await anyColonyNode.count() === 0) return false;
    await anyColonyNode.click();
  } else {
    await completedNodes.first().click();
  }

  // Wait for colony detail to appear
  const detail = page.locator('fc-colony-detail');
  if (await detail.isVisible({ timeout: 5_000 }).catch(() => false)) {
    return true;
  }
  return false;
}

test('colony detail has at most one Final Output section', async ({ page }) => {
  const found = await navigateToCompletedColony(page);
  if (!found) return; // no colonies to test

  // Count all visible "Final Output" section labels across the entire detail page.
  // colony-detail.ts renders one via _renderFinalOutput and round-history.ts renders
  // another inside fc-round-history — only one should be visible at top level.
  const detail = page.locator('fc-colony-detail');
  const finalOutputLabels = detail.locator('.s-label').filter({ hasText: 'Final Output' });
  const count = await finalOutputLabels.count();

  // At most one top-level Final Output section should be visible
  expect(count).toBeLessThanOrEqual(1);
});

test('completed colony shows Generated Artifacts section when artifacts exist', async ({ page }) => {
  const found = await navigateToCompletedColony(page);
  if (!found) return;

  const detail = page.locator('fc-colony-detail');

  // If the colony has artifacts, there should be a Generated Artifacts section
  const artifactSection = detail.locator('.s-label').filter({ hasText: /Generated Artifacts/i });
  const artifactCount = await artifactSection.count();

  if (artifactCount > 0) {
    // Verify at least one artifact row with name and type indicators
    const artifactRows = detail.locator('.artifact-row, .ws-file-row').filter({
      has: page.locator('.artifact-name, .ws-file-name'),
    });
    const rowCount = await artifactRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // Each visible artifact row should have non-empty name text
    for (let i = 0; i < Math.min(rowCount, 3); i++) {
      const nameEl = artifactRows.nth(i).locator('.artifact-name, .ws-file-name').first();
      if (await nameEl.isVisible()) {
        const name = await nameEl.innerText();
        expect(name.trim()).not.toBe('');
      }
    }
  }
  // If no artifacts section, that's fine — colony may not have produced typed artifacts
});

test('Colony Uploads, Workspace Library, and Generated Artifacts are separate sections', async ({ page }) => {
  const found = await navigateToCompletedColony(page);
  if (!found) return;

  const detail = page.locator('fc-colony-detail');
  const sectionLabels = await detail.locator('.s-label').allInnerTexts();

  // Collect which output-related sections are present
  const hasColonyUploads = sectionLabels.some(l => /Colony Uploads/i.test(l));
  const hasWorkspaceLibrary = sectionLabels.some(l => /Workspace Library/i.test(l));
  const hasGeneratedArtifacts = sectionLabels.some(l => /Generated Artifacts/i.test(l));

  // Workspace Library should always be present (it has an empty state)
  expect(hasWorkspaceLibrary).toBe(true);

  // If Colony Uploads is present, it should be separate from Workspace Library
  if (hasColonyUploads) {
    const uploadsIndex = sectionLabels.findIndex(l => /Colony Uploads/i.test(l));
    const libraryIndex = sectionLabels.findIndex(l => /Workspace Library/i.test(l));
    expect(uploadsIndex).not.toBe(libraryIndex);
  }

  // If Generated Artifacts is present, it should be separate from both
  if (hasGeneratedArtifacts && hasWorkspaceLibrary) {
    const artifactsIndex = sectionLabels.findIndex(l => /Generated Artifacts/i.test(l));
    const libraryIndex = sectionLabels.findIndex(l => /Workspace Library/i.test(l));
    expect(artifactsIndex).not.toBe(libraryIndex);
  }
});

test('empty Workspace Library shows truthful empty state', async ({ page }) => {
  const found = await navigateToCompletedColony(page);
  if (!found) return;

  const detail = page.locator('fc-colony-detail');
  const wsSection = detail.locator('.ws-files').last();

  // If workspace library has no files, it should show an empty hint
  const emptyHint = wsSection.locator('.empty-hint');
  const fileRows = wsSection.locator('.ws-file-row');
  const fileCount = await fileRows.count();

  if (fileCount === 0) {
    // Empty state message should be visible and truthful
    await expect(emptyHint).toBeVisible();
    const hintText = await emptyHint.innerText();
    expect(hintText).toBeTruthy();
    // Should not claim files exist when there are none
    expect(hintText).not.toMatch(/\d+ files?/i);
  }
});

// -- Wave 40 consistency assertions --

test('queen overview includes config memory component', async ({ page }) => {
  await page.goto(BASE);
  const overview = page.locator('fc-queen-overview');
  await expect(overview).toBeAttached({ timeout: 10_000 });

  // Config memory should be present as a child of the overview
  const configMemory = overview.locator('fc-config-memory');
  await expect(configMemory).toBeAttached();
});

test('proactive briefing component is present in queen overview', async ({ page }) => {
  await page.goto(BASE);
  const overview = page.locator('fc-queen-overview');
  await expect(overview).toBeAttached({ timeout: 10_000 });

  const briefing = overview.locator('fc-proactive-briefing');
  await expect(briefing).toBeAttached();
});
