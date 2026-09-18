"""
Cross-provider match identity at the registry level.

The rules under test are the owner's, not a heuristic's: a legacy match row is recovered instead of
duplicated, an uncertain fixture is refused instead of guessed, a secondary provider may not move a
kickoff or revive a finished match, and a stored club is found again whatever spelling the next
provider uses.

Requires PostgreSQL (same pattern as tests/services/test_provider_switching_db.py). Set
TEST_DATABASE_URL (default: the docker-compose test database); skipped when unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.predictions import Match, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team
from app.models.users import AccountStatus, User, UserType
from app.services import match_matching
from app.services.match_registry import MatchRegistry
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_SCHEDULED, ProviderCompetition, ProviderFixture, ProviderTeam,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

KICKOFF = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
# the two spellings the production database actually holds for these clubs
GLADBACH_LS, GLADBACH_GF = "Borussia Moenchengladbach", "Borussia Monchengladbach"
KOLN_LS, KOLN_GF = "1. FC Koeln", "FC Cologne"


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


# ----------------------------------------------------------------------------- helpers
def _slug(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())[:24]


def provider_fixture(provider="livescore", external_id="9001", home=GLADBACH_LS, away=KOLN_LS,
                     kickoff=KICKOFF, key="bundesliga", status=STATUS_SCHEDULED, **scores) -> ProviderFixture:
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-{key}", name=key.replace("_", " ").title(),
                               key=key, country="Germany", country_code="GER")
    return ProviderFixture(
        provider=provider, external_id=external_id, competition=comp,
        home=ProviderTeam(provider=provider, external_id=f"{provider}-{_slug(home)}", name=home),
        away=ProviderTeam(provider=provider, external_id=f"{provider}-{_slug(away)}", name=away),
        kickoff_utc=kickoff, status=status, **scores)


def team(db, name: str, country="Germany") -> Team:
    row = Team(id=uuid.uuid4(), name=name, short_name=name[:50], country=country, is_active=True)
    db.add(row)
    db.flush()
    return row


def legacy_match(db, registry, external_api_id: str, home: Team, away: Team, kickoff=KICKOFF,
                 key="bundesliga", status=MatchStatus.SCHEDULED) -> Match:
    """
    A match row as the pre-registry code wrote it: an external_api_id and no provider_entity_ref.

    NOTE (review B10): the row is only half legacy. Its LEAGUE comes from `ensure_canonical_league`,
    so it already carries `league_metadata["canonical_key"]` and a canonical ref - state that only
    exists from Phase 1 onwards. A genuinely pre-Phase-1 match sits in a league the old code path
    created, with no canonical key at all, and that changes the outcome: `candidates_for` filters on
    the canonical league id and never offers such a row to the name/kickoff fallback.
    `tests/services/test_legacy_recovery_db.py` builds that state with the ORM instead and pins the
    difference; keep the two files in step.
    """
    league = registry.ensure_canonical_league(key)
    source = external_api_id.split(":", 1)[0] if ":" in external_api_id else None
    row = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                match_date=kickoff.replace(tzinfo=None), status=status, external_api_id=external_api_id,
                external_api_source=source, match_metadata={})
    db.add(row)
    db.flush()
    assert registry.refs_for("match", row.id) == []
    return row


def expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"identity-{suffix}@test.local", username=f"identity_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT, account_status=AccountStatus.ACTIVE,
                email_verified=True)
    db.add(user)
    db.flush()
    return user


def publish(db, match: Match, user: User) -> Prediction:
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                            priority_level=100, reasoning="expert view")
    db.add(prediction)
    db.flush()
    return prediction


def match_count(db) -> int:
    return db.query(Match).count()


def ref_for(registry, match: Match, provider: str):
    return {r.provider: r for r in registry.refs_for("match", match.id)}.get(provider)


# ----------------------------------------------------------------------------- B1 legacy recovery
def test_legacy_match_is_recovered_instead_of_duplicated(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy = legacy_match(db, registry, "livescore:9001", home, away)
    prediction = publish(db, legacy, expert(db))
    before = match_count(db)

    recovered = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))

    assert recovered is not None and recovered.id == legacy.id
    assert match_count(db) == before, "the legacy row must be reused, not duplicated"
    ref = ref_for(registry, legacy, "livescore")
    assert ref is not None and ref.matched_by == "legacy_external_id" and ref.match_confidence == "exact"
    assert db.query(Prediction).filter(Prediction.match_id == legacy.id).one().id == prediction.id
    # the ref now exists, so the next sync is a direct lookup
    assert registry.match_by_ref("livescore", "9001").id == legacy.id


def test_legacy_bare_external_id_is_recovered(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy = legacy_match(db, registry, "7777", home, away)
    before = match_count(db)

    recovered = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="7777"))

    assert recovered is not None and recovered.id == legacy.id and match_count(db) == before
    assert ref_for(registry, legacy, "livescore").matched_by == "legacy_external_id"


def test_legacy_id_of_another_provider_is_recovered_when_it_is_unique(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy = legacy_match(db, registry, "gameforecast:5150", home, away)
    before = match_count(db)

    recovered = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="5150"))

    assert recovered is not None and recovered.id == legacy.id and match_count(db) == before
    ref = ref_for(registry, legacy, "livescore")
    assert ref.matched_by == "legacy_external_id" and ref.match_confidence == "high"


def test_two_legacy_rows_with_the_same_number_are_never_recovered(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy_match(db, registry, "gameforecast:5150", home, away)
    legacy_match(db, registry, "thesportsdb:5150", home, away)
    before = match_count(db)

    assert registry.upsert_fixture(provider_fixture(provider="livescore", external_id="5150")) is None
    assert match_count(db) == before, "an undecidable fixture writes nothing at all"
    assert len(registry.refusals) == 1 and len(registry.refusals[0]["candidates"]) == 2


def test_legacy_id_pointing_at_different_teams_is_not_recovered(db, registry):
    other_home, other_away = team(db, "Bayern Munich"), team(db, "Borussia Dortmund")
    legacy = legacy_match(db, registry, "livescore:9001", other_home, other_away)
    before = match_count(db)

    created = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))

    assert created is not None and created.id != legacy.id
    assert match_count(db) == before + 1
    assert ref_for(registry, legacy, "livescore") is None
    assert ref_for(registry, created, "livescore").matched_by == "provider_id"


def test_legacy_id_with_a_kickoff_days_away_is_not_recovered(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy = legacy_match(db, registry, "livescore:9001", home, away, kickoff=KICKOFF - timedelta(days=5))
    before = match_count(db)

    # same id, but the stored fixture is five days away: recovery refuses, and the name/kickoff pass
    # then reports a possible reschedule rather than silently creating a second row
    assert registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001")) is None
    assert match_count(db) == before
    assert ref_for(registry, legacy, "livescore") is None
    assert registry.refusals[0]["candidates"] == [str(legacy.id)]


# ----------------------------------------------------------------------------- B4 refusals
def test_two_candidates_in_the_window_are_refused(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    first = legacy_match(db, registry, "gameforecast:1", home, away)
    second = legacy_match(db, registry, "gameforecast:2", home, away, kickoff=KICKOFF + timedelta(hours=1))
    registry.set_ref("match", first.id, "gameforecast", "1")
    registry.set_ref("match", second.id, "gameforecast", "2")
    before = match_count(db)

    assert registry.upsert_fixture(provider_fixture(provider="livescore", external_id="L1")) is None
    assert match_count(db) == before
    assert set(registry.refusals[0]["candidates"]) == {str(first.id), str(second.id)}


def test_home_away_swapped_is_refused(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    stored = legacy_match(db, registry, "gameforecast:1", home, away)
    registry.set_ref("match", stored.id, "gameforecast", "1")
    before = match_count(db)

    swapped = provider_fixture(provider="livescore", external_id="L1", home=KOLN_LS, away=GLADBACH_LS)
    assert registry.upsert_fixture(swapped) is None
    assert match_count(db) == before
    assert "swapped" in registry.refusals[0]["reason"]
    assert ref_for(registry, stored, "livescore") is None


def test_a_refused_fixture_is_reported_with_everything_the_caller_needs(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    stored = legacy_match(db, registry, "gameforecast:1", home, away)
    registry.set_ref("match", stored.id, "gameforecast", "1")

    assert registry.upsert_fixture(provider_fixture(provider="livescore", external_id="L1",
                                                    home=KOLN_LS, away=GLADBACH_LS)) is None
    refusal = registry.refusals[0]
    assert refusal["provider"] == "livescore" and refusal["external_id"] == "L1"
    assert refusal["home"] == KOLN_LS and refusal["away"] == GLADBACH_LS
    assert refusal["competition_key"] == "bundesliga" and refusal["reason"]
    # a sync drains them once and reports the count
    assert registry.take_refusals() == [refusal] and registry.refusals == []


def test_the_ref_records_the_confidence_the_decision_really_produced(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    stored = legacy_match(db, registry, "gameforecast:1", home, away)
    registry.set_ref("match", stored.id, "gameforecast", "1")

    # two hours apart: attached, but "high", never the hardcoded "exact"/"provider_id"
    attached = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="L1",
                                                        kickoff=KICKOFF + timedelta(hours=2)))
    assert attached is not None and attached.id == stored.id
    ref = ref_for(registry, stored, "livescore")
    assert ref.match_confidence == "high" and ref.matched_by == "name_kickoff"


# ----------------------------------------------------------------------------- B5 rescheduling
def test_a_fixture_postponed_by_days_is_not_duplicated(db, registry):
    stored = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))
    before = match_count(db)

    postponed = provider_fixture(provider="gameforecast", external_id="G1", home=GLADBACH_GF, away=KOLN_GF,
                                 kickoff=KICKOFF + timedelta(days=5))
    assert registry.upsert_fixture(postponed) is None
    assert match_count(db) == before, "a postponed fixture must never create a second match row"
    refusal = registry.refusals[0]
    assert refusal["candidates"] == [str(stored.id)] and "rescheduled" in refusal["reason"]


def test_the_owning_provider_still_follows_its_own_postponement(db, registry):
    stored = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))
    moved = provider_fixture(provider="livescore", external_id="9001", kickoff=KICKOFF + timedelta(days=5))

    again = registry.upsert_fixture(moved)
    assert again is not None and again.id == stored.id
    assert again.match_date == (KICKOFF + timedelta(days=5)).replace(tzinfo=None)
    assert registry.refusals == []


# ----------------------------------------------------------------------------- B3 kickoff/status guards
def test_a_secondary_provider_cannot_move_the_kickoff(db, registry):
    stored = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))
    stale = provider_fixture(provider="gameforecast", external_id="G1", home=GLADBACH_GF, away=KOLN_GF,
                             kickoff=KICKOFF + timedelta(hours=2))

    attached = registry.upsert_fixture(stale)
    assert attached is not None and attached.id == stored.id
    assert attached.match_date == KICKOFF.replace(tzinfo=None), "only the owning provider moves a kickoff"


def test_a_finished_match_is_never_sent_back_to_scheduled(db, registry):
    played = provider_fixture(provider="livescore", external_id="9001", status=STATUS_FINISHED,
                              home_score=2, away_score=1)
    stored = registry.upsert_fixture(played)
    assert stored.status == MatchStatus.FINISHED

    stale = provider_fixture(provider="gameforecast", external_id="G1", home=GLADBACH_GF, away=KOLN_GF,
                             status=STATUS_SCHEDULED)
    again = registry.upsert_fixture(stale)
    assert again is not None and again.id == stored.id
    assert again.status == MatchStatus.FINISHED, "a terminal status is monotonic"


def test_the_owning_provider_may_still_correct_a_finished_match(db, registry):
    stored = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001",
                                                      status=STATUS_FINISHED, home_score=2, away_score=1))
    live_again = registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001",
                                                          status=STATUS_FINISHED, home_score=2, away_score=2))
    assert live_again.id == stored.id and live_again.status == MatchStatus.FINISHED
    assert live_again.match_metadata["away_score"] == 2


# ----------------------------------------------------------------------------- B2 team identity
def test_stored_german_spellings_are_found_again(db, registry):
    gladbach = team(db, GLADBACH_LS)   # exactly what the production database holds
    koln = team(db, KOLN_GF)

    assert registry.find_team_by_name("Borussia Mönchengladbach").id == gladbach.id
    assert registry.find_team_by_name(GLADBACH_GF).id == gladbach.id
    assert registry.find_team_by_name("Monchengladbach").id == gladbach.id
    assert registry.find_team_by_name(KOLN_LS).id == koln.id
    assert registry.find_team_by_name("Köln").id == koln.id
    assert registry.find_team_by_name("Bayern Munich") is None


def test_a_provider_switch_does_not_duplicate_a_team(db, registry):
    registry.upsert_fixture(provider_fixture(provider="livescore", external_id="9001"))
    teams_before = db.query(Team).count()

    other = provider_fixture(provider="gameforecast", external_id="G1", home=GLADBACH_GF, away=KOLN_GF)
    attached = registry.upsert_fixture(other)

    assert attached is not None
    assert db.query(Team).count() == teams_before, "the same clubs under another spelling are one team"
    home = db.query(Team).filter(Team.id == attached.home_team_id).one()
    assert match_matching.team_names_match(home.name, GLADBACH_GF)


# ----------------------------------------------------------------------------- B6 id resolution
def test_a_bare_legacy_id_of_an_inactive_provider_resolves_and_backfills(db, registry, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PROVIDER", "livescore")
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy = legacy_match(db, registry, "gameforecast:5150", home, away)

    assert registry.resolve_match_id("5150") == legacy.id
    ref = ref_for(registry, legacy, "gameforecast")
    assert ref is not None and ref.external_id == "5150" and ref.matched_by == "legacy_external_id"
    # the backfilled ref answers the next lookup directly
    assert registry.resolve_match_id("gameforecast:5150") == legacy.id


def test_a_bare_legacy_id_shared_by_two_providers_is_refused(db, registry, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PROVIDER", "livescore")
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    legacy_match(db, registry, "gameforecast:5150", home, away)
    legacy_match(db, registry, "thesportsdb:5150", home, away, kickoff=KICKOFF + timedelta(days=3))

    assert registry.resolve_match_id("5150") is None


def test_an_unknown_id_still_resolves_to_nothing(db, registry):
    assert registry.resolve_match_id("does-not-exist") is None
    assert registry.resolve_match_id("") is None


# ----------------------------------------------------------------------------- B8 competition gate
def test_each_candidate_carries_its_own_competition_key(db, registry):
    home, away = team(db, GLADBACH_GF), team(db, KOLN_GF)
    german = legacy_match(db, registry, "x:1", home, away, key="bundesliga")
    english = legacy_match(db, registry, "x:2", team(db, "Liverpool", "England"),
                           team(db, "Everton", "England"), key="premier_league")

    candidates = {c.match_id: c for c in registry.candidates_for(None, KICKOFF, competition_key="premier_league")}
    assert candidates[str(german.id)].competition_key == "bundesliga"
    assert candidates[str(english.id)].competition_key == "premier_league"

    # and the gate now really excludes the other competition
    decision = match_matching.find_match(GLADBACH_LS, KOLN_LS, KICKOFF, "premier_league", candidates.values())
    assert not decision.attached and decision.confidence == "none"
