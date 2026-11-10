# Shared helpers for Gaming Shorts AI PowerShell scripts (Windows PowerShell 5.1+).
# ASCII only on purpose: PowerShell 5.1 misreads UTF-8 files without BOM.

$ErrorActionPreference = 'Stop'

$Script:RepoRoot   = Split-Path -Parent $PSScriptRoot
$Script:BackendDir = Join-Path $RepoRoot 'backend'
$Script:FrontendDir = Join-Path $RepoRoot 'frontend'
$Script:VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$Script:RunDir     = Join-Path $RepoRoot '.run'
$Script:PidFile    = Join-Path $RunDir 'pids.json'

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "    [OK] $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "    [!] $Message" -ForegroundColor Yellow }
function Write-Err([string]$Message)  { Write-Host "    [ERREUR] $Message" -ForegroundColor Red }

function Get-DotEnvValue([string]$Name, [string]$Default) {
    $envFile = Join-Path $RepoRoot '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match "^\s*$Name\s*=\s*(.*)\s*$") { return $Matches[1].Trim('"', "'", ' ') }
        }
    }
    return $Default
}

function Test-PortInUse([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}
