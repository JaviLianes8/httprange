"""Fetch the third-party files listed in tests/upstream/MANIFEST.json.

The files (specifications and a reference implementation) are not part of the
repository. Their tests skip until this script has fetched them; each download is checked
against the size and sha256 in the manifest.

    python scripts/fetch_upstream.py            # fetch and verify
    python scripts/fetch_upstream.py --update   # fetch and record the new size and sha256

Errata pages can change over time; ``--update`` records their current state (and the
date) in the manifest, which is then committed with the change.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "tests" / "upstream"
MANIFEST = FOLDER / "MANIFEST.json"


def main(argv: list[str]) -> int:
    update = "--update" in argv
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failed = 0
    for name, entry in manifest.items():
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "httprange-tests"})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        digest = hashlib.sha256(body).hexdigest()
        if len(body) != entry["size"] or digest != entry["sha256"]:
            if not update:
                print(f"{name}: got {len(body)} bytes, sha256 {digest}; manifest differs")
                failed += 1
                continue
            entry.update(size=len(body), sha256=digest, fetched=datetime.date.today().isoformat())
            print(f"{name}: updated")
        (FOLDER / name).write_bytes(body)
        print(f"{name}: ok")
    if update:
        text = json.dumps(manifest, indent=2) + "\n"
        MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
