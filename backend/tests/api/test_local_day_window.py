"""
A local calendar day is not always 24 hours.

On a daylight-saving transition it is 23 or 25, so a window built by adding a fixed day to local
midnight is wrong exactly twice a year - and the hour it drops is the one just after midnight, which
is where a late kickoff lands for viewers west of Greenwich.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.api.v1.endpoints.matches import local_day_window

HOUR = timedelta(hours=1)


def _hours(window):
    start, end = window
    return (end - start).total_seconds() / 3600


def test_an_ordinary_day_is_twenty_four_hours():
    window = local_day_window(date(2026, 9, 18), -240, -240)
    assert window[0] == datetime(2026, 9, 18, 4, tzinfo=timezone.utc)
    assert _hours(window) == 24


def test_the_day_clocks_go_back_is_twenty_five_hours():
    """New York, 1 November 2026: the local day runs 04:00Z to 05:00Z the next day."""
    window = local_day_window(date(2026, 11, 1), -240, -300)
    assert window[0] == datetime(2026, 11, 1, 4, tzinfo=timezone.utc)
    assert window[1] == datetime(2026, 11, 2, 5, tzinfo=timezone.utc)
    assert _hours(window) == 25


def test_the_day_clocks_go_forward_is_twenty_three_hours():
    """New York, 8 March 2026: the local day runs 05:00Z to 04:00Z the next day."""
    window = local_day_window(date(2026, 3, 8), -300, -240)
    assert _hours(window) == 23


def test_a_kickoff_just_after_local_midnight_on_a_transition_day_is_included():
    """The regression: a fixed 24-hour window started an hour late and lost this match."""
    start, end = local_day_window(date(2026, 11, 1), -240, -300)
    just_after_midnight = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)   # 00:30 local
    assert start <= just_after_midnight < end

    naive_fixed_window_start = datetime(2026, 11, 1, 5, tzinfo=timezone.utc)  # what the old code used
    assert just_after_midnight < naive_fixed_window_start


def test_the_end_offset_is_optional_and_defaults_to_the_start():
    assert local_day_window(date(2026, 9, 18), -240) == local_day_window(date(2026, 9, 18), -240, -240)


@pytest.mark.parametrize("offset", [-720, 0, 840])
def test_windows_are_half_open_and_contiguous(offset):
    """Consecutive days must not overlap or leave a gap, or a match is shown twice or not at all."""
    first = local_day_window(date(2026, 9, 18), offset, offset)
    second = local_day_window(date(2026, 9, 19), offset, offset)
    assert first[1] == second[0]


def test_a_nonsensical_offset_pair_does_not_produce_an_empty_day():
    start, end = local_day_window(date(2026, 9, 18), -240, 840)
    assert end > start


# --------------------------------------------------------------- complementary market validation
def test_an_expert_cannot_publish_a_market_that_contradicts_itself():
    """Over 2.5 and under 2.5 are complementary: 90% both is not a prediction, it is a mistake."""
    from app.schemas.predictions import ExpertPredictionCreate, ExpertPredictionUpdate
    import pydantic

    base = dict(match_id="00000000-0000-0000-0000-000000000000",
                home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2)
    for model in (ExpertPredictionCreate, ExpertPredictionUpdate):
        with pytest.raises(pydantic.ValidationError):
            model(**base, total_goals_over_25_prob=0.9, total_goals_under_25_prob=0.9)
        with pytest.raises(pydantic.ValidationError):
            model(**base, total_goals_over_35_prob=0.8, total_goals_under_35_prob=0.8)
        with pytest.raises(pydantic.ValidationError):
            model(**base, btts_yes_prob=0.8, btts_no_prob=0.8)

        # a consistent pair, and a half published on its own, both stand
        assert model(**base, total_goals_over_25_prob=0.6, total_goals_under_25_prob=0.4)
        assert model(**base, total_goals_over_25_prob=0.6)
