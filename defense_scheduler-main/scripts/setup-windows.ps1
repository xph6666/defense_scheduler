$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Require-Command python
Require-Command npm.cmd

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created local .env. Use .env.production.example when configuring a shared server."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed" }
}
$Python = ".venv\Scripts\python.exe"
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed" }
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }

$env:VITE_USE_MOCK = "false"
$env:VITE_ENABLE_DEMO_TOOLS = "false"
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }

if (Test-Path "db.sqlite3") {
    & $Python manage.py backupdb
    if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
}
& $Python manage.py migrate
if ($LASTEXITCODE -ne 0) { throw "Database migration failed" }

Write-Host ""
Write-Host "Setup complete."
Write-Host "Create an admin user if needed: .venv\Scripts\python manage.py createsuperuser"
Write-Host "Start the app: .\scripts\start-windows.ps1"
