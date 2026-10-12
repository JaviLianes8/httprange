"""Real end to end test: a local HTTP server built on the library, fetched with urllib.

No mocks. A threaded ``http.server`` serves a file from disk, deciding every response
with :func:`httprange.evaluate_range_request`. Requests go over a real socket through
``urllib`` with real ``Range`` and ``If-Range`` headers, and the assertions check the
status codes, the headers and the exact bytes received.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from email.message import Message

import pytest
from range_server import CONTENT, ETAG, LAST_MODIFIED

import httprange as hr


def fetch(url: str, **headers: str) -> tuple[int, Message, bytes]:
    request = urllib.request.Request(
        url, headers={k.replace("_", "-"): v for k, v in headers.items()}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.headers, error.read()


def test_no_range_gives_the_whole_file(base_url: str) -> None:
    status, headers, body = fetch(base_url)
    assert (status, body) == (200, CONTENT)
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["Content-Range"] is None


@pytest.mark.parametrize(
    ("range_header", "first", "last"),
    [
        ("bytes=0-499", 0, 499),
        ("bytes=500-999", 500, 999),
        ("bytes=-500", 9500, 9999),
        ("bytes=9500-", 9500, 9999),
        ("bytes=0-", 0, 9999),
        ("bytes=9000-20000", 9000, 9999),
        ("Bytes=500-600,601-999", 500, 999),
    ],
)
def test_single_ranges_give_206_and_exact_bytes(
    base_url: str, range_header: str, first: int, last: int
) -> None:
    status, headers, body = fetch(base_url, Range=range_header)
    assert status == 206
    assert headers["Content-Range"] == f"bytes {first}-{last}/10000"
    assert body == CONTENT[first : last + 1]
    assert int(headers["Content-Length"]) == last - first + 1


def test_multiple_ranges_give_a_multipart_206(base_url: str) -> None:
    status, headers, body = fetch(base_url, Range="bytes=0-0,-1")
    assert status == 206
    assert headers["Content-Range"] is None
    parts = hr.parse_multipart_byteranges(body, headers["Content-Type"])
    assert [str(part.content_range) for part in parts] == [
        "bytes 0-0/10000",
        "bytes 9999-9999/10000",
    ]
    assert [part.data for part in parts] == [CONTENT[:1], CONTENT[-1:]]


def test_three_ranges_arrive_in_request_order(base_url: str) -> None:
    status, headers, body = fetch(base_url, Range="bytes= 4500-5499, 0-999, -1000")
    parts = hr.parse_multipart_byteranges(body, headers["Content-Type"])
    assert status == 206
    assert [part.data for part in parts] == [CONTENT[4500:5500], CONTENT[:1000], CONTENT[9000:]]


@pytest.mark.parametrize("range_header", ["bytes=10000-", "bytes=20000-30000", "bytes=-0"])
def test_unsatisfiable_ranges_give_416(base_url: str, range_header: str) -> None:
    status, headers, body = fetch(base_url, Range=range_header)
    assert (status, body) == (416, b"")
    assert headers["Content-Range"] == "bytes */10000"


def test_excessive_overlap_gives_416(base_url: str) -> None:
    status, headers, _ = fetch(base_url, Range="bytes=0-0,0-0,0-0")
    assert (status, headers["Content-Range"]) == (416, "bytes */10000")


@pytest.mark.parametrize("range_header", ["bytes=abc", "items=0-1", "bytes=5-1", "bytes 0-1"])
def test_invalid_or_unknown_ranges_give_the_whole_file(base_url: str, range_header: str) -> None:
    status, _, body = fetch(base_url, Range=range_header)
    assert (status, body) == (200, CONTENT)


def test_if_range_controls_partial_delivery(base_url: str) -> None:
    assert fetch(base_url, Range="bytes=0-9", If_Range=ETAG)[0] == 206
    assert fetch(base_url, Range="bytes=0-9", If_Range=LAST_MODIFIED)[0] == 206
    status, _, body = fetch(base_url, Range="bytes=0-9", If_Range='"stale"')
    assert (status, body) == (200, CONTENT)
    assert fetch(base_url, Range="bytes=0-9", If_Range='W/"v1"')[0] == 200


def test_resuming_a_download_rebuilds_the_file(base_url: str) -> None:
    received = b""
    while len(received) < len(CONTENT):
        end = len(received) + 2999
        status, headers, body = fetch(base_url, Range=f"bytes={len(received)}-{end}", If_Range=ETAG)
        assert status == 206
        span = hr.parse_content_range(headers["Content-Range"])
        assert span.first == len(received) and span.complete_length == len(CONTENT)
        received += body
    assert received == CONTENT
