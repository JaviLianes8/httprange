"""Build and parse Content-Range header values per RFC 9110 section 14.4."""

from __future__ import annotations

from dataclasses import dataclass

from ._checks import optional_bounded_int, plain_str, short
from ._errors import MalformedContentRange, RangeError
from ._numbers import OWS, describe_int, int_text, is_token, to_int

UNIT = "bytes"


def build_content_range(
    start: int | None, end: int | None, total: int | None, *, unit: str = UNIT
) -> str:
    """Build a ``Content-Range`` header value.

    Pass ``start`` and ``end`` as ``None`` for the unsatisfiable form of a 416
    response, and ``total`` as ``None`` when the length is unknown. ``unit`` must be a
    token and is written as given. Positions are ints (not bools) of at most 4000
    digits. Anything RFC 9110 14.4 calls invalid raises :class:`RangeError`.

    >>> build_content_range(0, 499, 1234)
    'bytes 0-499/1234'
    >>> build_content_range(None, None, 1234)
    'bytes */1234'
    >>> build_content_range(42, 1233, None)
    'bytes 42-1233/*'
    """
    unit = plain_str(unit, RangeError, "unit")
    if not is_token(unit):
        raise RangeError(f"range unit {short(unit)} is not a token")
    start = optional_bounded_int(start, RangeError, "start")
    end = optional_bounded_int(end, RangeError, "end")
    total = optional_bounded_int(total, RangeError, "total")
    if total is not None and total < 0:
        raise RangeError(f"total {describe_int(total)} is negative")
    size = "*" if total is None else int_text(total)
    if start is None and end is None:
        if total is None:
            raise RangeError("an unsatisfiable Content-Range needs a known total")
        return f"{unit} */{size}"
    if start is None or end is None:
        raise RangeError("start and end must both be set for a satisfied range")
    if start < 0 or end < start:
        raise RangeError(f"invalid range {describe_int(start)}-{describe_int(end)}")
    if total is not None and end >= total:
        raise RangeError(
            f"range {describe_int(start)}-{describe_int(end)} exceeds total {describe_int(total)}"
        )
    return f"{unit} {int_text(start)}-{int_text(end)}/{size}"


@dataclass(frozen=True, slots=True)
class ContentRange:
    """A parsed ``Content-Range`` value.

    A satisfied range (206) has ``first`` and ``last`` set and ``complete_length``
    either set or ``None`` for ``*``. The unsatisfied form (416, ``bytes */1234``) has
    ``first`` and ``last`` as ``None`` and a ``complete_length``. ``unit`` is stored
    lower-cased, as range units are case-insensitive. Construction enforces the RFC
    9110 14.4 validity rules and raises :class:`MalformedContentRange`.

    >>> span = ContentRange("bytes", 0, 499, 1234)
    >>> span.length, span.is_satisfied, str(span)
    (500, True, 'bytes 0-499/1234')
    """

    unit: str
    first: int | None
    last: int | None
    complete_length: int | None

    def __post_init__(self) -> None:
        try:
            unit = plain_str(self.unit, RangeError, "unit")
            first = optional_bounded_int(self.first, RangeError, "first")
            last = optional_bounded_int(self.last, RangeError, "last")
            total = optional_bounded_int(self.complete_length, RangeError, "complete_length")
            # Checked before lower-casing: str.lower maps some non-ASCII letters to ASCII.
            build_content_range(first, last, total, unit=unit)
        except RangeError as exc:
            raise MalformedContentRange(str(exc)) from None
        object.__setattr__(self, "unit", unit.lower())
        object.__setattr__(self, "first", first)
        object.__setattr__(self, "last", last)
        object.__setattr__(self, "complete_length", total)

    @property
    def is_satisfied(self) -> bool:
        """True for a 206 range, False for the 416 ``*/length`` form.

        >>> parse_content_range("bytes */1234").is_satisfied
        False
        """
        return self.first is not None

    @property
    def length(self) -> int | None:
        """Number of units enclosed, or ``None`` for the unsatisfied form.

        >>> parse_content_range("bytes 42-1233/*").length
        1192
        """
        if self.first is None or self.last is None:
            return None
        return self.last - self.first + 1

    def __str__(self) -> str:
        return build_content_range(self.first, self.last, self.complete_length, unit=self.unit)


def parse_content_range(value: str) -> ContentRange:
    """Parse a ``Content-Range`` value such as ``'bytes 42-1233/1234'``.

    Accepts ``range-unit SP ( range-resp / unsatisfied-range )``: ``bytes 0-499/1234``,
    ``bytes 42-1233/*`` and ``bytes */1234``, for any token unit. A last position
    before the first, or a complete length not above the last position, is invalid.
    Raises :class:`MalformedContentRange`.

    >>> parse_content_range("Bytes 42-1233/1234")
    ContentRange(unit='bytes', first=42, last=1233, complete_length=1234)
    """
    text = plain_str(value, MalformedContentRange, "value").strip(OWS)
    unit, sep, rest = text.partition(" ")
    if not sep or not is_token(unit):
        raise MalformedContentRange(f"expected '<unit> <range>/<length>', got {short(text)}")
    resp, slash, size = rest.partition("/")
    if not slash:
        raise MalformedContentRange(f"missing '/' in {short(text)}")
    if resp == "*":
        return ContentRange(unit, None, None, _number(size, text))
    first, dash, last = resp.partition("-")
    if not dash:
        raise MalformedContentRange(f"missing '-' in {short(text)}")
    complete = None if size == "*" else _number(size, text)
    return ContentRange(unit, _number(first, text), _number(last, text), complete)


def _number(text: str, value: str) -> int:
    return to_int(text, MalformedContentRange, value)
