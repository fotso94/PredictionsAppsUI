import { test, expect, Page } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, DayPayload, baseMatches, dayPayload, localDay, stubBackend,
} from '../support/api-stub';
import { signIn } from '../support/auth';

/**
 * Getting around: can every control be reached, and does a page open where you can read it.
 *
 * Two failures the reviewer hit on a real device, both of which the existing suite passed straight
 * over because it only ever ran at 1440 and 390:
 *
 *  1. at 360px the header did not fit on one row. The brand wrapped, both account actions and the
 *     menu button could not sit beside it, the menu button was clipped by the right edge and the
 *     document scrolled sideways — so the one control that reaches every other page on a phone
 *     could not be tapped at all.
 *  2. opening a team from the two links at the FOOT of a match page landed on the team page at its
 *     own footer, because nothing in the application ever touched the scroll position on a
 *     navigation. Reproduced twice, and every deep page in the app had the same defect.
 *
 * These run in mocked-desktop (1440), mocked-mobile (iPhone 13, 390) and mocked-mobile-360
 * (Galaxy S8, 360). Anything that is only true at one width fails here.
 */

/**
 * Below this the destinations live in the menu rather than on the bar. It is Tailwind's `lg`, not
 * `md`: the four-entry row needs 928px, so joining the bar at 768 overflowed every screen from
 * iPad portrait up to about 950.
 */
const MENU_BREAKPOINT = 1024;

/** How far the document may exceed the viewport before it is sideways scroll. One px is rounding. */
const OVERFLOW_TOLERANCE = 1;

/** A restore lands within this many pixels. Sub-pixel layout and a re-measured sticky header. */
const RESTORE_TOLERANCE = 40;

/**
 * The restore's own numbers, from src/components/layout/ScrollBehaviour.tsx.
 *
 * Restated here on purpose. RESTORE_MAX_MS is the interesting one: it was a defensible choice held
 * in place by nothing at all, and raising it to sixty seconds used to leave every test in this file
 * green. The two tests that name it are what hold it now — one proves a restore still owed at the
 * cap is abandoned there, the other measures how long that took — so if either number moves in the
 * component without moving here, they fail.
 */
const RESTORE_WINDOW_MS = 1500;
const RESTORE_MAX_MS = 6000;

/**
 * Where a pending restore publishes its phase: `converging`, then `holding`, then the attribute is
 * removed. It is what lets the tests below hold the fixture list on a signal instead of a
 * stopwatch — see holdFixtureList().
 */
const RESTORE_PHASE_ATTRIBUTE = 'data-scroll-restore';

const restorePhase = (page: Page): Promise<string | null> =>
  page.evaluate(attribute => document.documentElement.getAttribute(attribute), RESTORE_PHASE_ATTRIBUTE);

/** Wait for the restore to reach `phase`; `null` means it is over, however it ended. */
async function expectRestorePhase(
  page: Page, phase: 'converging' | 'holding' | null, why: string, timeout: number,
): Promise<void> {
  await expect.poll(() => restorePhase(page), { message: why, timeout }).toBe(phase);
}

const horizontalOverflow = (page: Page): Promise<number> =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

const scrollY = (page: Page): Promise<number> => page.evaluate(() => Math.round(window.scrollY));

/** Offset and the furthest this document can be scrolled, read together so they agree. */
const scrollState = (page: Page): Promise<{ y: number; furthest: number }> =>
  page.evaluate(() => ({
    y: Math.round(window.scrollY),
    furthest: Math.max(0, Math.round(document.documentElement.scrollHeight - window.innerHeight)),
  }));

/**
 * Bring `locator` into view the way a reader scrolling to it would, and report where that left
 * the page.
 *
 * Reading the offset before the click rather than after scrolling to the bottom matters: a
 * Playwright click scrolls its target into view first, so a position captured earlier is not the
 * position the page is actually left at, and the test would then demand a restore to somewhere
 * the reader never was.
 */
async function scrollToAndReport(page: Page, locator: ReturnType<Page['locator']>): Promise<number> {
  await locator.scrollIntoViewIfNeeded();
  await expect(locator).toBeInViewport();
  return scrollY(page);
}

/**
 * Assert the reader came back to where they left, allowing for a page that returns slightly
 * shorter than it went away — in which case its own bottom is where they were.
 *
 * THE HOLE THIS CLOSES. Clamping the wanted offset to the page's CURRENT height, on its own, is a
 * pass waiting to happen: a page that is still a skeleton reaches nothing, the clamp turns a
 * demand for y=1100 into a demand for y=0, and y=0 is where a page that has done nothing at all
 * already is. The first poll would then report success before the restore had even been attempted.
 *
 * So a page shorter than the offset is only allowed to stand in for it once all three of these
 * hold: it has something to scroll at all, its height has stopped changing, and the network has
 * gone quiet — a skeleton waiting on a request is a stable height too, and height alone cannot
 * tell it from a page that really did come back shorter. A page tall enough to hold the offset is
 * held to the offset itself, and never to its own bottom.
 */
async function expectRestoredTo(page: Page, left: number, what: string): Promise<void> {
  let previousHeight = -1;
  let quiet = false;
  const settle = page.waitForLoadState('networkidle').then(() => { quiet = true; }, () => { quiet = true; });

  await expect.poll(async () => {
    const { y, furthest } = await scrollState(page);
    const settled = furthest === previousHeight;
    previousHeight = furthest;

    if (furthest >= left - RESTORE_TOLERANCE) {
      return y >= left - RESTORE_TOLERANCE ? 'restored' : `stopped at ${y}, wanted ${left}`;
    }
    if (furthest === 0) return 'the page still has nothing to scroll';
    if (!settled) return `the page is still growing (reaches ${furthest})`;
    if (!quiet) return `the page reaches only ${furthest} and is still loading`;
    return y >= furthest - RESTORE_TOLERANCE
      ? 'restored, to the bottom of a page that came back shorter'
      : `stopped at ${y}, and this shorter page's own bottom is ${furthest}`;
  }, { message: `Back must restore ${what}`, timeout: 15_000 }).toMatch(/^restored/);
  await settle;
}

/**
 * Scroll to the very bottom.
 *
 * `behavior: 'instant'` on purpose: index.css sets `scroll-behavior: smooth` on <html>, so the
 * plain two-argument form would animate and every assertion below would be racing the animation.
 */
async function scrollToBottom(page: Page): Promise<number> {
  await page.evaluate(() =>
    window.scrollTo({ top: document.body.scrollHeight, left: 0, behavior: 'instant' }));
  await expect.poll(() => scrollY(page)).toBeGreaterThan(0);
  return scrollY(page);
}

/** The teams named by the captured fixtures, so a stubbed team page can answer for any of them. */
function teamRefs(): ApiTeamRef[] {
  const refs: ApiTeamRef[] = [];
  for (const match of baseMatches()) {
    for (const side of [match.home, match.away]) if (side) refs.push(side);
  }
  return refs;
}

/**
 * Answer `GET /api/v1/teams/{id}`.
 *
 * stubBackend answers that path with an empty team, which renders the "Team not found" state — a
 * short page with no heading to land on. Registered AFTER stubBackend so Playwright reaches it
 * first, and matched by regex rather than glob so that `/teams/search` keeps going to the stub
 * that the header search depends on.
 */
async function stubTeamPages(page: Page, upcoming: ApiMatch[]): Promise<void> {
  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, async route => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    const team = teamRefs().find(ref => ref.id === id);
    if (!team) {
      return route.fulfill({
        status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Team not found' }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ team, upcoming, recent: [] }),
    });
  });
}

/** The captured fixture every scroll test walks into, and the club it links out to. */
const FIXTURE = baseMatches()[0];
const HOME_TEAM = FIXTURE.home as ApiTeamRef;
const COMPETITION = FIXTURE.competition as { id: string; name: string };

/**
 * A day on which ONE competition has more fixtures than a 1440x900 window can show.
 *
 * The captured day spreads 23 fixtures over five competitions, so filtering to one of them leaves
 * a list that fits on a desktop screen with nothing to scroll — and a scroll-restoration test on a
 * page that cannot scroll asserts nothing at all. Re-labelling four fifths of the fixtures keeps
 * every other captured field exactly as the backend serves it.
 */
function crowdedDay(iso: string): DayPayload {
  const stacked = baseMatches().map((match, index) =>
    (index % 5 === 4 ? match : { ...match, competition: FIXTURE.competition }));
  return dayPayload(iso, stacked);
}

async function openMatchDetail(page: Page): Promise<void> {
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { name: HOME_TEAM.name as string }).first()).toBeVisible();
}

/* ------------------------------------------------------------------ no sideways scroll, ever */

/**
 * The absolute rule. `/leagues` is in the list because it renders the header with no matchday
 * controls under it, so a header that only fits because the page below it is narrow still fails.
 */
const PAGES_UNDER_TEST: Array<[string, string]> = [
  ['the home page', '/'],
  ['the matches list', `/matches?date=${localDay(0)}`],
  ['a match detail page', `/match/${baseMatches()[0].id}`],
  ['the leagues index', '/leagues'],
];

for (const [name, path] of PAGES_UNDER_TEST) {
  test(`${name} does not scroll sideways, signed out`, async ({ page }) => {
    await stubBackend(page, { day: d => dayPayload(d) });
    await page.goto(path);
    await page.waitForLoadState('networkidle');

    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(OVERFLOW_TOLERANCE);
  });

  test(`${name} does not scroll sideways, signed in`, async ({ page }) => {
    // A signed-in header carries the account button instead of the sign-in link, and at 360 that
    // is the wider of the two. Asserting only the signed-out layout would miss it.
    await signIn(page);
    await stubBackend(page, { day: d => dayPayload(d) });
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: /account menu|qa/i }).first()).toBeVisible();

    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(OVERFLOW_TOLERANCE);
  });
}

/* ------------------------------------------------------------------------------- the menu */

test('the menu button is reachable and opens the menu', async ({ page }, testInfo) => {
  const width = testInfo.project.use.viewport?.width ?? 0;
  test.skip(width >= MENU_BREAKPOINT, 'the full navigation is on the bar at this width');

  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const button = page.getByRole('button', { name: /open main menu/i });
  await expect(button).toBeVisible();

  // Clipped by the right edge is the failure this catches: the button was in the DOM and
  // "visible", and its right edge sat past the viewport where a thumb cannot reach it.
  const box = await button.boundingBox();
  expect(box, 'the menu button must have a box').not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(width);
  expect(box!.x).toBeGreaterThanOrEqual(0);

  await expect(button).toHaveAttribute('aria-expanded', 'false');
  await button.click();
  await expect(page.getByRole('button', { name: /close main menu/i })).toHaveAttribute('aria-expanded', 'true');

  // Every destination, and the account action the narrow bar has no room for.
  const menu = page.locator('#mobile-menu');
  await expect(menu.getByRole('link', { name: 'Matches' })).toBeVisible();
  await expect(menu.getByRole('link', { name: 'Leagues' })).toBeVisible();
  await expect(menu.getByRole('link', { name: 'Create account' })).toBeVisible();
  // and the search box, which is the only way to search from a phone
  await expect(menu.locator('input[type="search"], input[placeholder*="Search" i]').first()).toBeVisible();
});

/* --------------------------------------------------- a forward move starts at the top */

test('opening a team from the foot of a match page lands at the top of the team page', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await stubTeamPages(page, baseMatches().slice(0, 8));
  await openMatchDetail(page);

  // The team links are the last thing on the match page, which is what made this fail: the team
  // page opened at whatever offset the match page had been left at — its own footer.
  const left = await scrollToBottom(page);
  expect(left, 'the match page must be tall enough for this to mean anything').toBeGreaterThan(200);

  await page.getByRole('link', { name: new RegExp(`^${HOME_TEAM.name}\\s*→`) }).click();
  await page.waitForURL(`**/teams/${HOME_TEAM.id}`);

  const heading = page.getByRole('heading', { level: 1, name: HOME_TEAM.name as string });
  await expect(heading).toBeVisible();
  await expect(heading).toBeInViewport();
  expect(await scrollY(page)).toBeLessThanOrEqual(2);
});

test('Back from the team page returns to where the match page was left', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await stubTeamPages(page, baseMatches().slice(0, 8));
  await openMatchDetail(page);

  const teamLink = page.getByRole('link', { name: new RegExp(`^${HOME_TEAM.name}\\s*→`) });
  const left = await scrollToAndReport(page, teamLink);
  expect(left, 'the match page must be tall enough for this to mean anything').toBeGreaterThan(200);

  await teamLink.click();
  await page.waitForURL(`**/teams/${HOME_TEAM.id}`);
  await expect(page.getByRole('heading', { level: 1, name: HOME_TEAM.name as string })).toBeVisible();

  /*
   * Read the team page from the top before going back, and prove we are actually there.
   *
   * Without this the test passes with the scroll handling removed entirely. With nothing managing
   * the scroll, a client-side navigation simply leaves the document at the offset the previous
   * page had — so the reader is still at `left` when they arrive on the team page, still at `left`
   * when they press Back, and "the match page came back to `left`" is satisfied by a position
   * that was never lost. Only a team page the reader has moved on can tell a restore from an
   * offset nobody ever touched.
   */
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  await expect.poll(() => scrollY(page), {
    message: 'the team page must be at the top before Back, or the restore proves nothing',
  }).toBeLessThanOrEqual(2);

  await page.goBack();
  await page.waitForURL(`**/match/${FIXTURE.id}`);
  await expect(page.getByRole('heading', { name: HOME_TEAM.name as string }).first()).toBeVisible();

  // The match page refetches on the way back, so it is short for a few frames before it is tall
  // enough to hold the offset again. Polling is the point: the restore is allowed to take those
  // frames, it is not allowed to never happen.
  await expectRestoredTo(page, left, 'the match page');
});

/*
 * WHICH ENGINE IS ACTUALLY BEING TESTED ABOVE, measured, not assumed.
 *
 * The test above was re-run with ScrollBehaviour.tsx neutered — the component mounted and doing
 * nothing at all — on all three mocked projects:
 *
 *   mocked-desktop (Chromium 1440)     FAILS: "stopped at 407, wanted 1086".
 *   mocked-mobile-360 (Chromium 360)   FAILS: "stopped at 859, wanted 1718".
 *   mocked-mobile (WebKit, iPhone 13)  PASSES. WebKit restores the scroll offset of a
 *                                      same-document history entry itself, so the assertion is
 *                                      satisfied by the engine rather than by anything in this
 *                                      repository.
 *
 * On the WebKit project, therefore, that test proves the reader is not stranded — worth asserting
 * on every engine, because it is the reader's experience and it has to hold whoever provides it —
 * but it does NOT prove this application restores anything there, and no assertion that can be
 * written about that page will, because the engine gets there first.
 *
 * What WebKit's own restoration does NOT do is wait for a page that is still arriving: neutered,
 * the slow-list test below ends at 2699 on WebKit with the reader's offset at 2037, the growth
 * having carried them past it. That is the case no engine covers, so that is the test that holds
 * this component to account — and it fails on all three projects without it.
 */

/**
 * Hold `GET /api/v1/matches` until the test lets it go, then let the stub answer it unchanged.
 *
 * Registered after stubBackend so Playwright reaches this handler first, and it falls through
 * rather than fulfilling, so the list is the same captured payload — only later. The pattern
 * deliberately does not match `/matches/live` or `/matches/{id}`: only the list is held.
 *
 * WHY A GATE AND NOT A DELAY, because this is the whole reason the slow-list tests were flaky.
 *
 * They used to hold the list back a fixed 4000ms and hope that landed in the gap between the
 * component's 1500ms convergence window and its 6000ms cap. What actually had to fit in the
 * remaining 2000ms was a whole cross-document load of /matches: Back destroys the document, so the
 * browser fetches the page, Vite serves the module graph, React mounts, react-query fires and
 * nineteen fixture rows render. Measured on an idle machine that is about 4.0s from Back to rows
 * — roughly 1.95s of headroom — and on a loaded one it is not. "Back to a list that arrives after
 * the restore window" passed 2 runs in 7 on mocked-desktop, always at the restore assertion,
 * because the rows were landing after the cap had already given up on them.
 *
 * A stopwatch cannot fix that; the machine is the variable. So the list is released on the
 * component's own signal instead — the test waits until the restore says it has left its
 * convergence window and is still owed, and only then lets the rows through. What remains inside
 * the cap is one already-answered route falling through and one render, inside the 4.5s that is
 * left of the watch: a margin of about forty times the work, rather than half of it.
 */
async function holdFixtureList(page: Page): Promise<() => void> {
  let release = (): void => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route(/\/api\/v1\/matches(\?|$)/, async route => {
    await held;
    await route.fallback();
  });
  return () => release();
}

/** Walk into a fixture from the crowded list, and report where the list was left. */
async function leaveListAtDepthAndOpenFixture(page: Page): Promise<number> {
  await page.goto(`/matches?date=${localDay(0)}&comp=${COMPETITION.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('fixture-list')).toBeVisible();

  const lastFixture = page.getByTestId('fixture-list').locator('a[href^="/match/"]').last();
  const left = await scrollToAndReport(page, lastFixture);
  expect(left, 'the list must be tall enough for this to mean anything').toBeGreaterThan(200);

  await lastFixture.click();
  await page.waitForURL('**/match/**');
  return left;
}

test('Back to a list that arrives after the restore window still lands where the reader was', async ({ page }) => {
  await stubBackend(page, { day: d => crowdedDay(d) });
  const left = await leaveListAtDepthAndOpenFixture(page);

  /*
   * Reload on the fixture page before going back.
   *
   * It empties the in-memory map — it lives in the module, and the module goes with the document —
   * so the offset can only come back from sessionStorage, which is the path a reader who left for
   * another site and returned takes. It also empties the react-query cache, which is what makes
   * the list genuinely refetch on the way back rather than paint from memory.
   */
  await page.reload();
  await page.waitForLoadState('networkidle');

  const releaseList = await holdFixtureList(page);
  await page.goBack();
  await page.waitForURL(url => url.pathname === '/matches');

  /*
   * THE MEASURED FAILURE THIS PINS, at 360px: the reader left the list at 1100; the skeleton they
   * came back to reached 1023, and the restore converged onto that bottom; the 1500ms window
   * expired with nothing more to converge onto; the rows landed at about 4.5s, the document grew
   * to 1754, and the browser's own scroll anchoring carried the reader down with the growth — to
   * the very bottom of a list they had been in the middle of, 654px past where they were.
   *
   * Re-measured here with only the cap put back to the old 1500ms and everything else in place:
   * 360 ends at 2691 with the reader's offset at 2043, 390 (WebKit) at 2639 with it at 2037, and
   * 1440 ends at 19 — the same abandoned restore, landing in a different arbitrary place.
   */
  await expectRestorePhase(page, 'holding',
    'the convergence window must close with the offset still out of reach — that is the case this '
    + 'test is named after, and the held list is what guarantees it',
    RESTORE_WINDOW_MS + 10_000);

  /*
   * The page really is the skeleton the restore could not satisfy, stated rather than raced.
   *
   * expectRestoredTo() has a guard of its own against accepting the bottom of a page that is
   * merely still waiting for its rows; these two lines are what prove the page is in exactly that
   * state, and they do it at an instant the test chose instead of one it happened to sample.
   */
  const skeleton = await scrollState(page);
  expect(skeleton.furthest, 'the skeleton must be shorter than the offset, or nothing is owed')
    .toBeLessThan(left - RESTORE_TOLERANCE);
  expect(Math.abs(skeleton.y - skeleton.furthest),
    'and the reader must have been converged onto its bottom, as close as it can reach')
    .toBeLessThanOrEqual(1);

  releaseList();

  await expectRestoredTo(page, left, 'a list that arrived after the convergence window closed');
  await expect(page.getByTestId('fixture-list').locator('a[href^="/match/"]').first()).toBeVisible();

  // And settled there, at the offset rather than at the bottom the growth used to deliver.
  await page.waitForTimeout(600);
  const settled = await scrollState(page);
  expect(settled.furthest, 'the arrived list must be taller than the skeleton, or nothing grew')
    .toBeGreaterThan(left);
  expect(settled.y, `the reader was at ${left}; this page's bottom is ${settled.furthest}`)
    .toBeLessThanOrEqual(left + RESTORE_TOLERANCE);
  expect(settled.y).toBeGreaterThanOrEqual(left - RESTORE_TOLERANCE);

  // And the page is handed back. The component holds the browser's own scroll anchoring off only
  // while a restore is owed; this one landed, so nothing of it may be left switched off.
  expect(await page.evaluate(() => [
    document.documentElement.style.overflowAnchor, document.body.style.overflowAnchor,
  ]), 'a restore that landed leaves the page\'s scroll anchoring as it found it').toEqual(['', '']);
});

/**
 * Wait until a running restore has actually PUT the reader somewhere, on a page that has stopped
 * growing — and report where.
 *
 * Both halves of that are load-bearing, and skipping them is what made the first version of the
 * scrollbar test below fail two runs in three on mocked-desktop. A skeleton that has not laid out
 * yet leaves the document at 0 with nothing to scroll, so a reader who "scrolls to the top" of it
 * has moved nothing at all: there is no takeover for the component to notice and nothing for this
 * test to assert on. And a page still growing is the one case the component's position check
 * deliberately ignores, because a height that changed is content arriving rather than a reader.
 */
async function whereTheRestorePutTheReader(page: Page): Promise<number> {
  let previous = -1;
  await expect.poll(async () => {
    const { y, furthest } = await scrollState(page);
    const settled = furthest === previous;
    previous = furthest;
    if (y <= 2) return `the restore has not moved the page yet (reaches ${furthest})`;
    return settled ? 'placed' : `the skeleton is still growing (reaches ${furthest})`;
  }, {
    message: 'the restore must have placed the reader on a settled skeleton before they take over',
    timeout: 15_000,
  }).toBe('placed');
  return scrollY(page);
}

/**
 * Both ways a reader can take the page back from a restore that is still running.
 *
 * `a keypress` is one of the events the watch has always listened for. `a scrollbar drag` is the
 * reader it used to fight: dragging the scrollbar fires no wheel, no touchstart and no keydown,
 * and neither does middle-click autoscroll, so for the whole six seconds of the watch their own
 * scrolling was undone every frame. That hole existed at 1500ms too; lengthening the watch made it
 * four times longer.
 *
 * Playwright cannot dispatch a scrollbar drag portably — an iPhone 13 has no scrollbar to grab and
 * where there is one its geometry belongs to the platform — so this reader moves the page the way
 * both of those do AS THE COMPONENT SEES IT: the offset changes, and not one input event fires.
 * That is the signature the component's position check answers, and it is also the signature of
 * find-in-page, which sends no DOM event at all. It is deliberately NOT the same signature as the
 * `mousedown` the component now also listens for, so this case still stands on the general check
 * rather than on the list of inputs somebody happened to think of.
 */
const TAKEOVERS: Array<[string, (page: Page) => Promise<void>]> = [
  ['a keypress', async page => {
    await page.keyboard.press('Home');
    await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  }],
  ['a scrollbar drag', async page => {
    await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  }],
];

for (const [how, takeOver] of TAKEOVERS) {
  test(`a reader who takes the page back with ${how} during a slow restore keeps it`, async ({ page }) => {
    /*
     * The constraint that comes with waiting longer. This guards the restore's MANNERS rather than
     * its existence: it is here because extending the watch to six seconds is exactly the change
     * that could start yanking a reader who has given up waiting and begun reading the top of the
     * page.
     *
     * That is a statement about what it is for, not a concession that it passes for free.
     * Re-measured with ScrollBehaviour neutered — both of its effects short-circuited, the
     * component mounted and doing nothing — on mocked-desktop: BOTH cases fail, and they fail on
     * the same line, "a restore must be converging, or there is nothing for the reader to take
     * over from". With nothing placing the reader on the skeleton there is no restore to take the
     * page back from, so the case cannot be set up, let alone passed.
     *
     * What this test does not pin on its own is the reader's half of it, which is why it is a
     * table: with the component's position check removed the keypress case still passes and only
     * the scrollbar-drag case fails. The two mechanisms hold each other up, separately.
     */
    await stubBackend(page, { day: d => crowdedDay(d) });
    const left = await leaveListAtDepthAndOpenFixture(page);
    await page.reload();
    await page.waitForLoadState('networkidle');

    const releaseList = await holdFixtureList(page);
    await page.goBack();
    await page.waitForURL(url => url.pathname === '/matches');

    // Inside the convergence window, which is when the restore is at its most insistent: it is
    // moving the page every single frame. Waited for rather than timed, so the reader always acts
    // while there is something to take the page back from.
    await expectRestorePhase(page, 'converging',
      'a restore must be converging, or there is nothing for the reader to take over from', 10_000);
    const placed = await whereTheRestorePutTheReader(page);
    await takeOver(page);

    // The reader really did move the page off the offset the restore had put it on. Without this
    // a takeover that happened to land where the component already was would look like a pass.
    expect(await scrollY(page), `the reader must move the page off the ${placed} the restore chose`)
      .toBeLessThan(placed - 2);

    // The restore let go, and said so. Without this the assertions below would also be satisfied
    // by a watch that simply never got round to moving anybody.
    await expectRestorePhase(page, null,
      'the restore must abandon itself the moment the reader moves the page themselves', 5_000);

    releaseList();
    const rows = page.getByTestId('fixture-list').locator('a[href^="/match/"]');
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(600);

    const settled = await scrollState(page);
    expect(settled.furthest, 'the list must have arrived, or this proves nothing').toBeGreaterThan(left);
    expect(settled.y, 'a restore must never outrank a position the reader chose for themselves')
      .toBeLessThanOrEqual(RESTORE_TOLERANCE);
  });
}

test('past its cap the restore gives up, and the page growing afterwards does not move the reader', async ({ page }) => {
  /*
   * WHAT HOLDS RESTORE_MAX_MS IN PLACE, and what happens on the far side of it.
   *
   * Six seconds is a judgement call, and until this test it was a judgement call nothing could
   * catch. Measured: with RESTORE_MAX_MS set to sixty seconds, every other test in this file is
   * still green on mocked-desktop — sixteen passed, two skipped at that width — and this is the
   * only one that fails. Before it, the number could have drifted anywhere. It holds because the list is not released until the restore has given
   * up on its own, which is only observable if it does give up — at sixty seconds the wait below
   * times out instead — and because the time that took is then measured against the number itself.
   *
   * And past the cap, measured on this component as it stood at the start of this round with the
   * list held seven seconds: the reader who left the Galaxy S8 list at 2043 was converged onto the
   * skeleton's bottom at 765, the watch expired, the rows landed, and the browser's own scroll
   * anchoring carried them to 2691 — the very
   * bottom of the list, which is the original defect arriving a second late. WebKit at 390 did the
   * same, 751 to 2699; Chromium at 1440 left them at 19. Three engines, three arbitrary answers.
   *
   * The fallback is now a decision: for as long as a restore is owed the component holds the
   * browser's scroll anchoring off, and an expired cap keeps it held. So the reader stays exactly
   * where the convergence left them — as close to where they were as the page could reach while
   * they waited — and the rows arriving underneath them move nobody. That is what the last three
   * assertions say: not the saved offset, not the bottom, and not one pixel from where it stopped.
   */
  await stubBackend(page, { day: d => crowdedDay(d) });
  const left = await leaveListAtDepthAndOpenFixture(page);
  await page.reload();
  await page.waitForLoadState('networkidle');

  const releaseList = await holdFixtureList(page);
  const wentBack = Date.now();
  await page.goBack();
  await page.waitForURL(url => url.pathname === '/matches');

  await expectRestorePhase(page, null,
    `the restore must give up on its own: RESTORE_MAX_MS is ${RESTORE_MAX_MS}ms in ScrollBehaviour.tsx`,
    RESTORE_MAX_MS + 6_000);
  const gaveUpAfter = Date.now() - wentBack;
  const abandoned = await scrollState(page);
  // The mechanism the fallback below is made of, read while it is doing its work: an expired cap
  // is the one ending that keeps the browser's scroll anchoring held off.
  const anchoring = await page.evaluate(() =>
    getComputedStyle(document.documentElement).overflowAnchor);

  releaseList();
  await expect(page.getByTestId('fixture-list').locator('a[href^="/match/"]').first())
    .toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(800);
  const settled = await scrollState(page);

  // The cap is where the component says it is. The lower bound is the load-bearing one — the watch
  // starts after this clock does, so it can never legitimately end early — and the upper bound
  // allows for the document load before the watch begins and for the polling above noticing late.
  expect(gaveUpAfter, `a restore may not end before its ${RESTORE_MAX_MS}ms cap`)
    .toBeGreaterThanOrEqual(RESTORE_MAX_MS);
  expect(gaveUpAfter, `nor long after it`).toBeLessThan(RESTORE_MAX_MS + 4_000);

  // It really was the cap that ended it: the list was still held, so nothing could have satisfied
  // the restore and no reader touched the page.
  expect(abandoned.furthest, 'the list must still have been held when the watch ended')
    .toBeLessThan(left - RESTORE_TOLERANCE);
  expect(anchoring, 'an expired cap keeps the browser\'s scroll anchoring off — that is the fallback')
    .toBe('none');

  expect(settled.furthest, 'the arrived list must be taller than the skeleton, or nothing grew')
    .toBeGreaterThan(abandoned.furthest);
  expect(Math.abs(settled.y - abandoned.y),
    `the reader was left at ${abandoned.y}; the rows arriving must not move them`)
    .toBeLessThanOrEqual(1);
  expect(settled.y, 'and past the cap the saved offset is not pursued after all')
    .toBeLessThan(left - RESTORE_TOLERANCE);
  expect(settled.y, `nor is the bottom of the arrived list where anybody asked to be`)
    .toBeLessThan(settled.furthest - RESTORE_TOLERANCE);
});

test('a fresh document does not inherit the offset the last document left in this tab', async ({ page }) => {
  /*
   * Saved offsets are keyed by `location.key`, and React Router names the FIRST location of every
   * document with the literal string `default`. The map is mirrored into sessionStorage, which
   * survives a document load — so two different first locations in one tab (a reader who walks
   * off to another site and comes back to a different page of ours, or simply follows a link that
   * loads a fresh document) both ask for the slot called `default`, and the second is handed the
   * first one's offset. Nothing about that offset has anything to do with the page it is applied
   * to.
   *
   * Two goto()s ARE that case: each is a real document load, and the outgoing one writes its
   * offsets out on pagehide. Measured with the offsets keyed by `location.key` alone: the leagues
   * page opened at y=407 at 1440 and y=1059 at 390 and 360, having never been scrolled by anyone.
   *
   * WHY THIS WATCHES RATHER THAN LOOKS ONCE. Reading window.scrollY a single time, just after
   * networkidle, is a coin toss. An inherited offset is applied by the same restore machinery as
   * any other: it converges for 1500ms and keeps watching to 6000ms, so whether one sample lands
   * before or after the yank depends entirely on how quickly the leagues page grew tall enough to
   * be yanked. Reverted to keying on `location.key` alone — the defect present, in other words —
   * this test passed 1 run in 3 at 360, which makes it no evidence at all. So a probe records the
   * furthest the document is EVER scrolled to, from its first frame, and the assertion is made
   * after the whole watch has had time to run. Under the same revert, this version fails 3 runs in
   * 3 on every one of the three projects — at 407 on mocked-desktop and 1059 on both phones.
   */
  const furthestEverScrolled = () =>
    page.evaluate(() => (window as unknown as { __maxScrollY?: number }).__maxScrollY);

  await page.addInitScript(() => {
    const store = window as unknown as { __maxScrollY: number };
    store.__maxScrollY = 0;
    const sample = (): void => {
      store.__maxScrollY = Math.max(store.__maxScrollY, window.scrollY);
      requestAnimationFrame(sample);
    };
    sample();
  });

  await stubBackend(page, { day: d => crowdedDay(d) });
  await page.goto(`/matches?date=${localDay(0)}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('fixture-list')).toBeVisible();

  const left = await scrollToBottom(page);
  expect(left, 'the list must be tall enough for this to mean anything').toBeGreaterThan(200);

  // The probe follows a page that really is scrolled. Without this the assertion below would be
  // satisfied just as well by a probe that had never run: nought is nought either way.
  await expect.poll(furthestEverScrolled, {
    message: 'the probe must follow the scroll position, or it proves nothing on the page below',
  }).toBeGreaterThanOrEqual(left - 1);

  await page.goto('/leagues');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();

  // Long enough for a restore on this fresh document to have converged, watched and given up, so
  // a yank arriving late cannot hide behind the end of the test.
  await page.waitForTimeout(RESTORE_MAX_MS + 500);

  const { y, furthest } = await scrollState(page);
  expect(furthest, 'the leagues page must be scrollable, or this proves nothing').toBeGreaterThan(100);
  expect(await furthestEverScrolled(),
    'a page opened fresh starts at its top and stays there, whatever the last page in this tab did')
    .toBeLessThanOrEqual(2);
  expect(y, 'and it is still there at the end').toBeLessThanOrEqual(2);
});

test('Back from a fixture restores the filtered list, its filters and its position', async ({ page }) => {
  await stubBackend(page, { day: d => crowdedDay(d) });

  const competition = COMPETITION;
  const listUrl = `/matches?date=${localDay(0)}&comp=${competition.id}`;
  await page.goto(listUrl);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('fixture-list')).toBeVisible();

  // The filter really is applied before we leave, so "the filters came back" is a real assertion.
  const chip = page.getByTestId('active-filter-chip').filter({ hasText: competition.name });
  await expect(chip).toBeVisible();

  // The LAST fixture, not the first: a click scrolls its target into view, so opening the first
  // row would quietly scroll the list back up and the test would be measuring that instead.
  const lastFixture = page.getByTestId('fixture-list').locator('a[href^="/match/"]').last();
  const left = await scrollToAndReport(page, lastFixture);
  expect(left, 'the list must be tall enough for this to mean anything').toBeGreaterThan(200);

  await lastFixture.click();
  await page.waitForURL('**/match/**');
  await expect.poll(() => scrollY(page), {
    message: 'the fixture page itself must open at the top',
  }).toBeLessThanOrEqual(2);

  await page.goBack();
  await page.waitForURL(url => url.pathname === '/matches');

  // the list, its filters, and the place in it — all three
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  expect(new URL(page.url()).searchParams.get('comp')).toBe(competition.id);
  await expect(page.getByTestId('active-filter-chip').filter({ hasText: competition.name })).toBeVisible();
  await expectRestoredTo(page, left, 'the filtered list');

  /*
   * And it STAYS restored.
   *
   * This is the assertion the whole same-path rule exists for. The workspace writes its state back
   * into the URL with `replace: true`, and a replace mints a fresh history key — so if a URL
   * rewrite counted as a forward move, one arriving in the moments after Back would throw away the
   * position that was just restored, and it would do it late enough that a poll had already passed.
   * Hence the settle: nothing is allowed to undo this afterwards.
   */
  await page.waitForTimeout(600);
  const settled = await scrollState(page);
  expect(settled.y, 'a URL rewrite after Back must not send the reader to the top')
    .toBeGreaterThan(Math.min(left, settled.furthest) - RESTORE_TOLERANCE);
});

/* ------------------------------------------------- the filter sheet still behaves as it did */

test('Escape closes the filter sheet and gives focus back to the button that opened it', async ({ page }) => {
  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto(`/matches?date=${localDay(0)}`);
  await page.waitForLoadState('networkidle');

  // Opened from the keyboard, which is the reader this assertion is about: WebKit does not focus
  // a button on click at all, so a click-opened sheet has no focus to give back and the test would
  // be measuring the platform rather than the sheet.
  const open = page.getByTestId('filter-sheet-open').first();
  await open.focus();
  await expect(open).toBeFocused();
  await page.keyboard.press('Enter');
  const sheet = page.getByTestId('filter-sheet');
  await expect(sheet).toBeVisible();
  await expect(page.getByTestId('filter-result-count').first()).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await expect(open).toBeFocused();

  // and the header menu, whose own Escape handler is new, must not have been dragged open or shut
  // by that keypress
  await expect(page.locator('#mobile-menu')).toHaveCount(0);
});

test('Escape closes the header menu and gives focus back to the menu button', async ({ page }, testInfo) => {
  const width = testInfo.project.use.viewport?.width ?? 0;
  test.skip(width >= MENU_BREAKPOINT, 'there is no menu button at this width');

  await stubBackend(page, { day: d => dayPayload(d) });
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const button = page.getByRole('button', { name: /open main menu/i });
  await button.click();
  await expect(page.locator('#mobile-menu')).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(page.locator('#mobile-menu')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /open main menu/i })).toBeFocused();
});
