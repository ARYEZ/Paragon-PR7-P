"""Screenshots of the real window (offscreen) on stand-in photos: python tools/screenshots.py OUT_DIR"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_cfg = Path(tempfile.gettempdir()) / "pr7p_offscreen.json"
_cfg.write_text(json.dumps({"screens": [{"name": "s", "x": 0, "y": 0, "width": 3200, "height": 2200,
                                          "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}))
os.environ.setdefault("QT_QPA_PLATFORM", f"offscreen:configfile={_cfg}")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
work = Path(tempfile.mkdtemp())
os.environ["PR7P_TRASH"] = str(work / "trash")

from PySide6.QtCore import QRect, QSettings  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(work / "settings"))
import sample_images  # noqa: E402
from pr7p import theme  # noqa: E402
from pr7p.main_window import InfoDialog, MainWindow, apply_look  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
apply_look(app)
files = sample_images.folder(work / "Summer", 12)
sample_images.with_exif(files[4])


def settle():
    end = time.time() + .6
    while time.time() < end:
        app.processEvents(); time.sleep(.02)


def shot(w, name, dialog=None):
    settle()
    img = w.grab().toImage()
    if dialog:
        dialog.show(); settle()
        pm = dialog.grab()
        p = QPainter(img)
        p.fillRect(img.rect(), QColor(0, 0, 0, 90))
        size, whole = pm.deviceIndependentSize(), img.deviceIndependentSize()
        x, y = int((whole.width() - size.width()) / 2), int((whole.height() - size.height()) / 2)
        p.drawPixmap(x, y, pm)
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1)); p.drawRect(x, y, int(size.width()), int(size.height()))
        p.end()
        dialog.hide()
    img.save(str(out / f"{name}.png"))
    print(out / f"{name}.png")


w = MainWindow(str(files[4]), thumbs_sync=True)
w.resize(1280, 820)
w.show()
shot(w, "main_window")
w.view.set_selection(QRect(420, 260, 1080, 720))
shot(w, "selection")
w.view.set_selection(QRect())
shot(w, "information", InfoDialog(w.path, w.image, w))
w.toggle_thumbnails()
shot(w, "thumbnails")
w.toggle_thumbnails()
w.set_finish("aurora")
w.go(0)
shot(w, "main_window_aurora")
w.set_finish("obsidian")
w.close()
