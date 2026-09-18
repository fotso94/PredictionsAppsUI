"""
The forecast-coverage diagnosis: every cause must be evidenced, and what cannot be is said so.

`scripts/diagnose_forecast_coverage.py` answers "why has this fixture no prematch forecast?".
These tests pin the part that is easy to get wrong and expensive to get wrong: a cause is only
reported when a stored record proves it, and a fixture whose cause cannot be proved comes back as
`unexplained` rather than being folded into the most plausible bucket. A diagnosis that guesses
"the provider published nothing" is worse than one that admits it does not know, because it closes
an investigation that should stay open.

One fixture per cause is built in the database, together with exactly the stored state (cache
keys, budget counters, snapshots, refs) that the classifier is supposed to read.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
No provider is ever called: the diagnosis makes no HTTP request at all, which is the point of it.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import League, Match, MatchStatus, Team
from app.models.provider_data import (
    ProviderEntityRef,
    ProviderForecastRecord,
    ProviderForecastSnapshot,
)
from app.services.forecast_service import LAST_SYNC_KEY, PENDING_KEY, STATUS_KEY, _forecast_to_dict
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderForecast
from app.services.providers.budget import budget_key
from app.services.providers.gameforecast import LEAGUE_STORE_KEY
from scripts import diagnose_forecast_coverage as diag
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

PROVIDER = "gameforecast"
KEY = "premier_league"

# Far enough ahead that no other test file has fixtures in the window this diagnosis looks at.
BASE = (datetime.now(timezone.utc) + timedelta(days=60)).replace(microsecond=0)
NOW = BASE - timedelta(hours=6)
CREATED = NOW - timedelta(days=2)          # the fixture row existed before any fetch below
FETCHED = NOW - timedelta(hours=1)         # a competition turn that ran after the row existed


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
    """Session joined to an outer transaction; nothing this test writes survives it."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def cache(redis):
    return MatchCache(client=redis)


# ----------------------------------------------------------------------------- helpers
def _league(db, key: str = KEY) -> League:
    league = MatchRegistry(db).ensure_canonical_league(key)
    db.flush()
    return league


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, short_name=name[:10], country="England",
                external_api_id=f"test:{uuid.uuid4().hex[:12]}", external_api_source="test")
    db.add(team)
    db.flush()
    return team


def _fixture(db, league: League, home: str, away: str, kickoff: datetime = BASE,
             created_at: datetime = CREATED, status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    match = Match(id=uuid.uuid4(), home_team_id=_team(db, home).id, away_team_id=_team(db, away).id,
                  league_id=league.id, match_date=kickoff.astimezone(timezone.utc).replace(tzinfo=None),
                  status=status, external_api_id=f"test:{uuid.uuid4().hex[:12]}",
                  external_api_source="test",
                  created_at=created_at.astimezone(timezone.utc).replace(tzinfo=None),
                  updated_at=created_at.astimezone(timezone.utc).replace(tzinfo=None))
    db.add(match)
    db.flush()
    return match


def _snapshot(db, match: Match, retrieved: datetime, prematch: bool = True) -> ProviderForecastSnapshot:
    naive = retrieved.astimezone(timezone.utc).replace(tzinfo=None)
    snapshot = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider=PROVIDER, external_event_id="evt-snap",
        content_hash=uuid.uuid4().hex, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
        match_confidence="exact", matched_by="name_kickoff", first_fetched_at=naive,
        last_fetched_at=naive, kickoff_at_capture=match.match_date,
        captured_before_kickoff=prematch)
    db.add(snapshot)
    db.flush()
    return snapshot


def _record(db, match: Match, external_event_id: str = "evt-orphan") -> ProviderForecastRecord:
    record = ProviderForecastRecord(
        id=uuid.uuid4(), match_id=match.id, provider=PROVIDER, external_event_id=external_event_id,
        home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2, match_confidence="exact",
        matched_by="name_kickoff", fetched_at=FETCHED.replace(tzinfo=None))
    db.add(record)
    db.flush()
    return record


def _ref(db, match: Match, external_event_id: str = "evt-ref") -> ProviderEntityRef:
    ref = ProviderEntityRef(id=uuid.uuid4(), entity_type="match", entity_id=match.id,
                            provider=PROVIDER, external_id=external_event_id,
                            match_confidence="exact", matched_by="name_kickoff")
    db.add(ref)
    db.flush()
    return ref


def _held(cache: MatchCache, home: str, away: str, kickoff: datetime, event: str = "evt-held",
          key: str = KEY) -> None:
    """Put one already-paid-for forecast in the pending cache, the way sync_competition does."""
    forecast = ProviderForecast(provider=PROVIDER, external_event_id=event, home_name=home,
                                away_name=away, kickoff_utc=kickoff, competition_key=key,
                                home_prob=0.5, draw_prob=0.3, away_prob=0.2, fetched_at=FETCHED)
    cache.set(PENDING_KEY.format(provider=PROVIDER, key=key), [_forecast_to_dict(forecast)],
              ttl=3600, stale_ttl=3600)


def _synced(cache: MatchCache, when: datetime = FETCHED, key: str = KEY) -> None:
    cache.set(LAST_SYNC_KEY.format(provider=PROVIDER, key=key), when.isoformat(), ttl=3600, stale_ttl=3600)


def _run(cache: MatchCache, **report) -> None:
    cache.set(STATUS_KEY.format(provider=PROVIDER), report, ttl=3600, stale_ttl=3600)


def _spend_allowance(redis: FakeRedis, used: int = 8) -> None:
    redis.set(budget_key(PROVIDER), used)


def _diagnose(db, cache, redis, keys=(KEY,), days: int = 1):
    return diag.diagnose(db, cache=cache, provider=PROVIDER, now=NOW, days=days,
                         keys=list(keys), budget_client=redis)


def _only(result, cause: str = None):
    """The single classified fixture in the report (these tests build exactly one miss)."""
    missing = [entry for comp in result["competitions"] for entry in comp["missing"]]
    assert len(missing) == 1, missing
    if cause is not None:
        assert missing[0]["cause"] == cause, missing[0]
    return missing[0]


# ------------------------------------------------------------------- coverage counting
def test_a_prematch_snapshot_counts_as_coverage_and_is_not_classified(db, cache, redis):
    league = _league(db)
    match = _fixture(db, league, "Arsenal", "Chelsea")
    _snapshot(db, match, retrieved=FETCHED)
    _synced(cache)

    result = _diagnose(db, cache, redis)

    comp = result["competitions"][0]
    assert (comp["fixtures"], comp["with_prematch_forecast"], comp["without"]) == (1, 1, 0)
    assert result["totals"]["causes"] == {}


def test_a_forecast_retrieved_after_kickoff_is_not_prematch_coverage(db, cache, redis):
    """A late forecast must never be presented as evidence available before the match."""
    league = _league(db)
    match = _fixture(db, league, "Arsenal", "Chelsea")
    _snapshot(db, match, retrieved=BASE + timedelta(hours=2), prematch=False)
    _synced(cache)

    result = _diagnose(db, cache, redis)

    comp = result["competitions"][0]
    assert (comp["with_prematch_forecast"], comp["without"]) == (0, 1)
    assert "after the" in _only(result, "only_after_kickoff")["evidence"]


def test_a_postponed_fixture_is_excluded_from_both_sides_of_the_ratio(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea", status=MatchStatus.POSTPONED)
    _synced(cache)

    result = _diagnose(db, cache, redis)

    assert result["excluded_by_status"] == 1
    assert result["totals"] == {"fixtures": 0, "with_prematch_forecast": 0, "without": 0, "causes": {}}


# ------------------------------------------------------------- (a) the turn never ran
def test_never_fetched_competition_with_a_spent_allowance_is_not_fetched(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _spend_allowance(redis, used=8)
    _run(cache, synced_at=FETCHED.isoformat(), paused=True,
         error="Daily request budget for gameforecast exhausted (8/8 used)")

    entry = _only(_diagnose(db, cache, redis), "not_fetched")

    assert entry["sub_cause"] == "daily_allowance_spent"
    assert "never been fetched" in entry["evidence"]
    assert "0 remaining" in entry["evidence"]


def test_a_competition_the_last_run_deferred_names_that_run(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _spend_allowance(redis, used=8)
    _run(cache, synced_at=FETCHED.isoformat(), order=[KEY], deferred=[KEY],
         error="daily request allowance for gameforecast is spent; 1 competition(s) deferred")

    entry = _only(_diagnose(db, cache, redis), "not_fetched")

    assert entry["sub_cause"] == "daily_allowance_spent"
    assert "deferred it to the next reset" in entry["evidence"]


def test_a_fixture_added_after_the_last_fetch_is_not_provider_silence(db, cache, redis):
    """The competition was fetched, but before this fixture existed: it was never offered."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea", created_at=FETCHED + timedelta(minutes=10))
    _synced(cache, when=FETCHED)
    _run(cache, synced_at=FETCHED.isoformat(), competitions={KEY: {"fetched": 5, "attached": 5}})

    entry = _only(_diagnose(db, cache, redis), "not_fetched")

    assert "before this fixture row existed" in entry["evidence"]


# ------------------------------------------------------ (b) the provider returned nothing
def test_a_retained_fetch_report_evidences_provider_silence_per_event(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    cache.set(diag.COMPETITION_STATUS_KEY.format(provider=PROVIDER, key=KEY),
              {"fetched_at": FETCHED.isoformat(), "events_returned": 6,
               "discarded_events": [{"external_event_id": "evt-9", "home": "Arsenal FC",
                                     "away": "Chelsea FC", "reason": "no_predictions"}]},
              ttl=3600, stale_ttl=3600)

    entry = _only(_diagnose(db, cache, redis), "provider_no_forecast")

    assert "evt-9" in entry["evidence"] and "no_predictions" in entry["evidence"]


def test_a_fetch_report_older_than_the_fixture_row_evidences_nothing(db, cache, redis):
    """The response it describes was read before this fixture was in our calendar."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea", created_at=FETCHED)
    _synced(cache, when=FETCHED + timedelta(minutes=5))
    cache.set(diag.COMPETITION_STATUS_KEY.format(provider=PROVIDER, key=KEY),
              {"fetched_at": (FETCHED - timedelta(days=1)).isoformat(), "events_returned": 6,
               "discarded_events": []}, ttl=3600, stale_ttl=3600)

    _only(_diagnose(db, cache, redis), "unexplained")


def test_a_complete_run_report_evidences_provider_silence_for_the_rest(db, cache, redis):
    """Every forecast fetched was attached, so a fixture still missing was not in the response."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache, when=FETCHED)
    _run(cache, synced_at=FETCHED.isoformat(), order=[KEY],
         competitions={KEY: {"fetched": 4, "attached": 4, "unmatched": 0, "ambiguous": 0,
                             "without_markets": 0}})

    entry = _only(_diagnose(db, cache, redis), "provider_no_forecast")

    assert "attached all of them" in entry["evidence"]
    assert "cannot be told apart" in entry["evidence"]  # the sub-cause stays open, not guessed


def test_a_run_that_left_forecasts_unattached_does_not_evidence_silence(db, cache, redis):
    """If that run refused forecasts, "not among them" no longer follows from its counts."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache, when=FETCHED)
    _run(cache, synced_at=FETCHED.isoformat(), order=[KEY],
         competitions={KEY: {"fetched": 4, "attached": 3, "unmatched": 1, "ambiguous": 0}})

    _only(_diagnose(db, cache, redis), "unexplained")


def test_a_later_no_op_run_cannot_evidence_the_run_that_fetched(db, cache, redis):
    """The global status key is overwritten by every run; stale counts must not be read as proof."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache, when=FETCHED)
    # A paused run hours later overwrote the report; its stats no longer describe the fetch.
    _run(cache, synced_at=(FETCHED + timedelta(hours=12)).isoformat(), paused=True,
         error="skipped (recent failure: budget exhausted)",
         competitions={KEY: {"fetched": 4, "attached": 4, "unmatched": 0, "ambiguous": 0}})

    entry = _only(_diagnose(db, cache, redis), "unexplained")

    assert diag.COMPETITION_STATUS_KEY.format(provider=PROVIDER, key=KEY) in entry["evidence"]


# ----------------------------------------------------------- (c) identity was not resolved
def test_an_unresolved_competition_marker_is_an_identity_failure(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    cache.set(f"{LEAGUE_STORE_KEY}:unresolved:{KEY}", {"at": FETCHED.isoformat()},
              ttl=3600, stale_ttl=3600)

    entry = _only(_diagnose(db, cache, redis), "identity_unresolved")

    assert "unresolvable" in entry["evidence"]


def test_a_held_forecast_listed_the_other_way_round_is_an_identity_failure(db, cache, redis):
    """The owner's rule: a reversed fixture is refused, never attached. The report says so."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _held(cache, home="Chelsea", away="Arsenal", kickoff=BASE, event="evt-swapped")

    entry = _only(_diagnose(db, cache, redis), "identity_unresolved")

    assert "home/away swapped" in entry["evidence"]
    assert "evt-swapped" in entry["evidence"]


def test_a_held_forecast_for_unknown_teams_explains_no_fixture(db, cache, redis):
    """It cannot be tied to a fixture, so it is reported on its own and explains nothing."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _held(cache, home="Real Madrid", away="Barcelona", kickoff=BASE, event="evt-elsewhere")

    result = _diagnose(db, cache, redis)

    held = result["competitions"][0]["held_unattached"]
    assert [h["event"] for h in held] == ["evt-elsewhere"]
    assert held[0]["reason"] == "no candidate with matching team names"
    assert _only(result)["cause"] == "unexplained"  # not blamed on the unrelated held forecast


# ------------------------------------------------------------ (d) fetched but not attached
def test_a_held_forecast_that_names_the_fixture_is_not_attached(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _held(cache, home="Arsenal FC", away="Chelsea FC", kickoff=BASE + timedelta(minutes=5),
          event="evt-held-1")

    entry = _only(_diagnose(db, cache, redis), "not_attached")

    assert "evt-held-1" in entry["evidence"] and "names this fixture" in entry["evidence"]


def test_a_stored_forecast_with_no_snapshot_is_not_attached(db, cache, redis):
    """The row reached the database and stopped short of the history the reader is served from."""
    league = _league(db)
    match = _fixture(db, league, "Arsenal", "Chelsea")
    _record(db, match)
    _synced(cache)

    entry = _only(_diagnose(db, cache, redis), "not_attached")

    assert "no snapshot was written" in entry["evidence"]


def test_a_provider_link_with_no_forecast_row_is_not_attached(db, cache, redis):
    league = _league(db)
    match = _fixture(db, league, "Arsenal", "Chelsea")
    _ref(db, match, external_event_id="evt-linked")
    _synced(cache)

    entry = _only(_diagnose(db, cache, redis), "not_attached")

    assert "evt-linked" in entry["evidence"]


# ------------------------------------------------------------------------ honest ignorance
def test_a_fetched_competition_with_no_surviving_report_is_unexplained(db, cache, redis):
    """The case that must NOT be guessed: the shape today's live database is in.

    The competition was fetched after the fixture existed, nothing is held, nothing is orphaned -
    consistent with the provider publishing no forecast, but no record proves it. The report says
    so and names the record that is missing instead of counting it as provider silence.
    """
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache, when=FETCHED)
    _run(cache, synced_at=(FETCHED + timedelta(hours=12)).isoformat(), paused=True,
         error="skipped (recent failure: budget exhausted)")

    result = _diagnose(db, cache, redis)
    entry = _only(result, "unexplained")

    assert result["totals"]["causes"] == {"unexplained": 1}
    assert "provider_no_forecast" not in entry["evidence"]
    assert "cannot be evidenced" in entry["evidence"]
    assert [e["match_id"] for e in result["unexplained"]] == [entry["match_id"]]


def test_a_fixture_outside_the_covered_competitions_is_not_blamed_on_the_budget(db, cache, redis):
    """No allowance was ever going to be spent on it, so saying the allowance ran out would lie."""
    other = League(id=uuid.uuid4(), name="Eredivisie", display_name="Eredivisie", country="Netherlands",
                   country_code="NED", external_api_id=f"test:{uuid.uuid4().hex[:12]}",
                   external_api_source="test", is_active=True)
    db.add(other)
    db.flush()
    _fixture(db, other, "Ajax", "PSV")
    _spend_allowance(redis, used=8)

    entry = _only(_diagnose(db, cache, redis), "not_fetched")

    assert entry["sub_cause"] == "competition_not_covered"
    assert "not one of the covered competitions" in entry["evidence"]


def test_a_canonical_competition_left_out_of_the_covered_list_is_not_blamed_on_the_budget(db, cache, redis):
    """Having a canonical key is not the same as being walked by the sync.

    A league row can carry a `canonical_key` the covered list leaves out. Its turn never comes, so
    no allowance was ever going to be spent on it and "today's allowance is spent" would be the
    wrong answer - the same lie as for a league with no key at all, and harder to notice because
    the competition looks fully configured (it even has a provider league id).
    """
    league = _league(db, "la_liga")           # canonical, but NOT in the keys diagnosed below
    _fixture(db, league, "Sevilla", "Valencia")
    _spend_allowance(redis, used=8)
    _run(cache, synced_at=FETCHED.isoformat(), order=[KEY], paused=True,
         error="Daily request budget for gameforecast exhausted (8/8 used)")

    entry = _only(_diagnose(db, cache, redis, keys=(KEY,)), "not_fetched")

    assert entry["sub_cause"] == "competition_not_covered"
    assert "not one of the covered competitions" in entry["evidence"]
    assert "allowance" not in entry["evidence"]


def test_every_uncovered_fixture_gets_exactly_one_known_cause(db, cache, redis):
    """No fixture may fall through the classifier silently, and no cause may be invented."""
    league = _league(db)
    for home, away in (("Arsenal", "Chelsea"), ("Everton", "Liverpool"), ("Fulham", "Brentford")):
        _fixture(db, league, home, away)
    _synced(cache)

    result = _diagnose(db, cache, redis)

    causes = [entry["cause"] for comp in result["competitions"] for entry in comp["missing"]]
    assert len(causes) == result["totals"]["without"] == 3
    assert set(causes) <= set(diag.CAUSES)


# ----------------------------------------------------------------------- budget and safety
def test_a_counter_above_the_limit_is_flagged_as_stale_not_as_overspend(db, cache, redis):
    """9 against a limit of 8 is explained, never tuned away and never called overspend."""
    _league(db)
    _spend_allowance(redis, used=9)

    ledger = _diagnose(db, cache, redis)["budget"]

    assert ledger["used_today"] == 9 and ledger["daily_limit"] == 8 and ledger["over_limit"] is True
    assert "not overspend" in ledger["over_limit_note"]
    assert "stale counter" in ledger["over_limit_note"]


def test_the_diagnosis_writes_nothing(db, cache, redis):
    """A report that can change what it reports on is not a report."""
    league = _league(db)
    match = _fixture(db, league, "Arsenal", "Chelsea")
    _held(cache, home="Arsenal FC", away="Chelsea FC", kickoff=BASE)
    _synced(cache)
    db.commit()
    before = (db.query(Match).count(), db.query(ProviderForecastRecord).count(),
              db.query(ProviderForecastSnapshot).count(), db.query(ProviderEntityRef).count())

    _diagnose(db, cache, redis)

    assert not db.new and not db.dirty and not db.deleted
    assert (db.query(Match).count(), db.query(ProviderForecastRecord).count(),
            db.query(ProviderForecastSnapshot).count(), db.query(ProviderEntityRef).count()) == before
    assert db.query(ProviderForecastRecord).filter(
        ProviderForecastRecord.match_id == match.id).count() == 0


def test_the_text_report_renders_every_section(db, cache, redis):
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _spend_allowance(redis, used=9)
    _run(cache, synced_at=FETCHED.isoformat(), order=[KEY], paused=True, error="budget exhausted")

    text_report = diag.render(_diagnose(db, cache, redis))

    assert "Forecast coverage for gameforecast" in text_report
    assert "Budget ledger (gameforecast): used 9/8" in text_report
    assert "not_fetched" in text_report
    assert "Arsenal v Chelsea" in text_report


# ------------------------------------- (b2) a retained per-competition record, and its limits
def _retained(cache, **report):
    """Write the per-competition fetch record a real pass leaves behind."""
    base = {"provider": PROVIDER, "key": KEY, "fetched_at": FETCHED.isoformat(),
            "window_from": (BASE - timedelta(days=1)).date().isoformat(),
            "window_to": (BASE + timedelta(days=1)).date().isoformat(),
            "complete": True, "events_returned": 6, "forecasts_returned": 6,
            "discarded": 0, "discarded_events": [], "discarded_truncated": False}
    base.update(report)
    cache.set(diag.COMPETITION_STATUS_KEY.format(provider=PROVIDER, key=KEY), base,
              ttl=3600, stale_ttl=3600)


def test_the_diagnosis_reads_the_key_the_forecast_service_writes(db, cache, redis):
    """A reader looking under a key nobody writes reports honest ignorance forever."""
    from app.services.forecast_service import COMPETITION_STATUS_KEY as WRITER_KEY

    assert diag.COMPETITION_STATUS_KEY == WRITER_KEY


def test_a_complete_listing_evidences_that_the_provider_never_returned_the_fixture(db, cache, redis):
    """The other half of provider silence: not "returned and empty" but "not returned at all"."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache)

    entry = _only(_diagnose(db, cache, redis), "provider_no_forecast")

    assert "did not return this fixture at all" in entry["evidence"]
    assert "6 event(s) returned" in entry["evidence"]


def test_a_listing_whose_window_misses_the_kickoff_evidences_nothing(db, cache, redis):
    """A response for one week says nothing whatsoever about a fixture in the next one."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache, window_from=(BASE - timedelta(days=8)).date().isoformat(),
              window_to=(BASE - timedelta(days=1)).date().isoformat())

    entry = _only(_diagnose(db, cache, redis), "unexplained")

    assert "window does not contain this kick-off" in entry["evidence"]


def test_a_listing_cut_off_at_the_page_cap_evidences_nothing(db, cache, redis):
    """The provider said there was more and we stopped reading; this fixture may be on page five."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache, complete=False)

    _only(_diagnose(db, cache, redis), "unexplained")


def test_a_truncated_discarded_list_cannot_say_the_fixture_was_never_returned(db, cache, redis):
    """The capped list may not name this fixture even though the provider returned it."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache, discarded=99, discarded_truncated=True,
              discarded_events=[{"external_event_id": "evt-1", "home": "Fulham",
                                 "away": "Brentford", "reason": "no prediction snapshot"}])

    _only(_diagnose(db, cache, redis), "unexplained")


def test_a_named_discarded_event_outranks_the_listing_and_says_what_was_wrong(db, cache, redis):
    """Naming the event is stronger evidence, and it is a different answer: returned, but empty."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache, discarded=1,
              discarded_events=[{"external_event_id": "evt-9", "home": "Arsenal FC",
                                 "away": "Chelsea FC",
                                 "reason": "a prediction snapshot was published with no usable market in it"}])

    entry = _only(_diagnose(db, cache, redis), "provider_no_forecast")

    assert "evt-9" in entry["evidence"] and "no usable market" in entry["evidence"]
    assert "did not return this fixture at all" not in entry["evidence"]


def test_a_record_with_an_unreadable_retrieval_time_evidences_nothing(db, cache, redis):
    """A report that cannot be placed in time cannot be placed against a fixture row."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache)
    _retained(cache, fetched_at=FETCHED.strftime("%Y-%m-%dT%H:%M:%SZ"))

    _only(_diagnose(db, cache, redis), "unexplained")


# ------------------------------------------- (b3) a timestamp this tool cannot read is not a crash
def test_a_z_suffixed_last_fetch_stamp_degrades_to_unexplained(db, cache, redis):
    """A stored "Z" used to take the whole report down on Python 3.9 - and on 3.11 it parsed.

    Neither is acceptable: a report that dies on one key explains nothing, and a report whose
    answer depends on which interpreter ran it is not evidence. It degrades, on both.
    """
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    cache.set(LAST_SYNC_KEY.format(provider=PROVIDER, key=KEY),
              FETCHED.strftime("%Y-%m-%dT%H:%M:%SZ"), ttl=3600, stale_ttl=3600)

    entry = _only(_diagnose(db, cache, redis), "unexplained")

    assert "not a timestamp this tool can read" in entry["evidence"]
    assert "never been fetched" not in entry["evidence"], "absence of a readable stamp is not absence of a fetch"


def test_a_z_suffixed_run_timestamp_degrades_instead_of_crashing(db, cache, redis):
    """The run report's own stamp is read to date its statistics; unreadable means untrusted."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    _synced(cache, when=FETCHED)
    _run(cache, synced_at=FETCHED.strftime("%Y-%m-%dT%H:%M:%SZ"), order=[KEY],
         competitions={KEY: {"fetched": 4, "attached": 4, "unmatched": 0, "ambiguous": 0,
                             "without_markets": 0}})

    _only(_diagnose(db, cache, redis), "unexplained")


def test_an_unreadable_stamp_never_suppresses_a_cause_that_does_not_need_it(db, cache, redis):
    """Steps that read no timestamp still answer: degrading must not blind the whole classifier."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    cache.set(LAST_SYNC_KEY.format(provider=PROVIDER, key=KEY),
              FETCHED.strftime("%Y-%m-%dT%H:%M:%SZ"), ttl=3600, stale_ttl=3600)
    _held(cache, home="Arsenal FC", away="Chelsea FC", kickoff=BASE + timedelta(minutes=5),
          event="evt-held-1")

    entry = _only(_diagnose(db, cache, redis), "not_attached")

    assert "evt-held-1" in entry["evidence"]


def test_the_report_still_renders_when_a_stored_stamp_is_unreadable(db, cache, redis):
    """The crash was in the report, not just the classifier: rendering must survive it too."""
    league = _league(db)
    _fixture(db, league, "Arsenal", "Chelsea")
    cache.set(LAST_SYNC_KEY.format(provider=PROVIDER, key=KEY), "not-a-timestamp",
              ttl=3600, stale_ttl=3600)

    text_report = diag.render(_diagnose(db, cache, redis))

    assert "unexplained" in text_report and "Arsenal v Chelsea" in text_report
