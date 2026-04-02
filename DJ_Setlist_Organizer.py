"""
DJ Setlist Organizer (AudioSetlist) — run this file to start the app.

    python DJ_Setlist_Organizer.py
"""
import sys

from PyQt6.QtWidgets import QApplication

from AudioSetList import AudioPlayer, default_ui_font


def main():
    app = QApplication(sys.argv)
    app.setFont(default_ui_font(12))
    window = AudioPlayer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
