"""Pins for documented orders and shapes: the rules of evaluate_range_request in the order
its docstring and the GUIDE give, the whitespace around a Range field value, and the
prefix of command line errors. Each runs in the default gate."""

from __future__ import annotations

from typing import Literal

import pytest

import httprange as hr
from httprange._cli import main

MANY_THEN_BAD = "bytes=" + "0-0," * 100 + "x"


def _status(header: str, on_excessive: Literal["reject", "ignore"] = "reject") -> int:
    decision = hr.evaluate_range_request(
        method="GET", range_header=header, length=10, on_excessive=on_excessive
    )
    return decision.status


def test_specs_are_counted_before_their_syntax_is_read() -> None:
    assert _status("bytes=x") == 200
    assert _status("bytes=0-0,x") == 200
    assert _status(MANY_THEN_BAD) == 416
    assert _status(MANY_THEN_BAD, on_excessive="ignore") == 200
    with pytest.raises(hr.ExcessiveRanges):
        hr.resolve_ranges(MANY_THEN_BAD, 10)


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        ("items=a b", "invalid Range ignored"),
        ("items=", "invalid Range ignored"),
        ("bytes", "invalid Range ignored"),
        ("items=" + "a," * 101 + "b", "unsupported range unit"),
    ],
)
def test_the_unit_and_list_are_read_before_the_count(header: str, reason: str) -> None:
    decision = hr.evaluate_range_request(method="GET", range_header=header, length=10)
    assert decision.status == 200
    assert decision.reason.startswith(reason)


def test_an_empty_representation_wins_over_an_invalid_header() -> None:
    decision = hr.evaluate_range_request(method="GET", range_header=MANY_THEN_BAD, length=0)
    assert (decision.status, decision.reason) == (200, "the representation is empty")


def test_nothing_satisfiable_is_416_even_when_excess_is_ignored() -> None:
    assert _status("bytes=20-30", on_excessive="ignore") == 416
    assert _status("bytes=0-5,0-5,0-5") == 416
    assert _status("bytes=0-5,0-5,0-5", on_excessive="ignore") == 200


@pytest.mark.parametrize("pad", [" ", "\t", " \t "])
def test_whitespace_around_the_whole_range_value_is_ignored(pad: str) -> None:
    request = hr.parse_range_request(pad + "bytes=0-1" + pad)
    assert request == hr.RangeRequest("bytes", (hr.RangeSpec(0, 1),))


@pytest.mark.parametrize("value", ["bytes =0-1", "bytes\t=0-1", "bytes=0 -1", "bytes=0- 1"])
def test_whitespace_before_the_equals_sign_or_inside_a_spec_is_refused(value: str) -> None:
    with pytest.raises(hr.MalformedRange):
        hr.parse_range_request(value)


def test_errors_name_the_tool_or_the_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["resolve", "bytes=a", "--length", "5"]) == 1
    assert capsys.readouterr().err.startswith("httprange: error: ")
    with pytest.raises(SystemExit) as caught:
        main(["resolve", "bytes=0-1", "--length", "x"])
    assert caught.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("usage: httprange resolve ")
    assert "\nhttprange resolve: error: argument --length: " in err
