$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root
$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

if (-not (Test-Path "dist\index.html")) {
    throw "Frontend build not found. Run .\scripts\setup-windows.ps1 first."
}

if (Test-Path "db.sqlite3") {
    & $Python manage.py backupdb
    if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
}
& $Python manage.py migrate
if ($LASTEXITCODE -ne 0) { throw "Database migration failed" }

if (-not $env:DJANGO_DEBUG) {
    $env:DJANGO_DEBUG = "false"
}
if (-not $env:DJANGO_ALLOWED_HOSTS) {
    $env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
}

$Url = "http://127.0.0.1:8000"
Start-Process $Url
& $Python -m defense_scheduler.server
if ($LASTEXITCODE -ne 0) { throw "Server exited with an error" }
