"""Parse and build HTTP Range and Content-Range headers (RFC 7233)."""

from __future__ import annotations

from ._content_range import build_content_range
from ._errors import MalformedRange, RangeError, UnsatisfiableRange
from ._spec import RangeSpec, parse_range, resolve

__version__ = "0.1.0"

__all__ = [
    "MalformedRange",
    "RangeError",
    "RangeSpec",
    "UnsatisfiableRange",
    "build_content_range",
    "parse_range",
    "resolve",
]
