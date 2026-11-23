"""Build a standalone Windows folder with no Python installation requirement."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from tabla.theme import application_icon
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from tabla import __version__

app = QApplication.instance() or QApplication([])
assets = ROOT / "assets"
app_icon = assets / "tabla.ico"
launcher = application_icon()
sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
images = []
for size in sizes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not launcher.pixmap(size, size).save(buffer, 'PNG'):
        raise RuntimeError('Could not render the Windows app icon')
    buffer.close()
    images.append(bytes(data))
offset = 6 + 16 * len(sizes)
directory = bytearray(struct.pack('<HHH', 0, 1, len(sizes)))
for size, data in zip(sizes, images):
    directory.extend(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
app_icon.write_bytes(bytes(directory) + b''.join(images))

build_env = dict(os.environ)
# Do not let unrelated tool runtimes on PATH replace Windows system libraries.
# In this host, Poppler's versioned ICU was shadowing the system ICU used by Qt.
for variable in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
    build_env.pop(variable, None)
windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
build_env["PATH"] = os.pathsep.join(str(p) for p in (
    Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows))
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
    "--distpath", str(ROOT / "dist" / __version__),
    "--name", "Tabla", "--icon", "assets/tabla.ico", "--add-data", "assets;assets",
    "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.QtQuick",
    "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "tkinter", "run_tabla.py",
], check=True, cwd=ROOT, env=build_env)
destination = ROOT / "dist" / __version__ / "Tabla"
icu = destination / "_internal" / "icuuc.dll"
if icu.exists():
    import pefile
    binary = pefile.PE(str(icu), max_symbol_exports=1000000)
    symbols = {s.name for s in binary.DIRECTORY_ENTRY_EXPORT.symbols}
    binary.close()
    if b"ucnv_open" not in symbols:
        raise RuntimeError("Incompatible versioned ICU collected. Refusing to ship this package.")
shutil.copy2(ROOT / "docs" / "PORTABLE_README.txt", destination / "READ-ME.txt")
shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", destination / "THIRD-PARTY-NOTICES.md")
shutil.copy2(ROOT / "docs" / "USER_GUIDE.md", destination / "USER-GUIDE.md")
shutil.copy2(ROOT / "LICENSE", destination / "LICENSE.txt")
licenses = destination / "licenses"
licenses.mkdir(exist_ok=True)
shutil.copy2(assets / "fonts" / "OFL.txt", licenses / "Manrope-OFL.txt")
for font_license in (assets / "fonts").glob("*-OFL.txt"):
    shutil.copy2(font_license, licenses / font_license.name)
for license_file in (assets / "licenses").glob("*.txt"):
    shutil.copy2(license_file, licenses / license_file.name)
for distribution in ("PySide6_Essentials", "shiboken6"):
    from importlib.metadata import distribution as metadata
    dist = metadata(distribution)
    for file in dist.files or []:
        if "license" in str(file).lower() and str(file).lower().endswith((".txt", ".html", ".md")):
            source = Path(dist.locate_file(file))
            if source.is_file():
                shutil.copy2(source, licenses / (distribution + "-" + source.name))
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
print("Standalone app:", destination / "Tabla.exe")
