import subprocess
import sys
from pathlib import Path

import pytest

from seabed_sidescan.cli import _rewrite_runtime_config, main
from seabed_sidescan.paths import (
    default_project_root,
    project_dir,
    safe_project_name,
    sonar_files,
)


@pytest.mark.parametrize("name", [".", "..", "___", "...", "CON", "aux.txt", "LPT1", "project."])
def test_reject_nonportable_project_names(name):
    with pytest.raises(ValueError):
        safe_project_name(name)


def test_project_is_below_selected_root(tmp_path):
    result = project_dir("Survey 75m", tmp_path)
    assert result == tmp_path / "Survey_75m"
    assert result.parent == tmp_path


def test_installed_workspace_default_and_override(tmp_path, monkeypatch):
    monkeypatch.delenv("SSS_PROJECT_ROOT", raising=False)
    assert default_project_root(tmp_path) == tmp_path / "SSS_processing" / "projects"
    monkeypatch.setenv("SSS_PROJECT_ROOT", str(tmp_path / "custom"))
    assert default_project_root(tmp_path) == tmp_path / "custom"


def test_sonar_extensions_are_case_insensitive(tmp_path):
    for name in ("a.xTf", "B.JSF", "ignore.txt"):
        (tmp_path / name).touch()
    (tmp_path / "directory.xtf").mkdir()
    assert [path.name for path in sonar_files(tmp_path)] == ["a.xTf", "B.JSF"]


def test_cli_help_without_scientific_imports():
    result = subprocess.run(
        [sys.executable, "-c", "from seabed_sidescan.cli import build_parser; import sys; build_parser().parse_args(['--version'])"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    result = subprocess.run(
        [sys.executable, "-c", "from seabed_sidescan.cli import build_parser; import sys; assert 'rasterio' not in sys.modules; assert 'sklearn' not in sys.modules"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_module_entrypoint():
    result = subprocess.run([sys.executable, "-m", "seabed_sidescan", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "evaluate-clusters" in result.stdout


def test_packaged_runtime_template_handles_yaml_characters(tmp_path):
    import yaml

    from seabed_sidescan import __file__ as package_file

    template = Path(package_file).parent / "resources" / "sidescantools_project_info.yml"
    output = tmp_path / "runtime.yml"
    georef = tmp_path / "survey #1: processed" / "georef_out"
    preview = georef.parent / "previews"
    _rewrite_runtime_config(template, output, georef, preview, 0.5, 1.0)
    config = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert config["main_proc_params"]["georef_dir"] == georef.as_posix()
    assert config["main_proc_params"]["egn_table_path"] == (georef.parent / "EGN_table.npz").as_posix()
    assert config["georef_view_params"]["output_resolution"] == 0.5
    assert "D:/a" not in output.read_text(encoding="utf-8")


def test_raw_backend_missing_is_actionable(tmp_path, capsys):
    raw = tmp_path / "input.xtf"
    raw.touch()
    assert main(["process", "--project", "survey", "--input", str(raw),
                 "--sidescantools-repo", str(tmp_path / "absent"),
                 "--project-root", str(tmp_path / "projects"), "--dry-run"]) == 1
    assert "--sidescantools-repo" in capsys.readouterr().err
    assert not (tmp_path / "projects").exists()


def test_raw_backend_zero_exit_without_outputs_is_failure(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "input.xtf"
    raw.touch()
    repo = tmp_path / "backend"
    script = repo / "src" / "sidescantools" / "main_cli.py"
    script.parent.mkdir(parents=True)
    script.touch()
    monkeypatch.setattr("seabed_sidescan.cli._run_raw_backend", lambda *a, **k: 0)
    assert main(["process", "--project", "survey", "--input", str(raw),
                 "--sidescantools-repo", str(repo), "--sidescantools-python", sys.executable,
                 "--project-root", str(tmp_path / "projects")]) == 1
    assert "without creating or updating a GeoTIFF" in capsys.readouterr().err
