import { readFile } from 'node:fs/promises';
import { test, expect, APIRequestContext, Download, Page } from '@playwright/test';
import { apiContext, ensureQaExpertToken, QA_EXPERT } from '../support/qa-account';

/**
 * Control, privacy and the calendar snapshot, against the real local stack.
 *
 * WHY LIVE AND NOT MOCKED. Three of the five things here are only true if the whole chain is
 * real. A preference has to survive a reload, which means it has to have reached storage under
 * the id of the account that is actually signed in. A deletion has to be gone FROM THE SERVER,
 * not from an optimistic store that would happily report success over a 500. And an export has
 * to contain the reader's own rows, which only exist because the API put them there. Stubbing any
 * of that would leave a suite that passes while the feature does not work.
 *
 * COST AND CLEANLINESS
 *  - Every read is a stored read. Nothing here passes `refresh=true`, so no provider request is
 *    issued and no allowance is spent. One test measures the provider counters either side of the
 *    whole journey and fails if a single unit moved.
 *  - The only rows written are saved-match and follow rows on the QA account the suite already
 *    creates. `afterEach` removes every one of them, and each test clears the account first so a
 *    rerun starts from the same place. No fixture, forecast or prediction is touched.
 *
 * AT BOTH WIDTHS. The controls are a column of switches and a confirmation with two side-by-side
 * buttons, which is exactly the shape that survives 1440 and quietly breaks at 390 — so every
 * test runs at both, and the 390 pass is what proves the confirmation's buttons are reachable on
 * a phone rather than pushed off the edge.
 */

interface Fixture {
  id: string;
  kickoff_utc: string;
  status: string;
  competition: { id: string; name: string };
  home: { id: string; name: string };
  away: { id: string; name: string };
}

const auth = (bearer: string) => ({ headers: { Authorization: `Bearer ${bearer}` } });

let token = '';
const savedInThisTest = new Set<string>();
const followedInThisTest = new Set<string>();

async function qaToken(api: APIRequestContext): Promise<string> {
  if (!token) token = await ensureQaExpertToken(api);
  return token;
}

/** Skip rather than assert against data this database does not hold, and narrow the type. */
function required<T>(value: T | null, reason: string): T {
  test.skip(value === null, reason);
  return value as T;
}

function dayOffsetUtc(offset: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

async function fixturesOn(api: APIRequestContext, day: string): Promise<Fixture[]> {
  // refresh=false keeps this a database read: no provider request is made
  const response = await api.get(`/api/v1/matches?date=${day}&refresh=false`);
  if (!response.ok()) return [];
  return ((await response.json()).matches || []) as Fixture[];
}

/** Any fixture in the local database, in the days the dashboard feed covers. */
async function anyFixture(api: APIRequestContext): Promise<Fixture | null> {
  for (const offset of [0, 1, 2, -1, 3, -2, 4, 5]) {
    const found = (await fixturesOn(api, dayOffsetUtc(offset)))[0];
    if (found) return found;
  }
  return null;
}

/** Leave the QA account holding nothing, so every test starts from the same place. */
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

async function saveMatch(api: APIRequestContext, bearer: string, matchId: string, note?: string): Promise<void> {
  const response = await api.put(`/api/v1/me/saved-matches/${matchId}`, {
    ...auth(bearer),
    data: note === undefined ? {} : { note },
  });
  expect(response.ok(), 'the QA account could not save a match through the API').toBe(true);
  savedInThisTest.add(matchId);
}

async function followTeam(api: APIRequestContext, bearer: string, teamId: string): Promise<void> {
  const response = await api.put(`/api/v1/me/favourites/teams/${teamId}`, auth(bearer));
  expect(response.ok(), 'the QA account could not follow a team through the API').toBe(true);
  followedInThisTest.add(teamId);
}

/** Every provider's spend today, so a test can prove this whole journey moved none of it. */
async function providerSpend(api: APIRequestContext): Promise<Record<string, number>> {
  const status = await (await api.get('/api/v1/data-providers/status')).json();
  const spend: Record<string, number> = {};
  for (const provider of status.chain ?? []) spend[provider.name] = provider.budget?.used_today ?? 0;
  spend.forecasts = status.forecasts?.budget?.used_today ?? 0;
  return spend;
}

/** Sign in through the real form, as a visitor would. Resolves once the route has changed. */
async function signInThroughTheForm(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(QA_EXPERT.email);
  await page.locator('input[type="password"]').first().fill(QA_EXPERT.password);
  await page.getByRole('button', { name: /^sign in$/i }).first().click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 15_000 });
}

async function openDashboard(page: Page): Promise<void> {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('personal-controls')).toBeVisible();
}

/** The bytes of a download, as text. */
async function downloadedText(download: Download): Promise<string> {
  const path = await download.path();
  expect(path, 'the browser did not hand the download to a file').toBeTruthy();
  return readFile(path as string, 'utf8');
}

/** Press something that produces a file, and return the file. */
async function downloadFrom(page: Page, testId: string): Promise<Download> {
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15_000 }),
    page.getByTestId(testId).click(),
  ]);
  return download;
}

test.afterEach(async () => {
  if (savedInThisTest.size === 0 && followedInThisTest.size === 0) return;
  const api = await apiContext();
  const bearer = await qaToken(api);
  for (const matchId of savedInThisTest) await api.delete(`/api/v1/me/saved-matches/${matchId}`, auth(bearer));
  for (const teamId of followedInThisTest) await api.delete(`/api/v1/me/favourites/teams/${teamId}`, auth(bearer));
  savedInThisTest.clear();
  followedInThisTest.clear();
  await api.dispose();
});

/**
 * Wording nothing on this panel is allowed to contain.
 *
 * E5 asks for the copy to be read back and checked; this is that check, made executable so it
 * stays done. Every entry is a way of turning a preference panel into pressure: a streak, a
 * congratulation, a scarcity line, a loss-recovery prompt, or a suggestion to follow one more
 * thing. Scoped to this panel rather than the whole page, so it tests copy this package owns and
 * cannot fail because of a card somebody else added.
 */
const NUDGES = [
  /streak/i,
  /congratulat/i,
  /well done/i,
  /keep it up/i,
  /do ?n['’]?t miss/i,
  /last chance/i,
  /hurry/i,
  /why not/i,
  /follow more/i,
  /win (it )?back/i,
  /recover your/i,
  /you['’]ve earned/i,
  /miss out/i,
];

const VIEWPORTS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '390', width: 390, height: 844 },
];

for (const viewport of VIEWPORTS) {
  test.describe(`personal controls at ${viewport.label}px`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    /**
     * E1. FOOTBALL WITHOUT FORECASTS, AND IT STAYS THAT WAY.
     *
     * The three halves that have to hold together: the forecast surfaces actually go, the
     * football does not, and the choice survives a reload — a preference that forgets itself is
     * a preference nobody will use twice.
     */
    test('a reader can turn the forecasts off, keep the football, and find it still off after a reload', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      await saveMatch(api, bearer, fixture.id);

      await signInThroughTheForm(page);
      await openDashboard(page);

      const row = page.locator(`[data-testid="saved-match"][data-match-id="${fixture.id}"]`);
      await expect(row).toBeVisible();
      // Before: the row carries the per-source preview and a way into the full brief.
      await expect(row.getByTestId('fixture-row-preview')).toBeVisible();
      await expect(row.getByTestId('fixture-row-expand')).toHaveCount(1);
      await expect(page.getByTestId('feed-scores-only')).toHaveCount(0);

      const forecasts = page.getByTestId('personal-switch-forecasts');
      await expect(forecasts).toHaveAttribute('aria-checked', 'true');
      await forecasts.click();

      // After: the forecast surfaces are gone from the row, and the detail is not merely
      // collapsed — the control that opens it is not rendered at all.
      await expect(forecasts).toHaveAttribute('aria-checked', 'false');
      await expect(row.getByTestId('fixture-row-preview')).toBeHidden();
      await expect(row.getByTestId('fixture-row-expand')).toHaveCount(0);

      // And the football is untouched: the fixture, both clubs and the save are all still there.
      await expect(row).toBeVisible();
      await expect(row).toContainText(fixture.home.name);
      await expect(row).toContainText(fixture.away.name);
      await expect(row.getByTestId('save-match-button')).toHaveAttribute('data-saved', 'true');

      // It says what it is, so a preference is never mistaken for an outage.
      await expect(page.getByTestId('feed-scores-only')).toContainText(/scores only/i);

      await page.reload();
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('personal-switch-forecasts')).toHaveAttribute('aria-checked', 'false');
      await expect(page.getByTestId('feed-scores-only')).toBeVisible();
      await expect(
        page.locator(`[data-testid="saved-match"][data-match-id="${fixture.id}"]`).getByTestId('fixture-row-preview'),
      ).toBeHidden();

      await api.dispose();
    });

    /**
     * E2. ONE SWITCH STOPS EVERYTHING, IT IS REVERSIBLE WITHOUT LOSS, AND IT DOES NOT OVERCLAIM.
     *
     * The last assertion is the one that matters most and is the easiest to leave out: the panel
     * has to say, in words, that pausing what a page draws is not a bookmaker self-exclusion. A
     * reader who believed otherwise would stop looking for the tool that would actually help.
     */
    test('pausing stops everything optional, says exactly what it is not, and gives the settings back', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      await saveMatch(api, bearer, fixture.id);

      await signInThroughTheForm(page);
      await openDashboard(page);

      const pause = page.getByTestId('personal-pause');
      // Said whether or not the pause is on, because it is true either way.
      await expect(pause).toContainText(/not a bookmaker self-exclusion/i);
      await expect(pause).toContainText(/does not block any betting site/i);
      await expect(pause).toHaveAttribute('data-paused', 'false');

      const row = page.locator(`[data-testid="saved-match"][data-match-id="${fixture.id}"]`);
      await expect(row.getByTestId('fixture-row-preview')).toBeVisible();

      await page.getByTestId('personal-pause-toggle').click();

      await expect(pause).toHaveAttribute('data-paused', 'true');
      await expect(row.getByTestId('fixture-row-preview')).toBeHidden();
      await expect(row.getByTestId('fixture-row-expand')).toHaveCount(0);
      await expect(page.getByTestId('feed-scores-only')).toBeVisible();

      /*
       * The reader's own settings are KEPT, not overwritten. Each switch still reports its own
       * value, and each says on its own row that the pause is what is holding it — which is the
       * difference between a pause and having your configuration silently rewritten.
       */
      for (const testId of ['personal-switch-forecasts', 'personal-switch-prompts', 'personal-switch-live']) {
        await expect(page.getByTestId(testId)).toHaveAttribute('aria-checked', 'true');
      }
      await expect(page.getByTestId('personal-surfaces')).toContainText(/everything optional is paused/i);

      // Immediate and reversible, with those same settings back.
      await page.getByTestId('personal-pause-toggle').click();
      await expect(pause).toHaveAttribute('data-paused', 'false');
      await expect(row.getByTestId('fixture-row-preview')).toBeVisible();
      await expect(page.getByTestId('feed-scores-only')).toHaveCount(0);

      await api.dispose();
    });

    /**
     * E3, first half. THE DATA COMES OUT, IN SOMETHING THAT OPENS.
     *
     * The export is checked for the reader's actual row rather than for being non-empty: a file
     * with the right shape and none of their data in it is the failure worth catching.
     */
    test('a reader can download their own data, and what comes out is their own data', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      const note = 'Checking the export carries my note.';
      await saveMatch(api, bearer, fixture.id, note);
      await followTeam(api, bearer, fixture.home.id);

      await signInThroughTheForm(page);
      await openDashboard(page);

      const json = await downloadFrom(page, 'personal-export-json');
      expect(json.suggestedFilename()).toMatch(/^your-data-\d{4}-\d{2}-\d{2}\.json$/);
      const parsed = JSON.parse(await downloadedText(json));
      expect(parsed.savedMatches.map((entry: { matchId: string }) => entry.matchId)).toContain(fixture.id);
      expect(parsed.savedMatches.find((entry: { matchId: string }) => entry.matchId === fixture.id).yourNote).toBe(note);
      expect(parsed.following.teams.map((team: { id: string }) => team.id)).toContain(fixture.home.id);
      // The settings travel with it, and the file says where they actually live.
      expect(parsed.preferences.showForecastsAndTips).toBe(true);
      expect(parsed.preferences.storedWhere).toMatch(/this browser only/i);
      // It states what it does NOT contain rather than letting the reader assume it is everything.
      expect(JSON.stringify(parsed.export.notIncluded)).toMatch(/account record/i);

      const csv = await downloadFrom(page, 'personal-export-csv');
      expect(csv.suggestedFilename()).toMatch(/^your-saved-matches-\d{4}-\d{2}-\d{2}\.csv$/);
      const table = await downloadedText(csv);
      expect(table.split('\r\n')[0]).toBe(
        'Saved at,Kick-off (UTC),Date,Status,Competition,Home,Away,Final score as stored,Your note',
      );
      expect(table).toContain(fixture.home.name);
      expect(table).toContain(note);

      await api.dispose();
    });

    /**
     * E4. THE CALENDAR IS A SNAPSHOT, AND THE INTERFACE SAYS SO WHERE THE BUTTON IS.
     *
     * Two separate claims are checked: the file is a valid one-time calendar that carries none of
     * the properties a subscribed feed would need, and the sentence saying so sits in the same
     * block as the control — not in a footnote somewhere down the page.
     */
    test('the calendar download is a snapshot, says so beside the button, and implies no feed', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      await saveMatch(api, bearer, fixture.id);

      await signInThroughTheForm(page);
      await openDashboard(page);

      // The warning is visible, and it is in the same block as the button — which is what "not in
      // a footnote" has to mean if it is going to be testable at all.
      const warning = page.getByTestId('calendar-snapshot-warning');
      await expect(warning).toBeVisible();
      await expect(warning).toContainText(/one-time snapshot/i);
      await expect(warning).toContainText(/will never update/i);
      const block = page.locator('div').filter({ has: page.getByTestId('calendar-snapshot-warning') })
        .filter({ has: page.getByTestId('personal-export-calendar') });
      await expect(block.first()).toBeVisible();

      const ics = await downloadFrom(page, 'personal-export-calendar');
      expect(ics.suggestedFilename()).toMatch(/^saved-fixtures-snapshot-\d{4}-\d{2}-\d{2}\.ics$/);
      const text = await downloadedText(ics);

      expect(text.startsWith('BEGIN:VCALENDAR\r\n')).toBe(true);
      expect(text.trimEnd().endsWith('END:VCALENDAR')).toBe(true);
      expect(text).toContain('VERSION:2.0');
      expect(text).toContain(`UID:${fixture.id}@`);
      expect(text).toContain(`SUMMARY:${fixture.home.name.replace(/,/g, '\\,')} v `);
      // The honesty is inside the file too, for whoever opens it months later.
      expect(text).toMatch(/X-WR-CALDESC:.*one-time snapshot/);

      /*
       * NOTHING THAT WOULD MAKE A CLIENT TREAT THIS AS A MANAGED FEED. These three properties are
       * how an .ics announces itself as something to come back to and re-read, and a file
       * carrying them with no endpoint behind it is a promise that cannot be kept.
       */
      expect(text).not.toMatch(/(^|\r\n)METHOD:/);
      expect(text).not.toContain('REFRESH-INTERVAL');
      expect(text).not.toContain('X-PUBLISHED-TTL');
      // Every line folded to 75 octets, so a club name with an accent in it does not break import.
      const overlong = text.split('\r\n').filter(line => Buffer.byteLength(line, 'utf8') > 75);
      expect(overlong, `unfolded lines: ${overlong.join(' | ')}`).toHaveLength(0);

      // And the page reports what it actually wrote, rather than saying "done".
      await expect(page.getByTestId('calendar-outcome')).toContainText(/entry|entries/i);

      await api.dispose();
    });

    /**
     * E3, second half. DELETION IS ASKED ONCE, SAYS WHAT GOES AND WHAT STAYS, AND REALLY DELETES.
     *
     * The server is the witness. An optimistic store would report a clean deletion over a failed
     * request, and the whole point of this control is that the reader is leaving and will not be
     * around to find out.
     */
    test('deletion asks once, is honest about what remains, and the server really has nothing left', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      await saveMatch(api, bearer, fixture.id, 'This note goes with it.');
      await followTeam(api, bearer, fixture.home.id);

      await signInThroughTheForm(page);
      await openDashboard(page);

      await page.getByTestId('personal-delete-open').click();
      const confirm = page.getByTestId('personal-delete-confirm');
      await expect(confirm).toBeVisible();
      // What goes, what stays, and the honest limit of what this page can do.
      await expect(confirm).toContainText(/what goes/i);
      await expect(confirm).toContainText(/what stays/i);
      await expect(confirm).toContainText(/close your own account/i);
      // Not a dark pattern: the way out is a button of the same weight, not a hidden link.
      await expect(confirm.getByTestId('personal-delete-confirm-no')).toBeVisible();
      await expect(confirm.getByTestId('personal-delete-confirm-no')).toBeEnabled();
      // And a copy is still offered to somebody who is on their way out.
      await expect(page.getByTestId('personal-export-json')).toBeVisible();

      // Backing out changes nothing at all.
      await confirm.getByTestId('personal-delete-confirm-no').click();
      await expect(page.getByTestId('personal-delete-confirm')).toHaveCount(0);
      const untouched = await (await api.get('/api/v1/me/favourites', auth(bearer))).json();
      expect(untouched.saved_matches.counts.total).toBeGreaterThan(0);

      // Asked once. One press and it is done — no second confirmation, no countdown.
      await page.getByTestId('personal-delete-open').click();
      await page.getByTestId('personal-delete-confirm-yes').click();

      const outcome = page.getByTestId('personal-delete-outcome');
      await expect(outcome).toBeVisible({ timeout: 20_000 });
      await expect(outcome).toContainText(/removed 2 of 2 records/i);

      // The server, not the page, is what is being asserted here.
      const after = await (await api.get('/api/v1/me/favourites', auth(bearer))).json();
      expect(after.saved_matches.counts.total).toBe(0);
      expect(after.team_ids ?? []).toHaveLength(0);
      expect(after.league_ids ?? []).toHaveLength(0);
      savedInThisTest.clear();
      followedInThisTest.clear();

      // And the control now says the truth about an account holding nothing.
      await expect(page.getByTestId('personal-delete-nothing')).toBeVisible();
      await expect(page.getByTestId('personal-delete-open')).toBeDisabled();

      await api.dispose();
    });

    /**
     * E5, made executable, and the cost of the whole journey.
     *
     * The copy check is the "read your own copy back" step written down so it stays done. The
     * spend check is the standing rule: browsing, toggling and exporting must move no provider
     * counter, and this exercise touches more of the personal surfaces than any other test here.
     */
    test('nothing on the panel nudges, and none of this spends a provider request', async ({ page }) => {
      const api = await apiContext();
      const bearer = await qaToken(api);
      await clearQaFavourites(api, bearer);
      const fixture = required(await anyFixture(api), 'no fixture in the local database for the days the feed covers');
      await saveMatch(api, bearer, fixture.id);
      await followTeam(api, bearer, fixture.home.id);

      const before = await providerSpend(api);
      let refreshRequests = 0;
      page.on('request', request => {
        if (/[?&]refresh=true/i.test(request.url())) refreshRequests += 1;
      });

      await signInThroughTheForm(page);
      await openDashboard(page);

      const panel = page.getByTestId('personal-controls');
      const paths = [
        async () => { await page.getByTestId('personal-switch-forecasts').click() },
        async () => { await page.getByTestId('personal-switch-prompts').click() },
        async () => { await page.getByTestId('personal-switch-live').click() },
        async () => { await page.getByTestId('personal-pause-toggle').click() },
      ];
      for (const walk of paths) {
        await walk();
        const copy = await panel.innerText();
        for (const nudge of NUDGES) {
          expect(copy, `the panel copy matched ${nudge}`).not.toMatch(nudge);
        }
      }

      // The empty-state and hidden-count invitations answer to the prompts switch; the count
      // itself is a fact about the list and is not allowed to disappear with them.
      await expect(page.getByTestId('feed-scores-only')).toBeVisible();

      await page.waitForLoadState('networkidle');
      expect(refreshRequests, 'the personal pages must never ask a provider to refresh').toBe(0);
      expect(await providerSpend(api), 'browsing and exporting spent a provider request').toEqual(before);

      await api.dispose();
    });
  });
}
