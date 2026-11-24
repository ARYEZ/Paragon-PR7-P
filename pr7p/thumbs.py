"""Thumbnails: made on worker threads (JPEGs decoded straight at the small size, which is far quicker than the whole
picture), kept in memory while the file is unchanged. ImageGlass's strip under the picture and IrfanView's
Thumbnails grid (T) both draw from them."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageIOHandler, QImageReader, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea

from . import theme

SIZE = 220     # thumbnails are made this big (longest side), then drawn smaller


def turned(r: QImageReader) -> bool:
    """Whether the camera's orientation tag turns the picture a quarter (its width and height swap when shown)."""
    return bool(r.transformation() & QImageIOHandler.Transformation.TransformationRotate90)


def shown_size(path: str) -> QSize:
    r = QImageReader(path)
    r.setAutoTransform(True)
    s = r.size()
    return s.transposed() if s.isValid() and turned(r) else s


def make(path: str, size: int = SIZE) -> QImage:
    r = QImageReader(path)
    r.setAutoTransform(True)
    s = r.size()          # as stored: Qt shrinks first, then turns
    if s.isValid() and s.width() > 0 and s.height() > 0:
        k = min(size / s.width(), size / s.height(), 1.0)
        r.setScaledSize(QSize(max(1, round(s.width() * k)), max(1, round(s.height() * k))))
    img = r.read()
    if img.isNull():
        try:
            from .imageio import read
            img = read(path)
        except Exception:  # noqa: BLE001 - shown as an empty frame
            return QImage()
    if max(img.width(), img.height()) > size:
        img = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return img


class _Bridge(QObject):
    done = Signal(str, float, QImage)


class _Job(QRunnable):
    def __init__(self, path, stamp, bridge):
        super().__init__()
        self.path, self.stamp, self.bridge = path, stamp, bridge

    def run(self):
        self.bridge.done.emit(self.path, self.stamp, make(self.path))


class Thumbs(QObject):
    """get(path) gives the thumbnail if it's ready (else None and it's made); `ready` says when one arrives."""
    ready = Signal(str)

    def __init__(self, sync: bool = False, parent=None):
        super().__init__(parent)
        self.sync = sync
        self.cache: dict[str, tuple[float, QImage]] = {}
        self.pending: set[str] = set()
        self.bridge = _Bridge()
        self.bridge.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(2, min(4, (os.cpu_count() or 2) - 1)))

    def _stamp(self, path) -> float:
        try:
            st = os.stat(path)
            return st.st_mtime + st.st_size * 1e-12
        except OSError:
            return -1.0

    def get(self, path: str) -> QImage | None:
        stamp = self._stamp(path)
        hit = self.cache.get(path)
        if hit and hit[0] == stamp:
            return hit[1]
        if path not in self.pending:
            self.pending.add(path)
            if self.sync:
                self._done(path, stamp, make(path))
                return self.cache[path][1]
            self.pool.start(_Job(path, stamp, self.bridge))
        return None

    def _done(self, path, stamp, img):
        self.pending.discard(path)
        self.cache[path] = (stamp, img)
        self.ready.emit(path)

    def forget(self, path: str) -> None:
        self.cache.pop(path, None)

    def wait(self) -> None:
        self.pool.waitForDone()


def draw_thumb(p: QPainter, img: QImage | None, box: QRectF, current: bool, selected: bool = False) -> QRectF:
    """A thumbnail fitted in `box`, the current one outlined with the family gradient."""
    if selected or current:
        c = QColor(theme.ACCENT); c.setAlphaF(.16)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
        p.drawRoundedRect(box.adjusted(-6, -6, 6, 6), 6, 6)
    if img is None or img.isNull():
        r = box.adjusted(box.width() * .2, box.height() * .2, -box.width() * .2, -box.height() * .2)
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 4, 4)
        return r
    k = min(box.width() / img.width(), box.height() / img.height(), 1.0)
    w, h = img.width() * k, img.height() * k
    r = QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)
    p.drawImage(r, img)
    if current:
        p.setPen(QPen(theme.family_gradient(r.left(), 0, r.right(), 0), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 3, 3)
    return r


class Strip(QAbstractScrollArea):
    """The row of thumbnails under the picture; a click opens one, the wheel scrolls, the current one stays in view."""
    activated = Signal(int)
    CELL, GAP = 104, 16

    def __init__(self, thumbs: Thumbs, parent=None):
        super().__init__(parent)
        self.thumbs = thumbs
        self.files: list[str] = []
        self.current = -1
        self.setFixedHeight(104)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        thumbs.ready.connect(lambda _p: self.viewport().update())
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    def set_files(self, files: list[str], current: int) -> None:
        self.files, self.current = list(files), current
        self.horizontalScrollBar().setRange(0, max(0, len(files) * (self.CELL + self.GAP) + self.GAP - self.viewport().width()))
        self.show_current()

    def set_current(self, i: int) -> None:
        self.current = i
        self.show_current()

    def cell(self, i: int) -> QRectF:
        x = self.GAP + i * (self.CELL + self.GAP) - self.horizontalScrollBar().value()
        return QRectF(x, 14, self.CELL, 76)

    def show_current(self) -> None:
        if 0 <= self.current < len(self.files):
            want = self.GAP + self.current * (self.CELL + self.GAP) + self.CELL / 2 - self.viewport().width() / 2
            self.horizontalScrollBar().setValue(int(want))
        self.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.set_files(self.files, self.current)

    def paintEvent(self, _):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.viewport().rect(), QColor(theme.BACKGROUND))
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1))
        p.drawLine(0, 0, self.viewport().width(), 0)
        first = max(0, int(self.horizontalScrollBar().value() // (self.CELL + self.GAP)))
        last = min(len(self.files), first + self.viewport().width() // (self.CELL + self.GAP) + 2)
        for i in range(first, last):
            draw_thumb(p, self.thumbs.get(self.files[i]), self.cell(i), i == self.current)

    def index_at(self, pos) -> int:
        for i in range(len(self.files)):
            if self.cell(i).adjusted(-6, -6, 6, 6).contains(QPointF(pos)):
                return i
        return -1

    def mouseReleaseEvent(self, e):
        i = self.index_at(e.position())
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(i)

    def wheelEvent(self, e):
        hs = self.horizontalScrollBar()
        hs.setValue(hs.value() - int(e.angleDelta().y() or e.angleDelta().x()))


class Grid(QAbstractScrollArea):
    """IrfanView's Thumbnails: the whole folder in a grid with each picture's size. Click / Ctrl+click / Shift+click
    select (for Delete, Copy to, Move to); double-click or Enter opens one."""
    activated = Signal(int)
    selectionChanged = Signal()
    CW, CH, GAP, TOP = 190, 190, 14, 72

    def __init__(self, thumbs: Thumbs, parent=None):
        super().__init__(parent)
        self.thumbs = thumbs
        self.files: list[str] = []
        self.sizes: dict[str, str] = {}
        self.current = -1
        self.selected: set[int] = set()
        self.title = ""
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        thumbs.ready.connect(lambda _p: self.viewport().update())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    def cols(self) -> int:
        return max(1, (self.viewport().width() - 40) // (self.CW + self.GAP))

    def set_files(self, files: list[str], current: int, title: str = "") -> None:
        self.files, self.current, self.title = list(files), current, title
        self.selected = {current} if current >= 0 else set()
        self._range()
        self.ensure_visible(current)

    def _range(self):
        rows = (len(self.files) + self.cols() - 1) // self.cols()
        total = self.TOP + rows * (self.CH + 20) + 20
        vs = self.verticalScrollBar()
        vs.setRange(0, max(0, total - self.viewport().height()))
        vs.setPageStep(self.viewport().height()); vs.setSingleStep(60)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._range()

    def cell(self, i: int) -> QRectF:
        c = self.cols()
        return QRectF(40 + (i % c) * (self.CW + self.GAP), self.TOP + (i // c) * (self.CH + 20) -
                      self.verticalScrollBar().value(), self.CW, self.CH)

    def ensure_visible(self, i: int) -> None:
        if 0 <= i < len(self.files):
            r = self.cell(i)
            vs = self.verticalScrollBar()
            if r.top() < 0:
                vs.setValue(int(vs.value() + r.top() - 20))
            elif r.bottom() > self.viewport().height():
                vs.setValue(int(vs.value() + r.bottom() - self.viewport().height() + 20))
        self.viewport().update()

    def paintEvent(self, _):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.viewport().rect(), QColor(theme.BACKGROUND))
        top = -self.verticalScrollBar().value()
        f = QFont("Inter"); f.setPixelSize(15); f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f); p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(40, top + 18, 1200, 30), Qt.AlignmentFlag.AlignVCenter, self.title)
        bar = QRectF(40, top + 50, 120, 2)
        p.fillRect(bar, theme.family_gradient(bar.left(), 0, bar.right(), 0))
        f2 = QFont("Inter"); f2.setPixelSize(12)
        f3 = QFont("Inter"); f3.setPixelSize(11)
        for i, path in enumerate(self.files):
            cell = self.cell(i)
            if cell.bottom() < 0 or cell.top() > self.viewport().height():
                continue
            box = QRectF(cell.x() + 12, cell.y() + 10, cell.width() - 24, 124)
            img = self.thumbs.get(path)
            draw_thumb(p, img, box, i == self.current, i in self.selected)
            p.setFont(f2); p.setPen(QColor(theme.TEXT))
            name = p.fontMetrics().elidedText(os.path.basename(path), Qt.TextElideMode.ElideMiddle, int(cell.width()) - 8)
            p.drawText(QRectF(cell.x() + 4, cell.y() + 142, cell.width() - 8, 18), Qt.AlignmentFlag.AlignCenter, name)
            p.setFont(f3); p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(cell.x() + 4, cell.y() + 162, cell.width() - 8, 16), Qt.AlignmentFlag.AlignCenter,
                       self._size_text(path))

    def _size_text(self, path: str) -> str:
        if path not in self.sizes:
            s = shown_size(path)
            try:
                kb = os.path.getsize(path) // 1024
            except OSError:
                kb = 0
            self.sizes[path] = (f"{s.width()} x {s.height()}   " if s.isValid() else "") + f"{kb:,} KB"
        return self.sizes[path]

    def index_at(self, pos) -> int:
        for i in range(len(self.files)):
            if self.cell(i).contains(QPointF(pos)):
                return i
        return -1

    def mousePressEvent(self, e):
        self.setFocus()
        i = self.index_at(e.position())
        if i < 0:
            return
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.selected ^= {i}
        elif mods & Qt.KeyboardModifier.ShiftModifier and self.current >= 0:
            a, b = sorted((self.current, i))
            self.selected = set(range(a, b + 1))
        else:
            self.selected = {i}
        self.current = i
        self.selectionChanged.emit()
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        i = self.index_at(e.position())
        if i >= 0:
            self.activated.emit(i)

    def keyPressEvent(self, e):
        k, c = e.key(), self.cols()
        move = {Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1, Qt.Key.Key_Down: c, Qt.Key.Key_Up: -c}.get(k)
        if move is not None and self.files:
            self.current = min(max(self.current + move, 0), len(self.files) - 1)
            self.selected = {self.current}
            self.ensure_visible(self.current)
            self.selectionChanged.emit()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.current >= 0:
            self.activated.emit(self.current)
        elif k == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.selected = set(range(len(self.files)))
            self.selectionChanged.emit()
            self.viewport().update()
        else:
            super().keyPressEvent(e)

    def selected_files(self) -> list[str]:
        return [self.files[i] for i in sorted(self.selected) if 0 <= i < len(self.files)]
