"""Independent per-window references for texture definitions and precision."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from skimage.feature import graycomatrix, graycoprops

from seabed_sidescan import texture
from seabed_sidescan.texture import (
    local_entropy,
    local_glcm_features,
    masked_local_mean_variance,
    quantize,
)


def brute_glcm(q, valid, levels, window_size, directions):
    """Explicit endpoint enumeration, without any spatial filtering/shifting."""
    outputs = np.full((4, *q.shape), np.nan)
    radius = window_size // 2
    indices = np.arange(levels)
    squared_difference = (indices[:, None] - indices[None, :]) ** 2
    for row, col in np.ndindex(q.shape):
        if not valid[row, col]:
            continue
        y0, y1 = max(0, row - radius), min(q.shape[0], row + radius + 1)
        x0, x1 = max(0, col - radius), min(q.shape[1], col + radius + 1)
        properties = []
        for dy, dx in directions:
            counts = np.zeros((levels, levels), dtype=np.int64)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    ny, nx = y + dy, x + dx
                    if y0 <= ny < y1 and x0 <= nx < x1 and valid[y, x] and valid[ny, nx]:
                        counts[q[y, x], q[ny, nx]] += 1
            if counts.sum():
                probability = counts / counts.sum()
                properties.append([
                    np.sum(probability * squared_difference),
                    np.sum(probability / (1 + squared_difference)),
                    np.sum(probability ** 2),
                ])
        if properties:
            outputs[:3, row, col] = np.mean(properties, axis=0)
            outputs[3, row, col] = np.sqrt(outputs[2, row, col])
    return outputs


@pytest.mark.parametrize("window_size", [3, 5, 9])
@pytest.mark.parametrize("directions", [((0, 1),), ((1, -1),), ((-2, 1), (1, -3)),
                                         ((0, 1), (1, 0), (1, 1), (1, -1), (20, 0))])
def test_glcm_matches_endpoint_reference_at_masks_borders_and_offsets(window_size, directions):
    rng = np.random.default_rng(715)
    q = rng.integers(0, 4, size=(7, 8), dtype="uint8")
    valid = rng.random(q.shape) > 0.3
    valid[0, 0] = valid[-1, -1] = True
    expected = brute_glcm(q, valid, 4, window_size, directions)
    actual = np.asarray(local_glcm_features(q, valid, 4, window_size, directions))
    np.testing.assert_allclose(actual, expected, atol=2e-7, rtol=2e-7, equal_nan=True)


def test_glcm_matches_skimage_on_fully_valid_focal_window():
    q = np.array([[0, 1, 1, 2, 3], [1, 1, 2, 2, 3], [0, 2, 1, 3, 2],
                  [3, 2, 0, 1, 0], [2, 3, 1, 0, 1]], dtype="uint8")
    glcm = graycomatrix(q, [1], [0, np.pi / 2], levels=4, symmetric=False, normed=True)
    expected = [graycoprops(glcm, prop).mean() for prop in ("contrast", "homogeneity", "ASM")]
    expected.append(np.sqrt(expected[2]))
    actual = local_glcm_features(q, np.ones(q.shape, bool), 4, 5, [(0, 1), (1, 0)])
    np.testing.assert_allclose([array[2, 2] for array in actual], expected, rtol=1e-7)


def test_glcm_excludes_neighbors_outside_focal_window():
    q = np.zeros((3, 5), dtype="uint8")
    q[:, 0] = 1
    contrast, _, _, _ = local_glcm_features(q, np.ones(q.shape, bool), 2, 3, [(0, 1)])
    # The centre's 3x3 window is columns 1..3, all zero. Column 0 must not
    # contribute a pair, even though an endpoint in column 1 is in the window.
    assert contrast[1, 2] == 0


def test_glcm_returns_nan_without_pairs_and_rejects_zero_directions():
    q = np.zeros((3, 3), dtype="uint8")
    valid = np.eye(3, dtype=bool)
    actual = local_glcm_features(q, valid, 2, 3, [(0, 1), (30, 0)])
    assert all(np.isnan(array).all() for array in actual)
    for directions in ([], [(0, 0)]):
        with pytest.raises(ValueError, match="direction|offset"):
            local_glcm_features(q, valid, 2, 3, directions)


def test_local_moments_preserve_small_variance_at_large_offset():
    data = (1_000_000 + np.arange(35).reshape(5, 7) / 8).astype("float64")
    valid = np.ones(data.shape, dtype=bool)
    valid[1, 2] = False
    data[1, 2] = np.nan
    mean, variance, std = masked_local_mean_variance(data, valid, 3)
    for row, col in np.ndindex(data.shape):
        if not valid[row, col]:
            assert np.isnan(mean[row, col]) and np.isnan(variance[row, col])
            continue
        sub = data[max(0, row - 1):row + 2, max(0, col - 1):col + 2]
        values = sub[np.isfinite(sub)]
        assert mean[row, col] == pytest.approx(values.mean(), abs=0.04)
        assert variance[row, col] == pytest.approx(values.var(), rel=2e-7)
        assert std[row, col] == pytest.approx(values.std(), rel=2e-7)


def test_constant_quantization_and_entropy_are_defined():
    data = np.full((5, 5), 9.0)
    valid = np.ones(data.shape, dtype=bool)
    q, low, high = quantize(data, valid, 4)
    assert low == high == 9
    np.testing.assert_array_equal(q, 0)
    np.testing.assert_array_equal(local_entropy(q, valid, 3), 0)
    actual = local_glcm_features(q, valid, 4, 3, [(0, 1)])
    np.testing.assert_array_equal(actual[0], 0)
    for array in actual[1:]:
        np.testing.assert_array_equal(array, 1)


def test_local_moments_preserve_low_variance_despite_distant_large_intensities():
    data = np.tile(np.arange(12, dtype="float64") / 8, (5, 1))
    data[:, 7:] += 1e12
    mean, variance, std = masked_local_mean_variance(data, np.ones(data.shape, bool), 3)
    for row, col in np.ndindex(data.shape):
        sub = data[max(0, row - 1):row + 2, max(0, col - 1):col + 2]
        assert variance[row, col] == pytest.approx(sub.var(), rel=1e-6, abs=1e-8)
        assert std[row, col] == pytest.approx(sub.std(), rel=1e-6, abs=1e-8)
    assert mean[2, 1] == pytest.approx(0.125)


def test_entropy_is_shannon_bits_of_masked_partial_window():
    q = np.array([[0, 0, 1], [1, 2, 3], [2, 3, 3]], dtype="uint8")
    valid = np.ones(q.shape, dtype=bool)
    valid[1, 1] = False
    actual = local_entropy(q, valid, 3)
    for row, col in np.ndindex(q.shape):
        if not valid[row, col]:
            assert np.isnan(actual[row, col])
            continue
        ys, xs = slice(max(0, row - 1), row + 2), slice(max(0, col - 1), col + 2)
        counts = np.bincount(q[ys, xs][valid[ys, xs]], minlength=4)
        probabilities = counts[counts > 0] / counts.sum()
        assert actual[row, col] == pytest.approx(-np.sum(probabilities * np.log2(probabilities)))


def test_quantization_validates_empty_mask_bounds_and_upper_bin():
    data = np.array([[0.0, 1.0, np.nan]])
    valid = np.array([[True, True, True]])
    q, _, _ = quantize(data, valid, 256, 0, 100)
    np.testing.assert_array_equal(q, [[0, 255, 0]])
    with pytest.raises(ValueError, match="No valid"):
        quantize(data, np.zeros(data.shape, bool), 4)
    with pytest.raises(ValueError, match="percentiles"):
        quantize(data, valid, 4, np.nan, 100)


def write_texture_raster(path, data, nodata=None):
    with rasterio.open(path, "w", driver="GTiff", count=1, height=data.shape[0], width=data.shape[1],
                       dtype=data.dtype, transform=from_origin(500000, 1000, 1, 1),
                       crs="EPSG:32632", nodata=nodata) as dst:
        dst.write(data, 1)
    return path


def test_mask_nodata_value_one_is_excluded_from_texture_inputs(tmp_path):
    source = write_texture_raster(tmp_path / "input.tif", np.ones((3, 3), dtype="float32"))
    mask = write_texture_raster(tmp_path / "mask.tif", np.ones((3, 3), dtype="uint8"), nodata=1)
    _, valid, _ = texture.read_inputs(source, mask)
    assert not valid.any()


@pytest.mark.parametrize("mask_values", [np.full((3, 3), 2, dtype="uint8"),
                                         np.ones((3, 3), dtype="complex64")])
def test_texture_rejects_nonbinary_and_complex_analysis_masks(tmp_path, mask_values):
    source = write_texture_raster(tmp_path / "input.tif", np.ones((3, 3), dtype="float32"))
    mask = write_texture_raster(tmp_path / "mask.tif", mask_values)
    with pytest.raises(ValueError, match="0 and 1|real"):
        texture.read_inputs(source, mask)


@pytest.mark.parametrize("failure", ["empty_mask", "late_writer"])
def test_failed_texture_run_preserves_previous_products(tmp_path, monkeypatch, failure):
    data = np.arange(25, dtype="float32").reshape(5, 5)
    source = write_texture_raster(tmp_path / "input.tif", data)
    mask_values = np.zeros(data.shape, dtype="uint8") if failure == "empty_mask" else np.ones(data.shape, dtype="uint8")
    mask = write_texture_raster(tmp_path / "mask.tif", mask_values, nodata=0)
    outputs = tmp_path / "textures"
    outputs.mkdir()
    previous = outputs / "SSS_mean.tif"
    previous.write_bytes(b"previous successful mean")
    if failure == "late_writer":
        original = texture.write_float_raster

        def fail_late(path, array, profile):
            if path.name == "SSS_ASM.tif":
                raise OSError("simulated later texture writer failure")
            return original(path, array, profile)

        monkeypatch.setattr(texture, "write_float_raster", fail_late)
    with pytest.raises((ValueError, OSError)):
        texture.main(["--input-raster", str(source), "--mask-raster", str(mask),
                      "--output-dir", str(outputs), "--window-size", "3", "--levels", "4"])
    assert previous.read_bytes() == b"previous successful mean"
    assert sorted(path.name for path in outputs.iterdir()) == ["SSS_mean.tif"]
