import type { FullConfig } from '@playwright/test';
import { loadCommittedPolicy } from './support/target-policy';
import { createBrowserPreflight } from './support/isolation-preflight';
import { issuePreflightToken } from './support/preflight-token';

/**
 * playwright.config.ts's globalSetup: the browser tests' isolation preflight
 * (e2e/support/isolation-preflight.ts). Playwright runs it before it loads any spec file, so a
 * refusal here means no test module was imported and no test ran. The policy is the committed
 * backend/app/core/isolation_targets.json; a policy that cannot be read or trusted refuses too.
 *
 * Only after a PASS does it issue the run token (support/preflight-token.ts) that every worker of
 * this runner inherits and checks: a run that starts tests without this setup having passed - another
 * configuration, or watch / UI mode, which carry on after a failed global setup - is refused there.
 */
export default async function globalPreflight(config: FullConfig): Promise<void> {
  let policy;
  try {
    policy = loadCommittedPolicy();
  } catch (error) {
    console.error(`isolation preflight: REFUSED - ${(error as Error).message}; nothing was sent to any server`);
    const refusal = new Error('the isolation preflight refused this run (above); no test was loaded or started');
    refusal.stack = refusal.message;
    throw refusal;
  }
  await createBrowserPreflight(policy).run(config);
  issuePreflightToken(policy.sha256);
}
