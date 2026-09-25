"""Selection slips: a reader's own combinations of forecast selections, and what became of them

Revision ID: b7c8d9e0f1a2
Revises: f7a8b9c0d1e2
Create Date: 2026-09-25 19:40:00.000000

Two new tables in the ``users`` schema (see app/models/slips.py for the reasoning behind every
column). Nothing existing is altered and no row is rewritten.

- users.selection_slips       the combination: draft, saved, or recorded as placed elsewhere.
- users.selection_slip_legs   one selection per fixture, UNIQUE(slip_id, match_id), each carrying
                              the probability, snapshot and times it was taken from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'selection_slips',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('stake_minor', sa.BigInteger(), nullable=True),
        sa.Column('price', sa.DECIMAL(precision=12, scale=4), nullable=True),
        sa.Column('price_source', sa.String(length=20), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('recorded_reference', sa.String(length=120), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        schema='users',
        comment="A reader's own combination of forecast selections; private to its author",
    )
    op.create_index('idx_selection_slips_user_status', 'selection_slips', ['user_id', 'status', 'updated_at'], schema='users')

    op.create_table(
        'selection_slip_legs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('slip_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.selection_slips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('predictions.matches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('predictions.provider_forecast_snapshots.id', ondelete='SET NULL'), nullable=True),
        sa.Column('market_id', sa.String(length=40), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('line', sa.DECIMAL(precision=4, scale=2), nullable=True),
        sa.Column('period', sa.String(length=20), nullable=False),
        sa.Column('probability', sa.DECIMAL(precision=6, scale=5), nullable=True),
        sa.Column('probability_source', sa.String(length=20), nullable=False),
        sa.Column('calculation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model_run_at', sa.DateTime(), nullable=True),
        sa.Column('forecast_fetched_at', sa.DateTime(), nullable=True),
        sa.Column('normalisation_version', sa.String(length=20), nullable=False),
        sa.Column('odds_value', sa.DECIMAL(precision=10, scale=4), nullable=True),
        sa.Column('odds_source', sa.String(length=20), nullable=True),
        sa.Column('odds_captured_at', sa.DateTime(), nullable=True),
        sa.Column('kickoff_at_add', sa.DateTime(), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
        sa.Column('settlement', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('slip_id', 'match_id', name='uq_selection_slip_legs_slip_match'),
        schema='users',
        comment='One selection on one fixture inside a slip',
    )
    op.create_index('idx_selection_slip_legs_match', 'selection_slip_legs', ['match_id'], schema='users')
    op.create_index('idx_selection_slip_legs_state', 'selection_slip_legs', ['state'], schema='users')


def downgrade() -> None:
    op.drop_index('idx_selection_slip_legs_state', table_name='selection_slip_legs', schema='users')
    op.drop_index('idx_selection_slip_legs_match', table_name='selection_slip_legs', schema='users')
    op.drop_table('selection_slip_legs', schema='users')
    op.drop_index('idx_selection_slips_user_status', table_name='selection_slips', schema='users')
    op.drop_table('selection_slips', schema='users')
