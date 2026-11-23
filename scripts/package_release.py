"""Build and verify the Windows app before producing a portable ZIP and checksum."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tabla import __version__

def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows package on Windows x64.")
    for script in ("build_windows.py", "verify_package.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)
    folder = ROOT / "dist" / __version__ / "Tabla"
    if not (folder / "Tabla.exe").is_file():
        raise SystemExit("Packaged executable is missing")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = Path(shutil.make_archive(str(release / f"Tabla-Windows-{__version__}"), "zip", root_dir=folder.parent, base_dir=folder.name))
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Portable ZIP: {archive}\nSHA-256: {digest}")

if __name__ == "__main__":
    main()
