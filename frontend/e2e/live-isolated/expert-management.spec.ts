import { APIRequestContext, BrowserContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { ISOLATED_API, isolatedApiContext } from '../support/isolated';
import {
  anyUpcomingMatch, cleanupQaPredictions, ensureQaExpertToken, publishQaPrediction, QA_EXPERT, QA_REASONING_MARKER,
} from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';
import expertEn from '../../src/i18n/messages/expert.en';

/**
 * My Predictions' pages and the publish toggle on REAL records, on the isolated stack (:3101
 * against :8001, soccer_predictions_e2e).
 *
 * WHY LIVE AS WELL AS MOCKED. e2e/mocked/expert-management.spec.ts proves the pages against a stub
 * that imitates the backend. This proves the imitation is right: the real endpoint's limit, offset
 * and X-Total-Count, the real CORS configuration letting the browser read that header, the real
 * toggle (PUBLISHED <-> ARCHIVED) and the real counts on /analytics/performance.
 *
 * WHAT IT WRITES. Only this suite's own predictions, published through publishQaPrediction and so
 * classified as test data, all on one upcoming fixture, and removed again before and after each
 * test (soft-deleted, as every delete is). The pagination test needs the QA expert to hold no
 * other prediction, because it deletes the 21st row through the UI and must know that row is its
 * own; it skips, saying so, when the account holds anything else.
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. The API context is isolatedApiContext (it refuses :8000
 * and any backend serving the live database), and the browser context aborts, and fails the test
 * on, any request to :8000 or :3100. No provider is called: anyUpcomingMatch reads with
 * refresh=false and the isolated backend has no provider keys.
 */

const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;

let api: APIRequestContext;
let token: string;
let match: ApiMatch | null = null;
let liveStackHits: string[] = [];
/** `METHOD /path` of every non-GET API request the browser sent, the sign-in excepted. */
let writes: string[] = [];
let dialogs: string[] = [];

const auth = () => ({ Authorization: `Bearer ${token}` });

async function guard(context: BrowserContext): Promise<void> {
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
}

/** X-Total-Count for the QA expert's predictions, optionally of one status. */
async function totalOnServer(status?: string): Promise<number> {
  const query = status ? `&status=${status}` : '';
  const response = await api.get(`/api/v1/expert/predictions/my-predictions?limit=1${query}`, { headers: auth() });
  expect(response.ok(), 'GET my-predictions on the isolated backend').toBe(true);
  return Number(response.headers()['x-total-count']);
}

const publish = (label: string) => publishQaPrediction(api, token, {
  match_id: match?.id,
  home_win_prob: 0.5,
  draw_prob: 0.3,
  away_win_prob: 0.2,
  confidence_score: 0.6,
  reasoning: `${QA_REASONING_MARKER} management ${label}`,
});

test.beforeAll(async () => {
  api = await isolatedApiContext();
  token = await ensureQaExpertToken(api);
  await cleanupQaPredictions(api, token);
  match = await anyUpcomingMatch(api);
});

test.beforeEach(async ({ context, page }) => {
  test.skip(!match, 'no upcoming fixture in the isolated database to attach a prediction to');
  await cleanupQaPredictions(api, token);
  liveStackHits = [];
  writes = [];
  dialogs = [];
  await guard(context);
  page.on('request', request => {
    const method = request.method();
    if (method === 'GET' || method === 'OPTIONS' || method === 'HEAD') return;
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    if (method === 'POST' && url.pathname === '/api/v1/auth/login') return;
    writes.push(`${method} ${url.pathname}`);
  });
  // Every confirmation on these pages is accepted, and recorded so its words can be checked.
  page.on('dialog', dialog => {
    dialogs.push(dialog.message());
    void dialog.accept();
  });
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
});

test.afterAll(async () => {
  if (api && token) await cleanupQaPredictions(api, token);
  await api?.dispose();
});

async function signInThroughTheUi(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /sign in|log in/i }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
}

const cards = (page: Page) => page.locator('div.space-y-4 > div');
const cardWith = (page: Page, text: string) => cards(page).filter({ hasText: text });
const listHeading = (page: Page) => page.locator('h2').filter({ hasText: /^Your Predictions/ });

async function openMine(page: Page): Promise<void> {
  await page.goto('/expert/predictions/my-predictions');
  await expect(page.getByRole('heading', { level: 1, name: 'My Predictions' })).toBeVisible();
  await page.waitForLoadState('networkidle');
}

async function recordOnScreen(page: Page): Promise<Record<string, number>> {
  await page.goto('/expert/dashboard');
  const tiles = page.locator('section[aria-labelledby="record-heading"] div.grid > div.card');
  await expect(tiles.first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  const out: Record<string, number> = {};
  for (let i = 0; i < await tiles.count(); i += 1) {
    const label = (await tiles.nth(i).locator('p').first().innerText()).trim();
    const figure = (await tiles.nth(i).locator('p.num').innerText()).replace(/\s+/g, '');
    if (/^\d+$/.test(figure)) out[label] = Number(figure);
  }
  return out;
}

/** The dashboard against the backend's own counts: the same numbers, and both add up. */
async function expectRecordMatchesServer(page: Page, when: string): Promise<void> {
  const response = await api.get('/api/v1/expert/analytics/performance', { headers: auth() });
  expect(response.ok()).toBe(true);
  const server = await response.json();
  expect(server.total_predictions, `${when}: the backend's own counts add up`)
    .toBe(server.published_predictions + server.not_published_predictions);
  const screen = await recordOnScreen(page);
  expect(screen, when).toEqual({
    [expertEn['expert.dashboard.statWritten']]: server.total_predictions,
    [expertEn['expert.dashboard.statPublished']]: server.published_predictions,
    [expertEn['expert.dashboard.statNotPublished']]: server.not_published_predictions,
    [expertEn['expert.dashboard.statUnpublished']]: server.archived_predictions,
  });
}

test('twenty-one real predictions: paged by the backend total, and deleting the 21st steps back', async ({ page }) => {
  test.skip(await totalOnServer() !== 0,
    'the QA expert holds predictions this suite did not create; this test deletes through the UI and must own every row');
  const created: string[] = [];
  for (let n = 1; n <= 21; n += 1) created.push((await publish(`row ${String(n).padStart(2, '0')}`)).id);
  expect(await totalOnServer()).toBe(21);

  await signInThroughTheUi(page);
  await openMine(page);
  await expect(cards(page)).toHaveCount(20);
  await expect(listHeading(page)).toHaveText('Your Predictions (21)');

  // The browser itself can read the total cross-origin: the backend's CORS configuration exposes it.
  const readable = await page.evaluate(async (base) => {
    const response = await fetch(`${base}/api/v1/expert/predictions/my-predictions?limit=1`, {
      headers: { Authorization: `Bearer ${window.localStorage.getItem('access_token')}` },
    });
    return response.headers.get('x-total-count');
  }, ISOLATED_API);
  expect(readable, 'X-Total-Count is not readable from the page').toBe('21');

  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Page 2', { exact: true })).toBeVisible();
  await expect(cards(page)).toHaveCount(1);
  // Newest first, so the first one published is the one on page 2.
  await expect(cardWith(page, 'management row 01')).toHaveCount(1);
  const next = page.getByRole('button', { name: 'Next', exact: true });
  await expect(next).toBeDisabled();

  await cardWith(page, 'management row 01').getByRole('button', { name: 'Delete', exact: true }).click();
  await expect.poll(() => writes).toEqual([`DELETE /api/v1/expert/predictions/${created[0]}`]);
  await expect(cards(page)).toHaveCount(20);
  await expect(page.getByText('Page 2', { exact: true })).toHaveCount(0);
  await expect(listHeading(page)).toHaveText('Your Predictions (20)');
  await expect(page.locator('body')).not.toContainText(expertEn['expert.mine.emptyNone']);
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toHaveCount(0);
  expect(await totalOnServer()).toBe(20);
});

test('Unpublish and Publish on My Predictions change the real record, and the dashboard agrees', async ({ page }) => {
  const created = await publish('toggle');
  const mine = (await totalOnServer()) <= 20;
  test.skip(!mine, 'the QA expert holds more than a page of predictions; the new one may not be on page 1');

  await signInThroughTheUi(page);
  await expectRecordMatchesServer(page, 'after publishing');

  await openMine(page);
  const card = cardWith(page, 'management toggle');
  await card.getByRole('button', { name: 'Unpublish', exact: true }).click();
  await expect.poll(() => writes).toEqual([`POST /api/v1/expert/predictions/${created.id}/toggle-publish`]);
  expect(dialogs).toEqual([expertEn['expert.publication.confirmUnpublish']]);
  await expect(card.getByRole('button', { name: 'Publish', exact: true })).toBeVisible();
  expect(await totalOnServer('archived')).toBe(1);
  // Off the public match page.
  const hidden = await (await api.get(`/api/v1/matches/${match?.id}`)).json();
  expect(hidden.expert_prediction?.reasoning ?? '').not.toContain('management toggle');
  await expectRecordMatchesServer(page, 'after unpublishing');
  await page.reload();
  await expectRecordMatchesServer(page, 'after unpublishing and a reload');

  await openMine(page);
  await card.getByRole('button', { name: 'Publish', exact: true }).click();
  await expect.poll(() => writes).toHaveLength(2);
  expect(writes[1]).toBe(`POST /api/v1/expert/predictions/${created.id}/toggle-publish`);
  expect(dialogs[1]).toBe(expertEn['expert.publication.confirmPublish']);
  await expect(card.getByRole('button', { name: 'Unpublish', exact: true })).toBeVisible();
  expect(await totalOnServer('archived')).toBe(0);
  const shown = await (await api.get(`/api/v1/matches/${match?.id}`)).json();
  expect(shown.expert_prediction?.reasoning ?? '').toContain('management toggle');
  await expectRecordMatchesServer(page, 'after republishing');
});
