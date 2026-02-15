#!/usr/bin/env python
import os
import signal
import sys


def main():
    # Ensure propertree package is importable
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    from PySide6.QtWidgets import QApplication

    from propertree.qt_app import ProperTreeApp

    # Allow Ctrl+C to quit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("qtProperTree")
    app.setOrganizationName("CorpNewt")

    # Collect any plist files passed as arguments
    plists = [a for a in sys.argv[1:] if not a.startswith("-")]

    ProperTreeApp(app, plists=plists)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
