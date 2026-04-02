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
    QTableView, QLabel, QLineEdit, QMessageBox, QFileDialog, QProgressDialog, QHeaderView, QComboBox
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QTimer
from PyQt6.QtGui import QDrag
import sounddevice as sd
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from datetime import datetime

def _log(cat: str, msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{cat}] {msg}")

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
        self.should_stop = Event()
        self.should_pause = Event()
        self.is_playing = Event()
        self.loading = True
        self.duration = 0.0

    def stop(self):
        self.should_stop.set()
        self.is_playing.clear()

    def pause(self):
        self.should_pause.set()

    def resume(self):
        self.should_pause.clear()

    def run(self):
        stream = None
        try:
            _log('AUDIO', f"Loading: {os.path.basename(self.filepath)}")
            try:
                sound = AudioSegment.from_file(self.filepath)
            except CouldntDecodeError:
                try:
                    import subprocess
                    cmd = ["ffmpeg", "-i", self.filepath, "-f", "wav", "-"]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    data, _ = proc.communicate(timeout=5)
                    if proc.returncode != 0:
                        raise CouldntDecodeError("FFmpeg failed")
                    sound = AudioSegment.from_file(io.BytesIO(data), format="wav")
                except Exception as e:
                    _log('AUDIO', f"Failed to load: {e}")
                    return

            fs = 44100
            if sound.frame_rate != fs:
                sound = sound.set_frame_rate(fs)
            samples = np.array(sound.get_array_of_samples(), dtype=np.float32) / 32768.0
            max_val = np.max(np.abs(samples))
            if 0 < max_val < 0.1:
                samples = samples * (0.9 / max_val)
            ch = getattr(sound, 'channels', 1)
            if ch == 1:
                samples = np.column_stack([samples, samples])
            else:
                samples = samples.reshape((-1, ch))
            self.duration = len(samples) / fs
            _log('AUDIO', f"Ready: {self.duration:.1f}s")
            self.is_playing.set()
            self.loading = False
            position = 0
            nch = samples.shape[1] if hasattr(samples, 'shape') and len(samples.shape) > 1 else 1

            def audio_callback(outdata, frames, time_info, status):
                nonlocal position
                if status:
                    _log('AUDIO', f"Stream status: {status}")
                if self.should_pause.is_set():
                    outdata.fill(0)
                    return
                chunk = samples[position:position + frames]
                position += len(chunk)
                if len(chunk) == 0:
                    self.is_playing.clear()
                    outdata.fill(0)
                else:
                    if len(chunk) < frames:
                        padded = np.zeros((frames, 2), dtype=np.float32)
                        padded[:len(chunk)] = chunk
                        outdata[:] = padded
                        self.is_playing.clear()
                    else:
                        outdata[:] = chunk

            stream = sd.OutputStream(
                samplerate=fs,
                channels=nch,
                callback=audio_callback,
                blocksize=512,
                dtype='float32'
            )
            stream.start()
            while self.is_playing.is_set() and not self.should_stop.is_set():
                time.sleep(0.1)
            stream.stop()
        except Exception as e:
            _log('AUDIO', f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if stream:
                try:
                    stream.close()
                except:
                    pass
            self.is_playing.clear()

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
    _active_player_id = None

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App")
        self.setGeometry(100, 100, 1200, 600)

        sd.default.samplerate = None
        sd.default.dtype = 'float32'
        _log('AUDIO', f"sd.default.device (startup) = {sd.default.device}")

        self.df = pd.DataFrame(columns=[
            "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
        ])
        self.song_model = SongTableModel(self.df)
        self.current_playing = None
        self.current_folder_path = None
        self.player = None
        self.song_table = None
        self.failed_songs = set()
        self.undo_stack = deque(maxlen=10)
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.check_playback_status)

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top controls
        top_controls = QHBoxLayout()
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        top_controls.addWidget(self.folder_btn)

        # Device selector
        self.device_label = QLabel("Output:")
        self.device_combo = QComboBox()
        self.device_combo.setToolTip("Select audio output device")
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        top_controls.addWidget(self.device_label)
        top_controls.addWidget(self.device_combo)

        self.test_out_btn = QPushButton("Test Output")
        self.test_out_btn.setToolTip("Play a short test tone on the selected output device")
        self.test_out_btn.clicked.connect(self.play_test_tone)
        top_controls.addWidget(self.test_out_btn)

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

        # Move Up/Down buttons
        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_up)
        self.move_up_btn.setShortcut("Ctrl+Up")

        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_down)
        self.move_down_btn.setShortcut("Ctrl+Down")

        top_controls.addWidget(self.move_up_btn)
        top_controls.addWidget(self.move_down_btn)

        layout.addLayout(top_controls)

        # Populate device list after UI elements exist
        try:
            self.populate_audio_devices()
        except Exception as e:
            _log('AUDIO', f"populate_audio_devices error: {e}")

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
        self.song_table.setColumnWidth(0, 60)
        self.song_table.setColumnWidth(1, 60)
        self.song_table.setColumnWidth(2, 300)
        self.song_table.setColumnWidth(3, 50)
        self.song_table.setColumnWidth(4, 400)
        self.song_table.setColumnWidth(5, 400)

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
        if index.isValid():
            row = index.row()
            if 0 <= row < len(self.df):
                self.play_song(row)

    def on_rows_moved(self, parent, start, end, destination, row):
        if start < 0 or start >= len(self.df) or destination < 0 or destination > len(self.df):
            return

        current_filename = None
        current_row = self.current_playing
        if current_row is not None and 0 <= current_row < len(self.df):
            current_filename = self.df.iloc[current_row]["Filename"]

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
                remaining.iloc[:destination],
                row_to_move,
                remaining.iloc[destination:]
            ], ignore_index=True)

        self.df = new_df
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)

        if current_filename:
            matching = self.df[self.df["Filename"] == current_filename]
            if not matching.empty:
                self.current_playing = matching.index[0]
                self.song_table.selectRow(self.current_playing)
            else:
                self.current_playing = None
                self.now_playing_label.setText("Now Playing: None")

    def move_up(self):
        selected = self.song_table.selectedIndexes()
        if not selected:
            return
        row = selected[0].row()
        if row > 0:
            self.df = self._move_row(row, row - 1)
            self.song_model = SongTableModel(self.df)
            self.song_table.setModel(self.song_model)
            self.song_table.selectRow(row - 1)
            if self.current_playing == row:
                self.current_playing -= 1

    def move_down(self):
        selected = self.song_table.selectedIndexes()
        if not selected:
            return
        row = selected[0].row()
        if row < len(self.df) - 1:
            self.df = self._move_row(row, row + 1)
            self.song_model = SongTableModel(self.df)
            self.song_table.setModel(self.song_model)
            self.song_table.selectRow(row + 1)
            if self.current_playing == row:
                self.current_playing += 1

    def _move_row(self, from_row, to_row):
        new_df = self.df.copy()
        row_to_move = new_df.iloc[[from_row]]
        remaining = new_df.drop(index=from_row)
        if to_row <= from_row:
            new_df = pd.concat([
                remaining.iloc[:to_row],
                row_to_move,
                remaining.iloc[to_row:]
            ], ignore_index=True)
        else:
            new_df = pd.concat([
                remaining.iloc[:to_row],
                row_to_move,
                remaining.iloc[to_row:]
            ], ignore_index=True)
        return new_df

    def play_selected(self):
        selected = self.song_table.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "Warning", "No song selected.")
            return
        row = selected[0].row()
        if 0 <= row < len(self.df):
            self.play_song(row)

    def play_next(self):
        if len(self.df) == 0:
            return
        if self.current_playing is None:
            self.current_playing = 0
        else:
            self.current_playing = (self.current_playing + 1) % len(self.df)
        failed = getattr(self, 'failed_songs', set())
        attempts = 0
        while attempts < len(self.df):
            if self.current_playing not in failed:
                break
            self.current_playing = (self.current_playing + 1) % len(self.df)
            attempts += 1
        if attempts >= len(self.df):
            self.now_playing_label.setText("All songs failed")
            return
        self.play_song(self.current_playing)

    def play_prev(self):
        if len(self.df) == 0:
            return
        if self.current_playing is None:
            self.current_playing = len(self.df) - 1
        else:
            self.current_playing = (self.current_playing - 1) % len(self.df)
        failed = getattr(self, 'failed_songs', set())
        attempts = 0
        while attempts < len(self.df):
            if self.current_playing not in failed:
                break
            self.current_playing = (self.current_playing - 1) % len(self.df)
            attempts += 1
        if attempts >= len(self.df):
            self.now_playing_label.setText("All songs failed")
            return
        self.play_song(self.current_playing)

    def play_song(self, row):
        if len(self.df) == 0 or row < 0 or row >= len(self.df):
            return
        try:
            if self.player:
                self.player.stop()
                self.player.join(timeout=0.5)
            if not self.current_folder_path or not os.path.isdir(self.current_folder_path):
                QMessageBox.critical(self, "Error", "Folder no longer exists.")
                return
            filepath = os.path.abspath(os.path.join(
                self.current_folder_path,
                self.df.iloc[row]["Filename"]
            ))
            if not os.path.isfile(filepath):
                QMessageBox.critical(self, "Error", f"File not found: {filepath}")
                self.failed_songs.add(row)
                self.play_next()
                return
            _log('PLAY', f"Starting: {os.path.basename(filepath)}")
            self.player = AudioPlayer(filepath)
            self.player.start()
            self.current_playing = row
            self.song_table.selectRow(row)
            self.now_playing_label.setText(f"▶ {self.df.iloc[row]['Filename']}")
            self.playback_timer.start(500)
        except Exception as e:
            _log('PLAY', f"Error: {e}")
            QMessageBox.critical(self, "Error", f"Playback error: {str(e)}")
            self.failed_songs.add(row)
            self.play_next()

    def pause_playback(self):
        if self.player and self.player.is_alive():
            if self.player.should_pause.is_set():
                self.player.resume()
                self.now_playing_label.setText(f"▶ {self.df.iloc[self.current_playing]['Filename']}")
            else:
                self.player.pause()
                self.now_playing_label.setText(f"⏸ {self.df.iloc[self.current_playing]['Filename']}")

    def stop_playback(self):
        if self.player:
            self.player.stop()
            self.playback_timer.stop()
        self.current_playing = None
        self.now_playing_label.setText("⏹ Stopped")

    def check_playback_status(self):
        if not self.player or self.current_playing is None:
            self.playback_timer.stop()
            return
        if getattr(self.player, 'loading', False):
            return
        if not self.player.is_playing.is_set():
            self.playback_timer.stop()
            _log('PLAY', 'Song finished, playing next')
            self.play_next()

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.current_folder_path = folder_path
            self.load_folder_metadata(folder_path)
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
            self.failed_songs.clear()
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

    def populate_audio_devices(self):
        try:
            devices = sd.query_devices()
        except Exception as e:
            _log('AUDIO', f"Could not query devices: {e}")
            return
        output_devices = []
        for idx, d in enumerate(devices):
            if d.get('max_output_channels', 0) > 0:
                name = d.get('name')
                ch = d.get('max_output_channels')
                output_devices.append((idx, f"{idx}: {name} (out_ch={ch})"))
        self._output_device_map = {i: label for i, label in output_devices}
        for i, label in output_devices:
            self.device_combo.addItem(label, i)
        try:
            dev = sd.default.device
            out_idx = None
            if isinstance(dev, (list, tuple)) and len(dev) > 1:
                out_idx = dev[1]
            elif isinstance(dev, int):
                out_idx = dev
            if out_idx is not None:
                for cb_index in range(self.device_combo.count()):
                    if self.device_combo.itemData(cb_index) == out_idx:
                        self.device_combo.setCurrentIndex(cb_index)
                        break
        except Exception:
            pass

    def on_device_changed(self, combo_index):
        try:
            data = self.device_combo.itemData(combo_index)
            if data is None:
                return
            out_idx = int(data)
            cur = sd.default.device
            if isinstance(cur, (list, tuple)) and len(cur) > 1:
                in_idx = cur[0]
            else:
                in_idx = None
            if in_idx is not None:
                sd.default.device = [in_idx, out_idx]
            else:
                sd.default.device = out_idx
            _log('AUDIO', f"Set default output device to {out_idx}: {self.device_combo.currentText()}")
        except Exception as e:
            _log('AUDIO', f"Error setting output device: {e}")

    def play_test_tone(self):
        def _play():
            fs = 44100
            duration = 1.0
            t = np.linspace(0, duration, int(fs * duration), False)
            tone = (0.25 * np.sin(2 * np.pi * 440 * t)).astype('float32')
            try:
                _log('AUDIO', "Playing test tone...")
                sd.play(tone, fs)
                sd.wait()
                _log('AUDIO', "Test tone finished")
            except Exception as e:
                _log('AUDIO', f"Test tone failed: {e}")
        th = Thread(target=_play, daemon=True)
        th.start()

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
