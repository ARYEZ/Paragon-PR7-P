"""The pictures in a folder (no Qt): which files count as images, IrfanView's sort by name (natural: IMG_2 before
IMG_10, case and accents ignored), and moving through them (next / previous loop round, as ImageGlass does)."""

from __future__ import annotations

import os
import re
import unicodedata

# What Qt's image plugins read, then what Pillow adds (pr7p.imageio uses Pillow for those).
QT_EXTS = {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "dib", "ico", "cur", "tif", "tiff", "webp", "svg",
           "tga", "icns", "wbmp", "pbm", "pgm", "ppm", "xbm", "xpm"}
PIL_EXTS = {"avif", "jp2", "j2k", "jpf", "pcx", "psd", "dds", "qoi", "sgi", "rgb", "ras", "im", "msp"}
IMAGE_EXTS = QT_EXTS | PIL_EXTS


def ext(path: str) -> str:
    return os.path.splitext(path)[1][1:].lower()


def is_image(path: str) -> bool:
    return ext(path) in IMAGE_EXTS


def natural_key(name: str):
    """Sort key: numbers by value, letters without case or accents ("IMG_2" < "IMG_10", "é" next to "e")."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower() or name.lower()
    return [(0, int(t), t) if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", plain) if t != ""]


def images_in(folder: str) -> list[str]:
    """The image files in a folder, sorted by name; hidden files (dot files) left out."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    files = [os.path.join(folder, n) for n in names
             if not n.startswith(".") and is_image(n) and os.path.isfile(os.path.join(folder, n))]
    files.sort(key=lambda p: natural_key(os.path.basename(p)))
    return files


class Folder:
    """The folder being viewed and where in it the viewer is."""

    def __init__(self, path: str | None = None, loop: bool = True):
        self.loop = loop
        self.files: list[str] = []
        self.index = -1
        if path:
            self.open(path)

    def open(self, path: str) -> None:
        """A file (its folder, positioned on it) or a folder (its first picture)."""
        path = os.path.abspath(path)
        if os.path.isdir(path):
            self.files = images_in(path)
            self.index = 0 if self.files else -1
            return
        self.files = images_in(os.path.dirname(path))
        key = os.path.normcase(path)
        for i, f in enumerate(self.files):
            if os.path.normcase(f) == key:
                self.index = i
                return
        # Not an image by its name (or not listed yet): show it anyway, on its own place in the order.
        self.files.append(path)
        self.files.sort(key=lambda p: natural_key(os.path.basename(p)))
        self.index = self.files.index(path)

    def refresh(self) -> None:
        """Read the folder again (files added, renamed or deleted), staying on the current file if it's there."""
        cur = self.current
        if not self.files:
            return
        folder = os.path.dirname(self.files[0])
        self.files = images_in(folder)
        if cur and os.path.exists(cur):
            self.open(cur)
        else:
            self.index = min(max(self.index, 0), len(self.files) - 1) if self.files else -1

    @property
    def current(self) -> str | None:
        return self.files[self.index] if 0 <= self.index < len(self.files) else None

    @property
    def count(self) -> int:
        return len(self.files)

    def step(self, delta: int) -> str | None:
        """Next (+1) / previous (-1): round from the last to the first when looping, else stop at the ends."""
        if not self.files:
            return None
        i = self.index + delta
        if self.loop:
            i %= len(self.files)
        else:
            i = min(max(i, 0), len(self.files) - 1)
        self.index = i
        return self.current

    def go(self, index: int) -> str | None:
        if self.files:
            self.index = min(max(index, 0), len(self.files) - 1)
        return self.current

    def removed(self, path: str) -> None:
        """A file was deleted or moved away: drop it and stay at the same place (the next file slides in)."""
        key = os.path.normcase(os.path.abspath(path))
        for i, f in enumerate(self.files):
            if os.path.normcase(f) == key:
                self.files.pop(i)
                if self.index > i or self.index >= len(self.files):
                    self.index -= 1
                if self.files and self.index < 0:
                    self.index = 0
                return

    def renamed(self, old: str, new: str) -> None:
        self.removed(old)
        self.files.append(os.path.abspath(new))
        self.files.sort(key=lambda p: natural_key(os.path.basename(p)))
        self.index = self.files.index(os.path.abspath(new))
