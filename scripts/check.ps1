# Local quality gate. Run before every commit. No CI runs in the cloud.
#   scripts/check.ps1         format, lint, types and the self-contained tests
#   scripts/check.ps1 -Full   also the opt-in tests: fetched RFCs, the 0.2.0 oracle, the
#                             wheel e2e and the PyPI upgrade; any skipped test fails it.
# -Full needs network access, Node.js, curl, werkzeug and aiohttp (see CONTRIBUTING.md).
param([switch]$Full)
$ErrorActionPreference = "Stop"

ruff format --check .
if ($LASTEXITCODE) { exit $LASTEXITCODE }
ruff check .
if ($LASTEXITCODE) { exit $LASTEXITCODE }
mypy --strict src
if ($LASTEXITCODE) { exit $LASTEXITCODE }
mypy --strict tests
if ($LASTEXITCODE) { exit $LASTEXITCODE }

if ($Full) {
    python scripts/fetch_upstream.py
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $oracle = Join-Path (Get-Location) "build/oracle-0.2.0"
    Remove-Item -Recurse -Force $oracle -ErrorAction SilentlyContinue
    python -m pip download httprange==0.2.0 --no-deps --only-binary :all: -d $oracle
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $wheel = Get-ChildItem $oracle -Filter "httprange-0.2.0-*.whl" | Select-Object -First 1
    python -m zipfile -e $wheel.FullName (Join-Path $oracle "package")
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $env:HTTPRANGE_V02 = Join-Path $oracle "package"
    $env:HTTPRANGE_E2E = "1"
    $env:HTTPRANGE_E2E_PYPI = "1"
    $env:HTTPRANGE_FULL = "1"
}
pytest
if ($LASTEXITCODE) { exit $LASTEXITCODE }
