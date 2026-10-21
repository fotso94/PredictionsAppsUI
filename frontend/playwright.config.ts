import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';
import { assertPreflightPassed } from './e2e/support/preflight-token';
import { parseStack } from './e2e/support/target-policy';

/**
 * Two kinds of browser test, kept apart on purpose:
 *
 *  - `mocked`  — every backend response is stubbed from captured, sanitised payloads in e2e/fixtures.
 *                Deterministic, spends no provider allowance, and is where the edge cases live
 *                (missing markets, 1% probabilities, exhausted quota, provider errors, empty days).
 *  - `live`    — runs against the local backend and the data already in the local database, and
 *                NEVER SIGNS IN: two anonymous specs that read. It never triggers a provider
 *                refresh, so it also spends no trial allowance.
 *  - `live-isolated` — every live test that signs in as the QA account, and the one that records
 *                a slip. Signing in is a write path: the slip dock loads the reader's slips, and that
 *                read settles any pending leg whose fixture has a result and commits — which is how
 *                the five QA slips on the live database settled on 2026-10-10 during a `live` run
 *                (docs/evidence/journey-proof/live-settlement-2026-10-10.md). These specs therefore
 *                run only against the isolated pair, a clone of the live database behind a backend
 *                with the scheduler off and no provider credentials (docs/isolated-dev-environment.md;
 *                e2e/support/isolated.ts refuses anything else), where they publish their own
 *                clearly-marked QA records and remove them again.
 *
 * They assume the local stack is already running (scripts/local-servers.sh start all):
 *   backend  http://127.0.0.1:8000   frontend  http://localhost:3100
 *   isolated backend  http://127.0.0.1:8001   isolated frontend  http://localhost:3101
 *
 * WHICH PROJECTS EXIST. `live` exists only with E2E_STACK=live and `live-isolated` only with
 * E2E_STACK=live-isolated (any other value refuses the run as the config loads), so a bare
 * `playwright test` is mocked-only, `--project=live` without the opt-in is "project not found", and
 * the two real stacks can never run in one invocation:
 *   npm run e2e:mocked | npm run e2e:live | npm run e2e:live-isolated
 * The mocked projects exist in every stack but `live`: they share E2E_BASE_URL with it, and the
 * live frontend is the one frontend a mocked spec may never load its pages from.
 *
 * WHERE THE MOCKED PAGES COME FROM. The isolated frontend, http://localhost:3101, unless
 * E2E_BASE_URL names another one; never the live :3100, which serves the main checkout's code with
 * its API on the live backend, so that only a spec's page stubs stood between it and :8000 (the
 * preflight refuses it: 2026-10-21 review).
 *
 * WHICH SPECS A PROJECT RUNS. Its own directory (testDir), and nothing else. testMatch is tested
 * against the ABSOLUTE path, so the regular expressions this file had (/mocked\/.*\.spec\.ts/,
 * /live\/.*\.spec\.ts/) selected every spec under a checkout whose directory ends in "mocked" or
 * "live" - live-isolated's sign-in journeys included, against the mocked or the live frontend.
 *
 * BEFORE ANY TEST. globalSetup (e2e/global-preflight.ts) runs the isolation preflight before
 * Playwright loads a spec file: every target of every defined project is resolved and judged
 * against backend/app/core/isolation_targets.json, and for live-isolated the isolated backend's
 * GET /health and the isolated frontend's real API origin are checked. A refusal stops the run
 * with nothing sent anywhere, or after only that one GET. Never add a webServer entry here: it
 * would start a server before the preflight. A worker loading this file refuses to run any test
 * unless that preflight passed in its runner (e2e/support/preflight-token.ts): watch and UI mode
 * carry on after a failed global setup, and a configuration built on this one may drop it.
 */
const E2E = join(dirname(fileURLToPath(import.meta.url)), 'e2e');
const STACK = parseStack(process.env.E2E_STACK);
const BASE_URL = process.env.E2E_BASE_URL || (STACK === 'live' ? 'http://localhost:3100' : 'http://localhost:3101');
const ISOLATED_BASE_URL = process.env.E2E_ISOLATED_BASE_URL || 'http://localhost:3101';
/** Every spec of a project's own directory; a project never selects by a pattern over the whole path. */
const SPEC = /\.spec\.ts$/;

if (process.env.TEST_WORKER_INDEX) {
  assertPreflightPassed('playwright.config.ts, as this worker loaded it');
}

// A hint, from the runner process only: a live project asked for without its opt-in is reported by
// Playwright as "not found", which on its own does not say why.
if (!process.env.TEST_WORKER_INDEX) {
  const asked = process.argv.flatMap((arg, i, all) => (arg.startsWith('--project=') ? [arg.slice(10)]
    : arg === '--project' && all[i + 1] ? [all[i + 1]] : []));
  for (const project of asked.filter((name) => (name === 'live' || name === 'live-isolated') && name !== STACK)) {
    console.error(`hint: the ${project} project exists only with E2E_STACK=${project} (npm run e2e:${project})`);
  }
}

const mockedProjects = [
  {
    name: 'mocked-desktop',
    testDir: join(E2E, 'mocked'),
    testMatch: SPEC,
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
  },
  {
    name: 'mocked-mobile',
    testDir: join(E2E, 'mocked'),
    testMatch: SPEC,
    use: { ...devices['iPhone 13'] },
  },
  {
    /**
     * The narrowest phone this interface has to work on: Galaxy S8, 360x740, unmodified.
     *
     * 360px is where the header broke. The brand wrapped onto two lines, both account actions
     * and the menu button would not fit on one row, the menu button was clipped by the right
     * edge and the document scrolled sideways — so the one control that reaches every other page
     * could not be tapped. mocked-mobile is an iPhone 13 at 390px and passed throughout, which
     * is exactly why this needs a project of its own: thirty pixels is the entire difference
     * between the two, and 360 is what a Galaxy S-series, a Pixel "a" in a font-scaled profile
     * and most budget Androids report.
     *
     * SCOPE. It runs a named list, not every mocked spec. Widening the testMatch to SPEC
     * (every spec in its testDir) is a one-line change and is where this should end up — but the rest
     * of the mocked suite has never been run at 360, so turning it all on in the same commit
     * would mix "the header is fixed" with an unknown number of unrelated failures in files
     * owned by other people. Run the mocked suite at 360 first, then widen it.
     *
     * overdue-results.spec.ts joins it because the words it puts on a row are the longest any
     * fixture row carries — a whole sentence about a result that never arrived, in the column
     * that used to hold a five-character kickoff time, and in French as well — and 360 is the
     * width where that either wraps cleanly or pushes the club names out of the row. The same
     * file also holds the live scores this must not suppress, so it is run at all three widths.
     *
     * national-teams.spec.ts joins it because 360 is where its subject matter breaks: a
     * competition called "World Cup CONCACAF Qualifiers" and a country called "Sao Tome And
     * Principe" are four and three times the width of "Arsenal", and the club/national control
     * shares a row with the competition chips. Both of those are new width, on the one strip
     * that already had to be taught not to overflow. It is added rather than the list being
     * widened because it is the file this package wrote and can vouch for at this width; the
     * rest of the suite is still unmeasured here.
     *
     * expert-management.spec.ts joins it because this is where its layout can break: the
     * expert's record grew a fifth tile and each My Predictions card a fourth action, and its
     * French labels are the longer ones. It measures sideways scroll, cut-short tile labels and
     * actions outside their card at whatever width it runs, and 360 is the one that binds.
     *
     * revision-history.spec.ts joins it for the same reason: an earlier version now shows every
     * market it carried, in labelled cells whose French labels (« Conviction déclarée », « Plus
     * de 2,5 ») are the longer ones, and a picker row can carry a two-line kicked-off badge. It
     * measures sideways scroll on the match page, both pickers and the composer.
     *
     * expert-composer-localisation.spec.ts joins it because the composer is where French runs
     * longest: whole validation sentences under 360px-wide fields, two badges side by side on a
     * picker row, and every optional market ticked at once. It walks each of those states for
     * English and measures sideways scroll in every one.
     */
    name: 'mocked-mobile-360',
    testDir: join(E2E, 'mocked'),
    testMatch: /[\\/](navigation-continuity|national-teams|overdue-results|parlay-builder|match-data-state|expert-management|revision-history|expert-composer-localisation)\.spec\.ts$/,
    use: { ...devices['Galaxy S8'] },
  },
].filter(() => STACK !== 'live');

const liveProjects = [
  {
    name: 'live',
    testDir: join(E2E, 'live'),
    testMatch: SPEC,
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
  },
].filter(() => STACK === 'live');

const isolatedProjects = [
  {
    name: 'live-isolated',
    testDir: join(E2E, 'live-isolated'),
    testMatch: SPEC,
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, baseURL: ISOLATED_BASE_URL },
  },
].filter(() => STACK === 'live-isolated');

export default defineConfig({
  testDir: E2E,
  outputDir: './e2e/.artifacts',
  globalSetup: './e2e/global-preflight.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: './e2e/.report', open: 'never' }]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    // A fixed timezone and clock keep the today/tomorrow assertions meaningful; individual tests
    // override the timezone to exercise UTC boundaries and daylight-saving transitions.
    timezoneId: 'America/New_York',
    locale: 'en-US',
  },
  projects: [
    ...mockedProjects,
    ...liveProjects,
    ...isolatedProjects,
  ],
});
