"""Boundary, field-value and Content-Type checks for multipart/byteranges."""

from __future__ import annotations

from ._checks import short
from ._errors import MalformedMultipart
from ._numbers import OWS, TCHARS, is_token

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
    """Reject a header field value that RFC 9110 5.5 does not allow.

    Visible ASCII and obs-text, with spaces and tabs only between visible characters.
    """
    if value != value.strip(OWS) or any(_forbidden(char) for char in value):
        raise MalformedMultipart(f"invalid header field value {short(value)}")


def _forbidden(char: str) -> bool:
    code = ord(char)
    return (code < 0x20 and char != "\t") or code == 0x7F or code > 0xFF


def boundary_from_content_type(content_type: str, media_type: str) -> str:
    """Return the ``boundary`` parameter of a ``Content-Type`` naming ``media_type``."""
    kind, _, _ = content_type.partition(";")
    if kind.strip(OWS).lower() != media_type:
        raise MalformedMultipart(f"expected {media_type}, got {short(content_type)}")
    found = [value for name, value in _parameters(content_type, len(kind)) if name == "boundary"]
    if not found:
        raise MalformedMultipart("the Content-Type has no boundary parameter")
    if len(found) > 1:
        raise MalformedMultipart("the Content-Type has more than one boundary parameter")
    value = found[0]
    if not 1 <= len(value) <= 70 or value.endswith(" ") or not all(c in _BCHARS for c in value):
        raise MalformedMultipart(f"invalid multipart boundary {short(value)}")
    return value


def _parameters(text: str, index: int) -> list[tuple[str, str]]:
    """Read ``*( OWS ";" OWS [ parameter ] )`` (RFC 9110 5.6.6) from ``index`` on."""
    found: list[tuple[str, str]] = []
    size = len(text)
    while (index := _skip(text, index, OWS)) < size:
        if text[index] != ";":
            raise MalformedMultipart(f"expected ';' in Content-Type at {short(text[index:])}")
        index = _skip(text, index + 1, OWS)
        if index == size or text[index] == ";":
            continue
        equals = _skip(text, index, TCHARS)
        name = text[index:equals]
        if not name or not text.startswith("=", equals):
            raise MalformedMultipart(f"invalid media type parameter {short(text[index:])}")
        if text.startswith('"', equals + 1):
            value, index = _quoted(text, equals + 1)
        else:
            index = _skip(text, equals + 1, TCHARS)
            value = text[equals + 1 : index]
            if not is_token(value):
                raise MalformedMultipart(f"invalid value for parameter {short(name)}")
        found.append((name.lower(), value))
    return found


def _skip(text: str, index: int, chars: str | frozenset[str]) -> int:
    while index < len(text) and text[index] in chars:
        index += 1
    return index


def _quoted(text: str, start: int) -> tuple[str, int]:
    """Read the quoted-string opening at ``start``; return its value and the next index."""
    out: list[str] = []
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and not _forbidden(text[index + 1]):
            out.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return "".join(out), index + 1
        if char == "\\" or _forbidden(char):
            break
        out.append(char)
        index += 1
    raise MalformedMultipart("invalid quoted string in Content-Type")
