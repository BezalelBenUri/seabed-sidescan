# Industry Standard Mosaic Workflow

This workflow rebuilds the sidescan processing from scratch and makes the final working mosaic a corrected relative acoustic-intensity GeoTIFF. The product is intended for visual interpretation, texture extraction, and unsupervised acoustic facies classification.

The package default is not a raw strip mosaic. Raw strip mosaics preserve strong path and scan-line artifacts. The standard mosaic applies strip QC, robust line balancing, strip-edge trimming, and feathered overlap averaging to reduce line-to-line artifacts before classification.

## Main Product

Use this mosaic for GIS, textures, feature stacking, and classification:

```text
mosaics\SSS_combined_standard_mosaic.tif
```

The AOI-clipped version is:

```text
mosaics\SSS_combined_standard_mosaic_AOI.tif
```

## Reports

The main QC and processing reports are:

```text
qc\strip_qc_report.csv
qc\strip_balance_report.csv
qc\mosaic_method_report.txt
```

## Commands

Run from PowerShell:

```powershell
Set-Location "D:\a\seabed_sidescan_solution"

& "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
conda activate env_sidescantools_cli

pip install -e .

$ProjectName = "MSc_Project_Industry_Mosaic"
$ProjectRoot = "D:\a\SSS_processing\projects"
$ProjectDir = Join-Path $ProjectRoot $ProjectName
$RawInput = "D:\a\SSS RAW"
$Boundary = "D:\a\SSS_processing\projects\Boundary.shp"
$Resolution = 0.25
$SearchRadius = $Resolution * 2

if (Test-Path -LiteralPath $ProjectDir) {
    Remove-Item -LiteralPath $ProjectDir -Recurse -Force
}

seabed-sidescan list-input --input $RawInput

seabed-sidescan process `
    --project $ProjectName `
    --input $RawInput `
    --channel-pair "2,3" `
    --resolution $Resolution `
    --search-radius $SearchRadius

seabed-sidescan mosaic `
    --project $ProjectName `
    --channels 0 1 `
    --clean-output `
    --min-valid-percent 1 `
    --min-std 0.5 `
    --min-percentile-range 2 `
    --edge-trim-percent 2 `
    --feather-percent 8 `
    --balance-low-percentile 10 `
    --balance-mid-percentile 50 `
    --balance-high-percentile 90

seabed-sidescan mask `
    --project $ProjectName `
    --boundary $Boundary

seabed-sidescan clip-raster `
    --project $ProjectName `
    --boundary $Boundary

seabed-sidescan textures --project $ProjectName

seabed-sidescan stack-features --project $ProjectName

seabed-sidescan evaluate-clusters `
    --project $ProjectName `
    --classes 3 4 5 6

seabed-sidescan classify `
    --project $ProjectName `
    --classes 5

seabed-sidescan clean-classification `
    --project $ProjectName `
    --classes 5
```

Change the final `--classes 5` only after reviewing `classification\cluster_evaluation.csv` and the candidate maps.

`--resolution` controls the GeoTIFF strip pixel size produced during georeferencing. The mosaic inherits this resolution from the processed strips. `--search-radius` controls the GMT Nearneighbor interpolation radius; use about two times the output resolution unless testing shows holes or over-smoothing.
