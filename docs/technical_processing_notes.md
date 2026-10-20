# Technical Processing Notes

This project is being handled as an unsupervised seabed acoustic facies classification workflow.

No sediment samples or ground-truth labels are currently available, so the classification should be described as acoustic facies or seabed texture classification, not supervised sediment classification.

## Main XTF Finding

The `.xtf` extension is only a container format. The channel structure was confirmed by reading internal XTF headers with `pyxtf`.

The tested Klein XTF file contains:

```text
NumberOfSonarChannels = 4
```

The channel structure observed was:

```text
Channels 0 and 1: 2084 samples each, 100 m slant range
Channels 2 and 3: 3126 samples each, 75 m slant range
```

This indicates two likely port/starboard pairs:

```text
0,1 = wider 100 m pair
2,3 = narrower 75 m pair
```

For the main project run, channels `0,1` are recommended first because they provide wider spatial coverage.

## Current Processing Chain

```text
Raw XTF files
-> select consistent port/starboard pair
-> bottom detection/refinement
-> slant range correction
-> beam/gain correction
-> dB conversion and contrast enhancement
-> georeferencing
-> GeoTIFF output
-> mosaic creation
-> texture feature extraction
-> unsupervised classification
```

## Successful Disposable GIS Test

One test line was processed successfully:

```text
D:\a\SSS_processing\test_small\PL018220414110300.xtf
```

Outputs were written to:

```text
D:\a\SSS_processing\projects\<project-name>\georef_out
```

GDAL confirmed:

```text
CRS: EPSG:32632 - WGS 84 / UTM zone 32N
Pixel size: approximately 1 m
Valid raster values: yes
Approximate coverage: 7.326-7.328 E, 4.247-4.262 N
```

## Disk Space Note

Navigation CSV export is disabled in the main full-processing config:

```yaml
active_export_navigation: false
```

The disposable test config keeps it enabled only for QC.

Current packaged scripts create one named project folder per run:

```text
D:\a\SSS_processing\projects\<project-name>\
  georef_out\
  previews\
  configs\
  logs\
```

This prevents separate processing attempts from overwriting or mixing outputs.

## Full Processing Completion Note

The full `0,1` channel-pair processing run was completed for project:

```text
MSc_Project_100m
```

Output folder:

```text
D:\a\SSS_processing\projects\MSc_Project_100m
```

Observed output count:

```text
44 channel 0 GeoTIFFs
44 channel 1 GeoTIFFs
44 processed PNG previews
```

Post-processing sequence:

```text
processed strip QC
channel-wise mosaic creation
texture feature extraction
feature stack preparation
unsupervised classification
acoustic facies interpretation
```

Detailed post-processing steps are documented in:

```text
docs/post_processing_methodology.md
```

## Report Wording

Use cautious wording:

```text
unsupervised acoustic seabed facies classification
```

Avoid claiming confirmed sand, mud, gravel, or rock classes unless external validation is later provided.
