from __future__ import annotations

import html
import re
from datetime import date
from urllib.parse import quote, unquote
from PySide6.QtCore import Qt, QDate, QTime, QTimer, Signal, QUrl, QRectF, QPoint, QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QTextCursor, QTextBlockFormat
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDateEdit, QTimeEdit, QCheckBox, QPlainTextEdit, QDialogButtonBox,
    QTabWidget, QTextBrowser, QWidget, QMessageBox, QSpinBox, QLabel, QMenu,
    QFrame, QBoxLayout, QSizePolicy,
)
from .storage import LINK_RE
from .theme import polish_surfaces, themed_color
from .widgets import label, button, row, LinkEditor, clear, scroll, PinButton
from .polish import ColorPicker, color_popup, fade_window
from .attachment_widgets import AttachmentPanel
from .pickers import DateField


class PolishedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setObjectName('roundedDialog')
        self.setStyleSheet('QDialog#roundedDialog {background:transparent;border:none;}')
        self.modal_surface = False
        self._surface_backdrop = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(themed_color('#ffffff')))
        painter.setPen(QPen(QColor(themed_color('#dadce0')), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 8, 8)

    def showEvent(self, event):
        parent = self.parentWidget()
        if self.modal_surface and parent and self._surface_backdrop is None:
            from .layer_effects import WorkspaceBackdrop
            available = parent.rect()
            center = parent.mapToGlobal(available.center())
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
            self._surface_backdrop = WorkspaceBackdrop(parent, parent.grab())
            self._surface_backdrop.show()
            self._surface_backdrop.raise_()
            parent.installEventFilter(self)
        super().showEvent(event)
        fade_window(self)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self._surface_backdrop:
            self._surface_backdrop.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        if self._surface_backdrop:
            self._surface_backdrop.hide()
            self._surface_backdrop.deleteLater()
            self._surface_backdrop = None
            if self.parentWidget():
                self.parentWidget().removeEventFilter(self)
        animation = getattr(self, '_fade', None)
        if animation:
            animation.stop()
        super().hideEvent(event)


def dialog_header(layout, title, close):
    dismiss = button('×', close, 'text')
    dismiss.setFixedSize(30, 30)
    dismiss.setAccessibleName('Close dialog')
    dismiss.setToolTip('Close')
    layout.addLayout(row(label(title, 'fieldLabel'), None, dismiss))


def dialog_divider(layout):
    line = QFrame()
    line.setObjectName('dialogDivider')
    line.setFixedHeight(1)
    layout.addWidget(line)


def project_picker(store, current=None):
    combo = QComboBox()
    combo.addItem("No project", None)
    for p in store.records("project"):
        combo.addItem(p["title"], p["id"])
    index = combo.findData(current)
    combo.setCurrentIndex(max(0, index))
    return combo


class ItemDialog(PolishedDialog):
    def __init__(self, store, kind="task", record=None, day=None, project=None, parent=None):
        super().__init__(parent)
        self.modal_surface = True
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.store, self.record, self.kind = store, dict(record or {}), kind
        self.result_record = None
        self.setWindowTitle(("Edit " if record else "New ") + {"block": "work block"}.get(kind, kind))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setMinimumWidth(500)
        self.resize(580, 650 if kind in ('event', 'block') else 530)
        if kind == 'project':
            self.resize(540, 390)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 20)
        outer.setSpacing(12)
        dialog_header(outer, ('Edit ' if record else 'New ') + {'event': 'meeting / event', 'block': 'work block'}.get(kind, kind), self.reject)
        host = QWidget()
        root = QVBoxLayout(host)
        self.detail_layout = root
        root.setContentsMargins(2, 0, 6, 0)
        root.setSpacing(12)
        self.form_scroll = scroll(host)
        outer.addWidget(self.form_scroll, 1)
        form = QFormLayout()
        self.form = form
        form.setSpacing(8)
        self.title = QLineEdit(self.record.get("title", ""))
        self.title.setPlaceholderText({'project': 'Project name', 'task': 'Task name', 'event': 'Meeting or event name', 'block': 'Work block name'}.get(kind, 'Title'))
        self.title.setObjectName('itemTitle')
        self.title.setAccessibleName('Title')
        root.addWidget(self.title)
        self.error = label('', 'formError', True)
        self.error.setMinimumHeight(18)
        self.error.hide()
        root.addWidget(self.error)
        self.title.textEdited.connect(self.clear_title_error)
        self.project = project_picker(store, self.record.get("project", project))
        if kind != "project":
            form.addRow("Project", self.project)
        self.dated = QCheckBox("Set a date")
        existing_date = self.record.get("date", day)
        self.dated.setChecked(bool(existing_date) or kind in ("event", "block"))
        self.day = DateField()
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat("ddd, d MMM yyyy")
        qdate = QDate.fromString(existing_date or date.today().isoformat(), "yyyy-MM-dd")
        self.day.setDate(qdate if qdate.isValid() else QDate.currentDate())
        self.day.setEnabled(self.dated.isChecked())
        self.dated.toggled.connect(self.day.setEnabled)
        if kind != "project":
            form.addRow(self.dated, self.day)
        self.status = QComboBox()
        self.status.addItems(["To do", "In progress", "Done"])
        self.status.setCurrentText(self.record.get("status", "To do"))
        self.priority = QComboBox()
        self.priority.addItems(["Low", "Medium", "High"])
        self.priority.setCurrentText(self.record.get("priority", "Medium"))
        if kind == "task":
            form.addRow("Status", self.status)
            form.addRow("Priority", self.priority)
        self.time = QTimeEdit()
        self.end = QTimeEdit()
        self.time.setDisplayFormat("h:mm AP")
        self.end.setDisplayFormat("h:mm AP")
        self.time.setTime(QTime.fromString(self.record.get("time", "09:00"), "HH:mm"))
        self.end.setTime(QTime.fromString(self.record.get("end_time", "10:00"), "HH:mm"))
        if kind in ("event", "block"):
            form.addRow("Start", self.time)
            form.addRow("End", self.end)
        self.task = QComboBox()
        self.task.addItem("Choose a task", None)
        for task in store.records("task"):
            self.task.addItem(task["title"], task["id"])
        self.task.setCurrentIndex(max(0, self.task.findData(self.record.get("task"))))
        if kind == "block":
            form.addRow("Task", self.task)
        self.color = ColorPicker()
        self.color.addItems(["blue", "green", "yellow", "violet", "rose", "gray"])
        self.color.setCurrentText(self.record.get("color", "blue"))
        if kind in ("project", "event", "block"):
            form.addRow("Color", self.color)
        root.addLayout(form)
        self.field_error = label('', 'formError', True)
        self.field_error.hide()
        root.addWidget(self.field_error)
        self.body = LinkEditor(store)
        self.body.setPlainText(self.record.get("body", ""))
        self.body.link_targets = dict(self.record.get("link_targets", {}))
        self.body.setObjectName('itemDetails')
        self.body.setPlaceholderText('Agenda, notes and decisions…' if kind == 'event' else 'Add details…')
        self.body.setToolTip('Link an item with [[. Start a checklist with - [ ].')
        self.body.setMinimumHeight(110)
        self.body.setMaximumHeight(140)
        if kind == 'project':
            self.body.setMinimumHeight(75)
            self.body.setMaximumHeight(100)
            self.body.setPlaceholderText('Add a short description…')
        root.addWidget(label('Description' if kind == 'project' else 'Details', 'fieldLabel'))
        root.addWidget(self.body, 1)
        if kind in ('event', 'block'):
            root.addWidget(label('Related items', 'fieldLabel'))
            root.addLayout(row(button('Add linked note', self.add_linked_note, 'text', 'note'),
                               button('Create action task', self.create_action_task, 'text', 'tasks'), None))
        if record:
            targets = []
            for token in set(LINK_RE.findall(record.get("body", ""))):
                target = store.resolve(token, record["id"])
                if target and not target.get("deleted"):
                    targets.append(target)
            self.pending_navigation = None
            for target in targets:
                root.addWidget(button("Open: " + target["title"], lambda checked=False, rid=target["id"]: self.follow_target(rid), "text", "link"))
            for ref in store.backlinks(record["id"])[:3]:
                root.addWidget(button("Referenced by: " + ref["title"], lambda checked=False, rid=ref["id"]: self.follow_target(rid), "text", "link"))
        dialog_divider(outer)
        bottom = QHBoxLayout()
        if record:
            bottom.addWidget(button("Move to trash", self.trash, "danger", "trash"))
        bottom.addStretch()
        bottom.addWidget(button("Cancel", self.reject))
        bottom.addWidget(button("Save", self.save, "primary"))
        outer.addLayout(bottom)
        if parent:
            self.resize(min(self.width(), max(420, parent.width() - 32)), min(self.height(), max(320, parent.height() - 48)))
        self.title.setFocus()
        polish_surfaces(self)

    def clear_title_error(self):
        self.error.clear()
        self.error.hide()
        self.field_error.clear()
        self.field_error.hide()
        self.title.setProperty('invalid', False)
        self.title.style().unpolish(self.title)
        self.title.style().polish(self.title)

    def validation_error(self, message, field):
        self.error.setText(message)
        self.error.setVisible(field is self.title)
        self.field_error.setText(message)
        self.field_error.setVisible(field is not self.title)
        self.form_scroll.ensureWidgetVisible(field)
        field.setFocus()

    def save(self):
        if not self.title.text().strip():
            self.validation_error('Add a title to save this item.', self.title)
            self.title.setProperty('invalid', True)
            self.title.style().unpolish(self.title)
            self.title.style().polish(self.title)
            self.form_scroll.ensureWidgetVisible(self.title)
            self.title.setFocus()
            return
        if self.kind in ("event", "block") and self.end.time() <= self.time.time():
            self.validation_error('Choose an end time after the start time. Split overnight events into two entries.', self.end)
            return
        if self.kind == "block" and self.task.currentData() is None:
            self.validation_error('Choose the task you want to schedule.', self.task)
            return
        r = dict(self.record)
        r.update(kind=self.kind, title=self.title.text().strip(), body=self.body.toPlainText(),
                 project=self.project.currentData(), color=self.color.currentText(), link_targets=self.body.link_targets)
        if self.kind != "project":
            r["date"] = self.day.date().toString("yyyy-MM-dd") if self.dated.isChecked() else None
        if self.kind == "task":
            r.update(status=self.status.currentText(), priority=self.priority.currentText())
        if self.kind in ("event", "block"):
            r.update(time=self.time.time().toString("HH:mm"), end_time=self.end.time().toString("HH:mm"))
        if self.kind == "block":
            r["task"] = self.task.currentData()
        try:
            self.result_record = self.store.save(r)
        except Exception as exc:
            self.validation_error(f'Could not save: {exc}', self.title)
            return
        self.accept()

    def follow_target(self, record_id):
        self.pending_navigation = record_id
        self.save()

    def add_linked_note(self):
        dialog = NoteDialog(self.store, project=self.project.currentData(), parent=self)
        dialog.title.setText((self.title.text().strip() or 'Meeting') + ' · notes')
        if self.record.get('id'):
            dialog.editor.setPlainText('Meeting: [[' + self.record['id'] + ']]\n\n')
        dialog.exec()
        if dialog.record.get('id'):
            self.body.appendPlainText('\nNotes: [[' + dialog.record['id'] + ']]')
        dialog.deleteLater()

    def create_action_task(self):
        dialog = ItemDialog(self.store, 'task', project=self.project.currentData(), parent=self)
        selected = self.body.textCursor().selectedText().strip()
        dialog.title.setText(selected)
        if self.record.get('id'):
            dialog.body.setPlainText('Meeting: [[' + self.record['id'] + ']]')
        if dialog.exec():
            self.body.appendPlainText('\n- [ ] [[' + dialog.result_record['id'] + ']]')
        dialog.deleteLater()

    def trash(self):
        r = dict(self.record)
        r["deleted"] = True
        try:
            self.result_record = self.store.save(r)
        except Exception as exc:
            self.error.setText(f"Could not save: {exc}")
            return
        self.accept()


class LegacyNoteDialog(PolishedDialog):
    changed = Signal()
    navigate = Signal(str)

    def __init__(self, store, record=None, project=None, parent=None):
        super().__init__(parent)
        self.store, self.record = store, dict(record or {})
        self.pending_navigation = None
        self.dirty = False
        self.setWindowTitle("Note · tabla")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        width = min(1080, max(560, parent.width() - 80)) if parent else 1080
        self.resize(width, 680)
        self.setMinimumSize(560, 440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 20)
        outer.setSpacing(16)
        self._context_wide, self._context_compact = True, False
        self.context_toggle = button('Links && sources', self.toggle_context, 'tab', 'sidebar')
        self.context_toggle.setCheckable(True)
        self.context_toggle.setAccessibleName('Show or hide links and sources')
        outer.addLayout(row(label('Note', 'muted'), None, self.context_toggle))
        self.panes = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.panes.setSpacing(20)
        outer.addLayout(self.panes, 1)
        self.reading = QWidget()
        self.reading.setObjectName('noteReadingColumn')
        self.reading.setMaximumWidth(720)
        root = QVBoxLayout(self.reading)
        root.setContentsMargins(6, 0, 6, 0)
        root.setSpacing(14)
        self.panes.addWidget(self.reading, 1)
        self.title = QLineEdit(self.record.get("title", ""))
        self.title.setPlaceholderText("Title")
        self.title.setStyleSheet("font-family:'Inter';font-size:20px;font-weight:600;border:none;background:transparent;padding:6px;")
        self.project = project_picker(store, self.record.get("project", project))
        self.color = ColorPicker()
        self.color.addItems(["yellow", "violet", "blue", "green", "rose", "gray"])
        self.color.setCurrentText(self.record.get("color", "yellow"))
        self.pin = PinButton(self.record.get('pinned', False))
        root.addLayout(row(self.title, self.pin))
        self.labels = QLineEdit(self.record.get("labels", ""))
        self.labels.setPlaceholderText("Labels, separated by commas")
        self.details = QWidget()
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addLayout(row(label('Project', 'muted'), self.project, label('Color', 'muted'), self.color))
        detail_layout.addWidget(self.labels)
        self.details.hide()
        self.tabs = QTabWidget()
        self.editor = LinkEditor(store)
        self.editor.setPlaceholderText('Take a note…')
        self.editor.setPlainText(self.record.get("body", ""))
        self.editor.link_targets = dict(self.record.get("link_targets", {}))
        self.editor.linkActivated.connect(lambda token: self.follow(QUrl('tabla:' + quote(token, safe=''))))
        self.preview = QTextBrowser()
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.anchorClicked.connect(self.follow)
        self.checklist = QWidget()
        self.check_layout = QVBoxLayout(self.checklist)
        self.check_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.tabs.addTab(self.editor, "Write")
        self.tabs.addTab(self.preview, "Read")
        self.tabs.addTab(scroll(self.checklist), "Checklist")
        self.tabs.currentChanged.connect(self.tab_changed)
        root.addWidget(self.tabs, 1)
        self.sidecar = QFrame()
        self.sidecar.setObjectName('noteSidecar')
        self.sidecar.setStyleSheet('QFrame#noteSidecar {background:#fafaf9;border:1px solid #e5e5e3;border-radius:12px;}')
        side = QVBoxLayout(self.sidecar)
        side.setContentsMargins(14, 16, 14, 12)
        context_host = QWidget()
        context = QVBoxLayout(context_host)
        context.setContentsMargins(0, 0, 0, 0)
        context.setSpacing(10)
        self.links_heading = label('Links', 'section')
        context.addWidget(self.links_heading)
        self.outgoing = QVBoxLayout()
        self.outgoing.setSpacing(4)
        context.addLayout(self.outgoing)
        self.backlinks = QVBoxLayout()
        self.backlinks.setSpacing(4)
        context.addLayout(self.backlinks)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet('background:#e5e5e3;')
        context.addWidget(divider)
        self.sources_heading = label('Sources', 'section')
        add_source = button('', lambda: self.attachments.choose_files(), 'icon', 'plus')
        add_source.setToolTip('Add source files')
        add_source.setAccessibleName('Add source files')
        context.addLayout(row(self.sources_heading, None, add_source))
        self.attachments = AttachmentPanel(store.attachments, self.record.get('attachments', []), self.record.get('attachment_display') == 'compact', parent=self)
        self.attachments.max_height = None
        self.attachments.render()
        context.addWidget(self.attachments)
        self.empty_sources = label('Keep reference files beside your note.\nAdd a PDF, document or image.', 'muted', True)
        context.addWidget(self.empty_sources)
        context.addStretch()
        side.addWidget(scroll(context_host))
        self.panes.addWidget(self.sidecar)
        self.attachments.changed.connect(self.refresh_sources)
        self.editor.filesDropped.connect(self.attachments.add_paths)
        root.addWidget(self.details)
        self.link_label = label("", "muted", True)
        root.addWidget(self.link_label)
        self.status = label("", "muted")
        root.addWidget(self.status)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(450)
        self.autosave.timeout.connect(self.save)
        self.attachments.changed.connect(self.mark_dirty)
        self.changed.connect(self.refresh_backlinks)
        for widget, signal in ((self.title, "textChanged"), (self.editor, "textChanged"),
                               (self.labels, "textChanged"), (self.project, "currentIndexChanged"),
                               (self.color, "currentIndexChanged"), (self.pin, "toggled")):
            getattr(widget, signal).connect(self.mark_dirty)
        controls = QHBoxLayout()
        for text, glyph, tip, callback in (
            ('A', None, 'Formatting', self.format_menu),
            ('', 'palette', 'Note color', self.color_menu),
            ('', 'attachment', 'Attach files', self.attachments.choose_files),
            ('', 'tasks', 'Checklist', lambda: self.tabs.setCurrentIndex(2)),
            ('', 'more', 'More options', self.more_menu),
            ('', 'undo', 'Undo', self.editor.undo),
            ('', 'redo', 'Redo', self.editor.redo)):
            control = button(text, callback, 'text', glyph)
            control.setToolTip(tip)
            control.setAccessibleName(tip)
            control.setFixedWidth(32)
            if tip == 'Formatting':
                control.setStyleSheet('border:none;background:transparent;font-size:16px;text-decoration:underline;padding:4px;')
            if tip in ('Undo', 'Redo'):
                control.setEnabled(False)
                (self.editor.undoAvailable if tip == 'Undo' else self.editor.redoAvailable).connect(control.setEnabled)
            controls.addWidget(control)
        controls.addStretch()
        controls.addWidget(button("Close", self.accept, 'text'))
        root.addLayout(controls)
        self.refresh_backlinks()
        self.refresh_sources()
        self.layout_context()
        if self.record.get('id') and self.record.get('body'):
            self.tabs.setCurrentIndex(1)
        else:
            self.editor.setFocus()
        polish_surfaces(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sidecar'):
            self.layout_context()

    def toggle_context(self):
        if self.width() < 880:
            self._context_compact = not self._context_compact
        else:
            self._context_wide = not self._context_wide
        self.layout_context()

    def layout_context(self):
        compact = self.width() < 880
        self.panes.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)
        self.sidecar.setMinimumWidth(0 if compact else 280)
        self.sidecar.setMaximumWidth(16777215 if compact else 280)
        self.sidecar.setMaximumHeight(max(130, min(220, self.height() // 3)) if compact else 16777215)
        visible = self._context_compact if compact else self._context_wide
        self.sidecar.setVisible(visible)
        self.context_toggle.setChecked(visible)
        self.context_toggle.setProperty('active', visible)
        self.context_toggle.style().unpolish(self.context_toggle)
        self.context_toggle.style().polish(self.context_toggle)

    def refresh_sources(self):
        count = len(self.attachments.items)
        self.sources_heading.setText('Sources' + (f'  {count}' if count else ''))
        self.empty_sources.setVisible(not count)

    def format_menu(self):
        menu = QMenu(self)
        for title, marker in (('Bold', '**'), ('Italic', '*'), ('Highlight', '=='), ('Inline code', '`')):
            menu.addAction(title, lambda checked=False, m=marker: self.wrap_selection(m))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def wrap_selection(self, marker):
        from PySide6.QtGui import QTextCursor
        self.tabs.setCurrentIndex(0)
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(marker + selected + marker)
        if not selected:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(marker))
            self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def color_menu(self):
        color_popup(self, self.color.currentText(), self.color.setCurrentText, self.sender() if isinstance(self.sender(), QWidget) else None)

    def more_menu(self):
        menu = QMenu(self)
        for title, callback in (
            ('Write', lambda: self.tabs.setCurrentIndex(0)),
            ('Preview', lambda: self.tabs.setCurrentIndex(1)),
            ('Checklist', lambda: self.tabs.setCurrentIndex(2)),
            ('Add checklist item', self.add_checklist),
            ('Labels and details', lambda: self.details.setVisible(not self.details.isVisible())),
            ('Create task', self.create_task)):
            menu.addAction(title, callback)
        menu.addAction('Attach files…', self.attachments.choose_files)
        compact = menu.addAction('Filename-only attachments')
        compact.setCheckable(True)
        compact.setChecked(self.attachments.compact)
        compact.toggled.connect(self.attachments.set_compact)
        if self.record.get('id'):
            menu.addSeparator()
            menu.addAction('Archive', self.archive)
            menu.addAction('Move to trash', self.trash)
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def highlight_selection(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText('==' + cursor.selectedText() + '==')
        else:
            cursor.insertText('==highlight==')
        self.editor.setFocus()

    def mark_dirty(self, *args):
        self.dirty = True
        self.status.setText("Saving on this device...")
        self.autosave.start()

    def save(self):
        self.autosave.stop()
        if not self.dirty:
            return True
        r = dict(self.record)
        r.update(kind="note", title=self.title.text().strip() or "Untitled note", body=self.editor.toPlainText(),
                 project=self.project.currentData(), color=self.color.currentText(), labels=self.labels.text(),
                 pinned=self.pin.isChecked(), link_targets=self.editor.link_targets,
                 attachments=list(self.attachments.items), attachment_display='compact' if self.attachments.compact else 'details')
        try:
            self.record = self.store.save(r)
        except Exception as exc:
            self.status.setText(f"Not saved: {exc}. Keep this window open and retry Done.")
            return False
        self.dirty = False
        self.status.setText("Saved on this device")
        self.changed.emit()
        return True

    def done(self, result):
        if not self.save():
            return
        super().done(result)

    def tab_changed(self, index):
        self.save()
        if index == 1:
            def replace(match):
                token = match.group(1)
                target = self.store.resolve(token, self.record.get("id"))
                display = (target or {}).get("title", token)
                return f'[{display.replace("[", "").replace("]", "")}](tabla:{quote(token, safe="")})'
            self.preview.setMarkdown(LINK_RE.sub(replace, self.editor.toPlainText()))
            rendered = self.preview.toHtml()
            self.preview.setHtml(re.sub(r'==([^<\n]+)==', r'<span style="background-color:#fff0a5">\1</span>', rendered))
            cursor = QTextCursor(self.preview.document())
            cursor.select(QTextCursor.SelectionType.Document)
            spacing = QTextBlockFormat()
            spacing.setLineHeight(140, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            spacing.setBottomMargin(10)
            cursor.mergeBlockFormat(spacing)
            self.link_label.setText("")
        elif index == 2:
            self.render_checklist()
        else:
            self.link_label.setText("")

    def render_checklist(self):
        clear(self.check_layout)
        lines = self.editor.toPlainText().splitlines()
        found = False
        for number, text in enumerate(lines):
            match = re.match(r"^\s*[-*] \[([ xX])\] (.*)$", text)
            if match:
                found = True
                check = QCheckBox(match.group(2))
                check.setChecked(match.group(1).lower() == "x")
                check.toggled.connect(lambda value, n=number: self.toggle_line(n, value))
                self.check_layout.addWidget(check)
        if not found:
            self.check_layout.addWidget(label("Add checklist items in Write using - [ ] or the Add checklist button.", "muted", True))
        self.check_layout.addStretch()

    def toggle_line(self, number, checked):
        lines = self.editor.toPlainText().splitlines()
        if number < len(lines):
            lines[number] = re.sub(r"\[[ xX]\]", "[x]" if checked else "[ ]", lines[number], count=1)
            self.editor.setPlainText("\n".join(lines))
            self.save()

    def add_checklist(self):
        self.tabs.setCurrentIndex(0)
        self.editor.appendPlainText("- [ ] ")
        self.editor.setFocus()

    def create_task(self):
        if not self.record.get("id"):
            self.mark_dirty()
        if not self.save():
            return
        source = self.preview if self.tabs.currentIndex() == 1 else self.editor
        selected = source.textCursor().selectedText().replace("\u2029", " ").strip()
        r = {"title": selected or self.title.text() or "Task from note",
             "body": f'Reference: [[{self.record["id"]}]]', "project": self.project.currentData()}
        dialog = ItemDialog(self.store, "task", record=None, project=self.project.currentData(), parent=self)
        dialog.title.setText(r["title"])
        dialog.body.setPlainText(r["body"])
        if dialog.exec():
            task = dialog.result_record
            self.editor.appendPlainText(f'\nTask: [[{task["id"]}]]')
            self.save()
            self.refresh_backlinks()

    def refresh_backlinks(self):
        clear(self.outgoing)
        clear(self.backlinks)
        tokens = list(dict.fromkeys(LINK_RE.findall(self.editor.toPlainText())))
        self.links_heading.setText('Links' + (f'  {len(tokens)}' if tokens else ''))
        if not tokens:
            self.outgoing.addWidget(label('No linked notes yet.\nType [[ while writing to connect an idea.', 'muted', True))
        for token in tokens:
            chosen = self.editor.link_targets.get(token)
            target = self.store.get(chosen) if chosen else self.store.resolve(token, self.record.get('id'))
            title = target['title'] if target else token
            link = button(title, lambda checked=False, value=token: self.follow(QUrl('tabla:' + quote(value, safe=''))), 'text', 'link', elide=True)
            link.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            link.setToolTip(title + (' · Not created yet' if not target else ' · ' + target['kind']))
            link.setAccessibleName('Open linked item ' + title)
            link.setProperty('linkTarget', target['id'] if target else token)
            if target and not target.get('deleted'):
                link.clicked.disconnect()
                link.clicked.connect(lambda checked=False, rid=target['id']: self.open_target(rid))
            self.outgoing.addWidget(link)
        refs = self.store.backlinks(self.record.get("id")) if self.record.get("id") else []
        if refs:
            self.backlinks.addWidget(label('Linked from', 'muted'))
        for ref in refs:
            link = button(ref['title'], lambda checked=False, target=ref['id']: self.open_target(target), 'text', 'note', elide=True)
            link.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            link.setToolTip(ref['title'])
            link.setProperty('backlinkTarget', ref['id'])
            self.backlinks.addWidget(link)

    def open_target(self, record_id):
        if not self.save():
            return
        self.pending_navigation = record_id
        self.accept()

    def follow(self, url):
        if url.scheme() != "tabla":
            self.link_label.setText("External links are not opened automatically. Copy the address if you want to visit it.")
            return
        token = unquote(url.toString()[6:])
        target = self.store.resolve(token, self.record.get("id"))
        if target and not target.get("deleted"):
            self.open_target(target["id"])
        elif target:
            self.link_label.setText("This item is in Trash. Restore it from Trash in the sidebar to reopen it.")
        else:
            candidates = [r for r in self.store.records(state="all") if r["title"].casefold() == token.casefold()]
            if len(candidates) > 1:
                self.link_label.setText("More than one item has that title. Insert a link using an item's ID to choose precisely.")
                return
            choice = QMessageBox.question(self, "Create linked note", f'Create a note called "{token}"?')
            if choice == QMessageBox.StandardButton.Yes:
                target = self.store.save({"kind": "note", "title": token, "body": ""})
                self.open_target(target["id"])

    def archive(self):
        self.mark_dirty()
        if self.save():
            self.record["archived"] = True
            self.store.save(self.record)
            self.changed.emit()
            self.accept()

    def trash(self):
        self.mark_dirty()
        if self.save():
            self.record["deleted"] = True
            self.store.save(self.record)
            self.changed.emit()
            self.accept()


from .note_dialog import NoteDialog


class TimerSettingsDialog(PolishedDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.modal_surface = True
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Focus preferences")
        self.resize(450, 340)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        dialog_header(root, 'Pomodoro settings', self.reject)
        form = QFormLayout()
        self.values = {}
        for key, title, default in (("focus_minutes", "Focus minutes", 25), ("short_minutes", "Short break", 5),
                                    ("long_minutes", "Long break", 15), ("long_interval", "Long break every N focus sessions", 4)):
            spin = QSpinBox()
            spin.setRange(1, 180 if key != "long_interval" else 20)
            spin.setValue(store.setting(key, default))
            self.values[key] = spin
            form.addRow(title, spin)
        root.addLayout(form)
        root.addWidget(label("Changes apply to the next timer. Breaks start when you press Start.", "muted", True))
        root.addWidget(button("Save preferences", self.save, "primary"))
        polish_surfaces(self)

    def save(self):
        for key, spin in self.values.items():
            self.store.set_setting(key, spin.value())
        self.accept()
