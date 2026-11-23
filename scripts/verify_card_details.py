"""Native acceptance of the two-pane card, using disposable data only."""
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
    env.update(QT_QPA_PLATFORM='windows', PATH=r'C:\Windows\System32;C:\Windows', PYTHONUNBUFFERED='1', PYTHONFAULTHANDLER='1')
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=90)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent, QCoreApplication
from PySide6.QtGui import QFont, QPixmap, QPainter, QImage, QColor
from PySide6.QtTest import QTest
from tabla.storage import Store, now
from tabla.workspace import TablaWindow
from tabla.task_card import TaskCardDialog
from tabla.theme import load_fonts

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors = []
def report_error(kind, value, tb):
    import traceback
    traceback.print_exception(kind, value, tb)
    errors.append(str(value))
sys.excepthook = report_error

with tempfile.TemporaryDirectory(prefix='tabla-card-detail-') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    source = Path(folder) / 'Dashboard reference.png'
    image = QImage(160, 96, QImage.Format.Format_ARGB32)
    image.fill(QColor('#f0e8d5'))
    painter = QPainter(image)
    painter.fillRect(8, 8, 144, 18, QColor('#d3c7f2'))
    painter.fillRect(8, 34, 68, 54, QColor('#ffffff'))
    painter.fillRect(84, 34, 68, 54, QColor('#ffffff'))
    painter.end()
    image.save(str(source))
    files = store.attachments.import_files([source])
    project = store.save({'kind': 'project', 'title': 'Website refresh'})
    record = store.save({'kind': 'task', 'title': 'Build dashboard page', 'body': 'Bring the most useful information into one clear view.\n\nKeep the summary readable and make the next action easy to find.',
        'status': 'In progress', 'project': project['id'], 'cover': 'violet', 'date': '2026-10-28',
        'task_labels': [{'name': 'Design UI', 'color': 'violet'}, {'name': 'Front End', 'color': 'blue'}],
        'attachments': files, 'checklists': [{'id': 'launch', 'title': 'Before review', 'items': [
            {'id': 'a', 'text': 'Arrange summary cards', 'checked': True},
            {'id': 'b', 'text': 'Check smaller window sizes', 'checked': False}]}],
        'comments': [{'text': 'The first layout is ready. Focus on hierarchy before adding more detail.', 'at': now()},
                     {'text': 'Keep the labels and dates visible without crowding the title.', 'at': now()}]})
    window = TablaWindow(store)
    window.resize(1500, 940)
    window.show()
    window.navigate('My Tasks')
    QTest.qWait(400)
    for theme in ('Light', 'Dark'):
        window.set_appearance(theme)
        QTest.qWait(250)
        dialog = TaskCardDialog(store, record, parent=window)
        dialog.show()
        QTest.qWait(250)
        assert dialog.area.isVisible() and dialog.comments_area.isVisible()
        assert dialog.area.width() > dialog.comments_area.width()
        shot = QPixmap(window.size())
        shot.fill(QColor('transparent'))
        painter = QPainter(shot)
        painter.drawPixmap(0, 0, window.grab())
        painter.drawPixmap(window.mapFromGlobal(dialog.pos()), dialog.grab())
        painter.end()
        shot.save(str(ROOT / 'design' / 'screenshots' / ('card-details-' + theme.lower() + '.png')))
        left_position = dialog.area.verticalScrollBar().value()
        dialog.comments = [{'text': 'Comment ' + str(i), 'at': now()} for i in range(35)]
        dialog.render_comments()
        assert dialog.older_comments.isVisible()
        dialog.show_earlier_comments()
        assert dialog.older_comments.isHidden()
        assert dialog.area.verticalScrollBar().value() == left_position
        dialog.reject()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(150)
    compact = TaskCardDialog(store, record, parent=window)
    compact.resize(440, 440)
    compact.show()
    QTest.qWait(200)
    assert compact.area.isVisible() and compact.comments_area.isHidden()
    compact.toggle_comments()
    assert compact.area.isHidden() and compact.comments_area.isVisible()
    compact.comment.setText('A compact review comment')
    compact.add_comment()
    compact.toggle_comments()
    assert compact.area.isVisible()
    compact.grab().save(str(ROOT / 'design' / 'screenshots' / 'card-details-compact.png'))
    compact.title.setText('Dashboard ready for review')
    assert compact.save()
    saved = store.get(record['id'])
    assert saved['title'] == 'Dashboard ready for review'
    assert saved['comments'][-1]['text'] == 'A compact review comment'
    assert saved['attachments'] == files and saved['cover'] == 'violet'
    compact.deleteLater()
    window.timer.pause()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
    assert not errors, errors
print('PASS two independent panes, both themes, earlier comments, compact switching, image attachment and saved data', flush=True)
