$ErrorActionPreference = "Stop"
$Task = Get-ScheduledTask -TaskName "Prixon Agent" -ErrorAction SilentlyContinue
if ($Task) { Unregister-ScheduledTask -TaskName "Prixon Agent" -Confirm:$false }
& (Join-Path $PSScriptRoot "stop-prixon.ps1")
Write-Host "Prixon sign-in startup task removed." -ForegroundColor Green
