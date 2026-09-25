import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { apiContext, ensureQaExpertToken, QA_EXPERT } from '../support/qa-account';
import { expectNothingSpentBesidesTheScheduler, providerSpend } from '../support/provider-spend';

/**
 * Coming BACK: the half of the journey that begins after the reader has already been here once.
 *
 * A reviewer found that match browsing worked and the journeys did not complete. The save journey
 * is covered by save-journey.spec.ts; this file covers what happens afterwards — whether the
 * dashboard is worth returning to, and whether what it shows is still true an hour later.
 *
 *   1. a saved match is in the feed, and once it has been played the feed carries its result;
 *   2. a followed team's fixtures are in the feed too, labelled with the follow that brought them;
 *   3. an empty feed says what is actually empty, and never invents an emptiness it did not check;
 *   4. coming back to the tab re-reads the data, and spends no provider request doing it.
 *
 * WHY THIS IS A LIVE SPEC. Case 4 is the interesting one and it cannot be stubbed: it asserts that
 * a change made OUTSIDE the browser shows up inside it after a real tab switch, and that the
 * provider's own counters did not move while that happened. A stub would prove neither half.
 *
 * COST AND CLEANLINESS
 *  - Every read is of data the local database already holds. Nothing here sends `refresh=true`,
 *    so no provider request is issued and no allowance is spent — and case 4 asserts exactly that
 *    against the live budget counters rather than trusting it.
 *  - The only rows written are saved-match and follow rows on the QA account the suite already
 *    creates. `afterEach` removes every one of them.
 */

/** The fields of a fixture payload this spec reads. */
interface JourneyFixture {
  id: string;
  kickoff_utc: string;
  status: string;
  competition: { id: string; name: string };
  home: { id: string; name: string };
  away: { id: string; name: string };
  score?: { home?: number | null; away?: number | null };
}

/** Rows this spec created, removed after each test so a rerun starts from the same place. */
const savedInThisTest = new Set<string>();
const followedTeams = new Set<string>();
const followedLeagues = new Set<string>();
let token = '';

async function qaToken(api: APIRequestContext): Promise<string> {
  if (!token) token = await ensureQaExpertToken(api);
  return token;
}

const auth = (bearer: string) => ({ headers: { Authorization: `Bearer ${bearer}` } });

/**
 * Skip rather than assert against data that is not in this database, and narrow the type while we
 * are at it. `test.skip` throws when the condition holds, so nothing past it runs with a null.
 */
function required<T>(value: T | null, reason: string): T {
  test.skip(value === null, reason);
  return value as T;
}

function dayOffsetUtc(offset: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

async function fixturesOn(api: APIRequestContext, day: string): Promise<JourneyFixture[]> {
  // refresh=false keeps this a database read: no provider request is made
  const response = await api.get(`/api/v1/matches?date=${day}&refresh=false`);
  if (!response.ok()) return [];
  return ((await response.json()).matches || []) as JourneyFixture[];
}

/** A played fixture carrying a result, or null. Never invented: the test skips instead. */
async function finishedFixture(api: APIRequestContext): Promise<JourneyFixture | null> {
  for (let offset = 0; offset < 4; offset += 1) {
    const match = (await fixturesOn(api, dayOffsetUtc(-offset)))
      .find(entry => entry.status === 'finished' && typeof entry.score?.home === 'number');
    if (match) return match;
  }
  return null;
}

/**
 * A scheduled fixture inside the feed's own window, or null.
 *
 * The window matters: FEED_DAYS_AHEAD in src/services/favourites.service.ts is 7, and a fixture
 * beyond it is deliberately NOT in the feed. Looking further than the feed reaches would produce
 * a test that fails for the one reason that is not a defect.
 */
async function upcomingFixture(api: APIRequestContext): Promise<JourneyFixture | null> {
  for (let offset = 0; offset < 7; offset += 1) {
    const match = (await fixturesOn(api, dayOffsetUtc(offset))).find(entry => entry.status === 'scheduled');
    if (match) return match;
  }
  return null;
}

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

async function saveMatch(api: APIRequestContext, bearer: string, matchId: string): Promise<void> {
  const response = await api.put(`/api/v1/me/saved-matches/${matchId}`, { ...auth(bearer), data: {} });
  expect(response.ok(), 'the QA account could not save a match through the API').toBeTruthy();
  savedInThisTest.add(matchId);
}

async function followTeam(api: APIRequestContext, bearer: string, teamId: string): Promise<void> {
  const response = await api.put(`/api/v1/me/favourites/teams/${teamId}`, auth(bearer));
  expect(response.ok(), 'the QA account could not follow a team through the API').toBeTruthy();
  followedTeams.add(teamId);
}

/**
 * Leave the QA account holding nothing.
 *
 * Used by the empty-feed case, which is only meaningful against an account with no saves and no
 * follows. Everything it deletes is a row this suite created: the QA expert exists only for these
 * tests, is created by them, and holds nothing else.
 */
async function clearQaFavourites(api: APIRequestContext, bearer: string): Promise<void> {
  const response = await api.get('/api/v1/me/favourites', auth(bearer));
  if (!response.ok()) return;
  const body = await response.json();
  for (const id of body.team_ids ?? []) await api.delete(`/api/v1/me/favourites/teams/${id}`, auth(bearer));
  for (const id of body.league_ids ?? []) await api.delete(`/api/v1/me/favourites/leagues/${id}`, auth(bearer));
  const saved = body.saved_matches ?? {};
  for (const bucket of ['upcoming', 'live', 'finished']) {
    for (const entry of saved[bucket] ?? []) {
      await api.delete(`/api/v1/me/saved-matches/${entry.match_id}`, auth(bearer));
    }
  }
}

/** The row for one fixture in the feed, saved or reached through a follow. */
const feedRow = (page: Page, fixture: JourneyFixture) =>
  page.locator('[data-testid="saved-match"], [data-testid="feed-match"]')
    .filter({ hasText: fixture.home.name });

/** A team's own goals, as the fixture row renders them: the name and then the number. */
function scoreBeside(team: string, goals: number): RegExp {
  return new RegExp(`${team.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*${goals}(?!\\d)`);
}

test.afterEach(async () => {
  if (savedInThisTest.size === 0 && followedTeams.size === 0 && followedLeagues.size === 0) return;
  const api = await apiContext();
  const bearer = await qaToken(api);
  for (const matchId of savedInThisTest) await api.delete(`/api/v1/me/saved-matches/${matchId}`, auth(bearer));
  for (const teamId of followedTeams) await api.delete(`/api/v1/me/favourites/teams/${teamId}`, auth(bearer));
  for (const leagueId of followedLeagues) await api.delete(`/api/v1/me/favourites/leagues/${leagueId}`, auth(bearer));
  savedInThisTest.clear();
  followedTeams.clear();
  followedLeagues.clear();
  await api.dispose();
});

test('a saved match that has been played shows its result in the feed', async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  // Never faked: with no played fixture in the local database there is nothing to assert about.
  const fixture = required(await finishedFixture(api), 'no finished fixture carrying a result in the local database');
  const score = fixture.score as { home: number; away: number };

  await saveMatch(api, bearer, fixture.id);
  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // In the feed exactly once, and in the results group rather than among what is still to come.
  const row = page.locator('[data-testid="saved-match"]').filter({ hasText: fixture.home.name });
  await expect(row).toHaveCount(1);
  await expect(page.getByTestId('feed-group-result').locator('[data-testid="saved-match"]')
    .filter({ hasText: fixture.home.name })).toHaveCount(1);

  // The result itself, beside the team it belongs to, from the payload. A bare toContainText('0')
  // would pass on any percentage on the row, which is not the same claim at all.
  await expect(row).toContainText('FT');
  await expect(row).toContainText(scoreBeside(fixture.home.name, score.home));
  await expect(row).toContainText(scoreBeside(fixture.away.name, score.away));
  // And the row says why it is in the feed, so a reader can tell a save from a follow.
  await expect(row.getByTestId('feed-reasons')).toContainText('Saved');
  await api.dispose();
});

test('the results group is reachable from the top of the feed without scrolling for it', async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  const fixture = required(await finishedFixture(api), 'no finished fixture carrying a result in the local database');

  await saveMatch(api, bearer, fixture.id);
  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // The jump link is the short path the reviewer asked for: one control, at the top, that names
  // how many results there are and goes to them.
  const jump = page.getByTestId('feed-jump-result');
  await expect(jump).toBeVisible();
  await expect(jump).toContainText(/result/i);
  await jump.click();
  await expect(page.getByTestId('feed-group-result')).toBeVisible();
  await api.dispose();
});

test("a followed team's upcoming fixtures appear in the feed, labelled with the follow", async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  const fixture = required(
    await upcomingFixture(api),
    `no scheduled fixture in the local database within the feed's window`,
  );

  await followTeam(api, bearer, fixture.home.id);
  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // Not saved — reached purely through the follow — so it carries the other testid.
  const row = page.getByTestId('feed-group-upcoming').locator('[data-testid="feed-match"]')
    .filter({ hasText: fixture.home.name })
    .filter({ hasText: fixture.away.name });
  await expect(row.first()).toBeVisible();
  await expect(row.first().getByTestId('feed-reasons')).toContainText(fixture.home.name);

  // And the follow itself now says what that team plays next, instead of being a bare link.
  const followed = page.getByTestId('followed-team').filter({ hasText: fixture.home.name });
  await expect(followed.first().getByTestId('follow-fixture-line')).toBeVisible();
  await api.dispose();
});

test('unfollowing a team on the dashboard takes its fixtures out of the feed at once', async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  const fixture = required(
    await upcomingFixture(api),
    `no scheduled fixture in the local database within the feed's window`,
  );

  await followTeam(api, bearer, fixture.home.id);
  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const row = page.getByTestId('feed-group-upcoming').locator('[data-testid="feed-match"]')
    .filter({ hasText: fixture.home.name });
  await expect(row.first()).toBeVisible();

  // The follow and the feed are one store, so the feed has to follow the change without a reload.
  // Before this they were two unrelated reads and the feed would have kept the fixtures of a team
  // the reader had just stopped following until they refreshed the page.
  await page.getByTestId('followed-team').filter({ hasText: fixture.home.name })
    .first().getByRole('button').click();
  await expect(row).toHaveCount(0, { timeout: 15_000 });
  await api.dispose();
});

test('an account with nothing saved and nothing followed gets an honest empty feed', async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  await clearQaFavourites(api, bearer);

  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const empty = page.getByTestId('saved-matches-empty');
  await expect(empty).toBeVisible();
  // It states what is empty and what to do, and claims nothing about the world: "no matches
  // today" after an unchecked question is the mistake this whole suite exists to prevent.
  await expect(empty).toContainText(/nothing in your feed/i);
  await expect(empty).toHaveAttribute('data-tone', 'empty');
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);

  // Nothing is fabricated to fill the space.
  const text = (await page.locator('body').innerText()).toLowerCase();
  expect(text).not.toContain('nan');
  expect(text).not.toContain('undefined');
  await api.dispose();
});

test('coming back to the tab picks up a change made elsewhere, and spends no provider request', async ({ page }) => {
  const api = await apiContext();
  const bearer = await qaToken(api);
  const fixture = required(await upcomingFixture(api), `no scheduled fixture in the local database within the feed's window`);
  await clearQaFavourites(api, bearer);

  await signInThroughTheForm(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();

  const before = await providerSpend(api);
  let favouriteReads = 0;
  page.on('request', request => {
    if (request.url().includes('/api/v1/me/favourites')) favouriteReads += 1;
  });

  // The change happens OUTSIDE this tab — another device, another window, the phone in a pocket.
  // Nothing in the page knows about it, which is the situation the refresh exists for.
  await saveMatch(api, bearer, fixture.id);
  await expect(feedRow(page, fixture)).toHaveCount(0);

  // Past FOCUS_REFRESH_MIN_AGE_MS (5s in src/services/favourites.service.ts), which exists to
  // collapse the focus/visibilitychange pair into one request rather than to ration them.
  await page.waitForTimeout(6_000);
  expect(favouriteReads, 'a tab nobody came back to must not be polling').toBe(0);

  /*
   * THE TAB SWITCH IS SYNTHESISED, AND HERE IS WHY.
   *
   * Headless Chromium never blurs or hides a page. Measured against this stack before writing
   * this test: opening a second page in the same context, calling `bringToFront()` on it and then
   * on this one leaves this page reporting `visibilityState: "visible"` and
   * `document.hasFocus() === true` throughout, and fires neither `focus` nor `visibilitychange`.
   * No CDP command reaches it either — `Emulation.setPageVisibility` does not exist in this
   * protocol version, and `Page.setWebLifecycleState` changes nothing the document can observe.
   *
   * So the test dispatches the exact pair of events a browser sends on the way back, in the order
   * it sends them. Only the trigger is synthetic: the age guard, the request, the store, the
   * merge and the render are all the application's own, and breaking any of them fails this test.
   */
  await page.evaluate(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
  });

  await expect(feedRow(page, fixture)).toHaveCount(1, { timeout: 15_000 });
  // Both events, one request: the guard coalesces the pair instead of asking twice.
  expect(favouriteReads, 'the focus/visibilitychange pair must collapse into one read').toBe(1);

  // The whole constraint in one assertion: not one provider request was spent getting there.
  // The scheduler's own requests in the same window are subtracted exactly, not hoped absent.
  expectNothingSpentBesidesTheScheduler(before, await providerSpend(api),
    'coming back to the tab spent a provider request');
  await api.dispose();
});

test.describe('on a 390px phone', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('the feed fits the screen and scrolls only downwards', async ({ page }) => {
    const api = await apiContext();
    const bearer = await qaToken(api);
    const fixture = required(await upcomingFixture(api), `no scheduled fixture in the local database within the feed's window`);
    await followTeam(api, bearer, fixture.home.id);

    await signInThroughTheForm(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    await expect(page.getByTestId('feed-summary')).toBeVisible();
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    // One pixel of slack for sub-pixel rounding; anything more is a sideways scroll.
    expect(overflow).toBeLessThanOrEqual(1);
    await api.dispose();
  });
});
