"""
The daily allowance across a UTC day boundary, with a controlled clock.

`tests/providers/test_request_budget.py` covers counting and attribution within one day, through a
Redis stand-in that has no EVAL. This file covers the two things that one cannot reach:

  1. the day boundary itself - a spent allowance has to come back on its own, with no restart, no
     manual reset and nothing that "clears" a counter, purely because the counter keys are
     day-scoped and the new day's key does not exist yet;
  2. the atomic reserve - redis-py has EVAL, so the Lua script is the path a healthy deployment
     takes, and every test that uses a fake without `eval` exercises the fallback instead;
  3. what a FAILING EVAL does. A store that declines EVAL but still answers GET/INCRBY has to
     keep metering, and one that answers nothing has to stop granting (small plan) or say plainly
     that it is no longer enforcing anything (large plan). Routing both to "store unavailable"
     removed a 1,200/day ceiling for a whole day while the status endpoint read as untouched.

The state on 2026-09-18 is the worked example throughout: the gameforecast counter read 9 against a
limit of 8 because an older build (1f396e4) incremented first and checked after, so the refusal of
the 9th request counted itself as a spend. The current reserve cannot do that, and the tests below
pin both halves - the refusal that must not count, and the over-limit day that must still recover.

No network, no real Redis, no sleeping: a fake clock and an in-memory stand-in.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.providers import budget as budget_module
from app.services.providers.base import ProviderQuotaError
from app.services.providers.budget import (
    KEY_TTL_SECONDS, RequestBudget, budget_key, by_reason_key, refused_key,
)
from tests.providers.support import FakeRedis

#: Late on the day the gameforecast allowance was spent: one hour before the reset.
DAY_ONE = datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc)
ONE_HOUR = 3600


class Clock:
    """Fake clock. `tick` moves it the way waiting does - it never touches the real one."""

    def __init__(self, start: datetime = DAY_ONE):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class LuaRedis(FakeRedis):
    """FakeRedis that speaks EVAL, so the atomic reserve runs instead of the fallback.

    Executes the reserve contract the script implements - check the limit, and only then move the
    usage counter - and records what it was asked to run, so a test can prove the production path
    was taken and that nothing incremented the usage key behind the script's back.
    """

    def __init__(self):
        super().__init__()
        self.scripts = []
        self.direct_incrby = []

    def _bump(self, key, amount):
        self.store[key] = int(self.store.get(key) or 0) + int(amount)
        return self.store[key]

    def incrby(self, key, amount):  # only the fallback path calls this
        self.direct_incrby.append(key)
        return self._bump(key, amount)

    def eval(self, script, numkeys, *args):
        self.scripts.append(script)
        usage_key, refused = list(args[:numkeys])
        amount, limit, ttl = (int(a) for a in args[numkeys:])
        used = int(self.store.get(usage_key) or 0)
        if limit > 0 and used + amount > limit:
            if self._bump(refused, amount) == amount:
                self.ttls[refused] = ttl
            return [used, 0]
        new_value = self._bump(usage_key, amount)
        if new_value == amount:
            self.ttls[usage_key] = ttl
        return [new_value, 1]


class BrokenEvalRedis(LuaRedis):
    """A reachable store that will not run EVAL: NOPERM, a Cluster CROSSSLOT error, a read replica.

    GET and INCRBY still work, which is the whole point: the store can count, it just cannot count
    atomically.
    """

    def eval(self, *args, **kwargs):
        raise RuntimeError("NOPERM this user has no permissions to run the 'eval' command")


class UnreachableRedis(BrokenEvalRedis):
    """A store that answers nothing. Every command raises, not only EVAL."""

    def get(self, key):
        raise RuntimeError("Connection closed by server")

    def incrby(self, key, amount):
        raise RuntimeError("Connection closed by server")

    def hincrby(self, key, field, amount):
        raise RuntimeError("Connection closed by server")

    def hgetall(self, key):
        raise RuntimeError("Connection closed by server")


# ------------------------------------------------------------------ the atomic path
def test_the_atomic_reserve_is_the_path_a_client_with_eval_takes():
    """Every real client has EVAL, so the script is what production runs. Nothing may bypass it."""
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client)

    for _ in range(8):
        budget.consume()
    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()

    assert "(8/8 used)" in str(refused.value)
    assert client.scripts and set(client.scripts) == {budget_module._RESERVE_LUA}
    assert client.direct_incrby == [], "the usage counter must only move inside the script"
    assert client.ttls[budget_key("gameforecast")] == KEY_TTL_SECONDS


def test_the_reserve_checks_the_limit_before_it_increments():
    """The shape of the 2026-09-18 residue: increment first, check after, and a refusal counts.

    Kept as a guard on the script text because a reordering here is invisible in behaviour until a
    day's counter is already wrong and cannot be recovered.
    """
    script = budget_module._RESERVE_LUA

    assert script.index("return {used, 0}") < script.index("redis.call('INCRBY', KEYS[1]")


def test_a_refused_reservation_is_never_counted_as_a_spend():
    """The exact accounting that produced 9 against a limit of 8. A refusal sends nothing."""
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client)
    for _ in range(8):
        budget.consume(reason="fetch")

    for _ in range(3):
        with pytest.raises(ProviderQuotaError):
            budget.consume()

    assert budget.used_today() == 8, "refusals must not push the counter past the limit"
    assert budget.refused_today() == 3
    snapshot = budget.snapshot()
    assert snapshot["over_limit"] is False
    # and the day reconciles: everything counted as spent is attributed to a reason
    assert sum(snapshot["by_reason"].values()) == snapshot["used_today"] == 8


# ------------------------------------------------------------------ the day boundary
def test_a_spent_allowance_comes_back_on_the_next_utc_day_with_no_reset():
    """Nothing resets the counter. The new day simply reads a key that does not exist yet."""
    clock = Clock()
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client, now=clock)
    for _ in range(8):
        budget.consume()
    with pytest.raises(ProviderQuotaError):
        budget.consume()
    assert budget.remaining() == 0 and budget.can_afford() is False

    clock.tick(ONE_HOUR)  # 23:00 -> 00:00, the provider's reset

    # same object, nothing restarted, no counter cleared
    assert budget.can_afford() is True and budget.remaining() == 8
    budget.consume()
    assert budget.used_today() == 1
    assert client.store[budget_key("gameforecast", DAY_ONE)] == 8, "yesterday's count stays honest"
    assert budget_key("gameforecast", clock()) != budget_key("gameforecast", DAY_ONE)


def test_a_counter_above_the_limit_refuses_cleanly_today_and_still_recovers_tomorrow():
    """Today's live reading: 9 spent against a limit of 8, left by a build that counted refusals."""
    clock = Clock()
    client = LuaRedis()
    client.store[budget_key("gameforecast", DAY_ONE)] = 9
    budget = RequestBudget("gameforecast", 8, client=client, now=clock)

    assert budget.used_today() == 9
    assert budget.remaining() == 0, "remaining is clamped: a negative allowance is not a thing"
    assert budget.can_afford(1) is False
    snapshot = budget.snapshot()
    assert snapshot["remaining_today"] == 0 and snapshot["over_limit"] is True
    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()
    assert "(9/8 used)" in str(refused.value)
    assert budget.used_today() == 9, "a refusal must not push an over-limit counter further"

    clock.tick(ONE_HOUR)

    assert budget.remaining() == 8 and budget.snapshot()["over_limit"] is False
    budget.consume()
    assert budget.used_today() == 1


def test_the_refused_and_attribution_counters_are_day_scoped_too():
    """A new day starts clean on all three counters, or yesterday's noise is read as today's."""
    clock = Clock()
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 1, client=client, now=clock)
    budget.consume(reason="discovery")
    with pytest.raises(ProviderQuotaError):
        budget.consume(reason="fetch")
    assert budget.refused_today() == 1 and budget.by_reason() == {"discovery": 1}

    clock.tick(ONE_HOUR)

    assert budget.refused_today() == 0 and budget.by_reason() == {}
    assert client.store[refused_key("gameforecast", DAY_ONE)] == 1, "yesterday is still on record"
    assert client.store[by_reason_key("gameforecast", DAY_ONE)] == {"discovery": 1}


# ------------------------------------------------------------------ a broken store
def test_an_eval_failure_against_a_reachable_store_still_meters_the_request():
    """The metering regression, in the shape it was measured: a 1,200/day ceiling that vanished.

    With EVAL failing (a Cluster CROSSSLOT error, NOPERM, a read replica) five consume() calls
    all succeeded, five real outbound requests were paid for, and the day afterwards read
    used_today 0 / remaining_today 1,200 / enforced true while by_reason showed fetch 5. The
    ceiling had stopped existing for the rest of the day and the status endpoint said the plan
    was untouched.

    A store that refuses EVAL still answers GET and INCRBY, so it can still count. Counting
    non-atomically is weaker than the script - racing callers can overshoot - but it is bounded
    and it is visible in the counter, which is strictly better than not counting at all.
    """
    client = BrokenEvalRedis()
    budget = RequestBudget("livescore", 1200, client=client)

    for _ in range(5):
        budget.consume(reason="fetch")

    assert budget.used_today() == 5, "five paid-for requests must be five on the counter"
    assert budget.remaining() == 1195
    assert client.store[budget_key("livescore")] == 5
    snapshot = budget.snapshot()
    assert snapshot["used_today"] == 5 and snapshot["remaining_today"] == 1195
    assert snapshot["unmetered_today"] == 0 and snapshot["enforced"] is True
    assert sum(snapshot["by_reason"].values()) == snapshot["used_today"], "the day reconciles"


def test_the_ceiling_still_refuses_when_only_the_atomic_path_is_broken():
    """Metering is not the point on its own: the limit has to keep refusing the 1,201st request."""
    client = BrokenEvalRedis()
    client.store[budget_key("livescore")] = 1200
    budget = RequestBudget("livescore", 1200, client=client)

    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()

    assert "(1200/1200 used)" in str(refused.value)
    assert budget.used_today() == 1200, "a refusal must not advance the counter here either"
    assert budget.refused_today() == 1


def test_a_small_plan_that_cannot_reserve_atomically_is_metered_not_refused():
    """An 8-a-day plan on a store that can still count is metered, so the 9th is still refused."""
    client = BrokenEvalRedis()
    budget = RequestBudget("gameforecast", 8, client=client)

    for _ in range(8):
        budget.consume(reason="fetch")
    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()

    assert "(8/8 used)" in str(refused.value)
    assert budget.used_today() == 8 and budget.refused_today() == 1
    assert budget.by_reason() == {"fetch": 8}


def test_a_small_plan_fails_closed_when_the_store_answers_nothing_at_all():
    """Fail-closed is unchanged, and now it means what it says: the store really is gone.

    Every command raises here, not only EVAL, so the counting path cannot meter the request
    either - and a 10-a-day plan spent blind is a plan that is gone.
    """
    client = UnreachableRedis()
    budget = RequestBudget("gameforecast", 8, client=client)

    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()

    assert "budget store unavailable" in str(refused.value)
    assert client.store == {}, "nothing was reserved, so nothing was counted"
    assert budget.unmetered_today() == 0, "a refused request was never let out"


def test_a_large_plan_granted_uncounted_is_reported_as_spent_not_as_untouched():
    """The store is gone, the site stays up - but the snapshot must not claim a full allowance.

    This is the other half of the regression: a request granted while the counter could not be
    updated must never be attributed by reason (nothing could reconcile that number), and the
    snapshot has to show the requests as spent with the ceiling no longer enforced.
    """
    client = UnreachableRedis()
    budget = RequestBudget("livescore", 1200, client=client)

    for _ in range(5):
        budget.consume(reason="fetch")  # must not raise: a Redis blip is not worth going dark for

    assert budget.fail_open is True
    assert client.store == {}, "the store took nothing; there was nowhere to count"
    snapshot = budget.snapshot()
    assert snapshot["by_reason"] == {}, "an attribution the usage counter never saw is invented"
    assert snapshot["unmetered_today"] == 5 and snapshot["counted_today"] == 0
    assert snapshot["used_today"] == 5, "five requests went out; the day did not stay at zero"
    assert snapshot["remaining_today"] == 1195
    assert snapshot["enforced"] is False, "nothing is enforcing the ceiling while nothing counts"


def test_requests_granted_uncounted_do_not_follow_the_day_into_tomorrow():
    """The degraded reading is day-scoped like every counter, or yesterday's blip shadows today."""
    clock = Clock()
    budget = RequestBudget("livescore", 1200, client=UnreachableRedis(), now=clock)
    budget.consume()
    assert budget.snapshot()["unmetered_today"] == 1

    clock.tick(ONE_HOUR)

    assert budget.unmetered_today() == 0, "yesterday's uncounted requests are not today's"
    assert budget.snapshot()["used_today"] == 0
    budget.consume()
    assert budget.snapshot()["unmetered_today"] == 1, "and today's are recorded from today"


def test_a_client_without_eval_still_counts_and_still_refuses():
    """The fallback stays for the simple test doubles, and it must not over-grant single-threaded."""
    client = FakeRedis()
    budget = RequestBudget("gameforecast", 2, client=client)

    budget.consume()
    budget.consume()
    with pytest.raises(ProviderQuotaError):
        budget.consume()

    assert budget.used_today() == 2 and budget.refused_today() == 1
