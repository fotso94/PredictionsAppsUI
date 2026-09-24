"""Store a tie's score periods separately so settlement can name the one it means

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-23 10:00:00.000000

predictions.match_results held one scoreline plus half time. A knockout tie has more than one, and
they are not interchangeable. Live Score API separates them and always has - `ht_score`, `ft_score`,
`et_score`, `ps_score` - and on 2026-07-07 it reported Switzerland 0-0 Colombia, 0-0 after extra
time, 4-3 on penalties. To a 1X2 market settled on regulation time that tie is a DRAW. To the
reader it is a Switzerland win. One pair of columns cannot be both, so the periods get their own.

Six nullable columns are added:

  home_score_ft / away_score_ft      regulation time, 90 minutes plus stoppage
  home_score_et / away_score_et      after extra time
  home_score_pens / away_score_pens  the penalty shoot-out

home_score / away_score keep their meaning and are not touched: the score of the football played,
extra time included, penalties never. Settlement reads the _ft pair and nothing else.

NO ROW IS REWRITTEN. At the time of writing this installation held 48 match_results rows, every one
of them carrying `{"provider": "livescore"}` and nothing more - no period marker of any kind was
ever stored, which is why settlement's own extra-time refusal had never once been able to fire. The
periods of those 48 are simply not known, and NULL is what "not known" looks like. Deriving _ft from
their stored home_score would assert that none of them went past 90 minutes, which is a claim this
migration has no evidence for. Settlement handles the NULLs explicitly: a row with no _ft pair and
nothing saying it went beyond regulation still settles on home_score exactly as it did before, so
the 48 and every club fixture behind them score identically after this runs.

Every column is nullable with no default and no constraint, so the upgrade rewrites no page and
cannot fail against existing data whatever it holds.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERIOD_COLUMNS = (
    ('home_score_ft', 'Regulation-time score: 90 minutes plus stoppage'),
    ('away_score_ft', 'Regulation-time score: 90 minutes plus stoppage'),
    ('home_score_et', 'Score after extra time'),
    ('away_score_et', 'Score after extra time'),
    ('home_score_pens', 'Penalty shoot-out score'),
    ('away_score_pens', 'Penalty shoot-out score'),
)


def upgrade() -> None:
    for name, comment in _PERIOD_COLUMNS:
        op.add_column('match_results',
                      sa.Column(name, sa.Integer(), nullable=True, comment=comment),
                      schema='predictions')


def downgrade() -> None:
    # Going back discards the periods. Nothing reconstructs them afterwards: the regulation score
    # of a tie that went to extra time is not recoverable from the score of the tie.
    for name, _comment in reversed(_PERIOD_COLUMNS):
        op.drop_column('match_results', name, schema='predictions')
