"""HTTP-dates, entity-tag comparison, If-Range and erratum 7306, read from the fetched text.

Sources (fetched 2026-10-18, sha256 in tests/upstream/MANIFEST.json):
https://www.rfc-editor.org/rfc/rfc9110.txt and https://www.rfc-editor.org/errata/eid7306.
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone

import pytest
from conftest import section, upstream_prose, upstream_text

import httprange as hr

RFC = "rfc9110.txt"


def _dates() -> list[tuple[str, str]]:
    body = section(upstream_text(RFC), "5.6.7", "Date/Time Formats")
    kinds = r"(IMF-fixdate|obsolete RFC 850 format|ANSI C's)"
    return re.findall(rf"^     (\S.*?\S) +; {kinds}", body, re.MULTILINE)


def test_the_three_example_dates_are_the_same_instant() -> None:
    examples = _dates()
    assert [kind for _, kind in examples] == ["IMF-fixdate", "obsolete RFC 850 format", "ANSI C's"]
    instants = {hr.parse_http_date(text) for text, _ in examples}
    assert len(instants) == 1
    assert hr.format_http_date(instants.pop()) == examples[0][0]


def test_http_dates_are_case_sensitive_and_take_no_extra_whitespace() -> None:
    body = section(upstream_text(RFC), "5.6.7", "Date/Time Formats")
    assert "HTTP-date is case sensitive." in body
    for text, _ in _dates():
        for variant in (text.lower(), text.upper(), text.replace(" ", "  ", 1)):
            with pytest.raises(hr.MalformedDate):
                hr.parse_http_date(variant)


def test_time_of_day_runs_from_midnight_to_the_leap_second() -> None:
    body = section(upstream_text(RFC), "5.6.7", "Date/Time Formats")
    low, high = re.search(r"; (\d\d:\d\d:\d\d) - (\d\d:\d\d:\d\d) \(leap second\)", body).groups()  # type: ignore[union-attr]
    assert hr.parse_http_date(f"Sun, 06 Nov 1994 {low} GMT").hour == 0
    assert hr.parse_http_date(f"Sun, 06 Nov 1994 {high} GMT").second == 59
    for wrong in ("24:00:00", "23:60:00", "23:59:61"):
        with pytest.raises(hr.MalformedDate):
            hr.parse_http_date(f"Sun, 06 Nov 1994 {wrong} GMT")


def test_two_digit_years_follow_the_fifty_year_rule() -> None:
    body = " ".join(section(upstream_text(RFC), "5.6.7", "Date/Time Formats").split())
    rule = "MUST interpret a timestamp that appears to be more than 50 years in the future"
    assert rule in body
    rng = random.Random(5067)
    for _ in range(3000):
        now = datetime(rng.randrange(1, 9940), 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=rng.randrange(366 * 86400)
        )
        ahead = _fifty_years_after(now)
        month, day, digits = rng.randrange(1, 13), rng.randrange(1, 29), rng.randrange(100)
        stamp = datetime(2001, month, day, 12, tzinfo=timezone.utc)
        text = f"{stamp:%A}, {stamp:%d-%b}-{digits:02d} 12:00:00 GMT"
        try:
            got = hr.parse_http_date(text, now=now)
        except hr.MalformedDate:
            # Only when every year with these digits, from year 1 on, is too far ahead.
            assert stamp.replace(year=digits or 100) > ahead
            continue
        assert (got.year % 100, got.month, got.day) == (digits, month, day)
        assert got <= ahead  # not more than 50 years in the future
        if got.year + 100 <= 9999:
            assert got.replace(year=got.year + 100) > ahead  # the most recent such year


def _fifty_years_after(now: datetime) -> datetime:
    try:
        return now.replace(year=now.year + 50)
    except ValueError:  # 29 February
        return now.replace(year=now.year + 50, day=28)


def test_the_strong_comparison_column_of_table_3() -> None:
    body = section(upstream_text(RFC), "8.8.3.2", "Comparison")
    rows = re.findall(r"^   \| (\S+) +\| (\S+) +\| (no match|match) +\|", body, re.M)
    assert len(rows) == 4
    for first, second, strong in rows:
        assert hr.if_range_matches(first, etag=second) is (strong == "match"), (first, second)


def test_if_range_tells_an_entity_tag_from_a_date_by_the_first_three_characters() -> None:
    body = " ".join(section(upstream_text(RFC), "13.1.5", "If-Range").split())
    assert "examining the first three characters for a DQUOTE" in body
    stamp = "Sun, 06 Nov 1994 08:49:37 GMT"
    assert hr.if_range_matches(stamp, last_modified=stamp)
    for value in ('"a"', 'W/"a"', ' "a"'):
        assert not hr.if_range_matches(value, last_modified=stamp)
    assert not hr.if_range_matches(stamp, etag=stamp)


def test_if_range_dates_follow_the_three_steps() -> None:
    body = " ".join(section(upstream_text(RFC), "13.1.5", "If-Range").split())
    assert "If the HTTP-date validator provided is not a strong validator" in body
    assert "exactly matches the Last-Modified field value" in body
    stamp = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    value = hr.format_http_date(stamp)
    assert not hr.if_range_matches(value, last_modified=stamp, date_is_strong=False)
    assert hr.if_range_matches(value, last_modified=stamp)
    assert not hr.if_range_matches(value, last_modified=stamp + timedelta(seconds=1))


def test_erratum_7306_allows_whitespace_after_the_equals_sign() -> None:
    prose = upstream_prose("rfc9110-erratum-7306.html")
    assert 'It should say: ranges-specifier = range-unit "=" OWS range-set' in prose
    assert "Status: Verified" in prose
    example = re.search(r"given in 14\.1\.2 (bytes=.+?) The bug", prose)
    assert example is not None
    assert str(hr.parse_range_request(example[1])) == "bytes=0-999,4500-5499,-1000"
    for value in ("bytes=\t0-1", "bytes= \t 0-1"):
        assert hr.parse_range_request(value).specs == (hr.RangeSpec(0, 1),)
