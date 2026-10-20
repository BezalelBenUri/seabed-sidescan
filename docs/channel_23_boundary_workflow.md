# Channel 2/3 Boundary-Limited Workflow

This workflow processes the higher-resolution Klein source-channel pair `2,3` and restricts texture extraction and classification to:

```text
D:\a\SSS_processing\projects\Boundary.shp
```

The boundary is applied after georeferencing and mosaicking. This preserves complete strip and mosaic products for QC, while all downstream analytical products use only valid sonar pixels inside the polygon.

The boundary shapefile and processed SSS outputs both use:

```text
EPSG:32632 - WGS 84 / UTM zone 32N
```

## 1. Open The Solution And Activate The Environment

```powershell
cd D:\a\seabed_sidescan_solution
conda activate env_sidescantools_cli
python -m pip install -e .
seabed-sidescan --version
```

Expected package version: `0.5.0` or newer.

## 2. Check The Raw Input

```powershell
seabed-sidescan list-input --input "D:\a\SSS RAW"
```

## 3. Check The Channel 2/3 Run Without Processing

```powershell
seabed-sidescan process --project "MSc_Project_75m_AOI" --input "D:\a\SSS RAW" --channel-pair "2,3" --dry-run
```

## 4. Process Source Channels 2 And 3

```powershell
seabed-sidescan process --project "MSc_Project_75m_AOI" --input "D:\a\SSS RAW" --channel-pair "2,3"
```

The selected source channels are loaded into SidescanTools processing slots `0` and `1`. Output GeoTIFF filenames therefore contain `_ch0_` and `_ch1_`, even though the selected source XTF channels are `2` and `3`.

## 5. Check The GeoTIFF Outputs

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_geotiff_outputs.ps1 -ProjectName "MSc_Project_75m_AOI"
```

Inspect representative strips in GIS before mosaicking.

## 6. Build Channel And Combined Mosaics

Use processed slot names `0 1`, not source channel numbers `2 3`:

```powershell
seabed-sidescan mosaic --project "MSc_Project_75m_AOI" --channels 0 1 --clean-output
```

Inspect these outputs before continuing:

```text
mosaics\SSS_ch0_standard_mosaic.tif
mosaics\SSS_ch1_standard_mosaic.tif
mosaics\SSS_combined_standard_mosaic.tif
qc\strip_qc_report.csv
qc\strip_balance_report.csv
```

## 7. Create The Boundary-Limited Analysis Mask

```powershell
seabed-sidescan mask --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

Outputs:

```text
masks\SSS_boundary_mask.tif
masks\SSS_valid_data_mask.tif
```

Mask meanings:

```text
SSS_boundary_mask.tif:
1 = inside boundary
0 = outside boundary

SSS_valid_data_mask.tif:
1 = inside boundary and valid SSS data
0 = outside boundary, NoData, or an internal coverage gap
```

Do not use `--all-touched` unless boundary-edge pixels must be included. The default centre-of-pixel rule is more conservative.

## 8. Extract Boundary-Limited Texture Features

```powershell
seabed-sidescan textures --project "MSc_Project_75m_AOI" --window-size 15 --levels 16
```

The command automatically uses `masks\SSS_valid_data_mask.tif`, so pixels outside the boundary remain NoData.

## 8A. Create A Physically Clipped Mosaic For Mapping

The analytical workflow keeps the complete mosaic grid and uses the mask. For map production, create a separate cropped copy:

```powershell
seabed-sidescan clip-raster --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

Default output:

```text
mosaics\SSS_combined_standard_mosaic_AOI.tif
```

Do not replace the original mosaic. The `_AOI` raster is the cartographic copy; the complete mosaic remains the analytical/QC source.

## 9. Build The Feature Stack

```powershell
seabed-sidescan stack-features --project "MSc_Project_75m_AOI"
```

## 10. Evaluate Candidate Class Counts

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_75m_AOI" --classes 3 4 5 6
```

Review:

```text
classification\cluster_evaluation.csv
classification\cluster_evaluation_summary.txt
```

## 11. Run The Selected Classification

Use the class count supported by the evaluation. For the current channel 2/3 evaluation, `k=5` is preferred:

```powershell
seabed-sidescan classify --project "MSc_Project_75m_AOI" --classes 5
```

## 12. Clean The Selected Classification

```powershell
seabed-sidescan clean-classification --project "MSc_Project_75m_AOI" --classes 5
```

After selecting and cleaning `k=5`, create a cropped final map raster with:

```powershell
seabed-sidescan clip-raster --input-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleaned.tif" --boundary "D:\a\SSS_processing\projects\Boundary.shp" --output-raster "D:\a\SSS_processing\projects\MSc_Project_75m_AOI\classification\SSS_acoustic_facies_k5_cleaned_AOI.tif"
```

The final class raster stores class `0` outside the boundary and outside valid SSS coverage. The GeoTIFF retains the full mosaic grid for alignment; crop it cartographically in GIS only if a smaller display extent is required.

## Methodology Statement

```text
The channel 2/3 sidescan data were georeferenced and mosaicked before application of the area-of-interest boundary. A binary polygon mask was rasterized on the mosaic grid and intersected with the valid acoustic-data mask. Texture extraction, feature stacking, cluster evaluation, unsupervised classification, and post-classification cleanup were subsequently restricted to pixels containing valid sidescan observations within the defined project boundary.
```
