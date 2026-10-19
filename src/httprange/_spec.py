"""Parse Range headers and resolve their specs against a known length."""

from __future__ import annotations

from dataclasses import dataclass

from ._byterange import ByteRange
from ._checks import optional_bounded_int, plain_str, short, size
from ._errors import MalformedRange, RangeError, UnsatisfiableRange
from ._numbers import describe_int, int_repr, int_text, to_int

UNIT = "bytes"


@dataclass(frozen=True)
class RangeSpec:
    """A single requested byte range, following RFC 9110 section 14.1.2.

    ``RangeSpec(0, 499)`` asks for bytes 0 through 499 (an int-range),
    ``RangeSpec(1000, None)`` asks from byte 1000 to the end, and
    ``RangeSpec(None, 500)`` asks for the final 500 bytes (a suffix-range, where
    ``start`` is ``None``). Positions are ints (not bools) of at most 4000 digits.
    Construction rejects shapes the grammar cannot express with :class:`MalformedRange`.

    >>> RangeSpec(None, 500).resolve(10000)
    (9500, 9999)
    >>> str(RangeSpec(1000, None))
    '1000-'
    """

    start: int | None
    end: int | None

    def __post_init__(self) -> None:
        start = optional_bounded_int(self.start, MalformedRange, "start")
        end = optional_bounded_int(self.end, MalformedRange, "end")
        if start is None and end is None:
            raise MalformedRange("a range spec needs a start, an end, or both")
        if (start is not None and start < 0) or (end is not None and end < 0):
            raise MalformedRange("range positions must not be negative")
        if start is not None and end is not None and end < start:
            raise MalformedRange(
                f"last byte {describe_int(end)} precedes first byte {describe_int(start)}"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def is_suffix(self) -> bool:
        """True when the spec selects the final ``end`` bytes of the body.

        >>> RangeSpec(None, 1).is_suffix
        True
        """
        return self.start is None

    def resolve(self, total: int) -> tuple[int, int]:
        """Return inclusive absolute ``(start, end)`` for a body of ``total`` bytes.

        An end past the body is clamped to the last byte, and a suffix longer than the
        body selects all of it (RFC 9110 14.1.2). Raises :class:`UnsatisfiableRange`
        when the range falls outside the body. An empty body has no byte positions, so
        every spec raises here; RFC 9110 14.1.2 still calls a non-zero suffix-range
        satisfiable on it, which :func:`resolve_ranges` reports as ``()``. A negative
        or non-int ``total`` raises :class:`RangeError`.

        >>> RangeSpec(9000, 20000).resolve(10000)
        (9000, 9999)
        """
        total = size(total, RangeError, "total")
        if self.start is None:
            length = self.end or 0
            if length <= 0 or total == 0:
                raise UnsatisfiableRange(
                    f"suffix range {short(str(self))} for length {describe_int(total)}", total
                )
            return max(0, total - length), total - 1
        if self.start >= total:
            raise UnsatisfiableRange(
                f"range {short(str(self))} for length {describe_int(total)}", total
            )
        end = total - 1 if self.end is None else min(self.end, total - 1)
        return self.start, end

    def byte_range(self, total: int) -> ByteRange:
        """Like :meth:`resolve`, but return a :class:`ByteRange`.

        >>> RangeSpec(0, 0).byte_range(10)
        ByteRange(first=0, last=0)
        """
        first, last = self.resolve(total)
        return ByteRange(first, last)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}(start={int_repr(self.start)}, end={int_repr(self.end)})"

    def __str__(self) -> str:
        """The spec as it appears in a header: ``'0-499'``, ``'1000-'`` or ``'-500'``."""
        first = "" if self.start is None else int_text(self.start)
        last = "" if self.end is None else int_text(self.end)
        return f"{first}-{last}"


def parse_range(value: str) -> list[RangeSpec]:
    """Parse a ``bytes`` ``Range`` header value into its specs, preserving their order.

    This parser is lenient about whitespace around ``=`` and ignores empty list
    elements; use :func:`parse_range_request` for the strict RFC 9110 grammar and other
    units. Raises :class:`MalformedRange`.

    >>> parse_range("bytes=0-499, -500")
    [RangeSpec(start=0, end=499), RangeSpec(start=None, end=500)]
    """
    value = plain_str(value, MalformedRange, "value")
    unit, sep, raw = value.strip().partition("=")
    if not sep or unit.strip().lower() != UNIT or not raw.strip():
        raise MalformedRange(f"expected 'bytes=<ranges>', got {short(value)}")
    specs = [parse_spec(part.strip()) for part in raw.split(",") if part.strip()]
    if not specs:
        raise MalformedRange(f"no ranges in {short(value)}")
    return specs


def resolve(header: str, total: int) -> list[tuple[int, int]]:
    """Parse ``header`` and resolve every satisfiable spec against ``total``.

    Unsatisfiable specs are dropped, as a server may serve the rest. Raises
    :class:`UnsatisfiableRange` when no spec resolves to a byte. On a non-empty
    representation that is the RFC 9110 case for a 416 response. On an empty
    representation (``total == 0``) every spec raises, as in 0.1, although RFC 9110
    14.1.2 calls a non-zero suffix-range such as ``bytes=-5`` satisfiable there:
    :func:`resolve_ranges`, the policy-aware version, returns ``()`` for it.

    >>> resolve("bytes=0-0,-1,20000-", 10000)
    [(0, 0), (9999, 9999)]
    """
    specs = parse_range(header)
    total = size(total, RangeError, "total")
    resolved: list[tuple[int, int]] = []
    for spec in specs:
        try:
            resolved.append(spec.resolve(total))
        except UnsatisfiableRange:
            continue
    if not resolved:
        raise UnsatisfiableRange(f"no satisfiable range for length {describe_int(total)}", total)
    return resolved


def parse_spec(part: str) -> RangeSpec:
    """Parse one ``bytes`` range-spec such as ``'0-499'``, ``'1000-'`` or ``'-500'``."""
    first, sep, last = part.partition("-")
    if not sep:
        raise MalformedRange(f"missing '-' in range {short(part)}")
    if not first:
        return RangeSpec(None, to_int(last, MalformedRange, part))
    start = to_int(first, MalformedRange, part)
    if not last:
        return RangeSpec(start, None)
    return RangeSpec(start, to_int(last, MalformedRange, part))
