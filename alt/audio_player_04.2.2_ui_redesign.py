import os
import sys
import datetime
import logging
import vlc

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QSlider, QFileDialog, QMessageBox, QProgressDialog, QDialog,
    QTextEdit, QSizePolicy, QFrame, QInputDialog
)

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AudioSetlist")

# ---------------------------------------------------------------------
# Track model
# ---------------------------------------------------------------------
class Track:
    def __init__(self, path: str, duration: int):
        self.path = path
        self.duration = duration  # seconds
        self.name = os.path.basename(path)

    def __repr__(self):
        return f"Track(name={self.name!r}, duration={self.duration}, path={self.path!r})"

# ---------------------------------------------------------------------
# Folder scanner thread
# ---------------------------------------------------------------------
class FolderScanner(QThread):
    progress = pyqtSignal(int, int)          # current, total
    finished = pyqtSignal(list, int)         # playlist (list[Track]), total_seconds
    error = pyqtSignal(str)

    def __init__(self, folder: str, instance: vlc.Instance):
        super().__init__()
        self.folder = folder
        self.instance = instance
        self._running = True

    def run(self):
        playlist: list[Track] = []
        total_seconds = 0
        try:
            for root, _, files in os.walk(self.folder):
                audio_files = [f for f in files if f.lower().endswith(('.mp3', '.m4a', '.wav'))]
                total = len(audio_files)
                for i, file in enumerate(audio_files):
                    if not self._running:
                        return
                    path = os.path.join(root, file)
                    try:
                        media = self.instance.media_new(path)
                        media.parse()  # can later be replaced with async parsing
                        duration_ms = media.get_duration()
                        duration = max(0, duration_ms // 1000)
                        track = Track(path, duration)
                        playlist.append(track)
                        total_seconds += duration
                        self.progress.emit(i + 1, total)
                    except Exception as e:
                        logger.error(f"Failed to parse {path}: {e}")
            self.finished.emit(playlist, total_seconds)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._running = False

# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------
class AudioSetlist(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("AudioSetlist – DJ Setlist Organizer 🎧")
        self.setGeometry(100, 100, 1000, 650)

        # VLC
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.player_event_manager = self.player.event_manager()
        self.player_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_media_end)

        # State
        self.playlist: list[Track] = []
        self.current_index: int = -1
        self.current_playing: Track | None = None
        self.loop_playlist: bool = True
        self.current_folder: str | None = None

        # Undo/redo for playlist order
        self.order_undo_stack: list[list[Track]] = []
        self.order_redo_stack: list[list[Track]] = []
        self.max_order_undo = 20

        # Undo/redo for renaming
        self.rename_undo_stack: list[list[tuple[str, str]]] = []
        self.rename_redo_stack: list[list[tuple[str, str]]] = []
        self.max_rename_undo = 20

        # UI
        self.setup_ui()
        self.setup_shortcuts()

        # Timers
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(1000)

        self.statusBar().showMessage("AudioSetlist: Ready")

    # -----------------------------------------------------------------
    # UI setup
    # -----------------------------------------------------------------
    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #eee;
            }
            QPushButton {
                font-size: 11px;
            }
            QLineEdit {
                background-color: #333;
                color: #eee;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 3px;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #eee;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #444;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ddd;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(8)

        # ---------------- Left Sidebar ----------------
        sidebar = QVBoxLayout()
        sidebar.setSpacing(10)

        # Folder controls
        folder_box = QVBoxLayout()
        folder_label = QLabel("Folder")
        folder_label.setStyleSheet("font-weight: bold;")
        self.btn_select_folder = QPushButton("Select Folder")
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.btn_select_folder.setToolTip("Select a folder containing your audio files")

        self.btn_refresh = QPushButton("Reload folder")
        self.btn_refresh.clicked.connect(self.refresh_folder)
        self.btn_refresh.setToolTip("Rescan the current folder")

        self.btn_loop = QPushButton("Loop: ON")
        self.btn_loop.clicked.connect(self.toggle_loop)
        self.btn_loop.setToolTip("Toggle playlist looping on/off")

        folder_box.addWidget(folder_label)
        folder_box.addWidget(self.btn_select_folder)
        folder_box.addWidget(self.btn_refresh)
        folder_box.addWidget(self.btn_loop)

        # File renaming section
        rename_box = QVBoxLayout()
        rename_label = QLabel("File Renaming")
        rename_label.setStyleSheet("font-weight: bold; margin-top: 10px;")

        self.btn_rename_file = QPushButton("Rename File")
        self.btn_rename_file.clicked.connect(self.rename_selected_file)
        self.btn_rename_file.setToolTip("Rename only the selected file. Does not affect other tracks.")

        self.btn_rename_all = QPushButton("Rename All (Add Numbers)")
        self.btn_rename_all.clicked.connect(self.rename_all_files)
        self.btn_rename_all.setToolTip("Rename every file in the playlist using sequential numbers to lock in your setlist order.")

        self.btn_undo_rename = QPushButton("Undo File Rename")
        self.btn_undo_rename.clicked.connect(self.undo_rename)
        self.btn_undo_rename.setToolTip("Restore the previous filenames on disk from the last rename operation.")

        self.btn_redo_rename = QPushButton("Redo File Rename")
        self.btn_redo_rename.clicked.connect(self.redo_rename)
        self.btn_redo_rename.setToolTip("Reapply the rename operation you just undid.")

        self.start_index_input = QLineEdit()
        self.start_index_input.setPlaceholderText("Start index (e.g. 1)")
        self.start_index_input.setText("1")

        rename_box.addWidget(rename_label)
        rename_box.addWidget(self.btn_rename_file)
        rename_box.addWidget(self.btn_rename_all)
        rename_box.addWidget(self.start_index_input)
        rename_box.addWidget(self.btn_undo_rename)
        rename_box.addWidget(self.btn_redo_rename)

        # Playlist order section
        order_box = QVBoxLayout()
        order_label = QLabel("Playlist Order")
        order_label.setStyleSheet("font-weight: bold; margin-top: 10px;")

        self.btn_undo_order = QPushButton("Undo Order Change")
        self.btn_undo_order.clicked.connect(self.undo_order_change)
        self.btn_undo_order.setToolTip("Undo the last playlist reorder (drag-and-drop or move up/down).")

        self.btn_redo_order = QPushButton("Redo Order Change")
        self.btn_redo_order.clicked.connect(self.redo_order_change)
        self.btn_redo_order.setToolTip("Redo the last undone playlist reorder.")

        self.btn_move_up = QPushButton("Move Up")
        self.btn_move_up.clicked.connect(self.move_selected_up)
        self.btn_move_up.setToolTip("Move selected track up in the playlist.")

        self.btn_move_down = QPushButton("Move Down")
        self.btn_move_down.clicked.connect(self.move_selected_down)
        self.btn_move_down.setToolTip("Move selected track down in the playlist.")

        order_box.addWidget(order_label)
        order_box.addWidget(self.btn_undo_order)
        order_box.addWidget(self.btn_redo_order)
        order_box.addWidget(self.btn_move_up)
        order_box.addWidget(self.btn_move_down)

        # Help
        help_box = QVBoxLayout()
        help_label = QLabel("Help")
        help_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.btn_help = QPushButton("Show Help (F1)")
        self.btn_help.clicked.connect(self.show_help)

        help_box.addWidget(help_label)
        help_box.addWidget(self.btn_help)

        sidebar.addLayout(folder_box)
        sidebar.addSpacing(10)
        sidebar.addWidget(self._hline())
        sidebar.addLayout(rename_box)
        sidebar.addWidget(self._hline())
        sidebar.addLayout(order_box)
        sidebar.addWidget(self._hline())
        sidebar.addLayout(help_box)
        sidebar.addStretch()

        # ---------------- Main Area ----------------
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)

        # Folder info
        self.folder_info = QLabel("AudioSetlist | Songs: 0 | Total: 00:00:00 | Folder: ")
        self.folder_info.setStyleSheet("font-family: monospace; font-weight: bold;")
        main_layout.addWidget(self.folder_info)

        # Playlist
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Arial", 11))
        self.file_list.setUniformItemSizes(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.itemDoubleClicked.connect(self.play_selected)
        self.file_list.model().rowsMoved.connect(self.on_rows_moved)
        main_layout.addWidget(self.file_list, stretch=1)

        # Now playing
        self.now_playing_label = QLabel("Now Playing: ")
        self.now_playing_label.setStyleSheet("font-family: monospace; font-weight: bold;")
        main_layout.addWidget(self.now_playing_label)

        # Playback controls
        controls_layout = QHBoxLayout()

        self.time_info = QLabel("00:00 / 00:00")
        self.time_info.setStyleSheet("font-family: monospace; font-weight: bold;")
        controls_layout.addWidget(self.time_info)

        controls_layout.addStretch()

        self.btn_prev = QPushButton("⏮")
        self.btn_prev.clicked.connect(self.prev_track)
        self.btn_prev.setToolTip("Previous track (Ctrl+Left)")
        controls_layout.addWidget(self.btn_prev)

        self.btn_play = QPushButton("▶/⏸")
        self.btn_play.clicked.connect(self.play_pause)
        self.btn_play.setToolTip("Play/Pause (Space)")
        controls_layout.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setToolTip("Stop (Ctrl+S)")
        controls_layout.addWidget(self.btn_stop)

        self.btn_next = QPushButton("⏭")
        self.btn_next.clicked.connect(self.next_track)
        self.btn_next.setToolTip("Next track (Ctrl+Right)")
        controls_layout.addWidget(self.btn_next)

        self.btn_scroll_to_playing = QPushButton("Now Playing")
        self.btn_scroll_to_playing.clicked.connect(self.scroll_to_playing)
        self.btn_scroll_to_playing.setToolTip("Scroll to the currently playing track (Ctrl+P)")
        controls_layout.addWidget(self.btn_scroll_to_playing)

        main_layout.addLayout(controls_layout)

        # Sliders
        sliders_layout = QHBoxLayout()
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderMoved.connect(self.seek)
        sliders_layout.addWidget(self.progress_slider)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        sliders_layout.addWidget(self.volume_slider)

        main_layout.addLayout(sliders_layout)

        # Search
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.filter_files)
        search_layout.addWidget(self.search_box)
        main_layout.addLayout(search_layout)

        # Assemble root layout
        root_layout.addLayout(sidebar, stretch=0)
        root_layout.addLayout(main_layout, stretch=1)

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #555;")
        return line

    # -----------------------------------------------------------------
    # Shortcuts
    # -----------------------------------------------------------------
    def setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, activated=self.play_pause)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next_track)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.prev_track)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.stop)
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self.volume_slider.setValue(min(100, self.volume_slider.value() + 5)))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self.volume_slider.setValue(max(0, self.volume_slider.value() - 5)))
        QShortcut(QKeySequence("Return"), self, activated=self.play_selected)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.scroll_to_playing)
        QShortcut(QKeySequence("F2"), self, activated=self.rename_selected_file)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_box.setFocus())
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.search_box.clear())
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_file)

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.select_folder)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_folder)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, activated=self.rename_all_files)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_loop)
        QShortcut(QKeySequence("Shift+Up"), self, activated=self.move_selected_up)
        QShortcut(QKeySequence("Shift+Down"), self, activated=self.move_selected_down)

        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_order_change)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo_order_change)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.undo_rename)
        QShortcut(QKeySequence("Ctrl+Shift+Y"), self, activated=self.redo_rename)

        QShortcut(QKeySequence("F1"), self, activated=self.show_help)

    # -----------------------------------------------------------------
    # Folder handling
    # -----------------------------------------------------------------
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        self.current_folder = folder
        self.scan_folder(folder)

    def refresh_folder(self):
        if not self.current_folder:
            QMessageBox.information(self, "AudioSetlist", "No folder selected.")
            return
        self.scan_folder(self.current_folder)

    def scan_folder(self, folder: str):
        self.stop()
        self.playlist.clear()
        self.update_file_list()

        self.progress_dialog = QProgressDialog("Scanning folder...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("AudioSetlist: Scanning")
        self.progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setMinimumDuration(0)

        self.scanner = FolderScanner(folder, self.instance)
        self.scanner.progress.connect(self.on_scan_progress)
        self.scanner.finished.connect(self.on_scan_finished)
        self.scanner.error.connect(self.on_scan_error)
        self.progress_dialog.canceled.connect(self.scanner.stop)
        self.scanner.start()

    def on_scan_progress(self, current: int, total: int):
        if total > 0:
            self.progress_dialog.setValue(int(current / total * 100))

    def on_scan_finished(self, playlist: list[Track], total_seconds: int):
        self.progress_dialog.close()
        self.playlist = playlist
        self.update_file_list()
        self.statusBar().showMessage(
            f"Scan complete. {len(self.playlist)} tracks, total {datetime.timedelta(seconds=total_seconds)}"
        )

    def on_scan_error(self, message: str):
        self.progress_dialog.close()
        QMessageBox.critical(self, "AudioSetlist: Error", f"Error scanning folder:\n{message}")

    # -----------------------------------------------------------------
    # Playlist / UI sync
    # -----------------------------------------------------------------
    def update_file_list(self):
        self.file_list.setUpdatesEnabled(False)
        self.file_list.clear()
        for track in self.playlist:
            item = QListWidgetItem(track.name)
            item.setData(Qt.ItemDataRole.UserRole, track)
            self.file_list.addItem(item)
        self.file_list.setUpdatesEnabled(True)
        self.update_folder_info()

    def update_folder_info(self):
        total_tracks = len(self.playlist)
        total_seconds = sum(t.duration for t in self.playlist)
        total_time_str = str(datetime.timedelta(seconds=total_seconds))
        foldername = os.path.basename(self.current_folder) if self.current_folder else ""
        self.folder_info.setText(
            f"AudioSetlist | Songs: {total_tracks} | Total: {total_time_str} | Folder: {foldername}"
        )

    def sync_playlist_from_view(self):
        new_playlist: list[Track] = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.ItemDataRole.UserRole)
            new_playlist.append(track)
        self.playlist = new_playlist

    # -----------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------
    def play_selected(self, item: QListWidgetItem | None = None):
        if item is None:
            items = self.file_list.selectedItems()
            if not items:
                return
            item = items[0]
        track = item.data(Qt.ItemDataRole.UserRole)
        if track is None:
            return
        self.current_index = self.playlist.index(track)
        self.play_track(track)

    def play_track(self, track: Track):
        self.stop()
        media = self.instance.media_new(track.path)
        self.player.set_media(media)
        self.player.play()
        self.current_playing = track
        self.now_playing_label.setText(f"Now Playing: {track.name}")
        self.statusBar().showMessage(f"Playing: {track.name}")

    def play_pause(self):
        if self.player.is_playing():
            self.player.pause()
        else:
            if self.current_playing is None and self.playlist:
                self.current_index = 0
                self.play_track(self.playlist[0])
            else:
                self.player.play()

    def stop(self):
        self.player.stop()

    def next_track(self):
        if not self.playlist:
            return
        if self.current_index < 0:
            self.current_index = 0
        else:
            self.current_index += 1
        if self.current_index >= len(self.playlist):
            if self.loop_playlist:
                self.current_index = 0
            else:
                self.stop()
                return
        track = self.playlist[self.current_index]
        self.play_track(track)
        self.scroll_to_playing()

    def prev_track(self):
        if not self.playlist:
            return
        if self.current_index <= 0:
            if self.loop_playlist:
                self.current_index = len(self.playlist) - 1
            else:
                self.current_index = 0
        else:
            self.current_index -= 1
        track = self.playlist[self.current_index]
        self.play_track(track)
        self.scroll_to_playing()

    def on_media_end(self, event):
        self.next_track()

    def update_progress(self):
        if self.current_playing is None or self.current_playing.duration <= 0:
            self.time_info.setText("00:00 / 00:00")
            self.progress_slider.setValue(0)
            return

        length = self.current_playing.duration
        current_ms = self.player.get_time()
        if current_ms < 0:
            current_ms = 0
        current_sec = current_ms // 1000
        current_sec = max(0, min(current_sec, length))

        self.time_info.setText(
            f"{str(datetime.timedelta(seconds=current_sec))} / {str(datetime.timedelta(seconds=length))}"
        )

        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(int(current_sec / length * 1000))

    def seek(self, value: int):
        if self.current_playing is None or self.current_playing.duration <= 0:
            return
        ratio = value / 1000.0
        new_time_ms = int(self.current_playing.duration * 1000 * ratio)
        self.player.set_time(new_time_ms)

    def set_volume(self, value: int):
        self.player.audio_set_volume(value)

    def scroll_to_playing(self):
        if self.current_playing is None:
            return
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.ItemDataRole.UserRole)
            if track is self.current_playing:
                self.file_list.setCurrentItem(item)
                self.file_list.scrollToItem(item)
                break

    # -----------------------------------------------------------------
    # Playlist order / undo
    # -----------------------------------------------------------------
    def push_order_undo(self):
        self.order_undo_stack.append(list(self.playlist))
        if len(self.order_undo_stack) > self.max_order_undo:
            self.order_undo_stack.pop(0)
        self.order_redo_stack.clear()

    def on_rows_moved(self, parent, start, end, dest, row):
        self.push_order_undo()
        self.sync_playlist_from_view()

    def move_selected_up(self):
        row = self.file_list.currentRow()
        if row <= 0:
            return
        self.push_order_undo()
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(row - 1, item)
        self.file_list.setCurrentRow(row - 1)
        self.sync_playlist_from_view()

    def move_selected_down(self):
        row = self.file_list.currentRow()
        if row < 0 or row >= self.file_list.count() - 1:
            return
        self.push_order_undo()
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(row + 1, item)
        self.file_list.setCurrentRow(row + 1)
        self.sync_playlist_from_view()

    def undo_order_change(self):
        if not self.order_undo_stack:
            return
        self.order_redo_stack.append(list(self.playlist))
        self.playlist = self.order_undo_stack.pop()
        self.update_file_list()

    def redo_order_change(self):
        if not self.order_redo_stack:
            return
        self.order_undo_stack.append(list(self.playlist))
        self.playlist = self.order_redo_stack.pop()
        self.update_file_list()

    # -----------------------------------------------------------------
    # Delete
    # -----------------------------------------------------------------
    def delete_selected_file(self):
        items = self.file_list.selectedItems()
        if not items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to remove from the playlist.")
            return
        item = items[0]
        track = item.data(Qt.ItemDataRole.UserRole)
        if track is None:
            return

        reply = QMessageBox.question(
            self,
            "Remove from Playlist",
            f"Remove '{track.name}' from the playlist?\n\n(This does NOT delete the file from disk.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.current_playing is track:
            self.stop()
            self.current_playing = None
            self.current_index = -1

        self.playlist.remove(track)
        self.update_file_list()

    # -----------------------------------------------------------------
    # Renaming
    # -----------------------------------------------------------------
    def rename_selected_file(self):
        items = self.file_list.selectedItems()
        if not items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to rename.")
            return
        item = items[0]
        track = item.data(Qt.ItemDataRole.UserRole)
        if track is None:
            return

        new_name, ok = QInputDialog.getText(self, "Rename File", "New filename:", text=track.name)
        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()
        folder = os.path.dirname(track.path)
        new_path = os.path.join(folder, new_name)
        if os.path.exists(new_path):
            QMessageBox.warning(self, "AudioSetlist", "A file with that name already exists.")
            return

        try:
            os.rename(track.path, new_path)
        except Exception as e:
            QMessageBox.critical(self, "AudioSetlist", f"Failed to rename file:\n{e}")
            return

        # record rename
        self.rename_undo_stack.append([(track.path, new_path)])
        if len(self.rename_undo_stack) > self.max_rename_undo:
            self.rename_undo_stack.pop(0)
        self.rename_redo_stack.clear()

        track.path = new_path
        track.name = os.path.basename(new_path)
        item.setText(track.name)
        self.statusBar().showMessage(f"Renamed to {track.name}")

    def rename_all_files(self):
        if not self.playlist:
            QMessageBox.information(self, "AudioSetlist", "No tracks to rename.")
            return

        try:
            start_index = int(self.start_index_input.text())
        except ValueError:
            QMessageBox.warning(self, "AudioSetlist", "Invalid start index.")
            return

        width = len(str(start_index + len(self.playlist) - 1))
        planned: list[tuple[Track, str]] = []

        for i, track in enumerate(self.playlist):
            folder = os.path.dirname(track.path)
            base, ext = os.path.splitext(track.name)
            index_str = str(start_index + i).zfill(width)
            new_name = f"{index_str} {base}{ext}"
            new_path = os.path.join(folder, new_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "AudioSetlist", f"File already exists: {new_name}")
                return
            planned.append((track, new_path))

        performed: list[tuple[str, str]] = []
        for track, new_path in planned:
            old_path = track.path
            try:
                os.rename(old_path, new_path)
                track.path = new_path
                track.name = os.path.basename(new_path)
                performed.append((old_path, new_path))
            except Exception as e:
                QMessageBox.critical(self, "AudioSetlist", f"Failed to rename {old_path}:\n{e}")
                break

        if performed:
            self.rename_undo_stack.append(performed)
            if len(self.rename_undo_stack) > self.max_rename_undo:
                self.rename_undo_stack.pop(0)
            self.rename_redo_stack.clear()
            self.update_file_list()
            self.statusBar().showMessage("Renamed all files with indices.")

    def undo_rename(self):
        if not self.rename_undo_stack:
            return
        operations = self.rename_undo_stack.pop()
        reverse_ops: list[tuple[str, str]] = []
        for old_path, new_path in reversed(operations):
            if os.path.exists(new_path):
                try:
                    os.rename(new_path, old_path)
                    reverse_ops.append((new_path, old_path))
                    for track in self.playlist:
                        if track.path == new_path:
                            track.path = old_path
                            track.name = os.path.basename(old_path)
                except Exception as e:
                    QMessageBox.critical(self, "AudioSetlist", f"Failed to undo rename {new_path}:\n{e}")
        if reverse_ops:
            self.rename_redo_stack.append(reverse_ops)
        self.update_file_list()

    def redo_rename(self):
        if not self.rename_redo_stack:
            return
        operations = self.rename_redo_stack.pop()
        reverse_ops: list[tuple[str, str]] = []
        for old_path, new_path in reversed(operations):
            if os.path.exists(old_path):
                try:
                    os.rename(old_path, new_path)
                    reverse_ops.append((new_path, old_path))
                    for track in self.playlist:
                        if track.path == old_path:
                            track.path = new_path
                            track.name = os.path.basename(new_path)
                except Exception as e:
                    QMessageBox.critical(self, "AudioSetlist", f"Failed to redo rename {old_path}:\n{e}")
        if reverse_ops:
            self.rename_undo_stack.append(reverse_ops)
        self.update_file_list()

    # -----------------------------------------------------------------
    # Search / filter
    # -----------------------------------------------------------------
    def filter_files(self, text: str):
        text = text.lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.ItemDataRole.UserRole)
            item.setHidden(text not in track.name.lower())

    # -----------------------------------------------------------------
    # Loop toggle
    # -----------------------------------------------------------------
    def toggle_loop(self):
        self.loop_playlist = not self.loop_playlist
        self.btn_loop.setText(f"Loop: {'ON' if self.loop_playlist else 'OFF'}")

    # -----------------------------------------------------------------
    # Help
    # -----------------------------------------------------------------
    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("AudioSetlist Help")
        dlg.setMinimumSize(600, 500)
        layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml("""
        <h2 style="color:#eee;">AudioSetlist – DJ Setlist Organizer</h2>
        <p>Prepare and test your DJ setlists by organizing, renaming, and playing tracks from a folder.</p>
        <h3 style="color:#eee;">Key Concepts</h3>
        <ul>
          <li><b>File Renaming</b>: Changes real filenames on disk.</li>
          <li><b>Playlist Order</b>: Changes only the order inside the app.</li>
        </ul>
        <h3 style="color:#eee;">Keyboard Shortcuts</h3>
        <ul>
          <li><b>Space</b>: Play/Pause</li>
          <li><b>Ctrl+Right / Ctrl+Left</b>: Next / Previous track</li>
          <li><b>Ctrl+S</b>: Stop</li>
          <li><b>Ctrl+O</b>: Select folder</li>
          <li><b>F5</b>: Reload folder</li>
          <li><b>F2</b>: Rename selected file</li>
          <li><b>Ctrl+Shift+R</b>: Rename all (add numbers)</li>
          <li><b>Ctrl+Z / Ctrl+Y</b>: Undo/Redo playlist order</li>
          <li><b>Ctrl+Shift+Z / Ctrl+Shift+Y</b>: Undo/Redo file renaming</li>
          <li><b>Ctrl+F</b>: Focus search box</li>
          <li><b>Esc</b>: Clear search</li>
          <li><b>Delete</b>: Remove from playlist (not from disk)</li>
        </ul>
        """)
        layout.addWidget(text)
        dlg.exec()

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = AudioSetlist()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()