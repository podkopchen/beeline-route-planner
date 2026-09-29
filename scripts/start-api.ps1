$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $env:ROUTEFLOW_AUTH_ENABLED) {
    $env:ROUTEFLOW_AUTH_ENABLED = 'true'
}
if (-not $env:ROUTEFLOW_DEMO_USERNAME) {
    $env:ROUTEFLOW_DEMO_USERNAME = 'dispatcher'
}
if (-not $env:ROUTEFLOW_DEMO_PASSWORD) {
    $env:ROUTEFLOW_DEMO_PASSWORD = 'RouteFlow2026!'
}
if (-not $env:ROUTEFLOW_SESSION_SECRET) {
    $secretBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($secretBytes)
    $generator.Dispose()
    $env:ROUTEFLOW_SESSION_SECRET = [Convert]::ToBase64String($secretBytes)
}
if (-not $env:ROUTEFLOW_ROUTING_MODE) {
    $env:ROUTEFLOW_ROUTING_MODE = 'road_if_available'
}
if (-not $env:ROUTEFLOW_ROUTE_GEOMETRY_URL) {
    # Used only after the dispatcher opens a route with missing road geometry.
    # The canonical planner remains cache-first and never calls this endpoint.
    $env:ROUTEFLOW_ROUTE_GEOMETRY_URL = 'https://router.project-osrm.org'
}
Write-Host "RouteFlow routing mode: $env:ROUTEFLOW_ROUTING_MODE"
Write-Host "Selected-route geometry service: $env:ROUTEFLOW_ROUTE_GEOMETRY_URL"
Write-Host "RouteFlow account: $env:ROUTEFLOW_DEMO_USERNAME (password is configured locally)"
& "$projectRoot\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "$projectRoot\backend" --host 127.0.0.1 --port 8000
