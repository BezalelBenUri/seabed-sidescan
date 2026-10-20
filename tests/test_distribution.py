import importlib.metadata
import importlib.util
import zipfile
from pathlib import Path

from seabed_sidescan import __version__


def test_installed_metadata_version():
    assert importlib.metadata.version("seabed-sidescan") == __version__


def test_plugin_development_archive_is_small_and_separate(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools" / "build_qgis_plugin.py"
    spec = importlib.util.spec_from_file_location("build_qgis_plugin", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = module.build_plugin(tmp_path, development=True)
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert all(name.startswith("seabed_sidescan_qgis/") for name in names)
        assert "seabed_sidescan_qgis/metadata.txt" in names
        assert "seabed_sidescan_qgis/__init__.py" in names
        assert "seabed_sidescan_qgis/DEVELOPMENT.txt" in names
        assert not any("vendor/" in name or "__pycache__" in name for name in names)
        assert not any(name.endswith((".dll", ".so", ".whl", ".tif")) for name in names)
    assert archive.stat().st_size < 25 * 1024 * 1024
