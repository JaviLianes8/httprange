"""Pins for promises that only a wrong implementation would break: the range cap on an
iterable, every argument checked up front, every field rule of the value classes, str
subclasses and int class fakers, and short messages for huge numbers."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import pytest

import httprange as hr

UTC = timezone.utc


def test_resolve_ranges_caps_an_iterable_of_specs_while_reading_it() -> None:
    specs = [hr.RangeSpec(2 * i, 2 * i) for i in range(101)]
    with pytest.raises(hr.ExcessiveRanges, match="more than 100 ranges"):
        hr.resolve_ranges(specs, 1000)
    assert len(hr.resolve_ranges(specs[:100], 1000)) == 100
    read: list[int] = []

    def endless() -> Iterator[hr.RangeSpec]:
        for i in itertools.count():
            read.append(i)
            yield hr.RangeSpec(2 * i, 2 * i)

    with pytest.raises(hr.ExcessiveRanges):
        hr.resolve_ranges(endless(), 1000, policy=hr.RangePolicy(max_ranges=3))
    assert len(read) == 4


def decide(**extra: Any) -> hr.RangeDecision:
    kwargs: dict[str, Any] = {"method": "GET", "range_header": None, "length": 10, **extra}
    return hr.evaluate_range_request(**kwargs)


@pytest.mark.parametrize("header", [None, "bytes=0-1", "items=1", "bytes=x"])
@pytest.mark.parametrize(
    "bad",
    [
        {"last_modified": datetime(2020, 1, 1)},
        {"last_modified": 5},
        {"last_modified": b"Sun, 06 Nov 1994 08:49:37 GMT"},
        {"etag": 5},
        {"etag": b'"v1"'},
    ],
)
def test_validators_are_checked_whatever_the_headers_hold(
    header: str | None, bad: dict[str, Any]
) -> None:
    with pytest.raises(hr.RangeError):
        decide(range_header=header, **bad)
    with pytest.raises(hr.RangeError):
        decide(range_header=header, method="HEAD", **bad)


@pytest.mark.parametrize("choice", ["", "Reject", "IGNORE", " reject", "reject ", "rejec", "none"])
def test_on_excessive_refuses_every_value_but_reject_and_ignore(choice: str) -> None:
    for header in (None, "bytes=0-0"):
        with pytest.raises(hr.RangeError, match="on_excessive must be 'reject' or 'ignore'"):
            decide(range_header=header, on_excessive=choice)
    assert decide(range_header="bytes=0-0", on_excessive="ignore").status == 206
    assert decide(range_header="bytes=0-0", on_excessive="reject").status == 206


def test_a_decision_status_is_200_206_or_416_only() -> None:
    for status in range(0, 1000):
        if status in (200, 206, 416):
            continue
        with pytest.raises(hr.RangeError, match="status must be 200, 206 or 416"):
            hr.RangeDecision(status, (), 10, "x")
    assert hr.RangeDecision(200, (), 10, "x").status == 200
    assert hr.RangeDecision(416, [], 10, "x").content_range == "bytes */10"


@pytest.mark.parametrize("status", [200, 416])
def test_only_a_206_decision_carries_ranges(status: int) -> None:
    with pytest.raises(hr.RangeError, match=f"a {status} decision carries no ranges"):
        hr.RangeDecision(status, (hr.ByteRange(0, 0),), 10, "x")
    with pytest.raises(hr.RangeError, match="a 206 decision needs at least one range"):
        hr.RangeDecision(206, (), 10, "x")


@pytest.mark.parametrize("reason", [5, None, b"x", ["x"]])
def test_a_decision_reason_must_be_a_str(reason: Any) -> None:
    with pytest.raises(hr.RangeError, match="reason must be a str"):
        hr.RangeDecision(200, (), 10, reason)


def test_a_bytes_request_holds_specs_only_and_another_unit_other_items_only() -> None:
    spec = hr.RangeSpec(0, 1)
    with pytest.raises(hr.MalformedRange, match="a bytes range request needs specs"):
        hr.RangeRequest("bytes", (spec,), ("x",))
    with pytest.raises(hr.MalformedRange, match="a bytes range request needs specs"):
        hr.RangeRequest("bytes", (), ("x",))
    with pytest.raises(hr.MalformedRange, match="another unit needs other items only"):
        hr.RangeRequest("pages", (spec,), ("x",))
    with pytest.raises(hr.MalformedRange, match="another unit needs other items only"):
        hr.RangeRequest("pages", (spec,))
    assert str(hr.RangeRequest("pages", other=("x",))) == "pages=x"


@pytest.mark.parametrize("unit", ["a b", "", "bytes ", " bytes", "by=tes", "b,c", "caf\xe9"])
def test_a_range_request_unit_must_be_a_token(unit: str) -> None:
    with pytest.raises(hr.MalformedRange, match="is not a token"):
        hr.RangeRequest(unit, other=("x",))


def test_resolve_ranges_parses_a_str_subclass_as_a_header() -> None:
    class Header(str):
        pass

    assert hr.resolve_ranges(Header("bytes=0-1"), 10) == (hr.ByteRange(0, 1),)
    with pytest.raises(hr.UnsupportedRangeUnit):
        hr.resolve_ranges(Header("items=1"), 10)


class IntFaker:
    """Reports ``int`` through ``__class__`` without being one."""

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return int


@pytest.mark.parametrize(
    ("call", "error"),
    [
        (lambda v: hr.RangeSpec(v, None), hr.MalformedRange),
        (lambda v: hr.ByteRange(v, 0), hr.RangeError),
        (lambda v: hr.resolve_ranges("bytes=0-1", v), hr.RangeError),
        (lambda v: hr.RangePolicy(max_ranges=v), hr.RangeError),
        (lambda v: hr.build_content_range(0, 1, v), hr.RangeError),
        (lambda v: hr.ContentRange("bytes", 0, 1, v), hr.MalformedContentRange),
        (lambda v: hr.RangeDecision(v, (), 10, "x"), hr.RangeError),
        (lambda v: hr.parse_multipart_byteranges(b"", "x", max_parts=v), hr.MalformedMultipart),
    ],
)
def test_an_int_class_faker_is_refused_with_the_documented_error(call: Any, error: Any) -> None:
    faker = IntFaker()
    assert isinstance(faker, int)
    with pytest.raises(error, match="must be an int, got IntFaker"):
        call(faker)


def test_rfc_850_years_use_a_29_february_clock_as_the_28th() -> None:
    now = datetime(2024, 2, 29, tzinfo=UTC)
    march = hr.parse_http_date("Thursday, 01-Mar-74 00:00:00 GMT", now=now)
    assert march == datetime(1974, 3, 1, tzinfo=UTC)
    february = hr.parse_http_date("Wednesday, 28-Feb-74 00:00:00 GMT", now=now)
    assert february == datetime(2074, 2, 28, tzinfo=UTC)


@pytest.mark.parametrize(
    "call",
    [
        lambda: hr.RangeSpec(10**1500, 5),
        lambda: hr.ByteRange(10**1500, 0),
        lambda: hr.ByteRange(0, 10**3999).content_range(10**1500),
        lambda: hr.build_content_range(10**1500, 5, None),
        lambda: hr.ContentRange("bytes", 10**1500, 5, None),
        lambda: hr.RangeDecision(206, (hr.ByteRange(0, 10**1500),), 10**1499, "x"),
        lambda: hr.resolve_ranges("bytes=" + "9" * 1500 + "-", 10),
        lambda: hr.RangePolicy(max_overlapping=-(10**1500)),
    ],
)
def test_an_error_names_a_huge_number_by_its_size(call: Any) -> None:
    with pytest.raises(hr.RangeError) as caught:
        call()
    assert len(str(caught.value)) < 120, str(caught.value)[:200]
    assert "999999999999999999999" not in str(caught.value)
    assert "000000000000000000000" not in str(caught.value)
