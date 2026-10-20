from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .io import atomic_output, validate_paths, windows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run scikit-learn KMeans clustering on a masked feature stack."
    )
    parser.add_argument("--feature-stack", required=True, type=Path)
    parser.add_argument("--mask-raster", required=True, type=Path)
    parser.add_argument("--output-raster", required=True, type=Path)
    parser.add_argument("--report-csv", required=True, type=Path)
    parser.add_argument("--model-json", required=True, type=Path)
    parser.add_argument("--classes", type=int, default=4)
    parser.add_argument("--sample-size", type=int, default=200000)
    parser.add_argument("--n-init", type=int, default=50)
    parser.add_argument("--max-iterations", type=int, default=500)
    parser.add_argument("--tolerance", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--chunk-rows", type=int, default=256)
    parser.add_argument("--no-standardize", action="store_true")
    return parser.parse_args(argv)


def validate_inputs(feature_stack, mask_raster, classes):
    if classes < 2 or classes > 255:
        raise ValueError("--classes must be between 2 and 255.")

    with rasterio.open(feature_stack) as src:
        if any(np.issubdtype(np.dtype(dtype), np.complexfloating) for dtype in src.dtypes):
            raise ValueError("Feature bands must contain real values.")
        reference = {
            "shape": src.shape,
            "transform": src.transform,
            "crs": src.crs,
            "count": src.count,
            "profile": src.profile.copy(),
            "descriptions": src.descriptions,
        }

    with rasterio.open(mask_raster) as mask_src:
        if mask_src.count != 1 or np.issubdtype(np.dtype(mask_src.dtypes[0]), np.complexfloating):
            raise ValueError("Analysis mask must have exactly one real-valued band.")
        if mask_src.shape != reference["shape"]:
            raise ValueError("Mask shape does not match feature stack.")
        if mask_src.transform != reference["transform"]:
            raise ValueError("Mask transform does not match feature stack.")
        if mask_src.crs != reference["crs"]:
            raise ValueError("Mask CRS does not match feature stack.")

    return reference


def read_training_data(feature_stack, mask_raster, sample_size, seed):
    if sample_size < 1:
        raise ValueError("--sample-size must be at least 1.")
    rng = np.random.default_rng(seed)
    validate_inputs(feature_stack, mask_raster, 2)
    with rasterio.open(feature_stack) as src, rasterio.open(mask_raster) as mask_src:
        def read_window(window):
            data = np.ma.filled(src.read(window=window, masked=True).astype("float64"), np.nan)
            analysis = mask_src.read(1, window=window, masked=True)
            unmasked = analysis.compressed()
            if np.any((unmasked != 0) & (unmasked != 1)):
                raise ValueError("Analysis mask must contain only 0 and 1.")
            valid = np.ma.filled(analysis == 1, False) & np.all(np.isfinite(data), axis=0)
            return data, valid

        valid_pixels = 0
        for window in windows(src.width, src.height, src.count):
            _, valid = read_window(window)
            valid_pixels += int(np.count_nonzero(valid))
        if not valid_pixels:
            raise ValueError("No valid pixels are available for classification.")
        count = min(sample_size, valid_pixels)
        ranks = np.sort(rng.choice(valid_pixels, size=count, replace=False)) if count < valid_pixels else np.arange(count)
        sample = np.empty((count, src.count), dtype="float64")
        offset = 0
        for window in windows(src.width, src.height, src.count):
            data, valid = read_window(window)
            size = int(np.count_nonzero(valid))
            start, stop = np.searchsorted(ranks, [offset, offset + size])
            if stop > start:
                sample[start:stop] = data[:, valid].T[ranks[start:stop] - offset]
            offset += size
        if offset != valid_pixels:
            raise RuntimeError("Input rasters changed while sampling; retry with stable input files.")
    return sample, valid_pixels, count


def standardize(sample, enabled):
    limit = np.sqrt(np.finfo("float64").max / max(1, sample.shape[1])) / 4
    if not np.all(np.isfinite(sample)) or np.max(np.abs(sample)) > limit:
        raise ValueError("Feature magnitudes exceed the safe numerical range; rescale the features.")
    if not enabled:
        mean = np.zeros(sample.shape[1], dtype="float64")
        std = np.ones(sample.shape[1], dtype="float64")
        return sample, mean, std

    scaler = StandardScaler()
    scaled = scaler.fit_transform(sample)
    return scaled, scaler.mean_.astype("float64"), scaler.scale_.astype("float64")


def squared_distances(values, centers):
    # cdist avoids a (pixels, classes, features) broadcast temporary and the
    # cancellation in the alternative squared-norm matrix identity.
    from scipy.spatial.distance import cdist

    distances = cdist(values, centers, metric="sqeuclidean")
    if not np.all(np.isfinite(distances)):
        raise ValueError("Feature distances exceed the finite numerical range; rescale the features.")
    return distances


def assign_labels(values, centers, chunk_size=50000):
    chunk_size = max(1, min(chunk_size, (16 * 1024 * 1024) // max(8, centers.shape[0] * 8)))
    labels = np.empty(values.shape[0], dtype="int32")
    inertia = 0.0
    for start in range(0, values.shape[0], chunk_size):
        stop = min(start + chunk_size, values.shape[0])
        distances = squared_distances(values[start:stop], centers)
        labels[start:stop] = np.argmin(distances, axis=1)
        inertia += float(np.min(distances, axis=1).sum())
        if not np.isfinite(inertia):
            raise ValueError("Classification inertia exceeds the finite numerical range; rescale the features.")
    return labels, inertia


def fit_kmeans(values, classes, n_init, max_iterations, tolerance, seed):
    validate_cluster_count(values, classes)
    model = KMeans(
        n_clusters=classes,
        init="k-means++",
        n_init=n_init,
        max_iter=max_iterations,
        tol=tolerance,
        random_state=seed,
        algorithm="lloyd",
    )
    model.fit(values)
    if np.unique(model.labels_).size != classes:
        raise ValueError("KMeans could not produce the requested number of distinct classes.")
    return model.cluster_centers_, int(model.n_iter_), float(model.inertia_)


def validate_cluster_count(values, classes):
    if values.shape[0] < classes:
        raise ValueError("Training sample has fewer pixels than the requested number of classes.")
    if np.unique(values, axis=0).shape[0] < classes:
        raise ValueError("Training sample has fewer distinct feature vectors than the requested classes.")


def sorted_centers(centers_standardized, mean, std):
    centers_original = centers_standardized * std + mean
    order = np.argsort(centers_original[:, 0])
    return centers_standardized[order], centers_original[order]


def classify_full_stack(feature_stack, mask_raster, output_raster, centers, mean, std, standardize_enabled, chunk_rows):
    if chunk_rows < 1:
        raise ValueError("--chunk-rows must be at least 1.")
    with rasterio.open(feature_stack) as src, rasterio.open(mask_raster) as mask_src:
        profile = src.profile.copy()
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

        output_raster.parent.mkdir(parents=True, exist_ok=True)
        class_counts = np.zeros(centers.shape[0], dtype="int64")
        with atomic_output(output_raster) as staged, rasterio.open(staged, "w", **profile) as dst:
            for window in windows(src.width, src.height, src.count, rows_limit=chunk_rows):
                height = int(window.height)
                features = src.read(window=window, masked=True).astype("float64")
                data = np.ma.filled(features, np.nan)
                analysis_mask = mask_src.read(1, window=window, masked=True)
                mask = np.ma.filled(analysis_mask == 1, False)
                finite = np.all(np.isfinite(data), axis=0)
                valid = mask & finite
                labels = np.zeros((height, int(window.width)), dtype="uint8")

                if np.any(valid):
                    flat = data.reshape(data.shape[0], -1).T
                    valid_flat = valid.ravel()
                    values = flat[valid_flat]
                    if standardize_enabled:
                        values = (values - mean) / std
                    assigned, _ = assign_labels(values, centers)
                    class_values = (assigned + 1).astype("uint8")
                    labels.ravel()[valid_flat] = class_values
                    class_counts += np.bincount(assigned, minlength=centers.shape[0])

                dst.write(labels, 1, window=window)
                if window.col_off + window.width == src.width:
                    print(f"Classified rows {int(window.row_off) + 1}-{int(window.row_off) + height} of {src.height}")

    return class_counts


def write_report(path, class_counts, centers_original, feature_names, pixel_area):
    path.parent.mkdir(parents=True, exist_ok=True)
    total = int(class_counts.sum())
    fieldnames = ["class", "pixel_count", "area_m2", "percent_valid"]
    fieldnames += [f"center_{name}" for name in feature_names]
    with atomic_output(path) as staged, staged.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, count in enumerate(class_counts):
            row = {
                "class": index + 1,
                "pixel_count": int(count),
                "area_m2": float(count * pixel_area),
                "percent_valid": float(count / total * 100.0) if total else 0.0,
            }
            for name, value in zip(feature_names, centers_original[index], strict=True):
                row[f"center_{name}"] = float(value)
            writer.writerow(row)


def write_model(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(path) as staged:
        staged.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def pixel_area_m2(reference):
    """Return the affine pixel area, requiring a projected metre grid."""
    crs = reference["crs"]
    if crs is None or not crs.is_projected:
        raise ValueError("Classification area reports require a projected CRS in metres.")
    _, unit_factor = crs.linear_units_factor
    if not np.isclose(unit_factor, 1.0, rtol=0.0, atol=1e-12):
        raise ValueError("Classification area reports require CRS horizontal units in metres.")
    transform = reference["transform"]
    area = abs(transform.a * transform.e - transform.b * transform.d)
    if not np.isfinite(area) or area <= 0:
        raise ValueError("Raster transform must define a finite, nonzero pixel area.")
    return float(area)


def main(argv=None):
    args = parse_args(argv)
    validate_paths([args.feature_stack, args.mask_raster], [args.output_raster, args.report_csv, args.model_json])
    if args.sample_size < 1 or args.chunk_rows < 1:
        raise ValueError("--sample-size and --chunk-rows must be at least 1.")
    if args.n_init < 1 or args.max_iterations < 1:
        raise ValueError("--n-init and --max-iterations must be at least 1.")
    if not np.isfinite(args.tolerance) or args.tolerance < 0:
        raise ValueError("--tolerance must be a finite, nonnegative number.")
    reference = validate_inputs(args.feature_stack, args.mask_raster, args.classes)
    pixel_area = pixel_area_m2(reference)
    feature_names = [
        description or f"band_{index}"
        for index, description in enumerate(reference["descriptions"], start=1)
    ]
    if len(set(feature_names)) != len(feature_names):
        raise ValueError("Feature band descriptions must be unique for the class report.")

    print(f"Feature stack: {args.feature_stack}")
    print(f"Mask raster: {args.mask_raster}")
    print(f"Classes: {args.classes}")
    print(f"Sample size target: {args.sample_size:,}")
    print(f"KMeans n_init: {args.n_init}")
    print(f"KMeans max iterations: {args.max_iterations}")

    sample, valid_pixels, actual_sample_size = read_training_data(
        args.feature_stack, args.mask_raster, args.sample_size, args.seed
    )
    print(f"Valid pixels: {valid_pixels:,}")
    print(f"Training sample pixels: {actual_sample_size:,}")

    sample_for_fit, mean, std = standardize(sample, enabled=not args.no_standardize)
    print("Fitting scikit-learn KMeans...")
    centers, iterations, inertia = fit_kmeans(
        sample_for_fit,
        args.classes,
        args.n_init,
        args.max_iterations,
        args.tolerance,
        args.seed,
    )
    centers, centers_original = sorted_centers(centers, mean, std)

    class_counts = classify_full_stack(
        args.feature_stack,
        args.mask_raster,
        args.output_raster,
        centers,
        mean,
        std,
        standardize_enabled=not args.no_standardize,
        chunk_rows=args.chunk_rows,
    )

    write_report(args.report_csv, class_counts, centers_original, feature_names, pixel_area)
    write_model(
        args.model_json,
        {
            "algorithm": "sklearn_kmeans",
            "classes": args.classes,
            "init": "k-means++",
            "class_order": "ascending center value of first feature band",
            "feature_names": feature_names,
            "standardized": not args.no_standardize,
            "n_init": args.n_init,
            "max_iterations": args.max_iterations,
            "tolerance": args.tolerance,
            "random_seed": args.seed,
            "feature_mean": mean.tolist(),
            "feature_std": std.tolist(),
            "centers_standardized": centers.tolist(),
            "centers_original_units": centers_original.tolist(),
            "valid_pixels": valid_pixels,
            "training_sample_pixels": actual_sample_size,
            "iterations": iterations,
            "inertia": inertia,
            "nodata_label": 0,
        },
    )

    print(f"Classification raster written to: {args.output_raster}")
    print(f"Class report written to: {args.report_csv}")
    print(f"Model metadata written to: {args.model_json}")


if __name__ == "__main__":
    main()
