"""
A live or results pass is judged by what answered, not by who failed first.

THE DEFECT THIS PINS, verified on 2026-10-18. `SyncScheduler._run_live` and `_run_results` ended
with `ok = not out["errors"]`, and `MatchDataService._call_chain` records the primary's error
before falling through to a fallback. So a Live Score timeout answered by API-Football - the live
scores stored - still failed the live task and backed it off `BACKOFF_MIN_SECONDS`: a five-minute
live gap on a matchday, over an answer that had arrived. The results task had the same shape.

What holds now, for both tasks:

  * each call is classified from what it was SERVED (`match_data_service.CALL_*`): fresh, cache,
    stale, failed, deferred or not_asked - never from the chain's error list, nor from
    `request_failed` alone (it keeps an earlier provider's failure), nor from rows being written
    (a stale copy is stored again too);
  * a pass whose calls were all served fresh or from the valid cache is ok even when the primary
    failed first; the primary's error is kept in `diagnostics.provider_errors`, in the chain's
    own `errors` list and on the provider's status record - not in the verdict;
  * a call that ended failed, stale or deferred fails the pass, which backs off exactly as it
    always did; one answered competition never hides another's failure, and the report names
    which ended how;
  * an empty answer is an answer, and a question no provider in the chain can take is
    `not_asked`, a gap in coverage rather than a failure;
  * the counting is untouched: every request that went out is charged, reported and counted
    against the ceilings exactly as before, the one that went out and failed included.

No database and no network: the stub providers and fakes of `test_sync_scheduler`, and once the
real Live Score and API-Football classes over mock transports that raise on any request the test
did not expect.
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import settings
from app.services import sync_scheduler
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    CALL_CACHE, CALL_DEFERRED, CALL_FAILED, CALL_FRESH, CALL_NOT_ASKED, CALL_STALE, SyncMeta,
    call_outcome,
)
from app.services.providers.api_football_provider import APIFootballProvider
from app.services.providers.budget import RequestBudget, rate_limit_key
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.sync_scheduler import TASK_LIVE, TASK_RESULTS, SyncScheduler
from tests.providers.support import json_response, make_transport
from tests.services.test_sync_scheduler import (
    KEYS, NOW, Clock, FakeMatch, LockingFakeRedis, SpendingDataProvider, StubForecastService,
    build_match_service,
)

#: Twenty minutes in: inside the live window.
IN_PLAY = NOW - timedelta(minutes=20)
#: Four hours on: past the grace after which a result is due.
OVERDUE = NOW - timedelta(hours=4)
TODAY = NOW.date().isoformat()
FIRST, SECOND = (f"{key}@{TODAY}" for key in KEYS)


# --------------------------------------------------------------------- harness
@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def redis_client(clock):
    return LockingFakeRedis(clock=clock)


@pytest.fixture
def cache(redis_client):
    return MatchCache(client=redis_client)


@pytest.fixture(autouse=True)
def _today_only(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_FIXTURES_DAYS_AHEAD", 1)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 0)


def stub(name: str, redis, clock, *, fail: bool = False, limit: int = 100) -> SpendingDataProvider:
    """A stub that pays for every call out of its own budget before answering - or failing, which
    is what a request that went out and timed out costs."""
    provider = SpendingDataProvider(budget=RequestBudget(name, daily_limit=limit, client=redis, now=clock),
                                    fail=fail)
    provider.name = name
    return provider


class ClubOnlyStub(SpendingDataProvider):
    """A fallback that can name the first covered competition and no other, the way API-Football
    names the club competitions and no national-team one."""

    def askable(self, keys):
        return [key for key in keys if key == KEYS[0]]


def chain(cache, clock, providers, matches):
    """The shipped scheduler over a real MatchDataService (the live window, the results gating,
    the chain and its cool-downs are the shipped ones) with this chain of providers."""
    service = build_match_service(cache, providers[0], clock, matches)
    service._providers = list(providers)

    def match_factory(_db):
        service._now = clock()
        return service

    scheduler = SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                              match_service_factory=match_factory,
                              forecast_service_factory=lambda db: StubForecastService(),
                              tasks=[TASK_LIVE, TASK_RESULTS], close_sessions=False,
                              budget_client=cache._redis())
    return scheduler, service


def provider_status(service):
    return {entry["name"]: entry for entry in service.provider_status()["chain"]}


# ---------------------------------------------------- what a call is classified as
@pytest.mark.parametrize("meta, expected", [
    (SyncMeta(source="provider", provider="fallback", request_failed=True, errors=["primary: timed out"],
              failed_requests=["primary: timed out"]), CALL_FRESH),
    (SyncMeta(source="cache", provider="primary"), CALL_CACHE),
    (SyncMeta(source="stale-cache", provider="primary", stale=True, request_failed=True,
              errors=["primary: timed out"]), CALL_STALE),
    (SyncMeta(source="database", request_failed=True, errors=["primary: timed out", "live: primary: timed out"]),
     CALL_FAILED),
    (SyncMeta(source="database", not_sent=["our_allowance"], errors=["budget exhausted"]), CALL_DEFERRED),
    (SyncMeta(source="database", not_sent=["provider_allowance"]), CALL_DEFERRED),
    (SyncMeta(source="database", not_sent=["cooling_down", "not_served"]), CALL_DEFERRED),
    (SyncMeta(source="database", not_sent=["not_served", "not_configured"]), CALL_NOT_ASKED),
    (SyncMeta(source="database", errors=["No match-data provider is configured"]), CALL_NOT_ASKED),
], ids=["fallback_answered_after_a_failure", "cache", "stale_copy", "nobody_answered", "our_allowance",
        "provider_allowance", "cooling_down_outranks_not_served", "nobody_can_take_it", "empty_chain"])
def test_a_call_is_classified_from_what_answered_it(meta, expected):
    """The source decides first: a fallback's answer is `fresh` with the primary's failure still on
    the meta. Only a call that served nothing is told apart by whether a request left."""
    assert call_outcome(meta) == expected


# ------------------------------------------ the defect: a fallback's answer is an answer
def test_a_primary_failure_answered_by_the_fallback_is_a_success_that_keeps_the_primary_error(
        cache, clock, redis_client):
    """The 2026-10-18 pass: the primary's poll goes out and fails, the fallback's answers, the
    scores are stored. The pass is ok and keeps its cadence; the failure is preserved in three
    places and in the verdict in none; both requests are charged exactly as before."""
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = stub("stub-fallback", redis_client, clock)
    scheduler, service = chain(cache, clock, [primary, fallback], [FakeMatch(IN_PLAY)])

    report = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert primary.calls == ["live"] and fallback.calls == ["live"]
    assert report["ok"] is True
    result = report["result"]
    assert result["outcome"] == CALL_FRESH and result["live_polled"] is True
    assert result["provider"] == "stub-fallback" and result["source"] == "provider"
    assert result["by_outcome"] == {CALL_FRESH: ["live"]}
    live = result["call_outcomes"]["live"]
    assert live["outcome"] == CALL_FRESH and live["provider"] == "stub-fallback"
    assert "after a request that got no answer: upstream is down" in live["detail"]
    # -- the primary's failure is preserved: in the diagnostics, in the chain's own list, and on
    #    the primary's status record - and nowhere in the verdict.
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    assert result["diagnostics"]["request_failed"] is True
    assert result["request_failed"] is True, "the meta still says a request failed; the verdict no longer reads it"
    assert "upstream is down" in result["errors"]
    status = provider_status(service)
    assert status["stub"]["last_error"] == "upstream is down" and status["stub"]["cooling_down"]
    assert status["stub-fallback"]["last_error"] is None and status["stub-fallback"]["last_success_at"]
    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 0 and state["last_error"] is None
    assert state["backoff_seconds"] is None, "no five-minute gap on a matchday over an answer that arrived"
    assert state["next_due_at"] == (NOW + timedelta(seconds=scheduler.interval(TASK_LIVE))).isoformat()
    assert state["last_success_at"] == NOW.isoformat()
    # -- counting unchanged: the request that went out and failed is charged like the answered one,
    #    on the pass, on the scheduler's ledger, on each budget, and once against the live ceiling.
    assert result["requests"] == 2
    assert state["last_requests_sent"] == {"stub": 1, "stub-fallback": 1}
    assert scheduler.status()["tasks"][TASK_LIVE]["requests_sent_total"] == {"stub": 1, "stub-fallback": 1}
    assert primary.budget.used_today() == 1 and fallback.budget.used_today() == 1
    assert primary.budget.granted == 1 and fallback.budget.granted == 1
    assert scheduler._live_polls_today() == 1, "one poll, however many providers it took"


def test_a_results_request_that_went_out_and_failed_is_charged_and_reported_as_before(
        cache, clock, redis_client):
    """The same for results: the primary's request fails for both competitions, the fallback answers
    for both. Ok, fresh, the failure under `diagnostics`, and every request charged as it was."""
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = stub("stub-fallback", redis_client, clock)
    scheduler, service = chain(cache, clock, [primary, fallback], [FakeMatch(OVERDUE)])

    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    assert primary.calls == [f"results:{TODAY}"] and fallback.calls == [f"results:{TODAY}"]
    assert report["ok"] is True
    result = report["result"]
    assert result["outcome"] == CALL_FRESH and result["polled"] is True
    assert result["by_outcome"] == {CALL_FRESH: [FIRST, SECOND]}
    for name in (FIRST, SECOND):
        assert result["call_outcomes"][name]["provider"] == "stub-fallback"
        assert "after a request that got no answer: upstream is down" in result["call_outcomes"][name]["detail"]
    day = result["days"][TODAY]
    assert day["call_outcomes"][KEYS[0]] == result["call_outcomes"][FIRST]
    assert day["source"] == "provider" and day["provider"] == "stub-fallback" and day["request_failed"] is True
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    assert "upstream is down" in result["errors"]
    assert provider_status(service)["stub"]["last_error"] == "upstream is down"
    state = scheduler.state(TASK_RESULTS)
    assert state["consecutive_failures"] == 0 and state["backoff_seconds"] is None
    # -- counting unchanged
    assert result["requests"] == 2, "the cap's count of competitions asked about, as before"
    assert day["requests"] == 2, "the failed request and the answered one, both charged"
    assert state["last_requests_sent"] == {"stub": 1, "stub-fallback": 1}
    assert primary.budget.used_today() == 1 and fallback.budget.used_today() == 1


def test_a_live_score_timeout_answered_by_api_football_with_the_real_provider_classes(
        cache, clock, redis_client, monkeypatch):
    """The defect's own scenario through the real classes: Live Score's live poll times out on
    the wire, API-Football's poll answers. Both transports raise on any request the scenario does
    not contain, so nothing else can pass for an answer."""
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)

    def livescore_times_out(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches/live.json"):
            raise httpx.ReadTimeout("timed out", request=request)
        raise AssertionError(f"unexpected request to Live Score: {request.url.path}")

    def api_football_answers_the_poll(request: httpx.Request) -> httpx.Response:
        if "live" in request.url.params:
            return json_response({"response": [], "errors": []})
        raise AssertionError(f"unexpected request to API-Football: {request.url}")

    livescore_transport, livescore_requests = make_transport(livescore_times_out)
    api_football_transport, api_football_requests = make_transport(api_football_answers_the_poll)
    livescore = LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=livescore_transport,
        budget=RequestBudget("livescore", 1200, client=redis_client, now=clock), store=cache,
        competition_overrides={})
    api_football = APIFootballProvider(
        api_key="test-api-football-key", transport=api_football_transport,
        budget=RequestBudget("api_football", 90, client=redis_client, now=clock))
    scheduler, service = chain(cache, clock, [livescore, api_football], [FakeMatch(IN_PLAY)])

    report = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert len(livescore_requests.requests) == 1 and len(api_football_requests.requests) == 1
    assert report["ok"] is True
    result = report["result"]
    assert result["outcome"] == CALL_FRESH and result["provider"] == "api_football"
    assert result["live_polled"] is True
    assert result["diagnostics"]["provider_errors"] == ["livescore: network error: timed out"]
    status = provider_status(service)
    assert status["livescore"]["last_error"] == "livescore: network error: timed out"
    assert status["livescore"]["last_error_kind"] == "unavailable"
    assert status["api_football"]["last_error"] is None and status["api_football"]["last_success_at"]
    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 0 and state["backoff_seconds"] is None
    assert state["last_requests_sent"] == {"livescore": 1, "api_football": 1}
    assert livescore.budget.used_today() == 1, "the provider charged the request that timed out"
    assert api_football.budget.used_today() == 1
    assert scheduler._live_polls_today() == 1


# ------------------------------------------------------------ what still fails a pass
def test_a_pass_nobody_answers_still_fails_and_backs_off(cache, clock, redis_client):
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = stub("stub-fallback", redis_client, clock, fail=True)
    scheduler, _ = chain(cache, clock, [primary, fallback], [FakeMatch(IN_PLAY)])

    report = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == CALL_FAILED and result["live_polled"] is False
    assert result["by_outcome"] == {CALL_FAILED: ["live"]}
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    assert result["errors"].count("upstream is down") == 2, "both went out, both failed"
    assert report["error"].startswith("live: failed (upstream is down")
    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 1
    assert state["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS
    assert state["last_requests_sent"] == {"stub": 1, "stub-fallback": 1}, "both charged all the same"
    assert scheduler._live_polls_today() == 1, "a poll that went out and failed is still a poll"


def test_one_competition_answered_does_not_hide_another_whose_request_failed(cache, clock, redis_client):
    """The primary's request fails for both competitions; the fallback can name only the first and
    answers for it. The first is fresh, the second's request went out and nobody answered it: the
    pass fails, names the second and not the first, and backs off."""
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = ClubOnlyStub(budget=RequestBudget("stub-fallback", daily_limit=100, client=redis_client, now=clock))
    fallback.name = "stub-fallback"
    scheduler, _ = chain(cache, clock, [primary, fallback], [FakeMatch(OVERDUE)])

    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    assert primary.calls == [f"results:{TODAY}"] and fallback.calls == [f"results:{TODAY}"]
    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == sync_scheduler.PASS_PARTIAL
    assert result["by_outcome"] == {CALL_FRESH: [FIRST], CALL_FAILED: [SECOND]}
    assert result["call_outcomes"][FIRST]["provider"] == "stub-fallback"
    assert result["call_outcomes"][SECOND] == {"outcome": CALL_FAILED, "provider": None,
                                               "detail": "results: upstream is down"}
    assert result["days"][TODAY]["call_outcomes"][KEYS[1]]["outcome"] == CALL_FAILED
    assert SECOND in report["error"] and FIRST not in report["error"]
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    state = scheduler.state(TASK_RESULTS)
    assert state["consecutive_failures"] == 1
    assert state["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS
    assert state["last_requests_sent"] == {"stub": 1, "stub-fallback": 1}


def test_a_poll_served_only_from_the_stale_copy_is_not_a_success(cache, clock, redis_client):
    provider = stub("stub", redis_client, clock)
    scheduler, _ = chain(cache, clock, [provider], [FakeMatch(IN_PLAY)])
    assert scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]["result"]["outcome"] == CALL_FRESH

    provider.fail = True
    clock.tick(scheduler.interval(TASK_LIVE))  # past the 60 s live cache; the stale copy remains
    report = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert provider.calls == ["live", "live"], "the provider was asked again, and failed"
    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == CALL_STALE and result["source"] == "stale-cache" and result["stale"] is True
    assert result["live_polled"] is True, "the stale copy was served and stored, as before"
    assert result["by_outcome"] == {CALL_STALE: ["live"]}
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    assert "stale copy stub fetched at" in report["error"] and "upstream is down" in report["error"]
    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 1
    assert state["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS
    assert state["last_requests_sent"] == {"stub": 1}


def test_a_results_call_served_only_from_the_stale_copy_is_not_a_success(cache, clock, redis_client):
    provider = stub("stub", redis_client, clock)
    scheduler, _ = chain(cache, clock, [provider], [FakeMatch(OVERDUE)])
    assert scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]["result"]["outcome"] == CALL_FRESH

    provider.fail = True
    clock.tick(settings.MATCH_CACHE_TTL_RESULTS + 1)  # past the results cache; the stale copy remains
    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    assert provider.calls == [f"results:{TODAY}"] * 2
    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == CALL_STALE
    assert result["by_outcome"] == {CALL_STALE: [FIRST, SECOND]}
    assert result["days"][TODAY]["source"] == "stale-cache"
    assert result["call_outcomes"][FIRST]["provider"] == "stub"
    assert "stale copy stub fetched at" in result["call_outcomes"][FIRST]["detail"]
    assert result["diagnostics"]["provider_errors"] == ["upstream is down"]
    assert scheduler.state(TASK_RESULTS)["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS


def test_a_request_refused_before_it_left_is_deferred_not_a_provider_failure(cache, clock, redis_client):
    """The provider's own window says nothing is left, so the budget refuses the poll before it goes
    out while our counter still has room (so the task is not skipped first). Nothing was sent, so
    nothing failed: `deferred`, no provider error, nothing charged. The verdict is the one such a
    pass always had - not ok, backing off, which `_record` clamps to the next budget reset."""
    provider = stub("stub", redis_client, clock)
    redis_client.store[rate_limit_key("stub")] = json.dumps({
        "limit": 100, "remaining": 0, "reset_at": (NOW + timedelta(hours=2)).isoformat(),
        "observed_at": NOW.isoformat()})
    scheduler, service = chain(cache, clock, [provider], [FakeMatch(IN_PLAY)])

    report = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert report["ran"] is True, "our own counter has room, so the ceiling let the task run"
    assert provider.calls == [], "nothing was sent"
    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == CALL_DEFERRED and result["live_polled"] is False
    assert result["diagnostics"] == {"provider_errors": [], "not_sent": ["provider_allowance"],
                                     "declined": [], "request_failed": False}
    assert result["requests"] == 0
    assert "itself reports 0 request(s) left" in report["error"]
    assert "refused by the daily ceiling" not in report["error"], "whose limit it was is said"
    state = scheduler.state(TASK_LIVE)
    assert state["last_requests_sent"] == {}
    assert provider.budget.used_today() == 0 and provider.budget.refused_today() == 1
    assert state["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS
    assert scheduler._live_polls_today() == 0, "a poll that never left is not charged to the ceiling"
    assert provider_status(service)["stub"]["last_error_kind"] == "quota"


def test_a_results_call_held_back_by_a_cool_down_is_deferred(cache, clock, redis_client):
    """Every provider that could take the question is cooling down after an earlier failure, and
    nothing was served in its place: `deferred`, no request, no provider error, and the pass
    fails as it always did (the cool-down is minutes long; the backoff clamps to the reset)."""
    provider = stub("stub", redis_client, clock)
    scheduler, service = chain(cache, clock, [provider], [FakeMatch(OVERDUE)])
    service._set_cooldown("stub", "upstream is down", 120)

    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    assert provider.calls == []
    assert report["ok"] is False
    result = report["result"]
    assert result["outcome"] == CALL_DEFERRED
    assert result["by_outcome"] == {CALL_DEFERRED: [FIRST, SECOND]}
    assert result["diagnostics"]["provider_errors"] == [] and result["diagnostics"]["request_failed"] is False
    assert result["diagnostics"]["not_sent"] == ["cooling_down"]
    assert "skipped (recent failure: upstream is down)" in result["call_outcomes"][FIRST]["detail"]
    assert scheduler.state(TASK_RESULTS)["last_requests_sent"] == {}


# ------------------------------------------------------------ what does not fail a pass
def test_an_empty_answer_is_an_answer(cache, clock, redis_client):
    provider = stub("stub", redis_client, clock)  # answers every call with an empty list
    scheduler, _ = chain(cache, clock, [provider], [FakeMatch(IN_PLAY), FakeMatch(OVERDUE)])

    report = scheduler.run_once(only=[TASK_LIVE, TASK_RESULTS])

    assert provider.calls == ["live", f"results:{TODAY}"]
    live, results = report["tasks"][TASK_LIVE], report["tasks"][TASK_RESULTS]
    assert live["ok"] is True and live["result"]["outcome"] == CALL_FRESH
    assert live["result"]["fixtures_seen"] == 0 and live["result"]["live_polled"] is True
    assert results["ok"] is True and results["result"]["outcome"] == CALL_FRESH
    assert results["result"]["by_outcome"] == {CALL_FRESH: [FIRST, SECOND]}
    assert results["result"]["days"][TODAY]["fixtures_seen"] == 0
    assert results["result"]["diagnostics"]["provider_errors"] == []
    for task in (live, results):
        assert task["result"]["errors"] == [] and task.get("error") is None


def test_a_pass_served_from_the_valid_cache_is_a_success_that_asked_nobody(cache, clock, redis_client):
    provider = stub("stub", redis_client, clock)
    scheduler, _ = chain(cache, clock, [provider], [FakeMatch(OVERDUE)])
    scheduler.run_once(only=[TASK_RESULTS])

    report = scheduler.run_once(only=[TASK_RESULTS], force=True)["tasks"][TASK_RESULTS]

    assert provider.calls == [f"results:{TODAY}"], "the second pass was served from the cache"
    assert report["ok"] is True
    assert report["result"]["outcome"] == CALL_CACHE
    assert report["result"]["by_outcome"] == {CALL_CACHE: [FIRST, SECOND]}
    assert report["result"]["call_outcomes"][FIRST] == {"outcome": CALL_CACHE, "provider": "stub", "detail": None}
    assert scheduler.state(TASK_RESULTS)["last_requests_sent"] == {}


def test_a_competition_no_provider_can_take_is_not_asked_and_does_not_fail_the_pass(cache, clock, redis_client):
    """The only provider names the first competition and answers for it; nobody in the chain can
    name the second. A gap in coverage the next pass cannot change is not an outage: the pass
    is ok, and says which competition went unasked and why."""
    only = ClubOnlyStub(budget=RequestBudget("stub", daily_limit=100, client=redis_client, now=clock))
    scheduler, _ = chain(cache, clock, [only], [FakeMatch(OVERDUE)])

    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    assert only.calls == [f"results:{TODAY}"]
    assert report["ok"] is True and report.get("error") is None
    result = report["result"]
    assert result["outcome"] == sync_scheduler.PASS_PARTIAL
    assert result["by_outcome"] == {CALL_FRESH: [FIRST], CALL_NOT_ASKED: [SECOND]}
    unasked = result["call_outcomes"][SECOND]
    assert unasked["outcome"] == CALL_NOT_ASKED and unasked["provider"] is None
    assert f"not asked about {KEYS[1]}" in unasked["detail"]
    # A provider that answered for part of a call is not "passed over", so `not_sent` stays empty;
    # the competition it left out is in `declined`, as the chain has always recorded it.
    assert result["diagnostics"]["not_sent"] == []
    assert result["diagnostics"]["declined"] == [unasked["detail"]]
    assert result["errors"] == [], "a gap in coverage is not an error, as before"
    assert scheduler.state(TASK_RESULTS)["consecutive_failures"] == 0


# ----------------------------------------------------------------- the caps still bind
def test_the_live_ceiling_counts_a_poll_the_fallback_answered_and_still_binds(cache, clock, redis_client,
                                                                               monkeypatch):
    monkeypatch.setattr(settings, "SYNC_LIVE_MAX_REQUESTS_PER_DAY", 2)
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = stub("stub-fallback", redis_client, clock)
    scheduler, _ = chain(cache, clock, [primary, fallback], [FakeMatch(IN_PLAY)])

    for _ in range(2):
        entry = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]
        assert entry["ok"] is True and entry["result"]["outcome"] == CALL_FRESH
        clock.tick(scheduler.interval(TASK_LIVE))  # past the live cache and the primary's cool-down
    third = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert primary.calls == ["live", "live"] and fallback.calls == ["live", "live"]
    assert scheduler._live_polls_today() == 2, "one poll per pass, however many providers it took"
    assert third["ok"] is True and third["result"]["live_polled"] is False
    assert third["result"]["outcome"] == sync_scheduler.PASS_SKIPPED
    assert "ceiling" in third["result"]["note"]
    assert scheduler.status()["tasks"][TASK_LIVE]["requests_sent_total"] == {"stub": 2, "stub-fallback": 2}


def test_the_results_cap_still_binds_when_the_primary_fails_and_the_fallback_answers(cache, clock, redis_client,
                                                                                      monkeypatch):
    monkeypatch.setattr(settings, "SYNC_RESULTS_MAX_REQUESTS_PER_PASS", 1)
    primary = stub("stub", redis_client, clock, fail=True)
    fallback = stub("stub-fallback", redis_client, clock)
    scheduler, _ = chain(cache, clock, [primary, fallback], [FakeMatch(OVERDUE)])

    report = scheduler.run_once(only=[TASK_RESULTS])["tasks"][TASK_RESULTS]

    result = report["result"]
    assert report["ok"] is True and result["outcome"] == CALL_FRESH
    assert result["requests"] == 1, "the cap counts the competitions asked about, as before"
    assert result["deferred"] == [SECOND], "the cap deferred the second competition to the next pass"
    assert result["by_outcome"] == {CALL_FRESH: [FIRST]}
    assert primary.calls == [f"results:{TODAY}"] and fallback.calls == [f"results:{TODAY}"]
    assert scheduler.state(TASK_RESULTS)["last_requests_sent"] == {"stub": 1, "stub-fallback": 1}


def test_a_closed_window_and_a_reached_ceiling_are_passes_with_no_call_to_judge(cache, clock, redis_client,
                                                                                 monkeypatch):
    provider = stub("stub", redis_client, clock)
    scheduler, _ = chain(cache, clock, [provider], [FakeMatch(NOW + timedelta(days=1))])

    closed = scheduler.run_once(only=[TASK_LIVE])["tasks"][TASK_LIVE]

    assert closed["ok"] is True and closed["result"]["live_window_open"] is False
    assert closed["result"]["outcome"] == sync_scheduler.PASS_SKIPPED
    assert closed["result"]["call_outcomes"] == {} and closed["result"]["by_outcome"] == {}
    assert provider.calls == []
