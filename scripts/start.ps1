# Demarre l'API (127.0.0.1:8000), le worker et le frontend (127.0.0.1:5173) en arriere-plan.
# Usage : powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Open]
#   -Open : ouvre l'interface dans le navigateur par defaut une fois prete.

param([switch]$Open)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path $VenvPython)) { Write-Err 'backend\.venv absent : lancer d''abord scripts\install.ps1'; exit 1 }
if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) { Write-Err 'frontend\node_modules absent : lancer d''abord scripts\install.ps1'; exit 1 }

if (Test-Path $PidFile) {
    $alive = (Get-Content $PidFile -Raw | ConvertFrom-Json).PSObject.Properties |
        Where-Object { Get-Process -Id $_.Value -ErrorAction SilentlyContinue }
    if ($alive) { Write-Err 'L''application semble deja lancee. Utiliser scripts\stop.ps1 d''abord.'; exit 1 }
    Remove-Item $PidFile
}

$apiPort = [int](Get-DotEnvValue 'GSA_API_PORT' '8000')
foreach ($port in $apiPort, 5173) {
    if (Test-PortInUse $port) { Write-Err "Le port $port est deja utilise par un autre programme."; exit 1 }
}

New-Item -ItemType Directory -Force $RunDir | Out-Null

Write-Step 'Migrations de la base'
Push-Location $BackendDir
try {
    & $VenvPython -m app.db.migrate
    if ($LASTEXITCODE -ne 0) { Write-Err 'Migration echouee (voir ci-dessus)'; exit 1 }
} finally { Pop-Location }

function Start-Component([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkDir) {
    $p = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $RunDir "$Name.out.log") `
        -RedirectStandardError (Join-Path $RunDir "$Name.err.log")
    Write-Ok "$Name demarre (PID $($p.Id))"
    return $p.Id
}

Write-Step 'Demarrage des composants'
$pids = [ordered]@{}
$pids.api      = Start-Component 'api' $VenvPython @('-m', 'app.server') $BackendDir
$pids.worker   = Start-Component 'worker' $VenvPython @('-m', 'app.workers.runner') $BackendDir
$viteJs = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
$pids.frontend = Start-Component 'frontend' 'node' @("`"$viteJs`"") $FrontendDir
$pids | ConvertTo-Json | Set-Content -Encoding ASCII $PidFile

Write-Step 'Attente de disponibilite'
$apiUrl = "http://127.0.0.1:$apiPort/api/health"
if (Wait-HttpOk $apiUrl 30) { Write-Ok "API prete : $apiUrl" } else { Write-Err "API non joignable. Voir .run\api.err.log"; exit 1 }
if (Wait-HttpOk 'http://127.0.0.1:5173/' 30) { Write-Ok 'Frontend pret : http://127.0.0.1:5173/' } else { Write-Err 'Frontend non joignable. Voir .run\frontend.err.log'; exit 1 }

Write-Host ''
Write-Host 'Gaming Shorts AI est lance : http://127.0.0.1:5173/' -ForegroundColor Green
Write-Host 'Arret : powershell -ExecutionPolicy Bypass -File scripts\stop.ps1'
if ($Open) { Start-Process 'http://127.0.0.1:5173/' }
