"""PR7-P's window: IrfanView's menus, keys and status line, ImageGlass's thumbnail strip, IrfanView's Thumbnails grid,
Image > Information, the editing commands with Undo, slideshow and full screen.

Anything that would ask the user goes through `_ask(kind, ...)`; tests answer with `window.answers[kind]`."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import finish
from . import __version__, edit, exif, files, imageio, settings, theme, widgets
from .folder import IMAGE_EXTS, Folder, is_image
from .thumbs import Grid, Strip, Thumbs
from .viewer import FIT, FIT_BIG, ImageView

OPEN_FILTER = "Images (" + " ".join(f"*.{e}" for e in sorted(IMAGE_EXTS)) + ");;All files (*)"
SAVE_FILTERS = {"jpg": "JPEG (*.jpg)", "png": "PNG (*.png)", "webp": "WebP (*.webp)", "bmp": "BMP (*.bmp)",
                "tif": "TIFF (*.tif)", "gif": "GIF (*.gif)", "avif": "AVIF (*.avif)"}
ZOOM_CHOICES = [("Fit only big images", FIT_BIG), ("Fit to window", FIT), ("Original size", 100.0)] + \
               [(f"{z}%", float(z)) for z in (400, 200, 150, 100, 75, 50, 25)]

EXTRA = """
QWidget#status {{ background: {bg}; border-top: 1px solid {edge}; }}
QLabel#stat {{ color: {dim}; font-size: 12px; }}
QLabel#statname {{ color: {text}; font-size: 12px; }}
QLabel#key {{ color: {dim}; font-weight: 600; font-size: 11px; }}
QLabel#head {{ color: {text}; font-weight: 600; font-size: 12px; padding-top: 8px; }}
"""


def stylesheet() -> str:
    return theme.stylesheet() + EXTRA.format(bg=theme.BACKGROUND, edge=theme.PANEL_EDGE, dim=theme.TEXT_DIM,
                                             text=theme.TEXT)


def apply_look(app: QApplication) -> None:
    app.setPalette(theme.palette())
    app.setStyleSheet(stylesheet())


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None, thumbs_sync: bool = False):
        super().__init__()
        self.answers: dict = {}
        self.folder = Folder(loop=settings.get_bool("loop_folder", True))
        self.thumbs = Thumbs(sync=thumbs_sync, parent=self)
        self.image = QImage()
        self.path: str | None = None          # the file shown (None: pasted from the clipboard)
        self.undo_stack: list[QImage] = []
        self.redo_stack: list[QImage] = []
        self.modified = False
        self.fullscreen = False
        self.slideshow = QTimer(self)
        self.slideshow.timeout.connect(self._slide)
        self.setAcceptDrops(True)
        self.resize(1280, 820)
        self._build()
        self._build_menus()
        self._sync()
        if path:
            self.open_path(path)

    # ================================================================== building
    def _key(self, icon, tip, slot, checkable=False):
        k = widgets.SmallKey(icon, tip, checkable)
        k.clicked.connect(slot)
        return k

    def _build(self):
        central = QWidget()
        col = QVBoxLayout(central)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.header = widgets.Header("IMAGE VIEWER")
        col.addWidget(self.header)
        self.toolbar = QWidget()
        bar = QHBoxLayout(self.toolbar)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(4)

        def gap():
            line = QFrame(); line.setFixedSize(1, 22); line.setObjectName("gap")
            line.setStyleSheet(f"background: {theme.PANEL_EDGE};")
            bar.addSpacing(6); bar.addWidget(line); bar.addSpacing(6)

        bar.addWidget(self._key("open", "Open (O)", self.open_dialog))
        self.k_save = self._key("save", "Save as (S)", self.save_as); bar.addWidget(self.k_save)
        gap()
        self.k_prev = self._key("left", "Previous image (Left)", lambda: self.step(-1)); bar.addWidget(self.k_prev)
        self.k_next = self._key("right", "Next image (Right)", lambda: self.step(1)); bar.addWidget(self.k_next)
        gap()
        self.k_zout = self._key("zoomout", "Zoom out (-)", lambda: self.view.zoom_step(False)); bar.addWidget(self.k_zout)
        self.k_zin = self._key("zoomin", "Zoom in (+)", lambda: self.view.zoom_step(True)); bar.addWidget(self.k_zin)
        self.zoom_box = QComboBox()
        self.zoom_box.setFixedWidth(170)
        for text, _ in ZOOM_CHOICES:
            self.zoom_box.addItem(text)
        self.zoom_box.activated.connect(lambda i: self.set_zoom(ZOOM_CHOICES[i][1]))
        bar.addSpacing(4); bar.addWidget(self.zoom_box)
        self.k_fit = self._key("fit", "Fit images to window (Shift+F)", lambda: self.set_zoom(
            FIT_BIG if self.view.zoom == FIT else FIT), True)
        bar.addWidget(self.k_fit)
        self.k_actual = self._key("actual", "Original size (Ctrl+H)", lambda: self.set_zoom(100.0)); bar.addWidget(self.k_actual)
        gap()
        self.k_rotl = self._key("rotleft", "Rotate left (L)", lambda: self.apply(lambda i: edit.rotate(i, -90)))
        self.k_rotr = self._key("rotate", "Rotate right (R)", lambda: self.apply(lambda i: edit.rotate(i, 90)))
        self.k_flip = self._key("flip", "Horizontal flip (H)", lambda: self.apply(lambda i: edit.flip(i, True)))
        self.k_crop = self._key("crop", "Crop selection (Ctrl+Y)", self.crop)
        for k in (self.k_rotl, self.k_rotr, self.k_flip, self.k_crop):
            bar.addWidget(k)
        gap()
        self.k_thumbs = self._key("thumbs", "Thumbnails (T)", self.toggle_thumbnails, True); bar.addWidget(self.k_thumbs)
        self.k_slide = self._key("play", "Slideshow (W)", self.slideshow_dialog); bar.addWidget(self.k_slide)
        self.k_full = self._key("fullscreen", "Full screen (Enter)", self.toggle_fullscreen); bar.addWidget(self.k_full)
        self.k_info = self._key("info", "Information (I)", self.information); bar.addWidget(self.k_info)
        bar.addStretch(1)
        self.k_delete = self._key("trash", "Delete (Del)", self.delete); bar.addWidget(self.k_delete)
        col.addWidget(self.toolbar)

        self.stack = QStackedWidget()
        self.view = ImageView()
        self.view.step.connect(self.step)
        self.view.zoomChanged.connect(lambda _z: self._sync_status())
        self.view.selectionChanged.connect(lambda _r: self._sync())
        self.view.fullscreenRequested.connect(self.toggle_fullscreen)
        self.view.customContextMenuRequested.connect(self._view_menu)
        self.view.zoom = self._default_zoom()
        self.grid = Grid(self.thumbs)
        self.grid.activated.connect(self._grid_open)
        self.grid.selectionChanged.connect(self._sync)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.grid)
        col.addWidget(self.stack, 1)
        self.strip = Strip(self.thumbs)
        self.strip.activated.connect(self.go)
        col.addWidget(self.strip)

        self.statusw = QWidget(); self.statusw.setObjectName("status")
        sl = QHBoxLayout(self.statusw)
        sl.setContentsMargins(14, 4, 14, 6)
        sl.setSpacing(26)
        self.stat = {}
        for key in ("dims", "pos", "zoom", "size", "date"):
            lab = QLabel(""); lab.setObjectName("stat"); sl.addWidget(lab); self.stat[key] = lab
        sl.addStretch(1)
        self.stat["name"] = QLabel(""); self.stat["name"].setObjectName("statname"); sl.addWidget(self.stat["name"])
        col.addWidget(self.statusw)
        self.setCentralWidget(central)

    def _act(self, menu, text, slot=None, shortcut=None, checkable=False, key=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcuts([QKeySequence(s) for s in (shortcut if isinstance(shortcut, (list, tuple)) else [shortcut])])
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setCheckable(checkable)
        if slot:
            a.triggered.connect(slot)
        if menu is not None:
            menu.addAction(a)
        else:
            self.addAction(a)
        if key:
            self.acts[key] = a
        return a

    def _build_menus(self):
        self.acts: dict[str, QAction] = {}
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "&Open...", self.open_dialog, "O", key="open")
        self.recent_menu = f.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        f.addSeparator()
        self._act(f, "&Thumbnails", self.toggle_thumbnails, "T", True, key="thumbnails")
        self._act(f, "&Slideshow...", self.slideshow_dialog, "W", key="slideshow")
        f.addSeparator()
        self._act(f, "&Save", self.save, "Ctrl+S", key="save")
        self._act(f, "Save &as...", self.save_as, "S", key="save_as")
        self._act(f, "&Print...", self.print_image, "Ctrl+P", key="print")
        f.addSeparator()
        self._act(f, "Copy &to...", lambda: self.copy_move(False), "F8", key="copy_to")
        self._act(f, "&Move to...", lambda: self.copy_move(True), "F7", key="move_to")
        self._act(f, "Re&name...", self.rename, "F2", key="rename")
        self._act(f, "&Delete", self.delete, "Del", key="delete")
        self._act(f, "Show in &folder", self.show_in_folder, key="folder")
        f.addSeparator()
        self._act(f, "E&xit", self.close, key="exit")

        e = mb.addMenu("&Edit")
        self._act(e, "&Undo", self.undo, "Ctrl+Z", key="undo")
        self._act(e, "&Redo", self.redo, ["Ctrl+Shift+Z"], key="redo")
        e.addSeparator()
        self._act(e, "&Copy", self.copy, "Ctrl+C", key="copy")
        self._act(e, "&Paste", self.paste, "Ctrl+V", key="paste")
        self._act(e, "Cr&op selection", self.crop, ["Ctrl+Y", "Ctrl+Shift+Y"], key="crop")
        e.addSeparator()
        self._act(e, "Select &all", self.select_all, "Ctrl+A", key="select_all")
        self._act(e, "&Clear selection", lambda: self.view.set_selection(QRect()), key="clear_selection")

        im = mb.addMenu("&Image")
        self._act(im, "&Information...", self.information, "I", key="info")
        im.addSeparator()
        self._act(im, "Rotate &left", lambda: self.apply(lambda i: edit.rotate(i, -90)), "L", key="rotate_left")
        self._act(im, "Rotate &right", lambda: self.apply(lambda i: edit.rotate(i, 90)), "R", key="rotate_right")
        self._act(im, "Custom / fine &rotation...", self.fine_rotation, "Ctrl+U", key="fine_rotation")
        self._act(im, "&Vertical flip", lambda: self.apply(lambda i: edit.flip(i, False)), "V", key="flip_v")
        self._act(im, "&Horizontal flip", lambda: self.apply(lambda i: edit.flip(i, True)), "H", key="flip_h")
        im.addSeparator()
        self._act(im, "Resi&ze / resample...", self.resize_dialog, "Ctrl+R", key="resize")
        self._act(im, "Change &canvas size...", self.canvas_dialog, "Shift+V", key="canvas")
        im.addSeparator()
        self._act(im, "&Auto-adjust colours", lambda: self.apply(edit.auto_adjust), "Shift+U", key="auto")
        self._act(im, "&Sharpen", lambda: self.apply(edit.sharpen), "Shift+S", key="sharpen")
        self._act(im, "Colour &corrections...", self.colour_dialog, "Shift+G", key="colours")
        self._act(im, "Convert to &greyscale", lambda: self.apply(edit.greyscale), "Ctrl+G", key="grey")
        self._act(im, "&Negative", lambda: self.apply(edit.negative), "Ctrl+Shift+N", key="negative")
        im.addSeparator()
        self._act(im, "Set as &wallpaper", self.wallpaper, key="wallpaper")

        o = mb.addMenu("&Options")
        fin = o.addMenu("&Finish")
        fg = QActionGroup(self)
        for name in theme.FINISHES:
            a = self._act(fin, name.upper(), lambda _=False, n=name: self.set_finish(n), None, True, key=f"finish_{name}")
            a.setChecked(name == theme.FINISH)
            fg.addAction(a)
        self._act(o, "&Properties / settings...", self.options, "P", key="options")
        o.addSeparator()
        self._act(o, "Check for &updates...", self.check_updates, key="updates")

        v = mb.addMenu("&View")
        zg = QActionGroup(self)
        zg.addAction(self._act(v, "&Fit images to window", lambda: self.set_zoom(FIT), "Shift+F", True, key="zoom_fit"))
        zg.addAction(self._act(v, "Fit &only big images", lambda: self.set_zoom(FIT_BIG), None, True, key="zoom_fitbig"))
        zg.addAction(self._act(v, "&Original size", lambda: self.set_zoom(100.0), "Ctrl+H", True, key="zoom_100"))
        self._act(v, "Zoom &in", lambda: self.view.zoom_step(True), ["+", "="], key="zoom_in")
        self._act(v, "Zoom o&ut", lambda: self.view.zoom_step(False), "-", key="zoom_out")
        v.addSeparator()
        self._act(v, "Full &screen", self.toggle_fullscreen, ["Return", "Enter", "F11"], key="fullscreen")
        v.addSeparator()
        self._act(v, "Show &toolbar", lambda on: self._show("toolbar", on), None, True, key="show_toolbar")
        self._act(v, "Show &status bar", lambda on: self._show("statusbar", on), None, True, key="show_statusbar")
        self._act(v, "Show thumbnail &strip", lambda on: self._show("strip", on), None, True, key="show_strip")
        v.addSeparator()
        self._act(v, "&Next image", lambda: self.step(1), ["Right", "Space", "PgDown"], key="next")
        self._act(v, "&Previous image", lambda: self.step(-1), ["Left", "Backspace", "PgUp"], key="prev")
        self._act(v, "&First image", lambda: self.go(0), "Home", key="first")
        self._act(v, "&Last image", lambda: self.go(self.folder.count - 1), "End", key="last")

        h = mb.addMenu("&Help")
        self._act(h, "&Keyboard shortcuts", self.shortcuts, "F1", key="shortcuts")
        self._act(h, "&About Paragon PR7-P", self.about, key="about")
        self._act(None, "", self._escape, "Escape", key="escape")
        for k, s in (("toolbar", "show_toolbar"), ("statusbar", "show_statusbar"), ("strip", "show_strip")):
            on = settings.get_bool(f"show_{k}", True)
            self.acts[s].setChecked(on)
            self._show(k, on, save=False)

    # ================================================================== asking
    def _ask(self, kind: str, *args):
        if kind in self.answers:
            a = self.answers[kind]
            return a(*args) if callable(a) else a
        if kind == "open":
            path, _ = QFileDialog.getOpenFileName(self, "Open", settings.get("last_dir", ""), OPEN_FILTER)
            return path or None
        if kind == "save_as":
            name, fmt = args
            filters = ";;".join(SAVE_FILTERS.values())
            path, chosen = QFileDialog.getSaveFileName(self, "Save As", name, filters, SAVE_FILTERS.get(fmt, ""))
            if path and not os.path.splitext(path)[1]:
                for ext_, flt in SAVE_FILTERS.items():
                    if flt == chosen:
                        path += "." + ext_
            return path or None
        if kind == "save_changes":
            b = QMessageBox.question(self, "Paragon PR7-P", f"{args[0]} has been changed. Save the changes?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                     QMessageBox.StandardButton.Cancel)
            return {QMessageBox.StandardButton.Save: "save", QMessageBox.StandardButton.Discard: "discard"}.get(b, "cancel")
        if kind == "delete":
            if not settings.get_bool("confirm_delete", True):
                return True
            return QMessageBox.question(self, "Delete", f"Move {args[0]} to the Recycle Bin?") == \
                QMessageBox.StandardButton.Yes
        if kind == "folder":
            return QFileDialog.getExistingDirectory(self, args[0], settings.get("last_copy_dir", "")) or None
        if kind == "rename":
            text, ok = QInputDialog.getText(self, "Rename", "New name:", QLineEdit.EchoMode.Normal, args[0])
            return text if ok else None
        if kind == "rotation":
            v, ok = QInputDialog.getDouble(self, "Custom / Fine Rotation", "Angle (degrees, clockwise):", 0, -360,
                                           360, 1)
            return v if ok else None
        if kind in ("resize", "canvas", "colours", "slideshow"):
            return self._dialog(kind, *args)
        if kind == "error":
            QMessageBox.warning(self, "Paragon PR7-P", args[0])
            return None
        return None

    def _dialog(self, kind, *args):
        d = QDialog(self)
        form = QFormLayout(d)
        out = {}
        if kind in ("resize", "canvas"):
            w0, h0 = args
            d.setWindowTitle("Resize / Resample" if kind == "resize" else "Change Canvas Size")
            ws, hs = QSpinBox(), QSpinBox()
            for s, v in ((ws, w0), (hs, h0)):
                s.setRange(1, 65535); s.setValue(v); s.setSuffix(" px")
            keep = QCheckBox("Keep proportions"); keep.setChecked(kind == "resize")
            lock = {"busy": False}

            def follow(src, dst, ratio):
                if keep.isChecked() and not lock["busy"]:
                    lock["busy"] = True
                    dst.setValue(max(1, round(src.value() * ratio)))
                    lock["busy"] = False
            ws.valueChanged.connect(lambda _v: follow(ws, hs, h0 / w0))
            hs.valueChanged.connect(lambda _v: follow(hs, ws, w0 / h0))
            form.addRow("WIDTH", ws); form.addRow("HEIGHT", hs); form.addRow(keep)
            out["get"] = lambda: (ws.value(), hs.value())
        elif kind == "colours":
            d.setWindowTitle("Colour Corrections")
            sliders = {}
            for name in ("brightness", "contrast", "saturation"):
                s = QSlider(Qt.Orientation.Horizontal); s.setRange(-100, 100); s.setValue(0)
                form.addRow(name.upper(), s); sliders[name] = s
            g = QDoubleSpinBox(); g.setRange(0.1, 6.99); g.setSingleStep(0.05); g.setValue(1.0)
            form.addRow("GAMMA", g)
            out["get"] = lambda: {**{k: s.value() for k, s in sliders.items()}, "gamma": g.value()}
        else:
            d.setWindowTitle("Slideshow")
            secs = QDoubleSpinBox(); secs.setRange(0.5, 600); secs.setValue(settings.get_float("slide_seconds", 3.0))
            secs.setSuffix(" s")
            form.addRow("NEXT IMAGE AFTER", secs)
            out["get"] = lambda: secs.value()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        form.addRow(bb)
        return out["get"]() if d.exec() == QDialog.DialogCode.Accepted else None

    # ================================================================== opening and moving through the folder
    def _default_zoom(self):
        z = settings.get("default_zoom", FIT_BIG)
        if z in (FIT, FIT_BIG):
            return z
        try:
            return float(z)
        except ValueError:
            return FIT_BIG

    def open_dialog(self):
        path = self._ask("open")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        """Open a picture (its folder becomes the one to move through) or a folder (its first picture)."""
        if not self._may_leave():
            return False
        path = os.path.abspath(path)
        if not os.path.exists(path):
            self._ask("error", f"{path}\n\nThe file doesn't exist.")
            return False
        self.folder.open(path)
        settings.set("last_dir", os.path.dirname(path) if os.path.isfile(path) else path)
        if os.path.isfile(path):
            self._remember_recent(path)
        self.strip.set_files(self.folder.files, self.folder.index)
        if self.stack.currentWidget() is self.grid:
            self._fill_grid()
        return self._load()

    def _load(self) -> bool:
        path = self.folder.current
        self.undo_stack.clear(); self.redo_stack.clear()
        self.modified = False
        if path is None:
            self.path, self.image = None, QImage()
            self.view.set_image(QImage())
            self._sync()
            return False
        try:
            img = imageio.read(path)
        except imageio.ReadError as e:
            self.path, self.image = path, QImage()
            self.view.set_image(QImage())
            self._sync()
            self._ask("error", f"PR7-P couldn't read this picture:\n{e}")
            return False
        self.path, self.image = path, img
        self.view.zoom = self.view.zoom if settings.get_bool("keep_zoom", False) else self._default_zoom()
        animated = imageio.frame_count(path) > 1
        self.view.set_image(img, path if animated else None)
        self.strip.set_current(self.folder.index)
        self._sync()
        return True

    def step(self, delta: int) -> None:
        if self.folder.count and self._may_leave():
            self.folder.step(delta)
            self._load()

    def go(self, index: int) -> None:
        if self.folder.count and self._may_leave():
            self.folder.go(index)
            self._load()

    def _may_leave(self) -> bool:
        """IrfanView's question when leaving a changed picture: save, don't save, or stay."""
        if not self.modified:
            return True
        answer = self._ask("save_changes", os.path.basename(self.path) if self.path else "The picture")
        if answer == "save":
            return self.save()
        return answer == "discard"

    def _remember_recent(self, path: str) -> None:
        recent = [p for p in settings.get_list("recent") if os.path.normcase(p) != os.path.normcase(path)]
        settings.set("recent", [path] + recent[:9])

    def _fill_recent(self):
        self.recent_menu.clear()
        for i, p in enumerate([p for p in settings.get_list("recent") if os.path.exists(p)][:10], 1):
            a = self.recent_menu.addAction(f"&{i % 10} {os.path.basename(p)}")
            a.setToolTip(p)
            a.triggered.connect(lambda _=False, x=p: self.open_path(x))
        self.recent_menu.setEnabled(True)

    # ================================================================== the toolbar, menus and status follow
    def _sync(self):
        has = not self.image.isNull()
        in_folder = self.folder.count > 0 and self.path is not None
        sel = not self.view.selection.isNull()
        name = os.path.basename(self.path) if self.path else ("Clipboard" if has else "")
        self.setWindowTitle(f"{name}{' *' if self.modified else ''} - Paragon PR7-P" if name else "Paragon PR7-P")
        for k in (self.k_save, self.k_zout, self.k_zin, self.zoom_box, self.k_fit, self.k_actual, self.k_rotl,
                  self.k_rotr, self.k_flip, self.k_info, self.k_full):
            k.setEnabled(has)
        self.k_crop.setEnabled(has and sel)
        for k in (self.k_prev, self.k_next, self.k_slide):
            k.setEnabled(self.folder.count > 1)
        self.k_delete.setEnabled(in_folder or bool(self.grid.selected_files()))
        for key in ("save_as", "print", "copy", "select_all", "info", "rotate_left", "rotate_right", "fine_rotation",
                    "flip_v", "flip_h", "resize", "canvas", "auto", "sharpen", "colours", "grey", "negative",
                    "zoom_fit", "zoom_fitbig", "zoom_100", "zoom_in", "zoom_out", "fullscreen", "clear_selection"):
            self.acts[key].setEnabled(has)
        self.acts["save"].setEnabled(has and (self.modified or self.path is None))
        self.acts["crop"].setEnabled(has and sel)
        self.acts["undo"].setEnabled(bool(self.undo_stack))
        self.acts["redo"].setEnabled(bool(self.redo_stack))
        for key in ("copy_to", "move_to", "rename", "delete", "folder", "wallpaper"):
            self.acts[key].setEnabled(in_folder)
        for key in ("next", "prev", "first", "last", "slideshow"):
            self.acts[key].setEnabled(self.folder.count > 1)
        z = self.view.zoom
        self.acts["zoom_fit"].setChecked(z == FIT)
        self.acts["zoom_fitbig"].setChecked(z == FIT_BIG)
        self.acts["zoom_100"].setChecked(z == 100.0)
        self.k_fit.setChecked(z == FIT)
        self._sync_status()

    def _sync_status(self):
        img, path = self.image, self.path
        has = not img.isNull()
        self.stat["dims"].setText(f"{img.width()} x {img.height()} x {24 if not img.hasAlphaChannel() else 32} BPP"
                                  if has else "")
        self.stat["pos"].setText(f"{self.folder.index + 1}/{self.folder.count}" if path and self.folder.count else "")
        self.stat["zoom"].setText(f"{self.view.zoom_percent():.0f} %" if has else "")
        if has and path and os.path.exists(path):
            st = os.stat(path)
            self.stat["size"].setText(f"{st.st_size / 1024 / 1024:.2f} MB / {img.width() * img.height() / 1e6:.2f} MP")
            self.stat["date"].setText(imageio.date_text(st.st_mtime))
        else:
            self.stat["size"].setText(f"{img.width() * img.height() / 1e6:.2f} MP" if has else "")
            self.stat["date"].setText("")
        self.stat["name"].setText((os.path.basename(path) if path else ("Clipboard" if has else "")) +
                                  (" *" if self.modified else ""))
        z = self.view.zoom
        label = {FIT: "Fit to window", FIT_BIG: "Fit only big images"}[z] if z in (FIT, FIT_BIG) else f"{float(z):g}%"
        i = self.zoom_box.findText(label)
        if i < 0:
            self.zoom_box.addItem(label)
            i = self.zoom_box.count() - 1
        self.zoom_box.setCurrentIndex(i)

    def _show(self, what: str, on: bool, save: bool = True):
        {"toolbar": self.toolbar, "statusbar": self.statusw, "strip": self.strip}[what].setVisible(bool(on) and
                                                                                               not self.fullscreen)
        if save:
            settings.set(f"show_{what}", bool(on))

    def set_zoom(self, z) -> None:
        self.view.set_zoom(z)
        self.view.setFocus()
        self._sync()

    # ================================================================== editing
    def apply(self, fn) -> None:
        """Run an Image menu command on the picture (or a whole animation's first frame) with Undo."""
        if self.image.isNull():
            return
        out = fn(self.image)
        if out is None or out.isNull():
            return
        self.undo_stack.append(self.image)
        del self.undo_stack[:-20]                 # keep the last 20 steps (pictures are big)
        self.redo_stack.clear()
        self._set_image(out)

    def _set_image(self, img: QImage) -> None:
        self.image = img
        self.modified = True
        self.view.set_image(img)
        self._sync()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.image)
            self.image = self.undo_stack.pop()
            self.modified = bool(self.undo_stack) or self.path is None
            self.view.set_image(self.image)
            self._sync()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.image)
            self._set_image(self.redo_stack.pop())

    def crop(self):
        r = self.view.selection
        if not r.isNull():
            self.apply(lambda i: edit.crop(i, r))

    def select_all(self):
        self.view.select_all()
        self._sync()

    def fine_rotation(self):
        deg = self._ask("rotation")
        if deg:
            self.apply(lambda i: edit.rotate(i, float(deg), QColor("white")))

    def resize_dialog(self):
        got = self._ask("resize", self.image.width(), self.image.height())
        if got:
            self.apply(lambda i: edit.resize(i, *got))

    def canvas_dialog(self):
        got = self._ask("canvas", self.image.width(), self.image.height())
        if got:
            self.apply(lambda i: edit.canvas(i, *got))

    def colour_dialog(self):
        got = self._ask("colours")
        if got:
            self.apply(lambda i: edit.colours(i, **got))

    def copy(self):
        if self.image.isNull():
            return
        r = self.view.selection
        QGuiApplication.clipboard().setImage(self.image.copy(r) if not r.isNull() else self.image)

    def paste(self):
        img = QGuiApplication.clipboard().image()
        if img.isNull() or not self._may_leave():
            return
        self.path = None
        self.image = img
        self.undo_stack.clear(); self.redo_stack.clear()
        self.modified = True                      # nothing saved yet
        self.view.set_image(img)
        self._sync()

    # ================================================================== saving
    def save(self) -> bool:
        """Ctrl+S: write the changes over the file (in its own format); a pasted picture asks where."""
        if self.image.isNull():
            return False
        if self.path is None or not is_image(self.path):
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        if self.image.isNull():
            return False
        base = os.path.splitext(os.path.basename(self.path))[0] if self.path else "Clipboard"
        fmt = (os.path.splitext(self.path)[1][1:].lower() if self.path else "png") or "png"
        start = os.path.join(os.path.dirname(self.path) if self.path else settings.get("last_dir", ""),
                             f"{base}.{fmt if fmt in SAVE_FILTERS else 'png'}")
        target = self._ask("save_as", start, fmt)
        if not target:
            return False
        if not self._write(target):
            return False
        if self.path is None or os.path.dirname(os.path.abspath(target)) == os.path.dirname(self.path or ""):
            self.folder.open(target)
            self.strip.set_files(self.folder.files, self.folder.index)
            self.path = os.path.abspath(target)
            self._sync()
        return True

    def _write(self, target: str) -> bool:
        try:
            imageio.write(self.image, target, settings.get_int("jpeg_quality", 90), exif_from=self.path)
        except Exception as e:  # noqa: BLE001 - shown to the user
            self._ask("error", f"Couldn't save {os.path.basename(target)}:\n{e}")
            return False
        if self.path and os.path.normcase(os.path.abspath(target)) == os.path.normcase(self.path):
            self.modified = False
            self.undo_stack.clear(); self.redo_stack.clear()
            self.thumbs.forget(self.path)
            self.grid.sizes.pop(self.path, None)
        self._sync()
        return True

    def print_image(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        if self.image.isNull():
            return
        printer = self.answers.get("print")
        if printer is None:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
                return
        print_image(self.image, printer)

    # ================================================================== file commands
    def _targets(self) -> list[str]:
        """The pictures a file command is for: the grid's selection in Thumbnails, else the one shown."""
        if self.stack.currentWidget() is self.grid and self.grid.selected_files():
            return self.grid.selected_files()
        return [self.path] if self.path and os.path.exists(self.path) else []

    def delete(self):
        targets = self._targets()
        if not targets:
            return
        what = os.path.basename(targets[0]) if len(targets) == 1 else f"these {len(targets)} pictures"
        if not self._ask("delete", what):
            return
        for p in targets:
            try:
                files.trash(p)
            except (files.FileError, OSError) as e:
                self._ask("error", str(e))
                break
            self.thumbs.forget(p)
            self.folder.removed(p)
        self.modified = False
        self.strip.set_files(self.folder.files, self.folder.index)
        if self.stack.currentWidget() is self.grid:
            self._fill_grid()
        self._load()

    def copy_move(self, move: bool):
        targets = self._targets()
        if not targets or (move and not self._may_leave()):
            return
        dest = self._ask("folder", "Move to" if move else "Copy to")
        if not dest:
            return
        settings.set("last_copy_dir", dest)
        for p in targets:
            try:
                (files.move_to if move else files.copy_to)(p, dest)
            except OSError as e:
                self._ask("error", f"{os.path.basename(p)}: {e}")
                return
            if move:
                self.folder.removed(p)
        if move:
            self.strip.set_files(self.folder.files, self.folder.index)
            if self.stack.currentWidget() is self.grid:
                self._fill_grid()
            self._load()

    def rename(self):
        if not self.path or not os.path.exists(self.path) or not self._may_leave():
            return
        name = self._ask("rename", os.path.basename(self.path))
        if not name or name == os.path.basename(self.path):
            return
        try:
            new = files.rename(self.path, name)
        except (files.FileError, OSError) as e:
            self._ask("error", str(e))
            return
        self.folder.renamed(self.path, new)
        self.path = new
        self.strip.set_files(self.folder.files, self.folder.index)
        self._sync()

    def show_in_folder(self):
        if self.path:
            files.show_in_folder(self.path)

    def wallpaper(self):
        if self.path and not files.set_wallpaper(self.path) and sys.platform == "win32":
            self._ask("error", "Windows didn't take the picture as the wallpaper.")

    # ================================================================== Thumbnails, information, slideshow
    def toggle_thumbnails(self):
        if self.stack.currentWidget() is self.grid:
            self.stack.setCurrentWidget(self.view)
            self.strip.setVisible(self.acts["show_strip"].isChecked() and not self.fullscreen)
        else:
            if not self.folder.count:
                return
            self._fill_grid()
            self.stack.setCurrentWidget(self.grid)
            self.strip.hide()
            self.grid.setFocus()
        self.k_thumbs.setChecked(self.stack.currentWidget() is self.grid)
        self.acts["thumbnails"].setChecked(self.stack.currentWidget() is self.grid)
        self._sync()

    def _fill_grid(self):
        folder_name = os.path.basename(os.path.dirname(self.folder.files[0])) if self.folder.files else ""
        self.grid.set_files(self.folder.files, self.folder.index,
                            f"{folder_name.upper()}   ·   {self.folder.count} IMAGES")

    def _grid_open(self, i: int):
        self.toggle_thumbnails()
        self.go(i)

    def information(self):
        if self.image.isNull():
            return
        dlg = InfoDialog(self.path, self.image, self)
        self.info_dialog = dlg
        if "info" not in self.answers:
            dlg.exec()

    def slideshow_dialog(self):
        if self.folder.count < 2:
            return
        secs = self._ask("slideshow")
        if secs:
            settings.set("slide_seconds", float(secs))
            self.start_slideshow(float(secs))

    def start_slideshow(self, seconds: float):
        if not self.fullscreen:
            self.toggle_fullscreen()
        self.slideshow.start(int(seconds * 1000))

    def _slide(self):
        if self.folder.count < 2 or self.modified:
            self.slideshow.stop()
            return
        self.step(1)

    def toggle_fullscreen(self):
        if self.image.isNull() and not self.fullscreen:
            return
        self.fullscreen = not self.fullscreen
        self.view.fullscreen = self.fullscreen
        for w in (self.menuBar(), self.header):
            w.setVisible(not self.fullscreen)
        self._show("toolbar", self.acts["show_toolbar"].isChecked(), save=False)
        self._show("statusbar", self.acts["show_statusbar"].isChecked(), save=False)
        self._show("strip", self.acts["show_strip"].isChecked() and self.stack.currentWidget() is self.view, save=False)
        if self.fullscreen:
            self._was_max = self.isMaximized()
            if self.stack.currentWidget() is self.grid:
                self.toggle_thumbnails()
            self.showFullScreen()
        else:
            self.slideshow.stop()
            self.showMaximized() if getattr(self, "_was_max", False) else self.showNormal()
        self.view.relayout(centre=True)
        self.view.setFocus()

    def _escape(self):
        if self.fullscreen:
            self.toggle_fullscreen()
        elif self.stack.currentWidget() is self.grid:
            self.toggle_thumbnails()
        elif not self.view.selection.isNull():
            self.view.set_selection(QRect())
        elif settings.get_bool("esc_closes", True):
            self.close()

    # ================================================================== menus, settings, help
    def _view_menu(self, pos):
        if self.image.isNull():
            return
        m = QMenu(self)
        for key in ("copy", "crop", "select_all", None, "rotate_left", "rotate_right", "flip_h", None, "info",
                    "fullscreen", None, "folder", "wallpaper", "delete"):
            if key is None:
                m.addSeparator()
            else:
                m.addAction(self.acts[key])
        m.exec(self.view.viewport().mapToGlobal(pos))

    def set_finish(self, name: str):
        theme.set_finish(name)
        finish.set(theme.FINISH)                 # every family app follows (finish.py)
        settings.set("finish", name)
        apply_look(QApplication.instance())
        for gap in self.toolbar.findChildren(QFrame, "gap"):
            gap.setStyleSheet(f"background: {theme.PANEL_EDGE};")
        self.acts[f"finish_{name}"].setChecked(True)
        for w in (self.header, self.view.viewport(), self.strip.viewport(), self.grid.viewport()):
            w.update()

    def options(self):
        dlg = OptionsDialog(self)
        self.options_dialog = dlg
        if "options" not in self.answers and dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply()
            self.folder.loop = settings.get_bool("loop_folder", True)

    def check_updates(self):
        from . import update_ui
        update_ui.check(self, manual=True)

    def shortcuts(self):
        rows = [("Next / previous image", "Right, Space, wheel / Left, Backspace"), ("First / last", "Home / End"),
                ("Zoom in / out", "+ / -, Ctrl+wheel"), ("Fit images to window / original size", "Shift+F / Ctrl+H"),
                ("Select / move the picture", "Left drag / right drag"),
                ("Rotate left / right", "L / R"), ("Vertical / horizontal flip", "V / H"),
                ("Crop selection", "Ctrl+Y"), ("Resize", "Ctrl+R"), ("Information", "I"), ("Thumbnails", "T"),
                ("Slideshow", "W"), ("Full screen", "Enter, double-click"), ("Save / save as", "Ctrl+S / S"),
                ("Copy to / move to / rename / delete", "F8 / F7 / F2 / Del"), ("Undo / redo", "Ctrl+Z / Ctrl+Shift+Z"),
                ("Close (or leave full screen)", "Esc")]
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        form = QFormLayout(dlg)
        for what, keys in rows:
            k = QLabel(keys); k.setStyleSheet(f"color: {theme.TEXT_DIM};")
            form.addRow(what, k)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        self.shortcuts_dialog = dlg
        if "shortcuts" not in self.answers:
            dlg.exec()

    def about(self):
        if "about" not in self.answers:
            QMessageBox.about(self, "About Paragon PR7-P",
                              f"<b>Paragon PR7-P</b> {__version__}<br>An image viewer that works the way IrfanView "
                              "and ImageGlass work.")

    # ================================================================== drag and drop, closing
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.open_path(u.toLocalFile())
                e.acceptProposedAction()
                return

    def closeEvent(self, e):
        if not self._may_leave():
            e.ignore()
            return
        self.slideshow.stop()
        self.thumbs.wait()
        super().closeEvent(e)


def print_image(img: QImage, printer) -> None:
    """The picture fitted to the paper and centred (IrfanView's "best fit to page")."""
    from PySide6.QtPrintSupport import QPrinter
    p = QPainter()
    if not p.begin(printer):
        return
    area = printer.pageRect(QPrinter.Unit.DevicePixel)
    k = min(area.width() / img.width(), area.height() / img.height())
    w, h = img.width() * k, img.height() * k
    from PySide6.QtCore import QRectF
    p.drawImage(QRectF((area.width() - w) / 2, (area.height() - h) / 2, w, h), img)
    p.end()


# ==================================================================== dialogs
class InfoDialog(QDialog):
    """Image > Information (I): the file, the picture and the camera."""

    def __init__(self, path: str | None, img: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Information")
        self.setMinimumWidth(520)
        g = QGridLayout(self)
        g.setHorizontalSpacing(18)
        rows: list[tuple[str | None, str]] = []
        if path and os.path.exists(path):
            inf = imageio.info(path, img)
            fmt = inf.format + (", progressive" if inf.extra.get("progressive") else "") + \
                (f", {inf.extra['subsampling']}" if inf.extra.get("subsampling") else "")
            rows += [("File name", os.path.basename(path)), ("Folder", os.path.dirname(path)), ("Format", fmt),
                     ("Original size", f"{inf.width} x {inf.height} pixels ({inf.megapixels:.2f} MP)"),
                     ("Current size", f"{img.width()} x {img.height()} pixels"),
                     ("Print size", inf.print_size()), ("Colours", inf.colours),
                     ("Frames", str(inf.frames)) if inf.frames > 1 else ("", ""),
                     ("Disk size", f"{inf.file_size / 1024:,.0f} KB ({inf.file_size:,} bytes)"),
                     ("File date", imageio.date_text(inf.modified))]
            cam = exif.read(path)
            if cam:
                rows.append((None, "CAMERA (EXIF)"))
                rows += list(cam.items())
        else:
            rows += [("Source", "Clipboard"), ("Current size", f"{img.width()} x {img.height()} pixels")]
        self.rows = [(k, v) for k, v in rows if k != ""]
        title = QLabel("IMAGE INFORMATION"); title.setObjectName("head")
        g.addWidget(title, 0, 0, 1, 2)
        for i, (k, v) in enumerate(self.rows, 1):
            if k is None:
                h = QLabel(v); h.setObjectName("head"); g.addWidget(h, i, 0, 1, 2); continue
            a = QLabel(k.upper()); a.setObjectName("key")
            b = QLabel(v); b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); b.setWordWrap(True)
            g.addWidget(a, i, 0); g.addWidget(b, i, 1)
        bb = QDialogButtonBox()
        copy = bb.addButton("COPY", QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(self.copy)
        bb.addButton("CLOSE", QDialogButtonBox.ButtonRole.RejectRole)
        bb.rejected.connect(self.reject)
        g.addWidget(bb, len(self.rows) + 1, 0, 1, 2)

    def values(self) -> dict:
        return {k: v for k, v in self.rows if k}

    def text(self) -> str:
        return "\r\n".join(f"{k}: {v}" if k else f"\r\n{v}" for k, v in self.rows)

    def copy(self):
        QGuiApplication.clipboard().setText(self.text())


class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties / Settings")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.zoom = QComboBox()
        for text, val in ZOOM_CHOICES[:3]:
            self.zoom.addItem(text, str(val))
        self.zoom.setCurrentIndex(max(0, self.zoom.findData(settings.get("default_zoom", FIT_BIG))))
        self.quality = QSpinBox(); self.quality.setRange(1, 100); self.quality.setValue(settings.get_int("jpeg_quality", 90))
        self.loop = QCheckBox("Go round from the last picture to the first"); self.loop.setChecked(
            settings.get_bool("loop_folder", True))
        self.keep_zoom = QCheckBox("Keep the zoom for the next picture"); self.keep_zoom.setChecked(
            settings.get_bool("keep_zoom", False))
        self.confirm = QCheckBox("Ask before deleting"); self.confirm.setChecked(settings.get_bool("confirm_delete", True))
        self.esc = QCheckBox("Esc closes PR7-P (as in IrfanView)"); self.esc.setChecked(settings.get_bool("esc_closes", True))
        from . import update_ui
        self.updates = QCheckBox("Check for updates automatically"); self.updates.setChecked(update_ui.auto_enabled())
        form.addRow("ZOOM", self.zoom)
        form.addRow("JPEG QUALITY", self.quality)
        for w in (self.loop, self.keep_zoom, self.confirm, self.esc, self.updates):
            form.addRow(w)
        from . import shell
        if shell.available():
            b = QPushButton("Make PR7-P the default image viewer...")
            b.clicked.connect(shell.open_default_apps)
            form.addRow(b)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def apply(self):
        from . import update_ui
        settings.set("default_zoom", self.zoom.currentData())
        settings.set("jpeg_quality", self.quality.value())
        settings.set("loop_folder", self.loop.isChecked())
        settings.set("keep_zoom", self.keep_zoom.isChecked())
        settings.set("confirm_delete", self.confirm.isChecked())
        settings.set("esc_closes", self.esc.isChecked())
        update_ui.set_auto(self.updates.isChecked())
