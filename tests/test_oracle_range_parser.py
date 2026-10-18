"""range-parser 1.3.0, the Range parser of Express and send, as an independent oracle.

The npm tarball (https://registry.npmjs.org/range-parser/-/range-parser-1.3.0.tgz, fetched
2026-10-18, sha256 in tests/upstream/MANIFEST.json) runs under Node.js through
scripts/range_parser_oracle.js. Inside RFC 9110 both answer the same; each of its
departures from RFC 9110 is asserted on its own.
"""

from __future__ import annotations

import io
import json
import random
import shutil
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import upstream_bytes

import httprange as hr

ROOT = Path(__file__).resolve().parents[1]
WIDE = {"max_ranges": 10**6, "max_overlapping": 10**6}
Oracle = Callable[[list[tuple[int, str, bool]]], list[object]]


@pytest.fixture(scope="module")
def oracle(tmp_path_factory: pytest.TempPathFactory) -> Oracle:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    script = tmp_path_factory.mktemp("range-parser") / "index.js"
    with tarfile.open(fileobj=io.BytesIO(upstream_bytes("range-parser-1.3.0.tgz"))) as archive:
        member = archive.extractfile("package/index.js")
        assert member is not None
        script.write_bytes(member.read())

    def run(cases: list[tuple[int, str, bool]]) -> list[object]:
        payload = "".join(json.dumps(list(case)) + "\n" for case in cases)
        command = [node, str(ROOT / "scripts" / "range_parser_oracle.js"), str(script)]
        done = subprocess.run(command, input=payload, capture_output=True, text=True, check=True)
        return [_theirs(json.loads(line)) for line in done.stdout.splitlines()]

    return run


def _theirs(answer: object) -> object:
    return answer if isinstance(answer, int) else answer["ranges"]  # type: ignore[index]


def _ours(header: str, size: int, combine: bool) -> object:
    try:
        found = hr.resolve_ranges(header, size, policy=hr.RangePolicy(**WIDE, coalesce=combine))
    except hr.UnsatisfiableRange:
        return -1
    except hr.MalformedRange:
        return -2
    return [[item.first, item.last] for item in found]


def _spec(rng: random.Random, size: int) -> str:
    """A spec inside RFC 9110 that range-parser also reads as the RFC says."""
    point = rng.choice((0, size - 1, size, size + 7, rng.randrange(size + 9)))
    kind = rng.randrange(3)
    if kind == 0:
        return f"{point}-{rng.randrange(point, point + size + 9)}"
    return f"{point}-" if kind == 1 else f"-{rng.randrange(size + 1)}"


def _header(rng: random.Random, size: int) -> str:
    specs = [rng.choice(("", " ", "\t ")) + _spec(rng, size) for _ in range(rng.randrange(1, 5))]
    return "bytes=" + ",".join(specs)


def _contained(header: str, size: int) -> bool:
    found = _ours(header, size, False)
    ranges = found if isinstance(found, list) else []
    return any(a != b and a[0] <= b[0] and b[1] <= a[1] for a in ranges for b in ranges)


def test_both_agree_on_headers_inside_rfc_9110(oracle: Oracle) -> None:
    rng = random.Random(9110)
    cases = []
    for _ in range(6000):
        size = rng.choice((1, 2, 10, 500, 10000, 2**40))
        cases.append((size, _header(rng, size), rng.random() < 0.5))
    for (size, header, combine), theirs in zip(cases, oracle(cases), strict=True):
        ours = _ours(header, size, combine)
        if combine and _contained(header, size):
            # A range wholly inside another keeps the outer range's position there; here a
            # merged range takes the earliest position of the specs it covers.
            assert sorted(theirs) == sorted(ours), (size, header)  # type: ignore[call-overload]
        else:
            assert theirs == ours, (size, header, combine)


def test_each_departure_from_rfc_9110(oracle: Oracle) -> None:
    cases = [
        (100, "bytes=0-1,,5-6", False),  # empty list element (5.6.1.2: ignore it)
        (100, "bytes=0-1,", False),
        (100, "bytes=0- 1", False),  # whitespace inside a range-spec
        (100, "bytes=5-1", False),  # last-pos before first-pos (14.1.1: invalid)
        (100, "bytes=5-1,7-8", False),
        (100, "bytes=-500", False),  # suffix longer than the representation (14.1.2)
        (100, "bytes=-500,0-0", False),
        (0, "bytes=-5", False),  # empty representation, non-zero suffix (14.1.2)
        (100, "Bytes=0-1", False),  # unit names are case-insensitive (14.1)
        (200, "bytes=10-20,100-110,0-30", True),  # merge order
    ]
    assert oracle(cases) == [
        -2,
        -2,
        [[0, 1]],
        -1,
        [[7, 8]],
        -1,
        [[0, 0]],
        -1,
        [[0, 1]],
        [[100, 110], [0, 30]],
    ]
    assert [_ours(header, size, combine) for size, header, combine in cases] == [
        [[0, 1], [5, 6]],
        [[0, 1]],
        -2,
        -2,
        -2,
        [[0, 99]],
        [[0, 99], [0, 0]],
        [],
        [[0, 1]],
        [[0, 30], [100, 110]],
    ]
