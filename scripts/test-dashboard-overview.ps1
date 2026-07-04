$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$outDir = Join-Path $repoRoot ".tmp\dashboard-overview-test"
$compiledModule = Join-Path $outDir "utils\dashboardOverview.js"

try {
    if (Test-Path $outDir) {
        Remove-Item -LiteralPath $outDir -Recurse -Force
    }

    npx.cmd tsc src\utils\dashboardOverview.ts `
        --rootDir src `
        --outDir $outDir `
        --module ES2022 `
        --moduleResolution Bundler `
        --target ES2022 `
        --skipLibCheck

    node scripts\test-dashboard-overview.mjs $compiledModule
}
finally {
    if (Test-Path $outDir) {
        Remove-Item -LiteralPath $outDir -Recurse -Force
    }
}
