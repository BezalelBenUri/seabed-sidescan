"""Explicit, asynchronous setup for users who do not use a terminal."""

import os
import signal
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path

from qgis.core import QgsApplication, QgsProcessingException, QgsSettings
from qgis.PyQt.QtCore import QProcess, Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .engine import (
    ENGINE_KEY,
    ENGINE_VERSION,
    checked_python,
    configured_python,
    process_environment,
    taskkill_executable,
)
from .setup_flow import GuidedSetup
from .setup_plan import prepare_installation, windows_64


class EngineSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Seabed Sidescan processing tools")
        self.resize(760, 640)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.steps = []
        self.running = False
        self.installing = False
        self.canceled = False
        self.pending_output = ""
        self.save_on_success = False
        self.close_requested = False
        self.picker_buttons = []
        self.killer = QProcess(self)
        self.killer.finished.connect(lambda *_: self._kill_main_process())
        self.killer.errorOccurred.connect(lambda *_: self._kill_main_process())
        self.managed_directory = Path(QgsApplication.qgisSettingsDirPath()) / "seabed_sidescan" / ("engine-" + ENGINE_VERSION)
        self.managed_python = self.managed_directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.guided = GuidedSetup(self)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Install the processing tools once, then process your sonar data locally. "
            "Setup needs an internet connection; normal processing does not. "
            "After setup, open Processing > Toolbox and search for Seabed Sidescan."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        guided_group = QGroupBox("Guided setup")
        guided_form = QFormLayout(guided_group)
        self.folder_edit = QLineEdit(str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SeabedSidescan"))
        folder_widget = QWidget()
        folder_row = QHBoxLayout(folder_widget)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.addWidget(self.folder_edit)
        self.folder_button = QPushButton("Browse…")
        self.folder_button.clicked.connect(self._choose_install_folder)
        folder_row.addWidget(self.folder_button)
        guided_form.addRow("Installation folder", folder_widget)
        storage = QLabel("Allow at least 6 GB free for the tools and download cache. A first installation can take several minutes.")
        storage.setWordWrap(True)
        guided_form.addRow(storage)
        self.raw_checkbox = QCheckBox("Include raw-sonar conversion (XTF; JSF is experimental)")
        self.raw_checkbox.setChecked(True)
        guided_form.addRow(self.raw_checkbox)
        self.setup_button = QPushButton("Install tools")
        self.setup_button.clicked.connect(self.install_tools)
        guided_form.addRow(self.setup_button)
        if not windows_64():
            self.setup_button.setEnabled(False)
            notice = QLabel("Guided setup currently supports 64-bit Windows. Use Advanced settings to select an existing engine on another platform.")
            notice.setWordWrap(True)
            guided_form.addRow(notice)
        layout.addWidget(guided_group)
        self.advanced_toggle = QCheckBox("Advanced settings — use or install an existing Python engine")
        layout.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        existing = QGroupBox("Existing engine")
        existing_form = QFormLayout(existing)
        self.python_edit = QLineEdit(configured_python())
        existing_form.addRow("Python executable", self._picker(self.python_edit, "Choose engine Python executable"))
        self.check_button = QPushButton("Check engine")
        self.check_button.clicked.connect(self.check_engine)
        existing_form.addRow(self.check_button)
        advanced_layout.addWidget(existing)

        install = QGroupBox("Managed engine installer")
        install_form = QFormLayout(install)
        help_label = QLabel(
            "Select a standalone Python 3.10 or newer (not QGIS Python). Choose the local "
            "seabed-sidescan wheel supplied with the release, or leave it empty to download "
            f"seabed-sidescan=={ENGINE_VERSION} from PyPI once that release is published. "
            "Clicking Install downloads and installs this package and its dependencies "
            "into the managed environment shown below. Internet access is needed for dependencies."
        )
        help_label.setWordWrap(True)
        install_form.addRow(help_label)
        self.base_edit = QLineEdit()
        install_form.addRow("Base Python", self._picker(self.base_edit, "Choose standalone Python executable"))
        self.wheel_edit = QLineEdit()
        self.wheel_edit.setPlaceholderText(f"Optional local seabed_sidescan-{ENGINE_VERSION}-*.whl")
        install_form.addRow("Release wheel", self._picker(self.wheel_edit, "Choose seabed-sidescan wheel", "Python wheels (*.whl)"))
        self.destination = QLabel(str(self.managed_directory))
        self.destination.setWordWrap(True)
        install_form.addRow("Managed environment", self.destination)
        self.install_button = QPushButton("Install / update managed engine")
        self.install_button.clicked.connect(self.install_engine)
        install_form.addRow(self.install_button)
        advanced_layout.addWidget(install)
        layout.addWidget(self.advanced)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(3000)
        layout.addWidget(self.log)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status = QLabel("Click Install tools to prepare the processing environment.")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bottom = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel operation")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.stop_process)
        bottom.addWidget(self.cancel_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        self.buttons.button(QDialogButtonBox.Save).hide()
        self.advanced_toggle.toggled.connect(self.buttons.button(QDialogButtonBox.Save).setVisible)
        self.buttons.button(QDialogButtonBox.Save).clicked.connect(self.save_settings)
        self.buttons.rejected.connect(self.close)
        bottom.addWidget(self.buttons)
        layout.addLayout(bottom)
        self.guided.message.connect(self._guided_output)
        self.guided.status.connect(self.status.setText)
        self.guided.progress.connect(self._guided_progress)
        self.guided.finished.connect(self._guided_finished)

    def _choose_install_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose the processing-tools installation folder", self.folder_edit.text())
        if directory:
            self.folder_edit.setText(directory)

    def install_tools(self):
        if self.running:
            return
        if not self.folder_edit.text().strip():
            self.status.setText("Choose an installation folder for the processing tools.")
            return
        try:
            plan = prepare_installation(Path(self.folder_edit.text()),
                Path(__file__).parent / "resources" / "setup", ENGINE_VERSION, raw=self.raw_checkbox.isChecked())
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.status.setText(str(exc))
            return
        self.log.clear()
        self._busy(True)
        try:
            self.guided.start(plan)
        except OSError as exc:
            self.status.setText("Cannot start setup: " + str(exc))
            self._busy(False)

    def _guided_output(self, output):
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(output)
        self.log.ensureCursorVisible()

    def _guided_progress(self, value):
        self.progress_bar.setRange(0, 0 if value < 0 else 100)
        if value >= 0:
            self.progress_bar.setValue(value)

    def _guided_finished(self, success, report):
        if success:
            self.managed_python = Path(report["python"])
            self.managed_directory = self.managed_python.parent
            self.python_edit.setText(str(self.managed_python))
            self.destination.setText(str(self.managed_directory))
        self._busy(False)

    def _picker(self, edit, title, file_filter="All files (*)"):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        button = QPushButton("Browse…")
        self.picker_buttons.append(button)

        def choose():
            selected, _ = QFileDialog.getOpenFileName(self, title, edit.text(), file_filter)
            if selected:
                edit.setText(selected)

        button.clicked.connect(choose)
        row.addWidget(button)
        return widget

    def _busy(self, value):
        self.running = value
        for widget in (self.check_button, self.install_button, self.base_edit, self.wheel_edit, self.python_edit,
                       self.folder_edit, self.folder_button, self.raw_checkbox, self.advanced_toggle, *self.picker_buttons):
            widget.setEnabled(not value)
        self.setup_button.setEnabled(not value and windows_64())
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not value)
        self.cancel_button.setEnabled(value)
        if not value and self.close_requested:
            self.close_requested = False
            QTimer.singleShot(0, self.close)

    def _run_steps(self, steps, installing=False, save_on_success=False):
        self.log.clear()
        self.pending_output = ""
        self.canceled = False
        self.installing = installing
        self.save_on_success = save_on_success
        self.steps = list(steps)
        self._busy(True)
        self._next_step()

    def _next_step(self):
        if not self.steps:
            if self.installing:
                self.python_edit.setText(str(self.managed_python))
                QgsSettings().setValue(ENGINE_KEY, str(self.managed_python))
                self.status.setText("Managed engine installed, checked and selected. The Processing tools are ready.")
            else:
                if self.save_on_success:
                    QgsSettings().setValue(ENGINE_KEY, checked_python(self.python_edit.text()))
                    self.status.setText("Engine checked and selection saved. Open Processing > Toolbox and search for Seabed Sidescan.")
                else:
                    self.status.setText("Engine check passed. Click Save to select this interpreter.")
            self._busy(False)
            return
        executable, arguments, label = self.steps.pop(0)
        self.status.setText(label)
        self.log.append(label)
        self.process.setProcessEnvironment(process_environment(executable))
        self.process.setWorkingDirectory(str(Path.home()))
        if os.name != "nt":
            arguments = ["-u", "-c", "import os, sys; os.setsid(); os.execv(sys.executable, [sys.executable, *sys.argv[1:]])", *arguments]
        self.process.start(str(executable), list(arguments))

    def _read_output(self, final=False):
        self.pending_output += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        lines = self.pending_output.split("\n")
        self.pending_output = lines.pop()
        if final and self.pending_output:
            lines.append(self.pending_output)
            self.pending_output = ""
        for line in lines:
            # QTextEdit.append interprets HTML; insertPlainText preserves subprocess logs.
            self.log.moveCursor(self.log.textCursor().End)
            self.log.insertPlainText(line.rstrip("\r") + "\n")
        self.log.ensureCursorVisible()

    def _finished(self, exit_code, exit_status):
        self._read_output(final=True)
        if self.canceled:
            self.steps = []
            self.status.setText("Operation canceled. You can run the installer again to finish setup.")
            self._busy(False)
        elif exit_status != QProcess.NormalExit or exit_code != 0:
            self.steps = []
            self.status.setText(f"Engine operation failed (exit {exit_code}). Review the log above; the previous selection was kept.")
            self._busy(False)
        else:
            self._next_step()

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self.steps = []
            self.log.insertPlainText(self.process.errorString() + "\n")
            self.status.setText("Could not start this Python executable. Choose a standalone Python installation.")
            self._busy(False)

    @staticmethod
    def _backend_check():
        return [
            "-u", "-c",
            "import sys; from seabed_sidescan import __version__; "
            f"assert __version__ == {ENGINE_VERSION!r}, 'Expected seabed-sidescan {ENGINE_VERSION}, got ' + __version__; "
            "import numpy, rasterio, shapefile, scipy, skimage, sklearn, yaml; "
            "from seabed_sidescan.cli import main; print('Python:', sys.executable); "
            "main(['--version'])",
        ]

    def check_engine(self):
        if self.running:
            return
        try:
            executable = checked_python(self.python_edit.text())
        except QgsProcessingException as exc:
            self.status.setText(str(exc))
            return
        self._run_steps([(executable, self._backend_check(), "Checking backend version and dependencies…")])

    def install_engine(self):
        if self.running:
            return
        try:
            base = checked_python(self.base_edit.text())
        except QgsProcessingException as exc:
            self.status.setText("Choose a standalone Python 3.10 or newer as the base Python. " + str(exc))
            return
        wheel = self.wheel_edit.text().strip()
        if wheel:
            path = Path(wheel).expanduser()
            if not path.is_file() or path.suffix.lower() != ".whl" or not path.name.lower().startswith("seabed_sidescan-"):
                self.status.setText("Choose the seabed_sidescan release wheel (.whl).")
                return
            try:
                with zipfile.ZipFile(path) as archive:
                    names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
                    if len(names) != 1:
                        raise ValueError("The wheel must contain one package metadata file.")
                    metadata = BytesParser().parsebytes(archive.read(names[0]))
                    if str(metadata.get("Name", "")).replace("_", "-").lower() != "seabed-sidescan" or metadata.get("Version") != ENGINE_VERSION:
                        raise ValueError(f"This plugin requires the seabed-sidescan {ENGINE_VERSION} wheel.")
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                self.status.setText(f"Cannot use this release wheel: {exc}")
                return
            package = str(path.resolve())
        else:
            package = "seabed-sidescan==" + ENGINE_VERSION
        # Venvs contain absolute interpreter paths. Keep each installation in its
        # final directory and change the saved selection only after verification;
        # a failed update must not damage a previously working engine.
        if self.managed_directory.exists():
            self.managed_directory = self.managed_directory.parent / ("engine-" + ENGINE_VERSION + "-" + uuid.uuid4().hex[:12])
            self.managed_python = self.managed_directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self.destination.setText(str(self.managed_directory))
        try:
            self.managed_directory.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status.setText(f"Cannot create the managed environment folder: {exc}")
            return
        self._run_steps([
            (base, ["-u", "-c", "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer is required'; print(sys.version)"], "Checking standalone Python…"),
            (base, ["-u", "-m", "venv", str(self.managed_directory)], "Creating the managed Python environment…"),
            (str(self.managed_python), ["-u", "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", package], "Installing the backend and dependencies…"),
            (str(self.managed_python), self._backend_check(), "Checking the installed backend…"),
        ], installing=True)

    def stop_process(self):
        if self.guided.running:
            self.guided.cancel()
            return
        if self.running and not self.canceled:
            self.canceled = True
            self.steps = []
            self.cancel_button.setEnabled(False)
            self.status.setText("Canceling the operation and its child processes…")
            if self.process.state() == QProcess.NotRunning:
                self._busy(False)
            elif os.name == "nt":
                self.killer.start(taskkill_executable(), ["/PID", str(self.process.processId()), "/T", "/F"])
                QTimer.singleShot(5000, self._kill_main_process)
            else:
                try:
                    pid = int(self.process.processId())
                    if os.getpgid(pid) == pid:
                        os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self._kill_main_process()

    def _kill_main_process(self):
        if self.canceled and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def save_settings(self):
        if self.running:
            return
        try:
            executable = checked_python(self.python_edit.text())
        except QgsProcessingException as exc:
            self.status.setText(str(exc))
            return
        self._run_steps([(executable, self._backend_check(), "Checking engine before saving…")], save_on_success=True)

    def closeEvent(self, event):
        if self.running:
            self.close_requested = True
            self.stop_process()
            event.ignore()
        else:
            event.accept()
