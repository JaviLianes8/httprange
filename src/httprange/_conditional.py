"""If-Range evaluation (RFC 9110 13.1.5)."""

from __future__ import annotations

import re
from datetime import datetime

from ._checks import optional_str, plain_bool, plain_str
from ._dates import parse_http_date, to_utc
from ._errors import MalformedDate, RangeError
from ._numbers import OWS

# entity-tag = [ "W/" ] DQUOTE *etagc DQUOTE, etagc = %x21 / %x23-7E / obs-text.
_ETAG = re.compile(r'(W/)?"([\x21\x23-\x7e\x80-\xff]*)"')


def if_range_matches(
    if_range: str,
    *,
    etag: str | None = None,
    last_modified: datetime | str | None = None,
    date_is_strong: bool = True,
) -> bool:
    """Evaluate an ``If-Range`` value against the current validators (RFC 9110 13.1.5).

    An entity-tag (it has a DQUOTE in its first three characters) matches only by
    strong comparison with ``etag``, the current ``ETag`` value: a weak tag on either
    side never matches. An HTTP-date matches only when it names the same second as
    ``last_modified`` (an aware ``datetime`` or an HTTP-date), and only if the date is a
    strong validator (RFC 9110 8.8.2.2): pass ``date_is_strong=False`` when the
    representation can change twice within one second. A malformed value never
    matches. A wrong type or a naive ``datetime`` raises :class:`RangeError`, whichever
    kind of validator ``if_range`` holds. When this returns False the server MUST
    ignore ``Range`` and send 200.

    >>> if_range_matches('"v1"', etag='"v1"')
    True
    >>> if_range_matches('W/"v1"', etag='W/"v1"')
    False
    >>> if_range_matches("Sun, 06 Nov 1994 08:49:37 GMT",
    ...                  last_modified="Sun, 06 Nov 1994 08:49:37 GMT")
    True
    """
    text = plain_str(if_range, RangeError, "if_range").strip(OWS)
    current_tag = optional_str(etag, RangeError, "etag")
    strong = plain_bool(date_is_strong, "date_is_strong")
    current = validator_date(last_modified)
    if '"' in text[:3]:
        tag = _strong_tag(text)
        return tag is not None and current_tag is not None and tag == _strong_tag(current_tag)
    if current is None or not strong:
        return False
    try:
        return parse_http_date(text) == current
    except MalformedDate:
        return False


def validator_date(value: object) -> datetime | None:
    """``last_modified`` as an aware UTC instant cut to the second, or ``None``.

    ``None`` and a string that is not an HTTP-date give ``None``; other types and naive
    datetimes raise :class:`RangeError`.
    """
    if value is None:
        return None
    if issubclass(type(value), datetime):
        return to_utc(value, "last_modified").replace(microsecond=0)
    text = plain_str(value, RangeError, "last_modified")
    try:
        return parse_http_date(text)
    except MalformedDate:
        return None


def _strong_tag(value: str) -> str | None:
    match = _ETAG.fullmatch(value.strip(OWS))
    if match is None or match.group(1):
        return None
    return match.group(2)
