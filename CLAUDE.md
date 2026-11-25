# Paragon PR7-P: notes for Claude

**Paragon PR7-P** is the owner's personal image viewer: Python (**PySide6** + **Pillow**) that **works the way
IrfanView works** (menus, keys, status line, Thumbnails, Information) with **ImageGlass's** thumbnail strip, in the
Paragon family look (PR7-Z, PR7-W, PR7-L, PR7-F, PR7-E, PR7-R `ARYEZ/Paragon-PR7-R`). Windows 10/11 x64 is the target;
it runs on Linux for tests. The owner writes Python; explain the why of changes.

## How it's built

- `pr7p/folder.py` (no Qt): `IMAGE_EXTS` (Qt's plugins + Pillow's extras), `natural_key`, `Folder` (open a file or a
  folder, `step` loops round unless `loop` is off, `removed` / `renamed` keep the place).
- `pr7p/imageio.py`: `read` (QImageReader with autoTransform = EXIF orientation applied, Pillow fallback for AVIF /
  JPEG 2000 / PCX / PSD), `info` (Pillow for format, bits, dpi, JPEG subsampling), `write` (temp file then replace;
  JPEG and AVIF through Pillow, JPEG keeps EXIF with Orientation reset to 1; GIF through Pillow; the rest QImageWriter),
  `to_pil` / `from_pil`. `pr7p/exif.py`: camera details for the Information dialog (IFDRational for test EXIF).
- Windows lesson: never hand QImageWriter a file name and then move the file: it keeps the file open until the writer
  is gone, and Windows won't move an open file. `imageio.write` opens, writes and closes a QFile itself first.
- `pr7p/edit.py`: the Image menu as pure functions QImage -> QImage (Undo is a list of images, last 20 kept).
- `pr7p/viewer.py`: `ImageView` (QAbstractScrollArea): FIT / FIT_BIG / percent, `fit_scale`, `step_zoom`, IrfanView's
  mouse (wheel emits `step`, Ctrl+wheel zooms at the pointer, left drag = selection in image pixels, right drag pans,
  right click = menu, double click = full screen), QMovie for animations, chequerboard under transparency.
- `pr7p/thumbs.py`: `Thumbs` (QThreadPool; `sync=True` in tests; QImageReader.setScaledSize before the orientation
  turn), `Strip`, `Grid` (selection set used by Delete / Copy to / Move to), `shown_size` (turned sizes).
- `pr7p/files.py`: Delete = QFile.moveToTrash (Recycle Bin); **PR7P_TRASH points it at a folder: tests always set it**.
  `free_name` never overwrites on Copy / Move to; `name_problem` uses Windows' rules.
- `pr7p/main_window.py`: menus via `_act(..., key=)` into `acts`; `_ask(kind)` for every question (tests:
  `window.answers`); `_may_leave` asks save / discard / cancel for a changed picture; `_sync` sets keys, menus and the
  status line; `InfoDialog`, `OptionsDialog`, `print_image`.
- `pr7p/app.py`: one window per user (QLocalSocket, PR7-R's hand-off incl. its Windows fix), `--register` /
  `--unregister` (shell.py: Open with + Capabilities for image types, HKCU), `--selftest FOLDER OUT.json`.
- `tools/sample_images.py`: stand-in photos (Qt-drawn) and `with_exif` (camera details and orientation, Pillow).
- Installer `installer/pr7p.iss` (per user, AppId {02CE0A66-B141-47AD-9489-ACCB0C53E81C} permanent); CI installs it,
  `tools/verify_install.py installed` runs the installed exe on JPEG / WebP / TIFF / GIF / AVIF and an EXIF-turned photo.
- Updates: `pr7p/updates.py` (no Qt; GitHub's public releases/latest, User-Agent names only the app, installer asset `PR7-P-Setup-*.exe`, run with /SILENT /relaunch=1) and `update_ui.py` (once-a-day check from app.py, the menu's Check for Updates, UpdateDialog; settings updates/auto|last|skip; `notify` for tests). The installer's [Code] Relaunch starts PR7-P again only for /relaunch=1. Same files in every family app (PR7-W's update_ui imports PyQt6): keep them in step. With PR7-U (the family installer) installed, update_ui offers it (`_family_app`, `open_family`; `answer` for tests); every app has the shared family.py with all ten AppIds. `family.py`: the other family apps by their permanent AppIds (uninstall InstallLocation).

## The look (family rules)

- Theme is PR7-R's (OBSIDIAN + AURORA via `theme.set_finish`). Colours: the family's only (hues ~318 -> 0 -> 42 deg,
  pearl and onyx greys), selection and thumbnail marks included; Inter; labels UPPER CASE; file names keep their case.
- The PR7-P mark: PR7 `Logo.cpp` geometry plus a P (`widgets.R_BOWL` / `R_COUNTER`); icon by `tools/make_icon.py`,
  wizard art by `tools/make_installer_art.py`. Check visuals with `QT_SCALE_FACTOR=2 python tools/screenshots.py OUT`.

## Rules

- Behaviour questions: do what IrfanView does (menus, keys, dialogs); the strip as ImageGlass.
- Tests: `python -m pytest` (offscreen) on real pictures in temp folders. Never the real settings (conftest), Recycle
  Bin (PR7P_TRASH) or, outside CI, the registry.
- Releases: bump `__version__` in `pr7p/__init__.py` and add a `## x.y.z` section to CHANGELOG.md, then push:
  CI publishes that version by itself once every check has passed (the "Is this version released yet?"
  step; this session can't start workflows or push tags). Run workflow / `v*` tags still work.
