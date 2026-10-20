from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import rasterio

from .io import atomic_output, validate_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a masked multi-band feature stack from aligned raster features."
    )
    parser.add_argument("--input-rasters", required=True, nargs="+", type=Path)
    parser.add_argument("--band-names", nargs="+")
    parser.add_argument("--mask-raster", required=True, type=Path)
    parser.add_argument("--output-stack", required=True, type=Path)
    parser.add_argument("--metadata-csv", required=True, type=Path)
    return parser.parse_args(argv)


def validate_names(paths, names):
    if names is None:
        names = [path.stem for path in paths]
    if len(names) != len(paths):
        raise ValueError("--band-names must contain one name for each input raster.")
    if any(not name.strip() for name in names) or len(set(names)) != len(names):
        raise ValueError("Feature band names must be nonempty and unique.")
    return names


def validate_alignment(paths, mask_path):
    if not paths:
        raise ValueError("At least one input raster is required.")

    with rasterio.open(paths[0]) as first:
        if first.count != 1 or np.issubdtype(np.dtype(first.dtypes[0]), np.complexfloating):
            raise ValueError("Each input feature raster must have one real-valued band.")
        reference = {
            "shape": first.shape,
            "transform": first.transform,
            "crs": first.crs,
            "profile": first.profile.copy(),
        }

    for path in paths[1:]:
        with rasterio.open(path) as src:
            if src.count != 1 or np.issubdtype(np.dtype(src.dtypes[0]), np.complexfloating):
                raise ValueError("Each input feature raster must have one real-valued band.")
            if src.shape != reference["shape"]:
                raise ValueError(f"Shape mismatch in {path}: {src.shape} != {reference['shape']}")
            if src.transform != reference["transform"]:
                raise ValueError(f"Transform mismatch in {path}")
            if src.crs != reference["crs"]:
                raise ValueError(f"CRS mismatch in {path}: {src.crs} != {reference['crs']}")

    with rasterio.open(mask_path) as mask_src:
        if mask_src.count != 1 or np.issubdtype(np.dtype(mask_src.dtypes[0]), np.complexfloating):
            raise ValueError("Analysis mask must have exactly one real-valued band.")
        if mask_src.shape != reference["shape"]:
            raise ValueError(
                f"Mask shape {mask_src.shape} does not match feature shape {reference['shape']}."
            )
        if mask_src.transform != reference["transform"]:
            raise ValueError("Mask transform does not match feature rasters.")
        if mask_src.crs != reference["crs"]:
            raise ValueError("Mask CRS does not match feature rasters.")

    return reference


def band_stats(path, valid_mask):
    with rasterio.open(path) as src:
        data = src.read(1, masked=True).astype("float32")
        arr = np.ma.filled(data, np.nan)
    valid = valid_mask & np.isfinite(arr)
    values = arr[valid].astype("float64", copy=False)
    if values.size == 0:
        return {
            "valid_pixels": 0,
            "min": "",
            "max": "",
            "mean": "",
            "std": "",
            "p02": "",
            "p98": "",
        }
    return {
        "valid_pixels": int(values.size),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p02": float(np.percentile(values, 2)),
        "p98": float(np.percentile(values, 98)),
    }


def write_metadata(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "band",
        "name",
        "source",
        "valid_pixels",
        "min",
        "max",
        "mean",
        "std",
        "p02",
        "p98",
    ]
    with atomic_output(path) as staged, staged.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    args = parse_args(argv)
    validate_paths([*args.input_rasters, args.mask_raster], [args.output_stack, args.metadata_csv])
    names = validate_names(args.input_rasters, args.band_names)
    reference = validate_alignment(args.input_rasters, args.mask_raster)

    args.output_stack.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_csv.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(args.mask_raster) as mask_src:
        mask_values = mask_src.read(1, masked=True)
        values = mask_values.compressed()
        if np.any((values != 0) & (values != 1)):
            raise ValueError("Analysis mask must contain only 0 and 1.")
        valid_mask = np.ma.filled(mask_values == 1, False)

    profile = reference["profile"]
    profile.update(
        {
            "driver": "GTiff",
            "count": len(args.input_rasters),
            "dtype": "float32",
            "nodata": np.nan,
            "compress": "deflate",
            "predictor": 2,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "BIGTIFF": "IF_SAFER",
        }
    )

    rows = []
    common_valid = valid_mask.copy()
    with atomic_output(args.output_stack) as staged, rasterio.open(staged, "w", **profile) as dst:
        for band_index, (raster_path, name) in enumerate(zip(args.input_rasters, names, strict=True), start=1):
            print(f"Adding band {band_index}: {name} <- {raster_path}")
            stats = band_stats(raster_path, valid_mask)
            with rasterio.open(raster_path) as src:
                original = src.read(1, masked=True).astype("float64")
                finite_original = original.compressed()
                if np.any(np.isfinite(finite_original) & (np.abs(finite_original) > np.finfo("float32").max)):
                    raise ValueError("Feature values exceed float32 output range; rescale the feature first.")
                data = src.read(1, masked=True).astype("float32")
                arr = np.ma.filled(data, np.nan).astype("float32")
            arr[~valid_mask] = np.nan
            common_valid &= np.isfinite(arr)
            dst.write(arr, band_index)
            dst.set_band_description(band_index, name)

            row = {"band": band_index, "name": name, "source": str(raster_path)}
            row.update(stats)
            rows.append(row)
        if not np.any(common_valid):
            raise ValueError("No pixels have valid values in every feature band.")

    write_metadata(args.metadata_csv, rows)
    print(f"Feature stack written to: {args.output_stack}")
    print(f"Band metadata written to: {args.metadata_csv}")


if __name__ == "__main__":
    main()

