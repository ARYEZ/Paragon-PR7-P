"""Start PR7-P.

    PR7-P.exe [picture or folder]        show it (in the PR7-P window that's open already: double-clicking another
                                          picture shows it there instead of opening a second window)
    PR7-P.exe -new-window picture.jpg    a window of its own
    PR7-P.exe --register / --unregister  "Open with" and Default apps for pictures (the installer runs these)
    PR7-P.exe --version
    PR7-P.exe --selftest FOLDER OUT.json  open the folder offscreen and write what was shown and read (CI checks the
                                          installed program with it; settings go to a temp folder)
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys

TIMEOUT_MS = 1500


def server_name() -> str:
    """One window per user: a local socket named after the user (hashed: names must be plain)."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no user name: one name for all
        user = "user"
    return "Paragon-PR7-P-" + hashlib.sha1(user.encode()).hexdigest()[:12]


def parse(argv: list[str]) -> tuple[str | None, bool]:
    """(picture or folder, new window) from the command line."""
    path, new = None, False
    for a in argv:
        low = a.lower().lstrip("-")
        if low in ("new-window", "newwindow"):
            new = True
        elif not a.startswith("-") and path is None:
            path = os.path.abspath(a.strip('"'))
    return path, new


def hand_over(path: str | None) -> bool:
    """If a PR7-P window is open, give it the picture and return True."""
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(server_name())
    if not s.waitForConnected(TIMEOUT_MS):
        return False
    s.write(json.dumps({"path": path}).encode() + b"\n")
    s.flush()
    s.waitForBytesWritten(TIMEOUT_MS)
    # The window closes the connection once it has the message: wait for that, so this process doesn't end before
    # it's delivered (a named pipe on Windows); then close our end if it hasn't.
    if not s.waitForDisconnected(TIMEOUT_MS):
        s.disconnectFromServer()
    return True


def listen(window):
    """Take pictures from later launches (hand_over) into this window."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(server_name())   # a name left by a PR7-P that crashed
    if not server.listen(server_name()):
        return None

    def connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        done = []

        def read():
            buf.extend(bytes(sock.readAll()))
            if buf.endswith(b"\n") and not done:
                done.append(True)
                try:
                    msg = json.loads(buf.decode())
                except ValueError:
                    return
                if msg.get("path"):
                    window.open_path(msg["path"])
                if window.isMinimized():
                    window.showNormal()
                window.raise_()
                window.activateWindow()
                sock.disconnectFromServer()
        sock.readyRead.connect(read)
        sock.disconnected.connect(read)
        if sock.bytesAvailable():      # on Windows the message can be here before readyRead is connected
            read()
    server.newConnection.connect(connection)
    window.instance_server = server
    return server


def selftest(folder: str, out: str) -> int:
    import tempfile
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PR7P_TRASH"] = tempfile.mkdtemp()
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    result = {}
    try:
        from PySide6.QtGui import QFontDatabase

        from . import __version__, exif, folder as folder_mod, theme
        from .main_window import MainWindow, apply_look
        app = QApplication.instance() or QApplication(sys.argv[:1])
        theme.load_fonts()
        apply_look(app)
        w = MainWindow(folder, thumbs_sync=True)
        w.show()
        app.processEvents()
        names = [os.path.basename(f) for f in w.folder.files]
        sizes = {}
        for f in w.folder.files:          # every format the build should read
            w.go(w.folder.files.index(f))
            sizes[os.path.basename(f)] = [w.image.width(), w.image.height()]
        thumbs_ok = all(not w.thumbs.get(f).isNull() for f in w.folder.files)
        cameras = {os.path.basename(f): exif.read(f).get("Camera", "") for f in w.folder.files}
        result = {"version": __version__, "names": names, "sizes": sizes, "thumbs": thumbs_ok,
                  "cameras": {k: v for k, v in cameras.items() if v},
                  "formats": sorted({folder_mod.ext(f) for f in w.folder.files}),
                  "fonts": "Inter" in QFontDatabase.families()}
        w.close()
    except Exception as e:  # noqa: BLE001 - reported in the output
        result = {"error": f"{type(e).__name__}: {e}"}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0 if "names" in result else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--version"]:
        from . import __version__
        print(__version__)
        return 0
    if argv[:1] == ["--selftest"] and len(argv) == 3:
        return selftest(argv[1], argv[2])
    if argv[:1] and argv[0] in ("--register", "--unregister"):
        from . import shell
        return shell.run(argv[0])
    path, new = parse(argv)
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import settings, theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Paragon")
    app.setApplicationName("PR7-P")
    if not new and hand_over(path):
        return 0
    theme.set_finish(settings.get("finish", "obsidian"))
    theme.load_fonts()
    from .main_window import MainWindow, apply_look
    apply_look(app)
    icon = os.path.join(os.path.dirname(__file__), "icons", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    w = MainWindow(path)
    w.show()
    if not new:
        listen(w)
    from . import update_ui
    update_ui.start(w)  # a check for updates, once a day
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
