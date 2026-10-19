"""Huge and hostile input: the work grows linearly and messages stay short.

Each shape is timed at two sizes eight times apart; linear work grows about eight times,
quadratic work sixty-four times. The bound leaves room for a busy machine.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest

import httprange as hr

LOOSE = hr.RangePolicy(max_ranges=10**9, max_overlapping=10**9)
CT = "multipart/byteranges; boundary=x"
PART = b"--x\r\nContent-Range: bytes 0-0/1\r\n\r\nz\r\n"


def _parts(n: int) -> bytes:
    return PART * max(1, n // len(PART)) + b"--x--"


def _decide(header: str) -> object:
    return hr.evaluate_range_request(method="GET", range_header=header, length=10)


SHAPES: dict[str, tuple[Callable[[Any], object], Callable[[int], Any]]] = {
    "same spec": (
        lambda t: hr.resolve_ranges(t, 10, policy=LOOSE),
        lambda n: "bytes=" + "0-0," * (n // 4),
    ),
    "distinct specs": (
        lambda t: hr.resolve_ranges(t, 10**9, policy=LOOSE),
        lambda n: "bytes=" + ",".join(f"{2 * i}-{2 * i}" for i in range(n // 10)),
    ),
    "empty elements": (
        lambda t: hr.parse_range_request(t, max_empty=10**9),
        lambda n: "bytes=" + "," * n + "0-0",
    ),
    "leading zeros": (hr.parse_range_request, lambda n: "bytes=" + "0" * n + "1-2"),
    "long unit": (hr.parse_range_request, lambda n: "u" * n + "=1"),
    "long other range": (hr.parse_range_request, lambda n: "items=" + "a" * n),
    "content range zeros": (hr.parse_content_range, lambda n: "bytes " + "0" * n + "1-2/3"),
    "many parameters": (
        lambda t: hr.parse_multipart_byteranges(_parts(1), t),
        lambda n: "multipart/byteranges" + "; a=b" * (n // 5) + "; boundary=x",
    ),
    "long quoted parameter": (
        lambda t: hr.parse_multipart_byteranges(_parts(1), t),
        lambda n: 'multipart/byteranges; a="' + "\\x" * (n // 2) + '"; boundary=x',
    ),
    "many parts": (lambda b: hr.parse_multipart_byteranges(b, CT, max_parts=10**9), _parts),
    "long preamble": (
        lambda b: hr.parse_multipart_byteranges(b, CT),
        lambda n: b"x" * n + b"\r\n" + _parts(1),
    ),
    "many part headers": (
        lambda b: hr.parse_multipart_byteranges(b, CT),
        lambda n: b"--x\r\n" + b"A: b\r\n" * (n // 6) + PART[5:] + b"--x--",
    ),
    "long entity tag": (lambda t: hr.if_range_matches(t, etag=t), lambda n: '"' + "a" * n + '"'),
    "long date junk": (hr.parse_http_date, lambda n: "Sun, " + "9" * n),
    "decision with many specs": (_decide, lambda n: "bytes=" + "0-0," * (n // 4)),
    "boundary search": (
        lambda d: hr.build_multipart_byteranges(
            d, [hr.ByteRange(0, 0), hr.ByteRange(1, len(d) - 1)]
        ),
        lambda n: b"--" * (n // 2),
    ),
}


def _seconds(call: Callable[[Any], object], value: Any) -> float:
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        try:
            call(value)
        except hr.RangeError as error:
            assert len(str(error)) < 300
        best = min(best, time.perf_counter() - start)
    return best


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_work_grows_linearly(name: str) -> None:
    call, build = SHAPES[name]
    small, large = _seconds(call, build(25_000)), _seconds(call, build(200_000))
    assert large < 24 * small + 0.05, (name, small, large)


@pytest.mark.parametrize(
    "call",
    [
        lambda t: hr.parse_range_request(t),
        lambda t: hr.parse_range_request("bytes=" + t),
        lambda t: hr.parse_range_request("bytes=0-" + t),
        lambda t: hr.parse_range("bytes=" + t),
        lambda t: hr.resolve_ranges("items=" + t, 9),
        lambda t: hr.parse_accept_ranges(t),
        lambda t: hr.parse_content_range(t),
        lambda t: hr.parse_content_range("bytes 0-" + t),
        lambda t: hr.build_content_range(0, 0, 1, unit=t),
        lambda t: hr.ContentRange(t, 0, 0, 1),
        lambda t: hr.parse_http_date(t),
        lambda t: hr.parse_multipart_byteranges(b"", t),
        lambda t: hr.parse_multipart_byteranges(b"", CT + "; boundary=" + t),
        lambda t: hr.parse_multipart_byteranges(b"--x\r\n" + t.encode() + b"\r\n\r\n--x--", CT),
        lambda t: hr.build_multipart_byteranges(b"ab", [hr.ByteRange(0, 0)], content_type=t),
        lambda t: hr.build_multipart_byteranges(b"ab", [hr.ByteRange(0, 0)], boundary=t),
        lambda t: hr.evaluate_range_request(
            method="GET", range_header="bytes=0-0", length=1, on_excessive=t
        ),
        lambda t: hr.RangeRequest(t),
    ],
)
def test_messages_quote_at_most_forty_characters_of_input(call: Callable[[str], object]) -> None:
    for text in ("x \x00" * 100_000, "é" * 100_000, "9" * 100_000 + "-"):
        try:
            call(text)
        except hr.RangeError as error:
            assert len(str(error)) < 300
            assert text[:41] not in str(error)
