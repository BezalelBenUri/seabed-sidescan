"""Regression checks for raster masks, class labels and scientific units."""

import csv

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.transform import from_origin

from seabed_sidescan import api
from seabed_sidescan.classify import pixel_area_m2, read_training_data
from seabed_sidescan.cleanup import majority_filter
from seabed_sidescan.texture import (
    masked_local_mean_variance,
    parse_directions,
    shift_array,
)


def write_raster(path, values, *, nodata, crs="EPSG:32632"):
    values = np.asarray(values)
    bands = values[np.newaxis] if values.ndim == 2 else values
    with rasterio.open(path, "w", driver="GTiff", height=bands.shape[1], width=bands.shape[2],
                       count=bands.shape[0], dtype=bands.dtype, crs=crs,
                       transform=from_origin(500000, 1000, 1, 1), nodata=nodata) as destination:
        destination.write(bands)
    return path


def test_mask_accepts_integer_raster_with_nodata(tmp_path):
    values = np.array([[0, 2, 3], [4, 0, 5]], dtype="uint8")
    raster = write_raster(tmp_path / "integer.tif", values, nodata=0)
    mask = api.create_mask(raster, tmp_path / "mask.tif")
    with rasterio.open(mask) as source:
        np.testing.assert_array_equal(source.read(1), values != 0)


def test_finite_feature_nodata_is_excluded_from_training_and_prediction(tmp_path):
    features = np.ones((2, 8, 8), dtype="float32")
    features[:, :, 4:] = 10
    features[1, 0, 0] = -9999
    stack = write_raster(tmp_path / "features.tif", features, nodata=-9999)
    mask = write_raster(tmp_path / "mask.tif", np.ones((8, 8), dtype="uint8"), nodata=0)
    sample, valid_pixels, count = read_training_data(stack, mask, 100, 42)
    assert valid_pixels == count == 63
    assert np.all(sample > 0)
    result = api.classify(stack, mask, tmp_path / "classes.tif", classes=2, n_init=2)
    with rasterio.open(result.output_raster) as source:
        labels = source.read(1)
        assert labels[0, 0] == 0
        assert np.count_nonzero(labels) == 63
    with result.report_csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert sum(int(row["pixel_count"]) for row in rows) == 63
    assert sum(float(row["area_m2"]) for row in rows) == 63


def test_cleanup_supports_nonzero_nodata_and_valid_class_zero(tmp_path):
    values = np.zeros((5, 5), dtype="uint8")
    values[2, 2] = 1
    values[0, 0] = 255
    valid = values != 255
    expected = np.zeros_like(values)
    expected[0, 0] = 255
    np.testing.assert_array_equal(majority_filter(values, valid, 3, nodata_label=255), expected)
    raster = write_raster(tmp_path / "classes.tif", values, nodata=255)
    result = api.clean_classification(raster, tmp_path / "cleaned.tif", nodata_label=255,
                                      min_patch_size=1)
    with rasterio.open(result.output_raster) as source:
        np.testing.assert_array_equal(source.read(1), expected)
        assert source.nodata == 255
    assert "Class 255 / NoData" in result.report_txt.read_text()


def test_cleanup_rejects_labels_that_would_wrap_uint8(tmp_path):
    raster = write_raster(tmp_path / "classes.tif", np.array([[1, 256]], dtype="uint16"), nodata=0)
    with pytest.raises(ValueError, match="integer labels"):
        api.clean_classification(raster, tmp_path / "cleaned.tif")


def test_pixel_area_uses_affine_determinant_and_requires_metre_crs():
    reference = {"crs": rasterio.crs.CRS.from_epsg(32632),
                 "transform": Affine(2, 0.5, 500000, 0.25, -3, 1000)}
    assert pixel_area_m2(reference) == pytest.approx(6.125)
    for crs in (None, rasterio.crs.CRS.from_epsg(4326), rasterio.crs.CRS.from_epsg(2263)):
        with pytest.raises(ValueError, match="metres"):
            pixel_area_m2({**reference, "crs": crs})


def test_geographic_classification_rejects_mislabeled_square_metre_report(tmp_path):
    stack = write_raster(tmp_path / "features.tif", np.arange(16, dtype="float32").reshape(4, 4),
                         nodata=np.nan, crs="EPSG:4326")
    mask = write_raster(tmp_path / "mask.tif", np.ones((4, 4), dtype="uint8"),
                        nodata=0, crs="EPSG:4326")
    with pytest.raises(ValueError, match="projected CRS"):
        api.classify(stack, mask, tmp_path / "classes.tif", classes=2)
    assert not (tmp_path / "classes.tif").exists()


def test_texture_offsets_validate_and_large_shift_is_empty():
    with pytest.raises(ValueError, match="nonzero"):
        parse_directions("0,0")
    with pytest.raises(ValueError, match="duplicates"):
        parse_directions("0,1;0,1")
    values = np.arange(12).reshape(3, 4)
    for dy, dx in ((10, 0), (-10, 1), (0, 20), (1, -20)):
        assert not shift_array(values, dy, dx).any()


def test_local_moments_exclude_nodata_and_use_partial_edge_window():
    values = np.array([[1, 2, 3], [4, 1000, 6], [7, 8, 9]], dtype="float32")
    valid = np.ones(values.shape, dtype=bool)
    valid[1, 1] = False
    mean, variance, std = masked_local_mean_variance(values, valid, 3)
    # The left-centre window contains exactly 1, 2, 4, 7, 8.
    assert mean[1, 0] == pytest.approx(4.4)
    assert variance[1, 0] == pytest.approx(7.44, rel=1e-5)
    assert std[1, 0] == pytest.approx(np.sqrt(7.44), rel=1e-5)
    assert np.isnan(mean[1, 1]) and np.isnan(variance[1, 1])
