# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

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

### Changed

- Documentation now cites RFC 9110, which obsoletes RFC 7233.

## [0.1.0]

- First release: `parse_range` for `Range` headers, `RangeSpec.resolve` and `resolve`
  against a known length (suffix, open ended and unsatisfiable cases), and
  `build_content_range` for `Content-Range` replies. Zero dependencies, fully typed.
