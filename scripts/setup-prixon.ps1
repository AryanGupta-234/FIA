$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.11 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { python -m venv .venv }
    else { throw "Python 3.11+ is required." }
}
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Prixon virtual environment creation failed." }
$Version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$Version -lt [version]"3.11") { throw "Prixon requires Python 3.11+. Found $Version." }
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $Python -m pip install -e ".[windows,media,browser]"
if ($LASTEXITCODE -ne 0) { throw "Prixon dependency installation failed." }
$EnvPath = Join-Path $Root ".env"
if (-not (Test-Path $EnvPath)) { Copy-Item (Join-Path $Root ".env.example") $EnvPath }
$LogRoot = Join-Path $env:LOCALAPPDATA "Prixon\logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
Write-Host "Prixon local environment is ready. Voice remains opt-in." -ForegroundColor Green
