"""IrfanView's file commands (Delete, Copy to, Move to, Rename, Set as wallpaper, Show in folder) on real files.

Delete sends to the Recycle Bin (Qt's moveToTrash: Windows' own Recycle Bin, a freedesktop trash elsewhere), never
deletes outright. **PR7P_TRASH points it at a folder instead: tests always set it**, so they never touch the real
Recycle Bin."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from PySide6.QtCore import QFile

BAD_CHARS = '\\/:*?"<>|'


class FileError(Exception):
    pass


def free_name(folder: str, name: str) -> str:
    """name, or "name (2).ext", "name (3).ext"... the first that isn't taken in folder."""
    base, ext = os.path.splitext(name)
    candidate, n = name, 2
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{base} ({n}){ext}"
        n += 1
    return candidate


def trash(path: str) -> None:
    folder = os.environ.get("PR7P_TRASH")
    if folder:
        os.makedirs(folder, exist_ok=True)
        shutil.move(path, os.path.join(folder, free_name(folder, os.path.basename(path))))
        return
    ok = QFile.moveToTrash(path)
    if isinstance(ok, tuple):     # PySide returns (ok, path in trash)
        ok = ok[0]
    if not ok:
        raise FileError(f"{os.path.basename(path)} couldn't be moved to the Recycle Bin.")


def copy_to(path: str, folder: str, overwrite: bool = False) -> str:
    target = os.path.join(folder, os.path.basename(path) if overwrite else free_name(folder, os.path.basename(path)))
    shutil.copy2(path, target)
    return target


def move_to(path: str, folder: str, overwrite: bool = False) -> str:
    target = os.path.join(folder, os.path.basename(path) if overwrite else free_name(folder, os.path.basename(path)))
    shutil.move(path, target)
    return target


def name_problem(name: str) -> str | None:
    """Why Windows wouldn't take this file name, or None."""
    if not name.strip() or name in (".", ".."):
        return "The name can't be empty."
    if any(c in name for c in BAD_CHARS):
        return f"A file name can't contain any of these: {' '.join(BAD_CHARS)}"
    if name.rstrip(" .") != name:
        return "A file name can't end with a space or a dot."
    return None


def rename(path: str, name: str) -> str:
    problem = name_problem(name)
    if problem:
        raise FileError(problem)
    target = os.path.join(os.path.dirname(path), name)
    if os.path.exists(target) and os.path.normcase(target) != os.path.normcase(path):
        raise FileError(f"{name} already exists in this folder.")
    os.rename(path, target)
    return target


def set_wallpaper(path: str) -> bool:
    """Options > Set as wallpaper (Windows: SystemParametersInfoW SPI_SETDESKWALLPAPER, saved for next sign-in)."""
    if sys.platform != "win32":
        return False
    import ctypes
    SPI_SETDESKWALLPAPER, SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x14, 0x1, 0x2
    return bool(ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, os.path.abspath(path),
                                                           SPIF_UPDATEINIFILE | SPIF_SENDCHANGE))


def show_in_folder(path: str) -> None:
    """The picture's folder: in PR7-E when it's the folder app, else Explorer with the file selected."""
    from . import family
    folder = os.path.dirname(path)
    if family.pr7e_for_folders() and family.launch("PR7-E", [folder]):
        return
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
    else:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
