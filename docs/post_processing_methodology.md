# Post-Processing Methodology After Full SSS Processing

Project output inspected: `MSc_Project_100m`

Processing folder:

```text
D:\a\SSS_processing\projects\MSc_Project_100m
```

Current output summary:

```text
GeoTIFF folder: D:\a\SSS_processing\projects\MSc_Project_100m\georef_out
Preview folder: D:\a\SSS_processing\projects\MSc_Project_100m\previews
Runtime config: D:\a\SSS_processing\projects\MSc_Project_100m\configs\full.runtime.yml
Log folder: D:\a\SSS_processing\projects\MSc_Project_100m\logs
```

The full processing produced:

```text
44 channel 0 GeoTIFFs
44 channel 1 GeoTIFFs
44 processed PNG previews
```

This means the raw XTF processing stage is complete for the selected `0,1` channel pair.

## Stage Already Completed

The completed SSS processing stage converted raw XTF files into georeferenced sidescan rasters.

Main operations completed:

```text
XTF reading
Klein 4-channel handling
channel pair selection: 0,1
bottom detection/refinement
slant range correction
beam angle correction
energy normalization
dB conversion
histogram equalization
georeferencing
GMT blockmedian gridding support
GMT nearneighbor raster generation
GeoTIFF export
PNG preview export
```

The output GeoTIFFs are the main GIS-ready products for the next stage.

The reproducible workflow is packaged in `D:\a\seabed_sidescan_solution` as the Python command `seabed-sidescan`. The older PowerShell scripts remain available as Windows wrappers, but the package command is the preferred reusable interface for processing, mosaicking, mask creation, and texture extraction.

## Next Stage 1: Quality Control In QGIS

Before mosaicking or classification, inspect the processed GeoTIFFs.

Open QGIS and load:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\georef_out\*.tif
```

Check:

```text
1. Do the rasters appear in the correct study area?
2. Are any lines blank or mostly NoData?
3. Are any strips badly rotated or displaced?
4. Are channel 0 and channel 1 positioned on opposite sides of the track?
5. Are there obvious brightness differences between lines?
6. Are there artifacts near the nadir or outer range?
7. Do the PNG previews look like valid sidescan imagery?
```

This stage is important because classification should not be run on bad lines. If a bad line is found, it should be excluded or reprocessed before mosaic creation.

For this project, use three QC decisions:

```text
Keep: strip has visible sonar texture and falls in the expected survey block.
Review: strip is positioned correctly but has strong nadir, gain, overlap, turn, or brightness artifacts.
Reject: strip is blank, corrupted, mostly NoData, or clearly displaced away from the survey block.
```

The first QGIS visual inspection showed that the processed strips are generally visible and geographically coherent. The major visible concerns are not blank lines, but common sidescan processing issues: bright/dark nadir bands, variable brightness between overlapping lines, curved turn sections, and strip seams. These should be addressed during mosaic preparation and interpretation rather than treated automatically as failed georeferencing.

## Next Stage 2: Create Sidescan Mosaics

After QC, create mosaics from the accepted GeoTIFFs.

Recommended first mosaics:

```text
SSS_ch0_mosaic.tif
SSS_ch1_mosaic.tif
```

Channel 0 and channel 1 should be mosaicked separately first because they represent opposite sides of the sidescan swath.

Then decide whether to:

```text
1. classify channel 0 and channel 1 separately,
2. merge both channels into a combined sidescan mosaic, or
3. use the cleaner/better-looking channel mosaic as the main acoustic layer.
```

In QGIS, a simple open-source route is:

```text
Raster -> Miscellaneous -> Build Virtual Raster
Raster -> Miscellaneous -> Merge
```

Use files matching:

```text
*_ch0_EPSG32632.tif
*_ch1_EPSG32632.tif
```

Methodology wording:

```text
The georeferenced sidescan strips were visually inspected and then mosaicked by channel to create continuous acoustic backscatter surfaces for feature extraction and unsupervised classification.
```

### Automated Mosaic Step Used In This Project

The channel mosaics can be generated using the packaged automation:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_channel_mosaics.ps1 -ProjectName "MSc_Project_100m" -CleanOutput
```

This script performs three tasks:

```text
1. Calculates strip statistics for every channel GeoTIFF.
2. Applies robust line-to-line acoustic intensity balancing to accepted strips.
3. Builds standard corrected channel and combined mosaics.
```

The script writes:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_qc_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\qc\strip_balance_report.csv
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch0_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_ch1_standard_mosaic.tif
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_combined_standard_mosaic.tif
```

In the first automated QC run, all strips were retained:

```text
ch0: 44 keep, 0 review, 0 reject
ch1: 44 keep, 0 review, 0 reject
```

This indicates that the visually dark strips were not blank in a statistical sense. They contain valid backscatter values and should be treated as dark/low-backscatter or display-stretch issues unless later visual inspection proves otherwise.

Methodology wording:

```text
A statistical QC was performed before mosaicking. Each strip was assessed using valid-pixel percentage, standard deviation, and percentile range. Strips with sufficient valid pixels and backscatter variation were retained for channel-wise mosaicking.
```

The final package workflow creates one main analytical product type:

```text
standard corrected mosaic: applies strip QC, robust P10-P50-P90 line balancing, light edge handling, and feathered overlap averaging.
```

The standard corrected mosaic is the preferred final product because it reduces line-to-line acquisition bias and trackline seam dominance without converting every strip to a separate 0-255 display stretch.

Important qualification:

```text
"Standard corrected" means corrected at the mosaic stage.
The input GeoTIFF strips may already include SidescanTools processing such as slant-range correction, beam correction, and gridding depending on the runtime configuration.
Because no manufacturer calibration to physical decibel backscatter was available, the output should be described as corrected relative acoustic intensity, not absolute calibrated backscatter.
```

Methodology wording:

```text
To reduce line-to-line striping and seam effects, accepted strips were radiometrically balanced using robust percentile matching before mosaicking. Overlap zones were merged using a feathered weighted mean so strip edges contributed less strongly than strip centres.
```

### Standard Corrected Mosaic Method Used

The standard corrected mosaics were produced using robust percentile matching applied separately to each processed GeoTIFF strip before mosaicking.

For each strip:

```text
strip_low  = P10 of valid strip pixels
strip_mid  = P50 of valid strip pixels
strip_high = P90 of valid strip pixels
```

The survey reference tone is calculated as the median of those strip percentiles:

```text
reference_low  = median(strip P10 values)
reference_mid  = median(strip P50 values)
reference_high = median(strip P90 values)
```

Each valid pixel is adjusted using:

```text
scale = (reference_high - reference_low) / (strip_high - strip_low)
corrected_pixel = (pixel - strip_mid) * scale + reference_mid
```

Overlap zones are mosaicked using a feathered weighted mean:

```text
final_mosaic_pixel = weighted_mean(valid corrected strip values at that location)
```

The default settings use a 2 percent edge trim and an 8 percent feather zone. This reduces the influence of strip edges and hard survey-line seams while preserving local acoustic texture.

Interpretation caution:

```text
The standard corrected mosaic is not an absolute calibrated backscatter product.
It is a corrected relative acoustic-intensity product intended for visual interpretation, texture extraction, and unsupervised acoustic facies classification.
```

Methodology wording:

```text
To improve radiometric consistency between survey lines, each processed sidescan strip was adjusted to the median survey tone using a robust P10-P50-P90 percentile match. The corrected strips were then mosaicked using feathered overlap averaging. This reduced strip-to-strip brightness variation and trackline seam dominance while retaining local acoustic texture for subsequent feature extraction.
```

### Trackline And Seam Reduction

The uncorrected mosaic showed strong survey-line and trackline effects. These line effects are common in sidescan sonar mosaics and are usually caused by a mixture of acquisition geometry, range-dependent insonification, gain differences, towfish altitude changes, water-column/nadir effects, and overlap order. They should not automatically be interpreted as seabed facies.

Industry sidescan processing normally tries to reduce these effects through bottom tracking, slant-range correction, time-varied gain or beam-pattern correction, bad-line rejection, nadir/edge handling, line balancing, and overlap blending. SonarWiz, HYPACK, QPS, CARIS, and similar packages use this same general idea, although the exact implementation and controls differ by software.

For this project, the package default uses a reproducible line-balancing and feathered mosaicking rule instead of manual display stretching.

For each accepted strip, the following percentiles are calculated from valid pixels:

```text
strip_low  = P10
strip_mid  = P50
strip_high = P90
```

The survey reference tone is calculated as the median of those strip percentiles:

```text
reference_low  = median(strip P10 values)
reference_mid  = median(strip P50 values)
reference_high = median(strip P90 values)
```

Each strip is then linearly adjusted to the reference tone:

```text
scale = (reference_high - reference_low) / (strip_high - strip_low)
corrected_pixel = (pixel - strip_mid) * scale + reference_mid
```

This operation keeps the output in the processed acoustic-intensity value range instead of converting every strip to a 0-255 display scale. It also records the adjustment applied to each strip in:

```text
qc\strip_balance_report.csv
```

Overlap zones are mosaicked using a feathered mean. The centre of each strip receives stronger weight, while a configurable percentage of the strip edge receives lower weight. This reduces hard seam lines where adjacent strips overlap.

Recommended command for the AOI project:

```powershell
seabed-sidescan mosaic --project "MSc_Project_75m_AOI" --channels 0 1 --clean-output
```

Equivalent explicit command:

```powershell
seabed-sidescan mosaic --project "MSc_Project_75m_AOI" --channels 0 1 --clean-output --balance-low-percentile 10 --balance-mid-percentile 50 --balance-high-percentile 90 --feather-percent 8 --edge-trim-percent 2
```

Standard outputs:

```text
mosaics\SSS_ch0_standard_mosaic.tif
mosaics\SSS_ch1_standard_mosaic.tif
mosaics\SSS_combined_standard_mosaic.tif
qc\strip_balance_report.csv
```

Interpretation caution:

```text
The standard corrected mosaic is a corrected relative acoustic-intensity product.
It is not absolute calibrated backscatter in dB.
It should be used for texture extraction and unsupervised acoustic facies classification when the mosaic is affected by survey-line bias.
```

Report wording:

```text
To reduce line-to-line radiometric striping, accepted sidescan strips were balanced before mosaicking using a robust P10-P50-P90 percentile matching approach. Each strip was adjusted to the median survey tone, and overlap zones were merged using a feathered mean to reduce hard seam effects. The resulting mosaic represents corrected relative acoustic intensity and was used for texture extraction and unsupervised acoustic facies classification. Because no manufacturer-calibrated backscatter correction was available, the product was not interpreted as absolute dB backscatter.
```

### How Overlapping Strips Are Represented In A Mosaic

When multiple GeoTIFF strips overlap, the mosaic output is still a normal single-band raster. This means each final mosaic pixel stores one value, not a stack of every overlapping strip value.

In the current automated mosaic script, the overlap method is:

```text
mean
```

This means that where two or more valid strips overlap, the final pixel stores the arithmetic mean of the valid overlapping values. The individual underlying strip values are not kept inside the final single-band mosaic pixel. The companion `*_overlap_count.tif` rasters record how many strips contributed to each output pixel.

Important distinction:

```text
GIS visual overlay: multiple layers may be drawn on top of each other.
Mosaic raster: one output raster pixel value is stored at each location.
```

Therefore, if channel 0 and channel 1 are both switched on in GIS, the top layer in the layer list may visually cover the lower one. That is not the same as a true combined raster unless a separate combination/mosaic operation has been run.

For classification, this matters because overlap handling can influence seam effects. The final package approach therefore uses:

```text
strip QC before mosaicking
robust P10-P50-P90 line balancing
light strip-edge handling
feathered weighted averaging in overlap zones
```

Methodology wording:

```text
Overlapping sidescan strips were mosaicked into single-band raster surfaces. Where overlaps occurred, only one output value was stored per mosaic cell according to the selected merge rule. The resulting mosaics were visually inspected for seam effects before being used for feature extraction.
```

Report wording:

```text
Accepted georeferenced sidescan strips were mosaicked into single-band raster surfaces after robust line-to-line acoustic intensity balancing. Where overlaps occurred, only one output value was stored per mosaic cell using a feathered weighted mean of the valid corrected strip values.
```

## Next Stage 3: Create A Valid-Data Mask

Before texture extraction, create a valid-data mask from:

```text
SSS_combined_standard_mosaic.tif
```

The mask stores:

```text
1 = valid sidescan data
0 = NoData / outside survey coverage / transparent gap
```

This is needed because the GIS basemap may show water through transparent raster gaps. Those gaps are not seabed observations and must not be included in texture calculation or classification.

Packaged command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_valid_data_mask.ps1 -ProjectName "MSc_Project_100m"
```

Output:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\masks\SSS_valid_data_mask.tif
```

Methodology wording:

```text
A binary valid-data mask was generated from the standard corrected sidescan mosaic to separate valid acoustic observations from NoData gaps and areas outside the survey coverage. Only pixels within the valid-data mask were used for subsequent texture extraction and classification.
```

Where an area-of-interest boundary was supplied, the polygon was rasterized on the same grid as the standard corrected mosaic. The final analysis mask was calculated as the intersection of the polygon footprint and valid sidescan coverage. Texture extraction, feature stacking, clustering, and classification were therefore restricted to valid acoustic pixels inside the defined project boundary, while complete mosaics were retained for quality control.

## Next Stage 4: Prepare Bathymetry Support Layers

Use the SBES points as supporting terrain information if they are spatially reliable.

Main SBES layer:

```text
depth raster
```

Possible derived terrain layers:

```text
slope
roughness
local relief
curvature, if useful
```

The bathymetry layers should be resampled or aligned to the same CRS and approximate resolution as the SSS mosaic.

Important note:

```text
SBES bathymetry supports interpretation, but the unsupervised acoustic facies classification is mainly driven by SSS backscatter and texture.
```

## Next Stage 5: Derive Texture Features From SSS

The classification should not use only raw brightness. It should use texture features because seabed types/facies often differ by tone and spatial pattern.

Core texture layers to derive from the SSS mosaic:

```text
SSS_mean.tif
SSS_standard_deviation.tif
SSS_entropy.tif
SSS_contrast.tif
SSS_homogeneity.tif
SSS_energy_or_ASM.tif
SSS_variance.tif
```

These can be created using open-source GIS/Python methods such as:

```text
QGIS
Orfeo ToolBox
GRASS GIS
SAGA GIS
Python with rasterio, scikit-image, numpy
```

Methodology wording:

```text
Texture measures were derived from the sidescan mosaic to describe local acoustic variability, roughness, and spatial arrangement of backscatter values.
```

### Texture Extraction Method Used

Texture extraction was automated using:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\extract_texture_features.ps1 -ProjectName "MSc_Project_100m"
```

Input raster:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_combined_standard_mosaic.tif
```

Mask raster:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\masks\SSS_valid_data_mask.tif
```

Default parameters:

```text
moving window: 15 x 15 pixels
GLCM quantization: 16 grey levels
GLCM quantization range: 2nd-98th valid-pixel percentiles
GLCM directions: 0, 90, 45, 135 degrees
analysis area: valid SSS mask only
```

Texture outputs:

```text
SSS_mean.tif
SSS_standard_deviation.tif
SSS_variance.tif
SSS_entropy.tif
SSS_contrast.tif
SSS_homogeneity.tif
SSS_ASM.tif
SSS_energy.tif
```

Mean, standard deviation, and variance were calculated as local focal statistics inside the moving window. Mean and standard deviation retain the input raster's units; variance uses squared input units. Entropy was calculated from the quantized local grey-level distribution. Contrast, homogeneity, angular second moment (ASM), and energy were calculated using local grey-level co-occurrence matrix measures across four directions. For entropy and GLCM features, the input mosaic was internally quantized to 16 grey levels using the 2nd-98th percentile range of valid pixels; this binning step is separate from mosaic line balancing.

The valid-data mask was applied so that NoData gaps and areas outside sidescan coverage were excluded from texture extraction.

Methodology wording:

```text
Texture features were extracted from the sidescan mosaic using a 15 x 15 pixel moving window. Local mean, variance, and standard deviation were calculated directly from the mosaic values. For entropy and GLCM-based measures, the mosaic was quantized to 16 grey levels using a robust 2nd-98th percentile valid-pixel range, and four directions (0, 90, 45, and 135 degrees) were used to reduce directional bias. The valid-data mask was applied so that only pixels covered by sidescan observations contributed to the texture layers.
```

## Next Stage 6: Build A Classification Feature Stack

All input rasters must match:

```text
same CRS
same pixel size
same extent
same NoData mask
same row/column alignment
```

Likely feature stack:

```text
SSS backscatter mosaic
SSS mean
SSS standard deviation
SSS entropy
SSS contrast
SSS homogeneity
SSS energy/ASM
SSS variance
optional depth
optional slope
optional roughness
```

This feature stack is the "training data" for unsupervised classification. In this project, training data does not mean labelled sediment samples. It means the image pixels or image objects described by their acoustic and terrain features.

In the packaged workflow, the feature stack is generated with:

```powershell
seabed-sidescan stack-features --project "MSc_Project_100m"
```

By default, the stack contains the standard corrected sidescan mosaic, local mean, standard deviation, entropy, contrast, homogeneity, and energy. Variance and ASM are not included by default because they duplicate information already represented by standard deviation and energy.

## Next Stage 7: Run Unsupervised Classification

Recommended algorithms:

```text
K-means clustering
ISODATA clustering
Gaussian Mixture Model
object-based clustering, if segmentation is used
```

Start with a small number of classes:

```text
3 to 6 acoustic facies
```

Before final classification, candidate class counts should be evaluated using internal unsupervised metrics:

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_100m" --classes 3 4 5 6
```

The evaluation report includes inertia, silhouette score, Calinski-Harabasz score, Davies-Bouldin score, class balance, and stability using adjusted Rand index across repeated runs.

The implemented classification approach uses `scikit-learn` `KMeans` with `k-means++` initialization and multiple restarts:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 4
```

Feature values are standardized before clustering so that all feature layers contribute on a comparable scale. This prevents high-range variables such as contrast from dominating lower-range variables such as homogeneity or energy.

Then compare results visually against:

```text
sidescan mosaic
texture layers
bathymetry
known seabed morphology
survey line patterns
```

Because there are no sediment samples, the classes should be named cautiously:

```text
low-backscatter smooth facies
moderate-backscatter mixed facies
high-backscatter rough facies
heterogeneous acoustic facies
possible hard/rough seabed zone
possible soft/smooth seabed zone
```

Avoid claiming confirmed sediment types such as sand, mud, gravel, or rock unless external validation is added later.

## Next Stage 8: Clean And Interpret Classes

After classification:

```text
remove small isolated patches
smooth class boundaries only where appropriate
compare classes with SSS tone and texture
compare classes with bathymetry
produce final acoustic facies map
```

The interpretation should explain what each class likely represents acoustically, not as confirmed sediment.

The packaged cleanup command is:

```powershell
seabed-sidescan clean-classification --project "MSc_Project_100m" --classes 4
```

The cleanup is conservative: one 3 x 3 majority-filter pass is applied, class 0 / NoData is preserved, and connected patches smaller than 25 pixels are replaced only when a strict surrounding majority exists. Ties and components without valid neighbours retain their original class. The raw classification remains the analytical output, while the cleaned raster is used for final cartographic presentation and interpretation.

## Report Methodology Structure

Use this order in Chapter 3:

```text
1. Data sources
2. Raw SSS file structure and channel selection
3. SSS preprocessing
4. Slant range correction
5. Radiometric/gain correction
6. Georeferencing and GeoTIFF production
7. Quality control of processed sidescan strips
8. Sidescan mosaic creation
9. SBES bathymetry preparation
10. Texture feature extraction
11. Feature stack preparation
12. Unsupervised classification
13. Acoustic facies interpretation
14. Limitations due to lack of sediment ground truth
```

## Strip Quality-Control Sequence

Inspect the processed strips before mosaicking, texture extraction and classification:

```text
Open the 88 GeoTIFFs in QGIS.
Inspect line quality.
Identify any bad lines.
Create separate channel 0 and channel 1 mosaics.
```

Only after the mosaic is clean should texture extraction and unsupervised classification begin.
