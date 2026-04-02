import os
import sys
import vlc
import re
import logging
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem,
    QMessageBox, QSlider, QInputDialog, QSizePolicy, QProgressDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FolderScanner(QThread):
    progress = pyqtSignal(int, int)  # (current, total)
    finished = pyqtSignal(list, int)  # (playlist, total_seconds)
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
                            total_seconds += duration
                            self.progress.emit(i + 1, len(files))
                        except Exception as e:
                            logger.error(f"Failed to parse {path}: {e}")
            self.finished.emit(playlist, total_seconds)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False

class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio File Manager & Player")
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
            QPushButton {
                box-shadow: 0 2px 3px rgba(0, 0, 0, 0.2);
            }
        """)

        # VLC setup
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.player_event_manager = self.player.event_manager()
        self.player_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_media_end)

        # UI
        self.setup_ui()
        self.current_playing = None
        self.last_played = None
        self.playlist = []  # Stores full paths
        self.current_index = -1
        self.is_paused = False
        self.loop_playlist = True
        self.next_track_pending = False
        self.current_folder = None
        self.track_durations = {}  # Stores duration of each track

        # Status bar
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("Ready")

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
        top_controls.addWidget(self.folder_btn)
        top_controls.addWidget(self.refresh_btn)
        top_controls.addWidget(self.rename_btn)
        top_controls.addWidget(self.rename_one_btn)
        top_controls.addStretch()
        top_controls.addWidget(self.loop_btn)
        layout.addLayout(top_controls)

        # --- Folder Info ---
        self.folder_info = QLabel("Songs in folder: 0 | Total time: 00:00:00 | Remaining: 00:00:00 | Finish: 00:00 | Foldername: ")
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
        self.now_playing_label = QLabel("Now Playing: ")
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
                background-color: #B71C1C;
            }
        """)
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

    # --- Folder Scanner Methods ---
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.current_folder = folder
            self.scan_folder(folder)

    def scan_folder(self, folder):
        self.save_window_state()
        self.file_list.clear()
        self.playlist = []
        self.track_durations = {}

        # Show progress dialog
        self.progress_dialog = QProgressDialog("Scanning folder...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Scanning")
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
        self.statusBar.showMessage("Scanning folder...")

    def update_scan_progress(self, current, total):
        progress = int((current / total) * 100)
        self.progress_dialog.setValue(progress)
        self.statusBar.showMessage(f"Scanning: {progress}%")

    def cancel_scan(self):
        self.scanner.stop()
        self.progress_dialog.close()
        self.statusBar.showMessage("Scan canceled")

    def on_scan_finished(self, playlist, total_seconds):
        self.progress_dialog.close()
        self.playlist = playlist
        self.update_file_list()
        self.update_folder_info(total_seconds=total_seconds)
        self.restore_window_state()
        self.statusBar.showMessage(f"Found {len(playlist)} files")

    def on_scan_error(self, error):
        self.progress_dialog.close()
        QMessageBox.warning(self, "Error", f"Failed to scan folder: {error}")
        self.statusBar.showMessage("Scan error")

    # --- Rest of your methods remain unchanged ---
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
        self.now_playing_label.setText("Now Playing: ")

    def update_folder_info(self, total_seconds=None, remaining_seconds=None):
        """Update the folder info label with folder name, total and remaining time, and expected finish time."""
        if total_seconds is None:
            total_seconds = sum(self.track_durations.values())
        if remaining_seconds is None:
            remaining_seconds = total_seconds

        folder_name = os.path.basename(self.current_folder) if self.current_folder else "No folder selected"
        max_name_length = 40  # Truncate if longer than 40 chars
        if len(folder_name) > max_name_length:
            folder_name = folder_name[:max_name_length-3] + "..."

        songs_count = len(self.playlist)

        total_h = total_seconds // 3600
        total_m = (total_seconds % 3600) // 60
        total_s = total_seconds % 60
        remaining_h = remaining_seconds // 3600
        remaining_m = (remaining_seconds % 3600) // 60
        remaining_s = remaining_seconds % 60

        finish_time = (datetime.datetime.now() + datetime.timedelta(seconds=remaining_seconds)).strftime("%H:%M")

        self.folder_info.setText(
            f"Songs: {songs_count} | "
            f"Total: {total_h:02d}:{total_m:02d}:{total_s:02d} | "
            f"Remaining: {remaining_h:02d}:{remaining_m:02d}:{remaining_s:02d} | "
            f"Finish: {finish_time} | "
            f"Folder: {folder_name}"
        )

    def update_file_list(self):
        """Update the file list widget with current playlist"""
        self.file_list.clear()
        for file in self.playlist:
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

    def on_rows_moved(self, parent, start, end, destination, row):
        """Update the playlist order when items are moved in the GUI"""
        current_order = self.get_current_playlist_order()
        self.playlist = current_order.copy()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        logger.debug("Updated playlist order after drag-and-drop")

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
            QMessageBox.warning(self, "Error", f"Failed to play track: {e}")

    def _play_track(self, index):
        """Internal method to play a track with proper state handling"""
        media = self.instance.media_new(self.playlist[index])
        self.player.set_media(media)
        logger.debug("Media set for track %d, state: %s", index, self.player.get_state())
        self.player.play()
        logger.debug("Play called for track %d, state: %s", index, self.player.get_state())
        self.is_paused = False
        logger.debug("Playing track %d: %s", index, self.playlist[index])

        self.now_playing_label.setText(f"Now Playing: {os.path.basename(self.playlist[index])}")

        if self.current_index >= 0:
            remaining_seconds = sum(self.track_durations[path] for path in self.playlist[self.current_index:])
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
                self.now_playing_label.setText(f"Paused: {os.path.basename(self.current_playing)}")
        else:
            if self.current_index == -1 and self.playlist:
                self.current_index = 0
                self.play_track(0)
            else:
                if self.current_playing is not None:
                    self.player.play()
                    self.is_paused = False
                    logger.debug("Resumed playback")
                    self.now_playing_label.setText(f"Now Playing: {os.path.basename(self.current_playing)}")

    def stop(self):
        self.player.stop()
        self.is_paused = False
        if self.current_playing and self.current_playing in self.playlist:
            row = self.playlist.index(self.current_playing)
            if row < self.file_list.count():
                self.file_list.item(row).setBackground(QColor("#1e1e1e"))
                self.file_list.item(row).setForeground(QColor("#eee"))
        self.now_playing_label.setText("Now Playing: ")
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
        self.file_list.clear()
        for file in self.playlist:
            if text.lower() in os.path.basename(file).lower():
                self.file_list.addItem(os.path.basename(file))

    def refresh_songlist(self):
        if not hasattr(self, 'current_folder') or not self.current_folder:
            QMessageBox.warning(self, "Error", "No folder selected. Please select a folder first.")
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
            self.now_playing_label.setText(f"Now Playing: {os.path.basename(current_playing)}")
            if self.current_index >= 0:
                remaining_seconds = sum(self.track_durations[path] for path in self.playlist[self.current_index:])
                self.update_folder_info(remaining_seconds=remaining_seconds)
        else:
            self.current_playing = None
            self.current_index = -1
            self.now_playing_label.setText("Now Playing: ")
            self.update_folder_info()

        QMessageBox.information(self, "Success", "Songlist refreshed. Currently playing song preserved.")

    def rename_all(self):
        current_order = self.get_current_playlist_order()
        self.playlist = current_order.copy()
        errors = []
        for i, file in enumerate(self.playlist):
            dirname, basename = os.path.split(file)
            new_basename = re.sub(r'^\d{3}_', '', basename)
            new_name = f"{i:03d}_{new_basename}"
            new_path = os.path.join(dirname, new_name)
            if file != new_path:
                try:
                    if os.path.exists(new_path):
                        errors.append(f"Destination exists: {new_name}")
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
            QMessageBox.warning(self, "Partial Success", "Some files could not be renamed:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Success", "All files have been renamed according to the current visual order.")

    def rename_selected_file(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Info", "Please select a file to rename.")
            return
        item = selected_items[0]
        row = self.file_list.row(item)
        if row < 0 or row >= len(self.playlist):
            return
        file_path = self.playlist[row]
        dirname, basename = os.path.split(file_path)
        new_name, ok = QInputDialog.getText(
            self, "Rename File", "Enter new filename:", text=basename
        )
        if ok and new_name:
            new_path = os.path.join(dirname, new_name)
            try:
                if os.path.exists(new_path):
                    QMessageBox.warning(self, "Error", f"Destination file already exists: {new_name}")
                    return
                os.rename(file_path, new_path)
                self.playlist[row] = new_path
                if file_path in self.track_durations:
                    self.track_durations[new_path] = self.track_durations.pop(file_path)
                self.update_file_list()
                if self.current_playing == file_path:
                    self.current_playing = new_path
                    self.now_playing_label.setText(f"Now Playing: {os.path.basename(new_path)}")
            except PermissionError:
                QMessageBox.warning(self, "Error", f"Permission denied: {basename}")
            except OSError as e:
                QMessageBox.warning(self, "Error", f"Failed to rename file: {e}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Unexpected error: {e}")

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
            if self.current_index >= 0:
                remaining_seconds = sum(self.track_durations[path] for path in self.playlist[self.current_index:])
                remaining_seconds -= (time // 1000)
                remaining_h = remaining_seconds // 3600
                remaining_m = (remaining_seconds % 3600) // 60
                remaining_s = remaining_seconds % 60
                total_seconds = sum(self.track_durations.values())
                total_h = total_seconds // 3600
                total_m = (total_seconds % 3600) // 60
                total_s = total_seconds % 60
                finish_time = (datetime.datetime.now() + datetime.timedelta(seconds=remaining_seconds)).strftime("%H:%M")
                self.update_folder_info(
                    total_seconds=total_seconds,
                    remaining_seconds=remaining_seconds
                )
        else:
            self.time_info.setText("00:00 / 00:00")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())
