"""Every item a constructor or entry point takes is type-checked, and errors name it briefly.

Lookalike objects with the right fields are refused, items after a valid one are
checked too, and a type with a huge name never reaches an error message uncut.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import pytest

import httprange as hr

HUGE = type("X" * 5000, (), {})


class SpecLookalike(NamedTuple):
    start: int
    end: int


class ByteRangeLookalike(NamedTuple):
    first: int
    last: int


class ContentRangeLookalike(NamedTuple):
    unit: str
    first: int
    last: int
    complete_length: int


class Text(str):
    def upper(self) -> str:
        return "steered"


def test_range_decision_refuses_a_byte_range_lookalike() -> None:
    with pytest.raises(hr.RangeError, match="ranges must hold ByteRange items, got Byte"):
        hr.RangeDecision(206, [ByteRangeLookalike(0, 1)], 10, "r")  # type: ignore[list-item]


def test_byte_part_refuses_a_content_range_lookalike() -> None:
    span = ContentRangeLookalike("bytes", 0, 1, 5)
    with pytest.raises(hr.MalformedMultipart, match="content_range must be a ContentRange"):
        hr.BytePart(span, b"ab")  # type: ignore[arg-type]


def test_range_request_checks_every_spec_not_only_the_first() -> None:
    with pytest.raises(hr.MalformedRange, match="specs must hold RangeSpec items, got Spec"):
        hr.RangeRequest("bytes", [hr.RangeSpec(0, 1), SpecLookalike(2, 3)])  # type: ignore[list-item]


def test_range_decision_checks_every_range_not_only_the_first() -> None:
    ranges = [hr.ByteRange(0, 0), ByteRangeLookalike(2, 3)]
    with pytest.raises(hr.RangeError, match="ranges must hold ByteRange items, got Byte"):
        hr.RangeDecision(206, ranges, 10, "r")  # type: ignore[arg-type]


def test_range_request_refuses_a_non_str_other_item() -> None:
    with pytest.raises(hr.MalformedRange, match="other must be a str, got int"):
        hr.RangeRequest("items", (), ("a", 5))  # type: ignore[arg-type]


def test_range_request_stores_other_items_as_plain_str() -> None:
    request = hr.RangeRequest("items", (), (Text("1"), "2"))
    assert [type(item) for item in request.other] == [str, str]
    assert request.other == ("1", "2")


ENTRY_POINTS: dict[str, Callable[[Any], object]] = {
    "RangeRequest specs item": lambda bad: hr.RangeRequest("bytes", [bad]),
    "RangeDecision ranges item": lambda bad: hr.RangeDecision(206, [bad], 10, "r"),
    "BytePart content_range": lambda bad: hr.BytePart(bad, b"ab"),
    "build_multipart_byteranges ranges": lambda bad: hr.build_multipart_byteranges(
        b"ab",
        bad,
        boundary="b",
    ),
    "build_multipart_byteranges ranges item": lambda bad: hr.build_multipart_byteranges(
        b"ab",
        [bad],
        boundary="b",
    ),
    "resolve_ranges ranges": lambda bad: hr.resolve_ranges(bad, 10),
    "resolve_ranges ranges item": lambda bad: hr.resolve_ranges([bad], 10),
    "resolve_ranges policy": lambda bad: hr.resolve_ranges("bytes=0-0", 10, policy=bad),
    "evaluate_range_request policy": lambda bad: hr.evaluate_range_request(
        method="GET",
        range_header="bytes=0-0",
        length=10,
        policy=bad,
    ),
    "format_http_date": lambda bad: hr.format_http_date(bad),
    "ByteRange.overlaps": lambda bad: hr.ByteRange(0, 1).overlaps(bad),
}


@pytest.mark.parametrize("call", ENTRY_POINTS.values(), ids=list(ENTRY_POINTS))
def test_every_type_error_cuts_a_huge_type_name(call: Callable[[Any], object]) -> None:
    with pytest.raises(hr.RangeError) as info:
        call(HUGE())
    message = str(info.value)
    assert message.endswith(", got " + "X" * 40)
    assert "X" * 41 not in message


def test_a_type_error_names_the_class_not_its_qualified_name() -> None:
    def make() -> Any:
        class Bad:
            pass

        return Bad()

    with pytest.raises(hr.MalformedRange) as info:
        hr.RangeRequest("bytes", make())
    assert str(info.value) == "specs must be a tuple or list, got Bad"
    with pytest.raises(hr.RangeError) as info2:
        hr.format_http_date(make())
    assert str(info2.value).endswith(", got Bad")
