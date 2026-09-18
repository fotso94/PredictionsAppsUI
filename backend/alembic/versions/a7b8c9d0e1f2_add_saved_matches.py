"""Add users.saved_matches: a user's saved fixtures with their own private note

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-18 09:10:00.000000

Followed teams and leagues stay where they already are, in the user_preferences JSONB columns: a
follow is a bare id and nothing else. A saved fixture is not that. It carries the moment it was saved
and the owner's note, it is read by joining to predictions.matches and ordering by kickoff, and it
wants a per-row uniqueness rule so saving twice is a no-op rather than a duplicate. That is a table.

Both foreign keys cascade on delete, so a removed fixture or a removed account takes its saves with
it instead of leaving rows pointing at nothing.

note holds text the user wrote for themselves. No query outside the owner's own endpoints reads it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_matches',
        sa.Column('user_id', sa.UUID(), nullable=False, comment='Owner of this save'),
        sa.Column('match_id', sa.UUID(), nullable=False, comment='Saved fixture'),
        sa.Column('note', sa.Text(), nullable=True,
                  comment="The owner's private note; never returned to another user"),
        sa.Column('id', sa.UUID(), nullable=False, comment='Primary key (UUID)'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='Record last update timestamp'),
        sa.ForeignKeyConstraint(['match_id'], ['predictions.matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'match_id', name='uq_saved_matches_user_match'),
        schema='users',
        comment="Matches a user saved, with that user's own private note",
    )
    op.create_index('idx_saved_matches_user_id_created_at', 'saved_matches', ['user_id', 'created_at'],
                    unique=False, schema='users')
    op.create_index('idx_saved_matches_match_id', 'saved_matches', ['match_id'], unique=False, schema='users')


def downgrade() -> None:
    # Dropping the table drops the notes with it: there is nowhere else to put them, and leaving an
    # orphaned copy of private text behind would be worse than losing it.
    op.drop_index('idx_saved_matches_match_id', table_name='saved_matches', schema='users')
    op.drop_index('idx_saved_matches_user_id_created_at', table_name='saved_matches', schema='users')
    op.drop_table('saved_matches', schema='users')
