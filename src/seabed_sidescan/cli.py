from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import uuid
from importlib import import_module
from pathlib import Path

from . import __version__
from .io import atomic_output, validate_paths
from .paths import (
    default_project_root,
    ensure_dir,
    latest_project,
    project_dir,
    resolve_sonar_input,
    safe_project_name,
    solution_root,
)

DEFAULT_COMBINED_MOSAIC = "SSS_combined_standard_mosaic.tif"


def _record_outputs(args, files) -> None:
    paths = tuple(Path(path).resolve() for path in files)
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError("Processing did not produce expected files: " + ", ".join(missing))
    args._outputs = paths


def _protect_manifest(args, inputs, outputs=()) -> None:
    manifest = getattr(args, "output_manifest", None)
    if manifest is not None:
        protected = [*inputs, *outputs]
        for path in tuple(protected):
            path = Path(path)
            if path.suffix.lower() == ".shp":
                protected.extend(path.with_suffix(suffix) for suffix in (".prj", ".dbf", ".shx", ".cpg", ".qix"))
        validate_paths(protected, [manifest])


def _path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _project_root(args) -> Path:
    return _path(args.project_root).resolve() if args.project_root else default_project_root()


def _project_dir(args) -> Path:
    root = _project_root(args)
    if getattr(args, "project", None):
        return project_dir(args.project, root)
    return latest_project(root)


def _rewrite_runtime_config(
    template_path: Path,
    runtime_path: Path,
    georef_dir: Path,
    preview_dir: Path,
    resolution: float,
    search_radius: float,
) -> None:
    import yaml

    if not template_path.exists():
        raise FileNotFoundError(f"Config template not found: {template_path}")
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config template must contain a YAML mapping.")
    for section in ("main_proc_params", "meta_infos", "georef_view_params"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Config template is missing mapping: {section}")
    config["main_proc_params"]["georef_dir"] = georef_dir.as_posix()
    config["main_proc_params"]["egn_table_path"] = (georef_dir.parent / "EGN_table.npz").as_posix()
    config["meta_infos"]["working_dir"] = preview_dir.as_posix()
    config["georef_view_params"].update(
        active_automatic_resolution=False,
        output_resolution=resolution,
        output_search_radius=search_radius,
    )
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _print_input_summary(resolved) -> None:
    total_bytes = sum(path.stat().st_size for path in resolved.files)
    print(f"Input source: {resolved.source}")
    print(f"Input path: {resolved.path}")
    print(f"Sonar files found: {len(resolved.files)}")
    print(f"Total input size: {total_bytes / (1024 ** 3):.2f} GB")


def _run_raw_backend(command, *, cwd, env) -> int:
    """Forward POSIX cancellation to the optional backend and its children."""
    process = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=(os.name == "posix"))
    previous_handlers = {}
    cancelled = False

    def interrupted(signum, frame):
        nonlocal cancelled
        cancelled = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        # A signal can interrupt Popen.wait while its internal waitpid lock is
        # held. Unwind that wait before waiting for the child in finally.
        raise SystemExit(128 + signum)

    try:
        if os.name == "posix" and threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[signum] = signal.signal(signum, interrupted)
        return process.wait()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if cancelled:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)


def cmd_list_input(args) -> int:
    resolved = resolve_sonar_input(args.input, root=solution_root(), purpose=args.purpose)
    _protect_manifest(args, resolved.files)
    _print_input_summary(resolved)
    print("")
    for path in resolved.files[: args.limit]:
        print(f"{path.name}\t{path.stat().st_size / (1024 ** 2):.2f} MB")
    if len(resolved.files) > args.limit:
        print(f"... {len(resolved.files) - args.limit} more file(s)")
    return 0


def cmd_process(args) -> int:
    if not math.isfinite(args.resolution) or args.resolution <= 0:
        raise ValueError("--resolution must be greater than 0")
    search_radius = args.search_radius if args.search_radius is not None else args.resolution * 2.0
    if not math.isfinite(search_radius) or search_radius <= 0:
        raise ValueError("--search-radius must be greater than 0")

    root = solution_root()
    project_root = _project_root(args)
    project_name = safe_project_name(args.project)
    current_project = project_dir(project_name, project_root)
    run_kind = safe_project_name(args.run_kind)
    try:
        pair = [int(channel.strip()) for channel in args.channel_pair.split(",")]
    except ValueError as exc:
        raise ValueError("--channel-pair must contain two distinct nonnegative channel indices.") from exc
    if len(pair) != 2 or min(pair) < 0 or pair[0] == pair[1]:
        raise ValueError("--channel-pair must contain two distinct nonnegative channel indices.")
    resolved_input = resolve_sonar_input(args.input, root=root, purpose="full")
    configured_repo = args.sidescantools_repo or os.environ.get("SIDESCANTOOLS_REPO")
    sidescantools_repo = (
        _path(configured_repo).resolve() if configured_repo else root / "vendor" / "sidescantools-main"
    )
    sidescantools_cli = sidescantools_repo / "src" / "sidescantools" / "main_cli.py"
    sidescantools_src = sidescantools_repo / "src"
    if not sidescantools_cli.exists():
        raise FileNotFoundError(
            "Raw sonar processing requires a separately configured, patched SidescanTools checkout. "
            "Set --sidescantools-repo or SIDESCANTOOLS_REPO. "
            f"CLI not found: {sidescantools_cli}"
        )
    backend_python = args.sidescantools_python or sys.executable
    if args.sidescantools_python:
        candidate = _path(backend_python)
        resolved_python = str(candidate.resolve()) if candidate.is_file() else shutil.which(backend_python)
        if resolved_python is None:
            raise FileNotFoundError(f"SidescanTools Python executable not found: {backend_python}")
        backend_python = resolved_python
    if not args.sidescantools_python and sys.version_info < (3, 12):
        raise ValueError("SidescanTools requires Python 3.12 or later; set --sidescantools-python.")
    georef_dir = current_project / "georef_out"
    preview_dir = current_project / "previews"
    config_dir = current_project / "configs"
    log_dir = current_project / "logs"
    for path in (current_project, georef_dir, preview_dir, config_dir, log_dir):
        ensure_dir(path)

    config_template = (
        _path(args.config).resolve() if args.config
        else Path(__file__).parent / "resources" / "sidescantools_project_info.yml"
    )
    runtime_config = config_dir / f"{run_kind}.runtime.yml"
    validate_paths([config_template], [runtime_config])
    _protect_manifest(args, [*resolved_input.files, config_template, sidescantools_cli, Path(backend_python)], [runtime_config])
    _rewrite_runtime_config(config_template, runtime_config, georef_dir, preview_dir, args.resolution, search_radius)

    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env["SIDESCANTOOLS_XTF_CHANNEL_PAIR"] = args.channel_pair
    backend_manifest = log_dir / f"{run_kind}.backend-{uuid.uuid4().hex}.json"
    env["SIDESCANTOOLS_RUN_MANIFEST"] = str(backend_manifest)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(sidescantools_src)
        if not existing_pythonpath
        else str(sidescantools_src) + os.pathsep + existing_pythonpath
    )
    interpreter_dir = Path(backend_python).parent
    backend_prefix = interpreter_dir.parent if interpreter_dir.name.lower() in {"bin", "scripts"} else interpreter_dir
    if (backend_prefix / "conda-meta").is_dir():
        # Calling a conda Python directly does not activate its DLL search path.
        # Use the selected backend's libraries without changing the caller's env.
        search_dirs = [backend_prefix, backend_prefix / "Scripts", backend_prefix / "Library" / "bin", backend_prefix / "bin"]
        env["PATH"] = os.pathsep.join(str(path) for path in search_dirs if path.is_dir()) + os.pathsep + env.get("PATH", "")
        env["CONDA_PREFIX"] = str(backend_prefix)
        for variable, directory, marker in (
            ("GDAL_DATA", backend_prefix / "Library" / "share" / "gdal", "gdalvrt.xsd"),
            ("PROJ_DATA", backend_prefix / "Library" / "share" / "proj", "proj.db"),
        ):
            if (directory / marker).is_file():
                env[variable] = str(directory)

    print(f"Project name: {project_name}")
    _print_input_summary(resolved_input)
    print(f"Channel pair: {args.channel_pair}")
    print(f"GeoTIFF resolution: {args.resolution:g} m")
    print(f"GeoTIFF search radius: {search_radius:g} m")
    print(f"Runtime config: {runtime_config}")
    print(f"GeoTIFF output folder: {georef_dir}")
    print(f"Preview output folder: {preview_dir}")
    print("")

    command = [backend_python, str(sidescantools_cli), str(resolved_input.path), str(runtime_config)]
    if args.dry_run:
        _record_outputs(args, [runtime_config])
        print("Dry run only. SidescanTools was not started.")
        print("Command that would run:")
        print(" ".join(f'"{part}"' if " " in part else part for part in command))
        return 0

    def geotiff_snapshot():
        return {
            path: (path.stat().st_mtime_ns, path.stat().st_size)
            for path in georef_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
        }

    previous_outputs = geotiff_snapshot()
    returncode = _run_raw_backend(command, cwd=sidescantools_repo, env=env)
    if returncode != 0:
        return returncode
    current_outputs = geotiff_snapshot()
    if not any(signature[1] > 0 and previous_outputs.get(path) != signature for path, signature in current_outputs.items()):
        raise RuntimeError(
            "SidescanTools exited without creating or updating a GeoTIFF. "
            "Inspect its georeferencing log; the backend can catch export errors internally."
        )
    produced = [path for path, signature in current_outputs.items() if previous_outputs.get(path) != signature]
    if backend_manifest.exists():
        report = json.loads(backend_manifest.read_text(encoding="utf-8"))
        if report.get("schema_version") != 1 or not isinstance(report.get("inputs"), list):
            raise RuntimeError("SidescanTools returned an invalid per-input run manifest.")
        inputs = report["inputs"]
        reported_paths = [Path(item["path"]).resolve() for item in inputs]
        if len(set(reported_paths)) != len(reported_paths) or set(reported_paths) != set(resolved_input.files):
            raise RuntimeError("SidescanTools did not report success for every selected input file.")
        reported_outputs = []
        for item in inputs:
            records = item.get("outputs", [])
            if len(records) != 2 or {record["channel"] for record in records} != {0, 1}:
                raise RuntimeError("SidescanTools must produce both logical output channels for each input.")
            for record in records:
                if Path(item["path"]).suffix.lower() == ".xtf" and record.get("input_channel") != pair[record["channel"]]:
                    raise RuntimeError("SidescanTools output channel does not match the selected raw input channel.")
                path = Path(record["path"]).resolve()
                if path not in produced:
                    raise RuntimeError("SidescanTools reported an unchanged, missing or unrelated output raster.")
                reported_outputs.append(path)
        if len(set(reported_outputs)) != len(reported_outputs):
            raise RuntimeError("SidescanTools reported the same output raster for multiple inputs.")
        produced = reported_outputs
    else:
        raise RuntimeError("Raw backend supplied no per-input run manifest. Apply the reviewed SidescanTools compatibility patch before processing.")
    import numpy as np
    import rasterio

    from .io import windows

    for path in produced:
        with rasterio.open(path) as dataset:
            if dataset.crs is None or dataset.count != 1:
                raise RuntimeError(f"Backend output must have one georeferenced raster band: {path}")
            valid_count = 0
            for window in windows(dataset.width, dataset.height):
                data = dataset.read(1, window=window, masked=True)
                valid_count += int(np.count_nonzero(~np.ma.getmaskarray(data) & np.isfinite(np.asarray(data))))
            if valid_count == 0:
                raise RuntimeError(f"Backend output contains no valid finite pixels: {path}")
    _record_outputs(args, [runtime_config, *produced, *([backend_manifest] if backend_manifest.exists() else [])])

    print("")
    print(f"Backend finished and GeoTIFF output was detected. Check coverage and logs in: {georef_dir}")
    return 0


def cmd_mosaic(args) -> int:
    from . import mosaic as mosaic_module
    if args.project or not args.georef_dir:
        current_project = _project_dir(args)
    else:
        current_project = _path(args.georef_dir).resolve().parent

    georef_dir = _path(args.georef_dir).resolve() if args.georef_dir else current_project / "georef_out"
    output_dir = _path(args.output_dir).resolve() if args.output_dir else current_project / "mosaics"
    report_dir = _path(args.report_dir).resolve() if args.report_dir else current_project / "qc"

    argv = [
        "--georef-dir",
        str(georef_dir),
        "--output-dir",
        str(output_dir),
        "--report-dir",
        str(report_dir),
        "--channels",
        *args.channels,
        "--min-valid-percent",
        str(args.min_valid_percent),
        "--min-std",
        str(args.min_std),
        "--min-percentile-range",
        str(args.min_percentile_range),
        "--edge-trim-percent",
        str(args.edge_trim_percent),
        "--feather-percent",
        str(args.feather_percent),
        "--balance-low-percentile",
        str(args.balance_low_percentile),
        "--balance-mid-percentile",
        str(args.balance_mid_percentile),
        "--balance-high-percentile",
        str(args.balance_high_percentile),
    ]
    if args.clean_output:
        argv.append("--clean-output")
    if args.include_review:
        argv.append("--include-review")
    if args.skip_combined:
        argv.append("--skip-combined")
    if args.also_raw:
        argv.append("--also-raw")
    _protect_manifest(args, [path for path in georef_dir.iterdir() if path.is_file()] if georef_dir.is_dir() else [])
    mosaics = mosaic_module.main(argv)
    _record_outputs(args, [*mosaics,
        *(path.with_name(f"{path.stem}_overlap_count.tif") for path in mosaics),
        report_dir / "strip_qc_report.csv", report_dir / "strip_balance_report.csv",
        report_dir / "mosaic_method_report.txt"])
    return 0


def cmd_mask(args) -> int:
    from . import mask as mask_module
    if args.project or not args.input_raster:
        current_project = _project_dir(args)
    else:
        current_project = _path(args.input_raster).resolve().parent.parent

    input_raster = (
        _path(args.input_raster).resolve()
        if args.input_raster
        else current_project / "mosaics" / DEFAULT_COMBINED_MOSAIC
    )
    output_mask = (
        _path(args.output_mask).resolve()
        if args.output_mask
        else current_project / "masks" / "SSS_valid_data_mask.tif"
    )
    argv = ["--input-raster", str(input_raster), "--output-mask", str(output_mask)]
    if args.boundary:
        boundary = _path(args.boundary).resolve()
        output_boundary_mask = (
            _path(args.output_boundary_mask).resolve()
            if args.output_boundary_mask
            else current_project / "masks" / "SSS_boundary_mask.tif"
        )
        argv.extend(
            [
                "--boundary",
                str(boundary),
                "--output-boundary-mask",
                str(output_boundary_mask),
            ]
        )
        if args.boundary_crs:
            argv.extend(["--boundary-crs", args.boundary_crs])
        if args.all_touched:
            argv.append("--all-touched")
    _protect_manifest(args, [input_raster, *([_path(args.boundary)] if args.boundary else [])],
                      [output_mask, *([output_boundary_mask] if args.boundary else [])])
    mask_module.main(argv)
    _record_outputs(args, [output_mask, *([output_boundary_mask] if args.boundary else [])])
    return 0


def cmd_clip_raster(args) -> int:
    from . import clip as clip_module
    if args.project or not args.input_raster:
        current_project = _project_dir(args)
    else:
        current_project = _path(args.input_raster).resolve().parent.parent

    input_raster = (
        _path(args.input_raster).resolve()
        if args.input_raster
        else current_project / "mosaics" / DEFAULT_COMBINED_MOSAIC
    )
    output_raster = (
        _path(args.output_raster).resolve()
        if args.output_raster
        else input_raster.with_name(f"{input_raster.stem}_AOI{input_raster.suffix}")
    )
    boundary = _path(args.boundary).resolve()

    argv = [
        "--input-raster",
        str(input_raster),
        "--boundary",
        str(boundary),
        "--output-raster",
        str(output_raster),
    ]
    if args.boundary_crs:
        argv.extend(["--boundary-crs", args.boundary_crs])
    if args.nodata is not None:
        argv.extend(["--nodata", str(args.nodata)])
    if args.all_touched:
        argv.append("--all-touched")
    if args.keep_extent:
        argv.append("--keep-extent")
    _protect_manifest(args, [input_raster, boundary], [output_raster])
    clip_module.main(argv)
    _record_outputs(args, [output_raster])
    return 0


def cmd_textures(args) -> int:
    from . import texture as texture_module
    if args.project or not args.input_raster:
        current_project = _project_dir(args)
    else:
        current_project = _path(args.input_raster).resolve().parent.parent

    input_raster = (
        _path(args.input_raster).resolve()
        if args.input_raster
        else current_project / "mosaics" / DEFAULT_COMBINED_MOSAIC
    )
    mask_raster = (
        _path(args.mask_raster).resolve()
        if args.mask_raster
        else current_project / "masks" / "SSS_valid_data_mask.tif"
    )
    output_dir = _path(args.output_dir).resolve() if args.output_dir else current_project / "textures"
    _protect_manifest(args, [input_raster, mask_raster], [output_dir / f"SSS_{name}.tif" for name in
        ("mean", "variance", "standard_deviation", "entropy", "contrast", "homogeneity", "ASM", "energy")])
    texture_module.main(
        [
            "--input-raster",
            str(input_raster),
            "--mask-raster",
            str(mask_raster),
            "--output-dir",
            str(output_dir),
            "--window-size",
            str(args.window_size),
            "--levels",
            str(args.levels),
            "--low-percentile",
            str(args.low_percentile),
            "--high-percentile",
            str(args.high_percentile),
            "--directions",
            args.directions,
        ]
    )
    _record_outputs(args, [output_dir / f"SSS_{name}.tif" for name in
        ("mean", "variance", "standard_deviation", "entropy", "contrast", "homogeneity", "ASM", "energy")])
    return 0


def default_feature_inputs(current_project: Path, include_redundant: bool = False):
    inputs = [
        current_project / "mosaics" / DEFAULT_COMBINED_MOSAIC,
        current_project / "textures" / "SSS_mean.tif",
        current_project / "textures" / "SSS_standard_deviation.tif",
        current_project / "textures" / "SSS_entropy.tif",
        current_project / "textures" / "SSS_contrast.tif",
        current_project / "textures" / "SSS_homogeneity.tif",
        current_project / "textures" / "SSS_energy.tif",
    ]
    names = [
        "SSS_corrected_relative_acoustic_intensity",
        "SSS_mean",
        "SSS_standard_deviation",
        "SSS_entropy",
        "SSS_contrast",
        "SSS_homogeneity",
        "SSS_energy",
    ]
    if include_redundant:
        inputs.extend(
            [
                current_project / "textures" / "SSS_variance.tif",
                current_project / "textures" / "SSS_ASM.tif",
            ]
        )
        names.extend(["SSS_variance", "SSS_ASM"])
    return inputs, names


def cmd_stack_features(args) -> int:
    from . import features as features_module

    current_project = (
        _path(args.input_rasters[0]).resolve().parent.parent
        if args.input_rasters and not args.project else _project_dir(args)
    )
    if args.input_rasters:
        input_rasters = [_path(path).resolve() for path in args.input_rasters]
        band_names = args.band_names
    else:
        input_rasters, band_names = default_feature_inputs(
            current_project, include_redundant=args.include_redundant
        )

    mask_raster = (
        _path(args.mask_raster).resolve()
        if args.mask_raster
        else current_project / "masks" / "SSS_valid_data_mask.tif"
    )
    output_stack = (
        _path(args.output_stack).resolve()
        if args.output_stack
        else current_project / "features" / "SSS_feature_stack.tif"
    )
    metadata_csv = (
        _path(args.metadata_csv).resolve()
        if args.metadata_csv
        else current_project / "features" / "SSS_feature_stack_bands.csv"
    )

    argv = [
        "--input-rasters",
        *[str(path) for path in input_rasters],
        "--mask-raster",
        str(mask_raster),
        "--output-stack",
        str(output_stack),
        "--metadata-csv",
        str(metadata_csv),
    ]
    if band_names:
        argv.extend(["--band-names", *band_names])
    _protect_manifest(args, [*input_rasters, mask_raster], [output_stack, metadata_csv])
    features_module.main(argv)
    _record_outputs(args, [output_stack, metadata_csv])
    return 0


def cmd_classify(args) -> int:
    classify_module = import_module(".classify", __package__)

    current_project = (
        _path(args.feature_stack).resolve().parent.parent
        if args.feature_stack and not args.project else _project_dir(args)
    )
    feature_stack = (
        _path(args.feature_stack).resolve()
        if args.feature_stack
        else current_project / "features" / "SSS_feature_stack.tif"
    )
    mask_raster = (
        _path(args.mask_raster).resolve()
        if args.mask_raster
        else current_project / "masks" / "SSS_valid_data_mask.tif"
    )
    output_dir = _path(args.output_dir).resolve() if args.output_dir else current_project / "classification"
    output_raster = (
        _path(args.output_raster).resolve()
        if args.output_raster
        else output_dir / f"SSS_acoustic_facies_k{args.classes}.tif"
    )
    report_csv = (
        _path(args.report_csv).resolve()
        if args.report_csv
        else output_dir / f"SSS_acoustic_facies_k{args.classes}_report.csv"
    )
    model_json = (
        _path(args.model_json).resolve()
        if args.model_json
        else output_dir / f"SSS_acoustic_facies_k{args.classes}_model.json"
    )

    argv = [
        "--feature-stack",
        str(feature_stack),
        "--mask-raster",
        str(mask_raster),
        "--output-raster",
        str(output_raster),
        "--report-csv",
        str(report_csv),
        "--model-json",
        str(model_json),
        "--classes",
        str(args.classes),
        "--sample-size",
        str(args.sample_size),
        "--n-init",
        str(args.n_init),
        "--max-iterations",
        str(args.max_iterations),
        "--tolerance",
        str(args.tolerance),
        "--seed",
        str(args.seed),
        "--chunk-rows",
        str(args.chunk_rows),
    ]
    if args.no_standardize:
        argv.append("--no-standardize")
    _protect_manifest(args, [feature_stack, mask_raster], [output_raster, report_csv, model_json])
    classify_module.main(argv)
    _record_outputs(args, [output_raster, report_csv, model_json])
    return 0


def cmd_evaluate_clusters(args) -> int:
    from . import evaluate as evaluate_module

    current_project = (
        _path(args.feature_stack).resolve().parent.parent
        if args.feature_stack and not args.project else _project_dir(args)
    )
    feature_stack = (
        _path(args.feature_stack).resolve()
        if args.feature_stack
        else current_project / "features" / "SSS_feature_stack.tif"
    )
    mask_raster = (
        _path(args.mask_raster).resolve()
        if args.mask_raster
        else current_project / "masks" / "SSS_valid_data_mask.tif"
    )
    output_dir = _path(args.output_dir).resolve() if args.output_dir else current_project / "classification"
    output_csv = (
        _path(args.output_csv).resolve()
        if args.output_csv
        else output_dir / "cluster_evaluation.csv"
    )
    summary_txt = (
        _path(args.summary_txt).resolve()
        if args.summary_txt
        else output_dir / "cluster_evaluation_summary.txt"
    )

    argv = [
        "--feature-stack",
        str(feature_stack),
        "--mask-raster",
        str(mask_raster),
        "--output-csv",
        str(output_csv),
        "--summary-txt",
        str(summary_txt),
        "--classes",
        *[str(value) for value in args.classes],
        "--sample-size",
        str(args.sample_size),
        "--metric-sample-size",
        str(args.metric_sample_size),
        "--runs",
        str(args.runs),
        "--n-init",
        str(args.n_init),
        "--max-iterations",
        str(args.max_iterations),
        "--tolerance",
        str(args.tolerance),
        "--seed",
        str(args.seed),
    ]
    if args.no_standardize:
        argv.append("--no-standardize")
    _protect_manifest(args, [feature_stack, mask_raster], [output_csv, summary_txt])
    evaluate_module.main(argv)
    _record_outputs(args, [output_csv, summary_txt])
    return 0


def cmd_clean_classification(args) -> int:
    from . import cleanup as cleanup_module

    current_project = (
        _path(args.input_raster).resolve().parent.parent
        if args.input_raster and not args.project else _project_dir(args)
    )
    input_raster = (
        _path(args.input_raster).resolve()
        if args.input_raster
        else current_project / "classification" / f"SSS_acoustic_facies_k{args.classes}.tif"
    )
    output_raster = (
        _path(args.output_raster).resolve()
        if args.output_raster
        else current_project / "classification" / f"SSS_acoustic_facies_k{args.classes}_cleaned.tif"
    )
    report_txt = (
        _path(args.report_txt).resolve()
        if args.report_txt
        else current_project / "classification" / f"SSS_acoustic_facies_k{args.classes}_cleanup_report.txt"
    )

    _protect_manifest(args, [input_raster], [output_raster, report_txt])
    cleanup_module.main(
        [
            "--input-raster",
            str(input_raster),
            "--output-raster",
            str(output_raster),
            "--report-txt",
            str(report_txt),
            "--majority-size",
            str(args.majority_size),
            "--min-patch-size",
            str(args.min_patch_size),
            "--nodata-label",
            str(args.nodata_label),
        ]
    )
    _record_outputs(args, [output_raster, report_txt])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seabed-sidescan",
        description="Project-aware side-scan processing utilities for seabed acoustic facies work.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_input = subparsers.add_parser("list-input", help="Show which sonar files will be processed.")
    list_input.add_argument("--input", help="Folder or single .xtf/.jsf file. If omitted, known project locations are checked.")
    list_input.add_argument("--purpose", choices=["full", "test"], default="full")
    list_input.add_argument("--limit", type=int, default=20)
    list_input.set_defaults(func=cmd_list_input)

    process = subparsers.add_parser("process", help="Run SidescanTools georeferencing for a named project.")
    process.add_argument("--project", required=True, help="Project folder name under the processing project root.")
    process.add_argument("--input", help="Folder or single .xtf/.jsf file. If omitted, known project locations are checked.")
    process.add_argument("--channel-pair", default="0,1", help='XTF channel indices in port,starboard order, for example "0,1" or "2,3". Does not select JSF subsystems.')
    process.add_argument(
        "--resolution",
        type=float,
        default=1.0,
        help="GeoTIFF strip pixel size in metres. Use 0.25 for high-detail mosaics, 0.5 or 1.0 for faster runs.",
    )
    process.add_argument(
        "--search-radius",
        type=float,
        help="GMT Nearneighbor search radius in metres. Defaults to 2 x --resolution.",
    )
    process.add_argument("--config", help="SidescanTools YAML template. Defaults to the packaged portable template.")
    process.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    process.add_argument("--sidescantools-repo", help="Path to SidescanTools repo. Defaults to vendor/sidescantools-main.")
    process.add_argument("--sidescantools-python", help="Python executable in the SidescanTools environment (Python >=3.12).")
    process.add_argument("--run-kind", default="full", help="Runtime config file prefix inside project/configs.")
    process.add_argument("--dry-run", action="store_true", help="Create/check paths and runtime config without starting SidescanTools.")
    process.set_defaults(func=cmd_process)

    mosaic = subparsers.add_parser(
        "mosaic",
        help="QC strips and build standard corrected sidescan mosaics.",
    )
    mosaic.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    mosaic.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    mosaic.add_argument("--georef-dir", help="Override GeoTIFF strip input folder.")
    mosaic.add_argument("--output-dir", help="Override mosaic output folder.")
    mosaic.add_argument("--report-dir", help="Override QC report folder.")
    mosaic.add_argument("--channels", nargs="+", default=["0", "1"])
    mosaic.add_argument("--min-valid-percent", type=float, default=1.0)
    mosaic.add_argument("--min-std", type=float, default=0.5)
    mosaic.add_argument("--min-percentile-range", type=float, default=2.0)
    mosaic.add_argument(
        "--edge-trim-percent",
        type=float,
        default=2.0,
        help="Set this percent of each strip edge to NoData before mosaicking.",
    )
    mosaic.add_argument(
        "--feather-percent",
        type=float,
        default=8.0,
        help="Down-weight this percent of each strip edge in overlap zones.",
    )
    mosaic.add_argument("--clean-output", action="store_true", help="Delete known old mosaic products before rebuilding.")
    mosaic.add_argument("--include-review", action="store_true")
    mosaic.add_argument("--skip-combined", action="store_true")
    mosaic.add_argument("--balance-low-percentile", type=float, default=10.0)
    mosaic.add_argument("--balance-mid-percentile", type=float, default=50.0)
    mosaic.add_argument("--balance-high-percentile", type=float, default=90.0)
    mosaic.add_argument("--also-raw", action="store_true", help="Also write raw acoustic-intensity mosaics for QC/audit comparison.")
    mosaic.set_defaults(func=cmd_mosaic)

    mask = subparsers.add_parser("mask", help="Create a 1/0 valid-data mask from a mosaic.")
    mask.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    mask.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    mask.add_argument("--input-raster", help=f"Input mosaic. Defaults to project/mosaics/{DEFAULT_COMBINED_MOSAIC}.")
    mask.add_argument("--output-mask", help="Output mask. Defaults to project/masks/SSS_valid_data_mask.tif.")
    mask.add_argument("--boundary", help="Optional polygon shapefile used to restrict all downstream analysis.")
    mask.add_argument("--boundary-crs", help="Override the boundary CRS if its .prj is missing or wrong.")
    mask.add_argument("--output-boundary-mask", help="Boundary-only mask output. Defaults to project/masks/SSS_boundary_mask.tif.")
    mask.add_argument("--all-touched", action="store_true", help="Include pixels touched by the boundary edge.")
    mask.set_defaults(func=cmd_mask)

    clip_raster = subparsers.add_parser("clip-raster", help="Mask and crop a raster to a polygon boundary.")
    clip_raster.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    clip_raster.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    clip_raster.add_argument("--input-raster", help=f"Raster to clip. Defaults to project/mosaics/{DEFAULT_COMBINED_MOSAIC}.")
    clip_raster.add_argument("--boundary", required=True, help="Polygon shapefile used for clipping.")
    clip_raster.add_argument("--output-raster", help="Output GeoTIFF. Defaults to the input name with _AOI appended.")
    clip_raster.add_argument("--boundary-crs", help="Override the boundary CRS if its .prj is missing or wrong.")
    clip_raster.add_argument("--nodata", type=float, help="Override output NoData.")
    clip_raster.add_argument("--all-touched", action="store_true", help="Include pixels touched by the boundary edge.")
    clip_raster.add_argument("--keep-extent", action="store_true", help="Mask outside the boundary without cropping the raster extent.")
    clip_raster.set_defaults(func=cmd_clip_raster)

    textures = subparsers.add_parser("textures", help="Extract local mean, standard deviation, entropy, and GLCM texture rasters.")
    textures.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    textures.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    textures.add_argument("--input-raster", help=f"Input SSS mosaic. Defaults to project/mosaics/{DEFAULT_COMBINED_MOSAIC}.")
    textures.add_argument("--mask-raster", help="Valid-data mask. Defaults to project/masks/SSS_valid_data_mask.tif.")
    textures.add_argument("--output-dir", help="Texture output folder. Defaults to project/textures.")
    textures.add_argument("--window-size", type=int, default=15)
    textures.add_argument("--levels", type=int, default=16)
    textures.add_argument("--low-percentile", type=float, default=2.0)
    textures.add_argument("--high-percentile", type=float, default=98.0)
    textures.add_argument("--directions", default="0,1;1,0;1,1;1,-1")
    textures.set_defaults(func=cmd_textures)

    stack_features = subparsers.add_parser("stack-features", help="Build the masked multi-band feature stack for classification.")
    stack_features.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    stack_features.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    stack_features.add_argument("--input-rasters", nargs="+", help="Override feature rasters. If omitted, default SSS mosaic and texture rasters are used.")
    stack_features.add_argument("--band-names", nargs="+", help="Names for --input-rasters. Must match raster count.")
    stack_features.add_argument("--mask-raster", help="Valid-data mask. Defaults to project/masks/SSS_valid_data_mask.tif.")
    stack_features.add_argument("--output-stack", help="Output multi-band GeoTIFF. Defaults to project/features/SSS_feature_stack.tif.")
    stack_features.add_argument("--metadata-csv", help="Output band metadata CSV. Defaults to project/features/SSS_feature_stack_bands.csv.")
    stack_features.add_argument("--include-redundant", action="store_true", help="Also include variance and ASM, which duplicate standard deviation and energy information.")
    stack_features.set_defaults(func=cmd_stack_features)

    evaluate_clusters = subparsers.add_parser("evaluate-clusters", help="Evaluate candidate k values before final classification.")
    evaluate_clusters.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    evaluate_clusters.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    evaluate_clusters.add_argument("--feature-stack", help="Feature stack. Defaults to project/features/SSS_feature_stack.tif.")
    evaluate_clusters.add_argument("--mask-raster", help="Valid-data mask. Defaults to project/masks/SSS_valid_data_mask.tif.")
    evaluate_clusters.add_argument("--output-dir", help="Evaluation output folder. Defaults to project/classification.")
    evaluate_clusters.add_argument("--output-csv", help="Output evaluation CSV. Defaults to project/classification/cluster_evaluation.csv.")
    evaluate_clusters.add_argument("--summary-txt", help="Output summary text file. Defaults to project/classification/cluster_evaluation_summary.txt.")
    evaluate_clusters.add_argument("--classes", nargs="+", type=int, default=[3, 4, 5, 6], help="Candidate class counts to evaluate.")
    evaluate_clusters.add_argument("--sample-size", type=int, default=200000, help="Maximum valid pixels sampled for fitting.")
    evaluate_clusters.add_argument("--metric-sample-size", type=int, default=5000, help="Maximum sampled pixels used for silhouette and related metrics.")
    evaluate_clusters.add_argument("--runs", type=int, default=3, help="Repeated model fits per k for stability scoring.")
    evaluate_clusters.add_argument("--n-init", type=int, default=50, help="KMeans initializations per run.")
    evaluate_clusters.add_argument("--max-iterations", type=int, default=500)
    evaluate_clusters.add_argument("--tolerance", type=float, default=1e-4)
    evaluate_clusters.add_argument("--seed", type=int, default=42)
    evaluate_clusters.add_argument("--no-standardize", action="store_true")
    evaluate_clusters.set_defaults(func=cmd_evaluate_clusters)

    classify = subparsers.add_parser("classify", help="Run unsupervised k-means acoustic facies classification.")
    classify.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    classify.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    classify.add_argument("--feature-stack", help="Feature stack. Defaults to project/features/SSS_feature_stack.tif.")
    classify.add_argument("--mask-raster", help="Valid-data mask. Defaults to project/masks/SSS_valid_data_mask.tif.")
    classify.add_argument("--output-dir", help="Classification output folder. Defaults to project/classification.")
    classify.add_argument("--output-raster", help="Output class raster. Defaults to project/classification/SSS_acoustic_facies_kN.tif.")
    classify.add_argument("--report-csv", help="Output class report CSV.")
    classify.add_argument("--model-json", help="Output model metadata JSON.")
    classify.add_argument("--classes", type=int, default=4, help="Number of acoustic facies clusters.")
    classify.add_argument("--sample-size", type=int, default=200000, help="Maximum valid pixels sampled for k-means fitting.")
    classify.add_argument("--n-init", type=int, default=50, help="Number of k-means initializations. Higher values reduce local-minimum risk.")
    classify.add_argument("--max-iterations", type=int, default=500)
    classify.add_argument("--tolerance", type=float, default=1e-4)
    classify.add_argument("--seed", type=int, default=42)
    classify.add_argument("--chunk-rows", type=int, default=256)
    classify.add_argument("--no-standardize", action="store_true", help="Cluster on raw feature values instead of z-scored features.")
    classify.set_defaults(func=cmd_classify)

    clean = subparsers.add_parser("clean-classification", help="Conservatively clean isolated pixel noise in a class raster.")
    clean.add_argument("--project", help="Project folder name. If omitted, the newest project is used.")
    clean.add_argument("--project-root", help="Root folder for project outputs. Defaults to SSS_PROJECT_ROOT or the local processing workspace.")
    clean.add_argument("--classes", type=int, default=4, help="Class count suffix used to find the default classification raster.")
    clean.add_argument("--input-raster", help="Input classification raster. Defaults to project/classification/SSS_acoustic_facies_kN.tif.")
    clean.add_argument("--output-raster", help="Output cleaned raster. Defaults to project/classification/SSS_acoustic_facies_kN_cleaned.tif.")
    clean.add_argument("--report-txt", help="Cleanup report path. Defaults to project/classification/SSS_acoustic_facies_kN_cleanup_report.txt.")
    clean.add_argument("--majority-size", type=int, default=3, help="Odd local majority filter size. Default is 3.")
    clean.add_argument("--min-patch-size", type=int, default=25, help="Connected patches smaller than this are replaced.")
    clean.add_argument("--nodata-label", type=int, default=0, help="Class value reserved for NoData/outside coverage.")
    clean.set_defaults(func=cmd_clean_classification)

    for subparser in subparsers.choices.values():
        subparser.add_argument("--output-manifest", type=Path,
                              help="Write a JSON list of files produced by this successful run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.output_manifest:
            explicit_inputs = []
            for field in ("input", "input_raster", "input_rasters", "mask_raster", "feature_stack", "boundary", "config"):
                value = getattr(args, field, None)
                if value:
                    explicit_inputs.extend(Path(item) for item in (value if isinstance(value, list) else [value]))
            validate_paths(explicit_inputs, [args.output_manifest])
        result = args.func(args)
        if result == 0 and args.output_manifest:
            outputs = getattr(args, "_outputs", ())
            validate_paths(outputs, [args.output_manifest])
            with atomic_output(args.output_manifest) as staged:
                staged.write_text(json.dumps({"schema_version": 1, "command": args.command,
                    "package_version": __version__, "outputs": [str(path) for path in outputs]}, indent=2), encoding="utf-8")
        return result
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
