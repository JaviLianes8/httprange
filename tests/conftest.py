from __future__ import annotations

from collections.abc import Iterator

import pytest
from range_server import CONTENT, serve


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """URL of a real local HTTP server that answers range requests with the library."""
    path = tmp_path_factory.mktemp("served") / "file.bin"
    path.write_bytes(CONTENT)
    with serve(path) as url:
        yield url
