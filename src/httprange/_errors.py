"""Errors raised when a range header cannot be parsed or satisfied."""

from __future__ import annotations


class RangeError(ValueError):
    """Base class for every error raised by this library, wrong argument types included.

    It subclasses ``ValueError``. Messages quote at most 40 characters of any input.

    >>> from httprange import resolve_ranges
    >>> try:
    ...     resolve_ranges("bytes=0-1", -1)
    ... except RangeError as error:
    ...     print(error)
    length must not be negative
    """


class MalformedRange(RangeError):
    """The ``Range`` header does not follow the RFC 9110 grammar (section 14.1.1).

    >>> from httprange import parse_range_request
    >>> parse_range_request("bytes=500-100")
    Traceback (most recent call last):
    ...
    httprange.MalformedRange: last byte 100 precedes first byte 500
    """


class UnsatisfiableRange(RangeError):
    """The range is well formed but cannot be satisfied for the given length.

    ``length`` holds the representation length when it is known, ready for the
    ``Content-Range: bytes */<length>`` field of a 416 response (RFC 9110 15.5.17).

    >>> from httprange import resolve_ranges
    >>> try:
    ...     resolve_ranges("bytes=50000-", 47022)
    ... except UnsatisfiableRange as error:
    ...     print(error.length)
    47022
    """

    def __init__(self, message: str, length: int | None = None) -> None:
        super().__init__(message, length)
        self.length = length

    def __str__(self) -> str:
        return str(self.args[0])


class UnsupportedRangeUnit(RangeError):
    """The header uses a range unit other than ``bytes``.

    An origin server MUST ignore such a header (RFC 9110 14.2). ``unit`` is the
    lower-cased unit name.

    >>> from httprange import resolve_ranges
    >>> try:
    ...     resolve_ranges("Items=0-1", 10)
    ... except UnsupportedRangeUnit as error:
    ...     print(error.unit)
    items
    """

    def __init__(self, message: str, unit: str = "") -> None:
        super().__init__(message, unit)
        self.unit = unit

    def __str__(self) -> str:
        return str(self.args[0])


class ExcessiveRanges(RangeError):
    """Too many ranges, or too many overlapping ranges (RFC 9110 14.2 and 15.5.17).

    A server MAY ignore the header or reject it with 416; this is a sign of a broken
    client or a denial-of-service attempt.

    >>> from httprange import resolve_ranges
    >>> resolve_ranges("bytes=0-0,0-0,0-0", 10)
    Traceback (most recent call last):
    ...
    httprange.ExcessiveRanges: 3 ranges overlap at one byte, at most 2
    """


class MalformedContentRange(RangeError):
    """The ``Content-Range`` value is not valid per RFC 9110 section 14.4.

    >>> from httprange import parse_content_range
    >>> parse_content_range("bytes 0-1234/1234")
    Traceback (most recent call last):
    ...
    httprange.MalformedContentRange: range 0-1234 exceeds total 1234
    """


class MalformedMultipart(RangeError):
    """A ``multipart/byteranges`` body or its boundary is not usable (RFC 9110 14.6).

    >>> from httprange import parse_multipart_byteranges
    >>> parse_multipart_byteranges(b"", "text/plain")
    Traceback (most recent call last):
    ...
    httprange.MalformedMultipart: expected multipart/byteranges, got 'text/plain'
    """


class MalformedDate(RangeError):
    """The value is not an HTTP-date in any of the three RFC 9110 5.6.7 formats.

    >>> from httprange import parse_http_date
    >>> parse_http_date("1994-11-06T08:49:37Z")
    Traceback (most recent call last):
    ...
    httprange.MalformedDate: not an HTTP-date: '1994-11-06T08:49:37Z'
    """
