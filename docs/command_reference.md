# Command Reference

Run commands from the solution folder unless stated otherwise:

```powershell
cd D:\a\seabed_sidescan_solution
```

## 1. Setup Environment

Use after installing Miniconda, or after pulling the repo on a new machine.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_environment.ps1
```

Purpose:

```text
Creates/updates env_sidescantools_cli.
Installs the vendored SidescanTools package.
Applies the Klein 4-channel CLI patch.
Installs this solution as the seabed-sidescan Python package.
Verifies key Python/GIS imports.
```

After setup, use the package command directly from the activated environment:

```powershell
conda activate env_sidescantools_cli
seabed-sidescan --help
python -c "import sklearn; print(sklearn.__version__)"
```

## 2. List Input Data

Check what raw SSS data the solution will process.

Package command:

```powershell
seabed-sidescan list-input
```

With an explicit input path:

```powershell
seabed-sidescan list-input --input "D:\a\SSS RAW"
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\list_input_data.ps1
```

Use an explicit input path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\list_input_data.ps1 -InputPath "D:\a\SSS RAW"
```

Purpose:

```text
Finds .xtf and .jsf files.
Reports file count and total size.
Does not process data.
```

## 3. Run GIS Test

Run one small test before full processing.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_georef_test.ps1 -ProjectName "gis_test_100m"
```

Use explicit input if needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_georef_test.ps1 -ProjectName "gis_test_100m" -InputPath "D:\a\SSS_processing\test_small"
```

Output:

```text
D:\a\SSS_processing\projects\gis_test_100m\georef_out
D:\a\SSS_processing\projects\gis_test_100m\previews
D:\a\SSS_processing\projects\gis_test_100m\logs
```

## 4. Run Full SSS Processing

Package command:

```powershell
seabed-sidescan process --project "MSc_Project_100m" --input "D:\a\SSS RAW"
```

Dry run without starting SidescanTools:

```powershell
seabed-sidescan process --project "MSc_Project_100m" --input "D:\a\SSS RAW" --dry-run
```

Process the alternate 75 m channel pair:

```powershell
seabed-sidescan process --project "MSc_Project_75m" --input "D:\a\SSS RAW" --channel-pair "2,3"
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "MSc_Project_100m" -InputPath "D:\a\SSS RAW"
```

If the raw data is in an auto-discovered folder, this also works:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "MSc_Project_100m"
```

Process the alternate 75 m channel pair:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "MSc_Project_75m" -InputPath "D:\a\SSS RAW" -ChannelPair "2,3"
```

Output:

```text
D:\a\SSS_processing\projects\<project-name>\georef_out
D:\a\SSS_processing\projects\<project-name>\previews
D:\a\SSS_processing\projects\<project-name>\configs
D:\a\SSS_processing\projects\<project-name>\logs
```

## 5. Check GeoTIFF Outputs

Check processed GeoTIFF metadata and statistics.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_geotiff_outputs.ps1 -ProjectName "MSc_Project_100m"
```

Purpose:

```text
Runs gdalinfo checks on the processed GeoTIFFs.
Reports size, CRS, pixel size, corner coordinates, and statistics.
```

## 6. Clean Navigation CSVs

Preview large navigation CSVs:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cleanup_navigation_csvs.ps1
```

Delete them:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cleanup_navigation_csvs.ps1 -Delete
```

Purpose:

```text
Removes Navigation_*.csv files if they are consuming disk space.
Does not delete GeoTIFFs or mosaics.
```

## 7. Estimate Runtime

Estimate processing time from raw folder size.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\estimate_runtime.ps1
```

Use explicit paths:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\estimate_runtime.ps1 -RawFolder "D:\a\SSS RAW" -TestFile "D:\a\SSS_processing\test_small\PL018220414110300.xtf"
```

## 8. Build Channel And Combined Mosaics

Build the standard corrected channel mosaics and combined mosaic. This is the single package method to use for the final workflow.

Package command:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --clean-output
```

`--clean-output` removes previous raw, normalized, balanced, standard, and AOI mosaic products from the project `mosaics` folder before rebuilding. It does not delete the original XTF files or the processed GeoTIFF strips in `georef_out`.

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_channel_mosaics.ps1 -ProjectName "MSc_Project_100m" -CleanOutput
```

Output:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_qc_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_balance_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch0_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch1_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_combined_standard_mosaic.tif
```

Optional stricter QC:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_channel_mosaics.ps1 -ProjectName "MSc_Project_100m" -MinValidPercent 5 -MinStd 1 -MinPercentileRange 5
```

Equivalent package command:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --min-valid-percent 5 --min-std 1 --min-percentile-range 5
```

Channel-only mosaics:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --skip-combined
```

Standard mosaic method:

```text
Each strip is read separately and checked statistically.
Accepted strips are line-balanced using robust P10, P50, and P90 percentile matching.
The default edge trim is 2 percent to suppress weak strip-edge/nadir artefacts.
The default feather zone is 8 percent so strip edges contribute less in overlap areas.
Overlapping corrected pixels are combined using a feathered weighted mean.
The result is a corrected relative acoustic-intensity product for texture extraction and unsupervised classification.
It is not manufacturer-calibrated absolute dB backscatter.
```

## 8A. Standard Corrected Acoustic Branch

Use this branch for the final acoustic-facies workflow. It reduces line-to-line acquisition bias and trackline seam dominance while keeping the product in corrected relative acoustic-intensity units.

Build standard corrected channel and combined mosaics:

```powershell
seabed-sidescan mosaic --project "MSc_Project_75m_AOI" --channels 0 1 --clean-output
```

This cleanup is limited to known mosaic outputs and sidecar files. It prevents an older raw or normalized mosaic from being mistaken for the current standard corrected product.

Equivalent explicit command:

```powershell
seabed-sidescan mosaic --project "MSc_Project_75m_AOI" --channels 0 1 --clean-output --balance-low-percentile 10 --balance-mid-percentile 50 --balance-high-percentile 90 --feather-percent 8 --edge-trim-percent 2
```

Equivalent PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_channel_mosaics.ps1 -ProjectName "MSc_Project_75m_AOI" -Channels 0,1 -CleanOutput
```

Standard corrected mosaic outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_75m_AOI\mosaics\SSS_ch0_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_75m_AOI\mosaics\SSS_ch1_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_75m_AOI\mosaics\SSS_combined_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_75m_AOI\qc\strip_balance_report.csv
```

The `strip_balance_report.csv` file records each strip's `P10`, `P50`, `P90`, reference percentiles, scale, and offset. Keep this file because it proves the balancing operation used a repeatable radiometric rule rather than manual display stretching.

Clip the standard corrected mosaic to the AOI boundary for map production:

```powershell
seabed-sidescan clip-raster --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

Create a valid-data mask aligned to the standard corrected mosaic:

```powershell
seabed-sidescan mask --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

Extract textures from the standard corrected mosaic:

```powershell
seabed-sidescan textures --project "MSc_Project_75m_AOI"
```

Build the feature stack:

```powershell
seabed-sidescan stack-features --project "MSc_Project_75m_AOI"
```

Evaluate candidate class counts:

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_75m_AOI" --classes 3 4 5 6
```

Run final classification after choosing the class count:

```powershell
seabed-sidescan classify --project "MSc_Project_75m_AOI" --classes 5
```

Clean the final classification:

```powershell
seabed-sidescan clean-classification --project "MSc_Project_75m_AOI" --input-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5.tif" --output-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleaned.tif" --report-txt "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleanup_report.txt"
```

Standard mosaic method:

```text
For each accepted strip, the 10th, 50th, and 90th percentiles of valid acoustic pixels are calculated.
The median P10, P50, and P90 across all accepted strips forms the survey reference tone.
Each strip is linearly shifted and scaled so its P50 and P10-P90 range match the reference.
Overlapping pixels are then averaged, with optional edge feathering so strip edges contribute less strongly.
```

Report wording:

```text
To reduce line-to-line radiometric striping, accepted sidescan strips were radiometrically balanced before mosaicking. A robust P10-P50-P90 percentile match was used to align each strip to the median survey tone, and overlap zones were merged using a feathered mean to reduce hard seam effects. The resulting mosaic is a corrected relative acoustic-intensity product suitable for texture extraction and unsupervised acoustic facies classification. It should not be described as absolute calibrated backscatter because no manufacturer calibration to physical decibel backscatter was available.
```

## 9. Create Valid-Data Mask

Create the mask from the combined standard corrected mosaic.

Package command:

```powershell
seabed-sidescan mask --project "MSc_Project_100m"
```

Restrict the analysis to a polygon boundary:

```powershell
seabed-sidescan mask --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

This creates:

```text
masks\SSS_boundary_mask.tif
masks\SSS_valid_data_mask.tif
```

The second mask is the intersection of valid acoustic coverage and the boundary. All later package commands use it automatically. Complete channel mosaics remain available for QC.

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_valid_data_mask.ps1 -ProjectName "MSc_Project_100m"
```

Output:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\masks\SSS_valid_data_mask.tif
```

Mask values:

```text
1 = valid SSS data
0 = NoData / outside coverage
```

The complete channel 2/3 boundary workflow is documented in `docs\channel_23_boundary_workflow.md`.

## 9A. Clip A Raster For Map Production

Clip the default combined standard corrected mosaic and crop its extent to the project boundary:

```powershell
seabed-sidescan clip-raster --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

Default output:

```text
mosaics\SSS_combined_standard_mosaic_AOI.tif
```

Clip any other project raster by providing explicit input and output paths:

```powershell
seabed-sidescan clip-raster --input-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleaned.tif" --boundary "D:\a\SSS_processing\projects\Boundary.shp" --output-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleaned_AOI.tif"
```

The command masks pixels outside the polygon and crops the GeoTIFF to the polygon bounding extent. Use `--keep-extent` only when the original raster dimensions must be retained.

## 10. Extract Texture Features

Create texture rasters from the combined standard corrected SSS mosaic using the valid-data mask.

Package command:

```powershell
seabed-sidescan textures --project "MSc_Project_100m"
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\extract_texture_features.ps1 -ProjectName "MSc_Project_100m"
```

Default processing settings:

```text
Input raster: mosaics\SSS_combined_standard_mosaic.tif
Mask raster: masks\SSS_valid_data_mask.tif
Window size: 15 x 15 pixels
GLCM quantization: 16 grey levels
GLCM quantization range: 2nd-98th valid-pixel percentiles
GLCM directions: 0, 90, 45, and 135 degrees
```

Local mean and standard deviation use the input raster's units; variance uses squared input units. Percentile quantization is only used internally for entropy, contrast, homogeneity, ASM, and energy because those calculations use discrete grey levels.

Outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_mean.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_standard_deviation.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_variance.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_entropy.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_contrast.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_homogeneity.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_ASM.tif
D:\a\SSS_processing\projects\MSc_Project_100m\textures\SSS_energy.tif
```

Use a different window size if needed:

```powershell
seabed-sidescan textures --project "MSc_Project_100m" --window-size 21
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\extract_texture_features.ps1 -ProjectName "MSc_Project_100m" -WindowSize 21
```

Use fewer grey levels for a faster exploratory run:

```powershell
seabed-sidescan textures --project "MSc_Project_100m" --levels 8
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\extract_texture_features.ps1 -ProjectName "MSc_Project_100m" -Levels 8
```

## 11. Build Feature Stack

Package command:

```powershell
seabed-sidescan stack-features --project "MSc_Project_100m"
```

Outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\features\SSS_feature_stack.tif
D:\a\SSS_processing\projects\MSc_Project_100m\features\SSS_feature_stack_bands.csv
```

The default stack uses the standard corrected SSS mosaic plus mean, standard deviation, entropy, contrast, homogeneity, and energy.

## 12. Evaluate Candidate Class Counts

Evaluate `k=3,4,5,6` before final classification:

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_100m" --classes 3 4 5 6
```

Outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\classification\cluster_evaluation.csv
D:\a\SSS_processing\projects\MSc_Project_100m\classification\cluster_evaluation_summary.txt
```

The report includes inertia, silhouette score, Calinski-Harabasz score, Davies-Bouldin score, class balance, and adjusted Rand stability across repeated runs.

## 13. Run Unsupervised Classification

Run four acoustic facies classes:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 4
```

Compare alternative class counts:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 3
seabed-sidescan classify --project "MSc_Project_100m" --classes 5
seabed-sidescan classify --project "MSc_Project_100m" --classes 6
```

Outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\classification\SSS_acoustic_facies_k4.tif
D:\a\SSS_processing\projects\MSc_Project_100m\classification\SSS_acoustic_facies_k4_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\classification\SSS_acoustic_facies_k4_model.json
```

The command uses `scikit-learn` `KMeans` with `k-means++`, `n_init=50`, `max_iter=500`, and standardized features by default.

## 14. Clean Classification

Create a conservative cleaned version of the final class raster:

```powershell
seabed-sidescan clean-classification --project "MSc_Project_100m" --classes 4
```

Outputs:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\classification\SSS_acoustic_facies_k4_cleaned.tif
D:\a\SSS_processing\projects\MSc_Project_100m\classification\SSS_acoustic_facies_k4_cleanup_report.txt
```

Default cleanup:

```text
one 3 x 3 majority filter
replace connected patches smaller than 25 pixels when a strict surrounding majority exists
preserve class 0 / NoData
```

## 15. Package Development Commands

Install the package manually in the active environment:

```powershell
python -m pip install -e D:\a\seabed_sidescan_solution
```

Run the package as a Python module if the console script is unavailable:

```powershell
python -m seabed_sidescan.cli --help
```

Compile-check package files:

```powershell
python -m py_compile .\src\seabed_sidescan\__init__.py .\src\seabed_sidescan\paths.py .\src\seabed_sidescan\cli.py .\src\seabed_sidescan\mosaic.py .\src\seabed_sidescan\mask.py .\src\seabed_sidescan\texture.py .\src\seabed_sidescan\features.py .\src\seabed_sidescan\evaluate.py .\src\seabed_sidescan\classify.py .\src\seabed_sidescan\cleanup.py
```

## 16. Git Commands

Check what will be committed:

```powershell
git status
```

Commit:

```powershell
git add .
git commit -m "feat: introduce Seabed Sidescan 0.1.0"
```

Push:

```powershell
git remote add origin https://github.com/BezalelBenUri/seabed-sidescan.git
git branch -M main
git push -u origin main
```

Do not commit raw data or heavy outputs:

```text
*.xtf
*.tif
*.csv
*.png
```
