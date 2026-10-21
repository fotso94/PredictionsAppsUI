import http from 'node:http';
import https from 'node:https';
import type { FullConfig } from '@playwright/test';
import { BrowserPolicy, Refusal, origin, stageA } from './target-policy';

/**
 * The browser tests' isolation preflight: Stage A (pure, target-policy.ts) and, for live-isolated
 * only and only once Stage A is clean, Stage B against the isolated pair and nothing else.
 *
 * Playwright runs a global setup before it loads a single spec file (and before any worker
 * starts), so a refusal here means no test module was imported and no test ran. It does run after
 * Playwright empties the output directory, and it does not run for `--list`.
 *
 * STAGE B, in this order, each step only if the one before it passed:
 *  B1. Exactly one GET to <isolated API>/health, over node:http to that address, no agent, no
 *      proxy, no redirect followed, a 5 s timeout and a 64 KB cap. It must say it serves an approved
 *      isolated database (and no live one), that EVERY Redis database it opens - the default
 *      client's and the six roles' (`redis_databases`) - is one of the isolated pair's and none of
 *      the live instance's, on that Redis server (`redis_server`: its port, and that it is this
 *      machine), and that its scheduler is off. A field it does not publish is a refusal: a backend
 *      that cannot say is a backend on older code.
 *  B2. Which backend the isolated frontend really calls. Its VITE_API_BASE_URL lives in a gitignored
 *      file (frontend/.env.dev8001.local); without it `vite --mode dev8001` falls back to
 *      frontend/.env and calls :8000. So the frontend is loaded once in a headless browser whose
 *      every request is aborted IN THE BROWSER except the frontend's own non-API files: the API call
 *      it makes is recorded, never sent, and its origin must be the isolated API's.
 *
 * Every refusal states what was sent: "nothing was sent to any server", or the one GET.
 */

export interface Timeouts { healthMs: number; navigationMs: number; firstApiCallMs: number }
export interface PreflightResult { ok: boolean; refusals: Refusal[]; operations: string[]; lines: string[] }

const DEFAULT_TIMEOUTS: Timeouts = { healthMs: 5_000, navigationMs: 15_000, firstApiCallMs: 15_000 };
const HEALTH_LIMIT = 64 * 1024;
const RESTART = 'restart the isolated backend on the current code (scripts/local-servers.sh stop backend-isolated, '
  + 'then start isolated)';

interface Answer { status?: number; body?: unknown; error?: string; location?: string }

function getHealth(apiUrl: string, timeoutMs: number): Promise<Answer> {
  const parsed = new URL(apiUrl);
  const bare = parsed.hostname.replace(/^\[|\]$/g, '');
  const host = bare === 'localhost' || bare === '0.0.0.0' ? '127.0.0.1' : bare;
  const lib = parsed.protocol === 'https:' ? https : http;
  return new Promise((resolve) => {
    let settled = false;
    const done = (answer: Answer) => { if (!settled) { settled = true; resolve(answer); } };
    const request = lib.request({
      host, port: Number(parsed.port || (parsed.protocol === 'https:' ? 443 : 80)), path: '/health', method: 'GET',
      agent: false, timeout: timeoutMs, headers: { accept: 'application/json', host: parsed.host },
    }, (response) => {
      const chunks: Buffer[] = [];
      let size = 0;
      response.on('data', (chunk: Buffer) => {
        size += chunk.length;
        if (size > HEALTH_LIMIT) {
          done({ error: 'its answer is larger than 64 KB' });
          request.destroy();
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => {
        let body: unknown;
        try {
          body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        } catch {
          body = undefined;
        }
        done({ status: response.statusCode, body, location: response.headers.location });
      });
      response.on('error', () => done({ error: 'its answer was cut off' }));
    });
    request.on('timeout', () => { done({ error: `no answer within ${timeoutMs} ms` }); request.destroy(); });
    request.on('error', (err: NodeJS.ErrnoException) => done({ error: err.code || 'the connection failed' }));
    request.end();
  });
}

const span = (values: number[]) => {
  const v = [...values].sort((a, b) => a - b);
  return v.length > 2 && v[v.length - 1] - v[0] === v.length - 1 ? `${v[0]}-${v[v.length - 1]}` : v.join(',');
};

/** B1. One GET, judged field by field. */
async function probeIsolatedBackend(apiUrl: string, policy: BrowserPolicy, operations: string[], timeouts: Timeouts):
  Promise<{ refusals: Refusal[]; facts: string | null }> {
  operations.push(`GET ${apiUrl}/health`);
  const answer = await getHealth(apiUrl, timeouts.healthMs);
  const refusals: Refusal[] = [];
  if (answer.error) {
    return { refusals: [{ code: 'health-unreadable', message: `the isolated backend ${apiUrl} did not answer GET /health `
      + `(${answer.error}); start the isolated pair first (scripts/local-servers.sh start isolated)` }], facts: null };
  }
  if (answer.status !== 200 || !answer.body || typeof answer.body !== 'object' || Array.isArray(answer.body)) {
    const redirect = answer.status && answer.status >= 300 && answer.status < 400 ? ' (a redirect, which is not followed)' : '';
    return { refusals: [{ code: 'health-unreadable', message: `the isolated backend ${apiUrl} answered GET /health with `
      + `HTTP ${answer.status}${redirect}${answer.body === undefined ? ' and no JSON' : ''}` }], facts: null };
  }
  const body = answer.body as Record<string, unknown>;
  const missing = (field: string) => refusals.push({ code: 'missing-field', message: `the backend at ${apiUrl} does not `
    + `publish \`${field}\` in GET /health, so what it uses cannot be established; ${RESTART}` });

  const database = body.database;
  if (typeof database !== 'string') {
    missing('database');
  } else if (policy.live.databases.includes(database)) {
    refusals.push({ code: 'live-database', message: `the backend at ${apiUrl} serves ${database}, a live database; `
      + 'live-isolated writes what it cannot remove and never runs against it' });
  } else if (!policy.isolated.databases.includes(database)) {
    refusals.push({ code: 'unapproved-database', message: `the backend at ${apiUrl} serves ${database}, which is not an `
      + `approved isolated database (${policy.isolated.databases.join(', ')})` });
  }
  const server = body.redis_server as { port?: unknown; loopback?: unknown } | null | undefined;
  const serverOk = !!server && typeof server === 'object' && Number.isInteger(server.port) && typeof server.loopback === 'boolean';
  if (!serverOk) {
    missing('redis_server');
  } else if (server!.port !== policy.isolated.redisPort || server!.loopback !== true) {
    refusals.push({ code: 'unapproved-redis', message: `the backend at ${apiUrl} uses Redis on port ${String(server!.port)}`
      + `${server!.loopback ? '' : ' on another machine'}; the isolated pair's Redis is this machine's :${policy.isolated.redisPort}` });
  }
  const dbs = body.redis_databases;
  if (!Array.isArray(dbs) || !dbs.length || !dbs.every((d) => Number.isInteger(d))) {
    missing('redis_databases');
  } else {
    const onLiveServer = serverOk && server!.port === policy.live.redisPort;
    const live = onLiveServer ? (dbs as number[]).filter((d) => policy.live.redisDatabases.includes(d)) : [];
    const outside = (dbs as number[]).filter((d) => !policy.isolated.redisDatabases.includes(d) && !live.includes(d));
    if (live.length) {
      refusals.push({ code: 'live-redis', message: `the backend at ${apiUrl} opens Redis database(s) ${span(live)} on the `
        + `live instance's server, which are the live databases (${span(policy.live.redisDatabases)}); every database it `
        + `opens - REDIS_DB included - must be one of ${span(policy.isolated.redisDatabases)}` });
    }
    if (outside.length) {
      refusals.push({ code: 'unapproved-redis', message: `the backend at ${apiUrl} opens Redis database(s) ${span(outside)}, `
        + `outside the isolated pair's ${span(policy.isolated.redisDatabases)}` });
    }
  }
  if (typeof body.scheduler_enabled !== 'boolean') {
    missing('scheduler_enabled');
  } else if (body.scheduler_enabled) {
    refusals.push({ code: 'scheduler-on', message: `the backend at ${apiUrl} runs its scheduler, which spends provider `
      + 'allowance and writes on its own; the isolated backend runs with SYNC_SCHEDULER_ENABLED=false' });
  }
  const facts = refusals.length ? null
    : `database ${String(database)}, Redis databases ${span(dbs as number[])} on this machine's :${String(server!.port)}, scheduler off`;
  return { refusals, facts };
}

/** B2. Load the isolated frontend once, with everything but its own files aborted in the browser. */
async function probeIsolatedFrontend(baseUrl: string, apiUrl: string, operations: string[], timeouts: Timeouts):
  Promise<{ refusals: Refusal[]; observed: string | null }> {
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch();
  // Written from inside the route handler, so kept in an object rather than a narrowed local.
  const seen: { first: string | null } = { first: null };
  let note = '';
  try {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    const own = new URL(baseUrl).origin;
    let announce: (value: string) => void = () => {};
    const firstCall = new Promise<string>((resolve) => { announce = resolve; });
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.origin === own && !url.pathname.startsWith('/api/')) return route.continue();
      if (url.pathname.startsWith('/api/v1/') && seen.first === null) {
        seen.first = `${url.protocol}//${url.host}`;
        announce(seen.first);
      }
      return route.abort('blockedbyclient');
    });
    const page = await context.newPage();
    for (const path of ['/', '/matches']) {
      try {
        await page.goto(`${baseUrl}${path}`, { waitUntil: 'domcontentloaded', timeout: timeouts.navigationMs });
      } catch {
        if (path === '/') {
          note = ' (it did not load)';
          break;
        }
      }
      const called = await Promise.race([firstCall, new Promise<null>((r) => setTimeout(() => r(null), timeouts.firstApiCallMs))]);
      if (called) break;
    }
  } finally {
    await browser.close();
  }
  const observed = seen.first;
  operations.push(`browser: loaded ${baseUrl}/ with every API request aborted in the browser${note}`
    + (observed ? ` (its first API call was to ${observed})` : ''));
  if (note) {
    return { refusals: [{ code: 'frontend-unreachable', message: `the isolated frontend ${baseUrl} did not load; start the `
      + 'isolated pair first (scripts/local-servers.sh start isolated)' }], observed };
  }
  if (!observed) {
    return { refusals: [{ code: 'frontend-unverified', message: `the isolated frontend ${baseUrl} made no API call within `
      + `${timeouts.firstApiCallMs} ms on / or /matches, so which backend it calls cannot be established` }], observed };
  }
  if (origin(observed) !== origin(apiUrl)) {
    return { refusals: [{ code: 'frontend-calls-other-backend', message: `the isolated frontend ${baseUrl} calls ${observed}, `
      + `not the isolated API ${apiUrl}: its VITE_API_BASE_URL (frontend/.env.dev8001.local, gitignored) is missing or wrong, `
      + 'and without it vite falls back to frontend/.env (:8000). The call was aborted in the browser.' }], observed };
  }
  return { refusals: [], observed };
}

export function createBrowserPreflight(policy: BrowserPolicy, timeouts: Partial<Timeouts> = {}) {
  const limits = { ...DEFAULT_TIMEOUTS, ...timeouts };

  async function check(env: Record<string, string | undefined>, projects: string[]): Promise<PreflightResult> {
    const operations: string[] = [];
    const { refusals, plan } = stageA(env, policy, projects);
    let isolatedFacts: string | null = null;
    let observed: string | null = null;
    const isolated = plan.find((p) => p.project === 'live-isolated');
    if (!refusals.length && isolated?.api) {
      const backend = await probeIsolatedBackend(isolated.api, policy, operations, limits);
      refusals.push(...backend.refusals);
      isolatedFacts = backend.facts;
      if (!refusals.length) {
        const frontend = await probeIsolatedFrontend(isolated.frontend, isolated.api, operations, limits);
        refusals.push(...frontend.refusals);
        observed = frontend.observed;
      }
    }
    const sent = operations.length ? `only this was sent: ${operations.join('; ')}` : 'nothing was sent to any server';
    const lines: string[] = [];
    if (refusals.length) {
      lines.push(`isolation preflight: REFUSED - ${refusals.length} problem(s); no test was loaded or started`);
      refusals.forEach((r, i) => lines.push(`  ${i + 1}. [${r.code}] ${r.message}`));
      lines.push(`  (${sent})`);
      lines.push('  How to run: npm run e2e:mocked; npm run e2e:live-isolated (sets E2E_STACK=live-isolated and the '
        + 'isolated URLs); E2E_STACK=live for the live project. The allowlist is backend/app/core/isolation_targets.json.');
    } else {
      lines.push(`isolation preflight: PASS (policy sha256 ${policy.sha256.slice(0, 12)})`);
      const mocked = plan.filter((p) => p.api === null);
      if (mocked.length) {
        lines.push(`  ${mocked.map((p) => p.project).join(', ')}: frontend ${mocked[0].frontend}; every /api/v1 call is answered by the stubs`);
      }
      for (const p of plan.filter((q) => q.project === 'live')) {
        lines.push(`  live: frontend ${p.frontend}, API ${p.api} (the main pair; not contacted by the preflight)`);
      }
      if (isolated) {
        lines.push(`  live-isolated: frontend ${isolated.frontend} calls ${observed} (observed); backend ${isolated.api}: ${isolatedFacts}`);
      }
      lines.push(`  (${sent})`);
    }
    return { ok: !refusals.length, refusals, operations, lines };
  }

  async function run(config: FullConfig): Promise<void> {
    const result = await check(process.env, config.projects.map((p) => p.name));
    const write = result.ok ? console.log : console.error;
    for (const line of result.lines) write(line);
    if (!result.ok) {
      const error = new Error('the isolation preflight refused this run (above); no test was loaded or started');
      error.stack = error.message;
      throw error;
    }
  }

  return { check, run };
}
