"""
The journey proof: every verdict it can give, and the guarantees that make it safe on the live system.

`scripts/prove_journey.py` reads the live database, Redis and the API to say how far each fixture
has come along fixture -> forecast -> suggestion -> stored result -> settlement. These tests pin
what would make it lie or do harm:

* a classifier that calls a fixture `failed` when nobody could be asked about it, or `proven`
  on evidence that does not show it;
* an access detector fooled by one of the signals that have already been seen to lie - a
  fallback's HTTP 200 carrying a plan error, a recovery pass that "succeeded" having sent
  nothing, a row touched by bookkeeping;
* an HTTP request that reaches an endpoint which asks a provider or settles slips, a Redis write,
  a database write, or the settlement rule applied with the function that WRITES it;
* an email, an id or a credential in a file committed to a public repository.

The database test needs PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test
database named by TEST_DATABASE_URL, tests/conftest.py); it is skipped
when unreachable. It commits its own rows and removes them again, so point it at a database no
other run is using. No provider is ever called.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core import source_identity
from app.core.config import settings
from app.db.base import Base
from app.models.predictions import League, Match, MatchResult, MatchStatus, PredictionOutcome, Team
from app.models.provider_data import ProviderForecastRecord, ProviderForecastResult, ProviderForecastSnapshot
from app.models.slips import SelectionSlip, SelectionSlipLeg
from app.models.users import User
from app.services import slip_settlement
from app.services.providers.budget import (
    SCHEDULER_SENT_KEY, budget_key, read_scheduler_sent, read_transmitted, transmitted_key,
)
from scripts import prove_journey as pj
from tests.providers.support import FakeRedis

from tests.conftest import TEST_DATABASE_URL  # noqa: E402 - one place for the default

UTC = timezone.utc
SINCE = pj._instant(pj.DEFAULT_ACCESS_SINCE)
#: The moment the survey read the status endpoint, and every fixture below is judged at.
MEASURED_AT = datetime(2026, 10, 7, 1, 6, 2, tzinfo=UTC)

LIVESCORE_401 = ("livescore: authentication rejected (HTTP 401): This API key and secret do not have access to "
                 "our data enabled")
API_FOOTBALL_PLAN = ("API-Football errors: {'plan': 'Free plans do not have access to this season, try from 2022 "
                     "to 2024.'}")
THESPORTSDB_400 = ('thesportsdb: request rejected (HTTP 400): {"Message":"Invalid Premium API key: Signup here: '
                   'https:\\/\\/www.thesportsdb.com\\/pricing"}')


def measured_status() -> dict:
    """GET /api/v1/data-providers/status as it answered at 2026-10-07 01:06:02 UTC, trimmed to the
    fields the proof reads. Live Score refuses, API-Football answers 200 with a plan error,
    TheSportsDB refuses its key, GameForecast has spent its 8 and the recovery task "succeeded"
    having sent nothing.

    The fixtures and results tasks' `last_requests_sent` and day counts are those of the same two
    passes (last run 01:04:46), as the endpoint still reported them at 02:14:58. The results pass
    shows why `last_result.requests` is not read as "sent": it counted the 2 competitions it put to
    the chain, and every provider was skipped in cool-down, so nothing left."""
    def budget(provider, used, sent, answered, status):
        return {"provider": provider, "used_today": used, "scheduler_sent": {"total": sent, "by_task": {}},
                "transmitted_today": {"answered": answered, "no_answer": 0, "not_connected": 0,
                                      "last_status": status}}
    return {
        "active_provider": "livescore",
        "chain": [
            {"name": "livescore", "budget": budget("livescore", 2, 3744, 2, 401), "cooling_down": LIVESCORE_401,
             "last_success_at": "2026-10-02T14:53:28.028159+00:00", "last_error": LIVESCORE_401,
             "last_error_at": "2026-10-07T01:04:45.307108+00:00"},
            {"name": "api_football", "budget": budget("api_football", 1, 159, 1, 200), "cooling_down": API_FOOTBALL_PLAN,
             "last_success_at": "2026-10-06T00:55:24.221370+00:00", "last_error": API_FOOTBALL_PLAN,
             "last_error_at": "2026-10-07T01:04:45.927317+00:00"},
            {"name": "thesportsdb", "budget": budget("thesportsdb", 1, 11, 1, 400), "cooling_down": THESPORTSDB_400,
             "last_success_at": "2026-10-05T21:39:12.435861+00:00", "last_error": THESPORTSDB_400,
             "last_error_at": "2026-10-07T01:04:46.105929+00:00"},
        ],
        "forecasts": {"active_provider": "gameforecast", "cooling_down": None,
                      "budget": dict(budget("gameforecast", 8, 74, 8, 200), daily_limit=8, remaining_today=0,
                                     effective_remaining_today=0)},
        "scheduler": {"tasks": {
            "fixtures": {"last_run_at": "2026-10-07T01:04:46.116357+00:00",
                         "last_success_at": "2026-10-02T13:07:44.765961+00:00", "consecutive_failures": 15,
                         "last_error": LIVESCORE_401, "next_due_at": "2026-10-07T07:04:46.116357+00:00",
                         "last_requests_sent": {"livescore": 2, "api_football": 1, "thesportsdb": 1},
                         "last_result": {"days": {day: {"source": "database", "forward_source": None}
                                                  for day in ("2026-10-07", "2026-10-08", "2026-10-09")},
                                         "days_answered": 0, "days_from_stale_cache": 0, "days_unanswered": 3,
                                         "forward_answer": "not_answered"}},
            "results": {"last_run_at": "2026-10-07T01:04:46.639394+00:00",
                        "last_success_at": "2026-10-02T14:53:28.028159+00:00", "consecutive_failures": 19,
                        "last_error": LIVESCORE_401, "last_requests_sent": {},
                        "last_result": {"requests": 2, "errors": [LIVESCORE_401]}},
            "recover": {"last_success_at": "2026-10-07T01:04:47.000000+00:00", "consecutive_failures": 0,
                        "last_result": {"requests": 0}},
            "forecasts": {"last_success_at": "2026-10-07T01:04:55.000000+00:00", "consecutive_failures": 0,
                          "next_due_at": "2026-10-07T03:04:55.000000+00:00"},
            "settle": {"last_success_at": "2026-10-07T01:04:55.000000+00:00", "consecutive_failures": 0},
        }},
        "checked_at": "2026-10-07T01:06:02.000000+00:00",
    }


#: What the database said at the same moment: nothing stored since the outage began, except the
#: recovery bookkeeping that bumped matches.updated_at at 01:04:47.
MEASURED_STORED = {
    "newest_last_synced_at": "2026-10-02T14:52:26Z", "first_last_synced_after_since": None,
    "newest_result_created_at": "2026-10-02T13:36:37Z", "first_result_created_after_since": None,
    "newest_result_updated_at": "2026-10-02T13:36:37Z", "newest_match_created_at": "2026-10-02T14:46:16Z",
    "newest_match_updated_at": "2026-10-07T01:04:47Z",
}

BLOCKED = {"verdict": "blocked", "missing": ["primary_provider_answering"]}
PARTIAL = {"verdict": "partial", "missing": ["primary_provider_answering"]}


def returned(by: datetime) -> dict:
    return {"verdict": "returned", "missing": [], "returned_no_later_than": pj._iso(by)}


# ----------------------------------------------------------------------------- row builders
def naive(instant: datetime) -> datetime:
    return instant.astimezone(UTC).replace(tzinfo=None)


def match_row(kickoff: datetime, status: MatchStatus = MatchStatus.SCHEDULED, created: datetime = None,
              synced: datetime = None, recovery: dict = None, **meta) -> SimpleNamespace:
    metadata = dict(meta)
    if synced is not None:
        metadata["last_synced_at"] = synced.isoformat()
    if recovery is not None:
        metadata["recovery"] = recovery
    return SimpleNamespace(id=uuid.uuid4(), league_id=uuid.uuid4(), match_date=naive(kickoff), status=status,
                           created_at=naive(created or kickoff - timedelta(days=7)), match_metadata=metadata,
                           external_api_source="livescore", external_api_id="livescore:1")


def snapshot_row(first: datetime, before_kickoff=True, last: datetime = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), provider="gameforecast", first_fetched_at=naive(first),
                           last_fetched_at=naive(last or first), captured_before_kickoff=before_kickoff,
                           kickoff_at_capture=None, model_run_at=None)


def result_row(home: int, away: int, created: datetime, ht=(None, None)) -> SimpleNamespace:
    return SimpleNamespace(home_score=home, away_score=away, home_score_ft=home, away_score_ft=away,
                           home_score_ht=ht[0], away_score_ht=ht[1], home_score_et=None, away_score_et=None,
                           home_score_pens=None, away_score_pens=None, created_at=naive(created),
                           updated_at=naive(created), result_metadata={"provider": "livescore"})


def leg_row(market: str, outcome: str, line=None, state: str = "pending", created: datetime = None,
            snapshot=True, source: str = "provider", settled: datetime = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), slip_id=uuid.uuid4(), match_id=None, position=0, market_id=market,
                           outcome=outcome, line=Decimal(str(line)) if line is not None else None,
                           probability=Decimal("0.5"), probability_source=source,
                           snapshot_id=uuid.uuid4() if snapshot else None,
                           created_at=naive(created) if created else None, state=state,
                           settled_at=naive(settled) if settled else None, settlement=None,
                           slip_status="recorded", owner_is_qa=True)


def score_row(settled: datetime) -> SimpleNamespace:
    return SimpleNamespace(snapshot_id=uuid.uuid4(), settled_at=naive(settled), outcome=PredictionOutcome.WON,
                           is_correct=True, rules_version="soccer-regulation-time-v2", void_reason=None)


NOW = MEASURED_AT
PAST = NOW - timedelta(days=2)          # a fixture that kicked off two days ago
FUTURE = NOW + timedelta(days=2)


# ===================================================================== stage 1: fixture_stored
def test_a_fixture_stored_before_the_outage_is_proven_and_not_current():
    stage = pj.classify_fixture_stored(match_row(PAST, created=SINCE - timedelta(days=5),
                                                 synced=SINCE - timedelta(hours=2)), SINCE)
    assert stage["verdict"] == "proven"


@pytest.mark.parametrize("created,synced", [(SINCE + timedelta(hours=1), None),
                                            (SINCE - timedelta(days=5), SINCE + timedelta(minutes=1))])
def test_a_fixture_created_or_synced_after_the_outage_is_current(created, synced):
    assert pj.classify_fixture_stored(match_row(PAST, created=created, synced=synced), SINCE)["verdict"] == "proven_current"


def test_no_row_is_not_found():
    assert pj.classify_fixture_stored(None, SINCE)["verdict"] == "not_found"


# ================================================================== stage 2: forecast_attached
def test_a_snapshot_captured_before_kickoff_proves_the_forecast():
    stage = pj.classify_forecast(match_row(PAST), [snapshot_row(PAST - timedelta(hours=10))], [], NOW)
    assert stage["verdict"] == "proven"
    assert stage["at"] == pj._iso(PAST - timedelta(hours=10))


def test_a_snapshot_with_no_capture_flag_is_placed_by_its_first_retrieval():
    before = snapshot_row(PAST - timedelta(hours=1), before_kickoff=None)
    after = snapshot_row(PAST + timedelta(hours=1), before_kickoff=None)
    assert pj.classify_forecast(match_row(PAST), [before], [], NOW)["verdict"] == "proven"
    assert pj.classify_forecast(match_row(PAST), [after], [], NOW)["verdict"] == "failed"


def test_a_forecast_retrieved_only_after_kickoff_fails_the_stage():
    stage = pj.classify_forecast(match_row(PAST), [snapshot_row(PAST + timedelta(hours=1), before_kickoff=False)], [], NOW)
    assert stage["verdict"] == "failed"
    assert "after kickoff" in stage["evidence"]["detail"]


def test_an_upcoming_fixture_without_a_forecast_is_pending_with_the_next_pass():
    stage = pj.classify_forecast(match_row(FUTURE), [], [], NOW, {"remaining_today": 3, "cooling_down": None},
                                 {"next_due_at": "2026-10-07T03:04:55Z"})
    assert stage["verdict"] == "pending"
    assert stage["evidence"]["next_due_at"] == "2026-10-07T03:04:55Z"


@pytest.mark.parametrize("forecasts", [{"remaining_today": 0, "cooling_down": None},
                                       {"remaining_today": 5, "cooling_down": "gameforecast: HTTP 429"}])
def test_an_upcoming_fixture_waits_on_a_spent_or_cooling_forecast_provider(forecasts):
    assert pj.classify_forecast(match_row(FUTURE), [], [], NOW, forecasts)["verdict"] == "blocked: forecast provider"


def test_a_fixture_that_kicked_off_with_no_forecast_is_absent_not_failed():
    assert pj.classify_forecast(match_row(PAST), [], [], NOW)["verdict"] == "absent"


# ========================================================================= stage 3: suggestion
def suggestions_body(match_id=None, fixtures_in_window=4, qualifying=4, excluded=None) -> dict:
    combinations = []
    if match_id:
        combinations.append({"index": 1, "legs": [{"match": {"id": str(match_id)},
                                                    "selection": {"selection_id": "total_goals:under@3.5", "probability": 0.8},
                                                    "why": {"rank": 2, "forecast": {"snapshot_id": "snap-1"}}}]})
    pool_excluded = {"no_forecast": 0, "stale": 0, "kickoff_passed": 0, "below_threshold": 0}
    pool_excluded.update(excluded or {})
    return {"generated_at": "2026-10-07T01:07:57.160684Z", "combinations": combinations,
            "pool": {"fixtures_in_window": fixtures_in_window, "qualifying": qualifying, "excluded": pool_excluded},
            "shortfall": None}


def answered(body) -> dict:
    return {"ok": True, "status": 200, "body": body}


def test_a_fixture_in_a_suggested_combination_is_proven():
    match = match_row(FUTURE)
    stage = pj.classify_suggestion(match, NOW, answered(suggestions_body(match.id)), None)
    assert stage["verdict"] == "proven"
    assert stage["evidence"]["basis"] == "combination"
    assert stage["evidence"]["rank"] == 2 and stage["evidence"]["selection_id"] == "total_goals:under@3.5"
    assert stage["at"] == "2026-10-07T01:07:57.160684Z"


def test_the_only_fixture_in_the_probe_window_qualifying_is_proven_by_the_pool():
    match = match_row(FUTURE)
    stage = pj.classify_suggestion(match, NOW, answered(suggestions_body()),
                                   answered(suggestions_body(fixtures_in_window=1, qualifying=1)))
    assert stage["verdict"] == "proven"
    assert stage["evidence"]["basis"] == "pool"


def test_the_only_fixture_in_the_probe_window_excluded_names_the_reason():
    stage = pj.classify_suggestion(match_row(FUTURE), NOW, answered(suggestions_body()),
                                   answered(suggestions_body(fixtures_in_window=1, qualifying=0,
                                                             excluded={"no_forecast": 1})))
    assert stage["verdict"] == "excluded:no_forecast"


def test_a_probe_that_does_not_isolate_the_fixture_proves_nothing():
    stage = pj.classify_suggestion(match_row(FUTURE), NOW, answered(suggestions_body()),
                                   answered(suggestions_body(fixtures_in_window=2, qualifying=1,
                                                             excluded={"stale": 1})))
    assert stage["verdict"] == "not_observed"


def test_an_unanswered_suggestions_call_is_not_observed():
    down = {"ok": False, "status": None, "error": "ConnectError"}
    assert pj.classify_suggestion(match_row(FUTURE), NOW, down, down)["verdict"] == "not_observed"


def test_after_kickoff_an_earlier_run_that_saw_it_suggested_proves_it_earlier():
    match = match_row(PAST)
    hits = [{"file": "late.json", "generated_at": pj._iso(PAST + timedelta(minutes=5)), "evidence": {}},
            {"file": "early.json", "generated_at": pj._iso(PAST - timedelta(hours=3)), "evidence": {"rank": 1}}]
    stage = pj.classify_suggestion(match, NOW, previous_hits=hits)
    assert stage["verdict"] == "proven_earlier"
    assert stage["evidence"]["file"] == "early.json"


def test_after_kickoff_a_suggestion_seen_only_after_kickoff_does_not_count():
    hits = [{"file": "late.json", "generated_at": pj._iso(PAST + timedelta(minutes=5)), "evidence": {}}]
    assert pj.classify_suggestion(match_row(PAST), NOW, previous_hits=hits)["verdict"] == "not_observed"


def test_after_kickoff_a_prematch_slip_leg_is_selection_evidence_not_a_suggestion():
    leg = leg_row("match_result", "home", created=PAST - timedelta(hours=10))
    stage = pj.classify_suggestion(match_row(PAST), NOW, legs=[leg])
    assert stage["verdict"] == "selection_evidence"
    assert "not the suggestion service" in stage["evidence"]["detail"]


@pytest.mark.parametrize("leg", [
    leg_row("match_result", "home", created=PAST + timedelta(minutes=1)),            # added after kickoff
    leg_row("match_result", "home", created=PAST - timedelta(hours=1), snapshot=False),  # no snapshot
    leg_row("total_goals", "over", 2.5, created=PAST - timedelta(hours=1), source="calculated"),
])
def test_a_leg_that_does_not_show_a_prematch_provider_selection_is_not_evidence(leg):
    assert pj.classify_suggestion(match_row(PAST), NOW, legs=[leg])["verdict"] == "not_observed"


# ====================================================================== stage 4: stored_result
def test_a_finished_fixture_with_a_result_is_proven_and_current_only_after_the_outage():
    match = match_row(PAST, status=MatchStatus.FINISHED)
    old = pj.classify_stored_result(match, result_row(1, 0, SINCE - timedelta(hours=1)), NOW, BLOCKED, SINCE)
    new = pj.classify_stored_result(match, result_row(1, 0, PAST + timedelta(hours=3)), NOW, BLOCKED, SINCE)
    assert old["verdict"] == "proven"
    assert new["verdict"] == "proven_current"
    assert new["evidence"]["result"]["regulation"] == [1, 0]


def test_a_fixture_still_to_kick_off_waits_for_kickoff():
    assert pj.classify_stored_result(match_row(FUTURE), None, NOW, BLOCKED, SINCE)["verdict"] == "pending: waiting for kickoff"


def test_a_fixture_inside_its_result_window_is_pending_even_while_blocked():
    match = match_row(NOW - timedelta(minutes=30), status=MatchStatus.LIVE)
    assert pj.classify_stored_result(match, None, NOW, BLOCKED, SINCE)["verdict"] == "pending: inside result window"


def test_no_result_while_no_source_answers_is_blocked_never_failed():
    stage = pj.classify_stored_result(match_row(PAST), None, NOW, BLOCKED, SINCE)
    assert stage["verdict"] == "blocked: no match-data source answering"
    partial = pj.classify_stored_result(match_row(PAST), None, NOW, PARTIAL, SINCE)
    assert partial["verdict"] == "blocked: match-data access partial"
    assert partial["evidence"]["missing"] == ["primary_provider_answering"]


def test_a_row_still_reading_live_long_after_kickoff_is_flagged_stale():
    stage = pj.classify_stored_result(match_row(PAST, status=MatchStatus.LIVE), None, NOW, BLOCKED, SINCE)
    assert stage["evidence"]["status_stale"] is True


def test_once_access_returned_an_unasked_fixture_waits_in_the_recovery_queue():
    match = match_row(PAST, recovery={"last_outcome": "deferred", "next_ask_after": pj._iso(NOW + timedelta(hours=1))})
    stage = pj.classify_stored_result(match, None, NOW, returned(NOW - timedelta(hours=2)), SINCE)
    assert stage["verdict"] == "pending: recovery queue"
    assert stage["evidence"]["next_ask_after"] == pj._iso(NOW + timedelta(hours=1))


def test_asked_after_access_returned_and_stopped_by_the_retry_budget_is_failed():
    back = NOW - timedelta(days=1)
    match = match_row(NOW - timedelta(days=15), recovery={
        "attempts": 3, "last_attempt_at": pj._iso(back + timedelta(hours=2)),
        "gave_up_at": pj._iso(back + timedelta(hours=2)), "stopped_by": "retry_budget"})
    assert pj.classify_stored_result(match, None, NOW, returned(back), SINCE)["verdict"] == "failed"


def test_a_stop_made_before_access_returned_is_not_called_failed():
    back = NOW - timedelta(hours=3)
    match = match_row(NOW - timedelta(days=15), recovery={
        "attempts": 5, "last_attempt_at": pj._iso(back - timedelta(days=1)),
        "gave_up_at": pj._iso(back - timedelta(days=1)), "stopped_by": "retry_budget"})
    stage = pj.classify_stored_result(match, None, NOW, returned(back), SINCE)
    assert stage["verdict"] == "unresolved: stopped before access returned"


def test_a_cancelled_fixture_needs_no_score():
    stage = pj.classify_stored_result(match_row(PAST, status=MatchStatus.CANCELLED), None, NOW, BLOCKED, SINCE)
    assert stage["verdict"] == "proven"
    assert stage["evidence"]["basis"] == "fixture_status"


def test_a_finished_fixture_without_a_result_row_is_unresolved():
    stage = pj.classify_stored_result(match_row(PAST, status=MatchStatus.FINISHED), None, NOW, BLOCKED, SINCE)
    assert stage["verdict"] == "unresolved: finished without a stored result"


def test_attempts_counted_after_the_outage_began_are_flagged_unreliable():
    match = match_row(PAST, recovery={"attempts": 4, "first_attempt_at": "2026-10-05T04:24:00+00:00",
                                      "last_attempt_at": "2026-10-05T04:24:00+00:00"})
    stage = pj.classify_stored_result(match, None, NOW, BLOCKED, SINCE)
    flagged = stage["evidence"]["attempt_counts_unreliable"]
    assert flagged["attempts"] == 4 and flagged["why"]
    fixture = pj.prove_fixture(match, label="A v B", competition=None, now=NOW, since=SINCE, access=BLOCKED)
    assert fixture["flags"]["attempt_counts_unreliable"] is True


@pytest.mark.parametrize("recovery,flagged", [
    ({"attempts": 2, "last_attempt_at": "2026-10-01T10:00:00+00:00"}, False),
    ({"attempts": 2, "last_attempt_at": "2026-10-05T04:24:00+00:00"}, True),
    # scripts/repair_not_answers.py marks what it sorted out: its mark, not the clock, then decides.
    ({"attempts": 2, "last_attempt_at": "2026-10-05T04:24:00+00:00", "attempts_quality": "exact",
      "attempts_quality_as_of": "2026-10-07T03:00:00+00:00"}, False),
    ({"attempts": 2, "last_attempt_at": "2026-10-01T10:00:00+00:00", "attempts_quality": "upper_bound"}, True),
    ({"attempts": 2, "last_attempt_at": "2026-10-01T10:00:00+00:00", "attempts_quality": "unverified"}, True),
])
def test_a_repaired_record_is_trusted_only_when_it_calls_its_count_exact(recovery, flagged):
    assert (pj.attempt_counts_unreliable(recovery, SINCE) is not None) is flagged


def test_a_bounded_count_carries_the_repairs_own_account_of_it():
    flagged = pj.attempt_counts_unreliable({"attempts": 29, "attempts_quality": "upper_bound", "attempts_at_correction": 18,
                                            "attempts_quality_as_of": "2026-10-07T03:00:00+00:00"}, SINCE)
    assert (flagged["attempts_quality"], flagged["attempts_at_correction"]) == ("upper_bound", 18)
    assert flagged["attempts_quality_as_of"] == "2026-10-07T03:00:00+00:00"


# ========================================================================= stage 5: settlement
FINISHED_2_1 = result_row(2, 1, PAST + timedelta(hours=3), ht=(1, 0))


@pytest.mark.parametrize("leg,expected", [
    (leg_row("match_result", "home", state="won", settled=PAST + timedelta(hours=4)), "proven"),
    (leg_row("match_result", "home"), "pending: owner read"),
    (leg_row("match_result", "away", state="won", settled=PAST + timedelta(hours=4)), "failed"),
    (leg_row("total_goals", "over", 2.5), "pending: owner read"),
    (leg_row("team_to_score_first", "home"), "unresolved:event_order"),
])
def test_a_slip_leg_is_judged_against_a_dry_run_of_the_rule(leg, expected):
    match = match_row(PAST, status=MatchStatus.FINISHED)
    stage = pj.classify_settlement(match, FINISHED_2_1, [leg], [], True)
    assert stage["verdict"] == expected
    assert stage["evidence"]["basis"] == "slip_legs"


def test_a_leg_on_a_fixture_with_no_result_is_pending():
    stage = pj.classify_settlement(match_row(PAST), None, [leg_row("match_result", "home")], [], True)
    assert stage["verdict"] == "pending"
    assert stage["evidence"]["legs"][0]["dry_run"]["state"] == "pending"


def test_a_first_half_leg_with_no_half_time_score_is_unresolved_not_guessed():
    match = match_row(PAST, status=MatchStatus.FINISHED)
    stage = pj.classify_settlement(match, result_row(2, 1, PAST + timedelta(hours=3)),
                                   [leg_row("first_half_result", "home")], [], True)
    assert stage["verdict"] == "unresolved:half_time"


def test_several_legs_read_as_the_worst_of_them():
    match = match_row(PAST, status=MatchStatus.FINISHED)
    legs = [leg_row("match_result", "home", state="won", settled=PAST + timedelta(hours=4)),
            leg_row("match_result", "away", state="won", settled=PAST + timedelta(hours=4)),
            leg_row("total_goals", "over", 0.5)]
    assert pj.classify_settlement(match, FINISHED_2_1, legs, [], True)["verdict"] == "failed"


@pytest.mark.parametrize("result,scores,prematch,expected", [
    (FINISHED_2_1, [score_row(PAST + timedelta(hours=4))], True, "proven"),
    (FINISHED_2_1, [], True, "pending: forecast scoring"),
    (None, [], True, "pending"),
    (FINISHED_2_1, [], False, "not_applicable"),
])
def test_a_fixture_in_no_slip_is_judged_by_its_forecast_scoring(result, scores, prematch, expected):
    status = MatchStatus.FINISHED if result else MatchStatus.SCHEDULED
    assert pj.classify_settlement(match_row(PAST, status=status), result, [], scores, prematch)["verdict"] == expected


def test_the_dry_run_never_writes_a_leg(monkeypatch):
    """settle_leg and settle_slip assign onto the ORM row; only the pure rule may be used."""
    def refuse(*args, **kwargs):
        raise AssertionError("the proof applied a settlement function that writes")

    monkeypatch.setattr(slip_settlement, "settle_leg", refuse)
    monkeypatch.setattr(slip_settlement, "settle_slip", refuse)
    leg = leg_row("match_result", "home")
    pj.classify_settlement(match_row(PAST, status=MatchStatus.FINISHED), FINISHED_2_1, [leg], [], True)
    assert leg.state == "pending" and leg.settled_at is None and leg.settlement is None
    with open(pj.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "settle_leg(" not in source and "settle_slip(" not in source


# ======================================================================= chain and slip
def stages_with(**verdicts) -> dict:
    stages = {name: {"verdict": "proven"} for name in pj.STAGES}
    stages.update({name: {"verdict": verdict} for name, verdict in verdicts.items()})
    return stages


def test_the_chain_stops_at_the_first_stage_that_does_not_pass():
    chain = pj.chain_verdict(stages_with(forecast_attached="absent", stored_result="blocked: x"))
    assert chain == {"verdict": "absent", "stage": "forecast_attached", "passed_with": [],
                     "later": ["stored_result: blocked: x"]}


def test_selection_evidence_lets_the_chain_through_and_is_named():
    chain = pj.chain_verdict(stages_with(suggestion="selection_evidence",
                                         stored_result="blocked: no match-data source answering"))
    assert chain["stage"] == "stored_result"
    assert chain["passed_with"] == ["suggestion: selection_evidence"]


def test_a_chain_of_proven_stages_is_proven():
    chain = pj.chain_verdict(stages_with(fixture_stored="proven_current", suggestion="proven_earlier",
                                         stored_result="proven_current"))
    assert chain == {"verdict": "proven", "stage": None, "passed_with": [], "later": []}


def slip_row(state="pending") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="Journey 2026-10-05T06:08", status="recorded", state=state,
                           settled_at=None, created_at=naive(PAST - timedelta(hours=10)),
                           recorded_at=naive(PAST - timedelta(hours=10)), price=None)


def slip_legs(match_a, match_b, states=("pending", "pending")):
    first = leg_row("match_result", "home", state=states[0])
    second = leg_row("total_goals", "over", 0.5, state=states[1])
    first.match_id, second.match_id = match_a.id, match_b.id
    return [first, second]


def test_a_slip_whose_dry_run_is_final_but_stored_pending_waits_for_its_owner():
    a, b = match_row(PAST, status=MatchStatus.FINISHED), match_row(PAST, status=MatchStatus.FINISHED)
    results = {a.id: result_row(0, 0, PAST), b.id: result_row(1, 2, PAST)}
    slip = pj.classify_slip(slip_row(), slip_legs(a, b), {a.id: a, b.id: b}, results, True)
    assert slip["dry_run_state"] == "lost"
    assert slip["verdict"] == "pending: owner read"
    assert slip["name"] == "Journey 2026-10-05T06:08"


def test_a_slip_stored_final_and_agreeing_is_proven_and_a_non_qa_name_is_withheld():
    a, b = match_row(PAST, status=MatchStatus.FINISHED), match_row(PAST, status=MatchStatus.FINISHED)
    results = {a.id: result_row(2, 0, PAST), b.id: result_row(1, 2, PAST)}
    slip = pj.classify_slip(slip_row("won"), slip_legs(a, b, ("won", "won")), {a.id: a, b.id: b}, results, False)
    assert slip["verdict"] == "proven"
    assert slip["name"] is None and slip["owner_is_qa"] is False


def test_a_slip_stored_final_against_the_rule_is_failed():
    a, b = match_row(PAST, status=MatchStatus.FINISHED), match_row(PAST, status=MatchStatus.FINISHED)
    results = {a.id: result_row(0, 1, PAST), b.id: result_row(1, 2, PAST)}
    slip = pj.classify_slip(slip_row("won"), slip_legs(a, b, ("won", "won")), {a.id: a, b.id: b}, results, True)
    assert slip["verdict"] == "failed"


# ===================================================================== access detector
def detect(status=None, stored=None):
    return pj.detect_match_data_access(pj.status_view_from_api(status or measured_status()),
                                       stored or MEASURED_STORED, SINCE)


def test_today_is_blocked_with_every_provider_error_quoted():
    access = detect()
    assert access["verdict"] == "blocked"
    assert access["missing"] == ["primary_provider_answering", "scheduler_fixtures_or_results_succeeding",
                                 "stored_match_data_advancing"]
    errors = {p["name"]: p["last_error"] for p in access["providers"]}
    assert errors["livescore"] == LIVESCORE_401 and errors["api_football"] == API_FOOTBALL_PLAN
    assert access["returned_no_later_than"] is None


def test_a_fallbacks_http_200_and_moved_success_are_ignored():
    """API-Football answered 200 - with a plan error - and its last_success_at moved on 10-06."""
    access = detect()
    assert access["verdict"] == "blocked"
    ignored = {entry["signal"]: entry for entry in access["ignored_signals"]}
    football = ignored["api_football: last transmission status and last_success_at"]
    assert football["value"]["transmitted_last_status"] == 200
    assert football["last_error"] == API_FOOTBALL_PLAN


def test_a_recovery_pass_that_sent_nothing_and_bumped_rows_does_not_read_as_recovery():
    status = measured_status()
    status["scheduler"]["tasks"]["recover"]["last_success_at"] = "2026-10-07T01:30:00+00:00"
    stored = dict(MEASURED_STORED, newest_match_updated_at="2026-10-07T01:30:00Z")
    access = detect(status, stored)
    assert access["verdict"] == "blocked"
    ignored = {entry["signal"]: entry for entry in access["ignored_signals"]}
    assert ignored["scheduler.tasks.recover.last_success_at"]["last_requests"] == 0
    assert ignored["matches.updated_at"]["value"] == "2026-10-07T01:30:00Z"


def signal(access: dict, name: str) -> dict:
    return next(s for s in access["signals"] if s["signal"] == name)


#: The day the verifier named: the only fixtures stored after 2026-10-07 kick off on 10-09 at
#: 18:30-19:00, results look back one day and a fixture is pending only 150 minutes after kickoff,
#: so every results pass that day until about 21:00 has nothing due - and succeeds.
QUIET_PASS_AT = "2026-10-09T00:30:00+00:00"


def task_succeeded(task: str, **state) -> dict:
    """The measured status, with one task's last pass a success at QUIET_PASS_AT and `state` on it.
    Nothing else changes: Live Score still refuses and nothing has been stored."""
    status = measured_status()
    status["scheduler"]["tasks"][task].update(last_run_at=QUIET_PASS_AT, last_success_at=QUIET_PASS_AT,
                                              consecutive_failures=0, last_error=None, **state)
    return status


@pytest.mark.parametrize("last_result, sent", [
    # `_run_results` with no competition due: no call, no error, ok=True - and `_record` writes the
    # success. This is the 10-09 pass.
    ({"days": {"2026-10-09": {"source": "database", "competitions": 0}}, "errors": [], "requests": 0,
      "deferred": []}, {}),
    # Answered from the fresh cache: `requests` counts the competitions put to the chain, and none
    # of it left.
    ({"errors": [], "requests": 2}, {}),
    # Live Score holds no id for the competition, so it was passed over unasked and a fallback
    # answered: nothing about the primary was learned.
    ({"errors": [], "requests": 1}, {"api_football": 1}),
    # A build that did not record what its pass sent: unknown is not "asked".
    ({"errors": [], "requests": 0}, None),
], ids=["nothing_due", "fresh_cache", "fallback_only", "not_recorded"])
def test_a_results_success_that_never_asked_the_primary_is_not_access(last_result, sent):
    access = detect(task_succeeded("results", last_result=last_result, last_requests_sent=sent))
    assert access["verdict"] == "blocked"
    scheduler = signal(access, "scheduler_fixtures_or_results_succeeding")
    assert scheduler["holds"] is False
    assert scheduler["evidence"]["results"]["counts"] is False
    assert scheduler["evidence"]["results"]["last_requests_sent"] == sent
    ignored = {entry["signal"]: entry for entry in access["ignored_signals"]}
    entry = ignored["scheduler.tasks.results.last_success_at"]
    assert entry["value"] == QUIET_PASS_AT and "livescore" in entry["why_ignored"]


def test_a_results_success_that_asked_the_primary_holds():
    """A results pass succeeds only with no error, and a request to the primary that went out and
    got no answer records one - so a success that sent the primary a request was answered by it."""
    access = detect(task_succeeded("results", last_result={"errors": [], "requests": 1},
                                   last_requests_sent={"livescore": 1}))
    scheduler = signal(access, "scheduler_fixtures_or_results_succeeding")
    assert scheduler["holds"] is True and scheduler["evidence"]["results"]["counts"] is True
    assert access["verdict"] == "partial"
    assert access["missing"] == ["primary_provider_answering", "stored_match_data_advancing"]
    assert "scheduler.tasks.results.last_success_at" not in {e["signal"] for e in access["ignored_signals"]}


def fixtures_pass(*forward_sources) -> dict:
    """A fixtures pass's `last_result`: one day per forward source, counted as the task counts them."""
    days = {f"2026-10-{9 + i:02d}": {"source": "database" if s is None else s, "forward_source": s}
            for i, s in enumerate(forward_sources)}
    return {"days": days,
            "days_answered": sum(s in ("provider", "cache") for s in forward_sources),
            "days_from_stale_cache": sum(s == "stale-cache" for s in forward_sources),
            "days_unanswered": sum(s is None for s in forward_sources)}


@pytest.mark.parametrize("forward_sources, sent", [
    # Live Score was asked and refused; the 24-hour stale copy made the day "data" (`got_data`
    # is any source but the database), so the pass succeeded.
    (("stale-cache", None, None), {"livescore": 2, "api_football": 1}),
    # Every day a fresh cache hit: answered by somebody within the TTL, by nobody in this pass.
    (("cache", "cache", "cache"), {"livescore": 1}),
    # Answered, but the primary was never asked (cooling down, or holding no id for it).
    (("provider", None, None), {"api_football": 1}),
    (("provider", None, None), None),
], ids=["stale_cache", "fresh_cache_only", "primary_not_asked", "not_recorded"])
def test_a_fixtures_success_without_an_answer_after_asking_the_primary_is_not_access(forward_sources, sent):
    access = detect(task_succeeded("fixtures", last_result=fixtures_pass(*forward_sources), last_requests_sent=sent))
    assert access["verdict"] == "blocked"
    scheduler = signal(access, "scheduler_fixtures_or_results_succeeding")
    assert scheduler["holds"] is False and scheduler["evidence"]["fixtures"]["counts"] is False
    ignored = {entry["signal"]: entry for entry in access["ignored_signals"]}
    assert ignored["scheduler.tasks.fixtures.last_success_at"]["value"] == QUIET_PASS_AT


def test_a_fixtures_success_answered_in_the_pass_after_asking_the_primary_holds():
    access = detect(task_succeeded("fixtures", last_result=fixtures_pass("provider", "stale-cache", None),
                                   last_requests_sent={"livescore": 3}))
    scheduler = signal(access, "scheduler_fixtures_or_results_succeeding")
    assert scheduler["holds"] is True
    assert scheduler["evidence"]["fixtures"]["days_from_provider"] == 1
    assert scheduler["evidence"]["fixtures"]["days_from_stale_cache"] == 1


def test_a_quiet_pass_beside_a_fallback_stored_fixture_is_one_signal_not_two():
    """The 10-09 pass with nothing due, and a fixture a fallback stored. The stored row is real;
    the pass is not, so `missing` still names the scheduler - a reader told "only the primary is
    missing" would wait for the wrong thing."""
    status = task_succeeded("results", last_result={"errors": [], "requests": 0}, last_requests_sent={})
    stored = dict(MEASURED_STORED, newest_last_synced_at="2026-10-09T00:10:00Z",
                  first_last_synced_after_since="2026-10-09T00:10:00Z")
    access = detect(status, stored)
    assert access["verdict"] == "partial"
    assert access["missing"] == ["primary_provider_answering", "scheduler_fixtures_or_results_succeeding"]


def returned_status() -> dict:
    status = measured_status()
    livescore = status["chain"][0]
    livescore.update(last_success_at="2026-10-08T09:00:00+00:00", cooling_down=None, last_error=None)
    livescore["budget"]["transmitted_today"]["last_status"] = 200
    status["scheduler"]["tasks"]["results"].update(
        last_run_at="2026-10-08T09:00:00+00:00", last_success_at="2026-10-08T09:00:00+00:00",
        consecutive_failures=0, last_error=None, last_requests_sent={"livescore": 2},
        last_result={"errors": [], "requests": 2})
    return status


RETURNED_STORED = dict(MEASURED_STORED, newest_result_created_at="2026-10-08T09:00:05Z",
                       first_result_created_after_since="2026-10-08T08:30:05Z",
                       first_last_synced_after_since="2026-10-08T08:30:01Z")


def test_all_three_signals_after_the_outage_read_as_returned():
    access = detect(returned_status(), RETURNED_STORED)
    assert access["verdict"] == "returned"
    assert access["missing"] == []
    # It cannot have come back later than the first row it delivered.
    assert access["returned_no_later_than"] == "2026-10-08T08:30:01Z"


def test_two_signals_of_three_are_partial_and_name_the_missing_one():
    access = detect(returned_status(), MEASURED_STORED)
    assert access["verdict"] == "partial"
    assert access["missing"] == ["stored_match_data_advancing"]


def test_the_apps_own_match_data_state_is_recorded_and_never_decides():
    """The backend's reader-facing state is kept beside the verdict, so a banner that disagrees
    with the evidence shows up in the proof - but it is a claim being checked, not a signal."""
    status = measured_status()
    status["match_data"] = {"state": "ok"}
    access = detect(status)
    assert access["verdict"] == "blocked"
    assert access["app_reports"] == {"state": "ok"}
    assert detect()["app_reports"] is None


def test_a_primary_that_answered_200_but_is_cooling_down_is_not_answering():
    status = returned_status()
    status["chain"][0]["cooling_down"] = "livescore: HTTP 429"
    assert detect(status, RETURNED_STORED)["missing"] == ["primary_provider_answering"]


def test_the_redis_view_reads_the_same_keys_the_backend_writes():
    store, budgets = FakeRedis(), FakeRedis()
    store.set("provider:status:livescore", json.dumps({"last_success_at": "2026-10-02T14:53:28.028159+00:00",
                                                       "last_error": LIVESCORE_401}))
    store.set("provider:cooldown:livescore", json.dumps({"reason": LIVESCORE_401}))
    store.set("sync:task:results", json.dumps({"last_success_at": "2026-10-02T14:53:28+00:00",
                                               "consecutive_failures": 19}))
    budgets.hset(transmitted_key("livescore", NOW), "answered", 2)
    budgets.hset(transmitted_key("livescore", NOW), "last_status", "401")
    view = pj.status_view_from_redis(pj.ReadOnlyRedis(store), pj.ReadOnlyRedis(budgets), NOW, "livescore",
                                     ["api_football"], "gameforecast")
    livescore = view["chain"][0]
    assert livescore["cooling_down"] == LIVESCORE_401
    assert livescore["transmitted_today"]["last_status"] == 401
    assert view["tasks"]["results"]["consecutive_failures"] == 19
    assert pj.detect_match_data_access(view, MEASURED_STORED, SINCE)["verdict"] == "blocked"


def test_the_redis_view_carries_what_each_pass_sent():
    """Read from the task's own state key, the quiet pass is judged exactly as through the API."""
    store, budgets = FakeRedis(), FakeRedis()
    store.set("sync:task:results", json.dumps({"last_run_at": QUIET_PASS_AT, "last_success_at": QUIET_PASS_AT,
                                               "consecutive_failures": 0, "last_requests_sent": {},
                                               "last_result": {"errors": [], "requests": 0}}))
    view = pj.status_view_from_redis(pj.ReadOnlyRedis(store), pj.ReadOnlyRedis(budgets), NOW, "livescore",
                                     ["api_football"], "gameforecast")
    assert view["tasks"]["results"]["last_requests_sent"] == {}
    access = pj.detect_match_data_access(view, MEASURED_STORED, SINCE)
    assert signal(access, "scheduler_fixtures_or_results_succeeding")["holds"] is False
    assert access["verdict"] == "blocked"


# ======================================================================== GuardedClient
MATCH_ID = "1dabe788-3629-4b89-ab33-435c5846e7de"


def guarded():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    return pj.GuardedClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler)), calls


@pytest.mark.parametrize("path,params", [
    ("/health", None),
    ("/api/v1/data-providers/status", None),
    ("/api/v1/suggestions", {"legs": 2, "min_probability": 0, "from": "2026-10-07T01:59:59Z"}),
    (f"/api/v1/matches/{MATCH_ID}", None),
    (f"/api/v1/matches/{MATCH_ID}/markets", None),
])
def test_only_the_allowlisted_gets_are_sent(path, params):
    client, calls = guarded()
    response = client.get(path, params=params)
    assert response["ok"] and response["body"] == {"ok": True}
    assert [(c.method, c.url.path) for c in calls] == [("GET", path)]


@pytest.mark.parametrize("method,path,params", [
    ("GET", "/api/v1/matches", None),                          # refresh defaults to true
    ("GET", "/api/v1/matches/", None),
    ("GET", "/api/v1/matches", {"refresh": "false"}),          # never a list, even unrefreshed
    ("GET", "/api/v1/matches/live", None),                     # polls the provider
    ("GET", "/api/v1/matches/upcoming", None),
    ("GET", "/api/v1/me/slips", None),                         # settles and commits
    ("GET", f"/api/v1/me/slips/{MATCH_ID}", None),
    ("GET", f"/api/v1/matches/{MATCH_ID}", {"refresh": "true"}),
    ("GET", "/api/v1/suggestions", {"refresh": "false"}),
    ("GET", f"/api/v1/matches/{MATCH_ID}/markets/", None),
    ("GET", "/api/v1/leagues/premier_league/standings", None),
    ("GET", "/api/v1/data-providers/sync", None),
    ("POST", "/api/v1/data-providers/sync", None),
    ("POST", "/health", None),
    ("DELETE", f"/api/v1/matches/{MATCH_ID}", None),
    ("PUT", "/api/v1/suggestions", None),
])
def test_everything_else_is_refused_before_it_is_sent(method, path, params):
    client, calls = guarded()
    with pytest.raises(pj.RefusedRequest):
        client.request(method, path, params=params)
    assert calls == []
    assert client.refused


@pytest.mark.parametrize("send", [
    lambda raw: raw.post("/health"),
    lambda raw: raw.get("/api/v1/matches"),
    lambda raw: raw.get("/api/v1/me/slips"),
    lambda raw: raw.get(f"/api/v1/matches/{MATCH_ID}?refresh=true"),
])
def test_the_hook_refuses_a_call_made_around_the_guard(send):
    """The second check runs on the request the client is about to send, whoever built it."""
    client, calls = guarded()
    with pytest.raises(pj.RefusedRequest):
        send(client._client)
    assert calls == []


@pytest.mark.parametrize("url", [
    f"https://livescore-api.com/api/v1/matches/{MATCH_ID}",    # an allowlisted path on another host
    "http://127.0.0.1:9999/health",                            # the right host, another port
    "https://127.0.0.1:8000/health",                           # the right host and port, another scheme
])
def test_an_allowlisted_path_on_another_origin_is_refused(url):
    """The allowlist names this backend's paths; the same path elsewhere could be anything."""
    client, calls = guarded()
    with pytest.raises(pj.RefusedRequest):
        client.get(url)
    with pytest.raises(pj.RefusedRequest):
        client._client.get(url)
    assert calls == []


@pytest.mark.parametrize("base", ["https://livescore-api.com", "http://10.0.0.5:8000", "http://example.com"])
def test_the_tool_reads_a_backend_on_this_machine_only(base):
    with pytest.raises(pj.RefusedRequest):
        pj.GuardedClient(base, transport=httpx.MockTransport(lambda request: httpx.Response(200)))


def test_the_default_cut_comes_after_the_last_success_it_is_measured_from():
    """Live Score's last success, and the results pass 0.3 s after it, precede the outage."""
    since = pj._instant(pj.DEFAULT_ACCESS_SINCE)
    for before in ("2026-10-02T14:53:28.028159+00:00", "2026-10-02T14:53:28.332818+00:00"):
        assert pj._instant(before) < since


def test_an_unreachable_backend_is_an_answer_not_a_crash():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = pj.GuardedClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
    response = client.get("/health")
    assert response["ok"] is False and response["status"] is None and "ConnectError" in response["error"]


# ======================================================================== ReadOnlyRedis
@pytest.mark.parametrize("command,args", [
    ("set", ("k", "v")), ("setex", ("k", 10, "v")), ("hset", ("h", "f", 1)), ("hincrby", ("h", "f", 1)),
    ("incrby", ("k", 1)), ("expire", ("k", 10)), ("delete", ("k",)), ("pipeline", ()), ("eval", ("return 1", 0)),
    ("execute_command", ("SET", "k", "v")), ("flushdb", ()),
])
def test_read_only_redis_refuses_every_write(command, args):
    fake = FakeRedis()
    fake.set("k", "kept")
    store = pj.ReadOnlyRedis(fake)
    with pytest.raises(pj.RefusedWrite):
        getattr(store, command)(*args)
    assert fake.store == {"k": "kept"}
    assert store.refused == [command]


def test_read_only_redis_reads_and_refuses_a_write_queued_in_a_transaction():
    fake = FakeRedis()
    fake.set("k", "v")
    fake.hset("h", "f", "1")
    store = pj.ReadOnlyRedis(fake)
    assert store.get("k") == "v" and store.hgetall("h") == {"f": "1"}
    assert store.read_together([("get", "k"), ("hgetall", "h")]) == ["v", {"f": "1"}]
    with pytest.raises(pj.RefusedWrite):
        store.read_together([("get", "k"), ("set", "k")])


def test_the_redis_spend_reading_parses_the_counters_as_the_budget_module_does():
    fake = FakeRedis()
    fake.set(budget_key("livescore", NOW), "7")
    for outcome, count in (("answered", 5), ("no_answer", 1), ("not_connected", 1)):
        fake.hincrby(transmitted_key("livescore", NOW), outcome, count)
    fake.hset(transmitted_key("livescore", NOW), "last_status", "401")
    fake.hincrby(SCHEDULER_SENT_KEY, "livescore:live", 4)
    fake.hincrby(SCHEDULER_SENT_KEY, "livescore:recover", 2)
    fake.hincrby(SCHEDULER_SENT_KEY, "gameforecast:forecasts", 9)
    reading = pj.spend_from_redis(pj.ReadOnlyRedis(fake), ["livescore", "gameforecast"], NOW)
    record = read_transmitted("livescore", fake, NOW)
    assert reading["livescore"]["transmitted"] == record["answered"] + record["no_answer"] + record["not_connected"] == 7
    assert reading["livescore"]["scheduler_sent"] == sum(read_scheduler_sent(fake)["livescore"].values()) == 6
    assert reading["livescore"]["used_today"] == 7
    assert reading["gameforecast"] == {"used_today": 0, "scheduler_sent": 9, "transmitted": 0}


# ========================================================================== spend check
def reading(used, sent, transmitted=0):
    return {"livescore": {"used_today": used, "scheduler_sent": sent, "transmitted": transmitted}}


def test_requests_the_scheduler_sent_during_the_run_are_not_charged_to_it():
    check = pj.compare_spend(reading(10, 100, 10), reading(12, 102, 12))
    assert check["verdict"] == "passed"
    assert check["providers"]["livescore"]["spent_besides_scheduler"] == 0


def test_a_request_the_scheduler_did_not_send_fails_the_check():
    check = pj.compare_spend(reading(10, 100), reading(11, 100))
    assert check["verdict"] == "failed"
    assert pj._overall_spend(check, {"verdict": "passed"}) == "failed"


def test_a_day_turning_over_inside_the_run_measures_nothing():
    check = pj.compare_spend(reading(1200, 100), reading(0, 100))
    assert check["verdict"] == "unknown" and "turned over" in check["problems"][0]


# ============================================================================ redaction
def all_keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from all_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from all_keys(inner)


FORBIDDEN = {"email", "user_id", "recorded_reference", "note", "token", "key", "secret"}


def test_redaction_drops_personal_and_credential_keys_and_scrubs_values(monkeypatch):
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "fake-livescore-key-0123456789")
    document = {
        "slip": {"id": "s1", "user_id": "u1", "email": "someone@example.test", "note": "private",
                 "recorded_reference": "BET-1", "legs": [{"token": "t", "key": "k", "secret": "s", "state": "pending"}]},
        "provider_api_key": "x", "Password": "y",
        "errors": ["GET https://api.example.test/v1?key=abc123&x=1 failed",
                   "rejected fake-livescore-key-0123456789 for qa.expert@predictions-local.dev",
                   f"path {os.path.expanduser('~')}/project"],
    }
    clean = pj.redact(document, pj.credential_values())
    assert not FORBIDDEN & set(all_keys(clean))
    assert "provider_api_key" not in clean and "Password" not in clean
    assert clean["slip"]["legs"] == [{"state": "pending"}]
    rendered = json.dumps(clean)
    assert "abc123" not in rendered and "fake-livescore-key" not in rendered and "@" not in rendered
    assert os.path.expanduser("~") not in rendered


# ========================================================================= run metadata
REPO = {"head": "201442e", "head_moved_at": "2026-10-05T23:00:19Z", "app_tree_changes": []}
PROCESS = {"started_at": "2026-10-07T01:02:40Z", "app_files_modified_after_start": []}


def test_a_backend_started_after_head_on_a_clean_tree_serves_head():
    assert pj.running_code(REPO, PROCESS)["includes_head"] is True


def test_files_other_sessions_changed_after_the_start_were_not_loaded():
    repo = dict(REPO, app_tree_changes=["backend/app/services/slips.py", "backend/app/services/new_module.py"])
    process = dict(PROCESS, app_files_modified_after_start=["backend/app/services/new_module.py",
                                                            "backend/app/services/slips.py"])
    verdict = pj.running_code(repo, process)
    assert verdict["includes_head"] is True and "cannot be ruled out" in verdict["detail"]


def test_a_file_changed_before_the_start_leaves_the_question_open():
    repo = dict(REPO, app_tree_changes=["backend/app/services/slips.py"])
    verdict = pj.running_code(repo, PROCESS)
    assert verdict["includes_head"] is None and "slips.py" in verdict["detail"]


def test_a_porcelain_status_keeps_the_first_files_leading_column():
    """The first line of `git status --porcelain` starts with a space (" M path"); stripping the
    whole output once cut the first path to "ackend/app/...", which no longer matched the same
    file in the modified-after-start list."""
    assert pj._command([sys.executable, "-c", "print(' M backend/app/x.py')"]) == " M backend/app/x.py"


def test_the_repo_state_names_every_changed_application_file(monkeypatch):
    answers = {"rev-parse": "201442e", "show": "2026-10-05T18:58:58-04:00",
               "log": "HEAD@{2026-10-05T19:00:19-04:00}",
               "status": ' M backend/app/services/slips.py\n?? backend/app/services/new.py\n'
                         'R  backend/app/old.py -> backend/app/renamed.py'}
    monkeypatch.setattr(pj, "_command", lambda args, cwd=None: next(v for k, v in answers.items() if k in args))
    state = pj.repo_state("/repo")
    assert state["app_tree_changes"] == ["backend/app/renamed.py", "backend/app/services/new.py",
                                         "backend/app/services/slips.py"]
    assert state["head_moved_at"] == "2026-10-05T23:00:19Z" and state["committed_at"] == "2026-10-05T22:58:58Z"


def test_a_backend_started_before_head_arrived_does_not_serve_it():
    """A commit that changed the application after the start moved those files' modification times."""
    process = dict(PROCESS, started_at="2026-10-05T22:00:00Z",
                   app_files_modified_after_start=["backend/app/services/match_data_service.py"])
    assert pj.running_code(REPO, process)["includes_head"] is False


def test_a_commit_of_files_already_loaded_still_serves_head():
    """2026-10-07: the backend restarted at 02:51:55 on edits made by 02:48; they were committed at
    02:59 and later. HEAD arrived after the start, yet nothing under backend/app changed since it."""
    verdict = pj.running_code(dict(REPO, head_moved_at="2026-10-07T04:07:30Z"),
                              dict(PROCESS, started_at="2026-10-07T02:51:55Z"))
    assert verdict["includes_head"] is True and "after the process started" in verdict["detail"]


# ------------------------------------------------------- measured against the backend's own account
TREE = {"main.py": b"app = 1\n", "services/slips.py": b"def settle(): ...\n"}
HEAD_SHA = "e05cf10ceac38f5e7351d3b0bb4132c0c575d076"
OLDER_SHA = "201442e" + "0" * 33


def app_tree(root, files: dict) -> str:
    """<root>/backend/app holding `files`: a checkout's application tree."""
    app = os.path.join(str(root), "backend", "app")
    for relative, content in files.items():
        path = os.path.join(app, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content)
    return app


def health_with(tree: str, commit: str = HEAD_SHA, dirty=()) -> dict:
    """GET /health from a backend that recorded its source identity when it started."""
    return {"status": "healthy", "environment": "development", "version": "0.1.0",
            "started_at": "2026-10-07T22:53:40Z", "database": "soccer_predictions",
            "source": {"commit": commit, "commit_dirty_app_files": list(dirty), "app_tree_sha256": tree,
                       "app_files": len(TREE), "started_at": "2026-10-07T22:53:40Z"}}


def test_the_tools_digest_is_the_backends_own(tmp_path):
    """Reimplemented from the documented algorithm, so it must agree with the backend's over the
    same tree, skip what the backend skips, and read nothing into a tree that is not there."""
    app = app_tree(tmp_path, dict(TREE, **{"__pycache__/main.cpython-311.pyc": b"\x00", "notes.txt": b"n",
                                           "services/__pycache__/stale.py": b"skipped"}))
    assert pj.app_tree_digest(app) == source_identity.app_tree_digest(app)
    assert pj.app_tree_digest(app)[1] == 2
    assert pj.app_tree_digest(os.path.join(str(tmp_path), "missing")) == (None, 0)
    assert pj.app_tree_digest(None) == (None, 0)


def test_a_backend_that_loaded_the_tree_on_disk_at_head_is_measured_to_serve_head(tmp_path):
    app = app_tree(tmp_path, TREE)
    tree, _ = pj.app_tree_digest(app)
    verdict = pj.running_code(dict(REPO, head=HEAD_SHA), {}, health_with(tree), app)
    assert verdict["includes_head"] is True and verdict["basis"] == "measured"
    measured = verdict["measured"]
    assert measured["tree_matches"] is True and measured["commit_matches"] is True
    assert (measured["commit_served"], measured["commit_head"], measured["tree_now"]) == (HEAD_SHA, HEAD_SHA, tree)
    assert measured["dirty_app_files_at_start"] == [] and measured["app_files_now"] == 2


def test_a_tree_that_changed_since_the_start_of_a_clean_checkout_is_not_what_runs(tmp_path):
    """The checkout is clean, so the tree on disk is HEAD's; the process loaded another one."""
    app = app_tree(tmp_path, TREE)
    verdict = pj.running_code(dict(REPO, head=HEAD_SHA), PROCESS, health_with("0" * 64), app)
    assert verdict["includes_head"] is False and verdict["basis"] == "measured"
    assert verdict["measured"]["tree_matches"] is False and "not what the process loaded" in verdict["detail"]


def test_edits_made_after_a_clean_start_on_head_were_not_loaded(tmp_path):
    """The inference's "changed after the start" reasoning, now on the backend's own account: it
    started clean on the commit that is still HEAD, so the tree it loaded was HEAD's whatever has
    been edited since."""
    app = app_tree(tmp_path, TREE)
    tree, _ = pj.app_tree_digest(app)
    with open(os.path.join(app, "services", "slips.py"), "wb") as handle:
        handle.write(b"def settle(): return 1\n")
    repo = dict(REPO, head=HEAD_SHA, app_tree_changes=["backend/app/services/slips.py"])
    verdict = pj.running_code(repo, {}, health_with(tree), app)
    assert verdict["includes_head"] is True and verdict["measured"]["tree_matches"] is False
    assert "changed after the start and not loaded" in verdict["detail"]


def test_a_commit_of_files_already_loaded_is_measured_not_inferred(tmp_path):
    """HEAD moved after the start - a docs-only commit, or one recording files already loaded: the
    tree shows the process serves HEAD's application code, and the commit alone does not decide."""
    app = app_tree(tmp_path, TREE)
    tree, _ = pj.app_tree_digest(app)
    verdict = pj.running_code(dict(REPO, head=HEAD_SHA), {}, health_with(tree, commit=OLDER_SHA), app)
    assert verdict["includes_head"] is True and verdict["measured"]["commit_matches"] is False
    assert "already loaded" in verdict["detail"]


def test_uncommitted_files_the_process_loaded_leave_the_question_open_and_are_named(tmp_path):
    app = app_tree(tmp_path, TREE)
    tree, _ = pj.app_tree_digest(app)
    repo = dict(REPO, head=HEAD_SHA, app_tree_changes=["backend/app/services/slips.py"])
    dirty = ["backend/app/services/slips.py"]
    on_disk = pj.running_code(repo, {}, health_with(tree, dirty=dirty), app)
    assert on_disk["includes_head"] is None and "slips.py" in on_disk["detail"]
    since_changed = pj.running_code(repo, {}, health_with("0" * 64, dirty=dirty), app)
    assert since_changed["includes_head"] is None and "slips.py" in since_changed["detail"]


def test_a_commit_that_is_not_head_with_the_tree_changed_since_cannot_be_judged(tmp_path):
    app = app_tree(tmp_path, TREE)
    repo = dict(REPO, head=HEAD_SHA, app_tree_changes=["backend/app/main.py"])
    verdict = pj.running_code(repo, {}, health_with("0" * 64, commit=OLDER_SHA), app)
    assert verdict["includes_head"] is None and "cannot be told" in verdict["detail"]


def test_a_backend_without_a_source_identity_is_inferred_and_says_so():
    verdict = pj.running_code(REPO, PROCESS, {"status": "healthy"}, "/nowhere")
    assert verdict["basis"] == "inferred" and verdict["includes_head"] is True
    assert "published no source identity" in verdict["detail"] and verdict["measured"] is None
    unread = pj.running_code(REPO, PROCESS)
    assert unread["basis"] == "inferred" and "was not read" in unread["detail"]


def test_a_checkout_that_cannot_be_digested_leaves_the_measurement_unknown(tmp_path):
    verdict = pj.running_code(dict(REPO, head=HEAD_SHA), PROCESS, health_with("0" * 64),
                              os.path.join(str(tmp_path), "missing"))
    assert verdict["includes_head"] is None and verdict["basis"] == "unknown"
    assert verdict["measured"]["tree_now"] is None and "could not be digested" in verdict["detail"]


# ===================================================================== golden: today's state
def todays_journey():
    """Slip "Journey 2026-10-05T06:08" and its two fixtures as stored at 2026-10-07 01:06 UTC."""
    recovery = {"deferrals": 2, "last_outcome": "deferred", "last_outcome_at": "2026-10-07T01:04:46.641460+00:00",
                "next_ask_after": "2026-10-07T01:04:46.641460+00:00", "last_deferred_because": ["our_allowance"],
                "last_outcome_detail": "due an ask, but one pass reopens at most 2 day(s), oldest first; it stays due"}
    cyprus = match_row(datetime(2026, 10, 5, 16, 0, tzinfo=UTC), created=datetime(2026, 9, 28, 0, 4, 55, tzinfo=UTC),
                       synced=datetime(2026, 10, 2, 12, 2, 41, tzinfo=UTC), recovery=recovery,
                       provider="livescore", provider_status="NOT STARTED")
    france = match_row(datetime(2026, 10, 5, 18, 45, tzinfo=UTC), created=datetime(2026, 9, 28, 0, 4, 55, tzinfo=UTC),
                       synced=datetime(2026, 10, 2, 12, 2, 41, tzinfo=UTC), recovery=dict(recovery),
                       provider="livescore", provider_status="NOT STARTED")
    fetched = datetime(2026, 10, 5, 6, 2, 6, tzinfo=UTC)
    added = datetime(2026, 10, 5, 6, 8, 37, tzinfo=UTC)
    home = leg_row("match_result", "home", created=added)
    over = leg_row("total_goals", "over", 0.5, created=added)
    home.match_id, over.match_id = cyprus.id, france.id
    slip = slip_row()
    home.slip_id = over.slip_id = slip.id
    return slip, [(cyprus, "Cyprus v Latvia", home, fetched), (france, "France v Belgium", over, fetched)]


def test_golden_todays_journey_is_blocked_at_the_stored_result_and_its_slip_pending():
    access = pj.detect_match_data_access(pj.status_view_from_api(measured_status()), MEASURED_STORED, SINCE)
    assert access["verdict"] == "blocked"
    slip, fixtures = todays_journey()
    for match, label, leg, fetched in fixtures:
        proof = pj.prove_fixture(match, label=label, competition=None, now=MEASURED_AT, since=SINCE, access=access,
                                 view=pj.status_view_from_api(measured_status()),
                                 snapshots=[snapshot_row(fetched)], legs=[leg])
        verdicts = {name: proof["stages"][name]["verdict"] for name in pj.STAGES}
        assert verdicts == {"fixture_stored": "proven", "forecast_attached": "proven",
                            "suggestion": "selection_evidence",
                            "stored_result": "blocked: no match-data source answering", "settlement": "pending"}, label
        assert proof["chain"] == {"verdict": "blocked: no match-data source answering", "stage": "stored_result",
                                  "passed_with": ["suggestion: selection_evidence"], "later": ["settlement: pending"],
                                  "current": False}
        # Deferred, never asked: nothing to distrust in an attempt count it does not have.
        assert proof["flags"] == {}
    matches = {match.id: match for match, *_ in fixtures}
    verdict = pj.classify_slip(slip, [leg for _, _, leg, _ in fixtures], matches, {}, True)
    assert (verdict["state"], verdict["dry_run_state"], verdict["verdict"]) == ("pending", "pending", "pending")


# ============================================================================== database
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


QA_EMAIL = "qa.proof@example.test"
OTHER_EMAIL = "someone.else@example.test"
TABLES = ("predictions.leagues", "predictions.teams", "predictions.matches", "predictions.match_results",
          "predictions.provider_forecasts", "predictions.provider_forecast_snapshots",
          "predictions.provider_forecast_results", "users.users", "users.selection_slips", "users.selection_slip_legs")


def table_state(engine) -> dict:
    with engine.connect() as conn:
        return {table: tuple(conn.execute(text(f"select count(*), max(updated_at) from {table}")).one())
                for table in TABLES}


@pytest.fixture
def world(engine):
    """Four fixtures, two slips, committed for real so the tool's own read-only session sees them,
    and removed again afterwards whatever the test did."""
    now = datetime.now(UTC).replace(microsecond=0)
    since = now - timedelta(days=10)
    tag = uuid.uuid4().hex[:10]
    session = sessionmaker(bind=engine)()
    created = []

    def add(row):
        session.add(row)
        session.flush()
        created.append(row)
        return row

    league = add(League(id=uuid.uuid4(), name=f"Proof League {tag}", display_name="Proof League", country="Test",
                        external_api_id=f"proof:{tag}", external_api_source="test"))

    def team(name):
        return add(Team(id=uuid.uuid4(), name=f"{name} {tag}", short_name=name, country="Test",
                        external_api_id=f"proof:{tag}:{name}", external_api_source="test"))

    def fixture(home, away, kickoff, status, created_at, synced=None, recovery=None):
        meta = {"provider": "livescore"}
        if synced:
            meta["last_synced_at"] = synced.isoformat()
        if recovery:
            meta["recovery"] = recovery
        return add(Match(id=uuid.uuid4(), home_team_id=team(home).id, away_team_id=team(away).id, league_id=league.id,
                         match_date=naive(kickoff), status=status, external_api_id=f"proof:{tag}:{home}",
                         external_api_source="test", match_metadata=meta, created_at=naive(created_at),
                         updated_at=naive(created_at)))

    def snapshot(match, fetched, before=True):
        return add(ProviderForecastSnapshot(
            id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=f"evt-{tag}",
            content_hash=uuid.uuid4().hex, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
            match_confidence="exact", matched_by="name_kickoff", first_fetched_at=naive(fetched),
            last_fetched_at=naive(fetched), kickoff_at_capture=match.match_date, captured_before_kickoff=before))

    finished = fixture("Alpha", "Beta", now - timedelta(days=12), MatchStatus.FINISHED, now - timedelta(days=20),
                       synced=now - timedelta(days=12))
    stranded = fixture("Gamma", "Delta", now - timedelta(days=2), MatchStatus.SCHEDULED, now - timedelta(days=20),
                       synced=now - timedelta(days=20),
                       recovery={"attempts": 2, "first_attempt_at": (now - timedelta(days=1)).isoformat(),
                                 "last_attempt_at": (now - timedelta(days=1)).isoformat(),
                                 "last_outcome": "fresh_unanswered"})
    upcoming = fixture("Epsilon", "Zeta", now + timedelta(days=2), MatchStatus.SCHEDULED, now - timedelta(days=1),
                       synced=now - timedelta(days=1))
    unforecast = fixture("Eta", "Theta", now - timedelta(days=13), MatchStatus.FINISHED, now - timedelta(days=20),
                         synced=now - timedelta(days=13))

    add(MatchResult(id=uuid.uuid4(), match_id=finished.id, home_score=2, away_score=1, home_score_ft=2, away_score_ft=1,
                    home_score_ht=1, away_score_ht=0, result_metadata={"provider": "livescore"},
                    created_at=naive(now - timedelta(days=12) + timedelta(hours=2)),
                    updated_at=naive(now - timedelta(days=12) + timedelta(hours=2))))
    add(MatchResult(id=uuid.uuid4(), match_id=unforecast.id, home_score=0, away_score=0, home_score_ft=0,
                    away_score_ft=0, result_metadata={"provider": "livescore"},
                    created_at=naive(now - timedelta(days=13) + timedelta(hours=2)),
                    updated_at=naive(now - timedelta(days=13) + timedelta(hours=2))))
    finished_snapshot = snapshot(finished, now - timedelta(days=12, hours=10))
    stranded_snapshot = snapshot(stranded, now - timedelta(days=2, hours=10))
    snapshot(upcoming, now - timedelta(hours=5))
    add(ProviderForecastRecord(id=uuid.uuid4(), match_id=finished.id, provider="gameforecast",
                               external_event_id=f"evt-{tag}", match_confidence="exact", matched_by="name_kickoff",
                               fetched_at=naive(now - timedelta(days=12, hours=10))))
    add(ProviderForecastResult(id=uuid.uuid4(), snapshot_id=finished_snapshot.id, match_id=finished.id,
                               provider="gameforecast", outcome=PredictionOutcome.WON, is_correct=True,
                               settled_at=naive(now - timedelta(days=12) + timedelta(hours=3)),
                               rules_version="soccer-regulation-time-v2"))

    qa = add(User(id=uuid.uuid4(), email=QA_EMAIL, username=f"qa_{tag}", password_hash="not-a-hash"))
    other = add(User(id=uuid.uuid4(), email=OTHER_EMAIL, username=f"other_{tag}", password_hash="not-a-hash"))
    journey = add(SelectionSlip(id=uuid.uuid4(), user_id=qa.id, name=f"Journey {tag}", status="recorded",
                                state="pending", note="private note", recorded_reference="BET-REF-1",
                                recorded_at=naive(now - timedelta(days=13)),
                                created_at=naive(now - timedelta(days=13)), updated_at=naive(now - timedelta(days=13))))
    private = add(SelectionSlip(id=uuid.uuid4(), user_id=other.id, name=f"My own {tag}", status="saved",
                                state="lost", created_at=naive(now - timedelta(days=13)),
                                updated_at=naive(now - timedelta(days=12))))

    def leg(slip, match, position, market, outcome, snap, line=None, state="pending", settled=None, settlement=None):
        return add(SelectionSlipLeg(
            id=uuid.uuid4(), slip_id=slip.id, match_id=match.id, position=position, provider="gameforecast",
            snapshot_id=snap.id, market_id=market, outcome=outcome, line=line, period="regulation",
            probability=Decimal("0.6"), probability_source="provider", normalisation_version="markets.v1",
            kickoff_at_add=match.match_date, state=state, settled_at=settled, settlement=settlement,
            created_at=naive(now - timedelta(days=13)), updated_at=naive(now - timedelta(days=13))))

    leg(journey, finished, 0, "match_result", "home", finished_snapshot)
    leg(journey, stranded, 1, "total_goals", "over", stranded_snapshot, line=Decimal("0.5"))
    leg(private, finished, 0, "match_result", "away", finished_snapshot, state="lost",
        settled=naive(now - timedelta(days=12) + timedelta(hours=3)),
        settlement={"state": "lost", "rule": "regulation-time result", "basis": "regulation_time"})
    session.commit()
    ids = SimpleNamespace(now=now, since=since, finished=finished.id, stranded=stranded.id, upcoming=upcoming.id,
                          unforecast=unforecast.id, journey=journey.id, private=private.id, league=league.id,
                          users=(qa.id, other.id))
    try:
        yield ids
    finally:
        session.rollback()
        for row in reversed(created):
            session.delete(session.merge(row))
            session.flush()
        session.commit()
        session.close()


def backend_double(world, health=None):
    """The backend's allowlisted answers, from the measured status, recording every request.
    `health` is what GET /health answers: by default an older backend's, with no source identity."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json=health or {"status": "healthy"})
        if path == "/api/v1/data-providers/status":
            return httpx.Response(200, json=measured_status())
        if path == "/api/v1/suggestions":
            if request.url.params.get("competitions"):
                return httpx.Response(200, json=suggestions_body(fixtures_in_window=1, qualifying=1))
            return httpx.Response(200, json=suggestions_body())
        if path.endswith("/markets"):
            return httpx.Response(200, json={"forecast": {"state": "available", "snapshot_id": "s"}})
        return httpx.Response(200, json={"status": "scheduled", "forecast_state": "available"})

    return pj.GuardedClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler)), calls


def test_the_tool_proves_a_built_world_without_writing_anything(engine, world):
    factory = sessionmaker(bind=pj.read_only_engine(TEST_DATABASE_URL))
    api, calls = backend_double(world)
    store, budgets = pj.ReadOnlyRedis(FakeRedis()), pj.ReadOnlyRedis(FakeRedis())
    before = table_state(engine)

    result = pj.run(factory, api=api, store=store, budget_store=budgets,
                    selection={"matches": [str(world.upcoming), str(world.unforecast)], "slips": [str(world.journey)],
                               "window": None, "recorded_slips": False},
                    since=world.since, qa_email=QA_EMAIL, clock=lambda: world.now, process_check=False,
                    database_name="soccer_predictions_test_proof")

    assert table_state(engine) == before, "the proof changed a row"
    assert result["database"]["transaction_read_only"] == "on"
    assert result["database"]["default_transaction_read_only"] == "on"
    assert {(c.method, pj._path_template(c.url.path)) for c in calls} <= {
        ("GET", "/health"), ("GET", "/api/v1/data-providers/status"), ("GET", "/api/v1/suggestions"),
        ("GET", "/api/v1/matches/{id}"), ("GET", "/api/v1/matches/{id}/markets")}
    assert result["guards"]["redis_refused"] == [] and result["guards"]["http"]["refused"] == []
    assert result["spend_check"]["verdict"] == "passed"

    # Live Score refuses and the scheduler fails, but a fixture was synced after `since` (the
    # upcoming one, a day ago): one signal of three.
    assert result["match_data_access"]["verdict"] == "partial"
    by_id = {f["match_id"]: f for f in result["fixtures"]}
    verdicts = {key: {name: by_id[str(getattr(world, key))]["stages"][name]["verdict"] for name in pj.STAGES}
                for key in ("finished", "stranded", "upcoming", "unforecast")}
    assert verdicts["finished"] == {"fixture_stored": "proven", "forecast_attached": "proven",
                                    "suggestion": "selection_evidence", "stored_result": "proven",
                                    "settlement": "pending: owner read"}
    assert verdicts["stranded"] == {"fixture_stored": "proven", "forecast_attached": "proven",
                                    "suggestion": "selection_evidence",
                                    "stored_result": "blocked: match-data access partial", "settlement": "pending"}
    assert verdicts["upcoming"] == {"fixture_stored": "proven_current", "forecast_attached": "proven",
                                    "suggestion": "proven", "stored_result": "pending: waiting for kickoff",
                                    "settlement": "pending"}
    assert verdicts["unforecast"] == {"fixture_stored": "proven", "forecast_attached": "absent",
                                      "suggestion": "not_observed", "stored_result": "proven",
                                      "settlement": "not_applicable"}
    assert by_id[str(world.stranded)]["flags"] == {"attempt_counts_unreliable": True}

    # The other reader's slip is judged on the shared fixture, by id only.
    legs = by_id[str(world.finished)]["stages"]["settlement"]["evidence"]["legs"]
    assert sorted((leg["owner_is_qa"], leg["stored_state"], leg["verdict"]) for leg in legs) == [
        (False, "lost", "proven"), (True, "pending", "pending: owner read")]

    (journey,) = result["slips"]
    assert journey["id"] == str(world.journey) and journey["owner_is_qa"] is True
    assert (journey["state"], journey["dry_run_state"], journey["verdict"]) == ("pending", "pending", "pending")
    assert [leg["dry_run_state"] for leg in journey["legs"]] == ["won", "pending"]

    rendered = json.dumps(result)
    assert not FORBIDDEN & set(all_keys(result))
    for private in (QA_EMAIL, OTHER_EMAIL, "private note", "BET-REF-1", *(str(u) for u in world.users)):
        assert private not in rendered
    assert pj.render(result)


def test_the_run_measures_the_running_code_against_the_backends_own_account(engine, world, tmp_path, monkeypatch):
    """GET /health's source identity reaches the proof, measured against the checkout given as
    repo_root, with no process to inspect (process_check=False)."""
    app = app_tree(tmp_path, TREE)
    tree, _ = pj.app_tree_digest(app)
    api, _ = backend_double(world, health=health_with(tree))
    monkeypatch.setattr(pj, "repo_state", lambda root: dict(REPO, head=HEAD_SHA))
    factory = sessionmaker(bind=pj.read_only_engine(TEST_DATABASE_URL))
    result = pj.run(factory, api=api, store=pj.ReadOnlyRedis(FakeRedis()), budget_store=pj.ReadOnlyRedis(FakeRedis()),
                    selection={"matches": [str(world.upcoming)], "slips": [], "window": None, "recorded_slips": False},
                    since=world.since, qa_email=QA_EMAIL, clock=lambda: world.now, process_check=False,
                    repo_root=str(tmp_path), database_name="soccer_predictions_test_proof")
    running = result["backend"]["running_code"]
    assert running["basis"] == "measured" and running["includes_head"] is True
    assert running["measured"]["tree_served"] == running["measured"]["tree_now"] == tree
    assert result["backend"]["health"]["source"]["commit"] == HEAD_SHA
    assert "running code includes HEAD: True (measured)" in pj.render(result)


def test_a_write_inside_the_tools_session_is_refused_by_the_database(engine, world):
    factory = sessionmaker(bind=pj.read_only_engine(TEST_DATABASE_URL))
    with pj.read_only_session(factory) as db:
        with pytest.raises(DBAPIError, match="read-only transaction"):
            db.execute(text("update predictions.matches set venue = 'x' where id = :id"), {"id": world.finished})
    # And the connection alone, before any SET TRANSACTION: the first of the two guards.
    with pj.read_only_engine(TEST_DATABASE_URL).connect() as conn:
        with pytest.raises(DBAPIError, match="read-only transaction"):
            conn.execute(text("delete from users.selection_slip_legs where slip_id = :id"), {"id": world.journey})
    with engine.connect() as conn:
        assert conn.execute(text("select venue from predictions.matches where id = :id"),
                            {"id": world.finished}).scalar() is None


def test_recorded_slips_and_a_window_select_their_fixtures(engine, world):
    factory = sessionmaker(bind=pj.read_only_engine(TEST_DATABASE_URL))
    result = pj.run(factory, api=None, store=None, budget_store=None,
                    selection={"matches": [], "slips": [], "recorded_slips": True,
                               "window": (world.now - timedelta(days=12, hours=1), world.now - timedelta(days=11))},
                    since=world.since, qa_email=QA_EMAIL, clock=lambda: world.now, process_check=False)
    ids = {f["match_id"] for f in result["fixtures"]}
    assert {str(world.finished), str(world.stranded)} <= ids          # the journey's legs, and the window's
    assert str(world.upcoming) not in ids and str(world.unforecast) not in ids
    assert str(world.journey) in {s["id"] for s in result["slips"]}
    assert str(world.private) not in {s["id"] for s in result["slips"]}   # saved, not recorded
    assert result["spend_check"]["verdict"] == "unknown"
