"""Read the ``python`` code blocks of the project's Markdown documents."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def python_blocks(name: str) -> list[str]:
    """The source of every fenced ``python`` block of ``name``, in document order."""
    text = (ROOT / name).read_text(encoding="utf-8")
    return re.findall(r"^```python\n(.*?)^```$", text, re.DOTALL | re.MULTILINE)
