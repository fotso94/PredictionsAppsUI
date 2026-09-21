"""
Prediction Schemas
Pydantic models for prediction-related API requests and responses
"""

from pydantic import BaseModel, Field, field_serializer, model_validator, validator
from typing import List, Optional, Dict, Any, Tuple, TypeVar
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.schemas.matches import iso_utc


#: Serialise a datetime as UTC ISO-8601 with a trailing Z. Stored timestamps are naive UTC, and a
#: value serialised without an offset is parsed by the browser as LOCAL time, which can move a
#: kickoff to the wrong day on the expert pages. One implementation, shared with the match payloads.
to_utc_iso_z = iso_utc


# --------------------------------------------------------------------- complementary market pairs
#
# THE RULE: A COMPLEMENTARY PAIR IS PUBLISHED TOGETHER OR WITHDRAWN TOGETHER.
#
# Each of these markets is one statement about a match - "both teams score, or they do not" - split
# across two columns. Half of it is not a smaller claim, it is an incoherent one. A row holding
# btts_yes_prob NULL beside btts_no_prob 0.4000 makes app/services/match_brief.py report the market
# at 40% in the same breath as naming the other side unpublished: both sentences true, the pair of
# them a description of something the expert never did.
#
# It is enforced here, on the request, and not left to the database. The CHECK on
# predictions.predictions does not reject a half pair and never did - see the comment on
# ck_predictions_btts_prob_sum in app/models/predictions.py for why, and why the table is not the
# place for this rule. A 422 that names the other half is also an answer the expert can act on,
# which a constraint name is not.
#
#: The pairs, as (first side, second side, the market's name in a sentence), with the two sides in
#: the order the sum validators below add them.
COMPLEMENTARY_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("btts_yes_prob", "btts_no_prob", "both teams to score"),
    ("total_goals_over_25_prob", "total_goals_under_25_prob", "over/under 2.5 goals"),
    ("total_goals_over_35_prob", "total_goals_under_35_prob", "over/under 3.5 goals"),
)

_Model = TypeVar("_Model", bound=BaseModel)


def _pairs_are_whole(model: _Model) -> _Model:
    """Refuse a body that states one side of a complementary market and not the other.

    For a body that describes a record in full - a create or an override, each of which writes a
    new row - an absent key and an explicit null both mean "no view offered", so the rule is about
    values alone: a side carrying a number needs the other side to carry one too.
    """
    for first, second, market in COMPLEMENTARY_PAIRS:
        first_given = getattr(model, first) is not None
        if first_given == (getattr(model, second) is not None):
            continue
        given, missing = (first, second) if first_given else (second, first)
        raise ValueError(
            f"{market} is a complementary pair and has to be published whole: {given} was "
            f"supplied without {missing}. Send both sides, or neither."
        )
    return model


def _pair_edits_move_together(model: _Model) -> _Model:
    """Refuse an edit that publishes, revalues or withdraws one side of a pair on its own.

    An edit is a partial body, so here the rule is about which KEYS the request carried as well as
    about their values. ExpertPredictionService.update_prediction_with_revision reads an absent key
    as "leave the stored value alone" and a key carrying null as "withdraw it", which makes three
    different bodies incoherent. The stored row is not visible from a schema, so all three are
    refused on the body alone:

        {"btts_yes_prob": null}                       withdraws one side, leaves the other standing
        {"btts_yes_prob": 0.7}                        moves one side alone: against a stored other
                                                      side the pair stops summing to 1, and against
                                                      a stored NULL it half-publishes the market
        {"btts_yes_prob": null, "btts_no_prob": 0.4}  states the two halves as if they were separate

    Naming both sides in any edit that touches the market is the single rule that covers all three,
    and it is what frontend/src/components/expert/composer.ts sends for every optional field.
    """
    supplied = model.model_fields_set
    for first, second, market in COMPLEMENTARY_PAIRS:
        in_first, in_second = first in supplied, second in supplied
        if in_first != in_second:
            named, other = (first, second) if in_first else (second, first)
            raise ValueError(
                f"{market} is a complementary pair: this edit sends {named} without {other}. "
                f"Send both sides - two numbers to publish the market, two nulls to withdraw it."
            )
        if not in_first:
            continue
        first_cleared = getattr(model, first) is None
        if first_cleared != (getattr(model, second) is None):
            cleared, kept = (first, second) if first_cleared else (second, first)
            raise ValueError(
                f"{market} is a complementary pair: this edit clears {cleared} but leaves {kept} "
                f"standing. Send both sides as null to withdraw the market."
            )
    return model


# ------------------------------------------------------- a conviction belongs to its own market
#
# THE RULE: WITHDRAWING A MARKET WITHDRAWS ITS CONVICTION, AND A CONVICTION MAY NOT BE SUPPLIED
# FOR A MARKET WITH NO OUTCOMES.
#
# btts_confidence and total_goals_confidence are not probabilities. Each is the expert's stated
# conviction IN one of the markets above - a claim about those outcomes, which cannot outlive
# them. The pair rule keeps a market's two sides together and stops there, and on its own it lets
# the conviction come apart from the market it describes: one body carrying btts_yes_prob null,
# btts_no_prob null and btts_confidence 0.9 withdraws the BTTS market whole while RAISING the
# expert's stated conviction in it to 90%, and the row that results holds a conviction about
# nothing. So the conviction is treated as part of its market here, in the same place and on the
# same terms as the two sides of a pair.
#
# The two goal lines share one conviction column, so total_goals_confidence is a conviction in
# whichever of the four goal-line columns carry numbers, and is orphaned only when none do.
#
# confidence_score needs no rule of its own: it is the conviction in the match result, whose three
# probabilities are required on every one of these bodies, so it always has outcomes to be about.
#
#: Each conviction column, with every probability column it can be a conviction about and the
#: market's name in a sentence.
MARKET_CONVICTIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("btts_confidence", ("btts_yes_prob", "btts_no_prob"), "both teams to score"),
    ("total_goals_confidence",
     ("total_goals_over_25_prob", "total_goals_under_25_prob",
      "total_goals_over_35_prob", "total_goals_under_35_prob"),
     "total goals"),
)


def _convictions_have_a_market(model: _Model) -> _Model:
    """Refuse a body that states a conviction in a market it publishes no outcome for.

    For a create or an override - each of which writes a whole new row - the body is the whole
    record, so the question is answerable from values alone.
    """
    for conviction, outcomes, market in MARKET_CONVICTIONS:
        if getattr(model, conviction) is None:
            continue
        if any(getattr(model, field) is not None for field in outcomes):
            continue
        raise ValueError(
            f"{conviction} states a conviction in {market}, but this prediction publishes no "
            f"{market} probability for it to be about. Publish the market, or leave "
            f"{conviction} out."
        )
    return model


def _conviction_edits_move_with_the_market(model: _Model) -> _Model:
    """Refuse an edit that would leave a conviction standing over a market with no outcomes.

    An edit is a partial body, so - exactly as for the pairs - the rule is about which KEYS the
    request carried as well as their values: an absent key leaves the stored value alone, and a
    key carrying null withdraws it. The stored row is not visible from a schema, so every case
    that cannot be judged from the body is refused rather than guessed at:

        {..._prob: null, ..._prob: null}                 withdraws the market and says nothing
                                                         about the conviction, which would then
                                                         stand over no outcomes
        {..._prob: null, ..._prob: null, ..._conf: 0.9}  withdraws the market and raises the
                                                         conviction in it
        {..._conf: 0.9}                                  a conviction with no market named beside
                                                         it; whether it has outcomes to be about
                                                         is not something this body says

    Clearing the conviction alone - the conviction key null, no probability key named - is not
    refused: withdrawing a claim about a market that stays published is a coherent thing for an
    expert to do, and the editor offers it. An edit that sends the conviction as null can never
    orphan it, whatever it does to the probabilities, so it is never the body this refuses.
    """
    supplied = model.model_fields_set
    for conviction, outcomes, market in MARKET_CONVICTIONS:
        named = [field for field in outcomes if field in supplied]
        if any(getattr(model, field) is not None for field in named):
            continue  # the market keeps outcomes in this body, so the conviction has a subject
        if conviction in supplied and getattr(model, conviction) is None:
            continue  # the conviction is withdrawn here, so nothing of it is left to be orphaned
        if not named:
            if conviction in supplied:
                raise ValueError(
                    f"this edit sets {conviction} without naming any {market} probability, so "
                    f"nothing in it says the conviction has a market to be about. Send the "
                    f"market's probabilities with it, or send {conviction} as null to withdraw "
                    f"the conviction on its own."
                )
            continue  # this edit says nothing about the market or its conviction
        if len(named) != len(outcomes):
            raise ValueError(
                f"this edit withdraws part of {market} and says nothing about the rest, so "
                f"whether {conviction} still has a market to be about cannot be told from it. "
                f"Send every {market} probability ({', '.join(outcomes)}), or send "
                f"{conviction} as null."
            )
        raise ValueError(
            f"this edit withdraws {market}, so {conviction} has to go with it: a conviction is a "
            f"claim about a market's outcomes and cannot outlive them. Send {conviction} as null."
        )
    return model


# ------------------------------------------------ what the probability columns will actually hold
#
# THE RULE: A VALIDATOR THAT DISAGREES WITH A CONSTRAINT IS NOT A VALIDATOR, IT IS A 500.
#
# Every sum rule below is measured on the numbers predictions.predictions will HOLD, never on the
# floats the request carried. Those columns are NUMERIC(5, 4): Postgres rounds each value to four
# decimal places, half away from zero, and the CHECK constraints then add the ROUNDED values. A
# validator that adds the request's doubles is measuring different numbers, and the strip where
# the two disagree is not leniency - it is a correctable mistake turned into a failed write.
#
# The strip opens where a value carries more precision than the column keeps, because that is
# where the rounding moves it. btts_yes_prob 0.98995 with btts_no_prob 0.02005 shows it: the two
# doubles sum to exactly 1.01 and satisfy a 0.99 <= total <= 1.01 test, while the stored values
# are 0.9900 and 0.0201, which sum to 1.0101 and make ck_predictions_btts_prob_sum FALSE. Measured
# against the isolated QA database on 2026-09-21: `select 0.98995::numeric(5,4) +
# 0.02005::numeric(5,4)` returns 1.0101, and `between 0.99 and 1.01` on that total returns false.
#
# So every rule here quantises through as_stored before it compares, and the three complementary
# markets go through one function so they cannot drift apart from each other.
#
#: The scale of the probability columns on predictions.predictions: NUMERIC(5, 4).
_STORED_SCALE = Decimal("0.0001")

#: The window ck_predictions_btts_prob_sum accepts, as the table measures it: BETWEEN 0.99 AND
#: 1.01, applied to the sum of the two STORED values. The over/under pairs carry no sum constraint
#: of their own - see the comment on ck_predictions_btts_prob_sum in app/models/predictions.py -
#: so for them the request is the only place the arithmetic is checked, and they are held to the
#: same window to keep one rule over all three markets.
_PAIR_MIN = Decimal("0.99")
_PAIR_MAX = Decimal("1.01")


def as_stored(value: float) -> Decimal:
    """One probability as the column will hold it.

    ``Decimal(str(value))`` reads the decimal the request meant rather than the binary expansion
    of the double, and the quantise repeats what Postgres does to it on the way into
    NUMERIC(5, 4).
    """
    return Decimal(str(value)).quantize(_STORED_SCALE, rounding=ROUND_HALF_UP)


def outcome_probabilities_sum_to_one(home: float, draw: float, away: float) -> None:
    """Refuse a match-outcome triple that the table would refuse.

    EXACTLY 1, measured at the stored scale, because that is what the table says:
    ck_predictions_prob_sum is ``(home_win_prob + draw_prob + away_win_prob) = 1.0``, an equality
    with no tolerance in it. A tolerance here would accept 34 / 33 / 34, which the insert then
    refuses - the write is lost, and the endpoint cannot tell the expert which of their numbers
    to change, because it cannot identify the constraint without parsing the driver's message and
    may not put that message in front of a caller. Refused here, the reply names the three values
    and their total.

    The request is the side that holds the tighter rule, not the constraint, and the direction
    matters. Every row in the table sums to exactly 1, and the reader side treats the three as a
    distribution - app/services/match_brief.py renders each as a percentage and never rescales -
    so a stored 0.34 / 0.33 / 0.34 would be shown as 34% and 33% and 34%. Widening the CHECK would
    make that storable and weaken what a stored row means; refusing it on the request costs
    nothing, is satisfied by every row already there, and tells the expert which numbers to fix.

    Exactness is measured at NUMERIC(5, 4), not on the floats as sent. Comparing floats against
    1.0 would refuse 0.1 / 0.2 / 0.7 - 1.0000000000000002 in binary floating point, exactly
    1.0000 in the column - and would accept 0.333333 three times, which is 0.999999 as a float,
    0.9999 in the column, and a CheckViolation on the way in.
    """
    home_stored, draw_stored, away_stored = as_stored(home), as_stored(draw), as_stored(away)
    total = home_stored + draw_stored + away_stored
    if total != 1:
        raise ValueError(
            f"Match outcome probabilities must sum to exactly 1. As stored, "
            f"{home_stored} + {draw_stored} + {away_stored} = {total}."
        )


def _pairs_sum_to_one(model: _Model) -> _Model:
    """Refuse a complementary pair whose two stored values fall outside the table's window.

    One side without the other is not this rule's business: _pairs_are_whole and
    _pair_edits_move_together answer that case, and they name the missing half.

    The reply carries both values as the columns would hold them, so a total that only goes wrong
    at the fourth decimal - the case a float comparison gets wrong - is visible in the message
    rather than implied by it.
    """
    for first, second, market in COMPLEMENTARY_PAIRS:
        first_value, second_value = getattr(model, first), getattr(model, second)
        if first_value is None or second_value is None:
            continue
        first_stored, second_stored = as_stored(first_value), as_stored(second_value)
        total = first_stored + second_stored
        if _PAIR_MIN <= total <= _PAIR_MAX:
            continue
        raise ValueError(
            f"{market} is a complementary pair and its two sides must sum to 1.0. As stored, "
            f"{first} {first_stored} + {second} {second_stored} = {total}."
        )
    return model


class PredictionBase(BaseModel):
    """Base prediction schema"""
    match_id: str
    market_type: str
    home_win_prob: Decimal
    draw_prob: Decimal
    away_win_prob: Decimal
    confidence_score: Optional[Decimal] = None


class PredictionResponse(BaseModel):
    """Prediction response schema for list views"""
    id: str
    match_id: str
    league_name: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    match_date: Optional[datetime] = None
    market_type: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_level: Optional[str] = None  # Hidden for free tier
    source: str  # "ml" or "expert"
    created_at: datetime
    
    class Config:
        from_attributes = True
    
    @validator('home_win_prob', 'draw_prob', 'away_win_prob', pre=True)
    def convert_decimal_to_float(cls, v):
        if isinstance(v, Decimal):
            return float(v)
        return v

    @field_serializer('match_date', 'created_at')
    def serialize_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        """UTC ISO-8601 with a trailing Z (see to_utc_iso_z)."""
        return to_utc_iso_z(value)


class PredictionDetailResponse(PredictionResponse):
    """Detailed prediction response with additional information"""
    reasoning: Optional[str] = None
    key_factors: Optional[Dict[str, Any]] = None
    expert_name: Optional[str] = None
    expert_accuracy: Optional[float] = None
    match_details: Optional[Dict[str, Any]] = None
    team_stats: Optional[Dict[str, Any]] = None
    head_to_head: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    """Paginated prediction list response"""
    predictions: List[PredictionResponse]
    pagination: Dict[str, int]
    tier_info: Dict[str, Any]


class FeedbackRequest(BaseModel):
    """Feedback submission request"""
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1 to 5")
    comment: Optional[str] = Field(None, max_length=500, description="Optional comment")
    is_upvote: Optional[bool] = Field(None, description="Upvote this prediction")
    is_downvote: Optional[bool] = Field(None, description="Downvote this prediction")


class FeedbackResponse(BaseModel):
    """Feedback response schema"""
    id: str
    prediction_id: str
    user_id: str
    username: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    is_upvote: Optional[bool] = None
    is_downvote: Optional[bool] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer('created_at')
    def serialize_created_at(self, value: Optional[datetime]) -> Optional[str]:
        """UTC ISO-8601 with a trailing Z (see to_utc_iso_z)."""
        return to_utc_iso_z(value)


class FeedbackListResponse(BaseModel):
    """Paginated feedback list response"""
    prediction_id: str
    summary: Dict[str, Any]
    feedback: List[FeedbackResponse]
    pagination: Dict[str, int]


# Expert Prediction Schemas

class ExpertPredictionCreate(BaseModel):
    """Schema for creating manual expert predictions"""
    match_id: str = Field(..., description="Match ID")

    # Match Outcome (1X2) - Required
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")

    # Both Teams to Score (BTTS) - Optional
    btts_yes_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability both teams score (0-1)")
    btts_no_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability at least one team does not score (0-1)")
    btts_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for BTTS prediction (0-1)")

    # Total Goals - Optional
    total_goals_over_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 2.5 goals (0-1)")
    total_goals_under_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 2.5 goals (0-1)")
    total_goals_over_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 3.5 goals (0-1)")
    total_goals_under_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 3.5 goals (0-1)")
    total_goals_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for total goals prediction (0-1)")

    # Reasoning & Metadata
    reasoning: Optional[str] = Field(None, max_length=2000, description="Expert reasoning")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing prediction")

    #: Ask for this record to be classified as test data, so it is left out of measured
    #: performance. The request is honoured ONLY where the installation allows classification
    #: (ALLOW_TEST_DATA_CLASSIFICATION, off by default and therefore off in any real deployment);
    #: everywhere else the record is simply stored unclassified. Without that gate this field
    #: would be a way for an expert to keep their own losses off the leaderboard.
    is_test_data: Optional[bool] = Field(
        None, description="Ask to classify this record as test data (honoured only where the "
                          "installation allows test-data classification)")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Exactly 1, at the scale the columns store: see outcome_probabilities_sum_to_one."""
        if 'home_win_prob' in values and 'draw_prob' in values:
            outcome_probabilities_sum_to_one(values['home_win_prob'], values['draw_prob'], v)
        return v

    @model_validator(mode='after')
    def complementary_pairs_sum_to_one(self):
        """Every complementary market, at the scale the columns store: see _pairs_sum_to_one."""
        return _pairs_sum_to_one(self)

    @model_validator(mode='after')
    def complementary_pairs_are_published_whole(self):
        return _pairs_are_whole(self)

    @model_validator(mode='after')
    def convictions_have_a_market(self):
        return _convictions_have_a_market(self)


class ExpertPredictionOverride(BaseModel):
    """Schema for overriding existing predictions"""
    prediction_id: str = Field(..., description="ID of prediction to override")

    # Match Outcome (1X2) - Required
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")

    # Both Teams to Score (BTTS) - Optional
    btts_yes_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability both teams score (0-1)")
    btts_no_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability at least one team does not score (0-1)")
    btts_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for BTTS prediction (0-1)")

    # Total Goals - Optional
    total_goals_over_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 2.5 goals (0-1)")
    total_goals_under_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 2.5 goals (0-1)")
    total_goals_over_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 3.5 goals (0-1)")
    total_goals_under_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 3.5 goals (0-1)")
    total_goals_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for total goals prediction (0-1)")

    # Reasoning & Metadata
    reasoning: str = Field(..., min_length=10, max_length=2000, description="Reason for override")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing override")

    #: Ask for this record to be classified as test data, so it is left out of measured
    #: performance. The request is honoured ONLY where the installation allows classification
    #: (ALLOW_TEST_DATA_CLASSIFICATION, off by default and therefore off in any real deployment);
    #: everywhere else the record is simply stored unclassified. Without that gate this field
    #: would be a way for an expert to keep their own losses off the leaderboard.
    is_test_data: Optional[bool] = Field(
        None, description="Ask to classify this record as test data (honoured only where the "
                          "installation allows test-data classification)")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Exactly 1, at the scale the columns store: see outcome_probabilities_sum_to_one."""
        if 'home_win_prob' in values and 'draw_prob' in values:
            outcome_probabilities_sum_to_one(values['home_win_prob'], values['draw_prob'], v)
        return v

    @model_validator(mode='after')
    def complementary_pairs_sum_to_one(self):
        """Every complementary market, at the scale the columns store: see _pairs_sum_to_one."""
        return _pairs_sum_to_one(self)

    @model_validator(mode='after')
    def complementary_pairs_are_published_whole(self):
        return _pairs_are_whole(self)

    @model_validator(mode='after')
    def convictions_have_a_market(self):
        return _convictions_have_a_market(self)


class ExpertPredictionUpdate(BaseModel):
    """Schema for updating existing predictions"""
    # Match Outcome (1X2) - Required
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")

    # Both Teams to Score (BTTS) - Optional
    btts_yes_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability both teams score (0-1)")
    btts_no_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability at least one team does not score (0-1)")
    btts_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for BTTS prediction (0-1)")

    # Total Goals - Optional
    total_goals_over_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 2.5 goals (0-1)")
    total_goals_under_25_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 2.5 goals (0-1)")
    total_goals_over_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of over 3.5 goals (0-1)")
    total_goals_under_35_prob: Optional[float] = Field(None, ge=0.0, le=1.0, description="Probability of under 3.5 goals (0-1)")
    total_goals_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for total goals prediction (0-1)")

    # Reasoning & Metadata
    reasoning: Optional[str] = Field(None, max_length=2000, description="Expert reasoning")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing prediction")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Exactly 1, at the scale the columns store: see outcome_probabilities_sum_to_one."""
        if 'home_win_prob' in values and 'draw_prob' in values:
            outcome_probabilities_sum_to_one(values['home_win_prob'], values['draw_prob'], v)
        return v

    @model_validator(mode='after')
    def complementary_pairs_sum_to_one(self):
        """Every complementary market, at the scale the columns store: see _pairs_sum_to_one."""
        return _pairs_sum_to_one(self)

    @model_validator(mode='after')
    def complementary_pair_edits_move_together(self):
        return _pair_edits_move_together(self)

    @model_validator(mode='after')
    def conviction_edits_move_with_the_market(self):
        return _conviction_edits_move_with_the_market(self)


class MatchDetails(BaseModel):
    """Match details for prediction responses"""
    home_team_name: str
    away_team_name: str
    home_team_logo: Optional[str] = None
    away_team_logo: Optional[str] = None
    league_name: Optional[str] = None
    match_date: Optional[datetime] = None
    external_match_id: Optional[str] = None

    @field_serializer('match_date')
    def serialize_match_date(self, value: Optional[datetime]) -> Optional[str]:
        """Kickoff as UTC ISO-8601 with a trailing Z, so the browser never reads it as local time."""
        return to_utc_iso_z(value)


class PublicPredictionResponse(BaseModel):
    """Public prediction response for published predictions (no authentication required)"""
    id: str
    match_id: str
    external_match_id: Optional[str] = None
    source: str
    priority_level: int

    # Match Outcome (1X2)
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_score: Optional[float] = None

    # Both Teams to Score (BTTS) - Optional
    btts_yes_prob: Optional[float] = None
    btts_no_prob: Optional[float] = None
    btts_confidence: Optional[float] = None

    # Total Goals - Optional
    total_goals_over_25_prob: Optional[float] = None
    total_goals_under_25_prob: Optional[float] = None
    total_goals_over_35_prob: Optional[float] = None
    total_goals_under_35_prob: Optional[float] = None
    total_goals_confidence: Optional[float] = None

    # Reasoning & Metadata
    reasoning: Optional[str] = None
    published_at: Optional[str] = None
    match_details: Dict[str, Any]  # Using Dict to avoid circular dependency

    class Config:
        from_attributes = True


class UserDetails(BaseModel):
    """User details for prediction responses"""
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ExpertPredictionResponse(BaseModel):
    """Response schema for expert predictions"""
    id: str
    match_id: str
    source: str
    priority_level: int

    # Match Outcome (1X2)
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    #: NULL when the author supplied no conviction. Declaring this a required float was the last
    #: link in the chain that made a blank field indistinguishable from a claim of zero: even once
    #: the column and the service could say "not given", the response model could not carry it.
    #: A reader must test for null, never for falsiness - 0.0 is a conviction someone chose.
    confidence_score: Optional[float] = None

    # Both Teams to Score (BTTS) - Optional
    btts_yes_prob: Optional[float] = None
    btts_no_prob: Optional[float] = None
    btts_confidence: Optional[float] = None

    # Total Goals - Optional
    total_goals_over_25_prob: Optional[float] = None
    total_goals_under_25_prob: Optional[float] = None
    total_goals_over_35_prob: Optional[float] = None
    total_goals_under_35_prob: Optional[float] = None
    total_goals_confidence: Optional[float] = None

    # Reasoning & Metadata
    reasoning: Optional[str] = None
    key_factors: Optional[Dict[str, Any]] = None

    # Status & Timestamps
    status: str
    created_by: str
    created_at: datetime
    published_at: Optional[datetime] = None
    #: When the prediction was last taken off the public lists. published_at is never cleared, so
    #: the pair says what a reader could see and when - which is what makes a prediction's
    #: standing at kickoff checkable after the match.
    unpublished_at: Optional[datetime] = None
    #: TRUE when this record is deliberately classified as test data and so excluded from measured
    #: performance. NULL means nobody has classified it.
    is_test_data: Optional[bool] = None
    superseded_by: Optional[str] = None

    # Enhanced fields
    match_details: Optional[MatchDetails] = None
    user_details: Optional[UserDetails] = None

    class Config:
        from_attributes = True

    @validator('id', 'match_id', 'created_by', 'superseded_by', pre=True)
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string"""
        if v is None:
            return v
        return str(v)

    @validator('home_win_prob', 'draw_prob', 'away_win_prob', 'confidence_score',
               'btts_yes_prob', 'btts_no_prob', 'btts_confidence',
               'total_goals_over_25_prob', 'total_goals_under_25_prob',
               'total_goals_over_35_prob', 'total_goals_under_35_prob',
               'total_goals_confidence', pre=True)
    def convert_decimal_to_float(cls, v):
        """Convert Decimal to float for JSON serialization"""
        if v is None:
            return v
        if isinstance(v, Decimal):
            return float(v)
        return v

    @field_serializer('created_at', 'published_at')
    def serialize_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        """UTC ISO-8601 with a trailing Z (see to_utc_iso_z)."""
        return to_utc_iso_z(value)


class ReviewQueueItem(BaseModel):
    """Schema for review queue items"""
    prediction_id: str
    match_id: str
    match_details: Dict[str, Any]
    source: str
    created_by: str
    expert_name: Optional[str] = None
    created_at: datetime
    status: str
    requires_approval: bool

    class Config:
        from_attributes = True

    @field_serializer('created_at')
    def serialize_created_at(self, value: Optional[datetime]) -> Optional[str]:
        """UTC ISO-8601 with a trailing Z (see to_utc_iso_z)."""
        return to_utc_iso_z(value)


class TestDataClassificationRequest(BaseModel):
    """Classify an existing record as test data, or clear the classification.

    The mechanism exists so an automated suite can mark the records it creates without writing a
    marker into the reasoning text, which is free-form and would let anyone exclude their own
    losses from measured performance by typing the right string. It is refused unless the
    installation allows classification at all.
    """
    is_test_data: bool = Field(
        True, description="TRUE classifies the record as test data; FALSE clears the "
                          "classification, leaving it unclassified")


class ExpertPerformanceMetrics(BaseModel):
    """Schema for expert performance analytics"""
    expert_id: str
    expert_name: str
    total_predictions: int
    published_predictions: int
    pending_predictions: int
    accuracy_rate: Optional[float] = None
    #: Mean conviction across this expert's predictions, or NULL when none of them carries one.
    #: An average of nothing is not zero. Widened alongside Prediction.confidence_score becoming
    #: nullable so the shape can carry "nobody claimed a conviction", and the producer in
    #: app/api/v1/endpoints/expert.py now averages only the predictions whose conviction is not
    #: None, so this really is NULL when an expert has rated none of their work.
    average_confidence: Optional[float] = None
    predictions_by_league: Dict[str, int]
    recent_predictions: List[ExpertPredictionResponse]
    performance_trend: List[Dict[str, Any]]

