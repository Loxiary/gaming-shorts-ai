# Diagnostic de l'environnement : Python, Node, npm, FFmpeg, GPU, disque.
# Usage : powershell -ExecutionPolicy Bypass -File scripts\check-env.ps1

. (Join-Path $PSScriptRoot 'common.ps1')
$ErrorActionPreference = 'Continue'

function Show-Tool([string]$Name, [scriptblock]$Version) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { Write-Warn2 "$Name : absent du PATH"; return }
    try { $v = (& $Version | Select-Object -First 1) } catch { $v = '?' }
    Write-Ok "$Name : $v  ($($cmd.Source))"
}

Write-Step 'Systeme'
$os = Get-CimInstance Win32_OperatingSystem
Write-Ok ("{0} {1}, RAM {2:N1} Go (libre {3:N1} Go)" -f $os.Caption, $os.Version, ($os.TotalVisibleMemorySize / 1MB), ($os.FreePhysicalMemory / 1MB))
Write-Ok ((Get-CimInstance Win32_Processor | Select-Object -First 1).Name.Trim())

Write-Step 'Outils'
Show-Tool 'python'  { python --version }
Show-Tool 'node'    { node --version }
Show-Tool 'npm'     { npm --version }
Show-Tool 'git'     { git --version }
Show-Tool 'ffmpeg'  { ffmpeg -hide_banner -version }
Show-Tool 'ffprobe' { ffprobe -hide_banner -version }

Write-Step 'GPU (nvidia-smi)'
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version --format=csv
} else {
    Write-Warn2 'nvidia-smi absent : pas de GPU NVIDIA detecte (mode CPU).'
}

Write-Step 'Dossier de donnees'
$dataDir = Get-DotEnvValue 'GSA_DATA_DIR' (Join-Path $RepoRoot 'data')
Write-Ok "GSA_DATA_DIR = $dataDir"
$qualifier = Split-Path -Qualifier $dataDir
$drive = Get-PSDrive -Name $qualifier.TrimEnd(':') -ErrorAction SilentlyContinue
if ($drive) {
    Write-Ok ("Disque {0} : {1:N0} Go libres" -f $qualifier, ($drive.Free / 1GB))
} else {
    Write-Warn2 "Disque $qualifier introuvable"
}

Write-Step 'Installation du projet'
if (Test-Path $VenvPython) { Write-Ok 'Environnement Python backend\.venv present' } else { Write-Warn2 'backend\.venv absent : lancer scripts\install.ps1' }
if (Test-Path (Join-Path $FrontendDir 'node_modules')) { Write-Ok 'frontend\node_modules present' } else { Write-Warn2 'frontend\node_modules absent : lancer scripts\install.ps1' }
if (Test-Path (Join-Path $RepoRoot '.env')) { Write-Ok '.env present' } else { Write-Warn2 '.env absent : il sera cree depuis .env.example par install.ps1' }
