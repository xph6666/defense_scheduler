param(
    [string]$ExePath = "",
    [int]$TimeoutSeconds = 360,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
$ReleaseDir = Join-Path $Root "release"
if (-not $ExePath) {
    $ExePath = Join-Path $ReleaseDir "DefenseScheduler.exe"
}
$ResolvedExe = Resolve-Path $ExePath

if (-not (Test-Path -LiteralPath $ResolvedExe)) {
    throw "Executable not found: $ResolvedExe"
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Remove-SmokeArtifact {
    param([Parameter(Mandatory = $true)][string]$Path)

    $releasePath = [System.IO.Path]::GetFullPath($ReleaseDir)
    $targetPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetPath.StartsWith($releasePath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove smoke artifact outside release directory: $targetPath"
    }
    if (Test-Path -LiteralPath $targetPath) {
        Remove-Item -LiteralPath $targetPath -Force
    }
}

function Restore-EnvVar {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][string]$Value
    )

    if ($null -eq $Value) {
        Remove-Item -LiteralPath "Env:\$Name" -ErrorAction SilentlyContinue
    } else {
        Set-Item -LiteralPath "Env:\$Name" -Value $Value
    }
}

function Unwrap-ApiEnvelope {
    param([Parameter(Mandatory = $true)]$Response)

    $propertyNames = @($Response.PSObject.Properties.Name)
    if ($propertyNames -contains "success" -and $propertyNames -contains "data") {
        if ($Response.success -eq $false) {
            throw "API returned error envelope: $($Response | ConvertTo-Json -Compress)"
        }
        return $Response.data
    }

    return $Response
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$dbPath = Join-Path $ReleaseDir "smoke-exe-$stamp.sqlite3"
$stdoutPath = Join-Path $ReleaseDir "smoke-exe-$stamp.out.log"
$stderrPath = Join-Path $ReleaseDir "smoke-exe-$stamp.err.log"
$port = Get-Random -Minimum 30001 -Maximum 34000
$baseUrl = "http://127.0.0.1:$port"
$process = $null
$success = $false

$oldEnv = @{
    DJANGO_DB_PATH = $env:DJANGO_DB_PATH
    DJANGO_SECRET_KEY = $env:DJANGO_SECRET_KEY
    DJANGO_DEBUG = $env:DJANGO_DEBUG
    DJANGO_ALLOWED_HOSTS = $env:DJANGO_ALLOWED_HOSTS
    DEFENSE_SCHEDULER_OPEN_BROWSER = $env:DEFENSE_SCHEDULER_OPEN_BROWSER
    DEFENSE_SCHEDULER_PORT = $env:DEFENSE_SCHEDULER_PORT
}

try {
    Set-Location $Root

    $env:DJANGO_DB_PATH = $dbPath
    $env:DJANGO_SECRET_KEY = "smoke-secret-key-0123456789abcdefghijklmnopqrstuvwxyz"
    $env:DJANGO_DEBUG = "false"
    $env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"

    Invoke-NativeCommand "Django migrate" { python manage.py migrate --noinput }
    Invoke-NativeCommand "Create smoke users" {
        python manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser(username='admin', password='smoke-pass-123'); User.objects.create_user(username='viewer', password='viewer-pass-123')"
    }

    $env:DEFENSE_SCHEDULER_OPEN_BROWSER = "false"
    $env:DEFENSE_SCHEDULER_PORT = [string]$port
    $process = Start-Process `
        -FilePath $ResolvedExe `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $ready = $false
    $lastError = ""
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            $outText = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
            $errText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
            throw "Executable exited early with code $($process.ExitCode). Stdout:`n$outText`nStderr:`n$errText"
        }

        try {
            $homeResponse = Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
            if ($homeResponse.StatusCode -eq 200) {
                $ready = $true
                break
            }
            $lastError = "Unexpected home response: $($homeResponse.StatusCode)"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }

    if (-not $ready) {
        $outText = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
        $errText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
        throw "Executable did not become HTTP-ready at $baseUrl. Last error: $lastError`nStdout:`n$outText`nStderr:`n$errText"
    }

    $favicon = Invoke-WebRequest -Uri "$baseUrl/favicon.svg" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $faviconContent = [string]$favicon.Content
    if ($favicon.StatusCode -ne 200 -or -not $faviconContent.TrimStart().StartsWith("<svg")) {
        $first = $faviconContent.Substring(0, [Math]::Min(80, $faviconContent.Length))
        throw "Unexpected favicon response: status=$($favicon.StatusCode), first=$first"
    }

    $adminBody = @{ username = "admin"; password = "smoke-pass-123" } | ConvertTo-Json
    $admin = Unwrap-ApiEnvelope (Invoke-RestMethod -Uri "$baseUrl/api/auth/login/" -Method Post -ContentType "application/json" -Body $adminBody -TimeoutSec 10 -ErrorAction Stop)
    if (-not $admin.token -or $admin.isAdmin -ne $true) {
        throw "Admin login contract failed: $($admin | ConvertTo-Json -Compress)"
    }

    $viewerBody = @{ username = "viewer"; password = "viewer-pass-123" } | ConvertTo-Json
    $viewer = Unwrap-ApiEnvelope (Invoke-RestMethod -Uri "$baseUrl/api/auth/login/" -Method Post -ContentType "application/json" -Body $viewerBody -TimeoutSec 10 -ErrorAction Stop)
    if (-not $viewer.token -or $viewer.isAdmin -ne $false) {
        throw "Viewer login contract failed: $($viewer | ConvertTo-Json -Compress)"
    }

    $viewerHeaders = @{ Authorization = "Token $($viewer.token)" }
    $readTeachers = Invoke-WebRequest -Uri "$baseUrl/api/teachers/" -Headers $viewerHeaders -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    if ($readTeachers.StatusCode -ne 200) {
        throw "Viewer teacher read failed: $($readTeachers.StatusCode)"
    }

    $teacherBody = @{ name = "Smoke Teacher"; college = "Computer Science"; title = "Professor" } | ConvertTo-Json
    $postStatus = $null
    try {
        $postResult = Invoke-WebRequest -Uri "$baseUrl/api/teachers/" -Method Post -Headers $viewerHeaders -ContentType "application/json" -Body $teacherBody -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $postStatus = [int]$postResult.StatusCode
    } catch {
        if ($_.Exception.Response) {
            $postStatus = [int]$_.Exception.Response.StatusCode
        } else {
            throw
        }
    }
    if ($postStatus -ne 403) {
        throw "Expected viewer write to be 403, got $postStatus"
    }

    $success = $true
    Write-Host "SMOKE_OK $baseUrl"
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }

    $exeFullPath = [System.IO.Path]::GetFullPath($ResolvedExe)
    Get-Process -Name DefenseScheduler -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $exeFullPath) } |
        Stop-Process -Force -ErrorAction SilentlyContinue

    foreach ($entry in $oldEnv.GetEnumerator()) {
        Restore-EnvVar -Name $entry.Key -Value $entry.Value
    }

    if ($success -and -not $KeepArtifacts) {
        Remove-SmokeArtifact $dbPath
        Remove-SmokeArtifact $stdoutPath
        Remove-SmokeArtifact $stderrPath
    } else {
        Write-Host "Smoke artifacts:"
        Write-Host "  $dbPath"
        Write-Host "  $stdoutPath"
        Write-Host "  $stderrPath"
    }
}
