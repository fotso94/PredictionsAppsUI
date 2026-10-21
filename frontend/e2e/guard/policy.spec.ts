import net from 'node:net';
import { test, expect } from '@playwright/test';
import {
  BrowserPolicy, loadCommittedPolicy, parseStack, policyFromDocument, policyProblems, stageA,
} from '../support/target-policy';

/**
 * Stage A of the browser-test isolation preflight: every target a run would use, resolved from the
 * environment and judged against the committed policy (backend/app/core/isolation_targets.json),
 * with no network at all. Each test here runs with every outbound TCP connect of this process
 * recorded and blocked, and fails if there was one.
 */

const MOCKED = ['mocked-desktop', 'mocked-mobile', 'mocked-mobile-360'];
const ISOLATED_OK = {
  E2E_STACK: 'live-isolated',
  E2E_ISOLATED_BASE_URL: 'http://localhost:3101',
  E2E_ISOLATED_API_URL: 'http://127.0.0.1:8001',
};

let policy: BrowserPolicy;
const attempts: string[] = [];
const originalConnect = net.Socket.prototype.connect;

test.beforeAll(() => {
  policy = loadCommittedPolicy();
});

test.beforeEach(() => {
  attempts.length = 0;
  net.Socket.prototype.connect = function blocked(this: net.Socket, ...args: unknown[]) {
    attempts.push(JSON.stringify(args[0]));
    throw new Error('Stage A tried to connect');
  } as typeof net.Socket.prototype.connect;
});

test.afterEach(() => {
  net.Socket.prototype.connect = originalConnect;
  expect(attempts, 'Stage A must not touch the network').toEqual([]);
});

const codes = (env: Record<string, string | undefined>, projects: string[]) =>
  stageA(env, policy, projects).refusals.map((r) => r.code);
const report = (env: Record<string, string | undefined>, projects: string[]) =>
  stageA(env, policy, projects).refusals.map((r) => r.message).join('\n');

// ------------------------------------------------------------------------------------- approved
test('the mocked projects pass on the defaults and on the isolated frontend', () => {
  expect(codes({}, MOCKED)).toEqual([]);
  expect(codes({ E2E_BASE_URL: 'http://localhost:3101' }, MOCKED)).toEqual([]);
});

test('the isolated pair, named explicitly, passes Stage A', () => {
  expect(codes(ISOLATED_OK, [...MOCKED, 'live-isolated'])).toEqual([]);
  const plan = stageA(ISOLATED_OK, policy, ['live-isolated']).plan;
  expect(plan).toEqual([{ project: 'live-isolated', frontend: 'http://localhost:3101', api: 'http://127.0.0.1:8001' }]);
});

test('the live project passes on its own pair without any network', () => {
  expect(codes({ E2E_STACK: 'live' }, [...MOCKED, 'live'])).toEqual([]);
});

// ------------------------------------------------------------------------------------- missing
for (const key of ['E2E_ISOLATED_API_URL', 'E2E_ISOLATED_BASE_URL'] as const) {
  test(`live-isolated without ${key} is refused, with no silent default`, () => {
    expect(codes({ ...ISOLATED_OK, [key]: undefined }, ['live-isolated'])).toContain(`missing:${key}`);
    expect(codes({ ...ISOLATED_OK, [key]: '  ' }, ['live-isolated'])).toContain(`missing:${key}`);
  });
}

// ------------------------------------------------------------------------------------- live targets
for (const host of ['127.0.0.1', 'localhost', '[::1]', '0.0.0.0']) {
  test(`the live backend as the isolated API is refused (${host})`, () => {
    const found = codes({ ...ISOLATED_OK, E2E_ISOLATED_API_URL: `http://${host}:8000` }, ['live-isolated']);
    expect(found).toContain('live-target');
  });
}

test('the live frontend as the isolated frontend is refused', () => {
  expect(codes({ ...ISOLATED_OK, E2E_ISOLATED_BASE_URL: 'http://localhost:3100' }, ['live-isolated'])).toContain('live-target');
});

test('the live project pointed at the isolated pair is refused', () => {
  expect(codes({ E2E_STACK: 'live', E2E_API_URL: 'http://127.0.0.1:8001' }, ['live'])).toContain('isolated-target');
  expect(codes({ E2E_STACK: 'live', E2E_BASE_URL: 'http://localhost:3101' }, ['live'])).toContain('isolated-target');
});

test('a port the policy does not list is not approved', () => {
  expect(codes({ ...ISOLATED_OK, E2E_ISOLATED_API_URL: 'http://127.0.0.1:8002' }, ['live-isolated'])).toContain('unapproved-target');
});

for (const url of ['http://staging-test.example.com:8001', 'http://10.0.0.5:8001', 'http://postgres:8001']) {
  test(`a host that is not this machine cannot be identified (${url})`, () => {
    expect(codes({ ...ISOLATED_OK, E2E_ISOLATED_API_URL: url }, ['live-isolated'])).toContain('not-loopback');
  });
}

// ------------------------------------------------------------------------------------- conflicts
test('the isolated API may not be the main API or the isolated frontend', () => {
  expect(codes({ ...ISOLATED_OK, E2E_API_URL: 'http://localhost:8001' }, ['live-isolated'])).toContain('conflict:same-origin');
  expect(codes({ ...ISOLATED_OK, E2E_ISOLATED_BASE_URL: 'http://localhost:8001' }, ['live-isolated'])).toContain('conflict:same-origin');
});

for (const base of ['http://127.0.0.1:8000', 'http://localhost:8001', 'http://localhost:9000']) {
  test(`a mocked run whose frontend is a backend is refused (${base})`, () => {
    const env = { E2E_BASE_URL: base, E2E_API_URL: 'http://127.0.0.1:9000' };
    expect(codes(env, MOCKED)).toContain('conflict:frontend-is-backend');
  });
}

test('a URL with a password is refused and the password never echoed', () => {
  const env = { ...ISOLATED_OK, E2E_ISOLATED_API_URL: 'http://qa:hunter2-not-real@127.0.0.1:8001' };
  expect(codes(env, ['live-isolated'])).toContain('malformed-url');
  expect(report(env, ['live-isolated'])).not.toContain('hunter2-not-real');
});

for (const url of ['http://127.0.0.1:8001/api', 'http://127.0.0.1:8001/?x=1', 'ftp://127.0.0.1:8001', 'not a url']) {
  test(`a URL that is not a bare origin is refused (${url})`, () => {
    expect(codes({ ...ISOLATED_OK, E2E_ISOLATED_API_URL: url }, ['live-isolated'])).toContain('malformed-url');
  });
}

test('every refusal is collected before any is reported', () => {
  const env = { ...ISOLATED_OK, E2E_ISOLATED_API_URL: 'http://127.0.0.1:8000', E2E_ISOLATED_BASE_URL: undefined, E2E_BASE_URL: 'http://127.0.0.1:8001' };
  const found = codes(env, [...MOCKED, 'live-isolated']);
  expect(found).toEqual(expect.arrayContaining(['live-target', 'missing:E2E_ISOLATED_BASE_URL', 'conflict:frontend-is-backend']));
});

// ------------------------------------------------------------------------------------- selection
test('E2E_STACK accepts exactly unset, mocked, live and live-isolated', () => {
  expect(parseStack(undefined)).toBe('mocked');
  expect(parseStack('')).toBe('mocked');
  expect(parseStack('mocked')).toBe('mocked');
  expect(parseStack('live')).toBe('live');
  expect(parseStack('live-isolated')).toBe('live-isolated');
  for (const bad of ['live,live-isolated', 'LIVE', 'live ', '1', 'isolated', 'true']) {
    expect(() => parseStack(bad), bad).toThrow(/E2E_STACK/);
  }
});

// ------------------------------------------------------------------------------------- the policy
test('the committed policy is the backend guard\'s, and is self-consistent', () => {
  expect(policy.sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(policy.isolated.databases).toEqual(['soccer_predictions_e2e']);
  expect(policy.live.databases).toEqual(expect.arrayContaining(['soccer_predictions']));
  expect(policy.isolated.redisDatabases).toEqual([10, 11, 12, 13, 14, 15]);
  expect(policy.live.redisDatabases).toEqual([0, 1, 2, 3, 4, 5]);
  expect(policyProblems(policy)).toEqual([]);
});

test('a policy whose live and isolated sides overlap is refused', () => {
  const overlapping = { ...policy, isolated: { ...policy.isolated, backendPorts: [8001, 8000] } };
  expect(policyProblems(overlapping).join('\n')).toMatch(/overlap/);
  const sharedDb = { ...policy, isolated: { ...policy.isolated, redisDatabases: [5, 10] } };
  expect(policyProblems(sharedDb).join('\n')).toMatch(/overlap/);
  const empty = { ...policy, isolated: { ...policy.isolated, databases: [] } };
  expect(policyProblems(empty).join('\n')).toMatch(/empty/);
  expect(() => policyFromDocument({ format: 'something-else/1' })).toThrow(/format/);
});
