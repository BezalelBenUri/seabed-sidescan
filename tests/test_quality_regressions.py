"""Failure safety, independent numerical checks and bounded-memory contracts."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from seabed_sidescan import api
from seabed_sidescan.classify import read_training_data, squared_distances
from seabed_sidescan.cleanup import remove_small_patches
from seabed_sidescan.cli import main
from seabed_sidescan.io import atomic_output


def raster(path, data, nodata=None):
    data = np.asarray(data)
    bands = data[np.newaxis] if data.ndim == 2 else data
    with rasterio.open(path, "w", driver="GTiff", width=bands.shape[2], height=bands.shape[1],
                       count=bands.shape[0], dtype=bands.dtype, nodata=nodata,
                       transform=from_origin(500000, 1000, 1, 1), crs="EPSG:32632") as dst:
        dst.write(bands)
    return path


def boundary(path):
    import shapefile
    with shapefile.Writer(str(path)) as writer:
        writer.field("id", "N")
        writer.poly([[(500000, 1000), (500002, 1000), (500002, 998), (500000, 1000)]])
        writer.record(1)
    path.with_suffix(".prj").write_text(rasterio.crs.CRS.from_epsg(32632).to_wkt())
    return path


def test_cli_rejects_input_overwrite(tmp_path):
    source = raster(tmp_path / "input.tif", np.ones((3, 3), dtype="float32"))
    before = source.read_bytes()
    assert main(["mask", "--input-raster", str(source), "--output-mask", str(source)]) == 1
    assert source.read_bytes() == before


def test_api_rejects_hardlinked_input(tmp_path):
    source = raster(tmp_path / "input.tif", np.ones((3, 3), dtype="float32"))
    alias = tmp_path / "alias.tif"
    os.link(source, alias)
    with pytest.raises(ValueError, match="differ"):
        api.create_mask(source, alias)


def test_failed_writer_keeps_existing_file_and_removes_stage(tmp_path):
    path = tmp_path / "result.tif"
    path.write_bytes(b"existing result")
    with pytest.raises(RuntimeError):
        with atomic_output(path) as stage:
            stage.write_bytes(b"incomplete replacement")
            raise RuntimeError("injected writer failure")
    assert path.read_bytes() == b"existing result"
    assert list(tmp_path.iterdir()) == [path]


def test_clip_preserves_valid_integer_zero_with_internal_mask(tmp_path):
    source = raster(tmp_path / "zero.tif", np.zeros((2, 2), dtype="uint8"))
    polygon = boundary(tmp_path / "boundary.shp")
    output = api.clip_raster(source, polygon, tmp_path / "clipped.tif", keep_extent=True)
    with rasterio.open(output) as dataset:
        values = dataset.read(1, masked=True)
        assert dataset.nodata is None
        assert 0 < values.count() < values.size
        assert np.all(values.compressed() == 0)
    assert not Path(str(output) + ".msk").exists()


@pytest.mark.parametrize("nodata", [0, -1, 256, 0.5, float("inf"), float("nan")])
def test_clip_rejects_colliding_or_unrepresentable_integer_nodata(tmp_path, nodata):
    source = raster(tmp_path / "zero.tif", np.zeros((2, 2), dtype="uint8"))
    polygon = boundary(tmp_path / "boundary.shp")
    output = tmp_path / "old.tif"
    output.write_bytes(b"keep this")
    with pytest.raises(ValueError):
        api.clip_raster(source, polygon, output, nodata=nodata)
    assert output.read_bytes() == b"keep this"


def test_sampling_preserves_float64_detail_and_repeats_seed(tmp_path):
    values = (1e12 + np.arange(1537 * 270, dtype="float64").reshape(270, 1537) / 4)
    stack = raster(tmp_path / "features.tif", values)
    mask = raster(tmp_path / "mask.tif", np.ones(values.shape, dtype="uint8"), nodata=0)
    first, valid, size = read_training_data(stack, mask, 37, 42)
    second, _, _ = read_training_data(stack, mask, 37, 42)
    assert valid == values.size and size == 37
    np.testing.assert_array_equal(first, second)
    assert np.unique(first).size > 1  # float32 conversion would collapse detail.
    assert np.all(np.isin(first[:, 0], values))


def test_distances_match_direct_high_offset_calculation():
    values = np.array([[1e12, 1e12 + 0.25], [1e12 + 2, 1e12 - 1]])
    centers = np.array([[1e12, 1e12], [1e12 + 1, 1e12 - 2]])
    expected = np.sum((values[:, None, :] - centers[None, :, :]) ** 2, axis=2)
    np.testing.assert_array_equal(squared_distances(values, centers), expected)


def test_unrepresentable_distances_raise_instead_of_silent_class_assignment():
    with pytest.raises(ValueError, match="finite numerical range"):
        squared_distances(np.array([[1e200]]), np.array([[0.0], [1.0]]))


def test_degenerate_cluster_request_keeps_previous_output(tmp_path):
    source = raster(tmp_path / "constant.tif", np.ones((5, 5), dtype="float32"))
    mask = raster(tmp_path / "mask.tif", np.ones((5, 5), dtype="uint8"), nodata=0)
    output = tmp_path / "old.tif"
    output.write_bytes(b"previous classification")
    with pytest.raises(ValueError, match="distinct"):
        api.classify(source, mask, output, classes=2)
    assert output.read_bytes() == b"previous classification"


def test_nonbinary_mask_is_rejected(tmp_path):
    source = raster(tmp_path / "features.tif", np.arange(25, dtype="float32").reshape(5, 5))
    mask = raster(tmp_path / "mask.tif", np.full((5, 5), 2, dtype="uint8"))
    with pytest.raises(ValueError, match="0 and 1"):
        api.classify(source, mask, tmp_path / "out.tif", classes=2)
    with pytest.raises(ValueError, match="0 and 1"):
        api.stack_features([source], mask, tmp_path / "stack.tif")


def test_cleanup_is_independent_of_numeric_class_order():
    data = np.array([[0, 0, 0, 0, 0], [0, 1, 2, 2, 0], [0, 2, 1, 1, 0], [0, 0, 0, 0, 0]], dtype="uint8")
    swapped = np.where(data == 1, 2, np.where(data == 2, 1, 0)).astype("uint8")
    first, _, _ = remove_small_patches(data, data != 0, 4, 0)
    second, _, _ = remove_small_patches(swapped, swapped != 0, 4, 0)
    restored = np.where(second == 1, 2, np.where(second == 2, 1, 0))
    np.testing.assert_array_equal(first, restored)


def test_cli_manifest_contains_exact_outputs(tmp_path):
    source = raster(tmp_path / "input.tif", np.ones((3, 3), dtype="float32"))
    output = tmp_path / "mask.tif"
    report = tmp_path / "manifest.json"
    (tmp_path / "unrelated.tif").write_bytes(b"unrelated")
    assert main(["mask", "--input-raster", str(source), "--output-mask", str(output),
                 "--output-manifest", str(report)]) == 0
    manifest = json.loads(report.read_text())
    assert manifest["outputs"] == [str(output.resolve())]
    assert manifest["command"] == "mask" and manifest["schema_version"] == 1


def test_cli_manifest_cannot_replace_inferred_project_input(tmp_path):
    project = tmp_path / "survey" / "mosaics"
    project.mkdir(parents=True)
    source = raster(project / "SSS_combined_standard_mosaic.tif", np.ones((3, 3), dtype="float32"))
    before = source.read_bytes()
    assert main(["mask", "--project", "survey", "--project-root", str(tmp_path),
                 "--output-manifest", str(source)]) == 1
    assert source.read_bytes() == before
    assert not (tmp_path / "survey" / "masks" / "SSS_valid_data_mask.tif").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cancellation")
def test_raw_cancellation_stops_backend_and_its_child(tmp_path):
    script = tmp_path / "backend.py"
    script.write_text('''import os, pathlib, signal, subprocess, sys, time
root = pathlib.Path(sys.argv[1])
role = sys.argv[2] if len(sys.argv) > 2 else 'parent'
def stopped(signum, frame):
    (root / (role + '.stopped')).write_text('stopped')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stopped)
if role == 'parent':
    subprocess.Popen([sys.executable, __file__, str(root), 'child'])
else:
    (root / 'ready').write_text('ready')
while True: time.sleep(0.05)
''')
    runner = "import os,sys; from seabed_sidescan.cli import _run_raw_backend; raise SystemExit(_run_raw_backend([sys.executable,sys.argv[1],sys.argv[2]],cwd=os.getcwd(),env=os.environ.copy()))"
    worker = subprocess.Popen([sys.executable, "-c", runner, str(script), str(tmp_path)])
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
        os.kill(worker.pid, signal.SIGTERM)
        assert worker.wait(timeout=10) == 143
        assert (tmp_path / "parent.stopped").exists()
        assert (tmp_path / "child.stopped").exists()
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=3)
