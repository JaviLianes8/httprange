"""Resolve a whole range set against a length under a denial-of-service policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ._byterange import ByteRange
from ._errors import ExcessiveRanges, RangeError, UnsatisfiableRange, UnsupportedRangeUnit
from ._grammar import parse_range_request
from ._spec import RangeSpec


@dataclass(frozen=True, slots=True)
class RangePolicy:
    """Limits and merging rules applied by :func:`resolve_ranges`.

    - ``max_ranges``: most range-specs accepted in one header.
    - ``max_overlapping``: most ranges allowed to overlap another one; RFC 9110 14.2
      lets a server refuse "more than two overlapping ranges", hence the default 2.
    - ``coalesce``: merge ranges that overlap or touch (RFC 9110 15.3.7.2).
    - ``coalesce_gap``: also merge ranges separated by at most this many bytes; the RFC
      notes the overhead per multipart part is around 80 bytes.
    """

    max_ranges: int = 100
    max_overlapping: int = 2
    coalesce: bool = True
    coalesce_gap: int = 0

    def __post_init__(self) -> None:
        if self.max_ranges < 1:
            raise RangeError("max_ranges must be at least 1")
        if self.max_overlapping < 0 or self.coalesce_gap < 0:
            raise RangeError("max_overlapping and coalesce_gap must not be negative")


DEFAULT_POLICY = RangePolicy()


def resolve_ranges(
    ranges: str | Iterable[RangeSpec], length: int, *, policy: RangePolicy = DEFAULT_POLICY
) -> tuple[ByteRange, ...]:
    """Resolve a ``Range`` header (or its specs) against a representation ``length``.

    Unsatisfiable specs are dropped; when none is left :class:`UnsatisfiableRange` is
    raised with ``length`` attached, the case for a 416 response. Too many specs or too
    many overlapping ranges raise :class:`ExcessiveRanges`. With coalescing on, the
    result is merged and listed in the order the specs were requested, as RFC 9110
    15.3.7.2 asks for multipart responses. A header with another unit raises
    :class:`UnsupportedRangeUnit`; an invalid one raises :class:`MalformedRange`.
    """
    if length < 0:
        raise RangeError("length must not be negative")
    specs = _specs(ranges)
    if len(specs) > policy.max_ranges:
        raise ExcessiveRanges(f"{len(specs)} ranges requested, at most {policy.max_ranges}")
    resolved: list[ByteRange] = []
    for spec in specs:
        try:
            resolved.append(spec.byte_range(length))
        except UnsatisfiableRange:
            continue
    if not resolved:
        raise UnsatisfiableRange(f"no satisfiable range for length {length}", length)
    overlapping = _count_overlapping(resolved)
    if overlapping > policy.max_overlapping:
        raise ExcessiveRanges(f"{overlapping} overlapping ranges, at most {policy.max_overlapping}")
    if not policy.coalesce:
        return tuple(resolved)
    return _coalesce(resolved, policy.coalesce_gap)


def _specs(ranges: str | Iterable[RangeSpec]) -> list[RangeSpec]:
    if not isinstance(ranges, str):
        return list(ranges)
    request = parse_range_request(ranges)
    if not request.is_bytes:
        raise UnsupportedRangeUnit(f"unsupported range unit {request.unit!r}", request.unit)
    return list(request.specs)


def _count_overlapping(ranges: list[ByteRange]) -> int:
    """Count the ranges that share a byte with at least one other range."""
    order = sorted(range(len(ranges)), key=lambda i: ranges[i].first)
    marked: set[int] = set()
    reach = -1
    holder = -1
    for index in order:
        current = ranges[index]
        # Anything overlapping an earlier range overlaps the one reaching furthest.
        if current.first <= reach:
            marked.update((index, holder))
        if current.last > reach:
            reach, holder = current.last, index
    return len(marked)


def _coalesce(ranges: list[ByteRange], gap: int) -> tuple[ByteRange, ...]:
    order = sorted(range(len(ranges)), key=lambda i: ranges[i].first)
    groups: list[tuple[int, int, int]] = []  # (first, last, earliest request index)
    for index in order:
        current = ranges[index]
        if groups and current.first <= groups[-1][1] + 1 + gap:
            first, last, earliest = groups[-1]
            groups[-1] = (first, max(last, current.last), min(earliest, index))
        else:
            groups.append((current.first, current.last, index))
    groups.sort(key=lambda group: group[2])
    return tuple(ByteRange(first, last) for first, last, _ in groups)
