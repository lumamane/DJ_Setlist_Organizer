import os
import re
import sys
import json
import io
import numpy as np
import pandas as pd
import time
from threading import Thread, Event
from collections import deque
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
    QTableView, QLabel, QLineEdit, QMessageBox, QFileDialog, QProgressDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData, QByteArray, QTimer
from PyQt6.QtGui import QDrag
import sounddevice as sd
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# Pale Moon color palette
PALE_MOON_BLUE = "#82B5E8"
PALE_MOON_GREEN = "#8AE234"
PALE_MOON_RED = "#EF2929"
PALE_MOON_ORANGE = "#FCAF3E"
PALE_MOON_PURPLE = "#AD7FA8"

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.ogg', '.flac')

# --- Audio Player Class ---
class AudioPlayer(Thread):
    def __init__(self, filepath):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.stop_event = Event()
        self.pause_event = Event()
        self.pause_event.set()
        self.data = None
        self.fs = 44100
        self.channels = 1
        self.position = 0
        self.duration = 0
        self._is_playing = False
        self.playback_success = True

    def run(self):
        try:
            print(f"[AUDIO] Default device: {sd.default.device}")
            print(f"[AUDIO] Loading: {self.filepath}")
            print(f"[AUDIO] New player created id={id(self)}, stop_event initial={self.stop_event.is_set()}")
            print(f"[AUDIO] stop_event state at start: {self.stop_event.is_set()}")

            # Try to load the file with timeout
            sound = None
            try:
                # Use a simple approach first
                sound = AudioSegment.from_file(self.filepath)
            except CouldntDecodeError:
                # If that fails, try a more direct approach
                try:
                    import subprocess
                    cmd = [
                        "ffmpeg", "-i", self.filepath,
                        "-f", "wav", "-"
                    ]
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    data, _ = proc.communicate(timeout=5)  # Add timeout

                    if proc.returncode != 0:
                        raise CouldntDecodeError(f"FFmpeg failed with code {proc.returncode}")

                    # Create AudioSegment from raw WAV data
                    sound = AudioSegment.from_file(io.BytesIO(data), format="wav")
                except Exception as e:
                    raise CouldntDecodeError(f"Failed to decode file: {str(e)}")

            if sound.frame_rate != self.fs:
                sound = sound.set_frame_rate(self.fs)
                print(f"[AUDIO] Resampled to {self.fs}Hz")

            samples = np.array(sound.get_array_of_samples(), dtype=np.float32) / 32768.0

            current_max = np.max(np.abs(samples))
            if current_max < 0.1 and current_max > 0:
                samples = samples * (0.9 / current_max)
                print(f"[AUDIO] Normalized volume to {np.max(np.abs(samples)):.3f}")

            if sound.channels == 2:
                samples = samples.reshape((-1, 2))
                self.channels = 2
            else:
                samples = samples.reshape((-1, 1))
                self.channels = 1

            self.data = samples
            self.fs = sound.frame_rate
            self.duration = len(self.data) / self.fs
            self._is_playing = True
            print(f"[AUDIO] Playing: {self.duration:.2f}s, {self.channels}ch, {self.fs}Hz")
            print(f"[AUDIO] stop_event before stream: {self.stop_event.is_set()}, pause_event: {self.pause_event.is_set()}")

            # Create stream
            stream = sd.OutputStream(
                samplerate=self.fs,
                channels=self.channels,
                callback=self._callback,
                blocksize=512,
                dtype='float32',
                latency='low'
            )
            print(f"[AUDIO] Stream created, starting...")
            stream.start()
            print(f"[AUDIO] Stream started, active={stream.active}, stop_event={self.stop_event.is_set()}")
            
            # Wait for playback to complete
            loop_count = 0
            while not self.stop_event.is_set() and self._is_playing:
                loop_count += 1
                if loop_count % 10 == 0:
                    print(f"[AUDIO] Loop #{loop_count}: _is_playing={self._is_playing}, stop_event={self.stop_event.is_set()}, callbacks={getattr(self, '_callback_count', 0)}")
                sd.sleep(100)
            
            print(f"[AUDIO] Stopping stream, _is_playing={self._is_playing}, stop_event={self.stop_event.is_set()}, callbacks={getattr(self, '_callback_count', 0)}")
            stream.stop()
            stream.close()
            self._is_playing = False
            print("[AUDIO] Playback completed")
        except CouldntDecodeError as e:
            print(f"[AUDIO] Couldn't decode file: {e}")
            self.playback_success = False
            self._is_playing = False
        except Exception as e:
            print(f"[AUDIO] Error: {e}")
            import traceback
            traceback.print_exc()
            self.playback_success = False
            self._is_playing = False

    def _callback(self, outdata, frames, time, status):
        if status:
            print(f"[AUDIO] Callback status: {status}")
        
        if not hasattr(self, '_callback_count'):
            self._callback_count = 0
        self._callback_count += 1
        
        if self._callback_count % 100 == 0:  # Print every 100 callbacks to avoid spam
            print(f"[AUDIO] Callback #{self._callback_count}: pause_event={self.pause_event.is_set()}, pos={self.position}, data_len={len(self.data) if self.data is not None else 'None'}")
        
        if not self.pause_event.is_set():
            outdata.fill(0)
            return
        
        if self.data is None:
            outdata.fill(0)
            return
        
        remaining = len(self.data) - self.position
        if remaining <= 0:
            outdata.fill(0)
            self._is_playing = False
            print(f"[AUDIO] Callback: playback finished at position {self.position}")
            return

        chunk = self.data[self.position:self.position + frames]
        self.position += len(chunk)

        if len(chunk) < frames:
            outdata[:len(chunk)] = chunk
            outdata[len(chunk):].fill(0)
            self._is_playing = False
        else:
            outdata[:] = chunk

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def stop(self):
        self.stop_event.set()
        self._is_playing = False
        sd.stop()

    @property
    def is_playing(self):
        return self._is_playing

# --- Data Model ---
class SongTableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data.copy()

    def rowCount(self, index):
        return len(self._data)

    def columnCount(self, index):
        return len(self._data.columns)

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            try:
                return str(self._data.iloc[index.row(), index.column()])
            except (IndexError, KeyError):
                return ""
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            try:
                return self._data.columns[section]
            except:
                return ""
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled

# --- Main App ---
class DJApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App")
        self.setGeometry(100, 100, 1200, 600)

        sd.default.samplerate = None
        sd.default.dtype = 'float32'

        self.df = pd.DataFrame(columns=[
            "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
        ])
        self.song_model = SongTableModel(self.df)
        self.current_playing = None
        self.current_folder_path = None
        self.player = None
        self.song_table = None
        self.failed_songs = set()  # Track failed songs to prevent infinite retry

        # Read last session path but defer loading until UI exists
        self._last_folder_to_load = None
        try:
            settings_path = os.path.join(os.path.dirname(__file__), 'last_session.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    last = data.get('last_folder')
                    if last and os.path.isdir(last):
                        self._last_folder_to_load = last
        except Exception as e:
            print(f"[SESSION] Could not load last session: {e}")

        self.undo_stack = deque(maxlen=10)
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.check_playback_status)

        self.init_ui()

        # Load last folder after UI has been created
        if getattr(self, '_last_folder_to_load', None):
            try:
                self.current_folder_path = self._last_folder_to_load
                self.load_folder_metadata(self.current_folder_path)
            except Exception as e:
                print(f"[SESSION] Could not load folder after init: {e}")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top controls
        top_controls = QHBoxLayout()
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        top_controls.addWidget(self.folder_btn)

        # Playback buttons with colors
        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self.play_prev)
        self.prev_btn.setStyleSheet(f"background-color: {PALE_MOON_ORANGE}; color: black;")

        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_selected)
        self.play_btn.setStyleSheet(f"background-color: {PALE_MOON_GREEN}; color: black;")

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_playback)
        self.pause_btn.setStyleSheet(f"background-color: {PALE_MOON_PURPLE}; color: black;")

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_playback)
        self.stop_btn.setStyleSheet(f"background-color: {PALE_MOON_RED}; color: black;")

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setStyleSheet(f"background-color: {PALE_MOON_ORANGE}; color: black;")

        top_controls.addWidget(self.prev_btn)
        top_controls.addWidget(self.play_btn)
        top_controls.addWidget(self.pause_btn)
        top_controls.addWidget(self.stop_btn)
        top_controls.addWidget(self.next_btn)

        layout.addLayout(top_controls)

        # Now Playing label
        self.now_playing_label = QLabel("Now Playing: None")
        layout.addWidget(self.now_playing_label)

        # Song table
        self.song_table = QTableView()
        self.song_table.setModel(self.song_model)
        self.song_table.setDragDropMode(QTableView.DragDropMode.InternalMove)
        self.song_table.setDragEnabled(True)
        self.song_table.setAcceptDrops(True)
        self.song_table.setDropIndicatorShown(True)
        self.song_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.song_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.song_table.setDragDropOverwriteMode(False)

        # Set column widths
        header = self.song_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.song_table.setColumnWidth(0, 60)   # index
        self.song_table.setColumnWidth(1, 60)   # type
        self.song_table.setColumnWidth(2, 300)  # songfile
        self.song_table.setColumnWidth(3, 50)   # ext
        self.song_table.setColumnWidth(4, 400)  # Filename
        self.song_table.setColumnWidth(5, 400)  # alterFilenameTo

        # Connect double-click to play song
        self.song_table.doubleClicked.connect(self.on_song_double_clicked)

        self.song_table.model().rowsMoved.connect(self.on_rows_moved)
        layout.addWidget(self.song_table)

        # Bottom controls
        bottom_controls = QHBoxLayout()
        self.index_start_edit = QLineEdit("1")
        self.index_btn = QPushButton("Index")
        self.index_btn.clicked.connect(self.set_indices)
        self.save_btn = QPushButton("Save Filenames")
        self.save_btn.clicked.connect(self.save_filenames)
        self.undo_btn = QPushButton("Undo Rename")
        self.undo_btn.clicked.connect(self.undo_rename)
        bottom_controls.addWidget(QLabel("Start Index:"))
        bottom_controls.addWidget(self.index_start_edit)
        bottom_controls.addWidget(self.index_btn)
        bottom_controls.addWidget(self.save_btn)
        bottom_controls.addWidget(self.undo_btn)
        layout.addLayout(bottom_controls)

        # Keyboard shortcuts
        self.play_btn.setShortcut("Space")
        self.next_btn.setShortcut("Right")
        self.prev_btn.setShortcut("Left")
        self.stop_btn.setShortcut("S")

    def on_song_double_clicked(self, index):
        """Handle double-click on a song to play it"""
        if index.isValid():
            row = index.row()
            if 0 <= row < len(self.df):
                self.play_song(row)

    def check_playback_status(self):
        """Check if current playback has finished and play next song"""
        if hasattr(self, 'player') and self.player and hasattr(self.player, 'is_alive') and self.player.is_alive():
            if not self.player.is_playing:
                self.play_next()
        else:
            self.playback_timer.stop()

    def on_rows_moved(self, parent, start, end, destination, row):
        """Handle row reordering in the table"""
        if start < 0 or start >= len(self.df) or destination < 0 or destination > len(self.df):
            return

        current_filename = None
        if self.current_playing is not None and 0 <= self.current_playing < len(self.df):
            try:
                current_filename = self.df.iloc[self.current_playing]["Filename"]
            except (IndexError, KeyError):
                current_filename = None

        # Create new DataFrame with reordered rows
        new_df = self.df.copy()
        row_to_move = new_df.iloc[[start]]
        remaining = new_df.drop(index=start)

        if destination <= start:
            new_df = pd.concat([
                remaining.iloc[:destination],
                row_to_move,
                remaining.iloc[destination:]
            ], ignore_index=True)
        else:
            new_df = pd.concat([
                remaining.iloc[:destination-1],
                row_to_move,
                remaining.iloc[destination-1:]
            ], ignore_index=True)

        self.df = new_df
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)

        if current_filename:
            try:
                matching = self.df[self.df["Filename"] == current_filename]
                if not matching.empty:
                    self.current_playing = matching.index[0]
                    self.song_table.selectRow(self.current_playing)
                else:
                    self.current_playing = None
                    self.now_playing_label.setText("Now Playing: None")
            except Exception as e:
                print(f"Error updating current playing position: {e}")
                self.current_playing = None
                self.now_playing_label.setText("Now Playing: None")

    def play_selected(self):
        """Play the selected song"""
        selected = self.song_table.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "Warning", "No song selected.")
            return

        row = selected[0].row()
        if 0 <= row < len(self.df):
            self.play_song(row)

    def play_next(self):
        """Play the next song in the list"""
        if len(self.df) == 0:
            return

        if self.current_playing is None:
            self.current_playing = 0
        else:
            self.current_playing = (self.current_playing + 1) % len(self.df)

        # Skip songs that already failed (defensive: handle missing attribute)
        failed = getattr(self, 'failed_songs', set())
        attempts = 0
        max_attempts = len(self.df)
        while attempts < max_attempts:
            if self.current_playing not in failed:
                break
            self.current_playing = (self.current_playing + 1) % len(self.df)
            attempts += 1

        if attempts >= max_attempts:
            self.now_playing_label.setText("All songs failed to load.")
            return
        
        self.play_song(self.current_playing)

    def play_prev(self):
        """Play the previous song in the list"""
        if len(self.df) == 0:
            return

        if self.current_playing is None:
            self.current_playing = len(self.df) - 1
        else:
            self.current_playing = (self.current_playing - 1) % len(self.df)

        self.play_song(self.current_playing)

    def play_song(self, row):
        """Helper method to play a song at the given row"""
        if len(self.df) == 0 or row < 0 or row >= len(self.df):
            return

        try:
            # Validate folder path exists
            if not self.current_folder_path or not os.path.isdir(self.current_folder_path):
                QMessageBox.critical(self, "Error", "Folder no longer exists.")
                return
            
            filepath = os.path.abspath(os.path.join(self.current_folder_path, self.df.iloc[row]["Filename"]))
            
            # Validate file exists
            if not os.path.isfile(filepath):
                QMessageBox.critical(self, "Error", f"File not found: {filepath}")
                self.play_next()
                return

            # Stop any current playback
            if hasattr(self, 'player') and self.player and hasattr(self.player, 'is_alive') and self.player.is_alive():
                print(f"[AUDIO] Stopping old player id={id(self.player)}")
                self.player.stop()
                self.playback_timer.stop()
                try:
                    # Wait briefly for the previous thread to exit
                    self.player.join(timeout=1.0)
                    print("[AUDIO] Old player thread joined")
                except Exception:
                    pass

            print(f"[AUDIO] Creating new player instance")

            # Start new playback
            self.player = AudioPlayer(filepath)
            print(f"[AUDIO] New player assigned to self.player id={id(self.player)}, stop_event={self.player.stop_event.is_set()}")
            self.player.start()
            self.current_playing = row
            self.song_table.selectRow(row)
            self.now_playing_label.setText(f"Now Playing: {self.df.iloc[row]['Filename']}")

            # Start playback monitoring
            self.playback_timer.start(500)  # Check every 500ms

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error playing {self.df.iloc[row]['Filename']}: {str(e)}")
            if not hasattr(self, 'failed_songs'):
                self.failed_songs = set()
            self.failed_songs.add(row)  # Mark as failed
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")
            print(f"Error in play_song: {str(e)}")
            # Try to play next song if this one failed
            self.play_next()

    def pause_playback(self):
        if hasattr(self, 'player') and self.player and hasattr(self.player, 'is_alive') and self.player.is_alive():
            if self.current_playing is not None and 0 <= self.current_playing < len(self.df):
                if not self.player.pause_event.is_set():
                    self.player.pause()
                    self.now_playing_label.setText(f"Paused: {self.df.iloc[self.current_playing]['Filename']}")
                else:
                    self.player.resume()
                    self.now_playing_label.setText(f"Now Playing: {self.df.iloc[self.current_playing]['Filename']}")

    def stop_playback(self):
        if hasattr(self, 'player') and self.player and hasattr(self.player, 'is_alive') and self.player.is_alive():
            self.player.stop()
            self.playback_timer.stop()
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.current_folder_path = folder_path
            self.load_folder_metadata(folder_path)
            # persist last folder
            try:
                settings_path = os.path.join(os.path.dirname(__file__), 'last_session.json')
                with open(settings_path, 'w', encoding='utf-8') as f:
                    json.dump({'last_folder': folder_path}, f)
            except Exception as e:
                print(f"[SESSION] Could not save last session: {e}")

    def load_folder_metadata(self, path):
        try:
            df = pd.DataFrame(columns=[
                "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
            ])
            rows = []
            for file in sorted(os.listdir(path)):
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    base, ext = os.path.splitext(file)
                    rows.append({
                        "index": "",
                        "type": "",
                        "songfile": base,
                        "ext": ext,
                        "Filename": file,
                        "alterFilenameTo": ""
                    })
            if rows:
                df = pd.DataFrame(rows)
            self.df = df
            self.failed_songs.clear()  # Reset failed songs on new folder
            self.song_model = SongTableModel(self.df)
            self.song_table.setModel(self.song_model)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading folder: {str(e)}")
            print(f"Error in load_folder_metadata: {str(e)}")

    def set_indices(self):
        try:
            start_index = int(self.index_start_edit.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter a valid number for the start index.")
            return

        try:
            num_songs = len(self.df)
            num_digits = len(str(start_index + num_songs - 1))
            new_df = self.df.copy()
            for i, row in new_df.iterrows():
                new_index = f"{start_index + i:0{num_digits}d}_"
                filename = row["Filename"]
                base, ext = os.path.splitext(filename)
                match = re.match(r'^(\d+_)(.*)', base)
                if match:
                    new_base = f"{new_index}{match.group(2)}"
                else:
                    new_base = f"{new_index}{base}"
                new_df.at[i, "index"] = new_index[:-1]
                new_df.at[i, "alterFilenameTo"] = f"{new_base}{ext}"

            self.df = new_df
            self.song_model = SongTableModel(self.df)
            self.song_table.setModel(self.song_model)
            QMessageBox.information(self, "Info", f"Indices set starting from {start_index}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error setting indices: {str(e)}")
            print(f"Error in set_indices: {str(e)}")

    def save_filenames(self):
        if not hasattr(self, 'current_folder_path') or not self.current_folder_path:
            QMessageBox.critical(self, "Error", "No folder loaded.")
            return

        try:
            self.undo_stack.append(self.df.copy())
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

            progress = QProgressDialog("Renaming files...", "Cancel", 0, len(self.df), self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            for i, (_, row) in enumerate(self.df.iterrows()):
                if progress.wasCanceled():
                    break

                old_path = os.path.join(self.current_folder_path, row["Filename"])
                new_path = os.path.join(self.current_folder_path, row["alterFilenameTo"])

                if os.path.exists(new_path):
                    QMessageBox.critical(self, "Error", f"File {new_path} already exists.")
                    progress.close()
                    return

                try:
                    os.rename(old_path, new_path)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error renaming {old_path}: {str(e)}")
                    progress.close()
                    return

                progress.setValue(i)

            progress.close()
            self.load_folder_metadata(self.current_folder_path)
            QMessageBox.information(self, "Info", "Filenames saved!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving filenames: {str(e)}")
            print(f"Error in save_filenames: {str(e)}")

    def undo_rename(self):
        if not self.undo_stack:
            QMessageBox.information(self, "Info", "Nothing to undo.")
            return

        try:
            previous_df = self.undo_stack.pop()
            for _, row in previous_df.iterrows():
                old_path = os.path.join(self.current_folder_path, row["Filename"])
                new_path = os.path.join(self.current_folder_path, row["alterFilenameTo"])

                if os.path.exists(new_path):
                    try:
                        os.rename(new_path, old_path)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Error undoing rename: {str(e)}")
                        return

            self.load_folder_metadata(self.current_folder_path)
            QMessageBox.information(self, "Info", "Undo successful!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error undoing rename: {str(e)}")
            print(f"Error in undo_rename: {str(e)}")

if __name__ == "__main__":
    try:
        sd.default.samplerate = None
        sd.default.dtype = 'float32'

        app = QApplication(sys.argv)
        window = DJApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()

