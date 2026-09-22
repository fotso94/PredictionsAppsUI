"""
One pass of the background data refresh, then exit.

Exactly the same tasks, cadence rules, budget ceiling, backoff and locks as the in-process
scheduler: this script calls `SyncScheduler.run_once()`, it does not reimplement anything. That is
the point of it - a deployment can drive refreshes from cron or a platform scheduler instead of the
in-process loop (set SYNC_SCHEDULER_ENABLED=false and run this on a timer) and the behaviour, the
recorded state and the /data-providers/status output are identical either way.

The task-level Redis lock is shared with the running backend, so running this by hand while the
loop is alive cannot make two passes of the same task overlap.

    cd backend
    ./venv/bin/python scripts/sync_once.py --dry-run          # what it would do and what it would cost
    ./venv/bin/python scripts/sync_once.py                    # run whatever is due
    ./venv/bin/python scripts/sync_once.py --task live        # one task only
    ./venv/bin/python scripts/sync_once.py --task fixtures --force   # ignore the interval

  --dry-run makes no provider request at all. It reads the database and the Redis counters to work
  out an upper bound on what a real pass would spend, which is the number to look at before running
  this against a trial plan.

  --force skips only the "is it due yet" check. The daily budget ceiling and the locks still apply:
  there is deliberately no flag that lets this script spend allowance the budget has refused.

  The two combine: `--dry-run --force` describes the pass `--force` would make, not the unforced
  one. An estimate has one job, which is to be the pass you are about to run.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sync_scheduler import TASK_NAMES, SyncScheduler  # noqa: E402


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run one pass of the data-refresh tasks and exit.")
    parser.add_argument("--task", action="append", choices=list(TASK_NAMES), metavar="TASK",
                        help=f"run only this task (repeatable). One of: {', '.join(TASK_NAMES)}")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would run and what it would cost; call no provider")
    parser.add_argument("--force", action="store_true",
                        help="run even if the task is not due yet (the budget ceiling still applies)")
    parser.add_argument("--json", action="store_true", help="print the raw report as JSON")
    return parser.parse_args(argv)


def _print_estimate(report) -> None:
    print("dry run - no provider was called"
          + (" (--force: the interval is ignored)" if report.get("forced") else ""))
    print()
    for name, entry in report.get("tasks", {}).items():
        verb = "would run" if entry.get("would_run") else "would be skipped"
        print(f"  {name:10} {verb}")
        if not entry.get("due_now"):
            # Under --force the interval is reported and then overridden, in that order. Printing
            # only "not due" beside a task the same report prices and counts is how a dry run ends
            # up describing a pass nobody asked for.
            suffix = ", overridden by --force" if entry.get("forced") else ""
            print(f"{'':13}not due: {entry.get('reason_not_due')}{suffix}")
        if entry.get("blocked"):
            print(f"{'':13}blocked: {entry['blocked']}")
        cost = entry.get("estimated_requests")
        print(f"{'':13}at most {cost if cost is not None else '?'} request(s) to "
              f"{entry.get('provider') or 'the configured provider'}")
        print(f"{'':13}{entry.get('basis')}")
    print()
    print(f"  upper bound for this pass: {report.get('total_requests')} provider request(s)")
    print("  (an upper bound: a cached answer costs nothing)")


def _print_run(report) -> None:
    for name, entry in report.get("tasks", {}).items():
        if not entry.get("ran"):
            print(f"  {name:10} skipped ({entry.get('skipped')}): {entry.get('reason')}")
            continue
        state = "ok" if entry.get("ok") else "FAILED"
        duration = entry.get("duration_ms")
        print(f"  {name:10} ran [{state}]" + (f" in {duration} ms" if duration is not None else ""))
        if entry.get("error"):
            print(f"{'':13}error: {entry['error']}")
            print(f"{'':13}backing off; next due at {entry.get('next_due_at')}")
        else:
            print(f"{'':13}next due at {entry.get('next_due_at')}")
        result = entry.get("result")
        if result is None:
            # A task whose exception reached the scheduler has no summary: the report entry then
            # carries an error and no "result" at all. The error above is everything that is
            # known about the pass, and a summary line read off an empty dict would be a
            # diagnosis of a pass that never got far enough to have one.
            continue
        for line in _summarise(name, result):
            print(f"{'':13}{line}")


def _last_seen(result):
    """When a fixture was last offered, said in a way that does not overclaim.

    Three different things can be true and they must not print the same. A timestamp recorded by a
    pass is exactly that. A timestamp reconstructed from the matches table is evidence a fixture
    arrived, not evidence a pass saw one, and says so. Nothing at all means this pass had no
    recorded sighting to carry forward and none could be reconstructed - which is not the same as
    "never": the stored summary these are carried in is also lost when a pass raises, when its
    state entry expires, and whenever Redis is unavailable.
    """
    at = result.get("last_seen_at")
    if not at:
        return "no sighting recorded and none could be reconstructed"
    if result.get("last_seen_basis") == "matches_table":
        return f"{at} (newest fixture stored ahead of its kickoff; no recorded sighting to carry)"
    return str(at)


def _fixture_pass_lines(result):
    """What the fixtures pass was offered, in words.

    The pass is reported "ok" above whether it was handed a matchday, an empty calendar or a stale
    copy of last night's answer, so this says which of the three happened. Only the forward
    fixtures list is read for that: results and live scores come back through the same counters in
    the same pass, and one unsettled match dated today that has already kicked off - or kicks off
    within the next quarter of an hour - keeps those non-zero on a pass that was offered nothing at
    all to come.

    `forward_answer` is "fixtures" as soon as any ONE day was offered a fixture, so a pass that
    lands there can still have had days that nobody answered. Those are printed beside it rather
    than left in the JSON, because the word alone would read as a clean pass.

    A result holding none of the three is not a fourth outcome to describe: it is a pass that
    never recorded one, and there is nothing here to read.
    """
    lines = []
    answer = result.get("forward_answer")
    if answer is None:
        # The answer and the counters are written together at the end of a pass, so a result
        # without `forward_answer` has no counters either. Falling through to the branches below
        # reads them anyway and prints an absence as a measurement: "unanswered for 0 of None
        # day(s)", which is a confident diagnosis of a pass that produced no data at all.
        return ["no forward-list summary was recorded on this pass"]
    forward_seen = int(result.get("forward_seen") or 0)
    stale_days = int(result.get("days_from_stale_cache") or 0)
    dead_days = int(result.get("days_unanswered") or 0)
    if answer == "fixtures":
        lines.append(f"{forward_seen} forward fixture(s) offered, "
                     f"{result.get('forward_stored')} stored "
                     f"(stored counts rows updated as well as rows created)")
        if stale_days or dead_days:
            lines.append(f"but {stale_days + dead_days} of {result.get('days_requested')} day(s) "
                         f"were not answered ({stale_days} served from the 24-hour stale copy, "
                         f"{dead_days} not answered at all); the streaks reset anyway, because a "
                         f"fixture did arrive on another day")
    elif answer == "empty":
        lines.append(f"no forward fixture offered on any of the {result.get('days_answered')} "
                     f"day(s) the provider answered "
                     f"({result.get('empty_passes')} answered pass(es) in a row with none; "
                     f"last fixture seen: {_last_seen(result)})")
    else:
        lines.append(f"the forward list went unanswered for {stale_days + dead_days} of "
                     f"{result.get('days_requested')} day(s) ({stale_days} served from the "
                     f"24-hour stale copy, {dead_days} not answered at all); "
                     f"{result.get('unanswered_passes')} pass(es) in a row")
        lines.append(f"the empty-calendar streak stays at {result.get('empty_passes')}: this pass "
                     f"was told nothing either way. Last fixture seen: {_last_seen(result)}")
    other = int(result.get("fixtures_seen") or 0) - forward_seen
    if other > 0:
        lines.append(f"{other} further fixture(s) came back on this pass from the results and "
                     f"live ingests; those do not answer the forward question and are not counted "
                     f"towards the streaks above")
    return lines


def _summarise(name, result):
    """A couple of human lines per task; the full report is available with --json."""
    lines = []
    if "days" in result:
        for day, meta in result["days"].items():
            line = (f"{day}: source={meta.get('source')} provider={meta.get('provider')} "
                    f"stale={meta.get('stale')} seen={meta.get('fixtures_seen')} "
                    f"stored={meta.get('fixtures_stored')} ambiguous={meta.get('ambiguous')}")
            if name == "fixtures":
                # `source` belongs to whichever call answered last for this day: the fixtures list
                # runs first, then results, then the live poll. So the forward list's own answer is
                # printed beside it rather than inferred from a field it does not own.
                line += (f" forward={meta.get('forward_fixtures_seen')}/"
                         f"{meta.get('forward_fixtures_stored')} "
                         f"from={meta.get('forward_source') or 'no answer'}")
            lines.append(line)
    if name == "fixtures":
        lines.extend(_fixture_pass_lines(result))
    if name == "live" and not result.get("live_window_open"):
        lines.append(result.get("note", "no live window open"))
    if name == "forecasts":
        synced = [k for k, v in (result.get("competitions") or {}).items()
                  if not (isinstance(v, dict) and v.get("error"))]
        lines.append(f"synced={len(synced)} skipped={len(result.get('skipped') or [])} "
                     f"deferred={len(result.get('deferred') or [])}")
    for error in (result.get("errors") or [])[:5]:
        lines.append(f"error: {error}")
    return lines


def _quiet_sql_echo() -> None:
    """Silence SQLAlchemy's statement log for this process.

    The engine is built with `echo=settings.DEBUG`, which is right for a development server - every
    statement in the log beside the request that issued it - and wrong for a one-shot report: a
    fixtures pass emits hundreds of SQL lines, and the twenty they bury are the only reason to run
    this script. `Engine.echo` is a settable property, so this turns the statement log off here
    and changes nothing about how the server logs. The level is pinned as well as the flag,
    because turning the flag off leaves behind the handler and the INFO level that turning it on
    installed on the engine's own logger.

    Run the backend, or read its log, to see the statements themselves.
    """
    import logging

    from app.db.session import engine

    engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def main(argv=None) -> int:
    args = _parse_args(argv)
    _quiet_sql_echo()
    scheduler = SyncScheduler()
    try:
        report = (scheduler.estimate(only=args.task, force=args.force) if args.dry_run
                  else scheduler.run_once(only=args.task, force=args.force))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    if args.dry_run:
        _print_estimate(report)
        return 0
    print(f"pass started {report.get('started_at')}")
    if not report.get("tasks"):
        print(f"  {report.get('note', 'nothing to do')}")
        return 0
    _print_run(report)
    failed = [n for n, e in report["tasks"].items() if e.get("ran") and not e.get("ok")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
