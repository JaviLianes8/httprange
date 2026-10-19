"""Pins for the wire formats and the command line: Content-Range and part field rules,
Content-Type parameters, optional whitespace, the check order of resolve_ranges and the
tool's output under the smallest integer digit limit. Each runs in the default gate."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest

import httprange as hr
from httprange._cli import main

ONE_PART = b"--B\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--B--\r\n"
NINES = "9" * 4000


def test_a_content_range_unit_is_checked_before_it_is_lower_cased() -> None:
    with pytest.raises(hr.MalformedContentRange, match="not a token"):
        hr.ContentRange(chr(0x212A) + "bytes", 0, 0, 1)
    assert hr.ContentRange("BYTES", 0, 0, 1).unit == "bytes"


def test_a_range_never_fits_a_complete_length_of_zero() -> None:
    with pytest.raises(hr.RangeError, match="does not fit complete length 0"):
        hr.ByteRange(0, 0).content_range(0)
    assert hr.ByteRange(0, 0).content_range(1) == "bytes 0-0/1"


@pytest.mark.parametrize("unit", ["pages", "bytes"])
def test_a_part_needs_a_satisfied_content_range_in_any_unit(unit: str) -> None:
    with pytest.raises(hr.MalformedMultipart, match="needs a satisfied Content-Range"):
        hr.BytePart(hr.ContentRange(unit, None, None, 5), b"ab")
    assert hr.BytePart(hr.ContentRange("pages", 0, 0, 5), b"ab").data == b"ab"


@pytest.mark.parametrize("char", ["Ā", "€", "\U0001f600", "\x00", "\x7f", "\n"])
def test_a_part_content_type_refuses_characters_outside_a_field_value(char: str) -> None:
    span = hr.ContentRange("bytes", 0, 1, 5)
    with pytest.raises(hr.MalformedMultipart):
        hr.BytePart(span, b"ab", "text/" + char)
    with pytest.raises(hr.MalformedMultipart):
        hr.build_multipart_byteranges(b"abcde", [hr.ByteRange(0, 1)], content_type="a" + char)
    part = hr.BytePart(span, b"ab", "text/\xff")
    body = hr.encode_multipart_byteranges([part], boundary="B").body
    assert b"Content-Type: text/\xff\r\n" in body


@pytest.mark.parametrize(
    "params",
    ['; x="a\\\x01"', '; x="a\\\x7f"', "; x=", '; x="a\\\x00"', "; x= y", "; x=a b"],
)
def test_every_content_type_parameter_follows_the_grammar(params: str) -> None:
    with pytest.raises(hr.MalformedMultipart):
        hr.parse_multipart_byteranges(ONE_PART, "multipart/byteranges; boundary=B" + params)
    good = hr.parse_multipart_byteranges(ONE_PART, 'multipart/byteranges; boundary=B; x="a\\b"')
    assert good[0].data == b"ab"


def test_build_multipart_checks_the_content_type_before_the_ranges() -> None:
    for ranges in ([hr.ByteRange(0, 5)], 7):
        with pytest.raises(hr.MalformedMultipart, match="content_type must be a str"):
            hr.build_multipart_byteranges(b"ab", ranges, content_type=5)  # type: ignore[arg-type]


def test_resolve_ranges_checks_the_list_before_the_unit() -> None:
    for header in ("pages=a b", "pages=", "pages=\x01", "items=" + "," * 20 + "1"):
        with pytest.raises(hr.MalformedRange):
            hr.resolve_ranges(header, 10)
    with pytest.raises(hr.UnsupportedRangeUnit):
        hr.resolve_ranges("pages=a,b", 10)
    many = hr.RangePolicy(max_ranges=1)
    with pytest.raises(hr.ExcessiveRanges):
        hr.resolve_ranges("bytes=x,0-1", 10, policy=many)
    with pytest.raises(hr.UnsupportedRangeUnit):
        hr.resolve_ranges("pages=1,2", 10, policy=many)


@pytest.mark.parametrize("pad", [" ", "\t", " \t "])
def test_optional_whitespace_around_whole_values_is_ignored(pad: str) -> None:
    stamp = "Sun, 06 Nov 1994 08:49:37 GMT"
    moment = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
    assert hr.parse_http_date(pad + stamp + pad) == moment
    assert hr.parse_http_date(pad + "Sun Nov  6 08:49:37 1994" + pad) == moment
    assert hr.if_range_matches('"v1"', etag=pad + '"v1"' + pad)
    assert hr.if_range_matches(pad + '"v1"' + pad, etag='"v1"')
    assert str(hr.parse_content_range(pad + "bytes 0-1/2" + pad)) == "bytes 0-1/2"


def test_part_field_values_drop_spaces_and_tabs_and_names_must_be_tokens() -> None:
    head = b"--B\r\nContent-Type:\ttext/plain\t\r\nContent-Range: \tbytes 0-1/5 \r\n\r\nab"
    (part,) = hr.parse_multipart_byteranges(
        head + b"\r\n--B--\r\n", "multipart/byteranges; boundary=B"
    )
    assert part.content_type == "text/plain"
    assert str(part.content_range) == "bytes 0-1/5"
    for line in (b"Bad Name: x", b"Bad\tName: x", b"(x): y", b": y"):
        body = b"--B\r\n" + line + b"\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--B--\r\n"
        with pytest.raises(hr.MalformedMultipart):
            hr.parse_multipart_byteranges(body, "multipart/byteranges; boundary=B")


def test_cli_decide_passes_the_method(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["decide", "--method", "HEAD", "--range", "bytes=0-1", "--length", "10"]) == 0
    out, err = capsys.readouterr()
    assert (out.splitlines(), err) == (["status: 200", "reason: Range is ignored for HEAD"], "")
    assert main(["decide", "--range", "bytes=0-1", "--length", "10"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "status: 206"


@pytest.fixture
def low_limit() -> Iterator[None]:
    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("no digit limit before CPython 3.11")
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


@pytest.mark.usefixtures("low_limit")
def test_cli_text_and_json_print_wide_numbers_under_the_digit_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["parse-content-range", "bytes 0-" + NINES + "/*"]) == 0
    assert "last: " + NINES in capsys.readouterr().out.splitlines()
    assert main(["parse-content-range", "bytes 0-" + NINES + "/*", "--json"]) == 0
    assert '"last": ' + NINES + "," in capsys.readouterr().out
    first = NINES[:-1]
    assert main(["resolve", "bytes=" + first + "-", "--length", NINES, "--json"]) == 0
    assert f'"ranges": [[{first}, {first}8]]' in capsys.readouterr().out
    assert main(["decide", "--range", "bytes=" + first + "-", "--length", NINES, "--json"]) == 0
    assert f'"ranges": [[{first}, {first}8]]' in capsys.readouterr().out
