import pytest

from httprange import (
    MalformedRange,
    RangeError,
    RangeSpec,
    UnsatisfiableRange,
    parse_range,
    resolve,
)


def test_parses_a_single_range() -> None:
    assert parse_range("bytes=0-499") == [RangeSpec(0, 499)]


def test_parses_a_multi_range_set_in_order() -> None:
    assert parse_range("bytes=0-499,1000-") == [RangeSpec(0, 499), RangeSpec(1000, None)]


def test_parses_a_suffix_range() -> None:
    spec = parse_range("bytes=-500")[0]
    assert spec == RangeSpec(None, 500)
    assert spec.is_suffix


def test_parses_an_open_ended_range() -> None:
    spec = parse_range("bytes=1000-")[0]
    assert spec == RangeSpec(1000, None)
    assert not spec.is_suffix


def test_tolerates_whitespace_and_empty_parts() -> None:
    assert parse_range(" bytes = 0-9 , 20-29 ,") == [RangeSpec(0, 9), RangeSpec(20, 29)]


@pytest.mark.parametrize(
    "value",
    ["0-499", "items=0-499", "bytes=", "bytes=abc", "bytes=1-2-3", "bytes=-", "bytes=,"],
)
def test_rejects_malformed_input(value: str) -> None:
    with pytest.raises(MalformedRange):
        parse_range(value)


def test_rejects_a_last_byte_before_the_first() -> None:
    with pytest.raises(MalformedRange):
        parse_range("bytes=500-100")


def test_resolves_a_closed_range_against_length() -> None:
    assert RangeSpec(0, 499).resolve(1234) == (0, 499)


def test_clamps_an_end_past_the_length() -> None:
    assert RangeSpec(0, 499).resolve(200) == (0, 199)


def test_resolves_an_open_ended_range_to_the_last_byte() -> None:
    assert RangeSpec(1000, None).resolve(1234) == (1000, 1233)


def test_resolves_a_suffix_range_from_the_end() -> None:
    assert RangeSpec(None, 500).resolve(1234) == (734, 1233)


def test_suffix_longer_than_body_returns_the_whole_body() -> None:
    assert RangeSpec(None, 5000).resolve(1234) == (0, 1233)


def test_detects_an_unsatisfiable_start_past_the_end() -> None:
    with pytest.raises(UnsatisfiableRange):
        RangeSpec(2000, None).resolve(1234)


def test_detects_an_unsatisfiable_zero_length_suffix() -> None:
    with pytest.raises(UnsatisfiableRange):
        RangeSpec(None, 0).resolve(1234)


def test_detects_an_unsatisfiable_range_on_empty_body() -> None:
    with pytest.raises(UnsatisfiableRange):
        RangeSpec(0, 0).resolve(0)


def test_resolve_header_drops_unsatisfiable_specs() -> None:
    assert resolve("bytes=0-99,5000-6000", 1234) == [(0, 99)]


def test_resolve_header_raises_when_nothing_is_satisfiable() -> None:
    with pytest.raises(UnsatisfiableRange):
        resolve("bytes=5000-6000", 1234)


def test_lenient_parser_accepts_any_unit_case() -> None:
    assert parse_range("Bytes=0-9") == [RangeSpec(0, 9)]


@pytest.mark.parametrize("value", ["bytes=\u00b2-3", "bytes=0-\u0663", "bytes=" + "9" * 5000 + "-"])
def test_lenient_parser_raises_malformed_for_odd_numerals(value: str) -> None:
    with pytest.raises(MalformedRange):
        parse_range(value)


@pytest.mark.parametrize(("start", "end"), [(None, None), (-1, 5), (0, -1), (9, 3)])
def test_spec_rejects_shapes_the_grammar_cannot_express(start: int | None, end: int | None) -> None:
    with pytest.raises(MalformedRange):
        RangeSpec(start, end)


def test_spec_renders_and_resolves_to_a_byte_range() -> None:
    assert [str(RangeSpec(0, 499)), str(RangeSpec(9500, None)), str(RangeSpec(None, 500))] == [
        "0-499",
        "9500-",
        "-500",
    ]
    item = RangeSpec(None, 500).byte_range(10000)
    assert (item.first, item.last, item.length) == (9500, 9999, 500)


def test_unsatisfiable_errors_carry_the_length() -> None:
    with pytest.raises(UnsatisfiableRange) as info:
        resolve("bytes=5000-6000", 1234)
    assert info.value.length == 1234


def test_negative_total_is_a_range_error() -> None:
    with pytest.raises(RangeError):
        RangeSpec(0, 1).resolve(-1)
