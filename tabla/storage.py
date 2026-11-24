"""UI-independent SQLite model and versioned portable data interchange.

The outbox is a future synchronization boundary, not an active Firebase client.
No networking or account credentials are used in this desktop release.
"""
from __future__ import annotations

import copy
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .attachments import AttachmentVault, validate_metadata

KINDS = {"task", "note", "project", "event", "block", "session", "board"}
LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.attachments = AttachmentVault(self.path.parent / 'attachments')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._transaction_depth = 0
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL
          );
          CREATE INDEX IF NOT EXISTS records_kind ON records(kind, deleted, archived);
          CREATE INDEX IF NOT EXISTS records_board ON records(json_extract(payload, '$.board')) WHERE kind='task';
          CREATE INDEX IF NOT EXISTS records_project ON records(json_extract(payload, '$.project'));
          CREATE TABLE IF NOT EXISTS links (
            source TEXT NOT NULL, token TEXT NOT NULL, target TEXT NOT NULL,
            PRIMARY KEY(source, token)
          );
          CREATE INDEX IF NOT EXISTS links_target ON links(target);
          CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outbox (
            operation_id TEXT PRIMARY KEY, record_id TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL
          );
          CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(id UNINDEXED, title, body);
          PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def atomic(self):
        if self._transaction_depth:
            yield
            return
        self._transaction_depth += 1
        try:
            with self.db:
                yield
        finally:
            self._transaction_depth -= 1

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.atomic():
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def get(self, record_id):
        row = self.db.execute("SELECT payload FROM records WHERE id=?", (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def records(self, kind=None, project=None, state="active", query="", board=None, limit=None):
        sql, args = "SELECT payload FROM records WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if project is not None:
            sql += " AND json_extract(payload, '$.project')=?"
            args.append(project)
        if board is not None:
            sql += " AND json_extract(payload, '$.board')=?"
            args.append(board)
        if state == "trash":
            sql += " AND deleted=1"
        elif state == "archive":
            sql += " AND deleted=0 AND archived=1"
        elif state != "all":
            sql += " AND deleted=0 AND archived=0"
        else:
            sql += " AND deleted=0"
        if query.strip():
            # Quoted terms are literal FTS input; user punctuation is never SQL syntax.
            terms = re.findall(r"\w+", query, re.UNICODE)
            if terms:
                expression = " AND ".join('"' + term.replace('"', '""') + '"*' for term in terms)
                sql += " AND id IN (SELECT id FROM search_index WHERE search_index MATCH ?)"
                args.append(expression)
            else:
                sql += " AND (title LIKE ? OR body LIKE ?)"
                args.extend([f"%{query}%", f"%{query}%"])
        sql += " ORDER BY updated_at DESC, id"
        if limit is not None:
            if type(limit) is not int or limit < 1:
                raise ValueError('Record limit must be a positive integer.')
            sql += " LIMIT ?"
            args.append(limit)
        result = [json.loads(row[0]) for row in self.db.execute(sql, args)]
        return result

    def link_candidates(self, prefix="", kinds=None, limit=80):
        """Fast SQL-only projection for [[wiki-link]] autocomplete without JSON parsing."""
        sql = "SELECT id, title, kind FROM records WHERE deleted=0"
        args = []
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            sql += f" AND kind IN ({placeholders})"
            args.extend(kinds)
        else:
            sql += " AND kind!='session'"
        if prefix:
            sql += " AND title LIKE ? COLLATE NOCASE"
            args.append(f"%{prefix}%")
        sql += " ORDER BY updated_at DESC, id LIMIT ?"
        args.append(int(limit))
        return [{"id": r[0], "title": r[1], "kind": r[2]} for r in self.db.execute(sql, args)]

    def save(self, record):
        record = copy.deepcopy(record)
        if record.get('kind') == 'board':
            from .board_model import validate_board
            validate_board(record.get('workflow'))
        if record.get('kind') == 'task' and self.setting('multi_board_schema') == 1:
            from .boards import BoardCatalog
            BoardCatalog(self).assign(record)
        validate_metadata(record.get('attachments', []))
        self.validate_note_fields(record)
        if record.get('kind') == 'task':
            from .board_model import validate_card
            validate_card(record)
        if record.get("kind") not in KINDS:
            raise ValueError("Unsupported item type")
        record["title"] = str(record.get("title", "")).strip() or "Untitled"
        record["body"] = str(record.get("body", ""))
        tokens = set(LINK_RE.findall(record["body"]))
        if "link_targets" in record:
            record["link_targets"] = {token: target for token, target in record["link_targets"].items() if token in tokens}
        record.setdefault("id", str(uuid.uuid4()))
        previous = self.get(record["id"])
        if record.get('kind') == 'task' and record.get('board') and self.setting('multi_board_schema') == 1:
            from .board_model import BoardModel
            BoardModel(self, record['board']).route_completion(record, previous)
        if previous and not previous.get('document') and record.get('document'):
            recovery = self.path.with_name('before-rich-notes.sqlite3')
            if not recovery.exists():
                self.backup(recovery)
        record["created_at"] = previous["created_at"] if previous else record.get("created_at", now())
        record["updated_at"] = now()
        record["revision"] = (previous or {}).get("revision", 0) + 1
        record.setdefault("archived", False)
        record.setdefault("deleted", False)
        record.setdefault("schema_version", 1)
        with self.atomic():
            self._write(record)
            self._index_links(record, resolve_pending=previous is None or previous['title'] != record['title'])
            operation = str(uuid.uuid4())
            self.db.execute("INSERT INTO outbox VALUES (?,?,?,?)", (
                operation, record["id"], json.dumps(record, ensure_ascii=False), now()))
        return self.get(record["id"])

    def _write(self, record):
        payload = json.dumps(record, ensure_ascii=False)
        self.db.execute("""INSERT OR REPLACE INTO records
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (
            record["id"], record["kind"], record["title"], record.get("body", ""), payload,
            int(record.get("archived", False)), int(record.get("deleted", False)),
            record["created_at"], record["updated_at"], record["revision"]))
        self.db.execute("DELETE FROM search_index WHERE id=?", (record["id"],))
        self.db.execute("INSERT INTO search_index VALUES (?,?,?)", (
            record["id"], record["title"], record.get("body", "") + " " + (record.get("labels") or "")))

    @staticmethod
    def validate_note_fields(record):
        if record.get('document') is not None:
            from .rich_document import validate_document
            validate_document(record['document'], record.get('attachments', []))
        if record.get('note_template', 'none') not in ('none', 'lines', 'dots', 'grid', 'paper', 'diamonds'):
            raise ValueError('Invalid note background.')
        if type(record.get('pattern_spacing', 24)) is not int or not 16 <= record.get('pattern_spacing', 24) <= 48:
            raise ValueError('Invalid note pattern spacing.')
        strength = record.get('pattern_strength', .12)
        if type(strength) not in (int, float) or not .04 <= strength <= .25:
            raise ValueError('Invalid note pattern strength.')

    def resolve(self, token, source=None):
        # Retain an established target across rename and delete/restore.
        if source:
            row = self.db.execute("SELECT target FROM links WHERE source=? AND token=?", (source, token)).fetchone()
            if row:
                target = self.get(row[0])
                if target:
                    return target
        direct = self.get(token)
        if direct:
            return direct
        matches = self.db.execute("""SELECT payload FROM records
            WHERE title=? COLLATE NOCASE AND kind IN ('note','task','project','event','block') AND deleted=0""", (token,)).fetchall()
        return json.loads(matches[0][0]) if len(matches) == 1 else None

    def _index_links(self, record, resolve_pending=True):
        tokens = set(LINK_RE.findall(record.get("body", "")))
        saved = []
        for token in tokens:
            target = self.get(record.get("link_targets", {}).get(token)) or self.resolve(token, record["id"])
            if target:
                saved.append((record["id"], token, target["id"]))
        self.db.execute("DELETE FROM links WHERE source=?", (record["id"],))
        self.db.executemany("INSERT INTO links VALUES (?,?,?)", saved)
        if not resolve_pending:
            return
        # Resolve earlier missing links when a uniquely named target is created.
        for row in self.db.execute("SELECT payload FROM records WHERE deleted=0 AND id<>? AND instr(body, '[[')>0", (record["id"],)).fetchall():
            source = json.loads(row[0])
            for token in set(LINK_RE.findall(source.get("body", ""))):
                if token.casefold() == record["title"].casefold():
                    existing = self.db.execute("SELECT 1 FROM links WHERE source=? AND token=?", (source["id"], token)).fetchone()
                    if not existing and self.resolve(token):
                        self.db.execute("INSERT INTO links VALUES (?,?,?)", (source["id"], token, record["id"]))

    def backlinks(self, target):
        rows = self.db.execute("""SELECT DISTINCT r.payload FROM records r JOIN links l ON r.id=l.source
            WHERE l.target=? AND r.deleted=0 ORDER BY r.updated_at DESC""", (target,))
        return [json.loads(row[0]) for row in rows]

    def toggle_task(self, record_id, completed):
        record = self.get(record_id)
        if record and record["kind"] == "task":
            record["status"] = "Done" if completed else "To do"
            return self.save(record)

    def backup(self, path):
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def export_file(self, path):
        path = Path(path)
        if path.suffix.lower() != ".json" or path.resolve() == self.path.resolve():
            raise ValueError("Choose a .json backup file, separate from your workspace database.")
        data = {
            "app": "tabla", "schema_version": 2 if self.setting('multi_board_schema') == 1 or self.records('board', state='all') else 1, "exported_at": now(),
            "items": [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM records ORDER BY id")],
            "links": [dict(row) for row in self.db.execute("SELECT * FROM links ORDER BY source,token")],
            "preferences": {key: self.setting(key) for key in ("focus_minutes", "short_minutes", "long_minutes", "long_interval", "task_board")},
        }
        data['attachment_files'] = self.attachments.pack(data['items'])
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def import_file(self, path):
        if Path(path).stat().st_size > 200 * 1024 * 1024:
            raise ValueError("This import is too large (maximum 200 MB including attachments).")
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("app") != "tabla" or data.get("schema_version") not in (1, 2):
            raise ValueError("Choose a Tabla version 1 JSON export.")
        items = data.get("items")
        if not isinstance(items, list) or len(items) > 100000:
            raise ValueError("Invalid item list.")
        checked, seen = [], set()
        for r in items:
            if not isinstance(r, dict) or r.get("kind") not in KINDS:
                raise ValueError("The export contains an invalid item.")
            if not isinstance(r.get("id"), str) or not r["id"] or r["id"] in seen:
                raise ValueError("Invalid or duplicate item ID.")
            seen.add(r["id"])
            if not isinstance(r.get("title"), str) or not isinstance(r.get("body", ""), str):
                raise ValueError("An item has invalid text.")
            for field in ("project", "task", "parent", "labels", "color", "status", "priority", "time", "end_time", "date"):
                if r.get(field) is not None and not isinstance(r[field], str):
                    raise ValueError(f"An item has invalid {field} data.")
            if r.get("date"):
                date.fromisoformat(r["date"])
            if "status" in r and r["status"] not in (None, "To do", "In progress", "Done"):
                raise ValueError("An item has an invalid status.")
            if "priority" in r and r["priority"] not in (None, "Low", "Medium", "High"):
                raise ValueError("An item has an invalid priority.")
            for field in ("time", "end_time"):
                if r.get(field):
                    datetime.strptime(r[field], "%H:%M")
            for field in ("archived", "deleted", "pinned", "completed"):
                if field in r and not isinstance(r[field], bool):
                    raise ValueError(f"An item has invalid {field} data.")
            link_targets = r.get("link_targets", {})
            if not isinstance(link_targets, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in link_targets.items()):
                raise ValueError("An item has invalid linked targets.")
            if type(r.get("revision")) is not int or r["revision"] < 1:
                raise ValueError("An item has an invalid revision.")
            for field in ("created_at", "updated_at"):
                if not isinstance(r.get(field), str):
                    raise ValueError("An item has an invalid timestamp.")
                datetime.fromisoformat(r[field])
            if r["kind"] == "session":
                seconds = r.get("seconds", 0)
                if not isinstance(seconds, (int, float)) or not 0 <= seconds <= 86400 * 7:
                    raise ValueError("An item has invalid focus duration.")
            self.validate_note_fields(r)
            if r['kind'] == 'task':
                from .board_model import validate_card
                validate_card(r)
            if r['kind'] == 'board':
                from .board_model import validate_board
                validate_board(r.get('workflow'))
            checked.append(r)
        incoming_blobs = self.attachments.validate_bundle(data.get('attachment_files', []), checked)
        incoming_links = data.get("links", [])
        preferences = data.get("preferences", {})
        if not isinstance(preferences, dict):
            raise ValueError("Invalid preferences.")
        for key, value in preferences.items():
            if key == 'task_board':
                if value is not None:
                    from .board_model import validate_board
                    validate_board(value)
                continue
            if key not in ("focus_minutes", "short_minutes", "long_minutes", "long_interval"):
                continue
            if value is not None and (type(value) is not int or not 1 <= value <= (20 if key == "long_interval" else 180)):
                raise ValueError("Invalid timer preferences.")
        if not isinstance(incoming_links, list) or any(
            not isinstance(l, dict) or not all(isinstance(l.get(f), str) for f in ("source", "target", "token"))
            for l in incoming_links
        ):
            raise ValueError("Invalid link data.")
        incoming_by_id = {r['id']: r for r in checked}
        for task in (r for r in checked if r['kind'] == 'task' and r.get('board')):
            owner = incoming_by_id.get(task['board']) or self.get(task['board'])
            if not owner or owner['kind'] != 'board':
                raise ValueError('A card references a missing board.')
            if task.get('project') != owner.get('project'):
                raise ValueError('A card project does not match its board.')
            if task.get('board_list') not in {c['id'] for c in owner['workflow']['lists']}:
                raise ValueError('A card references a missing board list.')
        self.backup(self.path.with_name("before-import-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3"))
        for key, payload in incoming_blobs.items():
            self.attachments.write_blob(key, payload)
        # Merge adds missing IDs and preserves divergent existing records as copies.
        # Remap all incoming relationships together so existing originals remain untouched.
        remap, inserted, copies = {}, [], 0
        for r in checked:
            existing = self.get(r["id"])
            if existing and existing != r:
                remap[r["id"]] = str(uuid.uuid4())
                copies += 1
            elif not existing:
                remap[r["id"]] = r["id"]
        with self.atomic():
            for source in checked:
                if source["id"] not in remap:
                    continue
                r = copy.deepcopy(source)
                r["id"] = remap[source["id"]]
                for f in ("project", "task", "parent", "board"):
                    if r.get(f) in remap:
                        r[f] = remap[r[f]]
                if "link_targets" in r:
                    r["link_targets"] = {token: remap.get(target, target) for token, target in r["link_targets"].items()}
                if source["id"] != r["id"]:
                    r["title"] += " (imported copy)"
                self._write(r)
                inserted.append(r)
                self.db.execute("INSERT INTO outbox VALUES (?,?,?,?)", (
                    str(uuid.uuid4()), r["id"], json.dumps(r, ensure_ascii=False), now()))
            if self.setting('multi_board_schema') == 1:
                from .boards import BoardCatalog
                catalog = BoardCatalog(self)
                imported_boards = {}
                for r in inserted:
                    if r['kind'] != 'task':
                        continue
                    if not r.get('board'):
                        project = r.get('project')
                        if project not in imported_boards:
                            imported_boards[project] = catalog.create('Imported tasks', project, preferences.get('task_board'))
                        r['board'] = imported_boards[project]['id']
                    catalog.assign(r)
                    self._write(r)
            inserted_ids = {r["id"] for r in inserted}
            for l in incoming_links:
                source = remap.get(l["source"], l["source"])
                target = remap.get(l["target"], l["target"])
                if source in inserted_ids and self.get(target):
                    self.db.execute("INSERT OR REPLACE INTO links VALUES (?,?,?)", (source, l["token"], target))
            for r in inserted:
                self._index_links(r)
            for key in ("focus_minutes", "short_minutes", "long_minutes", "long_interval"):
                if preferences.get(key) is not None:
                    self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(preferences[key])))
            if preferences.get('task_board'):
                from .board_model import BoardModel
                config = BoardModel(self).config()
                known = {c['id'] for c in config['lists']}
                config['lists'].extend(c for c in preferences['task_board']['lists'] if c['id'] not in known)
                from .board_model import validate_board
                validate_board(config)
                self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('task_board', json.dumps(config)))
        return len(inserted), copies

    def seed_demo(self):
        today = date.today()
        projects = [self.save({"kind": "project", "title": name, "color": color}) for name, color in (
            ("Personal website", "blue"), ("Learning", "green"), ("Life admin", "violet"))]
        for title, offset, project, priority in (
            ("Draft homepage", 0, 0, "High"), ("Read one chapter", 0, 1, "Medium"),
            ("Evening workout", 0, 2, "Low"), ("Website outline", -2, 0, "Medium"),
            ("Course notes", 3, 1, "Low"), ("Plan next month", 6, 2, "Medium")):
            self.save({"kind": "task", "title": title, "date": (today + timedelta(days=offset)).isoformat(),
                       "status": "To do", "priority": priority, "project": projects[project]["id"]})
        self.save({"kind": "note", "title": "Website ideas", "pinned": True, "color": "yellow",
                   "project": projects[0]["id"], "labels": "ideas, website",
                   "body": "# A clearer first impression\n\n- Cleaner hero section\n- Add work examples\n\nRelated: [[Personal website]]"})
        self.save({"kind": "note", "title": "Things to remember", "pinned": True, "color": "violet",
                   "body": "- [ ] Book dentist appointment\n- [ ] Renew domain\n- [ ] Plan next month"})
        self.save({"kind": "note", "title": "How links work", "color": "blue", "body":
                   "Type [[ to link a note, task, or project.\n\nTry [[Website ideas]] or [[Draft homepage]].\n\nLinks keep their targets when you rename them. Unresolved links can become new notes."})
        for title, offset, hour, color in (("Deep work", 0, "10:00", "blue"), ("Weekly review", 2, "16:00", "yellow")):
            self.save({"kind": "event", "title": title, "date": (today + timedelta(days=offset)).isoformat(),
                       "time": hour, "end_time": "17:00" if hour == "16:00" else "11:00", "color": color})

