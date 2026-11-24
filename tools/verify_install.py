"""Check a real install of PR7-P-Setup.exe (CI, Windows): python tools/verify_install.py installed|uninstalled

`installed` runs the installed PR7-P.exe offscreen on a folder of pictures (--selftest): JPEG, PNG, WebP, TIFF, GIF,
AVIF and a camera photo turned by its orientation tag. That shows the frozen program starts with Qt, its image
plugins, Pillow and the Inter fonts. It also checks the "Open with" and Default apps registration. `uninstalled`
checks all of it is gone."""
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HKCU = winreg.HKEY_CURRENT_USER
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PR7-P"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Paragon PR7-P.lnk"
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{02CE0A66-B141-47AD-9489-ACCB0C53E81C}_is1"
PROGID = r"Software\Classes\Paragon.PR7P.Image"


def value(path, name=""):
    try:
        with winreg.OpenKey(HKCU, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def exists(path, name):
    """Whether a value is there (an empty REG_NONE value, as Open with's entries are, reads back as None)."""
    try:
        with winreg.OpenKey(HKCU, path) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def check(ok, what, p):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        p.append(what)


def installed():
    p = []
    exe = APP / "PR7-P.exe"
    for f in (exe, APP / "unins000.exe", APP / "_internal" / "pr7p" / "fonts" / "Inter-Regular.ttf",
              APP / "_internal" / "pr7p" / "icons" / "app.ico"):
        check(f.is_file(), f"file {f}", p)
    check(SHORTCUT.is_file(), "Start menu shortcut", p)
    check(value(UNINSTALL, "DisplayName") == "Paragon PR7-P", "Installed apps entry", p)
    cmd = value(PROGID + r"\shell\open\command") or ""
    check(str(exe).lower() in cmd.lower() and cmd.endswith('"%1"'), f"picture open command: {cmd}", p)
    for ext in ("jpg", "png", "webp"):
        check(exists(rf"Software\Classes\.{ext}\OpenWithProgids", "Paragon.PR7P.Image"), f"Open with lists PR7-P for .{ext}", p)
    check(value(r"Software\RegisteredApplications", "Paragon PR7-P") == r"Software\Paragon\PR7-P\Capabilities",
          "Default apps lists PR7-P", p)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(["x", "-platform", "offscreen"])
    import sample_images
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d) / "Pictures"
        files = sample_images.folder(folder, 4, (600, 400))
        sample_images.with_exif(files[0], orientation=6)          # shown 400 x 600
        with Image.open(files[1]) as im:
            for fmt in ("webp", "tif", "gif", "avif"):
                im.save(folder / f"extra.{fmt}")
        out = Path(d) / "out.json"
        subprocess.run([str(exe), "--selftest", str(folder), str(out)], timeout=180, check=False)
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        sizes = got.get("sizes", {})
        check(len(got.get("names", [])) == 8 and got.get("thumbs") is True and got.get("fonts") is True,
              f"PR7-P.exe opens a folder of pictures ({got})", p)
        check(sizes.get("IMG_2041.jpg") == [400, 600], "the camera's orientation is applied", p)
        for fmt in ("webp", "tif", "gif", "avif"):
            check(sizes.get(f"extra.{fmt}") == [600, 400], f"reads .{fmt}", p)
        check(got.get("cameras", {}).get("IMG_2041.jpg") == "FUJIFILM X-T5", "reads camera details", p)
    del app
    return p


def uninstalled():
    deadline = time.time() + 60
    while True:
        p = []
        check(not (APP / "PR7-P.exe").exists(), "program files removed", p)
        check(not SHORTCUT.exists(), "Start menu shortcut removed", p)
        check(value(UNINSTALL, "DisplayName") is None, "Installed apps entry removed", p)
        check(value(PROGID) is None, "picture type removed", p)
        check(value(r"Software\RegisteredApplications", "Paragon PR7-P") is None, "Default apps entry removed", p)
        if not p or time.time() > deadline:
            return p
        print("... waiting for the uninstaller to finish")
        time.sleep(3)


if __name__ == "__main__":
    problems = {"installed": installed, "uninstalled": uninstalled}[sys.argv[1]]()
    print("\nALL OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
