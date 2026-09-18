"""
Competition fairness: who gets the next request when the allowance is smaller than the coverage.

The GameForecastAPI trial plan is 8 requests a day for six competitions, so a pass cannot cover
everything and the order decides who gets forecasts at all. On 2026-09-18 one pass at 03:13Z spent
the allowance on four competitions and the last two - Ligue 1 and the Champions League - never got
a turn; Ligue 1 ended the day with eight upcoming fixtures and zero forecasts. These tests pin the
rotation that is supposed to stop that from being permanent, and the true cost of a pass.

Real ForecastService, real GameForecastProvider, real RequestBudget, real Redis-backed rotation
state - only the HTTP transport, the clock and the database are doubles. Every request the
provider "sends" is an httpx MockTransport call that a real deployment would have paid for, so the
request counts asserted below are the real cost of a pass, discovery included.

The /events responses carry no events: what is under test is who is asked and what it costs, not
the parsing, which `tests/providers/test_gameforecast_provider.py` already covers.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.forecast_service import COOLDOWN_KEY, LAST_SYNC_KEY, ForecastService
from app.services.match_cache import MatchCache
from app.services.providers.budget import RequestBudget, budget_key
from app.services.providers.gameforecast import LEAGUE_STORE_KEY, GameForecastProvider
from app.services.sync_scheduler import TASK_FORECASTS, SyncScheduler
from tests.providers.support import json_response, make_transport
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

PROVIDER = "gameforecast"
#: The six covered competitions, in the configured order (COVERED_COMPETITIONS).
KEYS = ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league"]
#: Five carry a confirmed GameForecast id; the Champions League has to be discovered by name.
NEEDS_DISCOVERY = "champions_league"

#: The pass that spent the allowance, and the reset the deferred competitions are waiting for.
SPENT_AT = datetime(2026, 9, 18, 3, 13, 11, tzinfo=timezone.utc)
RESET = datetime(2026, 9, 19, 0, 1, tzinfo=timezone.utc)
#: An hour before that reset, with the day's allowance already gone.
YESTERDAY = datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc)
#: Last sync per competition as stored in Redis after that pass (the four that got a turn).
SYNCED_ON_18TH = {
    "premier_league": SPENT_AT,
    "la_liga": SPENT_AT + timedelta(seconds=2),
    "serie_a": SPENT_AT + timedelta(seconds=5),
    "bundesliga": SPENT_AT + timedelta(seconds=8),
}


def _handler(request: httpx.Request) -> httpx.Response:
    """The provider's two endpoints. /leagues is the discovery lookup, /events the forecast fetch."""
    if request.url.path == "/leagues":
        return json_response({"data": [{"id": 22, "name": "UEFA Champions League",
                                        "type": "cup", "women": False}]})
    assert request.url.path == "/events", f"unexpected provider call: {request.url.path}"
    return json_response({"data": [], "pagination": {"hasMore": False}})


def build(clock: Clock, cache: MatchCache, budget: RequestBudget,
          keys: Optional[List[str]] = None, handler=None):
    """One pass's worth of service, the way the scheduler builds a fresh one each time."""
    transport, recorder = make_transport(handler or _handler)
    provider = GameForecastProvider(api_key="rapid-key", api_host="gf.test",
                                    base_url="https://gf.test", transport=transport,
                                    budget=budget, league_overrides={}, store=cache)
    service = ForecastService(MagicMock(), provider=provider, cache=cache, now=clock(),
                              keys=list(keys if keys is not None else KEYS), sync_fixtures=False)
    # The registry is the database boundary; forecasts are not attached here, only fetched.
    service.registry = MagicMock()
    return service, recorder


def seed_last_sync(cache: MatchCache, synced: dict) -> None:
    for key, when in synced.items():
        cache.set(LAST_SYNC_KEY.format(provider=PROVIDER, key=key), when.isoformat(),
                  ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)


def paths(recorder) -> List[str]:
    return [r.url.path for r in recorder.requests]


@pytest.fixture
def clock():
    return Clock(start=RESET)


@pytest.fixture
def cache(clock):
    return MatchCache(client=LockingFakeRedis(clock=clock))


@pytest.fixture
def budget(clock, cache):
    # Same store as production uses for counters; the clock seam lets the budget day roll.
    return RequestBudget(PROVIDER, 8, client=cache._redis(), now=clock)


# ------------------------------------------------------------------ the order
def test_never_synced_competitions_go_first_and_the_oldest_synced_follows(clock, cache, budget):
    """The rotation is the whole reason a competition at the tail of the list is ever reached."""
    seed_last_sync(cache, SYNCED_ON_18TH)
    service, _ = build(clock, cache, budget)

    assert service.sync_order() == ["ligue_1", "champions_league",       # never synced
                                    "premier_league", "la_liga", "serie_a", "bundesliga"]


def test_the_first_pass_after_the_reset_fetches_the_two_that_never_got_a_turn(clock, cache, budget):
    """The case on the table: Ligue 1 and the Champions League, first, on the new allowance."""
    seed_last_sync(cache, SYNCED_ON_18TH)
    service, recorder = build(clock, cache, budget)

    report = service.ensure_synced()

    assert list(report["competitions"]) == ["ligue_1", "champions_league"]
    assert set(report["skipped"]) == set(SYNCED_ON_18TH), "a competition synced 21 h ago waits its turn"
    # Ligue 1 has a confirmed provider id, so it costs one /events call and no lookup.
    assert paths(recorder) == ["/events", "/leagues", "/events"]
    assert budget.used_today() == 3 and budget.remaining() == 5
    assert report.get("error") is None


def test_the_four_synced_yesterday_cannot_crowd_out_the_two_that_were_starved(clock, cache, budget):
    """Two brakes, and both must hold: the rotation ranks them last AND the 24 h interval skips them."""
    seed_last_sync(cache, SYNCED_ON_18TH)
    service, recorder = build(clock, cache, budget)

    service.ensure_synced()

    assert len(paths(recorder)) == 3, "no request may go to a competition synced inside its interval"
    for key in SYNCED_ON_18TH:
        assert service._last_sync(key) == SYNCED_ON_18TH[key], "an untouched competition is untouched"
    assert service._last_sync("ligue_1") == clock(), "the starved ones are now on record as synced"


def test_two_daily_passes_with_a_small_allowance_cover_different_competitions(clock, cache):
    """An allowance of 2 against six competitions: the tail is reached on the next pass, not starved."""
    small = RequestBudget(PROVIDER, 2, client=cache._redis(), now=clock)
    first, first_recorder = build(clock, cache, small)

    day_one = first.ensure_synced()

    assert list(day_one["competitions"]) == ["premier_league", "la_liga"]
    assert day_one["deferred"] == ["serie_a", "bundesliga", "ligue_1", "champions_league"]
    assert len(paths(first_recorder)) == 2, "the pass stops before reserving a third request"

    clock.tick(24 * 3600 + 120)  # the next day: new counter key, and the pause has expired
    second, second_recorder = build(clock, cache, small)

    day_two = second.ensure_synced()

    assert list(day_two["competitions"]) == ["serie_a", "bundesliga"]
    assert set(day_one["competitions"]).isdisjoint(day_two["competitions"])
    assert len(paths(second_recorder)) == 2
    assert small.used_today() == 2, "the new day starts from its own counter"


def test_a_deferred_competition_keeps_its_place_at_the_head_of_the_next_order(clock, cache):
    """Deferred is not dropped: the competitions that did not get a turn are first next time."""
    small = RequestBudget(PROVIDER, 2, client=cache._redis(), now=clock)
    service, _ = build(clock, cache, small)

    deferred = service.ensure_synced()["deferred"]

    clock.tick(24 * 3600 + 120)
    later, _ = build(clock, cache, small)
    assert later.sync_order()[:len(deferred)] == deferred


# ------------------------------------------------------------------ what a pass costs
def test_a_full_pass_over_all_six_competitions_fits_inside_the_daily_limit(clock, cache, budget):
    """Five confirmed ids plus one discovery: 7 requests against a limit of 8. It did not always fit."""
    service, recorder = build(clock, cache, budget)

    report = service.ensure_synced()

    assert list(report["competitions"]) == KEYS
    assert len(paths(recorder)) == 7 == budget.used_today()
    assert paths(recorder).count("/leagues") == 1, "only the Champions League needs discovering"
    assert budget.remaining() == 1


def estimate_for(clock, cache, service) -> dict:
    """The scheduler's dry run over this exact ForecastService. Makes no provider request."""
    scheduler = SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                              forecast_service_factory=lambda _db: service,
                              tasks=[TASK_FORECASTS], close_sessions=False)
    return scheduler.estimate(only=[TASK_FORECASTS])["tasks"][TASK_FORECASTS]


def test_the_dry_run_estimate_bounds_what_the_pass_then_actually_spends(clock, cache, budget):
    """The estimate is what the owner reads before letting a pass go, so it has to bound it.

    Five competitions carry a confirmed provider id and cost one /events call each; the Champions
    League has none, so it pays a /leagues lookup first and costs two. An estimate of one request
    per competition says 6 for a pass that spends 7 - it drops exactly the request that decides
    whether the pass fits inside an 8-a-day plan.
    """
    service, recorder = build(clock, cache, budget)

    entry = estimate_for(clock, cache, service)

    assert recorder.requests == [], "an estimate makes no provider request"
    assert budget.used_today() == 0, "and spends nothing"

    service.ensure_synced()

    assert len(paths(recorder)) == 7 == budget.used_today(), "what the pass really costs"
    assert entry["estimated_requests"] == 7, "and what the estimate promised"


def test_the_estimate_drops_the_lookup_once_the_league_id_has_been_discovered(clock, cache, budget):
    """Paid once, estimated once: the second day costs six, and the estimate says six."""
    first, _ = build(clock, cache, budget)
    first.ensure_synced()
    assert cache.get(LEAGUE_STORE_KEY)[NEEDS_DISCOVERY]["external_id"] == "22"

    clock.tick(24 * 3600 + 120)
    second, recorder = build(clock, cache, budget)  # a fresh provider: no in-memory ids

    entry = estimate_for(clock, cache, second)
    second.ensure_synced()

    assert paths(recorder) == ["/events"] * 6
    assert entry["estimated_requests"] == 6 == budget.used_today()


def test_a_competition_the_provider_cannot_resolve_is_estimated_at_the_nothing_it_spends(clock, cache, budget):
    """A remembered discovery failure short-circuits before any request, and the estimate knows it.

    The marker is the only thing that stops an unresolvable competition paying a lookup on every
    pass, so an estimate that still billed it two requests would overstate the cost of a plan
    that has eight.
    """
    service, recorder = build(clock, cache, budget, keys=[NEEDS_DISCOVERY])
    service.provider._mark_unresolved(NEEDS_DISCOVERY)

    entry = estimate_for(clock, cache, service)
    service.ensure_synced()

    assert recorder.requests == [], "the remembered failure spends nothing"
    assert entry["estimated_requests"] == 0 == budget.used_today()
    assert "1 costing nothing" in entry["basis"]


def test_discovery_spending_is_attributed_rather_than_hidden_and_is_paid_once(clock, cache, budget):
    """Discovery ate 5 of the 8 requests on 2026-09-18. It must be visible, and it must not recur."""
    first, _ = build(clock, cache, budget)
    first.ensure_synced()

    assert budget.by_reason() == {"fetch": 6, "discovery": 1}
    assert sum(budget.by_reason().values()) == budget.used_today(), "spending reconciles by reason"
    assert cache.get(LEAGUE_STORE_KEY)[NEEDS_DISCOVERY]["external_id"] == "22"

    clock.tick(24 * 3600 + 120)
    second, second_recorder = build(clock, cache, budget)  # a fresh provider: no in-memory ids

    second.ensure_synced()

    assert paths(second_recorder) == ["/events"] * 6, "the stored id is reused, not rediscovered"
    assert budget.by_reason() == {"fetch": 6} and budget.used_today() == 6


def test_a_turn_that_cannot_be_paid_for_in_full_is_not_started_at_all(clock, cache):
    """The allowance buys forecasts or it buys nothing: never a league id and then a refusal.

    This is the shape that left Ligue 1 with no forecasts. A competition whose provider id is not
    known yet costs two requests - a /leagues discovery, then /events - and the gate used to ask
    only whether ONE request was left. With one left it started the turn, spent it on the lookup,
    and was refused the fetch. The day's last unit bought an id and not a single forecast.

    The gate now prices the whole turn before starting it. With one request left and a turn that
    costs two, nothing goes out, the competition is deferred by name, and the unit is still there
    for the next pass. It stops rather than skipping ahead to a cheaper competition behind it:
    reordering by price would put the expensive one permanently last, and permanently last on a
    small daily allowance means never fetched at all.
    """
    last_one = RequestBudget(PROVIDER, 1, client=cache._redis(), now=clock)
    service, recorder = build(clock, cache, last_one, keys=[NEEDS_DISCOVERY])

    report = service.ensure_synced()

    assert paths(recorder) == [], "not even the lookup went out"
    assert last_one.used_today() == 0, "the last unit is still there for the next pass"
    assert last_one.refused_today() == 0, "stopping early is how the refused counter stays meaningful"
    assert report["deferred"] == [NEEDS_DISCOVERY]
    assert NEEDS_DISCOVERY in report["error"] and "cannot cover" in report["error"]
    assert "2 request(s)" in report["error"], "the report says what the turn would have cost"
    assert service._last_sync(NEEDS_DISCOVERY) is None, "a competition never fetched is not 'synced'"
    assert cache.get(LEAGUE_STORE_KEY) in (None, {}), "no id was bought with a unit that bought no forecast"


def test_a_turn_that_fits_exactly_is_started(clock, cache):
    """The mirror of the gate: two units and a two-unit turn is affordable, so it runs.

    Without this the gate could pass its own test by refusing everything.
    """
    exactly_enough = RequestBudget(PROVIDER, 2, client=cache._redis(), now=clock)
    service, recorder = build(clock, cache, exactly_enough, keys=[NEEDS_DISCOVERY])

    report = service.ensure_synced()

    assert paths(recorder) == ["/leagues", "/events"], "discovery, then the fetch it paid for"
    assert exactly_enough.used_today() == 2
    assert report["deferred"] == []
    assert cache.get(LEAGUE_STORE_KEY)[NEEDS_DISCOVERY]["external_id"] == "22", "the lookup is kept"


def test_the_allowance_stops_a_pass_before_it_reserves_a_request_it_cannot_afford(clock, cache):
    """A spent allowance must not be discovered by being refused: refusals are noise, not spending."""
    spent = RequestBudget(PROVIDER, 3, client=cache._redis(), now=clock)
    for _ in range(3):
        spent.consume()
    service, recorder = build(clock, cache, spent)

    report = service.ensure_synced()

    assert recorder.requests == []
    assert spent.refused_today() == 0, "stopping early is how the refused counter stays meaningful"
    assert report["deferred"] == KEYS


# ------------------------------------------------------------------ across the reset
def test_a_quota_pause_written_today_does_not_outlive_the_reset(clock, cache):
    """The pause is bounded by the reset it is waiting for, or the new day's first pass is blocked."""
    clock.now = YESTERDAY
    spent = RequestBudget(PROVIDER, 3, client=cache._redis(), now=clock)
    for _ in range(3):
        spent.consume()
    blocked, blocked_recorder = build(clock, cache, spent)

    blocked.ensure_synced()

    assert blocked_recorder.requests == []
    assert cache.get(COOLDOWN_KEY.format(provider=PROVIDER)) is not None, "the pass paused the provider"

    clock.now = RESET  # 00:01 the next day, one scheduler tick after the allowance returns

    assert cache.get(COOLDOWN_KEY.format(provider=PROVIDER)) is None, "the pause expired with the day"
    assert spent.remaining() == 3, "and the new day reads its own, empty, counter"

    resumed, resumed_recorder = build(clock, cache, spent)
    report = resumed.ensure_synced()

    assert report.get("paused") is not True, "yesterday's pause must not block the first pass"
    assert paths(resumed_recorder) == ["/events"] * 3, "the new allowance is spent on forecasts"
    assert spent.used_today() == 3
    assert cache._redis().store[budget_key(PROVIDER, YESTERDAY)] == 3, "yesterday stays on record"


def test_a_discovery_that_fails_is_remembered_so_it_cannot_eat_the_allowance_every_pass(clock, cache, budget):
    """A competition the provider does not list costs one lookup, not one on every pass.

    An unremembered failure is the worst case for a small plan: it pays a request per pass,
    forever, and produces nothing. The negative marker (6 h) and the per-competition interval are
    what bound it - and the competition is still marked synced, which is deliberate: it drops to
    the back of the rotation instead of taking the head of every order with a lookup that fails.
    """
    def lists_nothing(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/leagues":
            return json_response({"data": [{"id": 99, "name": "UEFA Youth League",
                                            "type": "cup", "women": False}]})
        return json_response({"data": [], "pagination": {"hasMore": False}})

    service, recorder = build(clock, cache, budget, keys=[NEEDS_DISCOVERY], handler=lists_nothing)
    first = service.ensure_synced()

    assert paths(recorder) == ["/leagues"] and budget.used_today() == 1
    assert first["competitions"][NEEDS_DISCOVERY]["fetched"] == 0, "nothing was fetched to attach"

    clock.tick(3600)
    again, again_recorder = build(clock, cache, budget, keys=[NEEDS_DISCOVERY], handler=lists_nothing)
    again.ensure_synced(force=True)  # force past the interval: only the marker can stop this

    assert again_recorder.requests == [], "the remembered failure spends nothing"
    assert budget.used_today() == 1
