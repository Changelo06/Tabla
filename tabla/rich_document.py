"""Portable note documents and their native, single-surface editor."""
from __future__ import annotations

import re
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QStringListModel, QRectF, QPointF, QPoint, QSize
from PySide6.QtGui import (QTextCursor, QTextCharFormat, QTextBlockFormat, QTextImageFormat,
    QTextTable, QTextTableFormat, QTextFrameFormat, QTextLength, QTextListFormat,
    QTextDocument, QFont, QColor, QImage, QImageReader, QPixmap, QPolygonF, QPainter, QPen,
    QKeySequence, QTextDocumentFragment)
from PySide6.QtWidgets import QTextEdit, QCompleter, QMenu, QInputDialog, QMessageBox
from .widgets import LinkEditor

TEMPLATES = {'none': 'None', 'lines': 'Note lines', 'dots': 'Dotted grid',
             'grid': 'Grid lines', 'paper': 'Paper texture', 'diamonds': 'Diamond dots'}


def list_style_button(editor):
    from .widgets import button
    from .theme import icon
    from PySide6.QtGui import QIcon
    control = button('', editor.cycle_list, 'text', 'bullets')
    def update():
        current = editor.textCursor().currentList()
        style = current.format().style() if current and not editor._is_check(editor.textCursor().block()) else None
        caption, text = ('Numbers', '1.') if style == QTextListFormat.Style.ListDecimal else ('Letters', 'A.') if style == QTextListFormat.Style.ListUpperAlpha else ('Bullets', '')
        control.setText(text)
        control.setIcon(QIcon() if text else icon('bullets'))
        control.setToolTip(caption)
        control.setAccessibleName('Cycle list style')
    control.clicked.connect(update)
    update()
    return control


def validate_document(data, attachments):
    if data is None:
        return
    keys = {a['key'] for a in attachments}
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('nodes'), list):
        raise ValueError('Unsupported note document.')
    budget = [0]
    def visit(nodes, depth=0):
        if not isinstance(nodes, list) or depth > 8:
            raise ValueError('Note document is too deeply nested.')
        for n in nodes:
            budget[0] += 1
            if budget[0] > 100000 or not isinstance(n, dict):
                raise ValueError('Invalid note document.')
            kind = n.get('type')
            if kind == 'paragraph':
                if not isinstance(n.get('runs'), list):
                    raise ValueError('Invalid note paragraph.')
                for field, default, lower, upper in (('alignment', 1, 1, 511), ('heading', 0, 0, 6), ('indent', 1, 0, 16), ('check', 0, 0, 2)):
                    value = n.get(field, default)
                    if type(value) is not int or not lower <= value <= upper:
                        raise ValueError('Invalid paragraph formatting.')
                if 'list' in n and n['list'] not in range(-8, 0):
                    raise ValueError('Invalid list style.')
                for run in n['runs']:
                    if not isinstance(run, dict) or not isinstance(run.get('text', ''), str):
                        raise ValueError('Invalid note text.')
                    for mark in ('bold', 'italic', 'underline', 'strike'):
                        if mark in run and type(run[mark]) is not bool:
                            raise ValueError('Invalid text formatting.')
                    if run.get('highlight') and not re.fullmatch(r'#[a-fA-F0-9]{6}', run['highlight']):
                        raise ValueError('Invalid highlight color.')
                    if 'size' in run and (type(run['size']) not in (int, float) or not 6 <= run['size'] <= 72):
                        raise ValueError('Invalid text size.')
                    if 'href' in run and not isinstance(run['href'], str):
                        raise ValueError('Invalid text link.')
                    if 'image' in run:
                        image = run['image']
                        if not isinstance(image, dict) or image.get('key') not in keys:
                            raise ValueError('An inserted image has no source file.')
                        if image.get('wrap', 'inline') not in ('inline', 'left', 'right'):
                            raise ValueError('Invalid image wrapping.')
                        if not isinstance(image.get('alt', ''), str):
                            raise ValueError('Invalid image description.')
                        if image.get('vertical', 0) not in range(7):
                            raise ValueError('Invalid image alignment.')
                        for dim in ('width', 'height'):
                            if type(image.get(dim)) not in (int, float) or not 1 <= image[dim] <= 20000:
                                raise ValueError('Invalid image dimensions.')
            elif kind == 'table':
                cols, cells = n.get('columns'), n.get('cells')
                if type(cols) is not int or not 1 <= cols <= 10 or not isinstance(cells, list) or not 1 <= len(cells) <= 2000:
                    raise ValueError('Tables support 1–10 columns and up to 2000 rows.')
                for row in cells:
                    if not isinstance(row, list) or len(row) != cols:
                        raise ValueError('Invalid table cells.')
                    for cell in row:
                        visit(cell, depth + 1)
            elif kind == 'frame':
                if n.get('position') not in ('left', 'right', 'inline'):
                    raise ValueError('Invalid image wrap mode.')
                visit(n.get('nodes'), depth + 1)
            else:
                raise ValueError('Invalid note element.')
    visit(data['nodes'])


def encode_blocks(iterator):
    nodes = []
    while not iterator.atEnd():
        frame, block = iterator.currentFrame(), iterator.currentBlock()
        if isinstance(frame, QTextTable):
            cells = [[encode_blocks(frame.cellAt(r, c).begin()) for c in range(frame.columns())] for r in range(frame.rows())]
            nodes.append({'type': 'table', 'columns': frame.columns(), 'header': frame.format().headerRowCount(), 'cells': cells})
        elif frame:
            position = frame.frameFormat().position()
            nodes.append({'type': 'frame', 'position': 'left' if position == QTextFrameFormat.Position.FloatLeft else 'right' if position == QTextFrameFormat.Position.FloatRight else 'inline', 'nodes': encode_blocks(frame.begin())})
        elif block.isValid():
            fmt = block.blockFormat()
            node = {'type': 'paragraph', 'alignment': int(fmt.alignment()), 'heading': fmt.headingLevel(), 'runs': []}
            if block.textList():
                node['list'] = block.textList().format().style().value
                node['indent'] = block.textList().format().indent()
                node['check'] = fmt.marker().value
            fragment = block.begin()
            while not fragment.atEnd():
                f = fragment.fragment()
                if f.isValid():
                    char = f.charFormat()
                    run = {'text': f.text(), 'bold': char.fontWeight() >= QFont.Weight.Bold,
                        'italic': char.fontItalic(), 'underline': char.fontUnderline(), 'strike': char.fontStrikeOut()}
                    if char.background().style() != Qt.BrushStyle.NoBrush:
                        run['highlight'] = char.background().color().name()
                    if 6 <= char.fontPointSize() <= 72:
                        run['size'] = char.fontPointSize()
                    if char.isAnchor():
                        run['href'] = char.anchorHref()
                    if char.isImageFormat():
                        im = char.toImageFormat()
                        frame = block.document().objectForFormat(char)
                        position = frame.frameFormat().position() if frame and hasattr(frame, 'frameFormat') else QTextFrameFormat.Position.InFlow
                        run = {'text': '', 'image': {'key': im.name().removeprefix('tabla-asset:'),
                            'width': max(1, im.width()), 'height': max(1, im.height()), 'alt': im.property(QTextImageFormat.Property.ImageAltText) or '',
                            'wrap': 'left' if position == QTextFrameFormat.Position.FloatLeft else 'right' if position == QTextFrameFormat.Position.FloatRight else 'inline'}}
                        run['image']['vertical'] = char.verticalAlignment().value
                    node['runs'].append(run)
                fragment += 1
            nodes.append(node)
        iterator += 1
    return nodes


def decode_nodes(cursor, nodes):
    for index, n in enumerate(nodes):
        kind = n['type']
        if kind == 'paragraph':
            if index and not cursor.block().text() == '' or (index and nodes[index - 1]['type'] == 'paragraph'):
                cursor.insertBlock()
            block = QTextBlockFormat()
            block.setAlignment(Qt.AlignmentFlag(n.get('alignment', 1)))
            block.setHeadingLevel(n.get('heading', 0))
            block.setBottomMargin(7)
            block.setLineHeight(152, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            if n.get('check'):
                block.setMarker(QTextBlockFormat.MarkerType(n['check']))
            cursor.setBlockFormat(block)
            if 'list' in n:
                lf = QTextListFormat()
                lf.setStyle(QTextListFormat.Style(n['list']))
                lf.setIndent(n.get('indent', 1))
                previous = cursor.block().previous()
                if previous.isValid() and previous.textList() and previous.textList().format().style() == lf.style():
                    previous.textList().add(cursor.block())
                else:
                    cursor.createList(lf)
            for run in n['runs']:
                if 'image' in run:
                    image = run['image']
                    fmt = QTextImageFormat()
                    fmt.setName('tabla-asset:' + image['key'])
                    fmt.setWidth(image['width'])
                    fmt.setHeight(image['height'])
                    fmt.setProperty(QTextImageFormat.Property.ImageAltText, image.get('alt', ''))
                    fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment(image.get('vertical', 0)))
                    cursor.insertImage(fmt, {'left': QTextFrameFormat.Position.FloatLeft, 'right': QTextFrameFormat.Position.FloatRight, 'inline': QTextFrameFormat.Position.InFlow}[image.get('wrap', 'inline')])
                else:
                    cf = QTextCharFormat()
                    cf.setFontWeight(QFont.Weight.Bold if run.get('bold') else QFont.Weight.Normal)
                    cf.setFontItalic(bool(run.get('italic')))
                    cf.setFontUnderline(bool(run.get('underline')))
                    cf.setFontStrikeOut(bool(run.get('strike')))
                    if 'size' in run:
                        cf.setFontPointSize(run['size'])
                    if run.get('href'):
                        cf.setAnchor(True)
                        cf.setAnchorHref(run['href'])
                    if run.get('highlight'):
                        cf.setBackground(QColor(run['highlight']))
                    cursor.insertText(run.get('text', ''), cf)
        elif kind == 'table':
            fmt = table_format(n['columns'])
            fmt.setHeaderRowCount(n.get('header', 0))
            table = cursor.insertTable(len(n['cells']), n['columns'], fmt)
            for r, row in enumerate(n['cells']):
                for c, cell in enumerate(row):
                    decode_nodes(table.cellAt(r, c).firstCursorPosition(), cell)
            cursor.setPosition(table.lastPosition() + 1)
        elif kind == 'frame':
            fmt = QTextFrameFormat()
            fmt.setPosition({'left': QTextFrameFormat.Position.FloatLeft, 'right': QTextFrameFormat.Position.FloatRight, 'inline': QTextFrameFormat.Position.InFlow}[n['position']])
            fmt.setMargin(10)
            frame = cursor.insertFrame(fmt)
            decode_nodes(frame.firstCursorPosition(), n['nodes'])
            cursor.setPosition(frame.lastPosition() + 1)


def table_format(columns):
    fmt = QTextTableFormat()
    fmt.setBorder(1)
    fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
    fmt.setBorderBrush(QColor('#92969b'))
    fmt.setCellPadding(6)
    fmt.setCellSpacing(0)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, 100 / columns)] * columns)
    return fmt


class RichNoteEditor(QTextEdit):
    linkActivated = Signal(str)
    filesDropped = Signal(list)
    imagesInserted = Signal(list)
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName('noteEditor')
        self.setAcceptRichText(False)  # Pasted web markup never becomes an external resource.
        from .tokens import prose_font
        self.setFont(prose_font(15))
        self.setStyleSheet('QTextEdit#noteEditor {background:transparent;border:none;padding:6px;font-size:15px;}')
        self.setWordWrapMode(__import__('PySide6.QtGui', fromlist=['QTextOption']).QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(8)
        self.link_targets, self.candidates, self._start = {}, {}, None
        self.completer = QCompleter(self)
        self.model = QStringListModel(self.completer)
        self.completer.setModel(self.model)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.activated.connect(self.insert_link)
        self.template, self.pattern_spacing, self.pattern_strength = 'none', 24, .12
        self._image_cursor = None
        self._resize_drag = None
        self._snap_guide = False
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._check_hits = []
        self._check_hover = -1
        self._check_drag = None

    insert_link = LinkEditor.insert_link
    dragEnterEvent = LinkEditor.dragEnterEvent
    dragMoveEvent = LinkEditor.dragMoveEvent

    def appendPlainText(self, text):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def load_note(self, record):
        self.link_targets = dict(record.get('link_targets', {}))
        for item in record.get('attachments', []):
            if item.get('mime', '').startswith('image/'):
                reader = QImageReader(str(self.store.attachments.path_for(item)))
                reader.setAutoTransform(True)
                sz = reader.size()
                if sz.isValid() and max(sz.width(), sz.height()) > 1440:
                    reader.setScaledSize(sz.scaled(QSize(1440, 1440), Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
                if not image.isNull():
                    self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl('tabla-asset:' + item['key']), image)
        if record.get('document'):
            validate_document(record['document'], record.get('attachments', []))
            self.clear()
            decode_nodes(self.textCursor(), record['document']['nodes'])
        else:
            # Original text is retained in legacy_body on the first actual edit.
            self.setMarkdown(record.get('body', ''))
            # QTextDocument does not understand the application's ==highlight== extension.
        self.set_template(record.get('note_template', 'none'), record.get('pattern_spacing', 24), record.get('pattern_strength', .12))
        self._layout_checklists()
        self.document().clearUndoRedoStacks()
        self.moveCursor(QTextCursor.MoveOperation.Start)

    def snapshot(self):
        return {'version': 1, 'nodes': encode_blocks(self.document().rootFrame().begin())}

    def plain_body(self):
        # Portable searchable text with readable checklist, image and table markers.
        def render(nodes):
            result = []
            previous_list, count = None, 0
            for n in nodes:
                if n['type'] == 'paragraph':
                    text = ''.join('[Image: ' + (r['image'].get('alt') or 'image') + ']' if 'image' in r else r.get('text', '') for r in n['runs'])
                    if n.get('check'):
                        text = ('- [x] ' if n['check'] == QTextBlockFormat.MarkerType.Checked.value else '- [ ] ') + text
                    elif n.get('list'):
                        key = (n['list'], n.get('indent', 1))
                        count = count + 1 if previous_list == key else 1
                        if n['list'] == QTextListFormat.Style.ListDecimal.value:
                            text = str(count) + '. ' + text
                        elif n['list'] == QTextListFormat.Style.ListUpperAlpha.value:
                            number, letters = count, ''
                            while number:
                                number, digit = divmod(number - 1, 26)
                                letters = chr(65 + digit) + letters
                            text = letters + '. ' + text
                        else:
                            text = '• ' + text
                        previous_list = key
                    else:
                        previous_list, count = None, 0
                    result.append(text)
                elif n['type'] == 'table':
                    result.extend('\t'.join(render(cell).replace('\n', ' ').strip() for cell in row) for row in n['cells'])
                else:
                    result.append(render(n['nodes']))
            return '\n'.join(result)
        return render(self.snapshot()['nodes'])

    def toggle_mark(self, mark):
        fmt, old = QTextCharFormat(), self.currentCharFormat()
        if mark == 'bold':
            fmt.setFontWeight(QFont.Weight.Normal if old.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold)
        elif mark == 'italic':
            fmt.setFontItalic(not old.fontItalic())
        elif mark == 'underline':
            fmt.setFontUnderline(not old.fontUnderline())
        elif mark == 'highlight':
            fmt.setBackground(QColor('#8c7633') if old.background().style() == Qt.BrushStyle.NoBrush else Qt.GlobalColor.transparent)
        self.mergeCurrentCharFormat(fmt)
        self.setFocus()

    def add_checklist(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.block().text():
            cursor.insertBlock()
        fmt = QTextListFormat()
        fmt.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(fmt)
        block = cursor.blockFormat()
        block.setMarker(QTextBlockFormat.MarkerType.Unchecked)
        cursor.setBlockFormat(block)
        self._layout_checklists()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setFocus()

    def cycle_list(self):
        """Cycle the current list or selected paragraphs: dots, numbers, letters."""
        styles = (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListDecimal, QTextListFormat.Style.ListUpperAlpha)
        cursor = self.textCursor()
        current = cursor.currentList()
        previous = current.format().style() if current and not self._is_check(cursor.block()) else None
        style = styles[(styles.index(previous) + 1) % len(styles)] if previous in styles else styles[0]
        cursor.beginEditBlock()
        fmt = QTextListFormat()
        fmt.setStyle(style)
        fmt.setIndent(current.format().indent() if current else 1)
        if current and not cursor.hasSelection():
            current.setFormat(fmt)
            blocks = [current.item(i) for i in range(current.count())]
        else:
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            cursor.createList(fmt)
            blocks = []
            block = self.document().findBlock(start)
            while block.isValid() and block.position() <= end:
                blocks.append(block)
                block = block.next()
        for block in blocks:
            target = QTextCursor(block)
            block_format = block.blockFormat()
            block_format.setMarker(QTextBlockFormat.MarkerType.NoMarker)
            target.setBlockFormat(block_format)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self._layout_checklists()
        self.viewport().update()
        self.setFocus()

    @staticmethod
    def _is_check(block):
        return block.isValid() and block.textList() is not None and block.blockFormat().marker() != QTextBlockFormat.MarkerType.NoMarker

    def _layout_checklists(self):
        """Presentation only; markers remain portable in the document format."""
        self.document().setIndentWidth(52)
        block = self.document().begin()
        while block.isValid():
            if self._is_check(block):
                cursor = QTextCursor(block)
                fmt = block.blockFormat()
                fmt.setTopMargin(5)
                fmt.setBottomMargin(5 if self._is_check(block.next()) else 38)
                fmt.setRightMargin(30)
                fmt.setLineHeight(150, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                if fmt != block.blockFormat():
                    cursor.setBlockFormat(fmt)
            block = block.next()

    def _check_action(self, action, position):
        block = self.document().findBlock(position)
        if not self._is_check(block):
            return
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        if action == 'toggle':
            fmt = block.blockFormat()
            fmt.setMarker(QTextBlockFormat.MarkerType.Unchecked if fmt.marker() == QTextBlockFormat.MarkerType.Checked else QTextBlockFormat.MarkerType.Checked)
            cursor.setBlockFormat(fmt)
        elif action == 'add':
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertBlock()
            fmt = cursor.blockFormat()
            fmt.setMarker(QTextBlockFormat.MarkerType.Unchecked)
            cursor.setBlockFormat(fmt)
        elif action == 'remove':
            # Remove the whole row without consuming the following paragraph's format.
            if block.next().isValid():
                cursor.setPosition(block.next().position(), QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            elif block.previous().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.setPosition(block.position() - 1, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            else:
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                block.textList().remove(cursor.block())
                cursor.setBlockFormat(QTextBlockFormat())
        self._layout_checklists()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setFocus()

    def move_checklist_item(self, source, target):
        """Rotate row contents inside one contiguous list, retaining rich runs and undo."""
        first, last = sorted((source, target))
        blocks = []
        block = self.document().findBlock(first)
        while block.isValid() and block.position() <= last:
            if not self._is_check(block):
                return
            blocks.append(block)
            block = block.next()
        if len(blocks) < 2 or blocks[-1].position() != last:
            return
        rows = []
        for block in blocks:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            # Copy inline runs without the source list container: inserting a list
            # fragment directly would create an extra paragraph at each destination.
            temporary = QTextDocument()
            copy = QTextCursor(temporary)
            iterator = block.begin()
            while not iterator.atEnd():
                run = iterator.fragment()
                if run.isValid():
                    copy.insertText(run.text(), run.charFormat())
                iterator += 1
            copy.select(QTextCursor.SelectionType.Document)
            rows.append((QTextDocumentFragment(copy), block.blockFormat().marker()))
        rows.insert(len(rows) - 1 if source < target else 0, rows.pop(0 if source < target else -1))
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for block, (fragment, marker) in reversed(list(zip(blocks, rows))):
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertFragment(fragment)
            fmt = cursor.blockFormat()
            fmt.setMarker(marker)
            cursor.setBlockFormat(fmt)
        edit.endEditBlock()
        self.viewport().update()

    def _paint_checklists(self):
        from .theme import themed_color
        self._check_hits = []
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = self.palette().text().color()
        muted = QColor(ink); muted.setAlpha(145)
        block = self.document().begin()
        while block.isValid():
            if self._is_check(block):
                cursor = QTextCursor(block)
                rect = self.cursorRect(cursor)
                x, y = rect.x(), rect.y() + 2
                if -80 < y < self.viewport().height():
                    # Cover Qt's platform-specific boxed-X marker with a consistent gutter.
                    painter.fillRect(QRectF(x - 51, y - 2, 49, rect.height() + 4), QColor(themed_color('white')))
                    grip = QRectF(x - 49, y - 3, 18, 25)
                    box = QRectF(x - 29, y, 16, 16)
                    remove = QRectF(self.viewport().width() - 27, y - 3, 24, 24)
                    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(muted)
                    for dx in (0, 5):
                        for dy in (0, 5, 10):
                            painter.drawEllipse(QRectF(grip.x() + 5 + dx, y + 2 + dy, 2, 2))
                    checked = block.blockFormat().marker() == QTextBlockFormat.MarkerType.Checked
                    painter.setPen(QPen(muted, 1.5)); painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(box, 2, 2)
                    if checked:
                        painter.setPen(QPen(ink, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        painter.drawLine(QPointF(box.x() + 3, y + 8), QPointF(box.x() + 7, y + 12))
                        painter.drawLine(QPointF(box.x() + 7, y + 12), QPointF(box.x() + 13, y + 4))
                    if self._check_hover == block.position():
                        painter.setPen(QPen(muted, 1.5))
                        painter.drawLine(remove.center() + QPointF(-4, -4), remove.center() + QPointF(4, 4))
                        painter.drawLine(remove.center() + QPointF(-4, 4), remove.center() + QPointF(4, -4))
                    for action, hit in (('drag', grip), ('toggle', box.adjusted(-3, -4, 4, 5)), ('remove', remove)):
                        self._check_hits.append((action, block.position(), hit))
                    if not self._is_check(block.next()):
                        end = QTextCursor(block); end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                        add = QRectF(x - 32, self.cursorRect(end).bottom() + 10, 150, 25)
                        painter.setPen(muted)
                        painter.drawText(add, Qt.AlignmentFlag.AlignVCenter, '+   List item')
                        self._check_hits.append(('add', block.position(), add))
            block = block.next()
        painter.end()

    def insert_table(self, rows=3, columns=3):
        if not 1 <= columns <= 10 or not 1 <= rows <= 2000:
            raise ValueError('Choose 1–10 columns and 1–2000 rows.')
        if self.textCursor().currentTable():
            raise ValueError('Place the caret outside the current table to insert another table.')
        cursor = self.textCursor()
        cursor.beginEditBlock()
        table = cursor.insertTable(rows, columns, table_format(columns))
        cursor.endEditBlock()
        self.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.setFocus()
        return table

    def add_column(self):
        table = self.textCursor().currentTable()
        if table:
            if table.columns() >= 10:
                return False
            table.appendColumns(1)
            table.setFormat(table_format(table.columns()))
        return True

    def insert_images(self, paths):
        imported = self.store.attachments.import_files(paths)
        owner = self.parentWidget()
        existing = getattr(getattr(owner, 'attachments', None), 'items', [])
        if len({a['key'] for a in existing + imported}) > 100:
            raise ValueError('A note supports up to 100 source files.')
        images = []
        for item in imported:
            image = QImage(str(self.store.attachments.path_for(item)))
            if image.isNull() or image.width() * image.height() > 64000000:
                raise ValueError('Choose a valid image of at most 64 megapixels.')
            images.append((item, image))
        # Retain source metadata before any document change triggers autosave.
        self.imagesInserted.emit([item for item, _ in images])
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for item, image in images:
            self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl('tabla-asset:' + item['key']), image)
            fmt = QTextImageFormat()
            fmt.setName('tabla-asset:' + item['key'])
            width = min(max(100, self.viewport().width() - 50), image.width())
            fmt.setWidth(width)
            fmt.setHeight(width * image.height() / image.width())
            fmt.setProperty(QTextImageFormat.Property.ImageAltText, item['name'])
            cursor.insertImage(fmt)
            cursor.insertBlock()
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def image_at_cursor(self):
        cursor = self.textCursor()
        for position in (cursor.position(), cursor.position() - 1):
            if position < 0:
                continue
            selected = QTextCursor(self.document())
            selected.setPosition(position)
            selected.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            if selected.charFormat().isImageFormat():
                return selected
        return None

    def resize_image(self, width):
        cursor = self.image_at_cursor()
        if cursor:
            fmt = self.image_format(cursor)
            ratio = fmt.height() / max(1, fmt.width())
            fmt.setWidth(max(16, min(width, max(16, self.viewport().width() - 32))))
            fmt.setHeight(fmt.width() * ratio)
            cursor.setCharFormat(fmt)
            self.setTextCursor(cursor)
            self.relayout_images()

    def wrap_image(self, mode):
        cursor = self.image_at_cursor()
        if not cursor:
            return
        fmt = cursor.charFormat().toImageFormat()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        cursor.insertImage(fmt, {'left': QTextFrameFormat.Position.FloatLeft,
            'right': QTextFrameFormat.Position.FloatRight, 'inline': QTextFrameFormat.Position.InFlow}[mode])
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.relayout_images()

    def relayout_images(self):
        self.document().markContentsDirty(0, self.document().characterCount())
        self.document().documentLayout().documentSize()
        self.viewport().update()

    def set_template(self, template, spacing=24, strength=.12):
        self.template = template if template in TEMPLATES else 'none'
        self.pattern_spacing = max(16, min(48, spacing))
        self.pattern_strength = max(.04, min(.25, strength))
        self.viewport().update()

    def _pattern_tile(self, template, spacing, strength, ink_rgba, dpr):
        key = (template, spacing, round(strength, 3), ink_rgba, round(dpr, 2))
        if getattr(self, '_pattern_key', None) == key:
            return self._pattern_cache
        tile_w = 65 if template == 'paper' else spacing
        tile_h = 65 if template == 'paper' else spacing
        pm = QPixmap(max(1, round(tile_w * dpr)), max(1, round(tile_h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        color = QColor.fromRgba(ink_rgba)
        color.setAlphaF(strength)
        p.setPen(QPen(color, 0.65))
        if template == 'lines':
            p.drawLine(0, spacing - 1, tile_w, spacing - 1)
        elif template == 'grid':
            p.drawLine(0, spacing - 1, tile_w, spacing - 1)
            p.drawLine(0, 0, 0, tile_h)
        elif template == 'dots':
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(color)
            p.drawEllipse(QRectF(spacing / 2 - 0.75, spacing / 2 - 0.75, 1.5, 1.5))
        elif template == 'diamonds':
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(color)
            cx, cy = spacing / 2, spacing / 2
            p.drawPolygon(QPolygonF([QPointF(cx, cy - 1.4), QPointF(cx + 1.4, cy), QPointF(cx, cy + 1.4), QPointF(cx - 1.4, cy)]))
        elif template == 'paper':
            for y in range(0, tile_h, 5):
                for x in range((y * 7) % 13, tile_w, 13):
                    p.drawPoint(x, y)
        p.end()
        self._pattern_key = key
        self._pattern_cache = pm
        return pm

    def paintEvent(self, event):
        if self.template != 'none':
            painter = QPainter(self.viewport())
            spacing = self.pattern_spacing
            # Lock standard ruled-paper spacing cleanly to the editor's prose line rhythm
            if self.template == 'lines' and spacing == 24:
                spacing = max(18, round(self.fontMetrics().lineSpacing() * 1.52))
            offset = self.verticalScrollBar().value()
            tile = self._pattern_tile(
                self.template,
                spacing,
                self.pattern_strength,
                self.palette().text().color().rgba(),
                self.devicePixelRatioF(),
            )
            mod = 65 if self.template == 'paper' else spacing
            painter.drawTiledPixmap(self.viewport().rect(), tile, QPoint(0, offset % mod))
            painter.end()
        super().paintEvent(event)
        self._paint_checklists()
        selected = self.image_at_cursor()
        if selected:
            rect = self.image_rect(selected)
            p = QPainter(self.viewport())
            p.setPen(QPen(QColor('#2383e2'), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rect)
            p.setBrush(QColor('#2383e2'))
            for point in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
                p.drawRoundedRect(QRectF(point.x() - 3, point.y() - 3, 6, 6), 1, 1)
            if self._snap_guide:
                x = self.viewport().width() // 2
                p.setPen(QPen(QColor('#2383e2'), .7, Qt.PenStyle.DashLine))
                p.drawLine(x, 0, x, self.viewport().height())
            p.end()

    def image_rect(self, cursor):
        fmt = self.image_format(cursor)
        start = QTextCursor(cursor)
        start.setPosition(cursor.selectionStart())
        rect = QRectF(self.cursorRect(start))
        frame = self.document().objectForFormat(fmt)
        if frame and hasattr(frame, 'frameFormat') and frame.frameFormat().position() != QTextFrameFormat.Position.InFlow:
            rect = self.document().documentLayout().frameBoundingRect(frame)
            rect.translate(-self.horizontalScrollBar().value(), -self.verticalScrollBar().value())
        rect.setWidth(fmt.width())
        rect.setHeight(fmt.height())
        return rect

    def image_format(self, cursor):
        # QTextCursor.charFormat intentionally strips ObjectIndex. The fragment
        # retains the floating image frame identity needed by resize/selection.
        position = cursor.selectionStart()
        block = self.document().findBlock(position)
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.position() <= position < fragment.position() + fragment.length():
                return fragment.charFormat().toImageFormat()
            iterator += 1
        return cursor.charFormat().toImageFormat()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for action, position, rect in self._check_hits:
                if rect.contains(event.position()):
                    if action == 'drag':
                        self._check_drag = position
                    else:
                        self._check_action(action, position)
                    event.accept()
                    return
        cursor = self.image_at_cursor()
        if cursor and event.button() == Qt.MouseButton.LeftButton:
            rect = self.image_rect(cursor)
            if any((event.position() - point).manhattanLength() < 12 for point in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight())):
                cursor.beginEditBlock()
                self._resize_drag = (cursor, rect.topLeft(), rect.width(), rect.height())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        block = self.cursorForPosition(event.position().toPoint()).block()
        hover = block.position() if self._is_check(block) else -1
        for _, position, rect in self._check_hits:
            if rect.contains(event.position()):
                hover = position
                break
        if hover != self._check_hover:
            self._check_hover = hover
            self.viewport().update()
        if self._check_drag is not None:
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        over_grip = any(action == 'drag' and rect.contains(event.position()) for action, _, rect in self._check_hits)
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if over_grip else Qt.CursorShape.IBeamCursor)
        if self._resize_drag:
            cursor, top_left, width, height = self._resize_drag
            new_width = max(16, event.position().x() - top_left.x())
            available = max(16, self.viewport().width() - 32)
            self._snap_guide = not event.modifiers() & Qt.KeyboardModifier.AltModifier and abs(new_width - available / 2) < 8
            if self._snap_guide:
                new_width = available / 2
            fmt = self.image_format(cursor)
            fmt.setWidth(min(available, new_width))
            fmt.setHeight(fmt.width() * height / max(1, width))
            cursor.setCharFormat(fmt)
            self.setTextCursor(cursor)
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        if self._is_check(cursor.block()) and event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Space:
            self._check_action('toggle', cursor.block().position())
            return
        if self._is_check(cursor.block()) and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers():
            cursor.beginEditBlock()
            if not cursor.block().text():
                cursor.block().textList().remove(cursor.block())
                cursor.setBlockFormat(QTextBlockFormat())
            else:
                cursor.insertBlock()
                fmt = cursor.blockFormat(); fmt.setMarker(QTextBlockFormat.MarkerType.Unchecked)
                cursor.setBlockFormat(fmt)
            self._layout_checklists()
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        if self._is_check(cursor.block()) and event.modifiers() == Qt.KeyboardModifier.AltModifier and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            other = cursor.block().previous() if event.key() == Qt.Key.Key_Up else cursor.block().next()
            if self._is_check(other):
                self.move_checklist_item(cursor.block().position(), other.position())
                self.setTextCursor(QTextCursor(other))
            return
        if event.key() == Qt.Key.Key_Space and not event.modifiers() and not self._is_check(cursor.block()):
            prefix = cursor.block().text()[:cursor.positionInBlock()]
            if prefix in ('#', '##', '###', '-', '*', '1.', '[]', '[ ]'):
                cursor.beginEditBlock()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                if prefix in ('#', '##', '###'):
                    level = len(prefix)
                    bf = cursor.blockFormat()
                    bf.setHeadingLevel(level)
                    cursor.setBlockFormat(bf)
                    cf = QTextCharFormat()
                    cf.setFontWeight(QFont.Weight.DemiBold)
                    cf.setFontPointSize({1: 18, 2: 15, 3: 13.5}[level])
                    cursor.setCharFormat(cf)
                    self.setTextCursor(cursor)
                    cursor.endEditBlock()
                    return
                if prefix in ('-', '*', '1.'):
                    lf = QTextListFormat()
                    lf.setStyle(QTextListFormat.Style.ListDecimal if prefix == '1.' else QTextListFormat.Style.ListDisc)
                    cursor.createList(lf)
                    self.setTextCursor(cursor)
                    cursor.endEditBlock()
                    return
                if prefix in ('[]', '[ ]'):
                    cursor.endEditBlock()
                    self.add_checklist()
                    return
        for sequence, mark in (('Ctrl+B', 'bold'), ('Ctrl+I', 'italic'), ('Ctrl+U', 'underline')):
            if QKeySequence(event.keyCombination()) == QKeySequence(sequence):
                self.toggle_mark(mark)
                return
        if self.completer.popup().isVisible() and event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab):
            event.ignore()
            return
        super().keyPressEvent(event)
        cursor = self.textCursor()
        before = self.toPlainText()[:cursor.position()]
        start = before.rfind('[[')
        text = before[start + 2:] if start >= 0 else ''
        if start >= 0 and ']' not in text and '\n' not in text and len(text) <= 80:
            self._start = start + 2
            items = self.store.link_candidates(text)
            self.candidates = {f'{r["title"]} · {r["kind"]} · {r["id"][:6]}': r for r in items}
            self.model.setStringList(sorted(self.candidates))
            self.completer.setCompletionPrefix(text)
            if self.completer.completionCount():
                rect = self.cursorRect()
                rect.setWidth(320)
                self.completer.complete(rect)
        else:
            self.completer.popup().hide()

    def mouseReleaseEvent(self, event):
        if self._check_drag is not None:
            source, self._check_drag = self._check_drag, None
            self.viewport().unsetCursor()
            self.move_checklist_item(source, self.cursorForPosition(event.position().toPoint()).block().position())
            return
        if self._resize_drag:
            self._resize_drag[0].endEditBlock()
            self._resize_drag = None
            self._snap_guide = False
            self.viewport().update()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            cursor = self.cursorForPosition(event.position().toPoint())
            for match in re.finditer(r'\[\[([^\]]+)\]\]', cursor.block().text()):
                if match.start() <= cursor.positionInBlock() <= match.end():
                    self.linkActivated.emit(match[1])
                    return
        super().mouseReleaseEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            image_paths = [p for p in paths if Path(p).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif')]
            try:
                if image_paths:
                    self.insert_images(image_paths)
                other = [p for p in paths if p not in image_paths]
                if other:
                    self.filesDropped.emit(other)
                event.acceptProposedAction()
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, 'Could not insert image', str(exc))
        else:
            super().dropEvent(event)

    def insertFromMimeData(self, source):
        if source.hasImage():
            import tempfile
            image = QImage(source.imageData())
            with tempfile.TemporaryDirectory() as folder:
                path = str(Path(folder) / 'Pasted image.png')
                if image.save(path):
                    self.insert_images([path])
        else:
            self.textCursor().insertText(source.text())

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        table = self.textCursor().currentTable()
        if table:
            menu.addAction('Add row', lambda: table.appendRows(1))
            action = menu.addAction('Add column (maximum 10)', self.add_column)
            action.setEnabled(table.columns() < 10)
            menu.addAction('Use first row as header', lambda: self.set_table_header(table))
            menu.addAction('Remove current row…', lambda: self.remove_table_part(table, 'row'))
            menu.addAction('Remove current column…', lambda: self.remove_table_part(table, 'column'))
        if self.image_at_cursor():
            menu.addAction('Resize image…', self.image_size_dialog)
            for title, mode in (('Inline image', 'inline'), ('Wrap text · image left', 'left'), ('Wrap text · image right', 'right')):
                menu.addAction(title, lambda checked=False, m=mode: self.wrap_image(m))
            for title, alignment in (('Align image left', Qt.AlignmentFlag.AlignLeft), ('Center image', Qt.AlignmentFlag.AlignHCenter), ('Align image right', Qt.AlignmentFlag.AlignRight)):
                menu.addAction(title, lambda checked=False, a=alignment: self.setAlignment(a))
            for title, alignment in (('Vertical · top', QTextCharFormat.VerticalAlignment.AlignTop), ('Vertical · middle', QTextCharFormat.VerticalAlignment.AlignMiddle), ('Vertical · bottom', QTextCharFormat.VerticalAlignment.AlignBottom)):
                menu.addAction(title, lambda checked=False, a=alignment: self.align_image_vertically(a))
            menu.addAction('Image description…', self.describe_image)
        menu.exec(event.globalPos())

    def image_size_dialog(self):
        cursor = self.image_at_cursor()
        if cursor:
            width, ok = QInputDialog.getInt(self, 'Image size', 'Width in pixels (aspect ratio is preserved)', int(cursor.charFormat().toImageFormat().width()), 16, 20000)
            if ok:
                self.resize_image(width)

    def align_image_vertically(self, alignment):
        cursor = self.image_at_cursor()
        if cursor:
            fmt = self.image_format(cursor)
            fmt.setVerticalAlignment(alignment)
            cursor.setCharFormat(fmt)

    def describe_image(self):
        cursor = self.image_at_cursor()
        if cursor:
            fmt = self.image_format(cursor)
            text, ok = QInputDialog.getText(self, 'Image description', 'Description used by plain-text exports', text=fmt.property(QTextImageFormat.Property.ImageAltText) or '')
            if ok:
                fmt.setProperty(QTextImageFormat.Property.ImageAltText, text)
                cursor.setCharFormat(fmt)

    def set_table_header(self, table):
        fmt = table.format()
        fmt.setHeaderRowCount(0 if fmt.headerRowCount() else 1)
        table.setFormat(fmt)

    def remove_table_part(self, table, part):
        cell = table.cellAt(self.textCursor())
        cells = [table.cellAt(cell.row(), c) for c in range(table.columns())] if part == 'row' else [table.cellAt(r, cell.column()) for r in range(table.rows())]
        def content(c):
            cursor = c.firstCursorPosition()
            cursor.setPosition(c.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
            return cursor.selectedText().strip()
        if any(content(c) for c in cells) and QMessageBox.question(self, 'Remove ' + part, 'This ' + part + ' contains content. Remove it?') != QMessageBox.StandardButton.Yes:
            return
        if part == 'row':
            table.removeRows(cell.row(), 1)
        else:
            table.removeColumns(cell.column(), 1)
            if table.columns():
                table.setFormat(table_format(table.columns()))
