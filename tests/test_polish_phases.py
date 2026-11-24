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


if __name__ == "__main__":
    unittest.main()
