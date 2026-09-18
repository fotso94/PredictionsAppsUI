"""
Match registry: persists provider fixtures as internal matches/teams/leagues and keeps the
provider-id links (`provider_entity_refs`) that make records stable across provider changes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import League, Match, MatchResult, MatchStatus, Team
from app.models.provider_data import ProviderEntityRef
from app.services import match_matching
from app.services.providers import competitions as comps
from app.services.providers.base import (
    STATUS_CANCELLED, STATUS_FINISHED, STATUS_HALFTIME, STATUS_LIVE, STATUS_POSTPONED,
    ProviderCompetition, ProviderFixture, ProviderTeam,
)

logger = logging.getLogger(__name__)

CANONICAL_PROVIDER = "canonical"

STATUS_TO_ENUM = {
    STATUS_LIVE: MatchStatus.LIVE,
    STATUS_HALFTIME: MatchStatus.LIVE,
    STATUS_FINISHED: MatchStatus.FINISHED,
    STATUS_POSTPONED: MatchStatus.POSTPONED,
    STATUS_CANCELLED: MatchStatus.CANCELLED,
}


def _naive_utc(dt: datetime) -> datetime:
    """Match.match_date is a naive column; store UTC wall time."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _aware_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class MatchRegistry:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ refs
    def get_ref(self, entity_type: str, provider: str, external_id: str) -> Optional[ProviderEntityRef]:
        if external_id in (None, "", "None"):
            return None
        return self.db.query(ProviderEntityRef).filter(
            ProviderEntityRef.entity_type == entity_type,
            ProviderEntityRef.provider == provider,
            ProviderEntityRef.external_id == str(external_id),
        ).first()

    def refs_for(self, entity_type: str, entity_id: uuid.UUID) -> List[ProviderEntityRef]:
        return self.db.query(ProviderEntityRef).filter(
            ProviderEntityRef.entity_type == entity_type, ProviderEntityRef.entity_id == entity_id
        ).all()

    def set_ref(self, entity_type: str, entity_id: uuid.UUID, provider: str, external_id: str,
                confidence: str = "exact", matched_by: str = "provider_id", metadata: Optional[dict] = None) -> ProviderEntityRef:
        ref = self.get_ref(entity_type, provider, external_id)
        if ref is None:
            ref = ProviderEntityRef(id=uuid.uuid4(), entity_type=entity_type, entity_id=entity_id, provider=provider,
                                    external_id=str(external_id), match_confidence=confidence, matched_by=matched_by,
                                    ref_metadata=metadata or {})
            self.db.add(ref)
        else:
            ref.entity_id = entity_id
            ref.match_confidence = confidence
            ref.matched_by = matched_by
            if metadata:
                ref.ref_metadata = metadata
        self.db.flush()
        return ref

    # ------------------------------------------------------------------ leagues
    def league_for_key(self, key: str) -> Optional[League]:
        ref = self.get_ref("league", CANONICAL_PROVIDER, key)
        if ref:
            return self.db.query(League).filter(League.id == ref.entity_id).first()
        return None

    def ensure_canonical_league(self, key: str) -> League:
        league = self.league_for_key(key)
        if league:
            return league
        canonical = comps.get(key)
        league = League(id=uuid.uuid4(), name=canonical.name, display_name=canonical.name, country=canonical.country,
                        country_code=canonical.country_code, external_api_id=f"canonical:{key}",
                        external_api_source=CANONICAL_PROVIDER, is_active=True,
                        league_metadata={"canonical_key": key, "is_cup": canonical.is_cup})
        self.db.add(league)
        self.db.flush()
        self.set_ref("league", league.id, CANONICAL_PROVIDER, key, confidence="manual", matched_by="canonical_key")
        return league

    def upsert_league(self, comp: ProviderCompetition) -> League:
        ref = self.get_ref("league", comp.provider, comp.external_id)
        if ref:
            league = self.db.query(League).filter(League.id == ref.entity_id).first()
            if league:
                if comp.logo and not league.logo_url:
                    league.logo_url = comp.logo
                return league
        if comp.key:
            league = self.ensure_canonical_league(comp.key)
        else:
            league = League(id=uuid.uuid4(), name=comp.name or "Unknown", display_name=comp.name or "Unknown",
                            country=comp.country or "Unknown", country_code=comp.country_code,
                            external_api_id=f"{comp.provider}:{comp.external_id}", external_api_source=comp.provider,
                            is_active=True, league_metadata={})
            self.db.add(league)
            self.db.flush()
        if comp.logo and not league.logo_url:
            league.logo_url = comp.logo
        self.set_ref("league", league.id, comp.provider, comp.external_id, confidence="exact", matched_by="provider_id",
                     metadata={"name": comp.name, "country": comp.country})
        return league

    # ------------------------------------------------------------------ teams
    def find_team_by_name(self, name: str, country: Optional[str] = None) -> Optional[Team]:
        normalized = match_matching.normalize_team_name(name)
        if not normalized:
            return None
        first_token = normalized.split(" ")[0]
        query = self.db.query(Team).filter(Team.name.ilike(f"%{first_token}%"))
        for team in query.limit(50).all():
            if match_matching.team_names_match(team.name, name) and (not country or not team.country or team.country == country
                                                                     or team.country == "Unknown"):
                return team
        return None

    def upsert_team(self, team: ProviderTeam, country: Optional[str] = None) -> Team:
        ref = self.get_ref("team", team.provider, team.external_id)
        if ref:
            existing = self.db.query(Team).filter(Team.id == ref.entity_id).first()
            if existing:
                if team.logo and not existing.logo_url:
                    existing.logo_url = team.logo
                return existing
        existing = self.find_team_by_name(team.name, country or team.country)
        matched_by = "name"
        if existing is None:
            existing = Team(id=uuid.uuid4(), name=team.name, short_name=(team.short_name or team.name)[:50],
                            country=country or team.country or "Unknown", logo_url=team.logo,
                            external_api_id=f"{team.provider}:{team.external_id}", external_api_source=team.provider,
                            is_active=True)
            self.db.add(existing)
            self.db.flush()
            matched_by = "provider_id"
        elif team.logo and not existing.logo_url:
            existing.logo_url = team.logo
        self.set_ref("team", existing.id, team.provider, team.external_id, confidence="exact", matched_by=matched_by,
                     metadata={"name": team.name})
        return existing

    # ------------------------------------------------------------------ matches
    def match_by_ref(self, provider: str, external_id: str) -> Optional[Match]:
        ref = self.get_ref("match", provider, external_id)
        if ref:
            return self.db.query(Match).filter(Match.id == ref.entity_id).first()
        return None

    def candidates_for(self, league_id: Optional[uuid.UUID], kickoff_utc: datetime,
                       window: timedelta = timedelta(hours=36), competition_key: Optional[str] = None) -> List[match_matching.MatchCandidate]:
        start, end = _naive_utc(kickoff_utc - window), _naive_utc(kickoff_utc + window)
        query = self.db.query(Match).filter(Match.match_date >= start, Match.match_date <= end)
        if league_id is not None:
            query = query.filter(Match.league_id == league_id)
        candidates = []
        for m in query.all():
            home = self.db.query(Team).filter(Team.id == m.home_team_id).first()
            away = self.db.query(Team).filter(Team.id == m.away_team_id).first()
            if not home or not away:
                continue
            candidates.append(match_matching.MatchCandidate(str(m.id), home.name, away.name, _aware_utc(m.match_date), competition_key))
        return candidates

    def upsert_fixture(self, fixture: ProviderFixture) -> Match:
        league = self.upsert_league(fixture.competition)
        home = self.upsert_team(fixture.home, fixture.competition.country)
        away = self.upsert_team(fixture.away, fixture.competition.country)

        match = self.match_by_ref(fixture.provider, fixture.external_id)
        matched_by, confidence = "provider_id", "exact"
        if match is None:
            decision = match_matching.find_match(fixture.home.name, fixture.away.name, fixture.kickoff_utc,
                                                 fixture.competition.key,
                                                 self.candidates_for(league.id, fixture.kickoff_utc,
                                                                     competition_key=fixture.competition.key))
            if decision.attached:
                match = self.db.query(Match).filter(Match.id == uuid.UUID(decision.match_id)).first()
                matched_by, confidence = "name_kickoff", decision.confidence
            elif decision.confidence == "ambiguous":
                logger.warning("Fixture %s:%s (%s vs %s) is ambiguous against %s; creating a new match record",
                               fixture.provider, fixture.external_id, fixture.home.name, fixture.away.name, decision.candidate_ids)
        if match is None:
            match = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                          match_date=_naive_utc(fixture.kickoff_utc), status=MatchStatus.SCHEDULED,
                          external_api_id=f"{fixture.provider}:{fixture.external_id}", external_api_source=fixture.provider,
                          match_metadata={})
            self.db.add(match)
            self.db.flush()
        self._apply_fixture(match, fixture, home, away, league)
        self.set_ref("match", match.id, fixture.provider, fixture.external_id, confidence=confidence, matched_by=matched_by,
                     metadata={"home": fixture.home.name, "away": fixture.away.name, "kickoff_utc": fixture.kickoff_utc.isoformat()})
        return match

    def _apply_fixture(self, match: Match, fixture: ProviderFixture, home: Team, away: Team, league: League) -> None:
        # Only the provider that owns the match record (or a live/finished update) moves the kickoff
        match.match_date = _naive_utc(fixture.kickoff_utc)
        match.home_team_id = home.id
        match.away_team_id = away.id
        match.league_id = league.id
        match.venue = fixture.venue or match.venue
        match.round = fixture.round or match.round
        if fixture.competition.season_name:
            match.season = fixture.competition.season_name[:20]
        match.status = STATUS_TO_ENUM.get(fixture.status, MatchStatus.SCHEDULED)
        meta = dict(match.match_metadata or {})
        meta.update({
            "provider": fixture.provider,
            "provider_status": fixture.status,
            "minute": fixture.minute,
            "home_score": fixture.home_score,
            "away_score": fixture.away_score,
            "ht_home_score": fixture.ht_home_score,
            "ht_away_score": fixture.ht_away_score,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        })
        match.match_metadata = meta
        if fixture.status == STATUS_FINISHED and fixture.home_score is not None and fixture.away_score is not None:
            result = self.db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
            outcome = "H" if fixture.home_score > fixture.away_score else "A" if fixture.away_score > fixture.home_score else "D"
            if result is None:
                result = MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=fixture.home_score, away_score=fixture.away_score,
                                     home_score_ht=fixture.ht_home_score, away_score_ht=fixture.ht_away_score, result=outcome,
                                     result_metadata={"provider": fixture.provider})
                self.db.add(result)
            else:
                result.home_score, result.away_score, result.result = fixture.home_score, fixture.away_score, outcome
                result.home_score_ht, result.away_score_ht = fixture.ht_home_score, fixture.ht_away_score
        self.db.flush()

    # ------------------------------------------------------------------ queries
    def matches_for_day(self, day: date, league_ids: Optional[Iterable[uuid.UUID]] = None) -> List[Match]:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        query = self.db.query(Match).filter(Match.match_date >= start, Match.match_date < end)
        if league_ids is not None:
            query = query.filter(Match.league_id.in_(list(league_ids)))
        return query.order_by(Match.match_date.asc()).all()

    def matches_between(self, start: datetime, end: datetime, league_ids: Optional[Iterable[uuid.UUID]] = None) -> List[Match]:
        query = self.db.query(Match).filter(Match.match_date >= _naive_utc(start), Match.match_date < _naive_utc(end))
        if league_ids is not None:
            query = query.filter(Match.league_id.in_(list(league_ids)))
        return query.order_by(Match.match_date.asc()).all()

    def resolve_match_id(self, raw: str) -> Optional[uuid.UUID]:
        """
        Resolve a client-supplied match identifier: internal UUID, any provider's fixture id, or a
        legacy `external_api_id`. Returns None when nothing matches (the caller decides what to do).
        """
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            candidate = uuid.UUID(raw)
            if self.db.query(Match.id).filter(Match.id == candidate).first():
                return candidate
        except ValueError:
            pass
        # "provider:id" pins the provider; a bare id is looked up across providers
        provider, external_id = (raw.split(":", 1) if ":" in raw else (None, raw))
        query = self.db.query(ProviderEntityRef).filter(
            ProviderEntityRef.entity_type == "match", ProviderEntityRef.external_id == external_id)
        if provider:
            query = query.filter(ProviderEntityRef.provider == provider)
        refs = query.all()
        targets = {r.entity_id for r in refs}
        if len(targets) == 1:
            return refs[0].entity_id
        if len(targets) > 1:
            # The same bare id exists at several providers and they point to different fixtures: identical
            # numeric ids never identify the same fixture, so prefer the active provider or refuse to guess.
            active = [r for r in refs if r.provider == settings.DATA_PROVIDER]
            if active:
                return active[0].entity_id
            logger.warning("Match id %s is ambiguous across providers (%s); not resolved", raw, sorted(targets))
            return None
        legacy = self.db.query(Match).filter(or_(Match.external_api_id == raw,
                                                 Match.external_api_id == f"{settings.DATA_PROVIDER}:{external_id}")).first()
        if legacy:
            return legacy.id
        return None

    def team_names(self, matches: Iterable[Match]) -> Dict[uuid.UUID, Team]:
        ids = set()
        for m in matches:
            ids.add(m.home_team_id)
            ids.add(m.away_team_id)
        if not ids:
            return {}
        return {t.id: t for t in self.db.query(Team).filter(Team.id.in_(list(ids))).all()}

    def leagues_by_id(self, matches: Iterable[Match]) -> Dict[uuid.UUID, League]:
        ids = {m.league_id for m in matches}
        if not ids:
            return {}
        return {l.id: l for l in self.db.query(League).filter(League.id.in_(list(ids))).all()}
