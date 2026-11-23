import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QPoint, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.dialogs import NoteDialog
from tabla.theme import COLORS, apply_appearance, themed_color
from tabla.polish import set_reduced_motion


class NoteColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_open_note_and_live_color_changes_paint_entire_sheet_in_both_themes(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'tabla.sqlite3')
            set_reduced_motion(True)
            try:
                for dark in (False, True):
                    apply_appearance(self.app, dark)
                    record = store.save({'kind': 'note', 'title': 'Colored note', 'body': 'Keep this text', 'color': 'yellow'})
                    dialog = NoteDialog(store, record)
                    dialog.show()
                    QTest.qWait(35)
                    document = dialog.editor.snapshot()
                    for color in ('yellow', 'blue', 'green', 'violet', 'rose', 'gray'):
                        dialog.color.setCurrentText(color)
                        QTest.qWait(20)
                        expected = themed_color('#ffffff' if color == 'gray' else COLORS[color][0])
                        image = dialog.grab().toImage()
                        ratio = image.devicePixelRatio()
                        editor_point = dialog.editor.viewport().mapTo(dialog, QPoint(35, dialog.editor.viewport().height() - 15))
                        for point in (QPoint(20, 150), editor_point, QPoint(24, dialog.height() - 38)):
                            actual = image.pixelColor(round(point.x() * ratio), round(point.y() * ratio)).name()
                            self.assertEqual(actual, expected, (dark, color, point))
                        self.assertEqual(dialog.editor.snapshot(), document)
                        self.assertEqual(dialog.sidecar.surface_background(), themed_color('#ffffff'))
                    dialog.color.setCurrentText('violet')
                    self.assertTrue(dialog.save())
                    self.assertEqual(store.get(record['id'])['color'], 'violet')
                    self.assertEqual(store.get(record['id'])['body'], 'Keep this text')
                    dialog.close()
                    dialog.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    self.app.processEvents()
            finally:
                store.close()
                set_reduced_motion(False)
                apply_appearance(self.app, False)
