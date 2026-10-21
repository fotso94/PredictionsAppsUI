import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Which servers a browser-test run may use: the browser half of the isolation preflight, Stage A.
 *
 * ONE POLICY FOR BOTH HALVES. The allowlist is backend/app/core/isolation_targets.json, the file the
 * backend guard (app/core/target_guard.py) reads. Only that committed path is read: no variable can
 * point the loader elsewhere, because a redirected policy would itself be an override nobody can
 * see. The policy is checked for self-consistency (no list empty, the live and isolated sides
 * disjoint) and a policy that fails is refused, not repaired.
 *
 * SELECTION. playwright.config.ts defines `live` and `live-isolated` only when E2E_STACK names them
 * exactly (parseStack). That variable only decides WHICH projects exist; whether their targets are
 * safe is decided here, from the resolved URLs, so a mis-set or unexpanded variable can only ever
 * make a run refuse.
 *
 * STAGE A IS PURE: it parses and compares strings and port numbers. Hosts are recognised as this
 * machine only by exact text (localhost, 127.0.0.1, ::1, and 0.0.0.0 as the same machine), never by
 * a lookup and never because a name contains "test"; the port is what tells two local servers apart.
 */

export type Stack = 'mocked' | 'live' | 'live-isolated';
export const STACKS: readonly Stack[] = ['mocked', 'live', 'live-isolated'];

export interface Side {
  frontendPorts: number[];
  backendPorts: number[];
  /** Database names this side's backend serves (live: every protected `live` database). */
  databases: string[];
  /** The Redis port of this side's databases, when the policy names one. */
  redisPort: number | null;
  redisDatabases: number[];
}

export interface BrowserPolicy {
  sha256: string;
  loopbackHosts: string[];
  live: Side;
  isolated: Side;
}

export interface Refusal { code: string; message: string }

export interface PlannedTarget { project: string; frontend: string; api: string | null }

export class PolicyError extends Error {}

const POLICY_FORMAT = 'isolation-targets/1';
const POLICY_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'backend', 'app', 'core',
  'isolation_targets.json');
/** Hosts that are this machine. 0.0.0.0 is not loopback, but a URL naming it reaches this machine. */
const SAME_MACHINE = new Set(['localhost', '127.0.0.1', '::1', '0.0.0.0']);
const MOCKED_PROJECTS = ['mocked-desktop', 'mocked-mobile', 'mocked-mobile-360'];

/** The stack E2E_STACK selects: exactly unset/empty, `mocked`, `live` or `live-isolated`. */
export function parseStack(value: string | undefined): Stack {
  if (value === undefined || value === '') return 'mocked';
  if ((STACKS as readonly string[]).includes(value)) return value as Stack;
  const shown = JSON.stringify(value.length > 40 ? `${value.slice(0, 40)}...` : value);
  throw new Error(`E2E_STACK must be one of: unset, mocked, live, live-isolated (got ${shown}). It selects which `
    + 'Playwright projects exist: live and live-isolated are defined only when it names them, and a run never '
    + 'mixes the two. Use npm run e2e:live-isolated, or E2E_STACK=live-isolated with the isolated URLs.');
}

const isPort = (v: unknown): v is number => Number.isInteger(v) && (v as number) > 0 && (v as number) < 65536;
const isDb = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= 15;

interface PolicyDocument {
  format?: unknown;
  loopback_hosts?: unknown;
  protected?: { postgres_databases?: Array<{ database?: unknown; class?: unknown }>; redis?: Array<{ port?: unknown; databases?: unknown; class?: unknown }> };
  roles?: Record<string, { postgres?: Record<string, Array<{ database?: unknown }>>; redis?: Record<string, Array<{ port?: unknown; databases?: unknown }>> }>;
  browser?: Record<string, { frontend_ports?: unknown; backend_ports?: unknown; role?: unknown }>;
}

/** The browser's view of the policy document, validated; throws PolicyError on a malformed one. */
export function policyFromDocument(doc: unknown, sha256 = ''): BrowserPolicy {
  const d = (doc ?? {}) as PolicyDocument;
  if (d.format !== POLICY_FORMAT) throw new PolicyError(`the isolation policy is not format ${POLICY_FORMAT}`);
  const browser = d.browser ?? {};
  const ports = (side: string, key: 'frontend_ports' | 'backend_ports'): number[] => {
    const value = browser[side]?.[key];
    if (!Array.isArray(value) || !value.every(isPort)) throw new PolicyError(`browser.${side}.${key} is malformed`);
    return value as number[];
  };
  const marks = d.protected?.postgres_databases;
  const redisMarks = d.protected?.redis;
  if (!Array.isArray(marks) || !Array.isArray(redisMarks)) throw new PolicyError('protected is malformed');
  const liveRedis = redisMarks.filter((m) => m.class === 'live');
  const roleName = browser.isolated?.role;
  const role = typeof roleName === 'string' ? d.roles?.[roleName] : undefined;
  if (!role) throw new PolicyError('browser.isolated.role names no role');
  const isolatedDbs = Object.values(role.postgres ?? {}).flat().map((e) => e.database);
  const isolatedRedis = Object.values(role.redis ?? {}).flat();
  if (!isolatedDbs.every((n) => typeof n === 'string') || !isolatedRedis.every((e) => isPort(e.port)
      && Array.isArray(e.databases) && (e.databases as unknown[]).every(isDb))) {
    throw new PolicyError(`role ${roleName} is malformed for the browser (its Redis databases must be listed one by one)`);
  }
  const hosts = d.loopback_hosts;
  if (!Array.isArray(hosts) || !hosts.every((h) => typeof h === 'string')) throw new PolicyError('loopback_hosts is malformed');
  const sorted = (values: number[]) => [...new Set(values)].sort((a, b) => a - b);
  return {
    sha256,
    loopbackHosts: hosts as string[],
    live: {
      frontendPorts: ports('live', 'frontend_ports'),
      backendPorts: ports('live', 'backend_ports'),
      databases: marks.filter((m) => m.class === 'live').map((m) => String(m.database)),
      redisPort: liveRedis.length && isPort(liveRedis[0].port) ? (liveRedis[0].port as number) : null,
      redisDatabases: sorted(liveRedis.flatMap((m) => (Array.isArray(m.databases) ? (m.databases as number[]) : []))),
    },
    isolated: {
      frontendPorts: ports('isolated', 'frontend_ports'),
      backendPorts: ports('isolated', 'backend_ports'),
      databases: isolatedDbs as string[],
      redisPort: isolatedRedis.length ? (isolatedRedis[0].port as number) : null,
      redisDatabases: sorted(isolatedRedis.flatMap((e) => e.databases as number[])),
    },
  };
}

/** Why a policy cannot be trusted; empty when it can. */
export function policyProblems(policy: BrowserPolicy): string[] {
  const problems: string[] = [];
  const overlap = (a: readonly (number | string)[], b: readonly (number | string)[]) => a.filter((x) => b.includes(x));
  for (const [name, side] of Object.entries({ live: policy.live, isolated: policy.isolated })) {
    for (const [key, list] of Object.entries({ frontendPorts: side.frontendPorts, backendPorts: side.backendPorts,
      databases: side.databases, redisDatabases: side.redisDatabases })) {
      if (!list.length) problems.push(`${name}.${key} is empty`);
    }
  }
  const livePorts = [...policy.live.frontendPorts, ...policy.live.backendPorts];
  const isolatedPorts = [...policy.isolated.frontendPorts, ...policy.isolated.backendPorts];
  if (overlap(livePorts, isolatedPorts).length) problems.push('the live and isolated ports overlap');
  if (overlap(policy.live.databases, policy.isolated.databases).length) problems.push('the live and isolated databases overlap');
  if (policy.live.redisPort === policy.isolated.redisPort
      && overlap(policy.live.redisDatabases, policy.isolated.redisDatabases).length) {
    problems.push('the live and isolated Redis databases overlap');
  }
  if (overlap(policy.isolated.frontendPorts, policy.isolated.backendPorts).length) problems.push('an isolated port is both frontend and backend');
  return problems;
}

/** The committed policy, validated. Throws PolicyError when it is missing, malformed or inconsistent. */
export function loadCommittedPolicy(): BrowserPolicy {
  let raw: Buffer;
  try {
    raw = readFileSync(POLICY_PATH);
  } catch {
    throw new PolicyError('the isolation policy backend/app/core/isolation_targets.json cannot be read');
  }
  let doc: unknown;
  try {
    doc = JSON.parse(raw.toString('utf8'));
  } catch {
    throw new PolicyError('the isolation policy backend/app/core/isolation_targets.json is not JSON');
  }
  const policy = policyFromDocument(doc, createHash('sha256').update(raw).digest('hex'));
  const problems = policyProblems(policy);
  if (problems.length) throw new PolicyError(`the isolation policy cannot be trusted: ${problems.join('; ')}`);
  return policy;
}

// ------------------------------------------------------------------------------------------- URLs
export interface Origin { url: string; host: string; port: number; key: string }

/** host:port with every name for this machine folded into one, so a port is what tells servers apart. */
export function origin(url: string): string {
  const parsed = new URL(url);
  const bare = parsed.hostname.replace(/^\[|\]$/g, '');
  const host = SAME_MACHINE.has(bare) ? 'this-machine' : bare;
  return `${parsed.protocol}//${host}:${parsed.port || (parsed.protocol === 'https:' ? '443' : '80')}`;
}

/** A URL named by `key`, as Stage A accepts it: a bare http(s) origin on this machine. */
function readOrigin(key: string, value: string, refusals: Refusal[]): Origin | null {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    refusals.push({ code: 'malformed-url', message: `${key} is not a URL` });
    return null;
  }
  if (parsed.username || parsed.password) {
    refusals.push({ code: 'malformed-url', message: `${key} carries credentials in the URL; they are not shown, and are refused` });
    return null;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    refusals.push({ code: 'malformed-url', message: `${key} is not http or https` });
    return null;
  }
  if ((parsed.pathname && parsed.pathname !== '/') || parsed.search || parsed.hash) {
    refusals.push({ code: 'malformed-url', message: `${key} must be a bare origin (scheme, host and port): it has a path, a query or a fragment` });
    return null;
  }
  const host = parsed.hostname.replace(/^\[|\]$/g, '');
  const port = Number(parsed.port || (parsed.protocol === 'https:' ? 443 : 80));
  const shown = `${parsed.protocol}//${parsed.host}`;
  if (!SAME_MACHINE.has(host)) {
    refusals.push({ code: 'not-loopback', message: `${key} (${shown}) is not on this machine, so the server behind it cannot `
      + 'be identified; only localhost, 127.0.0.1, ::1 and 0.0.0.0 are recognised, by exact name and without a lookup' });
    return null;
  }
  return { url: shown, host, port, key: origin(shown) };
}

const nonBlank = (value: string | undefined) => (value !== undefined && value.trim() !== '' ? value.trim() : undefined);

/**
 * Stage A: every target of every DEFINED project (Playwright does not tell a global setup which
 * projects were selected, and checking more than were selected is safe), with every refusal
 * collected before any is reported. No network.
 */
export function stageA(env: Record<string, string | undefined>, policy: BrowserPolicy, projects: string[]):
  { refusals: Refusal[]; plan: PlannedTarget[] } {
  const refusals: Refusal[] = [];
  const plan: PlannedTarget[] = [];
  const isolatedPorts = [...policy.isolated.frontendPorts, ...policy.isolated.backendPorts];
  const livePorts = [...policy.live.frontendPorts, ...policy.live.backendPorts];
  const backendPorts = [...policy.live.backendPorts, ...policy.isolated.backendPorts];
  const fallback = (ports: number[], host: string) => `http://${host}:${ports[0]}`;

  const read = (key: string, fallbackUrl: string | null): Origin | null => {
    const value = nonBlank(env[key]);
    if (value === undefined) return fallbackUrl === null ? null : readOrigin(key, fallbackUrl, refusals);
    return readOrigin(key, value, refusals);
  };
  // The main pair's URLs as the projects resolve them (playwright.config.ts, qa-account.ts). The
  // frontend's default is the live one only for the live project; anything else - the mocked
  // projects - defaults to the isolated frontend, as playwright.config.ts does.
  const mainBase = read('E2E_BASE_URL', projects.includes('live') ? fallback(policy.live.frontendPorts, 'localhost')
    : fallback(policy.isolated.frontendPorts, 'localhost'));
  const mainApi = read('E2E_API_URL', fallback(policy.live.backendPorts, '127.0.0.1'));
  const isolatedApiGiven = nonBlank(env.E2E_ISOLATED_API_URL) ? read('E2E_ISOLATED_API_URL', null) : null;

  const mocked = projects.filter((p) => MOCKED_PROJECTS.includes(p));
  if (mocked.length && mainBase) {
    const apiPorts = [mainApi?.port, isolatedApiGiven?.port].filter((p): p is number => p !== undefined);
    if (backendPorts.includes(mainBase.port) || apiPorts.includes(mainBase.port)) {
      refusals.push({ code: 'conflict:frontend-is-backend', message: `E2E_BASE_URL (${mainBase.url}) is a backend's port, `
        + 'not a frontend: the mocked projects would load their pages from a backend' });
    } else if (policy.live.frontendPorts.includes(mainBase.port)) {
      // The live frontend serves the main checkout's code, whose API is the live backend; a mocked
      // spec would load every page and module from it, with only its page stubs in front of :8000.
      refusals.push({ code: 'live-target', message: `the mocked projects' frontend (${mainBase.url}) is the live frontend's `
        + `port; mocked specs load their pages from the isolated frontend (${fallback(policy.isolated.frontendPorts, 'localhost')}, `
        + 'the default) or another frontend that is not live, never from the main pair'
        + (projects.includes('live') ? ' - and they are not defined beside the live project, which shares that URL' : '') });
    }
    plan.push(...mocked.map((project) => ({ project, frontend: mainBase.url, api: null })));
  }

  if (projects.includes('live')) {
    for (const [target, ports, role] of [[mainBase, policy.live.frontendPorts, 'frontend'], [mainApi, policy.live.backendPorts, 'backend']] as const) {
      if (!target) continue;
      if (isolatedPorts.includes(target.port)) {
        refusals.push({ code: 'isolated-target', message: `${target.key === mainBase?.key ? 'E2E_BASE_URL' : 'E2E_API_URL'} (${target.url}) `
          + 'is the isolated pair; the live project drives the main pair only' });
      } else if (!ports.includes(target.port)) {
        refusals.push({ code: 'unapproved-target', message: `the live ${role} (${target.url}) is not on an approved live ${role} `
          + `port (${ports.join(', ')})` });
      }
    }
    if (mainBase && mainApi) plan.push({ project: 'live', frontend: mainBase.url, api: mainApi.url });
  }

  if (projects.includes('live-isolated')) {
    const missing = ['E2E_ISOLATED_BASE_URL', 'E2E_ISOLATED_API_URL'].filter((key) => nonBlank(env[key]) === undefined);
    for (const key of missing) {
      refusals.push({ code: `missing:${key}`, message: `${key} is not set; live-isolated writes what it cannot remove, so the `
        + 'isolated pair is never assumed: name it (npm run e2e:live-isolated sets both)' });
    }
    const base = missing.includes('E2E_ISOLATED_BASE_URL') ? null : read('E2E_ISOLATED_BASE_URL', null);
    const api = isolatedApiGiven;
    for (const [target, key, ports, role] of [[base, 'E2E_ISOLATED_BASE_URL', policy.isolated.frontendPorts, 'frontend'],
      [api, 'E2E_ISOLATED_API_URL', policy.isolated.backendPorts, 'backend']] as const) {
      if (!target) continue;
      if (livePorts.includes(target.port)) {
        refusals.push({ code: 'live-target', message: `${key} (${target.url}) is the live ${role}'s port; live-isolated never `
          + 'runs against the main pair' });
      } else if (!ports.includes(target.port)) {
        refusals.push({ code: 'unapproved-target', message: `${key} (${target.url}) is not an approved isolated ${role} port `
          + `(${ports.join(', ')})` });
      }
    }
    if (api && base && api.key === base.key) {
      refusals.push({ code: 'conflict:same-origin', message: 'E2E_ISOLATED_API_URL and E2E_ISOLATED_BASE_URL are the same server' });
    }
    if (api && mainApi && api.key === mainApi.key) {
      refusals.push({ code: 'conflict:same-origin', message: `E2E_ISOLATED_API_URL (${api.url}) is also the main API (E2E_API_URL, `
        + `${mainApi.url}); a write-producing test runs only against the isolated pair` });
    }
    if (base && api) plan.push({ project: 'live-isolated', frontend: base.url, api: api.url });
  }
  return { refusals, plan };
}
