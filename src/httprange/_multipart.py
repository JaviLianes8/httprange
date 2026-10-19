"""Build and parse multipart/byteranges bodies (RFC 9110 14.6 and 15.3.7.2)."""

from __future__ import annotations

import secrets
from collections.abc import Iterable, Sequence
from typing import TypeVar, cast

from ._byterange import ByteRange
from ._checks import count, optional_str, plain_bytes, plain_str, short, type_name
from ._content_range import ContentRange
from ._errors import MalformedMultipart, RangeError
from ._media import boundary_from_content_type, check_boundary
from ._numbers import describe_int
from ._parts import BytePart, MultipartBody, parse_part

MEDIA_TYPE = "multipart/byteranges"
_T = TypeVar("_T")


def build_multipart_byteranges(
    data: bytes | bytearray | memoryview,
    ranges: Iterable[ByteRange],
    *,
    content_type: str | None = None,
    boundary: str | None = None,
) -> MultipartBody:
    """Slice ``data`` by ``ranges`` and encode the parts as one 206 multipart body.

    ``content_type`` is the representation's media type, repeated in every part as
    RFC 9110 15.3.7.2 recommends. Parts keep the order of ``ranges``. Only answer
    with multipart when several ranges were requested: a server MUST NOT send it for a
    single-range request (15.3.7.2). ``data`` may be ``bytes``, ``bytearray`` or
    ``memoryview``. A range past the end of ``data`` raises :class:`RangeError`; a bad
    boundary or field value raises :class:`MalformedMultipart`.

    >>> body = build_multipart_byteranges(b"0123456789", [ByteRange(0, 1), ByteRange(8, 9)],
    ...                                   boundary="SEP")
    >>> body.content_type
    'multipart/byteranges; boundary=SEP'
    >>> body.body.split(b"\\r\\n")[:5]
    [b'--SEP', b'Content-Range: bytes 0-1/10', b'', b'01', b'--SEP']
    """
    data = plain_bytes(data, RangeError, "data")
    content_type = optional_str(content_type, MalformedMultipart, "content_type")
    total = len(data)
    parts = []
    for item in _items_of(ranges, ByteRange, RangeError, "ranges"):
        if item.last >= total:
            raise RangeError(f"range {short(str(item))} exceeds data of length {total}")
        span = ContentRange("bytes", item.first, item.last, total)
        parts.append(BytePart(span, data[item.as_slice()], content_type))
    return encode_multipart_byteranges(parts, boundary=boundary)


def encode_multipart_byteranges(
    parts: Iterable[BytePart], *, boundary: str | None = None
) -> MultipartBody:
    """Encode prepared parts. A random boundary is generated when none is given.

    The boundary is checked never to occur inside a part, so the body is unambiguous.
    Raises :class:`MalformedMultipart` for no parts, parts that disagree on the range
    unit or the complete length, or a bad or colliding boundary.

    >>> part = BytePart(ContentRange("bytes", 2, 3, 4), b"cd")
    >>> encode_multipart_byteranges([part], boundary="b").body
    b'--b\\r\\nContent-Range: bytes 2-3/4\\r\\n\\r\\ncd\\r\\n--b--\\r\\n'
    """
    boundary = optional_str(boundary, MalformedMultipart, "boundary")
    items = _items_of(parts, BytePart, MalformedMultipart, "parts")
    check_parts(items)
    if boundary is None:
        boundary = secrets.token_hex(16)
        while any(b"--" + boundary.encode("ascii") in part.data for part in items):
            boundary = secrets.token_hex(16)
    else:
        check_boundary(boundary)
    marker = b"--" + boundary.encode("ascii")
    chunks: list[bytes] = []
    for part in items:
        if marker in part.data:
            raise MalformedMultipart("the boundary occurs inside a part")
        chunks.append(marker + b"\r\n")
        if part.content_type is not None:
            chunks.append(f"Content-Type: {part.content_type}\r\n".encode("latin-1"))
        chunks.append(f"Content-Range: {part.content_range}\r\n\r\n".encode("ascii"))
        chunks.append(part.data + b"\r\n")
    chunks.append(marker + b"--\r\n")
    header = f"{MEDIA_TYPE}; boundary={boundary}"
    return MultipartBody(header, b"".join(chunks), boundary)


def parse_multipart_byteranges(
    body: bytes | bytearray | memoryview, content_type: str, *, max_parts: int = 1000
) -> tuple[BytePart, ...]:
    """Split a 206 ``multipart/byteranges`` body into its parts.

    ``content_type`` is the response's ``Content-Type`` value, which carries the
    boundary (quoted or not) and must follow the RFC 9110 5.6.6 parameter grammar. A
    preamble or extra CRLFs before the first boundary are skipped (RFC 9110 14.6 note
    1). Every part needs a satisfied ``Content-Range``; for ``bytes`` its length must
    equal the part size, and all parts must agree on the unit and the complete length.
    Positions must be integers, as the RFC 9110 14.4 grammar requires. More than
    ``max_parts`` parts, or anything else wrong, raise :class:`MalformedMultipart`.

    >>> body = b"--b\\r\\nContent-Range: bytes 2-3/4\\r\\n\\r\\ncd\\r\\n--b--\\r\\n"
    >>> (part,) = parse_multipart_byteranges(body, 'multipart/byteranges; boundary="b"')
    >>> str(part.content_range), part.data
    ('bytes 2-3/4', b'cd')
    """
    body = plain_bytes(body, MalformedMultipart, "body")
    content_type = plain_str(content_type, MalformedMultipart, "content_type")
    limit = count(max_parts, MalformedMultipart, "max_parts")
    boundary = boundary_from_content_type(content_type, MEDIA_TYPE)
    pieces = (b"\r\n" + body).split(b"\r\n--" + boundary.encode("latin-1"))
    parts: list[BytePart] = []
    for piece in pieces[1:]:
        if piece.startswith(b"--"):
            check_parts(parts)
            return tuple(parts)
        if len(parts) >= limit:
            raise MalformedMultipart(f"more than {describe_int(limit)} parts")
        parts.append(parse_part(piece))
    raise MalformedMultipart("missing closing boundary; the body is truncated")


def check_parts(parts: Sequence[BytePart]) -> None:
    """Parts of one representation: at least one, one unit and one complete length."""
    if not parts:
        raise MalformedMultipart("a multipart/byteranges body needs at least one part")
    if len({part.content_range.unit for part in parts}) > 1:
        raise MalformedMultipart("parts disagree on the range unit")
    if len({part.content_range.complete_length for part in parts}) > 1:
        raise MalformedMultipart("parts disagree on the complete length")


def _items_of(items: object, kind: type[_T], error: type[RangeError], name: str) -> list[_T]:
    """The items of an iterable, each of type ``kind``; text and bytes raise ``error``."""
    if issubclass(type(items), (str, bytes, bytearray, memoryview)) or not isinstance(
        items, Iterable
    ):
        raise error(f"{name} must be an iterable of {kind.__name__}, got {type_name(items)}")
    found: list[_T] = []
    for item in items:
        if not issubclass(type(item), kind):
            raise error(f"{name} must hold {kind.__name__} items, got {type_name(item)}")
        found.append(cast(_T, item))
    return found
