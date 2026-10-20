# Supported formats for 0.1.0

The Python API, command line and QGIS plugin share the same processing engine.
Release 0.1.0 concentrates on XTF, experimental JSF and georeferenced GeoTIFF.
Additional raw-format readers are outside this release's scope.

| Input | Processing path | Validation and limits |
| --- | --- | --- |
| XTF (`.xtf`, case-insensitive) | Optional reviewed raw backend, then GeoTIFF analysis | One real four-channel recording has been checked using pairs `0,1` and `2,3`. This is not a claim that every manufacturer-specific XTF variant is supported. |
| JSF (`.jsf`, case-insensitive) | Experimental reviewed raw backend | Envelope sample format 0 only, with channels 0/1 and matching ping identifiers and sample dimensions. Representative real-JSF workflow validation is still required. |
| Georeferenced GeoTIFF (`.tif`, `.tiff`) | Mosaic, mask, clipping, textures, feature stacking, evaluation, classification and cleanup | Supply an appropriate CRS, pixel grid, valid-data mask/NoData and intensity raster. Feature inputs must have compatible grids; projected metre coordinates are required for metric area reports. |

## Raw conversion contract

XTF channel indices are ordered **port, starboard**. The backend checks the roles
recorded in channel metadata rather than inferring them from even/odd indices.
Reversed, same-side, ambiguous or missing channel metadata is rejected. Navigation
must use geographic degrees (`NavUnits=3`). Selected channels must contain valid,
compatible ping/sample arrays. The raw channel-pair option does not select JSF
subsystems.

JSF currently selects the first detected subsystem. The public CLI and QGIS form
do not expose a subsystem selector. Coordinate units must be geographic minutes
of arc (`coord_units=2`). Complex samples (formats 1/9), unmatched raw samples
(format 2), proprietary sample encodings and mismatched port/starboard ping
sequences are rejected. Envelope handling has synthetic regression coverage;
that does not establish real-file compatibility. JSF remains experimental.

Raw georeferencing requires more than 300 valid navigation pings, enough distinct
fixes for interpolation, valid altitude for the configured preprocessing, and a
line within one supported UTM zone and hemisphere. Missing prerequisites should
produce an error rather than an apparently successful output. These constraints
belong to the current backend, rather than to the file formats themselves.

Data exported from other sonar software can enter the raster workflow as a
suitable georeferenced GeoTIFF. Decoding that software's original raw format is
outside this release's advertised coverage.

## Format references

- [Exail XTF specification, revision 42](https://www.exail.com/media-file/9742/xtf-file-format-specification-rev42.pdf).
- [EdgeTech JSF file and message descriptions, revision R](https://www.edgetech.com/wp-content/uploads/2023/04/0023492_Rev_R.pdf).
- [OGC GeoTIFF standard](https://www.ogc.org/standards/geotiff/).

See the [quality review](quality_review.md) for actual test evidence and the
[release procedure](releasing.md) for package and plugin publication.
