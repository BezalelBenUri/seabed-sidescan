# Quality review: first public-release candidate 0.1.0

Reviewed on 19 October 2026. The package and QGIS plugin provide side-scan
processing and acoustic characterization, with numerical reference checks, safer
output handling, and tested local installation paths. Publication awaits verified
public metadata and completion of the software checks below. Independent survey
positioning control and field sediment observations are outside the scope of
release 0.1.0 and are documented as limits on interpretation.

The project's own code uses **GPL-3.0-or-later**. Third-party licenses remain
unchanged. The corrected engine was initially checked under the local development
version 0.7.0 and was renumbered to **0.1.0** for its first public release.
The historical results below retain their original version and evidence. Version
0.1.0 uses the same corrected engine, with version and installation checks
repeated for the new artifacts. Nothing was published to PyPI or the QGIS plugin
directory during this review.

## Corrections included

- **Texture calculations:** GLCM features use valid pixel pairs within the
  declared footprint. Invalid neighbours are excluded, supported offsets and
  quantization settings are checked, and stable variance calculations avoid
  cancellation errors. Independent reference calculations test the results.
- **Mosaics:** union extents preserve the reference raster's pixel-grid origin.
  Edge trimming and feathering follow the valid-data footprint, including holes,
  and account for pixel dimensions in CRS units. Overlap counts use a wider integer
  type. Products are staged before replacing previous outputs.
- **Classification and evaluation:** a bounded two-pass sampler avoids reading
  the full feature stack merely to select training pixels. Chunked distance
  calculations avoid oversized prediction arrays. Inputs must have consistent
  bands, valid binary masks, matching grids, and enough distinct observations
  for the requested clusters. Cleanup requires a strict majority and preserves
  the existing class when there is no majority, avoiding a preference for small
  numeric labels.
- **File safety:** explicit and inferred output paths are checked against inputs,
  duplicate destinations, shapefile companions, and filesystem aliases including
  hard links. Writers stage files before replacement. Polygon clipping preserves
  valid integer zero values through an internal validity mask. Atomic replacement
  protects individual files; a multi-file operation is not one transaction, so
  interruption can still leave a mixture of completed and incomplete products.
- **Raw conversion:** the wrapper and patched backend report the outputs of the
  current run through manifests. The wrapper validates the resulting rasters and
  fails when the backend exits without the required products. Channel selection,
  configured output resolution, invalid navigation, and backend failures have
  focused regression coverage. The Python wheel keeps SidescanTools and GMT
  optional. The QGIS ZIP includes the licensed raw CLI source; guided setup
  provisions its native dependencies separately.
- **Dependency compatibility:** the engine declares `affine>=2.4,<3` to keep
  Rasterio's older supported Python 3.10 stack compatible with strict warning
  checks. Revisit this constraint when updating the supported Rasterio range.
- **QGIS:** operations verify the matching engine version and consume its output
  manifest. Old or unrelated TIFFs in the destination folder are excluded from
  results. Missing outputs, conflicting paths, and non-GeoTIFF raster destinations
  are rejected. Saving an engine verifies it asynchronously. Managed updates
  install into a separate environment and select it only after verification.
  Cancellation stops nested Windows processes, including installer children;
  closing the setup dialog remains responsive during cancellation.
- **Guided setup:** Windows 64-bit users can install Python and dependencies
  without choosing an existing interpreter or downloading an engine wheel.
  Bootstrap downloads require an exact size and SHA-256 match. Bundled source
  archives are hash-checked and extracted with traversal, alias and link checks.
  Setup uses a separate prefix, keeps previous settings until verification,
  prevents concurrent installation in the same folder, and isolates GMT's user
  directory from the user's existing configuration.

These changes can alter numerical results from earlier versions. Recompute
affected analytical products with the corrected 0.1.0 engine and retain the
version, parameters, configuration, and logs with the results. Existing survey products were not
rewritten as part of this review; real-data checks used separate audit output
directories.

## Historical verification record: 0.7.0 development build

| Surface | Verified result | Boundary of the result |
| --- | --- | --- |
| Windows core, Python 3.13 | **135 passed**, 1 POSIX-only skip, with warnings treated as errors | Includes overlapping API, CLI, scientific reference, raw-adapter and file-safety suites; subset counts must not be added together. |
| Windows core, Python 3.10.11 | **135 passed**, 1 POSIX-only skip, with warnings treated as errors | Fresh environment with the built wheel and separately downloaded, hash-verified dependencies; Rasterio 1.4.4, Affine 2.4.0, NumPy 2.2.6, SciPy 1.15.3, scikit-image 0.25.2 and scikit-learn 1.7.2. |
| QGIS 3.40.1 on Windows | **16/16 passed** using the installed 0.7.0 wheel | Covers all eight raster operations, synthetic raw-adapter behaviour, output manifests, engine-version failures, cancellation, setup and plugin registration. |
| QGIS managed installer | Real local-wheel installation, verified import location, responsive GUI, and preservation of the previous engine passed | Numerical dependencies were reused from a prepared environment. This does not test a fresh download of dependencies from the internet. Installation and settings writes used temporary directories and INI settings. |
| Real XTF | One 229,577,728-byte file containing 5,164 pings was processed with channel selections `0,1` and `2,3`; a further run exercised the complete package CLI and manifests | The latest CLI `0,1` and backend `2,3` checks produced finite valid pixels in EPSG:32632 at exactly 2 m resolution. These are file and workflow checks, not independent positioning calibration. |
| Linux core, Python 3.12 | **135 passed**, 1 Windows-only skip, with warnings treated as errors; POSIX nested-process cancellation passed | QGIS on Linux is a separate validation task. |
| Final wheel, source archive and plugin ZIP | Built locally; strict metadata, license, archive-content, source-rebuild and installed-wheel verification passed | Rebuilding and inspecting local artifacts does not publish them. |

## Initial confirmation record: 0.1.0 before guided setup

Version-specific checks were repeated after renumbering. These results confirm
the new artifacts independently of the historical 0.7.0 installation records.

| Surface | Status | Evidence |
| --- | --- | --- |
| Windows core, Python 3.13 | **135 passed**, 1 POSIX-only skip; warnings treated as errors | [Test log](../logs/windows_tests_010.log) |
| Linux core, Python 3.12 | **135 passed**, 1 Windows-only skip; warnings treated as errors | [Test log](../logs/linux_tests_010.log) |
| Windows core, Python 3.10.11 | **135 passed**, 1 POSIX-only skip; installed wheel, warnings treated as errors and `pip check` passed | [Verification](../logs/quality_py310_010_verification.json) |
| QGIS 3.40.1 on Windows with the installed wheel | **16/16 passed**; import location and all 17 installed package files verified | [Test log](../logs/quality_qgis_final_010.log) |
| Windows distribution and installed-wheel checks | **Passed**: archives, licenses, strict metadata, source rebuild and installed-wheel checks | [Verification log](../logs/distribution_verification_010.log) |
| Linux distribution and installed-wheel checks | **Passed**: archives, licenses, source rebuild and installed-wheel checks | [Verification log](../logs/linux_distribution_verification_010.log) |

A [comparison of both wheels](../logs/version_010_code_equivalence.json)
confirmed that all 17 package files match the audited 0.7.0 engine except for
the version literal in `__init__.py`. The previous real-data and numerical
evidence therefore concerns the same processing implementation. The 0.1.0
checks reuse the verified scientific dependencies; the later guided-setup
checks below independently exercise fresh dependency installation.

## Guided setup verification: 0.1.0

The updated candidate adds guided setup without changing the audited numerical
engine. Tests used temporary settings and installation directories; the user's
QGIS profile was not selected or overwritten.

| Surface | Verified result | Evidence |
| --- | --- | --- |
| Windows core, Python 3.13 | **182 passed**, 2 platform/privilege skips; warnings treated as errors | [Test log](../logs/guided_core_tests_windows.log) |
| Linux core, Python 3.12 | **183 passed**, 1 Windows-only skip; warnings treated as errors | [Test log](../logs/guided_core_tests_linux.log) |
| QGIS 3.40.1 on Windows | **30/30 passed**, including installer failure, cancellation, settings preservation and registration checks | [Test log](../logs/quality_guided_qgis_full.log) |
| Full guided online installation | **Passed in 206.234 seconds** into a new environment, including raw-conversion dependencies; no existing Python or prepared scientific dependency folder supplied to setup | [Verification](../logs/guided_online_verification.json) |
| Raster-only guided installation | **Passed in 50.64 seconds** into a new environment using the managed download cache; previous raw settings retained; all eight raster operations passed afterward | [Verification](../logs/guided_core_online_verification.json) |
| Real XTF workflow after setup | **All nine provider operations passed in 115.922 seconds** using restored settings and no manual backend paths | [Verification](../logs/guided_offline_verification.json) |

The final real-data run processed one 229,577,728-byte XTF through conversion,
mosaicking, masking, textures, stacking, evaluation, classification, cleanup and
polygon clipping. It produced 21 finite, nonempty georeferenced rasters in
EPSG:32632 at exactly 2 m resolution, with 37,489 classified pixels across three
classes. Source hash, size and modification time and saved settings were
unchanged. Eleven workers used the managed Python environment and its private
GMT directory. These output counts describe this run and its parameters.

The offline test denied Python socket connections, set closed HTTP/HTTPS
proxies and disabled PROJ network access. Each worker confirmed that its network
probe was denied, and no additional Python connection attempts were recorded.
This is a Python connection guard rather than operating-system firewall
isolation of arbitrary native code. It verifies that this workflow completed
under those restrictions; it does not prove every future format or dependency
will avoid network access.

Windows skips cover POSIX cancellation and directory symlinks unavailable
without the required OS privilege; Linux executes the symlink cases and skips
the Windows-only PowerShell patch test. Additional setup tests cover malformed
and conflicting archive entries, damaged downloads, verification failures,
logging failures, concurrent setup and cancellation. The visual check confirmed
that the main install button is visible with advanced settings collapsed.

The plugin bundles source archives and environment specifications, not Python,
GMT or other native binaries. A pinned, hash-checked micromamba executable
bootstraps a conda-forge environment when the user clicks **Install tools**.
Environment resolution uses version constraints rather than a complete platform
lockfile; later dependency updates can resolve differently and require renewed
verification. Current fresh-install evidence is Windows 64-bit with QGIS
3.40.1. Proxy configurations and other QGIS platforms remain unverified.

Artifact digests and final installed-wheel and QGIS verification references are
recorded in the [final artifact record](../logs/guided_final_artifacts.json).

## Format guards and publication preparation: 20 October 2026

Release 0.1.0 covers XTF raw input, experimental JSF and georeferenced GeoTIFF
analysis. No additional raw reader was added. Narrow checks now reject
XTF selections whose channel metadata does not map to port then starboard, or
whose ping channel mapping changes. JSF rejects unfinished sample encodings and
requires matching, strictly increasing port/starboard ping identifiers with
compatible finite samples. Shared gaps in otherwise matched ping sequences are
allowed. Existing envelope scaling and accepted XTF numerical processing remain
unchanged. The separate backend patch materializer also copies the JSF reader.

| Check | Observed result | Evidence |
| --- | --- | --- |
| New regressions against the previous implementation | 27 failures reproduced; 21 cases already passed | [Before log](../logs/raw_format_guards_before.log) |
| Focused raw backend suite after the guards | **48 passed**, warnings treated as errors | [After log](../logs/raw_format_guards_after.log) |
| Windows core, Python 3.13 | **212 passed**, 2 expected platform/privilege skips; warnings treated as errors | [Test log](../logs/release_core_tests_windows.log) |
| Linux core, Python 3.12 | **213 passed**, 1 Windows-only skip; warnings treated as errors | [Test log](../logs/release_core_tests_linux.log) |
| Real XTF header and complete decoding | Both pairs accepted across all 5,164 pings; `0,1` gives 2,084 samples/channel and `2,3` gives 3,126; source unchanged | [Header](../logs/raw_format_real_header_20261020.json), [decode](../logs/raw_format_real_decode_20261020.json) |

The [final release-candidate record](../logs/release_final_artifacts.json) records
the resulting artifact hashes and subsequent installed-wheel, distribution and
QGIS workflow checks. Earlier artifacts remain under
`dist/archive/0.1.0-before-format-guards-20261020`; the version is still unpublished
0.1.0. Synthetic JSF fixtures establish the rejection and alignment checks,
rather than representative real-file processing. See [formats.md](formats.md)
for the supported subset and [releasing.md](releasing.md) for the planned public
repository and manual publication workflow. Account setup and index rehearsal
are external publication steps; local checks do not establish their completion.

The documentation refresh on 20 October 2026 updated release instructions and
repository links without changing executable source. Its rebuilt distributions,
source comparisons and installation checks are recorded in the
[distribution refresh record](../logs/docs_cleanup_artifacts.json). The previous
tested distributions are retained under
`dist/archive/0.1.0-before-docs-cleanup-20261020`.

The following descriptions and local evidence record the initial 0.7.0 review.

Ruff static analysis passes for maintained source, tests, QGIS code and tools.
Source-rebuilt wheels are compared against the original wheel for package code,
resources, license material, dependency metadata, and entry points. Generated
metadata is compared after normalizing Windows/POSIX line endings; package code,
resources, and legal files must match byte for byte.

Cleanup limits each small-patch neighbourhood to its bounding box plus a
one-cell halo, with 20 independent reference cases. A local 300-by-300 benchmark
with 900 islands improved from 1.029 seconds to 0.057 seconds. This is an
algorithm microbenchmark rather than a full-survey performance measurement.

The downstream workflow also passed on the newly generated real survey strips:
mosaicking, mask creation, eight textures, feature stacking, evaluation of
2/3/4 clusters, three-class classification, and cleanup. The output grid is 785
by 65 pixels at 2 m in EPSG:32632, with 37,501 classified pixels. These checks
establish the processing path rather than independent sediment or positioning
accuracy.

The Ubuntu tests exposed and verified a fix for a POSIX cancellation deadlock
caused by waiting for a child inside an interrupted process wait. Windows
process-tree cancellation is separately covered by the QGIS suite. Ubuntu
scientific dependencies were installed from package indexes. Artifact smoke
tests reuse those installed dependencies while verifying that the project
imports from its installed wheel. These historical tests did not exercise fresh
online QGIS setup; that check is recorded in the later guided-setup results.

The fresh Python 3.10 installation first exposed a Rasterio 1.4.4/Affine 3.0.1
combination that dependency resolution accepted but that failed strict warning
checks. Affine's [upstream change log](https://raw.githubusercontent.com/rasterio/affine/main/CHANGES.txt)
documents the new multiplication deprecation. The declared Affine constraint
selects the verified 2.4 API instead. This case demonstrates why dependency
resolution and `pip check` alone are insufficient installation tests.

The plugin minimum is **QGIS 3.40.1**. That version was actually tested. The local
QGIS 3.34 directory contains installation remnants rather than a runnable QGIS
environment. Other QGIS 3.x releases, QGIS on Linux/macOS, and QGIS 4 have not been
validated by these checks. The current plugin excludes QGIS 4 in its metadata.

The real XTF checks took approximately two minutes for the `0,1` conversion and
two minutes fifty seconds for `2,3` on this machine. These single-file timings
are observations rather than a full-survey performance benchmark. The source
file's SHA-256, size, and modification time were unchanged after the checks.

Local evidence:

- [Complete CLI verification](../logs/quality_cli_raw/attempt_zrebmypj/verification.json),
  [current-run output manifest](../logs/quality_cli_raw/attempt_zrebmypj/outputs.json),
  and [processing log](../logs/quality_cli_raw/attempt_zrebmypj/run.log).
- [Channel `2,3` verification and source-integrity record](../logs/raw_audit_pair23_20261019_bqkjjaf2/verification.json).
- [Core regression and reference suites](../tests/) and
  [QGIS integration suite](../qgis_plugin/seabed_sidescan_qgis/tests/test_qgis_smoke.py).
- [Real-data downstream workflow verification](../logs/real_pipeline_070/verification.json).
- [Windows test log](../logs/windows_tests.log),
  [Linux test log](../logs/linux_tests.log), and
  [final-wheel QGIS test log](../logs/quality_qgis_final_070.log).
- [Python 3.10 verification](../logs/quality_py310_verification.json) and
  [strict Python 3.10 test log](../logs/quality_py310_pytest.log).
- [Windows distribution checks](../logs/distribution_verification.log) and
  [Linux distribution checks](../logs/linux_distribution_verification.log).

The audit logs and their generated sonar products are local evidence. They do
not belong in the distributable wheel or plugin archive.

## Remaining software and publication checks

1. **Create the public repository and configure publication accounts.** Maintainer
   contact `diamondinyang@gmail.com` and GitHub handle `BezalelBenUri` are
   configured. Package/plugin metadata point to the planned
   `BezalelBenUri/seabed-sidescan` repository, which still needs to be created.
   Verify the public documentation and issue links, configure PyPI/TestPyPI
   Trusted Publishers and GitHub environments, and complete the OSGeo submission
   setup. A local public ZIP build does not verify external account ownership.
2. **Maintain software regression coverage.** The matching 0.1.0 package and
   plugin were rebuilt and checked as recorded above. Retain that evidence.
   Keep numerical reference tests for georeferencing, channel orientation,
   resolution, CRS handling, texture calculations, and output validation. Survey
   input limitations do not excuse incorrect coordinate calculations, incorrect
   CRS declarations, or a success result with missing or invalid products.
3. **Measure and document the supported workload.** Classification sampling is
   bounded, but union mosaics and texture processing still hold substantial arrays
   in memory.
   Measure runtime, peak memory, storage requirements, and cancellation using
   available survey data or a reproducible synthetic workload. State the tested
   dimensions and limits before advertising support for larger workloads. This
   software benchmark does not require new field observations.
4. **Extend installation and platform coverage as needed.** Fresh online Windows
   guided setup and the real-XTF workflow now pass without a prepared environment.
   Run the remaining CI matrix combinations for advertised Python/platform
   support. Validate macOS, QGIS on Linux, and additional Python/QGIS versions
   before advertising them; support can remain limited to verified combinations.
   The advanced, separately provisioned raw-backend instructions still need an
   independent fresh-install check. Keep raw JSF support explicitly experimental until representative
   files have exercised its parser and processing path; real XTF checks establish
   only the layouts and channels actually tested.

## Scientific scope and input quality

Release 0.1.0 covers side-scan processing and acoustic characterization. The
software must correctly apply its documented coordinate transformations, channel
and navigation conventions, output resolution, CRS handling, and valid-data
rules. Known-answer numerical tests and processing checks on available files can
verify that behavior without independent field positioning control.

Absolute survey accuracy also depends on the navigation, timing, installation
offsets, and corrections supplied with the survey. Independent positioning
control is needed to establish that accuracy for a particular dataset. It is a
limit on survey interpretation rather than a requirement to collect new control
data before this software release.

Acoustic facies are unsupervised intensity and texture clusters. Field sediment
samples or other independent observations are needed before assigning sediment
type or assessing sediment-classification accuracy. Such interpretation is
outside release 0.1.0's scope. Users can process and characterize their acoustic
data without supplying sediment ground truth.

The build and release procedure is documented in [releasing.md](releasing.md).
The checks above define the remaining software release work. The scientific
boundaries describe how users should interpret their results.
