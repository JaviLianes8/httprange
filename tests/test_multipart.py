import pytest

from httprange import (
    BytePart,
    ByteRange,
    ContentRange,
    MalformedMultipart,
    RangeError,
    build_multipart_byteranges,
    encode_multipart_byteranges,
    parse_multipart_byteranges,
)

DATA = (bytes(range(256)) * 32)[:8000]  # 8000 bytes, as in RFC 9110 15.3.7.2
CT = "multipart/byteranges; boundary=THIS_STRING_SEPARATES"


def test_builds_the_rfc_example_layout() -> None:
    ranges = [ByteRange(500, 999), ByteRange(7000, 7999)]
    body = build_multipart_byteranges(
        DATA, ranges, content_type="application/pdf", boundary="THIS_STRING_SEPARATES"
    )
    assert body.content_type == CT
    assert body.boundary == "THIS_STRING_SEPARATES"
    expected = (
        b"--THIS_STRING_SEPARATES\r\nContent-Type: application/pdf\r\n"
        b"Content-Range: bytes 500-999/8000\r\n\r\n" + DATA[500:1000] + b"\r\n"
        b"--THIS_STRING_SEPARATES\r\nContent-Type: application/pdf\r\n"
        b"Content-Range: bytes 7000-7999/8000\r\n\r\n" + DATA[7000:8000] + b"\r\n"
        b"--THIS_STRING_SEPARATES--\r\n"
    )
    assert body.body == expected
    assert body.content_length == len(expected)


def test_round_trips_with_a_generated_boundary() -> None:
    ranges = [ByteRange(7000, 7999), ByteRange(0, 0)]
    body = build_multipart_byteranges(DATA, ranges)
    parts = parse_multipart_byteranges(body.body, body.content_type)
    assert [part.data for part in parts] == [DATA[7000:8000], DATA[0:1]]
    assert [str(part.content_range) for part in parts] == [
        "bytes 7000-7999/8000",
        "bytes 0-0/8000",
    ]
    assert parts[0].content_type is None


def test_generated_boundary_never_occurs_in_the_data() -> None:
    body = build_multipart_byteranges(b"--" + b"a" * 10, [ByteRange(0, 11)])
    assert body.body.count(b"--" + body.boundary.encode()) == 2


def test_rejects_a_given_boundary_found_in_a_part() -> None:
    with pytest.raises(MalformedMultipart):
        build_multipart_byteranges(b"x--abc", [ByteRange(0, 5)], boundary="abc")


@pytest.mark.parametrize("boundary", ["", "a" * 71, "has space", 'q"uote', "semi;colon"])
def test_rejects_unsafe_boundaries(boundary: str) -> None:
    with pytest.raises(MalformedMultipart):
        build_multipart_byteranges(DATA, [ByteRange(0, 1)], boundary=boundary)


def test_rejects_header_injection_and_bad_input() -> None:
    with pytest.raises(MalformedMultipart):
        build_multipart_byteranges(DATA, [ByteRange(0, 1)], content_type="text/x\r\nX: y")
    with pytest.raises(RangeError):
        build_multipart_byteranges(b"abc", [ByteRange(0, 3)])
    with pytest.raises(MalformedMultipart):
        encode_multipart_byteranges([])


def test_encodes_other_units() -> None:
    part = BytePart(ContentRange("exampleunit", 1, 4, 25), b"first", "video/example")
    body = encode_multipart_byteranges([part], boundary="B")
    assert b"Content-Range: exampleunit 1-4/25\r\n" in body.body
    assert parse_multipart_byteranges(body.body, body.content_type) == (part,)


def test_parses_preamble_padding_quoted_boundary_and_epilogue() -> None:
    body = (
        b"\r\n\r\nignored preamble\r\n--sep \t\r\n"
        b"content-range: bytes 0-2/10\r\nCONTENT-TYPE: text/plain\r\n\r\nabc\r\n"
        b"--sep\r\n\r\ndef\r\n--sep--\r\ntrailing epilogue"
    )
    with pytest.raises(MalformedMultipart):
        parse_multipart_byteranges(body, 'multipart/byteranges; boundary="sep"')
    fixed = body.replace(b"\r\n\r\ndef", b"\r\nContent-Range: bytes 3-5/10\r\n\r\ndef")
    parts = parse_multipart_byteranges(fixed, 'Multipart/ByteRanges; charset=x; boundary="sep"')
    assert [(part.data, part.content_type) for part in parts] == [
        (b"abc", "text/plain"),
        (b"def", None),
    ]


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"--B\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--B--", "text/plain; boundary=B"),
        (b"--B\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--B--", "multipart/byteranges"),
        (b"--B\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n", "multipart/byteranges; boundary=B"),
        (
            b"--B\r\nContent-Range: bytes 0-2/5\r\n\r\nab\r\n--B--",
            "multipart/byteranges; boundary=B",
        ),
        (b"--B\r\nContent-Range: bytes */5\r\n\r\nab\r\n--B--", "multipart/byteranges; boundary=B"),
        (b"--B\r\nContent-Range: nonsense\r\n\r\nab\r\n--B--", "multipart/byteranges; boundary=B"),
        (b"--B\r\nX-Other: 1\r\n\r\nab\r\n--B--", "multipart/byteranges; boundary=B"),
        (b"--B\r\nbroken header\r\n\r\nab\r\n--B--", "multipart/byteranges; boundary=B"),
        (b"--B\r\nContent-Range: bytes 0-1/5\r\nab\r\n--B--", "multipart/byteranges; boundary=B"),
        (
            b"--Bx\r\nContent-Range: bytes 0-1/5\r\n\r\nab\r\n--B--",
            "multipart/byteranges; boundary=B",
        ),
        (b"--B--\r\n", "multipart/byteranges; boundary=B"),
        (b"--B\r\n\r\nab\r\n--B--", 'multipart/byteranges; boundary="B'),
    ],
)
def test_rejects_broken_bodies(body: bytes, content_type: str) -> None:
    with pytest.raises(MalformedMultipart):
        parse_multipart_byteranges(body, content_type)


def test_caps_the_number_of_parts() -> None:
    parts = [ByteRange(i, i) for i in range(5)]
    body = build_multipart_byteranges(DATA, parts)
    with pytest.raises(MalformedMultipart):
        parse_multipart_byteranges(body.body, body.content_type, max_parts=4)
    assert len(parse_multipart_byteranges(body.body, body.content_type, max_parts=5)) == 5
