"""
One fixture, one row: what the registry may conclude from a shared kickoff, and what it may not.

The cases here come from an incident recorded against the real database on 2026-09-19. Live Score
API calls a club "Ipswich Town" and API-Football calls it "Ipswich"; the club sat in two Team rows,
the names in the away slot never met, and Everton v Ipswich occupied two match rows, one of them
reading LIVE at minute 62 for two days with seven expert predictions on it.

Three rules answer that, and each has a boundary this file pins:

* the curated alias table, where "Ipswich" -> "Ipswich Town" is one line a person wrote, is what
  makes the two spellings one club at all;
* club identity by ROW: a stored fixture in the same competition at the same kickoff carrying the
  identical clubs in BOTH slots is this game, whatever either provider spells them. One club row
  in one slot and a different club in the other is a contradiction between two records, not an
  invitation to merge the clubs -- the same shape merges Manchester United with Manchester City,
  and a merge re-points the provider's team id, so it is permanent;
* a fixture nothing can be reconciled with is still stored. The contradiction is recorded on the
  row for `scripts/repair_duplicate_matches.py`, because withholding it would let one stored row
  veto a real fixture at that kickoff on every sync for ever.

The sweep at the foot of the file is the other half of the incident: the live poll only looks at
today and the results task only looks back `SYNC_RESULTS_LOOKBACK_DAYS` days, so a fixture behind
that is never asked about again. A bounded sweep reopens those days and gives up in writing rather
than re-asking for ever.

Requires PostgreSQL (same pattern as tests/services/test_match_identity.py). Set
TEST_DATABASE_URL; skipped when unreachable.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    League, Match, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.users import AccountStatus, User, UserType
from app.services import match_matching
from app.services.match_registry import STALE_SWEEP_MAX_AGE, UNSETTLED_GRACE, MatchRegistry
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_LIVE, STATUS_SCHEDULED, ProviderCompetition, ProviderFixture, ProviderTeam,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

#: The real fixture, to the minute.
KICKOFF = datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc)
#: The two spellings the production database actually holds for one club.
IPSWICH_LS, IPSWICH_AF = "Ipswich Town", "Ipswich"


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


@pytest.fixture(scope="module")
def repair_script():
    """`scripts/repair_duplicate_matches.py`, loaded by path because `scripts/` is not a package."""
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "repair_duplicate_matches", os.path.join(backend, "scripts", "repair_duplicate_matches.py"))
    module = importlib.util.module_from_spec(spec)
    # `dataclass` resolves string annotations through `sys.modules[cls.__module__]`, so the module
    # has to be registered before its body runs, not after.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_ipswich_alias(monkeypatch):
    """
    Drop the club alias, so the names are those of a spelling nobody has listed yet.

    The alias table answers the spellings already met, and with "Ipswich" in it these tests would
    only ever exercise that one line. Every future provider name change arrives unlisted, so this
    is the state the rest of the registry has to behave correctly in.
    """
    monkeypatch.delitem(match_matching._ALIASES, "ipswich", raising=False)
    assert not match_matching.team_names_match(IPSWICH_AF, IPSWICH_LS)


# ----------------------------------------------------------------------------- helpers
def provider_team_id(provider: str, name: str) -> str:
    """The id a provider is taken to use for a club here: stable, and derived from its spelling."""
    return f"{provider}-" + "".join(c for c in name.lower() if c.isalnum())[:24]


def fixture_for(provider: str, external_id: str, home: str, away: str, kickoff=KICKOFF,
                key="premier_league", status=STATUS_SCHEDULED, home_id=None, away_id=None,
                **scores) -> ProviderFixture:
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-{key}",
                               name=key.replace("_", " ").title(), key=key,
                               country="England", country_code="ENG")
    return ProviderFixture(
        provider=provider, external_id=external_id, competition=comp,
        home=ProviderTeam(provider=provider, external_id=home_id or provider_team_id(provider, home), name=home),
        away=ProviderTeam(provider=provider, external_id=away_id or provider_team_id(provider, away), name=away),
        kickoff_utc=kickoff, status=status, **scores)


def stored_pair(registry, *, away_name=IPSWICH_LS, status=STATUS_FINISHED, kickoff=KICKOFF):
    """The Live Score API copy, stored first and correctly, exactly as production holds it."""
    match = registry.upsert_fixture(fixture_for("livescore", "1877297", "Everton", away_name,
                                                kickoff=kickoff, status=status,
                                                home_score=1, away_score=1))
    assert match is not None
    return match


def expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"dupe-{suffix}@test.local", username=f"dupe_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def publish(db, match: Match, user: User) -> Prediction:
    row = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                     created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                     away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                     status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                     priority_level=100, reasoning="expert view")
    db.add(row)
    db.flush()
    return row


def refs_by_provider(registry, entity_type: str, entity_id):
    return {r.provider: r for r in registry.refs_for(entity_type, entity_id)}


def link_clubs(registry, match: Match, provider: str,
               home_name: str = "Everton", away_name: str = IPSWICH_AF) -> None:
    """
    Point `provider`'s team ids at the clubs the stored match already uses.

    This is the state a club is in once `scripts/repair_duplicate_matches.py` has folded its
    duplicate row, and the state any second provider reaches once its team ids have been resolved
    to the stored clubs. The names given are that provider's OWN spellings, so the ids written
    here are the ones its fixtures will carry.
    """
    registry.set_ref("team", match.home_team_id, provider, provider_team_id(provider, home_name),
                     confidence="manual", matched_by="repair")
    registry.set_ref("team", match.away_team_id, provider, provider_team_id(provider, away_name),
                     confidence="manual", matched_by="repair")


# =========================================================== the shape that must be joined
def test_one_fixture_under_two_spellings_is_one_row_once_the_clubs_are_one_row(db, registry, no_ipswich_alias):
    """
    The recorded incident, at the point the club repair leaves it: one club, two spellings.

    Both providers now resolve the away club to the SAME Team row, so the fixtures agree on club
    identity even though the names never will. That is what identifies the game here: `find_match`
    still sees "Ipswich" against "Ipswich Town" and reports nothing.
    """
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    assert not match_matching.team_names_match(IPSWICH_AF, IPSWICH_LS)
    before = db.query(Match).count()

    joined = registry.upsert_fixture(
        fixture_for("api_football", "1557410", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert joined is not None and joined.id == stored.id, "the second provider must land on the stored match"
    assert db.query(Match).count() == before, "no second row for one fixture"
    assert registry.take_refusals() == []
    assert "shared_slot_conflict" not in (joined.match_metadata or {})
    ref = refs_by_provider(registry, "match", stored.id)["api_football"]
    assert ref.matched_by == "shared_slot_identity" and ref.match_confidence == "high"


def test_a_finished_match_is_not_dragged_back_to_live_by_the_join(db, registry, no_ipswich_alias):
    """The visible symptom of the incident: the second copy read LIVE at minute 62 for two days."""
    stored = stored_pair(registry, status=STATUS_FINISHED)
    link_clubs(registry, stored, "api_football")

    joined = registry.upsert_fixture(
        fixture_for("api_football", "1557410", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert joined is not None and joined.id == stored.id
    assert joined.status == MatchStatus.FINISHED


def test_an_expert_prediction_stays_on_the_one_surviving_fixture(db, registry, no_ipswich_alias):
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    prediction = publish(db, stored, expert(db))

    registry.upsert_fixture(fixture_for("api_football", "1557410", "Everton", IPSWICH_AF,
                                        status=STATUS_LIVE))

    assert db.query(Prediction).filter(Prediction.match_id == stored.id).one().id == prediction.id
    assert db.query(Prediction).count() == 1


def test_the_join_survives_a_second_pass_unchanged(db, registry, no_ipswich_alias):
    """Once the fixture is joined the provider has a ref, so later passes are ordinary lookups."""
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    first = registry.upsert_fixture(fixture_for("api_football", "1557410", "Everton", IPSWICH_AF,
                                                status=STATUS_LIVE))
    before = db.query(Match).count()

    again = registry.upsert_fixture(fixture_for("api_football", "1557410", "Everton", IPSWICH_AF,
                                                status=STATUS_LIVE))

    assert first is not None and again is not None and again.id == first.id == stored.id
    assert db.query(Match).count() == before
    assert registry.take_refusals() == []


# =========================================================== the alias layer, on its own
def test_the_listed_alias_alone_keeps_the_club_single(db, registry):
    """
    With the alias in place the names meet, the club is stored once and the fixture is found by name.

    This is the cheap layer and the one that carries the real spellings: a pairing here is a line
    a person wrote in `match_matching._ALIASES` on purpose.
    """
    stored = stored_pair(registry)
    joined = registry.upsert_fixture(
        fixture_for("api_football", "1557410", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert joined is not None and joined.id == stored.id
    assert db.query(Team).filter(Team.name.in_([IPSWICH_LS, IPSWICH_AF])).count() == 1
    ref = refs_by_provider(registry, "match", stored.id)["api_football"]
    assert ref.matched_by == "name_kickoff"


# =========================================================== two clubs are never merged into one
#: Pairs a similarity ratio scores as one club. Every one is two clubs, most of them in one city,
#: and a merge is permanent: it re-points the provider's team id, so the wrong club is re-confirmed
#: on every later sync and every fixture that provider sends for it lands on the other club.
MUST_NOT_MERGE = [
    ("Manchester United", "Manchester City"),
    ("Real Madrid", "Atletico Madrid"),
    ("Paris FC", "Paris Saint-Germain"),
    ("Sheffield United", "Sheffield Wednesday"),
    ("Bristol City", "Bristol Rovers"),
    ("Inter Milan", "AC Milan"),
]


@pytest.mark.parametrize("stored_club,incoming_club", MUST_NOT_MERGE)
def test_two_clubs_sharing_a_kickoff_are_never_merged(db, registry, stored_club, incoming_club):
    """
    A stored fixture holding one of these clubs proves nothing about the other slot.

    The two records put different clubs in the same place at the same time. One of them is wrong
    and the data does not say which, so the incoming fixture keeps its own clubs and its own row.
    """
    stored = registry.upsert_fixture(
        fixture_for("livescore", "9001", "Arsenal", stored_club, status=STATUS_SCHEDULED))
    assert stored is not None
    stored_away = db.query(Team).filter(Team.id == stored.away_team_id).one()
    before = db.query(Match).count()

    other = registry.upsert_fixture(
        fixture_for("api_football", "9002", "Arsenal", incoming_club, status=STATUS_SCHEDULED))

    assert other is not None, "the incoming fixture is a real game and must be stored"
    assert other.id != stored.id
    assert db.query(Match).count() == before + 1
    assert db.query(Team).filter(Team.id == other.away_team_id).one().id != stored_away.id, \
        f"{incoming_club!r} was folded into {stored_club!r}"
    assert "api_football" not in refs_by_provider(registry, "team", stored_away.id), \
        f"the api_football id for {incoming_club!r} now points at the stored {stored_club!r}"


@pytest.mark.parametrize("stored_club,incoming_club", MUST_NOT_MERGE)
def test_a_club_survives_a_near_miss_and_keeps_its_own_later_fixtures(db, registry, stored_club, incoming_club):
    """
    The cost of one wrong merge is not confined to the fixture that caused it.

    A merge re-points the provider's team id, so the provider's NEXT fixture for that club resolves
    to the other club and is stored under the wrong name for good. This walks that second fixture
    through after the near miss and checks the club it lands on.
    """
    registry.upsert_fixture(fixture_for("livescore", "9001", "Arsenal", stored_club,
                                        status=STATUS_SCHEDULED))
    registry.upsert_fixture(fixture_for("api_football", "9002", "Arsenal", incoming_club,
                                        status=STATUS_SCHEDULED))

    later = registry.upsert_fixture(
        fixture_for("api_football", "9003", "Chelsea", incoming_club,
                    kickoff=KICKOFF + timedelta(days=7), status=STATUS_SCHEDULED))

    assert later is not None
    landed = db.query(Team).filter(Team.id == later.away_team_id).one()
    assert match_matching.normalize_team_name(landed.name) == match_matching.normalize_team_name(incoming_club), \
        f"a later {incoming_club!r} fixture was stored against {landed.name!r}"


# ================================================ a fixture we cannot reconcile is still recorded
def test_a_shared_club_with_an_unrelated_opponent_is_stored_and_reported(db, registry):
    """
    Everton cannot host Ipswich and Liverpool at the same minute. One record is wrong.

    Merging the clubs would be a guess, so the fixture keeps its own clubs. Dropping it would be a
    second guess with a worse ending: the stored row is still there on the next sync and on every
    sync after it, so one wrong row would keep a real fixture off the site permanently. The row is
    written and the contradiction is recorded on it.
    """
    stored = stored_pair(registry)
    before = db.query(Match).count()

    result = registry.upsert_fixture(
        fixture_for("api_football", "3333", "Everton", "Liverpool", status=STATUS_LIVE))

    assert result is not None and result.id != stored.id
    assert db.query(Match).count() == before + 1
    assert registry.take_refusals() == [], "a stored fixture is not a refusal"
    conflict = (result.match_metadata or {}).get("shared_slot_conflict")
    assert conflict and conflict["candidates"] == [str(stored.id)]
    assert conflict["home"] == "Everton" and conflict["away"] == "Liverpool"


def test_a_real_fixture_is_not_vetoed_for_ever_by_one_wrong_stored_row(db, registry):
    """
    The kickoff is not a slot one row can own. Everton v Brentford is a real game and is stored.

    Re-running the same fixture finds it by its provider ref and changes nothing, which is the
    property that matters: a fixture refused once would be refused again on every later sync.
    """
    stored_pair(registry)

    first = registry.upsert_fixture(
        fixture_for("api_football", "4242", "Everton", "Brentford", status=STATUS_SCHEDULED))
    count_after_first = db.query(Match).count()
    again = registry.upsert_fixture(
        fixture_for("api_football", "4242", "Everton", "Brentford", status=STATUS_SCHEDULED))

    assert first is not None and again is not None and again.id == first.id
    assert db.query(Match).count() == count_after_first
    assert db.query(Team).filter(Team.name == "Brentford").count() == 1


def test_an_unlisted_spelling_is_stored_and_reported_rather_than_guessed(db, registry, no_ipswich_alias):
    """
    A spelling nobody has listed, with the clubs still two rows: the sync has no way to be sure.

    Two rows for one fixture is a real cost, and the honest fix is one alias line and a run of
    `scripts/repair_duplicate_matches.py`. Guessing from the names is a worse cost, because the
    same guess merges Manchester United with Manchester City.
    """
    stored = stored_pair(registry)
    stored_away = db.query(Team).filter(Team.id == stored.away_team_id).one()
    before = db.query(Match).count()

    second = registry.upsert_fixture(
        fixture_for("api_football", "1557410", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert second is not None and second.id != stored.id
    assert db.query(Match).count() == before + 1
    conflict = (second.match_metadata or {}).get("shared_slot_conflict")
    assert conflict and conflict["candidates"] == [str(stored.id)]
    assert "api_football" not in refs_by_provider(registry, "team", stored_away.id), \
        "the club is left as the two rows it is, for the repair script to fold"


def test_a_third_row_holding_one_club_is_reported_even_when_the_fixture_is_identified(db, registry, no_ipswich_alias):
    """
    Finding the fixture does not excuse the other row: two rows hold Everton at one kickoff.

    The join is still right -- the identical two clubs in one competition at one moment are one
    game -- so the fixture lands on the stored row. The leftover row is a contradiction all the
    same, and it goes on the row that survives rather than being dropped because the lookup
    happened to succeed.
    """
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    everton = db.query(Team).filter(Team.name == "Everton").one()
    league = db.query(League).one()
    brentford = Team(id=uuid.uuid4(), name="Brentford", short_name="Brentford", country="England", is_active=True)
    db.add(brentford)
    db.flush()
    third = Match(id=uuid.uuid4(), home_team_id=everton.id, away_team_id=brentford.id, league_id=league.id,
                  match_date=KICKOFF.replace(tzinfo=None), status=MatchStatus.SCHEDULED,
                  external_api_id=None, external_api_source="livescore", match_metadata={})
    db.add(third)
    db.flush()
    before = db.query(Match).count()

    joined = registry.upsert_fixture(
        fixture_for("api_football", "1557410", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert joined is not None and joined.id == stored.id
    assert db.query(Match).count() == before, "the fixture is the stored row, not a new one"
    conflict = (joined.match_metadata or {}).get("shared_slot_conflict")
    assert conflict and conflict["candidates"] == [str(third.id)]


def test_two_stored_fixtures_holding_the_club_are_reported_not_guessed_between(db, registry, no_ipswich_alias):
    """Two candidates are a contradiction, not a decision; both are named in the report."""
    stored = stored_pair(registry)
    # a second stored row already holding Everton at this kickoff: whatever put it there, the
    # sweep has no way to choose between them
    everton = db.query(Team).filter(Team.name == "Everton").one()
    league = db.query(League).one()
    other_away = Team(id=uuid.uuid4(), name="Brentford", short_name="Brentford", country="England", is_active=True)
    db.add(other_away)
    db.flush()
    second = Match(id=uuid.uuid4(), home_team_id=everton.id, away_team_id=other_away.id, league_id=league.id,
                   match_date=KICKOFF.replace(tzinfo=None), status=MatchStatus.SCHEDULED,
                   external_api_id=None, external_api_source="livescore", match_metadata={})
    db.add(second)
    db.flush()
    before = db.query(Match).count()

    result = registry.upsert_fixture(
        fixture_for("api_football", "6666", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert result is not None and result.id not in (stored.id, second.id)
    assert db.query(Match).count() == before + 1
    conflict = (result.match_metadata or {}).get("shared_slot_conflict")
    assert conflict and set(conflict["candidates"]) == {str(stored.id), str(second.id)}


# =========================================================== near misses that must NOT be joined
def test_the_same_clubs_in_a_different_competition_are_a_different_fixture(db, registry, no_ipswich_alias):
    """The join is scoped to one competition: the same two clubs elsewhere is another game."""
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    before = db.query(Match).count()

    other = registry.upsert_fixture(fixture_for("api_football", "2222", "Everton", IPSWICH_AF,
                                                key="champions_league", status=STATUS_SCHEDULED))

    assert other is not None and other.id != stored.id
    assert db.query(Match).count() == before + 1, "a fixture in another competition gets its own row"
    assert "shared_slot_conflict" not in (other.match_metadata or {})


def test_the_reverse_leg_is_never_joined(db, registry, no_ipswich_alias):
    """Swapped home and away is a different match; the join needs the clubs in the SAME slots."""
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    before = db.query(Match).count()

    reverse = registry.upsert_fixture(
        fixture_for("api_football", "4444", IPSWICH_AF, "Everton", status=STATUS_SCHEDULED))

    assert reverse is not None, "the reverse leg is a real fixture and is stored"
    assert reverse.id != stored.id
    assert db.query(Match).count() == before + 1
    assert reverse.home_team_id == stored.away_team_id and reverse.away_team_id == stored.home_team_id


def test_a_kickoff_outside_the_window_is_not_the_same_moment(db, registry, no_ipswich_alias):
    """Two hours apart is two fixtures as far as this rule is concerned; names decide those."""
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    before = db.query(Match).count()

    later = registry.upsert_fixture(
        fixture_for("api_football", "5555", "Everton", IPSWICH_AF,
                    kickoff=KICKOFF + timedelta(hours=2), status=STATUS_SCHEDULED))

    assert later is not None, "a fixture outside the window is stored on its own row"
    assert later.id != stored.id
    assert db.query(Match).count() == before + 1
    assert "shared_slot_conflict" not in (later.match_metadata or {})


def test_a_provider_that_already_owns_the_candidate_never_joins_it_twice(db, registry, no_ipswich_alias):
    """One provider never gives one fixture two live ids, so its other fixture is not a candidate."""
    stored = stored_pair(registry)
    link_clubs(registry, stored, "api_football")
    registry.set_ref("match", stored.id, "api_football", "1557410", confidence="exact", matched_by="provider_id")
    before = db.query(Match).count()

    other = registry.upsert_fixture(
        fixture_for("api_football", "7777", "Everton", IPSWICH_AF, status=STATUS_LIVE))

    assert other is not None and other.id != stored.id
    assert db.query(Match).count() == before + 1
    assert "shared_slot_conflict" not in (other.match_metadata or {}), \
        "the provider's own other fixture is not a contradiction to report"


# =========================================================== a split fixture with no marker
def test_both_clubs_spelled_differently_leaves_only_the_shared_slot_to_find_it(db, registry, repair_script):
    """
    Cardiff City v Swansea City beside Cardiff v Swansea: one fixture, two rows, no marker.

    Four club rows, because neither name matches its counterpart. No club row is shared, so the
    sync has no contradiction to write down and the rows carry no `shared_slot_conflict`. No
    normalised name is shared either, so `duplicate_groups` puts them in different buckets. The
    competition and the kickoff are the only thing the two rows still have in common, which is
    what `same_slot_fixtures` looks at.
    """
    first = registry.upsert_fixture(fixture_for("livescore", "cs-1", "Cardiff City", "Swansea City"))
    second = registry.upsert_fixture(fixture_for("api_football", "cs-2", "Cardiff", "Swansea"))
    assert first is not None and second is not None and first.id != second.id
    assert first.league_id == second.league_id
    assert "shared_slot_conflict" not in (first.match_metadata or {})
    assert "shared_slot_conflict" not in (second.match_metadata or {})
    db.flush()

    both = {str(first.id), str(second.id)}
    assert [g for g in repair_script.duplicate_groups(db) if {c.id for c in g} & both] == []
    assert [c for c in repair_script.slot_conflicts(db) if c.match.id in both] == []
    assert any(both <= {c.id for c in cluster} for cluster in repair_script.same_slot_fixtures(db))


def test_an_ordinary_matchday_fills_the_same_listing(db, registry, repair_script):
    """
    Two unrelated fixtures kicking off together are in that listing as well.

    They are a real matchday and there is nothing to repair, which is why `same_slot_fixtures`
    only reports: the shared slot is a reason for a person to look, never a reason to fold.
    """
    one = registry.upsert_fixture(fixture_for("livescore", "md-1", "Arsenal", "Chelsea"))
    two = registry.upsert_fixture(fixture_for("livescore", "md-2", "Everton", "Fulham"))
    assert one is not None and two is not None
    db.flush()

    both = {str(one.id), str(two.id)}
    assert any(both <= {c.id for c in cluster} for cluster in repair_script.same_slot_fixtures(db))


# =========================================================== placeholder fixtures
def _placeholder(db, registry) -> Match:
    """A fixture whose two slots name no club, as an interrupted agent run leaves behind."""
    league = registry.ensure_canonical_league("premier_league")
    home = Team(id=uuid.uuid4(), name="Home Team (TBD)", short_name="HOME", country="Unknown", is_active=True)
    away = Team(id=uuid.uuid4(), name="Away Team (TBD)", short_name="AWAY", country="Unknown", is_active=True)
    db.add_all([home, away])
    db.flush()
    row = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                match_date=KICKOFF.replace(tzinfo=None), status=MatchStatus.SCHEDULED,
                external_api_id=None, external_api_source="placeholder", match_metadata={})
    db.add(row)
    db.flush()
    return row


def test_a_placeholder_nothing_points_at_is_an_orphan_the_script_deletes(db, registry, repair_script):
    """Both slots name no club and no dependent row exists, so deleting it loses no record."""
    orphan = _placeholder(db, registry)
    deps = repair_script.dependents(db)

    found = {c.id: c for c in repair_script.placeholder_matches(db, deps)}

    assert str(orphan.id) in found
    assert found[str(orphan.id)].dependent_rows == 0
    repair_script.delete_unreferenced(db, deps, "predictions.matches", str(orphan.id))
    assert db.query(Match).filter(Match.id == orphan.id).first() is None


def test_a_placeholder_carrying_a_prediction_is_reported_and_refuses_to_be_deleted(db, registry, repair_script):
    """A prediction on the row means something was recorded against it; the count is the guard."""
    kept = _placeholder(db, registry)
    publish(db, kept, expert(db))
    deps = repair_script.dependents(db)

    found = {c.id: c for c in repair_script.placeholder_matches(db, deps)}

    assert found[str(kept.id)].dependent_rows > 0
    with pytest.raises(RuntimeError, match="not a deletable orphan"):
        repair_script.delete_unreferenced(db, deps, "predictions.matches", str(kept.id))
    assert db.query(Match).filter(Match.id == kept.id).first() is not None


# =========================================================== the sweep for stranded fixtures
def _stranded(db, registry, *, days_ago: int, status=MatchStatus.LIVE, minute="62") -> Match:
    league = registry.ensure_canonical_league("premier_league")
    now = datetime.now(timezone.utc)
    home = Team(id=uuid.uuid4(), name=f"Home {uuid.uuid4().hex[:6]}", short_name="H", country="England", is_active=True)
    away = Team(id=uuid.uuid4(), name=f"Away {uuid.uuid4().hex[:6]}", short_name="A", country="England", is_active=True)
    db.add_all([home, away])
    db.flush()
    row = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                match_date=(now - timedelta(days=days_ago)).replace(tzinfo=None), status=status,
                external_api_id=None, external_api_source="api_football",
                match_metadata={"minute": minute})
    db.add(row)
    db.flush()
    return row


def test_a_fixture_stuck_behind_the_lookback_is_found_by_the_sweep(db, registry):
    """Two days old, still LIVE: neither the live poll nor a one-day results lookback reaches it."""
    stuck = _stranded(db, registry, days_ago=2)
    now = datetime.now(timezone.utc)

    days = registry.stale_unsettled_days(now, lookback_days=1)

    assert stuck.match_date.date() in days


def test_a_finished_fixture_is_never_swept(db, registry):
    _stranded(db, registry, days_ago=2, status=MatchStatus.FINISHED)
    assert registry.stale_unsettled_days(datetime.now(timezone.utc), lookback_days=1) == []


@pytest.mark.parametrize("days_ago", [0, 1])
def test_a_fixture_inside_the_lookback_is_left_to_the_results_task(db, registry, days_ago):
    """
    The sweep only reopens what the ordinary refresh cannot reach; it never doubles up on it.

    A lookback of 1 covers today AND yesterday, so yesterday is the results task's day. Offering
    it here would spend the sweep's whole budget on a day that was going to be asked about anyway.
    """
    _stranded(db, registry, days_ago=days_ago)
    assert registry.stale_unsettled_days(datetime.now(timezone.utc), lookback_days=1) == []


def test_the_sweep_is_capped_so_it_cannot_reopen_the_whole_season(db, registry):
    for age in (2, 3, 4, 5):
        _stranded(db, registry, days_ago=age)
    now = datetime.now(timezone.utc)

    days = registry.stale_unsettled_days(now, lookback_days=1, max_days=2)

    assert len(days) == 2
    assert days == sorted(days), "oldest first: the fixtures that have been wrong longest"


def test_the_sweep_gives_up_in_writing_and_stops_asking(db, registry):
    """
    A provider that has not answered in three passes is not going to. Giving up is recorded.

    The row keeps the status it has -- a score nobody reported is not a score -- but it stops
    costing a provider request, and `match_metadata.recovery` says when and why.
    """
    stuck = _stranded(db, registry, days_ago=2)
    now = datetime.now(timezone.utc)

    for _ in range(3):
        registry.record_recovery_attempt(stuck, now)

    state = registry.recovery_state(stuck)
    assert state["attempts"] == 3
    assert state["gave_up_at"] and "no result after 3 attempts" in state["gave_up_reason"]
    assert stuck.status == MatchStatus.LIVE, "nothing is invented about the match itself"
    assert registry.stale_unsettled_days(now, lookback_days=1) == []


def test_a_fixture_past_the_results_horizon_is_given_up_at_once(db, registry):
    """Beyond the horizon the provider's results endpoint has nothing to say; asking is waste."""
    old = _stranded(db, registry, days_ago=30)
    now = datetime.now(timezone.utc)

    assert registry.stale_unsettled_days(now, lookback_days=1) == [], "too old to be offered at all"

    state = registry.record_recovery_attempt(old, now)
    assert state["gave_up_at"] and "results horizon" in state["gave_up_reason"]


def test_the_horizon_that_selects_a_fixture_is_the_horizon_that_gives_up_on_it(db, registry):
    """
    One day older than the horizon: not offered, and the two bounds are measured the same way.

    `unsettled_before` selects a fixture and `record_recovery_attempt` ages it, and each provider
    request the sweep spends is charged against the day it reopens. A fixture inside one bound and
    outside the other is offered, paid for, and abandoned as too old in the same pass.
    """
    horizon = int(STALE_SWEEP_MAX_AGE.days)
    just_outside = _stranded(db, registry, days_ago=horizon + 1)
    now = datetime.now(timezone.utc)

    assert registry.unsettled_before(now - UNSETTLED_GRACE, now=now) == []
    assert registry.stale_unsettled_days(now, lookback_days=1) == []
    assert registry.record_recovery_attempt(just_outside, now)["gave_up_at"], \
        "the age that keeps it out of the sweep is the age the sweep gives up at"

    inside = _stranded(db, registry, days_ago=horizon - 1)
    assert inside.match_date.date() in registry.stale_unsettled_days(now, lookback_days=1, max_days=9)
    assert not registry.record_recovery_attempt(inside, now).get("gave_up_at")


def test_a_recovered_fixture_leaves_the_sweep(db, registry):
    """The point of the sweep: once the result lands the fixture stops being asked about."""
    stuck = _stranded(db, registry, days_ago=2)
    now = datetime.now(timezone.utc)
    assert registry.stale_unsettled_days(now, lookback_days=1) != []

    stuck.status = MatchStatus.FINISHED
    db.flush()

    assert registry.stale_unsettled_days(now, lookback_days=1) == []
