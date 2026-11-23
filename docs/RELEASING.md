# Preparing a Windows release

1. Confirm that `LICENSE` and all third-party notices are included in the release.
2. Use Windows x64, Python 3.11 and the pinned development dependencies.
3. Review `tabla/__init__.py` and `CHANGELOG.md`. Keep the version unchanged for repository-only preparation.
4. Run `python scripts/run_tests.py`.
5. Run `python scripts/package_release.py`. This builds the app, verifies real packaged startup, page captures, reopen, SQLite integrity and an attached sample file, then archives the complete portable folder.
6. Check `build/package-verification.json`, the portable ZIP and its SHA-256 checksum. Extract to a new folder and run `Tabla.exe` on a Windows machine without Python installed before publishing a release.
7. Commit the source and documentation. Create the repository and push only after reviewing its contents. Attach the portable ZIP and checksum to a versioned GitHub Release; do not commit `dist/`, `build/` or `release/`.

CI runs isolated test modules on Windows for pushes and pull requests. It can build a checked portable package when triggered manually with the package option. It uploads a workflow artifact and does not publish a GitHub Release.

The application is unsigned. Keep `_internal` and all notices/licenses together with `Tabla.exe`. Never include a real workspace or private attachments in the app package.

`requirements-lock.txt` pins the development/build environment. The runtime-only dependency is in `requirements.txt`. The build script is the canonical build entry point; it regenerates the portable PyInstaller spec and launcher icon from repository-relative resources.
