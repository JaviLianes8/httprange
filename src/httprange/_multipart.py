"""Build and parse multipart/byteranges bodies (RFC 9110 14.6 and 15.3.7.2)."""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from dataclasses import dataclass

from ._byterange import ByteRange
from ._content_range import ContentRange, parse_content_range
from ._errors import MalformedMultipart, RangeError
from ._media import boundary_from_content_type, check_boundary, check_field_value

MEDIA_TYPE = "multipart/byteranges"


@dataclass(frozen=True, slots=True)
class BytePart:
    """One body part: its ``Content-Range``, its bytes and optional ``Content-Type``."""

    content_range: ContentRange
    data: bytes
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class MultipartBody:
    """An encoded ``multipart/byteranges`` body and its ``Content-Type`` header value."""

    content_type: str
    body: bytes
    boundary: str

    @property
    def content_length(self) -> int:
        """The ``Content-Length`` of the 206 response carrying this body."""
        return len(self.body)


def build_multipart_byteranges(
    data: bytes,
    ranges: Iterable[ByteRange],
    *,
    content_type: str | None = None,
    boundary: str | None = None,
) -> MultipartBody:
    """Slice ``data`` by ``ranges`` and encode the parts as one 206 multipart body.

    ``content_type`` is the representation's media type, repeated in every part as
    RFC 9110 15.3.7.2 recommends. Parts keep the order of ``ranges``.
    """
    total = len(data)
    parts = []
    for item in ranges:
        if item.last >= total:
            raise RangeError(f"range {item} exceeds data of length {total}")
        span = ContentRange("bytes", item.first, item.last, total)
        parts.append(BytePart(span, bytes(data[item.as_slice()]), content_type))
    return encode_multipart_byteranges(parts, boundary=boundary)


def encode_multipart_byteranges(
    parts: Iterable[BytePart], *, boundary: str | None = None
) -> MultipartBody:
    """Encode prepared parts. A random boundary is generated when none is given.

    The boundary is checked never to occur inside a part, so the body is unambiguous.
    """
    items = list(parts)
    if not items:
        raise MalformedMultipart("a multipart/byteranges body needs at least one part")
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
            check_field_value(part.content_type)
            chunks.append(f"Content-Type: {part.content_type}\r\n".encode("latin-1"))
        chunks.append(f"Content-Range: {part.content_range}\r\n\r\n".encode("ascii"))
        chunks.append(part.data + b"\r\n")
    chunks.append(marker + b"--\r\n")
    header = f"{MEDIA_TYPE}; boundary={boundary}"
    return MultipartBody(header, b"".join(chunks), boundary)


def parse_multipart_byteranges(
    body: bytes, content_type: str, *, max_parts: int = 1000
) -> tuple[BytePart, ...]:
    """Split a 206 ``multipart/byteranges`` body into its parts.

    ``content_type`` is the response's ``Content-Type`` value, which carries the
    boundary (quoted or not). A preamble or extra CRLFs before the first boundary are
    skipped (RFC 9110 14.6 note 1). Every part needs a satisfied ``Content-Range``; for
    ``bytes`` its length must equal the part size. Raises :class:`MalformedMultipart`.
    """
    boundary = boundary_from_content_type(content_type, MEDIA_TYPE)
    pieces = (b"\r\n" + body).split(b"\r\n--" + boundary.encode("latin-1"))
    parts: list[BytePart] = []
    for piece in pieces[1:]:
        if piece.startswith(b"--"):
            if not parts:
                raise MalformedMultipart("the body holds no parts")
            return tuple(parts)
        if len(parts) >= max_parts:
            raise MalformedMultipart(f"more than {max_parts} parts")
        parts.append(_parse_part(piece))
    raise MalformedMultipart("missing closing boundary; the body is truncated")


def _parse_part(piece: bytes) -> BytePart:
    padding, crlf, rest = piece.partition(b"\r\n")
    if not crlf or padding.strip(b" \t"):
        raise MalformedMultipart("boundary line is followed by unexpected text")
    if rest.startswith(b"\r\n"):
        head, data = b"", rest[2:]
    else:
        head, blank, data = rest.partition(b"\r\n\r\n")
        if not blank:
            raise MalformedMultipart("part headers are not terminated by a blank line")
    fields: dict[str, str] = {}
    for line in head.decode("latin-1").split("\r\n") if head else []:
        name, colon, value = line.partition(":")
        if not colon or not name.strip():
            raise MalformedMultipart(f"invalid part header line {line[:80]!r}")
        fields[name.strip().lower()] = value.strip(" \t")
    if "content-range" not in fields:
        raise MalformedMultipart("a part has no Content-Range")
    try:
        span = parse_content_range(fields["content-range"])
    except RangeError as exc:
        raise MalformedMultipart(f"invalid part Content-Range: {exc}") from None
    if not span.is_satisfied:
        raise MalformedMultipart("a part carries an unsatisfied Content-Range")
    if span.unit == "bytes" and span.length != len(data):
        raise MalformedMultipart(f"part holds {len(data)} bytes, Content-Range says {span}")
    return BytePart(span, data, fields.get("content-type"))
