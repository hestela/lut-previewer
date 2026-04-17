"""
Persistent recent-files history backed by QSettings.

One RecentFiles instance per file type (images, LUTs).
"""

import os
from PyQt5.QtCore import QSettings

MAX_RECENT = 10


class RecentFiles:
    def __init__(self, key: str):
        # key: "images" or "luts" — stored separately in QSettings
        self._settings = QSettings("lut-previewer", "LUTPreviewer")
        self._key = key

    def paths(self) -> list:
        """Return persisted paths, silently dropping any that no longer exist."""
        raw = self._settings.value(self._key, [])
        # QSettings returns a plain str (not list) when only one entry was saved
        if isinstance(raw, str):
            raw = [raw]
        return [p for p in raw if os.path.isfile(p)]

    def add(self, path: str):
        """Prepend path, deduplicate, cap at MAX_RECENT, and persist."""
        paths = [p for p in self.paths() if p != path]
        paths.insert(0, path)
        self._settings.setValue(self._key, paths[:MAX_RECENT])

    def clear(self):
        self._settings.setValue(self._key, [])
