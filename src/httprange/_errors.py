"""Errors raised when a range header cannot be parsed or satisfied."""

from __future__ import annotations


class RangeError(ValueError):
    """Base class for every error raised by this library."""


class MalformedRange(RangeError):
    """The header does not follow the RFC 7233 grammar."""


class UnsatisfiableRange(RangeError):
    """The range is well formed but cannot be satisfied for the given length."""
