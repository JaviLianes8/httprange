"""The ``httprange`` command line tool."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from . import __version__
from ._checks import short
from ._cli_io import cut, emit, flush_stdout, to_json
from ._content_range import build_content_range, parse_content_range
from ._decision import evaluate_range_request
from ._errors import RangeError
from ._grammar import parse_range_request
from ._numbers import to_int
from ._resolve import RangePolicy, resolve_ranges

EXAMPLES = """\
examples:
  httprange parse "bytes=0-499,-500"                 # one range-spec per line
  httprange parse --json "bytes=9500-"
  httprange resolve "bytes=-500" --length 10000      # bytes 9500-9999/10000
  httprange resolve "bytes=0-99,50-199" --length 1000 --no-coalesce
  httprange content-range 0 499 --length 1234        # bytes 0-499/1234
  httprange content-range --unsatisfied --length 1234   # bytes */1234
  httprange parse-content-range "bytes 42-1233/*"
  httprange decide --range "bytes=0-0,-1" --length 10000
  httprange decide --range "bytes=0-9" --length 100 --if-range '"v2"' --etag '"v1"'
  httprange resolve "bytes=5000-" --length 100       # error: unsatisfiable, exit 1
"""


class _Parser(argparse.ArgumentParser):
    """Argument parser whose usage errors exit with status 1 like every other error."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {cut(message)}\n")


def _length(text: str) -> int:
    try:
        return to_int(text, ValueError, text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a non-negative integer of at most 4000 digits, got {short(text)}"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``httprange`` command."""
    parser = _Parser(
        prog="httprange",
        description="Parse, resolve and build HTTP Range and Content-Range values (RFC 9110).",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"httprange {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    parse = sub.add_parser("parse", help="parse a Range header value (strict grammar)")
    parse.add_argument("header", help='a Range value such as "bytes=0-499,-500"')
    parse.add_argument("--json", action="store_true", help="print a JSON object")
    res = sub.add_parser("resolve", help="resolve a Range header against a length")
    res.add_argument("header", help='a Range value such as "bytes=-500"')
    res.add_argument("--length", type=_length, required=True, help="representation length")
    res.add_argument("--no-coalesce", action="store_true", help="keep overlapping ranges")
    res.add_argument("--max-ranges", type=_length, default=100, help="DoS cap (default 100)")
    res.add_argument("--json", action="store_true", help="print a JSON object")
    build = sub.add_parser("content-range", help="build a Content-Range value")
    build.add_argument("first", nargs="?", type=_length, help="first byte offset")
    build.add_argument("last", nargs="?", type=_length, help="last byte offset (inclusive)")
    build.add_argument("--length", type=_length, help="complete length (default: *)")
    build.add_argument("--unsatisfied", action="store_true", help="the 416 form */length")
    pcr = sub.add_parser("parse-content-range", help="parse a Content-Range value")
    pcr.add_argument("value", help='a value such as "bytes 0-499/1234"')
    pcr.add_argument("--json", action="store_true", help="print a JSON object")
    dec = sub.add_parser("decide", help="decide 200, 206 or 416 for a GET request")
    dec.add_argument("--range", dest="range_header", help="the Range header value")
    dec.add_argument("--length", type=_length, required=True, help="representation length")
    dec.add_argument("--method", default="GET", help="request method (default GET)")
    dec.add_argument("--if-range", help="the If-Range header value")
    dec.add_argument("--etag", help="the current ETag of the representation")
    dec.add_argument("--last-modified", help="the current Last-Modified HTTP-date")
    dec.add_argument("--json", action="store_true", help="print a JSON object")
    return parser


def _output(data: dict[str, object], lines: list[str], as_json: bool) -> str:
    return to_json(data) if as_json else "\n".join(lines)


def _run(args: argparse.Namespace) -> str:
    if args.command == "parse":
        request = parse_range_request(args.header)
        items = [str(spec) for spec in request.specs] or list(request.other)
        data: dict[str, object] = {"unit": request.unit, "ranges": items}
        return _output(data, [f"unit: {request.unit}", *items], args.json)
    if args.command == "resolve":
        policy = RangePolicy(max_ranges=args.max_ranges, coalesce=not args.no_coalesce)
        ranges = resolve_ranges(args.header, args.length, policy=policy)
        values = [item.content_range(args.length) for item in ranges]
        data = {"ranges": [[item.first, item.last] for item in ranges], "content_range": values}
        return _output(data, values, args.json)
    if args.command == "content-range":
        if args.unsatisfied:
            if args.first is not None:
                raise RangeError("--unsatisfied takes no offsets")
            return build_content_range(None, None, args.length)
        if args.first is None or args.last is None:
            raise RangeError("give FIRST and LAST, or --unsatisfied")
        return build_content_range(args.first, args.last, args.length)
    if args.command == "parse-content-range":
        span = parse_content_range(args.value)
        data = {
            "unit": span.unit,
            "first": span.first,
            "last": span.last,
            "complete_length": span.complete_length,
            "satisfied": span.is_satisfied,
        }
        lines = [f"{key}: {'*' if value is None else _text(value)}" for key, value in data.items()]
        return _output(data, lines, args.json)
    return _decide(args)


def _text(value: object) -> str:
    return to_json(value) if type(value) is int else str(value)


def _decide(args: argparse.Namespace) -> str:
    decision = evaluate_range_request(
        method=args.method,
        range_header=args.range_header,
        length=args.length,
        if_range=args.if_range,
        etag=args.etag,
        last_modified=args.last_modified,
    )
    data: dict[str, object] = {
        "status": decision.status,
        "ranges": [[item.first, item.last] for item in decision.ranges],
        "content_range": decision.content_range,
        "multipart": decision.is_multipart,
        "reason": decision.reason,
    }
    lines = [f"status: {decision.status}", f"reason: {decision.reason}"]
    if decision.content_range is not None:
        lines.append(f"content-range: {decision.content_range}")
    lines.extend(f"range: {item}" for item in decision.ranges if decision.is_multipart)
    return _output(data, lines, args.json)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line tool and return its exit status.

    0 on success; 1 for an error (printed on standard error) or when the reader of
    standard output has gone away. ``--help`` and ``--version`` raise ``SystemExit``
    with 0, or with 1 when that reader has gone away.
    """
    for stream in (sys.stdout, sys.stderr):
        # Echoed input may hold characters the console encoding cannot print.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        # --help, --version and usage errors end here; their text is still buffered.
        if not flush_stdout():
            raise SystemExit(1) from None
        raise
    except OSError:
        flush_stdout()
        raise SystemExit(1) from None
    try:
        text = _run(args)
    except RangeError as exc:
        print(f"httprange: error: {cut(str(exc))}", file=sys.stderr)
        return 1
    return 0 if emit(text) else 1


if __name__ == "__main__":
    raise SystemExit(main())
