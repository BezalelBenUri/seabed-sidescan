param(
    [string]$ProjectName = "",
    [string]$ProjectRoot = "",
    [string]$InputRaster = "",
    [string]$OutputMask = "",
    [string]$Boundary = "",
    [string]$BoundaryCRS = "",
    [string]$OutputBoundaryMask = "",
    [switch]$AllTouched,
    [string]$EnvName = "env_sidescantools_cli"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$SolutionRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Join-Path (Split-Path -Parent $SolutionRoot) "SSS_processing\projects"
}

if (-not $ProjectName -and -not $InputRaster) {
    $latestProject = Get-ChildItem -Path $ProjectRoot -Directory -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latestProject) {
        throw "No project folders found in $ProjectRoot. Provide -ProjectName or -InputRaster."
    }
    $ProjectName = $latestProject.Name
}

if ($ProjectName) {
    $projectDir = Join-Path $ProjectRoot (Get-SafeProjectName $ProjectName)
}
elseif ($InputRaster) {
    $projectDir = Split-Path -Parent (Split-Path -Parent (Resolve-Path -LiteralPath $InputRaster).Path)
}

if (-not $InputRaster) {
    $InputRaster = Join-Path $projectDir "mosaics\SSS_combined_standard_mosaic.tif"
}
if (-not $OutputMask) {
    $OutputMask = Join-Path $projectDir "masks\SSS_valid_data_mask.tif"
}
if ($Boundary -and -not $OutputBoundaryMask) {
    $OutputBoundaryMask = Join-Path $projectDir "masks\SSS_boundary_mask.tif"
}

if (-not (Test-Path -LiteralPath $InputRaster)) {
    throw "Input raster not found: $InputRaster"
}
if ($Boundary -and -not (Test-Path -LiteralPath $Boundary)) {
    throw "Boundary shapefile not found: $Boundary"
}

Ensure-Folder (Split-Path -Parent $OutputMask)

$conda = Find-CondaExe
$pythonScript = Join-Path $SolutionRoot "tools\create_valid_mask.py"

Write-Host "Input raster: $InputRaster"
Write-Host "Output mask: $OutputMask"
if ($Boundary) {
    Write-Host "Boundary: $Boundary"
    Write-Host "Boundary-only mask: $OutputBoundaryMask"
}
Write-Host ""

$arguments = @(
    "run", "--no-capture-output", "-n", $EnvName,
    "python", $pythonScript,
    "--input-raster", $InputRaster,
    "--output-mask", $OutputMask
)
if ($Boundary) {
    $arguments += @("--boundary", $Boundary, "--output-boundary-mask", $OutputBoundaryMask)
}
if ($BoundaryCRS) {
    $arguments += @("--boundary-crs", $BoundaryCRS)
}
if ($AllTouched) {
    $arguments += "--all-touched"
}

& $conda @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Mask creation failed with code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Valid-data mask created."
