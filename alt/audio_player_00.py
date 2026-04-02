import os
import sys
import vlc
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QPushButton,
    QVBoxLayout, QWidget, QLineEdit, QLabel, QHBoxLayout, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

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

        # Timer to check player state
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_player_state)
        self.state_timer.start(500)

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
        layout.addWidget(self.file_list)

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

    def toggle_loop(self):
        """Toggle playlist looping on/off"""
        self.loop_playlist = not self.loop_playlist
        self.loop_btn.setText(f"Loop: {'ON' if self.loop_playlist else 'OFF'}")
        print(f"[DEBUG] Playlist looping {'enabled' if self.loop_playlist else 'disabled'}")

    def check_player_state(self):
        """Check player state periodically and handle transitions"""
        state = self.player.get_state()
        if state == vlc.State.Ended and not self.is_paused:
            print("[DEBUG] Player in Ended state, moving to next track")
            self.next_track()
        elif state == vlc.State.Error:
            print("[DEBUG] Player in Error state, attempting to recover")
            if self.current_index < len(self.playlist) - 1:
                self.next_track()
            else:
                self.stop()

    def on_media_end(self, event):
        """Called when the current media finishes playing."""
        print("[DEBUG] on_media_end event received, current state:", self.player.get_state())
        if not self.is_paused:
            QTimer.singleShot(100, self.next_track)

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
        self.update_file_list()
        print(f"[DEBUG] Scanned {len(self.playlist)} files")

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

    def play_selected(self, item):
        # Get current visual order
        current_order = self.get_current_playlist_order()
        # Find the index in the current order
        selected_filename = item.text()
        for i, file in enumerate(current_order):
            if os.path.basename(file) == selected_filename:
                # Find the index in the main playlist
                self.current_index = self.playlist.index(file)
                break
        self.play_track(self.current_index)

    def play_track(self, index):
        if 0 <= index < len(self.playlist):
            self.stop()
            try:
                QTimer.singleShot(100, lambda: self._play_track(index))
            except Exception as e:
                print(f"[ERROR] Failed to play track: {e}")

    def _play_track(self, index):
        """Internal method to play a track with proper state handling"""
        media = self.instance.media_new(self.playlist[index])
        self.player.set_media(media)
        print(f"[DEBUG] Media set for track {index}, state: {self.player.get_state()}")
        self.player.play()
        print(f"[DEBUG] Play called for track {index}, state: {self.player.get_state()}")
        self.is_paused = False
        print(f"[DEBUG] Playing track {index}: {self.playlist[index]}")

        # Update UI highlights
        if self.last_played is not None:
            last_row = self.playlist.index(self.last_played)
            self.file_list.item(last_row).setBackground(QColor("#1e1e1e"))
            self.file_list.item(last_row).setForeground(QColor("#eee"))
        if self.current_playing is not None and self.current_playing != self.playlist[index]:
            self.last_played = self.current_playing
            last_row = self.playlist.index(self.last_played)
            self.file_list.item(last_row).setBackground(QColor("#4a4a2a"))

        self.current_playing = self.playlist[index]
        self.current_index = index
        self.file_list.setCurrentRow(index)
        self.file_list.item(index).setBackground(QColor("#2a4a2a"))
        self.file_list.item(index).setForeground(QColor("#fff"))

    def play_pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.is_paused = True
            print("[DEBUG] Paused playback")
        else:
            if self.current_index == -1 and self.playlist:
                self.current_index = 0
                self.play_track(0)
            else:
                if self.current_playing is not None:
                    self.player.play()
                    self.is_paused = False
                    print("[DEBUG] Resumed playback")

    def stop(self):
        self.player.stop()
        self.is_paused = False
        if self.current_playing:
            row = self.playlist.index(self.current_playing)
            self.file_list.item(row).setBackground(QColor("#1e1e1e"))
            self.file_list.item(row).setForeground(QColor("#eee"))
        print(f"[DEBUG] Player stopped, state: {self.player.get_state()}")

    def prev_track(self):
        current_order = self.get_current_playlist_order()
        if current_order:
            if self.current_index > 0:
                # Find current file in current order
                current_file = self.playlist[self.current_index]
                current_pos = current_order.index(current_file)
                if current_pos > 0:
                    prev_file = current_order[current_pos - 1]
                    self.current_index = self.playlist.index(prev_file)
                elif self.loop_playlist:
                    # Go to last file if at beginning and looping
                    prev_file = current_order[-1]
                    self.current_index = self.playlist.index(prev_file)
            elif self.loop_playlist and self.playlist:
                # If at the beginning and looping is enabled, go to the end
                self.current_index = len(self.playlist) - 1
            self.play_track(self.current_index)

    def next_track(self):
        current_order = self.get_current_playlist_order()
        if current_order:
            if self.current_index < len(self.playlist) - 1:
                # Find current file in current order
                current_file = self.playlist[self.current_index]
                current_pos = current_order.index(current_file)
                if current_pos < len(current_order) - 1:
                    next_file = current_order[current_pos + 1]
                    self.current_index = self.playlist.index(next_file)
                else:
                    # At the end of current order
                    self.current_index = self.playlist.index(current_order[0])
            elif self.loop_playlist:
                # If at the end and looping is enabled, go to the beginning
                self.current_index = 0

            print(f"[DEBUG] Moving to next track: {self.current_index}")
            self.play_track(self.current_index)
        else:
            self.stop()

    def filter_files(self, text):
        self.file_list.clear()
        for file in self.playlist:
            if text.lower() in os.path.basename(file).lower():
                self.file_list.addItem(os.path.basename(file))

    def rename_all(self):
        """
        Renames all files with 3-digit prefixes according to their CURRENT VISUAL ORDER in the list.
        This respects any drag-and-drop reordering the user has done.
        """
        # Get the current visual order from the list widget
        current_order = self.get_current_playlist_order()

        # Update playlist to match current visual order
        self.playlist = current_order.copy()

        # Now rename files according to this order
        for i, file in enumerate(self.playlist):
            dirname, basename = os.path.split(file)
            # Remove existing 3-digit prefix if present
            new_basename = re.sub(r'^\d{3}_', '', basename)
            new_name = f"{i:03d}_{new_basename}"
            new_path = os.path.join(dirname, new_name)

            if file != new_path:
                try:
                    os.rename(file, new_path)
                    # Update the playlist to reflect the new filename
                    self.playlist[i] = new_path
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename {basename}: {e}")
                    return  # Stop if any error occurs

        # Refresh the UI to show the new names
        self.update_file_list()

        # Update current_index if needed
        if self.current_playing in self.playlist:
            self.current_index = self.playlist.index(self.current_playing)

        QMessageBox.information(self, "Success", "All files have been renamed according to the current visual order.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())
