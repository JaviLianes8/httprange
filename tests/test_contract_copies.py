"""Values handed in are copied to plain ones, and every field of a moment survives.

A subclass of ``RangeSpec``, ``ContentRange``, ``BytePart`` or ``RangePolicy`` is read by
its fields once and then copied, so a later override of ``__str__`` or of attribute
access cannot change a header, a body or a policy check. Wrong-type errors name every
type the signature accepts.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

import httprange as hr

BIG = 10**700 + 7
TEXT = str(BIG)
NEXT = str(BIG + 1)


class SpecStr(hr.RangeSpec):
    def __str__(self) -> str:
        return "0-1\r\nX-Injected: 1"


class BogusSpan(hr.ContentRange):
    def __str__(self) -> str:
        return "bytes 9-9/99"


class LyingPart(hr.BytePart):
    lying = False

    def __getattribute__(self, name: str) -> object:
        if name == "data" and type(self).lying:
            return b"abc"
        return super().__getattribute__(name)


class LyingPolicy(hr.RangePolicy):
    lying = False

    def __getattribute__(self, name: str) -> object:
        if name == "coalesce_gap" and type(self).lying:
            return -5
        return super().__getattribute__(name)


class FoldZone(tzinfo):
    """+02:00 for the first of two ambiguous readings, +01:00 for the second."""

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=1 if dt is not None and dt.fold else 2)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "Fold"


def test_a_range_request_stores_plain_specs_and_prints_their_fields() -> None:
    request = hr.RangeRequest("bytes", [SpecStr(0, 1), SpecStr(None, 5)])
    assert [type(spec) for spec in request.specs] == [hr.RangeSpec, hr.RangeSpec]
    assert str(request) == "bytes=0-1,-5"
    assert request == hr.RangeRequest("bytes", (hr.RangeSpec(0, 1), hr.RangeSpec(None, 5)))


def test_a_part_stores_a_plain_content_range() -> None:
    part = hr.BytePart(BogusSpan("bytes", 0, 1, 5), b"ab")
    assert type(part.content_range) is hr.ContentRange
    body = hr.encode_multipart_byteranges([part], boundary="B").body
    assert b"Content-Range: bytes 0-1/5\r\n" in body
    assert b"9-9/99" not in body


def test_encode_rechecks_each_part_as_it_reads_now() -> None:
    part = LyingPart(hr.ContentRange("bytes", 0, 1, 5), b"ab")
    LyingPart.lying = True
    try:
        with pytest.raises(hr.MalformedMultipart, match="part holds 3 bytes"):
            hr.encode_multipart_byteranges([part], boundary="B")
    finally:
        LyingPart.lying = False


def test_resolve_rechecks_a_policy_as_it_reads_now() -> None:
    policy = LyingPolicy(coalesce=True)
    LyingPolicy.lying = True
    try:
        with pytest.raises(hr.RangeError, match="coalesce_gap must not be negative"):
            hr.resolve_ranges("bytes=0-9,20-29", 100, policy=policy)
    finally:
        LyingPolicy.lying = False


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


def test_every_field_of_a_span_and_a_policy_prints_under_the_digit_limit(
    low_limit: None,
) -> None:
    span = hr.ContentRange("bytes", BIG, BIG, BIG + 1)
    expected = f"ContentRange(unit='bytes', first={TEXT}, last={TEXT}, complete_length={NEXT})"
    assert repr(span) == expected
    policy = hr.RangePolicy(max_ranges=BIG, max_overlapping=BIG, coalesce_gap=BIG)
    assert repr(policy) == (
        f"RangePolicy(max_ranges={TEXT}, max_overlapping={TEXT}, coalesce=True, "
        f"coalesce_gap={TEXT})"
    )


def test_the_fold_picks_the_reading_of_an_ambiguous_local_time() -> None:
    first = datetime(2026, 10, 25, 2, 30, tzinfo=FoldZone())
    second = first.replace(fold=1)
    assert hr.format_http_date(first) == "Sun, 25 Oct 2026 00:30:00 GMT"
    assert hr.format_http_date(second) == "Sun, 25 Oct 2026 01:30:00 GMT"
    assert hr.if_range_matches("Sun, 25 Oct 2026 01:30:00 GMT", last_modified=second)
    assert not hr.if_range_matches("Sun, 25 Oct 2026 01:30:00 GMT", last_modified=first)
    rfc850 = "Sunday, 25-Oct-26 01:30:00 GMT"
    assert hr.parse_http_date(rfc850, now=second).year == 2026


def test_microseconds_count_when_moving_to_utc() -> None:
    when = datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=timezone(timedelta(microseconds=1)))
    assert hr.format_http_date(when) == "Thu, 01 Jan 2026 00:00:00 GMT"


@pytest.mark.parametrize(
    "moment",
    [
        datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
        datetime(9999, 12, 31, 23, 30, tzinfo=timezone(timedelta(hours=-1))),
    ],
)
def test_a_moment_outside_the_utc_years_raises_range_error(moment: datetime) -> None:
    with pytest.raises(hr.RangeError, match="when is outside the years 1 to 9999 in UTC"):
        hr.format_http_date(moment)
    with pytest.raises(hr.RangeError, match="now is outside the years 1 to 9999 in UTC"):
        hr.parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT", now=moment)
    with pytest.raises(hr.RangeError, match="last_modified is outside the years 1 to 9999"):
        hr.if_range_matches("Sun, 06 Nov 1994 08:49:37 GMT", last_modified=moment)


SPAN = hr.ContentRange("bytes", 0, 1, 10)
MEDIA = "multipart/byteranges; boundary=b"


@pytest.mark.parametrize(
    ("kind", "args", "message"),
    [
        (hr.RangeRequest, ("bytes", {hr.RangeSpec(0, 1)}), "specs must be a tuple or list, got"),
        (hr.RangeRequest, ("items", (), "a"), "other must be a tuple or list, got str"),
        (hr.RangeDecision, (206, iter([hr.ByteRange(0, 0)]), 10, "x"), "ranges must be a tuple"),
        (hr.BytePart, (SPAN, "ab"), "data must be bytes, bytearray or memoryview, got str"),
        (hr.MultipartBody, (MEDIA, "x", "b"), "body must be bytes, bytearray or memoryview, got"),
    ],
)
def test_a_wrong_type_error_names_every_accepted_type(
    kind: Callable[..., object], args: tuple[object, ...], message: str
) -> None:
    with pytest.raises(hr.RangeError) as info:
        kind(*args)
    assert str(info.value).startswith(message)
