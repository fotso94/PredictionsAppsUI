"""
Saying when football comes back, without spending the day's allowance finding out.

From 2026-09-21 the six covered competitions were in the international break and the first
fixture in any of them was on 9 October: eighteen days in which every matchday list is correctly
empty. "Nothing here" and "nothing until 9 October, and here is what is first" are both true, and
only the second is worth reading, so the empty state names the next fixtures.

The cost of knowing that is what these tests are mostly about, because the cheap way and the
ruinous way return the same list. Live Score API's fixtures/list.json answers WITHOUT a date with
the competition's remaining calendar in kickoff order, 30 rows to a page, so one request per
competition reaches 9 October from here - six in total. Walking forward a day at a time reaches
the same answer for six requests a DAY, and the base provider's `get_upcoming` does exactly that,
which is why `get_calendar_head` declines by default rather than inheriting a day-walk.

Five things have to stay true:

  - `get_calendar_head` costs exactly one request, however many pages the provider advertises;
  - a provider with no calendar endpoint declines, and declining is not a failure: it must not put
    an otherwise healthy provider into cool-down;
  - an answer is cached long enough that a reader refreshing the page cannot spend six requests a
    time, and two readers arriving together cannot spend twelve;
  - "the calendar lists nothing to come" and "nobody could tell us" never collapse into each
    other. The first may be shown to a reader as a fact; the second may not;
  - a sweep that reached some competitions and not others says so in the answer itself, which is
    what is cached and what every later reader is served.

No database and no network: the shipped provider over a mocked transport, the shipped
MatchDataService, an in-memory Redis stand-in whose TTLs elapse against a fake clock.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.endpoints.matches import upcoming_matches
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    CALENDAR_HEAD_LOCK_KEY, MatchDataService, SyncMeta,
)
from app.services.providers.base import (
    MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderTeam,
    ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from tests.providers.support import FakeRedis, json_response, make_transport
from tests.test_fixture_pipeline import Clock, ExpiringFakeRedis

NOW = datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)
KEYS = ["premier_league", "la_liga"]
LOGGER = "app.services.providers.livescore_api"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """The real client spaces calls a second apart; a test must not wait for that."""
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)


class FrozenDatetime(datetime):
    """`datetime.now()` pinned to NOW, so "still ahead of us" means ahead of 2026-09-21 11:00."""

    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def _row(day: str, time: str = "14:00:00", fixture_id: str = "1", home: str = "Arsenal",
         away: str = "Leeds United") -> Dict[str, Any]:
    return {"id": fixture_id, "date": day, "time": time,
            "home": {"id": "18", "name": home}, "away": {"id": "1131", "name": away},
            "competition": {"id": "2", "name": "Premier League"}}


def _calendar(pages: List[List[Dict[str, Any]]]):
    """A dateless fixtures/list.json that advertises a next page for every page but the last."""
    def handler(request):
        params = dict(request.url.params)
        assert "date" not in params, "the calendar head must ask for the whole calendar, not a day"
        index = int(params.get("page", 1)) - 1
        rows = pages[index] if index < len(pages) else []
        return json_response({"success": True,
                              "data": {"fixtures": rows, "next_page": index + 1 < len(pages)}})
    return handler


def _provider(handler, comp_ids: Optional[Dict[str, str]] = None):
    transport, recorder = make_transport(handler)
    provider = LiveScoreAPIProvider(
        api_key="trial-key", api_secret="trial-secret", transport=transport,
        budget=RequestBudget("livescore", 1200, client=FakeRedis()),
        # An EMPTY mapping is a meaningful argument here - "this provider can resolve no
        # competition id" - so it must not fall through to the default the way `or` would.
        competition_overrides={"premier_league": "2"} if comp_ids is None else comp_ids,
        store=MatchCache(client=FakeRedis()), use_default_ids=False)
    return provider, recorder


def _head(handler, limit: int = 5, key: str = "premier_league"):
    provider, recorder = _provider(handler)
    with patch("app.services.providers.livescore_api.datetime", FrozenDatetime):
        return provider.get_calendar_head(key, limit=limit), recorder


# --------------------------------------------------------------- one request, whatever it costs
def test_the_calendar_head_reads_one_page_and_stops():
    """The 9 October case: the answer is on page one because the calendar is in kickoff order."""
    head, recorder = _head(_calendar([
        [_row("2026-10-10", "11:30:00", "1877306"), _row("2026-10-10", "14:00:00", "1877307")],
        [_row("2026-10-17", "14:00:00", "1877340")],
    ]))

    assert [f.external_id for f in head] == ["1877306", "1877307"]
    assert len(recorder.requests) == 1, "a second page cannot hold an earlier fixture than page one"


def test_the_calendar_head_never_paginates_even_when_a_next_page_is_advertised():
    """The cost of this call is one request. A loop here is six extra requests per sweep."""
    pages = [[_row("2026-10-10", "14:00:00", str(n)) for n in range(30)] for _ in range(4)]
    head, recorder = _head(pages and _calendar(pages), limit=30)

    assert len(head) == 30
    assert len(recorder.requests) == 1


def test_the_calendar_head_honours_its_limit():
    head, _ = _head(_calendar([[_row("2026-10-10", f"1{n}:00:00", str(n)) for n in range(6)]]),
                    limit=2)

    assert [f.external_id for f in head] == ["0", "1"]


def test_the_calendar_head_returns_fixtures_in_kickoff_order():
    head, _ = _head(_calendar([[
        _row("2026-10-17", "14:00:00", "late"),
        _row("2026-10-09", "18:45:00", "first"),
        _row("2026-10-10", "11:30:00", "middle"),
    ]]))

    assert [f.external_id for f in head] == ["first", "middle", "late"]


# --------------------------------------------------------------- what is not a fixture to come
def test_a_kickoff_already_behind_us_is_not_a_fixture_to_come():
    head, _ = _head(_calendar([[
        _row("2026-09-21", "09:00:00", "kicked-off-this-morning"),
        _row("2026-10-09", "18:45:00", "next"),
    ]]))

    assert [f.external_id for f in head] == ["next"]


def test_a_row_whose_date_cannot_be_read_is_dropped_rather_than_dated_now():
    """The fixture mapper dates an unreadable row `now`, which would present it as the next match."""
    head, _ = _head(_calendar([[
        {"id": "broken", "date": None, "time": None, "home": {"id": "1", "name": "A"},
         "away": {"id": "2", "name": "B"}, "competition": {"id": "2", "name": "Premier League"}},
        _row("2026-10-09", "18:45:00", "next"),
    ]]))

    assert [f.external_id for f in head] == ["next"]


def test_a_competition_that_cannot_be_identified_is_unknown_not_empty():
    """No id to ask about, so no calendar was read. An empty list would claim one was."""
    def no_such_competition(request):
        return json_response({"success": True, "data": {"competition": [], "next_page": False}})

    provider, recorder = _provider(no_such_competition, comp_ids={})
    with patch("app.services.providers.livescore_api.datetime", FrozenDatetime):
        head = provider.get_calendar_head("premier_league", limit=5)

    assert head is None
    assert not any("fixtures/list.json" in str(r.url) for r in recorder.requests), \
        "with no competition id there is nothing to ask the calendar about"


def test_an_answered_calendar_with_no_fixture_in_it_is_an_empty_list_not_none():
    head, recorder = _head(_calendar([[]]))

    assert head == [], "the provider answered; it simply lists nothing to come"
    assert len(recorder.requests) == 1


def test_the_calendar_call_is_counted_under_its_own_reason():
    """The day's counters name this spending "calendar" rather than folding it into "fetch".

    It is the only provider spending a reader can start by opening a page, and the fixtures task
    spends under "fetch" all day, so a shared label would leave no way to see the calendar in the
    day's total at all. The label names the kind of call; it does not say who made it.
    """
    provider, _ = _provider(_calendar([[_row("2026-10-09", "18:45:00", "next")]]))
    with patch("app.services.providers.livescore_api.datetime", FrozenDatetime):
        provider.get_calendar_head("premier_league", limit=5)

    assert provider.budget.by_reason() == {"calendar": 1}
    assert provider.budget.used_today() == 1, "one request, and the day counts exactly it"


# --------------------------------------------------------------- the base provider declines
class CountingProvider(MatchDataProvider):
    """A provider with only a per-day fixtures endpoint, i.e. no calendar of its own."""

    name = "counting"

    def __init__(self):
        self.days_asked: List[date] = []

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day: date, keys):
        self.days_asked.append(day)
        return []

    def get_live(self, keys):
        return []

    def get_results(self, date_from, date_to, keys):
        return []

    def get_standings(self, key):
        return []


def test_a_provider_without_a_calendar_declines_instead_of_walking_the_days():
    """`get_upcoming` would ask for a day at a time. Inheriting that here is the ruinous answer."""
    provider = CountingProvider()

    assert provider.get_calendar_head("premier_league") is None
    assert provider.days_asked == [], "declining must cost nothing at all"


# --------------------------------------------------------------- the service sweep
class CalendarProvider(MatchDataProvider):
    """Answers the calendar question per competition, and records that it was asked."""

    name = "calendar-stub"

    def __init__(self, heads: Dict[str, Optional[List[ProviderFixture]]],
                 fail: Optional[Exception] = None):
        self.heads = heads
        self.fail = fail
        self.asked: List[str] = []
        self.budget = None

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day, keys):
        return []

    def get_live(self, keys):
        return []

    def get_results(self, date_from, date_to, keys):
        return []

    def get_standings(self, key):
        return []

    def get_calendar_head(self, key: str, limit: int = 5):
        self.asked.append(key)
        if self.fail is not None:
            raise self.fail
        return self.heads.get(key)


class PlainProvider(CalendarProvider):
    """A provider that publishes no calendar at all: every competition declines."""

    name = "plain-stub"

    def __init__(self):
        super().__init__(heads={})

    def get_calendar_head(self, key: str, limit: int = 5):
        self.asked.append(key)
        return None


def _fixture(kickoff: datetime, external_id: str, key: str, home: str, away: str) -> ProviderFixture:
    return ProviderFixture(
        provider="calendar-stub", external_id=external_id,
        competition=ProviderCompetition(provider="calendar-stub", external_id="1",
                                        name=key.replace("_", " ").title(), key=key),
        home=ProviderTeam(provider="calendar-stub", external_id="h", name=home),
        away=ProviderTeam(provider="calendar-stub", external_id="a", name=away),
        kickoff_utc=kickoff)


def _service(cache, clock, providers):
    service = MatchDataService(MagicMock(), providers=providers, cache=cache, now=clock(),
                               keys=list(KEYS))
    service.registry = MagicMock()
    return service


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def cache(clock):
    return MatchCache(client=ExpiringFakeRedis(clock=clock))


def test_the_sweep_asks_each_covered_competition_once_and_merges_them_in_order(cache, clock):
    provider = CalendarProvider({
        "premier_league": [_fixture(NOW + timedelta(days=19), "pl", "premier_league", "Arsenal", "Leeds")],
        "la_liga": [_fixture(NOW + timedelta(days=18), "ll", "la_liga", "Betis", "Elche")],
    })

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert provider.asked == KEYS, "one request per covered competition, and no more"
    assert [f["external_id"] for f in payload["fixtures"]] == ["ll", "pl"], "earliest kickoff first"
    assert payload["unanswered"] == [], "every covered competition answered"
    assert meta.source == "provider"


def test_a_second_reader_is_served_from_the_cache_and_costs_nothing(cache, clock):
    provider = CalendarProvider({
        "premier_league": [_fixture(NOW + timedelta(days=19), "pl", "premier_league", "A", "B")],
        "la_liga": [],
    })
    first = _service(cache, clock, [provider])
    first.next_fixtures()
    asked_once = list(provider.asked)

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert provider.asked == asked_once, "a refresh of the page must not re-sweep the calendar"
    assert [f["external_id"] for f in payload["fixtures"]] == ["pl"]
    assert meta.source == "cache"


def test_the_answer_is_swept_again_once_its_ttl_has_elapsed(cache, clock):
    from app.services.match_data_service import CALENDAR_HEAD_TTL_SECONDS

    provider = CalendarProvider({"premier_league": [], "la_liga": []})
    _service(cache, clock, [provider]).next_fixtures()
    clock.tick(CALENDAR_HEAD_TTL_SECONDS + 1)
    cache._redis().delete(CALENDAR_HEAD_LOCK_KEY)

    _service(cache, clock, [provider]).next_fixtures()

    assert provider.asked == KEYS * 2, "the calendar is re-read once the interval has passed"


def test_two_readers_arriving_together_pay_for_one_sweep_between_them(cache, clock):
    """The TTL stops a reader refreshing; only the guard stops readers arriving at once."""
    provider = CalendarProvider({"premier_league": [], "la_liga": []})
    holder = _service(cache, clock, [provider])
    assert holder._claim_calendar_refresh() is True

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert provider.asked == [], "the second reader must not start a sweep of its own"
    assert payload is None, "and must not report an empty calendar it never read"
    assert any("already in flight" in e for e in meta.errors)


# --------------------------------------------------------------- unknown is not empty
def test_no_provider_publishes_a_calendar_so_the_answer_is_unknown(cache, clock):
    provider = PlainProvider()

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert payload is None, "nobody was able to say, which is not the same as nothing is scheduled"
    assert any("publishes no competition calendar" in e for e in meta.errors)


def test_declining_the_calendar_does_not_put_a_working_provider_into_cool_down(cache, clock):
    """A provider that still serves fixtures perfectly well must not be shut out of them."""
    service = _service(cache, clock, [PlainProvider()])

    service.next_fixtures()

    assert service._cooldown("plain-stub") is None


def test_a_provider_that_fails_leaves_the_answer_unknown_rather_than_empty(cache, clock):
    provider = CalendarProvider({}, fail=ProviderUnavailableError("upstream is down", provider="calendar-stub"))

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert payload is None
    assert any("upstream is down" in e for e in meta.errors)


class NoCache(MatchCache):
    """A cache with no Redis behind it, as an installation without Redis has.

    Not `MatchCache(client=None)`, which means "connect on first use" and would find the Redis
    this machine is running - the opposite of the state under test.
    """

    def __init__(self):
        super().__init__(client=None)
        self._checked = True


def test_without_a_cache_the_calendar_is_not_read_at_all(clock):
    """A sweep is affordable because it is kept. With nowhere to keep it, it is not affordable."""
    provider = CalendarProvider({"premier_league": [], "la_liga": []})

    payload, meta = _service(NoCache(), clock, [provider]).next_fixtures()

    assert provider.asked == [], "every reload of an empty day would otherwise re-sweep"
    assert payload is None, "and declining to ask is not the same as being told there is nothing"
    assert any("no cache is available" in e for e in meta.errors)


def test_a_calendar_that_lists_nothing_is_a_known_answer(cache, clock):
    """Every competition answered and none has a fixture left. That is a fact, and may be shown."""
    provider = CalendarProvider({"premier_league": [], "la_liga": []})

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert payload == {"fixtures": [], "unanswered": []}, \
        "an empty list is the provider's answer, not the absence of one"
    assert meta.source == "provider"


def _partial_provider() -> CalendarProvider:
    """One competition answers; the other declines, so the sweep speaks for half of what it covers."""
    return CalendarProvider({
        "premier_league": [_fixture(NOW + timedelta(days=19), "pl", "premier_league", "A", "B")],
        "la_liga": None,
    })


def test_a_competition_nobody_could_answer_for_is_named_beside_the_partial_answer(cache, clock):
    payload, meta = _service(cache, clock, [_partial_provider()]).next_fixtures()

    assert [f["external_id"] for f in payload["fixtures"]] == ["pl"]
    assert payload["unanswered"] == ["la_liga"], \
        "a competition nobody asked about must not read as one with no fixtures"
    assert any("la_liga" in e for e in meta.errors)


def test_the_caveat_on_a_partial_answer_outlives_the_request_that_made_it(cache, clock):
    """`meta.errors` lasts one request; the answer is served from the cache for hours.

    A reader arriving on the second of those hours is handed the same shortened fixture list, so
    what says the list is shortened has to be in the answer rather than beside it.
    """
    provider = _partial_provider()
    _service(cache, clock, [provider]).next_fixtures()
    asked_once = list(provider.asked)

    payload, meta = _service(cache, clock, [provider]).next_fixtures()

    assert meta.source == "cache" and provider.asked == asked_once
    assert meta.errors == [], "the second reader made no sweep, so it collected no diagnostics"
    assert payload["unanswered"] == ["la_liga"], \
        "and is still told which competition the fixture list does not speak for"


# --------------------------------------------------------------- the endpoint says which it is
def _answer(*rows: Dict[str, Any], unanswered: Optional[List[str]] = None) -> Dict[str, Any]:
    """The answer object `next_fixtures` hands the endpoint."""
    return {"fixtures": list(rows), "unanswered": list(unanswered or [])}


def _call_endpoint(answer, meta, limit: int = 5):
    service = MagicMock()
    service.next_fixtures.return_value = (answer, meta)
    with patch("app.api.v1.endpoints.matches.MatchDataService", return_value=service):
        return asyncio.run(upcoming_matches(limit=limit, db=MagicMock()))


def _payload_row(kickoff: str, key: str, home: str, away: str) -> Dict[str, Any]:
    return {"provider": "livescore", "external_id": "1",
            "competition": {"provider": "livescore", "external_id": "2", "name": key.title(),
                            "key": key, "country": None, "country_code": None, "is_cup": False,
                            "season_name": None, "logo": None},
            "home": {"provider": "livescore", "external_id": "h", "name": home, "logo": None, "country": None},
            "away": {"provider": "livescore", "external_id": "a", "name": away, "logo": None, "country": None},
            "kickoff_utc": kickoff, "status": "scheduled", "minute": None,
            "home_score": None, "away_score": None, "ht_home_score": None, "ht_away_score": None,
            "venue": None, "round": "6"}


def test_the_endpoint_names_the_next_fixtures_and_when_football_resumes():
    body = _call_endpoint(
        _answer(_payload_row("2026-10-09T18:45:00+00:00", "la_liga", "Betis", "Elche"),
                _payload_row("2026-10-10T11:30:00+00:00", "premier_league", "Arsenal", "Leeds United")),
        SyncMeta(source="provider", provider="livescore"))

    assert body["known"] is True
    assert body["unanswered"] == [], "this answer speaks for every covered competition"
    assert body["next_kickoff"] == "2026-10-09T18:45:00+00:00"
    assert [f["home"] for f in body["fixtures"]] == ["Betis", "Arsenal"]
    assert body["fixtures"][0]["competition"]["key"] == "la_liga"
    assert "external_id" not in body["fixtures"][0], \
        "these are calendar rows this installation has not stored, so they carry no id to link to"


def test_the_endpoint_reports_an_unread_calendar_as_unknown():
    body = _call_endpoint(None, SyncMeta(errors=["livescore: upstream is down"]))

    assert body["known"] is False
    assert body["fixtures"] == []
    assert body["next_kickoff"] is None
    assert body["errors"] == ["livescore: upstream is down"]


def test_the_endpoint_distinguishes_an_empty_calendar_from_an_unread_one():
    empty = _call_endpoint(_answer(), SyncMeta(source="provider", provider="livescore"))
    unread = _call_endpoint(None, SyncMeta())

    assert empty["known"] is True and empty["fixtures"] == []
    assert unread["known"] is False and unread["fixtures"] == []
    assert empty["known"] != unread["known"], \
        "the reader is told 'no fixture is scheduled' only when a calendar was actually read"


def test_the_endpoint_caps_the_list_but_not_the_date_football_resumes():
    rows = [_payload_row("2026-10-09T18:45:00+00:00", "la_liga", "Betis", "Elche")]
    rows += [_payload_row("2026-10-10T14:00:00+00:00", "premier_league", f"H{n}", f"A{n}")
             for n in range(9)]

    body = _call_endpoint(_answer(*rows), SyncMeta(source="provider", provider="livescore"), limit=3)

    assert len(body["fixtures"]) == 3
    assert body["next_kickoff"] == "2026-10-09T18:45:00+00:00"


def test_the_endpoint_names_the_competitions_its_answer_does_not_speak_for():
    """A partial sweep is still `known`, and the caller has to be able to see that it is partial.

    The fixtures below were read from two calendars out of six. The four that were not read may
    hold an earlier kickoff than either of them, so `next_kickoff` is the earliest of what was
    read and the reader may not be told football resumes then.
    """
    body = _call_endpoint(
        _answer(_payload_row("2026-10-09T18:45:00+00:00", "la_liga", "Betis", "Elche"),
                unanswered=["serie_a", "bundesliga", "ligue_1", "premier_league"]),
        SyncMeta(source="cache", provider="livescore"))

    assert body["known"] is True
    assert body["next_kickoff"] == "2026-10-09T18:45:00+00:00"
    assert body["unanswered"] == ["serie_a", "bundesliga", "ligue_1", "premier_league"]


# ------------------------------------------------ the clock the answer was filtered against ages
def test_a_fixture_that_kicked_off_since_the_sweep_is_not_one_still_to_come():
    """The clock the sweep applied is hours old by the time this answer reaches a reader.

    `get_calendar_head` keeps only fixtures ahead of the moment it FETCHED, and that answer is
    then served fresh for six hours and stale for a day. Applying the clock again on the way out
    is what stops the date football resumes from being a date that has passed.
    """
    now = datetime.now(timezone.utc)
    played = (now - timedelta(hours=3)).isoformat()
    to_come = (now + timedelta(days=4)).isoformat()

    body = _call_endpoint(_answer(_payload_row(played, "la_liga", "Betis", "Elche"),
                                  _payload_row(to_come, "premier_league", "Arsenal", "Leeds")),
                          SyncMeta(source="cache", provider="livescore"))

    assert body["known"] is True
    assert body["next_kickoff"] == to_come, "the played fixture is not when football resumes"
    assert [f["home"] for f in body["fixtures"]] == ["Arsenal"]


def test_a_calendar_whose_every_fixture_has_been_played_is_no_longer_a_known_answer():
    """A copy that has run out describes no future, and must not be read as describing an empty one.

    Serving it as an empty fixture list would let a reader be told no football is scheduled on
    the strength of a calendar that was true this morning.
    """
    now = datetime.now(timezone.utc)

    body = _call_endpoint(_answer(_payload_row((now - timedelta(hours=3)).isoformat(),
                                               "la_liga", "Betis", "Elche"),
                                  _payload_row((now - timedelta(minutes=20)).isoformat(),
                                               "premier_league", "Arsenal", "Leeds United")),
                          SyncMeta(source="stale-cache", provider="livescore", stale=True))

    assert body["known"] is False
    assert body["fixtures"] == [] and body["next_kickoff"] is None


def test_a_calendar_that_listed_nothing_stays_a_known_answer_however_old_it_is():
    """Nothing to filter out and nothing that can expire: the calendars were read and were empty."""
    body = _call_endpoint(_answer(),
                          SyncMeta(source="stale-cache", provider="livescore", stale=True))

    assert body["known"] is True and body["fixtures"] == []


def test_an_answer_nobody_gave_names_no_source():
    """`source` says where the answer came from, so an answer that does not exist came from nowhere.

    `SyncMeta.source` defaults to "database", and the calendar path reads no database at all:
    reporting that default would contradict the `known: false` beside it.
    """
    unread = _call_endpoint(None, SyncMeta(errors=["livescore: upstream is down"]))
    read = _call_endpoint(_answer(), SyncMeta(source="provider", provider="livescore"))

    assert unread["source"] is None
    assert read["source"] == "provider"


# ------------------------------------------------------- one failure is one entry in the errors
def test_each_provider_in_a_failing_chain_is_counted_once():
    """An operator counting distinct failures must not be handed the last provider's twice.

    `_call_chain` records every provider it tried and then raises the last of those failures, so
    a caller that records the exception as well turns a three-provider chain into four entries.
    """
    cache = MatchCache(client=ExpiringFakeRedis(clock=Clock(NOW)))
    providers = []
    for index in range(3):
        provider = CalendarProvider({}, fail=ProviderUnavailableError(f"stub-{index} is down",
                                                                      provider=f"stub-{index}"))
        provider.name = f"stub-{index}"
        providers.append(provider)

    payload, meta = _service(cache, Clock(NOW), providers).next_fixtures()

    assert payload is None
    assert meta.errors == ["stub-0 is down", "stub-1 is down", "stub-2 is down"]


def test_a_chain_with_no_provider_in_it_still_says_why_there_is_no_answer(cache, clock):
    """The one failure the chain does not record itself, because it tried nobody."""
    payload, meta = _service(cache, clock, []).next_fixtures()

    assert payload is None
    assert meta.errors == ["No match-data provider is configured"]
