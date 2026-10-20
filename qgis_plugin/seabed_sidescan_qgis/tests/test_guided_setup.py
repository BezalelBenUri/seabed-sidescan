"""Offline QGIS checks for guided setup; no installer or network is executed."""

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject, QProcess, QSettings, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply

from qgis_plugin.seabed_sidescan_qgis.engine import (
    ENGINE_KEY,
    ENGINE_VERSION,
    RAW_PYTHON_KEY,
    RAW_REPO_KEY,
)
from qgis_plugin.seabed_sidescan_qgis.settings import EngineSettingsDialog
from qgis_plugin.seabed_sidescan_qgis.setup_flow import GuidedSetup

APP = QgsApplication.instance()
if APP is None:
    APP = QgsApplication([], False)
    APP.initQgis()


class FakeProcess(QObject):
    readyReadStandardOutput = pyqtSignal()
    finished = pyqtSignal(int, int)
    errorOccurred = pyqtSignal(object)

    def __init__(self, parent=None, finish_delay=None):
        super().__init__(parent)
        self.starts = []
        self.current_state = QProcess.NotRunning
        self.finish_delay = finish_delay
        self.kill_calls = 0

    def setProcessEnvironment(self, environment):
        self.environment = environment

    def setWorkingDirectory(self, directory):
        self.directory = directory

    def start(self, executable, arguments):
        self.starts.append((executable, arguments))
        self.current_state = QProcess.Running
        if self.finish_delay is not None:
            QTimer.singleShot(self.finish_delay, lambda: self.finish(0))

    def state(self):
        return self.current_state

    def readAllStandardOutput(self):
        return b""

    def processId(self):
        return 12345

    def finish(self, exit_code, exit_status=QProcess.NormalExit):
        self.current_state = QProcess.NotRunning
        self.finished.emit(exit_code, exit_status)

    def kill(self):
        self.kill_calls += 1
        QTimer.singleShot(0, lambda: self.finish(-1, QProcess.CrashExit))


class FakeReply(QObject):
    readyRead = pyqtSignal()
    downloadProgress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.aborted = False

    def readAll(self):
        payload, self.payload = self.payload, b""
        return payload

    def attribute(self, _attribute):
        return None

    def url(self):
        return QUrl("https://example.invalid/installer.exe")

    def error(self):
        return QNetworkReply.NoError

    def errorString(self):
        return ""

    def abort(self):
        self.aborted = True
        self.finished.emit()


class GuidedSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="seabed_guided_test_")
        self.directory = Path(self.temporary.name)
        self.settings = QSettings(str(self.directory / "settings.ini"), QSettings.IniFormat)
        self.previous = {
            ENGINE_KEY: "previous-engine",
            RAW_REPO_KEY: "previous-raw-source",
            RAW_PYTHON_KEY: "previous-raw-python",
        }
        for key, value in self.previous.items():
            self.settings.setValue(key, value)
        self.settings_patch = patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.QgsSettings", return_value=self.settings,
        )
        self.settings_patch.start()
        self.controllers = []

    def tearDown(self):
        for controller in self.controllers:
            controller.cancel()
        self.pump(lambda: all(not controller.running for controller in self.controllers))
        self.settings_patch.stop()
        self.temporary.cleanup()

    def pump(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.001)
        APP.processEvents()
        self.assertTrue(predicate(), "An asynchronous setup operation did not finish")

    def plan(self, *, raw=True, cached=True, steps=True):
        prefix = self.directory / "installation" / "environment"
        prefix.parent.mkdir(parents=True, exist_ok=True)
        bootstrap = self.directory / "bootstrap" / "micromamba.exe"
        bootstrap.parent.mkdir(parents=True, exist_ok=True)
        if cached:
            bootstrap.write_bytes(b"cached fixture, never executed")
        return SimpleNamespace(
            root=self.directory,
            prefix=prefix,
            python=prefix / "python.exe",
            raw_source=self.directory / "raw-source" if raw else None,
            micromamba=bootstrap,
            record=prefix.parent / "installation.json",
            log=prefix.parent / "setup.log",
            version=ENGINE_VERSION,
            steps=lambda _checker: [(bootstrap, ["fixture"], "Synthetic setup step")] if steps else [],
        )

    def controller(self, parent=None):
        controller = GuidedSetup(parent)
        process = FakeProcess(controller)
        process.readyReadStandardOutput.connect(controller._read_output)
        process.finished.connect(controller._process_finished)
        process.errorOccurred.connect(controller._process_error)
        controller.process = process
        killer = FakeProcess(controller, finish_delay=20)
        killer.finished.connect(lambda *_: controller._kill_main())
        killer.errorOccurred.connect(lambda *_: controller._kill_main())
        controller.killer = killer
        controller.results = []
        controller.finished.connect(lambda success, report: controller.results.append((success, report)))
        self.controllers.append(controller)
        return controller

    def start_cached(self, controller, plan):
        with patch("qgis_plugin.seabed_sidescan_qgis.setup_flow.sha256", return_value="verified-fixture"), patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.MICROMAMBA_SHA256", "verified-fixture",
        ):
            controller.start(plan)
            self.pump(lambda: bool(controller.process.starts) or not controller.running)

    def assert_previous_selection(self):
        self.assertEqual({key: self.settings.value(key) for key in self.previous}, self.previous)

    def write_record(self, plan, **changes):
        report = {
            "schema_version": 1, "status": "verified", "engine_version": plan.version,
            "python": str(plan.python.resolve()),
            "raw_repository": str(plan.raw_source.resolve()) if plan.raw_source else None,
        }
        report.update(changes)
        plan.record.write_text(json.dumps(report), encoding="utf-8")
        return report

    def test_failed_step_preserves_all_previous_settings(self):
        controller = self.controller()
        self.start_cached(controller, self.plan())
        self.assert_previous_selection()
        controller.process.finish(1)
        self.assertFalse(controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assert_previous_selection()

    def test_cancel_preserves_all_previous_settings(self):
        controller = self.controller()
        self.start_cached(controller, self.plan())
        controller.cancel()
        self.pump(lambda: not controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assertGreater(controller.process.kill_calls, 0)
        self.assert_previous_selection()

    def test_selection_changes_only_after_steps_and_record_verification(self):
        controller = self.controller()
        plan = self.plan()
        report = self.write_record(plan)
        self.start_cached(controller, plan)
        self.assert_previous_selection()
        controller.process.finish(0)
        self.assertEqual(controller.results, [(True, report)])
        self.assertEqual(self.settings.value(ENGINE_KEY), str(plan.python))
        self.assertEqual(self.settings.value(RAW_PYTHON_KEY), str(plan.python))
        self.assertEqual(self.settings.value(RAW_REPO_KEY), str(plan.raw_source))

    def test_missing_or_mismatched_record_keeps_all_previous_settings(self):
        for invalid in (None, {"engine_version": "incompatible"}, {"python": "wrong-interpreter"}):
            with self.subTest(record=invalid):
                controller = self.controller()
                plan = self.plan()
                plan.record.unlink(missing_ok=True)
                if invalid is not None:
                    self.write_record(plan, **invalid)
                self.start_cached(controller, plan)
                controller.process.finish(0)
                self.assertEqual(controller.results, [(False, {})])
                self.assert_previous_selection()

    def test_raster_only_success_preserves_separately_configured_raw_backend(self):
        controller = self.controller()
        plan = self.plan(raw=False)
        self.write_record(plan)
        self.start_cached(controller, plan)
        controller.process.finish(0)
        self.assertEqual(self.settings.value(ENGINE_KEY), str(plan.python))
        self.assertEqual(self.settings.value(RAW_PYTHON_KEY), self.previous[RAW_PYTHON_KEY])
        self.assertEqual(self.settings.value(RAW_REPO_KEY), self.previous[RAW_REPO_KEY])

    def test_corrupt_download_never_executes(self):
        controller = self.controller()
        plan = self.plan(cached=False)
        reply = FakeReply(b"evil")
        with patch("qgis_plugin.seabed_sidescan_qgis.setup_flow.QgsNetworkAccessManager") as network, patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.MICROMAMBA_BYTES", 4,
        ), patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.MICROMAMBA_SHA256", hashlib.sha256(b"safe").hexdigest(),
        ):
            network.instance.return_value.get.return_value = reply
            controller.start(plan)
            controller._download_finished()
        self.assertFalse(controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assertEqual(controller.process.starts, [])
        self.assertFalse(plan.micromamba.is_file())
        self.assertFalse(plan.micromamba.with_suffix(".part").exists())
        self.assert_previous_selection()

    def test_concurrent_setup_does_not_remove_active_download_and_can_retry(self):
        first, second = self.controller(), self.controller()
        plan = self.plan(cached=False)
        with patch("qgis_plugin.seabed_sidescan_qgis.setup_flow.QgsNetworkAccessManager") as network:
            network.instance.return_value.get.return_value = FakeReply(b"partial")
            first.start(plan)
            partial = plan.micromamba.with_suffix(".part")
            self.assertTrue(partial.exists())
            second.start(plan)
            self.assertFalse(second.running)
            self.assertEqual(second.results, [(False, {})])
            self.assertTrue(first.running)
            self.assertTrue(partial.exists(), "The rejected setup removed the active download")
            self.assertEqual(first.process.starts, [])
            self.assertEqual(second.process.starts, [])
            first.cancel()
            self.assertFalse(first.running)
            network.instance.return_value.get.return_value = FakeReply(b"retry")
            second.start(plan)
            self.assertTrue(second.running, "The installation lock was not released after cancellation")
            second.cancel()
        self.assert_previous_selection()

    def test_verified_download_commit_failure_is_reported_without_execution(self):
        controller = self.controller()
        plan = self.plan(cached=False)
        reply = FakeReply(b"safe")
        with patch("qgis_plugin.seabed_sidescan_qgis.setup_flow.QgsNetworkAccessManager") as network, patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.MICROMAMBA_BYTES", 4,
        ), patch(
            "qgis_plugin.seabed_sidescan_qgis.setup_flow.MICROMAMBA_SHA256", hashlib.sha256(b"safe").hexdigest(),
        ), patch.object(Path, "replace", side_effect=PermissionError("installer file is locked")):
            network.instance.return_value.get.return_value = reply
            controller.start(plan)
            controller._download_finished()
        self.assertFalse(controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assertEqual(controller.process.starts, [])
        self.assert_previous_selection()

    def test_startup_io_failure_leaves_setup_retryable(self):
        controller = self.controller()
        plan = self.plan()
        plan.log = self.directory / "missing-parent" / "setup.log"
        controller.start(plan)
        self.assertFalse(controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assert_previous_selection()
        self.start_cached(controller, self.plan())
        self.assertTrue(controller.running)
        self.assertEqual(len(controller.process.starts), 1)
        controller.process.finish(1)

    def test_log_write_failure_still_reports_failed_step(self):
        controller = self.controller()
        self.start_cached(controller, self.plan())
        controller.log_stream.close()
        controller.log_stream = Mock()
        controller.log_stream.write.side_effect = OSError("the log drive is full")
        controller.process.current_state = QProcess.NotRunning
        try:
            with patch.object(controller.process, "readAllStandardOutput", return_value=b"failed processing step\n"):
                controller._process_finished(1, QProcess.NormalExit)
        finally:
            # An unhandled controller error should fail this assertion without
            # making test cleanup reuse the deliberately broken log writer.
            if controller.log_stream is not None:
                controller.log_stream.close()
                controller.log_stream = None
        self.assertFalse(controller.running)
        self.assertEqual(controller.results, [(False, {})])
        self.assert_previous_selection()

    def test_gui_close_cancels_guided_setup_asynchronously(self):
        dialog = EngineSettingsDialog()
        controller = self.controller(dialog)
        dialog.guided = controller
        controller.finished.connect(dialog._guided_finished)
        dialog.show()
        try:
            dialog._busy(True)
            self.start_cached(controller, self.plan())
            start = time.monotonic()
            dialog.close()
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertTrue(dialog.running, "Closing synchronously destroyed the running setup")
            self.pump(lambda: not dialog.running and not dialog.isVisible())
            self.assertGreater(controller.process.kill_calls, 0)
            self.assert_previous_selection()
        finally:
            dialog.stop_process()
            dialog.close()


if __name__ == "__main__":
    unittest.main()
