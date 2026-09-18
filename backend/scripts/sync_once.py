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
    print("dry run - no provider was called")
    print()
    for name, entry in report.get("tasks", {}).items():
        verb = "would run" if entry.get("would_run") else "would be skipped"
        print(f"  {name:10} {verb}")
        if not entry.get("due_now"):
            print(f"{'':13}not due: {entry.get('reason_not_due')}")
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
        print(f"  {name:10} ran [{state}] in {entry.get('duration_ms')} ms")
        if entry.get("error"):
            print(f"{'':13}error: {entry['error']}")
            print(f"{'':13}backing off; next due at {entry.get('next_due_at')}")
        else:
            print(f"{'':13}next due at {entry.get('next_due_at')}")
        result = entry.get("result") or {}
        for line in _summarise(name, result):
            print(f"{'':13}{line}")


def _summarise(name, result):
    """A couple of human lines per task; the full report is available with --json."""
    lines = []
    if "days" in result:
        for day, meta in result["days"].items():
            lines.append(f"{day}: source={meta.get('source')} provider={meta.get('provider')} "
                         f"stale={meta.get('stale')} ambiguous={meta.get('ambiguous')}")
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


def main(argv=None) -> int:
    args = _parse_args(argv)
    scheduler = SyncScheduler()
    try:
        report = (scheduler.estimate(only=args.task) if args.dry_run
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
