import pytest

from httprange import ContentRange, MalformedContentRange, parse_content_range


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # RFC 9110 14.4 examples.
        ("bytes 42-1233/1234", ContentRange("bytes", 42, 1233, 1234)),
        ("bytes 42-1233/*", ContentRange("bytes", 42, 1233, None)),
        ("bytes */1234", ContentRange("bytes", None, None, 1234)),
        ("bytes 0-499/1234", ContentRange("bytes", 0, 499, 1234)),
        ("bytes 500-999/1234", ContentRange("bytes", 500, 999, 1234)),
        ("bytes 500-1233/1234", ContentRange("bytes", 500, 1233, 1234)),
        ("bytes 734-1233/1234", ContentRange("bytes", 734, 1233, 1234)),
        # RFC 9110 15.3.7.1 and 15.5.17.
        ("bytes 21010-47021/47022", ContentRange("bytes", 21010, 47021, 47022)),
        ("bytes */47022", ContentRange("bytes", None, None, 47022)),
        # Unit names are case-insensitive.
        ("Bytes 0-0/1", ContentRange("bytes", 0, 0, 1)),
    ],
)
def test_parses_rfc_examples(value: str, expected: ContentRange) -> None:
    parsed = parse_content_range(value)
    assert parsed == expected
    assert str(parsed) == value.replace("Bytes", "bytes")


def test_reports_satisfaction_and_length() -> None:
    assert parse_content_range("bytes 0-499/1234").length == 500
    assert parse_content_range("bytes 0-499/1234").is_satisfied
    unsatisfied = parse_content_range("bytes */1234")
    assert (unsatisfied.is_satisfied, unsatisfied.length) == (False, None)


@pytest.mark.parametrize(
    "value",
    [
        "bytes 500-499/1234",
        "bytes 0-1234/1234",
        "bytes 0-1234/1000",
        "bytes */*",
        "bytes 0-499",
        "bytes  0-499/1234",
        "bytes=0-499/1234",
        "bytes 0-/1234",
        "bytes -499/1234",
        "bytes 0-499/12a",
        "by tes 0-1/2",
        "bytes0-499/1234",
        "bytes \u0661-2/3",
    ],
)
def test_rejects_invalid_values(value: str) -> None:
    with pytest.raises(MalformedContentRange):
        parse_content_range(value)


def test_construction_enforces_validity() -> None:
    with pytest.raises(MalformedContentRange):
        ContentRange("bytes", 10, 5, 100)
    with pytest.raises(MalformedContentRange):
        ContentRange("bytes", None, None, None)
