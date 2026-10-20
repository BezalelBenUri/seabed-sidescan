"""Executed by the new external Python after installing the processing stack."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path


def check(version, record, raw_source=None):
    import numpy as np
    import rasterio
    import shapefile
    import yaml
    from rasterio.transform import from_origin
    from scipy.ndimage import uniform_filter
    from skimage.filters import rank
    from sklearn.cluster import KMeans

    import seabed_sidescan
    from seabed_sidescan.api import create_mask

    prefix = Path(sys.prefix).resolve()
    assert seabed_sidescan.__version__ == version, "Engine version mismatch"
    assert Path(seabed_sidescan.__file__).resolve().is_relative_to(prefix), "Engine imported outside its managed environment"
    assert shapefile.__version__
    assert yaml.safe_load("installed: true") == {"installed": True}
    tiny = np.array([[0, 0], [1, 1]], dtype="uint8")
    assert np.isfinite(uniform_filter(tiny.astype("float64"), size=3)).all()
    assert np.isfinite(rank.entropy(tiny, footprint=np.ones((3, 3), dtype="uint8"))).all()
    labels = KMeans(n_clusters=2, n_init=1, random_state=0).fit_predict([[0, 0], [0.1, 0], [10, 10], [10.1, 10]])
    assert len(np.unique(labels)) == 2, "Classification dependency check failed"
    with tempfile.TemporaryDirectory(prefix="seabed-setup-check-") as directory:
        source, mask = Path(directory) / "input.tif", Path(directory) / "mask.tif"
        with rasterio.open(source, "w", driver="GTiff", width=2, height=2, count=1,
                           dtype="float32", nodata=-9999, crs="EPSG:32632",
                           transform=from_origin(500000, 1000, 1, 1)) as dataset:
            dataset.write(np.array([[1, -9999], [2, 3]], dtype="float32"), 1)
        create_mask(source, mask)
        with rasterio.open(mask) as dataset:
            np.testing.assert_array_equal(dataset.read(1), [[1, 0], [1, 1]])
    names = ["seabed-sidescan", "numpy", "affine", "rasterio", "pyshp", "scipy", "scikit-image", "scikit-learn", "PyYAML"]
    for name in names:
        importlib.metadata.version(name)
    if raw_source:
        import pygmt
        import rioxarray  # noqa: F401 -- verifies the xarray accessor used by raw export
        import sidescantools
        from pyproj import Transformer
        from sidescantools.cfg_parser import CFG  # noqa: F401
        from sidescantools.main_cli import SidescanToolsMain  # noqa: F401

        assert Path(sidescantools.__file__).resolve().is_relative_to(prefix), "Raw backend imported outside its managed environment"
        assert (raw_source / "src/sidescantools/main_cli.py").is_file(), "Raw source entry point is missing"
        points = np.array([[0.25, 0.25, 2], [0.75, 0.75, 4], [1.25, 1.25, 6], [1.75, 1.75, 8]])
        medians = pygmt.blockmedian(data=points, region=[0, 2, 0, 2], spacing=1)
        assert len(medians), "GMT blockmedian produced no values"
        grid = pygmt.nearneighbor(data=medians, region=[0, 2, 0, 2], spacing=1, search_radius=2, sectors="1")
        assert np.isfinite(grid.values).any(), "GMT gridding produced no finite cells"
        assert np.isfinite(Transformer.from_crs(4326, 32632, always_xy=True).transform(7.3, 4.2)).all()
        names += ["sidescantools", "pygmt", "rioxarray", "pyproj", "pydantic", "Pillow", "pyxtf", "utm"]
    report = {"schema_version": 1, "status": "verified", "engine_version": version,
              "python": str(Path(sys.executable).resolve()), "prefix": str(prefix),
              "gmt_user_directory": os.environ.get("GMT_USERDIR"),
              "raw_repository": str(raw_source.resolve()) if raw_source else None,
              "packages": {name: importlib.metadata.version(name) for name in names}}
    record.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Processing tools passed the installation checks.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--raw-source", type=Path)
    options = parser.parse_args()
    check(options.version, options.record, options.raw_source)
