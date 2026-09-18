"""Live Score API provider — mocked HTTP (no credentials, no network)."""

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.services.providers.base import (
    STATUS_FINISHED, STATUS_HALFTIME, STATUS_LIVE, STATUS_SCHEDULED,
    ProviderAuthError, ProviderNotConfiguredError, ProviderQuotaError, ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.match_cache import MatchCache
from tests.providers.support import FakeRedis, json_response, make_transport

COMPETITIONS = {"success": True, "data": {"competition": [
    {"id": "2", "name": "Premier League", "is_cup": "0", "countries": [{"name": "England", "fifa_code": "ENG"}],
     "season": {"name": "2026/2027"}},
    {"id": "9", "name": "Premier League 2", "is_cup": "0", "countries": [{"name": "England"}]},
    {"id": "11", "name": "Women's Super League", "is_cup": "0", "countries": [{"name": "England"}]},
    {"id": "3", "name": "LaLiga", "is_cup": "0", "countries": [{"name": "Spain"}]},
    {"id": "4", "name": "Serie A", "is_cup": "0", "countries": [{"name": "Italy"}]},
    {"id": "5", "name": "Serie A Femminile", "is_cup": "0", "countries": [{"name": "Italy"}]},
    {"id": "1", "name": "Bundesliga", "is_cup": "0", "countries": [{"name": "Germany"}]},
    {"id": "6", "name": "2. Bundesliga", "is_cup": "0", "countries": [{"name": "Germany"}]},
    {"id": "7", "name": "Ligue 1", "is_cup": "0", "countries": [{"name": "France"}]},
], "next_page": False}}

FIXTURES_PAGE_1 = {"success": True, "data": {"fixtures": [
    {"id": "1001", "date": "2026-09-20", "time": "14:00:00", "round": "5", "location": "Anfield",
     "home": {"id": "1", "name": "Liverpool", "logo": "https://x/l.png"}, "away": {"id": "2", "name": "Everton"},
     "competition": {"id": "2", "name": "Premier League"}, "country": {"name": "England"}},
], "next_page": "https://livescore-api.com/api-client/fixtures/list.json?page=2"}}
FIXTURES_PAGE_2 = {"success": True, "data": {"fixtures": [
    {"id": "1002", "date": "2026-09-20", "time": "16:30:00", "round": "5", "location": "Old Trafford",
     "home": {"id": "3", "name": "Manchester United"}, "away": {"id": "4", "name": "Chelsea"},
     "competition": {"id": "2", "name": "Premier League"}, "country": {"name": "England"}},
], "next_page": False}}

LIVE = {"success": True, "data": {"match": [
    {"id": "77", "fixture_id": "1001", "date": "2026-09-20", "scheduled": "14:00", "time": "63", "status": "IN PLAY",
     "home": {"id": "1", "name": "Liverpool"}, "away": {"id": "2", "name": "Everton"},
     "scores": {"score": "2 - 1", "ht_score": "1 - 1"}, "competition": {"id": "2", "name": "Premier League"},
     "country": {"name": "England"}},
    {"id": "78", "fixture_id": "1002", "date": "2026-09-20", "scheduled": "16:30", "time": "HT", "status": "HALF TIME BREAK",
     "home": {"id": "3", "name": "Manchester United"}, "away": {"id": "4", "name": "Chelsea"},
     "scores": {"score": "0 - 0", "ht_score": "0 - 0"}, "competition": {"id": "2", "name": "Premier League"},
     "country": {"name": "England"}},
    {"id": "79", "fixture_id": "5000", "date": "2026-09-20", "scheduled": "15:00", "time": "40", "status": "IN PLAY",
     "home": {"id": "9", "name": "Some Club"}, "away": {"id": "10", "name": "Other Club"},
     "scores": {"score": "0 - 1"}, "competition": {"id": "999", "name": "Eliteserien"}, "country": {"name": "Norway"}},
]}}

HISTORY = {"success": True, "data": {"match": [
    {"id": "70", "fixture_id": "990", "date": "2026-09-13", "scheduled": "14:00", "time": "FT", "status": "FINISHED",
     "home": {"id": "1", "name": "Liverpool"}, "away": {"id": "4", "name": "Chelsea"},
     "scores": {"score": "3 - 1", "ht_score": "2 - 0", "ft_score": "3 - 1"},
     "competition": {"id": "2", "name": "Premier League"}, "country": {"name": "England"}},
], "next_page": False}}

TABLE = {"success": True, "data": {"table": [
    {"rank": "1", "team": {"id": "1", "name": "Liverpool"}, "matches": "5", "won": "4", "drawn": "1", "lost": "0",
     "goals_scored": "12", "goals_conceded": "3", "goal_diff": "9", "points": "13", "form": ["W", "W", "D", "W", "W"]},
    {"rank": "2", "team": {"id": "4", "name": "Chelsea"}, "matches": "5", "won": "3", "drawn": "1", "lost": "1",
     "goals_scored": "9", "goals_conceded": "5", "goal_diff": "4", "points": "10", "form": []},
]}}


def _route(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = dict(request.url.params)
    assert params.get("key") == "trial-key" and params.get("secret") == "trial-secret"
    if path.endswith("competitions/list.json"):
        return json_response(COMPETITIONS)
    if path.endswith("fixtures/list.json"):
        assert params.get("competition_id") == "2"
        return json_response(FIXTURES_PAGE_2 if params.get("page") == "2" else FIXTURES_PAGE_1)
    if path.endswith("matches/live.json"):
        return json_response(LIVE)
    if path.endswith("matches/history.json"):
        assert params["from"] == "2026-09-13" and params["to"] == "2026-09-13"
        return json_response(HISTORY)
    if path.endswith("competitions/table.json"):
        assert params.get("include_form") == "1"
        return json_response(TABLE)
    return json_response({"success": False, "error": "unknown endpoint"}, 404)


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """Requests are spaced 1 s apart against the real API; tests must not wait."""
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)


def provider(handler=_route, key="trial-key", secret="trial-secret", budget=None, overrides=None, store=None,
             use_default_ids=False):
    transport, recorder = make_transport(handler)
    p = LiveScoreAPIProvider(api_key=key, api_secret=secret, transport=transport,
                             budget=budget or RequestBudget("livescore", 1200, client=FakeRedis()),
                             competition_overrides=overrides if overrides is not None else {},
                             store=store or MatchCache(client=FakeRedis()), use_default_ids=use_default_ids)
    return p, recorder


def test_default_ids_avoid_the_competition_list_entirely():
    p, recorder = provider(use_default_ids=True)
    comps = {c.key: c.external_id for c in p.list_competitions(
        ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league"])}
    assert comps == {"premier_league": "2", "la_liga": "3", "serie_a": "4", "bundesliga": "1", "ligue_1": "5", "champions_league": "244"}
    assert recorder.requests == []


def test_exact_name_wins_over_lookalikes_listed_first():
    payload = {"success": True, "data": {"competition": [
        {"id": "487", "name": "Non Premier League", "is_cup": "0", "countries": [{"name": "England"}]},
        {"id": "93", "name": "2nd Bundesliga", "is_cup": "0", "countries": [{"name": "Germany"}]},
        {"id": "268", "name": "Champions League", "is_cup": "1", "federations": [{"name": "CONCACAF"}]},
        {"id": "512", "name": "Premier League", "is_cup": "0", "countries": [{"name": "Belize"}]},
        {"id": "2", "name": "Premier League", "is_cup": "0", "countries": [{"name": "England"}]},
        {"id": "1", "name": "Bundesliga", "is_cup": "0", "countries": [{"name": "Germany"}]},
        {"id": "244", "name": "Champions League", "is_cup": "1", "federations": [{"name": "UEFA"}]},
    ], "next_page": False}}
    p, _ = provider(lambda r: json_response(payload))
    comps = {c.key: c.external_id for c in p.list_competitions(["premier_league", "bundesliga", "champions_league"])}
    assert comps == {"premier_league": "2", "bundesliga": "1", "champions_league": "244"}


def test_burst_401_is_retried_once_before_failing():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return json_response({"success": False, "error": "This API key and secret do not have access to our data enabled"}, 401)
        return json_response(FIXTURES_PAGE_2)
    p, recorder = provider(flaky, overrides={"premier_league": "2"})
    fixtures = p.get_fixtures(date(2026, 9, 20), ["premier_league"])
    assert [f.external_id for f in fixtures] == ["1002"] and len(recorder.requests) == 2

    always = lambda r: json_response({"success": False, "error": "This API key and secret do not have access to our data enabled"}, 401)
    p, recorder = provider(always, overrides={"premier_league": "2"})
    with pytest.raises(ProviderAuthError):
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])
    assert len(recorder.requests) == 2  # exactly one retry


def test_resolved_competition_ids_persist_across_provider_instances():
    store = MatchCache(client=FakeRedis())
    first, recorder1 = provider(store=store)
    assert first.list_competitions(["premier_league", "la_liga"])[0].external_id == "2"
    assert len(recorder1.requests) == 1
    second, recorder2 = provider(store=store)
    comps = second.list_competitions(["premier_league", "la_liga"])
    assert [c.external_id for c in comps] == ["2", "3"]
    assert recorder2.requests == []  # served from the shared store, no competitions/list call


def test_not_configured_raises_before_any_request():
    p, recorder = provider(key="", secret="")
    assert p.is_configured() is False
    with pytest.raises(ProviderNotConfiguredError):
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])
    assert recorder.requests == []


def test_competitions_resolved_by_name_and_country_excluding_variants():
    p, recorder = provider()
    comps = {c.key: c for c in p.list_competitions(["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1"])}
    assert {k: c.external_id for k, c in comps.items()} == {
        "premier_league": "2", "la_liga": "3", "serie_a": "4", "bundesliga": "1", "ligue_1": "7"}
    assert comps["premier_league"].season_name == "2026/2027"
    # the list was fetched once; a second lookup of already resolved keys makes no request
    assert p.list_competitions(["serie_a"])[0].external_id == "4"
    assert len(recorder.requests) == 1


def test_competition_id_override_avoids_network():
    p, recorder = provider(overrides={"premier_league": "2"})
    assert p.list_competitions(["premier_league"])[0].external_id == "2"
    assert recorder.requests == []


def test_fixtures_are_paginated_and_mapped_to_utc():
    p, recorder = provider(overrides={"premier_league": "2"})
    fixtures = p.get_fixtures(date(2026, 9, 20), ["premier_league"])
    assert [f.external_id for f in fixtures] == ["1001", "1002"]
    first = fixtures[0]
    assert first.provider == "livescore"
    assert first.kickoff_utc == datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    assert first.status == STATUS_SCHEDULED
    assert first.home.name == "Liverpool" and first.away.name == "Everton"
    assert first.home.logo == "https://x/l.png"
    assert first.venue == "Anfield" and first.round == "5"
    assert first.competition.key == "premier_league" and first.competition.external_id == "2"
    pages = [dict(r.url.params).get("page") for r in recorder.requests]
    assert pages == [None, "2"]
    assert dict(recorder.requests[0].url.params)["date"] == "2026-09-20"


def test_live_matches_filtered_to_covered_competitions_and_status_mapped():
    p, _ = provider(overrides={"premier_league": "2"})
    live = p.get_live(["premier_league"])
    assert [f.external_id for f in live] == ["1001", "1002"]  # fixture_id preferred, foreign competition dropped
    assert live[0].status == STATUS_LIVE and live[0].minute == "63"
    assert (live[0].home_score, live[0].away_score, live[0].ht_home_score, live[0].ht_away_score) == (2, 1, 1, 1)
    assert live[1].status == STATUS_HALFTIME


def test_results_from_history_are_finished_with_scores():
    p, _ = provider(overrides={"premier_league": "2"})
    results = p.get_results(date(2026, 9, 13), date(2026, 9, 13), ["premier_league"])
    assert len(results) == 1
    assert results[0].status == STATUS_FINISHED
    assert (results[0].home_score, results[0].away_score) == (3, 1)
    assert results[0].external_id == "990"


def test_standings_mapping():
    p, _ = provider(overrides={"premier_league": "2"})
    rows = p.get_standings("premier_league")
    assert [r.position for r in rows] == [1, 2]
    assert rows[0].team.name == "Liverpool" and rows[0].points == 13 and rows[0].goal_difference == 9
    assert rows[0].form == ["W", "W", "D", "W", "W"] and rows[1].form == []


@pytest.mark.parametrize("payload,exc", [
    ({"success": False, "error": "This API key and secret do not have access to our data enabled"}, ProviderAuthError),
    ({"success": False, "error": "Your API key has expired"}, ProviderAuthError),
    ({"success": False, "error": "Request limit reached for today"}, ProviderQuotaError),
    ({"success": False, "error": "Something else"}, ProviderUnavailableError),
])
def test_api_level_errors_are_classified(payload, exc):
    p, _ = provider(lambda r: json_response(payload), overrides={"premier_league": "2"})
    with pytest.raises(exc):
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])


@pytest.mark.parametrize("status_code,exc", [(401, ProviderAuthError), (403, ProviderAuthError), (429, ProviderQuotaError),
                                              (500, ProviderUnavailableError), (404, ProviderUnavailableError)])
def test_http_errors_are_classified(status_code, exc):
    p, _ = provider(lambda r: httpx.Response(status_code, text="nope"), overrides={"premier_league": "2"})
    with pytest.raises(exc):
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])


def test_network_error_is_unavailable():
    def boom(request):
        raise httpx.ConnectError("connection refused", request=request)
    p, _ = provider(boom, overrides={"premier_league": "2"})
    with pytest.raises(ProviderUnavailableError):
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])


def test_daily_budget_blocks_requests_before_they_are_sent():
    budget = RequestBudget("livescore", 2, client=FakeRedis())
    p, recorder = provider(budget=budget, overrides={"premier_league": "2"})
    p.get_fixtures(date(2026, 9, 20), ["premier_league"])  # two pages = two requests
    assert len(recorder.requests) == 2
    with pytest.raises(ProviderQuotaError):
        p.get_fixtures(date(2026, 9, 21), ["premier_league"])
    assert len(recorder.requests) == 2  # nothing was sent once the budget was spent


def test_live_window():
    kickoff = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    assert LiveScoreAPIProvider.live_window(kickoff, kickoff - timedelta(minutes=20)) is False
    assert LiveScoreAPIProvider.live_window(kickoff, kickoff - timedelta(minutes=10)) is True
    assert LiveScoreAPIProvider.live_window(kickoff, kickoff + timedelta(minutes=140)) is True
    assert LiveScoreAPIProvider.live_window(kickoff, kickoff + timedelta(minutes=160)) is False


def test_auth_error_carries_the_provider_message():
    body = {"success": False, "error": "This API key and secret do not have access to our data enabled"}
    p, _ = provider(lambda r: json_response(body, 401), overrides={"premier_league": "2"})
    with pytest.raises(ProviderAuthError) as exc:
        p.get_fixtures(date(2026, 9, 20), ["premier_league"])
    assert "do not have access to our data enabled" in str(exc.value)


def test_upcoming_stops_paginating_after_the_window():
    def calendar(request):
        params = dict(request.url.params)
        assert params.get("competition_id") == "2" and "date" not in params
        if params.get("page") is None:
            return json_response({"success": True, "data": {"fixtures": [
                {"id": "1", "date": "2026-09-20", "time": "14:00:00", "home": {"id": "1", "name": "A"}, "away": {"id": "2", "name": "B"},
                 "competition": {"id": "2", "name": "Premier League"}},
                {"id": "2", "date": "2026-10-20", "time": "14:00:00", "home": {"id": "3", "name": "C"}, "away": {"id": "4", "name": "D"},
                 "competition": {"id": "2", "name": "Premier League"}},
            ], "next_page": "yes"}})
        raise AssertionError("page 2 must not be requested once the window is passed")
    p, recorder = provider(calendar, overrides={"premier_league": "2"})
    from unittest.mock import patch
    from datetime import datetime as real_datetime
    class FrozenDate(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 9, 18, 12, 0, tzinfo=tz)
    with patch("app.services.providers.livescore_api.datetime", FrozenDate):
        fixtures = p.get_upcoming("premier_league", days_ahead=7)
    assert [f.external_id for f in fixtures] == ["1"] and len(recorder.requests) == 1
