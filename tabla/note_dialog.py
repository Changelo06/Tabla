"""Keep-like note sheet with an independently floating reference card."""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from PySide6.QtCore import Qt, QTimer, QUrl, QRect, QPoint, QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QTextCursor, QIcon, QPixmap, QFont
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QMenu, QFileDialog, QInputDialog, QMessageBox, QGraphicsBlurEffect, QApplication,
    QSizePolicy)
from .dialogs import LegacyNoteDialog, PolishedDialog, project_picker
from .widgets import label, button, row, clear, PinButton, scroll
from .polish import ColorPicker, color_popup, motion_enabled
from .theme import themed_color, polish_surfaces, COLORS
from .rich_document import RichNoteEditor, TEMPLATES
from .attachment_widgets import AttachmentPanel
from .attachments import short_name


def _floating_shadow(widget, dark):
    width, height, dpr = widget.width(), widget.height(), round(widget.devicePixelRatioF(), 2)
    key = (width, height, dpr, dark)
    if getattr(widget, '_shadow_key', None) == key:
        return widget._shadow_cache
    px_w, px_h = max(1, round(width * dpr)), max(1, round(height * dpr))
    pm = QPixmap(px_w, px_h)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRect(0, 0, width, height).adjusted(12, 12, -12, -12)
    p.setPen(Qt.PenStyle.NoPen)
    for spread in range(11, 0, -1):
        alpha = (4 if spread > 5 else 7) if dark else (2 if spread > 5 else 4)
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawRoundedRect(rect.adjusted(-spread, -spread + 3, spread, spread + 3), 14 + spread, 14 + spread)
    p.end()
    widget._shadow_key = key
    widget._shadow_cache = pm
    return pm


class FloatingSurface(PolishedDialog):
    def surface_background(self):
        return themed_color('#ffffff')

    def paintEvent(self, event):
        from .tokens import current_tokens
        t = current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, _floating_shadow(self, t.dark))
        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.setPen(QPen(QColor(t.border_strong), 0.8))
        painter.setBrush(QColor(self.surface_background()))
        painter.drawRoundedRect(rect, 14, 14)


class NoteDialog(LegacyNoteDialog):
    def __init__(self, store, record=None, project=None, parent=None):
        # Deliberately replace the old tabbed/embedded-pane construction.
        PolishedDialog.__init__(self, parent)
        self.store, self.record = store, dict(record or {})
        self.setProperty('notesSurface', True)
        self.pending_navigation, self.dirty = None, False
        self._opening_origin = getattr(parent, '_note_origin', None)
        self._opening_card = getattr(parent, '_note_snapshot', None)
        self._return_card = self._opening_card
        if parent:
            parent._note_origin = None
            parent._note_snapshot = None
        self._morph_overlay = None
        self._opening_pending = False
        self._closing_pending = False
        self._closing_overlay = None
        self._closing_result = 0
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('Note · tabla')
        self.setMinimumSize(420, 360)
        self.resize(min(650, max(420, parent.width() - 50)) if parent else 650,
                    min(720, max(360, parent.height() - 50)) if parent else 680)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 27, 30, 24)
        outer.setSpacing(10)
        self.reading = self
        self.title = QLineEdit(self.record.get('title', ''))
        self.title.setPlaceholderText('Title')
        self.title.setStyleSheet("font-family:'Inter';font-size:19px;font-weight:500;border:none;background:transparent;padding:6px;")
        self.pin = PinButton(self.record.get('pinned', False))
        outer.addLayout(row(self.title, self.pin))
        self.editor = RichNoteEditor(store)
        self.editor.setPlaceholderText('Take a note…')
        self.editor.load_note(self.record)
        self.editor.linkActivated.connect(lambda token: self.follow(QUrl('tabla:' + quote(token, safe=''))))
        outer.addWidget(self.editor, 1)
        self.project = project_picker(store, self.record.get('project', project))
        self.color = ColorPicker()
        self.color.addItems(['yellow', 'violet', 'blue', 'green', 'rose', 'gray'])
        self.color.setCurrentText(self.record.get('color', 'gray'))
        self.color.currentTextChanged.connect(self.refresh_note_color)
        self.editor.viewport().setAutoFillBackground(False)
        self.labels = QLineEdit(self.record.get('labels', ''))
        self.labels.setPlaceholderText('Labels, separated by commas')
        self.details = QWidget()
        details = QVBoxLayout(self.details)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(self.project)
        details.addWidget(self.labels)
        outer.addWidget(self.details)
        self.details.hide()
        self.link_label = label('', 'muted', True)
        self.status = label('', 'muted', True)
        self.link_label.hide()
        self.status.hide()
        outer.addWidget(self.link_label)
        outer.addWidget(self.status)
        self.edited = label('', 'muted')
        self.edited.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.edited.setStyleSheet('font-size:11px;padding:0 7px;color:#80868b;')
        outer.addWidget(self.edited)
        controls = QHBoxLayout()
        controls.setSpacing(3)
        self.secondary_controls = []
        self.context_toggle = button('', self.toggle_context, 'text', 'sidebar')
        self.context_toggle.setToolTip('Links & sources')
        self.context_toggle.setAccessibleName('Links and sources')
        self.context_toggle.setCheckable(True)
        for text, glyph, tip, callback in (
            ('', 'format', 'Formatting', self.format_menu),
            ('', 'palette', 'Background and color', self.background_menu),
            ('', 'attachment', 'Insert', self.insert_menu),
            ('', 'image', 'Insert image', self.choose_image),
            ('', 'bullets', 'Lists: dots, numbers, letters', self.editor.cycle_list),
            ('', 'tasks', 'Add checklist', self.editor.add_checklist),
            ('', 'more', 'More options', self.more_menu),
            ('', 'undo', 'Undo', self.editor.undo),
            ('', 'redo', 'Redo', self.editor.redo)):
            if glyph == 'bullets':
                from .rich_document import list_style_button
                control = list_style_button(self.editor)
            else:
                control = button(text, callback, 'text', glyph)
            control.setToolTip(tip)
            if glyph != 'bullets':
                control.setAccessibleName(tip)
            control.setFixedWidth(30)
            if tip in ('Undo', 'Redo'):
                self.secondary_controls.append(control)
                control.setEnabled(False)
                (self.editor.undoAvailable if tip == 'Undo' else self.editor.redoAvailable).connect(control.setEnabled)
            controls.addWidget(control)
        controls.addWidget(self.context_toggle)
        controls.addStretch()
        controls.addWidget(button('Close', self.accept, 'text'))
        outer.addLayout(controls)
        self.sidecar = FloatingSurface(self)
        self.sidecar.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.sidecar.setWindowTitle('Links and sources · tabla')
        self.sidecar.setFixedWidth(294)
        self.sidecar.setMinimumHeight(170)
        side = QVBoxLayout(self.sidecar)
        side.setContentsMargins(30, 28, 30, 27)
        side.setSpacing(9)
        self.links_heading = label('Links', 'muted')
        dismiss_context = button('×', self.hide_context, 'text')
        dismiss_context.setFixedSize(26, 26)
        dismiss_context.setToolTip('Close panel')
        dismiss_context.setAccessibleName('Close links and sources')
        side.addLayout(row(self.links_heading, None, dismiss_context))
        link_host = QWidget()
        self.outgoing = QVBoxLayout(link_host)
        self.outgoing.setContentsMargins(0, 0, 0, 0)
        self.outgoing.setSpacing(2)
        self.backlinks = QVBoxLayout()
        self.backlinks.setSpacing(2)
        self.outgoing.addLayout(self.backlinks)
        # Backlinks are populated after outgoing rows; use a separate fixed host.
        self.outgoing.removeItem(self.backlinks)
        self.links_scroll = scroll(link_host)
        self.links_scroll.setMaximumHeight(180)
        side.addWidget(self.links_scroll)
        back_host = QWidget()
        back_host.setLayout(self.backlinks)
        self.backlinks_scroll = scroll(back_host)
        side.addWidget(self.backlinks_scroll)
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet('background:#e5e5e3;')
        side.addWidget(divider)
        self.sources_heading = label('Sources', 'muted')
        side.addLayout(row(self.sources_heading, None, button('', lambda: self.attachments.choose_files(), 'text', 'plus')))
        # Authoritative attachment list is independent from the three-row preview.
        self.attachments = AttachmentPanel(store.attachments, self.record.get('attachments', []), True, parent=self.sidecar)
        self.attachments.hide()
        self.source_rows = QVBoxLayout()
        self.source_rows.setSpacing(2)
        side.addLayout(self.source_rows)
        self.empty_sources = label('No sources yet', 'muted')
        side.addWidget(self.empty_sources)
        self.view_all = button('View all', self.show_all_sources, 'text', 'link')
        side.addWidget(self.view_all)
        self.attachments.changed.connect(self.refresh_sources)
        self.attachments.changed.connect(self.mark_dirty)
        self.editor.filesDropped.connect(self.attachments.add_paths)
        self.editor.imagesInserted.connect(self.add_image_sources)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(450)
        self.autosave.timeout.connect(self.save)
        for widget, signal in ((self.title, 'textChanged'), (self.editor, 'textChanged'),
                               (self.labels, 'textChanged'), (self.project, 'currentIndexChanged'),
                               (self.color, 'currentIndexChanged'), (self.pin, 'toggled')):
            getattr(widget, signal).connect(self.mark_dirty)
        self.changed.connect(self.refresh_backlinks)
        self._context_visible, self._shown = True, False
        self._backdrop = None
        self.refresh_backlinks()
        self.refresh_sources()
        self.update_edited()
        polish_surfaces(self)
        polish_surfaces(self.sidecar)
        self.layout_toolbar()

    def layout_toolbar(self):
        for control in self.secondary_controls:
            control.setVisible(self.width() >= 520)

    paintEvent = FloatingSurface.paintEvent

    def surface_background(self):
        color = self.color.currentText() if hasattr(self, 'color') else self.record.get('color', 'gray')
        background = COLORS.get(color, COLORS['gray'])[0] if color != 'gray' else '#ffffff'
        return themed_color(background)

    def refresh_note_color(self, *args):
        self.update()
        self.editor.viewport().update()

    def refresh_backlinks(self):
        LegacyNoteDialog.refresh_backlinks(self)
        self.links_scroll.setFixedHeight(min(150, max(32, self.outgoing.count() * 34)))
        self.backlinks_scroll.setFixedHeight(min(120, self.backlinks.count() * 30))
        if hasattr(self, '_shown'):
            self.sidecar.adjustSize()
            self.layout_context()

    def refresh_sources(self):
        clear(self.source_rows)
        self.attachments.hide()
        for item in self.attachments.items[:3]:
            source = button(short_name(item['name'], 26), lambda checked=False, value=item: self.attachments.open_file(value), 'text', 'note', elide=True)
            source.setToolTip(item['name'])
            source.setAccessibleName('Open source ' + item['name'])
            source.setProperty('sourceKey', item['key'])
            source.setFixedHeight(30)
            source.setStyleSheet('text-align:left;border:none;background:transparent;font-size:12px;padding:5px 0;')
            source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            self.source_rows.addWidget(source)
            source.show()
        count = len(self.attachments.items)
        self.sources_heading.setText('Sources' + (f'  {count}' if count else ''))
        self.empty_sources.setVisible(not count)
        self.view_all.setVisible(bool(count))
        self.view_all.setToolTip(f'View all {count} source files')
        self.fit_sidecar()
        QTimer.singleShot(0, self.fit_sidecar)
        if hasattr(self, '_shown'):
            self.layout_context()

    def fit_sidecar(self):
        self.sidecar.layout().invalidate()
        self.sidecar.layout().activate()
        self.sidecar.setFixedHeight(max(170, min(520, self.sidecar.layout().sizeHint().height())))

    def show_all_sources(self):
        dialog = FloatingSurface(self)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.resize(520, 440)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(32, 30, 32, 30)
        layout.addWidget(label('All sources', 'section'))
        panel = AttachmentPanel(self.store.attachments, self.attachments.items, False, False, dialog)
        panel.max_height = None
        panel.render()
        layout.addWidget(scroll(panel), 1)
        layout.addLayout(row(None, button('Close', dialog.accept, 'text')))
        self.all_sources_dialog = dialog
        polish_surfaces(dialog)
        dialog.exec()

    def add_image_sources(self, items):
        known = {a['key'] for a in self.attachments.items}
        if len(known | {a['key'] for a in items}) > 100:
            raise ValueError('A note supports up to 100 source files.')
        self.attachments.items.extend(a for a in items if a['key'] not in known)
        self.refresh_sources()
        self.mark_dirty()

    def toggle_context(self):
        self._context_visible = not self.sidecar.isVisible()
        self.context_toggle.setChecked(self._context_visible)
        self.layout_context()

    def hide_context(self):
        self._context_visible = False
        self.context_toggle.setChecked(False)
        self.sidecar.hide()
        self.editor.setFocus()

    def layout_context(self):
        if not self._shown:
            return
        if self._opening_pending or self._closing_pending:
            self.sidecar.hide()
            return
        available = self.screen().availableGeometry()
        if self.parentWidget():
            available = available.intersected(QRect(self.parentWidget().mapToGlobal(QPoint()), self.parentWidget().size()))
        right = self.geometry().right() + 8
        can_fit = right + self.sidecar.width() <= available.right()
        show = self._context_visible and (can_fit or self.context_toggle.isChecked())
        self.sidecar.move(right if can_fit else max(available.left(), available.right() - self.sidecar.width()),
                          max(available.top(), min(self.y() + 30, available.bottom() - self.sidecar.height())))
        self.sidecar.setVisible(show)
        self.context_toggle.setChecked(show)

    def resizeEvent(self, event):
        PolishedDialog.resizeEvent(self, event)
        if hasattr(self, 'secondary_controls'):
            self.layout_toolbar()
        if hasattr(self, '_shown'):
            self.layout_context()

    def moveEvent(self, event):
        PolishedDialog.moveEvent(self, event)
        if hasattr(self, '_shown'):
            self.layout_context()

    def showEvent(self, event):
        parent = self.parentWidget()
        if not self._shown and parent:
            center = parent.mapToGlobal(parent.rect().center())
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
            from .layer_effects import WorkspaceBackdrop
            self._backdrop = WorkspaceBackdrop(parent, parent.grab())
            self._backdrop.show()
            self._backdrop.raise_()
        self._shown = True
        PolishedDialog.showEvent(self, event)
        QTimer.singleShot(0, self.layout_context)
        if self._opening_origin and motion_enabled():
            self._opening_pending = True
            if self._backdrop:
                self._backdrop.set_strength(0)
            self._fade.stop()
            self.setWindowOpacity(0)
            QApplication.instance().installEventFilter(self)
            QTimer.singleShot(0, self.start_opening)

    def start_opening(self):
        if not self._shown or not self._opening_pending:
            return
        if not motion_enabled():
            self.finish_opening()
            return
        from .note_motion import NoteOpening
        self._morph_overlay = NoteOpening(self, self._opening_origin, self._opening_card, self.grab())
        self._morph_overlay.show()
        self._morph_overlay.animation.start()

    def finish_opening(self):
        self._opening_pending = False
        QApplication.instance().removeEventFilter(self)
        overlay, self._morph_overlay = self._morph_overlay, None
        self.setWindowOpacity(1)
        if overlay:
            overlay.animation.stop()
            overlay.hide()
            overlay.deleteLater()
        self._opening_card = None
        if self._backdrop:
            self._backdrop.set_strength(1)
        if self._shown:
            self.layout_context()
            if self.sidecar.isVisible() and motion_enabled():
                self._animate_sidecar_entry()

    def _animate_sidecar_entry(self):
        from .spring import SpringAnimation, SECONDARY_LAG
        target_pos = QPoint(self.sidecar.pos())
        start_x = target_pos.x() - 10
        self.sidecar.move(start_x, target_pos.y())
        self.sidecar.setWindowOpacity(0.0)
        anim = SpringAnimation(SECONDARY_LAG, 210, self.sidecar)
        def step(v):
            p = float(v)
            self.sidecar.move(round(start_x + 10.0 * p), target_pos.y())
            self.sidecar.setWindowOpacity(max(0.0, min(1.0, p)))
        anim.valueChanged.connect(step)
        self.sidecar._lag_anim = anim
        QTimer.singleShot(55, anim.start)

    def done(self, result):
        if self._closing_pending:
            self.finish_closing()
            return
        was_opening = self._opening_pending
        presentation = (QRect(self._morph_overlay.geometry()), self._morph_overlay.progress) if self._morph_overlay else None
        self.finish_opening()
        if not self.save():
            return
        if not self._shown or not motion_enabled() or was_opening and (not presentation or presentation[1] <= 0):
            QDialog.done(self, result)
            return
        self._closing_pending, self._closing_result = True, result
        self.sidecar.hide()
        self.editor.setReadOnly(True)
        self.title.setReadOnly(True)
        from .note_motion import NoteOpening
        origin, card = self._opening_origin, self._return_card
        if not origin or self.record.get('deleted') or self.record.get('archived'):
            # New/removed notes have no surviving card: a small, soft retreat.
            origin = self.geometry().adjusted(16, 10, -16, -10)
            origin.translate(0, 8)
            card = None
        self._closing_overlay = NoteOpening(self, origin, card, self.grab(), closing=True, presentation=presentation)
        self._closing_overlay.show()
        self.setWindowOpacity(0)
        QApplication.instance().installEventFilter(self)
        self._closing_overlay.animation.start()

    def finish_closing(self):
        if not self._closing_pending:
            return
        self._closing_pending = False
        QApplication.instance().removeEventFilter(self)
        overlay, self._closing_overlay = self._closing_overlay, None
        if overlay:
            overlay.animation.stop()
            overlay.hide()
            overlay.deleteLater()
        QDialog.done(self, self._closing_result)

    def finish_motion(self):
        if self._closing_pending:
            self.finish_closing()
        else:
            self.finish_opening()

    def eventFilter(self, watched, event):
        if self._closing_pending and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.finish_closing()
            return True
        if self._opening_pending and event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            if watched is self or isinstance(watched, QWidget) and self.isAncestorOf(watched):
                self.finish_opening()
        return PolishedDialog.eventFilter(self, watched, event)

    def hideEvent(self, event):
        self._shown = False
        self._closing_pending = False
        if self._closing_overlay:
            self._closing_overlay.animation.stop()
            self._closing_overlay.hide()
            self._closing_overlay.deleteLater()
            self._closing_overlay = None
        self.finish_opening()
        self.sidecar.hide()
        if self._backdrop:
            self._backdrop.hide()
            self._backdrop.deleteLater()
            self._backdrop = None
        PolishedDialog.hideEvent(self, event)

    def mark_dirty(self, *args):
        self.dirty = True
        self.edited.setText('Saving…')
        self.edited.show()
        self.autosave.start()

    def update_edited(self):
        stamp = self.record.get('updated_at')
        self.edited.setVisible(bool(stamp))
        if stamp:
            local = datetime.fromisoformat(stamp).astimezone()
            self.edited.setText('Saved · Edited ' + local.strftime('%b %d, %I:%M %p').replace(' 0', ' '))
            self.edited.setToolTip(local.strftime('%A, %d %B %Y at %I:%M:%S %p %Z'))

    def save(self):
        self.autosave.stop()
        if not self.dirty:
            return True
        record = dict(self.record)
        if not record.get('document') and record.get('body'):
            record.setdefault('legacy_body', record['body'])
        record.update(kind='note', title=self.title.text().strip() or 'Untitled note',
            body=self.editor.plain_body(), document=self.editor.snapshot(),
            project=self.project.currentData(), color=self.color.currentText(), labels=self.labels.text(),
            pinned=self.pin.isChecked(), link_targets=self.editor.link_targets,
            attachments=list(self.attachments.items), attachment_display='compact',
            note_template=self.editor.template, pattern_spacing=self.editor.pattern_spacing,
            pattern_strength=self.editor.pattern_strength)
        try:
            self.record = self.store.save(record)
        except Exception as exc:
            self.edited.setText('Not saved')
            self.status.setText(f'Not saved: {exc}. Keep this note open and retry Close.')
            self.status.show()
            return False
        self.dirty = False
        self.status.hide()
        self.update_edited()
        self.changed.emit()
        return True

    def format_menu(self):
        menu = QMenu(self)
        for title, mark in (('Bold  Ctrl+B', 'bold'), ('Italic  Ctrl+I', 'italic'), ('Underline  Ctrl+U', 'underline'), ('Highlight', 'highlight')):
            action = menu.addAction(title, lambda checked=False, m=mark: self.editor.toggle_mark(m))
            action.setCheckable(True)
            fmt = self.editor.currentCharFormat()
            action.setChecked({'bold': fmt.fontWeight() >= 700, 'italic': fmt.fontItalic(), 'underline': fmt.fontUnderline(), 'highlight': fmt.background().style() != Qt.BrushStyle.NoBrush}[mark])
        menu.addSeparator()
        for title, alignment in (('Align left', Qt.AlignmentFlag.AlignLeft), ('Center', Qt.AlignmentFlag.AlignHCenter), ('Align right', Qt.AlignmentFlag.AlignRight)):
            menu.addAction(title, lambda checked=False, a=alignment: self.editor.setAlignment(a))
        self.exec_menu(menu)

    def exec_menu(self, menu):
        sender = self.sender()
        point = sender.mapToGlobal(QPoint(0, -menu.sizeHint().height())) if isinstance(sender, QWidget) else self.mapToGlobal(QPoint(20, self.height() - 200))
        polish_surfaces(menu)
        menu.exec(point)

    def background_menu(self):
        menu = QMenu(self)
        for key, title in TEMPLATES.items():
            action = menu.addAction(title, lambda checked=False, k=key: self.set_background(k))
            action.setIcon(self.pattern_icon(key))
            action.setCheckable(True)
            action.setChecked(self.editor.template == key)
        spacing = menu.addMenu('Pattern spacing')
        for title, value in (('Compact', 18), ('Standard', 24), ('Wide', 32)):
            spacing.addAction(title, lambda checked=False, v=value: self.set_background(self.editor.template, v))
        strength = menu.addMenu('Pattern strength')
        for title, value in (('Low', .08), ('Medium', .12), ('High', .2)):
            strength.addAction(title, lambda checked=False, v=value: self.set_pattern_strength(v))
        menu.addSeparator()
        menu.addAction('Note color…', self.color_menu)
        self.exec_menu(menu)

    def pattern_icon(self, key):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(themed_color('#fafaf9')))
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(themed_color('#aaa9a3')), .8))
        for y in range(4, 32, 6):
            if key in ('lines', 'grid'):
                painter.drawLine(0, y, 32, y)
            elif key in ('dots', 'diamonds', 'paper'):
                for x in range(4, 32, 6):
                    if key == 'diamonds':
                        painter.drawLine(x - 1, y, x, y - 1)
                        painter.drawLine(x, y - 1, x + 1, y)
                        painter.drawLine(x + 1, y, x, y + 1)
                        painter.drawLine(x, y + 1, x - 1, y)
                    else:
                        painter.drawPoint(x + (y % 3 if key == 'paper' else 0), y)
        if key == 'grid':
            for x in range(4, 32, 6):
                painter.drawLine(x, 0, x, 32)
        painter.end()
        return QIcon(pixmap)

    def set_background(self, key, spacing=None):
        self.editor.set_template(key, spacing or self.editor.pattern_spacing, self.editor.pattern_strength)
        self.mark_dirty()

    def set_pattern_strength(self, value):
        self.editor.set_template(self.editor.template, self.editor.pattern_spacing, value)
        self.mark_dirty()

    def insert_menu(self):
        menu = QMenu(self)
        menu.addAction('Insert image…', self.choose_image)
        menu.addAction('Insert table…', self.choose_table)
        menu.addAction('Attach source files…', self.attachments.choose_files)
        self.exec_menu(menu)

    def choose_image(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Insert images', '', 'Images (*.png *.jpg *.jpeg *.webp *.gif)')
        if paths:
            try:
                self.editor.insert_images(paths)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, 'Could not insert image', str(exc))

    def choose_table(self):
        columns, ok = QInputDialog.getInt(self, 'Insert table', 'Columns (maximum 10)', 3, 1, 10)
        if not ok:
            return
        rows, ok = QInputDialog.getInt(self, 'Insert table', 'Rows', 3, 1, 2000)
        if ok:
            try:
                self.editor.insert_table(rows, columns)
            except ValueError as exc:
                QMessageBox.information(self, 'Insert table', str(exc))

    def more_menu(self):
        menu = QMenu(self)
        menu.addAction('Download as .txt…', self.export_text)
        menu.addAction('Labels and project', lambda: self.details.setVisible(not self.details.isVisible()))
        menu.addAction('Links and sources', self.toggle_context)
        menu.addAction('Create task', self.create_task)
        if self.record.get('id'):
            menu.addSeparator()
            menu.addAction('Archive', self.archive)
            menu.addAction('Move to trash', self.trash)
        self.exec_menu(menu)

    def export_text(self):
        import re
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', self.title.text().strip() or 'Untitled note')[:100]
        path, _ = QFileDialog.getSaveFileName(self, 'Download plain text · formatting and image bytes are omitted', name + '.txt', 'Text files (*.txt)')
        if path:
            try:
                Path(path).write_text(self.title.text() + '\n\n' + self.editor.plain_body(), encoding='utf-8')
            except OSError as exc:
                QMessageBox.warning(self, 'Could not export note', str(exc))

    def create_task(self):
        if not self.record.get('id'):
            self.mark_dirty()
        if not self.save():
            return
        from .dialogs import ItemDialog
        dialog = ItemDialog(self.store, 'task', project=self.project.currentData(), parent=self)
        dialog.title.setText(self.editor.textCursor().selectedText().strip() or self.title.text())
        dialog.body.setPlainText('Reference: [[' + self.record['id'] + ']]')
        if dialog.exec():
            self.editor.appendPlainText('Task: [[' + dialog.result_record['id'] + ']]')
            self.save()

    def follow(self, url):
        LegacyNoteDialog.follow(self, url)
        self.link_label.setVisible(bool(self.link_label.text()))
