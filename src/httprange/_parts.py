"""The parts of a multipart/byteranges body and how one part is read."""

from __future__ import annotations

from dataclasses import dataclass

from ._checks import optional_str, plain_bytes, plain_str, short, type_name
from ._content_range import ContentRange, parse_content_range
from ._errors import MalformedMultipart, RangeError
from ._media import check_field_value
from ._numbers import is_token

_SINGLE = ("content-range", "content-type")


@dataclass(frozen=True, slots=True)
class BytePart:
    """One body part: its ``Content-Range``, its bytes and optional ``Content-Type``.

    The range must be satisfied (not the ``*/length`` form) and, for the ``bytes``
    unit, enclose exactly ``len(data)`` bytes. ``data`` may be given as ``bytes``,
    ``bytearray`` or ``memoryview`` and is stored as ``bytes``. ``content_type`` must be
    a valid header field value (RFC 9110 5.5). Anything else raises
    :class:`MalformedMultipart`.

    >>> part = BytePart(ContentRange("bytes", 0, 1, 10), bytearray(b"ab"), "text/plain")
    >>> part.data
    b'ab'
    """

    content_range: ContentRange
    data: bytes
    content_type: str | None = None

    def __post_init__(self) -> None:
        span = self.content_range
        if not issubclass(type(span), ContentRange):
            raise MalformedMultipart(f"content_range must be a ContentRange, got {type_name(span)}")
        data = plain_bytes(self.data, MalformedMultipart, "data")
        content_type = optional_str(self.content_type, MalformedMultipart, "content_type")
        if not span.is_satisfied:
            raise MalformedMultipart("a part needs a satisfied Content-Range")
        if span.unit == "bytes" and span.length != len(data):
            raise MalformedMultipart(
                f"part holds {len(data)} bytes, Content-Range says {short(str(span))}"
            )
        if content_type is not None:
            check_field_value(content_type)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "content_type", content_type)


@dataclass(frozen=True, slots=True)
class MultipartBody:
    """An encoded ``multipart/byteranges`` body and its ``Content-Type`` header value.

    The fields must be a str, bytes (``bytearray`` and ``memoryview`` are stored as
    ``bytes``) and a str, or :class:`MalformedMultipart` is raised.

    >>> body = MultipartBody("multipart/byteranges; boundary=b", b"--b--\\r\\n", "b")
    >>> body.content_length
    7
    """

    content_type: str
    body: bytes
    boundary: str

    def __post_init__(self) -> None:
        content_type = plain_str(self.content_type, MalformedMultipart, "content_type")
        body = plain_bytes(self.body, MalformedMultipart, "body")
        boundary = plain_str(self.boundary, MalformedMultipart, "boundary")
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "boundary", boundary)

    @property
    def content_length(self) -> int:
        """The ``Content-Length`` of the 206 response carrying this body.

        >>> MultipartBody("multipart/byteranges; boundary=b", b"", "b").content_length
        0
        """
        return len(self.body)


def parse_part(piece: bytes) -> BytePart:
    """Read one part: transport padding, header lines, a blank line, then the data."""
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
        if not colon or not is_token(name):
            raise MalformedMultipart(f"invalid part header line {short(line)}")
        key = name.lower()
        if key in _SINGLE and key in fields:
            raise MalformedMultipart(f"a part has more than one {name}")
        fields[key] = value.strip(" \t")
    if "content-range" not in fields:
        raise MalformedMultipart("a part has no Content-Range")
    try:
        span = parse_content_range(fields["content-range"])
    except RangeError as exc:
        raise MalformedMultipart(f"invalid part Content-Range: {exc}") from None
    return BytePart(span, data, fields.get("content-type"))
