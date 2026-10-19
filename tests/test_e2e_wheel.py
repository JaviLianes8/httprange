"""Build the wheel and sdist, install the wheel in a throwaway venv and drive it as a consumer.

Slow and needs the ``build`` package, so it runs only with HTTPRANGE_E2E=1. The upgrade
from the PyPI release also needs the network: HTTPRANGE_E2E_PYPI=1.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("HTTPRANGE_E2E") != "1", reason="set HTTPRANGE_E2E=1 to build and install"
)

PROGRAM = r"""
import importlib.metadata, importlib.resources, pickle
import httprange as hr

assert "site-packages" in hr.__file__, hr.__file__
assert hr.__version__ == "1.0.0" == importlib.metadata.version("httprange")
assert sorted(hr.__all__) == sorted(n for n in dir(hr) if not n.startswith("_"))
assert importlib.resources.files("httprange").joinpath("py.typed").is_file()
data = bytes(range(256)) * 40
decision = hr.evaluate_range_request(
    method="GET", range_header="bytes=0-0,-1", length=len(data), if_range='"v1"', etag='"v1"'
)
assert (decision.status, decision.is_multipart) == (206, True), decision
body = hr.build_multipart_byteranges(data, decision.ranges, content_type="video/mp4")
parts = hr.parse_multipart_byteranges(body.body, body.content_type)
assert [p.data for p in parts] == [data[:1], data[-1:]]
assert str(parts[1].content_range) == "bytes 10239-10239/10240"
assert hr.resolve_ranges("bytes=500-600,601-999", 10000) == (hr.ByteRange(500, 999),)
span = hr.parse_content_range("bytes 42-1233/1234")
assert pickle.loads(pickle.dumps(span)) == span and type(span).__module__ == "httprange"
try:
    hr.resolve_ranges("bytes=0-0,0-0,0-0", 10)
except hr.ExcessiveRanges as error:
    assert isinstance(error, ValueError)
else:
    raise AssertionError("three overlapping ranges were accepted")
moment = hr.parse_http_date("Sunday, 06-Nov-94 08:49:37 GMT")
assert hr.format_http_date(moment) == "Sun, 06 Nov 1994 08:49:37 GMT"
print("e2e ok")
"""


def _run(*cmd: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, check=False, timeout=600
    )


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    built = _run(sys.executable, "-m", "build", "--outdir", out, ROOT)
    assert built.returncode == 0, built.stderr
    return out


def _venv(folder: Path) -> Path:
    venv.create(folder, with_pip=True)
    return folder / ("Scripts" if sys.platform == "win32" else "bin") / "python"


def _check(python: Path, work: Path) -> None:
    # Run from an empty folder so the source tree cannot shadow the install.
    work.mkdir(exist_ok=True)
    result = _run(python, "-I", "-c", PROGRAM, cwd=work)
    assert (result.returncode, result.stdout.strip()) == (0, "e2e ok"), result.stderr
    script = python.parent / ("httprange.exe" if sys.platform == "win32" else "httprange")
    decided = _run(script, "decide", "--range", "bytes=50000-", "--length", "47022", cwd=work)
    assert decided.returncode == 0, decided.stderr
    lines = decided.stdout.splitlines()
    assert lines[0] == "status: 416" and "content-range: bytes */47022" in lines, lines
    module = _run(python, "-I", "-m", "httprange", "resolve", "bytes=-500", "--length", "10000")
    assert (module.returncode, module.stdout) == (0, "bytes 9500-9999/10000\n"), module.stderr
    failed = _run(script, "parse", "bytes=5-1", cwd=work)
    assert (failed.returncode, failed.stdout) == (1, "")
    assert failed.stderr.startswith("httprange: error: ")


def test_wheel_and_sdist_contents(dist: Path) -> None:
    (wheel,) = dist.glob("httprange-1.0.0-*.whl")
    (sdist,) = dist.glob("httprange-1.0.0.tar.gz")
    names = zipfile.ZipFile(wheel).namelist()
    assert "httprange/py.typed" in names and "httprange/__main__.py" in names
    assert any(name.endswith("licenses/LICENSE") for name in names)
    assert all(name.startswith(("httprange/", "httprange-1.0.0.dist-info/")) for name in names)
    package = [name for name in names if name.startswith("httprange/")]
    assert all(name.endswith((".py", "py.typed")) for name in package), package
    listing = _run(sys.executable, "-m", "tarfile", "-l", sdist).stdout
    for absent in ("IMPROVEMENTS-round", "CERT-1.0-", "rfc", ".tgz", ".html", "__pycache__"):
        assert absent not in listing, absent
    for present in ("tests/upstream/MANIFEST.json", "GUIDE.md", "CHANGELOG.md", "LICENSE"):
        assert present in listing, present


def test_installed_wheel_end_to_end(dist: Path, tmp_path: Path) -> None:
    (wheel,) = dist.glob("httprange-1.0.0-*.whl")
    python = _venv(tmp_path / "venv")
    installed = _run(python, "-m", "pip", "install", "-q", wheel)
    assert installed.returncode == 0, installed.stderr
    _check(python, tmp_path / "work")


@pytest.mark.skipif(
    os.environ.get("HTTPRANGE_E2E_PYPI") != "1", reason="set HTTPRANGE_E2E_PYPI=1 to use PyPI"
)
def test_upgrade_in_place_from_the_pypi_release(dist: Path, tmp_path: Path) -> None:
    (wheel,) = dist.glob("httprange-1.0.0-*.whl")
    python = _venv(tmp_path / "venv")
    old = _run(python, "-m", "pip", "install", "-q", "httprange==0.2.0")
    assert old.returncode == 0, old.stderr
    probe = (
        "import httprange as h; print(h.__version__, h.resolve_ranges('bytes=0-0,-1', 10),"
        " h.evaluate_range_request(method='GET', range_header='bytes=9-', length=5).status)"
    )
    before = _run(python, "-I", "-c", probe, cwd=tmp_path)
    assert before.stdout.split()[0] == "0.2.0", before.stderr
    upgraded = _run(python, "-m", "pip", "install", "-q", "--upgrade", wheel)
    assert upgraded.returncode == 0, upgraded.stderr
    after = _run(python, "-I", "-c", probe, cwd=tmp_path)
    assert after.stdout.split()[0] == "1.0.0", after.stderr
    assert after.stdout.split(None, 1)[1] == before.stdout.split(None, 1)[1]
    _check(python, tmp_path / "work")
