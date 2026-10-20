"""QGIS Processing definitions mapping native controls to the public CLI."""

import json
import re
import shlex
import tempfile
from pathlib import Path

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingOutputFolder,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingProvider,
)
from qgis.PyQt.QtGui import QIcon

from .engine import (
    checked_python,
    configured_raw_python,
    configured_raw_repo,
    run_engine,
)

RAW_OVERRIDES = {"SIDESCANTOOLS_REPO", "SIDESCANTOOLS_PYTHON"}


def _file_signature(path):
    try:
        info = path.stat()
        return (info.st_size, info.st_mtime_ns, info.st_ctime_ns) if path.is_file() else None
    except FileNotFoundError:
        return None


def _read_manifest(path, command):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1 or document.get("command") != command:
            raise ValueError("unexpected manifest schema or command")
        values = document["outputs"]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("outputs must be a list of file paths")
        paths = {Path(value).resolve() for value in values if Path(value).is_absolute()}
        if len(paths) != len(values):
            raise ValueError("output paths must be absolute and distinct")
        for output in paths:
            if not output.is_file() or output.stat().st_size == 0:
                raise ValueError(f"missing or empty output: {output}")
        return paths
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise QgsProcessingException(f"The engine did not provide a valid output manifest: {exc}") from exc


def field(name, label, kind, default=None, minimum=None, maximum=None, optional=False):
    return dict(name=name, label=label, kind=kind, default=default, minimum=minimum,
                maximum=maximum, optional=optional)


def raster(name, label):
    return field(name, label, "raster")


def number(name, label, default, minimum=0, maximum=None, integer=False):
    return field(name, label, "integer" if integer else "number", default, minimum, maximum)


FIT_FIELDS = [
    number("SAMPLE_SIZE", "Maximum training pixels", 200000, 2, integer=True),
    number("N_INIT", "K-means initializations", 50, 1, integer=True),
    number("MAX_ITERATIONS", "Maximum iterations", 500, 1, integer=True),
    number("TOLERANCE", "Convergence tolerance", 0.0001, 0),
    number("SEED", "Random seed", 42, 0, integer=True),
    field("NO_STANDARDIZE", "Use original feature scales (disable standardization)", "boolean", False),
]

DEFINITIONS = [
    ("process", "0. Georeference raw sonar", [
        field("INPUT", "Folder containing raw XTF or JSF files", "folder"),
        field("PROJECT", "Survey folder name (letters, numbers, . _ -)", "string", "survey"),
        field("PROJECT_ROOT", "Output root for survey folders", "output_folder"),
        field("SIDESCANTOOLS_REPO", "Raw backend source folder override (blank uses setup)", "folder", optional=True),
        field("SIDESCANTOOLS_PYTHON", "Raw backend Python override (blank uses setup)", "file", optional=True),
        field("CHANNEL_PAIR", "XTF port,starboard channel indices (not a JSF subsystem selector)", "string", "0,1"),
        number("RESOLUTION", "GeoTIFF pixel size in metres", 1.0, 0.001),
        field("SEARCH_RADIUS", "Optional search radius in metres (default: twice pixel size)", "number", minimum=0.001, optional=True),
        field("CONFIG", "Optional SidescanTools YAML configuration", "file", optional=True),
    ]),
    ("mosaic", "1. Mosaic georeferenced strips", [
        field("GEOREF_DIR", "Folder of georeferenced GeoTIFF strips", "folder"),
        field("OUTPUT_DIR", "Mosaic output folder", "output_folder"),
        field("REPORT_DIR", "Quality-control report folder", "output_folder"),
        field("CHANNELS", "Channel identifiers separated by spaces", "words", "0 1"),
        number("MIN_VALID_PERCENT", "Minimum valid pixels (%)", 1.0, 0, 100),
        number("MIN_STD", "Minimum standard deviation", 0.5),
        number("MIN_PERCENTILE_RANGE", "Minimum percentile range", 2.0),
        number("EDGE_TRIM_PERCENT", "Strip edge trim (%)", 2.0, 0, 49.99),
        number("FEATHER_PERCENT", "Overlap feather (%)", 8.0, 0, 49.99),
        number("BALANCE_LOW_PERCENTILE", "Balance low percentile", 10.0, 0, 100),
        number("BALANCE_MID_PERCENTILE", "Balance middle percentile", 50.0, 0, 100),
        number("BALANCE_HIGH_PERCENTILE", "Balance high percentile", 90.0, 0, 100),
        field("INCLUDE_REVIEW", "Include strips marked for review", "boolean", False),
        field("SKIP_COMBINED", "Skip combined-channel mosaic", "boolean", False),
        field("ALSO_RAW", "Also produce raw intensity audit mosaics", "boolean", False),
    ]),
    ("mask", "2. Create valid-data mask", [
        raster("INPUT_RASTER", "Input mosaic"),
        field("BOUNDARY", "Optional polygon boundary", "boundary", optional=True),
        field("OUTPUT_MASK", "Valid-data mask", "output_raster"),
        field("OUTPUT_BOUNDARY_MASK", "Boundary footprint mask (when a boundary is supplied)", "output_raster", optional=True),
        field("ALL_TOUCHED", "Include every pixel touched by the polygon", "boolean", False),
    ]),
    ("textures", "3. Extract texture features", [
        raster("INPUT_RASTER", "Input mosaic"),
        raster("MASK_RASTER", "Valid-data mask"),
        field("OUTPUT_DIR", "Texture output folder", "output_folder"),
        number("WINDOW_SIZE", "Window width in pixels (odd)", 15, 3, integer=True),
        number("LEVELS", "GLCM quantization levels", 16, 4, 32, integer=True),
        number("LOW_PERCENTILE", "Low quantization percentile", 2.0, 0, 100),
        number("HIGH_PERCENTILE", "High quantization percentile", 98.0, 0, 100),
        field("DIRECTIONS", "GLCM row,column offsets separated by semicolons", "string", "0,1;1,0;1,1;1,-1"),
    ]),
    ("stack-features", "4. Stack feature rasters", [
        field("INPUT_RASTERS", "Feature rasters in band order", "rasters"),
        raster("MASK_RASTER", "Valid-data mask"),
        field("BAND_NAMES", "Optional band names (space separated; quote names containing spaces)", "words", "", optional=True),
        field("OUTPUT_STACK", "Multiband feature stack", "output_raster"),
        field("METADATA_CSV", "Band metadata", "csv"),
    ]),
    ("evaluate-clusters", "5. Evaluate candidate class counts", [
        raster("FEATURE_STACK", "Multiband feature stack"),
        raster("MASK_RASTER", "Valid-data mask"),
        field("CLASSES", "Candidate class counts separated by spaces", "integers", "3 4 5 6"),
        number("METRIC_SAMPLE_SIZE", "Maximum pixels for cluster metrics", 5000, 2, integer=True),
        number("RUNS", "Repeated model fits per class count", 3, 1, integer=True),
        *FIT_FIELDS,
        field("OUTPUT_CSV", "Cluster evaluation table", "csv"),
        field("SUMMARY_TXT", "Evaluation summary", "txt"),
    ]),
    ("classify", "6. Classify acoustic facies (k-means)", [
        raster("FEATURE_STACK", "Multiband feature stack"),
        raster("MASK_RASTER", "Valid-data mask"),
        number("CLASSES", "Number of acoustic facies clusters", 4, 2, 255, integer=True),
        *FIT_FIELDS,
        number("CHUNK_ROWS", "Prediction rows per chunk", 256, 1, integer=True),
        field("OUTPUT_RASTER", "Acoustic facies raster", "output_raster"),
        field("REPORT_CSV", "Class statistics table", "csv"),
        field("MODEL_JSON", "Model metadata", "json"),
    ]),
    ("clean-classification", "7. Clean classification raster", [
        raster("INPUT_RASTER", "Classification raster"),
        number("MAJORITY_SIZE", "Majority filter width in pixels (odd)", 3, 3, integer=True),
        number("MIN_PATCH_SIZE", "Minimum connected patch size in pixels", 25, 1, integer=True),
        number("NODATA_LABEL", "Class value reserved for NoData", 0, 0, 255, integer=True),
        field("OUTPUT_RASTER", "Cleaned classification raster", "output_raster"),
        field("REPORT_TXT", "Cleanup report", "txt"),
    ]),
    ("clip-raster", "Clip a raster to a polygon", [
        raster("INPUT_RASTER", "Input raster"),
        field("BOUNDARY", "Polygon boundary", "boundary"),
        field("OUTPUT_RASTER", "Clipped raster", "output_raster"),
        field("NODATA", "Optional output NoData value", "number", optional=True),
        field("ALL_TOUCHED", "Include every pixel touched by the polygon", "boolean", False),
        field("KEEP_EXTENT", "Keep the input extent", "boolean", False),
    ]),
]


class SeabedSidescanAlgorithm(QgsProcessingAlgorithm):
    def __init__(self, definition):
        super().__init__()
        self.definition = definition
        self.command, self.title, self.fields = definition

    def name(self):
        return self.command.replace("-", "_")

    def displayName(self):
        return self.title

    def group(self):
        return "Seabed Sidescan"

    def groupId(self):
        return "seabed_sidescan"

    def createInstance(self):
        return SeabedSidescanAlgorithm(self.definition)

    def shortHelpString(self):
        if self.command == "process":
            return (
                "Convert raw XTF/JSF files using the processing tools configured in "
                "Raster > Seabed Sidescan > Set up processing tools. Run setup with raw-sonar "
                "support before the first conversion. Choose the input survey folder, output "
                "root, XTF port/starboard channel pair and pixel size here. JSF is experimental: "
                "only envelope data from the first detected subsystem with matching "
                "port/starboard pings is accepted. Advanced parameters can override the "
                "configured raw backend source folder and Python interpreter when using a "
                "separately maintained SidescanTools environment with GMT. Blank overrides use "
                "the latest setup selection. Outputs go to output root / survey name / "
                "georef_out and can be loaded automatically. A successful adapter run only confirms "
                "that GeoTIFF files were produced; inspect navigation, coverage and the georeferencing "
                "log. Synthetic adapter tests do not establish survey positioning accuracy. "
                "Cancel stops the worker and may leave partial outputs."
            )
        return (
            "Runs the seabed-sidescan backend in a separate process. Use "
            "Raster > Seabed Sidescan > Set up processing tools before the first run. "
            "Raster inputs must be local files; export database, web or virtual layers to "
            "GeoTIFF first. Polygon inputs, including selections and memory layers, are "
            "converted to shapefiles automatically. All operations use explicit input and "
            "output paths. Class values describe unsupervised acoustic clusters. Existing "
            "files at the selected output paths may be overwritten."
        )

    def initAlgorithm(self, config=None):
        for spec in self.fields:
            name, label, kind = spec["name"], spec["label"], spec["kind"]
            optional, default = spec["optional"], spec["default"]
            if kind == "raster":
                parameter = QgsProcessingParameterRasterLayer(name, label)
            elif kind == "rasters":
                parameter = QgsProcessingParameterMultipleLayers(name, label, layerType=QgsProcessing.TypeRaster)
            elif kind == "boundary":
                parameter = QgsProcessingParameterFeatureSource(name, label, types=[QgsProcessing.TypeVectorPolygon], optional=optional)
            elif kind == "folder":
                parameter = QgsProcessingParameterFile(name, label, behavior=QgsProcessingParameterFile.Folder, optional=optional)
            elif kind == "file":
                kwargs = {"optional": optional}
                if name == "CONFIG":
                    kwargs["fileFilter"] = "YAML files (*.yml *.yaml)"
                parameter = QgsProcessingParameterFile(name, label, **kwargs)
            elif kind == "output_folder":
                parameter = QgsProcessingParameterFolderDestination(name, label)
            elif kind == "output_raster":
                parameter = QgsProcessingParameterRasterDestination(name, label, optional=optional, createByDefault=not optional)
            elif kind in ("csv", "txt", "json"):
                parameter = QgsProcessingParameterFileDestination(name, label, fileFilter=f"{kind.upper()} files (*.{kind})")
            elif kind in ("number", "integer"):
                kwargs = dict(defaultValue=default, optional=optional)
                if spec["minimum"] is not None:
                    kwargs["minValue"] = spec["minimum"]
                if spec["maximum"] is not None:
                    kwargs["maxValue"] = spec["maximum"]
                parameter = QgsProcessingParameterNumber(name, label, type=(QgsProcessingParameterNumber.Integer if kind == "integer" else QgsProcessingParameterNumber.Double), **kwargs)
            elif kind == "boolean":
                parameter = QgsProcessingParameterBoolean(name, label, defaultValue=default)
            else:
                parameter = QgsProcessingParameterString(name, label, defaultValue=default, optional=optional)
            if name in RAW_OVERRIDES:
                parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(parameter)
        if self.command in ("process", "mosaic", "textures"):
            self.addParameter(QgsProcessingParameterBoolean("LOAD_OUTPUTS", "Load generated rasters into QGIS", defaultValue=True))
            self.addOutput(QgsProcessingOutputMultipleLayers("OUTPUT_RASTERS", "Generated rasters"))
        if self.command == "process":
            self.addOutput(QgsProcessingOutputFolder("GEOREF_DIR", "Georeferenced GeoTIFF folder"))

    @staticmethod
    def _project_name(value):
        reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) or value.endswith(".") or value.split(".")[0].upper() in reserved:
            raise QgsProcessingException(
                "Use a survey folder name starting with a letter or number and containing only "
                "letters, numbers, periods, underscores or hyphens. Reserved Windows names and "
                "a final period are not supported."
            )
        return value

    @staticmethod
    def _raster_path(layer):
        if layer is None:
            raise QgsProcessingException("Could not resolve an input raster layer.")
        path = Path(layer.source().split("|")[0]).expanduser()
        if layer.providerType() != "gdal" or not path.is_file():
            raise QgsProcessingException(
                f"Raster '{layer.name()}' must be a local file. Export this layer to GeoTIFF first."
            )
        return str(path.resolve())

    def _raw_backend_paths(self, parameters, context):
        repository = self.parameterAsFile(parameters, "SIDESCANTOOLS_REPO", context).strip() or configured_raw_repo()
        python = self.parameterAsFile(parameters, "SIDESCANTOOLS_PYTHON", context).strip() or configured_raw_python()
        setup = (
            "Open Raster > Seabed Sidescan > Set up processing tools and install raw-sonar "
            "support, or supply your backend paths under Advanced parameters."
        )
        if not repository or not python:
            raise QgsProcessingException("Raw-sonar processing tools are not set up. " + setup)
        repository = Path(repository).expanduser().resolve()
        if not (repository / "src" / "sidescantools" / "main_cli.py").is_file():
            raise QgsProcessingException("The configured raw backend source folder is unavailable or incomplete. " + setup)
        try:
            python = checked_python(python)
        except QgsProcessingException as exc:
            raise QgsProcessingException("The configured raw backend Python executable is unavailable. " + setup) from exc
        return {"SIDESCANTOOLS_REPO": str(repository), "SIDESCANTOOLS_PYTHON": python}

    def processAlgorithm(self, parameters, context, feedback):
        executable = checked_python()
        raw_paths = self._raw_backend_paths(parameters, context) if self.command == "process" else {}
        arguments, outputs = [self.command], {}
        project_name = None
        input_paths = []
        with tempfile.TemporaryDirectory(prefix="seabed_qgis_") as working:
            for spec in self.fields:
                name, kind = spec["name"], spec["kind"]
                flag = "--" + name.lower().replace("_", "-")
                if kind == "boolean":
                    if self.parameterAsBool(parameters, name, context):
                        arguments.append(flag)
                    continue
                if name in raw_paths:
                    value = raw_paths[name]
                elif kind == "raster":
                    value = self._raster_path(self.parameterAsRasterLayer(parameters, name, context))
                    input_paths.append(value)
                elif kind == "rasters":
                    value = [self._raster_path(layer) for layer in self.parameterAsLayerList(parameters, name, context)]
                    input_paths.extend(value)
                    if not value:
                        raise QgsProcessingException("Choose at least one feature raster.")
                elif kind == "boundary":
                    source = self.parameterAsSource(parameters, name, context)
                    if source is None:
                        if spec["optional"]:
                            continue
                        raise QgsProcessingException("Choose a polygon boundary.")
                    if not source.sourceCrs().isValid():
                        raise QgsProcessingException("The polygon boundary needs a valid coordinate reference system.")
                    original = self.parameterAsVectorLayer(parameters, name, context)
                    if original is not None:
                        original_path = Path(original.source().split("|")[0]).expanduser()
                        if original_path.is_file():
                            input_paths.append(str(original_path.resolve()))
                    value = self.parameterAsCompatibleSourceLayerPath(parameters, name, context, ["shp"], "shp", feedback)
                    value = str(Path(value).expanduser().resolve())
                    input_paths.append(value)
                elif kind == "output_raster":
                    value = self.parameterAsOutputLayer(parameters, name, context)
                    if not value:
                        continue
                    value = str(Path(value).expanduser().resolve())
                    if Path(value).suffix.lower() not in (".tif", ".tiff"):
                        raise QgsProcessingException("Raster outputs must use a GeoTIFF (.tif or .tiff) file path.")
                    outputs[name] = value
                elif kind in ("csv", "txt", "json", "output_folder"):
                    value = self.parameterAsFileOutput(parameters, name, context)
                    value = str(Path(value).expanduser().resolve())
                    outputs[name] = value
                elif kind == "folder":
                    value = str(Path(self.parameterAsFile(parameters, name, context)).expanduser().resolve())
                elif kind == "file":
                    value = self.parameterAsFile(parameters, name, context)
                    if not value and spec["optional"]:
                        continue
                    value = str(Path(value).expanduser().resolve())
                    if name == "SIDESCANTOOLS_PYTHON":
                        value = checked_python(value)
                elif kind in ("number", "integer"):
                    if spec["optional"] and parameters.get(name) in (None, ""):
                        continue
                    value = (self.parameterAsInt if kind == "integer" else self.parameterAsDouble)(parameters, name, context)
                else:
                    value = self.parameterAsString(parameters, name, context).strip()
                    if self.command == "process" and name == "PROJECT":
                        project_name = self._project_name(value)
                        value = project_name
                    if spec["optional"] and not value:
                        continue
                    if kind in ("words", "integers"):
                        try:
                            value = shlex.split(value)
                            if not value:
                                raise ValueError("enter at least one value")
                            if kind == "integers":
                                value = [int(item) for item in value]
                                if min(value) < 2 or max(value) > 255:
                                    raise ValueError("class counts must be between 2 and 255")
                        except ValueError as exc:
                            raise QgsProcessingException(f"{spec['label']}: {exc}") from exc
                arguments.append(flag)
                arguments.extend(map(str, value if isinstance(value, list) else [value]))

            if self.command == "mask":
                has_boundary = "--boundary" in arguments
                if not has_boundary and "OUTPUT_BOUNDARY_MASK" in outputs:
                    raise QgsProcessingException("A polygon boundary is required to create a boundary footprint mask.")
                if has_boundary and "OUTPUT_BOUNDARY_MASK" not in outputs:
                    arguments.extend(["--output-boundary-mask", str(Path(working) / "boundary_mask.tif")])
            if self.command in ("classify", "evaluate-clusters"):
                destination = outputs.get("OUTPUT_RASTER") or outputs["OUTPUT_CSV"]
                arguments.extend(["--output-dir", str(Path(destination).parent)])
            output_files = {}
            for name, destination in outputs.items():
                path = Path(destination).expanduser().resolve()
                if path in {Path(item) for item in input_paths}:
                    raise QgsProcessingException("Choose an output path different from every input file.")
                if any(f["name"] == name and f["kind"] == "output_folder" for f in self.fields):
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    if path in output_files:
                        raise QgsProcessingException("Choose a different file path for each output.")
                    output_files[path] = _file_signature(path)
                    path.parent.mkdir(parents=True, exist_ok=True)
            raster_directory = None
            if self.command == "process":
                raster_directory = Path(outputs["PROJECT_ROOT"]) / project_name / "georef_out"
            elif self.command in ("mosaic", "textures"):
                raster_directory = Path(outputs["OUTPUT_DIR"])
            manifest = Path(working) / "outputs.json"
            arguments.extend(["--output-manifest", str(manifest)])
            run_engine(arguments, feedback, executable, working)
            produced = _read_manifest(manifest, self.command)
            for path, previous in output_files.items():
                signature = _file_signature(path)
                if path not in produced or signature is None or signature == previous:
                    raise QgsProcessingException(
                        f"The engine exited without creating or updating the expected output: {path}"
                    )
        if self.command in ("process", "mosaic", "textures"):
            if self.command == "process":
                outputs["GEOREF_DIR"] = str(raster_directory)
            paths = sorted(str(path) for path in produced
                           if path.is_relative_to(raster_directory.resolve()) and path.suffix.lower() in (".tif", ".tiff"))
            outputs["OUTPUT_RASTERS"] = paths
            if not paths:
                feedback.pushWarning("No rasters were produced. Review the quality-control reports and engine log.")
            if context.project() is not None and self.parameterAsBool(parameters, "LOAD_OUTPUTS", context):
                for path in paths:
                    context.addLayerToLoadOnCompletion(path, QgsProcessingContext.LayerDetails(Path(path).stem, context.project(), "OUTPUT_RASTERS"))
        return outputs


class SeabedSidescanProvider(QgsProcessingProvider):
    def id(self):
        return "seabed_sidescan"

    def name(self):
        return "Seabed Sidescan"

    def longName(self):
        return "Seabed Sidescan (external Python engine)"

    def icon(self):
        return QIcon(str(Path(__file__).with_name("icon.svg")))

    def loadAlgorithms(self):
        for definition in DEFINITIONS:
            self.addAlgorithm(SeabedSidescanAlgorithm(definition))

    def supportsNonFileBasedOutput(self):
        return False

    def supportedOutputRasterLayerExtensions(self):
        return ["tif", "tiff"]
