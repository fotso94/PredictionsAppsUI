"""
When a competition's forecasts are refreshed, in what order, and when a competition has nothing
to forecast. One object, `RefreshPolicy`, consulted by `ForecastService.ensure_synced` for
eligibility and order and by the scheduler's dry run for what a pass would fetch - so the two
cannot disagree about which competitions a pass walks.

Two policies, chosen by `GAMEFORECAST_REFRESH_POLICY`:

- ``elapsed-interval``: the earlier rule, kept exactly for comparison and rollback. A competition
  is due once `GAMEFORECAST_SYNC_INTERVAL_HOURS` have elapsed since its last sync, least recently
  synced first; the scheduler gates the whole task until `SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR`; a
  turn that cannot be paid for stops the pass. Its measured defect: a competition refreshed at
  20:01 on day D is not eligible at noon on D+1 (16 h elapsed) nor at 17:59 (21 h 58 min), and the
  next pass is gated until noon on D+2 - a 40-hour gap.

- ``daily-slot``: one refresh slot per competition per UTC day. Elapsed time is not consulted.
  A competition is eligible for an automatic paid fetch when it is active (no sufficient calendar
  evidence says it is dormant), unfetched for today - or fetched today with an older run and not
  yet re-checked - and the observed publication hour is reached. Priority 1: unfetched active
  competitions, a competition deferred for allowance first, then nearest kick-off first.
  Priority 2: one re-check per competition per day for an older-run outcome, nearest kick-off
  first, paid from what is left. Priority 3: nothing; what is left stays unspent. A turn that
  cannot be paid for in full defers the competition and the pass moves on to the next affordable
  one.

The publication hour is OBSERVED, never promised by the provider. `SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR`
is the baseline observation (a week of fetch history in which same-day runs were obtained at
12:xx and 18:xx UTC and never at 00:xx); every fetch whose `model_run_at` falls on the fetch's own
UTC date adds an observation at the fetch's hour, the earliest over a rolling fortnight is kept,
and the hour in force is the earliest of the baseline and those observations. An observation can
therefore only bring the hour forward: the baseline is itself an observation, and letting a late
first observation push the hour back would stop the policy ever fetching early enough to observe
an earlier hour again. A fetch that returns an older run records "not yet published at H on D" and
moves nothing.

State lives in Redis beside the other forecast keys, so a restart neither repeats nor forgets a
day's fetch:

  forecast:refresh:{provider}:{key}   the competition's slot: day, fetched_at, model_run_at,
                                      outcome (same-day-run | older-run | empty | dormant |
                                      failed | deferred), and the re-check when one was made
  forecast:publication:{provider}     the observations the publication hour is read from
  forecast:calendar:{provider}:{key}  the last calendar evidence a turn recorded for the key
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

POLICY_DAILY_SLOT = "daily-slot"
POLICY_ELAPSED_INTERVAL = "elapsed-interval"
POLICIES = (POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL)

REFRESH_KEY = "forecast:refresh:{provider}:{key}"
PUBLICATION_KEY = "forecast:publication:{provider}"
CALENDAR_EVIDENCE_KEY = "forecast:calendar:{provider}:{key}"

#: A slot record outlives the fortnight the publication observations are read over, so a
#: deferral recorded before a long stop still puts its competition first when the loop resumes.
REFRESH_TTL_SECONDS = 14 * 24 * 3600
PUBLICATION_TTL_SECONDS = 30 * 24 * 3600
CALENDAR_EVIDENCE_TTL_SECONDS = 7 * 24 * 3600
#: How far back fetch history is read for the publication hour.
OBSERVATION_DAYS = 14

OUTCOME_SAME_DAY_RUN = "same-day-run"
OUTCOME_OLDER_RUN = "older-run"
OUTCOME_EMPTY = "empty"
OUTCOME_DORMANT = "dormant"
OUTCOME_FAILED = "failed"
OUTCOME_DEFERRED = "deferred"

#: Calendar answers that are evidence about the window. "stale-cache" is a copy served because
#: every provider failed, "database" means the chain never answered: neither says anything.
SUFFICIENT_CALENDAR_SOURCES = ("provider", "cache")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return _aware(value).isoformat() if isinstance(value, datetime) else None


def _parse(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


# ------------------------------------------------------------------------- calendar evidence
@dataclass
class CalendarEvidence:
    """What one turn's fixture sync established about the forecast window, and the verdict.

    `dormant` is True only when every condition holds: a fixture sync ran this turn, answered from
    the provider or from a cache copy that is not stale, reported no error, was asked for at least
    the window the verdict is about, and the database then held no fixture still to be played
    inside that window. Anything less leaves the competition active, and `reason` says which
    condition failed - a forecast fetched before its fixture is stored is exactly what the pending
    store exists to attach later, so an empty window with no evidence behind it is never "nothing
    to forecast".
    """

    key: str
    checked_at: str
    window_days: int
    ran: bool
    source: Optional[str]
    stale: bool
    errors: List[str] = field(default_factory=list)
    asked_days: Optional[int] = None
    fixtures_in_window: Optional[int] = None
    dormant: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "checked_at": self.checked_at, "window_days": self.window_days,
                "ran": self.ran, "source": self.source, "stale": self.stale,
                "errors": list(self.errors)[:10], "asked_days": self.asked_days,
                "fixtures_in_window": self.fixtures_in_window, "dormant": self.dormant,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["CalendarEvidence"]:
        if not isinstance(data, dict) or not data.get("key"):
            return None
        try:
            return cls(key=str(data["key"]), checked_at=str(data.get("checked_at") or ""),
                       window_days=int(data.get("window_days") or 0), ran=bool(data.get("ran")),
                       source=data.get("source"), stale=bool(data.get("stale")),
                       errors=[str(e) for e in (data.get("errors") or [])],
                       asked_days=data.get("asked_days"),
                       fixtures_in_window=data.get("fixtures_in_window"),
                       dormant=bool(data.get("dormant")), reason=str(data.get("reason") or ""))
        except (TypeError, ValueError):  # a hand-edited or older record is not evidence
            return None


def judge_calendar(key: str, now: datetime, window_days: int, *, ran: bool,
                   source: Optional[str], stale: bool, errors: Sequence[str],
                   asked_days: Optional[int],
                   count: Callable[[], Optional[int]]) -> CalendarEvidence:
    """The dormancy verdict for one turn. `count` is only consulted once the answer qualifies.

    The database is counted AFTER the calendar answer is judged sufficient, never before: a count
    of zero against a calendar nobody answered is the empty window that says nothing.
    """
    evidence = CalendarEvidence(key=key, checked_at=_aware(now).isoformat(), window_days=window_days,
                                ran=ran, source=source, stale=stale, errors=list(errors),
                                asked_days=asked_days)
    if not ran:
        evidence.reason = "no fixture sync ran this turn, so the window was not checked"
        return evidence
    if evidence.errors:
        evidence.reason = "the fixture sync reported an error, so the calendar is not evidence"
        return evidence
    if stale or source not in SUFFICIENT_CALENDAR_SOURCES:
        evidence.reason = (f"the calendar was answered from {source or 'nobody'}"
                           f"{' (stale)' if stale else ''}, which says nothing about the window")
        return evidence
    if asked_days is None or asked_days < window_days:
        evidence.reason = (f"the fixture sync covered {asked_days} day(s), less than the "
                           f"{window_days}-day window")
        return evidence
    try:
        fixtures = count()
    except Exception as exc:  # the database is the last word; an unreadable one is not evidence
        logger.debug("Could not count %s fixtures in the window: %s", key, exc)
        fixtures = None
    if not isinstance(fixtures, int) or isinstance(fixtures, bool):
        evidence.reason = "the fixtures inside the window could not be counted"
        return evidence
    evidence.fixtures_in_window = fixtures
    if fixtures > 0:
        evidence.reason = f"{fixtures} fixture(s) still to be played inside the {window_days}-day window"
        return evidence
    evidence.dormant = True
    evidence.reason = (f"the calendar answered from the {source} with no error for the whole "
                       f"{window_days}-day window and the database holds no fixture in it")
    return evidence


# ------------------------------------------------------------------------- the plan of a pass
@dataclass
class RefreshPlan:
    """What a pass walks, in order, and why each competition it does not walk is left out."""

    policy: str
    fetch: List[str] = field(default_factory=list)
    recheck: List[str] = field(default_factory=list)
    ineligible: Dict[str, str] = field(default_factory=dict)
    deferred_first: List[str] = field(default_factory=list)
    publication_hour: Optional[int] = None
    hour_reached: Optional[bool] = None

    @property
    def order(self) -> List[str]:
        return list(self.fetch) + list(self.recheck)

    def to_dict(self) -> Dict[str, Any]:
        return {"policy": self.policy, "fetch": list(self.fetch), "recheck": list(self.recheck),
                "ineligible": dict(self.ineligible), "deferred_first": list(self.deferred_first),
                "publication_hour": self.publication_hour, "hour_reached": self.hour_reached}


class RefreshPolicy:
    """Eligibility, order and the per-day state of forecast refreshes for one provider."""

    def __init__(self, name: str, cache, provider: str, now, *, default_hour: int = 12,
                 interval_hours: int = 22, observation_days: int = OBSERVATION_DAYS):
        if name not in POLICIES:
            raise ValueError(f"unknown forecast refresh policy {name!r}; one of {', '.join(POLICIES)}")
        self.name = name
        self.cache = cache
        self.provider = provider
        self._now = now
        self.default_hour = max(int(default_hour or 0), 0)
        self.interval_hours = int(interval_hours)
        self.observation_days = max(int(observation_days), 1)

    @classmethod
    def from_settings(cls, cache, provider: str, now) -> "RefreshPolicy":
        from app.core.config import settings
        return cls(settings.GAMEFORECAST_REFRESH_POLICY, cache, provider, now,
                   default_hour=int(settings.SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR or 0),
                   interval_hours=int(settings.GAMEFORECAST_SYNC_INTERVAL_HOURS))

    @property
    def now(self) -> datetime:
        value = self._now() if callable(self._now) else self._now
        return _aware(value if isinstance(value, datetime) else datetime.now(timezone.utc)).astimezone(timezone.utc)

    @property
    def daily(self) -> bool:
        return self.name == POLICY_DAILY_SLOT

    @property
    def stops_when_unaffordable(self) -> bool:
        """The earlier rule stops the pass at the first turn it cannot pay for; the slot rule
        defers that competition and moves on to the next affordable one."""
        return self.name == POLICY_ELAPSED_INTERVAL

    # ------------------------------------------------------------------ the slot
    def _refresh_key(self, key: str) -> str:
        return REFRESH_KEY.format(provider=self.provider, key=key)

    def slot(self, key: str) -> Dict[str, Any]:
        stored = self.cache.get(self._refresh_key(key))
        return dict(stored) if isinstance(stored, dict) else {}

    def _save_slot(self, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        self.cache.set(self._refresh_key(key), record, ttl=REFRESH_TTL_SECONDS, stale_ttl=REFRESH_TTL_SECONDS)
        return record

    @staticmethod
    def fetch_outcome(fetched_at: datetime, model_run_at: Optional[datetime], forecasts: int) -> str:
        """What a fetch bought: a same-day run, an older one, or nothing.

        A run dated the fetch's own UTC date (or later, for a provider whose clock is ahead) is
        the day's run. Forecasts that carry no run date cannot be told apart from a same-day run
        and are treated as one: re-checking a provider that never dates its runs would spend a
        request a day on a question it cannot answer.
        """
        if forecasts <= 0:
            return OUTCOME_EMPTY
        if model_run_at is None or _aware(model_run_at).date() >= _aware(fetched_at).date():
            return OUTCOME_SAME_DAY_RUN
        return OUTCOME_OLDER_RUN

    def record_fetch(self, key: str, *, fetched_at: datetime, model_run_at: Optional[datetime],
                     forecasts: int, recheck: bool = False) -> Dict[str, Any]:
        """A turn called the provider for `key`: take the day's slot and learn from the run date."""
        fetched_at = _aware(fetched_at).astimezone(timezone.utc)
        outcome = self.fetch_outcome(fetched_at, model_run_at, forecasts)
        record: Dict[str, Any] = {"day": fetched_at.date().isoformat(), "fetched_at": fetched_at.isoformat(),
                                  "model_run_at": _iso(model_run_at), "outcome": outcome,
                                  "forecasts": int(forecasts)}
        if recheck:
            previous = self.slot(key)
            record["first_fetched_at"] = previous.get("fetched_at")
            record["first_outcome"] = previous.get("outcome")
            record["recheck"] = {"at": fetched_at.isoformat(), "outcome": outcome}
        self._save_slot(key, record)
        self._observe(fetched_at, model_run_at, forecasts)
        return record

    def record_dormant(self, key: str, evidence: Optional[CalendarEvidence] = None) -> Dict[str, Any]:
        now = self.now
        return self._save_slot(key, {"day": now.date().isoformat(), "recorded_at": now.isoformat(),
                                     "fetched_at": None, "model_run_at": None, "outcome": OUTCOME_DORMANT,
                                     "reason": evidence.reason if evidence else "no fixture in window"})

    def record_deferred(self, key: str, reason: str) -> Dict[str, Any]:
        now = self.now
        return self._save_slot(key, {"day": now.date().isoformat(), "recorded_at": now.isoformat(),
                                     "fetched_at": None, "model_run_at": None, "outcome": OUTCOME_DEFERRED,
                                     "reason": str(reason)[:300]})

    def record_failed(self, key: str, reason: str) -> Dict[str, Any]:
        now = self.now
        return self._save_slot(key, {"day": now.date().isoformat(), "recorded_at": now.isoformat(),
                                     "fetched_at": None, "model_run_at": None, "outcome": OUTCOME_FAILED,
                                     "reason": str(reason)[:300]})

    # ------------------------------------------------------------------ the publication hour
    def _publication_key(self) -> str:
        return PUBLICATION_KEY.format(provider=self.provider)

    def publication_evidence(self) -> Dict[str, Any]:
        stored = self.cache.get(self._publication_key())
        record = dict(stored) if isinstance(stored, dict) else {}
        record["observed"] = dict(record.get("observed") or {})
        record["not_yet"] = dict(record.get("not_yet") or {})
        return record

    def _observe(self, fetched_at: datetime, model_run_at: Optional[datetime], forecasts: int) -> None:
        """Learn from one fetch's run date. A fetch with nothing dated in it teaches nothing."""
        if forecasts <= 0 or model_run_at is None:
            return
        day = fetched_at.date().isoformat()
        record = self.publication_evidence()
        if _aware(model_run_at).date() >= fetched_at.date():
            record["observed"][day] = min(int(record["observed"].get(day, 24)), fetched_at.hour)
        else:
            # Still the previous run at this hour: evidence that H was too early on D, and nothing
            # more. It is kept for a reader and never moves the hour.
            record["not_yet"][day] = max(int(record["not_yet"].get(day, -1)), fetched_at.hour)
        cutoff = (fetched_at.date() - timedelta(days=self.observation_days)).isoformat()
        for name in ("observed", "not_yet"):
            record[name] = {d: h for d, h in record[name].items() if d >= cutoff}
        record["updated_at"] = self.now.isoformat()
        self.cache.set(self._publication_key(), record, ttl=PUBLICATION_TTL_SECONDS, stale_ttl=PUBLICATION_TTL_SECONDS)

    def publication_hour(self) -> int:
        """The UTC hour before which no automatic fetch is made: the earliest of the baseline
        and every same-day-run observation of the last `observation_days` days."""
        cutoff = (self.now.date() - timedelta(days=self.observation_days)).isoformat()
        hours = [int(h) for d, h in self.publication_evidence()["observed"].items()
                 if d >= cutoff and isinstance(h, int)]
        return min([self.default_hour] + hours)

    # ------------------------------------------------------------------ eligibility and order
    def plan(self, keys: Sequence[str], *, kickoff_of: Callable[[str], Optional[datetime]],
             last_sync_of: Callable[[str], Optional[datetime]], force: bool = False) -> RefreshPlan:
        """Which competitions a pass walks now, in order, and why the others are left out.

        `force` bypasses eligibility - every competition is walked - and nothing else: the
        budget, dormancy and the order still apply. `kickoff_of` and `last_sync_of` are the two
        facts the order is read from; either may answer None for "unknown".
        """
        keys = list(keys)
        if self.name == POLICY_ELAPSED_INTERVAL:
            return self._plan_elapsed(keys, last_sync_of, force)
        return self._plan_daily(keys, kickoff_of, force)

    def _plan_elapsed(self, keys: List[str], last_sync_of, force: bool) -> RefreshPlan:
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        order = sorted(keys, key=lambda key: (last_sync_of(key) or epoch, keys.index(key)))
        plan = RefreshPlan(policy=self.name)
        interval = timedelta(hours=self.interval_hours)
        now = self.now
        for key in order:
            last = last_sync_of(key)
            if not force and last and now - _aware(last) < interval:
                hours = int((now - _aware(last)).total_seconds() // 3600)
                plan.ineligible[key] = f"synced {hours} h ago, inside the {self.interval_hours} h interval"
                continue
            plan.fetch.append(key)
        return plan

    def _plan_daily(self, keys: List[str], kickoff_of, force: bool) -> RefreshPlan:
        now = self.now
        today = now.date().isoformat()
        hour = self.publication_hour()
        plan = RefreshPlan(policy=self.name, publication_hour=hour, hour_reached=now.hour >= hour)
        for key in keys:
            if force:
                plan.fetch.append(key)
                continue
            if not plan.hour_reached:
                plan.ineligible[key] = (f"before the observed publication hour ({hour:02d}:00 UTC); "
                                        f"a fetch now would buy the previous day's run")
                continue
            slot = self.slot(key)
            outcome = slot.get("outcome")
            if slot.get("day") != today or outcome in (OUTCOME_DEFERRED, OUTCOME_FAILED):
                plan.fetch.append(key)
                if outcome == OUTCOME_DEFERRED:
                    plan.deferred_first.append(key)
                continue
            if outcome == OUTCOME_OLDER_RUN and not slot.get("recheck"):
                plan.recheck.append(key)
                continue
            when = slot.get("fetched_at") or slot.get("recorded_at")
            plan.ineligible[key] = f"{outcome} for {today} at {when}; one slot per UTC day"
        far = datetime.max.replace(tzinfo=timezone.utc)

        def kickoff(key: str) -> datetime:
            value = kickoff_of(key)
            return _aware(value) if isinstance(value, datetime) else far

        plan.fetch.sort(key=lambda key: (0 if key in plan.deferred_first else 1, kickoff(key), keys.index(key)))
        plan.recheck.sort(key=lambda key: (kickoff(key), keys.index(key)))
        return plan

    # ------------------------------------------------------------------ calendar evidence
    def _calendar_key(self, key: str) -> str:
        return CALENDAR_EVIDENCE_KEY.format(provider=self.provider, key=key)

    def record_calendar(self, evidence: CalendarEvidence) -> None:
        self.cache.set(self._calendar_key(evidence.key), evidence.to_dict(),
                       ttl=CALENDAR_EVIDENCE_TTL_SECONDS, stale_ttl=CALENDAR_EVIDENCE_TTL_SECONDS)

    def calendar_evidence(self, key: str) -> Optional[CalendarEvidence]:
        return CalendarEvidence.from_dict(self.cache.get(self._calendar_key(key)))

    def calendar_still_dormant(self, key: str, *, window_days: int, valid_for_seconds: int,
                               count: Callable[[], Optional[int]]) -> Tuple[bool, str]:
        """Would a turn taken now find `key` dormant, judged from the LAST RECORDED evidence?

        For the dry run, which must not run a fixture sync. What it assumes: a fixture sync made
        now would get the same calendar answer the recorded turn got, which holds while that
        answer is still inside the fixture cache's own life (`valid_for_seconds` - the caller
        passes the TTL `sync_upcoming` caches under) and was asked for the same window; and the
        database is re-counted now rather than trusted from the record. Outside those bounds the
        answer is "active", which prices the turn in full: an estimate that cannot know rounds up.
        """
        evidence = self.calendar_evidence(key)
        if evidence is None:
            return False, "no calendar evidence recorded for this key"
        if not evidence.dormant:
            return False, evidence.reason
        if evidence.window_days != window_days:
            return False, (f"the recorded evidence is about a {evidence.window_days}-day window, "
                           f"not the {window_days}-day one")
        checked_at = _parse(evidence.checked_at)
        if checked_at is None or self.now - checked_at > timedelta(seconds=max(int(valid_for_seconds), 0)):
            return False, "the recorded calendar answer is older than the fixture cache keeps it"
        try:
            fixtures = count()
        except Exception as exc:
            logger.debug("Could not re-count %s fixtures for the estimate: %s", key, exc)
            fixtures = None
        if not isinstance(fixtures, int) or isinstance(fixtures, bool):
            return False, "the fixtures inside the window could not be counted"
        if fixtures > 0:
            return False, f"{fixtures} fixture(s) have appeared inside the window since"
        return True, (f"calendar evidence recorded at {evidence.checked_at} found nothing to forecast, "
                      f"and the database still holds no fixture in the window")

    # ------------------------------------------------------------------ reporting
    def describe(self) -> Dict[str, Any]:
        evidence = self.publication_evidence()
        return {"name": self.name,
                "publication_hour_utc": self.publication_hour() if self.daily else None,
                "publication_hour_baseline_utc": self.default_hour,
                "publication_observed": evidence.get("observed", {}),
                "publication_not_yet": evidence.get("not_yet", {}),
                "interval_hours": self.interval_hours if not self.daily else None}
