"""Parse Range headers and resolve their specs against a known length."""

from __future__ import annotations

from dataclasses import dataclass

from ._byterange import ByteRange
from ._errors import MalformedRange, RangeError, UnsatisfiableRange
from ._numbers import to_int

UNIT = "bytes"


@dataclass(frozen=True)
class RangeSpec:
    """A single requested byte range, following RFC 9110 section 14.1.2.

    ``RangeSpec(0, 499)`` asks for bytes 0 through 499 (an int-range),
    ``RangeSpec(1000, None)`` asks from byte 1000 to the end, and
    ``RangeSpec(None, 500)`` asks for the final 500 bytes (a suffix-range, where
    ``start`` is ``None``). Construction rejects shapes the grammar cannot express.
    """

    start: int | None
    end: int | None

    def __post_init__(self) -> None:
        if self.start is None and self.end is None:
            raise MalformedRange("a range spec needs a start, an end, or both")
        if (self.start is not None and self.start < 0) or (self.end is not None and self.end < 0):
            raise MalformedRange("range positions must not be negative")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise MalformedRange(f"last byte {self.end} precedes first byte {self.start}")

    @property
    def is_suffix(self) -> bool:
        """True when the spec selects the final ``end`` bytes of the body."""
        return self.start is None

    def resolve(self, total: int) -> tuple[int, int]:
        """Return inclusive absolute ``(start, end)`` for a body of ``total`` bytes.

        An end past the body is clamped to the last byte, and a suffix longer than the
        body selects all of it (RFC 9110 14.1.2). Raises :class:`UnsatisfiableRange`
        when the range falls outside the body, including any range on an empty body.
        """
        if total < 0:
            raise RangeError("total must not be negative")
        if self.start is None:
            length = self.end or 0
            if length <= 0 or total == 0:
                raise UnsatisfiableRange(f"suffix range -{self.end} for length {total}", total)
            return max(0, total - length), total - 1
        if total == 0 or self.start >= total:
            raise UnsatisfiableRange(f"range {self.start}- for length {total}", total)
        end = total - 1 if self.end is None else min(self.end, total - 1)
        return self.start, end

    def byte_range(self, total: int) -> ByteRange:
        """Like :meth:`resolve`, but return a :class:`ByteRange`."""
        first, last = self.resolve(total)
        return ByteRange(first, last)

    def __str__(self) -> str:
        """The spec as it appears in a header: ``'0-499'``, ``'1000-'`` or ``'-500'``."""
        first = "" if self.start is None else str(self.start)
        last = "" if self.end is None else str(self.end)
        return f"{first}-{last}"


def parse_range(value: str) -> list[RangeSpec]:
    """Parse a ``bytes`` ``Range`` header value into its specs, preserving their order.

    This parser is lenient about whitespace around ``=``; use
    :func:`parse_range_request` for the strict RFC 9110 grammar and other units.
    """
    unit, sep, raw = value.strip().partition("=")
    if not sep or unit.strip().lower() != UNIT or not raw.strip():
        raise MalformedRange(f"expected 'bytes=<ranges>', got {value[:80]!r}")
    specs = [parse_spec(part.strip()) for part in raw.split(",") if part.strip()]
    if not specs:
        raise MalformedRange(f"no ranges in {value[:80]!r}")
    return specs


def resolve(header: str, total: int) -> list[tuple[int, int]]:
    """Parse ``header`` and resolve every satisfiable spec against ``total``.

    Unsatisfiable specs are dropped, as a server may serve the rest. Raises
    :class:`UnsatisfiableRange` when none can be satisfied, the RFC 9110 case for a
    416 response. See :func:`resolve_ranges` for the policy-aware version.
    """
    resolved: list[tuple[int, int]] = []
    for spec in parse_range(header):
        try:
            resolved.append(spec.resolve(total))
        except UnsatisfiableRange:
            continue
    if not resolved:
        raise UnsatisfiableRange(
            f"no satisfiable range in {header[:80]!r} for length {total}", total
        )
    return resolved


def parse_spec(part: str) -> RangeSpec:
    """Parse one ``bytes`` range-spec such as ``'0-499'``, ``'1000-'`` or ``'-500'``."""
    first, sep, last = part.partition("-")
    if not sep:
        raise MalformedRange(f"missing '-' in range {part[:80]!r}")
    if not first:
        return RangeSpec(None, to_int(last, MalformedRange, part))
    start = to_int(first, MalformedRange, part)
    if not last:
        return RangeSpec(start, None)
    return RangeSpec(start, to_int(last, MalformedRange, part))
