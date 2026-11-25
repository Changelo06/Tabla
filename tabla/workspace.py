"""Tabla's reference-led native workspace, on the existing local data model."""
from __future__ import annotations
import calendar
import math
import re
from pathlib import Path
from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt, QTimer, QDate, QSize, QPoint, QEvent
from PySide6.QtGui import QFont, QColor, QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QDialog, QMenu, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QPushButton, QInputDialog, QFileDialog, QProgressBar)
from PySide6.QtWidgets import QSizePolicy
from .window import MainWindow
from .widgets import label, button, row, panel, scroll, clear, ClickCard, NoteCard, PinButton, StripeDivider, SegmentedSwitch, ThemePresetCard, CountdownDisplay
from .surfaces import CalendarCell, RecordButton, Timeline, Masonry, QuickCapture, BoardColumn
from .theme import icon, navigation_icon, COLORS, apply_appearance, polish_surfaces
from .storage import LINK_RE
from .dialogs import NoteDialog, ItemDialog, PolishedDialog, dialog_header, dialog_divider
from .polish import fade_in, install_polish, set_reduced_motion, color_popup, ColorPicker
from .chrome import TitleBar, WindowEdges
from .attachments import FILE_FILTER
from .attachment_widgets import AttachmentPanel
from .pickers import ChoiceMenu
from .board_model import BoardModel
from .boards import BoardCatalog
from .task_board import TaskBoard


class TablaWindow(MainWindow):
    def __init__(self, store, defer_render=False):
        self.board_catalog = BoardCatalog(store)
        self.board_catalog.migrate()
        available_boards = self.board_catalog.boards()
        remembered = store.setting('selected_board')
        self.board_id = remembered if any(b['id'] == remembered for b in available_boards) else available_boards[0]['id']
        self.boards_sidebar = None
        self._boards_hidden = store.setting('boards_sidebar_hidden', False)
        from PySide6.QtWidgets import QApplication
        apply_appearance(QApplication.instance(), store.setting('appearance', 'light'))
        self.collapsed = store.setting('sidebar_hidden', False)
        self._history, self._history_index, self._history_locked = [], -1, False
        install_polish(QApplication.instance())
        set_reduced_motion(store.setting('reduce_motion', False))
        from . import foley
        foley.set_enabled(store.setting('tactile_sound', False))
        self.task_view = store.setting('tasks_presentation', 'Board')
        self.note_view = 'Grid'
        self.task_query = ''
        self.task_sort = 'Date'
        self.trash_query = ''
        self.capture = None
        self._capture_to_restore = None
        self._board_scroll = {}
        self._sidebar_key = None
        super().__init__(store, defer_render=True)
        if self.task_view == 'Board':
            self.task_filter = 'All'
        self.root.layout().setContentsMargins(0, 0, 0, 0)
        self.root.layout().setSpacing(0)
        self.sidebar_layout.setContentsMargins(10, 14, 10, 16)
        self.sidebar_layout.setSpacing(3)
        self.content.setContentsMargins(36, 18, 36, 18)
        self.statusBar().hide()
        self.setMinimumSize(360, 400)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMouseTracking(True)
        self.chrome = TitleBar(self)
        from .board_sidebar import BoardSidebar
        self.boards_sidebar = BoardSidebar(self)
        self.root.layout().insertWidget(1, self.boards_sidebar)
        header_host = QWidget(self)
        header_layout = QVBoxLayout(header_host)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.addWidget(self.chrome)
        self.stripe_divider = StripeDivider(header_host, height=4)
        header_layout.addWidget(self.stripe_divider)
        self.setMenuWidget(header_host)
        from .windows_frame import available as _win_native_frame
        self.window_edges = None if _win_native_frame() else WindowEdges(self)
        self.resize_debounce.timeout.disconnect()
        self.resize_debounce.timeout.connect(self.reflow)
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(30000)
        self._clock_timer.timeout.connect(self._update_calendar_clock)
        self._clock_timer.start()
        if not defer_render:
            self.render_sidebar()
            self.render()
            self.remember_location()
        QShortcut(QKeySequence('Alt+Left'), self, activated=lambda: self.history_step(-1))
        QShortcut(QKeySequence('Alt+Right'), self, activated=lambda: self.history_step(1))

    def navigate(self, page):
        if page in ('Board', 'My Tasks'):
            board = self.store.get(self.board_id)
            state = self.store.setting('board_view_' + self.board_id, {})
            self.task_query, self.task_filter = state.get('query', ''), state.get('filter', 'All')
            self.page, self.project_id, self.search_query = 'My Tasks', board.get('project'), ''
            self.render_sidebar()
            self.render()
        else:
            super().navigate(page)
        self.remember_location()

    def scoped(self, kind, state='active', query=''):
        if kind == 'task' and self.page == 'My Tasks':
            return self.store.records(kind, state=state, query=query, board=self.board_id)
        return super().scoped(kind, state, query)

    def open_record(self, record_id):
        record = self.store.get(record_id)
        if record and record['kind'] == 'board' and not record.get('deleted'):
            if record.get('archived'):
                self.archived_boards()
            else:
                self.select_board(record_id)
            return
        super().open_record(record_id)

    def board_records(self):
        records = self.store.records('task', query=self.task_query, board=self.board_id)
        if self.task_filter == 'Open':
            records = [r for r in records if r.get('status') != 'Done']
        elif self.task_filter == 'Completed':
            records = [r for r in records if r.get('status') == 'Done']
        elif self.task_filter == 'Overdue':
            records = [r for r in records if r.get('status') != 'Done' and r.get('date') and r['date'] < date.today().isoformat()]
        return records

    def save_board_state(self):
        board = getattr(self, 'board', None)
        try:
            if board is not None and board.model.board_id and board.model.board_id == self.board_id:
                state = board.snapshot()
                state.update(query=self.task_query, filter=self.task_filter)
                self.store.set_setting('board_view_' + board.model.board_id, state)
        except RuntimeError:
            pass

    def select_board(self, board_id):
        board = self.store.get(board_id)
        if not board or board['kind'] != 'board' or board.get('archived') or board.get('deleted'):
            return
        self.save_board_state()
        self.board_id, self.page, self.project_id = board_id, 'My Tasks', board.get('project')
        state = self.store.setting('board_view_' + board_id, {})
        self.task_query, self.task_filter = state.get('query', ''), state.get('filter', 'All')
        self.store.set_setting('selected_board', board_id)
        self.render_sidebar()
        self.render()
        self.remember_location()

    def refresh(self):
        board = getattr(self, 'board', None)
        if self.page == 'My Tasks' and board is not None:
            try:
                if board.model.board_id == self.board_id and board.isVisible():
                    board.reconcile()
                    if self.boards_sidebar is not None:
                        self.boards_sidebar.refresh()
                    return
            except RuntimeError:
                pass
        super().refresh()

    def toggle_boards_sidebar(self):
        self.set_boards_sidebar_hidden(not self._boards_hidden)

    def set_boards_sidebar_hidden(self, hidden):
        self._boards_hidden = bool(hidden)
        self.store.set_setting('boards_sidebar_hidden', self._boards_hidden)
        self.sync_boards_sidebar()

    def sync_boards_sidebar(self):
        wide = self.width() >= 1000
        visible = self.page == 'My Tasks' and wide and not self._boards_hidden
        if self.boards_sidebar is not None:
            self.boards_sidebar.setVisible(visible)
        control = getattr(self, 'boards_toggle', None)
        if control is not None:
            try:
                control.setChecked(visible)
                control.setText('Boards')
                text = ('Hide boards sidebar' if visible else 'Show boards sidebar') if wide else 'Choose a board'
                control.setToolTip(text)
                control.setAccessibleName(text)
            except RuntimeError:
                pass  # The previous page's toolbar has been deleted.

    def boards_navigation(self):
        if self.width() >= 1000:
            self.toggle_boards_sidebar()
        else:
            self.board_picker()

    def board_picker(self):
        choices = []
        for b in self.board_catalog.boards():
            project = self.store.get(b.get('project')) if b.get('project') else None
            choices.append((b['title'] + ' · ' + (project['title'] if project else 'Personal'), b['id']))
        menu = ChoiceMenu(choices, self.board_id, self, 'Boards')
        menu.chosen.connect(self.select_board)
        anchor = self.sender()
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()) if isinstance(anchor, QWidget) else self.mapToGlobal(QPoint(80, 120)))

    def new_board(self):
        self.edit_board(None)

    def edit_board(self, board_id=None):
        from .dialogs import project_picker
        existing = self.store.get(board_id) if board_id else None
        dialog = PolishedDialog(self)
        dialog.modal_surface = True
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(min(480, self.width() - 30), 300)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        dialog_header(layout, 'Board settings' if existing else 'New board', dialog.reject)
        name = QLineEdit(existing['title'] if existing else '')
        name.setMaxLength(100)
        name.setPlaceholderText('Board name')
        name.setAccessibleName('Board name')
        layout.addWidget(name)
        layout.addWidget(label('Project', 'fieldLabel'))
        project = project_picker(self.store, existing.get('project') if existing else self.project_id)
        layout.addWidget(project)
        error = label('', 'formError', True)
        layout.addWidget(error)
        layout.addStretch()
        def save():
            if not name.text().strip():
                error.setText('Give the board a name.')
                return
            try:
                with self.store.atomic():
                    if existing:
                        existing.update(title=name.text().strip(), project=project.currentData())
                        board = self.store.save(existing)
                        rows = self.store.db.execute("SELECT payload FROM records WHERE kind='task' AND json_extract(payload, '$.board')=?", (board_id,)).fetchall()
                        import json
                        for row_data in rows:
                            card = json.loads(row_data[0])
                            if card.get('project') != board.get('project'):
                                card['project'] = board.get('project')
                                self.store.save(card)
                    else:
                        board = self.board_catalog.create(name.text(), project.currentData())
            except Exception as exc:
                error.setText(str(exc))
                return
            dialog.accept()
            self.select_board(board['id'])
        layout.addLayout(row(None, button('Cancel', dialog.reject), button('Save' if existing else 'Create board', save, 'primary')))
        name.returnPressed.connect(save)
        name.setFocus()
        dialog.exec()
        dialog.deleteLater()

    def board_menu(self, board_id):
        menu = QMenu(self)
        menu.addAction('New board', self.new_board)
        menu.addAction('Rename or move', lambda: self.edit_board(board_id))
        menu.addAction('Show boards sidebar', lambda: self.set_boards_sidebar_hidden(False))
        menu.addAction('Archive board', lambda: self.archive_board(board_id))
        anchor = self.sender()
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()) if isinstance(anchor, QWidget) else self.mapToGlobal(QPoint(120, 140)))

    def archive_board(self, board_id):
        self.save_board_state()
        board = self.store.get(board_id)
        board['archived'] = True
        self.store.save(board)
        active = self.board_catalog.boards()
        self.select_board((active[0] if active else self.board_catalog.default())['id'])

    def archived_boards(self):
        dialog = PolishedDialog(self)
        dialog.modal_surface = True
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(min(520, self.width() - 30), min(460, self.height() - 30))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        dialog_header(layout, 'Archived boards', dialog.reject)
        host = QWidget()
        items = QVBoxLayout(host)
        layout.addWidget(scroll(host))
        def restore(board):
            board['archived'] = False
            self.store.save(board)
            dialog.accept()
            self.select_board(board['id'])
        for board in self.board_catalog.boards(archived=True):
            items.addLayout(row(label(board['title'], wrap=True), None, button('Restore', lambda checked=False, b=board: restore(b), 'text')))
        if not self.board_catalog.boards(archived=True):
            items.addWidget(label('No archived boards', 'muted'))
        items.addStretch()
        dialog.exec()
        dialog.deleteLater()

    def open_project(self, project_id):
        super().open_project(project_id)
        self.remember_location()

    def project_tab(self, route):
        super().project_tab(route)
        self.remember_location()

    def remember_location(self):
        if self._history_locked:
            return
        state = (self.page, self.project_id, self.search_query if self.page == 'Search' else '', self.board_id)
        if self._history_index >= 0 and self._history[self._history_index] == state:
            return
        self._history = self._history[:self._history_index + 1] + [state]
        self._history_index = len(self._history) - 1
        if hasattr(self, 'chrome'):
            self.chrome.sync()

    def history_step(self, delta):
        index = self._history_index + delta
        if not 0 <= index < len(self._history):
            return
        self._history_index = index
        self._history_locked = True
        try:
            self.save_board_state()
            self.page, self.project_id, self.search_query, self.board_id = self._history[index]
            if self.page == 'My Tasks':
                state = self.store.setting('board_view_' + self.board_id, {})
                self.task_query, self.task_filter = state.get('query', ''), state.get('filter', 'All')
            self.render_sidebar()
            self.render()
        finally:
            self._history_locked = False
        self.chrome.sync()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'chrome'):
            self.chrome.sync()

    def reflow(self):
        self.render_sidebar()
        self.render(preserve_capture=True)

    def showEvent(self, event):
        super().showEvent(event)
        from .windows_frame import configure
        configure(self)

    def nativeEvent(self, event_type, message):
        from .windows_frame import handle
        result = handle(self, message)
        return result if result is not None else super().nativeEvent(event_type, message)

    def import_note_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Import files into a note', '', FILE_FILTER)
        if paths:
            try:
                record = self.create_import_note(paths)
                self.navigate('Notes')
                self.edit_note(record)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, 'Could not import files', str(exc))

    def create_import_note(self, paths):
        attachments = self.store.attachments.import_files(paths)
        first = Path(paths[0])
        body = ''
        if len(paths) == 1 and first.suffix.lower() in ('.txt', '.md', '.markdown') and first.stat().st_size <= 1024 * 1024:
            body = first.read_text(encoding='utf-8-sig', errors='replace')
        return self.store.save({'kind': 'note', 'title': first.stem if len(paths) == 1 else 'Imported files',
            'body': body, 'attachments': attachments, 'attachment_display': 'details', 'color': 'gray', 'project': self.project_id})

    def show_note_layout(self, layout):
        self.note_view = layout
        self.navigate('Notes')

    def show_calendar_layout(self, mode):
        self.calendar_view = mode
        self.navigate('Calendar')

    def set_reduce_motion(self, checked):
        self.store.set_setting('reduce_motion', bool(checked))
        set_reduced_motion(checked)
        if hasattr(self, 'chrome'):
            self.chrome.reduce_motion.blockSignals(True)
            self.chrome.reduce_motion.setChecked(checked)
            self.chrome.reduce_motion.blockSignals(False)

    def set_tactile_sound(self, checked):
        from . import foley
        self.store.set_setting('tactile_sound', bool(checked))
        foley.set_enabled(bool(checked))
        if checked:
            foley.play('pluck')
        if hasattr(self, 'chrome') and hasattr(self.chrome, 'tactile_sound'):
            self.chrome.tactile_sound.blockSignals(True)
            self.chrome.tactile_sound.setChecked(bool(checked))
            self.chrome.tactile_sound.blockSignals(False)

    def show_help(self):
        self.help_dialog('Quick guide', 'Capture notes\nUse Take a note to write quickly. Pin, label or color it from the composer.\n\nConnect ideas\nType [[ for a reference. Ctrl-click to follow it.\n\nPlan work\nEdit task properties inline. Drag calendar entries to reschedule.\n\nAttachments\nUse the paperclip, drop files into a note, or File → Import files. Files are copied into your local workspace. Use More → Filename-only attachments for compact cards.\n\nRecovery\nOpen Trash in the icon sidebar to restore deleted items.\n\nMotion\nUse Settings → Reduce motion to turn off animations.')

    def show_shortcuts(self):
        self.help_dialog('Keyboard shortcuts', 'Ctrl+N     New note\nCtrl+Shift+T     New task\nCtrl+K     Search\nCtrl+1     Home\nCtrl+2     Calendar\nAlt+Left / Alt+Right     Back / Forward\nCtrl+Z / Ctrl+Y     Undo / Redo while writing\nCtrl+click     Follow a note reference\nEscape     Close the note editor and save')

    def show_about(self):
        from . import __version__
        self.help_dialog('About Tabla', 'Tabla ' + __version__ + '\n\nYour personal task, calendar, notes and focus workspace.\n\nYour data is stored locally.\n\nBuilt with Qt for Python and SQLite.')

    def help_dialog(self, title, text):
        dialog = PolishedDialog(self)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(530, 500)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(25, 22, 25, 20)
        layout.addWidget(label(title, 'section'))
        layout.addWidget(scroll(label(text, 'reading', True)), 1)
        layout.addLayout(row(None, button('Close', dialog.accept)))
        polish_surfaces(dialog)
        dialog.exec()

    def resizeEvent(self, event):
        if getattr(self, 'boards_sidebar', None) is not None:
            self.sync_boards_sidebar()
        # All working views retain the full workspace width. No timer side rail.
        if hasattr(self, 'context'):
            self.context.hide()
        if hasattr(self, 'resize_debounce'):
            size_class = (self.height() >= 850, self.height() < 650, self.width() < 800, self.width() < 900)
            if getattr(self, '_rebuild_height_class', None) != size_class:
                self._rebuild_height_class = size_class
                self.resize_debounce.start()
        if hasattr(self, 'content'):
            padding = 16 if self.width() < 800 else 28 if self.width() < 1100 else 40
            self.content.setContentsMargins(padding, 16 if self.height() < 650 else 24, padding, 14)
            self.update_capture_width()
        super(MainWindow, self).resizeEvent(event)

    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        self.store.set_setting('sidebar_hidden', self.collapsed)
        self.sidebar.setVisible(not self.collapsed)
        self.update_capture_width()
        if not self.collapsed:
            fade_in(self.sidebar)
        if hasattr(self, 'chrome'):
            self.chrome.sync()

    def update_capture_width(self):
        if getattr(self, 'capture', None) is not None:
            margins = self.content.contentsMargins()
            available = self.width() - (0 if self.collapsed else 64) - margins.left() - margins.right() - 12
            self.capture.setFixedWidth(min(650, max(200, available)))
            self.capture.queue_text_resize()

    def _sync_sidebar_states(self, dark):
        for name, btn in getattr(self, 'nav_buttons', {}).items():
            active = self.page == name and (not self.project_id or name == 'My Tasks')
            btn.setProperty('active', active)
            if name != 'Trash':
                glyph = {'Today': 'home', 'Calendar': 'calendar', 'My Tasks': 'board', 'Notes': 'note', 'Focus': 'clock'}[name]
                btn.setIcon(navigation_icon(glyph, active, dark))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if getattr(self, '_projects_btn', None) is not None:
            active = bool(self.project_id) and self.page != 'My Tasks'
            self._projects_btn.setProperty('active', active)
            self._projects_btn.setIcon(navigation_icon('folder', active, dark))
            self._projects_btn.style().unpolish(self._projects_btn)
            self._projects_btn.style().polish(self._projects_btn)
        if getattr(self, '_settings_btn', None) is not None:
            active = self.page == 'Settings'
            self._settings_btn.setProperty('active', active)
            self._settings_btn.setIcon(navigation_icon('settings', active, dark))
            self._settings_btn.style().unpolish(self._settings_btn)
            self._settings_btn.style().polish(self._settings_btn)
        self.sidebar.setVisible(not self.collapsed)
        self.update_mini_timer()

    def render_sidebar(self):
        from PySide6.QtWidgets import QApplication
        from .tokens import current_tokens
        short = self.height() < 560
        t = current_tokens()
        dark = t.dark
        key = (short, t.key)
        if getattr(self, '_sidebar_key', None) == key and getattr(self, 'nav_buttons', None):
            self._sync_sidebar_states(dark)
            return
        self._sidebar_key = key
        clear(self.sidebar_layout)
        self.sidebar.setFixedWidth(64)
        self.sidebar.setVisible(not self.collapsed)
        self.sidebar_layout.setContentsMargins(10, 6 if short else 15, 10, 6 if short else 14)
        self.sidebar_layout.setSpacing(2 if short else 5)
        mark = QLabel()
        mark.setPixmap(icon('brand', t.ink_primary, 24, preserve_color=True).pixmap(24, 24))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedHeight(34)
        mark.setVisible(not short)
        self.sidebar_layout.addWidget(mark)
        self.search = QLineEdit(self.search_query, self.sidebar)
        self.search.hide()
        self.sidebar_layout.addSpacing(5 if short else 12)
        self.nav_buttons = {}
        for name, title, glyph in (('Today', 'Home', 'home'), ('Calendar', 'Calendar', 'calendar'),
                ('My Tasks', 'Board', 'board'), ('Notes', 'Notes', 'note'),
                ('Focus', 'Focus', 'clock'), ('Trash', 'Trash', 'trash')):
            if name == 'Trash':
                self.sidebar_layout.addSpacing(5 if short else 9)
                divider = QFrame()
                divider.setObjectName('trashDivider')
                divider.setProperty('tablaThemed', True)
                divider.setFixedSize(28, 1)
                divider.setStyleSheet(f'background:{t.border_subtle};')
                self.sidebar_layout.addWidget(divider, 0, Qt.AlignmentFlag.AlignHCenter)
                self.sidebar_layout.addSpacing(5 if short else 9)
            active = self.page == name and (not self.project_id or name == 'My Tasks')
            btn = self.rail_button(title, glyph, lambda checked=False, p=name: self.navigate(p), active)
            if name == 'Trash':
                red, tint = (t.danger, t.danger_soft)
                btn.setProperty('tablaThemed', True)
                btn.setIcon(icon('trash', red, 21, preserve_color=True))
                btn.setStyleSheet(f'QPushButton#nav {{padding:6px;text-align:center;border-radius:10px;color:{red};}}'
                    f'QPushButton#nav:hover, QPushButton#nav[active="true"] {{background:{tint};}}')
            self.sidebar_layout.addWidget(btn)
            self.nav_buttons[name] = btn
        self._projects_btn = None
        self.sidebar_layout.addStretch()
        self.mini_timer = self.rail_button('Running focus timer', 'clock', lambda: self.navigate('Focus'))
        self.sidebar_layout.addWidget(self.mini_timer)
        self.update_mini_timer()
        self._settings_btn = self.rail_button('Settings and backups', 'settings', lambda: self.navigate('Settings'), self.page == 'Settings')
        self.sidebar_layout.addWidget(self._settings_btn)
        polish_surfaces(self.sidebar)

    def rail_button(self, title, glyph, callback, active=False):
        from PySide6.QtWidgets import QApplication
        btn = button('', callback, 'nav', glyph)
        btn.setProperty('active', active)
        btn.setIcon(navigation_icon(glyph, active, bool(QApplication.instance().property('tablaDark'))))
        btn.setFixedSize(44, 30 if self.height() < 560 else 40)
        btn.setIconSize(QSize(21, 21))
        btn.setToolTip(title)
        btn.setAccessibleName(title)
        btn.setStyleSheet('QPushButton#nav {padding:6px;text-align:center;border-radius:9px;}')
        return btn

    def show_projects(self):
        menu = QMenu(self)
        menu.setMinimumWidth(230)
        menu.addAction('Projects').setEnabled(False)
        for project in reversed(self.store.records('project')):
            action = menu.addAction(project['title'], lambda checked=False, pid=project['id']: self.open_project(pid))
            action.setCheckable(True)
            action.setChecked(project['id'] == self.project_id)
        if not self.store.records('project'):
            menu.addAction('No projects yet').setEnabled(False)
        menu.addSeparator()
        menu.addAction(icon('plus'), 'New project', self.new_project)
        anchor = self.sender() if isinstance(self.sender(), QWidget) else self.sidebar
        polish_surfaces(menu)
        menu.exec(anchor.mapToGlobal(QPoint(anchor.width() + 6, 0)))

    def focus_search(self):
        if hasattr(self, 'chrome'):
            self.chrome.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.chrome.search.selectAll()

    def run_workspace_search(self, text):
        if text.strip():
            self.search_query = text.strip()
            self.page, self.project_id = 'Search', None
            self.render_sidebar()
            self.render()
            self.remember_location()

    def render(self, preserve_capture=False):
        if getattr(self, '_closed', False):
            return
        from PySide6.QtWidgets import QApplication
        previous_focus = QApplication.instance().focusWidget() if preserve_capture else None
        self.save_board_state()
        self._board_scroll = self.store.setting('board_view_' + self.board_id, {})
        if self.page == 'My Tasks':
            current_board = self.store.get(self.board_id)
            if not current_board or current_board.get('archived') or current_board.get('deleted'):
                self.board_id = self.board_catalog.default(self.project_id)['id']
                current_board = self.store.get(self.board_id)
            if self.project_id != current_board.get('project'):
                candidates = [b for b in self.board_catalog.boards() if b.get('project') == self.project_id]
                self.board_id = (candidates[0] if candidates else self.board_catalog.default(self.project_id))['id']
        if self.boards_sidebar is not None:
            self.sync_boards_sidebar()
            if self.page == 'My Tasks':
                self.boards_sidebar.refresh()
        self._board_scroll = self.store.setting('board_view_' + self.board_id, {})
        if getattr(self, 'capture', None) is not None:
            if preserve_capture:
                self._capture_to_restore = self.capture
                self.capture.setParent(None)
            else:
                self.capture.flush()
        clear(self.content)
        self.capture = None
        short = self.height() < 650
        narrow = self.width() < 580
        medium = 580 <= self.width() < 860
        if narrow:
            self.content.setContentsMargins(16, 12, 16, 14)
        elif medium:
            self.content.setContentsMargins(24, 16, 24, 16)
        else:
            self.content.setContentsMargins(36, 18, 36, 18)
        self.content.setSpacing(8 if (short or narrow) else 14 if medium else 16)
        project = self.store.get(self.project_id) if self.project_id else None
        names = {'Today': 'Home', 'My Tasks': self.store.get(self.board_id)['title'], 'Settings': 'Settings and backups', 'Search': 'Search'}
        title = names['My Tasks'] if self.page == 'My Tasks' else project['title'] if project else names.get(self.page, self.page)
        heading = label(title, 'title')
        heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        heading.setMinimumWidth(0)
        if short or narrow:
            heading.setStyleSheet('font-size:23px;font-weight:700;')

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(2)
        title_stack.addWidget(heading)
        if self.page == 'Today':
            title_stack.addWidget(label(date.today().strftime('%A, %B %d'), 'subtitle'))

        action_widgets = []
        if self.page == 'Today':
            from .tokens import current_tokens
            t_hdr = current_tokens()
            quick_note = button('Quick note', self.new_note, 'text', 'note')
            quick_note.setToolTip('Quick note')
            quick_note.setProperty('tablaThemed', True)
            pad = '5px 10px' if narrow else '6px 12px'
            quick_note.setStyleSheet(
                f'QPushButton {{border:1px solid {t_hdr.border_strong};border-radius:10px;padding:{pad};'
                f'background:{t_hdr.bg_elevated};color:{t_hdr.ink_primary};}}'
                f'QPushButton:hover {{background:{t_hdr.bg_surface_hover};}}'
                f'QPushButton:focus {{border:1px solid {t_hdr.accent};}}'
            )
            action_widgets.append(quick_note)
            new_task_btn = button('New task', self.new_task, 'primary', 'plus')
            action_widgets.append(new_task_btn)
        elif self.page == 'My Tasks':
            from .tokens import current_tokens
            t_hdr = current_tokens()
            action_widgets.append(button('New card', self.new_task, 'primary', 'plus'))
            board_opts = button('', lambda: self.board_menu(self.board_id), 'text', 'more-h')
            board_opts.setAccessibleName('Board options')
            board_opts.setToolTip('Board options (rename, move, archive)')
            board_opts.setFixedSize(32, 32)
            board_opts.setProperty('tablaThemed', True)
            board_opts.setStyleSheet(
                f'QPushButton {{background:{t_hdr.bg_elevated};color:{t_hdr.ink_secondary};'
                f'border:1px solid {t_hdr.border_subtle};border-radius:9px;padding:0;}}'
                f'QPushButton:hover {{background:{t_hdr.bg_surface_hover};color:{t_hdr.ink_primary};border-color:{t_hdr.border_strong};}}'
            )
            action_widgets.append(board_opts)

        if project and self.page != 'My Tasks':
            edit = button('' if (short or narrow) else 'Edit project', lambda: self.edit_item(project), 'text', 'settings' if (short or narrow) else None)
            edit.setToolTip('Edit project')
            edit.setAccessibleName('Edit project')
            action_widgets.insert(0, edit)

        if action_widgets and (not narrow or short):
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(8)
            head.addLayout(title_stack, 1)
            for w_act in action_widgets:
                head.addWidget(w_act, 0, Qt.AlignmentFlag.AlignVCenter)
            self.content.addLayout(head)
        else:
            header_wrap = QVBoxLayout()
            header_wrap.setContentsMargins(0, 0, 0, 0)
            header_wrap.setSpacing(8)
            header_wrap.addLayout(title_stack)
            if action_widgets:
                act_row = QHBoxLayout()
                act_row.setContentsMargins(0, 0, 0, 0)
                act_row.setSpacing(8)
                for w_act in action_widgets:
                    act_row.addWidget(w_act)
                act_row.addStretch()
                header_wrap.addLayout(act_row)
            self.content.addLayout(header_wrap)
        if project and self.page != 'My Tasks':
            tabs = row()
            for title, route in (('Calendar', 'Calendar'), ('Board', 'My Tasks'), ('Notes', 'Notes')):
                btn = button(title, lambda checked=False, p=route: self.project_tab(p), 'sectionTab')
                btn.setProperty('active', route == self.page)
                tabs.addWidget(btn)
            tabs.addStretch()
            self.content.addLayout(tabs)
        method = {'Today': self.render_today, 'Calendar': self.render_calendar, 'My Tasks': self.render_tasks,
                  'Notes': self.render_notes, 'Focus': self.render_focus, 'Search': self.render_search,
                  'Settings': self.render_settings, 'Trash': self.render_trash}[self.page]
        method()
        self.context.hide()
        polish_surfaces(self.workspace)
        if hasattr(self, 'chrome'):
            self.chrome.sync()
            if self.page not in ('Notes', 'My Tasks', 'Today'):
                fade_in(self.workspace, 140)
        for name, btn in getattr(self, 'nav_buttons', {}).items():
            btn.setProperty('active', name == self.page and (not self.project_id or name == 'My Tasks'))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if previous_focus and self.capture and self.capture.isAncestorOf(previous_focus):
            previous_focus.setFocus(Qt.FocusReason.OtherFocusReason)

    def render_trash(self):
        self.content.addWidget(label('Deleted items stay here until you restore them.', 'subtitle'))
        query = QLineEdit(self.trash_query)
        query.setPlaceholderText('Search trash')
        query.setAccessibleName('Search trash')
        query.setMaximumWidth(480)
        query.returnPressed.connect(lambda: self.search_trash(query.text()))
        self.content.addLayout(row(query, button('Search', lambda: self.search_trash(query.text()), 'text', 'search'), None))
        records = self.store.records(state='trash', query=self.trash_query)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(12)
        names = {'note': 'Note', 'task': 'Task', 'event': 'Meeting / event', 'project': 'Project', 'block': 'Work block'}
        for record in records:
            card, items = panel('card', 16)
            items.setSpacing(8)
            restore = button('Restore', lambda checked=False, rid=record['id']: self.restore_trashed(rid), glyph='import')
            restore.setAccessibleName('Restore ' + record['title'])
            restore.setProperty('trashRecordId', record['id'])
            items.addLayout(row(label(record['title'], 'section', True), None, restore))
            project = self.store.get(record.get('project'))
            metadata = names.get(record['kind'], record['kind'].capitalize())
            if project:
                metadata += ' · ' + project['title']
            items.addWidget(label(metadata, 'muted', True))
            if record.get('body'):
                preview = LINK_RE.sub(lambda m: (self.store.resolve(m[1], record['id']) or {}).get('title', m[1]), record['body'])
                items.addWidget(label(preview[:280] + ('…' if len(preview) > 280 else ''), 'reading', True))
            v.addWidget(card)
        if not records:
            v.addWidget(label('No matching items' if self.trash_query else 'Trash is empty', 'section'))
            v.addWidget(label('Try another search.' if self.trash_query else 'Items you delete will appear here, ready to restore.', 'muted', True))
        v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def search_trash(self, text):
        self.trash_query = text.strip()
        self.render()

    def restore_trashed(self, record_id):
        record = self.store.get(record_id)
        if record and record.get('deleted'):
            record.update(deleted=False, archived=False)
            self.store.save(record)
            self.refresh()

    def recovery_dialog(self, state):
        if state == 'trash':
            self.navigate('Trash')
        else:
            super().recovery_dialog(state)

    def set_notes_filter(self, state):
        if state == 'Trash':
            self.navigate('Trash')
        else:
            super().set_notes_filter(state)

    def render_settings(self):
        from .tokens import THEME_PRESETS, resolve_theme
        super().render_settings()
        scroll_item = self.content.itemAt(self.content.count() - 1)
        scroll_widget = scroll_item.widget() if scroll_item else None
        host_layout = scroll_widget.widget().layout() if scroll_widget and hasattr(scroll_widget, 'widget') and scroll_widget.widget() else self.content

        active_key = resolve_theme(self.store.setting('appearance', 'light')).key
        appearance_card, av = panel('smallCard', 20)
        av.setSpacing(12)
        av.addWidget(label('Appearance', 'section'))
        av.addWidget(label('Choose an overall workspace theme preset. All surfaces, notes, and window chrome adapt immediately.', 'muted', True))
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        columns = 4 if self.width() >= 960 else (3 if self.width() >= 720 else 2)
        for index, preset in enumerate(THEME_PRESETS):
            card_btn = ThemePresetCard(preset, active=(preset.key == active_key), callback=self.set_appearance)
            grid.addWidget(card_btn, index // columns, index % columns)
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        av.addLayout(grid)

        behavior_card, bv = panel('smallCard', 20)
        bv.setSpacing(10)
        bv.addWidget(label('Motion & feedback', 'section'))
        reduce = QCheckBox('Reduce motion')
        reduce.setChecked(bool(self.store.setting('reduce_motion', False)))
        reduce.toggled.connect(self.set_reduce_motion)
        bv.addWidget(reduce)
        tactile = QCheckBox('Tactile micro-sounds (subtle cues on pin, drop, completion)')
        tactile.setChecked(bool(self.store.setting('tactile_sound', False)))
        tactile.toggled.connect(self.set_tactile_sound)
        bv.addWidget(tactile)

        host_layout.insertWidget(0, appearance_card)
        host_layout.insertWidget(1, behavior_card)

    def set_appearance(self, value):
        from PySide6.QtWidgets import QApplication
        from .tokens import resolve_theme
        from .windows_frame import apply_dwm
        preset = resolve_theme(value)
        self.store.set_setting('appearance', preset.key)
        apply_appearance(QApplication.instance(), preset.key)
        apply_dwm(self, preset.dark)
        if hasattr(self, 'stripe_divider'):
            self.stripe_divider.update()
        if getattr(self, 'boards_sidebar', None):
            self.boards_sidebar.refresh()
        self.render_sidebar()
        self.render(preserve_capture=True)

    def closeEvent(self, event):
        self.save_board_state()
        if self.capture is not None:
            self.capture.flush()
        super().closeEvent(event)
        if event.isAccepted():
            self._closed = True
            self.resize_debounce.stop()
            self.pulse.stop()
            if hasattr(self, '_clock_timer'):
                self._clock_timer.stop()

    def render_context(self):
        if hasattr(self, 'context'):
            self.context.hide()

    def update_mini_timer(self):
        if not hasattr(self, 'mini_timer'):
            return
        remaining = int(math.ceil(self.timer.remaining()))
        running = self.timer.data['running']
        self.mini_timer.setVisible(running)
        self.mini_timer.setText('')
        self.mini_timer.setToolTip(f'{remaining // 60:02}:{remaining % 60:02} · {self.timer.data["mode"]} running')

    def _update_calendar_clock(self):
        if hasattr(self, 'timeline') and self.page == 'Calendar':
            try:
                self.timeline.update()
            except RuntimeError:
                pass

    def tick(self):
        super().tick()
        self.update_mini_timer()
        if hasattr(self, 'countdown') and self.countdown is not None and self.page == 'Focus':
            remaining = int(math.ceil(self.timer.remaining()))
            try:
                self.countdown.setText(f'{remaining // 60:02}:{remaining % 60:02}')
                self.focus_choose.setEnabled(not self.timer.data['running'])
                self.focus_progress.setValue(round((1 - remaining / max(1, self.timer.data['duration'])) * 1000))
            except RuntimeError:
                pass

    def render_calendar(self):
        from .tokens import current_tokens
        t = current_tokens()
        toolbar = row(spacing=10)
        title = self.month.strftime('%B %Y') if self.calendar_view == 'Month' else self.selected_day.strftime('%B %d, %Y')
        compact = self.width() < 900
        def _stepper():
            box = QFrame()
            box.setObjectName('segmentedTrack')
            lay = QHBoxLayout(box)
            lay.setContentsMargins(3, 3, 3, 3)
            lay.setSpacing(2)
            p_btn = button('', lambda: self.move_calendar(-1), 'tab', 'left')
            p_btn.setFixedWidth(28)
            p_btn.setToolTip('Previous')
            t_btn = button('Today', self.go_today, 'tab')
            n_btn = button('', lambda: self.move_calendar(1), 'tab', 'right')
            n_btn.setFixedWidth(28)
            n_btn.setToolTip('Next')
            lay.addWidget(p_btn)
            lay.addWidget(t_btn)
            lay.addWidget(n_btn)
            return box
        if compact:
            self.content.addLayout(row(label(title, 'section'), None, _stepper()))
        else:
            toolbar.addWidget(label(title, 'section'))
        toolbar.addStretch()
        toolbar.addWidget(SegmentedSwitch(
            [('Month', 'Month', None), ('Week', 'Week', None), ('Day', 'Day', None)],
            self.calendar_view,
            self.calendar_mode,
        ))
        if not compact:
            toolbar.addWidget(_stepper())
        toolbar.addWidget(button('New' if compact else 'New event', self.new_event, 'primary', 'plus'))
        self.content.addLayout(toolbar)
        if self.calendar_view != 'Month':
            self.render_timeline()
            return
        frame = QFrame()
        frame.setObjectName('calendarFrame')
        frame.setProperty('tablaThemed', True)
        frame.setStyleSheet(f'QFrame#calendarFrame {{background:{t.bg_canvas};border:1px solid {t.border_subtle};border-radius:14px;}}')
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        weekday_bar = QFrame()
        weekday_bar.setProperty('tablaThemed', True)
        weekday_bar.setStyleSheet(f'background:{t.bg_surface};border:none;border-bottom:1px solid {t.border_subtle};border-top-left-radius:13px;border-top-right-radius:13px;')
        weekdays = QHBoxLayout(weekday_bar)
        weekdays.setContentsMargins(0, 0, 8, 0)
        weekdays.setSpacing(0)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for column, weekday in enumerate(('SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT')):
            wtitle = label(weekday, 'muted')
            wtitle.setObjectName('weekdayHeader')
            wtitle.setProperty('tablaThemed', True)
            wtitle.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            wtitle.setStyleSheet(f'font-size:11px;font-weight:600;color:{t.ink_muted};padding:9px 10px;')
            weekdays.addWidget(wtitle, 1)
            grid.setColumnStretch(column, 1)
        frame_layout.addWidget(weekday_bar)
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.month.year, self.month.month)
        annotations = {r.get('date'): r for r in self.scoped('note') if r.get('day_annotation')}
        for rindex, week in enumerate(weeks):
            grid.setRowStretch(rindex, 1)
            for column, day in enumerate(week):
                annotation = annotations.get(day.isoformat(), {})
                cell = CalendarCell(day, day.month == self.month.month, annotation.get('day_color'))
                cell.setMinimumWidth(48)
                cell.setMinimumHeight(92)
                cell.activated.connect(self.day_dialog)
                cell.marked.connect(self.mark_day)
                cell.day_note.connect(self.open_day_note)
                cell.moved.connect(self.move_record_date)
                items = self.calendar_items(day)
                limit = 2 if self.height() >= 1050 else 1
                for record in items[:limit]:
                    project = self.store.get(record.get('project'))
                    kind = {'task': 'Task', 'event': 'Event', 'block': 'Work block'}.get(record['kind'], '')
                    tag = ' · '.join(s for s in (kind, record.get('time'), project['title'] if project else '') if s)
                    cell.v.addWidget(RecordButton(record, lambda rid=record['id']: self.open_record(rid), tag))
                if len(items) > limit:
                    more = button(f'+{len(items) - limit} more', lambda checked=False, d=day: self.day_dialog(d), 'text')
                    more.setProperty('tablaThemed', True)
                    more.setStyleSheet(f'QPushButton {{font-size:11px;color:{t.ink_muted};padding:1px 4px;min-height:18px;max-height:18px;}}')
                    more.setToolTip('Show all entries for this day')
                    cell.v.addWidget(more)
                if annotation.get('body'):
                    cell.v.addWidget(button('Day note', lambda checked=False, d=day: self.open_day_note(d), 'text', 'note'))
                cell.v.addStretch()
                grid.addWidget(cell, rindex, column)
        self.calendar_scroll = scroll(host)
        self.calendar_scroll.setObjectName('monthCalendarScroll')
        frame_layout.addWidget(self.calendar_scroll, 1)
        self.content.addWidget(frame, 1)

    def render_timeline(self):
        from .tokens import current_tokens
        t = current_tokens()
        start = self.selected_day - timedelta(days=self.selected_day.weekday())
        days = [self.selected_day] if self.calendar_view == 'Day' else [start + timedelta(days=i) for i in range(7)]
        frame = QFrame()
        frame.setObjectName('calendarFrame')
        frame.setProperty('tablaThemed', True)
        frame.setStyleSheet(f'QFrame#calendarFrame {{background:{t.bg_canvas};border:1px solid {t.border_subtle};border-radius:14px;}}')
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        header_bar = QFrame()
        header_bar.setProperty('tablaThemed', True)
        header_bar.setStyleSheet(f'background:{t.bg_surface};border:none;border-bottom:1px solid {t.border_subtle};border-top-left-radius:13px;border-top-right-radius:13px;')
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(62, 8, 8, 8)
        header.setSpacing(4)
        all_records = [r for kind in ('task', 'event', 'block') for r in self.scoped(kind)]
        for day in days:
            column = QWidget()
            v = QVBoxLayout(column)
            v.setContentsMargins(4, 0, 4, 0)
            v.setSpacing(5)
            is_today = day == date.today()
            title = button(day.strftime('%a  %d'), lambda checked=False, d=day: self.day_dialog(d), 'text')
            title.setProperty('tablaThemed', True)
            if is_today:
                title.setStyleSheet(f'QPushButton {{background:{t.bg_pill};color:{t.ink_inverse};border:none;border-radius:8px;padding:4px 9px;font-weight:600;}}')
            else:
                title.setStyleSheet(f'QPushButton {{background:transparent;color:{t.ink_secondary};border:none;border-radius:8px;padding:4px 6px;font-weight:500;}} QPushButton:hover {{background:{t.bg_surface_hover};color:{t.ink_primary};}}')
            v.addLayout(row(title, None))
            for record in [r for r in all_records if r.get('date') == day.isoformat() and not r.get('time')][:3]:
                v.addWidget(RecordButton(record, lambda rid=record['id']: self.open_record(rid)))
            v.addStretch()
            header.addWidget(column, 1)
        frame_layout.addWidget(header_bar)
        self.timeline = Timeline(days, all_records)
        self.timeline.opened.connect(self.open_record)
        self.timeline.rescheduled.connect(self.reschedule)
        self.timeline.create_at.connect(self.create_timed_event)
        area = scroll(self.timeline)
        frame_layout.addWidget(area, 1)
        self.content.addWidget(frame, 1)
        QTimer.singleShot(0, area, lambda: area.verticalScrollBar().setValue(8 * Timeline.hour_height))

    def move_record_date(self, record_id, day):
        record = self.store.get(record_id)
        if record and record['kind'] in ('task', 'event', 'block'):
            record['date'] = day
            self.store.save(record)
            self.render()

    def reschedule(self, record_id, day, minute, duration):
        record = self.store.get(record_id)
        if not record:
            return
        minute = max(0, min(1425, minute))
        end = min(1439, minute + duration)
        record.update(date=day, time=f'{minute // 60:02}:{minute % 60:02}', end_time=f'{end // 60:02}:{end % 60:02}')
        self.store.save(record)
        self.render()

    def create_timed_event(self, day, minute):
        from PySide6.QtCore import QTime
        dialog = ItemDialog(self.store, 'event', day=day, project=self.project_id, parent=self)
        dialog.time.setTime(QTime(minute // 60, minute % 60))
        end = min(1439, minute + 60)
        dialog.end.setTime(QTime(end // 60, end % 60))
        if dialog.exec():
            self.refresh()
        dialog.deleteLater()

    def day_annotation(self, day):
        existing = next((r for r in self.scoped('note') if r.get('day_annotation') and r.get('date') == day.isoformat()), None)
        return existing or {'kind': 'note', 'title': day.strftime('%B %d, %Y'), 'date': day.isoformat(),
                            'body': '', 'day_annotation': True, 'project': self.project_id, 'color': 'gray'}

    def mark_day(self, day, color):
        record = self.day_annotation(day)
        record['day_color'] = None if color == 'None' else color
        self.store.save(record)
        self.render()

    def open_day_note(self, day):
        record = self.day_annotation(day)
        if not record.get('id'):
            record = self.store.save(record)
        self.edit_note(record)

    def day_dialog(self, day):
        self.selected_day = day
        dialog = PolishedDialog(self)
        dialog.setObjectName('roundedDialog')
        dialog.setAccessibleName('Day details')
        dialog.modal_surface = True
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setWindowTitle(day.strftime('%A, %B %d'))
        dialog.resize(510, 360)
        v = QVBoxLayout(dialog)
        v.setContentsMargins(24, 18, 24, 20)
        v.setSpacing(12)
        dialog_header(v, 'Day details', dialog.reject)
        v.addWidget(label(day.strftime('%A, %B %d'), 'section'))
        host = QWidget()
        items = QVBoxLayout(host)
        items.setContentsMargins(0, 8, 0, 8)
        for record in self.calendar_items(day):
            items.addWidget(button((record.get('time') or 'Due') + '  ' + record['title'],
                lambda checked=False, rid=record['id']: (dialog.accept(), self.open_record(rid)), 'text'))
        if not self.calendar_items(day):
            items.addWidget(label('Nothing scheduled yet. Add a task, event or work block below.', 'muted', True))
        items.addStretch()
        agenda = scroll(host)
        agenda.setMaximumHeight(170)
        v.addWidget(agenda, 1)
        dialog_divider(v)
        picker = ColorPicker(self.day_annotation(day).get('day_color') or 'None', values=('None', 'blue', 'green', 'yellow', 'violet', 'rose'))
        picker.currentTextChanged.connect(lambda color: self.mark_day(day, color))
        v.addWidget(label('Day highlight', 'fieldLabel'))
        v.addWidget(picker)
        v.addWidget(label('Add to this day', 'fieldLabel'))
        v.addLayout(row(button('Note', lambda: (dialog.accept(), self.open_day_note(day)), 'text', 'note'),
                        button('Task', lambda: (dialog.accept(), self.new_task(day=day.isoformat()))),
                        button('Work block', lambda: (dialog.accept(), self.new_block(day.isoformat()))),
                        None, button('New event', lambda: (dialog.accept(), self.new_event(day=day.isoformat())), 'primary')))
        polish_surfaces(dialog)
        dialog.exec()
        dialog.deleteLater()

    def render_tasks(self):
        tools = row(spacing=10)
        self.boards_toggle = button('Boards', self.boards_navigation, 'tab', 'sidebar')
        self.boards_toggle.setCheckable(True)
        tools.addWidget(self.boards_toggle)
        self.sync_boards_sidebar()
        tools.addWidget(SegmentedSwitch(
            [('Board', 'Cards', 'board'), ('Table', 'Table', 'table')],
            self.task_view,
            self.set_task_layout,
        ))
        tools.addStretch()
        query = QLineEdit(self.task_query)
        query.setPlaceholderText('Search cards')
        query.setMaximumWidth(200)
        query.returnPressed.connect(lambda: self.filter_tasks(query.text()))
        state = QComboBox()
        state.addItems(['Open', 'All', 'Completed', 'Overdue'])
        state.setCurrentText(self.task_filter)
        state.currentTextChanged.connect(self.set_task_filter)
        sort = QComboBox()
        sort.addItems(['Date', 'Priority', 'Title'])
        sort.setCurrentText(self.task_sort)
        sort.currentTextChanged.connect(self.sort_tasks)
        if self.task_view == 'Board':
            state.deleteLater()
            sort.deleteLater()
            if self.width() < 560:
                query.setMinimumWidth(70)
                query.setMaximumWidth(180)
            else:
                query.setFixedWidth(180 if self.width() < 900 else 220)
            filter_button = button('Filter · ' + self.task_filter, self.board_filter, 'text')
            self.board_filter_button = filter_button
            if self.width() >= 560:
                filter_button.setFixedWidth(105)
            archive_button = button('Archived', self.board_archive, 'text')
            if self.width() >= 560:
                archive_button.setFixedWidth(75)
            filters = row(query, filter_button, archive_button, spacing=6)
            if self.width() >= 900:
                tools.addLayout(filters)
                self.content.addLayout(tools)
            else:
                self.content.addLayout(tools)
                self.content.addLayout(filters)
        else:
            filters = row(query, state, sort) if self.width() < 800 else tools
            if filters is tools:
                tools.addWidget(query)
                tools.addWidget(state)
                tools.addWidget(sort)
            self.content.addLayout(tools)
            if filters is not tools:
                self.content.addLayout(filters)
        quick = QLineEdit()
        quick.setPlaceholderText('+ New task… Press Enter to add')
        quick.setAccessibleName('Quick add task')
        quick.setStyleSheet('border:none;border-bottom:1px solid #eeeeec;padding:8px 2px;')
        quick.returnPressed.connect(lambda: self.quick_task(quick.text()))
        if self.task_view != 'Board':
            self.content.addWidget(quick)
        else:
            quick.deleteLater()
        tasks = self.scoped('task', query=self.task_query)
        if self.task_filter == 'Open':
            tasks = [r for r in tasks if r.get('status') != 'Done']
        elif self.task_filter == 'Completed':
            tasks = [r for r in tasks if r.get('status') == 'Done']
        elif self.task_filter == 'Overdue':
            tasks = [r for r in tasks if r.get('status') != 'Done' and r.get('date') and r['date'] < date.today().isoformat()]
        tasks.sort(key=lambda t: t['title'].casefold() if self.task_sort == 'Title' else
                   {'High': 0, 'Medium': 1, 'Low': 2}.get(t.get('priority'), 1) if self.task_sort == 'Priority' else t.get('date') or '9999')
        if self.task_view == 'Board':
            self.board = TaskBoard(self.store, tasks, self.open_record, self.refresh, self.project_id, self.focus_task, self._board_scroll, board_id=self.board_id, records_provider=self.board_records)
            self.content.addWidget(self.board, 1)
            return
        table = QTableWidget(len(tasks), 7)
        table.setObjectName('taskTable')
        table.setHorizontalHeaderLabels(['✓', 'Task', 'Status', 'Priority', 'Due date', 'Project', ''])
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        if self.width() < 1000:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(1, 220)
        for col, width in ((0, 34), (2, 145), (3, 105), (4, 116), (5, 150), (6, 36)):
            table.setColumnWidth(col, width)
        table.blockSignals(True)
        for index, task in enumerate(tasks):
            table.setRowHeight(index, 46)
            check = QTableWidgetItem('')
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if task.get('status') == 'Done' else Qt.CheckState.Unchecked)
            table.setItem(index, 0, check)
            title = QTableWidgetItem(task['title'])
            if task.get('status') == 'Done':
                font = title.font()
                font.setStrikeOut(True)
                title.setFont(font)
                title.setForeground(QColor('#8b8b85'))
            table.setItem(index, 1, title)
            for col, field, values in ((2, 'status', ['To do', 'In progress', 'Done']), (3, 'priority', ['Low', 'Medium', 'High'])):
                combo = QComboBox()
                combo.addItems(values)
                combo.setCurrentText(task.get(field, values[0]))
                combo.setStyleSheet('QComboBox {border:none;background:transparent;font-size:12px;padding:6px;}')
                combo.currentTextChanged.connect(lambda value, rid=task['id'], key=field: self.update_task(rid, key, value))
                table.setCellWidget(index, col, combo)
            table.setItem(index, 4, QTableWidgetItem(task.get('date') or ''))
            project = QComboBox()
            project.addItem('—', None)
            for p in self.store.records('project'):
                project.addItem(p['title'], p['id'])
            project.setCurrentIndex(max(0, project.findData(task.get('project'))))
            project.setStyleSheet('QComboBox {border:none;background:transparent;font-size:12px;padding:6px;}')
            project.currentIndexChanged.connect(lambda i, rid=task['id'], combo=project: self.update_task(rid, 'project', combo.currentData()))
            table.setCellWidget(index, 5, project)
            table.setCellWidget(index, 6, button('↗', lambda checked=False, rid=task['id']: self.open_record(rid), 'text'))
        table.blockSignals(False)
        table.cellChanged.connect(lambda r, c: self.table_changed(table, tasks, r, c))
        self.content.addWidget(table, 1)
        self.content.addWidget(label(f'{len(tasks)} tasks · Double-click a title or date to edit · Dates use YYYY-MM-DD', 'muted'))

    def table_changed(self, table, tasks, index, column):
        task = tasks[index]
        value = table.item(index, column)
        if column == 0:
            self.update_task(task['id'], 'status', 'Done' if value.checkState() == Qt.CheckState.Checked else 'To do')
        elif column == 1:
            if value.text().strip():
                self.update_task(task['id'], 'title', value.text().strip())
        elif column == 4:
            text = value.text().strip()
            try:
                if text:
                    date.fromisoformat(text)
                self.update_task(task['id'], 'date', text or None)
            except ValueError:
                QMessageBox.information(self, 'Choose a date', 'Enter a date as YYYY-MM-DD, or leave the field empty.')
                self.render()

    def update_task(self, record_id, field, value):
        record = self.store.get(record_id)
        if record:
            record[field] = value
            self.store.save(record)
            QTimer.singleShot(0, self.refresh)

    def quick_task(self, title, status='To do'):
        if title.strip():
            self.store.save({'kind': 'task', 'title': title.strip(), 'status': status, 'priority': 'Medium', 'project': self.project_id})
            self.refresh()

    def set_task_layout(self, value):
        self.task_view = 'Table' if value == 'List' else value
        self.store.set_setting('tasks_presentation', self.task_view)
        if self.task_view == 'Board':
            self.task_filter = 'All'
        self.render()

    def board_filter(self):
        anchor = self.sender()
        menu = ChoiceMenu([(s, s) for s in ('All', 'Open', 'Completed', 'Overdue')], self.task_filter, self, 'Filter cards')
        menu.chosen.connect(self.set_task_filter)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()) if isinstance(anchor, QWidget) else self.mapToGlobal(QPoint(100, 180)))

    def board_archive(self):
        model = BoardModel(self.store, self.board_id)
        dialog = PolishedDialog(self)
        dialog.modal_surface = True
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(540, min(500, self.height() - 40))
        root = QVBoxLayout(dialog)
        root.setContentsMargins(24, 18, 24, 20)
        dialog_header(root, 'Archived cards and lists', dialog.reject)
        host = QWidget()
        rows = QVBoxLayout(host)
        root.addWidget(scroll(host), 1)
        def render_archive():
            clear(rows)
            for column in model.lists(archived=True):
                rows.addLayout(row(label(column['title'] + ' · list'), None,
                    button('Restore list', lambda checked=False, c=column['id']: (model.archive_list(c, False), render_archive()), 'text')))
            cards = self.store.records('task', state='archive', board=self.board_id)
            for card in cards:
                rows.addLayout(row(label(card['title'], wrap=True), None,
                    button('Restore card', lambda checked=False, rid=card['id']: (model.restore_card(rid), render_archive()), 'text')))
            if not cards and not model.lists(archived=True):
                rows.addWidget(label('Nothing archived. Archived cards stay here until you restore them.', 'muted', True))
            rows.addStretch()
            polish_surfaces(dialog)
        render_archive()
        dialog.exec()
        dialog.deleteLater()
        self.refresh()

    def filter_tasks(self, text):
        self.task_query = text
        if self.task_view == 'Board' and self.page == 'My Tasks':
            self.board.reconcile()
            self.save_board_state()
        else:
            self.render()

    def set_task_filter(self, value):
        self.task_filter = value
        if self.task_view == 'Board' and self.page == 'My Tasks' and getattr(self, 'board', None) is not None:
            self.board.reconcile()
            self.board_filter_button.setText('Filter · ' + value)
            self.save_board_state()
        else:
            self.render()

    def sort_tasks(self, text):
        self.task_sort = text
        self.render()

    def set_note_filters_visible(self, visible):
        self.store.set_setting('show_note_filters', bool(visible))
        if self.page == 'Notes':
            self.render()

    def show_note_collection(self, state):
        self.notes_filter = state
        self.navigate('Notes')

    def set_note_preview_lines(self, lines):
        self.store.set_setting('note_preview_lines', lines)
        self.render()

    def render_notes(self):
        self._gallery_records = {}
        self._gallery_cards = {}
        filters = row(None)
        if self.store.setting('show_note_filters', False):
            for title, state in (('Notes', 'Active'), ('Pinned', 'Pinned'), ('Archive', 'Archive'), ('Trash', 'Trash')):
                btn = button(title, lambda checked=False, s=state: self.set_notes_filter(s), 'tab')
                btn.setProperty('active', self.notes_filter == state)
                filters.addWidget(btn)
        elif self.notes_filter != 'Active':
            filters.addWidget(label(self.notes_filter + ' notes', 'muted'))
        if self.store.setting('show_note_filters', False) or self.notes_filter != 'Active':
            self.content.addLayout(filters)
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 12, 0, 20)
        v.setSpacing(22)
        if self.notes_filter in ('Active', 'Pinned'):
            restored = self._capture_to_restore
            self._capture_to_restore = None
            self.capture = restored or QuickCapture(self.store, self.project_id)
            self.update_capture_width()
            if not restored:
                self.capture.saved.connect(lambda _: self.refresh())
            v.addLayout(row(None, self.capture, None))
            v.addSpacing(16)
        state = {'Archive': 'archive', 'Trash': 'trash'}.get(self.notes_filter, 'active')
        notes = self.scoped('note', state, self.notes_query)
        notes = [n for n in notes if not n.get('day_annotation') or n.get('body')]
        if self.notes_filter == 'Pinned':
            notes = [n for n in notes if n.get('pinned')]
        groups = [('Pinned', [n for n in notes if n.get('pinned')]), ('Other notes', [n for n in notes if not n.get('pinned')])]
        for title, matching in groups:
            if not matching:
                continue
            if state == 'active' and any(n.get('pinned') for n in notes):
                group_title = label(title.upper(), 'muted')
                group_title.setStyleSheet('font-size:11px;letter-spacing:1px;color:#747775;padding:0 6px;')
                v.addWidget(group_title)
            cards = [self.note_card(note) for note in matching]
            for note, card in zip(matching, cards):
                self._gallery_records[note['id']] = note
                self._gallery_cards[note['id']] = card
            v.addWidget(Masonry(cards))
        if not notes:
            empty = label('Your notes will appear here' if state == 'active' else ('Your archive is empty' if state == 'archive' else 'Trash is empty'), 'muted')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(0, 60, 0, 40)
            v.addWidget(empty)
        v.addStretch()
        from .layer_effects import ScrollEdgeLayer
        self.notes_scroll = scroll(host)
        self.content.addWidget(self.notes_scroll, 1)
        self.notes_edge = ScrollEdgeLayer(self.notes_scroll)

    def sync_note_gallery(self):
        """Keep the page and capture alive when only a note's content changed."""
        if self.page != 'Notes' or not hasattr(self, '_gallery_records'):
            self.refresh()
            return
        state = {'Archive': 'archive', 'Trash': 'trash'}.get(self.notes_filter, 'active')
        notes = [n for n in self.scoped('note', state, self.notes_query)
                 if (not n.get('day_annotation') or n.get('body'))
                 and (self.notes_filter != 'Pinned' or n.get('pinned'))]
        current = {n['id']: n for n in notes}
        old = self._gallery_records
        scroll_position = self.notes_scroll.verticalScrollBar().value()
        if current.keys() != old.keys() or any(bool(n.get('pinned')) != bool(old[rid].get('pinned')) for rid, n in current.items()):
            self.render(preserve_capture=True)
            QTimer.singleShot(0, lambda: self.notes_scroll.verticalScrollBar().setValue(scroll_position))
            return
        for rid, note in current.items():
            if note == old[rid] and len(self.store.backlinks(rid)) == getattr(self._gallery_cards[rid], '_reference_count', 0):
                continue
            previous = self._gallery_cards[rid]
            parent = previous.parentWidget()
            replacement = self.note_card(note)
            replacement.setParent(parent)
            if isinstance(parent, Masonry):
                parent.cards[parent.cards.index(previous)] = replacement
            else:
                replacement.setMaximumWidth(760)
                parent.layout().replaceWidget(previous, replacement)
            previous.hide()
            previous.deleteLater()
            replacement.show()
            polish_surfaces(replacement)
            if isinstance(parent, Masonry):
                parent.arrange()
            replacement.setFocus(Qt.FocusReason.OtherFocusReason)
            self._gallery_cards[rid] = replacement
        self._gallery_records = current
        self.notes_scroll.verticalScrollBar().setValue(scroll_position)

    def toggle_note_view(self):
        self.note_view = 'Grid'
        self.render()

    def note_card(self, note, compact=False):
        card = NoteCard(note.get('color', 'gray'))
        bg = COLORS.get(note.get('color', 'gray'), COLORS['gray'])[0]
        if note.get('color', 'gray') == 'gray':
            bg = 'white'
        card.setStyleSheet(f'ClickCard {{background:{bg};border:1px solid #dadce0;border-radius:8px;}} ClickCard:hover {{border-color:#a5a9ac;}} ClickCard:focus {{border:2px solid #2383e2;}}')
        card.clicked.connect(lambda: self.open_note_card(note, card))
        v = QVBoxLayout(card)
        v.setContentsMargins(15, 13, 15, 10)
        v.setSpacing(10)
        from .note_preview import NotePreview
        title = NotePreview(note['title'], 2, 120, title=True)
        title.setStyleSheet('font-size:15px;font-weight:500;color:#202124;')
        pin = PinButton(note.get('pinned', False))
        pin.toggled.connect(lambda checked: self.note_action(note['id'], 'pinned', checked))
        v.addLayout(row(title, pin))
        body = LINK_RE.sub(lambda m: (self.store.resolve(m[1], note['id']) or {}).get('title', m[1]), note.get('body', ''))
        limit = min(6, self.store.setting('note_preview_lines', 14)) if compact else self.store.setting('note_preview_lines', 14)
        indexed = [(i, t) for i, t in enumerate(body.splitlines()) if t.strip()]
        nodes = note.get('document', {}).get('nodes', [])
        simple_document = not nodes or all(n['type'] == 'paragraph' for n in nodes)
        only_checklist = bool(indexed) and simple_document and all(re.match(r'^\s*[-*] \[([ xX])\] (.*)', t) for _, t in indexed)
        if only_checklist:
            budget = 1200
            for index, text in indexed[:limit]:
                match = re.match(r'^\s*[-*] \[([ xX])\] (.*)', text)
                size = min(55, budget)
                if size < 1:
                    break
                caption = match[2][:size] + ('…' if len(match[2]) > size else '')
                budget -= len(caption)
                check = QCheckBox(caption)
                check.setChecked(match[1].lower() == 'x')
                check.setStyleSheet('font-size:13px;')
                check.setMinimumWidth(0)
                check.toggled.connect(lambda value, rid=note['id'], line=index: self.toggle_note_line(rid, line, value))
                v.addWidget(check)
            if len(indexed) > limit:
                v.addWidget(label('…', 'muted'))
        elif body.strip():
            text = re.sub(r'^#{1,6}\s+', '', body, flags=re.MULTILINE).replace('**', '').replace('==', '')
            text = re.sub(r'^\s*[-*] \[([ xX])\] ', lambda m: '☑ ' if m[1].lower() == 'x' else '☐ ', text, flags=re.MULTILINE)
            v.addWidget(NotePreview(text, limit, 1200))
        if note.get('document'):
            tables = [n for n in note['document']['nodes'] if n['type'] == 'table']
            if tables:
                v.addWidget(label(f'{len(tables)} table' + ('s' if len(tables) != 1 else ''), 'muted'))
            image = next((r['image'] for n in note['document']['nodes'] if n['type'] == 'paragraph' for r in n['runs'] if 'image' in r), None)
            if image:
                item = next((a for a in note.get('attachments', []) if a['key'] == image['key']), None)
                if item:
                    from PySide6.QtGui import QPixmap
                    pixmap = QPixmap(str(self.store.attachments.path_for(item)))
                    if not pixmap.isNull():
                        thumbnail = QLabel()
                        thumbnail.setPixmap(pixmap.scaled(220, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        thumbnail.setMaximumHeight(90)
                        v.addWidget(thumbnail)
        tags = list(dict.fromkeys([t.strip() for t in note.get('labels', '').split(',') if t.strip()] + re.findall(r'(?<!\w)#([\w/-]+)', note.get('body', ''))))
        if note.get('attachments'):
            v.addWidget(label(f'{len(note["attachments"])} source file' + ('s' if len(note['attachments']) != 1 else ''), 'muted'))
        if tags:
            tag = label('   '.join('#' + t.lstrip('#') for t in tags[:5]), 'muted', True)
            tag.setStyleSheet('font-size:11px;color:#6b6b66;')
            v.addWidget(tag)
        actions = row()
        for glyph, tip, callback in (
            ('palette', 'Color', lambda: self.note_color_menu(note, card)),
            ('archive', 'Restore' if note.get('archived') or note.get('deleted') else 'Archive', lambda: self.restore_or_archive(note)),
            ('trash', 'Trash', lambda: self.note_action(note['id'], 'deleted', True))):
            btn = button('', callback, 'text', glyph)
            btn.setToolTip(tip)
            btn.setAccessibleName(tip)
            actions.addWidget(btn)
        actions.addStretch()
        refs = len(self.store.backlinks(note['id']))
        card._reference_count = refs
        if refs:
            actions.addWidget(label(f'{refs} links', 'muted'))
        action_host = QWidget()
        action_host.setLayout(actions)
        v.addWidget(action_host)
        card.setup_controls(action_host, pin)
        return card

    def note_action(self, record_id, key, value):
        note = self.store.get(record_id)
        note[key] = value
        self.store.save(note)
        self.refresh()

    def restore_or_archive(self, note):
        if note.get('deleted'):
            self.restore_trashed(note['id'])
        else:
            self.note_action(note['id'], 'archived', not note.get('archived'))

    def note_color_menu(self, note, anchor):
        color_popup(self, note.get('color', 'gray'), lambda color: self.note_action(note['id'], 'color', color), anchor)

    def toggle_note_line(self, record_id, index, checked):
        note = self.store.get(record_id)
        lines = note.get('body', '').splitlines()
        if index < len(lines):
            lines[index] = re.sub(r'\[[ xX]\]', '[x]' if checked else '[ ]', lines[index], count=1)
            note['body'] = '\n'.join(lines)
            nodes = note.get('document', {}).get('nodes', [])
            if index < len(nodes) and nodes[index]['type'] == 'paragraph' and nodes[index].get('check'):
                from PySide6.QtGui import QTextBlockFormat
                nodes[index]['check'] = (QTextBlockFormat.MarkerType.Checked if checked else QTextBlockFormat.MarkerType.Unchecked).value
            self.store.save(note)

    def open_note_card(self, note, card=None):
        self._note_origin = __import__('PySide6.QtCore', fromlist=['QRect']).QRect(card.mapToGlobal(QPoint()), card.size()) if card is not None else None
        self._note_snapshot = card.grab() if card is not None else None
        note = self.store.get(note['id']) or note
        if note.get('deleted'):
            QMessageBox.information(self, 'Note in trash', 'Restore this note with its restore button to edit it.')
        else:
            self.edit_note(note)

    def render_focus(self):
        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 12, 0, 12)
        focus = QWidget()
        focus.setMaximumWidth(600)
        v = QVBoxLayout(focus)
        v.setContentsMargins(16, 12, 16, 16)
        v.setSpacing(24)
        modes = row(None, SegmentedSwitch(
            [(name, name, None) for name in ('Focus', 'Short break', 'Long break')],
            self.timer.data['mode'],
            self.timer_mode,
        ), None)
        v.addLayout(modes)
        remaining = int(math.ceil(self.timer.remaining()))
        self.countdown = CountdownDisplay(f'{remaining // 60:02}:{remaining % 60:02}', px=92)
        v.addWidget(self.countdown)
        self.focus_progress = QProgressBar()
        self.focus_progress.setRange(0, 1000)
        self.focus_progress.setTextVisible(False)
        self.focus_progress.setFixedHeight(4)
        self.focus_progress.setValue(round((1 - remaining / max(1, self.timer.data['duration'])) * 1000))
        v.addWidget(self.focus_progress)
        context, context_layout = panel('focusContext', 14)
        context_layout.addWidget(label('WORKING ON', 'fieldLabel'))
        selected = self.store.get(self.timer.data.get('task'))
        context_layout.addWidget(label(selected['title'] if selected else 'One thing at a time', 'section', True))
        self.focus_choose = button('Change task' if selected else 'Choose a task or note', self.choose_focus_context, 'text', 'tasks')
        self.focus_choose.setObjectName('focusTaskPicker')
        self.focus_choose.setAccessibleName('Choose focus task or note')
        self.focus_choose.setEnabled(not self.timer.data['running'])
        context_layout.addLayout(row(self.focus_choose, None))
        v.addWidget(context)
        toggle = button('Pause' if self.timer.data['running'] else 'Start focus', self.toggle_timer, 'primary', 'pause' if self.timer.data['running'] else 'play')
        toggle.setProperty('timerToggle', True)
        self._last_timer_running = bool(self.timer.data['running'])
        toggle.setMinimumWidth(130)
        v.addLayout(row(None, toggle, button('Reset', lambda: self.timer_mode(self.timer.data['mode']), 'text'), None))
        v.addLayout(row(None, button('Timer settings', self.timer_prefs, 'text', 'settings'), None))
        outer.addLayout(row(None, focus, None))
        outer.addSpacing(24)
        sessions = self.store.records('session')[:8]
        if sessions:
            outer.addWidget(label('Recent sessions', 'section'))
            for session in sessions:
                outer.addLayout(row(label(session['title']), None, label(f'{session.get("seconds", 0) // 60} min · ' + ('Completed' if session.get('completed') else 'Interrupted'), 'muted')))
        outer.addStretch()
        self.content.addWidget(scroll(host), 1)

    def choose_focus_context(self):
        if self.timer.data['running']:
            return
        records = [r for r in self.scoped('task') if r.get('status') != 'Done'] + self.scoped('note')
        menu = ChoiceMenu([('Focus without a task', None)] + [(r['title'] + ' · ' + r['kind'], r['id']) for r in records], self.timer.data.get('task'), self, 'Choose your focus')
        def choose(value):
            self.choose_focus_task(value)
            QTimer.singleShot(0, self.render)
        menu.chosen.connect(choose)
        menu.exec(self.focus_choose.mapToGlobal(self.focus_choose.rect().bottomLeft()))

    def render_today(self):
        from .home import render_home
        render_home(self)
