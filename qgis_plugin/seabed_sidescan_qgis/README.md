# Seabed Sidescan for QGIS (experimental)

Requires QGIS 3.40.1–3.99. Eight raster tools process **existing georeferenced
GeoTIFF strips or mosaics**. A ninth tool converts raw sonar through the reviewed
SidescanTools CLI backend. Real-file checks cover XTF; JSF remains experimental.

1. Install the release plugin ZIP through **Plugins > Manage and Install Plugins >
   Install from ZIP**, then enable **Seabed Sidescan**.
2. On 64-bit Windows, open **Raster > Seabed Sidescan > Set up processing tools**
   and click **Install tools**. Keep **Include raw-sonar conversion** selected for
   XTF, or clear it if you only need the eight raster tools. Keep an internet
   connection during setup. It downloads Python and the selected dependencies,
   including GMT for raw conversion, then installs the included source. No separate wheel,
   Python installation or backend checkout is required. The new environment is
   selected only after verification; failed updates keep the previous working
   selection. Existing environments and manual configuration remain available
   in the advanced options. Guided automatic setup currently targets 64-bit
   Windows.
3. Use the toolbar button or **Raster > Seabed Sidescan > Seabed Sidescan tools**
   and select a Processing tool. Inputs and output locations are explicit.

The raster tools include mosaicking, valid-data masking, texture extraction, feature
stacking, cluster evaluation, k-means classification, classification cleanup and
polygon clipping. The numbered operations show their usual order. Polygon
sources and selections are converted to shapefiles automatically. Raster inputs
must be local files; first export web, database or virtual rasters to GeoTIFF.
The algorithms also work in the Processing modeler and batch interface. Generated
rasters can be loaded into QGIS automatically. Only files declared by the current
successful run are returned and loaded; old or unrelated TIFFs in the output
folder are excluded. Raster destinations must use `.tif` or `.tiff`. Cancel stops
the external worker and its nested processes;
partial outputs can remain, and existing selected output files may be overwritten.

For **0. Georeference raw sonar**, choose the raw input folder, channel pair,
resolution and output root. Guided setup supplies the reviewed backend and
interpreter paths; advanced options allow manual overrides. The
survey folder name must start with a letter or number and use only letters,
numbers, periods, underscores and hyphens. Products go to
`output root / survey / georef_out`. Real XTF checks cover one survey file with
both channel pairs; other layouts and JSF need their own validation. Inspect logs
and newly produced GeoTIFFs after each run.

The scientific backend runs in a separate Python process. The plugin never
installs into QGIS Python and never imports rasterio, NumPy or scikit-learn into
QGIS. QGIS Python, Qt, GDAL and PROJ environment settings are removed from the
worker environment. Setup and installation logs remain visible in the settings
dialog; processing logs appear in the standard Processing feedback pane.

The ZIP includes engine and raw CLI source archives, their licenses and notices.
It contains no Python, micromamba, GMT or scientific-library binaries. Clicking
**Install tools** downloads a pinned, checksum-verified micromamba and creates a
separate Python 3.12 environment using conda-forge dependencies. Processing is
performed with the installed tools and local input files after setup.

Guided installation passed on 64-bit Windows with QGIS 3.40.1: full online setup
took 206.234 seconds with a new bootstrap and no supplied Python; a new raster-only
environment took 50.640 seconds using cached packages, then passed all eight
raster tools in 9.076 seconds. A cold-start workflow using the saved full setup
passed all nine tools with a real XTF input in 115.922 seconds, without backend
path overrides and with the source file unchanged. This run used a private GMT
directory, Python connection guards, closed proxies and disabled PROJ network
access. Native connections outside those guards were outside the test boundary;
no operating-system firewall was used. Timings describe these local runs. See
the repository's `docs/quality_review.md` for evidence and remaining limits.

Acoustic facies are unsupervised clusters. Validate their interpretation with
independent information; cluster labels alone do not identify sediment types.

Version 0.1.0 is an unpublished release candidate. The
project's own code is licensed under GPL-3.0-or-later; third-party licenses remain
unchanged. Maintainer metadata is configured. Publication requires a readable
public source repository and submission through an OSGeo account. Compatibility
and workload limits remain documented in `docs/quality_review.md`.

Developers can run the focused smoke suite from the repository root using QGIS's
Python: `python-qgis.bat -m unittest discover -s
qgis_plugin/seabed_sidescan_qgis/tests -v`. Set the environment variable
`SEABED_SIDESCAN_TEST_PYTHON` to the external backend interpreter to include the
synthetic end-to-end pipeline, cancellation and asynchronous setup checks. To
also verify the managed installer with a real local wheel, set
`SEABED_SIDESCAN_TEST_WHEEL` and `SEABED_SIDESCAN_TEST_DEPENDENCY_SITE` to the wheel
and a prepared standalone numerical-dependency site-packages folder. This test
uses temporary environments and INI settings and checks GUI responsiveness,
previous-engine preservation and installed-package import origin. It reuses
prepared dependencies; it does not validate online dependency downloads.
