import pytest

from httprange import RangeError, build_content_range


def test_builds_a_satisfied_content_range() -> None:
    assert build_content_range(0, 499, 1234) == "bytes 0-499/1234"


def test_builds_the_unsatisfiable_form() -> None:
    assert build_content_range(None, None, 1234) == "bytes */1234"


def test_builds_with_an_unknown_total() -> None:
    assert build_content_range(0, 499, None) == "bytes 0-499/*"


def test_rejects_an_unsatisfiable_form_without_a_total() -> None:
    with pytest.raises(RangeError):
        build_content_range(None, None, None)


def test_rejects_a_half_open_pair() -> None:
    with pytest.raises(RangeError):
        build_content_range(0, None, 1234)


def test_rejects_an_end_before_the_start() -> None:
    with pytest.raises(RangeError):
        build_content_range(499, 0, 1234)


def test_rejects_a_negative_start() -> None:
    with pytest.raises(RangeError):
        build_content_range(-1, 10, 1234)


def test_rejects_a_range_past_the_total() -> None:
    with pytest.raises(RangeError):
        build_content_range(0, 1234, 1234)


def test_builds_another_unit_and_rejects_a_bad_one() -> None:
    assert build_content_range(1, 4, 25, unit="items") == "items 1-4/25"
    with pytest.raises(RangeError):
        build_content_range(1, 4, 25, unit="it ems")


def test_rejects_a_negative_total() -> None:
    with pytest.raises(RangeError):
        build_content_range(None, None, -1)


@pytest.mark.parametrize("args", [(True, 1, 2), (0, 1.0, 2), (0, 1, "2")])
def test_rejects_non_integer_arguments(args: tuple[object, object, object]) -> None:
    with pytest.raises(RangeError):
        build_content_range(*args)  # type: ignore[arg-type]
