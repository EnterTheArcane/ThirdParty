param(
    [string]$BuildType = "Release",
    [switch]$ContinueOnError
)

$ErrorActionPreference = "Stop"
$thirdparty = ".\.venv\Scripts\thirdparty.exe"

$packages = Get-ChildItem -Path "recipes" -Directory | Select-Object -ExpandProperty Name | Sort-Object

$failed  = @()
$passed  = @()
$total   = $packages.Count

Write-Host "Found $total recipes to build." -ForegroundColor Cyan

foreach ($pkg in $packages) {
    Write-Host ""
    Write-Host "[$([array]::IndexOf($packages, $pkg) + 1)/$total] $pkg" -ForegroundColor Cyan

    try {
        & $thirdparty build $pkg --build-type $BuildType
        if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        $passed += $pkg
        Write-Host "  OK" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $_" -ForegroundColor Red
        $failed += $pkg
        if (-not $ContinueOnError) {
            Write-Host "Stopped. Re-run with -ContinueOnError to skip failures." -ForegroundColor Yellow
            exit 1
        }
    }
}

Write-Host ""
Write-Host "Results: $($passed.Count) passed, $($failed.Count) failed." -ForegroundColor Cyan
if ($failed.Count -gt 0) {
    Write-Host "Failed packages:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
