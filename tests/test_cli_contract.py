"""The command line promises: exact output lines, cut messages, and a closed reader.

The closed-reader cases run the tool in a child process whose standard output is a pipe
with no reader left, so every write to it fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import httprange as hr
from httprange import _cli as cli
from httprange._cli import main

SRC = Path(__file__).resolve().parent.parent / "src"
DATE = "Sun, 06 Nov 1994 08:49:37 GMT"


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_decide_prints_exact_lines_for_a_single_range(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "decide", "--range", "bytes=0-9", "--length", "100")
    assert (code, err) == (0, "")
    assert out.splitlines() == [
        "status: 206",
        "reason: 1 range(s) satisfiable",
        "content-range: bytes 0-9/100",
    ]


def test_decide_prints_every_range_of_a_multipart_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run(capsys, "decide", "--range", "bytes=0-0,-1", "--length", "10")
    assert code == 0
    assert out.splitlines() == [
        "status: 206",
        "reason: 2 range(s) satisfiable",
        "range: 0-0",
        "range: 9-9",
    ]


@pytest.mark.parametrize(
    ("last_modified", "status"),
    [(DATE, 206), ("Mon, 07 Nov 1994 08:49:37 GMT", 200), (None, 200)],
)
def test_decide_matches_a_date_if_range_against_last_modified(
    capsys: pytest.CaptureFixture[str], last_modified: str | None, status: int
) -> None:
    args = ["decide", "--range", "bytes=0-9", "--length", "100", "--if-range", DATE]
    if last_modified is not None:
        args += ["--last-modified", last_modified]
    code, out, _ = run(capsys, *args)
    assert code == 0
    assert out.splitlines()[0] == f"status: {status}"


def test_error_messages_are_cut_to_200_characters(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "parse", "x" * 5000)
    assert (code, out) == (1, "")
    message = err.rstrip("\n").removeprefix("httprange: error: ")
    assert len(message) <= 203
    with pytest.raises(SystemExit) as info:
        main(["x" * 5000])
    assert info.value.code == 1
    usage, error = capsys.readouterr().err.rstrip("\n").split("\n")[-2:]
    assert len(error.removeprefix("httprange: error: ")) <= 203, usage


def test_a_long_library_error_is_cut_too(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(args: object) -> str:
        raise hr.RangeError("y" * 1000)

    monkeypatch.setattr(cli, "_run", fail)
    code, out, err = run(capsys, "parse", "bytes=0-1")
    assert (code, out) == (1, "")
    assert err == "httprange: error: " + "y" * 200 + "...\n"


def _closed_reader(*args: str) -> tuple[int, bytes]:
    """Run the tool with a standard output pipe whose reader is already closed."""
    read_end, write_end = os.pipe()
    os.close(read_end)
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    try:
        done = subprocess.run(
            [sys.executable, "-m", "httprange", *args],
            stdin=subprocess.DEVNULL,
            stdout=write_end,
            stderr=subprocess.PIPE,
            env=env,
            timeout=120,
            check=False,
        )
    finally:
        os.close(write_end)
    return done.returncode, done.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("--help",),
        ("--version",),
        ("decide", "--help"),
        ("parse", "bytes=0-1"),
        ("decide", "--range", "bytes=0-0,-1", "--length", "10"),
    ],
)
def test_a_closed_reader_gives_exit_1_and_nothing_on_stderr(args: tuple[str, ...]) -> None:
    assert _closed_reader(*args) == (1, b"")


def test_usage_errors_still_exit_1_with_a_closed_reader() -> None:
    code, err = _closed_reader("resolve", "bytes=0-1")
    assert code == 1
    assert b"the following arguments are required: --length" in err


class _DeadStdout:
    """A standard output whose every write and flush fails, as with a vanished reader."""

    encoding = "utf-8"

    def write(self, text: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_a_failing_print_gives_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _DeadStdout())
    assert main(["parse", "bytes=0-1"]) == 1


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_help_into_a_failing_stdout_gives_exit_1(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setattr(sys, "stdout", _DeadStdout())
    with pytest.raises(SystemExit) as info:
        main([flag])
    assert info.value.code == 1
