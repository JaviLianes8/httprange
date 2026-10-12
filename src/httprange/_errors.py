"""Errors raised when a range header cannot be parsed or satisfied."""

from __future__ import annotations


class RangeError(ValueError):
    """Base class for every error raised by this library."""


class MalformedRange(RangeError):
    """The ``Range`` header does not follow the RFC 9110 grammar (section 14.1.1)."""


class UnsatisfiableRange(RangeError):
    """The range is well formed but cannot be satisfied for the given length.

    ``length`` holds the representation length when it is known, ready for the
    ``Content-Range: bytes */<length>`` field of a 416 response (RFC 9110 15.5.17).
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
    """


class MalformedContentRange(RangeError):
    """The ``Content-Range`` value is not valid per RFC 9110 section 14.4."""


class MalformedMultipart(RangeError):
    """A ``multipart/byteranges`` body or its boundary is not usable (RFC 9110 14.6)."""


class MalformedDate(RangeError):
    """The value is not an HTTP-date in any of the three RFC 9110 5.6.7 formats."""
