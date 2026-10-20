from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .provider import SeabedSidescanProvider
from .settings import EngineSettingsDialog


class SeabedSidescanPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.actions = []
        self.settings_dialog = None

    def initProcessing(self):
        """Register in both desktop QGIS and headless qgis_process sessions."""
        registry = QgsApplication.processingRegistry()
        if self.provider is None and registry.providerById("seabed_sidescan") is None:
            self.provider = SeabedSidescanProvider()
            registry.addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        icon = QIcon(str(Path(__file__).with_name("icon.svg")))
        toolbox = QAction(icon, "Seabed Sidescan tools", self.iface.mainWindow())
        toolbox.triggered.connect(self.open_toolbox)
        settings = QAction("Set up processing tools…", self.iface.mainWindow())
        settings.triggered.connect(self.open_settings)
        self.actions = [toolbox, settings]
        for action in self.actions:
            self.iface.addPluginToRasterMenu("Seabed Sidescan", action)
        self.iface.addToolBarIcon(toolbox)

    def open_toolbox(self):
        from qgis.utils import plugins

        processing_plugin = plugins.get("processing")
        if processing_plugin is None or not hasattr(processing_plugin, "toolbox"):
            QMessageBox.information(
                self.iface.mainWindow(), "Seabed Sidescan",
                "Enable the Processing plugin in Plugins > Manage and Install Plugins, "
                "then open Processing > Toolbox and search for Seabed Sidescan."
            )
            return
        toolbox = processing_plugin.toolbox
        toolbox.setUserVisible(True)
        toolbox.searchBox.setText("Seabed Sidescan")
        toolbox.searchBox.setFocus()

    def open_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = EngineSettingsDialog(self.iface.mainWindow())
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def unload(self):
        if self.settings_dialog is not None:
            self.settings_dialog.stop_process()
            self.settings_dialog.close()
            self.settings_dialog = None
        if self.actions:
            self.iface.removeToolBarIcon(self.actions[0])
        for action in self.actions:
            self.iface.removePluginRasterMenu("Seabed Sidescan", action)
            action.deleteLater()
        self.actions = []
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
