import { expect, test, Page, Request, Route } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import {
  API_FOOTBALL_REFUSAL, ApiMatch, FORECASTS_WAITING, Json, LAST_PROVIDER_WRITE, LIVESCORE_REFUSAL,
  ProviderStatusPayload, THESPORTSDB_REFUSAL, baseMatches, dayPayload, emptyDayPayload, matchDataBlockedStatus,
  matchDataDegradedStatus, matchDataHealthyStatus, matchDetail, refusingStatusWithoutBlock, stubBackend,
} from '../support/api-stub';
import { signIn } from '../support/auth';

/**
 * MOCKED: what a reader is told when fixture and result updates cannot reach us — and that the
 * forecasts we already hold are still there.
 *
 * THE NIGHT THIS IS ABOUT. On 2026-10-07 every match-data source refused at once — Live Score's
 * access was disabled (HTTP 401), API-Football's free plan excluded the season, TheSportsDB rejected
 * its key — while the forecast provider answered every request. The pages said so badly or not at
 * all: the banner named one provider by its internal key and quoted its English on the French page
 * too, and the freshness line said "fixtures and scores last refreshed 4 minutes ago" because the
 * recover and settle passes, which fetch nothing, had just succeeded. No page said since when, and
 * no page said the forecasts were fine.
 *
 * The backend now publishes one `match_data` block (blocked / degraded / ok / unknown) and this
 * pins what each surface does with it, in English and in French, in the Douala zone:
 *   * the banner leads with one sentence — no vendor, no HTTP code, no link — and keeps every
 *     source's reason, with its own words marked as English, inside the disclosure;
 *   * the freshness line states the last provider write, never a task's success, and collapses
 *     the per-task failures into one line (the rows behind the disclosure keep them);
 *   * the match page says a kick-off time cannot be re-checked and an overdue result cannot
 *     arrive, while the forecast and its markets render as they always did;
 *   * the empty day, the slip, the selection history and the suggestions each say what the block
 *     means for them, and the suggestions count the forecasts waiting for their fixtures;
 *   * degraded, healthy and an older backend with no block show none of it, and the banner on an
 *     older backend is exactly the banner it always was;
 *   * the fixture clock of a HEALTHY backend that runs recover and settle no longer takes its age
 *     from them — the stub schedulers never had either task, which is why nothing caught it;
 *   * nothing asks the backend to refresh from a provider.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';
const DOUALA = 'Africa/Douala';
const HOUR = 60 * 60 * 1000;

const catalogue = (language: Language) => (language === 'fr' ? fr : en) as Record<keyof typeof en, string>;
const say = (language: Language, key: keyof typeof en, params: Record<string, string | number> = {}): string =>
  renderMessage(compileMessage(catalogue(language)[key]), language, params);

/**
 * A catalogue sentence with its holes left open, for a value only the page can format — a relative
 * time, a date in the reader's zone. Anchored by default: the whole text, and nothing else.
 */
function shape(language: Language, key: keyof typeof en, holes: string[], anchored = true): RegExp {
  const params = Object.fromEntries(holes.map(hole => [hole, `@@${hole}@@`]));
  const escaped = say(language, key, params).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const body = holes.reduce((text, hole) => text.replace(`@@${hole}@@`, '.+?'), escaped);
  return new RegExp(anchored ? `^${body}$` : body);
}

async function seedPreferences(page: Page, language: Language): Promise<void> {
  await page.addInitScript(([languageKey, zoneKey, chosen, zone]) => {
    window.localStorage.setItem(languageKey, chosen);
    window.localStorage.setItem(zoneKey, zone);
  }, [LANGUAGE_KEY, ZONE_KEY, language, DOUALA] as const);
}

/**
 * `{since}` as the page must print it: the backend's instant in the reader's chosen zone, in the
 * reader's language — formatted by the browser's own Intl, the same one the application uses.
 */
async function sinceOnPage(page: Page, language: Language): Promise<string> {
  return page.evaluate(([iso, locale, zone]) => new Intl.DateTimeFormat(locale, {
    timeZone: zone, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso)), [LAST_PROVIDER_WRITE, language === 'fr' ? 'fr-FR' : 'en-GB', DOUALA] as const);
}

const normalise = (text: string | null): string => (text ?? '').replace(/\s+/g, ' ').trim();

/** Everything this package adds to a page, by test id. Healthy, degraded and older backends show none. */
const NEW_ELEMENTS = [
  'match-data-lead', 'match-data-detail', 'match-data-caveat', 'matchday-empty-blocked',
  'slip-leg-result-blocked', 'history-leg-result-blocked', 'suggest-blocked',
];

/* ------------------------------------------------------------------------------ fixtures */

const iso = (msFromNow: number): string => new Date(Date.now() + msFromNow).toISOString().replace(/\.\d{3}Z$/, 'Z');

/** The captured fixture with its forecast and brief, moved in time and renamed. */
function fixture(id: string, kickoffMs: number, status: string, over: Json = {}): ApiMatch {
  const match = matchDetail(baseMatches()[0].id)!;
  match.id = id;
  match.kickoff_utc = iso(kickoffMs);
  match.status = status;
  match.result_expected_by = iso(kickoffMs + 150 * 60 * 1000);
  return Object.assign(match, over);
}

const UPCOMING = 'blocked-upcoming';
const OVERDUE = 'blocked-overdue';
const IN_PLAY = 'blocked-in-play';
const FIXTURES: Record<string, () => ApiMatch> = {
  [UPCOMING]: () => fixture(UPCOMING, 26 * HOUR, 'scheduled'),
  [OVERDUE]: () => fixture(OVERDUE, -4 * HOUR, 'scheduled'),
  [IN_PLAY]: () => fixture(IN_PLAY, -30 * 60 * 1000, 'live', { minute: '30' }),
};

/** One slip with a selection waiting for its result and one still to kick off. */
function slipWith(language: Language): Json {
  const [first, second] = baseMatches();
  const summary = (match: ApiMatch, kickoffMs: number) => ({
    id: match.id, home: match.home, away: match.away, competition: match.competition,
    kickoff_utc: iso(kickoffMs), status: 'scheduled',
  });
  const leg = (id: string, match: ApiMatch, kickoffMs: number): Json => ({
    id, position: 0, match: summary(match, kickoffMs),
    selection: { selection_id: 'match_result:home', market_id: 'match_result', outcome: 'home', line: null, period: 'regulation' },
    probability: 0.55, probability_source: 'provider', calculation: null, provider: 'gameforecast',
    snapshot_id: null, model_run_at: null, forecast_fetched_at: null, normalisation_version: 'markets.v1',
    odds: null, kickoff_utc: iso(kickoffMs), started: kickoffMs < 0,
    result_expected_by: iso(kickoffMs + 150 * 60 * 1000),
    current: { probability: 0.55, available: true, forecast_changed: false, state: 'available' },
    state: 'pending', settled_at: null, settlement: null, settlement_capability: null,
  });
  return {
    id: 'slip-waiting', name: language === 'fr' ? 'En attente' : 'Waiting', status: 'draft', note: null,
    currency: null, stake: null, price: null, price_source: null, price_missing_legs: 2,
    price_note: 'no combined price: at least one selection has no price for exactly that selection',
    effective_price: null, effective_price_source: null, effective_price_note: null, potential: null,
    potential_withheld_reason: null, recorded_at: null, recorded_reference: null, recorded_note: null,
    state: 'pending', settled_at: null,
    counts: { legs: 2, pending: 2, won: 0, lost: 0, void: 0, unresolved: 0 },
    created_at: iso(-6 * HOUR), updated_at: iso(-6 * HOUR),
    legs: [leg('leg-overdue', first, -4 * HOUR), leg('leg-ahead', second ?? first, 30 * HOUR)],
  };
}

interface Traffic { refreshing: string[]; dayReads: string[]; lean: number }

/** The stubbed backend in a given state, the slips and suggestions on top, and every request seen. */
async function stubState(page: Page, language: Language, status: ProviderStatusPayload, options: {
  emptyDay?: boolean; suggestions?: Json; dayMatches?: ApiMatch[];
} = {}): Promise<Traffic> {
  const traffic: Traffic = { refreshing: [], dayReads: [], lean: 0 };
  page.on('request', (request: Request) => {
    const url = new URL(request.url());
    if (url.searchParams.get('refresh') === 'true') traffic.refreshing.push(request.url());
    if (url.pathname.endsWith('/api/v1/matches')) traffic.dayReads.push(url.searchParams.get('refresh') ?? 'absent');
    if (url.pathname.endsWith('/api/v1/data-providers/match-data')) traffic.lean += 1;
  });
  await seedPreferences(page, language);
  await stubBackend(page, {
    status,
    day: options.emptyDay ? (date => emptyDayPayload(date))
      : options.dayMatches ? (date => dayPayload(date, options.dayMatches)) : undefined,
    matchById: id => FIXTURES[id]?.() ?? null,
  });
  // Registered AFTER stubBackend on purpose: Playwright tries the most recently added route first.
  const json = (route: Route, body: unknown) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/api/v1/me/slips**', (route: Route, request: Request) => (
    request.method() === 'GET' ? json(route, { slips: [slipWith(language)] }) : route.fallback()));
  if (options.suggestions) {
    await page.route('**/api/v1/suggestions?**', route => json(route, options.suggestions));
  }
  return traffic;
}

const NO_FIXTURES = {
  generated_at: new Date().toISOString(), rules: {},
  pool: { fixtures_in_window: 0, qualifying: 0, excluded: {} }, combinations: [],
  shortfall: 'no scheduled fixture kicks off in this window',
  shortfall_reasons: [{ reason: 'no_fixtures', count: 0 }],
};

/* ================================================================== in both languages */

for (const language of ['en', 'fr'] as const) {
  test.describe(`fixture and result updates blocked, in ${language}`, () => {
    test('the banner leads with one plain sentence and keeps every source in its disclosure', async ({ page }) => {
      await stubState(page, language, matchDataBlockedStatus());
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const banner = page.getByTestId('provider-status-banner');
      await expect(banner).toHaveAttribute('data-state', 'blocked');
      const since = await sinceOnPage(page, language);
      const lead = page.getByTestId('match-data-lead');
      await expect(lead).toHaveText(say(language, 'banner.matchData.blocked', { since }));
      // Nothing of the plumbing on the visible line: no vendor, no HTTP code, no link.
      const leadText = normalise(await lead.textContent());
      expect(leadText).not.toMatch(/livescore|live score|api-football|thesportsdb|http|401|400|plan\b|abonnement/i);

      // Every source, one disclosure away, with our reason and then its own words marked as English.
      const sources = banner.getByTestId('match-data-source');
      await expect(sources).toHaveCount(3);
      await expect(sources.first()).toBeHidden();
      await banner.getByTestId('match-data-detail').locator('summary').click();
      await expect(sources.first()).toBeVisible();
      const expected = [
        { name: 'livescore', kind: 'access', reason: 'freshness.reason.accessNotEnabled', label: 'fixtureProvider.livescore', said: LIVESCORE_REFUSAL },
        { name: 'api_football', kind: 'plan', reason: 'freshness.reason.plan', label: 'fixtureProvider.apiFootball', said: API_FOOTBALL_REFUSAL },
        { name: 'thesportsdb', kind: 'access', reason: 'freshness.reason.credentials', label: 'fixtureProvider.thesportsdb', said: THESPORTSDB_REFUSAL },
      ] as const;
      for (const [index, source] of expected.entries()) {
        const line = sources.nth(index);
        await expect(line).toHaveAttribute('data-source', source.name);
        await expect(line).toHaveAttribute('data-kind', source.kind);
        await expect(line).toContainText(say(language, 'banner.matchData.source', {
          source: say(language, source.label), reason: say(language, source.reason),
        }));
        const verbatim = line.getByTestId('match-data-verbatim');
        await expect(verbatim).toHaveAttribute('lang', 'en');
        await expect(verbatim).toHaveText(source.said);
      }
      // And when anything will next try: a measured time, never a promise that it will work.
      await expect(banner.getByTestId('match-data-detail').locator('li').last())
        .toHaveText(shape(language, 'freshness.nextAttempt.ahead', ['when']));
    });

    test('the lead never promises forecasts the forecast source cannot give', async ({ page }) => {
      const status = matchDataBlockedStatus();
      const provider = String(status.forecasts?.active_provider ?? 'gameforecast');
      status.forecasts = { ...status.forecasts, active_provider: provider, configured: false };
      await stubState(page, language, status);
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const since = await sinceOnPage(page, language);
      const lead = page.getByTestId('match-data-lead');
      await expect(lead).toHaveText(`${say(language, 'banner.matchData.blockedOnly', { since })} ${say(language, 'forecast.notConfigured', { provider })}`);
      expect(normalise(await lead.textContent())).not.toContain(
        normalise(say(language, 'banner.matchData.blocked', { since }).replace(say(language, 'banner.matchData.blockedOnly', { since }), '')));
    });

    test('the freshness line states the last provider write, never a refresh minutes ago', async ({ page }) => {
      await stubState(page, language, matchDataBlockedStatus());
      await page.goto('/matches');
      await page.waitForLoadState('networkidle');

      const block = page.getByTestId('data-freshness');
      await expect(block).toHaveAttribute('data-match-data', 'blocked');
      const since = await sinceOnPage(page, language);
      await expect(block.getByTestId('freshness-summary')).toHaveText(say(language, 'freshness.summary.blocked', { since }));
      // The sentence that was false on 2026-10-07, in neither language.
      const text = normalise(await block.textContent());
      expect(text).not.toContain(say(language, 'freshness.summary.refreshed', { age: '' }).trim());
      // One line instead of three near-identical failure notes; the rows keep the detail.
      const notes = block.getByTestId('freshness-note').locator('p');
      await expect(notes).toHaveCount(1);
      await expect(notes.first()).toHaveText(say(language, 'freshness.line.blocked'));
      expect(text).not.toContain(say(language, 'freshness.reason.credentials'));
      // The forecasts keep their own clock, and it is still current.
      await expect(block.getByTestId('freshness-forecasts')).toHaveText(shape(language, 'freshness.forecasts.refreshed', ['age']));

      await block.getByTestId('freshness-detail').locator('summary').click();
      const settle = block.locator('[data-testid="freshness-task"][data-task="settle"]');
      await expect(settle.locator('dt')).toHaveText(say(language, 'sync.task.settle'));
      const fixtures = block.locator('[data-testid="freshness-task"][data-task="fixtures"]');
      await expect(fixtures).toContainText(say(language, 'freshness.task.providerSaid', { reason: LIVESCORE_REFUSAL }));
      // The next attempt, which the collapsed line no longer states, stays on the row.
      await expect(fixtures).toContainText(shape(language, 'freshness.nextAttempt.ahead', ['when'], false));
    });

    test('the match page keeps its forecast and says what cannot change', async ({ page }) => {
      await stubState(page, language, matchDataBlockedStatus());

      await page.goto(`/match/${UPCOMING}`);
      await page.waitForLoadState('networkidle');
      const kickoff = page.getByTestId('match-data-caveat');
      await expect(kickoff).toHaveAttribute('data-caveat', 'kickoff');
      await expect(kickoff).toHaveText(say(language, 'matchData.match.kickoff'));
      await expect(page.getByTestId('provider-forecast').getByTestId('market-table')).toBeVisible();
      await expect(page.getByTestId('result-delay-notice')).toHaveCount(0);

      await page.goto(`/match/${OVERDUE}`);
      await page.waitForLoadState('networkidle');
      const notice = page.getByTestId('result-delay-notice');
      await expect(notice).toHaveAttribute('data-blocked', 'true');
      await expect(notice.getByTestId('result-delay-detail')).toHaveText(shape(language, 'fixture.result.blockedDetail', ['due']));
      await expect(page.getByTestId('match-data-caveat')).toHaveCount(0);
      await expect(page.getByTestId('provider-forecast').getByTestId('market-table')).toBeVisible();

      await page.goto(`/match/${IN_PLAY}`);
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('match-data-caveat')).toHaveAttribute('data-caveat', 'live');
      await expect(page.getByTestId('match-data-caveat')).toHaveText(say(language, 'matchData.match.live'));
      await expect(page.getByTestId('provider-forecast').getByTestId('market-table')).toBeVisible();
    });

    test('an overdue row on the day list says result updates are unavailable', async ({ page }) => {
      await stubState(page, language, matchDataBlockedStatus(), { dayMatches: [FIXTURES[OVERDUE]()] });
      await page.goto('/matches');
      await page.waitForLoadState('networkidle');
      const line = page.getByTestId('result-delay-line').first();
      await expect(line).toHaveAttribute('data-blocked', 'true');
      await expect(line).toHaveText(shape(language, 'fixture.result.blockedShort', ['due']));
    });

    test('an empty day says it cannot fill itself while updates are blocked', async ({ page }) => {
      await stubState(page, language, matchDataBlockedStatus(), { emptyDay: true });
      await page.goto('/matches');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('matchday-empty-blocked')).toHaveText(shape(language, 'matchday.emptyBlocked', ['date']));
      // A variant, not an addition: the usual description is not printed beside it.
      await expect(page.getByText(shape(language, 'matchday.emptyDescription', ['date']))).toHaveCount(0);
    });

    test('a selection waiting for its result says it cannot settle for now, in the slip and the history', async ({ page }) => {
      await signIn(page);
      const traffic = await stubState(page, language, matchDataBlockedStatus());
      await page.goto('/selections');
      await page.waitForLoadState('networkidle');

      const waiting = page.locator('[data-testid="history-leg"][data-state="pending"]');
      await expect(waiting).toHaveCount(2);
      const blockedLine = page.getByTestId('history-leg-result-blocked');
      await expect(blockedLine).toHaveCount(1, { timeout: 10_000 });
      await expect(blockedLine).toHaveText(say(language, 'selections.history.awaitingBlocked'));
      // A variant, not an addition: the plain "awaiting" line is not printed beside it.
      await expect(page.getByText(say(language, 'selections.history.awaiting'), { exact: true })).toHaveCount(0);

      await page.getByTestId('slip-dock-toggle').click();
      const dock = page.getByTestId('slip-dock');
      await expect(dock.getByTestId('slip-leg-result-blocked')).toHaveCount(1);
      await expect(dock.getByTestId('slip-leg-result-blocked')).toHaveText(say(language, 'selections.dock.resultBlocked'));
      // One lean request served both, memoised; never the whole status payload for it.
      expect(traffic.lean).toBeLessThanOrEqual(1);
    });

    test('suggestions say they use only stored fixtures and count the forecasts waiting', async ({ page }) => {
      const traffic = await stubState(page, language, matchDataBlockedStatus(), { suggestions: NO_FIXTURES });
      await page.goto('/selections/suggestions');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('suggest-blocked-note')).toHaveText(say(language, 'selections.suggest.blockedNote'));
      await expect(page.getByTestId('suggest-forecasts-waiting')).toHaveText(
        say(language, 'selections.suggest.forecastsWaiting', { count: FORECASTS_WAITING }));
      await expect(page.getByTestId('suggest-no-fixtures')).toHaveText(say(language, 'selections.suggest.reason.noFixturesBlocked'));
      expect(traffic.lean, 'the lean endpoint, once').toBe(1);
    });
  });

  test.describe(`every other state leaves the pages as they were, in ${language}`, () => {
    test('healthy: none of it, and the fixture age no longer comes from recover or settle', async ({ page }) => {
      await signIn(page);
      await stubState(page, language, matchDataHealthyStatus());
      await page.goto('/matches');
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('provider-status-banner')).toHaveCount(0);
      // Recover and settle succeeded a minute ago and the idle live pass polled nothing; results,
      // eight minutes ago, is the youngest pass that fetched anything - "last checked". The newest
      // row a provider's answer wrote is eight minutes old too - "last arrived" - and the line keeps
      // the two apart: a check that brought nothing could never move the first clock.
      const minutes = (count: number) => say(language, 'time.ago', { duration: say(language, 'duration.minutes', { count }) });
      const summary = page.getByTestId('freshness-summary');
      const text = normalise(await summary.textContent());
      const either = [8, 9];
      expect(either.flatMap(arrived => either.map(checked =>
        say(language, 'freshness.summary.retrieved', { retrieved: minutes(arrived), checked: minutes(checked) })))).toContain(text);
      expect(text).not.toContain(say(language, 'freshness.summary.refreshed', { age: '' }).trim());

      for (const route of ['/matches', `/match/${UPCOMING}`, `/match/${OVERDUE}`, '/selections', '/selections/suggestions']) {
        await page.goto(route);
        await page.waitForLoadState('networkidle');
        if (route === '/selections') {
          // Open the slip, so its legs - one of them waiting for a result - are on the page at all.
          await page.getByTestId('slip-dock-toggle').click();
          await expect(page.getByTestId('slip-leg')).toHaveCount(2);
          await expect(page.getByText(say(language, 'selections.history.awaiting'), { exact: true })).toHaveCount(1);
        }
        for (const id of NEW_ELEMENTS) await expect(page.getByTestId(id), `${id} on ${route}`).toHaveCount(0);
      }
    });

    test('degraded: the banner keeps its old rules and nothing new appears', async ({ page }) => {
      await stubState(page, language, matchDataDegradedStatus());
      await page.goto(`/match/${OVERDUE}`);
      await page.waitForLoadState('networkidle');
      await expect(page.getByTestId('provider-status-banner')).toContainText(
        say(language, 'banner.providerCoolingDown', { provider: 'livescore', reason: LIVESCORE_REFUSAL }));
      await expect(page.getByTestId('result-delay-notice')).not.toHaveAttribute('data-blocked', 'true');
      for (const id of NEW_ELEMENTS) await expect(page.getByTestId(id), id).toHaveCount(0);
    });

    test('an older backend with no block gets exactly the banner it always had', async ({ page }) => {
      await stubState(page, language, refusingStatusWithoutBlock());
      await page.goto('/matches');
      await page.waitForLoadState('networkidle');
      const banner = page.getByTestId('provider-status-banner');
      await expect(banner).not.toHaveAttribute('data-state', 'blocked');
      await expect(banner.locator('p').first()).toHaveText(
        say(language, 'banner.providerCoolingDown', { provider: 'livescore', reason: LIVESCORE_REFUSAL }));
      for (const id of NEW_ELEMENTS) await expect(page.getByTestId(id), id).toHaveCount(0);
      // Its scheduler runs recover and settle, which "succeeded" minutes ago: the fixture line must
      // not borrow their time. Fixtures last fetched four days ago, and that is what it says.
      const days = say(language, 'time.ago', { duration: say(language, 'duration.days', { count: 4 }) });
      await expect(page.getByTestId('freshness-summary')).toHaveText(say(language, 'freshness.summary.refreshed', { age: days }));
    });
  });
}

/* ============================================================ at 360px, and what it costs */

test('at 360px in French the blocked banner fits, its disclosure included', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await stubState(page, 'fr', matchDataBlockedStatus());
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(await overflow(), 'the page scrolls sideways').toBe(0);

  const dismiss = page.getByTestId('provider-status-banner').getByRole('button', { name: fr['banner.dismiss'] });
  const box = await dismiss.boundingBox();
  expect(box, 'the dismiss button is on the page').not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(360);

  await page.getByTestId('match-data-detail').locator('summary').click();
  await expect(page.getByTestId('match-data-source').first()).toBeVisible();
  expect(await overflow(), 'the opened disclosure scrolls the page sideways').toBe(0);

  await page.goto('/matches');
  await page.waitForLoadState('networkidle');
  expect(await overflow(), 'the day list scrolls sideways while blocked').toBe(0);
});

test('nothing in the blocked state asks a provider for anything', async ({ page }) => {
  await signIn(page);
  const traffic = await stubState(page, 'fr', matchDataBlockedStatus(), { suggestions: NO_FIXTURES });
  for (const route of ['/', '/matches', `/match/${UPCOMING}`, `/match/${OVERDUE}`, '/selections', '/selections/suggestions']) {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
  }
  expect(traffic.refreshing, 'no request may carry refresh=true').toEqual([]);
  expect(traffic.dayReads.length, 'the day was read at least once').toBeGreaterThan(0);
  expect([...new Set(traffic.dayReads)], 'every day read is answered from stored rows').toEqual(['false']);
});
