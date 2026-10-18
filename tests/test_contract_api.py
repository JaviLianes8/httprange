"""The complete promise of every public name: signature, fields, members, errors, pickles.

The signatures, fields and defaults are those of 0.2.0, kept for 1.0.0.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import pickle

import pytest

import httprange as hr

POLICY = "RangePolicy(max_ranges=100, max_overlapping=2, coalesce=True, coalesce_gap=0)"
SIGNATURES = {
    "build_content_range": "(start: 'int | None', end: 'int | None', total: 'int | None', *, "
    "unit: 'str' = 'bytes') -> 'str'",
    "build_multipart_byteranges": "(data: 'bytes', ranges: 'Iterable[ByteRange]', *, "
    "content_type: 'str | None' = None, boundary: 'str | None' = None) -> 'MultipartBody'",
    "encode_multipart_byteranges": "(parts: 'Iterable[BytePart]', *, "
    "boundary: 'str | None' = None) -> 'MultipartBody'",
    "evaluate_range_request": "(*, method: 'str', range_header: 'str | None', length: 'int', "
    "if_range: 'str | None' = None, etag: 'str | None' = None, "
    "last_modified: 'datetime | str | None' = None, date_is_strong: 'bool' = True, "
    f"policy: 'RangePolicy' = {POLICY}, "
    "on_excessive: \"Literal['reject', 'ignore']\" = 'reject') -> 'RangeDecision'",
    "format_http_date": "(when: 'datetime') -> 'str'",
    "if_range_matches": "(if_range: 'str', *, etag: 'str | None' = None, "
    "last_modified: 'datetime | str | None' = None, date_is_strong: 'bool' = True) -> 'bool'",
    "parse_accept_ranges": "(value: 'str', *, max_empty: 'int' = 16) -> 'tuple[str, ...]'",
    "parse_content_range": "(value: 'str') -> 'ContentRange'",
    "parse_http_date": "(value: 'str', *, now: 'datetime | None' = None) -> 'datetime'",
    "parse_multipart_byteranges": "(body: 'bytes', content_type: 'str', *, "
    "max_parts: 'int' = 1000) -> 'tuple[BytePart, ...]'",
    "parse_range": "(value: 'str') -> 'list[RangeSpec]'",
    "parse_range_request": "(value: 'str', *, max_empty: 'int' = 16) -> 'RangeRequest'",
    "resolve": "(header: 'str', total: 'int') -> 'list[tuple[int, int]]'",
    "resolve_ranges": "(ranges: 'str | Iterable[RangeSpec]', length: 'int', *, "
    f"policy: 'RangePolicy' = {POLICY}) -> 'tuple[ByteRange, ...]'",
}
MISSING = dataclasses.MISSING
FIELDS: dict[type, tuple[list[tuple[str, object]], list[str]]] = {
    hr.BytePart: ([("content_range", MISSING), ("data", MISSING), ("content_type", None)], []),
    hr.ByteRange: (
        [("first", MISSING), ("last", MISSING)],
        ["as_slice", "content_range", "length", "overlaps"],
    ),
    hr.ContentRange: (
        [("unit", MISSING), ("first", MISSING), ("last", MISSING), ("complete_length", MISSING)],
        ["is_satisfied", "length"],
    ),
    hr.MultipartBody: (
        [("content_type", MISSING), ("body", MISSING), ("boundary", MISSING)],
        ["content_length"],
    ),
    hr.RangeDecision: (
        [("status", MISSING), ("ranges", MISSING), ("length", MISSING), ("reason", MISSING)],
        ["content_range", "is_multipart"],
    ),
    hr.RangePolicy: (
        [("max_ranges", 100), ("max_overlapping", 2), ("coalesce", True), ("coalesce_gap", 0)],
        [],
    ),
    hr.RangeRequest: ([("unit", MISSING), ("specs", ()), ("other", ())], ["is_bytes"]),
    hr.RangeSpec: (
        [("start", MISSING), ("end", MISSING)],
        ["byte_range", "is_suffix", "resolve"],
    ),
}
SAMPLES = [
    hr.BytePart(hr.ContentRange("bytes", 0, 1, 9), b"ab", "text/plain"),
    hr.ByteRange(3, 9),
    hr.ContentRange("bytes", None, None, 7),
    hr.MultipartBody("multipart/byteranges; boundary=b", b"--b--\r\n", "b"),
    hr.RangeDecision(206, (hr.ByteRange(0, 0), hr.ByteRange(4, 4)), 5, "two"),
    hr.RangePolicy(max_ranges=3, coalesce=False),
    hr.RangeRequest("items", other=("a", "1-2")),
    hr.RangeSpec(None, 5),
]


@pytest.mark.parametrize("name", sorted(SIGNATURES))
def test_function_signatures_are_pinned(name: str) -> None:
    assert str(inspect.signature(getattr(hr, name))) == SIGNATURES[name]


def test_every_function_is_pinned() -> None:
    functions = [name for name in hr.__all__ if inspect.isfunction(getattr(hr, name))]
    assert sorted(functions) == sorted(SIGNATURES)


@pytest.mark.parametrize("cls", list(FIELDS), ids=lambda cls: cls.__name__)
def test_value_classes_are_frozen_dataclasses_with_pinned_fields(cls: type) -> None:
    fields, members = FIELDS[cls]
    assert [(f.name, f.default) for f in dataclasses.fields(cls)] == fields
    public = sorted(m for m in vars(cls) if not m.startswith("_") and m not in dict(fields))
    assert public == members
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert cls.__module__ == "httprange"


@pytest.mark.parametrize("value", SAMPLES, ids=lambda value: type(value).__name__)
def test_values_pickle_copy_hash_and_refuse_assignment(value: object) -> None:
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        again = pickle.loads(pickle.dumps(value, protocol))
        assert again == value and type(again) is type(value)
        assert hash(again) == hash(value)
    assert copy.copy(value) == value == copy.deepcopy(value)
    assert dataclasses.replace(value) == value  # type: ignore[type-var]
    assert b"httprange._" not in pickle.dumps(value)  # pickles name httprange.<Name>
    with pytest.raises(dataclasses.FrozenInstanceError):
        object.__getattribute__(value, "__setattr__")(dataclasses.fields(value)[0].name, None)  # type: ignore[arg-type]


def test_errors_keep_their_hierarchy_attributes_and_pickles() -> None:
    errors = [getattr(hr, name) for name in hr.__all__ if name[0].isupper()]
    errors = [cls for cls in errors if issubclass(cls, BaseException)]
    assert len(errors) == 8
    for cls in errors:
        assert issubclass(cls, hr.RangeError) and issubclass(hr.RangeError, ValueError)
        assert cls.__module__ == "httprange"
    unsatisfiable = pickle.loads(pickle.dumps(hr.UnsatisfiableRange("none fit", 7)))
    assert (str(unsatisfiable), unsatisfiable.length) == ("none fit", 7)
    assert unsatisfiable.args == ("none fit", 7)
    unsupported = pickle.loads(pickle.dumps(hr.UnsupportedRangeUnit("no", "items")))
    assert (str(unsupported), unsupported.unit) == ("no", "items")
    assert hr.UnsatisfiableRange("m").length is None and hr.UnsupportedRangeUnit("m").unit == ""
    empty = inspect.Parameter.empty
    for cls, extra in (
        (hr.UnsatisfiableRange, ("length", None)),
        (hr.UnsupportedRangeUnit, ("unit", "")),
    ):
        params = inspect.signature(cls).parameters.values()
        assert [(p.name, p.default) for p in params] == [("message", empty), extra]


def test_every_public_name_and_member_has_a_runnable_example() -> None:
    for name in hr.__all__:
        obj = getattr(hr, name)
        assert ">>> " in (inspect.getdoc(obj) or ""), name
    for cls, (_, members) in FIELDS.items():
        for member in members:
            assert ">>> " in (inspect.getdoc(getattr(cls, member)) or ""), (cls, member)


def test_the_package_exports_nothing_else() -> None:
    public = sorted(name for name in dir(hr) if not name.startswith("_"))
    assert public == sorted(hr.__all__)
