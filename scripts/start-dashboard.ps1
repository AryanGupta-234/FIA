$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path -Parent $PSScriptRoot) "frontend")
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
