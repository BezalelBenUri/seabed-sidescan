"""External engine process support; no scientific dependencies enter QGIS."""

import os
import signal
from collections import deque
from pathlib import Path

from qgis.core import QgsApplication, QgsProcessingException, QgsSettings
from qgis.PyQt.QtCore import QProcess, QProcessEnvironment

ENGINE_VERSION = "0.1.0"
ENGINE_KEY = "seabed_sidescan/python_executable"
RAW_REPO_KEY = "seabed_sidescan/raw_repository"
RAW_PYTHON_KEY = "seabed_sidescan/raw_python_executable"


def taskkill_executable():
    """Use the Windows system tool, never a same-named file on a survey PATH."""
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe")


def stop_process_tree(process):
    """Stop a worker and its children; call only from a Processing worker thread."""
    if process.state() == QProcess.NotRunning:
        return
    group = None
    if os.name == "nt":
        killer = QProcess()
        killer.start(taskkill_executable(), ["/PID", str(process.processId()), "/T", "/F"])
        if not killer.waitForFinished(5000):
            killer.kill()
            killer.waitForFinished(1000)
    else:
        try:
            pid = int(process.processId())
            if os.getpgid(pid) == pid:
                group = pid
                os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    process.terminate()
    if not process.waitForFinished(1500):
        process.kill()
        process.waitForFinished(3000)
    # A child can ignore SIGTERM even after its parent has exited.
    if group is not None:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass


def configured_python():
    return str(QgsSettings().value(ENGINE_KEY, "") or "").strip()


def configured_raw_repo():
    return str(QgsSettings().value(RAW_REPO_KEY, "") or "").strip()


def configured_raw_python():
    return str(QgsSettings().value(RAW_PYTHON_KEY, "") or "").strip()


def checked_python(value=None):
    value = configured_python() if value is None else str(value).strip()
    path = Path(value).expanduser()
    if not value or not path.is_file():
        raise QgsProcessingException(
            "Configure the external Python engine first: Raster > Seabed Sidescan > "
            "Set up processing tools. Click Install tools, or select an existing engine "
            "under Advanced settings."
        )
    path = path.resolve()
    # Windows QGIS distributions bundle Python below <install>/apps. They need
    # QGIS-specific DLL paths and are unsuitable as a standalone engine/base.
    for ancestor in path.parents:
        if (ancestor / "apps" / "qgis").is_dir() or (ancestor / "apps" / "qgis-ltr").is_dir():
            raise QgsProcessingException(
                "This executable belongs to a QGIS installation. Select a standalone "
                "Python 3.10 or newer, or an engine created from standalone Python."
            )
    return str(path)


def process_environment(executable):
    """Remove QGIS Python/Qt/GDAL settings before starting standalone Python."""
    env = QProcessEnvironment.systemEnvironment()
    roots = []
    for key in ("OSGEO4W_ROOT", "QGIS_PREFIX_PATH"):
        if env.contains(key):
            roots.append(env.value(key).replace("\\", "/").rstrip("/").lower())
    prefix = Path(QgsApplication.prefixPath())
    if prefix.name.lower() in ("qgis", "qgis-ltr") and prefix.parent.name.lower() == "apps":
        roots.append(str(prefix.parent.parent).replace("\\", "/").lower())
    for key in list(env.keys()):
        upper = key.upper()
        if upper.startswith(("PYTHON", "QT_", "QGIS_", "GDAL_", "PROJ_")) or upper in (
            "VIRTUAL_ENV", "OSGEO4W_ROOT", "GEOTIFF_CSV", "CPL_PLUGIN_PATH"
        ):
            env.remove(key)
    def clean_search_path(value):
        kept = []
        for item in value.split(os.pathsep):
            normal = item.replace("\\", "/").rstrip("/").lower()
            if item and not any(normal == root or normal.startswith(root + "/") for root in roots if root):
                kept.append(item)
        return os.pathsep.join(kept)

    interpreter_dir = Path(executable).resolve().parent
    prefix = interpreter_dir.parent if interpreter_dir.name.lower() in {"bin", "scripts"} else interpreter_dir
    search_dirs = [interpreter_dir]
    if (prefix / "conda-meta").is_dir():
        search_dirs = [prefix, prefix / "Library" / "bin", prefix / "Scripts", prefix / "bin"]
        env.insert("CONDA_PREFIX", str(prefix))
        for variable, directory, marker in (
            ("GDAL_DATA", prefix / "Library" / "share" / "gdal", "gdalvrt.xsd"),
            ("PROJ_DATA", prefix / "Library" / "share" / "proj", "proj.db"),
        ):
            if (directory / marker).is_file():
                env.insert(variable, str(directory))
        if (prefix / "Library" / "bin" / "gmt.dll").is_file():
            env.insert("GMT_LIBRARY_PATH", str(prefix / "Library" / "bin"))
        gmt_directory = prefix / "var" / "gmt"
        if gmt_directory.is_dir():
            env.insert("GMT_USERDIR", str(gmt_directory))
    env.insert("PATH", os.pathsep.join(str(path) for path in search_dirs if path.is_dir())
               + os.pathsep + clean_search_path(env.value("PATH")))
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        if env.contains(key):
            env.insert(key, clean_search_path(env.value(key)))
    env.insert("PYTHONNOUSERSITE", "1")
    env.insert("PYTHONUTF8", "1")
    env.insert("PYTHONUNBUFFERED", "1")
    return env


def run_engine(arguments, feedback, executable=None, working_directory=None):
    """Run in the Processing worker; poll cancellation without blocking the GUI."""
    executable = checked_python(executable)
    if feedback.isCanceled():
        raise QgsProcessingException("Seabed Sidescan processing was canceled. Partial outputs may remain.")
    process = QProcess()
    process.setProcessEnvironment(process_environment(executable))
    process.setProcessChannelMode(QProcess.MergedChannels)
    if working_directory:
        process.setWorkingDirectory(str(working_directory))
    feedback.pushInfo("Starting external seabed-sidescan engine.")
    # Recheck compatibility at every run, including headless/batch callers that
    # never opened Settings. Start a separate POSIX process group so cancellation
    # includes nested raw-sonar workers.
    bootstrap = (
        "import os, runpy, sys; "
        + ("os.setsid(); " if os.name != "nt" else "")
        + "from seabed_sidescan import __version__; "
        + f"assert __version__ == {ENGINE_VERSION!r}, 'Expected seabed-sidescan {ENGINE_VERSION}, got ' + __version__; "
        + "sys.argv = ['seabed-sidescan', *sys.argv[1:]]; "
        + "runpy.run_module('seabed_sidescan', run_name='__main__')"
    )
    process.start(executable, ["-u", "-c", bootstrap, *map(str, arguments)])
    if not process.waitForStarted(10000):
        raise QgsProcessingException("Could not start engine: " + process.errorString())
    tail = deque(maxlen=40)
    pending = ""

    def drain(final=False):
        nonlocal pending
        pending += bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        lines = pending.split("\n")
        pending = lines.pop()
        if final and pending:
            lines.append(pending)
            pending = ""
        for line in lines:
            line = line.rstrip("\r")
            tail.append(line)
            feedback.pushInfo(line)

    while process.state() != QProcess.NotRunning:
        if feedback.isCanceled():
            stop_process_tree(process)
            drain(final=True)
            raise QgsProcessingException("Seabed Sidescan processing was canceled. Partial outputs may remain.")
        process.waitForReadyRead(100)
        drain()
    drain(final=True)
    if process.exitStatus() != QProcess.NormalExit or process.exitCode() != 0:
        detail = "\n".join(tail)
        raise QgsProcessingException(
            f"External engine failed (exit {process.exitCode()}). Check the engine in Raster > Seabed Sidescan > "
            f"Set up processing tools.\n{detail}"
        )
    return list(tail)
