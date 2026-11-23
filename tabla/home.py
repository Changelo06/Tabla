"""A small, actionable overview of the existing local workspace."""
import calendar
from datetime import date, timedelta
from PySide6.QtCore import Qt, QRectF, QEvent, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (QWidget, QFrame, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy)
from .widgets import label, button, row, scroll, clear
from .theme import themed_color, icon, polish_surfaces, COLORS


class HomeLink(QPushButton):
    def __init__(self, title, subtitle, callback, glyph='board', accent=False, compact=False):
        super().__init__()
        self.title, self.subtitle, self.glyph, self.accent = title, subtitle, glyph, accent
        self.compact = compact
        self.setAccessibleName(title + (', ' + subtitle if subtitle else ''))
        self.setToolTip(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        height = 44 if compact else 60
        self.setFixedHeight(height)
        self.setStyleSheet(f'QPushButton {{min-height:{height}px;max-height:{height}px;min-width:0;padding:0;}}')
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        bg = '#e8f0fe' if self.isDown() else '#eeeeec' if self.underMouse() else '#f7f7f5'
        painter.setBrush(QColor(themed_color(bg)))
        painter.setPen(QPen(QColor('#2383e2' if self.hasFocus() else themed_color('#e9e9e7')), 1))
        painter.drawRoundedRect(rect, 9, 9)
        color = '#b55b4f' if self.accent else themed_color('#69645f')
        icon(self.glyph, color, 18, preserve_color=True).paint(painter, 12, (self.height() - 18) // 2, 18, 18)
        painter.setFont(QFont('Inter', 10, QFont.Weight.Medium))
        painter.setPen(QColor(themed_color('#202124')))
        painter.drawText(42, 18 if self.compact else 25, painter.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, max(10, self.width() - 60)))
        painter.setFont(QFont('Inter', 8))
        painter.setPen(QColor(color if self.accent else themed_color('#69645f')))
        painter.drawText(42, 34 if self.compact else 44, painter.fontMetrics().elidedText(self.subtitle, Qt.TextElideMode.ElideRight, max(10, self.width() - 60)))


class RecentNotes(QWidget):
    """Keep the familiar note cards, bounded to four and reflowed in place."""
    def __init__(self, cards):
        super().__init__()
        self.cards = cards
        for card in cards:
            card.setParent(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = min(2, max(1, (self.width() + 16) // 246))
        width = max(1, (self.width() - 16 * (columns - 1)) // columns)
        heights = [0] * columns
        for index, card in enumerate(self.cards):
            column = index % columns
            layout = card.layout()
            height = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
            height = max(120, height)
            card.setGeometry(column * (width + 16), heights[column], width, height)
            heights[column] += height + 16
            card.show()
        self.setMinimumHeight(max(heights, default=0))


class CalendarDayButton(QPushButton):
    def __init__(self, day, in_month, colors, callback):
        super().__init__(str(day.day))
        self.day, self.in_month, self.colors = day, in_month, colors
        self.setMinimumSize(28, 31)
        self.setStyleSheet('QPushButton {min-width:0;min-height:31px;padding:0;border:none;background:transparent;}')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2 - 1
        today = self.day == date.today()
        if self.colors:
            color = QColor(COLORS[self.colors[0]][1])
            p.setPen(Qt.PenStyle.NoPen)
            for radius, alpha in ((15, 14), (13.5, 20), (12, 30)):
                tint = QColor(color)
                tint.setAlpha(alpha)
                p.setBrush(tint)
                p.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 1))
            p.drawEllipse(QRectF(cx - 12, cy - 12, 24, 24))
        if today or self.isDown() or self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#2383e2' if today else themed_color('#e8e6e2')))
            p.drawEllipse(QRectF(cx - 10.5, cy - 10.5, 21, 21))
        p.setPen(QColor('#fdfdfd' if today else themed_color('#37352f' if self.in_month else '#a5a5a0')))
        p.setFont(self.font())
        p.drawText(QRectF(0, cy - 10, self.width(), 20), Qt.AlignmentFlag.AlignCenter, str(self.day.day))
        for index, name in enumerate(self.colors[:3]):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(COLORS[name][1]))
            x = cx + (index - (min(3, len(self.colors)) - 1) / 2) * 5
            p.drawEllipse(QRectF(x - 1.5, self.height() - 4, 3, 3))


class MiniCalendar(QFrame):
    def __init__(self, owner, items):
        super().__init__()
        self.owner, self.month = owner, date.today().replace(day=1)
        self.dates = {r.get('date') for r in items}
        self.day_colors = {}
        self.day_items = {}
        for record in items:
            key = record.get('date')
            if not key:
                continue
            self.day_items.setdefault(key, []).append(record['title'])
            # Match Calendar's RecordButton fallback exactly, rather than
            # substituting a project's unrelated navigation color.
            color = record.get('color', 'blue')
            color = color if color in COLORS else 'blue'
            if color not in self.day_colors.setdefault(key, []):
                self.day_colors[key].append(color)
        rows = owner.store.db.execute("SELECT json_extract(payload, '$.date'), json_extract(payload, '$.day_color') FROM records WHERE kind='note' AND deleted=0 AND archived=0 AND json_extract(payload, '$.day_annotation')=1")
        for key, color in rows:
            if key and color in COLORS:
                self.day_colors[key] = [color] + [c for c in self.day_colors.get(key, []) if c != color]
        self.day_buttons = {}
        self.setObjectName('homeCalendar')
        self.setAccessibleName('Mini calendar')
        self.setMinimumWidth(270)
        self.setMaximumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        self.heading = button('', self.open_month, 'text')
        self.heading.setAccessibleName('Open month in Calendar')
        layout.addLayout(row(self.heading, None,
            button('', lambda: self.move(-1), 'text', 'left'),
            button('', lambda: self.move(1), 'text', 'right'), spacing=4))
        self.days = QGridLayout()
        self.days.setSpacing(2)
        layout.addLayout(self.days)
        self.render_days()

    def render_days(self):
        clear(self.days)
        self.day_buttons = {}
        self.heading.setText(self.month.strftime('%B %Y'))
        for column, name in enumerate(('S', 'M', 'T', 'W', 'T', 'F', 'S')):
            text = label(name, 'muted')
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.days.addWidget(text, 0, column)
        cal = calendar.Calendar(firstweekday=6)
        for week, dates in enumerate(cal.monthdatescalendar(self.month.year, self.month.month), 1):
            for column, day in enumerate(dates):
                colors = self.day_colors.get(day.isoformat(), [])
                day_button = CalendarDayButton(day, day.month == self.month.month, colors, lambda checked=False, d=day: self.open_day(d))
                self.day_buttons[day.isoformat()] = day_button
                day_button.setAccessibleName(day.strftime('%A, %B %d, %Y'))
                day_button.setToolTip(day.strftime('%B %d') + ('\n' + '\n'.join(self.day_items[day.isoformat()]) if day.isoformat() in self.day_items else '') + ('\n' + ', '.join(colors) if colors else ''))
                self.days.addWidget(day_button, week, column)
        polish_surfaces(self)

    def move(self, delta):
        absolute = self.month.year * 12 + self.month.month - 1 + delta
        if 1 <= absolute // 12 <= 9999:
            self.month = date(absolute // 12, absolute % 12 + 1, 1)
            self.render_days()

    def open_month(self):
        self.owner.month = self.month
        self.owner.selected_day = self.month
        self.owner.calendar_view = 'Month'
        self.owner.navigate('Calendar')

    def open_day(self, day):
        self.owner.month = day.replace(day=1)
        self.owner.selected_day = day
        self.owner.calendar_view = 'Day'
        self.owner.navigate('Calendar')


class HomeDashboard(QWidget):
    """Independent dashboard columns; each section keeps its natural height."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setObjectName('homeDashboard')
        self.setStyleSheet('QFrame#homeCalendar {border:1px solid #e9e9e7;border-radius:12px;background:#f7f7f5;} QFrame#homeSectionHeader {border:none;border-radius:6px;background:#f7f7f5;}')
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(24)
        self.left = QWidget()
        left = QVBoxLayout(self.left)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)
        tasks = owner.store.records('task')
        events = owner.store.records('event') + owner.store.records('block')
        self.calendar = MiniCalendar(owner, tasks + events)
        self.calendar.setMaximumWidth(16777215)
        left.addWidget(self.calendar)
        self.board_section, board_layout = self.section('Boards', lambda: owner.navigate('Board'))
        self.boards = owner.board_catalog.boards()
        self.boards.sort(key=lambda b: b['id'] != owner.board_id)
        for board in self.boards[:6]:
            project = owner.store.get(board.get('project'))
            link = HomeLink(board['title'], project['title'] if project else 'Personal', lambda checked=False, bid=board['id']: owner.select_board(bid), compact=True)
            board_layout.addWidget(link)
        left.addWidget(self.board_section)
        left.addStretch()
        self.deadlines, due_layout = self.section('Tasks', lambda: owner.navigate('Board'))
        today = date.today()
        self.due_tasks = sorted((r for r in tasks if r.get('date') and r.get('status') != 'Done'), key=lambda r: (r['date'], r['title'].casefold()))[:4]
        self.visible_tasks = self.due_tasks or [r for r in tasks if r.get('status') != 'Done'][:4]
        self.deadline_links = []
        for task in self.visible_tasks:
            day = date.fromisoformat(task['date']) if task.get('date') else None
            caption = 'No date' if day is None else 'Today' if day == today else 'Tomorrow' if day == today + timedelta(days=1) else day.strftime('%b %d, %Y' if day.year != today.year else '%b %d')
            overdue = day is not None and day < today
            if overdue:
                caption = 'Overdue: ' + caption
            board = owner.store.get(task.get('board'))
            if board:
                caption += ' / ' + board['title']
            link = HomeLink(task['title'], caption, lambda checked=False, rid=task['id']: owner.open_record(rid), 'clock', overdue)
            self.deadline_links.append(link)
            due_layout.addWidget(link)
        if not self.visible_tasks:
            due_layout.addWidget(label('No open tasks', 'muted'))
            due_layout.addLayout(row(button('Add a task', owner.new_task, 'text', 'plus'), None))
        self.notes_section, notes_layout = self.section('Notes', lambda: owner.navigate('Notes'))
        self.notes = owner.store.records('note', limit=4)
        self.note_cards = [owner.note_card(note, compact=True) for note in self.notes]
        self.notes_area = QScrollArea()
        self.notes_area.setObjectName('homeNotesScroll')
        self.notes_area.setAccessibleName('Recent notes')
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setFrameShape(QFrame.Shape.NoFrame)
        self.notes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_area.setFixedHeight(240)
        if self.note_cards:
            self.notes_area.setWidget(RecentNotes(self.note_cards))
        else:
            empty = QWidget()
            empty_layout = QVBoxLayout(empty)
            empty_layout.addWidget(label('Your latest notes will appear here.', 'muted'))
            empty_layout.addLayout(row(button('Take a note', owner.new_note, 'text', 'plus'), None))
            empty_layout.addStretch()
            self.notes_area.setWidget(empty)
        notes_layout.addWidget(self.notes_area)
        self.page_area = None
        self._notes_fit_pending = False
        self.mode = None
        self.wide = False
        self.reflow(1200)

    def section(self, title, opened):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QFrame()
        heading.setObjectName('homeSectionHeader')
        heading_layout = QHBoxLayout(heading)
        heading_layout.setContentsMargins(10, 3, 8, 3)
        heading_layout.addWidget(label(title, 'section'))
        heading_layout.addStretch()
        link = button('All', opened, 'text')
        link.setAccessibleName('All ' + title.lower())
        heading_layout.addWidget(link)
        layout.addWidget(heading)
        return host, layout

    def reflow(self, width):
        mode = 3 if width >= 1120 else 2 if width >= 760 else 1
        if mode == self.mode:
            return
        self.mode, self.wide = mode, mode > 1
        for widget in (self.left, self.deadlines, self.notes_section):
            self.grid.removeWidget(widget)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
            self.grid.setColumnMinimumWidth(column, 0)
        if mode == 3:
            self.grid.addWidget(self.left, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.deadlines, 0, 1, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.notes_section, 0, 2, Qt.AlignmentFlag.AlignTop)
            for column, weight in enumerate((3, 3, 6)):
                self.grid.setColumnStretch(column, weight)
        elif mode == 2:
            self.grid.addWidget(self.left, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.deadlines, 0, 1, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.notes_section, 1, 1, Qt.AlignmentFlag.AlignTop)
            self.grid.setColumnStretch(0, 3)
            self.grid.setColumnStretch(1, 5)
        else:
            self.grid.addWidget(self.left, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.deadlines, 1, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.notes_section, 2, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.setColumnStretch(0, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow(self.width())
        self.queue_notes_fit()

    def eventFilter(self, watched, event):
        if self.page_area is not None and watched is self.page_area.viewport() and event.type() == QEvent.Type.Resize:
            self.queue_notes_fit()
        return super().eventFilter(watched, event)

    def queue_notes_fit(self):
        if self.page_area is not None and not self._notes_fit_pending:
            self._notes_fit_pending = True
            QTimer.singleShot(0, self, self.fit_notes)

    def fit_notes(self):
        self._notes_fit_pending = False
        self.grid.activate()
        heading = self.notes_section.layout().itemAt(0).widget()
        available = self.page_area.viewport().height() - self.notes_section.y() - heading.height() - self.notes_section.layout().spacing() - 2
        self.notes_area.setFixedHeight(max(120, available))


def render_home(owner):
    owner.home = HomeDashboard(owner)
    area = scroll(owner.home)
    owner.home.page_area = area
    area.viewport().installEventFilter(owner.home)
    owner.content.addWidget(area, 1)
    owner.home.queue_notes_fit()
