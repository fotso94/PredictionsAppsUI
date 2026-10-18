import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { QA_EXPERT, ensureQaExpertToken } from '../support/qa-account';
import { ISOLATED_API as API, isolatedApiContext as apiContext } from '../support/isolated';

/**
 * The browser-level journey on the isolated pair, in two halves, each through the real pages
 * against the clone of the live database behind the isolated backend (:8001, scheduler off,
 * no provider credentials).
 *
 *  1. A suggested combination becomes a recorded slip THROUGH THE PAGE: the suggestions page,
 *     its first combination, the slip dock, save, record, and the slip history showing the new
 *     slip as recorded and pending.
 *  2. A slip that has results SHOWS THEM on the slip history, and viewing it again - a reload,
 *     then leaving and coming back - changes nothing: the card reads the same, and the API's
 *     answer for every slip is byte-identical before and after the views.
 *
 * Two slips, not one, by design: the clone receives no results (its providers are blank), so a
 * slip recorded here can only ever be pending here, and the one whose results are displayed is
 * the suggestion-born slip settled on the live database on 2026-10-17, which the clone carries.
 * Every screenshot and page text goes to E2E_EVIDENCE_DIR when it is set, so a run can be kept.
 */

const EVIDENCE = process.env.E2E_EVIDENCE_DIR;

function keep(name: string, text: string): void {
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  writeFileSync(join(EVIDENCE, name), text);
}

async function shot(page: Page, name: string): Promise<void> {
  if (!EVIDENCE) return;
  mkdirSync(EVIDENCE, { recursive: true });
  await page.screenshot({ path: join(EVIDENCE, name), fullPage: true, type: 'jpeg', quality: 70 });
}

function auth(bearer: string) {
  return { headers: { Authorization: `Bearer ${bearer}` } };
}

async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

interface SlipLeg { state: string; snapshot_id?: string | null; settlement?: { actual?: unknown } | null }
interface Slip { id: string; name: string | null; status: string; state: string; settled_at: string | null; legs: SlipLeg[] }

async function slips(api: APIRequestContext, bearer: string): Promise<Slip[]> {
  const body = await (await api.get('/api/v1/me/slips', auth(bearer))).json();
  return body.slips as Slip[];
}

test.describe.configure({ mode: 'serial' });

test('a suggested combination becomes a recorded slip through the page', async ({ page }) => {
  const api = await apiContext();
  const bearer = await ensureQaExpertToken(api);
  const probe = await (await api.get('/api/v1/suggestions?legs=2&min_probability=0.5')).json();
  test.skip((probe.combinations ?? []).length === 0, `no qualifying combination at ${API}: ${probe.shortfall}`);

  await signInThroughTheForm(page);
  await page.goto('/selections/suggestions');
  await expect(page.getByTestId('suggest-results')).toBeVisible();
  const first = page.getByTestId('suggested-combination').first();
  await expect(first).toBeVisible();
  const legsShown = await first.getByTestId('suggested-leg').count();
  expect(legsShown, 'the first combination has legs').toBeGreaterThan(0);
  keep('01-first-suggested-combination.txt', await first.innerText());
  await shot(page, '01-suggestions-page.jpg');

  await first.getByTestId('suggested-add-all').click();
  await expect(page.getByTestId('slip-dock-count')).toHaveText(String(legsShown));
  await page.getByTestId('slip-dock-toggle').click();
  const dock = page.getByTestId('slip-dock');
  await expect(dock.getByTestId('slip-leg')).toHaveCount(legsShown);
  const name = `Browser journey ${new Date().toISOString().slice(0, 16)}`;
  await dock.getByTestId('slip-name').fill(name);
  await dock.getByTestId('slip-save').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(name);
  await shot(page, '02-slip-saved-in-the-dock.jpg');

  await dock.getByTestId('slip-record-open').click();
  await dock.getByTestId('slip-record-reference').fill('browser journey on the isolated pair');
  await dock.getByTestId('slip-record-confirm').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(/recorded|Marqué/i);
  await shot(page, '03-slip-recorded-in-the-dock.jpg');

  await page.goto('/selections');
  const card = page.locator('[data-testid="history-slip"]').filter({ hasText: name });
  await expect(card).toHaveCount(1);
  await expect(card).toHaveAttribute('data-status', 'recorded');
  await expect(card).toHaveAttribute('data-state', 'pending');
  await expect(card.getByTestId('history-leg')).toHaveCount(legsShown);
  keep('04-history-new-slip.txt', await card.innerText());
  await shot(page, '04-history-with-the-new-slip.jpg');

  const recorded = (await slips(api, bearer)).find(s => s.name === name);
  expect(recorded, 'the recorded slip is on the server').toBeTruthy();
  expect(recorded!.status).toBe('recorded');
  expect(recorded!.state).toBe('pending');
  expect(recorded!.legs).toHaveLength(legsShown);
  for (const leg of recorded!.legs) {
    expect(leg.state).toBe('pending');
    expect(leg.snapshot_id, 'every leg is attributed to a forecast snapshot').toBeTruthy();
  }
  keep('04-recorded-slip-from-the-api.json', JSON.stringify(recorded, null, 2));
});

test('a settled slip shows its results, and viewing it again changes nothing', async ({ page }) => {
  const api = await apiContext();
  const bearer = await ensureQaExpertToken(api);
  const before = await slips(api, bearer);
  const settled = before.filter(s => s.state === 'won' || s.state === 'lost');
  test.skip(settled.length === 0, `the clone at ${API} holds no settled slip to display`);
  // The suggestion-born slip settled on the live database on 2026-10-17 when the clone carries it;
  // otherwise the most recently settled one.
  const target = settled.find(s => String(s.id).startsWith('a0dce8dd')) ?? settled.sort((a, b) => String(b.settled_at).localeCompare(String(a.settled_at)))[0];
  keep('05-all-slips-before-viewing.json', JSON.stringify(before, null, 2));

  await signInThroughTheForm(page);
  await page.goto('/selections');
  const card = page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) });
  await expect(card).toHaveCount(1);
  await expect(card).toHaveAttribute('data-status', 'recorded');
  await expect(card).toHaveAttribute('data-state', String(target.state));
  const legs = card.getByTestId('history-leg');
  await expect(legs).toHaveCount(target.legs.length);
  for (let i = 0; i < target.legs.length; i += 1) {
    const leg = target.legs[i];
    await expect(legs.nth(i)).toHaveAttribute('data-state', String(leg.state));
    const actual = leg.settlement?.actual;
    if (typeof actual === 'string') await expect(legs.nth(i)).toContainText(actual);
  }
  const firstView = await card.innerText();
  keep('05-history-settled-slip.txt', firstView);
  await shot(page, '05-history-settled-slip.jpg');

  await page.reload();
  const afterReload = await page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) }).innerText();
  expect(afterReload, 'a reload shows the same card').toBe(firstView);
  await shot(page, '06-history-settled-slip-after-reload.jpg');

  await page.goto('/');
  await page.goto('/selections');
  const afterReturn = await page.locator('[data-testid="history-slip"]').filter({ hasText: String(target.name) }).innerText();
  expect(afterReturn, 'leaving and coming back shows the same card').toBe(firstView);

  const after = await slips(api, bearer);
  keep('06-all-slips-after-viewing.json', JSON.stringify(after, null, 2));
  expect(after, 'every slip the API serves is identical before and after the views').toEqual(before);
});
