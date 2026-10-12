"""Real end to end test: build the wheel, install it, drive the installed console script.

No mocks. The project is built into a wheel, the wheel is pip-installed into a throwaway
virtual environment, and the real ``httprange`` executable is run over ``subprocess``.
The assertions cover the actual stdout, stderr and exit codes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import venv
from pathlib import Path

import pytest

import httprange

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _exe(env_dir: Path, name: str) -> Path:
    scripts = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
    return scripts / (f"{name}.exe" if sys.platform == "win32" else name)


@pytest.fixture(scope="module")
def cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a wheel, install it into a fresh venv and return the console script path."""
    wheel_dir = tmp_path_factory.mktemp("httprange-wheel")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(wheel_dir),
            str(PROJECT_ROOT),
        ],
        check=True,
        capture_output=True,
        timeout=600,
    )
    wheels = sorted(wheel_dir.glob("httprange-*.whl"))
    assert len(wheels) == 1, wheels
    env_dir = tmp_path_factory.mktemp("httprange-e2e-venv")
    venv.create(env_dir, with_pip=True)
    subprocess.run(
        [
            str(_exe(env_dir, "python")),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        timeout=600,
    )
    script = _exe(env_dir, "httprange")
    assert script.is_file(), f"console script was not installed at {script}"
    return script


def _run(cli: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(cli), *args], capture_output=True, text=True, timeout=60)


def test_parse(cli: Path) -> None:
    result = _run(cli, "parse", "bytes=0-499,-500")
    assert (result.returncode, result.stdout.splitlines(), result.stderr) == (
        0,
        ["unit: bytes", "0-499", "-500"],
        "",
    )


def test_resolve_rfc_example(cli: Path) -> None:
    result = _run(cli, "resolve", "bytes= 0-999, 4500-5499, -1000", "--length", "10000")
    assert result.stdout.splitlines() == [
        "bytes 0-999/10000",
        "bytes 4500-5499/10000",
        "bytes 9000-9999/10000",
    ]


def test_content_range_and_parse_back(cli: Path) -> None:
    built = _run(cli, "content-range", "21010", "47021", "--length", "47022").stdout.strip()
    assert built == "bytes 21010-47021/47022"
    parsed = json.loads(_run(cli, "parse-content-range", "--json", built).stdout)
    assert (parsed["first"], parsed["last"], parsed["complete_length"]) == (21010, 47021, 47022)


def test_decide_json(cli: Path) -> None:
    result = _run(cli, "decide", "--range", "bytes=50000-", "--length", "47022", "--json")
    data = json.loads(result.stdout)
    assert (data["status"], data["content_range"]) == (416, "bytes */47022")


def test_errors_go_to_stderr_with_exit_1(cli: Path) -> None:
    result = _run(cli, "resolve", "bytes=5000-", "--length", "100")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr.startswith("httprange: error: ")
    usage = _run(cli, "resolve", "bytes=0-1")
    assert usage.returncode == 1
    assert "--length" in usage.stderr


def test_help_and_version(cli: Path) -> None:
    help_text = _run(cli, "--help")
    assert help_text.returncode == 0
    assert "examples:" in help_text.stdout
    assert _run(cli, "--version").stdout.strip() == f"httprange {httprange.__version__}"


def test_installed_library_imports_in_the_venv(cli: Path) -> None:
    python = _exe(cli.parent.parent, "python")
    code = "import httprange as h; print(h.__version__, h.resolve_ranges('bytes=-500', 10000))"
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split(" ", 1) == [
        httprange.__version__,
        "(ByteRange(first=9500, last=9999),)\n",
    ]
