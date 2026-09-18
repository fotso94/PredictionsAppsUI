"""Cross-provider fixture identity: names + competition + UTC kickoff, never numeric ids."""

from datetime import datetime, timedelta, timezone

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
