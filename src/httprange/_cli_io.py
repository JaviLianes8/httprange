"""Output helpers for the command line tool."""

from __future__ import annotations

import json
import os
import sys

from ._numbers import int_text

_MESSAGE = 200


def to_json(value: object) -> str:
    """``json.dumps`` for the tool's plain data, with integers of any size.

    The standard encoder refuses integers past the interpreter's digit limit
    (``sys.set_int_max_str_digits``); this writes them exactly, in the same layout.
    """
    if value is None or type(value) is bool or type(value) is str:
        return json.dumps(value)
    if type(value) is int:
        return int_text(value) if value >= 0 else "-" + int_text(-value)
    if type(value) is list:
        return "[" + ", ".join(to_json(item) for item in value) + "]"
    if type(value) is dict:
        pairs = (f"{json.dumps(key)}: {to_json(item)}" for key, item in value.items())
        return "{" + ", ".join(pairs) + "}"
    raise TypeError(f"cannot encode {type(value).__name__}")


def cut(message: str) -> str:
    """A message cut to 200 characters, so a huge argument is never echoed whole."""
    return message if len(message) <= _MESSAGE else message[:_MESSAGE] + "..."


def emit(text: str) -> bool:
    """Print ``text``; False when the reader of standard output has gone away."""
    try:
        print(text)
    except OSError:
        _silence_stdout()
        return False
    return flush_stdout()


def flush_stdout() -> bool:
    """Flush standard output; False when its reader has gone away."""
    try:
        sys.stdout.flush()
    except OSError:
        _silence_stdout()
        return False
    return True


def _silence_stdout() -> None:
    """Point standard output at the null device, so the final flush cannot fail."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        pass
