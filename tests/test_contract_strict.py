"""Server-side values are checked strictly, lying objects never reach a comparison, and
counts stay cheap to print."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pytest

import httprange as hr
from httprange._cli import main

STAMP = "Fri, 02 Jan 2026 03:04:05 GMT"


@pytest.mark.parametrize("value", ["yesterday", "2026-01-02T03:04:05Z", "", " "])
def test_a_last_modified_that_is_not_an_http_date_raises(value: str) -> None:
    with pytest.raises(hr.MalformedDate):
        hr.if_range_matches(STAMP, last_modified=value)
    with pytest.raises(hr.MalformedDate):
        hr.if_range_matches('"v1"', etag='"v1"', last_modified=value)
    for header in (None, "bytes=0-1"):
        with pytest.raises(hr.MalformedDate):
            hr.evaluate_range_request(
                method="GET", range_header=header, length=10, if_range=STAMP, last_modified=value
            )
    with pytest.raises(hr.MalformedDate):
        hr.evaluate_range_request(method="GET", range_header=None, length=10, last_modified=value)


def test_a_last_modified_http_date_in_any_format_is_accepted() -> None:
    for value in (STAMP, "Friday, 02-Jan-26 03:04:05 GMT", "Fri Jan  2 03:04:05 2026"):
        assert hr.if_range_matches(STAMP, last_modified=value)


def test_the_cli_refuses_a_last_modified_typo(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["decide", "--range", "bytes=0-9", "--length", "100", "--if-range", STAMP]
    assert main([*args, "--last-modified", "2026-01-02T03:04:05Z"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "not an HTTP-date" in err
    assert main([*args, "--last-modified", STAMP]) == 0
    out, err = capsys.readouterr()
    assert (out.splitlines()[0], err) == ("status: 206", "")


def test_overlaps_reads_a_subclass_through_a_checked_copy() -> None:
    class Lying(hr.ByteRange):
        __slots__ = ()

        def __init__(self) -> None:
            object.__setattr__(self, "first", "x")
            object.__setattr__(self, "last", None)

    class Prop(hr.ByteRange):
        first = property(lambda self: 1.5)
        last = property(lambda self: 10**5000)

        def __init__(self) -> None:
            pass

    with pytest.raises(hr.RangeError, match="first must be an int, got str"):
        hr.ByteRange(0, 1).overlaps(Lying())
    with pytest.raises(hr.RangeError, match="first must be an int, got float"):
        hr.ByteRange(0, 1).overlaps(Prop())

    class Plain(hr.ByteRange):
        pass

    assert hr.ByteRange(0, 1).overlaps(Plain(1, 1))
    assert not hr.ByteRange(0, 1).overlaps(Plain(5, 6))


class BadIter:
    """Passes ``isinstance(x, Iterable)``, but its ``__iter__`` returns a non-iterator."""

    def __iter__(self) -> Any:
        return 5


def test_an_iterable_whose_iter_returns_a_non_iterator_raises_a_typed_error() -> None:
    with pytest.raises(hr.MalformedRange, match="ranges must be a str or RangeSpec items"):
        hr.resolve_ranges(BadIter(), 10)
    with pytest.raises(hr.RangeError, match="ranges must be an iterable of ByteRange"):
        hr.build_multipart_byteranges(b"ab", BadIter())
    with pytest.raises(hr.MalformedMultipart, match="parts must be an iterable of BytePart"):
        hr.encode_multipart_byteranges(BadIter())


def test_an_error_raised_by_the_callers_own_iterator_passes_through() -> None:
    def broken() -> Any:
        yield hr.RangeSpec(0, 1)
        raise KeyError("caller")

    with pytest.raises(KeyError):
        hr.resolve_ranges(broken(), 10)


def policy(field: str, value: int) -> dict[str, Any]:
    return {field: value}


@pytest.mark.parametrize("field", ["max_ranges", "max_overlapping", "coalesce_gap"])
def test_policy_counts_are_bounded_to_4000_digits(field: str) -> None:
    with pytest.raises(hr.RangeError, match=f"{field} has more than 4000 digits"):
        hr.RangePolicy(**policy(field, 10**4000))
    widest = hr.RangePolicy(**policy(field, 10**4000 - 1))
    assert getattr(widest, field) == 10**4000 - 1
    start = time.perf_counter()
    assert repr(widest).count("9") >= 4000
    assert time.perf_counter() - start < 1.0
    with pytest.raises(hr.RangeError):
        hr.RangePolicy(**policy(field, 10**1_000_000))


def test_naive_last_modified_still_raises_range_error() -> None:
    with pytest.raises(hr.RangeError):
        hr.if_range_matches(STAMP, last_modified=datetime(2020, 1, 1))
