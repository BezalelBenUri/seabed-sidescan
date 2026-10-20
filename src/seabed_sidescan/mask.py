import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

from .io import atomic_output, validate_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a valid-data mask from a raster mosaic."
    )
    parser.add_argument("--input-raster", required=True, type=Path)
    parser.add_argument("--output-mask", required=True, type=Path)
    parser.add_argument(
        "--boundary",
        type=Path,
        help="Optional polygon shapefile. Valid raster pixels outside it become 0.",
    )
    parser.add_argument(
        "--boundary-crs",
        help="Override the boundary CRS, for example EPSG:32632, if its .prj is missing or wrong.",
    )
    parser.add_argument(
        "--output-boundary-mask",
        type=Path,
        help="Optional 1/0 raster showing the polygon footprint on the mosaic grid.",
    )
    parser.add_argument(
        "--all-touched",
        action="store_true",
        help="Include every raster pixel touched by the boundary, not only pixels whose centre is inside.",
    )
    return parser.parse_args(argv)


def read_boundary_geometries(boundary_path, boundary_crs_override, target_crs):
    try:
        import shapefile
    except ImportError as exc:
        raise ImportError(
            "Boundary masking requires pyshp. Install the package again with "
            "'python -m pip install -e .'."
        ) from exc

    if boundary_path.suffix.lower() != ".shp":
        raise ValueError("--boundary currently supports ESRI polygon shapefiles (.shp).")
    if not boundary_path.exists():
        raise FileNotFoundError(f"Boundary shapefile not found: {boundary_path}")

    with shapefile.Reader(str(boundary_path)) as reader:
        polygon_types = {shapefile.POLYGON, shapefile.POLYGONM, shapefile.POLYGONZ}
        shapes = reader.shapes()
        if not shapes:
            raise ValueError(f"Boundary shapefile contains no features: {boundary_path}")
        invalid_types = sorted({shape.shapeType for shape in shapes} - polygon_types)
        if invalid_types:
            raise ValueError(
                "Boundary must contain only polygon features; "
                f"found shapefile geometry type code(s): {invalid_types}"
            )
        geometries = [shape.__geo_interface__ for shape in shapes]

    if boundary_crs_override:
        source_crs = CRS.from_user_input(boundary_crs_override)
    else:
        prj_path = boundary_path.with_suffix(".prj")
        if not prj_path.exists():
            raise FileNotFoundError(
                f"Boundary CRS is unknown because no .prj file was found: {prj_path}. "
                "Provide --boundary-crs."
            )
        source_crs = CRS.from_wkt(prj_path.read_text(encoding="utf-8", errors="replace"))

    if target_crs is None:
        raise ValueError("Input raster has no CRS, so the boundary cannot be aligned safely.")

    if source_crs != target_crs:
        geometries = [
            transform_geom(source_crs, target_crs, geometry, precision=-1)
            for geometry in geometries
        ]
    return geometries, source_crs


def mask_profile(source_profile):
    profile = source_profile.copy()
    profile.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "uint8",
            "nodata": 0,
            "compress": "deflate",
            "predictor": 1,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "BIGTIFF": "IF_SAFER",
        }
    )
    return profile


def write_mask(path, mask, profile):
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(path) as staged, rasterio.open(staged, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)


def main(argv=None):
    args = parse_args(argv)
    validate_paths([args.input_raster, *([args.boundary] if args.boundary else [])],
                   [args.output_mask, *([args.output_boundary_mask] if args.output_boundary_mask else [])])
    if not args.boundary and (args.output_boundary_mask or args.boundary_crs or args.all_touched):
        raise ValueError("Boundary options require a boundary shapefile.")
    args.output_mask.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(args.input_raster) as src:
        if src.count != 1 or np.issubdtype(np.dtype(src.dtypes[0]), np.complexfloating):
            raise ValueError("The intensity mosaic must have one real-valued band.")
        data = src.read(1, masked=True)
        # Inspect the mask directly: filling an integer masked array with NaN
        # raises TypeError and needlessly converts otherwise valid raster data.
        valid = ~np.ma.getmaskarray(data) & np.isfinite(np.asarray(data))

        valid_before_boundary = int(valid.sum())
        boundary_pixels = None
        source_boundary_crs = None
        if args.boundary:
            geometries, source_boundary_crs = read_boundary_geometries(
                args.boundary,
                args.boundary_crs,
                src.crs,
            )
            inside_boundary = geometry_mask(
                geometries,
                out_shape=src.shape,
                transform=src.transform,
                invert=True,
                all_touched=args.all_touched,
            )
            boundary_pixels = int(inside_boundary.sum())
            if boundary_pixels == 0:
                raise ValueError(
                    "Boundary does not overlap the input raster. Check both CRS definitions and locations."
                )
            valid &= inside_boundary

        mask = valid.astype("uint8")
        profile = mask_profile(src.profile)
        if int(mask.sum()) == 0:
            raise ValueError(
                "The final analysis mask contains no valid pixels. Check the mosaic, boundary, and CRS."
            )
        write_mask(args.output_mask, mask, profile)
        if args.boundary and args.output_boundary_mask:
            write_mask(args.output_boundary_mask, inside_boundary, profile)

    total = int(mask.size)
    valid_count = int(mask.sum())
    valid_percent = valid_count / total * 100.0 if total else 0.0
    print(f"Input raster: {args.input_raster}")
    if args.boundary:
        print(f"Boundary: {args.boundary}")
        print(f"Boundary source CRS: {source_boundary_crs}")
        print(f"Raster CRS: {src.crs}")
        print(f"Boundary pixels on raster grid: {boundary_pixels:,}")
        print(f"Valid sonar pixels before boundary: {valid_before_boundary:,}")
        print(f"Valid sonar pixels removed by boundary: {valid_before_boundary - valid_count:,}")
        if args.output_boundary_mask:
            print(f"Boundary-only mask: {args.output_boundary_mask}")
    print(f"Output mask: {args.output_mask}")
    print(f"Valid pixels: {valid_count:,} / {total:,} ({valid_percent:.2f}%)")


if __name__ == "__main__":
    main()
