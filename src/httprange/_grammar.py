"""Strict RFC 9110 grammar for the Range and Accept-Ranges header fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ._checks import count, plain_items, plain_str, short, type_name
from ._errors import MalformedRange
from ._numbers import OWS, describe_int, is_token
from ._spec import UNIT, RangeSpec, parse_spec

# RFC 9110 5.6.1.2: accept "a reasonable number" of empty list elements, not so many
# that they become a denial-of-service vector.
MAX_EMPTY_ELEMENTS = 16
# other-range = 1*( %x21-2B / %x2D-7E ), i.e. visible characters except the comma.
_OTHER_CHARS = frozenset(chr(code) for code in range(0x21, 0x7F)) - {","}


@dataclass(frozen=True, slots=True, init=False)
class RangeRequest:
    """A parsed ``Range`` header: ``ranges-specifier = range-unit "=" range-set``.

    ``unit`` is stored lower-cased (range units are case-insensitive, RFC 9110 14.1).
    For the ``bytes`` unit, ``specs`` holds the range-specs in request order and
    ``other`` is empty. For any other unit, ``specs`` is empty and ``other`` keeps each
    range-spec as raw text, because only the unit's own definition gives it meaning.
    Construction checks the same rules (a token unit, at least one item, ``other``
    items made of visible characters except the comma) and raises
    :class:`MalformedRange`; lists are stored as tuples.

    >>> request = parse_range_request("Bytes=0-0, -1")
    >>> request.unit, request.is_bytes, str(request)
    ('bytes', True, 'bytes=0-0,-1')
    """

    unit: str
    specs: tuple[RangeSpec, ...] = ()
    other: tuple[str, ...] = ()

    def __init__(
        self,
        unit: str,
        specs: tuple[RangeSpec, ...] | list[RangeSpec] = (),
        other: tuple[str, ...] | list[str] = (),
    ) -> None:
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "other", other)
        self.__post_init__()

    def __post_init__(self) -> None:
        unit = plain_str(self.unit, MalformedRange, "unit")
        if not is_token(unit):
            raise MalformedRange(f"range unit {short(unit)} is not a token")
        unit = unit.lower()
        given = plain_items(self.specs, MalformedRange, "specs")
        for spec in given:
            if not issubclass(type(spec), RangeSpec):
                raise MalformedRange(f"specs must hold RangeSpec items, got {type_name(spec)}")
        # Plain copies, so a subclass cannot put its own text into the header value.
        specs = tuple(
            RangeSpec(spec.start, spec.end) for spec in cast("tuple[RangeSpec, ...]", given)
        )
        raw = plain_items(self.other, MalformedRange, "other")
        other = tuple(plain_str(item, MalformedRange, "other") for item in raw)
        for item in other:
            _check_other(item)
        if unit == UNIT and (other or not specs):
            raise MalformedRange("a bytes range request needs specs and no other items")
        if unit != UNIT and (specs or not other):
            raise MalformedRange("a range request in another unit needs other items only")
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "other", other)

    @property
    def is_bytes(self) -> bool:
        """True when the unit is ``bytes``, the only unit RFC 9110 defines.

        >>> parse_range_request("pages=1-2").is_bytes
        False
        """
        return self.unit == UNIT

    def __repr__(self) -> str:
        fields = f"unit={self.unit!r}, specs={self.specs!r}, other={self.other!r}"
        return f"{type(self).__qualname__}({fields})"

    def __str__(self) -> str:
        """The canonical header value, for example ``'bytes=0-499,-500'``."""
        items = [str(spec) for spec in self.specs] if self.is_bytes else list(self.other)
        return f"{self.unit}={','.join(items)}"


def parse_range_request(value: str, *, max_empty: int = MAX_EMPTY_ELEMENTS) -> RangeRequest:
    """Parse a ``Range`` header value with the strict RFC 9110 grammar.

    No whitespace may surround the unit or sit inside a range-spec; optional
    whitespace is allowed after ``=`` (RFC 9110 erratum 7306) and around commas, and up
    to ``max_empty`` empty list elements are ignored (RFC 9110 5.6.1.2). Byte ranges
    follow 14.1.2: ``bytes=0-499``, ``bytes=9500-``, ``bytes=-500``, ``bytes=0-0,-1``.
    An int-range whose last position precedes the first is invalid. Raises
    :class:`MalformedRange`.

    >>> parse_range_request("bytes= 0-999, 4500-5499, -1000").specs[2]
    RangeSpec(start=None, end=1000)
    >>> parse_range_request("pages=intro,3").other
    ('intro', '3')
    """
    unit, items = split_request(value, max_empty)
    if unit == UNIT:
        return RangeRequest(unit, specs=tuple(bytes_spec(item) for item in items))
    return RangeRequest(unit, other=tuple(items))


def parse_accept_ranges(value: str, *, max_empty: int = MAX_EMPTY_ELEMENTS) -> tuple[str, ...]:
    """Parse an ``Accept-Ranges`` value into lower-cased range units (RFC 9110 14.3).

    ``'none'`` is the reserved unit a server sends to advise against range requests.
    Raises :class:`MalformedRange` for a non-token or an empty list.

    >>> parse_accept_ranges("bytes")
    ('bytes',)
    >>> parse_accept_ranges("None")
    ('none',)
    """
    value = plain_str(value, MalformedRange, "value")
    units = _split_list(value.strip(OWS), count(max_empty, MalformedRange, "max_empty"))
    for unit in units:
        if not is_token(unit):
            raise MalformedRange(f"range unit {short(unit)} is not a token")
    return tuple(unit.lower() for unit in units)


def split_request(value: object, max_empty: object) -> tuple[str, list[str]]:
    """Check the unit and the list of a ``Range`` value; return the unit and the items."""
    text = plain_str(value, MalformedRange, "value").strip(OWS)
    limit = count(max_empty, MalformedRange, "max_empty")
    unit, sep, raw = text.partition("=")
    if not sep:
        raise MalformedRange(f"missing '=' in range header {short(text)}")
    if not is_token(unit):
        raise MalformedRange(f"range unit {short(unit)} is not a token")
    unit = unit.lower()
    items = _split_list(raw, limit)
    if unit != UNIT:
        for item in items:
            _check_other(item)
    return unit, items


def bytes_spec(item: str) -> RangeSpec:
    """Parse one strict ``bytes`` range-spec: no whitespace, exactly one ``-``."""
    if any(char in OWS for char in item):
        raise MalformedRange(f"whitespace inside range-spec {short(item)}")
    if item.count("-") != 1:
        raise MalformedRange(f"invalid bytes range-spec {short(item)}")
    return parse_spec(item)


def _check_other(item: str) -> None:
    if not item or not all(char in _OTHER_CHARS for char in item):
        raise MalformedRange(f"invalid range-spec {short(item)}")


def _split_list(raw: str, max_empty: int) -> list[str]:
    elements = [item.strip(OWS) for item in raw.split(",")]
    items = [item for item in elements if item]
    if len(elements) - len(items) > max_empty:
        raise MalformedRange(f"more than {describe_int(max_empty)} empty list elements")
    if not items:
        raise MalformedRange("the list holds no elements")
    return items
