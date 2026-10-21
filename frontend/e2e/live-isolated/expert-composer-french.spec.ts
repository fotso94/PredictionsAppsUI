import { APIRequestContext, Page, Request } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { isolatedApiContext } from '../support/isolated';
import {
  anyUpcomingMatch, classifyQaPrediction, cleanupQaPredictions, ensureQaExpertToken, QA_EXPERT,
  QA_REASONING_MARKER, QaPredictionRow,
} from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';

/**
 * The composer in French and in Douala, against the REAL isolated backend (:3101 against :8001,
 * soccer_predictions_e2e) — QA findings 7 and 9.
 *
 * WHY LIVE AS WELL AS MOCKED. e2e/mocked/expert-composer-localisation.spec.ts proves the French
 * against stubs. This proves the two claims a stub cannot: that a French decimal comma typed into
 * the real composer is STORED as the same probability by the real API (55,5 → 0.555), and that the
 * picker's forecast badge says what the backend's own list payload says about a real fixture —
 * read from that payload here, not assumed.
 *
 * WHAT IT WRITES. One prediction by the QA expert on one upcoming fixture, published through the
 * composer UI, classified as test data straight after (best effort, as in ./expert-composer.spec.ts)
 * and removed again before and after (soft-deleted, as every delete is; its audit rows stay). One
 * edit is saved unchanged, which the backend records as a revision of that same QA row.
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. The API context is isolatedApiContext (it refuses :8000
 * and any backend serving the live database), and the browser context aborts, and fails the test
 * on, any request to :8000 or :3100. No provider is called: every read is refresh=false and the
 * isolated backend has no provider keys; the test also fails on any request carrying refresh=true.
 *
 * ABSENCE WINDOW. "Cancel sends nothing" is checked over 1500 ms after the press; the editor sends
 * its PUT synchronously from the Save click, so one that is going to leave has left by then.
 */

const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;
const DOUALA = 'Africa/Douala';

let api: APIRequestContext;
let token: string;
let match: ApiMatch | null = null;
let liveStackHits: string[] = [];
let refreshing: string[] = [];

const auth = () => ({ Authorization: `Bearer ${token}` });

test.beforeAll(async () => {
  api = await isolatedApiContext();
  token = await ensureQaExpertToken(api);
  await cleanupQaPredictions(api, token);
  match = await anyUpcomingMatch(api);
});

test.afterAll(async () => {
  if (api && token) await cleanupQaPredictions(api, token);
  await api?.dispose();
});

test.beforeEach(async ({ context, page }) => {
  liveStackHits = [];
  refreshing = [];
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
  page.on('request', (request: Request) => {
    if (request.url().includes('/api/v1') && /refresh=true/i.test(request.url())) refreshing.push(request.url());
  });
  // French, in Douala, before the app boots: src/i18n reads both keys as its module is evaluated.
  await page.addInitScript(zone => {
    window.localStorage.setItem('sp.language.v1', 'fr');
    window.localStorage.setItem('sp.timeZone.v1', zone);
  }, DOUALA);
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
  expect(refreshing, 'a provider refresh was asked for').toEqual([]);
});

const say = (key: keyof typeof fr, params: Record<string, string | number> = {}): string =>
  renderMessage(compileMessage(fr[key]), 'fr-FR', params);

/** A 0-100 percentage as the page's own Intl writes it in French, up to `max` decimals. */
const percentIn = (page: Page, percent: number, max = 2): Promise<string> =>
  page.evaluate(([value, digits]) => new Intl.NumberFormat('fr-FR', {
    style: 'percent', minimumFractionDigits: 0, maximumFractionDigits: digits, useGrouping: false,
  }).format(value / 100), [percent, max] as const);

async function signInThroughTheUi(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: fr['auth.login.submit'] }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
}

/**
 * The badge the picker must show for one fixture, decided from the backend's own list payload by
 * the backend's own states: the compact brief's verdict first, then the forecast's `state`, and a
 * forecast that is held is never called absent.
 */
function expectedBadge(payload: Record<string, unknown>): string {
  const compact = payload.brief_compact as { forecast_state?: string; stale?: boolean } | null | undefined;
  const forecast = payload.forecast as { state?: string } | null | undefined;
  const state = compact?.forecast_state ?? forecast?.state ?? payload.forecast_state ?? null;
  if (state === 'kickoff_passed') return fr['expert.picker.modelForecastReference'];
  if (state === 'stale' || compact?.stale === true) return fr['expert.picker.modelForecastStale'];
  if (state === 'available' || forecast) return fr['expert.picker.modelForecastHeld'];
  return fr['brief.noForecastHeld'];
}

test('the French picker states a real fixture\'s forecast as the backend\'s list payload does', async ({ page }) => {
  test.skip(!match, 'no upcoming fixture in the isolated database to write about');
  const fixture = match as ApiMatch;

  await signInThroughTheUi(page);
  await page.goto('/expert/predictions/create');
  await expect(page.locator('#picker-date')).toBeVisible();

  // The fixture's calendar day IN DOUALA, which is the day the picker files it under.
  const day = await page.evaluate(([iso, zone]) => new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(iso)), [fixture.kickoff_utc, DOUALA] as const);
  await page.locator('#picker-date').fill(day);
  await page.waitForLoadState('networkidle');

  // What the backend says about this fixture in that day's list — Douala is UTC+01:00 all year.
  const list = await api.get(`/api/v1/matches?date=${day}&tz_offset=60&tz_offset_end=60&refresh=false`);
  expect(list.ok(), 'the day list on the isolated backend').toBe(true);
  const served = ((await list.json()).matches as Array<Record<string, unknown>>).find(row => row.id === fixture.id);
  expect(served, 'the fixture is in its Douala day').toBeTruthy();

  const row = page.locator('li').filter({ hasText: String(fixture.home?.name) }).filter({ hasText: String(fixture.away?.name) });
  await expect(row).toHaveCount(1);
  const badge = expectedBadge(served as Record<string, unknown>);
  await expect(row, `the row does not say what the backend says: "${badge}"`).toContainText(badge);
  await expect(row.getByTestId('picker-forecast'), 'the forecast badge on a real fixture').toHaveText(badge);
  await expect(row.getByTestId('picker-expert')).toHaveCount((served as Record<string, unknown>).expert_prediction ? 1 : 0);
  // The row's name is French, and still begins with the action, as the English one does.
  expect(await row.getByRole('button').getAttribute('aria-label'))
    .toMatch(new RegExp(`^${fr['expert.action.writePrediction']}\\s?:`));
});

test('a French decimal comma is stored as the same probability, and an edit reopens it with a comma', async ({ page }) => {
  test.skip(!match, 'no upcoming fixture in the isolated database to write about');
  const fixture = match as ApiMatch;

  await signInThroughTheUi(page);
  await page.goto(`/expert/predictions/create?matchId=${encodeURIComponent(fixture.id)}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');

  await page.locator('#composer-home').fill('55,5');
  await page.locator('#composer-draw').fill('24,5');
  await page.locator('#composer-away').fill('20');
  await page.locator('#composer-reasoning').fill(`${QA_REASONING_MARKER} virgule décimale en français`);

  // The editor and the preview say it in French before anything is published.
  const hundred = await percentIn(page, 100);
  await expect(page.locator('p').filter({ hasText: say('expert.editor.totalBalanced', { percent: hundred }) }).first())
    .toBeVisible();
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  const preview = page.getByLabel(fr['expert.preview.regionLabel']);
  await expect(preview).toContainText(await percentIn(page, 55.5, 1));
  await expect(preview).toContainText(await percentIn(page, 24.5, 1));

  const created = page.waitForResponse(
    response => response.url().includes('/api/v1/expert/predictions/manual') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  const createResponse = await created;
  expect(createResponse.ok(), 'the composer published the prediction').toBeTruthy();
  const createdId = String((await createResponse.json()).id);
  await classifyQaPrediction(api, token, createdId);
  await expect(page.getByRole('heading', { name: fr['expert.published.title'] })).toBeVisible();

  // The API is the source of truth: 55,5 typed is 0.555 stored.
  const stored = async (): Promise<QaPredictionRow | undefined> => {
    const mine = await api.get('/api/v1/expert/predictions/my-predictions?limit=20', { headers: auth() });
    const rows = await mine.json();
    return (Array.isArray(rows) ? rows : rows.predictions || []).find((r: QaPredictionRow) => r.id === createdId);
  };
  const row = await stored();
  expect(row, 'the prediction reached the isolated backend').toBeTruthy();
  expect(Number(row?.home_win_prob)).toBeCloseTo(0.555, 6);
  expect(Number(row?.draw_prob)).toBeCloseTo(0.245, 6);
  expect(Number(row?.away_win_prob)).toBeCloseTo(0.2, 6);

  // The edit reopens it the way it was typed, and Cancel sends nothing.
  const puts: string[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && request.url().includes(`/api/v1/expert/predictions/${createdId}`)) puts.push(request.url());
  });
  await page.goto('/expert/predictions/my-predictions');
  await page.getByRole('button', { name: fr['expert.action.edit'], exact: true }).first().click();
  await expect(page.locator(`#edit-${createdId}-home`)).toHaveValue('55,5');
  await expect(page.locator(`#edit-${createdId}-draw`)).toHaveValue('24,5');
  await expect(page.locator(`#edit-${createdId}-away`)).toHaveValue('20');
  await page.getByRole('button', { name: fr['expert.action.cancel'], exact: true }).click();
  await page.waitForTimeout(1500);
  expect(puts, 'Cancel sent an update').toHaveLength(0);

  // Saved as reopened: one PUT, and the stored figures are exactly what they were.
  await page.getByRole('button', { name: fr['expert.action.edit'], exact: true }).first().click();
  await expect(page.locator(`#edit-${createdId}-home`)).toHaveValue('55,5');
  const saved = page.waitForResponse(
    response => response.url().includes(`/api/v1/expert/predictions/${createdId}`) && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: fr['expert.action.saveChanges'], exact: true }).click();
  expect((await saved).ok(), 'the unchanged edit was saved').toBeTruthy();
  await page.waitForTimeout(1000);
  expect(puts, 'the save was sent more than once').toHaveLength(1);
  const after = await stored();
  expect(Number(after?.home_win_prob)).toBeCloseTo(0.555, 6);
  expect(Number(after?.draw_prob)).toBeCloseTo(0.245, 6);
  expect(Number(after?.away_win_prob)).toBeCloseTo(0.2, 6);
});
