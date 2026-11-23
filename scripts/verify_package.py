"""Exercise the frozen exe with an isolated environment and disposable profile."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tabla import __version__
exe = ROOT / "dist" / __version__ / "Tabla" / "Tabla.exe"
profile = ROOT / "build" / ("packaged-smoke-" + str(int(time.time())))
shot = ROOT / "build" / "package-screenshots" / "packaged-calendar.png"
shot.parent.mkdir(parents=True, exist_ok=True)
profile.mkdir(parents=True)
from tabla.storage import Store
fixture_store = Store(profile / 'tabla.sqlite3')
fixture_store.seed_demo()
fixture_file = profile / 'Project reference document.txt'
fixture_file.write_text('Packaged attachment verification.', encoding='utf-8')
fixture_attachments = fixture_store.attachments.import_files([fixture_file])
fixture_store.save({'kind': 'note', 'title': 'Project documents', 'body': 'Original file saved locally.',
                    'pinned': True, 'attachments': fixture_attachments})
fixture_store.close()
env = dict(os.environ)
for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM"):
    env.pop(key, None)
env["PATH"] = r"C:\Windows\System32;C:\Windows"
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
result = subprocess.run([
    str(exe), "--data-dir", str(profile), "--demo", "--page", "Calendar", "--screenshot", str(shot), "--quit-after", "5000"
], env=env, startupinfo=startup, timeout=30)
if result.returncode:
    raise RuntimeError(f"Packaged app exited with {result.returncode}")
if not shot.exists() or shot.stat().st_size < 10000:
    raise RuntimeError("Packaged app did not produce a real UI screenshot")
database = profile / "tabla.sqlite3"
db = sqlite3.connect(database)
before = db.execute("SELECT count(*) FROM records").fetchone()[0]
integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
db.close()
result = subprocess.run([str(exe), "--data-dir", str(profile), "--quit-after", "1200"],
                        env=env, startupinfo=startup, timeout=20)
if result.returncode:
    raise RuntimeError("Packaged app did not reopen successfully")

for page in ('Today', 'My Tasks', 'Notes', 'Focus', 'Trash'):
    output = shot.parent / ('packaged-' + page.lower().replace(' ', '-') + '.png')
    result = subprocess.run([str(exe), '--data-dir', str(profile), '--page', page,
        '--screenshot', str(output), '--quit-after', '5000'], env=env, startupinfo=startup, timeout=25)
    if result.returncode or not output.exists() or output.stat().st_size < 10000:
        raise RuntimeError('Packaged ' + page + ' view failed')
db = sqlite3.connect(database)
db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('appearance', json.dumps('dark')))
db.commit()
db.close()
dark_shot = shot.parent / 'packaged-notes-dark.png'
result = subprocess.run([str(exe), '--data-dir', str(profile), '--page', 'Notes', '--screenshot', str(dark_shot),
    '--quit-after', '5000'], env=env, startupinfo=startup, timeout=25)
if result.returncode or not dark_shot.exists():
    raise RuntimeError('Packaged dark theme failed')
dark_board = shot.parent / 'packaged-board-dark.png'
result = subprocess.run([str(exe), '--data-dir', str(profile), '--page', 'My Tasks', '--screenshot', str(dark_board),
    '--quit-after', '5000'], env=env, startupinfo=startup, timeout=25)
if result.returncode or not dark_board.exists():
    raise RuntimeError('Packaged dark board failed')
db = sqlite3.connect(database)
after = db.execute("SELECT count(*) FROM records").fetchone()[0]
db.close()
assert before == after and before > 0 and integrity == "ok"
log = profile / "tabla.log"
if log.exists() and log.read_text(encoding="utf-8").strip():
    raise RuntimeError("Packaged app logged an error: " + log.read_text(encoding="utf-8"))
report = {"executable": str(exe), "exit_code": result.returncode, "isolated_runtime": True,
          "native_platform_plugin": "windows", "sqlite_integrity": integrity,
          "records_before_reopen": before, "records_after_reopen": after,
          "screenshot": str(shot), "test_profile": str(profile)}
report['verified_views'] = ['Home', 'Calendar', 'Tasks board', 'Notes', 'Focus', 'Trash', 'Notes (dark)', 'Tasks board (dark)']
assert (profile / 'attachments' / fixture_attachments[0]['key']).read_text(encoding='utf-8') == 'Packaged attachment verification.'
report['local_attachment_retained'] = True
(ROOT / "build" / "package-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
