"""
Preserved expert records: an edit must append, never rewrite.

What was happening before this change: `ExpertPredictionService.update_prediction` overwrote the
live `predictions.predictions` row in place. `predictions.prediction_audit` - the table built to
hold old_values/new_values - had never received a single row from anywhere in the application, and
the endpoint's only audit entry passed the *already updated* prediction as both the original and
the override, so it recorded the new probabilities as the old ones. The version readers had seen
before a correction was therefore gone, and a correction made after kickoff could quietly replace
the prematch view with a different one.

These tests hold the fixed behaviour: the replaced version is written to prediction_audit before the
row is touched, it stays retrievable with its own timestamp, a second correction appends a second
revision rather than rewriting the first, and an edit made after kickoff cannot remove the original.

Requires PostgreSQL (TEST_DATABASE_URL, default the docker-compose test database); skipped when
unreachable. No provider is ever called: match reads use refresh=false.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.predictions import (
    League,
    Match,
    MatchStatus,
    Prediction,
    PredictionAudit,
    PredictionSource,
    PredictionStatus,
    Team,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.matches import serialize_expert_prediction
from app.schemas.predictions import ExpertPredictionUpdate
from app.services import settlement as S
from app.services.expert_prediction import REVISION_ACTION, REVISION_VALUE_FIELDS, ExpertPredictionService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# Far enough ahead that no other module in the suite has fixtures there.
FUTURE_KICKOFF = datetime.utcnow() + timedelta(days=45)
PAST_KICKOFF = datetime.utcnow() - timedelta(hours=5)
#: A fixture already played, on a day of its own, for the late-publication cases.
LATE_KICKOFF = (datetime.utcnow() - timedelta(days=12)).replace(hour=15, minute=0, second=0, microsecond=0)


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


@pytest.fixture(autouse=True)
def in_memory_cache(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    # The match endpoints depend on app.db.session.get_db and the expert endpoints on
    # app.core.deps.get_db - two distinct callables. Both are overridden so one test session sees
    # the writes the other made.
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps_get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(deps_get_db, None)


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"rev-{suffix}@test.local", username=f"rev_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, country="England")
    db.add(team)
    db.flush()
    return team


def _league(db) -> League:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    return league


def _match(db, kickoff: datetime, label: str, status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    league = _league(db)
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, f"{label} Home").id,
                  away_team_id=_team(db, f"{label} Away").id, match_date=kickoff, status=status,
                  external_api_id=f"ext-{label}-{uuid.uuid4().hex[:6]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


def _publish(db, match: Match, user: User, published_at: datetime, **values) -> Prediction:
    fields = dict(home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
                  confidence_score=Decimal("0.8"))
    fields.update({name: Decimal(str(value)) for name, value in values.items()})
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, status=PredictionStatus.PUBLISHED,
                            published_at=published_at, priority_level=100,
                            reasoning="first view: home side rested", **fields)
    db.add(prediction)
    db.flush()
    return prediction


def _edit(db, prediction: Prediction, expert: User, **fields) -> Prediction:
    payload = dict(home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1)
    payload.update(fields)
    return ExpertPredictionService(db).update_prediction(
        str(prediction.id), ExpertPredictionUpdate(**payload), expert)


def _revision_rows(db, prediction: Prediction):
    return db.query(PredictionAudit).filter(
        PredictionAudit.prediction_id == prediction.id,
        PredictionAudit.action == REVISION_ACTION,
    ).order_by(PredictionAudit.created_at.asc()).all()


def _detail(client, match: Match) -> dict:
    response = client.get(f"/api/v1/matches/{match.id}")
    assert response.status_code == 200, response.text
    return response.json()


# ----------------------------------------------------------------------------- the audit row itself
def test_editing_a_published_prediction_writes_old_and_new_values_to_prediction_audit(db):
    """prediction_audit existed and had never been written to. It is now the preservation mechanism."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "audit")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=3))

    assert _revision_rows(db, prediction) == []

    _edit(db, prediction, expert, reasoning="second view: key defender fit again")

    rows = _revision_rows(db, prediction)
    assert len(rows) == 1
    assert rows[0].old_values["home_win_prob"] == pytest.approx(0.5)
    assert rows[0].new_values["home_win_prob"] == pytest.approx(0.7)
    assert rows[0].old_values["reasoning"] == "first view: home side rested"
    assert rows[0].user_id == expert.id
    assert "home_win_prob 0.5 -> 0.7" in rows[0].changes_summary


def test_the_edit_still_behaves_as_before_for_the_live_row(db):
    """Preserving the previous version must not change what an edit does to the current one."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "live")
    published_at = datetime.utcnow() - timedelta(hours=3)
    prediction = _publish(db, match, expert, published_at)

    updated = _edit(db, prediction, expert, confidence_score=0.9)

    assert float(updated.home_win_prob) == pytest.approx(0.7)
    assert updated.status == PredictionStatus.PUBLISHED
    assert updated.published_at == published_at  # publication time is not restamped


# ----------------------------------------------------------------------------- exposed on the match
def test_the_match_payload_exposes_the_original_version_with_its_timestamp(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "exposed")
    published_at = (datetime.utcnow() - timedelta(hours=6)).replace(microsecond=0)
    prediction = _publish(db, match, expert, published_at)

    _edit(db, prediction, expert, reasoning="second view")

    payload = _detail(client, match)
    revisions = payload["expert_prediction_revisions"]
    assert len(revisions) == 1
    original = revisions[0]
    assert original["revision"] == 1
    assert original["prediction_id"] == str(prediction.id)
    assert original["values"]["home_win_prob"] == pytest.approx(0.5)
    assert original["values"]["away_win_prob"] == pytest.approx(0.2)
    # The version that was live carries the time it was published, and the time it was replaced.
    assert original["published_at"] == published_at.isoformat() + "Z"
    assert original["replaced_at"].endswith("Z")
    assert original["edited_after_kickoff"] is False
    # ...alongside the current prediction, which shows the corrected numbers.
    assert payload["expert_prediction"]["home_win_prob"] == pytest.approx(0.7)


def test_an_unedited_prediction_has_no_revisions(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "unedited")
    _publish(db, match, expert, datetime.utcnow())

    assert _detail(client, match)["expert_prediction_revisions"] == []


def test_a_correction_appends_rather_than_rewriting(client, db):
    """Two corrections leave two revisions, and the first is still the original."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "append")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=8))

    _edit(db, prediction, expert, home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15)
    _edit(db, prediction, expert, home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1)

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert [row["revision"] for row in revisions] == [1, 2]
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)   # the original
    assert revisions[1]["values"]["home_win_prob"] == pytest.approx(0.6)   # the first correction
    assert revisions[0]["replaced_at"] <= revisions[1]["replaced_at"]


# ----------------------------------------------------------------------------- after kickoff
def test_a_post_kickoff_edit_cannot_make_the_original_disappear(client, db):
    """The prematch view is the whole point of the record: it must survive an edit made afterwards."""
    expert = _expert(db)
    match = _match(db, PAST_KICKOFF, "postkick", status=MatchStatus.LIVE)
    published_at = (datetime.utcnow() - timedelta(hours=9)).replace(microsecond=0)
    prediction = _publish(db, match, expert, published_at)

    _edit(db, prediction, expert, home_win_prob=0.95, draw_prob=0.03, away_win_prob=0.02,
          reasoning="rewritten after the match started")

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)
    assert revisions[0]["published_at"] == published_at.isoformat() + "Z"
    # Flagged, so a reader can see the correction was made after the match had begun.
    assert revisions[0]["edited_after_kickoff"] is True


def test_a_post_kickoff_edit_after_an_earlier_one_still_keeps_the_original(client, db):
    expert = _expert(db)
    match = _match(db, PAST_KICKOFF, "twoedits", status=MatchStatus.LIVE)
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=10))

    _edit(db, prediction, expert, home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15)
    _edit(db, prediction, expert, home_win_prob=0.99, draw_prob=0.005, away_win_prob=0.005)

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 2
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)


# ----------------------------------------------------------------------------- endpoint round trip
def test_the_update_endpoint_preserves_the_previous_version_too(client, db, monkeypatch):
    """The service is where preservation happens, but the HTTP path must reach it."""
    from app.core.deps import get_current_expert_user

    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "http")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=2))
    app.dependency_overrides[get_current_expert_user] = lambda: expert
    try:
        response = client.put(
            f"/api/v1/expert/predictions/{prediction.id}",
            json={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1,
                  "reasoning": "corrected over HTTP"},
        )
    finally:
        app.dependency_overrides.pop(get_current_expert_user, None)

    assert response.status_code == 200, response.text
    assert response.json()["home_win_prob"] == pytest.approx(0.7)
    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)


# ----------------------------------------------------------------------------- brief on the payloads
def test_the_detail_payload_carries_the_full_brief_and_the_list_carries_the_compact_one(client, db):
    """B1: the brief rides on the detail endpoint; the list gets the compact form, which is built
    from values the list loop already holds and so costs no query per match."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "brief")
    _publish(db, match, expert, datetime.utcnow())

    detail = _detail(client, match)
    day = FUTURE_KICKOFF.date().isoformat()
    listing = client.get(f"/api/v1/matches?date={day}&refresh=false")

    assert listing.status_code == 200, listing.text
    assert detail["brief"]["markets"][0]["key"] == "match_result"
    assert detail["brief_compact"]["headline"] == detail["brief"]["headline"]
    rows = [row for row in listing.json()["matches"] if row["id"] == str(match.id)]
    assert rows and "brief_compact" in rows[0]
    assert "brief" not in rows[0], "the list payload must stay compact"


def test_the_list_payload_costs_no_extra_query_per_match(client, db):
    """Measured, as B1 asks: adding matches must not add queries proportionally."""
    expert = _expert(db)
    day = (FUTURE_KICKOFF + timedelta(days=1)).date().isoformat()
    kickoff = FUTURE_KICKOFF + timedelta(days=1)
    first = _match(db, kickoff, "count1")
    _publish(db, first, expert, datetime.utcnow())
    db.commit()

    from sqlalchemy import event

    def count_queries(url: str) -> int:
        counter = {"n": 0}

        def before(conn, cursor, statement, parameters, context, executemany):
            counter["n"] += 1

        event.listen(db.get_bind(), "before_cursor_execute", before)
        try:
            assert client.get(url).status_code == 200
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", before)
        return counter["n"]

    one_match = count_queries(f"/api/v1/matches?date={day}&refresh=false")
    second = _match(db, kickoff + timedelta(hours=1), "count2")
    _publish(db, second, expert, datetime.utcnow())
    db.commit()
    two_matches = count_queries(f"/api/v1/matches?date={day}&refresh=false")

    # One more match adds only its own forecast lookup, which existed before the brief did.
    assert two_matches - one_match <= 1, f"{one_match} -> {two_matches} queries"


# ----------------------------------------------------------------------------- what an edit changed
#
# A reader was told what changed by `changes_summary`, the audit text written at edit time: raw
# column names and Python reprs ("btts_yes_prob 0.6 -> 0.4", "confidence_score 0.0 -> None"),
# served verbatim and so untranslatable. `changes` is the same diff, structured, computed when the
# revision is served from the two snapshots the row already stores. The audit text itself is left
# exactly as it was (it is pinned above) and stays in the payload.
def _btts_edit(db, prediction: Prediction, expert: User, yes: float, no: float) -> None:
    """An edit that names only the BTTS pair beside the 1X2 the schema always requires, unchanged."""
    ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=yes, btts_no_prob=no),
        expert)


def test_a_btts_only_edit_keeps_every_market_in_the_revision_and_lists_only_the_btts_changes(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "bttsonly")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=4),
                          btts_yes_prob=0.6, btts_no_prob=0.4,
                          total_goals_over_25_prob=0.55, total_goals_under_25_prob=0.45)

    _btts_edit(db, prediction, expert, yes=0.4, no=0.6)

    revision = _detail(client, match)["expert_prediction_revisions"][0]
    values = revision["values"]
    # The earlier version is carried whole: every market, including the ones the edit left alone
    # and the one that was never published (3.5, null on both sides, not absent).
    assert set(REVISION_VALUE_FIELDS) <= set(values)
    assert values["btts_yes_prob"] == pytest.approx(0.6) and values["btts_no_prob"] == pytest.approx(0.4)
    assert values["total_goals_over_25_prob"] == pytest.approx(0.55)
    assert values["total_goals_under_25_prob"] == pytest.approx(0.45)
    assert values["total_goals_over_35_prob"] is None and values["total_goals_under_35_prob"] is None
    assert values["confidence_score"] == pytest.approx(0.8)
    # ...and the change list names exactly the two BTTS sides, from and to, nothing else.
    assert revision["changes"] == [
        {"field": "btts_yes_prob", "from": 0.6, "to": 0.4},
        {"field": "btts_no_prob", "from": 0.4, "to": 0.6},
    ]
    # The audit text is still served, unchanged in form.
    assert revision["changes_summary"] == "btts_yes_prob 0.6 -> 0.4; btts_no_prob 0.4 -> 0.6"


def test_a_conviction_moved_between_zero_and_null_is_a_change_in_both_directions(client, db):
    """0 is a claim ("I rate this at nothing"); null is the absence of one. Neither is the other."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "zeronull")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=4), confidence_score=0.0)

    _edit(db, prediction, expert, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
          confidence_score=None)                                   # 0 -> withdrawn
    _edit(db, prediction, expert, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
          confidence_score=0.0)                                    # withdrawn -> 0

    first, second = _detail(client, match)["expert_prediction_revisions"]
    assert first["values"]["confidence_score"] == 0.0 and first["values"]["confidence_score"] is not None
    assert first["changes"] == [{"field": "confidence_score", "from": 0.0, "to": None}]
    assert second["values"]["confidence_score"] is None
    assert second["changes"] == [{"field": "confidence_score", "from": None, "to": 0.0}]


def test_reasoning_and_key_factors_are_named_as_changed_without_their_text(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "textual")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=4))

    _edit(db, prediction, expert, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
          reasoning="second view", key_factors={"injuries": "none"})

    revision = _detail(client, match)["expert_prediction_revisions"][0]
    assert revision["changes"] == [{"field": "reasoning"}, {"field": "key_factors"}]


# ----------------------------------------------------------------------------- the kickoff boundary
@pytest.mark.parametrize("kickoff_offset,after", [
    (timedelta(microseconds=-1), True),   # kickoff a hair before the edit
    (timedelta(0), True),                 # the edit AT kickoff: after kickoff, as settlement reads it
    (timedelta(microseconds=1), False),   # kickoff a hair after the edit
])
def test_edited_after_kickoff_uses_settlements_boundary(client, db, kickoff_offset, after):
    """Readers and settlement must agree about the same edit.

    Settlement restores the prematch view from the first revision made AT or after kickoff, so an
    edit at the exact instant is a post-kickoff edit there. The reader's flag used ``>`` and called
    that same edit prematch.
    """
    expert = _expert(db)
    match = _match(db, PAST_KICKOFF, "boundary", status=MatchStatus.LIVE)
    prediction = _publish(db, match, expert, PAST_KICKOFF - timedelta(hours=6))
    _edit(db, prediction, expert, home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15)
    revision = _revision_rows(db, prediction)[0]
    match.match_date = revision.created_at + kickoff_offset
    db.flush()

    served = _detail(client, match)["expert_prediction_revisions"][0]
    assert served["edited_after_kickoff"] is after

    _markets, refusal, provenance = S.prematch_expert_view(prediction, [revision], match.match_date)
    assert refusal is None
    assert provenance.startswith("restored from revision") is after, provenance


@pytest.mark.parametrize("published_offset,late", [
    (timedelta(hours=-2), False),
    (timedelta(microseconds=-1), False),
    (timedelta(0), True),                 # published AT kickoff is not prematch evidence
    (timedelta(minutes=30), True),
])
def test_published_after_kickoff_is_settlements_prematch_rule(client, db, published_offset, late):
    expert = _expert(db)
    kickoff = LATE_KICKOFF
    match = _match(db, kickoff, "late", status=MatchStatus.FINISHED)
    prediction = _publish(db, match, expert, kickoff + published_offset)

    detail = _detail(client, match)
    assert detail["expert_predictions"][0]["published_after_kickoff"] is late
    assert detail["expert_prediction"]["published_after_kickoff"] is late
    listing = client.get(f"/api/v1/matches?date={kickoff.date().isoformat()}&refresh=false")
    assert listing.status_code == 200, listing.text
    row = next(r for r in listing.json()["matches"] if r["id"] == str(match.id))
    assert row["expert_prediction"]["published_after_kickoff"] is late

    # Cross-checked against settlement itself, so the reader's flag cannot drift from the rule.
    assert S.stood_at_kickoff(prediction, kickoff) is (not late)
    _markets, refusal, _provenance = S.prematch_expert_view(prediction, [], kickoff)
    assert (refusal == "published at or after kickoff") is late
    if late:
        assert S.not_prematch_reason(prediction, kickoff) == S.NOT_PREMATCH_EVIDENCE_REASON


def test_published_after_kickoff_is_null_when_either_time_is_unknown(client, db):
    """Unknown is not "before kickoff": a stored False would assert a prematch publication."""
    expert = _expert(db)
    match = _match(db, LATE_KICKOFF, "undated", status=MatchStatus.FINISHED)
    undated = _publish(db, match, expert, None)

    assert _detail(client, match)["expert_predictions"][0]["published_after_kickoff"] is None
    assert S.not_prematch_reason(undated, match.match_date) == S.NO_PUBLICATION_TIME_REASON

    dated = _publish(db, match, expert, LATE_KICKOFF - timedelta(hours=1))
    assert serialize_expert_prediction(dated, kickoff=None)["published_after_kickoff"] is None
    assert serialize_expert_prediction(dated, kickoff=LATE_KICKOFF)["published_after_kickoff"] is False


# ----------------------------------------------------------------------------- withdrawn, then put back
#: Another played fixture on a day of its own, for the withdraw-and-republish cases.
WITHDRAWN_KICKOFF = (datetime.utcnow() - timedelta(days=11)).replace(hour=15, minute=0, second=0, microsecond=0)


def _toggle_at(db, monkeypatch, prediction: Prediction, expert: User, at: datetime) -> None:
    """Run the real publish toggle as though it were ``at``: it stamps its own time with utcnow."""
    class _At(datetime):
        @classmethod
        def utcnow(cls):
            return at

    monkeypatch.setattr("app.services.expert_prediction.datetime", _At)
    try:
        ExpertPredictionService(db).toggle_publish_status(str(prediction.id), expert)
        db.flush()
    finally:
        monkeypatch.setattr("app.services.expert_prediction.datetime", datetime)


def _served_rows(client, match: Match) -> list:
    """Every public payload of this match's expert prediction: detail (both shapes) and the list."""
    detail = _detail(client, match)
    listing = client.get(f"/api/v1/matches?date={match.match_date.date().isoformat()}&refresh=false")
    assert listing.status_code == 200, listing.text
    listed = next(r for r in listing.json()["matches"] if r["id"] == str(match.id))
    return [*detail["expert_predictions"], detail["expert_prediction"], listed["expert_prediction"]]


def test_withdrawn_before_kickoff_and_republished_after_is_served_as_not_scored(client, db, monkeypatch):
    """Published at K-3h, unpublished at K-1h, put back at K+30min: readers saw nothing at kickoff.

    Settlement does not score it (the prematch withdrawal is frozen in ``unpublished_at``), yet it
    was served with its pre-kickoff ``published_at`` and ``published_after_kickoff: false`` - which
    reads as an ordinary, scored prematch prediction. ``withdrawn_before_kickoff`` says what
    settlement says, from settlement's own predicate.
    """
    expert = _expert(db)
    kickoff = WITHDRAWN_KICKOFF
    match = _match(db, kickoff, "withdrawn", status=MatchStatus.FINISHED)
    prediction = _publish(db, match, expert, kickoff - timedelta(hours=3))

    _toggle_at(db, monkeypatch, prediction, expert, kickoff - timedelta(hours=1))      # unpublish
    assert prediction.status == PredictionStatus.ARCHIVED
    _toggle_at(db, monkeypatch, prediction, expert, kickoff + timedelta(minutes=30))   # republish
    assert prediction.status == PredictionStatus.PUBLISHED
    assert prediction.published_at == kickoff - timedelta(hours=3), "published_at is never restamped"
    assert prediction.unpublished_at == kickoff - timedelta(hours=1), "the prematch withdrawal is frozen"

    rows = _served_rows(client, match)
    for row in rows:
        assert row["id"] == str(prediction.id)
        assert row["published_after_kickoff"] is False, "its publication time is before kickoff"
        assert row["withdrawn_before_kickoff"] is True, row

    # Settlement agrees, and leaves it out of the measured record.
    assert S.withdrawn_before_kickoff(prediction, kickoff) is True
    assert S.stood_at_kickoff(prediction, kickoff) is False
    assert S.not_prematch_reason(prediction, kickoff) == S.NOT_STANDING_REASON
    assert prediction.id not in {row.id for row in S.candidate_predictions(db, [match])}


@pytest.mark.parametrize("label,published,toggles,expected", [
    # (published offset, [toggle offsets], (published_after_kickoff, withdrawn_before_kickoff))
    ("never-withdrawn", timedelta(hours=-2), [], (False, False)),
    ("put-back-before-kickoff", timedelta(hours=-3), [timedelta(hours=-2), timedelta(hours=-1)], (False, False)),
    ("withdrawn-after-kickoff", timedelta(hours=-3), [timedelta(hours=1), timedelta(hours=2)], (False, False)),
    ("withdrawn-before-put-back-after", timedelta(hours=-3), [timedelta(hours=-1), timedelta(minutes=30)], (False, True)),
    ("withdrawn-at-kickoff", timedelta(hours=-3), [timedelta(0), timedelta(hours=1)], (False, False)),
    ("published-after-kickoff", timedelta(minutes=10), [], (True, False)),
])
def test_the_public_flags_say_not_scored_exactly_when_settlement_does(client, db, monkeypatch,
                                                                     label, published, toggles, expected):
    """For every served row: (published_after_kickoff or withdrawn_before_kickoff) == not stood_at_kickoff."""
    expert = _expert(db)
    kickoff = WITHDRAWN_KICKOFF
    match = _match(db, kickoff, label, status=MatchStatus.FINISHED)
    prediction = _publish(db, match, expert, kickoff + published)
    for offset in toggles:
        _toggle_at(db, monkeypatch, prediction, expert, kickoff + offset)
    assert prediction.status == PredictionStatus.PUBLISHED

    stood = S.stood_at_kickoff(prediction, kickoff)
    for row in _served_rows(client, match):
        flags = (row["published_after_kickoff"], row["withdrawn_before_kickoff"])
        assert flags == expected, (label, row)
        assert (flags[0] or flags[1]) is (not stood), (label, flags, stood)


def test_withdrawn_before_kickoff_is_null_when_the_kickoff_is_unknown(db):
    """Unknown is not "kept standing": a stored False would assert it stood at kickoff."""
    expert = _expert(db)
    match = _match(db, WITHDRAWN_KICKOFF, "nokick", status=MatchStatus.FINISHED)
    prediction = _publish(db, match, expert, WITHDRAWN_KICKOFF - timedelta(hours=3))
    prediction.unpublished_at = WITHDRAWN_KICKOFF - timedelta(hours=1)
    db.flush()

    assert serialize_expert_prediction(prediction, kickoff=None)["withdrawn_before_kickoff"] is None
    assert serialize_expert_prediction(prediction, kickoff=WITHDRAWN_KICKOFF)["withdrawn_before_kickoff"] is True


# ----------------------------------------------------------------------------- the public author
def _named_expert(db, label: str) -> User:
    """An expert whose private details are distinctive strings, so their absence can be asserted."""
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"private-{label}-{suffix}@test.local",
                username=f"public_{label}_{suffix}", first_name=f"Firstname{label}{suffix}",
                last_name=f"Lastname{label}{suffix}", avatar_url=f"https://example.invalid/{label}{suffix}.png",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _assert_private_details_absent(text_body: str, *users: User) -> None:
    for user in users:
        for private in (user.email, user.first_name, user.last_name, user.avatar_url):
            assert private not in text_body, f"{private!r} reached a public payload"


def test_each_public_expert_prediction_names_its_author_by_username_only(client, db):
    first, second = _named_expert(db, "one"), _named_expert(db, "two")
    match = _match(db, FUTURE_KICKOFF + timedelta(days=2), "author")
    mine = _publish(db, match, first, datetime.utcnow() - timedelta(hours=3))
    theirs = _publish(db, match, second, datetime.utcnow() - timedelta(hours=2))

    response = client.get(f"/api/v1/matches/{match.id}")
    assert response.status_code == 200, response.text
    detail = response.json()
    authors = {row["id"]: row["author"] for row in detail["expert_predictions"]}
    assert authors == {
        str(mine.id): {"id": str(first.id), "username": first.username},
        str(theirs.id): {"id": str(second.id), "username": second.username},
    }
    assert detail["expert_prediction"]["author"]["username"] in {first.username, second.username}
    _assert_private_details_absent(response.text, first, second)

    listing = client.get(f"/api/v1/matches?date={match.match_date.date().isoformat()}&refresh=false")
    assert listing.status_code == 200, listing.text
    row = next(r for r in listing.json()["matches"] if r["id"] == str(match.id))
    assert row["expert_prediction"]["author"]["username"] in {first.username, second.username}
    _assert_private_details_absent(listing.text, first, second)


def test_an_author_with_a_blank_username_is_served_without_a_name_and_never_by_email(client, db):
    expert = _named_expert(db, "blank")
    expert.username = "   "
    match = _match(db, FUTURE_KICKOFF + timedelta(days=2), "blankauthor")
    _publish(db, match, expert, datetime.utcnow() - timedelta(hours=3))
    db.flush()

    response = client.get(f"/api/v1/matches/{match.id}")
    assert response.status_code == 200, response.text
    assert response.json()["expert_predictions"][0]["author"] == {"id": str(expert.id), "username": None}
    _assert_private_details_absent(response.text, expert)


def _count_user_queries(db, client, url: str) -> int:
    from sqlalchemy import event

    seen = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if "users.users" in statement:
            seen.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", before)
    try:
        assert client.get(url).status_code == 200
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", before)
    return len(seen)


def test_the_authors_cost_one_batched_query_per_request(client, db, monkeypatch):
    """Two matches by two experts, and two experts on one match: one users query either way.

    The measured-record summary the brief carries is replaced by a fixed one here, so the only
    reader of the users table left in the request is the author lookup being counted.
    """
    from app.services.match_brief import unknown_scoring_summary
    monkeypatch.setattr("app.api.v1.endpoints.matches.current_scoring_summary",
                        lambda db=None: unknown_scoring_summary("not measured in this test"))
    first, second = _named_expert(db, "qa"), _named_expert(db, "qb")
    kickoff = FUTURE_KICKOFF + timedelta(days=3)
    one = _match(db, kickoff, "batch1")
    two = _match(db, kickoff + timedelta(hours=1), "batch2")
    _publish(db, one, first, datetime.utcnow() - timedelta(hours=3))
    _publish(db, two, second, datetime.utcnow() - timedelta(hours=3))
    _publish(db, one, second, datetime.utcnow() - timedelta(hours=2))
    db.commit()

    assert _count_user_queries(db, client, f"/api/v1/matches?date={kickoff.date().isoformat()}&refresh=false") == 1
    assert _count_user_queries(db, client, f"/api/v1/matches/{one.id}") == 1
