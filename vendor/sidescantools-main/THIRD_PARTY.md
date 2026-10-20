# SidescanTools provenance and local modifications

SidescanTools is an upstream project by GEOMAR and sonoware, funded by the
AI Fund of the State of Schleswig-Holstein. Logo design and artwork: Aili Xue.
Upstream: https://github.com/sonoware/sidescantools
The original GPLv3 text is preserved unchanged in LICENSE. Upstream attribution
and metadata are retained. This local copy is not an official upstream release.

Original vendoring commit: unknown. Comparison reference used in the distribution
audit: f4d43bf27e7413e4490a0fb57300dc60d4694805 (18 February 2026).
That comparison reference does not prove the original source commit.

Local modifications recorded on 2026-10-19:

- src/sidescantools/__init__.py: allow CLI use without optional GUI dependencies.
- src/sidescantools/xtf_wrapper.py: explicitly select two XTF channels; reject
  invalid pairs, projected navigation units, missing/invalid pings and decode
  failures instead of silently substituting channels or fabricating samples.
  Preserve chronological sample/metadata alignment; use recorded slant range.
- src/sidescantools/sidescan_file.py: read metadata from the selected channel
  headers and fail if a requested header is absent.
- src/sidescantools/georef_thread.py: propagate failures and insufficient-ping
  errors; import rioxarray explicitly; validate navigation/sonar values; handle
  southern UTM hemispheres and reject cross-zone lines; convert degree-valued
  beam angles before cosine; retain positive across-track ground distance;
  preserve original ping positions when interpolating repeated navigation fixes,
  rotate ship-forward/starboard offsets and layback in the COG coordinate frame;
  return the generated GeoTIFF path; remove only the intermediate owned by this
  channel, use the specified metric UTM resolution, and label fractional
  resolutions accurately.
- src/sidescantools/main_cli.py: write previews to the configured working
  directory, discover case-insensitive supported extensions, reject empty inputs
  and colliding stems, honor disabled gain/dB settings and configured offsets,
  preserve unrelated XYZ/XML files, and optionally write an atomic per-input
  success manifest to SIDESCANTOOLS_RUN_MANIFEST. Manifest output `channel`
  identifies logical port/starboard 0/1; `input_channel` records the selected
  physical XTF channel index (or JSF 0/1).
- environment_cli.yml: declare directly imported Pillow dependency explicitly.

Additional local modifications recorded on 2026-10-20:

- src/sidescantools/xtf_wrapper.py: validate selected port/starboard roles against
  channel metadata and ping channel identifiers; reject reversed, same-side or
  ambiguous selections before processing.
- src/sidescantools/jsf.py: reject unfinished complex/raw and unknown sample
  formats explicitly; preserve the existing format-0 envelope conversion.
- src/sidescantools/sidescan_file.py: require compatible, matching port/starboard
  ping identifiers and sample dimensions instead of combining mismatched rows.
- scripts/patch_sidescantools_klein_cli.ps1 in the parent project now also copies
  the reviewed jsf.py reader when materializing the CLI patch.

scripts/patch_sidescantools_klein_cli.ps1 materializes these reviewed source files
and this notice into a separate 1.0.0 checkout, with unchanged-license and version
checks. Repeated application is idempotent. The checked-in vendor copy is the
canonical patch source; review changes before updating that snapshot.

Scientific limitations: these fixes are not survey certification. The backend
uses empirical navigation smoothing, interpolation, nominal beam geometry and
layback assumptions. Validate absolute position, channel orientation, ground
range and intensity behavior against independently surveyed reference/control
before quantitative use. JSF processing still needs representative real-data
validation. Do not redistribute private survey input or generated survey output
without the data owner's permission.
