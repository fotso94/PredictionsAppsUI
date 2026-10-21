import { expect, test, Page, Request, Route } from '@playwright/test';
import { ApiMatch, Json, dayPayload, fixtureAt, stubBackend } from '../support/api-stub';
import { BackendUser, regularUser, signIn } from '../support/auth';

/**
 * THE COMPOSER'S UNPUBLISHED DRAFTS, ONE PER EXPERT AND FIXTURE (QA finding 2).
 *
 * The defect: the composer kept ONE draft slot per user, with no fixture in it. An expert wrote a
 * view on fixture A, went to match selection and opened fixture B, and the composer's autosave
 * wrote B's empty form over A's slot in the first render. A's words were gone from storage before
 * a key was pressed; reloading B then said "Draft restored" over empty fields. Changing fixture
 * inside the composer carried A's numbers and reasoning onto B. Publishing, discarding and
 * "Start again" all worked on the whole slot, and none of them asked first.
 *
 * WHAT IS ASSERTED IS WHAT THE BROWSER HOLDS AND WHAT WAS SENT:
 *   - the values in the fields after a reload, and after leaving and coming back;
 *   - a scan of every localStorage key starting with `expert.composer.draft`, which the old (v1)
 *     and the new store share. The scan reads the stored TEXT, never the key's shape, so the same
 *     test runs on the old code and on the new one and fails on the old one for the real reason:
 *     the words are no longer there;
 *   - every non-GET request to /api/v1/expert/**, recorded and asserted empty, so no draft
 *     operation publishes, edits or deletes anything. Only the publish test sends one, and exactly
 *     one;
 *   - text on screen as well, never instead.
 *
 * DRAFTS ARE CREATED BY TYPING. `page.addInitScript` re-runs on every navigation, so a draft seeded
 * through it comes back after every reload and hides exactly the loss under test. The only seeds
 * here are the legacy v1 key (migration is the thing being tested, and it is seeded ONCE per tab
 * behind a sessionStorage flag), a storage that refuses writes, and the white-box cap test, which
 * says why it has to know the v2 shape.
 *
 * FIXTURES KICK OFF IN THE FUTURE (three days out) unless a test is about a fixture that has kicked
 * off, so no kickoff rule can interfere with the journeys.
 *
 * COST. Every /api/v1 route is stubbed; nothing reaches a backend. A guard aborts, and fails the
 * test on, any request to the live stack (:8000 or :3100).
 */

const LIVE_STACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0):(8000|3100)(\/|$)/;

const DAY_MS = 24 * 60 * 60 * 1000;
const isoIn = (ms: number): string => new Date(Date.now() + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');

const A = fixtureAt(isoIn(3 * DAY_MS), 'Coton Sport', 'Union Douala', 'fx-a');
const B = fixtureAt(isoIn(3 * DAY_MS + 2 * 60 * 60 * 1000), 'Canon Yaounde', 'Tonnerre', 'fx-b');
/** Kicked off thirty days ago: past the cap's seven-day grace, and still never pruned on its own. */
const KICKED_OFF = fixtureAt(isoIn(-30 * DAY_MS), 'Fovu Baham', 'Bamboutos', 'fx-k');
const FIXTURES: ApiMatch[] = [A, B, KICKED_OFF];

/** `regularUser()` in e2e/support/auth.ts; the second account differs only in id and address. */
const USER_X = '00000000-0000-4000-8000-000000000001';
const USER_Y = '00000000-0000-4000-8000-000000000002';
const expert = (userId: string): BackendUser => regularUser({
  user_id: userId,
  role: 'expert',
  // The header shows the first name, so the second account's is what proves who is signed in.
  full_name: userId === USER_X ? 'QA Expert' : 'Ysolde Second',
  email: userId === USER_X ? 'qa.expert@predictions-local.dev' : 'qa.second-expert@predictions-local.dev',
});

const DRAFT_PREFIX = 'expert.composer.draft';
const LEGACY_KEY = `${DRAFT_PREFIX}.v1.${USER_X}`;

// The English copy these tests read. Literals rather than catalogue lookups, so that on the old
// code (which has none of the new keys) a lookup cannot come back undefined and match anything.
const COPY = {
  listTitle: 'Your unpublished drafts',
  noFixture: 'Fixture not chosen yet',
  keep: 'Keep it',
  confirmDiscard: 'Discard draft',
  discard: 'Discard',
  continue: 'Continue',
  startAgain: 'Start again',
  seeAll: 'See all drafts',
  kickedOff: 'Kicked off — this draft can no longer be published as a prematch prediction.',
  saveFailed: 'This browser would not store your draft.',
  discardConfirmA: 'Discard your draft for Coton Sport v Union Douala? This cannot be undone.',
  keptA: 'Your draft for Coton Sport v Union Douala is kept.',
};

interface Draft { home: string; draw: string; away: string; reasoning: string }
const DRAFT_A: Draft = { home: '55', draw: '25', away: '20', reasoning: 'A-only words' };
const DRAFT_B: Draft = { home: '40', draw: '30', away: '30', reasoning: 'B-only words' };
const EMPTY: Draft = { home: '', draw: '', away: '', reasoning: '' };

interface World {
  /** Bodies of every POST /expert/predictions/manual. */
  created: Json[];
  /** `METHOD /path` of every non-GET request to /api/v1/expert/**. */
  expertWrites: string[];
  liveStackHits: string[];
}

let world: World | null = null;

/** Every expert endpoint the dashboard and the composer read, plus the one create. */
async function stubExpert(page: Page, state: World): Promise<void> {
  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');
    if (path === '/analytics/performance') {
      return json({
        expert_id: 'qa-expert', expert_name: 'QA Expert',
        total_predictions: 0, published_predictions: 0, pending_predictions: 0,
        archived_predictions: 0, not_published_predictions: 0,
        accuracy_rate: null, average_confidence: null,
        predictions_by_league: {}, recent_predictions: [], performance_trend: [],
      });
    }
    if (path === '/predictions/my-predictions') return json([]);
    if (path === '/predictions/review-queue') return json([]);
    if (path === '/predictions/manual' && request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      state.created.push(body);
      return json({
        id: 'pred-new', source: 'EXPERT_MANUAL', priority_level: 1, status: 'PUBLISHED',
        created_by: 'qa-expert', created_at: new Date().toISOString(), published_at: new Date().toISOString(),
        superseded_by: null, match_details: null, user_details: null, key_factors: null,
        ...body,
      });
    }
    return json({});
  });
}

/** Signed in as `userId` (an expert), every backend answer stubbed, every expert write recorded. */
async function openWorld(page: Page, userId: string = USER_X): Promise<World> {
  const state: World = { created: [], expertWrites: [], liveStackHits: [] };
  world = state;
  page.on('request', request => {
    const method = request.method();
    // A CORS preflight is not a write; nothing else that is not a GET is let through unrecorded.
    if (method === 'GET' || method === 'OPTIONS') return;
    if (/\/api\/v1\/expert\//.test(request.url())) {
      state.expertWrites.push(`${method} ${new URL(request.url()).pathname}`);
    }
  });
  await stubBackend(page, {
    // The day list shows A and B on whatever day is asked for; the detail route serves each
    // fixture with its own kickoff, which is what the composer and the draft read.
    day: date => dayPayload(date, [A, B].map(match => ({ ...match }))),
    matchById: id => FIXTURES.find(match => match.id === id) ?? null,
  });
  await stubExpert(page, state);
  await signIn(page, { user: expert(userId) });
  await page.route(LIVE_STACK, (route: Route) => {
    state.liveStackHits.push(`${route.request().method()} ${route.request().url()}`);
    return route.abort('blockedbyclient');
  });
  return state;
}

test.afterEach(() => {
  if (world) expect(world.liveStackHits, 'nothing may reach the live stack (:8000 or :3100)').toEqual([]);
  world = null;
});

/** The stored text of every draft entry in this browser, old store or new. */
const storedDrafts = (page: Page): Promise<string[]> => page.evaluate((prefix) => {
  const out: string[] = [];
  for (let i = 0; i < window.localStorage.length; i += 1) {
    const key = window.localStorage.key(i);
    if (key && key.startsWith(prefix)) out.push(window.localStorage.getItem(key) ?? '');
  }
  return out;
}, DRAFT_PREFIX);

/** How many stored draft entries contain `text`. */
const storedWith = async (page: Page, text: string): Promise<number> =>
  (await storedDrafts(page)).filter(value => value.includes(text)).length;

/** Open the composer on a fixture by URL and wait until its editor is on screen. */
async function openComposer(page: Page, fixture: ApiMatch): Promise<void> {
  await page.goto(`/expert/predictions/create?matchId=${fixture.id}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

const home = (fixture: ApiMatch) => (fixture.home as { name: string }).name;
const away = (fixture: ApiMatch) => (fixture.away as { name: string }).name;
const rowButton = (page: Page, fixture: ApiMatch) =>
  page.getByRole('button', { name: new RegExp(`^Write a prediction: ${home(fixture)} versus ${away(fixture)},`) });

/** The QA path: the match-selection page, then the fixture's own row. */
async function openThroughMatchSelection(page: Page, fixture: ApiMatch): Promise<void> {
  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');
  await rowButton(page, fixture).click();
  await expect(page).toHaveURL(new RegExp(`[?&]matchId=${fixture.id}(&|$)`));
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

/** Type a draft into the open composer and wait until the browser holds its words. */
async function typeDraft(page: Page, draft: Draft): Promise<void> {
  await page.locator('#composer-home').fill(draft.home);
  await page.locator('#composer-draw').fill(draft.draw);
  await page.locator('#composer-away').fill(draft.away);
  await page.locator('#composer-reasoning').fill(draft.reasoning);
  await expect.poll(() => storedWith(page, draft.reasoning), {
    message: `the draft "${draft.reasoning}" was never stored`,
  }).toBeGreaterThan(0);
}

async function expectFields(page: Page, draft: Draft): Promise<void> {
  await expect(page.locator('#composer-home')).toHaveValue(draft.home);
  await expect(page.locator('#composer-draw')).toHaveValue(draft.draw);
  await expect(page.locator('#composer-away')).toHaveValue(draft.away);
  await expect(page.locator('#composer-reasoning')).toHaveValue(draft.reasoning);
}

const draftRows = (page: Page) => page.getByTestId('draft-row');
const draftRow = (page: Page, text: string) => draftRows(page).filter({ hasText: text });

/* ============================================================================ the QA journey */

test("A's draft survives opening B through match selection, reloads, and coming back", async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  // Sanity: a reload of A gives A back. This much worked before the fix too.
  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, DRAFT_A);

  // The path QA took: match selection, then B's row.
  await openThroughMatchSelection(page, B);
  await expectFields(page, EMPTY);
  expect(
    await storedWith(page, DRAFT_A.reasoning),
    "opening B overwrote A's draft in this browser: A's words are no longer stored",
  ).toBe(1);

  await typeDraft(page, DRAFT_B);
  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, DRAFT_B);
  expect(await storedWith(page, DRAFT_A.reasoning), "A's draft did not survive B's draft").toBe(1);

  // Back to A, by its own URL: A's words, intact, and B's still kept beside them.
  await openComposer(page, A);
  await expectFields(page, DRAFT_A);
  expect(await storedWith(page, DRAFT_B.reasoning), "going back to A lost B's draft").toBe(1);

  expect(state.expertWrites, 'a draft operation sent a write to the expert API').toEqual([]);
  expect(state.created).toHaveLength(0);
});

test('changing fixture inside the composer carries nothing across, keeps the draft, and follows the URL', async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  await page.getByRole('button', { name: 'Change fixture' }).click();
  await expect(page, 'Change fixture did not take matchId out of the URL').not.toHaveURL(/matchId=/);
  await expect(page.locator('body'), 'the expert was not told A is kept').toContainText(COPY.keptA);
  expect(await storedWith(page, DRAFT_A.reasoning)).toBe(1);

  // B, chosen in the composer's own picker.
  await rowButton(page, B).click();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, EMPTY);
  await expect(page, 'choosing B in the page did not put B in the URL').toHaveURL(/[?&]matchId=fx-b(&|$)/);

  // A reload opens B again, still empty: the URL, not the last write, says which fixture this is.
  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, EMPTY);

  // And A is A's, not B's.
  await openComposer(page, A);
  await expectFields(page, DRAFT_A);

  // From the picker's drafts list, Continue reopens it too.
  await page.goto('/expert/predictions/create');
  await expect(page.getByRole('heading', { name: COPY.listTitle })).toBeVisible();
  await expect(draftRows(page), 'opening B without typing must not create a draft').toHaveCount(1);
  await draftRow(page, 'Coton Sport').getByRole('button', { name: COPY.continue, exact: true }).click();
  await expect(page).toHaveURL(/[?&]matchId=fx-a(&|$)/);
  await expectFields(page, DRAFT_A);

  expect(state.expertWrites, 'a draft operation sent a write to the expert API').toEqual([]);
});

test('opening a fixture without typing stores no draft and lists none', async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, B);
  expect(await storedDrafts(page), 'an untouched composer stored a draft').toEqual([]);

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('draft-summary'), 'the dashboard offered an empty draft').toHaveCount(0);
  expect(await storedDrafts(page)).toEqual([]);

  // And erasing every field of a typed draft removes it again: the expert's own words, gone by
  // the expert's own hand, are not kept as an empty shell.
  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);
  for (const id of ['#composer-home', '#composer-draw', '#composer-away', '#composer-reasoning']) {
    await page.locator(id).fill('');
  }
  await expect.poll(() => storedDrafts(page), { message: 'an emptied draft stayed in storage' }).toEqual([]);

  expect(state.expertWrites).toEqual([]);
});

/* ============================================================================ discard */

test('every discard asks first, and removes only the draft it names', async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);
  await openComposer(page, B);
  await typeDraft(page, DRAFT_B);

  // The dashboard lists both, newest first.
  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  const summaries = page.getByTestId('draft-summary');
  await expect(summaries, 'the dashboard does not list both drafts').toHaveCount(2);
  await expect(summaries.nth(0)).toContainText('Canon Yaounde v Tonnerre');
  await expect(summaries.nth(1)).toContainText('Coton Sport v Union Douala');

  // Discard on A asks; "Keep it" keeps it.
  const rowA = draftRow(page, 'Coton Sport');
  await rowA.getByRole('button', { name: COPY.discard, exact: true }).click();
  await expect(rowA).toContainText(COPY.discardConfirmA);
  expect(await storedWith(page, DRAFT_A.reasoning), 'Discard removed the draft before it was confirmed').toBe(1);
  await rowA.getByRole('button', { name: COPY.keep }).click();
  await expect(draftRows(page)).toHaveCount(2);
  expect(await storedWith(page, DRAFT_A.reasoning)).toBe(1);

  // Confirmed, it removes A and only A.
  await rowA.getByRole('button', { name: COPY.discard, exact: true }).click();
  await rowA.getByRole('button', { name: COPY.confirmDiscard }).click();
  await expect(draftRows(page)).toHaveCount(1);
  await expect(draftRows(page).first()).toContainText('Canon Yaounde v Tonnerre');
  expect(await storedWith(page, DRAFT_A.reasoning), 'the confirmed discard left A stored').toBe(0);
  expect(await storedWith(page, DRAFT_B.reasoning), 'discarding A removed B').toBe(1);

  // The composer's own "Start again" asks too, and "Keep it" keeps every word.
  await openComposer(page, B);
  await expectFields(page, DRAFT_B);
  await page.getByRole('button', { name: COPY.startAgain }).click();
  await expectFields(page, DRAFT_B);
  expect(await storedWith(page, DRAFT_B.reasoning)).toBe(1);
  await page.getByRole('button', { name: COPY.keep }).click();
  await expectFields(page, DRAFT_B);

  // The picker's list asks as well, and its confirmation removes the draft.
  await page.goto('/expert/predictions/create');
  const rowB = draftRow(page, 'Canon Yaounde');
  await rowB.getByRole('button', { name: COPY.discard, exact: true }).click();
  expect(await storedWith(page, DRAFT_B.reasoning)).toBe(1);
  await rowB.getByRole('button', { name: COPY.confirmDiscard }).click();
  await expect(draftRows(page)).toHaveCount(0);
  expect(await storedDrafts(page)).toEqual([]);

  expect(state.expertWrites, 'a discard sent a write to the expert API').toEqual([]);
});

/* ============================================================================ publish */

test("publishing B clears B's draft and keeps A's", async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);
  await openComposer(page, B);
  await typeDraft(page, DRAFT_B);

  await page.getByRole('button', { name: 'Publish', exact: true }).first().click();
  await expect.poll(() => state.created.length).toBe(1);
  await expect(page.getByRole('heading', { name: 'Published' })).toBeVisible();
  expect(state.created[0].match_id).toBe('fx-b');
  expect(state.created[0].home_win_prob as number).toBeCloseTo(0.4, 4);

  expect(await storedWith(page, DRAFT_B.reasoning), "B's draft outlived its publication").toBe(0);
  expect(await storedWith(page, DRAFT_A.reasoning), "publishing B removed A's draft").toBe(1);

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('draft-summary')).toHaveCount(1);
  await expect(page.getByTestId('draft-summary').first()).toContainText('Coton Sport v Union Douala');

  await openComposer(page, A);
  await expectFields(page, DRAFT_A);

  expect(state.expertWrites, 'the only expert write is the one publish')
    .toEqual(['POST /api/v1/expert/predictions/manual']);
});

/* ============================================================================ accounts */

test("another expert on this browser never sees the first one's draft", async ({ page }) => {
  const state = await openWorld(page, USER_X);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  // Sign in as Y in the same browser: /auth/me now answers Y, and the app boots as Y.
  await signIn(page, { user: expert(USER_Y) });
  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body'), 'the browser is not signed in as the second expert').toContainText('Ysolde');
  await expect(page.getByTestId('draft-summary')).toHaveCount(0);

  await openComposer(page, A);
  await expectFields(page, EMPTY);
  await expect(page.locator('body')).not.toContainText(DRAFT_A.reasoning);
  // The drafts list is Y's own. (On the old code this page restored Y's own EMPTY draft for A,
  // the empty-draft defect, so what is checked here is X's words and X's row, not A's name.)
  await page.goto('/expert/predictions/create');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).not.toContainText(DRAFT_A.reasoning);
  await expect(draftRow(page, 'Coton Sport'), "X's draft is listed for Y").toHaveCount(0);
  const restoredHome = page.locator('#composer-home');
  if (await restoredHome.count()) await expect(restoredHome).toHaveValue('');
  expect(await storedWith(page, DRAFT_A.reasoning), "Y's visit removed X's draft").toBe(1);

  // Back as X: the draft is there, intact.
  await signIn(page, { user: expert(USER_X) });
  await openComposer(page, A);
  await expectFields(page, DRAFT_A);

  expect(state.expertWrites).toEqual([]);
});

/* ============================================================================ the old store */

/** Seed the legacy v1 key ONCE per tab: a reload must show what the browser kept, not a re-seed. */
async function seedLegacyOnce(page: Page, payload: Json): Promise<void> {
  await page.addInitScript(([key, value]) => {
    if (window.sessionStorage.getItem('e2e.legacy-draft-seeded')) return;
    window.localStorage.setItem(key, value);
    window.sessionStorage.setItem('e2e.legacy-draft-seeded', '1');
  }, [LEGACY_KEY, JSON.stringify(payload)] as const);
}

const legacyValues = (reasoning: string, home = '60', draw = '25', away = '15'): Json => ({
  homeWin: home, draw, awayWin: away, conviction: '',
  bttsEnabled: false, bttsYes: '', bttsNo: '', bttsConviction: '',
  over25Enabled: false, over25: '', under25: '',
  over35Enabled: false, over35: '', under35: '',
  totalsConviction: '', reasoning,
});

const legacyKeyValue = (page: Page): Promise<string | null> =>
  page.evaluate(key => window.localStorage.getItem(key), LEGACY_KEY);

test('a legacy draft is moved to its fixture once, and kept', async ({ page }) => {
  const state = await openWorld(page);
  await seedLegacyOnce(page, {
    fixture: { id: 'fx-a', homeTeam: 'Coton Sport', awayTeam: 'Union Douala', competition: 'Elite One', kickoff: null },
    values: legacyValues('legacy words'),
    savedAt: new Date(Date.now() - 10 * 60_000).toISOString(),
  });

  await openComposer(page, A);
  await expectFields(page, { home: '60', draw: '25', away: '15', reasoning: 'legacy words' });
  await expect.poll(() => legacyKeyValue(page), { message: 'the legacy key was not retired' }).toBeNull();
  expect(await storedWith(page, 'legacy words'), 'the legacy draft is stored once').toBe(1);

  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, { home: '60', draw: '25', away: '15', reasoning: 'legacy words' });
  expect(await storedWith(page, 'legacy words'), 'a reload duplicated the migrated draft').toBe(1);

  // Opening another fixture leaves the migrated draft alone.
  await openThroughMatchSelection(page, B);
  await expectFields(page, EMPTY);
  expect(await storedWith(page, 'legacy words')).toBe(1);

  expect(state.expertWrites).toEqual([]);
});

test('an empty legacy draft is dropped rather than offered', async ({ page }) => {
  await openWorld(page);
  await seedLegacyOnce(page, {
    fixture: { id: 'fx-b', homeTeam: 'Canon Yaounde', awayTeam: 'Tonnerre', competition: 'Elite One', kickoff: null },
    values: legacyValues('', '', '', ''),
    savedAt: new Date(Date.now() - 10 * 60_000).toISOString(),
  });

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('draft-summary'), 'an empty draft was offered').toHaveCount(0);
  await expect.poll(() => legacyKeyValue(page)).toBeNull();
  expect(await storedDrafts(page)).toEqual([]);
});

test('a legacy draft with no fixture is listed as such, and moves to the fixture chosen for it', async ({ page }) => {
  const state = await openWorld(page);
  await seedLegacyOnce(page, {
    fixture: null,
    values: legacyValues('unassigned words'),
    savedAt: new Date(Date.now() - 10 * 60_000).toISOString(),
  });

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(draftRows(page)).toHaveCount(1);
  await expect(draftRows(page).first()).toContainText(COPY.noFixture);

  await page.goto('/expert/predictions/create');
  await expect(page.getByRole('heading', { name: COPY.listTitle })).toBeVisible();
  await draftRow(page, COPY.noFixture).getByRole('button', { name: COPY.continue, exact: true }).click();
  await rowButton(page, B).click();
  await expect(page).toHaveURL(/[?&]matchId=fx-b(&|$)/);
  await expectFields(page, { home: '60', draw: '25', away: '15', reasoning: 'unassigned words' });

  await page.reload();
  await expect(page.locator('#composer-home')).toBeVisible();
  await expectFields(page, { home: '60', draw: '25', away: '15', reasoning: 'unassigned words' });
  expect(await storedWith(page, 'unassigned words'), 'the draft was copied rather than moved').toBe(1);

  await page.goto('/expert/predictions/create');
  await expect(draftRows(page)).toHaveCount(1);
  await expect(draftRows(page).first()).toContainText('Canon Yaounde v Tonnerre');

  expect(state.expertWrites).toEqual([]);
});

test('a draft with no fixture never replaces a draft the chosen fixture already has', async ({ page }) => {
  const state = await openWorld(page);
  await seedLegacyOnce(page, {
    fixture: null,
    values: legacyValues('unassigned words'),
    savedAt: new Date(Date.now() - 10 * 60_000).toISOString(),
  });

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  await page.goto('/expert/predictions/create');
  await expect(draftRows(page)).toHaveCount(2);
  await draftRow(page, COPY.noFixture).getByRole('button', { name: COPY.continue, exact: true }).click();
  await rowButton(page, A).click();
  await expect(page).toHaveURL(/[?&]matchId=fx-a(&|$)/);
  // A's own draft is what opens, and the expert is told why.
  await expectFields(page, DRAFT_A);
  await expect(page.locator('body')).toContainText('You already had a draft for Coton Sport v Union Douala');
  expect(await storedWith(page, 'unassigned words'), 'the draft without a fixture was lost').toBe(1);
  expect(await storedWith(page, DRAFT_A.reasoning)).toBe(1);

  expect(state.expertWrites).toEqual([]);
});

/* ============================================================================ retention */

test('a draft whose fixture kicked off is kept, and says it can no longer be published as prematch', async ({ page }) => {
  const state = await openWorld(page);

  await openComposer(page, KICKED_OFF);
  await typeDraft(page, { ...DRAFT_A, reasoning: 'kicked-off words' });
  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  for (let visit = 0; visit < 2; visit += 1) {
    await page.goto('/expert/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(draftRows(page), 'a draft was pruned on its own').toHaveCount(2);
    await expect(draftRow(page, 'Fovu Baham')).toContainText(COPY.kickedOff);
    await expect(draftRow(page, 'Coton Sport')).not.toContainText(COPY.kickedOff);
  }
  expect(await storedWith(page, 'kicked-off words')).toBe(1);

  await page.goto('/expert/predictions/create');
  await expect(draftRow(page, 'Fovu Baham')).toContainText(COPY.kickedOff);

  expect(state.expertWrites).toEqual([]);
});

test('a browser that refuses to store the draft says so, and the words stay on the page', async ({ page }) => {
  const state = await openWorld(page);
  await page.addInitScript((prefix) => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function setItem(this: Storage, key: string, value: string) {
      if (String(key).startsWith(prefix)) {
        throw new DOMException('The quota has been exceeded.', 'QuotaExceededError');
      }
      return original.call(this, key, value);
    };
  }, DRAFT_PREFIX);

  await openComposer(page, A);
  await page.locator('#composer-home').fill(DRAFT_A.home);
  await page.locator('#composer-reasoning').fill(DRAFT_A.reasoning);
  await expect(page.locator('body')).toContainText(COPY.saveFailed);
  await expect(page.locator('#composer-reasoning')).toHaveValue(DRAFT_A.reasoning);
  expect(await storedDrafts(page)).toEqual([]);

  expect(state.expertWrites).toEqual([]);
});

/**
 * THE CAP, WHITE-BOX ON PURPOSE. Fifty drafts cannot reasonably be typed, so this one test seeds
 * them in the v2 shape the store writes (`expert.composer.draft.v2.<user>.<fixture>`). It pins the
 * decision: at most fifty per expert, and the only drafts ever evicted are the OLDEST-SAVED of
 * those whose fixture kicked off more than seven days ago. A draft inside that grace, a draft
 * with no known kickoff and a draft for a future fixture are never evicted, however old.
 */
test('over fifty drafts, only the oldest whose fixture kicked off over a week ago is evicted', async ({ page }) => {
  const state = await openWorld(page);
  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');

  await page.evaluate(({ user, day }) => {
    const iso = (offsetMs: number) => new Date(Date.now() + offsetMs).toISOString();
    const values = (reasoning: string) => ({
      homeWin: '50', draw: '30', awayWin: '20', conviction: '',
      bttsEnabled: false, bttsYes: '', bttsNo: '', bttsConviction: '',
      over25Enabled: false, over25: '', under25: '',
      over35Enabled: false, over35: '', under35: '',
      totalsConviction: '', reasoning,
    });
    const put = (id: string, kickoffUtc: string | null, savedAt: string) => {
      window.localStorage.setItem(`expert.composer.draft.v2.${user}.${id}`, JSON.stringify({
        v: 2,
        fixture: { id, homeTeam: `Home ${id}`, awayTeam: `Away ${id}`, competition: 'Elite One', kickoff: null, kickoffUtc },
        values: values(`words for ${id}`),
        savedAt,
      }));
    };
    put('old-1', iso(-30 * day), iso(-100 * day));
    put('old-2', iso(-20 * day), iso(-90 * day));
    put('old-3', iso(-10 * day), iso(-80 * day));
    put('recent-ko', iso(-2 * day), iso(-200 * day));
    put('unknown-ko', null, iso(-150 * day));
    for (let n = 1; n <= 45; n += 1) put(`future-${n}`, iso(5 * day), iso(-n * 3_600_000));
  }, { user: USER_X, day: DAY_MS });
  expect((await storedDrafts(page)).length).toBe(50);

  await openComposer(page, A);
  await typeDraft(page, DRAFT_A);

  const ids = async () => (await storedDrafts(page))
    .map(value => (JSON.parse(value) as { fixture?: { id?: string } }).fixture?.id ?? '?');
  await expect.poll(async () => (await ids()).length).toBe(50);
  const kept = await ids();
  expect(kept, 'the oldest-saved draft past the grace was not the one evicted').not.toContain('old-1');
  for (const id of ['fx-a', 'old-2', 'old-3', 'recent-ko', 'unknown-ko', 'future-1', 'future-45']) {
    expect(kept, `${id} was evicted`).toContain(id);
  }

  // The dashboard shows the newest three and links to the rest.
  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(draftRows(page)).toHaveCount(3);
  await expect(page.getByTestId('draft-summary').first()).toContainText('Coton Sport v Union Douala');
  const seeAll = page.getByRole('link', { name: COPY.seeAll });
  await expect(seeAll).toHaveAttribute('href', '/expert/predictions/create');

  expect(state.expertWrites).toEqual([]);
});
