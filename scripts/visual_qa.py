"""Render the actual native widgets with a separate sample workspace."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtGui import QPdfWriter, QPainter
from tabla.storage import Store
from tabla.theme import STYLE, load_fonts
from tabla.workspace import TablaWindow as MainWindow
from tabla.dialogs import NoteDialog, ItemDialog

root = Path(__file__).resolve().parents[1]
output = root / "design" / "screenshots"
output.mkdir(parents=True, exist_ok=True)
data = root / "build" / "visual-qa"
data.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setStyle("Fusion")
load_fonts()
app.setStyleSheet(STYLE)
store = Store(data / "tabla.sqlite3")
if not store.records():
    store.seed_demo()
for title, body, color, pinned in (
    ('Ideas for the next project', 'A simpler way to plan the week.\n\n- Keep capture quick\n- Leave room for deep work\n\n#ideas #personal', 'gray', True),
    ('Reading list', '- [ ] Finish the current chapter\n- [ ] Make a short summary\n- [x] Find the book\n\n#learning', 'green', False),
    ('Design review', '## What worked\nClear navigation and fewer interruptions.\n\n## Next\n==Keep the writing area quiet==\n\nRelated: [[Website ideas]]', 'gray', False),
    ('A thought to keep', 'Write it down while it is still fresh.', 'rose', False),
    ('Weekend', '- [ ] Groceries\n- [ ] Walk by the river\n- [ ] Call home', 'yellow', False),
    ('Links worth following', 'Tasks and notes should stay connected.\n\n[[Personal website]]\n[[Draft homepage]]', 'blue', False)):
    if not any(n['title'] == title for n in store.records('note')):
        store.save({'kind': 'note', 'title': title, 'body': body, 'color': color, 'pinned': pinned})
start = date.today() - timedelta(days=date.today().weekday())
for index, title, time, end in ((0, 'Weekly planning', '09:00', '10:00'), (1, 'Design review', '10:00', '11:30'),
    (1, 'Write project notes', '10:30', '11:00'), (2, 'Focused writing', '09:00', '10:30'),
    (3, 'Project check-in', '11:00', '12:00'), (4, 'Weekly reflection', '14:00', '15:00')):
    if not any(r['title'] == title for r in store.records('event')):
        store.save({'kind': 'event', 'title': title, 'date': (start + timedelta(days=index)).isoformat(),
            'time': time, 'end_time': end, 'color': 'blue' if index % 2 == 0 else 'green', 'body': '## Agenda\n\n- [ ] Review progress\n- [ ] Capture next actions'})
imports = data / 'import-examples'
imports.mkdir(exist_ok=True)
(imports / 'Meeting agenda and action items.md').write_text('# Meeting agenda\n\n- Review progress\n- Agree on next steps', encoding='utf-8')
(imports / 'Project reference notes for the design review.txt').write_text('Keep the original document attached to the note.', encoding='utf-8')
pdf = imports / 'Project brief and supporting reference material.pdf'
if not pdf.exists():
    writer = QPdfWriter(str(pdf))
    painter = QPainter(writer)
    painter.drawText(300, 500, 'Tabla project brief')
    painter.end()
if not any(n['title'] == 'Project documents' for n in store.records('note')):
    documents = store.attachments.import_files([pdf, imports / 'Meeting agenda and action items.md', imports / 'Project reference notes for the design review.txt'])
    store.save({'kind': 'note', 'title': 'Project documents', 'body': 'References for the next review.', 'attachments': documents, 'pinned': True, 'color': 'gray'})
window = MainWindow(store)
window.show()
window.mark_day(date.today() + timedelta(days=1), 'yellow')
for page in ("Today", "Calendar", "My Tasks", "Notes", "Focus", "Settings"):
    window.navigate(page)
    app.processEvents()
    QTest.qWait(200)
    app.processEvents()
    window.grab().save(str(output / (page.lower().replace(" ", "-") + ".png")))
window.navigate("Calendar")
window.resize(1100, 760)
app.processEvents()
QTest.qWait(300)
app.processEvents()
window.grab().save(str(output / "calendar-laptop.png"))
window.resize(1500, 960)
window.calendar_mode('Week')
QTest.qWait(300)
app.processEvents()
window.grab().save(str(output / 'calendar-week.png'))
window.calendar_mode('Day')
QTest.qWait(200)
window.grab().save(str(output / 'calendar-day.png'))
window.navigate('My Tasks')
window.set_task_layout('Board')
QTest.qWait(200)
window.grab().save(str(output / 'task-board.png'))
window.set_appearance('Dark')
window.navigate('Notes')
QTest.qWait(250)
window.grab().save(str(output / 'notes-dark.png'))
window.capture.expand()
QTest.qWait(150)
window.capture.grab().save(str(output / 'note-composer-dark.png'))
window.capture.pin.setChecked(True)
QTest.qWait(100)
window.capture.grab().save(str(output / 'note-composer-pinned.png'))
window.capture.pin.setChecked(False)
window.navigate('Calendar')
window.calendar_mode('Week')
QTest.qWait(250)
window.grab().save(str(output / 'calendar-week-dark.png'))
window.set_appearance('Light')
note = NoteDialog(store, next(n for n in store.records('note') if n.get('body') and not n.get('day_annotation')), parent=window)
note.show()
app.processEvents()
QTest.qWait(80)
note.grab().save(str(output / "note-editor.png"))
note.tabs.setCurrentIndex(1)
app.processEvents()
QTest.qWait(80)
note.grab().save(str(output / "note-preview.png"))
note.close()
task = ItemDialog(store, "task", store.records("task")[0], parent=window)
task.show()
app.processEvents()
QTest.qWait(80)
task.grab().save(str(output / "task-editor.png"))
task.close()
project = ItemDialog(store, 'project', parent=window)
project.title.setText('Personal website')
project.body.setPlainText('A place for the website tasks, meeting notes and reference documents.')
project.show()
QTest.qWait(180)
app.processEvents()
project.grab().save(str(output / 'project-editor.png'))
project.color.grab().save(str(output / 'color-swatches.png'))
project.close()
documents = NoteDialog(store, next(n for n in store.records('note') if n['title'] == 'Project documents'), parent=window)
documents.show()
QTest.qWait(180)
documents.grab().save(str(output / 'note-attachments.png'))
documents.attachments.set_compact(True)
QTest.qWait(100)
documents.grab().save(str(output / 'note-attachments-compact.png'))
documents.attachments.set_compact(False)
documents.close()
window.close()
app.processEvents()
store.close()
empty_store = Store(data / "empty-qa.sqlite3")
empty_store.set_setting('sidebar_hidden', False)
empty_store.set_setting('appearance', 'light')
empty_window = MainWindow(empty_store)
empty_window.resize(1500, 960)
empty_window.navigate("Today")
empty_window.show()
QTest.qWait(250)
app.processEvents()
empty_window.grab().save(str(output / "today-empty.png"))
empty_window.resize(1100, 760)
empty_window.navigate("Notes")
QTest.qWait(250)
app.processEvents()
empty_window.grab().save(str(output / "notes-empty-laptop.png"))
if not empty_store.records(state='trash'):
    empty_store.save({'kind': 'note', 'title': 'Meeting ideas', 'body': 'A note you can recover later.\n\n- [ ] Review the plan', 'deleted': True})
    empty_store.save({'kind': 'task', 'title': 'Follow up on the project', 'body': 'Keep the details when restoring this task.', 'deleted': True})
empty_window.navigate('Trash')
QTest.qWait(250)
app.processEvents()
empty_window.grab().save(str(output / 'trash.png'))
empty_window.toggle_sidebar()
QTest.qWait(200)
app.processEvents()
empty_window.grab().save(str(output / 'trash-collapsed.png'))
empty_window.close()
app.processEvents()
empty_store.close()
print("Rendered 25 native UI screenshots in", output)
