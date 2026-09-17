"""Add BTTS and Total Goals prediction fields

Revision ID: eb2ef2cf6caf
Revises: 2a4f8c9d1e3b
Create Date: 2025-10-16 01:36:40.626825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb2ef2cf6caf'
down_revision: Union[str, None] = '2a4f8c9d1e3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add Both Teams to Score (BTTS) and Total Goals prediction fields

    Changes:
    1. Add BTTS probability fields (yes/no must sum to 1.0)
    2. Add BTTS confidence field
    3. Add Total Goals probability fields (over/under for 2.5 and 3.5)
    4. Add Total Goals confidence field

    All fields are nullable for backward compatibility with existing predictions.
    """

    # 1. Add BTTS probability fields
    op.add_column(
        'predictions',
        sa.Column(
            'btts_yes_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability both teams score (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'btts_no_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability at least one team does not score (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'btts_confidence',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Confidence score for BTTS prediction (0-1)'
        ),
        schema='predictions'
    )

    # 2. Add Total Goals probability fields
    op.add_column(
        'predictions',
        sa.Column(
            'total_goals_over_25_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability of over 2.5 goals (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'total_goals_under_25_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability of under 2.5 goals (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'total_goals_over_35_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability of over 3.5 goals (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'total_goals_under_35_prob',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Probability of under 3.5 goals (0-1)'
        ),
        schema='predictions'
    )

    op.add_column(
        'predictions',
        sa.Column(
            'total_goals_confidence',
            sa.DECIMAL(5, 4),
            nullable=True,
            comment='Confidence score for total goals prediction (0-1)'
        ),
        schema='predictions'
    )

    # 3. Add check constraints for probability ranges (0-1)
    op.create_check_constraint(
        'ck_predictions_btts_yes_prob_range',
        'predictions',
        'btts_yes_prob IS NULL OR (btts_yes_prob >= 0 AND btts_yes_prob <= 1)',
        schema='predictions'
    )

    op.create_check_constraint(
        'ck_predictions_btts_no_prob_range',
        'predictions',
        'btts_no_prob IS NULL OR (btts_no_prob >= 0 AND btts_no_prob <= 1)',
        schema='predictions'
    )

    op.create_check_constraint(
        'ck_predictions_btts_confidence_range',
        'predictions',
        'btts_confidence IS NULL OR (btts_confidence >= 0 AND btts_confidence <= 1)',
        schema='predictions'
    )

    op.create_check_constraint(
        'ck_predictions_total_goals_confidence_range',
        'predictions',
        'total_goals_confidence IS NULL OR (total_goals_confidence >= 0 AND total_goals_confidence <= 1)',
        schema='predictions'
    )

    # 4. Add check constraint for BTTS probabilities sum (if both are provided)
    op.create_check_constraint(
        'ck_predictions_btts_prob_sum',
        'predictions',
        '(btts_yes_prob IS NULL AND btts_no_prob IS NULL) OR (btts_yes_prob + btts_no_prob BETWEEN 0.99 AND 1.01)',
        schema='predictions'
    )

    print("✅ BTTS and Total Goals prediction fields migration completed successfully")


def downgrade() -> None:
    """
    Remove BTTS and Total Goals prediction fields
    """

    # 1. Drop check constraints
    op.drop_constraint('ck_predictions_btts_prob_sum', 'predictions', schema='predictions')
    op.drop_constraint('ck_predictions_total_goals_confidence_range', 'predictions', schema='predictions')
    op.drop_constraint('ck_predictions_btts_confidence_range', 'predictions', schema='predictions')
    op.drop_constraint('ck_predictions_btts_no_prob_range', 'predictions', schema='predictions')
    op.drop_constraint('ck_predictions_btts_yes_prob_range', 'predictions', schema='predictions')

    # 2. Drop columns
    op.drop_column('predictions', 'total_goals_confidence', schema='predictions')
    op.drop_column('predictions', 'total_goals_under_35_prob', schema='predictions')
    op.drop_column('predictions', 'total_goals_over_35_prob', schema='predictions')
    op.drop_column('predictions', 'total_goals_under_25_prob', schema='predictions')
    op.drop_column('predictions', 'total_goals_over_25_prob', schema='predictions')
    op.drop_column('predictions', 'btts_confidence', schema='predictions')
    op.drop_column('predictions', 'btts_no_prob', schema='predictions')
    op.drop_column('predictions', 'btts_yes_prob', schema='predictions')

    print("✅ BTTS and Total Goals prediction fields rollback completed")

