"""
One match its provider listed again under a new fixture id: joined on the row it has - on evidence.

THE INCIDENT, AS THE STORED ROWS RECORD IT. Live Score listed Paris Saint-Germain v Lyon, Ligue 1
round 8, as fixture 1877019 for 2026-10-25 19:45 UTC; the sync stored it on 2026-10-18 and the
forecast provider's event 28930 was bound to it, nine snapshots by the 26th. Live Score last named
it in its listing of the 25th made at 17:08:50 UTC; the complete listing of the same date made at
23:11:00 UTC did not name it; nobody reported it started; the recovery sweep asked results
providers about it eighteen times. At 20:56 UTC on the 26th the live poll brought fixture 742799,
the same two clubs the same way round, 19:30 UTC that day, finished 2-0. The registry stored a
second row: a provider's own other id was never a candidate for a new one.

WHAT HOLDS NOW. When every candidate for a new id is this provider's other id, the registry asks
whether exactly one of them is a listing the provider WITHDREW - and withdrawal is a thing this
installation must have OBSERVED: a complete listing of the earlier row's date, straight from the
provider with every page read, made after the provider last named the row, that did not name it,
with nothing naming it since (`MatchRegistry.observe_listing`, called by the day sync before it
stores a listing). Elapsed time, a missing result and an old timestamp are not observations; a
provider that names both ids, in one batch or in succession, contradicts a replacement, whichever
order the two arrive in. The rest is as before: a league, the identical clubs by row and by the
provider's own names, another id, no result and nothing reported started (or POSTPONED), a later
kickoff within a fortnight, the same round when both name one. Anything less is stored as a new
row with the candidates and what was and was not observed written on it, and the record never says
"withdrawn" of something merely not seen.

THE REPAIR. `scripts/repair_duplicate_matches.py` reports each pair with its evidence, folds one
only when a person names it, and one whose withdrawal was not observed only with the person's
reviewed evidence, which goes into the record. Every dependent row moves with its timestamps
untouched; a move that would collide refuses the whole pair without a partial change.

Requires PostgreSQL. Set TEST_DATABASE_URL; skipped when unreachable. No network.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionAudit, PredictionOutcome, PredictionResult,
    PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import (
    ProviderEntityRef, ProviderForecastRecord, ProviderForecastResult, ProviderForecastSnapshot,
)
from app.models.slips import SelectionSlip, SelectionSlipLeg
from app.models.users import AccountStatus, SavedMatch, User, UserType
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService
from app.services.match_registry import UNSETTLED_GRACE, MatchRegistry
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_POSTPONED, STATUS_SCHEDULED, MatchDataProvider, ProviderCompetition, ProviderFixture,
    ProviderTeam, ProviderUnavailableError,
)
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

try:
    from app.services.match_registry import (
        LISTINGS_KEY, SUPERSEDED_CANDIDATES_KEY, SUPERSEDED_KEY, SUPERSEDED_LISTING_WINDOW,
    )
except ImportError:  # the previous implementation: the decisive tests below fail there on the rows, not here
    LISTINGS_KEY, SUPERSEDED_CANDIDATES_KEY, SUPERSEDED_KEY = "listings", "superseded_listing_candidates", "superseded_listing"
    SUPERSEDED_LISTING_WINDOW = timedelta(days=14)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

LEAGUE = "ligue_1"
PROVIDER = "livescore"
PSG, LYON = "Paris Saint Germain", "Lyon"
DEAD_ID, LIVE_ID, FORECAST_EVENT = "1877019", "742799", "28930"
LISTED_AT = datetime(2026, 10, 18, 18, 29, 32, tzinfo=timezone.utc)
LAST_LISTED_AT = datetime(2026, 10, 25, 17, 8, 50, tzinfo=timezone.utc)
#: The complete Ligue 1 listing of the 25th that did not name 1877019 (the day's other fixtures only).
ABSENT_LISTING_AT = datetime(2026, 10, 25, 23, 11, 0, tzinfo=timezone.utc)
DROPPED_KICKOFF = datetime(2026, 10, 25, 19, 45, tzinfo=timezone.utc)
PLAYED_KICKOFF = datetime(2026, 10, 26, 19, 30, tzinfo=timezone.utc)
LIVE_POLL_AT = datetime(2026, 10, 26, 20, 56, 8, tzinfo=timezone.utc)
#: (first_fetched_at, model run day) of the nine snapshots the earlier listing carried.
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
TABLES = [
    "predictions.matches", "predictions.match_results", "predictions.predictions", "predictions.prediction_results",
    "predictions.prediction_audit", "predictions.provider_forecast_snapshots", "predictions.provider_forecasts",
    "predictions.provider_forecast_results", "predictions.provider_entity_refs", "users.saved_matches",
    "users.selection_slips", "users.selection_slip_legs", "predictions.teams", "predictions.leagues",
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
            provider: str = PROVIDER, **scores) -> ProviderFixture:
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


def league_of(db, key: str = LEAGUE):
    return MatchRegistry(db).ensure_canonical_league(key)


def observe(db, external_ids: List[str], at: datetime, day: Optional[date] = None, complete: bool = True,
            key: str = LEAGUE, provider: str = PROVIDER) -> Dict[str, int]:
    """What one fresh listing by the provider said, as the day sync reports it to the registry."""
    league = league_of(db, key)
    registry = MatchRegistry(db, now=at)
    observe_listing = getattr(registry, "observe_listing", None)
    if observe_listing is None:                                 # the previous implementation observed nothing
        return {"seen": 0, "absent": 0}
    return observe_listing(provider, external_ids, at=at, day=day, league_ids=[league.id] if day else None,
                           complete=complete)


def earlier_listing(db, kickoff: datetime = DROPPED_KICKOFF, external_id: str = DEAD_ID, *,
                    withdrawal_observed: bool = True) -> Match:
    """Fixture 1877019 as production holds it, plus - when `withdrawal_observed` - what the sync
    observed: named by the listing of the 25th at 17:08:50, absent from the complete listing of the
    25th at 23:11:00. Nine snapshots and the current forecast are bound through event 28930."""
    match = stored(db, listing(external_id, kickoff), LISTED_AT)
    observe(db, [external_id, "1877020", "1877021"], LAST_LISTED_AT, day=kickoff.date())
    stored(db, listing(external_id, kickoff), LAST_LISTED_AT)
    if withdrawal_observed:
        observe(db, ["1877020", "1877021"], ABSENT_LISTING_AT, day=kickoff.date())
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
    return [(r.id, r.first_fetched_at, r.model_run_at, r.kickoff_at_capture, r.captured_before_kickoff) for r in rows]


def refs_of(db, match_id) -> Dict[Tuple[str, str], ProviderEntityRef]:
    return {(r.provider, r.external_id): r for r in MatchRegistry(db).refs_for("match", match_id)}


def result_of(db, match_id) -> Optional[Tuple[int, int]]:
    row = db.query(MatchResult).filter(MatchResult.match_id == match_id).first()
    return None if row is None else (row.home_score, row.away_score)


def fresh(db, match_id) -> Match:
    db.expire_all()
    return db.query(Match).filter(Match.id == match_id).one()


def note_of(db, match: Match) -> Dict:
    return fresh(db, match.id).match_metadata[SUPERSEDED_CANDIDATES_KEY]


def no_note(db, match: Match) -> None:
    assert SUPERSEDED_CANDIDATES_KEY not in (fresh(db, match.id).match_metadata or {})


def assert_untouched(db, earlier: Match, kickoff: datetime = DROPPED_KICKOFF) -> None:
    row = fresh(db, earlier.id)
    assert row.match_date == kickoff.replace(tzinfo=None) and row.status == MatchStatus.SCHEDULED
    assert SUPERSEDED_KEY not in (row.match_metadata or {})
    assert len(snapshots_of(db, row.id)) == 9 and result_of(db, row.id) is None


def checksums(db) -> Dict[str, Tuple[int, str]]:
    """Row count and a digest of every row's text, per table: equal before and after means untouched."""
    out = {}
    for table in TABLES:
        count, digest = db.execute(text(
            f"SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') FROM {table} t")).first()
        out[table] = (count, digest)
    return out


def reader(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"psg-{suffix}@test.local", username=f"psg_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


# =========================================================== the join, at ingestion, on evidence
def test_a_listing_withdrawn_and_issued_again_is_the_same_match_on_the_same_row(db):
    earlier = earlier_listing(db)
    before = snapshots_of(db, earlier.id)
    assert len(before) == 9 and before[-1][4] is False, "the 26th's snapshot was retrieved after the earlier kickoff"
    observed = fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]
    assert observed["seen_at"] == LAST_LISTED_AT.isoformat() and observed["absent"]["listings"] == 1

    match = stored(db, played(), LIVE_POLL_AT)

    assert match.id == earlier.id, "the forecast and the result are on one row - the previous code made a second"
    assert [m.id for m in psg_lyon_rows(db)] == [earlier.id]
    row = fresh(db, earlier.id)
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert result_of(db, row.id) == (2, 0)
    assert snapshots_of(db, row.id) == before, "every snapshot kept its id, retrieval time, model date and capture facts"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == row.id).count() == 1
    refs = refs_of(db, row.id)
    assert set(refs) == {("gameforecast", FORECAST_EVENT), (PROVIDER, DEAD_ID), (PROVIDER, LIVE_ID)}
    assert refs[(PROVIDER, DEAD_ID)].ref_metadata["superseded_by"]["external_id"] == LIVE_ID
    assert refs[(PROVIDER, LIVE_ID)].matched_by == "superseded_listing"
    note = row.match_metadata[SUPERSEDED_KEY]
    assert note["previous_external_ids"] == [DEAD_ID] and note["external_id"] == LIVE_ID
    assert note["previous"]["kickoff_utc"] == DROPPED_KICKOFF.isoformat() and note["previous"]["status"] == "scheduled"
    assert note["evidence"]["basis"] == "observed" and note["evidence"]["last_named_at"] == LAST_LISTED_AT.isoformat()
    assert note["evidence"]["absent"]["last"] == ABSENT_LISTING_AT.isoformat()
    assert "last named" in note["reason"] and "complete listing(s) of its date" in note["reason"]
    for claim in ("stopped listing", "never played", "proven", "withdrawn"):
        assert claim not in note["reason"], claim
    assert row.external_api_id == f"{PROVIDER}:{LIVE_ID}" and note["previous"]["external_api_id"] == f"{PROVIDER}:{DEAD_ID}"


def test_repeated_ingestion_changes_nothing(db):
    earlier = earlier_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    first = dict(fresh(db, earlier.id).match_metadata[SUPERSEDED_KEY])
    again = stored(db, played(), LIVE_POLL_AT + timedelta(minutes=30))
    assert again.id == earlier.id and [m.id for m in psg_lyon_rows(db)] == [earlier.id]
    row = fresh(db, earlier.id)
    assert row.match_metadata[SUPERSEDED_KEY] == first, "the record is written once, by the pass that joined the listing"
    assert len(snapshots_of(db, row.id)) == 9 and result_of(db, row.id) == (2, 0) and len(refs_of(db, row.id)) == 3


def test_the_earlier_id_sent_again_with_its_old_kickoff_is_refused_not_applied(db):
    earlier = earlier_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    registry = MatchRegistry(db, now=LIVE_POLL_AT + timedelta(hours=1))
    assert registry.upsert_fixture(listing(DEAD_ID, DROPPED_KICKOFF)) is None
    refusal = registry.take_refusals()[0]
    assert refusal["external_id"] == DEAD_ID and "superseded by 742799" in refusal["reason"]
    row = fresh(db, earlier.id)
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert [m.id for m in psg_lyon_rows(db)] == [earlier.id]


def test_a_postponed_listing_whose_withdrawal_was_observed_is_re_issued_on_the_same_row(db):
    earlier = earlier_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_POSTPONED), DROPPED_KICKOFF - timedelta(hours=2))
    observe(db, ["1877020", "1877021"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date())
    assert fresh(db, earlier.id).status == MatchStatus.POSTPONED
    match = stored(db, played(), LIVE_POLL_AT)
    assert match.id == earlier.id and [m.id for m in psg_lyon_rows(db)] == [earlier.id]
    row = fresh(db, earlier.id)
    assert row.status == MatchStatus.FINISHED and row.match_metadata[SUPERSEDED_KEY]["previous"]["status"] == "postponed"


# =========================================================== the reviewer's case: no observation, no join
def test_an_overdue_listing_the_provider_just_refreshed_is_not_superseded(db):
    """The reviewer's reproduction: an overdue SCHEDULED fixture with no result whose old id the
    provider named again minutes before the new id arrived. Nothing was withdrawn; nothing joins."""
    earlier = earlier_listing(db, withdrawal_observed=False)
    refreshed_at = LIVE_POLL_AT - timedelta(minutes=1)
    observe(db, [DEAD_ID, "1877020"], refreshed_at, day=None, complete=False)   # the provider named it again
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF), refreshed_at)

    second = stored(db, played(), LIVE_POLL_AT)

    assert second.id != earlier.id, "joined on elapsed time alone - the previous implementation's defect"
    assert_untouched(db, earlier)
    note = note_of(db, second)
    assert [c["match_id"] for c in note["candidates"]] == [str(earlier.id)]
    why = note["candidates"][0]["why"]
    assert why.startswith("its withdrawal has not been observed") and refreshed_at.isoformat() in why
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["seen_at"] == refreshed_at.isoformat()
    for claim in ("stopped listing", "never played", "withdrawn", "dropped"):
        assert claim not in why, claim


def test_an_absence_contradicted_by_a_later_listing_counts_for_nothing(db):
    earlier = earlier_listing(db)                                                   # absent at 23:11 on the 25th
    observe(db, [DEAD_ID], LIVE_POLL_AT - timedelta(hours=3), day=None, complete=False)   # named again on the 26th
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != earlier.id
    assert_untouched(db, earlier)
    why = note_of(db, second)["candidates"][0]["why"]
    assert why.startswith("its withdrawal is contradicted") and ABSENT_LISTING_AT.isoformat() in why
    assert MatchRegistry.withdrawal_observed(fresh(db, earlier.id), PROVIDER) is None, "no observation stands after the later naming"


@pytest.mark.parametrize("order", ["old-then-new", "new-then-old"])
def test_both_ids_in_one_listing_are_two_rows_whichever_comes_first(db, order):
    """One calendar answer naming both 1877019 (still on the 25th) and 742799 (the 26th): the
    provider returns both ids, so neither replaces the other, in either processing order. The sync
    tells the registry what the answer named before it stores a single fixture of it."""
    earlier = earlier_listing(db)                                        # absent from the 25th's listing at 23:11
    batch = [listing(DEAD_ID, DROPPED_KICKOFF), listing(LIVE_ID, PLAYED_KICKOFF)]
    if order == "new-then-old":
        batch.reverse()
    at = PLAYED_KICKOFF - timedelta(hours=8)
    observe(db, [f.external_id for f in batch], at, day=None, complete=False)   # a calendar: names, no absence
    rows = [stored(db, f, at) for f in batch]
    assert len({r.id for r in rows}) == 2 and earlier.id in {r.id for r in rows}
    assert_untouched(db, earlier)
    new_row = next(r for r in rows if r.id != earlier.id)
    why = note_of(db, new_row)["candidates"][0]["why"]
    assert why.startswith("its withdrawal is contradicted") and at.isoformat() in why
    assert len(psg_lyon_rows(db)) == 2


def test_without_any_observation_nothing_joins(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != earlier.id
    assert_untouched(db, earlier)
    why = note_of(db, second)["candidates"][0]["why"]
    assert why.startswith("its withdrawal has not been observed") and LAST_LISTED_AT.isoformat() in why


def test_an_incomplete_listing_records_no_absence(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    observe(db, ["1877020"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date(), complete=False)   # a page unread
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER].get("absent") is None
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != earlier.id and len(psg_lyon_rows(db)) == 2


def test_a_listing_of_another_day_or_competition_records_no_absence(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    observe(db, ["9001"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date() + timedelta(days=1))
    observe(db, ["9002"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date(), key="champions_league")
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER].get("absent") is None


def test_a_row_named_under_any_of_its_ids_is_present(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    MatchRegistry(db, now=LAST_LISTED_AT).set_ref("match", earlier.id, PROVIDER, "1877099", confidence="high",
                                                   matched_by="name_kickoff")
    observe(db, ["1877099", "1877020"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date())
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER].get("absent") is None


# =========================================================== the day sync records only fresh, complete answers
class ListingProvider(MatchDataProvider):
    """A fixtures provider whose answer the test scripts: a list, an outage, or a cut listing."""

    name = PROVIDER
    integration_status = "test"

    def __init__(self):
        self.answers: Dict[date, List[ProviderFixture]] = {}
        self.fail = False
        self.truncated_keys: set = set()
        self.cut = False
        self.calls = 0
        self.budget = None

    def is_configured(self) -> bool:
        return True

    def askable(self, keys):
        return list(keys)

    def list_competitions(self, keys):
        return [listing("x", DROPPED_KICKOFF, key=k).competition for k in keys]

    def get_fixtures(self, day: date, keys) -> List[ProviderFixture]:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailableError("upstream is down", provider=self.name)
        self.truncated_keys = set(keys) if self.cut else set()
        return list(self.answers.get(day, []))

    def get_live(self, keys) -> List[ProviderFixture]:
        return []

    def get_results(self, date_from: date, date_to: date, keys) -> List[ProviderFixture]:
        return []

    def get_standings(self, key):
        return []


def day_sync(db, provider: ListingProvider, clock: Clock, cache: MatchCache) -> MatchDataService:
    return MatchDataService(db, providers=[provider], cache=cache, now=clock(), keys=[LEAGUE])


def test_the_day_sync_observes_only_a_fresh_complete_answer(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 0)
    earlier = earlier_listing(db, withdrawal_observed=False)
    clock = Clock(ABSENT_LISTING_AT)
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    provider = ListingProvider()
    provider.answers[DROPPED_KICKOFF.date()] = [listing("1877020", DROPPED_KICKOFF.replace(hour=14))]

    meta = day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert meta.source == "provider" and provider.calls == 1, (meta.source, meta.errors, meta.declined)
    record = fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]
    assert record["absent"] == {"since": ABSENT_LISTING_AT.isoformat(), "last": ABSENT_LISTING_AT.isoformat(),
                                "listings": 1, "day": DROPPED_KICKOFF.date().isoformat()}

    clock.tick(600)                                                      # the same answer, from the cache
    meta = day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert meta.source == "cache" and provider.calls == 1
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 1, "a copy is no observation"

    clock.tick(3600); provider.fail = True                               # the provider is down; a stale copy is served
    meta = day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert meta.source == "stale-cache" and provider.calls == 2
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 1

    clock.tick(7 * 24 * 3600)                                            # no copy left either: an outage
    meta = day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert meta.source == "database" and meta.errors
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 1

    provider.fail, provider.cut = False, True                            # back, but a page unread
    clock.tick(3600)                                                     # past the chain's cool-down after the outage
    meta = day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert meta.source == "provider", (meta.source, meta.errors)
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 1, "a cut listing says nothing"

    provider.cut = False; clock.tick(7 * 24 * 3600)                      # fresh and complete again
    day_sync(db, provider, clock, cache).sync_day(DROPPED_KICKOFF.date())
    assert fresh(db, earlier.id).match_metadata[LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 2


def test_the_day_sync_names_the_rows_it_lists_before_storing_them(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 0)
    earlier = earlier_listing(db)                                        # absent on the 25th
    clock = Clock(PLAYED_KICKOFF - timedelta(hours=8))
    cache = MatchCache(client=LockingFakeRedis(clock=clock))
    provider = ListingProvider()
    provider.answers[PLAYED_KICKOFF.date()] = [listing(LIVE_ID, PLAYED_KICKOFF),
                                               listing(DEAD_ID, PLAYED_KICKOFF - timedelta(hours=3))]
    day_sync(db, provider, clock, cache).sync_day(PLAYED_KICKOFF.date())
    assert len(psg_lyon_rows(db)) == 2, "both ids named in one listing: two rows, in the order the provider sent them"
    assert MatchRegistry.withdrawal_observed(fresh(db, earlier.id), PROVIDER) is None


# =========================================================== what stays two rows
def test_the_return_leg_is_another_match(db):
    earlier = earlier_listing(db)
    reverse = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, home=LYON, away=PSG, status=STATUS_FINISHED,
                                 home_score=2, away_score=0), LIVE_POLL_AT)
    assert reverse.id != earlier.id
    assert_untouched(db, earlier)
    no_note(db, reverse)


def test_another_competition_is_another_match(db):
    earlier = earlier_listing(db)
    cup = stored(db, dataclasses.replace(played(), competition=ProviderCompetition(
        provider=PROVIDER, external_id="livescore-champions_league", name="Champions League",
        key="champions_league", country=None, country_code=None)), LIVE_POLL_AT)
    assert cup.id != earlier.id
    assert_untouched(db, earlier)
    assert SUPERSEDED_KEY not in (fresh(db, cup.id).match_metadata or {})


def test_a_played_listing_is_not_replaced(db):
    earlier = earlier_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_FINISHED, home_score=1, away_score=1),
           DROPPED_KICKOFF + timedelta(hours=2))
    observe(db, ["1877020"], ABSENT_LISTING_AT + timedelta(hours=1), day=DROPPED_KICKOFF.date())
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != earlier.id
    assert [c["why"] for c in note_of(db, second)["candidates"]] == ["it has a stored result"]
    assert result_of(db, earlier.id) == (1, 1)


def test_a_listing_still_to_be_played_is_not_replaced_yet(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    early = stored(db, listing(LIVE_ID, PLAYED_KICKOFF), DROPPED_KICKOFF - timedelta(days=1))
    assert early.id != earlier.id
    assert_untouched(db, earlier)
    assert note_of(db, early)["candidates"][0]["why"].startswith("its withdrawal has not been observed")


def test_an_absence_observed_before_the_kickoff_window_closed_still_waits_for_it(db):
    earlier = earlier_listing(db, withdrawal_observed=False)
    observe(db, ["1877020"], DROPPED_KICKOFF - timedelta(hours=1), day=DROPPED_KICKOFF.date())
    just_before = DROPPED_KICKOFF + UNSETTLED_GRACE - timedelta(minutes=1)
    second = stored(db, listing(LIVE_ID, PLAYED_KICKOFF), just_before)
    assert second.id != earlier.id
    assert_untouched(db, earlier)
    assert [c["why"] for c in note_of(db, second)["candidates"]] == ["its kickoff window has not closed"]


def test_a_different_round_is_another_meeting(db):
    earlier = earlier_listing(db)
    other = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, round_="Regular Season - 12"), LIVE_POLL_AT)
    assert other.id != earlier.id
    assert_untouched(db, earlier)
    assert note_of(db, other)["candidates"][0]["why"].startswith("a different round")


def test_the_same_round_in_another_providers_words_is_the_same_matchday(db):
    earlier = earlier_listing(db)
    match = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, status=STATUS_FINISHED, home_score=2, away_score=0,
                               round_="Regular Season - 8"), LIVE_POLL_AT)
    assert match.id == earlier.id


def test_an_earlier_kickoff_is_not_a_re_issue(db):
    earlier = earlier_listing(db)
    before = stored(db, listing(LIVE_ID, DROPPED_KICKOFF - timedelta(days=1)), DROPPED_KICKOFF + timedelta(days=3))
    assert before.id != earlier.id
    assert_untouched(db, earlier)
    no_note(db, before)


def test_a_listing_a_fortnight_later_is_left_to_a_person(db):
    earlier = earlier_listing(db)
    far = DROPPED_KICKOFF + SUPERSEDED_LISTING_WINDOW + timedelta(days=1)
    later = stored(db, listing(LIVE_ID, far), far - timedelta(days=1))
    assert later.id != earlier.id
    assert_untouched(db, earlier)
    no_note(db, later)
    edge = DROPPED_KICKOFF + SUPERSEDED_LISTING_WINDOW
    registry = MatchRegistry(db, now=edge - timedelta(hours=1))
    league = registry.upsert_league(played().competition)
    home, away = (db.query(Team).filter(Team.id == i).one() for i in (earlier.home_team_id, earlier.away_team_id))
    on_the_edge, _ = registry.superseded_listing_for(listing("742801", edge), home, away, league)
    assert on_the_edge is not None and on_the_edge.id == earlier.id, "fourteen days to the minute is inside the window"
    past_it, unproven = registry.superseded_listing_for(listing("742802", edge + timedelta(minutes=1)), home, away, league)
    assert past_it is None and unproven == []


def test_two_earlier_listings_decide_nothing(db):
    first = earlier_listing(db, kickoff=DROPPED_KICKOFF - timedelta(days=1), external_id="1877018")
    second = earlier_listing(db)
    third = stored(db, played(), LIVE_POLL_AT)
    assert third.id not in (first.id, second.id)
    assert_untouched(db, second)
    assert sorted(c["why"] for c in note_of(db, third)["candidates"]) == ["another stored listing qualifies as well"] * 2


def test_another_squad_is_another_club(db):
    earlier = earlier_listing(db)
    youth = stored(db, listing(LIVE_ID, PLAYED_KICKOFF, home=f"{PSG} U19", away=f"{LYON} U19"), LIVE_POLL_AT)
    assert youth.id != earlier.id
    assert_untouched(db, earlier)
    registry = MatchRegistry(db, now=LIVE_POLL_AT)
    league = registry.upsert_league(played().competition)
    home, away = (db.query(Team).filter(Team.id == i).one() for i in (earlier.home_team_id, earlier.away_team_id))
    match, unproven = registry.superseded_listing_for(
        listing(LIVE_ID, PLAYED_KICKOFF, home=f"{PSG} U19", away=f"{LYON} U19"), home, away, league)
    assert match is None and unproven[0]["why"].startswith("the provider names another squad")


def test_a_cup_or_national_team_fixture_is_never_joined_by_this_rule(db):
    for key, (first_id, second_id) in (("champions_league", ("7001", "7002")), ("national_teams_friendlies", ("7003", "7004"))):
        first = stored(db, listing(first_id, DROPPED_KICKOFF, key=key, round_=None), LISTED_AT)
        observe(db, [first_id], LAST_LISTED_AT, day=DROPPED_KICKOFF.date(), key=key)
        observe(db, ["x"], ABSENT_LISTING_AT, day=DROPPED_KICKOFF.date(), key=key)
        second = stored(db, listing(second_id, PLAYED_KICKOFF, key=key, round_=None, status=STATUS_FINISHED,
                                    home_score=2, away_score=0), LIVE_POLL_AT)
        assert second.id != first.id, key
        row = fresh(db, first.id)
        assert row.status == MatchStatus.SCHEDULED and row.match_date == DROPPED_KICKOFF.replace(tzinfo=None)
        assert note_of(db, second)["candidates"][0]["why"].startswith("not a league competition"), key


def test_two_live_ids_of_two_meetings_are_untouched(db):
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


def attach_people(db, match: Match) -> Dict[str, object]:
    """Representative rows a reader, an expert and the settlement left on the earlier listing."""
    user = reader(db)
    snapshots = db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id == match.id)\
        .order_by(ProviderForecastSnapshot.first_fetched_at).all()
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                            priority_level=100, reasoning="expert view")
    saved = SavedMatch(id=uuid.uuid4(), user_id=user.id, match_id=match.id, note="watch this one")
    slip = SelectionSlip(id=uuid.uuid4(), user_id=user.id, name="Sunday double")
    leg = SelectionSlipLeg(id=uuid.uuid4(), slip_id=slip.id, match_id=match.id, position=0, provider="gameforecast",
                           snapshot_id=snapshots[-2].id, market_id="match_result", outcome="home", period="regulation",
                           probability=Decimal("0.61"), probability_source="provider", normalisation_version="v1",
                           model_run_at=snapshots[-2].model_run_at, forecast_fetched_at=snapshots[-2].first_fetched_at,
                           kickoff_at_add=match.match_date)
    db.add_all([prediction, saved, slip, leg])
    db.flush()
    audit = [PredictionAudit(id=uuid.uuid4(), prediction_id=prediction.id, user_id=user.id, action=action,
                             action_description=f"{action} by the expert", changes_summary=action)
             for action in ("created", "published")]
    settled_at = datetime(2026, 10, 26, 0, 30)
    forecast_result = ProviderForecastResult(
        id=uuid.uuid4(), snapshot_id=snapshots[0].id, match_id=match.id, provider="gameforecast", outcome=None,
        is_correct=None, actual_outcome=None, settled_at=settled_at, settled_by_system=True,
        rules_version="soccer-regulation-time-v2", void_reason="no result stored for the listing",
        snapshot_captured_at=snapshots[0].first_fetched_at, kickoff_at=match.match_date)
    prediction_result = PredictionResult(
        id=uuid.uuid4(), prediction_id=prediction.id, outcome=PredictionOutcome.VOID, is_correct=None,
        actual_outcome=None, settled_at=settled_at, settled_by_system=True, rules_version="soccer-regulation-time-v2",
        void_reason="no result stored for the listing")
    db.add_all(audit + [forecast_result, prediction_result])
    db.flush()
    return {"prediction": prediction.id, "saved": saved.id, "slip": slip.id, "leg": leg.id,
            "leg_snapshot": snapshots[-2].id, "forecast_result": forecast_result.id,
            "prediction_result": prediction_result.id, "audit": [a.id for a in audit]}


def row_text(db, table: str, row_id) -> str:
    return db.execute(text(f"SELECT t::text FROM {table} t WHERE id = :rid"), {"rid": str(row_id)}).scalar()


def without_match_id(db, table: str, row_id) -> str:
    return db.execute(text(f"SELECT (to_jsonb(t) - 'match_id' - 'updated_at')::text FROM {table} t WHERE id = :rid"),
                      {"rid": str(row_id)}).scalar()


def the_split(db, *, withdrawal_observed: bool = True) -> Tuple[Match, Match, Dict[str, object]]:
    earlier = earlier_listing(db, withdrawal_observed=withdrawal_observed)
    people = attach_people(db, earlier)
    second = stored(db, played(), LIVE_POLL_AT)
    assert second.id != earlier.id, "the split, as production holds it"
    MatchRegistry(db, now=LIVE_POLL_AT + timedelta(minutes=11)).set_ref(
        "match", second.id, "api_football", "1552800", confidence="exact", matched_by="provider_id")
    db.expire_all()
    return earlier, second, people


def apply(db, repair_script, pair, deps, at: datetime, reviewed: Optional[str] = None) -> Dict[str, int]:
    moved = repair_script.apply_supersession(db, pair, deps, now=at, reviewed_evidence=reviewed)
    db.flush()
    db.expunge_all()
    return moved


AT = LIVE_POLL_AT + timedelta(hours=2)
EXPECTED_MOVES = {"predictions.provider_forecast_snapshots": 9, "predictions.provider_forecasts": 1,
                  "predictions.provider_forecast_results": 1, "predictions.provider_entity_refs": 2,
                  "predictions.predictions": 1, "users.saved_matches": 1, "users.selection_slip_legs": 1}


def test_the_repair_finds_the_split_and_plans_every_reference(db, repair_script, as_the_previous_code):
    earlier, second, _ = the_split(db)
    deps = repair_script.dependents(db)
    pairs = repair_script.superseded_listings(db, now=AT)
    assert [(p.stale.id, p.successor.id) for p in pairs] == [(str(earlier.id), str(second.id))]
    pair = repair_script.plan_supersession(db, pairs[0], deps)
    assert pair.provider == PROVIDER and pair.dead_ids == [DEAD_ID] and pair.live_ids == [LIVE_ID]
    assert pair.withdrawal_observed and pair.evidence.startswith("withdrawal observed")
    assert LAST_LISTED_AT.isoformat() in pair.evidence and ABSENT_LISTING_AT.isoformat() in pair.evidence
    assert pair.safe, pair.blockers
    assert pair.moves == EXPECTED_MOVES
    assert len(pair.consequences) == 2
    assert "3 prediction(s), slip leg(s) or saved match(es)" in pair.consequences[0]
    assert "1 snapshot(s) retrieved before the match was played" in pair.consequences[1]


def test_an_unobserved_withdrawal_is_reported_as_such_and_folds_only_with_reviewed_evidence(db, repair_script, as_the_previous_code):
    earlier, second, _ = the_split(db, withdrawal_observed=False)
    second_id = second.id
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=AT)[0], deps)
    assert not pair.withdrawal_observed and pair.evidence.startswith("withdrawal NOT observed")
    assert LAST_LISTED_AT.isoformat() in pair.evidence and pair.safe
    before = checksums(db)
    with pytest.raises(ValueError, match="reviewed evidence"):
        repair_script.apply_supersession(db, pair, deps, now=AT)
    db.flush()
    assert checksums(db) == before, "refused before anything moved"
    apply(db, repair_script, pair, deps, AT, reviewed="backend log 2026-10-25: listing of the 25th at 23:11:00Z did not name 1877019; last named 17:08:50Z")
    note = fresh(db, second_id).match_metadata[SUPERSEDED_KEY]
    assert note["evidence"]["basis"] == "reviewed" and "23:11:00Z" in note["evidence"]["reviewed"]
    assert note["reason"].startswith("Folded on a person's instruction") and "withdrawal NOT observed" in note["reason"]
    for claim in ("stopped listing", "never played", "proven"):
        assert claim not in note["reason"], claim


def test_the_dry_run_changes_nothing(db, repair_script, as_the_previous_code):
    the_split(db)
    deps = repair_script.dependents(db)
    before = checksums(db)
    for pair in repair_script.superseded_listings(db, now=AT):
        repair_script.plan_supersession(db, pair, deps)
    db.flush()
    assert checksums(db) == before


def test_the_repair_folds_the_earlier_listing_and_preserves_every_reference(db, repair_script, as_the_previous_code):
    earlier, second, people = the_split(db)
    earlier_id, second_id = earlier.id, second.id
    before_snapshots = snapshots_of(db, earlier_id)
    previous_meta = dict(fresh(db, earlier_id).match_metadata)
    kept = {name: without_match_id(db, table, people[name]) for name, table in (
        ("leg", "users.selection_slip_legs"), ("forecast_result", "predictions.provider_forecast_results"),
        ("prediction", "predictions.predictions"), ("saved", "users.saved_matches"))}
    kept_whole = {"prediction_result": row_text(db, "predictions.prediction_results", people["prediction_result"]),
                  "slip": row_text(db, "users.selection_slips", people["slip"]),
                  "audit": [row_text(db, "predictions.prediction_audit", a) for a in people["audit"]]}
    result_counts = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                     for t in ("predictions.prediction_results", "predictions.provider_forecast_results")}
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=AT)[0], deps)

    moved = apply(db, repair_script, pair, deps, AT)

    assert moved == EXPECTED_MOVES
    assert [m.id for m in psg_lyon_rows(db)] == [second_id], "the earlier row is gone, the successor stands"
    row = db.query(Match).filter(Match.id == second_id).one()
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and row.status == MatchStatus.FINISHED
    assert result_of(db, row.id) == (2, 0) and row.external_api_id == f"{PROVIDER}:{LIVE_ID}"
    assert snapshots_of(db, row.id) == before_snapshots, "nine snapshots: ids, timestamps, model dates and capture flags as they were"
    assert [s for s in snapshots_of(db, row.id) if s[4] is False] == [before_snapshots[-1]], "the one post-kickoff flag stays false"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == row.id).count() == 1
    refs = refs_of(db, row.id)
    assert set(refs) == {("gameforecast", FORECAST_EVENT), (PROVIDER, DEAD_ID), (PROVIDER, LIVE_ID), ("api_football", "1552800")}
    assert refs[(PROVIDER, DEAD_ID)].ref_metadata["superseded_by"]["external_id"] == LIVE_ID
    # every dependent row: on the survivor, otherwise byte for byte as it was
    for name, table in (("leg", "users.selection_slip_legs"), ("forecast_result", "predictions.provider_forecast_results"),
                        ("prediction", "predictions.predictions"), ("saved", "users.saved_matches")):
        assert db.execute(text(f"SELECT match_id FROM {table} WHERE id = :rid"), {"rid": str(people[name])}).scalar() == second_id
        assert without_match_id(db, table, people[name]) == kept[name], name
    leg = db.query(SelectionSlipLeg).filter(SelectionSlipLeg.id == people["leg"]).one()
    assert leg.snapshot_id == people["leg_snapshot"]
    assert db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.id == leg.snapshot_id).one().match_id == second_id
    assert row_text(db, "predictions.prediction_results", people["prediction_result"]) == kept_whole["prediction_result"]
    assert row_text(db, "users.selection_slips", people["slip"]) == kept_whole["slip"]
    assert [row_text(db, "predictions.prediction_audit", a) for a in people["audit"]] == kept_whole["audit"]
    assert {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in result_counts} == result_counts, "no re-scoring"
    note = row.match_metadata[SUPERSEDED_KEY]
    assert note["previous"]["match_id"] == str(earlier_id) and note["previous"]["status"] == "SCHEDULED"
    assert note["previous"]["match_metadata"]["last_synced_at"] == previous_meta["last_synced_at"]
    assert note["previous"]["match_metadata"][LISTINGS_KEY][PROVIDER]["absent"]["listings"] == 1
    assert note["evidence"]["basis"] == "observed" and note["moved"] == pair.moves
    assert db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_id == earlier_id).count() == 0
    orphans = db.execute(text("""
        SELECT count(*) FROM predictions.provider_entity_refs r
        WHERE r.entity_type = 'match' AND NOT EXISTS (SELECT 1 FROM predictions.matches m WHERE m.id = r.entity_id)
    """)).scalar()
    assert orphans == 0


def test_a_second_application_changes_nothing(db, repair_script, as_the_previous_code):
    the_split(db)
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=AT)[0], deps)
    apply(db, repair_script, pair, deps, AT)
    after_first = checksums(db)
    assert repair_script.superseded_listings(db, now=AT) == []
    db.flush()
    assert checksums(db) == after_first


def test_the_repair_touches_no_other_row(db, repair_script, as_the_previous_code):
    bystander = stored(db, listing("6001", PLAYED_KICKOFF + timedelta(hours=1), home="Marseille", away="Nice",
                                   status=STATUS_FINISHED, home_score=0, away_score=0), LIVE_POLL_AT)
    bystander_id = str(bystander.id)
    bystander_before = row_text(db, "predictions.matches", bystander_id)
    the_split(db)
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=AT)[0], deps)
    apply(db, repair_script, pair, deps, AT)
    assert row_text(db, "predictions.matches", bystander_id) == bystander_before
    assert db.query(Match).count() == 2


def test_the_repair_does_not_see_a_played_earlier_listing(db, repair_script, as_the_previous_code):
    earlier = earlier_listing(db)
    stored(db, listing(DEAD_ID, DROPPED_KICKOFF, status=STATUS_FINISHED, home_score=1, away_score=1),
           DROPPED_KICKOFF + timedelta(hours=2))
    stored(db, played(), LIVE_POLL_AT)
    assert repair_script.superseded_listings(db, now=AT) == []
    assert result_of(db, earlier.id) == (1, 1)


def test_the_repair_refuses_when_the_rounds_differ(db, repair_script, as_the_previous_code):
    earlier = earlier_listing(db)
    stored(db, dataclasses.replace(played(), round="Regular Season - 12"), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=AT)
    assert len(pairs) == 1 and not pairs[0].safe and any("rounds differ" in b for b in pairs[0].blockers)
    assert_untouched(db, earlier)


def test_a_uniqueness_breaking_move_refuses_without_a_partial_change(db, repair_script, as_the_previous_code):
    earlier, second, _ = the_split(db)
    db.add(ProviderForecastRecord(
        id=uuid.uuid4(), match_id=second.id, provider="gameforecast", external_event_id="99999",
        home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
        match_confidence="exact", matched_by="name_kickoff", fetched_at=LIVE_POLL_AT.replace(tzinfo=None)))
    db.flush()
    deps = repair_script.dependents(db)
    pair = repair_script.plan_supersession(db, repair_script.superseded_listings(db, now=AT)[0], deps)
    assert not pair.safe and any("provider_forecasts" in b and "collide" in b for b in pair.blockers)
    before = checksums(db)
    attempt = db.begin_nested()                               # the script's own transaction, as a savepoint here
    with pytest.raises(Exception):
        repair_script.fold_rows(db, deps, "predictions.matches", str(second.id), [str(earlier.id)])
    attempt.rollback()
    assert checksums(db) == before, "a refused fold leaves every table as it was"


def test_the_repair_reports_a_non_league_pair_and_refuses_it(db, repair_script, as_the_previous_code):
    stale = stored(db, listing("7003", DROPPED_KICKOFF, key="national_teams_friendlies", round_=None), LISTED_AT)
    stored(db, listing("7004", PLAYED_KICKOFF, key="national_teams_friendlies", round_=None, status=STATUS_FINISHED,
                       home_score=2, away_score=0), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=AT)
    assert len(pairs) == 1 and pairs[0].stale.id == str(stale.id) and not pairs[0].safe
    assert any("not a league competition" in b for b in pairs[0].blockers)


def test_the_repair_refuses_two_successors(db, repair_script, as_the_previous_code):
    earlier = earlier_listing(db)
    stored(db, played(), LIVE_POLL_AT)
    stored(db, listing("742800", PLAYED_KICKOFF + timedelta(days=1)), LIVE_POLL_AT)
    pairs = repair_script.superseded_listings(db, now=AT)
    assert len(pairs) == 2 and all(not p.safe for p in pairs)
    assert all(any("possible successors" in b for b in p.blockers) for p in pairs)
    assert_untouched(db, earlier)
