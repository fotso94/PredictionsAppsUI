"""
Provider credentials stay out of the log, and out of the error text we store.

Live Score authenticates with `key` and `secret` QUERY parameters, so both are part of every request
URL, and httpx logs every request URL at INFO. Until this was fixed the backend's stdout log held one
line like this for every request the scheduler made, credentials in full:

    httpx - INFO - HTTP Request: GET https://livescore-api.com/api-client/matches/live.json?key=...&secret=... "HTTP/1.1 200 OK"

The line is kept, because the path and the status are useful. Only the values are replaced.

A provider error's message goes further than the log: it is stored in the Redis status payload
served by GET /api/v1/data-providers/status and in a match row's recovery `last_provider_error`.

TheSportsDB carries its key in the URL PATH instead, /api/v1/json/<key>/..., and that line was found
in the live log after the query rule shipped, so the segment is replaced too.

The credentials below are fakes. Nothing here makes a real request - httpx.MockTransport throughout.
"""

import io
import json
import logging
import sys
from datetime import date

import httpx
import pytest

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redaction import (
    REDACTED, SOURCE_LOGGERS, CredentialRedactionFilter, contains_credentials, redact_credentials,
)
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService
from app.services.providers.base import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.providers.thesportsdb_provider import TheSportsDBProvider
from tests.providers.support import FakeRedis, json_response, make_transport

KEY = "abc123"
SECRET = "xyz789"
BASE_URL = "https://livescore-api.com/api-client"
PATH = "/api-client/matches/live.json"
URL = f"https://livescore-api.com{PATH}?key={KEY}&secret={SECRET}"
REDACTED_QUERY = f"{PATH}?key={REDACTED}&secret={REDACTED}"

#: A fake TheSportsDB key, which that provider sends as a path segment rather than a parameter.
PATH_KEY = "654321"


def assert_hidden(text):
    """Neither value appears, and the path they were attached to still does."""
    assert KEY not in text
    assert SECRET not in text
    assert PATH in text


def record(msg, args=(), name="httpx"):
    return logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)


@pytest.fixture(params=["text", "json"])
def app_log(request, monkeypatch):
    """The application's logging exactly as setup_logging installs it, writing to a buffer.

    Returns a function that reads what has been written so far. setup_logging replaces the root
    logger's handlers, so the handlers pytest had there are put back afterwards.
    """
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(settings, "LOG_FORMAT", request.param)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    setup_logging()
    try:
        yield buffer.getvalue
    finally:
        root.handlers = handlers
        root.setLevel(level)


@pytest.fixture
def no_throttle(monkeypatch):
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)


def live_score(handler):
    transport, recorder = make_transport(handler)
    provider = LiveScoreAPIProvider(api_key=KEY, api_secret=SECRET, base_url=BASE_URL, transport=transport,
                                    budget=RequestBudget("livescore", 100, client=FakeRedis()),
                                    competition_overrides={}, store=MatchCache(client=FakeRedis()))
    return provider, recorder


def http_client(handler):
    return ProviderHttpClient("livescore", BASE_URL, transport=httpx.MockTransport(handler),
                              rate_limit_sink=lambda reading: None)


# --------------------------------------------------------------------------- the log


def test_a_live_score_request_is_logged_with_its_path_and_status_but_not_its_credentials(app_log, no_throttle):
    provider, recorder = live_score(lambda request: json_response({"success": True, "data": {"match": []}}))

    provider.get_live(["premier_league"])

    # The request really did carry both values: this is the line that used to print them.
    sent = recorder.requests[0].url
    assert (sent.params["key"], sent.params["secret"]) == (KEY, SECRET)
    out = app_log()
    lines = [line for line in out.splitlines() if "HTTP Request" in line]
    assert len(lines) == 1, out
    assert_hidden(out)
    assert REDACTED_QUERY in lines[0]
    assert "HTTP/1.1 200 OK" in lines[0].replace('\\"', '"')


def test_a_thesportsdb_request_is_logged_without_the_key_in_its_path(app_log):
    transport, recorder = make_transport(lambda request: json_response({"events": []}))
    provider = TheSportsDBProvider(api_key=PATH_KEY, transport=transport,
                                   budget=RequestBudget("thesportsdb", 100, client=FakeRedis()))

    provider.get_fixtures(date(2026, 9, 25), ["premier_league"])

    assert f"/json/{PATH_KEY}/" in recorder.requests[0].url.path
    out = app_log()
    lines = [line for line in out.splitlines() if "HTTP Request" in line]
    assert len(lines) == 1, out
    assert PATH_KEY not in out
    assert f"/api/v1/json/{REDACTED}/eventsnextleague.php" in lines[0]


def test_every_record_reaching_the_root_handler_is_redacted_however_it_was_built(app_log):
    log = logging.getLogger("app.services.example")

    log.warning("could not reach %s", URL)                     # the URL as an argument
    log.warning(f"could not reach {URL}")                      # a message formatted in advance
    log.warning("could not reach %s?key=%s&secret=%s", f"https://livescore-api.com{PATH}", KEY, SECRET)
    log.warning("could not reach %(url)s", {"url": URL})       # a mapping of arguments

    out = app_log()
    assert_hidden(out)
    assert out.count(REDACTED_QUERY) == 4, out


def test_a_logged_traceback_is_redacted(app_log):
    try:
        raise httpx.ConnectError(f"could not connect to {URL}")
    except httpx.ConnectError:
        logging.getLogger("app.services.example").exception("provider call failed")

    out = app_log()
    assert_hidden(out)
    assert "httpx.ConnectError" in out
    assert REDACTED_QUERY in out


def test_setup_logging_redacts_the_http_loggers_at_the_source(app_log):
    """A filter on the logger runs before every handler - including ones setup_logging never saw."""
    for name in SOURCE_LOGGERS:
        filters = logging.getLogger(name).filters
        assert sum(isinstance(f, CredentialRedactionFilter) for f in filters) == 1, name

    stray = io.StringIO()
    handler = logging.StreamHandler(stray)                     # no filter of its own
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.addHandler(handler)
    try:
        http_client(lambda request: json_response({"success": True})).get_json(
            "matches/live.json", {"key": KEY, "secret": SECRET})
    finally:
        httpx_logger.removeHandler(handler)

    assert_hidden(stray.getvalue())
    assert REDACTED_QUERY in stray.getvalue()


def test_setup_logging_run_twice_installs_one_filter(app_log):
    setup_logging()
    assert sum(isinstance(f, CredentialRedactionFilter) for f in logging.getLogger("httpx").filters) == 1
    for handler in logging.getLogger().handlers:
        assert sum(isinstance(f, CredentialRedactionFilter) for f in handler.filters) == 1


# --------------------------------------------------------------------------- the filter itself


def test_the_httpx_request_line_keeps_everything_but_the_values():
    """httpx's own call: the URL arrives as an httpx.URL object, beside a %d status."""
    line = record('HTTP Request: %s %s "%s %d %s"', ("GET", httpx.URL(URL), "HTTP/1.1", 200, "OK"))

    assert CredentialRedactionFilter().filter(line) is True
    assert line.getMessage() == (
        f'HTTP Request: GET https://livescore-api.com{REDACTED_QUERY} "HTTP/1.1 200 OK"')


def test_arguments_keep_their_shape_for_formatters_that_unpack_them():
    """uvicorn's access formatter unpacks record.args by position; collapsing them would crash it."""
    line = record('%s - "%s %s HTTP/%s" %d',
                  ("127.0.0.1:5000", "GET", f"{PATH}?key={KEY}&secret={SECRET}", "1.1", 200),
                  name="uvicorn.access")

    CredentialRedactionFilter().filter(line)

    client_addr, method, full_path, http_version, status_code = line.args
    assert full_path == REDACTED_QUERY
    assert (client_addr, method, http_version, status_code) == ("127.0.0.1:5000", "GET", "1.1", 200)


def test_a_record_with_nothing_to_hide_is_left_exactly_as_it_was():
    url = httpx.URL(f"https://livescore-api.com{PATH}?competition_id=2")
    line = record('HTTP Request: %s %s "%s %d %s"', ("GET", url, "HTTP/1.1", 200, "OK"))

    CredentialRedactionFilter().filter(line)

    assert line.args[1] is url
    assert line.msg == 'HTTP Request: %s %s "%s %d %s"'


def test_a_record_whose_arguments_do_not_fit_is_still_redacted():
    """Logging prints such a record's msg and args raw when it reports the formatting error."""
    line = record("could not reach %s %s", (URL,))

    CredentialRedactionFilter().filter(line)

    assert KEY not in repr(line.args) and SECRET not in repr(line.args)


@pytest.mark.parametrize("name", ["key", "secret", "api_key", "apikey", "API_KEY", "Key", "token",
                                  "access_token", "x-api-key", "client_secret", "password"])
def test_every_credential_parameter_name_is_redacted_whatever_its_case(name):
    text = f"GET {PATH}?{name}={KEY}&page=2"

    assert redact_credentials(text) == f"GET {PATH}?{name}={REDACTED}&page=2"


def test_other_parameters_and_lookalike_names_are_left_alone():
    text = f"GET {PATH}?competition_id=2&keyboard=1&tokens=3&from=2026-09-20"

    assert redact_credentials(text) == text
    assert not contains_credentials(text)


def test_a_key_carried_as_a_path_segment_is_redacted_and_the_rest_of_the_path_kept():
    url = f"https://www.thesportsdb.com/api/v1/json/{PATH_KEY}/eventsnextleague.php?id=4328"

    assert redact_credentials(url) == (
        f"https://www.thesportsdb.com/api/v1/json/{REDACTED}/eventsnextleague.php?id=4328")
    # As a bare base URL, the form it takes in a client's configuration.
    assert redact_credentials(f"https://www.thesportsdb.com/api/v1/json/{PATH_KEY}") == (
        f"https://www.thesportsdb.com/api/v1/json/{REDACTED}")
    assert contains_credentials(url)
    assert not contains_credentials(redact_credentials(url))


def test_redaction_is_idempotent():
    once = redact_credentials(URL)

    assert redact_credentials(once) == once
    assert not contains_credentials(once)
    assert contains_credentials(URL)


# --------------------------------------------------------------------------- stored error text


def test_a_provider_error_never_carries_a_credential_whoever_wrote_its_message():
    exc = ProviderUnavailableError(f"livescore: something about {URL}", provider="livescore")

    assert_hidden(str(exc))
    assert REDACTED_QUERY in str(exc)
    assert exc.provider == "livescore"


def test_a_network_error_that_quotes_the_url_is_redacted_before_it_is_stored():
    def refuse(request):
        raise httpx.ConnectError(f"could not connect to {request.url}", request=request)

    with pytest.raises(ProviderUnavailableError) as caught:
        http_client(refuse).get_json("matches/live.json", {"key": KEY, "secret": SECRET})

    assert_hidden(str(caught.value))
    assert "network error" in str(caught.value)


@pytest.mark.parametrize("status, error", [(400, ProviderUnavailableError), (401, ProviderAuthError)])
def test_a_provider_body_that_echoes_the_url_is_redacted_before_it_is_stored(status, error):
    echo = lambda request: httpx.Response(status, text=f"bad request for {request.url}")

    with pytest.raises(error) as caught:
        http_client(echo).get_json("matches/live.json", {"key": KEY, "secret": SECRET})

    assert_hidden(str(caught.value))
    assert f"HTTP {status}" in str(caught.value)


def test_live_score_reporting_an_error_about_its_own_query_is_redacted(no_throttle):
    provider, _ = live_score(lambda request: json_response(
        {"success": False, "error": f"invalid key={KEY} or secret={SECRET} for {PATH}"}))

    with pytest.raises(ProviderError) as caught:
        provider.get_live(["premier_league"])

    assert_hidden(str(caught.value))


def test_the_status_payload_served_to_operators_carries_no_credential(no_throttle):
    """What GET /api/v1/data-providers/status serves: the chain's stored error and cool-down."""
    provider, _ = live_score(lambda request: httpx.Response(400, text=f"bad request for {request.url}"))
    service = MatchDataService(None, providers=[provider], cache=MatchCache(client=FakeRedis()),
                               keys=["premier_league"])

    rows, meta = service.standings("premier_league")

    assert rows == [] and meta.errors
    status = service.provider_status()
    livescore = status["chain"][0]
    assert "HTTP 400" in livescore["last_error"] and "HTTP 400" in livescore["cooling_down"]
    served = json.dumps(status, default=str)
    assert KEY not in served and SECRET not in served
    assert f"secret={REDACTED}" in livescore["last_error"]
