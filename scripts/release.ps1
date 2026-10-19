# Build and upload to PyPI. Run scripts/check.ps1 first.
# Refuses a version that is already on PyPI; the token is read from a secret store, never git.
$ErrorActionPreference = "Stop"

$init = Get-Content "src/httprange/__init__.py" -Raw
if ($init -notmatch '__version__ = "([^"]+)"') { throw "No __version__ in src/httprange/__init__.py." }
$version = $Matches[1]

# Works on both Windows PowerShell 5.1 and pwsh 7 (generic catch, no PS7-only types).
$published = $true
try {
    Invoke-WebRequest -UseBasicParsing "https://pypi.org/pypi/httprange/$version/json" | Out-Null
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 404) { $published = $false } else { throw }
}
if ($published) { throw "httprange $version is already on PyPI. Bump the version before publishing." }

$token = $env:PYPI_TOKEN
if (-not $token -and (Test-Path "C:\secrets\pypi-token.txt")) {
    $token = (Get-Content "C:\secrets\pypi-token.txt" -Raw).Trim()
}
if (-not $token) {
    throw "No PyPI token. Set `$env:PYPI_TOKEN or save it to C:\secrets\pypi-token.txt (never commit it)."
}

Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
python -m build
python -m twine check dist/*

$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = $token
try { python -m twine upload dist/* } finally { Remove-Item Env:\TWINE_PASSWORD -ErrorAction SilentlyContinue }
