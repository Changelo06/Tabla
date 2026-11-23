"""Native interaction surfaces for notes, calendar planning and connected writing."""
from __future__ import annotations
import json
import re
from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt, Signal, QRectF, QMimeData, QSize
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QDrag, QSyntaxHighlighter,
                          QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QMenu,
    QSizePolicy, QPushButton, QLabel, QCheckBox)
from .widgets import button, label, row, PinButton
from .theme import COLORS, themed_color


class MarkdownHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        heading = re.match(r'^(#{1,6})\s+', text)
        if heading:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.DemiBold)
            fmt.setFontPointSize({1: 22, 2: 18, 3: 16}.get(len(heading[1]), 14))
            self.setFormat(0, len(text), fmt)
        for pattern, color in ((r'\[\[[^\]]+\]\]', '#2383e2'), (r'(?<!\w)#[\w/-]+', '#9467a9'),
                               (r'^\s*[-*] \[[ xX]\]', '#8b8b86')):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match[0]), fmt)
        for pattern, mode in ((r'\*\*(.+?)\*\*', 'bold'), (r'==(.+?)==', 'highlight'),
                              (r'`([^`]+)`', 'code')):
            for match in re.finditer(pattern, text):
                fmt = QTextCharFormat()
                if mode == 'bold':
                    fmt.setFontWeight(QFont.Weight.DemiBold)
                else:
                    fmt.setBackground(QColor('#fff0a5' if mode == 'highlight' else '#f1f1ef'))
                self.setFormat(match.start(), len(match[0]), fmt)


class RecordButton(QPushButton):
    """An entry can be opened or dragged onto another calendar date."""
    def __init__(self, record, callback, tag=''):
        super().__init__()
        self.record = record
        self.full_title = record['title']
        self.setAccessibleName(self.full_title)
        self.setToolTip(self.full_title + ('\n' + tag if tag else ''))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda checked=False: callback())
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(30 if not tag else 48)
        bg, accent = COLORS.get(record.get('color', 'blue'), COLORS['blue'])
        self.setStyleSheet(f'QPushButton {{background:white;border:1px solid #e4e4e1;border-radius:4px;'
                           f'text-align:left;padding:4px 7px;color:#37352f;font-size:12px;}}'
                           f'QPushButton:hover {{background:{bg};border-color:{accent};}}')
        self.tag = tag
        self.setMouseTracking(True)
        self._press = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        title = ('✓ ' if self.record.get('status') == 'Done' else '') + self.full_title
        title = self.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, max(1, self.width() - 16))
        self.setText(title + ('\n' + self.tag if self.tag else ''))

    def mousePressEvent(self, event):
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        bg, accent = COLORS.get(self.record.get('color', 'blue'), COLORS['blue'])
        p.setPen(QColor(accent if self.underMouse() or self.hasFocus() else themed_color('#dadce0')))
        p.setBrush(QColor(themed_color(bg)))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(accent))
        p.drawRoundedRect(QRectF(1, 4, 3, self.height() - 8), 1.5, 1.5)
        title = ('✓ ' if self.record.get('status') == 'Done' else '') + self.full_title
        font = QFont('Inter', 9, QFont.Weight.Medium)
        font.setStrikeOut(self.record.get('status') == 'Done')
        p.setFont(font)
        title = p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, max(1, self.width() - 22))
        p.setPen(QColor(themed_color('#37352f')))
        p.drawText(QRectF(10, 4, self.width() - 20, 20), Qt.AlignmentFlag.AlignVCenter, title)
        if self.tag:
            p.setFont(QFont('Inter', 8))
            p.setPen(QColor(themed_color('#696864')))
            tag = p.fontMetrics().elidedText(self.tag, Qt.TextElideMode.ElideRight, max(1, self.width() - 20))
            p.drawText(QRectF(10, 25, self.width() - 20, 19), Qt.AlignmentFlag.AlignVCenter, tag)
        p.end()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton and (event.position().toPoint() - self._press).manhattanLength() > 8:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData('application/x-tabla-record', self.record['id'].encode())
            drag.setMimeData(mime)
            drag.setPixmap(self.grab())
            drag.setHotSpot(self._press)
            self.setDown(False)
            drag.exec(Qt.DropAction.MoveAction)
            self._press = None
        else:
            super().mouseMoveEvent(event)


class CalendarCell(QFrame):
    moved = Signal(str, str)
    activated = Signal(object)
    marked = Signal(object, str)
    day_note = Signal(object)

    def __init__(self, day, in_month=True, marker=None):
        super().__init__()
        self.day = day
        self.setObjectName('calendarCell')
        self.setAcceptDrops(True)
        self.setMinimumSize(85, 105)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        bg = COLORS.get(marker, ('white' if in_month else '#fafaf9', ''))[0]
        self.setStyleSheet(f'QFrame#calendarCell {{background:{bg};border-right:1px solid #e5e5e3;border-bottom:1px solid #e5e5e3;}}')
        self.setAccessibleName(day.strftime('%A, %B %d'))
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(6, 6, 6, 6)
        self.v.setSpacing(4)
        number = label(str(day.day))
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number.setFixedSize(24, 24)
        if day == date.today():
            number.setStyleSheet('background:#2383e2;color:white;border-radius:12px;font-size:12px;')
        elif not in_month:
            number.setStyleSheet('color:#aaa9a3;')
        self.v.addLayout(row(None, number))

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self.day)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.day)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction('Plan this day', lambda: self.activated.emit(self.day))
        menu.addAction('Open day note', lambda: self.day_note.emit(self.day))
        colors = menu.addMenu('Highlight day')
        for color in ('None', 'blue', 'green', 'yellow', 'violet', 'rose'):
            colors.addAction(color.capitalize(), lambda checked=False, c=color: self.marked.emit(self.day, c))
        menu.exec(event.globalPos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-tabla-record'):
            event.acceptProposedAction()

    def dropEvent(self, event):
        record_id = bytes(event.mimeData().data('application/x-tabla-record')).decode()
        self.moved.emit(record_id, self.day.isoformat())
        event.acceptProposedAction()


def overlapping_columns(records):
    """Assign lanes per overlapping cluster so separate appointments use full width."""
    events = []
    for record in records:
        try:
            start = sum(int(v) * m for v, m in zip(record['time'].split(':'), (60, 1)))
            end = sum(int(v) * m for v, m in zip(record.get('end_time', record['time']).split(':'), (60, 1)))
        except (KeyError, ValueError):
            continue
        events.append((start, max(start + 15, end), record))
    events.sort(key=lambda x: (x[0], x[1]))
    result, cluster, lanes, cluster_end = [], [], [], -1
    def flush():
        for start, end, record, lane in cluster:
            result.append((start, end, record, lane, len(lanes)))
    for start, end, record in events:
        if start >= cluster_end and cluster:
            flush()
            cluster, lanes = [], []
        lane = next((i for i, finish in enumerate(lanes) if finish <= start), len(lanes))
        if lane == len(lanes):
            lanes.append(end)
        else:
            lanes[lane] = end
        cluster.append((start, end, record, lane))
        cluster_end = max([e for _, e, _, _ in cluster])
    flush()
    return result


class BoardColumn(QFrame):
    moved = Signal(str, str)
    def __init__(self, status):
        super().__init__()
        self.status = status
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-tabla-record'):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.moved.emit(bytes(event.mimeData().data('application/x-tabla-record')).decode(), self.status)
        event.acceptProposedAction()


class Timeline(QWidget):
    opened = Signal(str)
    rescheduled = Signal(str, str, int, int)
    create_at = Signal(str, int)
    hour_height = 58
    start_hour = 0
    end_hour = 24

    def __init__(self, days, records):
        super().__init__()
        self.days, self.records = days, records
        self.rects = []
        self._drag = None
        self.setMinimumSize(600, (self.end_hour - self.start_hour) * self.hour_height)
        self.setMouseTracking(True)
        self.setAccessibleName('Weekly time grid. Drag appointments to reschedule; drag their bottom edge to resize.')

    def position(self, point):
        width = (self.width() - 58) / len(self.days)
        index = max(0, min(len(self.days) - 1, int((point.x() - 58) / width)))
        minutes = round((point.y() / self.hour_height * 60 + self.start_hour * 60) / 15) * 15
        return self.days[index].isoformat(), max(0, min(1425, minutes))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(themed_color('white')))
        width = (self.width() - 58) / len(self.days)
        p.setFont(QFont('Inter', 9))
        for hour in range(self.start_hour, self.end_hour + 1):
            y = (hour - self.start_hour) * self.hour_height
            p.setPen(QColor(themed_color('#eeeeec')))
            p.drawLine(58, y, self.width(), y)
            p.setPen(QColor(themed_color('#8b8b85')))
            p.drawText(QRectF(0, y + 3, 49, 20), Qt.AlignmentFlag.AlignRight, f'{hour % 12 or 12} {"AM" if hour % 24 < 12 else "PM"}')
        self.rects = []
        for index, day in enumerate(self.days):
            x = 58 + index * width
            p.setPen(QColor(themed_color('#eeeeec')))
            p.drawLine(int(x), 0, int(x), self.height())
            matching = [r for r in self.records if r.get('date') == day.isoformat() and r.get('time')]
            for start, end, record, lane, count in overlapping_columns(matching):
                y = (start / 60 - self.start_hour) * self.hour_height
                h = max(23, (end - start) / 60 * self.hour_height - 2)
                rect = QRectF(x + 3 + lane * (width - 6) / count, y + 1, (width - 6) / count - 2, h)
                bg, accent = COLORS.get(record.get('color', 'blue'), COLORS['blue'])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(themed_color(bg)))
                p.drawRoundedRect(rect, 3, 3)
                p.fillRect(QRectF(rect.x(), rect.y(), 3, rect.height()), QColor(accent))
                p.setPen(QColor(themed_color('#303332')))
                p.setFont(QFont('Inter', 9, QFont.Weight.Medium))
                p.save()
                p.setClipRect(rect.adjusted(6, 3, -3, -2))
                available = max(1, int(rect.width() - 12))
                title = p.fontMetrics().elidedText(record['title'], Qt.TextElideMode.ElideRight, available)
                p.drawText(QRectF(rect.x() + 7, rect.y() + 3, available, 18), Qt.AlignmentFlag.AlignVCenter, title)
                if h >= 42:
                    p.setFont(QFont('Inter', 8))
                    times = p.fontMetrics().elidedText(record['time'] + '–' + record.get('end_time', ''), Qt.TextElideMode.ElideRight, available)
                    p.drawText(QRectF(rect.x() + 7, rect.y() + 23, available, 16), Qt.AlignmentFlag.AlignVCenter, times)
                p.restore()
                self.rects.append((rect, record, start, end))
        if date.today() in self.days:
            index = self.days.index(date.today())
            now = datetime.now()
            y = (now.hour + now.minute / 60 - self.start_hour) * self.hour_height
            p.setPen(QPen(QColor('#e16f65'), 1.5))
            p.drawLine(int(58 + index * width), int(y), int(58 + (index + 1) * width), int(y))
        p.end()

    def mousePressEvent(self, event):
        for rect, record, start, end in reversed(self.rects):
            if rect.contains(event.position()):
                self._drag = (event.position(), record, start, end, event.position().y() >= rect.bottom() - 8)
                return

    def mouseMoveEvent(self, event):
        resizing = any(rect.contains(event.position()) and event.position().y() >= rect.bottom() - 8 for rect, *_ in self.rects)
        self.setCursor(Qt.CursorShape.SizeVerCursor if resizing else Qt.CursorShape.PointingHandCursor)
        for rect, record, *_ in self.rects:
            if rect.contains(event.position()):
                self.setToolTip(record['title'] + '\n' + record.get('time', '') + '–' + record.get('end_time', '') + '\nDrag to move; drag bottom edge to resize.')
                return
        self.setToolTip('Double-click to schedule an event.')

    def mouseReleaseEvent(self, event):
        if not self._drag:
            return
        point, record, start, end, resize = self._drag
        self._drag = None
        if (event.position() - point).manhattanLength() < 8:
            self.opened.emit(record['id'])
            return
        day, minute = self.position(event.position())
        if resize:
            minute = min(1440, max(start + 15, minute))
            self.rescheduled.emit(record['id'], record['date'], start, minute - start)
        else:
            delta = round((event.position().y() - point.y()) / self.hour_height * 4) * 15
            minute = max(0, min(1440 - (end - start), start + delta))
            self.rescheduled.emit(record['id'], day, minute, end - start)

    def mouseDoubleClickEvent(self, event):
        day, minute = self.position(event.position())
        self.create_at.emit(day, minute)


class Masonry(QWidget):
    """Keep-like fixed-width columns; note height follows its actual content."""
    def __init__(self, cards, minimum=235):
        super().__init__()
        self.cards, self.minimum = cards, minimum
        for card in cards:
            card.setParent(self)

    def resizeEvent(self, event):
        self.arrange()
        super().resizeEvent(event)

    def arrange(self):
        columns = max(1, self.width() // (self.minimum + 16))
        width = (self.width() - 16 * (columns - 1)) // columns
        heights = [0] * columns
        for card in self.cards:
            column = min(range(columns), key=lambda c: heights[c])
            layout = card.layout()
            height = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
            height = max(115, height)
            card.setGeometry(column * (width + 16), heights[column], width, height)
            card.show()
            heights[column] += height + 16
        self.setMinimumHeight(max(heights, default=0))


class QuickCapture(QFrame):
    saved = Signal(dict)
    def __init__(self, store, project=None):
        from .rich_document import RichNoteEditor
        from PySide6.QtWidgets import QLineEdit
        from .attachment_widgets import AttachmentPanel
        super().__init__()
        self.store, self.project = store, project
        self.setProperty('notesSurface', True)
        self.expanded = False
        self._sizing_text = False
        self.setObjectName('composerBox')
        self.setMaximumWidth(650)
        self.setFixedHeight(54)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 6, 12, 6)
        self.v.setSpacing(5)
        self.title = QLineEdit()
        self.title.setPlaceholderText('Title')
        self.title.setStyleSheet('border:none;background:transparent;font-size:18px;font-weight:500;padding:4px;')
        self.header = QWidget()
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.title, 1)
        self.pin = PinButton()
        header.addWidget(self.pin, 0, Qt.AlignmentFlag.AlignTop)
        self.header.hide()
        self.body = RichNoteEditor(store)
        self.body.setPlaceholderText('Take a note…')
        self.body.setFixedHeight(40)
        self.body.setStyleSheet("font-family:'Inter';font-size:14px;border:none;padding:4px;")
        from PySide6.QtGui import QTextOption
        self.body.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.textChanged.connect(self.expand)
        self.body.installEventFilter(self)
        self.v.addWidget(self.header)
        self.v.addWidget(self.body)
        self.attachments = AttachmentPanel(store.attachments, parent=self)
        self.attachments.max_height = 70
        self.v.addWidget(self.attachments)
        self.body.filesDropped.connect(self.attachments.add_paths)
        self.body.imagesInserted.connect(self.add_image_sources)
        self.actions = QWidget()
        self.secondary_controls = []
        h = QHBoxLayout(self.actions)
        h.setContentsMargins(0, 0, 0, 0)
        for text, glyph, tip, callback in (
            ('A', None, 'Formatting', self.format_menu),
            ('', 'palette', 'Color', self.color_menu),
            ('', 'attachment', 'Insert', self.insert_menu),
            ('', 'image', 'Insert image', self.choose_image),
            ('', 'bullets', 'Lists: dots, numbers, letters', self.body.cycle_list),
            ('', 'tasks', 'Add checklist', self.checklist),
            ('', 'more', 'More options', self.more_menu),
            ('', 'undo', 'Undo', self.body.undo),
            ('', 'redo', 'Redo', self.body.redo)):
            if glyph == 'bullets':
                from .rich_document import list_style_button
                control = list_style_button(self.body)
            else:
                control = button(text, callback, 'text', glyph)
            control.setToolTip(tip)
            if glyph != 'bullets':
                control.setAccessibleName(tip)
            control.setFixedWidth(32)
            if tip == 'Formatting':
                control.setStyleSheet('border:none;background:transparent;font-size:16px;text-decoration:underline;padding:4px;')
            if tip in ('Undo', 'Redo'):
                self.secondary_controls.append(control)
                control.setEnabled(False)
                (self.body.undoAvailable if tip == 'Undo' else self.body.redoAvailable).connect(control.setEnabled)
            h.addWidget(control)
        h.addStretch()
        close = button('Close', self.commit, 'text')
        close.setStyleSheet('border:none;background:transparent;font-weight:500;padding:5px 12px;')
        h.addWidget(close)
        self.v.addWidget(self.actions)
        self.actions.hide()
        from PySide6.QtCore import QTimer
        self.text_resize = QTimer(self)
        self.text_resize.setSingleShot(True)
        self.text_resize.timeout.connect(self.fit_text)
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(350)
        self.draft_timer.timeout.connect(self.write_draft)
        self.saved_state = QLabel('')
        self.saved_state.setObjectName('muted')
        h.insertWidget(h.count() - 1, self.saved_state)
        self.cursor_scroll = QTimer(self)
        self.cursor_scroll.setSingleShot(True)
        self.cursor_scroll.timeout.connect(self.reveal_cursor)
        self.body.cursorPositionChanged.connect(lambda: self.cursor_scroll.start(0))
        self.body.document().documentLayout().documentSizeChanged.connect(self.queue_text_resize)
        self.draft_key = 'note_draft_' + (project or 'personal')
        draft = store.setting(self.draft_key, {})
        self.color = draft.get('color', 'gray')
        self.labels = draft.get('labels', '')
        self.attachments.items = draft.get('attachments', [])
        self.attachments.compact = draft.get('attachment_display') == 'compact'
        self.attachments.render()
        self.title.setText(draft.get('title', ''))
        self.body.blockSignals(True)
        self.body.load_note(draft)
        self.body.blockSignals(False)
        self.pin.setChecked(draft.get('pinned', False))
        self.body.link_targets = draft.get('link_targets', {})
        if draft.get('title') or draft.get('body') or self.attachments.items:
            self.expand()
        self.title.textChanged.connect(self.save_draft)
        self.body.textChanged.connect(self.save_draft)
        self.pin.toggled.connect(self.save_draft)
        self.attachments.changed.connect(lambda: (self.expand(), self.save_draft()))

    def save_draft(self):
        self.saved_state.setText('Saving…')
        self.draft_timer.start()

    def add_image_sources(self, items):
        known = {item['key'] for item in self.attachments.items}
        self.attachments.items.extend(item for item in items if item['key'] not in known)
        self.attachments.render()
        self.attachments.changed.emit()

    def write_draft(self):
        try:
            self.store.set_setting(self.draft_key, {'title': self.title.text(), 'body': self.body.plain_body(),
            'document': self.body.snapshot(),
            'pinned': self.pin.isChecked(), 'link_targets': self.body.link_targets, 'color': self.color, 'labels': self.labels,
            'attachments': list(self.attachments.items), 'attachment_display': 'compact' if self.attachments.compact else 'details'})
        except Exception:
            self.saved_state.setText('Not saved — retry Close')
            return
        self.saved_state.setText('Draft saved')

    def format_menu(self):
        menu = QMenu(self)
        for title, mark in (('Bold · Ctrl+B', 'bold'), ('Italic · Ctrl+I', 'italic'), ('Underline · Ctrl+U', 'underline'), ('Highlight', 'highlight')):
            menu.addAction(title, lambda checked=False, m=mark: self.body.toggle_mark(m))
        menu.exec(self.actions.mapToGlobal(self.actions.rect().topLeft()))

    def insert_menu(self):
        from .note_dialog import NoteDialog
        menu = QMenu(self)
        menu.addAction('Image…', lambda: NoteDialog.choose_image(self))
        menu.addAction('Table…', lambda: NoteDialog.choose_table(self))
        menu.addAction('Source files…', self.attachments.choose_files)
        menu.exec(self.actions.mapToGlobal(self.actions.rect().topLeft()))

    def choose_image(self):
        from .note_dialog import NoteDialog
        NoteDialog.choose_image(self)

    @property
    def editor(self):
        return self.body

    def wrap_selection(self, marker):
        cursor = self.body.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(marker + selected + marker)
        if not selected:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(marker))
            self.body.setTextCursor(cursor)
        self.body.setFocus()

    def color_menu(self):
        from .polish import color_popup
        color_popup(self, self.color, self.set_color, self.sender() if isinstance(self.sender(), QWidget) else self.actions)

    def set_color(self, color):
        self.color = color
        self.save_draft()

    def more_menu(self):
        menu = QMenu(self)
        menu.addAction('Add checklist', self.checklist)
        menu.addAction('Edit labels', self.edit_labels)
        menu.addAction('Attach files…', self.attachments.choose_files)
        compact = menu.addAction('Filename-only attachments')
        compact.setCheckable(True)
        compact.setChecked(self.attachments.compact)
        compact.toggled.connect(self.attachments.set_compact)
        menu.exec(self.actions.mapToGlobal(self.actions.rect().topLeft()))

    def edit_labels(self):
        from PySide6.QtWidgets import QInputDialog
        text, accepted = QInputDialog.getText(self, 'Note labels', 'Labels, separated by commas', text=self.labels)
        if accepted:
            self.labels = text
            self.save_draft()

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusIn:
            self.expand()
        return super().eventFilter(watched, event)

    def expand(self):
        self.expanded = True
        self.v.setContentsMargins(14, 10, 14, 10)
        self.header.show()
        self.actions.show()
        self.fit_text()
        self.queue_text_resize()

    def queue_text_resize(self, *args):
        if self.expanded and not self._sizing_text:
            self.text_resize.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'text_resize') and event.size().width() != event.oldSize().width():
            self.queue_text_resize()

    def fit_text(self):
        if not self.expanded or self._sizing_text:
            return
        import math
        from .polish import animate_height
        self._sizing_text = True
        try:
            for control in self.secondary_controls:
                control.setVisible(self.width() >= 440)
            self.saved_state.setVisible(self.width() >= 520)
            document = self.body.document()
            height = document.documentLayout().documentSize().height()
            chrome = self.body.height() - self.body.viewport().height()
            attachment_height = self.attachments.height() + 6 if self.attachments.items else 0
            limit = max(64, min(360, self.window().height() - 330 - attachment_height))
            height = min(limit, max(64, math.ceil(height + chrome + 2)))
            if self.body.height() != height:
                self.body.setFixedHeight(height)
            target = 166 + height - 64 + attachment_height
            if target == 166 and getattr(self, '_height_target', 54) <= 54:
                animate_height(self, target)
            elif getattr(self, '_height_target', None) != target:
                previous = getattr(self, '_height_motion', None)
                if previous:
                    previous.stop()
                self._height_target = target
                self.setFixedHeight(target)
            self.cursor_scroll.start(0)
        finally:
            self._sizing_text = False

    def reveal_cursor(self):
        if not self.expanded or not self.body.hasFocus():
            return
        from PySide6.QtWidgets import QScrollArea
        self.body.ensureCursorVisible()
        parent = self.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                point = self.body.mapTo(parent.widget(), self.body.cursorRect().center())
                parent.ensureVisible(point.x(), point.y(), 16, 60)
                break
            parent = parent.parentWidget()

    def checklist(self):
        self.body.add_checklist()

    def commit(self):
        record = self.flush()
        if record:
            self.saved.emit(record)
        else:
            self.expanded = False
            self.text_resize.stop()
            self.header.hide()
            self.actions.hide()
            self.body.setFixedHeight(40)
            self.v.setContentsMargins(12, 6, 12, 6)
            from .polish import animate_height
            animate_height(self, 54)

    def flush(self):
        self.draft_timer.stop()
        body, title = self.body.plain_body(), self.title.text().strip()
        if body.strip() or title or self.attachments.items:
            fallback = self.attachments.items[0]['name'] if self.attachments.items else 'Untitled note'
            record = self.store.save({'kind': 'note', 'title': title or (body.strip().splitlines()[0][:80] if body.strip() else fallback),
                'body': body, 'document': self.body.snapshot(), 'project': self.project, 'pinned': self.pin.isChecked(), 'color': self.color,
                'link_targets': self.body.link_targets, 'labels': self.labels,
                'attachments': list(self.attachments.items), 'attachment_display': 'compact' if self.attachments.compact else 'details'})
            self.title.clear()
            self.body.clear()
            self.pin.setChecked(False)
            self.body.link_targets = {}
            self.attachments.items = []
            self.attachments.render()
            self.store.set_setting(self.draft_key, {})
            self.draft_timer.stop()
            self.saved_state.clear()
            return record
        self.store.set_setting(self.draft_key, {})
        self.saved_state.clear()
        return None
