"""Exercise the public interface against small, real geospatial rasters."""

import sys

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from seabed_sidescan import api


def write_raster(path, values, *, transform=None, crs="EPSG:32632", nodata=np.nan):
    values = np.asarray(values)
    bands = values[np.newaxis] if values.ndim == 2 else values
    with rasterio.open(
        path, "w", driver="GTiff", height=bands.shape[1], width=bands.shape[2],
        count=bands.shape[0], dtype=bands.dtype, crs=crs,
        transform=transform or from_origin(500000, 1000, 1, 1), nodata=nodata,
    ) as destination:
        destination.write(bands)
    return path


def test_synthetic_raster_pipeline(tmp_path):
    strips = tmp_path / "strips"
    strips.mkdir()
    rows, cols = np.indices((16, 16))
    values = (10 + rows + 3 * cols + 20 * (cols >= 8)).astype("float32")
    values[0, :2] = np.nan
    write_raster(strips / "line_ch0_proc.tif", values)
    write_raster(strips / "line_ch1_proc.tif", values * 1.5 + 4)

    mosaic = api.build_mosaics(strips, tmp_path / "mosaics", edge_trim_percent=0,
                               feather_percent=0)
    assert len(mosaic.mosaics) == 3
    assert len(mosaic.overlap_counts) == 3
    assert all(path.is_absolute() and path.is_file() for path in mosaic.mosaics)
    combined = next(path for path in mosaic.mosaics if "combined" in path.name)
    mask_path = api.create_mask(combined, tmp_path / "mask.tif")
    with rasterio.open(mask_path) as source:
        valid = source.read(1) == 1
        assert valid.sum() == values.size - 2

    textures = api.extract_textures(combined, mask_path, tmp_path / "textures",
                                    window_size=3, levels=4)
    assert len(textures.rasters) == 8
    for path in textures.rasters:
        with rasterio.open(path) as source:
            feature = source.read(1)
            assert feature.shape == values.shape
            assert np.all(np.isnan(feature[~valid]))
            assert np.all(np.isfinite(feature[valid]))

    feature_paths = [combined, *textures.rasters[:3]]
    stack = api.stack_features(feature_paths, mask_path, tmp_path / "features.tif",
                               band_names=["intensity", "mean", "variance", "std"])
    with rasterio.open(stack.output_stack) as source:
        assert source.count == len(feature_paths)
        assert source.descriptions[0] == "intensity"

    result = api.classify(stack.output_stack, mask_path, tmp_path / "classes.tif",
                          classes=2, n_init=2, sample_size=200, chunk_rows=5)
    with rasterio.open(result.output_raster) as source:
        classified = source.read(1)
        assert set(np.unique(classified[valid])) == {1, 2}
        assert np.all(classified[~valid] == 0)
    assert result.report_csv.is_file() and result.model_json.is_file()

    evaluation = api.evaluate_clusters(stack.output_stack, mask_path, tmp_path / "evaluation",
                                       classes=[2, 3], n_init=2, runs=2,
                                       sample_size=100, metric_sample_size=50)
    assert evaluation.output_csv.is_file() and evaluation.summary_txt.is_file()

    cleaned = api.clean_classification(result.output_raster, tmp_path / "cleaned.tif",
                                       min_patch_size=1)
    with rasterio.open(cleaned.output_raster) as source:
        assert np.all(source.read(1)[~valid] == 0)
    assert cleaned.report_txt.is_file()


def test_boundary_mask_and_clip(tmp_path):
    import shapefile

    raster = write_raster(tmp_path / "input.tif", np.arange(256, dtype="float32").reshape(16, 16))
    boundary = tmp_path / "boundary.shp"
    with shapefile.Writer(str(boundary)) as writer:
        writer.field("id", "N")
        writer.poly([[(500000, 1000), (500008, 1000), (500008, 984),
                      (500000, 984), (500000, 1000)]])
        writer.record(1)
    boundary.with_suffix(".prj").write_text(rasterio.crs.CRS.from_epsg(32632).to_wkt())
    mask = api.create_mask(raster, tmp_path / "mask.tif", boundary=boundary,
                           output_boundary_mask=tmp_path / "boundary_mask.tif")
    with rasterio.open(mask) as source:
        assert source.read(1).sum() == 128
    clipped = api.clip_raster(raster, boundary, tmp_path / "clipped.tif")
    with rasterio.open(clipped) as source:
        assert source.shape == (16, 8)
        assert source.crs.to_epsg() == 32632


def test_api_rejects_in_place_and_ambiguous_outputs(tmp_path):
    source = tmp_path / "input.tif"
    with pytest.raises(ValueError, match="differ"):
        api.create_mask(source, source)
    with pytest.raises(ValueError, match="distinct"):
        api.classify(source, tmp_path / "mask.tif", tmp_path / "out.tif",
                     report_csv=tmp_path / "out.tif")
    with pytest.raises(ValueError, match="At least one"):
        api.stack_features([], tmp_path / "mask.tif", tmp_path / "out.tif")
    with pytest.raises(ValueError, match="Boundary options"):
        api.create_mask(source, tmp_path / "out.tif", all_touched=True)


def test_mask_grid_mismatch_is_rejected(tmp_path):
    raster = write_raster(tmp_path / "input.tif", np.arange(16, dtype="float32").reshape(4, 4))
    mask = write_raster(tmp_path / "mask.tif", np.ones((4, 4), dtype="uint8"),
                        transform=from_origin(500001, 1000, 1, 1), nodata=0)
    with pytest.raises(ValueError, match="transform"):
        api.extract_textures(raster, mask, tmp_path / "textures", window_size=3, levels=4)
    with pytest.raises(ValueError, match="transform"):
        api.stack_features([raster], mask, tmp_path / "stack.tif")


@pytest.mark.parametrize("failure", ["invalid_parameters", "no_files", "rejected_strips", "resolution", "crs"])
def test_failed_mosaic_preflight_preserves_previous_product(tmp_path, failure):
    strips, mosaics = tmp_path / "strips", tmp_path / "mosaics"
    strips.mkdir()
    mosaics.mkdir()
    previous = mosaics / "SSS_combined_standard_mosaic.tif"
    previous.write_bytes(b"previous valid product")
    options = {}
    if failure != "no_files":
        values = np.arange(64, dtype="float32").reshape(8, 8)
        if failure == "rejected_strips":
            values[:] = 1
        write_raster(strips / "line_ch0_proc.tif", values)
        if failure in {"resolution", "crs"}:
            write_raster(strips / "line_ch1_proc.tif", values,
                         transform=from_origin(500000, 1000, 2, 2) if failure == "resolution" else None,
                         crs="EPSG:32631" if failure == "crs" else "EPSG:32632")
    if failure == "invalid_parameters":
        options["edge_trim_percent"] = 75
    with pytest.raises((ValueError, FileNotFoundError)):
        api.build_mosaics(strips, mosaics, clean_output=True, **options)
    assert previous.read_bytes() == b"previous valid product"


def fake_sonar_backend(tmp_path, code):
    repository = tmp_path / "fake_backend"
    package = repository / "src" / "sidescantools"
    package.mkdir(parents=True)
    (package / "main_cli.py").write_text(code, encoding="utf-8")
    sonar = tmp_path / "synthetic.xtf"
    sonar.write_bytes(b"Adapter test placeholder; not real sonar data.")
    return repository, sonar


def test_raw_adapter_dry_run_writes_portable_configuration(tmp_path):
    import yaml

    backend, sonar = fake_sonar_backend(tmp_path, "raise AssertionError('dry run executed backend')")
    result = api.process_sonar(sonar, tmp_path / "projects", "sample survey",
                               sidescantools_repo=backend, sidescantools_python=sys.executable,
                               channel_pair=(2, 3), resolution=0.5, dry_run=True)
    assert result.project_dir == tmp_path / "projects" / "sample_survey"
    assert result.georef_dir.is_dir() and result.previews_dir.is_dir()
    configuration = yaml.safe_load(result.runtime_config.read_text())
    assert configuration["main_proc_params"]["georef_dir"] == result.georef_dir.as_posix()
    assert configuration["meta_infos"]["working_dir"] == result.previews_dir.as_posix()
    assert configuration["georef_view_params"]["output_resolution"] == 0.5
    assert configuration["georef_view_params"]["output_search_radius"] == 1.0
    assert not tuple(result.georef_dir.iterdir())


def test_raw_adapter_detects_backend_geotiff_output(tmp_path):
    # This fake backend copies a known GeoTIFF to validate the adapter contract.
    # It does not exercise any actual XTF or JSF decoding or georeferencing.
    template = write_raster(tmp_path / "fixture.tif", np.ones((2, 3), dtype="float32"))
    code = (
        "from pathlib import Path\nimport json, os, shutil, sys, yaml\n"
        "configuration = yaml.safe_load(Path(sys.argv[2]).read_text())\n"
        "destination = Path(configuration['main_proc_params']['georef_dir'])\n"
        f"shutil.copyfile({str(template)!r}, destination / 'synthetic_ch0_proc.tif')\n"
        f"shutil.copyfile({str(template)!r}, destination / 'synthetic_ch1_proc.tif')\n"
        "pair = list(map(int, os.environ['SIDESCANTOOLS_XTF_CHANNEL_PAIR'].split(',')))\n"
        "outputs = [{'channel': ch, 'input_channel': pair[ch], 'path': str(destination / f'synthetic_ch{ch}_proc.tif')} for ch in (0,1)]\n"
        "Path(os.environ['SIDESCANTOOLS_RUN_MANIFEST']).write_text(json.dumps({'schema_version': 1, 'inputs': [{'path': sys.argv[1], 'outputs': outputs}]}))\n"
        "(destination / 'channel_pair.txt').write_text(os.environ['SIDESCANTOOLS_XTF_CHANNEL_PAIR'])\n"
    )
    backend, sonar = fake_sonar_backend(tmp_path, code)
    result = api.process_sonar(sonar, tmp_path / "projects", "adapter",
                               sidescantools_repo=backend, sidescantools_python=sys.executable,
                               channel_pair=(2, 3))
    with rasterio.open(result.georef_dir / "synthetic_ch0_proc.tif") as source:
        assert source.shape == (2, 3) and source.crs.to_epsg() == 32632
    assert (result.georef_dir / "channel_pair.txt").read_text() == "2,3"


def test_raw_adapter_rejects_unverified_partial_backend_output(tmp_path):
    template = write_raster(tmp_path / "fixture.tif", np.ones((2, 3), dtype="float32"))
    code = (
        "from pathlib import Path\nimport shutil, sys, yaml\n"
        "configuration = yaml.safe_load(Path(sys.argv[2]).read_text())\n"
        "destination = Path(configuration['main_proc_params']['georef_dir'])\n"
        f"shutil.copyfile({str(template)!r}, destination / 'only_one_channel.tif')\n"
    )
    backend, sonar = fake_sonar_backend(tmp_path, code)
    with pytest.raises(RuntimeError, match="no per-input run manifest"):
        api.process_sonar(sonar, tmp_path / "projects", "partial",
                          sidescantools_repo=backend, sidescantools_python=sys.executable)


@pytest.mark.parametrize("code, message", [
    ("raise SystemExit(7)", "status 7"),
    ("pass", "without creating or updating a GeoTIFF"),
])
def test_raw_adapter_rejects_unsuccessful_backend_run(tmp_path, code, message):
    backend, sonar = fake_sonar_backend(tmp_path, code)
    with pytest.raises(RuntimeError, match=message):
        api.process_sonar(sonar, tmp_path / "projects", "adapter",
                          sidescantools_repo=backend, sidescantools_python=sys.executable)
