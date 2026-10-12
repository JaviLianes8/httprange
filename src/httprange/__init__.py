"""Parse and build HTTP Range and Content-Range headers (RFC 9110 section 14)."""

from __future__ import annotations

from ._byterange import ByteRange
from ._content_range import build_content_range
from ._errors import (
    ExcessiveRanges,
    MalformedRange,
    RangeError,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
)
from ._grammar import RangeRequest, parse_accept_ranges, parse_range_request
from ._resolve import RangePolicy, resolve_ranges
from ._spec import RangeSpec, parse_range, resolve

__version__ = "0.1.0"

__all__ = [
    "ByteRange",
    "ExcessiveRanges",
    "MalformedRange",
    "RangeError",
    "RangePolicy",
    "RangeRequest",
    "RangeSpec",
    "UnsatisfiableRange",
    "UnsupportedRangeUnit",
    "build_content_range",
    "parse_accept_ranges",
    "parse_range",
    "parse_range_request",
    "resolve",
    "resolve_ranges",
]
