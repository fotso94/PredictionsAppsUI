"""
Whether fixture and result updates can arrive: the classifier, the derivation, and what feeds them.

THE STATE THIS WAS BUILT FOR, measured on 2026-10-07 between 01:05 and 01:41 UTC. Every match-data
source refused: Live Score with HTTP 401 ("do not have access to our data enabled"), API-Football
with its free plan's season restriction (an HTTP 200 carrying `errors: {'plan': ...}`), TheSportsDB
with HTTP 400 "Invalid Premium API key". The fixtures task had failed 15 passes running and the
results task 19. No provider had written a match row since 2026-10-02 14:52:26 UTC. And the pages
said "fixtures and scores last refreshed 4 minutes ago", because the recover and settle passes -
which fetch nothing - had just succeeded, and `matches.updated_at` had just been bumped by recovery
bookkeeping.

What is pinned here:
  * the three refusals, word for word, classify as access, plan and access - and a quota message
    that happens to mention a plan stays a quota refusal;
  * that state derives as BLOCKED, with `since` the last provider write and nothing else;
  * recover and settle successes do not move `since` or lift the state, and `updated_at` is not
    read at all (database test);
  * A COPY STORED AGAIN IS NOT DATA ARRIVING. `MatchRegistry` stamps `last_synced_at` when it
    stores a row, and `_call_chain` hands back the 24-hour stale copy once every provider has
    failed, which the fixtures and results passes store again. A stamp its provider's own record
    cannot account for - later than a failure that followed its last answer, or long after that
    answer - is bounded by that answer, so `since` does not move while nothing answers and the
    six-hour silence that leads to BLOCKED can elapse (pure tests, and a database test that drives
    the real chain into its stale copy);
  * a fallback that answers while the primary refuses is DEGRADED, not blocked - unless the passes
    keep failing with nothing written, in which case its "success" brought nothing;
  * a single failure on a current table is degraded; a healthy chain is ok; no records is unknown;
  * the forecasts waiting for their fixtures are counted from the last forecast pass;
  * `_record_status` keeps the kind of each refusal, from the exception class, when the real
    provider classes are driven over mock transports - the 200-with-a-plan-error included.

The database tests need PostgreSQL (TEST_DATABASE_URL; skipped when unreachable); the rest need
nothing. No network: every provider request goes to a mock transport.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import Match, MatchStatus, Team
from app.services import match_data_health as H
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta, last_provider_writes
from app.services.match_registry import MatchRegistry
from app.services.providers.api_football_provider import APIFootballProvider
from app.services.providers.base import (
    STATUS_SCHEDULED, MatchDataProvider, ProviderAuthError, ProviderCompetition, ProviderError, ProviderFixture,
    ProviderQuotaError, ProviderRequestNotSent, ProviderTeam, ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.providers.thesportsdb_provider import TheSportsDBProvider
from tests.providers.support import FakeRedis, json_response, make_transport

from tests.conftest import TEST_DATABASE_URL  # noqa: E402 - one place for the default

NOW = datetime(2026, 10, 7, 1, 41, 6, tzinfo=timezone.utc)
LAST_WRITE = datetime(2026, 10, 2, 14, 52, 26, tzinfo=timezone.utc)

# The three refusals as the status records held them on 2026-10-07, character for character.
LIVESCORE_401 = ("livescore: authentication rejected (HTTP 401): This API key and secret do not have "
                 "access to our data enabled")
API_FOOTBALL_PLAN = ("API-Football errors: {'plan': 'Free plans do not have access to this season, "
                     "try from 2022 to 2024.'}")
THESPORTSDB_400 = ('thesportsdb: request rejected (HTTP 400): {"Message":"Invalid Premium API key: '
                   'Signup here: https:\\/\\/www.thesportsdb.com\\/pricing"}')
# GameForecast's 429, which mentions a plan twice and is an allowance running out, not a plan limit.
GAMEFORECAST_429 = ("gameforecast: rate limit or quota exceeded (HTTP 429): You have exceeded the DAILY "
                    "quota for Requests on your current plan, BASIC. Upgrade your plan at "
                    "https://rapidapi.com/krnelstudio/api/game-forecast-api")


def ago(**delta: float) -> str:
    return (NOW - timedelta(**delta)).isoformat()


def ahead(**delta: float) -> str:
    return (NOW + timedelta(**delta)).isoformat()


def source(name: str, *, success: Optional[str] = None, error_at: Optional[str] = None,
           error: Optional[str] = None, kind: Optional[str] = None, configured: bool = True) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"name": name, "configured": configured, "cooling_down": None,
                             "last_success_at": success, "last_error_at": error_at, "last_error": error}
    if kind is not None:
        entry["last_error_kind"] = kind
    return entry


def task(*, success: Optional[str], failures: int = 0, next_due: Optional[str] = None,
         ran: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"enabled": True, "last_run_at": ran or success, "last_success_at": success,
            "consecutive_failures": failures, "next_due_at": next_due, "last_result": result}


def todays_chain() -> List[Dict[str, Any]]:
    """The chain as it read at 01:09 UTC on 2026-10-07: every source's last record a refusal."""
    return [
        source("livescore", success="2026-10-02T14:53:28+00:00", error_at=ago(minutes=6), error=LIVESCORE_401),
        source("api_football", success="2026-10-06T00:55:24+00:00", error_at=ago(minutes=36), error=API_FOOTBALL_PLAN),
        source("thesportsdb", success="2026-10-05T21:39:12+00:00", error_at=ago(minutes=36), error=THESPORTSDB_400),
    ]


def todays_scheduler(**over: Any) -> Dict[str, Any]:
    """Fixtures and results failing for days; recover and settle 'succeeding' minutes ago."""
    tasks = {
        "fixtures": task(success="2026-10-02T13:07:44+00:00", failures=15, next_due=ahead(hours=5, minutes=24),
                         ran=ago(minutes=36)),
        "live": task(success="2026-10-05T21:26:49+00:00", failures=7, next_due=ahead(hours=4, minutes=43),
                     ran=ago(minutes=36)),
        "results": task(success="2026-10-02T14:53:28+00:00", failures=19, next_due=ahead(hours=5, minutes=24),
                        ran=ago(minutes=36)),
        "recover": task(success=ago(minutes=6), next_due=ahead(minutes=24),
                        result={"overdue": 95, "outcomes": {"deferred": 78, "not_asked": 17}, "requests": 0}),
        "settle": task(success=ago(minutes=36), next_due=ahead(minutes=84), result={"matches_considered": 0}),
        "forecasts": task(success=ago(minutes=36), next_due=ahead(hours=5)),
    }
    tasks.update(over)
    return {"enabled": True, "state_store_available": True, "tasks": tasks}


TODAYS_FORECASTS = {"last_sync": {"retried": {
    "premier_league": {"pending": 10, "attached": 0}, "la_liga": {"pending": 10, "attached": 1},
    "serie_a": {"pending": 10, "attached": 0}, "bundesliga": {"pending": 9, "attached": 1},
    "ligue_1": {"pending": 9, "attached": 1},
}}}


def derive(chain=None, scheduler=None, last_write=LAST_WRITE, forecasts=None, **kwargs) -> Dict[str, Any]:
    return H.derive_match_data_state(
        chain=todays_chain() if chain is None else chain, active_provider="livescore",
        scheduler=todays_scheduler() if scheduler is None else scheduler, last_write_at=last_write,
        forecasts=TODAYS_FORECASTS if forecasts is None else forecasts, now=NOW, **kwargs)


# ----------------------------------------------------------------------------- the classifier
@pytest.mark.parametrize("message, expected", [
    (LIVESCORE_401, H.ERROR_ACCESS),
    (API_FOOTBALL_PLAN, H.ERROR_PLAN),
    (THESPORTSDB_400, H.ERROR_ACCESS),
    (GAMEFORECAST_429, H.ERROR_QUOTA),
    ("daily request budget for livescore is spent (1200/1200 used)", H.ERROR_QUOTA),
    ("livescore: network error: [Errno 8] nodename nor servname provided", H.ERROR_UNAVAILABLE),
    ("livescore: upstream error (HTTP 502)", H.ERROR_UNAVAILABLE),
    ("livescore: authentication rejected (HTTP 403)", H.ERROR_ACCESS),
    ("", H.ERROR_UNAVAILABLE),
    (None, H.ERROR_UNAVAILABLE),
])
def test_todays_three_refusals_and_their_neighbours_classify_from_the_message(message, expected):
    assert H.classify_provider_error(message) == expected


def test_a_plan_restriction_is_checked_before_access_because_its_words_contain_an_access_phrase():
    # "Free plans do not have access" holds "do not have access": the order is what keeps it a plan.
    assert "do not have access" in API_FOOTBALL_PLAN
    assert H.classify_provider_error(API_FOOTBALL_PLAN, ProviderUnavailableError("x")) == H.ERROR_PLAN
    assert H.classify_provider_error(API_FOOTBALL_PLAN, ProviderAuthError) == H.ERROR_PLAN


def test_the_exception_class_decides_before_the_message_where_it_can():
    # A quota error is a quota error whatever it says about plans.
    assert H.classify_provider_error(GAMEFORECAST_429, ProviderQuotaError("x")) == H.ERROR_QUOTA
    assert H.classify_provider_error("refused before it left", ProviderRequestNotSent("x")) == H.ERROR_QUOTA
    # An authentication error with a message nobody wrote a pattern for is still access.
    assert H.classify_provider_error("something new from the vendor", ProviderAuthError("x")) == H.ERROR_ACCESS
    assert H.classify_provider_error("something new from the vendor", ProviderError) == H.ERROR_UNAVAILABLE


# ----------------------------------------------------------------------------- the derivation
def test_todays_state_is_blocked_since_the_last_provider_write():
    block = derive()
    assert block["state"] == H.STATE_BLOCKED
    assert block["since"] == LAST_WRITE.isoformat()
    assert block["since_basis"] == "last_provider_write"
    assert [(s["name"], s["role"], s["answer"], s["kind"]) for s in block["sources"]] == [
        ("livescore", "primary", "refused", "access"),
        ("api_football", "fallback", "refused", "plan"),
        ("thesportsdb", "fallback", "refused", "access"),
    ]
    assert block["affects"] == H.AFFECTS
    assert "stored_forecasts" in block["still_available"]
    # The earliest due time among the passes that would reach a provider for this data: recover's.
    assert block["next_check_at"] == ahead(minutes=24)
    assert block["checked_at"] == NOW.isoformat()


def test_every_source_refusing_is_blocked_at_once_without_waiting_for_a_streak():
    fresh = todays_scheduler(fixtures=task(success=ago(hours=2), failures=1, ran=ago(minutes=5)),
                             results=task(success=ago(hours=1), failures=1, ran=ago(minutes=5)))
    block = derive(scheduler=fresh, last_write=NOW - timedelta(hours=1))
    assert block["state"] == H.STATE_BLOCKED


def test_recover_and_settle_successes_do_not_move_since_or_lift_the_state():
    # The regression this exists for: both passes succeed every half hour while fetching nothing.
    just_now = todays_scheduler(recover=task(success=ago(seconds=10), next_due=ahead(minutes=30)),
                                settle=task(success=ago(seconds=5), next_due=ahead(hours=2)))
    block = derive(scheduler=just_now)
    assert block["state"] == H.STATE_BLOCKED
    assert block["since"] == LAST_WRITE.isoformat(), "since is the last provider write, never a task's success"


def test_a_fallback_answering_while_the_primary_refuses_is_degraded_not_blocked():
    chain = todays_chain()
    chain[1] = source("api_football", success=ago(minutes=5), error_at=ago(hours=3), error=None, kind="plan")
    fresh = todays_scheduler(fixtures=task(success=ago(minutes=5)), results=task(success=ago(minutes=5)),
                             live=task(success=ago(minutes=2)))
    block = derive(chain=chain, scheduler=fresh, last_write=NOW - timedelta(minutes=5))
    assert block["state"] == H.STATE_DEGRADED
    assert block["sources"][1]["answer"] == "ok"
    assert block["sources"][1]["kind"] == "plan", "the last failure's kind is kept beside its time"


def test_a_fallbacks_success_that_wrote_nothing_does_not_lift_blocked():
    # 2026-10-07 01:35 UTC: API-Football answered a live poll on its free plan (nothing in play) after
    # refusing every fixtures and results call. That is not fixture data arriving.
    chain = todays_chain()
    chain[1] = source("api_football", success=ago(minutes=6), error_at=ago(minutes=36), error=None)
    block = derive(chain=chain)
    assert block["sources"][1]["answer"] == "ok"
    assert block["state"] == H.STATE_BLOCKED
    # The same answer with a fresh write behind it IS data arriving.
    assert derive(chain=chain, last_write=NOW - timedelta(minutes=10))["state"] == H.STATE_DEGRADED


def test_one_network_failure_on_a_current_table_is_degraded_not_blocked():
    chain = [source("livescore", success=ago(minutes=40), error_at=ago(minutes=2),
                    error="livescore: network error: timed out")]
    scheduler = todays_scheduler(fixtures=task(success=ago(hours=1)), live=task(success=ago(minutes=2)),
                                 results=task(success=ago(minutes=40), failures=1, ran=ago(minutes=2)))
    block = derive(chain=chain, scheduler=scheduler, last_write=NOW - timedelta(minutes=40))
    assert block["state"] == H.STATE_DEGRADED
    assert block["sources"][0]["answer"] == "failing" and block["sources"][0]["kind"] == "unavailable"


def test_a_long_streak_of_unexplained_failures_with_nothing_written_is_blocked():
    chain = [source("livescore", success=ago(days=2), error_at=ago(minutes=2), error="livescore: upstream error (HTTP 502)")]
    assert derive(chain=chain)["state"] == H.STATE_BLOCKED
    # The same streak on a table written an hour ago is not.
    assert derive(chain=chain, last_write=NOW - timedelta(hours=1))["state"] == H.STATE_DEGRADED


def test_a_healthy_chain_is_ok_and_a_stale_error_on_an_unneeded_fallback_is_no_fault():
    chain = [source("livescore", success=ago(minutes=3)),
             source("api_football", success=ago(days=3), error_at=ago(days=2), error=API_FOOTBALL_PLAN)]
    scheduler = {"enabled": True, "state_store_available": True, "tasks": {
        "fixtures": task(success=ago(hours=1)), "live": task(success=ago(minutes=2)),
        "results": task(success=ago(minutes=8))}}
    block = derive(chain=chain, scheduler=scheduler, last_write=NOW - timedelta(minutes=3))
    assert block["state"] == H.STATE_OK
    assert block["affects"] == []


def test_nothing_recorded_is_unknown_never_ok():
    chain = [source("livescore"), source("api_football")]
    assert derive(chain=chain, scheduler={"enabled": True, "state_store_available": False, "tasks": {}},
                  last_write=None)["state"] == H.STATE_UNKNOWN
    assert derive(chain=chain, scheduler={}, last_write=LAST_WRITE)["state"] == H.STATE_UNKNOWN
    assert derive(chain=[], scheduler={}, last_write=None)["state"] == H.STATE_UNKNOWN


def test_an_unconfigured_source_neither_answers_nor_refuses():
    chain = todays_chain() + [source("sample", success=ago(minutes=1), configured=False)]
    assert derive(chain=chain)["state"] == H.STATE_BLOCKED


def test_forecasts_waiting_for_their_fixtures_is_pending_less_attached_at_the_last_pass():
    # 10 + 9 + 10 + 8 + 8: the 45 paid-for forecasts with no fixture row to attach to on 2026-10-07.
    assert derive()["forecasts_waiting_for_fixtures"] == 45
    assert H.forecasts_waiting({"last_sync": {"retried": {}}}) == 0
    assert H.forecasts_waiting({"last_sync": {"retried": {"a": {"pending": 2, "attached": 5}}}}) == 0
    assert H.forecasts_waiting({"last_sync": {"retried": {"a": "broken", "b": {"pending": "3"}}}}) == 3
    assert H.forecasts_waiting({"last_sync": None}) is None, "no forecast run recorded is unknown, not zero"
    assert H.forecasts_waiting(None) is None


def test_a_record_written_before_the_kind_was_kept_is_classified_from_its_message():
    chain = todays_chain()
    assert all("last_error_kind" not in entry for entry in chain)
    assert [s["kind"] for s in derive(chain=chain)["sources"]] == ["access", "plan", "access"]
    # A recorded kind wins over the message.
    chain[0]["last_error_kind"] = "quota"
    assert derive(chain=chain)["sources"][0]["answer"] == "allowance"


# ----------------------------------------------------------------------------- a copy stored again
#: Live Score's last answer on record on 2026-10-07, a minute after the newest row it wrote.
LIVESCORE_ANSWERED = datetime(2026, 10, 2, 14, 53, 28, tzinfo=timezone.utc)


def test_todays_newest_stamp_stands_as_the_write_because_livescore_answered_just_before_it():
    # Measured on 2026-10-07: the newest Live Score row was stamped 14:52:26 and its last answer is
    # recorded at 14:53:28. A stamp its provider's record accounts for is the write itself.
    block = derive(last_write=None, provider_writes={"livescore": LAST_WRITE})
    assert block["since"] == LAST_WRITE.isoformat()
    assert block["since_basis"] == H.SINCE_BASIS
    assert block["state"] == H.STATE_BLOCKED


def test_a_row_stored_again_from_a_cached_copy_after_the_refusal_does_not_move_since():
    # The stale copy of a day Live Score answered before it refused, stored again two minutes ago
    # by a results pass. Nothing answered; the stamp says "two minutes ago" all the same.
    block = derive(last_write=None, provider_writes={"livescore": NOW - timedelta(minutes=2)})
    assert block["since"] == LIVESCORE_ANSWERED.isoformat(), "bounded by the provider's last answer"
    assert block["since_basis"] == H.SINCE_BASIS_ANSWER
    assert block["state"] == H.STATE_BLOCKED


def test_each_providers_stamp_is_checked_against_that_providers_own_record():
    answered = NOW - timedelta(hours=7)
    refusing = [source("livescore", success=answered.isoformat(), error_at=ago(minutes=5), error=LIVESCORE_401)]
    # Later than a failure that came after its last answer: a copy, not an answer.
    assert H.newest_provider_write({"livescore": NOW - timedelta(minutes=1)}, refusing) == (
        answered, H.SINCE_BASIS_ANSWER)
    # Written between its last answer and the failure that followed: the write stands.
    between = answered + timedelta(seconds=4)
    assert H.newest_provider_write({"livescore": between}, refusing) == (between, H.SINCE_BASIS)

    # No failure at all, but stored long after the only answer: the 30-minute fresh copy served
    # to a later pass. Its data is that answer's.
    healthy = [source("livescore", success=answered.isoformat())]
    assert H.newest_provider_write({"livescore": answered + timedelta(minutes=25)}, healthy) == (
        answered, H.SINCE_BASIS_ANSWER)
    within = answered + H.STORE_ALLOWANCE - timedelta(seconds=1)
    assert H.newest_provider_write({"livescore": within}, healthy) == (within, H.SINCE_BASIS)

    # Nothing on record to check against - no status record (Redis unavailable, which also means
    # no cached copy to store again), or a provider no longer in the chain: the stamp stands.
    assert H.newest_provider_write({"livescore": NOW}, [source("livescore")]) == (NOW, H.SINCE_BASIS)
    assert H.newest_provider_write({"sample": NOW}, refusing) == (NOW, H.SINCE_BASIS)

    # Failed and never answered on record, stamped after the failure: not its answer, and nothing
    # says when its last one was. Unknown, not the stamp.
    never = [source("livescore", error_at=ago(minutes=5), error=LIVESCORE_401)]
    assert H.newest_provider_write({"livescore": NOW - timedelta(minutes=1)}, never) == (None, None)

    # The newest of what each provider can account for; a malformed stamp is no stamp.
    both = refusing + [source("api_football", success=ago(hours=2))]
    assert H.newest_provider_write({"livescore": NOW, "api_football": ago(hours=2, seconds=-3),
                                    "thesportsdb": "garbage"}, both) == (
        NOW - timedelta(hours=2, seconds=-3), H.SINCE_BASIS)
    assert H.newest_provider_write({}, both) == (None, None)
    assert H.newest_provider_write(None, both) == (None, None)


def test_a_fresh_outage_reaches_blocked_after_six_hours_though_copies_keep_being_stored():
    # The first day of an outage. Live Score last answered seven hours ago. The fixtures and results
    # passes store the stale copy again every time they run - which also keeps the fixtures pass
    # "succeeding" - and API-Football answers a live poll with nothing in play on its free plan.
    # Measured by the newest stamp, a row was written four minutes ago and the silence never starts;
    # measured by what the providers' answers can account for, nothing has arrived for seven hours.
    answered = NOW - timedelta(hours=7)
    chain = [
        source("livescore", success=answered.isoformat(), error_at=ago(minutes=5), error=LIVESCORE_401),
        source("api_football", success=ago(minutes=3), error_at=ago(minutes=35), error=None, kind="plan"),
        source("thesportsdb", success=ago(days=2), error_at=ago(minutes=35), error=THESPORTSDB_400),
    ]
    scheduler = todays_scheduler(fixtures=task(success=ago(minutes=40), ran=ago(minutes=40)),
                                 results=task(success=answered.isoformat(), failures=13, ran=ago(minutes=5)))
    block = derive(chain=chain, scheduler=scheduler, last_write=None,
                   provider_writes={"livescore": NOW - timedelta(minutes=4)})
    assert block["sources"][1]["answer"] == "ok"
    assert block["since"] == answered.isoformat()
    assert block["state"] == H.STATE_BLOCKED


# ----------------------------------------------------------------------------- recording the kind
DAY = date(2026, 10, 7)


def _refusing_chain():
    """The three real provider classes, each answering exactly the way it did on 2026-10-07."""
    def livescore(request: httpx.Request) -> httpx.Response:
        return json_response({"success": False, "error": "This API key and secret do not have access to our data enabled"}, 401)

    def api_football(request: httpx.Request) -> httpx.Response:
        # HTTP 200: the refusal is in the body, which is the case a status code alone would miss.
        return json_response({"errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."},
                              "response": []}, 200)

    def thesportsdb(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b'{"Message":"Invalid Premium API key: Signup here: https:\\/\\/www.thesportsdb.com\\/pricing"}')

    store = MatchCache(client=FakeRedis())
    providers = [
        LiveScoreAPIProvider(api_key="test-key", api_secret="test-secret", transport=make_transport(livescore)[0],
                             budget=RequestBudget("livescore", 100, client=FakeRedis()), store=store,
                             competition_overrides={}),
        APIFootballProvider(api_key="test-key", transport=make_transport(api_football)[0],
                            budget=RequestBudget("api_football", 100, client=FakeRedis())),
        TheSportsDBProvider(api_key="test-key", transport=make_transport(thesportsdb)[0],
                            budget=RequestBudget("thesportsdb", 100, client=FakeRedis())),
    ]
    return providers


def test_each_refusal_is_recorded_with_its_kind_and_none_as_an_answer():
    service = MatchDataService(None, providers=_refusing_chain(), cache=MatchCache(client=FakeRedis()), now=NOW,
                               keys=["premier_league"])
    with pytest.raises(ProviderError):
        service._call_chain("test:fixtures", 60, SyncMeta(), lambda p: p.get_fixtures(DAY, ["premier_league"]))
    chain = service.provider_status()["chain"]
    assert [(e["name"], e["last_error_kind"], e.get("last_success_at")) for e in chain] == [
        ("livescore", "access", None),
        ("api_football", "plan", None),
        ("thesportsdb", "access", None),
    ]
    block = H.derive_match_data_state(chain=chain, active_provider="livescore", scheduler=todays_scheduler(),
                                      last_write_at=LAST_WRITE, now=NOW)
    assert block["state"] == H.STATE_BLOCKED


def test_a_later_success_keeps_the_kind_of_the_last_failure_beside_its_time():
    cache = MatchCache(client=FakeRedis())
    service = MatchDataService(None, providers=[], cache=cache, now=NOW)
    try:
        raise ProviderUnavailableError(API_FOOTBALL_PLAN, provider="api_football")
    except ProviderUnavailableError as exc:
        service._record_status("api_football", False, str(exc))
    later = MatchDataService(None, providers=[], cache=cache, now=NOW + timedelta(minutes=30))
    later._record_status("api_football", True)
    record = cache.get("provider:status:api_football")
    assert record["last_error"] is None, "a success clears the message, as it always has"
    assert record["last_error_kind"] == "plan" and record["last_error_at"] == NOW.isoformat()


# ----------------------------------------------------------------------------- the database
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
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    H.forget_stored_counts()
    yield session
    H.forget_stored_counts()
    session.close()
    transaction.rollback()
    connection.close()


def _match(db, kickoff: datetime, status: MatchStatus, meta: Optional[Dict[str, Any]] = None) -> Match:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    teams = []
    for label in ("Home", "Away"):
        team = Team(id=uuid.uuid4(), name=f"{label} {uuid.uuid4().hex[:6]}", country="England")
        db.add(team)
        teams.append(team)
    db.flush()
    row = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=teams[0].id, away_team_id=teams[1].id,
                match_date=kickoff.astimezone(timezone.utc).replace(tzinfo=None), status=status,
                external_api_id=f"ls-health-{uuid.uuid4().hex[:8]}", external_api_source="livescore",
                match_metadata=meta or {})
    db.add(row)
    db.flush()
    return row


def test_the_last_provider_write_is_last_synced_at_and_never_updated_at(db):
    # Stamps in the future so no row any other test leaves behind can be newer than them.
    written = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    bumped = written + timedelta(days=30)
    row = _match(db, datetime.now(timezone.utc) + timedelta(days=1), MatchStatus.SCHEDULED,
                 {"last_synced_at": written.isoformat(), "provider": "livescore"})
    # What recovery bookkeeping does: rewrite the row, which moves updated_at and nothing else.
    db.execute(text("UPDATE predictions.matches SET updated_at = :at WHERE id = :id"),
               {"at": bumped.replace(tzinfo=None), "id": row.id})
    # And a stamp of the wrong shape is left out rather than failing the whole aggregate.
    _match(db, datetime.now(timezone.utc) + timedelta(days=1), MatchStatus.SCHEDULED,
           {"last_synced_at": "garbage", "provider": "livescore"})
    assert last_provider_writes(db)["livescore"] == written


def test_the_stored_counts_measure_upcoming_and_overdue_and_are_reused_for_a_minute(db):
    now = datetime.now(timezone.utc)
    before = H.stored_match_counts(db, now)
    _match(db, now + timedelta(days=2), MatchStatus.SCHEDULED)                           # upcoming
    _match(db, now - timedelta(hours=5), MatchStatus.SCHEDULED)                          # overdue
    _match(db, now - timedelta(hours=4), MatchStatus.LIVE)                               # overdue
    _match(db, now - timedelta(hours=1), MatchStatus.SCHEDULED)                          # not due yet
    _match(db, now - timedelta(days=1), MatchStatus.FINISHED)                            # settled
    assert H.stored_match_counts(db, now) is before, "read again within the minute, the cached copy is served"
    H.forget_stored_counts()
    after = H.stored_match_counts(db, now)
    assert after["upcoming_stored"] - before["upcoming_stored"] == 1
    assert after["overdue_results"] - before["overdue_results"] == 2


class _RefusableFeed(MatchDataProvider):
    """Answers one day's fixtures with what it was given until it is told to refuse.

    Named apart from the real chain so that no row another test leaves behind can carry its name:
    the stamps this test reads are the ones it wrote.
    """

    name = "refusable_feed"
    integration_status = "test"

    def __init__(self, fixtures: List[ProviderFixture]):
        self.fixtures = list(fixtures)
        self.refusal: Optional[Exception] = None
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day: date, keys) -> List[ProviderFixture]:
        self.calls += 1
        if self.refusal is not None:
            raise self.refusal
        return list(self.fixtures)

    def get_live(self, keys):
        return []

    def get_results(self, date_from: date, date_to: date, keys):
        return []

    def get_standings(self, key):
        return []


def test_a_stale_copy_stored_again_after_the_refusal_moves_the_stamp_but_not_since(db):
    # Two days ahead, so `sync_day` makes the fixtures call alone: no results call, no live poll.
    day = (datetime.now(timezone.utc) + timedelta(days=2)).date()
    competition = ProviderCompetition(provider=_RefusableFeed.name, external_id="rf-pl", name="Premier League",
                                      key="premier_league")
    fixture = ProviderFixture(
        provider=_RefusableFeed.name, external_id=f"rf-{uuid.uuid4().hex[:8]}", competition=competition,
        home=ProviderTeam(provider=_RefusableFeed.name, external_id=f"rf-h-{uuid.uuid4().hex[:6]}", name="Restore Home FC"),
        away=ProviderTeam(provider=_RefusableFeed.name, external_id=f"rf-a-{uuid.uuid4().hex[:6]}", name="Restore Away FC"),
        kickoff_utc=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15),
        status=STATUS_SCHEDULED)
    feed = _RefusableFeed([fixture])
    redis = FakeRedis()
    cache = MatchCache(client=redis)

    first = MatchDataService(db, providers=[feed], cache=cache, keys=["premier_league"]).sync_day(day)
    assert first.source == "provider" and first.fixtures_stored == 1
    written = last_provider_writes(db)[feed.name]
    answered = datetime.fromisoformat(cache.get(f"provider:status:{feed.name}")["last_success_at"])

    # Access revoked. The 30-minute fresh copy runs out; the 24-hour stale copy is still there.
    feed.refusal = ProviderAuthError(LIVESCORE_401, provider=feed.name)
    for key in [key for key in redis.store if key.startswith("matchdata:fixtures:") and not key.endswith(":stale")]:
        redis.store.pop(key)
    service = MatchDataService(db, providers=[feed], cache=cache, keys=["premier_league"])
    second = service.sync_day(day)
    assert feed.calls == 2, "the provider was asked, and refused"
    assert second.source == "stale-cache" and second.fixtures_stored == 1, "the stale copy was stored again"

    chain = service.provider_status()["chain"]
    refused = datetime.fromisoformat(chain[0]["last_error_at"])
    restamped = last_provider_writes(db)[feed.name]
    # THE MECHANISM: the registry stamps the store, so the stamp moved past the refusal although
    # nothing answered.
    assert restamped > refused > written >= answered

    # What the block publishes is bounded by the provider's last answer, which the refusal followed.
    assert H.newest_provider_write({feed.name: restamped}, chain) == (answered, H.SINCE_BASIS_ANSWER)
    block = H.derive_match_data_state(chain=chain, active_provider=feed.name, scheduler=todays_scheduler(),
                                      provider_writes={feed.name: restamped}, now=refused + timedelta(minutes=1))
    assert block["since"] == answered.isoformat() and block["since_basis"] == H.SINCE_BASIS_ANSWER
    assert block["state"] == H.STATE_BLOCKED
    # And the cached aggregate the endpoints read carries the per-provider stamps for that check.
    assert H.stored_match_counts(db)["provider_writes"][feed.name] == restamped
