"""A knockout tie's score periods, from the provider payload to the settled row.

A tie that finishes 0-0 and is won 4-3 on penalties is two true things at once: a draw to every
market that settles on regulation time, and a Switzerland win to everyone who watched it. This
module drives that tie the whole way - Live Score API payload, provider mapping, match registry,
stored ``match_results`` row, settlement - and pins down that each reader gets the one that is
true for them.

The payloads are NOT invented. They are read from ``docs/evidence/`` as they came back from the
provider on 2026-09-17 and 2026-09-21: four World Cup knockout ties decided on penalties, and
three ordinary La Liga results. Only the team objects are put back into the ``{"id", "name"}``
shape the endpoint returns, because the evidence files flatten them to names for readability;
every score, status and period marker below is the provider's own.

One payload here IS constructed and is labelled as such: a tie whose extra-time score differs
from its full-time score. No such tie is in the evidence - all four verified ones were goalless
in extra time - so it exists to pin the parsing rule that a general "score" field is never read
as regulation time.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionOutcome, PredictionResult,
    PredictionSource, PredictionStatus,
)
from app.models.users import AccountStatus, User, UserType
from app.services import settlement as S
from app.services.match_registry import MatchRegistry, played_outcome, scoreline_label
from app.services.providers.base import ProviderFixture
from app.services.providers.livescore_api import LiveScoreAPIProvider

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

EVIDENCE = Path(__file__).resolve().parents[3] / "docs" / "evidence"
KNOCKOUT_FILE = EVIDENCE / "livescore-world-cup-knockout-scores.json"
NINETY_MINUTE_FILE = EVIDENCE / "livescore-history-2026-09-16-la-liga.json"


def _rows(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text())["rows"]


KNOCKOUT_ROWS = _rows(KNOCKOUT_FILE)
NINETY_MINUTE_ROWS = _rows(NINETY_MINUTE_FILE)


def _tie(name: str) -> Dict[str, Any]:
    return next(row for row in KNOCKOUT_ROWS if row["home"] == name)


SWITZERLAND_COLOMBIA = _tie("Switzerland")     # ft 0-0, et 0-0, ps 4-3, time "AP"


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
    """Session joined to an outer transaction; service-level commit() only releases a savepoint."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ----------------------------------------------------------------------------- the real pipeline
def _payload(row: Dict[str, Any], competition_id: str = "362",
             competition_name: str = "FIFA World Cup") -> Dict[str, Any]:
    """One provider `match` row, with the team objects put back in the endpoint's shape."""
    item = dict(row)
    for side, team_id in (("home", 100), ("away", 200)):
        value = row[side]
        item[side] = value if isinstance(value, dict) else {"id": team_id, "name": value}
    item.setdefault("status", "FINISHED")
    item.setdefault("competition", {"id": competition_id, "name": competition_name})
    item.setdefault("id", row.get("fixture_id"))
    return item


def _fixture(row: Dict[str, Any], **payload_kwargs) -> ProviderFixture:
    """Provider payload -> ProviderFixture, through the provider's own mapping."""
    provider = LiveScoreAPIProvider(api_key="test-key", api_secret="test-secret", use_default_ids=False)
    fixture = provider._fixture_from_match(_payload(row, **payload_kwargs), [])
    # Unique per test so a rolled-back run never collides with a stored fixture id.
    fixture.external_id = f"{fixture.external_id}-{uuid.uuid4().hex[:8]}"
    return fixture


def _store(db, fixture: ProviderFixture) -> Match:
    """ProviderFixture -> stored match and match_results row."""
    match = MatchRegistry(db).upsert_fixture(fixture)
    assert match is not None, "the registry refused a fixture these tests depend on storing"
    db.flush()
    db.refresh(match)
    return match


def _ingest(db, row: Dict[str, Any], **payload_kwargs) -> Match:
    """Provider payload -> ProviderFixture -> stored match and match_results row."""
    return _store(db, _fixture(row, **payload_kwargs))


def _period_blind(fixture: ProviderFixture, provider: str = "api_football") -> ProviderFixture:
    """The same finished match as a provider with no period breakdown reports it.

    A score, a status, and nothing about how the match got there. API-Football and TheSportsDB are
    both configured as fallbacks behind Live Score and neither of their mappings populates a single
    period column, so this is the ordinary second opinion on a stored tie rather than a contrived
    one. It keeps the teams, the competition and the kickoff, because that is how it lands on the
    same stored match.
    """
    return replace(fixture, provider=provider,
                   external_id=f"{provider}-{uuid.uuid4().hex[:8]}",
                   minute=None, periods_reported=False,
                   ht_home_score=None, ht_away_score=None,
                   ft_home_score=None, ft_away_score=None,
                   et_home_score=None, et_away_score=None,
                   ps_home_score=None, ps_away_score=None)


def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"knockout-{suffix}@test.local", username=f"knockout_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _prediction(db, match: Match, home: float, draw: float, away: float) -> Prediction:
    row = Prediction(
        id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
        created_by=_expert(db).id,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)), away_win_prob=Decimal(str(away)),
        confidence_score=Decimal("0.8"), status=PredictionStatus.PUBLISHED, priority_level=100,
        published_at=match.match_date - timedelta(hours=6))
    db.add(row)
    db.flush()
    return row


def _settle(db, match: Match) -> Dict[str, Any]:
    report = S.SettlementService(db).settle_match(match)
    db.flush()
    return report


def _settled(db, prediction: Prediction) -> Optional[PredictionResult]:
    return db.query(PredictionResult).filter(
        PredictionResult.prediction_id == prediction.id).one_or_none()


def _market(row: PredictionResult, name: str) -> Dict[str, Any]:
    return next(entry for entry in row.market_results if entry["market"] == name)


# ----------------------------------------------------------------------------- ingestion
@pytest.mark.parametrize("row", KNOCKOUT_ROWS, ids=[r["home"] for r in KNOCKOUT_ROWS])
def test_each_verified_knockout_tie_is_stored_with_its_periods_apart(db, row):
    """Every period the provider sent survives ingestion in its own column."""
    match = _ingest(db, row)
    result: MatchResult = match.result
    scores = row["scores"]

    def pair(text_score: str):
        return tuple(int(part.strip()) for part in text_score.split("-"))

    assert (result.home_score_ht, result.away_score_ht) == pair(scores["ht_score"])
    assert (result.home_score_ft, result.away_score_ft) == pair(scores["ft_score"])
    assert (result.home_score_et, result.away_score_et) == pair(scores["et_score"])
    assert (result.home_score_pens, result.away_score_pens) == pair(scores["ps_score"])
    # The score on display is the football that was played; the shoot-out is never folded into it.
    assert (result.home_score, result.away_score) == pair(scores["et_score"])
    assert result.result_metadata["beyond_regulation"] is True
    assert result.result_metadata["period_marker"] == row["time"]


def test_the_reader_is_shown_the_scoreline_people_remember(db):
    """"0-0" alone is as wrong for a reader as "4-3" would be for settlement."""
    match = _ingest(db, SWITZERLAND_COLOMBIA)

    assert match.result.result_metadata["scoreline"] == "0-0 (4-3 pens)"
    assert match.match_metadata["scoreline"] == "0-0 (4-3 pens)"
    assert scoreline_label(1, 1, None, None) == "1-1"
    assert scoreline_label(None, None, 4, 3) is None


def test_a_general_score_field_is_never_read_as_the_regulation_score(db):
    """A goal in the 105th minute must not turn a 90-minute draw into a win.

    CONSTRUCTED payload: no verified tie has a different score at full time and after extra time
    (all four were goalless in extra time), so the rule is pinned on a payload in the provider's
    shape rather than on a provider row.
    """
    row = dict(SWITZERLAND_COLOMBIA,
               scores={"ht_score": "0 - 0", "ft_score": "1 - 1", "et_score": "2 - 1",
                       "ps_score": "", "score": "2 - 1"},
               time="AET")
    match = _ingest(db, row)

    assert (match.result.home_score_ft, match.result.away_score_ft) == (1, 1)
    assert (match.result.home_score_et, match.result.away_score_et) == (2, 1)
    assert (match.result.home_score, match.result.away_score) == (2, 1)

    leaning_home = _prediction(db, match, home=0.6, draw=0.25, away=0.15)
    _settle(db, match)

    settled = _settled(db, leaning_home)
    assert settled.actual_outcome == "draw"
    assert settled.outcome == PredictionOutcome.LOST


# ----------------------------------------------------------------------------- settlement
def test_switzerland_loses_because_the_regulation_score_was_a_draw(db):
    """The tie Switzerland won 4-3 on penalties settles a 1X2 market as the draw it was."""
    match = _ingest(db, SWITZERLAND_COLOMBIA)
    on_switzerland = _prediction(db, match, home=0.55, draw=0.28, away=0.17)

    report = _settle(db, match)

    settled = _settled(db, on_switzerland)
    assert settled.actual_outcome == "draw"
    assert settled.outcome == PredictionOutcome.LOST
    assert settled.is_correct is False
    entry = _market(settled, S.MARKET_MATCH_RESULT)
    assert entry["predicted"] == "home" and entry["actual"] == "draw"
    # The shoot-out is still on the row: it settled nothing and it is still the result of the tie.
    assert (match.result.home_score_pens, match.result.away_score_pens) == (4, 3)
    assert report["expert_predictions"]["settled"] == 1


@pytest.mark.parametrize("row", KNOCKOUT_ROWS, ids=[r["home"] for r in KNOCKOUT_ROWS])
def test_no_verified_tie_is_ever_settled_on_its_shootout(db, row):
    """All four were level after 90 minutes, so all four settle as draws whoever won the shoot-out."""
    match = _ingest(db, row)
    pens_home, pens_away = (int(part.strip()) for part in row["scores"]["ps_score"].split("-"))
    shootout_winner = _prediction(db, match, home=0.6, draw=0.25, away=0.15) if pens_home > pens_away \
        else _prediction(db, match, home=0.15, draw=0.25, away=0.6)

    _settle(db, match)

    settled = _settled(db, shootout_winner)
    assert settled.actual_outcome == "draw"
    assert settled.outcome == PredictionOutcome.LOST


def test_a_tie_past_ninety_with_no_regulation_score_is_withheld_with_its_reason(db):
    """The period the rule names is missing, so nothing is scored and the reason says which."""
    match = _ingest(db, SWITZERLAND_COLOMBIA)
    prediction = _prediction(db, match, home=0.55, draw=0.28, away=0.17)
    # A source that reported the shoot-out but never the 90-minute score.
    match.result.home_score_ft = match.result.away_score_ft = None
    match.result.home_score_et = match.result.away_score_et = None
    db.flush()

    report = _settle(db, match)

    assert _settled(db, prediction) is None
    assert report["matches_settled"] == 0
    reason = next(entry["reason"] for entry in report["skipped_matches"]
                  if entry["match_id"] == str(match.id))
    assert "penalties" in reason and "regulation time only" in reason
    # The reason is on the prediction too, so an unscored row explains itself where it is read.
    withheld = next(entry for entry in report["not_scored"] if entry["id"] == str(prediction.id))
    assert withheld["reason"] == reason
    assert report["expert_predictions"]["not_scored"] == 1


def test_extra_time_alone_withholds_when_no_regulation_score_is_stored(db):
    match = _ingest(db, SWITZERLAND_COLOMBIA)
    prediction = _prediction(db, match, home=0.55, draw=0.28, away=0.17)
    match.result.home_score_ft = match.result.away_score_ft = None
    match.result.home_score_pens = match.result.away_score_pens = None
    db.flush()

    report = _settle(db, match)

    assert _settled(db, prediction) is None
    reason = next(entry["reason"] for entry in report["skipped_matches"]
                  if entry["match_id"] == str(match.id))
    assert "extra time" in reason and "regulation time only" in reason


# ----------------------------------------------------------------------------- nothing moved
@pytest.mark.parametrize("row", NINETY_MINUTE_ROWS,
                         ids=[r["home"]["name"] for r in NINETY_MINUTE_ROWS])
def test_an_ordinary_ninety_minute_result_settles_exactly_as_before(db, row):
    """The club suite depends on this not moving: same score in, same settlement out."""
    match = _ingest(db, row, competition_id="54", competition_name="La Liga")
    home_goals, away_goals = (int(part.strip()) for part in row["scores"]["ft_score"].split("-"))

    assert (match.result.home_score, match.result.away_score) == (home_goals, away_goals)
    assert (match.result.home_score_ft, match.result.away_score_ft) == (home_goals, away_goals)
    assert (match.result.home_score_et, match.result.away_score_et) == (None, None)
    assert (match.result.home_score_pens, match.result.away_score_pens) == (None, None)
    assert match.result.result_metadata["beyond_regulation"] is False
    assert match.result.result_metadata["scoreline"] == f"{home_goals}-{away_goals}"

    leaning_home = _prediction(db, match, home=0.6, draw=0.25, away=0.15)
    _settle(db, match)

    settled = _settled(db, leaning_home)
    expected = "home" if home_goals > away_goals else "away" if away_goals > home_goals else "draw"
    assert settled.actual_outcome == expected
    assert settled.outcome == (PredictionOutcome.WON if expected == "home" else PredictionOutcome.LOST)


def test_a_result_stored_before_the_periods_existed_still_settles(db):
    """Every row written by the old pipeline has NULL periods; none of them may stop scoring.

    This is the shape of all 48 results this installation already holds: a score, a half-time
    score, and ``{"provider": "livescore"}`` for metadata. Nothing there says the match went past
    90 minutes, so the stored score is its 90-minute score and is settled as one.
    """
    match = _ingest(db, NINETY_MINUTE_ROWS[0], competition_id="54", competition_name="La Liga")
    result: MatchResult = match.result
    result.home_score, result.away_score = 2, 0
    result.home_score_ft = result.away_score_ft = None
    result.home_score_et = result.away_score_et = None
    result.home_score_pens = result.away_score_pens = None
    result.result_metadata = {"provider": "livescore"}
    db.flush()

    leaning_home = _prediction(db, match, home=0.6, draw=0.25, away=0.15)
    report = _settle(db, match)

    settled = _settled(db, leaning_home)
    assert settled.actual_outcome == "home"
    assert settled.outcome == PredictionOutcome.WON
    assert report["skipped_matches"] == []


# ----------------------------------------------------------------------------- the rule itself
def test_the_published_ruleset_says_which_period_settles_and_what_happens_without_it():
    rules = S.settlement_rules()
    assert "penalty shoot-out" in rules["basis"] and "90 minutes" in rules["basis"]
    assert "settle nothing" in rules["periods"]
    assert "WITHHELD" in rules["withheld"] and "not a loss" in rules["withheld"]
    assert rules["version"] == S.RULES_VERSION


def test_regulation_score_prefers_the_stored_ninety_minute_score_over_the_tie_score(db):
    """A tie with both stored settles on the 90-minute pair, never on the score of the tie."""
    match = _ingest(db, SWITZERLAND_COLOMBIA)
    match.result.home_score, match.result.away_score = 2, 1      # as if extra time had decided it
    db.flush()

    score, refusal = S.regulation_score(match.result)

    assert refusal is None
    assert (score.home, score.away) == (0, 0)
    assert score.outcome == "draw"


# ------------------------------------------------- a source that knows less must not unlearn it
def test_a_period_blind_refresh_keeps_every_period_a_better_source_stored(db):
    """The fallback providers send no periods at all; their silence must change no period column.

    This is the whole of the second half of the pipeline's exposure. Live Score ingests the tie
    with its periods apart; a later results pass falls through to API-Football or TheSportsDB,
    neither of which populates one period column; and if that write went straight across, the row
    would come out of it with NULL periods, `beyond_regulation` False and a scoreline of "0-0" for
    a tie that was won 4-3 on penalties.
    """
    fixture = _fixture(SWITZERLAND_COLOMBIA)
    match = _store(db, fixture)
    before = match.result.id

    refreshed = _store(db, _period_blind(fixture))

    assert refreshed.id == match.id, "the fallback fixture must land on the stored match"
    result: MatchResult = refreshed.result
    assert result.id == before, "the fallback must refresh the stored result, not replace it"
    assert (result.home_score_ht, result.away_score_ht) == (0, 0)
    assert (result.home_score_ft, result.away_score_ft) == (0, 0)
    assert (result.home_score_et, result.away_score_et) == (0, 0)
    assert (result.home_score_pens, result.away_score_pens) == (4, 3)
    assert result.result_metadata["beyond_regulation"] is True
    assert result.result_metadata["scoreline"] == "0-0 (4-3 pens)"
    # The match-level copy a reader is served is merged the same way.
    assert refreshed.match_metadata["ps_home_score"] == 4
    assert refreshed.match_metadata["ft_home_score"] == 0
    assert refreshed.match_metadata["scoreline"] == "0-0 (4-3 pens)"


def test_a_period_blind_refresh_still_leaves_the_tie_settling_as_the_draw_it_was(db):
    """The point of keeping the periods: the settled answer does not depend on who synced last."""
    fixture = _fixture(SWITZERLAND_COLOMBIA)
    match = _store(db, fixture)
    on_switzerland = _prediction(db, match, home=0.55, draw=0.28, away=0.17)

    _store(db, _period_blind(fixture, provider="thesportsdb"))
    report = _settle(db, match)

    settled = _settled(db, on_switzerland)
    assert settled.actual_outcome == "draw"
    assert settled.outcome == PredictionOutcome.LOST
    assert report["skipped_matches"] == []


def test_a_period_blind_refresh_does_not_overwrite_a_stored_score_with_nothing(db):
    """A provider that sends no score at all leaves the stored one standing."""
    fixture = _fixture(NINETY_MINUTE_ROWS[0], competition_id="54", competition_name="La Liga")
    match = _store(db, fixture)
    stored = (match.result.home_score, match.result.away_score)

    scoreless = replace(_period_blind(fixture), home_score=None, away_score=None)
    refreshed = _store(db, scoreless)

    assert (refreshed.result.home_score, refreshed.result.away_score) == stored
    assert refreshed.match_metadata["home_score"] == stored[0]
    assert refreshed.match_metadata["scoreline"] == f"{stored[0]}-{stored[1]}"


# ------------------------------------------------- three states, because there are three answers
def test_a_provider_that_reports_no_periods_leaves_beyond_regulation_unknown(db):
    """"Nobody told us" is stored as nobody telling us, not as "it ended at 90"."""
    fixture = _period_blind(_fixture(NINETY_MINUTE_ROWS[0], competition_id="54",
                                     competition_name="La Liga"))
    assert fixture.went_beyond_regulation is None

    match = _store(db, fixture)

    assert match.result.result_metadata["beyond_regulation"] is None
    assert S.went_beyond_regulation(match.result) == (None, None)


def test_live_score_reporting_no_extra_time_is_a_report_and_reads_as_one(db):
    """Live Score sends `et_score` and `ps_score` on every row, so its "" is an answer."""
    fixture = _fixture(NINETY_MINUTE_ROWS[0], competition_id="54", competition_name="La Liga")
    assert fixture.periods_reported is True
    assert fixture.went_beyond_regulation is False

    match = _store(db, fixture)

    assert match.result.result_metadata["beyond_regulation"] is False
    beyond, evidence = S.went_beyond_regulation(match.result)
    assert beyond is False
    assert "reported no play past 90 minutes" in evidence


def test_a_live_match_is_not_yet_a_report_about_extra_time(db):
    """A match still being played has not ended at 90 or gone past it; it has not ended."""
    row = dict(NINETY_MINUTE_ROWS[0], status="IN PLAY", time="67")
    fixture = _fixture(row, competition_id="54", competition_name="La Liga")

    assert fixture.periods_reported is True
    assert fixture.went_beyond_regulation is None


def test_a_row_stored_before_the_periods_existed_reads_as_unknown(db):
    """All 48 rows this installation holds carry `{"provider": "livescore"}` and nothing else."""
    match = _ingest(db, NINETY_MINUTE_ROWS[0], competition_id="54", competition_name="La Liga")
    result: MatchResult = match.result
    result.home_score_ft = result.away_score_ft = None
    result.home_score_et = result.away_score_et = None
    result.home_score_pens = result.away_score_pens = None
    result.result_metadata = {"provider": "livescore"}
    db.flush()

    assert S.went_beyond_regulation(result) == (None, None)


def test_a_marker_past_ninety_is_never_downgraded_by_a_source_that_did_not_see_it(db):
    """"AP" on the row is positive evidence; a later silence about extra time is not evidence."""
    fixture = _fixture(SWITZERLAND_COLOMBIA)
    match = _store(db, fixture)
    # A source that enumerates periods but has the shoot-out missing from this row.
    contradicting = replace(_period_blind(fixture, provider="api_football"), periods_reported=True,
                            ft_home_score=0, ft_away_score=0)
    assert contradicting.went_beyond_regulation is False

    refreshed = _store(db, contradicting)

    assert refreshed.result.result_metadata["beyond_regulation"] is True
    assert (refreshed.result.home_score_pens, refreshed.result.away_score_pens) == (4, 3)


# ------------------------------------------------- which question the stored H/D/A column answers
@pytest.mark.parametrize("row", KNOCKOUT_ROWS + NINETY_MINUTE_ROWS,
                         ids=[r["home"] if isinstance(r["home"], str) else r["home"]["name"]
                              for r in KNOCKOUT_ROWS + NINETY_MINUTE_ROWS])
def test_the_result_column_is_the_outcome_of_the_score_in_its_own_row(db, row):
    """`match_results.result` answers one question: who won the football that was played."""
    competition = {} if row in KNOCKOUT_ROWS else {"competition_id": "54", "competition_name": "La Liga"}
    match = _ingest(db, row, **competition)
    result: MatchResult = match.result

    assert result.result == played_outcome(result.home_score, result.away_score)


def test_the_result_column_and_settlement_answer_different_questions_and_both_are_right(db):
    """ft 1-1, et 2-1: "H" to a reader of the row, a draw to every market. Neither is a bug.

    CONSTRUCTED payload, for the reason the parsing test above gives: no verified tie has a
    different score at full time and after extra time.
    """
    row = dict(SWITZERLAND_COLOMBIA,
               scores={"ht_score": "0 - 0", "ft_score": "1 - 1", "et_score": "2 - 1",
                       "ps_score": "", "score": "2 - 1"},
               time="AET")
    match = _ingest(db, row)
    prediction = _prediction(db, match, home=0.6, draw=0.25, away=0.15)

    # The row says H, and that is the played score's own outcome: 2-1 after extra time.
    assert (match.result.home_score, match.result.away_score) == (2, 1)
    assert match.result.result == "H"
    # Settlement reads the regulation pair and never this column.
    score, refusal = S.regulation_score(match.result)
    assert refusal is None and score.outcome == "draw"

    _settle(db, match)

    assert _settled(db, prediction).actual_outcome == "draw"


# ------------------------------------------------- the assumption, owned rather than denied
def test_an_unflagged_result_is_taken_as_regulation_time_and_the_rule_says_so(db):
    """No 90-minute score, nothing saying it went past 90: the stored score is settled as regulation."""
    match = _ingest(db, NINETY_MINUTE_ROWS[0], competition_id="54", competition_name="La Liga")
    result: MatchResult = match.result
    result.home_score, result.away_score = 2, 0
    result.home_score_ft = result.away_score_ft = None
    result.result_metadata = {"provider": "livescore"}
    db.flush()

    assert S.went_beyond_regulation(result) == (None, None)
    score, refusal = S.regulation_score(result)
    assert refusal is None
    assert (score.home, score.away) == (2, 0)
    # And the published ruleset says this is what happens, rather than the code doing it quietly.
    assert "nothing indicates the tie went past 90 minutes" in S.settlement_rules()["periods"]
