"""The strict parsers accept exactly what the RFC 9110 grammar accepts.

The grammar is the collected ABNF of the fetched RFC 9110 (Appendix A) with the core
rules of the fetched RFC 5234 (Appendix B.1) and the rule erratum 7306 gives; tests/abnf.py
turns it into regular expressions and random sentences. Seeded sentences and mutations of
them go through both, and they must agree, apart from the rules the RFC states in prose
(quoted next to each check) and the library's documented 4000-digit limit.
"""

from __future__ import annotations

import calendar
import functools
import random
import re
from collections.abc import Callable

import abnf
import pytest
from conftest import between, upstream_prose, upstream_text

import httprange as hr

OWS = " \t"
# Characters that sit on the grammar's edges, plus a few outside ASCII and controls.
NOISE = [*OWS, *',-=/*";.:!#~W0123456789abyteBYTE', *map(chr, (0xE9, 0x663, 0, 0x7F, 0xFF))]


@functools.cache
def _rules() -> dict[str, abnf.Node]:
    core = between(upstream_text("rfc5234.txt"), "B.1.  Core Rules", "B.2.  Common Encoding")
    collected = between(upstream_text("rfc9110.txt"), "Appendix A.  Collected", "Appendix B.  ")
    rules = {**abnf.read_rules(core, 9), **abnf.read_rules(collected, 3)}
    fixed = re.search(
        r"It should say: (ranges-specifier = .+?) range-set =",
        upstream_prose("rfc9110-erratum-7306.html"),
    )
    assert fixed is not None
    rules["ranges-specifier"] = abnf.parse(fixed[1].split("=", 1)[1])
    return rules


def _grammar(name: str) -> re.Pattern[str]:
    return re.compile(abnf.regex(_rules()[name], _rules()))


def _mutate(text: str, rng: random.Random) -> str:
    for _ in range(rng.choice((0, 0, 1, 1, 2, 3))):
        spot = rng.randrange(len(text) + 1)
        edit = rng.randrange(4)
        if edit == 0:
            text = text[:spot] + rng.choice(NOISE) + text[spot:]
        elif edit == 1:
            text = text[:spot] + text[spot + 1 :]
        elif edit == 2:
            text = text[:spot] + rng.choice(NOISE) + text[spot + 1 :]
        else:
            text = text[:spot] + text[spot : spot + 4] * 2 + text[spot + 4 :]
    return text


def _strip_list(value: str, head: str) -> str | None:
    """RFC 9110 5.6.1.2: drop up to 16 empty list elements (16 is the library's choice)."""
    items = [item.strip(OWS) for item in value.split(",")]
    kept = [item for item in items if item]
    if len(items) - len(kept) > 16 or not kept:
        return None
    return head + ",".join(kept)


def _digits_ok(text: str) -> bool:
    return all(len(run.lstrip("0")) <= 4000 for run in re.findall(r"\d+", text))


def _accepts(call: Callable[[str], object], text: str) -> bool:
    try:
        call(text)
    except hr.RangeError:
        return False
    return True


def _compare(name: str, expected: Callable[[str], bool], call: Callable[[str], object]) -> int:
    rules, rng = _rules(), random.Random(f"grammar-{name}")
    agreed = 0
    for _ in range(12000):
        text = _mutate(abnf.sentence(rules[name], rules, rng), rng)
        if name == "range" and rng.random() < 0.6:
            text = rng.choice(("bytes", "Bytes", "BYTES")) + text[text.find("=") :]
        text = rng.choice(("", " ", "\t")) + text + rng.choice(("", "", " "))
        assert _accepts(call, text) is expected(text), (name, text)
        agreed += 1
    return agreed


def test_range_headers() -> None:
    syntax, int_range = _grammar("range"), _grammar("int-range")
    suffix = _grammar("suffix-range")

    def expected(text: str) -> bool:
        unit, equals, rest = text.strip(OWS).partition("=")
        value = _strip_list(rest, unit + equals)
        if value is None or not syntax.fullmatch(value) or not _digits_ok(value):
            return False
        items = value.split("=", 1)[1].split(",")
        if unit.lower() != "bytes":  # 14.1: range unit names are case-insensitive
            return True
        # 14.1.2: "Byte ranges do not use the other-range specifier."
        if not all(int_range.fullmatch(item) or suffix.fullmatch(item) for item in items):
            return False
        # 14.1.1: "An int-range is invalid if the last-pos value is present and less than
        # the first-pos."
        pairs = [item.split("-") for item in items if not item.startswith("-")]
        return all(not last or int(last) >= int(first) for first, last in pairs)

    assert _compare("range", expected, hr.parse_range_request) == 12000


def test_content_range_values() -> None:
    syntax = _grammar("content-range")

    def expected(text: str) -> bool:
        value = text.strip(OWS)
        if not syntax.fullmatch(value) or not _digits_ok(value):
            return False
        numbers = [int(n) for n in re.findall(r"\d+", value.split(" ", 1)[1])]
        if "*/" in value:
            return True
        first, last = numbers[:2]
        # 14.4: invalid if last-pos < first-pos, or complete-length <= last-pos.
        return last >= first and (len(numbers) == 2 or numbers[2] > last)

    assert _compare("content-range", expected, hr.parse_content_range) == 12000


def test_accept_ranges_values() -> None:
    syntax = _grammar("acceptable-ranges")

    def expected(text: str) -> bool:
        value = _strip_list(text.strip(OWS), "")
        return value is not None and bool(syntax.fullmatch(value))

    assert _compare("acceptable-ranges", expected, hr.parse_accept_ranges) == 12000


def _plausible(text: str, rng: random.Random) -> str:
    """Most of the time, give a random date a real time of day and day of month."""
    if rng.random() < 0.3:
        return text
    clock = f"{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(61):02d}"
    text = re.sub(r"\d\d:\d\d:\d\d", clock, text)
    day = rng.randrange(1, 29)
    text = re.sub(r"(?<=, )\d\d(?=[ -])", f"{day:02d}", text)  # IMF-fixdate, RFC 850
    return re.sub(r"(?<=^\w{3} \w{3} )[ \d]\d(?= )", f"{day:2d}", text)  # asctime


# Field positions inside each format, which the grammar fixes; used only after it matched.
_FIELDS = {
    "imf-fixdate": r"\w+, (?P<d>\d\d) (?P<m>\w+) (?P<y>\d{4}) (?P<t>\S+) GMT",
    "rfc850-date": r"\w+, (?P<d>\d\d)-(?P<m>\w+)-\d\d (?P<t>\S+) GMT",
    "asctime-date": r"\w+ (?P<m>\w+) (?P<d>[ \d]\d) (?P<t>\S+) (?P<y>\d{4})",
}


@pytest.mark.parametrize("name", sorted(_FIELDS))
def test_http_dates(name: str) -> None:
    syntax = _grammar("http-date")
    months = [calendar.month_abbr[number] for number in range(1, 13)]

    def expected(text: str) -> bool:
        value = text.strip(OWS)
        if not syntax.fullmatch(value):
            return False
        kind = next(rule for rule in _FIELDS if _grammar(rule).fullmatch(value))
        fields = re.fullmatch(_FIELDS[kind], value)
        assert fields is not None, value
        # A two-digit year lands in 1977 to 2076 today; 2000 stands for "a leap year".
        year = int(fields["y"]) if "y" in fields.groupdict() else 2000
        month, day = months.index(fields["m"]) + 1, int(fields["d"])
        hour, minute, second = map(int, fields["t"].split(":"))
        # 5.6.7: time-of-day runs "00:00:00 - 23:59:60 (leap second)"; datetime has no
        # year 0.
        valid_day = year >= 1 and 1 <= day <= calendar.monthrange(year, month)[1]
        return valid_day and hour <= 23 and minute <= 59 and second <= 60

    rules, rng = _rules(), random.Random(f"date-{name}")
    checked = 0
    for _ in range(6000):
        text = _mutate(_plausible(abnf.sentence(rules[name], rules, rng), rng), rng)
        if "29-Feb-" in text:
            continue  # 29 February under the fifty-year rule depends on the year chosen
        assert _accepts(hr.parse_http_date, text) is expected(text), text
        checked += 1
    assert checked > 5000
