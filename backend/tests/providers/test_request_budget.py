from app.services.providers.base import ProviderQuotaError
from app.services.providers.budget import RequestBudget, budget_key
from tests.providers.support import FakeRedis
import pytest


def test_budget_counts_and_blocks():
    client = FakeRedis()
    budget = RequestBudget("livescore", 3, client=client)
    assert budget.remaining() == 3
    budget.consume(); budget.consume(2)
    assert budget.used_today() == 3 and budget.remaining() == 0
    with pytest.raises(ProviderQuotaError):
        budget.consume()
    snap = budget.snapshot()
    assert snap["enforced"] is True and snap["daily_limit"] == 3 and snap["used_today"] == 4
    assert client.ttls[budget_key("livescore")] == 2 * 24 * 3600


def test_budget_disabled_without_redis():
    budget = RequestBudget("gameforecast", 1, client=None)
    budget._client = None  # force "no redis" regardless of the environment
    budget.consume(); budget.consume()
    assert budget.snapshot()["enforced"] is False
    assert budget.remaining() == 1


def test_zero_limit_means_unlimited_but_counted():
    budget = RequestBudget("sample", 0, client=FakeRedis())
    for _ in range(5):
        budget.consume()
    assert budget.used_today() == 5 and budget.snapshot()["remaining_today"] is None
