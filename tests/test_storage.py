import json
import tempfile
import unittest
from pathlib import Path
from tabla.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path / "test.sqlite3")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_saved_items_survive_reopen_with_outbox(self):
        task = self.store.save({"kind": "task", "title": "Keep my work", "status": "To do"})
        self.store.close()
        self.store = Store(self.path / "test.sqlite3")
        self.assertEqual(self.store.get(task["id"])["title"], "Keep my work")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)

    def test_links_survive_rename_trash_and_restore(self):
        target = self.store.save({"kind": "note", "title": "Research"})
        source = self.store.save({"kind": "note", "title": "Plan", "body": "Read [[Research]]"})
        target["title"] = "Research renamed"
        self.store.save(target)
        source["body"] += " tomorrow"
        self.store.save(source)
        self.assertEqual(self.store.resolve("Research", source["id"])["id"], target["id"])
        target["deleted"] = True
        self.store.save(target)
        self.assertEqual(len(self.store.backlinks(target["id"])), 1)
        target["deleted"] = False
        self.store.save(target)
        self.assertEqual(self.store.resolve("Research", source["id"])["title"], "Research renamed")

    def test_unresolved_target_resolves_later_and_duplicate_titles_stay_unresolved(self):
        source = self.store.save({"kind": "note", "title": "Plan", "body": "[[Future]]"})
        target = self.store.save({"kind": "note", "title": "Future"})
        self.assertEqual(self.store.resolve("Future", source["id"])["id"], target["id"])
        self.store.save({"kind": "note", "title": "Duplicate"})
        self.store.save({"kind": "task", "title": "Duplicate"})
        self.assertIsNone(self.store.resolve("Duplicate"))

    def test_archive_and_trash_not_in_active_search(self):
        note = self.store.save({"kind": "note", "title": "Needle", "body": "reference", "labels": "important"})
        self.assertEqual(len(self.store.records(query="import")), 1)
        note["archived"] = True
        self.store.save(note)
        self.assertEqual(self.store.records(query="Needle"), [])
        self.assertEqual(len(self.store.records(state="archive")), 1)
        note["deleted"] = True
        self.store.save(note)
        self.assertEqual(len(self.store.records(state="trash")), 1)
        self.assertEqual(self.store.records(query='" OR * --', state="all"), [])

    def test_roundtrip_preserves_ids_and_renamed_links(self):
        note = self.store.save({"kind": "note", "title": "Old name"})
        source = self.store.save({"kind": "task", "title": "Task", "body": "[[Old name]]"})
        note["title"] = "New name"
        self.store.save(note)
        export = self.path / "backup.json"
        self.store.export_file(export)
        target = Store(self.path / "other.sqlite3")
        try:
            self.assertEqual(target.import_file(export), (2, 0))
            self.assertEqual(target.resolve("Old name", source["id"])["id"], note["id"])
            self.assertEqual(target.import_file(export), (0, 0))
        finally:
            target.close()

    def test_import_conflicts_keep_existing_and_remap_relationships(self):
        p = self.store.save({"kind": "project", "title": "Project"})
        n = self.store.save({"kind": "note", "title": "Ideas", "project": p["id"]})
        s = self.store.save({"kind": "task", "title": "Write", "body": "[[Ideas]]", "project": p["id"]})
        export = self.path / "old.json"
        self.store.export_file(export)
        n["body"] = "New local work"
        self.store.save(n)
        count, copies = self.store.import_file(export)
        self.assertEqual((count, copies), (1, 1))
        self.assertEqual(self.store.get(n["id"])["body"], "New local work")
        self.assertEqual(len(self.store.records("note")), 2)

    def test_invalid_import_is_atomic(self):
        self.store.save({"kind": "note", "title": "Existing"})
        export = self.path / "broken.json"
        export.write_text(json.dumps({"app": "tabla", "schema_version": 1, "items": [
            {"id": "okay", "kind": "note", "title": "Good", "revision": 1, "created_at": "2026-10-21", "updated_at": "2026-10-21"},
            {"id": "broken", "kind": "unknown"}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.import_file(export)
        self.assertEqual(len(self.store.records()), 1)

    def test_backup_does_not_overwrite_database_and_preferences_roundtrip(self):
        with self.assertRaises(ValueError):
            self.store.export_file(self.store.path)
        self.store.set_setting("focus_minutes", 35)
        export = self.path / "settings.json"
        self.store.export_file(export)
        self.store.set_setting("focus_minutes", 25)
        self.store.import_file(export)
        self.assertEqual(self.store.setting("focus_minutes"), 35)

    def test_failed_outbox_write_rolls_back_content(self):
        self.store.db.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END")
        self.store.db.commit()
        with self.assertRaises(Exception):
            self.store.save({"kind": "note", "title": "Must not be acknowledged"})
        self.assertEqual(self.store.records(), [])


if __name__ == "__main__":
    unittest.main()
