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
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.
