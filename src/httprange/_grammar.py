"""Strict RFC 9110 grammar for the Range and Accept-Ranges header fields."""

from __future__ import annotations

from dataclasses import dataclass

from ._errors import MalformedRange
from ._numbers import OWS, is_token
from ._spec import UNIT, RangeSpec, parse_spec

# RFC 9110 5.6.1.2: accept "a reasonable number" of empty list elements, not so many
# that they become a denial-of-service vector.
MAX_EMPTY_ELEMENTS = 16
# other-range = 1*( %x21-2B / %x2D-7E ), i.e. visible characters except the comma.
_OTHER_CHARS = frozenset(chr(code) for code in range(0x21, 0x7F)) - {","}


@dataclass(frozen=True, slots=True)
class RangeRequest:
    """A parsed ``Range`` header: ``ranges-specifier = range-unit "=" range-set``.

    ``unit`` is lower-cased (range units are case-insensitive, RFC 9110 14.1). For the
    ``bytes`` unit, ``specs`` holds the range-specs in request order and ``other`` is
    empty. For any other unit, ``specs`` is empty and ``other`` keeps each range-spec as
    raw text, because only the unit's own definition gives it meaning.
    """

    unit: str
    specs: tuple[RangeSpec, ...] = ()
    other: tuple[str, ...] = ()

    @property
    def is_bytes(self) -> bool:
        """True when the unit is ``bytes``, the only unit RFC 9110 defines."""
        return self.unit == UNIT

    def __str__(self) -> str:
        """The canonical header value, for example ``'bytes=0-499,-500'``."""
        items = [str(spec) for spec in self.specs] if self.is_bytes else list(self.other)
        return f"{self.unit}={','.join(items)}"


def parse_range_request(value: str, *, max_empty: int = MAX_EMPTY_ELEMENTS) -> RangeRequest:
    """Parse a ``Range`` header value with the strict RFC 9110 grammar.

    No whitespace may surround the unit or sit inside a range-spec; optional
    whitespace is allowed after ``=`` and around commas, and up to ``max_empty``
    empty list elements are ignored (RFC 9110 5.6.1.2). Byte ranges follow 14.1.2:
    ``bytes=0-499``, ``bytes=9500-``, ``bytes=-500``, ``bytes=0-0,-1``. An int-range
    whose last position precedes the first is invalid. Raises :class:`MalformedRange`.
    """
    text = value.strip(OWS)
    unit, sep, raw = text.partition("=")
    if not sep:
        raise MalformedRange(f"missing '=' in range header {value[:80]!r}")
    if not is_token(unit):
        raise MalformedRange(f"range unit {unit[:80]!r} is not a token")
    items = _split_list(raw, max_empty)
    unit = unit.lower()
    if unit == UNIT:
        return RangeRequest(unit, specs=tuple(_bytes_spec(item) for item in items))
    for item in items:
        if not all(char in _OTHER_CHARS for char in item):
            raise MalformedRange(f"invalid range-spec {item[:80]!r}")
    return RangeRequest(unit, other=tuple(items))


def parse_accept_ranges(value: str, *, max_empty: int = MAX_EMPTY_ELEMENTS) -> tuple[str, ...]:
    """Parse an ``Accept-Ranges`` value into lower-cased range units (RFC 9110 14.3).

    ``'bytes'`` gives ``('bytes',)``; ``'none'`` gives ``('none',)``, the reserved unit
    a server sends to advise against range requests.
    """
    units = _split_list(value.strip(OWS), max_empty)
    for unit in units:
        if not is_token(unit):
            raise MalformedRange(f"range unit {unit[:80]!r} is not a token")
    return tuple(unit.lower() for unit in units)


def _split_list(raw: str, max_empty: int) -> list[str]:
    elements = [item.strip(OWS) for item in raw.split(",")]
    items = [item for item in elements if item]
    if len(elements) - len(items) > max_empty:
        raise MalformedRange(f"more than {max_empty} empty list elements")
    if not items:
        raise MalformedRange("the list holds no elements")
    return items


def _bytes_spec(item: str) -> RangeSpec:
    if any(char in OWS for char in item):
        raise MalformedRange(f"whitespace inside range-spec {item[:80]!r}")
    if item.count("-") != 1:
        raise MalformedRange(f"invalid bytes range-spec {item[:80]!r}")
    return parse_spec(item)
