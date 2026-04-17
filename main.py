#!/usr/bin/env python3
import sys
import signal
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer
from app.gui.main_window import MainWindow


def main():
    # Enable HiDPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("LUT Previewer")
    app.setStyle("Fusion")

    # Qt's event loop blocks Python signal delivery. A short timer wakes
    # Python periodically so SIGINT (Ctrl-C) is processed promptly instead
    # of being delivered in the middle of a Qt event handler.
    signal_timer = QTimer()
    signal_timer.start(200)
    signal_timer.timeout.connect(lambda: None)

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    window = MainWindow()
    window.setWindowTitle("LUT Previewer")
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
