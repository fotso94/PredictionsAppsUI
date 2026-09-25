"""
The market contract, read from GENUINE stored GameForecastAPI payloads.

tests/fixtures/gameforecast_event_*.json are ``raw_payload`` rows copied from the local database on
2026-09-25 (UEFA Nations League: Bulgaria v Luxembourg before kickoff, Georgia v N.Ireland and
Armenia v Latvia after their results arrived). Nothing in them is a credential. What these tests
lock down:

* every market the payload carries is served, with the provider's own numbers, and the ones the
  adapter never stored as columns (0.5/1.5 lines, team totals, first half, first scorer) read the
  same way as the five it did;
* a market that is not there, is all zeros, is partial, or does not add up is said to be so and
  nothing is filled in - while a genuine zero inside a valid distribution is kept as zero;
* double chance and draw-no-bet are arithmetic on a complete, consistent 1X2 and carry the
  arithmetic; nothing is derived from the truncated exact-score table;
* the provider's 1X2 prices are attached as a dated provider snapshot and to nothing else;
* every ``recommended_bets`` reference the provider has been seen to write resolves to a served
  selection, and an ambiguous one is refused rather than guessed;
* rebuilding from a snapshot stamps the snapshot's own times, never now.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone

import pytest

from app.services import markets as m

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, f"gameforecast_event_{name}.json"), encoding="utf-8") as handle:
        return json.load(handle)


def by_id(built: dict) -> dict:
    return {s["selection_id"]: s for market in built["markets"] for s in market["selections"]}


def market(built: dict, market_id: str, line=None) -> dict:
    for entry in built["markets"]:
        if entry["market_id"] == market_id and entry["line"] == line:
            return entry
    raise AssertionError(f"{market_id}@{line} not served")


# ----------------------------------------------------------------------- what the payload carries
def test_every_market_in_the_genuine_payload_is_served_with_the_providers_own_numbers():
    built = m.build_markets(load("bulgaria_luxembourg"))
    sel = by_id(built)
    # Bulgaria v Luxembourg, run_at 2026-09-24: home 45 / draw 30 / away 25
    assert sel["match_result:home"]["probability"] == pytest.approx(0.45)
    assert sel["match_result:draw"]["probability"] == pytest.approx(0.30)
    assert sel["match_result:away"]["probability"] == pytest.approx(0.25)
    assert sel["match_result:home"]["probability_source"] == "provider"
    # Lines the adapter never stored as columns are read from the same entry
    assert sel["total_goals:over@0.5"]["probability"] == pytest.approx(0.90)
    assert sel["total_goals:under@1.5"]["probability"] == pytest.approx(0.30)
    assert sel["total_goals:under@2.5"]["probability"] == pytest.approx(0.55)
    assert sel["home_team_goals:over@1.5"]["probability"] == pytest.approx(0.45)
    assert sel["away_team_goals:under@3.5"]["probability"] == pytest.approx(0.98)
    assert sel["both_teams_score:no"]["probability"] == pytest.approx(0.55)
    assert sel["first_half_result:draw"]["probability"] == pytest.approx(0.50)
    assert sel["first_half_result:draw"]["period"] == m.PERIOD_FIRST_HALF
    assert sel["team_to_score_first:neither"]["probability"] == pytest.approx(0.10)
    assert sel["exact_score:1-0"]["probability"] == pytest.approx(0.20)
    assert all(s["available"] for s in sel.values()), [k for k, s in sel.items() if not s["available"]]


def test_the_exact_score_remainder_is_served_beside_the_table_and_never_as_a_selection():
    built = m.build_markets(load("bulgaria_luxembourg"))
    exact = market(built, m.EXACT_SCORE)
    assert exact["remainder"] == pytest.approx(0.01)
    assert not any(s["outcome"] in ("other", "others") for s in exact["selections"])
    # 3_3 was published at 0% and is dropped by the adapter's own rule, with a note saying so
    assert "exact_score:3-3" not in by_id(built)
    assert any(w["code"] == "score_zero_dropped" for w in exact["warnings"])
    # The most likely scoreline comes first
    assert exact["selections"][0]["outcome"] == "1-0"


def test_derived_markets_carry_their_arithmetic_and_come_only_from_a_complete_consistent_1x2():
    built = m.build_markets(load("bulgaria_luxembourg"))
    sel = by_id(built)
    dc = sel["double_chance:1x"]
    assert dc["probability"] == pytest.approx(0.75)
    assert dc["probability_source"] == "calculated"
    assert dc["calculation"]["formula"] == "P(1X) = P(home) + P(draw)"
    assert dc["calculation"]["inputs"] == {"home": pytest.approx(0.45), "draw": pytest.approx(0.30)}
    assert sel["double_chance:12"]["probability"] == pytest.approx(0.70)
    assert sel["double_chance:x2"]["probability"] == pytest.approx(0.55)
    dnb = sel["draw_no_bet:home"]
    assert dnb["probability"] == pytest.approx(0.45 / 0.70)
    assert dnb["settlement"]["rule"].startswith("Settles on the regulation-time score; a draw")
    assert sel["draw_no_bet:away"]["probability"] == pytest.approx(0.25 / 0.70)

    partial = copy.deepcopy(load("bulgaria_luxembourg"))
    del partial["predictions"][0]["match_result"]["draw"]
    built = m.build_markets(partial)
    sel = by_id(built)
    assert sel["match_result:home"]["available"], "a published outcome stays usable when a sibling is missing"
    assert not sel["match_result:draw"]["available"]
    assert not sel["double_chance:1x"]["available"]
    assert "incomplete" in sel["double_chance:1x"]["unavailable_reason"]
    assert not sel["draw_no_bet:home"]["available"]

    inconsistent = copy.deepcopy(load("bulgaria_luxembourg"))
    inconsistent["predictions"][0]["match_result"] = {"home": 60, "draw": 30, "away": 25}
    built = m.build_markets(inconsistent)
    sel = by_id(built)
    assert sel["match_result:home"]["available"], "the provider's numbers are served, not corrected"
    assert any(w["code"] == "sum_out_of_tolerance" for w in market(built, m.MATCH_RESULT)["warnings"])
    assert not sel["double_chance:1x"]["available"], "no arithmetic on a distribution that does not sum to one"


def test_nothing_is_derived_from_the_truncated_exact_score_table():
    built = m.build_markets(load("bulgaria_luxembourg"))
    served = {entry["market_id"] for entry in built["markets"]}
    assert served == set(m.MARKET_GROUP), served
    for entry in built["markets"]:
        for selection in entry["selections"]:
            if selection["probability_source"] == "calculated":
                assert selection["calculation"]["source_market"] == m.MATCH_RESULT


# ----------------------------------------------------------------------- what is not there
def test_an_absent_block_is_unavailable_and_says_it_was_not_published():
    event = copy.deepcopy(load("bulgaria_luxembourg"))
    del event["predictions"][0]["first_half_winner"]
    del event["predictions"][0]["home_team_goals"]
    built = m.build_markets(event)
    fh = market(built, m.FIRST_HALF_RESULT)
    assert fh["available"] is False
    assert fh["unavailable_reason"] == "not published by the provider"
    assert all(s["probability"] is None and not s["available"] for s in fh["selections"])
    assert market(built, m.HOME_TEAM_GOALS, 2.5)["available"] is False
    assert market(built, m.AWAY_TEAM_GOALS, 2.5)["available"] is True


def test_an_all_zero_block_is_a_placeholder_not_a_forecast():
    event = copy.deepcopy(load("bulgaria_luxembourg"))
    event["predictions"][0]["both_teams_score"] = {"yes": 0, "no": 0}
    built = m.build_markets(event)
    btts = market(built, m.BOTH_TEAMS_SCORE)
    assert btts["available"] is False
    assert "placeholder" in btts["unavailable_reason"]
    assert any(w["code"] == "market_all_zero" for w in btts["warnings"])


def test_a_genuine_zero_inside_a_valid_distribution_is_kept_as_zero():
    event = copy.deepcopy(load("bulgaria_luxembourg"))
    event["predictions"][0]["total_goals"]["over_0_5"] = 100
    event["predictions"][0]["total_goals"]["under_0_5"] = 0
    built = m.build_markets(event)
    sel = by_id(built)
    assert sel["total_goals:under@0.5"]["available"] is True
    assert sel["total_goals:under@0.5"]["probability"] == 0.0
    assert sel["total_goals:over@0.5"]["probability"] == 1.0


def test_an_invalid_percentage_is_reported_and_not_read_as_a_number():
    event = copy.deepcopy(load("bulgaria_luxembourg"))
    event["predictions"][0]["match_result"]["home"] = "lots"
    event["predictions"][0]["both_teams_score"]["yes"] = 140
    built = m.build_markets(event)
    sel = by_id(built)
    assert sel["match_result:home"]["available"] is False
    assert sel["match_result:draw"]["available"] is True
    assert any(w["code"] == "invalid_value" for w in market(built, m.MATCH_RESULT)["warnings"])
    assert sel["both_teams_score:yes"]["available"] is False
    assert sel["both_teams_score:no"]["available"] is True


def test_a_payload_with_no_prediction_entry_serves_nothing_and_says_why():
    built = m.build_markets({"id": 1, "predictions": []})
    assert built["markets"] == []
    assert built["reason"] == "the stored event carries no prediction entry"


# ----------------------------------------------------------------------- odds
def test_provider_1x2_prices_are_attached_as_a_dated_snapshot_and_to_nothing_else():
    built = m.build_markets(load("bulgaria_luxembourg"))
    sel = by_id(built)
    assert sel["match_result:home"]["odds"] == {
        "value": 2.3, "format": "decimal", "source": "provider_snapshot", "provider": "gameforecast",
        "captured_at": "2026-09-24T00:00:00+00:00"}
    assert sel["match_result:draw"]["odds"]["value"] == 3.0
    assert sel["match_result:away"]["odds"]["value"] == 3.4
    assert sel["double_chance:1x"]["odds"] is None, "a bookmaker's double-chance price is not arithmetic on these"
    assert sel["total_goals:over@2.5"]["odds"] is None
    assert built["provider_odds"]["bookmaker"] is None

    without = copy.deepcopy(load("bulgaria_luxembourg"))
    without["odds"] = []
    assert by_id(m.build_markets(without))["match_result:home"]["odds"] is None
    assert m.build_markets(without)["provider_odds"] is None


# ----------------------------------------------------------------------- recommended bets
@pytest.mark.parametrize("token,expected", [
    ("matchResult.homeWinProbability", "match_result:home"),
    ("matchResult.drawProbability", "match_result:draw"),
    ("matchResult.awayWinProbability", "match_result:away"),
    ("totalGoals.under2_5", "total_goals:under@2.5"),
    ("totalGoals.over1_5", "total_goals:over@1.5"),
    ("totalGoals.under3_5", "total_goals:under@3.5"),
    ("bothTeamsScore.yes", "both_teams_score:yes"),
    ("bothTeamsScore.no", "both_teams_score:no"),
    ("homeTeamGoals.over1_5", "home_team_goals:over@1.5"),
    ("awayTeamGoals.over1_5", "away_team_goals:over@1.5"),
    ("firstHalfWinner.drawProbability", "first_half_result:draw"),
    ("teamToScoreFirst.awayProbability", "team_to_score_first:away"),
])
def test_every_recommended_bet_reference_seen_in_stored_payloads_resolves(token, expected):
    """The parametrised tokens are every distinct value found across the 92 stored payloads on 2026-09-25."""
    resolved, why = m.resolve_recommended_bet(token)
    assert why is None
    assert m.selection_key(*resolved) == expected


def test_an_ambiguous_recommended_bet_is_refused_not_guessed():
    resolved, why = m.resolve_recommended_bet("awayWinProbability")  # seen once, without its market prefix
    assert resolved is None
    assert "ambiguous" in why
    assert m.resolve_recommended_bet("corners.over9_5") == (None, "unknown market prefix 'corners'")
    assert m.resolve_recommended_bet("") == (None, "empty or not a text reference")


def test_recommended_bets_in_the_payload_are_resolved_against_served_selections():
    built = m.build_markets(load("bulgaria_luxembourg"))
    ranked = {entry["rank"]: entry for entry in built["recommended_bets"]}
    assert ranked["1"]["selection_id"] == "match_result:home" and ranked["1"]["resolved"]
    assert ranked["2"]["selection_id"] == "total_goals:under@2.5"
    assert ranked["3"]["selection_id"] == "both_teams_score:no"

    unavailable = copy.deepcopy(load("bulgaria_luxembourg"))
    unavailable["predictions"][0]["both_teams_score"] = {"yes": 0, "no": 0}
    built = m.build_markets(unavailable)
    third = {entry["rank"]: entry for entry in built["recommended_bets"]}["3"]
    assert third["resolved"] is False and "not available" in third["reason"]


# ----------------------------------------------------------------------- selection keys and envelopes
def test_selection_keys_round_trip():
    for market_id, outcome, line in (("total_goals", "over", 2.5), ("match_result", "home", None), ("exact_score", "1-0", None)):
        assert m.parse_selection_key(m.selection_key(market_id, outcome, line)) == (market_id, outcome, line)
    assert m.parse_selection_key("nonsense") is None
    assert m.parse_selection_key("total_goals:over@two") is None


def test_settlement_capability_is_stated_per_market():
    built = m.build_markets(load("bulgaria_luxembourg"))
    sel = by_id(built)
    assert sel["match_result:home"]["settlement"]["capable"] is True
    assert sel["match_result:home"]["settlement"]["basis"] == "regulation_time"
    assert sel["first_half_result:home"]["settlement"]["basis"] == "half_time"
    first = sel["team_to_score_first:home"]["settlement"]
    assert first["capable"] is False and first["basis"] == "event_order"


def test_rebuilding_from_a_snapshot_keeps_the_snapshots_own_times_and_says_when_it_was_rebuilt():
    now = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    envelope = m.markets_for_forecast(
        match_id="m1", event=load("bulgaria_luxembourg"), provider="gameforecast", record_id=None, snapshot_id="snap-1",
        captured_before_kickoff=True, retrieved_at=datetime(2026, 9, 25, 12, 2, tzinfo=timezone.utc),
        model_run_at=datetime(2026, 9, 24, tzinfo=timezone.utc), provider_updated_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        freshness={"state": "snapshot", "reason": "rebuilt"}, now=now)
    assert envelope["built_at"] == "2026-12-01T12:00:00Z"
    assert envelope["forecast"]["retrieved_at"] == "2026-09-25T12:02:00Z"
    assert envelope["forecast"]["model_run_at"] == "2026-09-24T00:00:00Z"
    assert envelope["forecast"]["snapshot_id"] == "snap-1"
    assert envelope["normalisation_version"] == m.NORMALISATION_VERSION
    assert [g["group"] for g in envelope["groups"]] == list(m.GROUP_ORDER)
    assert m.find_selection(envelope, "total_goals:over@2.5")["probability"] == pytest.approx(0.45)
    assert len(m.available_selections(envelope)) > 30
