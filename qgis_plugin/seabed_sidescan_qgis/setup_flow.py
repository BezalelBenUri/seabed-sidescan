"""User-triggered asynchronous download and isolated runtime installation."""

import json
import os
import signal
from pathlib import Path
from urllib.parse import quote

from qgis.core import QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtCore import QLockFile, QObject, QProcess, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from .engine import (
    ENGINE_KEY,
    RAW_PYTHON_KEY,
    RAW_REPO_KEY,
    process_environment,
    taskkill_executable,
)
from .setup_plan import MICROMAMBA_BYTES, MICROMAMBA_SHA256, MICROMAMBA_URL, sha256


class GuidedSetup(QObject):
    message = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.canceled = False
        self.plan = None
        self.steps = []
        self.reply = None
        self.download_stream = None
        self.log_stream = None
        self.lock = None
        self.download_bytes = 0
        self.redirects = 0
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.killer = QProcess(self)
        self.killer.finished.connect(lambda *_: self._kill_main())
        self.killer.errorOccurred.connect(lambda *_: self._kill_main())
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._download_timeout)

    def _log(self, message):
        self.message.emit(message)
        if self.log_stream:
            try:
                self.log_stream.write(message)
                self.log_stream.flush()
            except OSError:
                try:
                    self.log_stream.close()
                except OSError:
                    pass
                self.log_stream = None
                self.message.emit("The setup log could not be saved. On-screen messages remain available.\n")

    def start(self, plan):
        if self.running:
            return
        self.plan = plan
        self.running = True
        self.canceled = False
        self.steps = plan.steps(Path(__file__).with_name("check_installation.py"))
        self.lock = QLockFile(str(plan.root / "setup.lock"))
        self.lock.setStaleLockTime(0)
        if not self.lock.tryLock(0):
            self._finish(False, "Another setup is using this installation folder. Wait for it to finish or choose another folder.")
            return
        try:
            self.log_stream = plan.log.open("w", encoding="utf-8")
            self._log("Preparing processing tools. Your current engine remains selected until all checks pass.\n")
            self._log("Setup log: " + str(plan.log) + "\n")
            plan.micromamba.parent.mkdir(parents=True, exist_ok=True)
            if plan.micromamba.is_file() and sha256(plan.micromamba) == MICROMAMBA_SHA256:
                QTimer.singleShot(0, self._next_step)
            else:
                self.redirects = 0
                self._begin_download(QUrl(MICROMAMBA_URL))
        except OSError as exc:
            self._finish(False, "Cannot prepare the setup files: " + str(exc))

    def _begin_download(self, url):
        if url.scheme().lower() != "https" or self.redirects > 5:
            self._finish(False, "The installer download used an unsafe or excessive redirect.")
            return
        self.status.emit("Downloading the processing-tools installer…")
        self.progress.emit(0)
        self.download_bytes = 0
        try:
            self.download_stream = self.plan.micromamba.with_suffix(".part").open("wb")
        except OSError as exc:
            self._finish(False, "Cannot save the installer download: " + str(exc))
            return
        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        self.reply = QgsNetworkAccessManager.instance().get(request)
        self.reply.readyRead.connect(self._download_ready)
        self.reply.downloadProgress.connect(self._download_progress)
        self.reply.finished.connect(self._download_finished)
        self.timeout.start(90000)

    def _download_ready(self):
        if self.reply is None or self.download_stream is None:
            return
        block = bytes(self.reply.readAll())
        self.download_bytes += len(block)
        if self.download_bytes > MICROMAMBA_BYTES:
            self._finish(False, "The installer download exceeded its verified size.")
            return
        try:
            self.download_stream.write(block)
        except OSError as exc:
            self._finish(False, "Cannot write the installer download: " + str(exc))
            return
        self.timeout.start(90000)

    def _download_progress(self, received, total):
        if self.running:
            self.progress.emit(min(100, int(received * 100 / MICROMAMBA_BYTES)))

    def _download_timeout(self):
        self._finish(False, "The download stopped responding. Check the internet connection and try again.")

    def _download_finished(self):
        if not self.running or self.reply is None:
            return
        self.timeout.stop()
        reply = self.reply
        self._download_ready()
        if not self.running:
            return
        self.timeout.stop()
        try:
            self.download_stream.close()
        except OSError as exc:
            self.download_stream = None
            self._finish(False, "Cannot finish saving the installer download: " + str(exc))
            return
        self.download_stream = None
        redirect = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
        error = reply.error()
        error_message = reply.errorString()
        self.reply = None
        if redirect:
            url = reply.url().resolved(redirect)
            reply.deleteLater()
            self.redirects += 1
            self._begin_download(url)
            return
        reply.deleteLater()
        if error != QNetworkReply.NoError:
            self._finish(False, "Could not download the installer: " + error_message)
            return
        partial = self.plan.micromamba.with_suffix(".part")
        try:
            if self.download_bytes != MICROMAMBA_BYTES or sha256(partial) != MICROMAMBA_SHA256:
                self._finish(False, "The installer failed its integrity check. Nothing was executed; try again.")
                return
            partial.replace(self.plan.micromamba)
        except OSError as exc:
            self._finish(False, "Cannot save the verified installer: " + str(exc))
            return
        self._log("Installer download verified.\n")
        self._next_step()

    @staticmethod
    def _proxy_environment(environment):
        settings = QgsSettings()
        if settings.value("proxy/proxyEnabled", False, type=bool):
            host = str(settings.value("proxy/proxyHost", "") or "").strip()
            if host:
                proxy_type = str(settings.value("proxy/proxyType", "HttpProxy"))
                if proxy_type not in {"HttpProxy", "HttpCachingProxy"}:
                    raise ValueError("Guided dependency installation currently supports HTTP proxies. Configure an existing engine in Advanced settings for other proxy types.")
                user = str(settings.value("proxy/proxyUser", "") or "")
                password = str(settings.value("proxy/proxyPassword", "") or "")
                authority = (quote(user, safe="") + ":" + quote(password, safe="") + "@") if user else ""
                port = str(settings.value("proxy/proxyPort", "8080") or "8080")
                proxy = "http://" + authority + host + ":" + port
                environment.insert("HTTP_PROXY", proxy)
                environment.insert("HTTPS_PROXY", proxy)
        return environment

    def _next_step(self):
        if not self.running or self.canceled:
            return
        if not self.steps:
            try:
                report = json.loads(self.plan.record.read_text(encoding="utf-8"))
                if (report["status"] != "verified" or report["engine_version"] != self.plan.version
                        or Path(report["python"]).resolve() != self.plan.python.resolve()
                        or report["raw_repository"] != (str(self.plan.raw_source.resolve()) if self.plan.raw_source else None)):
                    raise ValueError("The verification record does not match this installation.")
                settings = QgsSettings()
                if self.plan.raw_source:
                    settings.setValue(RAW_REPO_KEY, str(self.plan.raw_source))
                    settings.setValue(RAW_PYTHON_KEY, str(self.plan.python))
                # A raster-only install keeps any separately configured raw backend.
                settings.setValue(ENGINE_KEY, str(self.plan.python))
                settings.sync()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._finish(False, "Could not verify the completed installation: " + str(exc))
                return
            self._finish(True, "Processing tools installed, checked and selected. You can now use the Seabed Sidescan tools.", report)
            return
        executable, arguments, label = self.steps.pop(0)
        self.status.emit(label)
        self.progress.emit(-1)
        self._log(label + "\n")
        try:
            if executable == self.plan.python:
                (self.plan.prefix / "var" / "gmt").mkdir(parents=True, exist_ok=True)
            environment = self._proxy_environment(process_environment(str(executable)))
        except (OSError, ValueError) as exc:
            self._finish(False, str(exc))
            return
        for key in ("CONDA_DEFAULT_ENV", "MAMBA_ROOT_PREFIX", "CONDA_PKGS_DIRS"):
            environment.remove(key)
        if executable == self.plan.micromamba:
            environment.remove("CONDA_PREFIX")
        environment.insert("MAMBA_ROOT_PREFIX", str(self.plan.root / "package-cache"))
        environment.insert("CONDA_PKGS_DIRS", str(self.plan.root / "package-cache" / "pkgs"))
        environment.insert("NO_COLOR", "1")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(self.plan.prefix.parent))
        self.process.start(str(executable), list(arguments))

    def _read_output(self):
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if output:
            self._log(output)

    def _process_finished(self, exit_code, exit_status):
        self._read_output()
        if not self.running:
            return
        if self.canceled:
            self._finish(False, "Setup canceled. The previous engine selection was kept; you can retry.")
        elif exit_status != QProcess.NormalExit or exit_code != 0:
            self._finish(False, f"Setup failed (exit {exit_code}). The previous selection was kept. Review the setup log and try again.")
        else:
            self._next_step()

    def _process_error(self, error):
        if self.running and error == QProcess.FailedToStart:
            self._finish(False, "Could not start a setup step: " + self.process.errorString())

    def cancel(self):
        if not self.running or self.canceled:
            return
        self.canceled = True
        self.steps = []
        self.status.emit("Canceling setup…")
        if self.reply is not None:
            self._finish(False, "Setup canceled. The previous engine selection was kept; you can retry.")
        elif self.process.state() == QProcess.NotRunning:
            self._finish(False, "Setup canceled. The previous engine selection was kept; you can retry.")
        elif os.name == "nt":
            self.killer.start(taskkill_executable(), ["/PID", str(self.process.processId()), "/T", "/F"])
            QTimer.singleShot(5000, self._kill_main)
        else:
            try:
                pid = int(self.process.processId())
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._kill_main()

    def _kill_main(self):
        if self.canceled and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def _finish(self, success, message, report=None):
        if not self.running:
            return
        self.running = False
        self.timeout.stop()
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
            reply.deleteLater()
        if self.download_stream is not None:
            try:
                self.download_stream.close()
            except OSError:
                pass
            self.download_stream = None
        partial = self.plan.micromamba.with_suffix(".part")
        if self.lock is None or self.lock.isLocked():
            try:
                if partial.exists():
                    partial.unlink()
            except OSError:
                self.message.emit("The incomplete download could not be removed. Retry after checking folder permissions.\n")
        self._log(message + "\n")
        if self.log_stream:
            try:
                self.log_stream.close()
            except OSError:
                pass
            self.log_stream = None
        if self.lock is not None:
            self.lock.unlock()
            self.lock = None
        self.status.emit(message)
        self.progress.emit(100 if success else 0)
        self.finished.emit(success, report or {})
