import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, DayPayload, Json, baseMatches, dayPayload, localDay,
  registerAuthHandler, stubBackend,
} from '../support/api-stub';

/**
 * THE PERSONAL JOURNEY, PROVED AGAINST STUBBED PAYLOADS.
 *
 * Browse, narrow the list to one competition, open a fixture, be sent to sign in by a save, sign
 * in, come back to the SAME filtered list with the save done, find it in the personal feed, find a
 * played fixture's result in that feed, sign out, and be left with nothing personal behind.
 *
 * WHAT THIS FILE IS EVIDENCE OF, AND WHAT IT IS NOT.
 *   It proves the INTERFACE LOGIC: the router handoff, the save control's states, the feed's
 *   grouping, the failure wording, the focus contract, and what the document is left holding after
 *   a sign-out. Every backend answer is a stub, so it proves nothing about the backend, nothing
 *   about the real database and nothing about a real account.
 *   e2e/live/journey-proof.spec.ts is the other half: the same journey against the running backend
 *   and the QA account. Neither file's counts may be reported as the other's — several assertions
 *   here exist ONLY here, because they need a failure or a latency that cannot be arranged against
 *   a real backend without damaging it, and they are marked MOCKED-ONLY where they appear.
 *
 * THREE WIDTHS. The suite's projects give 1440 (mocked-desktop) and 390 (mocked-mobile, iPhone 13);
 * mocked-mobile-360 is restricted by playwright.config.ts to navigation-continuity.spec.ts, and
 * that file is not ours to widen. So the journey sets its own viewport and runs at 360, 390 and
 * 1440 INSIDE each project. Under mocked-mobile that is three widths with iPhone 13 touch and
 * mobile user-agent emulation; under mocked-desktop it is three widths of desktop Chrome. Both are
 * reported, and neither is described as the other.
 *
 * COST. Nothing here reaches the network at all: every /api/v1 route is intercepted. No provider
 * request is possible from this file, and `refresh=true` is never sent by anything it drives.
 *
 * Saving is not a wager. Nothing in this file stakes, scores or settles anything, and no assertion
 * below treats a save as a commitment of money.
 */

/* ------------------------------------------------------------------------ widths and geometry */

interface Width {
  label: string;
  width: number;
  height: number;
}

/**
 * 360 is the narrowest phone this interface has to work on (Galaxy S8 and most budget Androids),
 * 390 is the iPhone 13 the mobile project emulates, 1440 the desktop project's own window.
 */
const WIDTHS: Width[] = [
  { label: '360', width: 360, height: 740 },
  { label: '390', width: 390, height: 844 },
  { label: '1440', width: 1440, height: 900 },
];

/** A restore lands within this many pixels: sub-pixel layout and a re-measured sticky header. */
const RESTORE_TOLERANCE = 40;

/** How far the document may exceed the viewport before it is sideways scroll. One px is rounding. */
const OVERFLOW_TOLERANCE = 1;

const scrollY = (page: Page): Promise<number> => page.evaluate(() => Math.round(window.scrollY));

const scrollState = (page: Page): Promise<{ y: number; furthest: number }> =>
  page.evaluate(() => ({
    y: Math.round(window.scrollY),
    furthest: Math.max(0, Math.round(document.documentElement.scrollHeight - window.innerHeight)),
  }));

const horizontalOverflow = (page: Page): Promise<number> =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

/* -------------------------------------------------------------------------- the stubbed world */

/** The captured fixture the journey walks into, and the competition it is filtered to. */
const FIXTURE = baseMatches()[0];
const COMPETITION = FIXTURE.competition as { id: string; name: string };
const HOME = FIXTURE.home as ApiTeamRef;
const AWAY = FIXTURE.away as ApiTeamRef;
const FIXTURE_LABEL = `${HOME.name} versus ${AWAY.name}`;

/**
 * A day on which one competition holds most of the fixtures.
 *
 * The capture spreads 23 fixtures over five competitions, so a filtered list fits a 1440x900
 * window with nothing to scroll — and a scroll-restoration assertion on a page that cannot scroll
 * asserts nothing. Re-labelling four fifths of them leaves every other captured field untouched.
 */
function crowdedDay(iso: string): DayPayload {
  const stacked = baseMatches().map((match, index) =>
    (index % 5 === 4 ? match : { ...match, competition: FIXTURE.competition }));
  return dayPayload(iso, stacked);
}

/**
 * A played fixture carrying a result.
 *
 * DERIVED, NOT CAPTURED, and the distinction is the point: every fixture in e2e/fixtures is
 * `scheduled` with a null score, because that is what the local database held on the capture day.
 * The score below is therefore a STUB PAYLOAD used to exercise the feed's results group, in the
 * same way withoutMarkets() and fixtureAt() reshape a capture elsewhere in this suite. It is not a
 * claim about any real match, and the corresponding live assertion reads a real finished fixture
 * out of the local database rather than composing one.
 */
function playedFixture(): ApiMatch {
  const source = baseMatches()[1];
  const kickoff = new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString();
  return {
    ...source,
    kickoff_utc: kickoff,
    status: 'finished',
    minute: null,
    score: { home: 2, away: 1 },
  };
}

/* ------------------------------------------------------------------------- the stubbed session */

/**
 * The account the journey signs in as. A stub user in a stubbed browser context; it authenticates
 * nothing and exists nowhere.
 */
const USER: Json = {
  user_id: '00000000-0000-4000-8000-0000000000aa',
  email: 'qa.journey@predictions-local.dev',
  full_name: 'QA Journey',
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
const ACCESS_TOKEN = 'e2e-journey-access-token';
const REFRESH_TOKEN = 'e2e-journey-refresh-token';

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

/**
 * A saved match as `/api/v1/me/saved-matches` serves it, plus the bookkeeping this fake keeps.
 */
interface SavedRow {
  match: ApiMatch;
  note: string | null;
  savedAt: string;
}

/**
 * The stand-in for the signed-in half of the backend.
 *
 * It is a real little server rather than a fixed payload because three of the assertions below are
 * about what the application DOES to it: how many writes one double-press issues, whether a second
 * save of the same match creates a second row, and whether a request still carries a token after a
 * sign-out. A frozen payload cannot answer any of those.
 */
class FakeAccount {
  /** Whether /auth/me currently answers as a signed-in user. Flipped by /auth/login and /auth/logout. */
  signedIn = false;

  saved = new Map<string, SavedRow>();

  teams: ApiTeamRef[] = [];

  /** Team ids whose `/api/v1/teams/{id}` read must fail, to model one follow that cannot be read. */
  unreadableTeams = new Set<string>();

  /** Fixtures a readable followed team contributes. */
  teamFixtures: ApiMatch[] = [];

  /** Every write the application made against the saved-matches API, in order. */
  writes: Array<{ method: string; matchId: string }> = [];

  /** Every /api/v1 request seen, with whether it carried an Authorization header. */
  requests: Array<{ method: string; path: string; authorized: boolean }> = [];

  /** Delay applied to saved-match writes, so a second press can be made while one is in flight. */
  writeLatencyMs = 0;

  save(match: ApiMatch): boolean {
    const id = match.id as string;
    const existing = this.saved.get(id);
    // Idempotent by construction, exactly as the real API is: a second PUT on the same id updates
    // the row it already holds and reports `created: false`. A fake that appended instead would
    // make the idempotency assertion below pass against a server nobody would ship.
    this.saved.set(id, { match, note: existing?.note ?? null, savedAt: existing?.savedAt ?? new Date().toISOString() });
    return existing === undefined;
  }
}

const savedEntry = (row: SavedRow) => ({
  match_id: row.match.id,
  note: row.note,
  saved_at: row.savedAt,
  updated_at: row.savedAt,
  match: row.match,
});

/** `GET /api/v1/me/saved-matches`, in the shape src/services/favourites.service.ts maps. */
function savedMatchesPayload(account: FakeAccount): Json {
  const rows = Array.from(account.saved.values());
  const bucket = (status: string) => rows.filter(row => row.match.status === status).map(savedEntry);
  const live = rows.filter(row => row.match.status === 'live' || row.match.status === 'halftime').map(savedEntry);
  const upcoming = bucket('scheduled');
  const finished = bucket('finished');
  return {
    upcoming,
    live,
    finished,
    counts: {
      upcoming: upcoming.length,
      live: live.length,
      finished: finished.length,
      total: upcoming.length + live.length + finished.length,
    },
  };
}

function favouritesPayload(account: FakeAccount): Json {
  return {
    teams: account.teams,
    leagues: [],
    team_ids: account.teams.map(team => team.id),
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    saved_matches: savedMatchesPayload(account),
    limits: { teams: 10, leagues: 5, saved_matches: 200 },
  };
}

/**
 * Sign-in, sign-out and `/auth/me`, WITHOUT seeding a token.
 *
 * e2e/support/auth.ts exists for tests that need to start already signed in: it writes the tokens
 * into localStorage before the application boots. This journey is about the transition itself —
 * a signed-out visitor pressing a save — so the session has to begin genuinely absent and be
 * created by the real form submission. The application still stores the tokens itself
 * (authService.login -> tokenManager.setTokens), which is the behaviour the sign-out assertion
 * later depends on.
 */
async function stubAuth(page: Page, account: FakeAccount): Promise<void> {
  const handler = (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    const session = {
      access_token: ACCESS_TOKEN,
      refresh_token: REFRESH_TOKEN,
      token_type: 'bearer',
      user: USER,
    };

    if (path === '/login' || path === '/register') {
      account.signedIn = true;
      return json(session);
    }
    if (path === '/logout') {
      account.signedIn = false;
      return json({ message: 'Logged out successfully' });
    }
    if (path === '/me') {
      return account.signedIn ? json(USER) : json({ detail: 'Not authenticated' }, 401);
    }
    if (path === '/refresh') {
      return account.signedIn
        ? json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' })
        : json({ detail: 'Invalid refresh token' }, 401);
    }
    return json({ detail: 'Not found' }, 404);
  };

  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);
}

/**
 * The signed-in endpoints, and the followed-team fan-out.
 *
 * Registered AFTER stubBackend so Playwright reaches these first: stubBackend answers anything it
 * does not model with an empty object, and an empty object on `PUT /me/saved-matches/{id}` is a
 * payload the mapper cannot read.
 */
async function stubAccount(page: Page, account: FakeAccount): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  page.on('request', request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    account.requests.push({
      method: request.method(),
      path: url.pathname,
      authorized: Boolean(request.headers()['authorization']),
    });
  });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1\/me/, '');
    const method = request.method();

    // Every /me endpoint is authenticated. Answering a tokenless request would let a sign-out
    // failure look like a success: the panel would still be able to render the previous reader's
    // saves. This is the same 401 the real backend gives an anonymous caller.
    if (!account.signedIn) return json(route, { detail: 'Not authenticated' }, 401);

    if (path === '/favourites') return json(route, favouritesPayload(account));
    if (path === '/saved-matches') return json(route, savedMatchesPayload(account));

    const savedMatch = /^\/saved-matches\/(.+)$/.exec(path);
    if (savedMatch) {
      const matchId = decodeURIComponent(savedMatch[1]);
      account.writes.push({ method, matchId });
      if (account.writeLatencyMs > 0) {
        await new Promise(resolve => setTimeout(resolve, account.writeLatencyMs));
      }
      if (method === 'PUT') {
        const known = baseMatches().concat(playedFixture()).find(m => m.id === matchId);
        if (!known) return json(route, { detail: 'Match not found' }, 404);
        const created = account.save(known);
        const row = account.saved.get(matchId) as SavedRow;
        return json(route, { ...savedEntry(row), created });
      }
      if (method === 'DELETE') {
        const removed = account.saved.delete(matchId);
        return json(route, { match_id: matchId, removed });
      }
    }
    return json(route, {});
  });

  // The follow fan-out: `GET /api/v1/teams/{id}` (see feedApi.teamFixtures). Registered by regex so
  // `/teams/search`, which the header search depends on, keeps going to stubBackend.
  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, async (route: Route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    if (account.unreadableTeams.has(id)) {
      return json(route, { detail: 'Simulated upstream failure' }, 503);
    }
    const team = account.teams.find(entry => entry.id === id) ?? null;
    if (!team) return json(route, { detail: 'Team not found' }, 404);
    return json(route, { team, upcoming: account.teamFixtures, recent: [] });
  });
}

/** Everything a journey test needs stubbed, in the order the interceptors must be registered. */
async function stubWorld(
  page: Page,
  account: FakeAccount,
  options: { day?: (iso: string) => DayPayload } = {},
): Promise<void> {
  await stubBackend(page, { day: options.day ?? (iso => crowdedDay(iso)) });
  await stubAuth(page, account);
  await stubAccount(page, account);
}

/* ------------------------------------------------------------------------------ small helpers */

const saveControlIn = (scope: ReturnType<Page['locator']>) => scope.getByTestId('save-match-button');

/** The fixture row for a named club in the current list. */
const rowFor = (page: Page, club: string) =>
  page.getByTestId('fixture-row').filter({ hasText: club }).first();

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/login/);
  await page.locator('input[type="email"], input[name="email"]').first().fill(USER.email as string);
  await page.locator('input[type="password"]').first().fill('local-only-e2e-fixture');
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

/**
 * Sign out the way a reader has to: through the account menu in the header.
 *
 * The button is found by its popup role rather than by its name, because the name CHANGES with the
 * width — below Tailwind's `sm` the visible first name is not rendered at all and the button falls
 * back to an `sr-only` "Account menu" — and a sign-out test that only ran at one width would be
 * asserting about one of those two buttons and claiming both.
 */
async function signOutThroughTheHeader(page: Page): Promise<void> {
  const accountMenu = page.locator('header button[aria-haspopup]').last();
  await expect(accountMenu, 'the account menu must be reachable at this width').toBeVisible();
  await accountMenu.click();
  const signOut = page.getByRole('menuitem', { name: /sign out/i });
  await expect(signOut).toBeVisible();
  await signOut.click();
  await page.waitForURL('**/login**');
}

/**
 * Start the document already signed in.
 *
 * Only for the tests that are NOT about the sign-in transition itself: the double-press guard, the
 * feed's failure wording and the keyboard focus contract all need a session to exist and say
 * nothing about how it was created. The journey tests deliberately do not use this — they begin
 * genuinely signed out and let the real form create the session.
 */
async function startSignedIn(page: Page, account: FakeAccount): Promise<void> {
  account.signedIn = true;
  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ACCESS_TOKEN, REFRESH_TOKEN]);
}

/**
 * Press a control the way a reader's second, impatient press arrives — WITHOUT Playwright's
 * actionability wait.
 *
 * This matters more than it looks. `locator.click()` refuses to act on a button reporting
 * `aria-disabled="true"` and waits for the attribute to go, so the naive version of the
 * double-press test below passed for entirely the wrong reason: Playwright had serialised the
 * presses for us, the second one landed AFTER the first write had settled, and what it actually
 * recorded was a save followed by an unsave followed by a save. The browser itself delivers a
 * click to an `aria-disabled` button, so this is the faithful model of the press, and the guard
 * in SaveMatchButton's own handler is then the only thing that can stop it.
 */
async function pressWithoutWaiting(control: ReturnType<Page['locator']>): Promise<void> {
  await control.evaluate((element: HTMLElement) => element.click());
}

/** Wait for every saved-match write to have landed before reading what the server holds. */
async function writesSettled(page: Page, control: ReturnType<Page['locator']>): Promise<void> {
  await expect(control).toHaveAttribute('data-pending', 'false');
  // The optimistic store clears `pending` the moment the response is handled; one turn of the
  // event loop lets the fake's own bookkeeping finish before it is read.
  await page.waitForTimeout(50);
}

/**
 * Everything this document is holding that could be personal, read out of the browser rather than
 * off the screen.
 *
 * An assertion that only looks at what is drawn proves less than it appears to: a page can stop
 * rendering a name while the token that fetches it is still in localStorage, and the next
 * navigation signs the reader straight back in. So the sign-out assertion reads the real stores.
 */
async function storageDump(page: Page): Promise<{
  local: Record<string, string>;
  session: Record<string, string>;
  databases: string[];
}> {
  const stores = await page.evaluate(async () => {
    const dump = (store: Storage): Record<string, string> => {
      const out: Record<string, string> = {};
      for (let index = 0; index < store.length; index += 1) {
        const key = store.key(index);
        if (key !== null) out[key] = store.getItem(key) ?? '';
      }
      return out;
    };
    let databases: string[] = [];
    try {
      const listed = await (indexedDB as IDBFactory & {
        databases?: () => Promise<Array<{ name?: string }>>;
      }).databases?.();
      databases = (listed ?? []).map(entry => entry.name ?? '(unnamed)');
    } catch {
      databases = ['(indexedDB.databases() unavailable in this browser)'];
    }
    return { local: dump(window.localStorage), session: dump(window.sessionStorage), databases };
  });
  return stores;
}

/* ================================================================================= A1: the journey */

for (const size of WIDTHS) {
  test(`the personal journey, end to end, at ${size.label}px`, async ({ page }) => {
    const account = new FakeAccount();
    await stubWorld(page, account);
    await page.setViewportSize({ width: size.width, height: size.height });

    const day = localDay(0);

    /* ---------------------------------------------------------------- browse */
    await page.goto(`/matches?date=${day}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    const everything = await page.getByTestId('fixture-row').count();
    expect(everything, 'the day must hold fixtures, or nothing below means anything')
      .toBeGreaterThan(1);

    /* -------------------------------------------------- filter by competition */
    const chip = page.getByTestId('competition-chip-row')
      .getByRole('button', { name: new RegExp(COMPETITION.name, 'i') }).first();
    await chip.click();
    await expect.poll(() => new URL(page.url()).searchParams.get('comp'),
      { message: 'the chosen competition must be in the URL, so the list is a link' })
      .toBe(COMPETITION.id);
    await expect(chip).toHaveAttribute('aria-pressed', 'true');

    const filtered = await page.getByTestId('fixture-row').count();
    expect(filtered, 'the filter must actually remove fixtures, or it is not a filter')
      .toBeLessThan(everything);
    expect(filtered).toBeGreaterThan(0);

    const listPath = new URL(page.url()).pathname + new URL(page.url()).search;
    expect(await horizontalOverflow(page),
      `the filtered list must not scroll sideways at ${size.label}px`).toBeLessThanOrEqual(OVERFLOW_TOLERANCE);

    /* -------------------------------------------------------- open a fixture */
    const row = rowFor(page, HOME.name as string);
    await row.locator(`a[href^="/match/${FIXTURE.id}"]`).first().click();
    await page.waitForURL(`**/match/${FIXTURE.id}**`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: HOME.name as string }).first()).toBeVisible();

    /* ------------------------------ a save sends a signed-out visitor to sign in */
    const control = saveControlIn(page).first();
    await expect(control, 'a signed-out visitor gets a control that explains itself, not a dead one')
      .toHaveAttribute('title', new RegExp(`^Sign in to save`, 'i'));
    await control.click();

    await page.waitForURL('**/login**');
    // Registration is reachable from here and carries the same handoff, so creating an account
    // instead of signing in still finishes the save.
    await expect(page.getByRole('link', { name: /create a new account/i })).toBeVisible();
    await expect(page.getByTestId('login-save-intent'),
      'the form says which save is waiting, rather than leaving the visitor to wonder')
      .toContainText(FIXTURE_LABEL);

    /* ----------------------------------------------------------------- sign in */
    await signInThroughTheForm(page);

    /* ----------------- back where they were, with the save actually completed */
    /*
     * WHERE "BACK" IS. The save was pressed on the FIXTURE page, so that is where the handoff
     * returns them — not to the list, which is a step further back. Asserting the list here would
     * have been wrong about the product; the list is reached by the control below, and the URL the
     * reader was on is carried in `?from=` so that control still knows their filters.
     */
    await expect(page, 'the reader comes back to the page they pressed save on')
      .toHaveURL(new RegExp(`/match/${FIXTURE.id}`));
    const returned = saveControlIn(page).first();
    await expect(returned, 'the save the visitor asked for is DONE, not merely offered again')
      .toHaveAttribute('data-saved', 'true');
    await expect(returned).toHaveText(/^Saved$/);
    await expect.poll(() => account.saved.size,
      { message: 'and the server holds exactly that one save' }).toBe(1);
    expect(account.saved.has(FIXTURE.id as string)).toBe(true);

    /* ------------------------------- and the SAME filtered list is one control away */
    await page.getByTestId('back-to-results').click();
    await page.waitForURL('**/matches**');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    expect(new URL(page.url()).pathname + new URL(page.url()).search,
      'the competition filter and the date survived the whole sign-in round trip')
      .toBe(listPath);
    await expect(page.getByTestId('active-filter-chip').filter({ hasText: COMPETITION.name }))
      .toBeVisible();
    expect(await page.getByTestId('fixture-row').count(),
      'and it is the narrowed list, not the whole day').toBe(filtered);

    const restoredRow = rowFor(page, HOME.name as string);
    await expect(saveControlIn(restoredRow).first(),
      'the star in the list agrees with the control that made the save')
      .toHaveAttribute('data-saved', 'true');

    /* ------------------------------------------------- it is in the personal feed */
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const feed = page.getByTestId('saved-matches');
    await expect(feed).toBeVisible();
    await expect(feed.getByTestId('saved-match').filter({ hasText: HOME.name as string }).first())
      .toBeVisible();
    await expect(page.getByTestId('saved-matches-empty'),
      'a feed holding a save must never render the empty state').toHaveCount(0);
    expect(await horizontalOverflow(page),
      `the feed must not scroll sideways at ${size.label}px`).toBeLessThanOrEqual(OVERFLOW_TOLERANCE);

    /* -------------------------- a finished fixture's result is in that history */
    const played = playedFixture();
    account.save(played);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const results = page.getByTestId('feed-group-result');
    await expect(results, 'a played fixture belongs in the results group of the feed').toBeVisible();
    const playedHome = (played.home as ApiTeamRef).name as string;
    const playedRow = results.getByTestId('saved-match').filter({ hasText: playedHome }).first();
    await expect(playedRow).toBeVisible();
    // The score as the row renders it: the club's name and then its own goals.
    await expect(playedRow).toContainText('2');
    await expect(playedRow).toContainText('1');

    /* ------------------------------------------------------------- sign out */
    /*
     * THE POSITIVE CONTROL FIRST. "The token is gone" is worth nothing unless the same read can
     * see a token when there is one — a dump that always came back empty would pass the
     * assertion below on a page that had never signed in at all.
     */
    const beforeSignOut = await storageDump(page);
    expect(beforeSignOut.local[ACCESS_TOKEN_KEY],
      'the session really is in localStorage before we sign out of it').toBe(ACCESS_TOKEN);

    await signOutThroughTheHeader(page);

    /* --------------------------------------- nothing personal is left behind */
    /*
     * WHAT IS CHECKED, since an assertion here is worth only as much as its coverage:
     *   - every key in localStorage, by name and by value;
     *   - every key in sessionStorage, by name and by value — this is where
     *     `sp.scroll-positions` lives, and it is NOT expected to be deleted, so it is checked for
     *     CONTENT instead: scroll offsets are not personal, an account id in them would be;
     *   - which IndexedDB databases the origin holds;
     *   - and, last, that the next navigation to a protected page sends no bearer token and
     *     renders no feed. A token still in storage would fail that even if the screen looked right.
     */
    const dump = await storageDump(page);
    const cookies = await page.context().cookies();
    // Recorded as an artifact, so the claim "nothing personal is left" can be read against the
    // list of what was actually looked at rather than taken on trust.
    await test.info().attach(`storage-after-sign-out-${size.label}`, {
      contentType: 'application/json',
      body: JSON.stringify({ ...dump, cookies: cookies.map(c => c.name) }, null, 2),
    });

    expect(dump.local[ACCESS_TOKEN_KEY], 'the access token is gone from localStorage').toBeUndefined();
    expect(dump.local[REFRESH_TOKEN_KEY], 'and so is the refresh token').toBeUndefined();

    const everythingStored = JSON.stringify({ ...dump.local, ...dump.session, cookies });
    expect(everythingStored, 'no store may still carry the account it was signed in as')
      .not.toContain(USER.email as string);
    expect(everythingStored, 'nor the user id')
      .not.toContain(USER.user_id as string);
    expect(everythingStored, 'nor the fixture that was saved')
      .not.toContain(FIXTURE.id as string);
    expect(everythingStored, 'nor the token itself').not.toContain(ACCESS_TOKEN);
    expect(everythingStored, 'nor the refresh token').not.toContain(REFRESH_TOKEN);

    // And the protected page really is protected again, rather than merely blanked.
    account.requests.length = 0;
    await page.goto('/dashboard');
    await page.waitForURL('**/login**');
    await expect(page.getByTestId('saved-matches')).toHaveCount(0);
    expect(account.requests.filter(entry => entry.authorized),
      'a signed-out document must not send a bearer token to anything')
      .toEqual([]);
  });
}

/* ============================================================== A2: the parts easy to fudge */

for (const size of WIDTHS) {
  test(`Back restores the previous list and its scroll position at ${size.label}px`, async ({ page }) => {
    const account = new FakeAccount();
    await stubWorld(page, account);
    await page.setViewportSize({ width: size.width, height: size.height });

    const listUrl = `/matches?date=${localDay(0)}&comp=${COMPETITION.id}`;
    await page.goto(listUrl);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('fixture-list')).toBeVisible();

    // The LAST fixture, not the first: a click scrolls its target into view, so opening the first
    // row would quietly scroll the list back up and the test would measure that instead.
    const lastFixture = page.getByTestId('fixture-list').locator('a[href^="/match/"]').last();
    await lastFixture.scrollIntoViewIfNeeded();
    await expect(lastFixture).toBeInViewport();
    const left = await scrollY(page);
    expect(left, 'the list must be tall enough for this to mean anything').toBeGreaterThan(200);

    await lastFixture.click();
    await page.waitForURL('**/match/**');
    await expect.poll(() => scrollY(page), { message: 'the fixture page opens at its top' })
      .toBeLessThanOrEqual(2);

    await page.goBack();
    await page.waitForURL(url => url.pathname === '/matches');
    await expect(page.getByTestId('fixture-list')).toBeVisible();

    // THE URL IS NOT THE ASSERTION. A page that came back to the same address and dumped the
    // reader at the top has lost their place, and every check below the first is what says so.
    expect(new URL(page.url()).searchParams.get('comp')).toBe(COMPETITION.id);
    await expect(page.getByTestId('active-filter-chip').filter({ hasText: COMPETITION.name }))
      .toBeVisible();

    /*
     * BOUNDED ON BOTH SIDES, and it took a mutant to notice that it had not been.
     *
     * This read `y >= left - RESTORE_TOLERANCE` — a floor and nothing else. A restore that
     * OVERSHOT passed it, and on a long list "overshot" covers every offset between the reader's
     * place and the bottom of the document. Replacing the remembered offset with
     * Number.MAX_SAFE_INTEGER in ScrollBehaviour.tsx, so that Back always dumps the reader at the
     * very bottom of the list and their place is discarded entirely, kept all three widths green.
     * A restore has a place it is supposed to land on, so the assertion is a distance from it.
     */
    await expect.poll(async () => {
      const { y, furthest } = await scrollState(page);
      if (furthest < left - RESTORE_TOLERANCE) return `the list came back shorter (${furthest})`;
      // The page cannot scroll past its own end, so that is where `left` is reachable.
      const wanted = Math.min(left, furthest);
      return Math.abs(y - wanted) <= RESTORE_TOLERANCE
        ? 'restored'
        : `stopped at ${y}, wanted ${wanted}`;
    }, {
      message: 'Back must restore the position in the list, not only its address',
      timeout: 15_000,
    }).toBe('restored');

    // And it stays there: the workspace rewrites its own URL with `replace: true` shortly after
    // mounting, and a rewrite that counted as a forward move would undo the restore just late
    // enough for a single poll to have passed already. Bounded both ways for the same reason.
    await page.waitForTimeout(700);
    const settled = await scrollState(page);
    expect(Math.abs(settled.y - Math.min(left, settled.furthest)),
      `a URL rewrite after Back must leave the reader where the restore put them (at ${settled.y}, wanted ${Math.min(left, settled.furthest)})`)
      .toBeLessThanOrEqual(RESTORE_TOLERANCE);
  });
}

test('a save that resumes after sign-in on an already-saved match leaves one saved match, not two', async ({ page }) => {
  const account = new FakeAccount();
  await stubWorld(page, account);

  // The reader already has this match saved from an earlier visit. They then press the star again
  // while signed out on another device or after their session lapsed, and sign in. The resume path
  // (useResumeSave) always writes `saved = true`, so this is where a second row would appear.
  const already = baseMatches().find(m => m.id === FIXTURE.id) as ApiMatch;
  account.save(already);
  expect(account.saved.size).toBe(1);

  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');
  const control = saveControlIn(page).first();
  await expect(control).toHaveAttribute('title', /^Sign in to save/i);
  await control.click();
  await page.waitForURL('**/login**');
  await signInThroughTheForm(page);

  await expect.poll(() => account.writes.filter(w => w.method === 'PUT').length,
    { message: 'the resumed save writes once' }).toBe(1);
  expect(account.saved.size, 'and the server still holds exactly one row for it').toBe(1);

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('saved-matches')).toBeVisible();
  await expect(
    page.getByTestId('saved-match').filter({ hasText: HOME.name as string }),
    'and the feed shows it once, not twice',
  ).toHaveCount(1);
});

/**
 * MOCKED-ONLY. It needs a write held open for a known length of time, which cannot be arranged
 * against the real backend without slowing it down for everything else using it.
 */
test('MOCKED-ONLY: pressing the save control twice before the first write lands issues one write', async ({ page }) => {
  const account = new FakeAccount();
  account.writeLatencyMs = 1200;
  await stubWorld(page, account);
  await startSignedIn(page, account);

  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');
  const control = saveControlIn(page).first();
  await expect(control).toHaveAttribute('data-saved', 'false');

  await control.click();
  // While the write is in flight the control announces itself busy — with `aria-disabled`, not
  // the `disabled` attribute, so it keeps its place in the focus order.
  await expect(control).toHaveAttribute('data-pending', 'true');
  await expect(control).toHaveAttribute('aria-disabled', 'true');

  // Two more presses, delivered the way the browser delivers them to an `aria-disabled` button —
  // see pressWithoutWaiting(). Anything that waits for the control to become enabled would be
  // measuring Playwright's patience rather than the application's guard.
  await pressWithoutWaiting(control);
  await pressWithoutWaiting(control);
  await expect(control, 'the write is still the same one').toHaveAttribute('data-pending', 'true');

  await writesSettled(page, control);
  await expect(control).toHaveAttribute('data-saved', 'true');
  expect(account.writes.filter(w => w.method === 'PUT').length,
    'three presses during one write must not become three writes').toBe(1);
  expect(account.writes.filter(w => w.method === 'DELETE').length,
    'and certainly must not become an unsave').toBe(0);
  expect(account.saved.size, 'one saved match, not two').toBe(1);
});

/**
 * MOCKED-ONLY. It fails one upstream read on purpose; the live backend is not made to fail.
 */
test('MOCKED-ONLY: one unreadable follow reads as a failure with a retry, never as an empty feed', async ({ page }) => {
  const account = new FakeAccount();
  const readable = baseMatches()[3].home as ApiTeamRef;
  const broken = baseMatches()[7].home as ApiTeamRef;
  account.teams = [readable, broken];
  account.unreadableTeams.add(broken.id as string);
  // The readable follow answers, and holds nothing in the feed's window. That is the dangerous
  // case: with no rows to show, the panel used to announce "nothing you follow has a fixture
  // stored in it" — a positive claim about a follow nobody had managed to read.
  account.teamFixtures = [];

  await stubWorld(page, account);
  await startSignedIn(page, account);

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const partly = page.getByTestId('feed-partly-unreadable');
  await expect(partly, 'a partial failure is its own state, not the empty one').toBeVisible();
  await expect(page.getByTestId('feed-window-empty'),
    'and it must not be reported as "nothing stored for your follows"').toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toHaveCount(0);

  // THE EXACT SENTENCE. It names the follow that could not be read, and it refuses to make any
  // claim about what that follow holds.
  await expect(partly).toContainText('Nothing stored for the follows we could read.');
  await expect(partly).toContainText(
    `Fixtures for ${broken.name} could not be loaded, so nothing is claimed about it either way.`);
  await expect(partly.getByTestId('feed-partly-unreadable-retry')).toBeVisible();
  await expect(partly.getByTestId('feed-partly-unreadable-retry')).toHaveText('Try again');

  // And the retry really retries: with the upstream repaired, pressing it produces the fixtures.
  account.unreadableTeams.clear();
  account.teamFixtures = [baseMatches()[3]];
  await partly.getByTestId('feed-partly-unreadable-retry').click();
  await expect(page.getByTestId('saved-matches')).toBeVisible();
  await expect(page.getByTestId('feed-match').filter({ hasText: readable.name as string }).first())
    .toBeVisible();
});

/**
 * MOCKED-ONLY, for the same reason: it needs a short feed with one follow deliberately broken.
 */
test('MOCKED-ONLY: a feed that is short because a follow failed says so, and says which', async ({ page }) => {
  const account = new FakeAccount();
  const readable = baseMatches()[3].home as ApiTeamRef;
  const broken = baseMatches()[7].home as ApiTeamRef;
  account.teams = [readable, broken];
  account.unreadableTeams.add(broken.id as string);
  account.teamFixtures = [baseMatches()[3]];

  await stubWorld(page, account);
  await startSignedIn(page, account);

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const incomplete = page.getByTestId('feed-incomplete');
  await expect(incomplete, 'a short feed and an incomplete one look identical, so it is stated')
    .toBeVisible();
  await expect(incomplete).toContainText(
    `Fixtures for ${broken.name} could not be loaded, so this list is short by whatever they hold.`);
  await expect(incomplete.getByTestId('feed-incomplete-retry')).toHaveText('Try again');
});

for (const size of WIDTHS) {
  test(`a save made from the keyboard leaves focus on the control that made it, at ${size.label}px`, async ({ page }) => {
    const account = new FakeAccount();
    account.writeLatencyMs = 400;
    await stubWorld(page, account);
    await startSignedIn(page, account);
    await page.setViewportSize({ width: size.width, height: size.height });

    await page.goto(`/matches?date=${localDay(0)}&comp=${COMPETITION.id}`);
    await page.waitForLoadState('networkidle');
    const row = rowFor(page, HOME.name as string);
    const control = saveControlIn(row).first();

    await control.focus();
    await expect(control).toBeFocused();
    await page.keyboard.press('Enter');

    /*
     * THE WHOLE POINT IS WHAT HAPPENS DURING THE WRITE, not only after it.
     *
     * The control reports itself busy with `aria-disabled`, deliberately, rather than with the
     * `disabled` attribute: a disabled button is taken out of the focus order, and the browser
     * moves focus to the body — so a keyboard reader who saved would be returned to the top of the
     * document with no idea whether anything happened. Sampling while `data-pending` is true is
     * what makes this an assertion about that choice.
     */
    await expect(control).toHaveAttribute('data-pending', 'true');
    await expect(control).toHaveAttribute('aria-disabled', 'true');
    await expect(control, 'focus must not leave the control while the write is in flight')
      .toBeFocused();

    // `data-saved` flips optimistically, so the SERVER is only read once the write has landed —
    // otherwise this would assert against the interface's own guess and call it a saved match.
    await writesSettled(page, control);
    await expect(control).toHaveAttribute('data-saved', 'true');
    await expect(control, 'and it is still there once the write has landed').toBeFocused();
    expect(account.saved.size, 'the keyboard press really saved something').toBe(1);

    // Pressed again from the keyboard, it unsaves and still keeps focus.
    await page.keyboard.press('Enter');
    await writesSettled(page, control);
    await expect(control).toHaveAttribute('data-saved', 'false');
    await expect(control).toBeFocused();
    expect(account.saved.size).toBe(0);
  });
}
