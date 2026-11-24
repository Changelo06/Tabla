from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QLineEdit, QComboBox, QCheckBox, QDialog, QFileDialog, QMessageBox,
    QInputDialog, QApplication, QSystemTrayIcon, QMenu, QSizePolicy,
)
from .storage import LINK_RE
from .timer import FocusTimer
from .theme import icon, COLORS, application_icon
from .widgets import label, button, row, panel, scroll, clear, ClickCard, TimerRing
from .dialogs import ItemDialog, NoteDialog, TimerSettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, store, defer_render=False):
        super().__init__()
        self.store = store
        self.timer = FocusTimer(store)
        self.page = "Calendar"
        self.project_id = None
        self.selected_day = date.today()
        self.month = self.selected_day.replace(day=1)
        self.calendar_view = "Month"
        self.task_filter = "Open"
        self.task_layout = "List"
        self.notes_filter = "Active"
        self.notes_query = ""
        self.search_query = ""
        self.setWindowTitle("tabla · Your personal workspace")
        self.setWindowIcon(application_icon())
        self.resize(1500, 960)
        self.setMinimumSize(1040, 700)
        self.root = QWidget()
        self.root.setObjectName("appRoot")
        self.setCentralWidget(self.root)
        layout = QHBoxLayout(self.root)
        layout.setContentsMargins(12, 16, 16, 8)
        layout.setSpacing(16)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(224)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(8, 9, 12, 12)
        self.sidebar_layout.setSpacing(8)
        layout.addWidget(self.sidebar)
        self.workspace, self.content = panel("workspace", 28)
        self.content.setSpacing(17)
        layout.addWidget(self.workspace, 1)
        context_host = QWidget()
        self.context_layout = QVBoxLayout(context_host)
        self.context_layout.setContentsMargins(0, 0, 0, 0)
        self.context_layout.setSpacing(14)
        self.context = scroll(context_host)
        self.context.setFixedWidth(260)
        layout.addWidget(self.context)
        self.statusBar().setSizeGripEnabled(False)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("tabla")
        if QSystemTrayIcon.isSystemTrayAvailable():
            menu = QMenu()
            menu.addAction("Open tabla", self.restore_window)
            menu.addAction("Quit tabla", self.quit_from_tray)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.restore_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self.tray.show()
        self.pulse = QTimer(self)
        self.pulse.setInterval(250)
        self.pulse.timeout.connect(self.tick)
        if self.timer.data.get("running"):
            self.pulse.start()
        self._last_timer_running = None
        for sequence, callback in (("Ctrl+N", self.new_note), ("Ctrl+Shift+T", self.new_task),
                                   ("Ctrl+K", self.focus_search), ("Ctrl+1", lambda: self.navigate("Today")),
                                   ("Ctrl+2", lambda: self.navigate("Calendar"))):
            QShortcut(QKeySequence(sequence), self, activated=callback)
        if not defer_render:
            self.render_sidebar()
            self.render()
        self._layout_class = (self.width() >= 1360, self.height() < 850, self.width() >= 1550)
        self.resize_debounce = QTimer(self)
        self.resize_debounce.setSingleShot(True)
        self.resize_debounce.setInterval(60)
        self.resize_debounce.timeout.connect(self.render)

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_from_tray(self):
        self.restore_window()
        self.close()

    def closeEvent(self, event):
        if self.timer.data["running"]:
            msg = QMessageBox(self)
            msg.setWindowTitle("Your timer is running")
            msg.setText("Keep the timer running in the tray, or stop and quit?")
            keep = msg.addButton("Keep in tray", QMessageBox.ButtonRole.AcceptRole) if QSystemTrayIcon.isSystemTrayAvailable() else None
            stop = msg.addButton("Stop and quit", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if keep and msg.clickedButton() == keep:
                self.timer.persist()
                self.hide()
                event.ignore()
                return
            if msg.clickedButton() != stop:
                event.ignore()
                return
            self.timer.switch(self.timer.data["mode"])
        self.timer.persist()
        self.tray.hide()
        event.accept()

    def resizeEvent(self, event):
        if hasattr(self, "context"):
            self.context.setVisible(self.width() >= 1360 and self.page not in ("Settings", "Focus", "Notes"))
        if hasattr(self, "resize_debounce"):
            size_class = (self.width() >= 1360, self.height() < 850, self.width() >= 1550)
            if size_class != self._layout_class:
                self._layout_class = size_class
                self.resize_debounce.start()
        super().resizeEvent(event)

    def render_sidebar(self):
        old_query = self.search_query
        clear(self.sidebar_layout)
        mark = QLabel()
        mark.setPixmap(icon("brand", "#1878f8", 29).pixmap(QSize(29, 29)))
        mark.setFixedWidth(34)
        brand = label("tabla")
        brand.setStyleSheet("font-size:32px; font-weight:900; color:#242321; padding: 4px 9px 8px;")
        self.sidebar_layout.addLayout(row(mark, brand, None, spacing=0))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search   Ctrl+K")
        self.search.setAccessibleName("Search notes, tasks and projects")
        self.search.setText(old_query)
        self.search_timer = QTimer(self.search)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(220)
        self.search.textChanged.connect(lambda text: self.search_timer.start())
        self.search_timer.timeout.connect(self.search_changed)
        self.sidebar_layout.addWidget(self.search)
        self.sidebar_layout.addSpacing(12)
        self.nav_buttons = {}
        for title, glyph in (("Today", "home"), ("Calendar", "calendar"), ("My Tasks", "tasks"),
                             ("Notes", "note"), ("Focus", "clock")):
            btn = button(title, lambda checked=False, t=title: self.navigate(t), "nav", glyph)
            btn.setProperty("active", self.page == title)
            self.sidebar_layout.addWidget(btn)
            self.nav_buttons[title] = btn
        self.sidebar_layout.addSpacing(24)
        self.sidebar_layout.addLayout(row(label("Projects", "muted"), None, button("+", self.new_project, "text")))
        projects_area = QWidget()
        projects_layout = QVBoxLayout(projects_area)
        projects_layout.setContentsMargins(0, 0, 0, 0)
        projects_layout.setSpacing(3)
        for p in reversed(self.store.records("project")):
            tasks = [t for t in self.store.records("task", project=p["id"]) if t.get("status") != "Done"]
            btn = button(f'{p["title"][:21]}   {len(tasks)}', lambda checked=False, pid=p["id"]: self.open_project(pid), "nav", "folder")
            btn.setToolTip(p["title"])
            btn.setProperty("active", self.project_id == p["id"])
            projects_layout.addWidget(btn)
        if not self.store.records("project"):
            projects_layout.addWidget(button("Create a project", self.new_project, "text"))
        projects_layout.addStretch()
        self.sidebar_layout.addWidget(scroll(projects_area), 1)
        self.sidebar_layout.addWidget(button("Settings and backups", lambda: self.navigate("Settings"), "nav", "settings"))
        self.sidebar_layout.addWidget(label("  Saved on this device", "muted"))

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def search_changed(self):
        self.search_query = self.search.text()
        if self.search_query.strip():
            self.page = "Search"
            self.project_id = None
        else:
            self.page = "Calendar"
        self.render()

    def navigate(self, page):
        self.page, self.project_id, self.search_query = page, None, ""
        self.render_sidebar()
        self.render()

    def open_project(self, project_id):
        self.project_id = project_id
        self.page = "Calendar"
        self.render_sidebar()
        self.render()

    def scoped(self, kind, state="active", query=""):
        return self.store.records(kind, self.project_id, state, query)

    def render(self):
        clear(self.content)
        self.content.setSpacing(11 if self.height() < 850 else 17)
        project = self.store.get(self.project_id) if self.project_id else None
        title = project["title"] if project else {
            "Calendar": "Calendar", "My Tasks": "My tasks", "Today": "Today",
            "Notes": "Notes", "Focus": "Focus", "Settings": "Settings and backups",
            "Search": "Search",
        }.get(self.page, self.page)
        subtitle = {
            "Calendar": "Events, task deadlines and scheduled work.",
            "My Tasks": "",
            "Notes": "",
            "Focus": "Choose a task, set a timer, then take a break.",
            "Today": date.today().strftime("%A, %B %d, %Y"),
            "Settings": "",
            "Search": f'Results for “{self.search_query}”',
        }.get(self.page, "")
        if project:
            self.content.addWidget(label("Projects  /  " + project["title"], "muted"))
        heading = row(label(title, "title"), None)
        if self.page in ("Today", "My Tasks", "Search"):
            heading.addWidget(button("Quick note", self.new_note, glyph="note"))
            heading.addWidget(button("New task", self.new_task, "primary", "plus"))
        elif self.page == "Notes":
            heading.addWidget(button("New note", self.new_note, "primary", "plus"))
        self.content.addLayout(heading)
        if subtitle:
            self.content.addWidget(label(subtitle, "subtitle", True))
        if project:
            tabs, tabs_layout = panel("smallCard", 4)
            strip = QHBoxLayout()
            strip.setContentsMargins(0, 0, 0, 0)
            for name, route, glyph in (("Calendar", "Calendar", "calendar"), ("Tasks", "My Tasks", "tasks"),
                                       ("Notes", "Notes", "note"), ("Focus", "Focus", "clock")):
                btn = button(name, lambda checked=False, r=route: self.project_tab(r), "tab", glyph)
                btn.setProperty("active", self.page == route)
                strip.addWidget(btn)
            strip.addStretch()
            if project:
                strip.addWidget(button("Edit project", lambda: self.edit_item(project), "text"))
            tabs_layout.addLayout(strip)
            self.content.addWidget(tabs)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#e8e6e2;")
        self.content.addWidget(line)
        getattr(self, {"Calendar": "render_calendar", "My Tasks": "render_tasks", "Notes": "render_notes",
                        "Focus": "render_focus", "Today": "render_today", "Settings": "render_settings",
                        "Search": "render_search"}[self.page])()
        self.render_context()
        for name, btn in getattr(self, "nav_buttons", {}).items():
            btn.setProperty("active", name == self.page and not self.project_id)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def project_tab(self, route):
        self.page = route
        self.render()

    def refresh(self):
        self.render_sidebar()
        self.render()

    def new_task(self, checked=False, day=None):
        self.edit_item(None, "task", day)

    def new_project(self):
        self.edit_item(None, "project")

    def new_event(self, checked=False, day=None):
        self.edit_item(None, "event", day or self.selected_day.isoformat())

    def new_block(self, day=None):
        self.edit_item(None, "block", day or self.selected_day.isoformat())

    def new_note(self):
        self.edit_note()

    def edit_item(self, record=None, kind="task", day=None):
        kind = record["kind"] if record else kind
        if kind == "note":
            self.edit_note(record)
            return
        if kind == 'task':
            from .task_card import TaskCardDialog
            dialog = TaskCardDialog(self.store, record, day, self.project_id, self)
        else:
            dialog = ItemDialog(self.store, kind, record, day, self.project_id, self)
        if dialog.exec():
            if self.project_id and self.store.get(self.project_id).get("deleted"):
                self.project_id = None
            self.refresh()
            target = getattr(dialog, "pending_navigation", None)
            if target:
                QTimer.singleShot(0, lambda: self.open_record(target))
        dialog.deleteLater()

    def edit_note(self, record=None):
        dialog = NoteDialog(self.store, record, self.project_id, self)
        dialog.exec()
        target = dialog.pending_navigation
        dialog.deleteLater()
        if hasattr(self, 'sync_note_gallery'):
            self.sync_note_gallery()
        else:
            self.refresh()
        if target:
            QTimer.singleShot(0, lambda: self.open_record(target))

    def open_record(self, record_id):
        record = self.store.get(record_id)
        if not record or record.get("deleted"):
            QMessageBox.information(self, "Item unavailable", "This item is missing or in Trash. Open Trash in the sidebar to restore it.")
            return
        if record["kind"] == "project":
            self.open_project(record_id)
        elif record["kind"] in ("task", "event", "block", "note"):
            self.edit_item(record)

    def calendar_items(self, day):
        items = [r for kind in ("task", "event", "block") for r in self.scoped(kind)
                 if r.get("date") == day.isoformat()]
        return sorted(items, key=lambda r: (r.get("time", "23:59"), r["title"].casefold()))

    def move_calendar(self, delta):
        if self.calendar_view == "Month":
            absolute = self.month.year * 12 + self.month.month - 1 + delta
            self.month = date(absolute // 12, absolute % 12 + 1, 1)
        else:
            self.selected_day += timedelta(days=delta * (7 if self.calendar_view == "Week" else 1))
            self.month = self.selected_day.replace(day=1)
        self.render()

    def go_today(self):
        self.selected_day = date.today()
        self.month = self.selected_day.replace(day=1)
        self.render()

    def calendar_mode(self, mode):
        self.calendar_view = mode
        self.render()

    def render_calendar(self):
        mode = QComboBox()
        mode.addItems(["Month", "Week", "Day"])
        mode.setCurrentText(self.calendar_view)
        mode.currentTextChanged.connect(self.calendar_mode)
        heading = self.month.strftime("%B %Y") if self.calendar_view == "Month" else self.selected_day.strftime("%B %d, %Y")
        self.content.addLayout(row(button("", lambda: self.move_calendar(-1), "icon", "left"), label(heading, "section"),
                                   button("", lambda: self.move_calendar(1), "icon", "right"), None,
                                   button("Today", self.go_today), mode, button("Add event", self.new_event, "primary", "plus")))
        if self.calendar_view == "Day":
            body = QWidget()
            v = QVBoxLayout(body)
            v.setContentsMargins(0, 8, 0, 0)
            v.addLayout(row(label(self.selected_day.strftime("%A"), "section"), None,
                            button("Schedule a task", lambda: self.new_block(self.selected_day.isoformat()))))
            items = self.calendar_items(self.selected_day)
            for r in items:
                v.addWidget(self.agenda_item(r))
            if not items:
                v.addWidget(self.empty("Nothing scheduled", "Add an event or schedule a task for this day."))
            v.addStretch()
            self.content.addWidget(scroll(body), 1)
            return
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for col, weekday in enumerate(("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")):
            head = label(weekday[:3] if self.width() < 1350 else weekday, "muted")
            head.setContentsMargins(8, 4, 0, 7)
            grid.addWidget(head, 0, col)
            grid.setColumnStretch(col, 1)
        if self.calendar_view == "Month":
            weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.month.year, self.month.month)
        else:
            start = self.selected_day - timedelta(days=(self.selected_day.weekday() + 1) % 7)
            weeks = [[start + timedelta(days=i) for i in range(7)]]
        compact_month = self.height() < 850 and self.calendar_view == "Month"
        for row_index, days in enumerate(weeks, 1):
            grid.setRowStretch(row_index, 1)
            for col, day in enumerate(days):
                items = self.calendar_items(day)
                color = "gray"
                if items:
                    color = items[0].get("color", "blue" if items[0]["kind"] == "task" else "green")
                cell = ClickCard(color)
                cell.setMinimumHeight(60 if compact_month else (75 if len(weeks) == 6 else 90))
                cell.setMinimumWidth(70)
                cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                cell.setAccessibleName(day.strftime("%A, %B %d") + f", {len(items)} items")
                cell.clicked.connect(lambda d=day: self.day_dialog(d))
                v = QVBoxLayout(cell)
                v.setContentsMargins(7, 5 if compact_month else 8, 6, 5 if compact_month else 7)
                v.setSpacing(2 if compact_month else 3)
                number = label(str(day.day))
                number.setFixedSize(22 if compact_month else 27, 22 if compact_month else 27)
                number.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if day == date.today():
                    number.setStyleSheet("background:#1878f8; color:white; border-radius:13px; font-weight:600;")
                elif day.month != self.month.month and self.calendar_view == "Month":
                    number.setStyleSheet("color:#a2adbc;")
                v.addWidget(number)
                v.addStretch()
                limit = (1 if len(weeks) == 6 or compact_month else 2) if self.calendar_view == "Month" else 10
                for item_number, r in enumerate(items[:limit]):
                    mark = "[done] " if r.get("status") == "Done" else ""
                    if r["kind"] == "block":
                        mark = "> "
                    elif r["kind"] == "task":
                        mark += "• "
                    item = button(mark + r["title"], lambda checked=False, rid=r["id"]: self.open_record(rid), elide=True)
                    item.setToolTip(("Deadline: " if r["kind"] == "task" else "Scheduled work: " if r["kind"] == "block" else "Event: ") + r["title"])
                    item.setStyleSheet("QPushButton {background:transparent;border:none;border-left:2px solid " + COLORS.get(r.get("color", "blue"), COLORS["blue"])[1] + ";border-radius:0;text-align:left;padding:1px 3px;min-height:17px;font-size:14px;} QPushButton:hover {color:#006bc7;}")
                    item.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                    v.addWidget(item)
                if len(items) > limit:
                    v.addWidget(label(f"+{len(items) - limit} more", "muted"))
                grid.addWidget(cell, row_index, col)
        self.content.addWidget(scroll(grid_host), 1)
        self.content.addWidget(label("Select a day to add an event, task or work block.", "muted"))

    def day_dialog(self, day):
        self.selected_day = day
        dialog = QDialog(self)
        dialog.setWindowTitle(day.strftime("%A, %B %d"))
        dialog.resize(540, 450)
        v = QVBoxLayout(dialog)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)
        v.addWidget(label(day.strftime("%A, %B %d"), "section"))
        area_host = QWidget()
        area = QVBoxLayout(area_host)
        area.setContentsMargins(0, 0, 0, 0)
        for r in self.calendar_items(day):
            item = button((r.get("time", "Due") or "Due") + "   " + r["title"], lambda checked=False, rid=r["id"]: (dialog.accept(), self.open_record(rid)))
            area.addWidget(item)
        if not self.calendar_items(day):
            area.addWidget(label("Nothing scheduled for this day.", "muted", True))
        area.addStretch()
        v.addWidget(scroll(area_host), 1)
        v.addLayout(row(button("Task", lambda: (dialog.accept(), self.new_task(day=day.isoformat()))),
                        button("Work block", lambda: (dialog.accept(), self.new_block(day.isoformat()))),
                        button("Event", lambda: (dialog.accept(), self.new_event(day=day.isoformat())), "primary")))
        dialog.exec()

    def task_changed(self, task_id, checked):
        self.store.toggle_task(task_id, checked)
        self.refresh()

    def task_card(self, task, compact=False):
        card, v = panel("smallCard", 12 if compact else 15)
        h = QHBoxLayout()
        check = QCheckBox()
        check.setAccessibleName("Complete " + task["title"])
        check.setChecked(task.get("status") == "Done")
        check.toggled.connect(lambda value, rid=task["id"]: self.task_changed(rid, value))
        h.addWidget(check)
        title = button(task["title"], lambda: self.open_record(task["id"]), "text")
        title.setStyleSheet("border:none; background:transparent; color:" + ("#69645f;text-decoration:line-through;" if task.get("status") == "Done" else "#242321;") + "text-align:left;padding:0;")
        title.setToolTip(task["title"])
        h.addWidget(title, 1)
        if not compact:
            h.addWidget(button("Focus", lambda: self.focus_task(task["id"]), "text", "clock"))
        v.addLayout(h)
        project = self.store.get(task.get("project"))
        parts = [task.get("date") or "No deadline", task.get("priority", "Medium") + " priority"]
        if project:
            parts.append(project["title"])
        if not compact:
            parts.append(task.get("status", "To do"))
        v.addWidget(label("  ·  ".join(parts), "muted", True))
        return card

    def render_tasks(self):
        state = QComboBox()
        state.addItems(["Open", "All", "Completed", "Overdue"])
        state.setCurrentText(self.task_filter)
        state.currentTextChanged.connect(lambda value: self.set_task_filter(value))
        self.content.addLayout(row(state, None,
            button("List", lambda: self.set_task_layout("List"), glyph="tasks"),
            button("Board", lambda: self.set_task_layout("Board"), glyph="board")))
        tasks = self.scoped("task")
        if self.task_filter == "Open":
            tasks = [t for t in tasks if t.get("status") != "Done"]
        elif self.task_filter == "Completed":
            tasks = [t for t in tasks if t.get("status") == "Done"]
        elif self.task_filter == "Overdue":
            tasks = [t for t in tasks if t.get("status") != "Done" and t.get("date") and t["date"] < date.today().isoformat()]
        tasks.sort(key=lambda t: (t.get("status") == "Done", t.get("date") or "9999", {"High": 0, "Medium": 1, "Low": 2}.get(t.get("priority"), 1)))
        host = QWidget()
        if self.task_layout == "Board":
            columns = QHBoxLayout(host)
            columns.setContentsMargins(0, 0, 0, 0)
            for status in ("To do", "In progress", "Done"):
                column, v = panel("smallCard", 12)
                matching = [t for t in tasks if t.get("status", "To do") == status]
                v.addWidget(label(f"{status}   {len(matching)}", "section"))
                for task in matching:
                    v.addWidget(self.task_card(task, True))
                v.addStretch()
                columns.addWidget(column, 1)
        else:
            v = QVBoxLayout(host)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(9)
            if not tasks:
                v.addWidget(self.empty("No tasks here", "Use New task to add one, or choose another filter."))
            for task in tasks:
                v.addWidget(self.task_card(task))
            v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def set_task_filter(self, value):
        self.task_filter = value
        self.render()

    def set_task_layout(self, value):
        self.task_layout = value
        self.render()

    def note_card(self, note, compact=False):
        card = ClickCard(note.get("color", "yellow"))
        card.clicked.connect(lambda: self.edit_note(note))
        v = QVBoxLayout(card)
        v.setContentsMargins(15, 13, 15, 13)
        v.setSpacing(9)
        title = label(note["title"], wrap=True)
        title.setStyleSheet("font-weight:900; font-size:21px;")
        v.addWidget(title)
        text = LINK_RE.sub(lambda m: (self.store.resolve(m.group(1), note["id"]) or {}).get("title", m.group(1)), note.get("body", ""))
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = text.replace("- [x]", "[done]")
        if compact:
            text = "\n".join(line for line in text.splitlines() if line.strip()).strip()
            text = "\n".join(text.splitlines()[:3])
        text = text[:120 if compact else 260]
        v.addWidget(label(text or "Empty note", "reading", True))
        if note.get("labels") and not compact:
            v.addWidget(label(note["labels"], "muted", True))
        if not compact:
            v.addStretch()
            refs = len(self.store.backlinks(note["id"]))
            if refs:
                v.addWidget(label(f'{refs} incoming link' + ("s" if refs != 1 else ""), "muted"))
            card.setMinimumHeight(190)
        else:
            card.setMinimumHeight(110)
        return card

    def render_notes(self):
        query = QLineEdit(self.notes_query)
        query.setPlaceholderText("Filter notes by text or label...")
        query.setAccessibleName("Filter notes")
        query.returnPressed.connect(lambda: self.filter_notes(query.text()))
        filter_combo = QComboBox()
        filter_combo.addItems(["Active", "Pinned", "Archive"])
        filter_combo.setCurrentText(self.notes_filter)
        filter_combo.currentTextChanged.connect(self.set_notes_filter)
        self.content.addLayout(row(query, button("Find", lambda: self.filter_notes(query.text()), glyph="search"), filter_combo))
        notes = self.scoped("note", "archive" if self.notes_filter == "Archive" else "active", self.notes_query)
        if self.notes_filter == "Pinned":
            notes = [n for n in notes if n.get("pinned")]
        notes.sort(key=lambda n: not n.get("pinned", False))
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        if not notes:
            grid.addWidget(self.empty("No notes here", "Use New note to write a note or checklist."), 0, 0, 1, 3)
        columns = 2 if self.width() < 1250 else 3
        for i, note in enumerate(notes):
            grid.addWidget(self.note_card(note), i // columns, i % columns)
        for col in range(columns):
            grid.setColumnStretch(col, 1)
        grid.setRowStretch((len(notes) + columns - 1) // columns + 1, 1)
        self.content.addWidget(scroll(host), 1)

    def filter_notes(self, query):
        self.notes_query = query
        self.render()

    def set_notes_filter(self, state):
        self.notes_filter = state
        self.render()

    def focus_task(self, task_id):
        if self.timer.data["task"] != task_id and self.timer.data["running"]:
            QMessageBox.information(self, "Pause first", "Pause the current session before choosing another task.")
            return
        if self.timer.data["task"] != task_id:
            self.timer.switch("Focus")
        self.timer.data["task"] = task_id
        self.timer.persist()
        self.page = "Focus"
        self.refresh()

    def toggle_timer(self):
        if self.timer.data["running"]:
            self.timer.pause()
            self.pulse.stop()
        else:
            self.timer.start()
            if not self.pulse.isActive():
                self.pulse.start()
        self.tick()

    def timer_mode(self, mode):
        if self.timer.data["running"]:
            if QMessageBox.question(self, "Change timer", "End this session and switch timer mode? Time already spent will stay in history.") != QMessageBox.StandardButton.Yes:
                return
        self.timer.switch(mode)
        self.pulse.stop()
        self.render()

    def timer_prefs(self):
        dialog = TimerSettingsDialog(self.store, self)
        dialog.exec()
        self.render()

    def render_focus(self):
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)
        v.addLayout(row(button("Focus", lambda: self.timer_mode("Focus")),
                        button("Short break", lambda: self.timer_mode("Short break")),
                        button("Long break", lambda: self.timer_mode("Long break")), None,
                        button("Preferences", self.timer_prefs, glyph="settings")))
        v.addWidget(TimerRing(self.timer))
        task = QComboBox()
        task.addItem("Open focus · no task", None)
        for t in self.scoped("task"):
            if t.get("status") != "Done":
                task.addItem(t["title"], t["id"])
        task.setCurrentIndex(max(0, task.findData(self.timer.data.get("task"))))
        task.setEnabled(not self.timer.data["running"])
        task.setObjectName("focusTaskPicker")
        task.currentIndexChanged.connect(lambda i: self.choose_focus_task(task.currentData()))
        v.addWidget(task)
        toggle = button("Pause" if self.timer.data["running"] else "Start", self.toggle_timer, "primary", "pause" if self.timer.data["running"] else "play")
        toggle.setProperty("timerToggle", True)
        v.addLayout(row(None, toggle, button("Reset session", lambda: self.timer_mode(self.timer.data["mode"])), None))
        v.addWidget(label("Your timer is saved when you close Tabla. Tasks stay open until you check them off.", "muted", True))
        v.addWidget(label("Recent focus", "section"))
        sessions = self.store.records("session")[:12]
        if not sessions:
            v.addWidget(label("Completed and interrupted sessions will appear here.", "muted", True))
        for s in sessions:
            card, layout = panel("smallCard", 12)
            layout.addLayout(row(label(s["title"]), None, label(f'{s.get("seconds", 0) // 60}m {s.get("seconds", 0) % 60}s', "muted")))
            layout.addWidget(label(s.get("date", "") + (" · Completed" if s.get("completed") else " · Interrupted"), "muted"))
            v.addWidget(card)
        v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def choose_focus_task(self, task_id):
        if self.timer.data.get("task") != task_id:
            self.timer.switch(self.timer.data["mode"])
            self.timer.data["task"] = task_id
            self.timer.persist()
            self.render_context()

    def tick(self):
        from .tokens import current_tokens
        completed = self.timer.finish_if_due()
        if completed:
            from . import foley
            self.pulse.stop()
            if foley.enabled():
                foley.play("brass")
            else:
                QApplication.beep()
            if self.tray.isVisible():
                self.tray.showMessage("tabla · " + completed + " complete", "Ready for " + self.timer.data["mode"].lower() + ". Start when you're ready.")
            self.statusBar().showMessage(completed + " complete. Your next timer is ready.", 15000)
            self.render()
        running = bool(self.timer.data["running"])
        if not running and self.pulse.isActive():
            self.pulse.stop()
        for ring in self.findChildren(TimerRing):
            ring.update()
        if self._last_timer_running != running:
            self._last_timer_running = running
            t = current_tokens()
            from PySide6.QtWidgets import QPushButton
            for btn in self.findChildren(QPushButton):
                if btn.property("timerToggle"):
                    btn.setText("Pause" if running else "Start")
                    btn.setIcon(icon("pause" if running else "play", t.ink_inverse, preserve_color=True))
            for picker in self.findChildren(QComboBox):
                if picker.objectName() == "focusTaskPicker":
                    picker.setEnabled(not running)

    def agenda_item(self, item):
        card, v = panel("agendaRow", 8)
        when = item.get("time") or "Deadline"
        kind = {"task": "Task deadline", "event": "Event", "block": "Scheduled work"}.get(item["kind"], "")
        v.addLayout(row(label(when, "muted"), button(item["title"], lambda: self.open_record(item["id"]), "text"), None, label(kind, "muted")))
        return card

    def render_today(self):
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(13)
        v.addWidget(label("Today's plan", "section"))
        items = self.calendar_items(date.today())
        for r in items:
            v.addWidget(self.agenda_item(r))
        if not items:
            v.addWidget(self.empty("Nothing scheduled today", "Add a date to a task or plan an event in Calendar.", lambda: self.navigate("Calendar"), "Open calendar"))
        overdue = [t for t in self.scoped("task") if t.get("date") and t["date"] < date.today().isoformat() and t.get("status") != "Done"]
        if overdue:
            v.addWidget(label("Overdue", "section"))
            for t in overdue[:5]:
                v.addWidget(self.task_card(t))
        upcoming = [t for t in self.scoped("task") if t.get("status") != "Done" and (not t.get("date") or t["date"] > date.today().isoformat())]
        if upcoming:
            v.addWidget(label("Next tasks", "section"))
            for t in sorted(upcoming, key=lambda t: t.get("date") or "9999")[:4]:
                v.addWidget(self.task_card(t))
        pinned = [n for n in self.scoped("note") if n.get("pinned")][:3]
        if pinned:
            v.addWidget(label("Pinned notes", "section"))
        for n in pinned:
            v.addWidget(self.note_card(n, True))
        v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def render_context(self):
        clear(self.context_layout)
        focus, v = panel(padding=18)
        v.setSpacing(8)
        v.addLayout(row(label("Focus timer", "section"), None, button("", lambda: self.project_tab("Focus"), "icon", "clock")))
        v.addWidget(TimerRing(self.timer, True))
        task = self.store.get(self.timer.data.get("task"))
        title = label(task["title"] if task else "No task selected", "muted", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        toggle = button("Pause" if self.timer.data["running"] else "Start", self.toggle_timer, "primary", "pause" if self.timer.data["running"] else "play")
        toggle.setProperty("timerToggle", True)
        v.addLayout(row(None, toggle, None))
        v.addWidget(button("Choose task or timer", lambda: self.project_tab("Focus"), "text"))
        self.context_layout.addWidget(focus)
        tasks, v = panel(padding=18)
        v.setSpacing(8)
        v.addLayout(row(label("My tasks", "section"), None, button("", self.new_task, "icon", "plus")))
        open_tasks = [t for t in self.scoped("task") if t.get("status") != "Done"]
        open_tasks.sort(key=lambda t: (t.get("date") or "9999", t["title"]))
        for t in open_tasks[:3]:
            check = QCheckBox(t["title"][:29])
            check.setToolTip(t["title"])
            check.toggled.connect(lambda value, rid=t["id"]: self.task_changed(rid, value))
            v.addWidget(check)
            v.addWidget(label("      " + (t.get("date") or "No deadline"), "muted"))
        if open_tasks and self.page not in ("Today", "My Tasks"):
            self.context_layout.addWidget(tasks)
        else:
            tasks.deleteLater()
        notes, v = panel(padding=18)
        v.setSpacing(10)
        v.addWidget(label("Pinned notes", "section"))
        pinned = [n for n in self.scoped("note") if n.get("pinned")]
        for n in pinned[:2]:
            v.addWidget(self.note_card(n, True))
        v.addWidget(button("View all notes  →", lambda: self.project_tab("Notes"), "text"))
        if pinned and self.page != "Today":
            self.context_layout.addWidget(notes)
        else:
            notes.deleteLater()
        self.context_layout.addStretch()
        self.context.setVisible(self.width() >= 1360 and self.page not in ("Settings", "Focus", "Notes"))

    def empty(self, title, description, action=None, action_title="Create"):
        card, v = panel("smallCard", 20)
        v.addWidget(label(title, "section"))
        v.addWidget(label(description, "muted", True))
        if action:
            v.addLayout(row(button(action_title, action, glyph="right"), None))
        return card

    def render_search(self):
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        results = self.store.records(query=self.search_query, state="all")
        results = [r for r in results if r["kind"] in ("note", "task", "project", "event", "block")]
        v.addWidget(label(f"{len(results)} matching items", "muted"))
        for r in results[:150]:
            card, cv = panel("smallCard", 13)
            cv.addLayout(row(button(r["title"], lambda checked=False, rid=r["id"]: self.open_record(rid), "text"), None,
                             label(r["kind"] + (" · Archived" if r.get("archived") else ""), "muted")))
            cv.addWidget(label(r.get("body", "").replace("\n", " ")[:140], "muted", True))
            v.addWidget(card)
        if not results:
            v.addWidget(label("Nothing found. Try a word from a title, note, task, or label.", "muted", True))
        v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def render_settings(self):
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(18)
        card, cv = panel("smallCard", 20)
        cv.addWidget(label("Your local workspace", "section"))
        cv.addWidget(label("Your tasks and notes are stored on this device and are available offline.", "muted", True))
        path = label(str(self.store.path), "muted", True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cv.addWidget(path)
        cv.addLayout(row(button("Open data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.path.parent))), glyph="folder"),
                          button("Focus preferences", self.timer_prefs, glyph="clock"), None))
        v.addWidget(card)
        card, cv = panel("smallCard", 20)
        cv.addWidget(label("Backups & portability", "section"))
        cv.addWidget(label("Export a backup of your workspace. Importing keeps different versions as copies and saves a snapshot first.", "muted", True))
        cv.addLayout(row(button("Export workspace", self.export_data, "primary", "export"),
                          button("Import backup", self.import_data, glyph="import"), button("Export notes (.md)", self.export_markdown), None))
        v.addWidget(card)
        card, cv = panel("smallCard", 20)
        cv.addWidget(label("Archive & trash", "section"))
        cv.addLayout(row(button("Open archive", lambda: self.recovery_dialog("archive"), glyph="archive"),
                          button("Open trash", lambda: self.recovery_dialog("trash"), glyph="trash"), None))
        cv.addWidget(label("Nothing is permanently deleted in this version. Restoring an item keeps its ID and incoming links.", "muted", True))
        v.addWidget(card)
        card, cv = panel("smallCard", 20)
        cv.addWidget(label("Make a start", "section"))
        cv.addWidget(label("Optional example content helps you explore tasks, notes, project links, and the calendar. It is added only when you choose it.", "muted", True))
        cv.addLayout(row(button("Add sample workspace", self.add_demo), None))
        v.addWidget(card)
        v.addWidget(label("Keyboard: Ctrl+K search · Ctrl+N note · Ctrl+Shift+T task · Ctrl+1 Today · Ctrl+2 Calendar", "muted", True))
        v.addStretch()
        self.content.addWidget(scroll(host), 1)

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export workspace", f"tabla-backup-{date.today()}.json", "Tabla backup (*.json)")
        if not path:
            return
        try:
            self.store.export_file(path)
            QMessageBox.information(self, "Backup saved", "Your workspace was exported successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import a Tabla backup", "", "Tabla backup (*.json)")
        if not path:
            return
        try:
            count, copies = self.store.import_file(path)
            self.refresh()
            QMessageBox.information(self, "Import complete", f"Added {count} items, including {copies} preserved alternate versions. Existing items were kept.")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", "Your existing workspace was preserved.\n\n" + str(exc))

    def export_markdown(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for Markdown notes")
        if not folder:
            return
        try:
            destination = Path(folder) / ("Tabla-notes-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            destination.mkdir()
            notes = self.store.records("note", state="all")
            for n in notes:
                title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", n["title"]).strip(" .")[:80] or "Note"
                body = LINK_RE.sub(lambda m: "[[" + (self.store.resolve(m.group(1), n["id"]) or {}).get("title", m.group(1)) + "]]", n.get("body", ""))
                (destination / (title + "-" + n["id"][:8] + ".md")).write_text("# " + n["title"] + "\n\n" + body, encoding="utf-8")
            QMessageBox.information(self, "Notes exported", f"Saved {len(notes)} notes in {destination}")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def recovery_dialog(self, state):
        dialog = QDialog(self)
        dialog.setWindowTitle("Trash" if state == "trash" else "Archive")
        dialog.resize(570, 470)
        v = QVBoxLayout(dialog)
        host = QWidget()
        items = QVBoxLayout(host)
        items.setContentsMargins(12, 12, 12, 12)
        for r in self.store.records(state=state):
            def restore(checked=False, record=r):
                record["deleted"] = False
                record["archived"] = False
                self.store.save(record)
                dialog.accept()
                self.refresh()
            items.addLayout(row(label(r["title"], wrap=True), None, label(r["kind"], "muted"), button("Restore", restore)))
        if not self.store.records(state=state):
            items.addWidget(label("Nothing here. Your workspace is clear.", "muted"))
        items.addStretch()
        v.addWidget(scroll(host))
        v.addWidget(button("Done", dialog.accept))
        dialog.exec()

    def add_demo(self):
        if QMessageBox.question(self, "Add sample workspace", "Add clearly named example projects, tasks, and notes? You can move any of them to Trash later.") == QMessageBox.StandardButton.Yes:
            self.store.seed_demo()
            self.refresh()
