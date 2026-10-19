"""Documented constructor inputs type-check, and If-Range dates match exactly.

This module is part of the ``mypy --strict tests`` gate: each constructor call below
uses an input type its docstring documents, so a narrower annotation fails the gate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

import pytest

import httprange as hr

SPAN = hr.ContentRange("bytes", 0, 1, 10)
LEAP = "Sat, 31 Dec 2016 23:59:60 GMT"
BEFORE = "Sat, 31 Dec 2016 23:59:59 GMT"


def test_byte_part_takes_bytes_bytearray_or_memoryview() -> None:
    for data in (b"ab", bytearray(b"ab"), memoryview(b"ab")):
        part = hr.BytePart(SPAN, data, "text/plain")
        assert type(part.data) is bytes and part.data == b"ab"
    assert hr.BytePart(content_range=SPAN, data=bytearray(b"ab")).content_type is None


def test_multipart_body_takes_bytes_bytearray_or_memoryview() -> None:
    for body in (b"--b--\r\n", bytearray(b"--b--\r\n"), memoryview(b"--b--\r\n")):
        value = hr.MultipartBody("multipart/byteranges; boundary=b", body, "b")
        assert type(value.body) is bytes and value.content_length == 7


def test_range_decision_takes_a_list_of_ranges() -> None:
    decision = hr.RangeDecision(206, [hr.ByteRange(0, 0)], 10, "x")
    assert decision.ranges == (hr.ByteRange(0, 0),)
    assert hr.RangeDecision(status=200, ranges=[], length=10, reason="x").ranges == ()


def test_range_request_takes_lists() -> None:
    request = hr.RangeRequest("bytes", [hr.RangeSpec(0, 1)])
    assert request.specs == (hr.RangeSpec(0, 1),)
    assert hr.RangeRequest("items", other=["a"]).other == ("a",)
    assert hr.RangeRequest(unit="items", specs=[], other=["a", "b"]).other == ("a", "b")


def test_constructors_keep_their_field_order_and_defaults() -> None:
    assert hr.BytePart(SPAN, b"ab") == hr.BytePart(SPAN, b"ab", None)
    assert hr.RangeRequest("bytes", (hr.RangeSpec(0, 1),)) == hr.RangeRequest(
        "bytes", specs=(hr.RangeSpec(0, 1),), other=()
    )
    with pytest.raises(TypeError):
        hr.RangeDecision(206, (hr.ByteRange(0, 0),), 10)  # type: ignore[call-arg]


def test_a_leap_second_matches_only_itself() -> None:
    assert not hr.if_range_matches(BEFORE, last_modified=LEAP)
    assert not hr.if_range_matches(LEAP, last_modified=BEFORE)
    utc = datetime(2016, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert not hr.if_range_matches(LEAP, last_modified=utc)
    assert hr.if_range_matches(BEFORE, last_modified=utc)
    assert hr.if_range_matches(LEAP, last_modified=LEAP)
    assert hr.if_range_matches("Sat Dec 31 23:59:60 2016", last_modified=LEAP)


def test_a_leap_second_if_range_never_serves_a_range_for_another_second() -> None:
    def status(if_range: str, last_modified: str) -> int:
        return hr.evaluate_range_request(
            method="GET",
            range_header="bytes=0-0",
            length=10,
            if_range=if_range,
            last_modified=last_modified,
        ).status

    assert status(LEAP, BEFORE) == 200
    assert status(BEFORE, LEAP) == 200
    assert status(LEAP, LEAP) == 206


def test_legacy_resolve_refuses_every_spec_on_an_empty_representation() -> None:
    # Documented 0.1 behaviour: resolve() needs a byte to return, so even the suffix-range
    # RFC 9110 14.1.2 calls satisfiable raises; resolve_ranges() reports it as ().
    with pytest.raises(hr.UnsatisfiableRange) as info:
        hr.resolve("bytes=-5", 0)
    assert info.value.length == 0
    assert hr.resolve_ranges("bytes=-5", 0) == ()
    assert "On an empty representation" in " ".join((hr.resolve.__doc__ or "").split())


def test_range_request_stores_the_unit_lower_cased() -> None:
    assert hr.RangeRequest("Bytes", (hr.RangeSpec(0, 1),)).unit == "bytes"
    assert hr.RangeRequest("ITEMS", (), ("1",)).unit == "items"


class Lookalike(NamedTuple):
    start: int
    end: int


def test_range_request_refuses_a_spec_lookalike() -> None:
    with pytest.raises(hr.MalformedRange, match="specs must hold RangeSpec items, got Lookalike"):
        hr.RangeRequest("bytes", [Lookalike(0, 1)])  # type: ignore[list-item]


def test_a_wrong_type_error_cuts_a_huge_type_name() -> None:
    huge = type("X" * 5000, (), {})()
    with pytest.raises(hr.MalformedRange) as info:
        hr.RangeRequest("bytes", huge)
    assert str(info.value) == "specs must be a tuple or list, got " + "X" * 40
