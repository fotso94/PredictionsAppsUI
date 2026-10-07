"""
A count a repair could only bound must never be served, or written into a stop, as exact.

`scripts/repair_not_answers.py` takes back the attempts a provider that was never asked was
recorded as answering. Where nothing records each ask, it cannot say how many of a row's earlier
attempts were real; it marks the row instead: `attempts_quality` ("exact", "upper_bound" or
"unverified"), `attempts_at_correction` (how many attempts that covers) and
`attempts_quality_as_of` (when). These tests hold the two places a reader meets the count to that
mark:

* `serialize_recovery` serves the mark beside the count, so a reader can word it;
* `MatchRegistry._stop_reason`, the sentence written on the row when the retry budget stops, says
  "at most N" for a bounded count, and says how many of them came since the repair, exactly.

And the mark has to survive what the sweep writes afterwards: every later attempt is a real one
and is added to the count, under the same mark, with the number counted before it unchanged.

The stop test drives the shipped `record_recovery_attempt` against PostgreSQL (JSONB, the canonical
league lookup). Set TEST_DATABASE_URL; skipped when unreachable. No network.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import Match, MatchStatus, Team
from app.schemas.matches import serialize_recovery
from app.services.match_registry import RETRY_HORIZON, MatchRegistry
# TEST_DATABASE_URL when set, else the default `tests/conftest.py` points every database test at.
from tests.conftest import TEST_DATABASE_URL

#: When the repair ran, in the rows below.
CORRECTED_AT = "2026-10-07T03:00:00+00:00"
#: A row shaped like National Teams Friendlies 2026-09-24 after the repair: 18 attempts, an upper
#: bound, the last real ask the reconstructed Live Score answer of 2026-10-01.
BOUNDED = {
    "attempts": 18,
    "attempts_quality": "upper_bound",
    "attempts_at_correction": 18,
    "attempts_quality_as_of": CORRECTED_AT,
    "last_attempt_at": "2026-10-01T07:46:51.829861+00:00",
    "archive": {"state": "answered", "rows": 5, "asked_at": "2026-10-01T07:46:51.829861+00:00",
                "reconstructed": True},
    "deferrals": 4,
    "last_outcome": "deferred",
    "corrections": [{"applied_at": CORRECTED_AT, "by": "backend/scripts/repair_not_answers.py",
                     "group": "C", "removed_attempts": 2}],
}


# ----------------------------------------------------------------------------- serving the mark
def test_a_reconstructed_archive_answer_is_served_as_reconstructed():
    """A row count rebuilt from synced match rows must not read as a recorded one."""
    served = serialize_recovery({"recovery": dict(BOUNDED)})
    assert served["archive"]["reconstructed"] is True and served["archive"]["rows"] == 5
    plain = dict(BOUNDED, archive={"state": "empty", "rows": 0, "asked_at": CORRECTED_AT})
    assert serialize_recovery({"recovery": plain})["archive"]["reconstructed"] is False


def test_the_mark_is_served_beside_the_count():
    served = serialize_recovery({"recovery": dict(BOUNDED)})
    assert served["attempts"] == 18
    assert served["attempts_quality"] == "upper_bound"
    assert served["attempts_at_correction"] == 18


def test_a_row_no_repair_touched_serves_no_mark():
    served = serialize_recovery({"recovery": {"attempts": 3, "last_outcome": "fresh_unanswered"}})
    assert served["attempts"] == 3
    assert served["attempts_quality"] is None
    assert served["attempts_at_correction"] is None


def test_an_unverified_count_is_served_as_such():
    state = dict(BOUNDED, attempts=29, attempts_at_correction=29, attempts_quality="unverified")
    served = serialize_recovery({"recovery": state})
    assert (served["attempts_quality"], served["attempts_at_correction"]) == ("unverified", 29)


# ----------------------------------------------------------------------------- the stop sentence
def test_an_exact_count_is_worded_as_before():
    """No mark, or "exact": the sentence the sweep has always written, word for word."""
    registry = MatchRegistry(db=None)
    state = {"attempts": 3, "last_attempt_at": "2026-10-08T12:00:00+00:00"}
    plain = registry._stop_reason(state, RETRY_HORIZON)
    assert plain.startswith("We asked the results provider 3 times, most recently 2026-10-08 12:00 UTC, "
                            "and each answer it gave held no result for this match.")
    assert registry._stop_reason(dict(state, attempts_quality="exact"), RETRY_HORIZON) == plain
    assert "at most" not in plain


@pytest.mark.parametrize("quality", ["upper_bound", "unverified"])
def test_a_bounded_count_is_worded_as_a_bound(quality):
    registry = MatchRegistry(db=None)
    reason = registry._stop_reason(dict(BOUNDED, attempts_quality=quality), RETRY_HORIZON)
    assert reason.startswith("We asked the results provider at most 18 times, most recently "
                             "2026-10-01 07:46 UTC, and each answer it gave held no result for this match.")
    assert ("The 18 counted before 2026-10-07 03:00 UTC may include asks recorded as answered when no "
            "request was sent, so that part is an upper bound.") in reason
    # Everything else the stop says is unchanged: a budget decision, and what could reopen it.
    assert "a limit on what we spend, not evidence that no result exists" in reason


def test_asks_made_after_the_repair_are_stated_as_exact():
    registry = MatchRegistry(db=None)
    one = registry._stop_reason(dict(BOUNDED, attempts=19), RETRY_HORIZON)
    assert "at most 19 times" in one and "; the 1 since is exact." in one
    two = registry._stop_reason(dict(BOUNDED, attempts=20), RETRY_HORIZON)
    assert "at most 20 times" in two and "; the 2 since are exact." in two


def test_provider_errors_are_still_reported_apart():
    registry = MatchRegistry(db=None)
    reason = registry._stop_reason(dict(BOUNDED, provider_errors=2), RETRY_HORIZON)
    assert "2 other requests went out and got no answer, and are not counted." in reason


# ----------------------------------------------------------------------------- what the sweep writes later
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


def _fixture(db, kickoff: datetime, recovery: dict) -> Match:
    registry = MatchRegistry(db)
    league = registry.ensure_canonical_league("national_teams_friendlies")
    teams = []
    for name in ("Northland", "Southmark"):
        team = Team(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:6]}", country="World",
                    team_scope="national_senior_men")
        db.add(team)
        teams.append(team)
    db.flush()
    match = Match(id=uuid.uuid4(), home_team_id=teams[0].id, away_team_id=teams[1].id,
                  league_id=league.id, match_date=kickoff.replace(tzinfo=None),
                  status=MatchStatus.SCHEDULED, match_metadata={"recovery": dict(recovery)})
    db.add(match)
    db.flush()
    return match


def test_a_later_attempt_keeps_the_mark_and_counts_on_top_of_it(db):
    kickoff = datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc)
    match = _fixture(db, kickoff, BOUNDED)
    registry = MatchRegistry(db)

    state = registry.record_recovery_attempt(match, datetime(2026, 10, 8, 4, 30, tzinfo=timezone.utc))

    assert state["attempts"] == 19
    assert state["attempts_quality"] == "upper_bound"
    assert state["attempts_at_correction"] == 18
    assert state["attempts_quality_as_of"] == CORRECTED_AT
    assert state["corrections"] == BOUNDED["corrections"]
    assert "gave_up_at" not in state, "eight days old: the schedule still asks"
    served = serialize_recovery(match.match_metadata)
    assert (served["attempts"], served["attempts_quality"], served["attempts_at_correction"]) == (
        19, "upper_bound", 18)


def test_a_stop_on_a_bounded_row_states_a_bound(db):
    """Friendlies 2026-09-24: the first answered ask past the horizon stops it, and says "at most"."""
    kickoff = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
    match = _fixture(db, kickoff, BOUNDED)
    registry = MatchRegistry(db)
    now = kickoff + RETRY_HORIZON + timedelta(hours=1)

    state = registry.record_recovery_attempt(match, now)

    assert state["gave_up_at"] == now.isoformat()
    assert state["stopped_by"] == "retry_budget"
    assert state["attempts"] == 19 and state["attempts_quality"] == "upper_bound"
    reason = state["gave_up_reason"]
    assert reason.startswith("We asked the results provider at most 19 times, most recently "
                             "2026-10-08 05:00 UTC")
    assert "The 18 counted before 2026-10-07 03:00 UTC may include asks recorded as answered" in reason
    assert "; the 1 since is exact." in reason
