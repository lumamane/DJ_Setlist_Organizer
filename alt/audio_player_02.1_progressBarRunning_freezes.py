import os
import sys
import vlc
import re
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem, QMessageBox, QSlider
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

        # Attach to available VLC events
        self.attach_vlc_events()

        # UI
        self.setup_ui()
        self.current_playing = None
        self.last_played = None
        self.playlist = []  # Stores full paths
        self.visual_order = []  # Stores the current visual order
        self.current_index = -1
        self.is_paused = False
        self.loop_playlist = True

        # Timer to check player state (fallback)
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_player_state)
        self.state_timer.start(500)  # Check every 500ms

        # Timer to update progress
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(1000)  # Update every second

    def attach_vlc_events(self):
        """Attach to available VLC events"""
        logger.debug("Available VLC events: %s", [attr for attr in dir(vlc.EventType) if "MediaPlayer" in attr])

        try:
            self.player_event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self.on_player_playing)
            logger.info("Attached to MediaPlayerPlaying event")
        except AttributeError:
            logger.warning("MediaPlayerPlaying not available")

        try:
            self.player_event_manager.event_attach(vlc.EventType.MediaPlayerPaused, self.on_player_paused)
            logger.info("Attached to MediaPlayerPaused event")
        except AttributeError:
            logger.warning("MediaPlayerPaused not available")

        try:
            self.player_event_manager.event_attach(vlc.EventType.MediaPlayerStopped, self.on_player_stopped)
            logger.info("Attached to MediaPlayerStopped event")
        except AttributeError:
            logger.warning("MediaPlayerStopped not available")

        try:
            self.player_event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self.on_player_error)
            logger.info("Attached to MediaPlayerEncounteredError event")
        except AttributeError:
            logger.warning("MediaPlayerEncounteredError not available")

        try:
            self.player_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_media_end)
            logger.info("Attached to MediaPlayerEndReached event")
        except AttributeError:
            logger.warning("MediaPlayerEndReached not available")

    def setup_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Folder selection
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
        layout.addWidget(self.folder_btn)

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
                padding: 5px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #3a3a3a;
                color: #fff;
            }
        """)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.file_list.model().rowsMoved.connect(self.on_rows_moved)
        self.file_list.installEventFilter(self)
        layout.addWidget(self.file_list)

        # Track info labels
        self.track_info = QLabel("No track playing")
        self.track_info.setStyleSheet("color: #eee; font-weight: bold;")
        layout.addWidget(self.track_info)
        self.time_info = QLabel("00:00 / 00:00")
        self.time_info.setStyleSheet("color: #eee;")
        layout.addWidget(self.time_info)

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
        controls.addWidget(self.play_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
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

        # Loop toggle button
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
        layout.addWidget(self.loop_btn)

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

        # Renaming
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
        layout.addWidget(self.rename_btn)

    def eventFilter(self, obj, event):
        if obj is self.file_list and event.type() == event.Type.Drop:
            self.on_drop_event(event)
            return True
        return super().eventFilter(obj, event)

    def on_drop_event(self, event):
        """Handle drop event manually if needed"""
        logger.debug("Drop event received")

    def toggle_loop(self):
        """Toggle playlist looping on/off"""
        self.loop_playlist = not self.loop_playlist
        self.loop_btn.setText(f"Loop: {'ON' if self.loop_playlist else 'OFF'}")
        logger.debug("Playlist looping %s", "enabled" if self.loop_playlist else "disabled")

    def check_player_state(self):
        """Check player state periodically and handle transitions"""
        state = self.player.get_state()
        if state == vlc.State.Error:
            self.handle_playback_error()

    def on_player_playing(self, event):
        """Handle player playing event"""
        logger.debug("Player is now playing")
        self.is_paused = False
        if self.current_playing is not None and self.current_playing in self.visual_order:
            row = self.visual_order.index(self.current_playing)
            self.file_list.setCurrentRow(row)
            self.file_list.item(row).setBackground(QColor("#2a4a2a"))
        self.update_track_info()

    def on_player_paused(self, event):
        """Handle player paused event"""
        logger.debug("Player is now paused")
        self.is_paused = True

    def on_player_stopped(self, event):
        """Handle player stopped event"""
        logger.debug("Player is now stopped")
        self.is_paused = False

    def on_player_error(self, event):
        """Handle player error event"""
        logger.error("Player encountered an error")
        self.handle_playback_error()

    def on_media_end(self, event):
        """Called when the current media finishes playing."""
        logger.debug("Media ended event received")
        if not self.is_paused:
            self.next_track()

    def handle_playback_error(self):
        """Handle playback errors gracefully"""
        logger.error("Playback error occurred")
        if self.current_playing in self.visual_order:
            current_index = self.visual_order.index(self.current_playing)
            if current_index < len(self.visual_order) - 1:
                self.next_track()
            elif self.loop_playlist:
                self.play_track(0)
            else:
                self.stop()
                QMessageBox.warning(self, "Playback Error", "Could not play the selected file. Moving to next track.")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.scan_folder(folder)

    def scan_folder(self, folder):
        self.file_list.clear()
        self.playlist = []
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.wav')):
                    self.playlist.append(os.path.join(root, file))
        self.playlist.sort()
        self.visual_order = self.playlist.copy()
        self.update_file_list()
        logger.debug("Scanned %d files", len(self.playlist))

    def update_file_list(self):
        """Update the file list widget with current visual order"""
        self.file_list.clear()
        for file in self.visual_order:
            self.file_list.addItem(os.path.basename(file))

    def on_rows_moved(self, parent, start, end, destination, row):
        """Update visual_order when items are moved"""
        item = self.visual_order.pop(start)
        self.visual_order.insert(destination.row(), item)
        logger.debug("Moved item to new position. New order: %s", [os.path.basename(f) for f in self.visual_order])
        self.update_file_list()

    def play_selected(self, item):
        """Play the selected song, using visual order"""
        visual_index = self.file_list.row(item)
        self.play_track(visual_index)

    def play_track(self, visual_index):
        """Play the track at the given visual index"""
        if not 0 <= visual_index < len(self.visual_order):
            logger.error("Invalid track index: %d", visual_index)
            return
        self.stop()
        try:
            media = self.instance.media_new(self.visual_order[visual_index])
            self.player.set_media(media)
            self.player.play()
            self.is_paused = False
            self.current_playing = self.visual_order[visual_index]
            if self.last_played is not None and self.last_played in self.visual_order:
                last_row = self.visual_order.index(self.last_played)
                self.file_list.item(last_row).setBackground(QColor("#1e1e1e"))
            row = self.visual_order.index(self.current_playing)
            self.file_list.setCurrentRow(row)
            self.file_list.item(row).setBackground(QColor("#2a4a2a"))
            self.last_played = self.current_playing
            logger.info("Playing track %d: %s", visual_index, self.visual_order[visual_index])
            self.update_track_info()
        except Exception as e:
            logger.error("Failed to play track: %s", e)
            self.handle_playback_error()

    def play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.is_paused = True
            logger.debug("Paused playback")
        else:
            if not self.visual_order:
                return
            if self.current_playing is None:
                self.play_track(0)
            else:
                self.player.play()
                self.is_paused = False
                logger.debug("Resumed playback")

    def stop(self):
        self.player.stop()
        self.player.set_media(None)
        self.is_paused = False
        if self.current_playing:
            row = self.visual_order.index(self.current_playing)
            self.file_list.item(row).setBackground(QColor("#1e1e1e"))
        logger.debug("Player stopped")
        self.update_track_info()

    def next_track(self):
        """Play the next track in the visual order"""
        if not self.visual_order:
            return
        if self.current_playing is None:
            self.play_track(0)
            return
        current_index = self.visual_order.index(self.current_playing)
        if current_index < len(self.visual_order) - 1:
            self.play_track(current_index + 1)
        elif self.loop_playlist:
            self.play_track(0)
        else:
            self.stop()

    def prev_track(self):
        """Play the previous track in the visual order"""
        if not self.visual_order:
            return
        if self.current_playing is None:
            return
        current_index = self.visual_order.index(self.current_playing)
        if current_index > 0:
            self.play_track(current_index - 1)
        elif self.loop_playlist:
            self.play_track(len(self.visual_order) - 1)

    def filter_files(self, text):
        self.file_list.clear()
        for file in self.visual_order:
            if text.lower() in os.path.basename(file).lower():
                self.file_list.addItem(os.path.basename(file))

    def rename_all(self):
        """Rename all files with 3-digit prefixes according to their CURRENT VISUAL ORDER"""
        for i, file in enumerate(self.visual_order):
            dirname, basename = os.path.split(file)
            new_basename = re.sub(r'^\d{3}_', '', basename)
            new_name = f"{i:03d}_{new_basename}"
            new_path = os.path.join(dirname, new_name)
            if file != new_path:
                try:
                    os.rename(file, new_path)
                    # Update both playlist and visual_order
                    self.playlist[self.playlist.index(file)] = new_path
                    self.visual_order[i] = new_path
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename {basename}: {e}")
                    return
        self.update_file_list()

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
            self.update_track_info()

    def update_track_info(self):
        if self.current_playing:
            basename = os.path.basename(self.current_playing)
            self.track_info.setText(f"Now Playing: {basename}")
        else:
            self.track_info.setText("No track playing")

        if self.player.get_media():
            length = self.player.get_length() // 1000  # in seconds
            time = self.player.get_time() // 1000
            mins, secs = divmod(time, 60)
            duration_mins, duration_secs = divmod(length, 60)
            self.time_info.setText(f"{mins:02d}:{secs:02d} / {duration_mins:02d}:{duration_secs:02d}")
        else:
            self.time_info.setText("00:00 / 00:00")

    def closeEvent(self, event):
        self.stop()
        self.player.release()
        self.instance.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())
