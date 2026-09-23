"""
Match registry: persists provider fixtures as internal matches/teams/leagues and keeps the
provider-id links (`provider_entity_refs`) that make records stable across provider changes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
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

#: How close two kickoffs must be for `_shared_slot_candidates` to call them the same moment.
#: The tightest window there is; a club that appears twice an hour apart is playing twice.
SHARED_SLOT_WINDOW = match_matching.EXACT_WINDOW

#: How long after kickoff a fixture is left alone before anything calls it unsettled. The same
#: grace the results gate applies, so a sweep never asks about a game that is still being played.
UNSETTLED_GRACE = timedelta(minutes=150)
#: How many days older than the results lookback one sweep may reopen. A results call costs one
#: provider request per competition per day, so this cap is the sweep's entire extra cost.
STALE_SWEEP_MAX_DAYS = 2
#: How many sweeps one fixture is re-asked about before it is given up on. Only a pass that
#: actually put the question counts: see `RecoveryOutcome`.
STALE_SWEEP_MAX_ATTEMPTS = 3
#: The outer bound on how far back the sweep will look at all, measured from the moment of the
#: sweep. Without one, a row the provider will never answer about is a cost that never ends; and a
#: results endpoint is a window on the recent past rather than an archive, so the further back the
#: question, the less there is to get. `unsettled_before` selects by it and the recording side
#: gives up by it, both against the same clock, so a fixture is never offered and then abandoned
#: as too old in one pass.
STALE_SWEEP_MAX_AGE = timedelta(days=14)


class RecoveryOutcome(str, Enum):
    """
    What one sweep pass learned about one stranded fixture. Exactly one of these is an attempt.

    "Attempt" is the sweep's word for evidence that the provider has nothing to say, and
    `STALE_SWEEP_MAX_ATTEMPTS` of them retire a fixture with "no result after N attempts" written
    on the row. That sentence is only true of a fixture somebody was actually asked about, so the
    three outcomes where nobody was asked, or the answer was one we already held, are recorded
    without moving the counter.
    """

    #: The question was never put: every provider in the chain failed or was cooling down, or no
    #: results call was made for the day at all. Nothing was learned, so it cannot retire a
    #: fixture -- three outages in a row would otherwise give up on a fixture nobody asked about.
    #: It is still counted on the row, because a sweep failing silently for a week is its own
    #: defect and this is where that becomes visible.
    PROVIDER_ERROR = "provider_error"
    #: The day was served out of the cache, fresh or stale. This pass did not put the question,
    #: and it cannot tell who did: the results cache key is per day and per competition set, and
    #: `MatchDataService.matches_for_day(day, refresh=True)` shares it, which
    #: `GET /api/v1/matches?date=...` reaches for any date a reader asks for. So a stored answer
    #: may be one the sweep has already seen, or a genuinely fresh one a reader's request fetched
    #: moments ago. An attempt is evidence the provider was asked and had nothing, and evidence
    #: nobody can date is not evidence, so no attempt is spent. Erring this way costs a fixture
    #: one more pass in the sweep; erring the other way writes "no result after N attempts" about
    #: a question this sweep never put.
    CACHED = "cached"
    #: A provider was asked during this pass, answered, and the fixture is still unsettled. The
    #: only outcome that is evidence, and so the only one that counts toward giving up.
    FRESH_UNANSWERED = "fresh_unanswered"
    #: The fixture is settled now and was not before the pass. There is nothing left to retry, so
    #: no attempt is spent; what settled it is written on the row instead.
    RECOVERED = "recovered"


def is_settled(status: MatchStatus) -> bool:
    """Whether a fixture has an answer. The sweep asks about exactly the statuses this excludes."""
    return status not in REGRESSIVE_STATUSES


def classify_recovery_outcome(meta, *, settled_before: bool, settled_now: bool) -> Tuple[RecoveryOutcome, str]:
    """
    Which of the four outcomes one day's results call produced for one stranded fixture.

    `meta` is the `SyncMeta` that `MatchDataService._sync_results` filled for the fixture's own
    day. It is read by attribute rather than imported, because match_data_service imports this
    module. Three of its fields carry the answer:

    * `results_polled` is set only once the call chain has returned, so False means the question
      was never put -- every provider failed or was cooling down, or `_sync_results` returned
      early because the day held nothing pending. `errors` separates those two in the wording;
      the decision is the same either way, and it is not to count an attempt.
    * `source` says where the answer came from. "provider" is the only value meaning somebody was
      asked during this pass; "cache" and "stale-cache" mean the day came out of the store, which
      says nothing about when or by whom it was put there (see `RecoveryOutcome.CACHED`). They are
      reported apart because a stale copy also says the provider is not currently reachable.
    * `errors` may hold entries on a pass that succeeded anyway: the chain records every provider
      it gave up on before the one that answered. So a failed pass is `results_polled` being
      False, never `errors` being non-empty.

    The meta covers the DAY and not the fixture, which leaves one pair it cannot separate: a
    fresh answer that never mentioned this fixture, and a fresh answer that mentioned it and
    still calls it unfinished. `fixtures_seen` and `fixtures_stored` count a day's fixtures
    without naming them. Both land in FRESH_UNANSWERED, which is the right bucket for both: each
    is the provider, asked now, holding no final result for this fixture, and that is exactly
    what the attempt counter measures.

    `settled_before` is this fixture's own state, read before the sync ran. A fixture already
    settled cannot have been recovered by the pass and was never the sweep's to ask about, so
    offering one is a caller error rather than a recovery to be credited.
    """
    if settled_before:
        raise ValueError("this fixture was already settled before the pass; the sweep asks about "
                         "unsettled fixtures only, and a status it did not change is not a recovery")
    asked = bool(getattr(meta, "results_polled", False))
    source = getattr(meta, "source", None) or "database"
    provider = getattr(meta, "provider", None) or source
    if settled_now:
        if asked and source == "provider":
            return RecoveryOutcome.RECOVERED, f"a fresh answer from {provider} settled it"
        if asked:
            return RecoveryOutcome.RECOVERED, f"the {source} copy of the day settled it"
        return RecoveryOutcome.RECOVERED, "settled without this sweep's results call"
    if not asked:
        errors = getattr(meta, "errors", None) or []
        return RecoveryOutcome.PROVIDER_ERROR, "; ".join(errors) or "no results call was made for this day"
    if source in ("cache", "stale-cache"):
        return RecoveryOutcome.CACHED, f"served from {source}"
    return RecoveryOutcome.FRESH_UNANSWERED, f"{provider} answered and had no result for it"


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
        self._legacy_league_ids: Optional[List[uuid.UUID]] = None

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

    def _leagues_without_canonical_key(self) -> List[uuid.UUID]:
        """Leagues that predate the canonical registry: no canonical key by either form it is stored in."""
        if self._legacy_league_ids is None:
            self._legacy_league_ids = [
                league.id for league in self.db.query(League).all()
                if not self.canonical_key_for_league(league.id)
            ]
        return self._legacy_league_ids

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

        Matches in a league with no canonical key are admitted too. Those are rows written before the
        provider work, when leagues were created per provider; filtering them out by league made a
        pre-Phase-1 fixture invisible here, so the sync saw no candidate at all, wrote a SECOND match
        row for the same game, and left the expert prediction on the first one - without recording a
        refusal, so nobody would learn it had happened. Such a candidate carries `competition_key`
        None, and find_match's competition gate skips a candidate with no key, so the team names and
        the kickoff decide it, which is exactly what should happen when the competition is unknown.
        """
        start, end = _naive_utc(kickoff_utc - window), _naive_utc(kickoff_utc + window)
        query = self.db.query(Match).filter(Match.match_date >= start, Match.match_date <= end)
        if league_id is not None:
            legacy_league_ids = self._leagues_without_canonical_key()
            if legacy_league_ids:
                query = query.filter(or_(Match.league_id == league_id,
                                         Match.league_id.in_(legacy_league_ids)))
            else:
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

        Such a row is invisible to `match_by_ref`, and without this lookup the sync writes a SECOND
        match row for the fixture and leaves every expert prediction on the first. A row is
        accepted only when it is provably the same fixture -- both team names agree and the kickoff
        is inside the reschedule window -- and only when exactly one row matches.
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

    def _ref_still_describes(self, match: Match, fixture: ProviderFixture, home: Team, away: Team) -> bool:
        """Do the teams on the match a provider id points at still match the ones just sent, in order?

        A provider id is a claim, not proof. These ids are small integers and get recycled between
        seasons, and `_apply_fixture` overwrites the teams and the competition outright, so a recycled
        id would quietly repurpose an existing match row - taking any expert prediction attached to it
        along to a different game.

        The resolved club rows settle it whenever they agree, which is what happens once the
        provider's team ids are linked to the stored clubs; the raw provider names are the fallback
        for a match row whose clubs this provider has never been linked to. A provider that spells
        a club differently from the row it is stored under can only be accepted on identity, since
        its name will never match. The order has to agree either way: in a two-legged tie the
        reverse fixture is a different match.
        """
        if match.home_team_id == home.id and match.away_team_id == away.id:
            return True
        stored_home = self.db.query(Team).filter(Team.id == match.home_team_id).first()
        stored_away = self.db.query(Team).filter(Team.id == match.away_team_id).first()
        if stored_home is None or stored_away is None:
            return True  # a half-built row has nothing to contradict
        return (match_matching.team_names_match(fixture.home.name, stored_home.name)
                and match_matching.team_names_match(fixture.away.name, stored_away.name))

    # ------------------------------------------------------- one club, one game at a time
    def _shared_slot_candidates(self, league: League, home: Team, away: Team,
                                kickoff_utc: Optional[datetime], provider: str
                                ) -> List[Tuple[Match, Optional[str]]]:
        """
        Stored fixtures that hold one of these clubs in this competition at this kickoff.

        `find_match` has only team names to go on, so two providers that spell one club differently
        resolve it to two Team rows whose names never meet, and the fixture is stored twice. Club
        identity does meet, because it is a row id rather than a spelling.

        Each entry is the stored match and the slot whose club rows DISAGREE -- "home", "away", or
        None when both slots carry the identical club. Only the None entries identify the fixture:
        no calendar puts one club in two fixtures fifteen minutes apart in one competition, so a
        stored row with both of these clubs at this moment is this game whatever either provider
        calls them. An entry naming a slot is the opposite of a decision. It says two records put
        different clubs in the same place at the same time, which is a contradiction the caller
        reports rather than resolves.

        A row this provider already links to one of its other fixture ids is left out: one provider
        never gives one fixture two live ids.
        """
        if kickoff_utc is None:
            return []
        start, end = _naive_utc(kickoff_utc - SHARED_SLOT_WINDOW), _naive_utc(kickoff_utc + SHARED_SLOT_WINDOW)
        rows = self.db.query(Match).filter(
            Match.league_id == league.id,
            Match.match_date >= start, Match.match_date <= end,
            or_(Match.home_team_id == home.id, Match.away_team_id == away.id),
        ).all()
        claimed = self.claimed_by_provider(provider, [str(m.id) for m in rows])
        found: List[Tuple[Match, Optional[str]]] = []
        for m in rows:
            if str(m.id) in claimed:
                continue
            same_home, same_away = m.home_team_id == home.id, m.away_team_id == away.id
            if same_home and same_away:
                found.append((m, None))
            elif same_home:
                found.append((m, "away"))
            elif same_away:
                found.append((m, "home"))
        return found

    def upsert_fixture(self, fixture: ProviderFixture) -> Optional[Match]:
        """
        Persist one provider fixture and return the internal match.

        Returns **None** for four reasons. In every one of them nothing is written, the refusal
        goes on `self.refusals` and into the log for the caller to count and report, and callers
        MUST handle None instead of dereferencing the result.

        Three are a stored row that is the only honest home for this fixture and cannot be proven
        to be that row: an ambiguous name/kickoff decision, teams that match only with home and
        away swapped, several candidates in the window. Those candidates carry THESE clubs, so a
        new row would be a second copy of a fixture already stored.

        The fourth reason is the opposite case and is refused for its own reason: the provider's
        fixture id is already linked to a stored match whose clubs it no longer names. Writing
        this fixture onto that row would overwrite one fixture with another, and nothing here can
        tell an id re-pointed at a genuinely new fixture from a link that has gone wrong, so
        neither the stored row nor a new one is written. The cost is that a provider which reuses
        a fixture id for a new fixture has it refused on this sync and on every later one, and
        the fixture stays off the site until a person clears the stale ref -- which is what the
        repeated refusal in `self.refusals` and the log is there to bring to their attention.

        A fixture no candidate can be is different: it is stored. When a stored row holds one of
        its clubs at this kickoff beside a different opponent, the two records contradict each
        other and neither says which is wrong, so the row is written anyway and records the clash
        under `match_metadata.shared_slot_conflict` for a person to resolve. Declining to merge two
        clubs is a judgement about identity; declining to store is throwing a real fixture away,
        and a stored row that vetoes a kickoff vetoes it on every later sync too.
        """
        league = self.upsert_league(fixture.competition)
        home = self.upsert_team(fixture.home, fixture.competition.country)
        away = self.upsert_team(fixture.away, fixture.competition.country)

        match = self.match_by_ref(fixture.provider, fixture.external_id)
        matched_by, confidence = "provider_id", "exact"
        if match is not None and not self._ref_still_describes(match, fixture, home, away):
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
        clash: List[str] = []
        if match is None:
            # Last resort before a new row: the names failed, but club rows are ids, not spellings,
            # and a club plays one match at a time.
            shared = self._shared_slot_candidates(league, home, away, fixture.kickoff_utc, fixture.provider)
            settled = [m for m, slot in shared if slot is None]
            if len(settled) == 1:
                match = settled[0]
                matched_by, confidence = "shared_slot_identity", "high"
                logger.info("Fixture %s:%s (%s vs %s) is match %s: the identical two clubs in this competition "
                            "at this kickoff, whatever either provider spells them",
                            fixture.provider, fixture.external_id, fixture.home.name, fixture.away.name, match.id)
            # Every stored row left over is a contradiction: two records putting different clubs
            # in one competition at one moment, or two rows already holding this same pair. None
            # of them says which record is wrong, so they are recorded for
            # `scripts/repair_duplicate_matches.py` rather than resolved here -- on the row the
            # fixture was joined to when there was one, and otherwise on the row written below.
            # Withholding the fixture instead would make one stored row a permanent veto on every
            # other fixture at that kickoff: a real game would stay off the site on this sync and
            # on every later one, because the row that blocks it is still there next time.
            clash = [str(m.id) for m, _ in shared if match is None or m.id != match.id]
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
        if clash:
            self._record_slot_conflict(match, fixture, clash)
        # The ref records how this link was really made: an invented "exact/provider_id" would erase
        # the fact that the match was found by name, by a legacy id, or with a lower confidence.
        self.set_ref("match", match.id, fixture.provider, fixture.external_id, confidence=confidence, matched_by=matched_by,
                     metadata={"home": fixture.home.name, "away": fixture.away.name, "kickoff_utc": fixture.kickoff_utc.isoformat()})
        return match

    def _record_slot_conflict(self, match: Match, fixture: ProviderFixture, candidates: List[str]) -> None:
        """
        Mark a stored row as sharing a club and a kickoff with rows it could not be reconciled with.

        This is the handover to a person. One of the rows is a real fixture and the other is either
        the same fixture under a spelling nobody has listed yet -- fixed by one line in
        `match_matching._ALIASES` and a run of the repair script -- or a provider record that is
        simply wrong. Deciding which is not something the sync can do from the data it has, so it
        writes down what it saw. `scripts/repair_duplicate_matches.py` lists these.
        """
        meta = dict(match.match_metadata or {})
        meta["shared_slot_conflict"] = {
            "candidates": candidates,
            "provider": fixture.provider,
            "external_id": str(fixture.external_id),
            "home": fixture.home.name,
            "away": fixture.away.name,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        match.match_metadata = meta
        self.db.flush()
        logger.warning("Fixture %s:%s (%s vs %s) shares a club and a kickoff with %s but the other club could not "
                       "be reconciled; stored as match %s and reported for review.",
                       fixture.provider, fixture.external_id, fixture.home.name, fixture.away.name,
                       candidates, match.id)

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
            "ft_home_score": fixture.ft_home_score,
            "ft_away_score": fixture.ft_away_score,
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
            self._apply_periods(result, fixture)
        self.db.flush()

    def _apply_periods(self, result: MatchResult, fixture: ProviderFixture) -> None:
        """
        Store the period breakdown the provider supplied, and flag a tie that went past 90.

        `home_score`/`away_score` on the row is the score of the football played; this is what
        lets settlement tell that apart from the score after 90 minutes, which is the only one
        the published market rules settle on. A provider that supplies no breakdown leaves every
        column None -- the columns are never filled in from the final score, because a guessed
        regulation score is the bug this exists to stop, written down as data.
        """
        result.home_score_ft, result.away_score_ft = fixture.ft_home_score, fixture.ft_away_score
        result.home_score_et, result.away_score_et = fixture.et_home_score, fixture.et_away_score
        result.home_score_pens, result.away_score_pens = fixture.ps_home_score, fixture.ps_away_score
        if fixture.went_beyond_regulation:
            meta = dict(result.result_metadata or {})
            meta["went_beyond_regulation"] = True
            result.result_metadata = meta

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

    # -------------------------------------------------- fixtures the refreshes no longer reach
    def unsettled_before(self, cutoff: datetime, league_ids: Optional[Iterable[uuid.UUID]] = None,
                         now: Optional[datetime] = None,
                         max_age: timedelta = STALE_SWEEP_MAX_AGE,
                         max_attempts: int = STALE_SWEEP_MAX_ATTEMPTS) -> List[Match]:
        """
        Fixtures still SCHEDULED or LIVE long after kickoff that are worth asking about again.

        Neither refresh reaches these. The live poll only looks at today, and the results task only
        looks back `SYNC_RESULTS_LOOKBACK_DAYS` days, so a fixture whose final score never arrived
        inside that window is never asked about again and stays on the site reading LIVE for ever.

        `cutoff` is the youngest kickoff worth reopening; `max_age` is measured from `now`, the same
        clock `record_recovery_attempt` ages a fixture against, so the horizon offers exactly the
        fixtures it does not immediately give up on. Measuring it from `cutoff` instead would push
        the floor a further `now - cutoff` into the past, and every fixture in that strip would be
        offered, cost its provider requests, and be abandoned as too old in the same pass.

        Oldest first, so a sweep that can only afford a few days spends them on the fixtures that
        have been wrong longest. A fixture the sweep has given up on is not returned again: see
        `record_recovery_attempt` for what giving up means and when it happens.
        """
        floor = _naive_utc((now or datetime.now(timezone.utc)) - max_age)
        rows = self.db.query(Match).filter(
            Match.status.in_(REGRESSIVE_STATUSES),
            Match.match_date <= _naive_utc(cutoff),
            Match.match_date >= floor,
        )
        if league_ids is not None:
            rows = rows.filter(Match.league_id.in_(list(league_ids)))
        out = []
        for m in rows.order_by(Match.match_date.asc()).all():
            state = self.recovery_state(m)
            if state.get("gave_up_at") or int(state.get("attempts") or 0) >= max_attempts:
                continue
            out.append(m)
        return out

    def stale_unsettled_days(self, now: datetime, lookback_days: int,
                             league_ids: Optional[Iterable[uuid.UUID]] = None,
                             max_days: int = STALE_SWEEP_MAX_DAYS, **limits) -> List[date]:
        """
        The days OLDER than the results lookback that still hold a recoverable unsettled fixture.

        Oldest first and capped at `max_days`, because a results call costs one provider request
        per competition per day: the cap is the entire extra cost of the sweep, and it is what
        keeps an unanswerable fixture from being re-asked without end.

        A day the results task already covers is never offered here. The task walks back from
        today through `lookback_days`, so the sweep starts the instant before the earliest of
        those days: paying twice for one day would be the sweep's whole budget spent on a day
        that was going to be asked about anyway.
        """
        covered_from = now.date() - timedelta(days=max(int(lookback_days), 0))
        cutoff = min(now - UNSETTLED_GRACE,
                     datetime.combine(covered_from, datetime.min.time(),
                                      tzinfo=timezone.utc) - timedelta(microseconds=1))
        days: List[date] = []
        for m in self.unsettled_before(cutoff, league_ids, now=now, **limits):
            day = m.match_date.date()
            if day not in days:
                days.append(day)
            if len(days) >= max_days:
                break
        return days

    @staticmethod
    def recovery_state(match: Match) -> Dict[str, object]:
        """What the sweep has already tried for this fixture, as stored on the row."""
        return dict((match.match_metadata or {}).get("recovery") or {})

    def _store_recovery(self, match: Match, state: Dict[str, object]) -> Dict[str, object]:
        """Put the sweep's bookkeeping back on the row. JSONB is replaced whole, never mutated."""
        meta = dict(match.match_metadata or {})
        meta["recovery"] = state
        match.match_metadata = meta
        self.db.flush()
        return state

    @staticmethod
    def _past_horizon_reason(match: Match, now: datetime, max_age: timedelta) -> Optional[str]:
        """Why this fixture is beyond asking about at all, or None while it is still in range."""
        age = now - _aware_utc(match.match_date)
        if age > max_age:
            return f"kickoff is {age.days} days old, past the {max_age.days}-day results horizon"
        return None

    def _give_up(self, match: Match, state: Dict[str, object], now: datetime, reason: str) -> None:
        state["gave_up_at"] = now.isoformat()
        state["gave_up_reason"] = reason
        logger.warning("Giving up on match %s (%s, still %s): %s. It keeps its stored status; "
                       "no further provider request will be spent on it.",
                       match.id, match.match_date, match.status, reason)

    def record_recovery_attempt(self, match: Match, now: Optional[datetime] = None,
                                max_attempts: int = STALE_SWEEP_MAX_ATTEMPTS,
                                max_age: timedelta = STALE_SWEEP_MAX_AGE,
                                detail: str = "") -> Dict[str, object]:
        """
        Count one sweep attempt against a fixture, and give up on it when it has had enough.

        An attempt is `RecoveryOutcome.FRESH_UNANSWERED` and nothing else: the provider was asked
        during the pass, answered, and had no result for this fixture. Passes that learned
        nothing go to `record_recovery_outcome`, which leaves the count alone.

        Giving up is written on the row, under `match_metadata.recovery`: `gave_up_at` and
        `gave_up_reason` beside the attempt count. `unsettled_before` then skips the fixture for
        good, so the sweep stops spending requests on a question the provider is not going to
        answer. Only the bookkeeping moves: the status, the scores and the result are untouched,
        because a score nobody reported is not a score.
        """
        now = now or datetime.now(timezone.utc)
        state = self.recovery_state(match)
        attempts = int(state.get("attempts") or 0) + 1
        state["attempts"] = attempts
        state["last_attempt_at"] = now.isoformat()
        state["last_outcome"] = RecoveryOutcome.FRESH_UNANSWERED.value
        state["last_outcome_at"] = now.isoformat()
        if detail:
            state["last_outcome_detail"] = detail
        if not state.get("gave_up_at"):
            reason = self._past_horizon_reason(match, now, max_age)
            if reason is None and attempts >= max_attempts:
                reason = f"no result after {attempts} attempts"
            if reason:
                self._give_up(match, state, now, reason)
        return self._store_recovery(match, state)

    def _settled_by(self, match: Match) -> str:
        """What the row now says the result was, for the recovery note. Read, never invented."""
        result = self.db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
        if result is None or result.home_score is None or result.away_score is None:
            return match.status.value
        return f"{match.status.value} {result.home_score}-{result.away_score}"

    def record_recovery_outcome(self, match: Match, outcome: RecoveryOutcome, detail: str = "",
                                now: Optional[datetime] = None,
                                max_attempts: int = STALE_SWEEP_MAX_ATTEMPTS,
                                max_age: timedelta = STALE_SWEEP_MAX_AGE) -> Dict[str, object]:
        """
        Write down what one sweep pass learned about this fixture, counting it only if it counts.

        `RecoveryOutcome.FRESH_UNANSWERED` is the one outcome that spends an attempt, and it is
        handed straight to `record_recovery_attempt`. A provider error and a cached day each get
        their own counter so an unproductive sweep can be seen to be unproductive, and neither
        moves `attempts`. A recovery is written with what settled it and closes the fixture out:
        there is nothing left to retry and so nothing to give up on.

        The age bound applies to the other three outcomes all the same. It is a fact about the
        fixture and the provider's results window rather than about this pass, so a fixture that
        has drifted past the horizon is given up with that reason even when nobody could be
        asked; that reason names the age and never claims an answer.
        """
        now = now or datetime.now(timezone.utc)
        if outcome is RecoveryOutcome.FRESH_UNANSWERED:
            return self.record_recovery_attempt(match, now, max_attempts=max_attempts,
                                                max_age=max_age, detail=detail)
        state = self.recovery_state(match)
        state["last_outcome"] = outcome.value
        state["last_outcome_at"] = now.isoformat()
        if detail:
            state["last_outcome_detail"] = detail
        if outcome is RecoveryOutcome.RECOVERED:
            state["recovered_at"] = now.isoformat()
            state["recovered_as"] = self._settled_by(match)
            state["recovered_by"] = detail or "settled during the sweep"
            return self._store_recovery(match, state)
        if outcome is RecoveryOutcome.PROVIDER_ERROR:
            state["provider_errors"] = int(state.get("provider_errors") or 0) + 1
            state["last_provider_error_at"] = now.isoformat()
        elif outcome is RecoveryOutcome.CACHED:
            state["cached_passes"] = int(state.get("cached_passes") or 0) + 1
            state["last_cached_at"] = now.isoformat()
        if not state.get("gave_up_at"):
            reason = self._past_horizon_reason(match, now, max_age)
            if reason:
                self._give_up(match, state, now, reason)
        return self._store_recovery(match, state)

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
        if legacy is None and provider:
            # The pre-registry shape: the bare id in external_api_id with the provider name kept
            # separately in external_api_source. "api_football:1035049" has to find a row storing
            # "1035049". Scoped by source and external_api_id is unique, so this cannot be ambiguous
            # or claim another provider's row.
            legacy = self.db.query(Match).filter(Match.external_api_id == external_id,
                                                 Match.external_api_source == provider).first()
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
