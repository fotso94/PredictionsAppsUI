import { test as base, expect } from '@playwright/test';
import { guardExternalAssets } from './external-assets';
import { assertPreflightPassed } from './preflight-token';

/**
 * `test` for the live project: Playwright's own, with every page of every test kept from waiting on
 * a third party's server.
 *
 * The live specs drive the real frontend against the real backend, and that is what they prove.
 * Club crests and the web font come from other people's servers and are not part of it, yet a
 * crest that did not answer for 45 s at 04:00 UTC on 2026-10-07 failed a save test waiting for the
 * page to go quiet, while the same CDN answered in 0.4 s minutes later. Crests and the font are
 * fetched for real here, at most once per worker and under a five-second deadline, with a valid
 * stand-in when they cannot be had in time (external-assets.ts).
 *
 * The routes are set on the context, so pages a test opens itself are covered too.
 *
 * Before any of that, once per worker: this run's isolation preflight must have passed
 * (preflight-token.ts). Every live and live-isolated spec uses this `test`, so a run that starts
 * them without playwright.config.ts's globalSetup - another configuration, `-c e2e/live`, watch or
 * UI mode after a refusal - fails here, before a browser, a request context or a beforeAll hook
 * has done anything.
 */
export const test = base.extend<{ externalAssets: void }, { isolationPreflight: void }>({
  // Playwright reads a fixture's dependencies from its first parameter's pattern: this one has none.
  // eslint-disable-next-line no-empty-pattern
  isolationPreflight: [async ({}, use) => {
    assertPreflightPassed('live-test.ts, before the first live test of this worker');
    await use();
  }, { scope: 'worker', auto: true }],
  externalAssets: [async ({ context }, use) => {
    await guardExternalAssets(context, 'real');
    await use();
  }, { auto: true }],
});

export { expect };
