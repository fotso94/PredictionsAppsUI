"""
Provider provenance tables.

- provider_entity_refs: which provider id refers to which internal match/team/league, and how the
  link was established. This is what keeps expert predictions attached to the right match when
  the active data provider changes.
- provider_forecasts: the CURRENT third-party forecast (GameForecastAPI, API-Football...) per match
  and provider, always separate from expert predictions. One indexed row per match/provider so a
  page render is a single lookup.
- provider_forecast_snapshots: append-only history of every distinct forecast we received. A forecast
  is evidence of what a model said BEFORE kickoff, so updating the current row must never be the only
  record: evaluation later depends on the prematch snapshot still existing.
- provider_forecast_results: the score of one PREMATCH snapshot against the real result. Keyed to the
  snapshot rather than to the match, so the evidence and the score of that evidence stay together and
  a later forecast can never be credited with a score that an earlier one earned.
"""

from sqlalchemy import Boolean, Column, DateTime, DECIMAL, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin, uuid_fk
from app.models.predictions import PREDICTION_OUTCOME_ENUM


class ProviderEntityRef(Base, UUIDMixin, TimestampMixin):
    """Provider-specific identifier of an internal entity."""
    __tablename__ = "provider_entity_refs"
    __table_args__ = (
        UniqueConstraint('entity_type', 'provider', 'external_id', name='uq_provider_entity_refs_provider_external'),
        Index('idx_provider_entity_refs_entity', 'entity_type', 'entity_id'),
        Index('idx_provider_entity_refs_provider', 'provider', 'external_id'),
        {'schema': 'predictions', 'comment': 'Provider ids for matches, teams and leagues'}
    )

    entity_type = Column(String(20), nullable=False, comment="match | team | league")
    entity_id = Column(UUID(as_uuid=True), nullable=False, comment="Internal id of the entity")
    provider = Column(String(50), nullable=False, comment="livescore | gameforecast | api_football | thesportsdb | sample")
    external_id = Column(String(100), nullable=False, comment="Provider identifier")
    match_confidence = Column(String(20), comment="exact | high | manual | legacy")
    matched_by = Column(String(50), comment="provider_id | name_kickoff | legacy_external_id | manual")
    ref_metadata = Column(JSONB, comment="Names/kickoff seen at the provider when the link was made")


class ProviderForecastRecord(Base, UUIDMixin, TimestampMixin):
    """Third-party forecast for one match (one row per provider and match)."""
    __tablename__ = "provider_forecasts"
    __table_args__ = (
        UniqueConstraint('match_id', 'provider', name='uq_provider_forecasts_match_provider'),
        Index('idx_provider_forecasts_provider_event', 'provider', 'external_event_id'),
        Index('idx_provider_forecasts_match_id', 'match_id'),
        {'schema': 'predictions', 'comment': 'Provider forecasts kept separate from expert predictions'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'})
    provider = Column(String(50), nullable=False)
    external_event_id = Column(String(100), nullable=False)

    home_win_prob = Column(DECIMAL(5, 4))
    draw_prob = Column(DECIMAL(5, 4))
    away_win_prob = Column(DECIMAL(5, 4))
    btts_yes_prob = Column(DECIMAL(5, 4))
    btts_no_prob = Column(DECIMAL(5, 4))
    total_goals_over_25_prob = Column(DECIMAL(5, 4))
    total_goals_under_25_prob = Column(DECIMAL(5, 4))
    total_goals_over_35_prob = Column(DECIMAL(5, 4))
    total_goals_under_35_prob = Column(DECIMAL(5, 4))
    exact_score = Column(JSONB, comment="score -> probability (0-1); listed scorelines only")
    exact_score_other_prob = Column(DECIMAL(5, 4), comment="Provider 'other scorelines' remainder; never a scoreline")
    recommended_bets = Column(JSONB)
    reasoning = Column(Text)
    confidence = Column(DECIMAL(5, 4), comment="Provider-published confidence, if any (never derived)")
    anomalies = Column(JSONB, comment="Consistency problems found in the provider payload, reported not corrected")

    match_confidence = Column(String(20), nullable=False, comment="exact | high (ambiguous forecasts are never stored)")
    matched_by = Column(String(50), nullable=False)
    model_run_at = Column(DateTime, comment="When the provider's model produced the forecast (UTC)")
    provider_updated_at = Column(DateTime, comment="Provider's updated_at (UTC)")
    fetched_at = Column(DateTime, nullable=False, comment="When we fetched it (UTC)")
    raw_payload = Column(JSONB)


class ProviderForecastSnapshot(Base, UUIDMixin, TimestampMixin):
    """Append-only history of provider forecasts.

    One row per distinct forecast content. Re-fetching an unchanged forecast only moves
    `last_fetched_at`, so the table stays small while never losing a prematch prediction.
    """
    __tablename__ = "provider_forecast_snapshots"
    __table_args__ = (
        # Deliberately not unique: a model that moves A -> B -> A must leave three ordered snapshots.
        Index('idx_provider_forecast_snapshots_match', 'match_id', 'provider', 'first_fetched_at'),
        Index('idx_provider_forecast_snapshots_event', 'provider', 'external_event_id'),
        {'schema': 'predictions', 'comment': 'Timestamped forecast evidence, never overwritten'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'})
    provider = Column(String(50), nullable=False)
    external_event_id = Column(String(100), nullable=False)
    content_hash = Column(String(64), comment="Hash of the forecast values; lets a resync recognise unchanged content")

    home_win_prob = Column(DECIMAL(5, 4))
    draw_prob = Column(DECIMAL(5, 4))
    away_win_prob = Column(DECIMAL(5, 4))
    btts_yes_prob = Column(DECIMAL(5, 4))
    btts_no_prob = Column(DECIMAL(5, 4))
    total_goals_over_25_prob = Column(DECIMAL(5, 4))
    total_goals_under_25_prob = Column(DECIMAL(5, 4))
    total_goals_over_35_prob = Column(DECIMAL(5, 4))
    total_goals_under_35_prob = Column(DECIMAL(5, 4))
    exact_score = Column(JSONB)
    exact_score_other_prob = Column(DECIMAL(5, 4))
    recommended_bets = Column(JSONB)
    reasoning = Column(Text)
    confidence = Column(DECIMAL(5, 4))
    anomalies = Column(JSONB)

    match_confidence = Column(String(20), nullable=False)
    matched_by = Column(String(50), nullable=False)
    model_run_at = Column(DateTime, comment="Provider's own model run time (UTC), NULL when not supplied")
    provider_updated_at = Column(DateTime, comment="Provider's updated_at (UTC), NULL when not supplied")
    first_fetched_at = Column(DateTime, nullable=False, comment="When this content was first retrieved (UTC)")
    last_fetched_at = Column(DateTime, nullable=False, comment="When this content was last seen unchanged (UTC)")
    kickoff_at_capture = Column(DateTime, comment="Fixture kickoff known when this snapshot was captured (UTC)")
    captured_before_kickoff = Column(Boolean,
                                     comment="True/false only when the kickoff was known at capture; NULL when it was not")
    raw_payload = Column(JSONB)


class ProviderForecastResult(Base, UUIDMixin, TimestampMixin):
    """The score of one prematch provider forecast against the real result.

    Keyed to the SNAPSHOT, never to the current `provider_forecasts` row. The current row is
    overwritten every time the model changes its mind, including after kickoff; scoring it would
    credit a provider with a forecast it did not publish before the match. `snapshot_id` is unique,
    so settling the same snapshot twice updates one row instead of counting it twice.

    A snapshot whose `captured_before_kickoff` is not True is never scored at all - neither a win
    nor a loss - and no row appears here for it.
    """
    __tablename__ = "provider_forecast_results"
    __table_args__ = (
        Index('idx_provider_forecast_results_match', 'match_id'),
        Index('idx_provider_forecast_results_provider_settled', 'provider', 'settled_at'),
        Index('idx_provider_forecast_results_outcome', 'outcome'),
        {'schema': 'predictions',
         'comment': 'Scores of prematch provider forecasts, kept with the snapshot that was scored'}
    )

    snapshot_id = uuid_fk('predictions.provider_forecast_snapshots.id', nullable=False, unique=True,
                          fk_kwargs={'ondelete': 'CASCADE'},
                          comment="The prematch forecast that was scored")
    match_id = uuid_fk('predictions.matches.id', nullable=False, fk_kwargs={'ondelete': 'CASCADE'})
    provider = Column(String(50), nullable=False, comment="Copied from the snapshot so a source can be aggregated")
    # NULL when the fixture was never played to a result (postponed, cancelled, abandoned).
    match_result_id = uuid_fk('predictions.match_results.id', nullable=True,
                              comment="Result that settled this forecast; NULL when the fixture was never played")

    # NULL means the source published no 1X2 for this fixture: there is nothing to be right or wrong
    # about, and that is not a loss. Other markets on the same snapshot may still be scored.
    outcome = Column(PREDICTION_OUTCOME_ENUM, nullable=True,
                     comment="1X2 settlement; NULL when the source published no 1X2 for this fixture")
    is_correct = Column(Boolean, comment="NULL when there was no single most likely outcome, or nothing to score")

    actual_outcome = Column(String(10), comment="home | draw | away in regulation time; NULL when not played")
    probability_of_actual = Column(DECIMAL(5, 4),
                                   comment="The probability the source itself published for the outcome that "
                                           "occurred; never derived, NULL when it published none")
    brier_score = Column(DECIMAL(6, 5),
                         comment="Three-way Brier score of the published 1X2 probabilities (0 perfect, 2 worst); "
                                 "NULL when it cannot be computed without inventing numbers")

    settled_at = Column(DateTime, nullable=False, comment="When this score was computed (UTC)")
    settled_by_system = Column(Boolean, nullable=False, default=True)
    rules_version = Column(String(50), nullable=False,
                           comment="Identifier of the settlement ruleset applied; see app/services/settlement.py")
    market_results = Column(JSONB,
                            comment="Per market: the rule applied, what was published, what happened, the outcome")
    void_reason = Column(String(120), comment="Why the forecast was voided rather than scored")
    snapshot_captured_at = Column(DateTime,
                                  comment="first_fetched_at of the scored snapshot, copied so the evidence's age "
                                          "is readable without a join")
    kickoff_at = Column(DateTime, comment="Kickoff of the fixture (UTC), copied for range queries on measured periods")
