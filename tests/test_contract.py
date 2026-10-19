"""The public contract: every exported name, and the promise each one makes.

Each entry in ``CONTRACTS`` exercises one public name against RFC 9110 examples. The
first tests fail the moment ``__all__`` and this file disagree.
"""

from __future__ import annotations

import dataclasses
import importlib.resources
from collections.abc import Callable
from datetime import datetime, timezone

import pytest

import httprange as hr

PUBLIC_API: list[str] = [
    "BytePart",
    "ByteRange",
    "ContentRange",
    "ExcessiveRanges",
    "MalformedContentRange",
    "MalformedDate",
    "MalformedMultipart",
    "MalformedRange",
    "MultipartBody",
    "RangeDecision",
    "RangeError",
    "RangePolicy",
    "RangeRequest",
    "RangeSpec",
    "UnsatisfiableRange",
    "UnsupportedRangeUnit",
    "build_content_range",
    "build_multipart_byteranges",
    "encode_multipart_byteranges",
    "evaluate_range_request",
    "format_http_date",
    "if_range_matches",
    "parse_accept_ranges",
    "parse_content_range",
    "parse_http_date",
    "parse_multipart_byteranges",
    "parse_range",
    "parse_range_request",
    "resolve",
    "resolve_ranges",
]
STAMP = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)


def _raises(error: type[BaseException], call: Callable[[], object]) -> None:
    with pytest.raises(error):
        call()


def _errors() -> None:
    for name in PUBLIC_API:
        item = getattr(hr, name)
        if isinstance(item, type) and issubclass(item, BaseException):
            assert issubclass(item, hr.RangeError) and issubclass(item, ValueError)


def _multipart_round_trip() -> None:
    ranges = [hr.ByteRange(500, 999), hr.ByteRange(7000, 7999)]
    data = bytes(8000)
    body = hr.build_multipart_byteranges(data, ranges, content_type="application/pdf")
    parts = hr.parse_multipart_byteranges(body.body, body.content_type)
    assert [str(part.content_range) for part in parts] == [
        "bytes 500-999/8000",
        "bytes 7000-7999/8000",
    ]
    assert all(part.content_type == "application/pdf" for part in parts)


CONTRACTS: dict[str, Callable[[], None]] = {
    "BytePart": lambda: _multipart_round_trip(),
    "ByteRange": lambda: _check(hr.ByteRange(734, 1233).content_range(1234), "bytes 734-1233/1234"),
    "ContentRange": lambda: _check(hr.ContentRange("bytes", 42, 1233, None).length, 1192),
    "ExcessiveRanges": lambda: _raises(
        hr.ExcessiveRanges, lambda: hr.resolve_ranges("bytes=0-0,0-0,0-0", 9)
    ),
    "MalformedContentRange": lambda: _raises(
        hr.MalformedContentRange, lambda: hr.parse_content_range("bytes 9-1/10")
    ),
    "MalformedDate": lambda: _raises(hr.MalformedDate, lambda: hr.parse_http_date("1994-11-06")),
    "MalformedMultipart": lambda: _raises(
        hr.MalformedMultipart, lambda: hr.parse_multipart_byteranges(b"", "text/plain")
    ),
    "MalformedRange": lambda: _raises(
        hr.MalformedRange, lambda: hr.parse_range_request("bytes=500-100")
    ),
    "MultipartBody": lambda: _multipart_round_trip(),
    "RangeDecision": lambda: _check(
        hr.RangeDecision(416, (), 47022, "x").content_range, "bytes */47022"
    ),
    "RangeError": _errors,
    "RangePolicy": lambda: _check(hr.RangePolicy().max_overlapping, 2),
    "RangeRequest": lambda: _check(
        str(hr.parse_range_request("bytes= 0-999, 4500-5499, -1000")), "bytes=0-999,4500-5499,-1000"
    ),
    "RangeSpec": lambda: _check(hr.RangeSpec(None, 500).resolve(10000), (9500, 9999)),
    "UnsatisfiableRange": lambda: _raises(
        hr.UnsatisfiableRange, lambda: hr.resolve("bytes=10000-", 10000)
    ),
    "UnsupportedRangeUnit": lambda: _raises(
        hr.UnsupportedRangeUnit, lambda: hr.resolve_ranges("items=1-2", 9)
    ),
    "build_content_range": lambda: _check(hr.build_content_range(None, None, 1234), "bytes */1234"),
    "build_multipart_byteranges": lambda: _multipart_round_trip(),
    "encode_multipart_byteranges": lambda: _raises(
        hr.MalformedMultipart, lambda: hr.encode_multipart_byteranges([])
    ),
    "evaluate_range_request": lambda: _check(
        hr.evaluate_range_request(
            method="GET", range_header="bytes=21010-", length=47022
        ).content_range,
        "bytes 21010-47021/47022",
    ),
    "format_http_date": lambda: _check(hr.format_http_date(STAMP), "Sun, 06 Nov 1994 08:49:37 GMT"),
    "if_range_matches": lambda: _check(
        (hr.if_range_matches('"1"', etag='"1"'), hr.if_range_matches('W/"1"', etag='W/"1"')),
        (True, False),
    ),
    "parse_accept_ranges": lambda: _check(hr.parse_accept_ranges("none"), ("none",)),
    "parse_content_range": lambda: _check(
        hr.parse_content_range("bytes */1234").complete_length, 1234
    ),
    "parse_http_date": lambda: _check(hr.parse_http_date("Sun Nov  6 08:49:37 1994"), STAMP),
    "parse_multipart_byteranges": lambda: _multipart_round_trip(),
    "parse_range": lambda: _check(
        hr.parse_range("bytes=0-0,-1"), [hr.RangeSpec(0, 0), hr.RangeSpec(None, 1)]
    ),
    "parse_range_request": lambda: _check(
        hr.parse_range_request("Bytes=9500-").specs, (hr.RangeSpec(9500, None),)
    ),
    "resolve": lambda: _check(hr.resolve("bytes=0-0,-1", 10000), [(0, 0), (9999, 9999)]),
    "resolve_ranges": lambda: _check(
        hr.resolve_ranges("bytes=500-600,601-999", 10000), (hr.ByteRange(500, 999),)
    ),
}


def _check(actual: object, expected: object) -> None:
    assert actual == expected


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(hr.__all__) == sorted(PUBLIC_API)


def test_every_exported_name_resolves_and_has_a_contract() -> None:
    for name in hr.__all__:
        assert hasattr(hr, name)
    assert sorted(CONTRACTS) == sorted(PUBLIC_API)


@pytest.mark.parametrize("name", PUBLIC_API)
def test_each_public_name_keeps_its_promise(name: str) -> None:
    CONTRACTS[name]()


def test_every_public_name_is_documented() -> None:
    for name in PUBLIC_API:
        assert (getattr(hr, name).__doc__ or "").strip(), name


def test_public_dataclasses_are_frozen() -> None:
    samples: list[object] = [
        hr.ByteRange(0, 0),
        hr.RangePolicy(),
        hr.RangeRequest("bytes", (hr.RangeSpec(0, 0),)),
        hr.RangeSpec(0, 1),
        hr.ContentRange("bytes", None, None, 1),
        hr.RangeDecision(200, (), 1, "x"),
        hr.MultipartBody("t", b"", "b"),
        hr.BytePart(hr.ContentRange("bytes", 0, 0, 1), b"x"),
    ]
    for item in samples:
        name = dataclasses.fields(item)[0].name  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(item, name, None)


def test_version_is_a_three_part_string() -> None:
    parts = hr.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
    assert hr.__version__ == "1.0.0"


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("httprange").joinpath("py.typed").is_file()
