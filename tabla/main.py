from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QLockFile, QStandardPaths, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox
from . import __version__
from .storage import Store
from .theme import STYLE, load_fonts, application_icon
from .workspace import TablaWindow as MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tabla personal desktop workspace")
    parser.add_argument("--data-dir", type=Path, help="Use a separate local workspace directory")
    parser.add_argument("--demo", action="store_true", help="Seed an empty workspace with example content")
    parser.add_argument("--screenshot", type=Path, help="Save a screenshot of this app and exit (for visual QA)")
    parser.add_argument("--page", default="Today", choices=["Today", "Calendar", "Board", "My Tasks", "Notes", "Focus", "Settings", "Trash"])
    parser.add_argument("--quit-after", type=int, help="Exit after this many milliseconds (packaging smoke test)")
    args = parser.parse_args(argv)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Tabla")
    app.setOrganizationName("Tabla")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    load_fonts()
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(STYLE)
    directory = args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / "Tabla"
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(directory / "tabla.log"), level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    lock = QLockFile(str(directory / "tabla.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "Tabla is already open", "A Tabla window is already using this workspace. Check your taskbar or the system tray.")
        return 0
    try:
        store = Store(directory / "tabla.sqlite3")
        snapshots = directory / "snapshots"
        snapshots.mkdir(exist_ok=True)
        snapshot = snapshots / ("tabla-" + datetime.now().strftime("%Y-%m-%d") + ".sqlite3")
        if not snapshot.exists() and store.records(state="all"):
            store.backup(snapshot)
        # Snapshots are small and local. Retain the 7 most recent daily snapshots.
        for old in sorted(snapshots.glob("tabla-*.sqlite3"), reverse=True)[7:]:
            old.unlink()
        if args.demo and not store.records(state="all"):
            store.seed_demo()
    except Exception as exc:
        logging.exception("Could not open local workspace")
        QMessageBox.critical(None, "Could not open Tabla", f"Your existing files have not been replaced.\n\n{exc}\n\nData folder: {directory}")
        lock.unlock()
        return 1
    window = MainWindow(store)

    def exception_hook(exc_type, value, traceback):
        logging.error("Application error", exc_info=(exc_type, value, traceback))
        QMessageBox.warning(app.activeWindow(), "Tabla needs your attention", "An action could not be completed. Your last saved data is still on this device.\n\n" + str(value))

    sys.excepthook = exception_hook
    window.navigate(args.page)
    if not args.screenshot:
        available = app.primaryScreen().availableGeometry()
        window.resize(min(1500, max(1040, available.width() - 60)), min(960, max(700, available.height() - 65)))
    window.show()

    def capture():
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot)):
            logging.error("Could not save QA screenshot")
        app.quit()

    if args.screenshot:
        QTimer.singleShot(650, capture)
    if args.quit_after:
        QTimer.singleShot(args.quit_after, app.quit)
    result = app.exec()
    window.timer.persist()
    store.close()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
