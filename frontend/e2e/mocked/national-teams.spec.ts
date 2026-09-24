import { test, expect, Page, Route, Request } from '@playwright/test';
import {
  ApiMatch, ApiTeamRef, Json, baseMatches, dayPayload, fixtureAt, localDay, registerAuthHandler,
  stubBackend,
} from '../support/api-stub';

/**
 * NATIONAL-TEAM FIXTURES, THROUGH THE JOURNEYS A READER ACTUALLY USES.
 *
 * A fixture in the database nobody can find, filter, follow or read is not a feature. The backend
 * stores national-team fixtures now, with a competition that knows its confederation and squad
 * category and teams whose scope separates a country's senior, women's and under-23 squads. This
 * file walks the whole of that from the outside: discovery, the filter, the match page, saving and
 * following, and a knockout tie's result — on the day's list and on the fixture's own page, in
 * English and in French, on a desktop viewport and on a phone.
 *
 * ── THIS FILE IS MOCKED, AND THAT IS A LIMIT ON WHAT IT PROVES ──────────────────────────────
 *
 * Every /api/v1 route is stubbed, so nothing here reaches a provider and no request allowance is
 * spent. What that buys is determinism: a knockout tie decided on penalties, a women's national
 * team beside its country's men's squad, and an international-break day with nothing but national
 * fixtures on it are all states the local database does not hold today, and none of them can be
 * conjured up by waiting.
 *
 * WHAT IT THEREFORE PROVES is the interface: given a payload of the shape the backend serves, the
 * reader can find the fixture, narrow to it, open it, save it, follow the country, and read the
 * result. WHAT IT CANNOT PROVE, and must never be read as proving, is that any provider actually
 * covers these competitions, or that a forecast exists for any national-team fixture. A mock is
 * evidence about our code and about nobody else's.
 *
 * THE PAYLOADS ARE THE BACKEND'S OWN SHAPE. The classification block below
 * (`is_national_team` / `confederation` / `squad_category`) and the teams' `team_scope` are copied
 * from what `GET /api/v1/matches?date=2026-09-23` really served for National Teams Friendlies on
 * the local stack — competition id 371, Azerbaijan v Tajikistan and Gibraltar v Sao Tome And
 * Principe, both 16:00 UTC — so a payload the backend cannot produce cannot make these pass.
 *
 * NOTHING HERE IS A WAGER. Saving and following are bookmarks. No assertion stakes, scores or
 * settles anything.
 */

const LANGUAGE_KEY = 'sp.language.v1';

/** Put the reader's stored language in place before the application's own scripts run. */
async function seedLanguage(page: Page, language: 'en' | 'fr'): Promise<void> {
  await page.addInitScript(
    ([key, value]) => { window.localStorage.setItem(key, value); },
    [LANGUAGE_KEY, language] as const,
  );
}

const bodyText = (page: Page): Promise<string> =>
  page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));

/**
 * The page's whole text, as an AUTO-RETRYING assertion target.
 *
 * `bodyText` above reads once, and a one-shot read taken right after a navigation can catch the
 * shell with the content still to paint — `networkidle` is the network going quiet, not React
 * having drawn. That is a false failure on a phone and, for a `not.toContain`, a false PASS on
 * anything. Use `bodyText` where the read is genuinely after something already asserted; use this
 * where the page may still be arriving.
 */
const body = (page: Page) => page.locator('body');

/** The document must never scroll sideways, at any width. Measured, not eyeballed. */
const horizontalOverflow = (page: Page): Promise<number> => page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
);

/* ------------------------------------------------------------------------- the competitions */

interface ApiCompetition extends Json {
  id: string;
  key: string;
  name: string;
  country: string;
  country_code: string;
  logo: string;
  is_cup: boolean;
  providers: Record<string, string>;
  is_national_team: boolean;
  confederation: string | null;
  squad_category: string | null;
}

/**
 * National Teams Friendlies, exactly as the backend serialised it on 2026-09-23.
 *
 * `country: "World"` is the confederation's territory standing in for a country the competition
 * does not have — it is a fact about the competition and says nothing about any team in it, which
 * is why the teams below carry a scope instead.
 */
const FRIENDLIES: ApiCompetition = {
  id: 'd903b640-cb51-436e-b975-c6c62bd44e0e',
  key: 'national_teams_friendlies',
  name: 'National Teams Friendlies',
  country: 'World',
  country_code: 'WLD',
  logo: '/leagues/default.svg',
  is_cup: true,
  providers: { livescore: '371' },
  is_national_team: true,
  confederation: 'FIFA',
  squad_category: 'senior_men',
};

/**
 * The longest competition name in the catalogue, and the one the layout has to survive.
 *
 * "World Cup CONCACAF Qualifiers" is 29 characters against "Arsenal" at 7, and it is a real
 * canonical entry rather than a name invented to be long.
 */
const CONCACAF_QUALIFIERS: ApiCompetition = {
  ...FRIENDLIES,
  id: 'comp-concacaf-qualifiers',
  key: 'world_cup_qualifiers_concacaf',
  name: 'World Cup CONCACAF Qualifiers',
  country: 'North America',
  country_code: 'NCA',
  providers: { livescore: '404' },
  confederation: 'CONCACAF',
};

/** A women's competition: same countries, a different squad, and a different set of team rows. */
const WOMENS_WORLD_CUP: ApiCompetition = {
  ...FRIENDLIES,
  id: 'comp-womens-world-cup',
  key: 'womens_world_cup',
  name: "Women's World Cup",
  providers: { livescore: '412' },
  squad_category: 'senior_women',
};

/**
 * A club competition CARRYING THE CLASSIFICATION, which is what the backend serves now.
 *
 * The captured payloads in e2e/fixtures predate these three fields and so are the "not stated"
 * case, which is tested on its own further down. A mixed day needs the stated case on both sides,
 * because "this is club football" and "nobody said" are different answers and only one of them
 * puts a fixture under the Clubs filter.
 */
const PREMIER_LEAGUE: ApiCompetition = {
  id: '6a327af8-6d2e-4bc4-b325-0e7106884f35',
  key: 'premier_league',
  name: 'Premier League',
  country: 'England',
  country_code: 'ENG',
  logo: '/leagues/default.svg',
  is_cup: false,
  providers: { livescore: '2' },
  is_national_team: false,
  confederation: 'UEFA',
  squad_category: 'senior_men',
};

/* ------------------------------------------------------------------------------- the teams */

/** A team row with the scope that says which squad it is. */
const squad = (id: string, name: string, scope: string, country = 'Unknown'): ApiTeamRef => ({
  id,
  name,
  short_name: name,
  logo: '/teams/default.svg',
  // The country the PROVIDER spelled, which is what `upsert_team` stores for a national squad --
  // it declines the competition's confederation territory, not the team's own country. So both of
  // Spain's squads carry "Spain" here, which is the point: the country cannot tell them apart and
  // only `team_scope` can. A payload with a null country would be one the backend never produces
  // and would let these tests pass on a distinction the real data does not offer.
  country,
  team_scope: scope,
});

const SPAIN_MEN = squad('team-spain-men', 'Spain', 'national_senior_men', 'Spain');
const SPAIN_WOMEN = squad('team-spain-women', 'Spain', 'national_senior_women', 'Spain');
const PORTUGAL = squad('team-portugal', 'Portugal', 'national_senior_men');
const URUGUAY = squad('team-uruguay', 'Uruguay', 'national_senior_men');

/* ---------------------------------------------------------------------------- the fixtures */

/** One fixture in one competition, built on the captured shape so nothing else drifts. */
function fixture(
  id: string, competition: ApiCompetition, home: ApiTeamRef, away: ApiTeamRef, kickoffUtc: string,
): ApiMatch {
  const match = fixtureAt(kickoffUtc, home.name, away.name, id);
  match.competition = competition;
  match.home = { ...home };
  match.away = { ...away };
  match.status = 'scheduled';
  match.score = null;
  match.venue = null;
  return match;
}

/** Azerbaijan v Tajikistan — a real friendly, named as the provider names it. */
const friendly = (isoDate: string): ApiMatch => fixture(
  'national-friendly-aze-tjk', FRIENDLIES,
  squad('team-azerbaijan', 'Azerbaijan', 'national_senior_men'),
  squad('team-tajikistan', 'Tajikistan', 'national_senior_men'),
  `${isoDate}T16:00:00Z`,
);

/** Gibraltar v Sao Tome And Principe — the longest team name the provider gave us that day. */
const longNames = (isoDate: string): ApiMatch => fixture(
  'national-friendly-gib-stp', FRIENDLIES,
  squad('team-gibraltar', 'Gibraltar', 'national_senior_men'),
  squad('team-sao-tome', 'Sao Tome And Principe', 'national_senior_men'),
  `${isoDate}T16:00:00Z`,
);

/** A qualifier, for the longest competition name. */
const qualifier = (isoDate: string): ApiMatch => fixture(
  'national-qualifier-crc-pan', CONCACAF_QUALIFIERS,
  squad('team-costa-rica', 'Costa Rica', 'national_senior_men'),
  squad('team-panama', 'Panama', 'national_senior_men'),
  `${isoDate}T23:00:00Z`,
);

/** Spain's women's squad, which is a different row from Spain. */
const womensFixture = (isoDate: string): ApiMatch => fixture(
  'national-womens-esp-por', WOMENS_WORLD_CUP, SPAIN_WOMEN,
  squad('team-portugal-women', 'Portugal', 'national_senior_women'),
  `${isoDate}T18:00:00Z`,
);

/** A club row, which carries a country where a national team carries a squad. */
const club = (id: string, name: string): ApiTeamRef => ({
  id, name, short_name: name, logo: '/teams/default.svg', country: 'England',
  team_scope: 'club_senior_men',
});

/** A club fixture that SAYS it is a club fixture. */
const clubFixture = (isoDate: string): ApiMatch => fixture(
  'club-arsenal-everton', PREMIER_LEAGUE,
  club('team-arsenal', 'Arsenal'), club('team-everton', 'Everton'), `${isoDate}T14:00:00Z`,
);

/** A second one, so "the club fixtures are still here" is more than one row. */
const secondClubFixture = (isoDate: string): ApiMatch => fixture(
  'club-spurs-chelsea', PREMIER_LEAGUE,
  club('team-spurs', 'Tottenham Hotspur'), club('team-chelsea', 'Chelsea'), `${isoDate}T11:30:00Z`,
);

/**
 * A knockout tie that finished 0-0 after 90 minutes and was won 4-3 on penalties.
 *
 * The scoreline people remember and the scoreline every market settles on are different numbers
 * here, which is the whole reason the periods travel separately. Both are asserted.
 */
function penaltiesTie(isoDate: string): ApiMatch {
  const match = fixture(
    'national-tie-por-uru', CONCACAF_QUALIFIERS, PORTUGAL, URUGUAY, `${isoDate}T20:00:00Z`,
  );
  match.status = 'finished';
  match.score = {
    home: 0, away: 0, ht_home: 0, ht_away: 0, ft_home: 0, ft_away: 0,
    et_home: 0, et_away: 0, ps_home: 4, ps_away: 3,
  } as Json;
  return match;
}

/** A day with both kinds on it: two club fixtures and three national ones. */
const mixedDay = (isoDate: string): ApiMatch[] => [
  clubFixture(isoDate),
  secondClubFixture(isoDate),
  friendly(isoDate),
  longNames(isoDate),
  qualifier(isoDate),
];

/** The international break: the only football stored for the day is national-team football. */
const breakDay = (isoDate: string): ApiMatch[] => [friendly(isoDate), longNames(isoDate)];

/* --------------------------------------------------------------------------- the stubbed world */

interface World {
  matches: ApiMatch[];
  /** Team ids this reader follows, as the server would hold them. */
  followedTeamIds: string[];
  /** Match ids this reader has saved. */
  savedMatchIds: string[];
  /** Team rows `GET /teams/{id}` can answer with. */
  teams: ApiTeamRef[];
}

const reader = (role: 'regular' | 'expert' = 'regular') => ({
  user_id: '00000000-0000-4000-8000-0000000000a1',
  email: 'qa.national@predictions-local.dev',
  full_name: role === 'expert' ? 'QA Expert' : 'QA National',
  role,
  is_active: true,
  is_verified: true,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-05T09:00:00Z',
});

/** Opaque strings that never leave the browser context; they unlock nothing. */
const ACCESS_TOKEN = 'e2e-national-access-token';
const REFRESH_TOKEN = 'e2e-national-refresh-token';

async function signInReader(page: Page, role: 'regular' | 'expert' = 'regular'): Promise<void> {
  const user = reader(role);
  await page.addInitScript(({ access, refresh }) => {
    window.localStorage.setItem('access_token', access);
    window.localStorage.setItem('refresh_token', refresh);
  }, { access: ACCESS_TOKEN, refresh: REFRESH_TOKEN });

  const handler = (route: Route, request: Request): Promise<void> => {
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/auth/, '');
    if (path === '/me') return json(user);
    if (path === '/login' || path === '/register') {
      return json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer', user });
    }
    if (path === '/refresh') return json({ access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN, token_type: 'bearer' });
    if (path === '/logout') return json({ message: 'Logged out successfully' });
    return json({ detail: 'Not found' }, 404);
  };
  registerAuthHandler(page, handler);
  await page.route('**/api/v1/auth/**', handler);
}

/** The account endpoints, registered AFTER stubBackend so Playwright reaches these first. */
async function stubAccount(page: Page, world: World): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  const savedRows = () => world.savedMatchIds
    .map(id => world.matches.find(match => match.id === id))
    .filter((match): match is ApiMatch => Boolean(match))
    .map(match => ({ match_id: match.id, note: null, saved_at: new Date().toISOString(), updated_at: null, match }));

  const savedMatches = () => {
    const rows = savedRows();
    const finished = rows.filter(row => row.match.status === 'finished');
    const live = rows.filter(row => row.match.status === 'live' || row.match.status === 'halftime');
    const upcoming = rows.filter(row => !finished.includes(row) && !live.includes(row));
    return {
      upcoming, live, finished,
      counts: { upcoming: upcoming.length, live: live.length, finished: finished.length, total: rows.length },
    };
  };

  const favourites = () => ({
    teams: world.followedTeamIds
      .map(id => world.teams.find(team => team.id === id))
      .filter((team): team is ApiTeamRef => Boolean(team)),
    leagues: [],
    team_ids: [...world.followedTeamIds],
    league_ids: [],
    unresolved: { teams: [], leagues: [] },
    limits: { teams: 10, leagues: 5 },
    saved_matches: savedMatches(),
  });

  await page.route('**/api/v1/me/**', async (route: Route, request: Request) => {
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1\/me/, '');
    const method = request.method();

    if (path === '/favourites') return json(route, favourites());
    if (path === '/saved-matches') return json(route, savedMatches());

    const followTeam = /^\/favourites\/teams\/(.+)$/.exec(path);
    if (followTeam) {
      const id = decodeURIComponent(followTeam[1]);
      const following = method === 'PUT';
      world.followedTeamIds = following
        ? [...new Set([...world.followedTeamIds, id])]
        : world.followedTeamIds.filter(entry => entry !== id);
      return json(route, {
        kind: 'team', id, following, changed: true, ids: [...world.followedTeamIds], limit: 10,
      });
    }

    const save = /^\/saved-matches\/(.+)$/.exec(path);
    if (save) {
      const id = decodeURIComponent(save[1]);
      if (method === 'DELETE') {
        world.savedMatchIds = world.savedMatchIds.filter(entry => entry !== id);
        return json(route, { match_id: id, removed: true });
      }
      world.savedMatchIds = [...new Set([...world.savedMatchIds, id])];
      const match = world.matches.find(entry => entry.id === id) ?? null;
      return json(route, {
        match_id: id, note: null, saved_at: new Date().toISOString(), updated_at: null,
        match, created: true,
      });
    }

    return json(route, {});
  });

  // `GET /teams/{id}`, so a country has a page to be followed from.
  await page.route(/\/api\/v1\/teams\/(?!search)[^/?#]+$/, (route: Route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '');
    const team = world.teams.find(entry => entry.id === id);
    if (!team) return json(route, { detail: 'Team not found' }, 404);
    const upcoming = world.matches.filter(
      match => (match.home as ApiTeamRef)?.id === id || (match.away as ApiTeamRef)?.id === id,
    );
    return json(route, { team, upcoming, recent: [] });
  });
}

/** Open a day of fixtures with the whole backend stubbed. Returns the world the stubs mutate. */
async function openDay(
  page: Page,
  matches: ApiMatch[],
  options: { signedIn?: boolean; url?: string; teams?: ApiTeamRef[] } = {},
): Promise<World> {
  const world: World = {
    matches,
    followedTeamIds: [],
    savedMatchIds: [],
    teams: options.teams ?? [],
  };
  await stubBackend(page, {
    day: date => dayPayload(date, matches.map(match => ({ ...match }))),
    matchById: id => matches.find(match => match.id === id) ?? null,
  });
  if (options.signedIn) {
    await signInReader(page);
    await stubAccount(page, world);
  }
  await page.goto(options.url ?? '/matches');
  await page.waitForLoadState('networkidle');
  return world;
}

/*
 * `dayPayload` rewrites every kick-off onto the requested date at 12:00 + index, which is what
 * the rest of the suite wants and is wrong for a test about a specific kick-off time. These
 * fixtures' own times are restored by handing the payload back untouched instead.
 */
async function openDayKeepingKickoffs(
  page: Page, matches: ApiMatch[], options: { url?: string } = {},
): Promise<void> {
  await stubBackend(page, {
    day: date => ({ ...dayPayload(date, []), date, matches: matches.map(match => ({ ...match })) }),
    matchById: id => matches.find(match => match.id === id) ?? null,
  });
  await page.goto(options.url ?? '/matches');
  await page.waitForLoadState('networkidle');
}

const kindOption = (page: Page, kind: 'all' | 'club' | 'national') =>
  page.locator(`[data-testid="kind-filter-option"][data-kind="${kind}"]`);

/* ══════════════════════════════════════════════════ 1. discovery, and the international break */

test('a national-team fixture appears on its date like any other, under its own competition', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  await expect(page.getByTestId('fixture-list')).toBeVisible();
  await expect(body(page), 'the friendly is missing from the day it kicks off on').toContainText('Azerbaijan');
  await expect(body(page)).toContainText('Tajikistan');
  // Its competition heads its own group, exactly as a club competition does.
  await expect(page.locator('[data-testid="fixture-group"]')
    .filter({ hasText: 'National Teams Friendlies' })).toHaveCount(1);
  // And the club fixtures on the same day are untouched.
  await expect(body(page)).toContainText('Arsenal');
});

test('an otherwise empty day shows its national-team fixtures, and says that is what they are', async ({ page }) => {
  const day = localDay();
  await openDay(page, breakDay(day));

  // THE PAYOFF. Before this, the six club competitions being in an international break produced
  // "No matches stored for this date" — true of the store, and read by everybody else as "there
  // is no football".
  await expect(page.getByTestId('matchday-empty')).toHaveCount(0);
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  const note = page.getByTestId('matchday-national-only');
  await expect(note).toBeVisible();
  await expect(note).toContainText('national-team fixtures');
  await expect(note).toContainText('No club fixture is stored for this date.');
});

test('the note is about the day and never appears on a day that has club football too', async ({ page }) => {
  await openDay(page, mixedDay(localDay()));
  await expect(page.getByTestId('matchday-national-only')).toHaveCount(0);
});

test('a day of fixtures that state no classification claims nothing and hides nothing', async ({ page }) => {
  // The captured payloads predate the classification, which is exactly what a cached response
  // from an older backend is. "Nobody said" must not be read as "club football".
  await openDay(page, baseMatches());

  await expect(page.getByTestId('fixture-list')).toBeVisible();
  await expect(page.getByTestId('matchday-national-only'),
    'an unclassified day was reported as an international break').toHaveCount(0);
  await expect(page.getByTestId('kind-filter'),
    'a filter was offered that could only ever empty this list').toHaveCount(0);
});

/* ════════════════════════════════════════════════════════════════════════════════ 2. the filter */

test('the club / national filter is offered on a day that holds both, and narrows to each', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  const filter = page.getByTestId('kind-filter');
  await expect(filter).toBeVisible();
  // Three alternatives, stated as a radio group rather than three independent toggles.
  await expect(filter).toHaveAttribute('role', 'radiogroup');
  await expect(kindOption(page, 'all')).toHaveAttribute('aria-checked', 'true');

  await kindOption(page, 'national').click();
  await expect(kindOption(page, 'national')).toHaveAttribute('aria-checked', 'true');
  await expect(body(page)).toContainText('Azerbaijan');
  await expect(body(page), 'a club fixture survived the national-teams filter').not.toContainText('Arsenal');

  await kindOption(page, 'club').click();
  await expect(body(page)).toContainText('Arsenal');
  await expect(body(page), 'a national-team fixture survived the clubs filter').not.toContainText('Azerbaijan');
});

test('the filter is in the URL, so a narrowed day is a link and survives Back', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  await kindOption(page, 'national').click();
  await expect(page).toHaveURL(/[?&]teams=national/);

  // Opening a fixture and coming back restores the list the reader left.
  await page.locator('[data-match-id="national-friendly-aze-tjk"] a').first().click();
  await page.waitForLoadState('networkidle');
  await page.goBack();
  await page.waitForLoadState('networkidle');
  await expect(kindOption(page, 'national')).toHaveAttribute('aria-checked', 'true');
  await expect(body(page)).not.toContainText('Arsenal');
});

test('a link that arrives with the filter set can always see it and take it off', async ({ page }) => {
  const day = localDay();
  // A day of national football only, reached with `teams=club` carried over from another day.
  // Nothing matches, and the one thing the reader needs is the control that did it.
  await openDay(page, breakDay(day), { url: '/matches?teams=club' });

  await expect(page.getByTestId('matchday-filtered-empty')).toBeVisible();
  await expect(page.getByTestId('kind-filter'),
    'the filter that emptied the list was not on screen').toBeVisible();
  await expect(kindOption(page, 'club')).toHaveAttribute('aria-checked', 'true');

  await kindOption(page, 'all').click();
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  await expect(body(page)).toContainText('Azerbaijan');
});

test('the filter sheet offers the same choice, and the summary chip removes it', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  await page.getByTestId('filter-sheet-open').click();
  const radio = page.locator('[data-testid="kind-filter-radio"][data-kind="national"]');
  await expect(radio).toBeVisible();
  await radio.check();
  await page.getByTestId('filter-sheet-apply').click();

  await expect(body(page)).not.toContainText('Arsenal');

  // Every active filter is its own removable chip — including this one.
  const chip = page.locator('[data-testid="active-filter-chip"]').filter({ hasText: 'National teams' });
  await expect(chip).toHaveCount(1);
  await chip.getByRole('button').click();
  await expect(body(page)).toContainText('Arsenal');
});

/* ═══════════════════════════════════════════════════════════════════════════ 3. the match page */

test('a national-team fixture opens, names its competition and says what is published for it', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  await page.locator('[data-match-id="national-friendly-gib-stp"] a').first().click();
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: 'Gibraltar' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Sao Tome And Principe' })).toBeVisible();
  await expect(body(page)).toContainText('National Teams Friendlies');
  // The fixture page renders; whether a forecast exists is the payload's business and the
  // evidence panel's sentence, not something this test may assert into existence.
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
});

/* ══════════════════════════════════════════════════════════ 4. following a country, and saving */

test('following a country does not follow its women\'s squad, which is a different row', async ({ page }) => {
  const day = localDay();
  const world = await openDay(page, [friendly(day), womensFixture(day)], {
    signedIn: true,
    teams: [SPAIN_MEN, SPAIN_WOMEN],
  });

  await page.goto(`/teams/${SPAIN_MEN.id}`);
  await page.waitForLoadState('networkidle');
  // The country's page says which squad it is, because "Spain" alone cannot.
  await expect(page.getByTestId('team-squad')).toHaveText('National team');
  await page.getByTestId('follow-button').first().click();
  await expect(page.getByTestId('follow-button').first()).toHaveAttribute('data-following', 'true');
  expect(world.followedTeamIds).toEqual([SPAIN_MEN.id]);

  await page.goto(`/teams/${SPAIN_WOMEN.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('team-squad')).toHaveText('Women\'s national team');
  await expect(
    page.getByTestId('follow-button').first(),
    'following Spain silently followed Spain Women as well',
  ).toHaveAttribute('data-following', 'false');
  expect(world.followedTeamIds).toEqual([SPAIN_MEN.id]);
});

test('the follow list tells two squads of one country apart, which their name cannot', async ({ page }) => {
  const day = localDay();
  const world = await openDay(page, [friendly(day), womensFixture(day)], {
    signedIn: true,
    teams: [SPAIN_MEN, SPAIN_WOMEN],
  });
  // Both followed, which is what a reader who wants both ends up with — and the state in which
  // the list is two rows reading "Spain" with nothing to choose between them.
  world.followedTeamIds = [SPAIN_MEN.id, SPAIN_WOMEN.id];

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  const rows = page.getByTestId('followed-team');
  await expect(rows).toHaveCount(2);
  const squads = await rows.getByTestId('followed-team-squad').allInnerTexts();
  expect(squads.sort()).toEqual(['National team', 'Women\'s national team']);
});

test('a national-team fixture can be saved from the day list, through the same star as any other', async ({ page }) => {
  const day = localDay();
  const world = await openDay(page, mixedDay(day), { signedIn: true });

  const row = page.locator('[data-match-id="national-friendly-aze-tjk"]');
  await expect(row).toBeVisible();
  await row.getByTestId('save-match-button').click();
  await expect.poll(() => world.savedMatchIds).toEqual(['national-friendly-aze-tjk']);
  await expect(row.getByTestId('save-match-button')).toHaveAttribute('aria-pressed', 'true');
});

/* ═══════════════════════════════════════════════════════════════════════ 5. expert publishing */

test('an expert picking a fixture to write about is offered the national-team ones too', async ({ page }) => {
  const day = localDay();
  const matches = mixedDay(day);
  await stubBackend(page, { day: date => dayPayload(date, matches.map(match => ({ ...match }))) });
  await signInReader(page, 'expert');

  await page.goto('/expert/match-selection');
  await page.waitForLoadState('networkidle');

  // The picker derives its competition list from the day's own fixtures and holds no allow-list
  // of competitions, so nothing had to change for this to work — which is the claim being made.
  const body = page.getByTestId('expert-match-selection');
  await expect(body).toContainText('National Teams Friendlies');
  await expect(body).toContainText('Azerbaijan');
  await expect(body).toContainText('Arsenal');
});

/* ══════════════════════════════════════════════════════════════════════════ 6. knockout results */

test('a tie won on penalties shows the scoreline people remember beside the one markets settle on', async ({ page }) => {
  const day = localDay();
  const tie = penaltiesTie(day);
  await openDay(page, [tie]);

  // On the row: the short form, because a full sentence pushes the countries off a phone.
  const row = page.locator(`[data-match-id="${tie.id}"]`);
  await expect(row.getByTestId('fixture-row-periods')).toContainText('4–3 pens');

  await row.locator('a').first().click();
  await page.waitForLoadState('networkidle');

  const scoreline = page.getByTestId('match-scoreline');
  await expect(scoreline).toContainText('0 - 0');
  // Two period lines, because this tie went to extra time AND to a shoot-out, and they answer
  // different questions: one says the goals took 120 minutes, the other says who went through.
  const periods = scoreline.getByTestId('match-score-period');
  await expect(periods).toHaveCount(2);
  await expect(periods.nth(0)).toHaveText('After extra time');
  await expect(periods.nth(1)).toHaveText('4–3 on penalties');
  // The shoot-out is never the scoreline: settlement scores this tie as the draw it was.
  expect(await bodyText(page)).not.toMatch(/\b4\s*-\s*3\b/);
});

/* ═══════════════════════════════════════════════════════════════════════════════ 7. both languages */

test('everything this feature says is in French for a reader who chose French', async ({ page }) => {
  await seedLanguage(page, 'fr');
  const day = localDay();
  await openDay(page, breakDay(day));

  const note = page.getByTestId('matchday-national-only');
  await expect(note).toContainText('sélections nationales');
  await expect(note).toContainText('Aucun match de club');
  // The competition's name is the provider's and is never translated.
  await expect(body(page)).toContainText('National Teams Friendlies');
  // No English from the same catalogue entry may survive into a French page.
  expect(await bodyText(page)).not.toMatch(/national-team fixtures|No club fixture/i);
});

test('the filter and the squad note are in French too', async ({ page }) => {
  await seedLanguage(page, 'fr');
  const day = localDay();
  await openDay(page, mixedDay(day));

  await expect(kindOption(page, 'national')).toContainText('Sélections');
  await expect(kindOption(page, 'club')).toContainText('Clubs');
  expect(await bodyText(page)).not.toMatch(/National teams/);
});

test('a country\'s squad is named in French on the team page', async ({ page }) => {
  await seedLanguage(page, 'fr');
  const day = localDay();
  await openDay(page, [womensFixture(day)], { signedIn: true, teams: [SPAIN_WOMEN] });

  await page.goto(`/teams/${SPAIN_WOMEN.id}`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('team-squad')).toHaveText('Sélection nationale féminine');
});

/* ══════════════════════════════════════════════════════════════════════ 8. the reader's clock */

test('a national-team kick-off is shown in the reader\'s own zone, not UTC', async ({ page }) => {
  const day = localDay();
  // 16:00 UTC is 12:00 in America/New_York, the zone this project runs in.
  await openDayKeepingKickoffs(page, [friendly(day)]);

  const row = page.locator('[data-match-id="national-friendly-aze-tjk"]');
  await expect(row).toContainText('12:00');
  await expect(row, 'the kick-off was left on UTC').not.toContainText('16:00');
});

/* ════════════════════════════════════════════════════════════ 9. the width of a country's name */

test('the longest competition and country names do not push the page sideways', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));

  // "World Cup CONCACAF Qualifiers" and "Sao Tome And Principe" are both on this page, and the
  // project this runs under decides the width: 1440 on the desktop project, 390 on the phone.
  await expect(body(page)).toContainText('Sao Tome And Principe');
  await expect(body(page)).toContainText('World Cup CONCACAF Qualifiers');
  expect(await horizontalOverflow(page),
    'the document scrolls sideways with a long competition name on it').toBe(0);

  // With the filter on screen as well, which is the widest this row ever gets.
  await kindOption(page, 'national').click();
  expect(await horizontalOverflow(page)).toBe(0);
});

test('the match page for the longest names does not push the page sideways either', async ({ page }) => {
  const day = localDay();
  await openDay(page, mixedDay(day));
  await page.locator('[data-match-id="national-friendly-gib-stp"] a').first().click();
  await page.waitForLoadState('networkidle');

  expect(await horizontalOverflow(page)).toBe(0);
});

/* ══════════════════════════════════════════════════════ 10. the whole journey, in one sitting */

/**
 * ONE READER, ONE PASS: discovery → filter → match detail → save → the result.
 *
 * The tests above each hold one leg still so a failure names the leg. This one walks all of them
 * without letting go, because the failures a split suite cannot see are the ones between the
 * legs: a filter that survives into the fixture page's back link, a save made from a narrowed
 * list that is lost when the list is restored, a result that reads differently arrived at from
 * the day than opened directly.
 *
 * It runs on every project this file runs under, so the same walk is made at 1440, at 390 and at
 * 360. Mocked throughout — see the note at the top of this file for what that does and does not
 * establish.
 */
test('the whole journey: find it, narrow to it, open it, save it, read its result', async ({ page }) => {
  const day = localDay();
  const played = penaltiesTie(day);
  const matches = [...mixedDay(day), played];
  const world = await openDay(page, matches, { signedIn: true });

  // ── discovery ────────────────────────────────────────────────────────────────────────────
  await expect(page.getByTestId('fixture-list')).toBeVisible();
  await expect(body(page)).toContainText('Azerbaijan');

  // ── narrowing to national-team football ──────────────────────────────────────────────────
  await kindOption(page, 'national').click();
  await expect(page).toHaveURL(/[?&]teams=national/);
  await expect(body(page), 'a club fixture survived the filter').not.toContainText('Arsenal');

  // ── saving, from the narrowed list ───────────────────────────────────────────────────────
  const row = page.locator('[data-match-id="national-friendly-aze-tjk"]');
  await row.getByTestId('save-match-button').click();
  await expect.poll(() => world.savedMatchIds).toEqual(['national-friendly-aze-tjk']);

  // ── the fixture's own page, and back to the list as it was left ──────────────────────────
  await row.locator('a').first().click();
  await page.waitForLoadState('networkidle');
  // The fixture card paints after the detail request settles, which on a phone can be after
  // `networkidle` — so both of these have to be assertions that wait, not a single read.
  await expect(page.getByTestId('match-scoreline')).toBeVisible();
  await expect(body(page)).toContainText('National Teams Friendlies');

  await page.goBack();
  await page.waitForLoadState('networkidle');
  await expect(kindOption(page, 'national'),
    'the filter was lost coming back from the fixture').toHaveAttribute('aria-checked', 'true');
  await expect(row.getByTestId('save-match-button'),
    'the save made before opening the fixture was lost coming back').toHaveAttribute('aria-pressed', 'true');

  // ── the result, reached from the same narrowed list ──────────────────────────────────────
  const finished = page.locator(`[data-match-id="${played.id}"]`);
  await expect(finished.getByTestId('fixture-row-periods')).toContainText('4–3 pens');
  await finished.locator('a').first().click();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('match-scoreline')).toContainText('0 - 0');
  await expect(page.getByTestId('match-score-period').last()).toHaveText('4–3 on penalties');
});
