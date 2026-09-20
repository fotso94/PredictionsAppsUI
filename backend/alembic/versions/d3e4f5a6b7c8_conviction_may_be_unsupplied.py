"""Let an unsupplied conviction stay unsupplied instead of being stored as zero

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-20 02:20:00.000000

predictions.confidence_score was NOT NULL, and the expert service coerced a missing conviction to
0.0000 on the way in. A prediction whose author left the field blank and a prediction whose author
deliberately rated it at nothing therefore became the same stored number, and the interface showed
both as "0%". That is an absence rendered as a figure - the same defect this codebase has already
fixed for snapshot prematch flags and for test-data classification. The column becomes nullable so
"nobody said" is a value the database can hold and the API can transmit.

prediction_overrides.new_confidence is widened for the same reason: it took the same coercion, so
the audit trail recorded "this expert rated their override at zero" for overrides that carried no
conviction at all.

EXISTING ZEROS ARE LEFT EXACTLY AS THEY ARE. At the time of writing this installation held 217
prediction rows, 26 of them at exactly zero and none null. Those 26 are genuinely ambiguous: some
were blank and coerced, some may be a real zero, and nothing stored can tell them apart. Rewriting
them to NULL would be inventing the very information the old coercion destroyed, so the upgrade
touches no row. From here on the two are distinguishable; behind here they are not, and that stays
visible rather than being papered over.

The range CHECK is restated with an explicit IS NULL arm. A CHECK is satisfied by NULL either way
(NULL >= 0 evaluates to NULL, and only FALSE violates a constraint), so this changes no behaviour -
it stops the constraint reading as though it still required a value, and matches the form the three
sibling confidence constraints on this table already use.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.NUMERIC(precision=5, scale=4)


def upgrade() -> None:
    op.alter_column(
        'predictions', 'confidence_score',
        existing_type=_NUMERIC, nullable=True,
        comment='Confidence score 0-1; NULL when the source supplied none',
        existing_comment='Confidence score 0-1',
        schema='predictions')

    op.drop_constraint('ck_predictions_confidence', 'predictions', schema='predictions', type_='check')
    op.create_check_constraint(
        'ck_predictions_confidence', 'predictions',
        'confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)',
        schema='predictions')

    op.alter_column(
        'prediction_overrides', 'new_confidence',
        existing_type=_NUMERIC, nullable=True,
        comment='Expert confidence; NULL when none was supplied',
        existing_comment='Expert confidence',
        schema='predictions')


def downgrade() -> None:
    # Going back re-imposes NOT NULL, which cannot be done without choosing a number for rows that
    # have none. Zero is the value the old code wrote, so it is the only honest way back - and it
    # is lossy in exactly the way that made this migration necessary. Nothing can recover the
    # distinction afterwards.
    op.execute("UPDATE predictions.prediction_overrides SET new_confidence = 0 WHERE new_confidence IS NULL")
    op.alter_column(
        'prediction_overrides', 'new_confidence',
        existing_type=_NUMERIC, nullable=False,
        comment='Expert confidence',
        existing_comment='Expert confidence; NULL when none was supplied',
        schema='predictions')

    op.drop_constraint('ck_predictions_confidence', 'predictions', schema='predictions', type_='check')
    op.create_check_constraint(
        'ck_predictions_confidence', 'predictions',
        'confidence_score >= 0 AND confidence_score <= 1',
        schema='predictions')

    op.execute("UPDATE predictions.predictions SET confidence_score = 0 WHERE confidence_score IS NULL")
    op.alter_column(
        'predictions', 'confidence_score',
        existing_type=_NUMERIC, nullable=False,
        comment='Confidence score 0-1',
        existing_comment='Confidence score 0-1; NULL when the source supplied none',
        schema='predictions')
