"""Allow "kickoff unknown" on forecast snapshots instead of asserting "not prematch"

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-18 04:05:00.000000

captured_before_kickoff was NOT NULL defaulting to false, so a snapshot captured when the fixture's
kickoff was not yet known would be stored as "this was not a prematch forecast" - a claim we cannot
make from the evidence. The column becomes nullable: NULL means the kickoff was unknown at capture,
and only a real comparison against a known kickoff sets true or false.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('provider_forecast_snapshots', 'captured_before_kickoff',
                    existing_type=sa.Boolean(), nullable=True, server_default=None,
                    comment='True/false only when the kickoff was known at capture; NULL when it was not',
                    schema='predictions')


def downgrade() -> None:
    op.execute("UPDATE predictions.provider_forecast_snapshots "
               "SET captured_before_kickoff = false WHERE captured_before_kickoff IS NULL")
    op.alter_column('provider_forecast_snapshots', 'captured_before_kickoff',
                    existing_type=sa.Boolean(), nullable=False, server_default=sa.text('false'),
                    schema='predictions')
