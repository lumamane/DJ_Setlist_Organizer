import os
import re
import sys
import json
import io
import numpy as np
import pandas as pd
from threading import Thread, Event
from collections import deque
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
    QTableView, QLabel, QLineEdit, QMessageBox, QFileDialog, QProgressDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData, QByteArray
from PyQt6.QtGui import QDrag
import sounddevice as sd
from pydub import AudioSegment

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.ogg', '.flac')

# --- Audio Player Class ---
class AudioPlayer(Thread):
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.stop_event = Event()
        self.pause_event = Event()
        self.pause_event.set()
        self.data = None
        self.fs = 44100
        self.channels = 1
        self.position = 0

    def run(self):
        try:
            print(f"[AUDIO] Loading: {self.filepath}")
            sound = AudioSegment.from_file(self.filepath)

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
            print(f"[AUDIO] Playing: {len(self.data)/self.fs:.2f}s, {self.channels}ch, {self.fs}Hz")

            with sd.OutputStream(
                samplerate=self.fs,
                channels=self.channels,
                callback=self._callback,
                blocksize=512,
                dtype='float32'
            ) as stream:
                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        sd.sleep(100)
                    else:
                        sd.sleep(10)
                    self.stop_event.wait(0.01)

        except Exception as e:
            print(f"[AUDIO] Error: {e}")
            import traceback
            traceback.print_exc()

    def _callback(self, outdata, frames, time, status):
        if self.pause_event.is_set() and self.data is not None:
            remaining = len(self.data) - self.position
            if remaining <= 0:
                outdata.fill(0)
                return

            chunk = self.data[self.position:self.position + frames]
            self.position += frames

            if len(chunk) < frames:
                outdata[:len(chunk)] = chunk
                outdata[len(chunk):].fill(0)
            else:
                outdata[:] = chunk
        else:
            outdata.fill(0)

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def stop(self):
        self.stop_event.set()
        sd.stop()

# --- Data Model ---
class SongTableModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, index):
        return len(self._data)

    def columnCount(self, index):
        return len(self._data.columns)

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._data.columns[section]
        return None

    def flags(self, index):
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled

    def mimeData(self, indexes):
        mime_data = QMimeData()
        rows = sorted(set(index.row() for index in indexes))
        mime_data.setData("application/x-qabstractitemmodeldatalist", json.dumps(rows).encode())
        return mime_data

    def mimeTypes(self):
        return ["application/x-qabstractitemmodeldatalist"]

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat("application/x-qabstractitemmodeldatalist"):
            return False
        rows = json.loads(data.data("application/x-qabstractitemmodeldatalist").data().decode())
        self.beginMoveRows(QModelIndex(), rows[0], rows[0], QModelIndex(), row)
        self.endMoveRows()
        return True

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
        self.undo_stack = deque(maxlen=10)
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

        # Playback buttons
        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(self.play_prev)
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_selected)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_playback)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_playback)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.play_next)

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

        # Set column widths (WIDER COLUMNS)
        header = self.song_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.song_table.setColumnWidth(0, 60)   # index
        self.song_table.setColumnWidth(1, 60)   # type
        self.song_table.setColumnWidth(2, 300)  # songfile - WIDER
        self.song_table.setColumnWidth(3, 50)   # ext
        self.song_table.setColumnWidth(4, 400)  # Filename - WIDER
        self.song_table.setColumnWidth(5, 400)  # alterFilenameTo - WIDER

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

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.current_folder_path = folder_path
            self.load_folder_metadata(folder_path)

    def load_folder_metadata(self, path):
        df = pd.DataFrame(columns=[
            "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
        ])
        for file in sorted(os.listdir(path)):
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                base, ext = os.path.splitext(file)
                df = pd.concat([df, pd.DataFrame([{
                    "index": "",
                    "type": "",
                    "songfile": base,
                    "ext": ext,
                    "Filename": file,
                    "alterFilenameTo": ""
                }])], ignore_index=True)
        self.df = df
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)

    def on_rows_moved(self, parent, start, end, destination, row):
        self.df = self.df.drop(self.df.index[start]).insert(destination, self.df.iloc[start])
        self.df.reset_index(drop=True, inplace=True)

    def set_indices(self):
        try:
            start_index = int(self.index_start_edit.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter a valid number for the start index.")
            return

        num_songs = len(self.df)
        num_digits = len(str(start_index + num_songs - 1))
        for i, row in self.df.iterrows():
            new_index = f"{start_index + i:0{num_digits}d}_"
            filename = row["Filename"]
            base, ext = os.path.splitext(filename)
            match = re.match(r'^(\d+_)(.*)', base)
            if match:
                new_base = f"{new_index}{match.group(2)}"
            else:
                new_base = f"{new_index}{base}"
            self.df.at[i, "index"] = new_index[:-1]
            self.df.at[i, "alterFilenameTo"] = f"{new_base}{ext}"
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)
        #QMessageBox.information(self, "Info", f"Indices set starting from {start_index}.")

    def play_selected(self):
        selected = self.song_table.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "Warning", "No song selected.")
            return
        row = selected[0].row()
        filepath = os.path.abspath(os.path.join(self.current_folder_path, self.df.iloc[row]["Filename"]))
        try:
            if hasattr(self, 'player') and self.player.is_alive():
                self.player.stop()
            self.player = AudioPlayer(filepath)
            self.player.start()
            self.current_playing = row
            self.song_table.selectRow(row)
            self.now_playing_label.setText(f"Now Playing: {self.df.iloc[row]['Filename']}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error playing {filepath}: {e}")
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

    def play_next(self):
        if self.current_playing is None:
            if len(self.df) > 0:
                self.current_playing = 0
            else:
                return
        else:
            self.current_playing += 1
            if self.current_playing >= len(self.df):
                self.current_playing = 0

        filepath = os.path.abspath(os.path.join(self.current_folder_path, self.df.iloc[self.current_playing]["Filename"]))
        try:
            if hasattr(self, 'player') and self.player.is_alive():
                self.player.stop()
            self.player = AudioPlayer(filepath)
            self.player.start()
            self.song_table.selectRow(self.current_playing)
            self.now_playing_label.setText(f"Now Playing: {self.df.iloc[self.current_playing]['Filename']}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error playing {filepath}: {e}")
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

    def play_prev(self):
        if self.current_playing is None:
            if len(self.df) > 0:
                self.current_playing = len(self.df) - 1
            else:
                return
        else:
            self.current_playing -= 1
            if self.current_playing < 0:
                self.current_playing = len(self.df) - 1

        filepath = os.path.abspath(os.path.join(self.current_folder_path, self.df.iloc[self.current_playing]["Filename"]))
        try:
            if hasattr(self, 'player') and self.player.is_alive():
                self.player.stop()
            self.player = AudioPlayer(filepath)
            self.player.start()
            self.song_table.selectRow(self.current_playing)
            self.now_playing_label.setText(f"Now Playing: {self.df.iloc[self.current_playing]['Filename']}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error playing {filepath}: {e}")
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

    def pause_playback(self):
        if hasattr(self, 'player') and self.player.is_alive():
            self.player.pause()
            self.now_playing_label.setText(f"Paused: {self.df.iloc[self.current_playing]['Filename']}")

    def stop_playback(self):
        if hasattr(self, 'player') and self.player.is_alive():
            self.player.stop()
            self.current_playing = None
            self.now_playing_label.setText("Now Playing: None")

    def save_filenames(self):
        if not hasattr(self, 'current_folder_path'):
            QMessageBox.critical(self, "Error", "No folder loaded.")
            return
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
                return
            try:
                os.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error renaming {old_path}: {e}")
                return
            progress.setValue(i)
        progress.close()
        self.load_folder_metadata(self.current_folder_path)
        QMessageBox.information(self, "Info", "Filenames saved!")

    def undo_rename(self):
        if not self.undo_stack:
            QMessageBox.information(self, "Info", "Nothing to undo.")
            return
        previous_df = self.undo_stack.pop()
        for _, row in previous_df.iterrows():
            old_path = os.path.join(self.current_folder_path, row["Filename"])
            new_path = os.path.join(self.current_folder_path, row["alterFilenameTo"])
            try:
                os.rename(new_path, old_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error undoing rename: {e}")
                return
        self.load_folder_metadata(self.current_folder_path)
        QMessageBox.information(self, "Info", "Undo successful!")

if __name__ == "__main__":
    sd.default.samplerate = None
    sd.default.dtype = 'float32'

    app = QApplication(sys.argv)
    window = DJApp()
    window.show()
    sys.exit(app.exec())
