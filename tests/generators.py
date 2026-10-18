"""Seeded generators of near-valid and hostile header values for the property tests."""

from __future__ import annotations

import random

EDGE = list(' \t,-=/*";:.!#W0123456789') + [chr(c) for c in (0, 0x7F, 0xB2, 0xE9, 0x663, 0xFF)]
UNITS = ("bytes", "Bytes", "BYTES", "items", "by tes", "", "x" * 50)


def number(rng: random.Random, size: int = 1000) -> int:
    return rng.choice((0, 1, size - 1, size, size + 1, rng.randrange(size + 2), 2**64, 10**30))


def spec(rng: random.Random, size: int = 1000) -> str:
    kind = rng.randrange(6)
    if kind == 0:
        first = number(rng, size)
        return f"{first}-{first + rng.randrange(size + 2)}"
    if kind == 1:
        return f"{number(rng, size)}-"
    if kind == 2:
        return f"-{number(rng, size)}"
    if kind == 3:
        return f"{number(rng, size)}-{number(rng, size)}"
    return rng.choice(("", " ", "-", "a-b", "0-0", "00-01", "1.2-4.3", "-0", "0x1-2"))


def noise(text: str, rng: random.Random, edits: int = 3) -> str:
    """``text`` with up to ``edits`` random insertions, deletions or replacements."""
    for _ in range(rng.randrange(edits + 1)):
        spot = rng.randrange(len(text) + 1)
        choice = rng.randrange(3)
        char = rng.choice(EDGE)
        if choice == 0:
            text = text[:spot] + char + text[spot:]
        elif choice == 1:
            text = text[:spot] + text[spot + 1 :]
        else:
            text = text[:spot] + char + text[spot + 1 :]
    return text


def noise_bytes(data: bytes, rng: random.Random, edits: int = 3) -> bytes:
    """``data`` with up to ``edits`` random byte insertions, deletions or replacements."""
    alphabet = b' \t\r\n-:;="/*0123456789bB\x00\xff'
    for _ in range(rng.randrange(edits + 1)):
        spot = rng.randrange(len(data) + 1)
        byte = bytes([rng.choice(alphabet)])
        choice = rng.randrange(3)
        if choice == 0:
            data = data[:spot] + byte + data[spot:]
        elif choice == 1:
            data = data[:spot] + data[spot + 1 :]
        else:
            data = data[:spot] + byte + data[spot + 1 :]
    return data


def range_header(rng: random.Random, size: int = 1000, most: int = 6) -> str:
    unit = rng.choice(UNITS) if rng.random() < 0.3 else "bytes"
    gap = rng.choice(("", " ", ", ", " ,\t"))
    specs = gap.join(spec(rng, size) for _ in range(rng.randrange(1, most)))
    return noise(f"{unit}={rng.choice(('', ' '))}{specs}", rng, rng.choice((0, 0, 1, 3)))


def content_range(rng: random.Random) -> str:
    first = number(rng)
    last = rng.choice((first, first + rng.randrange(1000), max(0, first - 1)))
    total = rng.choice(("*", str(last + 1), str(last), str(last + rng.randrange(1, 10**6))))
    unit = rng.choice(("bytes", "Bytes", "items", "bytes"))
    value = f"{unit} */{total}" if rng.random() < 0.15 else f"{unit} {first}-{last}/{total}"
    return noise(value, rng, rng.choice((0, 0, 1, 3)))


def http_date(rng: random.Random) -> str:
    day = rng.randrange(0, 33)
    hour, minute, second = rng.randrange(25), rng.randrange(61), rng.randrange(62)
    month = rng.choice(("Jan", "Feb", "Mar", "Nov", "Dec", "jan", "Foo"))
    clock = f"{hour:02d}:{minute:02d}:{second:02d}"
    year = rng.randrange(0, 10000)
    value = rng.choice(
        (
            f"Sun, {day:02d} {month} {year:04d} {clock} GMT",
            f"Sunday, {day:02d}-{month}-{year % 100:02d} {clock} GMT",
            f"Sun {month} {day:2d} {clock} {year:04d}",
        )
    )
    return noise(value, rng, rng.choice((0, 0, 1, 2)))


def entity_tag(rng: random.Random) -> str:
    inner = "".join(rng.choice('ab1"\\ \x7f\x80') for _ in range(rng.randrange(4)))
    return noise(rng.choice(("", "W/")) + f'"{inner}"', rng, rng.choice((0, 0, 1)))
