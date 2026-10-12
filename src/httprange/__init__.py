"""Parse and build HTTP Range and Content-Range headers (RFC 9110 section 14)."""

from __future__ import annotations

from ._byterange import ByteRange
from ._conditional import format_http_date, if_range_matches, parse_http_date
from ._content_range import ContentRange, build_content_range, parse_content_range
from ._errors import (
    ExcessiveRanges,
    MalformedContentRange,
    MalformedDate,
    MalformedMultipart,
    MalformedRange,
    RangeError,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
)
from ._grammar import RangeRequest, parse_accept_ranges, parse_range_request
from ._multipart import (
    BytePart,
    MultipartBody,
    build_multipart_byteranges,
    encode_multipart_byteranges,
    parse_multipart_byteranges,
)
from ._resolve import RangePolicy, resolve_ranges
from ._spec import RangeSpec, parse_range, resolve

__version__ = "0.1.0"

__all__ = [
    "BytePart",
    "ByteRange",
    "ContentRange",
    "ExcessiveRanges",
    "MalformedContentRange",
    "MalformedDate",
    "MalformedMultipart",
    "MalformedRange",
    "MultipartBody",
    "RangeError",
    "RangePolicy",
    "RangeRequest",
    "RangeSpec",
    "UnsatisfiableRange",
    "UnsupportedRangeUnit",
    "build_content_range",
    "build_multipart_byteranges",
    "encode_multipart_byteranges",
    "format_http_date",
    "if_range_matches",
    "parse_accept_ranges",
    "parse_content_range",
    "parse_http_date",
    "parse_multipart_byteranges",
    "parse_range",
    "parse_range_request",
    "resolve",
    "resolve_ranges",
]
