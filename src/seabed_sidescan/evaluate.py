from __future__ import annotations

import argparse
import csv
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)

from .classify import (
    read_training_data,
    standardize,
    validate_cluster_count,
    validate_inputs,
)
from .io import atomic_output, validate_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate candidate KMeans class counts on a masked feature stack."
    )
    parser.add_argument("--feature-stack", required=True, type=Path)
    parser.add_argument("--mask-raster", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--summary-txt", required=True, type=Path)
    parser.add_argument("--classes", required=True, nargs="+", type=int)
    parser.add_argument("--sample-size", type=int, default=200000)
    parser.add_argument("--metric-sample-size", type=int, default=5000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--n-init", type=int, default=50)
    parser.add_argument("--max-iterations", type=int, default=500)
    parser.add_argument("--tolerance", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-standardize", action="store_true")
    return parser.parse_args(argv)


def fit_model(values, classes, n_init, max_iterations, tolerance, seed):
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
    return model


def metric_subset(values, sample_size, seed):
    if values.shape[0] <= sample_size:
        return values
    rng = np.random.default_rng(seed)
    indices = rng.choice(values.shape[0], size=sample_size, replace=False)
    return values[indices]


def safe_metrics(values, labels):
    unique = np.unique(labels)
    if unique.size < 2 or unique.size >= labels.size:
        return {"silhouette": "", "calinski_harabasz": "", "davies_bouldin": ""}

    return {
        "silhouette": float(silhouette_score(values, labels)),
        "calinski_harabasz": float(calinski_harabasz_score(values, labels)),
        "davies_bouldin": float(davies_bouldin_score(values, labels)),
    }


def class_balance(labels, classes):
    counts = np.bincount(labels, minlength=classes)
    total = counts.sum()
    percentages = counts / total * 100.0 if total else np.zeros(classes)
    return {
        "min_class_percent": float(np.min(percentages)),
        "max_class_percent": float(np.max(percentages)),
        "smallest_class": int(np.argmin(percentages) + 1),
        "largest_class": int(np.argmax(percentages) + 1),
    }


def stability_score(label_sets):
    if len(label_sets) < 2:
        return ""
    scores = [
        adjusted_rand_score(left, right)
        for left, right in combinations(label_sets, 2)
    ]
    return float(np.mean(scores)) if scores else ""


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "classes",
        "run",
        "seed",
        "inertia",
        "iterations",
        "silhouette",
        "calinski_harabasz",
        "davies_bouldin",
        "min_class_percent",
        "max_class_percent",
        "smallest_class",
        "largest_class",
        "stability_adjusted_rand_mean",
    ]
    with atomic_output(path) as staged, staged.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean_numeric(rows, key):
    values = [row[key] for row in rows if row.get(key) != ""]
    return float(np.mean(values)) if values else None


def write_summary(path, rows, classes):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Cluster Evaluation Summary",
        "",
        "Interpretation guide:",
        "- Lower inertia is expected as k increases; use it mainly for the elbow pattern.",
        "- Higher silhouette is better.",
        "- Higher Calinski-Harabasz is better.",
        "- Lower Davies-Bouldin is better.",
        "- Higher stability_adjusted_rand_mean is better.",
        "- Avoid tiny classes unless they map to a meaningful acoustic feature.",
        "",
    ]

    for k in classes:
        subset = [row for row in rows if row["classes"] == k]
        if not subset:
            continue
        lines.append(f"k={k}")
        for key in [
            "inertia",
            "silhouette",
            "calinski_harabasz",
            "davies_bouldin",
            "min_class_percent",
            "max_class_percent",
            "stability_adjusted_rand_mean",
        ]:
            value = mean_numeric(subset, key)
            if value is not None:
                lines.append(f"  mean_{key}: {value:.6f}")
        lines.append("")

    with atomic_output(path) as staged:
        staged.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    validate_paths([args.feature_stack, args.mask_raster], [args.output_csv, args.summary_txt])
    classes = sorted(set(args.classes))
    if any(k < 2 for k in classes):
        raise ValueError("All class counts must be at least 2.")
    if args.runs < 1:
        raise ValueError("--runs must be at least 1.")
    if args.sample_size < 1 or args.metric_sample_size < 2:
        raise ValueError("--sample-size must be at least 1 and --metric-sample-size at least 2.")
    if args.n_init < 1 or args.max_iterations < 1:
        raise ValueError("--n-init and --max-iterations must be at least 1.")
    if not np.isfinite(args.tolerance) or args.tolerance < 0:
        raise ValueError("--tolerance must be a finite, nonnegative number.")

    validate_inputs(args.feature_stack, args.mask_raster, max(classes))
    sample, valid_pixels, actual_sample_size = read_training_data(
        args.feature_stack,
        args.mask_raster,
        args.sample_size,
        args.seed,
    )
    sample_for_fit, _, _ = standardize(sample, enabled=not args.no_standardize)
    validate_cluster_count(sample_for_fit, max(classes))
    metric_values = metric_subset(sample_for_fit, args.metric_sample_size, args.seed + 1000)

    print(f"Feature stack: {args.feature_stack}")
    print(f"Mask raster: {args.mask_raster}")
    print(f"Valid pixels: {valid_pixels:,}")
    print(f"Training sample pixels: {actual_sample_size:,}")
    print(f"Metric sample pixels: {metric_values.shape[0]:,}")
    print(f"Classes to evaluate: {classes}")
    print(f"Runs per k: {args.runs}")
    print(f"KMeans n_init: {args.n_init}")

    rows = []
    for k in classes:
        print(f"Evaluating k={k}")
        metric_label_sets = []
        pending_rows = []
        for run_index in range(1, args.runs + 1):
            run_seed = args.seed + run_index - 1
            print(f"  run {run_index}/{args.runs}, seed={run_seed}")
            model = fit_model(
                sample_for_fit,
                k,
                args.n_init,
                args.max_iterations,
                args.tolerance,
                run_seed,
            )
            labels_fit = model.labels_
            labels_metric = model.predict(metric_values)
            metric_label_sets.append(labels_metric)

            row = {
                "classes": k,
                "run": run_index,
                "seed": run_seed,
                "inertia": float(model.inertia_),
                "iterations": int(model.n_iter_),
            }
            row.update(safe_metrics(metric_values, labels_metric))
            row.update(class_balance(labels_fit, k))
            pending_rows.append(row)

        stability = stability_score(metric_label_sets)
        for row in pending_rows:
            row["stability_adjusted_rand_mean"] = stability
        rows.extend(pending_rows)

    write_csv(args.output_csv, rows)
    write_summary(args.summary_txt, rows, classes)
    print(f"Evaluation CSV written to: {args.output_csv}")
    print(f"Evaluation summary written to: {args.summary_txt}")


if __name__ == "__main__":
    main()

