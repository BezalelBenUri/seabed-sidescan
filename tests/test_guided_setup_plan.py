"""Exercise installer archive boundaries and isolated staging without QGIS."""

import hashlib
import importlib.util
import json
import stat
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "_seabed_guided_setup_plan_tests",
    ROOT / "qgis_plugin/seabed_sidescan_qgis/setup_plan.py",
)
PLAN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLAN
SPEC.loader.exec_module(PLAN)

VERSION = "0.1.0"


def source_archive(path, root="engine-source", extras=()):
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(f"{root}/pyproject.toml", "[build-system]\nrequires=[]\n")
        package.writestr(f"{root}/LICENSE", "Preserved license\n")
        for name, content in extras:
            if isinstance(name, str):
                member = zipfile.ZipInfo(name)
                # ZipInfo normally rewrites backslashes on Windows; retain the
                # actual hostile ZIP member name that extraction must reject.
                member.filename = name
                name = member
            package.writestr(name, content)
    return path


def record(path, **extra):
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        **extra,
    }


def write_manifest(resources, manifest):
    (resources / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def installation(tmp_path_factory, monkeypatch):
    # Keep Windows test paths short enough for the installer's actual prefix limit.
    base = tmp_path_factory.mktemp("gs")
    resources = base / "resources"
    resources.mkdir()
    engine = source_archive(resources / "engine.zip")
    raw = source_archive(resources / "raw.zip", root="raw-source")
    environments = {}
    for mode in ("core", "raw"):
        path = resources / f"{mode}.yml"
        path.write_text("channels: [conda-forge, nodefaults]\ndependencies: [python=3.12, pip]\n")
        environments[mode] = record(path)
    manifest = {
        "schema_version": 1,
        "engine_version": VERSION,
        "bundles": {
            "engine": record(engine, root="engine-source"),
            "raw": record(raw, root="raw-source"),
        },
        "environments": environments,
    }
    write_manifest(resources, manifest)
    monkeypatch.setattr(PLAN, "windows_64", lambda: True)
    monkeypatch.setattr(
        PLAN.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3)
    )
    return SimpleNamespace(root=base / "managed", resources=resources, manifest=manifest)


def prepare(installation, **kwargs):
    return PLAN.prepare_installation(
        installation.root, installation.resources, VERSION, **kwargs
    )


def test_source_extraction_preserves_regular_files_and_license(tmp_path):
    archive = source_archive(
        tmp_path / "source.zip",
        extras=[("engine-source/src/example.py", b"VALUE = 42\n")],
    )
    result = PLAN.extract_source(archive, tmp_path / "out", "engine-source")
    assert (result / "src/example.py").read_bytes() == b"VALUE = 42\n"
    assert (result / "LICENSE").read_text() == "Preserved license\n"


@pytest.mark.parametrize(
    "member",
    [
        "engine-source/../../escape.py",
        "../escape.py",
        "/engine-source/absolute.py",
        "engine-source\\escape.py",
        "engine-source/src/C:drive.py",
        "other-root/file.py",
        "engine-source/src/CON",
        "engine-source/src/aux.txt",
        "engine-source/src/NUL",
        "engine-source/src/LPT1.py",
        "engine-source/src/COM1.py",
        "engine-source/src/trailing.py.",
        "engine-source/src/trailing.py ",
    ],
)
def test_unsafe_source_names_are_rejected_before_any_extraction(tmp_path, member):
    archive = source_archive(tmp_path / "bad.zip", extras=[(member, "untrusted")])
    destination = tmp_path / "out"
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert not destination.exists()
    assert not (tmp_path / "escape.py").exists()


@pytest.mark.parametrize(
    "file_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK]
)
def test_nonregular_archive_entries_are_rejected(tmp_path, file_type):
    member = zipfile.ZipInfo("engine-source/src/special.py")
    member.create_system = 3
    member.external_attr = (file_type | 0o777) << 16
    archive = source_archive(tmp_path / "special.zip", extras=[(member, "target")])
    destination = tmp_path / "out"
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert not destination.exists()


def test_duplicate_archive_names_are_rejected_before_any_extraction(tmp_path):
    with pytest.warns(UserWarning, match="Duplicate name"):
        archive = source_archive(
            tmp_path / "duplicate.zip", extras=[("engine-source/LICENSE", "replacement")]
        )
    destination = tmp_path / "out"
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert not destination.exists()


def test_windows_case_aliases_are_rejected_on_every_host(tmp_path):
    archive = source_archive(
        tmp_path / "aliases.zip",
        extras=[
            ("engine-source/src/example.py", "first"),
            ("engine-source/src/EXAMPLE.PY", "second"),
        ],
    )
    destination = tmp_path / "out"
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert not destination.exists()


def test_file_parent_conflict_is_rejected_before_any_extraction(tmp_path):
    archive = source_archive(
        tmp_path / "conflict.zip",
        extras=[("engine-source/src", "file"), ("engine-source/src/module.py", "child")],
    )
    destination = tmp_path / "out"
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert not destination.exists()


def test_existing_directory_symlink_cannot_redirect_source_extraction(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "protected.py"
    protected.write_text("original")
    destination = tmp_path / "out"
    source_root = destination / "engine-source"
    source_root.mkdir(parents=True)
    try:
        (source_root / "src").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are unavailable in this test environment: {exc}")
    archive = source_archive(
        tmp_path / "redirect.zip", extras=[("engine-source/src/protected.py", "replacement")]
    )
    with pytest.raises(ValueError):
        PLAN.extract_source(archive, destination, "engine-source")
    assert protected.read_text() == "original"
    assert not (source_root / "LICENSE").exists()


@pytest.mark.parametrize("filename", ["../engine.zip", "nested/engine.zip", "C:\\engine.zip", "", ".", ".."])
def test_manifest_cannot_select_a_resource_outside_its_directory(installation, filename):
    installation.manifest["bundles"]["engine"]["filename"] = filename
    write_manifest(installation.resources, installation.manifest)
    with pytest.raises(ValueError):
        prepare(installation)
    assert not installation.root.exists()


@pytest.mark.parametrize("resource", ["engine", "raw", "environment"])
def test_tampered_sources_and_environment_specs_fail_before_staging(installation, resource):
    if resource == "environment":
        selected = installation.manifest["environments"]["raw"]
    else:
        selected = installation.manifest["bundles"][resource]
    path = installation.resources / selected["filename"]
    path.write_bytes(path.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="missing or damaged"):
        prepare(installation)
    assert not installation.root.exists()


@pytest.mark.parametrize("change", ["schema", "version", "missing-record", "invalid-json"])
def test_incomplete_or_incompatible_manifest_cannot_start_installation(installation, change):
    if change == "schema":
        installation.manifest["schema_version"] = 2
    elif change == "version":
        installation.manifest["engine_version"] = "999.0.0"
    elif change == "missing-record":
        del installation.manifest["bundles"]["engine"]
    write_manifest(installation.resources, installation.manifest)
    if change == "invalid-json":
        (installation.resources / "manifest.json").write_text("{invalid")
    with pytest.raises(ValueError):
        prepare(installation)
    assert not installation.root.exists()


def test_low_disk_preflight_preserves_an_existing_installation(installation, monkeypatch):
    installation.root.mkdir()
    previous = installation.root / "working-engine.txt"
    previous.write_bytes(b"keep this installation")
    monkeypatch.setattr(PLAN.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(ValueError, match="free"):
        prepare(installation)
    assert list(installation.root.iterdir()) == [previous]
    assert previous.read_bytes() == b"keep this installation"


def test_low_disk_preflight_does_not_create_a_requested_folder(installation, monkeypatch):
    monkeypatch.setattr(PLAN.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(ValueError, match="free"):
        prepare(installation)
    assert not installation.root.exists()


def test_unsupported_platform_fails_without_creating_installation_files(installation, monkeypatch):
    monkeypatch.setattr(PLAN, "windows_64", lambda: False)
    with pytest.raises(ValueError, match="64-bit Windows"):
        prepare(installation)
    assert not installation.root.exists()


def test_each_installation_stages_sources_away_from_the_previous_environment(installation):
    previous = installation.root / "installations" / "working" / "environment"
    previous.mkdir(parents=True)
    marker = previous / "working.txt"
    marker.write_bytes(b"existing engine")
    first = prepare(installation)
    second = prepare(installation)
    assert first.prefix != second.prefix
    assert first.prefix != previous and second.prefix != previous
    assert first.prefix.is_relative_to(installation.root / "installations")
    assert second.prefix.is_relative_to(installation.root / "installations")
    assert not first.prefix.exists() and not second.prefix.exists()
    for plan in (first, second):
        work = plan.prefix.parent
        assert plan.engine_source.is_relative_to(work / "sources")
        assert plan.raw_source.is_relative_to(work / "sources")
        assert (plan.engine_source / "LICENSE").is_file()
        assert (plan.raw_source / "LICENSE").is_file()
        assert plan.record.parent == work and plan.log.parent == work
    assert marker.read_bytes() == b"existing engine"


def test_core_only_setup_does_not_require_or_install_the_raw_backend(installation):
    del installation.manifest["bundles"]["raw"]
    write_manifest(installation.resources, installation.manifest)
    plan = prepare(installation, raw=False)
    assert plan.raw_source is None
    assert plan.environment == installation.resources / "core.yml"
    steps = plan.steps(installation.resources / "check.py")
    assert len(steps) == 3
    assert all("--raw-source" not in arguments for _, arguments, _ in steps)


def test_manifest_cannot_redirect_bootstrap_or_dependency_channels(installation):
    installation.manifest["bootstrap"] = {
        "url": "http://untrusted.invalid/tool.exe", "filename": "../../tool.exe"
    }
    installation.manifest["channels"] = ["http://untrusted.invalid/channel"]
    write_manifest(installation.resources, installation.manifest)
    plan = prepare(installation)
    checker = installation.resources / "check.py"
    steps = plan.steps(checker)
    bootstrap, create_arguments, _ = steps[0]
    assert bootstrap.is_relative_to(installation.root / "bootstrap")
    assert create_arguments[create_arguments.index("--channel") + 1] == "conda-forge"
    assert "--no-rc" in create_arguments and "--override-channels" in create_arguments
    assert "--strict-channel-priority" in create_arguments
    assert create_arguments[create_arguments.index("--prefix") + 1] == str(plan.prefix)
    assert create_arguments[create_arguments.index("--file") + 1] == str(plan.environment)
    assert not any("untrusted.invalid" in str(value) for command in steps for value in command)
    for executable, arguments, _ in steps[1:-1]:
        assert executable == plan.python
        assert "--isolated" in arguments
        assert "--no-deps" in arguments and "--no-build-isolation" in arguments
        assert arguments[-1] in {str(plan.engine_source), str(plan.raw_source)}
    assert steps[-1][0] == plan.python
    assert str(checker) in steps[-1][1]
