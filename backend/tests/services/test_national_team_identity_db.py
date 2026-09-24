"""
Stored team identity: a country's men, a country's women and a club of the same name are three rows.

The acceptance case is Spain. Live Score writes the women's squad as "Spain (W)", and the club-name
matcher reads that as the same team as "Spain" - correctly, because dropping a trailing qualifier is
how "Ipswich" reaches "Ipswich Town". The competition's country cannot settle it either: a
national-team competition has no country, so the registry hands every FIFA competition the same
stand-in and both World Cups arrive with country "World". What separates them is the scope stored on
the row, and these tests are the guarantee that nothing can put two of them on one row.

Requires PostgreSQL (same pattern as tests/services/test_match_identity.py). Set TEST_DATABASE_URL
(default: the docker-compose test database); skipped when unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import Match, Team
from app.services.match_matching import team_names_match
from app.services.match_registry import MatchRegistry
from app.services.providers import competitions as comps
from app.services.providers.base import ProviderCompetition, ProviderFixture, ProviderTeam
from app.services.providers.competitions import TeamScope

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

KICKOFF = datetime(2026, 9, 23, 18, 45, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def engine():
    try:
        eng = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
        with eng.connect() as conn:
            for schema in ("users", "predictions", "ml_models", "analytics", "audit"):
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL test database not reachable: {exc}")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session joined to an outer transaction; nothing this module writes survives the test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def registry(db):
    return MatchRegistry(db)


# ----------------------------------------------------------------------------- helpers
def _slug(text_: str) -> str:
    return "".join(c for c in text_.lower() if c.isalnum())[:24]


def fixture_for(key: str, home: str, away: str, provider: str = "livescore",
                external_id: str = None, kickoff: datetime = KICKOFF) -> ProviderFixture:
    """A provider fixture in a registry competition, carrying that competition's own country."""
    canonical = comps.get(key)
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-{canonical.livescore_id or key}",
                               name=canonical.name, key=key, country=canonical.country,
                               country_code=canonical.country_code, is_cup=canonical.is_cup)
    return ProviderFixture(
        provider=provider, external_id=external_id or f"{key}-{_slug(home)}-{_slug(away)}",
        competition=comp,
        home=ProviderTeam(provider=provider, external_id=f"{provider}-{key}-{_slug(home)}", name=home),
        away=ProviderTeam(provider=provider, external_id=f"{provider}-{key}-{_slug(away)}", name=away),
        kickoff_utc=kickoff)


def stored(db, name: str) -> Team:
    return db.query(Team).filter(Team.name == name).one()


# ----------------------------------------------------------------------------- the acceptance case
def test_spain_men_spain_women_and_a_spanish_club_are_three_rows(db, registry):
    # One sync each, in the order that used to merge them: the men's row exists first, so the
    # women's fixture meets a stored "Spain" the name matcher is happy to call the same team.
    assert registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal")) is not None
    assert registry.upsert_fixture(fixture_for("womens_world_cup", "Spain (W)", "England (W)")) is not None
    assert registry.upsert_fixture(fixture_for("la_liga", "Spain", "Barcelona",
                                               kickoff=KICKOFF + timedelta(days=1))) is not None

    rows = db.query(Team).filter(Team.name.in_(["Spain", "Spain (W)"])).all()
    assert len(rows) == 3, [(r.name, r.team_scope) for r in rows]
    assert {r.team_scope for r in rows} == {
        TeamScope.NATIONAL_SENIOR_MEN.value, TeamScope.NATIONAL_SENIOR_WOMEN.value,
        TeamScope.CLUB_SENIOR_MEN.value}
    assert len({r.id for r in rows}) == 3
    assert len({r.identity_key for r in rows}) == 3


def test_the_womens_result_never_lands_on_the_mens_row(db, registry):
    # The single worst outcome this feature can produce, asserted against the stored match rows
    # rather than against the helper that computes the identity.
    mens = registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    womens = registry.upsert_fixture(fixture_for("womens_world_cup", "Spain (W)", "England (W)"))
    assert mens is not None and womens is not None
    assert mens.id != womens.id
    assert mens.home_team_id != womens.home_team_id
    assert stored(db, "Spain").team_scope == TeamScope.NATIONAL_SENIOR_MEN.value
    assert stored(db, "Spain (W)").team_scope == TeamScope.NATIONAL_SENIOR_WOMEN.value


def test_the_name_matcher_on_its_own_still_says_these_are_one_team(db, registry):
    # Not a defect asserted as correct: this is what the scope is protecting against, and it has to
    # stay true or the protection is testing nothing.
    assert team_names_match("Spain (W)", "Spain") is True
    registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    assert registry.find_team_by_name("Spain (W)", None, TeamScope.NATIONAL_SENIOR_MEN) is not None
    assert registry.find_team_by_name("Spain (W)", None, TeamScope.NATIONAL_SENIOR_WOMEN) is None


# ----------------------------------------------------------------------------- club vs national
def test_a_national_team_never_resolves_onto_a_club_row(db, registry):
    # Real collisions in the competitions this product already covers: AS Monaco plays Ligue 1 while
    # Monaco plays the national-team calendar, and FC Andorra is a Spanish club while Andorra is a
    # country. Both pairs normalise to one string.
    registry.upsert_fixture(fixture_for("ligue_1", "Monaco", "Lyon"))
    registry.upsert_fixture(fixture_for("national_teams_friendlies", "Monaco", "Andorra",
                                        kickoff=KICKOFF + timedelta(days=2)))
    monaco = db.query(Team).filter(Team.name == "Monaco").all()
    assert len(monaco) == 2
    assert {t.team_scope for t in monaco} == {
        TeamScope.CLUB_SENIOR_MEN.value, TeamScope.NATIONAL_SENIOR_MEN.value}
    assert {t.identity_key for t in monaco} == {"club_senior_men:monaco", "national_senior_men:monaco"}


def test_a_club_never_resolves_onto_a_national_team_row(db, registry):
    # The same guarantee in the other order, because the lookup that runs first is not the same one.
    registry.upsert_fixture(fixture_for("national_teams_friendlies", "Monaco", "Andorra"))
    registry.upsert_fixture(fixture_for("ligue_1", "Monaco", "Lyon", kickoff=KICKOFF + timedelta(days=2)))
    monaco = db.query(Team).filter(Team.name == "Monaco").all()
    assert len(monaco) == 2
    assert {t.team_scope for t in monaco} == {
        TeamScope.CLUB_SENIOR_MEN.value, TeamScope.NATIONAL_SENIOR_MEN.value}


def test_a_club_lookup_cannot_see_a_national_team_row_at_all(db, registry):
    registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    assert registry.find_team_by_name("Spain", None, TeamScope.CLUB_SENIOR_MEN) is None
    assert registry.find_team_by_name("Spain", None, TeamScope.NATIONAL_SENIOR_MEN) is not None
    # The default scope is the club one, so an unqualified caller asks about clubs.
    assert registry.find_team_by_name("Spain") is None


# ----------------------------------------------------------------------------- one squad, one row
def test_the_same_country_in_two_competitions_of_one_category_is_one_row(db, registry):
    # The women/men split must not be solved by splitting per competition.
    first = registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    second = registry.upsert_fixture(fixture_for("uefa_nations_league", "Spain", "France",
                                                 kickoff=KICKOFF + timedelta(days=3)))
    assert first is not None and second is not None
    assert first.home_team_id == second.home_team_id
    assert db.query(Team).filter(Team.name == "Spain").count() == 1


def test_one_womens_squad_across_two_competitions_is_one_row(db, registry):
    registry.upsert_fixture(fixture_for("womens_world_cup", "Spain (W)", "England (W)"))
    registry.upsert_fixture(fixture_for("national_teams_friendlies", "Spain (W)", "Germany (W)",
                                        kickoff=KICKOFF + timedelta(days=3)))
    assert db.query(Team).filter(Team.name == "Spain (W)").count() == 1
    assert stored(db, "Spain (W)").identity_key == "national_senior_women:spain"


def test_two_providers_spelling_one_national_team_share_its_row(db, registry):
    # The thing the registry exists for, inside a national-team competition: a second provider must
    # find the stored row by name rather than open a second one.
    first = registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    second = registry.upsert_fixture(
        fixture_for("fifa_world_cup", "Spain", "Portugal", provider="gameforecast"))
    assert first is not None and second is not None
    assert first.id == second.id
    assert db.query(Team).filter(Team.name == "Spain").count() == 1


# ----------------------------------------------------------------------------- stored columns
def test_a_confederations_territory_is_never_written_onto_a_team(db, registry):
    # "World" is the competition's stand-in country and it is not Spain's. Writing it would put
    # every country on earth into one of seven buckets.
    assert comps.get("fifa_world_cup").country == "World"
    registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    assert stored(db, "Spain").country == "Unknown"
    # A club competition's country is the club's, and still is.
    registry.upsert_fixture(fixture_for("la_liga", "Barcelona", "Sevilla",
                                        kickoff=KICKOFF + timedelta(days=1)))
    assert stored(db, "Barcelona").country == "Spain"


def test_every_row_the_registry_writes_carries_a_scope_and_a_matching_identity(db, registry):
    registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    registry.upsert_fixture(fixture_for("womens_world_cup", "Spain (W)", "England (W)"))
    registry.upsert_fixture(fixture_for("premier_league", "Arsenal", "Chelsea",
                                        kickoff=KICKOFF + timedelta(days=1)))
    for row in db.query(Team).all():
        assert row.team_scope, row.name
        assert row.identity_key, row.name
        assert row.identity_key.startswith(f"{row.team_scope}:"), row.name


def test_a_fixture_in_a_competition_the_registry_does_not_carry_stores_a_club(db, registry):
    # `key=None` is the provider saying no canonical key matched its competition.
    comp = ProviderCompetition(provider="livescore", external_id="ls-999", name="Some Other League",
                               key=None, country="Portugal")
    fixture = ProviderFixture(
        provider="livescore", external_id="9999", competition=comp,
        home=ProviderTeam(provider="livescore", external_id="ls-porto", name="Porto"),
        away=ProviderTeam(provider="livescore", external_id="ls-benfica", name="Benfica"),
        kickoff_utc=KICKOFF)
    assert registry.upsert_fixture(fixture) is not None
    assert stored(db, "Porto").team_scope == comps.DEFAULT_TEAM_SCOPE.value


# ----------------------------------------------------------------------------- the database refuses
def test_the_database_refuses_a_second_row_for_one_identity(db, registry):
    from sqlalchemy.exc import IntegrityError

    registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    spain = stored(db, "Spain")
    db.add(Team(id=uuid.uuid4(), name="Spain", short_name="Spain", country="Unknown", is_active=True,
                team_scope=spain.team_scope, identity_key=spain.identity_key))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_legacy_row_with_no_identity_is_adopted_rather_than_duplicated(db, registry):
    # Rows written before this column existed, and by paths that never knew the competition, carry
    # NULL. They are still found by name inside their scope, and the lookup writes the key it
    # resolved them under so the next one reaches them directly.
    legacy = Team(id=uuid.uuid4(), name="Arsenal", short_name="Arsenal", country="England",
                  is_active=True)
    db.add(legacy)
    db.flush()
    assert legacy.identity_key is None
    assert legacy.team_scope == comps.DEFAULT_TEAM_SCOPE.value

    registry.upsert_fixture(fixture_for("premier_league", "Arsenal", "Chelsea"))
    assert db.query(Team).filter(Team.name == "Arsenal").count() == 1
    db.refresh(legacy)
    assert legacy.identity_key == "club_senior_men:arsenal"


def test_a_country_the_caller_passed_cannot_hide_the_row_holding_the_identity(db, registry):
    """The identity decides before the country does, and that is what keeps a sync alive.

    `identity_key` is UNIQUE and already carries the scope, so a row holding it IS this team. A
    country cannot add to that and can take it away: the country in hand is the one THIS provider
    spells, and a row stored from another provider may spell it differently or not at all. Were the
    country filter to run first it would hide the holder, the caller would resolve onto some other
    row - or create one - and the write claiming the same identity would abort the whole sync batch
    rather than merely storing a duplicate.
    """
    holder = Team(id=uuid.uuid4(), name="Arsenal", short_name="Arsenal", country="England",
                  is_active=True, team_scope=TeamScope.CLUB_SENIOR_MEN.value,
                  identity_key="club_senior_men:arsenal")
    legacy = Team(id=uuid.uuid4(), name="Arsenal", short_name="Arsenal", country="Unknown",
                  is_active=True)
    db.add_all([holder, legacy])
    db.flush()

    # "Spain" matches neither row's country, and the holder is still the answer.
    assert registry.find_team_by_name("Arsenal", "Spain", TeamScope.CLUB_SENIOR_MEN).id == holder.id
    resolved = registry.upsert_team(
        ProviderTeam(provider="livescore", external_id="ls-arsenal-es", name="Arsenal", country="Spain"),
        "Spain", "la_liga")
    db.flush()
    assert resolved.id == holder.id
    # The legacy row is left exactly as it was: nothing adopted an identity it could not hold.
    assert legacy.identity_key is None
    assert db.query(Team).filter(Team.identity_key == "club_senior_men:arsenal").count() == 1


def test_two_rows_spelling_one_club_never_end_up_holding_one_identity(db, registry):
    # "Ipswich" and "Ipswich Town" normalise to the same string; a database that already holds both
    # is the state `scripts/repair_duplicate_matches.py` exists for. The key goes to one of them.
    registry.upsert_fixture(fixture_for("premier_league", "Ipswich Town", "Chelsea"))
    assert stored(db, "Ipswich Town").identity_key == "club_senior_men:ipswich town"
    legacy = Team(id=uuid.uuid4(), name="Ipswich", short_name="Ipswich", country="England",
                  is_active=True)
    db.add(legacy)
    db.flush()

    registry.upsert_fixture(fixture_for("premier_league", "Ipswich", "Everton",
                                        kickoff=KICKOFF + timedelta(days=1)))
    db.flush()
    assert legacy.identity_key is None
    assert db.query(Team).filter(Team.identity_key == "club_senior_men:ipswich town").count() == 1


# ----------------------------------------------------------------------------- schema defaults
def test_the_migration_default_is_the_registrys_default_scope():
    # The migration spells 'club_senior_men' as a literal so it reads without the registry. This is
    # what stops that literal and `TeamScope` drifting apart, and it is the value every row already
    # in the table was given.
    import importlib.util
    from pathlib import Path

    path = (Path(__file__).resolve().parents[1].parent / "alembic" / "versions"
            / "f7a8b9c0d1e2_a_team_row_carries_its_own_squad.py")
    spec = importlib.util.spec_from_file_location("migration_f7a8b9c0d1e2", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.CLUB_SENIOR_MEN == comps.DEFAULT_TEAM_SCOPE.value
    assert migration.down_revision == "e4f5a6b7c8d9"
    assert Team.__table__.c.team_scope.server_default.arg == comps.DEFAULT_TEAM_SCOPE.value
    assert Team.__table__.c.team_scope.nullable is False
    assert Team.__table__.c.identity_key.nullable is True


# ----------------------------------------------------------------------------- the competition too
def test_a_friendly_is_stored_with_the_classification_the_provider_gives_it(db, registry):
    # Live Score publishes competition 371 as is_cup "1", and as `is_cup: true, is_league: false`
    # inside each of its own fixture rows (read 2026-09-23). league_metadata is what the matches API
    # serves, so it carries the provider's answer and not an impression of what a friendly is.
    match = registry.upsert_fixture(fixture_for("national_teams_friendlies", "Azerbaijan", "Tajikistan"))
    assert match is not None
    league = registry.ensure_canonical_league("national_teams_friendlies")
    assert match.league_id == league.id
    assert league.league_metadata["is_cup"] is True
    assert league.league_metadata["canonical_key"] == "national_teams_friendlies"


def test_a_mens_and_a_womens_world_cup_fixture_are_two_matches_in_two_leagues(db, registry):
    mens = registry.upsert_fixture(fixture_for("fifa_world_cup", "Spain", "Portugal"))
    womens = registry.upsert_fixture(fixture_for("womens_world_cup", "Spain (W)", "England (W)"))
    assert mens.league_id != womens.league_id
    assert db.query(Match).count() == 2


# ------------------------------------------------- a match that was not played has no score
#
# `_apply_fixture` merges scores forward deliberately: a provider that sends none must not erase
# the ones another already gave us. The cost of that rule is that a score can never be un-stored,
# and an abandoned or postponed fixture carries whatever it had reached while it was live. Nothing
# a later sync does takes it back, so the fixture is published as "postponed" beside a score that
# stands for nothing.

def _void_fixture(status, home_score=None, away_score=None, minute=None):
    return ProviderFixture(
        provider="livescore", external_id="void-regression",
        competition=ProviderCompetition(provider="livescore", external_id="2",
                                        name="Premier League", key="premier_league"),
        home=ProviderTeam(provider="livescore", external_id="vh", name="Void Home"),
        away=ProviderTeam(provider="livescore", external_id="va", name="Void Away"),
        kickoff_utc=datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc),
        status=status, home_score=home_score, away_score=away_score, minute=minute)


@pytest.mark.parametrize("void_status", ["postponed", "cancelled"])
def test_a_fixture_abandoned_after_kickoff_stops_showing_the_score_it_reached(db, registry, void_status):
    from app.schemas.matches import serialize_match
    from app.models.predictions import League

    live = registry.upsert_fixture(_void_fixture("live", 1, 0, "62"))
    db.flush()
    assert (live.match_metadata or {}).get("home_score") == 1, "the score never reached the store"

    voided = registry.upsert_fixture(_void_fixture(void_status))
    db.flush()
    db.refresh(voided)
    meta = voided.match_metadata or {}

    assert meta.get("home_score") is None and meta.get("away_score") is None, (
        f"a {void_status} fixture kept the score it had while live: "
        f"{meta.get('home_score')}-{meta.get('away_score')}")
    assert not (meta.get("scoreline") or ""), f"a stale scoreline survived: {meta.get('scoreline')!r}"

    # And the same through the serializer the API answers with, because the store being clean is
    # only half of it - the reader is who must not be shown the number.
    teams = {t.id: t for t in db.query(Team).filter(
        Team.id.in_([voided.home_team_id, voided.away_team_id])).all()}
    league = db.query(League).filter(League.id == voided.league_id).first()
    served = serialize_match(voided, teams, {league.id: league} if league else {}, None)
    score = served.get("score") or {}
    assert score.get("home") is None and score.get("away") is None, served.get("score")


def test_a_played_fixture_keeps_its_score_through_the_same_path(db, registry):
    """The guard above must not be a rule that quietly deletes real results."""
    registry.upsert_fixture(_void_fixture("live", 2, 1, "80"))
    db.flush()
    finished = registry.upsert_fixture(_void_fixture("finished", 2, 1))
    db.flush()
    db.refresh(finished)
    meta = finished.match_metadata or {}
    assert (meta.get("home_score"), meta.get("away_score")) == (2, 1)
