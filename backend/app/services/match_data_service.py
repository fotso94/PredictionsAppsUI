"""
Match data orchestration: provider chain with fallbacks, Redis caching, request-budget aware
live polling, stale-data degradation, and persistence through the MatchRegistry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import League, Match, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers import competitions as comps
from app.services.providers.base import (
    MatchDataProvider, ProviderError, ProviderFixture, ProviderNotConfiguredError,
    ProviderQuotaError, ProviderAuthError, ProviderStanding, ProviderUnavailableError,
    parse_utc,
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

    def to_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "source": self.source, "stale": self.stale, "fetched_at": self.fetched_at,
                "errors": self.errors, "live_polled": self.live_polled, "results_polled": self.results_polled,
                "ambiguous": self.ambiguous, "fixtures_seen": self.fixtures_seen,
                "fixtures_stored": self.fixtures_stored,
                "forward_fixtures_seen": self.forward_fixtures_seen,
                "forward_fixtures_stored": self.forward_fixtures_stored,
                "forward_source": self.forward_source,
                "forward_fetched_at": self.forward_fetched_at}


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
    )


class MatchDataService:
    def __init__(self, db: Session, providers: Optional[List[MatchDataProvider]] = None, cache: Optional[MatchCache] = None,
                 now: Optional[datetime] = None, keys: Optional[List[str]] = None):
        self.db = db
        self.registry = MatchRegistry(db)
        self.cache = cache or MatchCache()
        self._providers = providers
        self._now = now
        self.keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)

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

    def _record_status(self, name: str, ok: bool, error: Optional[str] = None) -> None:
        payload = self.cache.get(STATUS_KEY.format(name=name)) or {}
        stamp = self.now.isoformat()
        if ok:
            payload.update({"last_success_at": stamp, "last_error": None})
        else:
            payload.update({"last_error_at": stamp, "last_error": error})
        self.cache.set(STATUS_KEY.format(name=name), payload, ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def _cooldown(self, name: str) -> Optional[str]:
        payload = self.cache.get(COOLDOWN_KEY.format(name=name))
        return payload.get("reason") if isinstance(payload, dict) else None

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

    def _set_cooldown(self, name: str, reason: str, seconds: int) -> None:
        self.cache.set(COOLDOWN_KEY.format(name=name), {"reason": reason, "until_seconds": seconds}, ttl=seconds, stale_ttl=seconds)

    def _call_chain(self, cache_key: str, ttl: int, meta: SyncMeta, fn, skip=None):
        """Run `fn(provider)` on the first working provider, with fresh/stale cache around it.

        `skip(provider)` lets a caller refuse to spend at one provider without refusing the whole
        chain: it returns the reason that provider is unaffordable FOR THIS CALLER, or None. A
        named provider is passed over exactly like one in cool-down - recorded, not called, not
        put in cool-down, and carried as the error to report only if nobody further down answers
        either. It is consulted per provider rather than once for the chain because the thing it
        usually guards, a request budget, is per provider too; asking it once and then calling
        whoever happens to be first is how a per-provider limit stops binding on anybody.

        It is not consulted at all when the cache answers, because then nothing is spent.
        """
        cached = self.cache.get(cache_key)
        if cached is not None:
            meta.source, meta.provider, meta.fetched_at = "cache", cached.get("provider"), cached.get("fetched_at")
            return cached["data"]
        last_error: Optional[ProviderError] = None
        for provider in self.providers:
            cooling = self._cooldown(provider.name)
            if cooling:
                meta.errors.append(f"{provider.name}: skipped (recent failure: {cooling})")
                last_error = last_error or ProviderUnavailableError(cooling, provider=provider.name)
                continue
            unaffordable = skip(provider) if skip is not None else None
            if unaffordable:
                meta.errors.append(unaffordable)
                last_error = last_error or ProviderQuotaError(unaffordable, provider=provider.name)
                continue
            try:
                data = fn(provider)
            except ProviderNotConfiguredError as exc:
                meta.errors.append(str(exc)); last_error = exc; continue
            except ProviderQuotaError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), _seconds_until_utc_midnight(self.now)); continue
            except ProviderAuthError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), AUTH_COOLDOWN_SECONDS); continue
            except ProviderError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), UNAVAILABLE_COOLDOWN_SECONDS); continue
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
            raise last_error
        raise ProviderNotConfiguredError("No match-data provider is configured", provider="none")

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

    def sync_day(self, day: date) -> SyncMeta:
        meta = SyncMeta()
        key = f"matchdata:fixtures:{day.isoformat()}:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_FIXTURES, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_fixtures(day, self.keys)])
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
            self._sync_results(day, meta)
        if day == self.now.date():
            self._sync_live(meta)
        return meta

    def _pending_results_exist(self, day: date) -> bool:
        cutoff = (self.now - timedelta(minutes=150)).replace(tzinfo=None)
        for m in self.registry.matches_for_day(day, self.league_ids()):
            if m.status in (MatchStatus.SCHEDULED, MatchStatus.LIVE) and m.match_date <= cutoff:
                return True
        return False

    def _sync_results(self, day: date, meta: SyncMeta) -> None:
        if not self._pending_results_exist(day):
            return
        key = f"matchdata:results:{day.isoformat()}:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_RESULTS, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_results(day, day, self.keys)])
        except ProviderError as exc:
            meta.errors.append(f"results: {exc}")
            return
        meta.results_polled = True
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta)
        self.db.commit()

    def _live_window_open(self) -> bool:
        now_naive = self.now.replace(tzinfo=None)
        for m in self.registry.matches_for_day(self.now.date(), self.league_ids()):
            if m.status == MatchStatus.FINISHED or m.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
                continue
            if m.match_date - timedelta(minutes=15) <= now_naive <= m.match_date + timedelta(minutes=150):
                return True
        return False

    def _sync_live(self, meta: SyncMeta) -> None:
        if not self._live_window_open():
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

    def sync_upcoming(self, key: str, days_ahead: int = 14) -> SyncMeta:
        """Fill the calendar of one competition (used by league pages and the expert match picker)."""
        meta = SyncMeta()
        cache_key = f"matchdata:upcoming:{key}:{days_ahead}"
        try:
            payload = self._call_chain(cache_key, settings.MATCH_CACHE_TTL_FIXTURES * 4, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_upcoming(key, days_ahead)])
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
        for key in self.keys:
            head = provider.get_calendar_head(key, limit=per_competition)
            if head is None:
                declined.append(key)
                continue
            fixtures.extend(head)
        if len(declined) == len(self.keys):
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

    def _calendar_ceiling_refusal(self, provider: MatchDataProvider) -> Optional[str]:
        """Why THIS provider may not be swept today, or None when its own share still has room.

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
        if used + len(self.keys) <= ceiling:
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
        cache_key = f"matchdata:calendar-head:{CALENDAR_HEAD_SHAPE}:{','.join(self.keys)}:{per_competition}"
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
                    return stale, meta
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
            # "<name>: skipped (recent failure: <why>)" while the error it raises carries only
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
        return answer, meta

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
            rows = p.get_standings(key)
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
