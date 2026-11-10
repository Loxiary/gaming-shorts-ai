# Arrete les composants lances par start.ps1 (API, worker, frontend).
# Un job en cours est repris automatiquement au prochain demarrage du worker
# (apres GSA_WORKER_STALE_SECONDS) sans rejouer les etapes deja terminees.
# Usage : powershell -ExecutionPolicy Bypass -File scripts\stop.ps1

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path $PidFile)) {
    Write-Warn2 'Aucun fichier .run\pids.json : rien a arreter (application non lancee par start.ps1).'
    exit 0
}

$pids = Get-Content $PidFile -Raw | ConvertFrom-Json
Write-Step 'Arret des composants'
foreach ($entry in $pids.PSObject.Properties) {
    $procId = [int]$entry.Value
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        # /T : arrete aussi les processus enfants (le python du venv lance un interpreteur enfant).
        taskkill /PID $procId /T /F | Out-Null
        Write-Ok "$($entry.Name) arrete (PID $procId)"
    } else {
        Write-Warn2 "$($entry.Name) deja arrete (PID $procId)"
    }
}
Remove-Item $PidFile
Write-Host 'Application arretee.' -ForegroundColor Green
