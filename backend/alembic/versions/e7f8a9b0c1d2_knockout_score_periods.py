"""Store the period breakdown of a result so knockout ties settle on regulation time

A knockout tie that was 1-1 after 90 minutes and 2-1 after extra time was stored as a single
2-1 scoreline, and settled as a 2-1 home win on markets whose published rule is regulation time
only. The score after 90 minutes was never written down, so there was nothing to settle on and
nothing to go back to.

These six columns hold the periods a provider supplies: `_ft` is the score after 90 minutes --
the pair settlement now reads -- and `_et` / `_pens` record that the tie went past 90 so a result
with no `_ft` can be withheld rather than guessed at.

Nullable with no backfill, deliberately: NULL means "this provider told us nothing about the
periods", which is the truth for every row already stored and for every result from a provider
that supplies no breakdown. Inventing an `_ft` equal to the stored score would re-create the bug
as data.

Revision ID: e7f8a9b0c1d2
Revises: d3e4f5a6b7c8
Create Date: 2026-09-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ('home_score_ft', 'Score after 90 minutes (regulation time)'),
    ('away_score_ft', 'Score after 90 minutes (regulation time)'),
    ('home_score_et', 'Score at the end of extra time, as reported'),
    ('away_score_et', 'Score at the end of extra time, as reported'),
    ('home_score_pens', 'Penalty shootout score'),
    ('away_score_pens', 'Penalty shootout score'),
)


def upgrade() -> None:
    for name, comment in _COLUMNS:
        op.add_column('match_results', sa.Column(name, sa.Integer(), nullable=True, comment=comment),
                      schema='predictions')


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column('match_results', name, schema='predictions')
