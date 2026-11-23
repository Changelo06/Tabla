"""Native Home dashboard checks against disposable records only."""
import os
import sys
import subprocess
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env.update(QT_QPA_PLATFORM='windows', PATH=r'C:\Windows\System32;C:\Windows', PYTHONFAULTHANDLER='1')
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=90)
    raise SystemExit(0)
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import QPoint, QRect, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog
from tabla.theme import COLORS, themed_color, load_fonts
app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors = []
sys.excepthook = lambda kind, value, tb: errors.append(str(value))
with tempfile.TemporaryDirectory(prefix='tabla-note-colors-') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    record = store.save({'kind': 'note', 'title': 'A little color, everywhere',
                         'body': 'The opened note keeps its selected color.\n\nBackground patterns remain visible, too.',
                         'color': 'yellow', 'note_template': 'lines'})
    window = TablaWindow(store)
    window.resize(1500, 900)
    window.show()
    window.navigate('Notes')
    for theme in ('Light', 'Dark'):
        window.set_appearance(theme)
        QTest.qWait(200)
        card = window._gallery_cards[record['id']]
        window._note_origin = QRect(card.mapToGlobal(QPoint()), card.size())
        window._note_snapshot = card.grab()
        dialog = NoteDialog(store, store.get(record['id']), parent=window)
        dialog.show()
        QTest.qWait(300)
        snapshot = dialog.editor.snapshot()
        for color in ('yellow', 'blue', 'green', 'violet', 'rose', 'gray'):
            dialog.color.setCurrentText(color)
            QTest.qWait(25)
            image = dialog.grab().toImage()
            ratio = image.devicePixelRatio()
            expected = themed_color('#ffffff' if color == 'gray' else COLORS[color][0])
            for point in (QPoint(20, 150), QPoint(24, dialog.height() - 38)):
                assert image.pixelColor(round(point.x() * ratio), round(point.y() * ratio)).name() == expected
            assert dialog.editor.snapshot() == snapshot
            assert dialog.editor.template == 'lines'
            assert dialog.sidecar.surface_background() == themed_color('#ffffff')
        dialog.color.setCurrentText('yellow')
        QTest.qWait(80)
        dialog.grab().save(str(ROOT / 'design' / 'screenshots' / ('note-color-' + theme.lower() + '.png')))
        dialog.accept()
        QTest.qWait(220)
        assert store.get(record['id'])['color'] == 'yellow'
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    assert not errors, errors
    window.timer.pause()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
print('PASS six colors in both native themes, opening/closing, live changes, templates, saved color and unchanged content')
