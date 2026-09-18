"""GameForecastAPI provider — mocked HTTP, real response shape from the published OpenAPI spec."""

from datetime import date, datetime, timezone

import httpx
import pytest

from app.services.providers.base import (
    ProviderAuthError, ProviderNotConfiguredError, ProviderQuotaError, ProviderUnavailableError,
)
from app.services.providers.base import to_probability as base_to_probability
from app.services.providers.budget import RequestBudget
from app.services.providers import gameforecast as gf
from app.services.providers.gameforecast import GameForecastProvider, parse_event, to_probability
from app.services.match_cache import MatchCache
from tests.providers.support import FakeRedis, json_response, make_transport


def event(**overrides):
    base = {
        "id": 501, "league": {"id": 15, "name": "Premier League"}, "status_code": "NS", "round": "5",
        "team_home": {"id": 31, "name": "Liverpool"}, "team_away": {"id": 32, "name": "Everton"},
        "start_at": "2026-09-20T14:00:00Z", "score": None, "odds": [], "updated_at": "2026-09-18T06:00:00Z",
        "predictions": [
            {"run_at": "2026-09-17T06:00:00Z",
             "match_result": {"home": 50, "draw": 30, "away": 20},
             "total_goals": {"over_2_5": 60, "under_2_5": 40},
             "both_teams_score": {"yes": 55, "no": 45},
             "exact_score": {"1-0": 12, "2-1": 11},
             "recommended_bets": {"match_result": "home"},
             "reasoning": {"en": "Older run."}},
            {"run_at": "2026-09-18T06:00:00Z",
             "match_result": {"home": 58, "draw": 24, "away": 18},
             "total_goals": {"over_2_5": 62, "under_2_5": 38, "over_3_5": 35, "under_3_5": 65},
             "both_teams_score": {"yes": 51, "no": 49},
             "exact_score": {"2-0": 14, "2-1": 12},
             "recommended_bets": {"match_result": "home", "total_goals": "over_2_5"},
             "reasoning": {"en": "Liverpool are strong at home.", "fr": "Liverpool est fort à domicile."}},
        ],
    }
    base.update(overrides)
    return base


def test_parse_event_uses_latest_snapshot_and_converts_percentages():
    f = parse_event(event(), competition_key="premier_league")
    assert f.provider == "gameforecast" and f.external_event_id == "501"
    assert f.kickoff_utc == datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (0.58, 0.24, 0.18)
    assert (f.btts_yes_prob, f.btts_no_prob) == (0.51, 0.49)
    assert (f.over_25_prob, f.under_25_prob, f.over_35_prob, f.under_35_prob) == (0.62, 0.38, 0.35, 0.65)
    assert f.exact_score == {"2-0": 0.14, "2-1": 0.12}
    assert f.recommended_bets == {"match_result": "home", "total_goals": "over_2_5"}
    assert f.reasoning == "Liverpool are strong at home."
    assert f.confidence is None  # never derived
    assert f.model_run_at == datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    assert f.competition_key == "premier_league" and f.home_external_id == "31"


def test_parse_event_real_percent_payload_with_small_exact_scores():
    """Shape observed live on 2026-09-17 (Bayern v Union Berlin)."""
    e = event(predictions=[{
        "run_at": "2026-09-17T00:00:00Z",
        "match_result": {"home": 85, "draw": 10, "away": 5},
        "total_goals": {"over_0_5": 99, "over_1_5": 95, "over_2_5": 85, "over_3_5": 65, "under_0_5": 1, "under_1_5": 5, "under_2_5": 15, "under_3_5": 35},
        "both_teams_score": {"yes": 30, "no": 70},
        "exact_score": {"0_0": 1, "1_0": 3, "2_0": 12, "3_0": 14, "3_1": 9, "other": 38},
        "recommended_bets": {"1": "matchResult.homeWinProbability", "2": "totalGoals.over2_5", "3": "bothTeamsScore.no"},
        "reasoning": "Bayern are in excellent form.",
    }])
    f = parse_event(e)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (0.85, 0.1, 0.05)
    assert (f.btts_yes_prob, f.btts_no_prob) == (0.3, 0.7)
    assert (f.over_25_prob, f.under_25_prob, f.over_35_prob, f.under_35_prob) == (0.85, 0.15, 0.65, 0.35)
    assert f.exact_score == {"0-0": 0.01, "1-0": 0.03, "2-0": 0.12, "3-0": 0.14, "3-1": 0.09}  # 1 means 1%, "other" dropped
    assert max(f.exact_score, key=f.exact_score.get) == "3-0"
    assert f.reasoning == "Bayern are in excellent form."


def test_small_payload_values_are_percentages_not_unit_fractions():
    """REPLACES test_parse_event_accepts_unit_scale_probabilities, which pinned the old behaviour.

    The scale used to be inferred from the magnitude of the value ("<= 1.0 means it is already a
    probability"), so a genuine 1% arrived as 100% certainty. The scale is now the provider's
    documented contract, applied unconditionally: 1 means 1%.
    """
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z", "match_result": {"home": 1, "draw": 0.5, "away": 100}}])
    f = parse_event(e)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (0.01, 0.005, 1.0)


@pytest.mark.parametrize("raw,expected", [
    (1, 0.01),          # 1 means 1%, never 100%
    (0.5, 0.005),       # half a percent
    (100, 1.0),         # the top of the published scale
    (75, 0.75), ("75", 0.75), ("75%", 0.75), (0, 0.0),
    (None, None), ("", None), ("abc", None), ("n/a", None),
    (float("nan"), None), (float("inf"), None), (float("-inf"), None),
    (-3, None), (101, None), (150, None), (True, None), (False, None),
])
def test_to_probability_applies_the_documented_percentage_scale(raw, expected):
    assert to_probability(raw) == expected
    # gameforecast.to_probability is base.to_probability with the scale bound: one implementation.
    assert to_probability(raw) == base_to_probability(raw, gf.PROBABILITY_SCALE)


def test_base_to_probability_never_infers_the_scale():
    assert base_to_probability(1) == 0.01                  # default scale is percentages
    assert base_to_probability(1, scale=1.0) == 1.0        # a unit-scale provider says so explicitly
    assert base_to_probability(0.65, scale=1.0) == 0.65
    assert base_to_probability(65, scale=1.0) is None      # out of range on that scale, not rescaled


def test_all_zero_market_is_unavailable_not_zero_percent():
    """A market published as all zeros was not forecast; 0% would present a non-forecast as one."""
    e = event(predictions=[{
        "run_at": "2026-09-18T06:00:00Z",
        "match_result": {"home": 0, "draw": 0, "away": 0},
        "both_teams_score": {"yes": 0, "no": 0},
        "total_goals": {"over_2_5": 0, "under_2_5": 0, "over_3_5": 40, "under_3_5": 60},
        "exact_score": {"1_0": 0, "2_1": 0},
    }])
    f = parse_event(e)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (None, None, None)
    assert (f.btts_yes_prob, f.btts_no_prob) == (None, None)
    assert (f.over_25_prob, f.under_25_prob) == (None, None)
    assert (f.over_35_prob, f.under_35_prob) == (0.4, 0.6)  # a real market is untouched
    assert f.exact_score is None and f.exact_score_other_prob is None
    markets = f.markets()
    assert markets["match_result"] is False and markets["btts"] is False
    assert markets["over_under_25"] is False and markets["exact_score"] is False
    assert markets["over_under_35"] is True
    assert "match result values were all zero; treated as unavailable" in f.anomalies
    assert any("both teams to score values were all zero" in a for a in f.anomalies)
    # the zeroed market is reported once, not also as a sum-out-of-tolerance anomaly
    assert not any("sum to" in a for a in f.anomalies)


def test_zero_probability_scorelines_can_never_be_the_most_likely_score():
    e = event(predictions=[{
        "run_at": "2026-09-18T06:00:00Z",
        "exact_score": {"0_0": 0, "1_0": 0, "2_1": 7, "3_0": 0},
    }])
    f = parse_event(e)
    assert f.exact_score == {"2-1": 0.07}
    assert max(f.exact_score, key=f.exact_score.get) == "2-1"
    assert any("0% and were dropped" in a for a in f.anomalies)


def test_partial_market_is_reported_as_incomplete_not_as_a_bad_sum():
    """A2/A3: two of three 1X2 outcomes legitimately add up to less than 100%."""
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z",
                            "match_result": {"home": 58, "draw": 24},
                            "both_teams_score": {"yes": 51}}])
    f = parse_event(e)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (0.58, 0.24, None)
    assert "match result incomplete: away probability not supplied" in f.anomalies
    assert "both teams to score incomplete: no probability not supplied" in f.anomalies
    assert not any("sum to" in a for a in f.anomalies)


def test_complete_market_out_of_tolerance_is_still_reported():
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z",
                            "match_result": {"home": 58, "draw": 24, "away": 40}}])
    f = parse_event(e)
    assert any("match result probabilities sum to 122.0%" in a for a in f.anomalies)


def test_market_absent_entirely_produces_no_anomaly():
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z", "match_result": {"home": 50, "draw": 30, "away": 20}}])
    f = parse_event(e)
    assert f.anomalies == []


def test_parse_event_missing_markets_stay_none():
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z", "match_result": {"home": 45, "draw": 30, "away": 25}}])
    f = parse_event(e)
    assert f.has_any_market()
    assert f.btts_yes_prob is None and f.btts_no_prob is None
    assert f.over_25_prob is None and f.over_35_prob is None and f.under_35_prob is None
    assert f.exact_score is None and f.recommended_bets is None and f.reasoning is None


def test_parse_event_without_predictions_or_without_markets():
    assert parse_event(event(predictions=[])) is None
    f = parse_event(event(predictions=[{"run_at": "2026-09-18T06:00:00Z", "reasoning": {"en": "no numbers"}}]))
    assert f is not None and f.has_any_market() is False


def _events_route(pages):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-RapidAPI-Key"] == "rapid-key"
        assert request.headers["X-RapidAPI-Host"] == "game-forecast-api.p.rapidapi.com"
        params = dict(request.url.params)
        if request.url.path == "/leagues":
            # Discovery is only exercised for a competition with no id recorded in code. Every league
            # in COMPETITIONS now carries a verified GameForecast id except the Champions League.
            return json_response({"data": [
                {"id": 20, "name": "UEFA Champions League", "type": "cup", "women": True},
                {"id": 21, "name": "UEFA Youth League", "type": "cup", "women": False},
                {"id": 22, "name": "UEFA Champions League", "type": "cup", "women": False},
            ]})
        assert request.url.path == "/events"
        assert params["start_at_start"] == "2026-09-18" and params["start_at_end"] == "2026-09-25"
        assert params["page_size"] == "50"
        page = int(params.get("page", "1"))
        return json_response(pages[page - 1])
    return handler


def provider(handler, key="rapid-key", budget=None, overrides=None, store=None):
    transport, recorder = make_transport(handler)
    p = GameForecastProvider(api_key=key, api_host="game-forecast-api.p.rapidapi.com",
                             base_url="https://game-forecast-api.p.rapidapi.com", transport=transport,
                             budget=budget or RequestBudget("gameforecast", 8, client=FakeRedis()),
                             league_overrides=overrides if overrides is not None else {},
                             store=store or MatchCache(client=FakeRedis()))
    return p, recorder


def test_resolved_league_ids_persist_across_provider_instances():
    store = MatchCache(client=FakeRedis())
    pages = [{"data": [], "pagination": {"hasMore": False}}]
    first, recorder1 = provider(_events_route(pages), store=store)
    assert first.resolve_league("champions_league").external_id == "22"
    assert [r.url.path for r in recorder1.requests] == ["/leagues"]
    second, recorder2 = provider(_events_route(pages), store=store)
    assert second.resolve_league("champions_league").external_id == "22"
    assert recorder2.requests == []  # no second /leagues lookup: the free plan is spent on /events only


def test_get_forecasts_paginates_and_skips_events_without_markets():
    pages = [
        {"data": [event(), event(id=502, predictions=[])], "pagination": {"page": 1, "hasMore": True}},
        {"data": [event(id=503, team_home={"id": 33, "name": "Arsenal"}, team_away={"id": 34, "name": "Chelsea"})],
         "pagination": {"page": 2, "hasMore": False}},
    ]
    p, recorder = provider(_events_route(pages))
    forecasts = p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))
    assert [f.external_event_id for f in forecasts] == ["501", "503"]
    assert all(dict(r.url.params)["league_id"] == "15" for r in recorder.requests)  # recorded id, no /leagues call
    assert [r.url.path for r in recorder.requests] == ["/events", "/events"]


def test_league_resolution_by_name_ignores_women_and_second_tier():
    """The women's competition and the youth competition must not be mistaken for the men's one."""
    pages = [{"data": [], "pagination": {"hasMore": False}}]
    p, recorder = provider(_events_route(pages))
    league = p.resolve_league("champions_league")
    assert league.external_id == "22"
    # no country_code: the Champions League is European, not national
    assert dict(recorder.requests[0].url.params) == {"name": "champions league", "page_size": "50"}
    p.get_forecasts("champions_league", date(2026, 9, 18), date(2026, 9, 25))
    assert dict(recorder.requests[-1].url.params)["league_id"] == "22"
    assert len(recorder.requests) == 2  # league lookup cached


def test_not_configured():
    p, recorder = provider(_events_route([]), key="")
    assert p.is_configured() is False
    with pytest.raises(ProviderNotConfiguredError):
        p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))
    assert recorder.requests == []


@pytest.mark.parametrize("status_code,exc", [(401, ProviderAuthError), (403, ProviderAuthError),
                                              (429, ProviderQuotaError), (502, ProviderUnavailableError)])
def test_http_errors(status_code, exc):
    p, _ = provider(lambda r: httpx.Response(status_code, json={"message": "denied"}))
    with pytest.raises(exc):
        p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))


def test_unexpected_payload_is_unavailable():
    p, _ = provider(lambda r: json_response({"unexpected": True}))
    with pytest.raises(ProviderUnavailableError):
        p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))


def test_free_plan_budget_is_enforced_locally():
    budget = RequestBudget("gameforecast", 1, client=FakeRedis())
    pages = [{"data": [event()], "pagination": {"hasMore": False}}]
    p, recorder = provider(_events_route(pages), budget=budget)
    assert len(p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))) == 1
    with pytest.raises(ProviderQuotaError):
        p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))
    assert len(recorder.requests) == 1
    assert budget.snapshot()["remaining_today"] == 0


def test_not_subscribed_message_is_surfaced():
    p, _ = provider(lambda r: httpx.Response(403, json={"message": "You are not subscribed to this API."}))
    with pytest.raises(ProviderAuthError) as exc:
        p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))
    assert "not subscribed" in str(exc.value)


# ---------------------------------------------------------------- retrieval time (A4)

def test_fetched_at_is_stamped_when_the_response_is_parsed():
    """Retrieval time belongs to the HTTP response, not to the later attach/persist step."""
    pages = [
        {"data": [event()], "pagination": {"page": 1, "hasMore": True}},
        {"data": [event(id=503)], "pagination": {"page": 2, "hasMore": False}},
    ]
    before = datetime.now(timezone.utc)
    p, _ = provider(_events_route(pages))
    forecasts = p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))
    after = datetime.now(timezone.utc)
    assert len(forecasts) == 2
    for f in forecasts:
        assert f.fetched_at is not None and f.fetched_at.tzinfo is not None
        assert before <= f.fetched_at <= after
        # the provider's own model-run timestamp is untouched and is NOT the retrieval time
        assert f.model_run_at == datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
        assert f.fetched_at != f.model_run_at


def test_every_forecast_from_one_response_shares_one_retrieval_timestamp():
    pages = [{"data": [event(), event(id=504), event(id=505)], "pagination": {"hasMore": False}}]
    p, _ = provider(_events_route(pages))
    stamps = {f.fetched_at for f in p.get_forecasts("premier_league", date(2026, 9, 18), date(2026, 9, 25))}
    assert len(stamps) == 1


# ------------------------------------------------- unresolvable league discovery (A5)

def _no_league_found(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/leagues":
        return json_response({"data": []})
    return json_response({"data": [], "pagination": {"hasMore": False}})


def test_failed_league_discovery_is_cached_and_not_retried():
    """Each discovery attempt costs 10% of the free plan: an unresolvable key must not re-pay."""
    store = MatchCache(client=FakeRedis())
    first, recorder1 = provider(_no_league_found, store=store)
    assert first.resolve_league("champions_league") is None
    assert [r.url.path for r in recorder1.requests] == ["/leagues"]

    # same instance: no second lookup
    assert first.resolve_league("champions_league") is None
    assert len(recorder1.requests) == 1

    # a fresh instance sharing the store (one is built per request) makes no request at all
    second, recorder2 = provider(_no_league_found, store=store)
    assert second.resolve_league("champions_league") is None
    assert recorder2.requests == []
    assert second.get_forecasts("champions_league", date(2026, 9, 18), date(2026, 9, 25)) == []
    assert recorder2.requests == []


def test_unresolved_marker_expires_so_a_new_competition_is_eventually_found():
    client = FakeRedis()
    store = MatchCache(client=client)
    first, _ = provider(_no_league_found, store=store)
    assert first.resolve_league("champions_league") is None
    marker = GameForecastProvider.unresolved_key("champions_league")
    assert client.ttls[marker] == gf.UNRESOLVED_TTL  # 6h, not forever

    client.delete(marker, f"{marker}:stale")  # as if the marker had expired
    third, recorder3 = provider(_events_route([{"data": [], "pagination": {"hasMore": False}}]), store=store)
    assert third.resolve_league("champions_league").external_id == "22"
    assert [r.url.path for r in recorder3.requests] == ["/leagues"]


def test_a_resolvable_league_is_never_marked_unresolved():
    client = FakeRedis()
    store = MatchCache(client=client)
    p, _ = provider(_events_route([{"data": [], "pagination": {"hasMore": False}}]), store=store)
    assert p.resolve_league("champions_league").external_id == "22"
    assert client.get(GameForecastProvider.unresolved_key("champions_league")) is None


def test_discovery_and_fetch_requests_are_attributed_separately():
    budget = RequestBudget("gameforecast", 8, client=FakeRedis())
    pages = [
        {"data": [event()], "pagination": {"page": 1, "hasMore": True}},
        {"data": [event(id=503)], "pagination": {"page": 2, "hasMore": False}},
    ]
    p, _ = provider(_events_route(pages), budget=budget)
    p.get_forecasts("champions_league", date(2026, 9, 18), date(2026, 9, 25))
    assert budget.by_reason() == {"discovery": 1, "fetch": 1, "page": 1}


def test_a_transient_discovery_failure_is_not_cached_as_unresolvable():
    """Only a search that completed and found nothing is a real 'unresolvable'; a 429 is not."""
    client = FakeRedis()
    store = MatchCache(client=client)
    p, _ = provider(lambda r: httpx.Response(429, json={"message": "rate limited"}), store=store)
    with pytest.raises(ProviderQuotaError):
        p.resolve_league("champions_league")
    assert client.get(GameForecastProvider.unresolved_key("champions_league")) is None

    healthy, recorder = provider(_events_route([{"data": [], "pagination": {"hasMore": False}}]), store=store)
    assert healthy.resolve_league("champions_league").external_id == "22"
    assert [r.url.path for r in recorder.requests] == ["/leagues"]
