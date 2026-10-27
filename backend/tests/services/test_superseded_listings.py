"""
One match its provider dropped and listed again under a new fixture id: joined on the row it has.

THE INCIDENT, AS THE STORED ROWS RECORD IT. Live Score listed Paris Saint-Germain v Lyon, Ligue 1
round 8, as fixture 1877019 for 2026-10-25 19:45 UTC; the sync stored it on 2026-10-18 and the
forecast provider's event 28930 was bound to it, nine snapshots by the 26th. The listing was last
sent at 17:09 UTC on the 25th and never again; nobody reported it started; the recovery sweep asked
results providers about it eighteen times. At 20:56 UTC on the 26th the live poll brought fixture
742799, the same two clubs the same way round, 19:30 UTC that day, finished 2-0. The registry stored
a second row: a provider's own other id was never a candidate for a new one - a rule that holds for
two LIVE ids and not for a dead one - so the forecasts stayed on a listing that never kicked off and
the result sat on a row with no forecast.

WHAT HOLDS NOW. When every candidate for a new id is this provider's other id, the registry asks
whether exactly one of them is a listing the provider DROPPED: same competition, the identical two
clubs in this order by row id, listed by this provider under another id, never played (no result;
SCHEDULED with the live poll's window closed, or POSTPONED), not closed as a second listing of a
played row, and re-issued for a later kickoff within a fortnight on the same matchday when both
listings name one. That row is re-dated and the result lands on it; its forecasts, snapshots,
predictions and refs stay where they are; the dead ref stays, marked. Anything less is stored as a
new row with the candidates written on it for a person, as before - a return leg, another
competition, another squad, a played listing, a listing still to be played, a different round, an
earlier kickoff, a fortnight away, two candidates.

THE REPAIR. `scripts/repair_duplicate_matches.py` folds a split that was stored before this rule into
the listing the provider maintains, moving every dependent row with its timestamps untouched, and
refuses two listings that disagree. The representative data below carries the incident's public
values (clubs, ids, kickoffs, score); nothing else of the live database is used.

Requires PostgreSQL. Set TEST_DATABASE_URL; skipped when unreachable. No network.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import ProviderEntityRef, ProviderForecastRecord, ProviderForecastSnapshot
from app.models.users import AccountStatus, SavedMatch, User, UserType
from app.services.match_registry import UNSETTLED_GRACE, MatchRegistry

try:
    from app.services.match_registry import SUPERSEDED_CANDIDATES_KEY, SUPERSEDED_KEY, SUPERSEDED_LISTING_WINDOW
except ImportError:  # the previous implementation: the decisive tests below fail there on the rows, not here
    SUPERSEDED_CANDIDATES_KEY, SUPERSEDED_KEY = "superseded_listing_candidates", "superseded_listing"
    SUPERSEDED_LISTING_WINDOW = timedelta(days=14)
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_POSTPONED, STATUS_SCHEDULED, ProviderCompetition, ProviderFixture, ProviderTeam,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

LEAGUE = "ligue_1"
PSG, LYON = "Paris Saint Germain", "Lyon"
DEAD_ID, LIVE_ID, FORECAST_EVENT = "1877019", "742799", "28930"
LISTED_AT = datetime(2026, 10, 18, 18, 29, 32, tzinfo=timezone.utc)
LAST_LISTED_AT = datetime(2026, 10, 25, 17, 9, 0, tzinfo=timezone.utc)
DROPPED_KICKOFF = datetime(2026, 10, 25, 19, 45, tzinfo=timezone.utc)
PLAYED_KICKOFF = datetime(2026, 10, 26, 19, 30, tzinfo=timezone.utc)
LIVE_POLL_AT = datetime(2026, 10, 26, 20, 56, 8, tzinfo=timezone.utc)
#: (first_fetched_at, model run day) of the nine snapshots the dropped listing carried.
FETCHES: List[Tuple[datetime, datetime]] = [
    (datetime(2026, 10, 18, 18, 29, 34, tzinfo=timezone.utc), datetime(2026, 10, 18, tzinfo=timezone.utc)),
    (datetime(2026, 10, 19, 18, 0, 57, tzinfo=timezone.utc), datetime(2026, 10, 19, tzinfo=timezone.utc)),
    (datetime(2026, 10, 20, 13, 15, 30, tzinfo=timezone.utc), datetime(2026, 10, 20, tzinfo=timezone.utc)),
    (datetime(2026, 10, 21, 13, 28, 40, tzinfo=timezone.utc), datetime(2026, 10, 21, tzinfo=timezone.utc)),
    (datetime(2026, 10, 22, 12, 2, 37, tzinfo=timezone.utc), datetime(2026, 10, 22, tzinfo=timezone.utc)),
    (datetime(2026, 10, 23, 12, 5, 25, tzinfo=timezone.utc), datetime(2026, 10, 23, tzinfo=timezone.utc)),
    (datetime(2026, 10, 24, 18, 10, 22, tzinfo=timezone.utc), datetime(2026, 10, 24, tzinfo=timezone.utc)),
    (datetime(2026, 10, 25, 12, 12, 37, tzinfo=timezone.utc), datetime(2026, 10, 25, tzinfo=timezone.utc)),
    (datetime(2026, 10, 26, 12, 14, 31, tzinfo=timezone.utc), datetime(2026, 10, 26, tzinfo=timezone.utc)),
]
DEPENDENT_TABLES = [
    "predictions.matches", "predictions.match_results", "predictions.predictions",
    "predictions.provider_forecast_snapshots", "predictions.provider_forecasts",
    "predictions.provider_entity_refs", "users.saved_matches", "predictions.teams", "predictions.leagues",
]


# ----------------------------------------------------------------------------- database
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
    """Session joined to an outer transaction; nothing a test writes survives it."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="module")
def repair_script():
    """`scripts/repair_duplicate_matches.py`, loaded by path because `scripts/` is not a package."""
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "repair_duplicate_matches_superseded", os.path.join(backend, "scripts", "repair_duplicate_matches.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------------- the listings
def team_id(provider: str, name: str) -> str:
    return f"{provider}-" + "".join(c for c in name.lower() if c.isalnum())[:24]


def listing(external_id: str, kickoff: datetime, *, home: str = PSG, away: str = LYON, key: str = LEAGUE,
            status: str = STATUS_SCHEDULED, round_: Optional[str] = "8", venue: str = "Parc des Princes",
            provider: str = "livescore", **scores) -> ProviderFixture:
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-{key}",
                               name=key.replace("_", " ").title(), key=key, country="France", country_code="FRA")
    return ProviderFixture(
        provider=provider, external_id=external_id, competition=comp,
        home=ProviderTeam(provider=provider, external_id=team_id(provider, home), name=home),
        away=ProviderTeam(provider=provider, external_id=team_id(provider, away), name=away),
        kickoff_utc=kickoff, status=status, venue=venue, round=round_, **scores)


def played() -> ProviderFixture:
    """Fixture 742799 as the live poll brought it on the 26th: finished 2-0, 0-0 at half-time."""
    return listing(LIVE_ID, PLAYED_KICKOFF, status=STATUS_FINISHED, venue="Parc des Princes ",
                   home_score=2, away_score=0, ht_home_score=0, ht_away_score=0)


def store(db, fixture: ProviderFixture, at: datetime) -> Optional[Match]:
    return MatchRegistry(db, now=at).upsert_fixture(fixture)


def stored(db, fixture: ProviderFixture, at: datetime) -> Match:
    match = store(db, fixture, at)
    assert match is not None, "the fixture was refused"
    return match


def dropped_listing(db, kickoff: datetime = DROPPED_KICKOFF, external_id: str = DEAD_ID) -> Match:
    """Fixture 1877019 as production holds it: stored on the 18th, last listed on the 25th, nine
    snapshots and the current forecast bound through the forecast provider's event 28930."""
    match = stored(db, listing(external_id, kickoff), LISTED_AT)
    stored(db, listing(external_id, kickoff), LAST_LISTED_AT)
    registry = MatchRegistry(db, now=LAST_LISTED_AT)
    registry.set_ref("match", match.id, "gameforecast", FORECAST_EVENT, confidence="exact", matched_by="name_kickoff",
                     metadata={"home": PSG, "away": LYON, "kickoff_utc": kickoff.isoformat()})
    for fetched, run in FETCHES:
        db.add(ProviderForecastSnapshot(
            id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=FORECAST_EVENT,
            content_hash=uuid.uuid4().hex, home_win_prob=Decimal("0.61"), draw_prob=Decimal("0.22"),
            away_win_prob=Decimal("0.17"), match_confidence="exact", matched_by="name_kickoff",
            model_run_at=run.replace(tzinfo=None), first_fetched_at=fetched.replace(tzinfo=None),
            last_fetched_at=fetched.replace(tzinfo=None), kickoff_at_capture=kickoff.replace(tzinfo=None),
            captured_before_kickoff=fetched < kickoff))
    db.add(ProviderForecastRecord(
        id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=FORECAST_EVENT,
        home_win_prob=Decimal("0.61"), draw_prob=Decimal("0.22"), away_win_prob=Decimal("0.17"),
        match_confidence="exact", matched_by="name_kickoff", model_run_at=FETCHES[-1][1].replace(tzinfo=None),
        fetched_at=FETCHES[-1][0].replace(tzinfo=None)))
    db.flush()
    db.expire_all()
    return db.query(Match).filter(Match.id == match.id).one()


def psg_lyon_rows(db) -> List[Match]:
    home = db.query(Team).filter(Team.name == PSG).first()
    away = db.query(Team).filter(Team.name == LYON).first()
    if home is None or away is None:
        return []
    return db.query(Match).filter(Match.home_team_id == home.id, Match.away_team_id == away.id)\
        .order_by(Match.match_date).all()


def snapshots_of(db, match_id) -> List[Tuple]:
    rows = db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id == match_id)\
        .order_by(ProviderForecastSnapshot.first_fetched_at).all()
    return [(r.first_fetched_at, r.model_run_at, r.kickoff_at_capture, r.captured_before_kickoff) for r in rows]


def refs_of(db, match_id) -> Dict[Tuple[str, str], ProviderEntityRef]:
    return {(r.provider, r.external_id): r for r in MatchRegistry(db).refs_for("match", match_id)}


def result_of(db, match_id) -> Optional[Tuple[int, int]]:
    row = db.query(MatchResult).filter(MatchResult.match_id == match_id).first()
    return None if row is None else (row.home_score, row.away_score)


def reader(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"psg-{suffix}@test.local", username=f"psg_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def attach_people(db, match: Match) -> Tuple[Prediction, SavedMatch]:
    user = reader(db)
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                            priority_level=100, reasoning="expert view")
    saved = SavedMatch(id=uuid.uuid4(), user_id=user.id, match_id=match.id, note="watch this one")
    db.add_all([prediction, saved])
    db.flush()
    return prediction, saved


def checksums(db) -> Dict[str, Tuple[int, str]]:
    """Row count and a digest of every row's text, per table: equal before and after means untouched."""
    out = {}
    for table in DEPENDENT_TABLES:
        count, digest = db.execute(text(
            f"SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') FROM {table} t")).first()
        out[table] = (count, digest)
    return out


# =========================================================== the join, at ingestion
def test_a_listing_dropped_and_issued_again_is_the_same_match_on_the_same_row(db):
    dropped = dropped_listing(db)
    before = snapshots_of(db, dropped.id)
    assert len(before) == 9 and before[-1][3] is False, "the 26th's snapshot was retrieved after the dropped kickoff"

    match = stored(db, played(), LIVE_POLL_AT)

    assert match.id == dropped.id, "the forecast and the result are on one row - the previous code made a second"
    assert [m.id for m in psg_lyon_rows(db)] == [dropped.id]
    db.expire_all()
    row = db.query(Match).filter(Match.id == dropped.id).one()
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert result_of(db, row.id) == (2, 0)
    assert snapshots_of(db, row.id) == before, "every snapshot kept its retrieval time, model date and capture facts"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == row.id).count() == 1
    refs = refs_of(db, row.id)
    assert set(refs) == {("gameforecast", FORECAST_EVENT), ("livescore", DEAD_ID), ("livescore", LIVE_ID)}
    assert refs[("livescore", DEAD_ID)].ref_metadata["superseded_by"]["external_id"] == LIVE_ID
    assert refs[("livescore", LIVE_ID)].matched_by == "superseded_listing"
    note = row.match_metadata[SUPERSEDED_KEY]
    assert note["previous_external_ids"] == [DEAD_ID] and note["external_id"] == LIVE_ID
    assert note["previous"]["kickoff_utc"] == DROPPED_KICKOFF.isoformat() and note["previous"]["status"] == "scheduled"
    assert note["previous"]["last_synced_at"] is not None
    assert row.external_api_id == f"livescore:{LIVE_ID}" and note["previous"]["external_api_id"] == f"livescore:{DEAD_ID}"
    assert SUPERSEDED_CANDIDATES_KEY not in row.match_metadata


def test_repeated_ingestion_changes_nothing(db):
    dropped = dropped_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    db.expire_all()
    first = dict(db.query(Match).filter(Match.id == dropped.id).one().match_metadata[SUPERSEDED_KEY])

    again = stored(db, played(), LIVE_POLL_AT + timedelta(minutes=30))

    assert again.id == dropped.id and [m.id for m in psg_lyon_rows(db)] == [dropped.id]
    db.expire_all()
    row = db.query(Match).filter(Match.id == dropped.id).one()
    assert row.match_metadata[SUPERSEDED_KEY] == first, "the note is written once, by the pass that joined the listing"
    assert len(snapshots_of(db, row.id)) == 9 and result_of(db, row.id) == (2, 0)
    assert len(refs_of(db, row.id)) == 3


def test_the_dead_id_sent_again_with_its_old_kickoff_is_refused_not_applied(db):
    dropped = dropped_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    registry = MatchRegistry(db, now=LIVE_POLL_AT + timedelta(hours=1))

    assert registry.upsert_fixture(listing(DEAD_ID, DROPPED_KICKOFF)) is None
    refusal = registry.take_refusals()[0]
    assert refusal["external_id"] == DEAD_ID and "superseded by 742799" in refusal["reason"]
    db.expire_all()
    row = db.query(Match).filter(Match.id == dropped.id).one()
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert [m.id for m in psg_lyon_rows(db)] == [dropped.id]


def test_a_postponed_listing_is_re_issued_on_the_same_row(db):
    dropped = dropped_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_POSTPONED), DROPPED_KICKOFF - timedelta(hours=2))
    db.expire_all()
    assert db.query(Match).filter(Match.id == dropped.id).one().status == MatchStatus.POSTPONED

    match = stored(db, played(), LIVE_POLL_AT)

    assert match.id == dropped.id and [m.id for m in psg_lyon_rows(db)] == [dropped.id]
    db.expire_all()
    row = db.query(Match).filter(Match.id == dropped.id).one()
    assert row.status == MatchStatus.FINISHED and result_of(db, row.id) == (2, 0)
    assert row.match_metadata[SUPERSEDED_KEY]["previous"]["status"] == "postponed"


# =========================================================== what stays two rows
def unproven_note(db, match: Match) -> Dict:
    db.expire_all()
    return db.query(Match).filter(Match.id == match.id).one().match_metadata[SUPERSEDED_CANDIDATES_KEY]


def assert_untouched(db, dropped: Match, kickoff: datetime = DROPPED_KICKOFF) -> None:
    db.expire_all()
    row = db.query(Match).filter(Match.id == dropped.id).one()
    assert row.match_date == kickoff.replace(tzinfo=None) and row.status == MatchStatus.SCHEDULED
    assert SUPERSEDED_KEY not in (row.match_metadata or {})
    assert len(snapshots_of(db, row.id)) == 9 and result_of(db, row.id) is None


def no_note(db, match: Match) -> None:
    db.expire_all()
    assert SUPERSEDED_CANDIDATES_KEY not in (db.query(Match).filter(Match.id == match.id).one().match_metadata or {})


def test_the_return_leg_is_another_match(db):
    dropped = dropped_listing(db)
    reverse = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, home=LYON, away=PSG, status=STATUS_FINISHED,
                                 home_score=2, away_score=0), LIVE_POLL_AT)
    assert reverse.id != dropped.id
    assert_untouched(db, dropped)
    no_note(db, reverse), "the other way round is never a candidate: nothing to weigh, nothing to note"


def test_another_competition_is_another_match(db):
    dropped = dropped_listing(db)
    cup = stored(db, dataclasses.replace(played(), competition=ProviderCompetition(
        provider="livescore", external_id="livescore-champions_league", name="Champions League",
        key="champions_league", country=None, country_code=None)), LIVE_POLL_AT)
    assert cup.id != dropped.id
    assert_untouched(db, dropped)
    db.expire_all()
    assert SUPERSEDED_KEY not in (db.query(Match).filter(Match.id == cup.id).one().match_metadata or {})


def test_a_played_listing_is_not_dropped(db):
    dropped = dropped_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_FINISHED, home_score=1, away_score=1),
           DROPPED_KICKOFF + timedelta(hours=2))
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != dropped.id
    assert [c["why"] for c in unproven_note(db, second)["candidates"]] == ["it has a stored result"]
    db.expire_all()
    assert result_of(db, dropped.id) == (1, 1)


def test_a_listing_still_to_be_played_is_not_dropped_yet(db):
    dropped = dropped_listing(db)
    early = stored(db, listing(LIVE_ID, PLAYED_KICKOFF), DROPPED_KICKOFF - timedelta(days=1))
    assert early.id != dropped.id
    assert_untouched(db, dropped)
    assert [c["why"] for c in unproven_note(db, early)["candidates"]] == ["its kickoff window has not closed"]


def test_the_window_closes_at_the_live_polls_grace(db):
    dropped = dropped_listing(db)
    just_before = DROPPED_KICKOFF + UNSETTLED_GRACE - timedelta(minutes=1)
    assert store(db, listing(LIVE_ID, PLAYED_KICKOFF), just_before).id != dropped.id
    assert_untouched(db, dropped)


def test_a_different_round_is_another_meeting(db):
    dropped = dropped_listing(db)
    other = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, round_="Regular Season - 12"), LIVE_POLL_AT)
    assert other.id != dropped.id
    assert_untouched(db, dropped)
    assert unproven_note(db, other)["candidates"][0]["why"].startswith("a different round")


def test_the_same_round_in_another_providers_words_is_the_same_matchday(db):
    dropped = dropped_listing(db)
    match = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, status=STATUS_FINISHED, home_score=2, away_score=0,
                               round_="Regular Season - 8"), LIVE_POLL_AT)
    assert match.id == dropped.id


def test_an_earlier_kickoff_is_not_a_re_issue(db):
    dropped = dropped_listing(db)
    earlier = stored(db, listing(LIVE_ID, DROPPED_KICKOFF - timedelta(days=1)), DROPPED_KICKOFF + timedelta(days=3))
    assert earlier.id != dropped.id
    assert_untouched(db, dropped)
    no_note(db, earlier)


def test_a_listing_a_fortnight_later_is_left_to_a_person(db):
    dropped = dropped_listing(db)
    far = DROPPED_KICKOFF + SUPERSEDED_LISTING_WINDOW + timedelta(days=1)
    later = stored(db, listing(LIVE_ID, far), far - timedelta(days=1))
    assert later.id != dropped.id
    assert_untouched(db, dropped)
    no_note(db, later), "beyond the window the dropped listing is not even a candidate"
    edge = DROPPED_KICKOFF + SUPERSEDED_LISTING_WINDOW
    registry = MatchRegistry(db, now=edge - timedelta(hours=1))
    league = registry.upsert_league(played().competition)
    home, away = (db.query(Team).filter(Team.id == i).one() for i in (dropped.home_team_id, dropped.away_team_id))
    on_the_edge, _ = registry.superseded_listing_for(listing("742801", edge), home, away, league)
    assert on_the_edge is not None and on_the_edge.id == dropped.id, "fourteen days to the minute is inside the window"
    past_it, unproven = registry.superseded_listing_for(listing("742802", edge + timedelta(minutes=1)), home, away, league)
    assert past_it is None and unproven == [], "a minute beyond it the earlier row is not a candidate at all"


def test_two_dropped_listings_decide_nothing(db):
    first = dropped_listing(db, kickoff=DROPPED_KICKOFF - timedelta(days=1), external_id="1877018")
    second = dropped_listing(db)
    third = stored(db, played(), LIVE_POLL_AT)
    assert third.id not in (first.id, second.id)
    assert_untouched(db, second)
    whys = sorted(c["why"] for c in unproven_note(db, third)["candidates"])
    assert whys == ["another stored listing qualifies as well"] * 2


def test_another_squad_is_another_club(db):
    dropped = dropped_listing(db)
    youth = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, home=f"{PSG} U19", away=f"{LYON} U19"), LIVE_POLL_AT)
    assert youth.id != dropped.id
    assert_untouched(db, dropped)


def test_a_squad_resolved_to_its_clubs_row_is_still_another_squad(db, monkeypatch):
    """Whatever club row the provider's youth side resolves to, the provider's own words say another squad."""
    dropped = dropped_listing(db)
    original = MatchRegistry.upsert_team

    def to_the_senior_row(self, team, country=None, key=None):
        return original(self, dataclasses.replace(team, name=team.name.replace(" U19", "")), country, key)

    monkeypatch.setattr(MatchRegistry, "upsert_team", to_the_senior_row)
    youth = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, home=f"{PSG} U19", away=f"{LYON} U19"), LIVE_POLL_AT)
    assert youth.id != dropped.id
    assert_untouched(db, dropped)
    # The guard itself, asked directly with the clubs resolved to the senior rows:
    registry = MatchRegistry(db, now=LIVE_POLL_AT)
    league = registry.upsert_league(played().competition)
    home, away = (db.query(Team).filter(Team.id == i).one() for i in (dropped.home_team_id, dropped.away_team_id))
    match, unproven = registry.superseded_listing_for(
        listing(LIVE_ID, PLAYED_KICKOFF, home=f"{PSG} U19", away=f"{LYON} U19"), home, away, league)
    assert match is None and unproven[0]["why"].startswith("the provider names another squad")


def test_a_cup_or_national_team_fixture_is_never_joined_by_this_rule(db):
    """The same two sides can meet again the same way round in a cup (a replay) or in a friendly
    window; only a league meets once a season per venue. Outside a league the re-issue stays two rows
    and is written on the new one for a person."""
    for key, external_ids in (("champions_league", ("7001", "7002")), ("national_teams_friendlies", ("7003", "7004"))):
        first_id, second_id = external_ids
        first = stored(db, listing(first_id, DROPPED_KICKOFF, key=key, round_=None), LISTED_AT)
        second = stored(db, listing(second_id, PLAYED_KICKOFF, key=key, round_=None, status=STATUS_FINISHED,
                                    home_score=2, away_score=0), LIVE_POLL_AT)
        assert second.id != first.id, key
        db.expire_all()
        row = db.query(Match).filter(Match.id == first.id).one()
        assert row.status == MatchStatus.SCHEDULED and row.match_date == DROPPED_KICKOFF.replace(tzinfo=None)
        note = unproven_note(db, second)
        assert note["candidates"][0]["why"].startswith("not a league competition"), key


def test_two_live_ids_of_two_meetings_are_untouched(db):
    """A played listing and a later one with the same clubs the same way round - a cup replay at the
    same venue, say - are two meetings: the first has a result, so nothing joins them."""
    first = stored(db, listing("5001", DROPPED_KICKOFF, status=STATUS_FINISHED, home_score=1, away_score=1,
                               key="champions_league"), DROPPED_KICKOFF + timedelta(hours=2))
    replay = stored(db, listing("5002", DROPPED_KICKOFF + timedelta(days=10), key="champions_league"),
                    DROPPED_KICKOFF + timedelta(days=2))
    assert replay.id != first.id and result_of(db, first.id) == (1, 1)


# =========================================================== the repair of a split already stored
@pytest.fixture
def as_the_previous_code(monkeypatch):
    """Store the re-issue the way the previous registry did: never a join, always a new row."""
    monkeypatch.setattr(MatchRegistry, "superseded_listing_for", lambda self, *a, **k: (None, []))


def the_split(db) -> Tuple[Match, Match, Prediction, SavedMatch]:
    dropped = dropped_listing(db)
    prediction, saved = attach_people(db, dropped)
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != dropped.id, "the split, as production holds it"
    MatchRegistry(db, now=LIVE_POLL_AT + timedelta(minutes=11)).set_ref(
        "match", second.id, "api_football", "1552800", confidence="exact", matched_by="provider_id")
    db.expire_all()
    return dropped, second, prediction, saved


def apply(db, repair_script, pair, deps, at: datetime) -> Dict[str, int]:
    moved = repair_script.apply_supersession(db, pair, deps, now=at)
    db.flush()
    db.expunge_all()
    return moved


def test_the_repair_finds_the_split_and_plans_every_reference(db, repair_script, as_the_previous_code):
    dropped, second, _, _ = the_split(db)
    deps = repair_script.dependents(db)

    pairs = repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))

    assert [(p.stale.id, p.successor.id) for p in pairs] == [(str(dropped.id), str(second.id))]
    pair = repair_script.plan_supersession(db, pairs[0], deps)
    assert pair.provider == "livescore" and pair.dead_ids == [DEAD_ID] and pair.live_ids == [LIVE_ID]
    assert pair.safe, pair.blockers
    assert pair.moves == {"predictions.provider_forecast_snapshots": 9, "predictions.provider_forecasts": 1,
                          "predictions.provider_entity_refs": 2, "predictions.predictions": 1,
                          "users.saved_matches": 1}
    assert len(pair.consequences) == 2
    assert "2 prediction(s), slip leg(s) or saved match(es)" in pair.consequences[0]
    assert "the next settle pass scores them" in pair.consequences[0]
    assert "1 snapshot(s) retrieved before the match was played" in pair.consequences[1]


def test_the_dry_run_changes_nothing(db, repair_script, as_the_previous_code):
    the_split(db)
    deps = repair_script.dependents(db)
    before = checksums(db)
    for pair in repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2)):
        repair_script.plan_supersession(db, pair, deps)
    db.flush()
    assert checksums(db) == before


def test_the_repair_folds_the_dropped_listing_into_its_successor(db, repair_script, as_the_previous_code):
    dropped, second, prediction, saved = the_split(db)
    dropped_id, second_id, prediction_id, saved_id = dropped.id, second.id, prediction.id, saved.id
    before = snapshots_of(db, dropped.id)
    previous_meta = dict(db.query(Match).filter(Match.id == dropped.id).one().match_metadata)
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(
        db, repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))[0], deps)

    moved = apply(db, repair_script, pair, deps, LIVE_POLL_AT + timedelta(hours=2))

    assert moved == pair.moves
    assert [m.id for m in psg_lyon_rows(db)] == [second_id], "the dropped row is gone, the successor stands"
    row = db.query(Match).filter(Match.id == second_id).one()
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert result_of(db, row.id) == (2, 0) and row.external_api_id == f"livescore:{LIVE_ID}"
    assert snapshots_of(db, row.id) == before, "nine snapshots, every timestamp and capture fact as it was"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == row.id).count() == 1
    refs = refs_of(db, row.id)
    assert set(refs) == {("gameforecast", FORECAST_EVENT), ("livescore", DEAD_ID), ("livescore", LIVE_ID),
                         ("api_football", "1552800")}
    assert refs[("livescore", DEAD_ID)].ref_metadata["superseded_by"]["external_id"] == LIVE_ID
    assert db.query(Prediction).filter(Prediction.id == prediction_id).one().match_id == row.id
    assert db.query(SavedMatch).filter(SavedMatch.id == saved_id).one().match_id == row.id
    note = row.match_metadata[SUPERSEDED_KEY]
    assert note["previous"]["match_id"] == str(dropped_id)
    assert note["previous"]["kickoff_utc"] == DROPPED_KICKOFF.isoformat() and note["previous"]["status"] == "SCHEDULED"
    assert note["previous"]["external_api_id"] == f"livescore:{DEAD_ID}"
    assert note["previous"]["match_metadata"]["last_synced_at"] == previous_meta["last_synced_at"]
    assert note["moved"] == pair.moves
    assert db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_id == dropped_id).count() == 0
    orphans = db.execute(text("""
        SELECT count(*) FROM predictions.provider_entity_refs r
        WHERE r.entity_type = 'match' AND NOT EXISTS (SELECT 1 FROM predictions.matches m WHERE m.id = r.entity_id)
    """)).scalar()
    assert orphans == 0


def test_a_second_application_changes_nothing(db, repair_script, as_the_previous_code):
    the_split(db)
    deps = repair_script.dependents(db)
    at = LIVE_POLL_AT + timedelta(hours=2)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=at)[0], deps)
    apply(db, repair_script, pair, deps, at)
    after_first = checksums(db)

    assert repair_script.superseded_listings(db, now=at) == []
    db.flush()
    assert checksums(db) == after_first


def test_the_repair_touches_no_other_row(db, repair_script, as_the_previous_code):
    bystander = stored(db, listing("6001", PLAYED_KICKOFF + timedelta(hours=1), home="Marseille", away="Nice",
                                   status=STATUS_FINISHED, home_score=0, away_score=0), LIVE_POLL_AT)
    bystander_before = db.execute(text("SELECT t::text FROM predictions.matches t WHERE id = :mid"),
                                  {"mid": str(bystander.id)}).scalar()
    the_split(db)
    deps = repair_script.dependents(db)
    at = LIVE_POLL_AT + timedelta(hours=2)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=at)[0], deps)
    bystander_id = str(bystander.id)
    apply(db, repair_script, pair, deps, at)
    assert db.execute(text("SELECT t::text FROM predictions.matches t WHERE id = :mid"),
                      {"mid": bystander_id}).scalar() == bystander_before
    assert db.query(Match).count() == 2


def test_the_repair_does_not_see_a_played_dropped_listing(db, repair_script, as_the_previous_code):
    dropped = dropped_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_FINISHED, home_score=1, away_score=1),
           DROPPED_KICKOFF + timedelta(hours=2))
    stored(db, played(), LIVE_POLL_AT)
    assert repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2)) == []
    db.expire_all()
    assert result_of(db, dropped.id) == (1, 1)


def test_the_repair_refuses_when_the_rounds_differ(db, repair_script, as_the_previous_code):
    dropped = dropped_listing(db)
    stored(db, dataclasses.replace(played(), round="Regular Season - 12"), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))
    assert len(pairs) == 1 and not pairs[0].safe
    assert any("rounds differ" in b for b in pairs[0].blockers)
    assert_untouched(db, dropped)


def test_the_repair_refuses_a_current_forecast_collision(db, repair_script, as_the_previous_code):
    dropped, second, _, _ = the_split(db)
    db.add(ProviderForecastRecord(
        id=uuid.uuid4(), match_id=second.id, provider="gameforecast", external_event_id="99999",
        home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
        match_confidence="exact", matched_by="name_kickoff", fetched_at=LIVE_POLL_AT.replace(tzinfo=None)))
    db.flush()
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(
        db, repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))[0], deps)
    assert not pair.safe and any("provider_forecasts" in b and "collide" in b for b in pair.blockers)
    assert_untouched(db, dropped)


def test_the_repair_reports_a_non_league_pair_and_refuses_it(db, repair_script, as_the_previous_code):
    stale = stored(db, listing("7003", DROPPED_KICKOFF, key="national_teams_friendlies", round_=None), LISTED_AT)
    stored(db, listing("7004", PLAYED_KICKOFF, key="national_teams_friendlies", round_=None, status=STATUS_FINISHED,
                       home_score=2, away_score=0), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))
    assert len(pairs) == 1 and pairs[0].stale.id == str(stale.id) and not pairs[0].safe
    assert any("not a league competition" in b for b in pairs[0].blockers)


def test_the_repair_refuses_two_successors(db, repair_script, as_the_previous_code):
    dropped = dropped_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    stored(db, listing("742800", PLAYED_KICKOFF + timedelta(days=1)), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=LIVE_POLL_AT + timedelta(hours=2))
    assert len(pairs) == 2 and all(not p.safe for p in pairs)
    assert all(any("possible successors" in b for b in p.blockers) for p in pairs)
    assert_untouched(db, dropped)
