"""
What the stranded-fixture sweep is entitled to conclude from one call, and what it is not.

`match_metadata.recovery` can end up saying "we asked N times ... and stopped", and that sentence
is a claim about EVIDENCE: somebody asked the provider N times and it answered each time with no
result. So an ask only counts when the question was actually put and actually answered. Passes
through an outage, passes served out of the cache and passes that asked nothing are recorded apart
and can never retire a fixture.

Six outcomes per fixture per pass, and only one of them is evidence:

* PROVIDER_ERROR   -- a request went out and no provider answered it. Counted on the row, never
                      an attempt, never a reason to stop.
* CACHED           -- the day came out of the cache; this pass did not ask. No attempt.
* FRESH_UNANSWERED -- asked, answered, still no result. THE attempt.
* RECOVERED        -- settled during the pass, recorded with what settled it.
* DEFERRED         -- due, and no request was made: an allowance refused it before it left, or the
                      provider was cooling down after a failure. No attempt; still due; not an
                      outage, because nothing was unreachable.
* NOT_ASKED        -- nothing was due for it. Nothing is written.

When the sweep STOPS is the retry schedule's decision (`RETRY_SCHEDULE`), a budget policy: only
straight after an answered ask, and only when the next ask would fall past the horizon. The last
files pin that both ways, and that an outage past the horizon still retires nothing.

Requires PostgreSQL (same pattern as tests/services/test_duplicate_fixtures.py). Set
TEST_DATABASE_URL; skipped when unreachable.
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import sys
import uuid
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import Match, MatchStatus, Team
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.match_registry import (
    RETRY_HORIZON, MatchRegistry, RecoveryOutcome, classify_recovery_outcome, is_settled,
    retry_due,
)
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_LIVE, MatchDataProvider, ProviderCompetition, ProviderFixture,
    ProviderTeam,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

#: A fixed clock, so "two days ago" is the same day every run and never drifts over midnight.
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
#: One day behind the results lookback of 1 (which covers today and yesterday): the sweep's own.
STRANDED_DAYS_AGO = 2
KEY = "premier_league"


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
def sweep_script():
    """`scripts/repair_unsettled_matches.py`, loaded by path because `scripts/` is not a package."""
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "repair_unsettled_matches", os.path.join(backend, "scripts", "repair_unsettled_matches.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------------- helpers
def stranded(db, registry, *, days_ago: float = STRANDED_DAYS_AGO,
             status: MatchStatus = MatchStatus.LIVE) -> Match:
    """A fixture stuck past the lookback: kicked off, never settled, no refresh reaches it."""
    league = registry.ensure_canonical_league(KEY)
    home = Team(id=uuid.uuid4(), name=f"Home {uuid.uuid4().hex[:6]}", short_name="H",
                country="England", is_active=True)
    away = Team(id=uuid.uuid4(), name=f"Away {uuid.uuid4().hex[:6]}", short_name="A",
                country="England", is_active=True)
    db.add_all([home, away])
    db.flush()
    row = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                match_date=(NOW - timedelta(days=days_ago)).replace(tzinfo=None), status=status,
                external_api_id=None, external_api_source="livescore",
                match_metadata={"minute": "62"})
    db.add(row)
    db.flush()
    return row


def error_meta(*errors: str) -> SyncMeta:
    """What `_sync_results` leaves behind when a request went out and nobody answered it: the
    chain never set results_polled, and it recorded that a request had left."""
    return SyncMeta(source="database", results_polled=False, request_failed=True,
                    errors=list(errors) or ["results: livescore unreachable"])


def not_sent_meta(*errors: str) -> SyncMeta:
    """What `_call_chain` leaves behind when no request left at all: every provider was cooling
    down, or an allowance refused the request first. Errors, and `request_failed` still False."""
    return SyncMeta(source="database", results_polled=False, request_failed=False,
                    errors=list(errors))


def silent_day_meta() -> SyncMeta:
    """`_sync_results` returned before calling anything. No error, and still nobody was asked."""
    return SyncMeta(source="database", results_polled=False, errors=[])


def cached_meta(*, stale: bool = False) -> SyncMeta:
    return SyncMeta(source="stale-cache" if stale else "cache", provider="livescore",
                    results_polled=True, stale=stale, fixtures_seen=4, fixtures_stored=4)


def fresh_meta(**kwargs) -> SyncMeta:
    fields = dict(source="provider", provider="livescore", results_polled=True,
                  fixtures_seen=6, fixtures_stored=6)
    fields.update(kwargs)
    return SyncMeta(**fields)


def one_pass(registry: MatchRegistry, match: Match, meta: SyncMeta, *,
             settled_before: bool = False, now: datetime = NOW) -> RecoveryOutcome:
    """One sweep pass over one fixture, decided and recorded exactly as the script does it."""
    outcome, detail = classify_recovery_outcome(
        meta, settled_before=settled_before, settled_now=is_settled(match.status))
    registry.record_recovery_outcome(match, outcome, detail, now)
    return outcome


# ------------------------------------------------------- 1. the provider errored: no attempt
def test_a_pass_where_every_provider_failed_costs_no_attempt(db, registry):
    """
    Nobody was asked, so nothing was learned, so there is nothing to count against the fixture.

    An outage is a fact about the provider, not about the fixture. Letting it spend the
    fixture's attempts writes "no result after 3 attempts" about a question never put.
    """
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, error_meta("results: livescore 503"))

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.PROVIDER_ERROR
    assert state.get("attempts", 0) == 0, "an outage is not an attempt"
    assert not state.get("gave_up_at")
    assert state["provider_errors"] == 1, "recorded, because a sweep failing silently is its own defect"
    assert "503" in state["last_outcome_detail"]


def test_a_day_whose_providers_were_all_cooling_down_is_deferred_not_an_outage(db, registry):
    """`_call_chain` passed over a cooling provider without sending anything. Nobody was asked, so
    nobody was unreachable either: the ask is DEFERRED, and a reader is never told the provider
    could not be reached on the strength of a request that never left."""
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck,
                       not_sent_meta("livescore: skipped (recent failure: upstream error (HTTP 503))"))

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.DEFERRED
    assert state.get("attempts", 0) == 0 and not state.get("provider_errors")
    assert state["deferrals"] == 1 and state["last_outcome"] == "deferred"
    assert "no request was made" in state["last_outcome_detail"]
    assert retry_due(stuck, NOW), "nothing was asked, so it stays due"


def test_a_call_our_own_daily_ceiling_refused_is_deferred_not_an_outage(db, registry):
    """Our own ceiling refused the request before it left. That is a budget decision: DEFERRED,
    with the refusal's own words on the row, and never PROVIDER_ERROR."""
    stuck = stranded(db, registry)
    refusal = ("Daily request budget for livescore exhausted (1200/1200 used); refused by the daily "
               "ceiling we configured, not by the provider")

    outcome = one_pass(registry, stuck, not_sent_meta(refusal))

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.DEFERRED
    assert not state.get("provider_errors") and state.get("attempts", 0) == 0
    assert "refused by the daily ceiling we configured" in state["last_outcome_detail"]


def test_a_day_nobody_was_asked_about_at_all_is_not_an_outage_and_writes_nothing(db, registry):
    """No error either: no call was made at all. That is neither evidence nor a network failure.

    Filing it as a provider error would make a pass that simply had nothing due read like an
    outage, which is the confusion between "we did not ask" and "we could not reach anyone" that
    the outcomes exist to prevent.
    """
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, silent_day_meta())

    assert outcome is RecoveryOutcome.NOT_ASKED
    assert registry.recovery_state(stuck) == {}, "nothing happened to the fixture, so nothing is written"


def test_an_outage_of_any_length_retires_nobody(db, registry):
    """Many failed calls leave the fixture exactly where it was: still due, still ours."""
    stuck = stranded(db, registry)

    for _ in range(12):
        one_pass(registry, stuck, error_meta())

    state = registry.recovery_state(stuck)
    assert state.get("attempts", 0) == 0
    assert not state.get("gave_up_at")
    assert state["provider_errors"] == 12
    assert retry_due(stuck, NOW), "a failed call does not move the retry schedule"
    assert stuck.match_date.date() in registry.stale_unsettled_days(NOW, lookback_days=1)


# ------------------------------------------------------------ 2. served from cache: no attempt
@pytest.mark.parametrize("stale", [False, True])
def test_a_pass_served_from_the_cache_costs_no_attempt(db, registry, stale):
    """Reading the store is not this pass asking, whoever filled it and whenever they did."""
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, cached_meta(stale=stale))

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.CACHED
    assert state.get("attempts", 0) == 0
    assert not state.get("gave_up_at")
    assert state["cached_passes"] == 1


def test_a_fresh_cache_hit_and_a_stale_one_are_told_apart_on_the_row(db, registry):
    """
    Both are the cache and neither is an attempt, but a stale copy also means nobody is reachable.

    `SyncMeta.source` carries the difference, so it is reported rather than flattened.
    """
    fresh_hit, stale_hit = stranded(db, registry), stranded(db, registry)

    one_pass(registry, fresh_hit, cached_meta(stale=False))
    one_pass(registry, stale_hit, cached_meta(stale=True))

    assert registry.recovery_state(fresh_hit)["last_outcome_detail"] == "served from cache"
    assert registry.recovery_state(stale_hit)["last_outcome_detail"] == "served from stale-cache"


def test_a_cache_only_sweep_retires_nobody(db, registry):
    stuck = stranded(db, registry)

    for _ in range(12):
        one_pass(registry, stuck, cached_meta())

    assert not registry.recovery_state(stuck).get("gave_up_at")
    assert stuck.match_date.date() in registry.stale_unsettled_days(NOW, lookback_days=1)


# ------------------------------------------- 3. asked, answered, still nothing: THE attempt
def test_a_fresh_answer_that_omits_the_fixture_is_the_attempt(db, registry):
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, fresh_meta())

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.FRESH_UNANSWERED
    assert state["attempts"] == 1
    assert state["last_outcome"] == "fresh_unanswered"


def test_the_first_attempt_is_dated_by_the_first_attempt_and_never_by_a_later_one(db, registry):
    """`first_attempt_at` is the time of attempt 1, or absent - never the time of attempt 4.

    A row that counted attempts before the field existed has no record of when the first was.
    Stamping the next attempt's time on it would date the whole chase from its fourth ask, so
    the field stays absent there: unknown, rather than a wrong time presented as a known one.
    """
    fresh = stranded(db, registry)
    one_pass(registry, fresh, fresh_meta(), now=NOW)
    one_pass(registry, fresh, fresh_meta(), now=NOW + timedelta(hours=6))
    state = registry.recovery_state(fresh)
    assert state["attempts"] == 2
    assert state["first_attempt_at"] == NOW.isoformat(), "set by attempt 1 and kept by attempt 2"

    legacy = stranded(db, registry)
    legacy.match_metadata = dict(legacy.match_metadata, recovery={
        "attempts": 3, "last_attempt_at": (NOW - timedelta(hours=20)).isoformat(),
        "last_outcome": "fresh_unanswered"})
    db.flush()
    one_pass(registry, legacy, fresh_meta(), now=NOW)
    state = registry.recovery_state(legacy)
    assert state["attempts"] == 4
    assert "first_attempt_at" not in state, "the fourth attempt's time is not the first attempt's"


def test_fresh_answers_move_the_schedule_but_do_not_retire_a_recent_fixture(db, registry):
    """Answered with nothing, several times: the fixture is asked about LATER, not given up on.

    An empty answer says what the archive held at that moment. Two days after kickoff a result may
    still appear, so the answer pushes the next ask out along the retry schedule and nothing more.
    """
    stuck = stranded(db, registry)

    for _ in range(3):
        one_pass(registry, stuck, fresh_meta())

    state = registry.recovery_state(stuck)
    assert state["attempts"] == 3
    assert not state.get("gave_up_at"), "three empty answers two days in are not a reason to stop"
    assert not retry_due(stuck, NOW), "just asked: the schedule waits before the next ask"
    assert retry_due(stuck, NOW + timedelta(hours=6)), "two days old: one ask every six hours"
    assert stuck.status == MatchStatus.LIVE, "nothing is invented about the match itself"


def test_the_sweep_stops_only_where_the_schedule_runs_out_and_says_it_was_a_budget_decision(
        db, registry):
    """The one sentence the sweep may write when it stops: what it did, what came back, and why.

    Past the last scheduled ask the fixture is given up on, straight after an answered ask. The
    reason names the count and the last ask, and says in so many words that stopping is a limit on
    spending and not evidence that the result does not exist.
    """
    stuck = stranded(db, registry, days_ago=RETRY_HORIZON.days - 0.5)

    one_pass(registry, stuck, fresh_meta())

    state = registry.recovery_state(stuck)
    assert state["gave_up_at"] and state["stopped_by"] == "retry_budget"
    reason = state["gave_up_reason"]
    assert "asked the results provider 1 time" in reason
    assert NOW.strftime("%Y-%m-%d %H:%M UTC") in reason, "when we last asked"
    assert "request budget" in reason
    assert "not evidence that no result exists" in reason
    for claim in ("answers nothing", "live window", "no endpoint", "cannot exist", "never"):
        assert claim not in reason, f"the reason may not claim {claim!r}"
    assert stuck.status == MatchStatus.LIVE, "nothing is invented about the match itself"
    assert registry.stale_unsettled_days(NOW, lookback_days=1) == []


def test_an_error_earlier_in_the_chain_does_not_demote_an_answer_that_arrived(db, registry):
    """
    `_call_chain` records every provider it gave up on before the one that answered.

    So `errors` being non-empty is not a failed pass; `results_polled` being False is.
    """
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, fresh_meta(errors=["api_football: 401 unauthorised"]))

    assert outcome is RecoveryOutcome.FRESH_UNANSWERED
    assert registry.recovery_state(stuck)["attempts"] == 1


# ------------------------------------------------------------------ 4. it came back settled
def test_a_fixture_that_comes_back_settled_is_recorded_as_recovered(db, registry):
    """The point of the sweep. Nothing is left to retry, so no attempt is owed and none is taken."""
    stuck = stranded(db, registry)
    stuck.status = MatchStatus.FINISHED  # what `_sync_results` storing the provider's answer does
    db.flush()

    outcome = one_pass(registry, stuck, fresh_meta())

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.RECOVERED
    assert state.get("attempts", 0) == 0
    assert not state.get("gave_up_at")
    assert state["recovered_at"] == NOW.isoformat()
    assert "livescore" in state["recovered_by"], "what settled it, not merely that it settled"
    assert state["recovered_as"] == MatchStatus.FINISHED.value
    assert registry.stale_unsettled_days(NOW, lookback_days=1) == []


def test_a_fixture_already_settled_before_the_pass_is_not_a_recovery(db, registry):
    """
    A row that was FINISHED when the sweep started is not something the sweep recovered.

    Status alone cannot tell the two apart, so the before-state is required and a caller that
    offers an already-settled fixture is told it has the wrong fixture.
    """
    done = stranded(db, registry, status=MatchStatus.FINISHED)

    with pytest.raises(ValueError, match="already settled"):
        one_pass(registry, done, fresh_meta(), settled_before=True)

    assert registry.recovery_state(done) == {}


def test_a_recovery_during_an_outage_is_still_a_recovery(db, registry):
    """Something else settled it while the chain was down. Still nothing to retry; say what did."""
    stuck = stranded(db, registry)
    stuck.status = MatchStatus.FINISHED
    db.flush()

    outcome = one_pass(registry, stuck, error_meta())

    state = registry.recovery_state(stuck)
    assert outcome is RecoveryOutcome.RECOVERED
    assert state.get("attempts", 0) == 0
    assert "without this sweep's own call" in state["recovered_by"]


# ------------------------------------------------------------------------- 5. the boundary
def test_only_an_answered_ask_can_end_the_schedule(db, registry):
    """
    Same age, same number of passes, opposite verdicts: stopping follows evidence, not passes.

    Both fixtures are past the last scheduled ask. `by_evidence` is answered once and is given up
    on. `by_mixture` goes through an outage and a cache hit, neither of which is an answer, and is
    still in the sweep - still owed the answered ask that alone may end it.
    """
    age = RETRY_HORIZON.days - 0.5
    by_evidence, by_mixture = stranded(db, registry, days_ago=age), stranded(db, registry, days_ago=age)

    one_pass(registry, by_evidence, fresh_meta())
    for meta in (error_meta(), cached_meta()):
        one_pass(registry, by_mixture, meta)

    retired, still_asked = registry.recovery_state(by_evidence), registry.recovery_state(by_mixture)
    assert retired["attempts"] == 1 and retired["gave_up_at"]
    assert still_asked.get("attempts", 0) == 0
    assert not still_asked.get("gave_up_at")
    assert still_asked["provider_errors"] == 1 and still_asked["cached_passes"] == 1
    assert retry_due(by_mixture, NOW)


def test_a_fixture_past_the_horizon_is_not_given_up_while_nobody_can_be_asked(db, registry):
    """
    An outage can carry a fixture past the horizon; it may not retire it there.

    Stopping is a decision about spending on a question that keeps being answered with nothing.
    A fixture whose last calls reached nobody has not been answered, so it stays in the sweep -
    selected, due, and asked on the next pass the provider can be reached.
    """
    old = stranded(db, registry, days_ago=RETRY_HORIZON.days + 1)
    one_pass(registry, old, error_meta())

    state = registry.recovery_state(old)
    assert state.get("attempts", 0) == 0
    assert not state.get("gave_up_at")
    assert [m.id for m in registry.recoverable_unsettled(NOW)] == [old.id], (
        "the sweep has touched it, so it is still selected past the horizon")
    assert retry_due(old, NOW)

    one_pass(registry, old, fresh_meta())

    state = registry.recovery_state(old)
    assert state["gave_up_at"], "the first answered ask past the horizon ends it"
    assert "1 other request went out and got no answer, and is not counted" in state["gave_up_reason"]


# ------------------------------------------------- 6. the sweep end to end, with a stub provider
class StubProvider(MatchDataProvider):
    """A provider that answers exactly what a test tells it to, and counts what it was asked.

    BOTH endpoints obey `error`, because an outage is not endpoint-shaped: the sweep reopens
    `matches/history.json` for the days behind the lookback AND polls `matches/live.json` once,
    and a stub that failed only the first would have the sweep reach a live provider on the very
    pass a test calls an outage. `results_calls` and `live_calls` are counted apart so a test can
    say which question was put; `calls` is the results count the older tests read.
    """

    name = "livescore"
    integration_status = "primary"

    def __init__(self, results: Optional[List[ProviderFixture]] = None, error: Optional[Exception] = None,
                 live: Optional[List[ProviderFixture]] = None,
                 results_error: Optional[Exception] = None):
        self.results, self.error = results or [], error
        #: A failure of `matches/history.json` alone, with the live feed answering. Outages are
        #: not endpoint-shaped as a rule, but a 503 from one endpoint is the shape in which a
        #: results request goes out and fails without the live poll's failure cooling the
        #: provider down first.
        self.results_error = results_error
        self.live = list(live or [])
        self.calls = self.live_calls = 0

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return [competition()]

    def get_fixtures(self, day: date, keys):
        return []

    def get_live(self, keys):
        self.live_calls += 1
        if self.error:
            raise self.error
        return list(self.live)

    def get_results(self, date_from: date, date_to: date, keys):
        self.calls += 1
        if self.error or self.results_error:
            raise self.error or self.results_error
        return list(self.results)

    def get_standings(self, key: str):
        return []


class DictCache:
    """The match cache as a dict: no Redis, and a test can seed a day to force a cache hit."""

    def __init__(self):
        self.store, self.stale_store = {}, {}

    available = True

    def get(self, key):
        return self.store.get(key)

    def get_stale(self, key):
        return self.stale_store.get(key)

    def set(self, key, value, ttl, stale_ttl=None):
        self.store[key], self.stale_store[key] = value, value

    def delete(self, key):
        self.store.pop(key, None)
        self.stale_store.pop(key, None)


def competition() -> ProviderCompetition:
    return ProviderCompetition(provider="livescore", external_id="ls-premier_league",
                               name="Premier League", key=KEY, country="England", country_code="ENG")


def provider_fixture(external_id: str, *, status: str, kickoff: datetime,
                     home: str = "Everton", away: str = "Ipswich Town", **scores) -> ProviderFixture:
    """One fixture as a provider hands it over. Club names are the registry's identity check."""
    def team(name: str) -> ProviderTeam:
        return ProviderTeam(provider="livescore", name=name,
                            external_id="ls-" + "".join(c for c in name.lower() if c.isalnum()))

    return ProviderFixture(provider="livescore", external_id=external_id, competition=competition(),
                           home=team(home), away=team(away), kickoff_utc=kickoff, status=status, **scores)


@pytest.fixture
def live_fixture_kickoff() -> datetime:
    return (NOW - timedelta(days=STRANDED_DAYS_AGO)).replace(hour=14, minute=0, second=0, microsecond=0)


def build_service(db, provider: StubProvider) -> MatchDataService:
    return MatchDataService(db, providers=[provider], cache=DictCache(), now=NOW, keys=[KEY])


def run_sweep(sweep_script, service: MatchDataService, stuck: Match):
    """The script's own sweep, over the day the registry selects, with its printout captured."""
    days = service.registry.stale_unsettled_days(NOW, lookback_days=1, league_ids=service.league_ids())
    assert stuck.match_date.date() in days
    printed = io.StringIO()
    with redirect_stdout(printed):
        report = sweep_script.sweep(service, days, [stuck], NOW)
        sweep_script.report_outcomes(report)
    return report, printed.getvalue()


def landed_in(report: dict, outcome: RecoveryOutcome) -> List[str]:
    """The fixtures the pass filed under one outcome, as the report itself records them."""
    return [row["match_id"] for row in report["fixtures"] if row["outcome"] == outcome.value]


def reported_counts(sweep_script, report: str) -> dict:
    """
    The six numbers off the report's own summary block, keyed by the label it printed them under.

    Every bucket is printed on every pass, empty ones included, and always in enum order, so
    where a phrase lands in the text says nothing about what the pass concluded -- only the
    number on its line does. Reading all six also asserts that all six lines are there.
    """
    counts = {}
    for outcome in RecoveryOutcome:
        label = sweep_script.OUTCOME_REPORT[outcome][0]
        line = re.search(rf"^  {re.escape(label)} +(\d+) ", report, re.M)
        assert line, f"the summary has no line for {label!r}:\n{report}"
        counts[label] = int(line.group(1))
    return counts


def test_the_sweep_recovers_a_real_answer_and_never_calls_it_an_attempt(db, registry, sweep_script,
                                                                        live_fixture_kickoff):
    """
    End to end through `_sync_results`: LIVE at minute 62, the provider says 2-1, the row settles.

    No provider is spent: the stub answers in place of the real chain.
    """
    stuck = registry.upsert_fixture(provider_fixture("ls-1", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    assert stuck is not None and stuck.status == MatchStatus.LIVE
    provider = StubProvider([provider_fixture("ls-1", status=STATUS_FINISHED, kickoff=live_fixture_kickoff,
                                              home_score=2, away_score=1)])

    report, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    state = registry.recovery_state(stuck)
    assert provider.calls == 1, "one results request for the one day the registry selected"
    assert provider.live_calls == 1, "and one live poll, made because the fixture was due"
    assert landed_in(report, RecoveryOutcome.RECOVERED) == [str(stuck.id)]
    assert stuck.status == MatchStatus.FINISHED
    assert state.get("attempts", 0) == 0
    assert state["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1", "the score the provider gave, read back off the row"
    assert re.search(r"^  recovered\s+1\s", printed, re.M), printed


def test_a_fixture_the_provider_rescheduled_across_midnight_still_records_its_outcome(
        db, registry, sweep_script, live_fixture_kickoff):
    """
    A fixture is looked up under the day it was SWEPT under, not under where the answer left it.

    `_sync_results` stores the provider's answer through `_apply_fixture`, which moves the stored
    kickoff to the provider's. When that move crosses a UTC midnight, the fixture's day no longer
    matches any day this pass reopened, and looking the meta up by the new date finds nothing: the
    pass records no outcome and reports the fixture as untouched. Here the same answer also
    settled it, so what would be thrown away is a recovery -- the whole point of the sweep.
    """
    stuck = registry.upsert_fixture(provider_fixture("ls-6", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    swept_day = stuck.match_date.date()
    moved = (live_fixture_kickoff + timedelta(days=1)).replace(hour=1)  # the next UTC day
    provider = StubProvider([provider_fixture("ls-6", status=STATUS_FINISHED, kickoff=moved,
                                              home_score=2, away_score=1)])

    report, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    assert stuck.match_date.date() == moved.date() != swept_day, "the provider moved it past midnight"
    assert landed_in(report, RecoveryOutcome.RECOVERED) == [str(stuck.id)]
    state = registry.recovery_state(stuck)
    assert state["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1"
    assert state.get("attempts", 0) == 0
    assert reported_counts(sweep_script, printed)["recovered"] == 1


def test_the_sweep_does_not_count_an_attempt_when_the_results_request_fails(
        db, registry, sweep_script, live_fixture_kickoff):
    """The results request about this fixture went out and got no answer: PROVIDER_ERROR, no
    attempt, and the pass reports the failed request."""
    from app.services.providers.base import ProviderError

    stuck = registry.upsert_fixture(provider_fixture("ls-2", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    provider = StubProvider(results_error=ProviderError("livescore: 503 from results"))

    report, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    assert provider.calls == 1, "the results request went out"
    assert landed_in(report, RecoveryOutcome.PROVIDER_ERROR) == [str(stuck.id)]
    assert registry.recovery_state(stuck).get("attempts", 0) == 0
    assert stuck.status == MatchStatus.LIVE
    assert any(call.startswith("results") for call in report["failed_calls"])


def test_a_whole_provider_outage_defers_the_fixture_and_reports_the_request_that_failed(
        db, registry, sweep_script, live_fixture_kickoff):
    """
    The provider is down on every endpoint. The pass's live poll goes out first and fails, and the
    cool-down it sets means the results request about this fixture never leaves.

    Two facts, and each is written where it is true: the PASS made a request nobody answered, and
    reports it as the outage it is; the FIXTURE was not asked about, so it is DEFERRED - not
    "could not reach the provider", which would describe a request that was never made.
    """
    from app.services.providers.base import ProviderError

    stuck = registry.upsert_fixture(provider_fixture("ls-7", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    provider = StubProvider(error=ProviderError("livescore: 503"))

    report, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    assert provider.live_calls == 1 and provider.calls == 0, "the history request never left"
    assert landed_in(report, RecoveryOutcome.DEFERRED) == [str(stuck.id)]
    assert landed_in(report, RecoveryOutcome.PROVIDER_ERROR) == []
    state = registry.recovery_state(stuck)
    assert state["last_outcome"] == "deferred" and not state.get("provider_errors")
    assert "cooling" in state["last_outcome_detail"] or "recent failure" in state["last_outcome_detail"]
    assert report["failed_calls"] and report["failed_calls"][0].startswith("live:")
    assert report["results_requests"] == 0, "nothing was sent to the archive, so nothing is charged"
    assert "REQUESTS NOBODY ANSWERED" in printed
    assert reported_counts(sweep_script, printed)["deferred"] == 1


def test_the_sweep_counts_an_attempt_when_the_provider_answers_without_the_fixture(
        db, registry, sweep_script, live_fixture_kickoff):
    """The provider was reached and named other games. That is evidence, and it is the attempt."""
    stuck = registry.upsert_fixture(provider_fixture("ls-3", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    # Different clubs, three hours later. The registry identifies a fixture by its clubs and its
    # kickoff, so anything closer than this is read as another sighting of the stored row and
    # settles it -- the other half of the pass, and not the one under test here.
    other = provider_fixture("ls-other", status=STATUS_FINISHED, home="Chelsea", away="Arsenal",
                             kickoff=live_fixture_kickoff + timedelta(hours=3),
                             home_score=0, away_score=0)

    report, _ = run_sweep(sweep_script, build_service(db, StubProvider([other])), stuck)

    assert landed_in(report, RecoveryOutcome.FRESH_UNANSWERED) == [str(stuck.id)]
    assert registry.recovery_state(stuck)["attempts"] == 1
    assert stuck.status == MatchStatus.LIVE


def test_the_report_tells_a_down_provider_from_a_provider_with_nothing_to_say(
        db, registry, sweep_script, live_fixture_kickoff):
    """
    A reader budgeting a sweep has to separate them: one says the provider could not be reached,
    the other says it answered and had nothing for these fixtures yet. Both leave the fixture
    unsettled, so only the report and the row say which happened.

    Both passes are read the same way: which bucket the fixture landed in, what its row now says,
    and the six counts in the summary.
    """
    from app.services.providers.base import ProviderError

    down = registry.upsert_fixture(provider_fixture("ls-4", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    outage, outage_report = run_sweep(
        sweep_script, build_service(db, StubProvider(results_error=ProviderError("503"))), down)

    # The outage: the request about it went out and nobody answered, so the fixture is in the
    # error bucket and owes nothing. Read now, because the second sweep's call covers this
    # fixture's day too.
    assert landed_in(outage, RecoveryOutcome.PROVIDER_ERROR) == [str(down.id)]
    assert landed_in(outage, RecoveryOutcome.FRESH_UNANSWERED) == []
    outage_state = registry.recovery_state(down)
    assert outage_state["last_outcome"] == RecoveryOutcome.PROVIDER_ERROR.value
    assert outage_state.get("attempts", 0) == 0
    assert outage_state["provider_errors"] == 1
    assert reported_counts(sweep_script, outage_report) == {
        "provider error": 1, "fresh, no result": 0, "cached": 0, "recovered": 0,
        "deferred": 0, "not asked": 0}
    assert "503" in outage_report, "the report names what failed, not merely that something did"
    assert "REQUESTS NOBODY ANSWERED" in outage_report, "and says it was an outage"
    assert outage["failed_calls"], "the pass itself reports the outage"

    # Its own clubs: two fixtures with the same clubs at the same kickoff are one fixture to the
    # registry, and this test needs two rows swept independently.
    silent = registry.upsert_fixture(provider_fixture("ls-5", status=STATUS_LIVE, home="Chelsea",
                                                      away="Arsenal", kickoff=live_fixture_kickoff))
    db.commit()
    silence, silence_report = run_sweep(sweep_script, build_service(db, StubProvider([])), silent)

    # The silence: asked and answered with nothing, which is the one outcome that is evidence.
    assert landed_in(silence, RecoveryOutcome.FRESH_UNANSWERED) == [str(silent.id)]
    assert landed_in(silence, RecoveryOutcome.PROVIDER_ERROR) == []
    silence_state = registry.recovery_state(silent)
    assert silence_state["last_outcome"] == RecoveryOutcome.FRESH_UNANSWERED.value
    assert silence_state["attempts"] == 1
    assert silence_state["archive"]["state"] == "empty", "what the archive returned is on the row"
    assert silence["failed_calls"] == [], "an empty answer is not an outage"
    assert reported_counts(sweep_script, silence_report) == {
        "fresh, no result": 1, "provider error": 0, "cached": 0, "recovered": 0,
        "deferred": 0, "not asked": 0}
