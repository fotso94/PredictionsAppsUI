"""
Canonical competitions covered by the product and their identifiers per provider.

Provider ids differ everywhere (API-Football 39 vs Live Score API "2" vs GameForecast 15 for
the Premier League), so the rest of the code works with canonical keys and asks this module
for the provider-specific id. Unknown ids are resolved at runtime by name matching against the
provider's competition list; explicit overrides can be given through settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from app.services.providers.base import strip_accents


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


COMPETITIONS: Dict[str, CanonicalCompetition] = {
    "premier_league": CanonicalCompetition(
        key="premier_league", name="Premier League", country="England", country_code="ENG", is_cup=False,
        aliases=("premier league",), api_football_id=39, thesportsdb_id=4328, gameforecast_id=15,
    ),
    "la_liga": CanonicalCompetition(
        key="la_liga", name="La Liga", country="Spain", country_code="ESP", is_cup=False,
        aliases=("la liga", "laliga", "primera division", "primera división", "liga ea sports"),
        api_football_id=140, thesportsdb_id=4335,
    ),
    "serie_a": CanonicalCompetition(
        key="serie_a", name="Serie A", country="Italy", country_code="ITA", is_cup=False,
        aliases=("serie a",), api_football_id=135, thesportsdb_id=4332,
    ),
    "bundesliga": CanonicalCompetition(
        key="bundesliga", name="Bundesliga", country="Germany", country_code="GER", is_cup=False,
        aliases=("bundesliga",), api_football_id=78, thesportsdb_id=4331,
    ),
    "ligue_1": CanonicalCompetition(
        key="ligue_1", name="Ligue 1", country="France", country_code="FRA", is_cup=False,
        aliases=("ligue 1", "ligue1"), api_football_id=61, thesportsdb_id=4334,
    ),
    "champions_league": CanonicalCompetition(
        key="champions_league", name="UEFA Champions League", country="Europe", country_code="EUR", is_cup=True,
        aliases=("champions league", "uefa champions league"), api_football_id=2, thesportsdb_id=4480,
        livescore_id=244,
    ),
}

#: Fragments that identify a different competition with a similar name.
EXCLUDED_NAME_FRAGMENTS = (
    "women", "u21", "u19", "u18", "u17", "u23", "youth", "reserve", " ii", "2.", " 2", "femen",
    "qualif", "playoff", "play-off", "amateur", "cup", "super", "rfef", "asia", "afc", "concacaf",
    "copa", "african", "caf ", "premier league 2", "next gen", "femm", "femin", "frauen", "feminine",
)


def covered_keys(setting: str) -> List[str]:
    keys = [k.strip() for k in (setting or "").split(",") if k.strip()]
    return [k for k in keys if k in COMPETITIONS] or list(COMPETITIONS.keys())


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


def match_competition_name(
    name: str,
    country: Optional[str] = None,
    keys: Optional[Iterable[str]] = None,
    is_cup: Optional[bool] = None,
) -> Optional[str]:
    """
    Return the canonical key whose aliases match a provider competition name, or None.

    - Names containing an excluded fragment (women, u21, qualifiers, "2", ...) never match.
    - For domestic leagues the provider country (when given) must agree with ours.
    - "cup" only disqualifies league competitions.
    """
    n = _norm(name)
    if not n:
        return None
    candidates = [COMPETITIONS[k] for k in (keys or COMPETITIONS.keys()) if k in COMPETITIONS]
    country_n = _norm(country) if country else ""
    for comp in candidates:
        if not any(alias in n for alias in comp.aliases):
            continue
        excluded = [frag for frag in EXCLUDED_NAME_FRAGMENTS if frag in n]
        if comp.is_cup:
            excluded = [frag for frag in excluded if frag != "cup"]
        if excluded:
            continue
        if is_cup is not None and is_cup != comp.is_cup:
            continue
        if comp.key != "champions_league" and country_n:
            if country_n not in (_norm(comp.country), _norm(comp.country_code)):
                continue
        return comp.key
    return None
