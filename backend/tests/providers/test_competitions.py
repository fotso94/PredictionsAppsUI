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


# ----------------------------------------------------------------- national-team competition names
# Provider spellings from `competitions/list.json` (Live Score, 2026-09-23).
LIVESCORE_NAMES = {
    "FIFA World Cup": "fifa_world_cup",
    "World Cup Inter-Confederation Play-Off": "world_cup_inter_confederation_playoff",
    "World Cup UEFA Qualifiers": "world_cup_qualifiers_uefa",
    "World Cup CAF Qualifiers": "world_cup_qualifiers_caf",
    "World Cup AFC Qualifiers": "world_cup_qualifiers_afc",
    "World Cup CONCACAF Qualifiers": "world_cup_qualifiers_concacaf",
    "World Cup CONMEBOL Qualifiers": "world_cup_qualifiers_conmebol",
    "World Cup OFC Qualifiers": "world_cup_qualifiers_ofc",
    "UEFA Nations League": "uefa_nations_league",
    "UEFA EURO Qualification": "uefa_euro_qualification",
    "African Cup of Nations": "africa_cup_of_nations",
    "Africa Cup of Nations Qualifications": "africa_cup_of_nations_qualification",
    "African Nations Championship": "african_nations_championship",
    "African Nations Championship Qualification": "african_nations_championship_qualification",
    "COSAFA Cup": "cosafa_cup",
    "Asian Cup": "asian_cup",
    "Asian Cup Qualification": "asian_cup_qualification",
    "AFF Suzuki Cup": "aff_suzuki_cup",
    "SAFF Championship": "saff_championship",
    "Arab Cup": "arab_cup",
    "Arabian Gulf Cup": "arabian_gulf_cup",
    "Gold Cup": "gold_cup",
    "Gold Cup Qualifiers": "gold_cup_qualifiers",
    "CONCACAF Nations League": "concacaf_nations_league",
    "CONCACAF Nations League Qualification": "concacaf_nations_league_qualification",
    "Olympic Games Football Tournament": "olympic_games_football",
    "Copa America": "copa_america",
    "National Teams Friendlies": "national_teams_friendlies",
    "Women's World Cup": "womens_world_cup",
    "FIFA Confederations Cup": "fifa_confederations_cup",
    "King's Cup": "kings_cup",
    "Kirin Cup": "kirin_cup",
    "Southeast Asian Games": "southeast_asian_games",
    "Toulon": "toulon",
}


def test_every_provider_name_resolves_to_its_own_competition():
    for name, key in LIVESCORE_NAMES.items():
        assert comps.match_competition_name(name, exact=True) == key, name
        assert comps.match_competition_name(name) == key, name


def test_similar_names_are_never_merged():
    # Each pair is two different competitions in the same catalogue. Alias matching loose enough to
    # merge any of them is worse than none.
    for loose, qualifier in [
        ("asian_cup", "Asian Cup Qualification"),
        ("gold_cup", "Gold Cup Qualifiers"),
        ("concacaf_nations_league", "CONCACAF Nations League Qualification"),
        ("africa_cup_of_nations", "Africa Cup of Nations Qualifications"),
        ("african_nations_championship", "African Nations Championship Qualification"),
        ("uefa_euro_qualification", "UEFA EURO"),
    ]:
        assert comps.match_competition_name(qualifier, keys=[loose]) is None, qualifier
    # ...and the two African competitions whose names share three words are not each other.
    assert comps.match_competition_name("African Nations Championship", keys=["africa_cup_of_nations"]) is None
    assert comps.match_competition_name("African Cup of Nations", keys=["african_nations_championship"]) is None
    # Two confederations run a "Nations League"; neither alias is the bare phrase.
    assert comps.match_competition_name("CONCACAF Nations League", keys=["uefa_nations_league"]) is None
    assert comps.match_competition_name("UEFA Nations League", keys=["concacaf_nations_league"]) is None
    # "AFF Suzuki Cup" is a substring-length away from "SAFF Championship".
    assert comps.match_competition_name("SAFF Championship", keys=["aff_suzuki_cup"]) is None
    # The men's World Cup must not swallow the women's, nor the qualifiers.
    assert comps.match_competition_name("Women's World Cup", keys=["fifa_world_cup"]) is None
    assert comps.match_competition_name("World Cup UEFA Qualifiers", keys=["fifa_world_cup"]) is None
    # One confederation's qualifiers are not another's.
    assert comps.match_competition_name("World Cup CAF Qualifiers", keys=["world_cup_qualifiers_uefa"]) is None


def test_a_competition_is_not_rejected_for_naming_its_own_confederation():
    # A confederation token only tells competitions apart across confederations.
    assert comps.match_competition_name("CONCACAF Gold Cup") == "gold_cup"
    assert comps.match_competition_name("AFC Asian Cup") == "asian_cup"
    assert comps.match_competition_name("CAF Africa Cup of Nations") == "africa_cup_of_nations"
    assert comps.match_competition_name("FIFA Women's World Cup") == "womens_world_cup"
    # while the club-side guard it exists for still holds
    assert comps.match_competition_name("AFC Champions League", country="AFC", is_cup=True) is None
    assert comps.match_competition_name("CONCACAF Champions League", is_cup=True) is None


def test_age_restricted_and_womens_variants_never_match_a_senior_mens_competition():
    for name in ["Copa America Femenina", "Gold Cup Women", "Asian Cup U23", "COSAFA U20 Cup",
                 "Arab Cup U-20", "World Cup U-17"]:
        assert comps.match_competition_name(name) is None, name


def test_national_team_competitions_ignore_the_country_on_a_fixture():
    # Live Score sends `countries: []` for these and the country on a fixture is the host's, so a
    # country check could only reject a competition that is ours.
    assert comps.match_competition_name("FIFA World Cup", country="Qatar") == "fifa_world_cup"
    assert comps.match_competition_name("UEFA Nations League", country="Andorra") == "uefa_nations_league"
    # Domestic leagues keep theirs.
    assert comps.match_competition_name("Premier League", country="Belize") is None


def test_a_season_marker_does_not_disqualify_a_name():
    assert comps.match_competition_name("Premier League 2026/2027", country="England") == "premier_league"
    assert comps.match_competition_name("FIFA World Cup 2026") == "fifa_world_cup"
    # ...while the reserve league, which carries no year, stays excluded
    assert comps.match_competition_name("Premier League 2", country="England") is None


def test_resolving_the_whole_catalogue_in_one_pass_keeps_each_pair_apart():
    rows = [(i, name, None, True) for i, name in enumerate(LIVESCORE_NAMES)]
    rows += [(len(rows), "Premier League", "England", False)]
    resolved = comps.resolve_competitions(rows, list(LIVESCORE_NAMES.values()) + ["premier_league"])
    assert len(resolved) == len(LIVESCORE_NAMES) + 1
    names = list(LIVESCORE_NAMES)
    for key, index in resolved.items():
        expected = "Premier League" if key == "premier_league" else names[index]
        assert LIVESCORE_NAMES.get(expected, "premier_league") == key, (key, expected)
