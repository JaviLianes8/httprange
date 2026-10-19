"""Every type check refuses lookalikes and class fakers, and checks every item it is given.

A lookalike is a different type with the right fields (a named tuple); a class faker
reports the expected class through ``__class__``. Both are refused at every entry point
that checks a type, and an item after a valid one is checked like the first.
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import httprange as hr

SpecLookalike = namedtuple("SpecLookalike", "start end")
RangeLookalike = namedtuple("RangeLookalike", "first last")
PolicyLookalike = namedtuple(
    "PolicyLookalike",
    "max_ranges max_overlapping coalesce coalesce_gap",
)


class DateLookalike:
    """Answers every question an aware datetime is asked, without being one."""

    year, month, day, hour, minute, second, microsecond = 2020, 1, 1, 0, 0, 0, 0
    tzinfo = timezone.utc

    def utcoffset(self) -> timedelta:
        return timedelta(0)

    def weekday(self) -> int:
        return 2


def _policy(bad: Any) -> Callable[[], object]:
    return lambda: hr.evaluate_range_request(
        method="GET",
        range_header=None,
        length=10,
        policy=bad,
    )


LOOKALIKES: dict[str, tuple[Callable[[], object], type[hr.RangeError], str]] = {
    "resolve_ranges item": (
        lambda: hr.resolve_ranges([SpecLookalike(0, 1)], 10),  # type: ignore[list-item]
        hr.MalformedRange,
        "ranges must hold RangeSpec items, got SpecLookalike",
    ),
    "build_multipart_byteranges item": (
        lambda: hr.build_multipart_byteranges(b"abcd", [RangeLookalike(0, 1)], boundary="b"),  # type: ignore[list-item]
        hr.RangeError,
        "ranges must hold ByteRange items, got RangeLookalike",
    ),
    "ByteRange.overlaps": (
        lambda: hr.ByteRange(0, 1).overlaps(RangeLookalike(1, 2)),  # type: ignore[arg-type]
        hr.RangeError,
        "got RangeLookalike",
    ),
    "resolve_ranges policy": (
        lambda: hr.resolve_ranges("bytes=0-0", 10, policy=PolicyLookalike(5, 5, False, 0)),  # type: ignore[arg-type]
        hr.RangeError,
        "policy must be a RangePolicy, got PolicyLookalike",
    ),
    "evaluate_range_request policy": (
        _policy(PolicyLookalike(5, 5, False, 0)),
        hr.RangeError,
        "got PolicyLookalike",
    ),
    "format_http_date": (
        lambda: hr.format_http_date(DateLookalike()),  # type: ignore[arg-type]
        hr.RangeError,
        "got DateLookalike",
    ),
}


@pytest.mark.parametrize("case", LOOKALIKES.values(), ids=list(LOOKALIKES))
def test_a_lookalike_with_the_right_fields_is_refused(case: Any) -> None:
    call, error, text = case
    with pytest.raises(error) as info:
        call()
    assert type(info.value) is error
    assert str(info.value).endswith(text)


def test_resolve_ranges_checks_every_item_not_only_the_first() -> None:
    with pytest.raises(hr.MalformedRange, match=r"RangeSpec items, got SpecLookalike$"):
        hr.resolve_ranges([hr.RangeSpec(0, 0), SpecLookalike(1, 2)], 10)  # type: ignore[list-item]


def test_build_multipart_byteranges_checks_every_item_not_only_the_first() -> None:
    with pytest.raises(hr.RangeError, match=r"ByteRange items, got str$"):
        hr.build_multipart_byteranges(b"abcd", [hr.ByteRange(0, 0), "x"], boundary="b")  # type: ignore[list-item]


def test_range_request_checks_every_other_item_not_only_the_first() -> None:
    with pytest.raises(hr.MalformedRange, match="invalid range-spec 'b c'"):
        hr.RangeRequest("items", (), ("a", "b c"))


def _faker(target: type) -> object:
    """An object whose ``__class__`` claims ``target`` and that has every field it needs."""
    fields = {
        "start": 0,
        "end": 1,
        "first": 0,
        "last": 1,
        "unit": "bytes",
        "complete_length": 5,
        "max_ranges": 5,
        "max_overlapping": 5,
        "coalesce": False,
        "coalesce_gap": 0,
        "tzinfo": timezone.utc,
        "utcoffset": lambda self: timedelta(0),
        "__class__": property(lambda self: target),
    }
    fake = type("Faker", (), fields)()
    assert isinstance(fake, target)
    return fake


FAKERS: dict[str, tuple[type, Callable[[Any], object]]] = {
    "RangeDecision ranges item": (hr.ByteRange, lambda v: hr.RangeDecision(206, [v], 10, "r")),
    "RangeRequest specs item": (hr.RangeSpec, lambda v: hr.RangeRequest("bytes", [v])),
    "BytePart content_range": (hr.ContentRange, lambda v: hr.BytePart(v, b"ab")),
    "build_multipart_byteranges item": (
        hr.ByteRange,
        lambda v: hr.build_multipart_byteranges(b"abcd", [v], boundary="b"),
    ),
    "resolve_ranges item": (hr.RangeSpec, lambda v: hr.resolve_ranges([v], 10)),
    "ByteRange.overlaps": (hr.ByteRange, lambda v: hr.ByteRange(0, 1).overlaps(v)),
    "format_http_date": (datetime, hr.format_http_date),
    "evaluate_range_request policy": (hr.RangePolicy, lambda v: _policy(v)()),
    "resolve_ranges policy": (
        hr.RangePolicy,
        lambda v: hr.resolve_ranges("bytes=0-0", 10, policy=v),
    ),
    "parse_range_request header": (str, hr.parse_range_request),
}


@pytest.mark.parametrize("case", FAKERS.values(), ids=list(FAKERS))
def test_an_object_faking_its_class_is_refused_with_the_documented_error(case: Any) -> None:
    target, call = case
    with pytest.raises(hr.RangeError) as info:
        call(_faker(target))
    assert str(info.value).endswith(", got Faker")


def test_a_class_property_that_raises_does_not_escape_a_type_error() -> None:
    class Raising:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            raise RuntimeError("boom")

    with pytest.raises(hr.MalformedRange) as info:
        hr.RangeRequest("bytes", Raising())  # type: ignore[arg-type]
    assert str(info.value) == "specs must be a tuple or list, got Raising"
