import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, Json, dayPayload, fixtureAt, registerAuthHandler, stubBackend,
} from '../support/api-stub';

/**
 * A SAVED FIXTURE FROM KICK-OFF TO FULL TIME, WITH THE TAB NEVER LEAVING THE FRONT.
 *
 * The defect. `syncLivePoll()` in src/services/favourites.service.ts started its interval only
 * when `savedMatches.live.length > 0`. A fixture that is still upcoming leaves that bucket empty,
 * so no interval ran, so nothing ever noticed the kick-off: the poll that would have discovered
 * the transition was gated on the state it would have discovered. Nothing else re-reads while the
 * tab stays in front — the focus refresh only fires on the way BACK — so a reader watching the
 * page saw "Coming up" until they alt-tabbed away and returned, or reloaded by hand.
 *
 * WHERE THE TRANSITION COMES FROM, AND WHY IT COSTS NO ALLOWANCE. `GET /api/v1/me/favourites`
 * buckets purely on the stored `match.status` (backend/app/api/v1/endpoints/favourites.py,
 * `_saved_matches`: LIVE, FINISHED, everything else). Those rows are updated centrally by the
 * backend's scheduler — `SYNC_LIVE_INTERVAL_SECONDS` is 120 — and never by a visitor's request.
 * So the whole upcoming → live → finished journey is observable from stored data, and a reader
 * watching it spends no provider request at all.
 *
 * BOTH TESTS HERE ARE MOCKED-ONLY, and the names say so. Each one needs a fixture to kick off and
 * finish on demand: against the real backend that means waiting for a real match to start, which
 * is neither available to order nor repeatable. The live suite can prove the buckets and the
 * spend; it cannot witness a kick-off.
 *
 * WHAT THE CLOCK IS FOR. `page.clock` moves the BROWSER's clock, not the data: every status change
 * below is made on the stub server first, exactly as the scheduler would make it in the database,
 * and the clock only decides when the application next looks. Nothing here fabricates a live match
 * — it fabricates a stub backend, which is what the whole mocked project is.
 *
 * COST. Every /api/v1 route is intercepted, so nothing reaches the network and no provider request
 * is possible. `refresh=true` is never sent by anything this file drives.
 */

/* ------------------------------------------------------------------------------- the reader */

const READER: Json = {
  user_id: '00000000-0000-4000-8000-0000000000d1',
  email: 'qa.lifecycle@predictions-local.dev',
  full_name: 'QA Lifecycle',
  role: 'regular',
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
};

/**
 * Opaque strings that never leave the browser context. The stub accepts anything and no real
 * backend is contacted, so these are not credentials and unlock nothing.
 */
const ACCESS_TOKEN = 'e2e-lifecycle-access-token';
const REFRESH_TOKEN = 'e2e-lifecycle-refresh-token';

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

/** Mirrors PREFERENCES_KEY_PREFIX in src/services/favourites.service.ts. */
const PREFERENCES_KEY = `personal.preferences.v1.${READER.user_id as string}`;

/* --------------------------------------------------------------------------------- the clock */

/**
 * Where the browser's clock starts. A fixed instant so the fixture's kick-off can be placed a
 * known distance from it and the assertions do not depend on the hour the suite is run.
 */
const START = new Date('2026-09-19T18:00:00Z');

/** How far ahead of the start the saved fixture kicks off. */
const KICKOFF_IN_MS = 3 * 60 * 1000;

const HOME = 'Fenchurch Rangers';
const AWAY = 'Deptford Albion';

/* -------------------------------------------------------------------------- the stubbed world */

interface SavedRow {
  match: ApiMatch;
  savedAt: string;
}

/**
 * The stand-in for the signed-in half of the backend, plus the one thing the scheduler does to it.
 */
class World {
  signedIn = false;

  saved = new Map<string, SavedRow>();

  /** Every `GET /api/v1/me/favourites` the application issued. */
  favouriteReads = 0;

  save(match: ApiMatch): void {
    this.saved.set(match.id, { match, savedAt: START.toISOString() });
  }

  /**
   * What the backend's scheduler does to a stored fixture, and the only thing that moves a saved
   * match between the buckets. No provider is involved on this path in the real system either.
   */
  schedulerMoves(matchId: string, patch: Partial<ApiMatch>): void {
    const row = this.saved.get(matchId);
    if (!row) throw new Error(`the stub holds no saved match ${matchId}`);
    row.match = { ...row.match, ...patch };
  }
}

const savedEntry = (row: SavedRow): Json => ({
  match_id: row.match.id,
  note: null,
  saved_at: row.savedAt,
  updated_at: row.savedAt,
  match: row.match,
});

/** `GET /api/v1/me/saved-matches`, bucketed by stored status exactly as the backend buckets it. */
function savedMatchesPayload(world: World): Json {
  const rows = Array.from(world.saved.values());
  const live = rows.filter(row => row.match.status === 'live' || row.match.status === 'halftime');
  const finished = rows.filter(row => row.match.status === 'finished');
  const upcoming = rows.filter(row => !live.includes(row) && !finished.includes(row));
  return {
    upcoming: upcoming.map(savedEntry),
    live: live.map(savedEntry),
    finished: finished.map(savedEntry),
    counts: {
      upcoming: upcoming.length,
      live: live.length,
      finished: finished.length,
      total: rows.length,
    },
  };
}

function favouritesPayload(world: World): Json {
  return {
    teams: [],
    leagues: [],
    team_ids: [],
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: savedMatchesPayload(world),
    limits: { teams: 10, leagues: 5 },
  };
}

async function stubAuth(page: Page, world: World): Promise<void> {
  const handler = (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    if (path === '/me') {
      return world.signedIn ? json(READER) : json({ detail: 'Not authenticated' }, 401);
    }
    if (path === '/login' || path === '/register') {
      world.signedIn = true;
      return json({
        access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer', user: READER,
      });
    }
    if (path === '/logout') {
      world.signedIn = false;
      return json({ message: 'Logged out successfully' });
    }
    if (path === '/refresh') {
      return world.signedIn
        ? json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' })
        : json({ detail: 'Invalid refresh token' }, 401);
    }
    return json({ detail: 'Not found' }, 404);
  };
  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);
}

/** Registered AFTER stubBackend so Playwright reaches it first. */
async function stubAccount(page: Page, world: World): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/me/, '');
    if (path === '/favourites') world.favouriteReads += 1;
    if (!world.signedIn) return json(route, { detail: 'Not authenticated' }, 401);
    if (path === '/favourites') return json(route, favouritesPayload(world));
    if (path === '/saved-matches') return json(route, savedMatchesPayload(world));
    return json(route, {});
  });
}

interface StartOptions {
  /** Seed the reader's stored preferences. Omitted leaves them at their defaults. */
  liveUpdates?: boolean;
}

async function startSignedIn(page: Page, world: World, options: StartOptions = {}): Promise<void> {
  world.signedIn = true;
  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCESS_TOKEN, REFRESH_TOKEN]);

  if (options.liveUpdates !== undefined) {
    await page.addInitScript(([key, value]) => {
      window.localStorage.setItem(key, value);
    }, [PREFERENCES_KEY, JSON.stringify({
      forecasts: true, prompts: true, liveUpdates: options.liveUpdates, paused: false,
    })]);
  }
}

/** Everything a lifecycle test needs stubbed, in the order the interceptors must be registered. */
async function stubWorld(page: Page, world: World): Promise<void> {
  await stubBackend(page, { day: iso => dayPayload(iso, []) });
  await stubAuth(page, world);
  await stubAccount(page, world);
}

/* ------------------------------------------------------------------------------ small helpers */

/** The saved fixture's row in the dashboard feed. */
const savedRow = (page: Page, matchId: string) =>
  page.locator(`[data-testid="saved-match"][data-match-id="${matchId}"]`);

/**
 * Come back to this tab. Used ONLY where a test is about the reader returning; the lifecycle
 * assertions below deliberately never call it, because the whole point is a tab that stays put.
 */
async function returnToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

/* ------------------------------------------------------------------- upcoming → live → finished */

test('MOCKED-ONLY: a saved fixture goes from upcoming to in play to finished while the tab stays in front', async ({ page }) => {
  const world = new World();
  const fixture = fixtureAt(new Date(START.getTime() + KICKOFF_IN_MS).toISOString(), HOME, AWAY);
  world.save(fixture);

  await page.clock.install({ time: START });
  // Let the application run at its own speed; the clock is only JUMPED, never stopped. A paused
  // clock would also freeze the things this test is not about, and prove less.
  await page.clock.resume();
  await stubWorld(page, world);
  await startSignedIn(page, world);

  await page.goto('/dashboard');
  const row = savedRow(page, fixture.id);
  await expect(row, 'the saved fixture is on the dashboard before kick-off').toBeVisible();
  await expect(row).toHaveAttribute('data-feed-phase', 'upcoming');
  await expect(page.getByTestId('feed-group-upcoming')).toBeVisible();

  /*
   * KICK-OFF. The scheduler has moved the stored row on, exactly as it does every two minutes
   * while a covered match is in its live window; the browser's clock passes the kick-off. The tab
   * is not touched: no focus event, no visibility change, no reload.
   */
  world.schedulerMoves(fixture.id, { status: 'live', minute: '12', score: { home: 0, away: 0 } });
  await page.clock.fastForward(KICKOFF_IN_MS + 2 * 60 * 1000);

  await expect(row, 'a saved fixture whose kick-off has passed must be noticed without the reader doing anything')
    .toHaveAttribute('data-feed-phase', 'live', { timeout: 20_000 });
  await expect(page.getByTestId('feed-group-live')).toBeVisible();
  await expect(page.getByTestId('feed-live-not-updating'),
    'automatic updates are on, so the page must not claim these scores are frozen').toHaveCount(0);

  /* FULL TIME. Same again: the stored row moves, and the page follows it on its own. */
  world.schedulerMoves(fixture.id, { status: 'finished', minute: null, score: { home: 2, away: 1 } });
  await page.clock.fastForward(3 * 60 * 1000);

  await expect(row, 'and full time must be noticed the same way')
    .toHaveAttribute('data-feed-phase', 'result', { timeout: 20_000 });
  await expect(page.getByTestId('feed-group-result')).toBeVisible();
  await expect(row).toContainText('2');
  await expect(row).toContainText('1');
  // The row moved out of the in-play group rather than being shown twice.
  await expect(page.getByTestId('feed-group-live')).toHaveCount(0);
});

/* ------------------------------------------------------- the reader who switched updates off */

test('MOCKED-ONLY: with automatic updates off, a saved fixture due to kick off is not polled', async ({ page }) => {
  const world = new World();
  const fixture = fixtureAt(new Date(START.getTime() + KICKOFF_IN_MS).toISOString(), HOME, AWAY);
  world.save(fixture);

  await page.clock.install({ time: START });
  await page.clock.resume();
  await stubWorld(page, world);
  await startSignedIn(page, world, { liveUpdates: false });

  await page.goto('/dashboard');
  const row = savedRow(page, fixture.id);
  await expect(row).toHaveAttribute('data-feed-phase', 'upcoming');
  const readsBefore = world.favouriteReads;

  // The fixture kicks off, and the reader has told us not to re-read anything by ourselves.
  world.schedulerMoves(fixture.id, { status: 'live', minute: '12', score: { home: 0, away: 0 } });
  await page.clock.fastForward(KICKOFF_IN_MS + 5 * 60 * 1000);
  await page.waitForTimeout(1_000);

  expect(world.favouriteReads,
    'a reader who turned automatic updates off must not be polled, kick-off or no kick-off')
    .toBe(readsBefore);
  await expect(row, 'and the page must still be showing what it last really read')
    .toHaveAttribute('data-feed-phase', 'upcoming');

  /*
   * And this is not vacuous: the new state was there to be found the whole time. Coming back to
   * the tab is the reader asking, not us polling, so it still refreshes — and the page then says
   * plainly that these scores are not updating themselves.
   */
  await returnToTheTab(page);
  await expect(row).toHaveAttribute('data-feed-phase', 'live', { timeout: 20_000 });
  expect(world.favouriteReads).toBeGreaterThan(readsBefore);
  await expect(page.getByTestId('feed-live-not-updating'),
    'with automatic updates off, a row headed "In play now" has to say the scores are frozen')
    .toBeVisible();
});
