"""Parse and build HTTP Range and Content-Range headers (RFC 9110 section 14)."""

from ._byterange import ByteRange
from ._conditional import if_range_matches
from ._content_range import ContentRange, build_content_range, parse_content_range
from ._dates import format_http_date, parse_http_date
from ._decision import RangeDecision, evaluate_range_request
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
    build_multipart_byteranges,
    encode_multipart_byteranges,
    parse_multipart_byteranges,
)
from ._parts import BytePart, MultipartBody
from ._resolve import RangePolicy, resolve_ranges
from ._spec import RangeSpec, parse_range, resolve

__version__ = "1.0.0"

# The public classes show and pickle as httprange.<Name>, so a pickle never depends on
# the private module that defines them.
for _cls in (
    BytePart,
    ByteRange,
    ContentRange,
    ExcessiveRanges,
    MalformedContentRange,
    MalformedDate,
    MalformedMultipart,
    MalformedRange,
    MultipartBody,
    RangeDecision,
    RangeError,
    RangePolicy,
    RangeRequest,
    RangeSpec,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
):
    _cls.__module__ = __name__
    # Methods follow, so doctest finds their examples here (it takes properties anyway).
    for _member in vars(_cls).values():
        if callable(_member) and str(getattr(_member, "__module__", "")).startswith("httprange._"):
            _member.__module__ = __name__
del _cls, _member

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
    "RangeDecision",
    "RangeError",
    "RangePolicy",
    "RangeRequest",
    "RangeSpec",
    "UnsatisfiableRange",
    "UnsupportedRangeUnit",
    "build_content_range",
    "build_multipart_byteranges",
    "encode_multipart_byteranges",
    "evaluate_range_request",
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
