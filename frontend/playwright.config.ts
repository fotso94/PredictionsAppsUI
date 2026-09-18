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
      name: 'live',
      testMatch: /live\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});
