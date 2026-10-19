"""Results never depend on the interpreter's digit limit, on subclasses that override their
methods, or on threads; exceptions from the caller's own objects pass through unchanged."""

from __future__ import annotations

import random
import sys
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone, tzinfo

import generators as gen
import pytest

import httprange as hr

NINES = "9" * 4000


@pytest.mark.skipif(not hasattr(sys, "set_int_max_str_digits"), reason="no digit limit")
def test_wide_numbers_work_under_the_smallest_digit_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from httprange._cli import main

    wide = 10**4000 - 1  # never converted from text here
    saved = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        (spec,) = hr.parse_range_request(f"bytes={NINES}-").specs
        assert spec.start == wide and str(spec) == NINES + "-"
        assert hr.ByteRange(0, wide).content_range(None) == "bytes 0-" + NINES + "/*"
        assert str(hr.parse_content_range("bytes 0-" + NINES + "/*")).endswith(NINES + "/*")
        decision = hr.evaluate_range_request(method="GET", range_header="bytes=5-", length=wide)
        assert decision.content_range == "bytes 5-" + NINES[:-1] + "8/" + NINES
        with pytest.raises(hr.RangeError, match="bit"):
            hr.ByteRange(wide, 1)
        assert main(["resolve", "bytes=0-0", "--length", NINES, "--json"]) == 0
        assert NINES in capsys.readouterr().out
    finally:
        sys.set_int_max_str_digits(saved)


class LyingStr(str):
    def strip(self, *args: object) -> str:
        return "bytes=0-0"

    def partition(self, *args: object) -> tuple[str, str, str]:
        return ("bytes", "=", "0-0")

    def lower(self) -> str:
        return "bytes"

    def __eq__(self, other: object) -> bool:
        return True

    __hash__ = str.__hash__


class LyingInt(int):
    def __lt__(self, other: object) -> bool:
        return False

    def __index__(self) -> int:
        return 0


class LyingBytes(bytes):
    def __len__(self) -> int:
        return 0

    def __contains__(self, item: object) -> bool:
        return False


class LyingList(list):  # type: ignore[type-arg]
    def __iter__(self) -> Iterator[object]:
        return iter([])


class LyingTuple(tuple):  # type: ignore[type-arg]
    def __iter__(self) -> Iterator[object]:
        return iter([hr.RangeSpec(5, 6)])


class LyingByteArray(bytearray):
    def __bytes__(self) -> bytes:
        return b"evil!"


class PlainByteArray(bytearray):
    pass


def test_subclasses_cannot_steer_a_result() -> None:
    assert hr.parse_range_request(LyingStr("bytes=5-9")).specs == (hr.RangeSpec(5, 9),)
    assert hr.parse_content_range(LyingStr("items 1-2/3")).unit == "items"
    with pytest.raises(hr.RangeError):
        hr.ByteRange(LyingInt(5), 2)
    assert type(hr.ByteRange(LyingInt(1), 2).first) is int
    with pytest.raises(hr.MalformedMultipart, match="boundary occurs"):
        hr.build_multipart_byteranges(LyingBytes(b"ab--b"), [hr.ByteRange(0, 4)], boundary="b")
    lying = LyingList([hr.RangeSpec(0, 0)])
    assert hr.RangeRequest("bytes", lying).specs == (hr.RangeSpec(0, 0),)
    part = hr.BytePart(hr.ContentRange("bytes", 0, 1, 2), LyingBytes(b"ab"))
    assert type(part.data) is bytes and part.data == b"ab"
    assert str(hr.RangeRequest("bytes", LyingTuple((hr.RangeSpec(0, 1),)))) == "bytes=0-1"
    span = hr.ContentRange("bytes", 0, 1, 5)
    for data in (LyingByteArray(b"ab"), PlainByteArray(b"ab")):
        part = hr.BytePart(span, data)
        assert type(part.data) is bytes and part.data == b"ab"


def test_a_released_memoryview_is_refused() -> None:
    view = memoryview(b"abc")
    view.release()
    with pytest.raises(hr.RangeError, match="released"):
        hr.build_multipart_byteranges(view, [hr.ByteRange(0, 0)])


class Broken(tzinfo):
    def utcoffset(self, moment: datetime | None) -> timedelta:
        raise ZeroDivisionError("from the caller's tzinfo")

    def dst(self, moment: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, moment: datetime | None) -> str:
        return "broken"


def test_exceptions_from_the_callers_objects_pass_through() -> None:
    with pytest.raises(ZeroDivisionError):
        hr.format_http_date(datetime(2026, 1, 1, tzinfo=Broken()))

    def specs() -> Iterator[hr.RangeSpec]:
        yield hr.RangeSpec(0, 0)
        raise KeyError("from the caller's iterator")

    with pytest.raises(KeyError):
        hr.resolve_ranges(specs(), 10)


def test_threads_get_the_answers_a_single_thread_gets() -> None:
    rng = random.Random(77)
    headers = [gen.range_header(rng) for _ in range(400)]

    def answers() -> list[object]:
        found: list[object] = []
        for header in headers:
            try:
                found.append(hr.resolve_ranges(header, 1000))
            except hr.RangeError as error:
                found.append(type(error))
        return found

    expected = answers()
    results: list[list[object]] = []
    threads = [threading.Thread(target=lambda: results.append(answers())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert results == [expected] * 8
    assert hr.parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT").tzinfo is timezone.utc
