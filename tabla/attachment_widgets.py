from pathlib import Path
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFileDialog, QMessageBox, QSizePolicy
from .attachments import FILE_FILTER, short_name
from .widgets import label, button, clear, scroll
from .theme import polish_surfaces
from .polish import fade_in


class AttachmentPanel(QWidget):
    changed = Signal()
    def __init__(self, vault, items=None, compact=False, editable=True, parent=None):
        super().__init__(parent)
        self.vault = vault
        self.items = [dict(item) for item in (items or [])]
        self.compact, self.editable = compact, editable
        self.preview_images = False
        self.max_height = 156
        self.setAcceptDrops(editable)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.host = QWidget()
        self.rows = QVBoxLayout(self.host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        root.addWidget(scroll(self.host))
        self.render()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Attach files', '', FILE_FILTER)
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        try:
            if len(self.items) + len(paths) > 100:
                raise ValueError('A note can have up to 100 attachments.')
            imported = self.vault.import_files(paths)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Could not attach files', str(exc))
            return False
        known = {item['key'] for item in self.items}
        self.items.extend(item for item in imported if item['key'] not in known)
        self.render()
        self.changed.emit()
        fade_in(self)
        return True

    def set_compact(self, compact):
        self.compact = bool(compact)
        self.render()
        self.changed.emit()

    def remove(self, index):
        self.items.pop(index)
        self.render()
        self.changed.emit()

    def render(self):
        clear(self.rows)
        self.setVisible(bool(self.items))
        for index, item in enumerate(self.items):
            frame = QFrame()
            frame.setFixedHeight(40 if self.compact else 46)
            frame.setStyleSheet('QFrame {background:#fafaf9;border:1px solid #e5e5e3;border-radius:7px;}')
            row = QHBoxLayout(frame)
            row.setContentsMargins(9, 6, 7, 6)
            row.setSpacing(10)
            extension = Path(item['name']).suffix.lstrip('.').upper()
            badge = label(extension[:4])
            badge.setFixedWidth(34)
            badge.setStyleSheet('font-size:10px;font-weight:600;color:#73726d;border:none;background:transparent;')
            badge.setVisible(not self.compact)
            if self.preview_images and item.get('mime', '').startswith('image/'):
                from PySide6.QtGui import QPixmap
                pixmap = QPixmap(str(self.vault.path_for(item)))
                if not pixmap.isNull():
                    badge.setPixmap(pixmap.scaled(40, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    badge.setFixedSize(40, 32)
            row.addWidget(badge)
            text = short_name(item['name'], 28 if self.compact else 48)
            open_file = button(text, lambda checked=False, attachment=item: self.open_file(attachment), 'text', elide=True)
            open_file.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            open_file.setToolTip(item['name'] + '\n' + self.size_text(item['size']))
            open_file.setAccessibleName('Open attachment ' + item['name'])
            open_file.setStyleSheet('border:none;background:transparent;text-align:left;padding:2px 0;font-size:12px;')
            row.addWidget(open_file, 1)
            if not self.compact:
                size = label(self.size_text(item['size']), 'muted')
                size.setStyleSheet('font-size:10px;border:none;background:transparent;')
                row.addWidget(size)
            if self.editable:
                detach = button('×', lambda checked=False, i=index: self.remove(i), 'text')
                detach.setToolTip('Remove attachment')
                detach.setAccessibleName('Remove attachment ' + item['name'])
                detach.setFixedWidth(22)
                row.addWidget(detach)
            self.rows.addWidget(frame)
        height = len(self.items) * (46 if self.compact else 52) - 6
        if self.max_height is not None:
            height = min(self.max_height, height)
        self.setFixedHeight(max(0, height))
        polish_surfaces(self)

    @staticmethod
    def size_text(size):
        return f'{size / (1024 * 1024):.1f} MB' if size >= 1024 * 1024 else f'{max(1, round(size / 1024))} KB'

    def open_file(self, item):
        try:
            path = self.vault.path_for(item)
            if not path.is_file():
                raise ValueError('The attachment file is missing. Restore it from a workspace backup.')
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise ValueError('No application could open this file. Install an application for this file type.')
        except (ValueError, OSError) as exc:
            QMessageBox.information(self, 'Attachment unavailable', str(exc))

    def dragEnterEvent(self, event):
        if self.editable and event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]):
            event.acceptProposedAction()
