"""Python's own parsers as independent oracles: ``email`` for multipart bodies, and
``email.utils``, ``http.cookiejar`` and ``time.asctime`` for HTTP-dates.

Each comparison stays inside the oracle's own valid domain; where an oracle reads the RFC
differently, the difference is asserted on its own.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import random
import time
from datetime import datetime, timedelta, timezone
from http.cookiejar import http2time  # type: ignore[attr-defined]

import httprange as hr

MEDIA = ("application/octet-stream", "text/plain; charset=utf-8", None)


def test_the_email_package_reads_every_built_body() -> None:
    rng = random.Random(2046)
    checked = 0
    for _ in range(3000):
        size = rng.randrange(1, 400)
        data = bytes(rng.choice(b"\r\n-ab\x00\xff") for _ in range(size))
        ranges = []
        for _ in range(rng.randrange(1, 5)):
            first = rng.randrange(size)
            ranges.append(hr.ByteRange(first, rng.randrange(first, size)))
        content_type = rng.choice(MEDIA)
        body = hr.build_multipart_byteranges(data, ranges, content_type=content_type)
        head = f"Content-Type: {body.content_type}\r\n\r\n".encode("ascii")
        # compat32 keeps the header text as received.
        message = email.message_from_bytes(head + body.body, policy=email.policy.compat32)
        parts = message.get_payload()
        assert isinstance(parts, list) and len(parts) == len(ranges)
        for part, item in zip(parts, ranges, strict=True):
            assert part["Content-Range"] == item.content_range(size)
            assert part["Content-Type"] == content_type
            assert part.get_payload(decode=True) == data[item.as_slice()]
        checked += 1
    assert checked == 3000


def _instants(seed: int, low: int, high: int, count: int) -> list[datetime]:
    rng = random.Random(seed)
    start = datetime(low, 1, 1, tzinfo=timezone.utc)
    span = int((datetime(high, 12, 31, tzinfo=timezone.utc) - start).total_seconds())
    return [start + timedelta(seconds=rng.randrange(span)) for _ in range(count)]


def test_imf_fixdates_match_email_utils_both_ways() -> None:
    for instant in _instants(5322, 1000, 9999, 5000):
        text = email.utils.format_datetime(instant, usegmt=True)
        assert hr.format_http_date(instant) == text
        assert hr.parse_http_date(text) == instant == email.utils.parsedate_to_datetime(text)


def test_asctime_dates_match_time_asctime() -> None:
    for instant in _instants(1994, 1000, 9999, 5000):
        text = time.asctime(instant.timetuple())
        assert hr.parse_http_date(text) == instant
        assert email.utils.parsedate_to_datetime(text) == instant.replace(tzinfo=None)


def test_dates_match_http_cookiejar() -> None:
    for instant in _instants(6265, 1970, 9999, 5000):
        text = hr.format_http_date(instant)
        assert http2time(text) == instant.timestamp()
    # Two-digit years: http.cookiejar keeps them within 50 years of this year by year
    # number; the fifty-year rule compares instants, so stay clear of the edge.
    now = datetime.now(timezone.utc)
    for instant in _instants(850, now.year - 40, now.year + 40, 3000):
        text = instant.strftime("%A, %d-%b-%y %H:%M:%S GMT")
        assert hr.parse_http_date(text, now=now) == instant
        assert http2time(text) == instant.timestamp()


def test_each_reads_a_leap_second_its_own_way() -> None:
    text = "Sat, 31 Dec 2016 23:59:60 GMT"
    assert hr.parse_http_date(text) == datetime(2016, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    rollover = datetime(2017, 1, 1, tzinfo=timezone.utc)
    assert http2time(text) == rollover.timestamp()  # the next second
    try:
        email.utils.parsedate_to_datetime(text)
    except ValueError:
        pass  # second must be in 0..59
    else:
        raise AssertionError("email.utils accepted second 60")
