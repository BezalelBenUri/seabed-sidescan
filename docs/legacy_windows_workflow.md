# Seabed Sidescan Processing Solution

This folder packages the processing workflow for the unsupervised seabed acoustic facies classification project.

It does not include raw XTF files, generated GeoTIFFs, large navigation CSVs, or image outputs. It includes a vendored copy of SidescanTools with the processing code needed to reproduce the workflow.

## What This Solution Contains

- SidescanTools configuration files
- PowerShell command scripts for setup, testing, full processing, cleanup, and output checks
- An installable Python package exposed as the `seabed-sidescan` command
- Documentation notes for the technical report
- Full command reference in `docs\command_reference.md`
- A vendored SidescanTools copy in `vendor\sidescantools-main`
- A patch script for using SidescanTools CLI with the four-channel Klein XTF files
- Git ignore rules to prevent pushing large survey data

## Expected Local Folder Layout

The scripts assume this local layout:

```text
D:\a
  SSS RAW\
    *.xtf
  SSS_processing\
    projects\
      project_name\
        georef_out\
        previews\
        configs\
        logs\
    test_small\
  seabed_sidescan_solution\

D:\a\seabed_sidescan_solution\
  vendor\sidescantools-main\
    src\sidescantools\
```

The vendored SidescanTools source is third-party GPLv3 software. Its `LICENSE` file is kept inside `vendor\sidescantools-main`.

## Step 1 - Set Up The Environment

Run this after Miniconda is installed:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\setup_environment.ps1
```

This creates or updates the conda environment, installs the vendored SidescanTools copy in editable mode, applies the local CLI/Klein compatibility patch, installs this solution package in editable mode, and verifies imports.

After setup, activate the environment when using the package command directly:

```powershell
conda activate env_sidescantools_cli
```

Check the package command:

```powershell
seabed-sidescan --help
```

## Step 2 - Run One GIS Georeferencing Test

Before full processing, run one disposable test:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\run_georef_test.ps1 -ProjectName "gis_test_100m"
```

Open the test GeoTIFFs in QGIS from:

```text
D:\a\SSS_processing\projects\gis_test_100m\georef_out
```

Check that they load around longitude 7.32 E and latitude 4.25 N, using CRS `EPSG:32632`.

## How Input Data Is Found

The scripts can work in two ways.

Recommended explicit method:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "main_100m_channels_0_1" -InputPath "D:\a\SSS RAW"
```

Automatic discovery method:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_processing.ps1 -ProjectName "main_100m_channels_0_1"
```

If `-InputPath` is not supplied, the script checks these locations:

```text
environment variable SSS_INPUT_PATH
.\data\raw
.\data\sss_raw
..\SSS RAW
..\SSS_raw
..\SSS
```

You can check what the solution will process before starting:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\list_input_data.ps1
```

Equivalent package command:

```powershell
seabed-sidescan list-input
```

For the test dataset:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\list_input_data.ps1 -Purpose test
```

## Step 3 - Run Full Processing

After the GIS test looks correct:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\run_full_processing.ps1 -ProjectName "main_100m_channels_0_1"
```

Equivalent package command:

```powershell
seabed-sidescan process --project "main_100m_channels_0_1" --input "D:\a\SSS RAW"
```

By default this processes channels `0,1`, the 100 m port/starboard pair.

To process the 75 m pair later:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\run_full_processing.ps1 -ProjectName "comparison_75m_channels_2_3" -ChannelPair "2,3"
```

Each run creates a named processing folder:

```text
D:\a\SSS_processing\projects\<project-name>\
  georef_out\
  previews\
  configs\
  logs\
```

## Step 4 - Check Outputs

After processing:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\check_geotiff_outputs.ps1 -ProjectName "main_100m_channels_0_1"
```

Then inspect the rasters in QGIS.

## Step 5 - Post-Processing Methodology

After full SSS processing, continue with:

```text
QC of processed strips
channel-wise mosaic creation
texture feature extraction
feature stack preparation
unsupervised classification
acoustic facies interpretation
```

The detailed methodology is documented in:

```text
docs\post_processing_methodology.md
```

## Step 6 - Automated Standard Mosaics

To QC strips statistically and build the standard corrected acoustic-intensity mosaics:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_channel_mosaics.ps1 -ProjectName "MSc_Project_100m" -CleanOutput
```

Equivalent package command:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --clean-output
```

`--clean-output` removes previous raw, normalized, balanced, standard, and AOI mosaic products from the project `mosaics` folder before rebuilding. It does not delete the original XTF files or the processed GeoTIFF strips in `georef_out`.

This creates:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_qc_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_balance_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch0_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch1_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_combined_standard_mosaic.tif
```

The QC does not reject a strip just because it is dark. It rejects strips that are mostly NoData or have almost no internal backscatter variation.

Standard mosaic method:

```text
1. Accepted strips are selected from the QC report.
2. Each strip is radiometrically balanced using robust P10-P50-P90 percentile matching.
3. A 2% strip-edge trim is applied by default to reduce outer-edge artefacts.
4. Overlap zones are merged using an 8% feathered weighted mean.
5. The output is written as the standard corrected mosaic for texture extraction and classification.
```

This is the one recommended package method for the project. It reduces visible trackline seams and scan/strip-edge effects while keeping the mosaic closer to processed acoustic intensity than a full per-strip 0-255 display stretch. It is still a corrected relative acoustic-intensity product, not absolute calibrated dB backscatter.

## Step 7 - Create Valid-Data Mask

Create a mask from the combined standard mosaic:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_valid_data_mask.ps1 -ProjectName "MSc_Project_100m"
```

Equivalent package command:

```powershell
seabed-sidescan mask --project "MSc_Project_100m"
```

Restrict every downstream analytical phase to a polygon boundary:

```powershell
seabed-sidescan mask --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

This additionally creates `masks\SSS_boundary_mask.tif`. The normal `SSS_valid_data_mask.tif` becomes the intersection of valid sonar coverage and the boundary. Georeferenced strips and mosaics remain complete for QC.

This creates:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\masks\SSS_valid_data_mask.tif
```

Mask values:

```text
1 = valid sidescan pixel
0 = NoData / outside coverage / transparent gap
```

Use this mask during texture extraction and classification so gaps are not treated as seabed.

The complete channel 2/3 boundary workflow is documented in `docs\channel_23_boundary_workflow.md`.

Create a cropped cartographic copy of the combined standard corrected mosaic:

```powershell
seabed-sidescan clip-raster --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

This writes `mosaics\SSS_combined_standard_mosaic_AOI.tif` and leaves the complete analytical mosaic unchanged.

## Step 8 - Extract Texture Features

Create texture rasters from the combined standard mosaic:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\extract_texture_features.ps1 -ProjectName "MSc_Project_100m"
```

Equivalent package command:

```powershell
seabed-sidescan textures --project "MSc_Project_100m"
```

This creates:

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

Default settings:

```text
15 x 15 pixel moving window
16 grey-level quantization for GLCM texture
four directions: 0, 90, 45, and 135 degrees
valid-data mask applied
```

## Step 9 - Build Feature Stack

Create the multi-band raster used for unsupervised classification:

```powershell
seabed-sidescan stack-features --project "MSc_Project_100m"
```

This creates:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\features\SSS_feature_stack.tif
D:\a\SSS_processing\projects\MSc_Project_100m\features\SSS_feature_stack_bands.csv
```

The default stack contains the standard corrected SSS acoustic intensity mosaic, mean, standard deviation, entropy, contrast, homogeneity, and energy.

## Step 10 - Evaluate Candidate Class Counts

Evaluate `k=3,4,5,6` before deciding the final number of acoustic facies:

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_100m" --classes 3 4 5 6
```

This creates:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\classification\cluster_evaluation.csv
D:\a\SSS_processing\projects\MSc_Project_100m\classification\cluster_evaluation_summary.txt
```

The report includes inertia, silhouette score, Calinski-Harabasz score, Davies-Bouldin score, class balance, and run-to-run stability.

## Step 11 - Run Unsupervised Classification

Start with four acoustic facies classes:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 4
```

Then compare other class counts:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 3
seabed-sidescan classify --project "MSc_Project_100m" --classes 5
seabed-sidescan classify --project "MSc_Project_100m" --classes 6
```

The classifier uses `scikit-learn` `KMeans` with `k-means++` initialization, `n_init=50`, and standardized feature values. Output classes are acoustic facies classes, not confirmed sediment types.

## Step 12 - Clean Classification For Final Map

Create a conservative cleaned version of the chosen classification:

```powershell
seabed-sidescan clean-classification --project "MSc_Project_100m" --classes 4
```

This applies one 3 x 3 majority-filter pass, replaces connected patches smaller than 25 pixels only when a strict surrounding majority exists, and preserves class 0 / NoData. Ties and components without valid neighbours retain their original class. Keep the raw classification as the analytical result and use the cleaned version for final map presentation.

## Space Management

The full processing config has navigation CSV export turned off:

```yaml
active_export_navigation: false
```

This avoids producing tens of gigabytes of navigation CSVs.

If old test navigation CSVs exist, preview them with:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\cleanup_navigation_csvs.ps1
```

Delete them only when ready:

```powershell
powershell -ExecutionPolicy Bypass -File D:\a\seabed_sidescan_solution\scripts\cleanup_navigation_csvs.ps1 -Delete
```

## Technical Position For The Report

Because sediment samples are not available, the defensible output is:

```text
unsupervised acoustic seabed facies classification
```

The final classes should be interpreted as acoustic/texture facies, not confirmed sediment classes.

## Python Package Usage

The package-first workflow is documented in:

```text
docs\python_package_usage.md
```

The Windows scripts are still kept because they are convenient on this machine, but the reusable project logic is now available through the `seabed-sidescan` Python command.
