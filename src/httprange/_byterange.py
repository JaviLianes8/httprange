"""A resolved, absolute, inclusive byte range."""

from __future__ import annotations

from dataclasses import dataclass

from ._checks import bounded_int, optional_bounded_int, type_name
from ._errors import RangeError
from ._numbers import describe_int, int_text


@dataclass(frozen=True, slots=True)
class ByteRange:
    """Inclusive byte offsets ``first`` through ``last`` of a representation.

    This is what a ``bytes`` range-spec becomes once it is resolved against a known
    length (RFC 9110 14.1.2): offsets start at zero and both ends are included, so
    ``ByteRange(0, 499)`` covers 500 bytes. Both offsets must be ints (not bools) of at
    most 4000 digits with ``0 <= first <= last``, or :class:`RangeError` is raised.

    >>> span = ByteRange(0, 499)
    >>> span.length
    500
    >>> str(span)
    '0-499'
    """

    first: int
    last: int

    def __post_init__(self) -> None:
        first = bounded_int(self.first, RangeError, "first")
        last = bounded_int(self.last, RangeError, "last")
        if first < 0:
            raise RangeError(f"first byte {describe_int(first)} is negative")
        if last < first:
            raise RangeError(
                f"last byte {describe_int(last)} precedes first byte {describe_int(first)}"
            )
        object.__setattr__(self, "first", first)
        object.__setattr__(self, "last", last)

    @property
    def length(self) -> int:
        """Number of bytes covered, ``last - first + 1``.

        >>> ByteRange(500, 999).length
        500
        """
        return self.last - self.first + 1

    def as_slice(self) -> slice:
        """A ``slice`` selecting this range from a ``bytes`` object.

        >>> b"abcdef"[ByteRange(1, 3).as_slice()]
        b'bcd'
        """
        return slice(self.first, self.last + 1)

    def content_range(self, complete_length: int | None) -> str:
        """The ``Content-Range`` value for this range in a 206 response.

        Pass ``None`` when the complete length is unknown. A complete length that does
        not exceed ``last`` raises :class:`RangeError`.

        >>> ByteRange(0, 499).content_range(1234)
        'bytes 0-499/1234'
        >>> ByteRange(0, 499).content_range(None)
        'bytes 0-499/*'
        """
        total = optional_bounded_int(complete_length, RangeError, "complete_length")
        span = f"bytes {int_text(self.first)}-{int_text(self.last)}"
        if total is None:
            return f"{span}/*"
        if total <= self.last:
            raise RangeError(
                f"range ending at {describe_int(self.last)} does not fit "
                f"complete length {describe_int(total)}"
            )
        return f"{span}/{int_text(total)}"

    def overlaps(self, other: ByteRange) -> bool:
        """True when the two ranges share at least one byte.

        >>> ByteRange(0, 9).overlaps(ByteRange(9, 20))
        True
        >>> ByteRange(0, 9).overlaps(ByteRange(10, 20))
        False
        """
        if not issubclass(type(other), ByteRange):
            raise RangeError(f"other must be a ByteRange, got {type_name(other)}")
        return self.first <= other.last and other.first <= self.last

    def __str__(self) -> str:
        return f"{int_text(self.first)}-{int_text(self.last)}"
