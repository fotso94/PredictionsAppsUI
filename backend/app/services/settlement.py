"""Result scoring: measuring what a source actually said against what actually happened.

Nothing here predicts anything. Settlement is arithmetic on two stored facts - the probabilities a
source published before kickoff, and the score of the match that was played - and it never fills a
gap. A market a source did not publish is not scored; it is not a loss, and it is not a zero.

Two different things are scored, and they are kept apart:

* expert predictions (``predictions.predictions``)   -> ``predictions.prediction_results``
* provider forecasts, scored from the PREMATCH SNAPSHOT (``provider_forecast_snapshots``)
                                                      -> ``predictions.provider_forecast_results``

Why the snapshot and not ``provider_forecasts``: the current row is overwritten whenever the model
changes its mind, including after kickoff. Scoring it would credit a provider with a forecast it did
not publish before the match. Only a snapshot with ``captured_before_kickoff IS TRUE`` is scored;
"unknown" (NULL) is not proof of prematch and is refused like "after kickoff" is.

The same rule applies to an expert: a published prediction that was edited after kickoff is scored
on the version that stood at kickoff, restored from the revision the edit preserved. If no such
version survives, the prediction is not scored at all.

Settlement is idempotent. Each score row is keyed one-to-one to the thing it scores (prediction_id,
snapshot_id), so a second run over the same data rewrites nothing and double-counts nothing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.predictions import (
    Match,
    MatchResult,
    MatchStatus,
    Prediction,
    PredictionAudit,
    PredictionOutcome,
    PredictionResult,
    PredictionStatus,
)
from app.models.provider_data import ProviderForecastResult, ProviderForecastSnapshot
from app.models.users import User
from app.services.expert_prediction import REVISION_ACTION
from app.services.forecast_service import choose_snapshots

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- the stored ruleset
#: Bump this when a rule below changes meaning. Every score row carries the version that settled it,
#: so an old score is always readable against the rule that produced it.
RULES_VERSION = "soccer-regulation-time-v1"

MARKET_MATCH_RESULT = "match_result"
MARKET_BTTS = "both_teams_score"
MARKET_OVER_UNDER_25 = "over_under_2_5"
MARKET_OVER_UNDER_35 = "over_under_3_5"
MARKET_CORRECT_SCORE = "correct_score"

OUTCOME_HOME = "home"
OUTCOME_DRAW = "draw"
OUTCOME_AWAY = "away"
THREE_WAY = (OUTCOME_HOME, OUTCOME_DRAW, OUTCOME_AWAY)

#: Per-market outcome vocabulary inside ``market_results``. "not_scored" is the important one: it is
#: neither a win nor a loss, and it never enters a denominator.
WON, LOST, PUSH, VOID, NOT_SCORED = "won", "lost", "push", "void", "not_scored"

SETTLEMENT_BASIS = (
    "Regulation time only: the score after 90 minutes plus stoppage time, as published by the data "
    "provider that supplied the result. Extra time and penalty shoot-outs settle nothing here. A "
    "stored result that is flagged as covering extra time is refused rather than scored."
)

VOID_RULE = (
    "A fixture that was postponed, cancelled or abandoned is VOID for every market. A void is never "
    "a loss, never a win, and never enters a hit rate or a Brier score."
)

UNSUPPLIED_RULE = (
    "A market the source did not publish is not scored at all. It is never counted as a loss and "
    "never read as a zero probability. Both sides of a two-way market must be published: deriving "
    "the missing side would be inventing a number the source never gave."
)

MARKET_RULES: Dict[str, str] = {
    MARKET_MATCH_RESULT: (
        "1X2 on the regulation-time score. Hit test: the single highest of the three published "
        "probabilities is compared with the outcome that occurred. When two or three share the "
        "highest probability there is no single pick, so the hit test does not apply and the "
        "settlement is PUSH; the probabilistic score still applies."
    ),
    MARKET_BTTS: (
        "Both teams to score: YES when both teams scored at least once in regulation time, NO "
        "otherwise. Hit test: the higher of the two published probabilities against what happened."
    ),
    MARKET_OVER_UNDER_25: (
        "Total goals in regulation time against the 2.5 line: OVER at 3 goals or more, UNDER at 2 "
        "or fewer. The line is not a whole number, so a push is impossible."
    ),
    MARKET_OVER_UNDER_35: (
        "Total goals in regulation time against the 3.5 line: OVER at 4 goals or more, UNDER at 3 "
        "or fewer. The line is not a whole number, so a push is impossible."
    ),
    MARKET_CORRECT_SCORE: (
        "The exact regulation-time scoreline. Only scorelines the source listed are candidates; the "
        "source's 'other scorelines' remainder is never treated as a prediction of any particular "
        "score. When the scoreline that occurred was not listed, the source published no "
        "probability for it and none is invented."
    ),
}

PROBABILITY_OF_ACTUAL_RULE = (
    "The probability the source itself published for the outcome that actually occurred. Nothing is "
    "derived, interpolated or renormalised; when the source published nothing for that outcome the "
    "field is null."
)

#: Brier is computed on the published numbers as they stand. Renormalising a set that does not sum
#: to 1 would replace the source's numbers with ours, so a set outside this tolerance is simply not
#: scored probabilistically (the hit test is unaffected: it only compares sizes).
PROB_SUM_TOLERANCE = 0.02

BRIER_DEFINITION = (
    "Brier score, the mean squared error of the published probabilities against what happened: "
    "sum over the outcomes of (published probability - 1 if that outcome occurred else 0) squared. "
    "0 is perfect, lower is better. A three-way market ranges 0 to 2 and an always-1/3 forecast "
    "scores 0.6667; a two-way market ranges 0 to 2 and an always-1/2 forecast scores 0.5. It is "
    "computed only when every side of the market was published and the published values sum to 1 "
    f"within {PROB_SUM_TOLERANCE}, because renormalising would replace the source's numbers."
)

#: What an uninformative forecast scores, so a number below can be read as better than nothing.
BRIER_BASELINES = {
    MARKET_MATCH_RESULT: 0.6667,   # an always-(1/3, 1/3, 1/3) forecast
    MARKET_BTTS: 0.5,              # an always-(1/2, 1/2) forecast
    MARKET_OVER_UNDER_25: 0.5,
    MARKET_OVER_UNDER_35: 0.5,
}

#: An accuracy headline below this many SCORED predictions is refused rather than published.
#: Why 30: at a hit rate near 50% the standard error is 0.5/sqrt(n), so 30 scored predictions still
#: carry a 95% interval of roughly +/- 18 percentage points - a "62% accurate" built on 30 matches
#: is indistinguishable from 44% or 80%. Thirty is also the conventional point where the normal
#: approximation to the binomial becomes usable at all. Below it there is no headline worth showing,
#: so the counts are published and the rate is withheld with its reason.
MINIMUM_SCORED_SAMPLE = 30
MINIMUM_SAMPLE_RATIONALE = (
    f"An accuracy figure is only published once at least {MINIMUM_SCORED_SAMPLE} predictions from "
    "that source have been scored. At a hit rate near 50% the standard error is 0.5/sqrt(n), so a "
    f"rate computed from fewer than {MINIMUM_SCORED_SAMPLE} results carries a 95% interval wider "
    "than +/- 18 percentage points and would mislead. The counts behind it are published either way."
)

HIT_RATE_DEFINITION = (
    "Share of scored predictions whose single most likely published outcome was the outcome that "
    "occurred. Voids, pushes and markets the source did not publish are excluded from both the "
    "numerator and the denominator."
)


def settlement_rules() -> Dict[str, Any]:
    """The complete ruleset, as published next to every figure computed from it."""
    return {
        "version": RULES_VERSION,
        "basis": SETTLEMENT_BASIS,
        "void": VOID_RULE,
        "unsupplied_market": UNSUPPLIED_RULE,
        "prematch_only": (
            "Only evidence that existed before kickoff is scored: a provider forecast snapshot "
            "captured before kickoff, and an expert prediction published before kickoff (on the "
            "version that stood at kickoff if it was edited afterwards)."
        ),
        "markets": dict(MARKET_RULES),
        "probability_of_actual": PROBABILITY_OF_ACTUAL_RULE,
        "brier": BRIER_DEFINITION,
        "brier_baselines": dict(BRIER_BASELINES),
        "hit_rate": HIT_RATE_DEFINITION,
        "minimum_sample": MINIMUM_SCORED_SAMPLE,
        "minimum_sample_rationale": MINIMUM_SAMPLE_RATIONALE,
    }


# --------------------------------------------------------------------------- value objects
@dataclass(frozen=True)
class RegulationScore:
    """The regulation-time scoreline everything below settles against."""
    home: int
    away: int

    @property
    def total(self) -> int:
        return self.home + self.away

    @property
    def outcome(self) -> str:
        if self.home > self.away:
            return OUTCOME_HOME
        if self.home < self.away:
            return OUTCOME_AWAY
        return OUTCOME_DRAW

    @property
    def both_scored(self) -> bool:
        return self.home > 0 and self.away > 0

    @property
    def label(self) -> str:
        return f"{self.home}-{self.away}"


@dataclass
class SourceMarkets:
    """Exactly what one source published for one fixture.

    ``None`` means "not supplied" everywhere in here and is never turned into a number.
    """
    home_win_prob: Optional[float] = None
    draw_prob: Optional[float] = None
    away_win_prob: Optional[float] = None
    btts_yes_prob: Optional[float] = None
    btts_no_prob: Optional[float] = None
    over_25_prob: Optional[float] = None
    under_25_prob: Optional[float] = None
    over_35_prob: Optional[float] = None
    under_35_prob: Optional[float] = None
    exact_score: Optional[Dict[str, Any]] = None


@dataclass
class Settlement:
    """The score of one source view of one fixture."""
    outcome: Optional[PredictionOutcome]
    is_correct: Optional[bool]
    actual_outcome: Optional[str]
    probability_of_actual: Optional[float]
    brier_score: Optional[float]
    markets: List[Dict[str, Any]] = field(default_factory=list)
    void_reason: Optional[str] = None


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _dec(value: Optional[float], places: int) -> Optional[Decimal]:
    return Decimal(str(round(value, places))) if value is not None else None


def _entry(market: str, outcome: str, **extra: Any) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "market": market,
        "outcome": outcome,
        "rule": MARKET_RULES[market],
        "predicted": None,
        "actual": None,
        "probability_of_actual": None,
        "brier_score": None,
        "reason": None,
    }
    entry.update(extra)
    return entry


def _brier(probabilities: Sequence[float], occurred_index: int) -> Optional[float]:
    """Brier score of a complete published distribution, or None when it cannot be computed."""
    if any(p is None for p in probabilities):
        return None
    total = sum(probabilities)
    if abs(total - 1.0) > PROB_SUM_TOLERANCE:
        return None
    return round(sum((p - (1.0 if i == occurred_index else 0.0)) ** 2
                     for i, p in enumerate(probabilities)), 5)


def _score_three_way(markets: SourceMarkets, score: RegulationScore) -> Dict[str, Any]:
    probs = {OUTCOME_HOME: markets.home_win_prob, OUTCOME_DRAW: markets.draw_prob,
             OUTCOME_AWAY: markets.away_win_prob}
    if any(probs[name] is None for name in THREE_WAY):
        return _entry(MARKET_MATCH_RESULT, NOT_SCORED, actual=score.outcome,
                      reason="the source published no complete 1X2 for this fixture")

    actual = score.outcome
    highest = max(probs[name] for name in THREE_WAY)
    leaders = [name for name in THREE_WAY if probs[name] == highest]
    probability_of_actual = probs[actual]
    brier = _brier([probs[name] for name in THREE_WAY], THREE_WAY.index(actual))
    brier_reason = None if brier is not None else (
        "the published probabilities do not sum to 1 within tolerance; renormalising them would "
        "replace the source's numbers with ours")

    if len(leaders) > 1:
        return _entry(MARKET_MATCH_RESULT, PUSH, predicted=None, actual=actual,
                      probability_of_actual=probability_of_actual, brier_score=brier,
                      reason=("no single most likely outcome: " + " and ".join(leaders) +
                              " shared the highest published probability"))
    predicted = leaders[0]
    entry = _entry(MARKET_MATCH_RESULT, WON if predicted == actual else LOST, predicted=predicted,
                   actual=actual, probability_of_actual=probability_of_actual, brier_score=brier)
    if brier_reason:
        entry["reason"] = brier_reason
    return entry


def _score_two_way(market: str, yes_prob: Optional[float], no_prob: Optional[float],
                   yes_label: str, no_label: str, yes_happened: bool) -> Dict[str, Any]:
    actual = yes_label if yes_happened else no_label
    if yes_prob is None and no_prob is None:
        return _entry(market, NOT_SCORED, actual=actual,
                      reason="the source published no probability for this market")
    if yes_prob is None or no_prob is None:
        return _entry(market, NOT_SCORED, actual=actual,
                      reason=("the source published only one side of this market; the other side "
                              "would have to be derived, so it is not scored"))

    probability_of_actual = yes_prob if yes_happened else no_prob
    brier = _brier([yes_prob, no_prob], 0 if yes_happened else 1)
    brier_reason = None if brier is not None else (
        "the published probabilities do not sum to 1 within tolerance; renormalising them would "
        "replace the source's numbers with ours")
    if yes_prob == no_prob:
        return _entry(market, PUSH, actual=actual, probability_of_actual=probability_of_actual,
                      brier_score=brier,
                      reason=f"no single most likely outcome: {yes_label} and {no_label} "
                             "shared the highest published probability")
    predicted = yes_label if yes_prob > no_prob else no_label
    entry = _entry(market, WON if predicted == actual else LOST, predicted=predicted, actual=actual,
                   probability_of_actual=probability_of_actual, brier_score=brier)
    if brier_reason:
        entry["reason"] = brier_reason
    return entry


def _score_correct_score(markets: SourceMarkets, score: RegulationScore) -> Dict[str, Any]:
    listed = markets.exact_score or {}
    listed = {str(k): _float(v) for k, v in listed.items() if _float(v) is not None}
    if not listed:
        return _entry(MARKET_CORRECT_SCORE, NOT_SCORED, actual=score.label,
                      reason="the source listed no scoreline probabilities")
    highest = max(listed.values())
    leaders = sorted(name for name, value in listed.items() if value == highest)
    probability_of_actual = listed.get(score.label)
    if len(leaders) > 1:
        return _entry(MARKET_CORRECT_SCORE, PUSH, actual=score.label,
                      probability_of_actual=probability_of_actual,
                      reason="no single most likely scoreline: " + ", ".join(leaders) +
                             " shared the highest published probability")
    predicted = leaders[0]
    reason = None if probability_of_actual is not None else (
        "the scoreline that occurred was not among the ones the source listed, so it published no "
        "probability for it")
    # No Brier here: the source's scoreline list is incomplete by construction (an "other" bucket
    # holds the rest), so the distribution cannot be enumerated without inventing it.
    return _entry(MARKET_CORRECT_SCORE, WON if predicted == score.label else LOST,
                  predicted=predicted, actual=score.label,
                  probability_of_actual=probability_of_actual, reason=reason)


def score_markets(markets: SourceMarkets, score: RegulationScore) -> Settlement:
    """Score every market the source published against the regulation-time result."""
    entries = [_score_three_way(markets, score)]
    entries.append(_score_two_way(MARKET_BTTS, markets.btts_yes_prob, markets.btts_no_prob,
                                  "yes", "no", score.both_scored))
    entries.append(_score_two_way(MARKET_OVER_UNDER_25, markets.over_25_prob, markets.under_25_prob,
                                  "over", "under", score.total >= 3))
    entries.append(_score_two_way(MARKET_OVER_UNDER_35, markets.over_35_prob, markets.under_35_prob,
                                  "over", "under", score.total >= 4))
    if markets.exact_score:
        entries.append(_score_correct_score(markets, score))

    headline = entries[0]
    outcome_map = {WON: PredictionOutcome.WON, LOST: PredictionOutcome.LOST,
                   PUSH: PredictionOutcome.PUSH}
    return Settlement(
        outcome=outcome_map.get(headline["outcome"]),
        is_correct={WON: True, LOST: False}.get(headline["outcome"]),
        actual_outcome=score.outcome,
        probability_of_actual=headline["probability_of_actual"],
        brier_score=headline["brier_score"],
        markets=entries,
    )


def void_settlement(markets_published: SourceMarkets, reason: str) -> Settlement:
    """Every market of a fixture that was never played to a result."""
    entries = [_entry(name, VOID, reason=reason)
               for name in (MARKET_MATCH_RESULT, MARKET_BTTS, MARKET_OVER_UNDER_25,
                            MARKET_OVER_UNDER_35)]
    if markets_published.exact_score:
        entries.append(_entry(MARKET_CORRECT_SCORE, VOID, reason=reason))
    return Settlement(outcome=PredictionOutcome.VOID, is_correct=None, actual_outcome=None,
                      probability_of_actual=None, brier_score=None, markets=entries,
                      void_reason=reason)


# --------------------------------------------------------------------------- reading the result
_EXTRA_TIME_MARKERS = {"aet", "pen", "et", "after extra time", "after_extra_time", "extra_time",
                       "extra time", "penalties", "pens"}
_EXTRA_TIME_FLAGS = ("after_extra_time", "extra_time", "went_to_extra_time", "penalties",
                     "penalty_shootout")

VOID_STATUSES = {MatchStatus.POSTPONED: "the fixture was postponed",
                 MatchStatus.CANCELLED: "the fixture was cancelled or abandoned"}
TERMINAL_STATUSES = (MatchStatus.FINISHED, MatchStatus.POSTPONED, MatchStatus.CANCELLED)


def regulation_score(result: Optional[MatchResult]) -> Tuple[Optional[RegulationScore], Optional[str]]:
    """The regulation-time score of a finished match, or the reason it cannot be read."""
    if result is None or result.home_score is None or result.away_score is None:
        return None, "the match is marked finished but no score is stored"
    meta = result.result_metadata or {}
    for key in ("period", "status", "time_status", "stage"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip().lower() in _EXTRA_TIME_MARKERS:
            return None, ("the stored score covers extra time or penalties; these markets settle on "
                          "regulation time only")
    for key in _EXTRA_TIME_FLAGS:
        if meta.get(key):
            return None, ("the stored result is flagged as going beyond regulation time; these "
                          "markets settle on regulation time only")
    return RegulationScore(int(result.home_score), int(result.away_score)), None


# --------------------------------------------------------------------------- source views
def markets_from_prediction_row(prediction: Prediction) -> SourceMarkets:
    return SourceMarkets(
        home_win_prob=_float(prediction.home_win_prob),
        draw_prob=_float(prediction.draw_prob),
        away_win_prob=_float(prediction.away_win_prob),
        btts_yes_prob=_float(prediction.btts_yes_prob),
        btts_no_prob=_float(prediction.btts_no_prob),
        over_25_prob=_float(prediction.total_goals_over_25_prob),
        under_25_prob=_float(prediction.total_goals_under_25_prob),
        over_35_prob=_float(prediction.total_goals_over_35_prob),
        under_35_prob=_float(prediction.total_goals_under_35_prob),
    )


def markets_from_revision(values: Dict[str, Any]) -> SourceMarkets:
    """The markets of a preserved earlier version of an expert prediction."""
    return SourceMarkets(
        home_win_prob=_float(values.get("home_win_prob")),
        draw_prob=_float(values.get("draw_prob")),
        away_win_prob=_float(values.get("away_win_prob")),
        btts_yes_prob=_float(values.get("btts_yes_prob")),
        btts_no_prob=_float(values.get("btts_no_prob")),
        over_25_prob=_float(values.get("total_goals_over_25_prob")),
        under_25_prob=_float(values.get("total_goals_under_25_prob")),
        over_35_prob=_float(values.get("total_goals_over_35_prob")),
        under_35_prob=_float(values.get("total_goals_under_35_prob")),
    )


def markets_from_snapshot(snapshot: ProviderForecastSnapshot) -> SourceMarkets:
    return SourceMarkets(
        home_win_prob=_float(snapshot.home_win_prob),
        draw_prob=_float(snapshot.draw_prob),
        away_win_prob=_float(snapshot.away_win_prob),
        btts_yes_prob=_float(snapshot.btts_yes_prob),
        btts_no_prob=_float(snapshot.btts_no_prob),
        over_25_prob=_float(snapshot.total_goals_over_25_prob),
        under_25_prob=_float(snapshot.total_goals_under_25_prob),
        over_35_prob=_float(snapshot.total_goals_over_35_prob),
        under_35_prob=_float(snapshot.total_goals_under_35_prob),
        exact_score=snapshot.exact_score if isinstance(snapshot.exact_score, dict) else None,
    )


# --------------------------------------------------------------------------- candidate selection
def eligible_matches(db: Session, start: Optional[datetime] = None,
                     end: Optional[datetime] = None) -> List[Match]:
    """Matches that reached a terminal state inside the window (kickoff time, naive UTC)."""
    query = db.query(Match).filter(Match.status.in_(TERMINAL_STATUSES))
    if start is not None:
        query = query.filter(Match.match_date >= start)
    if end is not None:
        query = query.filter(Match.match_date < end)
    return query.order_by(Match.match_date.asc()).all()


def candidate_predictions(db: Session, match_ids: Sequence[uuid.UUID]) -> List[Prediction]:
    """Published, live expert predictions for those matches.

    Soft-deleted and superseded rows are excluded: a withdrawn prediction is not a record of what
    the expert told readers, and a superseded one is represented by the row that replaced it.
    """
    if not match_ids:
        return []
    return (db.query(Prediction)
            .filter(Prediction.match_id.in_(list(match_ids)),
                    Prediction.status == PredictionStatus.PUBLISHED,
                    Prediction.deleted_at.is_(None),
                    Prediction.superseded_by.is_(None))
            .order_by(Prediction.created_at.asc())
            .all())


def prematch_snapshots(db: Session, match_ids: Sequence[uuid.UUID]
                       ) -> Dict[Tuple[uuid.UUID, str], ProviderForecastSnapshot]:
    """The last snapshot captured BEFORE kickoff, per match and provider.

    The last one is the model's final prematch word, which is what a reader saw on the match page
    when the match started. Snapshots captured after kickoff, and snapshots captured when the
    kickoff was not yet known (``captured_before_kickoff IS NULL``), are not prematch evidence and
    are never returned here.

    This function decides nothing on its own: the filter is settlement's (prematch only), the pick
    is :func:`app.services.forecast_service.choose_snapshots`, which every reader of this table
    goes through. Scoring and the performance read call this same function, so they cannot end up
    on two different snapshots of one forecast - which, while the ordering was only
    ``first_fetched_at`` and several snapshots share that timestamp, is precisely what happened:
    settlement scored one twin and /performance/sources reported the other as still pending.
    """
    if not match_ids:
        return {}
    return choose_snapshots(
        db.query(ProviderForecastSnapshot)
        .filter(ProviderForecastSnapshot.match_id.in_(list(match_ids)),
                ProviderForecastSnapshot.captured_before_kickoff.is_(True)))


def snapshot_providers(db: Session, match_ids: Sequence[uuid.UUID]
                       ) -> Dict[Tuple[uuid.UUID, str], int]:
    """Every (match, provider) that has any snapshot at all, prematch or not, with the count."""
    if not match_ids:
        return {}
    counts: Dict[Tuple[uuid.UUID, str], int] = {}
    for match_id, provider in (db.query(ProviderForecastSnapshot.match_id,
                                        ProviderForecastSnapshot.provider)
                               .filter(ProviderForecastSnapshot.match_id.in_(list(match_ids)))
                               .all()):
        counts[(match_id, provider)] = counts.get((match_id, provider), 0) + 1
    return counts


def prematch_expert_view(prediction: Prediction, revisions: Sequence[PredictionAudit],
                         kickoff: datetime) -> Tuple[Optional[SourceMarkets], Optional[str], str]:
    """The version of an expert prediction that stood at kickoff.

    Returns (markets, refusal reason, provenance). A prediction edited after kickoff is scored on
    the version the edit preserved, never on the values that replaced it.
    """
    if prediction.published_at is None:
        return None, "the prediction has no publication time, so it cannot be shown to predate kickoff", ""
    if prediction.published_at >= kickoff:
        return None, "published at or after kickoff", ""

    later = [r for r in revisions if r.created_at is not None and r.created_at >= kickoff]
    if not later:
        return markets_from_prediction_row(prediction), None, "as published"
    values = later[0].old_values or {}
    if not values:
        return (None,
                "edited after kickoff and the version that stood at kickoff was not preserved", "")
    return (markets_from_revision(values), None,
            f"restored from revision {later[0].id}, which preserved the version edited after kickoff")


# --------------------------------------------------------------------------- the service
class SettlementService:
    """Writes a score for every prediction and prematch forecast whose match has a real outcome."""

    def __init__(self, db: Session, now: Optional[datetime] = None):
        self.db = db
        self.now = now or datetime.now(timezone.utc)

    # -- writing ------------------------------------------------------------
    def _naive_now(self) -> datetime:
        return self.now.replace(tzinfo=None) if self.now.tzinfo else self.now

    def _apply(self, row: Any, settlement: Settlement, match_result_id: Optional[uuid.UUID]) -> bool:
        """Copy a settlement onto a score row. Returns True when anything actually changed."""
        payload = {
            "match_result_id": match_result_id,
            "outcome": settlement.outcome,
            "is_correct": settlement.is_correct,
            "actual_outcome": settlement.actual_outcome,
            "probability_of_actual": _dec(settlement.probability_of_actual, 4),
            "brier_score": _dec(settlement.brier_score, 5),
            "market_results": settlement.markets,
            "void_reason": settlement.void_reason,
            "rules_version": RULES_VERSION,
        }
        changed = False
        for name, value in payload.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
        if changed:
            row.settled_at = self._naive_now()
            row.settled_by_system = True
        return changed

    def _settle_predictions(self, match: Match, score: Optional[RegulationScore],
                            void_reason: Optional[str], report: Dict[str, Any]) -> None:
        predictions = candidate_predictions(self.db, [match.id])
        if not predictions:
            return
        ids = [p.id for p in predictions]
        revisions: Dict[uuid.UUID, List[PredictionAudit]] = {}
        for row in (self.db.query(PredictionAudit)
                    .filter(PredictionAudit.prediction_id.in_(ids),
                            PredictionAudit.action == REVISION_ACTION)
                    .order_by(PredictionAudit.created_at.asc(), PredictionAudit.id.asc())
                    .all()):
            revisions.setdefault(row.prediction_id, []).append(row)

        existing = {r.prediction_id: r for r in
                    self.db.query(PredictionResult).filter(PredictionResult.prediction_id.in_(ids)).all()}

        for prediction in predictions:
            markets, refusal, provenance = prematch_expert_view(
                prediction, revisions.get(prediction.id, []), match.match_date)
            if markets is None:
                report["expert_predictions"]["not_scored"] += 1
                report["not_scored"].append({"kind": "expert_prediction", "id": str(prediction.id),
                                             "reason": refusal})
                continue
            settlement = (void_settlement(markets, void_reason) if void_reason
                          else score_markets(markets, score))
            settlement.markets = [dict(entry, evidence=provenance) for entry in settlement.markets]

            row = existing.get(prediction.id)
            if row is None:
                row = PredictionResult(id=uuid.uuid4(), prediction_id=prediction.id,
                                       settled_at=self._naive_now(), settled_by_system=True,
                                       rules_version=RULES_VERSION,
                                       outcome=PredictionOutcome.PENDING)
                self.db.add(row)
                self._apply(row, settlement, match.result.id if match.result else None)
                report["expert_predictions"]["settled"] += 1
            elif self._apply(row, settlement, match.result.id if match.result else None):
                report["expert_predictions"]["updated"] += 1
            else:
                report["expert_predictions"]["unchanged"] += 1
            if settlement.outcome == PredictionOutcome.VOID:
                report["expert_predictions"]["void"] += 1

    def _settle_forecasts(self, match: Match, score: Optional[RegulationScore],
                          void_reason: Optional[str], report: Dict[str, Any]) -> None:
        chosen = prematch_snapshots(self.db, [match.id])
        all_providers = snapshot_providers(self.db, [match.id])
        for (match_id, provider) in sorted(all_providers, key=lambda key: key[1]):
            if (match_id, provider) not in chosen:
                report["provider_forecasts"]["not_scored"] += 1
                report["not_scored"].append({
                    "kind": "provider_forecast", "id": f"{provider}:{match_id}",
                    "reason": ("no snapshot of this forecast was captured before kickoff, so there "
                               "is no prematch evidence to score")})

        if not chosen:
            return
        snapshot_ids = [snapshot.id for snapshot in chosen.values()]
        existing = {r.snapshot_id: r for r in
                    self.db.query(ProviderForecastResult)
                    .filter(ProviderForecastResult.snapshot_id.in_(snapshot_ids)).all()}

        for snapshot in chosen.values():
            markets = markets_from_snapshot(snapshot)
            settlement = (void_settlement(markets, void_reason) if void_reason
                          else score_markets(markets, score))
            row = existing.get(snapshot.id)
            if row is None:
                row = ProviderForecastResult(id=uuid.uuid4(), snapshot_id=snapshot.id,
                                             match_id=match.id, provider=snapshot.provider,
                                             settled_at=self._naive_now(), settled_by_system=True,
                                             rules_version=RULES_VERSION,
                                             snapshot_captured_at=snapshot.first_fetched_at,
                                             kickoff_at=match.match_date)
                self.db.add(row)
                self._apply(row, settlement, match.result.id if match.result else None)
                report["provider_forecasts"]["settled"] += 1
            else:
                row.snapshot_captured_at = snapshot.first_fetched_at
                row.kickoff_at = match.match_date
                if self._apply(row, settlement, match.result.id if match.result else None):
                    report["provider_forecasts"]["updated"] += 1
                else:
                    report["provider_forecasts"]["unchanged"] += 1
            if settlement.outcome == PredictionOutcome.VOID:
                report["provider_forecasts"]["void"] += 1

    def settle_match(self, match: Match, report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Score everything attached to one match. Idempotent: a second call writes nothing."""
        report = report if report is not None else _empty_report()
        void_reason = VOID_STATUSES.get(match.status)
        score: Optional[RegulationScore] = None
        if void_reason is None:
            if match.status != MatchStatus.FINISHED:
                report["skipped_matches"].append({"match_id": str(match.id),
                                                  "reason": "the match has no terminal status yet"})
                return report
            score, refusal = regulation_score(match.result)
            if score is None:
                report["skipped_matches"].append({"match_id": str(match.id), "reason": refusal})
                return report
        report["matches_settled"] += 1
        self._settle_predictions(match, score, void_reason, report)
        self._settle_forecasts(match, score, void_reason, report)
        return report

    def settle_range(self, start: Optional[datetime] = None, end: Optional[datetime] = None,
                     limit: Optional[int] = None, commit: bool = True) -> Dict[str, Any]:
        """Score every terminal match in the window. Safe and cheap to re-run."""
        matches = eligible_matches(self.db, start, end)
        if limit is not None:
            matches = matches[:limit]
        report = _empty_report()
        report["matches_considered"] = len(matches)
        for match in matches:
            self.settle_match(match, report)
        self.db.flush()
        if commit:
            self.db.commit()
        logger.info("settlement %s: %d match(es) considered, expert %s, provider %s",
                    RULES_VERSION, report["matches_considered"],
                    report["expert_predictions"], report["provider_forecasts"])
        return report


def _empty_report() -> Dict[str, Any]:
    counters = {"settled": 0, "updated": 0, "unchanged": 0, "void": 0, "not_scored": 0}
    return {
        "rules_version": RULES_VERSION,
        "matches_considered": 0,
        "matches_settled": 0,
        "expert_predictions": dict(counters),
        "provider_forecasts": dict(counters),
        "skipped_matches": [],
        "not_scored": [],
    }


# --------------------------------------------------------------------------- measurement
def _market_bucket() -> Dict[str, Any]:
    return {"scored": 0, "hits": 0, "pushes": 0, "voids": 0, "not_scored": 0,
            "brier_values": [], "probability_of_actual_values": []}


def _finish_market(market: str, bucket: Dict[str, Any]) -> Dict[str, Any]:
    scored = bucket["scored"]
    brier_values = bucket.pop("brier_values")
    probabilities = bucket.pop("probability_of_actual_values")
    payload: Dict[str, Any] = {
        "market": market,
        "rule": MARKET_RULES[market],
        "scored": scored,
        "hits": bucket["hits"],
        "pushes": bucket["pushes"],
        "voids": bucket["voids"],
        "not_scored": bucket["not_scored"],
        "hit_rate_definition": HIT_RATE_DEFINITION,
        "brier_definition": BRIER_DEFINITION,
        "brier_baseline": BRIER_BASELINES.get(market),
        "brier_sample": len(brier_values),
    }
    if scored >= MINIMUM_SCORED_SAMPLE:
        payload["hit_rate"] = round(bucket["hits"] / scored, 4)
        payload["hit_rate_available"] = True
        payload["hit_rate_unavailable_reason"] = None
        payload["hit_rate_sample"] = scored
    else:
        payload["hit_rate"] = None
        payload["hit_rate_available"] = False
        payload["hit_rate_sample"] = scored
        payload["hit_rate_unavailable_reason"] = (
            f"{scored} scored prediction(s) is below the minimum of {MINIMUM_SCORED_SAMPLE}. "
            + MINIMUM_SAMPLE_RATIONALE)
    if len(brier_values) >= MINIMUM_SCORED_SAMPLE:
        payload["brier_score"] = round(sum(brier_values) / len(brier_values), 5)
        payload["brier_available"] = True
        payload["brier_unavailable_reason"] = None
    else:
        payload["brier_score"] = None
        payload["brier_available"] = False
        payload["brier_unavailable_reason"] = (
            f"{len(brier_values)} prediction(s) carry a computable Brier score, below the minimum "
            f"of {MINIMUM_SCORED_SAMPLE}. " + MINIMUM_SAMPLE_RATIONALE)
    payload["mean_probability_of_actual"] = (
        round(sum(probabilities) / len(probabilities), 4) if probabilities else None)
    payload["mean_probability_of_actual_definition"] = PROBABILITY_OF_ACTUAL_RULE
    payload["mean_probability_of_actual_sample"] = len(probabilities)
    return payload


class _SourceAccumulator:
    def __init__(self, source_type: str, source_id: str, label: str):
        self.source_type = source_type
        self.source_id = source_id
        self.label = label
        self.eligible = 0
        self.scored = 0
        self.pending = 0
        self.void = 0
        self.not_scored = 0
        self.not_scored_reasons: Dict[str, int] = {}
        self.markets: Dict[str, Dict[str, Any]] = {}

    def refuse(self, reason: str) -> None:
        self.eligible += 1
        self.not_scored += 1
        self.not_scored_reasons[reason] = self.not_scored_reasons.get(reason, 0) + 1

    def add_pending(self) -> None:
        self.eligible += 1
        self.pending += 1

    def add_result(self, outcome: Optional[str], market_results: Optional[List[Dict[str, Any]]]) -> None:
        self.eligible += 1
        if outcome == PredictionOutcome.VOID.value:
            self.void += 1
        else:
            self.scored += 1
        for entry in market_results or []:
            market = entry.get("market")
            if market not in MARKET_RULES:
                continue
            bucket = self.markets.setdefault(market, _market_bucket())
            state = entry.get("outcome")
            if state in (WON, LOST):
                bucket["scored"] += 1
                if state == WON:
                    bucket["hits"] += 1
            elif state == PUSH:
                bucket["pushes"] += 1
            elif state == VOID:
                bucket["voids"] += 1
            else:
                bucket["not_scored"] += 1
                continue
            if entry.get("brier_score") is not None:
                bucket["brier_values"].append(float(entry["brier_score"]))
            if entry.get("probability_of_actual") is not None:
                bucket["probability_of_actual_values"].append(float(entry["probability_of_actual"]))

    def payload(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_label": self.label,
            "eligible": self.eligible,
            "scored": self.scored,
            "pending": self.pending,
            "void": self.void,
            "not_scored": self.not_scored,
            "not_scored_reasons": [{"reason": reason, "count": count}
                                   for reason, count in sorted(self.not_scored_reasons.items())],
            "markets": [_finish_market(name, bucket) for name, bucket in sorted(self.markets.items())],
        }
        if self.scored:
            data["measured"] = True
            data["not_measured_reason"] = None
            return data
        data["measured"] = False
        if self.eligible == 0:
            data["not_measured_reason"] = "this source has nothing eligible for scoring in this window"
        elif self.void and not self.pending and not self.not_scored:
            data["not_measured_reason"] = ("every eligible prediction from this source was voided: "
                                           "those fixtures were never played to a result")
        else:
            data["not_measured_reason"] = "nothing from this source has been scored in this window yet"
        return data


def measure_sources(db: Session, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Per-source measured performance over a window of kickoffs. Every figure is counted, never estimated."""
    matches = eligible_matches(db, start, end)
    if not matches:
        return []
    match_ids = [m.id for m in matches]
    by_id = {m.id: m for m in matches}
    accumulators: Dict[Tuple[str, str], _SourceAccumulator] = {}

    def bucket(source_type: str, source_id: str, label: str) -> _SourceAccumulator:
        key = (source_type, source_id)
        if key not in accumulators:
            accumulators[key] = _SourceAccumulator(source_type, source_id, label)
        return accumulators[key]

    # ---- experts
    predictions = candidate_predictions(db, match_ids)
    if predictions:
        prediction_ids = [p.id for p in predictions]
        results = {r.prediction_id: r for r in
                   db.query(PredictionResult).filter(PredictionResult.prediction_id.in_(prediction_ids)).all()}
        user_ids = {p.created_by for p in predictions}
        names = {u.id: (u.username or u.email) for u in
                 db.query(User).filter(User.id.in_(list(user_ids))).all()}
        for prediction in predictions:
            acc = bucket("expert", str(prediction.created_by),
                         names.get(prediction.created_by, "unknown expert"))
            row = results.get(prediction.id)
            if row is not None:
                acc.add_result(row.outcome.value if row.outcome else None, row.market_results)
                continue
            kickoff = by_id[prediction.match_id].match_date
            if prediction.published_at is None or prediction.published_at >= kickoff:
                acc.refuse("published at or after kickoff, so it is not prematch evidence")
            else:
                acc.add_pending()

    # ---- model providers
    chosen = prematch_snapshots(db, match_ids)
    all_providers = snapshot_providers(db, match_ids)
    if all_providers:
        snapshot_ids = [s.id for s in chosen.values()]
        results = {r.snapshot_id: r for r in
                   db.query(ProviderForecastResult)
                   .filter(ProviderForecastResult.snapshot_id.in_(snapshot_ids)).all()} if snapshot_ids else {}
        for (match_id, provider) in all_providers:
            acc = bucket("model_provider", provider, provider)
            snapshot = chosen.get((match_id, provider))
            if snapshot is None:
                acc.refuse("no snapshot of this forecast was captured before kickoff")
                continue
            row = results.get(snapshot.id)
            if row is None:
                acc.add_pending()
            else:
                acc.add_result(row.outcome.value if row.outcome else None, row.market_results)

    return [acc.payload() for acc in
            sorted(accumulators.values(), key=lambda a: (a.source_type, a.label))]


DEFAULT_WINDOW_DAYS = 90
MAX_WINDOW_DAYS = 366


def window_bounds(start: Optional[date], end: Optional[date],
                  now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Half-open [start, end) window of kickoff times, naive UTC, from optional calendar dates."""
    today = (now or datetime.now(timezone.utc)).date()
    end_date = end or today
    start_date = start or (end_date - timedelta(days=DEFAULT_WINDOW_DAYS))
    return (datetime.combine(start_date, time.min),
            datetime.combine(end_date, time.min) + timedelta(days=1))


def measurement(db: Session, start: Optional[date] = None, end: Optional[date] = None,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """The full measured-performance payload, rules included."""
    moment = now or datetime.now(timezone.utc)
    start_dt, end_dt = window_bounds(start, end, moment)
    sources = measure_sources(db, start_dt, end_dt)
    return {
        "window": {
            "start": start_dt.date().isoformat(),
            "end": (end_dt - timedelta(days=1)).date().isoformat(),
            "basis": "kickoff date in UTC, both ends included",
        },
        "minimum_sample": MINIMUM_SCORED_SAMPLE,
        "minimum_sample_rationale": MINIMUM_SAMPLE_RATIONALE,
        "rules": settlement_rules(),
        "sources": sources,
        "sources_measured": sum(1 for s in sources if s["measured"]),
        "not_measured_reason": (None if sources else
                                "no match in this window has reached a terminal status yet, so "
                                "there is nothing to score"),
        "measured_at": moment.isoformat(),
    }


def iter_market_entries(rows: Iterable[Any]) -> Iterable[Dict[str, Any]]:
    """Flatten the stored per-market detail of a set of score rows (used by tests and reports)."""
    for row in rows:
        for entry in row.market_results or []:
            yield entry
