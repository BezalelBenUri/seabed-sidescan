from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from .io import atomic_output, validate_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Conservatively clean a classified acoustic facies raster."
    )
    parser.add_argument("--input-raster", required=True, type=Path)
    parser.add_argument("--output-raster", required=True, type=Path)
    parser.add_argument("--report-txt", required=True, type=Path)
    parser.add_argument("--majority-size", type=int, default=3)
    parser.add_argument("--min-patch-size", type=int, default=25)
    parser.add_argument("--nodata-label", type=int, default=0)
    return parser.parse_args(argv)


def validate_args(args):
    if args.majority_size < 3:
        raise ValueError("--majority-size must be at least 3.")
    if args.majority_size % 2 == 0:
        raise ValueError("--majority-size must be odd, for example 3 or 5.")
    if args.min_patch_size < 1:
        raise ValueError("--min-patch-size must be at least 1.")
    if args.nodata_label < 0 or args.nodata_label > 255:
        raise ValueError("--nodata-label must fit in uint8 range 0-255.")


def local_majority(values, nodata_label=0):
    values = values.astype("int32", copy=False)
    center = int(values[values.size // 2])
    if center == nodata_label:
        return nodata_label

    valid = values[values != nodata_label]
    if valid.size == 0:
        return center

    counts = np.bincount(valid)
    majority = int(np.argmax(counts))
    majority_count = int(counts[majority])
    if majority_count > valid.size / 2.0:
        return majority
    return center


def majority_filter(classified, valid, size, nodata_label=0):
    filtered = ndimage.generic_filter(
        classified,
        function=local_majority,
        size=size,
        mode="constant",
        cval=nodata_label,
        extra_arguments=(nodata_label,),
    ).astype("uint8")
    filtered[~valid] = nodata_label
    return filtered


def most_common_neighbor(array, component, nodata_label):
    dilated = ndimage.binary_dilation(component, structure=np.ones((3, 3), dtype=bool))
    ring = dilated & ~component
    neighbor_values = array[ring]
    neighbor_values = neighbor_values[neighbor_values != nodata_label]
    if neighbor_values.size == 0:
        return None
    counts = np.bincount(neighbor_values.astype("int32"))
    winner = int(np.argmax(counts))
    return winner if counts[winner] > neighbor_values.size / 2 else None


def remove_small_patches(classified, valid, min_patch_size, nodata_label):
    cleaned = classified.copy()
    removed_by_class: dict[int, int] = {}
    patch_count_by_class: dict[int, int] = {}
    structure = np.ones((3, 3), dtype=bool)

    classes = sorted(int(value) for value in np.unique(cleaned) if int(value) != nodata_label)
    for class_value in classes:
        # All decisions use the same pre-cleanup labels, so changing numeric
        # class identifiers cannot change the spatial cleanup result.
        class_mask = (classified == class_value) & valid
        labels, num_labels = ndimage.label(class_mask, structure=structure)
        patch_count_by_class[class_value] = int(num_labels)

        if num_labels == 0:
            continue

        sizes = np.bincount(labels.ravel())
        component_slices = ndimage.find_objects(labels, max_label=num_labels)
        for label_value, bounds in enumerate(component_slices, start=1):
            patch_size = int(sizes[label_value])
            if patch_size >= min_patch_size:
                continue
            # A one-cell halo contains the entire 8-connected neighbour ring.
            # Comparing/dilating the full survey for every small island makes
            # cleanup proportional to image size times number of components.
            # Keep decisions on the immutable input labels, while limiting
            # each comparison and dilation to its component and halo.
            neighborhood = tuple(slice(max(0, axis.start - 1), min(length, axis.stop + 1))
                                 for axis, length in zip(bounds, labels.shape, strict=True))
            component = labels[neighborhood] == label_value
            replacement = most_common_neighbor(classified[neighborhood], component, nodata_label)
            if replacement is None:
                continue

            cleaned_view = cleaned[neighborhood]
            cleaned_view[component] = replacement
            removed_by_class[class_value] = removed_by_class.get(class_value, 0) + patch_size

    cleaned[~valid] = nodata_label
    return cleaned, patch_count_by_class, removed_by_class


def class_counts(array, nodata_label):
    rows = []
    for value in sorted(int(item) for item in np.unique(array)):
        if value == nodata_label:
            continue
        rows.append((value, int(np.sum(array == value))))
    return rows


def write_report(
    path,
    *,
    input_raster,
    output_raster,
    majority_size,
    min_patch_size,
    before_counts,
    after_counts,
    patch_count_by_class,
    removed_by_class,
    nodata_label=0,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Classification Cleanup Report",
        "",
        f"Input raster: {input_raster}",
        f"Output raster: {output_raster}",
        f"Majority filter size: {majority_size} x {majority_size}",
        f"Minimum patch size retained: {min_patch_size} pixels",
        "",
        "Method:",
        f"1. Class {nodata_label} / NoData was preserved.",
        "2. One local majority-filter pass was applied.",
        "3. Connected patches smaller than the threshold were replaced by the surrounding majority class.",
        "",
        "Class counts before cleanup:",
    ]
    for class_value, count in before_counts:
        lines.append(f"  class {class_value}: {count} pixels")

    lines.append("")
    lines.append("Class counts after cleanup:")
    for class_value, count in after_counts:
        lines.append(f"  class {class_value}: {count} pixels")

    lines.append("")
    lines.append("Connected patches detected after majority filter:")
    for class_value in sorted(patch_count_by_class):
        lines.append(f"  class {class_value}: {patch_count_by_class[class_value]} patches")

    lines.append("")
    lines.append("Small-patch pixels replaced:")
    if removed_by_class:
        for class_value in sorted(removed_by_class):
            lines.append(f"  class {class_value}: {removed_by_class[class_value]} pixels")
    else:
        lines.append("  none")

    with atomic_output(path) as staged:
        staged.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    validate_paths([args.input_raster], [args.output_raster, args.report_txt])
    validate_args(args)

    with rasterio.open(args.input_raster) as src:
        if src.count != 1:
            raise ValueError("Classification raster must have exactly one band.")
        data = src.read(1, masked=True)
        profile = src.profile.copy()

    source_valid = ~np.ma.getmaskarray(data)
    source_values = np.asarray(data)[source_valid]
    if (
        not np.all(np.isfinite(source_values))
        or np.any(source_values < 0)
        or np.any(source_values > 255)
        or np.any(source_values != np.floor(source_values))
    ):
        raise ValueError("Classification values must be integer labels between 0 and 255.")
    classified = np.where(source_valid, np.asarray(data), args.nodata_label).astype("uint8")
    valid = source_valid & (classified != args.nodata_label)
    if not np.any(valid):
        raise ValueError("Classification raster contains no valid class pixels.")
    before_counts = class_counts(classified, args.nodata_label)

    print(f"Input raster: {args.input_raster}")
    print(f"Output raster: {args.output_raster}")
    print(f"Majority filter: {args.majority_size} x {args.majority_size}")
    print(f"Minimum patch size: {args.min_patch_size} pixels")

    majority = majority_filter(classified, valid, args.majority_size, args.nodata_label)
    cleaned, patch_count_by_class, removed_by_class = remove_small_patches(
        majority,
        valid,
        args.min_patch_size,
        args.nodata_label,
    )
    after_counts = class_counts(cleaned, args.nodata_label)

    profile.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "uint8",
            "nodata": args.nodata_label,
            "compress": "deflate",
            "predictor": 1,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "BIGTIFF": "IF_SAFER",
        }
    )
    args.output_raster.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(args.output_raster) as staged, rasterio.open(staged, "w", **profile) as dst:
        dst.write(cleaned, 1)

    write_report(
        args.report_txt,
        input_raster=args.input_raster,
        output_raster=args.output_raster,
        majority_size=args.majority_size,
        min_patch_size=args.min_patch_size,
        before_counts=before_counts,
        after_counts=after_counts,
        patch_count_by_class=patch_count_by_class,
        removed_by_class=removed_by_class,
        nodata_label=args.nodata_label,
    )

    print(f"Cleaned raster written to: {args.output_raster}")
    print(f"Cleanup report written to: {args.report_txt}")


if __name__ == "__main__":
    main()

