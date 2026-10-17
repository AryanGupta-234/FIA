$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "open-prixon.ps1"
$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = Join-Path $Programs "Prixon - Local Windows Agent.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + '"' + $Launcher + '"'
$Shortcut.WorkingDirectory = $Root
$Shortcut.Description = "Open the local Prixon Windows agent"
$Shortcut.Save()
Write-Host "Prixon Start Menu shortcut created." -ForegroundColor Green
