import { loadCommittedPolicy } from './target-policy';

/**
 * Proof, inside a worker, that this run's isolation preflight passed.
 *
 * WHY. The preflight is playwright.config.ts's globalSetup (e2e/global-preflight.ts), and a run can
 * start tests without it (2026-10-21 review):
 *  - any other configuration: `playwright test -c e2e/live` (a directory with no
 *    playwright.config.* makes Playwright build its default configuration, with no globalSetup and
 *    no E2E_STACK gate), or specs named from a directory with no configuration at all;
 *  - watch mode (PWTEST_WATCH): runWatchModeLoop in playwright/lib/runner awaits the global setup
 *    and drops its status, then runs tests on every change; UI mode lets a person run them as well.
 *
 * HOW. After a PASS, global-preflight.ts writes a token into the runner's environment: the
 * committed policy's sha256 and the runner's pid. Playwright forks every worker from the runner
 * with that environment (Playwright documents process.env from a global setup as reaching the
 * tests), so a worker holds a token whose pid is its own parent's. A worker without it, or with a
 * token from another process (one inherited from an outer run, say), refuses:
 *  - playwright.config.ts, as a worker loads it, refuses every test of the real configuration;
 *  - the live helpers (live-test.ts's worker fixture, qa-account.ts apiContext(), isolated.ts
 *    isolatedApiContext()) refuse at first use, which also covers a run that never loads
 *    playwright.config.ts. They check at first use, not at import, so `--list` keeps working.
 *
 * It is a guard against slips, not against someone who wants past it: it adds a check, it does not
 * replace the preflight, and the per-spec checks in isolated.ts still run after it.
 */

export const PREFLIGHT_TOKEN_KEY = 'E2E_ISOLATION_PREFLIGHT_TOKEN';

const tokenFor = (sha256: string, pid: number) => `${sha256}:${pid}`;

/** Called by global-preflight.ts after a PASS, in the runner process. */
export function issuePreflightToken(sha256: string): void {
  process.env[PREFLIGHT_TOKEN_KEY] = tokenFor(sha256, process.pid);
}

export class PreflightMissing extends Error {}

/** Throws unless this process is a worker of a runner whose preflight passed. */
export function assertPreflightPassed(where: string): void {
  let expected: string | null = null;
  try {
    expected = tokenFor(loadCommittedPolicy().sha256, process.ppid);
  } catch {
    expected = null;
  }
  if (expected !== null && process.env[PREFLIGHT_TOKEN_KEY] === expected) return;
  const error = new PreflightMissing(`REFUSED (${where}): the isolation preflight did not pass in this run, so nothing here `
    + 'may reach a server. Playwright started this test without playwright.config.ts\'s globalSetup '
    + '(e2e/global-preflight.ts) having passed in this runner: another --config or a directory given to -c, specs named '
    + 'from a directory with no configuration, or watch / UI mode after a refused preflight. Run npm run e2e:mocked, '
    + 'npm run e2e:live or npm run e2e:live-isolated.');
  error.stack = error.message;
  throw error;
}
