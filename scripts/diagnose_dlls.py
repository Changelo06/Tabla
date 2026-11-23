"""Read-only check for unresolved imports among collected Windows DLLs."""
from pathlib import Path
import pefile

root = Path(__file__).resolve().parents[1] / "dist" / "Tabla" / "_internal"
paths = list(root.rglob("*.dll")) + list(root.rglob("*.pyd"))
paths.sort(key=lambda p: len(p.parts))
by_name = {}
for p in paths:
    by_name.setdefault(p.name.lower(), p)
exports = {}
for p in by_name.values():
    binary = pefile.PE(str(p), fast_load=True, max_symbol_exports=1000000)
    binary.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    exports[p] = {s.name for s in getattr(getattr(binary, "DIRECTORY_ENTRY_EXPORT", None), "symbols", []) if s.name}
    binary.close()
for p in paths:
    binary = pefile.PE(str(p), fast_load=True, max_symbol_exports=1000000)
    binary.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for dependency in getattr(binary, "DIRECTORY_ENTRY_IMPORT", []):
        target = by_name.get(dependency.dll.decode().lower())
        if not target:
            continue
        missing = [s.name.decode(errors="replace") for s in dependency.imports if s.name and s.name not in exports[target]]
        if missing:
            print(p.relative_to(root), "->", target.relative_to(root), missing[:12])
    binary.close()
