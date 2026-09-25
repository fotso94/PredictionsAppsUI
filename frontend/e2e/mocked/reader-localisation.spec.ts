import { expect, test, Page, Route, Request } from '@playwright/test';
import en from '../../src/i18n/messages/en';
import fr from '../../src/i18n/messages/fr';
import readerEn from '../../src/i18n/messages/reader.en';
import { compileMessage, renderMessage } from '../../src/i18n/format';
import {
  ApiMatch, baseCoverage, baseLeagues, baseMatches, baseStatus, matchDetail, stubBackend,
} from '../support/api-stub';
import { regularUser, signIn } from '../support/auth';

/**
 * The reader pages, in the reader's language and the reader's time zone.
 *
 * ── WHAT THIS FILE COVERS, AND WHY IT IS A FILE OF ITS OWN ──────────────────────────────────
 *
 * `localisation.spec.ts` covers the shell, the matchday workspace and the account screens. It
 * does not reach the competition list, one competition, a team, the dashboard, or the three
 * panels on a match page that carry provenance, an expert's earlier versions and the evidence
 * summary — which are the pages a reader who is not signed in actually lands on from a search
 * result, and where an English patch is therefore most visible. Those are this file's.
 *
 * ── THE THREE THINGS IT ESTABLISHES, AND THE ONE IT CANNOT ──────────────────────────────────
 *
 * 1. LANGUAGE. Each page shows its own heading in the reader's language, does NOT show the other
 *    language's heading, and carries no string from the other catalogue anywhere in its body.
 *    The stray list is GENERATED from the two catalogues, exactly as localisation.spec.ts
 *    generates its own, so it grows with the catalogue instead of rotting — but a generated list
 *    can only ever see a string that is IN a catalogue, and the English on these pages was
 *    hard-coded in the JSX until this package, where no generated check could reach it. That is
 *    what the positive heading anchor is for: it fails the moment a `t()` call is replaced by a
 *    literal again, which the generated check alone would sail straight past.
 *
 * 2. COUNTS. Every count-bearing label on these pages is rendered at 0, 1, 2 and 11 and must not
 *    move. That is not the same claim localisation.spec.ts's COUNT_CASES makes about a plural —
 *    it is the opposite one, and it is deliberate: the reader area may not use `{count, plural,
 *    …}` at all, because the table that proves a French plural lives in a spec this package does
 *    not own (see the header of src/i18n/messages/reader.en.ts). So the French was written to be
 *    invariable, and this pins the invariance — including that it is not faked with "(s)", which
 *    is the shape that would otherwise creep back in.
 *
 * 3. TIME. Every timestamp these pages show is formatted in the zone the READER CHOSE. Each one
 *    is asserted against a timestamp placed either side of midnight, so a page that fell back to
 *    the device's zone shows the wrong DAY and not merely the wrong hour — an off-by-one hour
 *    can hide in a screenshot; an off-by-one day cannot. Each assertion states the wrong answer
 *    as well as the right one, because containing the right date proves nothing on a panel that
 *    carries several.
 *
 * WHAT IT CANNOT ESTABLISH: that the French reads well. No test can. No native speaker has read
 * it; the terms I am least sure of are in the package report and marked REVIEW in reader.fr.ts.
 *
 * ── COST ─────────────────────────────────────────────────────────────────────────────────────
 * Every /api/v1 route is intercepted, so nothing here can reach a provider. The last test
 * asserts that directly: no request may carry `refresh=true`.
 */

type Language = 'en' | 'fr';

const LANGUAGE_KEY = 'sp.language.v1';
const ZONE_KEY = 'sp.timeZone.v1';

/**
 * The zones this file chooses, and the one it may never choose.
 *
 * playwright.config.ts puts the browser context on America/New_York. A test that chose New York
 * and then checked a New York answer would pass whether the reader's choice was honoured or
 * thrown away — that is how three tests in localisation.spec.ts were once tautologies. So every
 * zone chosen here is one the device is not on, and NEW_YORK appears only as the wrong answer.
 *
 * DUBAI is UTC+4 and DOUALA UTC+1, both ahead of UTC; New York is four or five hours behind it.
 * A timestamp late in the UTC evening is therefore the NEXT day in the chosen zone and the SAME
 * day on the device, which is the separation every date assertion below rests on.
 */
const DOUALA = 'Africa/Douala';
const DUBAI = 'Asia/Dubai';
/** The browser context's own zone. Chosen by no test; the answer no date test may give. */
const NEW_YORK = 'America/New_York';

/** Put the reader's stored choices in place before the application's own scripts run. */
async function seedPreferences(
  page: Page,
  preferences: { language?: Language; zone?: string },
): Promise<void> {
  await page.addInitScript(
    ([languageKey, zoneKey, language, zone]) => {
      if (language) window.localStorage.setItem(languageKey, language);
      if (zone) window.localStorage.setItem(zoneKey, zone);
    },
    [LANGUAGE_KEY, ZONE_KEY, preferences.language ?? '', preferences.zone ?? ''] as const,
  );
}

const bodyText = (page: Page): Promise<string> =>
  page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));

const normalise = (value: string): string => value.replace(/\s+/g, ' ').trim();

const panelText = async (page: Page, testId: string): Promise<string> =>
  normalise(await page.locator(`[data-testid="${testId}"]`).first().innerText());

/**
 * One saved fixture that really is being played, for the dashboard's in-play sentence.
 *
 * Kicked off 40 minutes ago and reporting the 40th minute, so nothing about it is stale and the
 * page can say so. It carries no `result_expected_by`, which is what every other fixture in this
 * file carries too: with no deadline from the backend nothing here is measured against one.
 */
const inPlaySave = (): Record<string, unknown> => {
  const match = baseMatches()[0];
  match.status = 'live';
  match.minute = '40';
  match.kickoff_utc = new Date(Date.now() - 40 * 60_000).toISOString();
  match.score = { home: 0, away: 1, ht_home: null, ht_away: null };
  return {
    match_id: match.id, note: null, saved_at: null, updated_at: null, match,
  };
};

/**
 * Everything the stubs actually serve, as one searchable blob.
 *
 * WHY THIS EXISTS. The settlement rules, the market definitions, the missing-data sentences and
 * the minimum-sample rationale are English PROSE the backend serves, and the interface renders
 * them verbatim in both languages — deliberately, because those sentences are load-bearing and a
 * French paraphrase that drifted from the rule would be worse than English (4C in the package
 * brief). One of them, "No expert has published a prediction for this fixture.", happens to be
 * word for word a catalogue string as well, so the generated stray check below would otherwise
 * report the SERVER's English as though the interface had failed to translate its own.
 *
 * So a candidate that appears verbatim in what the stub served is not counted. That is a
 * characterisation of a known gap, not an excuse for one, and it is only safe because it cuts
 * exactly one way: `the backend's own sentences are rendered verbatim on the French page` below
 * asserts that those same sentences ARE on the page. If the interface ever started translating
 * one of them, that test fails; if it ever started leaving one of OURS in English, the stray
 * check fails, because ours are not in this blob.
 */
const SERVED_PROSE = normalise([
  JSON.stringify(baseMatches()),
  JSON.stringify(matchDetail(baseMatches()[0].id)),
  JSON.stringify(baseLeagues()),
  JSON.stringify(baseCoverage()),
  JSON.stringify(baseStatus()),
].join(' '));

/**
 * The strings of one language a page in the other must not contain — generated, never listed.
 *
 * Same rule as localisation.spec.ts and for the same reasons: a key whose translation was
 * accidentally left as its English is caught here rather than by a reader, and the check grows
 * with the catalogue rather than being complete only on the day it was written. Excluded are
 * keys whose two languages are identical (a product name proves nothing), anything holding ICU
 * syntax (the rendered text is nothing like the source, so a substring test on it is
 * meaningless), anything under 16 characters or without a space (short strings collide by
 * accident, and a false failure here teaches the next person to weaken the test), and anything
 * the server itself sent (see SERVED_PROSE).
 */
function strayList(from: Record<keyof typeof en, string>): string[] {
  return (Object.keys(en) as Array<keyof typeof en>)
    .filter(key => en[key] !== fr[key])
    .map(key => from[key])
    .filter(value => !/[{}#]/.test(value))
    .filter(value => value.trim().length >= 16 && value.trim().includes(' '))
    .map(value => normalise(value))
    .filter(value => !SERVED_PROSE.includes(value));
}

const ENGLISH_ONLY = strayList(en as Record<keyof typeof en, string>);
const FRENCH_ONLY = strayList(fr as Record<keyof typeof en, string>);

/** Every catalogue string on the page that belongs to the other language. */
function strays(text: string, forbidden: string[]): string[] {
  const normalised = normalise(text);
  return forbidden.filter(value => normalised.includes(value));
}

/* ============================================================ the pages, in both languages */

const LEAGUE = (baseLeagues().competitions ?? [])[0] as { id: string; name: string };
const FIXTURE = baseMatches()[0];
const TEAM_ID = '00000000-0000-4000-8000-0000000000b1';

/**
 * Timestamps placed so that the device and the reader's choice disagree about the DAY.
 *
 *   17 Sep 2026 23:40Z  →  18 September 03:40 in Dubai (the choice, and the right answer)
 *                       →  17 September 19:40 in New York (the device, and the wrong one)
 *   15 Sep 2026 23:50Z  →  16 September 03:50 in Dubai / 15 September 19:50 in New York
 *
 * Two days apart on purpose: the Dubai reading of the earlier stamp must not collide with the
 * New York reading of the later one, or the "wrong answer is absent" assertions would be
 * unfalsifiable.
 */
const LATE_UTC = '2026-09-17T23:40:00Z';
const EARLIER_UTC = '2026-09-15T23:50:00Z';

/**
 * A detail payload carrying all three provenance times, an expert prediction and two earlier
 * published versions — none of which the captured fixture has.
 *
 * The brief's expert source entry is switched to present with a publication time as well: the
 * evidence panel reads presence from the BRIEF, not from the prediction list, so leaving it at
 * `present: false` would have left the publication-time assertion testing nothing.
 */
function withRevisions(id: string): ApiMatch | null {
  const found = matchDetail(id);
  if (!found) return null;
  const forecast = {
    ...(found.forecast as Record<string, unknown>),
    model_run_at: EARLIER_UTC,
    provider_updated_at: EARLIER_UTC,
    fetched_at: LATE_UTC,
    generated_at_known: true,
  };
  const brief = JSON.parse(JSON.stringify(found.brief)) as {
    known: { sources: Array<Record<string, unknown>> };
  };
  const expertSource = brief.known.sources.find(entry => entry.source === 'expert');
  if (expertSource) {
    expertSource.present = true;
    expertSource.published_at = LATE_UTC;
  }
  const revision = (index: number) => ({
    id: `rev-${index}`,
    prediction_id: 'qa-expert-prediction',
    revision: index,
    replaced_at: LATE_UTC,
    edited_by: null,
    changes_summary: null,
    edited_after_kickoff: false,
    values: {
      home_win_prob: 40 + index, draw_prob: 35 - index, away_win_prob: 25,
      confidence_score: 50 + index, reasoning: null,
    },
  });
  return {
    ...found,
    forecast,
    brief,
    expert_prediction: {
      id: 'qa-expert-prediction',
      source: 'expert',
      priority_level: 1,
      status: 'published',
      home_win_prob: 50, draw_prob: 30, away_win_prob: 20,
      btts_yes_prob: null, btts_no_prob: null,
      total_goals_over_25_prob: null, total_goals_under_25_prob: null,
      total_goals_over_35_prob: null, total_goals_under_35_prob: null,
      total_goals_confidence: null,
      confidence_score: 60,
      reasoning: null,
      published_at: LATE_UTC,
      created_by: '00000000-0000-4000-8000-0000000000e1',
    },
    expert_prediction_revisions: [revision(1), revision(2)],
  } as unknown as ApiMatch;
}

/** A kickoff `days` from now at `hourUtc`, so a fixture list is never empty by accident. */
function futureIso(days: number, hourUtc: number): string {
  const at = new Date();
  at.setUTCDate(at.getUTCDate() + days);
  at.setUTCHours(hourUtc, 0, 0, 0);
  return at.toISOString();
}

/**
 * How a date reads in one zone — computed the way the page computes it, IN THE PAGE.
 *
 * Not `new Intl.DateTimeFormat(...)` in the test process, which is the obvious way to write this
 * and is wrong. Node and the browser ship different CLDR data, and the two do not even agree on
 * a month abbreviation: Node's ICU writes "18 Sept 2026" where WebKit — which is what the
 * mocked-mobile project runs — writes "18 Sep 2026". A hard-coded expectation is worse again,
 * because it pins one engine's spelling and fails on the other.
 *
 * Evaluating it in the page compares like with like: the same engine, the same locale data, the
 * same zone database. What the assertion is actually about — WHICH DAY the timestamp falls on —
 * is exactly what survives that, and it is the one thing a device-zone bug changes.
 */
async function dayIn(page: Page, zone: string, iso: string, locale: string): Promise<string> {
  return page.evaluate(
    ([zoneId, at, tag]) => new Intl.DateTimeFormat(tag, {
      timeZone: zoneId, day: 'numeric', month: 'short', year: 'numeric',
    }).format(new Date(at)),
    [zone, iso, locale] as const,
  );
}

/**
 * `/teams/{id}`, which stubBackend answers with `{ team: null }` — a page that renders "Team not
 * found." and would therefore pass a "no English here" check by having almost nothing on it.
 *
 * Registered AFTER stubBackend on purpose: Playwright tries the most recently added route first,
 * so this wins for the one prefix it claims and stubBackend keeps everything else.
 */
async function stubTeam(page: Page, options: { upcoming?: ApiMatch[]; recent?: ApiMatch[] } = {}): Promise<void> {
  await page.route('**/api/v1/teams/**', (route: Route, request: Request) => {
    const body = new URL(request.url()).pathname.includes('/teams/search')
      ? { teams: [], competitions: [] }
      : {
        // The club's own name, which is never translated in either language.
        team: { id: TEAM_ID, name: 'Coton Sport', short_name: 'CTS', logo: '/teams/default.svg', country: 'Cameroon' },
        upcoming: options.upcoming ?? [FIXTURE],
        recent: options.recent ?? [],
      };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

/** Standings and league fixtures with a chosen number of rows, for the count assertions. */
async function stubLeague(
  page: Page,
  options: { teams?: number; fixtures?: ApiMatch[] } = {},
): Promise<void> {
  const teams = options.teams ?? 2;
  await page.route('**/api/v1/leagues/*/**', (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname;
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (path.endsWith('/standings')) {
      return json({
        competition: LEAGUE,
        standings: Array.from({ length: teams }, (_, index) => ({
          position: index + 1,
          team: { id: `team-${index}`, external_id: `x${index}`, name: `Club ${index + 1}`, logo: '/teams/default.svg' },
          played: 3, won: 2, drawn: 1, lost: 0, goals_for: 5, goals_against: 2, goal_difference: 3, points: 7,
          form: [],
        })),
        errors: [],
      });
    }
    if (path.endsWith('/matches')) {
      return json({ competition: LEAGUE, matches: options.fixtures ?? [], errors: [] });
    }
    return json(LEAGUE);
  });
}

/**
 * The routes this package claims, the key that proves the page arrived, and whether it is behind
 * sign-in. Named here rather than in prose so the report and the test cannot disagree.
 *
 * `/predictions/today` is a two-line wrapper around the already-translated matchday workspace and
 * carries no wording of its own; it is listed because the route is in this package's ownership,
 * and "nothing here to translate, and still right" is worth one assertion rather than a sentence
 * in a report.
 */
const ROUTES: Array<{ path: string; anchor: keyof typeof en; signedIn?: boolean }> = [
  { path: '/leagues', anchor: 'reader.leagues.subheading' },
  { path: `/league/${LEAGUE.id}`, anchor: 'reader.upcomingMatches' },
  { path: `/teams/${TEAM_ID}`, anchor: 'reader.team.recentMatches' },
  { path: '/predictions/today', anchor: 'matchday.title.today' },
  { path: '/dashboard', anchor: 'reader.dashboard.feedHeading', signedIn: true },
];

for (const language of ['en', 'fr'] as const) {
  const other: Language = language === 'en' ? 'fr' : 'en';

  test(`the reader pages are in ${language} and carry nothing from the other catalogue`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page, { matchById: matchDetail });
    await stubLeague(page, { fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
    await stubTeam(page, { recent: [FIXTURE] });
    await signIn(page);

    for (const route of ROUTES) {
      await page.goto(route.path);
      await page.waitForLoadState('networkidle');

      // A screen reader picks its voice from this. Getting it wrong is a defect a sighted
      // reviewer never sees.
      await expect(page.locator('html')).toHaveAttribute('lang', language);

      const text = normalise(await bodyText(page));

      // THE POSITIVE ANCHOR. The generated check below can only see catalogue strings; this is
      // what fails when a t() call is replaced by an English literal again.
      const mine = normalise((language === 'en' ? en : fr)[route.anchor]);
      const theirs = normalise((other === 'en' ? en : fr)[route.anchor]);
      expect(text, `${route.path} did not show its own ${language} heading`).toContain(mine);
      if (mine !== theirs) {
        expect(text, `${route.path} showed the ${other} heading as well`).not.toContain(theirs);
      }

      const found = strays(text, language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY);
      expect(found, `${route.path} in ${language} carried text from the other catalogue`).toEqual([]);
    }
  });

  /**
   * The three match-page panels, checked inside their own subtrees.
   *
   * SCOPED BY TEST ID, AND THAT IS NOT A CONVENIENCE. MatchDetailPage.tsx is another package's
   * file and is still entirely in English; asserting "no English on /match/:id" would fail for
   * reasons that have nothing to do with these three components, and the obvious way to make it
   * pass would be to weaken it. The claim this package can honestly make is about the panels it
   * owns, so that is the claim, stated exactly — and the rest of that page is in the report as
   * work another owner still has to do.
   */
  test(`the provenance, revision and evidence panels are in ${language}`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page, { matchById: withRevisions });
    await page.goto(`/match/${FIXTURE.id}`);
    await page.waitForLoadState('networkidle');

    for (const testId of ['match-brief', 'expert-revisions', 'forecast-provenance']) {
      await expect(
        page.locator(`[data-testid="${testId}"]`).first(),
        `${testId} is not on the page at all, so this test would prove nothing`,
      ).toBeVisible();
      const found = strays(await panelText(page, testId), language === 'fr' ? ENGLISH_ONLY : FRENCH_ONLY);
      expect(found, `${testId} in ${language} carried text from the other catalogue`).toEqual([]);
    }
  });
}

/**
 * The three labels that are NOT in the catalogue, because French spells them as English does.
 *
 * "Pts", "Points" and "Source" are the same word in both languages. A catalogue pair holding
 * the identical string on both sides is indistinguishable from a translation nobody did, and
 * localisation.spec.ts fails on exactly that; its exemption list of shared words belongs to
 * another package, so these three are literals at their call sites with a comment saying so
 * (STANDINGS_COLUMNS in LeagueDetailPage.tsx, and the Source row in ForecastProvenance.tsx).
 *
 * A literal is a claim, though — "this really is the French" — and a claim in a comment is not
 * checked by anything. This is what checks it: the words have to be on the page in BOTH
 * languages. If one of them ever needs translating, the French run fails here and the label goes
 * back into the catalogue.
 */
for (const language of ['en', 'fr'] as const) {
  test(`the labels French shares with English are on the ${language} page unchanged`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page, { matchById: withRevisions });
    await stubLeague(page, { teams: 3, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });

    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');
    const table = normalise(await page.locator('table').first().innerText());
    expect(table, 'the points column lost its header').toContain('Pts');
    // The accessible name is what a screen reader reads for every cell in that column.
    await expect(
      page.locator('th[aria-label="Points"]'),
      'the points column has no accessible full name',
    ).toHaveCount(1);

    await page.goto(`/match/${FIXTURE.id}`);
    await page.waitForLoadState('networkidle');
    expect(await panelText(page, 'forecast-provenance'), 'the provenance lost its Source row')
      .toContain('Source');
  });
}

/* ================================================== the backend's own prose stays the backend's */

/**
 * 4C, asserted rather than left in a comment.
 *
 * The brief's headline and its settlement sentence are English prose the API serves. They are
 * load-bearing — what a hit test compares, why a rate is withheld below thirty — so this package
 * does not translate them. What it must not do is translate them BY ACCIDENT, or quietly replace
 * one with a catalogue sentence that says something subtly different. This is also the other
 * half of SERVED_PROSE: the stray check above ignores these sentences, and this is what stops
 * that exclusion hiding anything.
 */
test('the backend’s own sentences are rendered verbatim on the French page', async ({ page }) => {
  const payload = matchDetail(FIXTURE.id);
  expect(payload, 'the captured detail payload is missing').not.toBeNull();
  const brief = (payload as ApiMatch).brief as { headline: string; reliability: { detail: string } };

  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page, { matchById: matchDetail });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');

  const panel = await panelText(page, 'match-brief');
  expect(panel, 'the brief’s own headline was not shown as the server sent it')
    .toContain(normalise(brief.headline));
  expect(panel, 'the backend’s settlement sentence was not shown as the server sent it')
    .toContain(normalise(brief.reliability.detail));
});

/* ================================================================== counts at 0, 1, 2 and 11 */

const COUNTS = [0, 1, 2, 11];

const render = (
  catalogue: Record<keyof typeof en, string>,
  locale: Language,
  key: keyof typeof en,
  params: Record<string, string | number> = {},
): string => renderMessage(compileMessage(catalogue[key]), locale, params);

/**
 * Every count-bearing string this area added, and the label each must keep at every count.
 *
 * READ THE ASSERTION CAREFULLY: it is the opposite of the one COUNT_CASES makes. These messages
 * MUST NOT change with the count. They are a numeral in an element of its own beside a label,
 * and a label that inflected would be wrong at three of the four counts in the language where
 * zero takes the singular. The French was chosen for exactly that property — « en favoris »,
 * « en direct », « fois » — and this is what stops the next edit quietly putting
 * « enregistré(s) » back where no count can reach it.
 */
const INVARIABLE_COUNTS: Array<{ key: keyof typeof en; hole: string }> = [
  { key: 'reader.dashboard.savedCount', hole: 'count' },
  { key: 'reader.dashboard.liveCount', hole: 'count' },
  { key: 'reader.brief.expertsPublished', hole: 'count' },
  { key: 'reader.revisions.summaryMany', hole: 'count' },
  { key: 'reader.revisions.summaryManyWhen', hole: 'count' },
  { key: 'reader.revisions.version', hole: 'number' },
  // The follow control's count against its limit. Same claim, and the same reason for it: the
  // natural French — « 1 compétition suivie sur 5 », « 2 compétitions suivies sur 5 » — needs a
  // plural this area may not write, so the label was made a category name that does not inflect.
  // `limit` below is 5, which is none of 0, 1, 2 or 11, so stripping the count cannot strip it.
  { key: 'reader.follow.team.count', hole: 'count' },
  { key: 'reader.follow.league.count', hole: 'count' },
];

for (const language of ['en', 'fr'] as const) {
  test(`every ${language} count label in the reader area reads the same at 0, 1, 2 and 11`, () => {
    const catalogue = (language === 'en' ? en : fr) as Record<keyof typeof en, string>;
    const wrong: string[] = [];
    for (const { key, hole } of INVARIABLE_COUNTS) {
      const rendered = COUNTS.map(count => render(catalogue, language, key, { [hole]: count, when: '30 janvier 2026', limit: 5 }));
      // Strip the numeral itself; what is left is the label, and the label may not move.
      const labels = rendered.map((line, index) => line.replace(String(COUNTS[index]), '∎'));
      if (new Set(labels).size !== 1) {
        wrong.push(`${key} changes with the count: ${JSON.stringify(rendered)}`);
      }
      if (/\(s\)|\(e\)/.test(catalogue[key])) {
        wrong.push(`${key} fakes agreement with a written-out suffix`);
      }
    }
    expect(wrong, 'these reader labels do not hold at every count').toEqual([]);
  });
}

/*
 * The reader area now counts things (the selections dock, the suggested combinations), and its
 * count-bearing messages are rendered at 0, 1, 2 and 11 in COUNT_CASES in localisation.spec.ts,
 * like every other area's. The guard that once refused a reader plural until that table could
 * take one was retired on the day it said to.
 */

/** The same counts on the page itself, drawn from real rows rather than from a catalogue. */
for (const count of COUNTS) {
  test(`the competition page shows ${count} fixtures and ${count} teams in French without moving its labels`, async ({ page }) => {
    const fixtures = Array.from({ length: count }, (_, index) => ({
      ...FIXTURE,
      id: `${FIXTURE.id}-${index}`,
      // Well inside the two-week window and after today in every zone, so all of them list.
      kickoff_utc: futureIso(index + 2, 12),
    }));

    await seedPreferences(page, { language: 'fr', zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: count, fixtures });
    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');

    const text = normalise(await bodyText(page));
    // The label is invariable in every case — including zero, where French takes the singular
    // and the English-shaped « 0 matchs » would be wrong.
    expect(text).toContain(normalise(fr['reader.upcomingMatches']));
    if (count === 0) {
      expect(text, 'zero fixtures must say so rather than showing an empty list')
        .toContain(normalise(fr['reader.league.noFixturesTitle']));
      expect(text, 'zero teams must not draw a standings table')
        .toContain(normalise(fr['reader.league.nothingTitle']));
    } else {
      expect(text).toMatch(new RegExp(`${fr['reader.upcomingMatches']}\\s*${count}\\b`));
      expect(text).toMatch(new RegExp(`${fr['reader.league.teams']}\\s*\\(\\s*${count}\\s*\\)`));
    }
    expect(text, 'a written-out suffix is how agreement gets faked').not.toMatch(/\(s\)/);
  });
}

/**
 * The dashboard's own count sentence, rendered by the page rather than by the catalogue.
 *
 * WHY THIS IS NOT COVERED BY THE TABLE ABOVE. The two labels go through `Emphasised`, which
 * finds the numeral INSIDE the rendered sentence and wraps that run — and which falls back to
 * the plain sentence, silently and by design, when it cannot find the value. A mismatch between
 * the string the page interpolates and the string it then searches for (a grouped "1 234"
 * against a bare 1234, say) therefore costs the tabular-figure class and nothing else: no error,
 * no blank, nothing a catalogue test can see. So the assertion is on the DOM — the numeral has
 * to be inside its own `.num` element, which is only true if the lookup succeeded.
 *
 * `stubBackend` answers `/api/v1/me/favourites` from its catch-all with `{}`, which maps to zero
 * saves, so the payload is stubbed here on purpose.
 *
 * THE IN-PLAY COUNT NEEDS A FIXTURE THAT IS IN PLAY, and not merely a number in `counts`. The
 * page counts the fixtures it was actually sent and can see are running, because the server's
 * bucket is filled from a stored status — which a fixture keeps until its final score arrives —
 * and "1 en direct" over a card with no running match on it is the one sentence a
 * dashboard must never say (src/utils/resultDelay.ts). `counts.total` stays at 3: a server can
 * hold more saves than it could serialise, and the saved sentence is about what it holds.
 */
test('the dashboard’s saved and in-play counts are whole French sentences with the numeral picked out', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page);
  await signIn(page);
  await page.route(/\/api\/v1\/me\/favourites(\?|$)/, (route: Route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      teams: [], leagues: [], team_ids: [], league_ids: [],
      unresolved: { teams: [], leagues: [] },
      limits: { teams: 10, leagues: 5 },
      saved_matches: {
        upcoming: [], live: [inPlaySave()], finished: [],
        counts: { upcoming: 2, live: 1, finished: 0, total: 3 },
      },
    }),
  }));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  /*
    SCOPED TO THE COUNT LINE, not to the whole card. SavedMatchesPanel.tsx sits inside this card,
    belongs to another package and is still English throughout — it says "You have 3 saved
    matches, but we no longer hold the fixture behind them" — so a negative assertion across the
    card would be reporting THEIR untranslated English as this package's failure. That gap is
    real and is named in the package report; what is asserted here is the sentence this package
    owns, in the element that holds it.
  */
  const countLine = page.locator('[data-testid="dashboard-my-matches"] p:has(span.num)').first();
  const text = normalise(await countLine.innerText());
  expect(text, 'the saved count is not the French sentence').toContain('3 en favoris');
  expect(text, 'the in-play count is not the French sentence').toContain('1 en direct');
  expect(text, 'the English saved count is on the French dashboard').not.toContain('3 saved');
  expect(text, 'the English in-play count is on the French dashboard').not.toContain('1 in play now');

  // Each numeral in an element of its own, which is what `Emphasised` is there to produce and
  // what its silent fallback would quietly remove.
  await expect(countLine.locator('span.num'), 'the numerals lost their tabular-figure run').toHaveCount(2);
  await expect(countLine.locator('span.num').first()).toHaveText('3');
  await expect(countLine.locator('span.num').nth(1)).toHaveText('1');
});

/* ============================================================= time, in the zone the reader chose */

/**
 * The premise every date assertion rests on, asserted instead of assumed.
 *
 * If playwright.config.ts is ever moved onto one of the zones these tests choose, this fails
 * once and loudly rather than turning the date tests into tautologies nobody notices.
 */
test('the device this suite runs on is on neither zone these tests choose', async ({ page }) => {
  await stubBackend(page);
  await page.goto('/leagues');
  const device = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(device, 'playwright.config.ts sets the browser context zone').toBe(NEW_YORK);
  expect([DOUALA, DUBAI], 'a test may never choose the zone the device is already on').not.toContain(device);
});

test('the three provenance times are shown in the chosen zone, on the chosen zone’s day', async ({ page }) => {
  await seedPreferences(page, { language: 'en', zone: DUBAI });
  await stubBackend(page, { matchById: withRevisions });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');

  const text = await panelText(page, 'forecast-provenance');

  // "Retrieved by this site" is 18 September in Dubai and 17 September on the device; the model
  // run is 16 September in Dubai and 15 September on the device. Both wrong answers are asserted
  // absent, because containing the right date proves nothing on a panel carrying three of them.
  expect(text, 'the retrieval time is not on the Dubai day')
    .toContain(await dayIn(page, DUBAI, LATE_UTC, 'en-GB'));
  expect(text, 'the model-run time is not on the Dubai day')
    .toContain(await dayIn(page, DUBAI, EARLIER_UTC, 'en-GB'));
  expect(text, 'the retrieval time was formatted in the DEVICE’s zone')
    .not.toContain(await dayIn(page, NEW_YORK, LATE_UTC, 'en-GB'));
  expect(text, 'the model-run time was formatted in the DEVICE’s zone')
    .not.toContain(await dayIn(page, NEW_YORK, EARLIER_UTC, 'en-GB'));

  // And the clock readings, which separate the zone from the calendar.
  expect(text, 'the Dubai wall-clock reading is missing').toContain('03:40');
  expect(text, 'the device’s wall-clock reading is on the page').not.toContain('19:40');

  // The panel names the zone it is speaking in, once, rather than three times on three rows.
  const zoneLine = await panelText(page, 'provenance-zone');
  expect(zoneLine, 'the provenance does not say which zone these readings are in').toContain('Dubai');
  expect(zoneLine, 'these timestamps carry an offset, so no UTC caveat belongs here')
    .not.toContain(normalise(en['reader.provenance.unzoned']));
});

test('a revision’s replacement time and an expert’s publication time follow the chosen zone', async ({ page }) => {
  await seedPreferences(page, { language: 'fr', zone: DUBAI });
  await stubBackend(page, { matchById: withRevisions });
  await page.goto(`/match/${FIXTURE.id}`);
  await page.waitForLoadState('networkidle');

  const revisions = await panelText(page, 'expert-revisions');
  expect(revisions, 'the replacement time is not on the Dubai day')
    .toContain(await dayIn(page, DUBAI, LATE_UTC, 'fr-FR'));
  expect(revisions, 'the replacement time was formatted in the DEVICE’s zone')
    .not.toContain(await dayIn(page, NEW_YORK, LATE_UTC, 'fr-FR'));
  expect(revisions, 'the Dubai wall-clock reading is missing').toContain('03:40');

  // Two revisions, so the "N times" form is the one on the page and « fois » is invariable.
  expect(revisions, 'the revision count is not in its French form').toContain('2 fois');

  const brief = await panelText(page, 'match-brief');
  expect(brief, 'the expert’s publication time is not on the Dubai day')
    .toContain(await dayIn(page, DUBAI, LATE_UTC, 'fr-FR'));
  expect(brief, 'the expert’s publication time was formatted in the DEVICE’s zone')
    .not.toContain(await dayIn(page, NEW_YORK, LATE_UTC, 'fr-FR'));
});

/**
 * The competition page asks the backend for a window bounded by the READER's zone.
 *
 * This is the half of the time-zone question that is not about display. `tz_offset` must not be
 * computed from `-new Date().getTimezoneOffset()`, the DEVICE's offset: a reader in Douala on a
 * laptop still set to New York would be sent a fortnight cut on New York boundaries, while the
 * matchday workspace beside it cuts the same fixtures on Douala's.
 */
test('the competition’s fixture window is asked for in the reader’s zone, not the device’s', async ({ page }) => {
  const offsets: string[] = [];
  await seedPreferences(page, { language: 'en', zone: DOUALA });
  await stubBackend(page);
  await stubLeague(page, { fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.includes('/leagues/') && url.pathname.endsWith('/matches')) {
      offsets.push(url.searchParams.get('tz_offset') ?? 'absent');
    }
  });

  await page.goto(`/league/${LEAGUE.id}`);
  await page.waitForLoadState('networkidle');

  expect(offsets.length, 'the competition page did not read its fixtures').toBeGreaterThan(0);
  // Douala is UTC+1 all year: 60 minutes east. New York is -240 in September.
  expect(offsets, 'the fixture window was bounded by the device’s zone').toEqual(offsets.map(() => '60'));
});

/* ================================================================= nothing here spends allowance */

test('no reader page asks a provider for anything', async ({ page }) => {
  const refreshing: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1')) return;
    if (url.searchParams.get('refresh') === 'true') refreshing.push(request.url());
  });

  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page, { matchById: withRevisions });
  await stubLeague(page, { fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
  await stubTeam(page);

  for (const path of ['/leagues', `/league/${LEAGUE.id}`, `/teams/${TEAM_ID}`, `/match/${FIXTURE.id}`]) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
  }

  expect(refreshing, 'a reader page asked the backend to refresh from a provider').toEqual([]);
});

/* ============================================ the follow control, on the pages that carry it */

/**
 * ── WHY ONE SHARED CONTROL GETS A SECTION OF ITS OWN ────────────────────────────────────────
 *
 * FollowButton.tsx held its English in the JSX — the word on the button, the count against the
 * limit, the toast, the sentence read out after a write, and the accessible name. Every one of
 * those was invisible to the generated stray check at the top of this file, which can only ever
 * find a string that is IN a catalogue. So `/league/:id` and `/teams/:id` passed "this page
 * carries nothing from the other catalogue" while showing a French reader "Follow" and "0 of 5
 * competitions followed", and the dashboard's follow list did the same. Two pages reported as
 * fully translated, and one control responsible for all of it.
 *
 * So every assertion below is POSITIVE — the text on the page has to EQUAL the catalogue's own
 * sentence, rendered the way src/i18n renders it. A negative check ("no English here") passes
 * again the day somebody puts a literal back, which is exactly how this got missed the first
 * time.
 *
 * ── THE THREE THINGS IT ESTABLISHES ─────────────────────────────────────────────────────────
 *
 *  1. THE WORD, IN BOTH STATES AND BESIDE BOTH NOUNS. `reader.follow.team.following` and
 *     `reader.follow.league.following` are separate keys so French can agree with the noun the
 *     control sits beside; splitting them is a claim, and a claim in a comment is checked by
 *     nothing, so both are rendered here on the real page they belong to.
 *  2. WHAT IT ANNOUNCES. The accessible name is the half nobody looks at and was English on a
 *     French page with nothing on screen to show it. The labelled variant carries it as `title`,
 *     the dense variant as `aria-label`, and the outcome of a write is read out through
 *     `role="status"`. All three are asserted.
 *  3. THE COUNT AT 0, 1 AND SEVERAL — on the page, from real rows, not only in the catalogue.
 *     French takes the singular at 0 as well as at 1, so a label that inflected would be wrong
 *     at two of the four counts, and wrong first on the empty state. The line may not move.
 */

/** The limits the API reports. Five competitions, ten teams — the control never hard-codes them. */
const FOLLOW_LIMITS = { teams: 10, leagues: 5 };

/**
 * `/api/v1/me/favourites`, with a chosen set of follows.
 *
 * Registered AFTER stubBackend, whose catch-all answers this path with `{}` — a snapshot that
 * loads but carries no ids and no limits of its own. The count line needs both.
 */
async function stubFavourites(
  page: Page,
  ids: { teamIds?: () => string[]; leagueIds?: () => string[] } = {},
): Promise<void> {
  await page.route(/\/api\/v1\/me\/favourites(\?|$)/, (route: Route, request: Request) => {
    // Only the snapshot read. A follow write goes to /favourites/teams/<id> and is answered
    // separately, so this must not swallow it.
    if (request.method() !== 'GET') return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        teams: [], leagues: [],
        team_ids: ids.teamIds?.() ?? [],
        league_ids: ids.leagueIds?.() ?? [],
        unresolved: { teams: [], leagues: [] },
        limits: FOLLOW_LIMITS,
        saved_matches: {
          upcoming: [], live: [], finished: [],
          counts: { upcoming: 0, live: 0, finished: 0, total: 0 },
        },
      }),
    });
  });
}

/** The labelled control for one entity, and the dense one in a list row. */
const followControl = (page: Page, kind: 'team' | 'league') =>
  page.locator(`[data-testid="follow-button"][data-kind="${kind}"]`).first();

for (const language of ['en', 'fr'] as const) {
  const catalogue = (language === 'en' ? en : fr) as Record<keyof typeof en, string>;
  const otherCatalogue = (language === 'en' ? fr : en) as Record<keyof typeof en, string>;

  test(`the follow control is in ${language}, in both states, beside both nouns`, async ({ page }) => {
    // Nothing followed yet on the first pass; the second pass follows both, so each of the two
    // kind-specific state keys is rendered on the page it actually belongs to.
    let leagueIds: string[] = [];
    let teamIds: string[] = [];

    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: 2, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
    await stubTeam(page, { recent: [FIXTURE] });
    await signIn(page);
    await stubFavourites(page, { leagueIds: () => leagueIds, teamIds: () => teamIds });

    // ── not followed ──────────────────────────────────────────────────────────────────────
    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');

    const league = followControl(page, 'league');
    await expect(league, 'the competition control did not load its state').toHaveAttribute('data-following', 'false');
    await expect(league, 'the word on the control is not the catalogue’s')
      .toHaveText(catalogue['reader.follow.follow']);
    await expect(league, 'the word on the control is the other language’s')
      .not.toHaveText(otherCatalogue['reader.follow.follow']);
    // What it announces. The labelled variant carries its accessible name as a title.
    await expect(league, 'the accessible name is not in the reader’s language')
      .toHaveAttribute('title', render(catalogue, language, 'reader.follow.namedFollow', { name: LEAGUE.name }));

    // The dense variant in the standings, whose accessible name IS its aria-label.
    await expect(
      followControl(page, 'team'),
      'the dense control announces itself in the other language',
    ).toHaveAttribute('aria-label', render(catalogue, language, 'reader.follow.namedFollow', { name: 'Club 1' }));

    // ── followed ──────────────────────────────────────────────────────────────────────────
    leagueIds = [LEAGUE.id];
    teamIds = [TEAM_ID];

    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');
    const followedLeague = followControl(page, 'league');
    await expect(followedLeague).toHaveAttribute('data-following', 'true');
    await expect(followedLeague, 'the followed word does not agree with « compétition »')
      .toHaveText(catalogue['reader.follow.league.following']);
    await expect(followedLeague, 'the followed accessible name is not in the reader’s language')
      .toHaveAttribute('title', render(catalogue, language, 'reader.follow.namedFollowing', { name: LEAGUE.name }));

    await page.goto(`/teams/${TEAM_ID}`);
    await page.waitForLoadState('networkidle');
    const followedTeam = followControl(page, 'team');
    await expect(followedTeam).toHaveAttribute('data-following', 'true');
    await expect(followedTeam, 'the followed word does not agree with « équipe »')
      .toHaveText(catalogue['reader.follow.team.following']);
    await expect(followedTeam, 'the followed accessible name is not in the reader’s language')
      .toHaveAttribute('title', render(catalogue, language, 'reader.follow.namedFollowing', { name: 'Coton Sport' }));
  });

  /**
   * The count against the limit at 0, 1 and several — read off the page, not out of the
   * catalogue, and with the SHAPE of the line compared across the four.
   *
   * The shape is the assertion that matters. « 0 compétitions suivies » and « 1 compétitions
   * suivies » are the two forms an English-shaped pluraliser produces and French does not have,
   * and both of them would pass a test that only checked the numeral. Stripping the digits and
   * requiring one single remaining form is what catches a label that moves — including one that
   * fakes it with "(s)", which is asserted against directly.
   */
  test(`the follow count against the limit is right at 0, 1 and several in ${language}`, async ({ page }) => {
    let leagueIds: string[] = [];

    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: 1, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
    await signIn(page);
    await stubFavourites(page, { leagueIds: () => leagueIds });

    const shapes = new Set<string>();
    for (const followed of [0, 1, 2, FOLLOW_LIMITS.leagues]) {
      // Competitions OTHER than this one, so the control's own state — and therefore its word —
      // does not move with the count and the count line is the only thing under test.
      leagueIds = Array.from({ length: followed }, (_, index) => `another-competition-${index}`);

      await page.goto(`/league/${LEAGUE.id}`);
      await page.waitForLoadState('networkidle');

      const line = page.getByTestId('follow-count').first();
      await expect(line, `the count line is missing at ${followed}`).toBeVisible();
      await expect(line, `the count line at ${followed} is not the catalogue’s sentence`).toHaveText(
        render(catalogue, language, 'reader.follow.league.count', { count: followed, limit: FOLLOW_LIMITS.leagues }),
      );
      const text = normalise(await line.innerText());
      expect(text, 'a written-out suffix is how agreement gets faked').not.toMatch(/\(s\)|\(e\)/);
      shapes.add(text.replace(/\d+/g, '#'));
    }

    expect(
      [...shapes],
      'the follow count line changes shape with the count; in French 0 and 1 take the singular and 2 does not',
    ).toHaveLength(1);
  });

  /**
   * The sentence a screen reader is given after the write lands.
   *
   * It is a `role="status"` line rather than a toast alone, precisely because a toast can be
   * gone before anybody reaches it — so leaving it in English was leaving the one durable
   * confirmation of the write in the wrong language.
   */
  test(`the confirmation read out after a follow is in ${language}`, async ({ page }) => {
    const leagueIds: string[] = [];

    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: 1, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
    await signIn(page);
    await stubFavourites(page, { leagueIds: () => leagueIds });
    await page.route(`**/api/v1/me/favourites/leagues/${LEAGUE.id}`, (route: Route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        kind: 'league', id: LEAGUE.id, following: true, changed: true,
        ids: [LEAGUE.id], limit: FOLLOW_LIMITS.leagues,
      }),
    }));

    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');
    await followControl(page, 'league').click();

    await expect(
      page.getByTestId('follow-message'),
      'the outcome of the write was announced in the other language',
    ).toHaveText(render(catalogue, language, 'reader.follow.confirmed', { name: LEAGUE.name }));
  });
}

/**
 * The two states the tests above cannot reach, because neither has a snapshot behind it.
 *
 * SIGNED OUT is the state a reader arriving from a search result is actually in, and it is the
 * one whose word is longest in French — « Se connecter pour suivre » against "Sign in to
 * follow" — so it is also the one most likely to be left behind and least likely to be looked
 * at by somebody already signed in.
 *
 * THE LOAD FAILED is the state whose whole purpose is to say "we do not know", and saying it in
 * the wrong language is worse here than anywhere else on the control: an empty star that a
 * reader cannot read the caveat for asserts "you do not follow this", which is the one thing
 * this control must never claim on a failed read.
 */
for (const language of ['en', 'fr'] as const) {
  const catalogue = (language === 'en' ? en : fr) as Record<keyof typeof en, string>;

  test(`a signed-out reader is invited to sign in in ${language}, and is given no count`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: 1, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });

    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');

    const control = followControl(page, 'league');
    await expect(control, 'the signed-out invitation is not in the reader’s language')
      .toHaveText(catalogue['reader.follow.signIn']);
    await expect(control, 'the signed-out accessible name is not in the reader’s language')
      .toHaveAttribute('title', render(catalogue, language, 'reader.follow.namedSignIn', { name: LEAGUE.name }));
    // Nobody is signed in, so there is no count to report and none is invented.
    await expect(page.getByTestId('follow-count'), 'a count was shown for nobody').toHaveCount(0);
  });

  test(`a failed favourites read says so in ${language} rather than showing an empty star`, async ({ page }) => {
    await seedPreferences(page, { language, zone: DOUALA });
    await stubBackend(page);
    await stubLeague(page, { teams: 1, fixtures: [{ ...FIXTURE, kickoff_utc: futureIso(2, 12) }] });
    await signIn(page);
    await page.route(/\/api\/v1\/me\/favourites(\?|$)/, (route: Route, request: Request) => (
      request.method() === 'GET'
        ? route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'nope' }) })
        : route.fallback()
    ));

    await page.goto(`/league/${LEAGUE.id}`);
    await page.waitForLoadState('networkidle');

    await expect(
      page.getByTestId('follow-state-unknown').first(),
      'the caveat on a failed read is not in the reader’s language',
    ).toHaveText(render(catalogue, language, 'reader.follow.unknown', { name: LEAGUE.name }));
    // And the control does not claim to know: no aria-pressed, and no count against a limit.
    await expect(followControl(page, 'league')).not.toHaveAttribute('aria-pressed', /.*/);
    await expect(page.getByTestId('follow-count'), 'a count was reported from a snapshot that never arrived')
      .toHaveCount(0);
  });
}

/* ================================== French that does not fit, on the expert dashboard at 360px */

/**
 * ── WHY "THE PAGE DOES NOT SCROLL SIDEWAYS" IS NOT THE TEST ─────────────────────────────────
 *
 * Put `truncate` on the draft card's summary line — `white-space: nowrap` with
 * `overflow: hidden` — and at 360px in French the saved-ago run ends 106px past the paragraph
 * that holds it. The overflow is hidden on that PARAGRAPH, not on the page, so
 * `document.scrollWidth === document.clientWidth` throughout: the document does not scroll, and
 * the words are simply not there. A check written against the document stays green while the
 * reader is missing the end of the sentence.
 *
 * So what is asserted is CONTAINMENT: the run's own bounding box inside the box of the element
 * that holds it, and that element inside the card. That is the claim "a French reader can read
 * this", and it is the one a document-level check cannot make.
 *
 * ── AND WHY 360 AND FRENCH ──────────────────────────────────────────────────────────────────
 *
 * 360px is a Galaxy S-series and most budget Androids; playwright.config.ts's mocked-mobile is
 * an iPhone 13 at 390, and thirty pixels is the whole difference. The viewport is set in the
 * test rather than in a project because `mocked-mobile-360` runs one other file only, and
 * widening its testMatch is a change to a file this package does not own.
 *
 * French, because French is reliably longer: the test asserts that too rather than assuming it,
 * so the premise is visible and fails loudly if the two languages ever converge here.
 */

const DRAFT_KEY_PREFIX = 'expert.composer.draft.v1';
/** `regularUser()` in e2e/support/auth.ts. A draft is stored per signed-in user id. */
const QA_USER_ID = '00000000-0000-4000-8000-000000000001';
const DRAFT_MINUTES_AGO = 7;
/**
 * Two real competition names, both longer than the row was measured against.
 *
 * The first is what the defect was measured with: « Ligue des champions de la CAF · 21 septembre
 * 2026 » needed 298px in a 211px box. The second is longer than the row on its own, which is the
 * case where wrapping is not enough and something has to be abbreviated — the two together are
 * what pin WHICH of the two runs gives way. Neither is invented; both are CAF competitions.
 */
const LONG_COMPETITION = 'Ligue des champions de la CAF';
const LONGER_THAN_THE_ROW = 'Championnat d’Afrique des nations de football des moins de 17 ans';

/** The expert's own endpoints: one record, one published prediction, no moderation queue. */
async function stubExpertDashboard(page: Page, competition: () => string = () => LONG_COMPETITION): Promise<void> {
  await page.route('**/api/v1/expert/**', (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/expert/, '');
    const json = (body: unknown) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (path === '/analytics/performance') {
      return json({
        expert_id: 'qa-expert', expert_name: 'QA Expert',
        total_predictions: 12, published_predictions: 9, pending_predictions: 3,
        // Both null, never 0: nothing has been settled and nobody claimed a conviction, so the
        // page says so in words. 0 would be a different payload meaning a different thing — a
        // conviction claimed at zero, which the tile rightly prints as « 0 % ». Null is what the
        // real API sends for an expert who claimed nothing, and it puts « Aucune publiée » in
        // the tile.
        //
        // No assertion in this file reads the record grid: the three tests that use this stub
        // measure `draft-saved-ago`, `draft-summary`, `recent-row-kickoff` and
        // `recent-row-competition` against their own parents. Null is sent anyway, because a
        // stub that states one thing in its comment and sends another is wrong before it is red.
        accuracy_rate: null, average_confidence: null,
        predictions_by_league: {}, performance_trend: [],
        recent_predictions: [{
          id: 'pred-1', match_id: 'm1', source: 'EXPERT_MANUAL', priority_level: 1,
          home_win_prob: 0.55, draw_prob: 0.25, away_win_prob: 0.2, confidence_score: 0.8,
          btts_yes_prob: null, btts_no_prob: null, btts_confidence: null,
          total_goals_over_25_prob: null, total_goals_under_25_prob: null,
          total_goals_over_35_prob: null, total_goals_under_35_prob: null,
          total_goals_confidence: null, reasoning: null, key_factors: null,
          status: 'PUBLISHED', created_by: 'qa-expert',
          created_at: EARLIER_UTC, published_at: EARLIER_UTC, superseded_by: null,
          match_details: {
            home_team_name: 'Coton Sport', away_team_name: 'Union Douala',
            home_team_logo: null, away_team_logo: null,
            league_name: competition(), match_date: LATE_UTC, external_match_id: null,
          },
          user_details: { username: 'qa-expert', first_name: null, last_name: null },
        }],
      });
    }
    if (path === '/predictions/review-queue') return json([]);
    return json({});
  });
}

/** Half-written words in this browser, saved `DRAFT_MINUTES_AGO` ago. Nothing is published. */
async function seedDraft(page: Page): Promise<void> {
  await page.addInitScript(
    ([key, savedAt]) => {
      window.localStorage.setItem(key as string, JSON.stringify({
        fixture: {
          id: 'm1', homeTeam: 'Coton Sport', awayTeam: 'Union Douala',
          competition: 'Elite One', kickoff: null,
        },
        values: {
          homeWin: '55', draw: '25', awayWin: '20', conviction: '',
          bttsEnabled: false, bttsYes: '', bttsNo: '', bttsConviction: '',
          over25Enabled: false, over25: '', under25: '',
          over35Enabled: false, over35: '', under35: '',
          totalsConviction: '', reasoning: 'a private note nobody has published',
        },
        savedAt,
      }));
    },
    [
      `${DRAFT_KEY_PREFIX}.${QA_USER_ID}`,
      new Date(Date.now() - DRAFT_MINUTES_AGO * 60_000).toISOString(),
    ] as const,
  );
}

/** An element's box against the box of the element that holds it, in CSS pixels. */
async function overflowPastParent(page: Page, testId: string): Promise<{
  past: number; hidden: boolean; text: string;
}> {
  return page.getByTestId(testId).first().evaluate((el: HTMLElement) => {
    const parent = el.parentElement as HTMLElement;
    const own = el.getBoundingClientRect();
    const box = parent.getBoundingClientRect();
    return {
      past: Math.round(Math.max(own.right - box.right, box.left - own.left)),
      // The half that makes an overflow invisible rather than merely untidy.
      hidden: getComputedStyle(parent).overflowX === 'hidden',
      text: (el.textContent ?? '').trim(),
    };
  });
}

test('at 360px the French expert dashboard keeps its saved-ago line inside the box that holds it', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await seedPreferences(page, { language: 'fr', zone: DOUALA });
  await stubBackend(page);
  await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
  await stubExpertDashboard(page);
  await seedDraft(page);

  await page.goto('/expert/dashboard');
  await page.waitForLoadState('networkidle');

  // THE PREMISE, asserted rather than assumed: this line is longer in French than in English,
  // which is why an English-sized box loses it, and why the answer has to be the layout rather
  // than a shorter French string.
  const ago = (from: Record<keyof typeof en, string>, locale: Language) => render(
    from, locale, 'time.ago',
    { duration: render(from, locale, 'duration.minutes', { count: DRAFT_MINUTES_AGO }) },
  );
  const frenchLine = render(fr as Record<keyof typeof en, string>, 'fr', 'expert.draft.savedAgo', { ago: ago(fr as Record<keyof typeof en, string>, 'fr') });
  const englishLine = render(en as Record<keyof typeof en, string>, 'en', 'expert.draft.savedAgo', { ago: ago(en as Record<keyof typeof en, string>, 'en') });
  expect(
    frenchLine.length,
    'the premise of this test is that French runs longer here; it no longer does',
  ).toBeGreaterThan(englishLine.length);

  const savedAgo = page.getByTestId('draft-saved-ago');
  await expect(savedAgo, 'the draft card did not render its saved-ago line at all').toBeVisible();
  await expect(savedAgo, 'the saved-ago line is not the French sentence').toHaveText(
    new RegExp(`${frenchLine.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
  );

  const run = await overflowPastParent(page, 'draft-saved-ago');
  expect(
    run.past,
    `the saved-ago run ends ${run.past}px outside the line that holds it${run.hidden ? ', and that line hides its overflow, so a French reader loses the text entirely rather than scrolling to it' : ''}`,
  ).toBeLessThanOrEqual(1);

  const summary = await overflowPastParent(page, 'draft-summary');
  expect(summary.past, 'the draft summary line runs outside the card').toBeLessThanOrEqual(1);

  /*
    AND THE WEAKER CHECK, kept and labelled as such.

    A document-level overflow test cannot see the fault the assertion above is about: text that
    runs past the paragraph holding it is clipped there, one element down, so the DOCUMENT stays
    exactly as wide as the viewport and this assertion is green either way. It is kept where
    someone might reach for it INSTEAD, so the difference between the two claims is visible at
    the point of the mistake.
  */
  const scrolls = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrolls.scrollWidth, 'the page itself scrolls sideways at 360px')
    .toBeLessThanOrEqual(scrolls.clientWidth);
});

/**
 * The same shape, found on the same page by measuring rather than by reading.
 *
 * The published row's second line was one `truncate`d run holding a competition name joined to
 * a kick-off. Measured at 360px with a real competition name it needed 298px in a 211px box, and
 * what fell off the end was always the KICK-OFF, because the name comes first. An expert reads a
 * kick-off to decide whether a prediction is still prematch; losing it is not cosmetic.
 *
 * The two are not treated alike now, and the two cases below are what pin that:
 *
 *   - a name that FITS on its own: the pair does not fit together, so the line wraps and both
 *     are whole. Nothing is abbreviated at all.
 *   - a name LONGER THAN THE ROW: wrapping cannot help, so one of them has to give way — and
 *     it has to be the name. A name abbreviated with an ellipsis is still recognisable; a
 *     kick-off with its end cut off is a different date.
 *
 * Each case asserts its own premise (the runs really are under pressure) before asserting the
 * outcome, so neither can pass by being roomy.
 */
for (const [label, competition, nameMustGiveWay] of [
  ['a name that fits, so the line wraps and nothing is abbreviated', LONG_COMPETITION, false],
  ['a name longer than the row, so the name is abbreviated and the kick-off is not', LONGER_THAN_THE_ROW, true],
] as const) {
  test(`at 360px in French a published row keeps its kick-off: ${label}`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await seedPreferences(page, { language: 'fr', zone: DOUALA });
    await stubBackend(page);
    await signIn(page, { user: regularUser({ role: 'expert', full_name: 'QA Expert' }) });
    await stubExpertDashboard(page, () => competition);

    await page.goto('/expert/dashboard');
    await page.waitForLoadState('networkidle');

    const kickoff = page.getByTestId('recent-row-kickoff').first();
    await expect(kickoff, 'the published row shows no kick-off at all').toBeVisible();

    // The kick-off is 23:40Z on the 17th: the 18th in Douala, still the 17th in New York.
    const chosenDay = await dayIn(page, DOUALA, LATE_UTC, 'fr-FR');
    const deviceDay = await dayIn(page, NEW_YORK, LATE_UTC, 'fr-FR');
    const shown = normalise(await kickoff.innerText());
    expect(shown, 'the kick-off was not spelled out in the reader’s zone').toContain(chosenDay.split(' ')[0]);
    expect(shown, 'the kick-off was formatted in the DEVICE’s zone').not.toContain(`${deviceDay.split(' ')[0]} `);

    const run = await overflowPastParent(page, 'recent-row-kickoff');
    expect(run.past, `the kick-off ends ${run.past}px outside its line and is clipped away`)
      .toBeLessThanOrEqual(1);
    const lineRun = await overflowPastParent(page, 'recent-row-competition');
    expect(lineRun.past, 'the competition line runs outside the row that holds it').toBeLessThanOrEqual(1);

    const geometry = await page.getByTestId('recent-row-competition').first().evaluate((el: HTMLElement) => {
      const measure = (child: Element | null) => {
        const node = child as HTMLElement | null;
        return node
          ? { width: node.getBoundingClientRect().width, hidden: node.scrollWidth - node.clientWidth }
          : { width: 0, hidden: 0 };
      };
      return {
        lineWidth: el.clientWidth,
        hiddenByTheLine: el.scrollWidth - el.clientWidth,
        name: measure(el.querySelector('[data-testid="recent-row-competition-name"]')),
        kick: measure(el.querySelector('[data-testid="recent-row-kickoff"]')),
      };
    });

    // THE PREMISE. If the two runs fitted side by side there would be nothing under pressure
    // and every assertion below would pass whatever the layout did.
    expect(
      geometry.name.width + geometry.kick.width,
      'the two runs fit on one line here, so this case is not exercising the crowding it claims to',
    ).toBeGreaterThan(geometry.lineWidth);

    // Nothing is hidden by the line itself: what does not fit wrapped, it was not clipped away.
    expect(geometry.hiddenByTheLine, 'the row still hides part of this line').toBeLessThanOrEqual(1);
    // And the value is never the run that gives way, in either case.
    expect(geometry.kick.hidden, 'the kick-off is the run being abbreviated, which is the wrong way round')
      .toBeLessThanOrEqual(1);

    if (nameMustGiveWay) {
      expect(
        geometry.name.hidden,
        'a name longer than the row has to be abbreviated; if it is not, something else gave way instead',
      ).toBeGreaterThan(1);
    } else {
      expect(
        geometry.name.hidden,
        'this name fits on a line of its own, so wrapping should have left it whole',
      ).toBeLessThanOrEqual(1);
    }
  });
}
