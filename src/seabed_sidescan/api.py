"""Public, explicit-path interface to the side-scan processing tools.

Scientific dependencies are imported only when an operation is called. All paths
in the returned results are absolute. Operations overwrite their output files;
callers should select a separate destination when preserving previous products.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from .io import validate_paths

PathLike = str | Path


@dataclass(frozen=True)
class RawProcessingResult:
    project_dir: Path
    georef_dir: Path
    runtime_config: Path
    previews_dir: Path


@dataclass(frozen=True)
class TextureResult:
    output_dir: Path
    rasters: tuple[Path, ...]


@dataclass(frozen=True)
class FeatureStackResult:
    output_stack: Path
    metadata_csv: Path


@dataclass(frozen=True)
class ClassificationResult:
    output_raster: Path
    report_csv: Path
    model_json: Path


@dataclass(frozen=True)
class EvaluationResult:
    output_csv: Path
    summary_txt: Path


@dataclass(frozen=True)
class CleanupResult:
    output_raster: Path
    report_txt: Path


@dataclass(frozen=True)
class MosaicResult:
    mosaics: tuple[Path, ...]
    overlap_counts: tuple[Path, ...]
    qc_report: Path
    balance_report: Path
    method_report: Path


def _path(value: PathLike) -> Path:
    return Path(value).expanduser().resolve()


def _distinct(inputs: Sequence[Path], outputs: Sequence[Path]) -> None:
    """Reject accidental in-place writes and collisions between output files."""
    validate_paths(inputs, outputs)


def _run(module: str, arguments: list[str]):
    try:
        return import_module(f".{module}", __package__).main(arguments)
    except SystemExit as exc:
        if exc.code:
            raise ValueError(str(exc)) from exc


def process_sonar(
    input_path: PathLike,
    project_root: PathLike,
    project_name: str,
    *,
    sidescantools_repo: PathLike,
    sidescantools_python: PathLike | None = None,
    channel_pair: tuple[int, int] = (0, 1),
    resolution: float = 1.0,
    search_radius: float | None = None,
    config: PathLike | None = None,
    dry_run: bool = False,
) -> RawProcessingResult:
    """Run the optional, separately installed SidescanTools XTF/JSF backend.

    The backend requires its own compatible Python and GMT environment. A dry
    run writes the runtime configuration without executing conversion. A normal
    run requires a successful backend exit and a new or updated GeoTIFF; callers
    must independently inspect output coverage and scientific correctness.
    ``channel_pair`` selects XTF channel indices in port, starboard order. JSF
    remains experimental and uses the first detected subsystem; this argument
    does not change that subsystem.
    """
    cli = import_module(".cli", __package__)
    paths = import_module(".paths", __package__)
    source, root, backend = _path(input_path), _path(project_root), _path(sidescantools_repo)
    arguments = [
        "process", "--input", str(source), "--project-root", str(root),
        f"--project={project_name}", "--sidescantools-repo", str(backend),
        "--channel-pair=" + ",".join(map(str, channel_pair)),
        "--resolution", str(resolution),
    ]
    if sidescantools_python is not None:
        arguments += ["--sidescantools-python", str(sidescantools_python)]
    if search_radius is not None:
        arguments += ["--search-radius", str(search_radius)]
    if config is not None:
        arguments += ["--config", str(_path(config))]
    if dry_run:
        arguments.append("--dry-run")
    args = cli.build_parser().parse_args(arguments)
    returncode = cli.cmd_process(args)
    if returncode:
        raise RuntimeError(f"SidescanTools backend exited with status {returncode}.")
    current_project = paths.project_dir(project_name, root).resolve()
    return RawProcessingResult(
        current_project, current_project / "georef_out",
        current_project / "configs" / "full.runtime.yml", current_project / "previews",
    )


def create_mask(
    input_raster: PathLike,
    output_mask: PathLike,
    *,
    boundary: PathLike | None = None,
    boundary_crs: str | None = None,
    output_boundary_mask: PathLike | None = None,
    all_touched: bool = False,
) -> Path:
    """Write a 1/0 valid-data mask, optionally intersected with a shapefile."""
    source, output = _path(input_raster), _path(output_mask)
    outputs = [output]
    arguments = ["--input-raster", str(source), "--output-mask", str(output)]
    inputs = [source]
    if boundary is not None:
        inputs.append(_path(boundary))
        arguments += ["--boundary", str(inputs[-1])]
        if boundary_crs is not None:
            arguments += ["--boundary-crs", boundary_crs]
        if all_touched:
            arguments.append("--all-touched")
        if output_boundary_mask is not None:
            outputs.append(_path(output_boundary_mask))
            arguments += ["--output-boundary-mask", str(outputs[-1])]
    elif output_boundary_mask is not None or boundary_crs is not None or all_touched:
        raise ValueError("Boundary options require a boundary shapefile.")
    _distinct(inputs, outputs)
    _run("mask", arguments)
    return output


def extract_textures(
    input_raster: PathLike,
    mask_raster: PathLike,
    output_dir: PathLike,
    *,
    window_size: int = 15,
    levels: int = 16,
    low_percentile: float = 2.0,
    high_percentile: float = 98.0,
    directions: str = "0,1;1,0;1,1;1,-1",
) -> TextureResult:
    """Extract eight texture rasters on the input grid using the analysis mask."""
    source, mask, destination = _path(input_raster), _path(mask_raster), _path(output_dir)
    names = ("mean", "variance", "standard_deviation", "entropy", "contrast", "homogeneity", "ASM", "energy")
    outputs = tuple(destination / f"SSS_{name}.tif" for name in names)
    _distinct([source, mask], outputs)
    _run("texture", [
        "--input-raster", str(source), "--mask-raster", str(mask),
        "--output-dir", str(destination), "--window-size", str(window_size),
        "--levels", str(levels), "--low-percentile", str(low_percentile),
        "--high-percentile", str(high_percentile), "--directions", directions,
    ])
    return TextureResult(destination, outputs)


def stack_features(
    input_rasters: Sequence[PathLike],
    mask_raster: PathLike,
    output_stack: PathLike,
    *,
    band_names: Sequence[str] | None = None,
    metadata_csv: PathLike | None = None,
) -> FeatureStackResult:
    """Stack aligned rasters into float feature bands with NaN outside the mask."""
    sources = [_path(path) for path in input_rasters]
    if not sources:
        raise ValueError("At least one input raster is required.")
    if band_names is not None and len(band_names) != len(sources):
        raise ValueError("band_names must contain one name for each input raster.")
    mask, output = _path(mask_raster), _path(output_stack)
    metadata = _path(metadata_csv) if metadata_csv is not None else output.with_name(f"{output.stem}_bands.csv")
    _distinct([*sources, mask], [output, metadata])
    arguments = ["--input-rasters", *map(str, sources), "--mask-raster", str(mask),
                 "--output-stack", str(output), "--metadata-csv", str(metadata)]
    if band_names is not None:
        arguments += ["--band-names", *band_names]
    _run("features", arguments)
    return FeatureStackResult(output, metadata)


def classify(
    feature_stack: PathLike,
    mask_raster: PathLike,
    output_raster: PathLike,
    *,
    classes: int = 4,
    report_csv: PathLike | None = None,
    model_json: PathLike | None = None,
    sample_size: int = 200000,
    n_init: int = 50,
    max_iterations: int = 500,
    tolerance: float = 1e-4,
    seed: int = 42,
    chunk_rows: int = 256,
    standardize: bool = True,
) -> ClassificationResult:
    """Fit KMeans and classify valid features; class 0 denotes NoData.

    The area report requires a projected CRS whose horizontal units are metres.
    """
    source, mask, output = _path(feature_stack), _path(mask_raster), _path(output_raster)
    report = _path(report_csv) if report_csv is not None else output.with_name(f"{output.stem}_report.csv")
    model = _path(model_json) if model_json is not None else output.with_name(f"{output.stem}_model.json")
    _distinct([source, mask], [output, report, model])
    arguments = [
        "--feature-stack", str(source), "--mask-raster", str(mask),
        "--output-raster", str(output), "--report-csv", str(report), "--model-json", str(model),
        "--classes", str(classes), "--sample-size", str(sample_size), "--n-init", str(n_init),
        "--max-iterations", str(max_iterations), "--tolerance", str(tolerance),
        "--seed", str(seed), "--chunk-rows", str(chunk_rows),
    ]
    if not standardize:
        arguments.append("--no-standardize")
    _run("classify", arguments)
    return ClassificationResult(output, report, model)


def evaluate_clusters(
    feature_stack: PathLike,
    mask_raster: PathLike,
    output_dir: PathLike,
    *,
    classes: Sequence[int] = (3, 4, 5, 6),
    output_csv: PathLike | None = None,
    summary_txt: PathLike | None = None,
    sample_size: int = 200000,
    metric_sample_size: int = 5000,
    runs: int = 3,
    n_init: int = 50,
    max_iterations: int = 500,
    tolerance: float = 1e-4,
    seed: int = 42,
    standardize: bool = True,
) -> EvaluationResult:
    """Compare candidate class counts using internal clustering metrics."""
    if not classes:
        raise ValueError("At least one candidate class count is required.")
    source, mask, destination = _path(feature_stack), _path(mask_raster), _path(output_dir)
    report = _path(output_csv) if output_csv is not None else destination / "cluster_evaluation.csv"
    summary = _path(summary_txt) if summary_txt is not None else destination / "cluster_evaluation_summary.txt"
    _distinct([source, mask], [report, summary])
    arguments = [
        "--feature-stack", str(source), "--mask-raster", str(mask),
        "--output-csv", str(report), "--summary-txt", str(summary),
        "--classes", *map(str, classes), "--sample-size", str(sample_size),
        "--metric-sample-size", str(metric_sample_size), "--runs", str(runs),
        "--n-init", str(n_init), "--max-iterations", str(max_iterations),
        "--tolerance", str(tolerance), "--seed", str(seed),
    ]
    if not standardize:
        arguments.append("--no-standardize")
    _run("evaluate", arguments)
    return EvaluationResult(report, summary)


def clean_classification(
    input_raster: PathLike,
    output_raster: PathLike,
    *,
    report_txt: PathLike | None = None,
    majority_size: int = 3,
    min_patch_size: int = 25,
    nodata_label: int = 0,
) -> CleanupResult:
    """Write a cartographic majority/patch cleanup while preserving NoData."""
    source, output = _path(input_raster), _path(output_raster)
    report = _path(report_txt) if report_txt is not None else output.with_name(f"{output.stem}_cleanup_report.txt")
    _distinct([source], [output, report])
    _run("cleanup", [
        "--input-raster", str(source), "--output-raster", str(output),
        "--report-txt", str(report), "--majority-size", str(majority_size),
        "--min-patch-size", str(min_patch_size), "--nodata-label", str(nodata_label),
    ])
    return CleanupResult(output, report)


def clip_raster(
    input_raster: PathLike,
    boundary: PathLike,
    output_raster: PathLike,
    *,
    boundary_crs: str | None = None,
    nodata: float | None = None,
    all_touched: bool = False,
    keep_extent: bool = False,
) -> Path:
    """Clip a raster to an ESRI polygon shapefile and return the output path."""
    source, polygon, output = _path(input_raster), _path(boundary), _path(output_raster)
    _distinct([source, polygon], [output])
    arguments = ["--input-raster", str(source), "--boundary", str(polygon), "--output-raster", str(output)]
    if boundary_crs is not None:
        arguments += ["--boundary-crs", boundary_crs]
    if nodata is not None:
        arguments += ["--nodata", str(nodata)]
    if all_touched:
        arguments.append("--all-touched")
    if keep_extent:
        arguments.append("--keep-extent")
    _run("clip", arguments)
    return output


def build_mosaics(
    georef_dir: PathLike,
    output_dir: PathLike,
    report_dir: PathLike | None = None,
    *,
    channels: Sequence[str | int] = ("0", "1"),
    min_valid_percent: float = 1.0,
    min_std: float = 0.5,
    min_percentile_range: float = 2.0,
    edge_trim_percent: float = 2.0,
    feather_percent: float = 8.0,
    balance_low_percentile: float = 10.0,
    balance_mid_percentile: float = 50.0,
    balance_high_percentile: float = 90.0,
    include_review: bool = False,
    skip_combined: bool = False,
    also_raw: bool = False,
    clean_output: bool = False,
) -> MosaicResult:
    """QC georeferenced strips and build channel and combined mosaics.

    Inputs currently use SidescanTools ``_ch0_``/``_ch1_`` filenames. Large
    surveys require sufficient memory for complete mosaic grids.
    """
    source, destination = _path(georef_dir), _path(output_dir)
    report = _path(report_dir) if report_dir is not None else destination.parent / "qc"
    if source == destination:
        raise ValueError("Mosaic input and output directories must differ.")
    channel_names = tuple(str(channel) for channel in channels)
    if not channel_names or any(not channel.isdigit() or len(channel) != 1 for channel in channel_names):
        raise ValueError("channels must contain one or more single-digit channel numbers.")
    if len(set(channel_names)) != len(channel_names):
        raise ValueError("channels must not contain duplicates.")
    arguments = [
        "--georef-dir", str(source), "--output-dir", str(destination),
        "--report-dir", str(report), "--channels", *channel_names,
        "--min-valid-percent", str(min_valid_percent), "--min-std", str(min_std),
        "--min-percentile-range", str(min_percentile_range),
        "--edge-trim-percent", str(edge_trim_percent), "--feather-percent", str(feather_percent),
        "--balance-low-percentile", str(balance_low_percentile),
        "--balance-mid-percentile", str(balance_mid_percentile),
        "--balance-high-percentile", str(balance_high_percentile),
    ]
    for enabled, flag in ((include_review, "--include-review"), (skip_combined, "--skip-combined"),
                          (also_raw, "--also-raw"), (clean_output, "--clean-output")):
        if enabled:
            arguments.append(flag)
    mosaics = _run("mosaic", arguments)
    if not mosaics:
        raise ValueError("No mosaic was produced; inspect the strip QC and balance reports.")
    counts = tuple(path.with_name(f"{path.stem}_overlap_count.tif") for path in mosaics)
    return MosaicResult(mosaics, counts, report / "strip_qc_report.csv",
                        report / "strip_balance_report.csv", report / "mosaic_method_report.txt")
