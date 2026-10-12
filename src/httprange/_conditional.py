"""If-Range evaluation and HTTP-date handling (RFC 9110 13.1.5 and 5.6.7)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ._errors import MalformedDate, RangeError
from ._numbers import OWS

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_LONG_DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MON = "|".join(_MONTHS)
_TIME = r"(\d{2}):(\d{2}):(\d{2})"
_IMF = re.compile(rf"(?:{'|'.join(_DAYS)}), (\d{{2}}) ({_MON}) (\d{{4}}) {_TIME} GMT", re.ASCII)
_RFC850 = re.compile(rf"(?:{_LONG_DAYS}), (\d{{2}})-({_MON})-(\d{{2}}) {_TIME} GMT", re.ASCII)
_ASCTIME = re.compile(rf"(?:{'|'.join(_DAYS)}) ({_MON}) ([ \d]\d) {_TIME} (\d{{4}})", re.ASCII)
# entity-tag = [ "W/" ] DQUOTE *etagc DQUOTE, etagc = %x21 / %x23-7E / obs-text.
_ETAG = re.compile(r'(W/)?"([\x21\x23-\x7e\x80-\xff]*)"')


def parse_http_date(value: str, *, now: datetime | None = None) -> datetime:
    """Parse an HTTP-date in any of the three RFC 9110 5.6.7 formats, as aware UTC.

    ``'Sun, 06 Nov 1994 08:49:37 GMT'`` (IMF-fixdate), ``'Sunday, 06-Nov-94 08:49:37
    GMT'`` (RFC 850) and ``'Sun Nov  6 08:49:37 1994'`` (asctime) all give the same
    instant. A two-digit RFC 850 year that would land more than 50 years after ``now``
    (default: the current time) means the most recent past year with those digits. A
    leap second (``:60``) is read as ``:59``, as ``datetime`` cannot hold it.
    """
    text = value.strip(OWS)
    if match := _IMF.fullmatch(text):
        day, month, year, hour, minute, second = match.groups()
    elif match := _RFC850.fullmatch(text):
        day, month, short, hour, minute, second = match.groups()
        year = str(_full_year(int(short), now or datetime.now(timezone.utc)))
    elif match := _ASCTIME.fullmatch(text):
        month, day, hour, minute, second, year = match.groups()
    else:
        raise MalformedDate(f"not an HTTP-date: {value[:80]!r}")
    try:
        return datetime(
            int(year),
            _MONTHS.index(month) + 1,
            int(day),
            int(hour),
            int(minute),
            min(int(second), 59),
            tzinfo=timezone.utc,
        )
    except ValueError:
        raise MalformedDate(f"impossible date: {value[:80]!r}") from None


def format_http_date(when: datetime) -> str:
    """Format an aware ``datetime`` as an IMF-fixdate, the form senders MUST use."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise RangeError("format_http_date needs a timezone-aware datetime")
    utc = when.astimezone(timezone.utc)
    return (
        f"{_DAYS[utc.weekday()]}, {utc.day:02d} {_MONTHS[utc.month - 1]} {utc.year:04d} "
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d} GMT"
    )


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
    side never matches. An HTTP-date matches only when it equals ``last_modified``
    exactly, to the second, and only if the date is a strong validator; pass
    ``date_is_strong=False`` unless the server reliably knows the representation did
    not change twice within that second (RFC 9110 8.8.2.2). A malformed value never
    matches. When this returns False the server MUST ignore ``Range`` and send 200.
    """
    text = if_range.strip(OWS)
    if '"' in text[:3]:
        tag = _strong_tag(text)
        return tag is not None and etag is not None and tag == _strong_tag(etag.strip(OWS))
    if last_modified is None or not date_is_strong:
        return False
    try:
        requested = parse_http_date(text)
        current = (
            parse_http_date(last_modified)
            if isinstance(last_modified, str)
            else parse_http_date(format_http_date(last_modified))
        )
    except MalformedDate:
        return False
    return requested == current


def _strong_tag(value: str) -> str | None:
    match = _ETAG.fullmatch(value)
    if match is None or match.group(1):
        return None
    return match.group(2)


def _full_year(short: int, now: datetime) -> int:
    year = now.year - now.year % 100 + short
    if year > now.year + 50:
        year -= 100
    return year
