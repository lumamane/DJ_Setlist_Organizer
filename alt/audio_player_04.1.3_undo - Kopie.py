import os
import sys
import vlc
import re
import logging
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem,
    QMessageBox, QSlider, QInputDialog, QSizePolicy, QProgressDialog, QDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QKeySequence, QShortcut

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FolderScanner(QThread):
    progress = pyqtSignal(int, int)  # (current, total)
    finished = pyqtSignal(list, int, dict)  # (playlist, total_seconds, track_durations)
    error = pyqtSignal(str)

    def __init__(self, folder, instance):
        super().__init__()
        self.folder = folder
        self.instance = instance
        self._is_running = True

    def run(self):
        playlist = []
        total_seconds = 0
        track_durations = {}
        try:
            for root, _, files in os.walk(self.folder):
                for i, file in enumerate(files):
                    if not self._is_running:
                        return
                    if file.lower().endswith(('.mp3', '.m4a', '.wav')):
                        path = os.path.join(root, file)
                        try:
                            media = self.instance.media_new(path)
                            media.parse()
                            duration = media.get_duration() // 1000
                            playlist.append(path)
                            track_durations[path] = duration
                            total_seconds += duration
                            self.progress.emit(i + 1, len(files))
                        except Exception as e:
                            logger.error(f"Failed to parse {path}: {e}")
            self.finished.emit(playlist, total_seconds, track_durations)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False

class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioSetlist: DJ Setlist Organizer  🎧🎛️")
        self.setGeometry(100, 100, 800, 600)
        self._was_maximized = False
        self._restore_size = None

        # Set dark palette for the whole app
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

        # UI
        self.setup_ui()
        self.setup_shortcuts()
        self.current_playing = None
        self.last_played = None
        self.playlist = []  # Stores full paths
        self.current_index = -1
        self.is_paused = False
        self.loop_playlist = True
        self.next_track_pending = False
        self.current_folder = None
        self.track_durations = {}  # Stores duration of each track

        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo_steps = 20
        self.rename_undo_stack = []
        self.rename_redo_stack = []
        self.max_rename_steps = 20

        # Status bar
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("AudioSetlist: Ready")

        # Timer to check player state (fallback)
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_player_state)
        self.state_timer.start(500)

        # Timer to update progress
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(1000)  # Update every second

    def save_window_state(self):
        self._was_maximized = self.isMaximized()
        self._restore_size = self.size()

    def restore_window_state(self):
        if self._was_maximized:
            self.showMaximized()
        else:
            self.resize(self._restore_size)

    def split_filename_ext(self, filename):
        """Split filename into name and extension."""
        return os.path.splitext(filename)

    def setup_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # --- Top Controls ---
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

        # Undo/Redo buttons
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

        top_controls.addWidget(self.folder_btn)
        top_controls.addWidget(self.refresh_btn)
        top_controls.addWidget(self.rename_btn)

        # Add a QLineEdit for start index
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
        top_controls.addWidget(self.start_index_input)

        top_controls.addWidget(self.rename_one_btn)
        top_controls.addWidget(self.undo_btn)
        top_controls.addWidget(self.redo_btn)
        top_controls.addWidget(self.rename_undo_btn)
        top_controls.addWidget(self.rename_redo_btn)
        top_controls.addStretch()

        # Help button
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
        top_controls.addWidget(self.help_btn)
        top_controls.addWidget(self.loop_btn)
        layout.addLayout(top_controls)

        # --- Folder Info ---
        self.folder_info = QLabel("AudioSetlist | Songs in folder: 0 | Total time: 00:00:00 | Remaining: 00:00:00 | Finish: 00:00 | Foldername: ")
        self.folder_info.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        self.folder_info.setFixedWidth(800)
        layout.addWidget(self.folder_info)

        # --- File List ---
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

        # --- Now Playing Label ---
        self.now_playing_label = QLabel("AudioSetlist: Now Playing: ")
        self.now_playing_label.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        layout.addWidget(self.now_playing_label)

        # --- Time and Playback Controls (together) ---
        time_and_controls = QHBoxLayout()
        self.time_info = QLabel("00:00 / 00:00")
        self.time_info.setStyleSheet("color: #eee; font-weight: bold; font-family: monospace;")
        time_and_controls.addWidget(self.time_info)
        time_and_controls.addStretch()

        # Playback buttons
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

        # --- Progress and Volume Sliders (together) ---
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

        # --- Search Box (below songs) ---
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

    def show_help(self):
        help_text = """
        <h1 style="color: #eee; text-align: center;">AudioSetlist: DJ Setlist Organizer</h1>

        <p><strong>Prepare your next DJ gig with ease!</strong><br>
        AudioSetlist helps you <strong>organize, listen, and order your music files</strong> for upcoming performances.
        With a clean, dark-themed interface and intuitive controls, you can focus on crafting the perfect setlist.</p>

        <h2 style="color: #eee;">Key Features</h2>
        <ul>
            <li><strong>Drag-and-Drop Reordering:</strong> Arrange your tracks in the ideal order for your set.</li>
            <li><strong>Live Playback & Preview:</strong> Listen to each track directly in the app.</li>
            <li><strong>Save Order by Renaming:</strong> Rename all files with sequential indices (e.g., 001_song.mp3, 002_song.mp3).</li>
            <li><strong>Custom Start Index:</strong> Start numbering from any value to fit your existing file naming scheme.</li>
            <li><strong>Search & Filter:</strong> Quickly find songs in your collection.</li>
            <li><strong>Dark Theme:</strong> Easy on the eyes during long studio sessions.</li>
            <li><strong>Keyboard Shortcuts:</strong> Speed up your workflow with handy shortcuts.</li>
            <li><strong>Remove Tracks:</strong> Delete tracks from your setlist (without deleting files from disk).</li>
            <li><strong>Undo/Redo:</strong> Undo or redo playlist reordering and file renaming.</li>
        </ul>

        <h2 style="color: #eee;">Why Use AudioSetlist?</h2>
        <ul>
            <li><strong>No More Manual Renaming:</strong> Forget about manually renaming files one by one.</li>
            <li><strong>Visual Setlist Planning:</strong> See your entire set at a glance and make changes on the fly.</li>
            <li><strong>Portable Setlists:</strong> Your ordered files will work in any DJ software or on any USB drive.</li>
            <li><strong>Focus on the Music:</strong> Spend less time organizing and more time perfecting your mix.</li>
        </ul>

        <h2 style="color: #eee;">Keyboard Shortcuts</h2>

        <h3 style="color: #eee;">Playback</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><b>Space</b></td><td>Play/Pause</td></tr>
            <tr><td><b>Ctrl+→</b></td><td>Next Track</td></tr>
            <tr><td><b>Ctrl+←</b></td><td>Previous Track</td></tr>
            <tr><td><b>Shift+→</b></td><td>Fast Forward (5 sec)</td></tr>
            <tr><td><b>Shift+←</b></td><td>Fast Backward (5 sec)</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>Stop</td></tr>
            <tr><td><b>Ctrl+↑</b></td><td>Volume Up</td></tr>
            <tr><td><b>Ctrl+↓</b></td><td>Volume Down</td></tr>
        </table>

        <h3 style="color: #eee;">Navigation</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><b>Enter</b></td><td>Play Selected Song</td></tr>
            <tr><td><b>Ctrl+P</b></td><td>Scroll to Now Playing</td></tr>
            <tr><td><b>Ctrl+F</b></td><td>Focus Search Box</td></tr>
            <tr><td><b>Esc</b></td><td>Clear Search Box</td></tr>
            <tr><td><b>Delete</b></td><td>Remove Selected Track from Setlist</td></tr>
        </table>

        <h3 style="color: #eee;">Playlist</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><b>Ctrl+O</b></td><td>Select Folder</td></tr>
            <tr><td><b>F5</b></td><td>Refresh Song List</td></tr>
            <tr><td><b>Ctrl+Shift+R</b></td><td>Rename All Files (Add Index)</td></tr>
            <tr><td><b>F2</b></td><td>Rename Selected File</td></tr>
            <tr><td><b>Shift+↑/↓</b></td><td>Move Selected Song Up/Down</td></tr>
            <tr><td><b>Ctrl+L</b></td><td>Toggle Loop</td></tr>
            <tr><td><b>Ctrl+Z</b></td><td>Undo Playlist Reorder</td></tr>
            <tr><td><b>Ctrl+Y</b></td><td>Redo Playlist Reorder</td></tr>
            <tr><td><b>Ctrl+Shift+Z</b></td><td>Undo Rename</td></tr>
            <tr><td><b>Ctrl+Shift+Y</b></td><td>Redo Rename</td></tr>
        </table>

        <h3 style="color: #eee;">Help</h3>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><b>F1</b></td><td>Show This Help</td></tr>
        </table>

        <p style="text-align: center; font-size: 11px; color: #aaa;">
            AudioSetlist: Your music, your order, your way.
        </p>
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

    def delete_selected_file(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to delete.")
            return

        item = selected_items[0]
        row = self.file_list.row(item)
        if row < 0:
            return

        visible_filename = item.text()
        matching_files = [f for f in self.playlist if os.path.basename(f) == visible_filename]
        if not matching_files:
            QMessageBox.warning(self, "AudioSetlist Error", "Selected file not found in playlist.")
            return
        file_path = matching_files[0]

        reply = QMessageBox.question(
            self, "AudioSetlist: Confirm Delete",
            f"Are you sure you want to delete '{visible_filename}' from your setlist?\n\n"
            "This will only remove it from the playlist, not from your disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.playlist.remove(file_path)
            if file_path in self.track_durations:
                del self.track_durations[file_path]
            if self.current_playing == file_path:
                self.stop()
                self.current_playing = None
                self.current_index = -1
            self.update_file_list()
            QMessageBox.information(self, "AudioSetlist", f"'{visible_filename}' removed from the setlist.")

    def move_selected_up(self):
        row = self.file_list.currentRow()
        if row > 0:
            item = self.file_list.takeItem(row)
            self.file_list.insertItem(row - 1, item)
            self.file_list.setCurrentRow(row - 1)
            self.on_rows_moved()

    def move_selected_down(self):
        row = self.file_list.currentRow()
        if row < self.file_list.count() - 1:
            item = self.file_list.takeItem(row)
            self.file_list.insertItem(row + 1, item)
            self.file_list.setCurrentRow(row + 1)
            self.on_rows_moved()

    def on_rows_moved(self, *args):
        # Save current state to undo stack
        self.undo_stack.append(self.playlist.copy())
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.redo_stack.clear()  # Clear redo stack on new action

        # Update current playlist
        current_order = self.get_current_playlist_order()
        self.playlist = current_order.copy()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        logger.debug("Updated playlist order after drag-and-drop or move")

    def play_selected_with_fade(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        current_order = self.get_current_playlist_order()
        selected_filename = item.text()
        for i, file in enumerate(current_order):
            if os.path.basename(file) == selected_filename:
                self.current_index = self.playlist.index(file)
                break
        if self.player.is_playing():
            self.stop()
        self.play_track(self.current_index)

    def seek_forward(self):
        if self.player.get_media():
            current_time = self.player.get_time()
            self.player.set_time(current_time + 5000)  # Fast forward 5 seconds

    def seek_backward(self):
        if self.player.get_media():
            current_time = self.player.get_time()
            self.player.set_time(max(0, current_time - 5000))  # Fast backward 5 seconds

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "AudioSetlist: Select Folder")
        if folder:
            self.current_folder = folder
            self.scan_folder(folder)

    def scan_folder(self, folder):
        self.save_window_state()
        self.file_list.clear()
        self.playlist = []
        self.track_durations = {}

        # Show progress dialog
        self.progress_dialog = QProgressDialog("AudioSetlist: Scanning folder...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("AudioSetlist: Scanning")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.canceled.connect(self.cancel_scan)
        self.progress_dialog.show()

        # Start scanner thread
        self.scanner = FolderScanner(folder, self.instance)
        self.scanner.progress.connect(self.update_scan_progress)
        self.scanner.finished.connect(self.on_scan_finished)
        self.scanner.error.connect(self.on_scan_error)
        self.scanner.start()
        self.statusBar.showMessage("AudioSetlist: Scanning folder...")

    def update_scan_progress(self, current, total):
        progress = int((current / total) * 100)
        self.progress_dialog.setValue(progress)
        self.statusBar.showMessage(f"AudioSetlist: Scanning: {progress}%")

    def cancel_scan(self):
        self.scanner.stop()
        self.progress_dialog.close()
        self.statusBar.showMessage("AudioSetlist: Scan canceled")

    def on_scan_finished(self, playlist, total_seconds, track_durations):
        self.progress_dialog.close()
        self.playlist = playlist
        self.track_durations = track_durations
        self.update_file_list()
        self.update_folder_info(total_seconds=total_seconds, remaining_seconds=total_seconds)
        self.restore_window_state()
        self.statusBar.showMessage(f"AudioSetlist: Found {len(playlist)} files")

    def on_scan_error(self, error):
        self.progress_dialog.close()
        QMessageBox.warning(self, "AudioSetlist Error", f"Failed to scan folder: {error}")
        self.statusBar.showMessage("AudioSetlist: Scan error")

    def toggle_loop(self):
        """Toggle playlist looping on/off"""
        self.loop_playlist = not self.loop_playlist
        self.loop_btn.setText(f"Loop: {'ON' if self.loop_playlist else 'OFF'}")
        logger.debug("Playlist looping %s", "enabled" if self.loop_playlist else "disabled")

    def check_player_state(self):
        """Check player state periodically and handle transitions"""
        state = self.player.get_state()
        logger.debug("Player state: %s", state)
        if state == vlc.State.Ended:
            if not self.is_paused:
                logger.debug("Detected Ended state, moving to next track")
                self.next_track()
        elif state == vlc.State.Error:
            logger.error("Player in Error state, attempting to recover")
            if self.current_index < len(self.playlist) - 1:
                self.next_track()
            else:
                self.stop()

    def on_media_end(self, event):
        """Called when the current media finishes playing."""
        logger.debug("on_media_end event received, current state: %s", self.player.get_state())
        if not self.is_paused:
            QTimer.singleShot(100, self.next_track)
        self.now_playing_label.setText("AudioSetlist: Now Playing: ")

    def update_folder_info(self, total_seconds=None, remaining_seconds=None):
        """Update the folder info label with folder name, total and remaining time, and expected finish time."""
        if total_seconds is None:
            total_seconds = sum(self.track_durations.values())

        folder_name = os.path.basename(self.current_folder) if self.current_folder else "No folder selected"
        max_name_length = 40  # Truncate if longer than 40 chars
        if len(folder_name) > max_name_length:
            folder_name = folder_name[:max_name_length-3] + "..."

        songs_count = len(self.playlist)

        total_h = total_seconds // 3600
        total_m = (total_seconds % 3600) // 60
        total_s = total_seconds % 60

        remaining_h = remaining_seconds // 3600 if remaining_seconds is not None and remaining_seconds >= 0 else 0
        remaining_m = (remaining_seconds % 3600) // 60 if remaining_seconds is not None and remaining_seconds >= 0 else 0
        remaining_s = remaining_seconds % 60 if remaining_seconds is not None and remaining_seconds >= 0 else 0

        finish_time = (datetime.datetime.now() + datetime.timedelta(seconds=remaining_seconds)).strftime("%H:%M") if remaining_seconds is not None and remaining_seconds >= 0 else "00:00"

        self.folder_info.setText(
            f"AudioSetlist | Songs: {songs_count} | "
            f"Total: {total_h:02d}:{total_m:02d}:{total_s:02d} | "
            f"Remaining: {remaining_h:02d}:{remaining_m:02d}:{remaining_s:02d} | "
            f"Finish: {finish_time} | "
            f"Folder: {folder_name}"
        )

    def update_file_list(self):
        """Update the file list widget with current playlist, respecting the current filter."""
        current_filter = self.search_box.text()
        self.file_list.clear()
        for file in self.playlist:
            if not current_filter or current_filter.lower() in os.path.basename(file).lower():
                self.file_list.addItem(os.path.basename(file))

    def get_current_playlist_order(self):
        """Get the current visual order of files from the list widget"""
        current_order = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            filename = item.text()
            for file in self.playlist:
                if os.path.basename(file) == filename:
                    current_order.append(file)
                    break
        return current_order

    def play_selected(self, item):
        """Play the selected song, using visual order"""
        current_order = self.get_current_playlist_order()
        selected_filename = item.text()
        for i, file in enumerate(current_order):
            if os.path.basename(file) == selected_filename:
                self.current_index = self.playlist.index(file)
                break
        self.play_track(self.current_index)

    def play_track(self, index):
        if not (0 <= index < len(self.playlist)):
            logger.error("Invalid track index: %d", index)
            return
        self.stop()
        try:
            QTimer.singleShot(100, lambda: self._play_track(index))
        except Exception as e:
            logger.error("Failed to play track: %s", e)
            QMessageBox.warning(self, "AudioSetlist Error", f"Failed to play track: {e}")

    def _play_track(self, index):
        """Internal method to play a track with proper state handling"""
        media = self.instance.media_new(self.playlist[index])
        self.player.set_media(media)
        logger.debug("Media set for track %d, state: %s", index, self.player.get_state())
        self.player.play()
        logger.debug("Play called for track %d, state: %s", index, self.player.get_state())
        self.is_paused = False
        logger.debug("Playing track %d: %s", index, self.playlist[index])

        self.now_playing_label.setText(f"AudioSetlist: Now Playing: {os.path.basename(self.playlist[index])}")

        if self.current_index >= 0:
            remaining_seconds = sum(self.track_durations.get(path, 0) for path in self.playlist[self.current_index:])
            self.update_folder_info(remaining_seconds=remaining_seconds)

        if self.last_played is not None and self.last_played in self.playlist:
            last_row = self.playlist.index(self.last_played)
            if last_row < self.file_list.count():
                self.file_list.item(last_row).setBackground(QColor("#1e1e1e"))
                self.file_list.item(last_row).setForeground(QColor("#eee"))

        self.current_playing = self.playlist[index]
        self.current_index = index
        self.file_list.setCurrentRow(index)
        if index < self.file_list.count():
            self.file_list.item(index).setBackground(QColor("#2a4a2a"))
            self.file_list.item(index).setForeground(QColor("#fff"))
        self.last_played = self.current_playing

    def play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.is_paused = True
            logger.debug("Paused playback")
            if self.current_playing:
                self.now_playing_label.setText(f"AudioSetlist: Paused: {os.path.basename(self.current_playing)}")
        else:
            if self.current_index == -1 and self.playlist:
                self.current_index = 0
                self.play_track(0)
            else:
                if self.current_playing is not None:
                    self.player.play()
                    self.is_paused = False
                    logger.debug("Resumed playback")
                    self.now_playing_label.setText(f"AudioSetlist: Now Playing: {os.path.basename(self.current_playing)}")

    def stop(self):
        self.player.stop()
        self.is_paused = False
        if self.current_playing and self.current_playing in self.playlist:
            row = self.playlist.index(self.current_playing)
            if row < self.file_list.count():
                self.file_list.item(row).setBackground(QColor("#1e1e1e"))
                self.file_list.item(row).setForeground(QColor("#eee"))
        self.now_playing_label.setText("AudioSetlist: Now Playing: ")
        self.update_folder_info()
        logger.debug("Player stopped, state: %s", self.player.get_state())

    def prev_track(self):
        current_order = self.get_current_playlist_order()
        if current_order:
            if self.current_index > 0:
                current_file = self.playlist[self.current_index]
                current_pos = current_order.index(current_file)
                if current_pos > 0:
                    prev_file = current_order[current_pos - 1]
                    self.current_index = self.playlist.index(prev_file)
                elif self.loop_playlist:
                    prev_file = current_order[-1]
                    self.current_index = self.playlist.index(prev_file)
            elif self.loop_playlist and self.playlist:
                self.current_index = len(self.playlist) - 1
            self.play_track(self.current_index)

    def next_track(self):
        current_order = self.get_current_playlist_order()
        if current_order:
            if self.current_index < len(self.playlist) - 1:
                current_file = self.playlist[self.current_index]
                current_pos = current_order.index(current_file)
                if current_pos < len(current_order) - 1:
                    next_file = current_order[current_pos + 1]
                    self.current_index = self.playlist.index(next_file)
                else:
                    self.current_index = self.playlist.index(current_order[0])
            elif self.loop_playlist:
                self.current_index = 0
            logger.debug("Moving to next track: %d", self.current_index)
            self.play_track(self.current_index)
        else:
            self.stop()

    def filter_files(self, text):
        self.update_file_list()

    def refresh_songlist(self):
        if not hasattr(self, 'current_folder') or not self.current_folder:
            QMessageBox.warning(self, "AudioSetlist", "No folder selected. Please select a folder first.")
            return

        current_playing = self.current_playing
        current_index = self.current_index

        self.scan_folder(self.current_folder)

        if current_playing and current_playing in self.playlist:
            self.current_index = self.playlist.index(current_playing)
            self.current_playing = current_playing
            if self.current_index < self.file_list.count():
                self.file_list.setCurrentRow(self.current_index)
                self.file_list.item(self.current_index).setBackground(QColor("#2a4a2a"))
                self.file_list.item(self.current_index).setForeground(QColor("#fff"))
            self.now_playing_label.setText(f"AudioSetlist: Now Playing: {os.path.basename(current_playing)}")
            if self.current_index >= 0:
                remaining_seconds = sum(self.track_durations.get(path, 0) for path in self.playlist[self.current_index:])
                self.update_folder_info(remaining_seconds=remaining_seconds)
        else:
            self.current_playing = None
            self.current_index = -1
            self.now_playing_label.setText("AudioSetlist: Now Playing: ")
            self.update_folder_info()

        QMessageBox.information(self, "AudioSetlist", "Songlist refreshed. Currently playing song preserved.")

    def rename_all(self):
        # Save current state to undo stack
        self.rename_undo_stack.append((self.playlist.copy(), self.track_durations.copy()))
        if len(self.rename_undo_stack) > self.max_rename_steps:
            self.rename_undo_stack.pop(0)
        self.rename_redo_stack.clear()

        current_order = self.get_current_playlist_order()
        self.playlist = current_order.copy()
        errors = []

        # Get the start index from the input, default to 1 if invalid
        try:
            start_index = int(self.start_index_input.text())
        except ValueError:
            start_index = 1

        for i, file in enumerate(self.playlist):
            dirname, basename = os.path.split(file)
            name, ext = self.split_filename_ext(basename)

            # Strip any existing index (e.g., "0001_song.mp3" or "0001 song.mp3" -> "song.mp3")
            name = re.sub(r'^\d+[_ ]', '', name)

            new_basename = f"{start_index + i:03d}_{name}{ext}"
            new_path = os.path.join(dirname, new_basename)
            if file != new_path:
                try:
                    if os.path.exists(new_path):
                        errors.append(f"Destination exists: {new_basename}")
                        continue
                    os.rename(file, new_path)
                    self.playlist[i] = new_path
                    if file in self.track_durations:
                        self.track_durations[new_path] = self.track_durations.pop(file)
                except PermissionError:
                    errors.append(f"Permission denied: {basename}")
                except OSError as e:
                    errors.append(f"Failed to rename {basename}: {e}")
                except Exception as e:
                    errors.append(f"Unexpected error with {basename}: {e}")
        self.update_file_list()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        if errors:
            QMessageBox.warning(self, "AudioSetlist", "Some files could not be renamed:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "AudioSetlist", "All files have been renamed according to the current visual order.")

    def rename_selected_file(self):
        # Save current state to undo stack
        self.rename_undo_stack.append((self.playlist.copy(), self.track_durations.copy()))
        if len(self.rename_undo_stack) > self.max_rename_steps:
            self.rename_undo_stack.pop(0)
        self.rename_redo_stack.clear()

        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "AudioSetlist", "Please select a file to rename.")
            return
        item = selected_items[0]
        row = self.file_list.row(item)
        if row < 0:
            return

        # Get the visible (filtered) filename
        visible_filename = item.text()
        # Find the actual file path in the full playlist
        matching_files = [f for f in self.playlist if os.path.basename(f) == visible_filename]
        if not matching_files:
            QMessageBox.warning(self, "AudioSetlist Error", "Selected file not found in playlist.")
            return
        file_path = matching_files[0]

        dirname, basename = os.path.split(file_path)
        name, ext = self.split_filename_ext(basename)
        new_name, ok = QInputDialog.getText(
            self, "AudioSetlist: Rename File", "Enter new filename:", text=name
        )
        if ok and new_name:
            new_basename = f"{new_name}{ext}"
            new_path = os.path.join(dirname, new_basename)
            try:
                if os.path.exists(new_path):
                    QMessageBox.warning(self, "AudioSetlist Error", f"Destination file already exists: {new_basename}")
                    return
                os.rename(file_path, new_path)
                # Update playlist and track_durations
                index = self.playlist.index(file_path)
                self.playlist[index] = new_path
                if file_path in self.track_durations:
                    self.track_durations[new_path] = self.track_durations.pop(file_path)
                self.update_file_list()
                if self.current_playing == file_path:
                    self.current_playing = new_path
                    self.now_playing_label.setText(f"AudioSetlist: Now Playing: {os.path.basename(new_path)}")
            except PermissionError:
                QMessageBox.warning(self, "AudioSetlist Error", f"Permission denied: {basename}")
            except OSError as e:
                QMessageBox.warning(self, "AudioSetlist Error", f"Failed to rename file: {e}")
            except Exception as e:
                QMessageBox.warning(self, "AudioSetlist Error", f"Unexpected error: {e}")

    def scroll_to_playing(self):
        if self.current_playing is None or self.current_playing not in self.playlist:
            return
        row = self.playlist.index(self.current_playing)
        if row < self.file_list.count():
            self.file_list.setCurrentRow(row)
            self.file_list.scrollToItem(self.file_list.item(row))

    def seek(self, position):
        if self.player.get_media():
            self.player.set_time(int(self.player.get_length() * position / 1000))

    def set_volume(self, volume):
        self.player.audio_set_volume(volume)

    def update_progress(self):
        if self.player.get_media():
            length = self.player.get_length()
            time = self.player.get_time()
            if length > 0:
                self.progress_slider.setValue(int((time / length) * 1000))
            mins, secs = divmod(time // 1000, 60)
            duration_mins, duration_secs = divmod(length // 1000, 60)
            self.time_info.setText(f"{mins:02d}:{secs:02d} / {duration_mins:02d}:{duration_secs:02d}")

            # Update remaining time and finish time
            if self.current_index >= 0:
                remaining_seconds = sum(self.track_durations.get(path, 0) for path in self.playlist[self.current_index:])
                remaining_seconds -= (time // 1000)
                self.update_folder_info(remaining_seconds=remaining_seconds)
        else:
            self.time_info.setText("00:00 / 00:00")

    # --- Undo/Redo for Playlist Reordering ---
    def undo_playlist_reorder(self):
        if not self.undo_stack:
            return
        # Save current state to redo stack
        self.redo_stack.append(self.playlist.copy())
        # Restore previous state
        self.playlist = self.undo_stack.pop()
        self.update_file_list()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        logger.debug("Undid playlist reorder")

    def redo_playlist_reorder(self):
        if not self.redo_stack:
            return
        # Save current state to undo stack
        self.undo_stack.append(self.playlist.copy())
        # Restore next state
        self.playlist = self.redo_stack.pop()
        self.update_file_list()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        logger.debug("Redid playlist reorder")

    # --- Undo/Redo for File Renaming ---
    def undo_rename(self):
        if not self.rename_undo_stack:
            return
        # Save current state to redo stack
        self.rename_redo_stack.append((self.playlist.copy(), self.track_durations.copy()))
        # Restore previous state
        old_playlist, old_durations = self.rename_undo_stack.pop()
        # Revert file names on disk
        for old_path, new_path in zip(old_playlist, self.playlist):
            if old_path != new_path and os.path.exists(new_path):
                try:
                    os.rename(new_path, old_path)
                except Exception as e:
                    logger.error(f"Failed to revert rename: {e}")
        # Restore playlist and durations
        self.playlist = old_playlist
        self.track_durations = old_durations
        self.update_file_list()
        logger.debug("Undid rename operation")

    def redo_rename(self):
        if not self.rename_redo_stack:
            return
        # Save current state to undo stack
        self.rename_undo_stack.append((self.playlist.copy(), self.track_durations.copy()))
        # Restore next state
        new_playlist, new_durations = self.rename_redo_stack.pop()
        # Reapply file names on disk
        for old_path, new_path in zip(self.playlist, new_playlist):
            if old_path != new_path and os.path.exists(old_path):
                try:
                    os.rename(old_path, new_path)
                except Exception as e:
                    logger.error(f"Failed to redo rename: {e}")
        # Restore playlist and durations
        self.playlist = new_playlist
        self.track_durations = new_durations
        self.update_file_list()
        logger.debug("Redid rename operation")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())
