"""
The sync lease's atomic scripts against a REAL Redis - an isolated one, never the application's.

The deterministic tests (test_forecast_sync_lease.py) run the lease over an in-memory stand-in that
emulates the scripts. These run the actual Lua - renewal, release and fenced writes, each comparing
the owner token inside the server - on a throwaway Redis started for the purpose, for example:

    docker run -d --rm --pull never --name policy-round-lease-test-redis \\
        -p 127.0.0.1:6390:6390 redis:7-alpine redis-server --port 6390 --save "" --appendonly no
    LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/0 pytest tests/services/test_sync_lease_redis.py

They are skipped unless `LEASE_TEST_REDIS_URL` is set, and they refuse a server that answers on the
application's port (6379) or that holds any key when they start: the database they use is emptied
between tests, which is only acceptable on a server that was empty and isolated to begin with.

Expiry here is real Redis expiry. "A term has passed" is produced by setting the key's remaining
life to one millisecond (PEXPIRE) and waiting, within a bound, until Redis reports it gone - the
same state a lapsed five-minute lease leaves - rather than by waiting five minutes. Renewal is
driven by the same controlled `Ticker` the deterministic tests use; the service's own clock is the
fake one, which Redis never sees.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from datetime import timedelta
from urllib.parse import urlparse

import httpx
import pytest

from app.services.forecast_refresh_policy import OUTCOME_SAME_DAY_RUN
from app.services.match_cache import MatchCache
from app.services.providers.budget import RequestBudget
from app.services.sync_lease import LeaseLost, SyncLease, control_set, lease_scope
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    LOCK, START, InThread, daily_slot, service, wait,
)
from tests.services.test_forecast_sync_lease import Ticker, harness, hold_inside_the_fetch
from tests.services.test_sync_scheduler import Clock

redis_lib = pytest.importorskip("redis")

URL = os.environ.get("LEASE_TEST_REDIS_URL")
APPLICATION_PORT = 6379
pytestmark = pytest.mark.skipif(
    not URL, reason="LEASE_TEST_REDIS_URL is not set: no isolated Redis to run the real scripts on")


@pytest.fixture(autouse=True)
def only_the_isolated_redis(monkeypatch):
    """The network is closed except for the isolated Redis itself: no provider can be reached."""
    parsed = urlparse(URL or "redis://127.0.0.1:0")
    allowed = {(host, parsed.port) for host in (parsed.hostname, "127.0.0.1", "localhost", "::1")}
    connect = socket.socket.connect

    def guarded(sock, address):
        if isinstance(address, tuple) and (address[0], address[1]) in allowed:
            return connect(sock, address)
        raise AssertionError(f"a network request was attempted from a lease test: {address}")

    def refuse(*args, **kwargs):
        raise AssertionError("an HTTP request was attempted from a lease test")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


#: The lease lives in the URL's database; the budget and the provider's store in the next two, as
#: the application keeps the match-data cache (lease, provider store) and the request budget in
#: different databases of one server.
def database_of(offset: int) -> int:
    return (int((urlparse(URL).path or "/0").lstrip("/") or 0) + offset) % 16


@pytest.fixture(scope="module")
def identity():
    """Connect, and refuse anything that is not an empty, isolated server."""
    parsed = urlparse(URL)
    # Explicit host, port and database: `from_url` lets the URL's own database win over `db=`.
    clients = {offset: redis_lib.Redis(host=parsed.hostname, port=parsed.port, db=database_of(offset),
                                       socket_connect_timeout=2, socket_timeout=5) for offset in (0, 1, 2)}
    assert [c.connection_pool.connection_kwargs["db"] for c in clients.values()] == \
        [database_of(0), database_of(1), database_of(2)]
    client = clients[0]
    info = client.info("server")
    port = int(info["tcp_port"])
    if port == APPLICATION_PORT or port != (urlparse(URL).port or APPLICATION_PORT):
        pytest.fail(f"refusing Redis on port {port}: the lease tests run only on an isolated server")
    if any(c.dbsize() != 0 for c in clients.values()):
        pytest.fail("refusing a Redis that already holds keys: the lease tests empty the databases they use")
    return {"client": client, "clients": clients, "run_id": info["run_id"], "port": port}


@pytest.fixture
def real(identity):
    client = identity["client"]
    yield client
    info = client.info("server")
    assert info["run_id"] == identity["run_id"] and int(info["tcp_port"]) == identity["port"], \
        "the server changed under the tests; not emptying it"
    for each in identity["clients"].values():
        each.flushdb()


@pytest.fixture
def budget_db(identity, real):
    return identity["clients"][1]


@pytest.fixture
def store_db(identity, real):
    return identity["clients"][2]


def lapse(client, key: str) -> None:
    """Let `key` expire for real: one millisecond of life left, then wait until Redis says it is gone."""
    client.pexpire(key, 1)
    deadline = time.monotonic() + 2
    while client.exists(key):
        assert time.monotonic() < deadline, f"{key} did not expire"
        time.sleep(0.005)


def stored(client, key):
    value = client.get(key)
    return value.decode() if isinstance(value, bytes) else value


# ------------------------------------------------------------------ the scripts themselves
def test_renewal_and_release_check_the_owner_token_on_a_real_redis(real):
    owner = SyncLease(real, LOCK, 300)
    assert owner.acquire()
    assert 299_000 < real.pttl(LOCK) <= 300_000

    real.pexpire(LOCK, 5_000)                            # most of the term gone
    assert owner.renew() and real.pttl(LOCK) > 299_000, "renewed to a full term by the script"

    stranger = SyncLease(real, LOCK, 300)
    stranger.held = True                                 # believes it holds it; it never did
    assert stranger.renew() is False and stranger.lost
    assert SyncLease(real, LOCK, 300).release() is False
    impostor = SyncLease(real, LOCK, 300)
    impostor.held = True
    assert impostor.release() is False
    assert stored(real, LOCK) == owner.token

    assert owner.release() is True and not real.exists(LOCK)


def test_after_real_expiry_the_old_worker_can_neither_renew_nor_release_nor_write(real):
    old = SyncLease(real, LOCK, 300)
    assert old.acquire()
    lapse(real, LOCK)
    new = SyncLease(real, LOCK, 300)
    assert new.acquire()
    before = real.pttl(LOCK)

    def delayed():
        stale = SyncLease(real, LOCK, 300)
        stale.token, stale.held = old.token, True
        return stale

    assert delayed().renew() is False
    assert delayed().release() is False
    assert delayed().fenced_set(["forecast:refresh:stub:premier_league"], '{"by": "old"}', [60]) is False
    assert delayed().fenced_delete([LOCK]) is False
    assert stored(real, LOCK) == new.token and real.pttl(LOCK) <= before, "not extended by the old worker"
    assert not real.exists("forecast:refresh:stub:premier_league")

    assert new.fenced_set(["forecast:refresh:stub:premier_league", "forecast:refresh:stub:premier_league:stale"],
                          '{"by": "new"}', [60, 120]) is True
    assert stored(real, "forecast:refresh:stub:premier_league") == '{"by": "new"}'
    assert 0 < real.ttl("forecast:refresh:stub:premier_league") <= 60
    assert 60 < real.ttl("forecast:refresh:stub:premier_league:stale") <= 120
    assert new.release() is True


def test_a_crashed_workers_lease_lapses_and_is_taken_over_on_a_real_redis(real):
    dead = SyncLease(real, LOCK, 300)
    assert dead.acquire()                                # ... and nobody ever renews or releases it
    assert SyncLease(real, LOCK, 300).acquire() is False
    lapse(real, LOCK)
    successor = SyncLease(real, LOCK, 300)
    assert successor.acquire() and stored(real, LOCK) == successor.token
    assert successor.release()


# ------------------------------------------------------------------ the forecast pass on a real Redis
def test_a_forecast_pass_on_a_real_redis_renews_its_lease_and_shuts_out_a_second_caller(real):
    clock = Clock(START)
    h = harness(clock, real, ["premier_league"])
    inside, release = hold_inside_the_fetch(h, "caller A")
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its request")
    lease = a._lease

    real.pexpire(LOCK, 1_000)                            # as if the term were nearly over
    assert ticker.tick() and real.pttl(LOCK) > 299_000, "the real renewal script ran"
    report_b = InThread(lambda: service(h).ensure_synced(force=False), "caller B").join()
    assert "already running" in report_b["error"]

    release.set()
    report_a = first.join()
    assert report_a["competitions"]["premier_league"]["fetched"] == 1
    assert [key for key, _ in h.provider.calls] == ["premier_league"]
    assert h.budget.used_today() == 1, "the real budget counter moved once"
    assert not real.exists(LOCK) and not lease.renewing


def test_on_a_real_redis_a_late_answer_after_expiry_writes_nothing(real):
    clock = Clock(START)
    h = harness(clock, real, ["premier_league", "serie_a"])
    inside, release = hold_inside_the_fetch(h, "caller A", "premier_league")
    a = service(h)
    a.lease_waiter = Ticker()                            # never ticked: A's renewer is stalled
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its premier_league request")

    lapse(real, LOCK)
    clock.now = START + timedelta(seconds=301)
    report_b = InThread(lambda: service(h).ensure_synced(force=False), "caller B").join()
    assert sorted(report_b["competitions"]) == ["premier_league", "serie_a"]

    release.set()
    report_a = first.join()
    taken_over = START + timedelta(seconds=301)
    assert report_a.get("lease_lost") is True and report_a["competitions"] == {}
    assert [key for key, _ in h.provider.calls] == ["premier_league", "premier_league", "serie_a"]
    assert h.budget.used_today() == 3
    slot = a.policy.slot("premier_league")
    assert slot["fetched_at"] == taken_over.isoformat() and slot["outcome"] == OUTCOME_SAME_DAY_RUN
    pending = h.cache.get(a._pending_key("premier_league"))
    assert [item["fetched_at"] for item in pending] == [taken_over.isoformat()]
    assert not real.exists(LOCK)
    assert not [t for t in threading.enumerate() if t.name.endswith("lease-renewal") and t.is_alive()]


# ------------------------------------------------------------------ across databases, as deployed
def test_on_a_real_redis_a_reservation_is_owner_checked_across_databases(real, budget_db):
    """The lease in one database, the budget counter in another: the reservation script reads the
    first and moves the second in one step, and refuses a stale owner without moving anything."""
    clock = Clock(START)
    budget = RequestBudget("gameforecast", 8, client=budget_db, now=clock)
    owner = SyncLease(real, LOCK, 300)
    assert owner.acquire()
    with lease_scope(owner):
        budget.consume(reason="fetch")
    assert budget.used_today() == 1 and real.get(budget._usage_key()) is None, "counted in the budget's database"

    lapse(real, LOCK)
    successor = SyncLease(real, LOCK, 300)
    assert successor.acquire()
    stale = SyncLease(real, LOCK, 300)
    stale.token, stale.held = owner.token, True
    with pytest.raises(LeaseLost):
        budget._reserve(budget._usage_key(), 1, stale)        # the script itself, past any early check
    assert budget.used_today() == 1, "the stale reservation moved the counter"
    with lease_scope(successor):
        budget.consume(reason="fetch")
    assert budget.used_today() == 2
    assert successor.release()


def test_on_a_real_redis_provider_bookkeeping_is_fenced_across_databases(real, store_db):
    store = MatchCache(client=store_db)
    key = "provider:gameforecast:pages:premier_league"
    owner = SyncLease(real, LOCK, 300)
    assert owner.acquire()
    with lease_scope(owner):
        control_set(store, key, {"pages": 2, "by": "owner"}, 60, 60)
    assert store.get(key) == {"pages": 2, "by": "owner"} and real.get(key) is None

    lapse(real, LOCK)
    successor = SyncLease(real, LOCK, 300)
    assert successor.acquire()
    stale = SyncLease(real, LOCK, 300)
    stale.token, stale.held = owner.token, True
    with lease_scope(stale), pytest.raises(LeaseLost):
        control_set(store, key, {"pages": 1, "by": "stale"}, 60, 60)
    assert store.get(key) == {"pages": 2, "by": "owner"}, "the stale worker replaced the page count"
    with lease_scope(successor):
        control_set(store, key, {"pages": 3, "by": "successor"}, 60, 60)
    assert store.get(key)["by"] == "successor"
    assert successor.release()
