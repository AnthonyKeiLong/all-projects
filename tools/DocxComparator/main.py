"""
Entry point for DocxComparator.
"""
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore    import Qt

from ui.main_window import MainWindow


def main() -> None:
    # Enable High-DPI scaling on Windows
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,    True)

    app = QApplication(sys.argv)
    app.setApplicationName("DocxComparator")
    app.setApplicationVersion("1.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
