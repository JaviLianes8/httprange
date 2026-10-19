"""Resolve a whole range set against a length under a denial-of-service policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ._byterange import ByteRange
from ._checks import count, plain_bool, plain_int, size, type_name
from ._errors import (
    ExcessiveRanges,
    MalformedRange,
    RangeError,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
)
from ._grammar import MAX_EMPTY_ELEMENTS, bytes_spec, split_request
from ._numbers import describe_int, int_text
from ._spec import UNIT, RangeSpec


@dataclass(frozen=True, slots=True)
class RangePolicy:
    """Limits and merging rules applied by :func:`resolve_ranges`.

    - ``max_ranges``: most range-specs accepted in one header (at least 1).
    - ``max_overlapping``: most ranges allowed to cover the same byte at once; RFC 9110
      14.2 lets a server refuse "more than two overlapping ranges", hence the default 2.
      Zero refuses every range.
    - ``coalesce``: merge ranges that overlap or touch (RFC 9110 15.3.7.2).
    - ``coalesce_gap``: also merge ranges separated by at most this many bytes; the RFC
      notes the overhead per multipart part is around 80 bytes.

    The counts must be ints (not bools) and ``coalesce`` a bool, or
    :class:`RangeError` is raised.

    >>> RangePolicy(coalesce_gap=80)
    RangePolicy(max_ranges=100, max_overlapping=2, coalesce=True, coalesce_gap=80)
    """

    max_ranges: int = 100
    max_overlapping: int = 2
    coalesce: bool = True
    coalesce_gap: int = 0

    def __post_init__(self) -> None:
        max_ranges = plain_int(self.max_ranges, RangeError, "max_ranges")
        if max_ranges < 1:
            raise RangeError("max_ranges must be at least 1")
        overlapping = count(self.max_overlapping, RangeError, "max_overlapping")
        coalesce = plain_bool(self.coalesce, "coalesce")
        gap = count(self.coalesce_gap, RangeError, "coalesce_gap")
        object.__setattr__(self, "max_ranges", max_ranges)
        object.__setattr__(self, "max_overlapping", overlapping)
        object.__setattr__(self, "coalesce", coalesce)
        object.__setattr__(self, "coalesce_gap", gap)

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(max_ranges={int_text(self.max_ranges)}, "
            f"max_overlapping={int_text(self.max_overlapping)}, coalesce={self.coalesce!r}, "
            f"coalesce_gap={int_text(self.coalesce_gap)})"
        )


DEFAULT_POLICY = RangePolicy()


def resolve_ranges(
    ranges: str | Iterable[RangeSpec], length: int, *, policy: RangePolicy = DEFAULT_POLICY
) -> tuple[ByteRange, ...]:
    """Resolve a ``Range`` header (or its specs) against a representation ``length``.

    Checks run in this order: a unit other than ``bytes`` raises
    :class:`UnsupportedRangeUnit`; an invalid list, or no specs at all, raises
    :class:`MalformedRange`; more than ``policy.max_ranges`` specs raise
    :class:`ExcessiveRanges`; an invalid spec raises :class:`MalformedRange`.
    Unsatisfiable specs are dropped; when none is left :class:`UnsatisfiableRange` is
    raised with ``length`` attached, the case for a 416 response. An empty
    representation (``length == 0``) with a non-zero suffix-range is satisfiable per
    RFC 9110 14.1.2 but has no bytes to select, so the result is ``()``. More than
    ``policy.max_overlapping`` ranges covering one byte raise :class:`ExcessiveRanges`.
    With coalescing on, the result is merged and listed in the order the specs were
    requested, as RFC 9110 15.3.7.2 asks for multipart responses.

    >>> resolve_ranges("bytes=-500", 10000)
    (ByteRange(first=9500, last=9999),)
    >>> resolve_ranges("bytes=500-600,601-999", 10000)
    (ByteRange(first=500, last=999),)
    """
    length = size(length, RangeError, "length")
    if not issubclass(type(policy), RangePolicy):
        raise RangeError(f"policy must be a RangePolicy, got {type_name(policy)}")
    # Plain copies: a subclass with its own methods or properties cannot steer the result.
    policy = RangePolicy(
        policy.max_ranges, policy.max_overlapping, policy.coalesce, policy.coalesce_gap
    )
    specs = _specs(ranges, policy.max_ranges)
    if length == 0 and any(spec.is_suffix and spec.end for spec in specs):
        return ()
    resolved: list[ByteRange] = []
    for spec in specs:
        try:
            resolved.append(spec.byte_range(length))
        except UnsatisfiableRange:
            continue
    if not resolved:
        raise UnsatisfiableRange(f"no satisfiable range for length {describe_int(length)}", length)
    overlapping = _overlap_depth(resolved)
    if overlapping > policy.max_overlapping:
        raise ExcessiveRanges(
            f"{overlapping} ranges overlap at one byte, "
            f"at most {describe_int(policy.max_overlapping)}"
        )
    if not policy.coalesce:
        return tuple(resolved)
    return _coalesce(resolved, policy.coalesce_gap)


def _specs(ranges: object, max_ranges: int) -> list[RangeSpec]:
    if issubclass(type(ranges), str):
        unit, items = split_request(ranges, MAX_EMPTY_ELEMENTS)
        if unit != UNIT:
            raise UnsupportedRangeUnit(f"unsupported range unit {unit[:40]!r}", unit)
        _check_count(len(items), max_ranges)
        return [bytes_spec(item) for item in items]
    if issubclass(type(ranges), (bytes, bytearray, memoryview)) or not isinstance(ranges, Iterable):
        raise MalformedRange(f"ranges must be a str or RangeSpec items, got {type_name(ranges)}")
    specs: list[RangeSpec] = []
    for spec in ranges:
        if not issubclass(type(spec), RangeSpec):
            raise MalformedRange(f"ranges must hold RangeSpec items, got {type_name(spec)}")
        specs.append(RangeSpec(spec.start, spec.end))
        _check_count(len(specs), max_ranges)
    if not specs:
        raise MalformedRange("no range specs to resolve")
    return specs


def _check_count(found: int, max_ranges: int) -> None:
    if found > max_ranges:
        raise ExcessiveRanges(f"more than {describe_int(max_ranges)} ranges requested")


def _overlap_depth(ranges: list[ByteRange]) -> int:
    """The largest number of ranges that cover one same byte."""
    events = sorted([(item.first, 1) for item in ranges] + [(item.last + 1, -1) for item in ranges])
    depth = deepest = 0
    for _, step in events:
        depth += step
        deepest = max(deepest, depth)
    return deepest


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
