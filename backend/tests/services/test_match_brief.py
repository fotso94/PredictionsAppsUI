"""
The evidence brief: what is known, what is missing, and why.

No database and no network. The freshness verdicts come from the real `ForecastService.freshness`
(with an in-memory cache) rather than from hand-written dictionaries, so "stale" and "refresh
blocked" mean here exactly what they mean in the running application.

The four situations B1 names must stay distinguishable in the payload: never fetched, fetched
without this market, fetched but stale, and blocked from refreshing. A reader has to be able to tell
"we do not know" from "nobody has asked recently".
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterator, Optional
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.predictions import League, Match, MatchStatus, Prediction, PredictionSource, PredictionStatus
from app.models.provider_data import ProviderForecastRecord
from app.schemas.matches import serialize_expert_prediction, serialize_forecast, serialize_match
from app.services.forecast_service import ForecastService
from app.services.match_brief import (
    FORECAST_STALE,
    MARKET_NOT_IN_FORECAST,
    MARKET_NOT_SUPPLIED,
    NO_EXPERT_PREDICTION,
    NO_FORECAST_RETRIEVED,
    REFRESH_BLOCKED,
    build_brief,
    compact_brief,
)
from app.services.match_cache import MatchCache
from app.services.providers.base import ForecastProvider
from tests.providers.support import FakeRedis

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=6)

#: Language the owner has ruled out everywhere: certainty, recommendation, urgency, loss recovery.
#: Matched as whole words so "Both teams" is not mistaken for a betting tip.
BANNED_WORDS = (
    "sure bet", "guaranteed", "guarantee", "can't lose", "cannot lose", "risk-free", "riskfree",
    "will win", "will lose", "will draw", "certain", "certainty", "definitely", "recommend",
    "recommended", "recommendation", "tip", "tips", "bet", "bets", "betting", "stake", "odds",
    "lock", "banker", "hurry", "act now", "last chance", "expires", "recover", "loss recovery",
)


# --------------------------------------------------------------------- scaffolding
class _StubProvider(ForecastProvider):
    name = "stub"
    integration_status = "test"

    def is_configured(self):
        return True

    def get_forecasts(self, key, date_from, date_to):  # pragma: no cover - never called here
        return []


@pytest.fixture
def forecasts() -> ForecastService:
    """A real ForecastService whose only live parts are the clock and the in-memory cache."""
    db = MagicMock()
    return ForecastService(db, provider=_StubProvider(), cache=MatchCache(client=FakeRedis()),
                           now=NOW, sync_fixtures=False)


def _match(kickoff: datetime = KICKOFF, status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    return Match(id=uuid.uuid4(), league_id=uuid.uuid4(), home_team_id=uuid.uuid4(),
                 away_team_id=uuid.uuid4(), match_date=kickoff.replace(tzinfo=None), status=status,
                 external_api_id="ext-1", external_api_source="stub", match_metadata={})


def _league(match: Match) -> Dict[Any, League]:
    return {match.league_id: League(id=match.league_id, name="Premier League",
                                    display_name="Premier League", country="England",
                                    league_metadata={"canonical_key": "premier_league"})}


def _record(match: Match, *, model_run_at: Optional[datetime] = None, **markets) -> ProviderForecastRecord:
    """A provider forecast holding only the markets the caller names. Nothing else is filled in."""
    values = {name: (Decimal(str(value)) if value is not None else None)
              for name, value in markets.items() if name != "exact_score"}
    return ProviderForecastRecord(
        id=uuid.uuid4(), match_id=match.id, provider="stub", external_event_id="evt-1",
        match_confidence="exact", matched_by="provider_id",
        model_run_at=(model_run_at or NOW - timedelta(hours=2)).replace(tzinfo=None),
        provider_updated_at=None, fetched_at=(NOW - timedelta(hours=1)).replace(tzinfo=None),
        exact_score=markets.get("exact_score"), **values)


def _expert_prediction(match: Match, **fields) -> Prediction:
    base = dict(home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
                confidence_score=Decimal("0.75"))
    base.update({name: (Decimal(str(value)) if value is not None else None)
                 for name, value in fields.items()})
    return Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                      created_by=uuid.uuid4(), status=PredictionStatus.PUBLISHED,
                      published_at=(NOW - timedelta(hours=4)).replace(tzinfo=None),
                      priority_level=100, reasoning="team news", **base)


def _brief(forecasts: ForecastService, match: Match, record: Optional[ProviderForecastRecord] = None,
           expert: Optional[Prediction] = None) -> Dict[str, Any]:
    """Build the brief exactly the way the match endpoints do."""
    freshness = forecasts.freshness(record, match)
    forecast = serialize_forecast(record, freshness)
    expert_payload = serialize_expert_prediction(expert)
    payload = serialize_match(match, {}, _league(match), forecast, expert_payload, {})
    return build_brief(match=payload, forecast=forecast, freshness=freshness,
                       expert=expert_payload, now=NOW)


def _market(brief: Dict[str, Any], key: str) -> Dict[str, Any]:
    return next(entry for entry in brief["markets"] if entry["key"] == key)


def _reasons(brief: Dict[str, Any], source: str = "model") -> set:
    return {entry["reason"] for entry in brief["missing"] if entry["source"] == source}


def _strings(value: Any) -> Iterator[str]:
    """Every string anywhere in the brief, so language rules can be asserted on the whole payload."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _full_1x2(match: Match, **extra) -> ProviderForecastRecord:
    return _record(match, home_win_prob=0.85, draw_prob=0.10, away_win_prob=0.05, **extra)


# --------------------------------------------------------------------- the four missing-data reasons
def test_no_forecast_ever_retrieved_says_so(forecasts):
    brief = _brief(forecasts, _match(), record=None)

    assert NO_FORECAST_RETRIEVED in _reasons(brief)
    assert brief["known"]["model_markets"] == []
    assert brief["freshness"]["state"] == "unavailable"
    assert brief["freshness"]["refresh_blocked"] is False
    assert _market(brief, "match_result")["model"]["reason"] == NO_FORECAST_RETRIEVED
    assert "has ever been retrieved" in _market(brief, "match_result")["model"]["detail"]


def test_a_market_left_out_of_an_existing_forecast_is_reported_as_such(forecasts):
    """Different from "never fetched": we have the fixture's forecast, it just lacks this market."""
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match))

    assert _market(brief, "match_result")["model"]["available"] is True
    btts = _market(brief, "btts")["model"]
    assert btts["available"] is False
    assert btts["reason"] == MARKET_NOT_IN_FORECAST
    assert NO_FORECAST_RETRIEVED not in _reasons(brief)
    assert {"scope": "market", "source": "model", "market": "btts", "reason": MARKET_NOT_IN_FORECAST,
            "detail": btts["detail"]} in brief["missing"]


def test_a_stale_forecast_is_reported_as_stale_and_keeps_its_numbers(forecasts):
    match = _match()
    stale_run = NOW - timedelta(hours=settings.FORECAST_MAX_AGE_HOURS + 8)
    brief = _brief(forecasts, match, record=_full_1x2(match, model_run_at=stale_run))

    assert brief["freshness"]["stale"] is True
    assert FORECAST_STALE in _reasons(brief)
    market = _market(brief, "match_result")["model"]
    # Stale is not the same as missing: the numbers we hold are still shown, flagged as old.
    assert market["state"] == "stale"
    assert market["available"] is True
    assert market["outcomes"][0]["percent"] == 85.0
    assert str(settings.FORECAST_MAX_AGE_HOURS) in market["detail"]


def test_a_blocked_refresh_is_reported_separately_from_an_absent_forecast(forecasts):
    forecasts._pause("daily request allowance for stub is spent", 3600)

    brief = _brief(forecasts, _match(), record=None)

    assert _reasons(brief) == {NO_FORECAST_RETRIEVED, REFRESH_BLOCKED}
    assert brief["freshness"]["refresh_blocked"] is True
    assert "allowance" in brief["freshness"]["refresh_blocked_reason"]
    blocked = next(e for e in brief["missing"] if e["reason"] == REFRESH_BLOCKED)
    assert "Nobody has asked the provider recently" in blocked["detail"]


def test_the_four_missing_data_reasons_produce_four_different_briefs(forecasts):
    """The whole point of B1: these four must not render identically."""
    stale_run = NOW - timedelta(hours=settings.FORECAST_MAX_AGE_HOURS + 8)
    never = _match()
    partial, stale, blocked = _match(), _match(), _match()

    briefs = {
        NO_FORECAST_RETRIEVED: _brief(forecasts, never, record=None),
        MARKET_NOT_IN_FORECAST: _brief(forecasts, partial, record=_full_1x2(partial)),
        FORECAST_STALE: _brief(forecasts, stale, record=_full_1x2(stale, model_run_at=stale_run)),
    }
    forecasts._pause("daily request allowance for stub is spent", 3600)
    briefs[REFRESH_BLOCKED] = _brief(forecasts, blocked, record=None)

    for reason, brief in briefs.items():
        assert reason in brief["missing_reasons"], f"{reason} missing from its own brief"
    signatures = [tuple(brief["missing_reasons"]) for brief in briefs.values()]
    assert len(set(signatures)) == len(signatures), f"briefs are not distinguishable: {signatures}"


def test_stale_and_blocked_are_two_independent_facts(forecasts):
    """Both at once still reads as two separate statements, not one merged 'unavailable'."""
    match = _match()
    stale_run = NOW - timedelta(hours=settings.FORECAST_MAX_AGE_HOURS + 8)
    forecasts._pause("daily request allowance for stub is spent", 3600)

    brief = _brief(forecasts, match, record=_full_1x2(match, model_run_at=stale_run))

    assert brief["freshness"]["stale"] is True and brief["freshness"]["refresh_blocked"] is True
    assert {FORECAST_STALE, REFRESH_BLOCKED} <= _reasons(brief)
    stale_entry = next(e for e in brief["missing"] if e["reason"] == FORECAST_STALE)
    blocked_entry = next(e for e in brief["missing"] if e["reason"] == REFRESH_BLOCKED)
    assert stale_entry["detail"] != blocked_entry["detail"]


# --------------------------------------------------------------------- never 0%
def test_a_market_absent_from_the_payload_never_appears_as_zero_percent(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match), expert=_expert_prediction(match))

    for key in ("btts", "over_under_25", "over_under_35"):
        for source in ("model", "expert"):
            block = _market(brief, key)[source]
            assert block["outcomes"] == [], f"{key}/{source} invented an outcome"
            assert block["available"] is False
            assert block["summary"] is None
            assert block["confidence"] is None
    # A bare 0% anywhere would mean a probability nobody published ("10%" is not one).
    assert re.search(r"(?<![\d.])0%", " ".join(_strings(brief))) is None
    assert 0 not in [outcome["percent"] for market in brief["markets"]
                     for source in ("model", "expert") for outcome in market[source]["outcomes"]]


def test_one_side_of_a_pair_is_never_completed_with_the_remainder(forecasts):
    """The provider published BTTS yes only. 1 - 0.55 is a number it never published."""
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match, btts_yes_prob=0.55))

    btts = _market(brief, "btts")["model"]
    assert [outcome["key"] for outcome in btts["outcomes"]] == ["yes"]
    assert btts["summary"] == ("The model puts both teams scoring at 55%, and published nothing for "
                              "at least one team not scoring.")
    assert "45" not in btts["summary"]


# --------------------------------------------------------------------- the plain-language line
def test_the_match_result_line_reads_as_a_probability_not_an_outcome(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match))

    assert _market(brief, "match_result")["model"]["summary"] == (
        "The model makes a home win the most likely single outcome at 85%, with a draw at 10%.")
    assert brief["headline"] == _market(brief, "match_result")["model"]["summary"]


def test_the_expert_gets_its_own_line(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=None, expert=_expert_prediction(match))

    assert _market(brief, "match_result")["expert"]["summary"] == (
        "The expert makes a home win the most likely single outcome at 50%, with a draw at 30%.")


def test_listed_scorelines_are_never_renormalised_and_the_other_bucket_stays_apart(forecasts):
    match = _match()
    record = _full_1x2(match, exact_score={"2-1": 0.12, "1-0": 0.09})
    record.exact_score_other_prob = Decimal("0.4")

    brief = _brief(forecasts, match, record=record)

    scores = _market(brief, "exact_score")["model"]
    assert [outcome["key"] for outcome in scores["outcomes"]] == ["2-1", "1-0"]
    assert scores["other_scorelines_percent"] == 40.0
    assert scores["summary"] == ("The model's most likely listed scoreline is 2-1 at 12%. "
                                 "Every other scoreline is grouped together at 40%.")


def test_the_brief_contains_no_recommendation_or_certainty_wording(forecasts):
    """Asserted on the text of every brief this module can produce, not on one sample."""
    match = _match()
    record = _full_1x2(match, btts_yes_prob=0.55, btts_no_prob=0.45, total_goals_over_25_prob=0.6,
                       total_goals_under_25_prob=0.4, exact_score={"2-1": 0.12})
    record.confidence = Decimal("0.7")
    record.anomalies = [{"severity": "note", "code": "market_incomplete",
                         "message": "Total goals 3.5 incomplete: over probability not supplied"}]
    forecasts._pause("daily request allowance for stub is spent", 3600)
    briefs = [
        _brief(forecasts, match, record=record, expert=_expert_prediction(match)),
        _brief(forecasts, _match(), record=None),
        _brief(forecasts, _match(status=MatchStatus.FINISHED, kickoff=NOW - timedelta(hours=4)),
               record=_full_1x2(match)),
    ]

    for brief in briefs:
        text = " ".join(_strings(brief)).lower()
        for word in BANNED_WORDS:
            assert not re.search(rf"\b{re.escape(word)}\b", text), f"banned wording {word!r} in brief"


# --------------------------------------------------------------------- probability is not reliability
def test_probability_confidence_and_accuracy_are_three_separate_facts(forecasts):
    """B2: a published probability, a published confidence and a measured accuracy cannot be merged."""
    match = _match()
    record = _full_1x2(match)  # GameForecastAPI publishes no confidence; this stub does not either
    expert = _expert_prediction(match)

    brief = _brief(forecasts, match, record=record, expert=expert)

    model = _market(brief, "match_result")["model"]
    assert model["outcomes"][0]["probability"] == pytest.approx(0.85)
    assert model["confidence_published"] is False and model["confidence"] is None
    assert model["accuracy_measured"] is False

    by_expert = _market(brief, "match_result")["expert"]
    assert by_expert["confidence_published"] is True
    assert by_expert["confidence"] == pytest.approx(0.75)
    assert by_expert["confidence_scope"] == "prediction"
    assert by_expert["accuracy_measured"] is False

    assert brief["reliability"]["accuracy_measured"] is False
    assert brief["reliability"]["model"]["confidence_published"] is False
    assert brief["reliability"]["expert"]["confidence_published"] is True


def test_a_provider_confidence_is_reported_with_the_scope_it_applies_to(forecasts):
    match = _match()
    record = _full_1x2(match)
    record.confidence = Decimal("0.62")

    brief = _brief(forecasts, match, record=record)

    model = _market(brief, "match_result")["model"]
    assert (model["confidence_published"], model["confidence"], model["confidence_scope"]) == (
        True, pytest.approx(0.62), "forecast")


def test_an_expert_who_published_no_confidence_is_not_reported_as_zero_confidence(forecasts):
    """confidence_score is NOT NULL and defaults to 0.0, which is an absence, not a published zero."""
    match = _match()
    expert = _expert_prediction(match, confidence_score=0.0)

    brief = _brief(forecasts, match, record=None, expert=expert)

    block = _market(brief, "match_result")["expert"]
    assert block["confidence_published"] is False
    assert block["confidence"] is None
    assert brief["reliability"]["expert"]["confidence_published"] is False


# --------------------------------------------------------------------- freshness
def test_the_three_provenance_times_stay_separate_and_unknown_ones_are_named(forecasts):
    match = _match()
    record = _full_1x2(match)
    record.provider_updated_at = None

    fresh = _brief(forecasts, match, record=record)["freshness"]

    assert fresh["model_run_at_known"] is True
    assert fresh["provider_updated_at_known"] is False
    assert fresh["retrieved_at_known"] is True
    assert fresh["unknown_timestamps"] == ["provider_updated_at"]
    # The age says which field it was measured from instead of falling back silently.
    assert fresh["age_basis"] == "model_run_at"
    assert fresh["age_hours"] == pytest.approx(2.0)


def test_a_forecast_with_no_model_run_time_says_that_rather_than_pretending(forecasts):
    match = _match()
    record = _full_1x2(match)
    record.model_run_at = None

    fresh = _brief(forecasts, match, record=record)["freshness"]

    assert fresh["model_run_at"] is None and fresh["model_run_at_known"] is False
    assert "model_run_at" in fresh["unknown_timestamps"]
    assert fresh["age_basis"] == "retrieved_at"


def test_a_played_match_keeps_its_forecast_for_reference_only(forecasts):
    match = _match(kickoff=NOW - timedelta(hours=4), status=MatchStatus.FINISHED)

    brief = _brief(forecasts, match, record=_full_1x2(match))

    assert brief["freshness"]["kickoff_passed"] is True
    assert _market(brief, "match_result")["model"]["state"] == "reference_only"


# --------------------------------------------------------------------- what is known
def test_the_brief_records_what_is_known_about_the_fixture(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match, btts_yes_prob=0.55, btts_no_prob=0.45),
                   expert=_expert_prediction(match, btts_yes_prob=0.6, btts_no_prob=0.4))

    known = brief["known"]
    assert known["kickoff_known"] is True and known["kickoff_utc"].endswith("Z")
    assert known["status"] == "scheduled"
    assert known["competition"]["name"] == "Premier League" and known["competition_known"] is True
    assert known["model_markets"] == ["match_result", "btts"]
    assert known["expert_markets"] == ["match_result", "btts"]
    assert _market(brief, "btts")["supplied_by"] == ["model", "expert"]


def test_a_missing_expert_prediction_is_its_own_reason(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match))

    assert _reasons(brief, source="expert") >= {NO_EXPERT_PREDICTION}
    assert _market(brief, "match_result")["expert"]["reason"] == NO_EXPERT_PREDICTION


def test_a_market_the_expert_left_out_is_not_the_same_as_no_expert_at_all(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=None, expert=_expert_prediction(match))

    assert _market(brief, "match_result")["expert"]["available"] is True
    assert _market(brief, "btts")["expert"]["reason"] == MARKET_NOT_SUPPLIED
    assert NO_EXPERT_PREDICTION not in _reasons(brief, source="expert")


# --------------------------------------------------------------------- compact form
def test_the_compact_brief_carries_the_card_facts_without_the_detail(forecasts):
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match), expert=_expert_prediction(match))

    compact = compact_brief(brief)

    assert compact["headline"] == brief["headline"]
    assert compact["supplied_markets"] == {"model": ["match_result"], "expert": ["match_result"]}
    assert "btts" in compact["missing_markets"]["model"]
    assert compact["forecast_state"] == "available"
    assert compact["accuracy_measured"] is False
    assert "markets" not in compact and "missing" not in compact


def test_the_compact_brief_still_distinguishes_blocked_from_absent(forecasts):
    forecasts._pause("daily request allowance for stub is spent", 3600)

    compact = compact_brief(_brief(forecasts, _match(), record=None))

    assert compact["refresh_blocked"] is True
    assert NO_FORECAST_RETRIEVED in compact["missing_reasons"]
    assert REFRESH_BLOCKED in compact["missing_reasons"]
