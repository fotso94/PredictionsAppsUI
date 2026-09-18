"""
Match registry: persists provider fixtures as internal matches/teams/leagues and keeps the
provider-id links (`provider_entity_refs`) that make records stable across provider changes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func, or_
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

# A match that is over stays over: a stale secondary provider must never drag it back to the calendar.
TERMINAL_STATUSES = (MatchStatus.FINISHED, MatchStatus.CANCELLED)
REGRESSIVE_STATUSES = (MatchStatus.SCHEDULED, MatchStatus.LIVE)


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
        # Fixtures that could not be attributed with certainty; callers count/report them (never guess).
        self.refusals: List[dict] = []
        self._teams_cache: Optional[List[Team]] = None
        self._teams_count: int = -1
        self._league_key_cache: Dict[uuid.UUID, Optional[str]] = {}

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
    def _team_pool(self) -> List[Team]:
        """Stored teams, memoised per registry instance and refreshed whenever the table grows."""
        total = self.db.query(func.count(Team.id)).scalar() or 0
        if self._teams_cache is None or self._teams_count != total:
            self._teams_cache = self.db.query(Team).all()
            self._teams_count = total
        return self._teams_cache

    def find_team_by_name(self, name: str, country: Optional[str] = None) -> Optional[Team]:
        """
        Find a stored team by name, comparing NORMALISED names in Python.

        The normalised form is not a substring of the stored raw name -- "Borussia Moenchengladbach"
        does not contain "monchengladbach" and "FC Cologne" does not contain "koln" -- so a normalised
        token must never be used as a SQL LIKE pattern. Doing that made every provider switch insert a
        duplicate Team row for exactly those clubs.
        """
        normalized = match_matching.normalize_team_name(name)
        if not normalized:
            return None

        def usable(team: Team) -> bool:
            return not country or not team.country or team.country in (country, "Unknown")

        pool = [t for t in self._team_pool() if usable(t)]
        exact = [t for t in pool if match_matching.normalize_team_name(t.name) == normalized]
        if exact:
            return sorted(exact, key=lambda t: str(t.id))[0]
        fuzzy = [t for t in pool if match_matching.team_names_match(t.name, name)]
        if len(fuzzy) == 1:
            return fuzzy[0]
        if len(fuzzy) > 1:
            # Several stored clubs answer to this name: attaching to one of them would be a guess.
            logger.warning("Team name %r matches %s stored teams (%s); not resolved",
                           name, len(fuzzy), [t.name for t in fuzzy])
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

    def canonical_key_for_league(self, league_id: Optional[uuid.UUID]) -> Optional[str]:
        """The canonical competition key a stored league belongs to (both forms ensure_canonical_league writes)."""
        if league_id is None:
            return None
        if league_id in self._league_key_cache:
            return self._league_key_cache[league_id]
        key = None
        league = self.db.query(League).filter(League.id == league_id).first()
        if league is not None:
            key = (league.league_metadata or {}).get("canonical_key")
            if not key:
                ref = self.db.query(ProviderEntityRef).filter(
                    ProviderEntityRef.entity_type == "league", ProviderEntityRef.provider == CANONICAL_PROVIDER,
                    ProviderEntityRef.entity_id == league.id).first()
                key = ref.external_id if ref else None
        self._league_key_cache[league_id] = key
        return key

    def candidates_for(self, league_id: Optional[uuid.UUID], kickoff_utc: datetime,
                       window: timedelta = match_matching.LOOKUP_WINDOW,
                       competition_key: Optional[str] = None) -> List[match_matching.MatchCandidate]:
        """
        Stored matches that could be the same fixture.

        The lookup window is deliberately much wider than the attach thresholds in `match_matching`:
        a fixture postponed by several days has to surface its original row, otherwise the sync sees
        nothing and silently creates a duplicate. Extra candidates can only make a decision
        `ambiguous`, never attach one (find_match keeps its own thresholds).

        Every candidate carries ITS OWN canonical competition key, not the caller's, so find_match's
        competition gate actually compares two competitions.
        """
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
            key = self.canonical_key_for_league(m.league_id) or (competition_key if m.league_id == league_id else None)
            candidates.append(match_matching.MatchCandidate(str(m.id), home.name, away.name, _aware_utc(m.match_date), key))
        return candidates

    def claimed_by_provider(self, provider: str, match_ids: Iterable[str]) -> Set[str]:
        """Which of these matches the provider already links to one of its OTHER fixture ids."""
        ids = []
        for raw in match_ids:
            try:
                ids.append(uuid.UUID(str(raw)))
            except (ValueError, AttributeError, TypeError):
                continue
        if not ids:
            return set()
        rows = self.db.query(ProviderEntityRef.entity_id).filter(
            ProviderEntityRef.entity_type == "match", ProviderEntityRef.provider == provider,
            ProviderEntityRef.entity_id.in_(ids)).all()
        return {str(row[0]) for row in rows}

    def _recover_legacy_match(self, fixture: ProviderFixture) -> Optional[Tuple[Match, str, str]]:
        """
        Find a pre-registry match row for this fixture (`external_api_id`, no provider_entity_ref).

        Such a row is invisible to `match_by_ref`, so the next sync used to create a SECOND match row
        and orphan every expert prediction attached to the first. A row is accepted only when it is
        provably the same fixture (both team names agree and the kickoff is inside the reschedule
        window) and only when exactly one row matches.
        """
        external_id = str(fixture.external_id or "").strip()
        if not external_id or external_id == "None":
            return None
        # This provider's own legacy id is an exact identification; the bare and "<other>:<id>" forms
        # are only ever "high", because the number alone does not say which provider wrote it.
        rows = self.db.query(Match).filter(Match.external_api_id == f"{fixture.provider}:{external_id}").all()
        confidence = "exact"
        if not rows:
            rows = self.db.query(Match).filter(Match.external_api_id == external_id).all()
            confidence = "high"
        if not rows:
            # A "<other-provider>:<id>" row, but only while no provider ref points at it at all.
            rows = [m for m in self.db.query(Match).filter(Match.external_api_id.like(f"%:{external_id}")).all()
                    if not self.refs_for("match", m.id)]
        if len(rows) != 1:
            if len(rows) > 1:
                logger.warning("Legacy external id %r matches %s match rows (%s); not recovered",
                               external_id, len(rows), [str(m.id) for m in rows])
            return None
        candidate = rows[0]
        if self.claimed_by_provider(fixture.provider, [str(candidate.id)]):
            logger.warning("Match %s already carries another %s fixture id; legacy id %r not recovered",
                           candidate.id, fixture.provider, external_id)
            return None
        home = self.db.query(Team).filter(Team.id == candidate.home_team_id).first()
        away = self.db.query(Team).filter(Team.id == candidate.away_team_id).first()
        if not home or not away:
            return None
        if not (match_matching.team_names_match(fixture.home.name, home.name)
                and match_matching.team_names_match(fixture.away.name, away.name)):
            logger.warning("Legacy id %r points at %s (%s vs %s) but the fixture is %s vs %s; not recovered",
                           external_id, candidate.id, home.name, away.name, fixture.home.name, fixture.away.name)
            return None
        if candidate.match_date is None or fixture.kickoff_utc is None:
            return None
        if abs(_aware_utc(candidate.match_date) - _aware_utc(fixture.kickoff_utc)) > match_matching.RESCHEDULE_WINDOW:
            logger.warning("Legacy id %r points at %s but the kickoffs are %s apart; not recovered",
                           external_id, candidate.id, abs(_aware_utc(candidate.match_date) - _aware_utc(fixture.kickoff_utc)))
            return None
        logger.info("Recovered legacy match %s for %s:%s", candidate.id, fixture.provider, external_id)
        return candidate, "legacy_external_id", confidence

    def take_refusals(self) -> List[dict]:
        """Refused fixtures since the last call (for a sync report); clears the buffer."""
        refusals, self.refusals = self.refusals, []
        return refusals

    def _refuse_fixture(self, fixture: ProviderFixture, decision: match_matching.MatchDecision) -> None:
        self._record_refusal(fixture, decision.reason, list(decision.candidate_ids))

    def _record_refusal(self, fixture: ProviderFixture, reason: str, candidates: List[str]) -> None:
        self.refusals.append({
            "provider": fixture.provider, "external_id": str(fixture.external_id),
            "home": fixture.home.name, "away": fixture.away.name,
            "kickoff_utc": fixture.kickoff_utc.isoformat() if fixture.kickoff_utc else None,
            "competition_key": fixture.competition.key, "reason": reason,
            "candidates": candidates,
        })
        logger.warning("Refusing fixture %s:%s (%s vs %s): %s; candidates=%s. No match row written.",
                       fixture.provider, fixture.external_id, fixture.home.name, fixture.away.name,
                       reason, candidates)

    def _ref_still_describes(self, match: Match, fixture: ProviderFixture) -> bool:
        """Do the teams on the match a provider id points at still match the ones just sent, in order?

        A provider id is a claim, not proof. These ids are small integers and get recycled between
        seasons, and `_apply_fixture` overwrites the teams and the competition outright, so a recycled
        id would quietly repurpose an existing match row - taking any expert prediction attached to it
        along to a different game.

        The order has to agree too: in a two-legged tie the reverse fixture is a different match.
        """
        stored_home = self.db.query(Team).filter(Team.id == match.home_team_id).first()
        stored_away = self.db.query(Team).filter(Team.id == match.away_team_id).first()
        if stored_home is None or stored_away is None:
            return True  # a half-built row has nothing to contradict
        return (match_matching.team_names_match(fixture.home.name, stored_home.name)
                and match_matching.team_names_match(fixture.away.name, stored_away.name))

    def upsert_fixture(self, fixture: ProviderFixture) -> Optional[Match]:
        """
        Persist one provider fixture and return the internal match.

        Returns **None** when the fixture cannot be attributed with certainty -- an ambiguous
        name/kickoff decision, teams that only match with home and away swapped, several candidates
        in the window. Nothing is written for a refused fixture and the refusal is appended to
        `self.refusals` so the caller can count and report it. Creating a row on an ambiguous decision
        is what split one real fixture over two match rows and orphaned the expert prediction on the
        first one, so callers MUST handle None instead of dereferencing the result.
        """
        league = self.upsert_league(fixture.competition)
        home = self.upsert_team(fixture.home, fixture.competition.country)
        away = self.upsert_team(fixture.away, fixture.competition.country)

        match = self.match_by_ref(fixture.provider, fixture.external_id)
        matched_by, confidence = "provider_id", "exact"
        if match is not None and not self._ref_still_describes(match, fixture):
            self._record_refusal(
                fixture, "provider fixture id no longer names the same teams in the same order",
                [str(match.id)])
            return None
        if match is None:
            recovered = self._recover_legacy_match(fixture)
            if recovered is not None:
                match, matched_by, confidence = recovered
        if match is None:
            decision = match_matching.find_match(fixture.home.name, fixture.away.name, fixture.kickoff_utc,
                                                 fixture.competition.key,
                                                 self.candidates_for(league.id, fixture.kickoff_utc,
                                                                     competition_key=fixture.competition.key))
            if decision.attached:
                match = self.db.query(Match).filter(Match.id == uuid.UUID(decision.match_id)).first()
                matched_by, confidence = "name_kickoff", decision.confidence
            elif decision.confidence == "ambiguous":
                # Candidates this provider already links to its other fixture ids cannot be this
                # fixture: one provider never gives one fixture two live ids. Anything else is refused.
                unclaimed = set(decision.candidate_ids) - self.claimed_by_provider(fixture.provider, decision.candidate_ids)
                if unclaimed:
                    self._refuse_fixture(fixture, decision)
                    return None
                logger.info("Fixture %s:%s (%s vs %s): candidates %s are the same provider's other fixtures; new match row",
                            fixture.provider, fixture.external_id, fixture.home.name, fixture.away.name, decision.candidate_ids)
        if match is None:
            # `external_api_id` is unique: when another row already carries this provider id (a legacy
            # row we just refused to recover, for instance) the new row keeps it empty and is
            # identified by its provider ref alone, instead of failing the whole sync transaction.
            legacy_id = f"{fixture.provider}:{fixture.external_id}"
            if self.db.query(Match.id).filter(Match.external_api_id == legacy_id).first():
                logger.warning("external_api_id %s already belongs to another match row; the new row is identified by its ref only",
                               legacy_id)
                legacy_id = None
            match = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id, league_id=league.id,
                          match_date=_naive_utc(fixture.kickoff_utc), status=MatchStatus.SCHEDULED,
                          external_api_id=legacy_id, external_api_source=fixture.provider,
                          match_metadata={})
            self.db.add(match)
            self.db.flush()
        self._apply_fixture(match, fixture, home, away, league)
        # The ref records how this link was really made: an invented "exact/provider_id" would erase
        # the fact that the match was found by name, by a legacy id, or with a lower confidence.
        self.set_ref("match", match.id, fixture.provider, fixture.external_id, confidence=confidence, matched_by=matched_by,
                     metadata={"home": fixture.home.name, "away": fixture.away.name, "kickoff_utc": fixture.kickoff_utc.isoformat()})
        return match

    def _owns_match(self, match: Match, provider: str) -> bool:
        """The provider whose record created this match row owns its kickoff; nobody else moves it."""
        return not match.external_api_source or match.external_api_source == provider

    def _merged_status(self, match: Match, fixture: ProviderFixture) -> MatchStatus:
        incoming = STATUS_TO_ENUM.get(fixture.status, MatchStatus.SCHEDULED)
        if match.status in TERMINAL_STATUSES and incoming in REGRESSIVE_STATUSES:
            logger.warning("Provider %s reports %r for match %s which is already %s; keeping the terminal status",
                           fixture.provider, fixture.status, match.id, match.status)
            return match.status
        return incoming

    def _apply_fixture(self, match: Match, fixture: ProviderFixture, home: Team, away: Team, league: League) -> None:
        # Only the provider that owns the match record moves the kickoff. A secondary provider with a
        # stale calendar may disagree; it is logged and ignored instead of dragging the fixture around.
        if self._owns_match(match, fixture.provider):
            match.match_date = _naive_utc(fixture.kickoff_utc)
        elif match.match_date is not None and fixture.kickoff_utc is not None and \
                abs(_aware_utc(match.match_date) - _aware_utc(fixture.kickoff_utc)) > match_matching.EXACT_WINDOW:
            logger.warning("Provider %s reports kickoff %s for match %s owned by %s (stored %s); kickoff left unchanged",
                           fixture.provider, fixture.kickoff_utc, match.id, match.external_api_source, match.match_date)
        match.home_team_id = home.id
        match.away_team_id = away.id
        match.league_id = league.id
        match.venue = fixture.venue or match.venue
        match.round = fixture.round or match.round
        if fixture.competition.season_name:
            match.season = fixture.competition.season_name[:20]
        match.status = self._merged_status(match, fixture)
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
            self._backfill_legacy_ref(legacy)
            return legacy.id
        if provider is None:
            # A bare legacy id belonging to a provider that is not the active one: accepted only when
            # a single row carries it, because identical numbers at several providers never identify
            # the same fixture (same policy as the ref lookup above).
            rows = self.db.query(Match).filter(Match.external_api_id.like(f"%:{external_id}")).all()
            if len(rows) == 1:
                self._backfill_legacy_ref(rows[0])
                return rows[0].id
            if len(rows) > 1:
                active = [m for m in rows if m.external_api_source == settings.DATA_PROVIDER]
                if len(active) == 1:
                    self._backfill_legacy_ref(active[0])
                    return active[0].id
                logger.warning("Legacy match id %s is ambiguous across providers (%s); not resolved",
                               raw, sorted(str(m.id) for m in rows))
        return None

    def _backfill_legacy_ref(self, match: Match, confidence: str = "high") -> None:
        """A legacy row resolved by `external_api_id` gets the provider ref it was missing."""
        source, sep, stored = (match.external_api_id or "").partition(":")
        provider = (source if sep else (match.external_api_source or "")).strip()
        external_id = (stored if sep else (match.external_api_id or "")).strip()
        if not provider or not external_id:
            return
        if self.get_ref("match", provider, external_id) is not None:
            return
        try:
            self.set_ref("match", match.id, provider, external_id, confidence=confidence, matched_by="legacy_external_id")
        except Exception as exc:  # pragma: no cover - a failed backfill must never break resolution
            logger.warning("Could not backfill the %s ref for match %s: %s", provider, match.id, exc)

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
        return {league.id: league for league in self.db.query(League).filter(League.id.in_(list(ids))).all()}
