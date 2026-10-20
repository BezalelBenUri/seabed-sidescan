import argparse
import csv
import math
import re
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform
from scipy import ndimage

from .io import atomic_output, validate_paths

CHANNEL_PATTERN = re.compile(r"_ch(?P<channel>\d)_", re.IGNORECASE)
MOSAIC_CLEAN_PATTERNS = (
    "SSS_ch*_raw_mean_mosaic.tif",
    "SSS_ch*_raw_mean_mosaic_overlap_count.tif",
    "SSS_ch*_norm_mean_mosaic.tif",
    "SSS_ch*_norm_mean_mosaic_overlap_count.tif",
    "SSS_ch*_balanced_mean_mosaic.tif",
    "SSS_ch*_balanced_mean_mosaic_overlap_count.tif",
    "SSS_ch*_standard_mosaic.tif",
    "SSS_ch*_standard_mosaic_overlap_count.tif",
    "SSS_ch*_raw_acoustic_mosaic.tif",
    "SSS_ch*_raw_acoustic_mosaic_overlap_count.tif",
    "SSS_ch*_raw_mean_mosaic_AOI.tif",
    "SSS_ch*_norm_mean_mosaic_AOI.tif",
    "SSS_ch*_balanced_mean_mosaic_AOI.tif",
    "SSS_ch*_standard_mosaic_AOI.tif",
    "SSS_ch*_raw_acoustic_mosaic_AOI.tif",
    "SSS_combined_raw_mean_mosaic.tif",
    "SSS_combined_raw_mean_mosaic_overlap_count.tif",
    "SSS_combined_norm_mean_mosaic.tif",
    "SSS_combined_norm_mean_mosaic_overlap_count.tif",
    "SSS_combined_balanced_mean_mosaic.tif",
    "SSS_combined_balanced_mean_mosaic_overlap_count.tif",
    "SSS_combined_standard_mosaic.tif",
    "SSS_combined_standard_mosaic_overlap_count.tif",
    "SSS_combined_raw_acoustic_mosaic.tif",
    "SSS_combined_raw_acoustic_mosaic_overlap_count.tif",
    "SSS_combined_raw_mean_mosaic_AOI.tif",
    "SSS_combined_norm_mean_mosaic_AOI.tif",
    "SSS_combined_balanced_mean_mosaic_AOI.tif",
    "SSS_combined_standard_mosaic_AOI.tif",
    "SSS_combined_raw_acoustic_mosaic_AOI.tif",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "QC georeferenced sidescan strips and build standard corrected "
            "relative acoustic-intensity mosaics."
        )
    )
    parser.add_argument("--georef-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--channels", nargs="+", default=["0", "1"])
    parser.add_argument("--min-valid-percent", type=float, default=1.0)
    parser.add_argument("--min-std", type=float, default=0.5)
    parser.add_argument("--min-percentile-range", type=float, default=2.0)
    parser.add_argument(
        "--edge-trim-percent",
        type=float,
        default=2.0,
        help="Set this percent of each strip edge to NoData before mosaicking.",
    )
    parser.add_argument(
        "--feather-percent",
        type=float,
        default=8.0,
        help="Down-weight this percent of each strip edge in overlap zones.",
    )
    parser.add_argument(
        "--balance-low-percentile",
        type=float,
        default=10.0,
        help="Low robust percentile used for strip-to-strip line balancing.",
    )
    parser.add_argument(
        "--balance-mid-percentile",
        type=float,
        default=50.0,
        help="Mid robust percentile used for strip-to-strip line balancing.",
    )
    parser.add_argument(
        "--balance-high-percentile",
        type=float,
        default=90.0,
        help="High robust percentile used for strip-to-strip line balancing.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete known old mosaic products from the output folder before rebuilding.",
    )
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="Include REVIEW rasters in the mosaic. By default only KEEP rasters are mosaicked.",
    )
    parser.add_argument(
        "--skip-combined",
        action="store_true",
        help="Only create channel mosaics; skip the combined mosaic.",
    )
    parser.add_argument(
        "--also-raw",
        action="store_true",
        help="Also write raw acoustic-intensity mosaics for QC/audit comparison.",
    )
    return parser.parse_args(argv)


def clean_mosaic_outputs(output_dir: Path):
    deleted = []
    patterns = list(MOSAIC_CLEAN_PATTERNS)
    for pattern in MOSAIC_CLEAN_PATTERNS:
        if pattern.endswith(".tif"):
            patterns.extend((f"{pattern}.aux.xml", f"{pattern}.ovr", f"{pattern}.msk"))

    for pattern in patterns:
        for path in sorted(output_dir.glob(pattern)):
            if path.is_file():
                path.unlink()
                deleted.append(path)
    return deleted


def channel_from_name(path: Path):
    match = CHANNEL_PATTERN.search(path.name)
    if not match:
        return None
    return match.group("channel")


def safe_float(value):
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)) and (math.isnan(value) or math.isinf(value)):
        return ""
    return value


def valid_values(data):
    if np.ma.is_masked(data):
        values = data.compressed()
    else:
        arr = np.asarray(data)
        values = arr.ravel()
    values = values[np.isfinite(values)]
    return values.astype("float64", copy=False)


def raster_stats(path: Path):
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        values = valid_values(data)

        total_pixels = int(data.size)
        valid_pixels = int(values.size)
        valid_percent = (valid_pixels / total_pixels * 100.0) if total_pixels else 0.0

        stats = {
            "file": path.name,
            "path": str(path),
            "width": src.width,
            "height": src.height,
            "crs": str(src.crs) if src.crs else "",
            "total_pixels": total_pixels,
            "valid_pixels": valid_pixels,
            "valid_percent": valid_percent,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "p01": None,
            "p99": None,
            "percentile_range": None,
        }

        if valid_pixels:
            values = values.astype("float64", copy=False)
            p01 = float(np.percentile(values, 1))
            p99 = float(np.percentile(values, 99))
            stats.update(
                {
                    "min": float(np.min(values)),
                    "max": float(np.max(values)),
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)),
                    "p01": p01,
                    "p99": p99,
                    "percentile_range": p99 - p01,
                }
            )
        return stats


def classify_stats(stats, args):
    reasons = []

    if stats["valid_pixels"] == 0:
        return "REJECT", "no valid pixels"

    if stats["valid_percent"] < args.min_valid_percent:
        reasons.append(
            f"valid percent {stats['valid_percent']:.2f} < {args.min_valid_percent:.2f}"
        )

    if stats["std"] is not None and stats["std"] < args.min_std:
        reasons.append(f"std {stats['std']:.3f} < {args.min_std:.3f}")

    if (
        stats["percentile_range"] is not None
        and stats["percentile_range"] < args.min_percentile_range
    ):
        reasons.append(
            "p99-p01 "
            f"{stats['percentile_range']:.3f} < {args.min_percentile_range:.3f}"
        )

    if len(reasons) >= 2:
        return "REJECT", "; ".join(reasons)
    if reasons:
        return "REVIEW", "; ".join(reasons)
    return "KEEP", ""


def write_report(report_path: Path, rows):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "channel",
        "decision",
        "reason",
        "file",
        "valid_percent",
        "valid_pixels",
        "total_pixels",
        "min",
        "max",
        "mean",
        "std",
        "p01",
        "p99",
        "percentile_range",
        "width",
        "height",
        "crs",
        "path",
    ]
    with atomic_output(report_path) as staged:
        with staged.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({name: safe_float(row.get(name, "")) for name in fieldnames})


def write_method_report(report_path: Path, args):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Sidescan mosaic method",
        "======================",
        "",
        "Product: standard corrected relative acoustic-intensity mosaic.",
        "Radiometric handling: accepted strips are line-balanced using robust percentile matching before mosaicking.",
        "Trackline control: strip edge trimming and feathered overlap averaging are applied to reduce line-to-line and strip-edge artifacts.",
        "Calibration note: pixel values remain relative processed sonar intensity values, not manufacturer-calibrated dB backscatter.",
        "Line QC: georeferenced strips are assessed before mosaicking using valid-pixel percentage, standard deviation, and p99-p01 percentile range.",
        "Overlap handling: valid overlapping pixels are merged with a feathered weighted mean.",
        "Footprint edges: trimming and feathering use distances to invalid cells and the exterior of each strip, including internal NoData holes. Distances account for both pixel dimensions; percentages use twice the maximum interior distance as an approximate strip thickness.",
        "Grid: preserve the first input grid origin and resolution; other strips use nearest-neighbour resampling on that grid when necessary.",
        "",
        f"Minimum valid pixel percentage: {args.min_valid_percent}",
        f"Minimum standard deviation: {args.min_std}",
        f"Minimum p99-p01 percentile range: {args.min_percentile_range}",
        f"Strip edge trim percent: {args.edge_trim_percent}",
        f"Overlap feather percent: {args.feather_percent}",
        f"Balance low percentile: {args.balance_low_percentile}",
        f"Balance mid percentile: {args.balance_mid_percentile}",
        f"Balance high percentile: {args.balance_high_percentile}",
        f"Review strips included: {bool(args.include_review)}",
        f"Raw audit mosaics written: {bool(args.also_raw)}",
    ]
    with atomic_output(report_path) as staged:
        staged.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_balance_report(report_path: Path, rows):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "product",
        "channel",
        "decision",
        "reason",
        "file",
        "balance_low_percentile",
        "balance_mid_percentile",
        "balance_high_percentile",
        "strip_low",
        "strip_mid",
        "strip_high",
        "strip_range",
        "reference_low",
        "reference_mid",
        "reference_high",
        "reference_range",
        "scale",
        "offset",
        "path",
    ]
    with atomic_output(report_path) as staged:
        with staged.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({name: safe_float(row.get(name, "")) for name in fieldnames})


def mosaic_grid(paths):
    if not paths:
        raise ValueError("At least one raster is required to build a mosaic grid.")
    bounds = []
    res_x = []
    res_y = []
    crs = None

    for path in paths:
        with rasterio.open(path) as src:
            if src.crs is None:
                raise ValueError(f"Mosaic input has no CRS: {path}")
            if src.count != 1:
                raise ValueError(f"Mosaic inputs must be single-band intensity rasters: {path}")
            if np.issubdtype(np.dtype(src.dtypes[0]), np.complexfloating):
                raise ValueError(f"Mosaic inputs must have real intensity values: {path}")
            if not np.isfinite(tuple(src.transform)[:6]).all():
                raise ValueError(f"Mosaic input transform must be finite: {path}")
            if src.transform.b != 0 or src.transform.d != 0 or src.transform.a <= 0 or src.transform.e >= 0:
                raise ValueError(f"Mosaic inputs must use north-up raster grids: {path}")
            if crs is None:
                crs = src.crs
            elif src.crs != crs:
                raise ValueError(f"CRS mismatch in {path}: {src.crs} != {crs}")
            bounds.append(src.bounds)
            res_x.append(abs(src.transform.a))
            res_y.append(abs(src.transform.e))

    if not np.allclose(res_x, res_x[0], rtol=1e-6, atol=0.0) or not np.allclose(res_y, res_y[0], rtol=1e-6, atol=0.0):
        raise ValueError("Mosaic inputs must have matching pixel resolutions; resample explicitly first.")

    pixel_x = float(res_x[0])
    pixel_y = float(res_y[0])
    # Anchor to a real input pixel grid instead of snapping coordinates to a
    # multiple of the resolution relative to world zero, which can shift every
    # original cell in an already aligned survey.
    anchor_x, anchor_y = bounds[0].left, bounds[0].top
    min_col = _grid_floor((min(bound.left for bound in bounds) - anchor_x) / pixel_x)
    max_col = _grid_ceil((max(bound.right for bound in bounds) - anchor_x) / pixel_x)
    min_row = _grid_floor((anchor_y - max(bound.top for bound in bounds)) / pixel_y)
    max_row = _grid_ceil((anchor_y - min(bound.bottom for bound in bounds)) / pixel_y)
    left, top = anchor_x + min_col * pixel_x, anchor_y - min_row * pixel_y
    width, height = max_col - min_col, max_row - min_row
    transform = from_origin(left, top, pixel_x, pixel_y)
    return crs, transform, width, height


def _snap_grid_coordinate(value):
    nearest = round(value)
    return nearest if abs(value - nearest) <= 1e-7 else value


def _grid_floor(value):
    return math.floor(_snap_grid_coordinate(value))


def _grid_ceil(value):
    return math.ceil(_snap_grid_coordinate(value))


def compute_balance_reference(paths, low_percentile, mid_percentile, high_percentile):
    rows = []
    for path in paths:
        row = {
            "file": path.name,
            "path": str(path),
            "balance_low_percentile": low_percentile,
            "balance_mid_percentile": mid_percentile,
            "balance_high_percentile": high_percentile,
            "decision": "USE",
            "reason": "",
        }
        with rasterio.open(path) as src:
            values = valid_values(src.read(1, masked=True))

        if values.size == 0:
            row.update({"decision": "SKIP", "reason": "no valid pixels"})
            rows.append(row)
            continue

        strip_low, strip_mid, strip_high = [
            float(value)
            for value in np.percentile(
                values, [low_percentile, mid_percentile, high_percentile]
            )
        ]
        strip_range = strip_high - strip_low
        row.update(
            {
                "strip_low": strip_low,
                "strip_mid": strip_mid,
                "strip_high": strip_high,
                "strip_range": strip_range,
            }
        )
        if (
            not np.isfinite(strip_low)
            or not np.isfinite(strip_mid)
            or not np.isfinite(strip_high)
            or strip_range <= 0
        ):
            row.update({"decision": "SKIP", "reason": "invalid strip percentile range"})
        rows.append(row)

    usable_rows = [row for row in rows if row["decision"] == "USE"]
    if not usable_rows:
        return None, rows

    reference_low = float(np.median([row["strip_low"] for row in usable_rows]))
    reference_mid = float(np.median([row["strip_mid"] for row in usable_rows]))
    reference_high = float(np.median([row["strip_high"] for row in usable_rows]))
    reference_range = reference_high - reference_low
    reference = {
        "low": reference_low,
        "mid": reference_mid,
        "high": reference_high,
        "range": reference_range,
    }

    for row in rows:
        row.update(
            {
                "reference_low": reference_low,
                "reference_mid": reference_mid,
                "reference_high": reference_high,
                "reference_range": reference_range,
            }
        )
        if row["decision"] != "USE":
            continue
        if not np.isfinite(reference_range) or reference_range <= 0:
            row.update({"decision": "SKIP", "reason": "invalid reference percentile range"})
            continue
        scale = reference_range / row["strip_range"]
        offset = reference_mid - (row["strip_mid"] * scale)
        row.update({"scale": scale, "offset": offset})

    if not np.isfinite(reference_range) or reference_range <= 0:
        return None, rows
    return reference, rows


def _footprint_distances(arr, sampling=(1.0, 1.0)):
    """Cell-centre distances to footprint edges, including internal holes.

    The padded exterior makes all four raster boundaries real edges. Twice
    the maximum distance approximates strip thickness for a footprint of
    arbitrary orientation; highly variable widths share this global scale.
    Sampling is (pixel height, pixel width) in the raster's coordinate units.
    """
    if len(sampling) != 2 or not np.isfinite(sampling).all() or min(sampling) <= 0:
        raise ValueError("Footprint pixel dimensions must be finite and positive.")
    valid = np.isfinite(arr)
    return ndimage.distance_transform_edt(np.pad(valid, 1), sampling=sampling)[1:-1, 1:-1]


def apply_edge_trim(arr, edge_trim_percent, *, sampling=(1.0, 1.0)):
    if not 0 <= edge_trim_percent < 50:
        raise ValueError("Edge trim percent must be between 0 (inclusive) and 50 (exclusive).")
    if edge_trim_percent <= 0:
        return arr
    distances = _footprint_distances(arr, sampling)
    trim_distance = 2.0 * distances.max() * edge_trim_percent / 100.0
    trimmed = arr.copy()
    trimmed[distances <= trim_distance] = np.nan
    return trimmed


def source_weight_array(arr, feather_percent, *, sampling=(1.0, 1.0)):
    if not 0 <= feather_percent < 50:
        raise ValueError("Feather percent must be between 0 (inclusive) and 50 (exclusive).")
    valid = np.isfinite(arr)
    weights = np.zeros(arr.shape, dtype="float32")
    if not valid.any():
        return weights
    if feather_percent <= 0:
        weights[valid] = 1.0
        return weights

    distances = _footprint_distances(arr, sampling)
    feather_distance = 2.0 * distances.max() * feather_percent / 100.0
    weights = np.clip(distances / feather_distance, 0.0, 1.0).astype("float32")
    weights[~valid] = 0.0
    return weights


def read_source_array(
    src,
    mode,
    low_percentile,
    high_percentile,
    balance_reference=None,
    balance_low_percentile=10.0,
    balance_mid_percentile=50.0,
    balance_high_percentile=90.0,
    edge_trim_percent=0.0,
):
    data = src.read(1, masked=True).astype("float64")
    values = valid_values(data)
    if values.size == 0:
        return None

    arr = np.ma.filled(data, np.nan)
    arr[~np.isfinite(arr)] = np.nan
    sampling = (abs(src.transform.e), abs(src.transform.a))
    if mode == "raw":
        return apply_edge_trim(arr, edge_trim_percent, sampling=sampling)

    if mode == "normalized":
        low = float(np.percentile(values, low_percentile))
        high = float(np.percentile(values, high_percentile))
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            return None

        arr = (arr - low) / (high - low) * 255.0
        arr = np.clip(arr, 0.0, 255.0)
        return apply_edge_trim(arr, edge_trim_percent, sampling=sampling)

    if mode == "balanced":
        if balance_reference is None:
            raise ValueError("balance_reference is required for balanced mosaics")
        strip_low, strip_mid, strip_high = [
            float(value)
            for value in np.percentile(
                values,
                [
                    balance_low_percentile,
                    balance_mid_percentile,
                    balance_high_percentile,
                ],
            )
        ]
        strip_range = strip_high - strip_low
        reference_range = balance_reference["range"]
        if (
            not np.isfinite(strip_range)
            or strip_range <= 0
            or not np.isfinite(reference_range)
            or reference_range <= 0
        ):
            return None
        scale = reference_range / strip_range
        arr = (arr - strip_mid) * scale + balance_reference["mid"]
        return apply_edge_trim(arr, edge_trim_percent, sampling=sampling)

    raise ValueError(f"Unsupported mosaic mode: {mode}")


def build_mean_mosaic(
    paths,
    output_path: Path,
    normalize=None,
    low_percentile=2.0,
    high_percentile=98.0,
    mode=None,
    balance_reference=None,
    balance_low_percentile=10.0,
    balance_mid_percentile=50.0,
    balance_high_percentile=90.0,
    edge_trim_percent=0.0,
    feather_percent=0.0,
):
    paths = [Path(path) for path in paths]
    output_path = Path(output_path)
    count_path = output_path.with_name(output_path.stem + "_overlap_count.tif")
    source_paths = [path.resolve() for path in paths]
    if len(set(source_paths)) != len(source_paths):
        raise ValueError("Mosaic input paths must not contain duplicates.")
    validate_paths(paths, (output_path, count_path))
    if len(paths) > np.iinfo(np.uint32).max:
        raise ValueError("Too many mosaic inputs for uint32 overlap counts.")
    if mode is None:
        mode = "normalized" if normalize else "raw"
    if mode not in {"raw", "normalized", "balanced"}:
        raise ValueError(f"Unsupported mosaic mode: {mode}")
    if not 0 <= edge_trim_percent < 50 or not 0 <= feather_percent < 50:
        raise ValueError("Mosaic edge trim and feather percentages must be in [0, 50).")
    if not 0 <= low_percentile < high_percentile <= 100:
        raise ValueError("Normalization percentiles must satisfy 0 <= low < high <= 100.")
    if not 0 <= balance_low_percentile < balance_mid_percentile < balance_high_percentile <= 100:
        raise ValueError("Balance percentiles must satisfy 0 <= low < mid < high <= 100.")
    if mode == "balanced" and (balance_reference is None or
                               not np.isfinite(balance_reference.get("range", np.nan)) or
                               balance_reference["range"] <= 0 or
                               not np.isfinite(balance_reference.get("mid", np.nan))):
        raise ValueError("A finite positive balance reference range and finite midpoint are required.")

    crs, transform, width, height = mosaic_grid(paths)
    sum_arr = np.zeros((height, width), dtype="float64")
    weight_sum_arr = np.zeros((height, width), dtype="float64") if feather_percent > 0 else None
    count_arr = np.zeros((height, width), dtype="uint32")
    first_profile = None

    for path in paths:
        with rasterio.open(path) as src:
            if first_profile is None:
                first_profile = src.profile.copy()
            source = read_source_array(
                src,
                mode,
                low_percentile,
                high_percentile,
                balance_reference=balance_reference,
                balance_low_percentile=balance_low_percentile,
                balance_mid_percentile=balance_mid_percentile,
                balance_high_percentile=balance_high_percentile,
                edge_trim_percent=edge_trim_percent,
            )
            if source is None:
                continue
            if np.any(np.abs(source[np.isfinite(source)]) > np.finfo(np.float32).max):
                raise ValueError(f"Mosaic source intensity cannot be represented as float32: {path}")

            # Reproject only the source's intersection with the output grid.
            # Allocating a full union-sized destination for every strip wastes
            # memory and time on the predominantly empty survey exterior.
            fractional = from_bounds(*src.bounds, transform=transform)
            row0, col0 = max(0, _grid_floor(fractional.row_off)), max(0, _grid_floor(fractional.col_off))
            row1 = min(height, _grid_ceil(fractional.row_off + fractional.height))
            col1 = min(width, _grid_ceil(fractional.col_off + fractional.width))
            window = Window(col0, row0, col1 - col0, row1 - row0)
            destination_transform = window_transform(window, transform)
            destination = np.full((row1 - row0, col1 - col0), np.nan, dtype="float64")
            reproject(
                source=source,
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=np.nan,
                dst_transform=destination_transform,
                dst_crs=crs,
                dst_nodata=np.nan,
                resampling=Resampling.nearest,
            )
            if feather_percent > 0:
                source_weights = source_weight_array(
                    source, feather_percent,
                    sampling=(abs(src.transform.e), abs(src.transform.a)),
                )
                destination_weight = np.zeros(destination.shape, dtype="float32")
                reproject(
                    source=source_weights,
                    destination=destination_weight,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    src_nodata=0.0,
                    dst_transform=destination_transform,
                    dst_crs=crs,
                    dst_nodata=0.0,
                    resampling=Resampling.nearest,
                )

            valid = np.isfinite(destination)
            sum_view = sum_arr[row0:row1, col0:col1]
            count_view = count_arr[row0:row1, col0:col1]
            if feather_percent > 0:
                valid &= destination_weight > 0
                sum_view[valid] += destination[valid] * destination_weight[valid]
                weight_view = weight_sum_arr[row0:row1, col0:col1]
                weight_view[valid] += destination_weight[valid]
            else:
                sum_view[valid] += destination[valid]
            count_view[valid] += 1

    if not count_arr.any():
        raise ValueError("No valid mosaic pixels remain after normalization and edge trimming.")

    mean_arr = np.full((height, width), np.nan, dtype="float32")
    if feather_percent > 0:
        valid_count = weight_sum_arr > 0
        mean_arr[valid_count] = (
            sum_arr[valid_count] / weight_sum_arr[valid_count]
        ).astype("float32")
    else:
        valid_count = count_arr > 0
        mean_arr[valid_count] = (
            sum_arr[valid_count] / count_arr[valid_count]
        ).astype("float32")

    profile = first_profile or {}
    profile.update(
        {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "transform": transform,
            "crs": crs,
            "count": 1,
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count_profile = profile.copy()
    count_profile.update({"dtype": "uint32", "nodata": 0, "predictor": 1})
    # Both writers finish before either old product is replaced.
    with atomic_output(output_path) as staged_output, atomic_output(count_path) as staged_count:
        with rasterio.open(staged_output, "w", **profile) as dst:
            dst.write(mean_arr, 1)
        with rasterio.open(staged_count, "w", **count_profile) as dst:
            dst.write(count_arr, 1)
    return output_path


def build_standard_mosaic(paths, output_path: Path, args, product_channel, balance_rows):
    balance_reference, product_balance_rows = compute_balance_reference(
        paths,
        args.balance_low_percentile,
        args.balance_mid_percentile,
        args.balance_high_percentile,
    )
    for row in product_balance_rows:
        row.update({"product": output_path.name, "channel": product_channel})
    balance_rows.extend(product_balance_rows)

    if balance_reference is None:
        print(f"{product_channel}: standard mosaic skipped; no usable balance reference")
        return

    print(
        f"{product_channel}: standard corrected mosaic from {len(paths)} rasters -> "
        f"{output_path}"
    )
    return build_mean_mosaic(
        paths,
        output_path,
        mode="balanced",
        balance_reference=balance_reference,
        balance_low_percentile=args.balance_low_percentile,
        balance_mid_percentile=args.balance_mid_percentile,
        balance_high_percentile=args.balance_high_percentile,
        edge_trim_percent=args.edge_trim_percent,
        feather_percent=args.feather_percent,
    )


def build_raw_acoustic_mosaic(paths, output_path: Path, args, product_channel):
    print(
        f"{product_channel}: raw acoustic-intensity mosaic from {len(paths)} rasters -> "
        f"{output_path}"
    )
    return build_mean_mosaic(
        paths,
        output_path,
        mode="raw",
        edge_trim_percent=args.edge_trim_percent,
        feather_percent=args.feather_percent,
    )


def _build_requested_products(args, rows, accepted_by_channel, combined_paths, balance_rows):
    created = []
    for channel in args.channels:
        channel_rows = [row for row in rows if row["channel"] == channel]
        counts = {decision: sum(row["decision"] == decision for row in channel_rows)
                  for decision in ("KEEP", "REVIEW", "REJECT")}
        print(f"ch{channel}: {counts['KEEP']} keep, {counts['REVIEW']} review, {counts['REJECT']} reject")
        accepted = accepted_by_channel[channel]
        if not accepted:
            print(f"ch{channel}: no accepted rasters; mosaics skipped")
            continue
        standard_path = args.output_dir / f"SSS_ch{channel}_standard_mosaic.tif"
        result = build_standard_mosaic(accepted, standard_path, args, f"ch{channel}", balance_rows)
        if result is not None:
            created.append(result)
        if args.also_raw:
            raw_path = args.output_dir / f"SSS_ch{channel}_raw_acoustic_mosaic.tif"
            created.append(build_raw_acoustic_mosaic(accepted, raw_path, args, f"ch{channel}"))

    if combined_paths and not args.skip_combined:
        result = build_standard_mosaic(
            combined_paths, args.output_dir / "SSS_combined_standard_mosaic.tif",
            args, "combined", balance_rows,
        )
        if result is not None:
            created.append(result)
        if args.also_raw:
            created.append(build_raw_acoustic_mosaic(
                combined_paths, args.output_dir / "SSS_combined_raw_acoustic_mosaic.tif",
                args, "combined",
            ))
    return created


def main(argv=None):
    args = parse_args(argv)
    if args.georef_dir.resolve() == args.output_dir.resolve():
        raise ValueError("Mosaic input and output directories must differ.")
    if any(not channel.isdigit() or len(channel) != 1 for channel in args.channels):
        raise ValueError("Channels must be single-digit channel numbers.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    if not 0 <= args.edge_trim_percent < 50:
        raise ValueError("--edge-trim-percent must be between 0 (inclusive) and 50 (exclusive)")
    if not 0 <= args.feather_percent < 50:
        raise ValueError("--feather-percent must be between 0 (inclusive) and 50 (exclusive)")
    if not 0 <= args.min_valid_percent <= 100:
        raise ValueError("--min-valid-percent must be between 0 and 100")
    if not np.isfinite(args.min_std) or args.min_std < 0 or not np.isfinite(args.min_percentile_range) or args.min_percentile_range < 0:
        raise ValueError("QC standard deviation and percentile-range thresholds must be finite and nonnegative")
    if len(set(args.channels)) != len(args.channels):
        raise ValueError("Channels must not contain duplicates")
    if not (
        0 <= args.balance_low_percentile
        < args.balance_mid_percentile
        < args.balance_high_percentile <= 100
    ):
        raise ValueError(
            "Balance percentiles must satisfy 0 <= low < mid < high <= 100"
        )

    print("Mosaic method: standard corrected relative acoustic-intensity mosaic")
    print(
        "Radiometric handling: robust strip-to-strip line balancing "
        f"(P{args.balance_low_percentile:g}/"
        f"P{args.balance_mid_percentile:g}/"
        f"P{args.balance_high_percentile:g})"
    )
    print(f"Strip edge trim: {args.edge_trim_percent}%")
    print(f"Overlap feather: {args.feather_percent}%")
    if args.also_raw:
        print("Raw acoustic-intensity audit mosaics: enabled")

    tif_paths = sorted(path for path in args.georef_dir.glob("*") if path.suffix.lower() in {".tif", ".tiff"})
    if not tif_paths:
        raise FileNotFoundError(f"No GeoTIFF files found in {args.georef_dir}")
    product_prefixes = [f"SSS_ch{channel}" for channel in args.channels]
    if not args.skip_combined:
        product_prefixes.append("SSS_combined")
    products = [args.output_dir / f"{prefix}_standard_mosaic.tif" for prefix in product_prefixes]
    if args.also_raw:
        products.extend(args.output_dir / f"{prefix}_raw_acoustic_mosaic.tif" for prefix in product_prefixes)
    counts = [path.with_name(path.stem + "_overlap_count.tif") for path in products]
    reports = [args.report_dir / name for name in ("strip_qc_report.csv", "mosaic_method_report.txt", "strip_balance_report.csv")]
    validate_paths(tif_paths, [*products, *counts, *reports])

    rows = []
    accepted_by_channel = {channel: [] for channel in args.channels}

    for path in tif_paths:
        channel = channel_from_name(path)
        if channel not in accepted_by_channel:
            continue

        stats = raster_stats(path)
        decision, reason = classify_stats(stats, args)
        row = {"channel": channel, "decision": decision, "reason": reason}
        row.update(stats)
        rows.append(row)

        if decision == "KEEP" or (args.include_review and decision == "REVIEW"):
            accepted_by_channel[channel].append(path)

    report_path = args.report_dir / "strip_qc_report.csv"
    write_report(report_path, rows)
    method_report_path = args.report_dir / "mosaic_method_report.txt"
    write_method_report(method_report_path, args)

    print(f"QC report written to: {report_path}")
    print(f"Mosaic method report written to: {method_report_path}")
    combined_paths = [path for channel in args.channels for path in accepted_by_channel[channel]]
    if not combined_paths:
        raise ValueError("No accepted strips are available for mosaicking; inspect the strip QC report.")
    # Preflight the complete grid before removing any previous valid products.
    mosaic_grid(combined_paths)
    if not args.also_raw:
        reference, _ = compute_balance_reference(
            combined_paths, args.balance_low_percentile,
            args.balance_mid_percentile, args.balance_high_percentile,
        )
        if reference is None:
            raise ValueError("No usable strip percentile ranges are available for balanced mosaicking.")
    balance_rows = []
    # Complete every requested mosaic in a private staging directory before
    # cleaning/replacing earlier products. A late strip/read/compute failure
    # must not destroy a previous successful survey mosaic.
    with tempfile.TemporaryDirectory(prefix=".seabed-mosaics-", dir=args.output_dir) as staging:
        staged_args = argparse.Namespace(**vars(args))
        staged_args.output_dir = Path(staging)
        staged_products = _build_requested_products(
            staged_args, rows, accepted_by_channel, combined_paths, balance_rows,
        )
        if not staged_products:
            raise ValueError("No mosaic was produced; inspect the strip QC and balance reports.")
        if args.clean_output:
            deleted = clean_mosaic_outputs(args.output_dir)
            print(f"Cleaned {len(deleted)} existing mosaic product(s) from: {args.output_dir}")
        created = []
        for product in staged_products:
            destination = args.output_dir / product.name
            product.replace(destination)
            count = product.with_name(product.stem + "_overlap_count.tif")
            count.replace(destination.with_name(destination.stem + "_overlap_count.tif"))
            # Cached overviews/metadata belonging to an older raster are
            # invalid after replacement, even without --clean-output.
            for replaced in (destination, destination.with_name(destination.stem + "_overlap_count.tif")):
                for suffix in (".aux.xml", ".ovr", ".msk"):
                    replaced.with_name(replaced.name + suffix).unlink(missing_ok=True)
            created.append(destination)

    balance_report_path = args.report_dir / "strip_balance_report.csv"
    write_balance_report(balance_report_path, balance_rows)
    print(f"Strip balance report written to: {balance_report_path}")
    if not created:
        raise ValueError("No mosaic was produced; inspect the strip QC and balance reports.")
    return tuple(created)


if __name__ == "__main__":
    main()
