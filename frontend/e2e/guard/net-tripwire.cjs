'use strict';
/**
 * A network tripwire for a whole Playwright run, loaded with NODE_OPTIONS=--require by
 * refusal-runs.test.mjs into the runner AND every worker it forks (they inherit NODE_OPTIONS).
 *
 * Every outbound TCP connect made by Node in those processes - http, https, undici fetch,
 * Playwright's APIRequestContext, a raw net.connect - goes through net.Socket.prototype.connect.
 * Each one is written to GUARD_NET_TRIPWIRE_LOG and BLOCKED (the socket is destroyed with
 * ECONNREFUSED before any packet leaves), unless its exact host:port is listed in
 * GUARD_NET_TRIPWIRE_ALLOW, in which case it is written down as allowed and goes ahead.
 * Local IPC (a path rather than a port) is left alone: the runner talks to its workers and to the
 * browser over pipes, not over TCP.
 *
 * It does not see the browser's own network (Chromium is another process). The runs it guards
 * either refuse before any browser starts, or are approved runs whose browser traffic is the
 * frontend under test.
 */
const fs = require('node:fs');
const net = require('node:net');

const LOG = process.env.GUARD_NET_TRIPWIRE_LOG;
const ALLOW = new Set((process.env.GUARD_NET_TRIPWIRE_ALLOW || '').split(',').map((s) => s.trim()).filter(Boolean));

function note(line) {
  if (LOG) fs.appendFileSync(LOG, `${line}\n`);
}

function target(args) {
  let first = args[0];
  const second = args[1];
  if (Array.isArray(first)) first = first[0];   // net.connect() normalises to [options, callback]
  if (first && typeof first === 'object') {
    if (first.path) return null;
    return `${first.host || 'localhost'}:${Number(first.port)}`;
  }
  if (typeof first === 'string' && Number.isNaN(Number(first))) return null;   // an IPC path
  return `${typeof second === 'string' ? second : 'localhost'}:${Number(first)}`;
}

const original = net.Socket.prototype.connect;
net.Socket.prototype.connect = function tripwiredConnect(...args) {
  const where = target(args);
  if (where === null) return original.apply(this, args);
  if (ALLOW.has(where)) {
    note(`allowed ${where} pid ${process.pid}`);
    return original.apply(this, args);
  }
  note(`blocked ${where} pid ${process.pid}`);
  const error = Object.assign(new Error(`net tripwire: connection to ${where} blocked`), { code: 'ECONNREFUSED' });
  process.nextTick(() => this.destroy(error));
  return this;
};
note(`installed pid ${process.pid}`);
