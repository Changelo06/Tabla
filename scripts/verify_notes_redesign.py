"""Native Windows visual and interaction checks, using only an isolated QA profile."""
import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PATH'] = r'C:\Windows\System32;C:\Windows'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=55)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPainter, QPixmap, QTextCursor, QImage
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
errors = []
def report_error(kind, value, tb):
    import traceback
    errors.append(str(value))
    traceback.print_exception(kind, value, tb)
sys.excepthook = report_error
profile = ROOT / 'build' / 'notes-redesign-qa'
profile.mkdir(parents=True, exist_ok=True)
store = Store(profile / 'tabla.sqlite3')
if not store.records():
    store.seed_demo()
paths = []
for index in range(5):
    path = profile / f'Study reference {index + 1}.txt'
    path.write_text(f'Reference {index + 1}', encoding='utf-8')
    paths.append(path)
files = store.attachments.import_files(paths)
note = store.save({'kind': 'note', 'title': 'A little room to think', 'pinned': True,
    'body': 'Keep the important things close, and make space for the next idea.\n\n'
            '**A clearer plan for the week**\n\n'
            'Write down what matters, connect it to [[Website ideas]], and take one small step.\n\n'
            '- [ ] Review the project brief\n- [x] Capture the first idea\n\n'
            '**Reference notes**\n\nA focused writing space keeps the work comfortable.', 'attachments': files})
window = TablaWindow(store)
window.resize(1500, 900)
window.show()
results = []
try:
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        window.navigate('Notes')
        QTest.qWait(320)
        assert window.notes_edge.isVisible() and not window.notes_edge.image.isNull(), (window.notes_edge.isVisible(), window.notes_edge.image.isNull(), window.notes_edge.geometry(), window.notes_scroll.viewport().geometry())
        window.grab().save(str(ROOT / 'design' / 'screenshots' / ('notes-layers-' + appearance.lower() + '.png')))
        dialog = NoteDialog(store, note, parent=window)
        dialog.show()
        QTest.qWait(300)
        assert not hasattr(dialog, 'tabs')
        assert dialog.sidecar.isWindow() and dialog.sidecar.isVisible()
        assert dialog.sidecar.x() > dialog.geometry().right()
        assert dialog.source_rows.count() == 3
        assert len(dialog.attachments.items) == 5
        assert dialog.edited.isVisible()
        assert abs(dialog.geometry().center().x() - window.mapToGlobal(window.rect().center()).x()) < 3
        canvas = QPixmap(window.size())
        painter = QPainter(canvas)
        painter.drawPixmap(0, 0, window.grab())
        for surface in (dialog, dialog.sidecar):
            point = window.mapFromGlobal(surface.pos())
            painter.drawPixmap(point, surface.grab())
        painter.end()
        output = ROOT / 'design' / 'screenshots' / ('notes-redesign-' + appearance.lower() + '.png')
        canvas.save(str(output))
        # Keyboard editing, a table, and document persistence on the actual Windows backend.
        dialog.editor.moveCursor(QTextCursor.MoveOperation.End)
        dialog.editor.insertPlainText('\n\nNative editing check')
        dialog.editor.selectAll()
        QTest.keyClick(dialog.editor, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier)
        dialog.set_background('dots')
        dialog.save()
        assert dialog.record.get('document') and dialog.record['note_template'] == 'dots'
        if appearance == 'Dark':
            image_path = profile / 'Reference image.png'
            image = QImage(240, 140, QImage.Format.Format_ARGB32)
            image.fill('#b9d8ec')
            image.save(str(image_path))
            dialog.editor.moveCursor(QTextCursor.MoveOperation.Start)
            dialog.editor.insert_images([str(image_path)])
            cursor = QTextCursor(dialog.editor.document())
            cursor.setPosition(0)
            dialog.editor.setTextCursor(cursor)
            dialog.editor.resize_image(140)
            dialog.editor.wrap_image('right')
            dialog.editor.relayout_images()
            QTest.qWait(40)
            image_cursor = dialog.editor.image_at_cursor()
            assert dialog.editor.image_rect(image_cursor).center().x() > dialog.editor.viewport().width() / 2, 'Resize handles are detached from floating image'
            first_body = dialog.editor.document().begin().next()
            assert first_body.layout().lineAt(0).width() < dialog.editor.viewport().width() - 100, 'Text did not flow around the floating image'
            dialog.editor.moveCursor(QTextCursor.MoveOperation.End)
            table = dialog.editor.insert_table(3, 3)
            for r, values in enumerate((('Topic', 'Status', 'Next step'), ('English', 'Reading', 'Chapter 2'), ('Math', 'Practice', 'Quiz'))):
                for c, value in enumerate(values):
                    table.cellAt(r, c).firstCursorPosition().insertText(value)
            dialog.editor.moveCursor(QTextCursor.MoveOperation.Start)
            QTest.qWait(100)
            assert all(dialog.source_rows.itemAt(i + 1).widget().y() >= dialog.source_rows.itemAt(i).widget().geometry().bottom() for i in range(2)), 'Source rows overlap after insertion'
            picture = QPixmap(window.size())
            p = QPainter(picture)
            p.drawPixmap(0, 0, window.grab())
            for surface in (dialog, dialog.sidecar):
                p.drawPixmap(window.mapFromGlobal(surface.pos()), surface.grab())
            p.end()
            picture.save(str(ROOT / 'design' / 'screenshots' / 'notes-redesign-rich.png'))
            dialog.save()
        dialog.accept()
        QTest.qWait(190)
        assert not dialog.sidecar.isVisible() and dialog._backdrop is None
        dialog.deleteLater()
        results.append(appearance + ': centered editor, separate right sidecar, three-source limit, formatting and persistence')
    window.resize(640, 480)
    QTest.qWait(150)
    compact = NoteDialog(store, note, parent=window)
    compact.show()
    QTest.qWait(150)
    assert not compact.sidecar.isVisible()
    compact.context_toggle.click()
    assert compact.sidecar.isVisible() and compact.sidecar.isWindow()
    compact.close()
    QTest.qWait(190)
    compact.deleteLater()
    assert not errors, errors
    results.append('Compact: external context opens on demand; no unhandled callbacks')
    (ROOT / 'build' / 'notes-redesign-verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
finally:
    window.close()
    store.close()
