"""
What a provider's answer names is recorded before any of it is stored - on every ingestion path -
and a listing is only as complete as its pages were read.

TWO DEFECTS A REVIEWER REPRODUCED ON 2026-10-28 (branch fixture-cadence at 7e3bac4f).

1. The calendar (`sync_upcoming`) and the results import (`_sync_results`) stored their answers
   without first recording the ids the answer named. With an earlier absence recorded against the
   old listing, an answer that carried the NEW id first and the old id after it let the new id
   join the old row - on an absence the very same answer contradicted - and then refused the old
   id as "superseded". Now every path records what the answer names, attributed to the provider
   that answered, before matching starts (`MatchDataService._observe_seen`,
   `_observe_day_listing`); a calendar, a live poll and a results answer are evidence of presence
   only, never of absence.

2. `LiveScoreAPIProvider._paginate` stopped at an empty page even when another page was
   advertised, left its truncation flag false, and the day observer took the answer for a complete
   listing: a fixture on page two was never read and its absence was recorded. Now the list ends
   where the provider says it ends or at MAX_PAGES, which marks the answer cut; an empty page with
   nothing further advertised is still a complete listing, and a valid observation.

THE REPLIES ARE LIVE SCORE'S SHAPES: `fixtures/list.json` rows as `_fixture_from_scheduled` reads
them (paged by `next_page` or `total_pages`), `matches/history.json` rows as `_fixture_from_match`
reads them. Every request the service sends is recorded, so each test asserts the calls made as
well as the state left behind. The rows carry the incident's public values. Requires PostgreSQL;
set TEST_DATABASE_URL, skipped when unreachable. No network: the transport is a mock.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
import pytest

from app.core.config import settings
from app.models.predictions import Match, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.match_registry import MatchRegistry
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import MAX_PAGES, LiveScoreAPIProvider
from tests.providers.support import FakeRedis, json_response
from tests.services.test_superseded_listings import (  # noqa: F401 - pytest fixtures and the incident's rows
    ABSENT_LISTING_AT, DEAD_ID, DROPPED_KICKOFF, FORECAST_EVENT, LEAGUE, LIVE_ID, LYON as AWAY, PLAYED_KICKOFF,
    PROVIDER, PSG as HOME, db, earlier_listing, engine, fresh, played, psg_lyon_rows, refs_of, result_of, snapshots_of,
    stored,
)

try:
    from app.services.match_registry import LISTINGS_KEY
except ImportError:  # the previous implementation
    LISTINGS_KEY = "listings"

COMPETITION = {"id": 5, "name": "Ligue 1"}
PSG, LYON, MARSEILLE, NICE = ({"id": 59, "name": HOME}, {"id": 61, "name": AWAY},
                              {"id": 64, "name": "Marseille"}, {"id": 66, "name": "Nice"})
#: The morning after the earlier listing's kickoff window closed and before the re-issue was played.
MORNING_AFTER = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
OTHER_ID = "1877020"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)


# ----------------------------------------------------------------------------- Live Score's shapes
def listed(fixture_id: str, home: Dict, away: Dict, day: str, time: str, round_: str = "8") -> Dict:
    """A `fixtures/list.json` row."""
    return {"id": int(fixture_id), "date": day, "time": time, "round": round_, "location": "Parc des Princes",
            "home": dict(home), "away": dict(away), "competition": dict(COMPETITION)}


def finished(fixture_id: str, home: Dict, away: Dict, day: str, ht: str, ft: str, archive_id: int) -> Dict:
    """A `matches/history.json` row, in the captured archive row's keys."""
    return {"away": dict(away), "competition": dict(COMPETITION), "date": day, "fixture_id": int(fixture_id),
            "home": dict(home), "id": archive_id, "round": "8",
            "scores": {"et_score": "", "ft_score": ft, "ht_score": ht, "ps_score": "", "score": ft},
            "status": "FINISHED", "time": "FT"}


OLD_LISTED = listed(DEAD_ID, PSG, LYON, "2026-10-25", "19:45:00")
NEW_LISTED = listed(LIVE_ID, PSG, LYON, "2026-10-26", "19:30:00")
OTHER_LISTED = listed(OTHER_ID, MARSEILLE, NICE, "2026-10-25", "14:00:00")
OLD_FINISHED = finished(DEAD_ID, PSG, LYON, "2026-10-25", "0 - 0", "2 - 0", archive_id=900301)
NEW_FINISHED = finished(LIVE_ID, PSG, LYON, "2026-10-26", "0 - 0", "2 - 0", archive_id=900302)


class Replies:
    """What Live Score answers, page by page, and every request it was sent."""

    def __init__(self):
        #: (date or None for the calendar, page) -> the `data` object of fixtures/list.json
        self.fixture_pages: Dict[tuple, Dict] = {}
        #: page -> the `data` object of matches/history.json
        self.history_pages: Dict[int, Dict] = {1: {"match": [], "total_pages": 1}}
        #: page -> HTTP status to answer with instead of a body
        self.failures: Dict[tuple, int] = {}
        self.requests: List[httpx.Request] = []

    def fixtures(self, day: Optional[str], page: int, rows: List[Dict], *, next_page: Optional[bool] = None,
                 total_pages: Optional[int] = None) -> None:
        data: Dict = {"fixtures": rows}
        if next_page is not None:
            data["next_page"] = f"https://livescore-api.com/api-client/fixtures/list.json?page={page + 1}" if next_page else False
        if total_pages is not None:
            data["total_pages"] = total_pages
        self.fixture_pages[(day, page)] = data

    def calls(self, endpoint: str) -> List[Dict[str, str]]:
        """The query of every request to `endpoint`, without the credentials every request carries."""
        return [{k: v for k, v in dict(r.url.params).items() if k not in ("key", "secret")}
                for r in self.requests if r.url.path.endswith(endpoint)]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params, path = dict(request.url.params), request.url.path
        page = int(params.get("page") or 1)
        if path.endswith("fixtures/list.json"):
            assert params["competition_id"] == str(COMPETITION["id"]), params
            key = (params.get("date"), page)
            if key in self.failures:
                return httpx.Response(self.failures[key], json={"success": False, "error": "upstream failure"})
            data = self.fixture_pages.get(key)
            if data is None:
                return json_response({"success": True, "data": {"fixtures": [], "next_page": False}})
            return json_response({"success": True, "data": copy.deepcopy(data)})
        if path.endswith("matches/history.json"):
            assert params["competition_id"] == str(COMPETITION["id"]), params
            return json_response({"success": True, "data": copy.deepcopy(self.history_pages.get(page, {"match": [], "total_pages": 1}))})
        if path.endswith("matches/live.json"):
            return json_response({"success": True, "data": {"match": []}})
        raise AssertionError(f"unexpected request to {path}")


def provider_for(replies: Replies, at: datetime) -> LiveScoreAPIProvider:
    return LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=httpx.MockTransport(replies),
        budget=RequestBudget("livescore", 1200, client=FakeRedis(), now=at),
        competition_overrides={}, store=MatchCache(client=FakeRedis()), use_default_ids=True)


def service_at(db, replies: Replies, at: datetime) -> MatchDataService:
    """A pass at `at` with its own empty cache: every answer it uses is one it asked for, fresh."""
    return MatchDataService(db, providers=[provider_for(replies, at)], cache=MatchCache(client=FakeRedis()),
                            now=at, keys=[LEAGUE])


def listing_of(db, match: Match) -> Dict:
    return dict(((fresh(db, match.id).match_metadata or {}).get(LISTINGS_KEY) or {}).get(PROVIDER) or {})


def absences_of(db, match: Match) -> int:
    absent = listing_of(db, match).get("absent")
    return int(absent.get("listings") or 0) if isinstance(absent, dict) else 0


def assert_earlier_row_as_it_was(db, earlier: Match, *, with_result: bool = False) -> None:
    row = fresh(db, earlier.id)
    assert row.match_date == DROPPED_KICKOFF.replace(tzinfo=None), "the earlier row keeps its own kickoff"
    assert len(snapshots_of(db, row.id)) == 9, "its nine snapshots are its own"
    refs = refs_of(db, row.id)
    assert ("gameforecast", FORECAST_EVENT) in refs and (PROVIDER, DEAD_ID) in refs
    assert (PROVIDER, LIVE_ID) not in refs, "the new id was never written onto it"
    assert "superseded_by" not in (refs[(PROVIDER, DEAD_ID)].ref_metadata or {})
    assert (result_of(db, row.id) == (2, 0)) is with_result


# =========================================================== 1. calendar and results answers name what they name
@pytest.mark.parametrize("order", ["old-first", "new-first"])
def test_a_calendar_naming_both_ids_merges_nothing_whichever_comes_first(db, order):
    """An absence stands against the earlier listing; the calendar answer then names BOTH ids. The
    old id is marked seen before either is stored, so the new id finds its withdrawal contradicted
    and becomes its own row; the old id is applied to its own row and refused by nothing."""
    earlier = earlier_listing(db)                          # absent from the 25th's complete listing at 23:11
    replies = Replies()
    rows = [OLD_LISTED, NEW_LISTED] if order == "old-first" else [NEW_LISTED, OLD_LISTED]
    replies.fixtures(None, 1, rows, next_page=False)

    meta = service_at(db, replies, MORNING_AFTER).sync_upcoming(LEAGUE, 7)

    assert meta.source == "provider" and meta.errors == [] and meta.ambiguous == 0, (meta.source, meta.errors)
    assert [dict(c) for c in replies.calls("fixtures/list.json")] == [{"competition_id": "5"}], "one calendar page"
    rows_now = psg_lyon_rows(db)
    assert [m.id for m in rows_now if m.id == earlier.id] == [earlier.id] and len(rows_now) == 2, (
        "two rows: the new id was merged onto the earlier row on an absence the same answer contradicted")
    assert_earlier_row_as_it_was(db, earlier)
    assert listing_of(db, earlier)["seen_at"] == MORNING_AFTER.isoformat()
    assert MatchRegistry.withdrawal_observed(fresh(db, earlier.id), PROVIDER) is None
    new_row = next(m for m in rows_now if m.id != earlier.id)
    assert new_row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and (PROVIDER, LIVE_ID) in refs_of(db, new_row.id)
    assert len(snapshots_of(db, new_row.id)) == 0, "nothing of the earlier row moved"


@pytest.mark.parametrize("order", ["old-first", "new-first"])
def test_a_results_answer_naming_both_ids_merges_nothing_whichever_comes_first(db, order):
    """The results import for the 25th: the earlier listing is pending, so Live Score's archive is
    asked and answers with both ids finished. Neither order merges: the old id's result lands on its
    own row, the new id is its own row, and nothing is refused."""
    earlier = earlier_listing(db)
    replies = Replies()
    rows = [OLD_FINISHED, NEW_FINISHED] if order == "old-first" else [NEW_FINISHED, OLD_FINISHED]
    replies.history_pages = {1: {"match": rows, "total_pages": 1}}
    service = service_at(db, replies, MORNING_AFTER)
    meta = SyncMeta()

    outcome = service._sync_results(DROPPED_KICKOFF.date(), meta)

    assert outcome in ("answered", "mixed"), (outcome, meta.errors)
    assert meta.source == "provider" and meta.ambiguous == 0, (meta.source, meta.errors)
    history = replies.calls("matches/history.json")
    assert len(history) == 1 and history[0]["from"] == history[0]["to"] == "2026-10-25"
    rows_now = psg_lyon_rows(db)
    assert len(rows_now) == 2, "two rows: a merge happened on an absence the same answer contradicted"
    assert_earlier_row_as_it_was(db, earlier, with_result=True)
    assert fresh(db, earlier.id).status == MatchStatus.FINISHED
    new_row = next(m for m in rows_now if m.id != earlier.id)
    assert result_of(db, new_row.id) == (2, 0) and (PROVIDER, LIVE_ID) in refs_of(db, new_row.id)
    assert len(snapshots_of(db, new_row.id)) == 0
    assert MatchRegistry.withdrawal_observed(fresh(db, earlier.id), PROVIDER) is None


def test_a_calendar_that_no_longer_names_the_old_id_leaves_the_observed_absence_standing_and_the_join_happens(db):
    """The passing replacement, through the calendar: the absence was observed, the calendar names
    only the new id, and the new id joins the earlier row with everything on it."""
    earlier = earlier_listing(db)
    replies = Replies()
    replies.fixtures(None, 1, [NEW_LISTED], next_page=False)

    meta = service_at(db, replies, MORNING_AFTER).sync_upcoming(LEAGUE, 7)

    assert meta.errors == [] and meta.ambiguous == 0
    rows_now = psg_lyon_rows(db)
    assert [m.id for m in rows_now] == [earlier.id]
    row = fresh(db, earlier.id)
    assert row.match_date == PLAYED_KICKOFF.replace(tzinfo=None) and len(snapshots_of(db, row.id)) == 9
    assert {(PROVIDER, DEAD_ID), (PROVIDER, LIVE_ID), ("gameforecast", FORECAST_EVENT)} <= set(refs_of(db, row.id))


# =========================================================== 2. a listing is only as complete as its pages were read
def day_listing(db, replies: Replies) -> SyncMeta:
    return service_at(db, replies, MORNING_AFTER).sync_day(DROPPED_KICKOFF.date())


def fixture_pages_asked(replies: Replies) -> List[str]:
    return [c.get("page", "1") for c in replies.calls("fixtures/list.json") if c.get("date") == "2026-10-25"]


def test_an_empty_first_page_with_a_next_page_is_read_on_and_the_old_id_found_on_page_two(db):
    earlier = earlier_listing(db)                          # one absence already stands
    replies = Replies()
    replies.fixtures("2026-10-25", 1, [], next_page=True)
    replies.fixtures("2026-10-25", 2, [OLD_LISTED], next_page=False)

    meta = day_listing(db, replies)

    assert meta.errors == [] and fixture_pages_asked(replies) == ["1", "2"], "page two was read"
    assert listing_of(db, earlier)["seen_at"] == MORNING_AFTER.isoformat(), "named on page two: seen"
    assert absences_of(db, earlier) == 1, "no new absence: the previous implementation recorded one off the empty first page"
    assert MatchRegistry.withdrawal_observed(fresh(db, earlier.id), PROVIDER) is None
    second = stored(db, played(), MORNING_AFTER + timedelta(hours=13))
    assert second.id != earlier.id, "nothing joins a listing the provider still names"
    assert_earlier_row_as_it_was(db, earlier)


def test_an_empty_page_in_the_middle_does_not_end_the_listing(db):
    earlier = earlier_listing(db)
    replies = Replies()
    replies.fixtures("2026-10-25", 1, [OTHER_LISTED], next_page=True)
    replies.fixtures("2026-10-25", 2, [], next_page=True)
    replies.fixtures("2026-10-25", 3, [OLD_LISTED], next_page=False)

    meta = day_listing(db, replies)

    assert meta.errors == [] and fixture_pages_asked(replies) == ["1", "2", "3"]
    assert listing_of(db, earlier)["seen_at"] == MORNING_AFTER.isoformat() and absences_of(db, earlier) == 1


def test_the_total_pages_form_of_an_empty_first_page_is_read_on_too(db):
    earlier = earlier_listing(db)
    replies = Replies()
    replies.fixtures("2026-10-25", 1, [], total_pages=2)
    replies.fixtures("2026-10-25", 2, [OLD_LISTED], total_pages=2)

    meta = day_listing(db, replies)

    assert meta.errors == [] and fixture_pages_asked(replies) == ["1", "2"]
    assert listing_of(db, earlier)["seen_at"] == MORNING_AFTER.isoformat() and absences_of(db, earlier) == 1


def test_a_listing_cut_at_the_page_cap_is_no_evidence_of_absence(db):
    """Every page up to MAX_PAGES is empty and advertises another; the old id would be on the page
    after the cap. The cap is not raised; the answer is marked cut, and nothing is recorded absent."""
    earlier = earlier_listing(db)
    replies = Replies()
    for page in range(1, MAX_PAGES + 1):
        replies.fixtures("2026-10-25", page, [], next_page=True)
    replies.fixtures("2026-10-25", MAX_PAGES + 1, [OLD_LISTED], next_page=False)

    meta = day_listing(db, replies)

    assert meta.errors == [] and fixture_pages_asked(replies) == [str(p) for p in range(1, MAX_PAGES + 1)]
    provider = next(p for p in service_at(db, Replies(), MORNING_AFTER).providers)   # the attribute's shape
    assert hasattr(provider, "truncated_keys")
    assert absences_of(db, earlier) == 1, "the unread page is not evidence that the fixture disappeared"
    assert "seen_day" not in listing_of(db, earlier) or listing_of(db, earlier)["seen_at"] != MORNING_AFTER.isoformat()


def test_a_later_page_that_fails_leaves_no_observation(db):
    earlier = earlier_listing(db)
    replies = Replies()
    replies.fixtures("2026-10-25", 1, [], next_page=True)
    replies.failures[("2026-10-25", 2)] = 500

    meta = day_listing(db, replies)

    assert meta.errors and fixture_pages_asked(replies) == ["1", "2"]
    assert absences_of(db, earlier) == 1 and listing_of(db, earlier)["seen_at"] != MORNING_AFTER.isoformat()


def test_a_genuinely_complete_empty_listing_is_a_valid_observation(db):
    """One empty page and nothing further advertised: the provider lists nothing for the day, and the
    earlier listing's absence is observed again - enough, with the rest, for the re-issue to join."""
    earlier = earlier_listing(db)
    replies = Replies()
    replies.fixtures("2026-10-25", 1, [], next_page=False)

    meta = day_listing(db, replies)

    assert meta.errors == [] and fixture_pages_asked(replies) == ["1"]
    assert absences_of(db, earlier) == 2 and listing_of(db, earlier)["absent"]["last"] == MORNING_AFTER.isoformat()
    second = stored(db, played(), MORNING_AFTER + timedelta(hours=13))
    assert second.id == earlier.id, "sufficient evidence: the re-issue joins"
