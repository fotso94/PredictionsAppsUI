import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { apiContext } from '../support/qa-account';
import { ApiMatch } from '../support/api-stub';

/**
 * The match page's return refresh, against the running backend and the rows it already holds.
 *
 * WHAT THIS FILE PROVES, and it is deliberately narrow: that coming back to a tab left open on a
 * fixture issues exactly ONE read of that fixture, that the read is of STORED data, and that it
 * costs the providers nothing. Every request here is answered from the database — `GET
 * /matches/{id}` takes no refresh parameter at all (backend/app/api/v1/endpoints/matches.py) and
 * `GET /data-providers/status` reports our own budgets and scheduler out of the database and
 * process state — so a full run of this file moves no counter.
 *
 * WHAT IT CANNOT PROVE, said plainly rather than implied by silence.
 *
 *  - IT CANNOT WITNESS A KICKOFF. The transition a reader cares about — upcoming becoming live,
 *    live becoming finished — is made by the backend's scheduler writing a stored row, on the
 *    provider's timetable, not on the test's. Nothing here may force it: forcing it would mean
 *    either a provider request (forbidden, and pointless — it would prove the provider works,
 *    not that the page does) or writing to real match rows, which is not this suite's to do. The
 *    mocked half of this pair (e2e/mocked/detail-refresh.spec.ts) is where the transition itself
 *    is asserted, because there the stored row can be changed underneath the page deliberately.
 *  - IT CANNOT PROVE A FIXTURE WILL BE IN PLAY. `a fixture in play` below asserts what the page
 *    does with a running match and SKIPS when the local database holds none, because the local
 *    database's contents are a fact about the day, not a constant of the test. On 2026-09-19 at
 *    19:58 UTC it held seven, with minutes advancing; the handover for this work recorded none,
 *    which is exactly why neither test may assume either way.
 *  - IT CANNOT SEPARATE OUR SPEND FROM THE SCHEDULER'S BY ASSERTION ALONE. The backend polls live
 *    scores every 120 seconds on its own, and that spend is real and is not the browser's. The
 *    measurement below is therefore bracketed by the scheduler's own run counters and retried if
 *    it ran inside the window, so the counters are only ever read across a window the browser had
 *    to itself. A window the scheduler shared proves nothing and is not allowed to pass as proof.
 */

/** What every provider has spent today, plus who else has been running. */
interface Spend {
  /** `used_today` per provider in the chain, and for the forecast provider. */
  budgets: Record<string, number>;
  /** When each provider last ANSWERED us. A provider request would move this even at no cost. */
  contacted: Record<string, string | null>;
  /** The scheduler's own pass counters, so a background pass can be told apart from ours. */
  runs: Record<string, number>;
}

async function spendSnapshot(api: APIRequestContext): Promise<Spend> {
  const status = await (await api.get('/api/v1/data-providers/status')).json();
  const budgets: Record<string, number> = {};
  const contacted: Record<string, string | null> = {};
  for (const provider of status.chain ?? []) {
    budgets[provider.name] = provider.budget?.used_today ?? 0;
    contacted[provider.name] = provider.last_success_at ?? null;
  }
  budgets.forecasts = status.forecasts?.budget?.used_today ?? 0;
  const runs: Record<string, number> = {};
  const tasks = Object.entries(status.scheduler?.tasks ?? {}) as Array<[string, { runs?: number }]>;
  for (const [name, task] of tasks) runs[name] = task.runs ?? 0;
  return { budgets, contacted, runs };
}

/** Today's stored fixtures, read the way every page reads them: stored only. */
async function storedFixtures(api: APIRequestContext): Promise<ApiMatch[]> {
  const today = new Date().toISOString().slice(0, 10);
  const response = await api.get(`/api/v1/matches?date=${today}&refresh=false`);
  expect(response.ok(), 'the local backend did not answer for today').toBeTruthy();
  return (await response.json()).matches ?? [];
}

/**
 * The tab switch is SYNTHESISED, and here is why.
 *
 * Headless Chromium never blurs or hides a page — measured against this stack in
 * e2e/live/return-journey.spec.ts, which drives the saved-matches store's return refresh the same
 * way: `bringToFront()` on another page leaves this one reporting `visibilityState: "visible"`
 * throughout and fires neither event, and no CDP command in this protocol version reaches it.
 *
 * So the exact pair a browser sends on the way back is dispatched, in the order it sends them.
 * Only the trigger is synthetic: the listener, the age guard, the request and the render are the
 * application's own.
 */
async function comeBackToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
  });
}

/** Past RETURN_REFRESH_MIN_AGE_MS (5s in src/pages/MatchDetailPage.tsx). */
const waitOutTheGuard = (page: Page) => page.waitForTimeout(6_000);

/**
 * Count reads of one fixture's own endpoint, and refuse a refresh parameter on any of them.
 *
 * The assertion inside the listener is the standing rule for this page in its strictest form: not
 * "it did not pass refresh=true" but "it passed no refresh parameter at all", so the backend's
 * own default can never be argued into the gap.
 */
function countDetailReads(page: Page, id: string): () => number {
  let reads = 0;
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.endsWith(`/api/v1/matches/${id}`)) {
      reads += 1;
      expect(url.searchParams.get('refresh'), 'the match page asked for a provider refresh').toBeNull();
    }
  });
  return () => reads;
}

test('coming back to a match page reads it once, from stored data, and spends nothing', async ({ page }) => {
  // Three measured windows of six seconds each, plus page loads. The default 45s is not enough,
  // and waiting out a real guard is not something to shorten by weakening it.
  test.setTimeout(120_000);

  const api = await apiContext();
  const fixtures = await storedFixtures(api);
  test.skip(fixtures.length === 0, 'the local database holds no fixture for today');
  const fixture = fixtures[0];

  const reads = countDetailReads(page, fixture.id);
  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
  expect(reads(), 'the page did not read the fixture at all').toBeGreaterThan(0);

  /*
   * ONE MEASURED RETURN, TAKEN IN A WINDOW THE BROWSER HAD TO ITSELF.
   *
   * The scheduler polls live scores every two minutes and that spend is its own. Rather than
   * excuse a moved counter after the fact — which would turn this assertion into one that can
   * never fail — the window is bracketed by the scheduler's run counters and taken again if it
   * ran inside. An attempt is only ever CONCLUDED from, never explained away.
   */
  let measured: { before: Spend; after: Spend } | null = null;
  let readsBefore = 0;
  for (let attempt = 0; attempt < 3 && measured === null; attempt += 1) {
    await waitOutTheGuard(page);
    // Nothing polls: a tab nobody came back to must not have read anything in those six seconds.
    const idle = reads();
    readsBefore = idle;

    const opened = await spendSnapshot(api);
    await comeBackToTheTab(page);
    await expect.poll(() => reads(), { timeout: 15_000 }).toBe(readsBefore + 1);
    const closed = await spendSnapshot(api);

    if (JSON.stringify(closed.runs) === JSON.stringify(opened.runs)) measured = { before: opened, after: closed };
  }
  if (measured === null) {
    throw new Error('the backend scheduler ran inside all three measured windows, so none of them '
      + 'measures what the browser spent; nothing here may be concluded from a shared window');
  }

  // Exactly one read of this fixture: the focus/visibilitychange pair collapses into one request
  // rather than two, and nothing else re-read behind them.
  await page.waitForTimeout(1_500);
  expect(reads(), 'the return issued more than one read of the match').toBe(readsBefore + 1);

  // What the return cost the providers, in both accountings the backend keeps.
  expect(measured.after.budgets, 'coming back to a match page spent a provider request')
    .toEqual(measured.before.budgets);
  // And no provider was even spoken to: a call that returned from cache still moves this.
  expect(measured.after.contacted, 'coming back to a match page contacted a provider')
    .toEqual(measured.before.contacted);

  // The page is still the page, and still says what it is: stored data, with an age.
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
  await expect(page.getByTestId('freshness-summary')).toContainText(/stored data/i);
  await expect(page.getByTestId('detail-refresh-failed')).toHaveCount(0);
  await api.dispose();
});

test('a fixture in play keeps its running score under a running label across a return', async ({ page }) => {
  test.setTimeout(90_000);

  const api = await apiContext();
  /*
   * The fixtures in play are found in the STORED DAY LIST, not at `GET /matches/live`.
   *
   * That endpoint is not a stored read: `MatchDataService.live_matches()` calls `_sync_live`
   * first, which asks the provider whenever the live window is open and its 60-second cache
   * (MATCH_CACHE_TTL_LIVE) has lapsed. Reaching for it here would have spent provider requests
   * to set up a test whose whole point is that nothing spends any. The day list with
   * `refresh=false` answers the same question out of the database, for nothing.
   */
  const fixtures = await storedFixtures(api);
  /*
   * IN PLAY MEANS THE SAME THING HERE AS IT DOES ON THE PAGE, which is not what the stored status
   * alone says. A fixture keeps `live` or `halftime` until its final score arrives, and
   * the local database holds several of those at any time; picking one would set this test up
   * against a match that finished hours ago and then assert the page is calling it live — a test
   * that fails when the application is right. `result_expected_by` is the backend's own deadline
   * for a result, and a fixture inside it is one the application will still show running.
   */
  const stillRunning = (m: ApiMatch): boolean => {
    const due = m.result_expected_by ? Date.parse(m.result_expected_by) : NaN;
    return !Number.isNaN(due) && due > Date.now();
  };
  const inPlay = fixtures.filter(m => (m.status === 'live' || m.status === 'halftime') && m.score
    && stillRunning(m));
  test.skip(inPlay.length === 0, 'no fixture is in play in the local database right now');
  const fixture = inPlay[0];

  const reads = countDetailReads(page, fixture.id);
  await page.goto(`/match/${fixture.id}`);
  await page.waitForLoadState('networkidle');

  /*
   * Every scoreline the backend served for this fixture during the test.
   *
   * It is a SET rather than a single value on purpose: the scheduler rewrites this row every two
   * minutes, so between the page's read and the test's read the stored score may legitimately
   * have moved on. What must never happen is the page showing a scoreline the backend never
   * served — so the assertion is membership of what was actually served, which is exact, and not
   * a range or a tolerance, which would not be.
   */
  const served = new Set<string>();
  const record = (match: ApiMatch) => {
    const score = match.score as { home: number; away: number } | null;
    if (score) served.add(`${score.home} - ${score.away}`);
  };
  record(fixture);

  const scoreline = page.getByTestId('match-scoreline');
  // A running score is only ever shown under a running label. This is the element that carries
  // both, which is why they are asserted on it together rather than anywhere on the page.
  await expect(scoreline).toContainText(/LIVE|HT/);
  await expect(scoreline).not.toContainText(/Finished|Full time/i);

  await waitOutTheGuard(page);
  const before = await spendSnapshot(api);
  const readsBefore = reads();
  await comeBackToTheTab(page);
  await expect.poll(() => reads(), { timeout: 15_000 }).toBe(readsBefore + 1);

  const current = await (await api.get(`/api/v1/matches/${fixture.id}`)).json();
  record(current);
  test.skip((current.status !== 'live' && current.status !== 'halftime') || !stillRunning(current),
    'the fixture stopped being in play while the test was running');

  const shown = await scoreline.innerText();
  const scores = [...served];
  expect(scores.some(score => shown.includes(score)),
    `the scoreline showed "${shown.replace(/\n/g, ' ')}", which the backend never served (${scores.join(' | ')})`).toBe(true);
  await expect(scoreline).toContainText(/LIVE|HT/);
  await expect(scoreline).not.toContainText(/Finished|Full time/i);

  // A re-read is not live data, and the page must keep saying so in the same words as every
  // other surface: what it shows is stored, with an age.
  await expect(page.getByTestId('freshness-summary')).toContainText(/stored data/i);

  const after = await spendSnapshot(api);
  if (JSON.stringify(after.runs) === JSON.stringify(before.runs)) {
    // Only conclusive when the scheduler stayed out of the window; the test above is the one that
    // insists on such a window, so here it is reported rather than retried.
    expect(after.budgets, 'reading a live fixture again spent a provider request').toEqual(before.budgets);
  }
  await api.dispose();
});
