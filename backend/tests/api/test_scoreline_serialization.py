"""What the match payload says a tie finished at.

A knockout tie has more than one scoreline. Switzerland 0-0 Colombia, won 4-3 on penalties, is a
draw to every market settlement scores - those settle on the 90-minute score and nothing else - and
a Switzerland win to everyone who watched it. The published ruleset (``PERIODS_RULE``) tells readers
both are kept and neither is folded into the other; these tests hold the serialiser to that.

No database and no provider: ``serialize_match`` reads a stored row's metadata, so a constructed
row is the whole input and the assertions are about the shape that leaves the API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.predictions import Match, MatchStatus
from app.schemas.matches import serialize_match, serialize_score


def _match(**meta) -> Match:
    return Match(id=uuid.uuid4(), league_id=uuid.uuid4(), home_team_id=uuid.uuid4(),
                 away_team_id=uuid.uuid4(), match_date=datetime(2026, 6, 18, 15, 0),
                 status=MatchStatus.FINISHED, external_api_id="ext-scoreline-test",
                 external_api_source="sample", match_metadata=dict(meta))


def _score(**meta):
    return serialize_match(_match(**meta), {}, {})["score"]


def test_a_shoot_out_travels_beside_the_tie_and_is_never_folded_into_it():
    score = _score(home_score=0, away_score=0, ht_home_score=0, ht_away_score=0,
                   ft_home_score=0, ft_away_score=0, ps_home_score=4, ps_away_score=3)

    # the football played, and the period every market settles on: both 0-0, neither one 4-3
    assert (score["home"], score["away"]) == (0, 0)
    assert (score["ft_home"], score["ft_away"]) == (0, 0)
    # and the shoot-out, in its own fields, so a reader can be shown "0-0 (4-3 pens)"
    assert (score["ps_home"], score["ps_away"]) == (4, 3)


def test_extra_time_and_the_regulation_score_are_published_as_the_two_different_things_they_are():
    score = _score(home_score=2, away_score=1, ht_home_score=0, ht_away_score=1,
                   ft_home_score=1, ft_away_score=1, et_home_score=2, et_away_score=1)

    assert (score["home"], score["away"]) == (2, 1)        # what was played, extra time included
    assert (score["ft_home"], score["ft_away"]) == (1, 1)  # the draw every market here settles on
    assert (score["et_home"], score["et_away"]) == (2, 1)
    assert score["ps_home"] is None and score["ps_away"] is None


def test_a_period_the_source_did_not_supply_is_null_and_never_a_zero():
    score = _score(home_score=2, away_score=0)

    assert (score["home"], score["away"]) == (2, 0)
    for field in ("ht_home", "ht_away", "ft_home", "ft_away",
                  "et_home", "et_away", "ps_home", "ps_away"):
        assert score[field] is None, f"{field} was filled in when nothing supplied it"


def test_a_goalless_period_is_kept_apart_from_one_that_was_never_supplied():
    supplied = _score(home_score=0, away_score=0, ft_home_score=0, ft_away_score=0)
    absent = _score(home_score=0, away_score=0)

    assert supplied["ft_home"] == 0 and supplied["ft_away"] == 0
    assert absent["ft_home"] is None and absent["ft_away"] is None


def test_a_fixture_with_no_score_publishes_no_score_object():
    assert _score() is None
    assert _score(home_score=1) is None                    # half a scoreline is not a scoreline
    assert serialize_score({"away_score": 1}) is None
