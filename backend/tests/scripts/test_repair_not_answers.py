"""
The not-answers repair takes back only what a provider that was never asked was recorded as
answering, restores only what an earlier record proves, and marks every count it cannot.

The rows below are shaped like the live ones (read 2026-10-07 01:08 UTC, see
docs/evidence/not-answers-repair/), and cover every class and group the script tells apart:

* observations: class 1 (every ask a not-answer: removed, a recorded failure kept), class 2 (a
  Live Score answer at the cut: restored from the dump), class 3 (the entry at the cut was itself
  a not-answer: its count corrected, its state reconstructed from synced rows on request), whether
  the state at the cut is read from the dump or, where the dump already holds a later not-answer,
  from the 03:15 capture;
* fixtures: group A (every attempt false), group B (a real prefix in the dump), group C (its day's
  entry at the cut was itself false), including a row from before `first_attempt_at` existed and
  a closed second listing whose last outcome is still the not-answer's sentence.

And around them, what must not move: a genuine national-team observation, a club competition's
answer from API-Football after the cut (it holds an id for that competition, so it is an answer),
a national fixture last asked before the cut, a club fixture, and every column but the metadata.

And the two ways a write could go wrong after a clean plan: a cut that moved once Live Score
answered again (Redis's last success is checked against the pinned one, and the records refuse a
cut set after not-answers still stored), and a backend still running beside the apply (its
NullPool engine is invisible to pg_stat_activity between passes, so the backend's own database
always needs the backend stopped, the claim is checked, and a stale copy written back afterwards
is found again on a re-run).

Requires PostgreSQL (JSONB, row locks). Set TEST_DATABASE_URL; skipped when unreachable. No
network, no provider, no Redis: Live Score's last success is passed in, and the backend checks
are given a stand-in for Redis and a probe (or a socket of their own on 127.0.0.1).
"""

from __future__ import annotations

import copy
import fnmatch
import gzip
import json
import os
import socket
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.base import Base  # noqa: E402
from app.models.predictions import Match, MatchStatus, Team  # noqa: E402
from app.services.match_registry import MatchRegistry, _next_ask_from, recovery_state_of  # noqa: E402
from scripts import repair_not_answers as repair  # noqa: E402
from tests.conftest import TEST_DATABASE_URL  # noqa: E402  (set it, or conftest's default is used)

#: Live Score's last successful request, as Redis recorded it.
CUT = datetime(2026, 10, 2, 14, 53, 28, 28159, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat()

FRIENDLIES, AFCON_Q, UNL, CLUB = ("national_teams_friendlies", "africa_cup_of_nations_qualification",
                                  "uefa_nations_league", "premier_league")

# ----------------------------------------------------------------------------- observations, now
OBS_NOW = {
    FRIENDLIES: {
        # class 3, the dump holds it at the cut: TheSportsDB's not-answer of 10-02 08:43
        "2026-09-28": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:54:23.616092+00:00",
                       "provider": "api_football", "times_asked": 25,
                       "first_asked_at": "2026-09-28T14:51:13.757069+00:00",
                       "last_answered_at": "2026-10-01T07:16:22.276377+00:00"},
        # class 3, the dump already holds a later not-answer: the capture shows it at the cut
        "2026-09-24": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:23:35.032467+00:00",
                       "provider": "api_football", "times_asked": 17,
                       "first_asked_at": "2026-09-25T16:49:04.821200+00:00",
                       "last_answered_at": "2026-10-01T07:46:51.829861+00:00"},
        # genuine: the synced-row method is checked against it
        "2026-09-29": {"rows": 2, "state": "answered", "asked_at": "2026-09-29T22:47:13.263820+00:00",
                       "provider": "livescore", "times_asked": 2,
                       "first_asked_at": "2026-09-29T18:46:58.594730+00:00",
                       "last_answered_at": "2026-09-29T22:47:13.263820+00:00"},
        # class 2, with a failure recorded since that is genuine and must stay
        "2026-09-30": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T16:04:55.033008+00:00",
                       "provider": "api_football", "times_asked": 31,
                       "first_asked_at": "2026-09-30T06:56:28.798814+00:00",
                       "last_answered_at": "2026-10-02T12:16:17.850638+00:00",
                       "last_failed_at": "2026-10-07T01:04:45.307108+00:00",
                       "last_failure": "livescore: authentication rejected (HTTP 401)"},
        # class 1
        "2026-10-03": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T22:54:47.434682+00:00",
                       "provider": "api_football", "times_asked": 4,
                       "first_asked_at": "2026-10-05T04:24:56.745725+00:00"},
    },
    AFCON_Q: {
        # class 3 read from the capture, like Friendlies 09-24
        "2026-09-25": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:23:35.165626+00:00",
                       "provider": "api_football", "times_asked": 31,
                       "first_asked_at": "2026-09-25T21:53:51.987276+00:00",
                       "last_answered_at": "2026-10-01T07:46:53.389206+00:00"},
    },
    UNL: {
        # class 1, nothing genuine on it: the date goes
        "2026-10-04": {"rows": 0, "state": "empty", "asked_at": "2026-10-06T00:25:19.825069+00:00",
                       "provider": "api_football", "times_asked": 1,
                       "first_asked_at": "2026-10-06T00:25:19.825069+00:00"},
        # class 1 with a genuine failure: only the failure stays
        "2026-10-03": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T22:54:47.428267+00:00",
                       "provider": "api_football", "times_asked": 4,
                       "first_asked_at": "2026-10-05T04:24:56.741878+00:00",
                       "last_failed_at": "2026-10-07T01:04:45.307108+00:00",
                       "last_failure": "livescore: authentication rejected (HTTP 401)"},
        "2026-09-28": {"rows": 3, "state": "answered", "asked_at": "2026-09-28T21:31:42.618177+00:00",
                       "provider": "livescore", "times_asked": 1,
                       "first_asked_at": "2026-09-28T21:31:42.618177+00:00",
                       "last_answered_at": "2026-09-28T21:31:42.618177+00:00"},
    },
    # API-Football holds an id for the Premier League: an answer after the cut is an answer.
    CLUB: {
        "2026-10-04": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T10:00:00.000000+00:00",
                       "provider": "api_football", "times_asked": 3,
                       "first_asked_at": "2026-10-04T18:00:00.000000+00:00"},
    },
}

# ----------------------------------------------------------------------------- observations, in the dump
OBS_DUMP = {
    FRIENDLIES: {
        "2026-09-28": dict(OBS_NOW[FRIENDLIES]["2026-09-28"], asked_at="2026-10-02T08:43:11.020249+00:00",
                           provider="thesportsdb", times_asked=24),
        "2026-09-24": dict(OBS_NOW[FRIENDLIES]["2026-09-24"]),
        "2026-09-29": dict(OBS_NOW[FRIENDLIES]["2026-09-29"]),
        "2026-09-30": {"rows": 6, "state": "answered", "asked_at": "2026-10-02T12:16:17.850638+00:00",
                       "provider": "livescore", "times_asked": 29,
                       "first_asked_at": "2026-09-30T06:56:28.798814+00:00",
                       "last_answered_at": "2026-10-02T12:16:17.850638+00:00"},
    },
    AFCON_Q: {"2026-09-25": dict(OBS_NOW[AFCON_Q]["2026-09-25"])},
    UNL: {"2026-09-28": dict(OBS_NOW[UNL]["2026-09-28"])},
}

#: The application's own record at 2026-10-05 03:15 UTC, as the evidence file holds it.
CAPTURE = {"recorded_by_the_application": {"captured_at": "2026-10-05T03:15:00Z", "observations": [
    {"competition": "National Teams Friendlies", "match_date": "2026-09-24", "state": "empty", "rows": 0,
     "first_asked_at": "2026-09-25T16:49:04.821200+00:00", "last_asked_at": "2026-10-02T08:12:00.958908+00:00",
     "times_asked": 16, "answered_by": "api_football",
     "last_answered_at": "2026-10-01T07:46:51.829861+00:00"},
    {"competition": "National Teams Friendlies", "match_date": "2026-09-28", "state": "empty", "rows": 0,
     "first_asked_at": "2026-09-28T14:51:13.757069+00:00", "last_asked_at": "2026-10-02T08:43:11.020249+00:00",
     "times_asked": 24, "answered_by": "thesportsdb"},
    {"competition": "National Teams Friendlies", "match_date": "2026-09-30", "state": "answered", "rows": 6,
     "first_asked_at": "2026-09-30T06:56:28.798814+00:00", "last_asked_at": "2026-10-02T12:16:17.850638+00:00",
     "times_asked": 29, "answered_by": "livescore"},
    {"competition": "Africa Cup of Nations Qualifications", "match_date": "2026-09-25", "state": "empty",
     "rows": 0, "first_asked_at": "2026-09-25T21:53:51.987276+00:00",
     "last_asked_at": "2026-10-02T08:12:01.530199+00:00", "times_asked": 30, "answered_by": "api_football"},
]}}

# ----------------------------------------------------------------------------- fixtures
DEFERRED_NOW = {"last_outcome": "deferred", "last_outcome_at": "2026-10-07T01:04:46.512000+00:00",
                "last_outcome_detail": "due an ask, and no request was made for it: no provider in the chain "
                                       "can be asked about this competition. Nothing was asked, so nothing "
                                       "was learned; it stays due",
                "last_deferred_at": "2026-10-07T01:04:46.512000+00:00",
                "last_deferred_because": ["not_served"],
                "next_ask_after": "2026-10-07T01:04:46.512000+00:00"}
DEFERRED_DUMP = {"deferrals": 1, "last_deferred_at": "2026-10-05T03:23:30.690880+00:00",
                 "last_deferred_because": ["our_allowance"], "last_outcome": "deferred",
                 "last_outcome_at": "2026-10-05T03:23:30.690880+00:00",
                 "last_outcome_detail": "due an ask, but one pass reopens at most 2 day(s), oldest first; "
                                        "it stays due",
                 "next_ask_after": "2026-10-05T03:23:30.690880+00:00"}

FIXTURES = {
    # group B: Papua New Guinea v Solomon Islands, a real prefix of 29 in the dump
    "B": dict(key=FRIENDLIES, kickoff=datetime(2026, 9, 30, 4, 0), status=MatchStatus.SCHEDULED,
              now={"attempts": 31, "first_attempt_at": "2026-09-30T06:56:28.809883+00:00",
                   "last_attempt_at": "2026-10-05T16:04:55.036575+00:00",
                   "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T16:04:55.033008+00:00"},
                   "deferrals": 4, **DEFERRED_NOW},
              dump={"attempts": 29, "first_attempt_at": "2026-09-30T06:56:28.809883+00:00",
                    "last_attempt_at": "2026-10-02T12:16:17.857905+00:00",
                    "archive": {"asked_at": "2026-10-02T12:16:17.850638+00:00", "rows": 6, "state": "answered"},
                    **DEFERRED_DUMP}),
    # group A: every attempt false; deferrals and the new code's outcome stay
    "A": dict(key=FRIENDLIES, kickoff=datetime(2026, 10, 3, 19, 0), status=MatchStatus.SCHEDULED,
              now={"attempts": 4, "first_attempt_at": "2026-10-05T04:24:56.750000+00:00",
                   "last_attempt_at": "2026-10-05T22:54:47.440000+00:00",
                   "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T22:54:47.434682+00:00"},
                   "deferrals": 3, **DEFERRED_NOW},
              dump=None),
    # group A whose last outcome is still the not-answer's sentence, and not in the dump at all
    "A2": dict(key=UNL, kickoff=datetime(2026, 10, 4, 18, 45), status=MatchStatus.SCHEDULED,
               now={"attempts": 1, "first_attempt_at": "2026-10-06T00:25:19.830000+00:00",
                    "last_attempt_at": "2026-10-06T00:25:19.830000+00:00",
                    "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-06T00:25:19.825069+00:00"},
                    "last_outcome": "fresh_unanswered", "last_outcome_at": "2026-10-06T00:25:19.830000+00:00",
                    "last_outcome_detail": "api_football answered for this competition on 2026-10-04 with "
                                           "0 row(s), none of them a result for this match",
                    "next_ask_after": "2026-10-06T02:25:19.830000+00:00"},
               dump=None),
    # group C, dump clean at the cut (the 08:43 not-answer)
    "C": dict(key=FRIENDLIES, kickoff=datetime(2026, 9, 28, 12, 0), status=MatchStatus.SCHEDULED,
              now={"attempts": 25, "first_attempt_at": "2026-09-28T14:51:13.774672+00:00",
                   "last_attempt_at": "2026-10-05T03:54:23.620000+00:00",
                   "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:54:23.616092+00:00"},
                   "deferrals": 5, **DEFERRED_NOW},
              dump={"attempts": 24, "first_attempt_at": "2026-09-28T14:51:13.774672+00:00",
                    "last_attempt_at": "2026-10-02T08:43:11.030000+00:00",
                    "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-02T08:43:11.020249+00:00"},
                    "deferrals": 2, "last_outcome": "fresh_unanswered",
                    "last_outcome_at": "2026-10-02T08:43:11.030000+00:00",
                    "last_outcome_detail": "thesportsdb answered for this competition on 2026-09-28 with 0 "
                                           "row(s), none of them a result for this match"}),
    # group C from before `first_attempt_at` existed (Friendlies 09-24)
    "C_legacy": dict(key=FRIENDLIES, kickoff=datetime(2026, 9, 24, 4, 0), status=MatchStatus.SCHEDULED,
                     now={"attempts": 20, "last_attempt_at": "2026-10-05T03:23:35.040000+00:00",
                          "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:23:35.032467+00:00"},
                          "deferrals": 4, **DEFERRED_NOW},
                     dump={"attempts": 20, "last_attempt_at": "2026-10-05T03:23:35.040000+00:00",
                           "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:23:35.032467+00:00"},
                           **DEFERRED_DUMP}),
    # group C, a closed second listing whose last outcome is still the not-answer's (Senegal v Mozambique)
    "C_relisted": dict(key=AFCON_Q, kickoff=datetime(2026, 9, 25, 19, 0), status=MatchStatus.POSTPONED,
                       relisted=True,
                       now={"attempts": 31, "first_attempt_at": "2026-09-25T21:53:51.997061+00:00",
                            "last_attempt_at": "2026-10-05T03:23:35.168455+00:00",
                            "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T03:23:35.165626+00:00"},
                            "deferrals": 1, "last_deferred_at": "2026-09-29T18:41:28.486232+00:00",
                            "last_deferred_because": ["cooling_down"], "last_outcome": "fresh_unanswered",
                            "last_outcome_at": "2026-10-05T03:23:35.168455+00:00",
                            "last_outcome_detail": "api_football answered for this competition on 2026-09-25 with "
                                                   "0 row(s), none of them a result for this match",
                            "next_ask_after": "2026-10-06T03:23:35.168455+00:00"},
                       dump=None),
    # untouched: national, last asked before the cut
    "genuine": dict(key=UNL, kickoff=datetime(2026, 9, 28, 18, 45), status=MatchStatus.SCHEDULED,
                    now={"attempts": 1, "first_attempt_at": "2026-09-28T21:31:42.620000+00:00",
                         "last_attempt_at": "2026-09-28T21:31:42.620000+00:00",
                         "archive": {"rows": 3, "state": "answered", "asked_at": "2026-09-28T21:31:42.618177+00:00"},
                         "last_outcome": "fresh_unanswered", "last_outcome_at": "2026-09-28T21:31:42.620000+00:00"},
                    dump=None),
    # untouched: a club fixture asked after the cut by a provider that holds its id
    "club": dict(key=CLUB, kickoff=datetime(2026, 10, 4, 14, 0), status=MatchStatus.SCHEDULED,
                 now={"attempts": 3, "first_attempt_at": "2026-10-04T18:00:00+00:00",
                      "last_attempt_at": "2026-10-05T10:00:00.000000+00:00",
                      "archive": {"rows": 0, "state": "empty", "asked_at": "2026-10-05T10:00:00.000000+00:00"},
                      "last_outcome": "fresh_unanswered", "last_outcome_at": "2026-10-05T10:00:00+00:00"},
                 dump=None),
}

#: Rows Live Score's last real answers synced: (competition, kickoff, last_synced_at).
SYNCED = [
    (FRIENDLIES, datetime(2026, 9, 28, 16, 0), "2026-10-01T07:16:21.951000+00:00"),
    (FRIENDLIES, datetime(2026, 9, 28, 18, 0), "2026-10-01T07:16:22.210000+00:00"),
    (FRIENDLIES, datetime(2026, 9, 28, 9, 0), "2026-09-28T12:38:00.000000+00:00"),   # an earlier sync
    (FRIENDLIES, datetime(2026, 9, 24, 12, 0), "2026-10-01T07:46:51.800000+00:00"),
    (FRIENDLIES, datetime(2026, 9, 29, 18, 0), "2026-09-29T22:47:12.500000+00:00"),
    (FRIENDLIES, datetime(2026, 9, 29, 20, 0), "2026-09-29T22:47:13.100000+00:00"),
    (AFCON_Q, datetime(2026, 9, 25, 13, 0), "2026-10-01T07:46:53.321322+00:00"),
    (AFCON_Q, datetime(2026, 9, 25, 13, 1), "2026-10-01T07:46:53.344409+00:00"),
    (AFCON_Q, datetime(2026, 9, 25, 16, 0), "2026-10-01T07:46:53.377822+00:00"),
    (UNL, datetime(2026, 9, 28, 16, 0), "2026-09-28T21:31:41.900000+00:00"),
    (UNL, datetime(2026, 9, 28, 18, 0), "2026-09-28T21:31:42.100000+00:00"),
    (UNL, datetime(2026, 9, 28, 20, 0), "2026-09-28T21:31:42.600000+00:00"),
]


# ----------------------------------------------------------------------------- database
@pytest.fixture(scope="module")
def engine():
    try:
        eng = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
        with eng.connect() as conn:
            for schema in ("users", "predictions", "ml_models", "analytics", "audit"):
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL test database not reachable: {exc}")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session joined to an outer transaction; nothing a test writes survives it."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _copy_field(value) -> str:
    """A value as pg_dump writes it in COPY text format."""
    if value is None:
        return r"\N"
    return (str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
            .replace("\r", "\\r"))


@pytest.fixture
def store(db, tmp_path):
    """The rows above in the database, the dump and the capture on disk, and the ids to find them."""
    registry = MatchRegistry(db)
    leagues = {}
    for key in (FRIENDLIES, AFCON_Q, UNL, CLUB):
        league = registry.ensure_canonical_league(key)
        meta = dict(league.league_metadata or {})
        meta["archive_observations"] = copy.deepcopy(OBS_NOW.get(key, {}))
        league.league_metadata = meta
        leagues[key] = league
    db.flush()

    def team(name: str) -> Team:
        row = Team(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:6]}", country="World",
                   team_scope="national_senior_men")
        db.add(row)
        return row

    matches, dumped = {}, {}
    for label, spec in FIXTURES.items():
        home, away = team(f"{label} home"), team(f"{label} away")
        db.flush()
        meta = {"recovery": copy.deepcopy(spec["now"]), "provider": "livescore",
                "last_synced_at": "2026-09-20T10:00:00+00:00"}
        if spec.get("relisted"):
            meta[repair.RELISTED_KEY] = {"match_id": str(uuid.uuid4()), "reason": "listed again"}
        match = Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id,
                      league_id=leagues[spec["key"]].id, match_date=spec["kickoff"], status=spec["status"],
                      match_metadata=meta)
        db.add(match)
        matches[label] = match
        if spec["dump"] is not None:
            dumped[match.id] = {"recovery": spec["dump"]}
    for key, kickoff, synced in SYNCED:
        home, away = team("synced home"), team("synced away")
        db.flush()
        db.add(Match(id=uuid.uuid4(), home_team_id=home.id, away_team_id=away.id,
                     league_id=leagues[key].id, match_date=kickoff, status=MatchStatus.FINISHED,
                     match_metadata={"provider": "livescore", "last_synced_at": synced}))
    db.flush()

    dump_path = tmp_path / "before.sql.gz"
    with gzip.open(dump_path, "wt", encoding="utf-8") as handle:
        handle.write("--\n-- PostgreSQL database dump\n--\n\n")
        handle.write("COPY predictions.leagues (name, league_metadata, id) FROM stdin;\n")
        for key, league in leagues.items():
            meta = {"canonical_key": key, "note": "a\ttab, a \"quote\" and a back\\slash",
                    "archive_observations": OBS_DUMP.get(key, {})}
            handle.write("\t".join(_copy_field(v) for v in (league.name, json.dumps(meta), league.id)) + "\n")
        handle.write("\\.\n\n")
        handle.write("COPY predictions.matches (league_id, match_date, match_metadata, id) FROM stdin;\n")
        for match_id, meta in dumped.items():
            handle.write("\t".join(_copy_field(v) for v in ("x", "2026-09-30 04:00:00", json.dumps(meta),
                                                            match_id)) + "\n")
        handle.write("\\.\n")
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(CAPTURE), encoding="utf-8")
    prior = repair.PriorDump.load(str(dump_path))
    capture, _ = repair.load_capture(str(capture_path))
    return {"leagues": leagues, "matches": matches, "prior": prior, "capture": capture,
            "dump_path": dump_path}


def plan(db, store, **options):
    options.setdefault("reconstruct", True)
    return repair.plan_repair(db, cut=CUT, prior=store["prior"], capture=store["capture"], now=NOW,
                              sha="test", **options)


def observation(plan_, key, day):
    return next(f for f in plan_.observations if f.key == key and f.day == day)


def fixture(plan_, store, label):
    return next(f for f in plan_.fixtures if f.match_id == store["matches"][label].id)


def row_hashes(db, table: str):
    return dict(db.execute(text(
        f"SELECT id::text, md5(to_jsonb(t)::text) FROM predictions.{table} t")).fetchall())


def row_hashes_without(db, table: str, column: str):
    return dict(db.execute(text(
        f"SELECT id::text, md5((to_jsonb(t) - '{column}' - 'updated_at')::text) FROM predictions.{table} t"
    )).fetchall())


# ----------------------------------------------------------------------------- reading the records
def test_the_dump_is_read_back_exactly_including_escapes(store):
    prior = store["prior"]
    friendlies = store["leagues"][FRIENDLIES]
    assert prior.observation(friendlies.id, "2026-09-30") == OBS_DUMP[FRIENDLIES]["2026-09-30"]
    assert prior.recovery_of(store["matches"]["B"].id) == FIXTURES["B"]["dump"]
    assert prior.recovery_of(store["matches"]["A"].id) is None


def test_the_capture_is_read_as_it_stood_at_0315(store):
    entry = store["capture"][("Africa Cup of Nations Qualifications", "2026-09-25")]
    assert entry == {"state": "empty", "rows": 0, "asked_at": "2026-10-02T08:12:01.530199+00:00",
                     "provider": "api_football", "times_asked": 30,
                     "first_asked_at": "2026-09-25T21:53:51.987276+00:00"}
    assert "last_answered_at" not in store["capture"][("National Teams Friendlies", "2026-09-24")], (
        "added to the capture later, from another read: not part of the state at 03:15")


# ----------------------------------------------------------------------------- the plan
def test_rows_are_selected_and_classified_by_rule(db, store):
    p = plan(db, store)
    assert {(f.key, f.day): f.cls for f in p.observations} == {
        (FRIENDLIES, "2026-09-24"): 3, (FRIENDLIES, "2026-09-28"): 3, (FRIENDLIES, "2026-09-30"): 2,
        (FRIENDLIES, "2026-10-03"): 1, (AFCON_Q, "2026-09-25"): 3,
        (UNL, "2026-10-03"): 1, (UNL, "2026-10-04"): 1,
    }
    labels = ("A", "A2", "B", "C", "C_legacy", "C_relisted")
    groups = {label: fixture(p, store, label).group for label in labels}
    assert groups == {"A": "A", "A2": "A", "B": "B", "C": "C", "C_legacy": "C", "C_relisted": "C"}
    planned = {f.match_id for f in p.fixtures}
    for untouched in ("genuine", "club"):
        assert store["matches"][untouched].id not in planned
    assert p.skipped == []
    assert p.validation == {"checked": 2, "agree": 2, "disagree": []}


def test_observation_after_states(db, store):
    p = plan(db, store)
    entry = OBS_NOW[FRIENDLIES]
    # class 1: removed; a genuine failure on it stays and nothing else does
    assert observation(p, FRIENDLIES, "2026-10-03").after is None
    assert observation(p, UNL, "2026-10-04").after is None
    assert observation(p, UNL, "2026-10-03").after == {
        "last_failed_at": "2026-10-07T01:04:45.307108+00:00",
        "last_failure": "livescore: authentication rejected (HTTP 401)"}
    assert observation(p, FRIENDLIES, "2026-10-03").removed_asks == 4
    # class 2: Live Score's answer back, the failure since kept, the count unverified
    assert observation(p, FRIENDLIES, "2026-09-30").after == {
        **OBS_DUMP[FRIENDLIES]["2026-09-30"],
        "last_failed_at": "2026-10-07T01:04:45.307108+00:00",
        "last_failure": "livescore: authentication rejected (HTTP 401)",
        "count_quality": "unverified", "times_asked_at_correction": 29, "count_quality_as_of": STAMP}
    # class 3: the count at the cut less the proven not-answer, the state reconstructed
    assert observation(p, FRIENDLIES, "2026-09-28").after == {
        "rows": 2, "state": "answered", "asked_at": "2026-10-01T07:16:22.276377+00:00",
        "provider": "livescore", "times_asked": 23, "first_asked_at": entry["2026-09-28"]["first_asked_at"],
        "last_answered_at": "2026-10-01T07:16:22.276377+00:00", "reconstructed": True,
        "count_quality": "upper_bound", "times_asked_at_correction": 23, "count_quality_as_of": STAMP}
    assert observation(p, FRIENDLIES, "2026-09-28").evidence["at_cut_source"] == "dump"
    afcon = observation(p, AFCON_Q, "2026-09-25")
    assert afcon.evidence["at_cut_source"] == "capture"
    assert (afcon.after["state"], afcon.after["rows"], afcon.after["times_asked"]) == ("answered", 3, 29)
    assert afcon.removed_asks == 2 and afcon.window_false == 1 and afcon.proven_pre_window == 1
    assert observation(p, FRIENDLIES, "2026-09-24").after["times_asked"] == 15


def test_fixture_after_states(db, store):
    p = plan(db, store)
    matches = store["matches"]

    def expected(label, **changes):
        after = {k: v for k, v in copy.deepcopy(FIXTURES[label]["now"]).items()}
        for k, v in changes.items():
            if v is None:
                after.pop(k, None)
            else:
                after[k] = v
        upcoming = _next_ask_from(after, matches[label].match_date, NOW)
        after["next_ask_after"] = upcoming.isoformat()
        return after

    def without_audit(fix):
        audit = ("corrections", "attempts_quality", "attempts_at_correction", "attempts_quality_as_of")
        return {k: v for k, v in fix.after.items() if k not in audit}

    a = fixture(p, store, "A")
    assert without_audit(a) == expected("A", attempts=None, first_attempt_at=None, last_attempt_at=None,
                                        archive=None)
    assert (a.after["attempts_quality"], a.after["attempts_at_correction"]) == ("exact", 0)
    assert a.after["next_ask_after"] == STAMP, "never really asked: due now"
    assert a.after["deferrals"] == 3 and a.after["last_outcome"] == "deferred"

    a2 = fixture(p, store, "A2")
    assert without_audit(a2) == expected("A2", attempts=None, first_attempt_at=None, last_attempt_at=None,
                                         archive=None, last_outcome=None, last_outcome_at=None,
                                         last_outcome_detail=None)

    b = fixture(p, store, "B")
    dump = FIXTURES["B"]["dump"]
    assert without_audit(b) == expected("B", attempts=29, last_attempt_at=dump["last_attempt_at"],
                                        archive=dump["archive"])
    assert (b.after["attempts_quality"], b.after["attempts_at_correction"]) == ("unverified", 29)
    assert b.after["deferrals"] == 4, "the deferrals since are genuine and stay"

    c = fixture(p, store, "C")
    reconstructed = {"state": "answered", "rows": 2, "asked_at": "2026-10-01T07:16:22.276377+00:00",
                     "reconstructed": True}
    assert without_audit(c) == expected("C", attempts=23, last_attempt_at="2026-10-01T07:16:22.276377+00:00",
                                        archive=reconstructed)
    assert (c.after["attempts_quality"], c.after["attempts_at_correction"]) == ("upper_bound", 23)

    assert fixture(p, store, "C_legacy").after["attempts"] == 18, (
        "20, less the one after the cut and the proven one")
    assert "first_attempt_at" not in fixture(p, store, "C_legacy").after

    relisted = fixture(p, store, "C_relisted")
    assert relisted.after["attempts"] == 29
    assert relisted.after["last_outcome"] == "fresh_unanswered"
    assert relisted.after["last_outcome_at"] == "2026-10-01T07:46:53.389206+00:00"
    assert relisted.after["last_outcome_detail"].startswith(
        "livescore answered for this competition on 2026-09-25 with 3 row(s), none of them a result")
    assert "reconstructed on 2026-10-07" in relisted.after["last_outcome_detail"]
    assert "next_ask_after" not in relisted.after, "a closed second listing advertises no next ask"

    audit = b.after["corrections"][-1]
    assert audit["by"] == repair.BY and audit["group"] == "B" and audit["removed_attempts"] == 2
    assert audit["replaced"]["attempts"] == 31 and audit["restored_from"] == "dump"
    for fix in p.fixtures:
        assert fix.after["attempts_quality_as_of"] == STAMP
        for untouched in ("status", "home_score", "result"):
            assert untouched not in fix.after


def test_without_reconstruction_only_the_counts_change(db, store):
    p = plan(db, store, reconstruct=False)
    obs = observation(p, FRIENDLIES, "2026-09-28")
    for k in ("state", "rows", "asked_at", "provider"):
        assert obs.after[k] == OBS_NOW[FRIENDLIES]["2026-09-28"][k]
    assert (obs.after["times_asked"], obs.after["count_quality"]) == (23, "upper_bound")
    assert "reconstructed" not in obs.after
    c = fixture(p, store, "C")
    assert c.after["attempts"] == 23
    assert c.after["last_attempt_at"] == FIXTURES["C"]["now"]["last_attempt_at"]
    assert c.after["archive"] == FIXTURES["C"]["now"]["archive"]
    relisted = fixture(p, store, "C_relisted")
    assert "last_outcome" not in relisted.after, "the not-answer's sentence goes, with nothing invented"


def test_the_proven_not_answer_is_kept_on_request(db, store):
    p = plan(db, store, subtract_proven=False)
    assert observation(p, FRIENDLIES, "2026-09-28").after["times_asked"] == 24
    assert fixture(p, store, "C").after["attempts"] == 24
    assert fixture(p, store, "C_legacy").after["attempts"] == 19
    assert fixture(p, store, "C_relisted").after["attempts"] == 30
    assert fixture(p, store, "B").after["attempts"] == 29, "nothing proven before the cut on a class-2 day"


def test_closed_relistings_can_be_left_alone(db, store):
    p = plan(db, store, skip_closed_relistings=True)
    assert store["matches"]["C_relisted"].id not in {f.match_id for f in p.fixtures}
    assert [s["match_id"] for s in p.skipped] == [str(store["matches"]["C_relisted"].id)]


def test_reconstruction_is_refused_when_the_method_disagrees(db, store):
    league = store["leagues"][UNL]
    meta = copy.deepcopy(league.league_metadata)
    meta["archive_observations"]["2026-09-28"]["rows"] = 4    # three rows were synced, not four
    league.league_metadata = meta
    db.flush()
    p = plan(db, store)
    assert p.validation["disagree"] == [{"league": "UEFA Nations League", "date": "2026-09-28",
                                         "rows": 4, "synced": 3}]
    assert "agrees with 1 of 2" in p.options["reconstruction_refused"]
    assert not any(f.reconstructed for f in p.observations)
    assert observation(p, FRIENDLIES, "2026-09-28").after["state"] == "empty"


def test_a_fixture_whose_evidence_disagrees_is_left_alone(db, store):
    match = store["matches"]["B"]
    state = recovery_state_of(match)
    state["attempts"] = 33                                    # two more than its day's not-answers allow
    match.match_metadata = {**match.match_metadata, "recovery": state}
    db.flush()
    p = plan(db, store)
    assert match.id not in {f.match_id for f in p.fixtures}
    assert "since the dump the fixture moved 4 and its day 2" in p.skipped[0]["reason"]


def test_a_live_score_answer_after_the_cut_stops_the_plan(db, store):
    league = store["leagues"][UNL]
    meta = copy.deepcopy(league.league_metadata)
    meta["archive_observations"]["2026-10-05"] = {
        "rows": 2, "state": "answered", "asked_at": "2026-10-08T10:00:00+00:00", "provider": "livescore",
        "times_asked": 1, "first_asked_at": "2026-10-08T10:00:00+00:00",
        "last_answered_at": "2026-10-08T10:00:00+00:00"}
    league.league_metadata = meta
    db.flush()
    with pytest.raises(repair.PlanChanged, match="this plan no longer holds"):
        plan(db, store)


def test_live_score_answering_any_competition_after_the_cut_stops_the_plan(db, store):
    league = store["leagues"][CLUB]
    meta = copy.deepcopy(league.league_metadata)
    meta["archive_observations"]["2026-10-07"] = {
        "rows": 4, "state": "answered", "asked_at": "2026-10-08T09:00:00+00:00", "provider": "livescore",
        "times_asked": 1, "first_asked_at": "2026-10-08T09:00:00+00:00"}
    league.league_metadata = meta
    db.flush()
    with pytest.raises(repair.PlanChanged, match="Premier League 2026-10-07: livescore is recorded answering"):
        plan(db, store)


def test_a_row_live_score_synced_after_the_cut_stops_the_plan(db, store):
    match = store["matches"]["club"]
    match.match_metadata = {**match.match_metadata, "last_synced_at": "2026-10-08T09:00:00+00:00"}
    db.flush()
    with pytest.raises(repair.PlanChanged, match="1 match row livescore synced after"):
        plan(db, store)


def test_a_cut_moved_past_the_not_answers_stops_the_plan(db, store):
    """Live Score's first success once access returns moves Redis's `last_success_at`. Planned with
    that instant, every not-answer before it reads as genuine and the plan shrinks to a few rows
    without a word; the records themselves say the cut is wrong."""
    match = store["matches"]["club"]
    match.match_metadata = {**match.match_metadata, "last_synced_at": "2026-10-08T09:59:59+00:00"}
    db.flush()
    moved = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(repair.PlanChanged, match="before the 2026-10-08T10:00:00\\+00:00 given as Live Score's"):
        repair.plan_repair(db, cut=moved, prior=store["prior"], capture=store["capture"], now=NOW, sha="test")


def test_a_write_takes_the_cut_a_person_pinned_and_redis_must_agree_with_it():
    moved = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    cut, source, why = repair.choose_cut(None, CUT, apply=True)
    assert cut is None and "--apply needs --livescore-last-success" in why
    assert repair.choose_cut(CUT, CUT, apply=True) == (CUT, "given; Redis agrees", None)
    cut, source, why = repair.choose_cut(CUT, moved, apply=True)
    assert cut is None and "Live Score has answered since" in why and "has ended" in why
    cut, source, why = repair.choose_cut(CUT, moved, apply=False)
    assert cut is None, "a report on a moved cut would print a plan that no longer holds"
    cut, source, why = repair.choose_cut(moved, CUT, apply=False)
    assert cut is None and "later than Live Score's last success" in why
    assert repair.choose_cut(CUT, None, apply=True) == (CUT, "given; Redis holds none to check it against", None)
    cut, source, why = repair.choose_cut(None, CUT, apply=False)
    assert (cut, why) == (CUT, None) and "not pinned" in source
    assert repair.choose_cut(None, None, apply=False)[0] is None


# ----------------------------------------------------------------------------- applying it
def test_apply_writes_the_plan_and_nothing_else(db, store):
    counts_before = {t: db.execute(text(f"SELECT count(*) FROM predictions.{t}")).scalar()
                     for t in ("leagues", "matches", "teams", "provider_entity_refs")}
    hashes = {t: row_hashes(db, t) for t in ("leagues", "matches")}
    other_columns = {"leagues": row_hashes_without(db, "leagues", "league_metadata"),
                     "matches": row_hashes_without(db, "matches", "match_metadata")}
    p = plan(db, store)

    assert repair.apply_plan(db, p) == {"observations": 7, "fixtures": 6}

    targets = {"leagues": {str(f.league_id) for f in p.observations},
               "matches": {str(f.match_id) for f in p.fixtures}}
    for table, column in (("leagues", "league_metadata"), ("matches", "match_metadata")):
        after = row_hashes(db, table)
        assert set(after) == set(hashes[table])
        for row_id, digest in hashes[table].items():
            if row_id not in targets[table]:
                assert after[row_id] == digest, f"{table} {row_id} is outside the plan and changed"
        assert row_hashes_without(db, table, column) == other_columns[table], (
            f"only {column} and updated_at may change on {table}")
    for t, n in counts_before.items():
        assert db.execute(text(f"SELECT count(*) FROM predictions.{t}")).scalar() == n

    for fix in p.fixtures:
        stored = db.execute(text("SELECT match_metadata->'recovery' FROM predictions.matches WHERE id = :i"),
                            {"i": str(fix.match_id)}).scalar()
        assert stored == fix.after
    for fix in p.observations:
        stored = db.execute(text("SELECT league_metadata->'archive_observations'->:d FROM predictions.leagues "
                                 "WHERE id = :i"), {"i": str(fix.league_id), "d": fix.day}).scalar()
        assert stored == fix.after
    audits = db.execute(text("SELECT league_metadata->'archive_corrections' FROM predictions.leagues "
                             "WHERE id = :i"), {"i": str(store["leagues"][FRIENDLIES].id)}).scalar()
    assert sorted(a["date"] for a in audits) == ["2026-09-24", "2026-09-28", "2026-09-30", "2026-10-03"]
    assert {a["by"] for a in audits} == {repair.BY}
    removed = next(a for a in audits if a["date"] == "2026-10-03")
    assert removed["replaced"] == OBS_NOW[FRIENDLIES]["2026-10-03"] and removed["class"] == 1


def test_a_second_apply_changes_nothing(db, store):
    repair.apply_plan(db, plan(db, store))
    hashes = {t: row_hashes(db, t) for t in ("leagues", "matches")}
    again = plan(db, store)
    assert (again.observations, again.fixtures, again.skipped) == ([], [], [])
    # A restored or reconstructed entry no longer reads as false, and a removed one is gone; the six
    # fixtures are found false by their stamps no more either, and carry this script's record.
    assert again.already_corrected == 6
    assert repair.apply_plan(db, again) == {"observations": 0, "fixtures": 0}
    assert {t: row_hashes(db, t) for t in ("leagues", "matches")} == hashes
    # Without reconstruction a class-3 entry still names the not-answer's provider; it is still skipped.
    assert plan(db, store, reconstruct=False).observations == []


def test_a_row_changed_between_plan_and_apply_stops_everything(db, store):
    p = plan(db, store)
    hashes = {t: row_hashes(db, t) for t in ("leagues", "matches")}
    match = store["matches"]["B"]
    state = recovery_state_of(match)
    state["deferrals"] = 5                                   # a pass ran in between
    match.match_metadata = {**match.match_metadata, "recovery": state}
    db.flush()
    hashes["matches"][str(match.id)] = row_hashes(db, "matches")[str(match.id)]
    with pytest.raises(repair.PlanChanged, match=str(match.id)):
        repair.apply_plan(db, p)
    assert {t: row_hashes(db, t) for t in ("leagues", "matches")} == hashes, "nothing was written"


def test_a_fixture_written_back_after_the_repair_is_planned_again(db, store):
    """A pass that read a fixture before the repair committed and wrote it after puts the false
    JSONB back without this script's record. Its day is corrected and no longer reads as false,
    so the re-run rebuilds that day's fix from the audit and plans the fixture against it."""
    first = plan(db, store)
    repair.apply_plan(db, first)
    for label in ("A", "B", "C"):
        match = store["matches"][label]
        db.refresh(match)
        match.match_metadata = {**match.match_metadata, "recovery": copy.deepcopy(FIXTURES[label]["now"])}
    db.flush()

    again = plan(db, store)
    assert again.observations == [] and again.skipped == []
    assert {f.match_id for f in again.fixtures} == {store["matches"][label].id for label in ("A", "B", "C")}
    for label in ("A", "B", "C"):
        fix = fixture(again, store, label)
        assert fix.after == fixture(first, store, label).after, f"{label} is corrected as it was the first time"
        assert fix.evidence["observation"]["corrected_earlier_at"] == STAMP
    repair.apply_plan(db, again)
    assert plan(db, store).fixtures == [], "and then it is done"


def test_an_observation_written_back_after_the_repair_is_planned_again(db, store):
    repair.apply_plan(db, plan(db, store, reconstruct=False))
    kept = plan(db, store, reconstruct=False)
    assert kept.observations == [], "a class-3 entry kept without reconstruction is still false, and done"
    league = store["leagues"][FRIENDLIES]
    db.refresh(league)
    meta = copy.deepcopy(league.league_metadata)
    meta["archive_observations"]["2026-09-28"] = copy.deepcopy(OBS_NOW[FRIENDLIES]["2026-09-28"])
    league.league_metadata = meta
    db.flush()
    again = plan(db, store, reconstruct=False)
    assert [(f.key, f.day, f.cls) for f in again.observations] == [(FRIENDLIES, "2026-09-28", 3)]
    assert observation(again, FRIENDLIES, "2026-09-28").after["times_asked"] == 23


def test_blocked_by_us_sees_a_session_waiting_on_a_lock_this_one_holds(engine):
    """What the last look before COMMIT counts: a session that would write once the repair commits."""
    key = 7_340_201
    with engine.connect() as ours:
        ours.begin()
        ours.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        session = sessionmaker(bind=ours)()
        assert repair.blocked_by_us(session) == 0
        waiting = threading.Thread(target=_wait_for_lock, args=(engine, key))
        waiting.start()
        try:
            for _ in range(50):
                if repair.blocked_by_us(session):
                    break
                threading.Event().wait(0.1)
            assert repair.blocked_by_us(session) == 1
        finally:
            ours.rollback()
            waiting.join(timeout=10)
        assert not waiting.is_alive()


def _wait_for_lock(engine, key):
    with engine.connect() as theirs:
        theirs.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        theirs.rollback()


def test_a_reason_found_just_before_commit_rolls_everything_back(db, store):
    db.commit()                                   # the rows above stay; only the repair is undone
    p = plan(db, store)
    hashes = {t: row_hashes(db, t) for t in ("leagues", "matches")}
    with pytest.raises(repair.PlanChanged, match="just before COMMIT: 127.0.0.1:8000 accepts connections"):
        repair.commit_plan(db, p, lambda: ["127.0.0.1:8000 accepts connections"])
    assert {t: row_hashes(db, t) for t in ("leagues", "matches")} == hashes, "nothing was written"
    assert repair.commit_plan(db, plan(db, store), lambda: []) == {"observations": 7, "fixtures": 6}


def test_a_later_attempt_keeps_the_markers(db, store):
    repair.apply_plan(db, plan(db, store))
    match = store["matches"]["C"]
    db.refresh(match)
    later = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    state = MatchRegistry(db).record_recovery_attempt(match, later)
    assert state["attempts"] == 24
    assert (state["attempts_quality"], state["attempts_at_correction"], state["attempts_quality_as_of"]) == (
        "upper_bound", 23, STAMP)
    assert state["corrections"][-1]["by"] == repair.BY
    assert state["last_attempt_at"] == later.isoformat()


# ----------------------------------------------------------------------------- refusals and the report
def test_the_live_database_is_refused_without_the_owners_approval():
    reason = repair.refusal("soccer_predictions", apply=True, owner_approved=False, other_clients=0,
                            stopped_backend=True)
    assert reason and "live database" in reason
    assert repair.refusal("soccer_predictions", apply=True, owner_approved=True, other_clients=0,
                          stopped_backend=True) is None
    assert repair.refusal("soccer_predictions", apply=False, owner_approved=False, other_clients=3,
                          stopped_backend=False) is None, "a report writes nothing"
    assert repair.refusal("soccer_predictions_rehearsal_notanswers", apply=True, owner_approved=False,
                          other_clients=0, stopped_backend=False) is None


def test_the_backends_database_needs_the_backend_stopped_whatever_pg_stat_activity_shows():
    # The development backend's engine uses NullPool: between passes it holds no connection, so the
    # count of other clients is 0 while its scheduler is running. 0 must not read as "stopped".
    reason = repair.refusal("soccer_predictions", apply=True, owner_approved=True, other_clients=0,
                            stopped_backend=False)
    assert reason and "--i-stopped-the-backend" in reason and "pg_stat_activity proves nothing" in reason
    configured = repair.refusal("soccer_predictions_dev", apply=True, owner_approved=False, other_clients=0,
                                stopped_backend=False, application_database=True)
    assert configured and "the database the backend uses" in configured
    assert repair.LIVE_DATABASE in repair.application_databases()


def test_signs_of_a_running_backend_refuse_even_with_the_flag():
    signs = ["127.0.0.1:8000 accepts connections (the backend, and the scheduler inside it, look up)"]
    reason = repair.refusal("soccer_predictions", apply=True, owner_approved=True, other_clients=0,
                            stopped_backend=True, application_database=True, backend_signs=signs)
    assert reason and "looks alive, whatever --i-stopped-the-backend says" in reason and signs[0] in reason


class FakeCache:
    """The scheduler's Redis records, as `MatchCache` reads them."""

    def __init__(self, values=None, available=True):
        self.values, self.available = dict(values or {}), available

    def keys(self, pattern):
        return [k for k in self.values if fnmatch.fnmatchcase(k, pattern)]

    def get(self, key):
        return self.values.get(key)


def test_backend_signs_read_the_address_the_locks_and_the_last_ticks():
    quiet = {"sync:task:settle": {"last_run_at": "2026-10-07T02:15:06.218165+00:00"},
             "sync:task:recover": {"last_run_at": "2026-10-07T02:05:06.122607+00:00",
                                   "last_skipped_at": None}}
    now = datetime(2026, 10, 7, 2, 21, tzinfo=timezone.utc)
    down = lambda address: None                                              # noqa: E731
    assert repair.backend_signs(FakeCache(quiet), now=now, probe=down) == []

    up = lambda address: f"{address} accepts connections"                    # noqa: E731
    assert repair.backend_signs(FakeCache(quiet), addresses=["127.0.0.1:8000", "127.0.0.1:8001"], now=now,
                                probe=up) == ["127.0.0.1:8000 accepts connections",
                                              "127.0.0.1:8001 accepts connections"]
    locked = dict(quiet, **{"sync:lock:recover": "token"})
    assert repair.backend_signs(FakeCache(locked), now=now, probe=down) == [
        "a sync pass holds sync:lock:recover right now"]
    ticked = dict(quiet, **{"sync:task:settle": {"last_run_at": (now - timedelta(seconds=50)).isoformat()}})
    signs = repair.backend_signs(FakeCache(ticked), now=now, probe=down)
    assert len(signs) == 1 and "sync:task:settle" in signs[0] and "50 s ago" in signs[0]
    assert repair.backend_signs(FakeCache(available=False), now=now, probe=down) == [
        "Redis could not be read, so nothing shows the scheduler stopped"]


def test_the_address_probe_tells_a_listening_port_from_a_closed_one():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    address = f"127.0.0.1:{server.getsockname()[1]}"
    try:
        assert "accepts connections" in (repair._listening(address) or "")
    finally:
        server.close()
    assert repair._listening(address) is None, "refused: nothing listens there any more"


def test_a_database_another_client_is_using_is_refused():
    reason = repair.refusal("soccer_predictions_copy", apply=True, owner_approved=False, other_clients=2,
                            stopped_backend=False)
    assert reason and "2 other clients are connected" in reason and "--i-stopped-the-backend" in reason
    assert repair.refusal("soccer_predictions_copy", apply=True, owner_approved=False, other_clients=2,
                          stopped_backend=True) is None


def test_the_report_has_a_line_per_row(db, store):
    p = plan(db, store)
    lines = [json.loads(json.dumps(line, default=str))
             for line in repair.report_lines(p, "postgresql://x:***@h/db")]
    assert lines[0]["kind"] == "plan" and lines[0]["livescore_last_success"] == CUT.isoformat()
    assert [line["kind"] for line in lines[1:]].count("observation") == 7
    assert [line["kind"] for line in lines[1:]].count("fixture") == 6
    for line in lines[1:]:
        assert {"before", "after", "evidence"} <= set(line)

    left = plan(db, store, skip_closed_relistings=True)
    skipped = [line for line in repair.report_lines(left, "db") if line["kind"] == "skipped"]
    assert skipped == [{"kind": "skipped", "row": "fixture", "match_id": str(store["matches"]["C_relisted"].id),
                        "league": "Africa Cup of Nations Qualifications", "date": "2026-09-25",
                        "reason": "a closed second listing, left as it is (--skip-closed-relistings)"}]
