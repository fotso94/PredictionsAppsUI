"""
National-team competitions: provider flags, classification, coverage and team identity.

The Live Score ids asserted here were read from `competitions/list.json` (523 competitions, one
request) on 2026-09-23 and are re-checked against the saved catalogue in `docs/evidence/`.
"""

import json
from pathlib import Path

import pytest

from app.services.match_matching import normalize_team_name, team_names_match
from app.services.providers import competitions as comps
from app.services.providers.competitions import Confederation, SquadCategory, TeamScope

EVIDENCE = (Path(__file__).resolve().parents[3]
            / "docs" / "evidence" / "livescore-national-team-catalogue.json")

#: national_teams_only="1" AND active="1" in the provider catalogue.
FLAGGED_ACTIVE = {
    "fifa_world_cup": 362, "world_cup_inter_confederation_playoff": 365,
    "world_cup_qualifiers_uefa": 363, "world_cup_qualifiers_caf": 359,
    "world_cup_qualifiers_afc": 358, "world_cup_qualifiers_concacaf": 360,
    "world_cup_qualifiers_conmebol": 361, "world_cup_qualifiers_ofc": 364,
    "uefa_nations_league": 350, "uefa_euro_qualification": 274,
    "africa_cup_of_nations": 227, "africa_cup_of_nations_qualification": 228,
    "african_nations_championship": 226, "african_nations_championship_qualification": 403,
    "cosafa_cup": 225, "asian_cup": 240, "asian_cup_qualification": 241,
    "aff_suzuki_cup": 246, "saff_championship": 247, "arab_cup": 452, "arabian_gulf_cup": 412,
    "gold_cup": 266, "gold_cup_qualifiers": 435, "concacaf_nations_league": 391,
    "concacaf_nations_league_qualification": 269, "olympic_games_football": 385,
}
#: national_teams_only="1" AND active="0": dormant, so they keep their id and stay out of coverage.
FLAGGED_DORMANT = {
    "fifa_confederations_cup": 270, "kings_cup": 373, "kirin_cup": 374,
    "southeast_asian_games": 248, "toulon": 377,
}
#: The flag lies by omission: these three are sent with national_teams_only="0".
FLAG_SAYS_CLUB = {"copa_america": 271, "national_teams_friendlies": 371, "womens_world_cup": 490}

#: `is_cup` for those same three, read from `competitions/list.json` on 2026-09-23 - the same 523-row
#: response the catalogue in docs/evidence/ was filtered out of, which is why they are not in it. The
#: provider sends all three as the string "1", National Teams Friendlies included. Credentials are
#: request parameters and appear in no reply, so nothing here needs redacting.
MEASURED_IS_CUP = {"copa_america": True, "national_teams_friendlies": True, "womens_world_cup": True}

#: The two fixtures Live Score held for competition 371 on 2026-09-23, read from
#: `fixtures/list.json?date=2026-09-23&competition_id=371` the same day. They are here for the
#: competition object each one carries, which classifies the competition a second time and agrees
#: with the catalogue. The teams and kickoffs are the provider's, transcribed and not invented.
FRIENDLIES_FIXTURES_20260923 = [
    {"id": 1898558, "date": "2026-09-23", "time": "16:00:00", "home": "Azerbaijan", "away": "Tajikistan",
     "competition": {"id": 371, "name": "National Teams Friendlies", "active": True, "is_cup": True,
                     "is_league": False, "national_teams_only": False, "has_groups": False, "tier": 0}},
    {"id": 1901037, "date": "2026-09-23", "time": "16:00:00", "home": "Gibraltar",
     "away": "Sao Tome And Principe",
     "competition": {"id": 371, "name": "National Teams Friendlies", "active": True, "is_cup": True,
                     "is_league": False, "national_teams_only": False, "has_groups": False, "tier": 0}},
]


# ----------------------------------------------------------------- provider flag parsing
def test_zero_string_is_false_even_though_python_calls_it_true():
    # The whole reason the helper exists: every flag Live Score sends is a string.
    assert bool("0") is True
    assert comps.parse_provider_flag("0") is False
    assert comps.parse_provider_flag("1") is True


@pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "off", "", "  ", None, 0, False])
def test_falsey_flag_shapes(value):
    assert comps.parse_provider_flag(value) is False


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", " 1 ", "yes", "on", 1, 2, True])
def test_truthy_flag_shapes(value):
    assert comps.parse_provider_flag(value) is True


def test_unrecognised_flag_never_reads_as_true():
    # A provider that starts sending "maybe" must not silently flip 523 classifications.
    assert comps.parse_provider_flag("maybe") is False
    assert comps.parse_provider_flag("maybe", default=True) is True


def test_active_flag_is_parsed_from_the_string_the_provider_sends():
    assert comps.is_active_payload({"active": "1"}) is True
    assert comps.is_active_payload({"active": "0"}) is False
    assert comps.is_active_payload({}) is False


# ----------------------------------------------------------------- classification
def test_flag_alone_would_drop_three_national_team_competitions():
    for key, ident in FLAG_SAYS_CLUB.items():
        payload = {"id": str(ident), "name": comps.get(key).name, "national_teams_only": "0", "active": "1"}
        assert comps.parse_provider_flag(payload["national_teams_only"]) is False
        assert comps.is_national_team_payload(payload) is True, key
        assert comps.get(key).is_national_team is True


def test_flagged_competitions_are_recognised_by_the_flag():
    for key, ident in FLAGGED_ACTIVE.items():
        assert comps.is_national_team_payload(
            {"id": str(ident), "national_teams_only": "1", "active": "1"}) is True, key


def test_club_competition_is_not_a_national_team_competition():
    assert comps.is_national_team_payload({"id": "2", "national_teams_only": "0", "active": "1"}) is False
    assert comps.get("premier_league").is_national_team is False


def test_registry_ids_match_the_verified_catalogue():
    for key, ident in {**FLAGGED_ACTIVE, **FLAGGED_DORMANT, **FLAG_SAYS_CLUB}.items():
        comp = comps.get(key)
        assert comp.livescore_id == ident, key
        assert comp.is_national_team is True, key
        assert comp.confederation is not None, key


def test_dormant_competitions_are_marked_dormant_and_active_ones_active():
    for key in FLAGGED_DORMANT:
        assert comps.get(key).provider_active is False, key
    for key in {**FLAGGED_ACTIVE, **FLAG_SAYS_CLUB}:
        assert comps.get(key).provider_active is True, key


#: The only GameForecast ids any national-team competition may carry: the ones a name-targeted
#: /leagues probe returned on 2026-09-23, recorded in docs/evidence/gameforecast-league-catalogue.json.
VERIFIED_GAMEFORECAST_IDS = {"uefa_nations_league": 36, "concacaf_nations_league": 38}


def test_no_invented_ids_for_providers_that_were_never_asked():
    """An id may be written down only where it was asked for and answered.

    A wrong id attaches another competition's fixtures or forecasts to these matches, silently and
    with no error anywhere. API-Football and TheSportsDB have never been asked about a single one of
    these competitions, so every one of those ids must stay absent; GameForecast has been asked
    about exactly two, and only those two may carry one. The test is written as an ALLOW-LIST rather
    than as "none", so adding an id without measuring it fails here rather than in production.
    """
    for key in comps.select_keys(national_teams=True):
        comp = comps.get(key)
        assert comp.api_football_id is None, key
        assert comp.thesportsdb_id is None, key
        assert comp.gameforecast_id == VERIFIED_GAMEFORECAST_IDS.get(key), key
        assert comp.livescore_id is not None, key


def test_a_competition_with_no_forecast_id_is_not_offered_to_the_forecast_rotation():
    """Coverage by the match provider says nothing about coverage by the forecast provider.

    Feeding the rotation a competition whose id is unknown would spend discovery lookups out of an
    allowance of eight a day, and `ForecastService.sync_order` puts never-synced competitions first
    - so the unpriced ones would take every turn while the competitions that DO have ids never got
    one. Only a verified id admits a competition to the rotation.
    """
    offered = comps.keys_with_provider_id("gameforecast_id")
    national_offered = [k for k in offered if comps.get(k).is_national_team]
    assert sorted(national_offered) == sorted(VERIFIED_GAMEFORECAST_IDS)
    # And the club competitions that always had ids are still in it.
    assert {"premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1"} <= set(offered)


def test_every_competition_carries_a_confederation_and_a_squad_category():
    for key, comp in comps.COMPETITIONS.items():
        assert isinstance(comp.confederation, Confederation), key
        assert isinstance(comp.squad_category, SquadCategory), key


def test_confederation_grouping_is_complete():
    grouped = {conf: comps.select_keys(national_teams=True, confederation=conf) for conf in Confederation}
    assert sum(len(keys) for keys in grouped.values()) == len(comps.select_keys(national_teams=True))
    assert "copa_america" in grouped[Confederation.CONMEBOL]
    assert "world_cup_qualifiers_ofc" in grouped[Confederation.OFC]
    assert "uefa_nations_league" in grouped[Confederation.UEFA]
    assert "africa_cup_of_nations" in grouped[Confederation.CAF]
    assert "gold_cup" in grouped[Confederation.CONCACAF]
    assert "asian_cup" in grouped[Confederation.AFC]
    assert "fifa_world_cup" in grouped[Confederation.FIFA]


def test_each_squad_category_is_its_own_and_none_of_the_three_is_missing():
    """Women and youth are categories in their own right, and youth is NOT a category we lack.

    The provider publishes no age field, so a competition restricted by its governing body's entry
    rules - Olympic men's football at under-23, Toulon at under-21/23, Southeast Asian Games at
    under-22 - arrives looking exactly like a senior one. Reading them as senior is what would put
    an under-23 result on a country's senior record and its senior team row, so the registry
    classifies them from those published entry rules instead.
    """
    assert comps.select_keys(national_teams=True, squad_category=SquadCategory.SENIOR_WOMEN) == ["womens_world_cup"]
    assert sorted(comps.select_keys(squad_category=SquadCategory.YOUTH)) == [
        "olympic_games_football", "southeast_asian_games", "toulon"]
    support = comps.squad_category_support()
    for category in SquadCategory:
        assert support[category] == comps.SUPPORT_COVERED, category
    assert comps.unsupported_squad_categories() == []

    # And the categories are separate identities, not labels: one country's senior and under-23
    # squads must never resolve onto one team row.
    assert comps.team_scope("fifa_world_cup", "Spain") is not comps.team_scope("olympic_games_football", "Spain")


@pytest.mark.skipif(not EVIDENCE.exists(), reason="saved Live Score catalogue not present")
def test_registry_agrees_with_the_saved_catalogue():
    payload = json.loads(EVIDENCE.read_text())
    rows = {int(row["id"]): row for row in payload["national_team_competitions"]}
    assert payload["total_competitions_seen"] == 523
    for key, ident in {**FLAGGED_ACTIVE, **FLAGGED_DORMANT}.items():
        assert ident in rows, key
        assert rows[ident]["active"] is (key in FLAGGED_ACTIVE), key
        assert comps.get(key).name == rows[ident]["name"], key
    # The three the flag misses are absent from a catalogue filtered on national_teams_only="1".
    for key, ident in FLAG_SAYS_CLUB.items():
        assert ident not in rows, key


# ----------------------------------------------------------------- is_cup
@pytest.mark.skipif(not EVIDENCE.exists(), reason="saved Live Score catalogue not present")
def test_is_cup_comes_from_the_saved_catalogue_row_by_row():
    # `_national` defaults is_cup to True. This is the evidence for that default, and the reason it
    # may be a default at all: the provider publishes a value for each of these 31 and it is True
    # every time. A registry row that stopped agreeing with its catalogue row would fail here.
    rows = {int(row["id"]): row for row in json.loads(EVIDENCE.read_text())["national_team_competitions"]}
    for key, ident in {**FLAGGED_ACTIVE, **FLAGGED_DORMANT}.items():
        assert comps.get(key).is_cup is rows[ident]["is_cup"], key


def test_is_cup_for_the_three_the_flag_misses_is_the_providers_answer_not_an_impression():
    # A catalogue filtered on national_teams_only="1" does not contain these three, so their is_cup
    # was read straight from `competitions/list.json` on 2026-09-23 (523 rows, the same response the
    # flags above come from). National Teams Friendlies is the surprising one: a friendlies calendar
    # has no bracket, no group stage and no trophy, and the provider still publishes it as a cup.
    # The registry records the provider's answer, because the provider is what the rest of this
    # module has to agree with. Reasoning from the shape of the competition would have written False
    # here and put our league rows in contradiction with the fixtures they hold.
    for key in FLAG_SAYS_CLUB:
        assert comps.get(key).is_cup is MEASURED_IS_CUP[key], key


def test_the_friendlies_fixture_rows_of_2026_09_23_say_the_same_thing():
    # Read from fixtures/list.json?date=2026-09-23&competition_id=371. Each fixture carries its own
    # competition object, and it classifies the competition twice and agrees with itself.
    for row in FRIENDLIES_FIXTURES_20260923:
        assert comps.parse_is_cup(row["competition"]) is True
        assert row["competition"]["is_league"] is False
        assert comps.get("national_teams_friendlies").is_cup is True
        assert comps.match_competition_name(row["competition"]["name"],
                                            is_cup=comps.parse_is_cup(row["competition"])) == \
            "national_teams_friendlies"


def test_every_national_team_competition_is_a_cup_and_none_of_the_leagues_are():
    assert set(comps.select_keys(national_teams=True, is_cup=True)) == \
        set(comps.select_keys(national_teams=True))
    assert comps.select_keys(national_teams=True, is_cup=False) == []
    assert comps.select_keys(national_teams=False, is_cup=False) == [
        "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1"]


def test_a_row_that_does_not_classify_itself_is_unknown_and_not_a_league():
    # The trap the is_cup gate springs. `bool(payload.get("is_cup"))` spells "the provider omitted
    # this field" as False, which is a positive claim that the competition is a league, and False
    # then rejects every cup in the registry -- all 34 national-team competitions and the Champions
    # League. `parse_is_cup` keeps "unknown" as None, and None gates nothing.
    assert comps.parse_is_cup({"name": "National Teams Friendlies"}) is None
    assert bool({"name": "National Teams Friendlies"}.get("is_cup")) is False

    unknown = comps.parse_is_cup({"name": "National Teams Friendlies"})
    assert comps.match_competition_name("National Teams Friendlies", is_cup=unknown) == \
        "national_teams_friendlies"
    assert comps.match_competition_name("National Teams Friendlies", is_cup=False) is None
    for key in comps.select_keys(national_teams=True):
        assert comps.match_competition_name(comps.get(key).name, keys=[key], is_cup=None) == key, key


def test_parse_is_cup_reads_every_shape_the_provider_sends_it_in():
    # A string from competitions/list.json, a JSON boolean from a fixture's competition object.
    assert comps.parse_is_cup({"is_cup": "1"}) is True
    assert comps.parse_is_cup({"is_cup": "0"}) is False
    assert comps.parse_is_cup({"is_cup": True}) is True
    assert comps.parse_is_cup({"is_cup": False}) is False
    assert comps.parse_is_cup({}) is None
    assert comps.parse_is_cup({"is_cup": None}) is None


def test_a_stated_is_cup_still_rejects_a_competition_that_disagrees_with_it():
    assert comps.match_competition_name("FIFA World Cup", is_cup=False) is None
    assert comps.match_competition_name("Premier League", country="England", is_cup=True) is None
    assert comps.match_competition_name("Premier League", country="England", is_cup=False) == "premier_league"
    assert comps.match_competition_name("FIFA World Cup", is_cup=True) == "fifa_world_cup"


# ----------------------------------------------------------------- coverage
def test_club_coverage_is_unchanged():
    keys = comps.covered_keys("premier_league,la_liga,serie_a,bundesliga,ligue_1,champions_league", "")
    assert keys == ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league"]


def test_national_coverage_is_additive_and_never_displaces_a_club_competition():
    club = "premier_league,la_liga,serie_a,bundesliga,ligue_1,champions_league"
    keys = comps.covered_keys(club, "fifa_world_cup,uefa_nations_league")
    assert keys[:6] == club.split(",")
    assert keys[6:] == ["fifa_world_cup", "uefa_nations_league"]


def test_coverage_selector_tokens():
    assert comps.national_team_keys("") == []
    assert comps.national_team_keys("none") == []
    assert len(comps.national_team_keys("active")) == 29
    assert len(comps.national_team_keys("all")) == 34
    assert set(comps.national_team_keys("all")) - set(comps.national_team_keys("active")) == set(FLAGGED_DORMANT)


def test_provider_active_filters_exactly_one_selector_and_the_comment_says_so():
    # `provider_active=False` does not keep a competition out of "any coverage selection": it keeps
    # it out of `active`, and `all` and an explicit key both still return it. This test is the
    # claim the registry's dormant block now makes, so the two cannot drift apart again.
    active = comps.national_team_keys("active")
    everything = comps.national_team_keys("all")
    for key in FLAGGED_DORMANT:
        assert key not in active, key
        assert key in everything, key
        assert comps.national_team_keys(key) == [key], key
    assert comps.select_keys(national_teams=True, provider_active=False) == list(FLAGGED_DORMANT)


def test_a_dormant_competition_selected_by_a_setting_is_named_in_the_log(caplog):
    with caplog.at_level("INFO", logger="app.services.providers.competitions"):
        comps.national_team_keys("fifa_world_cup,kirin_cup")
    assert "kirin_cup" in caplog.text
    assert "fifa_world_cup" not in caplog.text


def test_selecting_only_active_competitions_logs_nothing_about_dormant_ones(caplog):
    with caplog.at_level("INFO", logger="app.services.providers.competitions"):
        comps.national_team_keys("active")
    assert caplog.text == ""


def test_unknown_or_club_keys_in_the_national_setting_are_dropped_not_widened():
    assert comps.national_team_keys("fifa_world_cup,not_a_competition") == ["fifa_world_cup"]
    assert comps.national_team_keys("premier_league") == []


def test_misconfiguration_falls_back_to_the_club_six_not_to_everything():
    # The old fallback was "every key in the registry", which is now 40 competitions of requests.
    assert comps.covered_keys("nonsense", "") == list(comps.DEFAULT_COVERED_KEYS)


def test_keys_with_a_verified_provider_id():
    # The club five that have always had ids, plus the two national-team competitions a probe
    # returned. The Champions League is absent on purpose: its id has never been asked for, so it
    # is resolved by name on first use rather than written down.
    assert comps.keys_with_provider_id("gameforecast_id") == [
        "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1",
        "uefa_nations_league", "concacaf_nations_league"]
    assert "fifa_world_cup" in comps.keys_with_provider_id("livescore_id")


# ----------------------------------------------------------------- team identity
def test_womens_teams_are_recognised_by_the_provider_suffix():
    assert comps.is_womens_team_name("Spain (W)") is True
    assert comps.is_womens_team_name("England (W)") is True
    assert comps.is_womens_team_name("Spain") is False
    assert comps.is_womens_team_name("Wales") is False  # a trailing "w" is not a suffix marker
    assert comps.strip_womens_suffix("Spain (W)") == "Spain"


def test_team_scope_separates_clubs_from_national_teams_and_men_from_women():
    assert comps.team_scope("premier_league", "Arsenal") is TeamScope.CLUB_SENIOR_MEN
    assert comps.team_scope("fifa_world_cup", "Spain") is TeamScope.NATIONAL_SENIOR_MEN
    assert comps.team_scope("womens_world_cup", "Spain (W)") is TeamScope.NATIONAL_SENIOR_WOMEN
    # A women's row inside a men's competition is still a women's team.
    assert comps.team_scope("national_teams_friendlies", "Spain (W)") is TeamScope.NATIONAL_SENIOR_WOMEN


def test_name_matching_alone_cannot_keep_these_apart():
    # Not a defect being asserted as correct: this is why identity carries a scope prefix. The club
    # matcher is built to discard suffixes, so it reads "Spain (W)" and "Spain" as one team.
    assert team_names_match("Spain (W)", "Spain") is True
    assert normalize_team_name("Spain (W)") != normalize_team_name("Spain")


def test_identity_keys_cannot_collide_across_scopes():
    national_men = comps.team_identity_key("fifa_world_cup", "Spain")
    national_women = comps.team_identity_key("womens_world_cup", "Spain (W)")
    club = comps.team_identity_key("la_liga", "Spain")
    assert len({national_men, national_women, club}) == 3
    assert national_men == "national_senior_men:spain"
    assert national_women == "national_senior_women:spain"
    # The same guarantee when the caller brings its own normalised name.
    assert comps.team_identity_key("la_liga", "Spain", normalize_team_name("Spain")) != national_men


def test_same_team_scope_rejects_every_cross_scope_pairing():
    assert comps.same_team_scope("fifa_world_cup", "Spain", "uefa_nations_league", "Spain") is True
    assert comps.same_team_scope("fifa_world_cup", "Spain", "la_liga", "Spain") is False
    assert comps.same_team_scope("fifa_world_cup", "Spain", "womens_world_cup", "Spain (W)") is False
    assert comps.same_team_scope("premier_league", "Arsenal", "womens_world_cup", "England (W)") is False


def test_a_national_team_and_a_club_of_the_same_name_are_different_entities():
    # Real collisions in the competitions this product already covers: AS Monaco plays in Ligue 1
    # and Monaco plays in the national-team calendar; FC Andorra is a Spanish club and Andorra is a
    # national team. Both pairs normalise to one string and the club matcher reads them as one team.
    for name, club_key in [("Monaco", "ligue_1"), ("Andorra", "la_liga")]:
        assert team_names_match(name, f"AS {name}") or team_names_match(name, f"FC {name}")
        national = comps.team_identity_key("national_teams_friendlies", name)
        club = comps.team_identity_key(club_key, name)
        assert national != club, name
        assert comps.same_team_scope("national_teams_friendlies", name, club_key, name) is False


def test_one_squad_is_one_row_across_every_competition_of_its_category():
    # The women/men split must not be solved by splitting per competition. Spain in the World Cup
    # and Spain in the Nations League are one team, and so are the two women's rows.
    men = {comps.team_identity_key(key, "Spain")
           for key in ("fifa_world_cup", "uefa_nations_league", "national_teams_friendlies",
                       "world_cup_qualifiers_uefa")}
    assert men == {"national_senior_men:spain"}
    women = {comps.team_identity_key(key, "Spain (W)")
             for key in ("womens_world_cup", "national_teams_friendlies")}
    assert women == {"national_senior_women:spain"}
    assert men.isdisjoint(women)


def test_an_unmatched_competition_reads_as_a_club_and_an_invented_one_raises():
    # None is the provider saying no canonical key matched, which is a club competition here.
    assert comps.team_scope(None, "Arsenal") is comps.DEFAULT_TEAM_SCOPE
    assert comps.DEFAULT_TEAM_SCOPE is TeamScope.CLUB_SENIOR_MEN
    assert comps.team_identity_key(None, "Arsenal") == "club_senior_men:arsenal"
    # A women's suffix still narrows a competition nobody classified.
    assert comps.team_scope(None, "Arsenal (W)") is TeamScope.CLUB_SENIOR_WOMEN
    # A key that does not exist is a caller's mistake, not a provider's, and still says so.
    with pytest.raises(KeyError):
        comps.team_scope("not_a_competition", "Arsenal")


def test_national_scopes_name_every_scope_whose_rows_are_countries():
    assert comps.NATIONAL_SCOPES == {
        TeamScope.NATIONAL_SENIOR_MEN, TeamScope.NATIONAL_SENIOR_WOMEN, TeamScope.NATIONAL_YOUTH}
    for key in comps.select_keys(national_teams=True):
        assert comps.team_scope(key) in comps.NATIONAL_SCOPES, key
    for key in comps.select_keys(national_teams=False):
        assert comps.team_scope(key) not in comps.NATIONAL_SCOPES, key


def test_the_two_fifa_competitions_share_a_country_and_share_no_identity():
    # The measurement this work started from: `_CONFEDERATION_TERRITORY` gives both of them
    # country "World"/"WLD", so the country can never be what tells their teams apart.
    men, women = comps.get("fifa_world_cup"), comps.get("womens_world_cup")
    assert (men.country, men.country_code) == (women.country, women.country_code) == ("World", "WLD")
    assert comps.team_identity_key("fifa_world_cup", "Spain") != \
        comps.team_identity_key("womens_world_cup", "Spain (W)")


def test_scoped_identity_key_is_the_one_spelling_of_an_identity():
    for scope in TeamScope:
        assert comps.scoped_identity_key(scope, "spain") == f"{scope.value}:spain"
    assert len({comps.scoped_identity_key(scope, "spain") for scope in TeamScope}) == len(TeamScope)


def test_a_provider_row_of_womens_national_teams_stays_in_its_own_scope():
    # A real row: "Spain (W) v England (W) 1 - 0".
    home, away = "Spain (W)", "England (W)"
    assert comps.team_scope("womens_world_cup", home) is TeamScope.NATIONAL_SENIOR_WOMEN
    assert comps.team_identity_key("womens_world_cup", home) == "national_senior_women:spain"
    assert comps.team_identity_key("womens_world_cup", away) == "national_senior_women:england"
    assert comps.team_identity_key("fifa_world_cup", "Spain") != comps.team_identity_key("womens_world_cup", home)
