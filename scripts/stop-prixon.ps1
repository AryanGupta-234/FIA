$ErrorActionPreference = "Stop"
$StateRoot = Join-Path $env:LOCALAPPDATA "Prixon"
$PidFile = Join-Path $StateRoot "server.pid"
if (Test-Path $PidFile) {
    $RawPid = (Get-Content $PidFile -Raw).Trim()
    if ($RawPid -match "^\d+$") {
        $ProcessId = [int]$RawPid
        $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
        if ($Process) {
            $CommandLine = [string]$Process.CommandLine
            $IsPrixon = (
                $Process.Name -ieq "python.exe"
                -and $CommandLine -match "(?i)uvicorn"
                -and $CommandLine -match "(?i)fia\.api:app"
            )
            if ($IsPrixon) {
                Stop-Process -Id $ProcessId -Force
                Write-Host "Stopped Prixon server process $ProcessId." -ForegroundColor Green
            }
            else {
                Write-Warning "PID $ProcessId is no longer Prixon's Uvicorn process. It was not terminated."
            }
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
else {
    Write-Host "No Prixon server PID file was found. The server may already be stopped."
}
