"""One task card with description, checklist, labels, dates, files and local activity."""
import copy
import uuid
import sqlite3
from datetime import datetime
from PySide6.QtCore import Qt, QPoint, QDate, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox,
    QMenu, QComboBox, QProgressBar, QMessageBox, QPushButton, QFrame, QSplitter, QGridLayout, QWidgetAction)
from .dialogs import PolishedDialog, dialog_header, dialog_divider, project_picker
from .widgets import label, button, row, scroll, clear, LinkEditor
from .pickers import DateField, ChoiceMenu
from .polish import ColorPicker
from .theme import COLORS, polish_surfaces, themed_color
from .board_model import BoardModel
from .attachment_widgets import AttachmentPanel
from .storage import now


class TaskCardDialog(PolishedDialog):
    def __init__(self, store, record=None, day=None, project=None, parent=None, list_id=None):
        super().__init__(parent)
        self.store, self.record = store, copy.deepcopy(record or {})
        board_id = self.record.get('board')
        if not board_id and store.setting('multi_board_schema') == 1:
            from .boards import BoardCatalog
            selected = store.get(getattr(parent, 'board_id', None)) if getattr(parent, 'board_id', None) and getattr(parent, 'page', None) == 'My Tasks' else None
            board_id = (selected if selected and selected.get('project') == project else BoardCatalog(store).default(project))['id']
        self.model = BoardModel(store, board_id)
        self.result_record, self.pending_navigation = None, None
        self.modal_surface = True
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('Task card')
        self.setMinimumSize(420, 320)
        self.resize(min(1120, max(420, parent.width() - 60)) if parent else 1120,
                    min(730, max(320, parent.height() - 50)) if parent else 730)
        self.list_id = list_id or self.model.column_for(self.record)
        if self.list_id not in {c['id'] for c in self.model.lists()}:
            self.list_id = self.model.lists()[0]['id']
        self.labels_data = copy.deepcopy(self.record.get('task_labels', []))
        self.checklists = copy.deepcopy(self.record.get('checklists', []))
        self.comments = copy.deepcopy(self.record.get('comments', []))
        self.cover = self.record.get('cover')
        self._compact_comments = False
        self._comments_limit = 30
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 12)
        root.setSpacing(0)
        self.cover_header = QFrame()
        self.cover_header.setObjectName('cardCoverHeader')
        header = QHBoxLayout(self.cover_header)
        header.setContentsMargins(22, 14, 18, 14)
        self.list_button = button('', self.choose_list, 'text', 'board', elide=True)
        self.list_button.setMaximumWidth(220)
        self.update_list_title()
        header.addWidget(self.list_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addStretch()
        self.cover_button = button('Cover', self.choose_cover, 'text', 'palette')
        header.addWidget(self.cover_button, 0, Qt.AlignmentFlag.AlignTop)
        self.comments_button = button('Comments', self.toggle_comments, 'text')
        header.addWidget(self.comments_button, 0, Qt.AlignmentFlag.AlignTop)
        if record:
            more = button('•••', self.more_menu, 'text')
            more.setAccessibleName('Card options')
            header.addWidget(more, 0, Qt.AlignmentFlag.AlignTop)
        close = button('×', self.reject, 'text')
        close.setAccessibleName('Close card without saving')
        close.setToolTip('Close')
        close.setFixedWidth(30)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(self.cover_header)
        self.panes = QSplitter(Qt.Orientation.Horizontal)
        self.panes.setChildrenCollapsible(False)
        self.panes.setHandleWidth(1)
        root.addWidget(self.panes, 1)
        host = QWidget()
        self.content = QVBoxLayout(host)
        self.content.setContentsMargins(26, 24, 24, 24)
        self.content.setSpacing(16)
        self.area = scroll(host)
        self.area.setMinimumWidth(0)
        self.panes.addWidget(self.area)
        self.title = QLineEdit(self.record.get('title', ''))
        self.title.setObjectName('itemTitle')
        self.title.setPlaceholderText('Card title')
        self.title.setAccessibleName('Card title')
        self.completed = QCheckBox()
        self.completed.setAccessibleName('Complete card')
        self.completed.setToolTip('Complete')
        self.completed.setChecked(self.record.get('status') == 'Done')
        self.completed.toggled.connect(self.toggle_completed)
        self.content.addLayout(row(self.completed, self.title))
        self.error = label('', 'formError', True)
        self.error.hide()
        self.content.addWidget(self.error)
        self.tools = QHBoxLayout()
        self.tools.setSpacing(6)
        self.tools.addWidget(button('Add', self.add_menu, 'text', 'plus'))
        self.tools.addWidget(button('Dates', self.show_dates, 'text', 'calendar'))
        self.tools.addWidget(button('Checklist', self.add_checklist, 'text', 'tasks'))
        self.attachment_action = button('Attachment', self.choose_files, 'text', 'attachment')
        self.attachment_action.setAccessibleName('Add attachment')
        self.attachment_action.setToolTip('Attachment')
        self.tools.addWidget(self.attachment_action)
        self.tools.addStretch()
        for index in range(self.tools.count()):
            control = self.tools.itemAt(index).widget()
            if control:
                control.setStyleSheet('QPushButton {border:1px solid #dadce0;border-radius:6px;padding:5px 8px;background:transparent;} QPushButton:hover {background:#f1f2f4;}')
        self.content.addLayout(self.tools)
        self.labels_host = QWidget()
        self.labels_layout = QGridLayout(self.labels_host)
        self.labels_layout.setContentsMargins(0, 0, 0, 0)
        self.labels_layout.setSpacing(6)
        self.content.addWidget(self.labels_host)
        self.label_editor = QWidget()
        label_edit_layout = QVBoxLayout(self.label_editor)
        label_edit_layout.setContentsMargins(0, 0, 0, 0)
        self.label_name = QLineEdit()
        self.label_name.setMaxLength(80)
        self.label_name.setPlaceholderText('Label name…')
        self.label_name.setAccessibleName('New label name')
        self.label_color = ColorPicker('blue')
        label_edit_layout.addWidget(self.label_color)
        label_edit_layout.addLayout(row(self.label_name, button('Add label', self.add_label, 'text', 'plus')))
        self.label_name.returnPressed.connect(self.add_label)
        self.content.addWidget(self.label_editor)
        self.label_editor.hide()
        self.render_labels()
        self.properties = QWidget()
        properties_layout = QVBoxLayout(self.properties)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        self.project = project_picker(store, self.record.get('project', project))
        self.project.setAccessibleName('Card project')
        self.priority = QComboBox()
        self.priority.addItems(['Low', 'Medium', 'High'])
        self.priority.setCurrentText(self.record.get('priority', 'Medium'))
        self.priority.setAccessibleName('Card priority')
        properties_layout.addLayout(row(label('Project'), self.project))
        properties_layout.addLayout(row(label('Priority'), self.priority))
        self.content.addWidget(self.properties)
        self.properties.hide()
        self.date_panel = QWidget()
        date_layout = QVBoxLayout(self.date_panel)
        date_layout.setContentsMargins(0, 0, 0, 0)
        self.dated = QCheckBox('Due date')
        self.dated.setChecked(bool(self.record.get('date') or day))
        self.day = DateField()
        self.day.setDisplayFormat('ddd, d MMM yyyy')
        self.day.setDate(QDate.fromString(self.record.get('date') or day or QDate.currentDate().toString('yyyy-MM-dd'), 'yyyy-MM-dd'))
        self.day.setEnabled(self.dated.isChecked())
        self.dated.toggled.connect(self.day.setEnabled)
        date_layout.addLayout(row(self.dated, self.day))
        self.content.addWidget(self.date_panel)
        self.date_panel.setVisible(self.dated.isChecked())
        self.content.addWidget(label('Description', 'section'))
        self.body = LinkEditor(store)
        self.body.setObjectName('itemDetails')
        self.body.setPlainText(self.record.get('body', ''))
        self.body.link_targets = dict(self.record.get('link_targets', {}))
        self.body.linkActivated.connect(self.follow_link)
        self.body.setPlaceholderText('Add a description…')
        self.body.setMinimumHeight(130)
        self.body.setMaximumHeight(220)
        self.content.addWidget(self.body)
        self.content.addLayout(row(label('Checklists', 'section'), None, button('Add', self.add_checklist, 'text', 'plus')))
        self.check_host = QWidget()
        self.check_layout = QVBoxLayout(self.check_host)
        self.check_layout.setContentsMargins(0, 0, 0, 0)
        self.check_layout.setSpacing(16)
        self.content.addWidget(self.check_host)
        self.render_checklists()
        self.attachments = AttachmentPanel(store.attachments, self.record.get('attachments', []), parent=self)        self.attachments.preview_images = True        self.attachments.render()
        self.content.addLayout(row(label('Attachments', 'section'), None, button('Add', self.choose_files, 'text', 'attachment')))
        self.content.addWidget(self.attachments)
        self.body.filesDropped.connect(self.attachments.add_paths)
        self.cover_picker = ColorPicker(self.cover or 'None', parent=self, values=('None', 'blue', 'green', 'yellow', 'violet', 'rose', 'gray'))
        self.cover_picker.currentTextChanged.connect(self.set_cover)
        self.cover_picker.hide()
        self.content.addStretch()
        comments_host = QWidget()
        comments_host.setObjectName('cardComments')
        comments_host.setStyleSheet('QWidget#cardComments {background:' + themed_color('#fafaf9') + ';}')
        comments_layout = QVBoxLayout(comments_host)
        comments_layout.setContentsMargins(22, 24, 22, 24)
        comments_layout.setSpacing(14)
        comments_layout.addWidget(label('Comments', 'section'))
        self.comment = QLineEdit()
        self.comment.setMaxLength(10000)
        self.comment.setPlaceholderText('Write a comment…')
        self.comment.setAccessibleName('New card comment')
        comments_layout.addWidget(self.comment)
        comments_layout.addLayout(row(button('Add comment', self.add_comment, 'text'), None))
        self.comment.returnPressed.connect(self.add_comment)
        self.activity = QVBoxLayout()
        self.activity.setSpacing(14)
        comments_layout.addLayout(self.activity)
        self.older_comments = button('Show earlier comments', self.show_earlier_comments, 'text')
        comments_layout.addWidget(self.older_comments)
        comments_layout.addStretch()
        if self.record.get('created_at'):
            created = datetime.fromisoformat(self.record['created_at']).astimezone().strftime('%b %d, %Y')
            comments_layout.addWidget(label('Created ' + created, 'fieldLabel'))
        self.comments_area = scroll(comments_host)
        self.comments_area.setMinimumWidth(0)
        self.panes.addWidget(self.comments_area)
        self.panes.setStretchFactor(0, 3)
        self.panes.setStretchFactor(1, 2)
        self.panes.setSizes([650, 400])
        self.render_comments()
        dialog_divider(root)
        actions = row()
        actions.setContentsMargins(22, 10, 22, 0)
        self.save_hint = label('Save applies your changes', 'fieldLabel')
        actions.addWidget(self.save_hint)
        actions.addStretch()
        actions.addWidget(button('Cancel', self.reject))
        actions.addWidget(button('Save card', self.save, 'primary'))
        root.addLayout(actions)
        for control in self.findChildren(QPushButton):
            control.setAutoDefault(False)
        self.title.returnPressed.connect(self.body.setFocus)
        self.title.setFocus()
        self.update_cover()
        self.layout_panes()
        polish_surfaces(self)

    def update_cover(self):
        color = COLORS[self.cover][1] if self.cover else themed_color('#fafaf9')
        self.cover_header.setStyleSheet('QFrame#cardCoverHeader {background:' + color + ';border-top-left-radius:8px;border-top-right-radius:8px;}')
        self.cover_header.setFixedHeight(112 if self.cover and self.width() >= 900 else 66)
        for control in self.cover_header.findChildren(QPushButton):
            control.setStyleSheet('QPushButton {background:rgba(0,0,0,25);color:#fff;border:none;border-radius:5px;padding:5px 8px;} QPushButton:hover {background:rgba(0,0,0,50);}' if self.cover else '')

    def set_cover(self, value):
        self.cover = None if value == 'None' else value
        self.update_cover()

    def choose_cover(self):
        menu = QMenu(self)
        picker = ColorPicker(self.cover or 'None', values=('None', 'blue', 'green', 'yellow', 'violet', 'rose', 'gray'))
        picker.currentTextChanged.connect(lambda value: (self.set_cover(value), menu.close()))
        action = QWidgetAction(menu)
        action.setDefaultWidget(picker)
        menu.addAction(action)
        polish_surfaces(menu)
        menu.exec(self.cover_button.mapToGlobal(self.cover_button.rect().bottomLeft()))

    def layout_panes(self):
        compact = self.width() < 900
        self.area.setVisible(not compact or not self._compact_comments)
        self.comments_area.setVisible(not compact or self._compact_comments)
        self.comments_button.setText('Card details' if compact and self._compact_comments else 'Comments' + (' · ' + str(len(self.comments)) if self.comments else ''))
        self.save_hint.setVisible(not compact)
        self.cover_button.setVisible(self.width() >= 540)
        self.list_button.setMaximumWidth(120 if compact else 220)
        self.attachment_action.setText('' if compact else 'Attachment')
        self.update_cover()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'comments_area'):
            self.layout_panes()

    def toggle_comments(self):
        if self.width() < 900:
            self._compact_comments = not self._compact_comments
            self.layout_panes()
        else:
            self.comment.setFocus()
            self.comments_area.ensureWidgetVisible(self.comment)

    def show_dates(self):
        self.date_panel.show()
        self.area.ensureWidgetVisible(self.date_panel)
        self.day.setFocus()

    def choose_files(self):
        self.attachments.choose_files()
        self.area.ensureWidgetVisible(self.attachments)

    def add_menu(self):
        menu = QMenu(self)
        menu.addAction('Labels', lambda: (self.label_editor.show(), self.label_name.setFocus()))
        menu.addAction('Properties', lambda: self.properties.setVisible(not self.properties.isVisible()))
        if self.model.board_id:
            menu.addAction('Move to board', self.choose_board)
        menu.addAction('Cover', self.choose_cover)
        menu.addAction('Checklist', self.add_checklist)
        polish_surfaces(menu)
        sender = self.sender()
        menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()) if isinstance(sender, QWidget) else self.mapToGlobal(QPoint(30, 150)))

    def show_earlier_comments(self):
        self._comments_limit += 30
        self.render_comments()

    def choose_board(self):
        from .boards import BoardCatalog
        boards = BoardCatalog(self.store).boards()
        menu = ChoiceMenu([(b['title'] + ' · ' + ((self.store.get(b.get('project')) or {}).get('title') or 'Personal'), b['id']) for b in boards], self.model.board_id, self, 'Move to board')
        def choose(board_id):
            self.model = BoardModel(self.store, board_id)
            board = self.store.get(board_id)
            index = self.project.findData(board.get('project'))
            self.project.setCurrentIndex(max(0, index))
            column = next((c for c in self.model.lists() if c['status'] == self.record.get('status', 'To do')), self.model.lists()[0])
            self.set_list(column['id'])
        menu.chosen.connect(choose)
        menu.exec(self.mapToGlobal(QPoint(30, 180)))

    def update_list_title(self):
        column = next(c for c in self.model.lists() if c['id'] == self.list_id)
        self.list_button.full_text = column['title'] + ' ▾'
        self.list_button.setText(self.list_button.full_text)
        self.list_button.setMinimumWidth(120)
        self.list_button.setAccessibleName('List: ' + column['title'])
        self.list_button.setToolTip(column['title'])

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.title.deselect)

    def choose_list(self):
        menu = ChoiceMenu([(c['title'], c['id']) for c in self.model.lists()], self.list_id, self, 'Move card to list')
        menu.chosen.connect(self.set_list)
        menu.exec(self.list_button.mapToGlobal(self.list_button.rect().bottomLeft()))

    def set_list(self, value):
        self.list_id = value
        column = next(c for c in self.model.lists() if c['id'] == value)
        self.completed.blockSignals(True)
        self.completed.setChecked(column['status'] == 'Done')
        self.completed.blockSignals(False)
        self.update_list_title()

    def toggle_completed(self, checked):
        if not self.model.board_id:
            self.set_list('done' if checked else 'todo')

    def add_label(self):
        name = self.label_name.text().strip()
        if name and len(self.labels_data) < 50:
            existing = next((t for t in self.labels_data if t['name'].casefold() == name.casefold()), None)
            if existing:
                existing['color'] = self.label_color.currentText()
            else:
                self.labels_data.append({'name': name, 'color': self.label_color.currentText()})
            self.label_name.clear()
            self.render_labels()

    def render_labels(self):
        clear(self.labels_layout)
        for index, tag in enumerate(self.labels_data):
            chip = QWidget()
            chip.setStyleSheet('background:' + COLORS[tag['color']][0] + ';border-radius:5px;')
            layout = QHBoxLayout(chip)
            layout.setContentsMargins(7, 2, 2, 2)
            name = label(tag['name'][:18] + ('…' if len(tag['name']) > 18 else ''))
            name.setToolTip(tag['name'])
            layout.addWidget(name)
            remove = button('×', lambda checked=False, t=tag: (self.labels_data.remove(t), self.render_labels()), 'text')
            remove.setAccessibleName('Remove label ' + tag['name'])
            remove.setFixedWidth(24)
            layout.addWidget(remove)
            self.labels_layout.addWidget(chip, index // 2, index % 2, Qt.AlignmentFlag.AlignLeft)
        self.labels_host.setVisible(bool(self.labels_data))
        polish_surfaces(self.labels_host)
        for control in self.labels_host.findChildren(QPushButton):
            control.setAutoDefault(False)

    def add_checklist(self):
        if len(self.checklists) < 30:
            self.checklists.append({'id': str(uuid.uuid4()), 'title': 'Checklist', 'items': []})
            self.render_checklists()            self.area.ensureWidgetVisible(self.check_host)

    def render_checklists(self):
        clear(self.check_layout)
        for checklist in self.checklists:
            title = QLineEdit(checklist['title'])
            title.setMaxLength(100)
            title.setAccessibleName('Checklist name')
            title.textEdited.connect(lambda text, c=checklist: c.update(title=text.strip() or 'Checklist'))
            self.check_layout.addLayout(row(title, button('Remove', lambda checked=False, c=checklist: (self.checklists.remove(c), self.render_checklists()), 'text')))
            progress = QProgressBar()
            count = len(checklist['items'])
            done = sum(i['checked'] for i in checklist['items'])
            progress.setRange(0, max(1, count))
            progress.setValue(done)
            progress.setFormat(f'{done}/{count}')
            progress.setFixedHeight(16)
            self.check_layout.addWidget(progress)
            for index, item in enumerate(checklist['items']):
                check = QCheckBox()
                check.setChecked(item['checked'])
                check.setAccessibleName('Complete ' + item['text'])
                def toggle(value, i=item, p=progress, c=checklist):
                    i['checked'] = value
                    p.setValue(sum(x['checked'] for x in c['items']))
                    p.setFormat(f'{sum(x["checked"] for x in c["items"])}/{len(c["items"])}')
                check.toggled.connect(toggle)
                text = QLineEdit(item['text'])
                text.setMaxLength(5000)
                text.setAccessibleName('Checklist item')
                text.textEdited.connect(lambda value, i=item: i.update(text=value))
                up = button('↑', lambda checked=False, c=checklist, n=index: self.move_check(c, n, -1), 'text')
                up.setEnabled(index > 0)
                down = button('↓', lambda checked=False, c=checklist, n=index: self.move_check(c, n, 1), 'text')
                down.setEnabled(index < len(checklist['items']) - 1)
                remove = button('×', lambda checked=False, c=checklist, i=item: (c['items'].remove(i), self.render_checklists()), 'text')
                self.check_layout.addLayout(row(check, text, up, down, remove))
            new = QLineEdit()
            new.setMaxLength(5000)
            new.setPlaceholderText('+ Add an item…')
            new.setAccessibleName('New checklist item')
            def add(c=checklist, field=new):
                if field.text().strip() and len(c['items']) < 1000:
                    c['items'].append({'id': str(uuid.uuid4()), 'text': field.text().strip(), 'checked': False})
                    self.render_checklists()
            new.returnPressed.connect(add)
            self.check_layout.addLayout(row(new, button('Add', add, 'text')))
        polish_surfaces(self.check_host)
        for control in self.check_host.findChildren(QPushButton):
            control.setAutoDefault(False)

    def move_check(self, checklist, index, offset):
        other = index + offset
        if 0 <= other < len(checklist['items']):
            checklist['items'][index], checklist['items'][other] = checklist['items'][other], checklist['items'][index]
            self.render_checklists()

    def add_comment(self):
        text = self.comment.text().strip()
        if text and len(self.comments) < 1000:
            self.comments.append({'text': text, 'at': now()})
            self.comment.clear()
            self.render_comments()

    def render_comments(self):
        clear(self.activity)
        if not self.comments:
            self.activity.addWidget(label('No comments yet', 'fieldLabel'))
        for comment in reversed(self.comments[-self._comments_limit:]):
            stamp = datetime.fromisoformat(comment['at']).astimezone().strftime('%b %d, %I:%M %p')
            self.activity.addWidget(label(stamp, 'fieldLabel'))
            text = label(comment['text'], wrap=True)
            text.setStyleSheet('background:' + themed_color('#fafaf9') + ';border:1px solid ' + themed_color('#e5e5e3') + ';border-radius:7px;padding:12px;')
            self.activity.addWidget(text)
        self.older_comments.setVisible(len(self.comments) > self._comments_limit)
        self.comments_button.setText('Comments' + (' · ' + str(len(self.comments)) if self.comments else ''))
        if hasattr(self, 'save_hint'):
            self.layout_panes()

    def save(self):
        if not self.title.text().strip():
            self.error.setText('Give this card a title before saving.')
            self.error.show()
            self.area.ensureWidgetVisible(self.title)
            self.title.setFocus()
            return False
        column = next(c for c in self.model.lists() if c['id'] == self.list_id)
        if self.model.board_id:
            board = self.store.get(self.model.board_id)
            if self.project.currentData() != board.get('project'):
                from .boards import BoardCatalog
                board = BoardCatalog(self.store).default(self.project.currentData())
                self.model = BoardModel(self.store, board['id'])
                self.list_id = self.model.lists()[0]['id']
                column = self.model.lists()[0]
        record = copy.deepcopy(self.record)
        record.update(kind='task', title=self.title.text().strip(), body=self.body.toPlainText(),
            link_targets=self.body.link_targets, project=self.project.currentData(), priority=self.priority.currentText(),
            date=self.day.date().toString('yyyy-MM-dd') if self.dated.isChecked() else None,
            board_list=self.list_id, status=column['status'], task_labels=self.labels_data,
            checklists=self.checklists, comments=self.comments, cover=self.cover,
            attachments=list(self.attachments.items))
        if self.model.board_id:
            record['board'] = self.model.board_id
            record['status'] = 'Done' if self.completed.isChecked() else (column['status'] if column['status'] != 'Done' else 'To do')
        # Preserve legacy searchable labels until the user adds/removes typed labels.
        if self.labels_data or self.record.get('task_labels'):
            record['labels'] = ', '.join(t['name'] for t in self.labels_data)
        if not self.record or self.record.get('board') != self.model.board_id or self.model.column_for(self.record) != self.list_id:
            cards = self.model.cards(self.list_id)
            record['board_position'] = max((c.get('board_position', 0) for c in cards), default=0) + 1024
        try:
            self.result_record = self.store.save(record)
            self.record = self.result_record
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.area.ensureWidgetVisible(self.error)
            return False
        self.accept()
        return True

    def more_menu(self):
        menu = QMenu(self)
        def archive():
            self.record['archived'] = True
            self.save()
        def trash():
            self.record['deleted'] = True
            self.save()
        menu.addAction('Archive card', archive)
        menu.addAction('Move to trash', trash)
        polish_surfaces(menu)
        menu.exec(self.mapToGlobal(QPoint(24, self.height() - 90)))

    def follow_link(self, token):
        target_id = self.body.link_targets.get(token)
        target = self.store.get(target_id) if target_id else self.store.resolve(token, self.record.get('id'))
        if target and not target.get('deleted'):
            self.pending_navigation = target['id']
            self.save()
