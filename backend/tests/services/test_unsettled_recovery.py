"""
What the stranded-fixture sweep is entitled to conclude from one pass, and what it is not.

`match_metadata.recovery` ends up saying "no result after 3 attempts" about a fixture, and that
sentence is a claim about EVIDENCE: somebody asked the provider, three times, and the provider had
nothing. So a pass only counts when the question was actually put and actually answered. Three
passes through an outage, or three served out of the cache, are three passes in which nobody
learned anything about the fixture, and retiring it on those would put a false sentence on the row.

Four outcomes per fixture per pass, and only one of them is evidence:

* PROVIDER_ERROR   -- the chain failed or every provider was cooling down; the question was never
                      put. Counted on the row (a sweep failing silently for a week is its own
                      defect) but it may not retire anything.
* CACHED           -- the day came out of the cache, fresh or stale. This pass did not ask, and
                      the store does not say who filled it (readers share the key), so nothing
                      here can be dated to a question the sweep put: no attempt is owed.
* FRESH_UNANSWERED -- asked, answered, still no result. THE attempt.
* RECOVERED        -- settled during the pass. Nothing left to retry; recorded with what settled
                      it, and never retired.

The last file pins the boundary both ways: `STALE_SWEEP_MAX_ATTEMPTS` reached by fresh answers
retires, and the same number of passes reached through a mixture including errors does not.

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
    STALE_SWEEP_MAX_AGE, STALE_SWEEP_MAX_ATTEMPTS, MatchRegistry, RecoveryOutcome,
    classify_recovery_outcome, is_settled,
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
def stranded(db, registry, *, days_ago: int = STRANDED_DAYS_AGO,
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
    """What `_sync_results` leaves behind when the whole chain failed: it never set results_polled."""
    return SyncMeta(source="database", results_polled=False,
                    errors=list(errors) or ["results: livescore unreachable"])


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


def test_a_day_whose_providers_were_all_cooling_down_costs_no_attempt(db, registry):
    """`_call_chain` skips a cooling provider and records it as an error; nobody was asked."""
    stuck = stranded(db, registry)

    one_pass(registry, stuck, error_meta("livescore: skipped (recent failure: quota spent)"))

    assert registry.recovery_state(stuck).get("attempts", 0) == 0


def test_a_day_nobody_was_asked_about_at_all_costs_no_attempt(db, registry):
    """No error either: `_sync_results` can return before it calls anything. Still no evidence."""
    stuck = stranded(db, registry)

    outcome = one_pass(registry, stuck, silent_day_meta())

    assert outcome is RecoveryOutcome.PROVIDER_ERROR
    assert registry.recovery_state(stuck).get("attempts", 0) == 0
    assert "no results call was made" in registry.recovery_state(stuck)["last_outcome_detail"]


def test_an_outage_lasting_longer_than_the_attempt_limit_retires_nobody(db, registry):
    """A week of failures leaves the fixture exactly where it was: still asked about, still ours."""
    stuck = stranded(db, registry)

    for _ in range(STALE_SWEEP_MAX_ATTEMPTS + 2):
        one_pass(registry, stuck, error_meta())

    state = registry.recovery_state(stuck)
    assert state.get("attempts", 0) == 0
    assert not state.get("gave_up_at")
    assert state["provider_errors"] == STALE_SWEEP_MAX_ATTEMPTS + 2
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

    for _ in range(STALE_SWEEP_MAX_ATTEMPTS + 1):
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


def test_enough_fresh_answers_with_nothing_in_them_retire_the_fixture(db, registry):
    """The one sentence the sweep may write: asked this many times, answered, still no result."""
    stuck = stranded(db, registry)

    for _ in range(STALE_SWEEP_MAX_ATTEMPTS):
        one_pass(registry, stuck, fresh_meta())

    state = registry.recovery_state(stuck)
    assert state["attempts"] == STALE_SWEEP_MAX_ATTEMPTS
    assert f"no result after {STALE_SWEEP_MAX_ATTEMPTS} attempts" in state["gave_up_reason"]
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
    assert "without this sweep's results call" in state["recovered_by"]


# ------------------------------------------------------------------------- 5. the boundary
def test_the_limit_is_reached_by_fresh_answers_and_by_nothing_else(db, registry):
    """
    Same number of passes, opposite verdicts: the count is of evidence, not of passes.

    `by_evidence` is asked three times and answered three times, so it is retired. `by_mixture`
    is put through the same three passes, but two of them learned nothing -- one outage and one
    cache hit -- so it has been answered once and stays in the sweep.
    """
    by_evidence, by_mixture = stranded(db, registry), stranded(db, registry)

    for _ in range(STALE_SWEEP_MAX_ATTEMPTS):
        one_pass(registry, by_evidence, fresh_meta())
    for meta in (error_meta(), cached_meta(), fresh_meta()):
        one_pass(registry, by_mixture, meta)

    retired, still_asked = registry.recovery_state(by_evidence), registry.recovery_state(by_mixture)
    assert retired["attempts"] == STALE_SWEEP_MAX_ATTEMPTS and retired["gave_up_at"]
    assert still_asked["attempts"] == 1, "one pass in three actually asked"
    assert not still_asked.get("gave_up_at")
    assert still_asked["provider_errors"] == 1 and still_asked["cached_passes"] == 1


def test_one_fresh_answer_short_of_the_limit_is_not_enough(db, registry):
    stuck = stranded(db, registry)

    for _ in range(STALE_SWEEP_MAX_ATTEMPTS - 1):
        one_pass(registry, stuck, fresh_meta())

    assert not registry.recovery_state(stuck).get("gave_up_at")
    assert stuck.match_date.date() in registry.stale_unsettled_days(NOW, lookback_days=1)


def test_a_fixture_past_the_horizon_is_given_up_even_when_nobody_could_be_asked(db, registry):
    """
    Age is a fact about the fixture and the provider's results window, not about this pass.

    The reason names the age and never claims an answer, so it stays true while the chain is down.
    """
    old = stranded(db, registry, days_ago=STALE_SWEEP_MAX_AGE.days + 1)

    one_pass(registry, old, error_meta())

    state = registry.recovery_state(old)
    assert state.get("attempts", 0) == 0
    assert "results horizon" in state["gave_up_reason"]
    assert "attempts" not in state["gave_up_reason"]


# ------------------------------------------------- 6. the sweep end to end, with a stub provider
class StubProvider(MatchDataProvider):
    """A provider that answers exactly what a test tells it to, and counts what it was asked."""

    name = "livescore"
    integration_status = "primary"

    def __init__(self, results: Optional[List[ProviderFixture]] = None, error: Optional[Exception] = None):
        self.results, self.error, self.calls = results or [], error, 0

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return [competition()]

    def get_fixtures(self, day: date, keys):
        return []

    def get_live(self, keys):
        return []

    def get_results(self, date_from: date, date_to: date, keys):
        self.calls += 1
        if self.error:
            raise self.error
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
    """The script's own sweep, over the day the registry selects, with its report captured."""
    days = service.registry.stale_unsettled_days(NOW, lookback_days=1, league_ids=service.league_ids())
    assert stuck.match_date.date() in days
    printed = io.StringIO()
    with redirect_stdout(printed):
        by_outcome = sweep_script.sweep(service, days, [stuck], NOW)
        sweep_script.report_outcomes(by_outcome, service.registry)
    return by_outcome, printed.getvalue()


def reported_counts(sweep_script, report: str) -> dict:
    """
    The four numbers off the report's own summary block, keyed by the label it printed them under.

    Every bucket is printed on every pass, empty ones included, and always in enum order, so
    where a phrase lands in the text says nothing about what the pass concluded -- only the
    number on its line does. Reading all four also asserts that all four lines are there.
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

    by_outcome, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    state = registry.recovery_state(stuck)
    assert provider.calls == 1, "one results request for the one day the registry selected"
    assert [m.id for m, _ in by_outcome[RecoveryOutcome.RECOVERED]] == [stuck.id]
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

    by_outcome, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    assert stuck.match_date.date() == moved.date() != swept_day, "the provider moved it past midnight"
    assert [m.id for m, _ in by_outcome[RecoveryOutcome.RECOVERED]] == [stuck.id]
    state = registry.recovery_state(stuck)
    assert state["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1"
    assert state.get("attempts", 0) == 0
    assert reported_counts(sweep_script, printed)["recovered"] == 1


def test_the_sweep_does_not_count_an_attempt_when_the_provider_is_down(db, registry, sweep_script,
                                                                       live_fixture_kickoff):
    from app.services.providers.base import ProviderError

    stuck = registry.upsert_fixture(provider_fixture("ls-2", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    provider = StubProvider(error=ProviderError("livescore: 503 from results"))

    by_outcome, printed = run_sweep(sweep_script, build_service(db, provider), stuck)

    assert [m.id for m, _ in by_outcome[RecoveryOutcome.PROVIDER_ERROR]] == [stuck.id]
    assert registry.recovery_state(stuck).get("attempts", 0) == 0
    assert stuck.status == MatchStatus.LIVE


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

    by_outcome, _ = run_sweep(sweep_script, build_service(db, StubProvider([other])), stuck)

    assert [m.id for m, _ in by_outcome[RecoveryOutcome.FRESH_UNANSWERED]] == [stuck.id]
    assert registry.recovery_state(stuck)["attempts"] == 1
    assert stuck.status == MatchStatus.LIVE


def test_the_report_tells_a_down_provider_from_a_provider_with_nothing_to_say(
        db, registry, sweep_script, live_fixture_kickoff):
    """
    A reader budgeting a sweep has to separate them: one says wait for the provider to come back,
    the other says these fixtures are not coming back. Both leave the fixture unsettled, so only
    the report and the row say which happened.

    Both passes are read the same way: which bucket the fixture landed in, what its row now says,
    and the four counts in the summary.
    """
    from app.services.providers.base import ProviderError

    down = registry.upsert_fixture(provider_fixture("ls-4", status=STATUS_LIVE, kickoff=live_fixture_kickoff))
    db.commit()
    outage, outage_report = run_sweep(
        sweep_script, build_service(db, StubProvider(error=ProviderError("503"))), down)

    # Its own clubs: two fixtures with the same clubs at the same kickoff are one fixture to the
    # registry, and this test needs two rows swept independently.
    silent = registry.upsert_fixture(provider_fixture("ls-5", status=STATUS_LIVE, home="Chelsea",
                                                      away="Arsenal", kickoff=live_fixture_kickoff))
    db.commit()
    silence, silence_report = run_sweep(sweep_script, build_service(db, StubProvider([])), silent)

    # The outage: the question was never put, so the fixture is in the error bucket and owes nothing.
    assert [m.id for m, _ in outage[RecoveryOutcome.PROVIDER_ERROR]] == [down.id]
    assert outage[RecoveryOutcome.FRESH_UNANSWERED] == []
    outage_state = registry.recovery_state(down)
    assert outage_state["last_outcome"] == RecoveryOutcome.PROVIDER_ERROR.value
    assert outage_state.get("attempts", 0) == 0
    assert outage_state["provider_errors"] == 1
    assert reported_counts(sweep_script, outage_report) == {
        "provider error": 1, "fresh, no result": 0, "cached": 0, "recovered": 0}
    assert "503" in outage_report, "the report names what failed, not merely that something did"

    # The silence: asked and answered with nothing, which is the one outcome that is evidence.
    assert [m.id for m, _ in silence[RecoveryOutcome.FRESH_UNANSWERED]] == [silent.id]
    assert silence[RecoveryOutcome.PROVIDER_ERROR] == []
    silence_state = registry.recovery_state(silent)
    assert silence_state["last_outcome"] == RecoveryOutcome.FRESH_UNANSWERED.value
    assert silence_state["attempts"] == 1
    assert reported_counts(sweep_script, silence_report) == {
        "fresh, no result": 1, "provider error": 0, "cached": 0, "recovered": 0}
