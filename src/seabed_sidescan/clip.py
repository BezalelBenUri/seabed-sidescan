import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask as raster_mask

from .io import atomic_output, validate_paths
from .mask import read_boundary_geometries


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Clip a georeferenced raster to a polygon boundary."
    )
    parser.add_argument("--input-raster", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--output-raster", required=True, type=Path)
    parser.add_argument(
        "--boundary-crs",
        help="Override the boundary CRS if its .prj is missing or wrong.",
    )
    parser.add_argument(
        "--nodata",
        type=float,
        help="Override output NoData. Defaults to source NoData, NaN for floats, or an internal validity mask for integers.",
    )
    parser.add_argument(
        "--all-touched",
        action="store_true",
        help="Include every raster pixel touched by the polygon boundary.",
    )
    parser.add_argument(
        "--keep-extent",
        action="store_true",
        help="Keep the full input extent while masking outside the boundary.",
    )
    return parser.parse_args(argv)


def choose_nodata(source_nodata, dtype, requested_nodata):
    if requested_nodata is not None:
        nodata = requested_nodata
    elif source_nodata is not None:
        nodata = source_nodata
    elif np.issubdtype(np.dtype(dtype), np.floating):
        nodata = np.nan
    else:
        nodata = None

    if nodata is not None:
        if np.isinf(nodata):
            raise ValueError("Infinite NoData is not supported.")
        if np.issubdtype(np.dtype(dtype), np.integer):
            limits = np.iinfo(dtype)
            if not np.isfinite(nodata) or nodata != np.floor(nodata) or not limits.min <= nodata <= limits.max:
                raise ValueError("NoData must be an integer representable by the output data type.")
        elif np.isfinite(nodata) and abs(nodata) > np.finfo(dtype).max:
            raise ValueError("NoData exceeds the output floating-point data type range.")
    return nodata


def valid_pixel_count(data, nodata):
    if nodata is None or np.isnan(nodata):
        valid = np.isfinite(data)
    else:
        valid = data != nodata
    return int(valid.sum())


def main(argv=None):
    args = parse_args(argv)
    validate_paths([args.input_raster, args.boundary], [args.output_raster])
    if not args.input_raster.exists():
        raise FileNotFoundError(f"Input raster not found: {args.input_raster}")

    args.output_raster.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(args.input_raster) as src:
        geometries, boundary_crs = read_boundary_geometries(
            args.boundary,
            args.boundary_crs,
            src.crs,
        )
        nodata = choose_nodata(src.nodata, src.dtypes[0], args.nodata)
        try:
            masked, clipped_transform = raster_mask(
                src,
                geometries,
                crop=not args.keep_extent,
                nodata=nodata,
                filled=False,
                all_touched=args.all_touched,
            )
        except ValueError as exc:
            raise ValueError(
                "Boundary does not overlap the raster. Check the raster and boundary CRS."
            ) from exc

        valid_bands = ~np.ma.getmaskarray(masked) & np.isfinite(np.asarray(masked))
        valid = np.all(valid_bands, axis=0)
        if not np.any(valid):
            raise ValueError("The clipped raster contains no valid pixels.")
        if args.nodata is not None and np.isfinite(args.nodata) and np.any(np.asarray(masked)[valid_bands] == args.nodata):
            raise ValueError("Requested NoData equals valid raster values; choose another value or use the default mask.")
        clipped = np.asarray(masked).copy()
        clipped[~valid_bands] = nodata if nodata is not None else 0

        profile = src.profile.copy()
        profile.update(
            {
                "driver": "GTiff",
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": clipped_transform,
                "nodata": nodata,
                "compress": "deflate",
                "BIGTIFF": "IF_SAFER",
            }
        )
        descriptions = src.descriptions
        dataset_tags = src.tags()
        band_tags = [src.tags(index) for index in range(1, src.count + 1)]
        source_crs = src.crs

    with atomic_output(args.output_raster) as staged, rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), rasterio.open(staged, "w", **profile) as dst:
        dst.write(clipped)
        dst.write_mask(valid)
        dst.update_tags(**dataset_tags)
        for index, (description, tags) in enumerate(
            zip(descriptions, band_tags, strict=True), start=1
        ):
            if description:
                dst.set_band_description(index, description)
            if tags:
                dst.update_tags(index, **tags)

    print(f"Input raster: {args.input_raster}")
    print(f"Boundary: {args.boundary}")
    print(f"Boundary source CRS: {boundary_crs}")
    print(f"Raster CRS: {source_crs}")
    print(f"Crop extent: {not args.keep_extent}")
    print(f"Output raster: {args.output_raster}")
    print(f"Output size: {clipped.shape[2]} x {clipped.shape[1]} pixels")
    print(f"Valid output pixels across all bands: {int(valid.sum()):,}")


if __name__ == "__main__":
    main()
