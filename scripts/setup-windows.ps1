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
    Copy-Item ".env.production.example" ".env"
    Write-Host "Created .env from .env.production.example. Edit it before production use."
}

python -m pip install -r requirements.txt
npm.cmd ci

$env:VITE_USE_MOCK = "false"
$env:VITE_ENABLE_DEMO_TOOLS = "false"
npm.cmd run build

python manage.py migrate

Write-Host ""
Write-Host "Setup complete."
Write-Host "Create an admin user if needed: python manage.py createsuperuser"
Write-Host "Start the app: .\scripts\start-windows.ps1"
