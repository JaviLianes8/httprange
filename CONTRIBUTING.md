# Contributing

Thanks for taking the time. This project keeps a small, predictable shape.

## Setup

```
pip install -r requirements-dev.txt
```

## Before you open a pull request

- Keep public API in `src/httprange/__init__.py`; internals live in `_`-prefixed modules.
- Add a test for the behaviour you change. Unit tests inject time, disk and network.
  The end to end tests are the exception: they serve a temporary file on a loopback
  socket and install the built wheel into a throwaway virtual environment.
- Run `scripts/check.ps1` (format, lint, types, tests) and make sure it passes.
- Before a release, run `scripts/check.ps1 -Full` as well (see below).
- One logical change per commit, imperative subject line.

## Opt-in tests

A plain `pytest` runs every self-contained test and skips the ones that need something
outside the repository. Each of them names its need in the skip reason (`pytest -rs`):

| Tests | Need |
| --- | --- |
| RFC text checks (`test_spec_*.py`) and the `range-parser` oracle | `python scripts/fetch_upstream.py` fetches the files into `tests/upstream/` |
| `range-parser` oracle (`test_oracle_range_parser.py`) | Node.js on the `PATH` |
| 0.2.0 comparisons (`test_upgrade*.py`) | `HTTPRANGE_V02` pointing at the unpacked 0.2.0 wheel |
| Wheel and sdist build, install and e2e (`test_e2e_wheel.py`) | `HTTPRANGE_E2E=1` |
| Upgrade in place from the PyPI release | `HTTPRANGE_E2E_PYPI=1` and network access |
| werkzeug and aiohttp oracles (`test_oracles_python.py`) | `pip install werkzeug==3.1.9 aiohttp==3.14.5` |
| curl e2e (`test_e2e_curl.py`) | `curl` on the `PATH` |

`scripts/check.ps1 -Full` fetches the files, downloads the 0.2.0 wheel into
`build/oracle-0.2.0`, sets the variables and sets `HTTPRANGE_FULL=1`, which turns every
skipped test into a failure, so a missing tool cannot pass unnoticed.

Open an issue first if the change is large or shifts the public API.
