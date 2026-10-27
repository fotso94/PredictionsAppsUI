#!/usr/bin/env python
"""
Find fixtures stored more than once, and fold the extra copies into one.

WHY THIS EXISTS
    Two providers that spell one club differently resolve it to two Team rows, and a fixture whose
    away club does not match by name is stored twice. Everton v Ipswich, 2026-09-19 14:00 UTC, was
    stored as two matches: the Live Score API copy finished correctly, the API-Football copy read
    LIVE at minute 62 for two days, and seven expert predictions sat on the copy that could never
    be settled. Folding a split fixture back into one row, and the club that split it back into
    one club, is a decision about identity that belongs to a person; this script lays out the
    evidence, does exactly what it printed, and never guesses.

    It also folds a listing its provider DROPPED AND ISSUED AGAIN under a new fixture id - a
    postponement, as a rule - into the listing the provider now maintains. Paris Saint-Germain v
    Lyon, Ligue 1 round 8, was listed by Live Score as fixture 1877019 for 2026-10-25 19:45 UTC,
    vanished from its lists on the 25th, and came back as fixture 742799 for 2026-10-26 19:30 UTC,
    the same clubs the same way round, played 2-0. The registry stored a second row (a provider's
    own other id was never a candidate), so nine forecast snapshots sat on a listing that never
    kicked off while the result sat on a row with no forecast, and the recovery sweep asked
    results providers about the dead listing eighteen times. The conditions are exactly the
    registry's (`MatchRegistry.superseded_listing_for`), which now joins such a re-issue at
    ingestion; this section is for the pairs that were stored before it did, or were re-issued
    before the dropped listing's kickoff had passed, when nothing could yet prove it dropped. The
    dropped row's forecasts, snapshots, predictions, slip legs, saved matches and provider refs
    MOVE to the maintained row with their timestamps untouched; the dead provider ref is kept,
    marked `superseded_by`; the dropped row's own record (kickoff, status, legacy id, sync and
    recovery metadata) is written onto the survivor under `match_metadata.superseded_listing`; and
    the emptied row is deleted. Two listings that disagree - the dropped one holds a result, the
    rounds differ, several candidates - are reported and left alone.

    It also reports two things it does not decide:

    * placeholder fixtures -- both slots naming no club, as `Home Team (TBD)` v `Away Team (TBD)`
      -- which are removed only when NOTHING at all points at them;
    * fixtures the sync stored with a `shared_slot_conflict`: a stored row held one of their clubs
      at their kickoff and the two could not be reconciled. One of the pair is a real fixture and
      the other is either the same fixture under an unlisted spelling -- one line in
      `app/services/match_matching.py`'s alias table, then a re-run of this script folds them --
      or a wrong provider record. That is a person's judgement, so they are listed, not touched;
    * every competition-and-kickoff slot holding more than one fixture. A fixture stored twice
      with BOTH clubs spelled differently shares no club row and no normalised name with its
      copy, so neither of the two reports above can see it; the slot it shares is all that is
      left. Ordinary matchdays fill this listing too, so it decides nothing -- see the docstring
      on `same_slot_fixtures`.

WHAT IT WILL NOT DO
    It never deletes a dependent row. Predictions, forecasts, snapshots, results, saved matches
    and provider refs are MOVED to the surviving match; only the emptied duplicate match row is
    deleted, and only after a recount proves nothing still points at it. Where a move would break
    a unique constraint the whole group is abandoned untouched and reported, because two rows the
    database says cannot coexist need a person, not a script.

    Dependent tables are read from the database catalogue on every run, not from a list in this
    file, so a foreign key added later cannot be silently left behind. The one table the catalogue
    cannot show is `provider_entity_refs`: it points at matches through a polymorphic
    (entity_type, entity_id) pair with no foreign key, so it is named here explicitly.

USAGE
    ./venv/bin/python scripts/repair_duplicate_matches.py                      # report only
    ./venv/bin/python scripts/repair_duplicate_matches.py --apply              # repair
    ./venv/bin/python scripts/repair_duplicate_matches.py --database-url ...   # a restored copy
    ./venv/bin/python scripts/repair_duplicate_matches.py --fold-superseded <dropped match id>
        folds ONE dropped-and-re-issued listing, named by a person; `--apply` alone never folds
        one, because a dropped listing beside a new one is a judgement about identity. Repeat the
        flag for several. With `--apply` too, the other sections repair as well.

    Prove it on a restored copy before running it against the live database.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.services.match_matching import normalize_team_name  # noqa: E402
from app.services.match_registry import (  # noqa: E402
    RELISTED_KEY, SHARED_SLOT_WINDOW, SUPERSEDED_KEY, SUPERSEDED_LISTING_WINDOW, UNSETTLED_GRACE, round_number,
)
from app.services.providers import competitions as comps  # noqa: E402

MATCHES_SCHEMA, MATCHES_TABLE = "predictions", "matches"

#: `provider_entity_refs` points at matches, teams and leagues alike through an (entity_type,
#: entity_id) pair with NO foreign key, so no catalogue query can find it. Its unique key is
#: (entity_type, provider, external_id), which a move never touches: the provider's id keeps its
#: value and simply comes to mean the surviving row.
POLYMORPHIC_ENTITY_TYPE = {"matches": "match", "teams": "team", "leagues": "league"}

#: Statuses a fixture can no longer leave.
TERMINAL = ("FINISHED", "CANCELLED")

#: Normalised club names that name no club. Spelt out in full rather than matched by a pattern:
#: a substring rule for "tbd" would take "Hapoel Tel Aviv (TBD venue)" with it, and the point of
#: this list is that a person can read every name a deletion can be based on.
PLACEHOLDER_TEAM_NAMES = {
    "home team (tbd)", "away team (tbd)", "tbd", "tba", "to be decided", "to be determined",
}


def redacted(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


# --------------------------------------------------------------------------- catalogue
@dataclass(frozen=True)
class Dependent:
    schema: str
    table: str
    column: str
    where: Optional[str] = None

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.table}"

    def filter_sql(self, param: str) -> str:
        clause = f"{self.column} = :{param}"
        return f"{clause} AND {self.where}" if self.where else clause


def dependents(db: Session, schema: str = MATCHES_SCHEMA, table: str = MATCHES_TABLE) -> List[Dependent]:
    """Every table that points at this one, read from the catalogue plus the polymorphic one."""
    rows = db.execute(text("""
        SELECT ns.nspname AS sch, cl.relname AS tbl, att.attname AS col
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = cl.relnamespace
        JOIN pg_class rcl ON rcl.oid = con.confrelid
        JOIN pg_namespace rns ON rns.oid = rcl.relnamespace
        JOIN LATERAL unnest(con.conkey) AS k(attnum) ON true
        JOIN pg_attribute att ON att.attrelid = cl.oid AND att.attnum = k.attnum
        WHERE con.contype = 'f' AND rcl.relname = :tbl AND rns.nspname = :sch
        ORDER BY 1, 2, 3
    """), {"sch": schema, "tbl": table}).fetchall()
    found = [Dependent(r.sch, r.tbl, r.col) for r in rows]
    entity_type = POLYMORPHIC_ENTITY_TYPE.get(table)
    if entity_type:
        found.append(Dependent("predictions", "provider_entity_refs", "entity_id",
                               f"entity_type = '{entity_type}'"))
    return found


def unique_key_columns(db: Session, dep: Dependent) -> List[List[str]]:
    """Column lists of the unique indexes on `dep.table` that constrain `dep.column`."""
    rows = db.execute(text("""
        SELECT i.relname AS idx, array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_namespace ns ON ns.oid = t.relnamespace
        JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE ix.indisunique AND NOT ix.indisprimary AND ns.nspname = :sch AND t.relname = :tbl
        GROUP BY i.relname
    """), {"sch": dep.schema, "tbl": dep.table}).fetchall()
    return [list(r.cols) for r in rows if dep.column in r.cols]


# --------------------------------------------------------------------------- finding duplicates
@dataclass
class Copy:
    id: str
    league_id: str
    kickoff: datetime
    status: str
    external_api_id: Optional[str]
    external_api_source: Optional[str]
    home: str
    away: str
    created_at: Optional[datetime]
    has_result: bool
    #: Competition name, for reports that group rows by competition. Left empty where the row was
    #: read by a query that does not join the leagues table.
    league: Optional[str] = None
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def dependent_rows(self) -> int:
        return sum(self.counts.values())


def _copies(db: Session) -> List[Copy]:
    rows = db.execute(text("""
        SELECT m.id::text AS id, m.match_date, m.status::text AS status, m.external_api_id,
               m.external_api_source, m.created_at, m.league_id::text AS league_id,
               ht.name AS home, at.name AS away, l.name AS league,
               EXISTS (SELECT 1 FROM predictions.match_results r WHERE r.match_id = m.id) AS has_result
        FROM predictions.matches m
        JOIN predictions.teams ht ON ht.id = m.home_team_id
        JOIN predictions.teams at ON at.id = m.away_team_id
        JOIN predictions.leagues l ON l.id = m.league_id
        ORDER BY m.match_date
    """)).fetchall()
    return [Copy(r.id, r.league_id, r.match_date, r.status, r.external_api_id, r.external_api_source,
                 r.home, r.away, r.created_at, bool(r.has_result), r.league) for r in rows]


def _clusters_within(members: List[Copy], window: timedelta) -> List[List[Copy]]:
    """Split rows that share a key into runs whose kickoffs lie within `window` of the run's first."""
    clusters: List[List[Copy]] = []
    members.sort(key=lambda c: c.kickoff)
    cluster: List[Copy] = members[:1]
    for copy in members[1:]:
        if copy.kickoff - cluster[0].kickoff <= window:
            cluster.append(copy)
        else:
            if len(cluster) > 1:
                clusters.append(cluster)
            cluster = [copy]
    if len(cluster) > 1:
        clusters.append(cluster)
    return clusters


def duplicate_groups(db: Session, window: timedelta = SHARED_SLOT_WINDOW) -> List[List[Copy]]:
    """
    Matches that are one fixture stored several times.

    Identity is the competition, the two clubs by their NORMALISED names -- which is what makes
    "Ipswich" and "Ipswich Town" one club here -- and a kickoff inside `window`. Anything further
    apart than that is two fixtures until a person says otherwise.
    """
    buckets: Dict[Tuple[str, str, str], List[Copy]] = defaultdict(list)
    for copy in _copies(db):
        key = (copy.league_id, normalize_team_name(copy.home), normalize_team_name(copy.away))
        buckets[key].append(copy)
    groups: List[List[Copy]] = []
    for members in buckets.values():
        if len(members) > 1:
            groups.extend(_clusters_within(members, window))
    return groups


def count_dependents(db: Session, copy: Copy, deps: Sequence[Dependent]) -> None:
    for dep in deps:
        copy.counts[dep.qualified] = db.execute(
            text(f"SELECT count(*) FROM {dep.qualified} WHERE {dep.filter_sql('mid')}"),
            {"mid": copy.id}).scalar() or 0


def pick_survivor(group: Sequence[Copy]) -> Copy:
    """
    Keep the copy that can still settle a prediction.

    A stored final score is the thing the whole pipeline exists to produce, and a copy that never
    got one can never score anything attached to it -- which is exactly how seven expert
    predictions ended up on a row frozen at minute 62. So a copy with a `match_results` row wins,
    then a copy whose status is terminal. Only after that does weight of attached rows count, and
    the oldest row breaks a remaining tie because it is the one the rest of the data grew around.

    The predictions are not lost by this: they MOVE to the survivor, which is where they become
    scorable.
    """
    return sorted(group, key=lambda c: (
        not c.has_result,
        c.status not in TERMINAL,
        -c.dependent_rows,
        c.created_at or datetime.max,
        c.id,
    ))[0]


# --------------------------------------------------------------------------- planning
@dataclass
class Plan:
    survivor: Copy
    dead: List[Copy]
    moves: Dict[str, int] = field(default_factory=dict)
    blockers: List[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.blockers


def collisions_for(db: Session, dep: Dependent, dead: Copy, survivor: Copy) -> List[str]:
    """Unique keys that moving `dead`'s rows onto `survivor` would break."""
    problems = []
    for cols in unique_key_columns(db, dep):
        others = [c for c in cols if c != dep.column]
        if others:
            on = " AND ".join(f"a.{c} IS NOT DISTINCT FROM b.{c}" for c in others)
            sql = (f"SELECT count(*) FROM {dep.qualified} a JOIN {dep.qualified} b ON {on} "
                   f"WHERE a.{dep.column} = :dead AND b.{dep.column} = :surv")
        else:
            sql = (f"SELECT count(*) FROM {dep.qualified} a WHERE a.{dep.column} = :dead "
                   f"AND EXISTS (SELECT 1 FROM {dep.qualified} b WHERE b.{dep.column} = :surv)")
        clashing = db.execute(text(sql), {"dead": dead.id, "surv": survivor.id}).scalar() or 0
        if clashing:
            problems.append(f"{dep.qualified}: {clashing} row(s) would collide on ({', '.join(cols)})")
    return problems


def plan_for(db: Session, group: Sequence[Copy], deps: Sequence[Dependent]) -> Plan:
    survivor = pick_survivor(group)
    plan = Plan(survivor, [c for c in group if c.id != survivor.id])
    for dead in plan.dead:
        for dep in deps:
            if dead.counts.get(dep.qualified):
                plan.moves[dep.qualified] = plan.moves.get(dep.qualified, 0) + dead.counts[dep.qualified]
                plan.blockers.extend(collisions_for(db, dep, dead, survivor))
    return plan


# --------------------------------------------------------------------------- applying
def fold_rows(db: Session, deps: Sequence[Dependent], target: str,
              survivor_id: str, dead_ids: Sequence[str]) -> Dict[str, int]:
    """
    Move every dependent row onto the survivor, then delete the emptied rows from `target`.

    One transaction per group: a half-moved fixture is worse than an unrepaired one. The recount
    before each delete is the guarantee in the docstring at the top of this file -- nothing is
    deleted while anything still points at it. Re-running this on an already-repaired database
    moves nothing and deletes nothing, because the duplicates no longer exist to be found.
    """
    moved: Dict[str, int] = {}
    for dead_id in dead_ids:
        for dep in deps:
            result = db.execute(
                text(f"UPDATE {dep.qualified} SET {dep.column} = :surv WHERE {dep.filter_sql('dead')}"),
                {"surv": survivor_id, "dead": dead_id})
            if result.rowcount:
                moved[dep.qualified] = moved.get(dep.qualified, 0) + result.rowcount
        left = {dep.qualified: db.execute(
            text(f"SELECT count(*) FROM {dep.qualified} WHERE {dep.filter_sql('rid')}"),
            {"rid": dead_id}).scalar() or 0 for dep in deps}
        still_pointing = {k: v for k, v in left.items() if v}
        if still_pointing:
            raise RuntimeError(f"{target} {dead_id} still has dependent rows after the move: {still_pointing}")
        db.execute(text(f"DELETE FROM {target} WHERE id = :rid"), {"rid": dead_id})
    return moved


def apply_plan(db: Session, plan: Plan, deps: Sequence[Dependent]) -> Dict[str, int]:
    return fold_rows(db, deps, f"{MATCHES_SCHEMA}.{MATCHES_TABLE}",
                     plan.survivor.id, [d.id for d in plan.dead])


def delete_unreferenced(db: Session, deps: Sequence[Dependent], target: str, row_id: str) -> None:
    """
    Delete one row, having proved at the moment of the delete that nothing points at it.

    The counts the caller reported were taken earlier and a concurrent sync can have attached a
    row since. Counting again here means the guarantee holds against the state being deleted
    rather than against the state that was printed.
    """
    left = {dep.qualified: db.execute(
        text(f"SELECT count(*) FROM {dep.qualified} WHERE {dep.filter_sql('rid')}"),
        {"rid": row_id}).scalar() or 0 for dep in deps}
    pointing = {k: v for k, v in left.items() if v}
    if pointing:
        raise RuntimeError(f"{target} {row_id} has dependent rows and is not a deletable orphan: {pointing}")
    db.execute(text(f"DELETE FROM {target} WHERE id = :rid"), {"rid": row_id})


# --------------------------------------------------------------------------- re-issued listings
@dataclass
class Supersession:
    """One listing a provider dropped (`stale`) and the listing it issued instead (`successor`)."""
    stale: Copy
    successor: Copy
    provider: str
    dead_ids: List[str]
    live_ids: List[str]
    blockers: List[str] = field(default_factory=list)
    moves: Dict[str, int] = field(default_factory=dict)
    #: Facts a person must weigh after the fold; none of them stops it.
    consequences: List[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.blockers


def _match_meta(db: Session, match_id: str) -> Dict:
    raw = db.execute(text("SELECT match_metadata FROM predictions.matches WHERE id = :mid"), {"mid": match_id}).scalar()
    if isinstance(raw, str):
        raw = json.loads(raw)
    return dict(raw or {})


def _round_of(db: Session, match_id: str) -> Optional[str]:
    return db.execute(text("SELECT round FROM predictions.matches WHERE id = :mid"), {"mid": match_id}).scalar()


def superseded_listings(db: Session, now: Optional[datetime] = None,
                        window: timedelta = SUPERSEDED_LISTING_WINDOW) -> List[Supersession]:
    """
    Every (dropped listing, re-issued listing) pair, by the registry's own conditions. Read-only.

    A dropped listing is SCHEDULED with no result and its kickoff window (`UNSETTLED_GRACE`) closed,
    or POSTPONED with no result, and not closed as the second listing of a played row. Its
    successor is another row in the same competition with the identical two clubs in the same
    order, kicking off after it and within `window`, that the SAME provider lists under a DIFFERENT
    id. The rows are compared by club row ids, as the registry compares them, so two spellings of
    one club are not seen here (the duplicate-clubs section above is for that). A dropped listing
    with two successors, or a successor with two dropped listings, is reported as such and not
    touched.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - UNSETTLED_GRACE).replace(tzinfo=None)
    rows = db.execute(text("""
        SELECT s.id::text AS stale_id, m.id::text AS successor_id,
               r1.provider AS provider, r1.external_id AS dead_id, r2.external_id AS live_id
        FROM predictions.matches s
        JOIN predictions.matches m
          ON m.id <> s.id AND m.league_id = s.league_id
         AND m.home_team_id = s.home_team_id AND m.away_team_id = s.away_team_id
         AND m.match_date > s.match_date AND m.match_date <= s.match_date + :window
        JOIN predictions.provider_entity_refs r1
          ON r1.entity_type = 'match' AND r1.entity_id = s.id
        JOIN predictions.provider_entity_refs r2
          ON r2.entity_type = 'match' AND r2.entity_id = m.id AND r2.provider = r1.provider
         AND r2.external_id <> r1.external_id
        WHERE NOT EXISTS (SELECT 1 FROM predictions.match_results x WHERE x.match_id = s.id)
          AND ((s.status::text = 'SCHEDULED' AND s.match_date <= :cutoff) OR s.status::text = 'POSTPONED')
        ORDER BY s.match_date, s.id, m.match_date, m.id, r1.provider, r1.external_id
    """), {"window": window, "cutoff": cutoff}).fetchall()
    copies = {c.id: c for c in _copies(db)}
    pairs: Dict[Tuple[str, str], Supersession] = {}
    for row in rows:
        stale, successor = copies.get(row.stale_id), copies.get(row.successor_id)
        if stale is None or successor is None:
            continue
        if RELISTED_KEY in _match_meta(db, stale.id):
            continue
        key = (stale.id, successor.id)
        if key not in pairs:
            pairs[key] = Supersession(stale, successor, row.provider, [], [])
        pair = pairs[key]
        if row.provider != pair.provider:
            pair.blockers.append(f"listed again by more than one provider ({pair.provider}, {row.provider}); a person decides")
        if row.dead_id not in pair.dead_ids:
            pair.dead_ids.append(row.dead_id)
        if row.live_id not in pair.live_ids:
            pair.live_ids.append(row.live_id)
    by_stale: Dict[str, List[Supersession]] = defaultdict(list)
    by_successor: Dict[str, List[Supersession]] = defaultdict(list)
    for pair in pairs.values():
        by_stale[pair.stale.id].append(pair)
        by_successor[pair.successor.id].append(pair)
    for pair in pairs.values():
        if len(by_stale[pair.stale.id]) > 1:
            pair.blockers.append(f"the dropped listing has {len(by_stale[pair.stale.id])} possible successors")
        if len(by_successor[pair.successor.id]) > 1:
            pair.blockers.append(f"the successor could replace {len(by_successor[pair.successor.id])} dropped listings")
        mine, theirs = round_number(_round_of(db, pair.stale.id)), round_number(_round_of(db, pair.successor.id))
        if mine is not None and theirs is not None and mine != theirs:
            pair.blockers.append(f"the rounds differ ({_round_of(db, pair.stale.id)!r} against "
                                 f"{_round_of(db, pair.successor.id)!r}): two meetings, not one")
        key = _canonical_key(db, pair.stale.league_id)
        entry = comps.COMPETITIONS.get(key) if key else None
        if entry is None:
            pair.blockers.append(f"not a registered competition ({key!r}); a person decides")
        elif entry.is_cup or entry.is_national_team:
            pair.blockers.append(f"not a league competition ({key}): a cup replays at the same ground and a "
                                 f"national-team window can hold two friendlies the same way round; a person decides")
    return sorted(pairs.values(), key=lambda p: (p.stale.kickoff, p.stale.id))


def _canonical_key(db: Session, league_id: str) -> Optional[str]:
    key = db.execute(text("SELECT league_metadata->>'canonical_key' FROM predictions.leagues WHERE id = :lid"),
                     {"lid": league_id}).scalar()
    if key:
        return key
    return db.execute(text("""
        SELECT external_id FROM predictions.provider_entity_refs
        WHERE entity_type = 'league' AND provider = 'canonical' AND entity_id = :lid
    """), {"lid": league_id}).scalar()


def plan_supersession(db: Session, pair: Supersession, deps: Sequence[Dependent]) -> Supersession:
    """
    What folding the dropped listing into its successor would move, and what stops it.

    The successor is the survivor whatever the two rows carry: it is the listing the provider
    maintains, with the kickoff the match was played at. Every dependent row of the dropped
    listing moves; a unique key that the move would break (a current forecast from a provider the
    successor already has one from, say) is a contradiction between the two rows and blocks the
    whole pair.
    """
    count_dependents(db, pair.stale, deps)
    count_dependents(db, pair.successor, deps)
    for dep in deps:
        n = pair.stale.counts.get(dep.qualified) or 0
        if n:
            pair.moves[dep.qualified] = n
            pair.blockers.extend(collisions_for(db, dep, pair.stale, pair.successor))
    if pair.stale.has_result:
        pair.blockers.append("the dropped listing holds a result: it was played, so it was not dropped")
    moved_people = sum(pair.stale.counts.get(t, 0) for t in
                       ("predictions.predictions", "users.selection_slip_legs", "users.saved_matches"))
    if moved_people:
        pair.consequences.append(
            f"{moved_people} prediction(s), slip leg(s) or saved match(es) made for the listing dated "
            f"{pair.stale.kickoff} move to a match played {pair.successor.kickoff}"
            + ("; the next settle pass scores them against its result" if pair.successor.has_result else "")
            + ": whether they should stand is a separate decision")
    late = db.execute(text("""
        SELECT count(*) FROM predictions.provider_forecast_snapshots
        WHERE match_id = :mid AND captured_before_kickoff IS FALSE AND first_fetched_at < :played
    """), {"mid": pair.stale.id, "played": pair.successor.kickoff}).scalar() or 0
    if late:
        pair.consequences.append(
            f"{late} snapshot(s) retrieved before the match was played but after the dropped listing's kickoff "
            f"are recorded as captured after the kickoff known at capture (`captured_before_kickoff` false) and "
            f"stay so: settlement will not score them unless a separate decision re-evaluates them; their "
            f"retrieval times are untouched")
    return pair


def apply_supersession(db: Session, pair: Supersession, deps: Sequence[Dependent], now: Optional[datetime] = None
                       ) -> Dict[str, int]:
    """
    Fold the dropped listing into its successor. One transaction, caller commits.

    Dependents move with `fold_rows` (recount before the delete, as everywhere in this script). Then
    the dead provider ref, now on the survivor, is marked `superseded_by` the live id, and the
    dropped row's own record - kickoff, status, legacy id, metadata, created_at - is written onto
    the survivor under `match_metadata.superseded_listing`, where a reader of the row can see
    what it was folded from. The survivor's kickoff, status, scores and refs are its own and are
    not touched. Re-running finds no dropped listing and changes nothing.
    """
    now = now or datetime.now(timezone.utc)
    stale_meta = _match_meta(db, pair.stale.id)
    stale_row = db.execute(text("""
        SELECT match_date, status::text AS status, external_api_id, external_api_source, round, created_at
        FROM predictions.matches WHERE id = :mid"""), {"mid": pair.stale.id}).first()
    moved = fold_rows(db, deps, f"{MATCHES_SCHEMA}.{MATCHES_TABLE}", pair.successor.id, [pair.stale.id])
    for dead_id in pair.dead_ids:
        db.execute(text("""
            UPDATE predictions.provider_entity_refs
            SET ref_metadata = COALESCE(ref_metadata, '{}'::jsonb) || CAST(:note AS jsonb)
            WHERE entity_type = 'match' AND entity_id = :surv AND provider = :prov AND external_id = :dead
        """), {"surv": pair.successor.id, "prov": pair.provider, "dead": dead_id,
               "note": json.dumps({"superseded_by": {"external_id": pair.live_ids[0],
                                                     "kickoff_utc": pair.successor.kickoff.replace(tzinfo=timezone.utc).isoformat(),
                                                     "at": now.isoformat(), "by": "scripts/repair_duplicate_matches.py"}})})
    meta = _match_meta(db, pair.successor.id)
    event = {
        "provider": pair.provider,
        "previous_external_ids": list(pair.dead_ids),
        "external_id": pair.live_ids[0],
        "previous": {"match_id": pair.stale.id,
                     "kickoff_utc": stale_row.match_date.replace(tzinfo=timezone.utc).isoformat() if stale_row.match_date else None,
                     "status": stale_row.status, "external_api_id": stale_row.external_api_id,
                     "external_api_source": stale_row.external_api_source, "round": stale_row.round,
                     "created_at": stale_row.created_at.isoformat() if stale_row.created_at else None,
                     "match_metadata": stale_meta},
        "kickoff_utc": pair.successor.kickoff.replace(tzinfo=timezone.utc).isoformat(),
        "moved": dict(moved),
        "detected_at": now.isoformat(),
        "by": "scripts/repair_duplicate_matches.py",
        "reason": (f"{pair.provider} stopped listing fixture {', '.join(pair.dead_ids)} ({stale_row.match_date} UTC, never "
                   f"reported started, no result) and lists the same two clubs the same way round in the same "
                   f"competition as fixture {', '.join(pair.live_ids)} ({pair.successor.kickoff} UTC): the same match, "
                   f"re-issued. The dropped row's dependents were moved here with their timestamps untouched and the "
                   f"row deleted."),
    }
    earlier = meta.get(SUPERSEDED_KEY)
    history = list(earlier.get("history") or []) if isinstance(earlier, dict) else []
    if isinstance(earlier, dict):
        history.append({k: v for k, v in earlier.items() if k != "history"})
    meta[SUPERSEDED_KEY] = {**event, "history": history}
    db.execute(text("UPDATE predictions.matches SET match_metadata = CAST(:meta AS jsonb) WHERE id = :mid"),
               {"meta": json.dumps(meta, default=str), "mid": pair.successor.id})
    return moved


# --------------------------------------------------------------------------- placeholder fixtures
def placeholder_matches(db: Session, deps: Sequence[Dependent]) -> List[Copy]:
    """
    Fixtures whose two slots name no club, carrying their dependent-row counts.

    BOTH slots have to be a placeholder. One placeholder beside a real club is a cup tie waiting
    on a draw, or a row somebody half-wrote, and either way it says something a person should see
    rather than something a script should delete.

    The counts decide the rest: a placeholder nothing points at holds no prediction, no forecast,
    no saved match and no provider ref, so deleting it loses nothing that was ever recorded. One
    with dependants is reported and left exactly where it is.
    """
    found = []
    for copy in _copies(db):
        if (copy.home or "").strip().lower() not in PLACEHOLDER_TEAM_NAMES:
            continue
        if (copy.away or "").strip().lower() not in PLACEHOLDER_TEAM_NAMES:
            continue
        count_dependents(db, copy, deps)
        found.append(copy)
    return found


# --------------------------------------------------------------------------- unresolved clashes
@dataclass
class Conflict:
    match: Copy
    detail: Dict[str, object]
    present: List[str] = field(default_factory=list)
    gone: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        """No named counterpart is still stored, so there is nothing left to choose between."""
        return not self.present


def slot_conflicts(db: Session) -> List[Conflict]:
    """Fixtures the sync stored beside a row it could not reconcile them with."""
    rows = db.execute(text("""
        SELECT m.id::text AS id, m.match_date, m.status::text AS status, m.external_api_id,
               m.external_api_source, m.created_at, m.league_id::text AS league_id,
               ht.name AS home, at.name AS away,
               m.match_metadata -> 'shared_slot_conflict' AS detail
        FROM predictions.matches m
        JOIN predictions.teams ht ON ht.id = m.home_team_id
        JOIN predictions.teams at ON at.id = m.away_team_id
        WHERE m.match_metadata ? 'shared_slot_conflict'
        ORDER BY m.match_date
    """)).fetchall()
    out = []
    for r in rows:
        copy = Copy(r.id, r.league_id, r.match_date, r.status, r.external_api_id,
                    r.external_api_source, r.home, r.away, r.created_at, False)
        detail = r.detail or {}
        conflict = Conflict(copy, detail)
        for candidate in detail.get("candidates") or []:
            exists = db.execute(text("SELECT 1 FROM predictions.matches WHERE id = :cid"),
                                {"cid": candidate}).first()
            (conflict.present if exists else conflict.gone).append(candidate)
        out.append(conflict)
    return out


def clear_conflict_marker(db: Session, match_id: str) -> None:
    """Drop the marker from a row whose counterparts are all gone; nothing else on the row moves."""
    db.execute(text("""
        UPDATE predictions.matches
        SET match_metadata = match_metadata - 'shared_slot_conflict'
        WHERE id = :mid
    """), {"mid": match_id})


# --------------------------------------------------------------------------- one slot, two rows
def match_providers(db: Session, match_id: str) -> Dict[str, str]:
    """Provider fixture ids attached to one match row, provider -> external id."""
    rows = db.execute(text("""
        SELECT provider, external_id FROM predictions.provider_entity_refs
        WHERE entity_type = 'match' AND entity_id = :mid ORDER BY provider
    """), {"mid": match_id}).fetchall()
    return {r.provider: r.external_id for r in rows}


def same_slot_fixtures(db: Session, window: timedelta = SHARED_SLOT_WINDOW) -> List[List[Copy]]:
    """
    Stored fixtures sharing a competition and a kickoff, whatever clubs they hold.

    The two reports above each need something to agree before a split fixture becomes visible.
    `duplicate_groups` needs both club names to normalise to the same pair. `shared_slot_conflict`
    is only written when one stored club row is common to the fixture and the row it clashed with.
    A fixture stored twice with BOTH clubs spelled differently -- Cardiff City v Swansea City
    beside Cardiff v Swansea -- satisfies neither: four club rows, four names that never meet, and
    no marker anywhere. It is invisible to both, and this report is the one place it shows up.

    Competition and kickoff are all such a pair still shares, so that is the whole test here.
    Most sets it finds are an ordinary matchday, several real fixtures kicking off together, which
    is why this decides nothing, changes nothing and does not make the run fail. Reading one takes
    the provider ids printed beside each row: the rows of a matchday each carry the providers that
    cover the competition, while a fixture split in two has its providers split with it, disjoint
    sets one on each row.
    """
    buckets: Dict[str, List[Copy]] = defaultdict(list)
    for copy in _copies(db):
        buckets[copy.league_id].append(copy)
    slots: List[List[Copy]] = []
    for members in buckets.values():
        if len(members) > 1:
            slots.extend(_clusters_within(members, window))
    return sorted(slots, key=lambda cluster: cluster[0].kickoff)


# --------------------------------------------------------------------------- duplicate clubs
@dataclass
class Club:
    id: str
    name: str
    country: Optional[str]
    created_at: Optional[datetime]
    fixtures: int = 0
    providers: Dict[str, str] = field(default_factory=dict)


def duplicate_clubs(db: Session) -> List[List[Club]]:
    """
    Clubs stored more than once under one identity.

    A club split in two is what splits its fixtures, and folding the fixture without folding the
    club leaves the next sync free to do it again: the second provider's team id still resolves to
    its own row, and the fixture's away club flips back on the next pass. Identity here is the
    normalised name, the same function the matcher uses, so "Ipswich" and "Ipswich Town" are one.
    """
    rows = db.execute(text("""
        SELECT t.id::text AS id, t.name, t.country, t.created_at,
               (SELECT count(*) FROM predictions.matches m
                 WHERE m.home_team_id = t.id OR m.away_team_id = t.id) AS fixtures
        FROM predictions.teams t ORDER BY t.name
    """)).fetchall()
    buckets: Dict[str, List[Club]] = defaultdict(list)
    for r in rows:
        club = Club(r.id, r.name, r.country, r.created_at, int(r.fixtures))
        for ref in db.execute(text("""
            SELECT provider, external_id FROM predictions.provider_entity_refs
            WHERE entity_type = 'team' AND entity_id = :tid
        """), {"tid": r.id}).fetchall():
            club.providers[ref.provider] = ref.external_id
        buckets[normalize_team_name(r.name)].append(club)
    return [members for key, members in buckets.items() if key and len(members) > 1]


def club_blockers(group: Sequence[Club]) -> List[str]:
    """Reasons to leave a same-named group of clubs alone."""
    problems = []
    countries = {c.country for c in group if c.country and c.country != "Unknown"}
    if len(countries) > 1:
        problems.append(f"the rows claim different countries ({', '.join(sorted(countries))}); "
                        f"one name in two countries is two clubs")
    by_provider: Dict[str, set] = defaultdict(set)
    for club in group:
        for provider, external_id in club.providers.items():
            by_provider[provider].add(external_id)
    for provider, ids in by_provider.items():
        if len(ids) > 1:
            problems.append(f"{provider} gives these rows different ids ({', '.join(sorted(ids))}); "
                            f"one provider does not give one club two ids")
    return problems


def pick_club(group: Sequence[Club]) -> Club:
    """
    Keep the row the stored fixtures already use.

    That row is the name the site is showing and the one the fewest rows have to be moved off, and
    a club with fixtures is a club the rest of the data has already agreed on. A named country
    beats "Unknown", and the oldest row breaks a remaining tie.
    """
    return sorted(group, key=lambda c: (
        -c.fixtures,
        c.country in (None, "Unknown"),
        c.created_at or datetime.max,
        c.id,
    ))[0]


# --------------------------------------------------------------------------- reporting
def describe(copy: Copy, marker: str) -> str:
    return (f"    {marker} {copy.id}  {copy.kickoff}  {copy.status:<10} "
            f"{copy.external_api_id or '-':<24} result={'yes' if copy.has_result else 'no ':<3} "
            f"rows={copy.dependent_rows} {copy.counts}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="actually move the rows and delete the duplicates (default: report only)")
    parser.add_argument("--database-url", default=None,
                        help="database to work on; defaults to the application's own")
    parser.add_argument("--fold-superseded", action="append", default=[], metavar="MATCH_ID",
                        help="fold this dropped-and-re-issued listing (its match id) into the listing the "
                             "provider maintains; repeatable. Never implied by --apply.")
    args = parser.parse_args()
    selected = {m.strip() for m in args.fold_superseded if m.strip()}

    if args.database_url:
        url = args.database_url
    else:
        from app.core.config import settings
        url = settings.DATABASE_URL

    engine = create_engine(url, echo=False)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    print(f"database: {redacted(str(url))}")
    print(f"mode:     {'APPLY - rows will be moved and duplicates deleted' if args.apply else 'report only'}"
          + (f"; folding {len(selected)} named dropped listing(s)" if selected else "") + "\n")

    deps = dependents(db)
    print(f"tables pointing at {MATCHES_SCHEMA}.{MATCHES_TABLE} ({len(deps)}):")
    for dep in deps:
        note = "  (polymorphic, no foreign key)" if dep.where else ""
        print(f"    {dep.qualified}.{dep.column}{note}")
    print()

    exit_code = 0
    total_moved: Dict[str, int] = {}

    # Clubs first: a fixture folded while its club is still stored twice is folded again next sync.
    club_deps = dependents(db, "predictions", "teams")
    club_groups = duplicate_clubs(db)
    print(f"duplicate clubs: {len(club_groups)}")
    for group in club_groups:
        survivor = pick_club(group)
        dead = [c for c in group if c.id != survivor.id]
        print(f"  {survivor.name} ({survivor.country})")
        print(f"    KEEP {survivor.id}  {survivor.name!r:<20} fixtures={survivor.fixtures} {survivor.providers}")
        for club in dead:
            print(f"    FOLD {club.id}  {club.name!r:<20} fixtures={club.fixtures} {club.providers}")
        blockers = club_blockers(group)
        if blockers:
            print("    ABANDONED, nothing changed:")
            for blocker in blockers:
                print(f"      - {blocker}")
            exit_code = 1
            continue
        if args.apply:
            try:
                moved = fold_rows(db, club_deps, "predictions.teams", survivor.id, [c.id for c in dead])
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"    FAILED, rolled back: {exc}")
                exit_code = 1
                continue
            for table, n in moved.items():
                total_moved[table] = total_moved.get(table, 0) + n
            print(f"    moved:   {moved or 'nothing'}")
            print(f"    deleted: {len(dead)} duplicate club row(s)")
    print()

    groups = duplicate_groups(db)
    print(f"duplicate fixtures: {len(groups)}")
    for group in groups:
        for copy in group:
            count_dependents(db, copy, deps)
        plan = plan_for(db, group, deps)
        print(f"{plan.survivor.home} v {plan.survivor.away}  {plan.survivor.kickoff}  "
              f"({len(group)} copies)")
        print(describe(plan.survivor, "KEEP"))
        for dead in plan.dead:
            print(describe(dead, "FOLD"))
        if not plan.safe:
            print("    ABANDONED, nothing changed:")
            for blocker in plan.blockers:
                print(f"      - {blocker}")
            exit_code = 1
            print()
            continue
        print(f"    to move: {plan.moves or 'nothing'}")
        if args.apply:
            try:
                moved = apply_plan(db, plan, deps)
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"    FAILED, rolled back: {exc}")
                exit_code = 1
                print()
                continue
            for table, n in moved.items():
                total_moved[table] = total_moved.get(table, 0) + n
            print(f"    moved:   {moved or 'nothing'}")
            print(f"    deleted: {len(plan.dead)} duplicate match row(s)")
        print()

    supersessions = superseded_listings(db)
    print(f"listings dropped and issued again under a new id: {len(supersessions)}")
    folded = 0
    for pair in supersessions:
        plan_supersession(db, pair, deps)
        print(f"{pair.successor.home} v {pair.successor.away}  {pair.successor.league or pair.successor.league_id}")
        print(describe(pair.successor, "KEEP") + f"  {pair.provider}:{','.join(pair.live_ids)}")
        print(describe(pair.stale, "FOLD") + f"  {pair.provider}:{','.join(pair.dead_ids)} (dropped)")
        if not pair.safe:
            print("    ABANDONED, nothing changed:")
            for blocker in pair.blockers:
                print(f"      - {blocker}")
            exit_code = 1
            print()
            continue
        print(f"    to move: {pair.moves or 'nothing'}")
        for consequence in pair.consequences:
            print(f"    A PERSON DECIDES AFTERWARDS: {consequence}")
        if pair.stale.id not in selected:
            print(f"    NOT FOLDED: name it with --fold-superseded {pair.stale.id} to fold it")
            print()
            continue
        try:
            moved = apply_supersession(db, pair, deps)
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"    FAILED, rolled back: {exc}")
            exit_code = 1
            print()
            continue
        for table, n in moved.items():
            total_moved[table] = total_moved.get(table, 0) + n
        folded += 1
        print(f"    moved:   {moved or 'nothing'}")
        print(f"    deleted: 1 dropped listing; its record is on the survivor under match_metadata.{SUPERSEDED_KEY}")
        print()

    placeholders = placeholder_matches(db, deps)
    print(f"placeholder fixtures (both slots name no club): {len(placeholders)}")
    deleted_placeholders = 0
    for copy in placeholders:
        print(f"  {copy.home} v {copy.away}  {copy.kickoff}  {copy.status}  created={copy.created_at}")
        print(describe(copy, "ORPHAN" if not copy.dependent_rows else "IN USE"))
        if copy.dependent_rows:
            print("    KEPT: rows point at it, so something was recorded against it")
            exit_code = 1
            continue
        if args.apply:
            try:
                delete_unreferenced(db, deps, f"{MATCHES_SCHEMA}.{MATCHES_TABLE}", copy.id)
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"    FAILED, rolled back: {exc}")
                exit_code = 1
                continue
            deleted_placeholders += 1
            print("    deleted")
    print()

    conflicts = slot_conflicts(db)
    print(f"fixtures stored beside an unreconciled clash: {len(conflicts)}")
    cleared = 0
    for conflict in conflicts:
        copy, detail = conflict.match, conflict.detail
        print(f"  {copy.home} v {copy.away}  {copy.kickoff}  {copy.id}")
        print(f"    stored from {detail.get('provider')}:{detail.get('external_id')} "
              f"as {detail.get('home')!r} v {detail.get('away')!r}, seen {detail.get('detected_at')}")
        for candidate in conflict.present:
            row = db.execute(text("""
                SELECT ht.name AS home, at.name AS away, m.match_date, m.status::text AS status
                FROM predictions.matches m
                JOIN predictions.teams ht ON ht.id = m.home_team_id
                JOIN predictions.teams at ON at.id = m.away_team_id
                WHERE m.id = :cid
            """), {"cid": candidate}).first()
            print(f"    CLASHES WITH {candidate}  {row.home} v {row.away}  {row.match_date}  {row.status}")
        for candidate in conflict.gone:
            print(f"    counterpart {candidate} is no longer stored")
        if not conflict.resolved:
            print("    A PERSON DECIDES: one alias line makes them one fixture, or one record is wrong")
            exit_code = 1
            continue
        if args.apply:
            try:
                clear_conflict_marker(db, copy.id)
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"    FAILED, rolled back: {exc}")
                exit_code = 1
                continue
            cleared += 1
            print("    marker cleared; nothing is left to reconcile")
    print()

    slots = same_slot_fixtures(db)
    already_reported = {copy.id for group in groups for copy in group}
    already_reported.update(conflict.match.id for conflict in conflicts)
    print(f"competition + kickoff slots holding more than one fixture: {len(slots)}")
    print("    a normal matchday looks like this; read the provider ids, and see the docstring on "
          "same_slot_fixtures()")
    for cluster in slots:
        print(f"  {cluster[0].league or cluster[0].league_id}  {cluster[0].kickoff}  {len(cluster)} fixtures")
        for copy in cluster:
            seen = "  (also reported above)" if copy.id in already_reported else ""
            print(f"    {copy.id}  {copy.home} v {copy.away}  {copy.status:<10} "
                  f"{match_providers(db, copy.id)}{seen}")
    print("    nothing in this section was changed.")
    print()

    unknown = selected - {pair.stale.id for pair in supersessions}
    for match_id in sorted(unknown):
        print(f"--fold-superseded {match_id}: no dropped listing with this id was found; nothing done for it")
        exit_code = 1
    if args.apply or selected:
        print(f"total moved: {total_moved or 'nothing'}")
        print(f"dropped listings folded into their re-issue: {folded}")
        if args.apply:
            print(f"placeholder fixtures deleted: {deleted_placeholders}")
            print(f"settled clash markers cleared: {cleared}")
    elif not (groups or club_groups or placeholders or conflicts or supersessions):
        print("nothing to repair")
    else:
        print("report only; nothing was changed. Re-run with --apply to repair.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
