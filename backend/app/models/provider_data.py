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
"""

from sqlalchemy import Boolean, Column, DateTime, DECIMAL, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin, uuid_fk


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
