# Tabla desktop data contract, export versions 1 and 2

The native laptop app is Qt/Python with SQLite. The later Flutter UI is a separate implementation. Use this contract to implement and verify a Dart importer; do not assume Dart can execute the Python model.

## Export envelope

JSON exports use UTF-8 with `app: "tabla"`, `schema_version: 2` for independent-board workspaces (0.7.0), `exported_at` (UTC ISO timestamp), `items` (array), `links` (array), and `preferences` (object). Version 1 imports remain supported. Older apps cannot read the new board entity; use 0.7.0 or later for version 2 exports. JSON is the portable boundary. The SQLite DB, active timer state, and implementation-specific outbox are not imported by this format.

## Independent boards (0.7.0)

Board entities are ordinary exported items with `kind: board`, `title`, optional `project` ID, `board_order`, lifecycle flags and `workflow: {version: 1, flexible: true, lists: [...]}`. Each list has an ID, title, canonical status and optional archived flag. List IDs are scoped to the owning board; identical default list IDs across different boards are intentional. At least one active list must remain. Task items carry `board` (owning board ID), `board_list` and `board_position`; their project matches that board. Import remaps board/project references together and validates ownership. Legacy exports with no board identities become independent imported boards when imported into a migrated workspace.

Startup migration creates one board per existing task project and a Personal board for unassigned tasks when needed. It copies the legacy workflow independently, preserves task IDs/revisions/timestamps/files/links and includes trashed tasks. A pre-migration SQLite snapshot is taken when tasks exist. Migration is transactional and idempotent. `multi_board_schema`, selected board, per-board draft/scroll/filter state and sidebar visibility are local settings; board entities and workflow definitions travel in exports.

## Common item fields

- `id`: stable UUID string, generated offline.
- `kind`: task, note, project, event, block, session, or board.
- `title`, `body`: Unicode strings. Notes and descriptions use Markdown-compatible text.
- `created_at`, `updated_at`: UTC ISO timestamps.
- `revision`: positive local integer. It is not a Firebase revision or global ordering value.
- `archived`, `deleted`: Boolean lifecycle flags.
- `schema_version`: 1.

Additional fields vary by kind. Unknown fields must be preserved by a future importer where safe, or rejected explicitly when incompatible.

## Kind-specific fields

| Kind | Additional fields |
|---|---|
| project | color |
| task | project (ID/null), date (YYYY-MM-DD/null), status (To do/In progress/Done), priority (Low/Medium/High), color |
| note | project, color, pinned, labels (comma-separated string), link_targets; day annotations also have date, day_annotation (true), day_color (color/null) |
| event | project, date, time/end_time (HH:mm, same-day local wall times), color |
| block | event fields plus task (ID) |
| session | task (task or note ID), seconds, completed, date, started_at |

Current events use floating local date/time values. The future sync migration must explicitly attach the user's selected timezone before converting events to UTC. Date-only task deadlines stay dates. Do not infer timezone from a record's updated_at field.

## Task board fields (0.6.0)

Task records may also contain `board_list` (stable list ID string), `board_position` (finite numeric order), `task_labels` (up to 50 objects with `name` and a palette `color`), `cover` (palette color/null), `checklists` (up to 30 named checklists, each with an `id`, `title`, and up to 1000 `items` containing `id`, `text`, `checked`), and `comments` (up to 1000 local `{text, at}` entries with ISO timestamps). Files use the same validated `attachments` metadata/vault as notes. Searchable `labels` remains a comma-separated string. `board_list_archived` marks cards archived by a custom-list archive operation so restoring that list does not unarchive cards previously archived individually.

`preferences.task_board` is an optional `{version:1, lists:[...]}` configuration. Each list has `id`, `title`, canonical `status` and optional `archived`. The standard `todo`, `doing`, `done` IDs map to To do, In progress, Done and remain active. Custom list IDs are UUIDs. Legacy tasks need no rewrite: missing/obsolete list references fall back to the matching standard status list. An external status change that disagrees with the assigned list also falls back to that status. Manual ordering is independent of titles and timestamps.

JSON backups include the board configuration and full card metadata/files. Import validates them before writing. Imported new list IDs are merged into the local list configuration; existing local list names/order/state win for matching IDs. Project-filtered boards share this workflow definition. SQLite backups already retain the configuration as settings. No SQL schema-version change is required.

## Rich notes (0.5.0)

Notes may carry `document: {version: 1, nodes: [...]}`. Paragraph nodes contain text runs with bold/italic/underline/strike/highlight marks, alignment, heading/list/checklist properties; image runs reference managed attachment keys and preserve width, height, wrapping, vertical alignment and alternative text. Table nodes have 1–10 columns, cell paragraph arrays and an optional header row. Frame nodes preserve floating content. The representation is structured JSON, independent of framework-generated HTML. `body` remains the derived searchable/plain-text representation, including readable checkbox markers, tab-separated table cells and image descriptions. Keep both fields together when moving or synchronizing a note.

`note_template` accepts none/lines/dots/grid/paper/diamonds, with `pattern_spacing` (16–48) and `pattern_strength` (.04–.25). Validate documents, source references and template fields before saving/importing. Existing schema-1 envelopes accept these optional fields. Opening a legacy note does not migrate or change its timestamp; the first actual edit preserves `legacy_body` and creates `before-rich-notes.sqlite3` before converting. Earlier executable versions do not understand rich documents; use the updated app for editing new-format notes.

Notes may include `attachments` (array) and `attachment_display` (`details` or `compact`). Each attachment has a UUID `id`, content-addressed `key` (SHA-256 hex plus extension), original basename `name`, byte `size`, and `mime`. Files live in the workspace's `attachments` directory; paths are never exported. JSON backups optionally carry `attachment_files`, an array of `{key, data}` objects with base64 bytes. Import validates metadata, sizes, hashes and referenced-file coverage before database changes. Older exports without attachments remain supported. A future Dart importer must decode and validate these blobs too. The database schema version remains 1 because these are optional JSON fields.

Limits are 25 MiB per file, 100 attachments per note, 100 MiB of unique binary backup content and 200 MiB per input JSON file. Daily SQLite snapshots do not include binary attachment files. JSON exports include files referenced by deleted records as well as active records; detached orphan files remain local but are not exported.

The body contains `[[token]]` references. Tokens may be readable titles or an explicit item ID. The authoritative exported `links` entries have `source`, `token`, and `target` IDs. `link_targets` also preserves exact choices made in the autocomplete picker, especially where titles are duplicated. Both must be interpreted when migrating; parsing only visible titles would lose rename-safe references.

Established links preserve target identity when a title changes. Incoming links are a derived index. A deleted target retains its identity for restoration. Unresolved tokens remain unresolved until a unique target exists or the user creates/selects a target. Unlinked text matches are not automatically converted to references.

## Import behavior of this release

- Validate the entire envelope before writing; use one SQLite transaction for imported items.
- Add unknown IDs. Leave identical existing items unchanged.
- Preserve divergent existing items; add incoming alternatives with fresh IDs and an `(imported copy)` suffix.
- Remap imported project/task/link relationships to copied targets together.
- Retain deletion/archive states and save a pre-import database snapshot.
- Import timer presets but never replace the active device-local timer.

The future Firebase sync engine needs its own server revisions, idempotency receipts, account partitioning, conflict rules, and tested synchronization protocol. Local revision and outbox fields alone do not provide sync.

## SQLite inventory

`records` holds canonical serialized items and indexed metadata; `links` is the resolved reference index; `search_index` is a derived FTS5 index; `settings` stores device state and timer preferences; `outbox` records local mutations for a future adapter. `PRAGMA user_version` is 1.

Test fixtures are generated by `Store.seed_demo()` in a separate QA workspace. `tests/test_storage.py` exercises export/import, conflict copies, rename/delete/restore links, preference roundtrips, and rollback on failed outbox writes. Future Dart tests should consume actual Python-produced exports and verify the same identities and relationships.

## Per-list completion routing (0.7.2)

A workflow list may include `completion_target`: null or another active list ID in the same board. Null/missing means stay. On a transition from unfinished to Done with unchanged board/list, save appends the card to the target while retaining Done. A new completed card also follows its source rule. A single save never chains rules. Metadata edits on completed cards, explicit board/list moves, archive/delete and unchecking do not route. Archiving a destination clears incoming rules. Workflow validation rejects self, missing, archived and non-string destinations. Backups retain these fields within the existing version 2 board workflow.
