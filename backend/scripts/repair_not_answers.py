#!/usr/bin/env python
"""
Take back the archive observations and fixture attempts a provider that was never asked was
recorded as giving, restore what an earlier record proves, and mark every count it cannot.

WHY THIS EXISTS
    Until 201442e, API-Football and TheSportsDB, which hold an id for none of the national-team
    competitions, skipped those competitions in a results call and returned an empty list for them
    without sending a request, and the call chain recorded that list as their answer. Each such
    not-answer overwrote the competition-day's archive observation with `empty`, 0 rows, its own
    time and its provider's name, added one to `times_asked`, and counted one attempt on every
    pending fixture of that day: `attempts` + 1, `last_attempt_at` (the retry schedule's clock)
    moved, `archive` copied from the false observation, `next_ask_after` pushed back. The code no
    longer does that. What it wrote is still in the store, and a stop the retry budget makes on one
    of these fixtures would quote a count that includes asks never made. This script takes those
    writes back, against any database, after printing exactly what it will do.

WHAT IS FALSE AND HOW IT IS TOLD
    By rule, never by a list of ids. A national-team competition has no API-Football or TheSportsDB
    id (`app/services/providers/competitions.py`, `_national`), so only Live Score can answer it,
    and Live Score's last successful request is recorded in Redis (`provider:status:livescore`,
    `last_success_at`). That instant is THE CUT, and a write pins it: --apply needs it given with
    --livescore-last-success, as the owner approved it in the report, and Redis is then checked
    against it rather than read for it. Redis's value moves on Live Score's first success of any
    kind once access returns, and a cut moved past the not-answers makes them look genuine: the
    plan shrinks without a word. A report without the flag plans with Redis's value and says it is
    not pinned. Then, with a 1 s margin because the observation and the fixture stamps of one pass
    land milliseconds apart:

    * an OBSERVATION is false if it names a provider holding no id for its competition, or it was
      written after that instant;
    * a FIXTURE is affected if its `last_attempt_at` is after that instant, or its `archive`
      carries the stamp of a false observation.

    Nothing records each ask separately, only counters and the last stamp, so what is false is
    counted as the difference between the counter now and the counter AT THE CUT, read from the
    earliest record that shows it: --prior-dump (a plain pg_dump taken before this repair) where its
    stamp is not after the cut, else --prior-capture (the application's own record, captured
    2026-10-05 03:15 UTC, in docs/evidence/livescore-archive-observations.json). Each not-answer
    added one to the observation and one to every pending fixture of its day, so a fixture's false
    attempts are its observation's false increments; where the dump also holds the fixture the
    script checks the two moved together, and leaves a row whose evidence disagrees untouched.

    An observation is one of three classes, and a fixture one of three groups:

    * class 1 -- no entry at the cut: every ask recorded was a not-answer. Group A -- the fixture
      had no attempt before the cut (or its day is class 1): every attempt it carries is false.
    * class 2 -- the entry at the cut is a Live Score answer. Group B -- the fixture's state at the
      cut is in the dump and its day is class 2.
    * class 3 -- the entry at the cut was itself written by a not-answer (2026-10-02 08:12 and
      08:43 UTC). Group C -- its day is class 3. What Live Score last answered for that day is
      dated by `last_answered_at`, which a not-answer never writes; HOW MANY rows it returned is in
      no record, and can be read only from the match rows that answer synced
      (`match_metadata.last_synced_at` within 3 s before the stamp). That method is checked on every
      genuine answered observation first, and refused unless all of them agree.

WHAT --apply DOES
    In one transaction, after locking every target row and checking it still equals what was
    planned (a row changed since is a reason to stop, not to overwrite):

    * class 1: the date's entry is removed, so it reads `unknown`, which is true; any key a
      not-answer does not write (a recorded failure) is kept.
    * class 2: the entry is restored from the record at the cut, keys that record lacks are kept,
      and `count_quality` is "unverified": not-answers before 2026-10-02 are possible and nothing
      records them.
    * class 3: with --reconstruct-from-synced-rows, the entry becomes Live Score's last real answer
      (`answered`, the synced row count, `asked_at` = `last_answered_at`), with `reconstructed`
      true; without it, the not-answer's state, rows, stamp and provider stay. Either way
      `times_asked` is the count at the cut, less the one not-answer the capture proves
      (--subtract-proven-pre-window, the default), and `count_quality` is "upper_bound".
    * group A: `attempts`, `first_attempt_at`, `last_attempt_at` and an `archive` a not-answer
      wrote are removed; deferrals and every outcome the current code recorded are kept.
    * group B: `attempts`, `last_attempt_at` and `archive` come back from the dump;
      `attempts_quality` is "unverified".
    * group C: `attempts` is the count at the cut less the proven not-answer; with
      reconstruction, `last_attempt_at` and `archive` are Live Score's last real answer, and
      `attempts_quality` is "upper_bound".
    * every fixture: a last outcome a not-answer wrote is replaced by the one the dump holds, or
      the reconstructed answer, or removed; `next_ask_after` is recomputed by the application's own
      schedule; `attempts_at_correction` and `attempts_quality_as_of` say how many of the attempts
      are covered by the quality and from when, and `corrections` (last 5) records what was
      replaced. Observations are audited in `league_metadata.archive_corrections` (last 50), with
      what a later run needs to plan that day's fixtures again.

WHAT IT WILL NOT DO
    It never touches a status, a score, a result, a stop, or any table but `leagues` and
    `matches`, and it makes no provider request and writes nothing to Redis. It writes nothing
    without --apply: report-only runs in a read-only transaction.

    It makes no plan at all, in either mode, once the outage it was made for has ended or the cut
    is not where it began: Redis records a last success for Live Score other than the instant
    given; Live Score is recorded answering after the cut (an observation of any competition, or
    a match row it synced); or a not-answer still stored was stamped before the cut. From then on
    the counters can mix real asks with false ones, and the plan has to be made again by a person.

    With --apply it refuses the live database (`soccer_predictions`) unless --owner-approved, and
    the database the backend uses (that one, or the one the application is configured with)
    unless --i-stopped-the-backend, whatever pg_stat_activity shows. The scheduler replaces these
    JSONB documents whole, and a pass that read them before the repair would write the false values
    back after it; but in development the backend's engine uses NullPool, so it holds no
    connection between passes and pg_stat_activity is empty while the scheduler is running. The
    flag is a claim, so it is also checked: the script refuses while anything accepts connections
    on the backend's address (127.0.0.1:8000, or --backend-address), while a sync pass holds a
    `sync:lock:*` key, while the scheduler recorded a task in the last two ticks, or when Redis
    cannot be read to tell. Just before COMMIT it checks again, and rolls back if any of that
    changed or another session is waiting on a row it locked: that session would write its stale
    copy the moment the repair commits. On any other database (a copy restored for a rehearsal) a
    connected client is a refusal unless --i-stopped-the-backend.

    A row this script already corrected is skipped. A fixture that a stale pass wrote back anyway
    carries no record of the correction, and a re-run finds it again: a competition-day corrected
    earlier is rebuilt from its `archive_corrections` record, and its fixtures are planned against
    it.

USAGE
    ./venv311/bin/python scripts/repair_not_answers.py --prior-dump ../backups/<dump>.sql.gz
    ./venv311/bin/python scripts/repair_not_answers.py --prior-dump ... --report plan.jsonl
    ./venv311/bin/python scripts/repair_not_answers.py --prior-dump ... --database-url ... --apply
        --livescore-last-success 2026-10-02T14:53:28.028159Z
        [--reconstruct-from-synced-rows] [--no-subtract-proven-pre-window] [--skip-closed-relistings]
        [--i-stopped-the-backend] [--backend-address 127.0.0.1:8000]

    Rehearse it on a restored copy and read the report before running it against the live database.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import socket
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.predictions import League, Match  # noqa: E402
from app.services.match_registry import (  # noqa: E402
    RELISTED_KEY, ArchiveState, MatchRegistry, RecoveryOutcome, _next_ask_from, _parse_instant,
    recovery_state_of,
)
from app.services.providers import competitions as comps  # noqa: E402
from app.services.sync_scheduler import LOCK_KEY, STATE_KEY as TASK_STATE_KEY  # noqa: E402
from repair_duplicate_matches import redacted  # noqa: E402

#: The database this script will not write to without --owner-approved.
LIVE_DATABASE = "soccer_predictions"
#: Where the backend listens when it is run locally; --backend-address replaces it. Only a TCP
#: connection is opened and closed: no request is sent.
DEFAULT_BACKEND_ADDRESSES = ("127.0.0.1:8000",)
#: The one provider that holds an id for the national-team competitions, and whose traces after
#: the cut mean the outage has ended.
LIVESCORE = "livescore"
#: What `by` says on every record this script leaves, and how a later run knows a row is done.
BY = "backend/scripts/repair_not_answers.py"
#: The observation stamp and the fixture stamps of one pass are taken separately, milliseconds
#: apart; Live Score's own status stamp precedes its observation by a few more. One second absorbs
#: that and is far shorter than the gap between two passes.
MARGIN = timedelta(seconds=1)
#: How long before an observation's stamp the rows its answer synced can carry their own stamps.
SYNC_WINDOW = timedelta(seconds=3)
#: The keys one answer writes on an observation (`MatchRegistry.record_archive_observation`).
#: `last_answered_at` is not among them: only an answer WITH rows writes it, which a not-answer
#: never had.
ANSWER_KEYS = ("state", "rows", "asked_at", "provider", "first_asked_at", "times_asked")
#: The three fields one recorded outcome writes on a fixture.
OUTCOME_KEYS = ("last_outcome", "last_outcome_at", "last_outcome_detail")
#: Audit records kept: per fixture like `previous_stops`, per competition for its observations.
FIXTURE_CORRECTIONS_KEPT = 5
ARCHIVE_CORRECTIONS_KEPT = 50
#: How a count reads after the repair. Only "exact" is a count of asks the provider answered.
EXACT, UNVERIFIED, UPPER_BOUND = "exact", "unverified", "upper_bound"
DEFAULT_CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "docs", "evidence", "livescore-archive-observations.json")
#: Where the application keeps a provider's last success (`MatchDataService._record_status`).
STATUS_KEY = "provider:status:{name}"


class PlanChanged(RuntimeError):
    """A row the plan was made from no longer holds what the plan read. Nothing was written."""


# --------------------------------------------------------------------------- reading the records
def _copy_unescape(field_text: str) -> Optional[str]:
    """One field of a COPY ... FROM stdin line, in PostgreSQL's text format, as its value."""
    if field_text == r"\N":
        return None
    out: List[str] = []
    i, n = 0, len(field_text)
    simple = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
    while i < n:
        c = field_text[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = field_text[i + 1]
        if nxt in simple:
            out.append(simple[nxt])
            i += 2
        elif nxt in "01234567":
            j = i + 1
            while j < n and j < i + 4 and field_text[j] in "01234567":
                j += 1
            out.append(chr(int(field_text[i + 1:j], 8)))
            i = j
        elif nxt == "x" and i + 2 < n and field_text[i + 2] in "0123456789abcdefABCDEF":
            j = i + 2
            while j < n and j < i + 4 and field_text[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(chr(int(field_text[i + 2:j], 16)))
            i = j
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


@dataclass
class PriorDump:
    """What a plain pg_dump held for the two tables this repair reads. Read once, never written."""

    path: str
    #: league id -> ISO date -> observation entry
    observations: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    recovery: Dict[str, Dict[str, Any]] = field(default_factory=dict)                 # match id -> recovery

    @classmethod
    def load(cls, path: str) -> "PriorDump":
        dump = cls(path=path)
        wanted = {"predictions.leagues", "predictions.matches"}
        opener = gzip.open if path.endswith(".gz") else open
        table: Optional[str] = None
        columns: List[str] = []
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if table is None:
                    match = re.match(r"^COPY (\S+) \((.*)\) FROM stdin;", line)
                    if match and match.group(1) in wanted:
                        table, columns = match.group(1), [c.strip() for c in match.group(2).split(",")]
                    continue
                if line.startswith("\\."):
                    table = None
                    continue
                row = dict(zip(columns, (_copy_unescape(v) for v in line.rstrip("\n").split("\t"))))
                if table == "predictions.leagues":
                    meta = json.loads(row["league_metadata"]) if row.get("league_metadata") else {}
                    if meta.get("archive_observations"):
                        dump.observations[row["id"]] = meta["archive_observations"]
                else:
                    meta = json.loads(row["match_metadata"]) if row.get("match_metadata") else {}
                    if isinstance(meta.get("recovery"), dict):
                        dump.recovery[row["id"]] = meta["recovery"]
        return dump

    def observation(self, league_id, day: str) -> Optional[Dict[str, Any]]:
        entry = (self.observations.get(str(league_id)) or {}).get(day)
        return dict(entry) if isinstance(entry, dict) else None

    def recovery_of(self, match_id) -> Optional[Dict[str, Any]]:
        state = self.recovery.get(str(match_id))
        return copy.deepcopy(state) if isinstance(state, dict) else None


def load_capture(path: Optional[str]) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Optional[str]]:
    """The application's own observations as captured in the evidence file, in the store's shape.

    Keyed (competition name, date). Only what the capture itself recorded is carried; the notes
    added beside it later (`last_answered_at` read at 22:55) are not part of the state at 03:15.
    """
    if not path:
        return {}, None
    with open(path, "r", encoding="utf-8") as handle:
        capture = (json.load(handle) or {}).get("recorded_by_the_application") or {}
    entries = {}
    for item in capture.get("observations") or []:
        entries[(item.get("competition"), item.get("match_date"))] = {
            "state": item.get("state"), "rows": item.get("rows"), "asked_at": item.get("last_asked_at"),
            "provider": item.get("answered_by"), "times_asked": item.get("times_asked"),
            "first_asked_at": item.get("first_asked_at"),
        }
    return entries, capture.get("captured_at")


def livescore_last_success(cache=None) -> Optional[datetime]:
    """Live Score's last successful request, as the application recorded it. A read; nothing set."""
    if cache is None:
        from app.services.match_cache import MatchCache
        cache = MatchCache()
    payload = cache.get(STATUS_KEY.format(name=LIVESCORE))
    return _parse_instant((payload or {}).get("last_success_at")) if isinstance(payload, dict) else None


def choose_cut(given: Optional[datetime], recorded: Optional[datetime], *, apply: bool
               ) -> Tuple[Optional[datetime], str, Optional[str]]:
    """The cut to plan with, where it came from, and why there must be no plan at all (or None).

    Redis's `last_success_at` is the right instant only while the outage lasts: Live Score's first
    success of any kind once access returns overwrites it, and planning with the later instant
    reads every not-answer before it as genuine, so the plan shrinks and still exits 0. A write
    therefore takes the instant a person approved, and Redis is a check on it from then on.
    """
    if given is None:
        if apply:
            return None, "", ("--apply needs --livescore-last-success: the instant the owner approved "
                              "in the report, pinned. Redis's value is not taken for a write: it moves on "
                              "Live Score's first success once access returns, and a cut moved past the "
                              "not-answers makes them look genuine"
                              + (f" (Redis says {recorded.isoformat()} now)" if recorded else ""))
        if recorded is None:
            return None, "", "Redis holds no last success for Live Score; pass --livescore-last-success"
        return recorded, "Redis provider:status:livescore, not pinned: --apply needs it given", None
    if recorded is None:
        return given, "given; Redis holds none to check it against", None
    if recorded > given:
        return None, "", (f"Redis records Live Score's last success at {recorded.isoformat()}, after the "
                          f"{given.isoformat()} given: Live Score has answered since, so the outage this "
                          f"plan was made for has ended and real asks may be mixed into the counters. The "
                          f"plan has to be made again by a person; nothing was changed")
    if recorded < given:
        return None, "", (f"the {given.isoformat()} given is later than Live Score's last success as the "
                          f"application recorded it, {recorded.isoformat()}: a cut later than the real one "
                          f"reads the not-answers before it as genuine; nothing was changed")
    return given, "given; Redis agrees", None


# --------------------------------------------------------------------------- rules
def holds_id(provider: Optional[str], comp: comps.CanonicalCompetition) -> Optional[bool]:
    """Whether `provider` can be asked about `comp` at all; None for a provider this file does not know."""
    attr = f"{provider}_id"
    if not provider or not hasattr(comp, attr):
        return None
    return getattr(comp, attr) is not None


def answering_provider(comp: comps.CanonicalCompetition) -> Optional[str]:
    """The one provider that can answer `comp`, or None when it is not exactly one."""
    able = [name for name in ("livescore", "api_football", "thesportsdb")
            if holds_id(name, comp)]
    return able[0] if len(able) == 1 else None


def is_false_observation(entry: Dict[str, Any], comp: comps.CanonicalCompetition, limit: datetime) -> bool:
    stamp = _parse_instant(entry.get("asked_at"))
    return holds_id(entry.get("provider"), comp) is False or (stamp is not None and stamp > limit)


def _same_instant(a, b) -> bool:
    pa, pb = _parse_instant(a), _parse_instant(b)
    return pa is not None and pa == pb


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def application_databases() -> Set[str]:
    """The databases a running backend writes to: the live one, and the one it is configured with."""
    names = {LIVE_DATABASE}
    try:
        configured = make_url(settings.DATABASE_URL).database
    except Exception:  # pragma: no cover - a malformed setting names nothing
        configured = None
    if configured:
        names.add(configured)
    return names


def refusal(database: str, *, apply: bool, owner_approved: bool, other_clients: int,
            stopped_backend: bool, application_database: bool = False,
            backend_signs: Sequence[str] = ()) -> Optional[str]:
    """Why --apply must not go ahead on this database now, or None."""
    if not apply:
        return None
    if database == LIVE_DATABASE and not owner_approved:
        return (f"refusing to write to {LIVE_DATABASE}, the live database: rehearse on a restored "
                f"copy, show the owner the report, and pass --owner-approved only once they approve it")
    if (application_database or database == LIVE_DATABASE) and not stopped_backend:
        # Not "unless other clients are connected": in development the backend's engine uses
        # NullPool, so between passes it holds no connection and pg_stat_activity is empty while the
        # scheduler is running. Nothing a query can see stands in for a person stopping it.
        return (f"refusing to write to {database}, the database the backend uses, without "
                f"--i-stopped-the-backend: the scheduler replaces these documents whole, and a pass "
                f"that read them before the repair would write the false values back after it. An "
                f"empty pg_stat_activity proves nothing (the development backend holds no connection "
                f"between passes). Stop the backend, keep it stopped until this commits, then pass "
                f"--i-stopped-the-backend")
    if other_clients and not stopped_backend:
        return (f"refusing to write while {_plural(other_clients, 'other client')} "
                f"{'is' if other_clients == 1 else 'are'} connected to {database}: the scheduler "
                f"replaces these documents whole, and a pass that read them before the repair would "
                f"write the false values back after it. Stop the backend, then pass "
                f"--i-stopped-the-backend")
    if backend_signs:
        return (f"refusing to write to {database} while the backend looks alive, whatever "
                f"--i-stopped-the-backend says: {'; '.join(backend_signs)}")
    return None


def other_clients(db: Session) -> int:
    # pg_stat_activity is read once per transaction and kept; clear it so this is now, not then.
    db.execute(text("SELECT pg_stat_clear_snapshot()"))
    return int(db.execute(text(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid()")).scalar() or 0)


def blocked_by_us(db: Session) -> int:
    """Sessions waiting on a lock this one holds: each would write its own copy once this commits."""
    # Asked late in the transaction that already read pg_stat_activity once (other_clients): without
    # clearing the snapshot it would list the sessions of that moment, not the one now waiting.
    db.execute(text("SELECT pg_stat_clear_snapshot()"))
    return int(db.execute(text(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() AND pg_backend_pid() = ANY(pg_blocking_pids(pid))")).scalar() or 0)


def _listening(address: str, timeout: float = 1.0) -> Optional[str]:
    """Why `address` looks taken, or None when the connection is refused. Opens and closes a TCP
    connection; sends nothing."""
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host.strip("[]") or "127.0.0.1", int(port)), timeout=timeout):
            return f"{address} accepts connections (the backend, and the scheduler inside it, look up)"
    except ConnectionRefusedError:
        return None
    except (OSError, ValueError) as exc:
        return f"could not tell whether {address} is free ({exc.__class__.__name__}: {exc})"


def backend_signs(cache=None, addresses: Sequence[str] = DEFAULT_BACKEND_ADDRESSES,
                  now: Optional[datetime] = None,
                  probe: Callable[[str], Optional[str]] = _listening) -> List[str]:
    """Everything that says a backend or a sync pass is running now; empty when nothing does.

    Read only: a TCP connection opened and closed per address, and Redis reads of the scheduler's
    own records. The scheduler runs inside the backend process, so an address that accepts
    connections is the strong sign; a held `sync:lock:*` is a pass in flight anywhere (also
    `scripts/sync_once.py`), and a task recorded in the last two ticks means a scheduler was
    running moments ago. None of these can prove a scheduler started elsewhere is not about to
    tick, which is why a person still has to say they stopped it.
    """
    signs = [sign for sign in (probe(address) for address in addresses) if sign]
    if cache is None:
        from app.services.match_cache import MatchCache
        cache = MatchCache()
    if not getattr(cache, "available", False):
        return signs + ["Redis could not be read, so nothing shows the scheduler stopped"]
    now = now or datetime.now(timezone.utc)
    for key in sorted(cache.keys(LOCK_KEY.format(name="*"))):
        signs.append(f"a sync pass holds {key} right now")
    quiet = timedelta(seconds=2 * max(int(settings.SYNC_SCHEDULER_TICK_SECONDS), 5))
    for key in sorted(cache.keys(TASK_STATE_KEY.format(name="*"))):
        state = cache.get(key)
        stamps = [_parse_instant(state.get(k)) for k in ("last_run_at", "last_skipped_at")] \
            if isinstance(state, dict) else []
        last = max((s for s in stamps if s is not None), default=None)
        if last is not None and now - last < quiet:
            signs.append(f"the scheduler recorded {key} at {last.isoformat()}, "
                         f"{int((now - last).total_seconds())} s ago (less than two ticks)")
    return signs


def script_sha256() -> str:
    with open(os.path.abspath(__file__), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:16]


# --------------------------------------------------------------------------- the plan
@dataclass
class ObservationFix:
    league_id: Any
    league: str
    key: str
    day: str
    cls: int
    before: Dict[str, Any]
    after: Optional[Dict[str, Any]]
    quality: str
    removed_asks: int
    window_false: int
    proven_pre_window: int
    reconstructed: bool
    evidence: Dict[str, Any]
    audit: Dict[str, Any]


@dataclass
class FixtureFix:
    match_id: Any
    league: str
    key: str
    day: str
    kickoff: str
    home: str
    away: str
    status: str
    group: str
    before: Dict[str, Any]
    after: Dict[str, Any]
    quality: str
    removed_attempts: int
    evidence: Dict[str, Any]


@dataclass
class Plan:
    now: datetime
    cut: datetime
    options: Dict[str, Any]
    validation: Dict[str, Any]
    observations: List[ObservationFix] = field(default_factory=list)
    fixtures: List[FixtureFix] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    already_corrected: int = 0


def _national_leagues(registry: MatchRegistry) -> List[Tuple[str, comps.CanonicalCompetition, League]]:
    out = []
    for key, comp in sorted(comps.COMPETITIONS.items()):
        if not comp.is_national_team:
            continue
        league = registry.league_for_key(key)
        if league is not None:
            out.append((key, comp, league))
    return out


def _synced_rows(db: Session, league_id, day: str, provider: str, stamp: datetime) -> List[str]:
    """Ids of the rows of `league_id` dated `day` that `provider` synced within SYNC_WINDOW before `stamp`."""
    start = datetime.combine(date.fromisoformat(day), datetime.min.time())
    rows = db.execute(text(
        "SELECT id, match_metadata->>'provider' AS provider, match_metadata->>'last_synced_at' AS synced "
        "FROM predictions.matches WHERE league_id = :lid AND match_date >= :start AND match_date < :end"),
        {"lid": str(league_id), "start": start, "end": start + timedelta(days=1)}).fetchall()
    found = []
    for row in rows:
        synced = _parse_instant(row.synced)
        if row.provider == provider and synced is not None and stamp - SYNC_WINDOW <= synced <= stamp:
            found.append(str(row.id))
    return sorted(found)


def check_synced_row_method(db: Session, nationals, limit: datetime) -> Dict[str, Any]:
    """Whether the rows a genuine answer synced still count what it returned, wherever that can be checked.

    A genuine answered observation whose last ask was its last answer with rows records both the
    stamp and the row count, so the method can be checked against it. Rows re-synced since moved
    their own stamps, and a disagreement anywhere means the method cannot be trusted here.
    """
    checked, disagree = 0, []
    for key, comp, league in nationals:
        provider = answering_provider(comp)
        for day, entry in sorted(((league.league_metadata or {}).get("archive_observations") or {}).items()):
            if (is_false_observation(entry, comp, limit) or entry.get("state") != ArchiveState.ANSWERED.value
                    or entry.get("provider") != provider
                    or not _same_instant(entry.get("asked_at"), entry.get("last_answered_at"))):
                continue
            checked += 1
            synced = _synced_rows(db, league.id, day, provider, _parse_instant(entry["last_answered_at"]))
            if len(synced) != entry.get("rows"):
                disagree.append({"league": league.name, "date": day, "rows": entry.get("rows"),
                                 "synced": len(synced)})
    return {"checked": checked, "agree": checked - len(disagree), "disagree": disagree}


def _at_cut(league: League, day: str, prior: PriorDump, capture: Dict, limit: datetime
            ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """The answer the observation recorded as it stood at the cut: (source, entry, disagreement).

    An entry holding only a recorded failure, or stamped after the cut, says nothing about it.
    """
    def usable(entry: Optional[Dict[str, Any]]) -> bool:
        stamp = _parse_instant((entry or {}).get("asked_at"))
        answered = (entry or {}).get("state") in (ArchiveState.ANSWERED.value, ArchiveState.EMPTY.value)
        return answered and stamp is not None and stamp <= limit

    found = []
    dumped = prior.observation(league.id, day)
    if usable(dumped):
        found.append(("dump", dumped))
    captured = capture.get((league.name, day))
    if usable(captured):
        found.append(("capture", dict(captured)))
    if not found:
        return None, None, None
    if len(found) == 2:
        a, b = found[0][1], found[1][1]
        same = (a.get("state") == b.get("state") and a.get("rows") == b.get("rows")
                and a.get("provider") == b.get("provider") and a.get("times_asked") == b.get("times_asked")
                and _same_instant(a.get("asked_at"), b.get("asked_at")))
        if not same:
            return None, None, "the dump and the capture disagree about this entry at the cut"
    return found[0][0], found[0][1], None


def _plan_observation(db: Session, key: str, comp, league: League, day: str, entry: Dict[str, Any],
                      prior: PriorDump, capture: Dict, cut: datetime, limit: datetime, now: datetime,
                      reconstruct_allowed: bool, reconstruct_refused: Optional[str],
                      subtract_proven: bool, sha: str) -> Tuple[Optional[ObservationFix], Optional[Dict]]:
    before = copy.deepcopy(entry)
    source, at_cut, disagreement = _at_cut(league, day, prior, capture, limit)
    where = {"row": "observation", "league": league.name, "date": day}
    if disagreement:
        return None, {**where, "reason": disagreement}
    first = _parse_instant(entry.get("first_asked_at"))
    if at_cut is None:
        if first is None or first <= limit:
            return None, {**where, "reason": "first asked before the cut, and no record shows it "
                                             "as it stood then"}
        cls = 1
    else:
        able = holds_id(at_cut.get("provider"), comp)
        if able is None:
            return None, {**where, "reason": f"the entry at the cut names {at_cut.get('provider')!r}, "
                                             f"a provider this script cannot judge"}
        cls = 2 if able else 3
    now_times = int(entry.get("times_asked") or 0)
    cut_times = int(at_cut.get("times_asked") or 0) if at_cut else 0
    window_false = now_times - cut_times
    if window_false < 0:
        return None, {**where, "reason": f"asked {now_times} times now but {cut_times} at the cut"}
    proven = 1 if cls == 3 and subtract_proven and cut_times > 0 else 0
    stamp = now.isoformat()
    evidence: Dict[str, Any] = {"at_cut_source": source, "at_cut": at_cut,
                                "times_asked_now": now_times, "times_asked_at_cut": cut_times,
                                "false_asks_after_cut": window_false}
    reconstructed = False
    if cls == 1:
        genuine = {k: v for k, v in entry.items() if k not in ANSWER_KEYS}
        after: Optional[Dict[str, Any]] = genuine or None
        quality = "removed"
        why = ("every ask recorded for this date was a not-answer: no provider that holds an id for it "
               "was asked")
    elif cls == 2:
        after = dict(entry)
        for k in ANSWER_KEYS:
            if k in at_cut:
                after[k] = at_cut[k]
            else:
                after.pop(k, None)
        quality = UNVERIFIED
        why = ("restored to the Live Score answer recorded at the cut; not-answers before it are "
               "possible and unrecorded, so its count is unverified")
    else:
        after = dict(entry)
        after["times_asked"] = cut_times - proven
        quality = UPPER_BOUND
        evidence["proven_not_answer_at_cut"] = {"asked_at": at_cut.get("asked_at"),
                                                "provider": at_cut.get("provider")}
        why = ("the entry at the cut was itself a not-answer; its count is the count at the cut"
               + (", less that not-answer," if proven else "")
               + " and is an upper bound")
        provider = answering_provider(comp)
        answered_at = _parse_instant(entry.get("last_answered_at"))
        if reconstruct_allowed and provider and answered_at is not None and answered_at <= limit:
            synced = _synced_rows(db, league.id, day, provider, answered_at)
            evidence["synced_rows"] = {"at": entry.get("last_answered_at"), "provider": provider,
                                       "count": len(synced), "match_ids": synced}
            if synced:
                after.update({"state": ArchiveState.ANSWERED.value, "rows": len(synced),
                              "asked_at": entry.get("last_answered_at"), "provider": provider,
                              "reconstructed": True})
                reconstructed = True
                why += ("; its state is Live Score's last answer with rows, reconstructed from the "
                        "match rows that answer synced")
            else:
                evidence["reconstruction_refused"] = "no match row carries that answer's sync any more"
        elif reconstruct_allowed or reconstruct_refused:
            evidence["reconstruction_refused"] = (reconstruct_refused
                                                  or "no Live Score answer with rows recorded")
        if not reconstructed:
            why += "; the state, rows, stamp and provider are still the not-answer's"
    if after is not None and cls != 1:
        after["count_quality"] = quality
        after["times_asked_at_correction"] = after.get("times_asked")
        after["count_quality_as_of"] = stamp
    # Beyond what was replaced and why, the audit keeps what planning the day's fixtures reads, so
    # a later run can plan a fixture a stale pass wrote back after the day itself was corrected.
    audit = {"date": day, "class": cls, "applied_at": stamp, "by": BY, "script_sha256": sha,
             "removed_asks": window_false + proven, "restored_from": source, "replaced": before,
             "why": why, "quality": quality, "after": copy.deepcopy(after),
             "false_asks_after_cut": window_false, "proven_pre_window": proven,
             "proven_not_answer_at_cut": evidence.get("proven_not_answer_at_cut"),
             "reconstructed": reconstructed}
    return ObservationFix(league_id=league.id, league=league.name, key=key, day=day, cls=cls,
                          before=before, after=after, quality=quality,
                          removed_asks=window_false + proven, window_false=window_false,
                          proven_pre_window=proven, reconstructed=reconstructed,
                          evidence=evidence, audit=audit), None


def _corrected_earlier(league: League, key: str, audit: Dict[str, Any]) -> Optional[ObservationFix]:
    """The fix an earlier run applied to a competition-day, rebuilt from its audit record.

    Not written again: it is what that day's fixtures are planned against when one of them no
    longer carries its own correction (a pass that read it before the repair wrote it back after).
    None for a record that lacks what planning needs.
    """
    needed = ("class", "replaced", "after", "false_asks_after_cut", "proven_pre_window", "reconstructed")
    if any(k not in audit for k in needed) or not isinstance(audit.get("replaced"), dict):
        return None
    cls = int(audit["class"])
    return ObservationFix(
        league_id=league.id, league=league.name, key=key, day=audit["date"], cls=cls,
        before=dict(audit["replaced"]), after=copy.deepcopy(audit["after"]),
        quality=audit.get("quality") or {1: "removed", 2: UNVERIFIED, 3: UPPER_BOUND}.get(cls, ""),
        removed_asks=int(audit.get("removed_asks") or 0), window_false=int(audit["false_asks_after_cut"]),
        proven_pre_window=int(audit["proven_pre_window"]), reconstructed=bool(audit["reconstructed"]),
        evidence={"proven_not_answer_at_cut": audit.get("proven_not_answer_at_cut"),
                  "corrected_earlier_at": audit.get("applied_at")},
        audit=audit)


def _outage_has_ended(db: Session, nationals, cut: datetime, limit: datetime) -> Optional[str]:
    """Why the records say the cut is not where the outage began, or None.

    Independent of Redis, which may hold nothing, or be checked against an instant someone copied
    from it after it moved. Live Score recorded answering after the cut, for any competition or in
    any row it synced, means real asks are mixed into the counters now. A not-answer still stored
    and stamped before the cut would be read as genuine, which is what a cut moved past the start
    of the outage does to all of them.
    """
    for league in db.query(League).order_by(League.name).all():
        for day, entry in sorted(((league.league_metadata or {}).get("archive_observations") or {}).items()):
            if not isinstance(entry, dict):
                continue
            stamp = _parse_instant(entry.get("asked_at"))
            if entry.get("provider") == LIVESCORE and stamp is not None and stamp > limit:
                return (f"{league.name} {day}: {LIVESCORE} is recorded answering at {entry.get('asked_at')}, "
                        f"after the {cut.isoformat()} given as its last success. Asks made since the "
                        f"outage ended are mixed into the counters now; this plan no longer holds")
    synced = db.execute(text(
        "SELECT id, match_metadata->>'last_synced_at' AS synced FROM predictions.matches "
        "WHERE match_metadata->>'provider' = :provider"), {"provider": LIVESCORE}).fetchall()
    after = sorted((s, str(row.id)) for row in synced
                   for s in [_parse_instant(row.synced)] if s is not None and s > limit)
    if after:
        return (f"{_plural(len(after), 'match row')} {LIVESCORE} synced after the {cut.isoformat()} given "
                f"as its last success (the latest at {after[-1][0].isoformat()}, match {after[-1][1]}). "
                f"The outage has ended and real asks may be mixed into the counters; this plan no "
                f"longer holds")
    for key, comp, league in nationals:
        for day, entry in sorted(((league.league_metadata or {}).get("archive_observations") or {}).items()):
            stamp = _parse_instant(entry.get("asked_at"))
            if holds_id(entry.get("provider"), comp) is False and stamp is not None and stamp + MARGIN <= cut:
                return (f"{league.name} {day}: the not-answer stored there ({entry.get('provider')}) was "
                        f"stamped {entry.get('asked_at')}, before the {cut.isoformat()} given as Live "
                        f"Score's last success. A cut set after not-answers still stored is not where the "
                        f"outage began (has Live Score answered since?); this plan no longer holds")
    return None


def _false_outcome(state: Dict[str, Any], limit: datetime, comp) -> bool:
    """Whether the last outcome on the row is one a not-answer wrote."""
    if state.get("last_outcome") != RecoveryOutcome.FRESH_UNANSWERED.value:
        return False
    at = _parse_instant(state.get("last_outcome_at"))
    detail = str(state.get("last_outcome_detail") or "")
    named = re.match(r"^(\w+) answered for this competition", detail)
    return (at is not None and at > limit) or bool(named and holds_id(named.group(1), comp) is False)


def _plan_fixture(match: Match, key: str, comp, obs: ObservationFix, prior: PriorDump,
                  limit: datetime, now: datetime, subtract_proven: bool, sha: str,
                  names: Dict) -> Tuple[Optional[FixtureFix], Optional[Dict]]:
    state = recovery_state_of(match)
    before = copy.deepcopy(state)
    day = match.match_date.date().isoformat()
    home, away = names.get(match.home_team_id), names.get(match.away_team_id)
    where = {"row": "fixture", "match_id": str(match.id), "league": obs.league, "date": day}
    attempts_now = int(state.get("attempts") or 0)
    first = _parse_instant(state.get("first_attempt_at"))
    if first is not None and first > limit:
        group = "A"
    elif obs.cls == 1:
        if first is not None:
            return None, {**where, "reason": "an attempt before the cut, on a day with no answer "
                                             "recorded then"}
        group = "A"
    else:
        group = "B" if obs.cls == 2 else "C"
    before_cut = attempts_now - obs.window_false
    dumped = prior.recovery_of(match.id)
    dumped_obs = prior.observation(match.league_id, day)
    evidence: Dict[str, Any] = {"observation": {"date": day, "class": obs.cls,
                                                "false_asks_after_cut": obs.window_false},
                                "attempts_now": attempts_now}
    if obs.evidence.get("corrected_earlier_at"):
        evidence["observation"]["corrected_earlier_at"] = obs.evidence["corrected_earlier_at"]
    if group == "A":
        if attempts_now > obs.window_false:
            return None, {**where, "reason": f"{attempts_now} attempts, more than the "
                                             f"{obs.window_false} not-answers its day received"}
        new_attempts = 0
    else:
        if before_cut < 1:
            return None, {**where, "reason": f"{attempts_now} attempts leaves {before_cut} before the cut"}
        if dumped is not None:
            # Between the dump and now the fixture and its day must have moved together.
            fixture_moved = attempts_now - int(dumped.get("attempts") or 0)
            day_moved = (int(obs.before.get("times_asked") or 0)
                         - int((dumped_obs or {}).get("times_asked") or 0))
            evidence["since_dump"] = {"fixture_attempts": fixture_moved, "observation_asks": day_moved}
            if fixture_moved != day_moved:
                return None, {**where, "reason": f"since the dump the fixture moved {fixture_moved} "
                                                 f"and its day {day_moved}"}
        # The not-answer at the cut counted an attempt on every fixture of its day that was being
        # asked about then: one first asked before it was. A row with attempts and no
        # `first_attempt_at` was first asked before the code that writes it ran (7380242), and that
        # same commit introduced the observations that prove the not-answer, so it was too.
        proven_at = _parse_instant((obs.evidence.get("proven_not_answer_at_cut") or {}).get("asked_at"))
        proven = 1 if (group == "C" and obs.proven_pre_window and proven_at is not None
                       and (first is None or first <= proven_at)) else 0
        new_attempts = before_cut - proven
        evidence["attempts_at_cut"] = before_cut
        evidence["proven_not_answer_removed"] = proven
    quality = {"A": EXACT, "B": UNVERIFIED, "C": UPPER_BOUND}[group]
    after = dict(state)
    restored_from = None
    if group == "A":
        for k in ("attempts", "first_attempt_at", "last_attempt_at"):
            after.pop(k, None)
        archive = state.get("archive") if isinstance(state.get("archive"), dict) else None
        if archive is not None and ((_parse_instant(archive.get("asked_at")) or limit) > limit
                                    or _same_instant(archive.get("asked_at"), obs.before.get("asked_at"))):
            after.pop("archive", None)
    elif group == "B":
        clean = dumped is not None and (_parse_instant(dumped.get("last_attempt_at")) or limit) <= limit
        if not clean or int(dumped.get("attempts") or 0) != before_cut:
            return None, {**where, "reason": "the dump does not hold this fixture as it stood at the cut"}
        after["attempts"] = new_attempts
        after["last_attempt_at"] = dumped.get("last_attempt_at")
        if isinstance(dumped.get("archive"), dict):
            after["archive"] = dumped["archive"]
        else:
            after.pop("archive", None)
        restored_from = "dump"
    else:
        after["attempts"] = new_attempts
        if obs.reconstructed:
            after["last_attempt_at"] = obs.after["asked_at"]
            after["archive"] = {"state": ArchiveState.ANSWERED.value, "rows": obs.after["rows"],
                                "asked_at": obs.after["asked_at"], "reconstructed": True}
            restored_from = "synced rows"
    if _false_outcome(state, limit, comp):
        dumped_outcome = {k: dumped.get(k) for k in OUTCOME_KEYS if k in (dumped or {})}
        if dumped_outcome and not _false_outcome(dumped_outcome, limit, comp):
            after.update(dumped_outcome)
        elif group == "C" and obs.reconstructed:
            after.update({
                "last_outcome": RecoveryOutcome.FRESH_UNANSWERED.value,
                "last_outcome_at": obs.after["asked_at"],
                "last_outcome_detail": (f"{obs.after['provider']} answered for this competition on {day} "
                                        f"with {obs.after['rows']} row(s), none of them a result for this "
                                        f"match (reconstructed on {now.date().isoformat()} from the match "
                                        f"rows that answer synced)"),
            })
        else:
            for k in OUTCOME_KEYS:
                after.pop(k, None)
    if (match.match_metadata or {}).get("relisted_as"):
        # A closed second listing: nothing will ask about it again, so it advertises no next ask
        # (MatchRegistry._retire_relisted removes the field for the same reason).
        after.pop("next_ask_after", None)
    elif not after.get("gave_up_at"):
        upcoming = _next_ask_from(after, match.match_date, now)
        if upcoming is None:
            after.pop("next_ask_after", None)
        else:
            after["next_ask_after"] = upcoming.isoformat()
    stamp = now.isoformat()
    after["attempts_quality"] = quality
    after["attempts_at_correction"] = new_attempts
    after["attempts_quality_as_of"] = stamp
    replaced = {k: state.get(k) for k in sorted(set(state) | set(after))
                if k not in ("corrections", "attempts_quality", "attempts_at_correction",
                             "attempts_quality_as_of") and state.get(k) != after.get(k)}
    corrections = list(state.get("corrections") or [])
    corrections.append({"applied_at": stamp, "by": BY, "script_sha256": sha, "group": group,
                        "removed_attempts": attempts_now - new_attempts, "replaced": replaced,
                        "restored_from": restored_from})
    after["corrections"] = corrections[-FIXTURE_CORRECTIONS_KEPT:]
    return FixtureFix(match_id=match.id, league=obs.league, key=key, day=day,
                      kickoff=match.match_date.isoformat(), home=home.name if home else "?",
                      away=away.name if away else "?", status=match.status.value, group=group,
                      before=before, after=after, quality=quality,
                      removed_attempts=attempts_now - new_attempts, evidence=evidence), None


def plan_repair(db: Session, *, cut: datetime, prior: PriorDump, capture: Dict, now: datetime,
                reconstruct: bool = False, subtract_proven: bool = True,
                skip_closed_relistings: bool = False, sha: Optional[str] = None) -> Plan:
    """Everything --apply would write, row by row, with the evidence for each. Writes nothing."""
    sha = sha or script_sha256()
    limit = cut + MARGIN
    registry = MatchRegistry(db)
    nationals = _national_leagues(registry)
    validation = check_synced_row_method(db, nationals, limit)
    refused = None
    if reconstruct and (validation["disagree"] or not validation["checked"]):
        refused = (f"the synced-row method agrees with {validation['agree']} of "
                   f"{validation['checked']} genuine answers, so nothing is reconstructed from it")
    plan = Plan(now=now, cut=cut, validation=validation, options={
        "reconstruct_from_synced_rows": reconstruct, "reconstruction_refused": refused,
        "subtract_proven_pre_window": subtract_proven, "skip_closed_relistings": skip_closed_relistings,
        "margin_seconds": MARGIN.total_seconds(), "script_sha256": sha})

    ended = _outage_has_ended(db, nationals, cut, limit)
    if ended:
        raise PlanChanged(ended)

    by_day: Dict[Tuple[str, str], ObservationFix] = {}
    for key, comp, league in nationals:
        meta = league.league_metadata or {}
        earlier: Dict[str, Dict[str, Any]] = {}
        for audit in meta.get("archive_corrections") or []:
            if isinstance(audit, dict) and str(audit.get("by", "")).startswith(BY) and audit.get("date"):
                earlier[audit["date"]] = audit                       # the latest record of a day wins
        for day, audit in earlier.items():
            rebuilt = _corrected_earlier(league, key, audit)
            if rebuilt is not None:
                by_day[(key, day)] = rebuilt
        for day, entry in sorted((meta.get("archive_observations") or {}).items()):
            if not is_false_observation(entry, comp, limit):
                continue
            audit = earlier.get(day)
            # Still false after a correction only as a class-3 entry kept without reconstruction,
            # which carries the correction's own stamp. Without it, the false entry was written
            # back after the correction (or written anew), and is planned again.
            if audit is not None and entry.get("count_quality_as_of") == audit.get("applied_at"):
                plan.already_corrected += 1
                continue
            fix, skip = _plan_observation(db, key, comp, league, day, entry, prior, capture, cut, limit,
                                          now, reconstruct and not refused, refused, subtract_proven, sha)
            if skip:
                plan.skipped.append(skip)
            else:
                plan.observations.append(fix)
                by_day[(key, day)] = fix

    national = {league.id: (key, comp) for key, comp, league in nationals}
    rows = (db.query(Match).filter(Match.league_id.in_(list(national)))
            .filter(Match.match_metadata.has_key("recovery")).order_by(Match.match_date, Match.id).all()
            if national else [])
    names = registry.team_names(rows)
    for match in rows:
        key, comp = national[match.league_id]
        state = recovery_state_of(match)
        if any(str(c.get("by", "")).startswith(BY) for c in state.get("corrections") or []):
            plan.already_corrected += 1
            continue
        day = match.match_date.date().isoformat()
        obs = by_day.get((key, day))
        last = _parse_instant(state.get("last_attempt_at"))
        archive = state.get("archive") if isinstance(state.get("archive"), dict) else {}
        archived = _parse_instant(archive.get("asked_at"))
        affected = ((last is not None and last > limit) or (archived is not None and archived > limit)
                    or (obs is not None
                        and _same_instant(archive.get("asked_at"), obs.before.get("asked_at"))))
        if not affected:
            continue
        where = {"row": "fixture", "match_id": str(match.id), "league": comp.name, "date": day}
        if obs is None:
            plan.skipped.append({**where, "reason": "its day has no false observation this run accounts "
                                                    "for, and no correction on record to plan it against"})
            continue
        if skip_closed_relistings and (match.match_metadata or {}).get(RELISTED_KEY):
            plan.skipped.append({**where, "reason": "a closed second listing, left as it is "
                                                    "(--skip-closed-relistings)"})
            continue
        fix, skip = _plan_fixture(match, key, comp, obs, prior, limit, now, subtract_proven, sha, names)
        if skip:
            plan.skipped.append(skip)
        else:
            plan.fixtures.append(fix)
    return plan


# --------------------------------------------------------------------------- applying it
def apply_plan(db: Session, plan: Plan) -> Dict[str, int]:
    """Write the plan in the caller's transaction, every target row locked and re-checked first."""
    league_ids = sorted({fix.league_id for fix in plan.observations}, key=str)
    match_ids = sorted({fix.match_id for fix in plan.fixtures}, key=str)
    leagues = {lg.id: lg for lg in (db.query(League).filter(League.id.in_(league_ids)).order_by(League.id)
                                    .populate_existing().with_for_update().all() if league_ids else [])}
    matches = {m.id: m for m in (db.query(Match).filter(Match.id.in_(match_ids)).order_by(Match.id)
                                 .populate_existing().with_for_update().all() if match_ids else [])}
    changed = []
    for fix in plan.observations:
        league = leagues.get(fix.league_id)
        store = ((league.league_metadata or {}).get("archive_observations") or {}) if league else {}
        if league is None or _canon(store.get(fix.day)) != _canon(fix.before):
            changed.append(f"{fix.league} {fix.day}")
    for fix in plan.fixtures:
        match = matches.get(fix.match_id)
        if match is None or _canon(recovery_state_of(match)) != _canon(fix.before):
            changed.append(f"match {fix.match_id}")
    if changed:
        raise PlanChanged(f"{_plural(len(changed), 'row')} changed since the plan was made: "
                          f"{', '.join(changed[:10])}{' ...' if len(changed) > 10 else ''}")

    for league_id in league_ids:
        league = leagues[league_id]
        meta = copy.deepcopy(league.league_metadata or {})
        store = dict(meta.get("archive_observations") or {})
        audits = list(meta.get("archive_corrections") or [])
        for fix in (f for f in plan.observations if f.league_id == league_id):
            if fix.after is None:
                store.pop(fix.day, None)
            else:
                store[fix.day] = copy.deepcopy(fix.after)
            audits.append(copy.deepcopy(fix.audit))
        meta["archive_observations"] = store
        meta["archive_corrections"] = audits[-ARCHIVE_CORRECTIONS_KEPT:]
        league.league_metadata = meta
    for fix in plan.fixtures:
        match = matches[fix.match_id]
        meta = copy.deepcopy(match.match_metadata or {})
        meta["recovery"] = copy.deepcopy(fix.after)
        match.match_metadata = meta
    db.flush()
    return {"observations": len(plan.observations), "fixtures": len(plan.fixtures)}


# --------------------------------------------------------------------------- reporting
def report_lines(plan: Plan, database: str) -> Iterable[Dict[str, Any]]:
    yield {"kind": "plan", "database": database, "now": plan.now.isoformat(),
           "livescore_last_success": plan.cut.isoformat(), "options": plan.options,
           "synced_row_method": plan.validation, "observations": len(plan.observations),
           "fixtures": len(plan.fixtures), "skipped": len(plan.skipped),
           "already_corrected": plan.already_corrected}
    for fix in plan.observations:
        yield {"kind": "observation", "league_id": str(fix.league_id), "league": fix.league, "key": fix.key,
               "date": fix.day, "class": fix.cls, "quality": fix.quality, "removed_asks": fix.removed_asks,
               "reconstructed": fix.reconstructed, "before": fix.before, "after": fix.after,
               "evidence": fix.evidence, "audit": fix.audit}
    for fix in plan.fixtures:
        yield {"kind": "fixture", "match_id": str(fix.match_id), "league": fix.league, "key": fix.key,
               "date": fix.day, "kickoff": fix.kickoff, "home": fix.home, "away": fix.away,
               "status": fix.status, "group": fix.group, "quality": fix.quality,
               "removed_attempts": fix.removed_attempts, "before": fix.before, "after": fix.after,
               "evidence": fix.evidence}
    for skip in plan.skipped:
        yield {**skip, "kind": "skipped"}


def print_plan(plan: Plan) -> None:
    v = plan.validation
    print(f"synced-row method checked on genuine answers: {v['agree']} of {v['checked']} agree"
          + (f"; disagreeing: {v['disagree']}" if v["disagree"] else ""))
    if plan.options.get("reconstruction_refused"):
        print(f"reconstruction refused: {plan.options['reconstruction_refused']}")
    print(f"\nfalse archive observations: {len(plan.observations)}")
    for fix in plan.observations:
        b, a = fix.before, fix.after
        after = ("removed" if a is None else
                 f"{a.get('state')}/{a.get('rows')}/{a.get('provider')} x{a.get('times_asked')} "
                 f"asked {a.get('asked_at')}")
        print(f"  class {fix.cls}  {fix.league:<38} {fix.day}  "
              f"{b.get('state')}/{b.get('rows')}/{b.get('provider')} x{b.get('times_asked')} -> {after}"
              f"  [{fix.quality}{', reconstructed' if fix.reconstructed else ''}; "
              f"{fix.removed_asks} ask(s) removed; "
              f"at cut: {fix.evidence.get('at_cut_source') or 'no entry'}]")
    print(f"\naffected fixtures: {len(plan.fixtures)}")
    for fix in plan.fixtures:
        b, a = fix.before, fix.after
        was, now = b.get("archive") or {}, a.get("archive") or {}
        earlier = fix.evidence.get("observation", {}).get("corrected_earlier_at")
        note = f"  (its day was corrected at {earlier}; this row was written back since)" if earlier else ""
        print(f"  group {fix.group}  {fix.match_id}  {fix.home} v {fix.away}  "
              f"{fix.kickoff} UTC  {fix.status}{note}")
        print(f"           attempts {b.get('attempts')} -> {a.get('attempts', 0)} [{fix.quality}], "
              f"last_attempt_at {b.get('last_attempt_at')} -> {a.get('last_attempt_at')}, "
              f"archive {was.get('state')}@{was.get('asked_at')} -> {now.get('state')}@{now.get('asked_at')}")
    if plan.skipped:
        print(f"\nleft untouched, evidence insufficient or disagreeing: {len(plan.skipped)}")
        for skip in plan.skipped:
            print(f"  {skip}")
    if plan.already_corrected:
        print(f"\nalready corrected by this script, skipped: {plan.already_corrected}")
    groups = {g: sum(1 for f in plan.fixtures if f.group == g) for g in "ABC"}
    classes = {c: sum(1 for f in plan.observations if f.cls == c) for c in (1, 2, 3)}
    print(f"\nobservations by class: {classes}; fixtures by group: {groups}; "
          f"asks removed: {sum(f.removed_asks for f in plan.observations)}; "
          f"attempts removed: {sum(f.removed_attempts for f in plan.fixtures)}")


def commit_plan(db: Session, plan: Plan, last_look: Callable[[], List[str]]) -> Dict[str, int]:
    """Write the plan and commit it, unless the last look before COMMIT finds a reason not to.

    The rows are locked and written by then, so a session that tries to write one of them waits
    on this transaction, and the last look sees it: it would write its own stale copy over the
    repair the moment this commits. On any reason, or any error, everything is rolled back and
    PlanChanged (or the error) is raised.
    """
    try:
        written = apply_plan(db, plan)
        reasons = last_look()
        if reasons:
            raise PlanChanged("just before COMMIT: " + "; ".join(reasons))
        db.commit()
        return written
    except Exception:
        db.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the plan (default: report only)")
    parser.add_argument("--database-url", default=None,
                        help="database to work on; defaults to the application's own")
    parser.add_argument("--prior-dump", required=True,
                        help="a plain pg_dump taken before the not-answers being repaired (read only)")
    parser.add_argument("--prior-capture", default=DEFAULT_CAPTURE,
                        help="the evidence file holding the application's 2026-10-05 03:15 capture")
    parser.add_argument("--livescore-last-success", default=None,
                        help="Live Score's last successful request (ISO), the cut: required with --apply, "
                             "and checked against Redis; a report without it uses Redis's value")
    parser.add_argument("--reconstruct-from-synced-rows", action="store_true",
                        help="rebuild a class-3 observation and its group-C fixtures from synced rows")
    parser.add_argument("--subtract-proven-pre-window", action=argparse.BooleanOptionalAction, default=True,
                        help="remove the one 2026-10-02 not-answer the capture proves (default: on)")
    parser.add_argument("--skip-closed-relistings", action="store_true",
                        help="leave fixtures closed as a second listing exactly as they are")
    parser.add_argument("--report", default=None, help="write one JSON line per row to this file")
    parser.add_argument("--owner-approved", action="store_true",
                        help=f"allow --apply on {LIVE_DATABASE}; only once the owner approved the report")
    parser.add_argument("--i-stopped-the-backend", action="store_true",
                        help="the backend is stopped and stays stopped until this commits: required with "
                             "--apply on the backend's database, and allows --apply on a copy other "
                             "clients are connected to")
    parser.add_argument("--backend-address", action="append", default=None, metavar="HOST:PORT",
                        help="where the backend listens, probed with a TCP connection before --apply on "
                             "its database (repeatable; default 127.0.0.1:8000)")
    args = parser.parse_args()

    url = args.database_url or settings.DATABASE_URL
    db = sessionmaker(autocommit=False, autoflush=False, bind=create_engine(url, echo=False))()
    if not args.apply:
        db.execute(text("SET TRANSACTION READ ONLY"))
    database = db.execute(text("SELECT current_database()")).scalar()
    now = datetime.now(timezone.utc)
    print(f"database: {redacted(str(url))}")
    mode = "APPLY - the plan below will be written" if args.apply else "report only, read-only transaction"
    print(f"mode:     {mode}")
    print(f"now:      {now.isoformat()}")

    from app.services.match_cache import MatchCache
    cache = MatchCache()
    recorded = None
    try:
        recorded = livescore_last_success(cache)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"could not read Live Score's status from Redis: {exc}")
    given = _parse_instant(args.livescore_last_success) if args.livescore_last_success else None
    if args.livescore_last_success and given is None:
        print(f"--livescore-last-success is not an instant: {args.livescore_last_success!r}")
        return 2
    cut, source, no_plan = choose_cut(given, recorded, apply=args.apply)
    print(f"live score last success: {cut.isoformat() if cut else 'none'} ({source or 'no cut'}; "
          f"given {given.isoformat() if given else 'nothing'}, "
          f"Redis says {recorded.isoformat() if recorded else 'nothing'})")
    if no_plan:
        db.rollback()
        print(f"REFUSED: {no_plan}")
        return 2
    print(f"false if stamped after: {(cut + MARGIN).isoformat()} (1 s margin)")

    application_database = database in application_databases()
    addresses = args.backend_address or list(DEFAULT_BACKEND_ADDRESSES)
    signs = backend_signs(cache, addresses) if args.apply and application_database else []
    stopped = refusal(database, apply=args.apply, owner_approved=args.owner_approved,
                      other_clients=other_clients(db) if args.apply else 0,
                      stopped_backend=args.i_stopped_the_backend,
                      application_database=application_database, backend_signs=signs)
    if stopped:
        db.rollback()
        print(stopped)
        return 2
    if args.apply and application_database:
        print(f"backend:  nothing accepts connections on {', '.join(addresses)}; no sync pass holds a "
              f"lock; no task recorded in the last two ticks (checked again just before COMMIT)")

    prior = PriorDump.load(args.prior_dump)
    capture, captured_at = load_capture(args.prior_capture)
    print(f"prior dump:    {args.prior_dump} ({len(prior.observations)} competitions with observations, "
          f"{len(prior.recovery)} fixtures with recovery)")
    print(f"prior capture: {args.prior_capture} (captured {captured_at}, {len(capture)} observations)")
    print(f"options:  reconstruct from synced rows: {'yes' if args.reconstruct_from_synced_rows else 'no'}; "
          f"subtract the proven pre-window not-answer: {'yes' if args.subtract_proven_pre_window else 'no'}; "
          f"skip closed relistings: {'yes' if args.skip_closed_relistings else 'no'}\n")

    try:
        plan = plan_repair(db, cut=cut, prior=prior, capture=capture, now=now,
                           reconstruct=args.reconstruct_from_synced_rows,
                           subtract_proven=args.subtract_proven_pre_window,
                           skip_closed_relistings=args.skip_closed_relistings)
    except PlanChanged as exc:
        db.rollback()
        print(f"REFUSED: {exc}")
        return 2
    plan.options["livescore_last_success_source"] = source
    print_plan(plan)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            for line in report_lines(plan, redacted(str(url))):
                handle.write(json.dumps(line, sort_keys=True, default=str) + "\n")
        print(f"\nreport: {args.report}")

    if not args.apply:
        db.rollback()
        print("\nreport only; nothing was changed. Re-run with --apply to write it.")
        return 0

    def last_look() -> List[str]:
        reasons = []
        waiting = blocked_by_us(db)
        if waiting:
            reasons.append(f"{_plural(waiting, 'other session')} {'is' if waiting == 1 else 'are'} waiting "
                           f"on rows this repair locked, and would write its own copy once it commits")
        if application_database:
            reasons += backend_signs(cache, addresses)
        return reasons

    try:
        written = commit_plan(db, plan, last_look)
    except PlanChanged as exc:
        print(f"\nABORTED, rolled back: {exc}")
        return 2
    except Exception as exc:
        print(f"\nFAILED, rolled back: {exc}")
        return 1
    print(f"\nwritten: {written['observations']} observation(s), {written['fixtures']} fixture(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
