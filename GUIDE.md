# Guide

This guide walks through serving and consuming range requests with `httprange`. Section
numbers refer to [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110).

## 1. A complete server handler

The order matters: evaluate your other preconditions first (`If-Match`,
`If-None-Match`, ...). Range only applies when the answer would otherwise be 200 (14.2).

```python
from http.server import BaseHTTPRequestHandler
from httprange import build_multipart_byteranges, evaluate_range_request


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        data = load_representation()  # bytes
        decision = evaluate_range_request(
            method=self.command,
            range_header=self.headers.get("Range"),
            length=len(data),
            if_range=self.headers.get("If-Range"),
            etag=current_etag(),  # e.g. '"5f3a-1b"'
            last_modified=last_modified(),  # aware datetime or HTTP-date string
        )
        self.send_response(decision.status)
        self.send_header("Accept-Ranges", "bytes")
        if decision.status == 416:
            body = b""
        elif decision.is_multipart:
            multipart = build_multipart_byteranges(
                data, decision.ranges, content_type="application/pdf"
            )
            self.send_header("Content-Type", multipart.content_type)
            body = multipart.body
        else:
            self.send_header("Content-Type", "application/pdf")
            body = data[decision.ranges[0].as_slice()] if decision.ranges else data
        if decision.content_range is not None:
            self.send_header("Content-Range", decision.content_range)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
```

The test suite runs this handler (plus an `ETag` header) on a loopback socket and
fetches it with `urllib` and `curl`.

### What `evaluate_range_request` decides

The rows apply in this order, and the first one that fits decides:

| Situation | Status | RFC 9110 |
|---|---|---|
| No `Range` header | 200 | 14.2 |
| Method other than `GET` (case-sensitive) | 200 | 14.2, MUST ignore |
| `If-Range` does not match | 200 | 13.1.5, MUST ignore Range |
| Empty representation | 200 | 14.2, MAY ignore |
| No token unit and `=`, or an invalid list | 200 | 14.2, MAY ignore |
| Unit other than `bytes` | 200 | 14.2, MUST ignore |
| More than `max_ranges` specs, counted before their syntax is read | 416 (or 200 with `on_excessive="ignore"`) | 14.2, 15.5.17 |
| Invalid range-spec | 200 | 14.2, MAY ignore |
| Nothing satisfiable | 416 with `Content-Range: bytes */length` | 14.4, 15.5.17 |
| More than `max_overlapping` ranges on one byte | 416 (or 200 with `on_excessive="ignore"`) | 14.2, 15.5.17 |
| Otherwise | 206 | 15.3.7 |

A single requested range is never answered as multipart (15.3.7.2). When several ranges
were requested but only one survives resolution or coalescing, the decision is a
single-part 206, which the RFC permits.

## 2. The denial-of-service policy

```python
from httprange import RangePolicy, resolve_ranges

policy = RangePolicy(
    max_ranges=100,  # range-specs accepted per header
    max_overlapping=2,  # 14.2: at most two ranges may cover one same byte
    coalesce=True,  # merge overlapping and adjacent ranges
    coalesce_gap=80,  # 15.3.7.2: per-part overhead is "around 80 bytes"
)
resolve_ranges("bytes=0-9,50-99", 1000, policy=policy)
# (ByteRange(first=0, last=99),)
```

Coalesced ranges keep the order of their earliest spec, so parts follow request order
(15.3.7.2). Pass `coalesce=False` to keep every satisfiable range as requested.

## 3. Strict parsing

`parse_range_request` follows 14.1.1 to the letter, with the list rules of 5.6.1.2:

- `bytes=0-499`, `bytes=9500-`, `bytes=-500`, `bytes=0-0,-1`,
  `bytes= 0-999, 4500-5499, -1000` (the RFC's own example) are valid;
- `bytes =0-1`, `bytes=0 - 1`, `bytes=500-100`, non-ASCII digits and numerals of more
  than 4000 significant digits (leading zeros are not counted) raise `MalformedRange`;
- `items=1.2-4.3` parses to `RangeRequest(unit='items', specs=(), other=('1.2-4.3',))`.

`parse_range`, from 0.1, stays lenient about spaces around `=` and only accepts `bytes`.

## 4. Clients: reading a 206

```python
from httprange import parse_content_range, parse_multipart_byteranges

span = parse_content_range(response.headers["Content-Range"])
span.first, span.last, span.complete_length

parts = parse_multipart_byteranges(body, response.headers["Content-Type"])
for part in parts:
    store(part.content_range.first, part.data)
```

The multipart parser accepts a preamble and extra CRLFs before the first boundary (14.6
note 1), a quoted boundary, and transport padding after a boundary. It checks that every
`bytes` part holds exactly as many bytes as its `Content-Range` says, and refuses a body
without its closing boundary.

## 5. If-Range

```python
from httprange import if_range_matches

if_range_matches('"v1"', etag='"v1"')  # True
if_range_matches('W/"v1"', etag='W/"v1"')  # False (8.8.3.2)
if_range_matches(
    "Fri, 02 Jan 2026 03:04:05 GMT", last_modified="Fri, 02 Jan 2026 03:04:05 GMT"
)  # True, exact match
```

A date only counts when it is a strong validator (8.8.2.2). The default
`date_is_strong=True` trusts your dates; if the representation can change twice within
one second, pass `date_is_strong=False` and only ETags will match.

Your own validators are checked strictly: `last_modified` must be an aware `datetime`
or an HTTP-date, and anything else raises `RangeError` (`MalformedDate` for a string
such as `"2026-01-02T03:04:05Z"`), so a typo never passes as a mismatch. An `etag` that
is not a strong entity-tag (a weak one such as `W/"v1"`, or a value without quotes)
never matches, so the client gets the whole representation.

## 6. Command line

```
httprange decide --range "bytes=0-9" --length 100 --if-range '"v2"' --etag '"v1"'
status: 200
reason: If-Range does not match
```

Every subcommand accepts `--json` where output is structured. Errors print
`httprange: error: ...` on stderr (`httprange <command>: error: ...` after the usage
line for a bad argument of a subcommand) and exit with status 1.
