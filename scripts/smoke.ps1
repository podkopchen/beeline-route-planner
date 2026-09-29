$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$npm = Get-Command npm.cmd -ErrorAction Stop | Select-Object -ExpandProperty Source

Push-Location $projectRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\test-backend.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $npm --prefix frontend run lint
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $npm --prefix frontend run typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $npm --prefix frontend test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
