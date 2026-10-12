"""Boundary and field-value checks for multipart/byteranges."""

from __future__ import annotations

from ._errors import MalformedMultipart
from ._numbers import OWS, is_token

# RFC 2046 bchars restricted to token characters, so the boundary never needs quoting:
# RFC 9110 14.6 notes that some implementations mishandle quoted boundaries.
_SAFE = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'+_-.")
# Every bchar RFC 2046 5.1.1 allows; a received boundary may use any of them.
_BCHARS = _SAFE | frozenset("(),/:=? ")


def check_boundary(boundary: str) -> None:
    """Reject a boundary that is empty, longer than 70 characters or needs quoting."""
    if not 1 <= len(boundary) <= 70 or not all(char in _SAFE for char in boundary):
        raise MalformedMultipart(
            "a boundary needs 1 to 70 characters from letters, digits and ' + _ - ."
        )


def check_field_value(value: str) -> None:
    """Reject a header field value that would break the part header block."""
    # RFC 9110 5.5: no control characters other than HTAB, nothing past Latin-1.
    if any(_forbidden(char) for char in value):
        raise MalformedMultipart(f"invalid header field value {value[:80]!r}")


def _forbidden(char: str) -> bool:
    code = ord(char)
    return (code < 0x20 and char != "\t") or code == 0x7F or code > 0xFF


def boundary_from_content_type(content_type: str, media_type: str) -> str:
    """Return the ``boundary`` parameter of a ``Content-Type`` naming ``media_type``."""
    kind, _, params = content_type.partition(";")
    if kind.strip(OWS).lower() != media_type:
        raise MalformedMultipart(f"expected {media_type}, got {content_type[:80]!r}")
    for name, value in _parameters(params):
        if name == "boundary":
            valid = 1 <= len(value) <= 70 and not value.endswith(" ")
            if not valid or not all(char in _BCHARS for char in value):
                raise MalformedMultipart(f"invalid multipart boundary {value[:80]!r}")
            return value
    raise MalformedMultipart("the Content-Type has no boundary parameter")


def _parameters(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    rest = text
    while True:
        rest = rest.lstrip(OWS + ";")
        if not rest:
            return found
        name, eq, rest = rest.partition("=")
        name = name.strip(OWS).lower()
        if not eq or not is_token(name):
            raise MalformedMultipart(f"invalid media type parameter {name[:80]!r}")
        if rest.startswith('"'):
            value, rest = _quoted(rest)
        else:
            value, _, rest = rest.partition(";")
            value = value.strip(OWS)
        found.append((name, value))


def _quoted(text: str) -> tuple[str, str]:
    out: list[str] = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return "".join(out), text[index + 1 :]
        out.append(char)
        index += 1
    raise MalformedMultipart("unterminated quoted string in Content-Type")
