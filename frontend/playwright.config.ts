import { defineConfig, devices } from '@playwright/test';

/**
 * Two kinds of browser test, kept apart on purpose:
 *
 *  - `mocked`  — every backend response is stubbed from captured, sanitised payloads in e2e/fixtures.
 *                Deterministic, spends no provider allowance, and is where the edge cases live
 *                (missing markets, 1% probabilities, exhausted quota, provider errors, empty days).
 *  - `live`    — runs against the local backend and the data already in the local database. It
 *                reads, and it publishes only its own clearly-marked QA records. It never triggers
 *                a provider refresh, so it also spends no trial allowance.
 *
 * Both assume the local stack is already running:
 *   backend  http://127.0.0.1:8000   frontend  http://localhost:3100
 */
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3100';

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.artifacts',
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
    {
      name: 'mocked-desktop',
      testMatch: /mocked\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mocked-mobile',
      testMatch: /mocked\/.*\.spec\.ts/,
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
       * SCOPE. It runs a named list, not every mocked spec. Widening the testMatch to
       * /mocked\/.*\.spec\.ts is a one-line change and is where this should end up — but the rest
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
       */
      name: 'mocked-mobile-360',
      testMatch: /mocked\/(navigation-continuity|national-teams|overdue-results)\.spec\.ts/,
      use: { ...devices['Galaxy S8'] },
    },
    {
      name: 'live',
      testMatch: /live\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});
