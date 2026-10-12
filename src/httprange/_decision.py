"""Turn a request's range headers into a 200, 206 or 416 decision (RFC 9110 14.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ._byterange import ByteRange
from ._conditional import if_range_matches
from ._errors import (
    ExcessiveRanges,
    MalformedRange,
    RangeError,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
)
from ._resolve import DEFAULT_POLICY, RangePolicy, resolve_ranges


@dataclass(frozen=True, slots=True)
class RangeDecision:
    """What to send back: the status code, the ranges to serve and why.

    ``status`` is 200 (send the whole representation), 206 (send ``ranges``) or 416
    (send ``Content-Range: bytes */length``). ``reason`` is a short human-readable
    explanation, useful in logs.
    """

    status: int
    ranges: tuple[ByteRange, ...]
    length: int
    reason: str

    @property
    def is_multipart(self) -> bool:
        """True when the 206 response must use ``multipart/byteranges`` (15.3.7.2)."""
        return self.status == 206 and len(self.ranges) > 1

    @property
    def content_range(self) -> str | None:
        """The response's ``Content-Range`` header, or ``None`` when it must not be sent.

        A single-part 206 gets ``bytes first-last/length``, a 416 gets
        ``bytes */length``. A 200 and a multipart 206 carry none in the header section;
        each multipart part carries its own (RFC 9110 15.3.7.2).
        """
        if self.status == 416:
            return f"bytes */{self.length}"
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
    - an invalid ``Range`` value: 200 (14.2 allows ignoring it);
    - a range unit other than ``bytes``: 200 (14.2, MUST ignore);
    - an empty representation: 200 (14.2 allows ignoring it);
    - too many or too overlapping ranges: 416, or 200 with ``on_excessive="ignore"``;
    - no satisfiable range: 416;
    - otherwise 206 with the resolved (and, per ``policy``, coalesced) ranges.
    """
    if length < 0:
        raise RangeError("length must not be negative")
    if range_header is None:
        return RangeDecision(200, (), length, "no Range header")
    if method != "GET":
        return RangeDecision(200, (), length, f"Range is ignored for {method[:20]}")
    if if_range is not None and not if_range_matches(
        if_range, etag=etag, last_modified=last_modified, date_is_strong=date_is_strong
    ):
        return RangeDecision(200, (), length, "If-Range does not match")
    if length == 0:
        return RangeDecision(200, (), length, "the representation is empty")
    try:
        ranges = resolve_ranges(range_header, length, policy=policy)
    except UnsupportedRangeUnit as exc:
        return RangeDecision(200, (), length, f"unsupported range unit {exc.unit[:20]!r}")
    except MalformedRange as exc:
        return RangeDecision(200, (), length, f"invalid Range ignored: {exc}")
    except ExcessiveRanges as exc:
        status = 416 if on_excessive == "reject" else 200
        return RangeDecision(status, (), length, str(exc))
    except UnsatisfiableRange as exc:
        return RangeDecision(416, (), length, str(exc))
    return RangeDecision(206, ranges, length, f"{len(ranges)} range(s) satisfiable")
