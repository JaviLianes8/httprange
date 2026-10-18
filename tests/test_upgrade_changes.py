"""Every behaviour change from PyPI 0.2.0 in argument checks and value objects, asserted
on both releases (see CHANGELOG.md). Needs HTTPRANGE_V02 (the ``old`` fixture in
conftest.py); skipped otherwise.
"""

from __future__ import annotations

from datetime import datetime
from types import ModuleType
from typing import Any

import pytest
from oldnew import Change, decide, kind

import httprange as hr

CHANGES: list[Change] = [
    ("float length", lambda m: m.resolve_ranges("bytes=0-1", 5.0)[0].last, 1, "RangeError"),
    ("float total", lambda m: m.RangeSpec(0, 1).resolve(5.0), (0, 1), "RangeError"),
    ("bool total", lambda m: m.resolve("bytes=0-1", True), [(0, 0)], "RangeError"),
    ("float limit", lambda m: m.RangePolicy(max_ranges=2.5).max_ranges, 2.5, "RangeError"),
    ("str coalesce", lambda m: m.RangePolicy(coalesce="no").coalesce, "no", "RangeError"),
    (
        "bytes header",
        lambda m: m.parse_range_request(b"bytes=0-1"),
        "leak TypeError",
        "MalformedRange",
    ),
    ("bytes method", lambda m: decide(m, "bytes=0-1", method=b"GET"), 200, "RangeError"),
    (
        "naive validator",
        lambda m: decide(
            m, "bytes=0-1", if_range='"a"', etag='"a"', last_modified=datetime(2020, 1, 1)
        ),
        206,
        "RangeError",
    ),
    (
        "str strength",
        lambda m: m.if_range_matches('"a"', etag='"a"', date_is_strong="no"),
        True,
        "RangeError",
    ),
    ("unit case", lambda m: m.ContentRange("BYTES", 0, 1, 2).unit, "BYTES", "bytes"),
    ("empty request", lambda m: m.RangeRequest("bytes").unit, "bytes", "MalformedRange"),
    ("bad decision", lambda m: m.RangeDecision(999, (), -1, "x").status, 999, "RangeError"),
    (
        "short part",
        lambda m: len(m.BytePart(m.ContentRange("bytes", 0, 9, 50), b"abc").data),
        3,
        "MalformedMultipart",
    ),
    ("huge position", lambda m: m.ByteRange(0, 10**5000).first, 0, "RangeError"),
    (
        "float length text",
        lambda m: m.ByteRange(0, 1).content_range(2.5),
        "bytes 0-1/2.5",
        "RangeError",
    ),
]


@pytest.mark.parametrize(("name", "call", "before", "after"), CHANGES, ids=[c[0] for c in CHANGES])
def test_documented_change(old: ModuleType, name: str, call: Any, before: Any, after: Any) -> None:
    assert kind(call, old) == before
    assert kind(call, hr) == after


def test_the_package_no_longer_exports_annotations(old: ModuleType) -> None:
    assert hasattr(old, "annotations") and not hasattr(hr, "annotations")
