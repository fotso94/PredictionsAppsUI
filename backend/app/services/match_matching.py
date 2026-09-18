"""
Cross-provider fixture matching.

Live Score API, GameForecastAPI, API-Football and TheSportsDB all use different fixture and team
ids. A record from one provider is attached to an internal match only when the competition, both
team names and the UTC kickoff agree. Anything uncertain is reported as `ambiguous` and left
unattached; callers must never guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Iterable, List, Optional

from app.services.providers.base import strip_accents

# Tokens that carry no identity (club-type suffixes/prefixes)
_NOISE_TOKENS = {
    "fc", "cf", "sc", "afc", "ac", "as", "ss", "us", "club", "de", "cd", "ud", "sd", "rc", "rcd", "calcio",
    "bc", "fk", "sv", "tsg", "vfb", "vfl", "bsc", "sport", "football", "the", "1", "1899", "1900", "1904", "1909",
    "05", "04", "96", "98", "ssc", "cp", "ssd", "asd", "cfc",
}
# Tokens shared by several clubs (cities, generic prefixes): a single one of them never identifies a team
_SHARED_TOKENS = {
    "madrid", "milan", "milano", "manchester", "sheffield", "paris", "london", "munich", "munchen", "berlin",
    "bilbao", "sevilla", "valencia", "roma", "torino", "genoa", "glasgow", "lisbon", "lisboa", "porto", "bremen",
    "hamburg", "real", "united", "city", "athletic", "atletico", "sporting", "olympique", "racing", "deportivo",
    "union", "dinamo", "dynamo", "rapid", "red", "bull", "borussia", "eintracht", "hertha", "fortuna", "stade",
    "inter", "nacional", "saint", "st", "sao", "san", "santa", "club", "atalanta", "athletico",
}
# Letters that unicode decomposition does not strip
_LETTER_MAP = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                             "þ": "th", "Þ": "Th", "ı": "i", "œ": "oe", "Œ": "OE"})
# Tokens that DO carry identity even though they look generic
_KEEP_TOKENS = {"real", "inter", "united", "city", "rovers", "wanderers", "hotspur", "albion", "villa", "town"}

# Canonical aliases (normalised form -> canonical normalised form)
_ALIASES = {
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
    "manchester utd": "manchester united", "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "newcastle": "newcastle united", "west ham": "west ham united", "brighton": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion", "brighton & hove albion": "brighton hove albion",
    "nottm forest": "nottingham forest", "nottingham": "nottingham forest", "sheffield utd": "sheffield united",
    "leeds": "leeds united", "villa": "aston villa", "leicester": "leicester city", "norwich": "norwich city",
    "internazionale": "inter milan", "inter": "inter milan", "fc internazionale milano": "inter milan",
    "milan": "ac milan", "roma": "roma", "as roma": "roma", "lazio": "lazio", "juve": "juventus",
    "napoli": "napoli", "ssc napoli": "napoli", "hellas": "hellas verona", "verona": "hellas verona",
    "psg": "paris saint germain", "paris sg": "paris saint germain",  # "paris" alone is ambiguous (Paris FC)
    "atletico de madrid": "atletico madrid", "club atletico de madrid": "atletico madrid",
    "athletic club bilbao": "athletic bilbao",
    "om": "marseille", "olympique marseille": "marseille", "ol": "lyon", "olympique lyonnais": "lyon",
    "losc": "lille", "losc lille": "lille", "ogc nice": "nice", "monaco": "monaco", "as monaco": "monaco",
    "stade rennais": "rennes", "rennais": "rennes", "stade brestois": "brest", "brestois": "brest",
    "rc lens": "lens", "rc strasbourg": "strasbourg", "fc nantes": "nantes", "toulouse fc": "toulouse",
    "bayern": "bayern munich", "bayern munchen": "bayern munich", "fc bayern munchen": "bayern munich",
    "fc bayern": "bayern munich", "borussia dortmund": "dortmund", "bvb": "dortmund",
    "borussia monchengladbach": "monchengladbach", "bor monchengladbach": "monchengladbach", "gladbach": "monchengladbach",
    "borussia m gladbach": "monchengladbach", "m gladbach": "monchengladbach", "mgladbach": "monchengladbach",
    "hamburger sv": "hamburg", "hsv": "hamburg", "hamburger": "hamburg", "fc cologne": "koln", "1 fc cologne": "koln",
    "heidenheim 1846": "heidenheim", "fc heidenheim": "heidenheim", "st pauli": "st pauli", "fc st pauli": "st pauli",
    "leverkusen": "bayer leverkusen", "bayer 04 leverkusen": "bayer leverkusen", "frankfurt": "eintracht frankfurt",
    "eintracht": "eintracht frankfurt", "koln": "koln", "fc koln": "koln", "1 fc koln": "koln", "cologne": "koln",
    "mainz": "mainz 05", "fsv mainz": "mainz 05", "rb leipzig": "leipzig", "rasenballsport leipzig": "leipzig",
    "hoffenheim": "hoffenheim", "tsg hoffenheim": "hoffenheim", "werder": "werder bremen", "bremen": "werder bremen",
    "atletico": "atletico madrid", "atletico de madrid": "atletico madrid", "athletic": "athletic bilbao",
    "athletic club": "athletic bilbao", "betis": "real betis", "sociedad": "real sociedad", "celta": "celta vigo",
    "rayo": "rayo vallecano", "valladolid": "real valladolid", "espanyol": "espanyol", "rcd espanyol": "espanyol",
    "mallorca": "mallorca", "rcd mallorca": "mallorca", "barca": "barcelona", "fc barcelona": "barcelona",
    "psv eindhoven": "psv", "sporting lisbon": "sporting cp", "sporting clube de portugal": "sporting cp",
    "sporting": "sporting cp", "fc porto": "porto", "sl benfica": "benfica", "club brugge": "club brugge",
    "brugge": "club brugge", "fc copenhagen": "copenhagen", "kobenhavn": "copenhagen", "fc kobenhavn": "copenhagen",
    "red bull salzburg": "salzburg", "fc salzburg": "salzburg", "shakhtar": "shakhtar donetsk",
    "olympiakos": "olympiacos", "olympiacos piraeus": "olympiacos", "olympiakos piraeus": "olympiacos",
    "brugge kv": "club brugge", "club brugge kv": "club brugge", "stade brestois 29": "brest", "brestois 29": "brest", "slavia praha": "slavia prague",
    "sparta praha": "sparta prague", "bodo/glimt": "bodo glimt", "fk bodo glimt": "bodo glimt",
    "union st gilloise": "union saint gilloise", "union sg": "union saint gilloise",
    "royale union saint gilloise": "union saint gilloise", "royale union sg": "union saint gilloise",
    "galatasaray sk": "galatasaray", "fenerbahce sk": "fenerbahce", "ajax amsterdam": "ajax", "afc ajax": "ajax",
    "qarabag fk": "qarabag", "pafos fc": "pafos", "fc kairat": "kairat", "kairat almaty": "kairat",
}


def normalize_team_name(name: Optional[str]) -> str:
    """Lower-case, accent-free, punctuation-free, noise-token-free team name with aliases applied."""
    if not name:
        return ""
    text = strip_accents(name.translate(_LETTER_MAP)).lower()
    # German transliterations: providers write "Moenchengladbach"/"Koeln"/"Muenchen" for ö/ü; fold both spellings
    text = text.replace("oe", "o").replace("ae", "a").replace("ue", "u")
    text = text.replace("&", " and ").replace("-", " ").replace("/", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text in _ALIASES:
        return _ALIASES[text]
    # founding years and squad numbers ("Bologna FC 1909", "Stade Brestois 29", "Mainz 05") never carry identity
    tokens = [t for t in text.split(" ") if t and (t in _KEEP_TOKENS or (t not in _NOISE_TOKENS and not t.isdigit()))]
    cleaned = " ".join(tokens).strip() or text
    return _ALIASES.get(cleaned, cleaned)


def team_names_match(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    # One name fully contained in the other (e.g. "alaves" vs "deportivo alaves", "osasuna" vs "ca osasuna").
    # A single shared city/generic token ("madrid", "paris", "united") is never enough on its own:
    # "Real Madrid" must not swallow "Atletico Madrid" and "Paris Saint-Germain" must not swallow "Paris FC".
    if ta and tb and (ta <= tb or tb <= ta):
        shorter = ta if len(ta) <= len(tb) else tb
        if len(shorter) >= 2 or (len(shorter) == 1 and next(iter(shorter)) not in _SHARED_TOKENS and len(next(iter(shorter))) >= 4):
            return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.9


@dataclass
class MatchCandidate:
    match_id: str
    home_name: str
    away_name: str
    kickoff_utc: datetime
    competition_key: Optional[str] = None


@dataclass
class MatchDecision:
    match_id: Optional[str]
    confidence: str            # exact | high | ambiguous | none
    reason: str
    candidate_ids: List[str] = field(default_factory=list)

    @property
    def attached(self) -> bool:
        return self.match_id is not None and self.confidence in ("exact", "high")


EXACT_WINDOW = timedelta(minutes=15)
DEFAULT_MAX_DELTA = timedelta(hours=3)
RESCHEDULE_WINDOW = timedelta(hours=36)


def find_match(
    home_name: str,
    away_name: str,
    kickoff_utc: Optional[datetime],
    competition_key: Optional[str],
    candidates: Iterable[MatchCandidate],
    max_delta: timedelta = DEFAULT_MAX_DELTA,
) -> MatchDecision:
    """
    Decide which internal match (if any) a provider record refers to.

    - competition keys must agree when both are known
    - home and away names must match in the same orientation
    - kickoff within 15 min -> exact; within `max_delta` -> high; within 36 h -> ambiguous
      (probably rescheduled: not attached automatically); several candidates -> ambiguous
    """
    if kickoff_utc is not None and kickoff_utc.tzinfo is None:
        kickoff_utc = kickoff_utc.replace(tzinfo=timezone.utc)
    name_matches: List[tuple] = []
    swapped: List[MatchCandidate] = []
    for cand in candidates:
        if competition_key and cand.competition_key and competition_key != cand.competition_key:
            continue
        if team_names_match(home_name, cand.home_name) and team_names_match(away_name, cand.away_name):
            ck = cand.kickoff_utc if cand.kickoff_utc.tzinfo else cand.kickoff_utc.replace(tzinfo=timezone.utc)
            delta = abs(ck - kickoff_utc) if kickoff_utc else None
            name_matches.append((delta, cand))
        elif team_names_match(home_name, cand.away_name) and team_names_match(away_name, cand.home_name):
            swapped.append(cand)
    if not name_matches:
        if swapped:
            return MatchDecision(None, "ambiguous", "teams match only with home/away swapped", [c.match_id for c in swapped])
        return MatchDecision(None, "none", "no candidate with matching team names")
    if kickoff_utc is None:
        return MatchDecision(None, "ambiguous", "provider record has no kickoff time", [c.match_id for _, c in name_matches])
    within = sorted([(d, c) for d, c in name_matches if d is not None and d <= max_delta], key=lambda x: x[0])
    if len(within) == 1:
        delta, cand = within[0]
        confidence = "exact" if delta <= EXACT_WINDOW else "high"
        return MatchDecision(cand.match_id, confidence, f"teams and kickoff match (delta {int(delta.total_seconds() // 60)} min)", [cand.match_id])
    if len(within) > 1:
        return MatchDecision(None, "ambiguous", "several candidates within the kickoff window", [c.match_id for _, c in within])
    near = [(d, c) for d, c in name_matches if d is not None and d <= RESCHEDULE_WINDOW]
    if near:
        return MatchDecision(None, "ambiguous", "teams match but kickoff differs by more than the allowed window (rescheduled?)",
                             [c.match_id for _, c in near])
    return MatchDecision(None, "none", "teams match but kickoff is on a different day", [c.match_id for _, c in name_matches])
