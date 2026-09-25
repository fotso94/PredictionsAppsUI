import { test, expect, Page, Route, Request } from '@playwright/test';
import { ApiMatch, Json, dayPayload, fixtureAt, matchDetail, stubBackend } from '../support/api-stub';
import { signIn } from '../support/auth';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';

/**
 * MOCKED: the multi-market panel, the selection dock and the suggested combinations, against a
 * stubbed backend. No provider, no database, no request spent. The payloads are the shapes
 * backend/app/services/markets.py, slips.py and suggestions.py serve, hand-built from the genuine
 * Bulgaria v Luxembourg forecast (tests/fixtures in the backend) so the numbers on screen are the
 * provider's real ones.
 *
 * What is locked down here:
 *   * every served market renders with its published probability, source and settlement rule;
 *     an unpublished market says so and is not selectable; a calculated one says its formula;
 *   * one selection per fixture: a second selection on the same fixture asks before replacing;
 *   * signed out, a draft lives in this browser and survives a reload; signing in hands it over;
 *   * a fixture that crosses kickoff while the draft is open is flagged, not removed;
 *   * the copied slip carries no booking code, no invented price, and the disclaimer;
 *   * suggestions explain each leg, say when fewer legs qualify, and never call a leg safe;
 *   * the history page shows won / lost / void / unresolved with the backend's rule;
 *   * nothing on these pages asks the backend to refresh from a provider;
 *   * all of it in French as well as English, at every width the suite runs.
 */

type Language = 'en' | 'fr';

const catalogue = (language: Language) => (language === 'fr' ? fr : en) as Record<keyof typeof en, string>;
const say = (language: Language, key: keyof typeof en, params: Record<string, string | number> = {}): string =>
  renderMessage(compileMessage(catalogue(language)[key]), language, params);

/* ------------------------------------------------------------------------------ the clock */

const START = new Date('2026-09-25T12:00:00Z');
const HOUR = 60 * 60 * 1000;

async function fixClock(page: Page, at: Date = START): Promise<void> {
  await page.clock.install({ time: at });
}

/* ------------------------------------------------------------------------------ fixtures */

const KICKOFF = new Date(START.getTime() + 26 * HOUR).toISOString();
const KICKOFF_SOON = new Date(START.getTime() + 2 * 60 * 1000).toISOString();

const bulgaria = (): ApiMatch => {
  const match = fixtureAt(KICKOFF, 'Bulgaria', 'Luxembourg', 'bulgaria-luxembourg');
  (match.competition as Json).name = 'UEFA Nations League';
  return match;
};
const armenia = (): ApiMatch => {
  const match = fixtureAt(KICKOFF, 'Armenia', 'Latvia', 'armenia-latvia');
  (match.competition as Json).name = 'UEFA Nations League';
  return match;
};
const soon = (): ApiMatch => {
  const match = fixtureAt(KICKOFF_SOON, 'Georgia', 'N.Ireland', 'georgia-ni');
  (match.competition as Json).name = 'UEFA Nations League';
  return match;
};

const REGULATION = { capable: true, basis: 'regulation_time', rule: 'Settles on the regulation-time score (90 minutes plus stoppage). Extra time and penalties settle nothing; a fixture never played to a result is void.' };
const HALF_TIME = { capable: true, basis: 'half_time', rule: 'Settles on the stored half-time score. Left unresolved when no half-time score is stored for the fixture; nothing is inferred from the final score.' };
const EVENT_ORDER = { capable: false, basis: 'event_order', rule: 'Needs the order in which the goals were scored, which no configured source supplies.', reason: 'no configured result source records the order of goals' };

const sel = (market_id: string, outcome: string, probability: number | null, extra: Json = {}): Json => ({
  selection_id: `${market_id}:${outcome}${extra.line !== undefined && extra.line !== null ? `@${extra.line}` : ''}`,
  market_id, outcome, line: null, period: 'regulation', probability, probability_source: 'provider', calculation: null,
  available: probability !== null, unavailable_reason: probability === null ? 'not published by the provider' : null,
  warnings: [], settlement: REGULATION, odds: null, ...extra,
});

/** The Bulgaria v Luxembourg envelope, numbers as the provider published them on 2026-09-24. */
function envelope(matchId: string, over: Json = {}): Json {
  const odds = (value: number) => ({ value, format: 'decimal', source: 'provider_snapshot', provider: 'gameforecast', captured_at: '2026-09-24T00:00:00+00:00' });
  const calc = (formula: string, inputs: Json) => ({ formula, inputs, source_market: 'match_result', note: 'calculated from provider probabilities' });
  const market = (market_id: string, group: string, selections: Json[], extra: Json = {}): Json => ({
    market_id, group, period: 'regulation', line: null, available: selections.some(s => s.available), unavailable_reason: null,
    warnings: [], settlement: REGULATION, selections, ...extra,
  });
  return {
    match_id: matchId, provider: 'gameforecast', normalisation_version: 'markets.v1', built_at: START.toISOString(),
    forecast: { record_id: 'rec-1', snapshot_id: '163bf671-649d-47a8-8d7d-aa15295308cf', captured_before_kickoff: true,
      retrieved_at: '2026-09-25T00:01:15Z', model_run_at: '2026-09-24T00:00:00Z', provider_updated_at: '2026-09-21T00:00:00Z',
      state: 'available', state_reason: null },
    groups: [
      { group: 'outcome', markets: [
        market('match_result', 'outcome', [
          sel('match_result', 'home', 0.45, { odds: odds(2.3) }), sel('match_result', 'draw', 0.30, { odds: odds(3.0) }), sel('match_result', 'away', 0.25, { odds: odds(3.4) }),
        ]),
        market('double_chance', 'outcome', [
          sel('double_chance', '1x', 0.75, { probability_source: 'calculated', calculation: calc('P(1X) = P(home) + P(draw)', { home: 0.45, draw: 0.30 }) }),
          sel('double_chance', '12', 0.70, { probability_source: 'calculated', calculation: calc('P(12) = P(home) + P(away)', { home: 0.45, away: 0.25 }) }),
          sel('double_chance', 'x2', 0.55, { probability_source: 'calculated', calculation: calc('P(X2) = P(draw) + P(away)', { draw: 0.30, away: 0.25 }) }),
        ]),
      ] },
      { group: 'goals', markets: [
        market('total_goals', 'goals', [sel('total_goals', 'over', 0.45, { line: 2.5 }), sel('total_goals', 'under', 0.55, { line: 2.5 })], { line: 2.5 }),
        market('both_teams_score', 'goals', [sel('both_teams_score', 'yes', 0.45), sel('both_teams_score', 'no', 0.55)]),
      ] },
      { group: 'first_half', markets: [
        market('first_half_result', 'first_half', [
          sel('first_half_result', 'home', 0.30, { period: 'first_half', settlement: HALF_TIME }),
          sel('first_half_result', 'draw', 0.50, { period: 'first_half', settlement: HALF_TIME }),
          sel('first_half_result', 'away', 0.20, { period: 'first_half', settlement: HALF_TIME }),
        ], { period: 'first_half', settlement: HALF_TIME }),
      ] },
      { group: 'team', markets: [
        market('home_team_goals', 'team', [sel('home_team_goals', 'over', null, { line: 1.5 }), sel('home_team_goals', 'under', null, { line: 1.5 })],
          { line: 1.5, available: false, unavailable_reason: 'not published by the provider' }),
        market('team_to_score_first', 'team', [
          sel('team_to_score_first', 'home', 0.55, { settlement: EVENT_ORDER }), sel('team_to_score_first', 'away', 0.35, { settlement: EVENT_ORDER }),
          sel('team_to_score_first', 'neither', 0.10, { settlement: EVENT_ORDER }),
        ], { settlement: EVENT_ORDER }),
      ] },
      { group: 'exact_score', markets: [
        market('exact_score', 'exact_score', [sel('exact_score', '1-0', 0.20), sel('exact_score', '1-1', 0.15)], { remainder: 0.01 }),
      ] },
    ],
    recommended_bets: [
      { rank: '1', raw: 'matchResult.homeWinProbability', selection_id: 'match_result:home', resolved: true, reason: null },
      { rank: '2', raw: 'awayWinProbability', selection_id: null, resolved: false, reason: 'no market prefix; ambiguous between markets with the same outcome names' },
    ],
    provider_odds: { market_id: 'match_result', source: 'provider_snapshot', provider: 'gameforecast', bookmaker: null, captured_at: '2026-09-24T00:00:00+00:00', note: 'decimal prices carried in the provider payload; the bookmaker is not named' },
    anomalies: [], reason: null, ...over,
  };
}

/* ------------------------------------------------------------------------------ a slip world */

interface StoredLeg {
  id: string; match: ApiMatch; selection: Json; odds: number | null; state: string; settlement: Json | null;
}
interface StoredSlip {
  id: string; name: string | null; status: string; note: string | null; currency: string | null; stake: string | null;
  price: number | null; recorded_at: string | null; recorded_reference: string | null; legs: StoredLeg[];
}

class SlipWorld {
  slips: StoredSlip[] = [];

  refreshRequests = 0;

  slipWrites = 0;

  private seq = 0;

  next(prefix: string): string { this.seq += 1; return `${prefix}-${this.seq}`; }

  serialize(slip: StoredSlip, now: Date): Json {
    const states = slip.legs.map(l => l.state);
    const state = states.includes('lost') ? 'lost'
      : states.length > 0 && states.every(s => s === 'void') ? 'void'
        : states.includes('pending') ? 'pending'
          : states.includes('unresolved') ? 'unresolved'
            : states.length > 0 && states.filter(s => s !== 'void').every(s => s === 'won') ? 'won' : 'pending';
    const priced = slip.legs.filter(l => l.state !== 'void');
    const price = slip.price ?? (priced.length > 0 && priced.every(l => l.odds) ? Math.round(priced.reduce((p, l) => p * (l.odds as number), 1) * 10000) / 10000 : null);
    const missing = priced.filter(l => !l.odds).length;
    const counts: Json = { legs: slip.legs.length };
    for (const s of ['pending', 'won', 'lost', 'void', 'unresolved']) counts[s] = states.filter(v => v === s).length;
    return {
      id: slip.id, name: slip.name, status: slip.status, note: slip.note, currency: slip.currency, stake: slip.stake,
      price, price_source: price !== null ? (slip.price !== null ? 'user' : 'user') : null, price_missing_legs: missing,
      price_note: price !== null ? "the product of the legs' prices; a void leg drops out of it" : 'no combined price: at least one selection has no price for exactly that selection',
      potential: price !== null && slip.stake && slip.currency
        ? { currency: slip.currency, stake: slip.stake, gross_return: (Number(slip.stake) * price).toFixed(slip.currency === 'XAF' ? 0 : 2), net_profit: (Number(slip.stake) * price - Number(slip.stake)).toFixed(slip.currency === 'XAF' ? 0 : 2), rounding: "half-up to the currency's minor unit", note: 'a quoted figure from the price given; not money held or promised by this application' }
        : null,
      recorded_at: slip.recorded_at, recorded_reference: slip.recorded_reference,
      recorded_note: slip.status === 'recorded' ? "the reader's own statement that this was placed elsewhere; nothing here is confirmed by any bookmaker" : null,
      state, settled_at: null, counts, created_at: START.toISOString(), updated_at: now.toISOString(),
      legs: slip.legs.map((leg, position) => ({
        id: leg.id, position,
        match: { id: leg.match.id, home: leg.match.home, away: leg.match.away, competition: leg.match.competition, kickoff_utc: leg.match.kickoff_utc, status: leg.match.status },
        selection: { selection_id: leg.selection.selection_id, market_id: leg.selection.market_id, outcome: leg.selection.outcome, line: leg.selection.line, period: leg.selection.period },
        probability: leg.selection.probability, probability_source: leg.selection.probability_source, calculation: leg.selection.calculation,
        provider: 'gameforecast', snapshot_id: '163bf671-649d-47a8-8d7d-aa15295308cf', model_run_at: '2026-09-24T00:00:00Z', forecast_fetched_at: '2026-09-25T00:01:15Z',
        normalisation_version: 'markets.v1',
        odds: leg.odds ? { value: leg.odds, format: 'decimal', source: 'user', captured_at: now.toISOString() } : null,
        kickoff_utc: leg.match.kickoff_utc, started: Date.parse(leg.match.kickoff_utc as string) <= now.getTime(),
        current: { probability: leg.selection.probability, available: true, forecast_changed: false, state: 'available' },
        state: leg.state, settled_at: null, settlement: leg.settlement, settlement_capability: leg.selection.settlement,
      })),
    };
  }
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

/** The markets, suggestions and slips endpoints, on top of stubBackend(). */
async function stubSelections(page: Page, world: SlipWorld, options: {
  envelopes: Record<string, Json>; matches: ApiMatch[]; suggestions?: Json; clock?: () => Date;
}): Promise<void> {
  const now = () => options.clock?.() ?? START;
  await stubBackend(page, {
    day: (date) => dayPayload(date, options.matches),
    matchById: (id) => options.matches.find(m => m.id === id) ?? matchDetail(id),
  });
  // Registered AFTER stubBackend on purpose: Playwright tries the most recently registered route
  // first, and stubBackend answers every path it does not model with an empty object.
  await page.route('**/api/v1/**', async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, '');
    if (url.searchParams.get('refresh') === 'true') world.refreshRequests += 1;

    const markets = path.match(/^\/matches\/([^/]+)\/markets$/);
    if (markets) {
      const found = options.envelopes[markets[1]];
      return found ? json(route, found) : json(route, { detail: 'Match not found' }, 404);
    }
    if (path === '/suggestions/capabilities') {
      return json(route, { normalisation_version: 'markets.v1', families: [
        { family: 'corners_cards_shots', markets: [], status: 'unavailable', provider: null, payload_field: null, settlement: 'would need corner counts', reason: 'no configured prediction source publishes them' },
      ] });
    }
    if (path === '/suggestions') {
      return json(route, options.suggestions ?? { generated_at: now().toISOString(), rules: {}, pool: { fixtures_in_window: 0, qualifying: 0, excluded: {} }, combinations: [], shortfall: 'no fixture in the window has a selection at or above the requested probability' });
    }
    if (path.startsWith('/me/slips')) {
      if (request.method() !== 'GET') world.slipWrites += 1;
      const body = request.postDataJSON?.() as Json | null;
      const parts = path.split('/').filter(Boolean); // me, slips, id?, legs?, legId?
      const slip = parts[2] ? world.slips.find(s => s.id === parts[2]) : undefined;
      const findMatch = (id: string) => options.matches.find(m => m.id === id);
      const addLeg = (target: StoredSlip, input: Json): Json | null => {
        const match = findMatch(input.match_id as string);
        if (!match) return { status: 404, detail: { message: 'match not found', code: 'match_not_found' } };
        if (target.status === 'recorded') return { status: 409, detail: { message: 'recorded', code: 'recorded_immutable' } };
        if (target.legs.some(l => l.match.id === match.id)) return { status: 409, detail: { message: 'one selection per match', code: 'one_per_match' } };
        if (Date.parse(match.kickoff_utc as string) <= now().getTime()) return { status: 409, detail: { message: 'that fixture has already kicked off; prematch selections close at kickoff', code: 'kickoff_passed' } };
        const env = options.envelopes[match.id];
        const selection = env ? (env.groups as Json[]).flatMap(g => g.markets as Json[]).flatMap(m => m.selections as Json[]).find(s => s.selection_id === input.selection_id) : undefined;
        if (!selection) return { status: 422, detail: { message: 'no such selection for this fixture', code: 'selection_unknown' } };
        if (!selection.available) return { status: 422, detail: { message: `that selection is not available: ${selection.unavailable_reason}`, code: 'selection_unavailable' } };
        target.legs.push({ id: world.next('leg'), match, selection, odds: (input.odds as number | null) ?? ((selection.odds as Json | null)?.value as number | undefined) ?? null, state: 'pending', settlement: null });
        return null;
      };
      if (path === '/me/slips' && request.method() === 'GET') {
        return json(route, { slips: world.slips.map(s => world.serialize(s, now())) });
      }
      if (path === '/me/slips' && request.method() === 'POST') {
        const created: StoredSlip = { id: world.next('slip'), name: (body?.name as string | null) ?? null, status: 'draft', note: null, currency: null, stake: null, price: null, recorded_at: null, recorded_reference: null, legs: [] };
        for (const input of (body?.legs as Json[] | undefined) ?? []) {
          const refused = addLeg(created, input);
          if (refused) return json(route, { detail: refused.detail }, refused.status as number);
        }
        world.slips.unshift(created);
        return json(route, world.serialize(created, now()), 201);
      }
      if (!slip) return json(route, { detail: { message: 'slip not found', code: 'not_found' } }, 404);
      if (parts.length === 3 && request.method() === 'GET') return json(route, world.serialize(slip, now()));
      if (parts.length === 3 && request.method() === 'PATCH') {
        if (slip.status === 'recorded' && (body?.status || body?.stake || body?.currency)) return json(route, { detail: { message: 'recorded', code: 'recorded_immutable' } }, 409);
        if ('name' in (body ?? {})) slip.name = (body?.name as string | null) ?? null;
        if (body?.status) { if (body.status === 'saved' && !slip.name) return json(route, { detail: { message: 'a saved combination needs a name', code: 'name_required' } }, 422); slip.status = body.status as string; }
        if ('stake' in (body ?? {})) { slip.stake = (body?.stake as string) || null; slip.currency = slip.stake ? (body?.currency as string) ?? slip.currency : null; }
        return json(route, world.serialize(slip, now()));
      }
      if (parts.length === 3 && request.method() === 'DELETE') {
        if (slip.status === 'recorded') return json(route, { detail: { message: 'recorded', code: 'recorded_immutable' } }, 409);
        world.slips = world.slips.filter(s => s.id !== slip.id);
        return route.fulfill({ status: 204, body: '' });
      }
      if (parts[3] === 'legs' && parts.length === 4 && request.method() === 'POST') {
        const refused = addLeg(slip, body ?? {});
        if (refused) return json(route, { detail: refused.detail }, refused.status as number);
        return json(route, world.serialize(slip, now()), 201);
      }
      if (parts[3] === 'legs' && parts.length === 5) {
        const leg = slip.legs.find(l => l.id === parts[4]);
        if (!leg) return json(route, { detail: { message: 'leg not found', code: 'leg_not_found' } }, 404);
        if (slip.status === 'recorded') return json(route, { detail: { message: 'recorded', code: 'recorded_immutable' } }, 409);
        if (request.method() === 'DELETE') slip.legs = slip.legs.filter(l => l.id !== leg.id);
        if (request.method() === 'PATCH') leg.odds = (body?.odds as number | null) ?? null;
        return json(route, world.serialize(slip, now()));
      }
      if (parts[3] === 'record') {
        if (slip.status === 'recorded') return json(route, { detail: { message: 'recorded', code: 'recorded_immutable' } }, 409);
        if (slip.legs.length === 0) return json(route, { detail: { message: 'nothing to record', code: 'no_legs' } }, 409);
        slip.status = 'recorded'; slip.recorded_at = now().toISOString(); slip.recorded_reference = (body?.reference as string | null) ?? null;
        if (body?.price) slip.price = body.price as number;
        if (body?.stake) { slip.stake = body.stake as string; slip.currency = (body.currency as string) ?? slip.currency; }
        return json(route, world.serialize(slip, now()));
      }
      if (parts[3] === 'duplicate') {
        const copy: StoredSlip = { ...slip, id: world.next('slip'), status: 'draft', recorded_at: null, recorded_reference: null, price: null, legs: slip.legs.map(l => ({ ...l, id: world.next('leg'), state: 'pending', settlement: null })) };
        world.slips.unshift(copy);
        return json(route, world.serialize(copy, now()), 201);
      }
      return json(route, {}, 404);
    }
    return route.fallback();
  });
}

/* ------------------------------------------------------------------------------ helpers */

const selectionRow = (page: Page, id: string) => page.locator(`[data-testid="market-selection"][data-selection-id="${id}"]`);

const FORBIDDEN = /\bsafe\b|guaranteed|sure win|booking code|sûr|garanti/i;

/** "45%" in English, "45 %" (narrow no-break space) in French: the app's Intl output, matched either way. */
const pct = (value: string): RegExp => new RegExp(`(^|\\D)${value}\\s?%`);

/* =================================================================================== tests */

for (const language of ['en', 'fr'] as const) {
  test.describe(`[${language}] mocked: markets and the slip`, () => {
    test.use({ locale: language === 'fr' ? 'fr-FR' : 'en-GB' });

    test.beforeEach(async ({ page }) => {
      await page.addInitScript((lang: string) => {
        try { localStorage.setItem('sp.language.v1', lang); } catch { /* ignore */ }
      }, language);
    });

    test('every served market renders with its number, source and rule; nothing unpublished is selectable', async ({ page }) => {
      const world = new SlipWorld();
      const match = bulgaria();
      await fixClock(page);
      await stubSelections(page, world, { envelopes: { [match.id]: envelope(match.id) }, matches: [match, armenia()] });
      await page.goto(`/match/${match.id}`);

      const panel = page.getByTestId('markets-panel');
      await expect(panel).toBeVisible();
      await expect(panel.getByTestId('market-group')).toHaveCount(5);
      await expect(panel.getByTestId('markets-provenance')).toContainText('gameforecast');

      // The provider's own 1X2, with its dated price on each outcome and nowhere else.
      await expect(selectionRow(page, 'match_result:home').getByTestId('selection-probability')).toHaveText(pct('45'));
      await expect(selectionRow(page, 'match_result:home').getByTestId('selection-price')).toContainText('2.30');
      await expect(selectionRow(page, 'double_chance:1x').getByTestId('selection-price')).toHaveCount(0);
      // A calculated market says its formula.
      await expect(selectionRow(page, 'double_chance:1x')).toContainText('P(1X) = P(home) + P(draw)');
      await expect(selectionRow(page, 'double_chance:1x').getByTestId('selection-probability')).toHaveText(pct('75'));
      // The words are the reader's: names for teams, catalogue words for everything else.
      await expect(selectionRow(page, 'double_chance:1x')).toContainText(say(language, 'selections.outcome.orDraw', { team: 'Bulgaria' }));
      await expect(selectionRow(page, 'total_goals:under@2.5')).toContainText(say(language, 'selections.outcome.under', { line: '2.5' }));
      // A market the provider did not publish is said so, once, and offers no button.
      const missing = panel.locator('[data-testid="market-block"][data-market-id="home_team_goals"]');
      await expect(missing.getByTestId('market-unavailable')).toContainText('not published by the provider');
      await expect(missing.getByTestId('selection-add')).toHaveCount(0);
      // First-scorer is served but says it cannot be tracked.
      const first = panel.locator('[data-testid="market-block"][data-market-id="team_to_score_first"]');
      await expect(first).toContainText(say(language, 'selections.panel.notTracked', { reason: 'no configured result source records the order of goals' }));
      // The exact-score remainder is a line, not a selection.
      await expect(panel).toContainText(language === 'fr' ? 'Autres scores' : 'Other scorelines');
      await expect(selectionRow(page, 'exact_score:other')).toHaveCount(0);
      // Provider flags: the resolved one names its selection, the ambiguous one says why not.
      const flagged = panel.getByTestId('provider-recommended');
      await expect(flagged).toContainText(pct('45'));
      await expect(flagged).toContainText(say(language, 'selections.panel.recommendedUnresolved', { raw: 'awayWinProbability', reason: 'no market prefix; ambiguous between markets with the same outcome names' }));
      await expect(panel.getByTestId('markets-disclaimer')).toHaveText(say(language, 'selections.dock.disclaimer'));
      expect(await panel.innerText()).not.toMatch(FORBIDDEN);
      expect(world.refreshRequests, 'browsing markets never asks a provider to refresh').toBe(0);
    });

    test('signed out: one selection per fixture, a draft that survives a reload, and a copied slip that invents nothing', async ({ page }) => {
      const world = new SlipWorld();
      const first = bulgaria();
      const second = armenia();
      await fixClock(page);
      // The clipboard itself is not under test (and a mobile profile grants no permission for it):
      // capture what the page hands to it.
      await page.addInitScript(() => {
        Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (text: string) => { (window as unknown as { __copied?: string }).__copied = text; } }, configurable: true });
      });
      await stubSelections(page, world, { envelopes: { [first.id]: envelope(first.id), [second.id]: envelope(second.id) }, matches: [first, second] });
      await page.goto(`/match/${first.id}`);

      await selectionRow(page, 'match_result:home').getByTestId('selection-add').click();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('1');
      await expect(selectionRow(page, 'match_result:home').getByTestId('selection-on-slip')).toBeVisible();

      // A second selection on the same fixture asks before replacing.
      await selectionRow(page, 'total_goals:under@2.5').getByTestId('selection-add').click();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('1');
      await expect(selectionRow(page, 'total_goals:under@2.5').getByTestId('selection-on-slip')).toBeVisible();
      await expect(selectionRow(page, 'match_result:home').getByTestId('selection-on-slip')).toHaveCount(0);

      // Another fixture adds a second leg.
      await page.goto(`/match/${second.id}`);
      await selectionRow(page, 'both_teams_score:no').getByTestId('selection-add').click();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('2');

      // The draft lives in this browser: a reload keeps it, and no slip write reached the server.
      await page.reload();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('2');
      expect(world.slipWrites).toBe(0);

      await page.getByTestId('slip-dock-toggle').click();
      const dock = page.getByTestId('slip-dock');
      await expect(dock.getByTestId('slip-leg')).toHaveCount(2);
      await expect(dock.getByTestId('slip-dock-signed-out')).toHaveText(say(language, 'selections.dock.signedOut'));
      // No price on the BTTS leg, so no combined price is invented.
      await expect(dock.getByTestId('slip-combined-price-missing')).toBeVisible();
      await expect(dock.getByTestId('slip-combined-price')).toHaveCount(0);
      await expect(dock.getByTestId('slip-combined-probability')).toContainText(say(language, 'selections.dock.combinedProbabilityNote'));

      await dock.getByTestId('slip-copy').click();
      const copied = await page.evaluate(() => (window as unknown as { __copied?: string }).__copied ?? '');
      expect(copied).toContain('Bulgaria v Luxembourg');
      expect(copied).toContain('Armenia v Latvia');
      expect(copied).toContain(say(language, 'selections.copy.noCombinedPrice'));
      expect(copied).toContain(say(language, 'selections.copy.disclaimer'));
      expect(copied).not.toMatch(FORBIDDEN);
      expect(copied).not.toMatch(/\bcode\b/i);
      expect(await dock.innerText()).not.toMatch(FORBIDDEN);
    });

    test('signing in hands the browser draft to the account, and a refused leg is reported, not dropped silently', async ({ page }) => {
      const world = new SlipWorld();
      const first = bulgaria();
      const late = soon();
      let now = START;
      await fixClock(page);
      await stubSelections(page, world, { envelopes: { [first.id]: envelope(first.id), [late.id]: envelope(late.id) }, matches: [first, late], clock: () => now });
      await page.goto(`/match/${first.id}`);
      await selectionRow(page, 'match_result:home').getByTestId('selection-add').click();
      await page.goto(`/match/${late.id}`);
      await selectionRow(page, 'match_result:away').getByTestId('selection-add').click();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('2');

      // Kickoff passes for the second fixture before the reader signs in.
      now = new Date(START.getTime() + 5 * 60 * 1000);
      await signIn(page);
      await page.goto('/selections');
      await expect(page.getByTestId('slip-dock-count')).toHaveText('1');
      await page.getByTestId('slip-dock-toggle').click();
      await expect(page.getByTestId('slip-dock-handoff')).toContainText('kicked off');
      expect(world.slips).toHaveLength(1);
      expect(world.slips[0].legs.map(l => l.match.id)).toEqual([first.id]);
      // The dock now edits the account's slip: prices, a stake, a name.
      const dock = page.getByTestId('slip-dock');
      await dock.getByTestId('slip-leg-odds').fill('2.30');
      await dock.getByTestId('slip-leg-odds').press('Enter');
      await expect(dock.getByTestId('slip-combined-price')).toContainText('2.30');
      await dock.getByTestId('slip-currency').selectOption('XAF');
      await dock.getByTestId('slip-stake').fill('5050');
      await dock.getByTestId('slip-stake').blur();
      await expect(dock.getByTestId('slip-potential')).toContainText('11615');
      await dock.getByTestId('slip-name').fill('Weekend single');
      await dock.getByTestId('slip-save').click();
      await expect(dock.getByTestId('slip-dock-notice')).toHaveText(say(language, 'selections.dock.saved', { name: 'Weekend single' }));
      expect(world.slips[0].status).toBe('saved');
    });

    test('a draft left open crosses kickoff visibly, and recording makes the slip immutable', async ({ page }) => {
      const world = new SlipWorld();
      const first = bulgaria();
      const late = soon();
      await fixClock(page);
      await signIn(page);
      await stubSelections(page, world, { envelopes: { [first.id]: envelope(first.id), [late.id]: envelope(late.id) }, matches: [first, late] });
      await page.goto(`/match/${late.id}`);
      await selectionRow(page, 'match_result:home').getByTestId('selection-add').click();
      await page.getByTestId('slip-dock-toggle').click();
      const dock = page.getByTestId('slip-dock');
      await expect(dock.getByTestId('slip-leg-started')).toHaveCount(0);

      // Three minutes pass with the draft open: the leg is flagged, not removed.
      await page.clock.fastForward(3 * 60 * 1000);
      await expect(dock.getByTestId('slip-leg-started')).toHaveText(say(language, 'selections.dock.started'));
      await expect(dock.getByTestId('slip-leg')).toHaveCount(1);

      await dock.getByTestId('slip-leg-remove').click();
      await expect(dock.getByTestId('slip-dock-empty')).toBeVisible();
      await page.goto(`/match/${first.id}`);
      await selectionRow(page, 'match_result:home').getByTestId('selection-add').click();
      await page.getByTestId('slip-dock-toggle').click();
      await dock.getByTestId('slip-name').fill('Recorded one');
      await dock.getByTestId('slip-record-open').click();
      await expect(dock.getByTestId('slip-record-form')).toContainText(say(language, 'selections.dock.recordHint'));
      await dock.getByTestId('slip-record-reference').fill('ticket 42');
      await dock.getByTestId('slip-record-price').fill('2.25');
      await dock.getByTestId('slip-record-confirm').click();
      await expect(dock.getByTestId('slip-dock-notice')).toHaveText(say(language, 'selections.dock.recorded'));
      // The dock has moved on to a new slip; the recorded one is kept as it was on the history page.
      await expect(page.getByTestId('slip-dock-count')).toHaveText('0');
      await page.goto('/selections');
      const recorded = page.locator('[data-testid="history-slip"][data-status="recorded"]');
      await expect(recorded).toHaveCount(1);
      await expect(recorded).toContainText(say(language, 'selections.status.recorded'));
      await expect(recorded).toContainText('ticket 42');
      await expect(recorded.getByTestId('history-price')).toContainText('2.25');
      await expect(recorded.getByTestId('history-delete')).toHaveCount(0);
      await expect(recorded).toContainText('nothing here is confirmed by any bookmaker');
    });

    test('history shows what became of each leg, with the rule, and never guesses', async ({ page }) => {
      const world = new SlipWorld();
      const first = bulgaria();
      const second = armenia();
      world.slips.push({
        id: 'slip-settled', name: 'Settled', status: 'saved', note: null, currency: 'EUR', stake: '10.00', price: null, recorded_at: null, recorded_reference: null,
        legs: [
          { id: 'l1', match: first, selection: sel('match_result', 'away', 0.25), odds: 3.4, state: 'won', settlement: { state: 'won', rule: 'regulation-time result', basis: 'regulation_time', actual: '0-1' } },
          { id: 'l2', match: second, selection: sel('draw_no_bet', 'home', 0.6), odds: 1.5, state: 'void', settlement: { state: 'void', rule: 'a draw after 90 minutes voids draw-no-bet', basis: 'regulation_time', actual: '1-1' } },
        ],
      });
      world.slips.push({
        id: 'slip-open', name: 'Open', status: 'saved', note: null, currency: null, stake: null, price: null, recorded_at: null, recorded_reference: null,
        legs: [
          { id: 'l3', match: first, selection: sel('team_to_score_first', 'away', 0.35, { settlement: EVENT_ORDER }), odds: null, state: 'unresolved', settlement: { state: 'unresolved', rule: 'needs the order of goals', basis: 'event_order', reason: 'no configured result source records which team scored first; this selection is not tracked automatically' } },
          { id: 'l4', match: second, selection: sel('total_goals', 'over', 0.45, { line: 2.5 }), odds: null, state: 'pending', settlement: null },
        ],
      });
      await fixClock(page);
      await signIn(page);
      await stubSelections(page, world, { envelopes: {}, matches: [first, second] });
      await page.goto('/selections');

      const settled = page.locator('[data-testid="history-slip"]').filter({ has: page.getByRole('heading', { name: 'Settled', exact: true }) });
      await expect(settled).toHaveAttribute('data-state', 'won');
      await expect(settled.locator('[data-testid="history-leg"][data-state="won"]')).toContainText(say(language, 'selections.history.actual', { actual: '0-1' }));
      await expect(settled.locator('[data-testid="history-leg"][data-state="void"]')).toContainText('voids draw-no-bet');
      // The void leg's price dropped out: 3.40, not 5.10.
      await expect(settled.getByTestId('history-price')).toContainText('3.40');
      await expect(settled.getByTestId('history-price')).toContainText(say(language, 'selections.history.voidNote'));

      const open = page.locator('[data-testid="history-slip"]').filter({ has: page.getByRole('heading', { name: 'Open', exact: true }) });
      await expect(open).toHaveAttribute('data-state', 'pending');
      const unresolved = open.locator('[data-testid="history-leg"][data-state="unresolved"]');
      await expect(unresolved).toContainText(say(language, 'selections.history.unresolvedNote'));
      await expect(unresolved).toContainText('not tracked automatically');
      await expect(unresolved.getByTestId('history-leg-state')).toHaveText(say(language, 'selections.state.unresolved'));
      await expect(open.locator('[data-testid="history-leg"][data-state="pending"]').getByTestId('history-leg-state')).toHaveText(say(language, 'selections.state.pending'));

      await page.getByTestId('history-filter-recorded').click();
      await expect(page.getByTestId('history-empty')).toBeVisible();
      expect(world.refreshRequests).toBe(0);
    });

    test('suggestions explain every leg, admit a shortfall, and add to the slip', async ({ page }) => {
      const world = new SlipWorld();
      const first = bulgaria();
      const second = armenia();
      const leg = (match: ApiMatch, selection: Json, rank: number): Json => ({
        match: { id: match.id, home: match.home, away: match.away, competition: match.competition, kickoff_utc: match.kickoff_utc, status: 'scheduled' },
        selection,
        why: { probability: selection.probability, probability_source: 'provider', threshold: 0.6, ceiling: 0.95, rank,
          forecast: { provider: 'gameforecast', snapshot_id: 's', model_run_at: '2026-09-24T00:00:00Z', retrieved_at: '2026-09-25T00:01:15Z', state: 'available', age_hours: 36, captured_before_kickoff: true },
          warnings: [], settlement: REGULATION, provider_odds: selection.odds ?? null },
      });
      const suggestions = {
        generated_at: START.toISOString(),
        rules: { version: 'suggestions.v1', legs: 3, min_probability: 0.6, max_probability: 0.95, markets: ['match_result'], max_combinations: 3, include_stale: false, settleable_only: true, kickoff_from: null, kickoff_to: null, odds_min: null, odds_max: null, competition_ids: [], selection_rule: 'one selection per fixture', combined_probability: 'assuming independence', source: 'stored provider forecasts only' },
        pool: { fixtures_in_window: 5, qualifying: 2, excluded: { no_forecast: 2, stale: 1, kickoff_passed: 0, no_available_market: 0, no_settleable_market: 0, odds_filter: 0, above_ceiling: 0, below_threshold: 0 } },
        combinations: [{ index: 1, legs: [leg(first, sel('double_chance', '1x', 0.75), 1), leg(second, sel('total_goals', 'under', 0.65, { line: 2.5 }), 2)],
          combined_probability: { value: 0.4875, basis: 'the product of the legs\' published probabilities, assuming the matches are independent of each other; an approximation for orientation, not a calibrated prediction' }, combined_odds: null }],
        shortfall: 'only 2 fixtures qualify for 3 legs; the combination below is shorter than asked',
      };
      await fixClock(page);
      await stubSelections(page, world, { envelopes: { [first.id]: envelope(first.id), [second.id]: envelope(second.id) }, matches: [first, second], suggestions });
      await page.goto('/selections/suggestions');

      await expect(page.getByTestId('suggest-results')).toBeVisible();
      await expect(page.getByTestId('suggest-shortfall')).toContainText('only 2 fixtures qualify for 3 legs');
      await expect(page.getByTestId('suggest-generated')).toContainText(say(language, 'selections.suggest.excluded', { stale: 1, noForecast: 2, belowThreshold: 0, aboveCeiling: 0, oddsFilter: 0 }));
      const combination = page.getByTestId('suggested-combination');
      await expect(combination).toHaveCount(1);
      await expect(combination.getByTestId('suggested-leg')).toHaveCount(2);
      await expect(combination.getByTestId('suggested-combined')).toContainText(say(language, 'selections.dock.combinedProbabilityNote'));
      await expect(combination.getByTestId('suggested-combined')).toContainText(say(language, 'selections.suggest.noCombinedOdds'));
      await expect(combination.getByTestId('suggested-leg').first()).toContainText(say(language, 'selections.suggest.rank', { rank: 1 }));
      await expect(combination.getByTestId('suggested-leg').first()).toContainText(say(language, 'selections.suggest.ageHours', { count: 36 }));
      expect(await page.locator('main').innerText()).not.toMatch(FORBIDDEN);

      await combination.getByTestId('suggested-add-all').click();
      await expect(page.getByTestId('slip-dock-count')).toHaveText('2');
      await expect(combination.getByText(say(language, 'selections.action.added'))).toHaveCount(2);
      expect(world.refreshRequests, 'generating suggestions never asks a provider to refresh').toBe(0);
    });
  });
}

test('mocked: the page stays inside the viewport at every width and logs no error', async ({ page }) => {
  const world = new SlipWorld();
  const match = bulgaria();
  await fixClock(page);
  await stubSelections(page, world, { envelopes: { [match.id]: envelope(match.id) }, matches: [match] });
  const errors: string[] = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto(`/match/${match.id}`);
  await expect(page.getByTestId('markets-panel')).toBeVisible();
  await selectionRow(page, 'match_result:home').getByTestId('selection-add').click();
  await page.getByTestId('slip-dock-toggle').click();
  await expect(page.getByTestId('slip-dock')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, 'the page scrolls sideways at this width').toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});
