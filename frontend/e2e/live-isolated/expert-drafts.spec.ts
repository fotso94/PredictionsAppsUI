import { APIRequestContext, BrowserContext, Page } from '@playwright/test';
import { test, expect } from '../support/live-test';
import { isolatedApiContext } from '../support/isolated';
import { ensureQaExpertToken, QA_EXPERT, QA_REASONING_MARKER } from '../support/qa-account';

/**
 * Two drafts, A and B, on the real isolated stack (:3101 against :8001, soccer_predictions_e2e).
 *
 * WHY LIVE AS WELL AS MOCKED. e2e/mocked/expert-drafts.spec.ts proves the store and the composer
 * with stubbed fixtures. This proves the same journey on real fixtures, through the real match
 * selection and the real sign-in, where the fixture ids are the backend's own and the detail
 * route is the real one: A typed, reloaded, B opened through match selection, typed, reloaded,
 * and both still there afterwards.
 *
 * NOTHING IS PUBLISHED, AND THAT IS ASSERTED. A draft lives in the browser only, so the journey
 * must send no POST, PUT, PATCH or DELETE to the API other than the sign-in itself, and the QA
 * expert's own predictions must be the same list before and after. A mistaken Publish click would
 * fail both checks rather than quietly leave a row behind.
 *
 * NOTHING HERE MAY REACH THE LIVE STACK. The API context is isolatedApiContext (it refuses :8000
 * and any backend serving the live database), and the browser context aborts, and fails the test
 * on, any request to :8000 or :3100.
 */

const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;

let api: APIRequestContext;
let token: string;
let liveStackHits: string[] = [];
let writes: string[] = [];

async function guard(context: BrowserContext): Promise<void> {
  await context.route(LIVE_STACK, route => {
    liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
}

const myPredictionIds = async (): Promise<string[]> => {
  const response = await api.get('/api/v1/expert/predictions/my-predictions?limit=100', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), 'GET my-predictions on the isolated backend').toBe(true);
  return ((await response.json()) as Array<{ id: string }>).map(row => row.id).sort();
};

test.beforeAll(async () => {
  api = await isolatedApiContext();
  token = await ensureQaExpertToken(api);
});

test.afterAll(async () => {
  await api?.dispose();
});

test.beforeEach(async ({ context, page }) => {
  liveStackHits = [];
  writes = [];
  await guard(context);
  page.on('request', request => {
    const method = request.method();
    if (method === 'GET' || method === 'OPTIONS' || method === 'HEAD') return;
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    if (method === 'POST' && url.pathname === '/api/v1/auth/login') return;
    writes.push(`${method} ${url.pathname}`);
  });
});

test.afterEach(() => {
  expect(liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
});

async function signInThroughTheUi(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /sign in|log in/i }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
}

const rows = (page: Page) => page.getByRole('button', { name: /^write a prediction:/i });

/** Click the first of Today / Tomorrow / In two days that lists at least `wanted` fixtures. */
async function dayWith(page: Page, wanted: number, only?: RegExp): Promise<RegExp | null> {
  for (const label of only ? [only] : [/^today$/i, /^tomorrow$/i, /^in two days$/i]) {
    const chip = page.getByRole('button', { name: label }).first();
    if (await chip.count() === 0) continue;
    await chip.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    if (await rows(page).count() >= wanted) return label;
  }
  return null;
}

const matchIdOf = (page: Page): string => new URL(page.url()).searchParams.get('matchId') ?? '';

interface Draft { home: string; draw: string; away: string; reasoning: string }

async function typeDraft(page: Page, draft: Draft): Promise<void> {
  await page.locator('#composer-home').fill(draft.home);
  await page.locator('#composer-draw').fill(draft.draw);
  await page.locator('#composer-away').fill(draft.away);
  await page.locator('#composer-reasoning').fill(draft.reasoning);
  await expect.poll(() => page.evaluate(text => Object.keys(window.localStorage)
    .filter(key => key.startsWith('expert.composer.draft'))
    .some(key => (window.localStorage.getItem(key) ?? '').includes(text)), draft.reasoning)).toBe(true);
}

async function expectFields(page: Page, draft: Draft): Promise<void> {
  await expect(page.locator('#composer-home')).toHaveValue(draft.home);
  await expect(page.locator('#composer-draw')).toHaveValue(draft.draw);
  await expect(page.locator('#composer-away')).toHaveValue(draft.away);
  await expect(page.locator('#composer-reasoning')).toHaveValue(draft.reasoning);
}

async function reloadComposer(page: Page): Promise<void> {
  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

const storedWith = (page: Page, text: string): Promise<number> => page.evaluate(wanted => Object.keys(window.localStorage)
  .filter(key => key.startsWith('expert.composer.draft'))
  .filter(key => (window.localStorage.getItem(key) ?? '').includes(wanted)).length, text);

/** The QA path: match selection, the day that was found, then the fixture's own row. */
async function openThroughMatchSelection(page: Page, day: RegExp, label: string): Promise<string> {
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  expect(await dayWith(page, 2, day), 'match selection lists the same day').not.toBeNull();
  await page.getByRole('button', { name: label, exact: true }).click();
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const id = matchIdOf(page);
  expect(id, 'match selection opened the composer on a fixture').not.toBe('');
  return id;
}

test("A's draft survives B, through real match selection and reloads, and nothing is published", async ({ page }) => {
  const before = await myPredictionIds();
  await signInThroughTheUi(page);

  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  const day = await dayWith(page, 2);
  test.skip(!day, 'no day in the next three with two fixtures to write about');
  const labelA = (await rows(page).nth(0).getAttribute('aria-label')) ?? '';
  const labelB = (await rows(page).nth(1).getAttribute('aria-label')) ?? '';

  const draftA: Draft = { home: '55', draw: '25', away: '20', reasoning: `${QA_REASONING_MARKER} draft A, never published` };
  const draftB: Draft = { home: '40', draw: '30', away: '30', reasoning: `${QA_REASONING_MARKER} draft B, never published` };

  const idA = await openThroughMatchSelection(page, day as RegExp, labelA);
  await typeDraft(page, draftA);
  await reloadComposer(page);
  await expectFields(page, draftA);

  const idB = await openThroughMatchSelection(page, day as RegExp, labelB);
  expect(idB).not.toBe(idA);
  await expectFields(page, { home: '', draw: '', away: '', reasoning: '' });
  expect(await storedWith(page, draftA.reasoning), "opening B overwrote A's draft in this browser").toBe(1);

  await typeDraft(page, draftB);
  await reloadComposer(page);
  await expectFields(page, draftB);

  await page.goto(`/expert/predictions/create?matchId=${encodeURIComponent(idA)}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, draftA);
  await page.goto(`/expert/predictions/create?matchId=${encodeURIComponent(idB)}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, draftB);

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('draft-row')).toHaveCount(2);

  expect(writes, 'a draft operation sent a write to the isolated API').toEqual([]);
  expect(await myPredictionIds(), "the QA expert's predictions changed").toEqual(before);
});
