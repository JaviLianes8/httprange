"""A tiny range-aware file server built on the library, shared by the e2e tests."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from docblocks import python_blocks

CONTENT = bytes((i * 7) % 256 for i in range(10000))
ETAG = '"v1"'
LAST_MODIFIED = "Fri, 02 Jan 2026 03:04:05 GMT"


def _handler(path: Path) -> type[BaseHTTPRequestHandler]:
    """The handler of GUIDE.md section 1, run as written, plus an ``ETag`` header."""
    namespace: dict[str, object] = {
        "load_representation": path.read_bytes,
        "current_etag": lambda: ETAG,
        "last_modified": lambda: LAST_MODIFIED,
    }
    exec(compile(python_blocks("GUIDE.md")[0], "GUIDE.md", "exec"), namespace)
    guide = cast("type[BaseHTTPRequestHandler]", namespace["Handler"])

    def end_headers(self: BaseHTTPRequestHandler) -> None:
        self.send_header("ETag", ETAG)
        guide.end_headers(self)

    def log_message(self: BaseHTTPRequestHandler, format: str, *args: object) -> None:
        pass

    members = {"end_headers": end_headers, "log_message": log_message}
    return type("Handler", (guide,), members)


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
