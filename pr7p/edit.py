"""IrfanView's Image menu as functions: each takes a picture and returns a new one, so Undo is a list of pictures.
Turning, flipping, cropping and resizing are Qt's; sharpen, auto-adjust and the colour corrections are Pillow's."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

from .imageio import from_pil, to_pil


def rotate(img: QImage, degrees: float, background: QColor | None = None) -> QImage:
    """Turn by any angle (L / R are -90 / 90). Quarter turns are exact; others turn on a bigger canvas filled with
    `background` (white, as IrfanView's fine rotation)."""
    d = degrees % 360
    if d in (90, 180, 270):
        return img.transformed(QTransform().rotate(d))
    out = img.transformed(QTransform().rotate(d), Qt.TransformationMode.SmoothTransformation)
    if background is not None:
        filled = QImage(out.size(), QImage.Format.Format_ARGB32)
        filled.fill(background)
        p = QPainter(filled)
        p.drawImage(0, 0, out)
        p.end()
        return filled
    return out


def flip(img: QImage, horizontal: bool = True) -> QImage:
    o = Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical
    return img.flipped(o)


def crop(img: QImage, rect: QRect) -> QImage:
    r = rect.normalized().intersected(img.rect())
    return img.copy(r) if not r.isEmpty() else img


def resize(img: QImage, width: int, height: int, smooth: bool = True) -> QImage:
    mode = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
    return img.scaled(max(1, int(width)), max(1, int(height)), Qt.AspectRatioMode.IgnoreAspectRatio, mode)


def canvas(img: QImage, width: int, height: int, colour: QColor = QColor("white"), centre: bool = True) -> QImage:
    """Change canvas size: the picture on a canvas of another size (centred, or top left)."""
    out = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32)
    out.fill(colour)
    p = QPainter(out)
    x = (width - img.width()) // 2 if centre else 0
    y = (height - img.height()) // 2 if centre else 0
    p.drawImage(x, y, img)
    p.end()
    return out


def greyscale(img: QImage) -> QImage:
    alpha = img.hasAlphaChannel()
    grey = img.convertToFormat(QImage.Format.Format_Grayscale8)
    return grey.convertToFormat(QImage.Format.Format_ARGB32 if alpha else QImage.Format.Format_RGB32)


def negative(img: QImage) -> QImage:
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    out.invertPixels(QImage.InvertMode.InvertRgb)
    return out


def sharpen(img: QImage) -> QImage:
    from PIL import ImageFilter
    return from_pil(to_pil(img).filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2)))


def auto_adjust(img: QImage) -> QImage:
    """Shift+U: stretch each picture's tones to the full range (Pillow's autocontrast, the darkest and lightest
    half percent let go)."""
    from PIL import ImageOps
    pil = to_pil(img)
    alpha = pil.getchannel("A")
    rgb = ImageOps.autocontrast(pil.convert("RGB"), cutoff=0.5)
    rgb.putalpha(alpha)
    return from_pil(rgb)


def colours(img: QImage, brightness: float = 0, contrast: float = 0, saturation: float = 0,
            gamma: float = 1.0) -> QImage:
    """Colour corrections: brightness / contrast / saturation from -100 to 100 (0 = unchanged), gamma 0.1 - 6.99."""
    from PIL import ImageEnhance
    pil = to_pil(img)
    alpha = pil.getchannel("A")
    rgb = pil.convert("RGB")
    if brightness:
        rgb = ImageEnhance.Brightness(rgb).enhance(1 + brightness / 100)
    if contrast:
        rgb = ImageEnhance.Contrast(rgb).enhance(1 + contrast / 100)
    if saturation:
        rgb = ImageEnhance.Color(rgb).enhance(1 + saturation / 100)
    if gamma and abs(gamma - 1.0) > 1e-3:
        table = [min(255, round(255 * (i / 255) ** (1 / gamma))) for i in range(256)]
        rgb = rgb.point(table * 3)
    rgb.putalpha(alpha)
    return from_pil(rgb)
