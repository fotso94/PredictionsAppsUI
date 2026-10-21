/**
 * The REAL Playwright configuration (playwright.config.ts) started with unsafe settings, and
 * refused before any test runs and before anything is sent anywhere.
 *
 *   node --test e2e/guard/refusal-runs.test.mjs        (npm run e2e:guard runs it after the specs)
 *
 * Each case starts one `playwright test` of its own, one after another, never two at once and
 * never from inside another Playwright runner. Each run is wrapped in two tripwires:
 *  - net-tripwire.cjs, loaded with NODE_OPTIONS=--require into the runner and every worker, which
 *    records and BLOCKS every outbound TCP connect Node makes (except the exact host:port a
 *    positive case allows);
 *  - TCP servers on free ports standing in for the frontend and backends a case names, which
 *    record every connection they receive.
 * An unsafe target is never a live service: it is either one of those stand-ins, or a live port
 * named only in a run that selects no test (--grep matching nothing), so that a configuration
 * WITHOUT the preflight runs nothing at all, and the preflight - which runs before tests are
 * loaded - is the only code that could act.
 *
 * Every run writes its output to a temporary directory (--output) with the line reporter, so it
 * never touches e2e/.artifacts or e2e/.report.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PLAYWRIGHT = path.join(FRONTEND, 'node_modules', '.bin', 'playwright');
const TRIPWIRE = path.join(FRONTEND, 'e2e', 'guard', 'net-tripwire.cjs');
const NO_SUCH_TEST = '__the_isolation_guard_selects_no_test__';
const PASS_THROUGH = ['PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'LOGNAME', 'SHELL', 'PLAYWRIGHT_BROWSERS_PATH'];
const RUNS_TEST = /Running \d+ tests? using/;

async function standIn() {
  const hits = [];
  const server = net.createServer((socket) => {
    hits.push(`connection from ${socket.remoteAddress}`);
    socket.end('HTTP/1.1 503 Service Unavailable\r\ncontent-length: 0\r\nconnection: close\r\n\r\n');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  return { port, url: `http://127.0.0.1:${port}`, hits, close: () => new Promise((resolve) => server.close(resolve)) };
}

async function playwright({ env = {}, args = [], allow = [], config = 'playwright.config.ts', cwd = FRONTEND, listOnly = false }) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'isolation-guard-run-'));
  const log = path.join(dir, 'net.log');
  fs.writeFileSync(log, '');
  const childEnv = {};
  for (const key of PASS_THROUGH) if (process.env[key]) childEnv[key] = process.env[key];
  Object.assign(childEnv, {
    FORCE_COLOR: '0', NODE_OPTIONS: `--require ${TRIPWIRE}`, GUARD_NET_TRIPWIRE_LOG: log,
    GUARD_NET_TRIPWIRE_ALLOW: allow.join(','),
  });
  for (const [key, value] of Object.entries(env)) if (value !== undefined) childEnv[key] = value;
  // config null: no --config at all, so Playwright looks for one in cwd and, finding none, builds its
  // default configuration. listOnly: --list, which takes no --output, reporter or workers.
  const argv = ['test', ...(config ? [`--config=${config}`] : []),
    ...(!listOnly ? [`--output=${path.join(dir, 'artifacts')}`, '--reporter=line', '--workers=1'] : []), ...args];
  const child = spawn(PLAYWRIGHT, argv, { cwd, env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk; });
  child.stderr.on('data', (chunk) => { output += chunk; });
  const timer = setTimeout(() => child.kill('SIGKILL'), 240_000);
  const status = await new Promise((resolve) => child.on('close', (code) => resolve(code)));
  clearTimeout(timer);
  const lines = fs.readFileSync(log, 'utf8').split('\n').filter(Boolean);
  fs.rmSync(dir, { recursive: true, force: true });
  return {
    status, output,
    installed: lines.filter((l) => l.startsWith('installed')).length,
    connections: lines.filter((l) => !l.startsWith('installed')),
  };
}

function refusedBeforeAnything(result, pattern, standIns = []) {
  const shown = `exit ${result.status}\n${result.output.slice(-4000)}\nnet: ${result.connections.join('; ')}`;
  assert.ok(result.installed >= 1, `the tripwire was not loaded\n${shown}`);
  assert.deepEqual(result.connections, [], `Node connected or tried to\n${shown}`);
  for (const s of standIns) assert.deepEqual(s.hits, [], `a stand-in on :${s.port} was contacted\n${shown}`);
  assert.doesNotMatch(result.output, RUNS_TEST, `a test started\n${shown}`);
  assert.notEqual(result.status, 0, shown);
  assert.match(result.output, pattern, shown);
}

/** Four stand-ins: whatever a run would have contacted lands on one of them, and is recorded. */
async function standIns() {
  const all = { isolatedBase: await standIn(), isolatedApi: await standIn(), base: await standIn(), api: await standIn() };
  return {
    ...all,
    list: Object.values(all),
    env: {
      E2E_ISOLATED_BASE_URL: all.isolatedBase.url, E2E_ISOLATED_API_URL: all.isolatedApi.url,
      E2E_BASE_URL: all.base.url, E2E_API_URL: all.api.url,
    },
    close: () => Promise.all(Object.values(all).map((s) => s.close())),
  };
}

// ----------------------------------------------------------------------------------- selection
test('the live-isolated project does not exist unless E2E_STACK selects it', async () => {
  const s = await standIns();
  try {
    const result = await playwright({ env: s.env, args: ['--project=live-isolated', 'e2e/live-isolated/expert-composer.spec.ts'] });
    refusedBeforeAnything(result, /Project\(s\) "live-isolated" not found/, s.list);
  } finally { await s.close(); }
});

test('the live project does not exist unless E2E_STACK selects it', async () => {
  const result = await playwright({ args: ['--project=live', '--grep', NO_SUCH_TEST] });
  refusedBeforeAnything(result, /Project\(s\) "live" not found/);
});

test('an E2E_STACK that is not exactly one stack is refused when the configuration loads', async () => {
  for (const value of ['live,live-isolated', 'LIVE', '1']) {
    const result = await playwright({ env: { E2E_STACK: value }, args: ['--grep', NO_SUCH_TEST] });
    refusedBeforeAnything(result, /E2E_STACK must be one of/);
  }
});

// ----------------------------------------------------------------------------------- unapproved and missing targets
test('live-isolated pointed at servers the policy does not name is refused before any test', async () => {
  const s = await standIns();
  try {
    const result = await playwright({
      env: { E2E_STACK: 'live-isolated', ...s.env },
      args: ['--project=live-isolated', 'e2e/live-isolated/expert-composer.spec.ts'],
    });
    refusedBeforeAnything(result, /isolation preflight: REFUSED[\s\S]*\[unapproved-target\][\s\S]*nothing was sent to any server/, s.list);
  } finally { await s.close(); }
});

test('live-isolated with no isolated API URL is refused, not defaulted', async () => {
  const result = await playwright({
    env: { E2E_STACK: 'live-isolated', E2E_ISOLATED_BASE_URL: 'http://localhost:3101' },
    args: ['--project=live-isolated', '--grep', NO_SUCH_TEST],
  });
  refusedBeforeAnything(result, /\[missing:E2E_ISOLATED_API_URL\][\s\S]*nothing was sent to any server/);
});

// ----------------------------------------------------------------------------------- live targets
test('the live backend or frontend named as the isolated pair is refused before anything is sent', async () => {
  const result = await playwright({
    env: { E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: 'http://127.0.0.1:8000', E2E_ISOLATED_BASE_URL: 'http://localhost:3100' },
    args: ['--project=live-isolated', '--grep', NO_SUCH_TEST],
  });
  refusedBeforeAnything(result, /\[live-target\][\s\S]*:8000[\s\S]*nothing was sent to any server/);
  assert.match(result.output, /\[live-target\][^\n]*:3100/);
});

// ----------------------------------------------------------------------------------- conflicts
test('an isolated API that is also the main API is refused', async () => {
  const result = await playwright({
    env: { E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: 'http://127.0.0.1:8001', E2E_ISOLATED_BASE_URL: 'http://localhost:3101', E2E_API_URL: 'http://localhost:8001' },
    args: ['--project=live-isolated', '--grep', NO_SUCH_TEST],
  });
  refusedBeforeAnything(result, /\[conflict:same-origin\]/);
});

test('a mocked run whose frontend URL is a backend is refused', async () => {
  const result = await playwright({ env: { E2E_BASE_URL: 'http://127.0.0.1:8001' }, args: ['--project=mocked-desktop', '--grep', NO_SUCH_TEST] });
  refusedBeforeAnything(result, /\[conflict:frontend-is-backend\]/);
});

test('a URL carrying a password is refused and the password is never printed', async () => {
  const result = await playwright({
    env: { E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: 'http://qa:hunter2-not-real@127.0.0.1:8001', E2E_ISOLATED_BASE_URL: 'http://localhost:3101' },
    args: ['--project=live-isolated', '--grep', NO_SUCH_TEST],
  });
  refusedBeforeAnything(result, /\[malformed-url\]/);
  assert.doesNotMatch(result.output, /hunter2-not-real/);
});

// ----------------------------------------------------------------------------------- approved setups still run
test('an approved mocked run starts and passes, and Node reaches for no server but the web font host', async () => {
  const result = await playwright({
    env: { E2E_BASE_URL: 'http://localhost:3101' },
    args: ['--project=mocked-desktop', 'e2e/mocked/provider-states.spec.ts', '--grep', 'the status banner stays away'],
  });
  const shown = `exit ${result.status}\n${result.output.slice(-3000)}\nnet: ${result.connections.join('; ')}`;
  assert.equal(result.status, 0, shown);
  assert.match(result.output, /isolation preflight: PASS[\s\S]*nothing was sent to any server/, shown);
  assert.match(result.output, /1 passed/, shown);
  // The mocked suite fetches the Google web font from Node by design (external-assets.ts, with a
  // stand-in when it cannot); the tripwire blocked it and the stand-in served. Nothing else, and
  // nothing on this machine - no backend - was reached for.
  const other = result.connections.filter((c) => !/^blocked fonts\.(googleapis|gstatic)\.com:443 /.test(c));
  assert.deepEqual(other, [], shown);
});

test('the approved isolated pair passes the preflight: one GET to the isolated backend and nothing else from Node', async () => {
  const result = await playwright({
    env: { E2E_STACK: 'live-isolated', E2E_ISOLATED_API_URL: 'http://127.0.0.1:8001', E2E_ISOLATED_BASE_URL: 'http://localhost:3101' },
    args: ['--project=live-isolated', '--grep', NO_SUCH_TEST],
    allow: ['127.0.0.1:8001'],
  });
  const shown = `exit ${result.status}\n${result.output.slice(-3000)}\nnet: ${result.connections.join('; ')}`;
  assert.match(result.output, /isolation preflight: PASS/, shown);
  assert.match(result.output, /live-isolated[^\n]*soccer_predictions_e2e/, shown);
  assert.equal(result.connections.length, 1, shown);
  assert.match(result.connections[0], /^allowed 127\.0\.0\.1:8001 /, shown);
  assert.match(result.output, /No tests found/, shown);   // it selected none on purpose
});


// ----------------------------------------------------------------------------------- the bypasses of 2026-10-21
/** A worker refused the run: the preflight token was missing, so the test never reached its body. */
function refusedInTheWorker(result, standIns = []) {
  const shown = `exit ${result.status}\n${result.output.slice(-4000)}\nnet: ${result.connections.join('; ')}`;
  assert.ok(result.installed >= 1, `the tripwire was not loaded\n${shown}`);
  assert.deepEqual(result.connections, [], `Node connected or tried to\n${shown}`);
  for (const s of standIns) assert.deepEqual(s.hits, [], `a stand-in on :${s.port} was contacted\n${shown}`);
  assert.notEqual(result.status, 0, shown);
  assert.doesNotMatch(result.output, /\b[1-9]\d* passed\b/, shown);
  assert.match(result.output, /the isolation preflight did not pass in this run/, shown);
}

test('a mocked run never uses the live frontend: the default is the isolated one, and :3100 is refused', async () => {
  const onDefaults = await playwright({ args: ['--project=mocked-desktop', '--grep', NO_SUCH_TEST] });
  const shown = `exit ${onDefaults.status}\n${onDefaults.output.slice(-3000)}`;
  assert.match(onDefaults.output, /isolation preflight: PASS[\s\S]*mocked-desktop[^\n]*: frontend http:\/\/localhost:3101;/, shown);
  assert.deepEqual(onDefaults.connections, [], shown);
  const named = await playwright({ env: { E2E_BASE_URL: 'http://localhost:3100' }, args: ['--project=mocked-desktop', '--grep', NO_SUCH_TEST] });
  refusedBeforeAnything(named, /\[live-target\][^\n]*:3100[\s\S]*nothing was sent to any server/);
});

test('live specs run under another configuration (no global setup) refuse before their first request', async () => {
  // `-c e2e/live` names a directory with no playwright.config.*: Playwright builds its default
  // configuration, with no globalSetup, so no preflight and no E2E_STACK gate.
  const [api, isolatedApi] = [await standIn(), await standIn()];
  try {
    const result = await playwright({ config: 'e2e/live', env: { E2E_API_URL: api.url, E2E_ISOLATED_API_URL: isolatedApi.url },
      args: ['--grep', 'three distinct forecast timestamps'] });
    refusedInTheWorker(result, [api, isolatedApi]);
  } finally { await api.close(); await isolatedApi.close(); }
});

test('live and live-isolated specs named from the repository root (no configuration at all) refuse too', async () => {
  const [api, isolatedApi] = [await standIn(), await standIn()];
  try {
    const result = await playwright({ config: null, cwd: path.dirname(FRONTEND),
      env: { E2E_API_URL: api.url, E2E_ISOLATED_API_URL: isolatedApi.url },
      args: ['frontend/e2e/live', 'frontend/e2e/live-isolated', '--grep', 'three distinct forecast timestamps|a DELETE sent twice'] });
    refusedInTheWorker(result, [api, isolatedApi]);
  } finally { await api.close(); await isolatedApi.close(); }
});

test('workers refuse when no preflight passed in their runner, as in watch mode, which ignores a failed global setup', async () => {
  // PWTEST_WATCH's loop (runWatchModeLoop in playwright/lib/runner) awaits runGlobalSetup and drops its
  // status, then runs tests on every change; UI mode lets a person run them too. A configuration
  // that is the real one without its globalSetup stands for that here, with no watcher and no prompt.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'isolation-guard-config-'));
  const config = path.join(dir, 'no-preflight.config.ts');
  fs.writeFileSync(path.join(dir, 'package.json'), '{ "type": "module" }\n');   // as frontend/package.json
  fs.writeFileSync(config, `import real from ${JSON.stringify(path.join(FRONTEND, 'playwright.config.ts'))};\n`
    + `export default { ...real, testDir: ${JSON.stringify(path.join(FRONTEND, 'e2e'))}, globalSetup: undefined };\n`);
  try {
    const result = await playwright({ config, env: { E2E_BASE_URL: 'http://localhost:3101' },
      args: ['--project=mocked-desktop', 'e2e/mocked/provider-states.spec.ts', '--grep', 'the status banner stays away'] });
    refusedInTheWorker(result);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

/** A copy of the browser tests whose checkout directory is called `name`, for `--list` only. */
function checkoutNamed(name) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'isolation-guard-checkout-'));
  const frontend = path.join(root, name, 'frontend');
  const policyDir = path.join(root, name, 'backend', 'app', 'core');
  fs.mkdirSync(policyDir, { recursive: true });
  fs.copyFileSync(path.join(FRONTEND, '..', 'backend', 'app', 'core', 'isolation_targets.json'), path.join(policyDir, 'isolation_targets.json'));
  fs.mkdirSync(frontend, { recursive: true });
  for (const file of ['playwright.config.ts', 'package.json']) fs.copyFileSync(path.join(FRONTEND, file), path.join(frontend, file));
  fs.cpSync(path.join(FRONTEND, 'e2e'), path.join(frontend, 'e2e'), {
    recursive: true, filter: (from) => !/[\\/]e2e[\\/]\.[^\\/]+/.test(from) });
  fs.symlinkSync(path.join(FRONTEND, 'node_modules'), path.join(frontend, 'node_modules'));
  fs.symlinkSync(path.join(FRONTEND, 'src'), path.join(frontend, 'src'));
  return { root, frontend };
}

/** project -> the e2e directories its listed tests come from (a list line: `[project] › path:line:col › title`). */
function directoriesPerProject(output) {
  const seen = {};
  for (const line of output.split('\n')) {
    const match = /^\s*\[([^\]]+)\] › (\S+?\.spec\.ts):\d+:\d+ › /.exec(line);
    if (!match) continue;
    const parts = match[2].split(/[\\/]/);
    const at = parts.lastIndexOf('e2e');
    (seen[match[1]] ||= new Set()).add(parts[at + 1] ?? '?');
  }
  return Object.fromEntries(Object.entries(seen).map(([k, v]) => [k, [...v].sort()]));
}

for (const [name, stack, expected] of [
  ['PredictionsAppsUI-mocked', undefined, { 'mocked-desktop': ['mocked'], 'mocked-mobile': ['mocked'], 'mocked-mobile-360': ['mocked'] }],
  ['PredictionsAppsUI-live', 'live', { live: ['live'] }],
  ['PredictionsAppsUI-live-isolated', 'live-isolated', { 'mocked-desktop': ['mocked'], 'mocked-mobile': ['mocked'], 'mocked-mobile-360': ['mocked'], 'live-isolated': ['live-isolated'] }],
]) {
  test(`in a checkout called ${name}, each project selects only its own directory`, async () => {
    // testMatch was a regular expression tested against the ABSOLUTE path, so /mocked\/.*\.spec\.ts/
    // matched every spec under ".../PredictionsAppsUI-mocked/", live and live-isolated included.
    const { root, frontend } = checkoutNamed(name);
    try {
      const result = await playwright({ config: 'playwright.config.ts', cwd: frontend, listOnly: true,
        env: stack ? { E2E_STACK: stack } : {}, args: ['--list'] });
      const shown = `exit ${result.status}\n${result.output.slice(-3000)}`;
      assert.equal(result.status, 0, shown);
      assert.deepEqual(result.connections, [], shown);
      assert.deepEqual(directoriesPerProject(result.output), expected, shown);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}
