"""Theme-owned calendar and searchable choice surfaces, without native popup chrome."""
from PySide6.QtCore import Qt, QDate, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QTextCharFormat, QPalette
from PySide6.QtWidgets import (QCalendarWidget, QDateEdit, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QMenu, QWidgetAction, QLineEdit, QListWidget, QListWidgetItem)
from .widgets import button
from .theme import themed_color, polish_surfaces


class CalendarPicker(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setNavigationBarVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setGridVisible(False)
        self.setMinimumSize(310, 280)
        self.layout().setContentsMargins(6, 6, 6, 6)
        self.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)
        header = QWidget(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(8, 8, 8, 4)
        row.addWidget(button('', self.showPreviousMonth, 'text', 'left'))
        self.month_title = QLabel()
        self.month_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.month_title, 1)
        row.addWidget(button('', self.showNextMonth, 'text', 'right'))
        self.layout().insertWidget(0, header)
        footer = QWidget(self)
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(12, 4, 12, 8)
        bottom.addStretch()
        bottom.addWidget(button('Today', self.choose_today, 'text'))
        self.layout().addWidget(footer)
        self.currentPageChanged.connect(self.update_month)
        self.update_month(self.yearShown(), self.monthShown())

    def update_month(self, year, month):
        self.month_title.setText(QDate(year, month, 1).toString('MMMM yyyy'))

    def showEvent(self, event):
        fg, bg = themed_color('#37352f'), themed_color('#ffffff')
        self.setStyleSheet(f'QCalendarWidget {{background:{bg};border:1px solid {themed_color("#dadce0")};border-radius:8px;}} '
            f'QCalendarWidget QWidget {{background:{bg};color:{fg};}} '
            f'QCalendarWidget QAbstractItemView {{background:{bg};color:{fg};border:none;outline:0;selection-background-color:#2383e2;selection-color:white;}} '
            'QCalendarWidget QHeaderView::section {background:transparent;border:none;padding:5px;font-size:11px;}')
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(fg))
        palette = self.palette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.AlternateBase, QPalette.ColorRole.Button):
            palette.setColor(role, QColor(bg))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            palette.setColor(role, QColor(fg))
        for child in [self, *self.findChildren(QWidget)]:
            child.setPalette(palette)
            child.setAutoFillBackground(True)
        for day in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday, Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
            self.setWeekdayTextFormat(day, fmt)
        super().showEvent(event)

    def choose_today(self):
        today = QDate.currentDate()
        self.setSelectedDate(today)
        self.clicked.emit(today)
        self.activated.emit(today)

    def paintCell(self, painter, rect, day):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor(themed_color('#ffffff')))
        target = QRectF(rect).adjusted(3, 2, -3, -2)
        selected = day == self.selectedDate()
        painter.setBrush(QColor('#2383e2') if selected else Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#2383e2'), 1) if day == QDate.currentDate() else Qt.PenStyle.NoPen)
        if selected or day == QDate.currentDate():
            painter.drawRoundedRect(target, 6, 6)
        enabled = self.minimumDate() <= day <= self.maximumDate()
        painter.setPen(QColor('white' if selected else themed_color('#37352f') if enabled and day.month() == self.monthShown() else themed_color('#8b8b85')))
        painter.setFont(QFont('Inter', 10))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(day.day()))
        painter.restore()


class DateField(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setCalendarWidget(CalendarPicker(self))


class ChoiceMenu(QMenu):
    chosen = Signal(object)

    def __init__(self, choices, current=None, parent=None, title='Choose an item'):
        super().__init__(parent)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName('fieldLabel')
        layout.addWidget(heading)
        search = QLineEdit()
        search.setPlaceholderText('Search…')
        search.setAccessibleName('Search choices')
        layout.addWidget(search)
        self.list = QListWidget()
        self.list.setMinimumWidth(290)
        self.list.setMaximumHeight(280)
        self.list.setStyleSheet('QListWidget {border:none;background:transparent;outline:0;} QListWidget::item {padding:10px 9px;border-radius:5px;} QListWidget::item:selected {background:#293e51;color:white;}')
        for text, value in choices:
            item = QListWidgetItem(('✓  ' if value == current else '    ') + text)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setToolTip(text)
            self.list.addItem(item)
        self.list.setFixedHeight(min(280, max(44, len(choices) * 40)))
        layout.addWidget(self.list)
        empty = QLabel('No matches')
        empty.setObjectName('fieldLabel')
        empty.hide()
        layout.addWidget(empty)
        def filter_items(text):
            for index in range(self.list.count()):
                item = self.list.item(index)
                item.setHidden(text.casefold() not in item.text().casefold())
            count = sum(not self.list.item(i).isHidden() for i in range(self.list.count()))
            empty.setVisible(not count)
            self.list.setFixedHeight(min(280, max(44, count * 40)))
            panel.adjustSize()
            self.setFixedHeight(panel.sizeHint().height() + 12)
        search.textChanged.connect(filter_items)
        self.list.itemClicked.connect(self.select)
        self.list.itemActivated.connect(self.select)
        def accept_search():
            item = next((self.list.item(i) for i in range(self.list.count()) if not self.list.item(i).isHidden()), None)
            if item:
                self.select(item)
        search.returnPressed.connect(accept_search)
        action = QWidgetAction(self)
        action.setDefaultWidget(panel)
        self.addAction(action)
        polish_surfaces(self)
        self.aboutToShow.connect(search.setFocus)

    def select(self, item):
        self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
        self.close()
