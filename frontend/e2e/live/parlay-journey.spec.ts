import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { API, QA_EXPERT, apiContext, ensureQaExpertToken } from '../support/qa-account';

/**
 * LIVE: one real journey from an available fixture to a saved, recorded combination, on the local
 * backend and its stored data. Nothing here asks a provider for anything, and the spend counters
 * are read before and after to prove it.
 *
 * Runs against whatever E2E_BASE_URL / E2E_API_URL point at. During the parlay build it was run
 * against the isolated pair (frontend 3101 → backend 8001 on the `soccer_predictions_dev` clone,
 * scheduler off, no provider credentials), never against the backend under observation on 8000.
 *
 * What it needs from the database: at least one scheduled fixture with a stored GameForecast
 * forecast in the next seven days. It skips, saying so, when there is none.
 */

interface Fixture { id: string; home: { name: string }; away: { name: string }; kickoff_utc: string; forecast_state: string; status: string }

const auth = (bearer: string) => ({ headers: { Authorization: `Bearer ${bearer}` } });

async function upcomingWithForecast(api: APIRequestContext): Promise<Fixture[]> {
  const found: Fixture[] = [];
  for (let offset = 0; offset < 7; offset += 1) {
    const day = new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
    const response = await api.get(`/api/v1/matches?date=${day}&refresh=false`);
    if (!response.ok()) continue;
    const matches = ((await response.json()).matches || []) as Fixture[];
    for (const match of matches) {
      if (match.forecast_state === 'available' && match.status === 'scheduled' && Date.parse(match.kickoff_utc) > Date.now() + 60 * 60 * 1000) found.push(match);
    }
    if (found.length >= 2) break;
  }
  return found;
}

async function spend(api: APIRequestContext): Promise<Record<string, number>> {
  const status = await (await api.get('/api/v1/data-providers/status')).json();
  const out: Record<string, number> = {};
  for (const provider of status.chain ?? []) out[provider.name] = provider.budget?.used_today ?? 0;
  out.forecasts = status.forecasts?.budget?.used_today ?? 0;
  return out;
}

async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

test('a real fixture → a selection → a saved, recorded combination, with no provider request', async ({ page }) => {
  const api = await apiContext();
  const bearer = await ensureQaExpertToken(api);
  const fixtures = await upcomingWithForecast(api);
  test.skip(fixtures.length < 2, `needs two upcoming fixtures with a stored forecast at ${API}; found ${fixtures.length}`);
  const [first, second] = fixtures;

  // Start clean: drop this account's drafts and saved slips (recorded ones are immutable and stay).
  const existing = await (await api.get('/api/v1/me/slips', auth(bearer))).json();
  for (const slip of existing.slips ?? []) {
    if (slip.status !== 'recorded') await api.delete(`/api/v1/me/slips/${slip.id}`, auth(bearer));
  }
  const before = await spend(api);

  // The markets endpoint serves the stored forecast's selections for the fixture.
  const envelope = await (await api.get(`/api/v1/matches/${first.id}/markets`)).json();
  expect(envelope.provider, 'the fixture has a stored forecast').toBe('gameforecast');
  expect(envelope.forecast.snapshot_id, 'the selection can be attributed to a snapshot').toBeTruthy();

  await signInThroughTheForm(page);
  await page.goto(`/match/${first.id}`);
  const panel = page.getByTestId('markets-panel');
  await expect(panel).toBeVisible();
  const homeRow = page.locator('[data-testid="market-selection"][data-selection-id="match_result:home"]');
  const shown = await homeRow.getByTestId('selection-probability').innerText();
  await homeRow.getByTestId('selection-add').click();
  await expect(page.getByTestId('slip-dock-count')).toHaveText('1');

  await page.goto(`/match/${second.id}`);
  await page.locator('[data-testid="market-selection"][data-selection-id="total_goals:over@0.5"], [data-testid="market-selection"][data-selection-id="total_goals:under@2.5"]').first().getByTestId('selection-add').click();
  await expect(page.getByTestId('slip-dock-count')).toHaveText('2');

  await page.getByTestId('slip-dock-toggle').click();
  const dock = page.getByTestId('slip-dock');
  await expect(dock.getByTestId('slip-leg')).toHaveCount(2);
  const name = `Journey ${new Date().toISOString().slice(0, 16)}`;
  await dock.getByTestId('slip-name').fill(name);
  await dock.getByTestId('slip-save').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(name);

  // The server holds it, with the probability that was on the page and the snapshot behind it.
  const saved = (await (await api.get('/api/v1/me/slips?status=saved', auth(bearer))).json()).slips.find((s: { name: string }) => s.name === name);
  expect(saved, 'the saved slip is on the server').toBeTruthy();
  expect(saved.legs).toHaveLength(2);
  const homeLeg = saved.legs.find((l: { match: { id: string } }) => l.match.id === first.id);
  expect(homeLeg.selection.selection_id).toBe('match_result:home');
  expect(homeLeg.snapshot_id).toBe(envelope.forecast.snapshot_id);
  expect(Math.round(homeLeg.probability * 100)).toBe(parseInt(shown, 10));

  // Record it as placed elsewhere; from then on it is immutable and reads as such.
  await dock.getByTestId('slip-record-open').click();
  await dock.getByTestId('slip-record-reference').fill('live journey');
  await dock.getByTestId('slip-record-confirm').click();
  await expect(dock.getByTestId('slip-dock-notice')).toContainText(/recorded|Marqué/i);
  await page.goto('/selections');
  const recorded = page.locator('[data-testid="history-slip"][data-status="recorded"]').filter({ hasText: name });
  await expect(recorded).toHaveCount(1);
  await expect(recorded).toContainText('live journey');
  const refused = await api.post(`/api/v1/me/slips/${saved.id}/legs`, { ...auth(bearer), data: { match_id: first.id, selection_id: 'match_result:away' } });
  expect(refused.status()).toBe(409);

  // None of it spent a provider request.
  expect(await spend(api)).toEqual(before);
  await api.dispose();
});

test('suggestions come from stored forecasts and add to the slip without a provider request', async ({ page }) => {
  const api = await apiContext();
  const before = await spend(api);
  const suggestions = await (await api.get('/api/v1/suggestions?legs=2&min_probability=0.5')).json();
  test.skip(suggestions.combinations.length === 0, `no qualifying combination at ${API}: ${suggestions.shortfall}`);

  await page.goto('/selections/suggestions');
  await expect(page.getByTestId('suggest-results')).toBeVisible();
  await expect(page.getByTestId('suggested-combination').first()).toBeVisible();
  // The page generates with its own defaults (3 legs), so the count to expect is the page's, not the API probe's.
  const first = page.getByTestId('suggested-combination').first();
  const legsShown = await first.getByTestId('suggested-leg').count();
  await first.getByTestId('suggested-add-all').click();
  await expect(page.getByTestId('slip-dock-count')).toHaveText(String(legsShown));
  expect(await page.locator('main').innerText()).not.toMatch(/\bsafe\b|guaranteed|sure win/i);
  expect(await spend(api)).toEqual(before);
  await api.dispose();
});
