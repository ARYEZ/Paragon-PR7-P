import json
import os
import sys
import time

import pytest
from PySide6.QtCore import QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage

from pr7p import __version__, app, imageio, settings, theme
from pr7p.viewer import FIT, FIT_BIG, fit_scale, step_zoom


def test_zoom_rules():
    assert fit_scale(QSize(4000, 2000), QSize(1000, 1000), FIT_BIG) == 0.25
    assert fit_scale(QSize(400, 200), QSize(1000, 1000), FIT_BIG) == 1.0       # small pictures aren't blown up
    assert fit_scale(QSize(400, 200), QSize(1000, 1000), FIT) == 2.5
    assert fit_scale(QSize(400, 200), QSize(1000, 1000), 150) == 1.5
    assert step_zoom(100, True) == 150 and step_zoom(100, False) == 70 and step_zoom(110, False) == 100


def test_starts_empty(window):
    assert window.image.isNull() and window.windowTitle() == "Paragon PR7-P"
    assert not window.k_save.isEnabled() and not window.acts["delete"].isEnabled()


def test_open_and_move_through_the_folder(window, pictures):
    window.open_path(str(pictures[2]))
    assert window.windowTitle() == "IMG_2043.jpg - Paragon PR7-P"
    assert window.stat["pos"].text() == "3/8" and window.stat["dims"].text() == "600 x 400 x 24 BPP"
    assert window.stat["name"].text() == "IMG_2043.jpg" and window.strip.current == 2
    window.step(1)
    assert window.path == str(pictures[3]) and window.image.size() == QSize(400, 600)   # the upright one
    window.go(7)
    window.step(1)
    assert window.path == str(pictures[0])                                               # round to the first
    window.acts["last"].trigger()
    assert window.path == str(pictures[7]) and window.stat["dims"].text().startswith("600 x 400")
    window.view.step.emit(-1)                                                            # the wheel
    assert window.path == str(pictures[6])
    window.open_path(str(pictures[0].parent))                                             # a folder: its first
    assert window.path == str(pictures[0])


def test_zoom(window, pictures):
    window.open_path(str(pictures[0]))
    assert window.view.zoom_percent() == 100                         # 600 x 400 fits: fit only big images
    window.set_zoom(FIT)
    assert window.view.zoom_percent() > 100
    window.set_zoom(50.0)
    assert window.stat["zoom"].text() == "50 %"
    window.view.zoom_step(True)
    assert window.view.zoom_percent() == 70


def test_edit_save_and_undo(window, pictures, qapp):
    window.open_path(str(pictures[1]))           # has camera details
    window.acts["rotate_right"].trigger()
    assert window.image.size() == QSize(400, 600) and window.modified and window.windowTitle().startswith("IMG_2042.jpg *")
    window.acts["undo"].trigger()
    assert window.image.size() == QSize(600, 400) and not window.modified
    window.acts["redo"].trigger()
    assert window.modified
    window.view.set_selection(QRect(0, 0, 200, 300))
    window.acts["crop"].trigger()
    assert window.image.size() == QSize(200, 300)
    window.acts["save"].trigger()
    assert not window.modified
    saved = imageio.read(str(pictures[1]))
    assert saved.size() == QSize(200, 300)                                     # really written over the file
    from pr7p import exif
    assert exif.read(str(pictures[1]))["Camera"] == "FUJIFILM X-T5"            # camera details kept


def test_leaving_a_changed_picture_asks(window, pictures):
    window.open_path(str(pictures[0]))
    window.acts["negative"].trigger()
    window.answers["save_changes"] = "cancel"
    window.step(1)
    assert window.path == str(pictures[0]) and window.modified           # stayed
    window.answers["save_changes"] = "discard"
    window.step(1)
    assert window.path == str(pictures[1]) and not window.modified
    assert imageio.read(str(pictures[0])).pixelColor(10, 10) != QColor("white")   # not saved: unchanged on disk


def test_save_as_another_format(window, pictures):
    window.open_path(str(pictures[0]))
    window.acts["grey"].trigger()
    out = pictures[0].parent / "grey.png"
    window.answers["save_as"] = str(out)
    window.acts["save_as"].trigger()
    back = QImage(str(out))
    c = back.pixelColor(300, 200)
    assert back.size() == QSize(600, 400) and c.red() == c.green() == c.blue()
    assert window.path == str(out) and window.folder.count == 9


def test_delete_goes_to_the_recycle_bin(window, pictures, own_trash):
    window.open_path(str(pictures[3]))
    window.answers["delete"] = True
    window.acts["delete"].trigger()
    assert not pictures[3].exists() and (own_trash / pictures[3].name).exists()    # in the bin, not gone
    assert window.path == str(pictures[4]) and window.folder.count == 7
    window.go(6)
    window.acts["delete"].trigger()
    assert window.path == str(pictures[6]) and window.folder.count == 6          # the last: the one before


def test_copy_move_rename(window, pictures, tmp_path):
    dest = tmp_path / "Holiday"
    dest.mkdir()
    window.open_path(str(pictures[0]))
    window.answers["folder"] = str(dest)
    window.acts["copy_to"].trigger()
    assert (dest / pictures[0].name).exists() and pictures[0].exists()
    window.acts["copy_to"].trigger()
    assert (dest / "IMG_2041 (2).jpg").exists()                                  # never overwrites
    window.acts["move_to"].trigger()
    assert not pictures[0].exists() and window.path == str(pictures[1])
    window.answers["rename"] = "Beach.jpg"
    window.acts["rename"].trigger()
    assert (pictures[1].parent / "Beach.jpg").exists() and window.path.endswith("Beach.jpg")
    errors = []
    window.answers["error"] = errors.append
    window.answers["rename"] = "bad:name.jpg"
    window.acts["rename"].trigger()
    assert errors and "can't contain" in errors[0]


def test_information(window, pictures, qapp):
    window.answers["info"] = True
    window.open_path(str(pictures[1]))
    window.information()
    v = window.info_dialog.values()
    assert v["File name"] == "IMG_2042.jpg" and v["Original size"] == "600 x 400 pixels (0.24 MP)"
    assert v["Format"].startswith("JPEG") and v["Camera"] == "FUJIFILM X-T5" and v["Exposure"].startswith("1/250 s")
    window.info_dialog.copy()
    assert "Camera: FUJIFILM X-T5" in qapp.clipboard().text()


def test_thumbnails_grid(window, pictures):
    window.open_path(str(pictures[2]))
    window.acts["thumbnails"].trigger()
    g = window.grid
    assert window.stack.currentWidget() is g and g.files == [str(p) for p in pictures] and g.current == 2
    assert all(not window.thumbs.get(str(p)).isNull() for p in pictures)
    assert g._size_text(str(pictures[3])).startswith("400 x 600")
    g.selected = {4, 5}
    window.answers["delete"] = True
    window.acts["delete"].trigger()
    assert not pictures[4].exists() and not pictures[5].exists() and len(g.files) == 6
    g.activated.emit(0)
    assert window.stack.currentWidget() is window.view and window.path == str(pictures[0])


def test_copy_paste_and_fullscreen(window, pictures, qapp):
    window.open_path(str(pictures[0]))
    window.view.set_selection(QRect(10, 10, 50, 40))
    window.acts["copy"].trigger()
    assert qapp.clipboard().image().size() == QSize(50, 40)
    window.acts["paste"].trigger()
    assert window.path is None and window.image.size() == QSize(50, 40) and window.modified
    window.answers["save_changes"] = "discard"
    window.open_path(str(pictures[0]))
    window.toggle_fullscreen()
    assert window.fullscreen and window.view.fullscreen and not window.menuBar().isVisible()
    window._escape()
    assert not window.fullscreen and window.menuBar().isVisible()


def test_slideshow(window, pictures):
    window.open_path(str(pictures[0]))
    window.start_slideshow(0.5)
    assert window.fullscreen and window.slideshow.isActive()
    window._slide(); window._slide()
    assert window.path == str(pictures[2])
    window._escape()
    assert not window.slideshow.isActive() and not window.fullscreen


def test_animated_gif_plays(window, tmp_path):
    from PIL import Image
    frames = [Image.new("RGB", (40, 30), c) for c in ((200, 0, 0), (0, 0, 200), (200, 120, 0))]
    gif = tmp_path / "anim.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50, loop=0)
    window.open_path(str(gif))
    assert window.view.movie is not None and window.view.movie.frameCount() == 3


def test_finish(window, pictures):
    window.open_path(str(pictures[0]))
    window.set_finish("aurora")
    assert theme.FINISH == "aurora" and settings.get("finish") == "aurora"
    window.set_finish("obsidian")


# ---------------------------------------------------------------- the command line
def test_version(capsys):
    assert app.main(["--version"]) == 0 and capsys.readouterr().out.strip() == __version__


def test_command_line():
    assert app.parse(["a.jpg", "--new-window"]) == (os.path.abspath("a.jpg"), True)
    assert app.parse([]) == (None, False)


def test_a_second_launch_shows_its_picture_in_the_open_window(window, pictures, qapp):
    import subprocess
    assert app.listen(window) is not None
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from PySide6.QtCore import QCoreApplication; "
            "a = QCoreApplication([]); from pr7p import app; sys.exit(0 if app.hand_over(sys.argv[2]) else 1)")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen([sys.executable, "-c", code, root, str(pictures[4])])
    deadline = time.time() + 20
    while (window.path != str(pictures[4]) or proc.poll() is None) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert proc.wait(5) == 0 and window.path == str(pictures[4])
    window.instance_server.close()


def test_selftest(pictures, tmp_path, qapp):
    out = tmp_path / "out.json"
    assert app.selftest(str(pictures[0].parent), str(out)) == 0
    got = json.loads(out.read_text())
    assert len(got["names"]) == 8 and got["thumbs"] and got["fonts"]
    assert got["sizes"]["IMG_2044.jpg"] == [400, 600] and got["cameras"] == {"IMG_2042.jpg": "FUJIFILM X-T5"}
