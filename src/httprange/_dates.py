"""HTTP-date parsing and formatting (RFC 9110 5.6.7)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, cast

from ._checks import plain_str, short, type_name
from ._errors import MalformedDate, RangeError
from ._numbers import OWS

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_LONG_DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MON = "|".join(_MONTHS)
_TIME = r"(\d{2}):(\d{2}):(\d{2})"
_IMF = re.compile(rf"(?:{'|'.join(DAYS)}), (\d{{2}}) ({_MON}) (\d{{4}}) {_TIME} GMT", re.ASCII)
_RFC850 = re.compile(rf"(?:{_LONG_DAYS}), (\d{{2}})-({_MON})-(\d{{2}}) {_TIME} GMT", re.ASCII)
_ASCTIME = re.compile(rf"(?:{'|'.join(DAYS)}) ({_MON}) ([ \d]\d) {_TIME} (\d{{4}})", re.ASCII)
_Fields = tuple[str, str, str, str, str]


def parse_http_date(value: str, *, now: datetime | None = None) -> datetime:
    """Parse an HTTP-date in any of the three RFC 9110 5.6.7 formats, as aware UTC.

    The three examples of RFC 9110 5.6.7 give the same instant. A two-digit RFC 850
    year is read as the latest year with those digits that is not more than 50 years
    after ``now`` (an aware ``datetime``, default the current time). A leap second
    (``:60``) is read as ``:59``, as ``datetime`` cannot hold it, though
    :func:`if_range_matches` still tells the two apart. The day name is not
    checked against the date. Raises :class:`MalformedDate`; a ``now`` that is naive
    or not a ``datetime`` raises :class:`RangeError`.

    >>> parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT")
    datetime.datetime(1994, 11, 6, 8, 49, 37, tzinfo=datetime.timezone.utc)
    >>> parse_http_date("Sun Nov  6 08:49:37 1994") == parse_http_date(
    ...     "Sunday, 06-Nov-94 08:49:37 GMT")
    True
    """
    return read_http_date(value, now)[0]


def read_http_date(value: object, now: object = None) -> tuple[datetime, bool]:
    """Like :func:`parse_http_date`, plus whether the date names a leap second."""
    text = plain_str(value, MalformedDate, "value").strip(OWS)
    clock = None if now is None else to_utc(now, "now")
    if match := _IMF.fullmatch(text):
        day, month, year, hour, minute, second = match.groups()
    elif match := _RFC850.fullmatch(text):
        day, month, short_year, hour, minute, second = match.groups()
        clock = clock or datetime.now(timezone.utc)
        year = str(_full_year(short_year, (month, day, hour, minute, second), clock))
    elif match := _ASCTIME.fullmatch(text):
        month, day, hour, minute, second, year = match.groups()
    else:
        raise MalformedDate(f"not an HTTP-date: {short(text)}")
    if int(second) > 60:
        raise MalformedDate(f"second out of range: {short(text)}")
    moment = _moment(int(year), (month, day, hour, minute, second))
    if moment is None:
        raise MalformedDate(f"impossible date: {short(text)}")
    return moment, second == "60"


def format_http_date(when: datetime) -> str:
    """Format an aware ``datetime`` as an IMF-fixdate, the form senders MUST use.

    Microseconds are dropped. A naive ``datetime``, another type or an instant outside
    years 1 to 9999 in UTC raises :class:`RangeError`.

    >>> from datetime import datetime, timezone
    >>> format_http_date(datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc))
    'Sun, 06 Nov 1994 08:49:37 GMT'
    """
    utc = to_utc(when, "when")
    return (
        f"{DAYS[utc.weekday()]}, {utc.day:02d} {_MONTHS[utc.month - 1]} {utc.year:04d} "
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d} GMT"
    )


def to_utc(when: object, name: str) -> datetime:
    """An aware ``datetime`` converted to UTC, or :class:`RangeError`.

    The fields are read through the base class, so a subclass with its own methods
    cannot steer the result; an invalid offset from the ``tzinfo`` raises
    :class:`RangeError`.
    """
    if not issubclass(type(when), datetime):
        raise RangeError(f"{name} must be a timezone-aware datetime, got {type_name(when)}")
    moment = _plain(cast(datetime, when))
    try:
        offset = moment.utcoffset()
    except (ValueError, TypeError):
        raise RangeError(f"{name} has a tzinfo with an invalid UTC offset") from None
    if offset is None:
        raise RangeError(f"{name} must be a timezone-aware datetime, got {type_name(when)}")
    try:
        return (moment.replace(tzinfo=None) - offset).replace(tzinfo=timezone.utc)
    except OverflowError:
        raise RangeError(f"{name} is outside the years 1 to 9999 in UTC") from None


def _plain(moment: datetime) -> datetime:
    """A plain ``datetime`` with the fields of ``moment``, past any subclass override."""
    return datetime(
        _read(date, "year", moment),
        _read(date, "month", moment),
        _read(date, "day", moment),
        _read(datetime, "hour", moment),
        _read(datetime, "minute", moment),
        _read(datetime, "second", moment),
        _read(datetime, "microsecond", moment),
        tzinfo=_read(datetime, "tzinfo", moment),
        fold=_read(datetime, "fold", moment),
    )


def _read(owner: type, name: str, moment: datetime) -> Any:
    return vars(owner)[name].__get__(moment, owner)


def _moment(year: int, fields: _Fields) -> datetime | None:
    month, day, hour, minute, second = fields
    try:
        return datetime(
            year,
            _MONTHS.index(month) + 1,
            int(day),
            int(hour),
            int(minute),
            min(int(second), 59),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _full_year(digits: str, fields: _Fields, clock: datetime) -> int:
    """RFC 9110 5.6.7: the latest year with these digits not more than 50 years ahead."""
    limit = clock.year + 50
    base = clock.year - clock.year % 100 + int(digits)
    for year in (base + 100, base, base - 100):
        if year > limit:
            continue
        moment = _moment(year, fields)
        if year < limit or moment is None or moment <= _shift(clock, 50):
            return year
    return base - 100


def _shift(clock: datetime, years: int) -> datetime:
    """``clock`` moved ``years`` ahead; 29 February becomes 28 February when needed."""
    day = 28 if (clock.month, clock.day) == (2, 29) else clock.day
    try:
        return clock.replace(year=clock.year + years, day=day)
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)
