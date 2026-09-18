"""Add provider entity references and provider forecasts

Revision ID: d4e5f6a7b8c9
Revises: eb2ef2cf6caf
Create Date: 2026-09-17 20:00:00.000000

Introduces:
1. predictions.provider_entity_refs — provider ids (Live Score API, GameForecastAPI, API-Football,
   TheSportsDB, sample) for internal matches, teams and leagues, with the confidence of the link.
2. predictions.provider_forecasts — third-party forecasts per match and provider, kept apart from
   expert predictions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'eb2ef2cf6caf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'provider_entity_refs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False, comment='match | team | league'),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Internal id of the entity'),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=False, comment='Provider identifier'),
        sa.Column('match_confidence', sa.String(length=20), nullable=True, comment='exact | high | manual | legacy'),
        sa.Column('matched_by', sa.String(length=50), nullable=True),
        sa.Column('ref_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint('entity_type', 'provider', 'external_id', name='uq_provider_entity_refs_provider_external'),
        schema='predictions',
        comment='Provider ids for matches, teams and leagues',
    )
    op.create_index('idx_provider_entity_refs_entity', 'provider_entity_refs', ['entity_type', 'entity_id'], schema='predictions')
    op.create_index('idx_provider_entity_refs_provider', 'provider_entity_refs', ['provider', 'external_id'], schema='predictions')

    op.create_table(
        'provider_forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('predictions.matches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_event_id', sa.String(length=100), nullable=False),
        sa.Column('home_win_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('draw_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('away_win_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('btts_yes_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('btts_no_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('total_goals_over_25_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('total_goals_under_25_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('total_goals_over_35_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('total_goals_under_35_prob', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('exact_score', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recommended_bets', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('confidence', sa.DECIMAL(5, 4), nullable=True),
        sa.Column('match_confidence', sa.String(length=20), nullable=False),
        sa.Column('matched_by', sa.String(length=50), nullable=False),
        sa.Column('model_run_at', sa.DateTime(), nullable=True),
        sa.Column('provider_updated_at', sa.DateTime(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint('match_id', 'provider', name='uq_provider_forecasts_match_provider'),
        schema='predictions',
        comment='Provider forecasts kept separate from expert predictions',
    )
    op.create_index('idx_provider_forecasts_provider_event', 'provider_forecasts', ['provider', 'external_event_id'], schema='predictions')
    op.create_index('idx_provider_forecasts_match_id', 'provider_forecasts', ['match_id'], schema='predictions')


def downgrade() -> None:
    op.drop_index('idx_provider_forecasts_match_id', table_name='provider_forecasts', schema='predictions')
    op.drop_index('idx_provider_forecasts_provider_event', table_name='provider_forecasts', schema='predictions')
    op.drop_table('provider_forecasts', schema='predictions')
    op.drop_index('idx_provider_entity_refs_provider', table_name='provider_entity_refs', schema='predictions')
    op.drop_index('idx_provider_entity_refs_entity', table_name='provider_entity_refs', schema='predictions')
    op.drop_table('provider_entity_refs', schema='predictions')
