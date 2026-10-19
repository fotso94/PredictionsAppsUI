"""The replayed week as a regression test: the properties the policy claims, asserted on the
simulation (a simulation, not a production observation). Runs the same harness as
scripts/replay_forecast_week.py against the suite's fakes; no network, no database."""
import importlib.util
import os
import sys

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "replay_forecast_week.py")


@pytest.fixture(scope="module")
def replay():
    spec = importlib.util.spec_from_file_location("replay_forecast_week", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["replay_forecast_week"] = module
    spec.loader.exec_module(module)
    scenario = module.build_scenario()
    runs = {name: module.forecast_replay(name, scenario) for name in (module.POLICY_ELAPSED_INTERVAL, module.POLICY_DAILY_SLOT)}
    return module, scenario, runs, module.live_replay()


def test_neither_policy_ever_exceeds_the_daily_ceiling(replay):
    module, _, runs, _ = replay
    for name, run in runs.items():
        assert max(run.requests_by_day().values()) <= module.CEILING, name


def test_the_elapsed_interval_rule_misses_a_day_after_a_late_evening_refresh(replay):
    """A competition refreshed at 20:05 is not eligible at the next noon (16 h) and falls short of 22 h
    at the 18:00 pass by five minutes: the reviewer's regression, reproduced."""
    module, _, runs, _ = replay
    gaps = runs[module.POLICY_ELAPSED_INTERVAL].refresh_gaps_hours()
    assert gaps["serie_a"] > 36


def test_the_daily_slot_policy_refreshes_every_active_competition_every_day(replay):
    module, scenario, runs, _ = replay
    gaps = runs[module.POLICY_DAILY_SLOT].refresh_gaps_hours()
    assert all(gap <= 24.5 for gap in gaps.values()), gaps
    ages = module.kickoff_ages(runs[module.POLICY_DAILY_SLOT], scenario)
    assert not any(a["missing"] for a in ages)
    behind = [a for a in ages if not a["missing"] and a["run_used"] < a["latest_run_available"]]
    assert behind == [], "a fixture was served an older run than the provider had at kick-off"


def test_no_automatic_fetch_happens_before_the_observed_publication_hour(replay):
    module, _, runs, _ = replay
    for r in runs[module.POLICY_DAILY_SLOT].requests:
        assert r["at"].hour >= 12, r


def test_a_restart_and_two_concurrent_callers_spend_nothing_extra(replay):
    module, _, runs, _ = replay
    for name, run in runs.items():
        concurrent = [p for p in run.passes if p["kind"] == "concurrent"]
        assert concurrent and concurrent[0]["requests"] == 0, name
        by_day = run.requests_by_day()
        assert by_day["2026-10-22"] <= 6, (name, by_day)      # the restart day: no double fetch


def test_a_fallback_answer_is_a_success_and_a_total_failure_still_backs_off(replay):
    _, _, _, live = replay
    polls = live["polls"]
    assert polls[4]["ok"] and polls[10]["ok"] and polls[4]["errors"] and polls[10]["errors"]
    assert not polls[16]["ok"] and polls[16]["backoff"] == 300
    assert live["new_backoffs"] == 1 and live["old_backoffs"] == 3
    assert live["requests_charged"] == {"livescore": live["primary_polls"], "api_football": live["fallback_polls"]}
