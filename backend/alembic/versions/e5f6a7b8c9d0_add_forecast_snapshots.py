"""Preserve forecast evidence: append-only snapshots, other-score bucket, payload anomalies

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-18 03:45:00.000000

A forecast is evidence of what a model said before a match was played. Updating
predictions.provider_forecasts in place destroyed that evidence, so this migration adds:

1. predictions.provider_forecast_snapshots — append-only history, one row per distinct forecast
   content per match and provider. Re-fetching unchanged content only moves last_fetched_at.
   predictions.provider_forecasts remains the convenient "current forecast" lookup.
2. provider_forecasts.exact_score_other_prob — the provider's "other scorelines" remainder, kept
   out of the scoreline map so it is never rendered as a specific score.
3. provider_forecasts.anomalies — consistency problems found in a provider payload, reported
   rather than silently corrected.

The upgrade backfills one snapshot per existing forecast row so no stored evidence is lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROB = sa.DECIMAL(5, 4)


def upgrade() -> None:
    op.add_column('provider_forecasts',
                  sa.Column('exact_score_other_prob', _PROB, nullable=True,
                            comment="Provider 'other scorelines' remainder; never a scoreline"),
                  schema='predictions')
    op.add_column('provider_forecasts',
                  sa.Column('anomalies', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                            comment='Consistency problems found in the provider payload, reported not corrected'),
                  schema='predictions')

    op.create_table(
        'provider_forecast_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_event_id', sa.String(length=100), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True,
                  comment='Hash of the forecast values; lets a resync recognise unchanged content'),
        sa.Column('home_win_prob', _PROB, nullable=True),
        sa.Column('draw_prob', _PROB, nullable=True),
        sa.Column('away_win_prob', _PROB, nullable=True),
        sa.Column('btts_yes_prob', _PROB, nullable=True),
        sa.Column('btts_no_prob', _PROB, nullable=True),
        sa.Column('total_goals_over_25_prob', _PROB, nullable=True),
        sa.Column('total_goals_under_25_prob', _PROB, nullable=True),
        sa.Column('total_goals_over_35_prob', _PROB, nullable=True),
        sa.Column('total_goals_under_35_prob', _PROB, nullable=True),
        sa.Column('exact_score', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('exact_score_other_prob', _PROB, nullable=True),
        sa.Column('recommended_bets', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('confidence', _PROB, nullable=True),
        sa.Column('anomalies', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('match_confidence', sa.String(length=20), nullable=False),
        sa.Column('matched_by', sa.String(length=50), nullable=False),
        sa.Column('model_run_at', sa.DateTime(), nullable=True,
                  comment="Provider's own model run time (UTC), NULL when not supplied"),
        sa.Column('provider_updated_at', sa.DateTime(), nullable=True,
                  comment="Provider's updated_at (UTC), NULL when not supplied"),
        sa.Column('first_fetched_at', sa.DateTime(), nullable=False),
        sa.Column('last_fetched_at', sa.DateTime(), nullable=False),
        sa.Column('kickoff_at_capture', sa.DateTime(), nullable=True),
        sa.Column('captured_before_kickoff', sa.Boolean(), nullable=False, server_default=sa.text('false'),
                  comment='True when retrieved before kickoff: only these are prematch evidence'),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['predictions.matches.id'], ondelete='CASCADE'),
        schema='predictions',
        comment='Timestamped forecast evidence, never overwritten',
    )
    op.create_index('idx_provider_forecast_snapshots_match', 'provider_forecast_snapshots',
                    ['match_id', 'provider', 'first_fetched_at'], schema='predictions')
    op.create_index('idx_provider_forecast_snapshots_event', 'provider_forecast_snapshots',
                    ['provider', 'external_event_id'], schema='predictions')

    # Backfill: keep the evidence that already exists. content_hash is left NULL for these rows; the
    # service compares a new forecast against the latest snapshot's VALUES, so the first sync after
    # this migration recognises unchanged content and only moves last_fetched_at.
    #
    # There is deliberately no uniqueness on content_hash: a model that moves A -> B -> A must leave
    # three ordered snapshots, not two.
    op.execute("""
        INSERT INTO predictions.provider_forecast_snapshots (
            id, created_at, updated_at, match_id, provider, external_event_id, content_hash,
            home_win_prob, draw_prob, away_win_prob, btts_yes_prob, btts_no_prob,
            total_goals_over_25_prob, total_goals_under_25_prob,
            total_goals_over_35_prob, total_goals_under_35_prob,
            exact_score, exact_score_other_prob, recommended_bets, reasoning, confidence, anomalies,
            match_confidence, matched_by, model_run_at, provider_updated_at,
            first_fetched_at, last_fetched_at, kickoff_at_capture, captured_before_kickoff, raw_payload
        )
        SELECT
            gen_random_uuid(), now(), now(), f.match_id, f.provider, f.external_event_id,
            NULL,
            f.home_win_prob, f.draw_prob, f.away_win_prob, f.btts_yes_prob, f.btts_no_prob,
            f.total_goals_over_25_prob, f.total_goals_under_25_prob,
            f.total_goals_over_35_prob, f.total_goals_under_35_prob,
            f.exact_score, f.exact_score_other_prob, f.recommended_bets, f.reasoning, f.confidence, f.anomalies,
            f.match_confidence, f.matched_by, f.model_run_at, f.provider_updated_at,
            f.fetched_at, f.fetched_at, m.match_date, (f.fetched_at < m.match_date), f.raw_payload
        FROM predictions.provider_forecasts f
        JOIN predictions.matches m ON m.id = f.match_id
    """)


def downgrade() -> None:
    op.drop_index('idx_provider_forecast_snapshots_event', table_name='provider_forecast_snapshots', schema='predictions')
    op.drop_index('idx_provider_forecast_snapshots_match', table_name='provider_forecast_snapshots', schema='predictions')
    op.drop_table('provider_forecast_snapshots', schema='predictions')
    op.drop_column('provider_forecasts', 'anomalies', schema='predictions')
    op.drop_column('provider_forecasts', 'exact_score_other_prob', schema='predictions')
