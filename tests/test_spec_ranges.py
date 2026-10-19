"""RFC 9110 section 14 and 15.3.7 / 15.5.17, read from the fetched text.

Every example header and every expected offset is cut from tests/upstream/rfc9110.txt
(https://www.rfc-editor.org/rfc/rfc9110.txt, fetched 2026-10-18, sha256 in the
manifest), never typed in by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from conftest import section, upstream_text

import httprange as hr

RFC = "rfc9110.txt"


def _bullets(body: str) -> list[str]:
    return re.split(r"\n   \*  ", body)[1:]


def _examples(text: str, prefix: str) -> list[str]:
    return re.findall(rf"^ +({re.escape(prefix)}.+?) *$", text, flags=re.MULTILINE)


def test_byte_range_examples_resolve_to_the_offsets_the_rfc_states() -> None:
    body = section(upstream_text(RFC), "14.1.2", "Byte Ranges")
    length = int(re.search(r"assuming a representation of length (\d+)", body)[1])  # type: ignore[index]
    checked = 0
    for bullet in _bullets(body):
        headers = _examples(bullet, "bytes=")
        offsets = re.search(r"byte offsets (\d+)-(\d+), inclusive", bullet)
        ends = re.search(r"\(bytes (\d+) and (\d+)\)", bullet)
        thirds = re.search(r"The first, middle, and last (\d+) bytes", bullet)
        for header in headers:
            ranges = hr.resolve_ranges(header, length)
            if offsets:
                assert ranges == (hr.ByteRange(int(offsets[1]), int(offsets[2])),), header
            elif ends:
                assert ranges == tuple(hr.ByteRange(int(n), int(n)) for n in ends.groups())
            else:
                assert thirds, bullet
                size = int(thirds[1])
                first, middle, last = ranges
                assert [item.length for item in ranges] == [size] * 3
                assert (first.first, last.last) == (0, length - 1)
                assert middle.first + middle.last == length - 1  # centred
            checked += 1
    assert checked == 8


def test_content_range_examples_parse_build_and_mean_what_the_rfc_says() -> None:
    body = section(upstream_text(RFC), "14.4", "Content-Range")
    values = _examples(body, "Content-Range: ")
    assert len(values) == 7
    for line in values:
        value = line.split(": ", 1)[1]
        parsed = hr.parse_content_range(value)
        assert str(parsed) == value
        assert hr.build_content_range(parsed.first, parsed.last, parsed.complete_length) == value
    known = int(re.search(r"known by the sender to be (\d+) bytes", body)[1])  # type: ignore[index]
    assert hr.parse_content_range(values[0].split(": ")[1]).complete_length == known
    assert hr.parse_content_range(values[1].split(": ")[1]).complete_length is None
    assert not hr.parse_content_range(values[2].split(": ")[1]).is_satisfied
    total = int(re.search(r"contains a total of (\d+) bytes", body)[1])  # type: ignore[index]
    meanings: dict[str, Callable[[int], tuple[int, int]]] = {
        r"The first (\d+) bytes": lambda n: (0, n - 1),
        r"The second (\d+) bytes": lambda n: (n, 2 * n - 1),
        r"All except for the first (\d+) bytes": lambda n: (n, total - 1),
        r"The last (\d+) bytes": lambda n: (total - n, total - 1),
    }
    bullets = _bullets(body)
    assert len(bullets) == 4
    for bullet in bullets:
        span = hr.parse_content_range(_examples(bullet, "Content-Range: ")[0].split(": ")[1])
        (pattern, meaning) = next((p, m) for p, m in meanings.items() if re.match(p, bullet))
        size = int(re.match(pattern, bullet)[1])  # type: ignore[index]
        assert (span.first, span.last, span.complete_length) == (*meaning(size), total)


def test_single_part_example_is_what_the_decision_produces() -> None:
    body = section(upstream_text(RFC), "15.3.7.1", "Single Part")
    match = re.search(r"Content-Range: bytes (\d+)-(\d+)/(\d+)", body)
    assert match is not None
    first, last, complete = map(int, match.groups())
    content_length = int(re.search(r"Content-Length: (\d+)", body)[1])  # type: ignore[index]
    for header in (f"bytes={first}-", f"bytes={first}-{last}"):
        decision = hr.evaluate_range_request(method="GET", range_header=header, length=complete)
        assert decision.content_range == match[0].split(": ")[1]
        assert decision.ranges[0].length == content_length


def test_unsatisfiable_example_is_what_the_decision_produces() -> None:
    body = section(upstream_text(RFC), "15.5.17", "416 Range Not Satisfiable")
    value = _examples(body, "Content-Range: ")[0].split(": ")[1]
    complete = int(value.rsplit("/", 1)[1])
    decision = hr.evaluate_range_request(
        method="GET", range_header=f"bytes={complete}-", length=complete
    )
    assert (decision.status, decision.content_range) == (416, value)


def test_accept_ranges_examples_parse() -> None:
    body = section(upstream_text(RFC), "14.3", "Accept-Ranges")
    values = [line.split(": ", 1)[1] for line in _examples(body, "Accept-Ranges: ")]
    assert values == ["bytes", "none"]
    assert [hr.parse_accept_ranges(value) for value in values] == [("bytes",), ("none",)]
