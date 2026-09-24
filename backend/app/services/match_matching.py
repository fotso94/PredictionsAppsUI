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
    "05", "04", "96", "98", "ssc", "cp", "ssd", "asd", "cfc", "sk",
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

# German transliterations: providers write "Moenchengladbach"/"Koeln"/"Muenchen" for ö/ü/ä.
# The fold must never touch unrelated words, so it only fires on a real umlaut context:
#   * preceded by a consonant inside the same token (never token-initial: "AEK" stays "aek"),
#   * followed by a consonant or the end of the token ("Piraeus", "Nueva" keep their vowel run),
#   * "cue"/"gue"/"pue"/"que" are excluded ("Prague", "league", "Queretaro", "Puebla", "Cuenca" must
#     survive); German umlaut spellings never need them, while "goe"/"gae" stay folded because
#     "Goeteborg" (Göteborg) is a real club spelling.
_UMLAUT_FOLD = re.compile(
    r"(?<=[bdfhjklmnrstvwxz])ue(?=[^aeiouy]|$)"
    r"|(?<=[bcdfghjklmnpqrstvwxz])(ae|oe)(?=[^aeiouy]|$)"
)
_UMLAUT_TARGET = {"ae": "a", "oe": "o", "ue": "u"}

# ------------------------------------------------------------------ dropped-suffix spellings
# A bare place name against that same place name plus a common club word is the one shape this
# module cannot decide. "Cardiff" / "Cardiff City" is one club written two ways. "Dundee" /
# "Dundee United" is two clubs in one city, and a bare "Bristol" is either Bristol City or
# Bristol Rovers. Every one of those strings is built the same way, so no ratio, threshold or
# token rule separates them: the difference is not in the strings. A rule loose enough to join
# "Cardiff" to "Cardiff City" joins "Manchester United" to "Manchester City" as well.
#
# Hence a list, one club per line. The two failures are not symmetrical. A club with no line here
# is stored twice, which `scripts/repair_duplicate_matches.py` lists and a person folds back into
# one row. A wrong line re-points the provider's team ref, so every later fixture of that club is
# filed under the other club, silently and for good. Missing is recoverable; wrong is not.
#
# The first block is an observation of this installation's data rather than a recollection:
# `provider_entity_refs` records the name each provider sent, and for each of those clubs both
# spellings appear against ONE team row in the competitions synced here. Each of those lines says
# which provider writes which, so it can be checked against the database by someone who does not
# follow football. The second block is marked off precisely because that check does not pass for
# it, and says so on its own terms.
_SUFFIX_DROP_ALIASES = {
    "brighton": "brighton hove albion",  # livescore "Brighton & Hove Albion"; api_football, gameforecast "Brighton"
    "coventry": "coventry city",         # livescore "Coventry City"; api_football, gameforecast "Coventry"
    "ipswich": "ipswich town",           # livescore "Ipswich Town"; api_football, gameforecast "Ipswich"
    "leeds": "leeds united",             # livescore "Leeds United"; api_football, gameforecast "Leeds"
    "newcastle": "newcastle united",     # livescore "Newcastle United"; api_football, gameforecast "Newcastle"
    "tottenham": "tottenham hotspur",    # livescore "Tottenham Hotspur"; gameforecast "Tottenham"

    # The same shape, with no such observation behind it: no provider here has been seen writing
    # these short forms. Leicester City, Norwich City and Wolverhampton Wanderers are not in this
    # database at all, and every provider that names Nottingham Forest names it in full. They are
    # marked off from the observed lines above and carry the same risk as any line -- each merges
    # only the two spellings written on it.
    "leicester": "leicester city",
    "norwich": "norwich city",
    "nottingham": "nottingham forest",
    "wolverhampton": "wolverhampton wanderers",
}

# Canonical aliases (normalised form -> canonical normalised form)
_ALIASES = {
    **_SUFFIX_DROP_ALIASES,
    # TWO COUNTRIES, FOUR SPELLINGS, AND THE ONE WORD THEY SHARE IS THE DANGEROUS ONE.
    # Live Score writes "N.Ireland" and "Republic of Ireland"; GameForecast writes "Northern
    # Ireland" and "Rep. Of Ireland". Every one of them contains "ireland", so any rule that
    # reaches for a common substring merges two different national teams and files one country's
    # forecast onto the other's fixture. These four lines pair the spellings BY NAME and leave the
    # shared word doing no work at all; `test_the_two_irelands_never_reach_each_other` is the
    # guard, and "ireland" deliberately has no entry of its own because alone it names neither.
    "n ireland": "northern ireland",
    "nir": "northern ireland",
    "rep of ireland": "republic of ireland",
    "roi": "republic of ireland",
    "ireland republic": "republic of ireland",
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
    "manchester utd": "manchester united", "spurs": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "west ham": "west ham united",
    "brighton and hove albion": "brighton hove albion", "brighton & hove albion": "brighton hove albion",
    "nottm forest": "nottingham forest", "sheffield utd": "sheffield united", "villa": "aston villa",
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
    "brugge kv": "club brugge", "club brugge kv": "club brugge", "stade brestois 29": "brest",
    "brestois 29": "brest", "slavia praha": "slavia prague", "sparta praha": "sparta prague",
    "bodo/glimt": "bodo glimt", "fk bodo glimt": "bodo glimt",
    "union st gilloise": "union saint gilloise", "union sg": "union saint gilloise",
    "royale union saint gilloise": "union saint gilloise", "royale union sg": "union saint gilloise",
    "galatasaray sk": "galatasaray", "fenerbahce sk": "fenerbahce", "ajax amsterdam": "ajax", "afc ajax": "ajax",
    "qarabag fk": "qarabag", "pafos fc": "pafos", "fc kairat": "kairat", "kairat almaty": "kairat",
}


def _fold_umlaut_digraphs(text: str) -> str:
    return _UMLAUT_FOLD.sub(lambda m: _UMLAUT_TARGET[m.group(0)], text)


def normalize_team_name(name: Optional[str]) -> str:
    """Lower-case, accent-free, punctuation-free, noise-token-free team name with aliases applied."""
    if not name:
        return ""
    text = strip_accents(name.translate(_LETTER_MAP)).lower()
    text = text.replace("&", " and ").replace("-", " ").replace("/", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _fold_umlaut_digraphs(text)
    if text in _ALIASES:
        return _ALIASES[text]
    # founding years and squad numbers ("Bologna FC 1909", "Stade Brestois 29", "Mainz 05") never carry identity
    tokens = [t for t in text.split(" ") if t and (t in _KEEP_TOKENS or (t not in _NOISE_TOKENS and not t.isdigit()))]
    cleaned = " ".join(tokens).strip() or text
    return _ALIASES.get(cleaned, cleaned)


def _is_generic_token(token: str) -> bool:
    """A token that cannot identify a club on its own: a city/prefix or a club-type initialism (CA, AJ, JK)."""
    return token in _SHARED_TOKENS or token in _NOISE_TOKENS or len(token) <= 2


def _is_decoration_of(token: str, longer_tokens: List[str]) -> bool:
    """
    Is `longer_tokens` the single word `token` with nothing but decoration around it?

    Position decides, because the two sides of a club name do different work. A word BEFORE the
    name decorates it: "Deportivo Alaves", "Stade de Reims", "CA Osasuna" are all one club under
    two spellings. A word AFTER it is an English club suffix, and those tell clubs APART -- Dundee
    and Dundee United are two clubs in one league, as are Bristol City and Bristol Rovers -- so
    only a club-type initialism may follow ("Besiktas JK"). Short forms that really do drop a
    suffix are spelt out in `_SUFFIX_DROP_ALIASES` one club at a time instead of being derived here.
    """
    if token not in longer_tokens:
        return False
    cut = longer_tokens.index(token)
    return (all(_is_generic_token(t) for t in longer_tokens[:cut])
            and all(len(t) <= 2 or t in _NOISE_TOKENS for t in longer_tokens[cut + 1:]))


def team_names_match(a: Optional[str], b: Optional[str]) -> bool:
    """
    Are these two spellings one club?

    The only answer this module gives, and the one every caller that needs club identity asks --
    including `match_registry`, where the answer is written into `provider_entity_refs` and
    survives every later sync. A looser companion is deliberately not offered.

    The answer comes from the curated `_ALIASES` table, where each pairing is one reviewable line
    a person wrote, and from `_is_decoration_of`, where a word in front of a name decorates it and
    a word behind it tells two clubs apart. A similarity measure cannot do this job at any
    threshold: "Ipswich" / "Ipswich Town" and "Paris FC" / "Paris Saint-Germain" are the same
    shape to a string metric, and the first pair is one club while the second is two clubs in one
    city. The ratio at the foot of this function is the last word on a TYPO, not on identity: at
    0.9 the two normalised names differ by about a letter.
    """
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    la, lb = na.split(), nb.split()
    ta, tb = set(la), set(lb)
    # One name fully contained in the other (e.g. "alaves" vs "deportivo alaves", "osasuna" vs "ca osasuna").
    # A single shared city/generic token ("madrid", "paris", "united") is never enough on its own:
    # "Real Madrid" must not swallow "Atletico Madrid" and "Paris Saint-Germain" must not swallow "Paris FC".
    if ta and tb and (ta <= tb or tb <= ta):
        shorter, longer_tokens = (ta, lb) if len(ta) <= len(tb) else (tb, la)
        if len(shorter) >= 2:
            return True
        if len(shorter) == 1:
            token = next(iter(shorter))
            # A one-token subset is never accepted on the name alone: the longer name may only add
            # decoration ("Deportivo Alaves", "CA Osasuna", "Besiktas JK"). Anything that adds a
            # real identifying word is a different club ("Grasshopper Zurich" is not "Zurich",
            # "Lokomotive Leipzig" is not "Leipzig", "Dundee United" is not "Dundee").
            if token not in _SHARED_TOKENS and len(token) >= 4 and _is_decoration_of(token, longer_tokens):
                return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.9


def _freeze_aliases() -> None:
    """
    Make every alias VALUE its own normalised fixed point.

    A value that is not normalised is unreachable: "slavia praha" -> "slavia prague" only helps when
    normalize_team_name("Slavia Prague") produces exactly "slavia prague" as well. The table is
    rewritten once at import and then verified, so a future edit cannot reintroduce the defect.
    """
    for key, value in list(_ALIASES.items()):
        canonical = value
        for _ in range(8):
            nxt = normalize_team_name(canonical)
            if nxt == canonical:
                break
            canonical = nxt
        else:  # pragma: no cover - a cyclic alias table is a programming error
            raise AssertionError(f"alias {key!r} -> {value!r} does not converge under normalisation")
        _ALIASES[key] = canonical
    broken = {k: v for k, v in _ALIASES.items() if normalize_team_name(v) != v}
    if broken:  # pragma: no cover - guarded at import so the table can never drift
        raise AssertionError(f"alias values are not normalised fixed points: {broken}")


_freeze_aliases()


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
# How far around a kickoff callers should LOOK for candidates. Deliberately much wider than the
# attach thresholds above: a postponement of several days must surface the original fixture so the
# decision can be reported as uncertain instead of silently creating a duplicate match row.
LOOKUP_WINDOW = timedelta(days=14)


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
    - kickoff within 15 min -> exact; within `max_delta` -> high; anything further apart ->
      ambiguous ("possibly rescheduled", carrying the candidate ids); several candidates -> ambiguous

    Attach thresholds never widen with the caller's lookup window: a candidate that the caller only
    found because it searched a fortnight ahead can produce an `ambiguous` or a `none` decision, never
    an attachment.
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
        return MatchDecision(cand.match_id, confidence,
                             f"teams and kickoff match (delta {int(delta.total_seconds() // 60)} min)",
                             [cand.match_id])
    if len(within) > 1:
        return MatchDecision(None, "ambiguous", "several candidates within the kickoff window", [c.match_id for _, c in within])
    near = [(d, c) for d, c in name_matches if d is not None and d <= RESCHEDULE_WINDOW]
    if near:
        return MatchDecision(None, "ambiguous", "teams match but kickoff differs by more than the allowed window (rescheduled?)",
                             [c.match_id for _, c in near])
    # Beyond the reschedule window the candidate is still the only fixture with these teams in the
    # caller's lookup range: report it as possibly rescheduled instead of pretending nothing was found.
    hours = sorted(int(d.total_seconds() // 3600) for d, _ in name_matches if d is not None)
    return MatchDecision(None, "ambiguous",
                         f"teams match but kickoff is {hours[0] if hours else '?'} h away (possibly rescheduled)",
                         [c.match_id for _, c in name_matches])
