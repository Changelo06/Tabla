"""Card-first board: independent scrollable lists and precise persistent moves."""
from datetime import date
import copy
from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QPoint, QPointF, QRectF, QTimer
from PySide6.QtGui import QDrag, QPainter, QPainterPath, QPixmap, QColor, QFont, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QStyledItemDelegate, QAbstractItemView, QMenu, QStyle,
    QPushButton, QMessageBox, QScrollArea)
from .widgets import button, label, row, clear
from .theme import COLORS, themed_color, polish_surfaces
from .tokens import current_tokens
from .board_model import BoardModel

CARD_MIME = 'application/x-tabla-card'
LIST_MIME = 'application/x-tabla-list'


def _lifted_drag_pixmap(source: QPixmap, radius: float = 11.0, tilt_deg: float = 1.6) -> tuple[QPixmap, QPoint]:
    """Create a tactile lifted drag preview with rounded clip, subtle tilt, and elevation shadow."""
    t = current_tokens()
    dpr = source.devicePixelRatio() or 1.0
    lw = source.width() / dpr
    lh = source.height() / dpr
    pad = 16
    out = QPixmap(max(1, round((lw + pad * 2) * dpr)), max(1, round((lh + pad * 2) * dpr)))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.translate(pad + lw / 2.0, pad + lh / 2.0)
    p.rotate(tilt_deg)
    rect = QRectF(-lw / 2.0, -lh / 2.0, lw, lh)
    # Soft multi-ring lift shadow
    p.setPen(Qt.PenStyle.NoPen)
    base_alpha = 38 if t.dark else 18
    for expand, mult in ((9.0, 0.35), (5.0, 0.55), (2.0, 0.85)):
        p.setBrush(QColor(0, 0, 0, round(base_alpha * mult)))
        p.drawRoundedRect(rect.adjusted(-expand, -expand + 3.0, expand, expand + 5.0), radius + 2, radius + 2)
    clip = QPainterPath()
    clip.addRoundedRect(rect, radius, radius)
    p.save()
    p.setClipPath(clip)
    p.setOpacity(0.95)
    p.drawPixmap(rect, source, QRectF(source.rect()))
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(t.accent), 1.4))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.end()
    return out, QPoint(pad, pad)


class CardDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        from .tokens import ui_font
        self._title_font = ui_font(13, QFont.Weight.Medium)
        self._title_font_key = self._title_font.toString()
        self._tag_font = ui_font(11, QFont.Weight.Medium)
        self._meta_font = ui_font(11)
        self._title_cache = {}

    def title_layout(self, text, width):
        key = (text, width, self._title_font_key)
        if key in self._title_cache:
            return self._title_cache[key]
        layout = QTextLayout(text, self._title_font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0
        for _ in range(3):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(70, width))
            line.setPosition(QPointF(0, y))
            y += line.height()
        layout.endLayout()
        if len(self._title_cache) > 1200:
            self._title_cache.clear()
        self._title_cache[key] = (layout, y)
        return layout, y

    def sizeHint(self, option, index):
        record = index.data(Qt.ItemDataRole.UserRole) or {}
        _, height = self.title_layout(record.get('title', ''), max(160, option.rect.width() - 30))
        meta = record.get('date') or record.get('checklists') or record.get('attachments') or record.get('comments') or record.get('body') or record.get('priority', 'Medium') != 'Medium'
        return QSize(244, int(height) + 30 + (24 if meta else 0) + (23 if record.get('task_labels') else 0) + (10 if record.get('cover') else 0))

    def paint(self, painter, option, index):
        record = index.data(Qt.ItemDataRole.UserRole) or {}
        t = current_tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(4, 3, -4, -4)
        if getattr(self.parent(), '_dragging_id', None) == record.get('id'):
            ghost_bg = QColor(t.accent)
            ghost_bg.setAlpha(22 if t.dark else 16)
            ghost_pen = QPen(QColor(t.accent), 1.2, Qt.PenStyle.DashLine)
            painter.setBrush(ghost_bg)
            painter.setPen(ghost_pen)
            painter.drawRoundedRect(rect, 11, 11)
            painter.restore()
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 26 if t.dark else 10))
        painter.drawRoundedRect(rect.translated(0, 1.5), 11, 11)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus))
        border_color = t.accent if focused else (t.border_strong if hovered else t.border_subtle)
        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(QColor(t.bg_elevated))
        painter.drawRoundedRect(rect, 11, 11)
        x, y = rect.x() + 12, rect.y() + 11
        if record.get('cover'):
            bg = COLORS.get(record['cover'], COLORS['blue'])[0]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(themed_color(bg)))
            painter.drawRoundedRect(QRectF(x, y - 3, rect.width() - 24, 5), 2.5, 2.5)
            y += 10
        painter.setFont(self._tag_font)
        tag_fm = painter.fontMetrics()
        max_x = rect.right() - 32
        for tag in record.get('task_labels', [])[:3]:
            bg = COLORS.get(tag['color'], COLORS['blue'])[0]
            chip_w = min(96, max(36, tag_fm.horizontalAdvance(tag['name']) + 14))
            if x + chip_w > max_x:
                chip_w = max(32, int(max_x - x))
            if chip_w < 28:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(themed_color(bg)))
            painter.drawRoundedRect(QRectF(x, y, chip_w, 18), 6, 6)
            painter.setPen(QColor(t.ink_primary))
            painter.drawText(QRectF(x + 7, y, chip_w - 14, 18), Qt.AlignmentFlag.AlignVCenter,
                tag_fm.elidedText(tag['name'], Qt.TextElideMode.ElideRight, int(chip_w - 14)))
            x += chip_w + 5
        if len(record.get('task_labels', [])) > 3:
            painter.setPen(QColor(t.ink_muted))
            painter.drawText(QRectF(x, y, 24, 18), Qt.AlignmentFlag.AlignVCenter, '+' + str(len(record['task_labels']) - 3))
        if record.get('task_labels'):
            y += 24
        x = rect.x() + 12
        layout, height = self.title_layout(record.get('title', ''), rect.width() - 28)
        painter.setPen(QColor(t.ink_primary))
        layout.draw(painter, QPointF(x, y))
        y += height + 10
        bits = []
        due = record.get('date')
        if due:
            day = date.fromisoformat(due)
            bits.append(day.strftime('%b %d').replace(' 0', ' '))
        items = [i for c in record.get('checklists', []) for i in c['items']]
        if items:
            bits.append('✓ ' + str(sum(i['checked'] for i in items)) + '/' + str(len(items)))
        if record.get('attachments'):
            bits.append(str(len(record['attachments'])) + (' file' if len(record['attachments']) == 1 else ' files'))
        if record.get('comments'):
            bits.append(str(len(record['comments'])) + (' comment' if len(record['comments']) == 1 else ' comments'))
        if not bits:
            if record.get('body'):
                bits.append('≡ Description')
            elif record.get('priority', 'Medium') != 'Medium':
                bits.append(record.get('priority', '') + ' priority')
        painter.setFont(self._meta_font)
        overdue = bool(due and due < date.today().isoformat() and record.get('status') != 'Done')
        painter.setPen(QColor(t.danger if overdue else t.ink_muted))
        text = ' · '.join(bits)
        painter.drawText(QRectF(x, y, rect.width() - 24, 18), Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() - 24)))
        painter.restore()


class CardList(QListWidget):
    moved = Signal(str, str, object)

    def __init__(self, column, records, opened, menu, parent=None):
        super().__init__(parent)
        self.column = column
        self.card_menu = menu
        self.setObjectName('boardCards')
        self.setAccessibleName(column['title'] + ' cards. Drag to reorder; Enter opens; use the context menu to move.')
        self.setItemDelegate(CardDelegate(self))
        self.setSpacing(3)
        self.setMinimumHeight(24)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setStyleSheet('QListWidget#boardCards {border:none;background:transparent;outline:0;}')
        for record in records:
            item = QListWidgetItem(record['title'])
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(record['title'])
            self.addItem(item)
        self.itemClicked.connect(lambda item: opened(item.data(Qt.ItemDataRole.UserRole)['id']))
        self.itemActivated.connect(lambda item: opened(item.data(Qt.ItemDataRole.UserRole)['id']))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def context(point):
            item = self.itemAt(point)
            if item:
                menu(item.data(Qt.ItemDataRole.UserRole), self.viewport().mapToGlobal(point))
        self.customContextMenuRequested.connect(context)
        self._drop_index = None
        self._dragging_id = None
        self._press = QPoint()

    def mousePressEvent(self, event):
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def startDrag(self, actions):
        item = self.currentItem()
        if not item:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)['id']
        item_rect = self.visualItemRect(item)
        raw = self.viewport().grab(item_rect.adjusted(4, 3, -4, -4))
        lifted, offset = _lifted_drag_pixmap(raw, radius=11.0, tilt_deg=1.6)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(CARD_MIME, record_id.encode())
        drag.setMimeData(mime)
        drag.setPixmap(lifted)
        drag.setHotSpot(self._press - item_rect.topLeft() + offset - QPoint(4, 3))
        self._dragging_id = record_id
        self.viewport().update()
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._dragging_id = None
            self._drop_index = None
            self.viewport().update()

    def keyPressEvent(self, event):
        if self.currentItem() and (event.key() == Qt.Key.Key_Menu or event.key() == Qt.Key.Key_F10 and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.card_menu(self.currentItem().data(Qt.ItemDataRole.UserRole), self.viewport().mapToGlobal(self.visualItemRect(self.currentItem()).center()))
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(CARD_MIME):
            return
        point = event.position().toPoint()
        item = self.itemAt(point)
        self._drop_index = self.row(item) + (point.y() > self.visualItemRect(item).center().y()) if item else self.count()
        if point.y() < 28:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - 24)
        elif point.y() > self.viewport().height() - 28:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + 24)
        # Horizontal drag-edge autoscroll on enclosing TaskBoard canvas
        board = self.parentWidget()
        while board is not None and not isinstance(board, QScrollArea):
            board = board.parentWidget()
        if board is not None:
            bx = board.viewport().mapFromGlobal(self.viewport().mapToGlobal(point)).x()
            hbar = board.horizontalScrollBar()
            if bx < 56:
                hbar.setValue(hbar.value() - 28)
            elif bx > board.viewport().width() - 56:
                hbar.setValue(hbar.value() + 28)
        self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drop_index = None
        self.viewport().update()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            index = self._drop_index if self._drop_index is not None else self.count()
            before = self.item(index).data(Qt.ItemDataRole.UserRole)['id'] if index < self.count() else None
            self.moved.emit(bytes(event.mimeData().data(CARD_MIME)).decode(), self.column['id'], before)
            self._drop_index = None
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_index is not None:
            t = current_tokens()
            accent = QColor(t.accent)
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            y = self.visualItemRect(self.item(self._drop_index)).top() if self._drop_index < self.count() else self.visualItemRect(self.item(self.count() - 1)).bottom() + 3 if self.count() else 5
            painter.setPen(QPen(accent, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(10, y), QPointF(self.viewport().width() - 10, y))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(10, y), 3.4, 3.4)
            painter.drawEllipse(QPointF(self.viewport().width() - 10, y), 3.4, 3.4)
            painter.end()


class ListGrip(QPushButton):
    def __init__(self, column):
        from .theme import icon
        super().__init__('')
        self.column = column
        self.setObjectName('text')
        self.setIcon(icon('grip', size=16))
        self.setIconSize(QSize(16, 16))
        self.setFixedSize(22, 24)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip('Drag list to reorder')
        self.setAccessibleName('Drag ' + column['title'] + ' list')
        self.origin = None

    def mousePressEvent(self, event):
        self.origin = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton and (event.position().toPoint() - self.origin).manhattanLength() > 6:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(LIST_MIME, self.column['id'].encode())
            drag.setMimeData(mime)
            panel = self.parentWidget()
            scaled = panel.grab().scaledToWidth(220, Qt.TransformationMode.SmoothTransformation)
            lifted, offset = _lifted_drag_pixmap(scaled, radius=13.0, tilt_deg=1.4)
            drag.setPixmap(lifted)
            point = self.mapTo(panel, self.origin)
            drag.setHotSpot(QPoint(round(point.x() * 220 / panel.width()), round(point.y() * 220 / panel.width())) + offset)
            drag.exec(Qt.DropAction.MoveAction)
            self.setDown(False)
            self.origin = None


class ListPanel(QFrame):
    def __init__(self, board, column):
        super().__init__()
        self.board, self.column = board, column
        self.setObjectName('boardList')
        self.setFixedWidth(280)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        title = QLineEdit(column['title'])
        self.title_field = title
        title.setMaxLength(100)
        title.setObjectName('listTitle')
        title.setAccessibleName('Rename ' + column['title'] + ' list')
        title.editingFinished.connect(lambda: board.rename(column['id'], title))
        cards = board.grouped.get(column['id'], [])
        self.count = label(str(len(cards)), 'fieldLabel')
        menu = button('', lambda: board.list_menu(column, self), 'text', 'more-h')
        menu.setFixedSize(26, 26)
        menu.setAccessibleName(column['title'] + ' list actions')
        menu.setToolTip(column['title'] + ' list actions')
        layout.addLayout(row(ListGrip(column), title, self.count, menu))
        self.cards = CardList(column, cards, board.opened, board.card_menu)
        self.cards.moved.connect(board.move_card)
        layout.addWidget(self.cards, 1)
        self.composer = QWidget()
        compose = QVBoxLayout(self.composer)
        compose.setContentsMargins(0, 0, 0, 0)
        compose.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText('Enter a card title…')
        self.input.setAccessibleName('New card in ' + column['title'])
        compose.addWidget(self.input)
        compose.addLayout(row(button('Add card', self.add_card, 'primary'), button('Cancel', self.close_composer, 'text'), None))
        self.input.returnPressed.connect(self.add_card)
        self.composer.hide()
        layout.addWidget(self.composer)
        self.add_button = button('+ Add a card', self.open_composer, 'text')
        layout.addWidget(self.add_button)

    def open_composer(self):
        self.composer.show()
        self.add_button.hide()
        self.input.setFocus()
        self.fit()

    def close_composer(self):
        self.composer.hide()
        self.add_button.show()
        self.input.clear()
        self.fit()

    def add_card(self):
        if self.input.text().strip():
            rank = max((r.get('board_position', 0) for r in self.board.model.cards(self.column['id'])), default=0) + 1024
            record = self.board.model.store.save({'kind': 'task', 'title': self.input.text().strip(), 'status': self.column['status'], 'project': self.board.project, 'priority': 'Medium', 'board': self.board.model.board_id, 'board_list': self.column['id'], 'board_position': rank})
            item = QListWidgetItem(record['title'])
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.cards.addItem(item)
            self.cards.scrollToBottom()
            self.count.setText(str(self.cards.count()))
            self.input.clear()
            self.input.setFocus()
            self.fit()

    def fit(self):
        self.cards.doItemsLayout()
        total = sum(self.cards.sizeHintForRow(i) + self.cards.spacing() * 2 for i in range(self.cards.count()))
        # Derive the chrome from its actual layout. A fixed allowance clipped
        # the card viewport at larger fonts/display scales, even for one card.
        layout = self.layout()
        margins = layout.contentsMargins()
        chrome = margins.top() + margins.bottom()
        visible_items = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is not None and item.widget().isHidden():
                continue
            visible_items.append(item)
            if item.widget() is not self.cards:
                chrome += item.sizeHint().height()
        chrome += max(0, len(visible_items) - 1) * layout.spacing()
        card_margins = self.cards.contentsMargins()
        target = chrome + max(24, total) + card_margins.top() + card_margins.bottom() + 2
        self.setFixedHeight(max(120, min(max(120, self.board.viewport().height() - 12), target)))
        layout.activate()

    def _set_list_drop_highlight(self, active: bool):
        t = current_tokens()
        if active:
            self.setProperty('tablaThemed', True)
            self.setStyleSheet(f'QFrame#boardList {{background:{t.bg_surface};border:1.5px solid {t.accent};border-radius:14px;}}')
        else:
            self.setProperty('tablaThemed', False)
            self.setStyleSheet('')

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(LIST_MIME):
            self._set_list_drop_highlight(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_list_drop_highlight(False)
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(LIST_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._set_list_drop_highlight(False)
        if event.mimeData().hasFormat(LIST_MIME):
            source = bytes(event.mimeData().data(LIST_MIME)).decode()
            if source == self.column['id']:
                event.acceptProposedAction()
                return
            self.board.model.move_list(source, self.column['id'])
            event.acceptProposedAction()
            self.board.reload()


class TaskBoard(QScrollArea):
    def __init__(self, store, records, opened, refresh, project=None, focus=None, state=None, board_id=None, records_provider=None):
        super().__init__()
        self.model, self.records, self.opened = BoardModel(store, board_id), records, opened
        self.project, self.reload, self.focus = project, self.reconcile, focus
        self.records_provider = records_provider
        self.group_records()
        self.restore_state = state or {}
        self.setWidgetResizable(True)
        self.setObjectName('taskBoard')
        self.setAccessibleName('Task board')
        host = QWidget()
        columns = QHBoxLayout(host)
        self.columns_layout = columns
        columns.setContentsMargins(0, 4, 4, 4)
        columns.setSpacing(12)
        for column in self.model.lists():
            panel = ListPanel(self, column)
            draft = self.restore_state.get('drafts', {}).get(column['id'], {})
            if draft.get('open'):
                panel.composer.show()
                panel.add_button.hide()
                panel.input.setText(draft.get('text', ''))
            columns.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)
        add = QFrame()
        add.setObjectName('boardList')
        add.setFixedWidth(260)
        v = QVBoxLayout(add)
        v.setContentsMargins(10, 10, 10, 10)
        trigger = button('+ Add another list', name='text')
        v.addWidget(trigger)
        composer = QWidget()
        compose = QVBoxLayout(composer)
        compose.setContentsMargins(0, 0, 0, 0)
        name = QLineEdit()
        name.setMaxLength(100)
        name.setPlaceholderText('New list title…')
        name.setAccessibleName('New list title')
        self.new_list_name, self.new_list_composer, self.new_list_trigger = name, composer, trigger
        if self.restore_state.get('new_list'):
            name.setText(self.restore_state['new_list'])
            composer.show()
            trigger.hide()
        compose.addWidget(name)
        def create():
            if name.text().strip():
                self.model.add_list(name.text())
                name.clear()
                composer.hide()
                trigger.show()
                add.adjustSize()
                self.reload()
        name.returnPressed.connect(create)
        compose.addLayout(row(button('Add list', create, 'primary'), button('Cancel', lambda: (composer.hide(), trigger.show(), add.adjustSize()), 'text')))
        composer.hide()
        v.addWidget(composer)
        trigger.clicked.connect(lambda: (trigger.hide(), composer.show(), name.setFocus(), add.adjustSize()))
        columns.addWidget(add, 0, Qt.AlignmentFlag.AlignTop)
        columns.addStretch()
        self.setWidget(host)
        if self.restore_state.get('new_list'):
            composer.show()
            trigger.hide()
        self.persist_timer = QTimer(self)
        self.persist_timer.setSingleShot(True)
        self.persist_timer.setInterval(350)
        self.persist_timer.timeout.connect(self.persist)
        name.textChanged.connect(lambda: self.persist_timer.start())
        for panel in self.findChildren(ListPanel):
            panel.input.textChanged.connect(lambda: self.persist_timer.start())
        polish_surfaces(self)

    def snapshot(self):
        return {'horizontal': self.horizontalScrollBar().value(),
                'lists': {p.column['id']: p.cards.verticalScrollBar().value() for p in self.findChildren(ListPanel)},
                'drafts': {p.column['id']: {'text': p.input.text(), 'open': not p.composer.isHidden()} for p in self.findChildren(ListPanel)},
                'new_list': self.new_list_name.text()}

    def persist(self):
        if self.model.board_id:
            previous = self.model.store.setting('board_view_' + self.model.board_id, {})
            previous.update(self.snapshot())
            self.model.store.set_setting('board_view_' + self.model.board_id, previous)

    def group_records(self):
        self.grouped = {}
        for record in self.records:
            self.grouped.setdefault(self.model.column_for(record), []).append(record)
        for cards in self.grouped.values():
            cards.sort(key=lambda r: (r.get('board_position', 0), r.get('created_at', ''), r['id']))

    def reconcile(self):
        """Patch existing list widgets rather than rebuild the workspace."""
        self.records = self.records_provider() if self.records_provider else self.model.store.records('task', project=self.project, board=self.model.board_id)
        self.model._config_cache = None
        self.group_records()
        active = self.model.lists()
        panels = {p.column['id']: p for p in self.findChildren(ListPanel)}
        for list_id, panel in panels.items():
            if not any(c['id'] == list_id for c in active):
                self.columns_layout.removeWidget(panel)
                panel.hide()
                panel.deleteLater()
        for index, column in enumerate(active):
            panel = panels.get(column['id'])
            if panel is None:
                panel = ListPanel(self, column)
                panel.input.textChanged.connect(lambda: self.persist_timer.start())
            panel.column = column
            if self.columns_layout.indexOf(panel) != index:
                self.columns_layout.removeWidget(panel)
                self.columns_layout.insertWidget(index, panel, 0, Qt.AlignmentFlag.AlignTop)
            panel.show()
            if not panel.title_field.hasFocus():
                panel.title_field.setText(column['title'])
            records = self.grouped.get(column['id'], [])
            if [panel.cards.item(i).data(Qt.ItemDataRole.UserRole) for i in range(panel.cards.count())] == records:
                continue
            panel.cards.setUpdatesEnabled(False)
            position = panel.cards.verticalScrollBar().value()
            selected = panel.cards.currentItem()
            selected_id = selected.data(Qt.ItemDataRole.UserRole)['id'] if selected else None
            existing = {}
            while panel.cards.count():
                item = panel.cards.takeItem(0)
                existing[item.data(Qt.ItemDataRole.UserRole)['id']] = item
            for record in records:
                item = existing.pop(record['id'], None) or QListWidgetItem(record['title'])
                item.setText(record['title'])
                item.setData(Qt.ItemDataRole.UserRole, record)
                item.setToolTip(record['title'])
                panel.cards.addItem(item)
                if record['id'] == selected_id:
                    panel.cards.setCurrentItem(item)
            panel.count.setText(str(len(records)))
            panel.fit()
            panel.cards.verticalScrollBar().setValue(position)
            panel.cards.setUpdatesEnabled(True)
        self.persist()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for panel in self.findChildren(ListPanel):
            panel.fit()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_lists)

    def fit_lists(self):
        for panel in self.findChildren(ListPanel):
            panel.fit()
        if self.restore_state:
            self.horizontalScrollBar().setValue(self.restore_state.get('horizontal', 0))
            for panel in self.findChildren(ListPanel):
                panel.cards.verticalScrollBar().setValue(self.restore_state.get('lists', {}).get(panel.column['id'], 0))
            self.restore_state = {}

    def rename(self, list_id, field):
        if field.text().strip():
            self.model.rename(list_id, field.text())
        else:
            field.setText(next(c['title'] for c in self.model.lists() if c['id'] == list_id))

    def move_card(self, card_id, column, before=None):
        if card_id != before:
            from . import foley
            self.model.move_card(card_id, column, before)
            foley.play('click')
            self.reload()

    def list_menu(self, column, anchor):
        menu = QMenu(self)
        menu.addAction('List settings', lambda: self.list_settings(column['id']))
        menu.addSeparator()
        lists = self.model.lists()
        index = next(i for i, c in enumerate(lists) if c['id'] == column['id'])
        left = menu.addAction('Move list left', lambda: (self.model.move_list(column['id'], lists[index - 1]['id']), self.reload()))
        left.setEnabled(index > 0)
        right = menu.addAction('Move list right', lambda: (self.model.move_list(lists[index + 1]['id'], column['id']), self.reload()))
        right.setEnabled(index < len(lists) - 1)
        menu.addSeparator()
        def archive_cards():
            for card in self.model.cards(column['id'], self.records):
                card['archived'] = True
                self.model.store.save(card)
            self.reload()
        menu.addAction('Archive cards in this view', archive_cards)
        archive = menu.addAction('Archive list', lambda: (self.model.archive_list(column['id']), self.reload()))
        archive.setEnabled(len(lists) > 1 if self.model.board_id else column['id'] not in ('todo', 'doing', 'done'))
        polish_surfaces(menu)
        menu.exec(anchor.mapToGlobal(QPoint(20, 35)))

    def list_settings(self, list_id):
        from .dialogs import PolishedDialog, dialog_header
        from .pickers import ChoiceMenu
        dialog = PolishedDialog(self.window())
        dialog.modal_surface = True
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(min(440, self.window().width() - 30), 260)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        column = next(c for c in self.model.lists() if c['id'] == list_id)
        dialog_header(layout, 'List settings', dialog.reject)
        layout.addWidget(label(column['title'], 'section'))
        layout.addWidget(label('When a card is completed', 'fieldLabel'))
        choices = [('Stay in this list', None)] + [(c['title'], c['id']) for c in self.model.lists() if c['id'] != list_id]
        selected = [column.get('completion_target')]
        picker = button(next((title for title, value in choices if value == selected[0]), 'Stay in this list'), name='tab')
        picker.setAccessibleName('Completed card destination')
        def choose():
            menu = ChoiceMenu(choices, selected[0], dialog, 'Move completed cards to')
            def changed(value):
                selected[0] = value
                picker.setText(next(title for title, key in choices if key == value))
            menu.chosen.connect(changed)
            menu.exec(picker.mapToGlobal(picker.rect().bottomLeft()))
        picker.clicked.connect(choose)
        layout.addWidget(picker)
        error = label('', 'formError', True)
        layout.addWidget(error)
        layout.addStretch()
        def save():
            try:
                self.model.set_completion_target(list_id, selected[0])
            except Exception as exc:
                error.setText(str(exc))
                return
            dialog.accept()
            self.reload()
        layout.addLayout(row(None, button('Cancel', dialog.reject), button('Save', save, 'primary')))
        polish_surfaces(dialog)
        dialog.exec()
        dialog.deleteLater()

    def card_menu(self, card, point):
        menu = QMenu(self)
        menu.addAction('Open card', lambda: self.opened(card['id']))
        moves = menu.addMenu('Move to list')
        for column in self.model.lists():
            moves.addAction(column['title'], lambda checked=False, c=column['id']: self.move_card(card['id'], c))
        current = self.model.column_for(card)
        cards = self.model.cards(current)
        menu.addAction('Move to top', lambda: self.move_card(card['id'], current, cards[0]['id'] if cards else None))
        menu.addAction('Move to bottom', lambda: self.move_card(card['id'], current))
        if self.focus:
            menu.addAction('Focus on this card', lambda: self.focus(card['id']))
        def duplicate():
            record = copy.deepcopy(self.model.store.get(card['id']))
            for key in ('id', 'created_at', 'updated_at', 'revision', 'comments'):
                record.pop(key, None)
            record['title'] += ' (copy)'
            record.update(archived=False, deleted=False, board_list_archived=False)
            created = self.model.store.save(record)
            self.model.move_card(created['id'], self.model.column_for(card))
            self.reload()
        menu.addAction('Duplicate card', duplicate)
        menu.addSeparator()
        def archive():
            latest = self.model.store.get(card['id'])
            latest['archived'] = True
            self.model.store.save(latest)
            self.reload()
        menu.addAction('Archive card', archive)
        polish_surfaces(menu)
        menu.exec(point)
