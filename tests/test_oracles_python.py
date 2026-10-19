"""werkzeug and aiohttp as independent oracles (skipped when they are not installed).

Checked against werkzeug 3.1.9 and aiohttp 3.14.5 on 2026-10-18. Inside RFC 9110 they
answer as this library does; each of their departures is asserted on its own.
"""

from __future__ import annotations

import random

import pytest

import httprange as hr


def _specs(rng: random.Random, size: int) -> list[str]:
    specs = []
    for _ in range(rng.randrange(1, 5)):
        first = rng.choice((0, size - 1, size, rng.randrange(2 * size)))
        kind = rng.randrange(3)
        if kind == 0:
            specs.append(f"{first}-{first + rng.randrange(size)}")
        else:
            specs.append(f"{first}-" if kind == 1 else f"-{rng.randrange(1, 2 * size)}")
    return specs


def _ascending(specs: list[str]) -> bool:
    """werkzeug's extra rule: ranges in ascending order without overlap, open ones last."""
    end = 0
    for spec in specs:
        first, last = spec.split("-")
        if end < 0 or (first and int(first) < end):
            return False
        end = int(last) + 1 if first and last else -1
    return True


def test_werkzeug_parses_what_this_library_parses_in_ascending_order() -> None:
    http = pytest.importorskip("werkzeug.http")
    rng = random.Random(3191)
    for _ in range(5000):
        specs = _specs(rng, rng.choice((1, 10, 1000)))
        header = rng.choice(("bytes=", "Bytes=", "bytes= ")) + ",".join(specs)
        theirs = http.parse_range_header(header)
        ours = hr.parse_range_request(header)
        if not _ascending(specs):
            assert theirs is None, header
            continue
        expected = [
            (spec.start, None if spec.end is None else spec.end + 1)
            if spec.start is not None
            else (-(spec.end or 0), None)
            for spec in ours.specs
        ]
        assert theirs is not None and theirs.ranges == expected, header


def test_werkzeug_single_range_resolution() -> None:
    http = pytest.importorskip("werkzeug.http")
    rng = random.Random(7233)
    for _ in range(5000):
        size = rng.choice((1, 10, 1000))
        header = "bytes=" + _specs(rng, size)[0]
        theirs = http.parse_range_header(header).range_for_length(size)
        try:
            (item,) = hr.resolve_ranges(header, size)
        except hr.UnsatisfiableRange:
            assert theirs is None, header
            continue
        if header.startswith("bytes=-") and int(header[7:]) > size:
            # RFC 9110 14.1.2: a suffix longer than the representation selects all of it;
            # werkzeug calls it unsatisfiable.
            assert theirs is None and (item.first, item.last) == (0, size - 1)
        else:
            assert theirs == (item.first, item.last + 1), header


def test_werkzeug_content_range_and_its_departures() -> None:
    http = pytest.importorskip("werkzeug.http")
    rng = random.Random(1233)
    for _ in range(5000):
        first, extent = rng.randrange(1000), rng.randrange(1000)
        total = rng.choice((first + extent + 1 + rng.randrange(9), "*"))
        value = f"bytes {first}-{first + extent}/{total}"
        theirs, ours = http.parse_content_range_header(value), hr.parse_content_range(value)
        assert theirs is not None
        assert (theirs.units, theirs.start, theirs.stop, theirs.length) == (
            ours.unit,
            ours.first,
            (ours.last or 0) + 1,
            ours.complete_length,
        )
    # RFC 9110 14.4: a complete length not above the last position is invalid, and the
    # unsatisfied form needs a complete length; werkzeug accepts both.
    for value in ("bytes 0-1233/1000", "bytes */*"):
        assert http.parse_content_range_header(value) is not None
        with pytest.raises(hr.MalformedContentRange):
            hr.parse_content_range(value)


def test_aiohttp_selects_the_same_bytes_for_a_single_range() -> None:
    utils = pytest.importorskip("aiohttp.test_utils")
    rng = random.Random(3145)
    data = bytes(range(256)) * 4
    for _ in range(5000):
        size = rng.choice((1, 10, len(data)))
        header = rng.choice(("bytes=", "Bytes=")) + _specs(rng, size)[0]
        selected = data[:size][
            utils.make_mocked_request("GET", "/", headers={"Range": header}).http_range
        ]
        try:
            (item,) = hr.resolve_ranges(header, size)
        except hr.UnsatisfiableRange:
            assert selected == b"", header  # aiohttp leaves the 416 to the caller
            continue
        assert selected == data[:size][item.as_slice()], header
    request = utils.make_mocked_request("GET", "/", headers={"Range": "bytes=-0"})
    assert request.http_range == slice(0, None, 1)  # the whole body; RFC 9110: unsatisfiable
    with pytest.raises(hr.UnsatisfiableRange):
        hr.resolve_ranges("bytes=-0", 10)
    for header in ("bytes= 0-1", "bytes=0-1,4-5"):  # OWS after = (erratum 7306), two ranges
        with pytest.raises(ValueError):
            utils.make_mocked_request("GET", "/", headers={"Range": header}).http_range  # noqa: B018
        assert hr.resolve_ranges(header, 10)
