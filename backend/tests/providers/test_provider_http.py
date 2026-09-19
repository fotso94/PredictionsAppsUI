"""
The provider's own accounting, read off the responses we already pay for.

RapidAPI returns three headers on every response, success and refusal alike:

    x-ratelimit-requests-limit / -remaining / -reset

Nothing in this codebase read them until now, and the cost of not reading them was measured on
2026-09-19: one minute into a new UTC day the GameForecastAPI counter was clean, the scheduler
spent two requests, and the third came back 429 - "you have exceeded the DAILY quota" - while our
own counter still showed five of eight left. The provider's window is not the UTC calendar day,
and it had been saying so in a header on every response.

These tests pin the reading and its limits. The headers are optional and best effort: a value
that cannot be read is ignored and the request behaves exactly as it did before. Nothing here
makes a real request - httpx.MockTransport throughout, and an in-memory Redis stand-in.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.providers.base import ProviderAuthError, ProviderQuotaError
from app.services.providers.budget import ProviderRateLimit, rate_limit_key
from app.services.providers.http import ProviderHttpClient, parse_rate_limit
from tests.providers.support import FakeRedis

#: One minute into the new UTC day, which is when the counter reset and the pass resumed.
NOW = datetime(2026, 9, 19, 0, 1, 10, tzinfo=timezone.utc)

#: The real 429 body, verbatim.
QUOTA_BODY = {"message": "You have exceeded the DAILY quota for Requests on your current plan, BASIC."}


class Sink:
    """Collects the readings the client takes, standing in for the Redis-backed store."""

    def __init__(self):
        self.readings = []

    def __call__(self, reading):
        self.readings.append(reading)


def client(handler, sink=None, now=NOW):
    return ProviderHttpClient("gameforecast", "https://game-forecast-api.p.rapidapi.com",
                              transport=httpx.MockTransport(handler),
                              rate_limit_sink=sink if sink is not None else Sink(),
                              now=lambda: now)


def responder(status=200, headers=None, payload=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload if payload is not None else {"data": []},
                              headers=headers or {})
    return handler


RAPIDAPI_HEADERS = {"x-ratelimit-requests-limit": "10",
                    "x-ratelimit-requests-remaining": "7",
                    "x-ratelimit-requests-reset": "25972"}


# --------------------------------------------------------------- the headers are read and recorded
def test_the_rate_limit_headers_are_read_from_a_successful_response():
    sink = Sink()
    payload = client(responder(200, RAPIDAPI_HEADERS), sink).get_json("/events")

    assert payload == {"data": []}
    reading, = sink.readings
    assert (reading.limit, reading.remaining, reading.reset_seconds) == (10, 7, 25972)
    assert reading.status_code == 200
    # The header is a duration; what is stored has to be an instant, or it would keep reading
    # "resets in 7 hours" for as long as it is kept.
    assert reading.reset_at == NOW + timedelta(seconds=25972)


def test_the_rate_limit_headers_are_read_from_a_429_as_well():
    """The refusal is the most informative response there is: it names the window we just hit."""
    sink = Sink()
    handler = responder(429, {"x-ratelimit-requests-limit": "10",
                              "x-ratelimit-requests-remaining": "0",
                              "x-ratelimit-requests-reset": "25972"}, QUOTA_BODY)

    with pytest.raises(ProviderQuotaError):
        client(handler, sink).get_json("/events")

    reading, = sink.readings
    assert (reading.limit, reading.remaining, reading.reset_seconds) == (10, 0, 25972)
    assert reading.status_code == 429


def test_an_auth_refusal_is_read_too():
    sink = Sink()
    with pytest.raises(ProviderAuthError):
        client(responder(403, RAPIDAPI_HEADERS, {"message": "not subscribed"}), sink).get_json("/events")
    assert sink.readings[0].remaining == 7


def test_the_reading_is_recorded_in_the_store_and_survives_a_restart():
    """In Redis, not in memory: the scheduler is in-process and the backend gets restarted."""
    redis = FakeRedis()
    store = ProviderRateLimit("gameforecast", client=redis, now=NOW)
    with pytest.raises(ProviderQuotaError):
        ProviderHttpClient("gameforecast", "https://x", transport=httpx.MockTransport(
            responder(429, {"x-ratelimit-requests-limit": "10",
                            "x-ratelimit-requests-remaining": "0",
                            "x-ratelimit-requests-reset": "10800"}, QUOTA_BODY)),
            rate_limit_sink=store.record, now=lambda: NOW).get_json("/events")

    assert rate_limit_key("gameforecast") in redis.store
    # A brand new process, the same store: the provider's window is still known.
    after_restart = ProviderRateLimit("gameforecast", client=redis, now=NOW + timedelta(minutes=5))
    assert after_restart.remaining_now() == 0
    assert after_restart.seconds_until_reset() == 10800 - 300
    # And it expires on its own rather than outliving the window it describes.
    assert redis.ttls[rate_limit_key("gameforecast")] > 10800


def test_the_header_names_are_matched_whatever_their_case():
    sink = Sink()
    client(responder(200, {"X-RateLimit-Requests-Limit": "10",
                           "X-RATELIMIT-REQUESTS-REMAINING": "4",
                           "X-Ratelimit-Requests-Reset": "600"}), sink).get_json("/events")
    reading, = sink.readings
    assert (reading.limit, reading.remaining, reading.reset_seconds) == (10, 4, 600)


# ------------------------------------------------------------- unreadable headers change nothing
@pytest.mark.parametrize("headers", [
    {},                                                                    # none at all
    {"x-ratelimit-requests-remaining": ""},                                # empty
    {"x-ratelimit-requests-remaining": "   "},                             # blank
    {"x-ratelimit-requests-remaining": "unlimited"},                       # not a number
    {"x-ratelimit-requests-remaining": "-3"},                              # not a count
    {"x-ratelimit-requests-reset": "NaN"},
    {"x-ratelimit-requests-limit": "ten", "x-ratelimit-requests-reset": ""},
])
def test_an_unusable_header_is_ignored_and_the_request_is_unaffected(headers):
    sink = Sink()
    payload = client(responder(200, headers, {"data": [1]}), sink).get_json("/events")
    assert payload == {"data": [1]}, "a header we cannot read must not change the response"
    assert sink.readings == [], "nothing was said, so nothing may be recorded"


def test_an_unusable_header_on_a_429_still_raises_exactly_as_before():
    sink = Sink()
    with pytest.raises(ProviderQuotaError) as exc:
        client(responder(429, {"x-ratelimit-requests-reset": "soon"}, QUOTA_BODY), sink).get_json("/events")
    assert "HTTP 429" in str(exc.value) and "DAILY quota" in str(exc.value)
    assert sink.readings == []


def test_a_partial_header_set_records_only_what_was_actually_said():
    """No defaults, no inference: a number the provider did not give stays None."""
    sink = Sink()
    client(responder(200, {"x-ratelimit-requests-remaining": "2"}), sink).get_json("/events")
    reading, = sink.readings
    assert reading.remaining == 2
    assert reading.limit is None and reading.reset_seconds is None and reading.reset_at is None


def test_a_response_with_no_headers_does_not_erase_what_the_provider_said_before():
    redis = FakeRedis()
    store = ProviderRateLimit("gameforecast", client=redis, now=NOW)
    ProviderHttpClient("gameforecast", "https://x",
                       transport=httpx.MockTransport(responder(200, RAPIDAPI_HEADERS)),
                       rate_limit_sink=store.record, now=lambda: NOW).get_json("/events")
    ProviderHttpClient("gameforecast", "https://x",
                       transport=httpx.MockTransport(responder(200, {})),
                       rate_limit_sink=store.record, now=lambda: NOW).get_json("/events")

    assert store.remaining_now() == 7, "silence is not a withdrawal of what was already said"


def test_a_store_that_will_not_answer_never_fails_the_request():
    class BrokenStore:
        def setex(self, *args, **kwargs):
            raise RuntimeError("redis is gone")

        def get(self, *args, **kwargs):
            raise RuntimeError("redis is gone")

    store = ProviderRateLimit("gameforecast", client=BrokenStore(), now=NOW)
    payload = ProviderHttpClient("gameforecast", "https://x",
                                 transport=httpx.MockTransport(responder(200, RAPIDAPI_HEADERS)),
                                 rate_limit_sink=store.record, now=lambda: NOW).get_json("/events")
    assert payload == {"data": []}
    assert store.remaining_now() is None, "a store that cannot be read is unknown, not zero"


def test_parsing_never_raises_whatever_it_is_handed():
    for response in (None, object(), httpx.Response(200)):
        reading = parse_rate_limit("gameforecast", response, now=NOW)
        assert reading.known is False


# ------------------------------------------------------------- unknown is unknown, never a number
def test_a_provider_that_has_never_sent_a_header_reads_as_unknown_not_as_zero():
    view = ProviderRateLimit("gameforecast", client=FakeRedis(), now=NOW).snapshot()
    assert view["known"] is False
    assert view["remaining"] is None and view["limit"] is None
    assert "never returned a rate-limit header" in view["detail"]
    assert ProviderRateLimit("gameforecast", client=FakeRedis(), now=NOW).remaining_now() is None


def test_a_reading_from_a_window_that_has_since_reset_reads_as_unknown_again():
    """A stale zero would refuse requests for a window the provider has already reopened."""
    redis = FakeRedis()
    ProviderRateLimit("gameforecast", client=redis, now=NOW).record(
        parse_rate_limit("gameforecast", httpx.Response(429, headers={
            "x-ratelimit-requests-limit": "10", "x-ratelimit-requests-remaining": "0",
            "x-ratelimit-requests-reset": "3600"}), now=NOW))

    during = ProviderRateLimit("gameforecast", client=redis, now=NOW + timedelta(minutes=30))
    assert during.remaining_now() == 0

    after = ProviderRateLimit("gameforecast", client=redis, now=NOW + timedelta(minutes=61))
    assert after.remaining_now() is None
    view = after.snapshot()
    assert view["known"] is True and view["window_expired"] is True
    assert view["remaining"] is None and view["remaining_as_observed"] == 0


# ------------------------------------------------------- the window is not the UTC day, said aloud
def test_a_window_that_is_not_the_utc_day_is_reported_as_such():
    """Tonight's reset was ~7h into the new UTC day: not the calendar day our counter is keyed to."""
    redis = FakeRedis()
    ProviderRateLimit("gameforecast", client=redis, now=NOW).record(
        parse_rate_limit("gameforecast", httpx.Response(429, headers={
            "x-ratelimit-requests-limit": "10", "x-ratelimit-requests-remaining": "0",
            "x-ratelimit-requests-reset": "25972"}), now=NOW))

    view = ProviderRateLimit("gameforecast", client=redis, now=NOW).snapshot()
    assert view["window_matches_utc_day"] is False
    assert "different windows" in view["window_note"]


def test_a_window_that_does_coincide_with_utc_midnight_is_not_flagged():
    redis = FakeRedis()
    seconds_to_midnight = int((datetime(2026, 9, 20, tzinfo=timezone.utc) - NOW).total_seconds())
    ProviderRateLimit("gameforecast", client=redis, now=NOW).record(
        parse_rate_limit("gameforecast", httpx.Response(200, headers={
            "x-ratelimit-requests-remaining": "5",
            "x-ratelimit-requests-reset": str(seconds_to_midnight)}), now=NOW))

    assert ProviderRateLimit("gameforecast", client=redis, now=NOW).snapshot()["window_matches_utc_day"] is True


def test_a_reset_that_is_plainly_not_a_duration_is_discarded():
    """An epoch timestamp read as "seconds from now" would pause this provider for decades."""
    sink = Sink()
    client(responder(200, {"x-ratelimit-requests-remaining": "3",
                           "x-ratelimit-requests-reset": "1789000000"}), sink).get_json("/events")
    reading, = sink.readings
    assert reading.remaining == 3, "the count it did give is still usable"
    assert reading.reset_seconds is None and reading.reset_at is None
