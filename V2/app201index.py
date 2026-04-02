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
    QTreeView, QTableView, QLabel, QLineEdit, QComboBox, QMessageBox
)
from PyQt6.QtGui import QFileSystemModel, QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData, QByteArray, QItemSelectionModel

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.mp3', '.wav', '.m4a')

# --- Data Model ---
class SongTableModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame(columns=[
        "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
    ])):
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

# --- Filename Parsing ---
def parse_filename(filename):
    base = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1][1:]
    return {"songfile": base, "ext": ext, "Filename": filename}

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

        # Folder view
        self.folder_view = QTreeView()
        self.folder_view.setModel(QFileSystemModel())
        self.folder_view.model().setRootPath("")
        self.folder_view.setRootIndex(self.folder_view.model().index(""))
        self.folder_view.clicked.connect(self.load_folder)
        layout.addWidget(self.folder_view)

        # Song table
        self.song_table = QTableView()
        self.song_table.setModel(self.song_model)
        self.song_table.setDragDropMode(QTableView.DragDropMode.InternalMove)
        self.song_table.setDragEnabled(True)
        self.song_table.setAcceptDrops(True)
        self.song_table.setDropIndicatorShown(True)
        self.song_table.model().rowsMoved.connect(self.on_rows_moved)
        self.song_table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.song_table)

        # Controls
        controls = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_selected)
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.play_next)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_playback)
        self.index_start_edit = QLineEdit("1")
        self.index_btn = QPushButton("Index")
        self.index_btn.clicked.connect(self.set_indices)
        self.save_btn = QPushButton("Save Filenames")
        self.save_btn.clicked.connect(self.save_filenames)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(QLabel("Start Index:"))
        controls.addWidget(self.index_start_edit)
        controls.addWidget(self.index_btn)
        controls.addWidget(self.save_btn)
        layout.addLayout(controls)

        # Type editor
        type_layout = QHBoxLayout()
        self.type_edit = QComboBox()
        self.type_edit.setEditable(True)
        self.type_edit.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.type_edit.currentTextChanged.connect(self.update_type)
        type_layout.addWidget(QLabel("Type:"))
        type_layout.addWidget(self.type_edit)
        layout.addLayout(type_layout)

    def load_folder(self, index):
        try:
            path = self.folder_view.model().filePath(index)
            if os.path.isdir(path):
                self.current_folder_path = path
                self.load_folder_metadata(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading folder: {e}")

    def load_folder_metadata(self, path):
        df = pd.DataFrame(columns=[
            "index", "type", "songfile", "ext", "Filename", "alterFilenameTo"
        ])
        for file in sorted(os.listdir(path)):
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                parsed = parse_filename(file)
                df = pd.concat([df, pd.DataFrame([{
                    "index": "",
                    "type": "",
                    "songfile": parsed["songfile"],
                    "ext": parsed["ext"],
                    "Filename": parsed["Filename"],
                    "alterFilenameTo": ""
                }])], ignore_index=True)
        self.df = df
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)
        self.update_type_combo()

    def update_type_combo(self):
        types = sorted(set(self.df["type"].dropna().unique()))
        self.type_edit.clear()
        self.type_edit.addItems([""] + types)

    def update_type(self, text):
        selected = self.song_table.selectedIndexes()
        if selected:
            row = selected[0].row()
            self.df.at[row, "type"] = text
            self.update_proposed_filenames()

    def update_proposed_filenames(self):
        for i, row in self.df.iterrows():
            index = f"{row['index']}_" if row['index'] else ""
            type_ = f"[{row['type'].strip():<8}]" if row['type'] else ""
            self.df.at[i, "alterFilenameTo"] = f"{index}{type_}{row['songfile']}.{row['ext']}"
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)

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
            self.df.at[i, "songfile"] = new_base
            self.df.at[i, "alterFilenameTo"] = f"{new_base}{ext}"
        self.song_model = SongTableModel(self.df)
        self.song_table.setModel(self.song_model)
        QMessageBox.information(self, "Info", f"Indices set starting from {start_index}.")

    def on_rows_moved(self, parent, start, end, destination, row):
        self.df = self.df.drop(self.df.index[start]).insert(destination, self.df.iloc[start])
        self.df.reset_index(drop=True, inplace=True)
        self.update_proposed_filenames()

    def on_selection_changed(self, selected, deselected):
        pass

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
    window = DJApp()
    window.show()
    sys.exit(app.exec())
