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

#: How long after kickoff a fixture is left alone before anything calls it unsettled. This is THIS
#: APPLICATION'S polling window: the live task stops considering a match 150 minutes after kickoff
#: and the results gate starts asking at the same moment. It is not a measurement of how long any
#: provider keeps a finished match on any endpoint.
UNSETTLED_GRACE = timedelta(minutes=150)
#: How many days older than the results lookback one recovery pass may reopen. A results call
#: costs one provider request per competition per day, so this caps what one pass can take.
STALE_SWEEP_MAX_DAYS = 2

#: THE RETRY SCHEDULE: how often a fixture still unsettled after `UNSETTLED_GRACE` is asked about,
#: by how long ago it kicked off. One schedule for every competition, club or national-team.
#:
#: It is a BUDGET POLICY and nothing more. It bounds what one missing result can cost and asserts
#: nothing about whether the result exists or when it will appear. The archive has answered for
#: national-team competitions (World Cup, AFCON, Copa America, Women's World Cup), and on
#: 2026-09-22 and 2026-09-25 it returned nothing dated 2026-09-18 or later for club and national
#: competitions alike, cause unknown (docs/evidence/livescore-archive-observations.json). So a
#: result may appear days after the match, and the schedule keeps asking, ever more rarely, rather
#: than stopping on the evening itself.
#:
#: Each entry is (up to this age, at most one ask per this gap). Against an archive that stays
#: empty, one competition-day costs 16 requests in its first 24 hours, 16 more over days 1-6 and 7
#: over days 7-13: 39 in all, where a flat half-hourly cadence would spend 672 over the same
#: fortnight. Behind the results lookback the recovery pass pays for these out of
#: `SYNC_RECOVERY_MAX_REQUESTS_PER_DAY` (40), and no competition-day that old costs more than 4 a
#: day, so that allowance covers ten stranded competition-days at once before any has to wait.
RETRY_SCHEDULE: Tuple[Tuple[timedelta, timedelta], ...] = (
    (timedelta(hours=6), timedelta(0)),          # every pass, as the results task always has
    (timedelta(hours=24), timedelta(hours=2)),
    (timedelta(days=3), timedelta(hours=6)),
    (timedelta(days=7), timedelta(hours=12)),
    (timedelta(days=14), timedelta(hours=24)),
)
#: Where the schedule ends. A fixture whose next ask would fall past it is given up on, and only
#: straight after an ask the provider ANSWERED, so an outage can never retire anything. What can
#: undo that is narrow, and stated where it is done: `MatchRegistry.reopen_retired`.
RETRY_HORIZON = RETRY_SCHEDULE[-1][0]
#: What `stopped_by` says on a stop the retry schedule made. It is the only policy that stops the
#: sweep, so it is the only value a stop in force may carry.
STOP_POLICY = "retry_budget"
#: Stops made under a policy this installation still applies. A row carrying `gave_up_at` with any
#: other `stopped_by` - or none, which is every stop written before the field existed - was stopped
#: by a rule that has since been removed, and `MatchRegistry.undo_superseded_stops` undoes it
#: rather than letting it stand under a policy that did not make it.
CURRENT_STOP_POLICIES = frozenset({STOP_POLICY})
#: The same horizon under the name the selection reads. A fixture older than this that the sweep
#: has never asked about predates the sweep, and is not started on.
STALE_SWEEP_MAX_AGE = RETRY_HORIZON
#: Passes run on an interval that drifts by seconds, so a gap counts as elapsed slightly early.
#: Without this a 2-hour gap measured at 1:59:58 waits for the next pass and becomes 2.5 hours.
RETRY_SLACK = timedelta(minutes=5)
#: How many dated archive observations one competition keeps (newest dates win).
ARCHIVE_OBSERVATIONS_KEPT = 120


class RecoveryOutcome(str, Enum):
    """
    What one pass learned about one unsettled fixture. Exactly one of these is an attempt.

    An attempt is the provider being asked about the fixture's competition and day, ANSWERING, and
    the answer holding no result for it. Attempts are what the retry schedule counts from and what
    a reader is told. Everything else is recorded apart, so that "the provider had nothing" and
    "nobody could reach the provider" never read as the same fact.
    """

    #: A request for a results call covering this fixture WENT OUT and no provider answered it: the
    #: network failed, the provider returned an error, or the provider itself refused it. Nothing
    #: was learned, so it spends no attempt, does not move the retry schedule and can never retire
    #: a fixture. It is counted on the row, and a recovery pass that met one reports itself as
    #: failed: an outage has to be visible as an outage. A call that never left is not this: see
    #: DEFERRED.
    PROVIDER_ERROR = "provider_error"
    #: The day was served out of the cache. This pass did not put the question, and it cannot tell
    #: who did: the results cache key is per day and per competition set, and
    #: `MatchDataService.matches_for_day(day, refresh=True)` shares it, which
    #: `GET /api/v1/matches?date=...` reaches for any date a reader asks for. Evidence nobody can
    #: date is not evidence, so no attempt is spent.
    CACHED = "cached"
    #: A provider was asked, answered, and had no result for the fixture. The only outcome that is
    #: evidence, and so the only attempt. It says what the archive held at that moment and nothing
    #: about what it will hold later.
    FRESH_UNANSWERED = "fresh_unanswered"
    #: The fixture is settled now and was not before the pass. What settled it is written on the row.
    RECOVERED = "recovered"
    #: The fixture was due an ask and NO REQUEST WAS MADE for it: the recovery allowance for the
    #: pass or the day was spent, our own daily ceiling for the provider (or the provider's own
    #: reported window) refused the request before it left, or every provider was cooling down
    #: after a failure elsewhere. Neither an answer nor an outage - nothing was asked, so nothing
    #: was unreachable. Recorded on the row, spends no attempt, and the fixture stays due.
    DEFERRED = "deferred"
    #: Nothing the pass did asked about this fixture because nothing was due: the retry schedule
    #: does not call for an ask yet, or its day is inside the results lookback and the results task
    #: asks about it. Reported by the pass and never written on the row, since nothing happened.
    NOT_ASKED = "not_asked"


class ArchiveState(str, Enum):
    """What `matches/history.json` returned for ONE competition on ONE date, the last time we asked.

    Recorded where the results call already happens (`MatchDataService._sync_results`), so knowing
    it costs no request. The three states are deliberately narrow:

    * ANSWERED -- rows came back for that competition and date.
    * EMPTY    -- the call succeeded and returned nothing. That says what the archive held WHEN we
                  asked, and nothing about whether it will ever hold more.
    * UNKNOWN  -- never asked, or every ask failed. The default for every competition, club or
                  national-team alike: nothing is assumed about a competition from its type.
    """

    ANSWERED = "answered"
    EMPTY = "empty"
    UNKNOWN = "unknown"


def is_settled(status: MatchStatus) -> bool:
    """Whether a fixture has an answer. The sweep asks about exactly the statuses this excludes."""
    return status not in REGRESSIVE_STATUSES


def scoreline_label(home: Optional[int], away: Optional[int],
                    pens_home: Optional[int] = None, pens_away: Optional[int] = None) -> Optional[str]:
    """The scoreline as a reader would say it: "1-1", or "0-0 (4-3 pens)" for a shoot-out.

    The shoot-out is appended, never merged. Switzerland 0-0 Colombia won 4-3 on penalties is not
    a 4-3 match, and showing only "0-0" is as wrong for the reader as showing "4-3" would be for
    settlement. Returns None when there is no scoreline to show at all; a shoot-out score without
    a scoreline to attach it to is dropped rather than shown on its own.
    """
    if home is None or away is None:
        return None
    if pens_home is None or pens_away is None:
        return f"{home}-{away}"
    return f"{home}-{away} ({pens_home}-{pens_away} pens)"


def merge_supplied(stored: Dict[str, object], incoming: Dict[str, object]) -> Dict[str, object]:
    """Write through what this provider supplied; leave alone what it did not.

    A ``None`` in ``incoming`` is the provider saying nothing about that field, which is not the
    same as saying the field is empty. The key is still created when it is missing, so a reader
    can tell "asked and unknown" from a key that was never there, but a value already stored is
    never replaced by a silence. This is what stops a fallback provider with no period breakdown
    erasing periods a better-informed provider already wrote.
    """
    for key, value in incoming.items():
        if value is None:
            stored.setdefault(key, None)
        else:
            stored[key] = value
    return stored


def _pair(home: Optional[int], away: Optional[int]) -> Optional[Tuple[int, int]]:
    """One period as the single fact it is: a scoreline, supplied or not.

    Half a scoreline is not a report of a period, so a provider that sends one side and not the
    other is treated as having sent neither rather than as having scored the other side nil.
    """
    if home is None or away is None:
        return None
    return home, away


def played_outcome(home: int, away: int) -> str:
    """The H/D/A that ``predictions.match_results.result`` answers, and the only question it answers.

    THE QUESTION: who won the football that was played? It is the outcome of the ``home_score`` /
    ``away_score`` pair in its own row - extra time included, the shoot-out never - and it is a
    reader's summary of that pair, nothing more. A row whose score reads 2-1 says "H" here, and a
    tie that finished 0-0 and was won 4-3 on penalties says "D", because 0-0 is the football that
    was played and the shoot-out is recorded beside it.

    THE QUESTION IT DOES NOT ANSWER: how a market settles. Markets settle on regulation time,
    which is a different period and sometimes a different answer - a tie of 1-1 at full time and
    2-1 after extra time is "H" here and a draw to every market. That answer is
    :func:`app.services.settlement.regulation_score`, it is computed from ``home_score_ft`` /
    ``away_score_ft``, and it can refuse to answer at all, which this column cannot: it is
    NOT NULL-scored and always says something. Nothing in settlement reads this column, and
    nothing that settles anything ever should.
    """
    if home > away:
        return "H"
    if away > home:
        return "A"
    return "D"


def classify_recovery_outcome(meta, *, settled_before: bool, settled_now: bool) -> Tuple[RecoveryOutcome, str]:
    """
    Which outcome one call produced for one unsettled fixture it covered.

    `meta` is the `SyncMeta` the call left behind: a results call for the fixture's competition
    and day, or a live poll. It is read by attribute rather than imported, because
    match_data_service imports this module. Three of its fields carry the answer:

    * `results_polled` OR `live_polled` is set only once the call chain has returned. Neither being
      set means no provider answered. With `errors` recorded, the chain tried and got nothing, and
      `request_failed` says which way: a request went out and nobody answered it (PROVIDER_ERROR),
      or none ever left - an allowance refused it first, or every provider was cooling down
      (DEFERRED). With no errors, no call was attempted at all - the day held nothing pending, or
      the pass declined to ask - and that is NOT_ASKED. None of the three spends an attempt. A meta
      that does not say whether a request left is read as one that did, which is what every
      caller before `request_failed` existed meant.
    * `source` says where an answer came from. "provider" is the only value meaning somebody was
      asked during this pass; "cache" and "stale-cache" mean the day came out of the store (see
      `RecoveryOutcome.CACHED`), and they are reported apart because a stale copy also says the
      provider is not currently reachable.
    * `errors` may hold entries on a call that succeeded anyway: the chain records every provider
      it gave up on before the one that answered. So a failed call is `results_polled` being
      False, never `errors` being non-empty.

    A LIVE POLL THAT DOES NOT MENTION A FIXTURE IS NOT HANDED HERE. How long the live feed keeps a
    finished match is not known, so its silence about a fixture is not evidence either way; only a
    poll that SETTLED the fixture is classified, as a recovery.

    `settled_before` is this fixture's own state, read before the call. A fixture already settled
    cannot have been recovered by it, so offering one is a caller error.
    """
    if settled_before:
        raise ValueError("this fixture was already settled before the pass; the sweep asks about "
                         "unsettled fixtures only, and a status it did not change is not a recovery")
    asked = bool(getattr(meta, "results_polled", False)) or bool(getattr(meta, "live_polled", False))
    source = getattr(meta, "source", None) or "database"
    provider = getattr(meta, "provider", None) or source
    if settled_now:
        if asked and source == "provider":
            return RecoveryOutcome.RECOVERED, f"a fresh answer from {provider} settled it"
        if asked:
            return RecoveryOutcome.RECOVERED, f"the {source} copy of the day settled it"
        return RecoveryOutcome.RECOVERED, "settled without this sweep's own call"
    if not asked:
        errors = getattr(meta, "errors", None) or []
        if errors and getattr(meta, "request_failed", True):
            return RecoveryOutcome.PROVIDER_ERROR, "; ".join(errors)
        if errors:
            return RecoveryOutcome.DEFERRED, ("no request was made for this fixture: "
                                              + "; ".join(errors))
        return RecoveryOutcome.NOT_ASKED, "no call was made for this fixture"
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


def _parse_instant(value) -> Optional[datetime]:
    """A timestamp the sweep wrote into JSONB, read back as an aware UTC datetime, or None."""
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _aware_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc_label(value) -> str:
    """An instant as a reader sees it in a recorded sentence: "2026-10-08 12:00 UTC"."""
    instant = _parse_instant(value)
    return instant.strftime("%Y-%m-%d %H:%M UTC") if instant else "an unrecorded time"


def recovery_state_of(match) -> Dict[str, object]:
    """What the sweep has recorded for this fixture. Tolerates rows with no metadata at all."""
    return dict((getattr(match, "match_metadata", None) or {}).get("recovery") or {})


def retry_gap(age: timedelta) -> timedelta:
    """The least time between two asks about a fixture this old. See `RETRY_SCHEDULE`.

    Past `RETRY_HORIZON` the last gap still applies: a fixture only gets there without having been
    given up on when no provider answered it (an outage), and it is still owed an answered ask.
    """
    for up_to, gap in RETRY_SCHEDULE:
        if age <= up_to:
            return gap
    return RETRY_SCHEDULE[-1][1]


def _schedule_clock(state: Dict[str, object]) -> Optional[datetime]:
    """The ask the next one is measured from, or None when an ask is owed now.

    The clock is the last ANSWERED ask (`last_attempt_at`). A call that reached nobody learned
    nothing, so it does not push the next ask back: during an outage a due fixture stays due and
    each pass tries again, which is also what keeps the outage visible pass after pass. A fixture
    reopened since its last answered ask is owed one at once.
    """
    last = _parse_instant(state.get("last_attempt_at"))
    if last is None:
        return None
    reopened = _parse_instant(state.get("reopened_at"))
    if reopened is not None and reopened > last:
        return None
    return last


def _next_ask_from(state: Dict[str, object], kickoff: Optional[datetime],
                   now: datetime) -> Optional[datetime]:
    """The earliest moment from `now` at which the schedule allows an ask; None if given up on."""
    if state.get("gave_up_at"):
        return None
    now = _aware_utc(now)
    last = _schedule_clock(state)
    if last is None or kickoff is None:
        return now
    kickoff = _aware_utc(kickoff)
    due = max(now, last)
    # The gap only widens with age, so reading it at the candidate moment and moving the candidate
    # out to it settles within a step per tier.
    for _ in range(len(RETRY_SCHEDULE) + 2):
        gap = retry_gap(due - kickoff)
        if due - last >= gap:
            break
        due = last + gap
    return due


def next_ask_after(match, now: datetime) -> Optional[datetime]:
    """When the schedule next allows an ask about this fixture: `now` if it is due, None if given up on."""
    return _next_ask_from(recovery_state_of(match), getattr(match, "match_date", None), now)


def retry_due(match, now: datetime) -> bool:
    """Whether the retry schedule calls for asking about this fixture on a pass at `now`.

    Never for a fixture given up on (until `MatchRegistry.reopen_retired` reopens it), always for
    one never asked, and otherwise once `retry_gap` - read at the fixture's age now - has passed
    since the last answered ask.
    """
    return _retry_due_from(recovery_state_of(match), getattr(match, "match_date", None), now)


def _retry_due_from(state: Dict[str, object], kickoff: Optional[datetime], now: datetime) -> bool:
    if state.get("gave_up_at"):
        return False
    last = _schedule_clock(state)
    if last is None or kickoff is None:
        return True
    now = _aware_utc(now)
    return now - last >= retry_gap(now - _aware_utc(kickoff)) - RETRY_SLACK


def due_once_stop_is_undone(match, now: datetime) -> bool:
    """Whether the retry schedule would call for an ask at `now` with the row's stop taken off.

    For pricing a pass before it runs (`MatchDataService.recovery_plan`): a stop made by a removed
    rule is undone at the start of the pass, and from then on the fixture is due exactly when its
    recorded asks and its age say so. Reads the row; writes nothing.
    """
    state = recovery_state_of(match)
    for field in ("gave_up_at", "gave_up_reason", "stopped_by"):
        state.pop(field, None)
    return _retry_due_from(state, getattr(match, "match_date", None), now)


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

    @staticmethod
    def team_identity(name: str, scope: comps.TeamScope) -> str:
        """
        The identity string a team row is stored under, for a name and the scope it plays in.

        The "(W)" suffix comes off before the name is normalised, so Spain's women's squad is
        `national_senior_women:spain` in the Women's World Cup and in a friendly alike -- one squad
        is one row however many competitions it plays. The scope in front is what keeps it off the
        men's row and off a Spanish club's row, neither of which a name comparison can do: the
        club-name matcher reads "Spain (W)" and "Spain" as one team, by design and correctly, because
        dropping a trailing qualifier is how "Ipswich" reaches "Ipswich Town".
        """
        return comps.scoped_identity_key(
            scope, match_matching.normalize_team_name(comps.strip_womens_suffix(name)))

    def find_team_by_name(self, name: str, country: Optional[str] = None,
                          scope: comps.TeamScope = comps.DEFAULT_TEAM_SCOPE) -> Optional[Team]:
        """
        Find a stored team by name WITHIN one scope, comparing NORMALISED names in Python.

        The normalised form is not a substring of the stored raw name -- "Borussia Moenchengladbach"
        does not contain "monchengladbach" and "FC Cologne" does not contain "koln" -- so a normalised
        token must never be used as a SQL LIKE pattern. Doing that made every provider switch insert a
        duplicate Team row for exactly those clubs.

        No comparison here crosses a scope, and none of them could decide one if it tried. A row of a
        different scope is not a worse match for this name, it is a different entity with the same
        name, so it is removed from the pool before any name is looked at rather than being ranked
        below the others.

        `scope` defaults to clubs because that is what an unqualified caller is asking about, and
        what every row stored before national-team coverage existed is.
        """
        normalized = match_matching.normalize_team_name(comps.strip_womens_suffix(name))
        if not normalized:
            return None
        identity = comps.scoped_identity_key(scope, normalized)

        def usable(team: Team) -> bool:
            if (team.team_scope or comps.DEFAULT_TEAM_SCOPE.value) != scope.value:
                return False
            return not country or not team.country or team.country in (country, "Unknown")

        # THE IDENTITY IS LOOKED UP BEFORE THE COUNTRY FILTER, AND ACROSS THE WHOLE SCOPE.
        # `identity_key` is UNIQUE and already carries the scope, so a row holding this identity IS
        # this team - there is nothing a country can add to that, and plenty it can take away: the
        # country we were handed is the one this provider spells, and a row stored from another
        # provider may spell it differently or not at all. Filtering first would hide the row, the
        # caller would create a second one carrying the same identity, and the unique index would
        # abort the write - turning a difference of spelling into a failed sync.
        in_scope = [t for t in self._team_pool()
                    if (t.team_scope or comps.DEFAULT_TEAM_SCOPE.value) == scope.value]
        stored = [t for t in in_scope if t.identity_key == identity]
        if stored:
            return stored[0]
        pool = [t for t in in_scope if usable(t)]
        exact = [t for t in pool
                 if match_matching.normalize_team_name(comps.strip_womens_suffix(t.name)) == normalized]
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

    def upsert_team(self, team: ProviderTeam, country: Optional[str] = None,
                    competition_key: Optional[str] = None) -> Team:
        """
        Persist one provider team and return the internal row.

        `competition_key` is the canonical competition the fixture belongs to, and it decides the
        scope: clubs play club competitions and countries play national-team ones, and that is known
        before a single character of the name is compared. `None` is a competition no canonical key
        matched, which reads as a club competition.

        A national-team competition's `country` is the confederation's territory -- "World" for every
        FIFA competition -- so it is not written onto the team. It is the competition's country, not
        the team's, and storing it would file every country in the world under one of seven values.
        """
        scope = self._scope_for(competition_key, team.name)
        if scope in comps.NATIONAL_SCOPES:
            country = None
        ref = self.get_ref("team", team.provider, team.external_id)
        if ref:
            existing = self.db.query(Team).filter(Team.id == ref.entity_id).first()
            if existing:
                if team.logo and not existing.logo_url:
                    existing.logo_url = team.logo
                return existing
        identity = self.team_identity(team.name, scope)
        existing = self.find_team_by_name(team.name, country or team.country, scope)
        if existing is None:
            # `identity_key` is UNIQUE, so creating a row that claims a taken identity does not
            # produce a duplicate - it aborts the flush and takes the whole sync batch with it. A
            # row already holding this identity is this team by definition, so it is adopted rather
            # than competed with. `find_team_by_name` normally returns it; this is the narrow case
            # where its name and country comparisons could not, and the identity still can.
            existing = self._team_by_identity(identity)
        matched_by = "name"
        if existing is None:
            existing = Team(id=uuid.uuid4(), name=team.name, short_name=(team.short_name or team.name)[:50],
                            country=country or team.country or "Unknown", logo_url=team.logo,
                            external_api_id=f"{team.provider}:{team.external_id}", external_api_source=team.provider,
                            is_active=True, team_scope=scope.value, identity_key=identity)
            self.db.add(existing)
            self.db.flush()
            matched_by = "provider_id"
        else:
            if team.logo and not existing.logo_url:
                existing.logo_url = team.logo
            if existing.identity_key is None and not self._identity_is_taken(identity):
                # A row written before identities were stored, or by a path that never knew the
                # competition. It is adopted into the scope it was just resolved in, so the next
                # lookup reaches it by key; the check above is what keeps the adoption from ever
                # being the write that violates the unique index.
                existing.identity_key = identity
        self.set_ref("team", existing.id, team.provider, team.external_id, confidence="exact", matched_by=matched_by,
                     metadata={"name": team.name})
        return existing

    def _team_by_identity(self, identity: str) -> Optional[Team]:
        """The row holding this identity, if any. The column is UNIQUE, so there is at most one."""
        return next((t for t in self._team_pool() if t.identity_key == identity), None)

    def _identity_is_taken(self, identity: str) -> bool:
        return self._team_by_identity(identity) is not None

    @staticmethod
    def _scope_for(competition_key: Optional[str], team_name: str) -> comps.TeamScope:
        """
        The scope of a team in a competition a PROVIDER named, which may be a key we do not carry.

        `comps.team_scope` raises on an unknown key, and that is right for our own callers: naming a
        competition that does not exist is a mistake worth stopping on. Here the key arrives inside a
        fixture, and one unrecognised key must not take the rest of the batch down with it. The row
        is stored as a club team -- the same thing an unrecognised competition has always produced --
        and the key is named in the log.
        """
        try:
            return comps.team_scope(competition_key, team_name)
        except KeyError:
            logger.warning("Fixture names competition %r, which is not in the registry; "
                           "%r is stored as a club team", competition_key, team_name)
            return comps.team_scope(None, team_name)

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
        home = self.upsert_team(fixture.home, fixture.competition.country, fixture.competition.key)
        away = self.upsert_team(fixture.away, fixture.competition.country, fixture.competition.key)

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
        # And only a kickoff the provider actually stated: a results row with a date and no time
        # is mapped to midnight, and writing that over the stored kickoff would invent one.
        if not fixture.kickoff_supplied:
            if match.match_date is not None and \
                    _aware_utc(match.match_date).date() != _aware_utc(fixture.kickoff_utc).date():
                logger.warning("Provider %s reports match %s on %s without a kickoff time (stored %s); "
                               "kickoff left unchanged", fixture.provider, match.id,
                               fixture.kickoff_utc.date(), match.match_date)
        elif self._owns_match(match, fixture.provider):
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
        # Who spoke last and what they said about the state of play: overwritten every sync,
        # because that is what these fields are.
        meta.update({
            "provider": fixture.provider,
            "provider_status": fixture.status,
            "minute": fixture.minute,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        })
        # The scores are facts about the match, not about this sync, so a provider that sends none
        # of them leaves the ones already stored standing.
        merge_supplied(meta, {
            "home_score": fixture.home_score,
            "away_score": fixture.away_score,
            "ht_home_score": fixture.ht_home_score,
            "ht_away_score": fixture.ht_away_score,
            "ft_home_score": fixture.ft_home_score,
            "ft_away_score": fixture.ft_away_score,
            "et_home_score": fixture.et_home_score,
            "et_away_score": fixture.et_away_score,
            "ps_home_score": fixture.ps_home_score,
            "ps_away_score": fixture.ps_away_score,
        })
        # A MATCH THAT WAS NOT PLAYED HAS NO SCORE, and keeping one is the cost of the merge above.
        # A fixture abandoned or postponed after kicking off carries whatever it had reached while
        # it was live, and `merge_supplied` is deliberately unable to un-store a value - so without
        # this, "postponed" would be published beside a 1-0 that stands for nothing and that no
        # later sync can take back. A void state is a statement that there is no result, so the
        # scores go with it; the half-time pair goes too, for the same reason.
        if match.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
            for key in ("home_score", "away_score", "ht_home_score", "ht_away_score",
                        "ft_home_score", "ft_away_score", "et_home_score", "et_away_score",
                        "ps_home_score", "ps_away_score"):
                meta.pop(key, None)
        # Built from the merged values rather than from the fixture, so a refresh that carries no
        # shoot-out does not shorten "0-0 (4-3 pens)" back to "0-0".
        meta["scoreline"] = scoreline_label(meta.get("home_score"), meta.get("away_score"),
                                            meta.get("ps_home_score"), meta.get("ps_away_score"))
        match.match_metadata = meta
        if fixture.status == STATUS_FINISHED and fixture.home_score is not None and fixture.away_score is not None:
            result = self.db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
            outcome = played_outcome(fixture.home_score, fixture.away_score)
            if result is None:
                result = MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=fixture.home_score,
                                     away_score=fixture.away_score, result=outcome)
                self.db.add(result)
            else:
                result.home_score, result.away_score, result.result = fixture.home_score, fixture.away_score, outcome
            self._apply_periods(result, fixture)
        self.db.flush()

    def _apply_periods(self, result: MatchResult, fixture: ProviderFixture) -> None:
        """Store each period this provider supplied, and leave the rest of the row alone.

        A period is written only when the fixture carries one. A provider that sends no period
        breakdown - API-Football and TheSportsDB both send none, and both are configured as
        fallbacks behind Live Score - therefore changes no period column at all, and a tie already
        ingested with its full time, extra time and shoot-out apart keeps them when a later refresh
        comes from a source that knows less. The absence of a period is not a report that the
        period was not played, and a write that treated it as one would silently destroy the only
        record of a 0-0 that was won 4-3 on penalties.

        Nothing here derives one period from another, and nothing here decides what settles:
        settlement reads ``home_score_ft`` and states its own rule for a row that has none
        (:func:`app.services.settlement.regulation_score`).
        """
        merged = merge_supplied(
            {"ht": (result.home_score_ht, result.away_score_ht),
             "ft": (result.home_score_ft, result.away_score_ft),
             "et": (result.home_score_et, result.away_score_et),
             "pens": (result.home_score_pens, result.away_score_pens)},
            {"ht": _pair(fixture.ht_home_score, fixture.ht_away_score),
             "ft": _pair(fixture.ft_home_score, fixture.ft_away_score),
             "et": _pair(fixture.et_home_score, fixture.et_away_score),
             "pens": _pair(fixture.ps_home_score, fixture.ps_away_score)},
        )
        result.home_score_ht, result.away_score_ht = merged["ht"]
        result.home_score_ft, result.away_score_ft = merged["ft"]
        result.home_score_et, result.away_score_et = merged["et"]
        result.home_score_pens, result.away_score_pens = merged["pens"]

        meta = dict(result.result_metadata or {})
        meta["provider"] = fixture.provider
        # `beyond_regulation` is the fact settlement needs and the one the pipeline used to throw
        # away: the provider's "AP"/"AET" marker went into ProviderFixture.minute and no further,
        # so no stored result had ever carried it. It is recorded here as a fact about the tie and
        # has three values, because there are three situations: True on evidence it went past 90,
        # False when a provider that enumerates periods reported none past 90, and None when
        # nobody said - which is every API-Football row, every TheSportsDB row, and every one of
        # the 48 results stored before this column existed.
        self._merge_beyond_regulation(result, meta, fixture)
        if fixture.minute is not None:
            meta["period_marker"] = fixture.minute
        else:
            meta.setdefault("period_marker", None)
        # The scoreline a reader remembers, built from the row as it now stands rather than from
        # this one fixture, so a refresh with no shoot-out in it does not turn "0-0 (4-3 pens)"
        # back into "0-0". Stored rather than re-derived so that everything showing this tie shows
        # the same line.
        meta["scoreline"] = scoreline_label(result.home_score, result.away_score,
                                            result.home_score_pens, result.away_score_pens)
        result.result_metadata = meta

    def _merge_beyond_regulation(self, result: MatchResult, meta: Dict[str, object],
                                 fixture: ProviderFixture) -> None:
        """Record whether the tie went past 90 minutes, without ever unlearning it.

        A provider that does not know (``None``) leaves the stored answer as it is. A provider
        that reports no extra time for a tie already recorded as having gone past 90 is
        contradicting positive evidence - a stored extra-time or shoot-out score, or an earlier
        report - with the absence of it, so the stronger claim is kept and the disagreement is
        logged for a person rather than resolved by whoever synced last. The row's own period
        columns are read for that, not just the flag, so the flag can never end up saying a tie
        ended at 90 while the columns beside it hold its shoot-out.
        """
        incoming = fixture.went_beyond_regulation
        if incoming is None:
            meta.setdefault("beyond_regulation", None)
            return
        stored_evidence = any(v is not None for v in (result.home_score_et, result.away_score_et,
                                                      result.home_score_pens, result.away_score_pens))
        if incoming is False and (stored_evidence or meta.get("beyond_regulation") is True):
            logger.warning("Provider %s reports no play past 90 minutes for match_result %s, which is "
                           "stored as going beyond regulation (%s); keeping the stored answer",
                           fixture.provider, result.id, meta.get("period_marker"))
            return
        meta["beyond_regulation"] = incoming

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
                         max_age: timedelta = STALE_SWEEP_MAX_AGE) -> List[Match]:
        """
        Fixtures still SCHEDULED or LIVE at or before `cutoff` that the sweep has not given up on.

        Neither refresh reaches these on its own. The live poll considers a match for
        `UNSETTLED_GRACE` after kickoff, and the results task only looks back
        `SYNC_RESULTS_LOOKBACK_DAYS` days, so a fixture whose final score did not arrive inside
        those windows is asked about by the recovery pass or by nobody.

        Two populations. A fixture that kicked off within `max_age` of `now` is selected whether or
        not anything has asked about it yet. An older one is selected only if the sweep has already
        been asking about it, i.e. it carries recovery bookkeeping: it is either still owed an
        answered ask (an outage can carry a fixture past the horizon, and the horizon may only be
        applied after an answer), or `reopen_retired` has just reopened it. An older fixture the
        sweep never touched predates it and is not started on.

        Oldest first. A fixture given up on is not returned: see `record_recovery_attempt`.
        """
        now = now or datetime.now(timezone.utc)
        floor = _naive_utc(now - max_age)
        rows = self.db.query(Match).filter(
            Match.status.in_(REGRESSIVE_STATUSES),
            Match.match_date <= _naive_utc(cutoff),
            or_(Match.match_date >= floor, Match.match_metadata.has_key("recovery")),
        )
        if league_ids is not None:
            rows = rows.filter(Match.league_id.in_(list(league_ids)))
        return [m for m in rows.order_by(Match.match_date.asc()).all()
                if not recovery_state_of(m).get("gave_up_at")]

    def stale_unsettled_days(self, now: datetime, lookback_days: int,
                             league_ids: Optional[Iterable[uuid.UUID]] = None,
                             max_days: int = STALE_SWEEP_MAX_DAYS, **limits) -> List[date]:
        """
        The days OLDER than the results lookback holding a fixture the retry schedule says is due.

        Oldest first and capped at `max_days`, because a results call costs one provider request
        per competition per day. A day holding only fixtures that were asked about recently enough
        is not offered: `retry_due` is the one schedule every caller shares.

        A day the results task already covers is never offered here. The task walks back from
        today through `lookback_days`, so the sweep starts the instant before the earliest of those
        days: paying twice for one day would spend the recovery allowance on a day that was going
        to be asked about anyway.
        """
        covered_from = now.date() - timedelta(days=max(int(lookback_days), 0))
        cutoff = min(now - UNSETTLED_GRACE,
                     datetime.combine(covered_from, datetime.min.time(),
                                      tzinfo=timezone.utc) - timedelta(microseconds=1))
        days: List[date] = []
        for m in self.unsettled_before(cutoff, league_ids, now=now, **limits):
            if not retry_due(m, now):
                continue
            day = m.match_date.date()
            if day not in days:
                days.append(day)
            if len(days) >= max_days:
                break
        return days

    def recoverable_unsettled(self, now: datetime, league_ids: Optional[Iterable[uuid.UUID]] = None,
                              grace: timedelta = UNSETTLED_GRACE, **limits) -> List[Match]:
        """Every fixture still unsettled `grace` after kickoff and not given up on, oldest first.

        `stale_unsettled_days` answers a narrower question - which days BEHIND the results lookback
        are worth reopening - because that is the part that costs the recovery allowance. This is
        the whole population the pass reports on, whichever day it sits on: a range on the kickoff
        column, so which side of a UTC midnight a fixture sits on changes nothing about whether it
        is selected. Whether it is ASKED about on a given pass is `retry_due`'s decision.
        """
        return self.unsettled_before(now - grace, league_ids, now=now, **limits)

    def recovered_since(self, since: datetime, kicked_off_before: datetime) -> List[Match]:
        """Settled fixtures the sweep recovered at or after `since` that kicked off before
        `kicked_off_before`: results that arrived later than a kickoff-dated window reaches."""
        rows = self.db.query(Match).filter(Match.status.in_(TERMINAL_STATUSES),
                                           Match.match_date < _naive_utc(kicked_off_before),
                                           Match.match_metadata.has_key("recovery"))
        floor = _aware_utc(since)
        out = []
        for match in rows.order_by(Match.match_date.asc()).all():
            recovered_at = _parse_instant(recovery_state_of(match).get("recovered_at"))
            if recovered_at is not None and recovered_at >= floor:
                out.append(match)
        return out

    # ------------------------------------------------------ what the archive has shown us
    def _archive_store(self, key: str, create: bool = False) -> Tuple[Optional[League], Dict[str, Dict]]:
        league = self.ensure_canonical_league(key) if create else self.league_for_key(key)
        if league is None:
            return None, {}
        store = (league.league_metadata or {}).get("archive_observations") or {}
        return league, {day: dict(entry) for day, entry in store.items()}

    def _save_archive_store(self, league: League, store: Dict[str, Dict]) -> None:
        kept = dict(sorted(store.items(), reverse=True)[:ARCHIVE_OBSERVATIONS_KEPT])
        meta = dict(league.league_metadata or {})
        meta["archive_observations"] = kept
        league.league_metadata = meta
        self.db.flush()

    def archive_observation(self, key: Optional[str], day: date) -> Dict[str, object]:
        """What the archive returned for `key` on `day` when last asked. UNKNOWN if never asked.

        Only a successful answer sets the state. A call that failed leaves the state as it was and
        is recorded beside it (`last_failed_at`, `last_failure`), because "we could not ask" says
        nothing about what the archive holds.
        """
        entry: Dict[str, object] = {}
        if key:
            entry = dict(self._archive_store(key)[1].get(day.isoformat()) or {})
        entry.setdefault("state", ArchiveState.UNKNOWN.value)
        return entry

    def archive_observations(self, key: str) -> Dict[str, Dict]:
        """Every dated observation kept for `key`, keyed by ISO date."""
        return self._archive_store(key)[1]

    def record_archive_observation(self, key: str, day: date, rows: int, *, provider: Optional[str],
                                   asked_at: datetime) -> Dict[str, object]:
        """Write down what one successful results call returned for one competition and date."""
        league, store = self._archive_store(key, create=True)
        stamp = _aware_utc(asked_at).isoformat()
        entry = store.get(day.isoformat()) or {}
        state = ArchiveState.ANSWERED if rows > 0 else ArchiveState.EMPTY
        entry.update({"state": state.value, "rows": int(rows), "asked_at": stamp,
                      "provider": provider})
        entry.setdefault("first_asked_at", stamp)
        entry["times_asked"] = int(entry.get("times_asked") or 0) + 1
        if state is ArchiveState.ANSWERED:
            entry["last_answered_at"] = stamp
        store[day.isoformat()] = entry
        self._save_archive_store(league, store)
        return entry

    def record_archive_failure(self, key: str, day: date, error: str, *, at: datetime) -> None:
        """Note a results call for `key` on `day` that no provider answered. The state is untouched."""
        league, store = self._archive_store(key, create=True)
        entry = store.get(day.isoformat()) or {}
        entry["last_failed_at"] = _aware_utc(at).isoformat()
        entry["last_failure"] = (error or "no provider answered")[:200]
        store[day.isoformat()] = entry
        self._save_archive_store(league, store)

    def archive_answered_through(self, key: Optional[str],
                                 asked_after: Optional[datetime] = None) -> Optional[date]:
        """The latest date the archive has returned rows for in `key`, optionally only counting
        answers given after `asked_after`. None when no such answer has been observed."""
        if not key:
            return None
        latest: Optional[date] = None
        for iso, entry in self._archive_store(key)[1].items():
            answered_at = _parse_instant(entry.get("last_answered_at"))
            if answered_at is None:
                continue
            if asked_after is not None and answered_at <= _aware_utc(asked_after):
                continue
            try:
                day = date.fromisoformat(iso)
            except ValueError:
                continue
            latest = day if latest is None or day > latest else latest
        return latest

    def reopen_candidates(self, league_ids: Optional[Iterable[uuid.UUID]] = None
                          ) -> List[Tuple[Match, Dict[str, object]]]:
        """Every given-up fixture the archive has since moved past, with the observation that did it.

        Read-only: `reopen_retired` is what acts on it, and `MatchDataService.recovery_plan` prices
        a pass with it without writing anything.

        A fixture qualifies when its competition's archive has returned rows, AFTER we stopped
        asking, for a date on or after the fixture's own - the archive now reaching that far is
        the thing we stopped waiting for - and when, at the moment we stopped, it had not already
        answered that far. If it had, it covered the date then and still had nothing, and reopening
        on more of the same would only repeat that ask. For the same reason a fixture whose own
        date has answered with rows since we stopped, without settling it, does not qualify.
        """
        rows = self.db.query(Match).filter(Match.status.in_(REGRESSIVE_STATUSES),
                                           Match.match_metadata.has_key("recovery"))
        if league_ids is not None:
            rows = rows.filter(Match.league_id.in_(list(league_ids)))
        found: List[Tuple[Match, Dict[str, object]]] = []
        for match in rows.order_by(Match.match_date.asc()).all():
            state = recovery_state_of(match)
            stopped_at = _parse_instant(state.get("gave_up_at"))
            if stopped_at is None:
                continue
            key = self.canonical_key_for_league(getattr(match, "league_id", None))
            through = self.archive_answered_through(key, asked_after=stopped_at)
            fixture_day = match.match_date.date()
            if through is None or through < fixture_day:
                continue
            try:
                before = date.fromisoformat(str(state.get("archive_answered_through") or ""))
            except ValueError:
                before = None
            if before is not None and before >= fixture_day:
                continue
            # The fixture's own date answered with rows after we stopped and did not settle it:
            # that answer already covered it, so there is nothing new to ask.
            own = _parse_instant(self.archive_observation(key, fixture_day).get("last_answered_at"))
            if own is not None and own > stopped_at:
                continue
            found.append((match, {"date": through, **self.archive_observation(key, through)}))
        return found

    def reopen_retired(self, now: datetime,
                       league_ids: Optional[Iterable[uuid.UUID]] = None) -> List[Match]:
        """Put back in the sweep every fixture `reopen_candidates` names.

        GIVING UP IS A BUDGET DECISION, and this undoes it on evidence it did not have. WHAT THAT
        EVIDENCE CAN BE is narrow, and nothing here goes looking for it: the observations are the
        ones results calls record anyway (`MatchDataService._sync_results`), and a results call is
        made for a competition-day only when some OTHER fixture of that competition is unsettled
        and due. Nothing asks the archive on a stopped fixture's behalf. So a stopped fixture is
        reopened only if such a call happens and returns rows dated on or after its date; a
        competition that plays no unsettled fixture again never reopens anything.

        Deciding costs nothing. A reopened fixture is owed one ask at once; if that answer still
        holds nothing it is given up on again with the archive's reach recorded, and the same
        evidence does not reopen it twice. The previous stop is kept on the row.
        """
        reopened: List[Match] = []
        for match, seen in self.reopen_candidates(league_ids):
            state = recovery_state_of(match)
            stops = list(state.get("previous_stops") or [])
            stops.append({"gave_up_at": state.get("gave_up_at"),
                          "gave_up_reason": state.get("gave_up_reason"),
                          "attempts": state.get("attempts")})
            state["previous_stops"] = stops[-5:]
            for field in ("gave_up_at", "gave_up_reason", "stopped_by", "archive_answered_through"):
                state.pop(field, None)
            state["reopened_at"] = _aware_utc(now).isoformat()
            state["reopened_because"] = (
                f"after we stopped asking, the archive returned {seen.get('rows')} row(s) for this "
                f"competition dated {seen['date'].isoformat()} (asked "
                f"{_utc_label(seen.get('asked_at'))}), on or after this match's date")
            self._store_recovery(match, state)
            logger.info("Reopening match %s (%s): %s", match.id, match.match_date,
                        state["reopened_because"])
            reopened.append(match)
        return reopened

    # ----------------------------------------------- stops a removed rule made, undone
    def superseded_stops(self, league_ids: Optional[Iterable[uuid.UUID]] = None) -> List[Match]:
        """Unsettled fixtures stopped by a rule this installation no longer applies. Read-only.

        A stop in force carries `stopped_by` naming a current policy (`CURRENT_STOP_POLICIES`).
        Anything else holding `gave_up_at` was written by a rule that has been removed: the
        three-attempts rule, and the rule that stopped national-team fixtures six hours after
        kickoff, both of which wrote `gave_up_at` and `gave_up_reason` and no `stopped_by`. Oldest
        first.
        """
        rows = self.db.query(Match).filter(Match.status.in_(REGRESSIVE_STATUSES),
                                           Match.match_metadata.has_key("recovery"))
        if league_ids is not None:
            rows = rows.filter(Match.league_id.in_(list(league_ids)))
        out: List[Match] = []
        for match in rows.order_by(Match.match_date.asc()).all():
            state = recovery_state_of(match)
            if state.get("gave_up_at") and state.get("stopped_by") not in CURRENT_STOP_POLICIES:
                out.append(match)
        return out

    def undo_superseded_stops(self, now: datetime,
                              league_ids: Optional[Iterable[uuid.UUID]] = None) -> List[Match]:
        """Undo every stop a current policy did not make, and put the fixture on the retry schedule.

        A STOP IS NOT RENAMED. Serving an old stop as `stopped_by: "retry_budget"` would attribute
        it to a policy that did not make it, and leaving it in place would keep the fixture stopped
        under a rule that no longer exists. So the stop is taken off the row: `gave_up_at`,
        `gave_up_reason` and whatever `stopped_by` it had are removed, and from then on the fixture
        is asked about exactly as the current schedule says for its age and its recorded asks -
        which, past the horizon, is one more answered ask and then a stop the current policy does
        make, recorded as one.

        What the old rule concluded in prose is WITHDRAWN rather than carried over: its stop reason
        and its last outcome detail were written by a rule whose premises were removed with it (one
        of them asserted that a competition's archive answers nothing, which the recorded archive
        observations do not show). The facts beside them stay: the count of answered asks, when
        they were made, what the last outcome was, and when the old stop was made, kept under
        `previous_stops` with the moment it was undone.

        Makes no request. Written for the recovery pass to run on every pass, so a stop like this
        is undone on this installation's own clock with nobody having to find it.
        """
        undone: List[Match] = []
        stamp = _aware_utc(now).isoformat()
        for match in self.superseded_stops(league_ids):
            state = recovery_state_of(match)
            withdrawn = [field for field in ("gave_up_reason", "last_outcome_detail") if state.get(field)]
            stops = list(state.get("previous_stops") or [])
            stops.append({"gave_up_at": state.get("gave_up_at"),
                          "attempts": state.get("attempts"),
                          "stopped_by": state.get("stopped_by") or None,
                          "undone_at": stamp,
                          "withdrawn": withdrawn})
            state["previous_stops"] = stops[-5:]
            for field in ("gave_up_at", "gave_up_reason", "stopped_by", "archive_answered_through",
                          "last_outcome_detail", "next_ask_after"):
                state.pop(field, None)
            state["stop_undone_at"] = stamp
            state["stop_undone_because"] = (
                "the stop recorded on this fixture was made by a rule this installation no longer "
                "applies; it records no current policy as having made it, so it was undone and the "
                "fixture returned to the retry schedule")
            self._note_next_ask(match, state, now)
            self._store_recovery(match, state)
            logger.info("Undid a stop made under a removed rule on match %s (%s, still %s); it is "
                        "back on the retry schedule", match.id, match.match_date, match.status)
            undone.append(match)
        return undone

    # ------------------------------------------------------------ the row's own bookkeeping
    @classmethod
    def overdue_state(cls, match: Match, now: datetime,
                      grace: timedelta = UNSETTLED_GRACE) -> Dict[str, object]:
        """Whether this fixture is past the point of still reading as in play, and what is known.

        Two different facts, kept apart:

        * `overdue` -- the fixture is unsettled and kickoff was longer ago than `grace`, this
          application's own polling window. A status of "LIVE, HT" five hours after kickoff is the
          absence of a report, and this is the fact a reader has to be shown instead.
        * `unresolved` -- the sweep has stopped asking, at a recorded moment, for a recorded
          reason. It says we stopped paying, never that no result exists. `stopped_by` is the
          policy the ROW records as having made the stop, and None when it records none: that is a
          stop from before the field existed, made by a rule since removed, which
          `undo_superseded_stops` undoes on the next recovery pass rather than attributing it to
          the retry budget.

        `last_outcome` is what the last call covering the fixture actually got, so "the provider
        answered with nothing" (fresh_unanswered) and "nobody could reach the provider"
        (provider_error) stay distinguishable. Nothing here reads or writes a score.
        """
        state = recovery_state_of(match)
        age = now - _aware_utc(match.match_date)
        overdue = not is_settled(match.status) and age > grace
        upcoming = next_ask_after(match, now)
        return {
            "overdue": overdue,
            "unresolved": bool(state.get("gave_up_at")),
            "reason": state.get("gave_up_reason"),
            "stopped_by": (state.get("stopped_by") or None) if state.get("gave_up_at") else None,
            "minutes_since_kickoff": int(age.total_seconds() // 60),
            "attempts": int(state.get("attempts") or 0),
            "provider_errors": int(state.get("provider_errors") or 0),
            "cached_passes": int(state.get("cached_passes") or 0),
            "deferrals": int(state.get("deferrals") or 0),
            "last_outcome": state.get("last_outcome"),
            "last_outcome_detail": state.get("last_outcome_detail"),
            "archive": state.get("archive"),
            "next_ask_after": upcoming.isoformat() if upcoming else None,
        }

    @staticmethod
    def recovery_state(match: Match) -> Dict[str, object]:
        """What the sweep has already tried for this fixture, as stored on the row."""
        return recovery_state_of(match)

    def _store_recovery(self, match: Match, state: Dict[str, object]) -> Dict[str, object]:
        """Put the sweep's bookkeeping back on the row. JSONB is replaced whole, never mutated."""
        meta = dict(match.match_metadata or {})
        meta["recovery"] = state
        match.match_metadata = meta
        self.db.flush()
        return state

    def _stop_reason(self, state: Dict[str, object], horizon: timedelta) -> str:
        """The sentence written on the row when the sweep stops: what we did, what came back, that
        stopping was a budget decision, and what - exactly - could still make us ask again. It
        claims nothing about whether a result exists, and it promises nothing the code does not
        do: nothing asks about the match once it is stopped, and the one thing that reopens it is
        an answer to a results call made for another fixture (`reopen_retired`)."""
        attempts = int(state.get("attempts") or 0)
        errors = int(state.get("provider_errors") or 0)
        text = (f"We asked the results provider {attempts} time{'' if attempts == 1 else 's'}, most "
                f"recently {_utc_label(state.get('last_attempt_at'))}, and each answer it gave held "
                f"no result for this match.")
        if errors:
            text += (f" {errors} other request{'' if errors == 1 else 's'} went out and got no "
                     f"answer, and {'is' if errors == 1 else 'are'} not counted.")
        text += (f" We stopped at the {horizon.days}-day results horizon of our request budget: a "
                 f"limit on what we spend, not evidence that no result exists. No further request "
                 f"is made on this match's behalf. It is asked about once more only if a results "
                 f"request we make later, for another unsettled match in this competition, returns "
                 f"results dated on or after this match's date when none that recent had come back "
                 f"before we stopped.")
        return text

    def _give_up(self, match: Match, state: Dict[str, object], now: datetime,
                 horizon: timedelta) -> None:
        key = self.canonical_key_for_league(getattr(match, "league_id", None))
        through = self.archive_answered_through(key)
        state["gave_up_at"] = now.isoformat()
        state["gave_up_reason"] = self._stop_reason(state, horizon)
        state["stopped_by"] = STOP_POLICY
        # What the archive had reached when we stopped, so `reopen_retired` can tell new reach from
        # reach we had already seen.
        state["archive_answered_through"] = through.isoformat() if through else None
        state.pop("next_ask_after", None)
        logger.warning("Stopped asking about match %s (%s, still %s) under the retry budget after "
                       "%s answered ask(s). It keeps its stored status.",
                       match.id, match.match_date, match.status, state.get("attempts"))

    def _note_next_ask(self, match: Match, state: Dict[str, object], now: datetime) -> None:
        upcoming = _next_ask_from(state, getattr(match, "match_date", None), now)
        if upcoming is None:
            state.pop("next_ask_after", None)
        else:
            state["next_ask_after"] = upcoming.isoformat()

    def record_recovery_attempt(self, match: Match, now: Optional[datetime] = None,
                                detail: str = "", archive: Optional[Dict[str, object]] = None,
                                max_age: timedelta = RETRY_HORIZON) -> Dict[str, object]:
        """
        Count one answered ask against a fixture, and stop asking when the schedule has run out.

        An attempt is `RecoveryOutcome.FRESH_UNANSWERED` and nothing else: the provider was asked
        about the fixture's competition and day, answered, and had no result for it. It moves the
        retry schedule's clock (`last_attempt_at`).

        THE ONLY PLACE THE SWEEP GIVES UP, and so it only ever gives up straight after an answer.
        If the next ask the schedule allows would fall past `max_age` after kickoff, the fixture is
        given up on: `gave_up_at`, `stopped_by = "retry_budget"` and a reason saying how many times
        we asked, when last, and that stopping is a budget decision. `unsettled_before` then skips
        the fixture unless `reopen_retired` puts it back. Only bookkeeping moves: the status, the
        scores and the result are untouched, because a score nobody reported is not a score.
        """
        now = now or datetime.now(timezone.utc)
        state = recovery_state_of(match)
        attempts = int(state.get("attempts") or 0) + 1
        state["attempts"] = attempts
        # Written only by the attempt that IS the first. A row that already counted attempts before
        # this field existed has no record of when the first was, and stamping this one's time on
        # it would date the chase from its fourth ask; the field stays absent there, as unknown.
        if attempts == 1:
            state.setdefault("first_attempt_at", now.isoformat())
        state["last_attempt_at"] = now.isoformat()
        state["last_outcome"] = RecoveryOutcome.FRESH_UNANSWERED.value
        state["last_outcome_at"] = now.isoformat()
        if detail:
            state["last_outcome_detail"] = detail
        if archive:
            state["archive"] = dict(archive)
        if not state.get("gave_up_at"):
            age = now - _aware_utc(match.match_date)
            if age + retry_gap(age) > max_age:
                self._give_up(match, state, now, max_age)
            else:
                self._note_next_ask(match, state, now)
        return self._store_recovery(match, state)

    def _settled_by(self, match: Match) -> str:
        """What the row now says the result was, for the recovery note. Read, never invented."""
        result = self.db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
        if result is None or result.home_score is None or result.away_score is None:
            return match.status.value
        return f"{match.status.value} {result.home_score}-{result.away_score}"

    def record_recovery_outcome(self, match: Match, outcome: RecoveryOutcome, detail: str = "",
                                now: Optional[datetime] = None,
                                archive: Optional[Dict[str, object]] = None,
                                max_age: timedelta = RETRY_HORIZON,
                                deferred_because: Optional[Iterable[str]] = None) -> Dict[str, object]:
        """
        Write down what one call learned about this fixture, counting it only if it counts.

        FRESH_UNANSWERED is the one outcome that spends an attempt, and it goes straight to
        `record_recovery_attempt`. The others each keep their own counter and never move
        `attempts`, never move the retry schedule and never give a fixture up: PROVIDER_ERROR
        (a request went out and nobody answered it), CACHED (a stored answer), DEFERRED (no request
        was made). RECOVERED closes the fixture out with what settled it. NOT_ASKED writes nothing,
        because nothing happened to the fixture.

        A DEFERRED ask records WHY nothing was sent (`deferred_because`, the kinds `SyncMeta.not_sent`
        names: "our_allowance", "provider_allowance", "cooling_down", "not_configured"), so the
        reason a reader is given can be the true one - "held back by our own allowance" is not
        true of an ask skipped while the provider cooled down after a failure.
        """
        now = now or datetime.now(timezone.utc)
        if outcome is RecoveryOutcome.FRESH_UNANSWERED:
            return self.record_recovery_attempt(match, now, detail=detail, archive=archive,
                                                max_age=max_age)
        state = recovery_state_of(match)
        if outcome is RecoveryOutcome.NOT_ASKED:
            return state
        state["last_outcome"] = outcome.value
        state["last_outcome_at"] = now.isoformat()
        if detail:
            state["last_outcome_detail"] = detail
        if archive:
            state["archive"] = dict(archive)
        if outcome is RecoveryOutcome.RECOVERED:
            state["recovered_at"] = now.isoformat()
            state["recovered_as"] = self._settled_by(match)
            state["recovered_by"] = detail or "settled during the sweep"
            state.pop("next_ask_after", None)
            return self._store_recovery(match, state)
        if outcome is RecoveryOutcome.PROVIDER_ERROR:
            state["provider_errors"] = int(state.get("provider_errors") or 0) + 1
            state["last_provider_error_at"] = now.isoformat()
            if detail:
                state["last_provider_error"] = detail[:300]
        elif outcome is RecoveryOutcome.CACHED:
            state["cached_passes"] = int(state.get("cached_passes") or 0) + 1
            state["last_cached_at"] = now.isoformat()
        elif outcome is RecoveryOutcome.DEFERRED:
            state["deferrals"] = int(state.get("deferrals") or 0) + 1
            state["last_deferred_at"] = now.isoformat()
            state["last_deferred_because"] = sorted(set(deferred_because or [])) or None
        if not state.get("gave_up_at"):
            self._note_next_ask(match, state, now)
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
