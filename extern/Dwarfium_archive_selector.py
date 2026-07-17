"""
(c) 2026, Stefan Schmidt-Bilkenroth
SPDX-License-Identifier: GPL-3.0-or-later

Dwarfum Session Selector
Version 0.9.0
"""

"""
ChangeLog:
    0.9.0   initial release, beta state for gathering feedback
"""

from genericpath import exists

import sirilpy as s
from sirilpy import LogColor

s.ensure_installed(["PyQt6"])

import json
import os
import shlex
import shutil
import sys
import zipfile
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Dwarfium Archive Selector"
VERSION = "0.9.1"
BUILD = "20260312"
AUTHOR = "Stefan Schmidt-Bilkenroth"

PRESET_FILE = "dwarfium-archive-select.json"
PRESET_JSON = """
{
    "archive_dir": null
}
"""

HELP_MD = """
## Help for Dwarfium Archive Selector

>This script is for convenience when preparing processing sessions shot
with smart telescopes made by Dwarf Lab. Its intention is, to ease preparation
of light images for stacking inside Siril.
The script assumes, that the Archive is organized the same way as on the
Dwwarf Lab devices. This can be achieved by either using tool like `rsync`
to archive the sessions or by using **Dwarfium Scope Archive**, which is my
recommendation. Thanks to JC. Lesaint for his tool.

### Step 1: Select the Folder containing your archived Dwarf session

>Click the button `Change` and use the File Selector Dialog to chose
the **Astronomy** folder containing all the Dwarf Sessions you have collected.
After choosing a folder, the path to the folder is shown in green color.
The folder is saved in the preferences of the script (in Siril preferences folder)
When the path to the Archive is shown in red color, the path is not available.
This can happen, when the Archive is located on an external drive and this one
is not connected, when the script is started.

>With the `Refresh` button you can trigger to scan the archive once again
in case you have added or removed sessions in the archive, after the script
was already started

>You can't change the Siril Home directory within this script, the path is
only shown for your information.

### Step 2: Select the Target in the left panel

>After choosing an Archive folder, the script will parse the file tree inside
the archive and gather information for all sessions found in the Archive.
The folder names inside the archive are parsed based on the naming pattern used
by Dwarf Lab when storing sessions onto their devices.
The script also inspects the `shotsinfo.json` file inside each session for
additional information (number of stacked images, filter selection, ...)

>All the targets, based on the Dwarf Lab naming schema, found in these sessions
are then displayed in the left panel. Ths number of session found for each target
is shown in parenthesis.

>It can happen, that some folder names with sessions do not match the naming
schema. These are ignored by the script but you can check the Siril Log for
more information.

>MegaStack sessions are ignored, as they do not contain indiviudal image, only
the result of the MegaStack processing. Check the Siril Log for more information.

### Step 3: Select the Sessions in the right panel

>After chosing a target in the left panel the right panel shows all sessions
on this target with session start date, number of stacked images, exposre time,
gain and filter.

>In the right pane you can chose one or more sessions. In the bottom the number
of selected images updates accordingly and is showing the total count of images
across the selected sessions.

### Step 4: Copy the lights from the selected sessions

>When you have at least selected one session with at least 1 image, the `Copy`
Button gets enabled. When you are happy with your selection, click on the
`Copy` button.

>The script will check if there are any images in the lights folder inside
the current Siril Home and if necessary ask for confirmation to delete them.
Also the `process` folder in Siril Home is deleted.

>Then it will start to copy all the images of the selected session from the
Archive into the new "lights" folder inside Siril home.
>This can take a while, but the progress of these file copy operation is
shown next to the `Copy` button.

### Step 5: Close the script window and continue your workflow

>After copying the files is completed you can close the script and
continue your workflow.

### ToDos:
- add safeguards around file operations
- move archive scan to background thread, be more responsive on slower systems
- proper handling of Mosaic sessions

### Caveats
>This script is provided as is and the Author takes now liability on its
functionality and any damage or loss of data when using the script.

### Legal Information:

**Author**: Stefan Schmidt-Bilkenroth

For suggestions, support and issues feel free to contact me:

>facebook: `https://www.facebook.com/stefan.ssb`

>mastodon: `https://gruene.social/@ssb`

>e-mail: `ssb@mac.com`

(c) 2026, Stefan Schmidt-Bilkenroth

SPDX-License-Identifier: GPL-3.0-or-later
"""

def win_long_path(filepath):
    if os.name == 'nt': 
        filepath_str = str(filepath) 
        if filepath_str.startswith('\\\\?\\'): 
            return filepath_str # already in long path format 
        else: 
            return '\\\\?\\' + os.path.abspath(filepath_str)
    else: return str(filepath)

class Target:
    """Target Class contains the targets from the Dwarfium archives with their sessions"""

    def __init__(self, target):
        self.target = target
        self.sessions = []

    def add_session(self, session):
        self.sessions.append(session)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.target}: {len(self.sessions)} sessions"


class Session:
    """Session Class contains the information of the single session"""

    def __init__(self, path, cam, target, exp, gain, date):
        self.cam = cam
        self.target = target
        self.exposure = exp
        self.gain = gain
        self.date = date
        self.thumbnail = os.path.join(path, "stacked.jpg")
        self.ra = None
        self.dec = None
        self.min_temp = None
        self.max_temp = None
        try:
            self.prettydate = datetime.strptime(date, "%Y-%m-%d-%H-%M-%S-%f")
        except:
            self.siril.log(f"Invalid date format: {date}", LogColor.RED)
            return None

        self.calendardate = datetime(
            self.prettydate.year,
            self.prettydate.month,
            self.prettydate.day,
            self.prettydate.hour,
            self.prettydate.minute,
        )
        self.path = path
        self.ir = "unknown"
        self.taken = 0
        self.stacked = 0

    def __str__(self):
        return "'{}' with {}, {}s/{}g on {}".format(
            self.target, self.cam.lower(), self.exposure, self.gain, self.date
        )


class CopyMultiThread(QThread):
    """Copy files from multiple source→dest pairs in the background."""
    progress = pyqtSignal(int)
    done     = pyqtSignal(int)

    def __init__(self, pairs):
        """pairs: list of (src_path, dest) tuples.
        dest may be a directory OR a full destination file path (used to rename
        files on copy and avoid collisions between sessions)."""
        QThread.__init__(self, None)
        self.pairs = pairs

    def run(self):
        done = 0
        for src, dest in self.pairs:
            root, ext = os.path.splitext(dest)
            if ext:
                # dest is a full file path — create its parent dir
                os.makedirs(os.path.dirname(dest), exist_ok=True)
            else:
                # dest is a directory
                os.makedirs(dest, exist_ok=True)
            try:
                print(f"COPY:\n  {src}\n  -> {dest}")
                shutil.copy2(win_long_path(src), win_long_path(dest))
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                raise
            done += 1
            self.progress.emit(done)
        self.done.emit(done)


class MosaicTileExtractThread(QThread):
    """Extract/copy already-stacked RESTACKED_ tile FITS files into a single
    working folder, ready for astrometric mosaic stitching in Siril.

    Each tile (a session whose name starts with "RESTACKED_") contributes
    either:
      - one stacked-16*.fits file directly in its session_dir, or
      - one or more stacked-16*.fits files packed inside a stacked-16*.zip
        at the root of its session_dir, if the session name contains
        "_MOSAIC_" (the session itself was a multi-panel mosaic capture
        that got pre-stacked panel by panel).
    Tiles are renamed with a session index prefix to avoid collisions.
    """
    progress = pyqtSignal(int)
    done     = pyqtSignal(int, list)  # (tile_count, error_messages)

    def __init__(self, sessions, dest_dir):
        QThread.__init__(self, None)
        self.sessions = sessions
        self.dest_dir = dest_dir

    def run(self):
        os.makedirs(self.dest_dir, exist_ok=True)
        tile_count = 0
        errors = []

        for s_idx, sess in enumerate(self.sessions, 1):
            session_dir  = sess.get("session_dir") or ""
            session_name = sess.get("session_name") or os.path.basename(session_dir)
            is_mosaic    = "_MOSAIC_" in session_name.upper()

            if not os.path.isdir(session_dir):
                errors.append(f"{session_name}: folder not found ({session_dir})")
                continue

            try:
                if is_mosaic:
                    zips = sorted(
                        f for f in os.listdir(session_dir)
                        if f.lower().startswith("stacked-16") and f.lower().endswith(".zip")
                    )
                    if not zips:
                        errors.append(f"{session_name}: no stacked-16*.zip found")
                        continue
                    zip_path = os.path.join(session_dir, zips[0])
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        fits_members = [
                            m for m in zf.namelist()
                            if os.path.basename(m).lower().startswith("stacked-16")
                            and os.path.basename(m).lower().endswith((".fits", ".fit", ".fts"))
                        ]
                        if not fits_members:
                            errors.append(f"{session_name}: zip contains no stacked-16 FITS")
                            continue
                        for m_idx, member in enumerate(sorted(fits_members), 1):
                            ext = os.path.splitext(member)[1]
                            dest_name = f"tile{s_idx:02d}_{m_idx:02d}{ext}"
                            dest_path = os.path.join(self.dest_dir, dest_name)
                            with zf.open(member) as src_f, open(dest_path, "wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
                            tile_count += 1
                            self.progress.emit(tile_count)
                else:
                    fits_files = sorted(
                        f for f in os.listdir(session_dir)
                        if f.lower().startswith("stacked-16")
                        and f.lower().endswith((".fits", ".fit", ".fts"))
                    )
                    if not fits_files:
                        errors.append(f"{session_name}: no stacked-16*.fits found")
                        continue
                    src_path = os.path.join(session_dir, fits_files[0])
                    ext = os.path.splitext(fits_files[0])[1]
                    dest_name = f"tile{s_idx:02d}{ext}"
                    dest_path = os.path.join(self.dest_dir, dest_name)
                    shutil.copy2(win_long_path(src_path), win_long_path(dest_path))
                    tile_count += 1
                    self.progress.emit(tile_count)
            except Exception as e:
                errors.append(f"{session_name}: {e}")

        self.done.emit(tile_count, errors)


class CopyThread(QThread):
    """Thread to copy the files in the background, otherise the progress bar would not update"""

    progress = pyqtSignal(int)
    done = pyqtSignal(int)

    def __init__(self, files, dest):
        QThread.__init__(self, None)
        self.files = files
        self.dest = dest

    def run(self):
        done = 0
        for f in self.files:
            shutil.copy2(win_long_path(f), win_long_path(self.dest))
            done += 1
            self.progress.emit(done)
        self.done.emit(done)


def close_dialog(self):
    try:
        self.siril.disconnect()
    except Exception:
        pass  # Ignore disconnect errors
    self.close()


class PreprocessingInterface(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - v{VERSION}")
        self.initialization_successful = False

        self.siril = s.SirilInterface()

        # declare internal members
        self.archive_dir = None
        self.targets = []
        self.target_list = []
        self.selected_target = None
        self.selected_sessions = []

        try:
            self.siril.connect()
            self.siril.log("Connected to Siril", LogColor.GREEN)
        except s.SirilConnectionError:
            self.siril.log("Failed to connect to Siril", LogColor.RED)
            self.close_dialog()
            return

        try:
            self.siril.cmd("requires", "1.3.6")
        except s.CommandError:
            self.close_dialog()
            return

        self.fits_extension = self.siril.get_siril_config("core", "extension")
        # home directory is unchanged
        self.home_directory = self.siril.get_siril_wd()
        self.current_working_directory = self.siril.get_siril_wd()
        self.cwd_label = self.current_working_directory

        # Assigns collected_lights directory to store all pp_lights files
        self.collected_lights_dir = os.path.join(
            self.current_working_directory, "collected_lights"
        )
        # Stores the last loaded siril_megastack.json data, so the mosaic
        # builder (RESTACKED tiles) can reuse it without reloading the file
        self._last_megastack_data = None
        # Stores the (ssf_path, lines) of the last generated stack/combine
        # scripts, so the "Build Sessions" button can run them directly
        # without re-reading the .ssf files from disk
        self._last_generated_scripts = []
        self._mosaic_include_stacks = []
        self._last_json_path = None
        # defaults for presets
        self.load_presets()
        self.create_widgets()
        self.initialization_successful = True  # Flag to track successful initialization

    def create_path_widgets(self, main_layout):
        """create Path box widgets"""
        paths_group = QGroupBox("Current paths:")
        cwd_layout = QVBoxLayout()
        cwd_label = QLabel(f"Current working directory: {self.cwd_label}")
        cwd_layout.addWidget(cwd_label)

        # Label with Archive path
        archive_layout = QHBoxLayout()
        self.archive_label = QLabel(f"Selected archive directory: {self.archive_dir}")
        if self.archive_dir is None or not os.path.exists(self.archive_dir):
            self.archive_label.setStyleSheet("QLabel {color: #FF0000};")
        else:
            self.archive_label.setStyleSheet("QLabel {color: #00FF00};")
        archive_layout.addWidget(self.archive_label)

        # chose archive path button
        archive_choose_btn = QPushButton("Change")
        archive_choose_btn.setMinimumWidth(80)
        archive_choose_btn.setMaximumWidth(80)
        archive_choose_btn.setMinimumHeight(35)
        archive_choose_btn.clicked.connect(self.chose_archive)
        archive_layout.addWidget(archive_choose_btn)
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(80)
        refresh_btn.setMaximumWidth(80)
        refresh_btn.setMinimumHeight(35)
        refresh_btn.clicked.connect(lambda: self.scan_archive(self.archive_dir))
        archive_layout.addWidget(refresh_btn)

        cwd_layout.addLayout(archive_layout)
        paths_group.setLayout(cwd_layout)
        main_layout.addWidget(paths_group)

    def create_list_widgets(self, main_layout):
        """create widgets with the listboxes for targets and sessions"""
        files_layout = QVBoxLayout()
        list_group = QGroupBox("Targets and Session in Dwarf Archive:")
        list_layout = QHBoxLayout()
        # Listbox for targets (left)
        self.target_listbox = QListWidget()
        self.target_listbox.setMaximumWidth(300)
        self.target_listbox.itemSelectionChanged.connect(self.target_selected)
        list_layout.addWidget(self.target_listbox)

        right_layout = QVBoxLayout()
        right_info = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setMinimumHeight(160)
        self.thumb.setMaximumHeight(160)
        self.thumb.setMinimumWidth(300)
        self.thumb.setMaximumWidth(300)
        right_info.addWidget(self.thumb)

        self.info_box = QTextEdit(readOnly=True)
        self.info_box.setMinimumHeight(self.thumb.height())
        self.info_box.setMaximumHeight(self.thumb.height())
        # self.info_box.setMaximumWidth(300)
        right_info.addWidget(self.info_box)

        right_layout.addLayout(right_info)
        # Listbox for sessions
        self.session_listbox = QListWidget()
        self.session_listbox.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.session_listbox.itemSelectionChanged.connect(self.session_selected)
        right_layout.addWidget(self.session_listbox)
        list_layout.addLayout(right_layout)

        list_group.setLayout(list_layout)
        files_layout.addWidget(list_group)
        main_layout.addWidget(list_group)

    def create_bottom_widgets(self, main_layout):
        """create the widgets for the bottom part - progress bar and action buttons"""
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(
            0, 15, 0, 0
        )  # Add top margin to separate from content

        help_btn = QPushButton("?")
        help_btn.setMinimumWidth(35)
        help_btn.setMaximumWidth(35)
        help_btn.setMinimumHeight(35)
        help_btn.clicked.connect(self.show_help)
        button_layout.addWidget(help_btn)

        # progressbar for copy operation
        self.progressbar = QProgressBar()
        self.progressbar.setTextVisible(False)
        self.progressbar.setMinimumHeight(35)
        self.progressbar.setMinimum(0)
        self.progressbar.setMaximum(1)
        self.progressbar.setValue(0)
        button_layout.addWidget(self.progressbar)

        # label showing number of files to copy
        self.progress_label = QLabel("0 / 0")
        self.progress_label.setMinimumWidth(100)
        self.progress_label.setMaximumWidth(100)
        self.progress_label.setMinimumHeight(35)
        self.progress_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        button_layout.addWidget(self.progress_label)

        # copy button
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setMinimumHeight(35)
        self.copy_btn.setMinimumWidth(80)
        self.copy_btn.setMaximumWidth(80)
        self.copy_btn.setDisabled(True)
        self.copy_btn.clicked.connect(self.start_copy)
        button_layout.addWidget(self.copy_btn)

        # Load from Dwarfium JSON button
        self.json_btn = QPushButton("📡 Load Dwarfium JSON")
        self.json_btn.setMinimumHeight(35)
        self.json_btn.setMinimumWidth(160)
        self.json_btn.setToolTip(
            "Load a siril_session.json generated by Dwarfium Scope Archive\n"
            "to copy lights + darks + bias + flat into Siril working folders."
        )
        self.json_btn.clicked.connect(self.load_dwarfium_json)
        button_layout.addWidget(self.json_btn)

        # Run the generated .ssf stack/combine scripts directly in Siril
        self.build_sessions_btn = QPushButton("🚀 Build Sessions")
        self.build_sessions_btn.setMinimumHeight(35)
        self.build_sessions_btn.setMinimumWidth(150)
        self.build_sessions_btn.setToolTip(
            "Run the generated 01_stack_*.ssf (and 02_combine_*.ssf if any)\n"
            "scripts directly in this Siril session, instead of having to\n"
            "open and run the .ssf file(s) manually."
        )
        self.build_sessions_btn.setDisabled(True)
        self.build_sessions_btn.clicked.connect(self.build_sessions_from_scripts)
        button_layout.addWidget(self.build_sessions_btn)

        # Build mosaic from RESTACKED tiles (astrometric stitching)
        self.mosaic_btn = QPushButton("🧩 Build Mosaic (RESTACKED)")
        self.mosaic_btn.setMinimumHeight(35)
        self.mosaic_btn.setMinimumWidth(180)
        self.mosaic_btn.setToolTip(
            "From the loaded siril_megastack.json, extract the already-stacked\n"
            "RESTACKED_ sessions (debayered FITS, single or _MOSAIC_ zip) and\n"
            "stitch them together using Siril's astrometric mosaic alignment\n"
            "(seqplatesolve + seqapplyreg -framing=max + stack -maximize)."
        )
        self.mosaic_btn.setDisabled(True)
        self.mosaic_btn.clicked.connect(self.build_mosaic_from_restacked)
        button_layout.addWidget(self.mosaic_btn)

        # Feathering option for the mosaic stack (smooths the seam between
        # overlapping tiles — see Siril's -feather=N stack option)
        self.feather_checkbox = QCheckBox("Feather edges")
        self.feather_checkbox.setToolTip(
            "Blend overlapping tile edges with a soft gradient instead of a\n"
            "hard cut, to hide visible seams caused by sky background or\n"
            "gradient differences between tiles. Usually not needed, but\n"
            "try it if you see a visible line where tiles meet."
        )
        self.feather_checkbox.stateChanged.connect(
            lambda state: self.feather_spinbox.setEnabled(state == Qt.CheckState.Checked.value)
        )
        button_layout.addWidget(self.feather_checkbox)

        self.feather_spinbox = QSpinBox()
        self.feather_spinbox.setRange(1, 2000)
        self.feather_spinbox.setValue(100)
        self.feather_spinbox.setSuffix(" px")
        self.feather_spinbox.setMinimumWidth(80)
        self.feather_spinbox.setMaximumWidth(80)
        self.feather_spinbox.setEnabled(False)
        self.feather_spinbox.setToolTip("Width (in pixels) of the feathered blend zone.")
        button_layout.addWidget(self.feather_spinbox)

        # HaRGB blend ratio — Ha weight in the R channel composition
        # R = Ha * ratio + astro_r * (1 - ratio)
        self.ha_blend_label = QLabel("Ha blend:")
        self.ha_blend_label.setToolTip(
            "Weight of the Ha channel in the HaRGB R channel.\n"
            "R = Ha × ratio + Astro_R × (1 − ratio)\n"
            "0.7 = 70% Ha, 30% natural star color from Astro."
        )
        button_layout.addWidget(self.ha_blend_label)

        self.ha_blend_spinbox = QDoubleSpinBox()
        self.ha_blend_spinbox.setRange(0.0, 1.0)
        self.ha_blend_spinbox.setSingleStep(0.05)
        self.ha_blend_spinbox.setValue(0.7)
        self.ha_blend_spinbox.setDecimals(2)
        self.ha_blend_spinbox.setMinimumWidth(70)
        self.ha_blend_spinbox.setMaximumWidth(70)
        self.ha_blend_spinbox.setToolTip(
            "Ha blend ratio for HaRGB combination (0.0 = pure Astro R, 1.0 = pure Ha)."
        )
        button_layout.addWidget(self.ha_blend_spinbox)

        # close button
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.setMinimumHeight(35)
        close_button.clicked.connect(self.close_dialog)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

    def create_widgets(self):
        """Creates the UI widgets using PyQt6."""

        # Main layout
        main_widget = QWidget()
        self.setMinimumSize(750, 600)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 6, 12, 12)
        main_layout.setSpacing(6)

        copyright = QLabel("(c) Stefan Schmidt-Bilkenroth, 2026")
        copyright.setStyleSheet("QLabel {font-size: 10px; color: grey}")
        copyright.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(copyright)

        self.create_path_widgets(main_layout)

        self.create_list_widgets(main_layout)
        self.create_bottom_widgets(main_layout)
        self.scan_archive(self.archive_dir)

    def select_folder(self, start_dir):
        """folder selection for the Dwarfium archive"""
        if start_dir is None or not os.path.exists(start_dir):
            start_dir = self.current_working_directory
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Archive directory",
            start_dir,
        )
        return selected_dir

    def chose_archive(self):
        """function to chose Dwarfium archive"""
        archive_dir = self.select_folder(self.archive_dir)
        if archive_dir is None:
            # do not update if file selector has been cancelled
            return
        self.archive_dir = archive_dir
        self.archive_label.setText(self.archive_dir)
        self.archive_label.setStyleSheet("QLabel {color: #FF0000};")
        self.save_presets()
        self.scan_archive(self.archive_dir)
        return

    def scan_archive(self, archive_dir=None):
        """scan the archive path for subdirectories matching Dwarf naming scheme"""
        self.siril.log(
            f"Running script version {VERSION} with arguments:\n"
            f"archive_dir: {archive_dir}",
            LogColor.GREEN,
        )
        start_dir = archive_dir
        if archive_dir is None or not os.path.exists(archive_dir):
            archive_dir = None
            start_dir = self.current_working_directory

        if archive_dir is None:
            archive_dir = self.select_folder(start_dir)

        self.archive_dir = archive_dir
        sessions = self.parse_filetree(self.archive_dir)
        self.targets = self.get_targets(sessions)
        self.refresh_target_list()

        self.siril.cmd("close")

    def ask(self, title, msg):
        """helper displaying a Question Message Box"""
        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply

    def progress_update(self, value):
        """callback for progress update emitted from Copy QThread"""
        self.progressbar.setValue(value)
        self.progress_label.setText(
            f"{self.progressbar.value()} / {self.progressbar.maximum()}"
        )

    def progress_done(self, value):
        """callback for progress completed emitted from Copy QThread"""
        self.copy_btn.setDisabled(False)
        self.progressbar.setValue(0)
        self.progressbar.setMaximum(1)
        self.progress_label.setText("completed")

        reply = QMessageBox.question(
            self,
            "File copy complete",
            f"{value} files have been copied to {os.path.join(self.current_working_directory, 'lights')}",
            buttons=QMessageBox.StandardButton(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Close
            ),
            defaultButton=QMessageBox.StandardButton.Ok,
        )
        if reply == QMessageBox.StandardButton.Close:
            self.close_dialog()

    def start_copy(self):
        """action for copy button - clean current lights and start copy operation"""
        lights_dir = os.sep.join([self.current_working_directory, "lights"])
        process_dir = os.sep.join([self.current_working_directory, "process"])

        # check if lights dir contains files and ask for confirmation to delete them
        if os.path.exists(lights_dir):
            file_cnt = len(os.listdir(lights_dir))

            if file_cnt > 0:
                self.progressbar.setMaximum(0)
                self.progress_label.setText("cleanup")

                reply = self.ask(
                    "Delete existing lights?",
                    f'This operation will delete {file_cnt} files in\n"{lights_dir}".\nProceed?',
                )
                if reply != QMessageBox.StandardButton.Yes:
                    # abort procesing, when not confirmed
                    return
                shutil.rmtree(lights_dir)

        # create new lights dir and delete process dir, when there is one
        os.mkdir(lights_dir)
        if os.path.exists(process_dir):
            shutil.rmtree(process_dir)

        # collect all the files that will get copied
        all_files = []
        for session in self.selected_sessions:
            src = session.path
            files = os.listdir(src)
            for f in files:
                if f.startswith(session.target) and f.endswith(".fits"):
                    all_files.append(os.sep.join([src, f]))
        # prepare progress bar
        self.progressbar.setMaximum(len(all_files))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(all_files)}")
        # prepare and start background thread to actually copy the files
        # This need to be done in a backgrond thread, otherwise the progressbar does not update
        self.copyThread = CopyThread(files=all_files, dest=lights_dir)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self.progress_done)
        self.copy_btn.setDisabled(True)
        self.copyThread.start()
        return

    def close_help(self):
        """action for close help button"""
        self.help_window.close()

    def show_help(self):
        """show help, which is provided in Markdown syntax in the beginning of the script"""
        self.help_window = QDialog(self)
        self.help_window.setModal(True)
        self.help_window.setWindowTitle("Dwarfium Archive Selector Help")
        self.help_window.setMinimumSize(750, 600)

        help_layout = QVBoxLayout()
        help_text = QTextEdit(readOnly=True)
        help_text.setMarkdown(HELP_MD)
        help_layout.addWidget(help_text)

        help_close = QPushButton("Close")
        help_close.setMinimumHeight(35)
        help_close.setMinimumWidth(80)
        help_close.setMaximumWidth(80)
        help_close.clicked.connect(self.close_help)
        help_layout.addWidget(help_close)
        self.help_window.setLayout(help_layout)
        self.help_window.exec()

    def load_dwarfium_json(self):
        """Load a siril_session.json or siril_megastack.json produced by Dwarfium Scope Archive."""
        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Dwarfium Session JSON",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not json_path:
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read JSON:\n{e}")
            return

        # ── Megastack JSON ─────────────────────────────────────────────────
        if data.get("type") == "megastack":
            self._last_json_path = json_path
            self._load_megastack_json(data)
            return

        # ── Single session JSON (original behaviour) ────────────────────────
        session  = data.get("session", {})
        lights   = data.get("lights", [])
        darks    = data.get("darks", {}).get("files", [])
        bias_dir = data.get("bias_dir")
        flat_dir = data.get("flat_dir")

        # Summary dialog
        dark_status = data.get("darks", {}).get("status", "none")
        temp_match  = data.get("darks", {}).get("temp_match", False)
        dark_info   = f"{len(darks)} dark(s) [{dark_status}{'  ✅ temp match' if temp_match else '  ⚠️ closest temp'}]"
        bias_info   = os.path.basename(data.get("bias_file") or bias_dir or "") or "❌ not found"
        flat_info   = os.path.basename(data.get("flat_file") or flat_dir or "") or "❌ not found"

        msg = (
            f"Session: {session.get('target', 'Unknown')}  —  {session.get('date', '')[:10]}\n"
            f"Dwarf: {session.get('dwarf', '')}  |  "
            f"exp={session.get('exp_s')}s  gain={session.get('gain')}  filter={session.get('ir_filter', '')}\n\n"
            f"Lights:  {len(lights)} file(s)\n"
            f"Darks:   {dark_info}\n"
            f"Bias:    {bias_info}\n"
            f"Flat:    {flat_info}\n\n"
            f"Siril home: {self.current_working_directory}\n\n"
            f"Files will be copied into:\n"
            f"  lights/  darks/  bias/  flat/"
        )

        reply = QMessageBox.question(
            self, "Load Dwarfium Session", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_copy_from_json(
            lights, darks, bias_dir, flat_dir,
            bias_file=data.get("bias_file"),
            flat_file=data.get("flat_file"),
        )

    def _start_copy_from_json(self, lights, darks, bias_dir, flat_dir, bias_file=None, flat_file=None):
        """Copy lights, darks, bias and flat into Siril working directories."""
        cwd = self.current_working_directory

        # Build (src, dest_dir) pairs
        pairs = []

        # Lights → lights/  (preserve panel subdirs for mosaics)
        lights_dir = os.path.join(cwd, "lights")
        if os.path.exists(lights_dir):
            file_cnt = sum(len(fs) for _, _, fs in os.walk(lights_dir))
            if file_cnt > 0:
                reply = self.ask(
                    "Delete existing lights?",
                    f"This will delete {file_cnt} file(s) in:\n{lights_dir}\nProceed?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                shutil.rmtree(lights_dir)
        os.makedirs(lights_dir, exist_ok=True)
        # Detect mosaic: files come from different parent directories
        parent_dirs = {os.path.basename(os.path.dirname(f)) for f in lights}
        is_mosaic = len(parent_dirs) > 1
        for f in lights:
            if is_mosaic:
                panel = os.path.basename(os.path.dirname(f))
                dest = os.path.join(lights_dir, panel)
            else:
                dest = lights_dir
            pairs.append((f, dest))
        # Darks → darks/
        darks_dir = os.path.join(cwd, "darks")
        if darks:
            if os.path.exists(darks_dir):
                shutil.rmtree(darks_dir)
            os.makedirs(darks_dir, exist_ok=True)
            for f in darks:
                pairs.append((f, darks_dir))

        # Bias → bias/
        # DwarfLab factory: single PNG file; user-captured: subfolder with FITS/PNG
        bias_dest = os.path.join(cwd, "bias")
        if bias_file and os.path.isfile(bias_file):
            if os.path.exists(bias_dest): shutil.rmtree(bias_dest)
            os.makedirs(bias_dest, exist_ok=True)
            pairs.append((bias_file, bias_dest))
        elif bias_dir and os.path.isdir(bias_dir):
            if os.path.exists(bias_dest): shutil.rmtree(bias_dest)
            os.makedirs(bias_dest, exist_ok=True)
            for f in os.listdir(bias_dir):
                if f.lower().endswith((".fits", ".fit", ".fts", ".png")):
                    pairs.append((os.path.join(bias_dir, f), bias_dest))

        # Flat → flat/
        flat_dest = os.path.join(cwd, "flat")
        if flat_file and os.path.isfile(flat_file):
            if os.path.exists(flat_dest): shutil.rmtree(flat_dest)
            os.makedirs(flat_dest, exist_ok=True)
            pairs.append((flat_file, flat_dest))
        elif flat_dir and os.path.isdir(flat_dir):
            if os.path.exists(flat_dest): shutil.rmtree(flat_dest)
            os.makedirs(flat_dest, exist_ok=True)
            for f in os.listdir(flat_dir):
                if f.lower().endswith((".fits", ".fit", ".fts", ".png")):
                    pairs.append((os.path.join(flat_dir, f), flat_dest))

        if not pairs:
            QMessageBox.information(self, "Nothing to copy", "No files to copy.")
            return

        # Delete process dir
        process_dir = os.path.join(cwd, "process")
        if os.path.exists(process_dir):
            shutil.rmtree(process_dir)

        self.progressbar.setMaximum(len(pairs))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(pairs)}")

        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.copyThread = CopyMultiThread(pairs=pairs)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self._copy_from_json_done)
        self.copyThread.start()

    def _save_step(self, step: str):
        """Update the 'step' field in the loaded siril_megastack.json on disk.

        Called automatically after each major processing stage completes
        successfully, so the user can reload the JSON later and resume from
        where they left off without redoing earlier steps.

        Args:
            step: one of "copied", "stacked", "combined"
        """
        if not self._last_json_path or not self._last_megastack_data:
            return
        try:
            self._last_megastack_data["step"] = step
            with open(self._last_json_path, "w", encoding="utf-8") as f:
                json.dump(self._last_megastack_data, f, indent=2, ensure_ascii=False)
            self.siril.log(f"[step] JSON updated: step={step}", LogColor.BLUE)
        except Exception as e:
            self.siril.log(f"[step] Could not update JSON step: {e}", LogColor.SALMON)

    def _load_megastack_json(self, data: dict):
        """Handle a siril_megastack.json — multi-session, multi-filter."""
        self._last_megastack_data = data
        obj      = data.get("object", "Unknown")
        filters  = data.get("filters", [])
        single   = data.get("single_filter", True)
        hint     = data.get("combination_hint") or ("single" if single else "manual")
        groups   = data.get("sessions_by_filter", {})
        cwd      = self.current_working_directory
        step     = data.get("step")  # None | "copied" | "stacked" | "combined"

        # Enable the mosaic builder button only if at least one RESTACKED_
        # session is present in the loaded data
        has_restacked = any(
            str(sess.get("session_name", "")).startswith("RESTACKED_")
            for sessions in groups.values()
            for sess in sessions
        )
        self.mosaic_btn.setDisabled(not has_restacked)

        # Adapt Copy/Build buttons based on how far processing has already gone
        # so the user can skip steps already done and resume from where they left off
        STEP_ORDER = [None, "copied", "stacked", "combined"]
        step_idx = STEP_ORDER.index(step) if step in STEP_ORDER else 0

        self.copy_btn.setDisabled(step_idx >= 1)           # already copied
        self.build_sessions_btn.setDisabled(step_idx >= 2) # already stacked
        # mosaic_btn state is managed separately (depends on RESTACKED presence)

        # Build summary
        step_label = f"  [step: {step}]" if step else "  [step: not started]"
        stack_mode = data.get("stack_mode", "raw")
        mode_label = (
            "  [mosaic panels: already-stacked FITS, no darks]"
            if stack_mode == "stacked_panels" else ""
        )
        lines = [f"Megastack — {obj}{step_label}{mode_label}", ""]
        total_lights = 0
        for flt, sessions in groups.items():
            n_lights = sum(len(s.get("lights", [])) for s in sessions)
            n_darks  = sum(s.get("darks", {}).get("count", 0) for s in sessions)
            total_lights += n_lights
            lines.append(f"  [{flt}]  {len(sessions)} session(s)  ·  {n_lights} lights  ·  {n_darks} darks")
        lines += [
            "",
            f"Mode: {'single filter — simple Megastack' if single else f'multi-filter → {hint}'}",
            "",
            f"Siril home: {cwd}",
        ]
        if step:
            lines += [
                "",
                f"⚡ Already processed up to: {step}",
                "Buttons for completed steps are disabled.",
            ]
        else:
            lines += [
                "",
                "Lights will be copied to  lights_<filter>/",
                "Darks  will be copied to  darks_<filter>/",
            ]

        reply = QMessageBox.question(
            self, "Load Dwarfium Megastack", "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if step in ("copied", "stacked"):
            # Files already copied — just regenerate the scripts so
            # build_sessions_from_scripts has the lines it needs to resume
            # from the right step without recopying anything.
            cwd = self.current_working_directory
            self._last_generated_scripts = self._generate_megastack_scripts(data, cwd)
            # Only enable Build Sessions if there are scripts left to run
            self.build_sessions_btn.setDisabled(step == "stacked" and not any(
                os.path.basename(p).startswith("02_combine_")
                for p, _ in self._last_generated_scripts
            ))
        elif step == "combined":
            # Everything done — nothing left to run
            self._last_generated_scripts = []
            self.build_sessions_btn.setDisabled(True)
        else:
            # step is None — normal flow: copy files then generate scripts
            self._start_copy_megastack_json(data)

    def _start_copy_megastack_json(self, data: dict):
        """Copy lights and darks for each filter group, then generate .ssf scripts."""
        cwd    = self.current_working_directory
        groups = data.get("sessions_by_filter", {})
        single = data.get("single_filter", True)
        hint   = data.get("combination_hint") or ("single" if single else "manual")
        obj    = data.get("object", "Unknown").replace(" ", "_")

        pairs = []

        for flt, sessions in groups.items():
            flt_safe   = flt.replace(" ", "_").replace("/", "_")
            lights_dir = os.path.join(cwd, f"lights_{flt_safe}")
            darks_dir  = os.path.join(cwd, f"darks_{flt_safe}")

            # Clear and recreate
            if os.path.exists(lights_dir):
                shutil.rmtree(lights_dir)
            os.makedirs(lights_dir, exist_ok=True)

            # Lights — prefix with session index to avoid name collisions
            # (Dwarf sessions all contain 0000.fits, 0001.fits, ... and mosaic
            #  panels reuse the same names too)
            for s_idx, sess in enumerate(sessions, 1):
                for f in sess.get("lights", []):
                    # For mosaic panels keep the panel name in the prefix
                    parent = os.path.basename(os.path.dirname(f))
                    sess_name = os.path.basename(sess.get("session_dir", "") or "")
                    if parent and sess_name and parent != sess_name:
                        new_name = f"s{s_idx:02d}_{parent}_{os.path.basename(f)}"
                    else:
                        new_name = f"s{s_idx:02d}_{os.path.basename(f)}"
                    pairs.append((f, os.path.join(lights_dir, new_name)))

            # Darks — deduplicate by source path (sessions often share the
            # same dark-library files); keep original names.
            # Also exclude RESTACKED_ sessions from dark aggregation — they
            # carry no lights and no relevant darks.
            all_darks, seen = [], set()
            for sess in sessions:
                if str(sess.get("session_name", "")).startswith("RESTACKED_"):
                    continue
                for f in sess.get("darks", {}).get("files", []):
                    if f not in seen:
                        seen.add(f)
                        all_darks.append(f)

            n_darks   = len(all_darks)
            has_darks = n_darks > 0

            # Warn if sessions in this group have different exposures —
            # a single master dark would not match all of them.
            # RESTACKED_ and other pre_stacked sessions are excluded:
            # they're already-stacked results (darks already applied, or
            # not needed for stack_mode="stacked_panels"), and contribute
            # no lights to calibrate against a master dark anyway.
            exposures = {
                s.get("exp_s")
                for s in sessions
                if s.get("exp_s") is not None
                and not s.get("pre_stacked")
                and not str(s.get("session_name", "")).startswith("RESTACKED_")
            }
            if len(exposures) > 1:
                self.siril.log(
                    f"[{flt}] WARNING: mixed exposures {sorted(exposures)}s — "
                    "darks may not match all sessions",
                    LogColor.SALMON,
                )

            if all_darks:
                if os.path.exists(darks_dir):
                    shutil.rmtree(darks_dir)
                os.makedirs(darks_dir, exist_ok=True)
                for f in all_darks:
                    pairs.append((f, darks_dir))

        if not pairs:
            QMessageBox.information(self, "Nothing to copy", "No files to copy.")
            return

        # Generate .ssf scripts
        self._last_generated_scripts = self._generate_megastack_scripts(data, cwd)

        # Copy files
        self.progressbar.setMaximum(len(pairs))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(pairs)}")
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.copyThread = CopyMultiThread(pairs=pairs)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self._copy_from_json_done)
        self.copyThread.start()

    def _generate_megastack_scripts(self, data: dict, cwd: str):
        """Generate one .ssf per filter group + one combination script if needed.

        Uses official Siril script syntax (validated against Siril 1.2+ docs):
          - convert <seqname> operates on current directory → cd into folder first
          - dual-band extraction: seqextract_HaOIII on calibrated CFA sequence (before debayer/stack)
          - rgbcomp uses positional args: rgbcomp red green blue -out=...
          - LRGB: rgbcomp -lum=image rgb_image -out=...
        """
        groups = data.get("sessions_by_filter", {})
        single = data.get("single_filter", True)
        hint   = data.get("combination_hint") or ("single" if single else "manual")
        obj    = data.get("object", "Unknown").replace(" ", "_")

        generated_scripts = []  # list of (ssf_path, lines) in execution order

        def _is_dualband(flt: str) -> bool:
            return "dual" in flt.lower()

        # ── Per-filter stack scripts ──────────────────────────────────────────
        for flt, sessions in groups.items():
            flt_safe   = flt.replace(" ", "_").replace("/", "_")
            n_sessions = len(sessions)
            dualband   = _is_dualband(flt)

            # Exclude RESTACKED_ sessions from dark/light accounting — they
            # contribute no lights to calibrate and no relevant darks.
            normal_sessions = [
                s for s in sessions
                if not str(s.get("session_name", "")).startswith("RESTACKED_")
            ]
            # Count unique dark files across normal sessions
            dark_files_seen = set()
            for s in normal_sessions:
                for f in s.get("darks", {}).get("files", []):
                    dark_files_seen.add(f)
            n_darks   = len(dark_files_seen)
            has_darks = n_darks > 0

            # True when every session contributing lights to this group is
            # already fully processed (calibrated + debayered + stacked) —
            # e.g. mosaic panels generated with stack_mode="stacked_panels",
            # or sessions from generate_siril_megastack_json_manual. These
            # must NOT be run through calibrate/debayer again.
            all_pre_stacked = bool(normal_sessions) and all(
                s.get("pre_stacked") for s in normal_sessions
            )
            mixed_pre_stacked = (
                not all_pre_stacked
                and any(s.get("pre_stacked") for s in normal_sessions)
            )
            if mixed_pre_stacked:
                self.siril.log(
                    f"[{flt}] WARNING: mixes already-stacked sessions/panels with "
                    "raw ones — falling back to the raw pipeline for the whole "
                    "group. Consider running pre-stacked and raw sessions as "
                    "separate Megastacks.",
                    LogColor.SALMON,
                )

            proc = os.path.join(cwd, f"process_{flt_safe}")

            # True when the pre-stacked lights in this group actually come
            # from mosaic panels (different pointings covering a wider
            # field) rather than repeat sessions of the same framing —
            # these need astrometric mosaic alignment, not a plain
            # integration stack, or the result would be cropped down to
            # the overlap between panels instead of the full mosaic.
            has_mosaic_panels = any(s.get("is_mosaic") for s in normal_sessions)

            if all_pre_stacked and dualband:
                self.siril.log(
                    f"[{flt}] WARNING: already-stacked panels/sessions in a "
                    "dual-band filter group aren't auto-split into Ha/OIII — "
                    "falling back to the standard pipeline. Verify the result "
                    "manually or split the Ha/OIII stacks before combining.",
                    LogColor.SALMON,
                )

            if all_pre_stacked and not dualband and has_mosaic_panels:
                # Already-stacked mosaic panels: astrometric plate solving
                # + max-framing registration, same approach as
                # build_mosaic_from_restacked, so the final canvas covers
                # the full mosaic footprint instead of just the overlap
                # between panels. Requires Siril 1.4.0+.
                stack_line = (
                    f"stack r_light rej 3 3 -norm=addscale -maximize "
                    f"-overlap_norm -output_norm -rgb_equal"
                )
                if self.feather_checkbox.isChecked():
                    stack_line += f" -feather={self.feather_spinbox.value()}"
                stack_line += f" -out=../stack_{flt_safe}"

                lines = [
                    f"# Dwarfium Megastack — {obj} — filter: {flt}",
                    f"# {n_sessions} session(s) — already-stacked mosaic panels: "
                    "astrometric mosaic alignment (plate solve + max framing), "
                    "no calibrate/debayer",
                    "requires 1.4.0",
                    "setext fit",
                    f'cd "{cwd}"',
                    "",
                    "# Convert already-stacked panel FITS (no debayer needed)",
                    f"cd lights_{flt_safe}",
                    f"convert light -out=../process_{flt_safe}",
                    "cd ..",
                    "",
                    f"cd process_{flt_safe}",
                    "# Plate-solve each panel (local Gaia DR3 catalogue) then",
                    "# register with max framing so the canvas grows to fit",
                    "# every panel instead of shrinking to their overlap",
                    "seqplatesolve light -catalog=localgaia",
                    "seqapplyreg light -framing=max",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    "",
                    stack_line,
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    "cd ..",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
                ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
                with open(ssf_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
                generated_scripts.append((ssf_path, lines))
                continue

            if all_pre_stacked and not dualband and not has_mosaic_panels:
                # Already-stacked sessions of the same framing (not a
                # mosaic) — e.g. several nights each already stacked with
                # stack_mode="stacked_panels". A plain integration stack is
                # enough: just convert (no -debayer), register, and stack.
                lines = [
                    f"# Dwarfium Megastack — {obj} — filter: {flt}",
                    f"# {n_sessions} session(s) — already-stacked sessions: "
                    "convert + register + stack only (no calibrate/debayer)",
                    "requires 1.2.0",
                    "setext fit",
                    f'cd "{cwd}"',
                    "",
                    "# Convert already-stacked light frames (no debayer needed)",
                    f"cd lights_{flt_safe}",
                    f"convert light -out=../process_{flt_safe}",
                    "cd ..",
                    "",
                    f"cd process_{flt_safe}",
                    "register light",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    "",
                    f"stack r_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    "cd ..",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
                ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
                with open(ssf_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
                generated_scripts.append((ssf_path, lines))
                continue

            lines = [
                f"# Dwarfium Megastack — {obj} — filter: {flt}",
                f"# {n_sessions} session(s) — generated by Dwarfium Scope Archive",
                "requires 1.2.0",
                "setext fit",
                f'cd "{cwd}"',
                "",
                "# Convert light frames",
                f"cd lights_{flt_safe}",
                f"convert light -out=../process_{flt_safe}",
                f"cd ..",
                "",
            ]
            if has_darks:
                if n_darks >= 2:
                    lines += [
                        "# Convert and stack darks into master dark",
                        f"cd darks_{flt_safe}",
                        f"convert dark -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                    ]
                else:
                    # Single dark file — it's already a pre-stacked master
                    # (e.g. dark_exp_45..._stack_8.fits from DwarfLab).
                    # Convert it to a .fit so calibrate can reference it by
                    # the fixed name master_dark.
                    lines += [
                        "# Single pre-stacked dark — convert and save as master dark",
                        f"cd darks_{flt_safe}",
                        f"convert dark -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                    ]
            lines += [
                f"cd process_{flt_safe}",
                "",
            ]
            if has_darks:
                if n_darks >= 2:
                    lines += [
                        "# Stack darks into master dark",
                        "stack dark rej 3 3 -nonorm -out=master_dark",
                        "",
                    ]
                else:
                    # Single dark already converted — load and save as master_dark
                    lines += [
                        "# Rename single dark to master_dark",
                        "load dark_00001",
                        "save master_dark",
                        "",
                    ]

            if dualband:
                # Dual-Band: calibrate WITHOUT debayer, extract Ha/OIII per frame, stack each
                seq = "pp_light" if has_darks else "light"
                proc = os.path.join(cwd, f"process_{flt_safe}")
                lines += [
                    "# Calibrate (keep CFA — no debayer before Ha/OIII extraction)",
                    "calibrate light -dark=master_dark -cc=dark -cfa" if has_darks
                        else "# (no darks — skipping calibration)",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'dark_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'master_dark.fit')}",
                    "",
                    "# Extract Ha and OIII from each calibrated frame",
                    f"seqextract_HaOIII {seq}",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'pp_light_*.fit')}",
                    "",
                    "# Register and stack the Ha sequence",
                    f"register Ha_{seq}",
                    f"stack r_Ha_{seq} rej 3 3 -norm=addscale -out=../stack_{flt_safe}_Ha",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'Ha_{seq}_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'r_Ha_{seq}_*.fit')}",
                    "",
                    "# Register and stack the OIII sequence",
                    f"register OIII_{seq}",
                    f"stack r_OIII_{seq} rej 3 3 -norm=addscale -out=../stack_{flt_safe}_OIII",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'OIII_{seq}_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'r_OIII_{seq}_*.fit')}",
                    "cd ..",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
            else:
                # Broadband
                proc = os.path.join(cwd, f"process_{flt_safe}")
                if has_darks:
                    lines += [
                        "# Calibrate with master dark and debayer",
                        "calibrate light -dark=master_dark -cc=dark -cfa -equalize_cfa -debayer",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'dark_*.fit')}",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'master_dark.fit')}",
                        "",
                        "register pp_light",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'pp_light_*.fit')}",
                        "",
                        f"stack r_pp_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'r_pp_light_*.fit')}",
                    ]
                else:
                    # No darks: calibrate requires a master frame, so debayer
                    # must happen at conversion time instead. Rebuild sequence.
                    lines = [
                        f"# Dwarfium Megastack — {obj} — filter: {flt}",
                        f"# {n_sessions} session(s) — no darks: debayer at convert",
                        "requires 1.2.0",
                        "setext fit",
                        f'cd "{cwd}"',
                        "",
                        f"cd lights_{flt_safe}",
                        f"convert light -debayer -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                        f"cd process_{flt_safe}",
                        "register light",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                        "",
                        f"stack r_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    ]
                lines.append("cd ..")
                lines += [
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]

            ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
            with open(ssf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
            generated_scripts.append((ssf_path, lines))

        # ── Combination script ────────────────────────────────────────────────
        if not single and hint not in ("single", "manual"):
            filter_keys = list(groups.keys())
            lines = [
                f"# Dwarfium Megastack — {obj} — combination: {hint}",
                "# Run AFTER all 01_stack_*.ssf scripts",
                "requires 1.2.0",
                f'cd "{cwd}"',
                "",
            ]

            if hint == "HaRGB":
                dual  = next((k for k in filter_keys if _is_dualband(k)), filter_keys[0])
                astro = next((k for k in filter_keys if k != dual), filter_keys[-1])
                d_safe = dual.replace(" ", "_").replace("/", "_")
                a_safe = astro.replace(" ", "_").replace("/", "_")
                # Detect whether the Duo-Band stack script used seqextract_HaOIII
                # (producing stack_Duo-Band_Ha + _OIII mono files) or a normal
                # debayer pipeline (producing a single stack_Duo-Band.fit RGB).
                # Check the already-generated 01_stack script lines for this filter.
                dual_was_extracted = any(
                    "seqextract_HaOIII" in "\n".join(l)
                    for p, l in generated_scripts
                    if d_safe in os.path.basename(p)
                )
                # Retrieve the Ha blend ratio from the UI widget
                ha_ratio  = round(self.ha_blend_spinbox.value(), 2)
                rgb_ratio = round(1.0 - ha_ratio, 2)
                single_dwarf = data.get("single_dwarf", True)

                # ── Decide alignment strategy ─────────────────────────────
                # Use per-session RA/DEC if available to detect significant
                # field offsets (different pointings), which need astrometric
                # alignment regardless of whether it's the same Dwarf.
                # Fallback: use single_dwarf flag only.
                def _mean_radec(sessions):
                    ras  = [s["ra"]  for s in sessions if s.get("ra")  is not None]
                    decs = [s["dec"] for s in sessions if s.get("dec") is not None]
                    return (sum(ras)/len(ras)  if ras  else None,
                            sum(decs)/len(decs) if decs else None)

                ra_a, dec_a = _mean_radec(groups.get(astro, []))
                ra_d, dec_d = _mean_radec(groups.get(dual,  []))
                if ra_a is not None and ra_d is not None:
                    delta_ra  = abs(ra_a  - ra_d)
                    delta_dec = abs(dec_a - dec_d)
                    # > 0.5° offset → fields differ enough to need plate solving
                    needs_platesolve = delta_ra > 0.5 or delta_dec > 0.5
                else:
                    # No per-session coords — fall back to Dwarf comparison
                    needs_platesolve = not single_dwarf

                # ── Alignment step ────────────────────────────────────────
                # The two stacks must be aligned before combining.
                # - same Dwarf (single_dwarf) → star-based registration, fast
                # - different Dwarf(s)        → astrometric plate solving,
                #   handles different pixel scales / fields of view
                ha_stack  = f"stack_{d_safe}_Ha" if dual_was_extracted else f"stack_{d_safe}"
                lines += [
                    f"# ── Align {a_safe} and {d_safe} stacks before combining ──",
                ]
                # Create the alignment sub-folder now (at script generation time,
                # in Python) so it exists before any Siril command runs.
                align_tmp = os.path.join(cwd, "align_tmp")
                os.makedirs(align_tmp, exist_ok=True)

                if not needs_platesolve:
                    lines += [
                        f"# Same Dwarf / close field — star-based registration (fast, no catalogue needed)",
                        f"# Work in a dedicated sub-folder so link/convert only sees these two stacks",
                        f'cd "{cwd}"',
                        f"load stack_{a_safe}",
                        f'save "align_tmp/img_1"',
                        f"load {ha_stack}",
                        f'save "align_tmp/img_2"',
                        f"cd align_tmp",
                        f"link align_",
                        f"register align_",
                        f"seqapplyreg align_",
                        f"",
                        f"# r_align_00001 = {a_safe}, r_align_00002 = {d_safe}",
                        f"# Split aligned Astro into R/G/B",
                        f"load r_align_00001",
                        f"split astro_r astro_g astro_b",
                        f"",
                    ]
                    if dual_was_extracted:
                        lines += [
                            f"# Aligned Duo-Band Ha mono — save back to CWD",
                            f"load r_align_00002",
                            f'save "aligned_ha"',
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/aligned_ha"
                    else:
                        lines += [
                            f"# Split aligned Duo-Band RGB to extract Ha (R channel)",
                            f"load r_align_00002",
                            f"split duoband_ha duoband_g duoband_b",
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/duoband_ha"
                else:
                    lines += [
                        f"# Different Dwarf / field offset > 0.5° — astrometric registration (requires Gaia local)",
                        f"requires 1.4.0",
                        f'cd "{cwd}"',
                        f"load stack_{a_safe}",
                        f'save "align_tmp/img_1"',
                        f"load {ha_stack}",
                        f'save "align_tmp/img_2"',
                        f"cd align_tmp",
                        f"link align_",
                        f"seqplatesolve align_ -catalog=localgaia",
                        f"seqapplyreg align_ -framing=max",
                        f"",
                        f"# r_align_00001 = {a_safe}, r_align_00002 = {d_safe}",
                        f"load r_align_00001",
                        f"split astro_r astro_g astro_b",
                        f"",
                    ]
                    if dual_was_extracted:
                        lines += [
                            f"load r_align_00002",
                            f'save "aligned_ha"',
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/aligned_ha"
                    else:
                        lines += [
                            f"load r_align_00002",
                            f"split duoband_ha duoband_g duoband_b",
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/duoband_ha"

                f_astro_r = "align_tmp/astro_r"
                lines += [
                    f"# Blend Ha with Astro R: R = Ha×{ha_ratio} + Astro_R×{rgb_ratio}",
                    f"# This preserves natural star colors while boosting nebula signal",
                    f'pm "${ha_src}$ * {ha_ratio} + ${f_astro_r}$ * {rgb_ratio}" -rescale',
                    f"save ha_blended",
                    "",
                    f"rgbcomp ha_blended ./align_tmp/astro_g ./align_tmp/astro_b",
                    f"# rgbcomp always outputs 'composed_rgb' — rename it",
                    f"load composed_rgb",
                    f"save final_{obj}_HaRGB",
                    "",
                    f"# Cleanup intermediate files — keep only stack_*.fit and final_*.fit",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'align_tmp')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'ha_blended.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_r.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_g.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_b.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_ha.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_g.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_b.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'aligned_ha.fit')}",
                    "",
                    f"load final_{obj}_HaRGB",
                    "autostretch",
                    f"savejpg final_{obj}_HaRGB 95",
                ]

            elif hint == "HOO_stars":
                dual = next((k for k in filter_keys if _is_dualband(k)), filter_keys[0])
                uvir = next((k for k in filter_keys if k != dual), filter_keys[-1])
                d_safe = dual.replace(" ", "_").replace("/", "_")
                u_safe = uvir.replace(" ", "_").replace("/", "_")
                lines += [
                    f"# HOO: R = Ha, G = OIII, B = OIII (both mono, from 01_stack_{d_safe}.ssf)",
                    f"rgbcomp stack_{d_safe}_Ha stack_{d_safe}_OIII stack_{d_safe}_OIII",
                    f"load composed_rgb",
                    f"save final_{obj}_HOO",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    "",
                    f"load final_{obj}_HOO",
                    "autostretch",
                    f"savejpg final_{obj}_HOO 95",
                    "",
                    f"# Optional star blend: stack_{u_safe} (UV/IR Cut) has natural star colors.",
                    f"# In Siril GUI use PixelMath, e.g.:  $final_{obj}_HOO$ * 0.85 + $stack_{u_safe}$ * 0.15",
                    f"# Or use StarNet to extract stars from stack_{u_safe} and screen-blend them.",
                ]

            elif hint == "RGB_combine":
                # Astro LP (color) + UV/IR Cut (color) → use UV/IR luminance via its green channel
                astro = next((k for k in filter_keys if "astro" in k.lower()), filter_keys[0])
                uvir  = next((k for k in filter_keys if k != astro), filter_keys[-1])
                a_safe = astro.replace(" ", "_").replace("/", "_")
                u_safe = uvir.replace(" ", "_").replace("/", "_")
                lines += [
                    f"# Extract a luminance from the UV/IR Cut stack (green channel ≈ luminance)",
                    f"load stack_{u_safe}",
                    f"split uvir_r uvir_g uvir_b",
                    "",
                    f"# LRGB: luminance from UV/IR Cut applied to the Astro color stack",
                    f"rgbcomp -lum=uvir_g stack_{a_safe}",
                    f"load composed_rgb",
                    f"save final_{obj}_LRGB",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'uvir_g.fit')}",
                    "",
                    f"load final_{obj}_LRGB",
                    "autostretch",
                    f"savejpg final_{obj}_LRGB 95",
                ]

            ssf_path = os.path.join(cwd, f"02_combine_{hint}.ssf")
            with open(ssf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.siril.log(f"Combination script saved: {ssf_path}", LogColor.GREEN)
            generated_scripts.append((ssf_path, lines))

        elif hint == "manual":
            self.siril.log(
                "Manual combination — run the stack scripts then combine the stacked files in Siril GUI.",
                LogColor.SALMON,
            )

        return generated_scripts

    def build_sessions_from_scripts(self):
        """Run the generated 01_stack_*.ssf (and 02_combine_*.ssf, if any)
        scripts directly in this Siril session, reusing the exact same lines
        that were written to disk by _generate_megastack_scripts — so this
        always stays in sync with whatever script logic produces.
        """
        scripts = self._last_generated_scripts
        if not scripts:
            QMessageBox.warning(
                self, "No scripts available",
                "Load a Dwarfium JSON and copy files first to generate the scripts."
            )
            return

        # Filter out already-completed scripts based on current step
        current_step = (self._last_megastack_data or {}).get("step")
        if current_step == "stacked":
            # Stacks done — only run the combination script if present
            scripts_to_run = [(p, l) for p, l in scripts
                              if os.path.basename(p).startswith("02_combine_")]
            if not scripts_to_run:
                QMessageBox.information(self, "Nothing to do",
                    "Stacks already done and no combination script to run.")
                return
        else:
            scripts_to_run = scripts

        reply = QMessageBox.question(
            self, "Build Sessions",
            f"This will run {len(scripts_to_run)} script(s) directly in this Siril session:\n\n"
            + "\n".join(os.path.basename(p) for p, _ in scripts_to_run)
            + "\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.build_sessions_btn.setDisabled(True)
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.mosaic_btn.setDisabled(True)

        ran_ok = True
        for ssf_path, lines in scripts_to_run:
            ssf_name = os.path.basename(ssf_path)
            self.siril.log(f"[build] Running {ssf_name}…", LogColor.BLUE)
            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                # Python-side cleanup: # PYTHON_CLEANUP <path_or_glob>
                # Executed by Python (not sent to Siril) to free disk space
                # as processing progresses. Supports glob patterns (*) and
                # plain paths (files or directories).
                if line.startswith("# PYTHON_CLEANUP"):
                    cleanup_arg = line[len("# PYTHON_CLEANUP"):].strip()
                    if cleanup_arg:
                        import glob as _glob
                        targets = _glob.glob(cleanup_arg)
                        if not targets:
                            targets = [cleanup_arg]  # try as literal path
                        for target in targets:
                            try:
                                if os.path.isdir(target):
                                    shutil.rmtree(target)
                                    self.siril.log(f"[cleanup] Removed dir: {target}", LogColor.BLUE)
                                elif os.path.isfile(target):
                                    os.remove(target)
                                    self.siril.log(f"[cleanup] Removed: {target}", LogColor.BLUE)
                            except Exception as e:
                                self.siril.log(f"[cleanup] Could not remove {target}: {e}", LogColor.SALMON)
                    continue
                if line.startswith("#"):
                    continue
                try:
                    args = shlex.split(line)
                except ValueError as e:
                    self.siril.log(f"[build] Could not parse line '{line}': {e}", LogColor.RED)
                    ran_ok = False
                    break
                if not args:
                    continue
                # Siril's command parser re-tokenizes the reconstructed
                # command line and splits on whitespace, so any argument
                # containing a space (e.g. a path under "Test Siril") must
                # be re-quoted here, same as it was originally in the .ssf
                # text — shlex.split() above already stripped those quotes.
                quoted_args = [f'"{a}"' if " " in a else a for a in args]
                try:
                    self.siril.cmd(*quoted_args)
                except s.CommandError as e:
                    self.siril.log(f"[build] Command '{line}' failed: {e}", LogColor.RED)
                    ran_ok = False
                    break
            if not ran_ok:
                break
            # Update step after each script completes successfully
            if ssf_name.startswith("01_stack_"):
                self._save_step("stacked")
            elif ssf_name.startswith("02_combine_"):
                self._save_step("combined")

        self.build_sessions_btn.setDisabled(False)
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.mosaic_btn.setDisabled(not bool(self._last_megastack_data))

        if ran_ok:
            self.siril.log("[build] All scripts completed successfully.", LogColor.GREEN)
            QMessageBox.information(self, "Build complete", "All scripts ran successfully.")
        else:
            QMessageBox.critical(
                self, "Build failed",
                "A command failed while running the scripts.\nCheck the Siril log for details."
            )

    def _copy_from_json_done(self, count):
        """Called when JSON-based copy is complete."""
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.build_sessions_btn.setDisabled(not self._last_generated_scripts)
        self.progressbar.setValue(0)
        self._save_step("copied")
        self.progressbar.setMaximum(1)
        self.progress_label.setText("completed")
        self.siril.log(f"Dwarfium JSON copy complete: {count} file(s) copied.", LogColor.GREEN)
        QMessageBox.information(
            self,
            "Copy complete",
            f"{count} file(s) copied to Siril working directory.\n"
            f"You can now close this window and run your Siril script.",
        )

    def build_mosaic_from_restacked(self):
        """Collect RESTACKED_ tiles from the last loaded siril_megastack.json,
        extract their stacked-16 FITS (direct file, or from a stacked-16*.zip
        for _MOSAIC_ sessions), then stitch them with Siril's astrometric
        mosaic alignment (seqplatesolve + seqapplyreg -framing=max + stack
        -maximize -overlap_norm).
        """
        data = self._last_megastack_data
        if not data:
            QMessageBox.warning(self, "No Megastack loaded", "Load a siril_megastack.json first.")
            return

        groups = data.get("sessions_by_filter", {})
        restacked_sessions = [
            sess
            for sessions in groups.values()
            for sess in sessions
            if str(sess.get("session_name", "")).startswith("RESTACKED_")
        ]
        if len(restacked_sessions) < 2:
            QMessageBox.warning(
                self, "Not enough tiles",
                "At least 2 RESTACKED_ sessions are needed to build a mosaic."
            )
            return

        obj = data.get("object", "Unknown").replace(" ", "_")
        self.current_working_directory = self.siril.get_siril_wd()
        self._mosaic_tiles_dir = os.path.join(self.current_working_directory, f"mosaic_tiles_{obj}")
        self._mosaic_object = obj

        # Detect any stack_*.fit(s) produced by a previous Build Sessions run
        # in the current working directory — offer to include them as extra tiles
        existing_stacks = sorted(
            os.path.join(self.current_working_directory, f)
            for f in os.listdir(self.current_working_directory)
            if f.lower().startswith("stack_") and f.lower().endswith((".fit", ".fits"))
        )
        include_stacks = []
        if existing_stacks:
            stack_names = "\n".join(f"  • {os.path.basename(f)}" for f in existing_stacks)
            reply_stacks = QMessageBox.question(
                self, "Include Build Sessions stacks?",
                f"Found {len(existing_stacks)} stack(s) from a previous Build Sessions run:\n\n"
                f"{stack_names}\n\n"
                "Include them as extra tiles in the mosaic?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply_stacks == QMessageBox.StandardButton.Yes:
                include_stacks = existing_stacks

        total_tiles = len(restacked_sessions) + len(include_stacks)
        extra_info = (
            f" + {len(include_stacks)} Build Sessions stack(s)" if include_stacks else ""
        )
        reply = QMessageBox.question(
            self, "Build Mosaic",
            f"Found {len(restacked_sessions)} RESTACKED_ session(s){extra_info} for {obj}.\n"
            f"Total tiles: {total_tiles}\n\n"
            f"Tiles will be extracted to:\n{self._mosaic_tiles_dir}\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._mosaic_include_stacks = include_stacks

        self.mosaic_btn.setDisabled(True)
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.progressbar.setMaximum(0)  # indeterminate while extracting
        self.progress_label.setText("extracting…")

        self.mosaicExtractThread = MosaicTileExtractThread(restacked_sessions, self._mosaic_tiles_dir)
        self.mosaicExtractThread.progress.connect(self._mosaic_extract_progress)
        self.mosaicExtractThread.done.connect(self._mosaic_extract_done)
        self.mosaicExtractThread.start()

    def _mosaic_extract_progress(self, value):
        """Progress callback for tile extraction (indeterminate progress bar)."""
        self.progress_label.setText(f"extracting… {value} tile(s)")

    def _mosaic_extract_done(self, tile_count, errors):
        """Called when tile extraction finishes — runs the Siril astrometric
        mosaic pipeline on the extracted tiles."""
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.progressbar.setMaximum(1)
        self.progressbar.setValue(0)

        if errors:
            for msg in errors:
                self.siril.log(f"[mosaic] {msg}", LogColor.SALMON)

        if tile_count < 2:
            self.progress_label.setText("failed")
            self.mosaic_btn.setDisabled(False)
            QMessageBox.warning(
                self, "Mosaic build failed",
                f"Only {tile_count} usable tile(s) extracted — need at least 2.\n"
                "Check the Siril log for details."
            )
            return

        self.siril.log(f"[mosaic] {tile_count} tile(s) extracted to {self._mosaic_tiles_dir}", LogColor.GREEN)

        # Copy any Build Sessions stacks the user chose to include as extra tiles
        extra_stacks = getattr(self, "_mosaic_include_stacks", [])
        for stack_path in extra_stacks:
            ext = os.path.splitext(stack_path)[1]
            dest_name = f"tile_stack_{os.path.basename(stack_path)}"
            dest_path = os.path.join(self._mosaic_tiles_dir, dest_name)
            try:
                shutil.copy2(win_long_path(stack_path), win_long_path(dest_path))
                tile_count += 1
                self.siril.log(f"[mosaic] Added stack tile: {dest_name}", LogColor.GREEN)
            except Exception as e:
                self.siril.log(f"[mosaic] Could not copy {stack_path}: {e}", LogColor.SALMON)

        self.progress_label.setText("registering…")

        seq_basename = f"mosaic_{self._mosaic_object}_"
        try:
            # Siril's command parser re-tokenizes the reconstructed command
            # line and splits on whitespace, so paths containing spaces (like
            # this one, under "Test Siril") must be quoted, same as in a .ssf
            # script file.
            self.siril.cmd("cd", f'"{self._mosaic_tiles_dir}"')
            actual_wd = self.siril.get_siril_wd()
            self.siril.log(f"[mosaic] CWD after cd: {actual_wd}", LogColor.BLUE)
            # Astrometric mosaic alignment (seqplatesolve + seqapplyreg
            # -framing=max + stack -maximize) requires Siril 1.4.0+
            self.siril.cmd("requires", "1.4.0")
            self.siril.cmd("link", seq_basename)
            # Use the local Gaia DR3 catalogue explicitly: with a local
            # catalogue, Siril re-reads each image's own header coordinates
            # individually (rather than fetching one shared online catalogue
            # for the whole sequence), and also enables the automatic
            # "near solve" search cone if the initial solve fails — both of
            # which matter here since tiles come from different Dwarf
            # devices/sensors with different framing and pixel scale.
            self.siril.cmd("seqplatesolve", seq_basename, "-catalog=localgaia")
            self.siril.cmd("seqapplyreg", seq_basename, "-framing=max")
            stack_args = [
                "stack", f"r_{seq_basename}", "rej", "3", "3",
                "-norm=addscale", "-maximize", "-overlap_norm",
                "-output_norm", "-rgb_equal",
            ]
            if self.feather_checkbox.isChecked():
                stack_args.append(f"-feather={self.feather_spinbox.value()}")
            stack_args.append(f"-out={self._mosaic_object}_mosaic")
            self.siril.cmd(*stack_args)
        except s.CommandError as e:
            self.progress_label.setText("failed")
            self.mosaic_btn.setDisabled(False)
            self.siril.log(f"[mosaic] Siril command failed: {e}", LogColor.RED)
            if "null matrices" in str(e).lower():
                hint = (
                    "This usually means most tiles failed plate solving.\n\n"
                    "Make sure a local star catalogue (Gaia DR3 or KStars NOMAD) is "
                    "installed in Siril's preferences — without one, only a single "
                    "online star catalogue is fetched for the whole sequence, which "
                    "often fails for tiles from different Dwarf devices/sensors.\n\n"
                )
            else:
                hint = ""
            QMessageBox.critical(
                self, "Mosaic build failed",
                f"A Siril command failed while building the mosaic:\n{e}\n\n"
                f"{hint}Check the Siril log for details."
            )
            return
        finally:
            try:
                self.siril.cmd("cd", f'"{self.current_working_directory}"')
            except Exception:
                pass

        self.progress_label.setText("completed")
        self.mosaic_btn.setDisabled(False)
        result_path = os.path.join(self._mosaic_tiles_dir, f"{self._mosaic_object}_mosaic.fit")
        self.siril.log(f"[mosaic] Mosaic complete: {result_path}", LogColor.GREEN)
        QMessageBox.information(
            self, "Mosaic complete",
            f"Mosaic built from {tile_count} tile(s).\n\nResult saved as:\n{result_path}"
        )

    def close_dialog(self):
        try:
            self.siril.disconnect()
        except Exception:
            pass  # Ignore disconnect errors
        self.close()

    def print_footer(self):
        self.siril.log(
            f"Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            LogColor.GREEN,
        )

    def save_presets(self):
        """Save current settings and session data to preset file"""
        # Collect settings
        presets = {
            "archive_dir": self.archive_dir,
        }

        # Create presets directory if it doesn't exist
        presets_file = os.path.join(self.siril.get_siril_configdir(), PRESET_FILE)

        try:
            with open(presets_file, "w") as f:
                json.dump(presets, f, indent=4)
            self.siril.log(f"Saved preset to {presets_file}", LogColor.GREEN)
        except Exception as e:
            self.siril.log(
                f"Failed to save presets to {presets_file}: {e}", LogColor.RED
            )

    def load_presets(self):
        """Load settings and session data from preset file"""
        presets_file = os.path.join(self.siril.get_siril_configdir(), PRESET_FILE)
        try:
            presets = None
            if os.path.exists(presets_file):
                self.siril.log(
                    f"Loading preset from {presets_file}",
                    LogColor.GREEN,
                )
                with open(presets_file) as f:
                    presets = json.load(f)
            else:
                # If default presets don't exist, use defaults
                presets = json.loads(PRESET_JSON)
                self.siril.log(
                    "No presets file found.",
                    LogColor.GREEN,
                )

            self.archive_dir = presets.get("archive_dir", None)

        except Exception as e:
            self.siril.log(
                f"Error loading presets from {presets_file}: {str(e)}", LogColor.RED
            )

    def session_selected(self):
        """collect the selected sessions"""
        selection = self.session_listbox.selectedItems()
        lights_count = 0
        self.selected_sessions = []
        if self.selected_target is None:
            return
        for item in selection:
            i = self.session_list.index(item.text())
            if self.selected_target.sessions is None:
                continue
            self.selected_sessions.append(self.selected_target.sessions[i])
            lights_count += self.selected_target.sessions[i].stacked
        self.progress_label.setText(f"0 / {lights_count}")
        if lights_count > 0:
            self.copy_btn.setDisabled(False)
        else:
            self.copy_btn.setDisabled(True)

    def target_selected(self):
        """chose the selected target and update the session list"""
        selection = self.target_listbox.selectedItems()
        self.session_listbox.clear()
        self.session_list = []
        self.selected_target = None
        self.info_box.clear()
        self.thumb.clear()
        if len(selection) == 1:
            i = self.target_list.index(selection[0].text())
            self.selected_target = self.targets[i]
            for s in self.selected_target.sessions:
                self.session_list.append(
                    f"{s.calendardate}: {s.stacked} x {s.exposure}s / {s.gain}g, {s.ir}"
                )
            self.session_listbox.addItems(self.session_list)
            first = self.selected_target.sessions[0]
            self.info_box.setText(f"RA: {first.ra:.2f}\nDEC:{first.dec:.2f}\n")
            thumb = QPixmap(first.thumbnail).scaledToHeight(self.thumb.height())
            self.thumb.setPixmap(thumb)

    def parse_foldername(self, path):
        """Helper function parsing folder names according to usualy Dwarf Lab naming scheme"""
        foldername = os.path.basename(path)
        parts = foldername.split("_")
        if "RESTACKED" in parts:
            # RESTACK sessions have a different format
            self.siril.log(
                f"skip MegaStack of {parts[3]} - {parts[4]} - {parts[5]}",
                LogColor.BLUE,
            )
        else:
            if len(parts) != 9:
                self.siril.log(
                    f"Path name '{os.path.basename(path)}' does not match the expected pattern",
                    LogColor.BLUE,
                )
            else:
                session = Session(
                    path, parts[2], parts[3], parts[5], parts[7], parts[8]
                )
                # add more info from shotsinfo.json if avaliable
                if os.path.isfile(os.path.join(path, "shotsinfo.json")):
                    with open(path + os.sep + "shotsinfo.json") as fp:
                        info = json.load(fp)
                        session.ir = info["ir"]
                        session.taken = info["shotsTaken"]
                        session.stacked = info["shotsStacked"]
                        session.ra = info["RA"]
                        session.dec = info["DEC"]
                        session.min_temp = info["minTemp"]
                        session.max_temp = info["maxTemp"]
                if not os.path.isfile(session.thumbnail):
                    session.thumbnail = ""
                return session
        return None

    def parse_filetree(self, path):
        """walk the archive path and collect dir names matching dwarf naming schema"""
        if path is None:
            return []
        path = os.path.abspath(path)
        self.siril.log(
            f"Parsing '{path}'",
            LogColor.BLUE,
        )
        skip_folders = ["Thumbnail", "", "Solving_Failed", "CALI_FRAME", "DWARF_DARK"]
        session_folders = []
        sessions = []

        for root, folders, _ in os.walk(path):
            for folder in list(folders):
                if folder in skip_folders:
                    folders.remove(folder)
                    continue
                if len(folder) == 0:
                    folders.remove(folder)
                    continue
                if "DWARF_RAW_" in folder and "_MOSAIC_" not in folder:
                    session_folders.append(os.path.join(root, folder))

        for f in session_folders:
            session = self.parse_foldername(f)
            if session is not None:
                sessions.append(session)
        return sessions

    def get_targets(self, sessions):
        """inspect the collected sessions and retrieve a list of targets"""
        targets = []

        sessions_by_target = sorted(sessions, key=lambda s: (s.target, s.cam, s.date))
        last = ""
        target = None
        for session in sessions_by_target:
            if session is None:
                continue
            if session.target != last:
                last = session.target
                target = Target(session.target)
                targets.append(target)
            if target is not None:
                target.add_session(session)

        return targets

    def refresh_target_list(self):
        """action for refresh button, rescan the archive"""
        self.target_listbox.clear()  # clear QListWidget instead of delete()
        self.target_list = []
        self.siril.log(f"Showing {self.archive_dir}", LogColor.BLUE)

        for t in self.targets:
            self.target_list.append(
                f"{t.target} ({len(t.sessions)}x {t.sessions[0].cam.capitalize()})"
            )
        self.target_listbox.addItems(self.target_list)


def main():
    try:
        app = QApplication(sys.argv)
        window = PreprocessingInterface()
        # Only show window if initialization was successful
        if window.initialization_successful:
            window.show()
            sys.exit(app.exec())
        else:
            # User canceled during initialization - exit gracefully
            sys.exit(0)
    except Exception as e:
        print(f"Error initializing application: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()