import { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { isolatedApiContext } from '../support/isolated';
import {
  anyUpcomingMatch, cleanupQaPredictions, ensureQaExpertToken, publishQaPrediction, QA_EXPERT, QA_REASONING_MARKER,
} from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';

/**
 * An expert's earlier version and byline on the REAL match page, on the isolated stack (:3101
 * against :8001, soccer_predictions_e2e).
 *
 * WHY LIVE AS WELL AS MOCKED. e2e/mocked/revision-history.spec.ts proves the rendering against a
 * stub shaped like the backend's payload. This proves the shape: it publishes a prediction with
 * BTTS and over/under 2.5, edits ONLY the BTTS figures through the API, then reads the match page
 * as a visitor and compares every figure the earlier version shows with the one
 * GET /matches/{id} serves in `expert_prediction_revisions[].values`, the change lines with that
 * revision's `changes`, and the byline with the author's username.
 *
 * WHAT IT WRITES. One prediction by the QA expert, published through publishQaPrediction (so
 * classified as test data) on one upcoming fixture, edited once, and removed again before and
 * after (soft-deleted, as every delete is; its audit rows stay). It never publishes a late
 * prediction: the late path is covered by the mocked spec and by backend pytest.
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

test.beforeEach(async ({ context }) => {
  liveStackHits = [];
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
});

const percentIn = (page: Page, unit: number): Promise<string> =>
  page.evaluate(value => new Intl.NumberFormat('en-GB', {
    style: 'percent', minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format((value * 100) / 100), unit);

const normalise = (value: string): string => value.replace(/\s+/g, ' ').trim();

test('the real match page shows every market of the earlier version, what changed, and the author', async ({ page }) => {
  test.skip(!match, 'no upcoming fixture in the isolated database to attach a prediction to');
  const fixture = match as ApiMatch;

  const me = await api.get('/api/v1/users/me', { headers: auth() });
  expect(me.ok(), 'GET /users/me on the isolated backend').toBe(true);
  const username = String((await me.json()).username);

  const created = await publishQaPrediction(api, token, {
    match_id: fixture.id,
    home_win_prob: 0.5, draw_prob: 0.3, away_win_prob: 0.2, confidence_score: 0,
    btts_yes_prob: 0.6, btts_no_prob: 0.4,
    total_goals_over_25_prob: 0.55, total_goals_under_25_prob: 0.45, total_goals_confidence: 0.65,
    reasoning: `${QA_REASONING_MARKER} revision history, first version`,
  });
  // Only BTTS changes. The update requires the 1X2 block, so it is sent again unchanged; every
  // other field is absent, which the update reads as "leave it".
  const edited = await api.put(`/api/v1/expert/predictions/${created.id}`, {
    headers: auth(),
    data: { home_win_prob: 0.5, draw_prob: 0.3, away_win_prob: 0.2, btts_yes_prob: 0.4, btts_no_prob: 0.6 },
  });
  expect(edited.status(), await edited.text()).toBeLessThan(300);

  // What the backend serves, which is what the page is checked against.
  const detail = await (await api.get(`/api/v1/matches/${fixture.id}`)).json();
  const revisions = (detail.expert_prediction_revisions as Array<Record<string, unknown>>)
    .filter(revision => revision.prediction_id === created.id);
  expect(revisions, 'one edit, one earlier version').toHaveLength(1);
  const served = revisions[0];
  const values = served.values as Record<string, number | null>;
  expect(served.changes, 'the backend reports exactly the two BTTS fields as changed').toEqual([
    { field: 'btts_yes_prob', from: 0.6, to: 0.4 },
    { field: 'btts_no_prob', from: 0.4, to: 0.6 },
  ]);
  const ours = (detail.expert_predictions as Array<Record<string, unknown>>).find(row => row.id === created.id);
  expect((ours?.author as { username?: string } | undefined)?.username, 'the public author').toBe(username);

  await page.goto(`/match/${fixture.id}`);
  const group = page.locator(`[data-testid="expert-revision-group"][data-prediction-id="${created.id}"]`);
  const item = group.getByTestId('expert-revision').first();
  // The figures first, by value: the old rendering showed four cells and no BTTS at all.
  await expect(page.getByTestId('expert-revisions')).toBeVisible();
  const shown = normalise(await page.getByTestId('expert-revisions').innerText());
  expect(shown, 'the earlier BTTS yes figure is not on the page').toContain(normalise(await percentIn(page, 0.6)));
  expect(shown, 'the raw audit text reached the page').not.toMatch(/btts_yes_prob|->/);

  await expect(group).toHaveCount(1);
  await expect(group).toContainText(`Earlier versions of the prediction by ${username}`);
  for (const [field, value] of Object.entries(values)) {
    if (!/_prob$|confidence/.test(field) || typeof value !== 'number') continue;
    const cell = item.locator(`[data-testid="revision-value"][data-field="${field}"]`);
    await expect(cell, `${field} (${value}) has no cell on the page`).toHaveCount(1);
    await expect(cell).toContainText(await percentIn(page, value));
  }
  // 3.5 was never published: both halves null, the market said to be left out.
  expect(values.total_goals_over_35_prob).toBeNull();
  await expect(item.locator('[data-testid="revision-market"][data-market="ou35"]')).toContainText('Expert left this out');

  const changes = item.getByTestId('revision-change');
  await expect(changes).toHaveCount(2);
  await expect(changes.nth(0)).toHaveText('Both teams to score – Yes: 60% → 40%');
  await expect(changes.nth(1)).toHaveText('Both teams to score – No: 40% → 60%');

  const byline = page.getByTestId('expert-byline').filter({ hasText: username });
  await expect(byline).toHaveCount(1);
  await expect(byline).toContainText(`By ${username}`);
  const body = normalise(await page.locator('body').innerText());
  expect(body, 'the raw source enum is on the page').not.toContain('expert_manual');
  expect(body, 'the expert’s email is on the page').not.toContain(QA_EXPERT.email);
  // Ours was published before kickoff; the page carries a late chip for exactly the rows the
  // backend flags, which on an upcoming fixture should be none.
  expect(ours?.published_after_kickoff, 'published before kickoff').toBe(false);
  const late = (detail.expert_predictions as Array<Record<string, unknown>>)
    .filter(row => row.published_after_kickoff === true).length;
  await expect(page.getByTestId('expert-late-publication')).toHaveCount(late);
});
