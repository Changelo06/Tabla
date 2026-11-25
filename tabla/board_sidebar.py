"""Contextual, scrollable board navigation beside the application icon rail."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QMenu
from .widgets import label, button, row
from .theme import polish_surfaces, icon


class BoardSidebar(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setObjectName('boardSidebar')
        self.setFixedWidth(236)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(10)

        self.header_title = label('Boards', 'section')
        self.header_title.setProperty('tablaThemed', True)
        self.collapse = button('', owner.toggle_boards_sidebar, 'text', 'left')
        self.collapse.setFixedSize(28, 28)
        self.collapse.setToolTip('Hide boards sidebar')
        self.collapse.setAccessibleName('Hide boards sidebar')
        layout.addLayout(row(self.header_title, None, self.collapse, spacing=4))

        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a board…')
        self.search.setAccessibleName('Filter boards')
        self.search.setFixedHeight(31)
        self.search.setClearButtonEnabled(True)
        self.search_icon = self.search.addAction(icon('search', size=15), QLineEdit.ActionPosition.LeadingPosition)
        layout.addWidget(self.search)

        self.top_sep = QFrame()
        self.top_sep.setFixedHeight(1)
        self.top_sep.setProperty('tablaThemed', True)
        layout.addWidget(self.top_sep)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(0)
        self.tree.setIconSize(QSize(15, 15))
        self.tree.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setAccessibleName('Boards grouped by project')
        layout.addWidget(self.tree, 1)

        self.bottom_sep = QFrame()
        self.bottom_sep.setFixedHeight(1)
        self.bottom_sep.setProperty('tablaThemed', True)
        layout.addWidget(self.bottom_sep)

        self.new_board_btn = button('New board', owner.new_board, 'text', 'plus')
        self.new_board_btn.setProperty('tablaThemed', True)
        self.new_board_btn.setFixedHeight(32)
        layout.addWidget(self.new_board_btn)

        self.archived_btn = button('Archived boards', owner.archived_boards, 'text', 'archive')
        self.archived_btn.setProperty('tablaThemed', True)
        self.archived_btn.setFixedHeight(30)
        layout.addWidget(self.archived_btn)

        self.tree.currentItemChanged.connect(self.choose)
        self.search.textChanged.connect(self.filter)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context)
        self.signature = None

    def refresh(self):
        from .tokens import current_tokens, ui_font
        t = current_tokens()
        self.setProperty('tablaThemed', True)
        self.setStyleSheet(f'QWidget#boardSidebar {{background:{t.bg_surface};border-right:1px solid {t.border_subtle};}}')
        self.header_title.setStyleSheet(f'font-size:14px;font-weight:600;color:{t.ink_primary};padding:0 2px;')
        self.top_sep.setStyleSheet(f'background:{t.border_subtle};border:none;')
        self.bottom_sep.setStyleSheet(f'background:{t.border_subtle};border:none;')
        self.search.setProperty('tablaThemed', True)
        self.search.setStyleSheet(
            f'QLineEdit {{background:{t.bg_elevated};color:{t.ink_primary};border:1px solid {t.border_subtle};'
            f'border-radius:8px;padding:3px 8px;font-size:12px;}}'
            f'QLineEdit:hover {{border-color:{t.border_strong};}}'
            f'QLineEdit:focus {{border-color:{t.accent};}}'
        )
        self.search_icon.setIcon(icon('search', t.ink_muted, 15, preserve_color=True))
        self.collapse.setIcon(icon('left', t.ink_muted, 15, preserve_color=True))
        self.new_board_btn.setIcon(icon('plus', t.ink_primary, 15, preserve_color=True))
        self.new_board_btn.setStyleSheet(
            f'QPushButton {{background:{t.bg_elevated};color:{t.ink_primary};border:1px solid {t.border_subtle};'
            f'border-radius:8px;padding:5px 10px;text-align:left;font-size:12px;font-weight:500;}}'
            f'QPushButton:hover {{background:{t.bg_surface_hover};border-color:{t.border_strong};}}'
        )
        self.archived_btn.setIcon(icon('archive', t.ink_muted, 15, preserve_color=True))
        self.archived_btn.setStyleSheet(
            f'QPushButton {{background:transparent;color:{t.ink_muted};border:none;'
            f'border-radius:8px;padding:5px 10px;text-align:left;font-size:12px;}}'
            f'QPushButton:hover {{background:{t.bg_surface_hover};color:{t.ink_primary};}}'
        )
        self.tree.setProperty('tablaThemed', True)
        self.tree.setStyleSheet(
            f'QTreeWidget {{border:none;background:transparent;outline:0;show-decoration-selected:0;}}'
            f'QTreeWidget::item {{padding:6px 8px;margin:1px 0;border-radius:8px;color:{t.ink_secondary};}}'
            f'QTreeWidget::item:hover {{background:{t.bg_surface_hover};color:{t.ink_primary};}}'
            f'QTreeWidget::item:selected {{background:{t.bg_surface_active};color:{t.ink_primary};font-weight:600;}}'
            f'QTreeWidget::branch {{background:transparent;}}'
            f'QTreeWidget::branch:selected {{background:transparent;}}'
        )
        boards = self.owner.board_catalog.boards()
        signature = (
            t.key,
            [(b['id'], b['title'], b.get('project'),
              (self.owner.store.get(b.get('project')) or {}).get('title')) for b in boards],
        )
        group_font = ui_font(10, QFont.Weight.DemiBold)
        group_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        item_font = ui_font(13, QFont.Weight.Normal)
        active_font = ui_font(13, QFont.Weight.DemiBold)
        self.tree.blockSignals(True)
        if signature != self.signature:
            expanded = {self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole): self.tree.topLevelItem(i).isExpanded() for i in range(self.tree.topLevelItemCount())}
            self.tree.clear()
            groups = {}
            for board in boards:
                project = board.get('project')
                if project not in groups:
                    owner = self.owner.store.get(project) if project else None
                    name = (owner['title'] if owner else 'Personal').upper()
                    group = QTreeWidgetItem([name])
                    group.setData(0, Qt.ItemDataRole.UserRole, project or 'personal')
                    group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    group.setFont(0, group_font)
                    group.setForeground(0, QColor(t.ink_muted))
                    group.setSizeHint(0, QSize(0, 26))
                    self.tree.addTopLevelItem(group)
                    group.setExpanded(expanded.get(project or 'personal', True))
                    groups[project] = group
                item = QTreeWidgetItem([board['title']])
                item.setData(0, Qt.ItemDataRole.UserRole, board['id'])
                item.setToolTip(0, board['title'])
                item.setSizeHint(0, QSize(0, 32))
                groups[project].addChild(item)
            self.signature = signature
        for group_index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(group_index)
            group.setExpanded(True)
            for child_index in range(group.childCount()):
                item = group.child(child_index)
                is_current = item.data(0, Qt.ItemDataRole.UserRole) == self.owner.board_id
                item.setFont(0, active_font if is_current else item_font)
                item.setForeground(0, QColor(t.ink_primary if is_current else t.ink_secondary))
                item.setIcon(0, icon('board', t.ink_primary if is_current else t.ink_muted, 15, preserve_color=True))
                if is_current:
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
