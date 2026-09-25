"""Daily request budget: counting, refusal accounting, fail-closed behaviour and attribution."""

import pytest

from app.services.providers.base import ProviderQuotaError
from app.services.providers.budget import (
    FAIL_OPEN_MIN_DAILY_LIMIT, RequestBudget, budget_key, by_reason_key, refused_key,
)
from tests.providers.support import FakeRedis


def test_budget_counts_and_blocks():
    client = FakeRedis()
    budget = RequestBudget("livescore", 3, client=client)
    assert budget.remaining() == 3
    budget.consume(); budget.consume(2)
    assert budget.used_today() == 3 and budget.remaining() == 0
    with pytest.raises(ProviderQuotaError):
        budget.consume()
    snap = budget.snapshot()
    # A refused reservation never reached the provider, so it must not inflate the usage counter:
    # usage stays at the limit and the refusal is recorded separately.
    assert snap["enforced"] is True and snap["daily_limit"] == 3 and snap["used_today"] == 3
    assert snap["refused_today"] == 1 and budget.refused_today() == 1
    assert client.store[refused_key("livescore")] == 1
    assert client.ttls[budget_key("livescore")] == 2 * 24 * 3600


def test_refusals_do_not_consume_allowance_that_frees_up_later():
    """A refusal must not eat the allowance: dropping the counter back leaves room again."""
    client = FakeRedis()
    budget = RequestBudget("livescore", 2, client=client)
    budget.consume(2)
    with pytest.raises(ProviderQuotaError):
        budget.consume()
    with pytest.raises(ProviderQuotaError):
        budget.consume()
    assert budget.used_today() == 2 and budget.refused_today() == 2


def _without_any_store(budget):
    """Detach a budget from EVERY store it reads, not just its own counter.

    `RequestBudget(..., client=None)` does not mean "no store": it falls back to the real Redis,
    and `__init__` hands that same client to `self.rate_limit` before a test can intervene. Nulling
    `budget._client` alone therefore leaves the PROVIDER'S OWN rate-limit record still being read
    from the live store - so these tests passed or failed according to how much GameForecast
    allowance the machine happened to have left, and the refusal they assert on was pre-empted by a
    real reading of `remaining: 0` the day the allowance was spent.
    """
    budget._client = None
    budget.rate_limit._client = None
    return budget


def test_small_plan_fails_closed_without_the_counter_store():
    """A 10/day plan spent blind is a plan that is gone: refuse instead of spending unmetered."""
    budget = _without_any_store(RequestBudget("gameforecast", 8, client=None))
    assert budget.fail_open is False
    assert budget.can_afford() is False
    with pytest.raises(ProviderQuotaError) as exc:
        budget.consume()
    assert "budget store unavailable" in str(exc.value)
    assert budget.snapshot()["enforced"] is False


def test_api_football_free_plan_also_fails_closed():
    budget = _without_any_store(RequestBudget("api_football", 90, client=None))
    assert budget.fail_open is False
    with pytest.raises(ProviderQuotaError):
        budget.consume()


def test_large_plan_fails_open_without_the_counter_store():
    """Live Score API (1,200/day) keeps working through a Redis outage rather than going dark."""
    budget = _without_any_store(RequestBudget("livescore", 1200, client=None))
    assert budget.fail_open is True
    assert budget.can_afford() is True
    budget.consume(); budget.consume()
    assert budget.snapshot()["enforced"] is False
    assert budget.remaining() == 1200


def test_fail_open_threshold_and_explicit_override():
    assert RequestBudget("x", FAIL_OPEN_MIN_DAILY_LIMIT, client=FakeRedis()).fail_open is False
    assert RequestBudget("x", FAIL_OPEN_MIN_DAILY_LIMIT + 1, client=FakeRedis()).fail_open is True
    forced_open = _without_any_store(
        RequestBudget("gameforecast", 8, client=None, fail_open=True))
    forced_open.consume()  # explicit override wins over the size-derived default
    forced_closed = _without_any_store(
        RequestBudget("livescore", 1200, client=None, fail_open=False))
    with pytest.raises(ProviderQuotaError):
        forced_closed.consume()


def test_zero_limit_means_unlimited_but_counted():
    budget = RequestBudget("sample", 0, client=FakeRedis())
    for _ in range(5):
        budget.consume()
    assert budget.used_today() == 5 and budget.snapshot()["remaining_today"] is None


def test_spending_is_attributed_by_reason():
    client = FakeRedis()
    budget = RequestBudget("gameforecast", 8, client=client)
    budget.consume(reason="discovery")
    budget.consume(reason="fetch")
    budget.consume(2, reason="page")
    budget.consume(reason="unknown-thing")  # unrecognised reasons are bucketed, never dropped
    assert budget.by_reason() == {"discovery": 1, "fetch": 1, "page": 2, "other": 1}
    assert budget.snapshot()["by_reason"] == {"discovery": 1, "fetch": 1, "page": 2, "other": 1}
    assert client.ttls[by_reason_key("gameforecast")] == 2 * 24 * 3600


def test_refused_requests_are_not_attributed():
    budget = RequestBudget("gameforecast", 1, client=FakeRedis())
    budget.consume(reason="fetch")
    with pytest.raises(ProviderQuotaError):
        budget.consume(reason="page")
    assert budget.by_reason() == {"fetch": 1}


def test_attribution_failure_never_blocks_a_request():
    class NoHashes(FakeRedis):
        def hincrby(self, key, field, amount):
            raise RuntimeError("HINCRBY unsupported")

    budget = RequestBudget("gameforecast", 8, client=NoHashes())
    budget.consume(reason="fetch")  # must not raise
    assert budget.used_today() == 1


def test_store_failing_mid_flight_also_fails_closed_for_a_small_plan():
    class Broken(FakeRedis):
        def incrby(self, key, amount):
            raise RuntimeError("connection lost")

    small = RequestBudget("gameforecast", 8, client=Broken())
    with pytest.raises(ProviderQuotaError) as exc:
        small.consume()
    assert "budget store unavailable" in str(exc.value)

    large = RequestBudget("livescore", 1200, client=Broken())
    large.consume()  # a Redis blip must not take the whole site's match data down
