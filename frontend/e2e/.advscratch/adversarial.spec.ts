import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, Json, baseMatches, dayPayload, fixtureAt, registerAuthHandler, stubBackend,
} from '../support/api-stub';

// Adversarial verification of the favourites-races package. Scratch file, mocked only.

interface Person extends Json {
  user_id: string; email: string; full_name: string; role: 'regular';
  is_active: boolean; is_verified: boolean; created_at: string; updated_at: string;
}
const person = (suffix: string, name: string): Person => ({
  user_id: `00000000-0000-4000-8000-0000000000${suffix}`,
  email: `qa.${name}@predictions-local.dev`,
  full_name: `QA ${name}`,
  role: 'regular', is_active: true, is_verified: true,
  created_at: '2026-01-05T09:00:00Z', updated_at: '2026-01-05T09:00:00Z',
});
const FIRST = person('e1', 'AdvFirst');
const SECOND = person('e2', 'AdvSecond');

const ACCESS_TOKEN = 'adv-access';
const REFRESH_TOKEN = 'adv-refresh';

const FIXTURE_ONE = baseMatches()[0];
const FIXTURE_TWO = baseMatches().find(
  m => (m.home as ApiTeamRef).name !== (FIXTURE_ONE.home as ApiTeamRef).name,
) as ApiMatch;
const CLUB_ONE = (FIXTURE_ONE.home as ApiTeamRef).name;
const CLUB_TWO = (FIXTURE_TWO.home as ApiTeamRef).name;
const TEAM = FIXTURE_ONE.home as ApiTeamRef;
const FOCUS_GUARD_MS = 5_000;

interface SavedRow { match: ApiMatch; savedAt: string }

class Reader {
  saved = new Map<string, SavedRow>();
  teamIds: string[] = [];
  constructor(readonly person: Person) {}
  save(match: ApiMatch): void {
    const existing = this.saved.get(match.id);
    this.saved.set(match.id, { match, savedAt: existing?.savedAt ?? new Date().toISOString() });
  }
}

interface Hold { announce: () => void; released: Promise<number> }
interface HeldRead { arrived: Promise<void>; release: (status?: number) => void }

class World {
  readonly first = new Reader(FIRST);
  readonly second = new Reader(SECOND);
  signedIn: Reader | null = null;
  favouriteReads = 0;
  knownTeams: ApiTeamRef[] = [TEAM];
  private holds: Hold[] = [];
  arm(hold: Hold): void { this.holds.push(hold); }
  takeHold(): Hold | null { return this.holds.shift() ?? null; }
  readerFor(email: string): Reader | null {
    if (email === FIRST.email) return this.first;
    if (email === SECOND.email) return this.second;
    return null;
  }
}

function holdNextFavouritesRead(world: World): HeldRead {
  let announce!: () => void;
  const arrived = new Promise<void>(resolve => { announce = resolve; });
  let unlock!: (status: number) => void;
  const released = new Promise<number>(resolve => { unlock = resolve; });
  world.arm({ announce, released });
  return { arrived, release: (status = 200) => unlock(status) };
}

const savedEntry = (row: SavedRow): Json => ({
  match_id: row.match.id, note: null, saved_at: row.savedAt, updated_at: row.savedAt, match: row.match,
});

function savedMatchesPayload(reader: Reader): Json {
  const rows = Array.from(reader.saved.values());
  const live = rows.filter(r => r.match.status === 'live' || r.match.status === 'halftime');
  const finished = rows.filter(r => r.match.status === 'finished');
  const upcoming = rows.filter(r => !live.includes(r) && !finished.includes(r));
  return {
    upcoming: upcoming.map(savedEntry), live: live.map(savedEntry), finished: finished.map(savedEntry),
    counts: { upcoming: upcoming.length, live: live.length, finished: finished.length, total: rows.length },
  };
}

function favouritesPayload(world: World, reader: Reader): Json {
  return {
    teams: world.knownTeams.filter(t => reader.teamIds.includes(t.id)),
    leagues: [], team_ids: [...reader.teamIds], league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: savedMatchesPayload(reader),
    limits: { teams: 10, leagues: 5 },
  };
}

async function stubAuth(page: Page, world: World): Promise<void> {
  const handler = async (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    if (path === '/login' || path === '/register') {
      const body = (request.postDataJSON() ?? {}) as { email?: string };
      const reader = world.readerFor(body.email ?? '');
      if (!reader) return json({ detail: 'Incorrect email or password' }, 401);
      world.signedIn = reader;
      return json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer', user: reader.person });
    }
    if (path === '/logout') { world.signedIn = null; return json({ message: 'Logged out successfully' }); }
    if (path === '/me') {
      return world.signedIn ? json(world.signedIn.person) : json({ detail: 'Not authenticated' }, 401);
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

async function stubAccount(page: Page, world: World): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1\/me/, '');
    const method = request.method();
    if (path === '/favourites') world.favouriteReads += 1;
    const reader = world.signedIn;
    if (!reader) return json(route, { detail: 'Not authenticated' }, 401);

    if (path === '/favourites') {
      const body = favouritesPayload(world, reader);
      const hold = world.takeHold();
      if (hold) {
        hold.announce();
        const status = await hold.released;
        if (status !== 200) return json(route, { detail: 'Simulated upstream failure' }, status);
      }
      return json(route, body);
    }
    if (path === '/saved-matches') return json(route, savedMatchesPayload(reader));

    const savedMatch = /^\/saved-matches\/(.+)$/.exec(path);
    if (savedMatch) {
      const matchId = decodeURIComponent(savedMatch[1]);
      if (method === 'PUT') {
        const known = baseMatches().find(m => m.id === matchId);
        if (!known) return json(route, { detail: 'Match not found' }, 404);
        const created = !reader.saved.has(matchId);
        reader.save(known);
        return json(route, { ...savedEntry(reader.saved.get(matchId) as SavedRow), created });
      }
      if (method === 'DELETE') {
        const removed = reader.saved.delete(matchId);
        return json(route, { match_id: matchId, removed });
      }
    }
    const follow = /^\/favourites\/(teams|leagues)\/(.+)$/.exec(path);
    if (follow) {
      const id = decodeURIComponent(follow[2]);
      const following = method === 'PUT';
      const before = [...reader.teamIds];
      reader.teamIds = following
        ? (before.includes(id) ? before : [...before, id])
        : before.filter(e => e !== id);
      return json(route, {
        kind: follow[1] === 'teams' ? 'team' : 'league', id, following,
        changed: before.length !== reader.teamIds.length, ids: [...reader.teamIds], limit: 10,
      });
    }
    return json(route, {});
  });

  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, async (route: Route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    const team = world.knownTeams.find(e => e.id === id) ?? null;
    if (!team) return json(route, { detail: 'Team not found' }, 404);
    return json(route, { team, upcoming: [], recent: [] });
  });
}

async function stubWorld(page: Page, world: World, day?: (iso: string) => Json): Promise<void> {
  await stubBackend(page, { day: day ?? (iso => dayPayload(iso)) });
  await stubAuth(page, world);
  await stubAccount(page, world);
}

async function startSignedIn(page: Page, world: World, reader: Reader, prefs?: Json): Promise<void> {
  world.signedIn = reader;
  await page.addInitScript(([ak, rk, a, r]) => {
    window.localStorage.setItem(ak, a);
    window.localStorage.setItem(rk, r);
  }, ['access_token', 'refresh_token', ACCESS_TOKEN, REFRESH_TOKEN]);
  if (prefs) {
    await page.addInitScript(([key, value]) => {
      window.localStorage.setItem(key, value);
    }, [`personal.preferences.v1.${reader.person.user_id}`, JSON.stringify(prefs)]);
  }
}

async function returnToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

async function signOutThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu).toBeVisible();
  await accountMenu.click();
  const signOut = page.getByRole('menuitem', { name: /sign out/i });
  await expect(signOut).toBeVisible();
  await signOut.click();
  await page.waitForURL('**/login**');
  await expect(page.getByRole('heading', { name: /sign in to your account/i })).toBeVisible();
  await page.waitForTimeout(250);
}

async function signInThroughTheForm(page: Page, who: Person): Promise<void> {
  await expect(page).toHaveURL(/\/login/);
  await page.locator('input[type="email"], input[name="email"]').first().fill(who.email);
  await page.locator('input[type="password"]').first().fill('local-only-e2e-fixture');
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

async function goToDashboardThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu).toBeVisible();
  await accountMenu.click();
  await page.getByRole('menuitem', { name: /^dashboard$/i }).click();
  await page.waitForURL('**/dashboard');
}

const savedRows = (page: Page) => page.getByTestId('saved-match');

/* ======================= T1: TWO READS IN FLIGHT AT ONCE ======================= */

test('ADV1: two favourites reads in flight at once across an account change', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const heldFirst = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await heldFirst.arrived;

  await signOutThroughTheHeader(page);

  // Arm a SECOND hold so the next account's own read is also in flight at the same moment.
  const heldSecond = holdNextFavouritesRead(world);
  await signInThroughTheForm(page, SECOND);
  await goToDashboardThroughTheHeader(page);
  await heldSecond.arrived;

  // Both are now on the wire. Land the OLD one first.
  heldFirst.release();
  await page.waitForTimeout(700);
  await expect(savedRows(page).filter({ hasText: CLUB_ONE }),
    'the previous account\'s snapshot must not appear while the new one is still loading').toHaveCount(0);

  heldSecond.release();
  await page.waitForTimeout(900);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO }),
    'the current account\'s own read must still land').toHaveCount(1);
  await expect(savedRows(page).filter({ hasText: CLUB_ONE })).toHaveCount(0);
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);

  // And the in-flight slot must not be wedged by the discarded read.
  const reads = world.favouriteReads;
  await page.waitForTimeout(FOCUS_GUARD_MS + 800);
  await returnToTheTab(page);
  await page.waitForTimeout(900);
  expect(world.favouriteReads, 'a later refresh must still be possible (inFlight not wedged)')
    .toBeGreaterThan(reads);
});

/* ======================= T2: A READ THAT FAILS AFTER SIGN-OUT ======================= */

test('ADV2: a favourites read that FAILS after sign-out does not error the signed-out screen', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  await signOutThroughTheHeader(page);
  const readsAtSignOut = world.favouriteReads;

  held.release(503);
  await page.waitForTimeout(900);

  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);
  expect(await page.locator('body').innerText()).not.toMatch(/could not be loaded/i);
  expect(await page.locator('body').innerText()).not.toContain(CLUB_ONE);

  await page.waitForTimeout(FOCUS_GUARD_MS + 800);
  await returnToTheTab(page);
  await page.waitForTimeout(800);
  expect(world.favouriteReads, 'a failed read after sign-out must leave no watcher behind')
    .toBe(readsAtSignOut);
});

/* ======================= T3: A WRITE DURING A WRITE ======================= */

test('ADV3: two writes overlapping a held read leave the server and the control agreeing', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('follow-button').first();
  await expect(star).toHaveAttribute('data-following', 'false');

  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;

  // follow, then unfollow, as fast as the control allows, both inside the held read.
  await star.click();
  await expect(star).toHaveAttribute('data-following', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
  await star.click();
  await expect(star).toHaveAttribute('data-following', 'false');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.teamIds, 'the server ends up not following').toEqual([]);

  held.release();
  await page.waitForTimeout(1_200);

  await expect(star, 'the control must agree with the server after the stale read lands')
    .toHaveAttribute('data-following', 'false');
});

/* ======================= T4: IS A READER NOW A POLLER? ======================= */

test('ADV4: a dashboard with nothing live and nothing due makes no extra reads over ten minutes', async ({ page }) => {
  const world = new World();
  // Saved, but kicks off in three days: outside any kick-off watch window.
  const far = fixtureAt(new Date(Date.parse('2026-09-19T18:00:00Z') + 3 * 24 * 3600_000).toISOString(),
    'Far Rangers', 'Far Albion');
  world.first.saved.set(far.id, { match: far, savedAt: '2026-09-19T18:00:00Z' });
  await page.clock.install({ time: new Date('2026-09-19T18:00:00Z') });
  await page.clock.resume();
  await stubWorld(page, world, iso => dayPayload(iso, []));
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(page.getByTestId('saved-match').first()).toBeVisible();
  await page.waitForTimeout(1_000);
  const readsAfterLoad = world.favouriteReads;

  await page.clock.fastForward(10 * 60 * 1000);
  await page.waitForTimeout(1_500);

  expect(world.favouriteReads,
    `nothing live and nothing due must mean no polling (was ${readsAfterLoad})`)
    .toBe(readsAfterLoad);
});

test('ADV5: a fixture that is due to kick off is polled, and at the slower cadence', async ({ page }) => {
  const world = new World();
  const soon = fixtureAt(new Date(Date.parse('2026-09-19T18:00:00Z') + 60_000).toISOString(),
    'Soon Rangers', 'Soon Albion');
  world.first.saved.set(soon.id, { match: soon, savedAt: '2026-09-19T18:00:00Z' });
  await page.clock.install({ time: new Date('2026-09-19T18:00:00Z') });
  await page.clock.resume();
  await stubWorld(page, world, iso => dayPayload(iso, []));
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(page.getByTestId('saved-match').first()).toBeVisible();
  await page.waitForTimeout(1_000);
  const readsAfterLoad = world.favouriteReads;

  // Ten minutes across the kick-off. At 120s that is at most ~6 reads, never 10+.
  await page.clock.fastForward(10 * 60 * 1000);
  await page.waitForTimeout(1_500);
  const extra = world.favouriteReads - readsAfterLoad;
  // eslint-disable-next-line no-console
  console.log(`ADV5 extra reads across 10 simulated minutes spanning kick-off: ${extra}`);
  expect(extra, 'the kick-off watch must actually read').toBeGreaterThan(0);
  expect(extra, 'and must not be faster than the 120s cadence it documents').toBeLessThanOrEqual(7);
});

/* ============ T6: IS THE liveUpdates PREFERENCE HONOURED AWAY FROM THE DASHBOARD? ============ */

test('ADV6: liveUpdates off is honoured on a match page the reader lands on directly', async ({ page }) => {
  const world = new World();
  const livePlaying: ApiMatch = {
    ...FIXTURE_ONE, status: 'live', minute: '23', score: { home: 1, away: 0 },
  };
  world.first.saved.set(livePlaying.id, { match: livePlaying, savedAt: '2026-09-19T18:00:00Z' });
  await page.clock.install({ time: new Date('2026-09-19T18:00:00Z') });
  await page.clock.resume();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first, {
    forecasts: true, prompts: true, liveUpdates: false, paused: false,
  });

  // Straight to a match page. The dashboard, where usePersonalPreferences binds the account,
  // is never visited in this page load.
  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1_000);
  const readsAfterLoad = world.favouriteReads;

  await page.clock.fastForward(5 * 60 * 1000);
  await page.waitForTimeout(1_500);
  const extra = world.favouriteReads - readsAfterLoad;
  // eslint-disable-next-line no-console
  console.log(`ADV6 extra favourites reads with liveUpdates OFF, off-dashboard: ${extra}`);
  expect(extra, 'a reader who switched automatic updates off must not be polled anywhere')
    .toBe(0);
});

test('ADV7: liveUpdates off IS honoured once the dashboard has been visited', async ({ page }) => {
  const world = new World();
  const livePlaying: ApiMatch = {
    ...FIXTURE_ONE, status: 'live', minute: '23', score: { home: 1, away: 0 },
  };
  world.first.saved.set(livePlaying.id, { match: livePlaying, savedAt: '2026-09-19T18:00:00Z' });
  await page.clock.install({ time: new Date('2026-09-19T18:00:00Z') });
  await page.clock.resume();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first, {
    forecasts: true, prompts: true, liveUpdates: false, paused: false,
  });

  await page.goto('/dashboard');
  await expect(page.getByTestId('saved-match').first()).toBeVisible();
  await page.waitForTimeout(1_000);
  const readsAfterLoad = world.favouriteReads;

  await page.clock.fastForward(5 * 60 * 1000);
  await page.waitForTimeout(1_500);
  const extra = world.favouriteReads - readsAfterLoad;
  // eslint-disable-next-line no-console
  console.log(`ADV7 extra favourites reads with liveUpdates OFF, on dashboard: ${extra}`);
  expect(extra).toBe(0);
});
