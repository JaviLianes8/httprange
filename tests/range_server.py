"""A tiny range-aware file server built on the library, shared by the e2e tests."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httprange as hr

CONTENT = bytes((i * 7) % 256 for i in range(10000))
ETAG = '"v1"'
LAST_MODIFIED = "Fri, 02 Jan 2026 03:04:05 GMT"


def _handler(path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            data = path.read_bytes()
            decision = hr.evaluate_range_request(
                method=self.command,
                range_header=self.headers.get("Range"),
                length=len(data),
                if_range=self.headers.get("If-Range"),
                etag=ETAG,
                last_modified=LAST_MODIFIED,
            )
            self.send_response(decision.status)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", ETAG)
            if decision.status == 416:
                body = b""
            elif decision.is_multipart:
                multipart = hr.build_multipart_byteranges(
                    data, decision.ranges, content_type="application/octet-stream"
                )
                self.send_header("Content-Type", multipart.content_type)
                body = multipart.body
            else:
                self.send_header("Content-Type", "application/octet-stream")
                body = data[decision.ranges[0].as_slice()] if decision.ranges else data
            if decision.content_range is not None:
                self.send_header("Content-Range", decision.content_range)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler


@contextmanager
def serve(path: Path) -> Iterator[str]:
    """Serve ``path`` on a free loopback port and yield its URL; stop on exit."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/{path.name}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
