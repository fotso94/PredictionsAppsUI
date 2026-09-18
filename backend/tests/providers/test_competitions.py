"""Canonical competition matching against real provider naming."""

from app.services.providers import competitions as comps


def test_lookalikes_never_match():
    assert comps.match_competition_name("Non Premier League", country="England") is None
    assert comps.match_competition_name("2nd Bundesliga", country="Germany") is None
    assert comps.match_competition_name("Premier League 2", country="England") is None
    assert comps.match_competition_name("Premier League", country="Belize") is None
    assert comps.match_competition_name("Serie A", country="Brazil") is None
    assert comps.match_competition_name("Ligue 1", country="Senegal") is None
    assert comps.match_competition_name("Champions League", country="CONCACAF", is_cup=True) is None
    assert comps.match_competition_name("AFC Champions League", country="AFC", is_cup=True) is None
    assert comps.match_competition_name("Premier League Summer Series", country="England") is None


def test_real_names_match():
    assert comps.match_competition_name("Premier League", country="England") == "premier_league"
    assert comps.match_competition_name("LaLiga Santander", country="Spain") == "la_liga"
    assert comps.match_competition_name("Primera División", country="Spain") == "la_liga"
    assert comps.match_competition_name("Serie A", country="Italy") == "serie_a"
    assert comps.match_competition_name("Bundesliga", country="Germany") == "bundesliga"
    assert comps.match_competition_name("Ligue 1", country="France") == "ligue_1"
    assert comps.match_competition_name("Champions League", country="UEFA", is_cup=True) == "champions_league"
    assert comps.match_competition_name("UEFA Champions League", is_cup=True) == "champions_league"


def test_exact_pass_only_accepts_whole_names():
    assert comps.match_competition_name("LaLiga Santander", country="Spain", exact=True) is None
    assert comps.match_competition_name("LaLiga", country="Spain", exact=True) == "la_liga"


def test_resolve_competitions_prefers_exact_matches_regardless_of_order():
    rows = [(0, "Non Premier League", "England", False), (1, "LaLiga Santander", "Spain", False),
            (2, "Premier League", "England", False), (3, "2nd Bundesliga", "Germany", False), (4, "Bundesliga", "Germany", False)]
    assert comps.resolve_competitions(rows, ["premier_league", "la_liga", "bundesliga"]) == {"premier_league": 2, "la_liga": 1, "bundesliga": 4}
