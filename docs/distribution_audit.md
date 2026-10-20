# Distribution Audit

This is the historical unpublished version 0.6.0 baseline. Several findings below were subsequently fixed in the unpublished 0.7.0 audit build. Those corrections are included in the first public-release candidate, 0.1.0. See [the current quality review](quality_review.md) for the latest implementation, real-data evidence, validation results, and remaining limitations.

Audit date: 19 October 2026.

The code can support a Python package and a QGIS plugin built around the same processing engine. The raster processing code under `src/seabed_sidescan` is the reusable core. Raw XTF/JSF processing uses a separate, locally modified copy of SidescanTools with a larger software environment.

This report records the initial repository findings, the accompanying implementation and validation, and the remaining release gates. The baseline findings below describe the initial code; the validation section identifies what was subsequently addressed.

## Recommended Distribution

1. Publish the reusable Python core as `seabed-sidescan`, imported as `seabed_sidescan`.
2. Make the QGIS plugin a small interface to that engine. Run the engine with a configured Python executable in a separate process. Use QGIS APIs for inputs, progress, and loading output layers.
3. Keep the SidescanTools raw-processing backend optional and explicitly configured. Identify the patched installation and its Python environment independently of the core package.
4. Build the Python wheel/source distribution and the QGIS plugin ZIP from the same release. Do not distribute survey data, processing outputs, environments, or compiled libraries in either artifact.

The separate engine process is useful because this project depends on Rasterio and other compiled libraries. Rasterio's own installation guidance says its PyPI wheels are not tested for compatibility with QGIS and other binary software stacks. Installing those wheels inside QGIS should not be the default deployment path. See the [Rasterio installation guidance](https://rasterio.readthedocs.io/en/stable/installation.html).

The plugin should use `qgis.PyQt` for its interface. It does not need the vendored SidescanTools GUI, napari, or a second Qt installation.

## Findings By Severity

Severity describes release impact. A release blocker prevents public distribution or a supported installation claim. High findings can cause processing failure, incorrect output, or loss of existing work. Medium findings concern reproducibility, scalability, or incomplete compatibility evidence.

| Severity | Initial finding and evidence | Required outcome |
| --- | --- | --- |
| Release blocker (resolved for first-party license) | The repository initially has no top-level `LICENSE` and no license field in `pyproject.toml`. The vendor license covers the vendor software; it does not select a license for the project's own source. | The owner has selected GPL-3.0-or-later for the project's own code. Include the full license and notices in both distributions; retain existing third-party licenses and verify redistribution rights for any examples added. |
| Release blocker | The QGIS directory requires a compatible open-source license, public repository/homepage/tracker links, documentation, and disclosure of external dependencies. These publication details were absent at the initial scan. | Supply real project URLs and a compatible license, document the engine installation, and verify the uploaded ZIP matches its public source. |
| High | Initial `pyproject.toml` discovers only packages under `src`. `cli.cmd_process` reads a repository-level config and executes `vendor/sidescantools-main/src/sidescantools/main_cli.py`. Those files are not part of the initial wheel. | Test an ordinary wheel install from a directory outside the checkout. Package portable defaults and provide an explicit optional raw-backend adapter. |
| High | `paths.solution_root` falls back to the current directory outside an editable checkout. Initial project and input defaults then depend on unrelated neighboring folders. | Select stable writable workspace defaults and explicit input/output paths outside the repository. |
| High | The raw backend's `Georeferencer.process` catches georeferencing exceptions and prints them without failing the job. The outer CLI can therefore report completion while GeoTIFF generation failed. | Propagate failures or verify expected output artifacts before declaring success. Test a deliberately failing backend. |
| High | The raw backend's `XTFWrapper.__post_init__` silently substitutes channels `0,1` for invalid selections. Broad exception handlers duplicate previous ping data or insert zeros. | Reject invalid selections before running; document missing-ping behavior and emit an actionable QC record. Test channels `0,1` and `2,3` independently. |
| High | Initial mosaic cleanup can remove outputs before input validation, in the mosaic entry point. | Validate inputs before removing or replacing any output. Preserve prior results when validation fails. |
| Medium | The core initially declares Python `>=3.10`; the vendored SidescanTools metadata declares `>=3.12`, while its environment pins Python 3.12. | State separate core and raw-backend compatibility. Do not imply that core Python support proves raw-backend support. |
| Medium | The upstream SidescanTools `pyproject.toml` does not declare its runtime Python dependencies. The supplied environment and requirements files carry much of that information instead. | Provision and check the optional backend environment explicitly. Installing its source package alone is insufficient. |
| Medium | Local vendor modifications are reproducible through a PowerShell patch script, but lack a recorded original upstream commit and prominent modification/date notices. | Preserve the vendor license, identify upstream and local changes, and add appropriate modification notices before redistributing a modified vendor artifact. |
| Medium | The initial repository has no automated test suite, lock file, release workflow, or genuine XTF/JSF fixture. `scripts/run_georef_test.ps1` is an operational script requiring external data. | Add meaningful core tests, wheel/plugin artifact checks, and a documented compatibility matrix; maintain separately authorized raw-data fixtures. |
| Medium | Important algorithms allocate whole-raster arrays; classifier sampling does not eliminate all earlier full-data allocation, and texture calculations can require many whole-image filters. | Document memory limits and measure realistic datasets before claiming large-survey scalability. |

The QGIS publication requirements above come from the [official plugin publication guide](https://plugins.qgis.org/docs/publish). Metadata validation alone cannot establish directory approval or working behavior in QGIS.

### Changes Made After The Initial Findings

The accompanying implementation adds an explicit-path Python API, lazy scientific imports, a module entry point, packaged portable YAML defaults, a typing marker, development dependencies, regression tests, and distribution checks. Installed-wheel operation no longer depends on reading configuration from the source checkout. Standalone CLI paths and safe project naming were corrected, including the related PowerShell project-path guard. Mosaic input validation now precedes cleanup of existing output files.

The QGIS plugin runs the shared engine in a separate Python process and provides Processing algorithms, engine settings, progress/cancellation, and output loading. Its development ZIP excludes the core engine, third-party backend, and scientific binary dependencies. The owner subsequently selected GPL-3.0-or-later for the project's own code, resolving the initial project-license blocker. A release ZIP still requires real public maintainer/repository metadata and the compatibility and survey validation described below.

The optional raw adapter now rejects a run with no new or updated GeoTIFF. It does not establish that every individual raw input was processed successfully. The vendor error handling, original source provenance, channel-specific scientific validation, and survey-scale limitations still require attention.

## License And Attribution

The vendored project identifies itself as GPLv3 software. Its metadata contains `license = "GPL-3.0"`, and its full license is preserved in `vendor/sidescantools-main/LICENSE`. The vendor README attributes the project to GEOMAR and sonoware, and the logo/artwork to Aili Xue. Preserve these attributions and avoid presenting the vendor code or artwork as original project work. The upstream is [sonoware/SidescanTools](https://github.com/sonoware/sidescantools).

If modified GPL-covered code is distributed, preserve the license and relevant notices, identify modifications and their dates, and provide the required source. A combined distribution must respect the applicable GPL terms. The [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#GPLPlugins) also distinguishes simple process invocation from tightly combined integration. An optional backend called through a subprocess does not, by itself, establish that every independent raster module must use the same license.

The project's own code, including the Python package and QGIS plugin, is licensed under GPL-3.0-or-later. This selection does not relicense the vendor code or change its existing notices. Confirm the exact upstream SPDX expression, including whether later GPL versions are permitted, rather than inferring that permission from the license document's example boilerplate.

The core wheel should depend on numerical/geospatial libraries through normal package metadata. If a later installer redistributes dependency binaries, that installer also needs the license and attribution material for the actual bundled binaries and their embedded libraries.

### Verified Local Vendor Modifications

The following local files differ from the upstream comparison reference and correspond to the four patches in `scripts/patch_sidescantools_klein_cli.ps1`:

| Vendor file | Local modification |
| --- | --- |
| `src/sidescantools/__init__.py` | Makes Qt/napari GUI imports optional for CLI use. |
| `src/sidescantools/xtf_wrapper.py` | Selects an XTF channel pair through `SIDESCANTOOLS_XTF_CHANNEL_PAIR`; changes missing-ping handling and uses the selected channel for sample metadata. |
| `src/sidescantools/sidescan_file.py` | Reads timing and slant-range metadata from selected channel indices. |
| `src/sidescantools/main_cli.py` | Writes preview PNGs to the configured working directory. |

Comparison reference retrieved from the upstream GitHub API during this audit: commit [`f4d43bf27e7413e4490a0fb57300dc60d4694805`](https://github.com/sonoware/sidescantools/commit/f4d43bf27e7413e4490a0fb57300dc60d4694805), whose recorded commit date is 18 February 2026. This is a comparison reference, not proof that this commit was the original source of the vendored copy. No original vendor commit identifier or local modification date was recorded in the initial repository. Filesystem timestamps are not an adequate substitute for that provenance.

No vendor source files were changed during this audit.

## Dependency Boundaries

| Component | Dependencies and installation considerations |
| --- | --- |
| Core raster processing | NumPy, Rasterio, SciPy, scikit-image, scikit-learn, and pyshp. These match the initial root dependency list. Core modules do not directly import SidescanTools. |
| Raw XTF/JSF processing | Patched SidescanTools, Python 3.12 under the supplied environment, pydantic, PyYAML, geopy, pyproj, utm, pyxtf, NumPy/SciPy/scikit-image, Pillow, PyGMT, rioxarray, and their dependencies. Declare direct dependencies even where the current environment obtains them transitively. |
| External raw-processing libraries | PyGMT 0.17 requires GMT 6.5 or later. GDAL/PROJ and their data/library configuration also matter for the geospatial stack. A pip requirements file is not a system-library installer. |
| QGIS interface | QGIS and its bundled Python/Qt stack, plus a separately configured compatible engine environment. The core must remain importable without QGIS installed. |

The supplied `vendor/sidescantools-main/environment_cli.yml` pins Python 3.12, NumPy 2.3.3, GDAL 3.10.3, PyGMT 0.17.0, rioxarray 0.18.1, Rasterio 1.4.3, utm 0.7.0, and pyxtf 1.4.2. These are an existing environment specification, not a demonstrated cross-platform compatibility guarantee. The initial pip requirements file omits GMT itself and explicit Pillow. Python's `osgeo.gdal` is used by setup verification; the reusable core primarily uses Rasterio.

The [PyGMT 0.17 installation guide](https://www.pygmt.org/v0.17.0/install.html) specifies Python 3.11 or later and GMT 6.5 or later and recommends an isolated environment. The stronger Python 3.12 requirement here comes from the [SidescanTools project metadata](https://github.com/sonoware/sidescantools/blob/main/pyproject.toml).

The raw georeferencer accesses the xarray `.rio` accessor without an explicit `import rioxarray` in the vendored source. It may currently work through a transitive import. Register that dependency explicitly or verify the behavior in a fresh backend environment; this is a dependency risk, not a reproduced failure in this audit.

## Reproducibility And Scientific Limits

The initial Git repository has no commit history or configured remote. The data directory contains only `.gitkeep`; raw survey files and outputs are intentionally excluded. The audit cannot infer access rights or redistribution permission for neighboring survey data from the codebase.

The default raw configuration includes machine-specific `D:/a/SSS_processing` paths. A released template should use portable defaults and separate user input, intermediate, and output directories. Each processing run should record package/backend versions, configuration, channel selection, input identifiers, CRS, resolution, random seed, and output filenames.

The documented four-channel Klein observation is specific to the surveyed input described in the project notes. It does not validate all XTF layouts, sonar manufacturers, navigation conventions, or channel orderings. Verify those claims with representative files before advertising them.

Mosaic seam trimming and feathering use raster bounding-box easting in the existing implementation. They are not demonstrated to follow actual swath edges on rotated or irregular footprints. GLCM texture work includes many whole-image operations, and the mosaic/classification pipeline can retain large arrays even when later sampling is enabled. These are scope and scalability limits requiring benchmark/QC evidence; they are not proof that all existing results are wrong.

The current GLCM implementation counts pixel pairs whose anchor falls inside the focal window, while a shifted neighbor can fall outside that window. An independent NumPy probe reproduced the difference: for a 5-by-5 image whose rows are `[0, 0, 0, 1, 1]`, the center 3-by-3 window and direction `(0, 1)` produce contrast `1/3` under the current convention, compared with `1/2` when both pixels must lie inside the focal window. Treat those GLCM products as experimental until the intended definition is documented and independently checked against local-window reference calculations. This convention has not been rewritten in the accompanying implementation.

The accompanying raw-backend adapter compares GeoTIFF size and modification time before and after execution and rejects a run with no new or updated GeoTIFF. That mitigates complete export failure being reported as success. It cannot prove that every expected strip succeeded: partial backend failures and incomplete coverage remain possible and require per-input output verification and QC.

Without independent ground-truth labels, output classes represent acoustic facies or texture clusters. Silhouette scores and related clustering diagnostics do not establish sediment identification accuracy. Preserve that distinction in package descriptions, plugin help, and research examples.

## Validation And Remaining Release Gates

The initial host shell uses Python 3.13.1 and lacked most core geospatial/scientific dependencies and the raw-processing stack. The project environment was then prepared for validation. No real raw-survey conversion, PyPI upload, or QGIS directory upload was performed.

The core Python suite passed 39 tests on Windows with Python 3.13.1: 18 CLI/path/distribution tests and 21 processing/API tests, including four optional raw-adapter cases using a fake backend or dry run. `pip check` reported no dependency conflicts in the project environment. Tested dependency versions were NumPy 2.5.4, Rasterio 1.5.2, SciPy 1.18.1, scikit-image 0.26.0, scikit-learn 1.9.1, pyshp 3.1.6, and PyYAML 6.0.3. This is one tested environment, not evidence for every version allowed by the dependency constraints.

Ten native smoke tests passed in QGIS 3.40.1. They exercised all eight raster operations and the ninth optional raw adapter (using a fake backend) through the external engine and covered polygon export/loading, temporary outputs, engine failure, cancellation, engine-setting dependency checks, headless provider registration, local Plugin Manager metadata acceptance, and Windows nested-process cancellation. POSIX cancellation remains unvalidated. This establishes working behavior in that installed QGIS runtime. It does not establish compatibility with every supported QGIS release, Qt generation, operating system, or installation method.

Distribution validation was performed on Windows with Python 3.13 using the prepared project virtual environment. A separate temporary source snapshot produced the wheel, source distribution, and development plugin ZIP. Both Python artifacts passed `twine check --strict`. `tools/verify_distributions.py` checked archive contents, rebuilt the source distribution with isolated build dependencies, and installed both original and rebuilt wheels outside the checkout. Both installs passed API/import/resource checks, a synthetic nodata-mask calculation, a raw-adapter configuration dry run, module help/version commands, and the console entry point. These smoke environments reuse already installed scientific dependencies; they prove that the project itself imports from its installed wheel rather than from the editable source tree. The resources directory is now an explicit package to avoid the setuptools namespace warning observed during the earlier snapshot build.

The GitHub workflows configure core tests on Linux and Windows with Python 3.10, 3.12, and 3.13, plus distribution checks on Linux and Windows. These configured jobs are not evidence that the remote matrix has run. The manually triggered artifact workflow retains development build outputs only and contains no publication step or publishing credentials.

Before publishing, retain the passing evidence above and complete the remaining release checks:

1. Real maintainer and repository details, verification that the selected GPL-3.0-or-later license and notices appear in the final artifacts, and complete vendor notices for any vendor source redistributed. The project-license choice is resolved.
2. Rebuild the final reviewed wheel, source distribution, and plugin ZIP, retaining the successful archive, metadata, outside-checkout installation, resource, and API/CLI checks.
3. Run the configured Linux/Windows and Python-version matrix in CI. Retain numerical/raster regression tests covering masks, nodata, CRS/grid alignment, classifier results, and failure paths, and record the versions actually tested.
4. Supply complete public metadata in the final plugin ZIP and exercise it inside every claimed QGIS version and supported Qt generation, with a separate engine interpreter. QGIS 3.40.1 has been tested locally.
5. Complete interactive UI checks for file paths with spaces, progress/cancellation, engine failures, missing dependencies, output loading, and interface responsiveness. Repeat with an installed engine wheel and no editable checkout on the engine path; native processing smoke tests do not cover every GUI interaction.
6. Separate raw-backend tests using authorized fixtures, including both Klein channel pairs, incomplete pings, invalid selections, and a deliberate GeoTIFF export failure. Confirm output CRS, pixel size, coverage, and alignment against independent reference data.
7. A representative survey benchmark recording peak memory, elapsed time, and scientific QC. Do not infer survey-scale support from small synthetic tests.

The [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) describes the metadata, dependency groups, project URLs, and license configuration used for a normal package release. A successful local build does not reserve a PyPI project name or publish a package. PyPI pages for `seabed-sidescan` and `sidescantools` returned HTTP 404 during the audit; this is not a reservation or guarantee of name availability.
