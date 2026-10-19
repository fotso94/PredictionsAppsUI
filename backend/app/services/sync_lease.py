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
- **Fenced writes.** `fenced_set` / `fenced_delete` apply a write only if the lease is still this
  worker's, checked inside the same Lua script as the write: there is no gap between "still the
  owner?" and the write for another worker to step into.
- **A spending guard.** `guard_spending` installs a check that `RequestBudget.consume` runs before
  it reserves anything, so a worker that has lost its lease neither reserves allowance nor sends a
  request, whichever provider or page it was about to ask.

A crashed worker's lease simply expires: nobody renews it, and another worker takes it over after
at most one term. Nothing here makes a provider request exactly-once; see the forecast service and
docs/evidence/policy-round-2026-10-18.md, section 8, for the boundary.
"""
from __future__ import annotations

import contextvars
import json
import logging
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional, Sequence

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

#: KEYS[1] is the lease; KEYS[2..n] receive ARGV[2] with the TTL in ARGV[3..n+1], only if the lease
#: is still ARGV[1]'s. The check and the writes run as one script, so nothing can come between them.
FENCED_SET_SCRIPT = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then
  return 0
end
for i = 2, #KEYS do
  redis.call('set', KEYS[i], ARGV[2], 'EX', ARGV[i + 1])
end
return 1
"""

#: KEYS[2..n] are deleted only if the lease KEYS[1] is still ARGV[1]'s.
FENCED_DELETE_SCRIPT = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then
  return 0
end
for i = 2, #KEYS do
  redis.call('del', KEYS[i])
end
return 1
"""


class LeaseLost(Exception):
    """This worker no longer holds its lease, or could not confirm that it does.

    Deliberately not a `ProviderError`: nothing is wrong with any provider, so the provider chains
    must not pause, cool down or mark a provider failed because of it.
    """


# ---------------------------------------------------------------------- the spending guard
_spend_guard: "contextvars.ContextVar[Optional[Callable[[], None]]]" = contextvars.ContextVar(
    "provider_spend_guard", default=None)


def check_spend_guard() -> None:
    """Run the guard installed for this thread's current work, if any. Raises `LeaseLost`."""
    guard = _spend_guard.get()
    if guard is not None:
        guard()


@contextmanager
def guard_spending(check: Callable[[], None]) -> Iterator[None]:
    """Make every budget reservation in this context run `check` first."""
    token = _spend_guard.set(check)
    try:
        yield
    finally:
        _spend_guard.reset(token)


# ---------------------------------------------------------------------- the lease
Waiter = Callable[[float, threading.Event], bool]


class SyncLease:
    """One worker's claim on `key`, held for `ttl_seconds` at a time and renewed while it works.

    Without a Redis client there is nothing to coordinate through: the lease is unmanaged, always
    "held", and fenced writes fall back to plain ones - the best-effort behaviour the sync lock
    always had when Redis was not configured.

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
        self.renewals = 0
        self._waiter = waiter
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._io = threading.Lock()          # one Redis call at a time between owner and renewer
        self._thread: Optional[threading.Thread] = None
        self._scripts: dict = {}

    # ------------------------------------------------------------------ state
    @property
    def managed(self) -> bool:
        return self.client is not None

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    @property
    def renewing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _lose(self, reason: str) -> None:
        if not self._lost.is_set():
            self.lost_reason = reason
            self._lost.set()
            logger.warning("%s lease lost: %s", self.name, reason)

    def _run(self, source: str, keys: Sequence[str], args: Sequence[Any]) -> Any:
        """Run one of the scripts above atomically on the server (EVALSHA, loading it if needed).

        `register_script` rather than `eval` by name: the request budget probes its client for `eval`
        to choose its own reservation path, and the lease must not change what it finds.
        """
        script = self._scripts.get(source)
        if script is None:
            script = self._scripts[source] = self.client.register_script(source)
        return script(keys=list(keys), args=list(args))

    # ------------------------------------------------------------------ acquire, renew, release
    def acquire(self) -> bool:
        """Take the lease if nobody holds it. A store that fails here is not proceeded past."""
        if not self.managed:
            self.held = True
            return True
        try:
            with self._io:
                self.held = bool(self.client.set(self.key, self.token, nx=True, ex=self.ttl_seconds))
        except Exception as exc:
            logger.warning("%s lease could not be taken (%s); not proceeding", self.name, exc)
            self.held = False
        return self.held

    def renew(self) -> bool:
        """Extend the lease to a full term if it is still this worker's. False marks it lost."""
        if not self.managed:
            return True
        if self._lost.is_set() or not self.held:
            return False
        try:
            with self._io:
                answer = self._run(RENEW_SCRIPT, [self.key], [self.token, self.ttl_seconds * 1000])
        except Exception as exc:
            self._lose(f"renewal could not be confirmed: {exc}")
            return False
        if int(answer or 0) != 1:
            self._lose("the lease is no longer this worker's: it expired or another worker holds it")
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
        if not self.managed:
            self.held = False
            return True
        if not self.held:
            return False                     # nothing of this worker's to give back
        released = False
        try:
            with self._io:
                released = int(self._run(RELEASE_SCRIPT, [self.key], [self.token]) or 0) == 1
        except Exception as exc:
            logger.warning("%s lease could not be released (%s); it expires on its own", self.name, exc)
        self.held = False
        return released

    # ------------------------------------------------------------------ fenced writes
    def fenced_set(self, keys: Sequence[str], payload: str, ttls: Sequence[int]) -> bool:
        """Write `payload` to every key, each with its TTL, only while the lease is this worker's."""
        if self._lost.is_set() or not self.held:
            return False
        args: List[Any] = [self.token, payload] + [max(int(ttl), 1) for ttl in ttls]
        return self._fenced(FENCED_SET_SCRIPT, keys, args)

    def fenced_delete(self, keys: Sequence[str]) -> bool:
        if self._lost.is_set() or not self.held:
            return False
        return self._fenced(FENCED_DELETE_SCRIPT, keys, [self.token])

    def _fenced(self, script: str, keys: Sequence[str], args: List[Any]) -> bool:
        try:
            with self._io:
                answer = self._run(script, [self.key, *keys], args)
        except Exception as exc:
            self._lose(f"a write could not be fenced: {exc}")
            return False
        if int(answer or 0) != 1:
            self._lose("a write was refused: the lease is no longer this worker's")
            return False
        return True

    # ------------------------------------------------------------------ the renewal worker
    def start_renewing(self) -> None:
        if not self.managed or not self.held or self._thread is not None:
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
            self._lose(f"the renewal worker failed: {exc!r}")
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

    Reads go straight to the cache. A write the lease no longer covers raises `LeaseLost`, so the
    work that tried it stops there. The stored format is MatchCache's own: JSON, with the parallel
    `:stale` copy under its own TTL.
    """

    def __init__(self, inner: Any, lease: SyncLease):
        self._inner = inner
        self._lease = lease

    def set(self, key: str, value: Any, ttl: int, stale_ttl: Optional[int] = None) -> None:
        from app.services.match_cache import STALE_TTL_SECONDS
        stale_ttl = STALE_TTL_SECONDS if stale_ttl is None else stale_ttl
        if not self._lease.managed:
            self._inner.set(key, value, ttl, stale_ttl=stale_ttl)
            return
        payload = json.dumps(value, default=str)
        if not self._lease.fenced_set([key, f"{key}:stale"], payload, [ttl, stale_ttl]):
            raise LeaseLost(self._lease.lost_reason or "write refused: the lease is not held")

    def delete(self, key: str) -> None:
        if not self._lease.managed:
            self._inner.delete(key)
            return
        if not self._lease.fenced_delete([key, f"{key}:stale"]):
            raise LeaseLost(self._lease.lost_reason or "delete refused: the lease is not held")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
