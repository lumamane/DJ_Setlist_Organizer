import os
import re
import sys
import numpy as np
import librosa
import sounddevice as sd
import pandas as pd
from threading import Thread
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
    QTableView, QLabel, QLineEdit, QComboBox, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData, QByteArray
from PyQt6.QtGui import QDrag, QFont

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a')

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
        mime_data.setData("application/x-qabstractitemmodeldatalist", QByteArray(str(rows).encode()))
        return mime_data

    def mimeTypes(self):
        return ["application/x-qabstractitemmodeldatalist"]

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not data.hasFormat("application/x-qabstractitemmodeldatalist"):
            return False
        rows = eval(data.data("application/x-qabstractitemmodeldatalist").data().decode())
        self.beginMoveRows(QModelIndex(), rows[0], rows[0], QModelIndex(), row)
        self.endMoveRows()
        return True

# --- Main App ---
class DJApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App")
        self.setGeometry(100, 100, 1200, 600)
        self.df = pd.DataFrame(columns=[
            "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
        ])
        self.song_model = SongTableModel(self.df)
        self.current_playing = None
        self.current_folder_path = None
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Folder selection button
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        layout.addWidget(self.folder_btn)

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
        self.song_table.model().rowsMoved.connect(self.on_rows_moved)
        layout.addWidget(self.song_table)

        # Controls
        controls = QHBoxLayout()

        # Set a consistent font for all buttons
        font = QFont()
        font.setFamily("Noto Sans")  # or "Segoe UI Symbol", "DejaVu Sans"

        self.play_btn = QPushButton("Play ▶/⏸")
        self.play_btn.setFont(font)
        self.play_btn.clicked.connect(self.play_selected)

        self.next_btn = QPushButton("Next ⏭")
        self.next_btn.setFont(font)
        self.next_btn.clicked.connect(self.play_next)

        self.stop_btn = QPushButton("Stop ⏹")
        self.stop_btn.setFont(font)
        self.stop_btn.clicked.connect(self.stop_playback)

        self.index_start_edit = QLineEdit("1")
        self.index_btn = QPushButton("Index")
        self.index_btn.setFont(font)
        self.index_btn.clicked.connect(self.set_indices)

        self.save_btn = QPushButton("Save Filenames")
        self.save_btn.setFont(font)
        self.save_btn.clicked.connect(self.save_filenames)

        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(QLabel("Start Index:"))
        controls.addWidget(self.index_start_edit)
        controls.addWidget(self.index_btn)
        controls.addWidget(self.save_btn)

        layout.addLayout(controls)

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
        # Update the DataFrame to match the new order
        self.df = self.df.drop(self.df.index[start]).insert(destination, self.df.iloc[start])
        self.df.reset_index(drop=True, inplace=True)
        print("Rows moved. New order:", self.df["Filename"].tolist())

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
        QMessageBox.information(self, "Info", f"Indices set starting from {start_index}.")

    def play_selected(self):
        selected = self.song_table.selectedIndexes()
        if selected:
            row = selected[0].row()
            filepath = os.path.join(self.current_folder_path, self.df.iloc[row]["Filename"])
            self.current_playing = row
            try:
                y, sr = librosa.load(filepath, sr=None)
                Thread(target=lambda: sd.play(y, sr), daemon=True).start()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error playing {filepath}: {e}")

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

        filepath = os.path.join(self.current_folder_path, self.df.iloc[self.current_playing]["Filename"])
        try:
            y, sr = librosa.load(filepath, sr=None)
            Thread(target=lambda: sd.play(y, sr), daemon=True).start()
            self.song_table.selectRow(self.current_playing)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error playing {filepath}: {e}")

    def stop_playback(self):
        sd.stop()
        self.current_playing = None

    def save_filenames(self):
        if not hasattr(self, 'current_folder_path'):
            QMessageBox.critical(self, "Error", "No folder loaded.")
            return
        sd.stop()
        self.current_playing = None
        for _, row in self.df.iterrows():
            old_path = os.path.join(self.current_folder_path, row["Filename"])
            new_path = os.path.join(self.current_folder_path, row["alterFilenameTo"])
            try:
                os.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error renaming {old_path}: {e}")
                return
        self.load_folder_metadata(self.current_folder_path)
        QMessageBox.information(self, "Info", "Filenames saved!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Optionally, set a global font for the app
    font = QFont()
    font.setFamily("Noto Sans")
    app.setFont(font)
    window = DJApp()
    window.show()
    sys.exit(app.exec())
