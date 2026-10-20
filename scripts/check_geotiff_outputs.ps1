param(
    [string]$ProjectName = "",
    [string]$ProjectRoot = "D:\a\SSS_processing\projects",
    [string]$Folder = "",
    [string]$EnvName = "env_sidescantools_cli"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$conda = Find-CondaExe
if ($ProjectName) {
    $Folder = Join-Path (Join-Path $ProjectRoot (Get-SafeProjectName $ProjectName)) "georef_out"
}
elseif (-not $Folder) {
    $Folder = "D:\a\SSS_processing\georef_out"
}

$tifs = Get-ChildItem -Path $Folder -Filter *.tif -File -ErrorAction SilentlyContinue

if (-not $tifs) {
    throw "No GeoTIFF files found in $Folder"
}

Write-Host "Found $($tifs.Count) GeoTIFF files in $Folder"
Write-Host ""

foreach ($tif in $tifs) {
    Write-Host "---- $($tif.Name)"
    & $conda run -n $EnvName gdalinfo -stats $tif.FullName | Select-String -Pattern "Size is|AUTHORITY|EPSG|Pixel Size|Minimum=|Maximum=|STATISTICS_VALID_PERCENT|Upper Left|Lower Right|Center"
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect GeoTIFF $($tif.FullName): GDAL exit code $LASTEXITCODE" }
    Write-Host ""
}
