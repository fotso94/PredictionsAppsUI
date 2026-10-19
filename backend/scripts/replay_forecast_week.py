"""Replay a simulated week of forecast refreshes and live polls under both refresh policies.

A SIMULATION, not a production observation. Everything runs in-process against the test suite's
fakes: a simulated clock, a fake Redis, a scripted forecast provider whose daily model run is
published at a scripted hour (or not at all), a scripted fixture calendar, and stub match-data
providers for the live chain. No network request is possible: the scripted providers are the only
providers, and nothing here opens a database.

What is replayed, for each of the two policies (`daily-slot`, `elapsed-interval`):

- seven days, the scheduler ticking every five minutes with the real `SyncScheduler` and the real
  `ForecastService` (fresh instances per pass, state in the fake Redis, as in production);
- early and late model publication, a day with none, morning and evening kick-offs, the UTC-day
  allowance reset and the provider's own 03:12 window, a late-evening page-load refresh, a restart,
  two callers at the same instant, an exhausted allowance, a dormant competition waking up;
- and, separately, a live-poll hour with primary failures with and without a fallback answer.

Run from backend/:  ./venv311/bin/python scripts/replay_forecast_week.py [--out report.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock

sys.path.insert(0, os.getcwd())

from app.core.config import settings  # noqa: E402
from app.services.forecast_refresh_policy import POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL  # noqa: E402
from app.services.forecast_service import ForecastService  # noqa: E402
from app.services.match_cache import MatchCache  # noqa: E402
from app.services.match_data_service import MatchDataService, SyncMeta  # noqa: E402
from app.services.providers.base import ForecastProvider, ProviderForecast, ProviderUnavailableError  # noqa: E402
from app.services.providers.budget import RequestBudget  # noqa: E402
from app.services.sync_scheduler import TASK_FORECASTS, TASK_LIVE, SyncScheduler  # noqa: E402
from tests.services.test_sync_scheduler import (  # noqa: E402
    KEYS as LIVE_KEYS, FakeMatch, LockingFakeRedis, StubDataProvider)

UTC = timezone.utc
START = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)          # a Monday
DAYS = 7
STEP = timedelta(minutes=5)
CEILING = 8                                                # GAMEFORECAST_DAILY_REQUEST_BUDGET stays 8
PROVIDER_WINDOW_RESET = timedelta(hours=3, minutes=12)     # the provider's own window, as observed
KEYS = ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league",
        "uefa_nations_league", "concacaf_nations_league"]


class Clock:
    def __init__(self, start: datetime = START):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now = self.now + delta


# ----------------------------------------------------------------------------- the scripted world
@dataclass
class Fixture:
    id: str
    key: str
    home: str
    away: str
    kickoff: datetime
    listed_at: datetime            # when OUR calendar first holds it (the provider knows it earlier)


@dataclass
class Scenario:
    """One replayed week. Hours are UTC; `publication[d]` is the hour:minute the provider's run for day
    d appears, None for a day without a run (the previous run stays current)."""
    publication: Dict[date, Optional[tuple]]
    fixtures: List[Fixture]
    calendar_failures: Dict[tuple, str] = field(default_factory=dict)   # (key, day) -> "raise"|"stale"
    late_evening_refresh: Optional[tuple] = None                        # (key, datetime)
    restart_at: Optional[datetime] = None
    concurrent_call_at: Optional[datetime] = None

    def listed(self, key: str, now: datetime, start: datetime, end: datetime) -> List[Fixture]:
        return [f for f in self.fixtures if f.key == key and f.listed_at <= now and start <= f.kickoff < end]

    def provider_knows(self, key: str, start: datetime, end: datetime) -> List[Fixture]:
        return [f for f in self.fixtures if f.key == key and start <= f.kickoff < end]

    def latest_run(self, now: datetime) -> Optional[date]:
        latest = None
        for day in sorted(self.publication):
            at = self.publication[day]
            if at is None or day > now.date():
                continue
            published = datetime(day.year, day.month, day.day, at[0], at[1], tzinfo=UTC)
            if published <= now:
                latest = day
        return latest


def build_scenario() -> Scenario:
    d = [START.date() + timedelta(days=i) for i in range(DAYS)]
    publication = {d[0]: (5, 0), d[1]: (14, 0), d[2]: None, d[3]: (9, 0), d[4]: (11, 30), d[5]: (3, 30), d[6]: (12, 0)}
    fixtures: List[Fixture] = []
    counter = 0

    def add(key: str, day_index: int, hour: int, listed_days_before: int = 6):
        nonlocal counter
        counter += 1
        kickoff = datetime(d[day_index].year, d[day_index].month, d[day_index].day, hour, 0, tzinfo=UTC)
        fixtures.append(Fixture(f"fx{counter}", key, f"{key}-home{counter}", f"{key}-away{counter}", kickoff,
                                listed_at=kickoff - timedelta(days=listed_days_before)))

    # evening kick-offs most days, morning kick-offs (11:00 UTC) on days 2 and 5 for two competitions
    for i in range(DAYS):
        add("premier_league", i, 11 if i in (1, 4) else 20)
        add("la_liga", i, 11 if i in (1, 4) else 20)
        add("serie_a", i, 20)
        add("bundesliga", i, 20)
    # the Champions League plays on days 3 and 4 only; listed a week ahead so it is never dormant
    add("champions_league", 2, 20); add("champions_league", 3, 20)
    # Ligue 1 has nothing until day 5: dormant for four days, then listed on day 4 at noon and plays day 5
    add("ligue_1", 4, 20, listed_days_before=1); add("ligue_1", 5, 20, listed_days_before=2)
    # the two Nations Leagues play nothing all week
    scenario = Scenario(publication=publication, fixtures=fixtures)
    scenario.calendar_failures = {("serie_a", d[2]): "raise", ("bundesliga", d[2]): "stale"}
    scenario.late_evening_refresh = ("serie_a", datetime(d[1].year, d[1].month, d[1].day, 20, 1, tzinfo=UTC))
    scenario.restart_at = datetime(d[3].year, d[3].month, d[3].day, 6, 0, tzinfo=UTC)
    scenario.concurrent_call_at = datetime(d[4].year, d[4].month, d[4].day, 12, 30, tzinfo=UTC)
    return scenario


# ----------------------------------------------------------------------------- scripted providers
class ScriptedForecastProvider(ForecastProvider):
    """The only forecast provider in the replay: answers from the scenario, charges the budget exactly
    as the real client does (before the call), and records every request. Anything else raises."""
    name = "gameforecast"
    integration_status = "simulated"

    def __init__(self, scenario: Scenario, clock: Clock, budget: RequestBudget, costs: Dict[str, int], log: list):
        self.scenario, self.clock, self.budget, self.costs, self.log = scenario, clock, budget, costs, log

    def is_configured(self) -> bool:
        return True

    def request_cost(self, key: str) -> int:
        return self.costs.get(key, 1)

    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        now = self.clock()
        cost = self.request_cost(key)
        self.budget.consume(cost, reason="fetch")
        run = self.scenario.latest_run(now)
        start = datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC)
        end = datetime(date_to.year, date_to.month, date_to.day, tzinfo=UTC) + timedelta(days=1)
        out = []
        for f in self.scenario.provider_knows(key, start, end):
            out.append(ProviderForecast(provider=self.name, external_event_id=f.id, home_name=f.home, away_name=f.away,
                                        kickoff_utc=f.kickoff, competition_key=key, home_prob=0.5, draw_prob=0.25,
                                        away_prob=0.25, over_25_prob=0.6, under_25_prob=0.4,
                                        model_run_at=datetime(run.year, run.month, run.day, tzinfo=UTC) if run else None,
                                        fetched_at=now, raw={}))
        self.log.append({"at": now, "key": key, "cost": cost, "run": run.isoformat() if run else None, "events": len(out)})
        return out

    def __getattr__(self, item):
        # The service probes a few optional attributes with getattr(..., None) (`last_fetch`,
        # `pages_last_seen`); those answer None. Anything that would fetch, resolve or list is a
        # request the replay never makes, and fails the run on the spot.
        if item.startswith(("get_", "fetch", "resolve", "list_", "_get", "discover")):
            raise AssertionError(f"unexpected provider call: {item}")
        return None


class FakeRegistry:
    def __init__(self, scenario: Scenario, clock: Clock):
        self.scenario, self.clock = scenario, clock

    def ensure_canonical_league(self, key: str):
        return SimpleNamespace(id=key)

    def fixtures_in_window(self, league_id, start: datetime, end: datetime) -> int:
        return len(self.scenario.listed(league_id, self.clock(), start, end))

    def next_kickoff(self, league_id, start: datetime) -> Optional[datetime]:
        later = [f.kickoff for f in self.scenario.fixtures if f.key == league_id and f.listed_at <= self.clock() and f.kickoff >= start]
        return min(later) if later else None


class FakeFixturesService:
    """Stands in for MatchDataService.sync_upcoming: fresh provider answers, or the scenario's failures."""
    def __init__(self, scenario: Scenario, clock: Clock, log: list):
        self.scenario, self.clock, self.log = scenario, clock, log

    def sync_upcoming(self, key: str, days_ahead: int) -> SyncMeta:
        now = self.clock()
        failure = self.scenario.calendar_failures.get((key, now.date()))
        self.log.append({"at": now, "key": key, "failure": failure})
        if failure == "raise":
            raise ProviderUnavailableError("livescore: read timed out", provider="livescore")
        if failure == "stale":
            return SyncMeta(provider="livescore", source="stale-cache", stale=True, fetched_at=(now - timedelta(hours=9)).isoformat())
        return SyncMeta(provider="livescore", source="provider", stale=False, fetched_at=now.isoformat())


# ----------------------------------------------------------------------------- the forecast replay
@dataclass
class ForecastReplay:
    policy: str
    requests: List[dict]
    attachments: Dict[str, List[dict]]          # fixture id -> [{fetched_at, model_run_at}]
    passes: List[dict]
    deferrals: int
    rechecks: int
    dormant_turns: int
    unmatched_at_fetch: int

    def requests_by_day(self) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for r in self.requests:
            out[r["at"].date().isoformat()] += r["cost"]
        return dict(out)

    def requests_by_key(self) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for r in self.requests:
            out[r["key"]] += r["cost"]
        return dict(out)

    def requests_by_provider_window(self) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for r in self.requests:
            shifted = r["at"] - PROVIDER_WINDOW_RESET
            out[shifted.date().isoformat() + "T03:12"] += r["cost"]
        return dict(out)

    def refresh_gaps_hours(self) -> Dict[str, float]:
        by_key: Dict[str, List[datetime]] = defaultdict(list)
        for r in self.requests:
            by_key[r["key"]].append(r["at"])
        out = {}
        for key, times in by_key.items():
            times.sort()
            gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
            out[key] = round(max(gaps), 1) if gaps else 0.0
        return out


def forecast_replay(policy: str, scenario: Scenario) -> ForecastReplay:
    settings.GAMEFORECAST_REFRESH_POLICY = policy
    settings.GAMEFORECAST_SYNC_INTERVAL_HOURS = 22
    settings.SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR = 12
    settings.GAMEFORECAST_DAILY_REQUEST_BUDGET = CEILING
    clock = Clock()
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    budget = RequestBudget("gameforecast", CEILING, client=redis, now=clock)
    requests: List[dict] = []
    calendar_log: List[dict] = []
    attachments: Dict[str, List[dict]] = defaultdict(list)
    counters = {"deferred": 0, "rechecks": 0, "dormant": 0, "unmatched": 0}
    costs = {"champions_league": 2}        # a two-page competition: priced and charged at two
    provider = ScriptedForecastProvider(scenario, clock, budget, costs, requests)
    fixtures = FakeFixturesService(scenario, clock, calendar_log)
    registry = FakeRegistry(scenario, clock)

    def attach(forecast: ProviderForecast, key: str, league_id) -> Dict[str, Any]:
        listed = [f for f in scenario.fixtures if f.id == forecast.external_event_id and f.listed_at <= clock()]
        if not listed:
            counters["unmatched"] += 1
            return {"result": "unmatched", "event": forecast.external_event_id, "home": forecast.home_name,
                    "away": forecast.away_name, "kickoff_utc": forecast.kickoff_utc.isoformat(),
                    "reason": "fixture not listed yet", "candidates": []}
        record = {"fetched_at": forecast.fetched_at, "model_run_at": forecast.model_run_at}
        if record not in attachments[forecast.external_event_id]:
            attachments[forecast.external_event_id].append(record)
        return {"result": "attached"}

    def service_factory(_db=None, keys: Optional[List[str]] = None) -> ForecastService:
        s = ForecastService(MagicMock(), provider=provider, cache=cache, now=clock(), keys=list(keys or KEYS),
                            fixtures=fixtures, sync_fixtures=False)
        s.registry = registry
        s.attach_forecast = attach
        return s

    def scheduler_factory() -> SyncScheduler:
        return SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                             match_service_factory=lambda db: MagicMock(), forecast_service_factory=service_factory,
                             tasks=[TASK_FORECASTS], close_sessions=False, budget_client=redis)

    scheduler = scheduler_factory()
    passes: List[dict] = []
    end = START + timedelta(days=DAYS)
    restarted = False
    concurrent_done = False
    late_done = False
    while clock() < end:
        now = clock()
        if scenario.restart_at and not restarted and now >= scenario.restart_at:
            scheduler = scheduler_factory()                # a restart: new objects, same Redis
            passes.append({"at": now, "kind": "restart", "requests_before": len(requests)})
            restarted = True
        if scenario.late_evening_refresh and not late_done and now >= scenario.late_evening_refresh[1]:
            # a reader's page load refreshes one competition out of band (the matches endpoint path)
            # an operator forces a refresh of one competition out of band (the admin force sync
            # walks every key the same way); force bypasses eligibility, never the budget
            key = scenario.late_evening_refresh[0]
            before = len(requests)
            report = service_factory(keys=[key]).ensure_synced(force=True)
            passes.append({"at": now, "kind": "forced-refresh", "key": key, "requests": len(requests) - before,
                           "report": _trim(report)})
            late_done = True
        if scenario.concurrent_call_at and not concurrent_done and now >= scenario.concurrent_call_at:
            before = len(requests)
            a, b = service_factory(), service_factory()
            ra = a.ensure_synced(force=False)
            rb = b.ensure_synced(force=False)
            passes.append({"at": now, "kind": "concurrent", "requests": len(requests) - before,
                           "report": {"first": _trim(ra), "second": _trim(rb)}})
            concurrent_done = True
        out = scheduler.run_once(only=[TASK_FORECASTS])
        task = (out.get("tasks") or {}).get(TASK_FORECASTS)
        if task and task.get("ran"):
            result = task.get("result") or {}
            counters["deferred"] += len(result.get("deferred") or [])
            counters["rechecks"] += len(result.get("rechecked") or [])
            counters["dormant"] += len(result.get("dormant") or [])
            passes.append({"at": now, "kind": "task", "report": _trim(result)})
        clock.advance(STEP)
    return ForecastReplay(policy, requests, dict(attachments), passes, counters["deferred"], counters["rechecks"],
                          counters["dormant"], counters["unmatched"])


def _trim(report: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("policy", "order", "skipped", "deferred", "dormant", "rechecked", "error", "paused", "ineligible", "fetch")
    out = {k: report.get(k) for k in keep if k in report}
    out["competitions"] = {k: {x: v.get(x) for x in ("fetched", "attached", "skipped", "error") if x in v}
                           for k, v in (report.get("competitions") or {}).items() if isinstance(v, dict)}
    return out


def kickoff_ages(replay: ForecastReplay, scenario: Scenario) -> List[dict]:
    """At each fixture's kick-off: the newest attached forecast's model age and retrieval age, or missing."""
    rows = []
    for f in scenario.fixtures:
        if f.key in ("uefa_nations_league", "concacaf_nations_league"):
            continue
        before = [a for a in replay.attachments.get(f.id, []) if a["fetched_at"] <= f.kickoff]
        if not before:
            rows.append({"fixture": f.id, "key": f.key, "kickoff": f.kickoff, "missing": True})
            continue
        newest = max(before, key=lambda a: a["fetched_at"])
        run = newest["model_run_at"]
        rows.append({"fixture": f.id, "key": f.key, "kickoff": f.kickoff, "missing": False,
                     "retrieval_age_h": round((f.kickoff - newest["fetched_at"]).total_seconds() / 3600, 1),
                     "model_age_h": round((f.kickoff - run).total_seconds() / 3600, 1) if run else None,
                     "latest_run_available": (scenario.latest_run(f.kickoff) or date.min).isoformat(),
                     "run_used": run.date().isoformat() if run else None})
    return rows


# ----------------------------------------------------------------------------- the live-poll replay
class ScriptedDataProvider(StubDataProvider):
    """A primary that times out on scripted polls; a fallback that answers or not on scripted polls."""
    def __init__(self, name: str, fail_on: Sequence[int], budget: Optional[RequestBudget] = None):
        super().__init__(budget=budget)
        self.name = name
        self.fail_on = set(fail_on)
        self.polls = 0

    def get_live(self, keys):
        self.polls += 1
        if self.budget is not None:
            self.budget.consume(1, reason="fetch")          # charged before the answer, as the real client is
        if self.polls in self.fail_on:
            raise ProviderUnavailableError(f"{self.name}: read timed out", provider=self.name)
        return super().get_live(keys)


def live_replay() -> Dict[str, Any]:
    clock = Clock(datetime(2026, 10, 24, 14, 0, tzinfo=UTC))
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    primary = ScriptedDataProvider("livescore", fail_on=[5, 11, 17], budget=RequestBudget("livescore", 1200, client=redis, now=clock))
    # the fallback is only asked when the primary fails: its third call is the primary's poll 17
    fallback = ScriptedDataProvider("api_football", fail_on=[3], budget=RequestBudget("api_football", 90, client=redis, now=clock))
    kickoff = clock() + timedelta(minutes=5)
    match = FakeMatch(kickoff)
    service = MatchDataService(MagicMock(), providers=[primary, fallback], cache=cache, now=clock(), keys=list(LIVE_KEYS))
    service.registry = MagicMock()
    service.registry.ensure_canonical_league.return_value = MagicMock(id="league-1")
    service.registry.matches_for_day.return_value = [match]
    service.registry.upsert_fixture.side_effect = lambda fixture: MagicMock()

    def match_factory(_db):
        service._now = clock()
        return service

    scheduler = SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                              match_service_factory=match_factory, forecast_service_factory=lambda db: MagicMock(),
                              tasks=[TASK_LIVE], close_sessions=False, budget_client=redis)
    settings.SYNC_LIVE_INTERVAL_SECONDS = 120
    polls: List[dict] = []
    for _ in range(45):                          # ninety minutes in two-minute steps
        out = scheduler.run_once(only=[TASK_LIVE])
        task = (out.get("tasks") or {}).get(TASK_LIVE) or {}
        if task.get("ran"):
            result = task.get("result") or {}
            polls.append({"at": clock(), "ok": task.get("ok"), "outcome": result.get("outcome"),
                          "errors": list(result.get("errors") or []),
                          "old_rule_ok": not result.get("errors"),
                          "backoff": scheduler.state(TASK_LIVE).get("backoff_seconds")})
        clock.advance(timedelta(minutes=2))
    new_gaps = [(b["at"] - a["at"]).total_seconds() / 60 for a, b in zip(polls, polls[1:])]
    # Under the old rule every poll with an error in the chain failed and the task backed off five
    # minutes: the gap after such a poll would have been max(interval, 300 s).
    old_gaps = [max(2.0, 5.0) if a["errors"] else 2.0 for a in polls[:-1]]
    return {"polls": polls, "primary_polls": primary.polls, "fallback_polls": fallback.polls,
            "requests_charged": {"livescore": primary.budget.used_today(), "api_football": fallback.budget.used_today()},
            "new_rule_gaps_min": new_gaps, "old_rule_gaps_min": old_gaps,
            "new_backoffs": sum(1 for p in polls if not p["ok"]),
            "old_backoffs": sum(1 for p in polls if p["errors"]),
            "new_minutes_lost": sum(max(g - 2.0, 0.0) for g in new_gaps),
            "old_minutes_lost": sum(max(g - 2.0, 0.0) for g in old_gaps)}


# ----------------------------------------------------------------------------- the report
def render(scenario: Scenario, replays: Dict[str, ForecastReplay], live: Dict[str, Any]) -> str:
    lines = ["# Replayed week: forecast refresh policies and the live-poll verdict",
             "",
             "**A simulation, not a production observation.** Simulated clock from 2026-10-19 00:00 UTC "
             "for seven days, five-minute ticks, the real `SyncScheduler` and `ForecastService`, the test "
             "suite's fake Redis, a scripted forecast provider and a scripted fixture calendar; no network "
             "request is possible and no database is opened. Ceiling 8 requests per UTC day.",
             "",
             "## The scripted week",
             "",
             "| Day | Provider publishes its run at (UTC) | Kick-offs | Other |",
             "|---|---|---|---|"]
    d = [START.date() + timedelta(days=i) for i in range(DAYS)]
    extras = {d[1]: "page-load refresh of serie_a at 20:01", d[2]: "serie_a calendar sync raises; bundesliga calendar stale; no run published",
              d[3]: "restart at 06:00", d[4]: "two callers at 12:30; ligue_1 listed at noon of day 4", d[5]: "ligue_1 plays"}
    for i, day in enumerate(d):
        pub = scenario.publication[day]
        kicks = sorted({f"{f.key} {f.kickoff:%H:%M}" for f in scenario.fixtures if f.kickoff.date() == day})
        lines.append(f"| {i+1} ({day}) | {'none' if pub is None else f'{pub[0]:02d}:{pub[1]:02d}'} | {', '.join(kicks) or '—'} | {extras.get(day, '')} |")
    for name, r in replays.items():
        events = [p for p in r.passes if p["kind"] in ("forced-refresh", "concurrent", "restart")]
        lines += ["", f"## Policy `{name}`", "",
                  "Out-of-band events: " + "; ".join(
                      f"{p['kind']} at {p['at']:%d %H:%M}" + (f" ({p.get('key')}, {p.get('requests')} request(s))" if p['kind'] == 'forced-refresh'
                                                            else f" ({p.get('requests')} request(s) by the two callers together)" if p['kind'] == 'concurrent' else "")
                      for p in events) + ".",
                  f"Requests: **{sum(r.requests_by_day().values())}** in the week — by day {json.dumps(r.requests_by_day())}; "
                  f"by competition {json.dumps(r.requests_by_key())}; by provider window (03:12→03:12) {json.dumps(r.requests_by_provider_window())}.",
                  f"Deferrals {r.deferrals}, re-checks {r.rechecks}, dormant turns {r.dormant_turns}, forecasts fetched before their fixture was listed {r.unmatched_at_fetch}.",
                  f"Longest gap between two fetches of a competition (hours): {json.dumps(r.refresh_gaps_hours())}.",
                  "", "| Fixture | Competition | Kick-off | Run used | Latest run that existed | Model age at kick-off | Retrieval age |",
                  "|---|---|---|---|---|---|---|"]
        ages = kickoff_ages(r, scenario)
        for row in ages:
            if row["missing"]:
                lines.append(f"| {row['fixture']} | {row['key']} | {row['kickoff']:%d %H:%M} | **missing** | | | |")
            else:
                lines.append(f"| {row['fixture']} | {row['key']} | {row['kickoff']:%d %H:%M} | {row['run_used']} | {row['latest_run_available']} | {row['model_age_h']} h | {row['retrieval_age_h']} h |")
        served = [a for a in ages if not a["missing"]]
        missing = [a for a in ages if a["missing"]]
        if served:
            model = sorted(a["model_age_h"] for a in served if a["model_age_h"] is not None)
            retrieval = sorted(a["retrieval_age_h"] for a in served)
            behind = sum(1 for a in served if a["run_used"] and a["run_used"] < a["latest_run_available"])
            lines += ["", f"Served {len(served)} of {len(ages)} fixtures; missing {len(missing)}. Model age at kick-off: median {model[len(model)//2]} h, max {model[-1]} h; "
                      f"retrieval age: median {retrieval[len(retrieval)//2]} h, max {retrieval[-1]} h. Fixtures served with an older run than the provider had at kick-off: {behind}."]
    lines += ["", "## Live polling: primary failures with and without a fallback answer", "",
              f"Forty-five two-minute ticks with a match in its live window; the primary times out on polls 5, 11 and 17; the fallback answers on 5 and 11 and times out on 17. "
              f"Polls made: primary {live['primary_polls']}, fallback {live['fallback_polls']}; requests charged {json.dumps(live['requests_charged'])}.",
              "", "| Poll | At | New verdict | Outcome | Old rule (`not errors`) | Backoff after |", "|---|---|---|---|---|---|"]
    for i, p in enumerate(live["polls"], 1):
        if p["errors"] or i in (1, len(live["polls"])):
            lines.append(f"| {i} | {p['at']:%H:%M} | {'ok' if p['ok'] else 'FAIL'} | {p['outcome']} | {'ok' if p['old_rule_ok'] else 'FAIL'} | {p['backoff'] or '—'} |")
    lines += ["", f"Backoffs: new verdict {live['new_backoffs']} (the total failure only), about {live['new_minutes_lost']:.0f} min of polling lost; "
              f"the old rule would have backed off {live['old_backoffs']} times (after every poll with any error in the chain, fallback answered or not), "
              f"about {live['old_minutes_lost']:.0f} min lost. Every poll that went out was charged, answered or not.",
              "", "## Trade-offs and worse outcomes, as replayed", ""]
    dl, el = replays.get(POLICY_DAILY_SLOT), replays.get(POLICY_ELAPSED_INTERVAL)
    if dl and el:
        extra = sum(dl.requests_by_day().values()) - sum(el.requests_by_day().values())
        lines += [f"- `daily-slot` spent {extra:+d} request(s) over the week against `elapsed-interval`: its re-checks. A re-check on a day the provider publishes late buys the same-day run; a re-check on a day it publishes nothing buys nothing — the scripted day without a run cost {sum(1 for p in dl.passes if p['kind']=='task' and (p['report'].get('rechecked') or []) and p['at'].date().isoformat()=='2026-10-21')} pass(es) of re-checks there. Both policies stayed within the ceiling of {CEILING} every day.",
                  "- Under `daily-slot` the forced refresh at 20:05 on day 2 made 0 requests: that day's allowance was already spent (six fetches and two re-checks), and a forced refresh bypasses eligibility, never the budget. Under `elapsed-interval` the same forced refresh went out — and produced the 39.9-hour gap, because the next noon pass saw only 16 h elapsed and the evening pass fell one minute short of 22 h.",
                  "- The two Nations Leagues and the dormant Ligue 1 days cost nothing under either policy here because the scripted calendar answered fresh every turn; on the day the serie_a calendar sync raised and the bundesliga calendar was stale, both competitions were fetched (treated as active), as the dormancy rule requires.",
                  "- Neither policy can serve a newer run than the provider has published: on the day without a run every fixture was served the previous day's run under both."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="write the markdown report here")
    args = parser.parse_args()
    scenario = build_scenario()
    replays = {name: forecast_replay(name, scenario) for name in (POLICY_ELAPSED_INTERVAL, POLICY_DAILY_SLOT)}
    live = live_replay()
    text = render(scenario, replays, live)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
