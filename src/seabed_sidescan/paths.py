from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SONAR_EXTENSIONS = {".xtf", ".jsf"}


@dataclass(frozen=True)
class SonarInput:
    path: Path
    files: tuple[Path, ...]
    source: str


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def solution_root() -> Path:
    """Return the repository root when installed in editable mode."""
    src_parent = package_dir().parent
    root = src_parent.parent
    if (root / "configs").exists() and (root / "scripts").exists():
        return root
    return Path.cwd().resolve()


def workspace_root(root: Path | None = None) -> Path:
    root = root or solution_root()
    return root.parent


def default_project_root(root: Path | None = None) -> Path:
    configured = os.environ.get("SSS_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    root = root or solution_root()
    # Preserve the original survey layout for repository users. Installed wheels
    # keep outputs below the working directory rather than writing to its parent.
    base = root.parent if (root / "src" / "seabed_sidescan").is_dir() else root
    return base / "SSS_processing" / "projects"


def safe_project_name(project_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", project_name.strip()).strip("_")
    if not safe_name or safe_name in {".", ".."} or not re.search(r"[A-Za-z0-9]", safe_name):
        raise ValueError("Project name must contain at least one letter or number.")
    if safe_name.endswith(".") or safe_name.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError("Project name must be a portable directory name.")
    return safe_name


def project_dir(project_name: str, project_root: Path | None = None) -> Path:
    root = (project_root or default_project_root()).resolve()
    result = (root / safe_project_name(project_name)).resolve()
    if result.parent != root:
        raise ValueError("Project directory must remain inside the project root.")
    return result


def latest_project(project_root: Path | None = None) -> Path:
    root = project_root or default_project_root()
    if not root.exists():
        raise FileNotFoundError(f"Project root not found: {root}")
    projects = [path for path in root.iterdir() if path.is_dir()]
    if not projects:
        raise FileNotFoundError(f"No project folders found in: {root}")
    return max(projects, key=lambda path: path.stat().st_mtime)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sonar_files(path: Path) -> tuple[Path, ...]:
    if not path.exists():
        return ()
    if path.is_file():
        return (path,) if path.suffix.lower() in SONAR_EXTENSIONS else ()
    files = [item for item in path.iterdir() if item.is_file() and item.suffix.lower() in SONAR_EXTENSIONS]
    return tuple(sorted(set(files), key=lambda item: item.name.lower()))


def resolve_sonar_input(
    input_path: str | Path | None = None,
    *,
    root: Path | None = None,
    purpose: str = "full",
) -> SonarInput:
    root = root or solution_root()

    if input_path:
        resolved = Path(input_path).expanduser().resolve()
        files = sonar_files(resolved)
        if not files:
            raise FileNotFoundError(
                f"Input path is missing or contains no .xtf or .jsf files: {resolved}"
            )
        return SonarInput(resolved, files, "explicit --input")

    candidates: list[Path] = []
    if os.environ.get("SSS_INPUT_PATH"):
        candidates.append(Path(os.environ["SSS_INPUT_PATH"]))

    if purpose == "test":
        candidates.extend(
            [
                root / "data" / "test_small",
                root / "data" / "test",
                workspace_root(root) / "SSS_processing" / "test_small",
            ]
        )

    candidates.extend(
        [
            root / "data" / "raw",
            root / "data" / "sss_raw",
            workspace_root(root) / "SSS RAW",
            workspace_root(root) / "SSS_raw",
            workspace_root(root) / "SSS",
        ]
    )

    checked: list[Path] = []
    for candidate in candidates:
        checked.append(candidate)
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        files = sonar_files(resolved)
        if files:
            return SonarInput(resolved, files, "auto-discovered")

    checked_text = "\n".join(f"  - {path}" for path in checked)
    raise FileNotFoundError(
        "No sonar input data was found automatically.\n"
        f"Checked:\n{checked_text}\n"
        'Run again with --input /path/to/sonar or set SSS_INPUT_PATH.'
    )

