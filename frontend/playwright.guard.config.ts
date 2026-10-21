import { defineConfig } from '@playwright/test';

/**
 * The browser-test isolation preflight's own tests (e2e/guard), kept out of playwright.config.ts on
 * purpose: they test the preflight that config runs, so they must not depend on it, and they need
 * neither pair of servers. Stage A is pure; Stage B is driven against small fake servers started
 * by the tests themselves, through an injected policy, so nothing here reaches :8000, :8001,
 * :3100 or :3101.
 *
 * The other half of these tests, the refused runs of the REAL configuration, is
 * e2e/guard/refusal-runs.test.mjs (node --test): each of those starts a Playwright run of its own,
 * one after another, and a Playwright runner must not start them from inside another runner.
 *
 *   npm run e2e:guard      both, one after the other
 */
export default defineConfig({
  testDir: './e2e/guard',
  testMatch: /.*\.spec\.ts/,
  outputDir: './e2e/.guard-artifacts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [['list']],
  timeout: 60_000,
});
