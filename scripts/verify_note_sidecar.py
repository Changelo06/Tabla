"""Native Windows note reader/context QA with an isolated sample workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PATH'] = r'C:\Windows\System32;C:\Windows'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=30)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QPdfWriter, QPainter
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
profile = ROOT / 'build' / 'note-sidecar-qa'
store = Store(profile / 'tabla.sqlite3')
if not store.records(state='all'):
    plan = store.save({'kind': 'note', 'title': 'Launch plan', 'body': 'A small, useful first release.'})
    research = store.save({'kind': 'note', 'title': 'Research and inspiration', 'body': 'Keep capture quick and reading calm.'})
    agenda = profile / 'Meeting agenda.md'
    agenda.write_text('# Meeting agenda\n\n- Review the plan\n- Choose the next step', encoding='utf-8')
    brief = profile / 'Product brief.pdf'
    pdf = QPdfWriter(str(brief))
    painter = QPainter(pdf)
    painter.drawText(100, 200, 'Tabla — Product brief')
    painter.end()
    note = store.save({'kind': 'note', 'title': 'A clearer plan for the week', 'pinned': True,
        'body': 'Keep the thinking in one place, with the references close by.\n\n'
                '**What matters this week**\n\n'
                'Finish the first useful version, make the writing feel natural, and leave room for the next idea.\n\n'
                'The [[' + plan['id'] + ']] brings the next steps together. [[' + research['id'] + ']] keeps the reasoning behind those choices.\n\n'
                '**Meeting notes**\n\n'
                'A quiet writing area makes it easier to follow a thought. Links and source documents belong beside the note, ready when needed.\n\n'
                '- [ ] Review the product brief\n- [ ] Turn the next decision into a task',
        'attachments': store.attachments.import_files([brief, agenda])})
    store.save({'kind': 'task', 'title': 'Review the week', 'body': '[[' + note['id'] + ']]'})
    store.save({'kind': 'note', 'title': 'Weekly review', 'body': 'Discuss [[' + note['id'] + ']]'})
note = next(n for n in store.records('note') if n['title'] == 'A clearer plan for the week')
window = TablaWindow(store)
window.resize(1400, 850)
window.show()
verified = []
try:
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        dialog = NoteDialog(store, note, parent=window)
        try:
            dialog.show()
            QTest.qWait(220)
            assert dialog.tabs.currentIndex() == 1 and dialog.sidecar.isVisible()
            assert dialog.sidecar.x() > dialog.reading.x() + dialog.reading.width() - 1
            assert dialog.sidecar.isAncestorOf(dialog.attachments)
            assert len([b for b in dialog.sidecar.findChildren(QPushButton) if b.property('linkTarget')]) == 2
            assert len([b for b in dialog.sidecar.findChildren(QPushButton) if b.property('backlinkTarget')]) == 2
            dialog.grab().save(str(ROOT / 'design' / 'screenshots' / ('note-sidecar-' + appearance.lower() + '.png')))
            if appearance == 'Dark':
                dialog.resize(640, 520)
                QTest.qWait(120)
                assert not dialog.sidecar.isVisible()
                dialog.context_toggle.click()
                QTest.qWait(100)
                assert dialog.sidecar.isVisible() and dialog.sidecar.y() > dialog.reading.y()
                dialog.grab().save(str(ROOT / 'design' / 'screenshots' / 'note-sidecar-compact.png'))
            verified.append(appearance)
        finally:
            dialog.close()
            dialog.deleteLater()
    report = {'platform': app.platformName(), 'themes': verified, 'read_on_open': True,
              'outgoing_and_incoming_links': True, 'sources_beside_note': True, 'compact_context_toggle': True}
    (ROOT / 'build' / 'note-sidecar-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
finally:
    window.timer.pause()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    store.close()
