"""Mock-up pictures of PR7-P, drawn offscreen with real Qt widgets: python tools/mockup.py OUT_DIR"""
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

from PySide6.QtCore import QPointF, QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,  # noqa: E402
                               QHBoxLayout, QLabel, QMainWindow, QMenu, QVBoxLayout, QWidget)

from pr7p import theme, widgets  # noqa: E402
import sample_images  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mockup")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
FILES = sample_images.folder(Path(tempfile.mkdtemp()) / "Pictures")
IMAGES = [QImage(str(f)) for f in FILES]
CURRENT = 4

MENUS = {
    "&File": ["&Open...\tO", "Open &recent", "-", "&Thumbnails\tT", "&Slideshow...\tW", "&Batch conversion / rename...\tB",
              "-", "&Save\tCtrl+S", "Save &as...\tS", "&Print...\tCtrl+P", "-", "Copy &to...\tF8", "&Move to...\tF7",
              "Re&name...\tF2", "&Delete\tDel", "Show in &folder", "-", "E&xit\tEsc"],
    "&Edit": ["&Undo\tCtrl+Z", "&Redo\tCtrl+Y", "-", "&Copy\tCtrl+C", "&Paste\tCtrl+V", "Cr&op selection\tCtrl+Shift+Y",
              "-", "Select &all\tCtrl+A", "&Clear selection"],
    "&Image": ["&Information...\tI", "-", "Rotate &left\tL", "Rotate &right\tR", "Custom / fine &rotation...\tCtrl+U",
               "&Vertical flip\tV", "&Horizontal flip\tH", "-", "Cr&op selection\tCtrl+Y",
               "Resi&ze / resample...\tCtrl+R", "Change &canvas size...\tShift+V", "-",
               "&Auto-adjust colours\tShift+U", "&Sharpen\tShift+S", "Colour &corrections...\tShift+G",
               "Convert to &greyscale\tCtrl+G", "&Negative\tCtrl+Shift+N", "-", "Set as &wallpaper"],
    "&Options": ["&Finish", "&Properties / settings...\tP", "-", "Check for &updates..."],
    "&View": ["&Fit images to window\tShift+F", "Fit &only big images", "&Original size\tCtrl+H", "-",
              "Full &screen\tEnter", "-", "Show &toolbar", "Show &status bar", "Show thumbnail &strip", "-",
              "&Next image\tRight", "&Previous image\tLeft", "&First image\tHome", "&Last image\tEnd"],
    "&Help": ["&Keyboard shortcuts\tF1", "&About Paragon PR7-P"],
}
CHECKED = {"&Fit images to window\tShift+F", "Show &toolbar", "Show &status bar", "Show thumbnail &strip"}


class View(QWidget):
    """The picture, fitted to the window on the family's dark ground, with an optional crop selection."""

    def __init__(self, img: QImage, crop: QRectF | None = None):
        super().__init__()
        self.img, self.crop = img, crop

    def fitted(self) -> QRectF:
        m = 18
        k = min((self.width() - 2 * m) / self.img.width(), (self.height() - 2 * m) / self.img.height(), 1.0)
        w, h = self.img.width() * k, self.img.height() * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.PANEL if theme.FINISH == "obsidian" else "#D9D4D6"))
        r = self.fitted()
        p.fillRect(r.translated(0, 4), QColor(0, 0, 0, 120 if theme.FINISH == "obsidian" else 40))
        p.drawImage(r, self.img)
        if self.crop:
            k = r.width() / self.img.width()
            c = QRectF(r.x() + self.crop.x() * k, r.y() + self.crop.y() * k, self.crop.width() * k,
                       self.crop.height() * k)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            shade = QColor(0, 0, 0, 120)
            for part in (QRectF(r.left(), r.top(), r.width(), c.top() - r.top()),
                         QRectF(r.left(), c.bottom(), r.width(), r.bottom() - c.bottom()),
                         QRectF(r.left(), c.top(), c.left() - r.left(), c.height()),
                         QRectF(c.right(), c.top(), r.right() - c.right(), c.height())):
                p.fillRect(part, shade)
            p.setPen(QPen(theme.family_gradient(c.left(), 0, c.right(), 0), 2))
            p.drawRect(c)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine))
            for i in (1, 2):
                p.drawLine(QPointF(c.left() + c.width() * i / 3, c.top()), QPointF(c.left() + c.width() * i / 3, c.bottom()))
                p.drawLine(QPointF(c.left(), c.top() + c.height() * i / 3), QPointF(c.right(), c.top() + c.height() * i / 3))
            p.setBrush(QColor("#FFFFFF")); p.setPen(Qt.PenStyle.NoPen)
            for pt in (c.topLeft(), c.topRight(), c.bottomLeft(), c.bottomRight()):
                p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
            label = f"{int(self.crop.width())} x {int(self.crop.height())}"
            f = QFont("Inter"); f.setPixelSize(12); f.setWeight(QFont.Weight.DemiBold); p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(label) + 16
            box = QRectF(c.left(), c.bottom() + 8, tw, 22)
            p.setBrush(QColor(theme.MENU)); p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor(theme.ON_DARK)); p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)


class Strip(QWidget):
    """ImageGlass's thumbnail strip: the folder's pictures, the current one marked with the family gradient."""

    def __init__(self, current: int):
        super().__init__()
        self.current = current
        self.setFixedHeight(104)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.BACKGROUND))
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1))
        p.drawLine(0, 0, self.width(), 0)
        x = 16.0
        for i, img in enumerate(IMAGES):
            box = QRectF(x, 14, 104, 76)
            k = min(box.width() / img.width(), box.height() / img.height())
            w, h = img.width() * k, img.height() * k
            r = QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)
            if i == self.current:
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(theme.ACCENT); c.setAlphaF(.16)
                p.setBrush(c); p.drawRoundedRect(box.adjusted(-6, -6, 6, 6), 6, 6)
            p.drawImage(r, img)
            if i == self.current:
                p.setPen(QPen(theme.family_gradient(r.left(), 0, r.right(), 0), 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 3, 3)
            x += 120


def keys_row(thumbs_on: bool = False) -> QWidget:
    bar = QWidget()
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(4)

    def gap():
        line = QFrame(); line.setFixedSize(1, 22); line.setStyleSheet(f"background: {theme.PANEL_EDGE};")
        lay.addSpacing(6); lay.addWidget(line); lay.addSpacing(6)

    for name, tip in (("open", "Open"), ("save", "Save as")):
        lay.addWidget(widgets.SmallKey(name, tip))
    gap()
    for name, tip in (("left", "Previous image"), ("right", "Next image")):
        lay.addWidget(widgets.SmallKey(name, tip))
    gap()
    lay.addWidget(widgets.SmallKey("zoomout", "Zoom out"))
    lay.addWidget(widgets.SmallKey("zoomin", "Zoom in"))
    zoom = QComboBox(); zoom.addItems(["Fit to window", "Original size", "200%", "100%", "50%"]); zoom.setFixedWidth(150)
    lay.addSpacing(4); lay.addWidget(zoom)
    fit = widgets.SmallKey("fit", "Fit images to window", True); fit.setChecked(not thumbs_on); lay.addWidget(fit)
    lay.addWidget(widgets.SmallKey("actual", "Original size"))
    gap()
    for name, tip in (("rotleft", "Rotate left"), ("rotate", "Rotate right"), ("flip", "Horizontal flip"),
                      ("crop", "Crop selection")):
        lay.addWidget(widgets.SmallKey(name, tip))
    gap()
    th = widgets.SmallKey("thumbs", "Thumbnails", True); th.setChecked(thumbs_on); lay.addWidget(th)
    lay.addWidget(widgets.SmallKey("play", "Slideshow"))
    lay.addWidget(widgets.SmallKey("fullscreen", "Full screen"))
    lay.addWidget(widgets.SmallKey("info", "Information"))
    lay.addStretch(1)
    lay.addWidget(widgets.SmallKey("trash", "Delete"))
    return bar


def status(img: QImage, index: int, zoom: int) -> QWidget:
    bar = QWidget()
    bar.setObjectName("status")
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(14, 4, 14, 6)
    lay.setSpacing(26)
    f = FILES[index]
    size = f.stat().st_size
    parts = [f"{img.width()} x {img.height()} x 24 BPP", f"{index + 1}/{len(FILES)}", f"{zoom} %",
             f"{size / 1024 / 1024:.2f} MB / {img.width() * img.height() / 1e6:.2f} MP", "3 Oct 2026  18:42"]
    for t in parts:
        lab = QLabel(t); lab.setObjectName("stat"); lay.addWidget(lab)
    lay.addStretch(1)
    name = QLabel(f.name); name.setObjectName("statname"); lay.addWidget(name)
    return bar


EXTRA = """
QWidget#status {{ background: {bg}; border-top: 1px solid {edge}; }}
QLabel#stat {{ color: {dim}; font-size: 12px; }}
QLabel#statname {{ color: {text}; font-size: 12px; }}
QLabel#key {{ color: {dim}; font-weight: 600; font-size: 11px; }}
QLabel#head {{ color: {text}; font-weight: 600; font-size: 12px; padding-top: 8px; }}
"""


def window(center: QWidget, index: int = CURRENT, zoom: int = 52, strip: bool = True, thumbs_on: bool = False):
    win = QMainWindow()
    win.resize(1280, 820)
    for title in MENUS:
        win.menuBar().addMenu(title)
    w = QWidget()
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(0)
    head = widgets.Header("IMAGE VIEWER")
    col.addWidget(head)
    col.addWidget(keys_row(thumbs_on))
    col.addWidget(center, 1)
    if strip:
        col.addWidget(Strip(index))
    col.addWidget(status(IMAGES[index], index, zoom))
    win.setCentralWidget(w)
    return win


class Grid(QWidget):
    """IrfanView's Thumbnails (T): the whole folder, with each picture's size."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.BACKGROUND))
        f = QFont("Inter"); f.setPixelSize(15); f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f); p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(40, 18, 800, 30), Qt.AlignmentFlag.AlignVCenter, "PICTURES   ·   12 IMAGES")
        bar = QRectF(40, 50, 120, 2)
        p.fillRect(bar, theme.family_gradient(bar.left(), 0, bar.right(), 0))
        cw, ch, cols = 190, 190, 6
        f2 = QFont("Inter"); f2.setPixelSize(12)
        f3 = QFont("Inter"); f3.setPixelSize(11)
        for i, img in enumerate(IMAGES):
            cx, cy = 40 + (i % cols) * (cw + 14), 72 + (i // cols) * (ch + 20)
            cell = QRectF(cx, cy, cw, ch)
            if i in (CURRENT, 5):
                c = QColor(theme.ACCENT); c.setAlphaF(.16)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(c); p.drawRoundedRect(cell, 8, 8)
            box = QRectF(cx + 12, cy + 10, cw - 24, 124)
            k = min(box.width() / img.width(), box.height() / img.height())
            w, h = img.width() * k, img.height() * k
            r = QRectF(box.center().x() - w / 2, box.bottom() - h, w, h)
            p.drawImage(r, img)
            if i == CURRENT:
                p.setPen(QPen(theme.family_gradient(r.left(), 0, r.right(), 0), 2.5)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 3, 3)
            p.setFont(f2); p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(cx + 4, cy + 142, cw - 8, 18), Qt.AlignmentFlag.AlignCenter,
                       p.fontMetrics().elidedText(FILES[i].name, Qt.TextElideMode.ElideMiddle, cw - 8))
            p.setFont(f3); p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(cx + 4, cy + 162, cw - 8, 16), Qt.AlignmentFlag.AlignCenter,
                       f"{img.width()} x {img.height()}   {FILES[i].stat().st_size // 1024} KB")


def info_dialog(parent) -> QDialog:
    d = QDialog(parent)
    d.setWindowTitle("Image Information")
    d.resize(560, 600)
    g = QGridLayout(d)
    g.setHorizontalSpacing(18)
    img = IMAGES[CURRENT]
    f = FILES[CURRENT]
    rows = [("FILE NAME", f.name), ("FOLDER", r"C:\Users\Pictures\Summer"), ("FORMAT", "JPEG, quality ~88"),
            ("ORIGINAL SIZE", f"{img.width()} x {img.height()} pixels ({img.width() * img.height() / 1e6:.2f} MP)"),
            ("CURRENT SIZE", f"{img.width()} x {img.height()} pixels"),
            ("PRINT SIZE", f"{img.width() / 300 * 2.54:.1f} x {img.height() / 300 * 2.54:.1f} cm at 300 DPI"),
            ("COLOURS", "16.7 million (24 BitsPerPixel)"), ("DISK SIZE", f"{f.stat().st_size / 1024:.0f} KB"),
            ("FILE DATE", "3 October 2026, 18:42"), (None, "CAMERA (EXIF)"),
            ("CAMERA", "Fujifilm X-T5"), ("LENS", "XF 16-55mm F2.8 R LM WR"), ("TAKEN", "3 October 2026, 18:41:07"),
            ("EXPOSURE", "1/250 s   f/5.6   ISO 200"), ("FOCAL LENGTH", "35 mm (53 mm in 35 mm film)"),
            ("FLASH", "Off"), ("GPS", "54.5973 N, 5.9301 W")]
    title = QLabel("IMAGE INFORMATION"); title.setObjectName("head")
    g.addWidget(title, 0, 0, 1, 2)
    rows.insert(0, ("", ""))
    for i, (k, v) in enumerate(rows):
        if i == 0:
            continue
        if k is None:
            h = QLabel(v); h.setObjectName("head"); g.addWidget(h, i, 0, 1, 2); continue
        a = QLabel(k); a.setObjectName("key")
        g.addWidget(a, i, 0)
        g.addWidget(QLabel(v), i, 1)
    bb = QDialogButtonBox()
    bb.addButton("COPY", QDialogButtonBox.ButtonRole.ActionRole)
    bb.addButton("CLOSE", QDialogButtonBox.ButtonRole.RejectRole)
    g.addWidget(bb, len(rows), 0, 1, 2)
    return d


def settle():
    end = time.time() + .5
    while time.time() < end:
        app.processEvents(); time.sleep(.02)


def shoot(win, name, menu=None, active=0, dialog=None):
    win.show(); settle()
    img = win.grab().toImage()
    p = QPainter(img)
    if menu:
        m = QMenu(win)
        for text in MENUS[menu]:
            if text == "-":
                m.addSeparator()
            else:
                a = m.addAction(text)
                if text in CHECKED:
                    a.setCheckable(True); a.setChecked(True)
        m.resize(m.sizeHint())
        act = next(a for a in win.menuBar().actions() if a.text() == menu)
        at = win.menuBar().actionGeometry(act).bottomLeft()
        m.popup(win.mapToGlobal(at)); app.processEvents()
        m.setActiveAction([a for a in m.actions() if not a.isSeparator()][active]); app.processEvents()
        p.drawPixmap(at, m.grab()); m.hide()
    if dialog:
        dialog.show(); settle()
        pm = dialog.grab()
        p.fillRect(img.rect(), QColor(0, 0, 0, 90))
        size = pm.deviceIndependentSize()           # both measured in screen points (the pictures are 2x)
        x = int((img.deviceIndependentSize().width() - size.width()) / 2)
        y = int((img.deviceIndependentSize().height() - size.height()) / 2)
        p.drawPixmap(x, y, pm)
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x, y, size.width(), size.height()))
        dialog.hide()
    p.end()
    img.save(str(out / f"{name}.png"))
    print(out / f"{name}.png")
    win.close()


def all_shots():
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet() + EXTRA.format(bg=theme.BACKGROUND, edge=theme.PANEL_EDGE,
                                                        dim=theme.TEXT_DIM, text=theme.TEXT))
    if theme.FINISH == "aurora":
        shoot(window(View(IMAGES[0]), index=0, zoom=51), "main_aurora")
        return
    shoot(window(View(IMAGES[CURRENT])), "main")
    crop = QRectF(420, 260, 1080, 720)
    shoot(window(View(IMAGES[CURRENT], crop)), "image_menu", menu="&Image", active=6)
    w = window(View(IMAGES[CURRENT]))
    shoot(w, "information", dialog=info_dialog(w))
    shoot(window(Grid(), strip=False, thumbs_on=True), "thumbnails")


all_shots()
theme.set_finish("aurora")
all_shots()
