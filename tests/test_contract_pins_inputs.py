"""Pins for input edges: overlaps on a shared edge byte in either order, short messages
for a huge malformed last_modified, text refused as a list of ranges or parts, objects
iterable only by index, and the decide --etag option. Each runs in the default gate."""

from __future__ import annotations

from collections.abc import Callable

import pytest

import httprange as hr
from httprange._cli import main

HUGE = "x" * 1_000_000


class _Text(str):
    pass


class _ByIndex:
    """Iterable only through the old ``__getitem__`` protocol, with no ``__iter__``."""

    def __getitem__(self, index: int) -> hr.RangeSpec:
        if index < 2:
            return hr.RangeSpec(index, index)
        raise IndexError(index)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 9), (9, 20), True),
        ((5, 5), (5, 5), True),
        ((0, 0), (0, 5), True),
        ((3, 7), (0, 3), True),
        ((0, 8), (9, 20), False),
        ((4, 4), (5, 5), False),
    ],
)
def test_overlaps_is_symmetric_and_counts_a_shared_edge_byte(
    a: tuple[int, int], b: tuple[int, int], expected: bool
) -> None:
    left, right = hr.ByteRange(*a), hr.ByteRange(*b)
    assert left.overlaps(right) is expected
    assert right.overlaps(left) is expected


@pytest.mark.parametrize(
    "call",
    [
        lambda: hr.if_range_matches('"a"', etag='"a"', last_modified=HUGE),
        lambda: hr.evaluate_range_request(
            method="GET", range_header=None, length=1, last_modified=HUGE
        ),
        lambda: hr.evaluate_range_request(
            method="GET", range_header="bytes=0-0", length=1, last_modified=HUGE
        ),
    ],
)
def test_a_huge_malformed_last_modified_gives_a_short_message(call: Callable[[], object]) -> None:
    with pytest.raises(hr.MalformedDate) as caught:
        call()
    message = str(caught.value)
    assert message.startswith("last_modified is not an HTTP-date: 'xxx")
    assert len(message) <= 120


@pytest.mark.parametrize("text", ["", "ab", _Text(""), _Text("x")])
def test_text_is_refused_as_the_ranges_of_build_multipart(text: str) -> None:
    with pytest.raises(hr.RangeError) as caught:
        hr.build_multipart_byteranges(b"abc", text)  # type: ignore[arg-type]
    assert type(caught.value) is hr.RangeError
    name = type(text).__name__
    assert str(caught.value) == f"ranges must be an iterable of ByteRange, got {name}"


@pytest.mark.parametrize("text", ["", "ab", _Text(""), _Text("x")])
def test_text_is_refused_as_the_parts_of_encode_multipart(text: str) -> None:
    with pytest.raises(hr.MalformedMultipart) as caught:
        hr.encode_multipart_byteranges(text)  # type: ignore[arg-type]
    name = type(text).__name__
    assert str(caught.value) == f"parts must be an iterable of BytePart, got {name}"


def test_resolve_ranges_refuses_an_object_iterable_only_by_index() -> None:
    with pytest.raises(hr.MalformedRange) as caught:
        hr.resolve_ranges(_ByIndex(), 10)  # type: ignore[arg-type]
    assert str(caught.value) == "ranges must be a str or RangeSpec items, got _ByIndex"
    specs = list(iter(_ByIndex()))
    assert hr.resolve_ranges(specs, 10) == (hr.ByteRange(0, 1),)


def test_cli_decide_passes_the_etag(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["decide", "--range", "bytes=0-1", "--length", "10", "--if-range", '"v1"']
    assert main([*args, "--etag", '"v1"']) == 0
    out, err = capsys.readouterr()
    assert (out.splitlines()[0], err) == ("status: 206", "")
    assert main([*args, "--etag", '"v2"']) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["status: 200", "reason: If-Range does not match"]
