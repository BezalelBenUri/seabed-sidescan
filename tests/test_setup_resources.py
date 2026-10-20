"""Checks for source-only, reproducible guided-installation resources."""

import ast
import hashlib
import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_setup_resources", ROOT / "tools/build_setup_resources.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def project_snapshot(destination, *, vendor=True):
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    shutil.copytree(ROOT / "src/seabed_sidescan", destination / "src/seabed_sidescan",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "requirements", destination / "requirements")
    if vendor:
        source = ROOT / "vendor/sidescantools-main"
        if not source.is_dir():
            pytest.skip("Pruned source distribution has no vendor checkout; packaged reuse is checked separately.")
        shutil.copytree(source, destination / "vendor/sidescantools-main",
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    return destination


def test_setup_bundles_are_deterministic_source_only_and_keep_legal_notices(tmp_path):
    root = project_snapshot(tmp_path / "source")
    output = tmp_path / "setup"
    manifest_path = BUILDER.build_setup_resources(root, output)
    first = {path.name: path.read_bytes() for path in output.iterdir()}
    # Filesystem timestamps and checkout newlines do not change bundle bytes.
    version = root / "src/seabed_sidescan/__init__.py"
    version.write_bytes(b"\xef\xbb\xbf" + version.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    BUILDER.build_setup_resources(root, output)
    assert first == {path.name: path.read_bytes() for path in output.iterdir()}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    for mode, record in manifest["bundles"].items():
        archive = output / record["filename"]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == record["sha256"]
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            assert all(name.startswith(record["root"] + "/") for name in names)
            assert all(name.endswith((".py", ".md", ".yml", ".json", ".toml", ".typed", "/LICENSE", "/NOTICE")) for name in names)
            assert not any("__pycache__" in name or "egg-info" in name or "/tests/" in name for name in names)
            assert f"{record['root']}/LICENSE" in names
            if mode == "engine":
                assert f"{record['root']}/NOTICE" in names
            else:
                assert f"{record['root']}/THIRD_PARTY.md" in names
                assert f"{record['root']}/BUNDLE_README.md" in names
                assert not any("main_gui" in name or "/res/" in name for name in names)
    assert (output / "engine-source.zip").stat().st_size < 200_000
    assert (output / "sidescantools-cli-source.zip").stat().st_size < 200_000


def test_raw_module_allowlist_covers_actual_cli_import_graph():
    vendor = ROOT / "vendor/sidescantools-main/src/sidescantools"
    if not vendor.is_dir():
        pytest.skip("Pruned source distribution has no vendor source to compare.")
    optional_gui = {"bottom_detection_napari_ui", "custom_threading", "custom_widgets"}
    for module in BUILDER.RAW_MODULES:
        tree = ast.parse((vendor / f"{module}.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module.startswith("sidescantools."):
                target = node.module.split(".")[1]
                assert target in BUILDER.RAW_MODULES or (module == "__init__" and target in optional_gui)
        if module == "main_cli":
            plotting = next(node for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "PLOTTING" for target in node.targets))
            assert ast.literal_eval(plotting.value) is False


def test_vendor_pruned_source_reuses_verified_cli_bundle(tmp_path):
    root = project_snapshot(tmp_path / "full")
    packaged = root / BUILDER.RESOURCE_PATH
    BUILDER.build_setup_resources(root, packaged)
    pruned = project_snapshot(tmp_path / "pruned", vendor=False)
    shutil.copytree(packaged, pruned / BUILDER.RESOURCE_PATH)
    output = tmp_path / "rebuilt"
    result = BUILDER.build_setup_resources(pruned, output)
    assert result.is_file()
    assert (packaged / "sidescantools-cli-source.zip").read_bytes() == (output / "sidescantools-cli-source.zip").read_bytes()


@pytest.mark.parametrize("update_checksum", [False, True])
def test_vendor_pruned_reuse_rejects_tampering_and_unexpected_members(tmp_path, update_checksum):
    root = project_snapshot(tmp_path / "full")
    packaged = root / BUILDER.RESOURCE_PATH
    BUILDER.build_setup_resources(root, packaged)
    pruned = project_snapshot(tmp_path / "pruned", vendor=False)
    shutil.copytree(packaged, pruned / BUILDER.RESOURCE_PATH)
    resources = pruned / BUILDER.RESOURCE_PATH
    archive = resources / "sidescantools-cli-source.zip"
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("sidescantools-cli-source/unexpected.dll", b"unexpected binary")
    if update_checksum:
        manifest_path = resources / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundles"]["raw"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum|unexpected"):
        BUILDER.build_setup_resources(pruned, tmp_path / "output")


def test_environment_specs_separate_core_from_raw_and_cover_declared_dependencies():
    required_core = {"python", "pip", "setuptools", "wheel", "affine", "numpy", "pyshp",
                     "rasterio", "scipy", "scikit-image", "scikit-learn", "pyyaml"}
    names = {}
    for mode in ("core", "raw"):
        spec = yaml.safe_load((ROOT / "requirements" / f"managed_{mode}_environment.yml").read_text())
        assert spec["channels"] == ["conda-forge", "nodefaults"]
        assert all(isinstance(value, str) for value in spec["dependencies"])
        names[mode] = {value.split("=")[0].split(">")[0].split("<")[0] for value in spec["dependencies"]}
        assert required_core <= names[mode]
        assert not ({"napari", "qtpy", "pyqt", "pyside6", "matplotlib"} & names[mode])
    assert "gmt" not in names["core"]
    assert {"gmt", "gdal", "pygmt", "rioxarray", "pyxtf", "utm", "pydantic", "pillow", "geopy", "pyproj"} <= names["raw"]
