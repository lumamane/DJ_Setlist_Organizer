import os
import sys
import vlc
import re
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem,
    QMessageBox, QSlider, QInputDialog, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio File Manager & Player")
        self.setGeometry(100, 100, 800, 600)

        # Set dark palette for the whole app
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #eee;
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

        # Timer to check player state (fallback)
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_player_state)
        self.state_timer.start(500)

        # Timer to update progress
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(1000)  # Update every second

    def setup_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top controls (horizontal layout)
        top_controls = QHBoxLayout()
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        self.folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        top_controls.addWidget(self.folder_btn)

        self.refresh_btn = QPushButton("Refresh Songlist")
        self.refresh_btn.clicked.connect(self.refresh_songlist)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFC107;
                color: black;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #FFB300;
            }
        """)
        top_controls.addWidget(self.refresh_btn)

        self.loop_btn = QPushButton("Loop: ON")
        self.loop_btn.clicked.connect(self.toggle_loop)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
        """)
        top_controls.addWidget(self.loop_btn)

        self.rename_btn = QPushButton("Rename All Files")
        self.rename_btn.clicked.connect(self.rename_all)
        self.rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
        """)
        top_controls.addWidget(self.rename_btn)

        self.rename_one_btn = QPushButton("Rename File")
        self.rename_one_btn.clicked.connect(self.rename_selected_file)
        self.rename_one_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
        """)
        top_controls.addWidget(self.rename_one_btn)

        layout.addLayout(top_controls)

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
        layout.addWidget(self.file_list)

        # Info labels (grid layout for alignment)
        info_grid = QGridLayout()

        self.folder_info = QLabel("Folder: 00:00:00 | Remaining: 00:00:00")
        self.folder_info.setStyleSheet("color: #eee; font-weight: bold;")
        info_grid.addWidget(self.folder_info, 0, 0)

        self.time_info = QLabel("00:00 / 00:00")
        self.time_info.setStyleSheet("color: #eee; font-weight: bold;")
        info_grid.addWidget(self.time_info, 1, 0)

        self.track_info = QLabel("Ready to play")
        self.track_info.setStyleSheet("color: #eee; font-weight: bold;")
        info_grid.addWidget(self.track_info, 1,1)

        layout.addLayout(info_grid)

        # Playback controls
        controls = QHBoxLayout()
        self.play_btn = QPushButton("Play/Pause")
        self.play_btn.clicked.connect(self.play_pause)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_track)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_track)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.scroll_to_playing_btn = QPushButton("Scroll to Playing")
        self.scroll_to_playing_btn.clicked.connect(self.scroll_to_playing)
        self.scroll_to_playing_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7b1fa2;
            }
        """)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.scroll_to_playing_btn)
        layout.addLayout(controls)

        # Progress and volume sliders
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderMoved.connect(self.seek)
        layout.addWidget(self.progress_slider)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        layout.addWidget(self.volume_slider)

        # Search
        self.search_box = QLineEdit()
        self.search_box.textChanged.connect(self.filter_files)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: #eee;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 6px;
            }
        """)
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #eee;")
        layout.addWidget(search_label)
        layout.addWidget(self.search_box)

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

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.current_folder = folder
            self.scan_folder(folder)

    def scan_folder(self, folder):
        self.file_list.clear()
        self.playlist = []
        self.track_durations = {}
        total_seconds = 0
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.wav')):
                    path = os.path.join(root, file)
                    self.playlist.append(path)
                    media = self.instance.media_new(path)
                    media.parse()
                    duration = media.get_duration() // 1000  # in seconds
                    self.track_durations[path] = duration
                    total_seconds += duration
        self.playlist.sort()
        self.update_file_list()
        self.update_folder_info(total_seconds)
        logger.debug("Scanned %d files", len(self.playlist))

    def update_folder_info(self, total_seconds=None, remaining_seconds=None):
        """Update the folder info label with total and remaining time."""
        if total_seconds is None:
            total_seconds = sum(self.track_durations.values())
        if remaining_seconds is None:
            remaining_seconds = total_seconds

        total_h = total_seconds // 3600
        total_m = (total_seconds % 3600) // 60
        total_s = total_seconds % 60
        remaining_h = remaining_seconds // 3600
        remaining_m = (remaining_seconds % 3600) // 60
        remaining_s = remaining_seconds % 60
        self.folder_info.setText(
            f"Folder: {total_h:02d}:{total_m:02d}:{total_s:02d} | "
            f"Remaining: {remaining_h:02d}:{remaining_m:02d}:{remaining_s:02d}"
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
            # Find the full path in playlist that matches this filename
            for file in self.playlist:
                if os.path.basename(file) == filename:
                    current_order.append(file)
                    break
        return current_order

    def on_rows_moved(self, parent, start, end, destination, row):
        """Update the playlist order when items are moved in the GUI"""
        # Get the current visual order from the GUI
        current_order = self.get_current_playlist_order()
        # Update the playlist to match the new order
        self.playlist = current_order.copy()
        # Update the current_index if needed
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
        if 0 <= index < len(self.playlist):
            self.stop()
            try:
                QTimer.singleShot(100, lambda: self._play_track(index))
            except Exception as e:
                logger.error("Failed to play track: %s", e)

    def _play_track(self, index):
        """Internal method to play a track with proper state handling"""
        media = self.instance.media_new(self.playlist[index])
        self.player.set_media(media)
        logger.debug("Media set for track %d, state: %s", index, self.player.get_state())
        self.player.play()
        logger.debug("Play called for track %d, state: %s", index, self.player.get_state())
        self.is_paused = False
        logger.debug("Playing track %d: %s", index, self.playlist[index])

        # Update track info label
        self.track_info.setText(os.path.basename(self.playlist[index]))

        # Update remaining time
        if self.current_index >= 0:
            remaining_seconds = sum(self.track_durations[path] for path in self.playlist[self.current_index:])
            self.update_folder_info(remaining_seconds=remaining_seconds)

        # Update UI highlights
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
            # Update label to show paused track
            if self.current_playing:
                self.track_info.setText(f"Paused: {os.path.basename(self.current_playing)}")
        else:
            if self.current_index == -1 and self.playlist:
                self.current_index = 0
                self.play_track(0)
            else:
                if self.current_playing is not None:
                    self.player.play()
                    self.is_paused = False
                    logger.debug("Resumed playback")
                    # Update label to show playing track
                    self.track_info.setText(os.path.basename(self.current_playing))

    def stop(self):
        self.player.stop()
        self.is_paused = False
        if self.current_playing and self.current_playing in self.playlist:
            row = self.playlist.index(self.current_playing)
            if row < self.file_list.count():
                self.file_list.item(row).setBackground(QColor("#1e1e1e"))
                self.file_list.item(row).setForeground(QColor("#eee"))
        self.track_info.setText("Ready to play")
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

        # Remember the currently playing song and its index
        current_playing = self.current_playing
        current_index = self.current_index

        # Rescan the folder
        self.scan_folder(self.current_folder)

        # Restore the currently playing song and index
        if current_playing and current_playing in self.playlist:
            self.current_index = self.playlist.index(current_playing)
            self.current_playing = current_playing
            # Highlight the currently playing song in the list
            if self.current_index < self.file_list.count():
                self.file_list.setCurrentRow(self.current_index)
                self.file_list.item(self.current_index).setBackground(QColor("#2a4a2a"))
                self.file_list.item(self.current_index).setForeground(QColor("#fff"))
            self.track_info.setText(os.path.basename(current_playing))
            # Update remaining time
            if self.current_index >= 0:
                remaining_seconds = sum(self.track_durations[path] for path in self.playlist[self.current_index:])
                self.update_folder_info(remaining_seconds=remaining_seconds)
        else:
            self.current_playing = None
            self.current_index = -1
            self.track_info.setText("Ready to play")
            self.update_folder_info()

        QMessageBox.information(self, "Success", "Songlist refreshed. Currently playing song preserved.")

    def rename_all(self):
        """
        Renames all files with 3-digit prefixes according to their CURRENT VISUAL ORDER in the list.
        This respects any drag-and-drop reordering the user has done.
        """
        current_order = self.get_current_playlist_order()
        self.playlist = current_order.copy()
        for i, file in enumerate(self.playlist):
            dirname, basename = os.path.split(file)
            new_basename = re.sub(r'^\d{3}_', '', basename)
            new_name = f"{i:03d}_{new_basename}"
            new_path = os.path.join(dirname, new_name)
            if file != new_path:
                try:
                    os.rename(file, new_path)
                    self.playlist[i] = new_path
                    # Update track_durations with new path
                    if file in self.track_durations:
                        self.track_durations[new_path] = self.track_durations.pop(file)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename {basename}: {e}")
                    return
        self.update_file_list()
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)
        QMessageBox.information(self, "Success", "All files have been renamed according to the current visual order.")

    def rename_selected_file(self):
        """Rename the last clicked (selected) file."""
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
                os.rename(file_path, new_path)
                self.playlist[row] = new_path
                # Update track_durations with new path
                if file_path in self.track_durations:
                    self.track_durations[new_path] = self.track_durations.pop(file_path)
                self.update_file_list()
                if self.current_playing == file_path:
                    self.current_playing = new_path
                    self.track_info.setText(os.path.basename(new_path))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename file: {e}")

    def scroll_to_playing(self):
        """Scroll the list to make the currently playing song visible and highlight it."""
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
            # Update remaining time as we play
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
                self.folder_info.setText(
                    f"Folder: {total_h:02d}:{total_m:02d}:{total_s:02d} | "
                    f"Remaining: {remaining_h:02d}:{remaining_m:02d}:{remaining_s:02d}"
                )
        else:
            self.time_info.setText("00:00 / 00:00")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())
