"""Shared helpers for provider tests (mocked HTTP + in-memory Redis stand-in)."""

from __future__ import annotations

import json
import threading
from typing import Callable, List

import httpx


class FakeRedis:
    """Minimal in-memory stand-in for the redis client methods used by MatchCache and RequestBudget."""

    def __init__(self):
        self.store = {}
        self.ttls = {}
        self._atomic = threading.RLock()
        #: Test hook: raised by every sync-lease script while set, as an unreachable Redis would.
        self.lease_error = None

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None, px=None, **kwargs):
        with self._atomic:
            if nx and self.get(key) is not None:
                return None
            self.store[key] = value
            if ex is not None:
                self._set_expiry_ms(key, int(ex) * 1000)
            elif px is not None:
                self._set_expiry_ms(key, int(px))
            return True

    def _set_expiry_ms(self, key, ms):
        self.ttls[key] = ms // 1000 if ms % 1000 == 0 else ms / 1000

    def register_script(self, script):
        """The sync lease's scripts (app.services.sync_lease), emulated atomically; nothing else.

        Deliberately not `eval`: RequestBudget probes for `eval` to pick its reservation path, and
        these fakes must keep sending it down the path the budget tests expect.
        """
        def run(keys=(), args=(), client=None):
            return self._run_lease_script(script, list(keys), list(args))
        return run

    def _run_lease_script(self, script, keys, args):
        from app.services import sync_lease
        with self._atomic:
            if self.lease_error is not None:
                raise self.lease_error
            held = self.get(keys[0])
            if isinstance(held, (bytes, bytearray)):
                held = held.decode("utf-8")
            mine = held is not None and held == str(args[0])
            if script == sync_lease.RENEW_SCRIPT:
                if not mine:
                    return 0
                self._set_expiry_ms(keys[0], int(args[1]))
                return 1
            if script == sync_lease.RELEASE_SCRIPT:
                if not mine:
                    return 0
                self.delete(keys[0])
                return 1
            if script == sync_lease.FENCED_SET_SCRIPT:
                if not mine:
                    return 0
                for key, ttl in zip(keys[1:], args[2:]):
                    self.setex(key, int(ttl), args[1])
                return 1
            if script == sync_lease.FENCED_DELETE_SCRIPT:
                if not mine:
                    return 0
                self.delete(*keys[1:])
                return 1
        raise NotImplementedError("FakeRedis emulates only the sync lease scripts")

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl

    def incrby(self, key, amount):
        self.store[key] = int(self.store.get(key) or 0) + int(amount)
        return self.store[key]

    def hincrby(self, key, field, amount):
        bucket = self.store.setdefault(key, {})
        bucket[field] = int(bucket.get(field) or 0) + int(amount)
        return bucket[field]

    def hgetall(self, key):
        value = self.store.get(key)
        return dict(value) if isinstance(value, dict) else {}

    def hset(self, key, field, value):
        bucket = self.store.setdefault(key, {})
        bucket[field] = value
        return 1

    def expire(self, key, ttl):
        self.ttls[key] = ttl

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)

    def expire_now(self, *keys):
        """Test helper: drop a key as if its TTL had elapsed (the `:stale` copy is left alone)."""
        for key in keys:
            self.store.pop(key, None)
            self.ttls.pop(key, None)


class Recorder:
    """Wraps a handler so tests can inspect the requests the provider issued."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]):
        self.handler = handler
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make_transport(handler):
    recorder = Recorder(handler)
    return httpx.MockTransport(recorder), recorder


def json_response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})
