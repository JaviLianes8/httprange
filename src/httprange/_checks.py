"""Argument checks shared by the public functions and classes.

Every check looks at the real type (``type(value)``), so an object faking ``__class__``
is refused, and returns a plain ``int``, ``str``, ``bool`` or ``bytes``, so a subclass
with its own methods cannot steer a result.
"""

from __future__ import annotations

from typing import NoReturn, cast

from ._errors import RangeError
from ._numbers import LIMIT, MAX_DIGITS


def type_name(value: object) -> str:
    """The name of ``value``'s type, cut to 40 characters for error messages."""
    return type(value).__name__[:40]


def short(text: str) -> str:
    """``repr`` of the first 40 characters of ``text``, for error messages."""
    return repr(text[:40]) + ("..." if len(text) > 40 else "")


def _wrong(error: type[RangeError], name: str, kind: str, value: object) -> NoReturn:
    raise error(f"{name} must be {kind}, got {type_name(value)}")


def plain_int(value: object, error: type[RangeError], name: str) -> int:
    """Return ``value`` as a plain int; a bool, a float or anything else raises ``error``."""
    kind = type(value)
    if not issubclass(kind, int) or issubclass(kind, bool):
        _wrong(error, name, "an int", value)
    return int.__index__(cast(int, value))


def bounded_int(value: object, error: type[RangeError], name: str) -> int:
    """A plain int of at most ``MAX_DIGITS`` digits, the limit the parsers apply too."""
    number = plain_int(value, error, name)
    if not -LIMIT < number < LIMIT:
        raise error(f"{name} has more than {MAX_DIGITS} digits")
    return number


def optional_bounded_int(value: object, error: type[RangeError], name: str) -> int | None:
    """Like :func:`bounded_int`, but ``None`` passes through."""
    return None if value is None else bounded_int(value, error, name)


def size(value: object, error: type[RangeError], name: str) -> int:
    """A length or total: a bounded int that is zero or more."""
    number = bounded_int(value, error, name)
    if number < 0:
        raise error(f"{name} must not be negative")
    return number


def count(value: object, error: type[RangeError], name: str) -> int:
    """A limit such as a number of parts: any plain int that is zero or more."""
    number = plain_int(value, error, name)
    if number < 0:
        raise error(f"{name} must not be negative")
    return number


def plain_str(value: object, error: type[RangeError], name: str) -> str:
    """Return ``value`` as a plain str, or raise ``error`` for any other type."""
    if not issubclass(type(value), str):
        _wrong(error, name, "a str", value)
    return str.__str__(cast(str, value))


def optional_str(value: object, error: type[RangeError], name: str) -> str | None:
    """Like :func:`plain_str`, but ``None`` passes through."""
    return None if value is None else plain_str(value, error, name)


def plain_items(value: object, error: type[RangeError], name: str) -> tuple[object, ...]:
    """The items of a tuple or list, read without calling an overridden ``__iter__``."""
    if issubclass(type(value), tuple):
        return tuple.__getitem__(cast("tuple[object, ...]", value), slice(None))
    if issubclass(type(value), list):
        return tuple(list.__getitem__(cast("list[object]", value), slice(None)))
    _wrong(error, name, "a tuple", value)


def plain_bool(value: object, name: str) -> bool:
    """Return ``value`` if it is a real bool; ``1``, ``"no"`` and the like raise."""
    if type(value) is not bool:
        _wrong(RangeError, name, "a bool", value)
    return value is True


def plain_bytes(value: object, error: type[RangeError], name: str) -> bytes:
    """Return ``bytes``, ``bytearray`` or ``memoryview`` content as plain bytes.

    A ``memoryview`` is read as its raw bytes, whatever its item format.
    """
    kind = type(value)
    if kind is bytes:
        return cast(bytes, value)
    if issubclass(kind, bytes):
        return bytes.__getitem__(cast(bytes, value), slice(None))
    if issubclass(kind, bytearray):
        return bytes(bytearray.__getitem__(cast(bytearray, value), slice(None)))
    if issubclass(kind, memoryview):
        try:
            return cast(memoryview, value).tobytes()
        except ValueError:
            raise error(f"{name} is a released memoryview") from None
    _wrong(error, name, "bytes", value)
