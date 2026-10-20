# Python Package Usage

The Python package is named `seabed-sidescan`, imported as `seabed_sidescan`.
The raster-analysis engine needs Python 3.10 or later. It works independently
of QGIS and the optional raw-sonar backend.

## Portable installation and API

Create a separate Python environment, then install this checkout or a local
wheel. Public PyPI installation will be available after publication.

```console
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install /path/to/seabed_sidescan_solution
seabed-sidescan --help
```

For an existing feature stack, explicit paths avoid any survey-folder layout:

```python
from seabed_sidescan.api import create_mask, classify

mask = create_mask("mosaic.tif", "analysis/mask.tif")
result = classify("features.tif", mask, "analysis/facies.tif", classes=4)
print(result.output_raster)
```

The feature stack must contain valid feature values on the same grid as the
mask. See the explicit-path API section below for all operations and return
values. Users working through QGIS can follow [the plugin guide](qgis_plugin.md).

## Existing Windows survey environment

The examples in this section use the original local survey folders and a
separately prepared raw-backend environment. They are useful when reproducing
that workflow; the portable raster-analysis installation above needs no conda
environment. The command-line entry point is:

```powershell
seabed-sidescan
```

Use this from the solution folder:

```powershell
cd D:\a\seabed_sidescan_solution
conda activate env_sidescantools_cli
```

If the environment has not been prepared yet, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_environment.ps1
```

That setup script installs both:

```text
vendor\sidescantools-main
D:\a\seabed_sidescan_solution
```

in editable mode, so code changes in the repository are immediately reflected in the command.

## Install Or Reinstall The Package Manually

Use this when the environment already exists and only the package needs to be refreshed:

```powershell
conda activate env_sidescantools_cli
python -m pip install -e D:\a\seabed_sidescan_solution
```

Confirm it works:

```powershell
seabed-sidescan --version
seabed-sidescan --help
```

Confirm `scikit-learn` is available for classification:

```powershell
python -c "import sklearn; print(sklearn.__version__)"
```

## Check Input Data

Automatic discovery:

```powershell
seabed-sidescan list-input
```

Explicit input folder:

```powershell
seabed-sidescan list-input --input "D:\a\SSS RAW"
```

The command checks for `.xtf` and `.jsf` files. If `--input` is omitted, it checks:

```text
SSS_INPUT_PATH environment variable
D:\a\seabed_sidescan_solution\data\raw
D:\a\seabed_sidescan_solution\data\sss_raw
D:\a\SSS RAW
D:\a\SSS_raw
D:\a\SSS
```

## Run Raw SSS Processing

Process the 100 m Klein port/starboard pair, channels `0,1`:

```powershell
seabed-sidescan process --project "MSc_Project_100m" --input "D:\a\SSS RAW"
```

Check paths and create the runtime config without starting the long processing job:

```powershell
seabed-sidescan process --project "MSc_Project_100m" --input "D:\a\SSS RAW" --dry-run
```

Process the alternate 75 m pair, channels `2,3`:

```powershell
seabed-sidescan process --project "MSc_Project_75m" --input "D:\a\SSS RAW" --channel-pair "2,3"
```

This creates:

```text
D:\a\SSS_processing\projects\<project-name>\georef_out
D:\a\SSS_processing\projects\<project-name>\previews
D:\a\SSS_processing\projects\<project-name>\configs
D:\a\SSS_processing\projects\<project-name>\logs
```

The command streams SidescanTools progress directly in the terminal.

## Build Mosaics

Create the standard corrected channel mosaics, combined mosaic, overlap rasters, strip QC report, and strip balance report:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --clean-output
```

`--clean-output` clears previous raw, normalized, balanced, standard, and AOI mosaic outputs from the project `mosaics` folder. It leaves the raw XTF files and `georef_out` strips untouched.

Optional stricter strip QC:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --min-valid-percent 5 --min-std 1 --min-percentile-range 5
```

Optional channel-only mosaics:

```powershell
seabed-sidescan mosaic --project "MSc_Project_100m" --skip-combined
```

Standard mosaicking method:

```text
1. Each georeferenced strip is checked using valid-pixel percentage, standard deviation, and percentile range.
2. Accepted strips are radiometrically balanced using P10, P50, and P90 percentile matching.
3. The outer 2 percent of each strip is downweighted/trimmed to reduce edge and nadir artefacts.
4. Overlapping strips are merged with an 8 percent feathered weighted mean.
5. Channel products and the combined mosaic are written as standard corrected acoustic-intensity GeoTIFFs.
```

This product is the package default for texture extraction and unsupervised acoustic facies classification. It is corrected relative acoustic intensity, not manufacturer-calibrated absolute dB backscatter.

## Create Valid-Data Mask

```powershell
seabed-sidescan mask --project "MSc_Project_100m"
```

Apply an analysis boundary:

```powershell
seabed-sidescan mask --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

The boundary is rasterized on the mosaic grid. The downstream analysis mask contains `1` only where valid SSS data intersects the polygon. The command validates geometry type, reads the shapefile `.prj`, reprojects the polygon if needed, and stops if the boundary does not overlap the mosaic.

## Clip A Raster For Mapping

The analysis mask does not physically crop the source mosaic. Create a separate map-ready AOI raster with:

```powershell
seabed-sidescan clip-raster --project "MSc_Project_75m_AOI" --boundary "D:\a\SSS_processing\projects\Boundary.shp"
```

This produces `mosaics\SSS_combined_standard_mosaic_AOI.tif`. The original mosaic remains unchanged for QC and reproducibility.

Default input:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\mosaics\SSS_combined_standard_mosaic.tif
```

Default output:

```text
D:\a\SSS_processing\projects\MSc_Project_100m\masks\SSS_valid_data_mask.tif
```

Mask values:

```text
1 = valid SSS mosaic pixel
0 = NoData / outside side-scan coverage
```

The blue water shown by ArcGIS is a basemap, not raster data. The mask is made from the actual SSS mosaic valid pixels.

## Extract Texture Features

```powershell
seabed-sidescan textures --project "MSc_Project_100m"
```

Default settings:

```text
Input raster: mosaics\SSS_combined_standard_mosaic.tif
Mask raster: masks\SSS_valid_data_mask.tif
Window size: 15 x 15 pixels
GLCM quantization: 16 grey levels
GLCM directions: 0, 90, 45, and 135 degrees
```

Outputs:

```text
textures\SSS_mean.tif
textures\SSS_standard_deviation.tif
textures\SSS_variance.tif
textures\SSS_entropy.tif
textures\SSS_contrast.tif
textures\SSS_homogeneity.tif
textures\SSS_ASM.tif
textures\SSS_energy.tif
```

Exploratory faster run:

```powershell
seabed-sidescan textures --project "MSc_Project_100m" --levels 8
```

Larger neighbourhood texture:

```powershell
seabed-sidescan textures --project "MSc_Project_100m" --window-size 21
```

## Build The Feature Stack

Create the multi-band raster used as the input to unsupervised classification:

```powershell
seabed-sidescan stack-features --project "MSc_Project_100m"
```

Default feature bands:

```text
1. SSS_corrected_relative_acoustic_intensity
2. SSS_mean
3. SSS_standard_deviation
4. SSS_entropy
5. SSS_contrast
6. SSS_homogeneity
7. SSS_energy
```

Default outputs:

```text
features\SSS_feature_stack.tif
features\SSS_feature_stack_bands.csv
```

`SSS_variance` and `SSS_ASM` are not included by default because they duplicate information already represented by standard deviation and energy. To include them anyway:

```powershell
seabed-sidescan stack-features --project "MSc_Project_100m" --include-redundant
```

## Evaluate Candidate Class Counts

Evaluate `k=3,4,5,6` before deciding the final number of acoustic facies:

```powershell
seabed-sidescan evaluate-clusters --project "MSc_Project_100m" --classes 3 4 5 6
```

Default outputs:

```text
classification\cluster_evaluation.csv
classification\cluster_evaluation_summary.txt
```

The evaluation report includes:

```text
inertia
silhouette score
Calinski-Harabasz score
Davies-Bouldin score
class balance
stability using adjusted Rand index across repeated runs
```

## Run Unsupervised Classification

Start with four acoustic facies classes:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 4
```

Try other class counts for comparison:

```powershell
seabed-sidescan classify --project "MSc_Project_100m" --classes 3
seabed-sidescan classify --project "MSc_Project_100m" --classes 5
seabed-sidescan classify --project "MSc_Project_100m" --classes 6
```

Default classification outputs:

```text
classification\SSS_acoustic_facies_k4.tif
classification\SSS_acoustic_facies_k4_report.csv
classification\SSS_acoustic_facies_k4_model.json
```

The classifier uses `scikit-learn` `KMeans` with `k-means++` initialization, `n_init=50`, and `max_iter=500`. Feature values are standardized by default so that high-range layers such as contrast do not dominate low-range layers such as homogeneity.

## Clean The Classification

Create a conservative cartographic cleanup of the final classification:

```powershell
seabed-sidescan clean-classification --project "MSc_Project_100m" --classes 4
```

Default cleanup settings:

```text
3 x 3 majority filter, applied once
replace connected patches smaller than 25 pixels when a strict surrounding majority exists
preserve class 0 / NoData
```

Default outputs:

```text
classification\SSS_acoustic_facies_k4_cleaned.tif
classification\SSS_acoustic_facies_k4_cleanup_report.txt
```

Keep the raw classification as the analytical output and use the cleaned raster for final map presentation and interpretation.

Pixels and small patches retain their current class when no valid strict
majority exists, including ties and isolated components without neighbours.

## Package Modules

The reusable Python modules are:

```text
src\seabed_sidescan\cli.py
src\seabed_sidescan\clip.py
src\seabed_sidescan\mosaic.py
src\seabed_sidescan\mask.py
src\seabed_sidescan\texture.py
src\seabed_sidescan\features.py
src\seabed_sidescan\evaluate.py
src\seabed_sidescan\classify.py
src\seabed_sidescan\cleanup.py
src\seabed_sidescan\paths.py
```

The older entry points in `tools\` delegate to the maintained package implementations, so scripts and package calls use the same numerical methods.

## Explicit-path public API

The `seabed_sidescan.api` module provides `create_mask`, `extract_textures`, `stack_features`, `classify`, `evaluate_clusters`, `clean_classification`, `clip_raster`, and `build_mosaics`. These accept `str` or `Path` arguments and return absolute output paths or frozen result dataclasses. They do not require a named project or the Windows survey folder layout. The optional `process_sonar` adapter creates a named raw-processing project under an explicitly supplied output root.

```python
from seabed_sidescan.api import create_mask, classify

mask = create_mask("mosaic.tif", "analysis/mask.tif")
result = classify("analysis/features.tif", mask, "analysis/facies.tif", classes=4)
print(result.output_raster)
```

Importing the API does not import QGIS, SidescanTools, or the numerical libraries until an operation is called. Use `help()` on each function for parameter names and defaults. `seabed_sidescan.classify_facies` is also available as a root-level alias; the `classify` name at package root identifies the existing implementation module.

Texture extraction returns `TextureResult(output_dir, rasters)`. Feature stacking returns `FeatureStackResult(output_stack, metadata_csv)`. Classification returns `ClassificationResult(output_raster, report_csv, model_json)`. Cluster evaluation returns `EvaluationResult(output_csv, summary_txt)`. Cleanup returns `CleanupResult(output_raster, report_txt)`. Mosaicking returns `MosaicResult(mosaics, overlap_counts, qc_report, balance_report, method_report)` containing only products created by the current call.

Inputs remain unchanged. Operations overwrite selected output paths; choose fresh output paths to preserve prior analyses. The API rejects direct input/output collisions. Raster feature bands and analysis masks must share a grid and CRS. Classification area summaries require a projected CRS with metre units and report planar pixel areas; use a suitable local or equal-area projection when interpreting totals. Class IDs belong to the fitted model rather than a universal facies legend. Core polygon operations accept ESRI shapefiles and read CRS from their `.prj`, or from an explicit override.

Named-project CLI commands are retained for existing users. Set `--project-root` or `SSS_PROJECT_ROOT` to avoid relying on automatic directory discovery. Explicit raster paths can be used without any project. The optional `process` command additionally requires a separately installed, patched SidescanTools checkout and its Python 3.12+ environment; use `--sidescantools-repo` and `--sidescantools-python` to select them.

### Optional raw-processing API

```python
from seabed_sidescan.api import process_sonar

plan = process_sonar(
    "raw_survey", "projects", "survey",
    sidescantools_repo="/path/to/patched/sidescantools",
    sidescantools_python="/path/to/raw/environment/python",
    channel_pair=(0, 1), resolution=1.0, dry_run=True,
)
print(plan.runtime_config)
```

A dry run prepares and writes the project configuration. Set `dry_run=False` to start the separately provisioned backend. The result includes `project_dir`, `georef_dir`, `runtime_config`, and `previews_dir`. A successful process requires the patched backend's manifest and newly created or updated, readable GeoTIFFs for both requested channels of every selected input. The caller still needs to inspect per-strip logs, coverage, navigation, and output metadata. Python 3.10+ can call a separately selected Python 3.12+ raw interpreter.
