$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root

if (-not (Test-Path "dist\index.html")) {
    throw "Frontend build not found. Run .\scripts\setup-windows.ps1 first."
}

python manage.py migrate

if (-not $env:DJANGO_DEBUG) {
    $env:DJANGO_DEBUG = "false"
}
if (-not $env:DJANGO_ALLOWED_HOSTS) {
    $env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
}

$Url = "http://127.0.0.1:8000"
Start-Process $Url
python manage.py runserver 127.0.0.1:8000
