import json
import shlex

import pytest

from httprange._cli import EXAMPLES, main


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_parse_lists_each_spec(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "parse", "bytes=0-499,-500") == (0, "unit: bytes\n0-499\n-500\n", "")


def test_parse_json_and_other_units(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "parse", "--json", "items=1.2-4.3")
    assert code == 0
    assert json.loads(out) == {"unit": "items", "ranges": ["1.2-4.3"]}


def test_resolve_prints_content_ranges(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "resolve", "bytes=-500", "--length", "10000")
    assert (code, out) == (0, "bytes 9500-9999/10000\n")
    code, out, _ = run(capsys, "resolve", "bytes=0-99,50-199", "--length", "1000", "--json")
    assert json.loads(out) == {"ranges": [[0, 199]], "content_range": ["bytes 0-199/1000"]}
    code, out, _ = run(capsys, "resolve", "bytes=0-99,50-199", "--length", "1000", "--no-coalesce")
    assert out.splitlines() == ["bytes 0-99/1000", "bytes 50-199/1000"]


def test_resolve_enforces_max_ranges(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "resolve", "bytes=0-1,4-5", "--length", "9", "--max-ranges", "1")
    assert (code, out) == (1, "")
    assert "at most 1" in err


def test_content_range_forms(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "content-range", "0", "499", "--length", "1234")[1] == "bytes 0-499/1234\n"
    assert run(capsys, "content-range", "42", "1233")[1] == "bytes 42-1233/*\n"
    assert run(capsys, "content-range", "--unsatisfied", "--length", "1234")[1] == "bytes */1234\n"


@pytest.mark.parametrize(
    "args",
    [
        ("content-range", "0"),
        ("content-range", "--unsatisfied", "0", "1", "--length", "9"),
        ("content-range", "--unsatisfied"),
        ("content-range", "5", "1", "--length", "9"),
        ("resolve", "bytes=5000-", "--length", "100"),
        ("parse", "bytes=5-1"),
        ("parse-content-range", "bytes 9-1/10"),
    ],
)
def test_errors_go_to_stderr_with_exit_1(
    capsys: pytest.CaptureFixture[str], args: tuple[str, ...]
) -> None:
    code, out, err = run(capsys, *args)
    assert (code, out) == (1, "")
    assert err.startswith("httprange: error: ")


def test_usage_errors_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["resolve", "bytes=0-1", "--length", "-5"])
    assert info.value.code == 1
    assert "non-negative" in capsys.readouterr().err


def test_parse_content_range(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "parse-content-range", "bytes 42-1233/*")
    assert out.splitlines() == [
        "unit: bytes",
        "first: 42",
        "last: 1233",
        "complete_length: *",
        "satisfied: True",
    ]
    code, out, _ = run(capsys, "parse-content-range", "--json", "bytes */1234")
    assert (code, json.loads(out)["complete_length"]) == (0, 1234)


def test_decide(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "decide", "--range", "bytes=0-0,-1", "--length", "10000")
    assert out.splitlines() == [
        "status: 206",
        "reason: 2 range(s) satisfiable",
        "range: 0-0",
        "range: 9999-9999",
    ]
    code, out, _ = run(
        capsys,
        "decide",
        "--range",
        "bytes=0-9",
        "--length",
        "100",
        "--json",
        "--if-range",
        '"v2"',
        "--etag",
        '"v1"',
    )
    assert json.loads(out)["status"] == 200
    code, out, _ = run(capsys, "decide", "--range", "bytes=500-", "--length", "100")
    assert code == 0
    assert "content-range: bytes */100" in out


def test_help_lists_the_examples(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    assert EXAMPLES in capsys.readouterr().out


@pytest.mark.parametrize("line", EXAMPLES.splitlines()[1:])
def test_every_help_example_runs(capsys: pytest.CaptureFixture[str], line: str) -> None:
    words = shlex.split(line, comments=True)
    assert words[0] == "httprange"
    code, out, err = run(capsys, *words[1:])
    expected = 1 if "error" in line.split("#", 1)[-1] else 0
    assert (code, bool(out), bool(err)) == (expected, expected == 0, expected == 1)
    comment = line.split("#", 1)[1].strip() if "#" in line else ""
    if comment and expected == 0 and not comment.startswith("one "):
        assert comment in out


def test_non_ascii_input_never_crashes(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "decide", "--range", "bytes=あ-1", "--length", "10")
    assert (code, out.splitlines()[0]) == (0, "status: 200")
