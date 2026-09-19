import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { apiContext, QA_EXPERT } from '../support/qa-account';

/**
 * THE PERSONAL JOURNEY, PROVED AGAINST THE RUNNING BACKEND AND A REAL ACCOUNT.
 *
 * The companion to e2e/mocked/journey-proof.spec.ts, and the counts are reported apart from it on
 * purpose. This file asserts the same journey — browse, narrow to one competition, open a fixture,
 * be sent to sign in by a save, sign in, come back with the save done, find it in the feed, find a
 * played fixture's real result there, sign out and be left with nothing personal — against the
 * local FastAPI backend, the local database and the QA account the suite creates. Where the mocked
 * file proves the interface logic against payloads we wrote, this proves it against payloads the
 * backend really serves.
 *
 * WHAT IS ONLY HERE: real fixtures, real scores, a real account, a real token, real authorisation.
 * WHAT IS ONLY IN THE MOCKED FILE: anything needing a failure or a latency arranged on purpose —
 * the in-flight double-press guard, the feed's "nothing we could read" state, and an upstream that
 * has been made to fail in more than one way. Those are marked MOCKED-ONLY there. One exception is
 * carried here deliberately and labelled where it appears: a single browser-side route is failed
 * so that a LIVE session with a real account exercises the feed's retry wording. The backend is
 * not made to fail; the response never leaves the browser.
 *
 * COST, AND THE RULE IT KEEPS
 *  - Every read is a stored read. Nothing here passes `refresh=true`, so no provider request is
 *    issued and no trial allowance is spent. The forecast provider is paused on a spent daily
 *    allowance and must stay untouched.
 *  - The gameforecast counter for the current UTC day is read before the first test and after the
 *    last, and asserted equal. Every provider's counter is printed at both ends, so the claim can
 *    be checked rather than believed.
 *  - Separately, and this is the assertion that actually holds the rule: no request THIS BROWSER
 *    issues may carry `refresh=true`, checked per test against the page's own traffic. The
 *    counters alone cannot carry it — the backend's scheduler moves them by itself; the note on
 *    `afterAll` has the measurement.
 *
 * WHAT IS WRITTEN, AND WHAT IS PUT BACK
 *  - Saved-match rows and followed-team rows on the QA account, and nothing else. Every one is
 *    deleted in `afterEach`. No fixture, forecast, prediction or result is touched, and no real
 *    business record is written at any point.
 *  - The QA account is SHARED with the rest of the live suite. Running two live specs at once will
 *    have them delete each other's rows; run this file on its own.
 *
 * Saving is not a wager. Nothing here stakes, scores or settles anything.
 */

/* --------------------------------------------------------------------------------- the widths */

interface Width {
  label: string;
  width: number;
  height: number;
}

/**
 * The live project is Desktop Chrome at 1440. 360 and 390 are set on the page, so all three widths
 * are asserted against the real backend. They are viewport widths only: this project carries no
 * touch or mobile user-agent emulation, and the mocked file's mobile project is where the journey
 * is seen under iPhone 13 device emulation. Neither is reported as the other.
 */
const WIDTHS: Width[] = [
  { label: '360', width: 360, height: 740 },
  { label: '390', width: 390, height: 844 },
  { label: '1440', width: 1440, height: 900 },
];

const RESTORE_TOLERANCE = 40;
const OVERFLOW_TOLERANCE = 1;

/* ----------------------------------------------------------------------------- the local data */

/** The fields of a fixture payload this spec reads. */
interface Fixture {
  id: string;
  kickoff_utc: string;
  status: string;
  competition: { id: string; name: string };
  home: { id: string; name: string };
  away: { id: string; name: string };
  score?: { home?: number | null; away?: number | null };
}

/** A real session on the local backend: the tokens the sign-in form would have stored. */
interface Session {
  access: string;
  refresh: string;
}

/** Mirrors TOKEN_STORAGE_KEYS in src/services/api-client.ts. */
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

const auth = (bearer: string) => ({ headers: { Authorization: `Bearer ${bearer}` } });

/**
 * Sign the QA account in against the local backend, creating it the first time.
 *
 * Returns BOTH tokens, unlike ensureQaExpertToken, because some tests below start already signed
 * in and the application reads the refresh token as well — `tokenManager.hasTokens()` is false
 * with only one of them, and the session would not boot.
 */
async function qaSession(api: APIRequestContext): Promise<Session> {
  const login = async () => {
    const response = await api.post('/api/v1/auth/login', {
      data: { email: QA_EXPERT.email, password: QA_EXPERT.password },
    });
    return response.ok() ? await response.json() : null;
  };
  let body = await login();
  if (!body) {
    await api.post('/api/v1/auth/register', { data: QA_EXPERT });
    body = await login();
  }
  if (!body) throw new Error('could not sign the QA account in against the local backend');
  return { access: body.access_token, refresh: body.refresh_token };
}

let session: Session | null = null;

async function sessionFor(api: APIRequestContext): Promise<Session> {
  if (!session) session = await qaSession(api);
  return session;
}

/** Rows this file created, removed after every test so a rerun starts from the same place. */
const savedHere = new Set<string>();
const followedHere = new Set<string>();

/**
 * Skip rather than assert against data this database does not hold, and narrow the type while we
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

/**
 * The local calendar day a kick-off falls on, in the browser's emulated timezone.
 *
 * The workspace lists a day in the VIEWER's calendar, so a fixture at 01:00 UTC belongs to the
 * previous day in New York. Taking the date straight off `kickoff_utc` would build a list URL that
 * does not contain the fixture the test then looks for. The timezone is read from the project so
 * the two cannot drift apart.
 */
function localDay(iso: string): string {
  const timeZone = test.info().project.use.timezoneId ?? 'UTC';
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date(iso));
}

/** `refresh=false` keeps this a database read: no provider request is made. */
async function fixturesOn(api: APIRequestContext, day: string): Promise<Fixture[]> {
  const response = await api.get(`/api/v1/matches?date=${day}&refresh=false`);
  if (!response.ok()) return [];
  return ((await response.json()).matches || []) as Fixture[];
}

/**
 * A scheduled fixture on a day that also holds more than one competition, and the competition it
 * belongs to.
 *
 * Both conditions matter. The competition strip only renders when a day has more than one
 * competition to choose between, so a day with one would leave the filter step with no control to
 * press — and a test that then "passed" would have proved nothing about filtering.
 */
async function filterableFixture(api: APIRequestContext): Promise<Fixture | null> {
  for (let offset = 0; offset < 8; offset += 1) {
    const day = await fixturesOn(api, dayOffsetUtc(offset));
    const competitions = new Set(day.map(entry => entry.competition.id));
    if (competitions.size < 2) continue;
    // The competition with the most scheduled fixtures on the day: the filter then visibly removes
    // rows, and the narrowed list still has something in it.
    const counts = new Map<string, Fixture[]>();
    for (const entry of day) {
      if (entry.status !== 'scheduled') continue;
      counts.set(entry.competition.id, [...(counts.get(entry.competition.id) ?? []), entry]);
    }
    const biggest = [...counts.values()].sort((a, b) => b.length - a.length)[0];
    if (biggest && biggest.length > 0) return biggest[0];
  }
  return null;
}

/** A played fixture carrying a real result, inside the feed's window. Never invented. */
async function playedFixture(api: APIRequestContext): Promise<Fixture | null> {
  for (let offset = 0; offset <= 3; offset += 1) {
    const match = (await fixturesOn(api, dayOffsetUtc(-offset)))
      .find(entry => entry.status === 'finished' && typeof entry.score?.home === 'number');
    if (match) return match;
  }
  return null;
}

/** Every provider's spend today, so this file can prove it moved none of it. */
async function providerSpend(api: APIRequestContext): Promise<Record<string, number>> {
  const status = await (await api.get('/api/v1/data-providers/status')).json();
  const spend: Record<string, number> = {};
  for (const provider of status.chain ?? []) spend[provider.name] = provider.budget?.used_today ?? 0;
  spend.gameforecast = status.forecasts?.budget?.used_today ?? 0;
  return spend;
}

/** What the QA account currently holds saved, straight from the API. */
async function savedMatchIds(api: APIRequestContext, bearer: string): Promise<string[]> {
  const response = await api.get('/api/v1/me/saved-matches', auth(bearer));
  if (!response.ok()) return [];
  const body = await response.json();
  return ['upcoming', 'live', 'finished']
    .flatMap(bucket => (body[bucket] ?? []) as Array<{ match_id: string }>)
    .map(entry => entry.match_id);
}

async function saveViaApi(api: APIRequestContext, bearer: string, matchId: string): Promise<void> {
  const response = await api.put(`/api/v1/me/saved-matches/${matchId}`, { ...auth(bearer), data: {} });
  expect(response.ok(), `the QA account could not save ${matchId}`).toBe(true);
  savedHere.add(matchId);
}

async function followViaApi(api: APIRequestContext, bearer: string, teamId: string): Promise<void> {
  const response = await api.put(`/api/v1/me/favourites/teams/${teamId}`, auth(bearer));
  expect(response.ok(), `the QA account could not follow ${teamId}`).toBe(true);
  followedHere.add(teamId);
}

/* ------------------------------------------------------------------------------ page helpers */

const scrollY = (page: Page): Promise<number> => page.evaluate(() => Math.round(window.scrollY));

const scrollState = (page: Page): Promise<{ y: number; furthest: number }> =>
  page.evaluate(() => ({
    y: Math.round(window.scrollY),
    furthest: Math.max(0, Math.round(document.documentElement.scrollHeight - window.innerHeight)),
  }));

const horizontalOverflow = (page: Page): Promise<number> =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

const saveControlIn = (scope: ReturnType<Page['locator']>) => scope.getByTestId('save-match-button');

const rowFor = (page: Page, club: string) =>
  page.getByTestId('fixture-row').filter({ hasText: club }).first();

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/login/);
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 20_000 });
}

/**
 * Sign out the way a reader has to: through the account menu in the header.
 *
 * Found by its popup role rather than its name, because the name changes with the width — below
 * Tailwind's `sm` the visible name is not rendered and the button falls back to an `sr-only`
 * "Account menu". A test that used one name would only ever have covered one width.
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
 * Start the document already signed in, with tokens the backend really issued.
 *
 * Nothing is weakened by this: these are the same two values `authService.login` would have
 * written, obtained from the same endpoint, and every request they authorise is checked by the
 * backend exactly as it would be otherwise. It is used only by the tests that are NOT about the
 * sign-in transition; the journey tests below begin genuinely signed out.
 */
async function startSignedIn(page: Page, tokens: Session): Promise<void> {
  await page.addInitScript(([accessKey, refreshKey, access, refresh]) => {
    window.localStorage.setItem(accessKey, access);
    window.localStorage.setItem(refreshKey, refresh);
  }, [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, tokens.access, tokens.refresh]);
}

/** Wait for a saved-match write to have landed before reading what the backend holds. */
async function writeSettled(control: ReturnType<Page['locator']>): Promise<void> {
  await expect(control).toHaveAttribute('data-pending', 'false');
}

/**
 * Everything this document holds that could be personal, read out of the browser rather than off
 * the screen. An assertion that only looks at what is drawn proves less than it appears to.
 */
async function storageDump(page: Page): Promise<{
  local: Record<string, string>;
  session: Record<string, string>;
  databases: string[];
}> {
  return page.evaluate(async () => {
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
}

/* ----------------------------------------------------- the allowance, before and after it all */

let spendBefore: Record<string, number> = {};

/**
 * Every `/api/v1` request THIS BROWSER made during the current test.
 *
 * The counters alone cannot answer the question this file has to answer, and it took a measurement
 * to see why. See the note on the afterAll hook below.
 */
let browserCalls: string[] = [];

test.beforeAll(async () => {
  const api = await apiContext();
  spendBefore = await providerSpend(api);
  console.log(`[journey-proof] gameforecast used_today BEFORE: ${spendBefore.gameforecast}`);
  console.log(`[journey-proof] all providers BEFORE: ${JSON.stringify(spendBefore)}`);
  await api.dispose();
});

test.beforeEach(async ({ page }) => {
  browserCalls = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/')) browserCalls.push(`${request.method()} ${url.pathname}${url.search}`);
  });
});

test.afterAll(async () => {
  const api = await apiContext();
  const spendAfter = await providerSpend(api);
  console.log(`[journey-proof] gameforecast used_today AFTER:  ${spendAfter.gameforecast}`);
  console.log(`[journey-proof] all providers AFTER:  ${JSON.stringify(spendAfter)}`);

  /*
   * THE FORECAST ALLOWANCE IS THE ONE THAT IS ASSERTED, AND HERE IS THE MEASUREMENT BEHIND THAT.
   *
   * The obvious assertion — every provider's counter is where it started — is not sound against
   * this installation, and a test carrying it would fail on the backend's own housekeeping rather
   * than on anything the browser did. Measured on 2026-09-19 with NOTHING running at all, no
   * browser open and no test in flight: livescore `used_today` read 186 at 15:42:56 and 187 at
   * 15:45:36. The scheduler's `live` task has `interval_seconds: 120` and today's fixture list
   * holds matches in play, so that counter advances by about one every two minutes on its own.
   * A forty-second run straddles such a tick often enough to be flaky, and the failure would say
   * "browsing spent a request" about a request browsing did not make.
   *
   * So the rule is asserted where it is actually decidable:
   *   - gameforecast, the PAUSED provider whose allowance is spent, must not move. Its scheduled
   *     task is paused, nothing else touches it, and any movement here would be ours.
   *   - and no request this browser issued may carry `refresh=true` — the thing the rule actually
   *     forbids — which is checked per test, against the browser's own traffic, and cannot be
   *     confused with the scheduler's.
   * The other counters are printed, not asserted, and the reason is written here rather than left
   * for the next person to rediscover.
   */
  expect(spendAfter.gameforecast,
    'the paused forecast provider must not be asked for anything: its allowance is spent')
    .toBe(spendBefore.gameforecast);
  await api.dispose();
});

test.afterEach(async () => {
  // THE RULE, CHECKED AGAINST THE BROWSER'S OWN TRAFFIC. A page that asked for a refresh would
  // spend a provider request whatever the counters happened to read afterwards.
  const refreshing = browserCalls.filter(call => /[?&]refresh=true\b/i.test(call));
  expect(refreshing, 'nothing this page did may ask the backend to refresh from a provider')
    .toEqual([]);

  if (savedHere.size === 0 && followedHere.size === 0) return;
  const api = await apiContext();
  const tokens = await sessionFor(api);
  const mine = { saved: [...savedHere], followed: [...followedHere] };

  for (const matchId of mine.saved) {
    await api.delete(`/api/v1/me/saved-matches/${matchId}`, auth(tokens.access));
  }
  for (const teamId of mine.followed) {
    await api.delete(`/api/v1/me/favourites/teams/${teamId}`, auth(tokens.access));
  }
  savedHere.clear();
  followedHere.clear();

  /*
   * THE CLEANUP CHECKS ITSELF.
   *
   * A delete that quietly did not happen leaves a row on a shared account for the next run — and
   * the next run then starts from a state nobody chose, which is how a suite ends up asserting
   * about data it did not create. Two rows and one follow were found on this account during this
   * work with no run of any kind in flight, and nothing in the suite had said so. Reading the
   * account back turns that into a failed test instead of a surprise later.
   *
   * Only rows THIS FILE created are named here. Anything else on the account belongs to another
   * spec and is left exactly where it is.
   */
  const remaining = await api.get('/api/v1/me/favourites', auth(tokens.access));
  if (remaining.ok()) {
    const body = await remaining.json();
    const savedLeft = ['upcoming', 'live', 'finished']
      .flatMap(bucket => ((body.saved_matches ?? {})[bucket] ?? []) as Array<{ match_id: string }>)
      .map(entry => entry.match_id);
    expect(mine.saved.filter(id => savedLeft.includes(id)),
      'every saved row this test created must be gone from the QA account').toEqual([]);
    expect(mine.followed.filter(id => (body.team_ids ?? []).includes(id)),
      'every follow this test created must be gone from the QA account').toEqual([]);
  }
  await api.dispose();
});

/* ================================================================================ A1: the journey */

for (const size of WIDTHS) {
  test(`LIVE: the personal journey, end to end, at ${size.label}px`, async ({ page }) => {
    const api = await apiContext();
    const tokens = await sessionFor(api);

    const fixture = required(await filterableFixture(api),
      'this database holds no day with a scheduled fixture and more than one competition');
    const played = required(await playedFixture(api),
      'this database holds no finished fixture with a result inside the feed window');

    // Start from an account holding nothing of this fixture, whatever an earlier run left.
    await api.delete(`/api/v1/me/saved-matches/${fixture.id}`, auth(tokens.access));

    await page.setViewportSize({ width: size.width, height: size.height });
    const day = localDay(fixture.kickoff_utc);

    /* ---------------------------------------------------------------- browse */
    await page.goto(`/matches?date=${day}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    const everything = await page.getByTestId('fixture-row').count();
    expect(everything, 'the day must hold fixtures, or nothing below means anything')
      .toBeGreaterThan(1);
    await expect(rowFor(page, fixture.home.name),
      'the fixture chosen from the database must be on the day the viewer is shown').toBeVisible();

    /* -------------------------------------------------- filter by competition */
    const chip = page.getByTestId('competition-chip-row')
      .getByRole('button', { name: new RegExp(fixture.competition.name, 'i') }).first();
    await chip.click();
    await expect.poll(() => new URL(page.url()).searchParams.get('comp'),
      { message: 'the chosen competition must be in the URL, so the list is a link' })
      .toBe(fixture.competition.id);
    await expect(chip).toHaveAttribute('aria-pressed', 'true');

    const filtered = await page.getByTestId('fixture-row').count();
    expect(filtered, 'the filter must actually remove fixtures, or it is not a filter')
      .toBeLessThan(everything);
    expect(filtered).toBeGreaterThan(0);
    const listPath = new URL(page.url()).pathname + new URL(page.url()).search;
    expect(await horizontalOverflow(page),
      `the filtered list must not scroll sideways at ${size.label}px`)
      .toBeLessThanOrEqual(OVERFLOW_TOLERANCE);

    /* -------------------------------------------------------- open a fixture */
    await rowFor(page, fixture.home.name).locator(`a[href^="/match/${fixture.id}"]`).first().click();
    await page.waitForURL(`**/match/${fixture.id}**`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: fixture.home.name }).first()).toBeVisible();

    /* ------------------------------ a save sends a signed-out visitor to sign in */
    const control = saveControlIn(page).first();
    await expect(control, 'a signed-out visitor gets a control that explains itself')
      .toHaveAttribute('title', /^Sign in to save/i);
    await control.click();
    await page.waitForURL('**/login**');
    await expect(page.getByRole('link', { name: /create a new account/i }),
      'registration is reachable from the same handoff').toBeVisible();
    await expect(page.getByTestId('login-save-intent'))
      .toContainText(`${fixture.home.name} versus ${fixture.away.name}`);

    /* ----------------------------------------------------------------- sign in */
    await signInThroughTheForm(page);
    savedHere.add(fixture.id);

    /* ----------------- back where they were, with the save actually completed */
    // The save was pressed on the FIXTURE page, so that is where the handoff returns them. The
    // list is one control away, and the URL they were on rides in `?from=`.
    await expect(page, 'the reader comes back to the page they pressed save on')
      .toHaveURL(new RegExp(`/match/${fixture.id}`));
    const returned = saveControlIn(page).first();
    await expect(returned, 'the save is DONE, not merely offered again')
      .toHaveAttribute('data-saved', 'true');
    await expect(returned).toHaveText(/^Saved$/);

    // The BACKEND is what settles this, not the control's own optimism.
    await expect.poll(async () => (await savedMatchIds(api, tokens.access)).filter(id => id === fixture.id).length,
      { message: 'the backend holds exactly one saved row for this fixture' }).toBe(1);

    /* ------------------------------- and the SAME filtered list is one control away */
    await page.getByTestId('back-to-results').click();
    await page.waitForURL('**/matches**');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    expect(new URL(page.url()).pathname + new URL(page.url()).search,
      'the competition filter and the date survived the whole sign-in round trip').toBe(listPath);
    await expect(page.getByTestId('active-filter-chip').filter({ hasText: fixture.competition.name }))
      .toBeVisible();
    expect(await page.getByTestId('fixture-row').count(),
      'and it is the narrowed list, not the whole day').toBe(filtered);
    await expect(saveControlIn(rowFor(page, fixture.home.name)).first(),
      'the star in the list agrees with the control that made the save')
      .toHaveAttribute('data-saved', 'true');

    /* ------------------------------------------------- it is in the personal feed */
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('saved-matches')).toBeVisible();
    await expect(page.getByTestId('saved-match').filter({ hasText: fixture.home.name }).first())
      .toBeVisible();
    await expect(page.getByTestId('saved-matches-empty'),
      'a feed holding a save must never render the empty state').toHaveCount(0);
    expect(await horizontalOverflow(page),
      `the feed must not scroll sideways at ${size.label}px`).toBeLessThanOrEqual(OVERFLOW_TOLERANCE);

    /* ------------------- a real finished fixture's real result is in that history */
    await saveViaApi(api, tokens.access, played.id);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const results = page.getByTestId('feed-group-result');
    await expect(results, 'a played fixture belongs in the results group of the feed').toBeVisible();
    const playedRow = results.getByTestId('saved-match').filter({ hasText: played.home.name }).first();
    await expect(playedRow).toBeVisible();
    // The score the DATABASE holds, read out of the database and looked for on the page. Nothing
    // here composes a result; if the backend's row changes, this assertion changes with it.
    const homeGoals = played.score?.home as number;
    const awayGoals = played.score?.away as number;
    await expect(playedRow,
      `the feed must show the result this database holds (${homeGoals}-${awayGoals})`)
      .toContainText(String(homeGoals));
    await expect(playedRow).toContainText(String(awayGoals));

    /* ------------------------------------------------------------- sign out */
    /*
     * THE POSITIVE CONTROL FIRST. "The token is gone" proves nothing unless the same read can see
     * a token when there is one — a dump that always came back empty would satisfy every
     * assertion below on a page that had never signed in at all.
     */
    const beforeSignOut = await storageDump(page);
    expect(beforeSignOut.local[ACCESS_TOKEN_KEY],
      'the session really is in localStorage before we sign out of it').toBeTruthy();

    await signOutThroughTheHeader(page);

    /*
     * NOTHING PERSONAL IS LEFT BEHIND. What was checked, so the claim can be weighed:
     *   - every key and value in localStorage — the two token keys by name, and the whole store
     *     searched for the account's own email, its saved fixture ids and the token strings;
     *   - every key and value in sessionStorage — this is where `sp.scroll-positions` lives, which
     *     is NOT expected to be deleted, so it is checked for content instead: a scroll offset is
     *     not personal, an account id in it would be;
     *   - the cookie jar for this context;
     *   - which IndexedDB databases the origin holds;
     *   - and last, that a fresh navigation to a protected page is refused and carries no bearer
     *     token. A token still in storage fails that even when the screen looks right.
     */
    const dump = await storageDump(page);
    const cookies = await page.context().cookies();
    await test.info().attach(`storage-after-sign-out-${size.label}`, {
      contentType: 'application/json',
      body: JSON.stringify({ ...dump, cookies: cookies.map(c => c.name) }, null, 2),
    });

    expect(dump.local[ACCESS_TOKEN_KEY], 'the access token is gone from localStorage').toBeUndefined();
    expect(dump.local[REFRESH_TOKEN_KEY], 'and so is the refresh token').toBeUndefined();

    const held = JSON.stringify({ ...dump.local, ...dump.session, cookies });
    expect(held, 'no store may still carry the account it was signed in as').not.toContain(QA_EXPERT.email);
    expect(held, 'nor the fixture that was saved').not.toContain(fixture.id);
    expect(held, 'nor the played fixture').not.toContain(played.id);

    const authorized: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/api/v1/') && request.headers()['authorization']) {
        authorized.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
    });
    await page.goto('/dashboard');
    await page.waitForURL('**/login**');
    await expect(page.getByTestId('saved-matches')).toHaveCount(0);
    expect(authorized, 'a signed-out document must not send a bearer token to anything').toEqual([]);

    // And the rows really are still on the account for afterEach to remove: signing out of the
    // browser is not the same event as deleting data, and must not be confused with it.
    const stillHeld = await savedMatchIds(api, tokens.access);
    expect(stillHeld, 'signing out does not delete what the account saved').toContain(fixture.id);

    await api.dispose();
  });
}

/* ============================================================== A2: the parts easy to fudge */

for (const size of WIDTHS) {
  test(`LIVE: Back restores the previous list, its filters and its position at ${size.label}px`, async ({ page }) => {
    const api = await apiContext();
    const fixture = required(await filterableFixture(api),
      'this database holds no day with a scheduled fixture and more than one competition');
    const day = localDay(fixture.kickoff_utc);
    await page.setViewportSize({ width: size.width, height: size.height });

    /*
     * TWO CLAIMS, MEASURED ON THE LIST EACH ONE NEEDS.
     *
     * The filters are proved on the FILTERED list, which is the journey's own list. The position
     * is proved on the WHOLE day, because a real competition on this installation holds four or
     * five fixtures and a 1440x900 window shows all of them — a scroll-restoration assertion on a
     * page that cannot scroll asserts nothing at all, and quietly passing it would be exactly the
     * loose assertion this file exists to avoid. The mocked companion measures both together on a
     * list crowded on purpose.
     */

    /* ------------------------------------------- the filters come back */
    await page.goto(`/matches?date=${day}&comp=${fixture.competition.id}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    await expect(page.getByTestId('active-filter-chip').filter({ hasText: fixture.competition.name }))
      .toBeVisible();
    const narrowed = await page.getByTestId('fixture-row').count();

    await rowFor(page, fixture.home.name).locator(`a[href^="/match/${fixture.id}"]`).first().click();
    await page.waitForURL('**/match/**');
    await page.goBack();
    await page.waitForURL(url => url.pathname === '/matches');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    expect(new URL(page.url()).searchParams.get('comp')).toBe(fixture.competition.id);
    await expect(page.getByTestId('active-filter-chip').filter({ hasText: fixture.competition.name }),
      'Back brings the filter back, not merely the address').toBeVisible();
    expect(await page.getByTestId('fixture-row').count(),
      'and the same narrowed set of fixtures').toBe(narrowed);

    /* ------------------------------------------- the position comes back */
    await page.goto(`/matches?date=${day}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('fixture-list')).toBeVisible();

    // The LAST fixture, not the first: a click scrolls its target into view, so opening the first
    // row would quietly scroll the list back up and this would measure that instead.
    const lastFixture = page.getByTestId('fixture-list').locator('a[href^="/match/"]').last();
    await lastFixture.scrollIntoViewIfNeeded();
    await expect(lastFixture).toBeInViewport();
    const left = await scrollY(page);
    expect(left, `the whole day must be taller than a ${size.label}px window for this to mean anything`)
      .toBeGreaterThan(200);

    await lastFixture.click();
    await page.waitForURL('**/match/**');
    await expect.poll(() => scrollY(page), { message: 'the fixture page opens at its top' })
      .toBeLessThanOrEqual(2);

    await page.goBack();
    await page.waitForURL(url => url.pathname === '/matches');
    await expect(page.getByTestId('fixture-list')).toBeVisible();
    /*
     * BOUNDED ON BOTH SIDES. This read `y >= left - RESTORE_TOLERANCE`, a floor and nothing else,
     * so a restore that OVERSHOT passed — and on a list taller than the window that covers every
     * offset between the reader's place and the bottom of the document. Measured against a mutant
     * that discarded the remembered offset and sent Back to the very bottom: the mocked companion
     * stayed green at 360 and 390 with the reader 648px and 572px away from where they had been.
     * A restore has a place it is supposed to land on, so this is a distance from it.
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
      timeout: 20_000,
    }).toBe('restored');

    // And it stays there: the workspace rewrites its own URL shortly after mounting, and a rewrite
    // counted as a forward move would undo the restore just late enough for one poll to have passed.
    await page.waitForTimeout(700);
    const settled = await scrollState(page);
    expect(Math.abs(settled.y - Math.min(left, settled.furthest)),
      `a URL rewrite after Back must leave the reader where the restore put them (at ${settled.y}, wanted ${Math.min(left, settled.furthest)})`)
      .toBeLessThanOrEqual(RESTORE_TOLERANCE);

    await api.dispose();
  });
}

test('LIVE: a save resumed after sign-in on an already-saved match leaves one saved match, not two', async ({ page }) => {
  const api = await apiContext();
  const tokens = await sessionFor(api);
  const fixture = required(await filterableFixture(api), 'this database holds no scheduled fixture');

  // The account already holds this save from an earlier visit. The reader then presses the star
  // again while signed out — a lapsed session, another device — and signs in. `useResumeSave`
  // always writes `saved = true`, so a second row would appear here if anything were not idempotent.
  await saveViaApi(api, tokens.access, fixture.id);
  expect((await savedMatchIds(api, tokens.access)).filter(id => id === fixture.id).length).toBe(1);

  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');
  const control = saveControlIn(page).first();
  await expect(control).toHaveAttribute('title', /^Sign in to save/i);
  await control.click();
  await page.waitForURL('**/login**');
  await signInThroughTheForm(page);

  await expect(page).toHaveURL(new RegExp(`/match/${fixture.id}`));
  await expect(saveControlIn(page).first()).toHaveAttribute('data-saved', 'true');

  const held = await savedMatchIds(api, tokens.access);
  expect(held.filter(id => id === fixture.id).length,
    'the backend holds one row for this fixture, not two').toBe(1);

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('saved-matches')).toBeVisible();
  await expect(page.getByTestId('saved-match').filter({ hasText: fixture.home.name }),
    'and the feed shows it once').toHaveCount(1);

  await api.dispose();
});

/**
 * A LIVE session with ONE BROWSER-SIDE ROUTE FAILED.
 *
 * The backend is not made to fail and nothing on it is changed: a single `GET /api/v1/teams/{id}`
 * is answered inside the browser with a 503 so that the feed has one follow it genuinely cannot
 * read. Everything else in this test — the account, the token, the follows, the fixtures behind
 * the other follow — is real. Reported as its own kind of evidence, because it is neither a fully
 * mocked run nor an untouched live one.
 *
 * The companion mocked file covers the OTHER branch, where nothing at all can be shown; that state
 * needs a readable follow holding no fixtures in the window, which this database does not have.
 */
test('LIVE (one route failed in the browser): a feed short because a follow failed says so, and offers a retry', async ({ page }) => {
  const api = await apiContext();
  const tokens = await sessionFor(api);

  const fixture = required(await filterableFixture(api), 'this database holds no scheduled fixture');
  const readable = fixture.home;
  const broken = fixture.away;
  expect(readable.id, 'two distinct teams are needed').not.toBe(broken.id);

  await followViaApi(api, tokens.access, readable.id);
  await followViaApi(api, tokens.access, broken.id);
  await startSignedIn(page, tokens);

  await page.route(`**/api/v1/teams/${broken.id}`, route =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Simulated upstream failure (browser-side, this test only)' }),
    }));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const incomplete = page.getByTestId('feed-incomplete');
  await expect(incomplete, 'a short feed and an incomplete one look identical, so it is stated')
    .toBeVisible();
  // THE EXACT SENTENCE, naming the follow whose fixtures nobody managed to read.
  await expect(incomplete).toContainText(
    `Fixtures for ${broken.name} could not be loaded, so this list is short by whatever they hold.`);
  await expect(incomplete.getByTestId('feed-incomplete-retry')).toHaveText('Try again');
  // It is a failure, not an absence: none of the empty states may be on the page.
  await expect(page.getByTestId('feed-window-empty')).toHaveCount(0);
  await expect(page.getByTestId('saved-matches-empty')).toHaveCount(0);

  // And the retry really retries: with the route repaired, pressing it clears the notice.
  await page.unroute(`**/api/v1/teams/${broken.id}`);
  await incomplete.getByTestId('feed-incomplete-retry').click();
  await expect(page.getByTestId('feed-incomplete'),
    'once the follow can be read again, the page stops saying it could not').toHaveCount(0);

  await api.dispose();
});

for (const size of WIDTHS) {
  test(`LIVE: a save made from the keyboard leaves focus on the control that made it, at ${size.label}px`, async ({ page }) => {
    const api = await apiContext();
    const tokens = await sessionFor(api);
    const fixture = required(await filterableFixture(api), 'this database holds no scheduled fixture');
    await api.delete(`/api/v1/me/saved-matches/${fixture.id}`, auth(tokens.access));

    await startSignedIn(page, tokens);
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto(`/matches?date=${localDay(fixture.kickoff_utc)}&comp=${fixture.competition.id}`);
    await page.waitForLoadState('networkidle');

    const control = saveControlIn(rowFor(page, fixture.home.name)).first();
    await control.focus();
    await expect(control).toBeFocused();
    savedHere.add(fixture.id);
    await page.keyboard.press('Enter');

    /*
     * THE POINT IS WHAT HAPPENS DURING THE WRITE, not only after it.
     *
     * The control reports itself busy with `aria-disabled`, deliberately, rather than with the
     * `disabled` attribute: a disabled button leaves the focus order and the browser moves focus
     * to the body, so a keyboard reader who saved would be dropped at the top of the document with
     * no idea whether anything had happened.
     */
    await expect(control).toHaveAttribute('aria-disabled', 'true');
    await expect(control, 'focus must not leave the control while the write is in flight')
      .toBeFocused();

    await writeSettled(control);
    await expect(control).toHaveAttribute('data-saved', 'true');
    await expect(control, 'and it is still there once the write has landed').toBeFocused();
    expect(await savedMatchIds(api, tokens.access),
      'the keyboard press really saved something on the account').toContain(fixture.id);

    // Pressed again from the keyboard it unsaves, still without moving focus.
    await page.keyboard.press('Enter');
    await writeSettled(control);
    await expect(control).toHaveAttribute('data-saved', 'false');
    await expect(control).toBeFocused();
    expect(await savedMatchIds(api, tokens.access),
      'and the removal reached the backend too').not.toContain(fixture.id);

    await api.dispose();
  });
}
