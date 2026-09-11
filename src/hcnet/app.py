"""Punto de entrada de la aplicación HCNet Transport."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from hcnet.ui.main_window import MainWindow
from hcnet.ui.styles import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HCNet Transport")
    app.setApplicationDisplayName("HCNet Transport 1.0")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("VanLinux")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    QLocale.setDefault(QLocale(QLocale.Language.Spanish, QLocale.Country.Mexico))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
