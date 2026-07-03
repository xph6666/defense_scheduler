$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Missing required command: npm.cmd"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Missing required command: python"
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }
}

function Remove-BuildArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $rootPath = [System.IO.Path]::GetFullPath($Root.Path)
    $targetPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside project root: $targetPath"
    }
    if (Test-Path -LiteralPath $targetPath) {
        Remove-Item -LiteralPath $targetPath -Recurse -Force
    }
}

$env:VITE_USE_MOCK = "false"
$env:VITE_ENABLE_DEMO_TOOLS = "false"
Invoke-NativeCommand "npm ci" { npm.cmd ci }

$VueTsc = Join-Path $Root "node_modules\.bin\vue-tsc.cmd"
if (-not (Test-Path $VueTsc)) {
    throw "Frontend dependency check failed: $VueTsc was not found"
}

Invoke-NativeCommand "npm run build" { npm.cmd run build }
Remove-BuildArtifact (Join-Path $Root "build\DefenseScheduler")
Remove-BuildArtifact (Join-Path $Root "release\DefenseScheduler.exe")
Invoke-NativeCommand "PyInstaller build" { python -m PyInstaller --clean --noconfirm --distpath release --workpath build DefenseScheduler.spec }

$Exe = Join-Path $Root "release\DefenseScheduler.exe"
if (-not (Test-Path $Exe)) {
    throw "Executable was not created: $Exe"
}

Write-Host "Built executable: $Exe"
