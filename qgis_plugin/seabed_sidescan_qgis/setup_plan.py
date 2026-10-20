"""Source-only installation planning; no QGIS or scientific imports."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MICROMAMBA_VERSION = "2.9.0-0"
MICROMAMBA_URL = (
    "https://github.com/mamba-org/micromamba-releases/releases/download/"
    + MICROMAMBA_VERSION + "/micromamba-win-64.exe"
)
MICROMAMBA_SHA256 = "a6d804394b2418991c4e29562853eaace2f2ce9d9da661a98e74e02e8dbb44b0"
MICROMAMBA_BYTES = 11454464
MINIMUM_FREE_BYTES = 6 * 1024 ** 3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def windows_64() -> bool:
    return os.name == "nt" and platform.machine().lower() in {"amd64", "x86_64"}


def resource_file(directory: Path, record: dict) -> Path:
    name = record["filename"]
    if (not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name
            or ":" in name or name.endswith((".", " "))):
        raise ValueError("Invalid installation resource filename.")
    path = directory / name
    if not path.is_file() or sha256(path) != record["sha256"]:
        raise ValueError(f"Installation resource is missing or damaged: {name}. Reinstall the plugin.")
    return path


def extract_source(archive: Path, destination: Path, root: str) -> Path:
    """Extract ordinary source files only, with size/path/link checks."""
    if not root or root in {".", ".."} or PurePosixPath(root).parts != (root,) or "\\" in root or ":" in root:
        raise ValueError("Invalid source root.")
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        if len(infos) > 1000 or sum(item.file_size for item in infos) > 16 * 1024 ** 2:
            raise ValueError("Installation source archive exceeds its expected size.")
        # Validate Windows names on every host so Linux builds and tests cannot
        # accept an archive that would alias files in the guided Windows setup.
        reserved = {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
        reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³")
        targets = {}
        for item in infos:
            # ZipInfo normalizes Windows backslashes in filename on Windows;
            # inspect the original archive spelling before that normalization.
            name = item.orig_filename
            path = PurePosixPath(name)
            parts = name.rstrip("/").split("/")
            file_type = stat.S_IFMT(item.external_attr >> 16)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or ":" in name or not path.parts or path.parts[0] != root
                    or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or (file_type == stat.S_IFDIR and not item.is_dir())
                    or (file_type == stat.S_IFREG and item.is_dir())
                    or any(not part or part in {".", ".."} or part.endswith((".", " "))
                           or part.split(".", 1)[0].rstrip(" .").upper() in reserved
                           or any(ord(character) < 32 or character in '<>:"|?*' for character in part)
                           for part in parts)):
                raise ValueError("Unsafe installation source archive member.")
            target = destination.joinpath(*path.parts).resolve()
            key = tuple(part.casefold() for part in path.parts)
            if (not target.is_relative_to(destination) or key in targets
                    or (target.exists() and not (item.is_dir() and target.is_dir()))):
                raise ValueError("Conflicting installation source archive member.")
            targets[key] = item.is_dir()
        for key in targets:
            if any(parent in targets and not targets[parent]
                   for parent in (key[:index] for index in range(1, len(key)))):
                raise ValueError("Conflicting installation source archive member.")
        for item in infos:
            target = destination.joinpath(*PurePosixPath(item.filename).parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    result = destination / root
    if not (result / "pyproject.toml").is_file() or not (result / "LICENSE").is_file():
        raise ValueError("Installation source is missing its project or license file.")
    return result


@dataclass(frozen=True)
class InstallationPlan:
    root: Path
    prefix: Path
    python: Path
    micromamba: Path
    environment: Path
    engine_source: Path
    raw_source: Path | None
    record: Path
    log: Path
    version: str

    def steps(self, checker: Path):
        commands = [
            (self.micromamba, ["--no-rc", "--root-prefix", str(self.root / "package-cache"),
              "create", "--yes", "--prefix", str(self.prefix), "--file", str(self.environment),
              "--override-channels", "--channel", "conda-forge", "--strict-channel-priority"],
             "Downloading and installing Python and processing dependencies…"),
            (self.python, ["-u", "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
              "--no-deps", "--no-build-isolation", str(self.engine_source)],
             "Installing Seabed Sidescan…"),
        ]
        if self.raw_source:
            commands.append((self.python, ["-u", "-m", "pip", "--isolated", "install",
                "--disable-pip-version-check", "--no-deps", "--no-build-isolation", str(self.raw_source)],
                "Installing raw-sonar processing tools…"))
        commands.append((self.python, ["-u", str(checker), "--version", self.version,
            "--record", str(self.record), *(["--raw-source", str(self.raw_source)] if self.raw_source else [])],
            "Checking the installed tools with a small processing example…"))
        return commands


def prepare_installation(root: Path, resources: Path, version: str, *, raw=True) -> InstallationPlan:
    if not windows_64():
        raise ValueError("Guided installation currently supports 64-bit Windows. Use Advanced settings for an existing engine on another platform.")
    root = root.expanduser().resolve()
    if len(str(root)) > 110:
        raise ValueError("Choose a shorter installation folder to allow room for processing-library filenames.")
    existing = root
    while not existing.exists():
        existing = existing.parent
    if not existing.is_dir():
        raise ValueError("Choose an installation folder, not a file.")
    if shutil.disk_usage(existing).free < MINIMUM_FREE_BYTES:
        raise ValueError("Choose an installation folder on a drive with at least 6 GB free for the tools and download cache.")
    try:
        manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or manifest["engine_version"] != version:
            raise ValueError("Installation resources do not match this plugin. Reinstall the plugin.")
        engine = resource_file(resources, manifest["bundles"]["engine"])
        backend = resource_file(resources, manifest["bundles"]["raw"]) if raw else None
        environment = resource_file(resources, manifest["environments"]["raw" if raw else "core"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Installation resources are incomplete. Reinstall the plugin ZIP.") from exc
    work = root / "installations" / (version + "-" + uuid.uuid4().hex[:10])
    work.mkdir(parents=True, exist_ok=False)
    engine_source = extract_source(engine, work / "sources", manifest["bundles"]["engine"]["root"])
    raw_source = extract_source(backend, work / "sources", manifest["bundles"]["raw"]["root"]) if backend else None
    prefix = work / "environment"
    return InstallationPlan(root, prefix, prefix / "python.exe", root / "bootstrap" / "micromamba-2.9.0.exe",
                            environment, engine_source, raw_source, work / "installation.json",
                            work / "setup.log", version)
