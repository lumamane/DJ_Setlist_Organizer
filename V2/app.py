import sys
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QFileSystemModel,
    QTableView, QVBoxLayout, QWidget, QPushButton, QLineEdit,
    QHBoxLayout, QLabel, QCheckBox, QMessageBox, QAbstractItemView,
    QHeaderView, QMenu, QInputDialog, QTimer
)
from PyQt6.QtCore import QDir, Qt, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice, pyqtSignal, QObject
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QAction
import pygame
import aubio
import numpy as np

class FileItem:
    def __init__(self, path):
        self.path = Path(path)
        self.index = ""
        self.type = ""
        self.interpret = ""
        self.title = ""
        self.key = ""
        self.bpm = ""
        self.new_filename = ""
        self.original_filename = self.path.name
        self.parse_filename()
        self.analyze_audio()

    def parse_filename(self):
        # Example: "[001][salsa__][Marc Anthony][vivir la vida].mp4"
        pattern = r'^(\[\d+\])?(\[\w+\])?([^[]+)(?:\.(\w+))?$'
        match = re.match(pattern, self.original_filename)
        if match:
            self.index = match.group(1) or ""
            self.type = match.group(2) or ""
            rest = match.group(3)
            parts = rest.split(" - ")
            if len(parts) == 2:
                self.interpret, self.title = parts
            else:
                self.title = rest

    def analyze_audio(self):
        try:
            src = aubio.source(str(self.path), 0, 0)
            samplerate = src.samplerate
            o = aubio.tempo("specdiff", 1024, samplerate, 0.97)
            bpm = 0
            while True:
                samples, read = src()
                if o(samples):
                    bpm = o.get_bpm()
                    break
                if read < src.hop_size:
                    break
            self.bpm = f"{bpm:.1f}"
            # Key detection is more complex; placeholder for now
            self.key = "C"
        except:
            self.bpm = "?"
            self.key = "?"

class FileModel(QStandardItemModel):
    def __init__(self):
        super().__init__()
        self.setHorizontalHeaderLabels([
            "Index", "Type", "Interpret", "Title", "Key", "BPM", "New Filename", "Original Filename"
        ])

    def add_file(self, file_item):
        row = [
            QStandardItem(file_item.index),
            QStandardItem(file_item.type),
            QStandardItem(file_item.interpret),
            QStandardItem(file_item.title),
            QStandardItem(file_item.key),
            QStandardItem(file_item.bpm),
            QStandardItem(file_item.new_filename),
            QStandardItem(file_item.original_filename),
        ]
        self.appendRow(row)

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def flags(self, index):
        return super().flags(index) | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled

class DJApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ File Manager")
        self.setGeometry(100, 100, 1200, 800)
        self.files = []
        self.playlist = []
        self.current_playing = None
        self.autoplay = True
        self.init_ui()
        self.init_playback()

    def init_ui(self):
        # Folder Selection
        self.folder_model1 = QFileSystemModel()
        self.folder_model1.setRootPath(QDir.rootPath())
        self.tree_view1 = QTreeView()
        self.tree_view1.setModel(self.folder_model1)
        self.tree_view1.setRootIndex(self.folder_model1.index(QDir.homePath()))

        self.folder_model2 = QFileSystemModel()
        self.folder_model2.setRootPath(QDir.rootPath())
        self.tree_view2 = QTreeView()
        self.tree_view2.setModel(self.folder_model2)
        self.tree_view2.setRootIndex(self.folder_model2.index(QDir.homePath()))

        # File Table
        self.file_model = FileModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.file_model)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table_view.setDropIndicatorShown(True)
        self.table_view.setAcceptDrops(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)

        # Playback Controls
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.next_button = QPushButton("Next")
        self.autoplay_checkbox = QCheckBox("Autoplay")
        self.autoplay_checkbox.setChecked(True)
        self.autoplay_checkbox.stateChanged.connect(self.toggle_autoplay)

        # Tagging Controls
        self.add_index_button = QPushButton("Add Index Tag")
        self.add_type_button = QPushButton("Add Type Tag")
        self.save_filenames_button = QPushButton("Save Filenames")

        # Search/Filter
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search files...")
        self.search_edit.textChanged.connect(self.filter_files)

        # Layout
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Folder 1:"))
        folder_layout.addWidget(self.tree_view1)
        folder_layout.addWidget(QLabel("Folder 2:"))
        folder_layout.addWidget(self.tree_view2)

        control_layout = QHBoxLayout()
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.pause_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.next_button)
        control_layout.addWidget(self.autoplay_checkbox)
        control_layout.addWidget(self.add_index_button)
        control_layout.addWidget(self.add_type_button)
        control_layout.addWidget(self.save_filenames_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(folder_layout)
        main_layout.addWidget(self.search_edit)
        main_layout.addWidget(self.table_view)
        main_layout.addLayout(control_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Connect signals
        self.tree_view1.doubleClicked.connect(self.on_folder_selected)
        self.tree_view2.doubleClicked.connect(self.on_folder_selected)
        self.play_button.clicked.connect(self.play)
        self.pause_button.clicked.connect(self.pause)
        self.stop_button.clicked.connect(self.stop)
        self.next_button.clicked.connect(self.next)
        self.add_index_button.clicked.connect(self.add_index_tag)
        self.add_type_button.clicked.connect(self.add_type_tag)
        self.save_filenames_button.clicked.connect(self.save_filenames)

    def init_playback(self):
        pygame.mixer.init()
        pygame.mixer.music.set_endevent(pygame.USEREVENT)
        QTimer.singleShot(100, self.check_music_end)

    def check_music_end(self):
        for event in pygame.event.get():
            if event.type == pygame.USEREVENT and self.autoplay:
                self.next()
        QTimer.singleShot(100, self.check_music_end)

    def toggle_autoplay(self, state):
        self.autoplay = state == Qt.CheckState.Checked.value

    def on_folder_selected(self, index):
        path = self.folder_model1.filePath(index)
        self.load_folder(path)

    def load_folder(self, folder_path):
        self.file_model.clear()
        self.files = []
        for p in Path(folder_path).glob("*"):
            if p.is_file() and p.suffix.lower() in [".mp3", ".m4a", ".wav"]:
                file_item = FileItem(p)
                self.files.append(file_item)
                self.file_model.add_file(file_item)
        self.playlist = self.files.copy()

    def filter_files(self, text):
        for i in range(self.file_model.rowCount()):
            row_hidden = not any(
                text.lower() in self.file_model.item(i, j).text().lower()
                for j in range(self.file_model.columnCount())
            )
            self.table_view.setRowHidden(i, row_hidden)

    def play(self):
        if not self.playlist:
            return
        if not self.current_playing:
            self.current_playing = self.playlist[0]
        pygame.mixer.music.load(str(self.current_playing.path))
        pygame.mixer.music.play()

    def pause(self):
        pygame.mixer.music.pause()

    def stop(self):
        pygame.mixer.music.stop()
        self.current_playing = None

    def next(self):
        if not self.playlist:
            return
        if self.current_playing:
            idx = self.playlist.index(self.current_playing)
            if idx + 1 < len(self.playlist):
                self.current_playing = self.playlist[idx + 1]
                self.play()
            elif self.autoplay:
                self.current_playing = self.playlist[0]
                self.play()

    def add_index_tag(self):
        for i, file_item in enumerate(self.files, 1):
            file_item.index = f"[{i:03d}]"
            self.file_model.item(i-1, 0).setText(file_item.index)

    def add_type_tag(self):
        tag, ok = QInputDialog.getText(self, "Add Type Tag", "Enter tag (e.g., salsa):")
        if ok and tag:
            for file_item in self.files:
                file_item.type = f"[{tag.ljust(7, '_')}]"
                self.file_model.item(self.files.index(file_item), 1).setText(file_item.type)

    def save_filenames(self):
        for file_item in self.files:
            new_name = f"{file_item.index}{file_item.type}{file_item.interpret} - {file_item.title}{file_item.path.suffix}"
            new_path = file_item.path.with_name(new_name)
            file_item.path.rename(new_path)
        QMessageBox.information(self, "Success", "Filenames saved!")

    def show_context_menu(self, pos):
        menu = QMenu()
        toggle_visibility = menu.addAction("Toggle Column Visibility")
        action = menu.exec(self.table_view.mapToGlobal(pos))
        if action == toggle_visibility:
            self.toggle_column_visibility()

    def toggle_column_visibility(self):
        header = self.table_view.horizontalHeader()
        for i in range(self.file_model.columnCount()):
            header.setSectionHidden(i, not header.isSectionHidden(i))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DJApp()
    window.show()
    sys.exit(app.exec())
