"""
Credential redaction for log lines and stored error text.

Live Score authenticates with `key` and `secret` QUERY parameters, so both credentials are part of
every request URL - and httpx writes every request URL to the log at INFO:

    httpx - INFO - HTTP Request: GET https://livescore-api.com/api-client/matches/live.json?key=...&secret=... "HTTP/1.1 200 OK"

The line is worth keeping: the path and the status are the cheapest record there is of what the
scheduler actually spent. Only the values go:

    ... /api-client/matches/live.json?key=REDACTED&secret=REDACTED "HTTP/1.1 200 OK"

TheSportsDB takes its key in the URL PATH instead - /api/v1/json/<key>/eventsnextleague.php - so
that segment is replaced too.

The same text reaches places other than the log. A provider error's message is stored in the Redis
status payload served by GET /api/v1/data-providers/status and in a match row's recovery
`last_provider_error`, so `ProviderError` redacts its own message with the same function.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

REDACTED = "REDACTED"

#: A query parameter whose NAME ends in one of these words carries a credential: key, api_key,
#: apikey, x-api-key, secret, client_secret, token, access_token, password... Matched without
#: regard to case. Ending in, not equal to, so that a provider's own spelling is covered without
#: being listed; the price is that a harmless `monkey=` is hidden too, which is the right way round.
#:
#: The name must start after a character that cannot be part of a name (`?`, `&`, a space, a
#: quote...), so `keyboard=` is left alone. A value already reading REDACTED is not matched again,
#: which is what lets `contains_credentials` answer "is anything still showing?".
_CREDENTIAL_PARAM = re.compile(
    r"(?<![\w.-])([\w.-]*(?:key|secret|token|password))="
    r"(?!" + REDACTED + r"(?:[&#\s'\"<>]|$))[^&#\s'\"<>]+",
    re.IGNORECASE,
)

#: TheSportsDB's v1 API carries its key as a path segment: /api/v1/json/<key>/eventsnextleague.php.
#: The segment is replaced whatever it holds - the public test key "123" too, which costs nothing.
_CREDENTIAL_PATH_SEGMENT = re.compile(
    r"(/api/v\d+/json/)"
    r"(?!" + REDACTED + r"(?:[/\s?#'\"<>]|$))[^/\s?#'\"<>]+",
    re.IGNORECASE,
)

#: Arguments of these types are formatted as themselves and cannot hold a query string.
_PLAIN_ARGS = (int, float, bool, type(None))

#: Renders a traceback once, so the rendered text can be redacted before any handler prints it.
_TRACEBACK_FORMATTER = logging.Formatter()


def redact_credentials(text: str) -> str:
    """`text` with every credential-bearing query value and path segment replaced by REDACTED."""
    text = _CREDENTIAL_PARAM.sub(r"\1=" + REDACTED, text)
    return _CREDENTIAL_PATH_SEGMENT.sub(r"\1" + REDACTED, text)


def contains_credentials(text: str) -> bool:
    """True when `text` still shows a credential-bearing query value or path segment."""
    return _CREDENTIAL_PARAM.search(text) is not None or _CREDENTIAL_PATH_SEGMENT.search(text) is not None


def _redact_arg(arg: Any) -> Any:
    """One logging argument, redacted - or returned untouched when there is nothing to hide.

    An argument is replaced only when it shows a credential, and then by its redacted text: an
    `httpx.URL` becomes a string, which `%s` prints identically. Numbers keep their type, so a
    `%d` beside the URL still formats.
    """
    if isinstance(arg, _PLAIN_ARGS):
        return arg
    if isinstance(arg, str):
        return redact_credentials(arg)
    try:
        text = str(arg)
        shown = contains_credentials(text) or contains_credentials(repr(arg))
    except Exception:
        return arg
    return redact_credentials(text) if shown else arg


def _redact_args(args: Any) -> Any:
    if isinstance(args, tuple):
        return tuple(_redact_arg(arg) for arg in args)
    if isinstance(args, dict):
        return {key: _redact_arg(value) for key, value in args.items()}
    return args


class CredentialRedactionFilter(logging.Filter):
    """Rewrites a log record so that no credential value reaches any handler. Drops nothing.

    The arguments are redacted one by one first, keeping the record's shape: a formatter that
    reads `record.args` positionally (uvicorn's access formatter does) still finds what it expects.
    Only when the credential is not in any single argument - a message that is itself an f-string,
    or a `key=%s` whose value arrives as an argument - is the finished message written back in
    place of the format and its arguments.

    A traceback attached to the record is rendered here and redacted, and handlers print the
    rendered text rather than rendering their own.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        self._redact_message(record)
        self._redact_traceback(record)
        return True

    @staticmethod
    def _redact_message(record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            # Arguments that do not fit the format. Logging reports such a record by printing its
            # msg and args as they are, so each is redacted in place.
            if isinstance(record.msg, str):
                record.msg = redact_credentials(record.msg)
            record.args = _redact_args(record.args)
            return
        if not contains_credentials(message):
            return
        if record.args:
            record.args = _redact_args(record.args)
            try:
                if not contains_credentials(record.getMessage()):
                    return
            except Exception:
                pass
        record.msg, record.args = redact_credentials(message), ()

    @staticmethod
    def _redact_traceback(record: logging.LogRecord) -> None:
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = _TRACEBACK_FORMATTER.formatException(record.exc_info)
            except Exception:
                return
        if record.exc_text:
            record.exc_text = redact_credentials(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_credentials(record.stack_info)


#: Loggers redacted at the source, before ANY handler sees their records - ours, a test's capture,
#: or one attached by someone else. httpx writes every request URL at INFO. A logger's filter does
#: not run for its children's records, so httpcore's loggers are named one by one.
SOURCE_LOGGERS = (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)


def _add_once(target: Any, redaction: CredentialRedactionFilter) -> None:
    if not any(isinstance(existing, CredentialRedactionFilter) for existing in target.filters):
        target.addFilter(redaction)


def install_credential_redaction(handlers: Optional[Iterable[logging.Handler]] = None) -> CredentialRedactionFilter:
    """Redact the source loggers, and every record that reaches one of `handlers`. Idempotent."""
    redaction = CredentialRedactionFilter()
    for name in SOURCE_LOGGERS:
        _add_once(logging.getLogger(name), redaction)
    for handler in handlers or ():
        _add_once(handler, redaction)
    return redaction
