# Modified for Seabed Sidescan on 2026-10-19: GUI dependencies are optional.
# Upstream attribution and local change history: ../../THIRD_PARTY.md.
from sidescantools.sidescan_preproc import SidescanPreprocessor
from sidescantools.sidescan_file import SidescanFile
from sidescantools.georef_thread import Georeferencer
from sidescantools.egn_table_build import (
    generate_egn_info,
    generate_egn_table_from_infos,
)
from sidescantools.aux_functions import convert_to_dB, hist_equalization
from sidescantools.cfg_parser import CFG, GAINSTRAT
# GUI-only imports are optional so the CLI can run in the lighter
# environment_cli.yml environment without Qt/napari installed.
try:
    from sidescantools.custom_threading import (
        FileImportManager,
        EGNTableBuilder,
        PreProcManager,
        NavPlotter,
        GeoreferencerManager,
    )
    from sidescantools.custom_widgets import (
        QHLine,
        Labeled2Buttons,
        LabeledLineEdit,
        OverwriteWarnDialog,
        ErrorWarnDialog,
        FilePicker,
    )
    from sidescantools.bottom_detection_napari_ui import run_napari_btm_line
except Exception:
    pass
from sidescantools.xtf_wrapper import XTFWrapper
from sidescantools.jsf import JSFFile, JSFSystemInformation, JSFSonarDataPacket
