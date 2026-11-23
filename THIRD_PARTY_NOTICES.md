# Third-party components

TABLA original source code is licensed under MIT (see LICENSE in source or LICENSE.txt in the portable app). This does not relicense the components listed below.

Inter is the active interface and writing font, bundled under the SIL Open Font License. Its license is `assets/fonts/Inter-OFL.txt` and `licenses/Inter-OFL.txt` in the packaged app. Source: https://github.com/google/fonts/tree/main/ofl/inter . Earlier font assets below are retained with their licenses and are not selected by the rebuilt interface.

Tabla uses dynamically loaded Qt for Python (PySide6 Essentials) and Shiboken 6.10.1, distributed under their applicable open-source license terms. Included license files are in the `licenses` folder of the packaged application. Corresponding project information and sources: https://code.qt.io/pyside/pyside-setup.git/ and https://code.qt.io/qt/ (Qt 6.10.1). The application uses the installed, replaceable Qt shared libraries rather than a statically linked Qt executable.

Python 3.11 is distributed under the Python Software Foundation license, included with the packaged application. SQLite is public domain. https://www.python.org/ and https://sqlite.org/copyright.html

Manrope is bundled under the SIL Open Font License. Its complete license is in `assets/fonts/OFL.txt` and the packaged `licenses/Manrope-OFL.txt`. Source: https://github.com/google/fonts/tree/main/ofl/manrope

Alegreya Sans (Regular, Medium and Black) and Alegreya (regular and italic variable fonts) are bundled for offline use under the SIL Open Font License. Licenses are in `assets/fonts/AlegreyaSans-OFL.txt` and `assets/fonts/Alegreya-OFL.txt`, also copied into the packaged `licenses` directory. Sources: https://github.com/google/fonts/tree/main/ofl/alegreyasans and https://github.com/google/fonts/tree/main/ofl/alegreya

PyInstaller 6.18.0 packages this app. Its bootloader license exception permits distribution of the bundled application; see https://pyinstaller.org/en/stable/license.html .

This notice does not change the licenses of the listed components. No third-party application code from Notion, Google Keep, Obsidian, Asana, or Pomofocus is included in Tabla.
