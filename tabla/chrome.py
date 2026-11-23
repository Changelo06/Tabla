"""Native window chrome: working menus, history controls, drag and resize."""
from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QRectF
from PySide6.QtGui import QCursor, QPainter, QColor, QPen
from PySide6.QtWidgets import (QFrame, QLabel, QHBoxLayout, QMenu, QToolButton, QLineEdit,
    QSizePolicy, QApplication, QWidget, QMessageBox, QPushButton)
from .widgets import button, label
from .theme import icon, polish_surfaces


class WindowControl(QPushButton):
    """Small traffic light, full-height rectangular pointer target."""
    def __init__(self, action, color, tip, callback, parent=None):
        super().__init__(parent)
        self.action, self.color = action, color
        self.setObjectName('trafficLight')
        self.setFixedSize(48, 43)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() or bool(self.property('nativeHover'))
        color = QColor(self.color)
        if hovered or self.isDown():
            tint = QColor(color)
            tint.setAlpha(34 if self.isDown() else 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 3, -2, -3), 8, 8)
        if self.isDown():
            color = color.darker(115)
        painter.setBrush(color)
        painter.setPen(QPen(color.darker(112), .7))
        x, y = self.width() / 2, self.height() / 2
        painter.drawEllipse(QRectF(x - 8, y - 8, 16, 16))
        if hovered:
            painter.setPen(QPen(QColor('#292b2e'), 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            if self.action == 'minimize':
                painter.drawLine(int(x - 3), int(y), int(x + 3), int(y))
            elif self.action == 'maximize':
                if self.window().isMaximized():
                    painter.drawRoundedRect(QRectF(x - 3, y - 3, 6, 6), .7, .7)
                else:
                    painter.drawLine(int(x - 3), int(y), int(x + 3), int(y))
                    painter.drawLine(int(x), int(y - 3), int(x), int(y + 3))
            elif self.action == 'close':
                painter.drawLine(int(x - 2), int(y - 2), int(x + 2), int(y + 2))
                painter.drawLine(int(x + 2), int(y - 2), int(x - 2), int(y + 2))


class TitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setObjectName('titleBar')
        self.setFixedHeight(43)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(3)
        self.back = self.control('Back', 'left', lambda: window.history_step(-1))
        self.forward = self.control('Forward', 'right', lambda: window.history_step(1))
        layout.addWidget(self.back)
        layout.addWidget(self.forward)
        layout.addWidget(self.control('Toggle sidebar', 'sidebar', window.toggle_sidebar))
        separator = QFrame()
        separator.setFixedSize(1, 17)
        separator.setStyleSheet('background:#e5e5e3;')
        layout.addWidget(separator)
        self.menus = {}
        self.menu_buttons = []
        for title in ('File', 'Edit', 'View', 'Layout', 'Settings', 'Help'):
            btn = QToolButton()
            btn.setText(title)
            btn.setObjectName('menuButton')
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            menu = QMenu(btn)
            menu.setTitle(title)
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            layout.addWidget(btn)
            self.menus[title] = menu
            self.menu_buttons.append(btn)
        self.overflow = QToolButton()
        self.overflow.setText('Menu')
        self.overflow.setObjectName('menuButton')
        self.overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        overflow_menu = QMenu(self.overflow)
        for menu in self.menus.values():
            overflow_menu.addMenu(menu)
        self.overflow.setMenu(overflow_menu)
        self.overflow.setAccessibleName('Application menus')
        layout.addWidget(self.overflow)
        self.build_menus()
        self.drag_area = QWidget()
        self.drag_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.drag_area.installEventFilter(self)
        search_layout = QHBoxLayout(self.drag_area)
        search_layout.setContentsMargins(12, 0, 12, 0)
        search_layout.setSpacing(0)
        search_layout.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName('titleSearch')
        self.search.setPlaceholderText('Search')
        self.search.setAccessibleName('Search workspace')
        self.search.setToolTip('Search notes, tasks, projects and meetings · Enter to search · Ctrl+K')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(80)
        self.search.setMaximumWidth(520)
        self.search.setFixedHeight(28)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_action = self.search.addAction(icon('search'), QLineEdit.ActionPosition.LeadingPosition)
        self.search_action.triggered.connect(window.focus_search)
        self.search.returnPressed.connect(lambda: window.run_workspace_search(self.search.text()))
        self.search.installEventFilter(self)
        search_layout.addWidget(self.search, 4)
        search_layout.addStretch()
        layout.addWidget(self.drag_area, 1)
        self.minimize = WindowControl('minimize', '#febc2e', 'Minimize', window.showMinimized, self)
        self.maximize = WindowControl('maximize', '#28c840', 'Maximize', self.toggle_maximize, self)
        self.close_button = WindowControl('close', '#ff5f57', 'Close Tabla', window.close, self)
        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        for control in (self.minimize, self.maximize, self.close_button):
            controls_layout.addWidget(control)
        layout.addWidget(controls)
        self.maximize.setProperty('nativeHover', False)
        self.hover_watch = QTimer(self)
        self.hover_watch.setInterval(80)
        self.hover_watch.timeout.connect(self.check_native_hover)
        self.sync()
        polish_surfaces(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 800
        for control in self.menu_buttons:
            control.setVisible(not compact)
        self.overflow.setVisible(compact)

    def set_native_maximize_hover(self, hovered):
        hovered = bool(hovered)
        if bool(self.maximize.property('nativeHover')) == hovered:
            return
        self.maximize.setProperty('nativeHover', hovered)
        self.maximize.style().unpolish(self.maximize)
        self.maximize.style().polish(self.maximize)
        self.maximize.update()
        if hovered:
            self.hover_watch.start()
        else:
            self.maximize.setDown(False)
            self.hover_watch.stop()

    def check_native_hover(self):
        inside = self.maximize.rect().contains(self.maximize.mapFromGlobal(QCursor.pos()))
        if not self.owner.isVisible() or self.owner.isMinimized() or not inside:
            self.set_native_maximize_hover(False)

    def control(self, tip, glyph, callback):
        result = button('', callback, 'chromeButton', glyph)
        result.setToolTip(tip)
        result.setAccessibleName(tip)
        result.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        result.setFixedSize(32, 31)
        result.setProperty('chromeGlyph', glyph)
        return result

    def build_menus(self):
        w = self.owner
        file = self.menus['File']
        file.addAction('New note\tCtrl+N', w.new_note)
        file.addAction('New task\tCtrl+Shift+T', w.new_task)
        file.addAction('New project', w.new_project)
        file.addSeparator()
        file.addAction('Import files into a note…', w.import_note_files)
        file.addAction('Export workspace…', w.export_data)
        file.addAction('Import workspace backup…', w.import_data)
        file.addSeparator()
        file.addAction('Quit Tabla', w.close)
        edit = self.menus['Edit']
        self.edit_actions = []
        for title, method in (('Undo', 'undo'), ('Redo', 'redo'), ('Cut', 'cut'), ('Copy', 'copy'), ('Paste', 'paste'), ('Select all', 'selectAll')):
            action = edit.addAction(title, lambda checked=False, m=method: self.edit_command(m))
            self.edit_actions.append((action, method))
        edit.aboutToShow.connect(self.sync_edit)
        view = self.menus['View']
        for title, page in (('Home', 'Today'), ('Calendar', 'Calendar'), ('Board', 'My Tasks'), ('Notes', 'Notes'), ('Focus', 'Focus'), ('Trash', 'Trash')):
            view.addAction(title, lambda checked=False, p=page: w.navigate(p))
        view.addSeparator()
        filters = view.addAction('Show note filters')
        filters.setCheckable(True)
        filters.setChecked(bool(w.store.setting('show_note_filters', False)))
        filters.toggled.connect(w.set_note_filters_visible)
        collections = view.addMenu('Note collection')
        for title, state in (('All notes', 'Active'), ('Pinned', 'Pinned'), ('Archive', 'Archive'), ('Trash', 'Trash')):
            collections.addAction(title, lambda checked=False, s=state: w.show_note_collection(s))
        previews = view.addMenu('Note preview length')
        for title, lines in (('Short · 3 lines', 3), ('Standard · 6 lines', 6), ('Natural · 14 lines', 14)):
            previews.addAction(title, lambda checked=False, n=lines: w.set_note_preview_lines(n))
        view.addSeparator()
        view.addAction('Light appearance', lambda: w.set_appearance('Light'))
        view.addAction('Dark appearance', lambda: w.set_appearance('Dark'))
        layout = self.menus['Layout']
        layout.addAction('Toggle icon sidebar', w.toggle_sidebar)
        layout.addAction('Notes as cards', lambda: w.show_note_layout('Grid'))
        layout.addAction('Notes as a list', lambda: w.show_note_layout('List'))
        layout.addSeparator()
        for title in ('Month', 'Week', 'Day'):
            layout.addAction('Calendar · ' + title.lower(), lambda checked=False, mode=title: w.show_calendar_layout(mode))
        settings = self.menus['Settings']
        settings.addAction('Settings and backups', lambda: w.navigate('Settings'))
        settings.addAction('Focus timer preferences', w.timer_prefs)
        self.reduce_motion = settings.addAction('Reduce motion')
        self.reduce_motion.setCheckable(True)
        self.reduce_motion.setChecked(bool(w.store.setting('reduce_motion', False)))
        self.reduce_motion.toggled.connect(w.set_reduce_motion)
        help = self.menus['Help']
        help.addAction('Quick guide', w.show_help)
        help.addAction('Keyboard shortcuts', w.show_shortcuts)
        help.addAction('About Tabla', w.show_about)

    def sync_edit(self):
        self.edit_target = self.owner.focusWidget()
        for action, method in self.edit_actions:
            action.setEnabled(callable(getattr(self.edit_target, method, None)))

    def edit_command(self, method):
        target = getattr(self, 'edit_target', None)
        operation = getattr(target, method, None)
        if callable(operation):
            operation()

    def refresh_projects(self):
        menu = self.menus['File']
        # Projects live in the rail's folder menu, not duplicate header submenus.
        self.sync()

    def sync(self):
        w = self.owner
        self.search_action.setIcon(icon('search'))
        if w.page == 'Search' and not self.search.hasFocus():
            self.search.setText(w.search_query)
        for control in self.findChildren(QPushButton):
            glyph = control.property('chromeGlyph')
            if glyph:
                control.setIcon(icon(glyph))
        polish_surfaces(self)
        self.back.setEnabled(getattr(w, '_history_index', 0) > 0)
        self.forward.setEnabled(getattr(w, '_history_index', 0) < len(getattr(w, '_history', [])) - 1)
        if hasattr(self, 'maximize'):
            self.maximize.setIcon(icon('restore' if w.isMaximized() else 'maximize'))
            self.maximize.setToolTip('Restore window' if w.isMaximized() else 'Maximize')

    def toggle_maximize(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()
        self.sync()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and watched is getattr(self, 'search', None) and event.key() == Qt.Key.Key_Escape:
            self.search.clearFocus()
            return True
        if watched is self.drag_area:
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self.toggle_maximize()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if self.owner.windowHandle():
                    self.owner.windowHandle().startSystemMove()
                return True
        return False


class WindowEdges(QObject):
    """Keep native resize/snap behavior around a frameless Qt window."""
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return False
        w = self.owner
        if not isinstance(obj, QWidget) or obj.window() is not w or w.isMaximized():
            return False
        point = w.mapFromGlobal(event.globalPosition().toPoint())
        if hasattr(w, 'chrome'):
            for control in (w.chrome.minimize, w.chrome.maximize, w.chrome.close_button):
                if control.rect().contains(control.mapFrom(w, point)):
                    return False
        edges = Qt.Edge(0)
        if point.x() < 5:
            edges |= Qt.Edge.LeftEdge
        elif point.x() > w.width() - 6:
            edges |= Qt.Edge.RightEdge
        if point.y() < 5:
            edges |= Qt.Edge.TopEdge
        elif point.y() > w.height() - 6:
            edges |= Qt.Edge.BottomEdge
        if edges and event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if w.windowHandle():
                return w.windowHandle().startSystemResize(edges)
        return False
