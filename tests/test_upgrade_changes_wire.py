"""Every behaviour change from PyPI 0.2.0 in multipart bodies, the order of the checks
and HTTP-dates, asserted on both releases (see CHANGELOG.md). Needs HTTPRANGE_V02 (the
``old`` fixture in conftest.py); skipped otherwise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any

import pytest
from oldnew import Change, decide, kind

import httprange as hr

UTC = timezone.utc
ONE = b"--b\r\nContent-Range: bytes 0-0/1\r\n\r\nz\r\n--b--"
TWO_UNITS = (
    b"--b\r\nContent-Range: bytes 0-0/2\r\n\r\na\r\n"
    b"--b\r\nContent-Range: items 1-1/2\r\n\r\nb\r\n--b--\r\n"
)
TWO_TYPES = (
    b"--b\r\nContent-Type: a/b\r\nContent-Type: c/d\r\nContent-Range: bytes 0-0/1\r\n\r\nz\r\n--b--"
)

CHANGES: list[Change] = [
    (
        "padded type",
        lambda m: (
            m.build_multipart_byteranges(b"ab", [m.ByteRange(0, 0)], content_type=" a/b").boundary
            != ""
        ),
        True,
        "MalformedMultipart",
    ),
    (
        "wide memoryview",
        lambda m: m.build_multipart_byteranges(
            memoryview(b"abcdefgh").cast("I"), [m.ByteRange(0, 1)], boundary="b"
        ).body[:33],
        "MalformedMultipart",
        b"--b\r\nContent-Range: bytes 0-1/8\r\n",
    ),
    (
        "mixed totals",
        lambda m: (
            m.encode_multipart_byteranges(
                [
                    m.BytePart(m.ContentRange("bytes", 0, 0, 1), b"a"),
                    m.BytePart(m.ContentRange("bytes", 0, 0, 2), b"b"),
                ]
            ).boundary
            != ""
        ),
        True,
        "MalformedMultipart",
    ),
    (
        "spaced boundary",
        lambda m: len(m.parse_multipart_byteranges(ONE, "multipart/byteranges; boundary = b")),
        1,
        "MalformedMultipart",
    ),
    (
        "two boundaries",
        lambda m: len(
            m.parse_multipart_byteranges(ONE, "multipart/byteranges; boundary=b; boundary=c")
        ),
        1,
        "MalformedMultipart",
    ),
    (
        "two part types",
        lambda m: (
            m.parse_multipart_byteranges(TWO_TYPES, "multipart/byteranges; boundary=b")[
                0
            ].content_type
        ),
        "c/d",
        "MalformedMultipart",
    ),
    (
        "two units",
        lambda m: len(m.parse_multipart_byteranges(TWO_UNITS, "multipart/byteranges; boundary=b")),
        2,
        "MalformedMultipart",
    ),
    ("long unknown unit", lambda m: decide(m, "items=" + "a," * 200), 416, 200),
    ("many empty items", lambda m: decide(m, "bytes=" + "," * 200 + "0-0"), 416, 200),
    ("many items one bad", lambda m: decide(m, "bytes=" + "0-0," * 101 + "x", 10**6), 200, 416),
    ("no specs", lambda m: m.resolve_ranges([], 10), "UnsatisfiableRange", "MalformedRange"),
    (
        "next century",
        lambda m: (
            m.parse_http_date(
                "Friday, 01-Jan-10 00:00:00 GMT", now=datetime(2090, 1, 1, tzinfo=UTC)
            ).year
        ),
        2010,
        2110,
    ),
    (
        "late clock",
        lambda m: (
            m.parse_http_date(
                "Sunday, 06-Nov-94 08:49:37 GMT", now=datetime(9990, 1, 1, tzinfo=UTC)
            ).year
        ),
        "leak ValueError",
        9994,
    ),
    (
        "year 0 in UTC",
        lambda m: m.format_http_date(datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))[:3],
        "leak OverflowError",
        "RangeError",
    ),
    (
        "fifty-year boundary day",
        lambda m: (
            m.parse_http_date(
                "Sunday, 18-Oct-76 12:00:00 GMT", now=datetime(2026, 10, 18, tzinfo=UTC)
            ).year
        ),
        2076,
        1976,
    ),
    (
        "method in reason",
        lambda m: (
            m.evaluate_range_request(method="GE T", range_header="bytes=0-1", length=5).reason
        ),
        "Range is ignored for GE T",
        "Range is ignored for 'GE T'",
    ),
]


@pytest.mark.parametrize(("name", "call", "before", "after"), CHANGES, ids=[c[0] for c in CHANGES])
def test_documented_change(old: ModuleType, name: str, call: Any, before: Any, after: Any) -> None:
    assert kind(call, old) == before
    assert kind(call, hr) == after
