# QGIS Plugin

Seabed Sidescan adds eight raster analysis tools to the Processing Toolbox: strip mosaics, valid-data masks, raster clipping, texture extraction, feature stacking, cluster-count evaluation, acoustic facies classification, and classification cleanup. A ninth tool converts raw sonar through the reviewed SidescanTools CLI backend. XTF has real-file checks; JSF remains experimental.

For QGIS, use the plugin ZIP. The files in `dist` serve different users:

- The `.whl` file, called a **wheel**, installs the Python analysis package for programmers and researchers using Python.
- The plugin `.zip` installs the QGIS buttons, forms, and guided setup. It includes the engine and reviewed raw-backend source needed by that setup. QGIS users do not need to select a separate wheel, Python installation, or backend checkout. **Development** means this is a local test build, before publication in the QGIS plugin directory.

Build the archives locally using [the release guide](releasing.md); generated
files in `dist` are not included in a fresh source checkout. QGIS users need only
the plugin ZIP. Leave it compressed and select it directly in QGIS's **Install
from ZIP** dialog.

## Install locally

1. Build the development plugin ZIP using [the release guide](releasing.md), or use a ZIP already built locally in `dist`.
2. In QGIS, select **Plugins > Manage and Install Plugins > Install from ZIP** and choose `seabed_sidescan_qgis-0.1.0-development.zip`. Enable Seabed Sidescan. This ZIP is for local evaluation and is not the archive submitted to the QGIS directory. Maintainer metadata is configured and the source is public; directory publication remains a separate step. The project's own code is licensed under GPL-3.0-or-later.
3. On 64-bit Windows, open **Raster > Seabed Sidescan > Set up processing tools** and click **Install tools**. Keep **Include raw-sonar conversion** selected to process XTF, or clear it if you only need the eight raster tools. Keep an internet connection during setup. The installer downloads Python and the selected processing dependencies, then installs the included source in a separate environment. A separate Python installation or manual backend setup is not required.
4. Wait for setup and its checks to finish. Setup selects the new tools only after verification and keeps the previous working environment available if an update fails. Installation logs are visible in the setup dialog. Guided automatic setup currently targets 64-bit Windows; existing-engine and manual configuration remain available under the advanced options for other installations.
5. Open **Raster > Seabed Sidescan > Seabed Sidescan tools**, or search for Seabed Sidescan in the Processing Toolbox.

The plugin uses QGIS's standard parameter forms. Select existing raster layers or files, choose the output paths, then run. Raster outputs are made available to QGIS, and folder-producing steps report their output products. Keep related analytical products together for reproducibility. Each algorithm's help describes its inputs.

For raw sonar conversion, select the input survey folder, project name/output folder, XTF channel indices in port/starboard order, and resolution. Guided setup supplies the backend and interpreter paths; manual overrides are advanced options. An optional custom YAML template can override the supplied processing defaults. Check the resulting strips and logs before mosaicking. Real XTF checks cover one survey file with both channel pairs; other layouts and JSF need their own validation. Experimental JSF accepts envelope data from the first detected subsystem with matching port/starboard pings; the XTF channel-pair field does not select a JSF subsystem. See [format scope](formats.md).

For polygon masks and clipping, select a polygon layer. The plugin exports it to a temporary shapefile for the engine, preserving the declared CRS. Core API/CLI callers currently provide shapefiles directly. Analysis masks and feature bands must match their source grid; these operations reject mismatches. Mosaicking separately places strips on the reference input grid and uses nearest-neighbour resampling when alignment differs.

## Engine separation

The plugin imports QGIS and standard Python libraries. Python 3.12, NumPy, Rasterio, SciPy, scikit-image, scikit-learn, pyshp and PyYAML live in the external engine environment. Selecting raw conversion also installs GMT, GDAL and the raw-backend dependencies. QGIS-specific Python/Qt/GDAL environment settings are removed before the engine starts. The QGIS ZIP carries source archives under `resources/setup`; it contains no runtime binaries or installed environment.

Setup starts only when you click **Install tools**. It downloads a pinned, checksum-verified micromamba executable and creates an isolated environment from conda-forge packages in the installation folder selected in the dialog. It then installs the included source archives. It does not install scientific packages into QGIS's Python or require the package to have been published on PyPI. You can also use an existing compatible environment through the advanced options.

After setup, processing uses the installed tools and local input files. A fresh online installation and a subsequent guarded offline workflow passed on 64-bit Windows with QGIS 3.40.1. The offline check rejected Python network connections, used closed proxies and disabled PROJ network access; native networking outside that guard was outside the test boundary. Consult [the quality review](quality_review.md) for the full evidence.

Processing runs through a worker process, streams logs into Processing feedback, and responds to cancellation by stopping the engine. A canceled run can leave partial output files. Select fresh output destinations when preserving prior results. The engine and plugin versions should match; update them together.

## Validation scope

The plugin requires QGIS 3.40.1 or later within QGIS 3.x. Windows QGIS 3.40.1 is the tested runtime; other QGIS versions and operating systems need their own validation. QGIS 4 and Qt6 are outside the current compatibility range.

Guided setup and processing passed these additional checks on 64-bit Windows with QGIS 3.40.1. Evidence paths identify maintainer-local records, excluded from the public repository; they are not downloads. Public automated test and distribution results are available in [GitHub Actions](https://github.com/BezalelBenUri/seabed-sidescan/actions/workflows/ci.yml).

| Check | Observed result | Evidence |
| --- | --- | --- |
| Full online setup including raw conversion | 206.234 seconds, with a new bootstrap and no supplied Python installation | Online setup record (local: `logs/guided_online_verification.json`) |
| New raster-only environment | 50.640 seconds using cached dependency packages; all eight raster operations then passed in 9.076 seconds | Raster-only setup and processing record (local: `logs/guided_core_online_verification.json`) |
| Cold-start workflow using saved setup settings | All nine provider operations passed with a real XTF input in 115.922 seconds, with no backend path overrides and the input unchanged | Guarded offline workflow record (local: `logs/guided_offline_verification.json`) |

The final workflow used a private GMT directory, a Python connection guard and closed proxies; it did not use an operating-system firewall. Timings describe these runs on this machine. Existing synthetic checks cover provider registration, output metadata, cancellation, setup failures and installed-package isolation. Earlier real XTF tests separately cover both channel pairs on one survey file. These checks do not establish compatibility with every sonar format, large-survey performance, or sediment classification accuracy. Classes are unsupervised acoustic facies; independent ground truth is needed for sediment labels. Consult the quality review for evidence and remaining limits.

If a run fails, inspect the Processing log, check the configured tools in Set up processing tools, and verify the input CRS, grid alignment, NoData, and selected output destinations. Preserve the log and configuration when reporting a problem.
