import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, Json, baseMatches, dayPayload, registerAuthHandler, stubBackend,
} from '../support/api-stub';

/**
 * RACES IN THE FAVOURITES STORE, EACH DRIVEN BY HOLDING ONE RESPONSE OPEN.
 *
 * `src/services/favourites.service.ts` keeps one optimistic store for everything a reader follows
 * and has saved. Every defect proved here is the same shape: a request that was issued while one
 * thing was true, and whose answer was applied after it had stopped being true.
 *
 *   1. A READ THAT OUTLIVES ITS SESSION. `reset()` clears the state and drops the in-flight
 *      HANDLE, but it cannot stop the request. The continuation then ran unconditionally, so the
 *      previous reader's saved matches were written back into the store AFTER they signed out —
 *      and, if somebody else had signed in by then, into that person's session. The failure path
 *      had the same hole: an older read's 503 could put the new session into `error`.
 *   2. A READ OLDER THAN A LOCAL WRITE. A save or a follow applies optimistically and reconciles
 *      against the server's own answer. A read issued BEFORE that write carries a snapshot which
 *      predates it, and applying it silently undid the reader's action: the star went back off.
 *   3. A WRITE THAT OUTLIVES ITS SESSION — the same hole as 1, in the six paths that were never
 *      guarded: save, unsave and follow, each with a success and a rollback. A save resolving
 *      after a change of account inserted the previous reader's save row, PRIVATE NOTE INCLUDED,
 *      into the new reader's store; and every rollback restored `before.data`, the previous
 *      reader's WHOLE favourites snapshot. Sections 4 and 5 below.
 *   4. A REFRESH THAT LANDS IN THE MIDDLE OF A WRITE. Not stale by either counter — it was issued
 *      after the local change, so nothing discards it — and it carries the server state from
 *      before the write committed. `unsaveMatch`'s success path only cleared the pending flag, on
 *      the assumption that its optimistic removal still stood, so the refresh's copy of the
 *      bookmark was left on screen after the removal had succeeded. Section 6 below.
 *
 * EVERY TEST HERE IS MOCKED-ONLY, and the names say so. Each one needs a response held open for a
 * known length of time — across a sign-out, across a change of account, or across a refresh —
 * which cannot be arranged against the real backend without slowing it down for everything else
 * using it. e2e/live/* covers the same journeys at their normal speed, where the ordering cannot
 * be chosen and so the race cannot be reached on purpose.
 *
 * COST. Every /api/v1 route is intercepted, so nothing here reaches the network and no provider
 * request is possible. `refresh=true` is never sent by anything this file drives.
 *
 * NOTHING HERE IS A WAGER. Saving and following are bookmarks; no assertion below stakes, scores
 * or settles anything.
 */

/* ------------------------------------------------------------------------------- the readers */

interface Person extends Json {
  user_id: string;
  email: string;
  full_name: string;
  role: 'regular';
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

const person = (suffix: string, name: string): Person => ({
  user_id: `00000000-0000-4000-8000-0000000000${suffix}`,
  email: `qa.${name}@predictions-local.dev`,
  full_name: `QA ${name}`,
  role: 'regular',
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
});

/** Two different people on one machine. The point of half this file is that they stay different. */
const FIRST = person('c1', 'First');
const SECOND = person('c2', 'Second');

/**
 * Opaque strings that never leave the browser context. The stub accepts anything and no real
 * backend is contacted, so these are not credentials and unlock nothing.
 */
const ACCESS_TOKEN = 'e2e-consistency-access-token';
const REFRESH_TOKEN = 'e2e-consistency-refresh-token';

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

/* -------------------------------------------------------------------------- the stubbed world */

/**
 * Two captured fixtures with different clubs in them, so "whose saved match is this?" can be
 * answered by reading the screen.
 */
const FIXTURE_ONE = baseMatches()[0];
const FIXTURE_TWO = baseMatches().find(
  match => (match.home as ApiTeamRef).name !== (FIXTURE_ONE.home as ApiTeamRef).name,
) as ApiMatch;
const CLUB_ONE = (FIXTURE_ONE.home as ApiTeamRef).name;
const CLUB_TWO = (FIXTURE_TWO.home as ApiTeamRef).name;
const TEAM = FIXTURE_ONE.home as ApiTeamRef;

/**
 * FOCUS_REFRESH_MIN_AGE_MS in src/services/favourites.service.ts, mirrored.
 *
 * It is a coalescing guard: a snapshot younger than this is not re-read when the tab comes back,
 * because `focus` and `visibilitychange` routinely arrive as a pair. Waiting it out is what makes
 * "come back to the tab" a reliable way to put a background read on the wire.
 */
const FOCUS_GUARD_MS = 5_000;

interface SavedRow {
  match: ApiMatch;
  savedAt: string;
  /** The reader's own private note on this save, exactly as the API stores and returns one. */
  note: string | null;
}

/**
 * The first reader's private note.
 *
 * A save row carries one, `GET /me/favourites` returns it and `PUT /me/saved-matches/{id}` returns
 * it again, so it travels inside every payload the write tests hold open. It is the single most
 * private thing this store handles and therefore the sharpest probe for a leak: a string that can
 * only have come from the first reader's row, searched for on the second reader's screen.
 */
const FIRST_NOTE = 'Leaving work at five to be home for kick-off.';

/** One person's rows on the server: what they saved and what they follow. */
class Reader {
  saved = new Map<string, SavedRow>();

  teamIds: string[] = [];

  /** The note this reader's save rows carry. Only the first reader has one. */
  note: string | null = null;

  constructor(readonly person: Person) {}

  save(match: ApiMatch): void {
    const existing = this.saved.get(match.id);
    this.saved.set(match.id, {
      match,
      savedAt: existing?.savedAt ?? new Date().toISOString(),
      note: this.note,
    });
  }
}

/** A read the test is holding open, and the handle that lets it land. */
interface HeldRead {
  /** Resolves when the application has actually issued the read and the stub is sitting on it. */
  arrived: Promise<void>;
  /** Let it land, with `status` 200 for a snapshot or anything else for a failure. */
  release: (status?: number) => void;
}

interface Hold {
  announce: () => void;
  released: Promise<number>;
}

/**
 * The stand-in for the signed-in half of the backend.
 *
 * It is a little server rather than a fixed payload because every assertion here is about WHEN an
 * answer arrives relative to something else. A frozen payload cannot hold a response open.
 */
class World {
  readonly first = new Reader(FIRST);

  readonly second = new Reader(SECOND);

  /** Who `/auth/me` currently answers as, or nobody. */
  signedIn: Reader | null = null;

  /** Every `GET /api/v1/me/favourites` the application issued, answered or not. */
  favouriteReads = 0;

  /** Every `GET /api/v1/teams/{id}`: the follow fan-out, which only a followed team causes. */
  teamReads = 0;

  /** Teams `GET /api/v1/teams/{id}` knows about. */
  knownTeams: ApiTeamRef[] = [TEAM];

  /** What `GET /api/v1/teams/{id}` reports that team has coming up. Empty unless a test sets it. */
  teamFixtures: ApiMatch[] = [];

  private hold: Hold | null = null;

  private writeHold: Hold | null = null;

  arm(hold: Hold): void {
    this.hold = hold;
  }

  /** The armed hold, once. A second read is answered at once rather than queued behind the first. */
  takeHold(): Hold | null {
    const held = this.hold;
    this.hold = null;
    return held;
  }

  armWrite(hold: Hold): void {
    this.writeHold = hold;
  }

  takeWriteHold(): Hold | null {
    const held = this.writeHold;
    this.writeHold = null;
    return held;
  }

  readerFor(email: string): Reader | null {
    if (email === FIRST.email) return this.first;
    if (email === SECOND.email) return this.second;
    return null;
  }
}

function makeHold(): { hold: Hold; held: HeldRead } {
  let announce!: () => void;
  const arrived = new Promise<void>(resolve => { announce = resolve; });
  let unlock!: (status: number) => void;
  const released = new Promise<number>(resolve => { unlock = resolve; });
  return { hold: { announce, released }, held: { arrived, release: (status = 200) => unlock(status) } };
}

function holdNextFavouritesRead(world: World): HeldRead {
  const { hold, held } = makeHold();
  world.arm(hold);
  return held;
}

/**
 * Hold the next WRITE — a save, an unsave or a follow — open.
 *
 * THE EFFECT LANDS WHEN THE HOLD IS RELEASED, NOT WHEN THE REQUEST ARRIVES, and that is the
 * opposite of the read hold a few lines up on purpose. A read is answered from the state the
 * server held when the request arrived, so its body is built then. A write that is still in
 * flight is one the server has not committed, so anything READ in the meantime must still see
 * the old value — which is exactly the window a refresh lands in, and the whole of section 6.
 * Releasing with a status other than 200 leaves the effect unapplied, the way a write that
 * failed leaves it.
 */
function holdNextWrite(world: World): HeldRead {
  const { hold, held } = makeHold();
  world.armWrite(hold);
  return held;
}

/** Wait on the armed write hold, if there is one. Returns the release status, or null. */
async function heldWrite(world: World): Promise<number | null> {
  const hold = world.takeWriteHold();
  if (!hold) return null;
  hold.announce();
  return hold.released;
}

const savedEntry = (row: SavedRow): Json => ({
  match_id: row.match.id,
  note: row.note,
  saved_at: row.savedAt,
  updated_at: row.savedAt,
  match: row.match,
});

function savedMatchesPayload(reader: Reader): Json {
  const rows = Array.from(reader.saved.values());
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

function favouritesPayload(world: World, reader: Reader): Json {
  return {
    teams: world.knownTeams.filter(team => reader.teamIds.includes(team.id)),
    leagues: [],
    team_ids: [...reader.teamIds],
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: savedMatchesPayload(reader),
    limits: { teams: 10, leagues: 5 },
  };
}

/**
 * Sign-in, sign-out and `/auth/me`, keyed on the address that was typed into the form.
 *
 * Two accounts share one browser here, so the session cannot be a boolean: the sign-in that
 * matters most in this file is the one where a DIFFERENT person arrives on the same machine.
 */
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
      return json({
        access_token: ACCESS_TOKEN,
        refresh_token: REFRESH_TOKEN,
        token_type: 'bearer',
        user: reader.person,
      });
    }
    if (path === '/logout') {
      world.signedIn = null;
      return json({ message: 'Logged out successfully' });
    }
    if (path === '/me') {
      return world.signedIn
        ? json(world.signedIn.person)
        : json({ detail: 'Not authenticated' }, 401);
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

/**
 * The signed-in endpoints.
 *
 * Registered AFTER stubBackend so Playwright reaches these first: stubBackend answers anything it
 * does not model with an empty object, and an empty object on `PUT /me/saved-matches/{id}` is a
 * payload the mapper cannot read.
 */
async function stubAccount(page: Page, world: World): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1\/me/, '');
    const method = request.method();

    // Counted before anything else: the question these tests ask most often is whether the
    // application issued a request at all, and a 401 is still a request.
    if (path === '/favourites') world.favouriteReads += 1;

    const reader = world.signedIn;
    // Every /me endpoint is authenticated. Answering a tokenless request would let a sign-out
    // failure look like a success. This is the 401 the real backend gives an anonymous caller.
    if (!reader) return json(route, { detail: 'Not authenticated' }, 401);

    if (path === '/favourites') {
      /*
       * THE BODY IS COMPUTED NOW, NOT WHEN THE HOLD IS RELEASED.
       *
       * That is the whole fidelity of this file. A held read is a read the server answered from
       * the state it held at the moment the request arrived; building the payload after the
       * release would model a read that answered from the future, which is the opposite of the
       * race under test.
       */
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
        const status = await heldWrite(world);
        if (status !== null && status !== 200) {
          return json(route, { detail: 'Simulated upstream failure' }, status);
        }
        const created = !reader.saved.has(matchId);
        reader.save(known);
        const row = reader.saved.get(matchId) as SavedRow;
        return json(route, { ...savedEntry(row), created });
      }
      if (method === 'DELETE') {
        const status = await heldWrite(world);
        if (status !== null && status !== 200) {
          return json(route, { detail: 'Simulated upstream failure' }, status);
        }
        const removed = reader.saved.delete(matchId);
        return json(route, { match_id: matchId, removed });
      }
    }

    const follow = /^\/favourites\/(teams|leagues)\/(.+)$/.exec(path);
    if (follow) {
      const id = decodeURIComponent(follow[2]);
      const following = method === 'PUT';
      const status = await heldWrite(world);
      if (status !== null && status !== 200) {
        return json(route, { detail: 'Simulated upstream failure' }, status);
      }
      const before = [...reader.teamIds];
      reader.teamIds = following
        ? (before.includes(id) ? before : [...before, id])
        : before.filter(entry => entry !== id);
      return json(route, {
        kind: follow[1] === 'teams' ? 'team' : 'league',
        id,
        following,
        changed: before.length !== reader.teamIds.length,
        ids: [...reader.teamIds],
        limit: 10,
      });
    }

    return json(route, {});
  });

  // `GET /api/v1/teams/{id}`: the team page, and the follow fan-out. Registered by regex so
  // `/teams/search`, which the header search depends on, keeps going to stubBackend.
  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, async (route: Route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    world.teamReads += 1;
    const team = world.knownTeams.find(entry => entry.id === id) ?? null;
    if (!team) return json(route, { detail: 'Team not found' }, 404);
    return json(route, { team, upcoming: world.teamFixtures, recent: [] });
  });
}

async function stubWorld(page: Page, world: World): Promise<void> {
  await stubBackend(page, { day: iso => dayPayload(iso) });
  await stubAuth(page, world);
  await stubAccount(page, world);
}

/**
 * Start the document already signed in as `reader`.
 *
 * These tests are not about how a session is created — e2e/mocked/journey-proof.spec.ts proves
 * that — so the token is seeded the way e2e/support/auth.ts seeds it and the application still
 * boots the session itself through `/auth/me`.
 */
async function startSignedIn(page: Page, world: World, reader: Reader): Promise<void> {
  world.signedIn = reader;
  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCESS_TOKEN, REFRESH_TOKEN]);
}

/* ------------------------------------------------------------------------------ small helpers */

/**
 * Come back to this tab.
 *
 * Both events, because `onReaderReturns` listens for both and neither alone covers both ways back:
 * switching browser tabs fires `visibilitychange`, switching applications fires `focus`.
 */
async function returnToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

/**
 * Sign out the way a reader has to: through the account menu in the header.
 *
 * Found by its popup role rather than its name, because the name changes with the width — below
 * Tailwind's `sm` the visible first name is not rendered and the button falls back to an `sr-only`
 * "Account menu".
 */
async function signOutThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu, 'the account menu must be reachable at this width').toBeVisible();
  await accountMenu.click();
  const signOut = page.getByRole('menuitem', { name: /sign out/i });
  await expect(signOut).toBeVisible();
  await signOut.click();
  await page.waitForURL('**/login**');
  /*
   * Wait for the sign-in form to be COMMITTED, not merely for the address to change.
   *
   * `waitForURL` resolves on the history entry; React renders the new screen a moment later, and
   * on that screen `useFavourites` runs its signed-out branch. Releasing a held response inside
   * that window lands it before anything has had the chance to react to the sign-out, which is a
   * narrower and luckier race than the one these tests are about — a reader whose request takes a
   * second is well past it. Every test here therefore starts from a settled signed-out screen.
   */
  await expect(page.getByRole('heading', { name: /sign in to your account/i })).toBeVisible();
  await page.waitForTimeout(250);
}

/** Sign in through the real form, as a second person on this machine would. */
async function signInThroughTheForm(page: Page, who: Person): Promise<void> {
  await expect(page).toHaveURL(/\/login/);
  await page.locator('input[type="email"], input[name="email"]').first().fill(who.email);
  await page.locator('input[type="password"]').first().fill('local-only-e2e-fixture');
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

/**
 * Walk to the dashboard through the header menu rather than `page.goto`.
 *
 * `page.goto` is a full document load, which would throw away the in-flight request every test in
 * this file is holding open. A reader gets there by pressing a link, and so does this.
 */
async function goToDashboardThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu, 'the account menu must be reachable at this width').toBeVisible();
  await accountMenu.click();
  await page.getByRole('menuitem', { name: /^dashboard$/i }).click();
  await page.waitForURL('**/dashboard');
}

/** Let a released response be received and React finish with it. */
async function landed(page: Page, release: () => void): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes('/api/v1/me/favourites'));
  release();
  await response;
  await page.waitForTimeout(500);
}

/** The same for a held WRITE: `part` is enough of the path to recognise it by. */
async function landedWrite(page: Page, part: string, release: () => void): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes(part));
  release();
  await response;
  await page.waitForTimeout(500);
}

const SAVE_PATH = '/api/v1/me/saved-matches/';
const FOLLOW_PATH = '/api/v1/me/favourites/teams/';

const savedRows = (page: Page) => page.getByTestId('saved-match');
const savedRow = (page: Page, matchId: string) =>
  page.locator(`[data-testid="saved-match"][data-match-id="${matchId}"]`);
const starIn = (page: Page, matchId: string) =>
  savedRow(page, matchId).getByTestId('save-match-button');

/**
 * Somebody else arrives on this machine while the first reader's write is still on the wire.
 *
 * One slow request and two taps: it is not an exotic ordering, and it is the one that decides
 * whether a private note can cross from one account to another.
 */
async function anotherReaderTakesOver(page: Page, who: Person): Promise<void> {
  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, who);
  await goToDashboardThroughTheHeader(page);
}

/** Wait out the coalescing guard so that coming back to the tab really issues a read. */
async function letTheSnapshotGoStale(page: Page): Promise<void> {
  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
}

/** Come back to the tab and wait for the refresh it causes to have landed and rendered. */
async function refreshThroughTheTab(page: Page): Promise<void> {
  const response = page.waitForResponse(r => r.url().includes('/api/v1/me/favourites'));
  await returnToTheTab(page);
  await response;
  await page.waitForTimeout(500);
}

/* ------------------------------------------------------ 1. a read that outlives its session */

test('MOCKED-ONLY: a favourites read held open across sign-out is discarded, not kept for the next session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;
  await expect(page.getByTestId('feed-loading'), 'the read under test must really be held open')
    .toBeVisible();

  await signOutThroughTheHeader(page);

  /*
   * What the server holds moves on while nobody is signed in — the reader removed this save from
   * their phone. The held response therefore carries a snapshot that is wrong in a way the screen
   * can show, which is what makes the assertions below about DATA and not only about timing.
   */
  world.first.saved.clear();
  await landed(page, () => held.release());

  // NO DATA on the signed-out screen, and nothing said about a failure either.
  await expect(page.getByTestId('saved-matches')).toHaveCount(0);
  await expect(savedRows(page)).toHaveCount(0);
  expect(await page.locator('body').innerText()).not.toContain(CLUB_ONE);

  // The same person signs back in. A response kept from the previous session is not just a stale
  // pixel: the store would still be `ready`, so `ensureLoaded()` finds nothing to do and the
  // dashboard is built from it WITHOUT reading anything — a match the server no longer holds,
  // presented as what this reader has saved.
  const readsBeforeSignIn = world.favouriteReads;
  await signInThroughTheForm(page, FIRST);
  await goToDashboardThroughTheHeader(page);

  expect(world.favouriteReads,
    'a new session must read the reader\'s favourites, not inherit the discarded response')
    .toBeGreaterThan(readsBeforeSignIn);
  await expect(page.getByTestId('saved-matches-empty'),
    'the server holds no saves for this reader, so that is what the feed must say').toBeVisible();
  await expect(savedRows(page).filter({ hasText: CLUB_ONE })).toHaveCount(0);
});

test('MOCKED-ONLY: a favourites read discarded at sign-out leaves no focus watcher behind it', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  await signOutThroughTheHeader(page);
  const readsAtSignOut = world.favouriteReads;

  await landed(page, () => held.release());

  /*
   * A response that is applied after sign-out does not only leave data behind: its continuation
   * calls `watchForReturns()` and `syncLivePoll()` as well, re-arming both for a session that
   * has ended. The reader is gone; every request that watcher makes can only ever be a 401 sent
   * on their behalf.
   */
  await page.waitForTimeout(FOCUS_GUARD_MS + 1_000);
  await returnToTheTab(page);
  await page.waitForTimeout(700);
  expect(world.favouriteReads,
    'a signed-out tab coming back to the front must not re-request the previous reader\'s favourites')
    .toBe(readsAtSignOut);
});

/* ---------------------------------------------- 2. a read that outlives the account it read for */

test('MOCKED-ONLY: a favourites read from the previous account does not land in the next account\'s session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  // A different person signs in on the same machine while the first one's read is still on the
  // wire. This is the ordering that leaks data across people, and it is quicker than it sounds:
  // one slow request and two taps.
  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, SECOND);
  await goToDashboardThroughTheHeader(page);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO }),
    'the second reader\'s own feed must be on screen before the stale read lands').toHaveCount(1);

  await landed(page, () => held.release());

  await expect(savedRows(page).filter({ hasText: CLUB_ONE }),
    'the first reader\'s saved match must never appear inside the second reader\'s session')
    .toHaveCount(0);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO }),
    'and the second reader\'s own saved match must still be there').toHaveCount(1);
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);
});

test('MOCKED-ONLY: a favourites read that FAILS after the account changed does not fail the new session', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  const held = holdNextFavouritesRead(world);
  await page.goto('/dashboard');
  await held.arrived;

  await signOutThroughTheHeader(page);
  await signInThroughTheForm(page, SECOND);
  await goToDashboardThroughTheHeader(page);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO })).toHaveCount(1);

  // The catch branch has the same hole as the success branch: an older read's failure was written
  // into whatever session happened to be current when it arrived.
  await landed(page, () => held.release(503));

  await expect(page.getByTestId('saved-matches-failed'),
    'a read that belonged to somebody else\'s session must not put this one into error')
    .toHaveCount(0);
  await expect(savedRows(page).filter({ hasText: CLUB_TWO })).toHaveCount(1);
  expect(await page.locator('body').innerText()).not.toMatch(/feed could not be loaded/i);
});

/* ------------------------------------------------- 3. a read older than the reader's own write */

test('MOCKED-ONLY: a favourites read that predates a save does not undo the save', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');

  // Put a background refresh on the wire the way the application really puts one there — by the
  // reader coming back to the tab — and hold it open.
  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;
  const readsWhileHeld = world.favouriteReads;

  await star.click();
  await expect(star).toHaveAttribute('data-saved', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.saved.size, 'the save really reached the server').toBe(1);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the save must not put the control back to unsaved')
    .toHaveAttribute('data-saved', 'true');
  // Discarded, and then read again: the store owes the reader the server's current answer, not
  // just the absence of a wrong one.
  expect(world.favouriteReads,
    'a discarded read must be replaced by a fresh one, not silently dropped')
    .toBeGreaterThan(readsWhileHeld);
  await expect(star).toHaveAttribute('data-saved', 'true');
});

test('MOCKED-ONLY: a favourites read that predates a follow does not undo the follow', async ({ page }) => {
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

  await star.click();
  await expect(star).toHaveAttribute('data-following', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.teamIds, 'the follow really reached the server').toEqual([TEAM.id]);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the follow must not put the control back')
    .toHaveAttribute('data-following', 'true');
});

test('MOCKED-ONLY: a favourites read that predates an unfollow does not reinstate it', async ({ page }) => {
  const world = new World();
  world.first.teamIds = [TEAM.id];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('follow-button').first();
  await expect(star).toHaveAttribute('data-following', 'true');

  await page.waitForTimeout(FOCUS_GUARD_MS + 500);
  const held = holdNextFavouritesRead(world);
  await returnToTheTab(page);
  await held.arrived;

  await star.click();
  await expect(star).toHaveAttribute('data-following', 'false');
  await expect(star).toHaveAttribute('data-pending', 'false');
  expect(world.first.teamIds, 'the unfollow really reached the server').toEqual([]);

  await landed(page, () => held.release());

  await expect(star, 'a snapshot older than the unfollow must not put the follow back')
    .toHaveAttribute('data-following', 'false');
});

/* --------------------------------------- 4. a write that outlives the account that issued it */

/**
 * SIX PATHS, AND EVERY ONE OF THEM USED TO APPLY UNCONDITIONALLY.
 *
 * `saveMatch`, `unsaveMatch` and `toggleFollow` each have a success path and a rollback, and none
 * of the six checked whose session the answer belonged to. The successes wrote the previous
 * reader's server row into the new reader's store — for a save, that row carries their PRIVATE
 * NOTE. The rollbacks were worse: every one of them restored `before.data`, the whole favourites
 * snapshot captured before the write went out, so a failed write in a session that had ended put
 * one reader's entire saved-and-followed state into another's.
 *
 * Each test below starts the write as the first reader, lets a second reader sign in on the same
 * machine while it is in flight, and then releases it. Nothing of the first reader's may appear,
 * and the second reader's own state must be exactly as they left it.
 */

test('MOCKED-ONLY: a SAVE released after another account signs in does not put the first reader\'s row — or their private note — into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // BOTH readers have this fixture saved. That is what makes the leak visible rather than
  // theoretical: the row is on screen either way, and only the note says whose it is.
  world.second.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;
  await expect(star, 'the save under test must really be in flight').toHaveAttribute('data-pending', 'true');

  await anotherReaderTakesOver(page, SECOND);
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await expect(page.getByTestId('saved-match-note-text'),
    'the second reader wrote no notes, so there are none on screen before the release').toHaveCount(0);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id),
    'the save really did happen on the server, for the reader who asked for it').toBe(true);
  expect(await page.locator('body').innerText(),
    'the first reader\'s private note must not reach the second reader\'s screen by any route')
    .not.toContain(FIRST_NOTE);
  await expect(page.getByTestId('saved-match-note-text'),
    'and no note at all must have appeared on a row that had none').toHaveCount(0);
  await expect(savedRows(page), 'the second reader\'s own two saves, unchanged').toHaveCount(2);
  await expect(starIn(page, FIXTURE_ONE.id),
    'a pending flag from the session that ended would spin here for a write that is not happening')
    .toHaveAttribute('data-pending', 'false');
  await expect(page.getByTestId('saved-matches-failed')).toHaveCount(0);
});

test('MOCKED-ONLY: a SAVE that FAILS after another account signs in does not roll the first reader\'s snapshot into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // The first reader's snapshot has something in it that the second reader's has not. That is
  // what `data: before.data` used to hand over wholesale.
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty'),
    'the second reader has saved nothing, and that is what their dashboard says').toBeVisible();

  await landedWrite(page, SAVE_PATH, () => held.release(500));

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the save really did fail on the server').toBe(false);
  await expect(savedRows(page),
    'a rollback belonging to a session that has ended must not put its snapshot here').toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
  expect(await page.locator('body').innerText()).not.toContain(CLUB_TWO);
});

test('MOCKED-ONLY: an UNSAVE released after another account signs in does not remove the second reader\'s bookmark', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  // The same fixture, saved by both. A removal applied into the wrong session deletes it here.
  world.second.save(FIXTURE_ONE);
  world.second.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'true');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal really happened, for the first reader')
    .toBe(false);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'the second reader\'s own bookmark for the same fixture must survive it').toHaveCount(1);
  await expect(savedRows(page)).toHaveCount(2);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-saved', 'true');
});

test('MOCKED-ONLY: an UNSAVE that FAILS after another account signs in does not restore the first reader\'s saves into the second\'s session', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'true');

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();

  await landedWrite(page, SAVE_PATH, () => held.release(500));

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal really did fail on the server').toBe(true);
  await expect(savedRows(page)).toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
});

test('MOCKED-ONLY: a FOLLOW released after another account signs in does not follow anything for the second reader', async ({ page }) => {
  const world = new World();
  // The followed team has a fixture, so a follow leaking into the second session would not only
  // change a hidden id list: it would fetch and show a fixture they never asked for.
  world.teamFixtures = [FIXTURE_ONE];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const follow = page.getByTestId('follow-button').first();
  await expect(follow).toHaveAttribute('data-following', 'false');

  const held = holdNextWrite(world);
  await follow.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  const teamReadsBefore = world.teamReads;

  await landedWrite(page, FOLLOW_PATH, () => held.release());

  expect(world.first.teamIds, 'the follow really happened, for the first reader').toEqual([TEAM.id]);
  expect(world.second.teamIds, 'and not for the second').toEqual([]);
  expect(world.teamReads,
    'a follow injected into this session would rebuild the feed and fetch that team\'s fixtures')
    .toBe(teamReadsBefore);
  await expect(page.getByTestId('feed-match'),
    'so no fixture reached through somebody else\'s follow may appear here').toHaveCount(0);
});

test('MOCKED-ONLY: a FOLLOW that FAILS after another account signs in does not roll the first reader\'s snapshot into the second\'s', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  // Again the discriminator is something only the first reader has: their saved matches, which
  // the old rollback restored along with everything else in `before.data`.
  world.first.save(FIXTURE_ONE);
  world.first.save(FIXTURE_TWO);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/teams/${TEAM.id}`);
  await page.waitForLoadState('networkidle');
  const follow = page.getByTestId('follow-button').first();

  const held = holdNextWrite(world);
  await follow.click();
  await held.arrived;

  await anotherReaderTakesOver(page, SECOND);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();

  await landedWrite(page, FOLLOW_PATH, () => held.release(500));

  expect(world.first.teamIds, 'the follow really did fail on the server').toEqual([]);
  await expect(savedRows(page),
    'a failed follow in a session that has ended must not deliver that session\'s saved matches')
    .toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText()).not.toContain(FIRST_NOTE);
});

/* ------------------------------ 5. a rollback inside ONE session reverts one thing, not the world */

test('MOCKED-ONLY: a rollback after a failed write keeps what a refresh legitimately brought in', async ({ page }) => {
  const world = new World();
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  // The reader removes the first fixture; the answer is held, so the server has not committed it.
  const held = holdNextWrite(world);
  await starIn(page, FIXTURE_ONE.id).click();
  await held.arrived;
  await expect(savedRow(page, FIXTURE_ONE.id), 'the removal is applied optimistically').toHaveCount(0);

  // Meanwhile the same reader saves a second fixture on their phone, and this tab picks it up.
  world.first.save(FIXTURE_TWO);
  await refreshThroughTheTab(page);
  await expect(savedRow(page, FIXTURE_TWO.id),
    'the refresh really brought the second fixture in').toHaveCount(1);

  // Now the removal fails. Reverting it must put the first fixture back and touch nothing else.
  await landedWrite(page, SAVE_PATH, () => held.release(500));

  await expect(savedRow(page, FIXTURE_ONE.id),
    'the removal failed, so the bookmark it removed must come back').toHaveCount(1);
  await expect(savedRow(page, FIXTURE_TWO.id),
    'and the fixture the refresh brought in must not be thrown away with it').toHaveCount(1);
  await expect(starIn(page, FIXTURE_ONE.id)).toHaveAttribute('data-pending', 'false');
});

/* --------------------------- 6. a refresh that lands in the middle of a write */

test('MOCKED-ONLY: a refresh landing between an optimistic removal and its answer does not resurrect the bookmark', async ({ page }) => {
  const world = new World();
  world.first.note = FIRST_NOTE;
  world.first.save(FIXTURE_ONE);
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await starIn(page, FIXTURE_ONE.id).click();
  await held.arrived;
  await expect(savedRow(page, FIXTURE_ONE.id)).toHaveCount(0);

  /*
   * THE RACE, REACHED. The removal has not been committed, so a read taken now honestly reports
   * the match as still saved — and nothing discards it, because it was issued AFTER the local
   * change it contradicts. The assertion below is not the behaviour anybody wants; it is the
   * proof that this test really put the two in the order the defect needs. What has to be true
   * is asserted after the release.
   */
  await refreshThroughTheTab(page);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'mid-flight, the refresh legitimately shows the server\'s uncommitted state').toHaveCount(1);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the removal succeeded on the server').toBe(false);
  await expect(savedRow(page, FIXTURE_ONE.id),
    'a bookmark the server has removed must not be left on the screen looking saved').toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toBeVisible();
  expect(await page.locator('body').innerText(),
    'and its private note must go with it').not.toContain(FIRST_NOTE);
});

test('MOCKED-ONLY: a refresh landing in the middle of a save does not leave the save undone', async ({ page }) => {
  const world = new World();
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto(`/match/${FIXTURE_ONE.id}`);
  await page.waitForLoadState('networkidle');
  const star = page.getByTestId('save-match-button').first();
  await expect(star).toHaveAttribute('data-saved', 'false');
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await star.click();
  await held.arrived;
  await expect(star).toHaveAttribute('data-saved', 'true');

  // The same ordering as the test above, the other way round: the refresh reports the server's
  // state from before the save committed.
  await refreshThroughTheTab(page);

  await landedWrite(page, SAVE_PATH, () => held.release());

  expect(world.first.saved.has(FIXTURE_ONE.id), 'the save succeeded on the server').toBe(true);
  await expect(star, 'so the control must end up saved, whatever the refresh saw mid-flight')
    .toHaveAttribute('data-saved', 'true');
  await expect(star).toHaveAttribute('data-pending', 'false');
});

test('MOCKED-ONLY: a refresh landing in the middle of an unfollow does not leave the team in the followed list', async ({ page }) => {
  /*
   * THE SAME ASSUMPTION AS THE REMOVAL ABOVE, IN THE THIRD WRITE.
   *
   * `toggleFollow`'s success assigned the server's authoritative `ids` and left the RESOLVED list
   * alone, assuming the optimistic step — which drops the row from `teams` on an unfollow — was
   * still standing. A refresh landing in between puts the row back. The panel that lists what you
   * follow renders `teams`, while the star renders `teamIds`, so the club stayed in the list with
   * its own star saying it was not followed.
   */
  const world = new World();
  world.first.teamIds = [TEAM.id];
  await stubWorld(page, world);
  await startSignedIn(page, world, world.first);

  await page.goto('/dashboard');
  await expect(page.getByTestId('followed-team')).toHaveCount(1);
  await letTheSnapshotGoStale(page);

  const held = holdNextWrite(world);
  await page.getByTestId('follow-button').first().click();
  await held.arrived;
  await expect(page.getByTestId('followed-team'), 'the unfollow is applied optimistically')
    .toHaveCount(0);

  // The race, reached: the unfollow is not committed, so a read taken now honestly still lists it.
  await refreshThroughTheTab(page);
  await expect(page.getByTestId('followed-team'),
    'mid-flight, the refresh legitimately shows the server\'s uncommitted state').toHaveCount(1);

  await landedWrite(page, FOLLOW_PATH, () => held.release());

  expect(world.first.teamIds, 'the unfollow succeeded on the server').toEqual([]);
  await expect(page.getByTestId('followed-team'),
    'a team the server no longer holds must not be left in the list of what you follow')
    .toHaveCount(0);
  await expect(page.getByTestId('following-empty')).toBeVisible();
});
