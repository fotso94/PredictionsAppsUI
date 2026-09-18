"""
Legacy match recovery on a GENUINELY pre-Phase-1 row (review finding B10).

`tests/services/test_match_identity.py` seeds its "legacy" matches through
`MatchRegistry.ensure_canonical_league`, so every one of them sits in a league that already carries
`league_metadata["canonical_key"]` and a `canonical` provider_entity_ref. That is Phase-1 state, not
legacy state, and it never exercises the row that actually matters in production: a match written
before `provider_entity_refs` existed, in a league the OLD code path created.

This module builds that state directly with the ORM - no `ensure_canonical_league`, no
`upsert_fixture` - reproducing exactly what `ExpertPredictionService._create_match_from_api_data`
wrote before commit 1f396e4:

    League(name=..., external_api_id="39", external_api_source="api-football")   # league_metadata NULL
    Team(name=..., external_api_id="42", external_api_source="api-football")
    Match(external_api_id="1035049", external_api_source="api-football",         # BARE id, not "provider:id"
          match_metadata={"fetched_from_api": True, "api_status": "NS"})

and no ProviderEntityRef rows at all.

Every case carries a published expert prediction on the legacy match, because losing that prediction
is the damage a missed recovery actually does.

Requires PostgreSQL (same fixture pattern as tests/services/test_provider_switching_db.py). Set
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
from app.models.predictions import (
    League, Match, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import ProviderEntityRef
from app.models.users import AccountStatus, User, UserType
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderCompetition, ProviderFixture, ProviderTeam

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

KICKOFF = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
# The provider that wrote the pre-Phase-1 rows, and the one that reads them now.
OLD_PROVIDER, NEW_PROVIDER = "api-football", "livescore"


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


# --------------------------------------------------------------- pre-Phase-1 seeding (ORM only)
def _unique(prefix: str) -> str:
    """A provider id that cannot collide with another test's row (external_api_id is UNIQUE)."""
    return f"{prefix}{uuid.uuid4().int % 10_000_000}"


def old_league(db, name="Premier League", country="England", external_api_id=None) -> League:
    """
    A league as the pre-registry code wrote it.

    `league_metadata` is left unset on purpose: the old constructor never passed it, so the column is
    NULL - not `{}` - and there is no `canonical` provider_entity_ref pointing at the row. This is
    the shape `canonical_key_for_league` has to cope with.
    """
    row = League(id=uuid.uuid4(), name=name, display_name=name, country=country,
                 external_api_id=external_api_id or _unique("afl-"), external_api_source=OLD_PROVIDER,
                 is_active=True)
    db.add(row)
    db.flush()
    assert row.league_metadata is None
    return row


def old_team(db, name: str, country="England") -> Team:
    row = Team(id=uuid.uuid4(), name=name, short_name=name[:10], country=country,
               external_api_id=_unique("aft-"), external_api_source=OLD_PROVIDER, is_active=True)
    db.add(row)
    db.flush()
    return row


def old_match(db, league: League, home: Team, away: Team, external_api_id: str,
              kickoff=KICKOFF, status=MatchStatus.SCHEDULED) -> Match:
    """A match row as the pre-registry code wrote it: a BARE external id and no provider ref."""
    row = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                match_date=kickoff.replace(tzinfo=None), status=status,
                external_api_id=external_api_id, external_api_source=OLD_PROVIDER,
                match_metadata={"fetched_from_api": True, "api_status": "NS"})
    db.add(row)
    db.flush()
    assert db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_id == row.id).count() == 0
    return row


def legacy_world(db, home_name="Arsenal", away_name="Chelsea", external_api_id="1035049", kickoff=KICKOFF):
    """The complete pre-Phase-1 state for one fixture: legacy league, legacy teams, legacy match."""
    league = old_league(db)
    home, away = old_team(db, home_name), old_team(db, away_name)
    match = old_match(db, league, home, away, external_api_id, kickoff=kickoff)
    return league, home, away, match


# ----------------------------------------------------------------------------- provider input
def _slug(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())[:24]


def new_fixture(external_id: str, home="Arsenal FC", away="Chelsea FC", kickoff=KICKOFF,
                key="premier_league", provider=NEW_PROVIDER) -> ProviderFixture:
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-{key}", name="Premier League",
                               key=key, country="England", country_code="ENG")
    return ProviderFixture(
        provider=provider, external_id=external_id, competition=comp,
        home=ProviderTeam(provider=provider, external_id=f"{provider}-{_slug(home)}", name=home),
        away=ProviderTeam(provider=provider, external_id=f"{provider}-{_slug(away)}", name=away),
        kickoff_utc=kickoff)


# ----------------------------------------------------------------------------- expert prediction
def expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"legacy-{suffix}@test.local", username=f"legacy_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT, account_status=AccountStatus.ACTIVE,
                email_verified=True)
    db.add(user)
    db.flush()
    return user


def publish(db, match: Match) -> Prediction:
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=expert(db).id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                            priority_level=100, reasoning="written before the registry existed")
    db.add(prediction)
    db.flush()
    return prediction


def ref_for(registry, match: Match, provider: str):
    return {r.provider: r for r in registry.refs_for("match", match.id)}.get(provider)


# ----------------------------------------------------------------------------- the premise itself
def test_a_pre_phase1_league_really_carries_no_canonical_key(db, registry):
    """Pins what makes these rows different from the ones test_match_identity seeds."""
    league, _, _, match = legacy_world(db)

    assert league.league_metadata is None
    assert registry.canonical_key_for_league(league.id) is None
    assert registry.league_for_key("premier_league") is None, "no canonical league exists yet"
    assert match.external_api_id == "1035049", "the old code stored a bare provider id, not 'provider:id'"
    assert registry.match_by_ref(OLD_PROVIDER, "1035049") is None, "a pre-registry row has no ref"

    # and the canonical league the new code creates is a DIFFERENT row
    canonical = registry.ensure_canonical_league("premier_league")
    assert canonical.id != league.id
    assert canonical.league_metadata["canonical_key"] == "premier_league"


# ----------------------------------------------------------------------------- B10: recovery
def test_the_same_fixture_recovers_the_pre_phase1_row_and_keeps_the_expert_prediction(db, registry):
    """
    The case that matters: the new provider reuses the old provider's fixture number.

    The row is in a league with no canonical key, so this also covers the specific gap the review
    named - recovery must not depend on the stored league being a canonical one.
    """
    league, home, away, legacy = legacy_world(db, external_api_id="1035049")
    prediction = publish(db, legacy)
    matches_before, predictions_before = db.query(Match).count(), db.query(Prediction).count()

    recovered = registry.upsert_fixture(new_fixture("1035049"))

    assert recovered is not None, "a pre-Phase-1 row must be recovered, not skipped"
    assert recovered.id == legacy.id
    assert db.query(Match).count() == matches_before, "the legacy row must be reused, not duplicated"
    assert registry.refusals == []

    # the expert prediction is still on the same match, untouched
    kept = db.query(Prediction).filter(Prediction.match_id == legacy.id).one()
    assert kept.id == prediction.id and kept.status == PredictionStatus.PUBLISHED
    assert db.query(Prediction).count() == predictions_before

    # the bare id alone cannot say which provider wrote it, so the link is "high", never "exact"
    ref = ref_for(registry, legacy, NEW_PROVIDER)
    assert ref is not None and ref.matched_by == "legacy_external_id" and ref.match_confidence == "high"

    # the recovered row is adopted into the canonical league and keeps its original teams
    db.refresh(recovered)
    assert recovered.league_id != league.id
    assert registry.canonical_key_for_league(recovered.league_id) == "premier_league"
    assert (recovered.home_team_id, recovered.away_team_id) == (home.id, away.id), "no duplicate teams"


def test_the_backfilled_ref_makes_the_second_sync_a_direct_lookup(db, registry):
    league, _, _, legacy = legacy_world(db, external_api_id="1035049")
    prediction = publish(db, legacy)

    assert registry.upsert_fixture(new_fixture("1035049")).id == legacy.id
    db.flush()

    # the ref now answers on its own - no external_api_id scan, no legacy heuristics
    assert registry.match_by_ref(NEW_PROVIDER, "1035049").id == legacy.id

    matches_before = db.query(Match).count()
    again = registry.upsert_fixture(new_fixture("1035049", kickoff=KICKOFF + timedelta(minutes=45)))
    assert again is not None and again.id == legacy.id
    assert db.query(Match).count() == matches_before
    # the second pass records the link honestly as a provider-id lookup
    ref = ref_for(registry, legacy, NEW_PROVIDER)
    assert ref.matched_by == "provider_id" and ref.match_confidence == "exact"
    assert db.query(Prediction).filter(Prediction.match_id == legacy.id).one().id == prediction.id


# ----------------------------------------------------------------------------- B10: refusal
def test_a_different_fixture_with_the_same_number_never_takes_the_legacy_row(db, registry):
    """Provider fixture numbers collide across providers; the teams decide, not the number."""
    league, home, away, legacy = legacy_world(db, home_name="Arsenal", away_name="Chelsea",
                                              external_api_id="1035049")
    prediction = publish(db, legacy)
    matches_before = db.query(Match).count()

    # the new provider's fixture 1035049 is a completely different game
    other = registry.upsert_fixture(new_fixture("1035049", home="Liverpool", away="Everton"))

    assert other is not None and other.id != legacy.id, "the legacy row must not be repurposed"
    assert ref_for(registry, legacy, NEW_PROVIDER) is None, "no link to the wrong fixture"

    # the legacy row is untouched: same teams, same league, same expert prediction
    db.refresh(legacy)
    assert (legacy.home_team_id, legacy.away_team_id) == (home.id, away.id)
    assert legacy.league_id == league.id
    assert legacy.external_api_id == "1035049"
    assert db.query(Prediction).filter(Prediction.match_id == legacy.id).one().id == prediction.id

    # Liverpool vs Everton really is a different fixture, so exactly one row is added for it, and it
    # takes the QUALIFIED id - which cannot collide with the legacy row's bare one
    assert db.query(Match).count() == matches_before + 1
    assert other.external_api_id == f"{NEW_PROVIDER}:1035049"
    assert ref_for(registry, other, NEW_PROVIDER).matched_by == "provider_id"


def test_the_bare_number_tier_can_never_itself_be_ambiguous(db, registry):
    """
    Why `_recover_legacy_match`'s tiers are safe: `matches.external_api_id` is UNIQUE.

    The review's sibling worry - two legacy rows carrying the same number - cannot arise inside the
    bare tier, because the database forbids a second row with the same `external_api_id`. Only the
    third tier (`LIKE '%:<id>'`) can return several rows, and that is the tier whose `len(rows) != 1`
    guard is already exercised. A bare row and a `<other>:<id>` row can coexist, and the bare tier
    then wins; that is the right answer here, since the bare form is the one the pre-registry code
    actually wrote.
    """
    league = old_league(db)
    home, away = old_team(db, "Arsenal"), old_team(db, "Chelsea")
    bare = old_match(db, league, home, away, "1035049")
    qualified = old_match(db, league, home, away, "thesportsdb:1035049",
                          kickoff=KICKOFF + timedelta(minutes=30))
    prediction = publish(db, bare)

    recovered = registry.upsert_fixture(new_fixture("1035049"))

    assert recovered is not None and recovered.id == bare.id
    assert db.query(Prediction).filter(Prediction.match_id == bare.id).one().id == prediction.id
    # the other row is left completely alone - no ref, no adoption into the canonical league
    assert ref_for(registry, qualified, NEW_PROVIDER) is None
    db.refresh(qualified)
    assert qualified.league_id == league.id


def test_a_legacy_row_days_away_is_not_recovered_on_the_number_alone(db, registry):
    """Same number, but the stored kickoff is a week out: that is not evidence of the same fixture."""
    league, home, away, legacy = legacy_world(db, external_api_id="1035049",
                                              kickoff=KICKOFF - timedelta(days=7))
    prediction = publish(db, legacy)

    created = registry.upsert_fixture(new_fixture("1035049"))

    assert created is None or created.id != legacy.id
    assert ref_for(registry, legacy, NEW_PROVIDER) is None
    assert db.query(Prediction).filter(Prediction.match_id == legacy.id).one().id == prediction.id


# ------------------------------------------- B10: the fallback cannot see a non-canonical league
# A provider switch is the whole reason the registry exists, and the new provider does NOT reuse the
# old provider's fixture numbers. `_recover_legacy_match` is then useless (it only ever looks the
# number up), so everything rests on the name/kickoff fallback - and that fallback asks
# `candidates_for(league.id, ...)` with the CANONICAL league the new fixture resolves to, while a
# pre-Phase-1 match sits in the league the old code path created. The row is filtered out before any
# name is compared.

def test_the_name_and_kickoff_fallback_reuses_the_match_when_the_league_is_canonical(db, registry):
    """Control for the gap below: identical scenario, only the stored league differs."""
    canonical = registry.ensure_canonical_league("premier_league")
    home, away = old_team(db, "Arsenal"), old_team(db, "Chelsea")
    stored = old_match(db, canonical, home, away, "1035049")
    prediction = publish(db, stored)
    matches_before = db.query(Match).count()

    # the new provider numbers this fixture 887766, nothing like the old 1035049
    reused = registry.upsert_fixture(new_fixture("887766"))

    assert reused is not None and reused.id == stored.id
    assert db.query(Match).count() == matches_before
    assert db.query(Prediction).filter(Prediction.match_id == stored.id).one().id == prediction.id


def test_a_pre_phase1_match_is_inside_the_lookup_window(db, registry):
    """Rules out the innocent explanation: the row is in range, and its league is a different row."""
    legacy_league_row, _, _, legacy = legacy_world(db, external_api_id="1035049")
    canonical = registry.ensure_canonical_league("premier_league")

    assert legacy.league_id == legacy_league_row.id != canonical.id
    unfiltered = registry.candidates_for(None, KICKOFF)
    assert [c.match_id for c in unfiltered] == [str(legacy.id)]
    # with no canonical key on its league, the candidate carries no competition key either, so
    # find_match's competition gate cannot be what excludes it
    assert unfiltered[0].competition_key is None


def test_the_fallback_is_offered_a_pre_phase1_match(db, registry):
    _, _, _, legacy = legacy_world(db, external_api_id="1035049")
    canonical = registry.ensure_canonical_league("premier_league")

    offered = {c.match_id for c in registry.candidates_for(canonical.id, KICKOFF)}
    assert str(legacy.id) in offered


def test_a_pre_phase1_match_survives_a_provider_change_that_renumbers_the_fixture(db, registry):
    legacy_league_row, home, away, legacy = legacy_world(db, external_api_id="1035049")
    prediction = publish(db, legacy)
    matches_before = db.query(Match).count()

    reused = registry.upsert_fixture(new_fixture("887766"))

    assert reused is not None and reused.id == legacy.id, "a renumbered fixture must find the old row"
    assert db.query(Match).count() == matches_before, "no duplicate match row"
    assert db.query(Prediction).filter(Prediction.match_id == legacy.id).one().id == prediction.id


def test_a_pre_phase1_match_a_week_away_is_reported_not_silently_duplicated(db, registry):
    legacy_league_row, home, away, legacy = legacy_world(db, external_api_id="1035049",
                                                         kickoff=KICKOFF - timedelta(days=7))
    publish(db, legacy)
    matches_before = db.query(Match).count()

    assert registry.upsert_fixture(new_fixture("887766")) is None
    assert db.query(Match).count() == matches_before
    assert registry.refusals[0]["candidates"] == [str(legacy.id)]


# ----------------------------------------------------------------------------- B10: id resolution
def test_resolve_match_id_finds_a_pre_phase1_row_by_its_bare_id(db, registry, monkeypatch):
    """Old deep links carry the bare provider number; they must still reach the match."""
    monkeypatch.setattr(settings, "DATA_PROVIDER", NEW_PROVIDER)
    league, _, _, legacy = legacy_world(db, external_api_id="1035049")
    publish(db, legacy)

    assert registry.resolve_match_id("1035049") == legacy.id
    # the row is repaired on the way: the ref it never had is backfilled from external_api_source
    ref = ref_for(registry, legacy, OLD_PROVIDER)
    assert ref is not None and ref.external_id == "1035049" and ref.matched_by == "legacy_external_id"

    # and the internal UUID keeps working
    assert registry.resolve_match_id(str(legacy.id)) == legacy.id
    assert registry.resolve_match_id("1035050") is None


def test_resolve_match_id_finds_a_pre_phase1_row_by_provider_qualified_id(db, registry, monkeypatch):
    """`api-football:1035049` names the same row as the bare `1035049` - and is strictly MORE specific."""
    monkeypatch.setattr(settings, "DATA_PROVIDER", NEW_PROVIDER)
    league, _, _, legacy = legacy_world(db, external_api_id="1035049")
    publish(db, legacy)

    # Asserted BEFORE any bare lookup: a bare resolution backfills the ref and would then answer the
    # qualified form too (test_a_bare_resolution_makes_the_qualified_form_work_afterwards), which
    # would hide the gap. It must hold whichever provider is active - the stored id is bare, so
    # neither string resolve_match_id compares (`raw`, `f"{DATA_PROVIDER}:{external_id}"`) can hit it.
    for active in (NEW_PROVIDER, OLD_PROVIDER, "gameforecast"):
        monkeypatch.setattr(settings, "DATA_PROVIDER", active)
        assert registry.resolve_match_id(f"{OLD_PROVIDER}:1035049") == legacy.id, active

    # the bare form already works, so the qualified form failing is an inconsistency, not a policy
    assert registry.resolve_match_id("1035049") == legacy.id


def test_a_bare_resolution_makes_the_qualified_form_work_afterwards(db, registry, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PROVIDER", NEW_PROVIDER)
    league, _, _, legacy = legacy_world(db, external_api_id="1035049")

    assert registry.resolve_match_id("1035049") == legacy.id       # backfills the ref
    assert registry.resolve_match_id(f"{OLD_PROVIDER}:1035049") == legacy.id
    assert registry.resolve_match_id(f"{NEW_PROVIDER}:1035049") is None, "the ref names the provider that wrote it"
