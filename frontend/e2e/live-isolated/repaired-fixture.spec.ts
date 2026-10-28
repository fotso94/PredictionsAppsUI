import { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { isolatedApiContext as apiContext } from '../support/isolated';
import { QA_EXPERT } from '../support/qa-account';

/**
 * The repaired Paris Saint-Germain v Lyon fixture, as a reader sees it.
 *
 * WHAT IS BEHIND THIS SPEC. Live Score listed the match as fixture 1877019 for 2026-10-25 19:45 UTC
 * and again as 742799 for 2026-10-26 19:30 UTC; the sync stored two rows (docs/evidence/
 * fixture-identity-cadence-2026-10-27). This spec runs against a DISPOSABLE pair - a backend on a
 * copy of the live database to which `scripts/repair_duplicate_matches.py --fold-superseded` was
 * applied, and a frontend calling it - selected with E2E_ISOLATED_SIDE=disposable (the policy's
 * `browser.disposable` side; backend/app/core/isolation_targets.json). It never touches the live
 * pair, the shared isolated pair on :8001/:3101, or a data provider: the backend has no provider
 * credential and its scheduler is off.
 *
 * WHAT IT PROVES, AND NO MORE. That the one surviving row shows the kickoff the match was played
 * at, the stored result and the forecast that moved onto it; that the day lists carry one card
 * for it and none for the folded listing; that a reader's saved match, an expert's published
 * prediction and a slip leg that reference the row still resolve and show the states the stored
 * rows hold; and that reloads and the phone layout change none of it. One thing to read with
 * care: the slip leg was seeded PENDING, and the slips endpoint settles every slip it returns
 * against the stored results (`GET /api/v1/me/slips`, its standing rule) - so the first read of the
 * slip settles the leg "won" against the 2-0 the row now holds, and the page shows what the row
 * then says. Nothing here changed a flag or a timestamp to produce that; it is the consequence the
 * repair script prints for a person: a leg placed on the 25 October listing's forecast is scored
 * against the match played on the 26th. The reader's rows are REPRESENTATIVE LOCAL DATA written into the
 * copy for this spec (a saved match, a published expert prediction dated before the original
 * kickoff, a saved slip with one leg on the 25 October snapshot). Nothing here scores anything:
 * the snapshot retrieved on the 26th keeps `captured_before_kickoff = false` as stored, and the
 * forecast is shown "for reference" because the match has been played.
 */
const PLAYED = '93bc3d08-e713-4336-9747-e5e9eb5e00a1';
const FOLDED = '1adf0e7d-e682-42e2-bbb2-e5a5ad365752';
const KICKOFF_UTC = '2026-10-26T19:30:00Z';
const HOME = 'Paris Saint Germain';
const AWAY = 'Lyon';

interface Failures { console: string[]; requests: string[]; responses: string[] }

/** Record what a reader's browser should never see: errors in the console, failed or 5xx requests. */
function watch(page: Page): Failures {
  const seen: Failures = { console: [], requests: [], responses: [] };
  page.on('console', (message) => { if (message.type() === 'error') seen.console.push(message.text()); });
  page.on('requestfailed', (request) => seen.requests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`));
  page.on('response', (response) => {
    const url = response.url();
    const api = url.includes('/api/');
    const deliberate = url.includes(FOLDED);                // the folded id is asked for on purpose below
    const signedOut = response.status() === 401 && /\/auth\/|\/me\//.test(url);
    if (response.status() >= 500 || (api && response.status() >= 400 && !deliberate && !signedOut)) {
      seen.responses.push(`${response.status()} ${url}`);
    }
  });
  return seen;
}

function clean(seen: Failures): void {
  expect(seen.console, 'console errors').toEqual([]);
  expect(seen.requests, 'failed requests').toEqual([]);
  expect(seen.responses, 'failing API answers').toEqual([]);
}

async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

/** The local calendar day of a kick-off in the project's emulated timezone (the list is per viewer day). */
function localDay(iso: string): string {
  const timeZone = test.info().project.use.timezoneId ?? 'UTC';
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso));
}

async function detail(api: APIRequestContext) {
  const response = await api.get(`/api/v1/matches/${PLAYED}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function expectThePlayedRow(page: Page): Promise<void> {
  await page.goto(`/match/${PLAYED}`);
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
  await expect(page.getByTestId('match-scoreline')).toContainText('2');
  await expect(page.getByTestId('match-scoreline')).toContainText('0');
  await expect(page.getByText(HOME).first()).toBeVisible();
  await expect(page.getByText(AWAY).first()).toBeVisible();
  // Where the fixture came from: the kickoff it was played at and the provider id the provider now uses.
  const provenance = page.getByTestId('match-provenance');
  await provenance.locator('summary').first().click();          // a native <details>
  await expect(provenance).toContainText('2026-10-26 19:30:00');
  await expect(provenance).toContainText('742799');
  // The forecast that moved onto the row, shown for reference because the match has been played.
  await expect(page.getByTestId('forecast-provenance')).toBeVisible();
  await expect(page.getByText(/for reference/i).first()).toBeVisible();
}

test.describe('the repaired fixture (disposable pair over the folded copy)', () => {
  test('the API describes one row: the played kickoff, the result, both provider ids and the forecast', async () => {
    const api = await apiContext();
    const row = await detail(api);
    expect(row.kickoff_utc).toBe(KICKOFF_UTC);
    expect(row.status).toBe('finished');
    expect(row.score).toMatchObject({ home: 2, away: 0, ht_home: 0, ht_away: 0 });
    expect(row.home.name).toBe(HOME);
    expect(row.away.name).toBe(AWAY);
    expect(row.external_id).toBe('livescore:742799');
    const ids = (row.provider_refs as Array<{ provider: string; external_id: string }>).map((r) => `${r.provider}:${r.external_id}`);
    expect(ids).toEqual(expect.arrayContaining(['livescore:742799', 'livescore:1877019', 'gameforecast:28930']));
    expect(row.forecast).toMatchObject({ provider: 'gameforecast', external_event_id: '28930' });
    expect(row.forecast_state).toBe('kickoff_passed');
    expect(row.expert_prediction).toMatchObject({ status: 'published' });
    const gone = await api.get(`/api/v1/matches/${FOLDED}`);
    expect(gone.status()).toBe(404);
    await api.dispose();
  });

  test('the fixture page shows the played kickoff, the result and the attached forecast; the folded id is gone', async ({ page }) => {
    const seen = watch(page);
    await expectThePlayedRow(page);
    await page.goto(`/match/${FOLDED}`);
    await expect(page.getByTestId('match-scoreline')).toHaveCount(0);
    await expect(page.getByTestId('forecast-provenance')).toHaveCount(0);
    clean(seen);
  });

  test('the day lists carry one card for the match and none for the folded listing', async ({ page }) => {
    const seen = watch(page);
    const api = await apiContext();
    const row = await detail(api);
    await api.dispose();
    const competition = row.competition.id as string;
    await page.goto(`/matches?date=${localDay(KICKOFF_UTC)}&comp=${competition}`);
    const cards = page.getByTestId('fixture-row').filter({ hasText: HOME });
    await expect(cards).toHaveCount(1);
    await expect(cards.first().locator(`a[href*="/match/${PLAYED}"]`).first()).toBeVisible();
    await expect(cards.first().getByTestId('fixture-row-score')).toHaveText(['2', '0']);   // home 2, away 0
    await page.goto(`/matches?date=${localDay('2026-10-25T19:45:00Z')}&comp=${competition}`);
    await expect(page.getByTestId('matchday-loading')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId('fixture-row').filter({ hasText: HOME })).toHaveCount(0);
    clean(seen);
  });

  test("a reader's saved match, expert prediction and slip leg still resolve, and say what the rows say", async ({ page }) => {
    const seen = watch(page);
    await signInThroughTheForm(page);
    await page.goto('/dashboard');
    const saved = page.getByTestId('saved-matches');
    await expect(saved).toBeVisible();
    await expect(saved).toContainText(HOME);
    await expect(saved.locator(`a[href*="/match/${PLAYED}"]`).first()).toBeVisible();
    await expect(saved.getByTestId('saved-match-note-text').first()).toContainText('representative local data');

    await page.goto(`/match/${PLAYED}`);
    await expect(page.getByTestId('expert-predictions')).toBeVisible();   // the published prediction's panel
    await expect(page.getByTestId('expert-byline')).toBeVisible();
    await expect(page.getByTestId('expert-late-publication')).toHaveCount(0);   // published on the 25th, before any kickoff
    await expect(page.getByTestId('match-save-status')).toBeVisible();

    await page.goto('/selections');
    // The QA account's older slips (copied with the database) may hold other PSG fixtures: scope to this round's slip.
    const slip = page.getByTestId('history-slip').filter({ hasText: 'representative local data' });
    await expect(slip).toHaveCount(1);
    const leg = slip.getByTestId('history-leg').filter({ hasText: HOME }).filter({ hasText: AWAY });
    await expect(leg).toHaveCount(1);
    await expect(leg.first().getByTestId('history-leg-state')).not.toBeEmpty();
    // What the page shows is what the stored row says after the endpoint's own read-time settlement:
    // the leg is on the played row and carries the state the API reports for it.
    const api = await apiContext();
    const login = await api.post('/api/v1/auth/login', { data: { email: QA_EXPERT.email, password: QA_EXPERT.password } });
    const token = (await login.json()).access_token;
    const slips = await (await api.get('/api/v1/me/slips', { headers: { Authorization: `Bearer ${token}` } })).json();
    const mine = (slips.slips as Array<{ name: string; legs: Array<{ state: string; match: { id: string } }> }>)
      .find((entry) => entry.name === 'representative local data');
    expect(mine).toBeTruthy();
    expect(mine!.legs).toHaveLength(1);
    expect(mine!.legs[0].match.id).toBe(PLAYED);
    expect(['pending', 'won']).toContain(mine!.legs[0].state);          // pending as seeded; won once the endpoint settled it against the stored 2-0
    await expect(leg.first()).toHaveAttribute('data-state', mine!.legs[0].state);
    await api.dispose();
    clean(seen);
  });

  test('reloading preserves what the pages show', async ({ page }) => {
    const seen = watch(page);
    await signInThroughTheForm(page);
    await expectThePlayedRow(page);
    await page.reload();
    await expect(page.getByTestId('match-scoreline')).toContainText('2');
    await expect(page.getByTestId('forecast-provenance')).toBeVisible();
    await expect(page.getByTestId('expert-predictions')).toBeVisible();
    await page.goto('/selections');
    await page.reload();
    const slip = page.getByTestId('history-slip').filter({ hasText: 'representative local data' });
    const leg = slip.getByTestId('history-leg').filter({ hasText: HOME }).filter({ hasText: AWAY });
    await expect(leg).toHaveCount(1);
    const before = await leg.getAttribute('data-state');
    await page.reload();
    await expect(slip.getByTestId('history-leg').filter({ hasText: HOME }).filter({ hasText: AWAY })).toHaveAttribute('data-state', before ?? '');
    clean(seen);
  });
});

test.describe('the same, on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 });

  test('the fixture page and the day list fit the screen without errors', async ({ page }) => {
    const seen = watch(page);
    await expectThePlayedRow(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, 'horizontal overflow in CSS pixels').toBeLessThanOrEqual(1);
    const api = await apiContext();
    const row = await detail(api);
    await api.dispose();
    await page.goto(`/matches?date=${localDay(KICKOFF_UTC)}&comp=${row.competition.id}`);
    await expect(page.getByTestId('fixture-row').filter({ hasText: HOME })).toHaveCount(1);
    clean(seen);
  });
});
