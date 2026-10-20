"""Verify local build artifacts without publishing them.

Run after installing .[dev], building wheel/sdist, and building a development
plugin ZIP. Source rebuilding uses PEP 517 build isolation. Fresh smoke-test
virtual environments reuse the calling environment's scientific dependencies;
the project itself is installed from its wheel, and its import location must be
inside the new environment. No editable checkout is used for package imports.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import json
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

FORBIDDEN_DIRECTORIES = {"vendor", "data", "outputs", "logs", ".venv", ".git", ".pytest_cache", "__pycache__"}
FORBIDDEN_SUFFIXES = {".xtf", ".jsf", ".tif", ".tiff", ".npy", ".npz", ".pyc", ".dll", ".so", ".dylib", ".exe", ".pyd"}
EXPECTED_PACKAGE_FILES = {
    "seabed_sidescan/__init__.py",
    "seabed_sidescan/__main__.py",
    "seabed_sidescan/api.py",
    "seabed_sidescan/cli.py",
    "seabed_sidescan/py.typed",
    "seabed_sidescan/resources/sidescantools_project_info.yml",
}
PLUGIN_NAME = "seabed_sidescan_qgis"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _check_member_names(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        _require(not path.is_absolute() and ".." not in path.parts and "\\" not in name,
                 f"Unsafe archive member: {name}")
        _require(not FORBIDDEN_DIRECTORIES.intersection(path.parts),
                 f"Development data or vendor files leaked into artifact: {name}")
        _require(path.suffix.lower() not in FORBIDDEN_SUFFIXES,
                 f"Survey, generated, or compiled file leaked into artifact: {name}")


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as package:
        _require(package.testzip() is None, f"Corrupt wheel: {path.name}")
        names = package.namelist()
        _check_member_names(names)
        _require(EXPECTED_PACKAGE_FILES.issubset(names),
                 f"Wheel is missing package modules, typing marker, or config: {path.name}")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        _require(len(metadata_names) == 1, f"Expected one wheel METADATA file: {path.name}")
        metadata = BytesParser().parsebytes(package.read(metadata_names[0]))
        _require(metadata["Name"] == "seabed-sidescan", "Unexpected wheel project name.")
        _require(bool(metadata["Version"]), "Wheel version is missing.")
        _require(bool(metadata.get_all("Requires-Dist")), "Wheel runtime dependencies are missing.")
        _require(metadata["License-Expression"] == "GPL-3.0-or-later",
                 "Wheel license expression differs from the selected project license.")
        metadata_root = metadata_names[0].rsplit("/", 1)[0]
        license_files = metadata.get_all("License-File", [])
        for name in ("LICENSE", "NOTICE"):
            _require(name in license_files and f"{metadata_root}/licenses/{name}" in names,
                     f"Wheel is missing its declared license material: {name}")
        return metadata["Name"], metadata["Version"]


def _wheel_payload(path: Path) -> dict[str, str]:
    """Compare code verbatim and generated text metadata across OS line endings."""
    payload = {}
    with zipfile.ZipFile(path) as package:
        for name in package.namelist():
            text_metadata = name.endswith((".dist-info/METADATA", ".dist-info/entry_points.txt"))
            if name.startswith("seabed_sidescan/") or ".dist-info/licenses/" in name or text_metadata:
                content = package.read(name)
                # Setuptools emits CRLF metadata on Windows and LF on POSIX.
                # Only normalize those generated text files, keeping code,
                # packaged resources and legal material byte-exact.
                if text_metadata:
                    content = content.replace(b"\r\n", b"\n")
                payload[name] = hashlib.sha256(content).hexdigest()
    return payload


def _extract_source(path: Path, destination: Path) -> Path:
    with tarfile.open(path, "r:gz") as source:
        members = source.getmembers()
        _check_member_names([item.name for item in members])
        roots = {PurePosixPath(item.name).parts[0] for item in members if item.name}
        _require(len(roots) == 1, "Source distribution must contain one project directory.")
        # Explicit extraction also works on Python 3.10, which has no tar filter.
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            _require(target.resolve().is_relative_to(destination.resolve()),
                     f"Source member escapes extraction directory: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                _require(member.isfile(), f"Unsupported source archive member: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(member)
                _require(stream is not None, f"Cannot read source member: {member.name}")
                with stream, target.open("wb") as output:
                    shutil.copyfileobj(stream, output)
    root = destination / roots.pop()
    _require((root / "pyproject.toml").is_file(), "Source distribution is missing pyproject.toml.")
    for name in ("LICENSE", "NOTICE"):
        _require((root / name).is_file(), f"Source distribution is missing {name}.")
    for name in EXPECTED_PACKAGE_FILES:
        _require((root / "src" / name).is_file(), f"Source distribution is missing {name}")
    return root


def _check_plugin(path: Path, version: str, *, development: bool = True) -> None:
    with zipfile.ZipFile(path) as package:
        _require(package.testzip() is None, f"Corrupt plugin archive: {path.name}")
        names = package.namelist()
        _check_member_names(names)
        _require(all(name.startswith(PLUGIN_NAME + "/") for name in names),
                 "Plugin archive must have one plugin root directory.")
        required = {f"{PLUGIN_NAME}/{name}" for name in (
            "__init__.py", "metadata.txt", "plugin.py", "provider.py", "engine.py",
            "settings.py", "setup_flow.py", "setup_plan.py", "check_installation.py",
            "icon.svg", "README.md", "LICENSE", "NOTICE",
        )}
        development_note = f"{PLUGIN_NAME}/DEVELOPMENT.txt"
        if development:
            required.add(development_note)
        else:
            _require(development_note not in names, "Public plugin contains a development marker.")
        _require(required.issubset(names), "Plugin archive is incomplete.")
        _require(not any("seabed_sidescan/" in name for name in names),
                 "Plugin must install its bundled engine source outside QGIS Python.")
        setup_root = f"{PLUGIN_NAME}/resources/setup/"
        manifest = json.loads(package.read(setup_root + "manifest.json"))
        _require(manifest["schema_version"] == 1 and manifest["engine_version"] == version,
                 "Guided setup resources do not match the plugin version.")
        _require(set(manifest["bundles"]) == {"engine", "raw"}
                 and set(manifest["environments"]) == {"core", "raw"},
                 "Guided setup source bundles or environment specifications are incomplete.")
        for section in ("bundles", "environments"):
            for record in manifest[section].values():
                name = record["filename"]
                _require(PurePosixPath(name).parts == (name,) and "\\" not in name,
                         "Unsafe setup resource filename.")
                content = package.read(setup_root + name)
                _require(hashlib.sha256(content).hexdigest() == record["sha256"],
                         f"Guided setup resource checksum mismatch: {name}")
                if section == "bundles":
                    with zipfile.ZipFile(io.BytesIO(content)) as source:
                        source_names = source.namelist()
                        _check_member_names(source_names)
                        expected = {record["root"] + "/" + item for item in record["files"]}
                        _require(set(source_names) == expected and len(source_names) == len(expected),
                                 "Source bundle contains missing, extra or duplicate files.")
                        for member in source_names:
                            relative = member.removeprefix(record["root"] + "/")
                            _require(hashlib.sha256(source.read(member)).hexdigest() == record["files"][relative],
                                     f"Source bundle file checksum mismatch: {member}")
                        _require(record["root"] + "/LICENSE" in source_names,
                                 "Source bundle is missing its license.")
                        if name == "sidescantools-cli-source.zip":
                            _require(record["root"] + "/THIRD_PARTY.md" in source_names,
                                     "Raw source bundle is missing its upstream/change notice.")
        metadata = configparser.ConfigParser(interpolation=None)
        metadata.read_string(package.read(f"{PLUGIN_NAME}/metadata.txt").decode("utf-8-sig"))
        _require(metadata["general"]["version"] == version,
                 "Plugin and engine versions differ.")
        _require(metadata["general"]["license"] == "GPL-3.0-or-later",
                 "Plugin license differs from the selected project license.")
        if not development:
            for name in ("author", "email", "homepage", "repository", "tracker"):
                _require(bool(metadata["general"].get(name, "").strip()),
                         f"Public plugin is missing {name} metadata.")
    _require(path.stat().st_size < 25 * 1024 * 1024, "Plugin archive unexpectedly exceeds 25 MiB.")


def _plugin_payload(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as package:
        return {name: hashlib.sha256(package.read(name)).hexdigest() for name in package.namelist()}


SMOKE_SCRIPT = r'''
import importlib.metadata
import importlib.resources
from pathlib import Path
import sys

import numpy as np
import rasterio
from rasterio.transform import from_origin
import yaml
import seabed_sidescan as package

assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), package.__file__
assert package.__version__ == importlib.metadata.version("seabed-sidescan")
assert package.__version__ == sys.argv[1]
assert all(callable(getattr(package, name)) for name in (
    "build_mosaics", "classify_facies", "clean_classification", "clip_raster",
    "create_mask", "evaluate_clusters", "extract_textures", "process_sonar", "stack_features",
))
assert "qgis" not in sys.modules and "sidescantools" not in sys.modules
resource = importlib.resources.files("seabed_sidescan").joinpath(
    "resources", "sidescantools_project_info.yml"
)
assert isinstance(yaml.safe_load(resource.read_text(encoding="utf-8")), dict)
source = Path.cwd() / "input with spaces.tif"
mask = Path.cwd() / "mask with spaces.tif"
with rasterio.open(source, "w", driver="GTiff", width=2, height=2, count=1,
                   dtype="float32", nodata=-9999, crs="EPSG:32632",
                   transform=from_origin(500000, 1000, 1, 1)) as dataset:
    dataset.write(np.array([[1, -9999], [2, 3]], dtype="float32"), 1)
assert package.create_mask(source, mask) == mask.resolve()
with rasterio.open(mask) as dataset:
    np.testing.assert_array_equal(dataset.read(1), [[1, 0], [1, 1]])
    assert dataset.crs.to_epsg() == 32632
raw = Path.cwd() / "survey.xtf"
raw.touch()
backend = Path.cwd() / "raw backend"
backend_cli = backend / "src" / "sidescantools" / "main_cli.py"
backend_cli.parent.mkdir(parents=True)
backend_cli.touch()
plan = package.process_sonar(raw, Path.cwd() / "projects", "survey",
    sidescantools_repo=backend, sidescantools_python=sys.executable, dry_run=True)
assert plan.runtime_config.is_file()
config = yaml.safe_load(plan.runtime_config.read_text(encoding="utf-8"))
assert config["main_proc_params"]["georef_dir"] == plan.georef_dir.as_posix()
print("Installed wheel API, resource and import checks passed:", package.__file__)
'''


def _run(arguments: list[str], *, cwd: Path) -> None:
    display = list(arguments)
    if "-c" in display:
        display[display.index("-c") + 1] = "<Python smoke check>"
    print("Running:", " ".join(display), flush=True)
    subprocess.run(arguments, cwd=cwd, check=True)


def _smoke_install(wheel: Path, directory: Path, version: str) -> None:
    from virtualenv import cli_run

    directory.mkdir(parents=True)
    environment = directory / "environment"
    # PyPA virtualenv includes its pip seed, including on Debian installations
    # whose base Python does not provide the stdlib ensurepip module.
    cli_run([str(environment), "--system-site-packages", "--no-download", "--no-periodic-update"])
    scripts = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    # A child venv otherwise inherits base-Python site-packages, not the calling
    # developer venv. Add its dependency folders after the new environment's own
    # site-packages. Installed-project origin is checked in SMOKE_SCRIPT.
    environment_site = Path(subprocess.check_output(
        [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True, cwd=directory,
    ).strip())
    dependency_paths = sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
    (environment_site / "inherited_dependencies.pth").write_text(
        "\n".join(dependency_paths) + "\n", encoding="utf-8",
    )
    _run([str(python), "-I", "-m", "pip", "install", "--no-deps", "--ignore-installed", str(wheel)], cwd=directory)
    _run([str(python), "-I", "-c", SMOKE_SCRIPT, version], cwd=directory)
    _run([str(python), "-I", "-m", "seabed_sidescan", "--help"], cwd=directory)
    _run([str(python), "-I", "-m", "seabed_sidescan", "--version"], cwd=directory)
    console = scripts / ("seabed-sidescan.exe" if sys.platform == "win32" else "seabed-sidescan")
    _require(console.is_file(), "Wheel console-script entry point is missing.")
    _run([str(console), "--version"], cwd=directory)


def verify(dist_dir: Path) -> None:
    dist_dir = dist_dir.expanduser().resolve()
    wheels = list(dist_dir.glob("*.whl"))
    sources = list(dist_dir.glob("*.tar.gz"))
    plugins = list(dist_dir.glob(f"{PLUGIN_NAME}-*-development.zip"))
    _require(len(wheels) == len(sources) == len(plugins) == 1,
             "Expected exactly one wheel, source distribution, and development plugin ZIP in dist-dir.")
    identity = _wheel_metadata(wheels[0])
    _check_plugin(plugins[0], identity[1])
    public_plugin = dist_dir / f"{PLUGIN_NAME}-{identity[1]}.zip"
    if public_plugin.is_file():
        _check_plugin(public_plugin, identity[1], development=False)
        development_payload = _plugin_payload(plugins[0])
        development_payload.pop(f"{PLUGIN_NAME}/DEVELOPMENT.txt")
        _require(_plugin_payload(public_plugin) == development_payload,
                 "Public and development plugins differ beyond the development marker.")
    with tempfile.TemporaryDirectory(prefix="seabed-distribution-check-") as temporary:
        work = Path(temporary)
        source = _extract_source(sources[0], work / "source")
        rebuilt_plugins = work / "rebuilt plugin"
        _run([sys.executable, str(source / "tools/build_qgis_plugin.py"), "--development",
              "--output-dir", str(rebuilt_plugins)], cwd=source)
        rebuilt_plugin = list(rebuilt_plugins.glob("*.zip"))
        _require(len(rebuilt_plugin) == 1, "Source distribution did not rebuild one plugin.")
        _check_plugin(rebuilt_plugin[0], identity[1])
        _require(_plugin_payload(rebuilt_plugin[0]) == _plugin_payload(plugins[0]),
                 "Source-rebuilt plugin differs in code, resources or legal notices.")
        if public_plugin.is_file():
            _run([sys.executable, str(source / "tools/build_qgis_plugin.py"),
                  "--output-dir", str(rebuilt_plugins)], cwd=source)
            rebuilt_public = rebuilt_plugins / public_plugin.name
            _check_plugin(rebuilt_public, identity[1], development=False)
            _require(_plugin_payload(rebuilt_public) == _plugin_payload(public_plugin),
                     "Source-rebuilt public plugin differs in code, resources or legal notices.")
        rebuilt_dir = work / "rebuilt"
        _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(rebuilt_dir), str(source)], cwd=work)
        rebuilt = list(rebuilt_dir.glob("*.whl"))
        _require(len(rebuilt) == 1, "Source distribution did not rebuild one wheel.")
        _require(_wheel_metadata(rebuilt[0]) == identity, "Rebuilt wheel project name/version differs.")
        _require(_wheel_payload(rebuilt[0]) == _wheel_payload(wheels[0]),
                 "Source-rebuilt wheel differs in package code, resources, metadata or license files.")
        _smoke_install(wheels[0], work / "wheel smoke", identity[1])
        _smoke_install(rebuilt[0], work / "source smoke", identity[1])
    print("Wheel, source distribution, and development plugin checks passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    try:
        verify(arguments.dist_dir)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
