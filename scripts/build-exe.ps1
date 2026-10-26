param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$ReleaseName = ("v" + (Get-Date -Format "yyyy.MM.dd-HHmmss")),
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
Set-Location $Root
$Python = if ($PythonPath) { $PythonPath } elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Missing required command: npm.cmd"
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Missing required Python interpreter: $Python"
}

$ReleaseDir = Join-Path $Root "release\$ReleaseName"
$WorkDir = Join-Path $Root "build\$ReleaseName"
if ((Test-Path -LiteralPath $ReleaseDir) -or (Test-Path -LiteralPath $WorkDir)) {
    throw "Release/build directory already exists. Use a new ReleaseName: $ReleaseName"
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

Invoke-NativeCommand "Install runtime and build dependencies" {
    & $Python -m pip install -r requirements-build.txt
}
Invoke-NativeCommand "Python dependency consistency" { & $Python -m pip check }
Invoke-NativeCommand "SciPy native solver preflight" {
    & $Python -c "from scipy.optimize import milp, Bounds; r = milp([1.], integrality=[1], bounds=Bounds([1.], [2.])); assert r.success and abs(r.x[0] - 1.) < 1e-8, r; print('SciPy MILP ready')"
}

$env:VITE_USE_MOCK = "false"
$env:VITE_ENABLE_DEMO_TOOLS = "false"
Invoke-NativeCommand "npm ci" { npm.cmd ci }

$VueTsc = Join-Path $Root "node_modules\.bin\vue-tsc.cmd"
if (-not (Test-Path $VueTsc)) {
    throw "Frontend dependency check failed: $VueTsc was not found"
}

Invoke-NativeCommand "npm run build" { npm.cmd run build }
Invoke-NativeCommand "PyInstaller build" { & $Python -m PyInstaller --noconfirm --distpath $ReleaseDir --workpath $WorkDir DefenseScheduler.spec }

$Exe = Join-Path $ReleaseDir "DefenseScheduler.exe"
if (-not (Test-Path $Exe)) {
    throw "Executable was not created: $Exe"
}

Write-Host "Built executable: $Exe"
