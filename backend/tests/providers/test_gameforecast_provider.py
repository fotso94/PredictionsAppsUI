"""GameForecastAPI provider — mocked HTTP, real response shape from the published OpenAPI spec."""

from datetime import date, datetime, timezone

import httpx
import pytest

from app.services.providers.base import (
    ProviderAuthError, ProviderNotConfiguredError, ProviderQuotaError, ProviderUnavailableError, to_probability,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.gameforecast import GameForecastProvider, parse_event
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


def test_parse_event_accepts_unit_scale_probabilities():
    e = event(predictions=[{"run_at": "2026-09-18T06:00:00Z", "match_result": {"home": 0.5, "draw": 0.3, "away": 0.2}}])
    f = parse_event(e)
    assert (f.home_prob, f.draw_prob, f.away_prob) == (0.5, 0.3, 0.2)


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


@pytest.mark.parametrize("raw,expected", [(75, 0.75), ("75", 0.75), (0.75, 0.75), (1, 1.0), (100, 1.0), (0, 0.0),
                                          (None, None), ("n/a", None), (-5, None), (150, None)])
def test_to_probability(raw, expected):
    assert to_probability(raw) == expected


def _events_route(pages):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-RapidAPI-Key"] == "rapid-key"
        assert request.headers["X-RapidAPI-Host"] == "game-forecast-api.p.rapidapi.com"
        params = dict(request.url.params)
        if request.url.path == "/leagues":
            return json_response({"data": [
                {"id": 20, "name": "La Liga", "country_code": "ES", "type": "league", "women": True},
                {"id": 21, "name": "La Liga 2", "country_code": "ES", "type": "league", "women": False},
                {"id": 22, "name": "La Liga", "country_code": "ES", "type": "league", "women": False},
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
    assert first.resolve_league("la_liga").external_id == "22"
    assert [r.url.path for r in recorder1.requests] == ["/leagues"]
    second, recorder2 = provider(_events_route(pages), store=store)
    assert second.resolve_league("la_liga").external_id == "22"
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
    pages = [{"data": [], "pagination": {"hasMore": False}}]
    p, recorder = provider(_events_route(pages))
    league = p.resolve_league("la_liga")
    assert league.external_id == "22"
    assert dict(recorder.requests[0].url.params) == {"name": "la liga", "country_code": "ES", "page_size": "50"}
    p.get_forecasts("la_liga", date(2026, 9, 18), date(2026, 9, 25))
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
