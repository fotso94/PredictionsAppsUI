"""Cross-provider fixture identity: names + competition + UTC kickoff, never numeric ids."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import match_matching
from app.services.match_matching import MatchCandidate, find_match, normalize_team_name, team_names_match

KICKOFF = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)


def cand(match_id, home, away, delta=timedelta(0), key="premier_league"):
    return MatchCandidate(match_id, home, away, KICKOFF + delta, key)


def test_normalisation_and_aliases():
    assert normalize_team_name("Manchester United FC") == normalize_team_name("Man Utd")
    assert normalize_team_name("Atlético de Madrid") == normalize_team_name("Atletico Madrid")
    assert team_names_match("FC Bayern München", "Bayern Munich")
    assert team_names_match("Paris Saint-Germain", "PSG")
    assert team_names_match("Inter", "FC Internazionale Milano")
    assert team_names_match("Brighton & Hove Albion", "Brighton")
    assert not team_names_match("Manchester United", "Manchester City")
    assert not team_names_match("Liverpool", "Everton")


def test_shared_city_tokens_do_not_match_across_clubs():
    assert not team_names_match("Real Madrid", "Atletico Madrid")
    assert not team_names_match("Real Madrid", "Atlético de Madrid")
    assert not team_names_match("Paris Saint-Germain", "Paris FC")
    assert not team_names_match("Sheffield United", "Sheffield Wednesday")
    assert not team_names_match("Sporting Gijón", "Sporting CP")
    assert not team_names_match("Inter", "Milan")
    # legitimate short forms still match
    assert team_names_match("Deportivo Alavés", "Alavés")
    assert team_names_match("CA Osasuna", "Osasuna")
    assert team_names_match("Athletic Club", "Athletic Bilbao")
    assert team_names_match("AJ Auxerre", "Auxerre")
    assert team_names_match("Stade de Reims", "Reims")
    assert team_names_match("Bayer 04 Leverkusen", "Bayer Leverkusen")
    assert team_names_match("1. FC Union Berlin", "Union Berlin")
    assert team_names_match("Atlético de Madrid", "Atletico Madrid")


def test_exact_and_high_confidence():
    d = find_match("Liverpool", "Everton", KICKOFF + timedelta(minutes=5), "premier_league", [cand("m1", "Liverpool FC", "Everton FC")])
    assert d.attached and d.match_id == "m1" and d.confidence == "exact"
    d = find_match("Liverpool", "Everton", KICKOFF + timedelta(hours=2), "premier_league", [cand("m1", "Liverpool", "Everton")])
    assert d.attached and d.confidence == "high"


def test_same_numeric_id_is_not_used_for_identity():
    # candidates only expose names/kickoff; an id-only coincidence has no way to match
    d = find_match("Arsenal", "Chelsea", KICKOFF, "premier_league", [cand("1001", "Liverpool", "Everton")])
    assert not d.attached and d.confidence == "none"


def test_swapped_home_away_is_ambiguous_not_attached():
    d = find_match("Everton", "Liverpool", KICKOFF, "premier_league", [cand("m1", "Liverpool", "Everton")])
    assert not d.attached and d.confidence == "ambiguous" and d.candidate_ids == ["m1"]


def test_rescheduled_beyond_window_is_ambiguous():
    d = find_match("Liverpool", "Everton", KICKOFF + timedelta(hours=26), "premier_league", [cand("m1", "Liverpool", "Everton")])
    assert not d.attached and d.confidence == "ambiguous" and "rescheduled" in d.reason


def test_two_candidates_in_window_is_ambiguous():
    d = find_match("Liverpool", "Everton", KICKOFF, "premier_league",
                   [cand("m1", "Liverpool", "Everton"), cand("m2", "Liverpool", "Everton", timedelta(hours=1))])
    assert not d.attached and d.confidence == "ambiguous" and set(d.candidate_ids) == {"m1", "m2"}


def test_competition_mismatch_is_ignored():
    d = find_match("Liverpool", "Everton", KICKOFF, "champions_league", [cand("m1", "Liverpool", "Everton", key="premier_league")])
    assert not d.attached and d.confidence == "none"


def test_missing_kickoff_never_attaches():
    d = find_match("Liverpool", "Everton", None, "premier_league", [cand("m1", "Liverpool", "Everton")])
    assert not d.attached and d.confidence == "ambiguous"


def test_naive_kickoffs_are_treated_as_utc():
    naive = KICKOFF.replace(tzinfo=None)
    d = find_match("Liverpool", "Everton", naive, "premier_league", [MatchCandidate("m1", "Liverpool", "Everton", naive, "premier_league")])
    assert d.attached and d.confidence == "exact"


def test_german_transliterations_match_live_provider_names():
    # Live Score API spells umlauts with "oe"/"ue"; GameForecast strips them
    assert team_names_match("Borussia Moenchengladbach", "Borussia Monchengladbach")
    assert team_names_match("Borussia Moenchengladbach", "Borussia M'gladbach")
    assert team_names_match("1. FC Koeln", "FC Cologne")
    assert team_names_match("FC Cologne", "Köln")
    assert team_names_match("Hamburger SV", "Hamburg")
    assert team_names_match("Bayern Muenchen", "Bayern Munich")
    assert team_names_match("Mainz 05", "FSV Mainz 05")
    assert team_names_match("RasenBallsport Leipzig", "RB Leipzig")
    assert not team_names_match("Borussia Moenchengladbach", "Borussia Dortmund")


# --------------------------------------------------------------------------- regression table
# Pairs that MUST be recognised as the same club. Each one is a spelling two of our providers
# actually use for the same team; a regression here silently duplicates the club and its matches.
MUST_MATCH = [
    ("Borussia Moenchengladbach", "Borussia Monchengladbach"),
    ("Moenchengladbach", "Monchengladbach"),
    ("1. FC Koeln", "FC Cologne"),
    ("Besiktas", "Besiktas JK"),
    ("Zuerich", "Zurich"),
    ("Malmoe", "Malmo"),
    ("Sporting CP", "Sporting Lisbon"),
    ("Internazionale", "Inter Milan"),
    ("Bayern Muenchen", "Bayern Munich"),
    ("Slavia Praha", "Slavia Prague"),
    ("SK Slavia Praha", "Slavia Prague"),
    ("Hamburger SV", "Hamburg"),
    ("FC St. Pauli", "St Pauli"),
    ("Stade Brestois 29", "Brest"),
]

# Pairs that MUST NOT be conflated: attaching one club's forecast to another club's match is worse
# than having no forecast at all.
MUST_NOT_MATCH = [
    ("Atletico Madrid", "Athletic Club"),
    ("Real Madrid", "Atletico Madrid"),
    ("Paris FC", "Paris Saint-Germain"),
    ("Manchester City", "Manchester United"),
    ("Bayer Leverkusen", "Bayern Munich"),
    ("Inter Milan", "AC Milan"),
    ("Sheffield United", "Sheffield Wednesday"),
]


@pytest.mark.parametrize("left,right", MUST_MATCH)
def test_provider_spellings_of_the_same_club_match(left, right):
    assert team_names_match(left, right), f"{left!r} / {right!r} -> {normalize_team_name(left)!r} / {normalize_team_name(right)!r}"
    assert team_names_match(right, left)


@pytest.mark.parametrize("left,right", MUST_NOT_MATCH)
def test_different_clubs_never_match(left, right):
    assert not team_names_match(left, right)
    assert not team_names_match(right, left)


def test_a_one_token_subset_is_not_enough_on_the_name_alone():
    # the extra word is an identity, not decoration
    assert not team_names_match("Zurich", "Grasshopper Zurich")
    assert not team_names_match("Leipzig", "Lokomotive Leipzig")
    assert not team_names_match("Madrid", "Rayo Vallecano de Madrid")
    # decoration (a city prefix or a club-type initialism) still matches
    assert team_names_match("Alaves", "Deportivo Alaves")
    assert team_names_match("Osasuna", "CA Osasuna")
    assert team_names_match("Auxerre", "AJ Auxerre")
    assert team_names_match("Reims", "Stade de Reims")


def test_umlaut_fold_does_not_corrupt_unrelated_words():
    assert normalize_team_name("Prague") == "prague"
    assert normalize_team_name("Queretaro") == "queretaro"
    assert normalize_team_name("Olympiakos Piraeus") == normalize_team_name("Olympiacos")
    assert normalize_team_name("AEK Athens") == "aek athens"
    # ... while the German spellings still fold
    assert normalize_team_name("Duesseldorf") == "dusseldorf"
    assert normalize_team_name("Nuernberg") == "nurnberg"
    assert normalize_team_name("Goeteborg") == "goteborg"


def test_every_alias_value_is_its_own_normalised_form():
    # an alias value that does not normalise to itself is unreachable (the "Slavia Prague" defect)
    broken = {k: v for k, v in match_matching._ALIASES.items() if normalize_team_name(v) != v}
    assert broken == {}


def test_find_match_links_the_real_livescore_gameforecast_pair():
    # Live Score API spelling on one side, GameForecast on the other, same fixture
    decision = find_match("Borussia Moenchengladbach", "1. FC Koeln", KICKOFF, "bundesliga",
                          [MatchCandidate("m1", "Borussia Monchengladbach", "FC Cologne", KICKOFF, "bundesliga")])
    assert decision.attached and decision.match_id == "m1" and decision.confidence == "exact"


def test_find_match_reports_a_postponed_fixture_instead_of_ignoring_it():
    # five days later: far outside every attach threshold, but the candidate must still be reported
    decision = find_match("Liverpool", "Everton", KICKOFF + timedelta(days=5), "premier_league",
                          [cand("m1", "Liverpool", "Everton")])
    assert not decision.attached and decision.confidence == "ambiguous"
    assert "rescheduled" in decision.reason and decision.candidate_ids == ["m1"]


def test_a_wider_lookup_window_never_turns_into_an_attachment():
    # the caller may hand over candidates a fortnight away; find_match keeps its own thresholds
    far = [cand("m1", "Liverpool", "Everton", timedelta(days=13)), cand("m2", "Liverpool", "Everton", timedelta(days=-13))]
    decision = find_match("Liverpool", "Everton", KICKOFF, "premier_league", far)
    assert not decision.attached and set(decision.candidate_ids) == {"m1", "m2"}


def test_lookup_window_is_much_wider_than_the_attach_windows():
    assert match_matching.LOOKUP_WINDOW > match_matching.RESCHEDULE_WINDOW > match_matching.DEFAULT_MAX_DELTA
