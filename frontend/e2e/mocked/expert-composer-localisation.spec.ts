import { expect, test, Locator, Page, Request, Route } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import { compileMessage, renderMessage } from '../../src/i18n/format';
// A namespace import, not named ones: run against a build without one of these helpers, a named
// import would fail the whole FILE at link time and hide what every other test here shows.
import * as percent from '../../src/components/expert/percent';
import { EMPTY_COMPOSER, validateComposer } from '../../src/components/expert/composer';
import {
  ApiMatch, Json, StubOptions, baseMatches, emptyDayPayload, fixtureAt, matchDetail, selectLocalDay, stubBackend,
  withCompactBrief, withKickoffPassedForecast, withStaleForecast, withoutForecast, withoutMarkets,
} from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';
import { LIVE_API_MESSAGE, fenceLiveApi } from '../support/live-stack';
import { frenchVocabulary, pageStringsIn, unaccountedWords, verbatimStrings, wordsOf } from '../support/vocabulary';

/**
 * THE COMPOSER IN FRENCH: PICKER, EDITOR, VALIDATION, PREVIEW AND EVIDENCE (QA findings 7 and 9).
 *
 * The composer's frame was translated and its children were not. A French expert in Douala read
 * « Rédiger un pronostic » above "Match result", "Your conviction in this call", "Enter a number,
 * for example 55." and a preview that printed 55.5% — and the picker labelled a stored forecast
 * that had gone out of date "No forecast held", which is false in any language. What this file
 * pins, at 1440px (mocked-desktop, Chromium), 390px (mocked-mobile, WebKit) and 360px
 * (mocked-mobile-360, Chromium):
 *
 *   - every state of the French composer — the picker, the editor, every optional market ticked,
 *     each validation message, the preview, a publish failure, the published confirmation and the
 *     edit form on My Predictions — carries no word the French catalogue, the injected fixtures
 *     or the locale cannot account for (the allow-list walk in ../support/vocabulary.ts), and
 *     nothing scrolls the document sideways;
 *   - the numbers a French expert types and reads are French: 55,5 typed is 0.555 sent, the total
 *     and the preview print 55,5 %, an edit reopens 55,5, and the English output is byte-for-byte
 *     what it was (conviction-clearing.spec.ts pins "99% total", "Add 1.", "101.01% total" and
 *     "Remove 1.01." on the English edit form, and this file pins the rest);
 *   - the kick-off is the chosen zone's — Africa/Douala, 00:30 on the next calendar day for a
 *     23:30Z fixture — in the picker row, the composer header, the evidence panel and the preview,
 *     never New York's 19:30 (the device zone, playwright.config.ts) and never an ISO date;
 *   - the picker's forecast badge says which of four things is true — current, stored but out of
 *     date, kept for reference after kick-off, or absent — in both languages, from the list
 *     payload alone, with the expert badge BESIDE it rather than instead of it;
 *   - the backend's own sentences stay as the backend wrote them, marked `lang="en"`, and are
 *     asserted exactly against the stub rather than waved through.
 *
 * Expected figures are formatted by the PAGE's `Intl` (Chromium and WebKit write French spaces
 * differently from Node and from each other), and expected sentences by src/i18n's own formatter.
 *
 * ABSENCE WINDOWS. "Nothing was sent" is checked over 1500 ms after the press that would have sent
 * it; the composer sends its request synchronously from the click handler, so a request that is
 * going to leave has left well inside that window.
 *
 * COST. Every /api/v1 route is stubbed. A guard (support/live-stack.ts) aborts, and fails the test
 * on, any request to the live API (:8000) that no stub answered, and no test here may ask for
 * `refresh=true`. The guard does not fence the frontend origin, which is the page under test on the
 * default configuration.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';
const DOUALA = 'Africa/Douala';
const NAIROBI = 'Africa/Nairobi';
/** The browser context's own zone (playwright.config.ts). Chosen by no test. */
const NEW_YORK = 'America/New_York';
const LOCALE: Record<Language, string> = { en: 'en-GB', fr: 'fr-FR' };

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const isoDay = (offsetDays: number): string => new Date(Date.now() + offsetDays * DAY_MS).toISOString().slice(0, 10);
const isoIn = (ms: number): string => new Date(Date.now() + ms).toISOString().replace(/\.\d{3}Z$/, 'Z');

/**
 * A kick-off three days out at 23:30Z: still prematch, so the composer is in its ordinary state,
 * and late enough that Douala (+01:00) files it under the NEXT calendar day while New York
 * (-04:00) keeps it on this one at 19:30. A page that ignored the chosen zone prints a different
 * date as well as a different clock.
 */
const UTC_DAY = isoDay(3);
const DOUALA_DAY = isoDay(4);
const KICKOFF_UTC = `${UTC_DAY}T23:30:00Z`;

const EXPERT_PREDICTION: Json = {
  home_win_prob: 0.5, draw_prob: 0.25, away_win_prob: 0.25, confidence_score: 0.8,
  btts_yes_prob: null, btts_no_prob: null, btts_confidence: null,
  total_goals_over_25_prob: null, total_goals_under_25_prob: null,
  total_goals_over_35_prob: null, total_goals_under_35_prob: null,
  total_goals_confidence: null, reasoning: null, source: 'EXPERT_MANUAL',
  priority_level: 1, published_at: isoIn(-DAY_MS),
};

/** The fixture the composer is opened on: current forecast, a compact brief, no exact score. */
const NEAR_MIDNIGHT = withCompactBrief(withoutMarkets(
  fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', 'fx-a1'), ['exact_score']));

/** The same Douala day, one fixture per forecast state the picker must tell apart. */
const DAY_POOL: ApiMatch[] = [
  NEAR_MIDNIGHT,
  withoutForecast(fixtureAt(`${DOUALA_DAY}T12:00:00Z`, 'Fovu Baham', 'Bamboutos', 'fx-b2')),
  withStaleForecast(fixtureAt(`${DOUALA_DAY}T13:00:00Z`, 'Canon Yaoundé', 'Colombe Sportive', 'fx-c3')),
  { ...withStaleForecast(fixtureAt(`${DOUALA_DAY}T14:00:00Z`, 'PWD Bamenda', 'Aigle Royal', 'fx-e5')), expert_prediction: EXPERT_PREDICTION },
];

/** The words the expert types into the reasoning box in the French journey: their own, not ours. */
const REASONING_FR = 'Les deux équipes jouent bien chez elles, la forme récente compte.';

let liveStackHits: string[] = [];

test.afterEach(() => {
  expect(liveStackHits, LIVE_API_MESSAGE).toEqual([]);
});

// --------------------------------------------------------------------------- helpers

/** One catalogue sentence, rendered the way src/i18n renders it. Throws for a missing key. */
function say(language: Language, key: string, params: Record<string, string | number> = {}): string {
  const catalogue = (language === 'en' ? en : fr) as unknown as Record<string, string>;
  const source = catalogue[key];
  if (typeof source !== 'string') throw new Error(`the ${language} catalogue has no key "${key}"`);
  return renderMessage(compileMessage(source), LOCALE[language], params);
}

const normalise = (value: string): string => value.replace(/\s+/g, ' ').trim();

/** A 0-100 percentage as the page's own Intl writes it, with up to `max` decimals and no grouping. */
const percentIn = (page: Page, language: Language, percent: number, max = 2): Promise<string> =>
  page.evaluate(([locale, value, digits]) => new Intl.NumberFormat(locale as string, {
    style: 'percent', minimumFractionDigits: 0, maximumFractionDigits: digits as number, useGrouping: false,
  }).format((value as number) / 100), [LOCALE[language], percent, max] as const);

/** Percentage points without a sign, as the page's Intl writes them: 1.01 / 1,01. */
const pointsIn = (page: Page, language: Language, points: number): Promise<string> =>
  page.evaluate(([locale, value]) => new Intl.NumberFormat(locale as string, {
    minimumFractionDigits: 0, maximumFractionDigits: 2, useGrouping: false,
  }).format(value as number), [LOCALE[language], points] as const);

const numberIn = (page: Page, language: Language, value: number): Promise<string> =>
  page.evaluate(([locale, v]) => new Intl.NumberFormat(locale as string).format(v as number), [LOCALE[language], value] as const);

const inZone = (page: Page, zone: string, language: Language, options: Intl.DateTimeFormatOptions, iso: string): Promise<string> =>
  page.evaluate(([z, l, o, at]) => new Intl.DateTimeFormat(l as string, {
    timeZone: z as string, ...(o as Intl.DateTimeFormatOptions),
  }).format(new Date(at as string)), [zone, LOCALE[language], options, iso] as const);

const CLOCK: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };
const STAMP: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
const DATE_LONG: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric' };

/** The invisible spaces `Intl` puts inside a time or a percentage, flattened for substring tests. */
const plainSpaces = (value: string): string => value.replace(/[\u202f\u00a0]/g, ' ');

const sidewaysOverflow = (page: Page): Promise<number> =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

interface World {
  created: Json[];
  updated: Array<{ id: string; body: Json }>;
  mine: Json[];
  requests: string[];
  /** When set, the create endpoint answers with this status and `{ detail }`. */
  failCreate?: { status: number; detail: string };
}

/** One of the expert's own predictions, on the 0-1 scale the API serves. */
function minePrediction(over: Partial<Json> = {}): Json {
  return {
    id: 'pred-1',
    match_id: NEAR_MIDNIGHT.id,
    source: 'EXPERT_MANUAL',
    priority_level: 1,
    home_win_prob: 0.555,
    draw_prob: 0.245,
    away_win_prob: 0.2,
    confidence_score: 0.7,
    btts_yes_prob: 0.45,
    btts_no_prob: 0.55,
    btts_confidence: null,
    total_goals_over_25_prob: null,
    total_goals_under_25_prob: null,
    total_goals_over_35_prob: null,
    total_goals_under_35_prob: null,
    total_goals_confidence: null,
    reasoning: REASONING_FR,
    key_factors: null,
    status: 'PUBLISHED',
    created_by: 'qa-expert',
    created_at: isoIn(-DAY_MS),
    published_at: isoIn(-DAY_MS),
    superseded_by: null,
    match_details: {
      home_team_name: 'Coton Sport',
      away_team_name: 'Union Douala',
      home_team_logo: null,
      away_team_logo: null,
      league_name: 'Elite One',
      match_date: KICKOFF_UTC,
      external_match_id: null,
    },
    user_details: { username: 'qa-expert', first_name: null, last_name: null },
    ...over,
  };
}

/**
 * Seed the reader's choices before boot, fence off the live API, stub every route, sign in.
 *
 * Every stub is in place BEFORE the sign-in, so nothing the signed-in page asks for can find its
 * route still unstubbed (the order expert-localisation.spec.ts settled on for the same reason).
 */
async function openAsExpert(
  page: Page,
  options: {
    language: Language;
    zone?: string;
    day?: StubOptions['day'];
    fixtures?: ApiMatch[];
    mine?: Json[];
    failCreate?: World['failCreate'];
  },
): Promise<World> {
  const world: World = { created: [], updated: [], mine: options.mine ?? [], requests: [], failCreate: options.failCreate };
  liveStackHits = [];
  await page.addInitScript(
    ([languageKey, zoneKey, language, zone]) => {
      window.localStorage.setItem(languageKey, language);
      window.localStorage.setItem(zoneKey, zone);
    },
    [LANGUAGE_KEY, ZONE_KEY, options.language, options.zone ?? DOUALA] as const,
  );
  await fenceLiveApi(page, liveStackHits);
  page.on('request', request => { if (request.url().includes('/api/v1/')) world.requests.push(request.url()); });

  const fixtures = options.fixtures ?? DAY_POOL;
  await stubBackend(page, {
    day: options.day ?? ((iso, params) => selectLocalDay(fixtures, iso, params)),
    matchById: id => fixtures.find(match => match.id === id) ?? null,
  });
  await page.route('**/api/v1/expert/**', async (route: Route, request: Request) => {
    const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
      route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');
    if (path === '/analytics/performance') {
      return json({
        expert_id: 'qa-expert', expert_name: 'QA Expert', total_predictions: world.mine.length,
        published_predictions: world.mine.length, pending_predictions: 0, archived_predictions: 0,
        not_published_predictions: 0, accuracy_rate: null, average_confidence: null,
        predictions_by_league: {}, recent_predictions: [], performance_trend: [],
      });
    }
    if (path === '/predictions/my-predictions') {
      return json(world.mine, 200, { 'X-Total-Count': String(world.mine.length), 'Access-Control-Expose-Headers': 'X-Total-Count' });
    }
    if (path === '/predictions/review-queue') return json([]);
    if (path === '/predictions/manual' && request.method() === 'POST') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      world.created.push(body);
      if (world.failCreate) return json({ detail: world.failCreate.detail }, world.failCreate.status);
      return json({ ...minePrediction(), ...body, id: 'pred-new' });
    }
    const editing = /^\/predictions\/([^/]+)$/.exec(path);
    if (editing && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() || '{}') as Json;
      world.updated.push({ id: editing[1], body });
      const row = world.mine.find(entry => entry.id === editing[1]) ?? minePrediction();
      return json({ ...row, ...body });
    }
    return json({});
  });
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  return world;
}

/** The composer picker, moved to the Douala day the near-midnight fixture belongs to. */
async function openComposerPicker(page: Page): Promise<void> {
  await page.goto('/expert/predictions/create');
  await expect(page.locator('#picker-date')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.locator('#picker-date').fill(DOUALA_DAY);
  await expect(page.locator('li').filter({ hasText: 'Coton Sport' })).toHaveCount(1);
  await page.waitForLoadState('networkidle');
}

/** Open the composer straight on the near-midnight fixture. */
async function openComposer(page: Page): Promise<void> {
  await page.goto(`/expert/predictions/create?matchId=${NEAR_MIDNIGHT.id}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
}

/** The vocabulary of the French journey: catalogue, fixtures (venues included) and the expert's words. */
function journeyVocabulary(extra: string[] = []): Set<string> {
  const allowed = frenchVocabulary([...DAY_POOL, ...baseMatches().slice(0, 1)], { withVenue: true });
  for (const words of [REASONING_FR, ...extra]) wordsOf(words, allowed);
  return allowed;
}

/** The allow-list walk over the routed page (`#main`: everything but the shared header and footer). */
async function expectAllAccountedFor(page: Page, allowed: Set<string>, state: string, selector = '#main'): Promise<void> {
  const strings = await pageStringsIn(page, selector, { skipVerbatim: true });
  expect(strings.length, `${state}: nothing was rendered to check`).toBeGreaterThan(0);
  expect(
    unaccountedWords(strings, allowed),
    `${state}: a word on the French composer is in no catalogue, no fixture and no locale`,
  ).toEqual([]);
  expect(await sidewaysOverflow(page), `${state}: the document scrolls sideways`).toBeLessThanOrEqual(0);
}

/** The running-total line under one market, found by its rule sentence. */
const totalLine = (page: Page, rule: string) => page.locator('p').filter({ hasText: rule }).first();

/** Nothing reached `list` within the window: the composer sends synchronously from the click. */
async function nothingSent(page: Page, list: unknown[], what: string): Promise<void> {
  await page.waitForTimeout(1500);
  expect(list, what).toHaveLength(0);
}

/* ============================================================ the numbers, with no page at all */

/**
 * THE ARITHMETIC IS UNCHANGED AND THE ENGLISH IS BYTE-FOR-BYTE, measured rather than claimed.
 *
 * The old display helpers were `toFixed` and `String`, English-only. The new ones are `Intl` with
 * the locale passed in. This sweeps every value the composer can actually produce — totals and
 * gaps are whole ten-thousandths of a unit, so exact hundredths of a percentage point — and holds
 * the English output to what the old code printed, character for character.
 */
test('the English figures the composer prints are exactly what they were, and the French ones are French', () => {
  const oldPoints = (points: number): string => {
    const text = points.toFixed(2);
    return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
  };
  const oldShown = (percent: number): string => {
    const rounded = Math.round(percent * 10) / 10;
    return `${Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)}%`;
  };
  const drift: string[] = [];
  for (let hundredths = 0; hundredths <= 30_000; hundredths += 1) {
    const points = hundredths / 100;
    if (percent.formatPercentPoints(points, 'en-GB') !== oldPoints(points)) drift.push(`points ${points}`);
    if (percent.formatPercentTotal(points, 'en-GB') !== `${oldPoints(points)}%`) drift.push(`total ${points}`);
  }
  for (let tenths = -50; tenths <= 2_000; tenths += 1) {
    const value = tenths / 10;
    if (percent.formatPercentShown(value, 'en-GB') !== oldShown(value)) drift.push(`shown ${value}`);
  }
  for (const count of [0, 1, 999, 1000, 1500, 2000, 2001, 12_345]) {
    if (percent.formatWholeNumber(count, 'en-GB') !== String(count)) drift.push(`whole ${count}`);
  }
  expect(drift, 'an English figure changed').toEqual([]);

  // French: a decimal comma, and the locale's own space before the sign.
  expect(percent.formatPercentPoints(1.01, 'fr-FR')).toBe('1,01');
  expect(percent.formatPercentTotal(101.01, 'fr-FR')).toMatch(/^101,01[\u00a0\u202f]%$/);
  expect(percent.formatPercentTotal(99, 'fr-FR')).toMatch(/^99[\u00a0\u202f]%$/);
  expect(percent.formatPercentShown(55.5, 'fr-FR')).toMatch(/^55,5[\u00a0\u202f]%$/);
  // A character count is never grouped, in either language: "2000", not "2,000" or « 2 000 ».
  expect(percent.formatWholeNumber(2000, 'fr-FR')).toBe('2000');

  // An edit reopens in the reader's decimal separator, and either separator reads back the same.
  expect(percent.unitToPercentInput(0.555, 'en-GB')).toBe('55.5');
  expect(percent.unitToPercentInput(0.555, 'fr-FR')).toBe('55,5');
  expect(percent.unitToPercentInput(0.2, 'fr-FR')).toBe('20');
  expect(percent.unitToPercentInput(null, 'fr-FR')).toBe('');
  expect(percent.parsePercent('55,5')).toBe(55.5);
  expect(percent.parsePercent('55.5')).toBe(55.5);
});

test('validation returns message keys and figures, not English sentences, and its arithmetic is unchanged', () => {
  const values = {
    ...EMPTY_COMPOSER,
    homeWin: '33', draw: '33', awayWin: '33', conviction: 'abc',
    bttsEnabled: true, bttsYes: '98.995', bttsNo: '2.005',
    over25Enabled: true, over25: '101', under25: '',
    reasoning: 'x'.repeat(2001),
  };
  const result = validateComposer(values, null);

  // The arithmetic: the same totals, gaps and verdicts as before.
  expect(result.outcome).toEqual({ percent: 99, balanced: false, gap: 1 });
  expect(result.btts).toEqual({ percent: 101.01, balanced: false, gap: -1.01 });
  expect(result.ready).toBe(false);

  // The messages: a key and its figures, rendered later in whatever language is on screen.
  expect(result.errors).toEqual({
    matchId: { key: 'expert.validation.chooseFixture' },
    outcomeTotal: { key: 'expert.editor.adjustAdd', params: { points: { kind: 'points', value: 1 } } },
    conviction: { key: 'expert.validation.notANumber', params: { example: { kind: 'whole', value: 55 } } },
    bttsTotal: { key: 'expert.editor.adjustRemove', params: { points: { kind: 'points', value: 1.01 } } },
    over25: {
      key: 'expert.validation.outOfRange',
      params: { min: { kind: 'whole', value: 0 }, max: { kind: 'whole', value: 100 } },
    },
    under25: { key: 'expert.validation.lineBlank' },
    reasoning: {
      key: 'expert.validation.reasoningTooLong',
      params: { max: { kind: 'whole', value: 2000 }, count: { kind: 'whole', value: 2001 } },
    },
  });

  // And the English those keys render is the English the editor always printed.
  const total = say('en', 'expert.editor.totalUnbalanced', {
    percent: '99%', rule: say('en', 'expert.editor.ruleOutcomes', { hundred: '100%' }),
  });
  expect(`${total} ${say('en', 'expert.editor.adjustAdd', { points: '1' })}`)
    .toBe('99% total — The three outcomes must total 100%. Add 1.');
  expect(say('en', 'expert.validation.notANumber', { example: '55' })).toBe('Enter a number, for example 55.');
  expect(say('en', 'expert.validation.outOfRange', { min: '0', max: '100' })).toBe('Enter a percentage between 0 and 100.');
  expect(say('en', 'expert.validation.reasoningTooLong', { max: '2000', count: '2001' }))
    .toBe('Shorten this to 2000 characters — it is 2001 now.');
});

/* ======================================================= the French journey, word by word */

test('the French composer, from picker to published, carries no English the catalogue cannot account for', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'fr' });
  const allowed = journeyVocabulary();

  // ---------------------------------------------------------------- the picker
  await openComposerPicker(page);
  await expect(page.locator('#main')).toContainText(fr['expert.compose.chooseFixture']);
  await expect(page.locator('#main')).toContainText(fr['expert.picker.dayLabel']);
  await expectAllAccountedFor(page, allowed, 'the composer picker');

  // ---------------------------------------------------------------- a fixture chosen
  const clock = await inZone(page, DOUALA, 'fr', CLOCK, KICKOFF_UTC);
  await page.getByRole('button', {
    name: say('fr', 'expert.picker.rowAction', {
      action: fr['expert.action.writePrediction'], home: 'Coton Sport', away: 'Union Douala',
      competition: 'Premier League', time: clock,
    }),
  }).click();
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#main')).toContainText(fr['expert.editor.matchResultIntro']);
  await expect(page.locator('#main')).toContainText(fr['expert.evidence.heading']);
  await expectAllAccountedFor(page, allowed, 'the editor and the evidence, on arrival');

  // ---------------------------------------------------------------- every optional market ticked
  await page.locator('#composer-btts-enabled').check();
  await page.locator('#composer-over25-enabled').check();
  await page.locator('#composer-over35-enabled').check();
  await expect(page.locator('#composer-totals-conviction')).toBeVisible();
  await expectAllAccountedFor(page, allowed, 'every optional market ticked');

  // ---------------------------------------------------------------- filled in, French decimals
  await page.locator('#composer-home').fill('55,5');
  await page.locator('#composer-draw').fill('24,5');
  await page.locator('#composer-away').fill('20');
  await page.locator('#composer-conviction').fill('70');
  await page.locator('#composer-btts-yes').fill('45');
  await page.locator('#composer-btts-no').fill('55');
  await page.locator('#composer-over25').fill('52,5');
  await page.locator('#composer-under25').fill('47,5');
  await page.locator('#composer-over35').fill('30');
  await page.locator('#composer-under35').fill('70');
  await page.locator('#composer-totals-conviction').fill('50');
  await page.locator('#composer-reasoning').fill(REASONING_FR);
  await expectAllAccountedFor(page, allowed, 'every field filled');

  // ---------------------------------------------------------------- the preview
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  await expect(page.getByLabel(fr['expert.preview.regionLabel'])).toBeVisible();
  await expectAllAccountedFor(page, allowed, 'the preview');

  // ---------------------------------------------------------------- published
  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  await expect.poll(() => world.created.length, { message: 'the publish was not sent' }).toBe(1);
  await expect(page.getByRole('heading', { name: fr['expert.published.title'] })).toBeVisible();
  await expectAllAccountedFor(page, allowed, 'the published confirmation');

  expect(world.requests.filter(url => /refresh=true/i.test(url)), 'a provider refresh was asked for').toEqual([]);
});

test('a French decimal comma is sent as the same probability, and read back with a comma', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'fr' });
  await openComposer(page);

  await page.locator('#composer-home').fill('55,5');
  await page.locator('#composer-draw').fill('24,5');
  await page.locator('#composer-away').fill('20');

  // The running total is French: the locale's percent, and « au total ».
  const hundred = await percentIn(page, 'fr', 100);
  const rule = say('fr', 'expert.editor.ruleOutcomes', { hundred });
  await expect(totalLine(page, rule)).toHaveCount(0); // a balanced total states its total, not the rule
  const balanced = say('fr', 'expert.editor.totalBalanced', { percent: hundred });
  await expect(page.locator('p').filter({ hasText: balanced }).first()).toBeVisible();

  // The preview prints what will be published, in French: 55,5 %, not 55.5%.
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  const preview = page.getByLabel(fr['expert.preview.regionLabel']);
  await expect(preview).toBeVisible();
  const home = await percentIn(page, 'fr', 55.5, 1);
  const draw = await percentIn(page, 'fr', 24.5, 1);
  await expect(preview).toContainText(home);
  await expect(preview).toContainText(draw);
  expect(normalise(await preview.innerText()), 'the preview printed an English decimal').not.toContain('55.5');

  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  await expect.poll(() => world.created.length, { message: 'the publish was not sent' }).toBe(1);
  const body = world.created[0] as Record<string, unknown>;
  expect(body.home_win_prob).toBe(0.555);
  expect(body.draw_prob).toBe(0.245);
  expect(body.away_win_prob).toBe(0.2);
  expect(body.match_id).toBe(NEAR_MIDNIGHT.id);
  // Nothing the expert did not tick is sent at all.
  expect('btts_yes_prob' in body).toBe(false);
  expect('confidence_score' in body).toBe(false);
});

/* ================================================================ the validation, in French */

test('the French composer refuses bad input in French, and sends nothing', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'fr' });
  await openComposer(page);
  // The textarea's text is the expert's own, and React mirrors it into the DOM as a text node.
  const allowed = journeyVocabulary(['x'.repeat(2001)]);

  const hundred = await percentIn(page, 'fr', 100);

  // 34 / 33 / 34 is 101: one point too many, said in French with the size of it.
  await page.locator('#composer-home').fill('34');
  await page.locator('#composer-draw').fill('33');
  await page.locator('#composer-away').fill('34');
  const outcomeRule = say('fr', 'expert.editor.ruleOutcomes', { hundred });
  const outcomeTotal = `${say('fr', 'expert.editor.totalUnbalanced', {
    percent: await percentIn(page, 'fr', 101), rule: outcomeRule,
  })} ${say('fr', 'expert.editor.adjustRemove', { points: await pointsIn(page, 'fr', 1) })}`;
  await expect(totalLine(page, outcomeRule)).toHaveText(outcomeTotal);
  expect(plainSpaces(outcomeTotal)).toContain('101 % au total');
  expect(outcomeTotal).toContain('Retirez 1.');

  // A word where a number belongs, and a number out of range.
  await page.locator('#composer-conviction').fill('abc');

  // Both teams to score, one side blank; a goal line with both sides blank; and a two-way pair
  // that is short, so it says « Ajoutez » with a decimal comma.
  await page.locator('#composer-btts-enabled').check();
  await page.locator('#composer-btts-yes').fill('45');
  await page.locator('#composer-over25-enabled').check();
  await page.locator('#composer-over25').fill('101');
  await page.locator('#composer-over35-enabled').check();
  await page.locator('#composer-over35').fill('40,5');
  await page.locator('#composer-under35').fill('50');
  const sidesRule = say('fr', 'expert.editor.ruleOverUnder', { hundred });
  await expect(page.locator('p').filter({ hasText: sidesRule }).last()).toHaveText(
    `${say('fr', 'expert.editor.totalUnbalanced', { percent: await percentIn(page, 'fr', 90.5), rule: sidesRule })} `
    + say('fr', 'expert.editor.adjustAdd', { points: await pointsIn(page, 'fr', 9.5) }),
  );

  // Reasoning one character over the limit.
  await page.locator('#composer-reasoning').fill('x'.repeat(2001));

  // Publishing an invalid form marks every problem and sends nothing.
  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  const example = await numberIn(page, 'fr', 55);
  await expect(page.locator('#composer-conviction-error'))
    .toHaveText(say('fr', 'expert.validation.notANumber', { example }));
  await expect(page.locator('#composer-over25-error'))
    .toHaveText(say('fr', 'expert.validation.outOfRange', { min: '0', max: '100' }));
  await expect(page.locator('#composer-under25-error')).toHaveText(fr['expert.validation.lineBlank']);
  await expect(page.locator('#composer-btts-no-error')).toHaveText(fr['expert.validation.marketBlank']);
  await expect(page.locator('#main')).toContainText(say('fr', 'expert.validation.reasoningTooLong', { max: '2000', count: '2001' }));
  await expect(page.locator('#main')).toContainText(fr['expert.compose.fixThenPreview']);
  await nothingSent(page, world.created, 'an invalid French form was sent');

  // A blank required outcome, in French.
  await page.locator('#composer-draw').fill('');
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  await expect(page.locator('#composer-draw-error')).toHaveText(fr['expert.validation.drawBlank']);
  await expect(page.getByLabel(fr['expert.preview.regionLabel'])).toContainText(fr['expert.preview.needsAttention']);

  await expectAllAccountedFor(page, allowed, 'every validation message on screen');
  await nothingSent(page, world.created, 'the preview sent something');
});

/**
 * THE MESSAGES FOLLOW A CHANGE OF LANGUAGE WITHOUT ANOTHER KEYSTROKE.
 *
 * The composer page memoises validation on the values alone. When validation produced English
 * sentences, a reader who switched to French with errors on screen kept the English until they
 * typed again — and a French sentence produced there would have stuck the same way in reverse.
 * Validation now returns keys, and the editor writes them at render time, so the switch itself
 * re-renders every message, total and label.
 */
test('switching to French with errors on screen re-renders them in French, untouched', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'en' });
  await openComposer(page);
  await page.locator('#composer-home').fill('33');
  await page.locator('#composer-draw').fill('33');
  await page.locator('#composer-away').fill('33');
  await page.locator('#composer-conviction').fill('abc');
  await page.getByRole('button', { name: en['expert.action.publish'], exact: true }).click();
  await expect(page.locator('#composer-conviction-error')).toHaveText(say('en', 'expert.validation.notANumber', { example: '55' }));
  await expect(totalLine(page, 'The three outcomes must total 100%.'))
    .toHaveText('99% total — The three outcomes must total 100%. Add 1.');

  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('language-choice-fr').first().click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');

  // Nothing typed since: the same problems, now said in French.
  await expect(page.locator('#composer-conviction-error'))
    .toHaveText(say('fr', 'expert.validation.notANumber', { example: await numberIn(page, 'fr', 55) }));
  const hundred = await percentIn(page, 'fr', 100);
  const rule = say('fr', 'expert.editor.ruleOutcomes', { hundred });
  await expect(totalLine(page, rule)).toHaveText(
    `${say('fr', 'expert.editor.totalUnbalanced', { percent: await percentIn(page, 'fr', 99), rule })} `
    + say('fr', 'expert.editor.adjustAdd', { points: await pointsIn(page, 'fr', 1) }),
  );
  await expect(page.locator('#main')).toContainText(fr['expert.editor.convictionLabel']);
  await expect(page.locator('#main')).not.toContainText('Your conviction in this call');
  expect(world.created, 'an invalid form was sent').toHaveLength(0);
});

test('a French publish the server refuses says so around the server\'s own words', async ({ page }) => {
  const detail = 'Simulated publish refusal';
  const world = await openAsExpert(page, { language: 'fr', failCreate: { status: 503, detail } });
  await openComposer(page);
  await page.locator('#composer-home').fill('55');
  await page.locator('#composer-draw').fill('25');
  await page.locator('#composer-away').fill('20');
  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  await expect.poll(() => world.created.length).toBe(1);
  await expect(page.locator('#main [role="alert"]').filter({ hasText: detail })).toHaveCount(1);
  await expectAllAccountedFor(page, journeyVocabulary([detail]), 'a refused publish');
});

/* ========================================================== the kick-off, in the chosen zone */

test('the kick-off is the Douala time and day in the picker, the header, the evidence and the preview', async ({ page }) => {
  await openAsExpert(page, { language: 'fr' });
  await openComposerPicker(page);

  const clock = await inZone(page, DOUALA, 'fr', CLOCK, KICKOFF_UTC);
  const deviceClock = await inZone(page, NEW_YORK, 'fr', CLOCK, KICKOFF_UTC);
  expect(clock, 'the two zones must disagree, or this proves nothing').not.toBe(deviceClock);
  const stamp = plainSpaces(await inZone(page, DOUALA, 'fr', STAMP, KICKOFF_UTC));
  const deviceStamp = plainSpaces(await inZone(page, NEW_YORK, 'fr', STAMP, KICKOFF_UTC));

  // The picker row and the day it is filed under.
  const row = page.locator('li').filter({ hasText: 'Coton Sport' });
  await expect(row.locator('time')).toHaveText(clock);
  expect(await row.innerText()).not.toContain(deviceClock);

  await row.getByRole('button').click();
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');

  // The header and the evidence panel.
  const header = plainSpaces(normalise(await page.locator('h1').locator('xpath=..').innerText()));
  expect(header, 'the composer header did not show the Douala kick-off').toContain(stamp);
  // Found by structure rather than by name: the evidence panel is the page's one <aside>.
  const evidence = page.locator('#main aside');
  const evidenceText = plainSpaces(normalise(await evidence.innerText()));
  expect(evidenceText, 'the evidence panel did not show the Douala kick-off').toContain(stamp);
  expect(evidenceText, 'the evidence panel printed an ISO date').not.toMatch(/\d{4}-\d{2}-\d{2}/);
  expect(evidenceText).not.toContain(deviceStamp);

  // The preview.
  await page.locator('#composer-home').fill('55');
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  // The preview is the one named <section> on the composer.
  const previewText = plainSpaces(normalise(await page.locator('#main section[aria-label]').innerText()));
  expect(previewText, 'the preview did not show the Douala kick-off').toContain(stamp);
  expect(previewText, 'the preview printed an ISO date').not.toMatch(/\d{4}-\d{2}-\d{2}/);
  expect(previewText).not.toContain(deviceStamp);
});

/*
 * Review finding #24. The composer header and the preview each put the kick-off LAST in one
 * `truncate`d line, so at 360 and 390 px the ellipsis fell before it — and the kick-off is the one
 * value on that line the expert reads off the page to know the fixture is still prematch. Only the
 * competition may give way now. Measured from the drawn text, not read from innerText, which still
 * holds every clipped character (the Douala test above passed on the clipped header).
 */
const LONG_COMPETITION = 'Ligue des champions de la CAF';

/**
 * Every way `stamp` is not drawn whole inside `scope`: no element holds it, or the text of the
 * element that does runs past the edge of an ancestor that hides its overflow (a `truncate` line, a
 * card). Empty when it is all on screen.
 */
async function hiddenKickoff(scope: Locator, stamp: string): Promise<string[]> {
  return scope.evaluate((root, wanted) => {
    const flat = (text: string) => text.replace(/[\u202f\u00a0]/g, ' ').replace(/\s+/g, ' ');
    const holds = (el: Element) => flat(el.textContent ?? '').includes(wanted);
    const all = [root, ...Array.from(root.querySelectorAll('*'))];
    const deepest = all.filter(el => holds(el) && !Array.from(el.children).some(holds));
    if (deepest.length === 0) return [`nothing here holds "${wanted}"`];
    const problems: string[] = [];
    for (const el of deepest) {
      const range = document.createRange();
      range.selectNodeContents(el);
      const text = range.getBoundingClientRect();
      for (let box: Element | null = el; box && box !== document.documentElement; box = box.parentElement) {
        if (getComputedStyle(box).overflowX === 'visible') continue;
        const edge = box.getBoundingClientRect();
        if (text.right > edge.right + 0.5 || text.left < edge.left - 0.5) {
          problems.push(`<${box.tagName.toLowerCase()} class="${box.getAttribute('class') ?? ''}"> hides ${Math.round(text.right - edge.right)}px of the text that holds the kick-off`);
        }
      }
    }
    return problems;
  }, stamp);
}

test('the kick-off is drawn whole in the composer header and in the preview, at this width', async ({ page }) => {
  const fixture = withCompactBrief(withoutMarkets(fixtureAt(KICKOFF_UTC, 'Coton Sport', 'Union Douala', 'fx-l1'), ['exact_score']));
  (fixture.competition as Json).name = LONG_COMPETITION;
  await openAsExpert(page, { language: 'fr', fixtures: [fixture] });
  await page.goto(`/expert/predictions/create?matchId=${fixture.id}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const stamp = plainSpaces(await inZone(page, DOUALA, 'fr', STAMP, KICKOFF_UTC));

  const header = page.locator('h1').locator('xpath=..');
  await expect(header).toContainText(LONG_COMPETITION.slice(0, 6));
  // Soft, so a page that clips both reports both.
  expect.soft(await hiddenKickoff(header, stamp), 'the composer header clips the kick-off').toEqual([]);

  await page.locator('#composer-home').fill('55');
  await page.getByRole('button', { name: fr['expert.action.preview'], exact: true }).click();
  const preview = page.locator('#main section[aria-label]');
  await expect(preview).toBeVisible();
  expect.soft(await hiddenKickoff(preview, stamp), 'the preview clips the kick-off').toEqual([]);
  expect(await sidewaysOverflow(page), 'the composer scrolls sideways').toBeLessThanOrEqual(0);
});

/*
 * Review finding #23. getErrorMessage returned axios's own err.message — "Network Error",
 * "Request failed with status code 500" — whenever the server sent no words, ahead of the caller's
 * translated fallback. So a French expert read English under a French title on the picker, on a
 * fixture that would not load and on a refused publish. The server's own words still come first
 * (the refused-publish test above); the HTTP client's are never shown.
 */
const TRANSPORT_ENGLISH = /Network Error|Request failed|status code|\bcanceled\b/i;

test('a picker that cannot reach the server says so in French, with no HTTP-client English', async ({ page }) => {
  await openAsExpert(page, { language: 'fr' });
  await page.route(url => url.pathname === '/api/v1/matches', route => route.abort('failed'));
  await page.goto('/expert/predictions/create');
  // The failed state's title (EmptyState puts its tone word in front of it, so not an exact match).
  await expect(page.locator('#main').getByText(fr['expert.picker.loadFailed'])).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await page.locator('#main').innerText(), 'the picker printed the HTTP client\'s English').not.toMatch(TRANSPORT_ENGLISH);
  await expectAllAccountedFor(page, journeyVocabulary(), 'a picker whose day list could not be reached');
});

test('a fixture that cannot be loaded says so in French, with the French reason', async ({ page }) => {
  await openAsExpert(page, { language: 'fr' });
  await page.route(url => url.pathname === `/api/v1/matches/${NEAR_MIDNIGHT.id}`, route => route.abort('failed'));
  await page.goto(`/expert/predictions/create?matchId=${NEAR_MIDNIGHT.id}`);
  await expect(page.locator('#main').getByText(fr['expert.compose.fixtureNotOpened'])).toBeVisible();
  await expect(page.locator('#main').getByText(fr['expert.compose.fixtureLoadFailed'], { exact: true }),
    'the French reason is not where the failure is explained').toBeVisible();
  expect(await page.locator('#main').innerText(), 'the composer printed the HTTP client\'s English').not.toMatch(TRANSPORT_ENGLISH);
});

test('a publish refused with no words from the server says so in French', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'fr' });
  // Registered after the expert stub, so it answers first: a 500 whose body is not JSON at all.
  let posts = 0;
  await page.route('**/api/v1/expert/predictions/manual', route => {
    posts += 1;
    return route.fulfill({ status: 500, contentType: 'text/plain', body: 'Internal Server Error' });
  });
  await openComposer(page);
  await page.locator('#composer-home').fill('55');
  await page.locator('#composer-draw').fill('25');
  await page.locator('#composer-away').fill('20');
  await page.getByRole('button', { name: fr['expert.action.publish'], exact: true }).click();
  await expect.poll(() => posts).toBe(1);
  const alert = page.locator('#main [role="alert"]');
  await expect(alert).toHaveText(fr['expert.compose.publishFailed']);
  expect(await page.locator('#main').innerText(), 'the composer printed the HTTP client\'s English').not.toMatch(TRANSPORT_ENGLISH);
  expect(world.created, 'the refused publish reached the stubbed create').toHaveLength(0);
});

test('changing the zone re-times the composer picker and asks the backend for the new day window', async ({ page }) => {
  await openAsExpert(page, { language: 'fr' });
  await openComposerPicker(page);
  const row = page.locator('li').filter({ hasText: 'Coton Sport' });
  await expect(row.locator('time')).toHaveText(await inZone(page, DOUALA, 'fr', CLOCK, KICKOFF_UTC));

  let dayRequests = 0;
  page.on('request', request => { if (/\/api\/v1\/matches\?/.test(request.url())) dayRequests += 1; });

  await page.getByTestId('footer-region-settings').first().click();
  await page.getByTestId('time-zone-choice').first().selectOption(NAIROBI);

  // 23:30Z is 00:30 in Douala and 02:30 in Nairobi, both on the same next day.
  await expect(row.locator('time')).toHaveText(await inZone(page, NAIROBI, 'fr', CLOCK, KICKOFF_UTC));
  // The day the kick-offs belong to is spelled out, with the zone named beside it.
  const day = page.getByTestId('picker-day-shown');
  await expect(day).toContainText(say('fr', 'expert.picker.dayShown', {
    date: await inZone(page, NAIROBI, 'fr', DATE_LONG, `${DOUALA_DAY}T12:00:00Z`),
  }));
  await expect(day).toContainText('Nairobi');
  // Polled: the refetch is issued by an effect after the preference commits.
  await expect.poll(() => dayRequests, { message: 'a change of zone is a change of window, so it must be asked again' })
    .toBeGreaterThan(0);
});

/* ======================================================== the forecast badge, four states */

/**
 * QA FINDING 9: A STORED FORECAST THAT IS OUT OF DATE IS NOT "NO FORECAST HELD".
 *
 * One fixture per state, all on whatever day the picker asks for, plus an expert-published
 * fixture whose forecast is stale — whose row must say BOTH things, since an expert's prediction
 * says nothing about the model's.
 */
const BADGE_FIXTURES: ApiMatch[] = [
  fixtureAt(isoIn(2 * DAY_MS), 'Coton Sport', 'Union Douala', 'fx-current'),
  withoutForecast(fixtureAt(isoIn(2 * DAY_MS + HOUR_MS), 'Fovu Baham', 'Bamboutos', 'fx-absent')),
  withStaleForecast(fixtureAt(isoIn(2 * DAY_MS + 2 * HOUR_MS), 'Canon Yaoundé', 'Colombe Sportive', 'fx-stale')),
  // Kept for reference: 3 hours past kick-off and still `scheduled`, as the compact brief says.
  withKickoffPassedForecast(withCompactBrief(fixtureAt(isoIn(-3 * HOUR_MS), 'Apejes Mfou', 'Gazelle Garoua', 'fx-reference'))),
  { ...withStaleForecast(fixtureAt(isoIn(2 * DAY_MS + 3 * HOUR_MS), 'PWD Bamenda', 'Aigle Royal', 'fx-expert')), expert_prediction: EXPERT_PREDICTION },
];

for (const language of ['en', 'fr'] as const) {
  test(`the picker badge says current, out of date, kept for reference or none, truthfully, in ${language}`, async ({ page }) => {
    const world = await openAsExpert(page, {
      language,
      fixtures: BADGE_FIXTURES,
      day: iso => ({ ...emptyDayPayload(iso), matches: BADGE_FIXTURES.map(match => ({ ...match })) }),
    });
    const label = (key: string) => say(language, key);
    const expected: Array<[string, string[]]> = [
      ['Coton Sport', [label('expert.picker.modelForecastHeld')]],
      ['Fovu Baham', [label('brief.noForecastHeld')]],
      ['Canon Yaoundé', [label('expert.picker.modelForecastStale')]],
      ['Apejes Mfou', [label('expert.picker.modelForecastReference')]],
      ['PWD Bamenda', [label('expert.picker.modelForecastStale'), label('expert.picker.expertPublished')]],
    ];
    expect(label('expert.picker.modelForecastStale'), 'out of date must not read as none').not.toBe(label('brief.noForecastHeld'));

    for (const path of ['/expert/match-selection', '/expert/predictions/create']) {
      await page.goto(path);
      await expect(page.locator('li').filter({ hasText: 'Coton Sport' })).toHaveCount(1);
      await page.waitForLoadState('networkidle');

      // What each row says, first, in words.
      for (const [home, badges] of expected) {
        const row = page.locator('li').filter({ hasText: home });
        for (const badge of badges) {
          await expect(row, `${path}: the ${home} row does not say "${badge}"`).toContainText(badge);
        }
      }
      // "No forecast held" is said of the one fixture that has none, and of no other.
      await expect(page.locator('li').filter({ hasText: label('brief.noForecastHeld') }),
        `${path}: a fixture with a forecast was labelled as having none`).toHaveCount(1);

      // Then which badge says it, and what a screen reader is told.
      for (const [home, badges] of expected) {
        const row = page.locator('li').filter({ hasText: home });
        await expect(row.getByTestId('picker-forecast'), `${path}: the ${home} row's forecast badge`)
          .toHaveText(badges[0]);
        await expect(row.getByTestId('picker-expert'), `${path}: the ${home} row's expert badge`)
          .toHaveCount(badges.length > 1 ? 1 : 0);
        // The row's accessible name hides its badges, so they are its description.
        const description = await row.getByRole('button').evaluate(el => {
          const ids = (el.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
          return ids.map(id => document.getElementById(id)?.textContent ?? '').join(' ');
        });
        for (const badge of badges) expect(description, `${path}: ${home} does not announce "${badge}"`).toContain(badge);
      }
    }

    // Read from the list payload already on the wire: browsing asks for nothing else.
    const forecastReads = world.requests.filter(url => /\/api\/v1\/matches\/[^/?]+/.test(url) || /\/markets\b/.test(url));
    expect(forecastReads, 'the badge asked the backend for something beyond the day list').toEqual([]);
    expect(world.requests.filter(url => /refresh=true/i.test(url)), 'a provider refresh was asked for').toEqual([]);
    const lists = world.requests.filter(url => /\/api\/v1\/matches\?/.test(url));
    expect(lists.length, 'the pickers loaded their days').toBeGreaterThan(0);
    for (const url of lists) expect(new URL(url).searchParams.get('refresh'), `${url} was not a stored-only read`).toBe('false');
  });
}

/* ======================================================= the backend's words, kept as they are */

test('the backend\'s own sentence in the evidence panel is shown as written, marked English, and nothing else is', async ({ page }) => {
  const captured = matchDetail(baseMatches()[0].id) as ApiMatch;
  const detail = { ...captured, kickoff_utc: KICKOFF_UTC };
  await openAsExpert(page, { language: 'fr', fixtures: [detail] });
  await page.goto(`/expert/predictions/create?matchId=${detail.id}`);
  await expect(page.locator('#composer-home')).toBeVisible();
  await page.waitForLoadState('networkidle');

  const brief = detail.brief as { markets: Array<{ key: string; expert: { detail: string | null } }> };
  const expertDetail = brief.markets.find(market => market.key === 'match_result')?.expert.detail;
  expect(expertDetail, 'the captured brief carries the backend sentence this test is about').toBeTruthy();

  expect(await verbatimStrings(page, '#main'), 'the backend sentences on the page, exactly')
    .toEqual([{ text: expertDetail, lang: 'en' }]);
  await expectAllAccountedFor(page, frenchVocabulary([detail], { withVenue: true }), 'the evidence panel with a full brief');
});

/* ============================================================== the edit form, in French */

for (const language of ['fr', 'en'] as const) {
  test(`an edit reopens in the reader's decimals and is checked in ${language}`, async ({ page }) => {
    const world = await openAsExpert(page, { language, mine: [minePrediction()] });
    await page.goto('/expert/predictions/my-predictions');
    await page.getByRole('button', { name: say(language, 'expert.action.edit'), exact: true }).click();
    await expect(page.locator('#edit-pred-1-home')).toBeVisible();

    // Reopened as typed in this language: 55,5 in French, 55.5 in English, never 0.555.
    const decimal = language === 'fr' ? ',' : '.';
    await expect(page.locator('#edit-pred-1-home')).toHaveValue(`55${decimal}5`);
    await expect(page.locator('#edit-pred-1-draw')).toHaveValue(`24${decimal}5`);
    await expect(page.locator('#edit-pred-1-away')).toHaveValue('20');
    await expect(page.locator('#edit-pred-1-conviction')).toHaveValue('70');
    await expect(page.locator('#edit-pred-1-btts-yes')).toHaveValue('45');

    if (language === 'fr') {
      // The editor box: the edit note, the whole editor, and nothing in it English.
      await page.evaluate(() => document.querySelector('#edit-pred-1-home')?.closest('fieldset')?.parentElement
        ?.parentElement?.setAttribute('data-walk', 'editor'));
      await expectAllAccountedFor(page, journeyVocabulary(), 'the edit form', '[data-walk="editor"]');
    }

    // Cancel sends nothing.
    await page.getByRole('button', { name: say(language, 'expert.action.cancel'), exact: true }).click();
    await nothingSent(page, world.updated, 'Cancel sent an update');

    // An unbalanced edit is refused in the reader's language and sends nothing.
    await page.getByRole('button', { name: say(language, 'expert.action.edit'), exact: true }).click();
    await page.locator('#edit-pred-1-draw').fill('30');
    const hundred = await percentIn(page, language, 100);
    const rule = say(language, 'expert.editor.ruleOutcomes', { hundred });
    await expect(totalLine(page, rule)).toHaveText(
      `${say(language, 'expert.editor.totalUnbalanced', { percent: await percentIn(page, language, 105.5), rule })} `
      + say(language, 'expert.editor.adjustRemove', { points: await pointsIn(page, language, 5.5) }),
    );
    await page.getByRole('button', { name: say(language, 'expert.action.saveChanges'), exact: true }).click();
    await expect(page.locator('#main')).toContainText(say(language, 'expert.mine.fixThenSave'));
    await nothingSent(page, world.updated, 'an unbalanced edit was sent');

    // Balanced again, the conviction withdrawn: exactly one PUT, with the reader's decimals read
    // back as the same probabilities and the withdrawn conviction as null.
    await page.locator('#edit-pred-1-draw').fill(`24${decimal}5`);
    await page.locator('#edit-pred-1-conviction').fill('');
    await page.getByRole('button', { name: say(language, 'expert.action.saveChanges'), exact: true }).click();
    await expect.poll(() => world.updated.length, { message: 'the save was not sent' }).toBe(1);
    await page.waitForTimeout(1000);
    expect(world.updated, 'the save was sent more than once').toHaveLength(1);
    const { id, body } = world.updated[0];
    expect(id).toBe('pred-1');
    expect(body.home_win_prob).toBe(0.555);
    expect(body.draw_prob).toBe(0.245);
    expect(body.away_win_prob).toBe(0.2);
    expect(body.confidence_score).toBeNull();
    expect(body.btts_yes_prob).toBe(0.45);
  });
}

/* ================================================================ the English, unchanged */

/**
 * THE ENGLISH COMPOSER SAYS EXACTLY WHAT IT SAID.
 *
 * Every sentence below is the literal the components shipped before they read the catalogue,
 * typed out here on purpose rather than read from it: if a catalogue entry drifts, this is the
 * test that notices.
 */
test('the English composer reads exactly as it did', async ({ page }) => {
  const world = await openAsExpert(page, { language: 'en' });
  await openComposer(page);
  const main = page.locator('#main');

  for (const sentence of [
    'Match result',
    'Your own percentages for the three outcomes. Every prediction publishes this market.',
    'Coton Sport win', 'Draw', 'Union Douala win',
    'The three outcomes must total 100%.',
    'Your conviction in this call(optional)',
    'How strongly you hold this view. Left blank, no conviction is published — it is never inferred from how large your percentages are, and it is not an accuracy.',
    'Other markets',
    'Tick only the markets you want to publish a view on. The rest stay unavailable.',
    'Both teams to score', 'Over / under 2.5 goals', 'Over / under 3.5 goals',
    'Left unticked, this market is not published and readers see it as unavailable.',
    'Your reasoning(optional)',
    '0 of 2000 characters. Published with your prediction so readers can weigh it.',
    'What is already known',
    'The same evidence the public match page shows. It is here to read, not to copy — none of your fields are filled in from it.',
    'Model markets held: Match result, Both teams to score, Total goals 2.5, Total goals 3.5.',
    'Not supplied by the model: Exact score. Those stay unavailable unless you publish a view on them.',
  ]) {
    expect(normalise(await main.innerText()), `the English composer lost "${sentence}"`).toContain(sentence);
  }
  await expect(page.locator('#composer-reasoning')).toHaveAttribute('placeholder', 'What led you to these numbers — team news, recent form, the match-up.');
  await expect(page.getByLabel('What is already known about this fixture')).toBeVisible();
  const sides = await page.getByLabel('What is already known about this fixture').locator('span.uppercase').allTextContents();
  expect(sides).toEqual(['Home', 'Away']);

  await page.locator('#composer-home').fill('33');
  await page.locator('#composer-draw').fill('33');
  await page.locator('#composer-away').fill('33');
  await expect(totalLine(page, 'The three outcomes must total 100%.'))
    .toHaveText('99% total — The three outcomes must total 100%. Add 1.');
  await page.locator('#composer-away').fill('34');
  await expect(page.locator('p').filter({ hasText: /^100% total\.$/ })).toHaveCount(1);

  await page.locator('#composer-btts-enabled').check();
  await expect(main).toContainText('Both sides are published, and they must total 100%.');
  await page.locator('#composer-btts-yes').fill('98.995');
  await page.locator('#composer-btts-no').fill('2.005');
  await expect(totalLine(page, 'The two sides must total 100%.'))
    .toHaveText('101.01% total — The two sides must total 100%. Remove 1.01.');
  await page.locator('#composer-btts-no').fill('1.005');
  await page.locator('#composer-over25-enabled').check();
  await expect(main).toContainText('Over 2.5 goals');
  await expect(main).toContainText('Conviction for the goal lines');
  await expect(main).toContainText('One value covers both lines — that is what the API stores.');
  await page.locator('#composer-conviction').fill('fifty');
  await page.locator('#composer-over25').fill('101');
  await page.locator('#composer-reasoning').fill('x'.repeat(2001));
  await expect(main).toContainText('2001 of 2000 characters.');

  await page.getByRole('button', { name: 'Publish', exact: true }).click();
  await expect(page.locator('#composer-conviction-error')).toHaveText('Enter a number, for example 55.');
  await expect(page.locator('#composer-over25-error')).toHaveText('Enter a percentage between 0 and 100.');
  await expect(page.locator('#composer-under25-error')).toHaveText('Enter a percentage, or untick this line.');
  await expect(main).toContainText('Shorten this to 2000 characters — it is 2001 now.');
  await nothingSent(page, world.created, 'an invalid English form was sent');

  // The preview of a valid one.
  await page.locator('#composer-btts-enabled').uncheck();
  await page.locator('#composer-over25-enabled').uncheck();
  await page.locator('#composer-conviction').fill('70');
  await page.locator('#composer-home').fill('55.5');
  await page.locator('#composer-draw').fill('24.5');
  await page.locator('#composer-away').fill('20');
  await page.locator('#composer-reasoning').fill('');
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  const preview = page.getByLabel('Preview of what will be published');
  const text = normalise(await preview.innerText());
  for (const sentence of [
    'This is what readers will see. Publishing puts it on the public match page straight away.',
    'Coton Sport v Union Douala',
    'Coton Sport win 55.5%', 'Draw 24.5%', 'Union Douala win 20%',
    'Your stated conviction: 70%.',
    'Both teams to score — not published. Readers see this market as unavailable, never as 0%.',
    'Over / under 2.5 goals — not published. Readers see this market as unavailable, never as 0%.',
  ]) {
    expect(text, `the English preview lost "${sentence}"`).toContain(sentence);
  }
});
