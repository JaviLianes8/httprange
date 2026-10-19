"""Edge contracts that hold without any fetched source: wide numbers, limits, multipart.

Every case here is written by hand from the RFC 9110 grammar; none is copied from an
upstream file.
"""

from __future__ import annotations

import json
import secrets

import pytest

import httprange as hr
from httprange._cli import main

# Runs of zeros inside numbers wider than one 600-digit conversion chunk.
WIDE = [10**600 + 5, 10**1300 + 10**610 + 7, 7 * 10**1799, 10**3999 - 10**1200]


@pytest.mark.parametrize("number", WIDE, ids=lambda n: f"{len(str(n))}-digits")
def test_wide_numbers_print_and_parse_exactly(number: int) -> None:
    text = str(number)
    assert hr.build_content_range(0, number, None) == f"bytes 0-{text}/*"
    assert hr.build_content_range(1, number - 1, number) == f"bytes 1-{number - 1}/{text}"
    assert str(hr.RangeSpec(0, number)) == f"0-{text}"
    assert str(hr.ByteRange(number, number)) == f"{text}-{text}"
    assert hr.parse_range_request(f"bytes=0-{text}").specs == (hr.RangeSpec(0, number),)
    assert hr.parse_content_range(f"bytes 0-0/{text}").complete_length == number


@pytest.mark.parametrize("number", WIDE, ids=lambda n: f"{len(str(n))}-digits")
def test_wide_numbers_survive_the_cli_json(capsys: pytest.CaptureFixture[str], number: int) -> None:
    assert main(["resolve", "bytes=-1", "--length", str(number), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ranges"] == [[number - 1, number - 1]]
    assert data["content_range"] == [f"bytes {number - 1}-{number - 1}/{number}"]


def test_the_digit_cap_counts_significant_digits_only() -> None:
    zeros = "0" * 5000
    assert hr.parse_range_request(f"bytes={zeros}1-").specs == (hr.RangeSpec(1, None),)
    assert hr.parse_content_range(f"bytes 0-0/{zeros}1").complete_length == 1
    assert hr.parse_range_request("bytes=" + "9" * 4000 + "-").specs[0].start == 10**4000 - 1
    with pytest.raises(hr.MalformedRange, match="4000 significant digits"):
        hr.parse_range_request(f"bytes={zeros}{'1' * 4001}-")


def test_a_decision_range_must_end_before_the_length() -> None:
    assert hr.RangeDecision(206, (hr.ByteRange(0, 9),), 10, "r").content_range == "bytes 0-9/10"
    with pytest.raises(hr.RangeError, match="past the length 10"):
        hr.RangeDecision(206, (hr.ByteRange(0, 10),), 10, "r")


def test_a_quoted_boundary_unescapes_its_quoted_pairs() -> None:
    body = b"--ab\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--ab--\r\n"
    (part,) = hr.parse_multipart_byteranges(body, 'multipart/byteranges; boundary="a\\b"')
    assert part.data == b"ab"


@pytest.mark.parametrize("value", ["text/pl\x7fain", "text/plain\x00", "text/plain\n"])
def test_control_characters_and_del_are_refused_in_a_part_content_type(value: str) -> None:
    span = hr.ContentRange("bytes", 0, 1, 5)
    with pytest.raises(hr.MalformedMultipart, match="invalid header field value"):
        hr.BytePart(span, b"ab", value)
    with pytest.raises(hr.MalformedMultipart, match="invalid header field value"):
        hr.build_multipart_byteranges(b"abcde", [hr.ByteRange(0, 1)], content_type=value)


def test_a_random_boundary_that_collides_with_the_data_is_drawn_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = iter(["c" * 32, "1" * 32])
    monkeypatch.setattr(secrets, "token_hex", lambda size: next(tokens))
    data = b"xx--" + b"c" * 32 + b"yy"
    ranges = [hr.ByteRange(0, len(data) - 1), hr.ByteRange(0, 0)]
    body = hr.build_multipart_byteranges(data, ranges)
    assert body.boundary == "1" * 32
    parts = hr.parse_multipart_byteranges(body.body, body.content_type)
    assert [part.data for part in parts] == [data, b"x"]


def test_a_range_past_the_data_raises_the_base_error() -> None:
    with pytest.raises(hr.RangeError) as info:
        hr.build_multipart_byteranges(b"abc", [hr.ByteRange(0, 5)])
    assert type(info.value) is hr.RangeError
    assert str(info.value) == "range '0-5' exceeds data of length 3"


@pytest.mark.parametrize("value", ["bytes\t0-1/2", "bytes\t*/2", "bytes  0-1/2"])
def test_content_range_needs_one_space_after_the_unit(value: str) -> None:
    with pytest.raises(hr.MalformedContentRange):
        hr.parse_content_range(value)


def test_obs_text_entity_tags_match_by_strong_comparison() -> None:
    assert hr.if_range_matches('"caf\xe9"', etag='"caf\xe9"')
    assert not hr.if_range_matches('"caf\xe9"', etag='"cafe"')
    assert not hr.if_range_matches('"cafĀ"', etag='"cafĀ"')


def _part(unit: str, extra: bytes = b"") -> bytes:
    return b"--b\r\n" + extra + f"Content-Range: {unit} 0-1/5\r\n\r\nab\r\n".encode()


def test_parts_must_agree_on_the_range_unit() -> None:
    body = _part("bytes") + _part("items") + b"--b--\r\n"
    with pytest.raises(hr.MalformedMultipart, match="range unit"):
        hr.parse_multipart_byteranges(body, "multipart/byteranges; boundary=b")
    parts = [
        hr.BytePart(hr.ContentRange("bytes", 0, 1, 5), b"ab"),
        hr.BytePart(hr.ContentRange("items", 0, 1, 5), b"ab"),
    ]
    with pytest.raises(hr.MalformedMultipart, match="range unit"):
        hr.encode_multipart_byteranges(parts, boundary="b")


def test_a_part_with_two_content_types_is_refused() -> None:
    twice = b"Content-Type: text/plain\r\ncontent-type: text/html\r\n"
    body = _part("bytes", twice) + b"--b--\r\n"
    with pytest.raises(hr.MalformedMultipart, match="more than one content-type"):
        hr.parse_multipart_byteranges(body, "multipart/byteranges; boundary=b")


@pytest.mark.parametrize(
    ("content_type", "message"),
    [
        ('multipart/byteranges; boundary="b "', "invalid multipart boundary"),
        ("multipart/byteranges; boundary=b; boundary=c", "more than one boundary"),
        ("multipart/byteranges; boundary=b; BOUNDARY=b", "more than one boundary"),
    ],
)
def test_bad_boundary_parameters_are_refused(content_type: str, message: str) -> None:
    body = _part("bytes") + b"--b--\r\n"
    with pytest.raises(hr.MalformedMultipart, match=message):
        hr.parse_multipart_byteranges(body, content_type)
    # Framed with the trailing space too, so only the parameter check can refuse it.
    trailing = b"--b \r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--b --\r\n"
    with pytest.raises(hr.MalformedMultipart, match=message):
        hr.parse_multipart_byteranges(trailing, content_type)
