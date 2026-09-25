"""
What a GameForecastAPI turn costs before it is started, and what it reports about what it dropped.

Two things the provider has to say out loud, both of them about the ten-requests-a-day free plan:

- what one competition's turn will cost. A competition whose league id is not recorded yet needs a
  /leagues lookup BEFORE the /events fetch, so its turn cannot be paid for with one request left.
  The caller can only refuse to start such a turn if the provider quotes the price first.
- which events it returned and threw away. An event the provider returned with no usable
  prediction in it used to be dropped silently, which made it indistinguishable afterwards from an
  event the provider never returned at all - and left fixtures with no explainable cause.

No network: httpx.MockTransport throughout, and an in-memory Redis stand-in for the store and the
budget. Nothing here makes a provider request or touches a real allowance.
"""

from datetime import date, datetime, timezone

import httpx
import pytest

from app.services.match_cache import MatchCache
from app.services.providers import gameforecast as gf
from app.services.providers.base import ProviderQuotaError
from app.services.providers.budget import RequestBudget
from app.services.providers.gameforecast import GameForecastProvider
from tests.providers.support import FakeRedis, json_response, make_transport

FROM, TO = date(2026, 9, 18), date(2026, 9, 25)


def event(event_id=501, home="Liverpool", away="Everton", predictions=None):
    """One /events item. `predictions=None` means the usual full snapshot."""
    if predictions is None:
        predictions = [{"run_at": "2026-09-18T06:00:00Z",
                        "match_result": {"home": 58, "draw": 24, "away": 18}}]
    return {"id": event_id, "league": {"id": 15, "name": "Premier League"},
            "team_home": {"id": 31, "name": home}, "team_away": {"id": 32, "name": away},
            "start_at": "2026-09-20T14:00:00Z", "updated_at": "2026-09-18T06:00:00Z",
            "predictions": predictions}


def _route(pages):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/leagues":
            return json_response({"data": [{"id": 22, "name": "UEFA Champions League",
                                            "type": "cup", "women": False}]})
        page = int(dict(request.url.params).get("page", "1"))
        return json_response(pages[page - 1])
    return handler


def provider(handler, store=None, budget=None, limit=8):
    transport, recorder = make_transport(handler)
    return GameForecastProvider(
        api_key="rapid-key", api_host="game-forecast-api.p.rapidapi.com",
        base_url="https://game-forecast-api.p.rapidapi.com", transport=transport,
        budget=budget or RequestBudget("gameforecast", limit, client=FakeRedis()),
        league_overrides={}, store=store or MatchCache(client=FakeRedis())), recorder


# ------------------------------------------------- what a turn costs, quoted before it is started
def test_a_competition_whose_league_id_is_recorded_costs_one_request():
    p, recorder = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    assert p.request_cost("premier_league") == 1        # gameforecast_id is in COMPETITIONS
    assert recorder.requests == [], "pricing a turn must not cost a request"


def test_a_competition_that_still_needs_discovery_costs_two_requests():
    """The defect this closes: a turn priced at 1 when it really costs a /leagues then an /events."""
    p, recorder = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    assert p.league_id_is_known("champions_league") is False
    assert p.request_cost("champions_league") == 2
    assert recorder.requests == []


def test_a_discovered_league_id_drops_the_price_back_to_one():
    store = MatchCache(client=FakeRedis())
    p, _ = provider(_route([{"data": [], "pagination": {"hasMore": False}}]), store=store)
    assert p.request_cost("champions_league") == 2
    p.resolve_league("champions_league")                # pays the discovery once, stores the id
    assert p.request_cost("champions_league") == 1

    fresh, _ = provider(_route([{"data": [], "pagination": {"hasMore": False}}]), store=store)
    assert fresh.request_cost("champions_league") == 1, "the stored id must price the next run too"


def test_a_competition_marked_unresolvable_costs_nothing():
    """Its fetch is short-circuited before any HTTP call, so its turn is free, not one request."""
    p, recorder = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    p._mark_unresolved("champions_league")
    assert p.request_cost("champions_league") == 0
    assert p.get_forecasts("champions_league", FROM, TO) == []
    assert recorder.requests == []


# --------------------------------------------------- what the provider returned and threw away
def test_events_with_nothing_usable_are_reported_not_silently_dropped():
    """Both silences have to be tellable apart later: "never returned" vs "returned and empty"."""
    pages = [{"data": [
        event(501),
        event(502, home="Arsenal", away="Chelsea", predictions=[]),
        event(503, home="Fulham", away="Brentford",
              predictions=[{"run_at": "2026-09-18T06:00:00Z", "reasoning": {"en": "no numbers"}}]),
    ], "pagination": {"hasMore": False}}]
    p, _ = provider(_route(pages))

    forecasts = p.get_forecasts("premier_league", FROM, TO)

    assert [f.external_event_id for f in forecasts] == ["501"]
    report = p.last_fetch
    assert report["events_returned"] == 3 and report["forecasts_returned"] == 1
    assert report["discarded"] == 2 and report["discarded_truncated"] is False
    by_id = {e["external_event_id"]: e for e in report["discarded_events"]}
    assert set(by_id) == {"502", "503"}
    assert by_id["502"]["reason"] == gf.DISCARD_NO_PREDICTIONS
    assert by_id["503"]["reason"] == gf.DISCARD_NO_MARKET
    # Named well enough to be tied back to a fixture, and nothing more: no payload is retained.
    assert (by_id["502"]["home"], by_id["502"]["away"]) == ("Arsenal", "Chelsea")
    assert by_id["502"]["kickoff_utc"] == "2026-09-20T14:00:00+00:00"
    assert set(by_id["502"]) == {"external_event_id", "home", "away", "kickoff_utc", "reason"}


def test_the_report_records_the_window_and_that_the_listing_was_complete():
    """Without the window, "none of the events is this fixture" would be claimed outside it."""
    pages = [{"data": [event(501)], "pagination": {"hasMore": False}}]
    p, _ = provider(_route(pages))

    p.get_forecasts("premier_league", FROM, TO)

    report = p.last_fetch
    assert (report["window_from"], report["window_to"]) == ("2026-09-18", "2026-09-25")
    assert report["complete"] is True and report["pages_read"] == 1
    assert report["key"] == "premier_league" and report["league_id"] == "15"
    assert datetime.fromisoformat(report["fetched_at"]).tzinfo is not None


def test_a_listing_cut_off_at_the_page_cap_does_not_claim_to_be_complete():
    """Four pages and the provider still says there is more: this listing proves nothing absent."""
    page = {"data": [event(600)], "pagination": {"hasMore": True}}
    p, recorder = provider(_route([page] * gf.MAX_PAGES), limit=50)

    p.get_forecasts("premier_league", FROM, TO)

    assert len(recorder.requests) == gf.MAX_PAGES
    assert p.last_fetch["complete"] is False
    assert p.last_fetch["pages_read"] == gf.MAX_PAGES


def test_the_discarded_list_is_capped_and_says_when_it_is_truncated():
    """The record must stay bounded: a page that all parses to nothing cannot inflate it."""
    too_many = gf.MAX_DISCARDED_REPORTED + 5
    pages = [{"data": [event(700 + n, predictions=[]) for n in range(too_many)],
              "pagination": {"hasMore": False}}]
    p, _ = provider(_route(pages))

    assert p.get_forecasts("premier_league", FROM, TO) == []

    report = p.last_fetch
    assert report["discarded"] == too_many                       # the count stays exact
    assert len(report["discarded_events"]) == gf.MAX_DISCARDED_REPORTED
    assert report["discarded_truncated"] is True


def test_a_fetch_that_never_happened_leaves_no_report():
    """A short-circuited turn must not leave a report a reader would take for a real response."""
    p, _ = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    p._mark_unresolved("champions_league")
    p.get_forecasts("champions_league", FROM, TO)
    assert p.last_fetch is None


def test_a_new_fetch_replaces_the_previous_report():
    pages = [{"data": [event(501)], "pagination": {"hasMore": False}}]
    p, _ = provider(_route(pages))
    p.get_forecasts("premier_league", FROM, TO)
    assert p.last_fetch["events_returned"] == 1

    empty, _ = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    empty.get_forecasts("premier_league", FROM, TO)
    assert empty.last_fetch["events_returned"] == 0


@pytest.mark.parametrize("key", ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1"])
def test_every_domestic_competition_is_priced_without_a_request(key):
    """Pricing reads recorded ids only; it must never be the thing that spends the allowance."""
    p, recorder = provider(_route([{"data": [], "pagination": {"hasMore": False}}]))
    assert p.request_cost(key) == 1
    assert recorder.requests == []
    assert p.budget.used_today() == 0


# ------------------------------------------------- the provider's own accounting, read and obeyed
#
# GameForecastAPI is served through RapidAPI, which reports the plan's ceiling, what is left and
# when the window resets on every response. Until 2026-09-19 nothing here read them, and the cost
# was measured that night: the provider refused the third request of a fresh UTC day while our own
# counter still showed five of eight left, because its window is not the UTC calendar day.

RATE_LIMIT_HEADERS = {"x-ratelimit-requests-limit": "10",
                      "x-ratelimit-requests-remaining": "1",
                      "x-ratelimit-requests-reset": "25972"}


def _with_headers(payload, status=200, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload,
                              headers=RATE_LIMIT_HEADERS if headers is None else headers)
    return handler


def test_a_fetch_records_what_the_provider_said_about_its_own_window():
    """Into the budget's own store, so the counter and the provider's window are read together."""
    redis = FakeRedis()
    budget = RequestBudget("gameforecast", 8, client=redis)
    p, _ = provider(_with_headers({"data": [], "pagination": {"hasMore": False}}), budget=budget)

    p.get_forecasts("premier_league", FROM, TO)

    assert budget.used_today() == 1
    assert budget.provider_remaining() == 1, "the provider's own count, not ours"
    assert budget.remaining_effective() == 1, "and it is the binding one: ours still shows 7"
    assert budget.snapshot()["limited_by"] == "the_provider"


def test_a_turn_is_refused_when_the_provider_says_its_window_is_empty():
    """Our counter is untouched and no request goes out: the provider already said no."""
    redis = FakeRedis()
    budget = RequestBudget("gameforecast", 8, client=redis)
    handler = _with_headers({"data": [], "pagination": {"hasMore": False}},
                            headers=dict(RATE_LIMIT_HEADERS, **{"x-ratelimit-requests-remaining": "0"}))
    p, recorder = provider(handler, budget=budget)

    p.get_forecasts("premier_league", FROM, TO)          # spends one, and learns the window is now empty
    assert len(recorder.requests) == 1

    with pytest.raises(ProviderQuotaError) as refused:
        p.get_forecasts("premier_league", FROM, TO)

    assert len(recorder.requests) == 1, "the second turn must never reach the network"
    assert "gameforecast itself reports 0 request(s) left in its own window" in str(refused.value)
    assert budget.used_today() == 1


def test_a_429_still_teaches_us_the_window_even_though_it_fails():
    redis = FakeRedis()
    # A fixed clock, because the last assertion is about the clock. The reset header is 25,972 s
    # (7h13m) ahead of whenever the response is observed, so on the wall clock that lands within
    # the tolerance of UTC midnight for twenty minutes every afternoon (about 16:37-16:57 UTC) and
    # this test went red there. Observed at noon, the window ends at 19:13 UTC, nowhere near it.
    budget = RequestBudget("gameforecast", 8, client=redis,
                           now=datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc))
    handler = _with_headers({"message": "You have exceeded the DAILY quota for Requests on your "
                                        "current plan, BASIC."}, status=429,
                            headers=dict(RATE_LIMIT_HEADERS, **{"x-ratelimit-requests-remaining": "0"}))
    p, _ = provider(handler, budget=budget)

    with pytest.raises(ProviderQuotaError):
        p.get_forecasts("premier_league", FROM, TO)

    assert budget.provider_remaining() == 0
    assert budget.rate_limit.seconds_until_reset() is not None
    assert budget.snapshot()["provider_reported"]["window_matches_utc_day"] is False


def test_a_provider_that_sends_no_such_header_behaves_exactly_as_before():
    """The headers are optional. Their absence must change nothing about a normal fetch."""
    redis = FakeRedis()
    budget = RequestBudget("gameforecast", 8, client=redis)
    p, recorder = provider(_with_headers({"data": [event()], "pagination": {"hasMore": False}},
                                         headers={}), budget=budget)

    forecasts = p.get_forecasts("premier_league", FROM, TO)

    assert len(forecasts) == 1 and len(recorder.requests) == 1
    assert budget.used_today() == 1
    assert budget.provider_remaining() is None, "silence is unknown, never zero"
    assert budget.remaining_effective() == 7, "so our own counter is what governs"
