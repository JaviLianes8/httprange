"""Shared ASCII digit and token checks for the header grammars."""

from __future__ import annotations

DIGITS = frozenset("0123456789")
# RFC 9110 5.6.2: tchar.
TCHARS = frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
OWS = " \t"
# Well below the interpreter's default limit on decimal string conversion.
MAX_DIGITS = 4000


def is_digits(text: str) -> bool:
    """True when ``text`` is one or more ASCII digits (``1*DIGIT``)."""
    return bool(text) and all(char in DIGITS for char in text)


def is_token(text: str) -> bool:
    """True when ``text`` is an RFC 9110 token."""
    return bool(text) and all(char in TCHARS for char in text)


def to_int(text: str, error: type[Exception], context: str) -> int:
    """Convert ``1*DIGIT`` text to an int, raising ``error`` on anything else."""
    if not is_digits(text):
        raise error(f"invalid number in {context[:80]!r}")
    significant = text.lstrip("0")
    if len(significant) > MAX_DIGITS:
        raise error(f"number with more than {MAX_DIGITS} digits in range value")
    return int(significant or "0")


def check_int(value: object, error: type[Exception], name: str) -> None:
    """Raise ``error`` unless ``value`` is an int (a bool does not count)."""
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise error(f"{name} must be an int, got {type(value).__name__}")
