"""Shared ASCII digit and token checks for the header grammars."""

from __future__ import annotations

DIGITS = frozenset("0123456789")
# RFC 9110 5.6.2: tchar.
TCHARS = frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
OWS = " \t"
# The most significant digits a position or length may have. Far beyond any real size,
# yet small enough that converting and printing such a number stays cheap.
MAX_DIGITS = 4000
LIMIT = 10**MAX_DIGITS
# Below the smallest limit ``sys.set_int_max_str_digits`` accepts (640), so the caller's
# limit never makes a conversion fail.
_CHUNK = 600
_CHUNK_SCALE = 10**_CHUNK


def is_digits(text: str) -> bool:
    """True when ``text`` is one or more ASCII digits (``1*DIGIT``)."""
    return bool(text) and all(char in DIGITS for char in text)


def is_token(text: str) -> bool:
    """True when ``text`` is an RFC 9110 token."""
    return bool(text) and all(char in TCHARS for char in text)


def to_int(text: str, error: type[Exception], context: str) -> int:
    """Convert ``1*DIGIT`` text to an int, raising ``error`` on anything else."""
    if not is_digits(text):
        raise error(f"invalid number in {context[:40]!r}")
    significant = text.lstrip("0")
    if len(significant) > MAX_DIGITS:
        raise error(f"number with more than {MAX_DIGITS} digits in range value")
    value = 0
    for start in range(0, len(significant), _CHUNK):
        chunk = significant[start : start + _CHUNK]
        value = value * 10 ** len(chunk) + int(chunk)
    return value


def int_text(value: int) -> str:
    """Decimal text of a non-negative ``value``, whatever the interpreter's digit limit."""
    if value < _CHUNK_SCALE:
        return str(value)
    chunks: list[str] = []
    while value >= _CHUNK_SCALE:
        value, low = divmod(value, _CHUNK_SCALE)
        chunks.append(str(low).zfill(_CHUNK))
    return str(value) + "".join(reversed(chunks))


def describe_int(value: int) -> str:
    """A short form of ``value`` for error messages: wide integers are named by size."""
    if -(10**20) < value < 10**20:
        return str(value)
    return f"<{abs(value).bit_length()}-bit {'negative ' if value < 0 else ''}integer>"
