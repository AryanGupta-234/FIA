$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$BackendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$DashboardScript = Join-Path $PSScriptRoot "start-dashboard.ps1"

Write-Host ""
Write-Host "  FIA  /  FASHION INTELLIGENCE AGENT" -ForegroundColor Magenta
Write-Host "  Starting your local research workspace..." -ForegroundColor Gray
Write-Host ""

Start-Process -FilePath "powershell.exe" -WorkingDirectory $Root -ArgumentList @(
    "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BackendScript
)
Start-Sleep -Seconds 2
Start-Process -FilePath "powershell.exe" -WorkingDirectory $Root -ArgumentList @(
    "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $DashboardScript
)

$Ready = $false
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -TimeoutSec 2 -UseBasicParsing
        if ($Response.StatusCode -eq 200) { $Ready = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($Ready) {
    Start-Process "http://127.0.0.1:5173"
    Write-Host "FIA dashboard opened in your browser." -ForegroundColor Green
} else {
    Write-Host "Dashboard is still starting. Open http://127.0.0.1:5173 when ready." -ForegroundColor Yellow
}
Write-Host "Backend API: http://127.0.0.1:8000/docs"
