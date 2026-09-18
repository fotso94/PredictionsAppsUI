import { test, expect } from '@playwright/test';
import {
  stubBackend, dayPayload, emptyDayPayload, quotaExhaustedStatus,
  expiredTrialStatus, localDay,
} from '../support/api-stub';

/**
 * What the site says when the data behind it is degraded.
 *
 * The distinction that matters: a spent daily allowance means refreshes are PAUSED and the
 * forecasts already on screen are still real. That must never read the same as "unavailable",
 * and a stale forecast must never be presented as current.
 */

test('an exhausted daily allowance reads as paused, not unavailable', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), status: quotaExhaustedStatus() });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).toMatch(/paused|allowance|until tomorrow/);
  // the forecasts already fetched must still be on the page
  expect(text).not.toMatch(/forecasts are unavailable/);
});

test('an expired or rejected trial is surfaced to the reader', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d), status: expiredTrialStatus() });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const banner = page.getByTestId('provider-status-banner');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(/paused|failed|not configured/i);
});

test('a day with no fixtures shows an empty state, not an error', async ({ page }) => {
  await stubBackend(page, { day: d => emptyDayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).toMatch(/no matches/);
  expect(text).not.toMatch(/something went wrong|failed to load/);
});

test('a backend failure shows an error state, not an empty day', async ({ page }) => {
  await stubBackend(page, { fail: url => (url.includes('/matches') ? 503 : null) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');

  const text = (await page.locator('body').innerText()).toLowerCase();
  // the backend's own message reaches the reader, with a way to try again
  expect(text).toContain('simulated backend failure');
  expect(text).toContain('retry');
  // and the page does not claim the day is empty: we do not know what is on today
  expect(text).not.toMatch(/no matches (are )?(scheduled|found) for today/);
});

test('the status banner stays away when every provider is healthy', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/predictions/today');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('provider-status-banner')).toHaveCount(0);
});

test('a loading state appears before the data arrives', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  // A regex, not a glob: in Playwright's glob syntax '?' is a single-character wildcard, so
  // '**/matches?**' would never match the query string. Registered last so that it wins.
  await page.route(/\/api\/v1\/matches\?/, async route => {
    await new Promise(resolve => setTimeout(resolve, 2000));
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(dayPayload(localDay())),
    });
  });

  await page.goto('/predictions/today', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toContainText(/loading/i, { timeout: 5000 });
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).not.toContainText(/loading/i);
});
