$ErrorActionPreference = "Stop"
$PidFile = Join-Path (Join-Path $env:LOCALAPPDATA "Prixon") "server.pid"
if (Test-Path $PidFile) {
    $RawPid = (Get-Content $PidFile -Raw).Trim()
    if ($RawPid -match "^\d+$") {
        $Process = Get-Process -Id ([int]$RawPid) -ErrorAction SilentlyContinue
        if ($Process) { Stop-Process -Id $Process.Id -Force }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Prixon stop requested." -ForegroundColor Green
