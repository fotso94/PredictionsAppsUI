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
from pathlib import Path
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
from app.services import match_brief, settlement
from app.services.match_brief import (
    FORECAST_STALE,
    MARKET_NOT_IN_FORECAST,
    MARKET_NOT_SUPPLIED,
    NO_EXPERT_PREDICTION,
    NO_FORECAST_RETRIEVED,
    REFRESH_BLOCKED,
    ACCURACY_AVAILABLE,
    ACCURACY_BELOW_MINIMUM_SAMPLE,
    ACCURACY_NO_SOURCE,
    ACCURACY_NOTHING_SCORED,
    ACCURACY_UNKNOWN,
    build_brief,
    compact_brief,
    summarise_scoring,
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


# ------------------------------------------------------- measured scoring, in its three states
#: A `settlement.measurement` payload, built here rather than from a database so the brief can be
#: driven through each state deliberately. Only the fields `summarise_scoring` reads are filled in.
def _measured_source(source_type: str, source_id: str, *, eligible: int, scored: int,
                     pending: int = 0, void: int = 0, not_scored: int = 0,
                     markets: Any = ()) -> Dict[str, Any]:
    return {"source_type": source_type, "source_id": source_id, "source_label": source_id,
            "eligible": eligible, "scored": scored, "pending": pending, "void": void,
            "not_scored": not_scored, "markets": list(markets), "measured": scored > 0,
            "not_measured_reason": None}


def _measured_market(name: str, scored: int, *, hit_rate: bool = False, brier: bool = False) -> Dict[str, Any]:
    return {"market": name, "scored": scored, "hits": 0, "hit_rate_available": hit_rate,
            "brier_available": brier}


def _measurement(*sources: Dict[str, Any], minimum: int = 30) -> Dict[str, Any]:
    return {
        "window": {"start": "2026-06-21", "end": "2026-09-19",
                   "basis": "kickoff date in UTC, both ends included"},
        "minimum_sample": minimum,
        "sources": list(sources),
        "sources_measured": sum(1 for source in sources if source["scored"]),
        "not_measured_reason": None if sources else ("no match in this window has reached a "
                                                     "terminal status yet, so there is nothing to score"),
        "measured_at": NOW.isoformat(),
    }


#: The three states, from the provider the forecasts in this file carry ("stub"). Real numbers from
#: the installation this package was written against: nine upcoming fixtures eligible and nothing
#: scored; four scored and no market near the minimum; and a sample that has cleared it.
NOTHING_SCORED = summarise_scoring(_measurement(
    _measured_source("model_provider", "stub", eligible=9, scored=0, pending=9)))
BELOW_MINIMUM = summarise_scoring(_measurement(
    _measured_source("model_provider", "stub", eligible=9, scored=4, pending=5,
                     markets=[_measured_market("match_result", 4)])))
MEASURED = summarise_scoring(_measurement(
    _measured_source("model_provider", "stub", eligible=120, scored=106, pending=14,
                     markets=[_measured_market("match_result", 106, hit_rate=True, brier=True)])))


@pytest.fixture(autouse=True)
def _no_cached_scoring():
    """No test may inherit another's cached summary, or reach a database for one."""
    match_brief.reset_scoring_cache()
    yield
    match_brief.reset_scoring_cache()


def _brief(forecasts: ForecastService, match: Match, record: Optional[ProviderForecastRecord] = None,
           expert: Optional[Prediction] = None,
           scoring: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the brief exactly the way the match endpoints do.

    ``scoring`` defaults to the nothing-scored state so the rest of this file keeps asserting
    against one known world; the tests that are about the scoring sentence pass the other two.
    """
    freshness = forecasts.freshness(record, match)
    forecast = serialize_forecast(record, freshness)
    expert_payload = serialize_expert_prediction(expert)
    payload = serialize_match(match, {}, _league(match), forecast, expert_payload, {})
    return build_brief(match=payload, forecast=forecast, freshness=freshness,
                       expert=expert_payload, now=NOW,
                       scoring=NOTHING_SCORED if scoring is None else scoring)


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


# --------------------------------------------------------------- F2: the accuracy sentence is measured
#: The sentence this package exists to remove. It was a module constant served on every match page
#: while /performance/sources reported four scored forecasts from the same database.
OLD_CONSTANT = "No prediction has been scored against a match result yet"


@pytest.mark.parametrize("scoring, state, measured, scored_anything", [
    (NOTHING_SCORED, ACCURACY_NOTHING_SCORED, False, False),
    (BELOW_MINIMUM, ACCURACY_BELOW_MINIMUM_SAMPLE, False, True),
    (MEASURED, ACCURACY_AVAILABLE, True, True),
])
def test_the_reliability_detail_follows_the_measured_scoring_state(
        forecasts, scoring, state, measured, scored_anything):
    """F2: one brief builder, three worlds, three different answers.

    The three have to stay told apart. "Nothing has been scored" and "four have been scored and
    that is too few to publish a rate" are different facts, and a surface that says the first when
    the second is true is the defect this package closes.
    """
    match = _match()
    brief = _brief(forecasts, match, record=_full_1x2(match), scoring=scoring)
    reliability = brief["reliability"]

    assert reliability["accuracy_state"] == state
    assert reliability["accuracy_measured"] is measured
    assert reliability["results_scored"] is scored_anything
    # The counts the sentence was built from travel with it, so a reader can check the arithmetic.
    assert reliability["scoring"]["scored"] == scoring["scored"]
    assert reliability["scoring"]["minimum_sample"] == 30
    assert reliability["scoring"]["window"]["start"] == "2026-06-21"


def test_only_the_nothing_scored_state_says_nothing_has_been_scored(forecasts):
    """The half of F2 that is easy to lose: the honest absence has to survive the repair."""
    match = _match()
    claim = re.compile(r"has been scored against a match result yet", re.I)

    nothing = _brief(forecasts, match, record=_full_1x2(match))["reliability"]["detail"]
    below = _brief(forecasts, match, record=_full_1x2(match), scoring=BELOW_MINIMUM)["reliability"]["detail"]
    measured = _brief(forecasts, match, record=_full_1x2(match), scoring=MEASURED)["reliability"]["detail"]

    assert claim.search(nothing), "the honest nothing-scored sentence must still be reachable"
    assert "9 prediction(s)" in nothing and "9 are still waiting to be scored" in nothing
    assert not claim.search(below) and not claim.search(measured)
    # Each state is a sentence of its own: none of the three can stand in for another.
    assert len({nothing, below, measured}) == 3


def test_a_withheld_rate_is_a_sentence_with_its_counts_and_never_a_figure(forecasts):
    """The standing rule: a percentage below the minimum sample is withheld in words, not as 0%."""
    match = _match()
    detail = _brief(forecasts, match, record=_full_1x2(match), scoring=BELOW_MINIMUM)["reliability"]["detail"]

    assert "4 of 9 eligible prediction(s)" in detail
    assert "minimum of 30 scored predictions" in detail
    assert "The counts are published; the rate is not." in detail
    assert "%" not in detail, "a withheld rate is a sentence, never a percentage"


def test_each_source_gets_the_record_of_that_source_and_not_of_another(forecasts):
    """The sentence says "this source", so it has to be counted per source.

    Here the model provider has a measured record and the expert has none at all. One shared
    installation-wide sentence would have credited the expert with the provider's sample.
    """
    match = _match()
    scoring = summarise_scoring(_measurement(
        _measured_source("model_provider", "stub", eligible=120, scored=106,
                         markets=[_measured_market("match_result", 106, hit_rate=True)])))
    brief = _brief(forecasts, match, record=_full_1x2(match), expert=_expert_prediction(match),
                   scoring=scoring)

    model = _market(brief, "match_result")["model"]
    expert = _market(brief, "match_result")["expert"]

    assert model["accuracy_state"] == ACCURACY_AVAILABLE and model["accuracy_measured"] is True
    assert "from stub" in model["accuracy_detail"] and "106 of 120" in model["accuracy_detail"]
    # The expert is absent from the measured rows, which is itself a measurement, not a blank.
    assert expert["accuracy_state"] == ACCURACY_NOTHING_SCORED
    assert expert["accuracy_measured"] is False
    assert "Nothing from this expert has been scored" in expert["accuracy_detail"]
    assert "106" not in expert["accuracy_detail"]


# --------------------------------------------- K1: a block for a source that is not on this fixture
def test_the_expert_block_of_a_fixture_with_no_expert_never_quotes_the_installation_record(forecasts):
    """K1: a per-source block states what is true of THAT source, or of nothing at all.

    Every fixture on this installation is in exactly this position — no expert has published
    anything — so this is the sentence the expert block of every market on every match page
    actually renders. It used to be the installation-wide sentence, which on this data is a
    statement about the model provider's scored record, sitting inside a block about experts.
    """
    match = _match()
    scoring = summarise_scoring(_measurement(
        _measured_source("model_provider", "stub", eligible=120, scored=106, pending=14,
                         markets=[_measured_market("match_result", 106, hit_rate=True)])))
    brief = _brief(forecasts, match, record=_full_1x2(match), scoring=scoring)

    block = _market(brief, "match_result")["expert"]

    assert block["accuracy_state"] == ACCURACY_NO_SOURCE
    assert block["accuracy_measured"] is False
    assert "No expert has published a prediction for this match." in block["accuracy_detail"]
    # Something true about experts, and nothing at all about the provider's record.
    assert "expert" in block["accuracy_detail"]
    assert scoring["detail"] not in block["accuracy_detail"]
    for borrowed in ("106", "120", "stub", "on this installation with a kickoff"):
        assert borrowed not in block["accuracy_detail"], f"the provider's record leaked in: {borrowed}"
    # And the source that IS on this fixture keeps its own record, counted from its own row.
    model = _market(brief, "match_result")["model"]
    assert model["accuracy_state"] == ACCURACY_AVAILABLE
    assert "106 of 120" in model["accuracy_detail"]


def test_no_expert_published_and_this_expert_has_no_record_are_different_sentences(forecasts):
    """The two statements the reader may need, and neither may stand in for the other.

    "Nobody published a view of this match" is a fact about this fixture; "this expert has never
    been scored" is a fact about a person who did publish one. A block that has no expert cannot
    make the second statement, because there is no expert for it to be about.
    """
    match = _match()
    scoring = summarise_scoring(_measurement(
        _measured_source("model_provider", "stub", eligible=120, scored=106,
                         markets=[_measured_market("match_result", 106, hit_rate=True)])))

    absent = _market(_brief(forecasts, match, record=None, scoring=scoring), "match_result")["expert"]
    unscored = _market(_brief(forecasts, match, record=None, expert=_expert_prediction(match),
                              scoring=scoring), "match_result")["expert"]

    assert absent["accuracy_state"] == ACCURACY_NO_SOURCE
    assert unscored["accuracy_state"] == ACCURACY_NOTHING_SCORED
    assert absent["accuracy_detail"] != unscored["accuracy_detail"]
    assert "No expert has published a prediction for this match." in absent["accuracy_detail"]
    assert "Nothing from this expert has been scored" in unscored["accuracy_detail"]
    # The fixture with no expert must not claim a record for an expert it does not have.
    assert "this expert" not in absent["accuracy_detail"]


def test_the_model_block_of_a_fixture_with_no_forecast_is_treated_the_same_way(forecasts):
    """The same helper, the same defect: a block with no source of its own borrowed the total.

    Here the installation-wide figure is dominated by an expert sample the model provider had no
    part in, so a model block quoting it would be crediting the provider with somebody else's
    scored predictions.
    """
    match = _match()
    scoring = summarise_scoring(_measurement(
        _measured_source("model_provider", "stub", eligible=9, scored=0, pending=9),
        _measured_source("expert", str(uuid.uuid4()), eligible=44, scored=44,
                         markets=[_measured_market("match_result", 44, hit_rate=True)])))
    brief = _brief(forecasts, match, record=None, scoring=scoring)

    block = _market(brief, "match_result")["model"]

    assert block["accuracy_state"] == ACCURACY_NO_SOURCE
    assert block["accuracy_measured"] is False
    assert "No provider forecast has been retrieved for this match." in block["accuracy_detail"]
    assert scoring["detail"] not in block["accuracy_detail"]
    assert "44" not in block["accuracy_detail"], "the expert sample is not the provider's record"


def test_a_block_with_no_source_never_claims_the_source_published_nothing(forecasts):
    """Retrieved is not published, in the one branch of the no-source sentence that lost it.

    This branch needs a kind that has cleared the minimum sample, so it is not reachable on
    today's four scored forecasts — which is exactly why it has to be pinned now. What is known
    about a fixture we hold no forecast for is that none was RETRIEVED; whether the provider
    published one is precisely what we cannot know, and least of all while refreshing is paused.
    The same sentence serves both kinds, so it may only assert what is true of both.
    """
    match = _match()
    scoring = summarise_scoring(_measurement(
        _measured_source("model_provider", "stub", eligible=40, scored=40,
                         markets=[_measured_market("match_result", 40, hit_rate=True)])))

    block = _market(_brief(forecasts, match, record=None, scoring=scoring), "match_result")["model"]

    assert block["accuracy_state"] == ACCURACY_NO_SOURCE
    assert "No provider forecast has been retrieved for this match." in block["accuracy_detail"]
    assert "1 figure(s) have reached the minimum sample of 30" in block["accuracy_detail"]
    assert "none of that record is this match's" in block["accuracy_detail"]
    assert "published a view of it" not in block["accuracy_detail"], (
        "we hold that nothing was retrieved, never that the provider published nothing")


# --------------------------------------------- K2: whose database session a page load measures on
def test_the_match_endpoint_measures_on_the_request_session_and_opens_none_of_its_own(
        forecasts, monkeypatch):
    """K2: the request already holds a session, so the brief must not open a second one.

    Driven through the endpoint helper that actually builds every match payload, because the
    defect was not in ``build_brief`` — which accepts a measured summary — but in the one caller
    that never passed it and so took the fallback on every page load with a cold cache.
    """
    from app.api.v1.endpoints import matches as matches_endpoint
    from app.db import session as db_session

    first, second = _match(), _match()
    record = _full_1x2(first)
    measured_with = []
    opened = []

    def measurement(db, **kwargs):
        measured_with.append(db)
        return _measurement(_measured_source("model_provider", "stub", eligible=9, scored=4,
                                             pending=5, markets=[_measured_market("match_result", 4)]))

    def session_local(*args, **kwargs):
        opened.append(args)
        raise AssertionError("a page load opened a database session of its own")

    monkeypatch.setattr(settlement, "measurement", measurement)
    monkeypatch.setattr(db_session, "SessionLocal", session_local)
    monkeypatch.setattr(forecasts, "forecast_for_match", lambda match, provider_name=None: record)

    request_db = MagicMock(name="the request's own session")
    request_db.query.return_value.filter.return_value.all.return_value = []
    request_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    service = MagicMock()
    service.registry.team_names.return_value = {}
    service.registry.leagues_by_id.return_value = {**_league(first), **_league(second)}

    payloads = matches_endpoint.build_match_payloads(request_db, [first, second], service,
                                                     forecasts, full_brief=True)

    assert opened == [], "the fallback session must not be reached from an endpoint"
    assert measured_with == [request_db], (
        "the measurement runs once for the request, on the session the request already holds")
    # And the measured figures really did reach the payload, so this is not passing on a silence.
    assert len(payloads) == 2
    for payload in payloads:
        assert "4 of 9 eligible prediction(s) on this installation" in payload["brief"]["reliability"]["detail"]


def test_a_caller_with_no_session_of_its_own_still_gets_a_measured_summary(monkeypatch):
    """The fallback stays for callers that genuinely hold no session: scripts, shells, tests.

    No endpoint in this application is one of those any more, and this is the test that would go
    red if the fallback were deleted rather than left for them.
    """
    from app.db import session as db_session

    own_session = MagicMock(name="a session of the module's own")
    measured_with = []
    monkeypatch.setattr(db_session, "SessionLocal", lambda: own_session)
    monkeypatch.setattr(settlement, "measurement",
                        lambda db, **kwargs: measured_with.append(db) or _measurement(
                            _measured_source("model_provider", "stub", eligible=9, scored=0, pending=9)))
    match_brief.reset_scoring_cache()

    summary = match_brief.current_scoring_summary()

    assert measured_with == [own_session]
    own_session.close.assert_called_once()
    assert summary["accuracy_state"] == ACCURACY_NOTHING_SCORED


def test_the_compact_brief_carries_the_state_and_not_only_the_boolean(forecasts):
    match = _match()

    below = compact_brief(_brief(forecasts, match, record=_full_1x2(match), scoring=BELOW_MINIMUM))
    measured = compact_brief(_brief(forecasts, match, record=_full_1x2(match), scoring=MEASURED))

    assert below["accuracy_state"] == ACCURACY_BELOW_MINIMUM_SAMPLE
    assert below["accuracy_measured"] is False
    assert measured["accuracy_state"] == ACCURACY_AVAILABLE
    assert measured["accuracy_measured"] is True


def test_counts_that_cannot_be_read_are_unknown_and_never_nothing_scored(forecasts, monkeypatch):
    """A failed read is not an absence of results. Reporting it as one would be the same bug."""
    def explode(db, *, now=None):
        raise RuntimeError("could not connect to server")

    monkeypatch.setattr(match_brief, "scoring_summary", explode)
    match_brief.reset_scoring_cache()

    summary = match_brief.current_scoring_summary()
    brief = _brief(forecasts, _match(), record=None, scoring=summary)

    assert summary["accuracy_state"] == ACCURACY_UNKNOWN
    assert summary["results_scored"] is None, "unknown is not False"
    assert brief["reliability"]["accuracy_state"] == ACCURACY_UNKNOWN
    assert "could not be read" in brief["reliability"]["detail"]
    assert "has been scored against a match result yet" not in brief["reliability"]["detail"]
    assert brief["reliability"]["scoring"]["unavailable_reason"] == "could not connect to server"


def test_the_summary_is_measured_once_per_window_not_once_per_match(forecasts, monkeypatch):
    """Cheapness is part of the requirement: this is on a page load, once per fixture in a list."""
    calls = {"n": 0}

    def counted(db, *, now=None):
        calls["n"] += 1
        return NOTHING_SCORED

    monkeypatch.setattr(match_brief, "scoring_summary", counted)
    match_brief.reset_scoring_cache()

    for _ in range(30):
        match_brief.current_scoring_summary()

    assert calls["n"] == 1, "a thirty-fixture list must not run the measurement thirty times"
    match_brief.reset_scoring_cache()
    match_brief.current_scoring_summary()
    assert calls["n"] == 2, "and resetting the cache must actually re-measure"


@pytest.mark.parametrize("measurement", [
    _measurement(),
    _measurement(_measured_source("model_provider", "stub", eligible=9, scored=0, pending=9)),
    _measurement(_measured_source("model_provider", "stub", eligible=9, scored=4, pending=5,
                                  markets=[_measured_market("match_result", 4)])),
    _measurement(_measured_source("model_provider", "stub", eligible=120, scored=106,
                                  markets=[_measured_market("match_result", 106, hit_rate=True)])),
])
def test_the_brief_and_the_coverage_endpoint_reach_the_same_state_from_one_measurement(
        measurement, monkeypatch):
    """Anti-drift: two surfaces, one database, one answer.

    /api/v1/data-providers/coverage already keeps these three states apart. The brief now does
    too, and the two must never be able to describe the same counts differently — so both are
    driven from a single measurement payload here and their states compared. This is the pin that
    fails if either side is edited alone.
    """
    from app.api.v1.endpoints import data_providers

    monkeypatch.setattr(settlement, "measurement", lambda db, **kwargs: measurement)

    from_brief = match_brief.scoring_summary(db=None)
    from_coverage = data_providers._accuracy_state(None, NOW)

    assert from_brief["accuracy_state"] == from_coverage["accuracy_state"]
    assert from_brief["accuracy_measured"] == from_coverage["accuracy_available"]
    assert from_brief["scored"] == from_coverage["scoring"]["scored"]
    assert from_brief["published_figures"] == from_coverage["scoring"]["published_figures"]
    # And the vocabulary itself is the same three words, not two parallel sets of them.
    assert from_brief["accuracy_state"] in {data_providers.ACCURACY_NOTHING_SCORED,
                                            data_providers.ACCURACY_BELOW_MINIMUM_SAMPLE,
                                            data_providers.ACCURACY_AVAILABLE}


def test_no_constant_in_the_brief_states_whether_anything_has_been_scored():
    """F2, the defect itself: a fact about the database cannot live in a string literal.

    Scanning the source rather than the payload is deliberate. A payload assertion only proves the
    sentence is wrong for the one state a test happens to build; this proves the sentence cannot be
    a standing claim at all, which is the property that keeps going false as results come in.
    """
    source = Path(match_brief.__file__).read_text(encoding="utf-8")
    assert OLD_CONSTANT not in source, (
        "the scored-state sentence is still written into the module; it has to be computed")
    assert not hasattr(match_brief, "ACCURACY_DETAIL"), "the constant is still exported"
    assert not hasattr(match_brief, "ACCURACY_MEASURED"), "the constant is still exported"
