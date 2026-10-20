"""Mosaic references based on explicit arithmetic and geometric distances."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from seabed_sidescan import mosaic


def write_raster(path, values, *, transform=None, nodata=np.nan, crs="EPSG:32632"):
    values = np.asarray(values)
    with rasterio.open(path, "w", driver="GTiff", count=1, width=values.shape[1], height=values.shape[0],
                       dtype=values.dtype, transform=transform or from_origin(500000, 1000, 1, 1),
                       crs=crs, nodata=nodata) as dst:
        dst.write(values, 1)
    return path


def brute_edge_distances(valid, sampling=(1.0, 1.0)):
    """Enumerate nearest invalid centres including the one-cell exterior."""
    distances = np.zeros(valid.shape)
    exterior = np.pad(valid, 1)
    invalid_cells = np.argwhere(~exterior) - 1
    for row, col in np.argwhere(valid):
        deltas = (invalid_cells - [row, col]) * np.asarray(sampling)
        distances[row, col] = np.sqrt(np.sum(deltas ** 2, axis=1)).min()
    return distances


@pytest.mark.parametrize("sampling", [(1.0, 1.0), (2.0, 0.5)])
def test_true_footprint_feather_matches_explicit_distance_on_diagonal_and_holes(sampling):
    y, x = np.indices((31, 31))
    valid = np.abs(y - x) <= 9
    valid[12:14, 12:14] = False
    arr = np.where(valid, 5.0, np.nan)
    distances = brute_edge_distances(valid, sampling)
    thickness = 2 * distances.max()
    expected = np.clip(distances / (thickness * 0.4), 0, 1)
    actual = mosaic.source_weight_array(arr, 40, sampling=sampling)
    np.testing.assert_allclose(actual, expected, atol=5e-8)
    assert actual[12, 12] == 0
    assert actual[10, 19] < actual[23, 23]


def test_footprint_trim_follows_occupied_cells_and_preserves_untrimmed_input():
    y, x = np.indices((31, 31))
    valid = np.abs(y - x) <= 9
    arr = np.where(valid, 5.0, np.nan)
    distances = brute_edge_distances(valid)
    expected = arr.copy()
    expected[distances <= distances.max() * 2 * 0.2] = np.nan
    actual = mosaic.apply_edge_trim(arr, 20)
    np.testing.assert_allclose(actual, expected, equal_nan=True)
    np.testing.assert_array_equal(np.isfinite(arr), valid)
    assert np.isnan(actual[15, 6])  # an interior raster column on a diagonal footprint edge
    assert actual[15, 15] == 5


def test_mosaic_preserves_fractional_native_grid_and_expected_overlap_mean(tmp_path):
    transform = from_origin(500000.25, 1000.75, 2, 3)
    a = np.array([[2, 4, 6], [8, np.nan, 12]], dtype="float32")
    b = np.array([[20, 40, 60], [80, 100, np.nan]], dtype="float32")
    first = write_raster(tmp_path / "a.tif", a, transform=transform)
    second = write_raster(tmp_path / "b.tif", b, transform=from_origin(500004.25, 997.75, 2, 3))
    output = mosaic.build_mean_mosaic([first, second], tmp_path / "mean.tif")
    expected = np.array([[2, 4, 6, np.nan, np.nan], [8, np.nan, 16, 40, 60],
                         [np.nan, np.nan, 80, 100, np.nan]], dtype="float32")
    counts = np.array([[1, 1, 1, 0, 0], [1, 0, 2, 1, 1], [0, 0, 1, 1, 0]], dtype="uint32")
    with rasterio.open(output) as src:
        assert src.transform == transform
        assert src.crs.to_epsg() == 32632
        assert src.dtypes == ("float32",)
        np.testing.assert_allclose(src.read(1), expected, equal_nan=True)
    with rasterio.open(tmp_path / "mean_overlap_count.tif") as src:
        assert src.transform == transform
        assert src.dtypes == ("uint32",)
        assert src.nodata == 0
        np.testing.assert_array_equal(src.read(1), counts)


def test_feathered_mean_matches_independent_weighted_arithmetic(tmp_path):
    a = np.ones((17, 17), dtype="float32") * 10
    b = np.ones((17, 17), dtype="float32") * 30
    b[:, :5] = np.nan
    b[7:9, 10:12] = np.nan
    paths = [write_raster(tmp_path / "a.tif", a), write_raster(tmp_path / "b.tif", b)]
    weights = []
    for arr in (a, b):
        distance = brute_edge_distances(np.isfinite(arr))
        weights.append(np.clip(distance / (2 * distance.max() * 0.4), 0, 1))
    denominator = weights[0] + weights[1]
    expected = (10 * weights[0] + 30 * weights[1]) / denominator
    output = mosaic.build_mean_mosaic(paths, tmp_path / "weighted.tif", feather_percent=40)
    with rasterio.open(output) as src:
        np.testing.assert_allclose(src.read(1), expected, rtol=1e-7)
    with rasterio.open(tmp_path / "weighted_overlap_count.tif") as src:
        np.testing.assert_array_equal(src.read(1), 1 + np.isfinite(b))


def test_fractionally_offset_strip_is_nearest_resampled_on_first_native_grid(tmp_path):
    first_transform = from_origin(500000.25, 1000.75, 1, 1)
    first = write_raster(tmp_path / "a.tif", np.array([[10, 20, 30]], dtype="float32"),
                         transform=first_transform)
    second = write_raster(tmp_path / "b.tif", np.array([[100, 200, 300]], dtype="float32"),
                          transform=from_origin(500000.65, 1000.75, 1, 1))
    output = mosaic.build_mean_mosaic([first, second], tmp_path / "offset.tif")
    with rasterio.open(output) as src:
        assert src.transform == first_transform
        np.testing.assert_allclose(src.read(1), [[55, 110, 165, np.nan]], equal_nan=True)


def test_balancing_preserves_expected_reference_midpoint_and_range(tmp_path):
    a = np.arange(25, dtype="float32").reshape(5, 5)
    b = 2 * a + 100
    paths = [write_raster(tmp_path / "a.tif", a), write_raster(tmp_path / "b.tif", b)]
    reference, rows = mosaic.compute_balance_reference(paths, 10, 50, 90)
    assert reference["mid"] == pytest.approx(68)
    assert reference["range"] == pytest.approx(28.8)
    assert [row["scale"] for row in rows] == pytest.approx([1.5, 0.75])
    output = mosaic.build_mean_mosaic(paths, tmp_path / "balanced.tif", mode="balanced",
                                      balance_reference=reference)
    with rasterio.open(output) as src:
        np.testing.assert_allclose(src.read(1), (a - 12) * 1.5 + 68, rtol=1e-7)


def test_low_level_mosaic_rejects_input_aliases_and_duplicate_strips(tmp_path):
    path = write_raster(tmp_path / "source.tif", np.arange(9, dtype="float32").reshape(3, 3))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="differ"):
        mosaic.build_mean_mosaic([path], path)
    with pytest.raises(ValueError, match="duplicates"):
        mosaic.build_mean_mosaic([path, path], tmp_path / "out.tif")
    assert path.read_bytes() == before
    count_collision = tmp_path / "out_overlap_count.tif"
    count_collision.hardlink_to(path)
    with pytest.raises(ValueError, match="differ"):
        mosaic.build_mean_mosaic([path], tmp_path / "out.tif")
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["empty", "unusable_normalization", "unsupported_mode"])
def test_no_usable_pixels_or_invalid_mode_preserves_previous_outputs(tmp_path, failure):
    values = np.full((5, 5), np.nan if failure == "empty" else 1.0, dtype="float32")
    source = write_raster(tmp_path / "source.tif", values)
    output = tmp_path / "result.tif"
    output.write_bytes(b"previous successful mosaic")
    count = tmp_path / "result_overlap_count.tif"
    count.write_bytes(b"previous overlap counts")
    mode = "normalized" if failure == "unusable_normalization" else "bad" if failure == "unsupported_mode" else "raw"
    with pytest.raises(ValueError):
        mosaic.build_mean_mosaic([source], output, mode=mode)
    assert output.read_bytes() == b"previous successful mosaic"
    assert count.read_bytes() == b"previous overlap counts"


def test_late_mosaic_failure_before_cleaning_preserves_all_previous_products(tmp_path, monkeypatch):
    sources, outputs = tmp_path / "strips", tmp_path / "mosaics"
    sources.mkdir()
    outputs.mkdir()
    write_raster(sources / "line_ch0_proc.tif", np.arange(100, dtype="float32").reshape(10, 10))
    previous = outputs / "SSS_combined_standard_mosaic.tif"
    previous.write_bytes(b"previous successful mosaic")
    original = mosaic.build_standard_mosaic
    calls = []

    def fail_late(paths, output, *args):
        calls.append(output)
        if len(calls) == 2:
            raise RuntimeError("simulated later product failure")
        return original(paths, output, *args)

    monkeypatch.setattr(mosaic, "build_standard_mosaic", fail_late)
    with pytest.raises(RuntimeError, match="later product"):
        mosaic.main(["--georef-dir", str(sources), "--output-dir", str(outputs),
                     "--report-dir", str(tmp_path / "reports"), "--channels", "0", "--clean-output"])
    assert previous.read_bytes() == b"previous successful mosaic"
    assert not (outputs / "SSS_ch0_standard_mosaic.tif").exists()
    assert not list(outputs.glob(".seabed-mosaics-*"))


def test_raster_writer_failure_preserves_both_previous_products(tmp_path, monkeypatch):
    path = write_raster(tmp_path / "source.tif", np.arange(9, dtype="float32").reshape(3, 3))
    output, count = tmp_path / "out.tif", tmp_path / "out_overlap_count.tif"
    output.write_bytes(b"previous mosaic")
    count.write_bytes(b"previous count")
    original = rasterio.open

    def fail_count_writer(path, mode="r", **kwargs):
        if mode == "w" and "overlap_count" in Path(path).name:
            raise OSError("simulated count write failure")
        return original(path, mode, **kwargs)

    monkeypatch.setattr(rasterio, "open", fail_count_writer)
    with pytest.raises(OSError, match="count write"):
        mosaic.build_mean_mosaic([path], output)
    assert output.read_bytes() == b"previous mosaic"
    assert count.read_bytes() == b"previous count"


def test_successful_rebuild_removes_obsolete_sidecar_mask(tmp_path):
    source = write_raster(tmp_path / "source.tif", np.arange(9, dtype="float32").reshape(3, 3))
    output = tmp_path / "out.tif"
    Path(str(output) + ".msk").write_bytes(b"obsolete external mask")
    mosaic.build_mean_mosaic([source], output)
    assert not Path(str(output) + ".msk").exists()
    with rasterio.open(output) as src:
        assert src.read(1, masked=True).count() == 9
