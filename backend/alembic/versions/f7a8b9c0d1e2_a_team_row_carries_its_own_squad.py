"""A team row carries its own squad, so two squads of one country cannot share it

Revision ID: f7a8b9c0d1e2
Revises: e4f5a6b7c8d9
Create Date: 2026-09-23 14:00:00.000000

predictions.teams identified a team by name and country. Neither separates a national team from
another national team of the same country: a national-team competition has no country, so the
registry hands every FIFA competition the same stand-in ("World"), and Live Score writes the
women's squad as "Spain (W)" - a suffix every club-name matcher is built to discard. Spain's men,
Spain's women and a Spanish club could therefore land on one row, which puts a women's result on a
men's team.

Two columns are added:

  team_scope    club-or-country plus squad category ('club_senior_men', 'national_senior_women', ...)
  identity_key  that scope, a colon, and the normalised name without the '(W)' suffix, UNIQUE

team_scope is NOT NULL with server default 'club_senior_men'. That default is not a convenience: at
the time of writing this installation held 98 team rows, 96 of them reached from matches in the five
domestic club leagues and the other two the "Home Team (TBD)"/"Away Team (TBD)" placeholders. Every
one is a club, and PostgreSQL fills a defaulted NOT NULL column from catalogue metadata without
rewriting a page.

identity_key is nullable and back-filled here for rows whose key can be computed and is unique
inside the table; a row whose key would duplicate another's is left NULL and named in the log
rather than merged, because this migration has no way to know which of two rows is the right one.
Those 98 names were checked before writing this and collide zero times, so the back-fill is
expected to reach all of them - but the check is done at run time, so the UNIQUE index that follows
cannot fail whatever the table holds when it runs.

Nothing else is touched: no row's name, country or id changes, no match is repointed, and the 48
stored matches keep the same two team ids they had before.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

#: The scope every row already in the table belongs to, and the only one this schema had a way to
#: store before now. Kept as a literal so the migration is readable without importing the registry;
#: `test_the_migration_default_is_the_registrys_default_scope` holds it to `TeamScope`.
CLUB_SENIOR_MEN = 'club_senior_men'


def _identity_keys(rows) -> dict:
    """
    id -> identity key, for the rows that can have one and are the only claimant to it.

    The normalisation has to be the application's own - "Borussia Moenchengladbach" normalises to
    "monchengladbach", which no SQL expression reproduces - so it is imported rather than rewritten
    here. A key claimed by more than one row is given to none of them.
    """
    from app.services.match_matching import normalize_team_name
    from app.services.providers.competitions import scoped_identity_key, strip_womens_suffix, TeamScope

    scope = TeamScope(CLUB_SENIOR_MEN)
    keys = {}
    for row in rows:
        normalised = normalize_team_name(strip_womens_suffix(row.name))
        if normalised:
            keys[row.id] = scoped_identity_key(scope, normalised)
    counts = {}
    for key in keys.values():
        counts[key] = counts.get(key, 0) + 1
    contested = {team_id: key for team_id, key in keys.items() if counts[key] > 1}
    for team_id, key in contested.items():
        logger.warning("teams.identity_key left NULL for %s: %r is claimed by %s rows",
                       team_id, key, counts[key])
        del keys[team_id]
    return keys


def upgrade() -> None:
    op.add_column('teams',
                  sa.Column('team_scope', sa.String(length=32), nullable=False,
                            server_default=CLUB_SENIOR_MEN,
                            comment='TeamScope value: club/national and squad category'),
                  schema='predictions')
    op.add_column('teams',
                  sa.Column('identity_key', sa.String(length=300), nullable=True,
                            comment='Scope-prefixed normalised team name; unique across all teams'),
                  schema='predictions')

    bind = op.get_bind()
    rows = bind.execute(sa.text('SELECT id, name FROM predictions.teams')).fetchall()
    keys = _identity_keys(rows)
    for team_id, key in keys.items():
        bind.execute(sa.text('UPDATE predictions.teams SET identity_key = :key WHERE id = :id'),
                     {'key': key, 'id': team_id})
    logger.info("teams.identity_key back-filled for %s of %s rows", len(keys), len(rows))

    op.create_index('idx_teams_team_scope', 'teams', ['team_scope'], schema='predictions')
    op.create_index('uq_teams_identity_key', 'teams', ['identity_key'], unique=True,
                    schema='predictions')


def downgrade() -> None:
    op.drop_index('uq_teams_identity_key', table_name='teams', schema='predictions')
    op.drop_index('idx_teams_team_scope', table_name='teams', schema='predictions')
    op.drop_column('teams', 'identity_key', schema='predictions')
    op.drop_column('teams', 'team_scope', schema='predictions')
