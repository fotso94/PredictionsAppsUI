"""
A lease one worker holds in Redis while it spends a shared provider allowance.

The forecast pass used to take a plain key that expired after five minutes and was never renewed.
A pass that outlived it - slow responses, a slow database, a paused process - lost the lock without
knowing, a second worker took it, and the two then overlapped: duplicate paid requests, and the
older worker's late writes landing over the newer one's.

What this module provides, and nothing more:

- **Renewal.** A small daemon thread extends the lease every third of its term while the work runs,
  so a healthy pass keeps exclusive ownership for as long as it takes.
- **Owner-checked, atomic renewal and release.** Both are one Lua script that compares the stored
  value with this worker's unique token before touching the key, so a worker whose lease expired
  and was taken over can neither extend nor delete its successor's lease.
- **Loss is sticky.** Once a renewal is refused or cannot be confirmed (Redis unreachable, timeout),
  the lease is marked lost for good; every later check fails without asking Redis again.
- **Fenced writes, wherever the store lives.** `fenced_set_on` / `fenced_delete_on` apply a write
  only if the lease is still this worker's, checked inside the same Lua script as the write. The
  script reads the lease in the lease's own Redis database and writes in the target store's, so
  the forecast cache (match-data database), the provider's own bookkeeping (same) and the request
  budget (rate-limit database) are all fenced by the one lease. A store on a different Redis
  server cannot be fenced and is refused, never written unfenced.
- **The active lease.** `lease_scope` makes the lease visible to code the pass calls into without
  passing it down: `RequestBudget.consume` reserves through an owner-checked script
  (`budget.FENCED_RESERVE_LUA`), and provider bookkeeping writes go through `control_set`.
- **No lease without Redis.** A lease that cannot be taken - no Redis client, or Redis failing -
  is not taken, and the pass that needed it does not fetch.

A crashed worker's lease simply expires: nobody renews it, and another worker takes it over after
at most one term. Nothing here makes a provider request exactly-once; the boundary is stated in
docs/evidence/policy-round-2026-10-18.md, section 9.
"""
from __future__ import annotations

import contextvars
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Extend the lease to a full term, only if this worker still holds it.
RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

#: Delete the lease, only if this worker still holds it.
RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

#: Run on the TARGET store's client. ARGV[1] is the lease's database, ARGV[2] the lease key, ARGV[3]
#: the owner token, ARGV[4] the target's own database, ARGV[5] the payload and ARGV[6..] one TTL per
#: key. The lease is read and every key written inside one script, so nothing can come between the
#: check and the write. The script always ends in the target's database (restoring the caller's
#: selection on servers older than Redis 7, which does not propagate a script's SELECT anyway).
FENCED_SET_SCRIPT = """
redis.call('select', ARGV[1])
local owner = redis.call('get', ARGV[2])
redis.call('select', ARGV[4])
if owner ~= ARGV[3] then
  return 0
end
for i = 1, #KEYS do
  redis.call('set', KEYS[i], ARGV[5], 'EX', ARGV[i + 5])
end
return 1
"""

#: As above; every key in KEYS is deleted only if the lease is still the owner's.
FENCED_DELETE_SCRIPT = """
redis.call('select', ARGV[1])
local owner = redis.call('get', ARGV[2])
redis.call('select', ARGV[4])
if owner ~= ARGV[3] then
  return 0
end
for i = 1, #KEYS do
  redis.call('del', KEYS[i])
end
return 1
"""


#: What `SyncLease.acquire` records when the lease is simply someone else's.
HOLDER_REFUSAL = "another worker holds the lease"


class LeaseLost(Exception):
    """This worker does not hold its lease, or could not confirm that it does.

    Deliberately not a `ProviderError`: nothing is wrong with any provider, so the provider chains
    must not pause, cool down or mark a provider failed because of it.
    """


# ---------------------------------------------------------------------- the active lease
_spend_guard: "contextvars.ContextVar[Optional[Callable[[], None]]]" = contextvars.ContextVar(
    "provider_spend_guard", default=None)
_active_lease: "contextvars.ContextVar[Optional[SyncLease]]" = contextvars.ContextVar(
    "provider_active_lease", default=None)


def check_spend_guard() -> None:
    """Run the guard installed for this thread's current work, if any. Raises `LeaseLost`."""
    guard = _spend_guard.get()
    if guard is not None:
        guard()


def active_lease() -> Optional["SyncLease"]:
    """The lease the current work runs under, or None outside a managed pass."""
    return _active_lease.get()


@contextmanager
def guard_spending(check: Callable[[], None]) -> Iterator[None]:
    """Make every budget reservation in this context run `check` first."""
    token = _spend_guard.set(check)
    try:
        yield
    finally:
        _spend_guard.reset(token)


@contextmanager
def lease_scope(lease: "SyncLease") -> Iterator[None]:
    """Run the enclosed work under `lease`: spending and control-state writes are owner-checked."""
    lease_token = _active_lease.set(lease)
    guard_token = _spend_guard.set(lease.confirm)
    try:
        yield
    finally:
        _spend_guard.reset(guard_token)
        _active_lease.reset(lease_token)


def control_set(store: Any, key: str, value: Any, ttl: int, stale_ttl: int) -> None:
    """Write shared control state to a `MatchCache`: plainly outside a managed pass, fenced inside one.

    Control state is what decides what the next pass does - page counts that price a turn, league
    ids and negative-discovery markers, the provider's own reading of its window. Inside a pass only
    the lease's holder may change it; a stale worker's write raises `LeaseLost` and changes nothing.
    """
    lease = _active_lease.get()
    if lease is None:
        store.set(key, value, ttl, stale_ttl=stale_ttl)
        return
    FencedCache(store, lease).set(key, value, ttl, stale_ttl)


def _redis_of(store: Any) -> Any:
    reach = getattr(store, "_redis", None)
    return reach() if callable(reach) else None


def _location(client: Any) -> Tuple[Optional[Tuple[Any, Any, Any]], int]:
    """(server, database) of a redis-py client, or (None, 0) for anything else (the test stand-ins)."""
    kwargs = getattr(getattr(client, "connection_pool", None), "connection_kwargs", None)
    if not isinstance(kwargs, dict):
        return None, 0
    return (kwargs.get("host"), kwargs.get("port"), kwargs.get("path")), int(kwargs.get("db") or 0)


# ---------------------------------------------------------------------- the lease
Waiter = Callable[[float, threading.Event], bool]


class SyncLease:
    """One worker's claim on `key`, held for `ttl_seconds` at a time and renewed while it works.

    There is no lease without Redis: with no client, `acquire` refuses and says why.

    `waiter(seconds, stop)` paces the renewal worker; it returns True when the worker should stop.
    The default waits on the stop event, so stopping is immediate. Tests pass a controlled one.
    """

    def __init__(self, client: Any, key: str, ttl_seconds: int, *, renew_every: Optional[float] = None,
                 waiter: Optional[Waiter] = None, name: str = "sync"):
        self.client = client
        self.key = key
        self.ttl_seconds = max(int(ttl_seconds), 1)
        self.renew_every = float(renew_every) if renew_every else max(self.ttl_seconds / 3.0, 1.0)
        self.token = uuid.uuid4().hex
        self.name = name
        self.held = False
        self.lost_reason: Optional[str] = None
        self.refusal: Optional[str] = None
        self.renewals = 0
        self._waiter = waiter
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._io = threading.Lock()          # one Redis call at a time between owner and renewer
        self._thread: Optional[threading.Thread] = None
        self._scripts: Dict[Tuple[int, str], Any] = {}

    # ------------------------------------------------------------------ state
    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    @property
    def renewing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def lose(self, reason: str) -> None:
        """Mark the lease lost for good; every later check, write and reservation is refused."""
        if not self._lost.is_set():
            self.lost_reason = reason
            self._lost.set()
            logger.warning("%s lease lost: %s", self.name, reason)

    def _run(self, client: Any, source: str, keys: Sequence[str], args: Sequence[Any]) -> Any:
        """Run one of the scripts above atomically on `client` (EVALSHA, loading it if needed).

        `register_script` rather than `eval` by name: the request budget probes its client for `eval`
        to choose its own reservation path, and the lease must not change what it finds.
        """
        slot = (id(client), source)
        script = self._scripts.get(slot)
        if script is None:
            script = self._scripts[slot] = client.register_script(source)
        return script(keys=list(keys), args=list(args))

    # ------------------------------------------------------------------ acquire, renew, release
    def acquire(self) -> bool:
        """Take the lease if nobody holds it. No Redis, or a Redis that fails, is a refusal."""
        if self.client is None:
            self.refusal = "no Redis to coordinate through; a provider-fetching pass needs one"
            self.held = False
            return False
        try:
            with self._io:
                self.held = bool(self.client.set(self.key, self.token, nx=True, ex=self.ttl_seconds))
        except Exception as exc:
            self.refusal = f"the lease could not be taken: {exc}"
            logger.warning("%s lease could not be taken (%s); not proceeding", self.name, exc)
            self.held = False
            return False
        if not self.held:
            self.refusal = HOLDER_REFUSAL
        return self.held

    def renew(self) -> bool:
        """Extend the lease to a full term if it is still this worker's. False marks it lost."""
        if self._lost.is_set() or not self.held:
            return False
        try:
            with self._io:
                answer = self._run(self.client, RENEW_SCRIPT, [self.key], [self.token, self.ttl_seconds * 1000])
        except Exception as exc:
            self.lose(f"renewal could not be confirmed: {exc}")
            return False
        if int(answer or 0) != 1:
            self.lose("the lease is no longer this worker's: it expired or another worker holds it")
            return False
        self.renewals += 1
        return True

    def confirm(self) -> None:
        """Raise `LeaseLost` unless the lease is still this worker's; renews it as it checks."""
        if not self.renew():
            raise LeaseLost(self.lost_reason or f"the {self.name} lease is not held")

    def release(self) -> bool:
        """Stop renewing, then delete the lease if it is still this worker's. Never raises."""
        self.stop_renewing()
        if not self.held:
            return False                     # nothing of this worker's to give back
        released = False
        try:
            with self._io:
                released = int(self._run(self.client, RELEASE_SCRIPT, [self.key], [self.token]) or 0) == 1
        except Exception as exc:
            logger.warning("%s lease could not be released (%s); it expires on its own", self.name, exc)
        self.held = False
        return released

    # ------------------------------------------------------------------ fencing
    def fence_args(self, target: Any) -> List[Any]:
        """[lease database, lease key, token, target database] for a script run on `target`.

        Raises `LeaseLost` when the lease is not held or `target` is not on the lease's Redis server:
        a check in one server and a write in another cannot be made one step, so it is not made.
        """
        if self._lost.is_set() or not self.held:
            raise LeaseLost(self.lost_reason or f"the {self.name} lease is not held")
        mine, lease_db = _location(self.client)
        if target is self.client:
            return [lease_db, self.key, self.token, lease_db]
        theirs, target_db = _location(target)
        if mine is None or theirs is None or mine != theirs:
            reason = "the store to be written is not on the lease's Redis server; the write cannot be fenced"
            self.lose(reason)
            raise LeaseLost(reason)
        return [lease_db, self.key, self.token, target_db]

    def fenced_set_on(self, target: Any, keys: Sequence[str], payload: str, ttls: Sequence[int]) -> bool:
        """Write `payload` to every key of `target`, each with its TTL, only while the lease is held."""
        try:
            fence = self.fence_args(target)
        except LeaseLost:
            return False
        args: List[Any] = fence + [payload] + [max(int(ttl), 1) for ttl in ttls]
        return self._fenced(target, FENCED_SET_SCRIPT, keys, args)

    def fenced_delete_on(self, target: Any, keys: Sequence[str]) -> bool:
        try:
            fence = self.fence_args(target)
        except LeaseLost:
            return False
        return self._fenced(target, FENCED_DELETE_SCRIPT, keys, fence)

    def fenced_set(self, keys: Sequence[str], payload: str, ttls: Sequence[int]) -> bool:
        return self.fenced_set_on(self.client, keys, payload, ttls)

    def fenced_delete(self, keys: Sequence[str]) -> bool:
        return self.fenced_delete_on(self.client, keys)

    def _fenced(self, target: Any, script: str, keys: Sequence[str], args: List[Any]) -> bool:
        try:
            with self._io:
                answer = self._run(target, script, keys, args)
        except Exception as exc:
            self.lose(f"a write could not be fenced: {exc}")
            return False
        if int(answer or 0) != 1:
            self.lose("a write was refused: the lease is no longer this worker's")
            return False
        return True

    # ------------------------------------------------------------------ the renewal worker
    def start_renewing(self) -> None:
        if not self.held or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._renew_loop, name=f"{self.name}-lease-renewal", daemon=True)
        self._thread.start()

    def _wait(self) -> bool:
        if self._waiter is not None:
            return bool(self._waiter(self.renew_every, self._stop))
        return self._stop.wait(self.renew_every)

    def _renew_loop(self) -> None:
        try:
            while not self._wait():
                if not self.renew():
                    return
        except BaseException as exc:  # a dead renewer must never leave the owner believing it holds
            self.lose(f"the renewal worker failed: {exc!r}")
        finally:
            exited = getattr(self._waiter, "exited", None)
            if callable(exited):
                exited()

    def stop_renewing(self, timeout: float = 5.0) -> bool:
        """Stop the renewal worker and wait for it. True once it is no longer running."""
        self._stop.set()
        wake = getattr(self._waiter, "wake", None)
        if callable(wake):
            wake()
        thread = self._thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(timeout)
        return not thread.is_alive()


class FencedCache:
    """A `MatchCache` whose writes land only while `lease` is held, checked atomically with each write.

    Reads go straight to the cache. A write the lease does not cover - lost, never held, or a store
    on another Redis server, or no Redis at all - raises `LeaseLost`, so the work that tried it stops
    there. The stored format is MatchCache's own: JSON, with the parallel `:stale` copy under its own
    TTL.
    """

    def __init__(self, inner: Any, lease: SyncLease):
        self._inner = inner
        self._lease = lease

    def _target(self) -> Any:
        client = _redis_of(self._inner)
        if client is None:
            raise LeaseLost("no Redis behind this store: the write cannot be fenced")
        return client

    def set(self, key: str, value: Any, ttl: int, stale_ttl: Optional[int] = None) -> None:
        from app.services.match_cache import STALE_TTL_SECONDS
        stale_ttl = STALE_TTL_SECONDS if stale_ttl is None else stale_ttl
        payload = json.dumps(value, default=str)
        if not self._lease.fenced_set_on(self._target(), [key, f"{key}:stale"], payload, [ttl, stale_ttl]):
            raise LeaseLost(self._lease.lost_reason or "write refused: the lease is not held")

    def delete(self, key: str) -> None:
        if not self._lease.fenced_delete_on(self._target(), [key, f"{key}:stale"]):
            raise LeaseLost(self._lease.lost_reason or "delete refused: the lease is not held")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
