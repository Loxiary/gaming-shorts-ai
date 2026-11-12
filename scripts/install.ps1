# Installation : environnement Python, dependances npm, .env, migrations SQLite.
# Usage : powershell -ExecutionPolicy Bypass -File scripts\install.ps1

. (Join-Path $PSScriptRoot 'common.ps1')

Write-Step 'Verification des prerequis'
foreach ($tool in 'python', 'node', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Err "$tool introuvable dans le PATH. Voir README.md (Prerequis)."
        exit 1
    }
}
$pyVersion = (python -c "import sys; print('%d.%d' % sys.version_info[:2])")
if ([version]$pyVersion -lt [version]'3.12') { Write-Err "Python >= 3.12 requis (trouve $pyVersion)"; exit 1 }
Write-Ok "Python $pyVersion, Node $(node --version), npm $(npm --version)"

Write-Step 'Fichier .env'
$envFile = Join-Path $RepoRoot '.env'
if (Test-Path $envFile) {
    Write-Ok '.env existant conserve'
} else {
    Copy-Item (Join-Path $RepoRoot '.env.example') $envFile
    Write-Ok '.env cree depuis .env.example (a verifier : GSA_DATA_DIR)'
}

Write-Step 'Environnement Python (backend\.venv)'
if (-not (Test-Path $VenvPython)) {
    python -m venv (Join-Path $BackendDir '.venv')
    if ($LASTEXITCODE -ne 0) { Write-Err 'Creation du venv impossible'; exit 1 }
}
# --no-cache-dir : evite ~2 Go de cache pip (bibliotheques CUDA) sur le disque systeme.
& $VenvPython -m pip install --disable-pip-version-check --no-cache-dir -q -r (Join-Path $BackendDir 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { Write-Err 'pip install a echoue'; exit 1 }
Write-Ok 'Dependances Python installees'

Write-Step 'Dependances frontend (npm ci)'
Push-Location $FrontendDir
try {
    npm ci --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { Write-Err 'npm ci a echoue'; exit 1 }
} finally { Pop-Location }
Write-Ok 'Dependances npm installees'

Write-Step 'Base SQLite (migrations Alembic)'
Push-Location $BackendDir
try {
    & $VenvPython -m app.db.migrate
    if ($LASTEXITCODE -ne 0) { Write-Err 'Migration echouee'; exit 1 }
} finally { Pop-Location }
Write-Ok 'Base a jour'

Write-Step 'Modele de transcription (faster-whisper)'
Push-Location $BackendDir
try {
    & $VenvPython -m app.cli.models status
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 'Modele absent : la transcription echouera tant qu''il ne sera pas telecharge.'
        Write-Warn2 'Telechargement (taille affichee, confirmation demandee) :'
        Write-Warn2 '  cd backend; .\.venv\Scripts\python.exe -m app.cli.models download'
    }
} finally { Pop-Location }

Write-Host ''
Write-Host 'Installation terminee. Lancement : powershell -ExecutionPolicy Bypass -File scripts\start.ps1' -ForegroundColor Green
