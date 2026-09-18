"""
Provider provenance tables.

- provider_entity_refs: which provider id refers to which internal match/team/league, and how the
  link was established. This is what keeps expert predictions attached to the right match when
  the active data provider changes.
- provider_forecasts: third-party forecasts (GameForecastAPI, API-Football...) stored per match and
  provider, always separate from expert predictions.
"""

from sqlalchemy import Column, DateTime, DECIMAL, Index, String, Text, UniqueConstraint
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
    exact_score = Column(JSONB, comment="score -> probability (0-1)")
    recommended_bets = Column(JSONB)
    reasoning = Column(Text)
    confidence = Column(DECIMAL(5, 4), comment="Provider-published confidence, if any (never derived)")

    match_confidence = Column(String(20), nullable=False, comment="exact | high (ambiguous forecasts are never stored)")
    matched_by = Column(String(50), nullable=False)
    model_run_at = Column(DateTime, comment="When the provider's model produced the forecast (UTC)")
    provider_updated_at = Column(DateTime, comment="Provider's updated_at (UTC)")
    fetched_at = Column(DateTime, nullable=False, comment="When we fetched it (UTC)")
    raw_payload = Column(JSONB)
