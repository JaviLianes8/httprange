"""Parse Range headers and resolve their specs against a known length."""

from __future__ import annotations

from dataclasses import dataclass

from ._errors import MalformedRange, UnsatisfiableRange

UNIT = "bytes"


@dataclass(frozen=True)
class RangeSpec:
    """A single requested range, following RFC 7233.

    ``RangeSpec(0, 499)`` asks for bytes 0 through 499, ``RangeSpec(1000, None)``
    asks from byte 1000 to the end, and ``RangeSpec(None, 500)`` asks for the final
    500 bytes (a suffix range, where ``start`` is ``None``).
    """

    start: int | None
    end: int | None

    @property
    def is_suffix(self) -> bool:
        """True when the spec selects the final ``end`` bytes of the body."""
        return self.start is None

    def resolve(self, total: int) -> tuple[int, int]:
        """Return inclusive absolute ``(start, end)`` for a body of ``total`` bytes.

        Raises :class:`UnsatisfiableRange` when the range falls outside the body.
        """
        if total < 0:
            raise ValueError("total must not be negative")
        if self.start is None:
            length = self.end or 0
            if length <= 0 or total == 0:
                raise UnsatisfiableRange(f"suffix range -{self.end} for length {total}")
            return max(0, total - length), total - 1
        if total == 0 or self.start >= total:
            raise UnsatisfiableRange(f"range {self.start}- for length {total}")
        end = total - 1 if self.end is None else min(self.end, total - 1)
        return self.start, end


def parse_range(value: str) -> list[RangeSpec]:
    """Parse a ``Range`` header value into its specs, preserving their order."""
    unit, sep, raw = value.strip().partition("=")
    if not sep or unit.strip() != UNIT or not raw.strip():
        raise MalformedRange(f"expected 'bytes=<ranges>', got {value!r}")
    specs = [_parse_spec(part.strip()) for part in raw.split(",") if part.strip()]
    if not specs:
        raise MalformedRange(f"no ranges in {value!r}")
    return specs


def resolve(header: str, total: int) -> list[tuple[int, int]]:
    """Parse ``header`` and resolve every satisfiable spec against ``total``.

    Unsatisfiable specs are dropped, as a server may serve the rest. Raises
    :class:`UnsatisfiableRange` when none can be satisfied, the RFC 7233 case for
    a 416 response.
    """
    resolved: list[tuple[int, int]] = []
    for spec in parse_range(header):
        try:
            resolved.append(spec.resolve(total))
        except UnsatisfiableRange:
            continue
    if not resolved:
        raise UnsatisfiableRange(f"no satisfiable range in {header!r} for length {total}")
    return resolved


def _parse_spec(part: str) -> RangeSpec:
    first, sep, last = part.partition("-")
    if not sep:
        raise MalformedRange(f"missing '-' in range {part!r}")
    if not first:
        return RangeSpec(None, _as_int(last, part))
    start = _as_int(first, part)
    if not last:
        return RangeSpec(start, None)
    end = _as_int(last, part)
    if end < start:
        raise MalformedRange(f"last byte {end} precedes first byte {start}")
    return RangeSpec(start, end)


def _as_int(text: str, part: str) -> int:
    if not text.isdigit():
        raise MalformedRange(f"invalid number in range {part!r}")
    return int(text)
