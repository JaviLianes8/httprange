"""Real interop test: the curl command line client against the library-built server.

``curl -r`` writes real ``Range`` headers; skipped when curl is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from range_server import CONTENT

import httprange as hr


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
@pytest.mark.parametrize(
    ("curl_range", "first", "last"),
    [("0-499", 0, 499), ("-500", 9500, 9999), ("9500-", 9500, 9999)],
)
def test_curl_range_option_interoperates(
    base_url: str, tmp_path: Path, curl_range: str, first: int, last: int
) -> None:
    out = tmp_path / "body.bin"
    result = subprocess.run(
        ["curl", "-s", "-r", curl_range, "-o", str(out), "-w", "%{http_code}", base_url],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.stdout == "206"
    assert out.read_bytes() == CONTENT[first : last + 1]


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
def test_curl_multi_range_body_parses(base_url: str, tmp_path: Path) -> None:
    out, head = tmp_path / "body.bin", tmp_path / "head.txt"
    command = ["curl", "-s", "-r", "0-0,-1", "-D", str(head), "-o", str(out), base_url]
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    lines = head.read_text("latin-1").splitlines()
    assert lines[0].split()[1] == "206"
    content_type = next(
        line.split(":", 1)[1] for line in lines if line.lower().startswith("content-type:")
    )
    parts = hr.parse_multipart_byteranges(out.read_bytes(), content_type.strip())
    assert [part.data for part in parts] == [CONTENT[:1], CONTENT[-1:]]
