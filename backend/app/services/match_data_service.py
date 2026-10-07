"""
Match data orchestration: provider chain with fallbacks, Redis caching, request-budget aware
live polling, stale-data degradation, and persistence through the MatchRegistry.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from sqlalchemy import DateTime, case, cast, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import League, Match, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_health import classify_provider_error
from app.services.match_registry import (
    RELISTED_KEY, STALE_SWEEP_MAX_DAYS, UNSETTLED_GRACE, MatchRegistry, RecoveryOutcome,
    classify_recovery_outcome, due_once_stop_is_undone, is_settled, next_ask_after,
    recovery_state_of, retry_due,
)
from app.services.providers import competitions as comps
from app.services.providers.base import (
    MatchDataProvider, ProviderCannotServe, ProviderError, ProviderFixture,
    ProviderNotConfiguredError, ProviderQuotaError, ProviderAuthError, ProviderRequestNotSent,
    ProviderStanding, ProviderUnavailableError, parse_utc,
)
from app.services.providers.registry import data_provider_chain

logger = logging.getLogger(__name__)

STATUS_KEY = "provider:status:{name}"
COOLDOWN_KEY = "provider:cooldown:{name}"
AUTH_COOLDOWN_SECONDS = 30 * 60        # rejected credentials: retry every 30 minutes, not on every page load
UNAVAILABLE_COOLDOWN_SECONDS = 2 * 60  # upstream errors / network problems

# ----------------------------------------------------------------- the calendar head
# `next_fixtures` below answers "when is the next fixture, and which" for the covered competitions
# as a whole. It costs ONE provider request per covered competition and nothing else, because
# `get_calendar_head` is contractually a single request; with the six competitions covered here
# that is six requests per refresh. The TTL, the per-competition cap and the refresh lock below
# are what keep that from being six requests per page load; the shape name among them is about
# reading a stored answer correctly rather than about cost.

#: How long an answer is served before another sweep is paid for.
#:
#: A season calendar is not live data. A fixture moves when a broadcaster or a cup draw moves it,
#: which is days of notice, not minutes, so refreshing four times a day notices a change on the
#: day it is announced. Four sweeps x six competitions is 24 requests a day against a 1200/day
#: allowance, and only when every one of those four windows has a reader of an empty day in it.
#:
#: That figure is what SUCCESSFUL sweeps cost, and only a success is written here: a sweep that
#: fails leaves this TTL nothing to hold, so what bounds a FAILING calendar is the backoff and
#: the daily ceiling below, not this.
CALENDAR_HEAD_TTL_SECONDS = 6 * 3600

#: Fixtures kept per competition. Enough to name a round; deliberately not a calendar page.
CALENDAR_HEAD_PER_COMPETITION = 5

#: Names the shape of a stored calendar answer inside its cache key: an object holding both the
#: fixtures that were read and the competitions nobody could be asked about. A copy written under
#: another shape name is simply not found, so nothing here can unpack a stored answer the wrong
#: way.
CALENDAR_HEAD_SHAPE = "fixtures+unanswered"

#: One sweep at a time, process- and worker-wide.
#:
#: The TTL above stops a reader who refreshes; it does nothing about readers who arrive together.
#: Ten of them meeting a cold cache in the same second would each start their own sweep and spend
#: sixty requests on one answer. Whoever takes this key pays; everyone else is served the stale
#: copy, or told we do not know yet.
#:
#: It is deliberately NOT released when the sweep finishes. After a success the fresh copy makes
#: it irrelevant, and after a failure holding it is the point: a provider that just failed six
#: times should not be asked again by the next page load, only after this has expired.
CALENDAR_HEAD_LOCK_KEY = "matchdata:calendar-head:refreshing"
CALENDAR_HEAD_LOCK_SECONDS = 120

#: How long a failed sweep waits before another is paid for, and how that wait grows.
#:
#: Only a success is cached, so the TTL above holds nothing after a failure and every reader of
#: an empty day meets a cold cache again. Without this the floor is the lock, 120 seconds, which
#: a stream of readers turns into six requests every two minutes.
#:
#: The FIRST retry is still that 120 seconds, so a single bad minute costs the reader nothing
#: extra; it is a failure that REPEATS which is expensive, and each repeat doubles the wait.
#: The ceiling is 40 minutes because the answer this feature gives changes on the timescale of a
#: cup draw or a broadcaster's reschedule - a week, not a minute - so a reader waiting up to 40
#: minutes for a retry loses nothing real, while the provider is asked 9 times in the span one
#: successful answer would have covered rather than 180 times.
#:
#: The record outlives its own wait by a further ceiling, so a failure that keeps being met by
#: readers keeps escalating, while a streak nobody has retried for a whole ceiling window is
#: forgotten and starts again at 120 seconds.
#:
#: Deliberately separate from `COOLDOWN_KEY`, which `_call_chain` sets for the provider as a
#: whole: the live and results paths run through that cool-down and need it to stay short. This
#: key suppresses the calendar sweep alone.
CALENDAR_HEAD_BACKOFF_KEY = "matchdata:calendar-head:backoff"
CALENDAR_HEAD_BACKOFF_BASE_SECONDS = 120
CALENDAR_HEAD_BACKOFF_CEILING_SECONDS = 40 * 60

#: The most this feature may spend at one provider in a UTC day, counted from the budget's own
#: `calendar` reason rather than a counter of our own.
#:
#: PER PROVIDER, because a budget is. A chain of three providers therefore carries three of these
#: ceilings, one guarding each plan, and not one share of three plans put together: the provider
#: whose share is spent is passed over for the rest of the day and the sweep moves down the chain
#: to one that still has room, at that provider's own expense and under its own ceiling. That is
#: the deliberate answer to "may an empty-state notice spend a fallback's allowance": yes, because
#: the fallback's allowance is protected by the fallback's own copy of this number, and because
#: the scheduled tasks fall down the same chain when the primary is out - so the share that
#: protects them travels with the work. What no provider does is serve this feature after its own
#: share is gone.
#:
#: Sits BESIDE `SYNC_SCHEDULER_BUDGET_RESERVE`, not inside it. That reserve holds allowance back
#: from the scheduler so interactive page loads always have some; this holds allowance back from
#: one interactive page load so the scheduler always has some. They protect opposite sides of the
#: same plan and neither substitutes for the other.
#:
#: 120 is a tenth of the Live Score plan (1,200/day) and five times what four successful sweeps
#: cost, so a healthy day never comes near it. What it has to leave room for is the scheduler:
#: fixtures at 6 competitions x 3 days every 6 hours is 72 requests a day, results and live add
#: what a matchday actually needs, and the heaviest day this installation has recorded came to
#: 683. 1200 - 120 - 50 held back leaves 1,030 for those, which clears that heaviest day by more
#: than 300.
#:
#: Scaled down for a small plan the same way the scheduler scales its reserve, so this can never
#: be most of a tiny allowance: on a 10/day plan the share is 1, which is less than one sweep
#: costs, and the calendar simply never runs - which is the right answer for a 6-request sweep on
#: a 10-request plan.
CALENDAR_HEAD_DAILY_REQUEST_CEILING = 120

#: What a GRANTED calendar request is attributed to in the budget's `by_reason` hash. The provider
#: records its spending under this name; the ceiling above reads the same name back.
#:
#: A provider may charge itself more than the caller asked for, and what it adds does not land
#: here: `livescore_api._get` retries once after a burst 401 and attributes that second outbound
#: request to `retry`, so it counts against the day's total and not against this share. What the
#: ceiling bounds exactly is therefore GRANTED calendar requests; what those cost the plan is the
#: same number, doubled in the worst case where every one of them meets a burst 401, since one
#: retry is the most `_get` will make.
CALENDAR_BUDGET_REASON = "calendar"

# --------------------------------------------------- which competitions are worth asking about
# Coverage is 6 club competitions plus 29 national-team ones, and the two behave nothing alike.
# The club six play every week, so asking for all six on every pass is right. The 29 do not: AFCON
# is played in one window, the Gold Cup in another, World Cup qualifiers in international breaks,
# and outside its window a competition answers every request with an empty list. Asking all 35 on
# every pass is what makes coverage unaffordable - 35 x 3 days x 4 fixture passes is 420 requests a
# day before a single result is read, against a 1,200/day plan.
#
# So a national-team competition earns its place in a pass from a CALENDAR it has already been
# given, and the calendar is bought once and read for weeks. `get_calendar_head` is contractually
# ONE request and answers with the competition's next fixtures in kickoff order, whatever the date;
# the days in that answer are what say whether this competition plays inside the window a task
# covers. A competition with none costs nothing at all until its calendar is next refreshed.
#
# Refreshing is itself a cost, so it is spread two ways. It is adaptive: the wait before the next
# refresh is set from the competition's OWN next kickoff, so one that plays next week is re-read in
# days and one with nothing listed is left for a fortnight. And it ROTATES: a pass refreshes at
# most `SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS` of them, stalest first, so the 29 are never all
# paid for at once and none of them can be passed over twice while another is refreshed twice.
#
# It costs nothing to be wrong in the safe direction here: a competition whose calendar we have
# not read yet simply is not asked for, and it joins the pass on the rotation's next turn. That is
# what makes an international break work with nobody touching a setting - the break begins,
# fixtures appear in a competition that was dormant, the rotation reads its calendar within a day,
# and every task that covers those days starts asking for it.

#: One stored answer per competition: when it was read, which days it plays, when to read it again.
COVERAGE_CALENDAR_KEY = "matchdata:coverage:calendar:{key}"
#: The cached provider answer behind that record, so two passes close together cost one request.
COVERAGE_HEAD_CACHE_KEY = "matchdata:coverage:head:{key}"

#: Fixtures asked for per refresh. More than `CALENDAR_HEAD_PER_COMPETITION` because this answer is
#: read for its DAYS rather than for display: a matchday with eight fixtures on it would otherwise
#: fill the whole answer and hide the next matchday behind it. Still one request either way.
COVERAGE_CALENDAR_HEAD_LIMIT = 20

#: How far ahead a refreshed calendar is believed. Beyond this the answer is not kept, because a
#: fixture five months out will be re-read many times before its day arrives and storing it only
#: makes the record bigger.
COVERAGE_CALENDAR_HORIZON_DAYS = 60

#: The shortest and longest a calendar answer is held before another is paid for, and how far
#: ahead of a known kickoff the refresh is brought forward.
#:
#: The minimum bounds what a competition can cost: 12 hours means at most 2 refreshes a day for
#: one competition, however often the fixtures task runs. The maximum bounds how long a dormant
#: competition can stay unnoticed once it schedules something: 14 days, which is shorter than the
#: gap between international breaks, so a break is never missed by a competition that had nothing
#: listed when it was last read. The lead is why a competition is re-read BEFORE it plays rather
#: than on the day: 36 hours covers the fixtures task's 3-day window with a pass to spare.
COVERAGE_CALENDAR_MIN_SECONDS = 12 * 3600
COVERAGE_CALENDAR_MAX_SECONDS = 14 * 24 * 3600
COVERAGE_CALENDAR_LEAD_SECONDS = 36 * 3600

#: Fixtures kept in the record for display. The empty-state calendar reads these for the national
#: competitions instead of sweeping them, which is what keeps an ordinary page visit costing the
#: same six requests it costs today whatever the coverage setting says.
COVERAGE_CALENDAR_FIXTURES_KEPT = CALENDAR_HEAD_PER_COMPETITION

#: Keep a stored record small: it is read once per competition on every pass of several tasks.
MAX_COVERAGE_ERROR_CHARS = 200

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def is_national_team_competition(key: str) -> bool:
    """Whether `key` is played by national teams. An unknown key is treated as a club competition.

    Unknown is the safe answer here because every rule built on this protects the club set: a key
    the registry does not carry is asked for on every pass like a club competition rather than
    being made to wait for a calendar it will never be given.
    """
    comp = comps.COMPETITIONS.get(key)
    return bool(comp is not None and comp.is_national_team)


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)


@dataclass
class SyncMeta:
    provider: Optional[str] = None
    source: str = "database"          # provider | cache | stale-cache | database
    stale: bool = False
    fetched_at: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    live_polled: bool = False
    results_polled: bool = False
    #: Fixtures the registry refused to store because they could not be told apart from an existing
    #: match. Counted and reported rather than guessed into a duplicate row.
    ambiguous: int = 0
    #: How many fixtures were handed over and how many of those reached the database, summed over
    #: every ingest this meta covers. One `sync_day` makes three: the forward fixtures list, then
    #: results, then live scores. Without these a pass answered with an empty list is written down
    #: exactly like one handed a full matchday - `source="provider"`, `errors: []` - which is how
    #: the fixtures task reported success for three days while storing nothing at all.
    fixtures_seen: int = 0
    fixtures_stored: int = 0
    #: The same two counts for the FORWARD fixtures list alone. Kept apart because the three
    #: ingests answer different questions, and only this one answers "did the forward list hand
    #: back a fixture for a day we asked about". One unsettled match dated today that has already
    #: kicked off - or kicks off within the next quarter of an hour - is enough to make
    #: `_sync_results` (at least 150 minutes after kickoff) or `_sync_live` (from 15 minutes before
    #: kickoff to 150 after) hand back a day of fixtures on a pass whose forward list was empty, so
    #: the combined counts above cannot tell a dead forward path from a matchday.
    #:
    #: `..._stored` counts the fixtures the registry accepted, which includes one it merely updated
    #: on a row already held: `upsert_fixture` returns the existing match for those. So a forward
    #: list that re-offers matches already stored counts as seen and stored alike, and neither
    #: number says anything was new.
    forward_fixtures_seen: int = 0
    forward_fixtures_stored: int = 0
    #: Where the FORWARD list came from - "provider", "cache", "stale-cache" - or None when that
    #: question was never answered. `source` above cannot be read for this: the results and live
    #: calls that follow inside the same `sync_day` overwrite it.
    forward_source: Optional[str] = None
    #: When that forward answer was fetched from the provider. For a cache hit that is minutes
    #: before this pass rather than during it, so a sighting can be timed by when the fixture was
    #: really offered instead of by when it was read back out.
    forward_fetched_at: Optional[str] = None
    #: Outbound requests the calls this meta covers were CHARGED for, answered or not. Read off
    #: each provider's own budget (`RequestBudget.granted`) before and after the call, so a
    #: request that went out and then failed counts exactly like one that was answered, a burst
    #: retry or an extra page counts as the extra request it was, and a call the budget refused
    #: before sending counts nothing. A provider with no budget to read is charged `cost_hint`
    #: when the call reached it. See `MatchDataService._call_chain`.
    requests: int = 0
    #: At least one provider was actually ASKED and did not answer: a request went out and came
    #: back as a network failure, an HTTP error or a refusal from the provider itself. False when
    #: every provider was passed over without a request leaving - cooling down after an earlier
    #: failure, or refused by an allowance first - which is a skipped call, not an unreachable
    #: provider. Only meaningful for a call that failed; on a call that was answered it may still
    #: be True from a provider tried earlier in the chain.
    request_failed: bool = False
    #: Why each provider passed over WITHOUT a request was passed over, one entry per provider:
    #: "cooling_down" (an earlier failure put it in cool-down), "our_allowance" (a ceiling this
    #: installation configured, or a caller's `skip`), "provider_allowance" (the provider's own
    #: reported window said it was spent), "not_configured", or "not_served" (it holds no id for
    #: what was asked, so no request could name it). A deferral is recorded with these, so whoever
    #: words it for a reader can say whose limit it was, or that nobody's was.
    not_sent: List[str] = field(default_factory=list)
    #: The competitions a provider was NOT asked about because it holds no id for them, in its own
    #: words (`ProviderCannotServe`): one entry per provider passed over for that, and one per
    #: provider that answered for some competitions of a call and not for others.
    #:
    #: Kept apart from `errors` on purpose. A provider that cannot name a competition is not
    #: failing, the next one in the chain may answer in its place, and a gap in coverage that never
    #: changes must not read as a fault on every pass - `errors` is what a task's health is judged
    #: by. When nobody could be asked these are the reason why, and the fixture's record says so.
    declined: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "source": self.source, "stale": self.stale, "fetched_at": self.fetched_at,
                "errors": self.errors, "live_polled": self.live_polled, "results_polled": self.results_polled,
                "ambiguous": self.ambiguous, "fixtures_seen": self.fixtures_seen,
                "fixtures_stored": self.fixtures_stored,
                "forward_fixtures_seen": self.forward_fixtures_seen,
                "forward_fixtures_stored": self.forward_fixtures_stored,
                "forward_source": self.forward_source,
                "forward_fetched_at": self.forward_fetched_at,
                "requests": self.requests, "request_failed": self.request_failed,
                "not_sent": list(self.not_sent), "declined": list(self.declined)}


def not_served_reason(provider: str, keys: List[str]) -> str:
    """How a provider that was not asked about `keys`, for want of an id, is described everywhere."""
    them = "it" if len(keys) == 1 else "them"
    return (f"{provider}: not asked about {', '.join(keys)}: it holds no competition id for {them}, "
            f"so no request could name {them}")


#: Names the shape of a stored results answer inside its cache key: an object holding the fixtures
#: that came back AND the competitions the provider was asked about, because an answer speaks for
#: those and for no others. A copy stored in the older shape - a bare list, which cannot say that a
#: competition it was cached under was never asked about - is simply not found under this name,
#: so none of those can be read back as an answer.
RESULTS_SHAPE = "fixtures+asked"


#: The score periods a fixture carries besides the running score and half time. They travel
#: through the cache with everything else: every provider answer is stored by `_call_chain` as
#: these dicts and read back from them, so a field left out here never reaches the database at all.
#: Leaving these out once meant that a knockout tie ingested through the results or live path lost
#: its 90-minute score, and a shoot-out with an "AP" marker and no regulation score is one that
#: settlement must withhold.
_PERIOD_FIELDS = ("ft_home_score", "ft_away_score", "et_home_score", "et_away_score",
                  "ps_home_score", "ps_away_score")


def _fixture_to_dict(f: ProviderFixture) -> Dict[str, Any]:
    return {
        "provider": f.provider, "external_id": f.external_id,
        "competition": {"provider": f.competition.provider, "external_id": f.competition.external_id, "name": f.competition.name,
                        "key": f.competition.key, "country": f.competition.country, "country_code": f.competition.country_code,
                        "is_cup": f.competition.is_cup, "season_name": f.competition.season_name, "logo": f.competition.logo},
        "home": {"provider": f.home.provider, "external_id": f.home.external_id, "name": f.home.name, "logo": f.home.logo, "country": f.home.country},
        "away": {"provider": f.away.provider, "external_id": f.away.external_id, "name": f.away.name, "logo": f.away.logo, "country": f.away.country},
        "kickoff_utc": f.kickoff_utc.isoformat(), "status": f.status, "minute": f.minute,
        "home_score": f.home_score, "away_score": f.away_score, "ht_home_score": f.ht_home_score, "ht_away_score": f.ht_away_score,
        "venue": f.venue, "round": f.round,
        **{name: getattr(f, name) for name in _PERIOD_FIELDS},
        "periods_reported": bool(f.periods_reported),
        "kickoff_supplied": bool(f.kickoff_supplied),
    }


def _fixture_from_dict(d: Dict[str, Any]) -> ProviderFixture:
    from app.services.providers.base import ProviderCompetition, ProviderTeam, parse_utc
    c, h, a = d["competition"], d["home"], d["away"]
    return ProviderFixture(
        provider=d["provider"], external_id=d["external_id"],
        competition=ProviderCompetition(provider=c["provider"], external_id=c["external_id"], name=c["name"], key=c.get("key"),
                                        country=c.get("country"), country_code=c.get("country_code"), is_cup=bool(c.get("is_cup")),
                                        season_name=c.get("season_name"), logo=c.get("logo")),
        home=ProviderTeam(provider=h["provider"], external_id=h["external_id"], name=h["name"], logo=h.get("logo"), country=h.get("country")),
        away=ProviderTeam(provider=a["provider"], external_id=a["external_id"], name=a["name"], logo=a.get("logo"), country=a.get("country")),
        kickoff_utc=parse_utc(d["kickoff_utc"]), status=d["status"], minute=d.get("minute"),
        home_score=d.get("home_score"), away_score=d.get("away_score"), ht_home_score=d.get("ht_home_score"), ht_away_score=d.get("ht_away_score"),
        venue=d.get("venue"), round=d.get("round"),
        # A copy cached before these were carried simply has none, which reads as "not supplied".
        periods_reported=bool(d.get("periods_reported")),
        **{name: d.get(name) for name in _PERIOD_FIELDS},
        # A copy cached before this was carried was written by code that trusted every kickoff.
        kickoff_supplied=bool(d.get("kickoff_supplied", True)),
    )


#: One UTC day's live-poll count, and the ceiling over it.
#:
#: It lives beside the code that MAKES the requests rather than beside one of the tasks that asks
#: for them, because TWO tasks poll: the live task on its own interval, and the fixtures task on
#: its way out of `sync_day`. A ceiling only one of them consults is not a ceiling - an operator
#: who lowers it would watch the other task sail straight past.
LIVE_POLL_COUNT_KEY = "matchdata:live-polls:{day}"


def live_polls_today(cache, now: datetime) -> int:
    record = cache.get(LIVE_POLL_COUNT_KEY.format(day=now.strftime("%Y%m%d")))
    return int(record.get("count") or 0) if isinstance(record, dict) else 0


def note_live_poll(cache, now: datetime) -> None:
    key = LIVE_POLL_COUNT_KEY.format(day=now.strftime("%Y%m%d"))
    # An hour past midnight: still readable while a pass that began before the reset finishes, and
    # long gone before the same key comes round again.
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = int((midnight - now).total_seconds()) + 3600
    cache.set(key, {"count": live_polls_today(cache, now) + 1}, ttl=ttl, stale_ttl=ttl)


def live_poll_within_daily_ceiling(cache, now: datetime) -> bool:
    """Whether another live poll may be made today.

    Zero means NO CEILING, which is what zero means for every other request cap in this
    application. A setting left at nothing is not an instruction to stop working, and the one
    reading that would make it so is the reading an operator never intends.
    """
    cap = max(int(settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY), 0)
    return not cap or live_polls_today(cache, now) < cap


#: One UTC day's count of RESULTS requests made by the recovery pass, and the ceiling over it.
#:
#: The recovery pass is the only thing that spends out of this, and it is counted separately from
#: the results task for one reason: the results task's cost is bounded per PASS, which is a bound
#: on the day only because its interval is fixed. The recovery pass reopens days behind that task's
#: lookback, and how many of those exist depends on how long an outage lasted rather than on any
#: interval, so the honest bound on it is a bound on the day. `SYNC_RECOVERY_MAX_REQUESTS_PER_DAY`
#: is the figure the plan in config.py adds up.
#:
#: The pass's LIVE poll is deliberately not counted here. It is charged to `LIVE_POLL_COUNT_KEY`
#: and refused by `SYNC_LIVE_MAX_REQUESTS_PER_DAY` exactly like the live task's own polls, so the
#: day's worst case for live requests is the one ceiling it always was rather than two added
#: together.
RECOVERY_REQUEST_COUNT_KEY = "matchdata:recovery-requests:{day}"


def recovery_requests_today(cache, now: datetime) -> int:
    record = cache.get(RECOVERY_REQUEST_COUNT_KEY.format(day=now.strftime("%Y%m%d")))
    return int(record.get("count") or 0) if isinstance(record, dict) else 0


def note_recovery_requests(cache, now: datetime, count: int) -> None:
    if count <= 0:
        return
    key = RECOVERY_REQUEST_COUNT_KEY.format(day=now.strftime("%Y%m%d"))
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = int((midnight - now).total_seconds()) + 3600
    cache.set(key, {"count": recovery_requests_today(cache, now) + int(count)}, ttl=ttl, stale_ttl=ttl)


def recovery_requests_left_today(cache, now: datetime) -> Optional[int]:
    """How many more results requests the recovery pass may spend today; None means no ceiling.

    Zero as a SETTING means no ceiling, the way it does for every other request cap here. Zero as
    a RETURN VALUE means the ceiling is reached, which is why the two are different types: a
    caller that read them as one number would treat a disabled ceiling as a spent one and stop
    recovering anything at all.
    """
    cap = max(int(settings.SYNC_RECOVERY_MAX_REQUESTS_PER_DAY), 0)
    if not cap:
        return None
    return max(cap - recovery_requests_today(cache, now), 0)


#: The shape `MatchRegistry` writes `last_synced_at` in (`datetime.isoformat()`). A value of any
#: other shape is left out of the aggregate rather than cast: one malformed stamp would otherwise
#: fail the whole query, and with it the transaction of the request that asked.
_LAST_SYNCED_SHAPE = r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"


def last_provider_writes(db: Session) -> Dict[Optional[str], datetime]:
    """The newest `match_metadata.last_synced_at` per provider named on the row.

    WHAT THE STAMP IS. `MatchRegistry._apply_fixture` sets it to the wall-clock time of the STORE,
    on every upsert - including the upsert of a copy `_call_chain` served from the match cache: the
    30-minute fresh copy, and the 24-hour stale copy it falls back to once every provider has
    failed, which `sync_day`, the results pass and the recovery pass all store again. So a stamp is
    an upper bound on when its provider's data arrived, not that time. On the first day of an
    outage it reads "minutes ago" while nothing has answered for hours.

    That is why the stamps are returned per provider and not as one maximum: a stamp is only taken
    as a write once it has been checked against its own provider's status record, which says when
    that provider last answered and last failed (`match_data_health.newest_provider_write`). Whose
    data a row holds is the `provider` the registry writes beside the stamp; a cached copy keeps the
    name of the provider that produced it.

    `matches.updated_at` is not consulted, and must not be: the recovery pass rewrites its
    bookkeeping on every row it considers, so on 2026-10-07 that column read "4 minutes ago" over a
    table no provider had written to since 2 October.

    One grouped aggregate over the table, no provider request. Rows without a stamp of the expected
    shape are left out; a provider with none is absent from the result.
    """
    provider = Match.match_metadata["provider"].astext
    stamp = Match.match_metadata["last_synced_at"].astext
    newest = func.max(case((stamp.op("~")(_LAST_SYNCED_SHAPE), cast(stamp, DateTime(timezone=True))), else_=None))
    writes: Dict[Optional[str], datetime] = {}
    for name, value in db.query(provider, newest).group_by(provider).all():
        if value is not None:
            writes[name] = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return writes


class MatchDataService:
    def __init__(self, db: Session, providers: Optional[List[MatchDataProvider]] = None, cache: Optional[MatchCache] = None,
                 now: Optional[datetime] = None, keys: Optional[List[str]] = None):
        self.db = db
        self.registry = MatchRegistry(db, now=now)
        self.cache = cache or MatchCache()
        self._providers = providers
        self._now = now
        self.keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)
        #: The covered set split by who plays it. The club competitions are asked for on every
        #: pass exactly as they always have been; the national-team ones are asked for only when
        #: something says they play, which is the whole of what makes covering 35 affordable.
        self.club_keys = [k for k in self.keys if not is_national_team_competition(k)]
        self.national_keys = [k for k in self.keys if is_national_team_competition(k)]
        self._league_keys: Optional[Dict[Any, str]] = None
        #: What the results calls made through this instance recorded, per fixture and per
        #: competition-day. The recovery pass reads them back to report one outcome per fixture.
        self._outcomes: Dict[Any, Tuple[RecoveryOutcome, str]] = {}
        self._written: set = set()
        self._archive_seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
        #: What each competition-day's results call amounted to - "answered", "cached", "failed" or
        #: "deferred" - keyed (competition, ISO date). One call can end differently for different
        #: competitions, and the recovery pass reports them apart.
        self._competition_calls: Dict[Tuple[str, str], str] = {}

    # ------------------------------------------------------------------ helpers
    @property
    def now(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    @property
    def providers(self) -> List[MatchDataProvider]:
        if self._providers is None:
            self._providers = data_provider_chain()
        return self._providers

    @property
    def primary_name(self) -> Optional[str]:
        return self.providers[0].name if self.providers else None

    def _record_status(self, name: str, ok: bool, error: Optional[str] = None,
                       exc: Optional[BaseException] = None) -> None:
        """Note what a provider last did: when it last answered, and when and how it last failed.

        A failure also records `last_error_kind` - plan, access, quota or unavailable - because the
        kind is what says whether data can still arrive (`match_data_health`), and the cool-down
        cannot: API-Football's plan refusal and TheSportsDB's invalid-key refusal both cool down for
        two minutes, exactly like a network blip. The kind is classified from the exception's CLASS
        first and its message second. Every failure call site sits inside the `except` clause that
        caught the error, so when `exc` is not passed the exception being handled is that error.

        A later success clears the message, as it always has, but keeps the kind beside
        `last_error_at`, which it also keeps: both describe the last failure. A fallback that refuses
        every fixtures call on its plan and then answers a live poll with nothing has not started
        delivering fixtures, and the kind is what still says why.
        """
        payload = self.cache.get(STATUS_KEY.format(name=name)) or {}
        stamp = self.now.isoformat()
        if ok:
            payload.update({"last_success_at": stamp, "last_error": None})
        else:
            if exc is None:
                exc = sys.exc_info()[1]
            payload.update({"last_error_at": stamp, "last_error": error,
                            "last_error_kind": classify_provider_error(error, exc)})
        self.cache.set(STATUS_KEY.format(name=name), payload, ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def _cooldown(self, name: str) -> Optional[str]:
        payload = self.cache.get(COOLDOWN_KEY.format(name=name))
        return payload.get("reason") if isinstance(payload, dict) else None

    def _cooldown_cause(self, name: str) -> str:
        """Why a provider is cooling down, as a `SyncMeta.not_sent` kind.

        A cool-down set because an allowance refused a request before it left is that allowance
        still being spent, and a call skipped under it is skipped for the same reason. Only a
        cool-down set after a request went out and failed is "cooling_down". A record written
        before the cause was kept reads as the latter, which is what every such record was.
        """
        payload = self.cache.get(COOLDOWN_KEY.format(name=name))
        cause = payload.get("cause") if isinstance(payload, dict) else None
        return cause if cause in ("our_allowance", "provider_allowance") else "cooling_down"

    def clear_cooldowns(self) -> None:
        """Forget recent failures (used by the admin sync after credentials were fixed).

        The calendar's own backoff goes with them. It is keyed separately from the per-provider
        cool-downs on purpose, so nothing that deletes those touches it, and it can hold the sweep
        off for up to `CALENDAR_HEAD_BACKOFF_CEILING_SECONDS`: an operator who has just fixed
        credentials would get the fixtures, live and results paths back immediately and the
        empty-state calendar only after a wait of up to forty minutes they have no way to end.

        `CALENDAR_HEAD_LOCK_KEY` is deliberately left in place. It expires in two minutes by
        itself, so it costs the operator a short wait rather than a long one, and dropping it
        while a sweep is genuinely in flight would let a second one start and pay the whole
        per-competition cost over again.

        The daily ceiling is not cleared and cannot be: it is read from the provider's own
        spending, and an operator who has fixed credentials has not given the plan its requests
        back.
        """
        for p in self.providers:
            self.cache.delete(COOLDOWN_KEY.format(name=p.name))
        self.cache.delete(CALENDAR_HEAD_BACKOFF_KEY)

    def _set_cooldown(self, name: str, reason: str, seconds: int, cause: str = "failure") -> None:
        self.cache.set(COOLDOWN_KEY.format(name=name),
                       {"reason": reason, "until_seconds": seconds, "cause": cause},
                       ttl=seconds, stale_ttl=seconds)

    @staticmethod
    def _granted(provider) -> Optional[int]:
        """Requests this provider's budget has let out so far, or None when it keeps no count."""
        granted = getattr(getattr(provider, "budget", None), "granted", None)
        return granted if isinstance(granted, int) and not isinstance(granted, bool) else None

    def _call_chain(self, cache_key: str, ttl: int, meta: SyncMeta, fn, skip=None,
                    cost_hint: Union[int, Callable[[MatchDataProvider], int]] = 1,
                    providers: Optional[List[MatchDataProvider]] = None):
        """Run `fn(provider)` on the first working provider, with fresh/stale cache around it.

        `skip(provider)` lets a caller refuse to spend at one provider without refusing the whole
        chain: it returns the reason that provider is unaffordable FOR THIS CALLER, or None. A
        named provider is passed over exactly like one in cool-down - recorded, not called, not
        put in cool-down, and carried as the error to report only if nobody further down answers
        either. It is consulted per provider rather than once for the chain because the thing it
        usually guards, a request budget, is per provider too; asking it once and then calling
        whoever happens to be first is how a per-provider limit stops binding on anybody.

        It is not consulted at all when the cache answers, because then nothing is spent.

        WHAT WAS SPENT, AND WHETHER ANYONE WAS ASKED, are written on `meta` for every provider
        tried, answered or not (`SyncMeta.requests`, `SyncMeta.request_failed`). Five ways past a
        provider send nothing: its cool-down, the caller's `skip`, an allowance that refuses the
        request before it leaves (`ProviderRequestNotSent`, raised by `RequestBudget`), a provider
        that is not configured, and one that holds no id for what was asked
        (`ProviderCannotServe`). None of those is a provider that did not answer. Every other
        `ProviderError` from `fn` is a request that went out and got no usable answer.
        `cost_hint` is what one call costs at a provider that keeps no budget to read - one per
        competition for a results call - and is charged only when the call reached it. It may be
        a function of the provider, for a call whose cost depends on what that provider could be
        asked about.

        A provider that cannot name what was asked is passed over on the way to the next, and its
        reason goes to `meta.declined` rather than to `meta.errors`: it is not failing, and the
        next provider may answer in its place. When nobody answers and that was the last reason,
        what is raised names every provider that declined.

        `providers` limits the call to part of the chain - a caller that has already had an answer
        from some of it for some of its question, and is asking the rest about the rest. A stale
        copy is still served only from a provider in the whole chain.
        """
        cached = self.cache.get(cache_key)
        if cached is not None:
            meta.source, meta.provider, meta.fetched_at = "cache", cached.get("provider"), cached.get("fetched_at")
            return cached["data"]
        last_error: Optional[ProviderError] = None
        declined_from = len(meta.declined)
        for provider in (self.providers if providers is None else providers):
            cooling = self._cooldown(provider.name)
            if cooling:
                cause = self._cooldown_cause(provider.name)
                why = "recent failure" if cause == "cooling_down" else "allowance spent"
                meta.errors.append(f"{provider.name}: skipped ({why}: {cooling})")
                meta.not_sent.append(cause)
                last_error = last_error or ProviderUnavailableError(cooling, provider=provider.name)
                continue
            unaffordable = skip(provider) if skip is not None else None
            if unaffordable:
                meta.errors.append(unaffordable)
                meta.not_sent.append("our_allowance")
                last_error = last_error or ProviderRequestNotSent(unaffordable, provider=provider.name)
                continue
            before = self._granted(provider)
            reached = True
            try:
                data = fn(provider)
            except ProviderCannotServe as exc:
                # Not this provider's question: it holds no id to put it with, so nothing left and
                # nothing is wrong with it. No cool-down - it still serves what it does hold - no
                # failure on its status, and no error: the next provider may answer in its place.
                reached = False
                meta.not_sent.append("not_served")
                meta.declined.append(str(exc)); last_error = exc; continue
            except ProviderNotConfiguredError as exc:
                reached = False
                meta.not_sent.append("not_configured")
                meta.errors.append(str(exc)); last_error = exc; continue
            except ProviderRequestNotSent as exc:
                # Refused before it left: our own ceiling, the provider's reported window, or no
                # store to meter against. Nothing was asked, so nothing was unreachable. The
                # cool-down until midnight is kept: that is when the day's allowance comes back.
                reached = False
                cause = ("provider_allowance" if getattr(exc, "refused_by", "ours") == "provider"
                         else "our_allowance")
                meta.not_sent.append(cause)
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), _seconds_until_utc_midnight(self.now),
                                   cause=cause); continue
            except ProviderQuotaError as exc:
                meta.request_failed = True
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), _seconds_until_utc_midnight(self.now)); continue
            except ProviderAuthError as exc:
                meta.request_failed = True
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), AUTH_COOLDOWN_SECONDS); continue
            except ProviderError as exc:
                meta.request_failed = True
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), UNAVAILABLE_COOLDOWN_SECONDS); continue
            finally:
                after = self._granted(provider)
                if before is not None and after is not None:
                    meta.requests += max(after - before, 0)
                elif reached:
                    hint = cost_hint(provider) if callable(cost_hint) else cost_hint
                    meta.requests += max(int(hint), 0)
            self._record_status(provider.name, True)
            meta.source, meta.provider, meta.fetched_at = "provider", provider.name, self.now.isoformat()
            self.cache.set(cache_key, {"provider": provider.name, "fetched_at": meta.fetched_at, "data": data}, ttl=ttl)
            return data
        stale = self.cache.get_stale(cache_key)
        # Only a copy produced by a provider that is still in the chain may be served: switching
        # DATA_PROVIDER must never resurrect data from a provider that is no longer configured.
        if stale is not None and stale.get("provider") in {p.name for p in self.providers}:
            meta.source, meta.provider, meta.fetched_at, meta.stale = "stale-cache", stale.get("provider"), stale.get("fetched_at"), True
            return stale["data"]
        if last_error is not None:
            declined = meta.declined[declined_from:]
            if isinstance(last_error, ProviderCannotServe) and len(declined) > 1:
                # Nobody further down the chain could be asked either: one error naming them all.
                raise ProviderCannotServe("; ".join(declined), provider=last_error.provider)
            raise last_error
        raise ProviderNotConfiguredError("No match-data provider is configured", provider="none")

    @staticmethod
    def _askable(provider: MatchDataProvider, keys: List[str]) -> List[str]:
        """The competitions in `keys` that `provider` can be asked about, in order.

        Raises `ProviderCannotServe` when there are none, so the chain passes the provider over
        and asks the next one instead of taking an empty list nobody asked for as its answer.
        """
        can = set(provider.askable(keys))
        askable = [key for key in keys if key in can]
        if not askable:
            raise ProviderCannotServe(not_served_reason(provider.name, keys), provider=provider.name)
        return askable

    def _ask_only_what_it_names(self, provider: MatchDataProvider, keys: List[str],
                                meta: SyncMeta) -> List[str]:
        """`_askable`, noting on `meta` the competitions left out of a call that goes ahead."""
        askable = self._askable(provider, keys)
        if len(askable) < len(keys):
            note = not_served_reason(provider.name, [key for key in keys if key not in askable])
            if note not in meta.declined:
                meta.declined.append(note)
        return askable

    # ------------------------------------------------------------------ competitions
    def competitions(self) -> List[League]:
        """Internal league rows for the covered competitions (created on first use)."""
        leagues = [self.registry.ensure_canonical_league(k) for k in self.keys]
        self.db.commit()
        return leagues

    def league_ids(self) -> List:
        return [l.id for l in self.competitions()]

    # ------------------------------------------------------------------ fixtures
    def _store_fixtures(self, fixtures, meta: SyncMeta, *, forward: bool = False) -> int:
        """Persist fixtures, counting the ones the registry refused as too ambiguous to identify.

        `upsert_fixture` returns None when a provider fixture cannot be told apart from an existing
        match. Storing it anyway would create a second card for the same game and split the expert
        predictions across the two rows, so the refusal is recorded instead.

        The counts accumulate rather than overwrite: one `sync_day` stores fixtures, then results,
        then live scores through this same method, and the day's total is the sum of the three.
        `forward=True` marks the callers that fetched a list of matches to come - the day's fixture
        list and the competition calendar - so those are also counted on their own. Every ingest
        arriving in one shared counter is what made an empty forward list invisible whenever any
        other ingest had something to hand over.
        """
        stored = seen = 0
        for fixture in fixtures:
            seen += 1
            if self.registry.upsert_fixture(fixture) is None:
                meta.ambiguous += 1
            else:
                stored += 1
        meta.fixtures_seen += seen
        meta.fixtures_stored += stored
        if forward:
            meta.forward_fixtures_seen += seen
            meta.forward_fixtures_stored += stored
        if meta.ambiguous:
            logger.warning("%d fixture(s) were not stored because they could not be identified unambiguously",
                           meta.ambiguous)
        return stored

    def _live_polls_today(self) -> int:
        return live_polls_today(self.cache, self.now)

    def _note_live_poll(self) -> None:
        note_live_poll(self.cache, self.now)

    def _live_poll_within_daily_ceiling(self) -> bool:
        return live_poll_within_daily_ceiling(self.cache, self.now)

    def sync_day(self, day: date, keys: Optional[List[str]] = None) -> SyncMeta:
        """Ingest one day's fixtures, then its results and live scores.

        `keys` narrows the competitions asked for. It costs one provider request per competition,
        so a caller that knows which of them can possibly have a fixture on `day` - the scheduler
        does, from the coverage calendar - passes that subset and pays for nothing else. Omitting
        it asks for every covered competition, which is what every caller outside the scheduler
        wants and what this method has always done.

        The subset is part of the cache key, so an answer fetched for three competitions is never
        served to a caller that asked about thirty.
        """
        meta = SyncMeta()
        keys = self.keys if keys is None else [k for k in self.keys if k in set(keys)]
        if not keys:
            # Nothing to ask about is a real answer and a free one: no provider request, and a
            # source of "database" so the caller does not read this as a provider that answered.
            return meta
        key = f"matchdata:fixtures:{day.isoformat()}:{','.join(keys)}"
        try:
            # Each provider is asked only about the competitions it can name. One that can name
            # none of them is passed over, so a day nobody could be asked about stays unanswered
            # instead of reading as a day with no fixtures.
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_FIXTURES, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_fixtures(
                                           day, self._ask_only_what_it_names(p, keys, meta))])
        except ProviderError as exc:
            meta.errors.append(str(exc))
            meta.source = "database"
            # `forward_source` stays None: the chain never answered, so this pass learned nothing
            # about the calendar. Leaving it None is what lets the caller tell an outage apart from
            # a week with no fixtures in it.
            return meta
        # Pin where the forward answer came from before anything else can overwrite `source`:
        # `_sync_results` and `_sync_live` below run through the same `_call_chain` and each
        # rewrites `meta.source`, `meta.provider` and `meta.fetched_at` with their own.
        meta.forward_source, meta.forward_fetched_at = meta.source, meta.fetched_at
        fixtures = [_fixture_from_dict(d) for d in payload]
        self._store_fixtures(fixtures, meta, forward=True)
        self.db.commit()
        if day <= self.now.date():
            # The same subset: a caller that paid for three competitions' fixtures must not be
            # billed for thirty competitions' results on the way out of the method.
            #
            # AND THE SAME CAP. `SyncScheduler._run_results` bounds its own pass, but this call is
            # made from the FIXTURES task and reaches the provider all the same, so a bound that
            # lives only in the other task is not a bound on the day - a fixtures pass over 35
            # competitions holding unsettled matches spends 35 results requests that no cap ever
            # sees. The limit is applied where the requests are made rather than where they were
            # asked for.
            cap = max(int(settings.SYNC_RESULTS_MAX_REQUESTS_PER_PASS), 0)
            self._sync_results(day, meta, keys=keys[:cap] if cap else keys)
        if day == self.now.date():
            # Same reasoning, and the live poll has a DAILY ceiling rather than a per-pass one, so
            # it is asked and recorded through the same counter the live task uses. Without this a
            # ceiling an operator lowers is simply bypassed by every fixtures pass.
            if self._live_poll_within_daily_ceiling():
                self._sync_live(meta)
                self._note_live_poll()
        return meta

    def _league_key_map(self) -> Dict[Any, str]:
        """Stored league row id -> canonical competition key, for the covered competitions.

        Built from `ensure_canonical_league`, which is the same row every ingest writes against,
        so a match's `league_id` can be turned back into the key that would be asked for to settle
        it. `setdefault` keeps the FIRST key that claims an id: nothing should map two keys onto
        one league row, and if something does, attributing it to the last one read would depend on
        dictionary order.
        """
        if self._league_keys is None:
            mapping: Dict[Any, str] = {}
            for key in self.keys:
                try:
                    league = self.registry.ensure_canonical_league(key)
                except Exception:  # pragma: no cover - a missing row must not fail a results pass
                    logger.debug("Could not resolve the league row for %s", key, exc_info=True)
                    continue
                league_id = getattr(league, "id", None)
                if league_id is not None:
                    mapping.setdefault(league_id, key)
            self._league_keys = mapping
        return self._league_keys

    def _pending_groups(self, day: date, skip: frozenset = frozenset()) -> Dict[str, List[Match]]:
        """Covered competition -> its matches on `day` that kicked off and are still unsettled.

        `skip` leaves out fixtures a recovery pass closes before asking anything; only the plan
        that prices such a pass without running it passes one (`recovery_plan`).

        A match whose league row carries no canonical key cannot name a competition. Those rows
        predate the canonical registry, and everything that predates it is one of the club six -
        national-team coverage is newer than the registry by construction - so an unattributable
        match is put into every CLUB competition's group rather than the whole covered set. That
        keeps such a match settling without letting one unidentifiable row re-expand a pass to all
        35 competitions.

        The cutoff is `UNSETTLED_GRACE`, the same 150 minutes the recovery pass calls a match
        overdue by, so the two cannot drift apart.
        """
        cutoff = (self.now - UNSETTLED_GRACE).replace(tzinfo=None)
        by_league = self._league_key_map()
        groups: Dict[str, List[Match]] = {}
        unattributed: List[Match] = []
        for m in self.registry.matches_for_day(day, self.league_ids()):
            if m.status not in (MatchStatus.SCHEDULED, MatchStatus.LIVE) or m.match_date > cutoff or m.id in skip:
                continue
            key = by_league.get(getattr(m, "league_id", None))
            if key is None:
                unattributed.append(m)
            else:
                groups.setdefault(key, []).append(m)
        if unattributed:
            for key in self.club_keys:
                groups.setdefault(key, []).extend(unattributed)
        return groups

    def pending_result_keys(self, day: date) -> List[str]:
        """Covered competitions holding a match on `day` that kicked off and is still unsettled.

        This is the whole of what makes the results task affordable at 35 competitions. The task
        runs every half hour, so asking for every covered competition on every day that holds ANY
        unsettled match costs 35 x 2 x 48 = 3,360 requests a day against a 1,200/day plan. What a
        day actually needs is the competitions the unsettled matches are IN, which the stored rows
        already say, and that costs nothing to work out. See `_pending_groups` for the rows.
        """
        groups = self._pending_groups(day)
        return [k for k in self.keys if k in groups]

    def due_result_keys(self, day: date,
                        groups: Optional[Dict[str, List[Match]]] = None) -> List[str]:
        """The pending competitions on `day` that the retry schedule says to ask about now.

        A competition-day is due when any of its unsettled matches is (`retry_due`): never asked,
        or asked long enough ago for its age. This is the ONE retry policy, applied wherever a
        results call is made - the results task, the fixtures task's call on its way out of
        `sync_day`, a reader's refresh and the recovery pass - so a missing result costs what the
        schedule says wherever the question comes from. A match given up on is never due, and a
        young one (under six hours) is due on every pass exactly as before.
        """
        groups = self._pending_groups(day) if groups is None else groups
        now = self.now
        return [k for k in self.keys if k in groups and any(retry_due(m, now) for m in groups[k])]

    def _pending_results_exist(self, day: date) -> bool:
        return bool(self.pending_result_keys(day))

    def _sync_results(self, day: date, meta: SyncMeta, keys: Optional[List[str]] = None) -> str:
        """Ask for `day`'s finished results for the competitions due an ask, and write down what came back.

        `keys` narrows the competitions - the scheduler caps how many one pass may ask about - and
        defaults to whatever `due_result_keys` names, so a caller that passes nothing gets the
        cheapest correct set.

        WHO IS ASKED ABOUT WHAT. A provider is asked only about the competitions it can name
        (`MatchDataProvider.askable`), and its answer speaks for those and for no others: a
        competition it holds no id for was not asked about, and the empty list it would have been
        handed for it is not an answer. Those competitions go on down the chain in a further round,
        offered only to providers this call has not reached yet - each one already reached
        answered without them, declined them or failed, and asking it again would cost a request
        or learn nothing. A competition that reaches the end of the chain unasked is recorded as
        exactly that. API-Football and TheSportsDB hold no id for any national-team competition,
        so whenever Live Score is out of the chain a national-team competition ends here.

        WHAT IS RECORDED, where the call already happens so knowing it costs nothing extra:

        * per COMPETITION and date, what the archive returned (`record_archive_observation`):
          ANSWERED with the row count, or EMPTY - only for a competition a provider was asked
          about and answered for. A request about it that went out and got no answer changes no
          state; it is noted beside it as a failure, because "we could not ask" is not "there is
          nothing". A competition no request was sent about is not noted there at all.
        * per unsettled FIXTURE the call covered, the outcome (`record_recovery_outcome`):
          RECOVERED, FRESH_UNANSWERED (the attempt), PROVIDER_ERROR when a request about its
          competition went out and nobody answered it, or DEFERRED when none did - our own
          allowance refused it, every provider that could name it was cooling down after a
          failure elsewhere, or no provider in the chain can name it at all. A fresh cache hit is
          not written, because it teaches nothing and would put a write on every page load; the
          recovery pass reports it for its own calls.

        What the call was charged goes on `meta.requests`, answered or not (see `_call_chain`).
        Providers passed over for want of an id go on `meta.declined`, never on `meta.errors`: a
        gap in coverage is not a fault, and must not make a pass read as failed on every run.

        Returns what the call amounted to: "answered", "cached", "failed" (a request went out and
        no provider answered it, including a stale copy served in its place), "deferred" (no
        request went out), "skipped" (nothing was due, no call attempted), or "mixed" when its
        competitions ended differently. Per competition it is kept in `self._competition_calls`.

        A second listing of a played match on `day` is closed first (`retire_relisted`). It is not
        a pending result, and a call made on its behalf would be paid for and learn nothing.
        """
        if self.registry.retire_relisted(self.now, self.league_ids(), day=day):
            self.db.commit()
        groups = self._pending_groups(day)
        due = self.due_result_keys(day, groups)
        if keys is not None:
            due = [k for k in due if k in set(keys)]
        if not due:
            return "skipped"
        covered: Dict[Any, Tuple[Match, str]] = {}
        for key in due:
            for m in groups.get(key, []):
                covered.setdefault(m.id, (m, key))
        #: Fixtures the sweep has stopped asking about can still share a competition-day with one it
        #: has not. The answer is credited to them only if it settles them; otherwise their row is
        #: left exactly as it was when we stopped.
        stopped = {mid for mid, (m, _key) in covered.items() if recovery_state_of(m).get("gave_up_at")}
        #: Per competition: what its part of the call amounted to, and the error of a request about
        #: it that went out and got no answer.
        calls: Dict[str, str] = {}
        failed: Dict[str, str] = {}
        #: Why providers were passed over in this call, each reason once and in the order met, and
        #: the `SyncMeta.not_sent` kinds behind them. A competition nobody answered for is
        #: recorded with these.
        noted: List[str] = []
        declines: List[str] = []
        kinds: List[str] = []
        #: Providers this call has reached: asked, declined, failed, or refused before sending.
        reached: set = set()
        remaining = list(due)
        while remaining:
            asking = remaining
            chain = [p for p in self.providers if p.name not in reached]
            if not chain:
                # Every provider has had its turn in this call and none answered for these.
                self._note_results_failure(
                    day, asking, covered, failed,
                    noted + declines or ["no provider in the chain is left to ask about it"], kinds,
                    stopped, calls)
                break
            call = SyncMeta()
            asked_by: Dict[str, List[str]] = {}
            try:
                payload = self._call_chain(
                    f"matchdata:results:{RESULTS_SHAPE}:{day.isoformat()}:{','.join(asking)}",
                    settings.MATCH_CACHE_TTL_RESULTS, call,
                    self._results_fetch(day, asking, asked_by, reached, failed),
                    cost_hint=lambda p, asked_by=asked_by, asking=asking: len(asked_by.get(p.name, asking)),
                    providers=chain)
            except ProviderError as exc:
                self._absorb_results_round(meta, call, noted, declines, kinds)
                if not isinstance(exc, ProviderCannotServe):
                    meta.errors.append(f"results: {exc}")
                # A deferral is described by the chain's own record of why nothing left (a
                # cool-down, an allowance, no provider able to name the competition), which names
                # the reason; the last error alone would read like a failure of this call.
                self._note_results_failure(day, asking, covered, failed,
                                           noted + declines or [f"results: {exc}"], kinds, stopped, calls)
                break
            self._absorb_results_round(meta, call, noted, declines, kinds)
            meta.source, meta.provider, meta.fetched_at, meta.stale = (
                call.source, call.provider, call.fetched_at, call.stale)
            meta.results_polled = call.results_polled = True
            fixtures = [_fixture_from_dict(d) for d in payload.get("fixtures") or []]
            self._store_fixtures(fixtures, meta)
            spoke_for = set(payload.get("asked") or [])
            if call.source == "stale-cache" or not spoke_for & set(asking):
                # Every provider was passed over and an old copy was served instead. Whatever it
                # settles is settled; for everything else this is an outage when a request went out
                # and was not answered, and a deferral when none did.
                self._note_results_failure(
                    day, asking, covered, failed,
                    noted + declines or ["no provider answered; a stored copy was served"], kinds,
                    stopped, calls, settled_by="the stale-cache copy of the day settled it")
                break
            remaining = [key for key in asking if key not in spoke_for]
            if remaining:
                # Answered for some and not asked about the rest: those go on down the chain.
                note = not_served_reason(call.provider or "the provider", remaining)
                if note not in declines:
                    declines.append(note)
                kinds.append("not_served")
            self._credit_results_answer(day, call, [key for key in asking if key in spoke_for],
                                        fixtures, covered, stopped, calls)
        meta.declined.extend(d for d in declines if d not in meta.declined)
        for key, called in calls.items():
            self._competition_calls[(key, day.isoformat())] = called
        self.db.commit()
        outcomes = set(calls.values())
        return outcomes.pop() if len(outcomes) == 1 else "mixed"

    def _results_fetch(self, day: date, keys: List[str], asked_by: Dict[str, List[str]],
                       reached: set, failed: Dict[str, str]):
        """One round's `fn` for `_call_chain`: ask `provider` about the part of `keys` it can name.

        Notes, for the round's caller, which providers were reached and what each was asked, and
        which competitions a request that went out and got no answer was about: the ones that
        provider was asked about, or all of them when it failed before it could say which.
        """
        def fetch(provider: MatchDataProvider) -> Dict[str, Any]:
            reached.add(provider.name)
            try:
                asked = self._askable(provider, keys)
                asked_by[provider.name] = asked
                fixtures = provider.get_results(day, day, asked)
            except (ProviderNotConfiguredError, ProviderRequestNotSent):
                raise  # nothing was sent
            except ProviderError as exc:
                for key in asked_by.get(provider.name, keys):
                    failed[key] = str(exc)
                raise
            return {"fixtures": [_fixture_to_dict(f) for f in fixtures], "asked": asked}
        return fetch

    @staticmethod
    def _absorb_results_round(meta: SyncMeta, call: SyncMeta, noted: List[str], declines: List[str],
                              kinds: List[str]) -> None:
        """Add one round of a results call to the caller's meta: what it spent, whether a request
        failed, and why providers were passed over - each reason once, however many rounds met it."""
        meta.requests += call.requests
        meta.request_failed = meta.request_failed or call.request_failed
        meta.not_sent.extend(call.not_sent)
        kinds.extend(call.not_sent)
        for error in call.errors:
            if error not in noted:
                noted.append(error)
                meta.errors.append(error)
        for decline in call.declined:
            if decline not in declines:
                declines.append(decline)

    def _credit_results_answer(self, day: date, call: SyncMeta, keys: List[str],
                               fixtures: List[ProviderFixture], covered: Dict[Any, Tuple[Match, str]],
                               stopped: set, calls: Dict[str, str]) -> None:
        """Write down what an answer said about the competitions it was asked about, and only those."""
        observed: Dict[str, Dict[str, Any]] = {}
        if call.source == "provider":
            counts = {key: 0 for key in keys}
            for fixture in fixtures:
                comp_key = getattr(fixture.competition, "key", None)
                if comp_key in counts:
                    counts[comp_key] += 1
            for key in keys:
                entry = self.registry.record_archive_observation(
                    key, day, counts[key], provider=call.provider, asked_at=self.now)
                observed[key] = self._archive_summary(entry)
                self._archive_seen[(key, day.isoformat())] = observed[key]
        for key in keys:
            calls[key] = "answered" if call.source == "provider" else "cached"
        answered_for = set(keys)
        for match, key in covered.values():
            if key not in answered_for:
                continue
            settled_now = is_settled(match.status)
            if match.id in stopped and not settled_now:
                continue
            outcome, detail = classify_recovery_outcome(call, settled_before=False,
                                                        settled_now=settled_now)
            self._outcomes[match.id] = (outcome, detail)
            if outcome is RecoveryOutcome.CACHED:
                continue
            if outcome is RecoveryOutcome.RECOVERED and not recovery_state_of(match):
                # Settled at its first ask. Nothing was missing yet, so the row gets no bookkeeping
                # from here; the recovery pass still credits it if it was the one that asked.
                continue
            archive = observed.get(key)
            if outcome is RecoveryOutcome.FRESH_UNANSWERED and archive is not None:
                detail = (f"{call.provider} answered for this competition on {day.isoformat()} with "
                          f"{archive['rows']} row(s), none of them a result for this match")
            self.registry.record_recovery_outcome(match, outcome, detail, self.now, archive=archive)
            self._written.add(match.id)

    @staticmethod
    def _archive_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
        return {"state": entry.get("state"), "rows": entry.get("rows"), "asked_at": entry.get("asked_at")}

    @staticmethod
    def _not_sent_detail(reason: str) -> str:
        """What a fixture's row says when its due ask was never sent: why, in the chain's words."""
        return (f"due an ask, and no request was made for it: {reason}. Nothing was asked, so "
                f"nothing was learned; it stays due")

    def _note_results_failure(self, day: date, keys: List[str],
                              covered: Dict[Any, Tuple[Match, str]], failed: Dict[str, str],
                              reasons: List[str], kinds: List[str], stopped: set,
                              calls: Dict[str, str],
                              settled_by: str = "an answer this call received settled it") -> None:
        """Competitions of a results call nobody answered for: note each, and each fixture, as what it was.

        Two different things arrive here and they are written down differently, per competition:

        * PROVIDER_ERROR - a request about the competition went out and no provider answered it
          (`failed`). That is an outage. It is noted beside the archive's state for that
          competition and date, and counted on each of its fixtures as a provider error.
        * DEFERRED - no request about it went out at all: our own allowance refused it before it
          left, every provider that could name it was cooling down after a failure elsewhere, or
          none in the chain can name it. Nothing was unreachable, so nothing is noted about the
          archive, and each fixture's due ask is recorded as deferred, with `reasons` and the
          `kinds` behind them.

        `settled_by` is what a fixture this call settled anyway - from a stale copy, or from an
        answer for the rest of the call - is credited to.
        """
        detail = self._not_sent_detail("; ".join(reasons))
        because = sorted(set(kinds)) or None
        for key in keys:
            calls[key] = "failed" if key in failed else "deferred"
            if key in failed:
                self.registry.record_archive_failure(key, day, f"results: {failed[key]}", at=self.now)
        for match_id, (match, key) in covered.items():
            if key not in keys:
                continue
            if match_id in stopped and not is_settled(match.status):
                continue
            if is_settled(match.status):
                if recovery_state_of(match):
                    self.registry.record_recovery_outcome(match, RecoveryOutcome.RECOVERED, settled_by, self.now)
                    self._written.add(match.id)
                self._outcomes[match.id] = (RecoveryOutcome.RECOVERED, settled_by)
                continue
            if key in failed:
                outcome, said = RecoveryOutcome.PROVIDER_ERROR, f"results: {failed[key]}"
                self.registry.record_recovery_outcome(match, outcome, said, self.now)
            else:
                outcome, said = RecoveryOutcome.DEFERRED, detail
                self.registry.record_recovery_outcome(match, outcome, said, self.now,
                                                      deferred_because=because)
            self._outcomes[match.id] = (outcome, said)
            self._written.add(match.id)

    def _live_window_open(self) -> bool:
        """Whether any covered match is being played right now, give or take the window.

        THE WINDOW IS NOT A CALENDAR DAY, and asking about one made it shut on matches still being
        played. It runs from 15 minutes before a kickoff to 150 after, so it straddles midnight at
        both ends: a 23:50 kickoff is inside it at 00:05, and a 00:05 kickoff is inside it at
        23:50 the evening before. Reading only the matches dated TODAY lost both - not because
        anything about the match had changed, but because the match belongs to a day nothing looks
        at any more. That is the same rollover that strands a fixture for good, and around UTC
        midnight is exactly when a national-team fixture in the Americas is at half time.

        Three days is the whole of the fix and cannot need a fourth: no kickoff further from now
        than 150 minutes back or 15 minutes forward can open a window, and that span cannot reach
        past yesterday or into the day after tomorrow. The per-match test below is unchanged and
        still decides, so widening the days looked at admits no match the window does not cover.
        """
        now_naive = self.now.replace(tzinfo=None)
        today = self.now.date()
        league_ids = self.league_ids()
        for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
            for m in self.registry.matches_for_day(day, league_ids):
                if m.status == MatchStatus.FINISHED or m.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
                    continue
                if m.match_date - timedelta(minutes=15) <= now_naive <= m.match_date + timedelta(minutes=150):
                    return True
        return False

    def _sync_live(self, meta: SyncMeta, require_window: bool = True) -> None:
        """Poll `matches/live.json` and store whatever it holds.

        `require_window` is what keeps the ordinary live task from polling all night, and the
        recovery pass is the one caller that switches it off. The window is this application's own
        polling window; how long the feed itself keeps a finished match is not known. So the
        recovery pass polls on the retry schedule and credits whatever the poll settles, and a poll
        that does not mention a fixture is never read as an answer about it. It pays out of the
        same daily live ceiling as the live task, so turning the gate off buys no extra requests.
        """
        if require_window and not self._live_window_open():
            return
        key = f"matchdata:live:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_LIVE, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_live(self.keys)])
        except ProviderError as exc:
            meta.errors.append(f"live: {exc}")
            return
        meta.live_polled = True
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta)
        self.db.commit()

    # ------------------------------------------------- fixtures no ordinary refresh reaches
    def recovery_plan(self, max_days: int = STALE_SWEEP_MAX_DAYS) -> Dict[str, Any]:
        """What a recovery pass would work on and what it would cost. Makes no request and no write.

        STRANDED is every fixture still unsettled `UNSETTLED_GRACE` after kickoff and not given up
        on, plus any fixture the pass will put back: a stop made by a rule since removed
        (`superseded_stops`), which the pass undoes, and a given-up fixture the archive has since
        been seen to move past (`reopen_candidates`), which it reopens. DUE is the part of that the
        retry schedule says to ask about now. DAYS are the days behind the results lookback holding
        a due fixture, which is the only part that costs a results request here - a day the results
        task already walks is asked about there.

        `results_requests` is what those days WANT rather than what a pass may spend: the per-pass
        and per-day allowances are applied when the pass runs, and a plan that quietly pre-applied
        them would hide the work being deferred. It counts one request per competition-day, the
        first page; a day whose answer paginates costs more, and the pass charges what it actually
        spent. `live_requests` is the poll the pass would make: 0 when nothing is due or when the
        day's live ceiling would refuse it.

        RELISTED are the second listings of a played match (`MatchRegistry.relisting_of`). The pass
        closes them before anything else, for nothing, so here they are none of the above.
        """
        league_ids = self.league_ids()
        now = self.now
        relisted = [stale for stale, _played in self.registry.relisted_fixtures(now, league_ids)]
        closing = frozenset(m.id for m in relisted)
        superseded = [m for m in self.registry.superseded_stops(league_ids) if m.id not in closing]
        known_superseded = {m.id for m in superseded}
        reopenable = [m for m, _ in self.registry.reopen_candidates(league_ids)
                      if m.id not in known_superseded and m.id not in closing]
        stranded = [m for m in self.registry.recoverable_unsettled(now, league_ids) if m.id not in closing]
        known = {m.id for m in stranded}
        put_back = superseded + reopenable
        stranded = stranded + [m for m in put_back if m.id not in known]
        # A fixture the pass puts back is due as the schedule says once its stop is off the row -
        # a reopened one at once - and `retry_due` cannot say that while the row still carries the
        # stop, so it is asked without it.
        due = [m for m in stranded
               if (m.id in known_superseded and due_once_stop_is_undone(m, now))
               or (m.id not in known_superseded and (retry_due(m, now)
                                                     or m.id in {r.id for r in reopenable}))]
        days = self.registry.stale_unsettled_days(
            now, settings.SYNC_RESULTS_LOOKBACK_DAYS, league_ids=league_ids, max_days=max_days,
            skip=closing)
        wanted = {day: set(self.due_result_keys(day, self._pending_groups(day, skip=closing)))
                  for day in days}
        # The same for the competition-days they put in play: behind the results lookback, within
        # the pass's cap on days, one request per competition not already priced.
        lookback_from = now.date() - timedelta(days=max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0))
        due_ids = {m.id for m in due}
        for m in put_back:
            day = m.match_date.date()
            key = self.registry.canonical_key_for_league(getattr(m, "league_id", None))
            if m.id not in due_ids or day >= lookback_from or not key:
                continue
            if day not in wanted:
                if len(wanted) >= max_days:
                    continue
                wanted[day] = set()
            wanted[day].add(key)
        days = sorted(wanted)
        results_requests = sum(len(keys) for keys in wanted.values())
        will_poll = bool(due) and self._live_poll_within_daily_ceiling()
        return {"stranded": stranded, "due": due, "reopenable": reopenable,
                "superseded": superseded, "relisted": relisted, "days": days,
                "results_requests": results_requests, "live_requests": 1 if will_poll else 0}

    def recover_stranded(self, *, max_days: int = STALE_SWEEP_MAX_DAYS,
                         max_results_requests: Optional[int] = None,
                         poll_live: bool = True,
                         days: Optional[List[date]] = None,
                         stranded: Optional[List[Match]] = None) -> Dict[str, Any]:
        """
        One unattended pass over the fixtures no ordinary refresh reaches, within a stated bound.

        WHAT IT ASKS, AND WHEN. Nothing is assumed about any competition from its type: the archive
        has answered for national-team competitions and has also gone days without answering for
        club ones (docs/evidence/livescore-archive-observations.json). So every fixture is asked
        about on the same retry schedule (`RETRY_SCHEDULE`), which thins out with age and is a
        budget policy only. The pass:

        0. closes every second listing of a played match (`MatchRegistry.retire_relisted`). Such a
           fixture is not stranded: it was never going to be played as listed, so every ask made
           about it was a request spent on nothing. Costs nothing;
        1. undoes any stop made by a rule this installation no longer applies
           (`undo_superseded_stops`) - a stop no current policy made is taken off the row, not
           renamed - and reopens any given-up fixture the archive has since been seen to move past
           (`reopen_retired`). Both cost nothing;
        2. if at least one fixture is due, polls `matches/live.json` once. How long that feed keeps
           a finished match is not known, so a poll that settles a fixture is credited as its
           recovery and a poll that does not mention one is not read as an answer about it either
           way;
        3. asks `matches/history.json` for each due competition-day BEHIND the results lookback
           (the results task asks about the days inside it, on the same schedule). What each call
           got back is recorded where it is made: see `_sync_results`.

        WHAT IT SPENDS. At most `max_results_requests` results requests, floored by what is left
        of `SYNC_RECOVERY_MAX_REQUESTS_PER_DAY`, plus one live poll charged to the live task's own
        daily counter and ceiling. A pass with nothing due makes no request of either kind. What is
        charged is what the provider was sent: a request that went out and failed was still spent
        and counts against both ceilings exactly as an answered one does, a day whose answer ran to
        a second page counts both pages, and a call refused before sending counts nothing.

        WHAT IT CONCLUDES. Each fixture takes exactly one `RecoveryOutcome`. Only FRESH_UNANSWERED
        - the provider answered for its competition and day without a result for it - is an
        attempt. PROVIDER_ERROR is a request that went out and that nobody answered, and is
        reported as a failure of the pass (`failed_calls`); DEFERRED is a due ask for which no
        request was made - an allowance could not cover it, the provider was cooling down after
        a failure, or no provider in the chain can name its competition; NOT_ASKED is a fixture
        nothing was due for. None of those three spends an attempt or retires anything.

        `days` and `stranded` are for a caller that has already made the selection and wants this
        exact pass over it; left out, the pass selects its own.
        """
        now = self.now
        league_ids = self.league_ids()
        self._outcomes, self._written, self._archive_seen = {}, set(), {}
        self._competition_calls = {}
        relisted = self.registry.retire_relisted(now, league_ids)
        undone = self.registry.undo_superseded_stops(now, league_ids)
        reopened = self.registry.reopen_retired(now, league_ids)
        if stranded is None:
            stranded = self.registry.recoverable_unsettled(now, league_ids)
        else:
            closed = {m.id for m in relisted}
            stranded = [m for m in stranded if m.id not in closed]
        report: Dict[str, Any] = {
            "stranded": len(stranded), "due": 0,
            "relisted": [{"match_id": str(m.id),
                          "relisted_as": ((m.match_metadata or {}).get(RELISTED_KEY) or {}).get("match_id")}
                         for m in relisted],
            "reopened": [str(m.id) for m in reopened],
            "stops_undone": [str(m.id) for m in undone],
            "outcomes": {outcome.value: 0 for outcome in RecoveryOutcome},
            "fixtures": [], "days": {}, "live": None, "live_note": None,
            "results_requests": 0, "live_requests": 0,
            "deferred": [], "errors": [], "failed_calls": [], "archive": {},
            "retired": 0, "overdue": 0,
        }
        if not stranded:
            report["note"] = "no fixture is stranded; no provider request was made"
            self.db.commit()
            return report

        settled_before = {m.id: is_settled(m.status) for m in stranded}
        swept_under = {m.id: m.match_date.date() for m in stranded}
        due_now = {m.id for m in stranded if retry_due(m, now)}
        report["due"] = len(due_now)
        lookback = max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0)
        lookback_from = now.date() - timedelta(days=lookback)
        if days is None:
            days = self.registry.stale_unsettled_days(now, lookback, league_ids=league_ids,
                                                      max_days=max_days)

        # -- one live poll, for every competition at once, and only when something is due.
        live_meta, live_tried, report["live_note"] = self._recovery_live_poll(poll_live, bool(due_now))
        report["live"] = live_meta.to_dict()
        report["live_requests"] = live_meta.requests
        if live_tried and (not live_meta.live_polled or live_meta.stale):
            why = "; ".join(live_meta.errors) or "no provider answered"
            if live_meta.request_failed:
                # A poll went out and nobody answered it: the outage the pass must report.
                report["failed_calls"].append("live: " + why)
            else:
                # Nothing left: every provider was cooling down, or an allowance refused the poll.
                report["live_note"] = "live poll not made, no request was sent: " + why
        report["errors"].extend(live_meta.errors)

        # -- the archive, for each due competition-day behind the results lookback.
        allowance = self._results_allowance(max_results_requests)
        #: (day, competition) pairs a due ask was wanted for and the allowance could not cover. A
        #: deferral is not an answer, so it is kept apart from what the calls recorded.
        deferred_keys: set = set()
        for day in days:
            wanted = self.due_result_keys(day)
            take = wanted[:max(allowance, 0)]
            deferred_keys.update((day, key) for key in wanted[len(take):])
            report["deferred"].extend(f"{key}@{day.isoformat()}" for key in wanted[len(take):])
            if not take:
                continue
            meta = SyncMeta()
            called = self._sync_results(day, meta, keys=take)
            # WHAT WAS SENT IS WHAT WAS SPENT. `meta.requests` is read off the provider's own
            # budget around the call, so a request that went out and failed is charged like one
            # that was answered, an extra page is charged as the request it was, and a cache hit
            # or a call refused before it left is charged nothing.
            spent = meta.requests
            allowance -= spent
            report["results_requests"] += spent
            # One call can end differently for different competitions - answered for one, nobody
            # able to name another - so what is reported per competition is what each got.
            calls = {key: self._competition_calls[(key, day.isoformat())] for key in take
                     if (key, day.isoformat()) in self._competition_calls}
            report["days"][day.isoformat()] = {**meta.to_dict(), "competitions": len(take),
                                               "call": called, "calls": calls}
            report["errors"].extend(meta.errors)
            if "failed" in calls.values():
                report["failed_calls"].append(f"results {day.isoformat()}: "
                                              + ("; ".join(meta.errors) or "no provider answered"))
            report["deferred"].extend(f"{key}@{day.isoformat()}" for key, outcome in calls.items()
                                      if outcome == "deferred")
        note_recovery_requests(self.cache, now, report["results_requests"])
        reopened_ids = {m.id for m in reopened}
        undone_ids = {m.id for m in undone}

        # -- one outcome per fixture, from what the calls above actually recorded.
        for match in stranded:
            self.db.refresh(match)
            if settled_before[match.id]:
                continue
            settled_now = is_settled(match.status)
            key = self.registry.canonical_key_for_league(getattr(match, "league_id", None))
            its_days = {swept_under[match.id], match.match_date.date()}
            recorded = self._outcomes.get(match.id)
            if recorded is not None:
                outcome, detail = recorded
                if match.id not in self._written:
                    # A cached day, or a fixture settled at its first ask: `_sync_results` leaves
                    # those off the row, and the pass that asked writes them itself.
                    self.registry.record_recovery_outcome(match, outcome, detail, now)
            elif settled_now:
                outcome, detail = classify_recovery_outcome(
                    live_meta if live_meta.live_polled else SyncMeta(),
                    settled_before=False, settled_now=True)
                self.registry.record_recovery_outcome(match, outcome, detail, now)
            elif match.id in due_now and any((d, key) in deferred_keys for d in its_days):
                outcome = RecoveryOutcome.DEFERRED
                detail = ("due an ask, but the recovery allowance for this pass or this day was "
                          "spent; it stays due")
                self.registry.record_recovery_outcome(match, outcome, detail, now,
                                                      deferred_because=["our_allowance"])
            elif (match.id in due_now and all(d < lookback_from for d in its_days)
                  and not its_days & set(days)):
                outcome = RecoveryOutcome.DEFERRED
                detail = (f"due an ask, but one pass reopens at most {max_days} day(s), oldest "
                          f"first; it stays due")
                self.registry.record_recovery_outcome(match, outcome, detail, now,
                                                      deferred_because=["our_allowance"])
            else:
                outcome = RecoveryOutcome.NOT_ASKED
                if match.id in due_now and any(d >= lookback_from for d in its_days):
                    detail = "its day is inside the results lookback; the results task asks about it"
                elif match.id in due_now:
                    detail = "due, but no call this pass covered it"
                else:
                    upcoming = next_ask_after(match, now)
                    detail = (f"not due under the retry schedule until "
                              f"{upcoming.isoformat() if upcoming else 'it is reopened'}")
            report["outcomes"][outcome.value] += 1
            overdue = self.registry.overdue_state(match, now)
            report["overdue"] += 1 if overdue["overdue"] else 0
            report["retired"] += 1 if overdue["unresolved"] else 0
            report["fixtures"].append({
                "match_id": str(match.id), "match_date": match.match_date.isoformat(),
                "status": match.status.value, "outcome": outcome.value, "detail": detail,
                "reopened": match.id in reopened_ids, "stop_undone": match.id in undone_ids,
                **overdue})
        self.db.commit()
        report["archive"] = {f"{key}@{day}": seen for (key, day), seen in self._archive_seen.items()}
        return report

    def _results_allowance(self, max_results_requests: Optional[int]) -> int:
        """How many results requests this pass may make: the per-pass cap, floored by the day's.

        Both bounds are real and the smaller wins. The per-pass cap stops one pass taking the
        whole day's allowance in a single sweep; the daily ceiling is the figure the budget plan
        adds up, and it is what stops a fortnight of stranded fixtures turning the repair into the
        thing that starves the club competitions.
        """
        per_pass = (max(int(settings.SYNC_RECOVERY_MAX_REQUESTS_PER_PASS), 0)
                    if max_results_requests is None else max(int(max_results_requests), 0))
        left = recovery_requests_left_today(self.cache, self.now)
        return per_pass if left is None else min(per_pass, left)

    def _recovery_live_poll(self, poll_live: bool,
                            anything_due: bool) -> Tuple[SyncMeta, bool, Optional[str]]:
        """The pass's one live poll: its meta, whether a poll was attempted, and why not if not.

        A poll the pass chose not to make is a policy decision and is never recorded as an error:
        an error is a call that was made and that nobody answered, which is what an outage looks
        like. The three reasons not to poll are that the caller said not to, that no stranded
        fixture is due under the retry schedule, and that the day's live ceiling is reached.
        """
        meta = SyncMeta()
        if not poll_live:
            return meta, False, "live poll not attempted by this pass"
        if not anything_due:
            return meta, False, "no stranded fixture is due under the retry schedule"
        if not self._live_poll_within_daily_ceiling():
            return meta, False, (f"live poll skipped: the day's live-poll ceiling is reached "
                                 f"({self._live_polls_today()}/"
                                 f"{int(settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY)})")
        self._sync_live(meta, require_window=False)
        # A poll that went out is counted, answered or not: the provider charged it either way.
        # One served from the 60-second live cache, or refused before it left, spent nothing, and
        # charging it to the ceiling would stop the day early over a request never made.
        if meta.requests > 0:
            self._note_live_poll()
        return meta, True, None

    # ------------------------------------------------------ the coverage calendar (see the top)
    def coverage_record(self, key: str) -> Dict[str, Any]:
        """What is known about when `key` next plays. An empty mapping means nothing is known.

        Reads Redis and nothing else. Never a provider request, so every caller that only wants to
        decide whether to ask about a competition can consult it freely.
        """
        record = self.cache.get(COVERAGE_CALENDAR_KEY.format(key=key))
        return dict(record) if isinstance(record, dict) else {}

    def _store_coverage_record(self, key: str, record: Dict[str, Any]) -> None:
        # Kept well past its own refresh time so the rotation can still read WHEN it was last
        # checked: a record that vanished at its refresh time would make a competition checked a
        # fortnight ago indistinguishable from one never checked at all, and the rotation orders
        # by exactly that.
        ttl = COVERAGE_CALENDAR_MAX_SECONDS * 2
        self.cache.set(COVERAGE_CALENDAR_KEY.format(key=key), record, ttl=ttl, stale_ttl=ttl)

    def _coverage_head_payload(self, provider: MatchDataProvider, key: str) -> List[Dict[str, Any]]:
        """One competition's next fixtures from one provider. Contractually one request."""
        head = provider.get_calendar_head(key, limit=COVERAGE_CALENDAR_HEAD_LIMIT)
        if head is None:
            raise ProviderNotConfiguredError(
                f"{provider.name} publishes no calendar for {key}", provider=provider.name)
        return [_fixture_to_dict(f) for f in head]

    def _coverage_refresh_wait(self, next_kickoff: Optional[datetime]) -> int:
        """How long this answer is believed, from the competition's own next kickoff.

        Nothing listed means the competition is dormant and is left for the maximum. A kickoff
        already inside the lead window means it is about to play, or playing, and is re-read on the
        minimum. In between, the refresh is brought forward to the lead so the days that matter are
        known before a task has to cover them.
        """
        if next_kickoff is None:
            return COVERAGE_CALENDAR_MAX_SECONDS
        ahead = (next_kickoff - self.now).total_seconds() - COVERAGE_CALENDAR_LEAD_SECONDS
        return int(min(max(ahead, COVERAGE_CALENDAR_MIN_SECONDS), COVERAGE_CALENDAR_MAX_SECONDS))

    def refresh_coverage_calendar(self, key: str) -> Dict[str, Any]:
        """Read one competition's calendar and record when it next plays. At most one request.

        Goes through `_call_chain`, so the provider cool-downs, the stale copy and the fallback
        chain apply exactly as they do to every other fetch, and through the SAME per-provider
        calendar ceiling the empty-state sweep is bounded by - one request's worth of it rather
        than a whole sweep's. That ceiling is therefore what bounds this rotation as well, and the
        two share one number instead of each having their own.

        A refresh nobody could answer records the attempt and retries on the minimum wait. Holding
        a dormant competition's fortnight against an outage would make one bad afternoon look like
        a competition with nothing scheduled.
        """
        meta = SyncMeta()
        previous = self.coverage_record(key)
        record: Dict[str, Any] = {"key": key, "checked_at": self.now.isoformat()}
        try:
            payload = self._call_chain(
                COVERAGE_HEAD_CACHE_KEY.format(key=key), COVERAGE_CALENDAR_MIN_SECONDS, meta,
                lambda p: self._coverage_head_payload(p, key),
                skip=lambda p: self._calendar_ceiling_refusal(p, requests=1))
        except ProviderError as exc:
            # The days already known are CARRIED, not cleared. An afternoon nobody could be asked
            # about is not evidence that a competition stopped playing, and dropping its fixture
            # days here would stop the fixtures task asking about a matchday it already knew of -
            # turning one failed request into half a day of missing fixtures.
            record.update({
                "answered": bool(previous.get("answered")),
                "error": str(exc)[:MAX_COVERAGE_ERROR_CHARS],
                "fixture_days": list(previous.get("fixture_days") or []),
                "fixtures": list(previous.get("fixtures") or []),
                "next_kickoff": previous.get("next_kickoff"),
                "refresh_after": (self.now + timedelta(
                    seconds=COVERAGE_CALENDAR_MIN_SECONDS)).isoformat()})
            self._store_coverage_record(key, record)
            return record
        horizon = self.now.date() + timedelta(days=COVERAGE_CALENDAR_HORIZON_DAYS)
        days: List[str] = []
        kickoffs: List[datetime] = []
        for entry in payload:
            kickoff = parse_utc(entry.get("kickoff_utc"))
            if kickoff is None or kickoff.date() > horizon:
                continue
            kickoffs.append(kickoff)
            if kickoff.date().isoformat() not in days:
                days.append(kickoff.date().isoformat())
        next_kickoff = min(kickoffs) if kickoffs else None
        record.update({
            "answered": True,
            "source": meta.source,
            "provider": meta.provider,
            "fixture_days": sorted(days),
            "fixtures": payload[:COVERAGE_CALENDAR_FIXTURES_KEPT],
            "next_kickoff": next_kickoff.isoformat() if next_kickoff else None,
            "refresh_after": (self.now + timedelta(
                seconds=self._coverage_refresh_wait(next_kickoff))).isoformat(),
        })
        self._store_coverage_record(key, record)
        return record

    def coverage_refresh_due(self, limit: int) -> List[str]:
        """National-team competitions whose calendar is worth paying for again, stalest first.

        Strictly stalest-first, with the registry order breaking ties, is what makes the rotation
        fair: a competition passed over this pass has an older `checked_at` than the ones that were
        not, so it goes ahead of them next pass. No competition can be refreshed twice while
        another waits, and none can be starved however long the list grows.

        Club competitions are never in this list. They are asked for on every pass regardless, so
        buying them a calendar would tell us something we are not going to act on, and it would put
        them in competition with the national set for the same bounded number of turns.
        """
        limit = max(int(limit), 0)
        if not limit:
            return []
        now = self.now
        due: List[Tuple[datetime, int, str]] = []
        for position, key in enumerate(self.national_keys):
            record = self.coverage_record(key)
            refresh_after = parse_utc(record.get("refresh_after"))
            if refresh_after is not None and now < refresh_after:
                continue
            due.append((parse_utc(record.get("checked_at")) or _EPOCH, position, key))
        due.sort()
        return [key for _, _, key in due[:limit]]

    def coverage_keys_for_day(self, day: date) -> List[str]:
        """Covered competitions worth asking about `day`, in registry order.

        Three things put a competition in it, and the first is unconditional:

          - every CLUB competition, always. They play weekly, their pass is what this installation
            has always paid for, and nothing about national-team coverage may take a request away
            from them. This is the guarantee, and it is a membership rule rather than a priority
            ordering, so it cannot be lost to a cap applied further up;
          - a national-team competition whose coverage calendar lists a fixture that day;
          - a national-team competition that already has a stored match that day, which is how a
            fixture keeps being refreshed for kickoff changes and postponements after the calendar
            that first named it has moved on.
        """
        wanted = set(self.club_keys)
        stamp = day.isoformat()
        for key in self.national_keys:
            if stamp in (self.coverage_record(key).get("fixture_days") or []):
                wanted.add(key)
        wanted.update(self._stored_match_keys(day))
        return [k for k in self.keys if k in wanted]

    def _stored_match_keys(self, day: date) -> List[str]:
        """Covered competitions that already hold a match row on `day`."""
        by_league = self._league_key_map()
        found = []
        for m in self.registry.matches_for_day(day, self.league_ids()):
            key = by_league.get(getattr(m, "league_id", None))
            if key is not None and key not in found:
                found.append(key)
        return found

    def sync_upcoming(self, key: str, days_ahead: int = 14) -> SyncMeta:
        """Fill the calendar of one competition (used by league pages and the expert match picker)."""
        meta = SyncMeta()
        cache_key = f"matchdata:upcoming:{key}:{days_ahead}"
        try:
            payload = self._call_chain(cache_key, settings.MATCH_CACHE_TTL_FIXTURES * 4, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_upcoming(
                                           self._askable(p, [key])[0], days_ahead)])
        except ProviderError as exc:
            meta.errors.append(str(exc))
            return meta
        # Also a list of matches to come, so it is counted the same way `sync_day`'s fixture list
        # is. Nothing reads these counters off this path today; they are here so the two forward
        # fetches cannot drift into meaning different things.
        meta.forward_source, meta.forward_fetched_at = meta.source, meta.fetched_at
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta, forward=True)
        self.db.commit()
        return meta

    # ------------------------------------------------------------------ the calendar head
    @property
    def _calendar_sweep_keys(self) -> List[str]:
        """The competitions an empty-state calendar sweep pays for: the club set, and only it.

        A sweep costs one request per competition in it, so sweeping all 35 would cost 35 a time
        against a daily share of 120 - three sweeps a day, where six competitions get four, and
        a feature whose whole point is that a reader refreshing the page cannot spend the day's
        allowance. The national-team competitions are already being read by the rotation, one at a
        time and on their own schedule, so their next fixtures are merged in from those records
        instead of being bought again here. An ordinary page visit therefore costs exactly what it
        costs today, whatever the coverage setting says.
        """
        return self.club_keys

    def _merge_coverage_into_calendar(self, answer: Dict[str, Any]) -> Dict[str, Any]:
        """Add the national-team competitions to a swept club calendar, free, from their records.

        A competition the rotation has not reached yet, or could not read, is named in
        `unanswered` rather than left out silently: "we have not been told" and "it has nothing
        scheduled" are the two facts this answer exists to keep apart, and a competition missing
        from both lists would read as the second.
        """
        fixtures = list(answer.get("fixtures") or [])
        unanswered = list(answer.get("unanswered") or [])
        for key in self.national_keys:
            record = self.coverage_record(key)
            if not record.get("answered"):
                unanswered.append(key)
                continue
            fixtures.extend(record.get("fixtures") or [])
        fixtures.sort(key=lambda entry: entry.get("kickoff_utc") or "")
        return {"fixtures": fixtures, "unanswered": unanswered}

    def _calendar_head_payload(self, provider: MatchDataProvider, per_competition: int,
                               meta: SyncMeta) -> Dict[str, Any]:
        """Every covered competition's next fixtures, from one provider, in kickoff order.

        One `get_calendar_head` per competition, and that method is contractually one request, so
        this whole sweep costs at most one request per covered competition.

        A provider that publishes no calendar declines every competition without making a request.
        That is reported as `ProviderNotConfiguredError` so `_call_chain` moves to the next
        provider in the chain and does NOT put this one in cool-down: lacking an endpoint is not a
        failure, and a provider that still serves fixtures perfectly well must not be shut out of
        the fixture path because it cannot answer this question.

        Competitions that declined are carried in the payload itself, under `unanswered`, because
        the payload is what is cached and served for the next several hours. A caveat recorded
        only in `meta.errors` belongs to the one request that made the sweep; every reader after
        it would be handed the shortened fixture list with nothing to say it was shortened.
        """
        fixtures: List[ProviderFixture] = []
        declined: List[str] = []
        for key in self._calendar_sweep_keys:
            head = provider.get_calendar_head(key, limit=per_competition)
            if head is None:
                declined.append(key)
                continue
            fixtures.extend(head)
        if len(declined) == len(self._calendar_sweep_keys):
            raise ProviderNotConfiguredError(
                f"{provider.name} publishes no competition calendar, so it cannot say which "
                f"fixtures come next", provider=provider.name)
        if declined:
            # `errors` is this request's diagnostics; `unanswered` below is the part of the same
            # fact that survives into the cached answer and out to the caller.
            meta.errors.append(f"{provider.name}: no calendar answer for " + ", ".join(declined))
        fixtures.sort(key=lambda f: f.kickoff_utc)
        return {"fixtures": [_fixture_to_dict(f) for f in fixtures], "unanswered": declined}

    def _claim_calendar_refresh(self) -> bool:
        """True when this caller may pay for a calendar sweep; False when one is already in flight.

        Best effort, like every other Redis-backed guard here: with no Redis there is nothing to
        coordinate through, and refusing to answer at all would be a worse failure than a
        duplicated sweep on a single-process install.
        """
        client = getattr(self.cache, "_redis", lambda: None)()
        if client is None:
            return True
        try:
            return bool(client.set(CALENDAR_HEAD_LOCK_KEY, "1", nx=True, ex=CALENDAR_HEAD_LOCK_SECONDS))
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.debug("Calendar-head refresh guard unavailable (%s); proceeding without it", exc)
            return True

    # ------------------------------------------------ what a failing sweep is allowed to cost
    def _calendar_backoff_record(self) -> Dict[str, Any]:
        """The current failure streak, or an empty mapping when there is none to serve."""
        record = self.cache.get(CALENDAR_HEAD_BACKOFF_KEY)
        return record if isinstance(record, dict) else {}

    def _calendar_backoff_refusal(self) -> Optional[str]:
        """Why this sweep is too soon after the last failed one, or None when it may go ahead."""
        retry_at = parse_utc(self._calendar_backoff_record().get("retry_at"))
        if retry_at is None or self.now >= retry_at:
            return None
        failures = int(self._calendar_backoff_record().get("failures") or 0)
        return (f"the competition calendar could not be read {failures} time(s) in a row, so the "
                f"next attempt is held until {retry_at.isoformat()}")

    def _note_calendar_sweep_failure(self) -> None:
        """Lengthen the wait before the next sweep, doubling for each failure in a row.

        Counts a sweep that produced no answer, which is not only a sweep that reached the
        network and was refused: a chain whose every provider is already in cool-down produced no
        answer either, and re-asking it every two minutes costs the same readers the same wait for
        the same nothing.
        """
        failures = int(self._calendar_backoff_record().get("failures") or 0) + 1
        # The exponent is capped before it is used, not after: a long outage must not build a
        # number whose only purpose is to be thrown away by `min`.
        wait = min(CALENDAR_HEAD_BACKOFF_BASE_SECONDS * 2 ** min(failures - 1, 16),
                   CALENDAR_HEAD_BACKOFF_CEILING_SECONDS)
        record = {"failures": failures,
                  "wait_seconds": wait,
                  "retry_at": (self.now + timedelta(seconds=wait)).isoformat()}
        # Kept one ceiling longer than the wait itself, so the streak survives into the attempt
        # that follows it and keeps growing; see CALENDAR_HEAD_BACKOFF_CEILING_SECONDS.
        ttl = wait + CALENDAR_HEAD_BACKOFF_CEILING_SECONDS
        self.cache.set(CALENDAR_HEAD_BACKOFF_KEY, record, ttl=ttl, stale_ttl=ttl)
        logger.info("Competition-calendar sweep failed (%d in a row); next attempt in %ds",
                    failures, wait)

    def _clear_calendar_backoff(self) -> None:
        """Forget the failure streak. A sweep that answered is the evidence that ends it."""
        if self._calendar_backoff_record():
            self.cache.delete(CALENDAR_HEAD_BACKOFF_KEY)

    def _calendar_ceiling_refusal(self, provider: MatchDataProvider,
                                  requests: Optional[int] = None) -> Optional[str]:
        """Why THIS provider may not be swept today, or None when its own share still has room.

        `requests` is how many the caller is about to spend, defaulting to a whole sweep. The
        rotation that refreshes one competition's coverage calendar passes 1, so it is bounded by
        this same share rather than by a second ceiling of its own - which is what keeps the two
        features that read calendars from adding up to more than the number written down here.

        This is where the ceiling binds, and it has to be here rather than only in front of the
        chain: a ceiling is per provider because a budget is, so "some provider has room" is not
        a reason to spend the one that has none. `_call_chain` passes every candidate through
        this and skips the ones it names, which is what routes a sweep past a capped provider to
        the next in the chain instead of charging the capped one anyway.

        The share is read from the budget's own `calendar` attribution, so the number enforced is
        the number the provider recorded rather than a second count of our own.

        What that counts is GRANTED requests, and a provider may charge itself more than it was
        asked for: `livescore_api._get` retries once after a burst 401 and attributes that second
        outbound request to `retry`, which lands in the day's total but not in this share. So the
        relationship is a bound and not an equality - this refuses after
        `CALENDAR_HEAD_DAILY_REQUEST_CEILING` granted calendar requests, and those cost the plan
        the same number of outbound calls, or at worst twice it when every one meets a burst 401.

        A provider with no budget at all publishes no attribution to read, so nothing here can say
        it is out. A counter store that cannot be read answers 0, which lets the sweep through,
        exactly as `RequestBudget.remaining()` does for every other caller; the cheap floor in
        that state is the backoff, which lives in the match cache rather than the counter store.
        """
        budget = getattr(provider, "budget", None)
        try:
            limit = int(getattr(budget, "daily_limit", 0) or 0)
            if budget is None or not limit:
                return None
            # Scaled to the plan the same way SYNC_SCHEDULER_BUDGET_RESERVE is, so a small
            # allowance is never mostly spent on a calendar.
            ceiling = min(CALENDAR_HEAD_DAILY_REQUEST_CEILING, limit // 10)
            used = int(budget.by_reason().get(CALENDAR_BUDGET_REASON, 0) or 0)
        except Exception as exc:  # pragma: no cover - a ceiling is never worth a crash
            logger.debug("Calendar budget check failed for %s: %s",
                         getattr(provider, "name", "?"), exc)
            return None
        wanted = len(self._calendar_sweep_keys) if requests is None else max(int(requests), 0)
        if used + wanted <= ceiling:
            return None
        # Named for the provider rather than for its budget, to read alongside the cool-down skips
        # `_call_chain` records beside it; the budget belongs to this provider either way.
        return (f"{getattr(provider, 'name', '?')}: today's share of the request allowance for "
                f"reading competition calendars is spent ({used}/{ceiling} used)")

    def _calendar_spend_refusal(self) -> Optional[str]:
        """Why NO provider may be swept today, or None when one of them still has room.

        The per-provider check above is what actually protects each plan. This is the cheap
        question asked before the lock is claimed: when every provider in the chain would be
        skipped there is no sweep to serialise, and a reader who takes the lock anyway would hold
        it against the next reader for nothing.

        It is therefore a summary of the same rule and never a laxer one. If it lets a reader
        through because one provider has room, that provider is the one the chain will reach,
        because the chain skips the others by the same test.

        A chain of providers with no budgets at all constrains nothing and refuses nothing.
        """
        spent = []
        for provider in self.providers:
            refusal = self._calendar_ceiling_refusal(provider)
            if refusal is None:
                return None
            spent.append(refusal)
        if not spent:
            return None
        return "the competition calendar was not read: " + "; ".join(spent)

    def _stale_calendar(self, cache_key: str, meta: SyncMeta) -> Optional[Dict[str, Any]]:
        """A previously swept answer, when one is held and its provider is still in the chain.

        Serving it costs nothing, so every guard that declines to pay for a sweep offers it first.
        Switching DATA_PROVIDER must never resurrect an answer from a provider that is no longer
        configured, which is what the membership test is for.
        """
        stale = self.cache.get_stale(cache_key)
        if stale is None or stale.get("provider") not in {p.name for p in self.providers}:
            return None
        meta.source, meta.provider = "stale-cache", stale.get("provider")
        meta.fetched_at, meta.stale = stale.get("fetched_at"), True
        return stale["data"]

    def next_fixtures(self, per_competition: int = CALENDAR_HEAD_PER_COMPETITION
                      ) -> Tuple[Optional[Dict[str, Any]], SyncMeta]:
        """The next fixtures of the covered competitions, or None when nobody could tell us.

        The answer is `{"fixtures": [...], "unanswered": [competition keys]}`, and the facts it
        can carry are four, which the caller must be able to tell apart:

          fixtures, nothing unanswered   every covered competition's calendar was read and these
                                         come next;
          no fixtures, nothing unanswered  every calendar was read and none lists a fixture still
                                         to come;
          anything with `unanswered`     the competitions named there could not be asked at all,
                                         so what is in `fixtures` speaks only for the rest and may
                                         be missing an earlier kickoff than any of them;
          None                           nobody answered — no provider publishes a calendar, every
                                         one of them failed, a sweep is already in flight, the
                                         last one failed and the next is not due yet, or every
                                         provider has spent its own share of the allowance for
                                         this feature; and in each case there is no copy to serve
                                         meanwhile.

        Collapsing the last onto an empty list would let an outage print "no football is
        scheduled", which is a statement about the world made out of a network error; dropping
        `unanswered` would let a sweep that reached two competitions out of six speak for all six.
        The three guards below are refusals to spend, so they answer the same way an outage does:
        we could not find out. None of them may be reported as a calendar that is empty.

        Nothing here is written to the database. This reads a calendar to describe it, and a
        fixture eighteen days out is stored by the fixtures task when its day comes round.
        """
        meta = SyncMeta()
        # Keyed by the competitions actually SWEPT. The national-team ones are merged in from
        # their own records afterwards, so an answer cached here speaks only for the club set and
        # never goes stale because a rotation refreshed something it does not contain.
        cache_key = (f"matchdata:calendar-head:{CALENDAR_HEAD_SHAPE}:"
                     f"{','.join(self._calendar_sweep_keys)}:{per_competition}")
        if not self.cache.available:
            # One request per competition is affordable BECAUSE the answer is kept for hours.
            # With no cache there is nothing to keep it in, and nothing to stop the next page
            # load repeating the whole sweep, so this declines instead of spending. Every other
            # read here degrades to calling the provider again; this one must not, because it is
            # the only one a reader can trigger by doing nothing but reloading an empty day.
            meta.errors.append("no cache is available to hold a competition calendar, so it was "
                               "not read")
            return None, meta
        # Only a cold cache can cost anything, so only a cold cache is subject to the guards.
        # `_call_chain` re-reads the same key straight after, which also picks up a sweep that
        # finished while this request was deciding.
        if self.cache.get(cache_key) is None:
            # Order is cheapest question first, and the lock is claimed last: a reader the backoff
            # or the ceiling turns away must not take a lock it is never going to use, because
            # holding it would block the reader who arrives once the wait is over.
            refusal = (self._calendar_backoff_refusal()
                       or self._calendar_spend_refusal()
                       or (None if self._claim_calendar_refresh()
                           else "a refresh of the competition calendar is already in flight"))
            if refusal is not None:
                stale = self._stale_calendar(cache_key, meta)
                if stale is not None:
                    return self._merge_coverage_into_calendar(stale), meta
                meta.errors.append(refusal)
                return None, meta
        try:
            answer = self._call_chain(cache_key, CALENDAR_HEAD_TTL_SECONDS, meta,
                                      lambda p: self._calendar_head_payload(p, per_competition, meta),
                                      skip=self._calendar_ceiling_refusal)
        except ProviderError as exc:
            # `_call_chain` records every provider it tried in `meta.errors` and then raises the
            # last of those failures, so recording it here as well would show one failure twice
            # and make a three-provider chain read as four distinct ones. What is NOT already
            # there is the case where the chain tried nobody at all - no provider configured -
            # and that message is the only account of why there is no answer.
            #
            # The test is CONTAINMENT, not equality, because the two are not always the same
            # string: the chain skips a provider that failed recently by recording
            # "<name>: skipped (recent failure: <why>)" - or "(allowance spent: <why>)" when the
            # cool-down was an allowance refusing - while the error it raises carries only
            # "<why>". Comparing those for equality lets the skip through twice, which is the
            # over-count this guard exists to prevent.
            message = str(exc)
            if not any(message in recorded for recorded in meta.errors):
                meta.errors.append(message)
            # A CEILING IS NOT A FAILURE, and must not be answered with a failure's brake.
            # `_call_chain` skips a provider whose calendar share is spent by raising a quota
            # error on its behalf, so declining to spend arrives here wearing the same coat as a
            # provider that is broken. Escalating the backoff for it would apply a growing wait
            # for a reason that never happened, and - because the wait is measured in minutes
            # while the share is measured in UTC days - would carry that wait past the midnight
            # that refills the allowance.
            #
            # Both kinds of quota already have a brake of the right size. Our own ceiling IS the
            # brake for the share we set ourselves; a provider that says it is out of quota gets a
            # cool-down that runs to UTC midnight, set where that error is caught above. Neither
            # needs a third one measured in minutes.
            if not isinstance(exc, ProviderQuotaError):
                self._note_calendar_sweep_failure()
            return None, meta
        # What the backoff reacts to is where the answer came from, because that is what says
        # whether a sweep happened at all. "provider" is a sweep that answered and ends a streak.
        # "stale-cache" is a sweep whose every provider failed, answered out of a copy on the way
        # past - the failure is just as real and just as worth backing off from. "cache" means no
        # sweep was attempted, so it is evidence of nothing and leaves the streak as it stands.
        if meta.source == "provider":
            self._clear_calendar_backoff()
        elif meta.source == "stale-cache":
            self._note_calendar_sweep_failure()
        return self._merge_coverage_into_calendar(answer), meta

    def last_forward_fixture_stored_at(self) -> Optional[datetime]:
        """When a match row was most recently written before its own kickoff, or None.

        The fixtures task reports when a fixture was last offered to it. When it holds no
        recorded sighting to carry forward there is still something knowable here, and without it
        the task reports "never on this installation" while rows written ahead of kickoff sit in
        this table - which reads as a broken integration rather than a quiet calendar.

        `created_at < match_date` is the mark a fixture stored in advance leaves behind. It does
        not prove which ingest wrote the row, so the caller reports it under its own basis and
        never as something a pass of this task saw. The strict comparison is the point of the
        filter: a row created at or after its own kickoff is not evidence of a calendar arriving
        early. The live poll writes one when it meets a fixture it cannot identify against a row
        already held — it updates the row and leaves `created_at` alone when it can — and so does
        the placeholder match the expert-prediction flow creates dated `utcnow()`; dating a
        sighting from either would report a fixture arriving in advance where none did.
        """
        try:
            value = self.db.query(func.max(Match.created_at)).filter(
                Match.created_at < Match.match_date).scalar()
        except Exception:  # a seed for a report must never be the thing that fails a sync pass
            logger.debug("Could not read the newest stored forward fixture", exc_info=True)
            return None
        if not isinstance(value, datetime):
            # None on an empty table. Anything else did not come from the timestamp column and is
            # not evidence that a fixture was ever stored.
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def matches_for_day(self, day: date, refresh: bool = True) -> Tuple[List[Match], SyncMeta]:
        meta = self.sync_day(day) if refresh else SyncMeta()
        matches = self.registry.matches_for_day(day, self.league_ids())
        return matches, meta

    def live_matches(self) -> Tuple[List[Match], SyncMeta]:
        meta = SyncMeta()
        self._sync_live(meta)
        matches = [m for m in self.registry.matches_for_day(self.now.date(), self.league_ids()) if m.status == MatchStatus.LIVE]
        return matches, meta

    def match_by_id(self, match_id) -> Optional[Match]:
        return self.db.query(Match).filter(Match.id == match_id).first()

    # ------------------------------------------------------------------ standings
    def standings(self, key: str) -> Tuple[List[ProviderStanding], SyncMeta]:
        meta = SyncMeta()
        cache_key = f"matchdata:standings:{key}"

        def serial(p: MatchDataProvider):
            rows = p.get_standings(self._askable(p, [key])[0])
            return [{"position": r.position, "team": {"provider": r.team.provider, "external_id": r.team.external_id, "name": r.team.name,
                                                       "logo": r.team.logo},
                     "played": r.played, "won": r.won, "drawn": r.drawn, "lost": r.lost, "goals_for": r.goals_for,
                     "goals_against": r.goals_against, "goal_difference": r.goal_difference, "points": r.points, "form": r.form}
                    for r in rows]

        try:
            payload = self._call_chain(cache_key, settings.MATCH_CACHE_TTL_STANDINGS, meta, serial)
        except ProviderError as exc:
            meta.errors.append(str(exc))
            return [], meta
        from app.services.providers.base import ProviderTeam
        rows = [ProviderStanding(position=r["position"], team=ProviderTeam(provider=r["team"]["provider"], external_id=r["team"]["external_id"],
                                                                            name=r["team"]["name"], logo=r["team"].get("logo")),
                                 played=r["played"], won=r["won"], drawn=r["drawn"], lost=r["lost"], goals_for=r["goals_for"],
                                 goals_against=r["goals_against"], goal_difference=r["goal_difference"], points=r["points"], form=r.get("form") or [])
                for r in payload]
        return rows, meta

    # ------------------------------------------------------------------ status
    def provider_status(self) -> Dict[str, Any]:
        chain = []
        for p in self.providers:
            status = self.cache.get(STATUS_KEY.format(name=p.name)) or {}
            budget = getattr(p, "budget", None)
            chain.append({"name": p.name, "integration_status": p.integration_status, "configured": p.is_configured(),
                          "budget": budget.snapshot() if budget else None, "cooling_down": self._cooldown(p.name), **status})
        return {
            "active_provider": settings.DATA_PROVIDER,
            "configured_fallbacks": [n.strip() for n in settings.DATA_PROVIDER_FALLBACKS.split(",") if n.strip()],
            "covered_competitions": self.keys,
            "cache_available": self.cache.available,
            "chain": chain,
        }
