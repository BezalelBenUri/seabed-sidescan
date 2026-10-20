param(
    [string]$ProjectName = "",
    [string]$ProjectRoot = "",
    [string]$InputRaster = "",
    [string]$MaskRaster = "",
    [string]$OutputDir = "",
    [string]$EnvName = "env_sidescantools_cli",
    [int]$WindowSize = 15,
    [int]$Levels = 16,
    [string]$Directions = "0,1;1,0;1,1;1,-1"
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
if (-not $MaskRaster) {
    $MaskRaster = Join-Path $projectDir "masks\SSS_valid_data_mask.tif"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $projectDir "textures"
}

if (-not (Test-Path -LiteralPath $InputRaster)) {
    throw "Input raster not found: $InputRaster"
}
if (-not (Test-Path -LiteralPath $MaskRaster)) {
    throw "Mask raster not found: $MaskRaster"
}

Ensure-Folder $OutputDir

$conda = Find-CondaExe
$pythonScript = Join-Path $SolutionRoot "tools\extract_texture_features.py"

Write-Host "Input raster: $InputRaster"
Write-Host "Mask raster: $MaskRaster"
Write-Host "Texture output folder: $OutputDir"
Write-Host "Window size: $WindowSize"
Write-Host "GLCM levels: $Levels"
Write-Host "Directions: $Directions"
Write-Host ""

& $conda run --no-capture-output -n $EnvName python $pythonScript --input-raster $InputRaster --mask-raster $MaskRaster --output-dir $OutputDir --window-size $WindowSize --levels $Levels --directions $Directions
if ($LASTEXITCODE -ne 0) {
    throw "Texture extraction failed with code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Texture extraction complete."
