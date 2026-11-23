# TABLA

**A little order. A lot more room.**

A local-first Windows workspace for tasks, calendars, notes, and focus sessions. Built with Python and Qt.

## Download and run

Requires Windows x64. Python is not required for the packaged application.

**Download status:** the Windows package has not yet been published to this repository. These instructions apply once it is available in [Releases](https://github.com/Changelo06/Tabla/releases).

1. Download `Tabla-Windows-0.9.0.zip` from Releases. Choose the Windows package rather than GitHub's automatic source-code archive.
2. Right-click the ZIP and choose **Extract All**.
3. Move the extracted `Tabla` folder somewhere convenient, such as `C:\Users\YourName\Apps\Tabla`. Replace `YourName` with your Windows account name.
4. Open the folder and double-click **Tabla.exe**.

TABLA is portable, so there is no installation wizard. Keep the entire extracted folder together, including `_internal`, licenses and notices. Do not run the app from inside the ZIP or copy only `Tabla.exe`.

You can also keep the complete app folder on another writable drive. Moving the app does not move your saved workspace onto that drive.

### Optional desktop shortcut

Right-click `Tabla.exe` and choose **Show more options → Send to → Desktop (create shortcut)** where available. If you move the app folder later, recreate or update the shortcut.

## Getting started

- **Home:** see your calendar, tasks, board shortcuts and recent notes.
- **Board:** organize projects with lists and task cards.
- **Calendar:** plan events using month, week or day views.
- **Notes:** capture ideas, create checklists and pin favorites.
- **Focus:** choose a task or note and explicitly start a focus session.

A new workspace starts empty. Settings includes an **Add sample workspace** option for exploring examples.

## Where your data lives

Your default workspace is stored separately from the app:

```text
%LOCALAPPDATA%\Tabla
```

Paste this into File Explorer's address bar to open it. It normally resolves to `C:\Users\YourName\AppData\Local\Tabla`. Settings shows the exact folder and lets you export JSON backups containing referenced attachments.

Daily database snapshots alone do not include attachment files. This version does not encrypt your database.

## Updating

1. Export a JSON backup from Settings.
2. Close TABLA, including any running tray instance.
3. Extract the new Windows release into a separate folder.
4. Run its `Tabla.exe` and check your workspace.
5. Update your desktop shortcut to point to the new executable.

The new version normally opens the same default workspace. Keep your backup and previous app folder until you have checked the update. There is no automatic updater.

## Troubleshooting

- **Missing files or startup problems:** extract the complete ZIP again and keep `_internal` beside `Tabla.exe`.
- **TABLA is already open:** check the taskbar and system tray for the existing window.
- **Publisher warning:** the Windows package is unsigned. Verify its source before deciding whether to run it.

## Current scope

TABLA is an offline, single-user Windows application. No account or internet connection is required. Cloud sync, collaboration, recurring tasks and mobile apps are not included.

