"""
Predictions Schema Models
16 tables for prediction management, matches, and analytics
"""

from datetime import datetime

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Enum,
    Index, UniqueConstraint, CheckConstraint, DECIMAL
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, uuid_fk
import enum


# Enums
class PredictionSource(str, enum.Enum):
    """Prediction source enumeration"""
    ML_BASELINE = "ml_baseline"
    EXPERT_OVERRIDE = "expert_override"
    EXPERT_MANUAL = "expert_manual"
    ADMIN_MANUAL = "admin_manual"
    LLM_GENERATED = "llm_generated"
    API_FOOTBALL_BASELINE = "api_football_baseline"
    DEFAULT_RANDOMIZED = "default_randomized"


class PredictionStatus(str, enum.Enum):
    """Prediction status enumeration"""
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class MatchStatus(str, enum.Enum):
    """Match status enumeration"""
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class MarketType(str, enum.Enum):
    """Betting market type enumeration"""
    MATCH_RESULT = "match_result"  # 1X2
    OVER_UNDER = "over_under"
    BOTH_TEAMS_SCORE = "both_teams_score"
    CORRECT_SCORE = "correct_score"
    DOUBLE_CHANCE = "double_chance"


class PredictionOutcome(str, enum.Enum):
    """Settlement outcome of one prediction against a real result.

    PENDING - not settled yet.
    WON     - the single most likely outcome the source published is the outcome that occurred.
    LOST    - it is not.
    VOID    - the fixture was postponed, cancelled or abandoned, so it was never played to a result.
              A void is never a loss and never enters a hit rate.
    PUSH    - there was no single pick to be right or wrong about: two or three outcomes shared the
              highest probability the source published. The probabilistic score still applies.
    """
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    PUSH = "push"


#: One shared PostgreSQL enum type, used by both settlement tables (expert predictions and provider
#: forecasts) so the two scores are read with the same vocabulary.
PREDICTION_OUTCOME_ENUM = Enum(PredictionOutcome, name="predictionoutcome")


# Models

class Prediction(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Core predictions table
    Supports hybrid ML + Expert prediction system
    """
    __tablename__ = "predictions"
    __table_args__ = (
        Index('idx_predictions_match_id', 'match_id'),
        Index('idx_predictions_created_by', 'created_by'),
        Index('idx_predictions_source', 'source'),
        Index('idx_predictions_status', 'status'),
        Index('idx_predictions_published_at', 'published_at'),
        Index('idx_predictions_created_at', 'created_at'),
        Index('idx_predictions_superseded_by', 'superseded_by'),
        Index('idx_predictions_match_priority_published', 'match_id', 'priority_level', 'published_at'),
        # Exact equality, with no tolerance in it. outcome_probabilities_sum_to_one in
        # app/schemas/predictions.py refuses the same triples on the way in, measured at this
        # column's NUMERIC(5, 4) scale, so an expert who types 34 / 33 / 34 is told which numbers
        # are wrong instead of being handed this constraint's name. The two have to say the same
        # thing: a request validator looser than this CHECK turns a correctable mistake into a
        # failed insert, and one stricter than it refuses rows the table would accept.
        CheckConstraint('home_win_prob + draw_prob + away_win_prob = 1.0', name='ck_predictions_prob_sum'),
        # Restated for a nullable column. A CHECK is satisfied by NULL either way (NULL >= 0 is
        # NULL, not FALSE), so the old two-clause form did not actually reject an unsupplied
        # conviction - but it read as though it required one, and the next person to widen this
        # column should not have to rediscover that. The IS NULL arm says the permission out loud,
        # exactly as the three sibling confidence constraints below already do.
        CheckConstraint('confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)', name='ck_predictions_confidence'),
        CheckConstraint('priority_level >= 0 AND priority_level <= 100', name='ck_predictions_priority_level_range'),
        CheckConstraint('btts_yes_prob IS NULL OR (btts_yes_prob >= 0 AND btts_yes_prob <= 1)', name='ck_predictions_btts_yes_prob_range'),
        CheckConstraint('btts_no_prob IS NULL OR (btts_no_prob >= 0 AND btts_no_prob <= 1)', name='ck_predictions_btts_no_prob_range'),
        CheckConstraint('btts_confidence IS NULL OR (btts_confidence >= 0 AND btts_confidence <= 1)', name='ck_predictions_btts_confidence_range'),
        CheckConstraint('total_goals_confidence IS NULL OR (total_goals_confidence >= 0 AND total_goals_confidence <= 1)', name='ck_predictions_total_goals_confidence_range'),
        # WHAT THIS REJECTS: two BTTS probabilities that are both present and do not sum to 1.
        # WHAT IT DOES NOT REJECT: one side present and the other NULL. With btts_yes_prob NULL
        # the expression is FALSE OR NULL, which is NULL, and Postgres violates a CHECK only on
        # FALSE - so a half-published pair is stored without complaint, and always has been. It is
        # written out here because the two-clause shape reads as though the first clause forbade
        # exactly that, and anyone relying on it to do so is relying on nothing.
        #
        # WHAT "SUM" MEANS HERE: the two STORED values added. Postgres rounds each to this
        # column's NUMERIC(5, 4) before the expression sees it, so 0.98995 and 0.02005 are added
        # as 0.9900 and 0.0201 and the CHECK is FALSE at 1.0101 - although those two request
        # floats sum to exactly 1.01. _pairs_sum_to_one in app/schemas/predictions.py rounds the
        # same way before it compares, so the request and this line judge the same numbers and
        # the strip between them where a row is accepted and then refused does not exist.
        #
        # The half-pair rule is enforced instead on the request, in COMPLEMENTARY_PAIRS in
        # app/schemas/predictions.py, where the caller can be told which other side is missing.
        # It is deliberately NOT restated as a constraint here, and the total-goals pairs are
        # given none, because a half-published market is a state the rest of this system is built
        # to HOLD rather than to refuse: app/services/settlement.py::_score_two_way stores such a
        # row and declines to score that market ("the source published only one side of this
        # market"), and tests/services/test_settlement.py::
        # test_one_published_side_of_a_two_way_market_is_not_enough stores one to prove it. A
        # CHECK here would turn a state settlement can already report honestly into a failed
        # insert. What is closed is composing one through the expert API, and that is closed on
        # the request.
        #
        # The stored rows were counted before deciding, in case a constraint was wanted: on
        # 2026-09-21 this installation held 250 predictions, four with a complete BTTS pair, none
        # half-published, and no total-goals pair stored at all. Nothing stored would have blocked
        # a migration; the reason for not writing one is the paragraph above, not the data.
        CheckConstraint('(btts_yes_prob IS NULL AND btts_no_prob IS NULL) OR (btts_yes_prob + btts_no_prob BETWEEN 0.99 AND 1.01)', name='ck_predictions_btts_prob_sum'),
        {'schema': 'predictions', 'comment': 'Core predictions'}
    )
    
    # Match Reference
    match_id = uuid_fk('predictions.matches.id', nullable=False)
    
    # Source Attribution
    source = Column(Enum(PredictionSource), nullable=False, comment="Prediction source")
    created_by = uuid_fk('users.users.id', nullable=False, comment="User who created prediction")
    ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True, comment="Original ML prediction")
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=True, comment="Expert who created/modified")
    
    # Match Outcome Probabilities (must sum to 1.0)
    home_win_prob = Column(DECIMAL(5, 4), nullable=False, comment="Home win probability")
    draw_prob = Column(DECIMAL(5, 4), nullable=False, comment="Draw probability")
    away_win_prob = Column(DECIMAL(5, 4), nullable=False, comment="Away win probability")

    # Both Teams to Score (BTTS) Probabilities (optional, must sum to 1.0 if provided)
    btts_yes_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability both teams score (0-1)")
    btts_no_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability at least one team does not score (0-1)")
    btts_confidence = Column(DECIMAL(5, 4), nullable=True, comment="Confidence score for BTTS prediction (0-1)")

    # Total Goals Probabilities (optional)
    total_goals_over_25_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability of over 2.5 goals (0-1)")
    total_goals_under_25_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability of under 2.5 goals (0-1)")
    total_goals_over_35_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability of over 3.5 goals (0-1)")
    total_goals_under_35_prob = Column(DECIMAL(5, 4), nullable=True, comment="Probability of under 3.5 goals (0-1)")
    total_goals_confidence = Column(DECIMAL(5, 4), nullable=True, comment="Confidence score for total goals prediction (0-1)")

    # Confidence & Reasoning
    #: How strongly the source stands behind this prediction, 0-1, or NULL when nobody said.
    #:
    #: NULLABLE ON PURPOSE. It used to be NOT NULL, and the expert service coerced a missing
    #: conviction to 0.0000 on its way in, so a blank field and a deliberate "I rate this at
    #: nothing" became the same stored number and every reader showed both as 0%. An absence is
    #: not a figure: the column has to be able to say "not given" for the interface to be able
    #: to say it. Readers must test `is not None`, never truthiness - 0 is a real conviction.
    confidence_score = Column(DECIMAL(5, 4), nullable=True, comment="Confidence score 0-1; NULL when the source supplied none")
    reasoning = Column(Text, comment="Prediction reasoning/explanation")
    key_factors = Column(JSONB, comment="Key factors influencing prediction")
    
    # Status & Approval
    status = Column(Enum(PredictionStatus), nullable=False, default=PredictionStatus.PENDING)
    approved_by = uuid_fk('users.users.id', nullable=True, comment="Admin who approved")
    approved_at = Column(DateTime)
    #: When this prediction first went live. It is a historical fact and is never cleared or
    #: restamped once set: settlement reads it to decide whether the prediction predates kickoff,
    #: so clearing it on an unpublish would destroy the only evidence that it stood before the
    #: match. Unpublishing records ``unpublished_at`` instead.
    published_at = Column(DateTime)
    #: When it was last taken off the public lists (PUBLISHED -> ARCHIVED). Normally NULL while it
    #: is live. Paired with published_at this says what a reader could see at any given moment,
    #: which is what makes "was this standing at kickoff?" answerable after the fact.
    #:
    #: One exception, and it is the point of the column: a withdrawal recorded BEFORE kickoff is
    #: frozen once the match has kicked off, so a later republish does not clear it and a later
    #: unpublish does not overwrite it. Without that, an expert could withdraw everything in
    #: advance, wait for the results and republish only the winners. Such a row can therefore be
    #: PUBLISHED again while still carrying the prematch withdrawal that keeps it out of the
    #: measured record; the full toggle history is in prediction_audit.
    unpublished_at = Column(DateTime, comment="When the prediction was last unpublished (archived)")
    #: Explicit, server-side classification of a record as test data (a QA harness run, a demo
    #: fixture). NULL means unclassified, which is the honest state for anything nobody has
    #: deliberately marked. Measured performance excludes rows flagged TRUE. It is never inferred
    #: from the reasoning text, and it can only be set while
    #: ``settings.ALLOW_TEST_DATA_CLASSIFICATION`` is on - off in any normal deployment - so no
    #: user can exclude their own record from the leaderboard by asking for it.
    is_test_data = Column(Boolean, nullable=True,
                          comment="TRUE when this record is deliberately classified as test data")

    # Multi-Source Priority System
    priority_level = Column(Integer, nullable=False, comment="Priority level (0-100): Expert=100, LLM=50, API-Football=25, Randomized=0")
    superseded_by = uuid_fk('predictions.predictions.id', nullable=True, comment="ID of prediction that supersedes this one")

    # Metadata
    prediction_metadata = Column(JSONB, comment="Additional prediction metadata")
    
    # Relationships
    match = relationship("Match", back_populates="predictions")
    overrides = relationship("PredictionOverride", back_populates="prediction", cascade="all, delete-orphan")
    audit_logs = relationship("PredictionAudit", back_populates="prediction", cascade="all, delete-orphan")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    markets = relationship("PredictionMarket", back_populates="prediction", cascade="all, delete-orphan")
    analytics = relationship("PredictionAnalytics", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    views = relationship("UserPredictionView", back_populates="prediction", cascade="all, delete-orphan")
    feedback = relationship("UserPredictionFeedback", back_populates="prediction", cascade="all, delete-orphan")
    comments = relationship("PredictionComment", back_populates="prediction", cascade="all, delete-orphan")
    shares = relationship("PredictionShare", back_populates="prediction", cascade="all, delete-orphan")


class PredictionOverride(Base, UUIDMixin, TimestampMixin):
    """Expert overrides of ML predictions"""
    __tablename__ = "prediction_overrides"
    __table_args__ = (
        Index('idx_prediction_overrides_prediction_id', 'prediction_id'),
        Index('idx_prediction_overrides_expert_user_id', 'expert_user_id'),
        Index('idx_prediction_overrides_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction overrides'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    expert_user_id = uuid_fk('users.users.id', nullable=False)
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)
    
    # Original ML Prediction
    original_ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True)
    original_probabilities = Column(JSONB, nullable=False, comment="Original ML probabilities")
    original_confidence = Column(DECIMAL(5, 4), comment="Original ML confidence")
    
    # New Expert Prediction
    new_probabilities = Column(JSONB, nullable=False, comment="Expert-adjusted probabilities")
    #: The conviction the override carries, or NULL when the expert supplied none. Nullable for the
    #: same reason as Prediction.confidence_score: this row used to store 0.0000 for "not given",
    #: which made the audit trail claim an expert had rated their own override at zero.
    new_confidence = Column(DECIMAL(5, 4), nullable=True, comment="Expert confidence; NULL when none was supplied")
    
    # Override Details
    override_reason = Column(Text, nullable=False, comment="Reason for override")
    confidence_adjustment = Column(DECIMAL(6, 4), comment="Confidence change")
    key_insights = Column(JSONB, comment="Expert insights")
    
    # Review & Approval
    reviewed_by_admin_id = uuid_fk('users.users.id', nullable=True)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    is_approved = Column(Boolean, default=False)
    
    # Relationships
    prediction = relationship("Prediction", back_populates="overrides")


class PredictionAudit(Base, UUIDMixin, TimestampMixin):
    """Audit trail for prediction changes"""
    __tablename__ = "prediction_audit"
    __table_args__ = (
        Index('idx_prediction_audit_prediction_id', 'prediction_id'),
        Index('idx_prediction_audit_user_id', 'user_id'),
        Index('idx_prediction_audit_action', 'action'),
        Index('idx_prediction_audit_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction audit trail'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Action Info
    action = Column(String(50), nullable=False, comment="created, updated, approved, published, etc.")
    action_description = Column(Text)
    
    # Changes
    old_values = Column(JSONB, comment="Previous values")
    new_values = Column(JSONB, comment="New values")
    changes_summary = Column(Text, comment="Human-readable summary")
    
    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    
    # Relationships
    prediction = relationship("Prediction", back_populates="audit_logs")


class PredictionResult(Base, UUIDMixin, TimestampMixin):
    """The score of ONE expert prediction against the real result.

    One row per prediction (``prediction_id`` is unique), so re-running settlement updates the same
    row instead of counting the prediction twice.

    ``rules_version`` and ``market_results`` exist because "was it right?" is meaningless without the
    rule that was applied. The rule text that settled each market is stored on the row, next to what
    the expert published and what actually happened, so a score can be read back and checked years
    later even if the rules change in the meantime.
    """
    __tablename__ = "prediction_results"
    __table_args__ = (
        Index('idx_prediction_results_prediction_id', 'prediction_id'),
        Index('idx_prediction_results_outcome', 'outcome'),
        Index('idx_prediction_results_settled_at', 'settled_at'),
        {'schema': 'predictions', 'comment': 'Prediction results'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    # Nullable: a postponed or cancelled fixture is settled VOID and has no score to point at.
    match_result_id = uuid_fk('predictions.match_results.id', nullable=True,
                              comment="Result that settled this prediction; NULL when the fixture was never played")

    # Outcome
    outcome = Column(PREDICTION_OUTCOME_ENUM, nullable=False)
    is_correct = Column(Boolean, comment="Was prediction correct; NULL when there was no single pick or no result")

    # Accuracy Metrics
    probability_accuracy = Column(DECIMAL(5, 4), comment="How close probabilities were")
    confidence_calibration = Column(DECIMAL(5, 4), comment="Confidence vs actual")

    # What actually happened, and how the published numbers stood up to it
    actual_outcome = Column(String(10), comment="home | draw | away in regulation time; NULL when not played")
    probability_of_actual = Column(DECIMAL(5, 4),
                                   comment="The probability the expert published for the outcome that occurred; "
                                           "never derived, NULL when they published none")
    brier_score = Column(DECIMAL(6, 5),
                         comment="Three-way Brier score of the 1X2 probabilities (0 perfect, 2 worst); "
                                 "NULL when it cannot be computed without inventing numbers")

    # Financial Metrics
    potential_return = Column(DECIMAL(10, 2))
    actual_return = Column(DECIMAL(10, 2))
    roi_percentage = Column(DECIMAL(10, 2))

    # Settlement
    settled_at = Column(DateTime, nullable=False)
    settled_by_system = Column(Boolean, default=True)
    rules_version = Column(String(50), nullable=False,
                           comment="Identifier of the settlement ruleset applied; see app/services/settlement.py")
    market_results = Column(JSONB,
                            comment="Per market: the rule applied, what was published, what happened, the outcome")
    void_reason = Column(String(120), comment="Why the prediction was voided rather than scored")

    # Relationships
    prediction = relationship("Prediction", back_populates="result")


class PredictionMarket(Base, UUIDMixin, TimestampMixin):
    """Multiple betting markets per prediction"""
    __tablename__ = "prediction_markets"
    __table_args__ = (
        Index('idx_prediction_markets_prediction_id', 'prediction_id'),
        Index('idx_prediction_markets_market_type', 'market_type'),
        {'schema': 'predictions', 'comment': 'Prediction markets'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    
    # Market Info
    market_type = Column(Enum(MarketType), nullable=False)
    market_value = Column(String(50), comment="e.g., 'Over 2.5', 'BTTS Yes'")
    
    # Prediction
    predicted_outcome = Column(String(50), nullable=False)
    probability = Column(DECIMAL(5, 4), nullable=False)
    confidence = Column(DECIMAL(5, 4), nullable=False)
    
    # Odds
    recommended_odds = Column(DECIMAL(6, 2))
    market_odds = Column(DECIMAL(6, 2))
    
    # Status
    is_primary = Column(Boolean, default=False, comment="Primary market for this prediction")
    
    # Relationships
    prediction = relationship("Prediction", back_populates="markets")


class PredictionAnalytics(Base, UUIDMixin, TimestampMixin):
    """Analytics for individual predictions"""
    __tablename__ = "prediction_analytics"
    __table_args__ = (
        Index('idx_prediction_analytics_prediction_id', 'prediction_id'),
        {'schema': 'predictions', 'comment': 'Prediction analytics'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    
    # Engagement Metrics
    view_count = Column(Integer, nullable=False, default=0)
    unique_viewers = Column(Integer, nullable=False, default=0)
    share_count = Column(Integer, nullable=False, default=0)
    comment_count = Column(Integer, nullable=False, default=0)
    
    # Feedback Metrics
    upvote_count = Column(Integer, nullable=False, default=0)
    downvote_count = Column(Integer, nullable=False, default=0)
    average_rating = Column(DECIMAL(3, 2))
    total_ratings = Column(Integer, nullable=False, default=0)
    
    # Performance Metrics
    accuracy_score = Column(DECIMAL(5, 4))
    roi_percentage = Column(DECIMAL(10, 2))
    engagement_score = Column(DECIMAL(10, 2), comment="Composite engagement metric")
    
    # Relationships
    prediction = relationship("Prediction", back_populates="analytics")


class UserPredictionView(Base, UUIDMixin, TimestampMixin):
    """Track user views of predictions"""
    __tablename__ = "user_prediction_views"
    __table_args__ = (
        Index('idx_user_prediction_views_prediction_id', 'prediction_id'),
        Index('idx_user_prediction_views_user_id', 'user_id'),
        Index('idx_user_prediction_views_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'User prediction views'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=True, comment="Null for anonymous users")

    # View Info
    session_id = Column(String(255))
    view_duration_seconds = Column(Integer)

    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    referrer = Column(String(500))

    # Relationships
    prediction = relationship("Prediction", back_populates="views")


class UserPredictionFeedback(Base, UUIDMixin, TimestampMixin):
    """User feedback on predictions"""
    __tablename__ = "user_prediction_feedback"
    __table_args__ = (
        Index('idx_user_prediction_feedback_prediction_id', 'prediction_id'),
        Index('idx_user_prediction_feedback_user_id', 'user_id'),
        UniqueConstraint('prediction_id', 'user_id', name='uq_user_prediction_feedback'),
        {'schema': 'predictions', 'comment': 'User prediction feedback'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)

    # Feedback
    rating = Column(Integer, comment="1-5 star rating")
    is_upvote = Column(Boolean)
    is_downvote = Column(Boolean)

    # Comment
    comment = Column(Text)

    # Relationships
    prediction = relationship("Prediction", back_populates="feedback")


class Match(Base, UUIDMixin, TimestampMixin):
    """Match information"""
    __tablename__ = "matches"
    __table_args__ = (
        Index('idx_matches_home_team_id', 'home_team_id'),
        Index('idx_matches_away_team_id', 'away_team_id'),
        Index('idx_matches_league_id', 'league_id'),
        Index('idx_matches_match_date', 'match_date'),
        Index('idx_matches_status', 'status'),
        Index('idx_matches_external_api_id', 'external_api_id'),
        {'schema': 'predictions', 'comment': 'Match information'}
    )

    # Teams
    home_team_id = uuid_fk('predictions.teams.id', nullable=False)
    away_team_id = uuid_fk('predictions.teams.id', nullable=False)

    # League
    league_id = uuid_fk('predictions.leagues.id', nullable=False)

    # Match Details
    match_date = Column(DateTime, nullable=False)
    venue = Column(String(255))
    season = Column(String(20), comment="e.g., '2023-24'")
    round = Column(String(50), comment="e.g., 'Matchday 15'")

    # Status
    status = Column(Enum(MatchStatus), nullable=False, default=MatchStatus.SCHEDULED)

    # External API
    external_api_id = Column(String(100), unique=True, comment="External API match ID")
    external_api_source = Column(String(50), comment="API source name")

    # Metadata
    match_metadata = Column(JSONB, comment="Additional match data")

    # Relationships
    predictions = relationship("Prediction", back_populates="match", cascade="all, delete-orphan")
    result = relationship("MatchResult", back_populates="match", uselist=False, cascade="all, delete-orphan")
    statistics = relationship("MatchStatistic", back_populates="match", cascade="all, delete-orphan")


class MatchResult(Base, UUIDMixin, TimestampMixin):
    """Match results, kept as the separate PERIODS a tie is actually made of.

    A knockout tie has more than one scoreline and they answer different questions. Switzerland
    0-0 Colombia, 4-3 on penalties, is a draw to every market that settles on regulation time and
    a Switzerland win to everyone who watched it. Collapsing that into one pair of columns makes
    one of those two readers wrong, so both are stored:

    * ``home_score``/``away_score`` - the score of the football that was played, extra time
      included. This is the scoreline on display and the one non-settlement code should read.
      Penalties are never folded into it.
    * ``home_score_ft``/``away_score_ft`` - REGULATION time, 90 minutes plus stoppage. This is
      the only period markets settle on (see :mod:`app.services.settlement`). NULL means the
      source did not supply it, and no other period is ever substituted for it.
    * ``home_score_et``/``away_score_et`` and ``home_score_pens``/``away_score_pens`` - extra
      time and the shoot-out. Stored so the reader sees the true result of the tie; they settle
      nothing.

    Every period but ``home_score``/``away_score`` is nullable, because "not supplied" is a real
    and common answer and is not the same as zero. Rows written before the periods were carried
    have NULL in all of them, which is exactly right: nothing is known about their periods.
    """
    __tablename__ = "match_results"
    __table_args__ = (
        Index('idx_match_results_match_id', 'match_id'),
        {'schema': 'predictions', 'comment': 'Match results'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False, unique=True)

    # Score of the football played (extra time included, penalties never)
    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)

    # Half Time
    home_score_ht = Column(Integer)
    away_score_ht = Column(Integer)

    # Regulation time (90' + stoppage) - the only period markets settle on
    home_score_ft = Column(Integer, comment="Regulation-time score: 90 minutes plus stoppage")
    away_score_ft = Column(Integer, comment="Regulation-time score: 90 minutes plus stoppage")

    # Beyond regulation: shown to readers, never settled on
    home_score_et = Column(Integer, comment="Score after extra time")
    away_score_et = Column(Integer, comment="Score after extra time")
    home_score_pens = Column(Integer, comment="Penalty shoot-out score")
    away_score_pens = Column(Integer, comment="Penalty shoot-out score")

    # Result
    result = Column(String(10), comment="H, D, A")

    # Additional Stats
    home_corners = Column(Integer)
    away_corners = Column(Integer)
    home_yellow_cards = Column(Integer)
    away_yellow_cards = Column(Integer)
    home_red_cards = Column(Integer)
    away_red_cards = Column(Integer)

    # Metadata
    result_metadata = Column(JSONB, comment="Additional result data")

    # Relationships
    match = relationship("Match", back_populates="result")


class MatchStatistic(Base, UUIDMixin, TimestampMixin):
    """Match statistics (pre-match, live, post-match)"""
    __tablename__ = "match_statistics"
    __table_args__ = (
        Index('idx_match_statistics_match_id', 'match_id'),
        Index('idx_match_statistics_stat_type', 'stat_type'),
        {'schema': 'predictions', 'comment': 'Match statistics'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False)

    # Stat Type
    stat_type = Column(String(50), nullable=False, comment="pre_match, live, post_match")
    stat_category = Column(String(50), comment="possession, shots, passes, etc.")

    # Values
    home_value = Column(DECIMAL(10, 2))
    away_value = Column(DECIMAL(10, 2))

    # Metadata
    stat_metadata = Column(JSONB)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    match = relationship("Match", back_populates="statistics")


class League(Base, UUIDMixin, TimestampMixin):
    """League/competition reference data"""
    __tablename__ = "leagues"
    __table_args__ = (
        Index('idx_leagues_name', 'name'),
        Index('idx_leagues_country', 'country'),
        Index('idx_leagues_external_api_id', 'external_api_id'),
        {'schema': 'predictions', 'comment': 'League reference data'}
    )

    # League Info
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    country = Column(String(100), nullable=False)
    country_code = Column(String(3))

    # Details
    logo_url = Column(String(500))
    tier = Column(Integer, comment="League tier/division")

    # External API
    external_api_id = Column(String(100), unique=True)
    external_api_source = Column(String(50))

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Metadata
    league_metadata = Column(JSONB)


class Team(Base, UUIDMixin, TimestampMixin):
    """Team reference data"""
    __tablename__ = "teams"
    __table_args__ = (
        Index('idx_teams_name', 'name'),
        Index('idx_teams_country', 'country'),
        Index('idx_teams_external_api_id', 'external_api_id'),
        Index('idx_teams_team_scope', 'team_scope'),
        Index('uq_teams_identity_key', 'identity_key', unique=True),
        {'schema': 'predictions', 'comment': 'Team reference data'}
    )

    # Team Info
    name = Column(String(255), nullable=False)
    short_name = Column(String(50))
    code = Column(String(10), comment="3-letter team code")
    country = Column(String(100))

    # Identity
    #
    # `country` cannot carry identity for a national team: a national-team competition has no
    # country of its own, so every FIFA competition hands the same stand-in ("World") to every team
    # in it, and Spain's men's squad, Spain's women's squad and a Spanish club then share one
    # country bucket while their names differ only by a suffix a club-name matcher discards.
    # These two columns are what separate them instead.
    #
    # team_scope: club-or-country and squad category, the `TeamScope` value of the competition the
    # row was first seen in. It is a fact about the team, not about one competition, so Spain in the
    # World Cup and Spain in the Nations League are one row.
    team_scope = Column(String(32), nullable=False, server_default='club_senior_men',
                        comment="TeamScope value: club/national and squad category")
    # identity_key: that scope, a colon, and the normalised name with any '(W)' suffix removed
    # ("national_senior_women:spain"). UNIQUE, so two squads of one country sharing a row is refused
    # by the database and not merely avoided by the lookup that runs before it. NULL on rows written
    # by code that does not know the competition, which are still found by name within their scope.
    identity_key = Column(String(300),
                          comment="Scope-prefixed normalised team name; unique across all teams")

    # Details
    logo_url = Column(String(500))
    founded_year = Column(Integer)
    venue_name = Column(String(255))
    venue_capacity = Column(Integer)

    # External API
    external_api_id = Column(String(100), unique=True)
    external_api_source = Column(String(50))

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Metadata
    team_metadata = Column(JSONB)


class PredictionTemplate(Base, UUIDMixin, TimestampMixin):
    """Reusable prediction templates"""
    __tablename__ = "prediction_templates"
    __table_args__ = (
        Index('idx_prediction_templates_created_by', 'created_by'),
        Index('idx_prediction_templates_is_active', 'is_active'),
        {'schema': 'predictions', 'comment': 'Prediction templates'}
    )

    # Template Info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_by = uuid_fk('users.users.id', nullable=False)

    # Template Data
    template_data = Column(JSONB, nullable=False, comment="Template configuration")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_public = Column(Boolean, nullable=False, default=False)

    # Usage Stats
    usage_count = Column(Integer, nullable=False, default=0)


class PredictionComment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Comments on predictions"""
    __tablename__ = "prediction_comments"
    __table_args__ = (
        Index('idx_prediction_comments_prediction_id', 'prediction_id'),
        Index('idx_prediction_comments_user_id', 'user_id'),
        Index('idx_prediction_comments_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction comments'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)
    parent_comment_id = uuid_fk('predictions.prediction_comments.id', nullable=True, comment="For nested comments")

    # Comment
    comment_text = Column(Text, nullable=False)

    # Moderation
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_approved = Column(Boolean, nullable=False, default=True)

    # Relationships
    prediction = relationship("Prediction", back_populates="comments")


class PredictionShare(Base, UUIDMixin, TimestampMixin):
    """Track prediction shares"""
    __tablename__ = "prediction_shares"
    __table_args__ = (
        Index('idx_prediction_shares_prediction_id', 'prediction_id'),
        Index('idx_prediction_shares_user_id', 'user_id'),
        Index('idx_prediction_shares_platform', 'platform'),
        {'schema': 'predictions', 'comment': 'Prediction shares'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=True)

    # Share Info
    platform = Column(String(50), nullable=False, comment="twitter, facebook, whatsapp, etc.")
    share_url = Column(String(500))

    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)

    # Relationships
    prediction = relationship("Prediction", back_populates="shares")
