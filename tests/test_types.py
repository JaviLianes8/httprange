"""Every argument of every public name refuses the wrong type with a typed error.

A wrong type is a programming error, yet it still raises a RangeError subclass (never a
bare TypeError or AttributeError from inside the library), so one ``except`` covers all.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest import mock

import pytest

import httprange as hr

CR = hr.ContentRange("bytes", 0, 0, 1)
PART = hr.BytePart(CR, b"z")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
BAD_COUNT = [1.0, True, "1", b"1", None, [1]]
BAD_INT = [*BAD_COUNT, 10**4000]  # positions and lengths have at most 4000 digits
BAD_STR = [b"x", 1, None, ["x"], bytearray(b"x")]
BAD_BYTES = ["x", 1, None, [1]]


def _ints(call: Callable[[Any], object], error: type[Exception], bad: Any = BAD_INT) -> list[Any]:
    return [(call, value, error) for value in bad]


def _strs(call: Callable[[Any], object], error: type[Exception]) -> list[Any]:
    return [(call, value, error) for value in BAD_STR]


def _decide(**kwargs: Any) -> object:
    return hr.evaluate_range_request(
        **{"method": "GET", "range_header": "bytes=0-0", "length": 9, **kwargs}
    )


CASES: list[Any] = [
    *_strs(hr.parse_range, hr.MalformedRange),
    *_strs(hr.parse_range_request, hr.MalformedRange),
    *_strs(hr.parse_accept_ranges, hr.MalformedRange),
    *_strs(hr.parse_content_range, hr.MalformedContentRange),
    *_strs(hr.parse_http_date, hr.MalformedDate),
    *_strs(lambda v: hr.resolve(v, 9), hr.MalformedRange),
    *_strs(lambda v: hr.build_content_range(0, 0, 1, unit=v), hr.RangeError),
    *_strs(lambda v: hr.ContentRange(v, 0, 0, 1), hr.MalformedContentRange),
    *_strs(lambda v: hr.RangeRequest(v, (hr.RangeSpec(0, 0),)), hr.MalformedRange),
    *_strs(lambda v: hr.if_range_matches(v), hr.RangeError),
    *_strs(lambda v: hr.if_range_matches('"a"', etag=v) if v is not None else 1 / 0, hr.RangeError),
    *_strs(lambda v: hr.parse_multipart_byteranges(b"", v), hr.MalformedMultipart),
    *_strs(lambda v: hr.MultipartBody(v, b"", "b"), hr.MalformedMultipart),
    *_strs(lambda v: hr.MultipartBody("t", b"", v), hr.MalformedMultipart),
    *_strs(lambda v: _decide(method=v), hr.RangeError),
    *_strs(lambda v: _decide(range_header=v) if v is not None else 1 / 0, hr.RangeError),
    *_ints(
        lambda v: hr.parse_range_request("bytes=0-0", max_empty=v), hr.MalformedRange, BAD_COUNT
    ),
    *_ints(lambda v: hr.parse_accept_ranges("bytes", max_empty=v), hr.MalformedRange, BAD_COUNT),
    *_ints(lambda v: hr.resolve("bytes=0-0", v), hr.RangeError),
    *_ints(lambda v: hr.resolve_ranges("bytes=0-0", v), hr.RangeError),
    *_ints(lambda v: hr.RangeSpec(v, None) if v is not None else 1 / 0, hr.MalformedRange),
    *_ints(lambda v: hr.RangeSpec(0, 1).resolve(v), hr.RangeError),
    *_ints(lambda v: hr.ByteRange(v, 5), hr.RangeError),
    *_ints(
        lambda v: hr.ByteRange(0, 5).content_range(v) if v is not None else 1 / 0, hr.RangeError
    ),
    *_ints(lambda v: hr.RangePolicy(max_ranges=v), hr.RangeError, BAD_COUNT),
    *_ints(lambda v: hr.RangePolicy(max_overlapping=v), hr.RangeError, BAD_COUNT),
    *_ints(lambda v: hr.build_content_range(v, 5, 9) if v is not None else 1 / 0, hr.RangeError),
    *_ints(
        lambda v: hr.ContentRange("bytes", 0, 0, v) if v is not None else 1 / 0,
        hr.MalformedContentRange,
    ),
    *_ints(
        lambda v: hr.parse_multipart_byteranges(
            b"", "multipart/byteranges; boundary=b", max_parts=v
        ),
        hr.MalformedMultipart,
        BAD_COUNT,
    ),
    *_ints(lambda v: _decide(length=v), hr.RangeError),
    *_ints(lambda v: hr.RangeDecision(v, (), 9, "x"), hr.RangeError),
    *[
        (lambda v: hr.build_multipart_byteranges(v, [hr.ByteRange(0, 0)]), v, hr.RangeError)
        for v in BAD_BYTES
    ],
    *[(lambda v: hr.BytePart(CR, v), v, hr.MalformedMultipart) for v in BAD_BYTES],
    *[
        (
            lambda v: hr.parse_multipart_byteranges(v, "multipart/byteranges; boundary=b"),
            v,
            hr.MalformedMultipart,
        )
        for v in BAD_BYTES
    ],
    *[
        (call, value, error)
        for value in (1, "x", b"x", [object()], None)
        for call, error in (
            (lambda v: hr.resolve_ranges(v, 9), hr.MalformedRange),
            (lambda v: hr.build_multipart_byteranges(b"ab", v), hr.RangeError),
            (lambda v: hr.encode_multipart_byteranges(v), hr.MalformedMultipart),
            (lambda v: hr.RangeRequest("bytes", v), hr.MalformedRange),
            (lambda v: hr.RangeDecision(206, v, 9, "x"), hr.RangeError),
        )
    ],
    *[
        (call, value, hr.RangeError)
        for value in (1, "x", datetime(2026, 1, 1), None)
        for call in (
            hr.format_http_date,
            lambda v: hr.parse_http_date("Sunday, 06-Nov-94 08:49:37 GMT", now=v) if v else 1 / 0,
            lambda v: hr.if_range_matches("x", last_modified=v) if v != "x" and v else 1 / 0,
            lambda v: hr.resolve_ranges("bytes=0-0", 9, policy=v),
            lambda v: hr.BytePart(v, b"z") if v is not None else 1 / 0,
            lambda v: hr.ByteRange(0, 0).overlaps(v),
        )
    ],
    *[
        (call, value, hr.RangeError)
        for value in (1, "yes", None)
        for call in (
            lambda v: hr.if_range_matches("x", date_is_strong=v),
            lambda v: hr.RangePolicy(coalesce=v),
            lambda v: _decide(date_is_strong=v),
        )
    ],
    (lambda v: _decide(on_excessive=v), "drop", hr.RangeError),
    (lambda v: _decide(on_excessive=v), ["reject"], hr.RangeError),
]


@pytest.mark.parametrize(("call", "value", "error"), CASES, ids=lambda item: repr(item)[:24])
def test_a_wrong_type_raises_the_documented_error(call: Any, value: Any, error: Any) -> None:
    try:
        call(value)
    except ZeroDivisionError:
        return  # a value that this argument accepts (None for an optional one)
    except error as caught:
        assert len(str(caught)) < 200
        return
    raise AssertionError(f"{value!r} was accepted")


def test_objects_faking_their_class_are_refused() -> None:
    for fake, call in (
        (mock.Mock(spec=hr.RangeSpec), lambda v: hr.resolve_ranges([v], 9)),
        (mock.Mock(spec=hr.ByteRange), lambda v: hr.build_multipart_byteranges(b"ab", [v])),
        (mock.Mock(spec=hr.BytePart), lambda v: hr.encode_multipart_byteranges([v])),
        (mock.Mock(spec=str), hr.parse_range_request),
        (mock.Mock(spec=hr.RangePolicy), lambda v: hr.resolve_ranges("bytes=0-0", 9, policy=v)),
    ):
        assert isinstance(fake, fake._spec_class)
        with pytest.raises(hr.RangeError):
            call(fake)
