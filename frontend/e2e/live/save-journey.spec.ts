import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { apiContext, ensureQaExpertToken, QA_EXPERT } from '../support/qa-account';

/**
 * The save journey end to end: find a match, be asked to sign in, sign in, come back, and find the
 * save actually done.
 *
 * WHY THIS IS A LIVE SPEC. Every step is a handoff between the router, the auth context and the
 * favourites API, and stubbing any one of them would let the whole thing pass while the real
 * journey stays broken — which is the state a reviewer found it in: the sign-in form threw away
 * the page the visitor came from, and the match page had no save control at all.
 *
 * COST AND CLEANLINESS
 *  - Every read uses the data already in the local database. Nothing here passes `refresh=true`,
 *    so no provider request is issued and no allowance is spent.
 *  - The only rows written are saved-match rows on the QA account the suite already creates, and
 *    `afterEach` deletes every one of them. No fixture, prediction or forecast is touched.
 */

/**
 * The fields of a fixture payload this spec reads.
 *
 * Declared here rather than reused from `ApiMatch` in e2e/support: that type describes the
 * forecast-shaped payload the mocked specs assert on, and a journey needs the competition and the
 * team names instead.
 */
interface JourneyFixture {
  id: string;
  kickoff_utc: string;
  status: string;
  competition: { id: string; name: string };
  home: { name: string };
  away: { name: string };
  score?: { home?: number | null; away?: number | null };
}

/**
 * The recorders the focus test installs in the page.
 *
 * Declared rather than reached for through `any`: these are the only four names this spec ever
 * adds to the page's global object, and naming them keeps the lint clean on both sides.
 */
interface Probe {
  __focusSamples: string[];
  __statusSeen: string[];
  __focusTimer: number;
  __statusWatcher?: MutationObserver;
}

/** Saved-match rows this spec created, removed after each test so a rerun starts from the same place. */
const savedInThisTest = new Set<string>();
let token = '';

async function qaToken(api: APIRequestContext): Promise<string> {
  if (!token) token = await ensureQaExpertToken(api);
  return token;
}

/**
 * Skip rather than assert against data that is not in this database, and narrow the type while we
 * are at it. `test.skip` throws when the condition holds, so nothing past it runs with a null.
 */
function required<T>(value: T | null, reason: string): T {
  test.skip(value === null, reason);
  return value as T;
}

/**
 * The local calendar day a kick-off falls on, in the browser's emulated timezone.
 *
 * The workspace lists a day in the VIEWER's calendar (see `localDateString`), so a fixture at
 * 01:00 UTC belongs to the previous day in New York. Taking the date straight off `kickoff_utc`
 * would build a list URL that does not contain the fixture the test then looks for. The timezone
 * is read from the project rather than repeated here, so the two cannot drift apart.
 */
function localDay(iso: string): string {
  const timeZone = test.info().project.use.timezoneId ?? 'UTC';
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date(iso));
}

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page): Promise<void> {
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  // The redirect follows the auth response, so wait for the route rather than for the network to
  // fall idle: the sign-in page itself is idle long before the token comes back.
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

async function fixturesOn(api: APIRequestContext, day: string): Promise<JourneyFixture[]> {
  // refresh=false keeps this a database read: no provider request is made
  const response = await api.get(`/api/v1/matches?date=${day}&refresh=false`);
  if (!response.ok()) return [];
  return ((await response.json()).matches || []) as JourneyFixture[];
}

function dayOffsetUtc(offset: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

/** A scheduled fixture from the local database, or null. */
async function upcomingFixture(api: APIRequestContext): Promise<JourneyFixture | null> {
  for (let offset = 0; offset < 8; offset += 1) {
    const match = (await fixturesOn(api, dayOffsetUtc(offset))).find(entry => entry.status === 'scheduled');
    if (match) return match;
  }
  return null;
}

/** A played fixture that carries a result, or null. Never invented: the test skips instead. */
async function finishedFixture(api: APIRequestContext): Promise<JourneyFixture | null> {
  for (let offset = 0; offset < 8; offset += 1) {
    const match = (await fixturesOn(api, dayOffsetUtc(-offset)))
      .find(entry => entry.status === 'finished' && typeof entry.score?.home === 'number');
    if (match) return match;
  }
  return null;
}

/** The list URL a reader would have been on: one day, narrowed to one competition. */
function filteredList(fixture: JourneyFixture): string {
  return `/matches?date=${localDay(fixture.kickoff_utc)}&comp=${fixture.competition.id}`;
}

/**
 * Hand the sign-in form a navigation state it did not create itself.
 *
 * React Router keeps navigation state on the history entry, as `state.usr`. This init script
 * writes one there before the application's own scripts run, which is both the only way a test can
 * inject one and the shape an attacker would have to produce. The value travels through
 * sessionStorage rather than as a script argument because the script is registered once and runs
 * on every navigation, while the state under test changes from case to case.
 *
 * The page must already be on the application's own origin when `gotoLoginWith` is called:
 * sessionStorage is per origin, and there is none on about:blank.
 */
const LOGIN_STATE_KEY = 'e2e:login-state';

async function installLoginStateChannel(page: Page): Promise<void> {
  await page.addInitScript((key) => {
    if (window.location.pathname !== '/login') return;
    const raw = window.sessionStorage.getItem(key);
    if (raw === null) return;
    const current = (window.history.state ?? {}) as Record<string, unknown>;
    window.history.replaceState({ ...current, usr: JSON.parse(raw) }, '', '/login');
  }, LOGIN_STATE_KEY);
}

async function gotoLoginWith(page: Page, state: unknown): Promise<void> {
  await page.evaluate(
    ([key, value]) => window.sessionStorage.setItem(key as string, JSON.stringify(value)),
    [LOGIN_STATE_KEY, state],
  );
  await page.goto('/login');
}

/** A team's own goals, as the fixture row renders them: the name and then the number. */
function scoreBeside(team: string, goals: number): RegExp {
  return new RegExp(`${team.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*${goals}(?!\\d)`);
}

const currentPath = (page: Page): string => {
  const url = new URL(page.url());
  return url.pathname + url.search;
};

test.afterEach(async () => {
  if (savedInThisTest.size === 0) return;
  const api = await apiContext();
  const bearer = await qaToken(api);
  for (const matchId of savedInThisTest) {
    await api.delete(`/api/v1/me/saved-matches/${matchId}`, {
      headers: { Authorization: `Bearer ${bearer}` },
    });
  }
  savedInThisTest.clear();
  await api.dispose();
});

/**
 * THE STAR IN THE LIST, END TO END — the entry point a reviewer actually used.
 *
 * It used to get halfway: the visitor was sent to sign in, came back to the right filtered list,
 * and found the match exactly as unsaved as they had left it, with nothing on the sign-in form
 * ever having said a save was waiting. The list had a sign-in handoff of its own that carried
 * only where to come back to. Every assertion below is one of the halves that has to hold at the
 * same time for the journey to be finished rather than merely started.
 */
test('the star in the fixture list finishes the save across sign-in, and keeps the list it was pressed on', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');
  const list = filteredList(fixture);

  await page.goto(list);
  await page.waitForLoadState('networkidle');
  // This fixture's own row, not whichever row happens to be first: the assertions below name it.
  const rowFor = () => page.locator(`[data-testid="fixture-row"][data-match-id="${fixture.id}"]`);
  await expect(rowFor()).toBeVisible();

  // Signed out, the star is an invitation and says so — not a dead control, and not a lie about
  // what is saved.
  const star = rowFor().locator('[data-testid="save-match-button"]');
  await expect(star).toHaveAccessibleName(/^sign in to save/i);

  await star.click();
  savedInThisTest.add(fixture.id);
  await page.waitForURL(url => url.pathname === '/login', { timeout: 10_000 });

  // The form says why the visitor is looking at it, and which match is waiting. The list star used
  // to arrive here silently.
  await expect(page.getByTestId('login-save-intent')).toContainText(fixture.home.name);

  await signInThroughTheForm(page);

  // The date AND the competition filter are still in the URL. Before this journey existed the
  // visitor landed on a role dashboard and had to set both again.
  await expect.poll(() => currentPath(page)).toBe(list);

  // And the save they asked for actually happened, without them finding the star a second time.
  await expect(rowFor().locator('[data-testid="save-match-button"]')).toHaveAttribute('data-saved', 'true');

  // Not just in this tab's store: on the server.
  const bearer = await qaToken(api);
  const stored = await api.get('/api/v1/me/saved-matches', { headers: { Authorization: `Bearer ${bearer}` } });
  expect(JSON.stringify(await stored.json())).toContain(fixture.id);

  // ...and therefore on the dashboard they were sent to save it to.
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('[data-testid="saved-match"]').filter({ hasText: fixture.home.name }))
    .toHaveCount(1);

  // Back on the list, opening the fixture still offers a way back that keeps the competition.
  await page.goto(list);
  await page.waitForLoadState('networkidle');
  await rowFor().locator('a[href^="/match/"]').first().click();
  await page.waitForURL(url => url.pathname === `/match/${fixture.id}`, { timeout: 10_000 });
  await page.getByTestId('back-to-results').click();
  await expect.poll(() => currentPath(page)).toBe(list);
  await api.dispose();
});

test('the save a visitor started finishes itself after sign-in, and the match is on the dashboard', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');

  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');

  const control = page.locator('[data-testid="save-match-button"]');
  await expect(control).toHaveAttribute('data-saved', 'false');
  await control.click();
  savedInThisTest.add(fixture.id);

  await page.waitForURL(url => url.pathname === '/login', { timeout: 10_000 });
  // The form says what is waiting, so the visitor knows why they are looking at it.
  await expect(page.getByTestId('login-save-intent')).toContainText(fixture.home.name);

  await signInThroughTheForm(page);

  await expect.poll(() => new URL(page.url()).pathname).toBe(`/match/${fixture.id}`);
  // Saved, without the visitor having to find the control again.
  await expect(page.locator('[data-testid="save-match-button"]')).toHaveAttribute('data-saved', 'true');

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('[data-testid="saved-match"]').filter({ hasText: fixture.home.name }))
    .toHaveCount(1);
  await api.dispose();
});

test('the match-page control saves and unsaves, and says which it is', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');

  await page.goto('/login');
  await signInThroughTheForm(page);
  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');

  const control = page.locator('[data-testid="save-match-button"]');
  // The state is in the accessible name and in aria-pressed, not only in the fill of an icon or
  // in its colour.
  await expect(control).toHaveAttribute('aria-pressed', 'false');
  await expect(control).toHaveAccessibleName(/^save$/i);

  await control.click();
  savedInThisTest.add(fixture.id);
  await expect(control).toHaveAttribute('aria-pressed', 'true');
  await expect(control).toHaveAccessibleName(/^saved$/i);
  // Stated in words that are announced, not left to be inferred from a filled bookmark.
  await expect(page.getByRole('status').filter({ hasText: 'Saved to your dashboard.' })).toBeVisible();

  // And it is really on the server, not only in this tab's store.
  const bearer = await qaToken(api);
  const stored = await api.get('/api/v1/me/saved-matches', { headers: { Authorization: `Bearer ${bearer}` } });
  expect(JSON.stringify(await stored.json())).toContain(fixture.id);

  await control.click();
  await expect(control).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('status').filter({ hasText: 'Removed from your saved matches.' })).toBeVisible();
  savedInThisTest.delete(fixture.id);

  const after = await api.get('/api/v1/me/saved-matches', { headers: { Authorization: `Bearer ${bearer}` } });
  expect(JSON.stringify(await after.json())).not.toContain(fixture.id);
  await api.dispose();
});

/**
 * WHERE THE KEYBOARD IS, AT EVERY MOMENT OF THE WRITE.
 *
 * Measured before this was fixed: focus the match-page save control, press Enter, and
 * `document.activeElement` was `body` for the whole of the request and still `body` afterwards.
 * The control was `disabled` while its write was in flight, and a browser blurs what it disables
 * — so a keyboard or screen-reader user was dropped at the top of the document, and the
 * `role="status"` announcement that followed arrived with focus nowhere to anchor it.
 *
 * A single check after the fact would not catch a regression of that: focus can be lost and
 * restored, and "it ended up in the right place" is not the claim. So focus is SAMPLED for the
 * whole write, and every sample has to be the control.
 */
test('a save made from the keyboard never moves focus off the control that made it', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');

  await page.goto('/login');
  await signInThroughTheForm(page);
  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');

  const control = page.locator('[data-testid="save-match-button"]');
  await expect(control).toHaveAttribute('data-saved', 'false');

  // Reachable from the keyboard at all, which is the precondition for everything below.
  await control.focus();
  await expect(control).toBeFocused();

  // Start recording only once focus is where the test put it, so the samples are about the write
  // and not about the moment before it. The status line is recorded through a MutationObserver
  // rather than sampled, so a state that renders between two ticks is still seen.
  await page.evaluate(() => {
    const probe = window as unknown as Probe;
    probe.__focusSamples = [];
    probe.__statusSeen = [];
    probe.__focusTimer = window.setInterval(() => {
      const active = document.activeElement;
      probe.__focusSamples.push(
        active === null ? 'null' : active.getAttribute('data-testid') ?? active.tagName,
      );
    }, 5);
    const status = document.querySelector('[role="status"]');
    if (status) {
      probe.__statusWatcher = new MutationObserver(() => {
        const text = (status.textContent ?? '').trim();
        if (text && probe.__statusSeen[probe.__statusSeen.length - 1] !== text) probe.__statusSeen.push(text);
      });
      probe.__statusWatcher.observe(status, { childList: true, characterData: true, subtree: true });
    }
  });

  await page.keyboard.press('Enter');
  savedInThisTest.add(fixture.id);
  await expect(page.getByRole('status').filter({ hasText: 'Saved to your dashboard.' })).toBeVisible();

  const recorded = await page.evaluate(() => {
    const probe = window as unknown as Probe;
    window.clearInterval(probe.__focusTimer);
    probe.__statusWatcher?.disconnect();
    return { focus: probe.__focusSamples, status: probe.__statusSeen };
  });

  expect(recorded.focus.length, 'the sampler must have run while the write was in flight').toBeGreaterThan(0);
  expect(
    [...new Set(recorded.focus)],
    'focus must stay on the save control for the whole write; "BODY" is the regression this test exists for',
  ).toEqual(['save-match-button']);
  await expect(control).toBeFocused();

  // The pending state was stated while it was true, not skipped over on the way to a result.
  expect(recorded.status, 'the write must be announced while it is in flight, not only once it lands')
    .toContain('Saving this match…');
  expect(recorded.status[recorded.status.length - 1]).toBe('Saved to your dashboard.');

  // The control is never the HTML `disabled` that caused this: a write in flight says so through
  // aria-disabled, which does not take the control out of the focus order.
  await expect(control).toBeEnabled();
  await expect(control).toHaveAttribute('aria-pressed', 'true');
  await expect(control).toHaveAccessibleName(/^saved$/i);
  await api.dispose();
});

/**
 * G3: the way back to results, after the sign-in round trip has rewritten the history behind it.
 *
 * Measured before this was fixed: the control degraded from a real Back to a link to the whole
 * day — the right date and none of the reader's filters, a 23-row list where they had chosen one
 * competition.
 */
test('the way back to results still carries the competition after a sign-in round trip', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');
  const list = filteredList(fixture);

  await page.goto(list);
  await page.waitForLoadState('networkidle');
  const row = page.locator(`[data-testid="fixture-row"][data-match-id="${fixture.id}"]`);
  await expect(row).toBeVisible();
  await row.locator('a[href^="/match/"]').first().click();
  await page.waitForURL(url => url.pathname === `/match/${fixture.id}`, { timeout: 10_000 });

  // Walked here, so the control is the real Back it has always been.
  await expect(page.getByTestId('back-to-results')).toHaveText(/back to results/i);

  await page.locator('[data-testid="save-match-button"]').click();
  savedInThisTest.add(fixture.id);
  await page.waitForURL(url => url.pathname === '/login', { timeout: 10_000 });
  await signInThroughTheForm(page);
  await expect.poll(() => new URL(page.url()).pathname).toBe(`/match/${fixture.id}`);

  // Back is no longer the answer here — the form replaced its own history entry — so the control
  // is a link. It must still be a link to the list the reader chose.
  await page.getByTestId('back-to-results').click();
  await expect.poll(() => currentPath(page)).toBe(list);
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  await expect(page.getByTestId('active-filter-chip').filter({ hasText: fixture.competition.name }))
    .toBeVisible();
  await api.dispose();
});

/**
 * The way back to results is only ever a way back to RESULTS.
 *
 * The list a fixture was opened from travels in the fixture's own URL, which means anyone can
 * compose one. The control's label is a promise about where it goes, so the value is held to the
 * same allow-list as a sign-in return destination AND to being a fixture list; anything else gets
 * the honest day fallback instead of a sentence that is not true.
 */
test('a "back to results" the fixture URL asks for must be a results list on this application', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');
  const list = filteredList(fixture);
  const control = page.getByTestId('back-to-results');

  // Opened directly, so there is no history to go back to and the parameter is what decides.
  for (const refused of ['/dashboard', '/login', 'https://evil.example/steal', '/..//evil.example/steal']) {
    await page.goto(`/match/${fixture.id}?from=${encodeURIComponent(refused)}`);
    await page.waitForLoadState('networkidle');
    await expect(control, `${refused} must not become "back to results"`).toHaveText(/all matches on/i);
  }

  /*
   * ACCEPTED: every route that actually renders the fixture list.
   *
   * `/predictions/today` and `/predictions/tomorrow` are the same MatchdayWorkspace as `/matches`
   * with a day preselected, they hold the reader's competition filter in their own query string
   * the same way, and they are linked from the footer, the saved-matches panel and the following
   * panel. They were missing from the allow-list, so the journey this parameter exists for was
   * still broken from them: a reader on `/predictions/today?comp=<one competition>` who saved
   * while signed out came back to "All matches on <day>" and the whole unfiltered day. Listing
   * `/matches` alone would have let that ship, which is why the accepted half is a loop too.
   */
  const presetList = `/predictions/today?comp=${fixture.competition.id}`;
  for (const accepted of [list, presetList, '/predictions/tomorrow?comp=' + fixture.competition.id]) {
    await page.goto(`/match/${fixture.id}?from=${encodeURIComponent(accepted)}`);
    await page.waitForLoadState('networkidle');
    await expect(control, `${accepted} is a fixture list and must be offered as one`)
      .toHaveText(/back to results/i);
    await control.click();
    await expect.poll(() => currentPath(page)).toBe(accepted);
  }
  await api.dispose();
});

test('a return destination that leaves this application is refused', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');
  const list = filteredList(fixture);

  await page.goto('/login');
  await signInThroughTheForm(page);
  const appOrigin = new URL(page.url()).origin;

  await installLoginStateChannel(page);

  // Already signed in, so the form redirects the moment it reads the state: where it lands is the
  // answer to "was this destination accepted?".
  const arriveAtLoginWith = async (from: unknown): Promise<URL> => {
    await gotoLoginWith(page, { from });
    await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 10_000 });
    return new URL(page.url());
  };

  // A path on this application is honoured, filters and all. Without this the assertions below
  // would pass just as well against a form that refused every destination it was ever given.
  const honoured = await arriveAtLoginWith(list);
  expect(honoured.pathname + honoured.search).toBe(list);

  const refused = [
    'https://evil.example/steal',        // an absolute URL on another origin
    'http://localhost:3100.evil.test/x', // an absolute URL that merely starts like ours
    '//evil.example/steal',              // protocol-relative: the same thing without a scheme
    '/\\evil.example/steal',             // the backslash form, which the URL parser folds into "//"
    'javascript:alert(document.cookie)',
    'data:text/html,<script>alert(1)</script>',
    '/matches\n/../../evil',             // a control character, which some parsers strip before resolving
    '/login',                            // the form itself: a loop, not a return
    // The dot-segment form of the protocol-relative URL. It looks like an ordinary internal path
    // and resolves to OUR origin, so an origin test alone accepts it — but the parser strips the
    // "..", leaving "//evil.example/steal" as the pathname, and the router resolves that a second
    // time against the document. Left unguarded the visitor was stranded on a blank sign-in page.
    '/..//evil.example/steal',
    '/a/..//attacker.test/p',            // the same thing with a real segment in front of it
  ];

  for (const destination of refused) {
    const landed = await arriveAtLoginWith(destination);
    expect(landed.origin, `${destination} must not send the visitor off this origin`).toBe(appOrigin);
    expect(landed.pathname, `${destination} must not be used as a return destination`).toBe('/');
  }
  await api.dispose();
});

test('a save intent left over from hours ago is not acted on', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');

  await page.goto('/');
  await installLoginStateChannel(page);
  // A browser can restore a window, history state included, long after it was closed. This is
  // that handoff: the destination is still fine, but the save is a day old and the visitor is not
  // asking for it now.
  await gotoLoginWith(page, {
    from: `/match/${fixture.id}`,
    save: { matchId: fixture.id, label: `${fixture.home.name} versus ${fixture.away.name}` },
    at: Date.now() - 24 * 60 * 60 * 1000,
  });

  // Nothing offers to finish a save that has expired.
  await expect(page.getByTestId('login-save-intent')).toHaveCount(0);

  await signInThroughTheForm(page);

  // The page they were on is still a fine place to return to; the save is not still a fine thing
  // to perform.
  await expect.poll(() => new URL(page.url()).pathname).toBe(`/match/${fixture.id}`);
  await expect(page.locator('[data-testid="save-match-button"]')).toHaveAttribute('data-saved', 'false');

  const bearer = await qaToken(api);
  const stored = await api.get('/api/v1/me/saved-matches', { headers: { Authorization: `Bearer ${bearer}` } });
  expect(JSON.stringify(await stored.json())).not.toContain(fixture.id);
  await api.dispose();
});

test('the return-to-results action goes back to the filtered list the reader came from', async ({ page }) => {
  const api = await apiContext();
  const fixture = required(await upcomingFixture(api), 'no scheduled fixture in the local database for the next eight days');
  const list = filteredList(fixture);

  await page.goto(list);
  await page.waitForLoadState('networkidle');
  await page.locator('[data-testid="fixture-row"]').first().locator('a').first().click();
  await page.waitForURL(url => url.pathname.startsWith('/match/'), { timeout: 10_000 });

  await page.getByTestId('back-to-results').click();
  await expect.poll(() => currentPath(page)).toBe(list);
  await api.dispose();
});

test('a saved fixture that has been played shows its result', async ({ page }) => {
  const api = await apiContext();
  // Never faked: with no played fixture in the local database there is nothing to assert about.
  const fixture = required(
    await finishedFixture(api),
    'no finished fixture carrying a result in the local database for the last eight days',
  );
  const score = fixture.score as { home: number; away: number };

  await page.goto('/login');
  await signInThroughTheForm(page);
  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');
  await page.locator('[data-testid="save-match-button"]').click();
  savedInThisTest.add(fixture.id);
  await expect(page.locator('[data-testid="save-match-button"]')).toHaveAttribute('data-saved', 'true');

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  const entry = page.locator('[data-testid="saved-match"]').filter({ hasText: fixture.home.name });
  await expect(entry).toHaveCount(1);
  // The result itself, beside the team it belongs to, from the payload. A bare `toContainText("0")`
  // would pass on any percentage on the row, which is not the same claim at all.
  await expect(entry).toContainText('FT');
  await expect(entry).toContainText(scoreBeside(fixture.home.name, score.home));
  await expect(entry).toContainText(scoreBeside(fixture.away.name, score.away));
  await api.dispose();
});
