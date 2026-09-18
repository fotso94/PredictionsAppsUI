"""Make a prediction measurable: store the score, and the rule that produced it

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-09-18 11:30:00.000000

predictions.prediction_results existed as a table nothing ever wrote to, so no prediction on this
installation had ever been scored and no accuracy figure could honestly be published. This migration
makes scoring possible for both kinds of source and, just as importantly, makes a score readable:

1. predictions.prediction_results gains the rule and the evidence alongside the verdict -
   rules_version, market_results (per market: the rule applied, what was published, what happened),
   actual_outcome, probability_of_actual and brier_score. "Was it right?" is meaningless without
   them, and a rule that lives only in code cannot be checked against a score computed last season.

   match_result_id becomes NULLABLE. A postponed or cancelled fixture settles VOID and has no score
   to point at; forcing a result row would mean either inventing one or refusing to record that the
   prediction can never be scored.

2. predictions.provider_forecast_results is new: the score of a provider forecast. It is keyed to
   the SNAPSHOT (unique), not to the match and not to provider_forecasts, because the current
   forecast row is overwritten whenever the model changes its mind - including after kickoff.
   Scoring it would credit a provider with a forecast it never published before the match. Keying
   the score to the snapshot keeps the evidence and its score together forever.

   outcome is nullable here, unlike on prediction_results: a provider may publish BTTS without a
   1X2, and "the source published no 1X2" is not a loss. An expert prediction always carries all
   three outcome probabilities (the table's own CHECK constraint requires it), so its outcome stays
   NOT NULL.

The enum predictionoutcome already exists and is reused as-is (create_type=False).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Matches app.services.settlement.RULES_VERSION. Used only as a server default while the new NOT
#: NULL column is added; it is dropped again immediately so no future insert can inherit a rule
#: version it did not actually apply.
RULES_VERSION = 'soccer-regulation-time-v1'

_OUTCOME = postgresql.ENUM('PENDING', 'WON', 'LOST', 'VOID', 'PUSH', name='predictionoutcome',
                           create_type=False)


def upgrade() -> None:
    # ---- 1. prediction_results: the rule and the evidence, next to the verdict
    op.alter_column('prediction_results', 'match_result_id',
                    existing_type=postgresql.UUID(), nullable=True,
                    comment='Result that settled this prediction; NULL when the fixture was never played',
                    schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('actual_outcome', sa.String(length=10), nullable=True,
                            comment='home | draw | away in regulation time; NULL when not played'),
                  schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('probability_of_actual', sa.DECIMAL(5, 4), nullable=True,
                            comment="The probability the expert published for the outcome that occurred; "
                                    "never derived, NULL when they published none"),
                  schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('brier_score', sa.DECIMAL(6, 5), nullable=True,
                            comment='Three-way Brier score of the 1X2 probabilities (0 perfect, 2 worst); '
                                    'NULL when it cannot be computed without inventing numbers'),
                  schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('market_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                            comment='Per market: the rule applied, what was published, what happened, the outcome'),
                  schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('void_reason', sa.String(length=120), nullable=True,
                            comment='Why the prediction was voided rather than scored'),
                  schema='predictions')
    op.add_column('prediction_results',
                  sa.Column('rules_version', sa.String(length=50), nullable=False,
                            server_default=sa.text(f"'{RULES_VERSION}'"),
                            comment='Identifier of the settlement ruleset applied; '
                                    'see app/services/settlement.py'),
                  schema='predictions')
    # The default existed only to fill rows already in the table (there are none on this
    # installation). From here on the settlement service always states the version it applied.
    op.alter_column('prediction_results', 'rules_version', server_default=None, schema='predictions')

    # ---- 2. provider_forecast_results: the score of one PREMATCH snapshot
    op.create_table(
        'provider_forecast_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='Primary key (UUID)'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False,
                  comment='The prematch forecast that was scored'),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False,
                  comment='Copied from the snapshot so a source can be aggregated'),
        sa.Column('match_result_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Result that settled this forecast; NULL when the fixture was never played'),
        sa.Column('outcome', _OUTCOME, nullable=True,
                  comment='1X2 settlement; NULL when the source published no 1X2 for this fixture'),
        sa.Column('is_correct', sa.Boolean(), nullable=True,
                  comment='NULL when there was no single most likely outcome, or nothing to score'),
        sa.Column('actual_outcome', sa.String(length=10), nullable=True,
                  comment='home | draw | away in regulation time; NULL when not played'),
        sa.Column('probability_of_actual', sa.DECIMAL(5, 4), nullable=True,
                  comment='The probability the source itself published for the outcome that occurred; '
                          'never derived, NULL when it published none'),
        sa.Column('brier_score', sa.DECIMAL(6, 5), nullable=True,
                  comment='Three-way Brier score of the published 1X2 probabilities (0 perfect, 2 worst); '
                          'NULL when it cannot be computed without inventing numbers'),
        sa.Column('settled_at', sa.DateTime(), nullable=False, comment='When this score was computed (UTC)'),
        sa.Column('settled_by_system', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('rules_version', sa.String(length=50), nullable=False,
                  comment='Identifier of the settlement ruleset applied; see app/services/settlement.py'),
        sa.Column('market_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Per market: the rule applied, what was published, what happened, the outcome'),
        sa.Column('void_reason', sa.String(length=120), nullable=True,
                  comment='Why the forecast was voided rather than scored'),
        sa.Column('snapshot_captured_at', sa.DateTime(), nullable=True,
                  comment="first_fetched_at of the scored snapshot, copied so the evidence's age is "
                          'readable without a join'),
        sa.Column('kickoff_at', sa.DateTime(), nullable=True,
                  comment='Kickoff of the fixture (UTC), copied for range queries on measured periods'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['predictions.provider_forecast_snapshots.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['match_id'], ['predictions.matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['match_result_id'], ['predictions.match_results.id']),
        sa.PrimaryKeyConstraint('id'),
        # One score per snapshot: this is what makes re-running settlement idempotent rather than
        # additive. Without it a nightly run would multiply every provider's record by the number of
        # times it had been executed.
        sa.UniqueConstraint('snapshot_id', name='uq_provider_forecast_results_snapshot'),
        schema='predictions',
        comment='Scores of prematch provider forecasts, kept with the snapshot that was scored',
    )
    op.create_index('idx_provider_forecast_results_match', 'provider_forecast_results', ['match_id'],
                    unique=False, schema='predictions')
    op.create_index('idx_provider_forecast_results_provider_settled', 'provider_forecast_results',
                    ['provider', 'settled_at'], unique=False, schema='predictions')
    op.create_index('idx_provider_forecast_results_outcome', 'provider_forecast_results', ['outcome'],
                    unique=False, schema='predictions')


def downgrade() -> None:
    op.drop_index('idx_provider_forecast_results_outcome', table_name='provider_forecast_results',
                  schema='predictions')
    op.drop_index('idx_provider_forecast_results_provider_settled', table_name='provider_forecast_results',
                  schema='predictions')
    op.drop_index('idx_provider_forecast_results_match', table_name='provider_forecast_results',
                  schema='predictions')
    op.drop_table('provider_forecast_results', schema='predictions')

    op.drop_column('prediction_results', 'rules_version', schema='predictions')
    op.drop_column('prediction_results', 'void_reason', schema='predictions')
    op.drop_column('prediction_results', 'market_results', schema='predictions')
    op.drop_column('prediction_results', 'brier_score', schema='predictions')
    op.drop_column('prediction_results', 'probability_of_actual', schema='predictions')
    op.drop_column('prediction_results', 'actual_outcome', schema='predictions')

    # The pre-migration schema cannot represent a VOID settlement: it insists every score point at a
    # match result, and a postponed fixture has none. Those rows are removed so the NOT NULL can be
    # restored. They are recomputed in full by re-running settlement after a later upgrade - nothing
    # in them is a human judgement that could not be derived again from the stored evidence.
    op.execute('DELETE FROM predictions.prediction_results WHERE match_result_id IS NULL')
    op.alter_column('prediction_results', 'match_result_id',
                    existing_type=postgresql.UUID(), nullable=False, comment=None,
                    existing_comment='Result that settled this prediction; NULL when the fixture was never played',
                    schema='predictions')
