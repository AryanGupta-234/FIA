param([switch]$NoBrowser,[switch]$Foreground)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$EnvPath = Join-Path $Root ".env"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python) -or -not (Test-Path $EnvPath)) { & (Join-Path $PSScriptRoot "setup-prixon.ps1") }
if (-not (Test-Path $Python)) { throw "Prixon virtual environment is missing." }
$Port = 8000
if ($env:API_PORT -match "^\d+$") { $Port = [int]$env:API_PORT }
elseif (Test-Path $EnvPath) {
    $PortLine = Select-String -Path $EnvPath -Pattern "^\s*API_PORT\s*=\s*(\d+)" | Select-Object -First 1
    if ($PortLine -and $PortLine.Matches[0].Groups[1].Value) { $Port = [int]$PortLine.Matches[0].Groups[1].Value }
}
if ($Port -lt 1 -or $Port -gt 65535) { throw "API_PORT must be between 1 and 65535." }
$env:API_HOST = "127.0.0.1"
$env:API_PORT = [string]$Port
$BaseUrl = "http://127.0.0.1:$Port"
$HealthUrl = "$BaseUrl/api/v1/agent/health"
$UiUrl = "$BaseUrl/api/v1/agent/ui"
$StateRoot = Join-Path $env:LOCALAPPDATA "Prixon"
$LogRoot = Join-Path $StateRoot "logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$PidFile = Join-Path $StateRoot "server.pid"
$StdoutLog = Join-Path $LogRoot "server.stdout.log"
$StderrLog = Join-Path $LogRoot "server.stderr.log"
$Ready = $false
try { $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3; $Ready = $true } catch { }
if (-not $Ready) {
    if ($Foreground) { & $Python -m uvicorn fia.api:app --host 127.0.0.1 --port $Port; exit $LASTEXITCODE }
    $Process = Start-Process -FilePath $Python -ArgumentList @("-m","uvicorn","fia.api:app","--host","127.0.0.1","--port",[string]$Port) -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog
    Set-Content -Path $PidFile -Value $Process.Id -Encoding ascii
    for ($Attempt = 0; $Attempt -lt 90; $Attempt++) {
        Start-Sleep -Seconds 1
        $Process.Refresh()
        if ($Process.HasExited) {
            $Tail = if (Test-Path $StderrLog) { (Get-Content $StderrLog -Tail 50) -join [Environment]::NewLine } else { "No server log was written." }
            throw ("Prixon server exited during startup." + [Environment]::NewLine + $Tail)
        }
        try { $Health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3; $Ready = $true; break } catch { }
    }
}
if (-not $Ready) { throw "Prixon did not become ready on $BaseUrl. Inspect $StderrLog." }
if (-not $Health.loop_running) {
    try { Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/agent/runtime/start" -ContentType "application/json" -Body "{}" -TimeoutSec 10 | Out-Null }
    catch { Write-Warning "Agent loop could not be started: $($_.Exception.Message)" }
}
Write-Host "Prixon is ready: $UiUrl" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $UiUrl }
