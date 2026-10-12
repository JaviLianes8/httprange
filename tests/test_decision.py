from datetime import datetime, timezone

import pytest

from httprange import ByteRange, RangeError, RangePolicy, evaluate_range_request

LAST_MODIFIED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
STAMP = "Fri, 02 Jan 2026 03:04:05 GMT"


def decide(header: str | None, length: int = 10000, **kwargs: object):  # type: ignore[no-untyped-def]
    return evaluate_range_request(method="GET", range_header=header, length=length, **kwargs)  # type: ignore[arg-type]


def test_single_range_is_a_single_part_206() -> None:
    decision = decide("bytes=-500")
    assert (decision.status, decision.ranges) == (206, (ByteRange(9500, 9999),))
    assert decision.content_range == "bytes 9500-9999/10000"
    assert not decision.is_multipart


def test_multiple_ranges_are_multipart_without_a_header_content_range() -> None:
    decision = decide("bytes=0-0,-1")
    assert decision.status == 206 and decision.is_multipart
    assert decision.content_range is None


def test_unsatisfiable_is_416_with_the_length() -> None:
    decision = decide("bytes=50000-", length=47022)
    assert (decision.status, decision.ranges) == (416, ())
    assert decision.content_range == "bytes */47022"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"header": None}, "no Range"),
        ({"header": "bytes=abc"}, "invalid"),
        ({"header": "items=0-1"}, "unit"),
        ({"header": "bytes=0-1", "length": 0}, "empty"),
    ],
)
def test_ignored_ranges_give_200(kwargs: dict[str, object], reason: str) -> None:
    decision = decide(**kwargs)  # type: ignore[arg-type]
    assert (decision.status, decision.ranges, decision.content_range) == (200, (), None)
    assert reason in decision.reason


@pytest.mark.parametrize("method", ["HEAD", "POST", "PUT", "get"])
def test_range_is_ignored_for_methods_other_than_get(method: str) -> None:
    decision = evaluate_range_request(method=method, range_header="bytes=0-1", length=10)
    assert decision.status == 200


def test_excessive_ranges_are_rejected_or_ignored() -> None:
    header = "bytes=0-0,0-0,0-0"
    rejected = decide(header)
    assert (rejected.status, rejected.content_range) == (416, "bytes */10000")
    assert decide(header, on_excessive="ignore").status == 200
    assert decide(header, policy=RangePolicy(max_overlapping=3)).status == 206


def test_if_range_with_matching_etag_serves_the_range() -> None:
    assert decide("bytes=0-9", if_range='"v1"', etag='"v1"').status == 206
    assert decide("bytes=0-9", if_range='"v1"', etag='"v2"').status == 200
    assert decide("bytes=0-9", if_range='W/"v1"', etag='W/"v1"').status == 200


def test_if_range_with_a_date() -> None:
    assert decide("bytes=0-9", if_range=STAMP, last_modified=LAST_MODIFIED).status == 206
    assert decide("bytes=0-9", if_range=STAMP, last_modified=STAMP).status == 206
    weak = decide("bytes=0-9", if_range=STAMP, last_modified=LAST_MODIFIED, date_is_strong=False)
    assert weak.status == 200


def test_if_range_without_range_is_ignored() -> None:
    assert decide(None, if_range='"v1"', etag='"v2"').reason == "no Range header"


def test_rejects_a_negative_length() -> None:
    with pytest.raises(RangeError):
        decide("bytes=0-1", length=-1)
