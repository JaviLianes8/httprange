"""multipart/byteranges against RFC 9110 14.6 / 15.3.7.2 and RFC 2046 5.1.1, from the text.

Sources (fetched 2026-10-18, sha256 in tests/upstream/MANIFEST.json):
https://www.rfc-editor.org/rfc/rfc9110.txt and https://www.rfc-editor.org/rfc/rfc2046.txt.
The example messages are cut from the text; only their placeholder lines ("...the
first range...") are replaced, by data of the size their Content-Range names.
"""

from __future__ import annotations

import re

import pytest
from conftest import section, upstream_text

import httprange as hr


def _example(body: str) -> tuple[str, bytes]:
    """The Content-Type and the CRLF body of the example message in ``body``."""
    start = body.index("   HTTP/1.1 206")
    end = body.index("--\n", body.index("--THIS_STRING_SEPARATES--", start)) + 2
    lines = [line[3:] for line in body[start:end].split("\n")]
    blank = lines.index("")
    content_type = next(line for line in lines[:blank] if line.startswith("Content-Type: "))
    return content_type.split(": ", 1)[1], "\r\n".join(lines[blank + 1 :]).encode("ascii")


def _fill(message: bytes, sizes: list[int]) -> bytes:
    placeholders = re.findall(rb"\.\.\.the \w+ range(?:\.\.\.)?", message)
    assert len(placeholders) == len(sizes)
    for placeholder, size in zip(placeholders, sizes, strict=True):
        message = message.replace(placeholder, b"x" * size, 1)
    return message


def test_the_multiple_parts_example_parses_and_is_what_the_builder_writes() -> None:
    body = section(upstream_text("rfc9110.txt"), "15.3.7.2", "Multiple Parts")
    content_type, message = _example(body)
    spans = [hr.parse_content_range(v) for v in re.findall(r"Content-Range: (.+)", body)]
    filled = _fill(message, [span.length or 0 for span in spans])
    parts = hr.parse_multipart_byteranges(filled, content_type)
    assert [part.content_range for part in parts] == spans
    media = re.findall(r"^   Content-Type: (\S+)$", body, flags=re.MULTILINE)
    assert len(media) == 2
    assert [part.content_type for part in parts] == media
    boundary = content_type.split("boundary=", 1)[1]
    total = spans[0].complete_length
    assert total is not None
    ranges = [hr.ByteRange(s.first or 0, s.last or 0) for s in spans]
    built = hr.build_multipart_byteranges(
        b"x" * total, ranges, content_type=media[0], boundary=boundary
    )
    assert built.content_type == content_type
    assert built.body == filled + b"\r\n"


def test_the_exampleunit_message_needs_integer_positions() -> None:
    body = section(upstream_text("rfc9110.txt"), "14.6", "Media Type multipart/byteranges")
    content_type, message = _example(body)
    # RFC 9110 14.4: first-pos and last-pos are 1*DIGIT, so "1.2-4.3" is not a valid range.
    with pytest.raises(hr.MalformedMultipart, match="Content-Range"):
        hr.parse_multipart_byteranges(_fill(message, [3, 3]), content_type)
    integral = re.sub(rb"(\d+)\.\d+-(\d+)\.\d+", rb"\1-\2", message)
    parts = hr.parse_multipart_byteranges(_fill(integral, [3, 3]), content_type)
    assert [str(part.content_range) for part in parts] == [
        "exampleunit 1-4/25",
        "exampleunit 11-14/25",
    ]
    # Implementation note 1: additional CRLFs might precede the first boundary.
    again = hr.parse_multipart_byteranges(b"\r\n\r\n" + _fill(integral, [3, 3]), content_type)
    assert again == parts
    assert "1.  Additional CRLFs might precede the first boundary string" in body


def _bchars() -> tuple[set[str], set[str]]:
    text = upstream_text("rfc2046.txt")
    grammar = text[text.index("bcharsnospace :=") : text.index("Overall, the body")]
    chars = set(re.findall(r'"(.)"', grammar))
    assert "DIGIT / ALPHA" in grammar and 'bchars := bcharsnospace / " "' in text
    letters = {chr(c) for c in range(0x30, 0x3A)} | {chr(c) for c in range(0x41, 0x5B)}
    chars |= letters | {c.lower() for c in letters}
    return chars, chars | {" "}


def _tchars() -> set[str]:
    """RFC 9110 5.6.2 tchar, read from the collected ABNF."""
    text = upstream_text("rfc9110.txt")
    rule = text[text.index("   tchar = ") : text.index("   time-of-day = ")]
    assert "DIGIT / ALPHA" in rule
    letters = {chr(c) for c in range(0x30, 0x3A)} | {chr(c) for c in range(0x41, 0x5B)}
    return set(re.findall(r'"(.)"', rule)) | letters | {c.lower() for c in letters}


def _received(boundary: str) -> tuple[bytes, str]:
    quoted = boundary.replace("\\", "\\\\").replace('"', '\\"')
    body = f"--{boundary}\r\nContent-Range: bytes 0-0/1\r\n\r\nz\r\n--{boundary}--\r\n"
    return body.encode("latin-1"), f'multipart/byteranges; boundary="{quoted}"'


@pytest.mark.parametrize("code", range(256))
def test_a_received_boundary_may_use_exactly_the_rfc_2046_bchars(code: int) -> None:
    nospace, bchars = _bchars()
    boundary = "a" + chr(code) + "b"
    body, content_type = _received(boundary)
    if chr(code) in bchars:
        assert hr.parse_multipart_byteranges(body, content_type)[0].data == b"z"
    else:
        with pytest.raises(hr.MalformedMultipart):
            hr.parse_multipart_byteranges(body, content_type)
    # A built boundary is never quoted (RFC 9110 14.6 note 2), so it is a token too.
    built = chr(code) in nospace & _tchars()
    data, ranges = b"0123456789", [hr.ByteRange(0, 0), hr.ByteRange(9, 9)]
    if built:
        assert hr.build_multipart_byteranges(data, ranges, boundary=boundary).boundary == boundary
    else:
        with pytest.raises(hr.MalformedMultipart):
            hr.build_multipart_byteranges(data, ranges, boundary=boundary)


def test_a_boundary_has_one_to_seventy_characters_and_no_trailing_space() -> None:
    text = upstream_text("rfc2046.txt")
    assert "consists of 1 to 70 characters" in " ".join(text.split())
    for size, valid in ((1, True), (70, True), (71, False)):
        body, content_type = _received("b" * size)
        if valid:
            assert hr.parse_multipart_byteranges(body, content_type)
        else:
            with pytest.raises(hr.MalformedMultipart):
                hr.parse_multipart_byteranges(body, content_type)
    with pytest.raises(hr.MalformedMultipart):
        hr.parse_multipart_byteranges(*_received("ends with space "))


def test_transport_padding_preamble_and_epilogue_follow_the_rfc_2046_body_grammar() -> None:
    text = upstream_text("rfc2046.txt")
    assert "transport-padding := *LWSP-char" in text
    body = b"preamble\r\n--b \t \r\nContent-Range: bytes 0-0/1\r\n\r\nz\r\n--b-- \t\r\nepilogue"
    assert hr.parse_multipart_byteranges(body, "multipart/byteranges; boundary=b")[0].data == b"z"
