"""Contextual, scrollable board navigation beside the application icon rail."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QMenu
from .widgets import label, button, row
from .theme import polish_surfaces


class BoardSidebar(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setObjectName('boardSidebar')
        self.setFixedWidth(236)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 12, 16)
        layout.setSpacing(10)
        collapse = button('Hide', owner.toggle_boards_sidebar, 'text')
        collapse.setMinimumSize(58, 32)
        collapse.setStyleSheet('QPushButton {min-width:58px;min-height:32px;padding:4px 8px;text-align:center;border-radius:8px;}')
        collapse.setToolTip('Hide boards sidebar')
        collapse.setAccessibleName('Hide boards sidebar')
        layout.addLayout(row(label('Boards', 'section'), None, collapse))
        layout.addWidget(button('New board', owner.new_board, 'text', 'plus'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a board')
        self.search.setAccessibleName('Filter boards')
        layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setAccessibleName('Boards grouped by project')
        layout.addWidget(self.tree, 1)
        layout.addWidget(button('Archived boards', owner.archived_boards, 'text', 'archive'))
        self.tree.currentItemChanged.connect(self.choose)
        self.search.textChanged.connect(self.filter)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context)
        self.signature = None

    def refresh(self):
        from .tokens import current_tokens
        t = current_tokens()
        self.setProperty('tablaThemed', True)
        self.setStyleSheet(f'QWidget#boardSidebar {{background:{t.bg_surface};border-right:1px solid {t.border_subtle};}}')
        self.tree.setProperty('tablaThemed', True)
        self.tree.setStyleSheet(
            f'QTreeWidget {{border:none;background:transparent;outline:0;show-decoration-selected:0;}}'
            f'QTreeWidget::item {{padding:7px 8px;border-radius:8px;color:{t.ink_secondary};}}'
            f'QTreeWidget::item:hover {{background:{t.bg_surface_hover};color:{t.ink_primary};}}'
            f'QTreeWidget::item:selected {{background:{t.bg_surface_active};color:{t.ink_primary};font-weight:600;}}'
            f'QTreeWidget::branch {{background:transparent;}}'
            f'QTreeWidget::branch:selected {{background:transparent;}}'
        )
        boards = self.owner.board_catalog.boards()
        signature = [(b['id'], b['title'], b.get('project'),
                      (self.owner.store.get(b.get('project')) or {}).get('title')) for b in boards]
        self.tree.blockSignals(True)
        if signature != self.signature:
            expanded = {self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole): self.tree.topLevelItem(i).isExpanded() for i in range(self.tree.topLevelItemCount())}
            self.tree.clear()
            groups = {}
            for board in boards:
                project = board.get('project')
                if project not in groups:
                    owner = self.owner.store.get(project) if project else None
                    name = owner['title'] if owner else 'Personal'
                    group = QTreeWidgetItem([name])
                    group.setData(0, Qt.ItemDataRole.UserRole, project or 'personal')
                    group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    self.tree.addTopLevelItem(group)
                    group.setExpanded(expanded.get(project or 'personal', True))
                    groups[project] = group
                item = QTreeWidgetItem([board['title']])
                item.setData(0, Qt.ItemDataRole.UserRole, board['id'])
                item.setToolTip(0, board['title'])
                groups[project].addChild(item)
            self.signature = signature
        for group_index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(group_index)
            for child_index in range(group.childCount()):
                item = group.child(child_index)
                if item.data(0, Qt.ItemDataRole.UserRole) == self.owner.board_id:
                    self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)
        self.filter(self.search.text())
        polish_surfaces(self)

    def choose(self, item, previous):
        if item and item.parent():
            self.owner.select_board(item.data(0, Qt.ItemDataRole.UserRole))

    def filter(self, text):
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            visible = False
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                match = text.casefold() in child.text(0).casefold() or text.casefold() in group.text(0).casefold()
                child.setHidden(not match)
                visible |= match
            group.setHidden(not visible)
            if text:
                group.setExpanded(True)

    def context(self, point):
        item = self.tree.itemAt(point)
        if not item or not item.parent():
            return
        board_id = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction('Rename or move', lambda: self.owner.edit_board(board_id))
        menu.addAction('Archive', lambda: self.owner.archive_board(board_id))
        polish_surfaces(menu)
        menu.exec(self.tree.viewport().mapToGlobal(point))
