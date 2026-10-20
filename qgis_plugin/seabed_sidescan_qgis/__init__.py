"""QGIS entry point. The scientific backend always runs outside QGIS."""


def classFactory(iface):
    from .plugin import SeabedSidescanPlugin

    return SeabedSidescanPlugin(iface)
