"""Objects the caller hands in cannot steer a result, and every value prints under any limit.

A subclass of ``datetime``, ``RangeSpec``, ``ByteRange`` or ``ContentRange`` with its own
methods is read through the base class, so the documented promise of each function holds
whatever the override returns. ``repr`` and ``str`` of the public values and errors work
under the smallest integer string conversion limit, and an error's ``repr`` never echoes
a huge input.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

import httprange as hr

UTC = timezone.utc
BIG = 10**700 + 7
TEXT = str(BIG)
NEXT = str(BIG + 1)


class LyingClock(datetime):
    def astimezone(self, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
        return datetime(1994, 11, 6, 8, 49, 37, tzinfo=UTC)

    def utcoffset(self) -> timedelta | None:
        return timedelta(hours=5)

    def weekday(self) -> int:
        return 0


class BrokenClock(datetime):
    def astimezone(self, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
        return "x"  # type: ignore[return-value]


class OffsetZone(tzinfo):
    def __init__(self, offset: object) -> None:
        self.offset = offset

    def utcoffset(self, moment: datetime | None) -> timedelta:
        return self.offset  # type: ignore[return-value]

    def dst(self, moment: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, moment: datetime | None) -> str:
        return "offset"


def test_a_datetime_subclass_cannot_change_the_formatted_date() -> None:
    moment = LyingClock(2026, 10, 19, 12, tzinfo=UTC)
    assert hr.format_http_date(moment) == "Mon, 19 Oct 2026 12:00:00 GMT"
    assert hr.format_http_date(BrokenClock(2026, 1, 1, tzinfo=UTC)) == (
        "Thu, 01 Jan 2026 00:00:00 GMT"
    )


def test_a_datetime_subclass_cannot_make_if_range_match() -> None:
    moment = LyingClock(2026, 10, 19, 12, tzinfo=UTC)
    assert not hr.if_range_matches("Sun, 06 Nov 1994 08:49:37 GMT", last_modified=moment)
    assert hr.if_range_matches("Mon, 19 Oct 2026 12:00:00 GMT", last_modified=moment)
    decision = hr.evaluate_range_request(
        method="GET",
        range_header="bytes=0-1",
        length=10,
        if_range="Thu, 01 Jan 2026 00:00:00 GMT",
        last_modified=BrokenClock(2026, 1, 1, tzinfo=UTC),
    )
    assert decision.status == 206


def test_now_is_read_through_the_base_class() -> None:
    now = LyingClock(2090, 1, 1, tzinfo=UTC)
    parsed = hr.parse_http_date("Sunday, 10-Nov-10 08:49:37 GMT", now=now)
    assert parsed.year == 2110


@pytest.mark.parametrize("offset", [timedelta(hours=30), "x", 5])
def test_a_tzinfo_with_an_invalid_offset_raises_range_error(offset: object) -> None:
    moment = datetime(2020, 1, 1, tzinfo=OffsetZone(offset))
    with pytest.raises(hr.RangeError, match="offset"):
        hr.format_http_date(moment)
    with pytest.raises(hr.RangeError, match="offset"):
        hr.if_range_matches('"a"', last_modified=moment)
    with pytest.raises(hr.RangeError, match="offset"):
        hr.parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT", now=moment)


def test_a_valid_offset_converts_to_utc() -> None:
    moment = datetime(2020, 1, 1, 3, tzinfo=OffsetZone(timedelta(hours=2)))
    assert hr.format_http_date(moment) == "Wed, 01 Jan 2020 01:00:00 GMT"


class LyingSpec(hr.RangeSpec):
    def byte_range(self, total: int) -> hr.ByteRange:
        return hr.ByteRange(0, 10**6)

    def resolve(self, total: int) -> tuple[int, int]:
        return (0, 10**6)

    @property
    def is_suffix(self) -> bool:
        return True


class LyingRange(hr.ByteRange):
    __slots__ = ()

    def as_slice(self) -> slice:
        return "x"  # type: ignore[return-value]

    def content_range(self, complete_length: int | None) -> str:
        return "bytes 0-0/1"


def test_spec_subclasses_resolve_as_their_fields_say() -> None:
    assert hr.resolve_ranges([LyingSpec(0, 1)], 10) == (hr.ByteRange(0, 1),)
    assert hr.resolve_ranges([LyingSpec(None, 3)], 10) == (hr.ByteRange(7, 9),)
    with pytest.raises(hr.UnsatisfiableRange):
        hr.resolve_ranges([LyingSpec(20, None)], 10)
    with pytest.raises(hr.UnsatisfiableRange):
        hr.resolve_ranges([LyingSpec(0, 1)], 0)  # not a suffix, whatever is_suffix says


def test_range_subclasses_slice_and_print_as_their_fields_say() -> None:
    body = hr.build_multipart_byteranges(b"abcdef", [LyingRange(0, 1)], boundary="b")
    assert body.body == b"--b\r\nContent-Range: bytes 0-1/6\r\n\r\nab\r\n--b--\r\n"
    decision = hr.RangeDecision(206, (LyingRange(2, 3),), 6, "r")
    assert decision.content_range == "bytes 2-3/6"


@pytest.fixture
def low_limit() -> Iterator[None]:
    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("no digit limit")
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


def test_values_print_under_the_smallest_digit_limit(
    low_limit: None, caplog: pytest.LogCaptureFixture
) -> None:
    big, text = BIG, TEXT
    spec = hr.RangeSpec(0, big)
    assert repr(spec) == f"RangeSpec(start=0, end={text})"
    assert repr(hr.RangeSpec(None, big)) == f"RangeSpec(start=None, end={text})"
    assert repr(hr.ByteRange(big, big)) == f"ByteRange(first={text}, last={text})"
    span = hr.ContentRange("bytes", 0, big, None)
    assert repr(span) == f"ContentRange(unit='bytes', first=0, last={text}, complete_length=None)"
    request = hr.RangeRequest("bytes", (spec,))
    assert repr(request) == f"RangeRequest(unit='bytes', specs=({spec!r},), other=())"
    decision = hr.RangeDecision(206, (hr.ByteRange(0, big),), big + 1, "r")
    expected = (
        f"RangeDecision(status=206, ranges=(ByteRange(first=0, last={text}),), "
        f"length={NEXT}, reason='r')"
    )
    assert repr(decision) == str(decision) == expected
    logging.getLogger("httprange-test").warning("got %r", spec)
    assert text in caplog.text


def test_errors_print_under_the_smallest_digit_limit(low_limit: None) -> None:
    big = 10**3999 - 1
    with pytest.raises(hr.UnsatisfiableRange) as info:
        hr.resolve_ranges("bytes=" + "9" * 3999 + "-", big)
    assert info.value.length == big
    assert repr(info.value).startswith("UnsatisfiableRange(")
    assert len(repr(info.value)) < 200


def test_error_args_hold_the_message_only() -> None:
    unit = "S3CR3T" + "q7Zx" * 250_000
    with pytest.raises(hr.UnsupportedRangeUnit) as info:
        hr.resolve_ranges(unit + "=0-1", 10)
    assert info.value.unit == unit.lower()
    assert info.value.args == (str(info.value),)
    assert len(repr(info.value)) < 200
    unsatisfiable = hr.UnsatisfiableRange("none fit", 7)
    assert (unsatisfiable.args, unsatisfiable.length) == (("none fit",), 7)
