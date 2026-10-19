"""Seeded property tests: random and mutated input only ever raises the typed errors, and
the round trips and invariants hold for whatever is accepted."""

from __future__ import annotations

import itertools
import random
from datetime import datetime, timedelta, timezone

import generators as gen
import pytest

import httprange as hr

SEEDS = (1, 2, 3)
WIDE = hr.RangePolicy(max_ranges=1000, max_overlapping=1000, coalesce=False)


@pytest.mark.parametrize("seed", SEEDS)
def test_range_requests_round_trip_or_fail_typed(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(5000):
        header = gen.range_header(rng)
        try:
            request = hr.parse_range_request(header)
        except hr.MalformedRange as error:
            assert len(str(error)) < 300
            continue
        canonical = str(request)
        assert hr.parse_range_request(canonical) == request
        assert str(hr.parse_range_request(canonical)) == canonical
        if request.is_bytes:
            assert hr.parse_range(header.strip(" \t")) == list(request.specs)


def _satisfiable(header: str, length: int) -> list[hr.ByteRange]:
    found = []
    for spec in hr.parse_range_request(header).specs:
        try:
            found.append(spec.byte_range(length))
        except hr.UnsatisfiableRange:
            continue
    return found


@pytest.mark.parametrize("seed", SEEDS)
def test_resolution_keeps_its_invariants(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(4000):
        header, length = gen.range_header(rng), rng.choice((0, 1, 7, 1000, 10**12))
        gap = rng.choice((0, 0, 80))
        policy = hr.RangePolicy(max_ranges=1000, max_overlapping=1000, coalesce_gap=gap)
        try:
            ranges = hr.resolve_ranges(header, length, policy=policy)
            plain = hr.resolve_ranges(header, length, policy=WIDE)
        except (hr.MalformedRange, hr.UnsatisfiableRange, hr.UnsupportedRangeUnit) as error:
            assert len(str(error)) < 300
            continue
        if length == 0:  # only a non-zero suffix is satisfiable, and it selects nothing
            assert ranges == plain == ()
            continue
        assert list(plain) == _satisfiable(header, length)
        assert all(0 <= item.first <= item.last < length for item in ranges)
        ordered = sorted(ranges, key=lambda item: item.first)
        assert all(b.first > a.last + 1 + gap for a, b in itertools.pairwise(ordered))
        homes = [
            [i for i, r in enumerate(ranges) if r.first <= p.first and p.last <= r.last]
            for p in plain
        ]
        assert all(len(home) == 1 for home in homes)
        assert {r.first for r in ranges} <= {p.first for p in plain}
        assert {r.last for r in ranges} <= {p.last for p in plain}
        firsts = [min(i for i, home in enumerate(homes) if home == [n]) for n in range(len(ranges))]
        assert firsts == sorted(firsts)  # request order of the earliest spec in each range


@pytest.mark.parametrize("seed", SEEDS)
def test_content_ranges_round_trip_or_fail_typed(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(5000):
        try:
            span = hr.parse_content_range(gen.content_range(rng))
        except hr.MalformedContentRange as error:
            assert len(str(error)) < 300
            continue
        text = str(span)
        assert hr.parse_content_range(text) == span and span.unit == span.unit.lower()
        assert (
            hr.build_content_range(span.first, span.last, span.complete_length, unit=span.unit)
            == text
        )


@pytest.mark.parametrize("seed", SEEDS)
def test_multipart_bodies_round_trip_and_mutations_fail_typed(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(1500):
        size = rng.randrange(1, 500)
        data = bytes(rng.choice(b"-\r\nab\x00\xffB") for _ in range(size))
        ranges = []
        for _ in range(rng.randrange(1, 6)):
            first = rng.randrange(size)
            ranges.append(hr.ByteRange(first, rng.randrange(first, size)))
        media = rng.choice((None, "text/plain", 'application/pdf; x="y z"'))
        body = hr.build_multipart_byteranges(data, ranges, content_type=media)
        parts = hr.parse_multipart_byteranges(body.body, body.content_type)
        assert [p.data for p in parts] == [data[r.as_slice()] for r in ranges]
        assert [p.content_range for p in parts] == [
            hr.ContentRange("bytes", r.first, r.last, size) for r in ranges
        ]
        assert all(p.content_type == media for p in parts)
        try:
            parsed = hr.parse_multipart_byteranges(
                gen.noise_bytes(body.body, rng, 4), body.content_type
            )
        except hr.MalformedMultipart as error:
            assert len(str(error)) < 300
            continue
        # Only the bytes unit says how many octets a part holds (RFC 9110 14.4).
        assert all(
            p.content_range.unit != "bytes" or p.content_range.length == len(p.data) for p in parsed
        )


@pytest.mark.parametrize("seed", SEEDS)
def test_dates_round_trip_or_fail_typed(seed: int) -> None:
    rng = random.Random(seed)
    start = datetime(1, 1, 1, tzinfo=timezone.utc)
    for _ in range(4000):
        instant = start + timedelta(seconds=rng.randrange(315537897599))
        assert hr.parse_http_date(hr.format_http_date(instant)) == instant
        try:
            hr.parse_http_date(gen.http_date(rng))
        except hr.MalformedDate as error:
            assert len(str(error)) < 300


@pytest.mark.parametrize("seed", SEEDS)
def test_if_range_and_decisions_keep_their_invariants(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(4000):
        first, second = gen.entity_tag(rng), gen.entity_tag(rng)
        assert hr.if_range_matches(first, etag=second) is hr.if_range_matches(second, etag=first)
        header = rng.choice((None, gen.range_header(rng, most=4)))
        length = rng.choice((0, 1, 10, 1000))
        decision = hr.evaluate_range_request(
            method="GET",
            range_header=header,
            length=length,
            if_range=rng.choice((None, first)),
            etag=second,
        )
        assert decision.status in (200, 206, 416)
        assert (decision.status == 206) is bool(decision.ranges)
        assert decision.is_multipart is (len(decision.ranges) > 1)
        if decision.status == 416:
            assert decision.content_range == f"bytes */{length}"
        elif decision.status == 200 or decision.is_multipart:
            assert decision.content_range is None
        if header is not None and decision.is_multipart:
            assert "," in header  # a single range is never answered as multipart
