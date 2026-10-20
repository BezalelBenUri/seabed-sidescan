# Technical Processing Notes for SSS-Based Unsupervised Seabed Classification

Date: 2026-06-12

## Project Direction

The project is being treated as an unsupervised seabed acoustic facies classification workflow. Since no sediment samples or ground-truth labels are available, the classification will be based on acoustic and spatial patterns extracted from processed side scan sonar imagery and supporting bathymetry where usable.

The output will not be a supervised sediment-class map. It will be an acoustic facies or seabed texture class map, with classes interpreted from sonar backscatter texture, tone, and morphology.

## Available Main Data

- Raw side scan sonar files in XTF format.
- SBES sounding data, likely usable for bathymetric support and terrain context.
- Existing processed/project documents already in the workspace.

## Important XTF Finding

The `.xtf` extension alone does not reveal the internal sonar channel structure. XTF is only a container format.

Using `pyxtf`, the internal headers of the test XTF file showed:

- `NumberOfSonarChannels = 4`
- Channels `0` and `1`: 2084 samples each, 100 m slant range
- Channels `2` and `3`: 3126 samples each, 75 m slant range

This means the file contains two likely port/starboard pairs:

- Channels `0,1`: one complete sidescan pair with 100 m range
- Channels `2,3`: another complete sidescan pair with 75 m range

This is why the original SidescanTools loader failed. It expected a simple two-channel file, but the XTF contains four channels with different sample widths.

## Processing Decision

For the main project run, channels `0,1` are recommended first because they provide the wider 100 m swath. This gives better spatial coverage for building a broad study-area mosaic.

Channels `2,3` may be processed later as a comparison or higher-detail experiment, but they should not be mixed directly with channels `0,1` in the same classification workflow unless the differences in range/resolution are handled carefully.

## Current Software Setup

SidescanTools was installed in a conda environment:

- Environment name: `env_sidescantools_cli`
- Local repository: `D:\sidescantools-main`
- Processing folder: `D:\a\SSS_processing`

Conda is preferred for this project because GDAL, GMT, PyGMT, Rasterio, and related geospatial packages are difficult to install reliably with pip alone on Windows.

SidescanTools itself was installed using pip editable mode inside the conda environment.

For full batch processing, navigation CSV export was disabled in:

```text
D:\a\SSS_processing\sidescantools_project_info.yml
```

The setting is:

```yaml
active_export_navigation: false
```

This was done because the disposable test produced very large navigation CSV files. Keeping navigation export enabled for all 44 raw files could create tens of gigabytes of extra CSV output. The GeoTIFF rasters remain georeferenced without keeping these CSVs.

## Local Tool Adjustments

Two practical compatibility adjustments were made to the local SidescanTools copy:

1. GUI-only imports were made optional so the CLI can run without installing the full Qt/Napari GUI stack.
2. The XTF reader was adjusted to process a selected two-channel pair from four-channel Klein XTF files.

The default selected pair is:

```text
SIDESCANTOOLS_XTF_CHANNEL_PAIR = 0,1
```

The optional alternative pair is:

```text
SIDESCANTOOLS_XTF_CHANNEL_PAIR = 2,3
```

## Successful Test Run

Test file:

```text
D:\a\SSS_processing\test_small\PL018220414110300.xtf
```

The test run successfully produced:

- Processed PNG preview
- Georeferenced channel 0 GeoTIFF
- Georeferenced channel 1 GeoTIFF
- Navigation CSV files

The output GeoTIFFs are projected in:

```text
EPSG:32632 - WGS 84 / UTM zone 32N
```

This confirms that the installation and first-stage SSS processing workflow are usable.

## Disposable GIS Georeferencing Test

A separate disposable GIS test was run before full batch processing.

Test input:

```text
D:\a\SSS_processing\test_small\PL018220414110300.xtf
```

Test config:

```text
D:\a\SSS_processing\gis_georef_test_config.yml
```

Disposable output folder:

```text
D:\a\SSS_processing\gis_georef_test
```

The test generated:

```text
PL018220414110300_1m_ch0_EPSG32632.tif
PL018220414110300_1m_ch1_EPSG32632.tif
Navigation_PL018220414110300_ch0.csv
Navigation_PL018220414110300_ch1.csv
```

GDAL inspection confirmed:

- CRS: `EPSG:32632 - WGS 84 / UTM zone 32N`
- Pixel size: approximately 1 m
- Valid raster values are present in both channel outputs
- Approximate geographic coverage: 7.326-7.328 E, 4.247-4.262 N

This means the test GeoTIFFs are GIS-ready and should load in QGIS at their correct map location.

## Processing Workflow for the Project

The intended workflow is:

```text
Raw XTF files
→ select consistent port/starboard pair
→ bottom detection/refinement
→ slant range correction
→ gain correction / backscatter normalization
→ georeferencing
→ GeoTIFF output
→ mosaic creation
→ texture feature extraction
→ unsupervised classification
→ class interpretation and map production
```

## Classification-Ready Data Needed

The classification should use raster layers with the same coordinate system, pixel size, and spatial extent.

Core layers should include:

- Processed SSS backscatter mosaic
- Texture layers derived from the SSS mosaic, such as mean, standard deviation, entropy, contrast, homogeneity, energy/ASM, and variance
- Optional bathymetry/terrain layers from SBES if they can be gridded cleanly, such as depth, slope, and roughness

The training data for unsupervised classification is not manually labelled sediment data. Instead, the model uses image pixels or segmented image objects described by their acoustic and texture features.

## Key Caution for Report

Because there are no sediment samples, the project cannot claim direct supervised sediment-type classification. The more defensible wording is:

```text
unsupervised acoustic seabed facies classification
```

or:

```text
unsupervised seabed texture classification from side scan sonar imagery
```

Any final class names should be interpreted cautiously, for example:

- low-backscatter smooth facies
- high-backscatter rough facies
- mixed/heterogeneous facies
- possible sediment/morphology zones

They should not be presented as confirmed sand, mud, gravel, or rock unless external validation is later provided.

## Next Technical Steps

1. Batch-process the full raw SSS folder using channels `0,1`.
2. Review the generated GeoTIFFs and PNG previews for bad lines, blank outputs, georeferencing problems, or strong artifacts.
3. Decide whether channels `2,3` should also be processed for comparison.
4. Merge the acceptable channel outputs into a clean sidescan mosaic.
5. Derive texture rasters from the mosaic in GIS or Python.
6. Grid the SBES soundings if useful and derive supporting terrain layers.
7. Stack all classification features into a common raster grid.
8. Run unsupervised classification such as K-means, ISODATA, Gaussian Mixture Model, or object-based clustering.
9. Clean and interpret the classes using sonar appearance, bathymetry, and study-area knowledge.
10. Produce final maps, methodology, limitations, and discussion for the report.
