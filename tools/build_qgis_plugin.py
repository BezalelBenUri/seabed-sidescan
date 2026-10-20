"""Build a source-only plugin ZIP with guided setup resources and no survey data."""

from __future__ import annotations

import argparse
import configparser
import re
import zipfile
from pathlib import Path
from runpy import run_path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "seabed_sidescan_qgis"


def build_plugin(output_dir: Path, *, development: bool = False) -> Path:
    source = ROOT / "qgis_plugin" / PLUGIN_NAME
    # Support direct scripts, module imports, and run_path-based build checks.
    build_setup_resources = run_path(str(ROOT / "tools" / "build_setup_resources.py"))["build_setup_resources"]
    build_setup_resources(ROOT, source / "resources" / "setup")
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(source / "metadata.txt", encoding="utf-8-sig")
    general = metadata["general"]
    version = general["version"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[a-zA-Z0-9.-]*)", version):
        raise ValueError("Plugin version is not a safe archive filename.")
    package_version = re.search(
        r'^__version__ = "([^"]+)"',
        (ROOT / "src" / "seabed_sidescan" / "__init__.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    ).group(1)
    if package_version != version:
        raise ValueError("Plugin and engine versions must match.")
    missing = []
    if not (ROOT / "LICENSE").is_file():
        missing.append("the owner's selected LICENSE")
    for field in ("name", "description", "about", "author", "email", "qgisMinimumVersion", "license"):
        if not general.get(field, "").strip():
            missing.append(field)
    for field in ("homepage", "repository", "tracker"):
        value = general.get(field, "")
        if urlparse(value).scheme not in {"https", "http"} or not urlparse(value).netloc:
            missing.append(f"a public {field} URL")
    if missing and not development:
        raise ValueError("Public-release metadata is incomplete: " + ", ".join(missing))
    for required in ("__init__.py", "metadata.txt", "plugin.py", "provider.py", "engine.py", "icon.svg", "README.md"):
        if not (source / required).is_file():
            raise ValueError(f"Required plugin source is missing: {required}")
    suffix = "-development" if development else ""
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{PLUGIN_NAME}-{version}{suffix}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(source).parts):
                if (path.suffix in {".py", ".txt", ".md", ".svg", ".ui", ".html", ".json", ".yml"}
                        or path.name == "LICENSE"
                        or (path.suffix == ".zip" and path.parent == source / "resources" / "setup")):
                    if "tests" not in path.relative_to(source).parts and path.name != "LICENSE":
                        package.write(path, (Path(PLUGIN_NAME) / path.relative_to(source)).as_posix())
        for name in ("LICENSE", "NOTICE"):
            if (ROOT / name).is_file():
                package.write(ROOT / name, f"{PLUGIN_NAME}/{name}")
        if development:
            package.writestr(
                f"{PLUGIN_NAME}/DEVELOPMENT.txt",
                "Local evaluation build. Not prepared for public submission.\n"
                + ("Missing release information: " + ", ".join(missing) + "\n" if missing else ""),
            )
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("Plugin archive failed its integrity check.")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--development", action="store_true", help="Build a local evaluation ZIP even when license/contact/URLs are unset.")
    args = parser.parse_args()
    try:
        print(build_plugin(args.output_dir, development=args.development))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
