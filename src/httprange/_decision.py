"""Turn a request's range headers into a 200, 206 or 416 decision (RFC 9110 14.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from ._byterange import ByteRange
from ._checks import (
    optional_str,
    plain_bool,
    plain_int,
    plain_items,
    plain_str,
    short,
    size,
    type_name,
)
from ._conditional import if_range_matches, validator_date
from ._errors import (
    ExcessiveRanges,
    MalformedRange,
    RangeError,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
)
from ._numbers import describe_int, int_text, is_token
from ._resolve import DEFAULT_POLICY, RangePolicy, resolve_ranges


@dataclass(frozen=True, slots=True, init=False)
class RangeDecision:
    """What to send back: the status code, the ranges to serve and why.

    ``status`` is 200 (send the whole representation), 206 (send ``ranges``) or 416
    (send ``Content-Range: bytes */length``). ``reason`` is a short human-readable
    explanation for logs; its wording is not part of the API. Construction checks the
    status, that only a 206 carries ranges (at least one, each inside ``length``) and
    the field types, and raises :class:`RangeError`; a list of ranges becomes a tuple.

    >>> decision = evaluate_range_request(method="GET", range_header="bytes=0-0,-1", length=10)
    >>> decision.status, decision.is_multipart, decision.content_range
    (206, True, None)
    """

    status: int
    ranges: tuple[ByteRange, ...]
    length: int
    reason: str

    def __init__(
        self,
        status: int,
        ranges: tuple[ByteRange, ...] | list[ByteRange],
        length: int,
        reason: str,
    ) -> None:
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "ranges", ranges)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "reason", reason)
        self.__post_init__()

    def __post_init__(self) -> None:
        status = plain_int(self.status, RangeError, "status")
        if status not in (200, 206, 416):
            raise RangeError(f"status must be 200, 206 or 416, got {describe_int(status)}")
        ranges = _ranges(self.ranges)
        length = size(self.length, RangeError, "length")
        reason = plain_str(self.reason, RangeError, "reason")
        if status == 206 and not ranges:
            raise RangeError("a 206 decision needs at least one range")
        if status != 206 and ranges:
            raise RangeError(f"a {status} decision carries no ranges")
        if any(item.last >= length for item in ranges):
            raise RangeError(f"a range ends past the length {describe_int(length)}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "ranges", ranges)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "reason", reason)

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(status={int_text(self.status)}, ranges={self.ranges!r}, "
            f"length={int_text(self.length)}, reason={self.reason!r})"
        )

    @property
    def is_multipart(self) -> bool:
        """True when the 206 response must use ``multipart/byteranges`` (15.3.7.2).

        >>> RangeDecision(206, (ByteRange(0, 0),), 10, "one range").is_multipart
        False
        """
        return self.status == 206 and len(self.ranges) > 1

    @property
    def content_range(self) -> str | None:
        """The response's ``Content-Range`` header, or ``None`` when it must not be sent.

        A single-part 206 gets ``bytes first-last/length``, a 416 gets
        ``bytes */length``. A 200 and a multipart 206 carry none in the header section;
        each multipart part carries its own (RFC 9110 15.3.7.2).

        >>> RangeDecision(416, (), 47022, "nothing fits").content_range
        'bytes */47022'
        """
        if self.status == 416:
            return f"bytes */{int_text(self.length)}"
        if self.status == 206 and len(self.ranges) == 1:
            return self.ranges[0].content_range(self.length)
        return None


def evaluate_range_request(
    *,
    method: str,
    range_header: str | None,
    length: int,
    if_range: str | None = None,
    etag: str | None = None,
    last_modified: datetime | str | None = None,
    date_is_strong: bool = True,
    policy: RangePolicy = DEFAULT_POLICY,
    on_excessive: Literal["reject", "ignore"] = "reject",
) -> RangeDecision:
    """Decide how an origin server answers a request for a representation of ``length``.

    Call it after the other preconditions passed (RFC 9110 14.2). The rules, in order:

    - no ``Range``, or a method other than ``GET``: 200 (14.2, MUST ignore);
    - an ``If-Range`` that does not match ``etag`` / ``last_modified``: 200 (13.1.5);
    - an empty representation: 200 (14.2 allows ignoring it);
    - a range unit other than ``bytes``: 200 (14.2, MUST ignore);
    - an invalid ``Range`` value: 200 (14.2 allows ignoring it);
    - too many or too overlapping ranges: 416, or 200 with ``on_excessive="ignore"``;
    - no satisfiable range: 416;
    - otherwise 206 with the resolved (and, per ``policy``, coalesced) ranges.

    Every argument is checked first: a wrong type, a negative ``length`` or an unknown
    ``on_excessive`` raises :class:`RangeError`, whatever the headers hold.

    >>> evaluate_range_request(method="GET", range_header="bytes=-500", length=10000)
    RangeDecision(status=206, ranges=(ByteRange(first=9500, last=9999),), length=10000, reason='1 range(s) satisfiable')
    """  # noqa: E501
    method = plain_str(method, RangeError, "method")
    header = optional_str(range_header, RangeError, "range_header")
    length = size(length, RangeError, "length")
    validator = optional_str(if_range, RangeError, "if_range")
    optional_str(etag, RangeError, "etag")
    validator_date(last_modified)
    plain_bool(date_is_strong, "date_is_strong")
    if not issubclass(type(policy), RangePolicy):
        raise RangeError(f"policy must be a RangePolicy, got {type_name(policy)}")
    choice = plain_str(on_excessive, RangeError, "on_excessive")
    if choice not in ("reject", "ignore"):
        raise RangeError(f"on_excessive must be 'reject' or 'ignore', got {short(choice)}")
    if header is None:
        return RangeDecision(200, (), length, "no Range header")
    if method != "GET":
        shown = method[:20] if is_token(method) else short(method)
        return RangeDecision(200, (), length, f"Range is ignored for {shown}")
    if validator is not None and not if_range_matches(
        validator, etag=etag, last_modified=last_modified, date_is_strong=date_is_strong
    ):
        return RangeDecision(200, (), length, "If-Range does not match")
    if length == 0:
        return RangeDecision(200, (), length, "the representation is empty")
    try:
        ranges = resolve_ranges(header, length, policy=policy)
    except UnsupportedRangeUnit as exc:
        return RangeDecision(200, (), length, f"unsupported range unit {exc.unit[:20]!r}")
    except MalformedRange as exc:
        return RangeDecision(200, (), length, f"invalid Range ignored: {exc}")
    except ExcessiveRanges as exc:
        status = 416 if choice == "reject" else 200
        return RangeDecision(status, (), length, str(exc))
    except UnsatisfiableRange as exc:
        return RangeDecision(416, (), length, str(exc))
    return RangeDecision(206, ranges, length, f"{len(ranges)} range(s) satisfiable")


def _ranges(value: object) -> tuple[ByteRange, ...]:
    items = plain_items(value, RangeError, "ranges")
    for item in items:
        if not issubclass(type(item), ByteRange):
            raise RangeError(f"ranges must hold ByteRange items, got {type_name(item)}")
    # Plain copies, so a subclass's own methods never shape the response headers.
    return tuple(ByteRange(item.first, item.last) for item in cast("tuple[ByteRange, ...]", items))
