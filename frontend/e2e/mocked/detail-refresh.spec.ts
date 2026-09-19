import { test, expect, Page } from '@playwright/test';
import {
  ApiMatch, ProviderStatusPayload,
  baseMatches, baseStatus, dayPayload, healthyScheduler, healthyTask, stubBackend,
} from '../support/api-stub';

/**
 * A match page that was left open, and what it owes the reader when they come back to it.
 *
 * THE DEFECT THIS FILE EXISTS FOR. A reader opens a fixture, switches to something else, and
 * comes back an hour later. Before this change the page they came back to was the page they left,
 * frozen: the same scoreline, the same status badge, and — worse than either — the same "last
 * refreshed" line underneath, which is a claim about how current the page is that nobody had
 * re-checked. `MatchDetailPage.tsx` read the fixture once, in a mount effect, and listened for
 * nothing afterwards. The saved-matches store had woken on `focus` and `visibilitychange` since
 * it was written; the page a reader actually watches a match on did not.
 *
 * WHAT IS PROVED HERE, and each of the three failed before the change:
 *   1. coming back re-reads, and the reader sees the new score, the new state and the NEW age;
 *   2. a page that has just loaded and merely taken focus does NOT read again — the refresh is a
 *      return, not a cadence, and one reader must not become a load generator;
 *   3. a re-read that fails keeps every word of what was on screen and withdraws the AGE, rather
 *      than leaving a stale freshness line standing over content nobody could confirm.
 *
 * Every payload is stubbed. No provider request is made, no allowance is spent, and the page
 * never passes `refresh=true` — the two endpoints it reads (`GET /matches/{id}` and
 * `GET /data-providers/status`) are stored-data-only on the real backend too.
 */

/** The captured fixture, before anybody kicks off: scheduled, no score. */
const upcoming = (): ApiMatch => baseMatches()[0];

/**
 * The same fixture in play, with a score and a minute.
 *
 * Nothing here is invented about the WORLD — it is the captured fixture with the three fields the
 * backend sets when a match starts, in the shapes `mapApiMatch` reads them from
 * (`status`, `score`, `minute`). It stands in for the scheduler having updated the stored row
 * while the reader was in another tab, which is exactly how this transition reaches a page.
 */
function inPlay(): ApiMatch {
  const match = JSON.parse(JSON.stringify(upcoming())) as ApiMatch;
  match.status = 'live';
  match.score = { home: 1, away: 0, ht_home: 0, ht_away: 0 };
  match.minute = 57;
  return match;
}

/**
 * A provider status whose whole fixture side last succeeded `minutes` ago.
 *
 * All three fixture-side tasks are moved together on purpose. `freshnessReport` states the MOST
 * RECENT success across them (clockState in src/components/ui/freshness.ts), so moving only one
 * would leave the line reading another task's clock and the test would be measuring nothing.
 * Each keeps a next-due time in the future, so none of them is "behind" and the wording under
 * test is the ordinary one a healthy backend produces.
 */
function refreshedMinutesAgo(minutes: number): ProviderStatusPayload {
  const status = baseStatus();
  const scheduler = healthyScheduler();
  scheduler.tasks.fixtures = healthyTask(21_600, minutes, 348);
  scheduler.tasks.live = healthyTask(120, minutes, 2);
  scheduler.tasks.results = healthyTask(1800, minutes, 22);
  status.scheduler = scheduler;
  return status;
}

/**
 * The tab switch is SYNTHESISED, and here is why.
 *
 * Headless Chromium never blurs or hides a page — the same measurement recorded in
 * e2e/live/return-journey.spec.ts, which drives the saved-matches store's own return refresh this
 * way: `bringToFront()` on another page leaves this one reporting `visibilityState: "visible"`
 * throughout and fires neither event, and no CDP command in this protocol version reaches it.
 *
 * So the pair a browser really sends on the way back is dispatched, in the order it sends them.
 * Only the trigger is synthetic: the listener, the age guard, the request, the commit and the
 * render are all the application's own, and breaking any of them fails these tests.
 */
async function comeBackToTheTab(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
  });
}

/**
 * Past RETURN_REFRESH_MIN_AGE_MS (5s in src/pages/MatchDetailPage.tsx).
 *
 * That guard exists to collapse the focus/visibilitychange pair into one request and to stop a
 * page re-reading itself the instant it loads — not to ration a real return, which is why a test
 * of a real return waits it out rather than working around it.
 */
const waitOutTheGuard = (page: Page) => page.waitForTimeout(6_000);

/** Every read of THIS fixture's own endpoint, which is the request a return is supposed to make. */
function countDetailReads(page: Page, id: string): () => number {
  let reads = 0;
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.endsWith(`/api/v1/matches/${id}`)) {
      reads += 1;
      // The standing rule for every read on this page: stored data, never a provider refresh.
      expect(url.searchParams.get('refresh'), 'the match page asked for a provider refresh').toBeNull();
    }
  });
  return () => reads;
}

test.describe('a match page that was left open', () => {
  test('coming back to the tab shows the new score, the new state and the new age', async ({ page }) => {
    const fixture = upcoming();
    let served = upcoming();
    const status = refreshedMinutesAgo(45);
    await stubBackend(page, {
      day: d => dayPayload(d),
      matchById: () => served,
      status,
    });

    await page.goto(`/match/${fixture.id}`);
    await page.waitForLoadState('networkidle');

    // What the reader left: no score yet, and a freshness line with the age it had then.
    const scoreline = page.getByTestId('match-scoreline');
    await expect(scoreline).toContainText('VS');
    await expect(scoreline).toContainText('Scheduled');
    await expect(page.getByTestId('freshness-summary')).toContainText('45 minutes ago');

    // While they were away: the match kicked off and our refresh ran again. Both of those happen
    // in the backend's stored rows, which is the only place this page ever reads from.
    served = inPlay();
    Object.assign(status, refreshedMinutesAgo(1));

    // Still away. Nothing on the page may have noticed yet — no poll, no cadence.
    await waitOutTheGuard(page);
    await expect(scoreline).toContainText('VS');

    await comeBackToTheTab(page);

    // The score and the state the reader came back for.
    await expect(scoreline).toContainText('1 - 0');
    await expect(scoreline).toContainText("LIVE 57'");
    await expect(scoreline).not.toContainText('Scheduled');

    // And the age, which is the half that was silently wrong before: the line now states when the
    // refresh behind THIS content succeeded, not when the refresh behind the old content did.
    const summary = page.getByTestId('freshness-summary');
    await expect(summary).toContainText('1 minute ago');
    await expect(summary).not.toContainText('45 minutes ago');
    // Still stored data, said in the same words as everywhere else. A re-read is not live data.
    await expect(summary).toContainText(/stored data/i);
    await expect(page.getByTestId('detail-refresh-failed')).toHaveCount(0);
  });

  test('a page that has just loaded and taken focus does not read again', async ({ page }) => {
    const fixture = upcoming();
    let served = upcoming();
    const status = refreshedMinutesAgo(45);
    await stubBackend(page, { day: d => dayPayload(d), matchById: () => served, status });

    const reads = countDetailReads(page, fixture.id);
    await page.goto(`/match/${fixture.id}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('freshness-summary')).toContainText('45 minutes ago');

    const afterLoad = reads();
    expect(afterLoad, 'the page did not read the fixture at all').toBeGreaterThan(0);

    // Change what the stub would answer with, so a read that should not happen is not merely
    // uncounted but VISIBLE if it happens anyway.
    served = inPlay();
    Object.assign(status, refreshedMinutesAgo(1));

    // A reader who opens a fixture and clicks back into their own window has not come back from
    // anywhere. Focus alone, on a page loaded seconds ago, is not a return.
    await comeBackToTheTab(page);
    await page.waitForTimeout(1_500);

    expect(reads(), 'focus on a freshly loaded page issued a second read').toBe(afterLoad);
    await expect(page.getByTestId('match-scoreline')).toContainText('VS');
    await expect(page.getByTestId('freshness-summary')).toContainText('45 minutes ago');
  });

  test('a re-read that fails keeps the content and withdraws the age', async ({ page }) => {
    const fixture = upcoming();
    let served = upcoming();
    let refuseTheMatch = false;
    const status = refreshedMinutesAgo(45);
    await stubBackend(page, {
      day: d => dayPayload(d),
      matchById: () => served,
      status,
      fail: url => (refuseTheMatch && url.includes(`/matches/${fixture.id}`) ? 500 : null),
    });

    await page.goto(`/match/${fixture.id}`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('match-scoreline')).toContainText('VS');
    await expect(page.getByTestId('freshness-summary')).toContainText('45 minutes ago');

    // The match read will fail from here. Everything else still answers — including the status
    // endpoint, which now reports a much fresher refresh. That combination is the trap: adopting
    // that age while the fixture itself could not be re-read would print "refreshed 1 minute ago"
    // over a copy of the page nobody confirmed.
    refuseTheMatch = true;
    served = inPlay();
    Object.assign(status, refreshedMinutesAgo(1));

    await waitOutTheGuard(page);
    await comeBackToTheTab(page);

    // Said out loud, with the backend's own reason, and scoped to this page's copy.
    const failure = page.getByTestId('detail-refresh-failed');
    await expect(failure).toBeVisible();
    await expect(failure).toContainText(/its age is not known/i);
    await expect(failure).toContainText(/the copy from when you left/i);
    // The backend's own words for why, passed through rather than paraphrased into a shrug.
    await expect(failure).toContainText('Simulated backend failure');

    // The page the reader was reading is still the page in front of them.
    await expect(page.getByTestId('match-scoreline')).toContainText('VS');
    await expect(page.getByTestId('match-scoreline')).not.toContainText('1 - 0');
    await expect(page.locator('body')).toContainText('Tottenham Hotspur');
    // Not a spinner and not the error screen: a background read that failed may not take the page.
    await expect(page.locator('body')).not.toContainText('Match data unavailable');
    await expect(page.locator('body')).not.toContainText('Loading match...');

    // And the freshness line did not quietly get younger. The status half of the re-read answered
    // with "1 minute ago" and was thrown away with the read it belonged to.
    const summary = page.getByTestId('freshness-summary');
    await expect(summary).not.toContainText('1 minute ago');
    await expect(summary).toContainText('45 minutes ago');
  });
});
