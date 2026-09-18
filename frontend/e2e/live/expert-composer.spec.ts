import { test, expect } from '@playwright/test';
import { apiContext, ensureQaExpertToken, cleanupQaPredictions, QA_EXPERT, QA_REASONING_MARKER } from '../support/qa-account';

/**
 * The composer, driven the way an expert actually drives it.
 *
 * Three defects this pins, all of them observed in the shipped form before this change:
 *  - the first field was a raw match UUID
 *  - probabilities were entered as 0-1 decimals, so "55%" had to be typed as 0.55
 *  - the form arrived prefilled with home 0.33 / draw 0.33 / away 0.34 and confidence 0.75
 * The third is not theoretical. A prediction was published to this database carrying exactly those
 * four numbers and the reasoning "nothing to say but bayern will win for sure": the defaults were
 * never touched, because a form that arrives holding an opinion gets submitted holding it.
 */

let api: Awaited<ReturnType<typeof apiContext>>;
let token: string;

test.beforeAll(async () => {
  api = await apiContext();
  token = await ensureQaExpertToken(api);
});

test.beforeEach(async () => {
  await cleanupQaPredictions(api, token);
});

test.afterAll(async () => {
  if (api && token) await cleanupQaPredictions(api, token);
  await api?.dispose();
});

/**
 * Open the composer on a day that still has a fixture to write about.
 *
 * You cannot write a prediction for a match that has already kicked off, so "today" stops offering
 * fixtures once the evening's games start — which is exactly what happened the first time this ran
 * after 20:00 UTC. Walk forward until a day has one.
 */
async function openComposerOnADayWithFixtures(page: import('@playwright/test').Page) {
  await page.goto('/expert/predictions/create');
  await page.waitForLoadState('networkidle');

  const action = page.getByRole('button', { name: /^write a prediction:/i });
  for (const label of [/^today$/i, /^tomorrow$/i, /in two days/i]) {
    const chip = page.getByRole('button', { name: label }).first();
    if (await chip.count() === 0) continue;
    await chip.click();
    await page.waitForTimeout(500);
    if (await action.count() > 0) {
      await action.first().click();
      await page.waitForLoadState('networkidle');
      return true;
    }
  }
  return false;
}

async function signInThroughTheUi(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /sign in|log in/i }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
}

test('an expert reaches the form without ever seeing a match id', async ({ page }) => {
  await signInThroughTheUi(page);
  await page.goto('/expert/predictions/create');
  await page.waitForLoadState('networkidle');

  // the fixture picker is the first thing, and it shows football, not identifiers
  await expect(page.getByText(/choose a fixture/i)).toBeVisible();
  const visible = await page.locator('body').innerText();
  expect(visible).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);

  // pasting an id is still possible, but it is not the way in
  await expect(page.getByText(/advanced: paste a match id/i)).toBeVisible();
});

test('the form suggests no probability of its own', async ({ page }) => {
  await signInThroughTheUi(page);
  const opened = await openComposerOnADayWithFixtures(page);
  test.skip(!opened, 'no upcoming fixture in the next three days to write about');

  const numbers = page.locator('input[inputmode="decimal"]');
  const count = await numbers.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i += 1) {
    const value = await numbers.nth(i).inputValue();
    expect(value, 'no probability or confidence may be prefilled').toBe('');
  }
  // and none of the old anchoring defaults survives anywhere on the page
  const text = await page.locator('body').innerText();
  expect(text).not.toContain('0.33');
  expect(text).not.toContain('0.34');
});

test('a percentage typed as 55 is stored as 0.55 and published immediately', async ({ page }) => {
  await signInThroughTheUi(page);
  const opened = await openComposerOnADayWithFixtures(page);
  test.skip(!opened, 'no upcoming fixture in the next three days to write about');

  const numbers = page.locator('input[inputmode="decimal"]');
  await numbers.nth(0).fill('55');
  await numbers.nth(1).fill('25');
  await numbers.nth(2).fill('20');

  const reasoning = page.locator('textarea').first();
  await reasoning.fill(`${QA_REASONING_MARKER} the home side keeps more of the ball in this fixture`);

  await page.getByRole('button', { name: /publish/i }).first().click();
  await page.waitForLoadState('networkidle');

  // the API is the source of truth: 55 must have become 0.55, not 55 and not 0.0055
  const mine = await api.get('/api/v1/expert/predictions/my-predictions?limit=5', {
    headers: { Authorization: `Bearer ${token}` },
  });
  const rows = await mine.json();
  const published = (Array.isArray(rows) ? rows : rows.predictions || [])
    .find((r: { reasoning?: string }) => (r.reasoning || '').includes(QA_REASONING_MARKER));

  expect(published, 'the prediction reached the backend').toBeTruthy();
  expect(Number(published.home_win_prob)).toBeCloseTo(0.55, 4);
  expect(Number(published.draw_prob)).toBeCloseTo(0.25, 4);
  expect(Number(published.away_win_prob)).toBeCloseTo(0.2, 4);
  // publication is direct: no pending state, no approval queue
  expect(String(published.status).toLowerCase()).toBe('published');
  // a market the expert did not fill in stays unavailable rather than becoming zero
  expect(published.btts_yes_prob ?? null).toBeNull();
});
