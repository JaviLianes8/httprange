# httprange

Parse and build HTTP Range and Content-Range headers (RFC 7233), zero dependencies, fully typed

## Install

```
pip install httprange
```

## Usage

```python
from httprange import parse_range, resolve, build_content_range

# Parse a Range header into its specs, in order.
parse_range("bytes=0-499,1000-")
# [RangeSpec(start=0, end=499), RangeSpec(start=1000, end=None)]

# A suffix range asks for the final bytes (start is None).
parse_range("bytes=-500")
# [RangeSpec(start=None, end=500)]

# Resolve one spec against a known body length (inclusive positions).
parse_range("bytes=-500")[0].resolve(1234)
# (734, 1233)

# Resolve a whole header at once; unsatisfiable specs are dropped.
resolve("bytes=0-99,5000-6000", 1234)
# [(0, 99)]

# Build the matching Content-Range response header.
build_content_range(0, 499, 1234)
# 'bytes 0-499/1234'

# The unsatisfiable form, for a 416 response.
build_content_range(None, None, 1234)
# 'bytes */1234'
```

Malformed headers raise `MalformedRange`, and a range that cannot be met raises
`UnsatisfiableRange`. Both subclass `RangeError`, which subclasses `ValueError`.

## Why

Byte-range handling is defined once in RFC 7233, yet every large HTTP stack ships its
own private copy: Starlette, aiohttp, werkzeug and Django each vendor their own parser
inside the framework, none of it importable on its own. There is no small, zero
dependency, fully typed package that just parses a `Range` header, resolves suffix and
open ended ranges against a known length, detects the unsatisfiable case, and builds the
`Content-Range` reply. Reach for it in a plain WSGI or ASGI handler, a static file
server, or any download endpoint that needs correct partial content without pulling in a
framework.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
