# Release preparation validation

Validated on Windows x64 on 2026-11-23 for TABLA 0.9.0.

- 104 tests passed across 12 isolated unittest modules.
- Real packaged executable startup and reopen passed with an isolated sample workspace.
- Eight packaged views passed: Home, Calendar, task board, Notes, Focus, Trash, dark Notes and dark task board.
- SQLite integrity check returned `ok`; record counts were retained after reopening.
- The local sample attachment was retained.
- Final archives include the approved MIT license and third-party notices.
- Repository screenshots contain only disposable sample content.

Home tests now initialize the same Fusion style and bundled Inter font as the application, correcting an environment-dependent compact-layout assertion. Application behavior was not changed for this repository preparation.

GitHub Actions has been configured using the official [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python) and [upload-artifact](https://github.com/actions/upload-artifact) actions. The hosted workflow has not run yet because this copy has not been pushed to GitHub.

The portable executable is unsigned. A separate clean Windows-machine installation check remains a recommended pre-publication check; local verification used a sanitized runtime environment on the development machine.
