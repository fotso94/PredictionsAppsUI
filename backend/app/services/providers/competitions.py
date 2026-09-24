"""
Canonical competitions covered by the product and their identifiers per provider.

Provider ids differ everywhere (API-Football 39 vs Live Score API "2" vs GameForecast 15 for
the Premier League), so the rest of the code works with canonical keys and asks this module
for the provider-specific id. Unknown ids are resolved at runtime by name matching against the
provider's competition list; explicit overrides can be given through settings.

Every entry also carries its classification: club or national team, the confederation it belongs
to, and the squad category (senior men, senior women, youth). Those three answers are what the
product groups by, and none of them can be derived from a competition name at runtime without
guessing, so they are written down here once per competition.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from app.services.providers.base import strip_accents

logger = logging.getLogger(__name__)


class Confederation(str, Enum):
    """Football's six continental confederations, plus FIFA for worldwide competitions."""

    FIFA = "FIFA"
    CAF = "CAF"
    UEFA = "UEFA"
    AFC = "AFC"
    CONCACAF = "CONCACAF"
    CONMEBOL = "CONMEBOL"
    OFC = "OFC"


class SquadCategory(str, Enum):
    """Which squad plays the competition. Youth exists here without a single competition behind it."""

    SENIOR_MEN = "senior_men"
    SENIOR_WOMEN = "senior_women"
    YOUTH = "youth"


class TeamScope(str, Enum):
    """
    The kind of entity a team row in a competition is.

    Two teams may only be the same entity when their scopes are identical: "Spain" the national
    team, "Spain (W)" the women's national team and any Spanish club are three different entities
    that a name comparison alone cannot tell apart.
    """

    CLUB_SENIOR_MEN = "club_senior_men"
    CLUB_SENIOR_WOMEN = "club_senior_women"
    CLUB_YOUTH = "club_youth"
    NATIONAL_SENIOR_MEN = "national_senior_men"
    NATIONAL_SENIOR_WOMEN = "national_senior_women"
    NATIONAL_YOUTH = "national_youth"


#: A squad category the provider catalogue has at least one competition for.
SUPPORT_COVERED = "covered"
#: A squad category no competition in the provider catalogue belongs to. Reported, never omitted:
#: "we do not cover it" and "the provider does not carry it" are different answers to the same question.
SUPPORT_UNSUPPORTED = "unsupported_by_provider"


@dataclass(frozen=True)
class CanonicalCompetition:
    key: str
    name: str
    country: str
    country_code: str
    is_cup: bool
    #: lowercase name fragments accepted when matching a provider competition name
    aliases: tuple
    #: default provider ids (may be overridden by settings)
    api_football_id: Optional[int] = None
    thesportsdb_id: Optional[int] = None
    gameforecast_id: Optional[int] = None
    livescore_id: Optional[int] = None
    #: national teams play it (Spain), as opposed to clubs (Real Madrid)
    is_national_team: bool = False
    confederation: Optional[Confederation] = None
    squad_category: SquadCategory = SquadCategory.SENIOR_MEN
    #: the provider still schedules it (Live Score `active`); a dormant competition keeps its id
    provider_active: bool = True


# Display country/code per confederation. National-team competitions have no single country -
# Live Score sends `countries: []` for all 31 of them - so these stand in for one and are never
# used to accept or reject a name match (see `match_competition_name`).
#
# They are a property of the COMPETITION and say nothing about any team that plays in it. Two FIFA
# competitions share "World" by construction, so this value can never be what separates one squad
# from another: that is `TeamScope`'s job and only `TeamScope`'s.
_CONFEDERATION_TERRITORY: Dict[Confederation, Tuple[str, str]] = {
    Confederation.FIFA: ("World", "WLD"),
    Confederation.UEFA: ("Europe", "EUR"),
    Confederation.CAF: ("Africa", "AFR"),
    Confederation.AFC: ("Asia", "ASI"),
    Confederation.CONCACAF: ("North America", "NCA"),
    Confederation.CONMEBOL: ("South America", "SAM"),
    Confederation.OFC: ("Oceania", "OCE"),
}


def _national(
    key: str,
    name: str,
    livescore_id: int,
    confederation: Confederation,
    aliases: tuple,
    *,
    provider_active: bool = True,
    squad_category: SquadCategory = SquadCategory.SENIOR_MEN,
    is_cup: bool = True,
    gameforecast_id: Optional[int] = None,
) -> CanonicalCompetition:
    """
    Build a national-team entry.

    api_football_id, thesportsdb_id and gameforecast_id stay None: a guessed id attaches another
    competition's fixtures and results to these matches, and unlike a missing id that failure is
    silent. Each of the other providers' ids has to be verified against that provider before it
    is written here.

    `is_cup` defaults to True because that is the value Live Score publishes for all 34 of these,
    read from the provider and not reasoned about. 31 of them are in
    `docs/evidence/livescore-national-team-catalogue.json`; the other three were read from
    `competitions/list.json` on 2026-09-23 and are pinned in
    `tests/providers/test_national_team_competitions.py` as `MEASURED_IS_CUP`. That includes
    National Teams Friendlies, which the provider publishes as is_cup "1" in the catalogue and
    `is_cup: true, is_league: false` inside each of its own fixture rows. A friendlies calendar does
    not look like a cup from the outside, and the value here is the provider's answer rather than
    that impression, because the provider is the thing the rest of this module has to agree with.
    """
    country, code = _CONFEDERATION_TERRITORY[confederation]
    return CanonicalCompetition(
        key=key, name=name, country=country, country_code=code, is_cup=is_cup, aliases=aliases,
        livescore_id=livescore_id, is_national_team=True, confederation=confederation,
        squad_category=squad_category, provider_active=provider_active, gameforecast_id=gameforecast_id,
    )


#: Provider ids confirmed against live responses, so a cache flush never re-pays discovery out of a
#: ten-request daily allowance. GameForecastAPI ids verified 2026-09-17/18: Premier League 15,
#: La Liga 13, Serie A 3, Bundesliga 14, Ligue 1 4. The Champions League id is still unknown - it is
#: resolved by name on first use, which is why it carries no gameforecast_id here.
#:
#: Live Score ids for the national-team block were read from `competitions/list.json` on 2026-09-23
#: (523 competitions in one response); the names are the provider's own spellings, which is what the
#: aliases match against.
COMPETITIONS: Dict[str, CanonicalCompetition] = {
    "premier_league": CanonicalCompetition(
        key="premier_league", name="Premier League", country="England", country_code="ENG", is_cup=False,
        aliases=("premier league",), api_football_id=39, thesportsdb_id=4328, gameforecast_id=15, livescore_id=2,
        confederation=Confederation.UEFA,
    ),
    "la_liga": CanonicalCompetition(
        key="la_liga", name="La Liga", country="Spain", country_code="ESP", is_cup=False,
        aliases=("la liga", "laliga", "primera division", "primera división", "liga ea sports"),
        api_football_id=140, thesportsdb_id=4335, gameforecast_id=13, livescore_id=3,
        confederation=Confederation.UEFA,
    ),
    "serie_a": CanonicalCompetition(
        key="serie_a", name="Serie A", country="Italy", country_code="ITA", is_cup=False,
        aliases=("serie a",), api_football_id=135, thesportsdb_id=4332, gameforecast_id=3, livescore_id=4,
        confederation=Confederation.UEFA,
    ),
    "bundesliga": CanonicalCompetition(
        key="bundesliga", name="Bundesliga", country="Germany", country_code="GER", is_cup=False,
        aliases=("bundesliga",), api_football_id=78, thesportsdb_id=4331, gameforecast_id=14, livescore_id=1,
        confederation=Confederation.UEFA,
    ),
    "ligue_1": CanonicalCompetition(
        key="ligue_1", name="Ligue 1", country="France", country_code="FRA", is_cup=False,
        aliases=("ligue 1", "ligue1"), api_football_id=61, thesportsdb_id=4334, gameforecast_id=4, livescore_id=5,
        confederation=Confederation.UEFA,
    ),
    "champions_league": CanonicalCompetition(
        key="champions_league", name="UEFA Champions League", country="Europe", country_code="EUR", is_cup=True,
        aliases=("champions league", "uefa champions league"), api_football_id=2, thesportsdb_id=4480,
        livescore_id=244, confederation=Confederation.UEFA,
    ),

    # ---------------------------------------------------------------- FIFA World Cup and its qualifiers
    # "fifa world cup" is the alias rather than "world cup": the bare phrase is a substring of every
    # qualifier name and of "Women's World Cup", so it would swallow eight other competitions.
    "fifa_world_cup": _national(
        "fifa_world_cup", "FIFA World Cup", 362, Confederation.FIFA, ("fifa world cup",)),
    "world_cup_inter_confederation_playoff": _national(
        "world_cup_inter_confederation_playoff", "World Cup Inter-Confederation Play-Off", 365, Confederation.FIFA,
        ("world cup inter-confederation play-off", "world cup inter confederation play off",
         "inter-confederation play-off")),
    "world_cup_qualifiers_uefa": _national(
        "world_cup_qualifiers_uefa", "World Cup UEFA Qualifiers", 363, Confederation.UEFA,
        ("world cup uefa qualifiers",)),
    "world_cup_qualifiers_caf": _national(
        "world_cup_qualifiers_caf", "World Cup CAF Qualifiers", 359, Confederation.CAF,
        ("world cup caf qualifiers",)),
    "world_cup_qualifiers_afc": _national(
        "world_cup_qualifiers_afc", "World Cup AFC Qualifiers", 358, Confederation.AFC,
        ("world cup afc qualifiers",)),
    "world_cup_qualifiers_concacaf": _national(
        "world_cup_qualifiers_concacaf", "World Cup CONCACAF Qualifiers", 360, Confederation.CONCACAF,
        ("world cup concacaf qualifiers",)),
    "world_cup_qualifiers_conmebol": _national(
        "world_cup_qualifiers_conmebol", "World Cup CONMEBOL Qualifiers", 361, Confederation.CONMEBOL,
        ("world cup conmebol qualifiers",)),
    "world_cup_qualifiers_ofc": _national(
        "world_cup_qualifiers_ofc", "World Cup OFC Qualifiers", 364, Confederation.OFC,
        ("world cup ofc qualifiers",)),

    # ---------------------------------------------------------------- UEFA
    # "nations league" alone is never an alias: UEFA's and CONCACAF's share it.
    # GameForecast id 36, returned by a name-targeted /leagues probe on 2026-09-23 and recorded in
    # docs/evidence/gameforecast-league-catalogue.json. It is written here rather than resolved at
    # runtime because discovery costs a request out of an allowance of eight a day, and because an
    # id that was asked for and answered is not a guess. A competition with no id here is simply
    # not offered to the forecast rotation, which is the safe half of the trade.
    "uefa_nations_league": _national(
        "uefa_nations_league", "UEFA Nations League", 350, Confederation.UEFA, ("uefa nations league",),
        gameforecast_id=36),
    "uefa_euro_qualification": _national(
        "uefa_euro_qualification", "UEFA EURO Qualification", 274, Confederation.UEFA,
        ("uefa euro qualification", "uefa euro qualifiers", "european championship qualification")),

    # ---------------------------------------------------------------- CAF
    # Four competitions, two pairs of near-identical names. The Cup of Nations is the senior
    # continental championship; the Nations Championship (CHAN) is a different competition, and each
    # has its own qualifying competition.
    "africa_cup_of_nations": _national(
        "africa_cup_of_nations", "African Cup of Nations", 227, Confederation.CAF,
        ("african cup of nations", "africa cup of nations", "afcon")),
    "africa_cup_of_nations_qualification": _national(
        "africa_cup_of_nations_qualification", "Africa Cup of Nations Qualifications", 228, Confederation.CAF,
        ("africa cup of nations qualifications", "africa cup of nations qualification",
         "african cup of nations qualification", "africa cup of nations qualifiers")),
    "african_nations_championship": _national(
        "african_nations_championship", "African Nations Championship", 226, Confederation.CAF,
        ("african nations championship", "chan")),
    "african_nations_championship_qualification": _national(
        "african_nations_championship_qualification", "African Nations Championship Qualification", 403,
        Confederation.CAF, ("african nations championship qualification",
                            "african nations championship qualifiers")),
    "cosafa_cup": _national("cosafa_cup", "COSAFA Cup", 225, Confederation.CAF, ("cosafa cup",)),

    # ---------------------------------------------------------------- AFC
    "asian_cup": _national("asian_cup", "Asian Cup", 240, Confederation.AFC, ("asian cup",)),
    "asian_cup_qualification": _national(
        "asian_cup_qualification", "Asian Cup Qualification", 241, Confederation.AFC,
        ("asian cup qualification", "asian cup qualifiers")),
    "aff_suzuki_cup": _national(
        "aff_suzuki_cup", "AFF Suzuki Cup", 246, Confederation.AFC,
        ("aff suzuki cup", "asean championship")),
    "saff_championship": _national(
        "saff_championship", "SAFF Championship", 247, Confederation.AFC, ("saff championship",)),
    # Every entrant is an AFC member association.
    "arabian_gulf_cup": _national(
        "arabian_gulf_cup", "Arabian Gulf Cup", 412, Confederation.AFC, ("arabian gulf cup", "gulf cup")),
    # Entrants are Arab associations from both AFC and CAF, so the confederation recorded is the
    # organiser rather than an entry restriction.
    "arab_cup": _national("arab_cup", "Arab Cup", 452, Confederation.FIFA, ("arab cup",)),

    # ---------------------------------------------------------------- CONCACAF
    "gold_cup": _national("gold_cup", "Gold Cup", 266, Confederation.CONCACAF, ("gold cup",)),
    "gold_cup_qualifiers": _national(
        "gold_cup_qualifiers", "Gold Cup Qualifiers", 435, Confederation.CONCACAF,
        ("gold cup qualifiers", "gold cup qualification")),
    # GameForecast id 38, from the same probe as UEFA Nations League above.
    "concacaf_nations_league": _national(
        "concacaf_nations_league", "CONCACAF Nations League", 391, Confederation.CONCACAF,
        ("concacaf nations league",), gameforecast_id=38),
    "concacaf_nations_league_qualification": _national(
        "concacaf_nations_league_qualification", "CONCACAF Nations League Qualification", 269,
        Confederation.CONCACAF, ("concacaf nations league qualification",
                                 "concacaf nations league qualifiers")),

    # ---------------------------------------------------------------- CONMEBOL
    # Live Score flags this one national_teams_only="0". The flag is wrong, and trusting it alone
    # drops South America's continental championship. Its is_cup was read from the same response as
    # the flag on 2026-09-23 and is "1", like every other row in this block.
    "copa_america": _national(
        "copa_america", "Copa America", 271, Confederation.CONMEBOL, ("copa america", "copa américa")),

    # ---------------------------------------------------------------- worldwide
    # Also flagged national_teams_only="0" by the provider: every international friendly sits here.
    # This is the competition with fixtures on 2026-09-23 (Azerbaijan v Tajikistan and Gibraltar v
    # Sao Tome And Principe, both 16:00 UTC). The provider publishes it as is_cup "1" in
    # competitions/list.json AND as `is_cup: true, is_league: false` inside each of those fixture
    # rows, so True here is what the provider says rather than what a friendlies calendar looks like.
    "national_teams_friendlies": _national(
        "national_teams_friendlies", "National Teams Friendlies", 371, Confederation.FIFA,
        ("national teams friendlies", "international friendlies")),
    # The third competition the flag misses, and the whole of the provider's women's coverage. Its
    # is_cup came from the same 2026-09-23 response and is "1".
    "womens_world_cup": _national(
        "womens_world_cup", "Women's World Cup", 490, Confederation.FIFA,
        ("women's world cup", "womens world cup"), squad_category=SquadCategory.SENIOR_WOMEN),
    # The provider publishes no age marker on this row and its catalogue has no U-age competition at
    # AGE-RESTRICTED BY THE TOURNAMENT'S OWN RULES, THOUGH THE PROVIDER NEVER SAYS SO.
    # Live Score publishes no age field, so the registry classifies these three from the entry rules
    # their governing bodies publish: Olympic men's football is under-23 with three overage players,
    # the Toulon festival is under-21/under-23, and Southeast Asian Games football is under-22.
    #
    # The classification is deliberately NOT left at the provider's silence, because the squad
    # category is part of a team's stored identity and the two mistakes are not the same size. Call
    # a youth squad senior and Spain's under-23 result lands on Spain's senior row and its record;
    # call a senior squad youth and the only cost is a second team row that a person can merge. The
    # cheap error is the one to take.
    "olympic_games_football": _national(
        "olympic_games_football", "Olympic Games Football Tournament", 385, Confederation.FIFA,
        ("olympic games football tournament", "olympic games football"),
        squad_category=SquadCategory.YOUTH),

    # ---------------------------------------------------------------- dormant (Live Score active="0")
    # Ids kept so a returning competition needs no rediscovery. `provider_active=False` keeps them out
    # of ONE selection: the `active` token, which is what `select_keys(provider_active=True)` answers.
    # `all` returns them alongside the other 29 and naming one explicitly returns it, both on purpose -
    # a competition the provider wakes up is then covered by a settings change rather than by editing
    # this file. `national_team_keys` logs which dormant competitions a setting selected, so an empty
    # fixture list is never the first sign of it.
    "fifa_confederations_cup": _national(
        "fifa_confederations_cup", "FIFA Confederations Cup", 270, Confederation.FIFA,
        ("fifa confederations cup", "confederations cup"), provider_active=False),
    "kings_cup": _national(
        "kings_cup", "King's Cup", 373, Confederation.AFC, ("king's cup", "kings cup"), provider_active=False),
    "kirin_cup": _national(
        "kirin_cup", "Kirin Cup", 374, Confederation.AFC, ("kirin cup",), provider_active=False),
    "southeast_asian_games": _national(
        "southeast_asian_games", "Southeast Asian Games", 248, Confederation.AFC,
        ("southeast asian games", "south east asian games"),
        squad_category=SquadCategory.YOUTH, provider_active=False),
    # Hosted in France; the confederation recorded is the host's, since the invitation list is not
    # restricted to one confederation and the provider states nothing about it.
    "toulon": _national("toulon", "Toulon", 377, Confederation.UEFA, ("toulon",),
                        squad_category=SquadCategory.YOUTH, provider_active=False),
}

#: The club competitions the product has always covered. `covered_keys` falls back to these rather
#: than to every key in the registry: a misconfigured setting must not silently enable 40
#: competitions' worth of provider requests.
DEFAULT_COVERED_KEYS: Tuple[str, ...] = (
    "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league",
)

#: Fragments that identify a different competition with a similar name. A fragment only disqualifies
#: a candidate when the candidate's OWN name and aliases do not contain it, so "qualif" rejects
#: "Asian Cup Qualification" for `asian_cup` and accepts it for `asian_cup_qualification`.
EXCLUDED_NAME_FRAGMENTS = (
    "women", "u21", "u19", "u18", "u17", "u23", "youth", "reserve", " ii", "2.", " 2", "femen",
    "u20", "u-17", "u-18", "u-19", "u-20", "u-21", "u-23",
    "qualif", "playoff", "play-off", "amateur", "cup", "super", "rfef", "asia", "afc", "concacaf",
    "copa", "african", "caf ", "premier league 2", "next gen", "femm", "femin", "frauen", "feminine",
    # Live Score API list (verified 2026-09-17): "Non Premier League", "2nd Bundesliga", regional leagues
    "2nd", "3rd", "second", "third", "non premier", "national", "northern", "southern", "mainland",
    "territory", "summer series", "trophy", "welsh", "west bank", "sg.", "tt ", "state league", "regional",
)
# Confederations whose "Champions League" is ours
EUROPEAN_FEDERATIONS = ("uefa", "europe")

#: Season markers a provider may append ("Serie A 2026/2027"). Removed before the fragment test so a
#: year never trips " 2", and only there: "Premier League 2" carries no year and stays excluded.
_SEASON_MARKER = re.compile(r"\b(?:19|20)\d{2}(?:\s*[/-]\s*(?:\d{2}|\d{4}))?\b")

_TRUE_FLAGS = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE_FLAGS = frozenset({"0", "false", "f", "no", "n", "off", ""})


def parse_provider_flag(value: object, field: str = "flag", default: bool = False) -> bool:
    """
    Turn a provider's flag into a bool, whatever shape it arrives in.

    Live Score sends `national_teams_only` and `active` as the STRINGS "0" and "1", and "0" is
    truthy in Python: `if item["national_teams_only"]` classifies all 523 competitions as
    national-team ones. Every flag in this module goes through here, and anything unrecognised
    returns `default` and is logged rather than being read as True, so a provider that changes
    shape produces a visible warning instead of silently inverting every classification.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _TRUE_FLAGS:
        return True
    if text in _FALSE_FLAGS:
        return False
    logger.warning("Unrecognised provider %s value %r; treating it as %s", field, value, default)
    return default


def _national_team_ids(provider_attr: str) -> FrozenSet[int]:
    return frozenset(
        getattr(comp, provider_attr) for comp in COMPETITIONS.values()
        if comp.is_national_team and getattr(comp, provider_attr) is not None
    )


#: Live Score ids of every national-team competition in the registry, verified against
#: `competitions/list.json`. Needed because the provider's own flag is wrong for three of them.
LIVESCORE_NATIONAL_TEAM_IDS: FrozenSet[int] = _national_team_ids("livescore_id")


def is_national_team_payload(payload: Dict[str, object]) -> bool:
    """
    Is this Live Score competition row a national-team competition?

    The flag alone is not enough. 271 Copa America, 371 National Teams Friendlies and 490 Women's
    World Cup are all sent with national_teams_only="0" - a continental championship, every
    international friendly and the entire women's category - so the verified ids decide as well.
    """
    flag = parse_provider_flag(payload.get("national_teams_only"), field="national_teams_only")
    raw_id = str(payload.get("id") or "").strip()
    return flag or (raw_id.isdigit() and int(raw_id) in LIVESCORE_NATIONAL_TEAM_IDS)


def is_active_payload(payload: Dict[str, object]) -> bool:
    """Does the provider still schedule this competition? `active` is a string flag too."""
    return parse_provider_flag(payload.get("active"), field="active")


def parse_is_cup(payload: Dict[str, object]) -> Optional[bool]:
    """
    A competition row's cup/league classification: True, False, or None for "the row does not say".

    The three answers have to stay three. `bool(payload.get("is_cup"))` collapses the last two into
    False, and False is a positive claim that `match_competition_name` acts on: it rejects every
    competition the registry calls a cup, which is all 34 national-team ones and the Champions
    League. A provider row that simply omits the field then resolves them all to nothing.

    The value goes through `parse_provider_flag` rather than being compared to anything, because it
    arrives in more than one shape: Live Score sends it as the string "1"/"0" in
    `competitions/list.json` and as a JSON boolean inside a fixture's own `competition` object.
    """
    value = payload.get("is_cup")
    if value is None:
        return None
    return parse_provider_flag(value, field="is_cup")


def squad_category_support() -> Dict[SquadCategory, str]:
    """
    Per squad category: is there a competition to cover at all?

    Youth reports `unsupported_by_provider` because the provider's 523-competition catalogue
    contains no U-age or youth national-team competition - not because the product declined to
    cover it. The answer follows the registry, so the day such a competition is added it flips.
    """
    return {
        category: (SUPPORT_COVERED if any(
            comp.is_national_team and comp.squad_category is category for comp in COMPETITIONS.values()
        ) else SUPPORT_UNSUPPORTED)
        for category in SquadCategory
    }


def unsupported_squad_categories() -> List[SquadCategory]:
    return [cat for cat, status in squad_category_support().items() if status == SUPPORT_UNSUPPORTED]


#: The scopes whose rows are countries rather than clubs. A competition's country is the
#: confederation's territory, which is not any of these teams' country, so callers use this to know
#: not to write one onto a team row.
NATIONAL_SCOPES: FrozenSet[TeamScope] = frozenset({
    TeamScope.NATIONAL_SENIOR_MEN, TeamScope.NATIONAL_SENIOR_WOMEN, TeamScope.NATIONAL_YOUTH,
})

#: The scope a team is read as when nothing classifies its competition. Every one of the 98 team
#: rows this installation held before national-team coverage existed is one of these, and a national
#: team can only be stored as one by a competition that IS in the registry, so the default costs a
#: club nothing and can never turn a country into a club by accident.
DEFAULT_TEAM_SCOPE = TeamScope.CLUB_SENIOR_MEN


_SCOPES: Dict[Tuple[bool, SquadCategory], TeamScope] = {
    (False, SquadCategory.SENIOR_MEN): TeamScope.CLUB_SENIOR_MEN,
    (False, SquadCategory.SENIOR_WOMEN): TeamScope.CLUB_SENIOR_WOMEN,
    (False, SquadCategory.YOUTH): TeamScope.CLUB_YOUTH,
    (True, SquadCategory.SENIOR_MEN): TeamScope.NATIONAL_SENIOR_MEN,
    (True, SquadCategory.SENIOR_WOMEN): TeamScope.NATIONAL_SENIOR_WOMEN,
    (True, SquadCategory.YOUTH): TeamScope.NATIONAL_YOUTH,
}

#: Live Score marks a women's team by a suffix on the team name: "Spain (W) v England (W) 1 - 0".
_WOMENS_TEAM_SUFFIX = re.compile(r"\(\s*w(?:omen)?\s*\)\s*$", re.IGNORECASE)


def is_womens_team_name(name: Optional[str]) -> bool:
    return bool(_WOMENS_TEAM_SUFFIX.search((name or "").strip()))


def strip_womens_suffix(name: Optional[str]) -> str:
    return _WOMENS_TEAM_SUFFIX.sub("", (name or "").strip()).strip()


def team_scope(competition_key: Optional[str], team_name: Optional[str] = None) -> TeamScope:
    """
    What kind of entity plays under this competition key.

    The competition decides, because the competition is known before any name is compared. The
    name only ever narrows further: a "(W)" suffix inside a men's competition means the row is a
    women's team however the competition is classified, so the two can never share a scope.

    `None` is the provider saying no canonical key matched its competition, and reads as
    `DEFAULT_TEAM_SCOPE`. An unknown key is not that: it is a caller naming a competition that does
    not exist, and still raises.
    """
    if competition_key is None:
        is_national, category = False, SquadCategory.SENIOR_MEN
    else:
        comp = get(competition_key)
        is_national, category = comp.is_national_team, comp.squad_category
    if team_name and is_womens_team_name(team_name) and category is SquadCategory.SENIOR_MEN:
        category = SquadCategory.SENIOR_WOMEN
    return _SCOPES[(is_national, category)]


def scoped_identity_key(scope: TeamScope, normalised_name: str) -> str:
    """
    The one spelling of a team identity, so every caller writes and reads the same string.

    Kept apart from `team_identity_key` because the storage layer knows a row's scope without
    knowing which competition it came from: a stored team's scope is a fact about the team.
    """
    return f"{scope.value}:{normalised_name}"


def team_identity_key(competition_key: Optional[str], team_name: str,
                      normalised_name: Optional[str] = None) -> str:
    """
    A team identity that cannot collide across scopes: "national_senior_men:spain".

    Name comparison alone cannot keep these apart - "Spain" and "Spain (W)" differ by a suffix that
    every club-name matcher is built to discard, and a Spanish club named after the country would
    compare equal to both. Prefixing the scope makes the collision impossible instead of unlikely:
    two identities can only be equal when the competitions agree on club-vs-national AND on squad
    category. `normalised_name` lets a caller keep its own name normalisation (match_matching's, for
    instance) while still taking the prefix from here.

    The suffix is stripped from the name before it is normalised, so Spain's women's squad is
    "national_senior_women:spain" in every competition it plays. Two competitions of one category
    are still ONE team: the World Cup's Spain and the Nations League's Spain share this key.
    """
    base = normalised_name if normalised_name is not None else _norm(strip_womens_suffix(team_name))
    return scoped_identity_key(team_scope(competition_key, team_name), base)


def same_team_scope(competition_key_a: Optional[str], name_a: str,
                    competition_key_b: Optional[str], name_b: str) -> bool:
    """Could a team row in one competition be the same entity as a team row in the other?"""
    return team_scope(competition_key_a, name_a) is team_scope(competition_key_b, name_b)


def select_keys(
    national_teams: Optional[bool] = None,
    confederation: Optional[Confederation] = None,
    squad_category: Optional[SquadCategory] = None,
    provider_active: Optional[bool] = None,
    is_cup: Optional[bool] = None,
) -> List[str]:
    """
    Every registry key matching the given classification, in registry order.

    The query exists so coverage can be decided by a question ("which CAF senior-men competitions
    does the provider still run?") instead of by a list somebody has to keep up to date.
    """
    out: List[str] = []
    for key, comp in COMPETITIONS.items():
        if national_teams is not None and comp.is_national_team is not national_teams:
            continue
        if confederation is not None and comp.confederation is not confederation:
            continue
        if squad_category is not None and comp.squad_category is not squad_category:
            continue
        if provider_active is not None and comp.provider_active is not provider_active:
            continue
        if is_cup is not None and comp.is_cup is not is_cup:
            continue
        out.append(key)
    return out


def keys_with_provider_id(provider_attr: str) -> List[str]:
    """
    Keys that carry a verified id for `provider_attr` ("gameforecast_id", "api_football_id", ...).

    A caller with a small daily allowance can ask for these instead of offering every covered key to
    a provider that would have to spend a discovery request to find out it has no such competition.
    """
    return [key for key, comp in COMPETITIONS.items() if getattr(comp, provider_attr, None) is not None]


#: Tokens accepted by the national-team coverage setting in place of an explicit list of keys.
NATIONAL_SELECTOR_NONE = ("", "none", "off", "false", "0")
NATIONAL_SELECTOR_ALL = ("all",)
NATIONAL_SELECTOR_ACTIVE = ("active", "all_active")


def national_team_keys(setting: Optional[str]) -> List[str]:
    """
    Resolve the national-team coverage setting into keys.

    Accepts an explicit comma-separated list, `active` (every national-team competition the provider
    still schedules), `all` (those plus the dormant ones), or nothing at all. An unknown key is
    dropped with a warning rather than widening the selection.

    `all` and an explicit key both select dormant competitions, which is the point of keeping them in
    the registry. Only `active` filters them out, so the ones a setting picked up are named in the
    log: a competition the provider no longer schedules returns no fixtures, and that is not a
    symptom anybody should have to diagnose from an empty list.
    """
    token = (setting or "").strip().lower()
    if token in NATIONAL_SELECTOR_NONE:
        return []
    if token in NATIONAL_SELECTOR_ACTIVE:
        return select_keys(national_teams=True, provider_active=True)
    if token in NATIONAL_SELECTOR_ALL:
        keys = select_keys(national_teams=True)
    else:
        keys = []
        for part in token.split(","):
            key = part.strip()
            if not key:
                continue
            comp = COMPETITIONS.get(key)
            if comp is None:
                logger.warning("Unknown national-team competition key %r in coverage setting", key)
                continue
            if not comp.is_national_team:
                logger.warning("%r is a club competition; it belongs in COVERED_COMPETITIONS", key)
                continue
            keys.append(key)
    dormant = [key for key in keys if not COMPETITIONS[key].provider_active]
    if dormant:
        logger.info("National-team coverage includes %s dormant competition(s) the provider does not "
                    "currently schedule: %s", len(dormant), ", ".join(dormant))
    return keys


def _configured_national_setting() -> str:
    # Read here rather than at each call site: the callers pass the club setting only, and coverage
    # has to stay one answer. Imported inside the function so this module keeps no import-time
    # dependency on configuration.
    try:
        from app.core.config import settings

        return getattr(settings, "COVERED_NATIONAL_TEAM_COMPETITIONS", "") or ""
    except Exception:  # pragma: no cover - configuration must never break competition lookup
        logger.warning("Could not read COVERED_NATIONAL_TEAM_COMPETITIONS; covering club competitions only")
        return ""


def covered_keys(setting: str, national_setting: Optional[str] = None) -> List[str]:
    """
    The competitions the product covers: the configured club set, plus the national-team set.

    The two are separate settings because they answer to different constraints - the club six are a
    fixed weekly calendar, the national-team competitions run in windows and are mostly dormant in
    between - and because adding a national-team competition must never be able to drop a club one.
    """
    keys = [k.strip() for k in (setting or "").split(",") if k.strip()]
    selected = [k for k in keys if k in COMPETITIONS] or list(DEFAULT_COVERED_KEYS)
    national = national_team_keys(
        national_setting if national_setting is not None else _configured_national_setting())
    return selected + [k for k in national if k not in selected]


def get(key: str) -> CanonicalCompetition:
    if key not in COMPETITIONS:
        raise KeyError(f"Unknown competition key: {key}")
    return COMPETITIONS[key]


def parse_id_overrides(setting: Optional[str]) -> Dict[str, str]:
    """Parse "premier_league=2,la_liga=3" into a dict of canonical key -> provider id."""
    result: Dict[str, str] = {}
    for part in (setting or "").split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            key, value = key.strip(), value.strip()
            if key in COMPETITIONS and value:
                result[key] = value
    return result


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", strip_accents(text or "").lower()).strip()


#: How each confederation writes itself into a competition name. A confederation token only tells
#: competitions apart when they belong to DIFFERENT confederations ("AFC Champions League" is not
#: ours; "AFC Asian Cup" and "CONCACAF Gold Cup" are the same competitions as "Asian Cup" and "Gold
#: Cup"), so a competition is never rejected for carrying the name of its own confederation.
_CONFEDERATION_TOKENS: Dict[Confederation, str] = {
    Confederation.FIFA: " fifa world ",
    Confederation.UEFA: " uefa europe european ",
    Confederation.CAF: " caf african africa ",
    Confederation.AFC: " afc asia asian ",
    Confederation.CONCACAF: " concacaf north america ",
    Confederation.CONMEBOL: " conmebol south america ",
    Confederation.OFC: " ofc oceania ",
}


def _own_fragments(comp: CanonicalCompetition) -> FrozenSet[str]:
    """Excluded fragments carried by the competition's own name, aliases or confederation."""
    own = " ".join([_norm(comp.name)] + [_norm(alias) for alias in comp.aliases])
    if comp.confederation is not None:
        own += _CONFEDERATION_TOKENS[comp.confederation]
    return frozenset(frag for frag in EXCLUDED_NAME_FRAGMENTS if frag in own)


_OWN_FRAGMENTS: Dict[str, FrozenSet[str]] = {key: _own_fragments(comp) for key, comp in COMPETITIONS.items()}


def match_competition_name(
    name: str,
    country: Optional[str] = None,
    keys: Optional[Iterable[str]] = None,
    is_cup: Optional[bool] = None,
    exact: bool = False,
) -> Optional[str]:
    """
    Return the canonical key whose aliases match a provider competition name, or None.
    - `exact=True` requires the whole normalised name to equal an alias ("Premier League"), which
      callers try first; the substring pass ("LaLiga Santander") is only a fallback.
    - A name carrying an excluded fragment (women, u21, "2nd", "non premier", ...) never matches a
      competition whose own name does not carry that fragment: "Asian Cup Qualification" is rejected
      for `asian_cup` by "qualif" and accepted for `asian_cup_qualification`, which is spelt with it.
    - For domestic leagues the provider country (when given) must agree with ours. National-team
      competitions are exempt: they have no country, and the country on a fixture is the host's.
    - The Champions League must belong to UEFA/Europe when a federation or country is given.
    - "cup" only disqualifies league competitions.
    - `is_cup` rejects a candidate that disagrees with it, and `None` means the provider did not say.
      Pass it through `parse_is_cup`, never as `bool(payload.get("is_cup"))`: that spells a field the
      provider omitted as False, which is a positive claim that this is a league, and it then rejects
      every cup in the registry. All 34 national-team competitions are is_cup True, so a caller that
      makes that mistake resolves the entire national-team calendar to None.
    """
    n = _norm(name)
    if not n:
        return None
    fragment_subject = _SEASON_MARKER.sub(" ", n)
    candidates = [COMPETITIONS[k] for k in (keys or COMPETITIONS.keys()) if k in COMPETITIONS]
    country_n = _norm(country) if country else ""
    for comp in candidates:
        aliases = [_norm(a) for a in comp.aliases]
        if exact:
            if n not in aliases:
                continue
        elif not any(alias in n for alias in aliases):
            continue
        allowed = _OWN_FRAGMENTS.get(comp.key, frozenset())
        excluded = [frag for frag in EXCLUDED_NAME_FRAGMENTS
                    if frag in fragment_subject and frag not in allowed]
        if comp.is_cup:
            excluded = [frag for frag in excluded if frag != "cup"]
        if excluded:
            continue
        if is_cup is not None and is_cup != comp.is_cup:
            continue
        if not comp.is_national_team:
            if comp.key == "champions_league":
                if country_n and country_n not in EUROPEAN_FEDERATIONS:
                    continue
            elif country_n and country_n not in (_norm(comp.country), _norm(comp.country_code)):
                continue
        return comp.key
    return None


def resolve_competitions(items: Iterable[tuple], keys: Iterable[str]) -> Dict[str, int]:
    """
    Two-pass resolution over provider rows (index, name, country, is_cup): exact alias matches first,
    substring matches only for keys still unresolved. Returns key -> row index.
    """
    rows = list(items)
    wanted = [k for k in keys if k in COMPETITIONS]
    found: Dict[str, int] = {}
    for exact in (True, False):
        missing = [k for k in wanted if k not in found]
        if not missing:
            break
        for index, name, country, is_cup in rows:
            key = match_competition_name(name, country=country, keys=missing, is_cup=is_cup, exact=exact)
            if key and key not in found:
                found[key] = index
    return found
