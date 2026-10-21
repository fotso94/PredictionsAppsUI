import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { test, expect } from '@playwright/test';
import { BrowserPolicy, loadCommittedPolicy } from '../support/target-policy';
import { createBrowserPreflight } from '../support/isolation-preflight';

/**
 * Stage B of the browser-test isolation preflight, against fake servers started here.
 *
 * The committed policy names :8001/:3101 as the isolated pair and :8000/:3100 as the live one; these
 * tests inject a policy that names the fake servers' ports instead (createBrowserPreflight takes a
 * policy for exactly this), so the real pairs are never contacted. Every fake server records each
 * request it receives, which is how "exactly one GET" and "the frontend probe sends nothing to any
 * backend" are measured rather than assumed.
 */

interface Fake { url: string; port: number; hits: string[]; close: () => Promise<void> }

async function fakeServer(handler: (req: http.IncomingMessage, res: http.ServerResponse) => void): Promise<Fake> {
  const hits: string[] = [];
  const server = http.createServer((req, res) => {
    hits.push(`${req.method} ${req.url}`);
    handler(req, res);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`, port, hits,
    close: () => new Promise<void>((resolve) => { server.closeAllConnections(); server.close(() => resolve()); }),
  };
}

const HEALTHY = {
  status: 'healthy', database: 'soccer_predictions_e2e', redis_databases: [10, 11, 12, 13, 14, 15],
  redis_server: { port: 6379, loopback: true }, scheduler_enabled: false,
};

function json(body: unknown, status = 200) {
  return (_req: http.IncomingMessage, res: http.ServerResponse) => {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  };
}

/** A frontend whose bundle calls `api` - what the isolated frontend's VITE_API_BASE_URL decides. */
function frontendCalling(api: string | null) {
  return (_req: http.IncomingMessage, res: http.ServerResponse) => {
    res.writeHead(200, { 'content-type': 'text/html' });
    res.end(`<!doctype html><title>fake</title><script>
      ${api ? `fetch(${JSON.stringify(`${api}/api/v1/matches?date=today`)}).catch(() => {});` : ''}
    </script>`);
  };
}

let live: Fake;
let liveFrontend: Fake;
const opened: Fake[] = [];

test.beforeAll(async () => {
  live = await fakeServer(json({ database: 'soccer_predictions' }));   // stands in for :8000
  liveFrontend = await fakeServer(frontendCalling(null));               // stands in for :3100
});

test.afterAll(async () => {
  await live.close();
  await liveFrontend.close();
});

test.afterEach(async () => {
  while (opened.length) await opened.pop()!.close();
  expect(live.hits, 'nothing may reach the stand-in for the live backend').toEqual([]);
  expect(liveFrontend.hits, 'nothing may reach the stand-in for the live frontend').toEqual([]);
});

async function pair(health: http.RequestListener, frontendApi: 'self' | 'live' | null = 'self') {
  const api = await fakeServer(health);
  const target = frontendApi === 'self' ? api.url : frontendApi === 'live' ? live.url : null;
  const frontend = await fakeServer(frontendCalling(target));
  opened.push(api, frontend);
  const base = loadCommittedPolicy();
  const policy: BrowserPolicy = {
    ...base,
    live: { ...base.live, backendPorts: [live.port], frontendPorts: [liveFrontend.port] },
    isolated: { ...base.isolated, backendPorts: [api.port], frontendPorts: [frontend.port] },
  };
  const env = {
    E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: api.url, E2E_ISOLATED_BASE_URL: frontend.url.replace('127.0.0.1', 'localhost'),
    E2E_API_URL: live.url, E2E_BASE_URL: liveFrontend.url,
  };
  const preflight = createBrowserPreflight(policy, { healthMs: 3_000, navigationMs: 10_000, firstApiCallMs: 3_000 });
  return { api, frontend, check: () => preflight.check(env, ['live-isolated']) };
}

const codesOf = (result: { refusals: { code: string }[] }) => result.refusals.map((r) => r.code);

test('an isolated backend and frontend that are what they say pass, with one GET and nothing sent by the probe', async () => {
  const { api, frontend, check } = await pair(json(HEALTHY));
  const result = await check();
  expect(result.refusals).toEqual([]);
  expect(result.ok).toBe(true);
  expect(api.hits).toEqual(['GET /health']);                 // the probe's API call was aborted in the browser
  expect(frontend.hits).toContain('GET /');
  expect(result.operations).toEqual([
    `GET ${api.url}/health`,
    expect.stringMatching(/^browser: loaded http:\/\/localhost:\d+\/ with every API request aborted in the browser/),
  ]);
  expect(result.lines.join('\n')).toMatch(/soccer_predictions_e2e/);
});

test('a backend serving the live database is refused after its one GET, and the frontend is never loaded', async () => {
  const { api, frontend, check } = await pair(json({ ...HEALTHY, database: 'soccer_predictions' }));
  const result = await check();
  expect(codesOf(result)).toContain('live-database');
  expect(api.hits).toEqual(['GET /health']);
  expect(frontend.hits).toEqual([]);
  expect(result.operations).toEqual([`GET ${api.url}/health`]);
});

test('a backend that cannot vouch for its database (database: null) is refused, and the frontend is never loaded', async () => {
  // GET /health publishes null when the DATABASE_URL redirects (a ?dbname= parameter, say) or cannot
  // be read: the name it would otherwise give is not where the driver connects.
  const { api, frontend, check } = await pair(json({ ...HEALTHY, database: null }));
  const result = await check();
  expect(codesOf(result)).toEqual(['database-unknown']);
  expect(result.refusals[0].message).toMatch(/cannot say which database/);
  expect(api.hits).toEqual(['GET /health']);
  expect(frontend.hits).toEqual([]);
});

test('a database the policy does not list is refused, and a protected copy counts as live', async () => {
  const unlisted = await pair(json({ ...HEALTHY, database: 'soccer_predictions_e2e_old' }));
  expect(codesOf(await unlisted.check())).toEqual(['unapproved-database']);
  const devCopy = await pair(json({ ...HEALTHY, database: 'soccer_predictions_dev' }));
  expect(codesOf(await devCopy.check())).toEqual(['live-database']);
});

test('a backend using a live Redis database is refused, whichever role uses it', async () => {
  const { check } = await pair(json({ ...HEALTHY, redis_databases: [0, 10, 11, 12, 13, 14, 15] }));
  expect(codesOf(await check())).toContain('live-redis');
});

test('Redis databases outside the isolated set, or another Redis server, are refused', async () => {
  const outside = await pair(json({ ...HEALTHY, redis_databases: [7, 10] }));
  expect(codesOf(await outside.check())).toContain('unapproved-redis');
  const elsewhere = await pair(json({ ...HEALTHY, redis_server: { port: 6390, loopback: true } }));
  expect(codesOf(await elsewhere.check())).toContain('unapproved-redis');
  const remote = await pair(json({ ...HEALTHY, redis_server: { port: 6379, loopback: false } }));
  expect(codesOf(await remote.check())).toContain('unapproved-redis');
});

for (const field of ['database', 'redis_databases', 'redis_server', 'scheduler_enabled'] as const) {
  test(`a backend that does not publish ${field} is refused`, async () => {
    const body: Record<string, unknown> = { ...HEALTHY };
    delete body[field];
    const { check } = await pair(json(body));
    const result = await check();
    expect(codesOf(result)).toContain('missing-field');
    expect(result.refusals.map((r) => r.message).join('\n')).toMatch(/restart the isolated backend/);
  });
}

test('a backend with its scheduler on is refused', async () => {
  const { check } = await pair(json({ ...HEALTHY, scheduler_enabled: true }));
  expect(codesOf(await check())).toContain('scheduler-on');
});

test('a redirect, an error status or a body that is not JSON is refused, and a redirect is not followed', async () => {
  const redirect = await pair((_req, res) => { res.writeHead(302, { location: `${live.url}/health` }); res.end(); });
  expect(codesOf(await redirect.check())).toContain('health-unreadable');
  const failing = await pair(json({ detail: 'boom' }, 500));
  expect(codesOf(await failing.check())).toContain('health-unreadable');
  const text = await pair((_req, res) => { res.writeHead(200, { 'content-type': 'text/plain' }); res.end('ok'); });
  expect(codesOf(await text.check())).toContain('health-unreadable');
});

test('an isolated frontend whose bundle calls another backend is refused, and that backend receives nothing', async () => {
  const { api, check } = await pair(json(HEALTHY), 'live');
  const result = await check();
  expect(codesOf(result)).toContain('frontend-calls-other-backend');
  expect(result.refusals.map((r) => r.message).join('\n')).toContain(`:${live.port}`);
  expect(api.hits).toEqual(['GET /health']);
});

test('an isolated frontend that makes no API call is refused: which backend it calls cannot be established', async () => {
  const { check } = await pair(json(HEALTHY), null);
  expect(codesOf(await check())).toContain('frontend-unverified');
});

test('a refusal in Stage A sends nothing at all', async () => {
  const { api, frontend } = await pair(json(HEALTHY));
  const preflight = createBrowserPreflight(loadCommittedPolicy());   // the committed ports: the fakes are unapproved
  const result = await preflight.check({ E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: api.url,
    E2E_ISOLATED_BASE_URL: frontend.url }, ['live-isolated']);
  expect(codesOf(result)).toContain('unapproved-target');
  expect(result.operations).toEqual([]);
  expect(api.hits).toEqual([]);
  expect(frontend.hits).toEqual([]);
  expect(result.lines.join('\n')).toMatch(/nothing was sent to any server/);
});
