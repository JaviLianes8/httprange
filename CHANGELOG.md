# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.1] - 2026-10-19

No behaviour change: the code answers exactly as 1.0.0 does. The documentation now
states the order the code already follows.

### Fixed

- The `evaluate_range_request` docstring, the GUIDE decision table and the README 14.2
  row give the rules in the order they apply. The unit and list of a header are read
  first, then the unit, then the specs are counted, and only then is each spec's
  syntax read: more than `policy.max_ranges` specs give 416 (`ExcessiveRanges` from
  `resolve_ranges`) even when one of them is invalid, while a lone invalid spec gives
  200. No satisfiable range gives 416 before the overlap limit is applied.
- The `parse_range_request` docstring says that spaces and tabs around the whole field
  value are ignored; whitespace between the unit and `=` is still refused.
- GUIDE section 6 gives both error prefixes of the command line: `httprange: error:`
  and, for a bad argument of a subcommand, `httprange <command>: error:` after the
  usage line.

## [1.0.0] - 2026-10-19

The public API is now stable: the thirty names in `httprange.__all__`, their
signatures, defaults and error types follow Semantic Versioning from this release on.
Every change below was checked against the 0.2.0 release from PyPI.

### Stable

- Range requests: `parse_range_request` and `RangeRequest` (the strict RFC 9110 14.1.1
  grammar), `parse_range`, `RangeSpec` and `resolve` (the 0.1 API), `parse_accept_ranges`.
- Resolution: `resolve_ranges`, `RangePolicy` and `ByteRange`.
- Replies: `parse_content_range`, `build_content_range` and `ContentRange`;
  `build_multipart_byteranges`, `encode_multipart_byteranges`,
  `parse_multipart_byteranges`, `BytePart` and `MultipartBody`.
- Preconditions and dates: `if_range_matches`, `parse_http_date` and `format_http_date`.
- Decisions: `evaluate_range_request` and `RangeDecision`.
- Errors: `RangeError` (a `ValueError`) and its subclasses `MalformedRange`,
  `UnsatisfiableRange`, `UnsupportedRangeUnit`, `ExcessiveRanges`,
  `MalformedContentRange`, `MalformedMultipart` and `MalformedDate`.
- The `httprange` command and its exit statuses.

### Added

- Every public name has a runnable example in its docstring.
- `python -m httprange` runs the command line tool.
- `build_multipart_byteranges` and `parse_multipart_byteranges` are annotated to take
  `bytes`, `bytearray` or `memoryview`, which they already accepted. So are the `data`
  of `BytePart` and the `body` of `MultipartBody`; the `ranges` of `RangeDecision` and
  the `specs` and `other` of `RangeRequest` are annotated to take a list as well as a
  tuple. The fields keep their types: the values are stored as `bytes` and tuples.

### Changed

- An argument of the wrong type raises `RangeError` instead of being used as given or
  leaking another exception: a `float` or `bool` length or total (0.2.0 accepted `5.0`
  and `True`), a non-integer `RangePolicy` limit, a non-`bool` `coalesce` or
  `date_is_strong`, a `bytes` method. The value classes check their fields the same way
  (0.2.0 stored any value): a `set` or generator for `RangeRequest.specs` or
  `RangeDecision.ranges` raises "must be a tuple or list", a `str` for `BytePart.data`
  or `MultipartBody.body` raises "must be bytes, bytearray or memoryview".
- `parse_range_request` raises `MalformedRange` for a `bytes` header (it leaked
  `TypeError`).
- `evaluate_range_request` and `if_range_matches` raise `RangeError` for a naive
  `last_modified` datetime whatever the `If-Range` holds (0.2.0 checked it only when
  `If-Range` was a date), and the decision's reason quotes a method that is not a token
  with `repr` (a token such as `HEAD` is shown as is).
- `ContentRange` stores its unit in lower case, so `ContentRange("BYTES", 0, 1, 2)`
  equals the parsed `bytes 0-1/2`.
- `RangeRequest` refuses a request with neither specs nor other-range items
  (`MalformedRange`); `RangeDecision` refuses fields that no decision can hold
  (`RangeError`); `BytePart` refuses data whose length differs from its `bytes`
  Content-Range (`MalformedMultipart`).
- Positions and lengths are limited to 4000 significant decimal digits (leading zeros
  are not counted), and `ByteRange` refuses
  wider ones with `RangeError`; results no longer depend on the interpreter's integer
  string conversion limit. `ByteRange.content_range` refuses a non-integer length.
- `resolve_ranges` raises `MalformedRange` for an empty sequence of specs (it raised
  `UnsatisfiableRange`).
- `resolve_ranges` and `evaluate_range_request` count specs before they check their
  syntax: more than `max_ranges` specs raise `ExcessiveRanges` from `resolve_ranges`
  and give 416 from `evaluate_range_request` even when a later spec is invalid (0.2.0
  raised `MalformedRange` and answered 200). 0.2.0 raised `ExcessiveRanges` (416) for
  any header holding at least `max_ranges` + 16 commas, before it looked at the unit or
  the list: such a header in a unit other than `bytes`, or one that also has more than
  16 empty list elements, now raises `MalformedRange` from `resolve_ranges` when its
  list is invalid, `UnsupportedRangeUnit` otherwise, and `evaluate_range_request`
  ignores it with 200.
- `if_range_matches` and `evaluate_range_request` raise `MalformedDate` for a
  `last_modified` string that is not an HTTP-date, whatever the headers hold (0.2.0
  treated it as missing, so the `If-Range` silently did not match); `httprange decide`
  exits with 1 for such a `--last-modified`. An `etag` that is not a strong entity-tag
  still never matches, as documented.
- `RangePolicy` limits (`max_ranges`, `max_overlapping`, `coalesce_gap`) have at most
  4000 digits, like positions and lengths; a wider one raises `RangeError`, so `repr` of
  a policy stays cheap.
- `ByteRange.overlaps` reads a `ByteRange` subclass through a checked copy of its
  fields: invalid fields raise `RangeError` (0.2.0 compared them as given, leaking
  `TypeError` or answering silently).
- `resolve_ranges`, `build_multipart_byteranges` and `encode_multipart_byteranges` raise
  their documented "must be ... iterable" error for an object whose `__iter__` returns
  something that is not an iterator (it leaked `TypeError`).
- `build_multipart_byteranges` refuses a `content_type` with leading or trailing
  whitespace, and reads a `memoryview` of any item size as its bytes (0.2.0 refused
  item sizes above one). `encode_multipart_byteranges` refuses parts that disagree on
  the complete length.
- `parse_multipart_byteranges` raises `MalformedMultipart` for whitespace around the `=`
  of a parameter, a repeated `boundary` parameter, a part with two `Content-Type` fields,
  and parts that use different range units; 0.2.0 accepted all four.
- `parse_http_date` reads a two-digit RFC 850 year as the latest year with those digits
  that is not more than 50 years after `now`, comparing the full instant (RFC 9110
  5.6.7). 0.2.0 never chose the next century (`10` read in 2090 gave 2010, now 2110),
  compared the date without its time of day, and leaked `ValueError` for a `now` near
  year 9999.
- `format_http_date` raises `RangeError` for an instant before year 1 in UTC (it leaked
  `OverflowError`).
- `if_range_matches` and `evaluate_range_request` match a leap second (`:60`) only with
  itself: 0.2.0 read it as `:59` and served the range for a validator of that second.
- A `datetime` (`when`, `now`, `last_modified`) is read through the `datetime` class, so
  a subclass's own `astimezone`, `utcoffset` or `weekday` no longer changes a result,
  and a `tzinfo` that returns an invalid offset raises `RangeError` (it leaked
  `ValueError` or `TypeError`). Likewise `resolve_ranges`, `build_multipart_byteranges`,
  `encode_multipart_byteranges`, `BytePart`, `RangeDecision` and `RangeRequest` read
  subclasses of `RangeSpec`, `ByteRange`, `ContentRange`, `BytePart` and `RangePolicy` by
  their fields only: `RangeDecision.ranges`, `BytePart.content_range` and
  `RangeRequest.specs` hold plain instances, so `str` of a `RangeRequest` is always the
  canonical header value (0.2.0 called each spec's own `__str__`).
- `UnsatisfiableRange.args` and `UnsupportedRangeUnit.args` hold the message only (0.2.0
  added the length or the unit, so `repr` of the error could echo a huge unit); the
  `length` and `unit` attributes are unchanged.
- `repr` of `RangeSpec`, `ByteRange`, `ContentRange`, `RangeRequest`, `RangeDecision` and
  `RangePolicy`, and `str` of `RangeDecision`, work under any
  `sys.set_int_max_str_digits` limit.
- Error messages quote at most 40 characters of any input; the command line tool cuts
  its messages to 200 characters, takes lengths of up to 4000 digits and exits with 1
  when the reader of its output goes away, `--help` and `--version` included (they
  exited with 120).
- The public classes and functions report `httprange` as their module, so their pickles
  do not depend on private module names and `doctest.testmod(httprange)` runs every
  example. The package no longer exposes the `annotations` name that
  `from __future__ import annotations` left in 0.2.0.
- `Development Status :: 5 - Production/Stable`.

## [0.2.0] - 2026-10-17

### Added

- `parse_range_request` and `RangeRequest`: the strict RFC 9110 14.1.1 grammar, with
  case-insensitive units, the 5.6.1.2 list rules and raw `other-range` specs.
- `resolve_ranges`, `RangePolicy` and `ByteRange`: resolution against a length with a
  cap on range count and overlapping ranges, and optional coalescing that keeps request
  order.
- `parse_content_range` and `ContentRange` for 206 and 416 values; `build_content_range`
  takes an optional `unit`.
- `build_multipart_byteranges`, `encode_multipart_byteranges`,
  `parse_multipart_byteranges`, `BytePart` and `MultipartBody`.
- `if_range_matches`, `parse_http_date` and `format_http_date` (RFC 9110 13.1.5, 5.6.7).
- `evaluate_range_request` and `RangeDecision`: one call from request headers to a 200,
  206 or 416 answer with the exact `Content-Range`.
- `parse_accept_ranges`.
- Errors `UnsupportedRangeUnit`, `ExcessiveRanges`, `MalformedContentRange`,
  `MalformedMultipart` and `MalformedDate`; `UnsatisfiableRange.length`.
- `RangeSpec.byte_range` and `str(RangeSpec)`.
- The `httprange` command: `parse`, `resolve`, `content-range`, `parse-content-range`
  and `decide`.
- `GUIDE.md` with a complete server recipe.

### Fixed

- Non-ASCII digits are rejected as `MalformedRange`; superscript digits used to escape
  as a bare `ValueError`.
- Numerals too long to convert raise `MalformedRange` instead of a bare `ValueError`.
- `parse_range` accepts the `bytes` unit in any case, as RFC 9110 14.1 requires.
- `build_content_range` rejects a negative total.
- `RangeSpec` rejects shapes the grammar cannot express (no positions, negative
  positions, last before first).
- A negative `total` raises `RangeError` (still a `ValueError`).
- `RangeSpec`, `ByteRange` and `build_content_range` reject non-integer positions,
  including booleans.

### Changed

- Documentation now cites RFC 9110, which obsoletes RFC 7233.

## [0.1.0] - 2026-10-12

Never published on PyPI; its source is commit 3e75ac8.

- First release: `parse_range` for `Range` headers, `RangeSpec.resolve` and `resolve`
  against a known length (suffix, open ended and unsatisfiable cases), and
  `build_content_range` for `Content-Range` replies. Zero dependencies, fully typed.
