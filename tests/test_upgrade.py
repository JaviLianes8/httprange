"""The PyPI release 0.2.0 as an oracle: 1.0.0 answers the same, except where documented.

Needs HTTPRANGE_V02 (see the ``old`` fixture in conftest.py); skipped otherwise. The
documented differences are in test_upgrade_changes.py and CHANGELOG.md.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any

import generators as gen

import httprange as hr

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = (_plain(getattr(value, field.name)) for field in dataclasses.fields(value))
        return (type(value).__name__, *fields)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value.isoformat() if isinstance(value, datetime) else value


def _outcome(module: ModuleType, name: str, *args: Any, **kwargs: Any) -> Any:
    try:
        result = getattr(module, name)(*args, **kwargs)
    except ValueError as error:
        return ("error", type(error).__name__)
    if name == "evaluate_range_request":  # the reason is free text
        return (result.status, _plain(result.ranges), result.content_range)
    return _plain(result)


def _same(old: ModuleType, calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]]) -> int:
    for name, args, kwargs in calls:
        assert _outcome(old, name, *args, **kwargs) == _outcome(hr, name, *args, **kwargs), (
            name,
            args,
            kwargs,
        )
    return len(calls)


def _is_date(text: str) -> bool:
    try:
        hr.parse_http_date(text)
    except hr.MalformedDate:
        return False
    return True


def test_parsers_agree_with_0_2_0(old: ModuleType) -> None:
    rng = random.Random(20)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    for _ in range(6000):
        header, size = gen.range_header(rng), rng.choice((0, 1, 10, 1000))
        calls += [
            ("parse_range", (header,), {}),
            ("parse_range_request", (header,), {}),
            ("resolve", (header, size), {}),
            ("resolve_ranges", (header, size), {}),
            ("parse_accept_ranges", (gen.noise("bytes, items", rng),), {}),
            ("parse_content_range", (gen.content_range(rng),), {}),
        ]
    assert _same(old, calls) == 36000


def test_dates_and_if_range_agree_with_0_2_0(old: ModuleType) -> None:
    rng = random.Random(21)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    boundary = f"{NOW:%d-%b}-{(NOW.year + 50) % 100:02d}"
    while len(calls) < 12000:
        date, tag = gen.http_date(rng), gen.entity_tag(rng)
        if boundary in date:
            continue  # the boundary day of the fifty-year rule: see test_upgrade_changes
        calls.append(("parse_http_date", (date,), {"now": NOW}))
        # If-Range reads two-digit years against the real clock, so leave RFC 850 out.
        date = date if "Sunday" not in date else hr.format_http_date(NOW)
        current = rng.choice((date, NOW - timedelta(seconds=rng.randrange(10**9))))
        if current == date and not _is_date(date):
            current = NOW  # a malformed last_modified now raises: see test_upgrade_changes
        kwargs = {
            "etag": gen.entity_tag(rng),
            "last_modified": current,
            "date_is_strong": rng.random() < 0.8,
        }
        calls.append(("if_range_matches", (rng.choice((tag, date)),), kwargs))
    assert _same(old, calls) == 12000


def test_decisions_agree_with_0_2_0(old: ModuleType) -> None:
    rng = random.Random(22)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    for _ in range(6000):
        kwargs = {
            "method": rng.choice(("GET", "GET", "HEAD", "get")),
            "range_header": rng.choice((None, gen.range_header(rng))),
            "length": rng.choice((0, 1, 10, 1000)),
            "if_range": rng.choice((None, None, '"v1"', 'W/"v1"', gen.http_date(rng))),
            "etag": rng.choice((None, '"v1"')),
            "on_excessive": rng.choice(("reject", "ignore")),
        }
        calls.append(("evaluate_range_request", (), kwargs))
    assert _same(old, calls) == 6000


def test_builders_and_the_multipart_parser_agree_with_0_2_0(old: ModuleType) -> None:
    rng = random.Random(23)
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    for _ in range(3000):
        first, last, total = (rng.choice((None, gen.number(rng))) for _ in range(3))
        calls.append(("build_content_range", (first, last, total), {}))
        size = rng.randrange(1, 300)
        data = bytes(rng.randrange(256) for _ in range(size))
        ranges = [hr.ByteRange(0, rng.randrange(size)), hr.ByteRange(size - 1, size - 1)]
        old_ranges = [old.ByteRange(item.first, item.last) for item in ranges]
        media = rng.choice((None, "text/plain", "application/pdf"))
        options = {"content_type": media, "boundary": "SEP"}
        assert _plain(old.build_multipart_byteranges(data, old_ranges, **options)) == _plain(
            hr.build_multipart_byteranges(data, ranges, **options)
        )
        body = hr.build_multipart_byteranges(data, ranges, **options)
        mutated = gen.noise_bytes(body.body, rng, 2)
        content_type = rng.choice((body.content_type, 'multipart/byteranges; boundary="SEP"'))
        _same_parts(old, mutated, content_type)
    assert _same(old, calls) == 3000


def _same_parts(old: ModuleType, body: bytes, content_type: str) -> None:
    before = _outcome(old, "parse_multipart_byteranges", body, content_type)
    after = _outcome(hr, "parse_multipart_byteranges", body, content_type)
    if before == after:
        return
    # 1.0.0 refuses what 0.2.0 let through only for the documented reasons, read here
    # from 0.2.0's own answer or from the raw part headers.
    assert after == ("error", "MalformedMultipart") and before[0] != "error", (body, before)
    units = {part[1][1] for part in before}
    controls = any(
        part[3] is not None and any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in part[3])
        for part in before
    )
    heads = [piece.split(b"\r\n\r\n", 1)[0].lower() for piece in body.split(b"--SEP")[1:]]
    repeated = any(head.count(b"\r\ncontent-type:") > 1 for head in heads)
    assert len(units) > 1 or controls or repeated, (body, before)
