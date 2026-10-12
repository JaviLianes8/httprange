# Improvement round

The 0.1.0 release parses a `Range` header, resolves it against a length and builds a
`Content-Range` value. It still leaves a server author to hand-roll most of RFC 9110
section 14. This round closes that gap with an additive API. Ranked by impact.

## 1. Strict RFC 9110 grammar (`parse_range_request`, `RangeRequest`)

- Range units are case-insensitive tokens (RFC 9110 14.1). `Bytes=0-1` is valid.
- `ranges-specifier = range-unit "=" range-set`, with list rules from 5.6.1.2: OWS
  around commas, a bounded number of empty elements, at least one range-spec.
- Other range units keep their `other-range` items raw instead of being rejected, so a
  server can tell "unknown unit, ignore" (14.2, MUST) apart from "invalid, ignore or
  reject" (14.2, MAY).
- Digits are ASCII only. `str.isdigit` accepted superscript two (U+00B2), which crashed
  `int()` with a bare `ValueError`, and accepted non-ASCII digits that the grammar
  forbids.
- Huge numerals raise a typed error instead of tripping the interpreter's integer
  conversion limit (14.1.2 asks recipients to guard against conversion overflow).

## 2. Resolution policy with a DoS guard (`resolve_ranges`, `RangePolicy`, `ByteRange`)

- `ByteRange` is a frozen, validated, inclusive pair with `length`, `as_slice()` and
  `content_range(...)`.
- `RangePolicy` caps the number of range-specs and the number of overlapping ranges
  (14.2: "more than two overlapping ranges ... MAY ignore or reject"; 15.5.17).
- Optional coalescing of overlapping, adjacent and nearby ranges (15.3.7.2), keeping the
  order in which the specs were requested.

## 3. Content-Range parsing (`parse_content_range`, `ContentRange`)

- Full 14.4 grammar for 206 (`bytes 0-499/1234`, `bytes 0-499/*`) and 416
  (`bytes */1234`), including the invalidity rules (last before first, complete length
  not above last).
- `build_content_range` gains an optional `unit` and rejects a negative total.

## 4. multipart/byteranges (`build_multipart_byteranges`, `parse_multipart_byteranges`)

- Builder for the 206 multi-part body (14.6, 15.3.7.2) with a safe, unquoted, random
  boundary that never occurs inside a part.
- Parser for clients: accepts a preamble and extra CRLFs (14.6 note 1), quoted boundary,
  transport padding, and checks every part's size against its Content-Range.

## 5. If-Range evaluation (`if_range_matches`, `parse_http_date`, `format_http_date`)

- 13.1.5: strong ETag comparison (8.8.3.2), weak tags never match, exact date match.
- All three HTTP-date formats (5.6.7), with the 50-year rule for two-digit years.

## 6. One-call server decision (`evaluate_range_request`, `RangeDecision`)

- Method, If-Range, unknown unit, invalid header, empty representation, excessive
  ranges and unsatisfiable sets mapped to 200 / 206 / 416 with the exact Content-Range.

## 7. Accept-Ranges (`parse_accept_ranges`)

- 14.3 list of range units, lower-cased, `none` recognised.

## 8. Honest typed errors

- `UnsupportedRangeUnit`, `ExcessiveRanges`, `MalformedContentRange`,
  `MalformedMultipart` and `MalformedDate`, all under `RangeError` (a `ValueError`).
  `UnsatisfiableRange` carries the representation length for the 416 reply.

## 9. Command line tool

- `httprange parse | resolve | content-range | parse-content-range | decide`, with
  `--json`, runnable examples in `--help`, errors on stderr and exit status 1.

## 10. Proof

- A contract test per public name using the RFC examples.
- A real local HTTP server built on the library, fetched with `urllib` and real `Range`
  headers (206, 416, 200, exact bytes, multipart round trip).
- A wheel built and installed into a throwaway virtual environment, driving the real
  `httprange` script.
- `GUIDE.md` with a complete server recipe.
