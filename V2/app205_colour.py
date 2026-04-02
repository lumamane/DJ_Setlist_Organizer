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
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData, QByteArray, QTimer
from PyQt6.QtGui import QDrag
import sounddevice as sd
from pydub import AudioSegment

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
        super().__init__()
        self.filepath = filepath
        self.stop_event = Event()
        self.pause_event = Event()
        self.pause_event.set()
        self.data = None
        self.fs = 44100
        self.channels = 1
        self.position = 0
        self.playback_finished = Event()

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
            self.duration = len(self.data) / self.fs
            print(f"[AUDIO] Playing: {self.duration:.2f}s, {self.channels}ch, {self.fs}Hz")

            with sd.OutputStream(
                samplerate=self.fs,
                channels=self.channels,
                callback=self._callback,
                blocksize=512,
                dtype='float32'
            ) as stream:
                start_time = sd.get_time()
                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        sd.sleep(100)
                    else:
                        sd.sleep(10)

                    # Check if playback should be finished
                    if sd.get_time() - start_time >= self.duration:
                        self.playback_finished.set()
                        break

                    self.stop_event.wait(0.01)

                self.playback_finished.set()
            sd.stop()
        except Exception as e:
            print(f"[AUDIO] Error: {e}")
            import traceback
            traceback.print_exc()
            self.playback_finished.set()

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
        self.song_t
