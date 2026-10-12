"""A resolved, absolute, inclusive byte range."""

from __future__ import annotations

from dataclasses import dataclass

from ._errors import RangeError
from ._numbers import check_int


@dataclass(frozen=True, slots=True)
class ByteRange:
    """Inclusive byte offsets ``first`` through ``last`` of a representation.

    This is what a ``bytes`` range-spec becomes once it is resolved against a known
    length (RFC 9110 14.1.2): offsets start at zero and both ends are included, so
    ``ByteRange(0, 499)`` covers 500 bytes.
    """

    first: int
    last: int

    def __post_init__(self) -> None:
        check_int(self.first, RangeError, "first")
        check_int(self.last, RangeError, "last")
        if self.first < 0:
            raise RangeError(f"first byte {self.first} is negative")
        if self.last < self.first:
            raise RangeError(f"last byte {self.last} precedes first byte {self.first}")

    @property
    def length(self) -> int:
        """Number of bytes covered, ``last - first + 1``."""
        return self.last - self.first + 1

    def as_slice(self) -> slice:
        """A ``slice`` selecting this range from a ``bytes`` object: ``data[r.as_slice()]``."""
        return slice(self.first, self.last + 1)

    def content_range(self, complete_length: int | None) -> str:
        """The ``Content-Range`` value for this range in a 206 response.

        ``ByteRange(0, 499).content_range(1234)`` is ``'bytes 0-499/1234'``; pass
        ``None`` when the complete length is unknown (``'bytes 0-499/*'``).
        """
        if complete_length is None:
            return f"bytes {self.first}-{self.last}/*"
        if complete_length <= self.last:
            raise RangeError(f"range {self} exceeds complete length {complete_length}")
        return f"bytes {self.first}-{self.last}/{complete_length}"

    def overlaps(self, other: ByteRange) -> bool:
        """True when the two ranges share at least one byte."""
        return self.first <= other.last and other.first <= self.last

    def __str__(self) -> str:
        return f"{self.first}-{self.last}"
