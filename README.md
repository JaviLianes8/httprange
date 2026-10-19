# httprange

[![Lianes8 Certified](https://lianes8studio.com/certified/lianes8-certified-badge.svg)](https://lianes8studio.com/certified)

Parse and build HTTP Range and Content-Range headers (RFC 9110), zero dependencies, fully
typed.

`httprange` covers the whole of [RFC 9110 section 14](https://www.rfc-editor.org/rfc/rfc9110#section-14)
for a server or a client: the `Range` grammar, resolving ranges against a length, a
denial-of-service policy, `Content-Range` for 206 and 416, `multipart/byteranges` bodies,
`If-Range` evaluation and a one-call 200 / 206 / 416 decision. It also ships an
`httprange` command line tool.

## Install

```
pip install httprange
```

## Serve a range request in one call

```python
from httprange import build_multipart_byteranges, evaluate_range_request

decision = evaluate_range_request(
    method="GET",
    range_header="bytes=0-0,-1",  # the request's Range header, or None
    length=len(data),
    if_range=None,  # the request's If-Range header, if any
    etag='"v1"',  # current validators of the representation
)
decision.status  # 200, 206 or 416
decision.content_range  # None for a 200 or, as here, a multipart 206; else 'bytes 0-0/10000' or 'bytes */10000'
if decision.is_multipart:
    body = build_multipart_byteranges(data, decision.ranges, content_type="video/mp4")
    body.content_type  # 'multipart/byteranges; boundary=...'
```

The full recipe for a handler is in [GUIDE.md](https://github.com/JaviLianes8/httprange/blob/main/GUIDE.md).

## Building blocks

```python
from httprange import (
    parse_range_request,
    resolve_ranges,
    RangePolicy,
    parse_content_range,
    build_content_range,
    if_range_matches,
)

parse_range_request("bytes=0-499,-500").specs
# (RangeSpec(start=0, end=499), RangeSpec(start=None, end=500))

resolve_ranges("bytes=-500", 10000)
# (ByteRange(first=9500, last=9999),)

resolve_ranges("bytes=500-600,601-999", 10000)  # coalesced by default
# (ByteRange(first=500, last=999),)

resolve_ranges("bytes=0-0,0-0,0-0", 10)  # raises ExcessiveRanges

parse_content_range("bytes 42-1233/1234")
# ContentRange(unit='bytes', first=42, last=1233, complete_length=1234)

build_content_range(None, None, 1234)
# 'bytes */1234'

if_range_matches('"v1"', etag='"v1"')  # True
if_range_matches('W/"v1"', etag='W/"v1"')  # False: weak tags never match
```

The 0.1 API (`parse_range`, `resolve`, `RangeSpec.resolve`, `build_content_range`) keeps
its signatures and results for valid input. Every change since 0.2.0, mostly stricter
validation, is listed in the [CHANGELOG](https://github.com/JaviLianes8/httprange/blob/main/CHANGELOG.md).

## What the RFC says, and what this library does

| RFC 9110 | Behaviour |
|---|---|
| 14.1 | Range units are case-insensitive tokens: `Bytes=0-1` is valid. |
| 14.1.1 | `int-range`, `suffix-range` and `other-range`; `500-100` is invalid. Other units keep their specs as raw text. |
| 14.1.2 | Inclusive offsets from zero; a last position past the end is clamped; a suffix longer than the body selects all of it; a suffix of 0 is unsatisfiable. On an empty representation a non-zero suffix is satisfiable but selects nothing: `resolve_ranges` returns `()` and the decision is 200. Large numerals parse exactly, absurd ones raise a typed error. |
| 5.6.1.2 | Whitespace around commas and a bounded number of empty list elements are accepted. |
| 14.2 | `Range` is ignored for methods other than `GET` and for units other than `bytes`; an invalid header is ignored; more than `max_overlapping` (default 2) ranges covering one same byte or more than `max_ranges` (default 100) ranges raise `ExcessiveRanges` (a 416 decision by default). Specs are counted before their syntax is read, so a header with too many specs is refused even when one of them is invalid. |
| 14.3 | `parse_accept_ranges` reads `Accept-Ranges`, including `none`. |
| 14.4 | `Content-Range` for 206 (`bytes 0-499/1234`, `bytes 0-499/*`) and 416 (`bytes */1234`), with the validity rules enforced. |
| 14.6, 15.3.7.2 | `multipart/byteranges` builder and parser; parts keep request order after coalescing; the boundary is never quoted and never occurs in a part. Part positions must be integers, as the 14.4 grammar requires. |
| 13.1.5, 8.8.3.2 | `If-Range` with strong ETag comparison or an exact HTTP-date match. |
| 5.6.7 | IMF-fixdate, RFC 850 and asctime dates are all accepted. |
| 15.5.17 | A 416 decision carries `Content-Range: bytes */<length>`. |

Every error subclasses `RangeError`, which subclasses `ValueError`: `MalformedRange`,
`UnsatisfiableRange` (with `.length`), `UnsupportedRangeUnit` (with `.unit`),
`ExcessiveRanges`, `MalformedContentRange`, `MalformedMultipart` and `MalformedDate`.

## Command line

```
httprange parse "bytes=0-499,-500"
httprange resolve "bytes=-500" --length 10000           # bytes 9500-9999/10000
httprange content-range 0 499 --length 1234             # bytes 0-499/1234
httprange content-range --unsatisfied --length 1234     # bytes */1234
httprange parse-content-range "bytes 42-1233/*"
httprange decide --range "bytes=0-0,-1" --length 10000 --json
```

Errors go to stderr with exit status 1. `httprange --help` lists more examples.

## Why

RFC 9110 defines byte ranges once, but in Python the code that implements them lives
inside web frameworks, each with its own scope (checked on 2026-10-19 against the releases named):

- werkzeug 3.1.9 exports `parse_range_header` and friends, but it is a WSGI toolkit
  that depends on MarkupSafe, and its responses serve only a single range: a request for
  several ranges is answered with 416. It has no `multipart/byteranges` builder or
  parser.
- Starlette 1.9.0 serves single and multiple ranges from `FileResponse`, but the parser
  is a private method of that class.
- aiohttp 3.14.5 offers `request.http_range`, which describes one range as a `slice`
  and raises `ValueError` for a list of ranges.
- Django 6.1.2 does not handle `Range` in `HttpResponse`, `FileResponse` or the static
  file view.

`httprange` is the protocol part on its own: zero dependencies, fully typed, strict about
the grammar, with a denial-of-service policy, `If-Range`, the 416 rules and
`multipart/byteranges` in both directions. Use it in a plain WSGI or ASGI handler, a
static file server, a client that resumes downloads, or a test that checks a server's
206 replies. If your framework already serves the files you need, keep using it.

## License

MIT. See [LICENSE](https://github.com/JaviLianes8/httprange/blob/main/LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
