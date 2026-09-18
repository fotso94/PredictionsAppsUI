"""Keep the prematch record: an unpublish time, and an explicit test-data classification

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-18 23:05:00.000000

Two columns on predictions.predictions, both answering "what did this expert actually have
standing when the match kicked off?".

1. unpublished_at. Unpublishing a prediction (PUBLISHED -> ARCHIVED) used to write
   ``published_at = NULL``. That is the only place in the system where a prematch fact was
   destroyed rather than merely filtered out: once the publication time is gone, nothing can show
   that the prediction predated kickoff, so an unpublish/republish round trip after the result made
   a losing prediction permanently unscoreable. From here published_at is written once and never
   cleared, and the moment of the unpublish is recorded in its own column. The pair is what makes
   "was a reader seeing this at kickoff?" answerable afterwards.

2. is_test_data. The QA harness marked its records by writing "[e2e-qa]" into the reasoning field,
   which is free-form text a user controls: the moment such a marker influenced scoring, an expert
   could exclude their own losses by typing nine characters. This column is the explicit
   replacement - per record (not per account: the QA account also holds hand-typed records that
   must NOT be swept up), set server-side only, and only while
   ``settings.ALLOW_TEST_DATA_CLASSIFICATION`` is on, which is off by default and therefore off in
   any normal deployment.

   NULL means unclassified. That is deliberately different from FALSE: "nobody has said" is not the
   same claim as "this is genuine", and the honest state for an existing row is the former.

Both columns are nullable with no server default, so this migration rewrites no row and no existing
record acquires a classification by being migrated. The historical QA rows are classified by
backend/scripts/classify_test_predictions.py, which is run deliberately and reports what it matched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'predictions',
        sa.Column('unpublished_at', sa.DateTime(), nullable=True,
                  comment='When the prediction was last unpublished (archived); NULL while live'),
        schema='predictions')
    op.add_column(
        'predictions',
        sa.Column('is_test_data', sa.Boolean(), nullable=True,
                  comment='TRUE when this record is deliberately classified as test data; NULL '
                          'means unclassified. Never derived from the reasoning text'),
        schema='predictions')
    # Measured performance filters on this column on every settlement pass and every read of
    # /performance/sources. Partial, because the rows that matter are the flagged minority.
    op.create_index('idx_predictions_is_test_data', 'predictions', ['is_test_data'],
                    unique=False, schema='predictions',
                    postgresql_where=sa.text('is_test_data IS TRUE'))


def downgrade() -> None:
    op.drop_index('idx_predictions_is_test_data', table_name='predictions', schema='predictions')
    op.drop_column('predictions', 'is_test_data', schema='predictions')
    op.drop_column('predictions', 'unpublished_at', schema='predictions')
