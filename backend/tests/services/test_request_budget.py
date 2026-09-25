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

import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.services.providers import budget as budget_module
from app.services.providers.base import ProviderQuotaError
from app.services.providers.budget import (
    KEY_TTL_SECONDS, SCHEDULER_SENT_KEY, ProviderRateLimit, RequestBudget, budget_key,
    by_reason_key, refused_key, spending_for_task,
)
from app.services.providers.http import RateLimitReading
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


class _Transaction:
    """A MULTI/EXEC pipeline over the fake: queues reads and answers them as one step."""

    def __init__(self, client, transaction):
        self.client, self.transaction, self.queued = client, transaction, []

    def get(self, key):
        self.queued.append(("get", key))
        return self

    def hgetall(self, key):
        self.queued.append(("hgetall", key))
        return self

    def execute(self):
        self.client.transactions.append((self.transaction, list(self.queued)))
        return [getattr(self.client, command)(key) for command, key in self.queued]


class LuaRedis(FakeRedis):
    """FakeRedis that speaks EVAL, so the atomic reserve runs instead of the fallback.

    Executes the reserve contract the script implements - check the limit, then (inside a scheduler
    pass) the ledger, and only then move the usage counter - and records what it was asked to run,
    so a test can prove the production path was taken and that nothing incremented the usage key
    or the ledger behind the script's back. Its pipelines record what they were asked to read
    together.
    """

    def __init__(self):
        super().__init__()
        self.scripts = []
        self.direct_incrby = []
        self.direct_hincrby = []
        self.transactions = []

    def _bump(self, key, amount):
        self.store[key] = int(self.store.get(key) or 0) + int(amount)
        return self.store[key]

    def incrby(self, key, amount):  # only the fallback path calls this
        self.direct_incrby.append(key)
        return self._bump(key, amount)

    def hincrby(self, key, field, amount):  # by_reason, and the fallback path's ledger
        self.direct_hincrby.append(key)
        return super().hincrby(key, field, amount)

    def pipeline(self, transaction=True):
        return _Transaction(self, transaction)

    def eval(self, script, numkeys, *args):
        self.scripts.append(script)
        keys, argv = list(args[:numkeys]), list(args[numkeys:])
        usage_key, refused = keys[:2]
        amount, limit, ttl = (int(a) for a in argv[:3])
        used = int(self.store.get(usage_key) or 0)
        if limit > 0 and used + amount > limit:
            if self._bump(refused, amount) == amount:
                self.ttls[refused] = ttl
            return [used, 0]
        if len(keys) > 2:
            FakeRedis.hincrby(self, keys[2], argv[3], amount)
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


# ------------------------------------------------- our ceiling and the provider's window, together
#
# 2026-09-19T00:01:10Z, replayed: the UTC-day counter was clean, two requests went out, and the
# provider refused the third with "you have exceeded the DAILY quota" while our counter still
# showed five of eight left. Two independent constraints, and only one of them was reporting the
# truth about what the provider would serve. A request now goes out only when BOTH allow it.

DAY_TWO = datetime(2026, 9, 19, 0, 1, 10, tzinfo=timezone.utc)


def _record(client, now, remaining, limit=10, reset_seconds=25972, status=429):
    """Store one reading exactly as the HTTP client would, without making a request."""
    ProviderRateLimit("gameforecast", client=client, now=now).record(
        RateLimitReading(provider="gameforecast", limit=limit, remaining=remaining,
                         reset_seconds=reset_seconds, observed_at=now, status_code=status))


def test_a_request_is_refused_when_the_provider_says_zero_although_our_counter_has_room():
    """Tonight's defect: five of eight left by our count, nothing left by the provider's."""
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client, now=DAY_TWO)
    budget.consume(reason="fetch")
    budget.consume(reason="discovery")
    assert budget.remaining() == 6, "our own counter still has room"

    _record(client, DAY_TWO, remaining=0)

    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume(reason="fetch")

    message = str(refused.value)
    assert "gameforecast itself reports 0 request(s) left in its own window" in message
    assert "its window resets in 25972s" in message
    assert "Our daily counter still shows 6 of 8 left" in message, \
        "the refusal has to name which of the two constraints stopped it"
    assert budget.used_today() == 2, "a request that was never sent must not be counted as spent"
    assert budget.refused_today() == 1, "but the refusal itself is counted"


def test_our_own_ceiling_still_refuses_when_it_is_the_smaller_number():
    """The cap we chose is not bypassed by a generous provider count. Nothing here retunes a limit."""
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client, now=DAY_TWO)
    _record(client, DAY_TWO, remaining=500, limit=500)

    for _ in range(8):
        budget.consume()
    with pytest.raises(ProviderQuotaError) as refused:
        budget.consume()

    assert "(8/8 used)" in str(refused.value)
    assert "refused by the daily ceiling we configured, not by the provider" in str(refused.value)
    assert budget.limited_by() == "our_configured_ceiling"


def test_the_binding_number_is_the_smaller_of_the_two():
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client, now=DAY_TWO)
    assert budget.remaining_effective() == 8, "with no reading, our counter is all there is"

    _record(client, DAY_TWO, remaining=2)
    assert budget.remaining_effective() == 2 and budget.limited_by() == "the_provider"
    assert budget.can_afford(2) is True and budget.can_afford(3) is False

    _record(client, DAY_TWO, remaining=8)
    assert budget.remaining_effective() == 8 and budget.limited_by() == "both"


def test_an_unknown_provider_count_constrains_nothing():
    """Unknown is not zero. A provider that publishes no header must keep working exactly as before."""
    budget = RequestBudget("gameforecast", 8, client=LuaRedis(), now=DAY_TWO)

    assert budget.provider_remaining() is None
    assert budget.can_afford(8) is True
    for _ in range(8):
        budget.consume()
    assert budget.used_today() == 8


# ------------------------------------------------------------------ what the status payload says
def test_unknown_stays_unknown_in_the_status_payload():
    """A provider we have never heard from must not read as spent, nor as a full allowance."""
    snapshot = RequestBudget("gameforecast", 8, client=LuaRedis(), now=DAY_TWO).snapshot()

    view = snapshot["provider_reported"]
    assert view["known"] is False
    assert view["remaining"] is None and view["limit"] is None and view["reset_at"] is None
    assert view["remaining"] != 0, "unknown must never be reported as zero"
    assert snapshot["effective_remaining_today"] == 8, "our own counter is all there is to go on"
    assert snapshot["limited_by"] == "our_configured_ceiling"
    # and every pre-existing key still means what it meant
    assert snapshot["daily_limit"] == 8 and snapshot["used_today"] == 0
    assert snapshot["remaining_today"] == 8 and snapshot["enforced"] is True


def test_the_status_payload_puts_the_two_accountings_side_by_side():
    """Tonight's divergence, published rather than reconciled: ours said 5 left, its said 0."""
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 8, client=client, now=DAY_TWO)
    for _ in range(3):
        budget.consume()
    _record(client, DAY_TWO, remaining=0)

    snapshot = budget.snapshot()

    assert (snapshot["used_today"], snapshot["remaining_today"]) == (3, 5)
    view = snapshot["provider_reported"]
    assert view["known"] is True
    assert (view["limit"], view["remaining"]) == (10, 0)
    assert view["reset_in_seconds"] == 25972
    assert view["observed_status"] == 429
    assert view["window_matches_utc_day"] is False and "different windows" in view["window_note"]
    assert snapshot["effective_remaining_today"] == 0 and snapshot["limited_by"] == "the_provider"


def test_a_reading_whose_window_has_turned_is_not_reported_as_a_live_zero():
    client = LuaRedis()
    clock = Clock(DAY_TWO)
    budget = RequestBudget("gameforecast", 8, client=client, now=clock)
    _record(client, DAY_TWO, remaining=0, reset_seconds=ONE_HOUR)
    assert budget.remaining_effective() == 0

    clock.tick(ONE_HOUR + 60)

    assert budget.provider_remaining() is None, "the window has turned; the old zero is not a fact"
    assert budget.remaining_effective() == 8
    view = budget.snapshot()["provider_reported"]
    assert view["known"] is True and view["window_expired"] is True and view["remaining"] is None


# ------------------------------------------------------------ who spent it: the scheduler's ledger
#
# `used_today` is the whole day's spend, and the scheduler moves it on its own. On 2026-09-25 at
# 17:42:01 UTC a browser test read livescore 730 -> 731 across a journey that spent nothing; the one
# request in the window was the scheduler's live poll a second earlier. These pin the ledger that
# lets that window be read exactly: what the scheduler sent, written with the counter and read with
# it, so "spent" minus "sent by the scheduler" is what everything else spent.
def _spent_by_others(before, after):
    """What moved `used_today` between two snapshots that the scheduler did not send."""
    return ((after["used_today"] - before["used_today"])
            - (after["scheduler_sent"]["total"] - before["scheduler_sent"]["total"]))


def test_a_scheduler_grant_moves_the_counter_and_the_ledger_in_the_same_script():
    client = LuaRedis()
    budget = RequestBudget("livescore", 1200, client=client)

    with spending_for_task("live") as spend:
        budget.consume()
    budget.consume()  # a page load, beside the pass: counted, not the scheduler's

    assert budget.used_today() == 2
    assert client.store[SCHEDULER_SENT_KEY] == {"livescore:live": 1}
    assert spend.granted == {"livescore": 1}
    assert set(client.scripts) == {budget_module._RESERVE_LUA}
    assert client.direct_incrby == [] and SCHEDULER_SENT_KEY not in client.direct_hincrby, \
        "the counter and the ledger must only move inside the script, together"


def test_the_ledger_is_written_after_the_limit_check_and_before_the_counter():
    """Redis does not roll a script back when a command in it fails.

    A HINCRBY that failed AFTER the INCRBY would leave the request counted, raise, and send the
    caller down the fallback path to count it a second time. Written first, a failure writes nothing.
    """
    script = budget_module._RESERVE_LUA

    assert script.index("return {used, 0}") < script.index("redis.call('HINCRBY', KEYS[3]")
    assert script.index("redis.call('HINCRBY', KEYS[3]") < script.index("redis.call('INCRBY', KEYS[1]")


def test_a_ledger_the_script_cannot_write_does_not_count_the_request_twice():
    """The ordering above, as behaviour: the script fails before writing, the fallback counts once."""

    class LedgerOfTheWrongType(LuaRedis):
        def eval(self, script, numkeys, *args):
            if numkeys > 2 and not isinstance(self.store.get(args[2]), dict):
                self.scripts.append(script)
                raise RuntimeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            return super().eval(script, numkeys, *args)

    client = LedgerOfTheWrongType()
    client.store[SCHEDULER_SENT_KEY] = "not a hash"
    budget = RequestBudget("livescore", 1200, client=client)

    with spending_for_task("live") as spend:
        budget.consume()  # must not raise: an unwritable ledger never blocks a request

    assert budget.used_today() == 1, "counted once by the fallback, not once by each path"
    assert spend.granted == {"livescore": 1}, "the pass still knows what it sent"


def test_a_request_refused_during_a_pass_is_in_neither_counter():
    client = LuaRedis()
    budget = RequestBudget("gameforecast", 1, client=client)

    with spending_for_task("forecasts") as spend:
        budget.consume()
        with pytest.raises(ProviderQuotaError):
            budget.consume()

    assert (budget.used_today(), budget.refused_today()) == (1, 1)
    assert client.store[SCHEDULER_SENT_KEY] == {"gameforecast:forecasts": 1}
    assert spend.granted == {"gameforecast": 1}


def test_the_snapshot_reads_the_counter_and_the_ledger_in_one_transaction():
    client = LuaRedis()
    budget = RequestBudget("livescore", 1200, client=client)
    with spending_for_task("live"):
        budget.consume()
    with spending_for_task("fixtures"):
        budget.consume(3)
    with spending_for_task("forecasts"):  # another provider's ledger entry is not this one's
        RequestBudget("gameforecast", 8, client=client).consume()
    budget.consume()  # not the scheduler's

    client.transactions.clear()
    snapshot = budget.snapshot()

    assert snapshot["used_today"] == 5
    assert snapshot["scheduler_sent"] == {"total": 4, "by_task": {"live": 1, "fixtures": 3}}
    assert client.transactions == [
        (True, [("get", budget_key("livescore")), ("hgetall", SCHEDULER_SENT_KEY)])], \
        "the counter and the ledger have to come from one instant of the store"
    assert snapshot["used_today"] - snapshot["scheduler_sent"]["total"] == 1


def test_a_window_that_cuts_through_a_pass_still_subtracts_exactly():
    """The 2026-09-25 shape. A total recorded when the pass ENDS is behind the counter for as long
    as the pass is in flight, so a reading taken then blames the scheduler's request on whoever was
    being measured. Written at the grant, the ledger is never behind."""
    client = LuaRedis()
    scheduler_side = RequestBudget("livescore", 1200, client=client)
    status_side = RequestBudget("livescore", 1200, client=client)  # what the status endpoint builds

    before = status_side.snapshot()
    with spending_for_task("live"):
        scheduler_side.consume()               # the live poll goes out...
        during = status_side.snapshot()        # ...and the test's closing read lands mid-pass
    after = status_side.snapshot()

    assert during["used_today"] - before["used_today"] == 1
    assert _spent_by_others(before, during) == 0
    assert _spent_by_others(during, after) == 0

    scheduler_side.consume()  # and a request nobody scheduled is the one thing left over
    assert _spent_by_others(before, status_side.snapshot()) == 1


def test_the_counting_fallback_keeps_the_ledger_too():
    client = BrokenEvalRedis()
    budget = RequestBudget("livescore", 1200, client=client)

    with spending_for_task("results") as spend:
        budget.consume(2)

    assert budget.used_today() == 2
    assert client.store[SCHEDULER_SENT_KEY] == {"livescore:results": 2}
    assert spend.granted == {"livescore": 2}
    assert budget.snapshot()["scheduler_sent"] == {"total": 2, "by_task": {"results": 2}}


def test_a_ledger_the_fallback_cannot_write_never_blocks_the_request():
    class NoLedger(BrokenEvalRedis):
        def hincrby(self, key, field, amount):
            if key == SCHEDULER_SENT_KEY:
                raise RuntimeError("WRONGTYPE")
            return super().hincrby(key, field, amount)

    budget = RequestBudget("livescore", 1200, client=NoLedger())

    with spending_for_task("live") as spend:
        budget.consume()

    assert budget.used_today() == 1 and spend.granted == {"livescore": 1}


def test_a_grant_the_store_never_saw_is_the_pass_s_but_the_ledger_is_unknown():
    """Fail open with no store: the pass sent it, and neither the counter nor the ledger saw it."""
    budget = RequestBudget("livescore", 1200, client=UnreachableRedis())

    with spending_for_task("live") as spend:
        budget.consume()

    assert spend.granted == {"livescore": 1}
    snapshot = budget.snapshot()
    assert snapshot["enforced"] is False and snapshot["unmetered_today"] == 1
    assert snapshot["scheduler_sent"] is None, "an unreadable ledger is unknown, never zero"


def test_a_request_granted_on_another_thread_during_a_pass_is_not_the_pass_s():
    """The scheduler runs in its own thread; a page load is served on another at the same moment."""
    client = LuaRedis()
    budget = RequestBudget("livescore", 1200, client=client)

    with spending_for_task("live") as spend:
        page = threading.Thread(target=budget.consume)
        page.start()
        page.join()

    assert budget.used_today() == 1
    assert SCHEDULER_SENT_KEY not in client.store
    assert spend.granted == {}
