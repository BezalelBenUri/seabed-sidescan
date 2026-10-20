"""Build deterministic source bundles and specs for guided QGIS engine setup.

No downloaded dependency, native library, survey data, or GUI dependency is
included. A source distribution without vendor/ can reuse its verified bundled
CLI source while rebuilding the engine from its own current source files.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_PATH = Path("qgis_plugin/seabed_sidescan_qgis/resources/setup")
RAW_MODULES = (
    "__init__", "aux_functions", "cfg_parser", "egn_table_build", "georef_thread",
    "jsf", "main_cli", "sidescan_file", "sidescan_preproc", "xtf_wrapper",
)
RAW_SOURCE_FILES = tuple(f"src/sidescantools/{name}.py" for name in RAW_MODULES) + (
    "LICENSE", "THIRD_PARTY.md", "README.md", "pyproject.toml", "environment_cli.yml",
    "sidescan_out/project_info.yml", "sidescan_out/project_info_schema.json",
)
RAW_BUNDLE_README = """# Reviewed SidescanTools CLI source subset

This archive contains the complete Python source used by the optional raw
XTF/JSF command-line backend, its configuration examples, upstream GPL license,
and recorded local modifications. See LICENSE and THIRD_PARTY.md for licensing,
upstream attribution, and the explicitly unproven original vendoring commit.

Upstream GUI modules, artwork, generated egg-info, and compiled files are omitted.
The existing optional-GUI import block in __init__.py permits CLI-only use.
main_cli.py keeps PLOTTING=False; this distribution does not expose the upstream
GUI or optional matplotlib plotting branch. The processing source is otherwise
preserved; only source-text encoding and newlines are normalized by the builder.

The guided installer provisions the separate scientific/native dependencies
from conda-forge into an isolated environment, then installs this source with
pip --no-deps --no-build-isolation. It does not require a public Seabed Sidescan
release URL. The CLI entry script is src/sidescantools/main_cli.py; its parent
src directory must be on PYTHONPATH when invoked as a script.

This archive contains no survey data. Nominal geometry, empirical navigation
smoothing, and layback assumptions still require independent survey validation.
"""


def _text(path: Path) -> bytes:
    """Normalize source text so archives match on Windows and Unix checkouts."""
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _version(root: Path) -> str:
    tree = ast.parse((root / "src/seabed_sidescan/__init__.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[a-zA-Z0-9.-]*)", version):
                return version
    raise ValueError("Engine source has no valid literal __version__.")


def _engine_sources(root: Path) -> dict[str, bytes]:
    result = {name: _text(root / name) for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE")}
    source = root / "src/seabed_sidescan"
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and "__pycache__" not in relative.parts and path.suffix in {".py", ".typed", ".yml"}:
            result[relative.as_posix()] = _text(path)
    for name in ("__init__.py", "api.py", "cli.py", "resources/sidescantools_project_info.yml"):
        if f"src/seabed_sidescan/{name}" not in result:
            raise ValueError(f"Required engine source is missing: {name}")
    return result


def _raw_sources(root: Path) -> dict[str, bytes]:
    vendor = root / "vendor/sidescantools-main"
    result = {name: _text(vendor / name) for name in RAW_SOURCE_FILES}
    result["BUNDLE_README.md"] = RAW_BUNDLE_README.encode("utf-8")
    return result


def _read_existing_raw(root: Path, output_dir: Path) -> dict[str, bytes]:
    """Recover only the exact source allowlist from a checksum-verified bundle."""
    for location in dict.fromkeys((output_dir, root / RESOURCE_PATH)):
        manifest_path = location / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise ValueError("Existing setup resource manifest has an unsupported schema.")
        record = manifest["bundles"]["raw"]
        if record["filename"] != "sidescantools-cli-source.zip" or record["root"] != "sidescantools-cli-source":
            raise ValueError("Existing raw bundle has unexpected paths.")
        archive = location / record["filename"]
        if _digest(archive.read_bytes()) != record["sha256"]:
            raise ValueError("Existing raw source bundle checksum does not match its manifest.")
        expected = set(RAW_SOURCE_FILES) | {"BUNDLE_README.md"}
        result = {}
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None:
                raise ValueError("Existing raw source bundle is corrupt.")
            for info in package.infolist():
                parts = PurePosixPath(info.filename).parts
                if (len(parts) < 2 or parts[0] != record["root"] or ".." in parts
                        or "\\" in info.filename or info.is_dir() or info.file_size > 2_000_000
                        or (info.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError("Existing raw source bundle contains an unsafe member.")
                name = PurePosixPath(*parts[1:]).as_posix()
                if name not in expected or name in result:
                    raise ValueError("Existing raw source bundle contains unexpected or duplicate files.")
                data = package.read(info)
                data.decode("utf-8")
                if record.get("files", {}).get(name, _digest(data)) != _digest(data):
                    raise ValueError("Existing raw source file checksum mismatch.")
                result[name] = data
        if result.keys() != expected:
            raise ValueError("Existing raw source bundle is incomplete.")
        return result
    raise FileNotFoundError("No vendor source or verified packaged raw CLI source bundle was found.")


def _write_atomic(destination: Path, data: bytes) -> None:
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        staging.write_bytes(data)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _archive(output_dir: Path, filename: str, archive_root: str, sources: dict[str, bytes]) -> dict:
    staging = output_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for name, data in sorted(sources.items()):
                info = zipfile.ZipInfo(f"{archive_root}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(info, data, compresslevel=9)
        digest = _digest(staging.read_bytes())
        os.replace(staging, output_dir / filename)
    finally:
        staging.unlink(missing_ok=True)
    return {"filename": filename, "sha256": digest, "root": archive_root,
            "files": {name: _digest(data) for name, data in sorted(sources.items())}}


def build_setup_resources(root: Path, output_dir: Path) -> Path:
    """Build setup resources and return their manifest path; no network needed."""
    root = Path(root).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    version = _version(root)
    engine_sources = _engine_sources(root)
    raw_sources = (_raw_sources(root) if (root / "vendor/sidescantools-main").is_dir()
                   else _read_existing_raw(root, output_dir))
    specs = {
        mode: _text(root / "requirements" / f"managed_{mode}_environment.yml")
        for mode in ("core", "raw")
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "engine_version": version,
        "bundles": {
            "engine": _archive(output_dir, "engine-source.zip", "engine-source", engine_sources),
            "raw": _archive(output_dir, "sidescantools-cli-source.zip", "sidescantools-cli-source", raw_sources),
        },
        "environments": {},
    }
    for mode, data in specs.items():
        filename = f"environment-{mode}.yml"
        _write_atomic(output_dir / filename, data)
        manifest["environments"][mode] = {"filename": filename, "sha256": _digest(data)}
    destination = output_dir / "manifest.json"
    _write_atomic(destination, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.root / RESOURCE_PATH
    try:
        print(build_setup_resources(args.root, output_dir))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
