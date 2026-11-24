import os

import pytest
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage

import sample_images
from pr7p import edit, exif, imageio
from pr7p.folder import Folder, images_in, natural_key


# ---------------------------------------------------------------- the folder
def touch(folder, *names):
    for n in names:
        (folder / n).write_bytes(b"x")


def test_images_in_a_folder_sorted_like_irfanview(tmp_path):
    touch(tmp_path, "IMG_10.jpg", "IMG_2.JPG", "b.png", "Été.webp", "notes.txt", ".hidden.jpg", "a.avif")
    (tmp_path / "sub.jpg").mkdir()
    assert [os.path.basename(p) for p in images_in(str(tmp_path))] == \
        ["a.avif", "b.png", "Été.webp", "IMG_2.JPG", "IMG_10.jpg"]
    assert natural_key("img_2") < natural_key("IMG_10")


def test_moving_through_the_folder(tmp_path):
    touch(tmp_path, "1.jpg", "2.jpg", "3.jpg")
    f = Folder(str(tmp_path / "2.jpg"))
    assert (f.index, f.count) == (1, 3)
    assert f.step(1).endswith("3.jpg") and f.step(1).endswith("1.jpg")     # round from the last to the first
    f.loop = False
    assert f.step(-1).endswith("1.jpg")                                    # stops at the ends
    f.go(2)
    f.removed(str(tmp_path / "3.jpg"))
    assert f.current.endswith("2.jpg") and f.count == 2
    f.go(0)
    f.removed(str(tmp_path / "1.jpg"))
    assert f.current.endswith("2.jpg")                                     # the next one slides in
    f.renamed(str(tmp_path / "2.jpg"), str(tmp_path / "0.jpg"))
    assert f.current.endswith("0.jpg")
    assert Folder(str(tmp_path)).index == 0                                # a folder: its first picture


# ---------------------------------------------------------------- reading and writing
def test_read_and_information(pictures):
    img = imageio.read(str(pictures[0]))
    assert (img.width(), img.height()) == (600, 400)
    inf = imageio.info(str(pictures[0]), img)
    assert (inf.format, inf.width, inf.height, inf.bpp) == ("JPEG", 600, 400, 24)
    assert inf.colours.startswith("16.7 million") and inf.file_size == pictures[0].stat().st_size
    assert imageio.info(str(pictures[7])).format == "PNG"
    with pytest.raises(imageio.ReadError):
        bad = pictures[0].with_name("broken.jpg")
        bad.write_bytes(b"not a picture")
        imageio.read(str(bad))


def test_the_camera_orientation_is_applied(pictures):
    sample_images.with_exif(pictures[0], orientation=6)     # the camera was turned: 600 x 400 stored
    img = imageio.read(str(pictures[0]))
    assert (img.width(), img.height()) == (400, 600)


def test_camera_details(pictures):
    cam = exif.read(str(pictures[1]))
    assert cam["Camera"] == "FUJIFILM X-T5" and cam["Lens"] == "XF16-55mmF2.8 R LM WR"
    assert cam["Exposure"] == "1/250 s   f/5.6   ISO 200"
    assert cam["Focal length"] == "35 mm (53 mm in 35 mm film)" and cam["Flash"] == "Off"
    assert cam["Taken"] == "3 October 2026, 18:41:07" and cam["GPS"] == "54.5973 N, 5.9301 W"
    assert exif.read(str(pictures[0])) == {}


def test_saving_a_jpeg_keeps_the_camera_details_upright(pictures, tmp_path):
    src = sample_images.with_exif(pictures[2], orientation=6)
    img = imageio.read(str(src))                         # shown upright: 400 x 600
    out = tmp_path / "saved.jpg"
    imageio.write(img, str(out), 85, exif_from=str(src))
    from PIL import Image
    with Image.open(out) as pil:
        assert pil.size == (400, 600) and pil.getexif()[0x0112] == 1        # pixels turned, tag says upright
    assert imageio.read(str(out)).size() == QSize(400, 600)                 # so no viewer turns it twice
    assert exif.read(str(out))["Camera"] == "FUJIFILM X-T5"


@pytest.mark.parametrize("fmt", ["png", "webp", "bmp", "tif", "gif", "jpg"])
def test_every_save_format_reads_back(pictures, tmp_path, fmt):
    img = imageio.read(str(pictures[0]))
    out = tmp_path / f"out.{fmt}"
    imageio.write(img, str(out), 90)
    back = imageio.read(str(out))
    assert back.size() == img.size()
    a, b = img.pixelColor(300, 200), back.pixelColor(300, 200)
    assert abs(a.red() - b.red()) < 40 and abs(a.green() - b.green()) < 40   # the same picture (lossy formats close)
    assert not (tmp_path / f"out.{fmt}.pr7p-tmp").exists()


def test_formats_pillow_adds(pictures, tmp_path):
    """AVIF and PCX aren't Qt's: Pillow reads them."""
    from PIL import Image
    for fmt in ("avif", "pcx"):
        out = tmp_path / f"p.{fmt}"
        with Image.open(pictures[0]) as pil:
            pil.save(out)
        assert imageio.read(str(out)).size() == QSize(600, 400)


# ---------------------------------------------------------------- editing
def solid(w=40, h=20):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#204060"))
    img.setPixelColor(0, 0, QColor("#FF0000"))          # a marker in the top left corner
    return img


def test_rotate_flip_crop_resize():
    img = solid()
    r = edit.rotate(img, 90)
    assert r.size() == QSize(20, 40) and r.pixelColor(19, 0) == QColor("#FF0000")   # top left goes top right
    l = edit.rotate(img, -90)
    assert l.pixelColor(0, 39) == QColor("#FF0000")
    assert edit.flip(img, True).pixelColor(39, 0) == QColor("#FF0000")
    assert edit.flip(img, False).pixelColor(0, 19) == QColor("#FF0000")
    assert edit.crop(img, QRect(10, 5, 15, 10)).size() == QSize(15, 10)
    assert edit.crop(img, QRect(30, 10, 50, 50)).size() == QSize(10, 10)          # clipped to the picture
    assert edit.resize(img, 80, 10).size() == QSize(80, 10)
    c = edit.canvas(img, 60, 40)
    assert c.size() == QSize(60, 40) and c.pixelColor(0, 0) == QColor("white") and c.pixelColor(10, 10) == QColor("#FF0000")
    f = edit.rotate(img, 30, QColor("white"))
    assert f.width() > 40 and f.pixelColor(0, 0) == QColor("white")


def test_colour_commands():
    img = solid()
    g = edit.greyscale(img).pixelColor(5, 5)
    assert g.red() == g.green() == g.blue()
    n = edit.negative(img).pixelColor(5, 5)
    assert (n.red(), n.green(), n.blue()) == (255 - 0x20, 255 - 0x40, 255 - 0x60)
    brighter = edit.colours(img, brightness=50).pixelColor(5, 5)
    assert brighter.red() > 0x20 and brighter.blue() > 0x60
    assert edit.colours(img, saturation=-100).pixelColor(5, 5).saturation() == 0
    flat = QImage(10, 10, QImage.Format.Format_RGB32)
    for x in range(10):
        for y in range(10):
            flat.setPixelColor(x, y, QColor(100 + x * 5, 100 + x * 5, 100 + x * 5))
    stretched = edit.auto_adjust(flat)
    assert stretched.pixelColor(0, 0).red() < 30 and stretched.pixelColor(9, 0).red() > 220
    assert edit.sharpen(img).size() == img.size()
