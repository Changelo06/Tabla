# Contributing to TABLA

Use Windows x64 and Python 3.11. Set up the virtual environment and install `requirements-dev.txt` as described in the README.

## Working safely

Use `--data-dir build/demo --demo` for a separate sample workspace. Keep personal records, exported backups, attachments, logs and credentials out of commits and issue reports. Screenshots should show sample content only.

## Checks

Run `python scripts/run_tests.py` using the virtual environment. Each test module runs in a separate process so Qt state cannot leak between suites. Tests use temporary databases and the offscreen Qt platform.

For interface changes, also inspect the native Windows app in light and dark themes, including compact window sizes. Offscreen tests do not verify Windows snapping, notifications or tray behavior.

## Pull requests

Describe the concrete problem and resulting behavior. Include the checks you ran and screenshots for visible interface changes. Keep changes focused and preserve stable record IDs, attachments, backup compatibility and existing user data.

## Packaging

Run `python scripts/package_release.py`. Release binaries belong in GitHub Releases, not in the Git repository. See `docs/RELEASING.md`.
