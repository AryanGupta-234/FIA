$ErrorActionPreference = "Stop"
$Frontend = Join-Path (Split-Path -Parent $PSScriptRoot) "frontend"
Set-Location $Frontend

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js 20+ and npm are required to launch the FIA dashboard."
}
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev -- --host 127.0.0.1
