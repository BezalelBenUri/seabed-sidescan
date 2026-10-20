import argparse
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage
from skimage.filters import rank

from .io import atomic_output, validate_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract texture features from a sidescan mosaic."
    )
    parser.add_argument("--input-raster", required=True, type=Path)
    parser.add_argument("--mask-raster", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-size", type=int, default=15)
    parser.add_argument("--levels", type=int, default=16)
    parser.add_argument(
        "--low-percentile",
        type=float,
        default=2.0,
        help="Lower valid-pixel percentile used to quantize data for entropy/GLCM.",
    )
    parser.add_argument(
        "--high-percentile",
        type=float,
        default=98.0,
        help="Upper valid-pixel percentile used to quantize data for entropy/GLCM.",
    )
    parser.add_argument(
        "--directions",
        default="0,1;1,0;1,1;1,-1",
        help="Semicolon-separated dy,dx offsets for local GLCM features.",
    )
    return parser.parse_args(argv)


def parse_directions(text):
    directions = []
    for item in text.split(";"):
        item = item.strip()
        if not item:
            continue
        dy_text, dx_text = item.split(",")
        directions.append((int(dy_text), int(dx_text)))
    if not directions:
        raise ValueError("At least one direction is required.")
    if (0, 0) in directions:
        raise ValueError("Texture directions must have a nonzero offset.")
    if len(set(directions)) != len(directions):
        raise ValueError("Texture directions must not contain duplicates.")
    if len(directions) > 255:
        raise ValueError("At most 255 texture directions are supported.")
    return directions


def validate_window_size(window_size):
    if not isinstance(window_size, (int, np.integer)):
        raise ValueError("--window-size must be an integer.")
    if window_size < 3:
        raise ValueError("--window-size must be at least 3.")
    if window_size % 2 == 0:
        raise ValueError("--window-size must be odd, for example 7, 11, 15, or 21.")


def read_inputs(input_raster, mask_raster):
    with rasterio.open(input_raster) as src:
        if src.count != 1 or np.issubdtype(np.dtype(src.dtypes[0]), np.complexfloating):
            raise ValueError("Texture input must be a single-band real intensity raster.")
        data = src.read(1, masked=True).astype("float64")
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs
        shape = data.shape

    with rasterio.open(mask_raster) as mask_src:
        if mask_src.count != 1:
            raise ValueError("Texture mask must have exactly one band.")
        if np.issubdtype(np.dtype(mask_src.dtypes[0]), np.complexfloating):
            raise ValueError("Texture mask must contain real 0 and 1 values.")
        if mask_src.shape != shape:
            raise ValueError(
                f"Mask shape {mask_src.shape} does not match input shape {shape}."
            )
        if mask_src.transform != transform:
            raise ValueError("Mask transform does not match input raster transform.")
        if mask_src.crs != crs:
            raise ValueError("Mask CRS does not match input raster CRS.")
        mask_values = mask_src.read(1, masked=True)
        values = mask_values.compressed()
        if np.any((values != 0) & (values != 1)):
            raise ValueError("Texture mask must contain only 0 and 1.")
        mask = np.ma.filled(mask_values == 1, False)

    arr = np.ma.filled(data, np.nan)
    valid = mask & np.isfinite(arr)
    return arr, valid, profile


def write_float_raster(path, array, profile):
    path.parent.mkdir(parents=True, exist_ok=True)
    out_profile = profile.copy()
    out_profile.update(
        {
            "driver": "GTiff",
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
    finite = array[np.isfinite(array)]
    if np.isinf(array).any() or np.any(np.abs(finite) > np.finfo(np.float32).max):
        raise ValueError(f"Texture values cannot be represented as float32: {path.name}")
    with atomic_output(path) as staged:
        with rasterio.open(staged, "w", **out_profile) as dst:
            dst.write(array.astype("float32"), 1)


def masked_local_mean_variance(data, valid, window_size):
    """Population moments over valid cells in clipped, centred square windows.

    Centre the data before accumulating second moments, and accumulate in
    float64: raw float32 E[x**2] - E[x]**2 can erase small real variances.
    Outputs are float32, with NaN at invalid focal cells.
    """
    valid = np.asarray(valid, dtype=bool) & np.isfinite(data)
    validate_window_size(window_size)
    data = np.asarray(data, dtype="float64")
    if np.any(np.abs(data[valid]) > np.finfo(np.float32).max):
        raise ValueError("Texture intensities cannot be represented as float32.")
    valid_f = valid.astype("float64")
    offset = float(np.mean(np.asarray(data)[valid], dtype="float64")) if valid.any() else 0.0
    data_f = np.where(valid, np.asarray(data, dtype="float64") - offset, 0.0)

    valid_density = ndimage.uniform_filter(
        valid_f, size=window_size, mode="constant", cval=0.0
    )
    sum_x = ndimage.uniform_filter(data_f, size=window_size, mode="constant", cval=0.0)
    sum_x2 = ndimage.uniform_filter(
        data_f * data_f, size=window_size, mode="constant", cval=0.0
    )

    mean = np.full(data.shape, np.nan, dtype="float64")
    variance = np.full(data.shape, np.nan, dtype="float64")
    local_valid = valid_density > 0

    centred_mean = sum_x[local_valid] / valid_density[local_valid]
    mean[local_valid] = centred_mean + offset
    second_moment = np.zeros(data.shape, dtype="float64")
    second_moment[local_valid] = sum_x2[local_valid] / valid_density[local_valid]
    variance[local_valid] = second_moment[local_valid] - centred_mean * centred_mean
    # A global offset stabilizes ordinary sonar intensities, but distant
    # regions with very different means can still cancel small local variance.
    # Recompute only those suspect windows around their own focal-cell value.
    unstable = valid & (second_moment > 0) & (variance <= 64 * np.finfo(np.float64).eps * second_moment)
    if unstable.any():
        rows, cols = np.nonzero(unstable)
        radius = window_size // 2
        for start in range(0, len(rows), 65536):
            ys, xs = rows[start:start + 65536], cols[start:start + 65536]
            reference = data[ys, xs]
            delta_sum = np.zeros(reference.size)
            delta2_sum = np.zeros(reference.size)
            counts = np.zeros(reference.size, dtype="int64")
            for dy in range(-radius, radius + 1):
                ny = np.clip(ys + dy, 0, data.shape[0] - 1)
                for dx in range(-radius, radius + 1):
                    nx = np.clip(xs + dx, 0, data.shape[1] - 1)
                    usable = ((ys + dy >= 0) & (ys + dy < data.shape[0]) &
                              (xs + dx >= 0) & (xs + dx < data.shape[1]) & valid[ny, nx])
                    delta = data[ny[usable], nx[usable]] - reference[usable]
                    delta_sum[usable] += delta
                    delta2_sum[usable] += delta * delta
                    counts[usable] += 1
            local_delta_mean = delta_sum / counts
            mean[ys, xs] = reference + local_delta_mean
            variance[ys, xs] = delta2_sum / counts - local_delta_mean ** 2
    variance = np.maximum(variance, 0.0)
    if np.any(variance[valid] > np.finfo(np.float32).max):
        raise ValueError("Texture variance cannot be represented as float32.")
    std = np.sqrt(variance).astype("float32")

    mean[~valid] = np.nan
    variance[~valid] = np.nan
    std[~valid] = np.nan
    return mean.astype("float32"), variance.astype("float32"), std


def quantize(data, valid, levels, low_percentile=2.0, high_percentile=98.0):
    if not isinstance(levels, (int, np.integer)) or not 2 <= levels <= 256:
        raise ValueError("Quantization levels must be an integer between 2 and 256.")
    if not 0 <= low_percentile < high_percentile <= 100:
        raise ValueError("Quantization percentiles must satisfy 0 <= low < high <= 100.")
    valid = np.asarray(valid, dtype=bool) & np.isfinite(data)
    values = data[valid & np.isfinite(data)]
    if values.size == 0:
        raise ValueError("No valid pixels available for quantization.")

    low = float(np.percentile(values, low_percentile))
    high = float(np.percentile(values, high_percentile))
    if not np.isfinite(low) or not np.isfinite(high) or high < low:
        raise ValueError(
            "Invalid quantization percentile range. "
            f"Computed low={low!r}, high={high!r}."
        )

    q = np.zeros(data.shape, dtype="uint8")
    # Constant imagery has a well-defined one-bin distribution: entropy and
    # contrast are zero; homogeneity, ASM, and energy are one.
    if high == low:
        if values.min() != values.max():
            raise ValueError("Quantization percentile bounds collapse for nonconstant data; choose a wider percentile range.")
        return q, low, high
    scaled = np.clip((data[valid].astype("float64") - low) / (high - low), 0.0, 1.0)
    q[valid] = np.minimum(
        np.floor(scaled * levels), levels - 1
    ).astype("uint8")
    return q, low, high


def shift_array(array, dy, dx, fill_value=0):
    shifted = np.full(array.shape, fill_value, dtype=array.dtype)
    if abs(dy) >= array.shape[0] or abs(dx) >= array.shape[1]:
        return shifted

    if dy >= 0:
        src_y = slice(0, array.shape[0] - dy)
        dst_y = slice(dy, array.shape[0])
    else:
        src_y = slice(-dy, array.shape[0])
        dst_y = slice(0, array.shape[0] + dy)

    if dx >= 0:
        src_x = slice(0, array.shape[1] - dx)
        dst_x = slice(dx, array.shape[1])
    else:
        src_x = slice(-dx, array.shape[1])
        dst_x = slice(0, array.shape[1] + dx)

    shifted[dst_y, dst_x] = array[src_y, src_x]
    return shifted


def local_entropy(q, valid, window_size):
    """Shannon entropy in bits of valid quantized cells in each local window."""
    footprint = np.ones((window_size, window_size), dtype=bool)
    entropy = rank.entropy(q, footprint=footprint, mask=valid.astype("uint8")).astype(
        "float32"
    )
    entropy[~valid] = np.nan
    return entropy


def local_glcm_features(q, valid, levels, window_size, directions):
    """GLCM properties with both pair endpoints inside each focal window.

    Each offset creates a directed, normalized co-occurrence distribution;
    reverse pairs are not added implicitly. Contrast, homogeneity, and ASM
    (sum of squared probabilities) are averaged equally over directions that
    have at least one valid pair. Energy is sqrt(mean directional ASM), rather
    than the mean of directional energies. Invalid focal cells and windows
    with no pairs produce NaN. Image edges clip the window, and masked cells
    never participate in pairs. Offsets use (row, column) pixel coordinates.
    """
    validate_window_size(window_size)
    try:
        directions = tuple(tuple(direction) for direction in directions)
    except TypeError as exc:
        raise ValueError("At least one integer dy,dx direction is required.") from exc
    if not directions or any(len(direction) != 2 or not all(isinstance(v, (int, np.integer)) for v in direction) for direction in directions):
        raise ValueError("At least one integer dy,dx direction is required.")
    if any(dy == 0 and dx == 0 for dy, dx in directions):
        raise ValueError("Texture directions must have a nonzero offset.")
    if len(set(directions)) != len(directions):
        raise ValueError("Texture directions must not contain duplicates.")
    if len(directions) > 255:
        raise ValueError("At most 255 texture directions are supported.")
    if q.ndim != 2 or q.shape != valid.shape or not np.issubdtype(q.dtype, np.integer):
        raise ValueError("Quantized texture data and mask must be matching 2D integer arrays.")
    if not isinstance(levels, (int, np.integer)) or not 2 <= levels <= 256:
        raise ValueError("GLCM levels must be an integer between 2 and 256.")
    valid = np.asarray(valid, dtype=bool)
    if np.any((q[valid] < 0) | (q[valid] >= levels)):
        raise ValueError("Quantized values must be between zero and levels - 1.")
    shape = q.shape
    contrast_sum = np.zeros(shape, dtype="float64")
    homogeneity_sum = np.zeros(shape, dtype="float64")
    asm_sum = np.zeros(shape, dtype="float64")
    direction_count = np.zeros(shape, dtype="uint8")

    for dy, dx in directions:
        if abs(dy) >= window_size or abs(dx) >= window_size:
            continue
        q_shift = shift_array(q, dy, dx, fill_value=0)
        valid_shift = shift_array(valid.astype("uint8"), dy, dx, fill_value=0) == 1
        pair_valid = valid & valid_shift
        # For an anchor a and its neighbour a-offset to both lie in the
        # centred window, the anchor range is asymmetric and shorter by the
        # absolute offset on each axis. A full square box would count pairs
        # whose neighbour falls outside the requested focal window.
        radius = window_size // 2
        rows, cols = np.arange(shape[0]), np.arange(shape[1])
        y0 = np.clip(rows - radius + max(dy, 0), 0, shape[0])
        y1 = np.clip(rows + radius + min(dy, 0) + 1, 0, shape[0])
        x0 = np.clip(cols - radius + max(dx, 0), 0, shape[1])
        x1 = np.clip(cols + radius + min(dx, 0) + 1, 0, shape[1])

        def pair_counts(pair, y0=y0, y1=y1, x0=x0, x1=x1):
            # Summed-area counts support arbitrary signed offsets and are
            # exact integers, including empty windows at image borders.
            integral = np.zeros((shape[0] + 1, shape[1] + 1), dtype="int64")
            np.cumsum(pair, axis=0, dtype="int64", out=integral[1:, 1:])
            np.cumsum(integral[1:, 1:], axis=1, out=integral[1:, 1:])
            return (
                integral[np.ix_(y1, x1)] - integral[np.ix_(y0, x1)]
                - integral[np.ix_(y1, x0)] + integral[np.ix_(y0, x0)]
            )

        denom = pair_counts(pair_valid)
        direction_ok = denom > 0

        contrast = np.zeros(shape, dtype="float64")
        homogeneity = np.zeros(shape, dtype="float64")
        asm = np.zeros(shape, dtype="float64")

        for i in range(levels):
            q_i = q == i
            if not np.any(q_i & pair_valid):
                continue
            for j in range(levels):
                pair = q_i & (q_shift == j) & pair_valid
                if not pair.any():
                    continue
                count = pair_counts(pair)
                p = np.zeros(shape, dtype="float64")
                p[direction_ok] = count[direction_ok] / denom[direction_ok]
                diff2 = float((i - j) ** 2)
                contrast += p * diff2
                homogeneity += p / (1.0 + diff2)
                asm += p * p

        contrast_sum[direction_ok] += contrast[direction_ok]
        homogeneity_sum[direction_ok] += homogeneity[direction_ok]
        asm_sum[direction_ok] += asm[direction_ok]
        direction_count[direction_ok] += 1

    ok = direction_count > 0
    contrast_out = np.full(shape, np.nan, dtype="float32")
    homogeneity_out = np.full(shape, np.nan, dtype="float32")
    asm_out = np.full(shape, np.nan, dtype="float32")

    contrast_out[ok] = contrast_sum[ok] / direction_count[ok]
    homogeneity_out[ok] = homogeneity_sum[ok] / direction_count[ok]
    asm_out[ok] = asm_sum[ok] / direction_count[ok]

    contrast_out[~valid] = np.nan
    homogeneity_out[~valid] = np.nan
    asm_out[~valid] = np.nan
    energy_out = np.sqrt(asm_out).astype("float32")

    return contrast_out, homogeneity_out, asm_out, energy_out


def main(argv=None):
    args = parse_args(argv)
    validate_window_size(args.window_size)
    if args.levels < 4 or args.levels > 32:
        raise ValueError("--levels should be between 4 and 32 for a feasible run.")
    if not (0 <= args.low_percentile < args.high_percentile <= 100):
        raise ValueError("Quantization percentiles must satisfy 0 <= low < high <= 100.")

    directions = parse_directions(args.directions)
    names = ("mean", "variance", "standard_deviation", "entropy", "contrast", "homogeneity", "ASM", "energy")
    outputs = tuple(args.output_dir / f"SSS_{name}.tif" for name in names)
    validate_paths([args.input_raster, args.mask_raster], outputs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input raster: {args.input_raster}")
    print(f"Mask raster: {args.mask_raster}")
    print(f"Output folder: {args.output_dir}")
    print(f"Window size: {args.window_size} x {args.window_size}")
    print(f"GLCM quantization levels: {args.levels}")
    print(
        "GLCM quantization percentiles: "
        f"{args.low_percentile:g}-{args.high_percentile:g}"
    )
    print(f"GLCM directions: {directions}")

    data, valid, profile = read_inputs(args.input_raster, args.mask_raster)
    valid_count = int(valid.sum())
    print(f"Valid analysis pixels: {valid_count:,}")

    print("Quantizing mosaic for entropy and GLCM features...")
    q, q_low, q_high = quantize(
        data,
        valid,
        args.levels,
        low_percentile=args.low_percentile,
        high_percentile=args.high_percentile,
    )
    print(f"Quantization data range: {q_low:.6g} to {q_high:.6g}")

    print("Calculating local mean, variance, and standard deviation...")
    mean, variance, std = masked_local_mean_variance(data, valid, args.window_size)

    print("Calculating local entropy...")
    entropy = local_entropy(q, valid, args.window_size)

    print("Calculating local GLCM contrast, homogeneity, ASM, and energy...")
    contrast, homogeneity, asm, energy = local_glcm_features(
        q, valid, args.levels, args.window_size, directions
    )
    arrays = (mean, variance, std, entropy, contrast, homogeneity, asm, energy)
    with tempfile.TemporaryDirectory(prefix=".seabed-textures-", dir=args.output_dir) as staging:
        staged = [Path(staging) / output.name for output in outputs]
        for path, array in zip(staged, arrays, strict=True):
            write_float_raster(path, array, profile)
        for path, output in zip(staged, outputs, strict=True):
            with atomic_output(output) as destination:
                path.replace(destination)

    print("Texture extraction complete.")


if __name__ == "__main__":
    main()
