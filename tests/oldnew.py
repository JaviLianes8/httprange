"""Helpers for comparing a call on the 0.2.0 release with the same call on 1.0.0."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any

Change = tuple[str, Callable[[ModuleType], Any], Any, Any]


def kind(call: Callable[[ModuleType], Any], module: ModuleType) -> Any:
    """The result of ``call(module)``, or the name of what it raised."""
    try:
        return call(module)
    except module.RangeError as error:
        return type(error).__name__
    except Exception as error:  # anything else leaked out of the library
        return "leak " + type(error).__name__


def decide(module: ModuleType, header: str, length: int = 10, **extra: Any) -> int:
    """The status ``evaluate_range_request`` gives for a GET with ``header``."""
    kwargs = {"method": "GET", "range_header": header, "length": length, **extra}
    return int(module.evaluate_range_request(**kwargs).status)
