# Rebuilds all ThirdParty recipes on Windows.
# Run from d:\O3DE\Engine\Tools\ThirdParty
# Usage: .\.venv\Scripts\Activate.ps1 ; .\rebuild_all.ps1

param(
    [string]$BuildType = "Release",
    [switch]$ContinueOnError
)

$ErrorActionPreference = "Stop"
$thirdparty = ".\.venv\Scripts\thirdparty.exe"

# All Windows-compatible recipes, roughly in dependency order so the output
# reads naturally.  The build tool handles transitive dep ordering itself, so
# the exact sequence here only affects readability - not correctness.
$packages = @(
    # --- no-dep / header-only / compiler-level ---
    "eigen", "wil", "directx-headers", "spirv-headers", "vulkan-headers",
    "catch2", "gtest", "pybind11",
    "rapidjson", "rapidxml", "re2c", "xxhash",
    "md4c", "poly2tri", "mimalloc",
    "physx", "joltphysics", "v-hacd", "recastnavigation", "rvo2",
    "robin-hood-hashing",

    # --- low-level compression / crypto ---
    "zlib", "bzip2", "xz", "zstd", "brotli", "lz4", "libdeflate", "miniz",
    "openssl",

    # --- strings / parsing / scripting ---
    "abseil", "libexpat", "pcre2", "re2",
    "lua", "luau",
    "rapidyaml", "yaml-cpp",
    "jansson", "sqlite",
    "pystring",

    # --- image & audio I/O primitives ---
    "libiconv", "libjpeg-turbo", "libpng", "libwebp", "libwebm", "libsamplerate",
    "ogg", "opus", "vorbis",
    "hidapi",

    # --- zlib-compatible + minizip ---
    "zlib-ng", "minizip-ng",

    # --- graphics / math ---
    "imath", "little-cms", "msdfgen", "meshoptimizer",
    "icu", "freetype",
    "libxml2", "libtiff",

    # --- networking ---
    "libcurl",

    # --- SPIR-V / Vulkan ---
    "spirv-reflect", "spirv-tools", "spirv-cross",
    "vulkan-memory-allocator",
    "vulkan-validationlayers",

    # --- scene / asset libraries ---
    "openexr",
    "alembic",
    "tinyxml2",

    # --- new standalone packages ---
    "fmt", "pugixml", "robin-map",

    # --- high-level ---
    "opencolorio",
    "opensubdiv",
    "assimp",
    "openimageio",

    # --- misc remaining ---
    "manifold"
)

$failed = @()
$skipped = @()

foreach ($pkg in $packages) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Building: $pkg" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    try {
        & $thirdparty build $pkg --build-type $BuildType
        if ($LASTEXITCODE -ne 0) {
            throw "Exit code $LASTEXITCODE"
        }
        Write-Host "  [OK] $pkg" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] $pkg : $_" -ForegroundColor Red
        $failed += $pkg
        if (-not $ContinueOnError) {
            Write-Host ""
            Write-Host "Build failed. Re-run with -ContinueOnError to skip failures." -ForegroundColor Yellow
            exit 1
        }
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "Rebuild complete."
if ($failed.Count -gt 0) {
    Write-Host "FAILED packages ($($failed.Count)):" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
} else {
    Write-Host "All packages built successfully." -ForegroundColor Green
}
