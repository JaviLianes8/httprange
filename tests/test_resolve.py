import pytest

from httprange import (
    ByteRange,
    ExcessiveRanges,
    MalformedRange,
    RangeError,
    RangePolicy,
    RangeSpec,
    UnsatisfiableRange,
    UnsupportedRangeUnit,
    resolve_ranges,
)

NO_MERGE = RangePolicy(coalesce=False)


def test_byte_range_basics() -> None:
    item = ByteRange(500, 999)
    assert (item.length, str(item)) == (500, "500-999")
    data = bytes(range(256))
    assert data[ByteRange(10, 12).as_slice()] == bytes([10, 11, 12])
    assert item.content_range(8000) == "bytes 500-999/8000"
    assert item.content_range(None) == "bytes 500-999/*"
    assert item.overlaps(ByteRange(999, 1200)) and not item.overlaps(ByteRange(1000, 1001))


@pytest.mark.parametrize(("first", "last"), [(-1, 3), (5, 4), (True, 3), (0, 3.0)])
def test_byte_range_rejects_invalid_bounds(first: int, last: int) -> None:
    with pytest.raises(RangeError):
        ByteRange(first, last)


def test_byte_range_rejects_a_complete_length_not_above_last() -> None:
    with pytest.raises(RangeError):
        ByteRange(0, 9).content_range(9)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        # RFC 9110 14.1.2, representation of length 10000.
        ("bytes=-500", (ByteRange(9500, 9999),)),
        ("bytes=9500-", (ByteRange(9500, 9999),)),
        ("bytes=0-0,-1", (ByteRange(0, 0), ByteRange(9999, 9999))),
        (
            "bytes= 0-999, 4500-5499, -1000",
            (ByteRange(0, 999), ByteRange(4500, 5499), ByteRange(9000, 9999)),
        ),
        ("bytes=0-20000", (ByteRange(0, 9999),)),
        ("bytes=-20000", (ByteRange(0, 9999),)),
        ("bytes=0-99,20000-", (ByteRange(0, 99),)),
    ],
)
def test_resolves_rfc_examples(header: str, expected: tuple[ByteRange, ...]) -> None:
    assert resolve_ranges(header, 10000, policy=NO_MERGE) == expected


def test_non_canonical_second_half_coalesces_to_one_range() -> None:
    assert resolve_ranges("bytes=500-600,601-999", 10000) == (ByteRange(500, 999),)
    assert resolve_ranges("bytes=500-700,601-999", 10000) == (ByteRange(500, 999),)


def test_coalescing_keeps_request_order() -> None:
    header = "bytes=900-999,0-9,5-19"
    assert resolve_ranges(header, 1000) == (ByteRange(900, 999), ByteRange(0, 19))


def test_coalesce_gap_merges_nearby_ranges() -> None:
    policy = RangePolicy(coalesce_gap=80)
    assert resolve_ranges("bytes=0-9,90-99", 1000, policy=policy) == (ByteRange(0, 99),)
    assert resolve_ranges("bytes=0-9,91-99", 1000, policy=policy) == (
        ByteRange(0, 9),
        ByteRange(91, 99),
    )


def test_accepts_spec_objects() -> None:
    specs = [RangeSpec(None, 10), RangeSpec(0, 4)]
    assert resolve_ranges(specs, 100) == (ByteRange(90, 99), ByteRange(0, 4))


def test_unsatisfiable_set_carries_the_length() -> None:
    with pytest.raises(UnsatisfiableRange) as info:
        resolve_ranges("bytes=100-,-0", 100)
    assert info.value.length == 100


def test_empty_representation_with_a_suffix_selects_nothing() -> None:
    # RFC 9110 14.1.2: on a zero-length representation only a non-zero suffix-range is
    # satisfiable, and it selects no bytes.
    assert resolve_ranges("bytes=-5", 0) == ()
    assert resolve_ranges("bytes=0-1,-5", 0) == ()
    for header in ("bytes=0-1", "bytes=-0", "bytes=0-"):
        with pytest.raises(UnsatisfiableRange):
            resolve_ranges(header, 0)


def test_huge_headers_are_refused_before_parsing() -> None:
    with pytest.raises(ExcessiveRanges):
        resolve_ranges("bytes=" + "0-0," * 200_000, 10)


def test_too_many_ranges_are_excessive() -> None:
    header = "bytes=" + ",".join(f"{i * 2}-{i * 2}" for i in range(101))
    with pytest.raises(ExcessiveRanges):
        resolve_ranges(header, 10**6)
    assert len(resolve_ranges(header, 10**6, policy=RangePolicy(max_ranges=101))) == 101


def test_more_than_two_overlapping_ranges_are_excessive() -> None:
    with pytest.raises(ExcessiveRanges):
        resolve_ranges("bytes=0-0,0-0,0-0", 10)
    with pytest.raises(ExcessiveRanges):
        resolve_ranges("bytes=0-100,10-20,15-30", 1000)
    assert resolve_ranges("bytes=0-5,3-9", 10) == (ByteRange(0, 9),)
    policy = RangePolicy(max_overlapping=3)
    assert resolve_ranges("bytes=0-0,0-0,0-0", 10, policy=policy) == (ByteRange(0, 0),)


def test_overlap_is_measured_at_a_single_byte() -> None:
    # Two separate overlapping pairs and a chain never stack three ranges on one byte.
    assert resolve_ranges("bytes=0-1,1-2,10-11,11-12", 20) == (ByteRange(0, 2), ByteRange(10, 12))
    assert resolve_ranges("bytes=0-5,3-8,6-10", 20) == (ByteRange(0, 10),)


def test_adjacent_ranges_do_not_count_as_overlapping() -> None:
    assert resolve_ranges("bytes=0-1,2-3,4-5,6-7", 10) == (ByteRange(0, 7),)


def test_other_units_and_invalid_headers_raise_typed_errors() -> None:
    with pytest.raises(UnsupportedRangeUnit) as info:
        resolve_ranges("items=0-1", 10)
    assert info.value.unit == "items"
    with pytest.raises(MalformedRange):
        resolve_ranges("bytes=5-1", 10)


def test_policy_and_length_are_validated() -> None:
    for kwargs in ({"max_ranges": 0}, {"max_overlapping": -1}, {"coalesce_gap": -1}):
        with pytest.raises(RangeError):
            RangePolicy(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(RangeError):
        resolve_ranges("bytes=0-1", -1)
