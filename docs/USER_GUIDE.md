# Using TABLA

## Notes and links

Opening a note shows one centered editable sheet, without Write/Read/Checklist tabs. The independent right-hand floating card contains links and at most three source previews. **View all** opens the full list, and **+** adds files. A softly blurred backdrop and restrained shadows separate the sheet from the Notes page. Changes autosave; the small label above Close reports the last successful edit.

Use the context icon in the note toolbar to hide/show the floating card. At narrow widths it starts hidden and opens on demand. Source names retain full-name hover hints. Attachments and rich document structure travel together in JSON backups.

The desktop header's **Search** field is the single workspace search entry. Click it or press **Ctrl+K**, enter a title/content/label term, then press **Enter**. Search remains available in compact windows; the space around it still drags the window. Notes collection filters are hidden by default; **View → Show note filters** restores the strip. **View → Note collection** accesses pinned, archived and trashed notes, and **View → Note preview length** changes the bounded card preview.

The quick composer grows with short text, then caps the writing area according to window height. Long drafts scroll inside the editor so the toolbar stays reachable. Deleting text shrinks it again. Window and sidebar resizing remeasure the text without saving or replacing the draft.

The header contains back/forward history, a sidebar toggle, File, Edit, View, Layout, Settings and Help. Hover the navigation icons for labels; Trash is separated by a fine divider. Short fades, gentle icon feedback and expanding note capture provide motion. Turn it off with **Settings → Reduce motion**.

Use **File → Import files into a note** or the paperclip's source-file action. Dropped documents attach as sources; dropped images insert in the document. PDF, TXT, Markdown, common Office documents and images are supported. Single small TXT/Markdown imports also populate the note body. Files are copied locally, so moving the original does not break them. Hover source rows for full filenames; click to open the installed desktop viewer. PDFs are sources rather than embedded editors. Limits: 25 MiB per file, 100 sources per note, 100 MiB of unique attachment content per JSON backup.

Quick capture and opened notes share the formatted editor and keyboard commands. Use **A** or **Ctrl+B/I/U** for formatting; the palette chooses ruled lines, dotted grid, square grid, paper grain or diamond dots, with spacing/strength controls. The paperclip's Insert menu offers images, tables and source files. Right-click inside a table to add/remove rows or columns; the ten-column limit is enforced. Select an image for corner resizing; right-click for numeric size, wrap-left/right, inline alignment and a description. Hold Alt while resizing to bypass the gentle half-width guide. The More menu includes **Download as .txt**, labels/project, Create task, Archive and Trash. Pinning works from the composer, writer and note cards.

Use **Take a note…** to capture quickly. Close, navigation or quitting saves populated captures; drafts also persist while writing. Click a card for the complete note. Close or Escape saves and closes it. Use the checklist toolbar action for native inline checkboxes, and Ctrl-click a [[reference]] to navigate. Card previews hide overflow without deleting text. Plain-text export includes readable checklists, table cells and image descriptions, but omits visual formatting and image bytes. Deletion moves notes to the accessible Trash for restoration.

## Storage and backups

**Trash has a dedicated sidebar icon**. If the rail is hidden, show it using the header sidebar toggle, or use View → Trash. It shows deleted notes, tasks, meetings, projects and work blocks with a search field and explicit Restore buttons. Restoration keeps the original ID, content, attachments and links. View → Note collection → Trash and Settings also provide access. Items are not automatically removed from Trash.

Your real workspace lives in `%LOCALAPPDATA%/Tabla/tabla.sqlite3`, independently of the application folder. The exact folder is displayed in Settings. Settings also opens that folder and exports/imports JSON backups. Import adds missing records and preserves divergent existing records as alternate copies. It never silently overwrites existing work; check the import summary. Pre-import snapshots are stored beside the database. Timer preferences are included in JSON exports; a live timer is device-local and is not imported from a backup.

Startup retains the seven most recent daily database snapshots under `snapshots`. These snapshots contain metadata, not attachment bytes; attachments live alongside the database in `attachments`. JSON exports include referenced attachment bytes, including attachments of trashed notes. Attachment files are retained when a note is trashed or a file is detached. Export a JSON copy to a separate location periodically. The database is not encrypted by this release.

## Timer behavior

Start a timer explicitly. Breaks do not auto-start. Finishing a session records focus time without completing its task. Changing/resetting an active session asks for confirmation and records interrupted focus time. If you close Tabla with a running timer, choose **Keep in tray** to continue receiving alerts, or **Stop and quit**. Alerts cannot run after the app has fully exited. Tray alerts depend on Windows notification/sound settings; no exact-alarm or wake-from-sleep guarantee is made.

The timer uses a monotonic clock while running and a persisted deadline to recover after restart. Abrupt clock changes across a restart can affect the recovered countdown. Focus history is local to this laptop for now.
