$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing prerequisite: '$Name' is not installed or not on PATH."
    }
}

function Run([scriptblock]$Command, [string]$Description) {
    Write-Host "==> $Description"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

Require-Command python
Require-Command npm
foreach ($Required in @("requirements.txt", "desktop/requirements-build.txt", "web/package.json", "desktop/package.json")) {
    if (-not (Test-Path $Required)) { throw "Missing required file: $Required" }
}

Run { python -m pip install -r requirements.txt -r desktop/requirements-build.txt } "Installing Python dependencies"

Push-Location web
try {
    Run { npm install } "Installing web dependencies"
    Run { npm run build } "Building web UI"
} finally {
    Pop-Location
}

$Spec = if (Test-Path "vay-api.spec") { "vay-api.spec" } elseif (Test-Path "desktop/vay-api.spec") { "desktop/vay-api.spec" } else { $null }
if (-not $Spec) { throw "Missing prerequisite: vay-api.spec was not found at the repo root or in desktop/." }
Run { python -m PyInstaller --clean $Spec } "Building vay-api"

Push-Location desktop
try {
    Run { npm install } "Installing desktop dependencies"
    Run { npm run download-mongo } "Downloading MongoDB"
    Run { npm run dist } "Building desktop installer"
} finally {
    Pop-Location
}

$Installer = Join-Path $Repo "desktop/release/Vay-Reports-Setup-3.0.0.exe"
Write-Host "Installer: $Installer"
