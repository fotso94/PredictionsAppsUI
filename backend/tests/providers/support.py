"""Shared helpers for provider tests (mocked HTTP + in-memory Redis stand-in)."""

from __future__ import annotations

import json
from typing import Callable, List

import httpx


class FakeRedis:
    """Minimal in-memory stand-in for the redis client methods used by MatchCache and RequestBudget."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl

    def incrby(self, key, amount):
        self.store[key] = int(self.store.get(key) or 0) + int(amount)
        return self.store[key]

    def expire(self, key, ttl):
        self.ttls[key] = ttl

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


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
