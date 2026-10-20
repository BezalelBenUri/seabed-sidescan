param(
    [string]$SidescanToolsRepo = "",
    [string]$EnvName = "env_sidescantools_cli"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

if (-not $SidescanToolsRepo) {
    $SolutionRoot = Split-Path -Parent $PSScriptRoot
    $SidescanToolsRepo = Join-Path $SolutionRoot "vendor\sidescantools-main"
}
else {
    $SolutionRoot = Split-Path -Parent $PSScriptRoot
}

if (-not (Test-Path $SidescanToolsRepo)) {
    throw "SidescanTools repo not found: $SidescanToolsRepo"
}

$conda = Find-CondaExe
& "$PSScriptRoot\patch_sidescantools_klein_cli.ps1" -SidescanToolsRepo $SidescanToolsRepo
Push-Location $SidescanToolsRepo
try {

$envExists = (& $conda env list) -match "^\s*$EnvName\s+"
if ($LASTEXITCODE -ne 0) { throw "Conda environment discovery failed with exit code $LASTEXITCODE" }
if ($envExists) {
    & $conda env update -n $EnvName -f environment_cli.yml
    if ($LASTEXITCODE -ne 0) { throw "Conda environment update failed with exit code $LASTEXITCODE" }
}
else {
    & $conda env create -f environment_cli.yml
    if ($LASTEXITCODE -ne 0) { throw "Conda environment creation failed with exit code $LASTEXITCODE" }
}

& $conda install -n $EnvName pip -y
if ($LASTEXITCODE -ne 0) { throw "Conda pip installation failed with exit code $LASTEXITCODE" }
& $conda run -n $EnvName python -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "SidescanTools installation failed with exit code $LASTEXITCODE" }

Set-Location $SolutionRoot
& $conda run -n $EnvName python -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "Seabed Sidescan installation failed with exit code $LASTEXITCODE" }

& $conda run -n $EnvName python -c "import seabed_sidescan, sidescantools, sklearn, numpy, pyproj, pygmt, rasterio, scipy, shapefile, skimage, utm, pyxtf; from osgeo import gdal; print('imports ok'); print('sklearn', sklearn.__version__); print('gdal', gdal.VersionInfo()); print('pyshp', shapefile.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Environment import validation failed with exit code $LASTEXITCODE" }
& $conda run -n $EnvName seabed-sidescan --version
if ($LASTEXITCODE -ne 0) { throw "CLI validation failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Environment setup complete."
