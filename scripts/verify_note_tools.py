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
from datetime import date, timedelta
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtGui import QImage, QFont, QTextCursor
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog
from tabla.theme import load_fonts
app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter',10))
errors=[]
sys.excepthook=lambda kind,value,tb: errors.append(str(value))
with tempfile.TemporaryDirectory(prefix='tabla-note-tools-') as folder:
    store=Store(Path(folder)/'tabla.sqlite3')
    day=date.today().replace(day=15)
    for delta,color in ((0,'rose'),(1,'green'),(2,'violet'),(4,'yellow')):
        store.save({'kind':'event','title':color+' event','date':(day+timedelta(days=delta)).isoformat(),'color':color})
    store.save({'kind':'note','title':'Day highlight','date':day.isoformat(),'day_annotation':True,'day_color':'blue'})
    path=Path(folder)/'example.png'
    image=QImage(240,120,QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    image.save(str(path))
    record=store.save({'kind':'note','title':'Images and lists','color':'yellow'})
    window=TablaWindow(store)
    window.resize(1500,900)
    window.show()
    for theme in ('Light','Dark'):
        window.set_appearance(theme)
        window.navigate('Today')
        QTest.qWait(220)
        assert window.home.calendar.day_colors[day.isoformat()]==['blue','rose']
        assert window.chrome.minimize.x()<window.chrome.maximize.x()<window.chrome.close_button.x()
        window.grab().save(str(ROOT/'design'/'screenshots'/('calendar-glow-'+theme.lower()+'.png')))
        window.navigate('Notes')
        QTest.qWait(180)
        capture=window.capture
        capture.expand()
        image_button=next(b for b in capture.findChildren(QPushButton) if b.accessibleName()=='Insert image')
        with patch('tabla.note_dialog.QFileDialog.getOpenFileNames',return_value=([str(path)],'Images')):
            image_button.click()
        assert capture.attachments.items
        dialog=NoteDialog(store,store.get(record['id']),parent=window)
        dialog.show()
        QTest.qWait(180)
        dialog.editor.setPlainText('Collect ideas\nChoose the next step\nMake room to think')
        dialog.editor.selectAll()
        lists=next(b for b in dialog.findChildren(QPushButton) if b.accessibleName()=='Cycle list style')
        for caption in ('Bullets','Numbers','Letters'):
            lists.click()
            assert lists.toolTip()==caption
        assert 'C. Make room to think' in dialog.editor.plain_body()
        dialog.editor.moveCursor(QTextCursor.MoveOperation.End)
        dialog.editor.appendPlainText('')
        insert=next(b for b in dialog.findChildren(QPushButton) if b.accessibleName()=='Insert image')
        with patch('tabla.note_dialog.QFileDialog.getOpenFileNames',return_value=([str(path)],'Images')):
            insert.click()
        QTest.qWait(120)
        assert dialog.attachments.items
        dialog.grab().save(str(ROOT/'design'/'screenshots'/('note-tools-'+theme.lower()+'.png')))
        dialog.resize(420,500)
        QTest.qWait(150)
        for button in dialog.findChildren(QPushButton):
            if button.isVisible() and button.accessibleName() in ('Cycle list style','Insert image'):
                assert button.mapTo(dialog,button.rect().bottomRight()).x()<dialog.width()-12
        assert dialog.save()
        dialog.close()
        QTest.qWait(220)
        saved=store.get(record['id'])
        assert saved['attachments'] and 'C. Make room to think' in saved['body']
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
    window.timer.pause()
    window.close()
    QTest.qWait(100)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
    assert not errors,errors
print('PASS native image insertion, three list styles, compact toolbar, persistence, calendar color rings and yellow/green/red window order in both themes')
