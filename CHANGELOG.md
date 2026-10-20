# Changes

## 0.1.0 — first public-release candidate, 19 October 2026

Renumber the Python package and QGIS plugin together before their first publication. This candidate contains all corrections verified under the unpublished 0.7.0 audit build; the lower number starts the public release history rather than reverting those changes. The 0.6.0 and 0.7.0 records below describe local development builds only.

The supported purpose is side-scan processing and acoustic characterization. Independent sediment labels and survey positioning certification require external evidence and are outside this release's claims. Correct numerical processing, georeferencing logic, installation, format coverage and resource handling remain software responsibilities. No version has been published yet.

- Add guided Windows 64-bit QGIS setup: download Python and native dependencies into a private environment, install the included engine and optional raw-conversion source, and verify the installation before selecting it. No separately downloaded wheel or preinstalled Python is required.
- Use the saved raw-conversion installation automatically in the Processing form, with optional advanced path overrides. Keep existing installations selected if setup fails or is cancelled.
- Verify the bootstrap download and bundled source hashes; harden source extraction, isolate GMT configuration, and prevent concurrent installers from sharing the same setup folder.
- Validate fresh online installation, the raster-only setup option, and the complete real-XTF workflow using saved settings under Python network restrictions. Add offline installer failure-path tests and source-distribution plugin rebuild checks. See `docs/quality_review.md` for evidence and platform limits.
- Validate XTF port/starboard roles and stable ping channel mappings before georeferencing. Preserve the existing valid channel-pair processing path.
- Restrict experimental JSF conversion to the implemented envelope encoding. Reject unsupported sample types, unmatched or duplicate channel pings and incompatible sample dimensions instead of combining rows silently.
- Add focused format regressions, document XTF/JSF/GeoTIFF scope, supply maintainer contact and planned repository metadata, and prepare manual TestPyPI/PyPI Trusted Publishing. Repository creation, account configuration and submission remain separate actions.

## 0.7.0 — unpublished development quality review, 19 October 2026

This version changes scientific results. Regenerate mosaics, textures, features and classifications produced with the earlier development implementation before quantitative comparison. Existing survey inputs and existing analytical output folders are not automatically rewritten.

- Restrict GLCM pairs to valid pixels inside each focal window; define constant-image quantization and improve variance stability. Entropy remains local quantized-intensity Shannon entropy.
- Follow actual valid strip footprints for trimming and feathering, preserve native grid alignment, and use uint32 overlap counts.
- Stage texture and mosaic products before replacement. Validate path aliases and hard links; replace individual outputs atomically and remove obsolete raster sidecars.
- Sample training pixels and predict classes in bounded windows. Avoid large broadcast-distance arrays, reject degenerate class requests and nonfinite distance calculations, and preserve valid integer zeros when clipping.
- Report current-run outputs explicitly to QGIS. Verify the engine before selection and stage engine installations separately from the working environment. Improve nested-process cancellation and GUI responsiveness.
- Harden the optional raw backend's channel and ping handling, georeferencing error propagation, angular units, UTM hemisphere, offsets and pixel resolution. Record per-input channel manifests and dated vendor changes.
- Add numerical reference tests, failure-path regressions, Windows/Linux checks, QGIS installed-wheel integration tests and bounded real-XTF validation. Limits and evidence are recorded in `docs/quality_review.md`.
- Constrain Affine to the tested 2.4 API so Rasterio on Python 3.10 passes strict warning checks; reevaluate this constraint as the supported Rasterio/Python range changes.

## 0.6.0 — unpublished initial local distribution build

Established the public Python API, CLI/module entry point, portable packaged configuration, QGIS Processing interface, build tools and distribution verification. GPL-3.0-or-later was selected for first-party code. No version has been published to PyPI or the QGIS directory.
