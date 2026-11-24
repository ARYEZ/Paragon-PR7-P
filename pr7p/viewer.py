"""The picture view: zoom (fit to window, fit only big images, a percentage), scrolling, IrfanView's mouse (wheel =
next / previous picture, Ctrl+wheel = zoom at the pointer, left drag = selection, right drag = move the picture,
double-click = full screen), animated GIF / WebP, and transparency shown on a chequerboard (ImageGlass)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QMovie, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea

from . import theme

FIT, FIT_BIG = "fit", "fitbig"
ZOOMS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 50, 70, 100, 150, 200, 300, 400, 600, 800, 1000, 1600, 2400, 3200]
MARGIN = 0


def step_zoom(percent: float, up: bool) -> float:
    if up:
        bigger = [z for z in ZOOMS if z > percent + 0.01]
        return bigger[0] if bigger else ZOOMS[-1]
    smaller = [z for z in ZOOMS if z < percent - 0.01]
    return smaller[-1] if smaller else ZOOMS[0]


def fit_scale(img: QSize, view: QSize, mode, margin: int = 0) -> float:
    """The scale for a zoom: fit (grow or shrink to the window), fit only big images (shrink, never grow), or a
    percentage."""
    if img.isEmpty():
        return 1.0
    if mode in (FIT, FIT_BIG):
        k = min((view.width() - 2 * margin) / img.width(), (view.height() - 2 * margin) / img.height())
        return max(min(k, 1.0) if mode == FIT_BIG else k, 0.001)
    return float(mode) / 100


class ImageView(QAbstractScrollArea):
    step = Signal(int)                  # the wheel asks for the next (+1) / previous (-1) picture
    zoomChanged = Signal(float)
    selectionChanged = Signal(QRect)
    fullscreenRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.movie: QMovie | None = None
        self.zoom = FIT_BIG
        self.selection = QRect()
        self.fullscreen = False
        self._drag = None
        self._press = None
        self._checker = None
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # A right drag moves the picture; a right click without a drag asks for the menu (mouseReleaseEvent).
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    # ------------------------------------------------------------------ the picture
    def set_image(self, img: QImage, movie_path: str | None = None, keep_zoom: bool = False) -> None:
        """Show a picture. An animated file plays (its first frame is `img`). The zoom goes back to the default
        unless `keep_zoom` (IrfanView keeps a chosen zoom only when asked)."""
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.image = img
        self.selection = QRect()
        self.selectionChanged.emit(self.selection)
        if movie_path:
            m = QMovie(movie_path)
            if m.isValid() and m.frameCount() != 1:
                self.movie = m
                m.frameChanged.connect(self._frame)
                m.start()
        self.relayout(centre=True)

    def _frame(self, _n):
        if self.movie:
            self.image = self.movie.currentImage()
            self.viewport().update()

    def scale(self) -> float:
        return fit_scale(self.image.size(), self.viewport().size(), self.zoom, MARGIN)

    def zoom_percent(self) -> float:
        return self.scale() * 100

    def shown_size(self) -> QSize:
        k = self.scale()
        return QSize(max(1, round(self.image.width() * k)), max(1, round(self.image.height() * k)))

    def relayout(self, centre: bool = False, anchor: QPointF | None = None, keep: QPointF | None = None) -> None:
        """Set the scroll ranges for the zoom; keep the image point `keep` under the window point `anchor`."""
        s, vp = self.shown_size(), self.viewport().size()
        hs, vs = self.horizontalScrollBar(), self.verticalScrollBar()
        hs.setRange(0, max(0, s.width() - vp.width())); hs.setPageStep(vp.width()); hs.setSingleStep(40)
        vs.setRange(0, max(0, s.height() - vp.height())); vs.setPageStep(vp.height()); vs.setSingleStep(40)
        if keep is not None and anchor is not None:
            k = self.scale()
            hs.setValue(int(keep.x() * k - anchor.x()))   # so the image point stays under the pointer
            vs.setValue(int(keep.y() * k - anchor.y()))
        elif centre:
            hs.setValue(hs.maximum() // 2)
            vs.setValue(vs.maximum() // 2)
        self.zoomChanged.emit(self.zoom_percent())
        self.viewport().update()

    def set_zoom(self, zoom, anchor: QPointF | None = None) -> None:
        keep = self.to_image(anchor) if anchor is not None else None
        if keep is None and anchor is None:     # zoom about the window's centre
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
            keep = self.to_image(anchor, clamp=False)
        self.zoom = zoom if zoom in (FIT, FIT_BIG) else min(max(float(zoom), ZOOMS[0]), ZOOMS[-1])
        self.relayout(anchor=anchor, keep=keep, centre=keep is None)

    def zoom_step(self, up: bool, anchor: QPointF | None = None) -> None:
        self.set_zoom(step_zoom(self.zoom_percent(), up), anchor)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout(centre=self.zoom in (FIT, FIT_BIG))

    # ------------------------------------------------------------------ coordinates
    def _offset(self) -> QPointF:
        """Where the picture's top left is in the window."""
        s, vp = self.shown_size(), self.viewport().size()
        x = (vp.width() - s.width()) / 2 if s.width() <= vp.width() else -self.horizontalScrollBar().value()
        y = (vp.height() - s.height()) / 2 if s.height() <= vp.height() else -self.verticalScrollBar().value()
        return QPointF(x, y)

    def image_rect(self) -> QRectF:
        o, s = self._offset(), self.shown_size()
        return QRectF(o.x(), o.y(), s.width(), s.height())

    def to_image(self, pos: QPointF | None, clamp: bool = True) -> QPointF | None:
        if pos is None or self.image.isNull():
            return None
        o, k = self._offset(), self.scale()
        x, y = (pos.x() - o.x()) / k, (pos.y() - o.y()) / k
        if clamp:
            x = min(max(x, 0), self.image.width())
            y = min(max(y, 0), self.image.height())
        return QPointF(x, y)

    def from_image(self, r: QRect) -> QRectF:
        o, k = self._offset(), self.scale()
        return QRectF(o.x() + r.x() * k, o.y() + r.y() * k, r.width() * k, r.height() * k)

    # ------------------------------------------------------------------ selection
    def set_selection(self, r: QRect) -> None:
        self.selection = r.normalized().intersected(self.image.rect()) if not r.isNull() else QRect()
        self.selectionChanged.emit(self.selection)
        self.viewport().update()

    def select_all(self) -> None:
        self.set_selection(self.image.rect())

    # ------------------------------------------------------------------ painting
    def background(self) -> QColor:
        if self.fullscreen:
            return QColor("#000000")
        return QColor(theme.PANEL if theme.FINISH == "obsidian" else "#D9D4D6")

    def _chequer(self) -> QBrush:
        if self._checker is None or self._checker[0] != theme.FINISH:
            pm = QPixmap(16, 16)
            a, b = ("#2A262C", "#1C191E") if theme.FINISH == "obsidian" else ("#FFFFFF", "#E6E2E4")
            pm.fill(QColor(a))
            p = QPainter(pm)
            p.fillRect(0, 0, 8, 8, QColor(b)); p.fillRect(8, 8, 8, 8, QColor(b))
            p.end()
            self._checker = (theme.FINISH, QBrush(pm))
        return self._checker[1]

    def paintEvent(self, _):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), self.background())
        if self.image.isNull():
            return
        r = self.image_rect()
        if self.image.hasAlphaChannel():
            p.fillRect(r, self._chequer())
        k = self.scale()
        # Smooth when shrinking or slightly enlarged; sharp pixels when zoomed far in, as viewers do.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, k < 2)
        p.drawImage(r, self.image)
        if not self.selection.isNull():
            self._paint_selection(p, self.from_image(self.selection), r)

    def _paint_selection(self, p: QPainter, c: QRectF, r: QRectF) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        shade = QColor(0, 0, 0, 120)
        for part in (QRectF(r.left(), r.top(), r.width(), c.top() - r.top()),
                     QRectF(r.left(), c.bottom(), r.width(), r.bottom() - c.bottom()),
                     QRectF(r.left(), c.top(), c.left() - r.left(), c.height()),
                     QRectF(c.right(), c.top(), r.right() - c.right(), c.height())):
            if part.width() > 0 and part.height() > 0:
                p.fillRect(part, shade)
        p.setPen(QPen(theme.family_gradient(c.left(), 0, c.right(), 0), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(c)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            p.drawLine(QPointF(c.left() + c.width() * i / 3, c.top()), QPointF(c.left() + c.width() * i / 3, c.bottom()))
            p.drawLine(QPointF(c.left(), c.top() + c.height() * i / 3), QPointF(c.right(), c.top() + c.height() * i / 3))
        label = f"{self.selection.width()} x {self.selection.height()}"
        f = p.font(); f.setPixelSize(12); f.setBold(True); p.setFont(f)
        tw = p.fontMetrics().horizontalAdvance(label) + 16
        box = QRectF(c.left(), min(c.bottom() + 8, self.viewport().height() - 28), tw, 22)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(theme.MENU))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor(theme.ON_DARK))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    # ------------------------------------------------------------------ mouse and keys
    def mousePressEvent(self, e):
        self.setFocus()
        self._press = e.position()
        if e.button() == Qt.MouseButton.LeftButton and not self.image.isNull():
            start = self.to_image(e.position())
            self._drag = ("select", start)
        elif e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._drag = ("pan", e.position(), self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        if self._drag[0] == "pan":
            d = e.position() - self._drag[1]
            self.horizontalScrollBar().setValue(int(self._drag[2] - d.x()))
            self.verticalScrollBar().setValue(int(self._drag[3] - d.y()))
        elif (e.position() - self._press).manhattanLength() > 3:
            a, b = self._drag[1], self.to_image(e.position())
            self.set_selection(QRect(QPoint(round(min(a.x(), b.x())), round(min(a.y(), b.y()))),
                                     QPoint(round(max(a.x(), b.x())) - 1, round(max(a.y(), b.y())) - 1)))

    def mouseReleaseEvent(self, e):
        moved = self._press is not None and (e.position() - self._press).manhattanLength() > 3
        if self._drag and self._drag[0] == "select" and not moved:
            self.set_selection(QRect())          # a click clears the selection
        was_pan = self._drag and self._drag[0] == "pan"
        self._drag = None
        self.viewport().unsetCursor()
        if was_pan and not moved and e.button() == Qt.MouseButton.RightButton:
            self.customContextMenuRequested.emit(e.position().toPoint())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.fullscreenRequested.emit()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        if not steps:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_step(steps > 0, e.position())
        else:
            self.step.emit(-1 if steps > 0 else 1)
