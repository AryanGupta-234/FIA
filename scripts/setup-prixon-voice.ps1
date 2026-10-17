$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelName = "vosk-model-small-en-us-0.15"
$ModelRoot = Join-Path $env:LOCALAPPDATA "Prixon\models"
$ModelPath = Join-Path $ModelRoot $ModelName
$ArchivePath = Join-Path $env:TEMP "$ModelName.zip"
$ModelUrl = "https://alphacephei.com/vosk/models/$ModelName.zip"

New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null

if (-not (Test-Path (Join-Path $ModelPath "conf\model.conf"))) {
    if (Test-Path $ModelPath) {
        Remove-Item -Recurse -Force $ModelPath
    }

    Write-Host "Downloading the official Vosk small English model (~40 MB)..."
    Invoke-WebRequest -Uri $ModelUrl -OutFile $ArchivePath
    Expand-Archive -Path $ArchivePath -DestinationPath $ModelRoot -Force
    Remove-Item -Force $ArchivePath

    if (-not (Test-Path (Join-Path $ModelPath "conf\model.conf"))) {
        throw "The downloaded archive did not contain the expected Vosk model structure."
    }
}

Push-Location $RepoRoot
try {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        & $VenvPython -m pip install -e ".[windows,voice]"
    }
    else {
        py -3.11 -m pip install -e ".[windows,voice]"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Installing the optional local voice dependencies failed."
    }

    $EnvFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $EnvFile)) {
        Copy-Item (Join-Path $RepoRoot ".env.example") $EnvFile
    }

    $Values = [ordered]@{
        "PRIXON_VOICE_KILL_ENABLED" = "true"
        "PRIXON_VOICE_MODEL_PATH" = $ModelPath
        "PRIXON_VOICE_CAPTURE_SECONDS" = "5"
    }
    $Lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $EnvFile) {
        foreach ($Line in (Get-Content $EnvFile)) {
            $Lines.Add($Line)
        }
    }

    foreach ($Key in $Values.Keys) {
        $Pattern = "^$([regex]::Escape($Key))="
        $Found = $false
        for ($Index = 0; $Index -lt $Lines.Count; $Index++) {
            if ($Lines[$Index] -match $Pattern) {
                $Lines[$Index] = "$Key=$($Values[$Key])"
                $Found = $true
                break
            }
        }
        if (-not $Found) {
            $Lines.Add("$Key=$($Values[$Key])")
        }
    }

    [System.IO.File]::WriteAllLines(
        $EnvFile,
        $Lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Local voice kill is configured."
Write-Host "Restart Prixon, then press Ctrl+Alt+V and say: Prixon stop."
Write-Host "The microphone is only opened for the finite capture window after the hotkey."
