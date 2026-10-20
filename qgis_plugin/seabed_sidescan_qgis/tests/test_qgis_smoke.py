"""Run with QGIS Python from the repository root.

Set SEABED_SIDESCAN_TEST_PYTHON to a separate Python with the backend installed
to enable the complete synthetic-raster pipeline test. No backend is imported
into the QGIS interpreter.
"""

import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterDefinition,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtWidgets import QMainWindow

from qgis_plugin.seabed_sidescan_qgis import classFactory
from qgis_plugin.seabed_sidescan_qgis.engine import (
    checked_python,
    process_environment,
    run_engine,
)
from qgis_plugin.seabed_sidescan_qgis.provider import (
    DEFINITIONS,
    SeabedSidescanAlgorithm,
    SeabedSidescanProvider,
)
from qgis_plugin.seabed_sidescan_qgis.settings import EngineSettingsDialog

APP = QgsApplication.instance()
if APP is None:
    APP = QgsApplication([], False)
    APP.initQgis()


class RecordingFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.messages = []

    def pushInfo(self, message):
        self.messages.append(message)

    def reportError(self, message, fatalError=False):
        self.messages.append(message)


class FakeInterface:
    def __init__(self):
        self.window = QMainWindow()
        self.menu = []
        self.toolbar = []

    def mainWindow(self):
        return self.window

    def addPluginToRasterMenu(self, menu, action):
        self.menu.append(action)

    def removePluginRasterMenu(self, menu, action):
        self.menu.remove(action)

    def addToolBarIcon(self, action):
        self.toolbar.append(action)

    def removeToolBarIcon(self, action):
        self.toolbar.remove(action)


class PluginSmokeTests(unittest.TestCase):
    def test_headless_processing_registration_is_idempotent(self):
        plugin = classFactory(None)
        plugin.initProcessing()
        provider = APP.processingRegistry().providerById("seabed_sidescan")
        try:
            plugin.initProcessing()
            self.assertIs(APP.processingRegistry().providerById("seabed_sidescan"), provider)
            self.assertEqual(len(provider.algorithms()), 9)
        finally:
            plugin.unload()
        self.assertIsNone(APP.processingRegistry().providerById("seabed_sidescan"))

    def test_qgis_plugin_manager_accepts_development_metadata(self):
        from pyplugin_installer.installer_data import plugins

        directory = Path(__file__).resolve().parents[1]
        metadata = plugins.getInstalledPlugin("seabed_sidescan_qgis", str(directory), False)
        self.assertEqual(metadata["error"], "")
        self.assertEqual(metadata["version_installed"], "0.1.0")
        self.assertTrue(metadata["experimental"])

    def test_plugin_registers_and_unloads_without_backend_imports(self):
        iface = FakeInterface()
        plugin = classFactory(iface)
        plugin.initGui()
        try:
            provider = APP.processingRegistry().providerById("seabed_sidescan")
            self.assertEqual(len(provider.algorithms()), 9)
            self.assertEqual(len(iface.menu), 2)
            self.assertEqual(len(iface.toolbar), 1)
            self.assertEqual(plugin.actions[1].text(), "Set up processing tools…")
            plugin.actions[1].trigger()
            self.assertIsNotNone(plugin.settings_dialog)
            self.assertNotIn("rasterio", sys.modules)
            self.assertNotIn("sklearn", sys.modules)
            self.assertNotIn("seabed_sidescan", sys.modules)
        finally:
            plugin.unload()
        self.assertIsNone(APP.processingRegistry().providerById("seabed_sidescan"))
        self.assertEqual(iface.menu, [])
        self.assertEqual(iface.toolbar, [])

    @staticmethod
    def raw_algorithm():
        algorithm = SeabedSidescanAlgorithm(next(item for item in DEFINITIONS if item[0] == "process"))
        algorithm.initAlgorithm()
        return algorithm

    def test_raw_backend_overrides_are_optional_and_advanced(self):
        algorithm = self.raw_algorithm()
        for name in ("SIDESCANTOOLS_REPO", "SIDESCANTOOLS_PYTHON"):
            parameter = algorithm.parameterDefinition(name)
            self.assertTrue(parameter.flags() & QgsProcessingParameterDefinition.FlagOptional)
            self.assertTrue(parameter.flags() & QgsProcessingParameterDefinition.FlagAdvanced)
            self.assertFalse(parameter.defaultValue())

    def test_raw_backend_uses_latest_setup_selection_and_manual_overrides(self):
        algorithm = self.raw_algorithm()
        context = QgsProcessingContext()
        with tempfile.TemporaryDirectory(prefix="seabed_raw_wiring_") as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            for repository in (first, second):
                script = repository / "src" / "sidescantools" / "main_cli.py"
                script.parent.mkdir(parents=True)
                script.touch()
            first_python, second_python = root / "first-python", root / "second-python"
            first_python.touch()
            second_python.touch()
            with patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_repo", return_value=str(first)) as repository_setting, patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_python", return_value=str(first_python)) as python_setting:
                selected = algorithm._raw_backend_paths({}, context)
                self.assertEqual(selected["SIDESCANTOOLS_REPO"], str(first.resolve()))
                self.assertEqual(selected["SIDESCANTOOLS_PYTHON"], str(first_python.resolve()))
                # Algorithms are registered before setup. A later setup selection
                # must apply without restarting QGIS or rebuilding the provider.
                repository_setting.return_value = str(second)
                python_setting.return_value = str(second_python)
                selected = algorithm._raw_backend_paths({}, context)
                self.assertEqual(selected["SIDESCANTOOLS_REPO"], str(second.resolve()))
                self.assertEqual(selected["SIDESCANTOOLS_PYTHON"], str(second_python.resolve()))
                selected = algorithm._raw_backend_paths({
                    "SIDESCANTOOLS_REPO": str(first), "SIDESCANTOOLS_PYTHON": str(first_python),
                }, context)
                self.assertEqual(selected["SIDESCANTOOLS_REPO"], str(first.resolve()))
                self.assertEqual(selected["SIDESCANTOOLS_PYTHON"], str(first_python.resolve()))

    def test_raw_backend_missing_setup_has_actionable_error(self):
        algorithm = self.raw_algorithm()
        context = QgsProcessingContext()
        with patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_repo", return_value=""), patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_python", return_value=""):
            with self.assertRaisesRegex(QgsProcessingException, "Set up processing tools"):
                algorithm._raw_backend_paths({}, context)
        with tempfile.TemporaryDirectory(prefix="seabed_raw_wiring_") as temporary:
            with self.assertRaisesRegex(QgsProcessingException, "unavailable or incomplete"):
                algorithm._raw_backend_paths({
                    "SIDESCANTOOLS_REPO": temporary, "SIDESCANTOOLS_PYTHON": str(Path(temporary) / "missing-python"),
                }, context)

    def test_worker_environment_removes_qgis_contamination(self):
        with patch.dict(os.environ, {"PYTHONPATH": "qgis-python", "PYTHONHOME": "qgis-home", "QT_PLUGIN_PATH": "qt", "GDAL_DATA": "gdal", "PROJ_LIB": "proj", "VIRTUAL_ENV": "qgis-env"}):
            environment = process_environment(sys.executable)
        for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "GDAL_DATA", "PROJ_LIB", "VIRTUAL_ENV"):
            self.assertFalse(environment.contains(key), key)
        self.assertEqual(environment.value("PYTHONNOUSERSITE"), "1")

    @unittest.skipUnless(os.name == "nt", "Bundled QGIS Python layout is Windows-specific")
    def test_bundled_qgis_python_is_rejected(self):
        with self.assertRaisesRegex(QgsProcessingException, "belongs to a QGIS installation"):
            checked_python(sys.executable)


@unittest.skipUnless(os.environ.get("SEABED_SIDESCAN_TEST_PYTHON"), "Set an external backend Python to run integration tests")
class ExternalEnginePipelineTests(unittest.TestCase):
    def setUp(self):
        self.executable = str(Path(os.environ["SEABED_SIDESCAN_TEST_PYTHON"]).resolve())
        self.temporary = tempfile.TemporaryDirectory(prefix="seabed_qgis_test_")
        self.directory = Path(self.temporary.name).resolve()
        self.provider = SeabedSidescanProvider()
        APP.processingRegistry().addProvider(self.provider)
        self.python_patch = patch("qgis_plugin.seabed_sidescan_qgis.engine.configured_python", return_value=self.executable)
        self.python_patch.start()
        self.project = QgsProject()
        self.context = QgsProcessingContext()
        self.context.setProject(self.project)
        self.context.setTemporaryFolder(str(self.directory / "processing_temp"))
        self.feedback = RecordingFeedback()

    def tearDown(self):
        self.python_patch.stop()
        APP.processingRegistry().removeProvider(self.provider)
        self.context.temporaryLayerStore().removeAllMapLayers()
        self.project.removeAllMapLayers()
        self.context = None
        self.project = None
        # Failed Processing runs can keep a Python exception cycle containing a
        # temporary raster layer; release its GDAL file handle before cleanup.
        __import__("gc").collect()
        self.temporary.cleanup()

    def run_algorithm(self, name, parameters):
        algorithm = APP.processingRegistry().algorithmById("seabed_sidescan:" + name)
        result, success = algorithm.run(parameters, self.context, self.feedback)
        self.assertTrue(success, "\n".join(self.feedback.messages))
        return result

    @staticmethod
    def create_raster(path, offset=0):
        # GDAL is supplied by QGIS. Packing floats avoids importing NumPy or rasterio.
        from osgeo import gdal, osr

        gdal.UseExceptions()
        dataset = gdal.GetDriverByName("GTiff").Create(str(path), 24, 24, 1, gdal.GDT_Float32)
        dataset.SetGeoTransform((500000 + offset, 1, 0, 1000, 0, -1))
        crs = osr.SpatialReference()
        crs.ImportFromEPSG(32632)
        dataset.SetProjection(crs.ExportToWkt())
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-9999)
        values = [float(20 + row * 2 + col + ((row + col) % 5) * 3) for row in range(24) for col in range(24)]
        band.WriteRaster(0, 0, 24, 24, struct.pack("<576f", *values), buf_type=gdal.GDT_Float32)
        dataset.FlushCache()
        dataset = None

    def boundary(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:32632", "Synthetic boundary", "memory")
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(500002, 998), QgsPointXY(500020, 998), QgsPointXY(500020, 980),
            QgsPointXY(500002, 980), QgsPointXY(500002, 998),
        ]]))
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        self.project.addMapLayer(layer)
        return layer

    def test_all_eight_operations_on_synthetic_data(self):
        strips = self.directory / "strips"
        strips.mkdir()
        self.create_raster(strips / "test_ch0_line.tif")
        self.create_raster(strips / "test_ch1_line.tif", offset=2)
        mosaics = self.directory / "mosaics"
        mosaic = self.run_algorithm("mosaic", {
            "GEOREF_DIR": str(strips), "OUTPUT_DIR": str(mosaics),
            "REPORT_DIR": str(self.directory / "qc"), "EDGE_TRIM_PERCENT": 0,
            "FEATHER_PERCENT": 0, "LOAD_OUTPUTS": True,
        })
        combined = mosaics / "SSS_combined_standard_mosaic.tif"
        self.assertTrue(combined.exists())
        self.assertIn(str(combined), mosaic["OUTPUT_RASTERS"])
        self.assertTrue(self.context.willLoadLayerOnCompletion(str(combined)))
        boundary = self.boundary()
        mask = self.directory / "mask.tif"
        self.run_algorithm("mask", {
            "INPUT_RASTER": str(combined), "BOUNDARY": boundary,
            "OUTPUT_MASK": str(mask), "OUTPUT_BOUNDARY_MASK": str(self.directory / "boundary_mask.tif"),
        })
        result = self.run_algorithm("textures", {
            "INPUT_RASTER": str(combined), "MASK_RASTER": str(mask),
            "OUTPUT_DIR": "TEMPORARY_OUTPUT", "WINDOW_SIZE": 3, "LEVELS": 4,
        })
        textures = Path(result["OUTPUT_DIR"])
        self.assertTrue(textures.is_absolute())
        self.assertEqual(len(result["OUTPUT_RASTERS"]), 8)
        stack = self.directory / "features.tif"
        self.run_algorithm("stack_features", {
            "INPUT_RASTERS": [str(combined), str(textures / "SSS_mean.tif"), str(textures / "SSS_entropy.tif")],
            "MASK_RASTER": str(mask), "BAND_NAMES": "intensity mean entropy",
            "OUTPUT_STACK": str(stack), "METADATA_CSV": str(self.directory / "bands.csv"),
        })
        shared = {"FEATURE_STACK": str(stack), "MASK_RASTER": str(mask), "SAMPLE_SIZE": 100, "N_INIT": 2, "MAX_ITERATIONS": 30}
        self.run_algorithm("evaluate_clusters", {
            **shared, "CLASSES": "2 3", "RUNS": 2, "METRIC_SAMPLE_SIZE": 100,
            "OUTPUT_CSV": str(self.directory / "evaluation.csv"), "SUMMARY_TXT": str(self.directory / "evaluation.txt"),
        })
        classes = self.directory / "classes.tif"
        self.run_algorithm("classify", {
            **shared, "CLASSES": 3, "OUTPUT_RASTER": str(classes),
            "REPORT_CSV": str(self.directory / "classes.csv"), "MODEL_JSON": str(self.directory / "model.json"),
        })
        cleaned = self.directory / "cleaned.tif"
        self.run_algorithm("clean_classification", {
            "INPUT_RASTER": str(classes), "OUTPUT_RASTER": str(cleaned),
            "REPORT_TXT": str(self.directory / "cleanup.txt"), "MIN_PATCH_SIZE": 2,
        })
        clipped = self.directory / "clipped.tif"
        self.run_algorithm("clip_raster", {
            "INPUT_RASTER": str(cleaned), "BOUNDARY": boundary, "OUTPUT_RASTER": str(clipped),
        })
        from osgeo import gdal

        dataset = gdal.Open(str(clipped))
        self.assertEqual((dataset.RasterXSize, dataset.RasterYSize), (18, 18))
        self.assertGreater(dataset.GetRasterBand(1).GetStatistics(False, True)[1], 0)
        dataset = None
        self.assertNotIn("rasterio", sys.modules)
        self.assertNotIn("sklearn", sys.modules)

    def test_engine_failure_and_cancellation_are_reported(self):
        with self.assertRaisesRegex(QgsProcessingException, "External engine failed"):
            run_engine(["unknown-command"], self.feedback, self.executable)
        self.feedback.cancel()
        with self.assertRaisesRegex(QgsProcessingException, "canceled"):
            run_engine(["--version"], self.feedback, self.executable)

    def test_processing_rejects_mismatched_engine_version(self):
        package = self.directory / "seabed_sidescan"
        package.mkdir()
        (package / "__init__.py").write_text("__version__ = 'incompatible-test-fixture'\n", encoding="utf-8")
        with self.assertRaisesRegex(QgsProcessingException, "Expected seabed-sidescan"):
            run_engine(["--version"], self.feedback, self.executable, self.directory)

    def test_optional_raw_adapter_and_no_output_failure(self):
        raw = self.directory / "raw"
        raw.mkdir()
        (raw / "synthetic.xtf").write_bytes(b"synthetic adapter fixture, not sonar")
        repo = self.directory / "fake_backend"
        script = repo / "src" / "sidescantools" / "main_cli.py"
        script.parent.mkdir(parents=True)
        self.create_raster(repo / "fixture.tif")
        script.write_text(
            "from pathlib import Path\nimport json, os, shutil, sys\n"
            "assert Path(sys.argv[1]).is_dir()\n"
            "assert os.environ['SIDESCANTOOLS_XTF_CHANNEL_PAIR'] == '0,1'\n"
            "destination = Path(sys.argv[2]).parent.parent / 'georef_out'\n"
            "shutil.copyfile(Path(__file__).parents[2] / 'fixture.tif', destination / 'synthetic_ch0_georef.tif')\n"
            "shutil.copyfile(Path(__file__).parents[2] / 'fixture.tif', destination / 'synthetic_ch1_georef.tif')\n"
            "outputs = [{'channel': ch, 'input_channel': ch, 'path': str(destination / f'synthetic_ch{ch}_georef.tif')} for ch in (0,1)]\n"
            "Path(os.environ['SIDESCANTOOLS_RUN_MANIFEST']).write_text(json.dumps({'schema_version':1, 'inputs':[{'path':str(Path(sys.argv[1]) / 'synthetic.xtf'), 'outputs':outputs}]}))\n"
            "print('Synthetic adapter output created; this is not a georeferencing test.')\n",
            encoding="utf-8",
        )
        parameters = {
            "INPUT": str(raw), "PROJECT": "survey", "PROJECT_ROOT": str(self.directory / "projects"),
            "SIDESCANTOOLS_REPO": str(repo), "SIDESCANTOOLS_PYTHON": self.executable,
        }
        with patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_repo", return_value=str(repo)), patch("qgis_plugin.seabed_sidescan_qgis.provider.configured_raw_python", return_value=self.executable):
            result = self.run_algorithm("process", {
                key: value for key, value in parameters.items()
                if key not in {"SIDESCANTOOLS_REPO", "SIDESCANTOOLS_PYTHON"}
            })
        output = self.directory / "projects" / "survey" / "georef_out" / "synthetic_ch0_georef.tif"
        self.assertTrue(output.is_file())
        self.assertEqual(result["GEOREF_DIR"], str(output.parent))
        self.assertIn(str(output), result["OUTPUT_RASTERS"])
        self.assertTrue(self.context.willLoadLayerOnCompletion(str(output)))
        script.write_text("print('Synthetic backend returned without exporting')\n", encoding="utf-8")
        algorithm = APP.processingRegistry().algorithmById("seabed_sidescan:process")
        _, success = algorithm.run({**parameters, "PROJECT": "empty_survey"}, self.context, self.feedback)
        self.assertFalse(success)
        self.assertTrue(any("without creating or updating a GeoTIFF" in line for line in self.feedback.messages))

    @unittest.skipUnless(os.name == "nt", "Windows process-tree cancellation")
    def test_raw_cancellation_stops_nested_backend(self):
        raw = self.directory / "raw_cancel"
        raw.mkdir()
        (raw / "synthetic.xtf").write_bytes(b"synthetic adapter fixture, not sonar")
        repo = self.directory / "cancel_backend"
        script = repo / "src" / "sidescantools" / "main_cli.py"
        script.parent.mkdir(parents=True)
        marker = repo / "backend.pid"
        script.write_text(
            "from pathlib import Path\nimport os, time\n"
            "(Path(__file__).parents[2] / 'backend.pid').write_text(str(os.getpid()))\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )

        class CancelWhenBackendStarts(RecordingFeedback):
            def isCanceled(self):
                return marker.is_file()

        with self.assertRaisesRegex(QgsProcessingException, "canceled"):
            run_engine([
                "process", "--input", str(raw), "--project", "cancel_test",
                "--project-root", str(self.directory / "projects"),
                "--sidescantools-repo", str(repo), "--sidescantools-python", self.executable,
            ], CancelWhenBackendStarts(), self.executable)
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, int(marker.read_text()))
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0, "The nested raw backend survived cancellation")
            finally:
                kernel.CloseHandle(handle)

    def test_settings_checks_backend_asynchronously(self):
        dialog = EngineSettingsDialog()
        try:
            dialog.python_edit.setText(self.executable)
            dialog.check_engine()
            self.assertTrue(dialog.running)
            deadline = time.monotonic() + 30
            while dialog.running and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(0.01)
            self.assertFalse(dialog.running, dialog.log.toPlainText())
            self.assertIn("check passed", dialog.status.text(), dialog.log.toPlainText())
        finally:
            dialog.stop_process()
            dialog.close()

    def test_folder_results_exclude_stale_rasters(self):
        import json

        source = self.directory / "input.tif"
        self.create_raster(source)
        destination = self.directory / "textures"
        destination.mkdir()
        stale = destination / "stale.tif"
        self.create_raster(stale)
        fresh = destination / "fresh.tif"
        unlisted = destination / "unrelated-concurrent-output.tif"

        def fake_engine(arguments, *_):
            self.create_raster(fresh)
            self.create_raster(unlisted)
            Path(arguments[arguments.index("--output-manifest") + 1]).write_text(json.dumps({
                "schema_version": 1, "command": "textures", "outputs": [str(fresh)],
            }), encoding="utf-8")

        with patch("qgis_plugin.seabed_sidescan_qgis.provider.run_engine", side_effect=fake_engine):
            result = self.run_algorithm("textures", {
                "INPUT_RASTER": str(source), "MASK_RASTER": str(source), "OUTPUT_DIR": str(destination),
            })
        self.assertEqual(result["OUTPUT_RASTERS"], [str(fresh)])
        self.assertFalse(self.context.willLoadLayerOnCompletion(str(stale)))
        self.assertFalse(self.context.willLoadLayerOnCompletion(str(unlisted)))

    def test_successful_exit_requires_declared_outputs(self):
        import json

        source = self.directory / "input.tif"
        self.create_raster(source)
        algorithm = APP.processingRegistry().algorithmById("seabed_sidescan:mask")
        destination = self.directory / "missing.tif"
        def fake_engine(arguments, *_):
            Path(arguments[arguments.index("--output-manifest") + 1]).write_text(json.dumps({
                "schema_version": 1, "command": "mask", "outputs": [],
            }), encoding="utf-8")

        with patch("qgis_plugin.seabed_sidescan_qgis.provider.run_engine", side_effect=fake_engine):
            _, success = algorithm.run({"INPUT_RASTER": str(source), "OUTPUT_MASK": str(destination)}, self.context, self.feedback)
        self.assertFalse(success)
        self.assertTrue(any("expected output" in line for line in self.feedback.messages))

    def test_save_validates_engine_and_keeps_previous_selection_on_failure(self):
        # Use temporary INI settings rather than the real QGIS profile/registry.
        settings = QSettings(str(self.directory / "settings.ini"), QSettings.IniFormat)
        settings.setValue("seabed_sidescan/python_executable", "previous-engine")
        dialog = EngineSettingsDialog()
        try:
            dialog.python_edit.setText(self.executable)
            with patch("qgis_plugin.seabed_sidescan_qgis.settings.QgsSettings", return_value=settings), patch.object(dialog, "_backend_check", return_value=["-c", "raise RuntimeError('incompatible fixture')"]):
                dialog.save_settings()
                self.assertTrue(dialog.running)
                deadline = time.monotonic() + 10
                while dialog.running and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(0.01)
                self.assertFalse(dialog.running)
            self.assertEqual(settings.value("seabed_sidescan/python_executable"), "previous-engine")
            self.assertIn("failed", dialog.status.text())
        finally:
            dialog.stop_process()
            dialog.close()

    @unittest.skipUnless(os.name == "nt", "Windows GUI installer process-tree cancellation")
    def test_settings_close_cancels_nested_children_asynchronously(self):
        import ctypes
        from ctypes import wintypes

        marker = self.directory / "installer-child.pid"
        child_code = f"from pathlib import Path; import os, time; Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
        code = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); time.sleep(60)"
        dialog = EngineSettingsDialog()
        try:
            dialog.show()
            dialog._run_steps([(self.executable, ["-u", "-c", code], "Synthetic installer child fixture")])
            deadline = time.monotonic() + 15
            while not marker.exists() and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(0.01)
            self.assertTrue(marker.is_file(), dialog.log.toPlainText())
            started = time.monotonic()
            dialog.close()
            self.assertLess(time.monotonic() - started, 0.5, "Closing blocked the GUI")
            while dialog.running and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(0.01)
            APP.processEvents()
            self.assertFalse(dialog.running)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x00100000, False, int(marker.read_text()))
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0, "Installer child survived cancellation")
                finally:
                    kernel.CloseHandle(handle)
        finally:
            dialog.stop_process()
            dialog.close()

    @unittest.skipUnless(os.environ.get("SEABED_SIDESCAN_TEST_WHEEL") and os.environ.get("SEABED_SIDESCAN_TEST_DEPENDENCY_SITE"), "Set wheel and prepared dependency site for isolated managed-install verification")
    def test_managed_install_uses_isolated_environment_and_keeps_gui_responsive(self):
        import json

        settings = QSettings(str(self.directory / "settings.ini"), QSettings.IniFormat)
        settings.setValue("seabed_sidescan/python_executable", "previous-engine")
        dialog = EngineSettingsDialog()
        old = self.directory / "existing-engine"
        old.mkdir()
        marker = old / "keep.txt"
        marker.write_text("working previous engine", encoding="utf-8")
        dialog.managed_directory = old
        dialog.managed_python = old / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        dialog.base_edit.setText(self.executable)
        dialog.wheel_edit.setText(os.environ["SEABED_SIDESCAN_TEST_WHEEL"])
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start(20)
        original_next = dialog._next_step

        def next_step():
            if dialog.steps and "pip" in dialog.steps[0][1]:
                # Reuse prepared numerical dependencies, while pip installs the
                # actual wheel in the new environment. This checks installer UX
                # and wheel isolation without a network/dependency-download test.
                site = dialog.managed_directory / ("Lib/site-packages" if os.name == "nt" else "lib/python{}.{}".format(*sys.version_info[:2]) + "/site-packages")
                site.mkdir(parents=True, exist_ok=True)
                (site / "prepared_dependencies.pth").write_text(os.environ["SEABED_SIDESCAN_TEST_DEPENDENCY_SITE"] + "\n", encoding="utf-8")
            original_next()

        try:
            with patch("qgis_plugin.seabed_sidescan_qgis.settings.QgsSettings", return_value=settings), patch.object(dialog, "_next_step", side_effect=next_step), patch.dict(os.environ, {"PIP_NO_INDEX": "1"}):
                dialog.install_engine()
                self.assertTrue(dialog.running)
                deadline = time.monotonic() + 120
                while dialog.running and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(0.01)
                self.assertFalse(dialog.running, dialog.log.toPlainText())
                self.assertIn("installed, checked and selected", dialog.status.text(), dialog.log.toPlainText())
            self.assertGreater(len(ticks), 10, "The GUI event loop did not remain responsive")
            self.assertNotEqual(dialog.managed_directory, old)
            self.assertEqual(marker.read_text(encoding="utf-8"), "working previous engine")
            self.assertEqual(settings.value("seabed_sidescan/python_executable"), str(dialog.managed_python))
            # Inspect the import in the installed environment, with no checkout
            # package import. The prepared dependency .pth adds only dependencies.
            process = __import__("subprocess").run([
                str(dialog.managed_python), "-I", "-c",
                "import json, seabed_sidescan; print(json.dumps(seabed_sidescan.__file__))",
            ], capture_output=True, text=True, check=True, env={key: str(value) for key, value in os.environ.items() if not key.startswith(("PYTHON", "QT_", "QGIS_", "GDAL_", "PROJ_"))})
            self.assertTrue(Path(json.loads(process.stdout)).resolve().is_relative_to(dialog.managed_directory.resolve()), process.stdout)
        finally:
            timer.stop()
            dialog.stop_process()
            dialog.close()


if __name__ == "__main__":
    unittest.main()
