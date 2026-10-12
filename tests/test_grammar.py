import pytest

from httprange import (
    MalformedRange,
    RangeRequest,
    RangeSpec,
    parse_accept_ranges,
    parse_range_request,
)


@pytest.mark.parametrize(
    ("value", "specs"),
    [
        # RFC 9110 14.1.2 examples.
        ("bytes=0-499", (RangeSpec(0, 499),)),
        ("bytes=500-999", (RangeSpec(500, 999),)),
        ("bytes=-500", (RangeSpec(None, 500),)),
        ("bytes=9500-", (RangeSpec(9500, None),)),
        ("bytes=0-0,-1", (RangeSpec(0, 0), RangeSpec(None, 1))),
        (
            "bytes= 0-999, 4500-5499, -1000",
            (RangeSpec(0, 999), RangeSpec(4500, 5499), RangeSpec(None, 1000)),
        ),
        ("bytes=500-600,601-999", (RangeSpec(500, 600), RangeSpec(601, 999))),
        ("bytes=500-700,601-999", (RangeSpec(500, 700), RangeSpec(601, 999))),
        # What browsers and curl -r send in the wild.
        ("bytes=0-", (RangeSpec(0, None),)),
        ("bytes=0-1", (RangeSpec(0, 1),)),
    ],
)
def test_parses_the_rfc_and_real_world_examples(value: str, specs: tuple[RangeSpec, ...]) -> None:
    request = parse_range_request(value)
    assert request == RangeRequest("bytes", specs)
    assert request.is_bytes


def test_range_units_are_case_insensitive() -> None:
    assert parse_range_request("Bytes=0-1").unit == "bytes"
    assert parse_range_request("BYTES=0-1").specs == (RangeSpec(0, 1),)


def test_ignores_a_bounded_number_of_empty_elements() -> None:
    assert parse_range_request("bytes=0-1,,2-3, ,").specs == (RangeSpec(0, 1), RangeSpec(2, 3))


def test_rejects_too_many_empty_elements() -> None:
    with pytest.raises(MalformedRange):
        parse_range_request("bytes=0-1" + "," * 17)
    assert parse_range_request("bytes=0-1,,,", max_empty=3).specs == (RangeSpec(0, 1),)


def test_keeps_other_units_raw() -> None:
    request = parse_range_request("items=1.2-4.3, 7")
    assert (request.unit, request.specs, request.other) == ("items", (), ("1.2-4.3", "7"))
    assert not request.is_bytes
    assert str(request) == "items=1.2-4.3,7"


def test_renders_the_canonical_form() -> None:
    assert str(parse_range_request("bytes= 0-999 , -1000")) == "bytes=0-999,-1000"


@pytest.mark.parametrize(
    "value",
    [
        "0-499",
        "bytes =0-499",
        "by tes=0-1",
        "=0-1",
        "bytes=",
        "bytes=,",
        "bytes=abc",
        "bytes=1-2-3",
        "bytes=-",
        "bytes=0 - 1",
        "bytes=500-100",
        "bytes=\u00b2-3",
        "bytes=\u0661-3",
        "bytes=+1-2",
        "bytes=" + "9" * 5000 + "-",
        "items=a b",
    ],
)
def test_rejects_invalid_specifiers(value: str) -> None:
    with pytest.raises(MalformedRange):
        parse_range_request(value)


def test_huge_but_reasonable_numbers_parse_exactly() -> None:
    big = 10**40
    assert parse_range_request(f"bytes=0-{big}").specs == (RangeSpec(0, big),)


def test_parses_accept_ranges() -> None:
    assert parse_accept_ranges("bytes") == ("bytes",)
    assert parse_accept_ranges("None") == ("none",)
    assert parse_accept_ranges("bytes, items") == ("bytes", "items")
    for value in ("", "by tes", ","):
        with pytest.raises(MalformedRange):
            parse_accept_ranges(value)
