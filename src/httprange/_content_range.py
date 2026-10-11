"""Build Content-Range response headers per RFC 7233."""

from __future__ import annotations

from ._errors import RangeError

UNIT = "bytes"


def build_content_range(start: int | None, end: int | None, total: int | None) -> str:
    """Build a ``Content-Range`` header value.

    ``build_content_range(0, 499, 1234)`` returns ``'bytes 0-499/1234'``. Pass
    ``start`` and ``end`` as ``None`` for the unsatisfiable form ``'bytes */1234'``,
    and ``total`` as ``None`` when the length is unknown (``'bytes 0-499/*'``).
    """
    size = "*" if total is None else str(total)
    if start is None and end is None:
        if total is None:
            raise RangeError("an unsatisfiable Content-Range needs a known total")
        return f"{UNIT} */{size}"
    if start is None or end is None:
        raise RangeError("start and end must both be set for a satisfied range")
    if start < 0 or end < start:
        raise RangeError(f"invalid range {start}-{end}")
    if total is not None and end >= total:
        raise RangeError(f"range {start}-{end} exceeds total {total}")
    return f"{UNIT} {start}-{end}/{size}"
