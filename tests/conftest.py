from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from range_server import CONTENT, serve

UPSTREAM = Path(__file__).resolve().parent / "upstream"


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """URL of a real local HTTP server that answers range requests with the library."""
    path = tmp_path_factory.mktemp("served") / "file.bin"
    path.write_bytes(CONTENT)
    with serve(path) as url:
        yield url


def upstream_bytes(name: str) -> bytes:
    """Return a third-party file, checked against its manifest entry.

    The files are not committed: `python scripts/fetch_upstream.py` fetches them. Their
    tests skip while a file is absent and fail if it differs from the manifest.
    """
    path = UPSTREAM / name
    if not path.is_file():
        pytest.skip(f"{name} is not fetched; run python scripts/fetch_upstream.py")
    entry = json.loads((UPSTREAM / "MANIFEST.json").read_text(encoding="utf-8"))[name]
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == entry["sha256"], f"{name} differs from MANIFEST"
    return body


def upstream_text(name: str) -> str:
    """Return a fetched RFC as text, without a byte order mark or page breaks.

    Older RFCs end each page with a footer line, a form feed and a header line; those
    lines and the blank lines around them are removed.
    """
    text = upstream_bytes(name).decode("utf-8-sig")
    return re.sub(r"\n+[^\n]*\[Page \d+\]\n\f\n[^\n]*\n+", "\n", text)


def upstream_prose(name: str) -> str:
    """Return a fetched HTML page as plain text: tags removed, whitespace collapsed."""
    text = re.sub(r"<[^>]+>", " ", upstream_bytes(name).decode("utf-8"))
    return re.sub(r"\s+", " ", html.unescape(text))


def section(text: str, number: str, title: str) -> str:
    """The body of an RFC section, from its heading to the next numbered heading."""
    heading = re.search(rf"^{re.escape(number)}\.  {re.escape(title)}\n", text, re.MULTILINE)
    assert heading, (number, title)
    rest = text[heading.end() :]
    following = re.search(r"^(?:\d+\.)+\d*\.? {2}\S", rest, re.MULTILINE)
    return rest[: following.start()] if following else rest


def between(text: str, start: str, end: str) -> str:
    """The text from the line starting with ``start`` to the line starting with ``end``."""
    first = re.search("^" + re.escape(start), text, re.MULTILINE)
    assert first is not None, start
    last = re.search("^" + re.escape(end), text[first.end() :], re.MULTILINE)
    assert last is not None, end
    return text[first.end() : first.end() + last.start()]
