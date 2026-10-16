$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "start-fia.ps1"
$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = Join-Path $Programs "FIA - Fashion Intelligence Agent.lnk"

if (-not (Test-Path $Launcher)) { throw "FIA launcher was not found: $Launcher" }
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + '"' + $Launcher + '"'
$Shortcut.WorkingDirectory = $Root
$Shortcut.Description = "Launch the FIA Fashion Intelligence workspace"
$Shortcut.Save()

Write-Host "Created Start Menu shortcut:" -ForegroundColor Green
Write-Host $ShortcutPath
Write-Host "Search Windows Start for: FIA - Fashion Intelligence Agent"
