# Seabed Sidescan

Python tools for analysing georeferenced side-scan sonar rasters and producing unsupervised acoustic seabed facies maps. The same processing engine is available through a Python API, the `seabed-sidescan` command, and a QGIS Processing plugin.

Version 0.1.0 is the first public-release candidate; earlier 0.6.0 and 0.7.0 numbers identified unpublished local builds. The project's own code is licensed under GPL-3.0-or-later; third-party code retains its existing license and attribution. Maintainer metadata and release workflows are configured. Publication requires a public source repository, account setup and an index installation rehearsal; validation scope and workload limits are recorded in the [quality review](docs/quality_review.md). Field sediment samples and independent survey control are outside the software release requirements. The distributions are built locally; they have not been uploaded to PyPI or the QGIS directory.

## Install

Use Python 3.10 or later in a separate environment. For this source checkout:

```console
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install .
seabed-sidescan --help
python -m seabed_sidescan --version
```

Once published, the package will be installed with `python -m pip install seabed-sidescan`. Until then, install this checkout or a locally built wheel.

## Python API

All operations accept explicit input/output paths and return output paths or result objects. They do not require a survey folder layout or QGIS.

```python
from pathlib import Path
from seabed_sidescan.api import (
    create_mask, extract_textures, stack_features, classify,
)

work = Path("analysis")
mosaic = Path("survey_mosaic.tif")
mask = create_mask(mosaic, work / "valid_mask.tif")
textures = extract_textures(mosaic, mask, work / "textures", window_size=15)
features = stack_features(
    [mosaic, textures.output_dir / "SSS_entropy.tif",
     textures.output_dir / "SSS_contrast.tif"],
    mask,
    work / "features.tif",
    band_names=["intensity", "entropy", "contrast"],
)
result = classify(features.output_stack, mask, work / "facies.tif", classes=4)
print(result.output_raster, result.report_csv, result.model_json)
```

Other operations are `build_mosaics`, `clip_raster`, `evaluate_clusters`, `clean_classification`, and the optional raw-backend adapter `process_sonar`. See [Python package usage](docs/python_package_usage.md).

## Command line

```console
seabed-sidescan mask --input-raster survey_mosaic.tif --output-mask analysis/mask.tif
seabed-sidescan textures --input-raster survey_mosaic.tif --mask-raster analysis/mask.tif --output-dir analysis/textures
seabed-sidescan stack-features --input-rasters survey_mosaic.tif analysis/textures/SSS_entropy.tif --mask-raster analysis/mask.tif --output-stack analysis/features.tif --metadata-csv analysis/bands.csv
seabed-sidescan classify --feature-stack analysis/features.tif --mask-raster analysis/mask.tif --output-dir analysis/classification --classes 4
```

Existing project commands such as `seabed-sidescan mask --project survey` remain available. Set `--project-root` or `SSS_PROJECT_ROOT` to control their working directory. An installed wheel defaults to `./SSS_processing/projects`; an editable checkout keeps the original neighboring survey layout.

## QGIS

The plugin adds a Seabed Sidescan provider to the Processing Toolbox. Its forms support file/layer selection, processing parameters, and output destinations. They also support QGIS batch processing and models.

On 64-bit Windows, open **Raster > Seabed Sidescan > Set up processing tools** and click **Install tools**. Guided setup downloads Python and the processing dependencies into a private environment, installs the included source packages, and checks them before selection. It prepares raw-sonar conversion too when that option is selected. Advanced settings retain support for an existing Python environment. See [QGIS installation and use](docs/qgis_plugin.md) for setup and validation scope.

The engine runs in a separate process so the processing stack stays separate from QGIS's Python and native libraries. Internet access is needed during setup; processing uses local files after installation.

## Raw sonar conversion

The reusable package starts with georeferenced GeoTIFF strips or mosaics. The optional `process` command invokes the reviewed [SidescanTools](https://github.com/sonoware/sidescantools) CLI for XTF/JSF conversion. That backend needs Python 3.12 or later and GMT/geospatial dependencies. The Python wheel keeps it optional; the QGIS plugin includes its licensed CLI source and provisions dependencies through guided Windows setup. No compiled dependencies or survey data are bundled in the plugin. Raw JSF support remains experimental pending representative-file validation.

The QGIS raw-sonar form uses the backend selected by setup automatically. Manual backend paths remain optional advanced overrides. Python callers can configure an independently provisioned backend through `seabed_sidescan.api.process_sonar`.

Version 0.1.0 focuses on XTF raw conversion, experimental JSF envelope conversion,
and georeferenced GeoTIFF analysis. XTF channel indices must identify port then
starboard; unsupported selections fail rather than being reinterpreted. JSF is
limited to matched port/starboard envelope pings from the first detected
subsystem. See [supported formats and limits](docs/formats.md). Additional raw
format readers are outside this release's scope.

```console
seabed-sidescan process --project survey --input /path/to/xtf --project-root /path/to/projects --sidescantools-repo /path/to/patched/sidescantools --sidescantools-python /path/to/backend/python --channel-pair 0,1 --dry-run
```

Repository-specific Windows setup and survey notes are preserved in [the original workflow](docs/legacy_windows_workflow.md) and [the command reference](docs/command_reference.md).

## Scientific scope

Classes represent acoustic facies or texture clusters. They do not establish sediment types without independent ground truth. Mosaics are corrected relative acoustic intensity, rather than calibrated absolute backscatter. Classification area reports require a projected CRS with metre units. Reported areas are planar grid areas; use an appropriate local or equal-area projection when area totals matter. Class IDs describe one fitted model and should not be transferred automatically between runs.

Texture and mosaic processing still use whole-raster arrays in several stages. Check memory on representative data before running a large survey. Strip feathering and trimming follow the valid-data footprint using pixel dimensions in CRS units; use an appropriate projected grid for physical distance interpretation. The thickness estimate is approximate for varying-width strips, and holes count as edges. Raw XTF conversion has been checked on one real four-channel file using both channel pairs. JSF remains experimental. Independent survey control is needed to establish absolute positioning accuracy for a particular survey.

Entropy is local Shannon entropy of quantized intensity. GLCM pairs require both pixels to be valid and inside the focal window. Contrast, homogeneity and ASM are averaged across directions with valid pairs; energy is the square root of that mean ASM. Independent brute-force and scikit-image comparisons cover these definitions. Version 0.1.0 includes numerical corrections from the unpublished development builds; regenerate older analytical products before comparing or interpreting them.

## Development and distribution

```console
python -m pip install -e ".[dev]"
python -m pytest
python tools/build_setup_resources.py
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
python tools/build_qgis_plugin.py --development
```

See [the quality review](docs/quality_review.md) for current findings and evidence, [the initial audit](docs/distribution_audit.md) for the original baseline, and [the release guide](docs/releasing.md) for artifact checks and the remaining publication steps. `--development` marks the plugin archive as local evaluation material when public-release metadata is incomplete.
