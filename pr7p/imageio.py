"""Reading and writing pictures, and what IrfanView's Information dialog says about them.

Qt's image plugins read the common formats (with the camera's orientation tag applied, as every viewer does);
Pillow reads the rest (AVIF, JPEG 2000, PCX, Photoshop ...). JPEGs are written through Pillow so their camera details
(EXIF) are kept, with the orientation tag set back to "upright" because the pixels are already turned."""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QBuffer, QByteArray, QFile, QIODevice
from PySide6.QtGui import QImage, QImageReader, QImageWriter

from . import folder

BPP = {"1": 1, "L": 8, "P": 8, "LA": 16, "RGB": 24, "RGBA": 32, "CMYK": 32, "YCbCr": 24, "I;16": 16, "I": 32, "F": 32}
FORMAT_NAMES = {"jpeg": "JPEG", "jpg": "JPEG", "png": "PNG", "gif": "GIF", "bmp": "BMP", "webp": "WebP",
                "tiff": "TIFF", "tif": "TIFF", "ico": "ICO", "svg": "SVG", "avif": "AVIF", "jp2": "JPEG 2000",
                "psd": "Photoshop", "pcx": "PCX", "tga": "TGA"}
WRITABLE = ["jpg", "png", "webp", "bmp", "tif", "gif", "ico", "avif"]


class ReadError(Exception):
    pass


@dataclass
class Info:
    """IrfanView's Image > Information, less the camera (exif.read)."""
    path: str
    format: str
    width: int
    height: int
    bpp: int
    frames: int = 1
    dpi: tuple[float, float] | None = None
    file_size: int = 0
    modified: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1e6

    @property
    def colours(self) -> str:
        if self.bpp >= 24:
            return f"16.7 million ({self.bpp} BitsPerPixel)"
        return f"{2 ** self.bpp:,} ({self.bpp} BitsPerPixel)"

    def print_size(self, dpi: float | None = None) -> str:
        d = dpi or (self.dpi[0] if self.dpi and self.dpi[0] else 300)
        return f"{self.width / d * 2.54:.1f} x {self.height / d * 2.54:.1f} cm at {d:.0f} DPI"


# ------------------------------------------------------------------ Qt <-> Pillow
def to_pil(img: QImage):
    from PIL import Image
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(img.constBits())[: img.sizeInBytes()]
    pil = Image.frombuffer("RGBA", (img.width(), img.height()), data, "raw", "RGBA", img.bytesPerLine(), 1)
    return pil.copy()


def from_pil(pil) -> QImage:
    pil = pil.convert("RGBA")
    data = pil.tobytes("raw", "RGBA")
    img = QImage(data, pil.width, pil.height, pil.width * 4, QImage.Format.Format_RGBA8888)
    return img.copy()   # own the pixels (the bytes object goes away)


# ------------------------------------------------------------------ reading
def read(path: str) -> QImage:
    """The picture, turned as the camera said (EXIF orientation). Raises ReadError."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    img = reader.read()
    if not img.isNull():
        return img
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as pil:
            pil = ImageOps.exif_transpose(pil)
            return from_pil(pil)
    except Exception as e:  # noqa: BLE001 - any reason it can't be read
        raise ReadError(f"{os.path.basename(path)}: {reader.errorString() or e}") from None


def frame_count(path: str) -> int:
    r = QImageReader(path)
    n = r.imageCount() if r.supportsAnimation() else 1
    return max(n, 1)


def info(path: str, img: QImage | None = None) -> Info:
    st = os.stat(path)
    fmt = folder.ext(path)
    bpp, dpi, extra = None, None, {}
    try:
        from PIL import Image
        with Image.open(path) as pil:
            fmt = (pil.format or fmt).lower()
            bpp = BPP.get(pil.mode)
            if pil.info.get("dpi"):
                dpi = tuple(float(x) for x in pil.info["dpi"])
            if pil.format == "JPEG":
                sub = {0: "4:4:4", 1: "4:2:2", 2: "4:2:0"}.get(_subsampling(pil))
                if sub:
                    extra["subsampling"] = sub
                if pil.info.get("progressive"):
                    extra["progressive"] = True
            w, h = pil.size
    except Exception:  # noqa: BLE001 - Pillow can't read it: Qt's view of it
        r = QImageReader(path)
        s = r.size()
        w, h = s.width(), s.height()
    if img is not None and not img.isNull():
        w, h = img.width(), img.height()   # after the orientation turn, as shown
    if bpp is None:
        bpp = 32 if img is not None and img.hasAlphaChannel() else 24
    return Info(path, FORMAT_NAMES.get(fmt, fmt.upper()), w, h, bpp, frame_count(path), dpi, st.st_size,
                st.st_mtime, extra)


def _subsampling(pil):
    try:
        from PIL import JpegImagePlugin
        return JpegImagePlugin.get_sampling(pil)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ writing
def write(img: QImage, path: str, quality: int = 90, exif_from: str | None = None) -> None:
    """Save a picture, its format from the file name. JPEG / WebP use `quality`; a JPEG keeps the camera details of
    `exif_from` (the file it came from) with orientation reset. Written to a temporary file first, then moved over,
    so a failed save never leaves half a picture."""
    fmt = folder.ext(path) or "jpg"
    tmp = path + ".pr7p-tmp"
    try:
        if fmt in ("jpg", "jpeg", "jpe", "jfif", "avif") or fmt not in ("png", "bmp", "webp", "tif", "tiff", "gif",
                                                                          "ico"):
            pil = to_pil(img)
            if fmt in ("jpg", "jpeg", "jpe", "jfif"):
                pil = _flatten(pil)
                kwargs = {"quality": int(quality), "optimize": True}
                exif = _exif_bytes(exif_from)
                if exif:
                    kwargs["exif"] = exif
                pil.save(tmp, "JPEG", **kwargs)
            else:
                pil.save(tmp, fmt.upper() if fmt != "avif" else "AVIF", quality=int(quality))
        else:
            if fmt == "gif":         # Qt reads GIF but doesn't write it
                _flatten(to_pil(img)).convert("P", palette=1, colors=256).save(tmp, "GIF")
            else:
                # Our own file, closed before the move: a QImageWriter given a file name keeps it open until the
                # writer is gone, and Windows won't move an open file.
                fh = QFile(tmp)
                if not fh.open(QIODevice.OpenModeFlag.WriteOnly):
                    raise OSError(fh.errorString())
                w = QImageWriter(fh, QByteArray(("tiff" if fmt == "tif" else fmt).encode()))
                if fmt == "webp":
                    w.setQuality(int(quality))
                ok = w.write(img)
                error = w.errorString()
                fh.close()
                if not ok:
                    raise OSError(error)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _flatten(pil):
    """JPEG has no transparency: transparent parts go white, as IrfanView does."""
    from PIL import Image
    if pil.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        pil = pil.convert("RGBA")
        bg.paste(pil, mask=pil.split()[3])
        return bg
    return pil.convert("RGB")


def _exif_bytes(path: str | None) -> bytes | None:
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image
        with Image.open(path) as pil:
            ex = pil.getexif()
            if not ex:
                return None
            ex[0x0112] = 1           # Orientation: the pixels are upright now
            return ex.tobytes()
    except Exception:  # noqa: BLE001 - no camera details then
        return None


def encode(img: QImage, fmt: str = "PNG") -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, fmt)
    return bytes(buf.data())


def date_text(t: float) -> str:
    return time.strftime("%d %b %Y  %H:%M", time.localtime(t)).lstrip("0")
