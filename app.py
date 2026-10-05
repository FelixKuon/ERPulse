"""ERPulse — Einstiegspunkt der Anwendung.

    python app.py
"""
import sys
from PyQt6.QtWidgets import QApplication
from gui.theme import apply_theme
from gui.connection_dev_window import ConnectionDevWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ERPulse")
    apply_theme(app)
    window = ConnectionDevWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
