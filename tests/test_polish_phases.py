import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextBlockFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.tokens import DAYLIGHT, OBSIDIAN, build_stylesheet, current_tokens
from tabla.spring import SpringAnimation, SILKY, SNAPPY, TACTILE, evaluate_step, evaluate_impulse
from tabla.foley import _synth_wav, enabled as foley_enabled, set_enabled as set_foley_enabled
from tabla.rich_document import RichNoteEditor
from tabla.widgets import SegmentedSwitch
from tabla.polish import set_reduced_motion


class PolishPhasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_semantic_tokens_and_clean_stylesheet(self):
        assets = Path(__file__).resolve().parent.parent / "assets"
        light_qss = build_stylesheet(False, assets)
        dark_qss = build_stylesheet(True, assets)
        self.assertIn(DAYLIGHT.bg_canvas, light_qss)
        self.assertIn(OBSIDIAN.bg_canvas, dark_qss)
        self.assertNotIn("Alegreya", light_qss)
        self.assertNotIn("Alegreya", dark_qss)

    def test_spring_math_settles_cleanly(self):
        for preset in (SNAPPY, TACTILE, SILKY):
            self.assertEqual(evaluate_step(0.0, preset), 0.0)
            self.assertAlmostEqual(evaluate_step(1.5, preset), 1.0, places=2)
            self.assertAlmostEqual(evaluate_impulse(1.5, preset), 0.0, places=2)
        set_reduced_motion(True)
        try:
            anim = SpringAnimation(SILKY, 240)
            self.assertEqual(anim.duration(), 1)
        finally:
            set_reduced_motion(False)

    def test_procedural_foley_synthesizes_valid_wav_headers(self):
        for mat in ("click", "pop", "pluck", "brass"):
            wav = _synth_wav(mat)
            self.assertTrue(wav.startswith(b"RIFF"))
            self.assertIn(b"WAVE", wav[:16])
            self.assertGreater(len(wav), 200)
        set_foley_enabled(True)
        # Offscreen platform never emits audio even when toggled on
        self.assertFalse(foley_enabled())
        set_foley_enabled(False)

    def test_live_markdown_shortcuts_and_fast_link_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "tabla.sqlite3")
            try:
                store.save({"kind": "note", "title": "Design System", "body": "Notes"})
                store.save({"kind": "task", "title": "Ship Polish", "body": "Work"})
                hits = store.link_candidates("Design")
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["title"], "Design System")
                self.assertEqual(set(hits[0].keys()), {"id", "title", "kind"})

                editor = RichNoteEditor(store)
                editor.show()
                QTest.keyClicks(editor, "# ")
                self.assertEqual(editor.textCursor().blockFormat().headingLevel(), 1)
                editor.clear()
                QTest.keyClicks(editor, "[] ")
                self.assertEqual(editor.textCursor().blockFormat().marker(), QTextBlockFormat.MarkerType.Unchecked)
                editor.close()
                editor.deleteLater()
            finally:
                store.close()

    def test_board_toolbar_clarity_and_idle_pulse_gated(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "tabla.sqlite3")
            store.seed_demo()
            win = TablaWindow(store, defer_render=True)
            win.resize(1280, 800)
            win.navigate("My Tasks")
            try:
                self.assertFalse(win.pulse.isActive())
                self.assertEqual(win.boards_toggle.text(), "Boards")
                switches = win.workspace.findChildren(SegmentedSwitch)
                self.assertGreaterEqual(len(switches), 1)
                self.assertEqual(set(switches[0].buttons.keys()), {"Board", "Table"})
                # Check tactile sound preference persistence
                win.set_tactile_sound(True)
                self.assertTrue(store.setting("tactile_sound"))
                win.set_tactile_sound(False)
                self.assertFalse(store.setting("tactile_sound"))
            finally:
                win.close()
                store.close()

    def test_theme_presets_and_focus_numeral_display(self):
        from tabla.tokens import THEME_PRESETS, current_tokens, display_numeral_font
        from tabla.widgets import ThemePresetCard, CountdownDisplay
        self.assertGreaterEqual(len(THEME_PRESETS), 8)
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "tabla.sqlite3")
            win = TablaWindow(store, defer_render=True)
            win.resize(1280, 820)
            try:
                win.navigate("Settings")
                cards = win.workspace.findChildren(ThemePresetCard)
                self.assertEqual(len(cards), len(THEME_PRESETS))
                for preset in THEME_PRESETS:
                    win.set_appearance(preset.key)
                    self.assertEqual(store.setting("appearance"), preset.key)
                    self.assertEqual(current_tokens().key, preset.key)
                    self.assertEqual(bool(self.app.property("tablaDark")), preset.dark)
                # Backwards compatibility with Light / Dark strings
                win.set_appearance("Dark")
                self.assertEqual(current_tokens().key, "dark")
                win.set_appearance("Light")
                self.assertEqual(current_tokens().key, "light")
                # Focus countdown uses QSS-immune tabular display widget
                win.navigate("Focus")
                self.assertIsInstance(win.countdown, CountdownDisplay)
                self.assertRegex(win.countdown.text(), r"^\d{2}:\d{2}$")
                f = display_numeral_font(92)
                self.assertEqual(f.pixelSize(), 92)
            finally:
                win.close()
                store.close()

    def test_chatgpt_table_paste_and_ux_cleanup(self):
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QTextTable
        from PySide6.QtWidgets import QPushButton, QLabel
        from tabla.rich_document import RichNoteEditor, validate_document
        from tabla.spring import HighRefreshSpring

        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "tabla.sqlite3")
            store.seed_demo()
            # 1. Markdown pipe table paste (e.g. ChatGPT Copy button)
            editor = RichNoteEditor(store)
            md_mime = QMimeData()
            md_mime.setText("Summary:\n| Feature | Status |\n| --- | --- |\n| Tables | **Ready** |\n| Themes | Live |")
            editor.insertFromMimeData(md_mime)
            doc = editor.snapshot()
            validate_document(doc, [])
            tables = [n for n in doc["nodes"] if n["type"] == "table"]
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]["columns"], 2)
            self.assertEqual(tables[0]["header"], 1)
            self.assertEqual(len(tables[0]["cells"]), 3)

            # 2. HTML table paste (e.g. selecting rendered ChatGPT table)
            editor2 = RichNoteEditor(store)
            html_mime = QMimeData()
            html_mime.setHtml("<table><thead><tr><th>Item</th><th>Score</th></tr></thead><tbody><tr><td>Motion</td><td>60fps</td></tr></tbody></table>")
            html_mime.setText("Item\tScore\nMotion\t60fps")
            editor2.insertFromMimeData(html_mime)
            doc2 = editor2.snapshot()
            validate_document(doc2, [])
            tables2 = [n for n in doc2["nodes"] if n["type"] == "table"]
            self.assertEqual(len(tables2), 1)
            self.assertEqual(tables2[0]["columns"], 2)
            self.assertEqual(tables2[0]["header"], 1)
            self.assertEqual(len(tables2[0]["cells"]), 2)
            editor.deleteLater()
            editor2.deleteLater()

            # 3. High-refresh PreciseTimer spring
            driver = HighRefreshSpring(duration_ms=180)
            self.assertEqual(driver._timer.interval(), 8)

            # 4. UX cleanup: no eyebrow, no projects folder, Quick note only on Home, grid-only Notes, narrow vertical
            win = TablaWindow(store, defer_render=True)
            win.resize(1280, 820)
            try:
                win.navigate("Today")
                self.assertIsNone(win._projects_btn)
                labels = [l.text() for l in win.workspace.findChildren(QLabel)]
                self.assertFalse(any("Personal workspace" in txt for txt in labels))
                btn_texts = [b.text() for b in win.workspace.findChildren(QPushButton)]
                self.assertIn("Quick note", btn_texts)

                for page in ("Calendar", "My Tasks", "Notes", "Focus"):
                    win.navigate(page)
                    self.app.processEvents()
                    btn_texts = [b.text() for b in win.workspace.findChildren(QPushButton) if not b.isHidden()]
                    self.assertNotIn("Quick note", btn_texts, f"Quick note should not appear on {page}")
                    if page == "Notes":
                        self.assertNotIn("List", btn_texts)
                        self.assertNotIn("Grid", btn_texts)
                    if page == "My Tasks":
                        self.assertTrue(any(b.accessibleName() == "Board options" and not b.isHidden() for b in win.workspace.findChildren(QPushButton)))

                # Narrow vertical 20% laptop strip layout
                win.resize(380, 820)
                win.navigate("Today")
                self.assertEqual(win.width(), 380)
            finally:
                win.close()
                store.close()

    def test_checklist_uncheck_doubleclick_and_lifted_drag_pixmap(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QTextBlockFormat, QPixmap, QColor
        from PySide6.QtTest import QTest
        from tabla.dialogs import NoteDialog
        from tabla.task_board import _lifted_drag_pixmap
        from tabla.theme import navigation_icon

        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "tabla.sqlite3")
            rec = store.save({
                "kind": "note",
                "title": "Report",
                "color": "blue",
                "body": "Notes:\n\n- [x] Task one\n- [x] Task two",
            })
            dlg = NoteDialog(store, rec)
            dlg.show()
            self.app.processEvents()
            dlg.grab()
            ed = dlg.editor
            try:
                hits = ed._compute_check_hits()
                toggle_hit = next(h for h in hits if h[0] == "toggle")
                _, pos, rect = toggle_hit
                self.assertEqual(ed.document().findBlock(pos).blockFormat().marker(), QTextBlockFormat.MarkerType.Checked)
                # Click unchecks
                QTest.mouseClick(ed.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
                self.app.processEvents()
                self.assertEqual(ed.document().findBlock(pos).blockFormat().marker(), QTextBlockFormat.MarkerType.Unchecked)
                # Fast double-click toggles cleanly too
                QTest.mouseDClick(ed.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
                self.app.processEvents()
                self.assertEqual(ed.document().findBlock(pos).blockFormat().marker(), QTextBlockFormat.MarkerType.Checked)
                # Lifted drag preview pixmap
                pm = QPixmap(180, 72)
                pm.fill(QColor("#ffffff"))
                lifted, offset = _lifted_drag_pixmap(pm)
                self.assertFalse(lifted.isNull())
                self.assertGreater(lifted.width(), pm.width())
                # Unified nav icons render cleanly for both active and inactive states
                self.assertFalse(navigation_icon("home", active=True, dark=True).isNull())
                self.assertFalse(navigation_icon("home", active=False, dark=True).isNull())
            finally:
                dlg.close()
                store.close()


if __name__ == "__main__":
    unittest.main()
