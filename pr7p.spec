# PyInstaller build of PR7-P: pyinstaller pr7p.spec  ->  dist/PR7-P/PR7-P.exe  (folder build: starts fast)
#
# Windows Defender judges unknown, unsigned programs partly by how they look: a PyInstaller program with no file
# details and the stock (shared, much-copied) starter is a common false positive. So the .exe carries proper
# version details (Properties > Details), and CI builds PyInstaller's starter from source (see build.yml).
import re
import sys
from pathlib import Path


root = Path(SPECPATH)
version = re.search(r'__version__ = "(.+?)"', (root / "pr7p" / "__init__.py").read_text()).group(1)
nums = tuple(int(x) for x in (version.split(".") + ["0", "0", "0"])[:4])
details = None
if sys.platform == "win32":  # version resources exist only in Windows programs
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    details = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Paragon"),
            StringStruct("FileDescription", "Paragon PR7-P image viewer"),
            StringStruct("FileVersion", version),
            StringStruct("InternalName", "PR7-P"),
            StringStruct("LegalCopyright", "Paragon"),
            StringStruct("OriginalFilename", "PR7-P.exe"),
            StringStruct("ProductName", "Paragon PR7-P"),
            StringStruct("ProductVersion", version)])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])

a = Analysis(
    [str(root / "tools" / "launcher.py")],
    pathex=[str(root)],
    datas=[(str(root / "pr7p" / "fonts"), "pr7p/fonts"), (str(root / "pr7p" / "icons"), "pr7p/icons")],
    # QtPrintSupport prints; QtNetwork's local socket hands files to an open window; Qt's image plugins (WebP, TIFF,
    # ICO, SVG...) come with PySide6's hook; Pillow reads AVIF, JPEG 2000, PCX, PSD and keeps EXIF when saving.
    hiddenimports=["PySide6.QtPrintSupport", "PySide6.QtNetwork", "PySide6.QtSvg", "PIL.AvifImagePlugin",
                   "PIL.Jpeg2KImagePlugin", "PIL.PcxImagePlugin", "PIL.PsdImagePlugin"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PR7-P", console=False, upx=False,  # no UPX: packed
          icon=str(root / "pr7p" / "icons" / "app.ico"), version=details)          # .exes look worse still
coll = COLLECT(exe, a.binaries, a.datas, name="PR7-P", upx=False)
