# QGIS QC Checklist

Use this checklist after the disposable test and again after full processing.

## Load Test GeoTIFFs

In QGIS:

```text
Layer -> Add Layer -> Add Raster Layer
```

Load:

```text
D:\a\SSS_processing\projects\<project-name>\georef_out\*.tif
```

Set or confirm project CRS:

```text
EPSG:32632 - WGS 84 / UTM zone 32N
```

## What To Check

- Rasters should not appear at coordinate `0,0`.
- Rasters should fall around longitude `7.32 E`, latitude `4.25 N`.
- Channel 0 and channel 1 should appear as narrow strips on opposite sides of the survey track.
- The raster should not be blank.
- The image should look like a sidescan swath, not a random square block.
- Pixel values should display with a grayscale stretch.
- If a basemap is added, the strips should fall in the expected study area.

## How To Recognize Bad Lines

Use this practical interpretation when looking at all processed strips together.

### Good / Acceptable Lines

Acceptable lines usually have:

- A visible grey sidescan texture, not an empty rectangle.
- A long narrow swath shape following the survey direction.
- Gradual tonal variation across the swath.
- Seafloor texture such as speckle, ripples, patches, rough zones, or smooth zones.
- Position consistent with neighbouring survey lines.
- Overlap with adjacent strips where survey lines are close.

### Blank Or Nearly Blank Lines

A line is likely bad if it is:

- Almost completely one colour, such as all black, all white, or all transparent.
- Mostly NoData/background.
- A rectangle with no sonar texture.
- Missing one side completely when other lines show both sides.

Do not use blank lines for mosaicking or classification.

Important distinction:

```text
A strip that looks black in QGIS is not automatically bad.
```

It may simply have lower backscatter values than neighbouring strips or be affected by the current display stretch. Use the automated QC report to check whether it has valid pixels and measurable variation.

## Interpreting The Standard Corrected Mosaic

The standard corrected mosaics should look more balanced than the uncorrected strip mosaic because each line is adjusted to a common robust acoustic-intensity reference before overlap feathering.

This is useful when:

- raw strips have strong brightness differences,
- overlap seams dominate the display,
- classification would otherwise separate survey lines instead of seabed texture.

Remaining gaps are still real coverage gaps or NoData areas. Line balancing and feathering improve tonal consistency; they do not create data where no valid pixels exist.

### Displaced Lines

A line may be displaced if it:

- Appears far away from the survey block.
- Crosses other lines at an unrealistic angle.
- Is shifted so much that it does not follow the general survey pattern.
- Appears in a different geographic area from the other strips.

Check displaced-looking lines against the survey plan or navigation track before removing them.

### Lines With Strong Artifacts

Some artifacts are common in sidescan sonar and do not always mean the whole line is bad.

Common artifacts include:

- Bright or dark nadir band near the centre/trackline.
- Outer-range fading or brightening.
- Sharp seams where overlapping strips have different brightness.
- Small gaps caused by interpolation or NoData.
- Curved or widened sections during turns.

These lines may still be usable, but the artifact area should be treated carefully during mosaicking and classification.

## QC Decision Categories

Classify each strip into one of three practical categories:

```text
Keep: good texture and position.
Review: usable but has strong artifacts, turns, uneven brightness, or overlap issues.
Reject: blank, badly displaced, corrupted, or mostly NoData.
```

For this project, most lines should be kept unless they are blank or clearly out of position. Artifact-heavy zones can be handled later during mosaicking, masking, or interpretation.

## Warning Signs

- Raster appears far outside Nigeria.
- Raster appears at Null Island around `0,0`.
- Raster has no visible pixels after contrast stretch.
- Channel strips are strangely rotated or separated far from each other.
- Output is dominated by NoData.

If any warning sign appears, stop before full batch processing and review navigation, CRS, channel pair, and georeferencing settings.
