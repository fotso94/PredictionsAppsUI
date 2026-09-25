"""
Settling selections against stored results, on the results this installation really holds.

tests/fixtures/results_2026-09-25.jsonl are two UEFA Nations League results as stored on 2026-09-25:
Georgia 0-1 N.Ireland (half time 0-0) and Armenia 2-0 Latvia (half time 1-0), both with a
regulation-time score and a half-time score. The rules are the settlement module's own
(regulation time only; extra time and penalties settle nothing), and every "cannot settle" case is
left unresolved with its reason rather than guessed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.predictions import MatchStatus
from app.services import slip_settlement as ss
from app.services.markets import (
    AWAY_TEAM_GOALS, BOTH_TEAMS_SCORE, DOUBLE_CHANCE, DRAW_NO_BET, EXACT_SCORE, FIRST_HALF_RESULT, HOME_TEAM_GOALS,
    MATCH_RESULT, TEAM_TO_SCORE_FIRST, TOTAL_GOALS,
)

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def stored_results():
    with open(os.path.join(FIXTURES, "results_2026-09-25.jsonl"), encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {row["home"]: row for row in rows}


def result_of(row: dict, **overrides):
    fields = {"home_score": row["home_score"], "away_score": row["away_score"],
              "home_score_ht": row["home_score_ht"], "away_score_ht": row["away_score_ht"],
              "home_score_ft": row["home_score_ft"], "away_score_ft": row["away_score_ft"],
              "home_score_et": None, "away_score_et": None, "home_score_pens": None, "away_score_pens": None,
              "result_metadata": row["result_metadata"]}
    fields.update(overrides)
    return SimpleNamespace(**fields)


GEORGIA = stored_results()["Georgia"]     # 0-1, HT 0-0
ARMENIA = stored_results()["Armenia"]     # 2-0, HT 1-0


@pytest.mark.parametrize("market,outcome,line,expected", [
    (MATCH_RESULT, "away", None, "won"), (MATCH_RESULT, "home", None, "lost"), (MATCH_RESULT, "draw", None, "lost"),
    (DOUBLE_CHANCE, "x2", None, "won"), (DOUBLE_CHANCE, "12", None, "won"), (DOUBLE_CHANCE, "1x", None, "lost"),
    (DRAW_NO_BET, "away", None, "won"), (DRAW_NO_BET, "home", None, "lost"),
    (TOTAL_GOALS, "over", 0.5, "won"), (TOTAL_GOALS, "under", 1.5, "won"), (TOTAL_GOALS, "over", 2.5, "lost"),
    (HOME_TEAM_GOALS, "under", 0.5, "won"), (HOME_TEAM_GOALS, "over", 0.5, "lost"),
    (AWAY_TEAM_GOALS, "over", 0.5, "won"), (AWAY_TEAM_GOALS, "over", 1.5, "lost"),
    (BOTH_TEAMS_SCORE, "no", None, "won"), (BOTH_TEAMS_SCORE, "yes", None, "lost"),
    (EXACT_SCORE, "0-1", None, "won"), (EXACT_SCORE, "1-0", None, "lost"),
    (FIRST_HALF_RESULT, "draw", None, "won"), (FIRST_HALF_RESULT, "away", None, "lost"),
])
def test_georgia_0_1_northern_ireland_settles_every_regulation_and_half_time_market(market, outcome, line, expected):
    entry = ss.settle_selection(market, outcome, line, MatchStatus.FINISHED, result_of(GEORGIA))
    assert entry["state"] == expected, entry
    assert entry["rules_version"] == ss.RULES_VERSION


def test_armenia_2_0_latvia_first_half_and_team_totals():
    result = result_of(ARMENIA)
    assert ss.settle_selection(FIRST_HALF_RESULT, "home", None, MatchStatus.FINISHED, result)["state"] == "won"
    assert ss.settle_selection(FIRST_HALF_RESULT, "draw", None, MatchStatus.FINISHED, result)["state"] == "lost"
    assert ss.settle_selection(HOME_TEAM_GOALS, "over", 1.5, 	MatchStatus.FINISHED, result)["state"] == "won"
    assert ss.settle_selection(AWAY_TEAM_GOALS, "under", 0.5, MatchStatus.FINISHED, result)["state"] == "won"
    assert ss.settle_selection(TOTAL_GOALS, "under", 2.5, MatchStatus.FINISHED, result)["state"] == "won"
    entry = ss.settle_selection(EXACT_SCORE, "2-0", None, MatchStatus.FINISHED, result)
    assert entry["state"] == "won" and entry["actual"] == "2-0"


def test_draw_no_bet_is_void_on_a_draw_and_says_so():
    result = result_of(GEORGIA, home_score=1, away_score=1, home_score_ft=1, away_score_ft=1)
    entry = ss.settle_selection(DRAW_NO_BET, "home", None, MatchStatus.FINISHED, result)
    assert entry["state"] == "void"
    assert "draw" in entry["rule"]


def test_a_first_half_market_without_a_stored_half_time_score_is_unresolved_not_guessed():
    result = result_of(GEORGIA, home_score_ht=None, away_score_ht=None)
    entry = ss.settle_selection(FIRST_HALF_RESULT, "draw", None, MatchStatus.FINISHED, result)
    assert entry["state"] == "unresolved"
    assert "no half-time score is stored" in entry["reason"]
    # The final score decides nothing about the first half
    assert ss.settle_selection(MATCH_RESULT, "away", None, MatchStatus.FINISHED, result)["state"] == "won"


def test_team_to_score_first_is_unresolved_unless_nobody_scored():
    entry = ss.settle_selection(TEAM_TO_SCORE_FIRST, "away", None, MatchStatus.FINISHED, result_of(GEORGIA))
    assert entry["state"] == "unresolved"
    assert "order of goals" in entry["rule"]
    goalless = result_of(GEORGIA, home_score=0, away_score=0, home_score_ft=0, away_score_ft=0)
    assert ss.settle_selection(TEAM_TO_SCORE_FIRST, "neither", None, MatchStatus.FINISHED, goalless)["state"] == "won"
    assert ss.settle_selection(TEAM_TO_SCORE_FIRST, "home", None, MatchStatus.FINISHED, goalless)["state"] == "lost"


def test_extra_time_and_penalties_settle_nothing():
    """A tie that went past 90 minutes with no regulation score stored is withheld, not read from the final score."""
    beyond = result_of(GEORGIA, home_score=2, away_score=1, home_score_ft=None, away_score_ft=None,
                       home_score_et=2, away_score_et=1, home_score_ht=1, away_score_ht=1)
    entry = ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.FINISHED, beyond)
    assert entry["state"] == "unresolved"
    assert "extra time" in entry["reason"]
    # ...but a stored regulation score is what settles, whatever happened afterwards
    with_ft = result_of(GEORGIA, home_score=2, away_score=1, home_score_ft=1, away_score_ft=1, home_score_et=2, away_score_et=1)
    assert ss.settle_selection(MATCH_RESULT, "draw", None, MatchStatus.FINISHED, with_ft)["state"] == "won"
    assert ss.settle_selection(TOTAL_GOALS, "over", 2.5, None if False else MatchStatus.FINISHED, with_ft)["state"] == "lost"


def test_unplayed_and_unfinished_fixtures():
    assert ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.CANCELLED, None)["state"] == "void"
    assert ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.POSTPONED, None)["state"] == "void"
    assert ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.LIVE, None)["state"] == "pending"
    assert ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.SCHEDULED, None)["state"] == "pending"
    finished_without_score = ss.settle_selection(MATCH_RESULT, "home", None, MatchStatus.FINISHED, None)
    assert finished_without_score["state"] == "unresolved"
    assert "no score is stored" in finished_without_score["reason"]


@pytest.mark.parametrize("states,expected", [
    ([], "pending"),
    (["won", "won"], "won"),
    (["won", "lost"], "lost"),
    (["won", "pending"], "pending"),
    (["won", "void"], "won"),
    (["void", "void"], "void"),
    (["won", "unresolved"], "unresolved"),
    (["lost", "unresolved"], "lost"),
    (["pending", "unresolved"], "pending"),
])
def test_a_slips_state_follows_its_legs(states, expected):
    assert ss.slip_state(states) == expected


def test_the_effective_price_needs_a_price_on_every_non_void_leg():
    leg = lambda odds, state="pending", source="user": SimpleNamespace(odds_value=Decimal(str(odds)) if odds else None,
                                                                        state=state, odds_source=source)
    assert ss.effective_price([leg(2.0), leg(1.5)]) == (Decimal("3.0000"), "user", 0)
    assert ss.effective_price([leg(2.0), leg(None)]) == (None, None, 1)
    assert ss.effective_price([leg(2.0), leg(9.0, state="void")]) == (Decimal("2.0000"), "user", 0)
    assert ss.effective_price([leg(2.0, source="provider_snapshot"), leg(1.5)])[1] == "mixed"
    assert ss.effective_price([]) == (None, None, 0)


def test_settle_leg_never_reopens_a_final_state():
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    leg = SimpleNamespace(state="won", settlement={"state": "won"}, settled_at=None, market_id=MATCH_RESULT,
                          outcome="home", line=None)
    match = SimpleNamespace(status=MatchStatus.FINISHED, result=None)
    assert ss.settle_leg(leg, match, None, now) is False
    assert leg.state == "won"
