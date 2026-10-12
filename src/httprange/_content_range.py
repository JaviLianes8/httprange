"""Build and parse Content-Range header values per RFC 9110 section 14.4."""

from __future__ import annotations

from dataclasses import dataclass

from ._errors import MalformedContentRange, RangeError
from ._numbers import OWS, check_int, is_token, to_int

UNIT = "bytes"


def build_content_range(
    start: int | None, end: int | None, total: int | None, *, unit: str = UNIT
) -> str:
    """Build a ``Content-Range`` header value.

    ``build_content_range(0, 499, 1234)`` returns ``'bytes 0-499/1234'``. Pass
    ``start`` and ``end`` as ``None`` for the unsatisfiable form ``'bytes */1234'`` of
    a 416 response, and ``total`` as ``None`` when the length is unknown
    (``'bytes 0-499/*'``). ``unit`` must be a token.
    """
    if not isinstance(unit, str) or not is_token(unit):
        raise RangeError(f"range unit {unit!r} is not a token")
    for name, value in (("start", start), ("end", end), ("total", total)):
        check_int(value, RangeError, name)
    if total is not None and total < 0:
        raise RangeError(f"total {total} is negative")
    size = "*" if total is None else str(total)
    if start is None and end is None:
        if total is None:
            raise RangeError("an unsatisfiable Content-Range needs a known total")
        return f"{unit} */{size}"
    if start is None or end is None:
        raise RangeError("start and end must both be set for a satisfied range")
    if start < 0 or end < start:
        raise RangeError(f"invalid range {start}-{end}")
    if total is not None and end >= total:
        raise RangeError(f"range {start}-{end} exceeds total {total}")
    return f"{unit} {start}-{end}/{size}"


@dataclass(frozen=True, slots=True)
class ContentRange:
    """A parsed ``Content-Range`` value.

    A satisfied range (206) has ``first`` and ``last`` set and ``complete_length``
    either set or ``None`` for ``*``. The unsatisfied form (416, ``bytes */1234``) has
    ``first`` and ``last`` as ``None`` and a ``complete_length``.
    :func:`parse_content_range` lower-cases ``unit``. Construction enforces the RFC
    9110 14.4 validity rules.
    """

    unit: str
    first: int | None
    last: int | None
    complete_length: int | None

    def __post_init__(self) -> None:
        try:
            build_content_range(self.first, self.last, self.complete_length, unit=self.unit)
        except RangeError as exc:
            raise MalformedContentRange(str(exc)) from None

    @property
    def is_satisfied(self) -> bool:
        """True for a 206 range, False for the 416 ``*/length`` form."""
        return self.first is not None

    @property
    def length(self) -> int | None:
        """Number of units enclosed, or ``None`` for the unsatisfied form."""
        if self.first is None or self.last is None:
            return None
        return self.last - self.first + 1

    def __str__(self) -> str:
        return build_content_range(self.first, self.last, self.complete_length, unit=self.unit)


def parse_content_range(value: str) -> ContentRange:
    """Parse a ``Content-Range`` value such as ``'bytes 42-1233/1234'``.

    Accepts ``range-unit SP ( range-resp / unsatisfied-range )``: ``bytes 0-499/1234``,
    ``bytes 42-1233/*`` and ``bytes */1234``. A last position before the first, or a
    complete length not above the last position, is invalid. Raises
    :class:`MalformedContentRange`.
    """
    text = value.strip(OWS)
    unit, sep, rest = text.partition(" ")
    if not sep or not is_token(unit):
        raise MalformedContentRange(f"expected '<unit> <range>/<length>', got {value[:80]!r}")
    unit = unit.lower()
    resp, slash, size = rest.partition("/")
    if not slash:
        raise MalformedContentRange(f"missing '/' in {value[:80]!r}")
    if resp == "*":
        return ContentRange(unit, None, None, _number(size, value))
    first, dash, last = resp.partition("-")
    if not dash:
        raise MalformedContentRange(f"missing '-' in {value[:80]!r}")
    complete = None if size == "*" else _number(size, value)
    return ContentRange(unit, _number(first, value), _number(last, value), complete)


def _number(text: str, value: str) -> int:
    return to_int(text, MalformedContentRange, value)
