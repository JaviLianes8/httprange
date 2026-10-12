from datetime import datetime, timedelta, timezone

import pytest

from httprange import MalformedDate, RangeError, format_http_date, if_range_matches, parse_http_date

INSTANT = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    [
        # RFC 9110 5.6.7: the three formats a recipient MUST accept.
        "Sun, 06 Nov 1994 08:49:37 GMT",
        "Sunday, 06-Nov-94 08:49:37 GMT",
        "Sun Nov  6 08:49:37 1994",
    ],
)
def test_parses_all_three_http_date_formats(value: str) -> None:
    assert parse_http_date(value, now=NOW) == INSTANT


def test_two_digit_years_follow_the_fifty_year_rule() -> None:
    assert parse_http_date("Monday, 01-Jan-30 00:00:00 GMT", now=NOW).year == 2030
    assert parse_http_date("Monday, 01-Jan-76 00:00:00 GMT", now=NOW).year == 2076
    assert parse_http_date("Monday, 01-Jan-77 00:00:00 GMT", now=NOW).year == 1977
    assert parse_http_date("Friday, 01-Jan-77 00:00:00 GMT").tzinfo is timezone.utc


def test_leap_second_is_read_as_fifty_nine() -> None:
    assert parse_http_date("Sat, 31 Dec 2016 23:59:60 GMT").second == 59


@pytest.mark.parametrize(
    "value",
    [
        "Sun, 6 Nov 1994 08:49:37 GMT",
        "Sun, 06 Nov 1994 08:49:37 UTC",
        "sun, 06 nov 1994 08:49:37 GMT",
        "Sun, 31 Feb 1994 08:49:37 GMT",
        "Sun, 06 Nov 1994 25:49:37 GMT",
        "1994-11-06T08:49:37Z",
        "Sun, \u0660\u0666 Nov 1994 08:49:37 GMT",
        "",
    ],
)
def test_rejects_anything_else(value: str) -> None:
    with pytest.raises(MalformedDate):
        parse_http_date(value)


def test_formats_imf_fixdate() -> None:
    assert format_http_date(INSTANT) == "Sun, 06 Nov 1994 08:49:37 GMT"
    madrid = INSTANT.astimezone(timezone(timedelta(hours=1)))
    assert format_http_date(madrid) == "Sun, 06 Nov 1994 08:49:37 GMT"
    with pytest.raises(RangeError):
        format_http_date(datetime(1994, 11, 6))


def test_entity_tags_use_strong_comparison() -> None:
    # RFC 9110 8.8.3.2, table 3, strong column.
    assert if_range_matches('"1"', etag='"1"')
    assert not if_range_matches('W/"1"', etag='W/"1"')
    assert not if_range_matches('W/"1"', etag='"1"')
    assert not if_range_matches('"1"', etag='W/"1"')
    assert not if_range_matches('"1"', etag='"2"')
    assert not if_range_matches('"1"', etag=None)
    assert not if_range_matches('"1"', last_modified=INSTANT)
    assert if_range_matches('""', etag='""')


def test_malformed_entity_tags_never_match() -> None:
    assert not if_range_matches('"a b"', etag='"a b"')
    assert not if_range_matches('"open', etag='"open')


def test_dates_must_match_exactly() -> None:
    header = "Sun, 06 Nov 1994 08:49:37 GMT"
    assert if_range_matches(header, last_modified=INSTANT)
    assert if_range_matches(header, last_modified=INSTANT.replace(microsecond=500))
    assert if_range_matches(header, last_modified="Sunday, 06-Nov-94 08:49:37 GMT")
    later = INSTANT + timedelta(seconds=1)
    assert not if_range_matches(header, last_modified=later)
    assert not if_range_matches(format_http_date(later), last_modified=INSTANT)
    assert not if_range_matches(header, etag='"x"')


def test_weak_dates_and_malformed_dates_never_match() -> None:
    header = "Sun, 06 Nov 1994 08:49:37 GMT"
    assert not if_range_matches(header, last_modified=INSTANT, date_is_strong=False)
    assert not if_range_matches("yesterday", last_modified=INSTANT)
    assert not if_range_matches(header, last_modified="not a date")


def test_seconds_past_sixty_are_rejected() -> None:
    with pytest.raises(MalformedDate):
        parse_http_date("Sun, 06 Nov 1994 08:49:61 GMT")


def test_fifty_year_rule_compares_full_dates() -> None:
    new_year = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_http_date("Thursday, 31-Dec-76 00:00:00 GMT", now=new_year).year == 1976
    assert parse_http_date("Thursday, 01-Jan-76 00:00:00 GMT", now=new_year).year == 2076
    leap = datetime(2028, 2, 29, tzinfo=timezone.utc)
    assert parse_http_date("Monday, 28-Feb-78 00:00:00 GMT", now=leap).year == 2078
    with pytest.raises(RangeError):
        parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT", now=datetime(2026, 1, 1))
