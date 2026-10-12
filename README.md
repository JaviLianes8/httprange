# httprange

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
decision.content_range  # None here (multipart); 'bytes 0-0/10000' or 'bytes */10000' otherwise
if decision.is_multipart:
    body = build_multipart_byteranges(data, decision.ranges, content_type="video/mp4")
    body.content_type  # 'multipart/byteranges; boundary=...'
```

The full recipe for a handler is in [GUIDE.md](GUIDE.md).

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
its signatures and results for valid input; validation is stricter, as listed under
"Fixed" in the [CHANGELOG](CHANGELOG.md).

## What the RFC says, and what this library does

| RFC 9110 | Behaviour |
|---|---|
| 14.1 | Range units are case-insensitive tokens: `Bytes=0-1` is valid. |
| 14.1.1 | `int-range`, `suffix-range` and `other-range`; `500-100` is invalid. Other units keep their specs as raw text. |
| 14.1.2 | Inclusive offsets from zero; a last position past the end is clamped; a suffix longer than the body selects all of it; a suffix of 0 is unsatisfiable. On an empty representation a non-zero suffix is satisfiable but selects nothing: `resolve_ranges` returns `()` and the decision is 200. Large numerals parse exactly, absurd ones raise a typed error. |
| 5.6.1.2 | Whitespace around commas and a bounded number of empty list elements are accepted. |
| 14.2 | `Range` is ignored for methods other than `GET` and for units other than `bytes`; an invalid header is ignored; more than `max_overlapping` (default 2) ranges covering one same byte or more than `max_ranges` (default 100) ranges raise `ExcessiveRanges`. |
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

Byte-range handling is defined once in RFC 9110, yet every large HTTP stack ships its
own private copy: Starlette, aiohttp, werkzeug and Django each vendor their own parser
inside the framework, none of it importable on its own. There is no small, zero
dependency, fully typed package that parses a `Range` header strictly, resolves it under
a sane policy, and builds the matching 206, 416 or multipart reply. Reach for it in a
plain WSGI or ASGI handler, a static file server, a download client that resumes, or any
endpoint that needs correct partial content without pulling in a framework.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
