$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location (Join-Path $projectRoot "backend")
try {
    & $python -m ruff check app tests ../scripts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
