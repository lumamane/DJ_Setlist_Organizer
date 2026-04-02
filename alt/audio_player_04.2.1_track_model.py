import os
import sys
import vlc
import logging
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem,
    QMessageBox, QSlider, QInputDialog, QSizePolicy, QProgressDialog, QDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    progress = pyqtSignal(int, int)          # (current, total)
    finished = pyqtSignal(list, int)         # (playlist: list[Track], total_seconds)
    error = pyqtSignal(str)

    def __init__(self, folder, instance):
        super().__init__()
        self.folder = folder
        self.instance = instance
        self._is_running = True

    def run(self):
        playlist = []
        total_seconds = 0
        try:
            for root, _, files in os.walk(self.folder):
                audio_files = [f for f in files if f.lower().endswith(('.mp3', '.m4a', '.wav'))]
                total_files = len(audio_files)
                for i, file in enumerate(audio_files):
                    if not self._is_running:
                        return
                    path = os.path.join(root, file)
                    try:
                        media = self.instance.media_new(path)
                        media.parse()  # you can later switch to parse_async + event
                        duration_ms = media.get_duration()
                        duration = max(0, duration_ms // 1000)
                        track = Track(path, duration)
                        playlist.append(track)
                        total_seconds += duration
                        self.progress.emit(i + 1, total_files)
                    except Exception as e:
                        logger.error(f"Failed to parse {path}: {e}")
            self.finished.emit(playlist, total_seconds)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------
class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioSetlist: DJ Setlist Organizer  🎧🎛️")
        self.setGeometry(100, 100, 800, 600)
        self._was_maximized = False
        self._restore_size = None

        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #eee;
            }
            QDialog, QTextEdit {
                background-color: #333;
                color: #eee;
                border: 1px solid #444;
                border-radius: 5px;
            }
        """)

        # VLC setup
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.player_event_manager = self.player.event_manager()
        self.player_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_media_end)

        # State
        self.current_playing: Track | None = None
        self.last_played: Track | None = None
        self.playlist: list[Track] = []
        self.current_index: int = -1
        self.is_paused = False
        self.loop_playlist = True
        self.next_track_pending = False
        self.current_folder: str | None = None

        # Undo/Redo stacks (playlist)
        self.undo_stack: list[list[Track]] = []
        self.redo_stack: list[list[Track]] = []
        self.max_undo_steps = 20

        # Undo/Redo stacks (rename)
        self.rename_undo_stack: list[list[tuple[str, str]]] = []  # list of (old_path, new_path)
        self.rename_redo_stack: list[list[tuple[str, str]]] = []
        self.max_rename_steps = 20

        # UI
        self.setup_ui()
        self.setup_shortcuts()

        # Status bar
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("AudioSetlist: Ready")

        # Timers
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_player_state)
        self.state_timer.start(500)

        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(1000)

    # -----------------------------------------------------------------
    # Window state
    # -----------------------------------------------------------------
    def save_window_state(self):
        self._was_maximized = self.isMaximized()
        self._restore_size = self.size()

    def restore_window_state(self):
        if self._was_maximized:
            self.showMaximized()
        elif self._restore_size is not None:
            self.resize(self._restore_size)

    # -----------------------------------------------------------------
    # UI setup
    # -----------------------------------------------------------------
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Top controls
        top_controls = QHBoxLayout()

        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        self.folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """)
        self.folder_btn.setToolTip("Select a folder containing your DJ set audio files")

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_songlist)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFC107;
                color: #222;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #FFB300;
            }
            QPushButton:pressed {
                background-color: #FFA000;
            }
        """)
        self.refresh_btn.setToolTip("Refresh the song list")

        self.loop_btn = QPushButton("Loop: ON")
        self.loop_btn.clicked.connect(self.toggle_loop)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #8E24AA;
            }
            QPushButton:pressed {
                background-color: #7B1FA2;
            }
        """)
        self.loop_btn.setToolTip("Toggle playlist looping on/off")

        self.rename_btn = QPushButton("Add Index")
        self.rename_btn.clicked.connect(self.rename_all)
        self.rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        """)
        self.rename_btn.setToolTip("Rename all files in the current order (adds sequential indices)")

        self.rename_one_btn = QPushButton("Rename")
        self.rename_one_btn.clicked.connect(self.rename_selected_file)
        self.rename_one_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)
        self.rename_one_btn.setToolTip("Rename the selected file")

        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo_playlist_reorder)
        self.undo_btn.setToolTip("Undo last playlist reorder (Ctrl+Z)")
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)

        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self.redo_playlist_reorder)
        self.redo_btn.setToolTip("Redo last playlist reorder (Ctrl+Y)")
        self.redo_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)

        self.rename_undo_btn = QPushButton("Undo Rename")
        self.rename_undo_btn.clicked.connect(self.undo_rename)
        self.rename_undo_btn.setToolTip("Undo last rename operation (Ctrl+Shift+Z)")
        self.rename_undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)

        self.rename_redo_btn = QPushButton("Redo Rename")
        self.rename_redo_btn.clicked.connect(self.redo_rename)
        self.rename_redo_btn.setToolTip("Redo last rename operation (Ctrl+Shift+Y)")
        self.rename_redo_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)

        self.start_index_input = QLineEdit()
        self.start_index_input.setPlaceholderText("Start index (e.g., 1)")
        self.start_index_input.setText("1")
        self.start_index_input.setFixedWidth(80)
        self.start_index_input.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: #eee;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 4px;
            }
        """)

        self.help_btn = QPushButton("Help (F1)")
        self.help_btn.clicked.connect(self.show_help)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #546E7A;
            }
            QPushButton:pressed {
                background-color: #37474F;
            }
        """)
        self.help_btn.setToolTip("Show AudioSetlist help and keyboard shortcuts")

        top_controls.addWidget(self.folder_btn)
        top_controls.addWidget(self.refresh_btn)
        top_controls.addWidget(self.rename_btn)
        top_controls.addWidget(self.start_index_input)
        top_controls.addWidget(self.rename_one_btn)
        top_controls.addWidget(self.undo_btn)
        top_controls.addWidget(self.redo_btn)
        top_controls.addWidget(self.rename_undo_btn)
        top_controls.addWidget(self.rename_redo_btn)
        top_controls.addWidget(self.help_btn)
        top_controls.addWidget(self.loop_btn)
        top_controls.addStretch()
        layout.addLayout(top_controls)

        # Folder info
        self.folder_info = QLabel("AudioSetlist | Songs in folder: 0 | Total time: 00:00:00 | Remaining: 00:00:00 | Finish: 00:00 | Foldername: ")
        self.folder_info.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        self.folder_info.setFixedWidth(800)
        layout.addWidget(self.folder_info)

        # File list
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.play_selected)
        self.file_list.setFont(QFont("Arial", 11))
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                color: #eee;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 2px;
                spacing: 0px;
            }
            QListWidget::item {
                padding: 1px;
                margin: 0px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #3a3a3a;
                color: #fff;
            }
        """)
        self.file_list.setUniformItemSizes(True)
        self.file_list.setSpacing(0)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.model().rowsMoved.connect(self.on_rows_moved)
        layout.addWidget(self.file_list, stretch=1)

        # Now playing
        self.now_playing_label = QLabel("AudioSetlist: Now Playing: ")
        self.now_playing_label.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        layout.addWidget(self.now_playing_label)

        # Time + playback controls
        time_and_controls = QHBoxLayout()
        self.time_info = QLabel("00:00 / 00:00")
        self.time_info.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        time_and_controls.addWidget(self.time_info)
        time_and_controls.addStretch()

        self.play_btn = QPushButton("▶/⏸")
        self.play_btn.clicked.connect(self.play_pause)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px 15px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.play_btn.setToolTip("Play/Pause (Space)")

        self.stop_btn = QPushButton("◼")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                font-weight: bold;
                padding: 6px 15px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:pressed {
                background-color: #B71FA1;
            }
        """)
        self.stop_btn.setToolTip("Stop (Ctrl+S)")

        self.prev_btn = QPushButton("<<")
        self.prev_btn.clicked.connect(self.prev_track)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
        """)
        self.prev_btn.setToolTip("Previous Track (Ctrl+Left)")

        self.next_btn = QPushButton(">>")
        self.next_btn.clicked.connect(self.next_track)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
        """)
        self.next_btn.setToolTip("Next Track (Ctrl+Right)")

        time_and_controls.addWidget(self.prev_btn)
        time_and_controls.addWidget(self.play_btn)
        time_and_controls.addWidget(self.stop_btn)
        time_and_controls.addWidget(self.next_btn)
        time_and_controls.addStretch()

        self.scroll_to_playing_btn = QPushButton("Now playing")
        self.scroll_to_playing_btn.clicked.connect(self.scroll_to_playing)
        self.scroll_to_playing_btn.setStyleSheet("""
            QPushButton {
                background-color: #673AB7;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5E35B1;
            }
            QPushButton:pressed {
                background-color: #4527A0;
            }
        """)
        self.scroll_to_playing_btn.setToolTip("Scroll to the currently playing track (Ctrl+P)")
        time_and_controls.addWidget(self.scroll_to_playing_btn)

        layout.addLayout(time_and_controls)

        # Sliders
        sliders = QHBoxLayout()
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderMoved.connect(self.seek)
        sliders.addWidget(self.progress_slider)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        sliders.addWidget(self.volume_slider)

        layout.addLayout(sliders)

        # Search
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #eee;")
        search_layout.addWidget(search_label)
        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.filter_files)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: #eee;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 4px;
            }
        """)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)

    # -----------------------------------------------------------------
    # Shortcuts
    # -----------------------------------------------------------------
    def setup_shortcuts(self):
        # Playback
        QShortcut(QKeySequence("Space"), self, activated=self.play_pause)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next_track)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.prev_track)
        QShortcut(QKeySequence("Shift+Right"), self, activated=lambda: self.seek_forward())
        QShortcut(QKeySequence("Shift+Left"), self, activated=lambda: self.seek_backward())
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.stop)
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() + 5))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() - 5))

        # Navigation
        QShortcut(QKeySequence("Return"), self, activated=self.play_selected_with_fade)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.scroll_to_playing)
        QShortcut(QKeySequence("F2"), self, activated=self.rename_selected_file)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search_box.setFocus())
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.search_box.clear())
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_file)

        # Playlist
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.select_folder)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_songlist)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, activated=self.rename_all)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.toggle_loop)
        QShortcut(QKeySequence("Shift+Up"), self, activated=self.move_selected_up)
        QShortcut(QKeySequence("Shift+Down"), self, activated=self.move_selected_down)

        # Undo/Redo
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_playlist_reorder)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo_playlist_reorder)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.undo_rename)
        QShortcut(QKeySequence("Ctrl+Shift+Y"), self, activated=self.redo_rename)

        # Help
        QShortcut(QKeySequence("F1"), self, activated=self.show_help)

    # -----------------------------------------------------------------
    # Core helpers
    # -----------------------------------------------------------------
    def push_playlist_undo(self):
        self.undo_stack.append(list(self.playlist))
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def update_file_list(self):
        self.file_list.setUpdatesEnabled(False)
        self.file_list.clear()
        for track in self.playlist:
            item = QListWidgetItem(track.name)
            item.setData(Qt.UserRole, track)
            self.file_list.addItem(item)
        self.file_list.setUpdatesEnabled(True)
        self.update_folder_info()

    def update_folder_info(self):
        total_tracks = len(self.playlist)
        total_seconds = sum(t.duration for t in self.playlist)
        total_time_str = str(datetime.timedelta(seconds=total_seconds))
        remaining_str = total_time_str  # you can refine this based on current index
        finish_time = (datetime.datetime.now() + datetime.timedelta(seconds=total_seconds)).strftime("%H:%M")
        foldername = os.path.basename(self.current_folder) if self.current_folder else ""
        self.folder_info.setText(
            f"AudioSetlist | Songs in folder: {total_tracks} | Total time: {total_time_str} | "
            f"Remaining: {remaining_str} | Finish: {finish_time} | Foldername: {foldername}"
        )

    # -----------------------------------------------------------------
    # Folder selection & scanning
    # -----------------------------------------------------------------
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        self.current_folder = folder
        self.scan_folder(folder)

    def refresh_songlist(self):
        if not self.current_folder:
            QMessageBox.information(self, "AudioSetlist", "No folder selected.")
            return
        self.scan_folder(self.current_folder)

    def scan_folder(self, folder):
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

    def on_scan_progress(self, current, total):
        if total > 0:
            self.progress_dialog.setValue(int(current / total * 100))

    def on_scan_finished(self, playlist, total_seconds):
        self.progress_dialog.close()
        self.playlist = playlist
        self.update_file_list()
        self.statusBar.showMessage(f"Scan complete. {len(self.playlist)} tracks, total {datetime.timedelta(seconds=total_seconds)}")

    def on_scan_error(self, message):
        self.progress_dialog.close()
        QMessageBox.critical(self, "AudioSetlist: Error", f"Error scanning folder:\n{message}")

    # -----------------------------------------------------------------
    # Playback
    # -----------------------------------------------------------------
    def play_selected(self, item=None):
        if item is None:
            items = self.file_list.selectedItems()
            if not items:
                return
            item = items[0]
        track = item.data(Qt.UserRole)
        if track is None:
            return
        self.current_index = self.playlist.index(track)
        self.play_track(track)

    def play_selected_with_fade(self):
        # placeholder: same as play_selected for now
        self.play_selected()

    def play_track(self, track: Track):
        self.stop()
        media = self.instance.media_new(track.path)
        self.player.set_media(media)
        self.player.play()
        self.current_playing = track
        self.is_paused = False
        self.now_playing_label.setText(f"AudioSetlist: Now Playing: {track.name}")
        self.statusBar.showMessage(f"Playing: {track.name}")

    def play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.is_paused = True
        else:
            if self.current_playing is None and self.playlist:
                self.current_index = 0
                self.play_track(self.playlist[0])
            else:
                self.player.play()
                self.is_paused = False

    def stop(self):
        self.player.stop()
        self.is_paused = False

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

    def check_player_state(self):
        # fallback if needed; currently minimal
        pass

    def update_progress(self):
        if self.current_playing is None:
            self.time_info.setText("00:00 / 00:00")
            self.progress_slider.setValue(0)
            return
        length = self.current_playing.duration
        if length <= 0:
            self.time_info.setText("00:00 / 00:00")
            self.progress_slider.setValue(0)
            return
        current_ms = self.player.get_time()
        if current_ms < 0:
            current_ms = 0
        current_sec = current_ms // 1000
        current_sec = max(0, min(current_sec, length))
        self.time_info.setText(f"{str(datetime.timedelta(seconds=current_sec))} / {str(datetime.timedelta(seconds=length))}")
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(int(current_sec / length * 1000))

    def seek(self, value):
        if self.current_playing is None or self.current_playing.duration <= 0:
            return
        ratio = value / 1000.0
        new_time_ms = int(self.current_playing.duration * 1000 * ratio)
        self.player.set_time(new_time_ms)

    def seek_forward(self, seconds=5):
        t = self.player.get_time()
        self.player.set_time(t + seconds * 1000)

    def seek_backward(self, seconds=5):
        t = self.player.get_time()
        self.player.set_time(max(0, t - seconds * 1000))

    def set_volume(self, value):
        self.player.audio_set_volume(value)

    def scroll_to_playing(self):
        if self.current_playing is None:
            return
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.UserRole)
            if track is self.current_playing:
                self.file_list.setCurrentItem(item)
                self.file_list.scrollToItem(item)
                break

    # -----------------------------------------------------------------
    # Playlist reordering
    # -----------------------------------------------------------------
    def on_rows_moved(self, parent, start, end, dest, row):
        # Simple approach: rebuild playlist from QListWidget order
        self.push_playlist_undo()
        new_playlist = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.UserRole)
            new_playlist.append(track)
        self.playlist = new_playlist

    def move_selected_up(self):
        row = self.file_list.currentRow()
        if row <= 0:
            return
        self.push_playlist_undo()
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(row - 1, item)
        self.file_list.setCurrentRow(row - 1)
        self.sync_playlist_from_view()

    def move_selected_down(self):
        row = self.file_list.currentRow()
        if row < 0 or row >= self.file_list.count() - 1:
            return
        self.push_playlist_undo()
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(row + 1, item)
        self.file_list.setCurrentRow(row + 1)
        self.sync_playlist_from_view()

    def sync_playlist_from_view(self):
        new_playlist = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.UserRole)
            new_playlist.append(track)
        self.playlist = new_playlist

    def undo_playlist_reorder(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(list(self.playlist))
        self.playlist = self.undo_stack.pop()
        self.update_file_list()

    def redo_playlist_reorder(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(list(self.playlist))
        self.playlist = self.redo_stack.pop()
        self.update_file_list()

    # -----------------------------------------------------------------
    # Delete
    # -----------------------------------------------------------------
    def delete_selected_file(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to delete.")
            return

        item = selected_items[0]
        row = self.file_list.row(item)
        if row < 0:
            return

        track = item.data(Qt.UserRole)
        if track is None:
            QMessageBox.warning(self, "AudioSetlist Error", "Selected item has no track data.")
            return

        reply = QMessageBox.question(
            self, "AudioSetlist: Confirm Delete",
            f"Are you sure you want to delete '{track.name}' from your setlist?\n\n"
            "This will only remove it from the playlist, not from your disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.current_playing is track:
                self.stop()
                self.current_playing = None
                self.current_index = -1
            self.playlist.remove(track)
            self.update_file_list()
            QMessageBox.information(self, "AudioSetlist", f"'{track.name}' removed from the setlist.")

    # -----------------------------------------------------------------
    # Renaming
    # -----------------------------------------------------------------
    def rename_selected_file(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to rename.")
            return
        item = selected_items[0]
        track = item.data(Qt.UserRole)
        if track is None:
            return

        new_name, ok = QInputDialog.getText(self, "AudioSetlist: Rename File", "New name:", text=track.name)
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

        # record rename for undo
        self.rename_undo_stack.append([(track.path, new_path)])
        if len(self.rename_undo_stack) > self.max_rename_steps:
            self.rename_undo_stack.pop(0)
        self.rename_redo_stack.clear()

        track.path = new_path
        track.name = os.path.basename(new_path)
        item.setText(track.name)
        self.statusBar.showMessage(f"Renamed to {track.name}")

    def rename_all(self):
        if not self.playlist:
            QMessageBox.information(self, "AudioSetlist", "No tracks to rename.")
            return

        try:
            start_index = int(self.start_index_input.text())
        except ValueError:
            QMessageBox.warning(self, "AudioSetlist", "Invalid start index.")
            return

        width = len(str(start_index + len(self.playlist) - 1))
        renames = []

        for i, track in enumerate(self.playlist):
            folder = os.path.dirname(track.path)
            base, ext = os.path.splitext(track.name)
            index_str = str(start_index + i).zfill(width)
            new_name = f"{index_str} {base}{ext}"
            new_path = os.path.join(folder, new_name)
            if os.path.exists(new_path):
                QMessageBox.warning(self, "AudioSetlist", f"File already exists: {new_name}")
                return
            renames.append((track, new_path))

        # perform renames
        performed = []
        for track, new_path in renames:
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
            if len(self.rename_undo_stack) > self.max_rename_steps:
                self.rename_undo_stack.pop(0)
            self.rename_redo_stack.clear()
            self.update_file_list()
            self.statusBar.showMessage("Renamed all files with indices.")

    def undo_rename(self):
        if not self.rename_undo_stack:
            return
        operations = self.rename_undo_stack.pop()
        reverse_ops = []
        for old_path, new_path in reversed(operations):
            if os.path.exists(new_path):
                try:
                    os.rename(new_path, old_path)
                    reverse_ops.append((new_path, old_path))
                    # update track objects
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
        reverse_ops = []
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
    # Search/filter
    # -----------------------------------------------------------------
    def filter_files(self, text):
        text = text.lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            track = item.data(Qt.UserRole)
            if text in track.name.lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    # -----------------------------------------------------------------
    # Loop toggle
    # -----------------------------------------------------------------
    def toggle_loop(self):
        self.loop_playlist = not self.loop_playlist
        self.loop_btn.setText(f"Loop: {'ON' if self.loop_playlist else 'OFF'}")

    # -----------------------------------------------------------------
    # Help dialog
    # -----------------------------------------------------------------
    def show_help(self):
        help_text = """
        <h1 style="color: #eee; text-align: center;">AudioSetlist: DJ Setlist Organizer</h1>
        <p><strong>Prepare your next DJ gig with ease!</strong></p>
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("AudioSetlist Help")
        dlg.setMinimumSize(600, 600)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(help_text)
        text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #eee;
                border: none;
                font-family: Arial;
                font-size: 12px;
            }
        """)
        layout.addWidget(text)
        dlg.exec()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
